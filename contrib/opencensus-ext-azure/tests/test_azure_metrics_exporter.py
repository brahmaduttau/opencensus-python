# Copyright 2019, OpenCensus Authors
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

import unittest
from datetime import datetime

import mock

from opencensus.common import utils
from opencensus.ext.azure.common import Options
from opencensus.ext.azure.common.protocol import DataPoint
from opencensus.ext.azure.metrics_exporter import (
    MetricsExporter,
    new_metrics_exporter,
    standard_metrics,
)
from opencensus.metrics import label_key, label_value
from opencensus.metrics.export import (
    metric,
    metric_descriptor,
    point,
    time_series,
    value,
)
from opencensus.metrics.export.metric_descriptor import MetricDescriptorType


def create_metric():
    lv = label_value.LabelValue('val')
    val = value.ValueLong(value=123)
    dt = datetime(2019, 3, 20, 21, 34, 0, 537954)
    pp = point.Point(value=val, timestamp=dt)

    ts = [
        time_series.TimeSeries(label_values=[lv], points=[pp],
                               start_timestamp=utils.to_iso_str(dt))
    ]

    desc = metric_descriptor.MetricDescriptor(
        name='name',
        description='description',
        unit='unit',
        type_=metric_descriptor.MetricDescriptorType.GAUGE_INT64,
        label_keys=[label_key.LabelKey('key', 'description')]
    )

    mm = metric.Metric(descriptor=desc, time_series=ts)
    return mm


