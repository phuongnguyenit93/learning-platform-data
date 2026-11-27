# Designing Applications for Connection Loss, Bounded Retries, and Duplicate Transaction Prevention in Oracle

## 1. Why Must Applications Be Designed for Connection Failures?

An application using Oracle Database cannot assume a connection remains intact from session open to result return. Networks can flap, listeners or instances can restart, RAC nodes can fail, connection pools can hold dead sockets, or clients can time out while the database is still processing.

Connection failures also create a subtler hazard than ordinary SQL errors: **the client may not know whether the transaction committed**. For instance, the database may have committed an order while the `COMMIT` response was lost on the network. If the application blindly re-submits the entire operation without deduplication, the order or payment could be created twice.

A fault-tolerant application must solve three problems simultaneously:

1. **Connection recovery:** detect broken connections, purge them from the pool, and open fresh connections when available.
2. **Bounded retries:** retry only potentially transient failures, cap retry attempts and total wait time, and apply backoff with jitter.
3. **Duplicate transaction prevention:** use idempotency keys, unique constraints, and transaction boundaries so a resent request produces zero duplicate business side effects.

Within the **Database Engine Relational Oracle** module, this lesson belongs to the **High Availability** chapter. It spans error classification, timeout and retry design, handling ambiguous `COMMIT` outcomes, Oracle Transaction Guard, Application Continuity, connection pooling, and transactional outbox/inbox patterns.

## 2. Error Categories Applications Must Distinguish

Not every error can be solved by retrying. Before designing a retry policy, classify errors by root cause and transaction state.

### 2.1. Transient Errors

Errors that may clear after a brief interval:
- A node or instance is transitioning state.
- A TCP connection is reset.
- A listener temporarily stops accepting connections.
- Resource Manager or the system is busy.
- A transaction hits a deadlock or serialization conflict.
- A dependent service is recovering.

Errors of this type can be retried if the operation is safe, time remains within the deadline, and transaction state is resolved.

### 2.2. Configuration or Authentication Errors (Permanent/Configuration)

Repeated retries will not fix:
- Incorrect username/password.
- Wrong service name or connect descriptor.
- Locked or expired account.
- Insufficient user privileges.
- Invalid table/column name.
- Bad SQL syntax or bind type mismatch.
- Business constraint violations.
- Security policy denials.

Return the error to the caller or escalate to operations to fix configuration.

### 2.3. Business Errors

Examples:
- Insufficient balance.
- Order already closed.
- Invalid customer identifier.
- Request already processed earlier.
- Input violating business rules.

These are not infrastructure failures. Never automatically retry merely because a SQL query returned zero rows or the application raised a business error code.

### 2.4. Ambiguous-Outcome Errors

This is the most dangerous category. The client sent an operation but never received final confirmation.

Examples:
- Connection drops while a statement executes.
- Client times out right after sending `COMMIT`.
- Instance fails over right as the transaction finishes.
- Application crashes after database commit but before returning a response.

In these cases, the client cannot conclude the transaction failed based solely on an exception. Determine the outcome via Transaction Guard (if supported) or look up the idempotency record over a fresh connection.

## 3. Connection Failure Does Not Mean Transaction Rollback

A typical request traverses these steps:

```text
Client
  |
  | 1. Send SQL/DML
  v
Oracle session
  |
  | 2. Execute transaction
  v
Database
  |
  | 3. COMMIT
  v
Oracle sends response
  |
  X 4. Network drops before client receives ACK
```

By the time the client receives an error, the database may already have committed successfully. The client knows only that the response never arrived.

Therefore, distinguish:

- **Certainly never sent:** safe to retry after restoring connectivity.
- **Sent, outcome unknown:** must resolve outcome or rely on idempotency keys.
- **Commit confirmation received:** never resubmit the transaction.
- **Business/constraint error received:** handle that specific error; do not retry like a network fault.

In particular, an exception thrown by `commit()` does not prove the transaction rolled back. This is a common root cause of duplicate transactions.

## 4. Building a Bounded Retry Policy

Retries help applications ride out transient glitches, but unbounded retries can turn a minor hiccup into a system-wide outage.

### 4.1. Capping Retry Attempts

Every request should enforce:
- Maximum attempt count.
- Overall deadline.
- Dedicated pool acquisition timeout.
- Connect timeout.
- Statement/query timeout.
- Delay between attempts.

Example policy:
- Maximum 4 execution attempts.
- Total deadline 8 seconds.
- Connect timeout 1 second per attempt.
- Statement timeout per business SLA.
- Increasing backoff capped at 2 seconds.

These values are illustrative only. Base them on SLAs and real service recovery times.

### 4.2. Exponential Backoff

Exponential backoff increases wait time after each failure:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

Example with 100 ms base delay and 2-second max delay:

| Retry Attempt | Max Delay Before Jitter |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1,600 ms |

Never use the same fixed delay across all clients. If thousands of clients all retry after 500 ms, they create synchronized load spikes.

### 4.3. Jitter

Jitter injects randomness into backoff intervals. A common strategy is full jitter:

\[
actualDelay_n = random(0,\ delay_n)
\]

This prevents clients from waking simultaneously and hammering the service in lockstep. Jitter is critical right as a database or service recovers from an outage.

### 4.4. Enforcing Overall Deadlines

Do not cap only attempt counts. Every retry consumes time from the request's overall deadline.

Example:
- Request deadline: 8 seconds.
- First attempt consumed 3 seconds.
- Planned backoff: 2 seconds.
- Next attempt needs up to 4 seconds.

The projected total exceeds the deadline. Stop retrying and return a clean error instead of continuing an already-expired request.

