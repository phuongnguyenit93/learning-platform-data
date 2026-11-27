# Freezing, Transaction ID Age, and Anti-Wraparound in PostgreSQL

## 1. Why Must PostgreSQL Freeze Transaction IDs?

PostgreSQL uses transaction IDs (XIDs) to identify which transaction created, updated, or deleted a tuple and whether that transaction committed. Normal XIDs are 32 bits wide, giving a finite number space. Once that space is exhausted, the counter wraps around and reuses old values.

If a tuple still retains a very old XID after the counter wraps around, PostgreSQL could confuse an old transaction with a new transaction sharing the same numeric XID. This could corrupt visibility checks. Therefore, PostgreSQL must mark old XIDs as long-committed before they ever become ambiguous.

**Freezing** is the process of marking old transaction metadata in a tuple as frozen. Once frozen, PostgreSQL no longer needs to look up the commit status of that old XID to know the tuple is unconditionally visible under `xmin` rules.

VACUUM therefore carries two vital responsibilities:

- Cleaning up unneeded tuple versions, updating the visibility map, and enabling space reuse.
- Freezing sufficiently old XIDs/MultiXacts to protect the database against wraparound.

A table with few UPDATE/DELETEs still needs VACUUM for freezing. A low dead tuple count does not prove XID age is safe.

```text
32-bit XID increments
       |
       v
Tuple stores transaction metadata
       |
       v
VACUUM inspects old XIDs/MultiXacts
       |
       +---- Not old enough / snapshot still needs it
       |          |
       |          v
       |      Cannot freeze yet
       |
       +---- Old enough and safe
                  |
                  v
          Freeze tuple metadata
                  |
                  v
       relfrozenxid / relminmxid advance
                  |
                  v
        Maintain safe margin before wraparound

If VACUUM falls behind:
anti-wraparound autovacuum -> warnings -> refuse new transactions
```

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain why 32-bit XIDs can wrap around and why freezing is necessary.
2. Distinguish normal transaction IDs, special XIDs, and `FrozenTransactionId`.
3. Understand the roles of tuple `xmin`, `xmax`, `MultiXactId`, and MVCC visibility.
4. Explain tuple freezing and why not every tuple can be frozen immediately.
5. Read `pg_class.relfrozenxid`, `pg_database.datfrozenxid`, and XID age.
6. Distinguish XID age from dead tuple count.
7. Understand `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, and `autovacuum_freeze_max_age`.
8. Understand aggressive vacuum and the visibility map.
9. Distinguish standard VACUUM, VACUUM FREEZE, and VACUUM FULL.
10. Understand anti-wraparound autovacuum and failsafe vacuum.
11. Monitor MultiXact wraparound using `relminmxid` and `datminmxid`.
12. Detect long-running transactions, prepared transactions, and replication slots pinning the vacuum horizon.
13. Monitor autovacuum via `pg_stat_progress_vacuum` and `pg_stat_activity`.
14. Handle wraparound warnings without arbitrarily deleting data or resetting counters.
15. Design appropriate VACUUM schedules and capacity monitoring.
16. Test freezing in a lab database and verify XID age changes.
17. Distinguish anti-wraparound protection from routine cleanup/bloat maintenance.

## 3. 32-Bit XIDs and Comparison Limits

### 3.1. XIDs Are Not Infinite Sequence Numbers

Normal XIDs occupy a 32-bit space:

```text
2^32 = 4,294,967,296
```

A few values are reserved for internal use; normal transaction IDs start in the normal XID range. After the counter uses up the space, it wraps around.

You cannot compare XIDs like ever-increasing integers with ordinary arithmetic comparisons. PostgreSQL uses wraparound-aware comparison within a bounded safe window.

### 3.2. Half the XID Space Is the Critical Boundary

An old XID and a new XID become ambiguous if the distance between them exceeds half of the 32-bit space:

```text
2^31 = 2,147,483,648
```

PostgreSQL must ensure XIDs still referenced by tuples never cross into this ambiguous region. Freezing eliminates reliance on the transaction status of old XIDs.

### 3.3. Special Transaction IDs

Several special XIDs are commonly referenced:

| Name | Value | Meaning |
| --- | ---: | --- |
| `InvalidTransactionId` | 0 | Not a valid normal XID |
| `BootstrapTransactionId` | 1 | Initial bootstrap transaction |
| `FrozenTransactionId` | 2 | Represents a frozen tuple |
| `FirstNormalTransactionId` | 3 | Start of the normal XID range |

These are PostgreSQL internal details. Applications must never set or alter tuple system columns directly.

### 3.4. XIDs Are Allocated on Demand

Not every `SELECT` allocates a normal XID. A transaction typically receives an XID when performing an operation requiring a transaction identity, such as writing data. Thus XID consumption rate does not always equal SQL statement count or HTTP request rate.

A read-only transaction can hold a snapshot for a long time without consuming a new XID itself, yet its snapshot can still pin old XIDs and block VACUUM.

### 3.5. Inspecting Current XID Carefully

Certain functions that return the current XID allocate one if the transaction does not already have one. When writing monitoring, prefer non-allocating functions if you only want to see whether a transaction already holds an ID. Avoid burning unnecessary transaction IDs in monitoring checks.

## 4. Tuple Visibility: xmin, xmax, and Freezing

Every heap tuple carries transaction metadata. Two key system columns are:

- `xmin`: XID of the transaction that created the tuple version.
- `xmax`: XID or `MultiXactId` associated with the transaction that deleted/updated the tuple, or row locking depending on tuple state.

Example:

```sql
SELECT
    event_id,
    xmin,
    xmax,
    ctid
