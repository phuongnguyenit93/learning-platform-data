# Selecting synchronous_standby_names and Acknowledgement Levels in PostgreSQL

## 1. Why select standbys and acknowledgement levels?

PostgreSQL supports **synchronous streaming replication** so the primary confirms a transaction `COMMIT` only after one or more standbys respond at the level required by the transaction. This mechanism reduces the risk of losing confirmed transactions when the primary fails, provided the failover process promotes the right standby holding the required WAL.

Two settings work together:

- **`synchronous_standby_names`** specifies which standbys can participate synchronously and how many standbys the primary needs responses from. There are two main selection modes: priority-based `FIRST` and quorum-based `ANY`.
- **`synchronous_commit`** determines how far the primary must wait: until the standby has written WAL, flushed WAL to storage, or replayed WAL so changes become readable.

Choosing these two parameters correctly is a decision about durability, availability, latency, and topology. A stronger acknowledgement level can reduce RPO, yet makes `COMMIT` dependent on the network and standby health. Quorum selection can improve commit continuity when some standbys are unavailable, yet requires understanding quorum behavior and how to pick the promotion target.

This lesson focuses on physical streaming replication in PostgreSQL. Logical replication has different semantics and configuration; do not mechanically apply the synchronous standby examples below to logical subscribers.

### 1.1. Learning objectives

After this lesson, you will be able to:

1. Explain synchronous replication and the WAL path from primary to standby.
2. Distinguish configured standbys, connected standbys, and currently selected synchronous standbys.
3. Write `synchronous_standby_names` configurations using `FIRST` and `ANY`.
4. Distinguish priority-based replication from quorum-based replication.
5. Understand `synchronous_commit` levels: `off`, `local`, `remote_write`, `on`, and `remote_apply`.
6. Choose the acknowledgement level matching RPO, RTO, and read-after-write requirements.
7. Monitor sync state, LSN positions, and backends waiting on `SyncRep`.
8. Handle standby disconnects, lag, network partitions, and synchronous commit stalls.
9. Design topologies with sufficient standbys, failure domains, and safe promotion procedures.
10. Practice configuration, observation, and diagnostics in a lab environment.

### 1.2. Key principles to remember

- `synchronous_standby_names` selects **standby participants**; `synchronous_commit` selects the **acknowledgement level** for a transaction.
- A standby listed in configuration is not necessarily an active synchronous standby right now.
- `remote_write`, `on`, and `remote_apply` offer different levels of guarantee.
- `local` and `off` do not wait for synchronous standby responses.
- Synchronous replication can cause `COMMIT` to wait when too few standbys satisfy the quorum/priority set.
- Synchronous replication does not perform automatic failover and does not replace backups/PITR.
- After failover, you must promote the standby holding the latest WAL covering confirmed commits; never blindly pick the highest-priority name.
- Always verify actual configuration and runtime state using system views, logs, and failover drills.

---

## 2. The WAL path in synchronous replication

### 2.1. Components

A basic topology includes:

- **Primary:** receives application writes, generates WAL records, and sends WAL over replication connections.
- **WAL sender:** primary process transmitting WAL to standbys.
- **Standby:** receives WAL, writes/flushes it to WAL files, and replays it to apply changes.
- **WAL receiver:** standby process receiving the stream from the primary.
- **Synchronous replication wait logic:** primary waits for responses from the configured number of standbys before returning `COMMIT` at the requested level.

### 2.2. Overall flow

~~~text
Application
    |
    | BEGIN / UPDATE / COMMIT
    v
Primary backend
    |
    +--> Create WAL records
    |
    +--> Local WAL write/flush
    |
    +--> WAL sender streams records
             |
             v
        Standby WAL receiver
             |
             +--> Write WAL
             |
             +--> Flush WAL
             |
             +--> Replay WAL
             |
             +--> Send progress feedback
                      |
                      v
Primary evaluates synchronous_standby_names
                      |
                      v
Commit acknowledgement when requested level is met
~~~

The diagram is a conceptual model. PostgreSQL can batch writes, perform group commits, and handle multiple standbys concurrently. Specific milestones depend on `synchronous_commit`.

### 2.3. Why must the primary wait?

If the primary confirms `COMMIT` right after local write/flush without waiting for a standby, the application may receive success while the standby lacks the corresponding WAL. If the primary fails and an out-of-date standby is promoted, the just-confirmed transaction can be lost.

Synchronous replication lets the primary wait for an acknowledgement level from a standby. This narrows the data-loss window when failover is executed properly.

### 2.4. Three stages on the standby

Three milestones can be distinguished:

1. **Write:** standby has written WAL bytes to the OS/file layer per PostgreSQL semantics.
2. **Flush:** standby has flushed WAL to persistent storage per sync method/storage stack.
3. **Replay/apply:** standby has replayed WAL and applied changes to data files.

These milestones normally progress in order, yet are not equivalent:
- Written WAL is not guaranteed durable across an OS crash/power loss.
- Flushed WAL is not guaranteed visible to standby queries because replay may lag.
- Replayed WAL does not automatically make an already-open transaction with an older snapshot see those changes.

### 2.5. What feedback does the primary receive?

The standby sends WAL progress feedback. The primary uses write/flush/replay positions to decide whether the standby has reached the transaction's required acknowledgement level.

Do not use a single lag number to represent everything. Know whether you are inspecting write lag, flush lag, or replay lag.

---

## 3. The two main parameters and their relationship

### 3.1. synchronous_standby_names

This parameter is configured on the primary. It lists standby names and how many responses are required. A standby name must match the `application_name` of the standby's replication connection.

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

The primary prioritizes `standby_a`; if that standby is no longer eligible/connected, `standby_b` can be chosen as the synchronous standby.

### 3.2. synchronous_commit

This parameter controls which acknowledgement level a transaction waits for. It can be set at server, session, or transaction scope.

Example:

~~~sql
SHOW synchronous_commit;

BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'paid'
WHERE order_id = 1001;

COMMIT;
~~~

In the example, the transaction requests waiting until the synchronous standby replays the commit record per PostgreSQL semantics.

### 3.3. Division of responsibilities

| Parameter | Question answered |
|---|---|
| `synchronous_standby_names` | Which standbys participate and how many responses are needed? |
| `synchronous_commit` | Must the transaction wait for write, flush, or apply? |

You can configure multiple standbys while a transaction requests only local commit; conversely, you can set `remote_apply`, yet if no synchronous standby is configured, there is no remote apply acknowledgement to wait on.

### 3.4. Do not confuse with synchronous_commit=on

`synchronous_standby_names` does not choose the commit acknowledgement level. `synchronous_commit` decides how far to wait. For example, if `synchronous_standby_names` selected a standby yet a transaction sets `synchronous_commit=local`, that transaction waits only for local flush.

### 3.5. Per-transaction configuration

Different workloads can require different acknowledgement levels. A critical transaction might require `remote_apply`; a reproducible job from another source might use a weaker level per policy.

Use `SET LOCAL` inside a transaction so the change lasts only for that transaction:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'on';

INSERT INTO app.payment_ledger(payment_id, amount)
VALUES ('pay-1001', 250.00);

COMMIT;
~~~

Choosing a weaker level must be an intentional decision; do not let a connection pool accidentally carry the setting over to subsequent requests.

---

## 4. synchronous_standby_names: syntax and standby names