### 4.5. Never Hold Transactions or Connections During Backoff

When a transaction encounters a retryable failure:
1. Roll back the current transaction.
2. Close or discard the broken connection.
3. Sleep for the backoff interval outside any transaction.
4. Borrow a fresh connection.
5. Restart the entire transaction using the same idempotency key.

Never `sleep` while holding row locks, an open transaction, or a connection pool slot. Doing so ties up resources without doing useful work and worsens contention.

## 5. Classifying Oracle Errors Before Retrying

Applications should classify errors by Oracle error code, connection state, and point of failure. Never apply one blanket rule to all exceptions.

| Error / Example | Common Interpretation | Remediation |
|---|---|---|
| `ORA-03113` | End-of-file on communication channel | Discard connection; resolve transaction outcome before resubmitting |
| `ORA-03114` | Not connected to Oracle | Open a fresh connection; resolve outcome if DML/`COMMIT` was sent |
| `ORA-03135` | Connection lost / timeout | Check network, firewall, server; never blindly retry writes |
| `ORA-12541` | No listener at endpoint | Potentially transient; check listener/service and retry within deadline |
| `ORA-12514` | Listener does not know requested service | Usually requires fixing service registration/connect descriptor; retrying won't fix bad config |
| `ORA-12170` | Connect timeout | Network or endpoint issue; bounded retry after classification |
| `ORA-01017` | Invalid credentials | Authentication error; do not retry same credentials |
| `ORA-28000` | Account locked | Stop and resolve account/policy issue |
| `ORA-00060` | Deadlock detected | Roll back entire business transaction, then consider retrying |
| `ORA-08177` | Cannot serialize access | Roll back and retry entire transaction under serializable isolation |
| `ORA-00054` | Resource busy with `NOWAIT` | Bounded retry possible if business logic allows |
| `ORA-00001` | Unique constraint violation | Usually data error or duplicate; check idempotency record, never blindly retry |
| `ORA-01400` | Cannot insert NULL into `NOT NULL` column | Data/logic error; do not retry |
| `ORA-00942` | Table or view does not exist or missing privilege | Fix schema/privileges; do not retry as a network error |
| `ORA-01555` | Snapshot too old | Investigate undo/query duration; naive retry often fails again |
| `ORA-01013` | User requested cancel | Respect cancellation; do not auto-retry |
| `ORA-04021` | Timeout waiting to lock object | Potentially transient, though check for DDL/deployment holding locks |

Error codes are only one signal. Inspect the operation, transaction state, service state, driver exception, and application context. Some codes have multiple distinct causes.

### 5.1. Retry at the Transaction Level, Not Just the SQL Statement

Suppose a business transaction performs:
1. Read inventory.
2. Deduct inventory.
3. Create order.
4. Write history.

If step 4 fails, never retry step 4 alone if earlier steps modified state. For retryable errors, roll back the transaction and re-execute the entire business unit from the beginning.

### 5.2. Deadlocks and Serialization Conflicts

With `ORA-00060`, Oracle detects the deadlock and rolls back only the offending statement. Earlier statements in the same transaction remain active until the caller explicitly rolls back. Thus, applications must roll back the entire business transaction before retrying.

With `ORA-08177` under serializable isolation, the transaction must restart to acquire a fresh snapshot. Use bounded retries with the same idempotency key.

## 6. Idempotency: Repeating Requests Without Duplicate Effects

An operation is **idempotent** if executing it repeatedly with the same request identity produces no additional business effect beyond the first execution.

Examples:
- Setting an order status to `PAID` can be idempotent given proper state guards and locking.
- Adding 100 to a balance is not idempotent: sending twice adds 200.
- Creating a new payment is not idempotent if each call generates a separate payment.
- Setting configuration to an explicit target value is generally more idempotent than relative increments/decrements.

Never infer idempotency purely from HTTP methods or API names. Examine all database effects and external system calls.

### 6.1. Idempotency Keys

The client generates a unique key per business intent, such as a UUID:

```text
Idempotency-Key: 8e2f... (UUID)
```

When retrying the same request, the client must send the **exact same key**. Never generate a new key per attempt.

The server persists the key and processing result. If the key is already completed, the server returns the stored result instead of executing the business logic again.

### 6.2. Key Scoping

Keys should be scoped by:
- Tenant or customer.
- Operation/API.
- Client-supplied idempotency key.

For example, the logical key is `(tenant_id, operation_name, idempotency_key)`. This prevents a client reusing the same UUID across two tenants or two distinct operations from causing unintended collisions.

### 6.3. Payload Hash

Store a hash of the canonicalized payload. If a client reuses the same key with a different payload, the server must reject the request.

Examples:
- Key K + create order for 100 USD: processed initially.
- Key K + create order for 100 USD resent: returns stored result.
- Key K + create order for 500 USD: rejected as key conflict due to changed content.

Canonicalize the payload before hashing so insignificant JSON key ordering or whitespace differences do not cause false mismatches.

## 7. Idempotency/Deduplication Table in Oracle

Create a table to persist request state:

```sql
CREATE TABLE app.api_request_dedup (
    tenant_id        NUMBER        NOT NULL,
    operation_name   VARCHAR2(80) NOT NULL,
    idempotency_key  VARCHAR2(128) NOT NULL,
    request_hash     RAW(32)       NOT NULL,
    request_status   VARCHAR2(16) NOT NULL,
    response_code    NUMBER,
    response_body    CLOB,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at     TIMESTAMP WITH TIME ZONE,
    CONSTRAINT api_request_dedup_pk
        PRIMARY KEY (tenant_id, operation_name, idempotency_key),
    CONSTRAINT api_request_dedup_status_ck
        CHECK (request_status IN ('IN_PROGRESS', 'COMPLETED'))
);
```

