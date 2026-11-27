# Logical Replication Slots, WAL Retention, and Progress Monitoring in PostgreSQL

## 1. Why are logical replication slots important?

Logical replication allows PostgreSQL to emit data changes at a logical level so a subscriber or CDC system can receive and apply them. Unlike physical streaming replication, logical replication transmits changes for objects selected by a publication, such as INSERT, UPDATE, DELETE, and TRUNCATE on published tables.

A logical replication slot retains WAL decoding state for a consumer. The slot tells PostgreSQL how far the consumer has confirmed and what oldest WAL position may still be required to continue logical decoding. As a result, the publisher does not remove WAL that the consumer has not yet processed.

This mechanism enables a consumer to resume reading changes after an interruption, but introduces an operational risk: if the consumer stops reading, the slot can retain an ever-growing amount of WAL in the `pg_wal` directory. If disk fills up, the primary cannot write new WAL and the entire write workload is impacted.

To operate safely, monitor all of the following together:

- Whether the slot is active and which consumer is using it.
- `restart_lsn`: the oldest WAL position still potentially needed for decoding.
- `confirmed_flush_lsn`: the position confirmed by the consumer.
- `xmin` and `catalog_xmin`: transaction/catalog horizons retained by the slot.
- Estimated WAL bytes currently retained and disk headroom.
- Send, receive, apply, and initial table synchronization progress.
- Error counters, slot invalidation, and time since last consumer progress.
- Post-failover state and consumer recovery capability.

```text
              PUBLISHER (wal_level = logical)
                         |
                 WAL records / changes
                         |
                         v
                 LOGICAL SLOT
            restart_lsn / confirmed_flush_lsn
                 xmin / catalog_xmin
                         |
                         v
                Logical decoding
                         |
              +----------+-----------+
              |                      |
              v                      v
        PostgreSQL              CDC connector
        subscriber              / event pipeline
              |                      |
              v                      v
        Apply changes          Persist downstream
              |                      |
              +----------+-----------+
                         |
                         v
                Consumer feedback
                         |
                         v
              Slot progress advances
                         |
                         v
                WAL can be recycled
```

## 2. Learning objectives

After this lesson, you will be able to:

1. Explain how a logical replication slot protects WAL.
2. Distinguish logical slots from physical replication slots.
3. Understand `restart_lsn`, `confirmed_flush_lsn`, `xmin`, and `catalog_xmin`.
4. Create a logical slot and associate it with a subscription or CDC consumer.
5. Understand the relationship between `wal_level`, `max_replication_slots`, and `max_wal_senders`.
6. Read slot status via `pg_replication_slots`.
7. Estimate WAL retained by a slot.
8. Distinguish WAL retention from transaction/catalog tuple retention.
9. Understand the impact of long-running and uncommitted transactions.
10. Explain `max_slot_wal_keep_size` and slot WAL status.
11. Distinguish `max_wal_size`, `wal_keep_size`, and slot retention.
12. Monitor logical replication senders on the publisher.
13. Monitor apply workers and table synchronization on the subscriber.
14. Read `pg_stat_subscription`, `pg_subscription_rel`, and replication origin status.
15. Monitor apply/sync errors and logical decoding spill when supported by the version.
16. Distinguish received LSN, confirmed LSN, restart LSN, and replay/apply progress.
17. Handle inactive slots, consumer lag, and disk pressure.
18. Understand the consequences when a slot becomes invalidated or loses needed WAL.
19. Design alerts and runbooks for CDC/replication consumers.
20. Verify progress and recoverability through lab/restore drills.

## 3. How does a logical replication slot work?

### 3.1. WAL is the data source for logical decoding

Every change requiring durability is written by PostgreSQL to WAL. With `wal_level = logical`, WAL contains sufficient information for logical decoding to reconstruct the logical changes supported by the output plugin.

Logical decoding reads WAL, interprets records into changes, and sends them through an output plugin. The consumer receives the changes, writes them to the target, and sends feedback so the publisher knows up to where data has been safely processed.

### 3.2. The slot holds decoding state

A logical slot stores state so the next read resumes at the exact position and retains metadata required for decoding. If the consumer temporarily disconnects, the slot persists and the publisher retains needed WAL for the consumer's return, as long as retention limits and storage allow.

### 3.3. A slot is not a copy of the database

A slot does not store a full database copy, replace backups, or push changes to a consumer by itself. It holds decoding position/state and associated horizons.

### 3.4. Each consumer needs its own progress tracking

One slot represents one progress stream. If multiple independent consumers read from the same slot, feedback from one consumer can advance the slot past changes the other consumer has not yet processed. Use a dedicated slot for each independent consumer.

Example:

- One slot for subscription `orders_sub`.
- Another slot for a Debezium connector.
- Another slot for an analytics pipeline.

Do not share one slot across two systems simply because they need the same publication.

### 3.5. Slots are database-scoped

A logical slot is tied to a single database on the publisher and a single output plugin. It does not represent a single logical stream across all databases in the cluster. When managing multiple databases, inventory slots by database and consumer.

## 4. Differences between logical slots and physical slots

| Criterion | Logical replication slot | Physical replication slot |
| --- | --- | --- |
| Purpose | Retains WAL for logical decoding to emit changes | Retains WAL for a physical standby |
| Consumer | Subscription or CDC client | Physical standby |
| Transmitted content | Logical changes per output plugin/publication | WAL to reconstruct physical state |
| `confirmed_flush_lsn` | Meaningful for logical consumers | Typically NULL |
| `restart_lsn` | Oldest WAL potentially needed for decoding | Oldest WAL needed for standby |
| `xmin` / `catalog_xmin` | Can retain tuple/catalog horizons | Typically does not use logical decoding semantics |
| Recovering one table | Consumer can filter/apply logically | Does not provide a table-level stream |
| Retention risk | WAL and tuple/catalog retention | WAL retention |

A slot can persist long after a consumer disconnects. Therefore, an inactive slot does not mean a harmless slot.

## 5. Publisher configuration prerequisites

### 5.1. wal_level = logical

The publisher must use a WAL level supporting logical decoding:

```conf
wal_level = logical
```

`wal_level` requires a server restart to change in common PostgreSQL versions. Check the active value:

```sql
SHOW wal_level;
```

If `wal_level` is not yet `logical`, logical replication slot/publication workflows will not function as expected.

### 5.2. max_replication_slots

Set sufficient slot capacity for subscribers, CDC consumers, and other logical slots:

```conf
max_replication_slots = 20
```

The actual value depends on consumer count and reserve slots. This is a server capacity limit, not a license to create arbitrary unused slots.

### 5.3. max_wal_senders

Logical replication uses WAL sender processes to transmit changes:

```conf
max_wal_senders = 20
```

Account for physical standbys and other replication connections as well. Do not set it equal to only the subscriber count if the system also has physical replicas, backup connections, or CDC clients.

### 5.4. Connectivity and privileges

The consumer needs an appropriate replication connection and a role with required privileges. `pg_hba.conf` must permit connections from the proper hosts, database, and user. Prefer a dedicated role with least privilege.