### 4.1. FIRST syntax

Priority-based form:

~~~conf
synchronous_standby_names = 'FIRST num_sync (standby_name [, ...])'
~~~

`num_sync` is the number of standbys from which a transaction must receive responses. Names in the list are ordered by priority from left to right.

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (dc1_standby, dc2_standby, dc3_standby)'
~~~

The primary chooses the first connected, eligible standby in the list. If a higher-priority standby disconnects, the next standby can be chosen.

### 4.2. ANY syntax

Quorum-based form:

~~~conf
synchronous_standby_names = 'ANY num_sync (standby_name [, ...])'
~~~

Example:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

The primary waits for responses from any two standbys in the list. All standbys in the quorum list share equal priority status; `num_sync` defines the required response count.

### 4.3. Without FIRST/ANY

The legacy syntax omitting the `FIRST` keyword is interpreted as priority-based selection:

~~~conf
synchronous_standby_names = '1 (standby_a, standby_b)'
~~~

Writing `FIRST 1` explicitly makes it easier for operators to read.

### 4.4. Names must match application_name

On a standby, the replication connection can be configured as:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=replicator application_name=standby_a'
~~~

The `application_name=standby_a` value must match `standby_a` on the primary.

If misnamed, the standby can still stream yet will not be chosen as a synchronous standby. Always check `pg_stat_replication.application_name` and `sync_state` rather than merely checking that a connection is established.

### 4.5. Unique and clear names

Use a unique name for each standby:
- `dc1_standby_a`
- `dc1_standby_b`
- `dc2_standby_a`

Avoid letting multiple standbys share the same `application_name` without a deliberate architectural reason. Clear names simplify reading monitoring, priorities, and incident logs.

### 4.6. Where does this parameter live?

`synchronous_standby_names` is configured on the primary. It is not set on a standby for the standby to choose another node as a synchronous partner.

You can check:

~~~sql
SHOW synchronous_standby_names;

SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN ('synchronous_standby_names', 'synchronous_commit');
~~~

### 4.7. Invalid or unreachable counts

If `num_sync` exceeds the number of standby names or the number of standbys able to connect, the primary may never receive enough responses to release synchronous commit waits. Ensure your design includes sufficient nodes and corresponding fault tolerance.

### 4.8. Empty configuration

If `synchronous_standby_names` is empty, no synchronous standby is selected. Physical streaming replication can still run asynchronously; commits do not wait for remote acknowledgements.

This change directly affects durability. If altered during an incident to unblock commits, record the RPO exposure and when synchronous policy will be re-enabled.

---

## 5. FIRST: priority-based synchronous replication

### 5.1. FIRST 1 with two standbys

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Assume:
- `standby_a` is streaming.
- `standby_b` is streaming.

`standby_a` has higher priority so it is chosen as the synchronous standby. `standby_b` remains a useful physical standby, though it does not necessarily participate in every commit acknowledgement.

If `standby_a` disconnects, `standby_b` can become the synchronous standby once selected.

### 5.2. FIRST 2 with three standbys

~~~conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
~~~

The primary selects the two highest-priority eligible standbys. If all three are connected, `standby_a` and `standby_b` are chosen; `standby_c` may act as a `potential` standby.

If either priority node disconnects, the next node can take its place to maintain a count of two, provided enough eligible standbys remain.

### 5.3. Meaning of priority

The list defines priority order, not network latency order. If `standby_a` is still considered connected/eligible yet responds slowly, the primary can keep waiting on it per priority policy rather than automatically switching to a faster standby.

Do not treat `FIRST` as latency-aware load balancing.

### 5.4. Advantages

- Identifies a preferred standby for HA.
- Can designate a local site/region as the primary synchronous partner.
- Provides ordered fallback down the list when higher-priority standbys are no longer eligible.
- Easy to reason about in simple topologies like one primary and one main synchronous standby.

### 5.5. Limitations

- If the priority standby remains connected yet slow, commit latency can rise.
- With `FIRST 1`, only one standby is chosen as synchronous participant at a time.
- Other standbys can lag and lack every confirmed commit when the primary fails.
- Promotion must pick the node with the latest appropriate WAL, not merely the first name in the list.

### 5.6. When it fits

Use `FIRST` when there is a clearly preferred primary standby—such as a low-latency node in the same site as the primary—with other standbys serving as fallback/DR. Maintain a runbook verifying sync state and failover selection.

---

## 6. ANY: quorum-based synchronous replication

### 6.1. ANY 1 of three standbys

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
~~~

Transactions require one response from any standby among the three nodes. Whichever node responds first contributes to the quorum for that commit.

### 6.2. ANY 2 of three standbys

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Transactions require two responses from any two standbys in the list. If one standby is unavailable while the other two remain healthy, commits still satisfy quorum.

### 6.3. Meaning of quorum

Quorum is the count of responses required to confirm a commit. With `ANY 2` of three nodes, each commit needs at least two acknowledgements at the level required by `synchronous_commit`.

Quorum does not mean all standbys always share the exact same LSN. Nodes can have different lag, and which nodes respond fastest can vary from commit to commit.

### 6.4. Advantages

- Does not statically depend on one specific standby.
- Can continue committing when some standbys are slow or unavailable, as long as quorum holds.
- Useful in topologies with multiple standbys across different failure domains.
- Can lower tail latency compared to waiting for all standbys if quorum size is smaller than total node count.

### 6.5. Limitations

- Must determine which node actually holds the latest WAL before promotion.
- Standbys can be at different progress levels.
- Promoting the wrong node can lose commits that node lacked.
- Quorum is meaningful only if the list, node count, and failure domains are designed properly.

### 6.6. ANY does not mean every node is synchronous

If configured as `ANY 2` across three standbys, each transaction needs only two responses. The third node may not have flushed up to that commit LSN when the commit is confirmed.

### 6.7. When it fits

`ANY` fits when you have multiple peer standbys and want to tolerate one or more node/network failures while maintaining quorum. Size the quorum based on topology, latency, failure correlation, and promotion policy.

---

## 7. Comparing FIRST and ANY

| Criterion | FIRST (priority) | ANY (quorum) |
|---|---|---|
| Selection method | By priority order | Any up to required count |
| Responding standbys | Nodes chosen by priority | Any `num_sync` nodes |
| Fallback | Switches to next eligible node | Remaining nodes can still satisfy quorum |
| Preferred node | Yes | Does not use priority to form quorum |
| Best suited for | One primary standby plus fallback | Multiple peer standbys |
| Key caveat | A slow priority node can drag commit latency | Promotion must pick the node with newest WAL |

### 7.1. Configuration examples

**Topology A:** primary in region A, low-latency standby A1 in the same region, standby B1 in region B for DR.

Possible config:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a1, standby_b1)'
~~~

Evaluate the impact if standby A1 disconnects and commits wait on B1 across the WAN with higher latency.

**Topology B:** primary in main site, three peer standbys across three failure domains.

Consider:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Choose quorum and promotion policy carefully; never promote a node solely because its process is running.

### 7.2. No single configuration fits every topology

Configuration depends on:
- Number of standbys and failure domains.
- RTT between primary/standbys.
- Storage flush latency.
- RPO/RTO.
- Tolerance for standby outages.
- How the HA manager selects/promotes nodes.
- Workload commit rate.
- Tolerance for write unavailability.

