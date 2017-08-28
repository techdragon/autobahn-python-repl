################################################################################
# MIT License
#
# Copyright (c) 2017 OpenDNA Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
################################################################################
import asyncio
from copy import deepcopy

import txaio
from autobahn.wamp import CallOptions
from typing import Callable, Union, Any, Dict, Iterable

from opendna.autobahn.repl.abc import (
    AbstractCallInvocation,
    AbstractCall,
    AbstractCallManager,
    AbstractSession)
from opendna.autobahn.repl.utils import generate_name

__author__ = 'Adam Jorgensen <adam.jorgensen.za@gmail.com>'


class Keep(object):
    pass
Keep = Keep()


class CallInvocation(AbstractCallInvocation):

    def __init__(self,
                 call: AbstractCall,
                 args: Iterable,
                 kwargs: Dict[str, Any]):
        assert isinstance(call, AbstractCall)
        loop = call.call_manager.session.session_manager.loop
        self.__call = call
        self.__args = args
        self.__kwargs = kwargs
        self.__progress = []
        self.__result = None
        self.__exception = None

        def invoke(future: asyncio.Future):
            print('Here')
            try:
                result = future.result()
                print(result)
                self.__future = asyncio.ensure_future(self.__invoke(), loop=loop)
                # TODO: This is failing because when __invoke tries to access
                # TODO: call.call_manager.session.application_session it is still none
                print(self.__future)
            except Exception as e:
                # TODO: Print message about failure
                print(e)
                pass
        call.call_manager.session.future.add_done_callback(invoke)

    @property
    def result(self):
        return self.__result

    @property
    def progress(self):
        return self.__progress

    @property
    def exception(self):
        return self.__exception

    def __default_on_progress(self, value):
        self.__progress.append(value)

    async def __invoke(self):
        try:
            options = CallOptions(
                on_progress=(
                    self.__call.on_progress if callable(self.__call.on_progress)
                    else self.__default_on_progress
                ),
                timeout=self.__call.timeout
            )
            session = self.__call.call_manager.session.application_session
            self.__result = await session.call(
                self.__call.procedure,
                *self.__args,
                options=options,
                **self.__kwargs
            )
        except Exception as e:
            self.__exception = e

    def __call__(self, *new_args, **new_kwargs) -> AbstractCallInvocation:
        """

        :param new_args:
        :param new_kwargs:
        :return:
        """
        args = deepcopy(self.__args)
        args = [
            arg if new_arg == Keep else new_arg
            for arg, new_arg in zip(args, new_args)
        ]
        kwargs = deepcopy(self.__kwargs)
        kwargs.update(new_kwargs)
        return self.__call(*args, **kwargs)


class Call(AbstractCall):
    def __init__(self, manager: AbstractCallManager,
                 procedure: str, on_progress: Callable=None,
                 timeout: Union[int, float, None]=None):
        assert isinstance(manager, AbstractCallManager)
        self.__manager = manager
        self.__procedure = procedure
        self.__on_progress = on_progress
        self.__timeout = timeout
        self.__invocation_name__invocations = {}
        self.__invocations = {}

    @property
    def call_manager(self) -> AbstractCallManager:
        return self.__manager

    @property
    def procedure(self) -> str:
        return self.__procedure

    @property
    def on_progress(self) -> Callable:
        return self.__on_progress

    @property
    def timeout(self) -> Union[int, float, None]:
        return self.__timeout

    def __call__(self, *args, **kwargs) -> AbstractCallInvocation:
        name = generate_name()
        while name in self.__invocations:
            name = generate_name()
        # TODO: Allow custom CallInvocation class
        invocation = CallInvocation(call=self, args=args, kwargs=kwargs)
        invocation_id = id(invocation)
        self.__invocations[invocation_id] = invocation
        self.__invocation_name__invocations[name] = invocation_id
        return invocation

    def __getitem__(self, item):
        item = self.__invocation_name__invocations.get(item, item)
        return self.__invocations[item]

    def __getattr__(self, item):
        return self[item]


class CallManager(AbstractCallManager):
    logger = txaio.make_logger()

    def __init__(self, session: AbstractSession):
        assert isinstance(session, AbstractSession)
        self.__session = session
        self.__call_name__calls = {}
        self.__calls = {}

    @property
    def session(self) -> AbstractSession:
        return self.__session

    def __call__(self,
                 procedure: str,
                 name: str=None,
                 on_progress: Callable=None,
                 timeout: Union[int, float]=None) -> AbstractCall:
        """
        Generates a Callable which can be called to initiate an asynchronous
        request to the WAMP router this Session is connected to

        :param procedure:
        :param name:
        :param on_progress:
        :param timeout:
        :return:
        """
        while name is None or name in self.__call_name__calls:
            name = generate_name(name)
        self.logger.info(
            'Generating call to {procedure} with name {name}',
            procedure=procedure, name=name
        )
        # TODO: Allow custom Call class
        call = Call(
            manager=self, procedure=procedure, on_progress=on_progress,
            timeout=timeout
        )
        call_id = id(call)
        self.__calls[call_id] = call
        self.__call_name__calls[name] = call_id
        return call

    def __getitem__(self, item: str):
        item = self.__call_name__calls.get(item, item)
        return self.__calls[item]

    def __getattr__(self, item: str):
        return self[item]