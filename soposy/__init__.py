import argparse
import datetime
import os.path
import pytz
import sqlite3

import xdg.BaseDirectory

from soposy.connectors import (Console,
                               Facebook,
                               FivehundredPx,
                               Pinterest,
                               Twitter)
from soposy.config import parse_config

CONNECTORS = [
    Console,
    Facebook,
    FivehundredPx,
    Twitter,
    Pinterest,
]

DATABASE_FILE = 'data.sqlite'
DEFAULT_CONFIG_FILE = os.path.join(
    xdg.BaseDirectory.save_config_path('soposy'), 'config.ini')


def open_db():
    return sqlite3.connect(
        os.path.join(xdg.BaseDirectory.save_data_path('soposy'),
                     DATABASE_FILE))


def init_database(conn):

    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS SYNCED_ITEMS ('
                     '  workflow  VARCHAR(140) NOT NULL,'
                     '  connector VARCHAR(140) NOT NULL,'
                     '  entryId   VARCHAR(255) NOT NULL,'
                     '  createdAt INTEGER      NOT NULL,'
                     '  synced    INTEGER      NOT NULL,'
                     '  PRIMARY KEY (workflow, connector, entryId)'
                     ');')
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS SYNC_DONE ('
                     '  workflow  VARCHAR(140) NOT NULL,'
                     '  connector VARCHAR(140) NOT NULL,'
                     '  PRIMARY KEY (workflow, connector)'
                     ');')


def mark_as_processed(workflow, source, entry, timestamp, conn):
    conn.execute(
        """DELETE FROM SYNCED_ITEMS
               WHERE workflow=? AND connector=? AND entryId=?""",
        (workflow, source, str(entry.uniqueId)))
    conn.execute("INSERT INTO SYNCED_ITEMS VALUES (?, ?, ?, ?, ?)",
                 (workflow, source, str(entry.uniqueId),
                  int(entry.created_at.timestamp()),
                  int(timestamp.timestamp())))


def action_initial_sync(args, config, conn):
    print('Initial sync')

    now = datetime.datetime.now(pytz.utc)
    for workflow in config.workflows.values():
        print(workflow.name)

        source = workflow.source.create()

        with conn:
            for entry in source.entries(now -
                                        datetime.timedelta(days=args.max_gap)):
                print(entry.uniqueId)
                mark_as_processed(workflow.name, source.name, entry, now, conn)

            conn.execute("""INSERT INTO SYNC_DONE(workflow, connector)
                            SELECT :workflow, :connector
                            WHERE NOT EXISTS(SELECT 1 FROM SYNC_DONE
                                WHERE workflow=:workflow
                                AND connector=:connector)""",
                         {'workflow': workflow.name,
                          'connector': source.name})


def action_sync(args, config, conn):

    with conn:
        # first, ensure that all configured workflows had an initial sync
        for workflow in config.workflows.values():
                rows = conn.execute(
                    """SELECT COUNT(*) FROM SYNC_DONE
                           WHERE workflow=? AND connector=?""",
                    (workflow.name, workflow.source.name)).fetchone()[0]
                if rows < 1:
                    raise RuntimeError(
                        'Source {} lacks initial sync'.format(
                            workflow.source.name))

        # iterate all workflows
        now = datetime.datetime.now(pytz.utc)
        max_horizon = now - datetime.timedelta(days=args.max_gap)
        for workflow in config.workflows.values():
            print(workflow.name)

            source = workflow.source.create()

            # get time of most recent sync
            res = conn.execute("""SELECT createdAt FROM SYNCED_ITEMS
                                  WHERE workflow=?  AND connector=?
                                  ORDER BY createdAt DESC
                                  LIMIT 1""",
                               (workflow.name, source.name)).fetchone()
            if res:
                last_sync = pytz.utc.localize(
                    datetime.datetime.utcfromtimestamp(res[0]))
            else:
                last_sync = max_horizon
            horizon = max(max_horizon, last_sync)
            print("  Syncing up to {}".format(horizon))

            targets = [t.create() for t in workflow.targets]

            # process all matching entries
            for entry in source.entries(horizon):
                print(entry.uniqueId)

                # ensure that this entry was really not processed before
                res = conn.execute(
                    """SELECT COUNT(*) FROM SYNCED_ITEMS
                           WHERE workflow=? AND connector=? AND entryId=?""",
                    (workflow.name, source.name,
                     str(entry.uniqueId))).fetchone()[0]
                if res > 0:
                    print("  Skipping already processed entry {}".format(
                        entry.uniqueId))
                    continue

                # push new entry to all targets
                for target in targets:
                    target.push(entry)

                # mark entry as being processed
                mark_as_processed(workflow.name, source.name, entry, now, conn)


def parse_arguments(argv=None):
    """Parses the command line arguments."""

    parser = argparse.ArgumentParser(prog='soposy')

    # global options
    parser.add_argument(
        '-c', '--config',
        type=argparse.FileType(),
        metavar='FILE',
        required=not os.path.isfile(DEFAULT_CONFIG_FILE),
        default=open(DEFAULT_CONFIG_FILE)
                if os.path.isfile(DEFAULT_CONFIG_FILE)
                else None,
        help='Use the specified configuration file instead of the default.')
    parser.add_argument(
        '--maxgap',
        metavar='DAYS',
        dest='max_gap',
        type=int,
        default=31,
        help='Assumed maximum gap between sync runs in days.')

    # connector subcommands
    subparsers = parser.add_subparsers(title='Subcommands')
    for connector in CONNECTORS:
        connector.register_parser(subparsers)

    # global subcommands
    parser_init = subparsers.add_parser(
        'init', description='Initial sync without posting anything')
    parser_init.set_defaults(action=action_initial_sync)
    parser_sync = subparsers.add_parser(
        'sync', description='synchronize potentially new entries')
    parser_sync.set_defaults(action=action_sync)

    return parser.parse_args(args=argv)


def main(argv=None):
    args = parse_arguments(argv)

    config = parse_config(args.config)

    conn = open_db()
    init_database(conn)

    try:
        args.action(args, config, conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