### 7.3. FIRST 1 vs ANY 1

Both require one response, yet selection differs:
- `FIRST 1` picks the highest-priority eligible node.
- `ANY 1` lets any node in the quorum list respond.

`ANY 1` reduces dependence on a single priority node, while failover selection must still inspect WAL progress.

### 7.4. FIRST N vs ANY N

With `FIRST N`, the primary waits for the N priority-selected standbys. With `ANY N`, the primary waits for any N responses from the list. If N equals the total number of standby names, both require all listed nodes to respond, even though selection semantics differ.

---

## 8. synchronous_commit: acknowledgement levels

### 8.1. Overview table

| Value | Local WAL flush | Remote write | Remote flush | Remote apply |
|---|---:|---:|---:|---:|
| `off` | Do not wait | Do not wait | Do not wait | Do not wait |
| `local` | Yes | Do not wait | Do not wait | Do not wait |
| `remote_write` | Yes | Yes | Not required | Not required |
| `on` | Yes | Yes and flush | Yes | Not required |
| `remote_apply` | Yes | Yes and flush | Yes | Yes |

The table describes requirements under synchronous replication. When no synchronous standby is configured, remote modes have no remote acknowledgement to wait on; durability depends on local WAL behavior.

### 8.2. off

`synchronous_commit=off` allows the server to return `COMMIT` success before the corresponding WAL is flushed to local storage. This can lower commit latency.

Trade-off:
- Some recently confirmed transactions can be lost if the server/OS/storage crashes before flush.
- The database is still designed to maintain consistency; async commit does not mean permitting corruption.
- WAL is still generated; `off` does not disable WAL logging.
- Not suitable for all business transactions.

### 8.3. local

`synchronous_commit=local` waits for local WAL flush without waiting for a synchronous standby. This provides local durability: transactions are confirmed after local flush per storage assumptions, while a remote standby may not have received/flushed the commit record yet.

Use when a transaction requires local durability without remote synchronous acknowledgement, or under a deliberate policy.

### 8.4. remote_write

`synchronous_commit=remote_write` waits for local WAL flush and for the standby to confirm WAL has been written to the OS/file layer. It does not wait for remote `fsync`/durable flush to persistent storage.

The advantage is typically lower latency than remote flush. The trade-off is that a standby OS crash or power loss can lose WAL bytes not yet durably flushed. Understand exact storage/OS semantics.

### 8.5. on

`synchronous_commit=on` is the common default. When synchronous replication is configured, the primary waits for local WAL flush and for the synchronous standby to flush WAL to persistent storage per PostgreSQL mechanisms.

This is the common choice when you want acknowledged commits protected on both the primary and synchronous standby, provided failover promotes a node holding that WAL.

### 8.6. remote_apply

`synchronous_commit=remote_apply` waits for the synchronous standby to replay the commit record, meaning the transaction has been applied and can be visible to new queries on the standby under MVCC.

Use when read-after-write from a standby is needed:
1. Client writes on the primary.
2. `COMMIT` waits for standby replay.
3. After `COMMIT` returns, the client reads inside a new transaction/snapshot on the standby.
4. The query can see the committed transaction.

A read transaction already holding an older snapshot may still miss the new row even after standby replay; `remote_apply` does not alter snapshot isolation.

### 8.7. Why is remote_apply slower than on?

Remote apply includes the standby replaying WAL, not merely writing/flushing bytes. Replay can be bottlenecked by CPU, I/O, standby workload, or hot standby conflicts. On read-heavy standbys, long-running queries can impact recovery/replay depending on conflict settings.

### 8.8. Which level is "strongest"?

Among the levels above, `remote_apply` demands the furthest progress on the standby: replay. However, "strongest" does not solve every failure mode. Evaluate storage durability, standby count, failure domains, promotion policy, backups, and corruption scenarios.

### 8.9. Do not confuse remote_write with remote_flush

- Remote write: WAL has been written to the OS/file layer on the standby.
- Remote flush: WAL has been flushed along the durability path.
- Remote apply: WAL has been replayed.

These are distinct acknowledgement levels with different latency and risk profiles.

---

## 9. Relationship between standby count and commit level

### 9.1. FIRST 1 + on

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

The primary waits for one priority-selected standby to flush WAL. The remaining standby can continue as async/`potential` depending on selection state.

### 9.2. FIRST 2 + on

~~~conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
synchronous_commit = on
~~~

The primary waits for two selected standbys to flush WAL. If only one node is eligible, commits requiring synchronous acknowledgement can wait.

### 9.3. ANY 2 + on

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
synchronous_commit = on
~~~

The primary waits for any two standbys in the list to flush commit WAL. If one node disconnects, the remaining two nodes can still satisfy quorum.

### 9.4. ANY 2 + remote_apply

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
synchronous_commit = remote_apply
~~~

The primary waits for any two standbys to replay the commit record. This gives stronger read visibility across responding standbys, at potentially higher latency.

### 9.5. local override

Even when the primary has synchronous standby names configured:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = local;
UPDATE app.metrics SET value = value + 1 WHERE metric_id = 10;
COMMIT;
~~~

This transaction waits only for local WAL flush. It is not protected by remote synchronous acknowledgement like a transaction using `on`/`remote_apply`.

### 9.6. Off override

~~~sql
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO app.rebuild_queue(job_id) VALUES ('rebuild-42');
COMMIT;
~~~

Use only if the business accepts losing a recently confirmed transaction in a crash. If the queue is the sole record for critical work, `off` may be inappropriate.

---

## 10. Standby selection and status in pg_stat_replication

### 10.1. Observing on the primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
~~~

This view shows active WAL sender connections and each standby's sync state.

### 10.2. Common sync_state values

Common values include:
- `async`: standby is asynchronous.
- `potential`: eligible standby that could be selected by priority but is not currently in the synchronous set.
- `sync`: standby currently selected as synchronous in a priority-based configuration.
- `quorum`: standby participating in a quorum-based synchronous configuration.

Verify exact names/states for your version; read `sync_priority` together with `sync_state` and active config.

### 10.3. sync_priority

In a priority-based setup, priority numbers clarify selection order. Selected standbys have higher priority per list order. In a quorum setup, do not interpret priority as an ordering deciding which node wins quorum.

### 10.4. LSN positions

- `sent_lsn`: position sent by the WAL sender.
- `write_lsn`: position written by the standby.
- `flush_lsn`: position flushed by the standby.
- `replay_lsn`: position replayed by the standby.

Byte distances can be computed:

~~~sql
SELECT
    application_name,
    sync_state,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)::bigint
    ) AS flush_behind,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS replay_behind
FROM pg_stat_replication
WHERE flush_lsn IS NOT NULL;
~~~

These are byte LSN distances near query time, not exact time latency. If the primary is idle, lag timestamps may not reflect true lag in seconds.

### 10.5. Viewing backends waiting on SyncRep

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

The `SyncRep` wait event shows a backend waiting for a synchronous replication response. This is a key signal when `COMMIT` stalls due to missing standby acknowledgement.

### 10.6. Observing the receiver on the standby

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

Columns can vary across major versions. This view helps inspect receiver progress on the standby; combine with replay LSN and logs to understand apply lag.

### 10.7. Checking effective configuration

~~~sql
SHOW synchronous_standby_names;
SHOW synchronous_commit;

SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'synchronous_standby_names',
    'synchronous_commit',
    'wal_level',
    'wal_sender_timeout'
);
~~~

Verify the configuration actually active on the server, not just config files in a repository or automation. An edited config file that has not been reloaded is not yet effective.

---

## 11. Changing configuration and applying safely

### 11.1. Changing synchronous_standby_names

`synchronous_standby_names` can be reloaded in modern PostgreSQL versions; no server restart is needed for normal changes. Example using `ALTER SYSTEM` in a lab:

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'FIRST 1 (standby_a, standby_b)';

SELECT pg_reload_conf();

SHOW synchronous_standby_names;
~~~

In production, configuration may be managed by configuration management or include files. Use a single authoritative source to prevent drift between files and `ALTER SYSTEM`.

### 11.2. Verifying reload succeeded

`pg_reload_conf()` returns whether the reload signal was sent; it does not guarantee every setting is valid or a standby was selected. Check:
- PostgreSQL logs for parsing/configuration errors.
- `SHOW synchronous_standby_names` returns the expected value.
- `pg_stat_replication.sync_state` updated as intended.
- Commit behavior meets the desired level.

### 11.3. Setting synchronous_commit per session

~~~sql
SET synchronous_commit = 'on';
SHOW synchronous_commit;
~~~

A session setting persists across multiple transactions on the same connection. Connection pools must reset session state, or applications should use `SET LOCAL` inside transactions to avoid leaking settings between requests.

### 11.4. Setting per transaction

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.account_balance
SET balance = balance - 50
WHERE account_id = 10;

COMMIT;
~~~

`SET LOCAL` applies only to the current transaction. When the transaction ends, the session's prior setting is restored.

### 11.5. Changing standby application_name

If a standby changes `application_name` in `primary_conninfo`, the primary may stop recognizing it under the old name. Coordinate changes to the connection string and `synchronous_standby_names` so you do not create a gap without synchronous standbys.

### 11.6. Rollout sequence

A controlled rollout:
1. Verify all standbys are streaming and have unique names.
2. Confirm latency and write/flush/replay progress.
3. Update standby connection identities if needed.
4. Update the standby list on the primary.
5. Reload and check `sync_state`.
6. Run a test transaction at the desired acknowledgement level.
7. Check wait events, commit latency, and logs.
8. Update runbooks/failover policy.

Do not change topology, `application_name`, quorum size, and commit level simultaneously without a clear way to isolate the cause if something fails.

---

## 12. What happens when a standby is unavailable?

### 12.1. FIRST 1: priority standby disconnects

With:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

If `standby_a` disconnects and `standby_b` is eligible, `standby_b` can be selected as replacement. Commit waits can proceed once the primary selects the new synchronous standby.

### 12.2. FIRST 1: priority standby stays connected yet slow

If the priority standby stays connected yet responds slowly with WAL, the primary can keep waiting on that node. A fallback node will not automatically take over just because it is faster; selection is based on policy and eligibility, not latency-aware routing.

### 12.3. ANY 2: one standby disconnects

With:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

If one node disconnects, the remaining two nodes can still satisfy quorum. If only one eligible node remains, commits needing remote acknowledgement wait until quorum is restored or configuration/policy changes.

### 12.4. Too few standbys to satisfy num_sync

If eligible standbys fall below `num_sync`:
- Transactions using `on`, `remote_write`, or `remote_apply` can wait for synchronous acknowledgement.
- Transactions using `local` still wait for local WAL flush without waiting for standbys.
- Transactions using `off` can be confirmed before local WAL flush.
- Read-only transactions normally do not wait on synchronous commit like write transactions.

Do not assume the primary is broken just because `COMMIT` is waiting. Check wait events and standby status before acting.

### 12.5. Network partition

A network partition can prevent the WAL sender from receiving standby feedback. From the primary's perspective, the standby may appear alive yet unresponsive. Once the connection times out/disconnects, selection policy can pick another node if enough remain.

This is where durability and write availability collide: waiting preserves the acknowledgement level; stopping the wait weakens remote guarantees.

### 12.6. Can the primary still serve SELECT?

Synchronous replication mainly affects transactions needing synchronous commit. The primary can still serve reads and some other operations. However, write transactions may block at `COMMIT`, tying up connections and application resources.

### 12.7. Remediation when commits stall

In order:
1. Inspect backends waiting on `SyncRep`.
2. Inspect `pg_stat_replication` and standby `sync_state`.
3. Inspect network/WAL sender/receiver and logs.
4. Check standby disk flush/replay bottlenecks.
5. Restore the standby or network.
6. If the business requires restoring writes urgently, consider changing policy to asynchronous under an approved incident process.
7. Document RPO exposure and verify synchronous mode is restored post-incident.

Do not bulk-kill backends or drop standbys/slots before understanding transaction state and the failover plan.

### 12.8. Synchronous replication does not auto-timeout commits to a business threshold

There is no built-in setting in `synchronous_standby_names` meaning "wait 5 seconds for standby then commit asynchronously." Connection/keepalive timeouts and application timeouts have different semantics. If fallback after a threshold is desired, explicit orchestration/policy is required; do not confuse network timeouts with automatic quorum downgrade.

---

## 13. Latency, throughput, and acknowledgement costs

### 13.1. Commit latency

With synchronous replication, `COMMIT` duration is affected by:
- Local WAL flush.
- Primary–standby network RTT.
- Standby WAL write/flush latency.
- Replay speed if using `remote_apply`.
- Number of standbys required to respond.
- Group commit and concurrency.
- Storage queue depth and CPU contention.

### 13.2. FIRST 1

`FIRST 1` ties commit latency to the chosen standby. If that node is close to the primary, latency can stay low; if a distant fallback is selected, latency can rise markedly.

### 13.3. FIRST 2

`FIRST 2` waits for both chosen standbys. Latency is typically governed by the slower of the two responding nodes, since the transaction needs both acknowledgements.

### 13.4. ANY 2

`ANY 2` waits for two responses from the group. If three nodes have different latencies, the two fastest nodes can satisfy quorum. This can lower tail latency compared to waiting for all three, provided network/storage paths and node selection align.

### 13.5. remote_write, on, and remote_apply

- `remote_write` stops at remote OS write acknowledgement, usually waiting less than remote flush.
- `on` waits for remote flush, increasing durability across remote storage.
- `remote_apply` waits for replay, potentially increasing latency when standby apply is slow.

Never choose based on a single-transaction benchmark alone. Measure p50/p95/p99 commit latency under representative load.

### 13.6. Throughput and group commit

Group commit can coalesce multiple commits into one flush round, amortizing sync cost across transactions. Even so, synchronous replication adds a standby wait condition; when the standby bottlenecks, write throughput can drop and backend queues can grow.

### 13.7. Backpressure

If a standby falls behind, the primary can accumulate WAL and commit waiters. Monitor:
- Backends waiting on `SyncRep`.
- Commit latency.
- WAL sender send/write/flush/replay positions.
- Standby CPU/I/O.
- Disk queue/latency.
- Replication slot retention and `pg_wal` size.

### 13.8. Choosing quorum size

Increasing `num_sync`:
- Increases the number of nodes confirming each commit.
- Can improve data survival across multiple failure domains.
- Increases latency and reduces commit availability when nodes are unavailable.