FROM vacuum_lab.events
LIMIT 20;
```

Here `xmin` and `xmax` are tuple system columns. Never use them as business keys or modify them directly.

### 4.1. An UPDATE Usually Creates a New Tuple Version

PostgreSQL uses MVCC. On UPDATE, the system typically creates a new tuple version and marks the old version as superseded in transaction metadata. Different snapshots can see different versions.

VACUUM must determine when an old tuple is no longer needed by any valid snapshot; it can then prune/reclaim dead tuples and freeze necessary metadata on surviving live tuples.

### 4.2. Freezing Handles Old Transaction Identities

A tuple created by a transaction committed long ago can be marked Frozen. PostgreSQL then no longer needs to consult old commit status to know that tuple is visible by `xmin`.

This does not mean the tuple can never be UPDATEd or DELETEd again. A new version still receives its own XID when modified.

### 4.3. Freezing Does Not Make a Tuple Immutable

A frozen tuple can still be updated or deleted later. Freezing only changes how PostgreSQL interprets old transaction metadata; it does not lock data or forbid row modifications.

### 4.4. Not Every XID Can Be Frozen Immediately

A tuple created by a still-running transaction or within a range where an old snapshot might need to distinguish it cannot be safely marked frozen. VACUUM must respect the global visibility horizon.

### 4.5. Freezing vs. Removing Dead Tuples

- **Pruning/removal:** eliminates tuple versions that are no longer needed.
- **Freezing:** marks old XIDs of surviving tuples so they cannot be misinterpreted after wraparound.

A VACUUM can freeze live tuples without deleting them. Conversely, dead tuples are removed when safe without keeping them around as frozen tuples.

## 5. MultiXact IDs and the Second Wraparound

PostgreSQL also has MultiXact IDs (MXIDs). They are used when multiple transactions hold row locks on the same tuple simultaneously. In some cases, a tuple's `xmax` represents a MultiXact rather than a single XID.

MultiXact IDs also have finite space and must be frozen/retired. Therefore, monitoring XIDs alone is not enough.

### 5.1. A MultiXact Combines Multiple Members

A MultiXact represents a set of member transactions and lock modes. It enables PostgreSQL to track multiple concurrent row lockers.

### 5.2. Metadata Tracking MultiXacts

| Catalog Field | Meaning |
| --- | --- |
| `pg_class.relminmxid` | Oldest MXID the relation might still need |
| `pg_database.datminmxid` | Oldest MXID tracked at the database level |

Use `mxid_age()` to view MultiXact age with wraparound-aware semantics.

### 5.3. Why Tables with Heavy Row Locking Need Attention

Workloads where many concurrent transactions execute `SELECT ... FOR UPDATE` or row-locking statements can generate MultiXacts rapidly. Even if XID age is low, MXID age can climb fast.

### 5.4. XID Freezing and MultiXact Freezing Are Two Axes

A table can be safe on XIDs while nearing its MultiXact limit, or vice versa. Monitor both `relfrozenxid`/`datfrozenxid` and `relminmxid`/`datminmxid`.

## 6. relfrozenxid and datfrozenxid

PostgreSQL records freezing horizons in the catalogs.

### 6.1. relfrozenxid

`pg_class.relfrozenxid` is the XID horizon for a relation. It represents the oldest XID that the relation might still need to evaluate under visibility/freezing rules. Once VACUUM finishes enough safe work, this cutoff can advance.

### 6.2. datfrozenxid

`pg_database.datfrozenxid` is the database-level horizon, derived from the tracked relations in that database. One old relation can hold back the entire database cutoff even when all other tables were recently vacuumed.

### 6.3. Use age() Instead of Raw XID Comparisons

Use:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

`age(xid)` returns the number of transaction IDs elapsed since that XID under wraparound-aware semantics. This is the proper way to inspect age.

### 6.4. Do Not Compare XIDs with Arbitrary Arithmetic MAX/MIN

Because XIDs wrap around, `MAX(relfrozenxid)` or integer-cast comparisons cannot tell you which relation is oldest in transaction age. Always use `age()`.

### 6.5. Database Age and Table Age Answer Different Questions

- `age(datfrozenxid)`: how close the database is to the threshold.
- `age(relfrozenxid)`: how much XID age a specific relation holds.

Database-level age drives high-level alerting; relation-level age pinpoints the table, catalog, or TOAST relation holding back the old cutoff.

## 7. Lab: Creating an Observable Table

Practice examples use a dedicated schema. Never test manual freeze operations or XID load generation on production.

### 7.1. Create Schema and Data

```sql
CREATE SCHEMA IF NOT EXISTS vacuum_lab;

CREATE TABLE vacuum_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO vacuum_lab.events (tenant_id, payload)
SELECT
    (g % 10)::integer,
    'event-' || g
FROM generate_series(1, 10000) AS g;

ANALYZE vacuum_lab.events;
```

### 7.2. Inspect Tuple Metadata

```sql
SELECT
    event_id,
    xmin,
    xmax,
    ctid
FROM vacuum_lab.events
ORDER BY event_id
LIMIT 10;
```

You may see many rows sharing the same `xmin` when inserted in the same transaction.

### 7.3. Inspect the Table's relfrozenxid

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

The age in a lab may be very small since the table was just created.

### 7.4. Create Dead Tuples to Understand Standard VACUUM

```sql
UPDATE vacuum_lab.events
SET payload = payload || '-updated'
WHERE event_id <= 1000;

DELETE FROM vacuum_lab.events
WHERE event_id BETWEEN 9001 AND 9500;

SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
```

Statistics are estimates and can lag behind statements. Dead tuple counts are not XID age.

### 7.5. Run VACUUM FREEZE on the Lab Table

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

Then inspect again:

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

With a small table and no horizon blocker, `VACUUM FREEZE` can advance the freeze horizon close to the current XID. Exact results depend on active transactions and visibility conditions.

### 7.6. VACUUM Cannot Run Inside a Transaction Block

Do not place `VACUUM` inside a normal `BEGIN ... COMMIT`. Run it as an independent statement from `psql` or an autocommit JDBC connection. If a migration tool wraps all statements in a transaction, configure a separate non-transactional task.

## 8. Key Freezing Thresholds

PostgreSQL has multiple settings, each with a different purpose.

| Setting | Role |
| --- | --- |
| `vacuum_freeze_min_age` | Minimum XID age before VACUUM considers freezing |
| `vacuum_freeze_table_age` | Relation age triggering an aggressive scan by VACUUM |
| `autovacuum_freeze_max_age` | Relation age requiring anti-wraparound autovacuum |
| `vacuum_failsafe_age` | Failsafe threshold for XID wraparound |
| `vacuum_multixact_freeze_min_age` | MultiXact age threshold for freezing |
| `vacuum_multixact_freeze_table_age` | Aggressive scan threshold for MXID |
| `autovacuum_multixact_freeze_max_age` | Anti-wraparound threshold for MultiXacts |
| `vacuum_multixact_failsafe_age` | Failsafe threshold for MultiXacts |

Defaults depend on PostgreSQL version and can be overridden by configuration. Check settings on your running server rather than memorizing one number as immutable.

### 8.1. vacuum_freeze_min_age

XIDs older than this threshold can be frozen during a standard VACUUM when safe. A common default is 50 million XIDs.

Setting it too low triggers premature freezing and increases tuple metadata write work. Setting it too high keeps XIDs unfrozen longer and shifts extra work to later VACUUMs.

### 8.2. vacuum_freeze_table_age

When a table's `relfrozenxid` age exceeds this threshold, VACUUM performs an aggressive scan to locate tuples needing freezing across the relation, instead of skipping all-visible pages.

A common default is 150 million XIDs.

### 8.3. autovacuum_freeze_max_age

When a relation approaches this threshold, PostgreSQL triggers an anti-wraparound vacuum. A common default is 200 million XIDs.

This is a critical safety limit, not a target for routinely running tables near the edge.

### 8.4. Relationship Between Thresholds

Under common defaults:

```text
vacuum_freeze_min_age       ~  50 million
vacuum_freeze_table_age     ~ 150 million
autovacuum_freeze_max_age   ~ 200 million
                                  |
                                  v
                        2^31 = 2.147 billion
                        wraparound danger zone
