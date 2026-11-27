# Read Consistency From Standbys and Read-After-Write Requirements in PostgreSQL

## 1. Why Can Reading From a Standby Return Stale Data?

In a PostgreSQL High Availability architecture, standbys are commonly used to serve read queries, offload the primary, and maintain failover readiness. With physical streaming replication, the primary sends WAL to the standby; the standby receives, writes, flushes, and replays WAL to update the database state.

Those steps happen asynchronously when asynchronous replication is used. Therefore, a transaction can already be `COMMIT`ted successfully on the primary while the standby has not yet replayed the WAL containing that transaction. If an application writes to the primary and immediately reads from a standby, the query may not yet see the newly written data.

This situation is called **read-after-write inconsistency** or a stale read. It does not necessarily mean replication is broken; it can simply be normal asynchronous replication lag.

```text
Application
    |
    | 1. INSERT / UPDATE
    v
PRIMARY
    |
    | 2. COMMIT acknowledged
    | 3. WAL sent asynchronously
    |
    +------------------------------+
                                   |
                                   v
                              STANDBY
                              WAL received
                                   |
                                   | 4. WAL replayed later
                                   v
                              New row visible

Application reads standby between steps 3 and 4:
the row may not be visible yet.
```

The application must choose an explicit consistency policy for each request type. Some requests tolerate data delayed by a few seconds, some require seeing a just-committed transaction immediately, and some require consistent reads across a session.

### Learning Objectives

After this lesson, you will be able to:

1. Explain why a standby can lag behind the primary.
2. Distinguish replication lag, read freshness, and transaction snapshots.
3. Understand read-after-write, read-your-writes, monotonic reads, and causal consistency.
4. Design read/write routing according to consistency requirements.
5. Use an LSN token as a consistency fence between primary and standby.
6. Wait for a standby to replay up to an LSN before reading.
7. Understand the limitations of synchronous replication and `synchronous_commit`.
8. Distinguish `remote_write`, `on`, and `remote_apply`.
9. Handle stale transaction snapshots in `READ COMMITTED` and `REPEATABLE READ`.
10. Design session stickiness, fallbacks, and timeouts.
11. Understand the impact of delayed standbys and recovery conflicts.
12. Verify read-after-write in applications and connection pools.
13. Build test cases, metrics, and runbooks for stale reads.
14. Determine when reads must go to the primary.
15. Avoid using fixed sleeps or a single lag metric as a consistency guarantee.

---

## 2. Do Primary and Standby Have the Same Data at the Same Instant?

Not necessarily. The primary processes transactions and generates WAL. The standby receives and then replays WAL afterward. The interval between those two steps may be short, yet still long enough for a read request to observe an older state.

| Time | Primary | Standby |
|---|---|---|
| T1 | customer 42 has balance 100 | balance 100 |
| T2 | `UPDATE balance = 150` | balance 100 |
| T3 | `COMMIT` succeeds | balance 100 |
| T4 | Application reads standby | may still return 100 |
| T5 | Standby replays transaction | balance 150 |
| T6 | Application reads standby | returns 150 |

### 2.1. Replication Lag Is a Dynamic State

Lag can increase during batch hours, decrease during light workloads, and vary with network/storage. There is no fixed delay that holds for every query.

### 2.2. Primary Commit Does Not Wait for Standby Replay by Default

With a typical asynchronous configuration and default `synchronous_commit = on` without any synchronous standby configured, commit waits for local WAL flush. It does not wait for any standby to replay the transaction.

### 2.3. A Standby Only Replays WAL It Has Received

If WAL has not reached the standby, replay cannot advance to that transaction. If WAL has been received and flushed but replay has not caught up to it yet, the data is still not visible on the standby.

### 2.4. "Received" Differs From "Applied"

Receive/flush LSN and replay LSN describe two different stages. To read a newly modified row, the standby must have replayed up to the WAL containing that transaction.

## 3. Read-After-Write and Consistency Guarantees

These terms describe what an application can expect after writing.

| Guarantee | Meaning |
|---|---|
| Read-your-writes | A client reads the changes that it itself committed |
| Read-after-write | After a successful write, the subsequent read sees that change |
| Monotonic reads | A client never sees an older state than a state it observed earlier |
| Causal consistency | If operation B depends on operation A, a client does not observe B without A |
| Eventual consistency | If no new writes occur and replication continues, replicas eventually converge |
| Strong/linearizable read | Reads follow a defined real-time order; requires appropriate architecture/coordination |

### 3.1. Read-Your-Writes Is a Per-Client/Session Guarantee

A write request may succeed on the primary. If the next request is routed to a standby that has not replayed yet, the same client still sees stale data. Thus, keeping session affinity only at the HTTP layer is not necessarily enough; reads must route to the primary or wait for a replica to reach a consistency token.

### 3.2. Monotonic Reads

If the first request reads from standby A replayed up to LSN X, a later request should not be routed to standby B replayed only to an LSN lower than X. Otherwise, the same user could see data "go backward."

### 3.3. Causal Consistency

For example, a user creates an order and then opens the order details page. The details page must show the newly created order. Creating the order is the cause of the subsequent read; the read request must wait for a replica that has replayed that change or read from the primary.

### 3.4. Eventual Consistency Is Not Enough for Every Workflow

Analytics dashboards can tolerate delay. Account balances, payment statuses, access permissions, and outcomes of just-committed operations typically need stronger consistency.

## 4. Transaction Snapshots Affect Read-After-Write

Even when a standby has already replayed a transaction, an already-open read transaction may not see the new change.

PostgreSQL defaults to `READ COMMITTED`. Each statement begins a new snapshot. If a transaction uses `REPEATABLE READ` or `SERIALIZABLE`, the snapshot is normally fixed at the start of the transaction.

### 4.1. READ COMMITTED

A transaction can execute multiple statements and each statement receives a fresh snapshot. If the standby replays before the read statement starts, that statement can see the change.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE account_id = 42;

-- Another transaction is replayed on the standby.

SELECT balance
FROM accounts
WHERE account_id = 42;

COMMIT;
```

The second statement takes a new snapshot and can see the newly replayed data.

### 4.2. REPEATABLE READ

The transaction's snapshot is held steady. If the transaction started before the WAL was replayed, subsequent statements still cannot see the new change even as replay advances.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE account_id = 42;

-- The standby replays additional WAL outside this transaction.

SELECT balance
FROM accounts
WHERE account_id = 42;

COMMIT;
```

Both `SELECT`s use the same transaction snapshot.

### 4.3. SERIALIZABLE

