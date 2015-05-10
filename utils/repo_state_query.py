#! /usr/bin/env python

# Expect the following STDIN and file format:
#   project_path
#   project_sha to checkout
#   ...

import argparse
import sys

def get_flags():
    """
    Parses command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('projects', metavar='PROJS', type=str, nargs='+',
        help='projects to query')
    parser.add_argument('--input_file', metavar='INPUT_FILE', type=str,
        help='read from input_file')
    return parser.parse_args()

class RepoStateReader(object):
    def __init__(self, file_handle):
        self.projects = {}

        project_name = None
        project_hash = None
        while True:
            line = file_handle.readline()
            if not line:
                break

            if project_name is None:
                project_name = line.strip()
            else:
                project_hash = line.strip()

                if project_name not in self.projects:
                    self.projects[project_name] = project_hash
                else:
                    print >> sys.stderr, 'WARNING: Collision detected for project %s' % project_name

                project_name = None
                project_hash = None

    def get_project_hash(self, project_name, default_value=None):
        """
        Returns the commit hash for a project_name.  Returns None if the project_name is unknown.
        """
        return self.projects.get(project_name, default_value)

if __name__ == '__main__':
    flags = get_flags()

    if flags.input_file is not None:
        with open(flags.input_file) as file_handle:
            rsr = RepoStateReader(file_handle)
    else:
        rsr = RepoStateReader(sys.stdin)

    for projects in flags.projects:
        print rsr.get_project_hash(projects, '')