Size the table for realistic volume and retention. `response_body` can be replaced by a result code or reference to stored response data when payloads are large.

### 7.1. Why Is a Unique Constraint Required?

Two requests carrying the same key can arrive concurrently. If you only run a `SELECT` check followed by an `INSERT`, both transactions may see no existing row and execute the business logic twice.

A primary key/unique constraint serves as the database's final synchronization point. Only one transaction can succeed in inserting the same key.

### 7.2. Never Check Solely in Application Code

Unsafe pattern:

```text
SELECT to check whether key exists
If not:
    execute business logic
    INSERT key
```

Two parallel requests can both pass the `SELECT` check. Let the unique constraint enforce uniqueness and handle duplicates intentionally.

## 8. Placing the Dedup Record and Business Changes in One Transaction

For short requests, the simplest and safest design inserts the idempotency record, executes business changes, saves the response, and commits everything inside **one atomic Oracle transaction**.

Flow:

```text
BEGIN TRANSACTION
    |
    v
INSERT idempotency key (unique)
    |
    +---- Duplicate key --> read stored hash/result
    |                         |
    |                         +--> return stored response or report key conflict
    |
    v
Execute business changes
    |
    v
Save response and mark COMPLETED
    |
    v
COMMIT
```

If the process dies before `COMMIT`, both the idempotency row and business changes roll back. If `COMMIT` succeeds but the response is lost, a retry with the same key finds the completed record.

### 8.1. General Processing Sequence

```sql
-- Illustrative pseudocode inside the request transaction.
INSERT INTO app.api_request_dedup (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    request_status
)
VALUES (
    :tenant_id,
    'CREATE_ORDER',
    :idempotency_key,
    :request_hash,
    'IN_PROGRESS'
);

-- Execute order changes inside the same transaction.
INSERT INTO app.orders (
    order_id,
    tenant_id,
    status,
    amount
)
VALUES (
    app.orders_seq.NEXTVAL,
    :tenant_id,
    'CREATED',
    :amount
);

-- Persist response to return if the request is resent.
UPDATE app.api_request_dedup
SET request_status = 'COMPLETED',
    response_code = 201,
    response_body = :response_json,
    completed_at = SYSTIMESTAMP
WHERE tenant_id = :tenant_id
  AND operation_name = 'CREATE_ORDER'
  AND idempotency_key = :idempotency_key;

COMMIT;
```

This is an illustrative sequence, not a complete production script. Applications must roll back on errors and return success only after commit is confirmed or the outcome is verified.

### 8.2. Handling Duplicate Keys

If inserting the idempotency record hits `ORA-00001`:
1. Confirm the error originated from the idempotency key constraint.
2. Fetch the record by exact tenant, operation, and key.
3. Compare `request_hash`.
4. If the hash differs, return a key/payload conflict error.
5. If the hash matches and status is `COMPLETED`, return the stored response.
6. If the record is in progress under a separate reservation model, apply a wait policy or return an in-progress status.

In an atomic single-transaction design, an uncommitted `IN_PROGRESS` row is invisible to other sessions. A concurrent request's unique check waits for the first transaction to finish; the second request then receives a duplicate error if the first committed, or proceeds to insert if the first rolled back.

### 8.3. Catch Duplicates Only on the Exact Unique Key

Do not treat every `ORA-00001` as a duplicate request. An order insert can also violate a unique constraint on an order code or business key. Identify the specific failing constraint or query the idempotency record with the exact key.

### 8.4. Do Not Commit the Idempotency Record Separately Without a State Machine

If you insert `IN_PROGRESS`, commit separately, and then run business logic, a crash can leave an orphaned in-progress row with no active transaction behind it.

A separate reservation model requires:
- Owner/worker ID.
- Lease expiration.
- Heartbeat or update timestamps.
- Post-lease takeover rules.
- Detection of cases where the transaction committed before the worker crashed.
- State recovery mechanisms.

Use that model only for long-running or asynchronous workflows; for short requests, a single atomic transaction is much easier to reason about.

## 9. Resolving Ambiguous COMMIT Outcomes

Scenario: the application sends `COMMIT`, the database may have written redo and committed internally, yet the TCP connection breaks before the client receives confirmation.

You cannot solve this by:
- Assuming the commit failed.
- Re-sending `INSERT`/`UPDATE` with a new key.
- Starting a new transaction without checking the prior request.

### 9.1. Outcome Resolution Process Using Idempotency Keys

When connectivity drops during commit:
1. Mark the old connection broken and purge it from the pool.
2. Do not re-execute business logic immediately.
3. Acquire a fresh connection.
4. Query the idempotency record using the exact same tenant, operation, and key.
5. If the record shows `COMPLETED`, return the stored response.
6. If no record exists, the prior transaction likely rolled back; retry with the same key within the deadline.
7. If state remains indeterminate, wait/backoff or report an indeterminate status so the caller can poll with the same key.

Do not issue a single instant query to conclude the old transaction rolled back if the server session might still be finishing. Design must allow time for the database to resolve the orphaned session after network loss.

### 9.2. The Idempotency Record as Business Source of Truth

When the dedup record and business changes commit together in one transaction:
- A `COMPLETED` record proves the companion business changes committed.
- Absence of the record after the prior transaction finishes proves it did not commit under this design.
- Dedup state and business data cannot diverge from crashing between two separate commits.

The critical requirement is that every database effect requiring deduplication resides inside that same transaction, with zero external side effects executed prior to commit.