### 5.5. Checking settings together

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_slot_wal_keep_size'
)
ORDER BY name;
```

Some parameters or columns depend on the major version. If a row is missing, check your version and its documentation.

## 6. Creating a logical replication slot

### 6.1. Slot for a logical decoding client

You can create a slot directly via SQL:

```sql
SELECT *
FROM pg_catalog.pg_create_logical_replication_slot(
    'orders_cdc_slot',
    'pgoutput'
);
```

`pgoutput` is the output plugin used by PostgreSQL for the native logical replication protocol. A CDC client must understand the corresponding protocol and feedback semantics.

### 6.2. Slot for a native subscription

A subscription can usually create its slot on the publisher automatically:

```sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.internal port=5432 dbname=appdb user=repl_user'
PUBLICATION orders_publication
WITH (
    create_slot = true,
    enabled = true
);
```

In this example, PostgreSQL manages the slot linked to the subscription per the corresponding name/options. Inspect the actual subscription and slot after creation. Do not pre-create a slot with the same name if `create_slot = true` will attempt to create a new slot.

### 6.3. Creating a subscription using an existing slot

When a slot has already been created, a subscription can be configured to use it with appropriate options, such as `create_slot = false` and an explicit `slot_name`. Ensure the slot exists, belongs to the right database, and is not used by another consumer.

### 6.4. Output plugins

The output plugin determines how logical changes are encoded. `pgoutput` serves the native logical replication protocol. `test_decoding` is a plugin often used in labs to view text output when installed.

Do not assume every PostgreSQL installation includes the exact same plugins. Check packages/extensions and server permissions.

### 6.5. One slot per independent consumer

Each consumer needs its own progress tracking and retention. If CDC pipeline A stalls, it should not cause consumer B to lose changes or receive consumer B's feedback.

## 7. Key LSNs of a logical slot

### 7.1. restart_lsn

`restart_lsn` is the oldest WAL position the slot may still need to continue decoding. The publisher must retain WAL from this needed position onward.

If `restart_lsn` remains stationary while the current WAL LSN continues advancing, the amount of WAL retained can grow.

### 7.2. confirmed_flush_lsn

For a logical slot, `confirmed_flush_lsn` is the position the consumer has confirmed as flushed/processed per the feedback protocol. It reflects consumer progress acknowledged to the publisher.

Do not interpret this to mean every event has finished downstream business processing if the consumer acknowledges immediately after writing to a queue or intermediate layer. Safety semantics depend on how the consumer persists data before sending feedback.

### 7.3. restart_lsn and confirmed_flush_lsn are not necessarily equal

`confirmed_flush_lsn` can advance ahead of `restart_lsn`. Logical decoding may still need older WAL due to open transactions, decoding state, or other internal requirements.

Thus, looking solely at `confirmed_flush_lsn` can miss growing WAL retention.

### 7.4. xmin

`xmin` is the transaction horizon a slot can hold to prevent VACUUM from removing tuple versions still needed for decoding. This is a different form of retention from retaining WAL files.

### 7.5. catalog_xmin

`catalog_xmin` retains catalog rows required for logical decoding. If the catalog horizon is old, vacuuming on system catalogs may be constrained.

### 7.6. No single column describes overall health

A slot can be:

- Active yet making no progress.
- Inactive yet still retaining WAL.
- Showing a recent `confirmed_flush_lsn` while `restart_lsn` is old.
- Holding back `xmin`/`catalog_xmin` even before WAL retention becomes large.
- Missing needed WAL and unable to resume.

You must inspect the full state, consumer health, and disk trend.

## 8. Reading pg_replication_slots

This is the primary view for inventorying slots on the publisher:

```sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn,
    temporary
FROM pg_catalog.pg_replication_slots
ORDER BY slot_type, slot_name;
```

### 8.1. Key columns

| Column | Meaning |
| --- | --- |
| `slot_name` | Slot name |
| `plugin` | Output plugin of a logical slot |
| `slot_type` | `logical` or `physical` |
| `database` | Database associated with the logical slot |
| `active` | Whether the slot is currently in use by a consumer |
| `active_pid` | PID of the backend holding the slot active |
| `xmin` | Transaction horizon held by the slot |
| `catalog_xmin` | Catalog horizon held by the slot |
| `restart_lsn` | Oldest WAL position potentially still needed |
| `confirmed_flush_lsn` | Confirmed logical consumer progress |
| `temporary` | Temporary slot, lacking persistence of regular slots |

Some columns exist only in newer PostgreSQL versions. Check your running major version's catalog before deploying a shared query dashboard across multiple versions.

### 8.2. Finding inactive slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    plugin,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin
FROM pg_catalog.pg_replication_slots
WHERE NOT active
ORDER BY slot_name;
```

Inactive slots require investigation: is the consumer undergoing maintenance, failing, removed on the application side, or forgotten?

### 8.3. Matching active slots to backends

```sql
SELECT
    s.slot_name,
    s.slot_type,
    s.database,
    s.active,
    s.active_pid,
    a.usename,
    a.application_name,
    a.client_addr,
    a.state,
    a.backend_type,
    a.query_start
FROM pg_catalog.pg_replication_slots AS s
LEFT JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = s.active_pid
ORDER BY s.slot_name;
```

`active_pid` can be NULL when a slot is inactive. Set meaningful `application_name` values to accurately identify each CDC service or subscriber.

## 9. Estimating WAL retained by a slot

### 9.1. Calculating distance from current WAL to restart_lsn

On the publisher, you can estimate the WAL span behind `restart_lsn`:

```sql
SELECT
    slot_name,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_wal_span
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC NULLS LAST;
```

This represents a span of WAL address space, not an exact measurement of bytes exclusively belonging to one slot. Multiple slots may overlap on the same segments, and other WAL records also reside in that span.

### 9.2. Tracking trends instead of a single snapshot

Record periodically:

- Current WAL LSN.
- Each slot's `restart_lsn`.
- `confirmed_flush_lsn`.
- Estimated WAL span.
- Slot active/inactive state.
- WAL directory disk usage.
- WAL generation rate.

A steadily growing WAL span signals that the consumer is falling behind or decoding is pinned by another transaction.

### 9.3. Inspecting the WAL directory

