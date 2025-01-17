# -*- coding: utf-8 -*-
from hdx.location.currency import Currency
from hdx.utilities.dateparse import parse_date

from iati.calculatesplits import CalculateSplits
from iati.lookups import Lookups


class Transaction:
    def __init__(self, transaction_type_info, dtransaction, value):
        """
        Use the get_transaction static method to construct
        """
        self.transaction_type_info = transaction_type_info
        self.dtransaction = dtransaction
        # Use date falling back on value-date
        if dtransaction.date:
            self.year_month = dtransaction.date[:7]
        else:
            self.year_month = dtransaction.value_date[:7]
        self.value = value

    @staticmethod
    def get_transaction(configuration, dtransaction):
        # We're not interested in transactions that have no value
        if not dtransaction.value:
            return None
        # We're only interested in some transaction types
        transaction_type_info = configuration['transaction_type_info'].get(dtransaction.type)
        if not transaction_type_info:
            return None
        # We're not interested in transactions that can't be valued
        try:
            # Use value-date falling back on date
            date = dtransaction.value_date
            if not date:
                date = dtransaction.date
            # Convert the transaction value to USD
            value = Currency.get_historic_value_in_usd(dtransaction.value, dtransaction.currency, parse_date(date))
        except (ValueError, AttributeError):
            return None
        return Transaction(transaction_type_info, dtransaction, value)

    def get_label(self):
        return self.transaction_type_info['label']

    def get_classification(self):
        return self.transaction_type_info['classification']

    def get_direction(self):
        return self.transaction_type_info['direction']

    def process(self, today_year_month, activity):
        if self.value:
            if (Lookups.filter_transaction_date and self.year_month < Lookups.filter_transaction_date) or self.year_month > today_year_month:
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
        if self.get_direction() == 'outgoing':
            if self.get_classification() == 'commitments':
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
        is_strict = True if (Lookups.checks.has_desired_sector(self.dtransaction.sectors) or
                             (self.dtransaction.description and
                              Lookups.checks.is_desired_narrative(self.dtransaction.description.narratives))) else False
        is_strict = is_strict or activity_strict
        return 1 if is_strict else 0

    def make_country_or_region_splits(self, activity_country_splits):
        return CalculateSplits.make_country_or_region_splits(self.dtransaction, activity_country_splits)

    def make_sector_splits(self, activity_sector_splits):
        return CalculateSplits.make_sector_splits(self.dtransaction, activity_sector_splits)

    def get_provider_receiver(self):
        if self.get_direction() == 'incoming':
            provider = Lookups.get_org_info(self.dtransaction.provider_org)
            receiver = {'id': '', 'name': '', 'type': ''}
        else:
            provider = {'id': '', 'name': '', 'type': ''}
            expenditure = self.get_label() == 'Expenditure'
            receiver = Lookups.get_org_info(self.dtransaction.receiver_org, expenditure=expenditure)
        return provider, receiver