### 9.3. Oracle Transaction Guard

Oracle Transaction Guard helps clients determine the outcome of the last transaction after supported outages/failovers in compatible environments and drivers. It uses a Logical Transaction ID (LTXID) to identify transactions and expose outcome metadata.

Benefits:
- Prevents re-executing already-committed transactions.
- Helps clients resolve lost commit responses.
- Supports building safe retries when paired with compatible client stacks and service settings.

Transaction Guard does not automatically make arbitrary SQL idempotent, nor does it replace application-level idempotency keys. Verify Oracle version, driver, service attributes, and API support before deploying. Oracle JDBC, OCI, and other client stacks vary in support across releases.

## 10. Oracle Application Continuity and Transparent Application Continuity

Oracle provides client/service features to recover in-flight requests when a database service or instance fails.

### 10.1. Application Continuity (AC)

Application Continuity records and replays an in-flight request when an eligible outage occurs, masking certain infrastructure faults from the application.

Replay does not re-run every request unconditionally. Oracle tracks transaction state and executed calls to avoid duplicating effects within supported semantics.

### 10.2. Transparent Application Continuity (TAC)

TAC extends replay in supported environments while minimizing required application code changes. Exact behavior depends on release, service configuration, and driver.

### 10.3. Transaction Guard Combined with Replay

Transaction Guard supplies transaction outcome metadata; Application Continuity/TAC uses this mechanism to decide whether replaying a request is safe under supported conditions.

Verify:
- Database release and Release Update.
- Service attributes.
- Driver/client version.
- APIs or operations unsupported for replay.
- Session state and request boundaries.
- Idempotency of external side effects outside the database.

### 10.4. Transparent Application Failover (TAF)

TAF is a session failover mechanism in certain Oracle RAC/Data Guard architectures and supported clients. It carries restrictions on operation types, session state, and transaction continuation. TAF is not equivalent to Application Continuity and must never be described as guaranteeing in-flight transactions automatically resume from the exact instruction.

### 10.5. Do Not Confuse HA Failover with Business Retries

RAC or Data Guard improves service availability, yet applications still need:
- Connection exception handling.
- Deadlines and retry policies.
- Idempotency keys.
- Commit outcome verification.
- Error monitoring and retry-storm prevention.

HA reduces outage duration; application logic protects business correctness.

## 11. Connection Pools and Handling Broken Connections

Applications rarely open a fresh TCP connection per request. Connection pools retain open sessions and reuse them.

### 11.1. Dead Connections Can Linger in Pools

A connection can break due to:
- Database instance restarts.
- RAC service relocation to another instance.
- Firewalls closing idle connections.
- NAT or load balancer timeouts.
- Network partitions.
- Killed database sessions.
- Server-side timeouts.

The pool may not notice immediately. The next time an application borrows that connection, it receives an exception.

### 11.2. Validating and Purging Broken Connections

Pool configuration should address:
- Validation on borrow or via background sweeps.
- Connection acquisition timeout.
- Idle timeout.
- Maximum connection lifetime.
- Appropriate TCP keepalives/heartbeats.
- Validating connections before reuse after failover.
- Evicting broken connections from the pool.
- Capping total connections to avoid overloading the database.

A simple Oracle validation query is:

```sql
SELECT 1 FROM dual;
```

You need not execute a validation query on every borrow if the driver/pool offers lighter validation mechanisms (such as FAN/FCF or driver ping). Choose based on latency, networking, and stale-connection detection needs.

### 11.3. Never Return Broken Connections to the Pool

After a severe network error:
- Mark the connection invalid.
- Close/discard it via the pool API.
- Never return a broken session to the idle list.
- Borrow a fresh connection when retrying is permitted.

Never simply call `rollback()` on a connection that lost network connectivity and assume its state is clean. Whenever state cannot be confirmed, discard the connection.

### 11.4. Resetting Session State

Because connection pools reuse sessions, reset:
- Application contexts.
- `CLIENT_IDENTIFIER`.
- Module/action.
- Current schema.
- NLS settings if modified by a request.
- Transaction isolation/read-only state.
- Temporary state or package state per design.

If using VPD, re-establish tenant context on every request. Never let one request inherit the previous request's security context.

## 12. Oracle RAC, FAN, FCF, and Service Configuration

In Oracle RAC, database services can shift across instances. Applications need visibility into which instances/services remain healthy.

### 12.1. Fast Application Notification (FAN)

FAN broadcasts service/instance/node events to configured clients or middleware. Notifications let pools quickly identify connections to evict or services changing placement.

### 12.2. Fast Connection Failover (FCF)

FCF pairs FAN notifications with compatible connection pools/client stacks to purge affected connections and open new connections to active instances/services.

FCF does not safely retry business transactions on its own. Applications must still handle exceptions and resolve transaction outcomes.

### 12.3. Oracle Universal Connection Pool (UCP)

UCP integrates Oracle capabilities such as FAN/FCF, connection labeling, validation, and version-specific HA features. With JDBC, verify UCP and Oracle JDBC driver compatibility against your database/service version.

### 12.4. Service-Level Workload Management

Define services tailored to workload classes:
- OLTP service.
- Batch service.
- Reporting service.
- Service configured for Application Continuity where supported.

Services carry failover/replay attributes and Resource Manager mappings. Configure attributes per SLA and test real failovers.

## 13. Timeouts at Every Layer

An application often stacks multiple timeouts. Without coordination, clients can abandon requests while the database keeps running, or pools can wait past API deadlines.

