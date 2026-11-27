# Group Replication Consistency Levels and Latency Impact

MySQL Group Replication distributes transactions across members of a group. After a transaction is certified and committed in the shared global order, remaining members still need time for their appliers to execute the changes against local data. During that interval, a client reading from another member may see stale state. This is a fundamental characteristic of asynchronous application and explains why MySQL provides consistency levels for Group Replication.

The `group_replication_consistency` variable lets you choose whether to wait before a transaction executes, after a transaction commits, or both. Stronger consistency levels can guarantee certain read-after-write behaviors and reduce stale reads, but typically increase response latency—especially when a member applies changes slowly. Selecting the right level balances the consistency your application needs against the latency your system can tolerate.

## 1. Why can Group Replication return stale data?

Group Replication uses group communication to distribute transactions and runs certification to detect write conflicts. Transactions are ordered in a common global sequence. However, committing on the originating member does not mean every member has already applied that transaction to its local tables.

High-level flow:

```text
Client sends transaction to member A
              |
              v
    Execute and build write set
              |
              v
  Group communication / certification
              |
              v
     Transaction committed
              |
        +-----+-----+
        |           |
        v           v
   Member A     Members B, C
   applies      receive and queue
   locally      for applier
                    |
                    v
              Applied later
```

For example, an application updates an order status on member A and immediately sends a read query to member B. If B's applier has not processed that committed transaction yet, the query can observe the old status. This is commonly referred to as replication lag or apply lag.

In single-primary mode, writes generally go to the primary while read queries may be distributed across secondaries. In multi-primary mode, multiple members can accept writes, yet each member still maintains its own applier queue. Certification resolves transaction conflicts; it does not automatically ensure every read on every member sees every latest commit.

## 2. What does `group_replication_consistency` control?

`group_replication_consistency` specifies the synchronization guarantee a transaction requires from Group Replication. It has both GLOBAL and SESSION scope, defaulting to `EVENTUAL` in standard MySQL configurations.

| Level | Primary behavior | Common impact |
|---|---|---|
| `EVENTUAL` | Does not wait for prior transactions to apply before running, and does not wait for the current transaction to apply on other members before returning commit | Lower latency; applications may read stale data on other members |
| `BEFORE` | Waits for prior transactions in the group order to apply on the executing member before running the current transaction | Increases transaction start latency when the member has a backlog; ensures reads on this member see earlier commits |
| `AFTER` | Waits for the current transaction to apply on group members before returning commit success | Ties commit latency to the slowest member's apply speed; supports read-after-write when switching members after commit returns |
| `BEFORE_AND_AFTER` | Combines waiting both before and after the transaction | Stronger guarantees, but can increase both start and commit latency |
| `BEFORE_ON_PRIMARY_FAILOVER` | In single-primary mode, a newly elected primary waits for its transaction backlog from the old primary to apply before processing new transactions | Can delay initial transactions post-failover; prevents a new primary from serving stale state before old data finishes applying |

These levels govern when a transaction proceeds within Group Replication. They do not turn Group Replication into a synchronous system where every SQL operation completes simultaneously on every server. Actual latency still depends on group communication, networking, certification, CPU load, storage speed, and applier queues.

## 3. Understanding each consistency level

### EVENTUAL — prioritizing low latency

`EVENTUAL` adds no wait conditions to synchronize prior or current transactions across members. This default fits workloads that tolerate slightly stale reads for short windows.

Example:

```sql
-- Connection A: write on primary
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;

-- Connection B: read on another member with EVENTUAL
SET SESSION group_replication_consistency = 'EVENTUAL';
SELECT status
FROM sales.orders
WHERE order_id = 1001;
```

If the `SELECT` executes on a member that has not yet applied the update transaction, the result may still be `PENDING`. The application must tolerate delayed visibility or enforce stronger read consistency explicitly.

### BEFORE — waiting for local backlog before execution

`BEFORE` requires the executing member to wait until all transactions preceding this one in the group order have been applied on that member. Only after that condition is satisfied does the transaction execute.

This level is useful when a session needs to read previously committed data on a specific member. For instance, after learning a transaction committed in the group, the application sends a read transaction to member B with `BEFORE`; B waits to catch up on preceding transactions before running the query.

```sql
SET SESSION group_replication_consistency = 'BEFORE';

START TRANSACTION READ ONLY;
SELECT status
FROM sales.orders
WHERE order_id = 1001;
COMMIT;
```

