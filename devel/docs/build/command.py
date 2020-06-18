import argparse
import os
import sys

from dt_shell import DTCommandAbs, dtslogger

from utils.docker_utils import get_endpoint_architecture
from utils.cli_utils import start_command_in_subprocess


class DTCommand(DTCommandAbs):

    help = 'Builds the current project\'s documentation'

    @staticmethod
    def command(shell, args):
        # configure arguments
        parser = argparse.ArgumentParser()
        parser.add_argument('-C', '--workdir', default=os.getcwd(),
                            help="Directory containing the project to build")
        parser.add_argument('-f', '--force', default=False, action='store_true',
                            help="Whether to force the build when the git index is not clean")
        parser.add_argument('-u', '--username',default="duckietown",
                            help="The docker registry username to tag the image with")
        parser.add_argument('--no-cache', default=False, action='store_true',
                            help="Whether to use the Docker cache")
        parser.add_argument('--push', default=False, action='store_true',
                            help="Whether to push the resulting documentation")
        parser.add_argument('--loop', default=False, action='store_true',
                            help="(Developers only) Reuse the same base image, speed up the build")
        parser.add_argument('--ci', default=False, action='store_true',
                            help="Overwrites configuration for CI (Continuous Integration) builds")
        parser.add_argument('--quiet', default=False, action='store_true',
                            help="Suppress any building log")
        parsed, _ = parser.parse_known_args(args=args)
        # ---
        parsed.workdir = os.path.abspath(parsed.workdir)
        dtslogger.info('Project workspace: {}'.format(parsed.workdir))
        # CI builds
        if parsed.ci:
            parsed.pull = True
            parsed.cloud = True
            parsed.no_multiarch = True
            parsed.push = True
            parsed.rm = True
            # check that the env variables are set
            for key in ['MAJOR', 'DT_TOKEN']:
                if 'DUCKIETOWN_CI_'+key not in os.environ:
                    dtslogger.error(
                        'Variable DUCKIETOWN_CI_{:s} required when building with --ci'.format(key)
                    )
                    sys.exit(5)
        # show info about project
        if not parsed.quiet:
            shell.include.devel.info.command(shell, args)
        # get info about current repo
        repo_info = shell.include.devel.info.get_repo_info(parsed.workdir)
        repo = repo_info['REPOSITORY']
        branch = repo_info['BRANCH']
        nmodified = repo_info['INDEX_NUM_MODIFIED']
        nadded = repo_info['INDEX_NUM_ADDED']
        # check if the index is clean
        if nmodified + nadded > 0:
            dtslogger.warning('Your index is not clean (some files are not committed).')
            dtslogger.warning('If you know what you are doing, use --force (-f) to ' +
                              'force the build.')
            if not parsed.force:
                exit(1)
            dtslogger.warning('Forced!')
        # in CI, we only build certain branches
        if parsed.ci and os.environ['DUCKIETOWN_CI_MAJOR'] != branch:
            dtslogger.info(
                'CI is looking for the branch "{:s}", this is "{:s}". Nothing to do!'.format(
                    os.environ['DUCKIETOWN_CI_MAJOR'], branch
                )
            )
            exit(0)

        # get the arch
        arch = get_endpoint_architecture()

        # create defaults
        image = "%s/%s" % (parsed.username, repo)
        image_tag_components = [branch]
        docs_tag_components = [branch, 'docs']
        if parsed.loop:
            image_tag_components += ['LOOP']
            docs_tag_components += ['LOOP']
        image_tag_components += [arch]
        docs_tag_components += [arch]
        tag = "%s:%s" % (image, '-'.join(image_tag_components))
        docs_tag = "%s:%s" % (image, '-'.join(docs_tag_components))

        # file locators
        repo_file = lambda *p: os.path.join(parsed.workdir, *p)
        docs_file = lambda *p: os.path.join(repo_file('docs'), *p)

        # check if folders and files exist
        dtslogger.info("Checking if the documentation files are in order...")
        for f in ['', 'config.yaml', 'index.rst']:
            if not os.path.exists(docs_file(f)):
                dtslogger.error(f"File {docs_file(f)} not found. Aborting.")
                return
        dtslogger.info("Done!")

        # build and run the docs container
        dtslogger.info("Building the documentation environment...")
        cmd_dir = os.path.dirname(os.path.abspath(__file__))
        dockerfile = os.path.join(cmd_dir, 'Dockerfile')
        start_command_in_subprocess([
            'docker',
                'build',
                    '-f', dockerfile,
                    '-t', docs_tag,
                    '--build-arg', f'BASE_IMAGE={tag}',
                    f'--no-cache={int(parsed.no_cache)}',
                    cmd_dir
        ], shell=False, nostdout=parsed.quiet, nostderr=parsed.quiet)
        dtslogger.info("Done!")

        # clear output directory
        for f in os.listdir(repo_file('html')):
            if f.endswith('HTML_DOCS_WILL_BE_GENERATED_HERE'):
                continue
            start_command_in_subprocess([
                'rm', '-rf', repo_file('html', f)
            ], shell=False, nostdout=parsed.quiet, nostderr=parsed.quiet)

        # build docs
        dtslogger.info("Building the documentation environment...")
        start_command_in_subprocess([
            'docker',
                'run',
                    '-it',
                    '--rm',
                    '--user', str(os.geteuid()),
                    '--volume', f"{repo_file('docs')}:/docs/in",
                    '--volume', f"{repo_file('html')}:/docs/out",
                    docs_tag
        ], shell=False, nostdout=parsed.quiet, nostderr=parsed.quiet)
        dtslogger.info("Done!")

    @staticmethod
    def complete(shell, word, line):
        return []