```

These numbers only illustrate relative ordering. A cluster may configure different values; verify with `SHOW` and `pg_settings`.

### 8.5. Why Not Set autovacuum_freeze_max_age Very Large?

Raising it postpones anti-wraparound vacuuming, letting old XIDs linger longer and growing the volume of transaction status metadata that must be retained. It trades short-term work deferral for a thinner safety margin and can turn a routine maintenance need into a severe outage.

### 8.6. Do Not Look at Only One Setting

`vacuum_freeze_min_age` governs per-tuple freezing during a vacuum; `vacuum_freeze_table_age` governs aggressive scanning; `autovacuum_freeze_max_age` decides when urgent anti-wraparound vacuuming is forced. Tuning one setting does not replace the others.

## 9. Aggressive Vacuum and the Visibility Map

The visibility map (VM) tracks per-page flags indicating whether all tuples on the page are visible to all active transactions, and whether the page is all-frozen.

### 9.1. All-Visible

An all-visible page lets VACUUM skip normal visibility scanning and accelerates index-only scans. All-visible does not automatically mean all XIDs are frozen.

### 9.2. All-Frozen

An all-frozen page has been frozen sufficiently that normal VACUUMs do not need to re-inspect old XIDs for wraparound safety. This is a stronger state than all-visible.

### 9.3. Aggressive Vacuum

When `relfrozenxid` needs to advance, VACUUM must inspect every page that might still hold unfrozen XIDs, including pages marked all-visible that are not yet all-frozen. It can still use the all-frozen map to skip pages already known to be safe.

### 9.4. Why Does an Aggressive Scan Cost Heavy I/O?

A massive table may require reading huge numbers of pages to confirm no overly old XIDs remain. If storage is slow, buffer cache is small, or concurrent workload is heavy, the vacuum can take considerable time.

### 9.5. Pinned or Locked Pages

Some pages/tuples cannot be processed immediately due to concurrent activity, buffer pins, or lock contention. VACUUM may have to skip and revisit them later; monitor progress via logs and progress views.

## 10. Standard VACUUM, VACUUM FREEZE, and VACUUM FULL

| Command | Goal | Impact |
| --- | --- | --- |
| `VACUUM table_name` | Clean dead tuples, update visibility, freeze per thresholds | Usually allows concurrent reads/writes |
| `VACUUM (FREEZE) table_name` | Request stronger freezing | Aggressive freeze; still a standard VACUUM |
| `VACUUM FULL table_name` | Rewrite table to reclaim disk space | Requires strong lock, can block access |
| `ANALYZE table_name` | Update planner statistics | Does not replace freezing |

### 10.1. FREEZE Is Not FULL

`VACUUM (FREEZE)` does not rewrite the entire table like `VACUUM FULL`. Never run `FULL` merely because of a high XID age warning; `FULL` takes heavy locks and I/O and is not the right remedy for wraparound.

### 10.2. Standard VACUUM Also Freezes

You do not need `FREEZE` on every VACUUM command. Standard VACUUM still freezes XIDs old enough per freeze settings. `FREEZE` is useful when you intentionally want to freeze earlier, such as during maintenance or lab setup.

### 10.3. VACUUM FULL Rewrites the Relation

Rewriting creates a new relation file and requires a strong lock, normally `ACCESS EXCLUSIVE`. It can hold the lock for a long time and requires substantial temporary disk space. Plan it separately; never run it reflexively in response to wraparound warnings.

### 10.4. VACUUM Requires Appropriate Privileges

Normally only the relation owner or a role with appropriate privileges can run it. Anti-wraparound autovacuum runs under internal system mechanisms. Never grant superuser to an application just to call VACUUM.

## 11. Anti-Wraparound Autovacuum

Regular autovacuum triggers on dead tuples or inserts. Anti-wraparound vacuum triggers based on XID/MultiXact age to protect the database, even when a table has few dead tuples.

### 11.1. Autovacuum Is Not Just Performance Optimization

It is a data correctness safeguard. Disabling autovacuum to save I/O without a replacement vacuum plan can lead to the database refusing new transactions.

### 11.2. Anti-Wraparound Can Run Even When Autovacuum Is Disabled

PostgreSQL still spawns required workers to prevent transaction ID wraparound even when regular autovacuum is disabled. However, disabling autovacuum remains very dangerous because regular cleanup and analyze maintenance suffer.

### 11.3. Workers Can Prioritize Freezing Over Cleanup

When age approaches danger limits, the system prioritizes advancing the freeze horizon. Failsafe mode can disable cost delays and skip some index cleanup to accelerate wraparound protection.

### 11.4. Warnings in the Logs

When a database nears the limit, logs warn that the database must be vacuumed within a remaining number of transactions. Treat this as a high-priority operational incident, not a warning to defer until the next maintenance window.

### 11.5. Entering the Danger Zone

PostgreSQL stops allocating new XIDs to prevent wraparound from corrupting visibility. The system may refuse commands needing a transaction ID or reject new transactions in protective mode. Never wait until this point to build a response plan.

## 12. Failsafe Vacuum

A vacuum can be slowed by cost-based delays to shield foreground workloads. Once XID/MultiXact age crosses the failsafe threshold, PostgreSQL switches to prioritizing wraparound prevention.

### 12.1. vacuum_failsafe_age

This setting defines the XID age at which VACUUM activates failsafe behavior. Defaults and configurability depend on version; check your running server.

### 12.2. Failsafe Shifts Priorities

Failsafe can disable cost-based vacuum delays and skip index cleanup to complete freezing as fast as possible. This helps prevent wraparound at the expense of higher I/O/CPU and deferred index cleanup work.

### 12.3. Do Not Rely on Failsafe as a Maintenance Schedule

Failsafe is a last-resort safeguard when vacuum has already fallen badly behind. The operational goal is detecting rising age early so autovacuum finishes long before failsafe needs to intervene.

### 12.4. MultiXacts Have Their Own Failsafe

Monitor `vacuum_multixact_failsafe_age` alongside MultiXact freeze settings. Never monitor XIDs alone.

## 13. What Holds Back the Vacuum Horizon?

VACUUM cannot freeze or remove a tuple if an old snapshot might still need to distinguish that tuple's transaction state. Sources that pin the horizon:

- Long-open transactions, including read-only transactions.
- `idle in transaction` sessions.
- Prepared transactions not yet resolved via `COMMIT PREPARED` or `ROLLBACK PREPARED`.
- Replication slots holding `xmin` or `catalog_xmin`.
- Standby feedback (`hot_standby_feedback`) holding xmin on the primary.
- Exported snapshots with active owning transactions.
- Certain logical decoding/replication workflows.

### 13.1. Long-Running Transactions

A transaction started long ago can pin an old `backend_xmin`. Even if not actively executing queries continuously, its old snapshot prevents VACUUM from advancing the horizon.

### 13.2. Idle in Transaction

A session that runs `BEGIN`, executes a query, and sits waiting on an application holds transactions and locks open. This is a common reason vacuum cannot clean or freeze as expected.

### 13.3. Prepared Transactions

A prepared transaction retains locks and transaction state after `PREPARE TRANSACTION`. If the coordinator fails to finish the two-phase commit, it pins the horizon indefinitely.

### 13.4. Replication Slots

Replication slots can retain WAL and/or `xmin`/`catalog_xmin` so consumers can continue decoding properly. An abandoned slot can retain old data, inflate disk usage, or block vacuum.

### 13.5. Hot Standby Feedback

A standby can send `xmin` back to the primary to avoid query conflicts on the replica. That protects replica queries at the cost of pinning the primary's vacuum horizon. Balance replica query stability against primary bloat and freeze progress.

### 13.6. Do Not Drop Slots Arbitrarily

Dropping a replication slot can prevent subscribers/replicas from resuming from their last position, forcing a rebuild/resync. Verify consumer, retention, `restart_lsn`, and recovery plan before dropping.

## 14. Monitoring Database XID Age

Start at the database level:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS autovacuum_freeze_max_age,
    round(
        100.0 * age(datfrozenxid)::numeric
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::numeric,
            0
        ),
        1
    ) AS pct_of_freeze_max
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

### 14.1. Interpreting the Percentage

`pct_of_freeze_max` helps dashboards visualize trends. It is not a wraparound probability or an SLA. Exceeding 100% means autovacuum has been triggered, not necessarily that it has completed; investigate immediately.

### 14.2. Monitoring MXID Age at the Database Level

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY GREATEST(
    age(datfrozenxid),
    mxid_age(datminmxid)
) DESC;
```