Some environments permit calling `pg_ls_waldir()` to measure file count and size:

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_catalog.pg_ls_waldir();
```

Permission to call this function depends on role and version. This is the total size of the WAL directory, which cannot be attributed entirely to a single logical slot.

### 9.4. Do not mechanically sum retention estimates across slots

Slots can share overlapping WAL ranges. Summing each `estimated_wal_span` double-counts segments and exaggerates total size. Use it to rank which slot holds the oldest horizon, while disk metrics provide the true storage measurement.

### 9.5. Disk headroom matters more than status labels

A slot may not have crossed a retention cap while the WAL directory still nears full due to heavy WAL workload, archive backlog, physical slots, or checkpoint behavior. Always monitor filesystem capacity.

## 10. max_slot_wal_keep_size and retention limits

### 10.1. Unlimited retention

In supported versions, `max_slot_wal_keep_size = -1` means no cap is placed on the WAL volume retained by replication slots. This is a common default.

If a consumer stops for an extended time, the slot can retain WAL indefinitely until storage fills up.

### 10.2. Setting a limit

Example:

```conf
max_slot_wal_keep_size = '20GB'
```

This limit protects storage from a permanently stalled slot. However, when the limit is exceeded, PostgreSQL may recycle needed WAL and the slot becomes unusable for resuming from its old position.

### 10.3. Limits are enforced at checkpoints

The slot WAL retention limit is checked during checkpoints, rather than acting as an exact per-byte hard quota enforced instantaneously. WAL can temporarily exceed the limit before a checkpoint runs.

### 10.4. Slots can become invalidated

Once needed WAL has been recycled, the logical consumer can no longer resume decoding from the old `restart_lsn`. Inspect slot status and logs. Typically, you must create a new slot and perform a resnapshot/resync or a connector-compatible recovery procedure.

### 10.5. wal_status and safe_wal_size

Newer PostgreSQL versions may provide `wal_status` and `safe_wal_size` in `pg_replication_slots`.

- `reserved`: needed WAL remains within the retained range.
- `extended`: the slot is causing PostgreSQL to retain WAL beyond `max_wal_size`.
- `unreserved`: WAL is no longer guaranteed to be kept, though some segments may still exist.
- `lost`: needed WAL has been removed; the slot cannot continue as before.
- `safe_wal_size`: estimated bytes that can still be written before the slot risks losing WAL, when supported by settings/version.

Exact values and columns depend on version. When available, add them to your dashboard:

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical';
```

### 10.6. max_slot_wal_keep_size is not a recovery plan

Setting a limit only defines how much WAL retention is permitted. It does not create backups, resync consumers, or prevent downstream data loss. You must have a runbook for handling a lost slot.

## 11. Distinguishing max_wal_size, wal_keep_size, and slot retention

| Setting | Purpose | Changes slot WAL limit? |
| --- | --- | --- |
| `max_wal_size` | Soft target for WAL/checkpoint behavior | No |
| `wal_keep_size` | Retains a minimum WAL volume for standby streaming per its mechanism | Does not alter slot-specific retention |
| `max_slot_wal_keep_size` | Caps WAL retained by replication slots | Yes |
| `archive_timeout` | Forces WAL segment switch on interval when eligible activity occurs | No |

`max_wal_size` is not a hard cap on the WAL directory; replication slots and archiving can make the WAL directory grow larger. Never shrink `max_wal_size` to fix a stuck logical slot.

`wal_keep_size` provides physical standbys a buffer of WAL in certain situations, whereas logical slots must be managed via slot retention settings and consumer progress.

## 12. Why can restart_lsn stop advancing?

### 12.1. Consumer stops acknowledging

A CDC connector may disconnect, crash, or be paused. Without new feedback, the slot cannot advance its confirmed position.

### 12.2. Consumer reads without persisting downstream

A consumer might read changes without durably writing them to the destination. Until flush feedback is sent, the publisher must retain the data. This is safe behavior: consumers should acknowledge only after persisting data per the pipeline's durability contract.

### 12.3. Long-running transaction on the publisher

A long-running write transaction that has not committed can force logical decoding to keep older WAL. Even if the consumer has confirmed most of the stream, `restart_lsn` remains pinned by the unfinished transaction.

### 12.4. Large transactions and decoding spill

A large transaction can generate many changes before committing. Logical decoding must maintain state for that transaction. When exceeding `logical_decoding_work_mem`, decoding data may spill to disk per the version's supported mechanism. Spilling impacts I/O and decoding performance, while WAL retention depends on the positions needed for the transaction.

### 12.5. Unused orphaned slot

A slot left behind after a connector is removed can retain WAL indefinitely if no limit is set. Identify the owner and lifecycle before dropping.

### 12.6. Catalog/tuple horizons

Even if the WAL span is modest, an old `xmin` or `catalog_xmin` can prevent VACUUM from reclaiming tuple/catalog versions. Monitor both types of retention independently.

## 13. Monitoring logical replication on the publisher

### 13.1. pg_stat_replication

The `pg_stat_replication` view displays directly connected WAL senders. For logical replication, you can observe application name, state, and reported LSN positions:

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 13.2. Interpret cautiously

The LSN and lag columns in `pg_stat_replication` help inspect sender/receiver feedback, though detailed semantics differ between physical and logical replication and across PostgreSQL versions. Do not equate a logical subscriber's `replay_lsn` with all downstream business processing steps.

### 13.3. Seeing no sender does not mean the slot was deleted

`pg_stat_replication` shows only active sender connections. An inactive slot can still exist in `pg_replication_slots` and continue retaining WAL.

### 13.4. application_name

Set a clear `application_name` in the CDC connector or subscriber connection string. If all clients use generic or default names, matching senders to slot owners becomes difficult.

## 14. Monitoring subscribers with pg_stat_subscription

### 14.1. Basic view

On the subscriber:

```sql
SELECT
    subid,
    subname,
    pid,
    relid,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_subscription
ORDER BY subname, relid;
```

### 14.2. Column meanings

| Column | Meaning |
| --- | --- |
| `subname` | Subscription |
| `pid` | Worker PID |
| `relid` | Related table if the worker is syncing a relation |
| `received_lsn` | Most recent WAL position received per the view |
| `last_msg_send_time` | Timestamp when the last message was sent by sender |
| `last_msg_receipt_time` | Timestamp when the subscriber received the last message |
| `latest_end_lsn` | Latest end LSN reported in feedback |
| `latest_end_time` | Timestamp when latest end/feedback was recorded |

`received_lsn` and `latest_end_lsn` do not automatically prove every change has been processed by downstream business services. Combine them with replication origin and data verification on the subscriber.

### 14.3. Multiple workers

A subscription can have an apply worker and table synchronization workers. A row with a non-null `relid` represents a worker syncing a specific relation; the main apply worker typically has a NULL `relid`. Worker types/counts and additional columns vary by version.

### 14.4. Missing PID

If `pid` is NULL or no row appears, the worker may not have started yet, has exited, the subscription is disabled, or it is encountering errors. Inspect `pg_subscription`, logs, and worker state.

### 14.5. Tracking last message time

If `last_msg_receipt_time` is stale while the publisher is writing WAL, there may be a network disconnect, sender failure, or unresponsive consumer. If the publisher has no workload, an old timestamp alone does not prove an error.

## 15. Monitoring per-table sync state

### 15.1. pg_subscription_rel

Initial table synchronization maintains per-table state in the `pg_subscription_rel` catalog.

```sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation,
    r.srsubstate,
    r.srsublsn
FROM pg_catalog.pg_subscription_rel AS r
JOIN pg_catalog.pg_subscription AS s
  ON s.oid = r.srsubid
ORDER BY s.subname, r.srrelid::regclass::text;
```

### 15.2. Common states