| Timeout | Controls |
|---|---|
| Pool acquisition timeout | Time spent waiting to borrow a connection |
| DNS/connect timeout | Time to resolve and establish a socket/session |
| Socket/read timeout | Time waiting for a network response |
| Oracle Net timeout | Wait bounds for specific network operations |
| Statement/query timeout | Maximum execution time per SQL statement |
| Transaction deadline | Total duration of the business transaction |
| API/request deadline | Total time the caller waits |
| Retry deadline | Total budget allocated to attempts and backoff |

### 13.1. Timeouts Must Align Hierarchically

Example:
- API deadline: 10 seconds.
- Pool acquisition: max 1 second.
- Connect timeout: 2 seconds.
- Statement timeout: 5 seconds.
- Retry/backoff consumes only remaining budget.

This is an example. Summed per-attempt timeouts and backoff must fit within the overall deadline. Never set socket timeouts shorter than legitimate query execution times, which cuts valid work mid-flight.

### 13.2. Timeouts Do Not Instantly Cancel Database Work

A client timeout may only stop waiting for a response. Depending on driver, network, and server state, the SQL statement may continue running or cancellation may arrive late.

Upon timeout:
- Check whether the driver dispatched a cancel.
- Clean up connection/session state.
- Roll back if still connected and uncommitted.
- If connectivity dropped near `COMMIT`, resolve the outcome.
- Reuse the same idempotency key if the caller resubmits.

## 14. Circuit Breakers, Bulkheads, and Retry Budgets

Retries are only one piece of resilience.

### 14.1. Circuit Breaker

A circuit breaker tracks failure rates and temporarily halts calls to an unhealthy dependency.

Common states:
- **Closed:** requests flow through normally.
- **Open:** blocks requests for a cooldown period to let the dependency recover.
- **Half-open:** permits limited probe requests to test recovery.

Circuit breakers stop thousands of requests from piling load onto an unavailable database or network.

### 14.2. Bulkhead

Bulkheads isolate resources per workload:
- Separate pools for OLTP vs. batch.
- Concurrency limits per API.
- Caps on concurrent heavy queries/reports.
- Isolated worker queues by job class.

If batch jobs fail and retry aggressively, bulkheads prevent them from exhausting user-facing transaction pools.

### 14.3. Retry Budgets

Set retry budgets per request or per service:
- Maximum attempt count.
- Percentage of requests allowed to retry.
- Total retry time.
- Cap on concurrent in-flight retries.

Never let an API gateway, service A, service B, and the database client each retry independently. Nested retries multiply call counts exponentially. Designate one layer to own business-level retries and keep other layers strictly bounded or non-retrying.

## 15. Retrying an Entire Transaction Safely

A transaction should be an atomic unit of work. Example funds transfer:
1. Validate accounts.
2. Debit source account.
3. Credit target account.
4. Write ledger entry.
5. Commit.

If step 3 deadlocks or drops connection before commit, retry from step 1 with the exact same request identity after rollback/outcome resolution—never re-run step 3 in isolation.

### 15.1. Transaction Retry Pseudocode

```text
handle(request, idempotencyKey):
    deadline = now + requestBudget

    for attempt in 1..maxAttempts:
        connection = borrowConnection(deadline)

        try:
            begin transaction
            result = executeBusinessTransaction(
                connection,
                request,
                idempotencyKey
            )
            commit
            return result

        catch retryableFailure:
            rollback if outcome is known and connection is usable
            discard connection if broken
            if commit outcome is unknown:
                resolve outcome using idempotency key or Transaction Guard
                if already committed:
                    return stored result

            if attempt limit reached or deadline expired:
                return retryable failure

            sleep with exponential backoff and jitter
        finally:
            return only healthy, clean connection to pool
```

This is architectural pseudocode, not complete Java code. Clearly separate exceptions occurring before `COMMIT`, during `COMMIT`, and after `COMMIT`.

### 15.2. Preserve the Same Idempotency Key Across All Attempts

Every retry of the same business intent must carry the exact same key. Generating a new key per attempt prevents the server from recognizing the retry and defeats deduplication.

### 15.3. Never Retry Explicit Business Failures

If the database returns a constraint violation or the application detects insufficient funds, do not retry. Return the corresponding business error immediately.

## 16. Long-Running Operations and Reservation/Lease Models

For operations lasting several minutes, keeping a database transaction open throughout causes lock, undo, and connection pressure. An asynchronous pattern is often needed:

1. Accept the request and create an idempotency record.
2. Commit `ACCEPTED` status along with a job/outbox record.
3. A worker picks up the job.
4. The worker acquires a lease to process it.
5. The worker updates status to `COMPLETED` or `FAILED`.
6. Job retries reuse the same request key and inspect current state.

The job table can include:
- Unique `REQUEST_ID`.
- `STATUS`.
- `LEASE_OWNER`.
- `LEASE_EXPIRES_AT`.
- `ATTEMPT_COUNT`.
- `NEXT_ATTEMPT_AT`.
- `LAST_ERROR_CODE`.
- `COMPLETED_AT`.

### 16.1. Leases and Takeover

A crashed worker can leave a job stuck in `PROCESSING`. Leases let another worker take over after expiration while preventing two workers from processing simultaneously.

Use a conditional atomic update:

```sql
UPDATE app.job_request
SET lease_owner = :worker_id,
    lease_expires_at = SYSTIMESTAMP + INTERVAL '60' SECOND,
    attempt_count = attempt_count + 1
WHERE request_id = :request_id
  AND status IN ('ACCEPTED', 'RETRY')
  AND (lease_expires_at IS NULL
       OR lease_expires_at < SYSTIMESTAMP);
```

