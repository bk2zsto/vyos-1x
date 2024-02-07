#!/usr/bin/env python3
#
# Copyright (C) 2021-2024 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import unittest

from base_vyostest_shim import VyOSUnitTestSHIM

from vyos.configsession import ConfigSessionError
from vyos.utils.process import cmd
from vyos.utils.process import process_named_running

base_path = ['protocols', 'rpki']
PROCESS_NAME = 'bgpd'

rpki_ssh_key = '/config/auth/id_rsa_rpki'
rpki_ssh_pub = f'{rpki_ssh_key}.pub'

class TestProtocolsRPKI(VyOSUnitTestSHIM.TestCase):
    @classmethod
    def setUpClass(cls):
        # call base-classes classmethod
        super(TestProtocolsRPKI, cls).setUpClass()
        # Retrieve FRR daemon PID - it is not allowed to crash, thus PID must remain the same
        cls.daemon_pid = process_named_running(PROCESS_NAME)
        # ensure we can also run this test on a live system - so lets clean
        # out the current configuration :)
        cls.cli_delete(cls, base_path)

    def tearDown(self):
        self.cli_delete(base_path)
        self.cli_commit()

        # Nothing RPKI specific should be left over in the config
        # frrconfig = self.getFRRconfig('rpki')
        # self.assertNotIn('rpki', frrconfig)

        # check process health and continuity
        self.assertEqual(self.daemon_pid, process_named_running(PROCESS_NAME))

    def test_rpki(self):
        expire_interval = '3600'
        polling_period = '600'
        retry_interval = '300'
        cache = {
            '192.0.2.1' : {
                'port' : '8080',
                'preference' : '10'
            },
            '2001:db8::1' : {
                'port' : '1234',
                'preference' : '30'
            },
            'rpki.vyos.net' : {
                'port' : '5678',
                'preference' : '40'
            },
        }

        self.cli_set(base_path + ['expire-interval', expire_interval])
        self.cli_set(base_path + ['polling-period', polling_period])
        self.cli_set(base_path + ['retry-interval', retry_interval])

        for peer, peer_config in cache.items():
            self.cli_set(base_path + ['cache', peer, 'port', peer_config['port']])
            self.cli_set(base_path + ['cache', peer, 'preference', peer_config['preference']])

        # commit changes
        self.cli_commit()

        # Verify FRR configuration
        frrconfig = self.getFRRconfig('rpki')
        self.assertIn(f'rpki expire_interval {expire_interval}', frrconfig)
        self.assertIn(f'rpki polling_period {polling_period}', frrconfig)
        self.assertIn(f'rpki retry_interval {retry_interval}', frrconfig)

        for peer, peer_config in cache.items():
            port = peer_config['port']
            preference = peer_config['preference']
            self.assertIn(f'rpki cache {peer} {port} preference {preference}', frrconfig)

    def test_rpki_ssh(self):
        polling = '7200'
        cache = {
            '192.0.2.3' : {
                'port' : '1234',
                'username' : 'foo',
                'preference' : '10'
            },
            '192.0.2.4' : {
                'port' : '5678',
                'username' : 'bar',
                'preference' : '20'
            },
        }

        self.cli_set(base_path + ['polling-period', polling])

        for peer, peer_config in cache.items():
            self.cli_set(base_path + ['cache', peer, 'port', peer_config['port']])
            self.cli_set(base_path + ['cache', peer, 'preference', peer_config['preference']])
            self.cli_set(base_path + ['cache', peer, 'ssh', 'username', peer_config['username']])
            self.cli_set(base_path + ['cache', peer, 'ssh', 'public-key-file', rpki_ssh_pub])
            self.cli_set(base_path + ['cache', peer, 'ssh', 'private-key-file', rpki_ssh_key])

        # commit changes
        self.cli_commit()

        # Verify FRR configuration
        frrconfig = self.getFRRconfig('rpki')
        self.assertIn(f'rpki polling_period {polling}', frrconfig)

        for peer, peer_config in cache.items():
            port = peer_config['port']
            preference = peer_config['preference']
            username = peer_config['username']
            self.assertIn(f'rpki cache {peer} {port} {username} {rpki_ssh_key} {rpki_ssh_pub} preference {preference}', frrconfig)


    def test_rpki_verify_preference(self):
        cache = {
            '192.0.2.1' : {
                'port' : '8080',
                'preference' : '1'
            },
            '192.0.2.2' : {
                'port' : '9090',
                'preference' : '1'
            },
        }

        for peer, peer_config in cache.items():
            self.cli_set(base_path + ['cache', peer, 'port', peer_config['port']])
            self.cli_set(base_path + ['cache', peer, 'preference', peer_config['preference']])

        # check validate() - preferences must be unique
        with self.assertRaises(ConfigSessionError):
            self.cli_commit()


if __name__ == '__main__':
    # Create OpenSSH keypair used in RPKI tests
    if not os.path.isfile(rpki_ssh_key):
        cmd(f'ssh-keygen -t rsa -f {rpki_ssh_key} -N ""')

    unittest.main(verbosity=2)
