# Cross-Shard Transactions, XA, and Distributed Coordination Limits

When MySQL data is split across multiple shards, a business operation must sometimes update multiple servers. Examples include transferring funds between two accounts residing on different shards, creating an order on an order shard while reserving stock on an inventory shard, or updating customer data and a ledger across separate partitions. Each shard has its own InnoDB transaction; `COMMIT` on the first shard does not automatically commit or roll back the second shard.

To achieve a uniform commit outcome across multiple resource managers, a system can use **XA transactions with two-phase commit (2PC)**. A transaction coordinator orchestrates XA branches across each shard: asking all participants to prepare to commit, durably logging the decision, and then instructing the shards to commit. This mechanism provides an atomic outcome when components and recovery workflows operate properly, at the cost of network round trips, longer-held locks, in-doubt states, and reliance on the coordinator.

Not every cross-shard operation needs XA. Designing shard keys so data belonging to the same aggregate stays on the same shard is usually simpler and faster. For workflows that tolerate eventual consistency, sagas combined with a transactional outbox and compensating actions are often more suitable. This lesson examines these trade-offs, MySQL XA syntax, recovery, and the limits of distributed coordination.

## Learning Objectives

After this lesson, you will be able to:

- Explain why standard InnoDB transactions guarantee atomicity only within a single MySQL instance.
- Design shard keys to minimize multi-shard updates.
- Describe the roles of coordinator, participant, and the two phases of 2PC.
- Read and write `XA START`, `XA END`, `XA PREPARE`, `XA COMMIT`, `XA ROLLBACK`, and `XA RECOVER` statements.
- Analyze failures when the coordinator, participants, or network fail in each phase.
- Recover prepared transactions based on the coordinator's durable decision.
- Compare XA with sagas, outboxes, and eventual consistency.
- Design fault injection tests, monitoring, and operational procedures for cross-shard transactions.

## 1. Why Are Cross-Shard Transactions Harder?

Within a single MySQL instance, InnoDB can use one transaction to update multiple tables:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

COMMIT;
```

If both accounts reside on the same instance and both statements run in the same InnoDB transaction, the changes commit or roll back together. In a sharded system, however, account 101 may reside on `shard-a` while account 202 resides on `shard-b`. The two servers have independent transaction logs, lock managers, and commit states.

If the application sends `COMMIT` to shard A and then shard B fails, money may have been debited from A without being credited to B. If it commits B first and A fails, the inverse error occurs. A loop calling `commit()` sequentially does not produce an atomic distributed transaction.

### 1.1. Goals of Distributed Commit

A cross-shard transaction typically aims to guarantee:

- **Atomic outcome:** every participant commits, or every participant rolls back according to the global decision.
- **Durable decision:** once the coordinator decides to commit or abort, that decision is persisted durably so recovery can proceed.
- **Consistent recovery:** if a process or network fails, participants are reconciled to the same final outcome.

Atomic commit does not automatically enforce every business rule. XA does not create cross-shard foreign keys, verify unencoded business invariants, or automatically provide global serializable isolation across the whole system. Each shard still applies its own local isolation and constraints.

MySQL also has **internal XA** to coordinate storage engine transactions such as InnoDB with the binary log during commit. This is an internal mechanism ensuring consistency between engine data and the binlog; it does not enlist another MySQL server into an application transaction. Internal XA and cross-shard external XA are two distinct scopes.

## 2. Designing Shards to Avoid Cross-Shard Transactions

Before adopting XA, examine whether data frequently modified together can reside on the same shard. Choose shard keys around business aggregates and transaction boundaries.

For example, an e-commerce system can partition by `customer_id`:

```text
shard(customer_id)
   |
   +-- customers
   +-- orders
   +-- order_items
   +-- customer_addresses
