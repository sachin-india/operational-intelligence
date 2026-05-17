import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "opint123")

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://opint:opint123@localhost:5432/opint",
)
