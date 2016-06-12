
def exception_logged(func, log):
    def wrapped(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except:
            log("Caught Exception!", exc_info=True)
            raise # reraise
    return wrapped