The two ages can grow at different rates and have different thresholds. Dashboards should plot them as separate series rather than collapsing them into one number.

### 14.3. Checking Effective Settings

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum',
    'autovacuum_freeze_max_age',
    'vacuum_freeze_min_age',
    'vacuum_freeze_table_age',
    'vacuum_failsafe_age',
    'autovacuum_multixact_freeze_max_age',
    'vacuum_multixact_freeze_min_age',
    'vacuum_multixact_freeze_table_age',
    'vacuum_multixact_failsafe_age',
    'autovacuum_max_workers',
    'autovacuum_naptime',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit'
)
ORDER BY name;
```

If a setting does not exist in your PostgreSQL version, the `name IN (...)` filter simply returns no row for that setting.

## 15. Finding Relations Holding High XID Age

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    c.reloptions
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
  AND c.relfrozenxid <> '0'::xid
ORDER BY age(c.relfrozenxid) DESC
LIMIT 50;
```

### 15.1. Include TOAST Tables

TOAST relations also carry tuple metadata and participate in vacuum/freezing. `relkind = 't'` surfaces them.

### 15.2. Partitioned Parents

A partitioned parent typically has no heap storage like an ordinary table. Inspect each partition actually storing tuples; never inspect only the parent and conclude the whole partition tree is safe.

### 15.3. System Catalogs

System catalogs must also be vacuumed and frozen. Never exclude them from investigations just because they live in `pg_catalog`; catalog age can be pivotal in incidents.

### 15.4. Database Age Can Be Pinned by a Single Relation

One relation with very high age can pin the entire database's `datfrozenxid`. Top-relation queries help locate suspects, though you must also inspect vacuum horizons and relation types.

## 16. Finding Transactions Pinning the Horizon

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 16.1. Focus on the Oldest Transaction

Check the owner, application, state, query, and why the transaction has not ended. Never terminate solely because age is high; it could be a legitimate migration or maintenance job requiring runbook handling.

### 16.2. Read-Only Transactions Still Matter

A transaction doing no UPDATE/DELETE can still hold an old snapshot and block vacuum. Do not look only for sessions running writes.

### 16.3. Idle in Transaction

```sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

`state_change` shows when the backend entered its current state. Transaction age and idle age are two different durations.

### 16.4. Prepared Transactions

```sql
SELECT
    transaction,
    gid,
    prepared,
    clock_timestamp() - prepared AS prepared_age,
    owner,
    database,
    age(transaction) AS xid_age
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

Resolve prepared transactions only after verifying with the transaction coordinator and business owner. `COMMIT PREPARED` or `ROLLBACK PREPARED` is a transactional/business decision, not casual cleanup.

## 17. Checking Replication Slots and Standby Feedback

### 17.1. Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

A slot does not necessarily hold both fields. Inspect slot type, consumer, and state.

### 17.2. Standby Feedback

```sql
SHOW hot_standby_feedback;

SELECT
    application_name,
    state,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

If a replica holds an old snapshot, feedback can propagate `xmin` back to the primary. Monitor both long queries on replicas and vacuum progress on the primary.

### 17.3. Long-Inactive Slots

An inactive slot is not automatically useless. It could belong to a paused logical subscriber, backup workflow, or offline replica. Confirm the owner and recovery plan before dropping it.

### 17.4. WAL Retention vs. XID Horizon

`restart_lsn` retains WAL so logical decoding/replication can resume. `xmin`/`catalog_xmin` can pin the tuple/catalog visibility horizon. The two retention mechanisms are related but distinct.

## 18. Monitoring Running VACUUM

```sql
SELECT
    p.pid,
    a.datname,
    a.application_name,
    n.nspname,
    c.relname,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    round(
        100.0 * p.heap_blks_scanned
        / NULLIF(p.heap_blks_total, 0),
        1
    ) AS scanned_pct,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.query_start AS runtime
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
LEFT JOIN pg_catalog.pg_class AS c
  ON c.oid = p.relid
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
ORDER BY a.query_start;
```

### 18.1. Phase

The progress view reports phases such as scanning heap, vacuuming indexes, and cleaning up indexes. Exact phase names/details depend on PostgreSQL version.

### 18.2. Scanned Percentage Is Not Freeze Completion Percentage

A vacuum can scan many pages while still constrained by horizon blockers or pages needing retries. Use before/after ages, logs, and VACUUM output to judge real progress.

### 18.3. Autovacuum Workers

You can filter `pg_stat_activity` by `backend_type` or corresponding application/query metadata to identify autovacuum workers. Verify available columns for your version.

### 18.4. VACUUM Statistics

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY last_autovacuum NULLS FIRST;
```

These statistics track vacuum/dead-tuple activity; they do not replace `age(relfrozenxid)`.

## 19. Autovacuum Cleanup Threshold vs. Freeze Threshold

A common mistake is thinking autovacuum runs only when dead tuple counts exceed a threshold.

### 19.1. Dead-Tuple Trigger

Regular autovacuum vacuuming is triggered by a threshold roughly of the form:

```text
threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
```

This is a cleanup trigger driven by estimated dead tuples.

### 19.2. Freeze Trigger

Anti-wraparound vacuum triggers on `relfrozenxid` age or MultiXact age. An append-only table with minimal UPDATE/DELETEs can still need vacuum freeze.

### 19.3. Insert-Only Tables

An insert-only table may have few dead tuples while XID age on its oldest tuples keeps climbing. Freezing cannot be skipped just because a table rarely updates or deletes.

### 19.4. Autovacuum Per-Table Settings

You can tune `reloptions` such as scale factor/threshold, yet never accidentally configure a relation so it fails to vacuum on time. Always check `reloptions` and effective configuration before jumping to conclusions.