`SERIALIZABLE` provides serializable guarantees for transactions on the database node where it runs. It does not automatically synchronize snapshots between primary and standby, nor does it guarantee that a read from another standby has replayed a just-committed transaction.

### 4.4. How to Handle It

After waiting for the replica to reach the LSN fence, start a new read transaction or use a `READ COMMITTED` statement with a fresh snapshot. Do not hold onto an old `REPEATABLE READ` transaction and expect it to see new WAL automatically.

## 5. Simplest Approach: Read From the Primary After Writing

If a request that just wrote needs to read immediately, routing the subsequent read to the primary is the easiest solution to reason about.

```text
Application
    |
    v
Write to primary
    |
    v
COMMIT acknowledged
    |
    v
Read from the same primary
    |
    v
Fresh statement snapshot
```

### 5.1. Same Connection or Same Primary

If writing and reading happen in the same transaction, the transaction sees its own writes per isolation semantics. If committing and then reading in a new transaction on the same primary, the fresh statement snapshot will see the committed transaction, barring failover scenarios that lose commits under the durability model.

### 5.2. Read Routing Must Know a Request Just Wrote

The application can attach metadata to the request/session, such as `read_after_write=true`, and route related reads to the primary for a window of time or until a consistency token is satisfied.

### 5.3. No Need to Force Every Read to the Primary

Requests that do not depend on a just-executed write can read from standbys if the business tolerates staleness. Endpoint classification preserves read scaling.

### 5.4. Primary Reads Still Need Proper Transaction Semantics

A `REPEATABLE READ` transaction started before another commit will not automatically see that commit. Use a new transaction or an appropriate snapshot.

## 6. Session Stickiness and Its Limitations

Session stickiness can keep requests from the same user on the same node or same read route. It helps with monotonic reads, but does not guarantee read-after-write on its own.

### 6.1. Sticky to Primary

After a write, pinning reads in that session to the primary is a straightforward way to achieve read-your-writes within the current primary history.

### 6.2. Sticky to One Standby

If a session is pinned to standby A, it avoids jumping to standby B with higher lag. However, A may still not have replayed the just-committed transaction. Stickiness does not replace an LSN fence.

### 6.3. Load Balancer Switching Backends

A connection pool or proxy may pick a different backend per transaction. Do not assume two consecutive SQL statements in an application use the same PostgreSQL server unless connection routing guarantees it.

### 6.4. Failover Changes History

After promotion, the old primary and new primary may belong to different timelines. Session affinity cannot replace identifying the current primary and verifying durability of acknowledged transactions.

## 7. LSN Token: How to Build a Consistency Fence

A general approach is to capture an LSN token after a transaction commits on the primary. The application passes the token alongside the read request. A standby is only used once its replay position reaches or exceeds the token.

```text
1. Application writes on primary
2. COMMIT succeeds
3. Application reads a WAL LSN token
4. Token travels with the next read request
5. Application checks standby replay LSN
6. If replay LSN >= token, read from standby
7. Otherwise wait, retry, or read from primary
```

### 7.1. Capturing the Token After COMMIT

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 25
WHERE account_id = 42;

COMMIT;

SELECT pg_current_wal_lsn() AS consistency_lsn;
```

Capture the token on the same primary after `COMMIT` succeeds. The token may advance past the request's commit due to concurrent transactions' WAL being written simultaneously; this only makes the standby wait slightly longer at most, while creating a safe fence within the same WAL history.

### 7.2. Why Capture After Commit?

If you capture the LSN before the transaction commits, the token may not include the commit record. A standby reaching that token is then not guaranteed to have replayed the transaction you need to read.

### 7.3. The Token Is a Useful Upper Bound

An LSN captured after commit may include WAL from other concurrent transactions. A standby replaying up to the token replays all preceding WAL in order, including the just-committed transaction.

### 7.4. Bind the Token to Cluster/Timeline Context

Do not store just the bare LSN string. The token should travel with cluster identity/primary generation or enough metadata to know which WAL history it belongs to. Never blindly compare LSN numbers from two independent clusters/timelines.

## 8. Checking Whether a Standby Has Replayed to the Token

On the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn AS reached_token;
```

Replace `0/16B6C50` with the token received from the primary.

### 8.1. Ensure the Query Runs on the Intended Standby

If the connection pool misroutes to the primary or a different standby, the check no longer represents the intended node. Attach node identity to telemetry.

### 8.2. Check Role

`pg_is_in_recovery()` returns `true` on a standby in recovery. If `false`, the node may have been promoted. The application needs to recognize the new topology and verify whether the token belongs to the current history.

### 8.3. LSN Comparison

PostgreSQL supports the `pg_lsn` type and ordering comparisons within the same WAL history. Use an explicit cast for the token string. Do not parse LSNs by comparing text alphabetically in the application.

### 8.4. NULL and Indeterminate States

If replay LSN has no valid value or the server just changed roles, treat the check as "unverified," not as having reached the fence.

## 9. Polling Until the LSN Fence Is Reached

A portable implementation is polling with a timeout and exponential backoff at the application layer.

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    COALESCE(
        pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn,
        false
    ) AS reached_token;