```

When placing an order, customer, order, and line-item data can be written in a single transaction on one shard. This avoids distributed coordination for the common path.

However, not all data should be partitioned by the same key. Inventory may partition by `warehouse_id`; ledgers may partition by `account_id`; system-wide reporting may need fan-out queries or a dedicated analytics store. Identify which cross-domain operations are frequent, critical, and require atomic commit.

### 2.1. Issues to Design Upfront

- **Cross-shard foreign keys:** MySQL does not enforce foreign keys across two independent servers. The application must validate references and manage data lifecycles.
- **Global unique constraints:** a unique index on one shard guarantees uniqueness only within that shard. Global uniqueness requires routing all values of that key to the same shard, using a global ID generator, or maintaining a dedicated registry/coordination service.
- **Global IDs:** local auto-increment IDs can collide across shards. Use UUIDs, shard-prefixed IDs, or a suitable ID allocation service.
- **Fan-out queries:** querying across shards requires merging results, handling pagination/sorting, and managing read consistency at the application tier.
- **Hot shards:** partitioning on skewed keys can overload one shard even when total cluster capacity remains available.
- **Shard movement:** migrating data between shards is also a distributed workflow, requiring dual-write/copy/checkpoint/cutover or specialized tooling.

If a cross-shard operation is rare and unavoidable, evaluate XA or sagas against business requirements. Do not let XA become the default mechanism for every request.

## 3. XA and Two-Phase Commit

XA is a protocol coordinating transactions between a transaction manager and multiple resource managers. In a sharded MySQL architecture:

- **Transaction coordinator/manager:** creates the global transaction ID, logs decisions, and orchestrates phases.
- **Participant/resource manager:** each MySQL shard executes one branch of the global transaction.
- **XID:** identifies the global transaction and branch on a participant.

Each participant processes DML inside an XA branch. The coordinator uses two phases to ensure participants converge on a single outcome.

### 3.1. Phase 1 — Prepare

1. The coordinator creates a global transaction ID and determines the participant list.
2. The coordinator instructs each shard to start an XA branch.
3. The application executes DML on each shard.
4. The coordinator ends the active work branch with `XA END`.
5. The coordinator sends `XA PREPARE` to each participant.
6. Each participant votes YES once it has durably logged the prepared state and can commit later; if any cannot prepare, the coordinator must decide to abort.

While a branch is in the prepared state, it has not yet committed but holds the state needed to finish later. InnoDB may continue holding locks and associated resources. Other transactions may block when accessing rows held by a prepared branch.

### 3.2. Phase 2 — Commit or Rollback

- If all participants prepare successfully, the coordinator durably writes a **COMMIT** decision to the coordinator log and sends `XA COMMIT` to each participant.
- If a participant fails to prepare or the coordinator aborts before the commit decision, the coordinator writes a **ROLLBACK** decision and sends `XA ROLLBACK` to the involved branches.
- The coordinator tracks each participant's outcome. If a commit/rollback response is lost, recovery must proceed using the XID and durable decision.

Overview diagram:

```text
                Coordinator
                     |
          +----------+----------+
          |                     |
       shard-a                shard-b
          |                     |
       XA START               XA START
       DML                    DML
       XA END                 XA END
          |                     |
       XA PREPARE             XA PREPARE
          |                     |
       vote YES               vote YES
          +----------+----------+
                     |
             Durably log COMMIT
                 decision
                     |
          +----------+----------+
          |                     |
       XA COMMIT              XA COMMIT
          |                     |
          +----------+----------+
                     |
              Global tx complete
```

The coordinator must persist the participant list and XID before coordinating, then durably record the final decision before issuing phase 2 commands. Never rely on process memory or non-durable logs to drive recovery after a crash.

### 3.3. Why Can 2PC Block?

Suppose both shards have prepared, yet the coordinator crashes before persisting or recovering the final decision. Participants cannot infer on their own whether to commit or roll back. They remain in-doubt and wait for coordinator recovery.

If the coordinator durably logged COMMIT and crashed before sending the command to shard B, recovery must proceed to commit B. Never flip the decision to rollback just because one participant has not yet received the command.

This is a fundamental property of 2PC: it prioritizes an atomic decision, so under certain coordinator/network failures participants may have to wait. XA is not a non-blocking protocol and does not eliminate the impact of network partitions.

## 4. XA Syntax in MySQL

MySQL provides SQL statements to manage XA branches. In production applications, a transaction manager/XA coordinator normally invokes equivalent operations via the JDBC driver's XA resource API. The commands below illustrate server-side states and mechanics.

An XID consists of a global transaction identifier (`gtrid`), a branch qualifier (`bqual`), and a format ID. Branches of the same global transaction share the same `gtrid` while using distinct `bqual` values to identify each participant.

A branch transitions through core states:

| Command | State after command | Meaning |
|---|---|---|
| `XA START` | ACTIVE | The branch is bound to the session and can execute DML |
| `XA END` | IDLE | The session ends participation; the branch is neither prepared nor committed |
| `XA PREPARE` | PREPARED | The participant is prepared to commit or roll back later |
| `XA COMMIT` / `XA ROLLBACK` | Completed | The branch finishes according to the global decision |

`XA RECOVER` lists branches in the `PREPARED` state; it does not list `ACTIVE` or `IDLE` branches and is not a transaction history. When a connection or coordinator fails, determine the last acknowledged XA command and reconcile the XID against the coordinator log; never infer a branch rolled back merely because the client socket closed.

### 4.1. Starting and Ending a Branch

On `shard-a`:

```sql
XA START 'transfer-2026-0001', 'shard-a', 1;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