| State | Meaning |
| --- | --- |
| `i` | Initialize: synchronization starting |
| `d` | Data copy is in progress |
| `f` | Copy finished |
| `s` | Synchronizing / catching up |
| `r` | Ready: table is ready per subscription state |

Exact state transitions and displays depend on version. Use this catalog to identify tables that have not completed initial sync.

### 15.3. A subscription can be active while a table is not ready

The apply worker may be running for already-synchronized tables while another table remains in copy/catch-up state. Do not just verify the subscription exists and conclude the entire publication is fully replicated.

### 15.4. Table sync workers

During initial copy, PostgreSQL can run dedicated workers per table. Inspect `pg_stat_subscription.relid`, `pg_stat_activity`, and logs to see which relation is syncing.

### 15.5. pg_stat_progress_copy

In supported versions and execution paths, `pg_stat_progress_copy` can display COPY progress:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_catalog.pg_stat_progress_copy;
```

Not every table synchronization worker exposes useful `bytes_processed`/`bytes_total` values in every version. If `bytes_total` is unknown or no row appears, rely on table sync state, worker activity, and logs.

## 16. Monitoring replication origins on the subscriber

### 16.1. Origins track source position

Logical replication subscribers use replication origins to record progress applied from the source. `pg_replication_origin_status` shows the corresponding remote LSN and local LSN.

```sql
SELECT
    local_id,
    external_id,
    remote_lsn,
    local_lsn
FROM pg_catalog.pg_replication_origin_status
ORDER BY external_id;
```

### 16.2. remote_lsn

`remote_lsn` indicates the source position recorded by the origin. It is useful for reconciling against the publisher slot and subscription status.

### 16.3. local_lsn

`local_lsn` is the local WAL position associated with origin progress on the subscriber. It is not in the same LSN space as the remote publisher.

### 16.4. Never subtract LSNs from two different clusters

Do not call `pg_wal_lsn_diff(remote_lsn, local_lsn)` to measure lag; the two LSNs belong to two separate WAL streams. Compare each position against its proper source/destination metadata.

### 16.5. Origin names and topology

With multiple publishers or cascading pipelines, map `external_id` to the subscription/source identity. Do not infer solely from numeric `local_id`.

## 17. Monitoring apply and sync errors

### 17.1. Logs are primary evidence for specific errors

Logical replication workers can encounter:

- Unique or foreign key constraint violations.
- Schema or column mismatches.
- Permission errors.
- Network disconnects.
- Missing publications or tables.
- Conflicts caused by independent modifications on subscriber data.
- Lost slots or missing WAL.
- Serialization/type conversion errors.

Collect logs from both publisher and subscriber for the same timeframe to identify which side caused the error.

### 17.2. pg_stat_subscription_stats

Supported PostgreSQL versions provide `pg_stat_subscription_stats` to track error counters, such as apply errors and table synchronization errors:

```sql
SELECT *
FROM pg_catalog.pg_stat_subscription_stats;
```

Column names, availability, and reset behavior depend on version. For multi-version monitoring, check catalogs/views before fixing metric schemas.

### 17.3. pg_stat_activity

```sql
SELECT
    pid,
    backend_type,
    application_name,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS runtime,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type LIKE '%logical replication%'
   OR application_name ILIKE '%subscription%'
ORDER BY query_start;
```

`backend_type` and application names can differ across major versions and implementations. Supplement with logs if filters do not match.

### 17.4. Error counters do not replace logs

Counters show that errors incremented, but do not always contain the root cause, relation, or SQL details. Logs and subscription state are needed for diagnosis.

### 17.5. Resetting statistics

Counters can be reset. Store scrape history in your monitoring system and record reset timestamps so a drop in counters is not mistaken for resolved errors.

## 18. Logical decoding spill and performance

### 18.1. Large transactions

A large transaction can generate many changes before committing. The logical decoder must retain state to emit changes in proper order/transaction semantics.

### 18.2. logical_decoding_work_mem

The `logical_decoding_work_mem` parameter caps memory used by logical decoding before spilling state to disk per the version's supported mechanism:

```sql
SHOW logical_decoding_work_mem;
```

Increasing the value can reduce spilling at the cost of higher RAM consumption. Setting it too low can increase disk I/O.

### 18.3. Spill is not the same as WAL retention

Spill is temporary decoding data written to disk while processing large transactions. WAL retention is the publisher keeping WAL segments because a slot still needs them. Both issues can occur simultaneously, yet must be measured separately.

### 18.4. pg_stat_replication_slots

Newer PostgreSQL versions may provide `pg_stat_replication_slots` with metrics such as spilled/streamed transactions and bytes and total decoding activity. If the view exists on the server:

```sql
SELECT *
FROM pg_catalog.pg_stat_replication_slots;
```

Statistic columns and view availability depend on major version. Do not hard-code dashboards against a view absent on older servers.

### 18.5. Large workloads and streaming in-progress transactions

Certain logical replication/decoding modes can stream large transaction contents before the transaction commits, depending on version and configuration. This can avoid holding an entire transaction in memory, but does not remove WAL retention or commit semantics requirements.

## 19. Slot retention and vacuum horizons

### 19.1. Two types of retained resources

A logical slot can affect:

1. **WAL retention:** `restart_lsn` determines the oldest WAL potentially still needed.
2. **Tuple/catalog retention:** `xmin` and `catalog_xmin` can prevent VACUUM from removing row versions or catalog rows needed for decoding.

Resolving WAL disk pressure does not automatically release tuple/catalog horizons if the slot still holds `xmin`.

### 19.2. Impact on user tables

A slot holding an old `xmin` can keep dead tuples alive longer on tables with heavy write churn. Autovacuum can still run, but must preserve tuple versions not yet safe to remove.

### 19.3. Impact on system catalogs

`catalog_xmin` can retain catalog rows longer, increasing catalog bloat or hindering cleanup. Monitor slot horizons even when user tables show low dead-tuple estimates.

### 19.4. Inspecting slot horizons

```sql
SELECT
    slot_name,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

### 19.5. Do not ignore XID safety

A slot holding an old horizon can hinder vacuum/freeze progress. Monitor database/table XID age and anti-wraparound warnings; never wait until disk is full to act.

## 20. Inactive slots and WAL growth

### 20.1. Inactive does not mean obsolete

A slot may be inactive because the consumer is restarting, under maintenance, or experiencing a network outage. However, it can also be an orphaned slot from a deleted connector. Always identify the owner before acting.

### 20.2. Rapid WAL growth

If the workload generates WAL rapidly while a consumer makes no progress, the span from current LSN to `restart_lsn` widens. An inactive slot left for hours can retain many GBs or TBs depending on workload.

### 20.3. Estimating time to disk exhaustion

Track free disk space and WAL generation rate. You can estimate:

```text
time_to_full ≈ available_disk_bytes / net_wal_growth_bytes_per_second
```

This is an operational estimate. Net growth also depends on checkpoints, archiving, other slots, WAL recycling, and storage cleanup. Do not use a simple formula in place of real disk alerts.