```

The application repeats:
1. Connect to the intended standby.
2. Check role and replay LSN.
3. If the token is reached, execute the read in a new transaction.
4. If not yet reached, wait briefly and check again.
5. On timeout, fall back to the primary or return a retry state per policy.

### 9.1. Timeouts Must Fit the Latency Budget

Do not wait indefinitely. For example, an endpoint with a 300 ms budget can wait on the replica for part of that budget and then switch to the primary.

### 9.2. Bounded Backoff

Use increasing backoff with a cap and jitter so many requests do not poll in lockstep when a standby lags.

### 9.3. Do Not Hold a Read Transaction Open While Waiting

If you begin a `REPEATABLE READ` transaction before replay reaches the token, its snapshot may already be stale. Wait outside the read transaction, then open a new one.

### 9.4. Read After the Fence Is Reached

Immediately after the check succeeds, run the `SELECT` on the same standby and inside a new transaction. If the connection switches nodes between check and read, re-verify the fence on the new node.

## 10. An LSN Fence Is Not a Distributed Transaction

A token only proves the standby has replayed up to a WAL position within the relevant history. It does not create an atomic transaction between primary and standby, nor does it lock the primary against new writes.

### 10.1. New Writes Can Occur After the Token

The standby can continue replaying past the token while the request runs. That is normal. The token only guarantees it has passed the required point.

### 10.2. Does Not Guarantee Other Nodes Have Caught Up

If a token is checked on standby A, it does not prove standby B or C has replayed the same point.

### 10.3. Does Not Guarantee External Side Effects

If a transaction interacts with systems outside the database, WAL replay only reflects PostgreSQL changes. Payment gateways, queues, or object storage need their own consistency protocols.

### 10.4. Does Not Recover Lost Commits After Failover

If an asynchronous failover promotes a standby that lacks a transaction, a token from the old primary may not exist in the new primary's history. The application must handle commit ambiguity and reconcile.

## 11. Synchronous Replication and Read-After-Write

Synchronous replication lets the primary wait for one or more standbys to confirm WAL before reporting commit success, depending on configuration.

Key settings:
- `synchronous_standby_names`: selects synchronous standbys or quorum.
- `synchronous_commit`: acknowledgement level to wait for per transaction/session.
- `sync_state`: actual synchronous state of a standby.

### 11.1. synchronous_commit = on

With synchronous replication, `on` waits for the standby to flush WAL durably per PostgreSQL semantics. When commit is acknowledged, the synchronous standby has flushed the transaction, though it may not yet have replayed it for read queries.

### 11.2. synchronous_commit = remote_apply

`remote_apply` waits for the synchronous standby to replay the transaction before the commit is acknowledged. This supports read-after-write from the selected standby, provided the read starts after acknowledgement and routes to the standby that satisfied the sync policy.

### 11.3. synchronous_commit = remote_write

`remote_write` waits for the standby to write WAL to the operating system, without guaranteeing a durable remote flush like `on`.

### 11.4. synchronous_commit = local

Waits for local flush per semantics, without waiting for a remote synchronous standby.

### 11.5. synchronous_commit = off

May return `COMMIT` before local WAL flush. This reduces latency but risks losing already-acknowledged transactions if the primary crashes. Never use it as a path to strong durability.

## 12. Does remote_apply Guarantee Reading From Every Standby?

No. It only waits according to the configured synchronous standby policy.

Example:
- `synchronous_standby_names` selects standby A as synchronous.
- `remote_apply` waits for A to replay.
- Application reads from A after commit acknowledgement: read-after-write can be achieved.
- Application reads from standby B, which is asynchronous: B may still be stale.

### 12.1. Quorum Synchronous

With quorum configuration, commit waits for enough standbys per policy. Do not assume every node in the list has replayed. The application must know which node satisfies the consistency token or use an appropriate read route.

### 12.2. Priority-Based Synchronous

With priority-based configuration, the active synchronous node can change when standbys disconnect/reconnect. Monitor `sync_state` and topology at commit time.

### 12.3. Node Identity Is Required

If the application needs to read from the specific node that confirmed `remote_apply`, there must be a way to target the appropriate node/endpoint. Do not just send the token to a load-balanced endpoint unaware of the backend.

### 12.4. Latency Trade-Off

`remote_apply` makes commit latency depend on network, standby flush, and replay. A long query on the standby or a recovery conflict can slow replay, which in turn slows commits.

## 13. When to Choose LSN Fence vs. remote_apply?

| Approach | Best suited when | Cost/limitation |
|---|---|---|
| Read primary after write | Simple, need guaranteed RYW on current primary | Increases primary load |
| LSN fence + polling | Need to read from replica, but only once replica has caught up to the request | Extra round trips, timeout/fallback logic |
| `remote_apply` | Need synchronous commit to wait for selected standby replay | Increases commit latency and standby dependency |
| Session stickiness | Need monotonic reads on the same replica | Does not guarantee replica has seen write on its own |
| Eventual read | Analytics/reporting accepting stale data | UI/business must accept freshness window |

### 13.1. Combine Multiple Approaches

A system can route financial operations to the primary, use an LSN fence for detail pages after writes, and use eventual consistency for analytics dashboards.

### 13.2. Do Not Enable remote_apply System-Wide by Default

Only transactions requiring that guarantee need the higher sync level, if the application can set `synchronous_commit` per transaction/session and policy permits.

### 13.3. Measure Before Deciding

Measure commit latency, replica lag distribution, request latency, and primary load before and after applying changes.

## 14. Read Routing by Consistency Policy

An application can attach a consistency requirement to each request.

| Request | Read target | Consistency |
|---|---|---|
| Create order then view details | Primary or replica past token | Read-after-write |
| Profile page after update | Primary or LSN fence | Read-your-writes |
| Summary dashboard | Standby | Eventual |
| Historical reports | Standby/reporting replica | Eventual, explicit snapshot |
| Check just-changed permissions | Primary or fence | Stale not accepted |
| Public feed | Standby | Small lag acceptable |

### 14.1. Do Not Route Solely by HTTP Method

A `GET` after a `POST` may depend on the just-committed transaction. Another `GET` may not require strong consistency. Use business/causal tokens rather than just classifying `GET`/`POST`.

### 14.2. Consistency Token in Request Context

After a write, the application can store the token in a server-side session or pass the token with the next request so the read router picks the right primary/standby.

### 14.3. Scope-Limit the Token

Tokens must be tied to cluster/database history and expiry. Do not use tokens from another cluster or after an unreconciled failover.

### 14.4. Avoid Exposing Internal Details

It is not necessary to expose raw LSNs to public clients. You can use an opaque signed/encoded token at the application layer.

## 15. Connection Pools and Transaction Boundaries

A connection pool may lend a different connection for the read request. Therefore, do not assume the connection that wrote the transaction is the same connection performing the next read.

### 15.1. Pools With Primary and Replica Endpoints

Route endpoints explicitly by consistency policy. A transaction must never accidentally switch between primary and standby.

### 15.2. Transaction Pooling

A proxy in transaction pooling mode may assign a different backend after every transaction. LSN tokens or route metadata must live at the application layer, not rely on backend session state.

### 15.3. Session Variables

Do not use a session variable on one connection to hold a consistency token if the next request may use a different connection. Store it in a controlled application/session store.

### 15.4. Reset State When Returning a Connection

If you set `synchronous_commit`, isolation level, or read routing state per session, reset it before returning the connection to the pool to avoid leaking into the next request.

## 16. Read-Your-Writes Within the Same Transaction

If an application writes and then reads within the same transaction on the primary, PostgreSQL lets the transaction see its own writes.

```sql
BEGIN;

INSERT INTO public.orders (order_id, status)
VALUES (9001, 'NEW');

SELECT order_id, status
FROM public.orders
WHERE order_id = 9001;

