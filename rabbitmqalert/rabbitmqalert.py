#! /usr/bin/python2
# -*- coding: utf-8 -*-

import urllib2
import time
import smtplib

import sys
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

import optionsresolver
import logging
import requests


class RabbitMQAlert(object):

    def check_queue_conditions(self, options):
        vhost = options["vhost"]
        queue = options["queue"]
        url = self._get_url("queues/{0}/{1}".format(vhost, queue), options)
        data = self.send_request(url, options)
        if data is None:
            return

        messages_ready = data.get("messages_ready")
        messages_unacknowledged = data.get("messages_unacknowledged")
        messages = data.get("messages")
        consumers = data.get("consumers")

        queue_conditions = options["conditions"][queue]
        ready_size = queue_conditions.get("ready_queue_size")
        unack_size = queue_conditions.get("unack_queue_size")
        total_size = queue_conditions.get("total_queue_size")
        consumers_connected_min = queue_conditions.get("queue_consumers_connected")

        if ready_size is not None and messages_ready > ready_size:
            self.send_notification(options, "%s %s: messages_ready = %d > %d" % (vhost, queue, messages_ready, ready_size))

        if unack_size is not None and messages_unacknowledged > unack_size:
            self.send_notification(options, "%s %s: messages_unacknowledged = %d > %d" % (
                vhost, queue, messages_unacknowledged, unack_size))

        if total_size is not None and messages > total_size:
            self.send_notification(options, "%s %s: messages = %d > %d" % (vhost, queue, messages, total_size))

        if consumers_connected_min is not None and consumers < consumers_connected_min:
            self.send_notification(options,
                                   "%s %s: consumers_connected = %d < %d" % (vhost, queue, consumers, consumers_connected_min))

    def check_consumer_conditions(self, options):
        url = self._get_url("consumers", options)
        data = self.send_request(url, options)
        if data is None:
            return

        consumers_connected = len(data)
        consumers_connected_min = options["default_conditions"].get("consumers_connected")

        if consumers_connected is not None and consumers_connected < consumers_connected_min:
            self.send_notification(options,
                                   "consumers_connected = %d < %d" % (consumers_connected, consumers_connected_min))

    def check_connection_conditions(self, options):
        url = self._get_url("connections", options)
        data = self.send_request(url, options)
        if data is None:
            return

        open_connections = len(data)

        open_connections_min = options["default_conditions"].get("open_connections")

        if open_connections is not None and open_connections < open_connections_min:
            self.send_notification(options, "open_connections = %d < %d" % (open_connections, open_connections_min))

    def check_node_conditions(self, options):
        url = self._get_url("nodes", options)
        data = self.send_request(url, options)
        if data is None:
            return

        nodes_running = len(data)

        conditions = options["default_conditions"]
        nodes_run = conditions.get("nodes_running")
        node_memory = conditions.get("node_memory_used")

        if nodes_run is not None and nodes_running < nodes_run:
            self.send_notification(options, "nodes_running = %d < %d" % (nodes_running, nodes_run))

        for node in data:
            if node_memory is not None and node.get("mem_used") > (node_memory * 1000000):
                self.send_notification(options, "Node %s - node_memory_used = %d > %d MBs" % (
                    node.get("name"), node.get("mem_used"), node_memory))

    def send_request(self, url, options):
        class HostHeaderSSLAdapter(HTTPAdapter):
            def send(self, request, **kwargs):
                connection_pool_kwargs = self.poolmanager.connection_pool_kw
                connection_pool_kwargs["assert_hostname"] = False
                return super(HostHeaderSSLAdapter, self).send(request, **kwargs)

        auth = HTTPBasicAuth(options["username"], options["password"])

        try:
            s = requests.Session()
            if options["ssl"]:
                s.mount('https://', HostHeaderSSLAdapter())
            r = s.get(url, auth=auth, cert=self._get_cert(options), verify=self._get_ca(options))
            r.raise_for_status()
            data = r.json()
            return data
        except requests.exceptions.RequestException:
            logging.exception("Error while consuming the API endpoint \"{0}\"".format(url))
            return None

    @staticmethod
    def send_notification(options, body):
        text = "%s - %s" % (options["host"], body)

        if "email_to" in options and options["email_to"]:
            logging.info("Sending email notification: \"{0}\"".format(body))

            server = smtplib.SMTP(options["email_server"], 25)

            if "email_ssl" in options and options["email_ssl"]:
                server = smtplib.SMTP_SSL(options["email_server"], 465)

            if "email_password" in options and options["email_password"]:
                server.login(options["email_from"], options["email_password"])

            recipients = options["email_to"]
            # add subject as header before message text
            subject_email = options["email_subject"] % (options["host"], options["queue"])
            text_email = "Subject: %s\n\n%s" % (subject_email, text)
            server.sendmail(options["email_from"], recipients, text_email)

            server.quit()

        if "slack_url" in options and options["slack_url"] and "slack_channel" in options and options[
                "slack_channel"] and "slack_username" in options and options["slack_username"]:
            logging.info("Sending Slack notification: \"{0}\"".format(body))

            # escape double quotes from possibly breaking the slack message payload
            text_slack = text.replace("\"", "\\\"")
            slack_payload = '{"channel": "#%s", "username": "%s", "text": "%s"}' % (
                options["slack_channel"], options["slack_username"], text_slack)

            request = urllib2.Request(options["slack_url"], slack_payload)
            response = urllib2.urlopen(request)
            response.close()

        if "telegram_bot_id" in options and options["telegram_bot_id"] and "telegram_channel" in options and options[
                "telegram_channel"]:
            logging.info("Sending Telegram notification: \"{0}\"".format(body))

            text_telegram = "%s: %s" % (options["queue"], text)
            telegram_url = "https://api.telegram.org/bot%s/sendMessage?chat_id=%s&text=%s" % (
                options["telegram_bot_id"], options["telegram_channel"], text_telegram)

            request = urllib2.Request(telegram_url)
            response = urllib2.urlopen(request)
            response.close()

    @classmethod
    def _get_url(cls, path, options):
        if options["ssl"]:
            protocol = "https"
        else:
            protocol = "http"

        return "{0}://{1}:{2}/api/{3}".format(protocol, options["host"], options["port"], path)

    @classmethod
    def _get_cert(cls, options):
        if not options["ssl"]:
            return None

        return options["ssl_cert"], options["ssl_key"]

    @classmethod
    def _get_ca(cls, options):
        if not options["ssl"]:
            return None

        return options["ssl_ca"]


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.info("Starting application")

    opt_resolver = optionsresolver.OptionsResolver()
    options = opt_resolver.setup_options()
    options = options.copy()
    del opt_resolver

    while True:
        logging.info("Assessing node: {0}".format(options["host"]))
        rabbitmq_alert = RabbitMQAlert()

        default_conditions = options["default_conditions"]
        if "nodes_running" in default_conditions:
            rabbitmq_alert.check_node_conditions(options)
        if "open_connections" in default_conditions:
            rabbitmq_alert.check_connection_conditions(options)
        if "consumers_connected" in default_conditions:
            rabbitmq_alert.check_consumer_conditions(options)

        for queue in options["queues"]:
            logging.info("Assessing queue: {0}".format(queue))

            options["queue"] = queue
            queue_conditions = options["conditions"][queue]

            if "ready_queue_size" in queue_conditions \
                    or "unack_queue_size" in queue_conditions \
                    or "total_queue_size" in queue_conditions \
                    or "queue_consumers_connected" in queue_conditions:
                rabbitmq_alert.check_queue_conditions(options)

        logging.info("Next assessment in {0} seconds".format(options["check_rate"]))
        time.sleep(options["check_rate"])


if __name__ == "__main__":
    main()
