import sys

def getArgs(filter_kwargs=[]):
    args = sys.argv

    filename = args.pop(0)

    kwargs = {}
    kwarg_key = None

    for arg in args:
        if arg.startswith('-'):
            if len(filter_kwargs) == 0 or arg[1:] in filter_kwargs:
                kwarg_key = arg[1:].lower()
        else:
            if kwarg_key is not None:
                kwargs[kwarg_key] = arg
            kwarg_key = None

    return filename, kwargs

if __name__ == '__main__':
    filename, kwargs = getArgs()
    print(kwargs)