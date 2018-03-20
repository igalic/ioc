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
"""iocage libzfs enhancement module."""
import typing
import libzfs
import datetime

import iocage.lib.Logger
import iocage.lib.helpers
import iocage.lib.errors

Logger = iocage.lib.Logger.Logger


class ZFS(libzfs.ZFS):
    """libzfs enhancement module."""

    _logger: typing.Optional['iocage.lib.Logger.Logger']

    @property
    def logger(self) -> 'iocage.lib.Logger.Logger':
        """Return logger or raise an exception when it is unavailable."""
        if not (self._has_logger or isinstance(self._logger, Logger)):
            raise Exception("The logger is unavailable")
        return self._logger

    @logger.setter
    def logger(self, logger: 'iocage.lib.Logger.Logger') -> None:
        """Set the ZFS objects logger."""
        self._logger = logger

    def create_dataset(
        self,
        dataset_name: str,
        **kwargs
    ) -> libzfs.ZFSDataset:
        """Automatically get the pool and create a dataset from its name."""
        pool = self.get_pool(dataset_name)
        pool.create(dataset_name, kwargs, create_ancestors=True)

        dataset = self.get_dataset(dataset_name)
        dataset.mount()
        return dataset

    def get_or_create_dataset(
        self,
        dataset_name: str,
        **kwargs
    ) -> libzfs.ZFSDataset:
        """Find or create the dataset, then return it."""
        try:
            return self.get_dataset(dataset_name)
        except libzfs.ZFSException:
            pass

        return self.create_dataset(dataset_name, **kwargs)

    def get_pool(self, name: str) -> libzfs.ZFSPool:
        """Get the pool with a given name."""
        pool_name = name.split("/")[0]
        for pool in self.pools:
            if pool.name == pool_name:
                return pool
        raise iocage.lib.errors.ZFSPoolUnavailable(
            pool_name=pool_name,
            logger=self.logger
        )

    def delete_dataset_recursive(
        self,
        dataset: libzfs.ZFSDataset,
        delete_snapshots: bool=True,
        delete_origin_snapshot: bool=True
    ) -> None:
        """Recursively delete a dataset."""
        for child in dataset.children:
            self.delete_dataset_recursive(child)

        if dataset.mountpoint is not None:
            if self._has_logger:
                self.logger.spam(f"Unmounting {dataset.name}")
            dataset.umount()

        if delete_snapshots is True:
            for snapshot in dataset.snapshots:
                if self._has_logger:
                    self.logger.verbose(
                        f"Deleting snapshot {snapshot.name}"
                    )
                snapshot.delete()

        origin = None
        if delete_origin_snapshot is True:
            origin_property = dataset.properties["origin"]
            if origin_property.value != "":
                origin = origin_property

        if self._has_logger:
            self.logger.verbose(f"Deleting dataset {dataset.name}")
        dataset.delete()

        if origin is not None:
            if self._has_logger:
                self.logger.verbose(f"Deleting snapshot {origin}")
            origin_snapshot = self.get_snapshot(origin.value)
            origin_snapshot.delete()

    def clone_dataset(
        self,
        source: libzfs.ZFSDataset,
        target: str,
        snapshot_name: str,
        delete_existing: bool=False
    ) -> None:
        """Clone a ZFSDataset from a source to a target dataset name."""
        _snapshot_name = f"{source.name}@{snapshot_name}"

        # delete target dataset if it already exists
        try:
            existing_dataset = self.get_dataset(target)
        except libzfs.ZFSException:
            pass
        else:
            if delete_existing is False:
                raise iocage.lib.errors.DatasetExists(
                    dataset_name=target
                )
            self.logger.verbose(
                f"Deleting existing dataset {target}"
            )
            if existing_dataset.mountpoint is not None:
                existing_dataset.umount()
            existing_dataset.delete()
            del existing_dataset

        # delete existing snapshot if existing
        existing_snapshots = list(filter(
            lambda x: x.name.endswith(f"@{snapshot_name}"),
            source.snapshots_recursive
        ))

        if len(existing_snapshots) > 0:
            self.logger.verbose(
                f"Deleting existing snapshot {_snapshot_name}"
            )
            for dataset in [source] + source.children_recursive:
                snapshot = self.get_snapshot(f"{dataset.name}@{snapshot_name}")
                snapshot.delete()

        # snapshot release
        source.snapshot(_snapshot_name, recursive=True)
        snapshot = self.get_snapshot(_snapshot_name)

        # clone snapshot
        if self._has_logger:
            self.logger.verbose(
                f"Cloning snapshot {_snapshot_name} to {target}"
            )

        self._clone_and_mount(snapshot, target)

        for dataset in source.children_recursive:
            source_len = len(source.name)
            unprefixed_dataset_name = dataset.name[source_len:].strip("/")
            current_snapshot = self.get_snapshot(
                f"{dataset.name}@{snapshot_name}"
            )
            current_target = f"{target}/{unprefixed_dataset_name}"
            self._clone_and_mount(current_snapshot, current_target)

        if self._has_logger:
            self.logger.verbose(
                f"Successfully cloned {source} to {target}"
            )

    def promote_dataset(
        self,
        dataset: libzfs.ZFSDataset,
        logger: typing.Optional['iocage.lib.Logger.Logger']=None
    ):
        """Recursively promote a dataset."""
        datasets = list(reversed(list(dataset.children_recursive))) + [dataset]
        for child in datasets:
            self._promote(child, logger=logger)

    def _promote(
        self,
        dataset: libzfs.ZFSDataset,
        logger: typing.Optional['iocage.lib.Logger.Logger']=None
    ) -> None:
        if logger is not None:
            logger.verbose(f"Promoting ZFS dataset {dataset.name}")
        dataset.promote()

    def _clone_and_mount(
        self,
        snapshot: libzfs.ZFSSnapshot,
        target: str
    ) -> None:
        parent_name = "/".join(target.split("/")[:-1])
        self.get_or_create_dataset(parent_name)
        snapshot.clone(target)
        dataset = self.get_dataset(target)
        dataset.mount()

    @property
    def _has_logger(self) -> bool:
        return ("_logger" in self.__dir__())


def get_zfs(
    logger: typing.Optional[iocage.lib.Logger.Logger]=None,
    history: bool=True,
    history_prefix: str="<iocage>"
) -> ZFS:
    """Get an instance of iocages enhanced ZFS class."""
    zfs = ZFS(history=history, history_prefix=history_prefix)
    zfs.logger = iocage.lib.helpers.init_logger(zfs, logger)
    return zfs


def append_snapshot_datetime(text: str) -> str:
    """Append the current datetime string to a snapshot name."""
    now = datetime.datetime.utcnow()
    text += now.strftime("%Y%m%d%H%I%S.%f")
    return text