### 20.4. WAL archiving can succeed while the WAL directory remains large

Successfully archiving WAL does not mean a slot has confirmed progress. PostgreSQL must still retain segments in the WAL directory for the slot even if an archived copy already exists on external storage.

### 20.5. Never delete WAL files manually

Never use filesystem deletes to free WAL managed by PostgreSQL. Doing so can break recovery/replication or render the server inoperable. Resolve via slots, retention settings, and PostgreSQL procedures.

## 21. Slots losing WAL or becoming invalidated

### 21.1. Symptoms

- `wal_status = lost` on versions featuring this column.
- Logs report the slot no longer has needed WAL or the slot was invalidated.
- Consumer reconnects but cannot resume from the previous position.
- Logical decoding errors because needed WAL is gone.

### 21.2. Skipped changes cannot be recovered

Once required WAL segments have been recycled, the slot cannot reconstruct changes from the lost WAL range. Increasing retention after losing WAL cannot bring deleted segments back.

### 21.3. Recreating the slot

You may need to drop/recreate the slot and perform an initial snapshot/resync or the CDC connector's dedicated bootstrap procedure. This can generate heavy load and requires avoiding duplicate/missing events via a controlled cutover checkpoint.

### 21.4. Verifying downstream consistency

After resyncing, compare row counts, keys, offsets/checkpoints, and event sequences. Seeing the connector transition to running is not sufficient verification.

### 21.5. Prevention

- Set appropriate retention limits.
- Alert early when `safe_wal_size` drops low.
- Monitor inactive slots and lag.
- Ensure consumers have proper retry/backoff logic.
- Maintain capacity for resnapshots.
- Never delete WAL or slots arbitrarily.

## 22. Managing slot lifecycles

### 22.1. Listing before creating

Check whether the slot name already exists and whether a consumer is using it. Slot names must be unique server-wide.

### 22.2. Dropping a slot

```sql
SELECT pg_catalog.pg_drop_replication_slot('orders_cdc_slot');
```

An active slot cannot be dropped. Before dropping, confirm the consumer is stopped and the owner approves losing the ability to resume from that slot.

### 22.3. Advancing a slot

PostgreSQL provides a function to advance a slot in supported versions:

```sql
SELECT *
FROM pg_catalog.pg_replication_slot_advance(
    'orders_cdc_slot',
    '0/16B6C50'::pg_lsn
);
```

Advancing a slot skips changes prior to the requested position per slot semantics. This operation can cause downstream data loss; use it only with an explicit checkpoint/resync plan.

### 22.4. SQL decoding functions in the lab

With a text-based output plugin such as `test_decoding` if installed, you can inspect changes:

```sql
SELECT *
FROM pg_catalog.pg_create_logical_replication_slot(
    'lab_text_slot',
    'test_decoding'
);

SELECT *
FROM pg_catalog.pg_logical_slot_peek_changes(
    'lab_text_slot',
    NULL,
    10
);
```

`peek_changes` reads without advancing the slot. `pg_logical_slot_get_changes` reads and consumes changes, advancing the slot. Do not use these SQL functions with output plugins/protocols that do not output text records as though all plugins behave identically.

### 22.5. Temporary slots

Temporary slots are tied to a session's lifecycle and lack persistence across disconnects. Never use a temporary slot for CDC pipelines needing to resume across restarts or disconnects.

## 23. Initial table synchronization

### 23.1. Logical replication includes an initial data copy phase

When a subscription is created with `copy_data = true` (the common default), PostgreSQL copies existing table data and then synchronizes changes generated during the copy.

### 23.2. Slots retain changes during copy

The publisher must retain WAL/changes so the subscriber can catch up with the initial snapshot. If initial sync takes a long time, WAL retention and storage pressure can grow.

### 23.3. Multiple tables can sync in parallel

Sync workers accelerate initialization but consume connections, CPU, I/O, and network. Tune `max_sync_workers_per_subscription` alongside `max_logical_replication_workers` based on version and workload.

### 23.4. Monitoring per-table status

Use `pg_subscription_rel` to determine which tables are initializing, copying, catching up, or ready. A subscription may still be completing initial sync even when the apply worker is running.

### 23.5. Initial copy can create heavy load

Copying entire tables can compete with production workloads. Plan for subscriber capacity, network bandwidth, locks, and catch-up time.

## 24. Native logical replication does not replicate everything

### 24.1. DDL

Native logical replication focuses on row changes. Schema/DDL changes generally must be deployed separately on the subscriber via a migration workflow.

### 24.2. Sequences

Sequence state is not replicated like ordinary row changes. During cutover, synchronize sequence values through an appropriate procedure to avoid duplicate keys.

### 24.3. Large objects

Large objects are not automatically replicated by native logical replication the way table rows are. A separate strategy is needed if the application uses them.

### 24.4. Publications

Publications determine which tables/operations are published. A slot may operate normally while a consumer misses a table if that table is not in the publication or the operation is not published.

### 24.5. Subscriber writes

If independent writes are allowed to the same tables on the subscriber, conflicts or divergence can arise. Establish clear data ownership and write direction.

## 25. Failover and logical slot continuity

### 25.1. Slots are state that must be protected

Logical slots carry their own progress and horizons. When a primary fails over, do not assume logical slots on the old primary automatically appear intact on the promoted standby.

### 25.2. Version and topology determine slot sync support

Newer PostgreSQL versions add mechanisms for failover logical slots and syncing slot state across properly configured topologies. Availability, prerequisites, and behavior vary by major version. Check documentation for your exact version before relying on failover slots.

### 25.3. Failover slots require advance design

Evaluate:

- Which slots must continue after promotion?
- Does the standby receive and synchronize slot state?
- Is needed WAL present on the promoted server or archive?
- From which checkpoint can consumers reconnect and resume?
- Is a resnapshot needed if slot continuity is broken?

### 25.4. Prevent two consumers from processing one stream after failover

Consumers must know the new primary and a valid checkpoint. Avoid split-brain CDC or two instances writing downstream simultaneously without idempotency/ownership.

### 25.5. Failover drill

Test failover in a lab, confirm slots exist/synchronize as designed, consumers reconnect, no unexpected gaps/duplicates occur outside acceptable semantics, and downstream state is accurate.

## 26. Recommended monitoring dashboard