`BEFORE` does not wait for the current transaction to apply across all members before returning, nor does it force other members to catch up. If the executing member has a large backlog, the wait before the transaction starts can grow substantially.

### AFTER — waiting for changes to apply across the group

`AFTER` makes the transaction wait until its own changes have been applied across group members before `COMMIT` returns to the client.

This level helps write-then-read flows across different members. Once the write succeeds, the application can switch to reading from another member without hitting apply lag for that newly committed transaction, within the scope of active group members.

```sql
SET SESSION group_replication_consistency = 'AFTER';

START TRANSACTION;
UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;
COMMIT;
```

When `COMMIT` returns, the transaction has been applied on members required to satisfy the group consistency guarantee. In exchange, commit duration depends on the slowest applying member. A member with slow storage, saturated CPU, or a deep applier queue increases latency for waiting transactions.

### BEFORE_AND_AFTER — waiting on both sides

`BEFORE_AND_AFTER` combines both rules: the executing member waits for preceding transactions to apply before running the current transaction, then waits for the current transaction to apply across the group before commit returns.

This suits sensitive operations that must both observe prior updates and ensure new changes propagate before reporting success. However, waiting both before and after increases response time and can hurt throughput under heavy load. Apply it only to workloads that genuinely need this guarantee.

### BEFORE_ON_PRIMARY_FAILOVER — avoiding stale reads after primary switchover

In single-primary mode, when the old primary leaves and another member is elected primary, the new member may still have a backlog of group-accepted transactions awaiting apply. If the application immediately sends new transactions, the new primary risks processing work while older data is still pending application.

`BEFORE_ON_PRIMARY_FAILOVER` makes transactions on the new primary wait for the backlog from the old primary to finish applying before proceeding. This eliminates a window where the new primary could serve stale state right after failover. In return, the first transactions after a primary transition can stall significantly if the backlog is large.

This level targets single-primary failover scenarios and is not a general substitute for `BEFORE` or `AFTER` across all workloads. Check your MySQL version and Group Replication mode before configuring it.

## 4. How consistency levels impact latency

Each level introduces a different synchronization point into the transaction path:

| Level | Potential wait point | Dominant latency factor |
|---|---|---|
| `EVENTUAL` | No extra apply wait from consistency level | Local execution, group communication, and certification |
| `BEFORE` | Before transaction execution | Transactions queued in local applier and local apply speed |
| `AFTER` | Before commit returns | Slowest applying member in the group, network, and applier load |
| `BEFORE_AND_AFTER` | Before execution and before commit returns | Sum of local backlog wait and group-wide apply wait |
| `BEFORE_ON_PRIMARY_FAILOVER` | On the new primary after failover | Remaining backlog from old primary and new primary's apply speed |

You can visualize the added latency as follows:

```text
EVENTUAL
  Execute -> certify/commit -> return result

BEFORE
  Wait for local backlog -> execute -> certify/commit -> return result

AFTER
  Execute -> certify/commit -> wait for members to apply -> return result

BEFORE_AND_AFTER
  Wait for local backlog -> execute -> commit -> wait for members to apply -> return result
```

This is a conceptual model, not a fixed timing formula. Internal steps may overlap and depend on version, topology, and group state.

In practice, `AFTER` tends to inflate tail latency noticeably whenever one member lags behind the others. Even if the primary is healthy, sessions waiting on `AFTER` stall on the lagging member's apply speed. `BEFORE` makes a lagging reader wait for its own backlog without necessarily stalling transactions on other members for the same duration.

### Comparison example

Suppose a group has three members A, B, and C. A receives a write transaction. B applies changes in 15 ms, and C in 90 ms.

| Setting | When the client receives the result (simplified) |
|---|---|
| `EVENTUAL` | Once commit steps finish on A; B and C may still be applying |
| `AFTER` | Only after B and C have applied the transaction, thus governed by member C in this example |
| `BEFORE` on B | A new transaction on B waits for B's prior backlog; it does not wait for A's new transaction to finish applying on C |
| `BEFORE_AND_AFTER` | Waits for local backlog on the executing member and group-wide apply of the current transaction |

These numbers are illustrative only. Do not use them as production forecasts; benchmark on a realistic topology with representative transaction sizes, load, and network links.

## 5. Choosing levels by workload type

