#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2010-2016  Joanna Rutkowska <joanna@invisiblethingslab.com>
# Copyright (C) 2013-2016  Marek Marczykowski-Górecki
#                              <marmarek@invisiblethingslab.com>
# Copyright (C) 2014-2018  Wojtek Porczyk <woju@invisiblethingslab.com>
# Copyright (C) 2019 Frédéric Pierret <frederic.pierret@qubes-os.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, see <https://www.gnu.org/licenses/>.
#

import re

import qubes.config
import qubes.ext
import qubes.exc


class GUI(qubes.ext.Extension):
    # pylint: disable=too-few-public-methods,unused-argument,no-self-use
    @staticmethod
    def attached_vms(vm):
        for domain in vm.app.domains:
            if getattr(domain, 'guivm', None) and domain.guivm == vm:
                yield domain

    @qubes.ext.handler('domain-pre-shutdown')
    def on_domain_pre_shutdown(self, vm, event, **kwargs):
        attached_vms = [domain for domain in self.attached_vms(vm) if
                        domain.is_running()]
        if attached_vms and not kwargs.get('force', False):
            raise qubes.exc.QubesVMError(
                self, 'There are running VMs using this VM as GuiVM: '
                      '{}'.format(', '.join(vm.name for vm in attached_vms)))

    @staticmethod
    def send_gui_mode(vm):
        vm.run_service('qubes.SetGuiMode',
                       input=('SEAMLESS'
                              if vm.features.get('gui-seamless', False)
                              else 'FULLSCREEN'))

    @qubes.ext.handler('domain-init', 'domain-load')
    def on_domain_init_load(self, vm, event):
        if getattr(vm, 'guivm', None):
            if 'guivm-' + vm.guivm.name not in vm.tags:
                self.on_property_set(vm, event, name='guivm', newvalue=vm.guivm)

    @qubes.ext.handler('property-reset:guivm')
    def on_property_reset(self, subject, event, name, oldvalue=None):
        newvalue = getattr(subject, 'guivm', None)
        self.on_property_set(subject, event, name, newvalue, oldvalue)

    @qubes.ext.handler('property-set:guivm')
    def on_property_set(self, subject, event, name, newvalue, oldvalue=None):
        # Clean other 'guivm-XXX' tags.
        # gui-daemon can connect to only one domain
        tags_list = list(subject.tags)
        for tag in tags_list:
            if tag.startswith('guivm-'):
                subject.tags.remove(tag)

        if newvalue:
            guivm = 'guivm-' + newvalue.name
            subject.tags.add(guivm)

    @qubes.ext.handler('domain-qdb-create')
    def on_domain_qdb_create(self, vm, event):
        for feature in ('gui-videoram-overhead', 'gui-videoram-min'):
            try:
                vm.untrusted_qdb.write(
                    '/qubes-{}'.format(feature),
                    vm.features.check_with_template_and_adminvm(
                        feature))
            except KeyError:
                pass

        # Add GuiVM Xen ID for gui-daemon
        if getattr(vm, 'guivm', None):
            if vm != vm.guivm and vm.guivm.is_running():
                vm.untrusted_qdb.write('/qubes-gui-domain-xid',
                                       str(vm.guivm.xid))

            # Add keyboard layout from that of GuiVM
            kbd_layout = vm.guivm.features.get('keyboard-layout', None)
            if kbd_layout:
                vm.untrusted_qdb.write('/keyboard-layout', kbd_layout)

        # Set GuiVM prefix
        guivm_windows_prefix = vm.features.get('guivm-windows-prefix', 'GuiVM')
        if vm.features.get('service.guivm-gui-agent', None):
            vm.untrusted_qdb.write('/guivm-windows-prefix',
                                   guivm_windows_prefix)

    @qubes.ext.handler('property-set:default_guivm', system=True)
    def on_property_set_default_guivm(self, app, event, name, newvalue,
                                      oldvalue=None):
        for vm in app.domains:
            if hasattr(vm, 'guivm') and vm.property_is_default('guivm'):
                vm.fire_event('property-set:guivm',
                              name='guivm', newvalue=newvalue,
                              oldvalue=oldvalue)

    @qubes.ext.handler('domain-start')
    def on_domain_start(self, vm, event, **kwargs):
        attached_vms = [domain for domain in self.attached_vms(vm) if
                        domain.is_running()]
        for attached_vm in attached_vms:
            attached_vm.untrusted_qdb.write('/qubes-gui-domain-xid',
                                            str(vm.xid))

    @qubes.ext.handler('domain-feature-pre-set:keyboard-layout')
    def on_feature_pre_set(self, subject, event, feature, value, oldvalue=None):
        untrusted_xkb_layout = value.split('+')
        if len(untrusted_xkb_layout) != 3:
            raise qubes.exc.QubesValueError("Invalid number of parameters")

        untrusted_layout = untrusted_xkb_layout[0]
        untrusted_variant = untrusted_xkb_layout[1]
        untrusted_options = untrusted_xkb_layout[2]

        re_variant = r'^[a-zA-Z0-9-_]*$'
        re_options = r'^[a-zA-Z0-9-_:,]*$'

        if not untrusted_layout.isalpha():
            raise qubes.exc.QubesValueError("Invalid layout provided")
        if not re.match(re_variant, untrusted_variant):
            raise qubes.exc.QubesValueError("Invalid variant provided")
        if not re.match(re_options, untrusted_options):
            raise qubes.exc.QubesValueError("Invalid options provided")
