import pytest
import capnp
import os

import test_capability_capnp as capability

class Server(capability.TestInterface.Server):
    def __init__(self, val=1):
        self.val = val

    def foo(self, i, j, **kwargs):
        extra = 0
        if j:
            extra = 1
        return str(i * 5 + extra + self.val)

    def buz(self, i, **kwargs):
        return i.host + '_test'

    def bam(self, i, **kwargs):
        return str(i) + '_test', i

class PipelineServer(capability.TestPipeline.Server):
    def getCap(self, n, inCap, _context, **kwargs):
        def _then(response):
            _results = _context.results
            _results.s = response.x + '_foo'
            _results.outBox.cap = Server(100)

        return inCap.foo(i=n).then(_then)

def test_client():
    client = capability.TestInterface._new_client(Server())
    
    req = client._request('foo')
    req.i = 5

    remote = req.send()
    response = remote.wait()

    assert response.x == '26'
    
    req = client.foo_request()
    req.i = 5

    remote = req.send()
    response = remote.wait()

    assert response.x == '26'

    with pytest.raises(ValueError):
        client.foo2_request()

    req = client.foo_request()

    with pytest.raises(ValueError):
        req.i = 'foo'

    req = client.foo_request()

    with pytest.raises(AttributeError):
        req.baz = 1

def test_simple_client():
    client = capability.TestInterface._new_client(Server())
    
    remote = client._send('foo', i=5)
    response = remote.wait()

    assert response.x == '26'

    
    remote = client.foo(i=5)
    response = remote.wait()

    assert response.x == '26'
    
    remote = client.foo(i=5, j=True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.foo(5)
    response = remote.wait()

    assert response.x == '26'

    remote = client.foo(5, True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.foo(5, j=True)
    response = remote.wait()

    assert response.x == '27'

    remote = client.buz(capability.TestSturdyRefHostId.new_message(host='localhost'))
    response = remote.wait()

    assert response.x == 'localhost_test'

    remote = client.bam(i=5)
    response = remote.wait()

    assert response.x == '5_test'
    assert response.i == 5

    with pytest.raises(ValueError):
        remote = client.foo(5, 10)

    with pytest.raises(ValueError):
        remote = client.foo(5, True, 100)

    with pytest.raises(ValueError):
        remote = client.foo(i='foo')

    with pytest.raises(ValueError):
        remote = client.foo2(i=5)

    with pytest.raises(AttributeError):
        remote = client.foo(baz=5)

def test_pipeline():
    client = capability.TestPipeline._new_client(PipelineServer())
    foo_client = capability.TestInterface._new_client(Server())

    remote = client.getCap(n=5, inCap=foo_client)

    outCap = remote.outBox.cap
    pipelinePromise = outCap.foo(i=10)

    response = pipelinePromise.wait()
    assert response.x == '150'

    response = remote.wait()
    assert response.s == '26_foo'

class BadServer(capability.TestInterface.Server):
    def __init__(self, val=1):
        self.val = val

    def foo(self, i, j, **kwargs):
        extra = 0
        if j:
            extra = 1
        return str(i * 5 + extra + self.val), 10 # returning too many args

def test_exception_client():
    client = capability.TestInterface._new_client(BadServer())
    
    remote = client._send('foo', i=5)
    with pytest.raises(capnp.KjException):
        remote.wait()

class BadPipelineServer(capability.TestPipeline.Server):
    def getCap(self, n, inCap, _context, **kwargs):
        def _then(response):
            _results = _context.results
            _results.s = response.x + '_foo'
            _results.outBox.cap = Server(100)
        def _error(error):
            raise Exception('test was a success')

        return inCap.foo(i=n).then(_then, _error)

def test_exception_chain():
    client = capability.TestPipeline._new_client(BadPipelineServer())
    foo_client = capability.TestInterface._new_client(BadServer())

    remote = client.getCap(n=5, inCap=foo_client)

    try:
        remote.wait()
    except Exception as e:
        assert 'test was a success' in str(e)

def test_pipeline_exception():
    client = capability.TestPipeline._new_client(BadPipelineServer())
    foo_client = capability.TestInterface._new_client(BadServer())

    remote = client.getCap(n=5, inCap=foo_client)

    outCap = remote.outBox.cap
    pipelinePromise = outCap.foo(i=10)

    with pytest.raises(Exception):
        loop.wait(pipelinePromise)

    with pytest.raises(Exception):
        remote.wait()

def test_casting():
    client = capability.TestExtends._new_client(Server())
    client2 = client.upcast(capability.TestInterface)
    client3 = client2.cast_as(capability.TestInterface)

    with pytest.raises(Exception):
        client.upcast(capability.TestPipeline)

class TailCallOrder(capability.TestCallOrder.Server):
    def __init__(self):
        self.count = -1

    def getCallSequence(self, expected, **kwargs):
        self.count += 1
        return self.count

class TailCaller(capability.TestTailCaller.Server):
    def __init__(self):
        self.count = 0

    def foo(self, i, callee, _context, **kwargs):
        self.count += 1

        tail = callee.foo_request(i=i, t='from TailCaller')
        return _context.tail_call(tail)

class TailCallee(capability.TestTailCallee.Server):
    def __init__(self):
        self.count = 0

    def foo(self, i, t, _context, **kwargs):
        self.count += 1

        results = _context.results
        results.i = i
        results.t = t
        results.c = TailCallOrder()

def test_tail_call():
    callee_server = TailCallee()
    caller_server = TailCaller()

    callee = capability.TestTailCallee._new_client(callee_server)
    caller = capability.TestTailCaller._new_client(caller_server)

    promise = caller.foo(i=456, callee=callee)
    dependent_call1 = promise.c.getCallSequence()

    response = promise.wait()

    assert response.i == 456
    assert response.i == 456

    dependent_call2 = response.c.getCallSequence()
    dependent_call3 = response.c.getCallSequence()

    result = dependent_call1.wait()
    assert result.n == 0
    result = dependent_call2.wait()
    assert result.n == 1
    result = dependent_call3.wait()
    assert result.n == 2

    assert callee_server.count == 1
    assert caller_server.count == 1