"""convert ohlcv to timescaledb hypertable

Revision ID: 0002_hypertable
Revises: 1e3eb60714a3
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_hypertable"
down_revision: Union[str, None] = "1e3eb60714a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop surrogate PK — TimescaleDB requires time column in all unique constraints
    op.drop_constraint("ohlcv_pkey", "ohlcv", type_="primary")
    op.drop_column("ohlcv", "id")

    # Promote the existing unique constraint to primary key
    op.drop_constraint("uq_ohlcv_symbol_tf_ts", "ohlcv", type_="unique")
    op.create_primary_key("ohlcv_pkey", "ohlcv", ["symbol", "timeframe", "timestamp"])

    # Convert to hypertable (chunk interval = 7 days)
    op.execute(
        "SELECT create_hypertable('ohlcv', 'timestamp', "
        "chunk_time_interval => INTERVAL '7 days', "
        "migrate_data => true)"
    )


def downgrade() -> None:
    # Note: converting back from hypertable is not trivially reversible.
    # This downgrade creates a regular table with the same data.
    op.execute(
        """
        CREATE TABLE ohlcv_backup AS SELECT * FROM ohlcv;
        DROP TABLE ohlcv;
        CREATE TABLE ohlcv (
            id BIGSERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            timeframe VARCHAR(5) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            CONSTRAINT uq_ohlcv_symbol_tf_ts UNIQUE (symbol, timeframe, timestamp)
        );
        INSERT INTO ohlcv (symbol, timeframe, timestamp, open, high, low, close, volume)
        SELECT symbol, timeframe, timestamp, open, high, low, close, volume FROM ohlcv_backup;
        DROP TABLE ohlcv_backup;
        CREATE INDEX ix_ohlcv_symbol ON ohlcv (symbol);
        CREATE INDEX ix_ohlcv_timestamp ON ohlcv (timestamp);
        """
    )
