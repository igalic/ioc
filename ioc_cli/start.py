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
"""Start jails from the CLI.."""
import typing
import click

import libioc.errors
import libioc.Jails
import libioc.Logger

from .shared.click import IocClickContext
from .shared.jail import set_properties

__rootcmd__ = True


@click.command(name="start", help="Starts the specified jails or ALL.")
@click.pass_context
@click.option(
    "--rc",
    default=False,
    is_flag=True,
    help=(
        "Will start all jails with boot=on, in the specified "
        "order with smaller value for priority starting first."
    )
)
@click.option(
    "--option", "-o",
    "temporary_config_override",
    multiple=True,
    help="Temporarily override jail config options"
)
@click.argument("jails", nargs=-1)
def cli(
    ctx: IocClickContext,
    rc: bool,
    temporary_config_override: typing.Tuple[str, ...],
    jails: typing.Tuple[str, ...]
) -> None:
    """Start one or many jails."""
    logger = ctx.parent.logger
    start_args = {
        "zfs": ctx.parent.zfs,
        "host": ctx.parent.host,
        "logger": logger,
        "print_function": ctx.parent.print_events
    }

    if (rc is False) and (len(jails) == 0):
        logger.error("No jail selector provided")
        exit(1)

    elif rc is True:
        if len(jails) > 0:
            logger.error("Cannot use --rc and jail selectors simultaniously")
            exit(1)
        _autostart(**start_args)
    else:
        start_normal_successful = _normal(
            jails,
            temporary_config_override=temporary_config_override,
            **start_args
        )
        if start_normal_successful is False:
            exit(1)


def _autostart(
    zfs: libioc.ZFS.ZFS,
    host: libioc.Host.HostGenerator,
    logger: libioc.Logger.Logger,
    print_function: typing.Callable[
        [typing.Generator[libioc.events.IocEvent, None, None]],
        None
    ]
) -> None:

    filters = ("boot=yes", "running=no", "template=no,-",)

    ioc_jails = libioc.Jails.Jails(
        zfs=zfs,
        host=host,
        logger=logger,
        filters=filters
    )

    # sort jails by their priority
    jails = sorted(
        list(ioc_jails),
        key=lambda x: x.config["priority"]
    )

    failed_jails = []
    for jail in jails:
        try:
            if jail.running is True:
                logger.log(f"{jail.name} is already running - skipping start")
                continue
            jail.start()
        except libioc.errors.IocException:
            failed_jails.append(jail)
            continue

        logger.log(f"{jail.humanreadable_name} running as JID {jail.jid}")

    if len(failed_jails) > 0:
        exit(1)

    exit(0)


def _normal(
    filters: typing.Tuple[str, ...],
    temporary_config_override: typing.Tuple[str, ...],
    zfs: libioc.ZFS.ZFS,
    host: libioc.Host.HostGenerator,
    logger: libioc.Logger.Logger,
    print_function: typing.Callable[
        [typing.Generator[libioc.events.IocEvent, None, None]],
        None
    ]
) -> bool:

    filters += ("template=no,-",)

    jails = libioc.Jails.JailsGenerator(
        logger=logger,
        zfs=zfs,
        host=host,
        filters=filters
    )

    changed_jails = []
    skipped_jails = []
    failed_jails = []
    for jail in jails:
        try:
            set_properties(
                properties=temporary_config_override,
                target=jail,
                autosave=False
            )
        except libioc.errors.IocException:
            exit(1)
        try:
            jail.require_jail_not_template()
            if jail.running is True:
                logger.log(f"{jail.name} is already running - skipping start")
                skipped_jails.append(jail)
                continue
            print_function(jail.start())
        except libioc.errors.IocException:
            failed_jails.append(jail)
            continue

        logger.log(f"{jail.humanreadable_name} running as JID {jail.jid}")
        changed_jails.append(jail)

    if len(failed_jails) > 0:
        return False

    if (len(changed_jails) == 0) and (len(skipped_jails) == 0):
        jails_input = " ".join(list(filters))
        logger.error(f"No jails started your input: {jails_input}")
        return False

    return True