COMMIT;
```

Reading within this same transaction does not require waiting for replication. However, if the application commits and then routes a `SELECT` to a standby before replay, a different policy must apply.

### 16.1. Uncommitted Writes

Other transactions do not see uncommitted writes under standard isolation semantics. Reading from a standby certainly cannot see an uncommitted/unreplayed transaction.

### 16.2. Read-Your-Writes Is Not Read-Your-Concurrent-Writes

If another transaction updates the same row after your commit, the result depends on snapshot/timing/order. RYW only guarantees seeing your own writes in valid history.

### 16.3. Reading After COMMIT on the Primary

Open a new statement/transaction on the primary to see the committed state under a fresh snapshot. If failover and async loss occur, commit ambiguity must be handled separately.

## 17. Monotonic Reads With Multiple Standbys

Suppose:
- Request A reads standby 1 at replay LSN `0/500`.
- Request B reads standby 2 at replay LSN `0/420`.

The user may see an older value in request B. This is a non-monotonic read.

### 17.1. Sticky Replica

Keeping a session on the same replica helps avoid switching to a node that is further behind, though that replica can still pause replay or fail over.

### 17.2. Track Last-Seen LSN

The application can track the highest LSN fence observed by a session. Before the next read, select only a replica with replay LSN >= the last-seen token.

### 17.3. When No Replica Meets the Token

Wait within the latency budget or route to the primary. Do not return older data without an explicit policy.

### 17.4. After Failover

The last-seen LSN belongs to the old timeline. Mapping/history or resetting/reconciling session consistency state is required. Never compare raw LSN numbers across a timeline fork.

## 18. Causal Reads Across Multiple Requests

Example:
1. User creates an order.
2. Service emits an order-created event.
3. Consumer updates a read model.
4. User opens the order status page.

If the read model is a PostgreSQL standby, it must replay WAL up to the relevant change before returning the required state. If the event is processed in another database, the causal token must span the entire pipeline, not just a single LSN.

### 18.1. Causal Dependency Graph

Track which operations depend on which. Waiting only for a PostgreSQL LSN does not prove a message queue consumer or external index has processed the event.

### 18.2. Outbox/Inbox

An outbox writes the event in the same transaction as the business change; the consumer processes events idempotently. The read model may need its own watermark to know which event sequence has been applied.

### 18.3. Watermarks Differ From LSNs

If a pipeline transforms data through queues/ETL, use the pipeline's event sequence/offset/watermark. A PostgreSQL LSN does not replace a Kafka offset or a consumer checkpoint.

### 18.4. Pending UI State

If an eventual read model has not updated yet, the UI can display "updating" or temporarily use the primary result instead of returning a stale value as final.

## 19. Transaction Snapshots on a Standby

Hot standby serves read-only queries while replaying. The query/transaction snapshot determines which data it sees.

### 19.1. Statement Snapshot

In `READ COMMITTED`, each statement gets a fresh snapshot. If a query starts after replay reaches the token, it can see replayed changes.

### 19.2. Transaction Snapshot

In `REPEATABLE READ`/`SERIALIZABLE`, the transaction holds a steady snapshot. Waiting for replay between two statements will not automatically refresh the old snapshot.

### 19.3. Long-Running Queries

A long query that started before replay advanced to a new LSN can continue using the old snapshot until it completes.

### 19.4. Connection Pool Reuse

A connection may still have an open transaction if the application forgot `COMMIT`/`ROLLBACK`. Verify transaction state before reading after waiting on a fence.

## 20. Intentionally Delayed Standbys

PostgreSQL supports `recovery_min_apply_delay` to delay replay by a set interval. A delayed standby can help recover from replicated destructive operations, but is unsuitable for read-after-write freshness.

### 20.1. Receive Can Be Fast, Replay Intentionally Slow

The standby may receive/flush WAL while waiting to apply it. Receive and replay LSNs will diverge.

### 20.2. Do Not Route RYW to a Delayed Standby

A post-write request would have to wait out the entire delay policy, causing huge latency. Route to the primary or a non-delayed replica.

### 20.3. Delayed Standbys Serve a Different Role

They act as a safeguard against logical mistakes in some architectures. They are not necessarily the first failover target.

### 20.4. Do Not Remove Delay Just for Freshness

Changing the delay can defeat its protective purpose. Evaluate HA and delayed-recovery requirements separately.

## 21. Recovery Conflicts and Read Freshness

A standby can delay WAL replay due to query conflicts. Settings like `max_standby_streaming_delay` and `hot_standby_feedback` affect the balance between query continuity and replay freshness.

### 21.1. Long Queries Can Hold Back Replay

If a replay operation conflicts with a snapshot/query, PostgreSQL may wait or cancel the query depending on settings.

### 21.2. Replay Lag Rises

Read-after-write fences will wait longer. This signals that the standby is failing to meet the request's latency budget.

### 21.3. hot_standby_feedback

Feedback can reduce certain query cancellations, but can cause the primary to retain dead tuples longer. Monitor bloat and the vacuum horizon.

### 21.4. Isolate Reporting Workloads

Use a separate standby for long analytics queries if they impact replicas serving freshness/failover.

## 22. Synchronous Replication: Durability and Visibility

Three concepts must be distinguished:
- WAL written/flushed on the standby.
- WAL replayed.
- Query transaction having a snapshot that sees the change.

`remote_apply` goes further than remote flush because it waits for replay. However, the read transaction still needs a snapshot started after commit acknowledgement and routed to the appropriate node.

### 22.1. on Is Not remote_apply

With a synchronous standby, `on` waits for remote flush; the standby may not have replayed yet when commit returns.

### 22.2. remote_apply Does Not Bypass Snapshot Rules

A `REPEATABLE READ` transaction started before the commit still cannot see that transaction, even after the standby replays it.

### 22.3. Without a Synchronous Standby There Is No Remote Guarantee

Setting `synchronous_commit` alone does not create a standby or designate a synchronous node. Check `synchronous_standby_names` and `pg_stat_replication.sync_state`.

### 22.4. Failover Selection Must Match

If policy forbids losing acknowledged commits, promotion must choose a standby with matching durability evidence. A `remote_apply` acknowledgement from node A does not guarantee node B has the transaction.

## 23. Read-After-Write Through a Load Balancer

A load balancer can distribute requests across multiple standbys. Without knowing each backend's replay position, a request can hit a stale replica.

### 23.1. Sticky Routing

You can pin a session to one replica, though you must still verify the replica reached the token after a write.

### 23.2. Consistency-Aware Routing

A router can:
1. Receive the token.
2. Pick a sufficiently fresh standby.
3. If none, try another standby.
4. If budget expires, use the primary.
5. If the primary is unavailable, return retry/uncertain status per policy.

### 23.3. Backend Identity

If the proxy does not provide identity, the application can run a query returning server address/role/cluster metadata to record the backend. Do not use that information as a security identity; it is for routing/observability.

### 23.4. Pooler Transaction Mode

A proxy in transaction pooling mode can switch backends between transactions. Ensure the consistency check and actual `SELECT` run in the same transaction/backend, or re-verify the token on the selected backend.

## 24. Fallback When a Standby Has Not Reached the Token

| Option | Behavior | Suitable for |
|---|---|---|
| Wait | Wait for replica to reach LSN | Short lag, sufficient latency budget |
| Retry another replica | Pick another standby that has caught up | Multiple replicas |
| Read primary | Bypass stale replica | Critical RYW |
| Return pending/retry | Report not ready yet | Primary cannot be read |
| Serve stale with label | Return old data clearly marked | Analytics/feeds accepting staleness |

### 24.1. Never Silently Fall Back to Stale Data

If business requires read-after-write, returning stale data without indication violates the contract.

### 24.2. Timeouts and Circuit Breakers

If a replica repeatedly fails freshness SLOs, temporarily reduce read traffic or trip a circuit breaker. Monitor primary load during fallbacks.

### 24.3. Primary Overload

If every RYW request falls back to the primary, the primary can overload. Capacity planning must include fallback ratios during lag incidents.

### 24.4. When Primary Cannot Be Used

If the primary is unavailable and the standby has not reached the token, there is no way to conjure unreplicated data. The application must handle unavailable/uncertain states rather than assuming the transaction exists.

## 25. Read-After-Write After Failover

Failover is a special case because primary history can change.

### 25.1. Synchronous Failover

If an acknowledged commit was flushed/replayed on the standby promoted per policy, the transaction may exist on the new primary. Node and transaction history must still be verified.

### 25.2. Asynchronous Failover

A commit acknowledged on the old primary may not have reached the promoted standby. In that case, read-after-write cannot be guaranteed solely by the old token.

### 25.3. Commit Ambiguity

If the client loses connection right at `COMMIT`, the application may not know whether the transaction committed. Use an idempotency key/business operation ID to query/reconcile on the new primary.

### 25.4. Tokens From the Old Timeline

Never compare an old LSN token against the new replay LSN as two numbers in a single continuous sequence. Identify timeline/history and determine whether the transaction survived on the new primary.

## 26. Idempotency for Write Retries

When commit acknowledgement is lost due to network/failover, clients may retry. If the operation is not idempotent, duplicate orders/payments can occur.

```sql
CREATE TABLE request_deduplication (
    request_key uuid PRIMARY KEY,
    result_json jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Inside a transaction:
1. Insert `request_key`.
2. If the key already exists, read the stored result.
3. If new, execute the business write.
4. Store the response/result.
5. Commit.

### 26.1. Unique Key Is the Final Guardrail

A database unique constraint prevents the same request key from being processed into two records, provided all retries reuse the same key.

### 26.2. Idempotency Window

Retain deduplication records long enough for retry/client behavior and business requirements. Cleaning up too early can allow duplicate retries.

### 26.3. Do Not Infer Rollback From Client Timeout

A client timeout does not mean the transaction rolled back. The outcome may be unknown; query the idempotency key on the new primary.

## 27. Consistent Reads Across Multiple Tables

A request may read multiple related tables. If changes were committed in the same transaction on the primary, WAL replay preserves transaction atomicity when applying. However, the request must read after the standby replays up to that transaction and use an appropriate snapshot.

### 27.1. Single Read Transaction

Use a single `READ COMMITTED`/`REPEATABLE READ` transaction per business need to read tables within one snapshot. If a steady snapshot is required, start the transaction after reaching the fence.

### 27.2. Multiple Read Requests

If request 1 reads orders and request 2 reads payments, both need the same consistency token or causal context to avoid observing half a workflow.

### 27.3. Cross-Database Reads

A PostgreSQL standby replay token only applies to that cluster's WAL history. If data resides across two clusters, application-layer coordination tokens/watermarks are needed.

### 27.4. Cross-Service Dependencies

A database transaction does not automatically ensure event consumers, caches, or search indexes are updated. Each read model needs its own freshness contract.

## 28. Caches Complicate Read-After-Write

Even after a standby has replayed, a cache can still return stale data.

Possible layers:
- Application in-memory cache.
- Redis/Memcached.
- CDN.
- ORM identity map.
- Browser cache.
- Search index.

### 28.1. Invalidate After Commit

Only invalidate caches after commit succeeds. Invalidating before commit lets another request refill stale data.

### 28.2. Versioned Cache Keys

Attach an entity version/update sequence to the cache key to avoid reading stale entries after a write.

### 28.3. Cache Bypass for RYW

A request that just wrote can bypass the cache or read a cache entry updated directly from the transaction result.

### 28.4. Replication Fences Do Not Control Caches

An LSN token only proves the standby replayed. It does not prove Redis/CDN/search indexes have updated.

## 29. Read Consistency for Pagination and Feeds

Pagination on a standby can shift between requests if new data is replayed or sort order is unstable.

### 29.1. Keyset Pagination

Use a stable ordering key, such as `(created_at, id)`, instead of offset-only pagination when data changes continuously.

### 29.2. Snapshot Consistency

If a stable result set across multiple pages is needed, use a snapshot/export strategy or materialized result; independent HTTP requests generally do not share a transaction snapshot.

### 29.3. Monotonic Feeds

If a newly created feed item must appear immediately, route the read by token or return the newly created item from the write response while the read model catches up.

### 29.4. Analytics Freshness

When eventual consistency is acceptable, display an `updated-at` or freshness watermark so users understand data recency.

## 30. Read-After-Write With Sequences and Generated IDs

After an `INSERT`, applications often receive a generated ID via `RETURNING`. Immediately reading the row from primary or standby requires the same consistency policy.

```sql
INSERT INTO public.orders (status)
VALUES ('NEW')
RETURNING order_id;
```

If a response returns the ID and a subsequent request reads a standby before replay, the row may not exist there yet.

### 30.1. Return Representation From the Write Result

Where appropriate, return the row/result from the write transaction to avoid a read-after-write round trip.

### 30.2. Sequence State Differs From Row Replication

Sequence values are not synchronized by logical replication the same way row data is; on a physical standby, WAL/recovery maintains state per physical history. On failover/migration, sequence policies must still be verified.

### 30.3. Do Not Infer Row Visibility Solely From an Allocated ID

An ID can be generated before commit, or the transaction can roll back. Treat a row as committed only after the transaction succeeds.

## 31. Read-After-Write for Permissions and Security State

Changes such as revoking a role, disabling an account, updating permissions, or rotating access state typically require high freshness.

If an authorization service reads a stale standby, a recently locked user might still be granted access from old data.

### 31.1. Security-Sensitive Reads

Read from the primary or a consistency-aware replica for access-control decisions requiring immediate updates.

### 31.2. Cache TTL

A long TTL can extend the stale window even after PostgreSQL has replayed. Invalidation/versioning must align with replication policy.

### 31.3. Fail Closed vs. Fail Open

When primary/replica cannot verify the latest permissions, policy must be set by security/business owners. Never default to fail-open for sensitive operations.

### 31.4. Audit

Log the request, decision version/LSN token, and source node per policy for investigating stale authorization if it occurs.

## 32. Read-After-Write for Balances and Inventory

Workflows that must never oversell inventory or display wrong balances require a clear consistency strategy.

### 32.1. Command/Query Separation

Write commands to the primary; read immediate outcomes from the transaction/write response or the primary. Read models on standbys can update afterward.

### 32.2. Never Use a Stale Replica to Enforce Invariants

If inventory decrement decisions rely on a stale replica, two requests can both see old stock. Invariants must be enforced via transactions/locking/constraints on the authoritative primary.

### 32.3. Display Pending Status

A lagging read model can show a pending status with a version/watermark and update once the projection catches up.

### 32.4. Read Replicas Do Not Replace Transaction Isolation

Never use replica routing in place of row locks, atomic updates, or constraints required for correctness.

## 33. Checking Consistency With SQL

On the primary, after a transaction commits:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_current_wal_lsn() AS consistency_lsn;
```

On the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn AS reached_token;
```

### 33.1. Inspecting Replication Positions on the Primary

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

### 33.2. Inspecting the Receiver on a Standby

```sql
SELECT
    status,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
```

### 33.3. Checking a Row After the Fence

```sql
SELECT
    order_id,
    status,
    updated_at
FROM public.orders
WHERE order_id = 9001;
```

Run `SELECT` in a new transaction after the token is reached.

## 34. Measuring Read-After-Write Latency

Measure the time from `COMMIT` acknowledgement until the standby reaches the token and the read query sees the data.

A test agent:
1. Writes a unique marker on the primary.
2. Executes `COMMIT`.
3. Captures the post-commit LSN token.
4. Starts a monotonic timer.
5. Polls standby replay LSN.
6. Upon reaching the token, opens a new transaction and queries the marker.
7. Verifies the marker exists.
8. Logs elapsed time, replica identity, and token.
9. Repeats during peak/off-peak hours.

### 34.1. Measure Multiple Percentiles

Report median, P95, and P99 when enough samples exist, along with timeout rate and fallback rate.

### 34.2. Separate Wait Time and Query Time

Record commit latency, time waiting for replay, standby query latency, and end-to-end application latency separately.

### 34.3. Check for False Success

Do not stop merely at `replay LSN >= token`; also query the row/transaction marker and confirm the business result.

### 34.4. Test Across Every Replica Class

Synchronous, async, cross-region, delayed, and reporting standbys have different freshness characteristics. Measure separately.

## 35. Timeout, Retry, and Fallback Design

Consistency waits need timeouts. Example policy:
- Wait on standby for 100 ms.
- If not reached, try another standby.
- If still not reached and primary is healthy, route to primary.
- If primary is unavailable, return retryable/unavailable per business contract.

This is only an example; actual budgets depend on SLA.

### 35.1. Retries Must Be Idempotent

Read retries are safer than write retries. If retrying a write after a commit-ambiguity timeout, use an idempotency key.

### 35.2. Jitter

Add jitter to polling/retries to prevent thundering herds.

### 35.3. Circuit Breaker

If a replica repeatedly misses freshness SLOs, temporarily stop routing consistency-sensitive reads to that node.

### 35.4. Observability

Log reason codes: `token_not_reached`, `wrong_timeline`, `replica_disconnected`, `timeout`, `primary_fallback`, or `cache_bypass`.

## 36. Updating Routing After Promotion

When a standby is promoted:
- `pg_is_in_recovery()` changes state.
- Endpoint roles must be updated.
- Other replicas must follow the new primary per topology.
- LSN/timeline history may change.
- Session tokens from the old history must be handled.

### 36.1. Do Not Let Applications Write to the Old Primary

Fencing and routing updates must prevent split-brain. Low DNS TTL alone does not replace fencing.

### 36.2. Confirm the New Primary

Use orchestration/HA manager with authoritative role state, health checks, and fencing. Do not rely solely on one query from a load balancer endpoint.

### 36.3. Token Migration

If an old commit is confirmed lost during an async failover, the application must reconcile via idempotency keys/business records. Waiting on an old LSN token cannot make a lost transaction appear.

### 36.4. Rebuild Session Consistency State

After failover, per-session last-seen tokens may need to be reset or remapped to the new timeline and verified data.

## 37. Consistency With Caches and Read Models

A system may have multiple copies:
- PostgreSQL primary.
- Physical standby.
- Logical subscriber.
- Redis cache.
- Search index.
- Analytics warehouse.

Each copy has its own pipeline and watermark.

### 37.1. Do Not Use PostgreSQL LSN for Every System

LSN only describes the WAL history of a PostgreSQL cluster. Logical consumers, message brokers, and search indexes have their own checkpoints/offsets.

### 37.2. Unified Watermark

An application can maintain a causal context combining PostgreSQL LSN, event ID, and consumer watermark if a request spans multiple systems.

### 37.3. Cache Invalidation After Commit

Use an outbox or versioned cache updates to reduce races between commit and cache invalidation.

### 37.4. Read Models Can Lag Even When PostgreSQL Standbys Are Fast

If downstream ETL/consumers are slow, the read model falls behind. Measure pipelines end-to-end.

## 38. Consistency Anti-Patterns

- Writing to the primary and immediately reading any standby without accepting stale reads.
- Using a fixed 1-second sleep instead of checking replay LSN.
- Treating `write_lag` or `replay_lag` as a RYW guarantee.
- Using sticky sessions without tracking replica freshness.
- Checking LSN on standby A and then querying standby B.
- Waiting for an LSN inside an already-open `REPEATABLE READ` transaction.
- Enabling `remote_apply` while routing reads to a different async replica.
- Comparing LSNs across a timeline fork without checking history.
- Invalidating cache before the transaction commits.
- Retrying non-idempotent writes after a network timeout.
- Using a stale read replica to decide inventory/balance/authorization.
- Declaring service restored just because the database started.
- Using a single PostgreSQL metric to represent queue/search/cache pipelines.
- Ignoring fallback rate and overloading the primary when replicas lag.

## 39. Runbook: Request Just Wrote but Read Does Not See It

1. Record request ID, transaction ID/business key, and `COMMIT` acknowledgement timestamp.
2. Determine whether the write committed successfully or the client hit commit ambiguity.
3. Record primary identity, cluster identity, and post-commit LSN token if available.
4. Determine whether the read request went to the primary or which standby.
5. Check `pg_is_in_recovery()` and server identity on the read backend.
6. If it is a standby, check `pg_last_wal_replay_lsn()`.
7. Compare replay LSN against the token within the same WAL history.
8. Check whether transaction isolation/snapshot was opened before replay.
9. Check caches, ORM identity maps, and application read models.
10. If the token is not reached, wait within budget or route to primary.
11. If the token is reached, open a new transaction and inspect the row/query.
12. If failover occurred, verify timeline and reconcile commit ambiguity.
13. Record stale-read duration, fallback, and root cause.

### 39.1. Do Not Immediately Conclude Replication Is Broken

The request may simply have routed to the standby before replay. Verify the node and LSN first.

### 39.2. If the Token Is Reached but the Row Is Missing

Check whether the transaction committed to the right database/schema, whether row filters/application queries exclude the row, whether the transaction rolled back/was overwritten, and whether the token matches the cluster/timeline.

### 39.3. If Even the Primary Does Not See It

The commit may not have succeeded, the transaction may have rolled back, the application may be reading the wrong tenant/database, or commit outcome may be unknown.

## 40. Runbook: Designing Consistency for an Endpoint

1. Identify the business workflow and data the endpoint requires.
2. Determine whether it depends on a just-committed write.
3. Define the maximum acceptable stale window.
4. Choose primary, LSN fence, `remote_apply`, or eventual read.
5. Define transaction snapshot/isolation.
6. Define routing and replica identity.
7. Set timeout/fallback behavior.
8. Handle caches/ORMs/read models.
9. Define idempotency for writes and retries.
10. Write integration tests for lag, timeouts, failover, and stale caches.
11. Measure latency/fallback rates.
12. Document the consistency contract in API/runbook docs.

## 41. Practice Exercises With Answers

### Exercise 1. Why can reading from a standby return stale data?

**Answer:** The standby may not yet have replayed the WAL containing the transaction just committed on the primary.

### Exercise 2. Does received WAL mean the row is visible?

**Answer:** No. The WAL still has to be replayed.

### Exercise 3. What is read-after-write?

**Answer:** After a successful write, the client's subsequent read sees that change according to the consistency contract.

### Exercise 4. How does read-your-writes differ from eventual consistency?

**Answer:** Read-your-writes guarantees a client sees its own writes; eventual consistency only requires replicas to converge once updates stop.

### Exercise 5. What do monotonic reads mean?

**Answer:** A client never sees a state older than one it has already observed.

### Exercise 6. Does session stickiness to a standby guarantee RYW?

**Answer:** No. That standby may still not have replayed the just-committed transaction.

### Exercise 7. What is the simplest way to read immediately after writing?

**Answer:** Route the read to the primary or read the result directly within the write transaction.

### Exercise 8. What is an LSN token?

**Answer:** A WAL position captured after commit to serve as a consistency fence for standbys.

### Exercise 9. Why capture the token after COMMIT?

**Answer:** So the token includes the commit record; a token captured before commit might not cover the transaction to be read.

### Exercise 10. Which function retrieves the current WAL write position on the primary?

**Answer:** `pg_current_wal_lsn()`.

### Exercise 11. Which function retrieves the replay position on a standby?

**Answer:** `pg_last_wal_replay_lsn()`.

### Exercise 12. What is the basic fence condition?

**Answer:** The standby replay LSN must equal or exceed the token within the same WAL history.

### Exercise 13. Should LSNs be compared using text comparison in the application?

**Answer:** No. Use the `pg_lsn` type/operators or a proper parser, while also accounting for cluster/timeline.

### Exercise 14. Why can the token be higher than the request's commit?

**Answer:** WAL from other concurrent transactions may be written before the token is read; the token remains a safe upper bound within the same history.

### Exercise 15. Is an LSN fence a distributed transaction?

**Answer:** No. It only checks the replay progress of a standby.

### Exercise 16. After the token is reached, is a new read transaction needed?

**Answer:** Yes, to acquire a snapshot started after replay reached the token, especially if an older transaction snapshot existed earlier.

### Exercise 17. When does READ COMMITTED take a snapshot?

**Answer:** Each statement normally acquires a fresh snapshot.

### Exercise 18. Does REPEATABLE READ automatically see new WAL mid-transaction?

**Answer:** No. The transaction holds a steady snapshot.

### Exercise 19. Does SERIALIZABLE on a standby synchronize snapshots with the primary?

**Answer:** No. It only provides isolation semantics on that node/transaction.

### Exercise 20. Does synchronous_commit = on wait for standby replay?

**Answer:** No. With synchronous replication, `on` waits for remote WAL flush.

### Exercise 21. What does remote_apply wait for?

**Answer:** It waits for the synchronous standby to replay the transaction WAL before commit acknowledgement is returned.

### Exercise 22. Does remote_apply guarantee all standbys have replayed?

**Answer:** No. It follows the synchronous standby policy; other async replicas may still lag.

### Exercise 23. Is remote_write equivalent to remote durable flush?

**Answer:** No. It waits for the standby to write WAL to the OS, not a durable flush.

### Exercise 24. Is setting synchronous_commit = remote_apply alone enough?

**Answer:** No. `synchronous_standby_names` and an actively functioning standby are also required.

### Exercise 25. Why can remote_apply increase commit latency?

**Answer:** Commits must wait for network round trips, standby flush, and replay.

### Exercise 26. Why do long queries on a standby affect remote_apply?

**Answer:** Recovery conflicts can delay replay, making commits wait longer.

### Exercise 27. Is a delayed standby suitable for RYW?

**Answer:** Usually not; replay is intentionally delayed.

### Exercise 28. Why not use a fixed sleep to wait for a replica?

**Answer:** Lag varies with workload; the sleep may be too short or add unnecessary latency.

### Exercise 29. Does polling LSN require a timeout?

**Answer:** Yes. Requests need a latency budget and a fallback policy.

### Exercise 30. If a standby has not reached the token, what are the options?

**Answer:** Wait, try another replica, read from primary, return retry/unavailable, or serve stale if the contract allows.

### Exercise 31. Why must the fence check and SELECT run on the same standby?

**Answer:** If the query routes to another node, that node may not have replayed up to the token yet.

### Exercise 32. Can LSN tokens be blindly compared across a failover timeline?

**Answer:** No. Timelines can fork; history and transaction survival must be verified.

### Exercise 33. Can an async failover lose a commit acknowledged to the client?

**Answer:** Yes, if the promoted standby had not received that transaction yet.

### Exercise 34. What is commit ambiguity?

**Answer:** A client loses connection around `COMMIT` time and does not know whether the transaction committed or rolled back.

### Exercise 35. How do idempotency keys help?

**Answer:** They allow retrying a business operation without creating duplicate effects when the commit outcome is unknown.

### Exercise 36. Can a cache cause stale reads even after the standby has replayed?

**Answer:** Yes. Caches/ORMs/search indexes have their own freshness pipelines.

### Exercise 37. When should cache invalidation happen?

**Answer:** After the transaction commits successfully, per the application's consistency policy.

### Exercise 38. Does an LSN fence prove Redis has updated?

**Answer:** No. An LSN only describes PostgreSQL WAL replay.

### Exercise 39. What does causal consistency across a message queue require?

**Answer:** Event IDs/offsets/watermarks and mechanisms tracking consumer progress; PostgreSQL LSN alone is not enough.

### Exercise 40. Can a GET request require read-after-write?

**Answer:** Yes. HTTP method does not determine consistency; business logic and causal dependencies do.

### Exercise 41. Should balance/inventory write decisions rely on a stale standby?

**Answer:** No. Invariants must be protected on the authoritative primary via appropriate transactions/constraints/locking.

### Exercise 42. Do read replicas replace row locks?

**Answer:** No. Read replicas serve reads; they do not replace transaction coordination on the primary.

### Exercise 43. Why must security-sensitive reads be routed carefully?

**Answer:** Stale permissions/account states can allow access that was already revoked.

### Exercise 44. After reaching the fence, will an existing REPEATABLE READ transaction see new data?

**Answer:** No. A fresh transaction snapshot is needed.

### Exercise 45. How do you measure read-after-write latency?

**Answer:** Measure from `COMMIT` acknowledgement until standby replay reaches the token and the read query confirms the marker.

### Exercise 46. How does P95 read-after-write wait help?

**Answer:** It shows tail latency of replica freshness and helps set timeout/fallback budgets.

### Exercise 47. Why check pg_is_in_recovery()?

**Answer:** To know whether the endpoint is a standby or has been promoted; role affects how replay LSN is interpreted.

### Exercise 48. What if the primary is unavailable and the standby has not reached the token?

**Answer:** You cannot materialize an unreplicated transaction; handle unavailable/uncertain states and reconcile per business policy.

### Exercise 49. Does a read-after-write guarantee automatically apply to a search index?

**Answer:** No. Search indexes need their own consumer watermarks or consistency mechanisms.

### Exercise 50. What must an endpoint with a strong consistency contract define?

**Answer:** Source of truth, stale window, read route, snapshot behavior, token/fence, timeout/fallback, cache behavior, and validation tests.

## 42. Read Consistency Design Checklist

| Stage | Question |
|---|---|
| Business | Does the request depend on a just-committed write? |
| Business | What is the maximum acceptable stale window? |
| Source | Which primary is authoritative? |
| Routing | Does the read go to the primary or which standby? |
| Replication | Is the standby async, sync, quorum, or delayed? |
| Token | Is a post-commit LSN fence needed? |
| Fence | Is the token captured after `COMMIT`? |
| Identity | Do the check and `SELECT` run on the same standby? |
| Snapshot | Did the read transaction start after the fence? |
| Isolation | `READ COMMITTED` or fixed snapshot? |
| Timeout | Is the wait budget bounded? |
| Fallback | Switch to primary, retry, or return pending? |
| Failover | Does the token belong to the current timeline? |
| Cache | Can caches/ORMs/search indexes be stale? |
| Retry | Do writes have idempotency keys? |
| Security | Do permission-sensitive reads have proper freshness? |
| Metrics | Are commit latency, wait time, and fallback rate measured? |
| Testing | Are lag, failover, timeout, and cache races tested? |
| Documentation | Is the endpoint consistency contract clearly documented? |

## 43. Official PostgreSQL Documentation

- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — standby reads, snapshots, and recovery conflicts.
- [Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — WAL streaming and standbys.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous standbys and commit acknowledgement.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — `synchronous_commit` and WAL settings.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`.
- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — current/replay LSN and recovery functions.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication positions and lag.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — `synchronous_standby_names` and replication settings.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery delay settings.

Replication views, synchronous behavior, and function availability can vary by PostgreSQL major version. Before deploying consistency fences or `remote_apply`, verify `server_version`, `pg_settings`, topology, and the documentation for your exact version.

## 44. Summary: Choosing the Read Path by Consistency Contract

```text
Write transaction
      |
      v
COMMIT acknowledged on primary
      |
      +--> Read from primary
      |        |
      |        +--> Fresh primary snapshot
      |
      +--> Read from standby
               |
               v
          Obtain LSN token
               |
               v
          Check replay_lsn >= token
               |
          +----+----+
          |         |
         Yes        No
          |         |
          v         v
      New read    Wait / retry
      transaction     |
          |            +--> Another replica
          v            +--> Primary fallback
      Read-your-writes +--> Pending/unavailable
```

Key principles to remember:

1. **A standby can be stale even when replication is operating normally.** WAL must be replayed before changes become visible.
2. **Read-after-write is an application contract.** It does not happen automatically just because a write `COMMIT`ted on the primary.
3. **Reading from the primary is the simplest approach for RYW.** Use standbys when an explicit freshness policy is in place.
4. **An LSN token creates a consistency fence.** Capture it after `COMMIT` and only compare within the same cluster/WAL history.
5. **The fence must be verified on the exact standby serving the SELECT.** Never check one node and read from another.
6. **Open the read transaction after the fence is reached.** An older `REPEATABLE READ` snapshot does not refresh automatically.
7. **remote_apply waits for synchronous standby replay.** It does not guarantee every async standby has caught up.
8. **Session stickiness does not replace an LSN fence.** Even the same standby can lag.
9. **Caches and read models have separate consistency.** A PostgreSQL LSN does not prove external consumers have updated.
10. **Failover can change timelines and introduce commit ambiguity.** Use idempotency keys and reconciliation.
11. **Timeouts/fallbacks must stay within the latency budget.** Never wait forever or silently return stale data.
12. **Choose consistency by business need.** Balances, inventory, and authorization need stricter policies than analytics.

**One sentence to remember:** *After writing, only read from a standby when you know it has replayed up to the transaction you need to see; if you cannot prove that within your latency budget, read from the primary or return a pending state per your consistency contract.*
