# Common exceptions for the flash scripts

class BuildsNotFoundException(Exception):
    pass

class NoBuildsFoundException(BuildsNotFoundException):
    pass

class ManyBuildsFoundException(BuildsNotFoundException):
    pass
