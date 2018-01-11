#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
Copyright (c) 2014 trgk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
'''

import functools

from ... import utils as ut

from .. import allocator as ac
from .. import rawtrigger as bt
from .. import variable as ev

from ...utils.blockstru import (
    BlockStruManager,
    SetCurrentBlockStruManager
)


_currentCompiledFunc = None
_currentTriggerCount = 0


def _updateFuncTriggerCount():
    global _currentTriggerCount
    currentCounter = bt.GetTriggerCounter()
    addedTriggerCount = currentCounter - _currentTriggerCount

    if _currentCompiledFunc:
        _currentCompiledFunc._triggerCount += addedTriggerCount
    _currentTriggerCount = currentCounter


def _setCurrentCompiledFunc(func):
    global _currentCompiledFunc

    lastCompiledFunc = _currentCompiledFunc
    _updateFuncTriggerCount()
    _currentCompiledFunc = func
    return lastCompiledFunc


class EUDFuncN:
    def __init__(self, argn, callerfunc, bodyfunc):
        """ EUDFuncN

        :param callerfunc: Function to be wrapped.
        :param argn: Count of arguments got by callerfunc
        :param bodyfunc: Where function should return to
        """

        if bodyfunc is None:
            bodyfunc = callerfunc

        self._argn = argn
        self._retn = None
        self._callerfunc = callerfunc
        self._bodyfunc = bodyfunc
        functools.update_wrapper(self, bodyfunc)
        self._fstart = None
        self._fend = None
        self._fargs = None
        self._frets = None
        self._triggerCount = None

    def size(self):
        if not self._fstart:
            self._CreateFuncBody()

        return self._triggerCount

    def _CreateFuncBody(self):
        self._triggerCount = 0
        lastCompiledFunc = _setCurrentCompiledFunc(self)

        # Add return point
        self._fend = ac.Forward()

        # Prevent double compilication
        ut.ep_assert(self._fstart is None)

        # Initalize new namespace
        f_bsm = BlockStruManager()
        prev_bsm = SetCurrentBlockStruManager(f_bsm)
        bt.PushTriggerScope()

        f_args = [ev.EUDVariable() for _ in range(self._argn)]
        self._fargs = f_args

        fstart = bt.NextTrigger()
        self._fstart = fstart

        final_rets = self._callerfunc(*f_args)
        if final_rets is not None:
            self._AddReturn(ut.Assignable2List(final_rets), False)
        fend = bt.RawTrigger()
        bt.PopTriggerScope()

        # Finalize
        ut.ep_assert(f_bsm.empty(), 'Block start/end mismatch inside function')
        SetCurrentBlockStruManager(prev_bsm)

        self._fend << fend
        # No return -> set return count to 0
        if self._retn is None:
            self._retn = 0
        _setCurrentCompiledFunc(lastCompiledFunc)

    def _AddReturn(self, retv, needjump):
        retv = ut.FlattenList(retv)
        if self._frets is None:
            self._frets = [ev.EUDVariable() for _ in range(len(retv))]
            self._retn = len(retv)

        ut.ep_assert(
            len(retv) == len(self._frets),
            "Numbers of returned value should be constant."
            " (From function %s)" % self._callerfunc.__name__
        )

        ev.SetVariables(self._frets, retv)

        if needjump:
            bt.RawTrigger(nextptr=self._fend)

    def __call__(self, *args):
        if self._fstart is None:
            self._CreateFuncBody()

        ut.ep_assert(
            len(args) == self._argn,
            'Argument number mismatch : ' +
            'len(%s) != %d' % (repr(args), self._argn)
        )

        # Assign arguments into argument space
        ev.SeqCompute(
            [(farg, bt.SetTo, arg) for farg, arg in zip(self._fargs, args)]
        )

        # Call body
        fcallend = ac.Forward()

        bt.RawTrigger(
            nextptr=self._fstart,
            actions=[bt.SetNextPtr(self._fend, fcallend)]
        )

        fcallend << bt.NextTrigger()

        if self._frets is not None:
            retn = len(self._frets)
            tmp_rets = [ev.EUDVariable() for _ in range(retn)]
            ev.SetVariables(tmp_rets, self._frets)
            for tv in tmp_rets:
                tv.makeR()
            return ut.List2Assignable(tmp_rets)


def EUDReturn(*args):
    _currentCompiledFunc._AddReturn(args, True)