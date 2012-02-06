import os, copy, imp

def load_config(defaults, filename):
    ''' Shamelessly stolen from flask's excellent Config object '''
    r = copy.copy(defaults)

    if not os.path.exists(filename):
        return r

    d = imp.new_module('config')
    d.__file__ = filename
    try:
        execfile(filename, d.__dict__)
    except IOError, e:
        if silent and e.errno in (errno.ENOENT, errno.EISDIR):
            return False
        e.strerror = 'Unable to load configuration file (%s)' % e.strerror
        raise
    for key in r:
        val = getattr(d, key, None)
        if val != None:
            r[key] = val
    return r