## 20. Why Does Autovacuum Fall Behind?

Common causes:

- `autovacuum_max_workers` is too low for the table count or throughput.
- Vacuum cost delay/limit makes progress too slow.
- I/O is throttled or storage latency is high.
- A very large table requires an aggressive scan.
- Long-running transactions pin an old `xmin`.
- Replication slots or standby feedback pin the horizon.
- Unresolved prepared transactions.
- Autovacuum is disabled or `reloptions` are unsuitable.
- Workers are repeatedly canceled by maintenance/deployments.
- The database has huge numbers of small relations or bloated catalogs.
- Table churn or transaction allocation rate exceeds vacuum capacity.

### 20.1. Do Not Only Increase Worker Count

Adding workers can worsen I/O and CPU contention. Evaluate vacuum throughput, database workload, and storage headroom together.

### 20.2. Raising Cost Limit Can Help

`autovacuum_vacuum_cost_limit` and `autovacuum_vacuum_cost_delay` govern regular vacuum speed under the cost model. Tune based on load and observation; no single number fits every cluster.

### 20.3. Anti-Wraparound Must Be Prioritized

If age nears critical thresholds, you may need to reserve capacity for vacuum, throttle write traffic, or pause non-essential workloads so workers can finish.

### 20.4. Do Not Cancel Autovacuum Simply Because I/O Rose

If the worker is an anti-wraparound vacuum, canceling it can push the cluster into deeper danger. Verify the relation, age, and trigger reason before intervening.

## 21. Practicing VACUUM FREEZE and Verifying Results

### 21.1. Run a Standalone VACUUM Command

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

This command must run outside an explicit transaction block.

### 21.2. Compare Age Before and After

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

Read verbose output to see what the vacuum scan/freeze accomplished. On a tiny lab table, age may be minimal; that does not mean a production cluster has no issues.

### 21.3. Freezing Does Not Guarantee Age Becomes 0

The new cutoff must respect existing transactions/snapshots and relation scope. If an older transaction holds the horizon, VACUUM may not advance the cutoff as far as expected.

### 21.4. Inspecting the Visibility Map

If the `pg_visibility` extension is available and installed, its functions help inspect page visibility and all-frozen bits. It is a diagnostic aid; do not install extensions on production merely to run routine monitoring queries.

### 21.5. Never Edit System Catalogs Manually

Never directly UPDATE `pg_class.relfrozenxid`, `pg_database.datfrozenxid`, tuple `xmin`, or transaction status files. These values must be managed exclusively by PostgreSQL's VACUUM and transaction machinery.

## 22. Runbook for Handling Wraparound Warnings

When logs warn that a database must be vacuumed within a remaining transaction count, treat it as a high-priority incident.

### Step 1. Assess Cluster-Wide Age

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

Identify which database has the highest age and fastest growth rate.

### Step 2. Find the Oldest Relations in That Database

Query `pg_class` ordered by `age(relfrozenxid)` and `mxid_age(relminmxid)`. Check user tables, TOAST relations, and system catalogs alike.

### Step 3. Find Horizon Blockers

Inspect:

- `pg_stat_activity` and transaction ages.
- `idle in transaction` sessions.
- `pg_prepared_xacts`.
- `pg_replication_slots`.
- `pg_stat_replication.backend_xmin`.
- Exported snapshot workflows.
- Autovacuum and replication logs.

### Step 4. Give Vacuum Room to Complete

Verify autovacuum is enabled, workers are running, disk/WAL/storage headroom is sufficient, and no job is repeatedly canceling workers.

### Step 5. Clear Blockers Under Control

Ask application owners to finish old transactions. Resolve prepared transactions via their coordinator. Handle slots/replicas per recovery plans. Only terminate a backend after verifying owner, PID, and business impact.

### Step 6. Run Manual VACUUM If Needed

In the affected database, with proper privileges and verified capacity:

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

This is an example using the lab table. In production, vacuum the exact relations holding back the age, including catalogs and TOAST as planned. `VACUUM` cannot run inside a transaction block.

Across multiple databases, `vacuumdb` can target multiple databases:

```bash
vacuumdb --all --freeze --jobs=2 --verbose
```

The job count is illustrative. Pick concurrency based on I/O, CPU, and workload; never launch dozens of workers blindly.

### Step 7. Verify Age Advances

Re-run the age queries and progress views. Confirm `datfrozenxid`/`relfrozenxid` genuinely advanced and warnings subsided. Do not just verify that `VACUUM` exited with status 0.

### Step 8. Restore Workload Gradually

Once safety margins recover, restore write traffic within capacity while continuing to watch age, autovacuum duration, and replication lag.

### Step 9. Fix the Root Cause

Adjust transaction lifetimes, slot retention, autovacuum capacity, per-table settings, alert thresholds, and runbooks. Do not merely vacuum one table and ignore why vacuum was blocked.

## 23. When a Database Enters Transaction-Refusal Territory

PostgreSQL stops allocating new XIDs right before hitting the danger boundary. Once the database refuses commands to prevent wraparound, normal operations may no longer work.

### 23.1. Never Reset the XID Counter

Never use tricks to edit `pg_control`, patch catalogs, or alter transaction IDs manually. Those actions corrupt visibility and leave data untrustworthy.

### 23.2. Follow the Major-Version Maintenance Procedure

If the database no longer accepts transactions needed to vacuum, DBAs may have to use a specialized recovery procedure, such as single-user mode under controlled conditions. Syntax and steps must follow the official documentation for that exact major version, with backups/snapshots and experienced PostgreSQL operators.

### 23.3. Do Not Delete Data to Lower Age

Deleting rows does not help if old XIDs remain unfrozen; DELETE even generates new transaction metadata and dead tuples. VACUUM freeze is what advances the XID horizon.

### 23.4. Do Not Blindly Drop Old Databases/Tables

Dropping a relation might remove one XID horizon blocker if it is the exact object, yet it destroys data and ignores other blockers. Only do so after confirming ownership, backups, and dependencies.

### 23.5. Post-Recovery Verification

Verify database age, relation age, autovacuum status, logs, and the ability to execute new transactions. Run integrity checks per your runbook before declaring normal service restored.

## 24. High-Age Tables with Few Dead Tuples

This scenario is frequently misunderstood.

### 24.1. Append-Only Tables

An insert-only log table may have nearly zero dead tuples. Yet old rows still hold `xmin` values from months ago. They must be frozen so the XID counter can keep wrapping safely.

### 24.2. VACUUM FREEZE Is Not Only for Heavy-UPDATE Tables

Rarely updated tables are prime candidates for periodic freezing. Never use `n_dead_tup = 0` as an excuse to skip freezing.

### 24.3. Partitioned Tables

With daily/monthly partitions, old partitions receive few writes and freeze cleanly. However, a partitioned parent does not represent every heap partition. Monitor each partition and its TOAST relations.

### 24.4. Read-Only Archival Tables

Archival tables can be vacuum-frozen before moving to read-only workloads/storage. Freezing removes dependence on old XID status, though separate retention and restore plans remain necessary.

