CREATE OR REPLACE VIEW chain_moonbeam_moonbase_alpha._proof_chain_specimen_events AS
WITH
session_started_events AS (
  SELECT session_started.tx_hash AS observer_chain_tx_hash,
    session_started.block_id AS observer_chain_block_id,
    session_started.tx_offset AS observer_chain_tx_offset,
    session_started.topics[2]::numeric AS origin_chain_id,
    session_started.topics[3]::numeric AS origin_chain_block_height,
    abi_field(session_started.data, 0)::numeric AS proof_session_deadline
  FROM chain_moonbeam_moonbase_alpha.block_log_events session_started
  JOIN chain_moonbeam_moonbase_alpha.block_transactions trx
    ON (trx.block_id = session_started.block_id AND trx.tx_offset = session_started.tx_offset)
  WHERE
    session_started.sender = '\x1BFa3b5E9bE2c5298B7DE11B5Acb08c37683f4eF'::bytea
    AND session_started.topics @> ARRAY[
      '\x8b1f889addbfa41db5227bae3b091bd5c8b9a9122f874dfe54ba2f75aabe1f4c'::bytea
    ]
    AND trx.successful = TRUE
    AND session_started.block_id >= '1910104892088990000'::bigint
  ORDER BY session_started.block_id ASC, session_started.log_offset ASC
),
specimen_reward_awarded_events AS (
  SELECT
    fin.tx_hash AS observer_chain_tx_hash,
    fin.topics[2]::numeric AS origin_chain_id,
    fin.topics[3]::numeric AS origin_chain_block_height
  FROM chain_moonbeam_moonbase_alpha.block_log_events fin
  JOIN chain_moonbeam_moonbase_alpha.block_transactions trx_1
    ON (trx_1.block_id = fin.block_id AND trx_1.tx_offset = fin.tx_offset)
  WHERE
    fin.sender = '\x1BFa3b5E9bE2c5298B7DE11B5Acb08c37683f4eF'::bytea
    AND fin.topics @> ARRAY['\xf05ac779af1ec75a7b2fbe9415b33a67c00294a121786f7ce2eb3f92e4a6424a'::bytea]
    AND trx_1.successful = TRUE
    AND fin.block_id >= '1910104892088990000'::bigint
  ORDER BY fin.block_id ASC, fin.log_offset ASC
),
specimen_quorum_not_reached_events AS (
  SELECT
    fin.tx_hash AS observer_chain_tx_hash,
    fin.topics[2]::numeric AS origin_chain_id,
    public.abi_field(fin.data, 0)::numeric AS origin_chain_block_height
  FROM chain_moonbeam_moonbase_alpha.block_log_events fin
  JOIN chain_moonbeam_moonbase_alpha.block_transactions trx_1
    ON (trx_1.block_id = fin.block_id AND trx_1.tx_offset = fin.tx_offset)
  WHERE
    fin.sender = '\x1BFa3b5E9bE2c5298B7DE11B5Acb08c37683f4eF'::bytea
    AND fin.topics @> ARRAY['\x8340aa7a5b37153230f8b64fa66f25c843e5002c60e63a25db6a9195005ccabd'::bytea]
    AND trx_1.successful = TRUE
    AND fin.block_id >= '1910104892088990000'::bigint
  ORDER BY fin.block_id ASC, fin.log_offset ASC
),
all_finalization_events AS (
  SELECT * FROM specimen_reward_awarded_events
  UNION ALL
  SELECT * FROM specimen_quorum_not_reached_events
)
SELECT
  sse.observer_chain_tx_hash AS observer_chain_session_start_tx_hash,
  sse.observer_chain_block_id AS observer_chain_session_start_block_id,
  sse.observer_chain_tx_offset AS observer_chain_session_start_tx_offset,
  sse.origin_chain_id,
  sse.origin_chain_block_height,
  sse.proof_session_deadline,
  afe.observer_chain_tx_hash AS observer_chain_finalization_tx_hash
FROM session_started_events sse
LEFT JOIN all_finalization_events afe ON (
  sse.origin_chain_id = afe.origin_chain_id
  AND sse.origin_chain_block_height = afe.origin_chain_block_height
)
WHERE sse.origin_chain_block_height > 17374020::numeric
ORDER BY sse.observer_chain_block_id ASC, sse.observer_chain_tx_offset ASC
;
