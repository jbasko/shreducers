class PtNodeExtras(dict):
    """
    A dictionary with attribute-like access.
    Handy while processing parse tree and you
    need to store extra information about tree node
    as you discover it.
    """

    def __missing__(self, key):
        self[key] = None
        return self[key]

    def __getattr__(self, item):
        return self[item]

    def __setattr__(self, key, value):
        self[key] = value


class PtNode(object):
    """
    Represents a node in parse tree.
    """
    def __init__(self, *args, **kwargs):
        self._op = None
        self._a = None
        self._b = None
        self._x = PtNodeExtras()

        if args:
            if len(args) == 1:
                args = args[0]

            for i, k in enumerate(('op', 'a', 'b', 'x')):
                if len(args) > i:
                    setattr(self, '_' + k, args[i])

        for k, v in kwargs.iteritems():
            setattr(self, '_' + k, v)

    @property
    def a(self):
        if isinstance(self._a, tuple):
            self._a = PtNode(self._a)
        return self._a

    @a.setter
    def a(self, value):
        self._a = value

    @property
    def b(self):
        if isinstance(self._b, tuple):
            self._b = PtNode(self._b)
        return self._b

    @b.setter
    def b(self, value):
        self._b = value

    @property
    def op(self):
        return self._op

    @op.setter
    def op(self, value):
        self._op = value

    @property
    def x(self):
        return self._x

    @property
    def operands(self):
        if self.b is None:
            return self.a,
        else:
            return self.a, self.b

    def mark_operands(self, **marks):
        if self.a is not None and isinstance(self.a, PtNode):
            self.a.x.update(marks)
        if self.b is not None and isinstance(self.b, PtNode):
            self.b.x.update(marks)

    def to_tuple(self):
        return (self.op,) + tuple(ab.to_tuple() if isinstance(ab, PtNode) else ab for ab in self.operands)

    def __repr__(self):
        return '<{} op={}, a={}, b={}, x={}>'.format(self.__class__.__name__, self.op, self.a, self.b, self.x)


class PtNodeNotRecognised(Exception):
    """
    The exception that strict processors can choose to throw when encountering
    a node not handled by any process method.
    """
    def __init__(self, node):
        super(PtNodeNotRecognised, self).__init__('{!r}'.format(node))
        self.node = node


class ParseTreeProcessor(object):
    """
    Generic parse tree processor that other processors can extend
    and just implement custom node processors in methods called
    `process_<op>` where `<op>` is name of operator.

    To process primitive nodes implement `process_primitive`.

    To catch all non-primitive nodes, implement `process_unrecognised`.

    Make sure each processor does one thing and does it well.
    If you have a few different things to do before a parse tree can be compiled,
    you may want to use ParseTreeMultiProcessor which is a chain of processors.
    """

    class delegate_of(object):
        """
        Decorator to allow writing one method that does the job of many.
        This is handy when you want to process a number of operators with the
        same code.
        """
        def __init__(self, *method_names):
            self.delegate_of = method_names

        def __call__(self, func):
            func.delegate_of = self.delegate_of
            return func

    def __new__(cls, *args, **kwargs):
        instance = super(ParseTreeProcessor, cls).__new__(cls, *args, **kwargs)
        for k, v in cls.__dict__.iteritems():
            if v and callable(v) and hasattr(v, 'delegate_of'):
                for d in v.delegate_of:
                    # Must assign the bounded method of instance, not that of the class
                    setattr(instance, d, getattr(instance, k))
        return instance

    def __init__(self, strict=False):
        self._strict = strict

    def process(self, node):
        if isinstance(node, tuple):
            node = PtNode(node)
        if isinstance(node, PtNode):
            node.a = self.process(node.a)
            if node.b is not None:
                node.b = self.process(node.b)
            return self.do_process(node)
        else:
            return self.process_primitive(node)

    def do_process(self, node):
        processor_name = 'process_{}'.format(node.op)
        if hasattr(self, processor_name):
            return getattr(self, processor_name)(node)
        else:
            return self.process_unrecognised(node)

    def process_primitive(self, primitive):
        return primitive

    def process_unrecognised(self, node):
        if self._strict:
            raise PtNodeNotRecognised(node=node)
        else:
            return node


class ParseTreeMultiProcessor(ParseTreeProcessor):
    """
    Represents a chain of processors that need to be applied on each node
    one after another.

    This class should not be extended as that would complicate thinking about
    how it works.
    """

    def __init__(self, *processors):
        if self.__class__.__name__ != ParseTreeMultiProcessor.__name__:
            raise RuntimeError('Attempting to extend {}'.format(ParseTreeMultiProcessor.__name__))

        self._all_slots = processors
        self._current_slot_index = None

    @property
    def _current_slot(self):
        """
        Returns a list of processors that can be applied in "parallel" which is
        in the same -- current -- traversal of the tree.
        """
        if len(self._all_slots) <= self._current_slot_index:
            return []
        else:
            current_slot = self._all_slots[self._current_slot_index]
            if isinstance(current_slot, (tuple, list)):
                return current_slot
            else:
                return [current_slot]

    def _process_in_current_slot(self, method_name, node):
        """
        Returns `node` after it has been passed through `method_name` method of all processors in the current slot.
        """
        for p in self._current_slot:
            node = getattr(p, method_name)(node)
        return node

    def process(self, node):
        """
        This method is called only once with the root node.
        """

        if isinstance(node, tuple):
            node = PtNode(node)

        assert isinstance(node, PtNode)

        assert node.x.is_root is None
        node.x.is_root = True
        node.mark_operands(is_root=False)

        self._current_slot_index = 0
        while self._current_slot_index < len(self._all_slots):

            node.a = self._process_in_current_slot(self.process.__name__, node.a)
            if node.b is not None:
                node.b = self._process_in_current_slot(self.process.__name__, node.b)
            node = self._process_in_current_slot(self.do_process.__name__, node)

            self._current_slot_index += 1

        return node

    def do_process(self, node):
        raise RuntimeError('Do not call this')

    def process_primitive(self, primitive):
        raise RuntimeError('Do not call this')

    def process_unrecognised(self, node):
        raise RuntimeError('Do not call this')