| Category | Metric | Where to observe | Meaning |
| --- | --- | --- | --- |
| Slot inventory | slot name/type/database/plugin | Publisher `pg_replication_slots` | Identify owner and scope |
| Consumer state | `active`, `active_pid` | Publisher | Whether consumer is connected |
| WAL retention | `restart_lsn`, current LSN span | Publisher | How far back the slot retains WAL |
| Consumer progress | `confirmed_flush_lsn` | Publisher | Consumer-confirmed position |
| Tuple horizon | `xmin`, `age(xmin)` | Publisher | User tuple retention |
| Catalog horizon | `catalog_xmin`, `age(catalog_xmin)` | Publisher | Catalog retention |
| Slot safety | `wal_status`, `safe_wal_size` | Publisher, version-dependent | Risk of slot loss |
| Sender progress | sent/write/flush/replay LSN | Publisher `pg_stat_replication` | Transmission/feedback state |
| Subscription | `received_lsn`, `latest_end_lsn`/time | Subscriber `pg_stat_subscription` | Receive and feedback progress |
| Table sync | `srsubstate`, `srsublsn` | Subscriber `pg_subscription_rel` | Per-table initial sync |
| Apply workers | PID, backend type, wait | Subscriber `pg_stat_activity` | Worker health |
| Origin progress | `remote_lsn`, `local_lsn` | Subscriber origin status | Apply origin checkpoint |
| Errors | apply/sync error counters | Subscriber, version-dependent | Error detection |
| Decoding spill | spill/stream bytes | Publisher, version-dependent | Logical decoding pressure |
| Disk | `pg_wal` bytes, free bytes | OS/storage | Disk exhaustion risk |
| WAL rate | WAL bytes per second | `pg_stat_wal`/monitoring | Growth estimation |
| Database health | dead tuples, XID age | Publisher statistics | Tuple retention impact |

### 26.1. Alert on inactive slots

Alert when a critical slot stays inactive longer than an operational threshold. Distinguish scheduled maintenance from lost consumers.

### 26.2. Alert on stalled restart_lsn

Store LSN history. Alert when `restart_lsn` fails to advance while current WAL LSN keeps increasing and slot retention span exceeds baseline.

### 26.3. Alert on safe_wal_size

When available, alert when `safe_wal_size` drops low or `wal_status` shifts to an unsafe state. Base thresholds on WAL generation rate and incident response time.

### 26.4. Alert on disk headroom

Alert on filesystem free bytes and WAL directory growth rate. Do not wait until slot status turns `lost` to alert.

### 26.5. Alert on xmin age

Alert when slot `xmin` or `catalog_xmin` becomes too old relative to transaction rates and wraparound safety limits.

### 26.6. Alert on stale subscribers

On the subscriber, monitor `last_msg_receipt_time`, `latest_end_time`, worker PID, and origin progress. Correlate stale timestamps with publisher workload and network state.

### 26.7. Counters must be stored as time series

Apply errors and decoding stats can be reset. Scrape periodically to calculate deltas/rates, and record reset timestamps.

## 27. Runbook: logical slot causing rapid WAL growth

### Step 1. Identify the slot and owner

Retrieve slot name, database, plugin, consumer, `application_name`, `active_pid`, and owner. Check whether the slot belongs to an active subscription or a decommissioned CDC connector.

### Step 2. Measure retention

Read `restart_lsn`, `confirmed_flush_lsn`, current WAL LSN, `wal_status`, `safe_wal_size` if available, and free disk space.

### Step 3. Determine whether the consumer is progressing

On the subscriber/connector, check received/confirmed positions, last message timestamp, worker PID, errors, and downstream persistence.

### Step 4. Check for long-running transactions

If confirmed progress advances while `restart_lsn` stays fixed, inspect uncommitted transactions on the publisher and logical decoding state. Check `pg_stat_activity` and transaction age.

### Step 5. Check slot horizons

Read `xmin` and `catalog_xmin`; check VACUUM/dead tuple estimates and catalog pressure.

### Step 6. Check WAL generation and disk

Measure WAL bytes/second, archive backlog, slot count, and filesystem capacity. Estimate remaining time using net growth rate.

### Step 7. Choose an action

- Consumer temporarily disconnected: restore connection/worker and confirm the slot advances.
- Consumer hitting apply error: fix schema/data conflict per subscriber runbook.
- Long-running transaction: identify owner and handle in a controlled manner.
- Orphaned slot: confirm no consumer remains before dropping.
- Slot near retention cap: reduce WAL growth or restore consumer; prepare resync if the slot is lost.
- Disk nearly full: prioritize restoring progress or throttling load per incident procedure; never delete WAL files manually.

### Step 8. If the slot is already lost

Identify the last usable checkpoint, create a new slot if needed, resnapshot/resync the consumer, and check for duplicates/gaps. Never assume the slot can resume from the old LSN.

### Step 9. Verify

Confirm `restart_lsn` and `confirmed_flush_lsn` advance, WAL directory stabilizes, disk headroom recovers, subscriber apply state returns to normal, and downstream data is valid.

### Step 10. Update lifecycle records

Document owner, alert thresholds, retention cap, restart/resync procedure, and failover plan for the slot.

## 28. Diagnostic scenarios

| Symptom | Possible cause | Next evidence to check |
| --- | --- | --- |
| Slot inactive, WAL growing | Consumer disconnected or paused | Owner, logs, `active_pid`, `restart_lsn` |
| Active but `confirmed_flush_lsn` stalled | Consumer connected without acknowledging | Connector logs, downstream persistence |
| `confirmed_flush_lsn` advances, `restart_lsn` stalled | Long transaction/decoding state holding WAL | Publisher xact age, decoding metrics |
| Large WAL directory, small slot span | Archive backlog, physical slot, or other WAL workload | Archive status, all slots, disk metrics |
| `wal_status` `lost` | Required WAL was recycled | Logs, backup/checkpoint, resync plan |
| Old `xmin`, dead tuples rising | Logical slot holding tuple horizon | Slot `xmin`, autovacuum, table stats |
| Old `catalog_xmin` | Slot holding catalog horizon | Catalog age, slot lifecycle |
| Subscription has worker, table not ready | Initial sync incomplete | `pg_subscription_rel` state |
| Subscriber receives WAL, data not updating | Apply worker failing/slow or transaction uncommitted | Logs, origin status, constraints |
| LSNs do not match | Comparing different clusters or LSN types | Source identity, origin, timeline |
| Slot dropped | Consumer cannot resume old slot | Consumer checkpoint and bootstrap procedure |
| Disk full after connector outage | Unlimited retention or alerts fired too late | `max_slot_wal_keep_size`, disk history |
| CDC stops working after failover | Slot not synced/absent on new primary | Version support, failover slot setup |
| Apply errors increasing | Schema/data mismatch or constraint conflict | Subscriber logs and DDL history |

## 29. Mistakes to avoid

1. Treating a logical slot as a backup.
2. Monitoring only `active` while ignoring LSNs and retention.
3. Checking only `confirmed_flush_lsn` without checking `restart_lsn`.
4. Assuming `restart_lsn` and `confirmed_flush_lsn` must always be equal.
5. Treating `max_wal_size` as a hard cap for WAL retained by slots.
6. Using `wal_keep_size` in place of slot retention management.
7. Setting `max_slot_wal_keep_size = -1` without disk alerts.
8. Setting the retention cap too low, causing slots to be lost before consumers recover.
9. Dropping an inactive slot without identifying its owner.
10. Advancing a slot to free WAL without a resync plan.
11. Manually deleting WAL files in the WAL directory.
12. Sharing one slot across multiple independent consumers.
13. Treating `confirmed_flush_lsn` as a downstream business-processing checkpoint.
14. Ignoring long-running transactions on the publisher.
15. Ignoring `xmin` and `catalog_xmin`.
16. Assuming subscription existence means all tables are ready.
17. Failing to monitor initial table synchronization.
18. Treating `received_lsn` as data already processed downstream.
19. Subtracting LSNs from two different clusters.
20. Ignoring apply errors and checking only network connectivity.
21. Assuming slots survive every failover automatically.
22. Enabling logical replication without verifying `wal_level`.
23. Omitting physical standbys when sizing `max_wal_senders`.
24. Failing to record slot owners and resync procedures.
25. Checking only backups/WAL archiving without monitoring consumer progress.

