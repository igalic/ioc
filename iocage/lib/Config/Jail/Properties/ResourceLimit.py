# Copyright (c) 2014-2018, iocage
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Jail config resource limit."""
import typing
import iocage.lib.errors

properties: typing.List[str] = [
    "cputime",
    "datasize",
    "stacksize",
    "coredumpsize",
    "memoryuse",
    "memorylocked",
    "maxproc",
    "openfiles",
    "vmemoryuse",
    "pseudoterminals",
    "swapuse",
    "nthr",
    "msgqqueued",
    "msgqsize",
    "nmsgq",
    "nsem",
    "nsemop",
    "nshm",
    "shmsize",
    "wallclock",
    "pcpu",
    "readbps",
    "writebps",
    "readiops",
    "writeiops"
]


class ResourceLimitValue:
    """Model of a resource limits value."""

    amount: typing.Optional[str]
    action: typing.Optional[str]
    per: typing.Optional[str]

    def __init__(self) -> None:
        self.amount = None
        self.action = None
        self.per = None

    def _parse_resource_limit(
        self,
        value: typing.Union[str, int]
    ) -> typing.Tuple[str, str, str]:

        _value = str(value)

        if ("=" not in _value) and (":" not in _value):
            # simplified syntax vmemoryuse=128M
            amount = _value
            action = "deny"
            per = "jail"
        elif "=" in _value:
            # rctl syntax
            action, _rest = _value.split("=", maxsplit=1)
            amount, per = _rest.split("/", maxsplit=1)
        elif ":" in _value:
            # iocage legacy syntax
            amount, action = _value.split(":", maxsplit=1)
            per = "jail"
        else:
            raise ValueError("invalid syntax")

        if (amount == "") or (action == "") or (per == ""):
            raise ValueError("value may not be empty")

        return amount, action, per

    def __str__(self) -> str:
        """
        Return the resource limit value in string format.

        When self.per is "jail" the legacy compatible format is used.
        """
        if self.per == "jail":
            return f"{self.amount}:{self.action}"
        else:
            return self.limit_string

    @property
    def limit_string(self) -> str:
        """Return the limit string in rctl syntax."""
        return f"{self.action}={self.amount}/{self.per}"


_ResourceLimitInputType = typing.Optional[
    typing.Union[int, str, ResourceLimitValue]
]


class ResourceLimitProp(ResourceLimitValue):
    """Special jail config property for resource limits."""

    def __init__(
        self,
        property_name: str,
        config: typing.Optional[
            'iocage.lib.Config.Jail.BaseConfig.BaseConfig'
        ]=None,
        logger: typing.Optional['iocage.lib.Logger.Logger']=None,
        skip_on_error: bool=False
    ) -> None:

        self.logger = logger
        self.config = config
        self.property_name = property_name

        if property_name not in properties:
            raise iocage.lib.errors.ResourceLimitUnknown(logger=self.logger)

        self.__update_from_config()

        ResourceLimitValue.__init__(self)

    def _parse_resource_limit(
        self,
        value: typing.Union[str, int]
    ) -> typing.Tuple[str, str, str]:
        return ResourceLimitValue._parse_resource_limit(self, value=value)

    def __update_from_config(self) -> None:
        name = self.property_name
        if (self.config is None) or (name not in self.config.data.keys()):
            self.set(None)
        else:
            self.set(
                self.config.data[self.property_name]
            )

    def set(self, data: _ResourceLimitInputType) -> None:
        """
        Set the resource limit value.

        Setting it to None will remove it from the configuration.
        """
        if data is None:
            name = self.property_name
            config = self.config
            if (config is not None) and (name in config.data.keys()):
                config.data.__delitem__(name)
            amount = None
            action = None
            per = None
        elif isinstance(data, str) or isinstance(data, int):
            amount, action, per = self._parse_resource_limit(data)
        elif isinstance(data, ResourceLimitValue):
            amount = data.amount
            action = data.action
            per = data.per
        else:
            raise TypeError("invalid ResourceLimit input type")

        self.amount = amount
        self.action = action
        self.per = per

    def __notify(self) -> None:
        if self.config is None:
            return
        self.config.update_special_property(self.property_name)