Proceed only if `SQL%ROWCOUNT = 1`. Calibrate lease duration and heartbeats to processing times; too short a lease allows a second worker to hijack work while the first worker is still alive.

### 16.2. Fencing Tokens

In multi-worker systems, an expired lease does not guarantee the old worker has stopped. A monotonically increasing fencing token lets downstream resources reject stale operations from an old worker carrying a lower token—critical if a worker resumes after a network or GC pause.

## 17. External Side Effects and Transactional Outbox

A database transaction cannot automatically roll back an already-sent email, a completed payment API call, or a published broker message.

Example:
1. Insert order.
2. Call payment API.
3. Send email.
4. Commit Oracle.

If connectivity drops after step 2, the application may not know whether the payment succeeded. Retrying the whole flow risks charging twice.

### 17.1. Transactional Outbox

Inside one Oracle transaction:
- Write business changes.
- Insert an outbox event with a unique event ID.
- Commit.

A separate worker reads the outbox and dispatches messages to external systems. If the worker sends successfully but crashes before marking the event sent, it may resend. Thus, downstream consumers also require idempotency/deduplication.

### 17.2. Example Outbox Table

```sql
CREATE TABLE app.outbox_event (
    event_id       RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    aggregate_id   VARCHAR2(128) NOT NULL,
    event_type     VARCHAR2(80) NOT NULL,
    payload        CLOB NOT NULL,
    event_status   VARCHAR2(16) DEFAULT 'NEW' NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    published_at   TIMESTAMP WITH TIME ZONE
);
```

Inside the order-creation transaction, insert the outbox event alongside the order. When the order commits, the event is durably persisted. The publisher worker dispatches the event by event ID and updates its status.

### 17.3. Consumer Inbox/Deduplication

The consumer stores `event_id` in an inbox table guarded by a unique constraint. Upon receiving an event again:
- If `event_id` was already processed, skip business side effects and return ACK.
- Otherwise, record the inbox entry and apply business changes in the same consumer transaction.
- Send ACK only after committing.

This yields **effectively-once** semantics at the business level when transaction boundaries and deduplication are sound. Networks and message brokers can still deliver messages multiple times; never claim the transport layer guarantees end-to-end exactly-once delivery.

### 17.4. Payment Providers

If a payment provider supports idempotency keys, pass the exact same key on every retry of that payment. Persist the provider's transaction ID and outcome in the database. Never mint a new key when a response times out.

## 18. Preventing Duplicates with Business Constraints

Idempotency keys protect a single request identity. Additionally, enforce unique constraints for inherently unique business invariants.

Examples:
- Each order has a unique external reference per tenant.
- Each invoice number is unique per legal entity.
- Each payment provider transaction ID is recorded at most once.
- Each message/event ID is processed at most once by a consumer.

Example:

```sql
ALTER TABLE app.orders
ADD CONSTRAINT orders_tenant_external_ref_uq
UNIQUE (tenant_id, external_reference);
```

If two requests arrive with different idempotency keys yet the same external reference, the unique constraint still prevents creating duplicate orders.

Constraints must live in the database to prevent race conditions. Application-level checks aid early feedback, never replacing database uniqueness constraints.

## 19. Oracle Details That Affect Design

### 19.1. Transaction Atomicity

Oracle guarantees a transaction commits or rolls back as an atomic unit. Place the idempotency record and business data changes inside the same transaction whenever possible.

Never commit intermediate steps merely to avoid transient errors if doing so breaks business atomicity.

### 19.2. Sequences Can Have Gaps

`NEXTVAL` is not a request deduplication mechanism. Sequences can advance even when transactions roll back or due to cache loss/instance failures. Gaps in sequences are normal and do not indicate lost or duplicate transactions.

Use primary keys/unique constraints for uniqueness; use idempotency keys for request deduplication.

### 19.3. Isolation and Locking

Under `READ COMMITTED`, each statement sees a consistent snapshot as of statement start. When concurrent requests contend for the same resource, row locks, optimistic versioning, or conditional updates are required.

Example safe inventory update:

```sql
UPDATE app.inventory
SET available_qty = available_qty - :quantity
WHERE product_id = :product_id
  AND available_qty >= :quantity;
```

Check `SQL%ROWCOUNT`:
- 1 row: update succeeded.
- 0 rows: product missing or insufficient inventory.

This combines validation and mutation in a single statement, eliminating races between `SELECT` and `UPDATE`. If you must distinguish the two failure reasons, query further inside the transaction per business logic.

### 19.4. Conditional Updates and Optimistic Locking

For versioned records:

```sql
UPDATE app.account
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
```

If `SQL%ROWCOUNT = 0`, another transaction modified the row or the record does not exist. Re-read and re-evaluate business rules rather than blindly retrying with stale values.

### 19.5. DDL and Implicit Commits

Oracle DDL issues implicit commits. Never place DDL inside business transactions expecting it to roll back with DML. Separate object creation/drops from business transactions and manage them separately.

## 20. Observability for Retries and Duplicate Prevention

Logging only `"database error"` leaves operators blind to retry storms.

Each request should log structured metadata:
- Request/correlation ID.
- Idempotency key or safe hash (avoid logging raw keys if sensitive).
- Tenant/operation.
- Attempt number.
- Oracle error code.
- Connection pool name.
- Service/instance if available.
- Start/end timestamps.
- Retry delay.
- Transaction phase: acquire, execute, commit, outcome resolution.
- Dedup outcome: new, duplicate completed, key conflict, pending.
- Final status.

Never log passwords, tokens, full payment payloads, or unnecessary personal data.

