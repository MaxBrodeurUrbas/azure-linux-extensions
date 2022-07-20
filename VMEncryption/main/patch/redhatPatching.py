#!/usr/bin/python
#
# Copyright 2015 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import os.path
import sys
import base64
import re
import json
import platform
import shutil
import time
import traceback
import datetime
import subprocess
import inspect
import io

from .AbstractPatching import AbstractPatching
from Common import *
from CommandExecutor import *

class redhatPatching(AbstractPatching):
    def __init__(self, logger, distro_info):
        super(redhatPatching, self).__init__(distro_info)
        self.logger = logger
        self.command_executor = CommandExecutor(logger)
        self.distro_info = distro_info
        if distro_info[1].startswith("6."):
            self.base64_path = '/usr/bin/base64'
            self.bash_path = '/bin/bash'
            self.blkid_path = '/sbin/blkid'
            self.cat_path = '/bin/cat'
            self.cryptsetup_path = '/sbin/cryptsetup'
            self.dd_path = '/bin/dd'
            self.e2fsck_path = '/sbin/e2fsck'
            self.echo_path = '/bin/echo'
            self.getenforce_path = '/usr/sbin/getenforce'
            self.setenforce_path = '/usr/sbin/setenforce'
            self.lsblk_path = '/bin/lsblk' 
            self.lsscsi_path = '/usr/bin/lsscsi'
            self.mkdir_path = '/bin/mkdir'
            self.mount_path = '/bin/mount'
            self.openssl_path = '/usr/bin/openssl'
            self.resize2fs_path = '/sbin/resize2fs'
            self.touch_path = '/bin/touch'
            self.umount_path = '/bin/umount'
        else:
            self.base64_path = '/usr/bin/base64'
            self.bash_path = '/usr/bin/bash'
            self.blkid_path = '/usr/bin/blkid'
            self.cat_path = '/bin/cat'
            self.cryptsetup_path = '/usr/sbin/cryptsetup'
            self.dd_path = '/usr/bin/dd'
            self.e2fsck_path = '/sbin/e2fsck'
            self.echo_path = '/usr/bin/echo'
            self.getenforce_path = '/usr/sbin/getenforce'
            self.setenforce_path = '/usr/sbin/setenforce'
            self.lsblk_path = '/usr/bin/lsblk'
            self.lsscsi_path = '/usr/bin/lsscsi'
            self.mkdir_path = '/usr/bin/mkdir'
            self.mount_path = '/usr/bin/mount'
            self.openssl_path = '/usr/bin/openssl'
            self.resize2fs_path = '/sbin/resize2fs'
            self.touch_path = '/usr/bin/touch'
            self.umount_path = '/usr/bin/umount'
        self.min_version_online_encryption = '8.1'
        if type(self).__name__.startswith('redhat'):
            # Should not be called when actual instance is of subclass like oracle
            self.support_online_encryption = self.validate_online_encryption_support()

    def install_cryptsetup(self):
        if self.distro_info[1].startswith("6."):
            packages = ['cryptsetup-reencrypt']
        else:
            packages = ['cryptsetup']

        if self.command_executor.Execute("rpm -q " + " ".join(packages)):
            return_code = self.command_executor.Execute("yum install -y " + " ".join(packages), timeout=100)
            if return_code == -9:
                msg = "Command: yum install timed out. Make sure yum is configured correctly and there are no network problems."
                raise Exception(msg)
            return return_code

    def install_extras(self):
        packages = ['cryptsetup',
                    'lsscsi',
                    'psmisc',
                    'lvm2',
                    'uuid',
                    'at',
                    'patch',
                    'procps-ng',
                    'util-linux']

        if self.distro_info[1].startswith("6."):
            packages.append('cryptsetup-reencrypt')
            packages.remove('cryptsetup')
            packages.remove('procps-ng')
            packages.remove('util-linux')

        if self.command_executor.Execute("rpm -q " + " ".join(packages)):
            self.command_executor.Execute("yum install -y " + " ".join(packages))

    def update_prereq(self):
        if (self.distro_info[1].startswith('7.')):
            dracut_repack_needed = False

            if os.path.exists("/lib/dracut/modules.d/91lvm/"):
                # If 90lvm already exists 91lvm will cause problems, so remove it.
                if os.path.exists("/lib/dracut/modules.d/90lvm/"):
                    shutil.rmtree("/lib/dracut/modules.d/91lvm/")
                else:
                    os.rename("/lib/dracut/modules.d/91lvm/","/lib/dracut/modules.d/90lvm/")
                dracut_repack_needed = True

            if redhatPatching.is_old_patching_system():
                redhatPatching.remove_old_patching_system(self.logger, self.command_executor)
                dracut_repack_needed = True

            if os.path.exists("/lib/dracut/modules.d/91ade/"):
                shutil.rmtree("/lib/dracut/modules.d/91ade/")
                dracut_repack_needed = True

            if os.path.exists("/dev/mapper/osencrypt"):
                #TODO: only do this if needed (if code and existing module are different)
                redhatPatching.add_91_ade_dracut_module(self.command_executor)
                dracut_repack_needed = True

            if dracut_repack_needed:
                self.command_executor.ExecuteInBash("/usr/sbin/dracut -f -v --kver `grubby --default-kernel | sed 's|/boot/vmlinuz-||g'`", True)

    @staticmethod
    def is_old_patching_system():
        # Execute unpatching commands only if all the three patch files are present.
        if os.path.exists("/lib/dracut/modules.d/90crypt/cryptroot-ask.sh.orig"):
            if os.path.exists("/lib/dracut/modules.d/90crypt/module-setup.sh.orig"):
                if os.path.exists("/lib/dracut/modules.d/90crypt/parse-crypt.sh.orig"):
                    return True
        return False

    @staticmethod
    def _append_contents_to_file(self, contents, path):
        # Python 3.x strings are Unicode by default and do not use decode
        if sys.version_info[0] < 3:
            if isinstance(contents, str):
                contents = contents.decode('utf-8')

        with io.open(path, 'a') as f:
            f.write(contents)

    @staticmethod
    def add_91_ade_dracut_module(command_executor):
        scriptdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        ademoduledir = os.path.join(scriptdir, '../oscrypto/91ade')
        dracutmodulesdir = '/lib/dracut/modules.d'
        udevaderulepath = os.path.join(dracutmodulesdir, '91ade/50-udev-ade.rules')

        proc_comm = ProcessCommunicator()

        command_executor.Execute('cp -r {0} /lib/dracut/modules.d/'.format(ademoduledir), True)

        crypt_cmd = "cryptsetup status osencrypt | grep device:"
        command_executor.ExecuteInBash(crypt_cmd, communicator=proc_comm, suppress_logging=True)
        matches = re.findall(r'device:(.*)', proc_comm.stdout)
        if not matches:
            raise Exception("Could not find device in cryptsetup output")
        root_device = matches[0].strip()

        udevadm_cmd = "udevadm info --attribute-walk --name={0}".format(root_device)
        command_executor.Execute(command_to_execute=udevadm_cmd, raise_exception_on_failure=True, communicator=proc_comm)
        matches = re.findall(r'ATTR{partition}=="(.*)"', proc_comm.stdout)
        if not matches:
            raise Exception("Could not parse ATTR{partition} from udevadm info")
        partition = matches[0]
        sed_cmd = 'sed -i.bak s/ENCRYPTED_DISK_PARTITION/{0}/ "{1}"'.format(partition, udevaderulepath)
        command_executor.Execute(command_to_execute=sed_cmd, raise_exception_on_failure=True)
        sed_grub_cmd = "sed -i.bak '/osencrypt-locked/d' /etc/crypttab"
        command_executor.Execute(command_to_execute=sed_grub_cmd, raise_exception_on_failure=True)


    @staticmethod
    def remove_old_patching_system(logger, command_executor):
        logger.log("Removing patches and recreating initrd image")

        command_executor.Execute('mv /lib/dracut/modules.d/90crypt/cryptroot-ask.sh.orig /lib/dracut/modules.d/90crypt/cryptroot-ask.sh', False)
        command_executor.Execute('mv /lib/dracut/modules.d/90crypt/module-setup.sh.orig /lib/dracut/modules.d/90crypt/module-setup.sh', False)
        command_executor.Execute('mv /lib/dracut/modules.d/90crypt/parse-crypt.sh.orig /lib/dracut/modules.d/90crypt/parse-crypt.sh', False)
        
        sed_grub_cmd = "sed -i.bak '/rd.luks.uuid=osencrypt/d' /etc/default/grub"
        command_executor.Execute(sed_grub_cmd)
    
        redhatPatching.append_contents_to_file('\nGRUB_CMDLINE_LINUX+=" rd.debug"\n', 
                                               '/etc/default/grub')

        redhatPatching.append_contents_to_file('osencrypt UUID=osencrypt-locked none discard,header=/osluksheader\n',
                                               '/etc/crypttab')

        command_executor.Execute('/usr/sbin/dracut -f -v', True)
        command_executor.Execute('grub2-mkconfig -o /boot/grub2/grub.cfg', True)

    def add_kernelopts(self, args_to_add):
        grub_cfg_paths = [
            ("/boot/grub2/grub.cfg", "/boot/grub2/grubenv"),
            ("/boot/efi/EFI/redhat/grub.cfg", "/boot/efi/EFI/redhat/grubenv")
        ]

        grub_cfg_paths = filter(lambda path_pair: os.path.exists(path_pair[0]) and os.path.exists(path_pair[1]), grub_cfg_paths)

        for grub_cfg_path, grub_env_path in grub_cfg_paths:
            for arg in args_to_add:
                self.command_executor.ExecuteInBash("grubby --args {0} --update-kernel ALL -c {1} --env={2}".format(arg, grub_cfg_path, grub_env_path))