XA END 'transfer-2026-0001', 'shard-a', 1;
```

On `shard-b`:

```sql
XA START 'transfer-2026-0001', 'shard-b', 1;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

XA END 'transfer-2026-0001', 'shard-b', 1;
```

The example uses the same `gtrid` `'transfer-2026-0001'` with different branch qualifiers. In real systems, XIDs must be unique per coordinator and never reused while older transactions might still undergo recovery.

The application must check affected row counts. If the debit statement did not update exactly one account, the business invariant failed; the coordinator must decide to roll back all branches rather than continuing to prepare/commit.

### 4.2. Prepare and Commit

Once all branches have executed `XA END`, the coordinator instructs each participant to prepare:

```sql
-- On shard-a
XA PREPARE 'transfer-2026-0001', 'shard-a', 1;

-- On shard-b
XA PREPARE 'transfer-2026-0001', 'shard-b', 1;
```

Only after receiving successful prepare results from all participants and durably logging the COMMIT decision does the coordinator send:

```sql
-- On shard-a
XA COMMIT 'transfer-2026-0001', 'shard-a', 1;

-- On shard-b
XA COMMIT 'transfer-2026-0001', 'shard-b', 1;
```

If aborting per the coordinator's decision:

```sql
XA ROLLBACK 'transfer-2026-0001', 'shard-a', 1;
XA ROLLBACK 'transfer-2026-0001', 'shard-b', 1;
```

These statements illustrate the sequence across each shard, not a script to run arbitrarily on a single connection. In real applications, the coordinator must manage sessions/resources, per-step errors, timeouts, durable logs, and recovery. Never write ad-hoc `XA COMMIT` loops without a coordinator log.

### 4.3. `XA RECOVER`

On each MySQL participant, operators can inspect XA branches currently in the prepared state:

```sql
XA RECOVER;
```

The output typically includes `formatID`, `gtrid_length`, `bqual_length`, and `data` containing the XID identifier bytes. `XA RECOVER` is an inventory tool for prepared branches; it does not reveal whether the coordinator decided COMMIT or ROLLBACK.

If an XID appears in `XA RECOVER`, cross-reference it with the coordinator log and participant list. Never manually commit or roll back solely based on transaction age or XID name.

## 5. Cross-Shard Funds Transfer Business Example

Suppose the source account resides on shard A and the destination account resides on shard B. Business requirements:

- The source account exists and has sufficient balance.
- The destination account exists.
- Total money is conserved within the transfer scope.
- A given `transfer_id` is processed at most once.

Each shard's local schema should include a transaction identifier key to support idempotency:

```sql
CREATE TABLE account_transfers (
  transfer_id VARCHAR(64) NOT NULL,
  account_id BIGINT UNSIGNED NOT NULL,
  direction ENUM('DEBIT', 'CREDIT') NOT NULL,
  amount DECIMAL(18, 2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transfer_id, direction)
) ENGINE = InnoDB;
```

Each shard records the transfer's branch trail within the same XA transaction as the balance mutation. The unique key detects if the coordinator retries the same branch after a timeout; duplicate handling must integrate with the transaction manager and recovery rules.

High-level sequence:

1. Coordinator receives `transfer_id` and validates the request.
2. Determines source and destination shards from routing metadata.
3. Generates a unique global transaction XID, with `gtrid` representing the transfer and `bqual` for each shard.
4. Opens XA branches on both shards.
5. Conditionally debits on shard A, verifying exactly one row updated; inserts the debit record.
6. Credits on shard B, verifying exactly one row updated; inserts the credit record.
7. Ends and prepares both branches.
8. If all branches prepare successfully, durably logs the COMMIT decision and commits each branch.
9. If prepare fails, logs the ROLLBACK decision and rolls back participating branches.
10. Records completion state and returns the result to the caller.

If connectivity drops after step 8, the caller may not receive a response even though the transfer committed. The caller must re-submit the same `transfer_id` to look up the outcome rather than creating a new transfer with a different ID.

## 6. Coordinator Log and Recovery

The coordinator log is the core of recovery. It must record at least:

- Global transaction ID/`gtrid` and each branch XID.
- List of participating shards/resource managers.
- State of each branch: started, ended, prepared, commit sent, committed, or rolled back.
- Durably persisted global decision: COMMIT or ROLLBACK.
- Timestamps and metadata needed to retry/reconcile after a crash.

The log must be flushed durably before sending phase 2 commands. If the coordinator uses a dedicated database for its log, logging the decision must itself use appropriate durability settings. Never store decisions solely in memory, temporary log files, or caches that can be lost on restart.

### 6.1. Recovery Scenarios

| Failure | Possible State | Recovery Action |
|---|---|---|
| Coordinator fails before participants prepare | Branch may be ACTIVE or IDLE depending on last XA command; `XA RECOVER` does not list these states | Read coordinator log, reconcile XID and session/participant state; do not assume rollback solely from client disconnect |
| One participant fails to prepare | Some branches may already be prepared | Durably log ROLLBACK decision and roll back all prepared branches |
| Coordinator crashes after all prepare, before logging decision | Participants are in-doubt | Recover coordinator log; if log confirms no COMMIT decision was written, recovery can log ROLLBACK and resolve branches; if log cannot be verified, do not guess at participants |
| Coordinator logged COMMIT but did not send to all shards | Some branches prepared, some may have committed | Recovery must continue issuing COMMIT to all branches per durable decision |
| `XA COMMIT` response lost | Branch may have committed even though coordinator missed ACK | Reconcile durable decision, `XA RECOVER`, and business state; do not switch to rollback |
| Participant restarts while branch is prepared | Branch may reappear in `XA RECOVER` | Coordinator recovers decision and resolves the branch |
| Coordinator log lost | Final decision cannot be determined | Restore log from durable storage/backup; do not unilaterally decide commit/rollback |

### 6.2. Procedure for Handling In-Doubt Branches

1. Identify the exact MySQL shard and inspect `XA RECOVER`.
2. Collect the XID, timestamps, server status, error logs, and replication state.
3. Locate the corresponding global transaction in the coordinator log.
4. Determine whether a COMMIT or ROLLBACK decision was durably logged.
5. If a COMMIT decision exists, finish committing remaining prepared branches.
6. If a ROLLBACK decision exists, roll back remaining prepared branches.
7. If the decision cannot yet be recovered, leave the in-doubt state intact and escalate to the coordinator's recovery workflow; never release locks by arbitrarily rolling back.
8. Once resolved, verify data integrity and mark the branch resolved in the coordinator log.

A prepared transaction can hold locks and block other queries. However, manually rolling back a branch for which the coordinator already logged COMMIT breaks the atomic outcome. The global decision must remain the source of truth.

### 6.3. Lost Participant Commit Response

If the coordinator logged COMMIT and sent `XA COMMIT`, but the socket broke before receiving the reply, you cannot conclude the branch failed to commit. During recovery, verify:

- The durable coordinator decision.
- Whether the branch still appears in `XA RECOVER`.
- Which node is currently the participant's primary after any failover.
- Transaction markers or business records matching the XID/transfer ID.
- The state of the remaining participants.

If the branch no longer appears in `XA RECOVER` while the coordinator holds a COMMIT decision, the branch may already have committed; reconcile logs and data to confirm. `XA RECOVER` lists only branches still in the prepared state, not commit/rollback history.

## 7. XA via JDBC and Spring

In Java applications, XA is usually integrated through JDBC `XADataSource`/`XAResource` and a JTA transaction manager. The driver provides the resource adapter; the transaction manager coordinates prepare/commit/rollback across resources.

Points to remember:

- A plain JDBC `DataSource` with local `@Transactional` does not automatically create a distributed transaction.
- Spring `@Transactional` uses only the configured transaction manager. If it is a local `DataSourceTransactionManager`, transactions cover only that single resource.
- Coordinating multiple MySQL datasources requires configuring a JTA/XA transaction manager and XA-capable datasources for each shard.
- All participants must be enlisted in the same global transaction; opening a plain connection outside the transaction manager does not enlist it in XA.
- Verify XA support across your exact versions of MySQL Connector/J, connection pool, transaction manager, and MySQL Server.

Common transaction managers provide their own recovery mechanisms. Configure durable transaction log paths, unique node identifiers, and recovery connection details for every participant. Never delete transaction logs while in-doubt transactions remain.

### 7.1. Transaction Boundaries in Code

With JTA, a service uses transaction boundaries managed by the JTA manager. Conceptual example:

```java
@Transactional
public TransferResult transfer(TransferCommand command) {
    // accountRepository uses the source shard's XA datasource.
    // ledgerRepository uses the target shard's XA datasource.
    // Both resources must be enlisted in the same JTA transaction.
    debitSource(command);
    creditDestination(command);
    return TransferResult.accepted(command.transferId());
}
```

This code is distributed only when the transaction manager is genuinely JTA/XA and both datasources are configured for enlistment. With a local transaction manager, annotations do not turn two separate commits into 2PC.

Never manually execute `XA PREPARE` or `XA COMMIT` on a plain JDBC connection inside a method governed by another transaction manager. Mixing two mechanisms leaves the coordinator unaware of branch state.

### 7.2. Pools and XA Recovery

Connection pools must be compatible with XA resources and the transaction manager. When a global transaction completes, resources must be delisted and returned to the pool in a clean state. A prepared branch must not be treated like a normal idle connection; it can continue holding transaction state on the server even after the application loses its session.

The recovery manager must be able to reconnect to participants and enumerate prepared XIDs. Ensure the recovery account has proper privileges, endpoints always target the right shard, and credentials are managed securely.

## 8. Limits of XA and 2PC

XA coordinates atomic commits, yet it does not eliminate the costs and failure modes of distributed systems.

### 8.1. Latency and Throughput

Each transaction requires at least a prepare phase and a commit/rollback phase over the network to every participant. Latency depends on the slowest participant and the coordinator. When a request touches multiple shards, round trips, connections, and concurrently held resources increase.

Batching multiple operations within the same shard branch reduces coordinator calls, though larger transactions hold locks longer. Limit participant count and execution duration.

### 8.2. Locks and In-Doubt Transactions

Prepared branches can hold row locks and resources until the coordinator sends the final decision. If the coordinator or network suffers an extended outage, other transactions can block and lock queues grow.

Set timeouts at the request, coordinator, and database layers; however, timeouts do not resolve already-prepared branches automatically. Recovery must still follow the durable decision. Monitor prepared XID age, in-doubt branch counts, and lock waits.

### 8.3. Distributed Deadlocks

InnoDB detects deadlocks within a single MySQL instance. A lock-wait cycle spanning multiple shards cannot be seen as a global cycle by local deadlock detectors. For example, transaction A holds a row on shard 1 and waits on shard 2, while transaction B holds a row on shard 2 and waits on shard 1.

Reduce risk by:

- Accessing participants in a consistent shard order across all business flows.
- Keeping transactions short and updating minimal rows.
- Setting global deadlines and bounded wait timeouts.
- Detecting stalled transactions and aborting per coordinator decision.
- Retrying the entire business operation using an idempotency key after verifying the prior outcome.

Local timeouts can break a waiting branch, yet do not replace distributed deadlock detection and recovery.

### 8.4. Availability Under Network Partitions

If the coordinator cannot reach a participant, it cannot unilaterally assume that participant committed or rolled back. Once branches are prepared, 2PC may have to block to preserve an atomic decision. Thus, XA trades away availability to complete transactions during certain network partitions in favor of maintaining consistent decisions.

No timeout configuration turns 2PC into a protocol that always makes progress when the coordinator or participants are unreachable. Accept this trade-off at the business and SLO level.

### 8.5. XA Does Not Automatically Provide Global Constraints or Global Isolation

XA coordinates commit outcomes across resource managers. It does not provide:

- Physical foreign keys across two MySQL servers.
- Cluster-wide unique indexes if data is distributed arbitrarily.
- A global lock manager covering every row across every shard.
- Default global serializable isolation for cross-shard transactions.
- Atomicity with non-XA systems such as HTTP services, email, or unenlisted message brokers.

If a business flow needs global invariants, explicitly design where validation occurs, locking/identification mechanisms, and recovery workflows. XA does not replace distributed data design.

## 9. XA vs. Sagas and Transactional Outbox

Not every cross-shard operation requires atomic commit. Choose the mechanism based on the business consequences if one step completes while another fails.

| Criterion | XA / 2PC | Saga | Transactional outbox |
|---|---|---|---|
| Goal | Atomic outcome across XA participants | Sequence of local transactions and compensating actions | Write business data and event in the same local transaction |
| Rollback | Coordinator decides commit/rollback of branches | Uses compensating actions; does not erase committed history | Does not roll back consumers; guarantees event emission after commit |
| Consistency | Atomic commit when participants and recovery succeed | Eventual consistency across the workflow | Events published durably; consumers converge eventually |
| Resources | Holds prepared state/locks across phases | Does not hold DB transactions across the entire workflow | Each step has a short local transaction |
| Best fit when | All-or-nothing semantics needed and resources support XA | Long-running workflows with business compensation steps | Reliable event publication needed after database commit |
| Limitations | Blocking, latency, coordinator and recovery complexity | Compensation cannot always reverse external effects | Must handle duplicates, retries, and event ordering |

### 9.1. Sagas for Multi-Step State Transitions

For example, order placement may involve:

1. Creating the order on the order shard.
2. Reserving inventory on the warehouse shard.
3. Requesting payment from the payment service.
4. Confirming the order.

If payment fails after reserving inventory, the saga runs a compensating action to release inventory and transition the order to a failed state. A compensating action is a new business transaction, not a physical rollback of the previous transaction.

Sagas work well when the system can model intermediate states such as `PENDING`, `RESERVED`, and `PAYMENT_FAILED` and accept eventual consistency. Each step must be idempotent and paired with retries, dead-letter handling, and reconciliation.

### 9.2. Outbox for Event Emission

When a service updates MySQL and then must publish a message, write the business row and the outbox row in the same local transaction:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

INSERT INTO outbox_events (event_id, aggregate_id, event_type, payload)
VALUES ('evt-9001', '9001', 'OrderConfirmed', '{"orderId":9001}');

COMMIT;
```

