class ColorCli(object):
    """
    Provides color printing.
    """

    @classmethod
    def print_green(cls, line):
        print ''
        print '\033[32m  ' + line + '\033[0m'
        print ''

    @classmethod
    def print_red(cls, line):
        print ''
        print '\033[31m  ' + line + '\033[0m'
        print ''
