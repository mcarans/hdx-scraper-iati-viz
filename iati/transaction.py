# -*- coding: utf-8 -*-
from iati.calculatesplits import CalculateSplits
from iati.covidchecks import has_c19_sector, is_c19_narrative
from iati.lookups import Lookups


class Transaction:
    def __init__(self, transaction_type_info, dtransaction):
        self.classification = transaction_type_info['classification']
        self.direction = transaction_type_info['direction']
        self.dtransaction = dtransaction
        # Convert the transaction value to USD
        self.value = Lookups.get_value_in_usd(dtransaction.value, dtransaction.currency, dtransaction.date)

    @staticmethod
    def get_transaction(configuration, dtransaction):
        # We're not interested in transactions that have no value
        if not dtransaction.value:
            return None
        # We're only interested in some transaction types
        transaction_type_info = configuration['transaction_type_info'].get(dtransaction.type)
        if not transaction_type_info:
            return None
        return Transaction(transaction_type_info, dtransaction)

    def process(self, this_month, activity):
        if self.value:
            self.month = self.dtransaction.date[:7]
            if self.month < '2020-01' or self.month > this_month:
                # Skip transactions with out-of-range months
                return False
        else:
            return False

        # Set the net (new money) factors based on the type (commitments or spending)
        self.net_value = self.get_usd_net_value(activity.commitment_factor, activity.spending_factor)
        # transaction status defaults to activity
        self.is_humanitarian = self.is_humanitarian(activity.humanitarian)
        self.is_strict = self.is_strict(activity.strict)
        return True

    def get_usd_net_value(self, commitment_factor, spending_factor):
        # Set the net (new money) factors based on the type (commitments or spending)
        if self.direction == 'outgoing':
            if self.classification == 'commitments':
                return self.value * commitment_factor
            else:
                return self.value * spending_factor
        return None

    def is_humanitarian(self, activity_humanitarian):
        transaction_humanitarian = self.dtransaction.humanitarian
        if transaction_humanitarian is None:
            is_humanitarian = activity_humanitarian
        else:
            is_humanitarian = transaction_humanitarian
        return 1 if is_humanitarian else 0

    def is_strict(self, activity_strict):
        is_strict = True if (has_c19_sector(self.dtransaction.sectors) or
                             (self.dtransaction.description and
                              is_c19_narrative(self.dtransaction.description.narratives))) else False
        is_strict = is_strict or activity_strict
        return 1 if is_strict else 0

    def make_country_splits(self, activity_country_splits):
        return CalculateSplits.make_country_splits(self.dtransaction, activity_country_splits)

    def make_sector_splits(self, activity_sector_splits):
        return CalculateSplits.make_sector_splits(self.dtransaction, activity_sector_splits)

    def get_provider_receiver(self):
        if self.direction == 'incoming':
            provider = Lookups.get_org_name(self.dtransaction.provider_org)
            receiver = ''
        else:
            provider = ''
            receiver = Lookups.get_org_name(self.dtransaction.receiver_org)
        return provider, receiver
