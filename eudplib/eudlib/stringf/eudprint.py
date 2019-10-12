#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2014 trgk, 2019 Armoha

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
"""

from eudplib import core as c
from eudplib import ctrlstru as cs
from eudplib import utils as ut

from ..rwcommon import br1, bw1
from .dbstr import DBString

_conststr_dict = dict()
_str_jump, _str_EOS, _str_dst = c.Forward(), c.Forward(), c.Forward()
_dw_jump, _dw_EOS, _dw_dst = c.Forward(), c.Forward(), c.Forward()
_ptr_jump, _ptr_EOS, _ptr_dst = c.Forward(), c.Forward(), c.Forward()


def _dbstr_addstr_core(_f=[]):
    if not _str_jump.IsSet():

        def _():
            global _str_jump, _str_EOS, _str_dst
            c.PushTriggerScope()
            strlen = c.EUDVariable()
            init = c.RawTrigger(actions=strlen.SetNumber(0))
            write = c.Forward()

            if cs.EUDInfLoop()():
                b = br1.readbyte()
                _str_jump << c.RawTrigger(
                    conditions=b.Exactly(0), actions=c.SetNextPtr(_str_jump, _str_EOS)
                )
                write << c.NextTrigger()
                bw1.writebyte(b)
                strlen += 1
            cs.EUDEndInfLoop()

            _str_EOS << c.NextTrigger()
            bw1.writebyte(0)  # EOS
            _str_dst << c.RawTrigger(actions=c.SetNextPtr(_str_jump, write))
            c.PopTriggerScope()

            return init, _str_dst, strlen

        _f.extend(_())

    init, end, strlen = _f
    nptr = c.Forward()
    c.RawTrigger(nextptr=init, actions=c.SetNextPtr(end, nptr))
    nptr << c.NextTrigger()

    return strlen


@c.EUDFunc
def f_dbstr_addstr(dst, src):
    """Print string as string to dst. Same as strcpy except of return value.

    :param dst: Destination address (Not EPD player)
    :param src: Source address (Not EPD player)

    :returns: dst + strlen(src)
    """
    bw1.seekoffset(dst)
    br1.seekoffset(src)
    strlen = _dbstr_addstr_core()
    dst += strlen

    return dst


@c.EUDFunc
def f_dbstr_addstr_epd(dst, epd):
    """Print string as string to dst. Same as strcpy except of return value.

    :param dst: Destination address (Not EPD player)
    :param epd: Source EPD player

    :returns: dst + strlen_epd(epd)
    """
    bw1.seekoffset(dst)
    br1.seekepd(epd)
    strlen = _dbstr_addstr_core()
    dst += strlen

    return dst


@c.EUDFunc
def f_dbstr_adddw(dst, number):
    """Print number as string to dst.

    :param dst: Destination address (Not EPD player)
    :param number: DWORD to print

    :returns: dst + strlen(itoa(number))
    """
    global _dw_jump, _dw_EOS, _dw_dst
    bw1.seekoffset(dst)

    skipper = [c.Forward() for _ in range(9)]
    ch = [0] * 10

    # Get digits
    for i in range(10):
        number, ch[i] = c.f_div(number, 10)
        ch[i] += b"0"[0]
        if i != 9:
            cs.EUDJumpIf(number == 0, skipper[i])

    # print digits
    for i in range(9, -1, -1):
        if i != 9:
            skipper[i] << c.NextTrigger()
        bw1.writebyte(ch[i])
        if i == 0:
            _dw_jump << c.NextTrigger()
        dst += 1

    _dw_EOS << c.NextTrigger()
    bw1.writebyte(0)  # EOS
    _dw_dst << c.NextTrigger()

    return dst


@c.EUDFunc
def f_dbstr_addptr(dst, number):
    """Print number as string to dst.

    :param dst: Destination address (Not EPD player)
    :param number: DWORD to print

    :returns: dst + strlen(itoa(number))
    """
    global _ptr_jump, _ptr_EOS, _ptr_dst
    bw1.seekoffset(dst)
    ch = [0] * 8

    # Get digits
    for i in range(8):
        number, ch[i] = c.f_div(number, 16)

    # print digits
    for i in range(7, -1, -1):
        if cs.EUDIf()(ch[i] <= 9):
            bw1.writebyte(ch[i] + b"0"[0])
        if cs.EUDElse()():
            bw1.writebyte(ch[i] + (b"A"[0] - 10))
        cs.EUDEndIf()
        if i == 0:
            _ptr_jump << c.NextTrigger()
        dst += 1

    _ptr_EOS << c.NextTrigger()
    bw1.writebyte(0)  # EOS
    _ptr_dst << c.NextTrigger()

    return dst


def _OmitEOS(*args):
    dw = any(c.IsConstExpr(x) or c.IsEUDVariable(x) for x in args)
    ptr = any(ut.isUnproxyInstance(x, hptr) for x in args)
    cs.DoActions(
        [c.SetMemory(_str_jump + 348, c.SetTo, _str_dst)]
        + [c.SetNextPtr(_dw_jump, _dw_dst) if dw else []]
        + [c.SetNextPtr(_ptr_jump, _ptr_dst) if ptr else []]
    )
    yield (dw, ptr)
    if dw or ptr:
        cs.DoActions(
            [c.SetNextPtr(_dw_jump, _dw_EOS) if dw else []]
            + [c.SetNextPtr(_ptr_jump, _ptr_EOS) if ptr else []]
        )


class ptr2s:
    def __init__(self, value):
        self._value = value


class epd2s:
    def __init__(self, value):
        self._value = value


class hptr:
    def __init__(self, value):
        self._value = value


def f_dbstr_print(dst, *args, encoding="UTF-8"):
    """Print multiple string / number to dst.

    :param dst: Destination address (Not EPD player)
    :param args: Things to print

    """
    if ut.isUnproxyInstance(dst, DBString):
        dst = dst.GetStringMemoryAddr()

    args = ut.FlattenList(args)
    for arg in args:
        if ut.isUnproxyInstance(arg, str):
            arg = arg.encode(encoding)
        elif ut.isUnproxyInstance(arg, int):
            # int and c.EUDVariable should act the same if possible.
            # EUDVariable has a value of 32bit unsigned integer.
            # So we adjust arg to be in the same range.
            arg = ut.u2b(str(arg & 0xFFFFFFFF))
        if ut.isUnproxyInstance(arg, bytes):
            if arg not in _conststr_dict:
                _conststr_dict[arg] = c.Db(arg + b"\0")
            arg = _conststr_dict[arg]
        if ut.isUnproxyInstance(arg, c.Db):
            dst = f_dbstr_addstr_epd(dst, ut.EPD(arg))
        elif ut.isUnproxyInstance(arg, DBString):
            dst = f_dbstr_addstr_epd(dst, ut.EPD(arg.GetStringMemoryAddr()))
        elif ut.isUnproxyInstance(arg, epd2s):
            dst = f_dbstr_addstr_epd(dst, arg._value)
        elif ut.isUnproxyInstance(arg, ptr2s):
            dst = f_dbstr_addstr(dst, arg._value)
        elif ut.isUnproxyInstance(arg, c.EUDVariable):
            dst = f_dbstr_adddw(dst, arg)
        elif c.IsConstExpr(arg):
            dst = f_dbstr_adddw(dst, arg)
        elif ut.isUnproxyInstance(arg, hptr):
            dst = f_dbstr_addptr(dst, arg._value)
        else:
            raise ut.EPError(
                "Object with unknown parameter type %s given to f_eudprint." % type(arg)
            )

    return dst