A worker reads the outbox, publishes the event, and marks it sent. Workers can redeliver if an ACK is lost, so consumers must deduplicate by `event_id`. An outbox does not create an atomic transaction between MySQL and the broker, yet it closes the gap between committing to the database and persisting the intent to publish.

## 10. Durability, Replication, and Failover

2PC can recover accurately only if decisions and prepared states survive crashes. Configure MySQL and transaction manager durability to match data requirements.

Evaluate at minimum:

- InnoDB redo log flush policy, especially `innodb_flush_log_at_trx_commit`.
- Binary log durability, especially `sync_binlog` when binary logs participate in replication/recovery.
- Whether the coordinator log is flushed durably before phase 2.
- Backup/restore of the coordinator log and transaction manager configuration.
- Each shard's replication topology, GTIDs, failover policy, and RPO.
- Ability to locate prepared branches after restarts or primary promotion.

With asynchronous replication, a transaction may commit on the primary without having replicated before primary failover. If the new primary lacks that transaction, global state may no longer match coordinator expectations. Never assume XA turns cross-shard replication synchronous or eliminates RPO.

Rehearse failover while XA transactions are in active, prepared, and commit-sent states. After failover, reconcile coordinator decisions, `XA RECOVER`, GTIDs, and business records on the new primary before permitting retries.