Not every session needs the same level. Choose per application workflow:

| Workload | Candidate level | Rationale |
|---|---|---|
| Reporting tolerant of brief lag | `EVENTUAL` | Keeps latency low and tolerates replicas still catching up |
| Reading after a prior transaction committed, on current member | `BEFORE` | Waits for local backlog before reading |
| Writing and immediately reading from another member | `AFTER` | Commit returns only after changes apply across the group |
| Critical operations needing both prior state and propagated changes | `BEFORE_AND_AFTER` | Waits both before and after the transaction |
| Single-primary systems avoiding stale state post-failover | `BEFORE_ON_PRIMARY_FAILOVER` | New primary drains backlog from old primary |

For example, an e-commerce platform might use `EVENTUAL` for summary dashboards, `BEFORE` for secondary reads triggered after receiving a commit notification, and `AFTER` for writes immediately followed by reads routed to another member. Validate choices against real routing paths: reading back on the same session/member has different needs than hopping across members.

Consistency levels do not replace InnoDB transaction isolation. `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` govern intra-transaction visibility rules; `group_replication_consistency` governs waiting between transactions and group members. Both mechanisms solve distinct layers of problems.

## 6. Configuring at server and session scope

Check current values:

```sql
SHOW GLOBAL VARIABLES LIKE 'group_replication_consistency';
SHOW SESSION VARIABLES LIKE 'group_replication_consistency';
```

Set a level for a specific session:

```sql
SET SESSION group_replication_consistency = 'BEFORE';
```

Set the server-wide default for new sessions:

```sql
SET GLOBAL group_replication_consistency = 'EVENTUAL';
```

`SET SESSION` affects only the current connection. `SET GLOBAL` updates the global default without changing existing sessions' already-set values. When using connection pools, explicitly set session variables when checking out a connection and reset them on return so a request needing strong consistency does not leak its setting into the next request.

Set the startup default in the configuration file:

```ini
[mysqld]
group_replication_consistency=EVENTUAL
```

Or use `SET PERSIST` if your version and configuration management policy allow it:

```sql
SET PERSIST group_replication_consistency = 'EVENTUAL';
```

Run example commands with appropriate privileges and verify behavior on your exact MySQL version. Before changing global settings, assess the impact across all applications connected to that member.

## 7. Observing backlogs and lag

To understand why a consistency level introduces waits, monitor member state and applier queues.

List group members:

```sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Inspect per-member transaction stats:

```sql
SELECT
  MEMBER_ID,
  COUNT_TRANSACTIONS_IN_QUEUE,
  COUNT_TRANSACTIONS_REMOTE_IN_APPLIER_QUEUE,
  COUNT_TRANSACTIONS_REMOTE_APPLIED,
  COUNT_TRANSACTIONS_LOCAL_PROPOSED,
  COUNT_CONFLICTS_DETECTED
FROM performance_schema.replication_group_member_stats;
```

These columns report transaction counts in queues and apply/certification activity. Check exact counter semantics for your version. Tracking trends over time is usually far more informative than a single snapshot.

Additionally, inspect applier workers:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;
```

When investigating latency, combine these signals:

- `ONLINE`/`RECOVERING` member states in `replication_group_members`.
- Remote applier queue depth and counter rates in `replication_group_member_stats`.
- CPU, I/O, buffer pool, lock waits, and commit times per member.
- Network latency, packet loss, and performance variance across zones.
- Application commit and read latency histograms at p50, p95, and p99.

Do not use asynchronous replication's `Seconds_Behind_Source` as the sole proxy for Group Replication lag. Monitor Performance Schema metrics and application telemetry suited to group operation.

## 8. Flow control and consistency levels

Group Replication includes flow control to throttle members generating transactions faster than other members can apply them. When queues cross thresholds, flow control asks members to slow down transaction generation so the group can catch up.

Flow control and `group_replication_consistency` both relate to latency, yet are distinct:

- Consistency levels specify where a transaction waits to achieve requested visibility guarantees.
- Flow control throttles transaction generation rates when one or more members fall behind.

If one member is chronically slow, `AFTER` lengthens commit times for waiting sessions while flow control simultaneously caps group-wide throughput to curb backlog growth. Raising flow-control thresholds just to mask lag will not fix root causes like slow storage, oversized transactions, or insufficient applier workers.

