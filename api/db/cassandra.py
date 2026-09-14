import os

from cassandra.cluster import Cluster


cluster: Cluster | None = None
session = None


def init_cassandra():
    global cluster, session

    if cluster is None:
        cluster = Cluster(
            [os.getenv("CASSANDRA_HOST", "timeseries-db")],
            port=int(os.getenv("CASSANDRA_PORT", "9042")),
        )

        session = cluster.connect("gridsense")

    return session


def get_cassandra_session():
    if session is None:
        raise RuntimeError("Cassandra session has not been initialized")

    return session


def close_cassandra():
    global cluster, session

    if cluster is not None:
        cluster.shutdown()
        cluster = None
        session = None