## 25. Freezing and Transaction Age in Replication Environments

### 25.1. Physical Replication

Primary and standby servers must stay consistent across WAL/transaction history. Vacuum cleanup can conflict with standby queries. Hot standby feedback can pin `xmin` on the primary and slow cleanup/freezing.

### 25.2. Logical Replication

Logical decoding requires retaining catalog and tuple visibility per the slot horizon. A long-inactive slot can pin `catalog_xmin`/`xmin`, blocking the primary from reclaiming old data.

### 25.3. Replica Lag

Replica lag does not directly equal high XID age. Yet lag and slots prolong retention, grow disk usage, or pin the vacuum horizon. Monitor both replication progress and age.

### 25.4. Inactive Yet Existing Slots

A logical slot can pin `catalog_xmin` even after a subscriber stops. Verify the subscriber and resync plan before dropping.

### 25.5. Logical Slot Failover

Newer PostgreSQL versions include features for logical slot failover; details vary by major version. Never apply slot-management commands from a generic snippet without checking version and configuration.

## 26. MultiXact Monitoring and Operations

### 26.1. Database-Level MXID Age

```sql
SELECT
    datname,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY mxid_age(datminmxid) DESC;
```

### 26.2. Relation-Level MXID Age

```sql
SELECT
    n.nspname,
    c.relname,
    mxid_age(c.relminmxid) AS mxid_age,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY mxid_age(c.relminmxid) DESC
LIMIT 50;
```

### 26.3. Why Do MXIDs Have Different Thresholds Than XIDs?

MultiXacts are generated under specific row-locking patterns and have their own lifecycle/retention. `autovacuum_multixact_freeze_max_age` usually has a different default from `autovacuum_freeze_max_age`; never copy XID thresholds directly to MXIDs.

### 26.4. Row-Locking Workloads

If workloads have many transactions locking the same row or locking many rows concurrently, review transaction durations, lock modes, and contention. Shortening lock hold times reduces MultiXact pressure.

## 27. Tuning Autovacuum Capacity

When vacuum cannot keep pace, measure and adjust multiple factors.

### 27.1. autovacuum_max_workers

Caps concurrent autovacuum workers. Raising workers can boost throughput when CPU/I/O headroom exists; too many workers cause contention.

### 27.2. autovacuum_naptime

Interval between database checks by the launcher. Smaller values detect needed work sooner at slightly higher scheduling overhead.

### 27.3. Cost-Based Delay and Limit

```sql
SHOW autovacuum_vacuum_cost_delay;
SHOW autovacuum_vacuum_cost_limit;
SHOW vacuum_cost_delay;
SHOW vacuum_cost_limit;
```

These govern normal vacuum speed under the cost model. Failsafe mode can bypass throttling to prioritize wraparound safety.

### 27.4. autovacuum_work_mem

Caps memory per vacuum worker per configuration. Index cleanup needs memory; setting it too low forces extra index passes. Tune within workload and total memory budgets.

### 27.5. Table reloptions