## 30. Practice exercises with answers

Exercises assume an isolated PostgreSQL publisher/subscriber lab or CDC connector. Never drop or advance production slots for testing.

### Exercise 1. What is a logical replication slot?

**Answer:** Decoding state and progress tracking that enables the publisher to retain WAL needed by a logical consumer.

### Exercise 2. Is a slot a database copy?

**Answer:** No. It holds decoding position/horizons, not a full database copy.

### Exercise 3. What scope does a logical slot belong to?

**Answer:** One database on the publisher and one output plugin.

### Exercise 4. Common output plugin for native logical replication?

**Answer:** `pgoutput`.

### Exercise 5. Which WAL level setting is needed for logical replication?

**Answer:** `wal_level = logical`.

### Exercise 6. Which parameter limits the number of replication slots?

**Answer:** `max_replication_slots`.

### Exercise 7. Which parameter limits WAL sender processes?

**Answer:** `max_wal_senders`.

### Exercise 8. What is restart_lsn?

**Answer:** The oldest WAL position the slot may still need to continue decoding.

### Exercise 9. What is confirmed_flush_lsn?

**Answer:** The position a logical consumer has confirmed as flushed/processed per the replication feedback protocol.

### Exercise 10. Are these two LSNs always equal?

**Answer:** No. Decoding may still need older WAL due to transactions or internal state.

### Exercise 11. What does xmin mean?

**Answer:** The transaction horizon that can retain tuple versions so logical decoding can still read needed data.

### Exercise 12. What does catalog_xmin mean?

**Answer:** The catalog horizon retaining catalog rows needed for logical decoding.

### Exercise 13. Which view inventories slots?

**Answer:** `pg_replication_slots`.

### Exercise 14. Which column indicates whether a slot is in use by a consumer?

**Answer:** `active`, along with `active_pid`.

### Exercise 15. Can an inactive slot retain WAL?

**Answer:** Yes. Persistent slots retain WAL even while the consumer is disconnected.

### Exercise 16. Which function creates a logical slot?

**Answer:** `pg_create_logical_replication_slot()`.

### Exercise 17. Can a native subscription create its slot automatically?

**Answer:** Yes, when `CREATE SUBSCRIPTION` uses `create_slot = true`.

### Exercise 18. Why does each independent consumer need its own slot?

**Answer:** Each slot tracks one progress stream; one consumer advancing the slot can cause another consumer to miss changes.

### Exercise 19. Which function estimates the WAL span from restart_lsn?

**Answer:** `pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)`.

### Exercise 20. Is the WAL span the exact size dedicated solely to one slot?

**Answer:** No. It is a WAL address-space span and can overlap across multiple slots.

### Exercise 21. What does max_slot_wal_keep_size control?

**Answer:** The limit on WAL retained by replication slots in supported versions.

### Exercise 22. What does -1 usually mean?

**Answer:** No limit on slot WAL retention from this setting.

### Exercise 23. What happens if a slot exceeds the retention cap?

**Answer:** Required WAL may be recycled and the slot becomes invalidated/lost.

### Exercise 24. What does wal_status = lost mean?

**Answer:** WAL needed for the slot has been removed; the slot cannot resume from its old position.

### Exercise 25. How does safe_wal_size help?

**Answer:** Estimates bytes still writable before the slot risks losing WAL, when supported by the version.

### Exercise 26. Is max_wal_size a hard cap for pg_wal?

**Answer:** No. It is a soft target for checkpoint/WAL behavior.

### Exercise 27. Does wal_keep_size replace logical slot retention?

**Answer:** No. It provides minimum retention for standbys via a separate mechanism.

### Exercise 28. Which view monitors logical replication senders on the publisher?

**Answer:** `pg_stat_replication`.

### Exercise 29. Which view monitors subscription workers on the subscriber?

**Answer:** `pg_stat_subscription`.

### Exercise 30. Does received_lsn mean all changes were processed by business services?

**Answer:** No. It indicates receive progress; verify apply/origin and downstream persistence.

### Exercise 31. What is pg_subscription_rel used for?

**Answer:** Tracking initial synchronization state for each table in a subscription.

### Exercise 32. What does state d in pg_subscription_rel usually mean?

**Answer:** Data copy is in progress.

### Exercise 33. What does state r usually mean?

**Answer:** The table is ready per subscription state.

### Exercise 34. Which view can show COPY progress?

**Answer:** `pg_stat_progress_copy` in supported scenarios/versions.

### Exercise 35. What does pg_replication_origin_status display?

**Answer:** Remote LSN and local LSN associated with replication origins on the subscriber.

### Exercise 36. Can you subtract local_lsn from remote_lsn?

**Answer:** No. They belong to two different WAL address spaces.

### Exercise 37. How does pg_stat_subscription_stats help?

**Answer:** Tracks apply/synchronization error counters in versions that provide this view.

### Exercise 38. Why are logs still necessary?

**Answer:** Counters do not contain the full root cause and context for each error.

### Exercise 39. What does logical_decoding_work_mem affect?

**Answer:** Limits decoding memory before state may spill to disk per supported mechanisms.

### Exercise 40. Is decoding spill the same as WAL retention?

**Answer:** No. Spill is temporary decoding state; WAL retention is keeping WAL segments for a slot.

### Exercise 41. Why can restart_lsn stall even when the consumer confirms progress?

**Answer:** Uncommitted transactions or decoding state may still require older WAL.

### Exercise 42. Does successful WAL archiving automatically advance a slot?

**Answer:** No. Consumer feedback/decoding progress advances the slot.

### Exercise 43. Should WAL files be deleted manually to free disk?

**Answer:** No. PostgreSQL manages the WAL lifecycle; manual deletion can break recovery/replication.

### Exercise 44. Should an inactive slot be dropped immediately?

**Answer:** No. Verify the owner and consumer lifecycle first.

### Exercise 45. What does pg_replication_slot_advance() do?

**Answer:** Advances a slot to a specified LSN, skipping changes prior to that position per slot semantics.

### Exercise 46. What is the risk of advancing a slot?

**Answer:** The consumer may permanently miss skipped changes and require a resync.

### Exercise 47. How does peek_changes differ from get_changes?

**Answer:** Peek reads without advancing; get consumes changes and advances the slot, for compatible output plugins.

### Exercise 48. Does native logical replication automatically replicate DDL?

**Answer:** No. Schema changes usually require separate migrations on the subscriber.

### Exercise 49. Are sequence values replicated like table rows?

