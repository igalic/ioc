# Copyright (c) 2017-2019, Stefan Grönke
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
"""Set configuration values from the CLI."""
import typing
import click

import libioc.errors
import libioc.Logger
import libioc.helpers
import libioc.Resource
import libioc.Jails

from .shared.jail import set_properties

__rootcmd__ = True


@click.command(
    context_settings=dict(max_content_width=400,),
    name="set",
    help="Sets the specified property."
)
@click.pass_context
@click.argument("props", nargs=-1)
@click.argument("jail", nargs=1, required=True)
def cli(
    ctx: click.core.Context,
    props: typing.Tuple[str, ...],
    jail: str
) -> None:
    """Set one or many configuration properties of one jail."""
    parent: typing.Any = ctx.parent
    logger: libioc.Logger.Logger = parent.logger
    host: libioc.Host.HostGenerator = parent.host

    # Defaults
    if jail == "defaults":
        try:
            updated_properties = set_properties(
                properties=props,
                target=host.defaults
            )
        except libioc.errors.IocException:
            exit(1)

        if len(updated_properties) > 0:
            logger.screen("Defaults updated: " + ", ".join(updated_properties))
        else:
            logger.screen("Defaults unchanged")
        return

    # Jail Properties
    filters = (f"name={jail}",)
    ioc_jails = libioc.Jails.JailsGenerator(
        filters,
        host=host,
        logger=logger
    )

    updated_jail_count = 0

    for ioc_jail in ioc_jails:  # type: libioc.Jail.JailGenerator

        try:
            updated_properties = set_properties(
                properties=props,
                target=ioc_jail
            )
        except libioc.errors.IocException:
            exit(1)

        if len(updated_properties) == 0:
            logger.screen(f"Jail '{ioc_jail.humanreadable_name}' unchanged")
        else:
            _properties = ", ".join(updated_properties)
            logger.screen(
                f"Jail '{ioc_jail.humanreadable_name}' updated: {_properties}"
            )

        updated_jail_count += 1

    if updated_jail_count == 0:
        logger.error("No jails to update")
        exit(1)

    exit(0)