Tables can have custom autovacuum thresholds/scale factors and freeze settings. Inspect:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.reloptions IS NOT NULL
ORDER BY c.oid::regclass::text;
```

Never copy one table-specific setting to all tables without evaluating size, write rate, and SLAs.

### 27.6. Raising autovacuum_freeze_max_age Is Not a Capacity Solution

If workers cannot keep up, raising the threshold only delays action while increasing storage/risks. Fix blockers and vacuum throughput first.

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| VACUUM only deletes dead rows | VACUUM also freezes XIDs and advances horizons |
| Tables without UPDATEs never need VACUUM | Append-only rows still require freezing |
| Low `n_dead_tup` means low XID age | They measure completely different things |
| XIDs are infinite 64-bit integers | Normal tuple XIDs are 32-bit |
| You can compare XIDs with `MAX` | Use `age()` for wraparound-aware semantics |
| Frozen tuples cannot be updated | Tuples can still receive new versions |
| FREEZE is like VACUUM FULL | FREEZE does not rewrite or take `ACCESS EXCLUSIVE` |
| Autovacuum only triggers on dead tuples | Anti-wraparound triggers on XID/MXID age |
| Disabling autovacuum stops all anti-wraparound workers | PostgreSQL still enforces essential anti-wraparound protection |
| `VACUUM FREEZE` always resets age to 0 | Horizon blockers can prevent advancing the cutoff |
| Database age tells you which table is lagging | Run relation-level age queries |
| Only XID age needs monitoring | MultiXact age must also be monitored |
| Idle transactions do not affect vacuum | Open snapshots still hold the horizon |
| Read-only transactions do not matter | They can still hold snapshots |
| Dropping a replication slot is always safe | It can force subscribers/replicas to resync |
| Raising `freeze_max_age` fixes warnings | It only postpones them and shrinks safety margins |
| `VACUUM FULL` is the cure for wraparound | No; standard `VACUUM FREEZE` is the proper mechanism |
| Deleting all old rows solves wraparound | DELETE does not replace freezing |
| 100% progress guarantees age advanced | Always verify cutoffs after vacuum |
| Vacuuming one database makes the whole cluster safe | Every database has its own `datfrozenxid` |
| Checking the partitioned parent is enough | Check leaf heap partitions and TOAST relations |
| Failsafe is a normal maintenance plan | Failsafe is a last-resort safety mechanism |
| A long transaction only holds row locks | It also pins the visibility horizon |
| Slot WAL retention and `xmin` retention are identical | `restart_lsn` differs from `xmin`/`catalog_xmin` |
| More workers are always better | I/O and CPU contention can worsen |
| VACUUM can run inside `BEGIN` | VACUUM cannot run in a normal transaction block |
| Editing `relfrozenxid` manually is faster | Can corrupt the database; only VACUUM machinery may manage horizons |
| Resetting the XID counter is a fix | Never manually reset counters |

## 29. Practice Exercises with Answers

Exercises use the PostgreSQL lab and catalog views. Run `VACUUM` standalone, never inside a transaction block.

### Exercise 1. Why is freezing needed?

**Answer:** 32-bit XIDs wrap around; freezing marks old tuples so PostgreSQL never has to misinterpret an old XID as a new transaction after the counter wraps.

### Exercise 2. How wide is a normal XID?

**Answer:** 32 bits.

### Exercise 3. What is half the XID space?

**Answer:** `2^31`, or 2,147,483,648; this is the critical safety boundary for XID comparison.

### Exercise 4. What special value is `FrozenTransactionId`?

**Answer:** XID 2.

### Exercise 5. What does a tuple's `xmin` represent?

**Answer:** The transaction ID that created that tuple version.

### Exercise 6. Is `xmax` always the transaction that deleted a row?

**Answer:** No. It can represent delete/update or row-lock metadata, including a MultiXact where applicable.

### Exercise 7. Does freezing make a row immutable?

**Answer:** No. The tuple can still be updated or deleted; freezing only alters how old transaction metadata is interpreted.

### Exercise 8. Which function checks XID age?

```sql
SELECT age(datfrozenxid)
FROM pg_catalog.pg_database
WHERE datname = current_database();
```

**Answer:** `age(xid)`.

### Exercise 9. Why not use `MAX(relfrozenxid)`?

**Answer:** XIDs wrap around, so ordinary arithmetic comparison cannot determine true transaction age.

### Exercise 10. Which catalog stores `relfrozenxid`?

**Answer:** `pg_class`.

### Exercise 11. Where is `datfrozenxid` stored?

**Answer:** `pg_database`.

### Exercise 12. What does `relminmxid` track?

**Answer:** The oldest MultiXact ID a relation might still need.

### Exercise 13. What does `datminmxid` track?

**Answer:** The oldest MultiXact ID tracked at the database level.

### Exercise 14. Which function measures MXID age?

**Answer:** `mxid_age()`.

### Exercise 15. Why monitor MXID age even when XID age is low?

**Answer:** MultiXacts have their own counter and freeze lifecycle, which can advance rapidly under row-locking workloads.

### Exercise 16. What is the role of `vacuum_freeze_min_age`?

**Answer:** The age threshold at which VACUUM considers freezing tuples.

### Exercise 17. What is the role of `vacuum_freeze_table_age`?

**Answer:** The threshold triggering an aggressive scan of a relation to advance its freeze horizon.

### Exercise 18. What is the role of `autovacuum_freeze_max_age`?

**Answer:** The relation age at which anti-wraparound autovacuum is triggered.

### Exercise 19. What is the common default for `autovacuum_freeze_max_age`?

**Answer:** Roughly 200 million XIDs, though you must check actual server config and version.

### Exercise 20. Should you raise `freeze_max_age` when vacuum is slow?

**Answer:** Do not treat it as a default fix; it postpones vacuum, shrinks safety margins, and increases transaction status retention.

### Exercise 21. Do append-only tables need freezing?

**Answer:** Yes. Old tuples still hold old XIDs even without dead tuples.

### Exercise 22. Does `n_dead_tup = 0` prove a table is frozen?

**Answer:** No. That is a dead-tuple estimate, not XID age or freeze status.

### Exercise 23. How do all-visible and all-frozen differ?

**Answer:** All-frozen is stronger; all-visible does not prove every XID on the page is frozen.

### Exercise 24. What does aggressive vacuum do?

**Answer:** Scans pages that may still hold unfrozen XIDs to advance `relfrozenxid`, including pages that are all-visible but not yet all-frozen.

### Exercise 25. Is `VACUUM (FREEZE)` equivalent to `VACUUM FULL`?

**Answer:** No. `FREEZE` requests stronger freezing; `FULL` rewrites the table and takes a strong lock.

### Exercise 26. Can `VACUUM` run inside an explicit transaction block?

**Answer:** No; run `VACUUM` as a standalone statement.

### Exercise 27. Does standard `VACUUM` freeze tuples?

**Answer:** Yes, according to freeze age settings and visibility conditions.

### Exercise 28. Does anti-wraparound vacuum depend on dead tuple count?

**Answer:** No. It triggers on transaction/MultiXact age.

### Exercise 29. Can PostgreSQL launch anti-wraparound workers when `autovacuum` is disabled?

**Answer:** PostgreSQL still has mechanisms to run required vacuums to prevent wraparound; disabling regular autovacuum remains very dangerous.

### Exercise 30. What is failsafe vacuum for?

**Answer:** Prioritizing freezing completion when age becomes critically high, potentially bypassing throttling and skipping index cleanup.

### Exercise 31. Can a long-running read-only transaction block VACUUM?

**Answer:** Yes. An old snapshot can pin the vacuum horizon even if the transaction performs no writes.

### Exercise 32. Why is `idle in transaction` dangerous?

**Answer:** It holds transactions, snapshots, and locks while the application does no useful work, blocking cleanup and freezing.

### Exercise 33. Can prepared transactions hold the horizon?

**Answer:** Yes. They hold transaction state and locks until committed or rolled back prepared.

### Exercise 34. Which replication slot fields relate to the XID horizon?

**Answer:** `xmin` and `catalog_xmin`; `restart_lsn` is a separate WAL retention marker.

### Exercise 35. How can `hot_standby_feedback` affect the primary?

**Answer:** The standby sends `xmin` to the primary, which can pin the vacuum horizon and slow cleanup/freezing.

### Exercise 36. Query to find the database with the highest age?

```sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

**Answer:** Sort descending by `age(datfrozenxid)`.

### Exercise 37. Which catalogs are queried to find the highest-age relations?

**Answer:** `pg_class` joined with `pg_namespace`, ordered by `age(relfrozenxid)`.

### Exercise 38. Why must TOAST relations be checked?

**Answer:** TOAST is an auxiliary storage relation holding tuple data with its own XID/MultiXact metadata that must be vacuumed/frozen.

### Exercise 39. Does checking the partitioned parent cover the whole partition tree?

**Answer:** No. Inspect each heap partition and TOAST relation that holds storage.

### Exercise 40. What does `pg_stat_progress_vacuum` provide?

**Answer:** Tracks PID, relation, phase, and heap/index progress of running vacuums.

### Exercise 41. How do `n_dead_tup` and `age(relfrozenxid)` differ?

**Answer:** One estimates dead tuples; the other measures XID freeze horizon age.

### Exercise 42. Why should you not cancel an anti-wraparound vacuum due to higher I/O?

**Answer:** It can let age keep climbing toward the danger zone; inspect the worker and capacity before intervening.

### Exercise 43. Can you manually edit `pg_class.relfrozenxid`?

**Answer:** No. Only PostgreSQL's VACUUM and transaction machinery may manage these horizons.

### Exercise 44. Does deleting all old rows replace freezing?

**Answer:** No. DELETE generates transaction metadata and dead tuples; proper VACUUM freeze is required.

### Exercise 45. If a batch import drives XID age up rapidly, what should you inspect?

**Answer:** Write throughput, transaction rate, autovacuum progress, long snapshots, replication slots, and freeze thresholds.

### Exercise 46. Why can an aggressive scan on a huge relation take a long time?

**Answer:** VACUUM must read many heap pages to inspect and freeze tuples still carrying old XIDs.

### Exercise 47. What can `vacuumdb --all --freeze` help with?

**Answer:** Requests freeze vacuums across multiple databases; choose sensible concurrency and verify every database afterward.

### Exercise 48. Why not drop an inactive slot immediately?

**Answer:** The slot may belong to a subscriber/replica needing resync; confirm owner, retention, and recovery plan first.

### Exercise 49. When age is high, which blockers should be checked first?

**Answer:** Long transactions, `idle in transaction`, prepared xacts, replication slots, and standby feedback.

### Exercise 50. When a database refuses transactions due to wraparound, should you reset counters manually?

**Answer:** Absolutely not. Follow the recovery procedure for your exact PostgreSQL major version with an experienced DBA.

### Exercise 51. Does `VACUUM FREEZE` guarantee age becomes 0?