Decreasing `num_sync`:
- Improves commit continuity when some nodes fail.
- Reduces required acknowledgements.
- Reduces the number of standbys guaranteed to have confirmed each commit.

Base decisions on RPO, failure model, and promotion policy, not machine count alone.

---

## 14. Topology design and failover

### 14.1. One synchronous standby and one asynchronous standby

~~~text
             +--> standby_sync (priority 1)
Primary -----|
             +--> standby_dr (async / fallback)
~~~

A `FIRST 1` configuration can prioritize the standby near the primary. The DR standby can be chosen as synchronous standby if the priority node becomes ineligible. Evaluate fallback latency and verify the DR node holds sufficient WAL before promotion.

### 14.2. Three standbys with quorum

~~~text
                  +--> standby_a
Primary ----------+--> standby_b
                  +--> standby_c

synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Each commit requires two acknowledgements. If one node fails, the remaining two nodes maintain quorum.

### 14.3. Failure domains

Placing all synchronous standbys on the same host/rack/storage array creates correlated failure risks. Distribute across appropriate failure domains while evaluating network latency and operability. Multi-region topologies with high RTT can substantially increase commit latency.

### 14.4. Choosing a node to promote

When the primary is lost:
- Identify which node holds the newest WAL.
- Compare receive/flush/replay LSNs.
- Inspect `sync_state` and the configuration effective before the outage.
- Verify timeline/history.
- Confirm the chosen node contains the commit WAL that must be preserved.
- Fence the old primary to prevent split brain.
- Promote via HA manager/runbook.

Never blindly pick the first standby in a `FIRST` config or an arbitrary standby in `ANY`.

### 14.5. FIRST is not fencing

A priority list determines synchronous standby selection on a running primary. It does not stop an old primary from accepting writes after a partition, nor does it guarantee a single leader. Fencing/STONITH/leases/quorum in the HA layer are a separate responsibility.

### 14.6. ANY is not consensus leader election

Synchronous replication's quorum acknowledgement does not replace distributed consensus or an HA manager. It governs how many standbys acknowledge WAL for a commit; deciding who is allowed to be primary still requires failover coordination and fencing.

### 14.7. Synchronous replication and backups

A synchronous standby can hold every commit confirmed at the corresponding level, yet it still replicates destructive operations and logical mistakes. You still need independent base backups, WAL archives, retention, and PITR.

### 14.8. Conditional zero RPO

Synchronous replication can meet the goal of not losing acknowledged commits within a designed failure model if:
- Transactions use an appropriate remote level.
- Standby acknowledgements were achieved.
- The promoted node actually holds that WAL.
- Storage/host failures do not simultaneously destroy all acknowledged copies.
- The old primary is fenced.
- No out-of-policy `local`/`off` overrides occurred.

Never claim `RPO=0` simply because `synchronous_standby_names` is non-empty.

---

## 15. Read-after-write on a standby

### 15.1. The replication lag issue

An application writing on the primary and immediately reading from a standby may miss the newly written row if the standby has not replayed up to the commit record. This is normal eventual consistency in asynchronous replication and can also happen in synchronous replication when waiting only for remote write/flush.

### 15.2. remote_apply

`synchronous_commit=remote_apply` waits for the synchronous standby to replay the commit record before the primary confirms commit. After the commit response returns, a new transaction on that standby can see those changes.

### 15.3. Stale snapshots

If an application keeps a read transaction open from before the commit, the older snapshot still will not see changes. Open a new read transaction/snapshot after commit when read-after-write is required.

### 15.4. Only some standbys acknowledged

With `ANY 1` across multiple standbys, a transaction may be replayed on the single node satisfying quorum while other nodes lag. If the application reads randomly across all standbys, a `remote_apply` acknowledgement on one standby does not guarantee all replicas have replayed.

### 15.5. Read routing

If strict read-after-write is required:
- Read from the primary for immediate post-write reads; or
- Pin the session/tenant to the standby that acknowledged the transaction if architecture supports it; or
- Use `remote_apply` and route to the responding synchronous standby; or
- Wait for the replica to replay up to the commit LSN before reading.

Do not rely on fixed `sleep` delays as a consistency guarantee.

---

## 16. Troubleshooting common scenarios

### 16.1. Standby streaming yet sync_state=async

Check:
1. Does `application_name` on the standby match the list?
2. Was `synchronous_standby_names` reloaded?
3. Are you inspecting the right primary?
4. Is the standby connection the right WAL sender?
5. Are `num_sync` and listed names feasible?
6. Is another higher-priority standby already selected?

### 16.2. sync_state=potential instead of sync

In priority mode, a standby can be eligible yet lower priority than the currently chosen node. Check the higher-priority standby ahead of it and connection/sync state.

### 16.3. COMMIT waiting a long time

Inspect:
- `pg_stat_activity.wait_event='SyncRep'`.
- `pg_stat_replication`.
- Network latency/loss.
- Standby flush/replay progress.
- Standby storage latency.
- Number of standbys required to respond.
- `synchronous_commit` at session/transaction level.

### 16.4. Only remote_apply is slow

If write/flush LSNs keep up while replay LSN lags, investigate apply/replay:
- CPU/IO on the standby.
- Long-running read queries/hot standby conflicts.
- Heavy WAL record workloads.
- Recovery process wait events/logs.
- Competing query load on the standby.

### 16.5. Standby reconnected yet commits still wait

Check:
- Does the standby have the right `application_name`?
- Has it entered `sync`/`quorum` state?
- Is the WAL receiver catching up?
- Are enough `num_sync` nodes available?
- Are there duplicate/invalid standby names?

### 16.6. Commit latency rises after failover

When a distant fallback standby becomes the synchronous partner, network RTT can increase. Re-measure commit latency and verify the current topology; do not assume failover preserves the original performance profile.

### 16.7. WAL disk growing

A slow synchronous standby can relate to replication progress and slots; disk growth also depends on archiving/retention. Check slot `restart_lsn`, archive failures, checkpoints, and WAL generation before drawing conclusions.

### 16.8. Too few synchronous standbys

If writes must continue without enough nodes:
- Restore the standby/network if possible.
- Consider lowering `num_sync` or switching to async only per incident policy.
- Record the time window and transactions exposed to lower durability.
- Identify which nodes received/flushed WAL.
- When the standby returns, check sync state and lag before declaring the system healthy.

---

## 17. Runbook when synchronous commits stall

1. Confirm scope: all writes or one application/transaction class.
2. Check `pg_stat_activity` and count backends waiting on `SyncRep`.
3. Read `SHOW synchronous_standby_names` and `SHOW synchronous_commit`.
4. Inspect `pg_stat_replication`: `application_name`, `state`, `sync_state`, priority, flush/replay LSNs.
5. Check primary/standby logs, WAL sender/receiver, and network.
6. Check storage latency and replay bottlenecks on standbys.
7. Compare currently eligible standbys against `num_sync`.
8. Restore the node/network or reduce standby load.
9. If switching to async to restore writes, record approval, timestamp, RPO exposure, and re-enable plan.
10. Post-incident, verify the right synchronous standby is selected and run a test transaction.
11. Review failover/promotion policy and update the postmortem.

Do not kill all backends waiting on `SyncRep` as a default response. An aborted `COMMIT` or dropped connection can leave an unknown outcome; applications need idempotency and reconciliation.

