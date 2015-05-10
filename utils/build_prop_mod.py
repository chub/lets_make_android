#! /usr/bin/python

import argparse

class BuildPropMod(object):
    def __init__(self,
                 bp_file=None,
                 delete_list=None,
                 prop_append=None,
                 prop_set=None):
        self.bp_file = bp_file
        self.delete_list = delete_list
        self.prop_append = prop_append
        self.prop_set = prop_set

    def process_line(self, line):
        # True if the line should be commented
        is_comment = False

        # Remove any trailing newlines. Keep trailing whitespace.
        line = line.rstrip('\n')

        if line.startswith('#'):
            is_comment = True

            # Remove leading # comments.
            line = line.lstrip('#')

        if '=' in line:
            # Find (key, val) pair
            key, value = line.split('=', 1)

            if key in self.prop_set:
                # Update value to the one specified in the flags
                value = self.prop_set.get(key)
                # And delete it
                del self.prop_set[key]
                # And the line will no longer be a comment
                is_comment = False
            elif key in self.prop_append:
                # Append specified value
                value += self.prop_append.get(key)
                # And delete it
                del self.prop_append[key]
                # Assume this is an undeleted prop
                is_comment = False

            if key in self.delete_list:
                is_comment = True

            # Reconstruct line
            line = '%s=%s' % (key, value)

        if is_comment:
            line = '#%s' % line

        return line

    def run(self):
        self.new_lines = []

        # Read in all lines, and update by appending to another object
        # Update the lines (copy into new object, lest you use list comprehension and [:])
        for line in self.bp_file.xreadlines():
            new_line = self.process_line(line)

            # None means to completely delete it.
            if new_line is not None:
                self.new_lines.append(new_line)

        # Process any leftover overrides
        for key, value in self.prop_set.iteritems():
            self.new_lines.append('%s=%s' % (key, value))
        for key, value in self.prop_append.iteritems():
            self.new_lines.append('%s=%s' % (key, value))

        # Reset to beginning and truncate
        self.bp_file.seek(0, 0)
        self.bp_file.truncate()

        # Write each line
        for line in self.new_lines:
            self.bp_file.write(line)
            self.bp_file.write("\n")
        self.bp_file.close()

def get_flags():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=argparse.FileType('r+'), required=True,
                        help='a build.prop file to modify')
    parser.add_argument('--delete', type=str,
                        action='append',
                        metavar='KEY',
                        default=[],
                        help='properties to remove')
    parser.add_argument('--append', type=str,
                        action='append',
                        metavar='KEY=VAL',
                        default=[],
                        help='properties to append')
    parser.add_argument('prop_set_list', metavar='KEY=VAL',
                        nargs='*',
                        default=[],
                        help='properties to set')
    return parser.parse_args()

if __name__ == '__main__':
    # Usage:
    # python build_prop_mod.py \
    #     --file build.prop \  # input and output file
    #     --delete ro.build.selinux \    # delete prop if exists
    #     --delete drm.service.enabled \ # delete prop if exists
    #     --append "ro.build.description= selinux-caf" \ # append to existing prop
    #     ro.com.android.dateformat=yyyy-MM-dd \         # replace existing prop
    #     ro.cool.stuff=abcdef                           # i.e. new prop

    flags = get_flags()

    prop_set = {}
    for prop in flags.prop_set_list:
        if '=' not in prop:
            raise Exception('Invalid format for KEY=VAL property: "%s"' % prop)
        else:
            k, v = prop.split('=', 1)
            prop_set[k] = v

    prop_append = {}
    for prop in flags.append:
        if '=' not in prop:
            raise Exception('Invalid format for KEY=VAL property: "%s"' % prop)
        else:
            k, v = prop.split('=', 1)
            prop_append[k] = v

    # Test that there are no collisions between prop_set and prop_append.
    # We allow --delete to intersect to allow creating comments out of props.
    collision = set(prop_set.keys()).intersection(prop_append.keys())
    if len(collision) > 0:
        raise Exception('Duplicated keys in append and set lists: %r' % list(collision))

    bpm = BuildPropMod(bp_file=flags.file,
                       delete_list=flags.delete,
                       prop_append=prop_append,
                       prop_set=prop_set)
    bpm.run()
