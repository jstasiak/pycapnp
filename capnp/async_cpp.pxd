# schema.capnp.cpp.pyx
# distutils: language = c++
# distutils: extra_compile_args = --std=c++11

from cpython.ref cimport PyObject

cdef extern from "kj/exception.h" namespace " ::kj":
    cdef cppclass Exception:
        pass
        
cdef extern from "kj/async.h" namespace " ::kj":
    cdef cppclass Promise[T]:
        Promise()
        Promise(Promise)
        T wait()

ctypedef Promise[PyObject *] PyPromise
ctypedef Promise[void] VoidPromise