class TestAzureMetricsExporter(unittest.TestCase):
    def test_constructor_missing_key(self):
        instrumentation_key = Options._default.instrumentation_key
        Options._default.instrumentation_key = None
        self.assertRaises(ValueError,
                          lambda: MetricsExporter())
        Options._default.instrumentation_key = instrumentation_key

    def test_constructor_invalid_batch_size(self):
        self.assertRaises(
            ValueError,
            lambda: MetricsExporter(
                instrumentation_key='12345678-1234-5678-abcd-12345678abcd',
                max_batch_size=-1
            ))

    @mock.patch('requests.post', return_value=mock.Mock())
    def test_export_metrics(self, requests_mock):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd')
        requests_mock.return_value.text = '{"itemsReceived":1,'\
                                          '"itemsAccepted":1,'\
                                          '"errors":[]}'
        requests_mock.return_value.status_code = 200
        exporter.export_metrics([metric])

        self.assertEqual(len(requests_mock.call_args_list), 1)
        post_body = requests_mock.call_args_list[0][1]['data']
        self.assertTrue('metrics' in post_body)
        self.assertTrue('properties' in post_body)

    def test_export_metrics_histogram(self):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd')
        metric.descriptor._type = MetricDescriptorType.CUMULATIVE_DISTRIBUTION

        self.assertIsNone(exporter.export_metrics([metric]))

    @mock.patch('requests.post', return_value=mock.Mock())
    def test_export_metrics_empty(self, requests_mock):
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd')
        exporter.export_metrics([])

        self.assertEqual(len(requests_mock.call_args_list), 0)

    @mock.patch('requests.post', return_value=mock.Mock())
    def test_export_metrics_full_batch(self, requests_mock):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd',
            max_batch_size=1)
        requests_mock.return_value.status_code = 200
        requests_mock.return_value.text = '{"itemsReceived":1,'\
                                          '"itemsAccepted":1,'\
                                          '"errors":[]}'
        exporter.export_metrics([metric])

        self.assertEqual(len(requests_mock.call_args_list), 1)
        post_body = requests_mock.call_args_list[0][1]['data']
        self.assertTrue('metrics' in post_body)
        self.assertTrue('properties' in post_body)

    def test_create_data_points(self):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd'
        )
        data_points = exporter._create_data_points(metric.time_series[0],
                                                   metric.descriptor)

        self.assertEqual(len(data_points), 1)
        data_point = data_points[0]
        self.assertEqual(data_point.ns, metric.descriptor.name)
        self.assertEqual(data_point.name, metric.descriptor.name)
        self.assertEqual(data_point.value,
                         metric.time_series[0].points[0].value.value)

    def test_create_properties(self):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd'
        )
        properties = exporter._create_properties(metric.time_series[0],
                                                 metric.descriptor)

        self.assertEqual(len(properties), 1)
        self.assertEqual(properties['key'], 'val')

    def test_create_properties_none(self):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd'
        )
        metric.time_series[0].label_values[0]._value = None
        properties = exporter._create_properties(metric.time_series[0],
                                                 metric.descriptor)

        self.assertEqual(len(properties), 1)
        self.assertEqual(properties['key'], 'null')

    def test_create_envelope(self):
        metric = create_metric()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd'
        )
        value = metric.time_series[0].points[0].value.value
        data_point = DataPoint(ns=metric.descriptor.name,
                               name=metric.descriptor.name,
                               value=value)
        timestamp = datetime(2019, 3, 20, 21, 34, 0, 537954)
        properties = {'url': 'website.com'}
        envelope = exporter._create_envelope(data_point, timestamp, properties)

        self.assertTrue('iKey' in envelope)
        self.assertEqual(envelope.iKey, '12345678-1234-5678-abcd-12345678abcd')
        self.assertTrue('tags' in envelope)
        self.assertTrue('time' in envelope)
        self.assertEqual(envelope.time, timestamp.isoformat())
        self.assertTrue('name' in envelope)
        self.assertEqual(envelope.name, 'Microsoft.ApplicationInsights.Metric')
        self.assertTrue('data' in envelope)
        self.assertTrue('baseData' in envelope.data)
        self.assertTrue('baseType' in envelope.data)
        self.assertTrue('metrics' in envelope.data.baseData)
        self.assertTrue('properties' in envelope.data.baseData)
        self.assertEqual(envelope.data.baseData.properties, properties)

    def test_shutdown(self):
        mock_thread = mock.Mock()
        mock_storage = mock.Mock()
        exporter = MetricsExporter(
            instrumentation_key='12345678-1234-5678-abcd-12345678abcd'
        )
        exporter.exporter_thread = mock_thread
        exporter.storage = mock_storage
        exporter.shutdown()
        mock_thread.close.assert_called_once()
        mock_storage.close.assert_called_once()

    @mock.patch('opencensus.ext.azure.metrics_exporter'
                '.transport.get_exporter_thread')
    def test_new_metrics_exporter(self, exporter_mock):
        with mock.patch('opencensus.ext.azure.metrics_exporter'
                        '.statsbeat_metrics.collect_statsbeat_metrics') as hb:
            hb.return_value = None
            iKey = '12345678-1234-5678-abcd-12345678abcd'
            exporter = new_metrics_exporter(instrumentation_key=iKey)

            self.assertEqual(exporter.options.instrumentation_key, iKey)
            self.assertEqual(len(exporter_mock.call_args_list), 1)
            self.assertEqual(len(exporter_mock.call_args[0][0]), 2)
            producer_class = standard_metrics.AzureStandardMetricsProducer
            self.assertFalse(isinstance(exporter_mock.call_args[0][0][0],
                                        producer_class))
            self.assertTrue(isinstance(exporter_mock.call_args[0][0][1],
                                       producer_class))

    @mock.patch('opencensus.ext.azure.metrics_exporter'
                '.transport.get_exporter_thread')
    def test_new_metrics_exporter_no_standard_metrics(self, exporter_mock):
        with mock.patch('opencensus.ext.azure.metrics_exporter'
                        '.statsbeat_metrics.collect_statsbeat_metrics') as hb:
            hb.return_value = None
            iKey = '12345678-1234-5678-abcd-12345678abcd'
            exporter = new_metrics_exporter(
                instrumentation_key=iKey, enable_standard_metrics=False)

            self.assertEqual(exporter.options.instrumentation_key, iKey)
            self.assertEqual(len(exporter_mock.call_args_list), 1)
            self.assertEqual(len(exporter_mock.call_args[0][0]), 1)
            producer_class = standard_metrics.AzureStandardMetricsProducer
            self.assertFalse(isinstance(exporter_mock.call_args[0][0][0],
                                        producer_class))

    @unittest.skip("Skip because disabling heartbeat metrics")
    @mock.patch('opencensus.ext.azure.metrics_exporter'
                '.transport.get_exporter_thread')
    def test_new_metrics_exporter_heartbeat(self, exporter_mock):
        with mock.patch('opencensus.ext.azure.metrics_exporter'
                        '.statsbeat_metrics.collect_statsbeat_metrics') as hb:
            iKey = '12345678-1234-5678-abcd-12345678abcd'
            exporter = new_metrics_exporter(instrumentation_key=iKey)

            self.assertEqual(exporter.options.instrumentation_key, iKey)
            self.assertEqual(len(hb.call_args_list), 1)
            self.assertEqual(len(hb.call_args[0]), 2)
            self.assertEqual(hb.call_args[0][0], None)
            self.assertEqual(hb.call_args[0][1], iKey)