### 20.1. Metrics to Monitor

| Metric | Meaning |
|---|---|
| Retry attempts/request | How many attempts requests require |
| Retry success rate | How many retries recover successfully |
| Retry exhaustion | Requests exhausting their retry budget |
| Connection validation failures | Stale connections detected and evicted |
| Pool wait time | Time spent waiting to borrow connections |
| Commit outcome unknown | Incidents where client lost response around `COMMIT` |
| Duplicate key hits | Requests recognized as duplicates |
| Idempotency key conflicts | Same key submitted with differing payload |
| Circuit breaker open time | Duration dependencies stay blocked |
| Transaction duration | Time transactions remain open |
| Outbox lag | Delay of unpublished outbox events |

A rising retry success rate is not necessarily healthy if total request rates and database load surge simultaneously. Monitor final failure rates, p95/p99 latency, and database resource usage together.

### 20.2. Alerts

Alert when:
- Retry rate spikes sharply.
- Multiple connections fail on the same service.
- Pool wait time breaches thresholds.
- Ambiguous commit outcomes climb.
- Idempotency conflicts spike abnormally.
- Outbox backlog grows continuously.
- Circuit breakers remain open too long.
- `ORA-00060` or `ORA-08177` rates climb.

## 21. Fault Injection Testing

Testing only the happy path is insufficient. Actively inject faults in staging/lab environments.

### 21.1. Injection Points to Test

1. Connection lost before sending SQL.
2. Connection lost mid-SQL execution.
3. Connection lost after DML but before `COMMIT`.
4. Connection lost immediately after sending `COMMIT`.
5. Database instance restart mid-request.
6. Connection pool handing out a stale connection.
7. Two requests with the same idempotency key arriving concurrently.
8. Two requests with the same key but different payloads.
9. Outbox worker crashing after publishing but before marking complete.
10. Consumer receiving the same event multiple times.

### 21.2. Outcomes to Prove

- Zero duplicate orders/payments created.
- Zero double debits/credits.
- Repeated requests with the same key return identical business outcomes.
- Same key with different payload is rejected.
- Failed transactions leave zero unintended partial changes.
- Broken connections are purged from the pool.
- Retries stop once the deadline expires.
- Zero locks held during backoff intervals.
- Outbox/inbox recover cleanly after worker crashes.
- Service does not suffer retry storms.

### 21.3. Concurrency Testing

Have multiple clients submit the exact same idempotency key simultaneously. Expected behavior:
- Exactly one transaction executes the business change.
- Remaining requests receive the stored result or in-progress status per design.
- Business row count increases by exactly one.
- The unique constraint protects integrity under concurrent load.

Do not test only sequentially, as race conditions often surface exclusively under concurrency.

## 22. Complete Example Architecture for an Order Creation API

Assume `POST /orders` receives tenant, item list, and shipping address.

### Step 1. Client Creates Request Identity

The client generates a UUID idempotency key for the order intent and retains it until receiving a final result. On timeout, the client resends with the same key.

### Step 2. API Authenticates

The API authenticates the user/tenant, validates inputs, canonicalizes the payload, and computes the payload hash. Never trust a tenant ID merely because it appears in the request body.

### Step 3. Start Transaction

The API borrows a healthy connection from the pool and begins a transaction.

### Step 4. Claim Idempotency Key

Insert `(tenant_id, operation, idempotency_key, request_hash)` into the dedup table. The unique constraint guarantees only one request wins.

### Step 5. Execute Business Logic

Validate and deduct inventory via conditional updates, insert the order and order lines, and write required business audit rows.

### Step 6. Write Outbox

In the same transaction, insert an `ORDER_CREATED` event into the outbox so a worker dispatches it post-commit.

### Step 7. Save Response and Commit

Update the dedup record to `COMPLETED`, save the response/reference, and commit.

### Step 8. Return Response

Return success only once commit is confirmed. If connectivity drops around `COMMIT`, open a fresh connection and look up the key or use Transaction Guard to resolve the outcome.

### Step 9. Retry

If the error is classified transient and the outcome is safely resolved, retry the full transaction with the same key, backoff, and jitter. Stop if the deadline expires.

### Step 10. Publish Event

The worker reads the outbox and publishes the event ID. The consumer writes its inbox/dedup row alongside its business change and ACKs after committing.

## 23. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Retrying every exception | Repeats config/business errors, wastes load | Classify errors |
| Infinite retries | Holds requests and resources indefinitely | Cap attempts and deadlines |
| Fixed delay across all clients | Synchronized retry storms | Exponential backoff + jitter |
| Retrying only the last SQL statement | Leaves transactions half-executed | Roll back and retry whole business transaction |
| Generating new idempotency key per attempt | Server treats each retry as a brand-new request | Reuse the same key |
| `SELECT` then `INSERT` key | Race condition between parallel requests | Enforce uniqueness via unique constraint |
| Committing dedup before business change | Leaves orphan rows or inconsistent state | Same transaction or explicit lease state machine |
| Treating `COMMIT` exception as rollback | Causes duplicate transactions | Resolve outcome via key/Transaction Guard |
| Using sequences for deduplication | Sequences do not track request intent | Use unique idempotency/business keys |
| Holding connections during backoff | Exhausts pools and ties up locks | Roll back, release, then sleep |
| Retrying at every tier | Call counts multiply exponentially | Designate one primary retry tier |
| Sending email/payments inside transaction then retrying | External side effects repeat | Transactional outbox and external idempotency |
| Checking uniqueness only in app code | Race conditions persist | Unique constraints / conditional DML |
| Returning broken connections to pool | Subsequent requests fail too | Discard broken connections |
| Omitting overall timeout | Requests hang indefinitely | Enforce end-to-end deadlines |

