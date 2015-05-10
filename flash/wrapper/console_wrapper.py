class ConsoleWrapper(object):
    def __init__(self, verbose=False):
        self.verbose = verbose

    def print_verbose(self, message):
        if self.verbose:
            for line in message.splitlines():
                print "\t%s" % line

    def print_verbose_nonewline(self, l):
        # Prints single dot but without newline
        print(l),

    def print_when_not_verbose(self, message):
        if not self.verbose:
            for line in message.splitlines():
                print "\t%s" % line