---

## 18. PostgreSQL reference documentation

Prefer documentation matching your server's exact major version:

- [PostgreSQL — Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous standby selection and acknowledgement.
- [PostgreSQL — Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): `synchronous_standby_names` and replication settings.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): `synchronous_commit` and durability settings.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_replication`, `pg_stat_wal_receiver`, and wait events.
- [PostgreSQL — Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication and failover.
- [PostgreSQL — Administrative Functions](https://www.postgresql.org/docs/current/functions-admin.html): reload configuration and WAL/LSN functions.
- [PostgreSQL — High Availability](https://www.postgresql.org/docs/current/high-availability.html): HA architectures and replication.

`/current/` pages can change over time. Verify syntax, wait events, view columns, and semantics against your running major version.

---

## 19. Lab: configuring and observing FIRST 1

### 19.1. Lab topology

Assume:
- Primary: writable data node.
- Standby A: `application_name` is `standby_a`.
- Standby B: `application_name` is `standby_b`.

Both standbys must be configured for physical streaming replication, able to connect to the primary, and in `streaming` state. This lab describes configuration only; run it on a disposable test cluster that can be rebuilt.

### 19.2. Check WAL level

On the primary:

~~~sql
SHOW wal_level;
~~~

Physical streaming replication requires an appropriate WAL level, typically `replica` or higher depending on version. If the setting is insufficient, change configuration and restart as required by the parameter; never alter production just to run a lab.

### 19.3. Set application_name on the standby

Example connection string portion on standby A:

~~~conf
primary_conninfo = 'host=primary.lab port=5432 user=replicator application_name=standby_a'
~~~

Standby B uses a different `application_name`. Do not give both the same name if you want independent tracking/selection.

### 19.4. Configure FIRST 1 on the primary

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'FIRST 1 (standby_a, standby_b)';

SELECT pg_reload_conf();

SHOW synchronous_standby_names;
~~~

### 19.5. Observe selection

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
~~~

When both standbys are connected and eligible, the higher-priority node is selected as `sync`; the remaining node may appear as `potential`/`async` depending on version and state. Observe actual output rather than assuming from connection streaming alone.

### 19.6. Run a commit transaction

~~~sql
CREATE SCHEMA IF NOT EXISTS sync_lab;

CREATE TABLE IF NOT EXISTS sync_lab.events (
    event_id bigint PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

BEGIN;
SET LOCAL synchronous_commit = 'on';

INSERT INTO sync_lab.events(event_id, payload)
VALUES (1, 'first synchronous commit');

COMMIT;
~~~

`COMMIT` waits for the required local/remote flush per configuration and the selected sync standby.

### 19.7. Compare with local

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'local';

INSERT INTO sync_lab.events(event_id, payload)
VALUES (2, 'local acknowledgement only');

COMMIT;
~~~

The second transaction waits for local WAL flush without waiting for remote synchronous acknowledgement. The standby still receives WAL via normal streaming replication.

### 19.8. Observe waiting backends

In another session, when simulating a controlled slow/disconnected standby in the lab:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

If a transaction is waiting for remote acknowledgement, `SyncRep` appears as the wait event. Results depend on timing and version.

---

## 20. Lab: ANY 2 quorum

### 20.1. Configuration

With three standbys having distinct `application_name` values:

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'ANY 2 (standby_a, standby_b, standby_c)';

SELECT pg_reload_conf();
~~~

### 20.2. Confirm quorum state

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

Check which nodes participate in quorum via `sync_state` and live state. Do not infer all three nodes flushed the same commit just because all three appear in the list.

### 20.3. Test one standby disconnecting

In the lab:
1. Record LSN positions and sync states.
2. Stop one standby using test administration procedures.
3. Confirm the remaining two standbys are streaming and satisfy quorum.
4. Run a transaction using `synchronous_commit=on`.
5. Observe `COMMIT` and `pg_stat_activity`.
6. Restart the stopped standby.
7. Watch catch-up and sync state.

Never stop a production standby to test. If only one eligible standby remains, commits needing a quorum of two will wait.

### 20.4. Test insufficient quorum

In the test environment, stop two standbys so only one node remains under `ANY 2`. Observe backends waiting on `SyncRep`. Restore one node and confirm commits resume once quorum is met.

### 20.5. Compare FIRST and ANY

Repeat on the same topology with `FIRST 1` and `ANY 1`. Record:
- Which standby is selected.
- Sync state.
- Commit latency.
- Behavior when the priority node disconnects.
- Which node holds the newest flush/replay LSN.

### 20.6. Reset lab configuration

After testing, set configuration for the next lab objective or restore the saved baseline. Do not leave the test cluster in an unintended quorum/commit level state.

---

## 21. Lab: comparing acknowledgement levels

### 21.1. Sample workload

~~~sql
CREATE TABLE IF NOT EXISTS sync_lab.commit_probe (
    id bigserial PRIMARY KEY,
    mode text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Test each level in its own transaction:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'local';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('local');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_write';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('remote_write');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'on';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('on');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('remote_apply');
COMMIT;
~~~

### 21.2. Measure latency

Use a client benchmark/script to measure many commits, recording p50/p95/p99 and system load. Do not run only a single transaction because group commit, caches, and scheduling add noise.

### 21.3. Cross-check progress

On the primary:

~~~sql
SELECT
    application_name,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

For `remote_write`, watch write progress; for `on`, watch flush progress; for `remote_apply`, watch replay progress. Pair logs/metrics from the same window to interpret latency.

### 21.4. Read-after-write test

After a `remote_apply` transaction:
1. Open a new transaction on the standby.
2. Query the newly written row.
3. Confirm the row is visible after replay.
4. Repeat with a transaction snapshot opened before the commit to see snapshot isolation behavior.

### 21.5. Record results

Save configuration, version, standby count, RTT, storage type, commit mode, quorum, latency percentiles, and failure behavior. Never extrapolate one lab environment's numbers to claim production has identical latency.

---

## 22. Practice exercises

All exercises use a PostgreSQL lab. Never induce disconnects or stop production standbys to test failure scenarios.

### Exercise 1 — synchronous replication

Explain what problem synchronous replication solves during primary failover.

### Exercise 2 — Two parameters

Distinguish the roles of `synchronous_standby_names` and `synchronous_commit`.

### Exercise 3 — Standby name

Which setting on the replication connection must a standby name in `synchronous_standby_names` match?

### Exercise 4 — FIRST 1

With `FIRST 1 (a,b,c)`, which node has priority? What happens if `a` disconnects?

### Exercise 5 — FIRST 2

With `FIRST 2 (a,b,c)`, which two nodes are selected when all three are eligible? What role does the third node play?

### Exercise 6 — ANY 2

With `ANY 2 (a,b,c)`, how many responses are required? Can commits proceed if `c` disconnects?

### Exercise 7 — Quorum

Does quorum acknowledgement mean every standby has received the commit? Explain.

### Exercise 8 — FIRST and ANY

State the most important selection difference between `FIRST` and `ANY`.

### Exercise 9 — synchronous_commit off

Does `off` disable WAL? What is the primary risk?

### Exercise 10 — local

What does `local` wait for and what does it not wait for?

### Exercise 11 — remote_write

Does a standby's `remote_write` acknowledgement guarantee WAL survives a standby power loss? Why?

### Exercise 12 — on

Which remote level does `on` wait for? Does it require the standby to have replayed WAL?

### Exercise 13 — remote_apply

In which application scenario is `remote_apply` useful? Why might an older snapshot still miss the new row?

### Exercise 14 — No synchronous standby

If `synchronous_standby_names` is empty, do remote modes have a standby to wait on? How do commits behave?

### Exercise 15 — Insufficient quorum

`ANY 2` has three standbys but only one node is eligible. What happens to a `COMMIT` using `on`?

### Exercise 16 — Slow priority standby

`FIRST 1 (a,b)`, `a` stays connected yet very slow while `b` is fast. Why does `b` not automatically replace `a`?

### Exercise 17 — Sync state

Briefly state the meanings of `async`, `potential`, `sync`, and `quorum` in `pg_stat_replication`.

### Exercise 18 — Wait event

Write a query to find backends waiting on `SyncRep`.

### Exercise 19 — Replication progress

State the meanings of `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn`.

### Exercise 20 — Reload

Does `synchronous_standby_names` require a server restart for normal changes? How do you verify a reload took effect?

### Exercise 21 — Session override

Write a transaction using `SET LOCAL synchronous_commit='remote_apply'`.

### Exercise 22 — Connection pool

Why can session-level `SET synchronous_commit` cause policy leaks across requests if a pool does not reset session state?

### Exercise 23 — Latency

With `FIRST 2`, which of the two selected nodes usually governs commit latency? Explain.

### Exercise 24 — ANY 2 latency

Why can `ANY 2` reduce tail latency compared to waiting for all three standbys?

### Exercise 25 — Slow remote_apply

Write/flush LSNs keep up yet replay LSN lags. What should you investigate?

### Exercise 26 — Promotion

When the primary is lost, why shouldn't you blindly promote the first standby in the `FIRST` list?

### Exercise 27 — Quorum and failover

Does `ANY 2` of three standbys allow promoting any arbitrary node? What must be checked?

### Exercise 28 — Zero RPO

List the conditions required for synchronous replication to support avoiding loss of acknowledged commits.

### Exercise 29 — Synchronous replication and backups

Why does a synchronous standby not replace base backups/WAL archives/PITR?

### Exercise 30 — Network partition

The primary stops receiving feedback from the standby. Why can commits block? What are the operational options?

### Exercise 31 — wal_level

Which `wal_level` is required for physical streaming replication? Why is `minimal` unsuitable?

### Exercise 32 — Wrong standby application_name

A standby is streaming yet `sync_state=async`. List the investigative steps.

### Exercise 33 — RPO and quorum size

What are the durability, latency, and availability trade-offs of increasing `num_sync`?

### Exercise 34 — FIRST 1 vs ANY 1

Both configurations require one response. Why can their behavior differ?

### Exercise 35 — Read-after-write

A transaction commits with `on`, the application reads immediately from a standby, and misses the row. Explain and propose solutions.

### Exercise 36 — remote_apply and read routing

`ANY 1` has three standbys; `remote_apply` returns success. Can the application read randomly from any standby and be guaranteed to see the row? Why?

### Exercise 37 — Synchronous commit stall

List the investigation order when multiple backends wait on `SyncRep`.

### Exercise 38 — Async fallback

During an incident, a DBA considers clearing `synchronous_standby_names` to unblock writes. List the impacts and details to record.

### Exercise 39 — Failure domains

Why does placing all synchronous standbys in the same rack reduce fault tolerance?

### Exercise 40 — Runbook

Write a short runbook for handling increased commit latency after the primary synchronous standby fails over to a node in another region.

---

## 23. Solutions — exercises 1 to 20

### Exercise 1 — synchronous replication

It lets the primary wait for a standby to receive WAL up to an acknowledgement level before confirming `COMMIT`. This reduces the risk of losing acknowledged commits when the primary fails and an acknowledging standby is promoted.

### Exercise 2 — Two parameters

`synchronous_standby_names` determines which standbys participate and how many responses are required. `synchronous_commit` determines whether transactions wait for remote write, remote flush, or remote apply; `local`/`off` do not wait for remote acknowledgement.

### Exercise 3 — Standby name

The name must match the `application_name` of the physical replication connection, typically set in `primary_conninfo` on the standby.

### Exercise 4 — FIRST 1

`a` has the highest priority. If `a` disconnects and `b` is eligible, `b` can be selected as the replacement synchronous standby.

### Exercise 5 — FIRST 2

When all three are eligible, `a` and `b` are selected by priority order. `c` acts as a standby reserve/`potential` depending on selection state and version.

### Exercise 6 — ANY 2

Two responses are required. If `c` disconnects while `a` and `b` remain eligible, quorum still holds and commits can continue.

### Exercise 7 — Quorum

No. `ANY 2` of three only requires two nodes to respond for that commit; the third node may not have flushed/replayed up to the same commit LSN.

### Exercise 8 — FIRST and ANY

`FIRST` selects by priority order; `ANY` waits for any `num_sync` nodes in the list. `FIRST` prefers specific nodes; `ANY` allows quorum across peer nodes.

### Exercise 9 — off

`off` does not disable WAL. It allows `COMMIT` to return before local WAL flush, so recently confirmed commits can be lost if the server/OS/storage crashes before flush.

### Exercise 10 — local

`local` waits for local WAL flush but does not wait for synchronous standby write/flush/apply.

### Exercise 11 — remote_write

No. Remote write only confirms WAL was written to the OS/file layer on the standby; without durable `fsync`/flush, power loss/OS crash can lose those bytes.

### Exercise 12 — on

`on` waits for the synchronous standby to flush WAL along the durability path. It does not require the standby to have replayed; replay can lag behind flush.

### Exercise 13 — remote_apply

Used when reading from a standby immediately after a write and needing the standby to have replayed the commit. An older snapshot from a transaction opened before commit still may not see changes due to MVCC snapshot semantics.

### Exercise 14 — No synchronous standby

No remote standby is chosen to wait on. When no synchronous standby is configured, remote modes create no remote wait; commit behavior effectively relies on local WAL flush unless `synchronous_commit=off`.

### Exercise 15 — Insufficient quorum

`COMMIT` using `on` waits because only one of the two required acknowledgements is available. Restore a second node or change policy per incident procedure.

### Exercise 16 — Slow priority standby

`FIRST` selection relies on priority and eligibility, not automatically choosing the fastest node. As long as `a` stays connected/eligible, the primary can keep waiting on `a` even if `b` responds faster.

### Exercise 17 — Sync state

`async` is asynchronous; `potential` is an eligible priority standby not currently selected; `sync` is the currently chosen synchronous standby in priority mode; `quorum` is a node participating in a quorum-based synchronous set. Check exact details for your version.

### Exercise 18 — Wait event

~~~sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

### Exercise 19 — Replication progress

`sent_lsn` is the position sent by the sender; `write_lsn` is written by the standby; `flush_lsn` is flushed by the standby; `replay_lsn` is applied/replayed WAL on the standby.

### Exercise 20 — Reload

`synchronous_standby_names` can normally be reloaded without restarting. Use `pg_reload_conf()`, check `SHOW synchronous_standby_names`, PostgreSQL logs, and `pg_stat_replication.sync_state`.

### Exercise 21 — Session override

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
UPDATE app.orders
SET status = 'confirmed'
WHERE order_id = 2001;
COMMIT;
~~~

### Exercise 22 — Connection pool

Session-level `SET` persists beyond the transaction and can remain when the connection returns to the pool. Subsequent requests may receive a connection with an unintended commit level. Use `SET LOCAL` inside transactions or reset session state on pool return.

### Exercise 23 — FIRST 2 latency

The transaction requires two acknowledgements from the two chosen standbys. It typically waits for the slower node in the pair, since the second response completes `num_sync`.

### Exercise 24 — ANY 2 latency

`ANY 2` requires only two responses. With three standbys of varying latency, the two faster nodes can satisfy quorum instead of waiting for all three.

### Exercise 25 — Slow remote_apply

Inspect the replay process, standby CPU/I/O, hot standby conflicts, long-running readers, recovery logs, wait events, and competing workload. Write/flush keeping up shows receive/storage may be fine while apply lags.

### Exercise 26 — Promotion

The first node in the `FIRST` list is merely the preferred node for synchronous selection while the primary is running. After an outage, that node might be lost, stale, or unreachable. Compare WAL progress and identify the node holding the newest commit WAL before promotion.

### Exercise 27 — Quorum and failover

Do not promote arbitrarily. Check receive/flush/replay LSNs, timeline, sync configuration at outage time, WAL continuity, and fencing of the old primary. Choose the node with the newest WAL covering confirmed commits.

### Exercise 28 — Zero RPO

Requires transactions waiting for remote acknowledgement at an appropriate level, standby confirming commit, promoting a node holding that WAL, storage retaining WAL, fencing the old primary, and no out-of-policy `local`/`off` overrides. The goal holds only within the defined failure model.

### Exercise 29 — Not a backup replacement

Synchronous replication also replicates destructive actions, logical errors, and corruption recorded in WAL. Independent backups, retention, and PITR allow rolling back before an incident; standbys primarily serve HA.

### Exercise 30 — Network partition

The primary stops receiving feedback and lacks enough remote acknowledgements; `COMMIT` waits on `SyncRep`. Options include restoring network/standby, waiting for quorum, or switching to asynchronous per incident policy with documented RPO exposure.

### Exercise 31 — wal_level

Physical streaming replication needs `wal_level` at `replica` or higher depending on version. `minimal` does not provide enough WAL information for standard physical standby streaming.

### Exercise 32 — Wrong application_name

1. `SHOW synchronous_standby_names` on primary.
2. Inspect `pg_stat_replication.application_name`.
3. Inspect `primary_conninfo` on standby.
4. Confirm exact spelling/case and unique names.
5. Check reload/config logs.
6. Inspect `sync_state` and `sync_priority` after reconnect.

### Exercise 33 — Quorum size

Increasing `num_sync` makes more standbys confirm each commit, increasing WAL copies at the cost of higher latency and lower write availability during node failures. Decreasing `num_sync` improves availability/lowers latency, while fewer standbys confirm each commit.

### Exercise 34 — FIRST 1 vs ANY 1

`FIRST 1` picks the highest-priority eligible node. `ANY 1` accepts a response from any listed node. When the priority node is slow yet connected, `FIRST` keeps waiting on it; `ANY` can use another faster-responding node.

### Exercise 35 — Read-after-write

With `on`, the standby flushed WAL but may not have replayed it yet. Read from the primary, use `remote_apply` for transactions needing read-after-write on the standby, or wait for replay up to the commit LSN. Never rely on a fixed sleep as a guarantee.

### Exercise 36 — remote_apply and read routing

No. `ANY 1` waits only for one standby in the quorum list to replay. Other standbys may not have replayed up to the commit. Applications must route to the responding node or read from the primary/wait per node to reach the required LSN.

### Exercise 37 — Synchronous commit stall

1. Identify backends waiting on `SyncRep`.
2. Check `synchronous_standby_names` and `synchronous_commit`.
3. Inspect `pg_stat_replication` and `sync_state`.
4. Compare sent/write/flush/replay LSNs.
5. Check network and logs.
6. Check standby storage/replay bottlenecks.
7. Restore quorum or alter policy per incident process.

### Exercise 38 — Async fallback

Clearing `synchronous_standby_names` removes the remote synchronous wait for subsequent commits; commits rely on local behavior. Record approval, timestamp, cluster, affected transactions/workloads, RPO exposure, reason, restoration time, and sync state verification results.

### Exercise 39 — Failure domains

A single rack failure can take out the primary and all standbys together. Placing nodes in independent failure domains reduces correlated failures, while balancing latency and network reliability.

### Exercise 40 — Runbook after failover to a distant region

1. Measure p50/p95/p99 commit latency and pinpoint when the change started.
2. Check `pg_stat_replication`, `sync_state`, and the currently selected standby.
3. Measure RTT, packet loss, and standby flush latency in the new region.
4. Check quorum/priority lists and `num_sync`.
5. Determine whether the old node can return; avoid uncontrolled automatic selection changes.
6. If topology permits, restore a nearby standby per plan and verify catch-up.
7. Change synchronous policy only after RPO/availability review and approval.
8. Run workload tests and verify latency and failover readiness.
9. Update topology/runbook and monitor post-incident.

---

## 24. Summary

`synchronous_standby_names` and `synchronous_commit` must be designed together. One parameter selects the standby group and response count; the other defines whether transactions wait for write, flush, or replay. Together they directly govern durability, commit latency, and write continuity when standbys or networks fail.

Key principles:

1. `FIRST` is priority-based selection; `ANY` is quorum-based selection.
2. `FIRST 1 (a,b)` prioritizes `a`, failing over to `b` when `a` becomes ineligible.
3. `ANY 2 (a,b,c)` requires any two responses; the third node may not have acknowledged that commit.
4. Standby names must match `application_name` on the physical replication connection.
5. `off` does not wait for local WAL flush; `local` waits for local flush; `remote_write` waits for remote OS write; `on` waits for remote flush; `remote_apply` waits for replay.
6. `remote_write` offers weaker protection than remote flush against OS/power failures on the standby.
7. `remote_apply` supports read-after-write on a standby with a fresh snapshot, yet does not make every standby in a quorum instantaneously synchronous.
8. Insufficient `num_sync` standbys can cause `COMMIT` to wait; this is the core trade-off between write availability and synchronous durability.
9. `pg_stat_replication` and `pg_stat_activity` are the two primary places to observe `sync_state` and `SyncRep` waits.
10. Write/flush/replay LSNs must be read separately; a single lag metric does not represent all acknowledgement levels.
11. `FIRST` does not automatically pick the fastest standby; `ANY` can use the fastest responses forming quorum.
12. Promotion must rely on WAL progress/timeline and fencing, not merely configuration order.
13. Synchronous replication does not replace backups, WAL archives, and PITR.
14. Never claim zero RPO without specifying the failure model, commit level, promoted node, and transaction overrides.
15. Configuration changes require reloading, checking live status, and measuring commit latency.
16. If falling back to asynchronous during an incident, record duration and RPO exposure, then verify synchronous policy restoration.

Selection workflow: **define RPO/RTO and failure domains → choose FIRST or ANY → choose num_sync per node count and required availability → choose synchronous_commit per durability/read visibility → measure latency under load → drill standby failures and promotion → continuously monitor SyncRep, sync_state, and LSN progress**.
