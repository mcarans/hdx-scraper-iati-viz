# -*- coding: utf-8 -*-
from iati.calculatesplits import CalculateSplits
from iati.covidchecks import has_c19_scope, has_c19_tag, has_c19_sector, is_c19_narrative
from iati.lookups import Lookups
from iati.transaction import Transaction
from iati.utils import convert_to_usd


class Activity:
    activities_seen = set()

    def __init__(self, configuration, this_month, dactivity):
        self.configuration = configuration
        self.this_month = this_month
        self.dactivity = dactivity
        self.identifier = dactivity.identifier

    def should_process(self):
        # Don't use the same activity twice
        if self.identifier in self.activities_seen:
            return False
        self.activities_seen.add(self.identifier)

        # Skip activities from a secondary reporter (should have been filtered out already)
        if self.dactivity.secondary_reporter:
            return False
        return True

    def get_reporting_org(self):
        return Lookups.get_org_name(self.dactivity.reporting_org)

    def get_org_type(self):
        return str(self.dactivity.reporting_org.type)

    def is_strict(self):
        return True if (
            has_c19_scope(self.dactivity.humanitarian_scopes) or
            has_c19_tag(self.dactivity.tags) or
            has_c19_sector(self.dactivity.sectors) or
            is_c19_narrative(self.dactivity.title.narratives)
        ) else False

    def make_country_splits(self):
        return CalculateSplits.make_country_splits(self.dactivity)

    def make_sector_splits(self):
        return CalculateSplits.make_sector_splits(self.dactivity)

    @staticmethod
    def sum_transactions(transactions, types):
        total = 0
        for transaction in transactions:
            if transaction.value is None:
                continue
            elif transaction.type in types:
                total += convert_to_usd(transaction.value, transaction.currency, transaction.date)
        return total

    def humanitarian(self):
        return self.dactivity.humanitarian

    def process(self):
        transactions = list()
        flows = list()

        # Get the reporting-org name and C19 strictness at activity level
        org = self.get_reporting_org()
        org_type = self.get_org_type()
        activity_strict = self.is_strict()

        # Figure out default country/sector percentage splits at the activity level
        activity_country_splits = self.make_country_splits()
        activity_sector_splits = self.make_sector_splits()

        #
        # Figure out how to factor new money
        #

        # Total up the 4 kinds of transactions (with currency conversion to USD)
        incoming_funds = self.sum_transactions(self.dactivity.transactions, ['1'])
        outgoing_commitments = self.sum_transactions(self.dactivity.transactions, ['2'])
        spending = self.sum_transactions(self.dactivity.transactions, ['3', '4'])
        incoming_commitments = self.sum_transactions(self.dactivity.transactions, ['11'])

        # Figure out total incoming money (never less than zero)
        incoming = max(incoming_commitments, incoming_funds)
        if incoming < 0:
            incoming = 0

        # Factor to apply to outgoing commitments for net new money
        if incoming == 0:
            commitment_factor = 1.0
        elif outgoing_commitments > incoming:
            commitment_factor = (outgoing_commitments - incoming) / outgoing_commitments
        else:
            commitment_factor = 0.0

        # Factor to apply to outgoing spending for net new money
        if incoming == 0:
            spending_factor = 1.0
        elif spending > incoming:
            spending_factor = (spending - incoming) / spending
        else:
            spending_factor = 0.0

        #
        # Walk through the activity's transactions one-by-one, and split by country/sector
        #
        for dtransaction in self.dactivity.transactions:
            transaction = Transaction(self.configuration, self.this_month, dtransaction)

            if not transaction.should_process():
                continue

            # Convert the transaction value to USD
            value = transaction.calculate_value()

            # Set the net (new money) factors based on the type (commitments or spending)
            net_value = transaction.get_net_value(commitment_factor, spending_factor)

            # transaction status defaults to activity
            transaction_humanitarian = transaction.humanitarian()
            if transaction_humanitarian is None:
                is_humanitarian = self.humanitarian()
            else:
                is_humanitarian = transaction_humanitarian
            is_strict = activity_strict or transaction.is_strict()

            # Make the splits for the transaction (default to activity splits)
            country_splits = transaction.make_country_splits(activity_country_splits)
            sector_splits = transaction.make_sector_splits(activity_sector_splits)

            classification, direction = transaction.get_classification_direction()

            # Apply the country and sector percentage splits to the transaction
            # generate multiple split transactions
            for country, country_percentage in country_splits.items():
                for sector, sector_percentage in sector_splits.items():

                    sector_name = Lookups.get_sector_group_name(sector)
                    country_name = Lookups.get_country_name(country)

                    #
                    # Add to transactions
                    #

                    total_money = int(round(value * country_percentage * sector_percentage))
                    if net_value is not None:
                        net_money = int(round(net_value * country_percentage * sector_percentage))

                        # Fill in only if we end up with a non-zero value
                        if net_money != 0 or total_money != 0:
                            # add to transactions
                            transactions.append([
                                transaction.get_month(),
                                org,
                                org_type,
                                sector_name,
                                country_name,
                                1 if is_humanitarian else 0,
                                1 if is_strict else 0,
                                classification,
                                self.identifier,
                                net_money,
                                total_money,
                            ])

                #
                # Add to flows
                #
                provider, receiver = transaction.get_provider_receiver()
                if org != provider and org != receiver and org != Lookups.default_org:
                    # ignore internal transactions or unknown reporting orgs
                    flows.append([
                        org,
                        org_type,
                        provider,
                        receiver,
                        1 if is_humanitarian else 0,
                        1 if is_strict else 0,
                        classification,
                        direction,
                        total_money
                    ])
        return transactions, flows