# fiji/multithread.py
# v.2021.09.20
# m@muniak.com
#
# Functions to multithread FIJI tasks.

# 2024.11.07 - Cleaned up for manuscript deposit.

from ij import IJ
from java.lang import Runtime
from java.util.concurrent import Executors
from java.util.concurrent import Callable

from .utils import logmsg


class Task(Callable):
    """ Callable object for defining threads.
    """
    def __init__(self, fn, *args, **kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
    def call(self):
        return self.fn(*self.args, **self.kwargs)


def init_exe(n_threads=None):
    """ Initialize executor for multithreading tasks.
        If thread limit is not specified, will attempt to use all available processors.
    """
    avail_threads = Runtime.getRuntime().availableProcessors()
    if n_threads is None or n_threads > avail_threads:
        n_threads = avail_threads
    return Executors.newFixedThreadPool(n_threads)


def multi_task(task, args=None, kwargs=None, exe=None, n_threads=None, verbose=True, progress=True):   #### exe_task
    """ Queued multi-threading of repeated task with arguments.
    
        Use keyworded arguments (as a list of dicts) if multiple arguments are to 
        be passed per thread.
    """
    if exe is None:
        exe = init_exe(n_threads)
    try:
        if kwargs:  # Keyworded arguments.
            logmsg('Using KW args')
            if args: logmsg('WARNING: args for <%s> ignored because kwargs supplied ..!' % task.__name__)
            logmsg('Starting %d run(s) of <%s> with up to %d concurrent threads ...' % (len(kwargs), task.__name__, exe.getMaximumPoolSize()))
            futures = [exe.submit(Task(task, **kwarg)) for kwarg in kwargs]
            #results = [f.get() for f in futures]
        elif args:  # Simple arguments.
            logmsg('Starting %d run(s) of <%s> with up to %d concurrent threads ...' % (len(args), task.__name__, exe.getMaximumPoolSize()))
            # If arg is just a string, we don't want it broken down via * notation.
            # There may be a better way to do this, but it works...
            futures = [exe.submit(Task(task, arg)) if isinstance(arg, basestring) else exe.submit(Task(task, *arg)) for arg in args]
            #results = [f.get() for f in futures]
        else:
            logmsg('No arguments provided for running <%s>!' % task.__name__)
            futures = []
        results = []
        for i,f in enumerate(futures):
            results.append(f.get())
            if verbose:
                logmsg('Completed run %d/%d of <%s> ...' % (i+1, len(futures), task.__name__))
            if progress:
                IJ.showProgress(i, len(futures))
    finally:
        logmsg('Completed %d run(s) of <%s>' % (exe.getTaskCount(), task.__name__))
        exe.shutdown()
    return results
