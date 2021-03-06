# Copyright 2015 Hewlett-Packard Development Company, L.P.
# Copyright 2016 Rackspace Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import pprint

from tempest import config
from tempest.lib.common.utils import data_utils
from tempest import test

from f5lbaasdriver.test.tempest.tests.api import base

CONF = config.CONF


class PoolTestJSON(base.F5BaseTestCase):
    """Loadbalancer Tempest tests.

    Tests the following operations in the Neutron-LBaaS API using the
    REST client for Load Balancers with default credentials:

        create detached pool
        create shared pool
        delete shared pool
        delete detached pool
    """

    @classmethod
    def resource_setup(cls):
        """Setup client fixtures for test suite."""
        super(PoolTestJSON, cls).resource_setup()
        if not test.is_extension_enabled('lbaas', 'network'):
            msg = "lbaas extension not enabled."
            raise cls.skipException(msg)
        network_name = data_utils.rand_name('network')
        cls.network = cls.create_network(network_name)
        cls.subnet = cls.create_subnet(cls.network)
        cls.partition = 'Project_' + cls.subnet['tenant_id']
        cls.create_lb_kwargs = {'tenant_id': cls.subnet['tenant_id'],
                                'vip_subnet_id': cls.subnet['id']}
        cls.load_balancer = \
            cls._create_active_load_balancer(**cls.create_lb_kwargs)
        cls.load_balancer_id = cls.load_balancer['id']

        # get an RPC client for calling into driver
        cls.client = cls.plugin_rpc.get_client()
        cls.context = cls.plugin_rpc.get_context()

    @classmethod
    def resource_cleanup(cls):
        super(PoolTestJSON, cls).resource_cleanup()

    @test.attr(type='smoke')
    def test_create_shared_detached_pools(self):

        # create detached pool -- no listeners
        shared_pool_kwargs = {'loadbalancer_id': self.load_balancer_id,
                              'protocol': 'HTTP',
                              'description': 'Shared pool',
                              'lb_algorithm': 'ROUND_ROBIN'}
        shared_pool = self._create_pool(**shared_pool_kwargs)

        # create first listener for pool
        first_listener_kwargs = {'loadbalancer_id': self.load_balancer_id,
                                 'default_pool_id': shared_pool['id'],
                                 'description': 'First Listener',
                                 'protocol': 'HTTP',
                                 'protocol_port': 80}
        first_listener = self._create_listener(**first_listener_kwargs)
        self.addCleanup(self._delete_listener, first_listener['id'])

        # create second listener for same pool
        second_listener_kwargs = first_listener_kwargs
        second_listener_kwargs['protocol_port'] = 8080
        second_listener_kwargs['description'] = 'Second Listener'
        second_listener = self._create_listener(**second_listener_kwargs)
        self.addCleanup(self._delete_listener, second_listener['id'])

        # Check that bigip has pools set for each listener
        vs1_name = 'Project_' + first_listener['id']
        vs2_name = 'Project_' + second_listener['id']
        pool_name = 'Project_' + shared_pool['id']
        for bigip_client in self.bigip_clients:
            assert bigip_client.virtual_server_has_pool(
                vs1_name, self.partition, pool_name) is True
            assert bigip_client.virtual_server_has_pool(
                vs2_name, self.partition, pool_name) is True

        res = self.client.call(self.context, 'get_service_by_loadbalancer_id',
                               loadbalancer_id=self.load_balancer_id)

        pool = res['pools'][0]
        self.assertEqual(pool['id'], shared_pool['id'])

        # validate pool has two listeners
        assert res['listeners'][0]['default_pool_id'] == shared_pool['id']
        assert res['listeners'][1]['default_pool_id'] == shared_pool['id']

        assert 'listeners' not in pool

        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(res)

        # delete shared pool
        self._delete_pool(shared_pool['id'], wait=True)
        res = self.client.call(self.context, 'get_service_by_loadbalancer_id',
                               loadbalancer_id=self.load_balancer_id)

        # validate listeners not associated with a pool
        self.assertEqual(0, len(res['pools']))
        for listener in res['listeners']:
            self.assertIsNone(listener['default_pool_id'])

    @test.attr(type='smoke')
    def test_create_shared_pools(self):

        # create first listener with no pool yet
        first_listener_kwargs = {'loadbalancer_id': self.load_balancer_id,
                                 'description': 'First Listener',
                                 'protocol': 'HTTP',
                                 'protocol_port': 80}
        first_listener = self._create_listener(**first_listener_kwargs)
        self.addCleanup(self._delete_listener, first_listener['id'])

        # create attached pool
        shared_pool_kwargs = {'listener_id': first_listener['id'],
                              'protocol': 'HTTP',
                              'description': 'Shared pool',
                              'lb_algorithm': 'ROUND_ROBIN'}
        shared_pool = self._create_pool(**shared_pool_kwargs)

        # create second listener with that default pool set
        second_listener_kwargs = first_listener_kwargs
        second_listener_kwargs['default_pool_id'] = shared_pool['id']
        second_listener_kwargs['protocol_port'] = 8080
        second_listener_kwargs['description'] = 'Second Listener'
        second_listener = self._create_listener(**second_listener_kwargs)
        self.addCleanup(self._delete_listener, second_listener['id'])

        # Check that bigip has pools set for each listener
        vs1_name = 'Project_' + first_listener['id']
        vs2_name = 'Project_' + second_listener['id']
        pool_name = 'Project_' + shared_pool['id']
        for bigip_client in self.bigip_clients:
            assert bigip_client.virtual_server_has_pool(
                vs1_name, self.partition, pool_name) is True
            assert bigip_client.virtual_server_has_pool(
                vs2_name, self.partition, pool_name) is True
        # delete shared pool
        self._delete_pool(shared_pool['id'], wait=True)
        res = self.client.call(self.context, 'get_service_by_loadbalancer_id',
                               loadbalancer_id=self.load_balancer_id)

        # validate listeners not associated with a pool
        self.assertEqual(0, len(res['pools']))
        for listener in res['listeners']:
            self.assertIsNone(listener['default_pool_id'])
