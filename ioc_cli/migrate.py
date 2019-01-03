# Copyright (c) 2014-2017, iocage
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
"""Migrate jails to the latest format (python-iocage)."""
import typing
import click

import ioc.events
import ioc.errors
import ioc.helpers
import ioc.Jails
import ioc.Logger

from .shared.click import IocClickContext

__rootcmd__ = True


class JailMigrationEvent(ioc.events.IocageEvent):
    """CLI event that occurs when a jail is migrated from legacy format."""

    def __init__(
        self,
        jail: 'ioc.Jail.JailGenerator'
    ) -> None:
        self.identifier = jail.full_name
        ioc.events.IocageEvent.__init__(self)


@click.command(name="migrate", help="Migrate jails to the latest format.")
@click.pass_context
@click.argument("jails", nargs=-1)
def cli(
    ctx: IocClickContext,
    jails: typing.Tuple[str, ...]
) -> None:
    """Start one or many jails."""
    logger = ctx.parent.logger
    zfs = ioc.ZFS.get_zfs(logger=logger)
    host = ioc.Host.HostGenerator(logger=logger, zfs=zfs)

    filters = jails + ("template=no,-",)

    ioc_jails = ioc.Jails.JailsGenerator(
        filters,
        logger=logger,
        host=host,
        zfs=zfs
    )

    if len(ioc_jails) == 0:
        logger.error(f"No jails started your input: {jails}")
        exit(1)

    ctx.parent.print_events(_migrate_jails(
        ioc_jails,
        logger=logger,
        zfs=zfs,
        host=host
    ))


def _migrate_jails(
    jails: 'ioc.Jails.JailsGenerator',
    logger: 'ioc.Logger.Logger',
    host: 'ioc.Host.HostGenerator',
    zfs: 'ioc.ZFS.ZFS'
) -> typing.Generator['ioc.events.IocageEvent', None, None]:

    for jail in jails:

        event = JailMigrationEvent(jail=jail)
        yield event.begin()

        if jail.config.legacy is False:
            yield event.skip()
            continue

        if jail.running is True:
            yield event.fail(ioc.errors.JailAlreadyRunning(
                jail=jail,
                logger=logger
            ))
            continue

        if ioc.helpers.validate_name(jail.config["tag"]):
            name = jail.config["tag"]
            temporary_name = name
        else:
            name = jail.humanreadable_name
            temporary_name = "import-" + str(hash(name) % (1 << 32))

        try:
            new_jail = ioc.Jail.JailGenerator(
                dict(name=temporary_name),
                root_datasets_name=jail.root_datasets_name,
                new=True,
                logger=logger,
                zfs=zfs,
                host=host
            )
            if new_jail.exists is True:
                raise ioc.errors.JailAlreadyExists(
                    jail=new_jail,
                    logger=logger
                )

            def _destroy_unclean_migration() -> typing.Generator[
                'ioc.events.IocageEvents',
                None,
                None
            ]:
                _name = new_jail.humanreadable_name
                logger.verbose(
                    f"Destroying unfinished migration target jail {_name}"
                )
                yield from new_jail.destroy(
                    force=True,
                    event_scope=event.scope
                )
            event.add_rollback_step(_destroy_unclean_migration)

            yield from new_jail.clone_from_jail(jail, event_scope=event.scope)
            new_jail.save()
            new_jail.promote()
            yield from jail.destroy(
                force=True,
                force_stop=True,
                event_scope=event.scope
            )

        except ioc.errors.IocageException as e:
            yield event.fail(e)
            continue

        if name != temporary_name:
            # the jail takes the old jails name
            yield from new_jail.rename(name, event_scope=event.scope)

        yield event.end()