**Answer:** No. Sequence state must be synchronized separately per the cutover plan.

### Exercise 50. Do logical slots survive failover automatically?

**Answer:** Do not assume so. A version/topology-appropriate failover slot mechanism or resync plan is needed.

### Exercise 51. What is WAL generation rate used for?

**Answer:** Estimating WAL growth speed and remaining time before disk exhaustion.

### Exercise 52. Why check WAL directory disk usage in addition to slot span?

**Answer:** Disk also holds WAL from other slots, archive backlogs, and workload/checkpoint activity.

### Exercise 53. Does an active slot guarantee progress is advancing?

**Answer:** No. A connection can be active while the consumer fails to acknowledge or is stalled.

### Exercise 54. Does a subscription having a worker mean all tables are synced?

**Answer:** No. Check `pg_subscription_rel` for every table.

### Exercise 55. What does xmin retention affect?

**Answer:** It can prevent VACUUM from reclaiming tuple versions and increase bloat.

### Exercise 56. What does catalog_xmin retention affect?

**Answer:** It can retain catalog rows longer and create catalog cleanup pressure.

### Exercise 57. If a slot is lost, does raising max_slot_wal_keep_size recover old WAL?

**Answer:** No. Recycled WAL cannot be recreated by changing the setting.

### Exercise 58. What must be done when a slot is lost?

**Answer:** Recreate the slot and resnapshot/resync the consumer from a verified checkpoint.

### Exercise 59. Which alerts are most important for slots?

**Answer:** A combination of inactive duration, `restart_lsn` stagnation, `safe_wal_size`/`wal_status`, free disk space, and consumer progress.

### Exercise 60. Build an investigation checklist for a logical slot causing growing WAL

**Suggested answer:**

1. Identify the slot, database, plugin, owner, and consumer.
2. Read `active`/`active_pid` and join with `pg_stat_activity`.
3. Compare current WAL LSN, `restart_lsn`, and `confirmed_flush_lsn`.
4. Estimate WAL span and check `safe_wal_size`/`wal_status` if available.
5. Check free disk space and WAL generation rate.
6. On the subscriber/connector, check received LSN, worker state, errors, and downstream persistence.
7. Check `pg_subscription_rel` and replication origins if using native subscriptions.
8. Look for long-running transactions and `xmin`/`catalog_xmin` horizons.
9. Choose whether to recover the consumer, handle long transactions, drop an orphan slot, or resync if lost.
10. Verify LSNs advance, WAL/disk stabilize, and downstream data is consistent.

## 31. Production checklist

| Check | Requirement |
| --- | --- |
| `wal_level` | `logical` on publisher |
| `max_replication_slots` | Sufficient for subscriptions and CDC |
| `max_wal_senders` | Accounts for both logical and physical consumers |
| Slot owner | Assigned responsible service/team |
| Slot naming | Clearly identifies database and consumer |
| Slot inventory | Includes database/plugin/type |
| `active` / `active_pid` | Monitored |
| `restart_lsn` | Trended with stagnation alert |
| `confirmed_flush_lsn` | Monitored |
| `xmin` | Age alert configured |
| `catalog_xmin` | Age alert configured |
| WAL span | Estimated per slot |
| `pg_wal` disk | Free-space alert configured |
| WAL generation rate | Baseline established |
| `max_slot_wal_keep_size` | Policy and capacity rationale documented |
| `wal_status`/`safe_wal_size` | Monitored when supported by version |
| Consumer health | Heartbeat/progress monitored |
| `pg_stat_replication` | Sender progress observed |
| `pg_stat_subscription` | Receiver/apply progress observed |
| `pg_subscription_rel` | Per-table initial sync monitored |
| Replication origin | Checkpoint visibility enabled |
| Apply errors | Alerts and logs monitored |
| Decoding spill | Monitored if supported by version |
| Long transactions | Alerted on publisher |
| Archive backlog | Monitored separately |
| Slot invalidation | Resync runbook prepared |
| Drop/advance slot | Requires owner approval and checkpoint |
| Failover slots | Designed per version/topology |
| DDL/schema changes | Migration process exists for subscriber |
| Sequence state | Cutover procedure exists |
| Restore/resync drill | Tested regularly |
| Downstream consistency | Reconciliation checks exist |
| Metrics retention | Time series stored with reset context |

## 32. Summary

A logical replication slot is the mechanism that retains decoding state and WAL needed by a logical consumer. It allows subscribers and CDC pipelines to resume after interruptions, yet an unprogressing consumer can retain WAL and transaction/catalog horizons far longer than intended.

Key principles:

1. **A slot is one consumer's checkpoint.** Use a separate slot for each independent consumer.
2. **`restart_lsn` and `confirmed_flush_lsn` answer different questions.** Monitor both.
3. **`xmin` and `catalog_xmin` retain tuple/catalog horizons.** WAL retention and vacuum retention are separate impacts.
4. **An inactive slot can still retain WAL.** Check owner, active status, and LSN trend.
5. **`max_slot_wal_keep_size` protects storage but can cause slot loss.** Keep a resync plan ready.
6. **`max_wal_size` is not a hard cap for slot retention.** Do not use it to fix a stuck slot.
7. **Archiving WAL does not advance a slot.** The consumer must confirm progress.
8. **Long-running transactions can pin `restart_lsn`.** Check publisher transaction age when confirmed progress advances while restart position stalls.
9. **Subscriber progress has multiple layers.** Inspect receive, apply, table sync, and replication origins.
10. **Initial table copy also needs monitoring.** A subscription can be running while some tables are not yet ready.
11. **Logical decoding spill differs from WAL retention.** Monitor decoding memory/disk and WAL independently.
12. **A slot that lost WAL cannot self-recover.** Create a new slot and resnapshot/resync from a safe checkpoint.
13. **Never drop or advance slots arbitrarily.** These operations can cause downstream data loss.
14. **Failover slot continuity depends on version and topology.** Design and rehearse ahead of time.
15. **Alerts must combine slot progress and disk headroom.** Detect issues early before the WAL directory causes an outage.

Investigation model:

```text
WAL directory growing?
        |
        v
Which slot holds an old restart_lsn?
        |
        v
Is the slot active?
   +----+----+
   |         |
  Yes        No
   |         |
   v         v
Is consumer  Consumer stopped,
progressing? orphaned, or outage?
   |         |
   +----+----+
        |
        v
Is confirmed_flush_lsn advancing?
        |
        v
Is restart_lsn still stalled?
        |
        v
Check long transactions,
xmin/catalog_xmin, and decoding
        |
        v
Recover consumer or resync
        |
        v
Verify WAL, disk, apply, and
downstream consistency
```

**Final review question:** “If a CDC connector stops running for four hours, do we know which slot is retaining WAL, how much disk headroom remains, and up to which LSN the consumer confirmed? If the slot is lost due to a retention cap, do we have a checkpoint and resnapshot procedure to recover downstream without unexpected gaps or duplicates?” A safe logical replication system must answer these questions through slot metadata, subscriber progress, disk metrics, and a tested resync drill.