**Answer:** No. Transaction horizons and visibility conditions can keep the cutoff from advancing all the way.

### Exercise 52. Why can too low an `autovacuum_max_workers` setting cause trouble?

**Answer:** Multiple relations needing vacuum compete for worker slots, causing anti-wraparound work to fall behind.

### Exercise 53. Is adding more workers always better?

**Answer:** No. It requires I/O and CPU headroom; too many workers cause contention.

### Exercise 54. Does failsafe replace monitoring?

**Answer:** No. Failsafe is a last-resort safeguard; monitoring must catch rising age early.

### Exercise 55. Does vacuuming one database make the whole cluster safe?

**Answer:** No. Every database has its own `datfrozenxid`/`datminmxid`; monitor all of them.

### Exercise 56. Which workloads commonly generate MultiXacts?

**Answer:** Concurrent transactions holding shared/overlapping row locks, such as `SELECT ... FOR UPDATE`/`SHARE` and concurrent locking.

### Exercise 57. What problem can using `VACUUM FULL` to fight wraparound cause?

**Answer:** Heavy rewrite I/O and `ACCESS EXCLUSIVE` locks; it is not the proper way to advance freeze horizons.

### Exercise 58. Which metrics belong in alerts?

**Answer:** Database XID age, MXID age, percentage of freeze max age, oldest relation age, vacuum progress, blockers, slot `xmin`/`catalog_xmin`, and autovacuum duration.

### Exercise 59. What should you verify after a manual vacuum?

**Answer:** That database/relation age advanced, workers/logs completed cleanly, blockers cleared, and warnings stopped growing.

### Exercise 60. Build a checklist for handling an anti-wraparound warning

**Suggested answer:**

1. Rank all databases by `age(datfrozenxid)` and `mxid_age(datminmxid)`.
2. Locate relations, TOAST tables, and catalogs with the highest ages.
3. Check autovacuum workers and `pg_stat_progress_vacuum`.
4. Find long transactions, `idle in transaction` sessions, and prepared transactions.
5. Check `pg_replication_slots` (`xmin`/`catalog_xmin`) and standby feedback.
6. Ensure storage/I/O/capacity is sufficient for aggressive vacuum.
7. Never cancel anti-wraparound workers without understanding the consequences.
8. Run planned `VACUUM FREEZE` on the needed relations/databases.
9. Verify ages decreased and all databases are back within safety margins.
10. Address root causes, alerts, and runbooks to prevent recurrence.

## 30. Production Operations Checklist

| Check | What to Ensure |
| --- | --- |
| XID age across all databases? | Dashboards and alerts configured |
| MXID age across all databases? | Separate dashboards and alerts configured |
| Relation age? | Query for top oldest relations |
| TOAST relation age? | Included in checks |
| System catalog age? | Monitored |
| Freeze thresholds? | Verified for exact version |
| Autovacuum enabled? | Yes |
| Anti-wraparound worker logs? | Monitored |
| Autovacuum worker capacity? | Sized for throughput |
| Vacuum cost settings? | Matched to storage |
| Failsafe age? | Understood, never used as a target |
| Long transactions? | Alerted by age |
| Idle in transaction? | Timeouts and monitoring active |
| Prepared transactions? | Owner and runbook defined |
| Replication slots? | Track active status, `xmin`, `catalog_xmin` |
| Standby feedback? | Horizon impact evaluated |
| Partitioned tables? | Every leaf partition tracked |
| Append-only tables? | Still getting frozen |
| Table `reloptions`? | Audited |
| Manual VACUUM plan? | Documented runbook |
| VACUUM FULL? | Not used as a freeze substitute |
| Recovery procedure? | Documented for exact major version |
| System catalog modifications? | Manual edits forbidden |
| Post-vacuum age? | Explicitly verified |
| Storage headroom? | Sufficient for vacuum and WAL |
| Write rate? | XID allocation trend tracked |
| MultiXact workload? | Monitored |
| Replication lag? | Monitored alongside slot horizons |
| Incident response? | Clear owner assigned |
| Backup/restore? | Recovery tested |

## 31. Summary

Freezing enables PostgreSQL to keep interpreting tuple visibility accurately when 32-bit transaction IDs wrap around. Consequently, VACUUM does not merely reclaim dead tuples—it protects the correctness of the entire database.

Key principles to remember:

1. **Normal XIDs are 32-bit.** Wraparound is an architectural limit that must be managed through freezing.
2. **Tuple `xmin`/`xmax` store transaction metadata.** Never edit system columns directly.
3. **`FrozenTransactionId` marks frozen tuples.** Frozen tuples can still be updated later.
4. **`relfrozenxid` and `datfrozenxid` are critical horizons.** Use `age()` to measure age, never naive arithmetic comparisons.
5. **MultiXacts have their own lifecycle.** Track `relminmxid`, `datminmxid`, and `mxid_age()`.
6. **Freeze age, aggressive scan age, and anti-wraparound age are distinct.** Understand each setting before tuning.
7. **Append-only tables still require freezing.** Low dead tuple counts do not prove XID age is safe.
8. **All-visible does not mean all-frozen.** Aggressive vacuum must inspect every page that could still hold unfrozen XIDs.
9. **`VACUUM FREEZE` differs from `VACUUM FULL`.** Never use a table rewrite with `ACCESS EXCLUSIVE` locking as a substitute for freezing.
10. **Anti-wraparound autovacuum is an essential safeguard.** Never disable or cancel it arbitrarily.
11. **Failsafe is the last line of defense.** Monitoring and capacity should let vacuum finish well before that limit.
12. **Long transactions and replication horizons can block freezing.** Check `pg_stat_activity`, prepared transactions, slots, and standby feedback.
13. **Inspect relation age, not only database age.** TOAST relations and system catalogs must be tracked too.
14. **Do not raise `freeze_max_age` to hide slow vacuuming.** Fix blockers, throughput, and transaction lifetimes.
15. **Never reset XIDs or edit catalogs manually.** If transaction refusal occurs, follow the recovery procedure for your exact major version.
16. **Verify after every action.** Confirm XID/MXID ages advance and safety margins recover.

Diagnostic flow:

```text
Database XID/MXID age rising
          |
          v
Find oldest relation
          |
          v
Is VACUUM running and advancing?
          |
      +---+---+
      |       |
     Yes      No
      |       |
      v       v
Is age      Find blockers:
dropping?   transaction / slot /
      |     prepared xact / capacity
  +---+---+
  |       |
 Yes      No
  |       |
  v       v
Keep      Resolve blocker,
monitoring vacuum per runbook
          |
          v
   Verify safety margin
```

**Final review question:** "If a table has almost zero dead tuples yet `age(relfrozenxid)` keeps climbing, will our system detect and freeze that table? If autovacuum fails to advance, can we pinpoint the transaction or replication slot pinning the horizon? And if the database nears wraparound, does our runbook protect the data without manually resetting XIDs?" Only when you can answer these with concrete metrics, catalog queries, and operational procedures is your system truly protected against wraparound.