## 11. Observability and Operations

The coordinator and every participant need logs linked by a global transaction ID. Avoid per-shard logs lacking a shared correlation ID.

Metrics to monitor:

- Count of global transactions active, preparing, prepared, committing, rolling back, and in-doubt.
- Count of prepared XA branches and age of the oldest branch on each shard.
- p95/p99 latency of prepare and commit phases.
- Prepare failure rate, commit/rollback timeouts, and recovery retries.
- Unresolved transactions in the coordinator and recovery lag.
- Lock waits, deadlocks, transaction age, connection pool usage, and replica lag per shard.
- Saga compensation rate, outbox backlog, and consumer duplicate rate if using eventual consistency.

### 11.1. Inspecting Prepared Transactions

On each shard:

```sql
XA RECOVER;

SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id,
  trx_rows_locked,
  trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Prepared XA branches do not necessarily appear as ordinary active session transactions in every view; use `XA RECOVER` to enumerate prepared branches. Combine the process list, InnoDB transaction views, and coordinator logs when investigating.

### 11.2. Operational Rules

- Never delete coordinator logs while unresolved global transactions exist.
- Never start a new coordinator with the same identity while an old transaction manager can still run recovery, unless HA fencing is guaranteed.
- Never allow two coordinators to make decisions for the same global transaction.
- Never manually commit or roll back an XID solely to release locks.
- Never reuse old XIDs for new requests.
- Persist participant info, shard identities, and routing versions so recovery never sends decisions to the wrong server.
- Periodically rehearse coordinator crashes, network partitions, participant restarts, and primary failovers.

## 12. Practice Exercise

A banking application shards account data by `account_id`. Source account `101` lives on shard A; destination account `202` lives on shard B. Each shard runs MySQL 8.0 with InnoDB. The application must transfer 100 currency units while guaranteeing no money is lost or created twice.

Design a solution and answer:

1. Why can a regular InnoDB transaction on shard A not roll back a transaction already committed on shard B?
2. How could shard keys or aggregate design be adjusted to reduce how often transfers require XA?
3. Describe the coordinator, participants, `gtrid`, and `bqual` in the global transaction.
4. Write the sequence of `XA START`, DML, `XA END`, `XA PREPARE`, and `XA COMMIT` for both shards.
5. If debiting the source balance affects 0 rows, how must the coordinator proceed?
6. Why must the COMMIT decision be durably logged before sending `XA COMMIT` to participants?
7. If shard A committed but its response was lost, how does recovery determine its state?
8. If the coordinator crashes after both shards prepare but before a durable decision is logged, why can participants not decide on their own?
9. How do you use `XA RECOVER` to find in-doubt branches and correlate them with the coordinator log?
10. Why can `XA RECOVER` not tell you whether a branch committed or rolled back in the past?
11. What lock, latency, and availability trade-offs arise during a network partition?
12. If an order workflow allows compensation, design a saga and transactional outbox instead of XA.
13. After a primary failover on a shard using asynchronous replication, how should you verify GTIDs, prepared branches, and RPO?
14. Write a fault-injection matrix for failures before prepare, during prepare, after durable commit decision, and while sending commits.

A strong solution has unique XIDs, a durable coordinator log, evidence-based recovery without guessing, API idempotency keys, and balance-verification criteria after every fault injection. Run experiments on two isolated MySQL test instances—never test against real accounts or production data.

## 13. Common Misconceptions

- **Calling `commit()` on each shard is a distributed transaction:** sequential commits can leave one shard committed and the other uncommitted.
- **Assuming `@Transactional` orchestrates XA by default:** the annotation uses whatever transaction manager is configured; local transaction managers do not coordinate multiple datasources.
- **Assuming XA cannot block:** prepared branches can wait on the coordinator in an in-doubt state.
- **Rolling back branches when the coordinator disconnects:** can contradict a durably persisted COMMIT decision.
- **Using `XA RECOVER` as a transaction history:** the command lists only currently prepared branches.
- **Assuming XA creates cross-shard foreign keys:** physical constraints apply only within a single MySQL instance.
- **Assuming XA provides global serializable isolation:** each participant still enforces local isolation and constraints.
- **Retrying with a new global transaction ID after a timeout:** can execute the same business operation twice; a stable idempotency key is required.
- **Using XA for long multi-service workflows:** prolonged locks and prepared states cause contention; sagas usually fit better when compensation is possible.
- **Assuming XA eliminates replication failover risk:** each shard still has its own RPO and durability profile.

## Conclusion

Cross-shard transactions require a coordination mechanism because local commits on individual MySQL servers do not produce global atomicity. XA/2PC uses a coordinator, participants, and durable decisions to prepare and then commit or roll back branches, yet it can hold locks in an in-doubt state during coordinator or network failures. Minimize cross-shard writes with suitable shard keys; reserve XA for operations that truly require atomic outcomes and have recovery infrastructure; use sagas/outboxes for workflows that tolerate intermediate states and compensation. Whichever approach you choose, enforce global transaction IDs, idempotency, observability, failover drills, and recovery procedures grounded in durable evidence.