When tuning, evaluate transaction sizes, applier worker counts, CPU, IOPS, and flow-control settings together. Change one parameter at a time, measure p95/p99, and inspect group health before rolling into production.

## 9. Handling failovers and slow members

In single-primary mode, a new primary is elected after the old primary leaves or becomes ineligible. Some group-accepted transactions may still be waiting in the new member's applier queue. If applications immediately send read/write traffic to the new primary, results can be unexpected until the backlog clears.

`BEFORE_ON_PRIMARY_FAILOVER` closes this gap by forcing transactions on the new primary to wait for the old primary's backlog first. Applications must account for this post-failover drain time in RTO budgets and health checks. A TCP port check alone does not prove the backlog has finished applying.

If a slow member causes `AFTER` transactions to stall:

1. Identify which member shows a steadily growing remote applier queue.
2. Check CPU, storage latency, lock contention, and transaction sizes on that member.
3. Verify inter-member networking and overall group state.
4. Assess whether the member can catch up or should be removed per operational runbook.
5. Re-measure commit latency and availability after fixing the root cause.

Never arbitrarily remove a member just to lower latency. Membership changes impact quorum, fault tolerance, and resynchronization overhead when the member rejoins. Follow Group Replication procedures and check remaining member counts before making changes.

## 10. Practical scenario

An ordering system runs a three-member Group Replication cluster in single-primary mode. The application writes orders to the primary, and another service reads status from a secondary. Dashboards can tolerate slight lag, but the payment confirmation API must ensure subsequent reads see the updated status.

**Step 1 — Measure baseline.** Leave sessions on `EVENTUAL`, and record p50/p95/p99 for commits and reads. Monitor applier queues on each member.

**Step 2 — Set consistency for sensitive flows.** For write sessions requiring changes to propagate across the group before responding, set `AFTER`:

```sql
SET SESSION group_replication_consistency = 'AFTER';

UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 1001;
```

The application waits for commit to return before sending the read request to a secondary. Verify the secondary returns status `PAID`.

**Step 3 — Keep dashboards on EVENTUAL.** Reporting sessions stay on `EVENTUAL` so dashboard queries do not stall behind slow members. Dashboard views are documented as potentially lagging within workload bounds.

**Step 4 — Simulate a slow member.** Introduce synthetic I/O load or test workload on one member in staging. Compare commit latency between `EVENTUAL` and `AFTER`; observe applier queues and p99. Never run disruptive load tests on production.

**Step 5 — Drill failover.** Perform a controlled primary switchover. If using `BEFORE_ON_PRIMARY_FAILOVER`, measure how long the new primary waits for its backlog and verify the API accepts transactions only once consistency requirements are satisfied.

The expected outcome is that only read-after-write flows pay the stronger synchronization cost, while reporting workloads retain low latency. Operations should budget latency for post-failover backlog drains and monitor slow members to prevent unexpected tail-latency spikes.

## 11. Production readiness checklist

- [ ] Consistency requirements identified per workload: stale reads tolerable vs. read-after-write required.
- [ ] `EVENTUAL`, `BEFORE`, `AFTER`, `BEFORE_AND_AFTER`, and `BEFORE_ON_PRIMARY_FAILOVER` distinguished clearly.
- [ ] MySQL version, single-primary/multi-primary mode, and supported consistency levels verified.
- [ ] `SET SESSION` tested per session type and connection pool variable reset verified.
- [ ] p50, p95, p99, and throughput measured across each consistency level on a production-like topology.
- [ ] Slow members, applier backlogs, CPU, storage, and network latency checked.
- [ ] Effects of consistency levels distinguished from flow control and transaction isolation.
- [ ] Failover drilled and post-failover backlog wait measured if using `BEFORE_ON_PRIMARY_FAILOVER`.
- [ ] Alerts configured for member state changes, growing applier queues, or commit latency breaching budgets.
- [ ] Timeouts, retries, and application behavior verified when transactions wait too long or fail.

Group Replication consistency levels are a transaction-scoped tool for controlling synchronization points across members. `EVENTUAL` favors low latency, `BEFORE` waits for local backlogs, `AFTER` waits for changes to apply across the group, and `BEFORE_AND_AFTER` combines both. For single-primary failovers, `BEFORE_ON_PRIMARY_FAILOVER` ensures the new primary drains its backlog before serving new transactions. Matching levels to workloads and measuring latency per member helps satisfy consistency requirements while keeping performance predictable.