## 24. Implementation Checklist

### Connectivity
- Pool configured with proper validation/eviction.
- Broken connections purged from pool.
- Connect, pool, socket, and statement timeouts configured.
- Session state reset between requests.
- RAC/service failover tested if used.

### Retries
- Explicit allowlist/classification of retryable vs. non-retryable errors.
- Retries bounded by max attempts and deadline.
- Exponential backoff and jitter implemented.
- Retries executed at transaction/business-operation granularity.
- Zero connections/locks held during backoff.
- Circuit breakers, bulkheads, or retry budgets applied where appropriate.

### Deduplication
- Clients generate and preserve idempotency keys across retries.
- Keys scoped by tenant/operation.
- Payload hashes detect conflicting key reuse.
- Unique constraints enforced in the database.
- Dedup records and business changes committed atomically where suitable.
- Responses persisted for replay.
- Ambiguous commit outcomes explicitly resolved.
- Retention covers full retry windows.

### External Integrations
- Side effects emitted via outbox or guarded by external idempotency.
- Consumers maintain inbox/dedup tables.
- Event IDs remain stable.
- ACKs sent only after commit.
- Retry/dead-letter queues and backlog monitoring configured.

### Operations
- Metrics for retries, duplicates, commit ambiguity, and pool health.
- Alerts and runbooks established.
- Fault-injection and concurrency tests executed.
- Retry abort thresholds and escalation paths defined.
- No secrets or sensitive payloads logged.

## 25. Self-Check Questions

**Question 1.** Why does connection loss not prove a transaction rolled back?

**Answer:** The database may have committed while the `COMMIT` response was lost on the network, leaving the client unaware of the outcome.

**Question 2.** What does a bounded retry policy require?

**Answer:** Maximum attempts, overall deadline, per-layer timeouts, backoff, jitter, and error classification.

**Question 3.** What is the purpose of exponential backoff?

**Answer:** Progressively increases wait intervals between retries to relieve pressure on a recovering dependency.

**Question 4.** What problem does jitter solve?

**Answer:** Spreads out client retry timestamps to avoid synchronized retry bursts.

**Question 5.** When must an entire transaction be retried?

**Answer:** Whenever a retryable error prevents the business transaction from continuing safely; roll back partial work and restart the whole business unit.

**Question 6.** What is an idempotency key?

**Answer:** A stable identifier for one business intent, enabling the server to recognize resent requests as duplicates.

**Question 7.** Why is a unique constraint needed for idempotency keys?

**Answer:** It resolves race conditions at the database level when concurrent requests arrive with the same key.

**Question 8.** Why store a request payload hash?

**Answer:** To detect clients reusing the same key with a modified payload.

**Question 9.** Why should the dedup record and business changes share the same transaction?

**Answer:** So they commit or roll back atomically, preventing states marked complete without business changes or vice versa.

**Question 10.** How should a `COMMIT` timeout be handled?

**Answer:** Never assume failure; open a fresh connection to check the idempotency record or query Transaction Guard if supported.

**Question 11.** What does Transaction Guard provide?

**Answer:** Enables clients to determine the outcome of the last transaction across supported outage/failover scenarios.

**Question 12.** What does Application Continuity do?

**Answer:** Replays eligible in-flight requests after outages per Oracle/client-stack configuration and constraints.

**Question 13.** How do FAN/FCF help in RAC?

**Answer:** Broadcast service/instance events and help pools evict affected connections and establish new ones to healthy instances.

**Question 14.** Why not retry every `ORA-` error?

**Answer:** Many codes reflect authentication, configuration, data, or business errors that will never clear by waiting.

**Question 15.** Why must connections not be held during backoff?

**Answer:** Open connections and transactions hold locks/resources, starving the pool while doing no useful work.

**Question 16.** What problem does a transactional outbox solve?

**Answer:** Writes business changes and events atomically in one transaction so a publisher worker can retry without losing events.

**Question 17.** Why do consumers still need an inbox/dedup table?

**Answer:** Publishers may resend events if an acknowledgment is lost, so consumers must guard against applying the same event twice.

**Question 18.** Can retries alone guarantee end-to-end exactly-once semantics?

**Answer:** No. Stability requires durable identifiers, persistent state, transaction boundaries, and deduplication at every side-effect boundary.

## 26. Conclusion

Fault-tolerant Oracle applications treat connection loss as a normal operational scenario to design for. Broken connections must be detected and purged from pools; retries apply strictly to transient errors with capped attempts, overall deadlines, exponential backoff, and jitter. When retrying transactions, roll back and re-execute the entire business operation using the exact same request identity, never holding connections or locks during backoff.

The hardest challenge is an ambiguous `COMMIT` outcome. Clients can lose responses even after the database commits. Therefore, never assume an exception implies rollback. Idempotency keys, payload hashes, unique constraints, and dedup records committed atomically with business data allow retries to return the prior result instead of creating duplicate transactions. Oracle Transaction Guard adds transaction outcome resolution in supported environments; Application Continuity/TAC, FAN/FCF, and RAC services improve connection recovery without replacing application deduplication logic.

For external side effects outside the database, combine transactional outboxes with consumer inbox/dedup tables or downstream idempotency keys. Measure retry rates, commit ambiguity, pool health, duplicate hits, and outbox lag; test failures before, during, and after `COMMIT` alongside concurrent duplicate requests. Only consider the system production-ready once proven that outages neither lose committed transactions, produce duplicate effects, nor trigger self-inflicted retry storms.
