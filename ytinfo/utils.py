def dict_tryget(d, *keyseq, default=None):
    for k in keyseq:
        if k in d:
            d = d[k]
        else:
            return default
    return d
