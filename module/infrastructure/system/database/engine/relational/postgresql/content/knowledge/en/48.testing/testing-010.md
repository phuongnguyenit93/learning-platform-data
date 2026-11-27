# Testing Connection Loss, Retries, and Safe Idempotency

In applications using PostgreSQL, connection loss can occur when a server restarts, a primary fails over, the network glitches, a connection pool holds a broken connection, or a query gets canceled. Applications often need to retry to keep serving users. However, retrying a write operation can create duplicate data if the previous attempt was already confirmed by PostgreSQL while the response failed to reach the application.

Therefore, resilience testing must simultaneously answer three questions:

1. Does the application properly detect and evict broken connections?
2. Does the application make the right decision when it is unknown whether the previous transaction committed?
3. When the exact same request is sent multiple times, does business data change only once?

These three questions are related yet not synonymous. Connections can recover while a business operation still executes twice. Conversely, an operation may be protected by idempotency while the application still exhausts its connection pool if broken connections are not evicted.

## 1. Understanding When Connection Loss Can Happen

PostgreSQL manages each connection as a session. Transactions execute inside that session. When a session is lost, an uncommitted transaction cannot be resumed on a new connection. The application must open a different connection and decide whether to re-execute the operation.

The hardest point is at `COMMIT`. Suppose the application sends `COMMIT`, PostgreSQL processes it successfully and records the transaction, and the network drops before the `COMMIT` acknowledgment reaches the application. On the application side, the commit call throws an error or times out. The application cannot conclude the transaction rolled back merely from the connection error. The transaction may have committed successfully.

Situations to distinguish:

| Moment of failure | What the application can know | Appropriate handling |
|---|---|---|
| Before opening a connection | No transaction was sent on that connection | Retry connecting within the retry budget |
| After connecting, before sending work | No business changes occurred from that operation | Open a new connection and retry |
| While a statement is running | The statement may be incomplete; the session may have closed | Discard the broken connection; re-run the entire business operation via idempotency |
| After a write statement, before `COMMIT` | The transaction is uncommitted if the server never received `COMMIT`; a new connection cannot resume the old transaction | Start a new transaction and process with the same idempotency key |
| While sending `COMMIT` or waiting for `COMMIT` response | Commit outcome may be indeterminate on the client | Look up or resend the same idempotent request on a new connection |
| After receiving `COMMIT` confirmation | The transaction is confirmed by PostgreSQL under its current durability configuration | Do not re-run the operation; return the saved result |

Never label every connection-loss error as a rollback. The phrase *indeterminate transaction outcome* accurately describes a situation where the client did not receive final confirmation. This is why write operations require a stable request identifier rather than relying solely on function call counts or socket state.

A new connection is always a new session. It cannot continue transactions, session state, temporary tables, or advisory locks tied to the old session. After a connection error, evict the old connection from the pool using your library's API; never return a broken connection to the pool for another request to reuse.

## 2. Identifying and Classifying PostgreSQL Errors

PostgreSQL returns a `SQLSTATE` for many SQL errors. Applications should classify errors using `SQLSTATE` and the operation stage, rather than matching error message strings that may vary across versions or locales.

Common codes:

| SQLSTATE | Name or meaning | Handling guidance |
|---|---|---|
| Class 08, e.g., 08000, 08003, 08006 | Connection exception; connection no longer exists or was lost | Evict connection; outcome of an in-flight operation may be indeterminate |
| 08001 | Unable to establish connection | May retry connecting if budget remains and the service is recovering |
| 08007 | Transaction resolution unknown | Do not assume rollback; look up by idempotency key or re-run via idempotent flow |
| 40003 | Statement completion unknown | Treat as indeterminate outcome, especially for writes |
| 40001 | serialization_failure | Roll back and retry the entire transaction |
| 40P01 | deadlock_detected | PostgreSQL aborted one transaction in a deadlock; retry the entire aborted transaction |
| 55P03 | lock_not_available | Consider retrying per lock policy and deadline; do not retry infinitely |
| 57P01 | admin_shutdown | Server is shutting down; current connection is unusable |
| 57P02 | crash_shutdown | Server crashed; connections must be recreated after service recovery |
| 57P03 | cannot_connect_now | Server temporarily not accepting connections, common during startup or recovery |
| 53300 | too_many_connections | Server hit its connection limit; shed load and wait with backoff |
| 57014 | query_canceled | Statement was canceled, possibly by `statement_timeout` or client cancel request |
| 25P02 | in_failed_sql_transaction | Current transaction is in an aborted state; `ROLLBACK` required before continuing |
| 23505 | unique_violation | Unique constraint violation; usually a data error or idempotency conflict to handle, not an error to blindly retry |

JDBC libraries, drivers, and connection pools may wrap SQL errors inside other exceptions. When classifying, walk the exception cause chain to extract `SQLSTATE` if present, while recording whether the error happened while acquiring a connection, executing SQL, or committing. Some TCP-level network errors may carry no PostgreSQL `SQLSTATE`.

Not every error that looks transient should be retried. For example:

- Syntax errors, missing tables, missing columns, or wrong data types require fixing the statement or schema.
- Authentication and authorization errors require fixing credentials or privileges.
- `23505` may signal that a request was already processed previously; the application should look up the idempotency record instead of blindly re-running the same command.
- `57014` may reflect an overly slow query or an explicit user cancellation. Immediate retries can increase load without fixing the cause.
- `25P02` is a follow-on state after an earlier error. Find the root error in the transaction, roll back, and then decide whether to retry.

## 3. Retrying the Right Unit: The Entire Transaction

When PostgreSQL returns `40001` or `40P01`, the transaction is aborted. The application must roll back or close the connection per actual state, then re-execute the entire transaction from the start on a new connection or new transaction.

Do not retry only the final statement. Earlier reads may have driven business decisions based on an old snapshot or lock order. Re-running only the last statement can produce inconsistent results.

For example, a money transfer transaction might execute:

1. Read source account balance.
2. Verify balance is sufficient for transfer.
3. Debit source account.
4. Credit destination account.
5. Insert two ledger entries.
6. `COMMIT`.

If the transaction hits a deadlock or serialization failure, re-run all six steps inside a fresh transaction. Never retry only the debit or credit step.

A practical rule of thumb:

- `40001` and `40P01`: usually appropriate for bounded full-transaction retries.
- Connection errors: open a new connection and route the request through an idempotent flow. Do not rely on whether the client received a `COMMIT` acknowledgment.
- `55P03`: retry only if business rules allow waiting on locks and sufficient deadline remains; investigate lock contention causes.
- `53300`, `57P03`, or transient service unavailability: retry connecting with backoff while limiting concurrent requests.
- Data, syntax, authentication, and privilege errors: return errors or handle per business rules; do not auto-retry.

### Backoff, jitter, and retry limits

Continuous retrying can worsen overload. If thousands of requests retry simultaneously the moment the database recovers, they create a thundering herd.

A commonly used policy is exponential backoff with full jitter:

    delay = random(0, min(cap, base × 2^(attempt - 1)))

Where:

- `attempt` is the current attempt number, starting at 1.
- `base` is the base wait duration.
- `cap` is the maximum wait duration.
- `random` picks a random value between 0 and the computed ceiling.

As an illustration, take a 100 ms base and a 2-second cap. The first retry might wait randomly between 0 and 100 ms; subsequent attempts grow while never exceeding 2 seconds. Real values must match your SLA, normal latency, and system recovery times.

A retry policy must include all necessary bounds:

- Maximum attempt count.
- Total request deadline, counting connection pool wait, connect time, execution, and backoff.
- Limit on concurrent retry operations.
- Jitter so clients do not synchronize retries.
- Circuit breaking or load shedding when the database is overloaded.

Do not let every layer in the stack independently retry multiple times without a shared budget. For example, 4 API retries × 4 service retries × 4 driver retries can turn one request into dozens of database calls. Clearly assign which layer owns retries and propagate deadlines downward.

## 4. Designing Idempotency for Write Operations

An operation is idempotent if repeating the same request produces the same business result as executing it once. For example, setting an order status to `PAID` can be idempotent when updated conditionally and the outcome is saved; adding 100 to a balance every time a request arrives is not idempotent.

An idempotency key is a unique identifier representing one business intent. The client generates the key once for the initial request and resends that exact key on every retry. The key must remain stable across timeouts, connection drops, API gateway retries, and worker retries. Never generate a fresh key per attempt.

The following table illustrates where to store keys and results:

    CREATE TABLE request_dedup (
        idempotency_key uuid PRIMARY KEY,
        request_hash bytea NOT NULL,
        response jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    );

In multi-tenant systems or across multiple operation types, a composite primary key such as `(tenant_id, operation, idempotency_key)` can be used. Key scope must ensure two customers or two operation types cannot accidentally collide in the same key space.

Processing steps inside one transaction:

1. Canonicalize the payload and compute `request_hash`. The hash represents business content, excluding per-attempt metadata like request timestamps.
2. `INSERT` the idempotency key with `ON CONFLICT DO NOTHING` and `RETURNING`.
3. If `INSERT` created a new row, the current transaction owns processing the request. Apply the business changes.
4. Save the final response into the same idempotency row.
5. `COMMIT` the idempotency row, business changes, and response in the same transaction.
6. If `INSERT` created no row, read the existing record. Compare `request_hash`. If hashes match, return the saved response. If hashes differ, reject because the same key is being reused for two different request payloads.

Example initial SQL:

    INSERT INTO request_dedup (idempotency_key, request_hash)
    VALUES ($1, $2)
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING idempotency_key;

If the statement returns a row, the current transaction proceeds with business processing. If no row is returned, execute `SELECT request_hash, response FROM request_dedup WHERE idempotency_key = $1` in the next statement. Under default `READ COMMITTED` isolation, the subsequent `SELECT` obtains a fresh snapshot and can read the record committed by the earlier request. If the system uses `REPEATABLE READ` or `SERIALIZABLE`, concurrent conflicts can cause a serialization failure; in that case retry the entire transaction per `40001` rules.

Example business update and result persistence:

    UPDATE accounts
    SET balance = balance - $1
    WHERE account_id = $2
      AND balance >= $1;

    -- The application must verify exactly one row was updated.
    -- Then write the ledger and generate the business response.

    UPDATE request_dedup
    SET response = $3::jsonb
    WHERE idempotency_key = $4;

The SQL above illustrates the structure only. In a real application, check the updated row count, validate positive amounts, lock the right accounts, write the ledger inside the same transaction, and roll back if any business condition fails.

### Why must the idempotency record and business changes share one transaction?

If you save the key first and update the balance in a separate transaction, the process can crash between the two steps. A retry sees the key already exists and assumes the request finished, while the balance never changed. If you update the balance first and save the key in a separate transaction, the process can crash after crediting money and before saving the key; a retry will credit the money a second time.

When the key, business changes, and response commit atomically:

- If the transaction rolls back, neither the key nor the business change exists; a retry can process it again.
- If the transaction commits, both the key and the business change exist; a retry finds the key and returns the saved response.
- If the client loses the `COMMIT` acknowledgment, a retry on a new connection determines the outcome by looking up the key.

Idempotency records must not be purged earlier than the window during which clients, message brokers, or intermediaries can resend a request. If a key expires while an old request can still arrive, the operation risks executing again. Retention must follow business rules and maximum retry durations.

Never allow reusing the same key with a different payload. Comparing `request_hash` catches client bugs or malformed request replays. Define how payloads are canonicalized prior to hashing so JSON property ordering or numeric formatting does not make two equivalent payloads appear different.

## 5. Idempotency with External Side Effects

A PostgreSQL transaction guarantees atomicity only for data managed by that transaction. It cannot atomically `COMMIT` alongside an HTTP call to a payment gateway, email service, or separate message broker.

For example, an application debits money in PostgreSQL and then calls a payment API. If the payment API succeeds yet the connection drops before returning a response, the application does not know whether the payment executed. Rolling back the database cannot retract effects already committed in the external system.

A common pattern is the transactional outbox:

    CREATE TABLE outbox (
        event_id uuid PRIMARY KEY,
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        published_at timestamptz
    );

Within the same business transaction, the application updates data and `INSERT`s an event into `outbox`. After commit, a worker reads `outbox` and dispatches the event to the target system. The worker can resend if no acknowledgment arrives.

The outbox prevents losing events between database changes and event publication, yet it does not by itself create exactly-once delivery. The worker may dispatch an event successfully and crash before marking `published_at`. Upon restart, the worker will dispatch the event again.

Consequently, consumers should maintain an inbox or `processed_messages` table keyed uniquely by `event_id`. The consumer records `event_id` and applies its business change in the same transaction. Upon receiving the same `event_id` again, the consumer skips the duplicate effect and returns the appropriate result. For payment APIs, pass a provider-supported idempotency key whenever available.

A safe flow typically follows these steps:

1. API receives request with an idempotency key.
2. PostgreSQL commits business changes and the outbox event in one transaction.
3. Worker fetches unpublished events, acquires a lease or marks processing state in a short transaction, and commits.
4. Worker calls the external system using the stable `event_id` as an idempotency key.
5. Worker marks the event published after receiving the response.
6. If the worker crashes midway, the event may be resent; the target system or consumer deduplicates any repeat effect.

Never hold a database transaction open for a long time just waiting on HTTP. Doing so holds locks and connections, increasing pool exhaustion risk. If events must be claimed, use a time-bounded lease or short claim step; design delivery so resending remains safe.

If an external system neither supports idempotency nor provides a way to query results, retries cannot guarantee no duplicate effects. In such cases, implement reconciliation jobs, pending confirmation business states, or compensating actions tailored to the system.

## 6. Handling Connection Pools and Timeouts

Connection pools reuse PostgreSQL sessions to reduce connection creation overhead. While this boosts performance, it introduces additional failure modes:

- Idle connections closed silently by a firewall, proxy, or server.
- Database restarts or failovers leaving stale sockets inside the pool.
- Broken connections after a timeout accidentally returned to the pool.
- Pool exhaustion caused by requests holding connections too long or abandoned transactions.
- Total connections across all application instances exceeding PostgreSQL capacity.

Applications should configure bounded pools, validate or evict invalid connections per library capabilities, align connection lifetimes with network infrastructure, and close connections along every code path. Checking with `SELECT 1` proves only that a connection worked at that instant; it does not guarantee the next statement or `COMMIT` will succeed.

Timeouts to distinguish:

| Timeout | Scope | Purpose |
|---|---|---|
| `connect_timeout` | Client/driver | Limits time to establish a connection |
| `statement_timeout` | PostgreSQL | Cancels statements exceeding allowed execution time |
| `lock_timeout` | PostgreSQL | Avoids waiting too long for locks |
| `idle_in_transaction_session_timeout` | PostgreSQL | Closes sessions sitting idle inside a transaction |
| Client or socket timeout | Driver/runtime | Limits how long the client waits for a response |

Example checking PostgreSQL-side settings:

    SHOW statement_timeout;
    SHOW lock_timeout;
    SHOW idle_in_transaction_session_timeout;

You can scope timeouts to a specific transaction using `SET LOCAL`:

    BEGIN;
    SET LOCAL lock_timeout = '500ms';
    SET LOCAL statement_timeout = '5s';
    -- Execute business statements.
    COMMIT;

Values shown are illustrative only. Timeouts must align with request deadlines and legitimate query durations. If `statement_timeout` cancels a statement, the transaction normally enters an aborted state and requires `ROLLBACK` before continuing. Never treat a client timeout as proof that PostgreSQL aborted the statement; the server may still be executing if cancellation has not taken effect.

Do not size pools overly large assuming more connections are always better. Total connections across all app instances, workers, migrations, and admin tools must stay within safe server limits. Waiting on a bounded pool is usually better than opening unbounded connections and hitting `53300`.

## 7. Building Retry Flows in the Application

Processing logic should separate three responsibilities:

- The business function executing database steps within one transaction.
- An error classifier determining which errors are retryable based on `SQLSTATE` and execution phase.
- A retry coordinator managing deadlines, attempt counts, backoff, and idempotency keys.

The following pseudocode illustrates this structure. `evictConnection`, `isConnectionFailure`, and `sleepWithJitter` depend on your application library:

    Result handleRequest(UUID key, Payload payload) {
        byte[] hash = canonicalHash(payload);

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection connection = pool.getConnection()) {
                connection.setAutoCommit(false);

                try {
                    Result result = applyIdempotently(
                        connection, key, hash, payload
                    );
                    connection.commit();
                    return result;
                } catch (SQLException error) {
                    if (isConnectionFailure(error)) {
                        evictConnection(connection);
                        // Do not assume the transaction rolled back.
                        // Next attempt uses the same key and hash.
                    } else {
                        rollbackIfPossible(connection);
                        if (!isRetryableTransactionAbort(error)) {
                            throw error;
                        }
                    }
                }
            } catch (SQLException connectionOrPoolError) {
                if (!isRetryableConnectionError(connectionOrPoolError)) {
                    throw connectionOrPoolError;
                }
            }

            if (attempt == MAX_ATTEMPTS || deadlineExceeded()) {
                break;
            }
            sleepWithJitter(attempt);
        }

        throw new RetryExhaustedException(key);
    }

This pseudocode demonstrates principles rather than a directly compilable Java class. When implementing:

- `applyIdempotently` must use the same key, hash, and transaction to persist outcomes as described earlier.
- If `commit` throws a connection error, never treat it as a rollback. Evict the connection from the pool; the next attempt checks the same key on a fresh connection.
- For `40001` or `40P01`, roll back the transaction and re-run the entire business function.
- For connection errors, the driver may not allow rolling back because the socket is broken. Closing or evicting the connection is mandatory; never reuse that connection object.
- Do not swallow non-retryable exceptions. Return the appropriate error to the caller or transition to reconciliation if the outcome is indeterminate.
- Never generate a new idempotency key inside the retry loop.

If a request's deadline expires, stop retrying even if attempts remain. Return an appropriate status so the client can query or resend with the same key. APIs can expose a status lookup endpoint by key so clients can resolve timeouts without guessing.

## 8. Designing Connection-Loss Test Scenarios

Testing merely by stopping and starting PostgreSQL is insufficient. Actively inject failures at multiple points in the transaction lifecycle, especially the window around `COMMIT`.

Use a dedicated PostgreSQL environment, Docker, Toxiproxy, or network fault-injection tools for controlled failures. In test environments, `pg_terminate_backend` can terminate a session's PostgreSQL backend. Never terminate connections on a production database.

Get the PID of the session under test:

    SELECT pg_backend_pid();

From a privileged session, terminate the target backend:

    SELECT pg_terminate_backend(<pid>);

This terminates the corresponding session; it is useful for verifying that the application detects closed connections and evicts them from the pool. It does not fully replace cutting the network right at `COMMIT`, so add a proxy or failpoint when testing lost `COMMIT` acknowledgments.

Scenario matrix to include:

| Scenario | Fault injection method | What to verify |
|---|---|---|
| Database unavailable | Stop PostgreSQL before application connects | Bounded connection retries; request makes no changes |
| Session killed mid-query | Run `pg_terminate_backend` on the test backend | Driver errors; pool evicts connection; request is safely reprocessed |
| Disconnect after write, before `COMMIT` | Terminate session prior to sending `COMMIT` | Uncommitted transaction leaves no partial data |
| Lost `COMMIT` response | Use a proxy to drop response traffic after server processes `COMMIT` | Client does not assume rollback; retry with same key has single effect |
| PostgreSQL restart or failover | Restart primary or promote standby in test environment | Application reconnects to the right writer and resolves indeterminate outcomes |
| Deadlock | Two transactions lock the same two rows in reverse order | One transaction gets `40P01`; entire transaction retries |
| Serialization failure | Run conflicting concurrent transactions under `SERIALIZABLE` | `40001` triggers full-transaction retry |
| Stale pooled connections | Hold idle connections, then restart database or close sockets | Stale connections are detected and not repeatedly handed out |
| Connection exhaustion | Cap pool/server and generate concurrent load | System avoids retry storms; deadlines and backoff hold |
| Two concurrent requests, same key | Send identical key and payload in parallel | Only one transaction applies changes; both receive the same result |
| Same key, different payload | Resend existing key with altered content | Request is explicitly rejected; no second effect occurs |

### Testing deadlocks with two sessions

Create two test rows in `accounts`, then open two sessions.

Session A:

    BEGIN;
    UPDATE accounts SET balance = balance - 1 WHERE account_id = 1;
    -- Wait for session B to update the second row.
    UPDATE accounts SET balance = balance + 1 WHERE account_id = 2;
    COMMIT;

Session B:

    BEGIN;
    UPDATE accounts SET balance = balance - 1 WHERE account_id = 2;
    -- Wait for session A to update the first row.
    UPDATE accounts SET balance = balance + 1 WHERE account_id = 1;
    COMMIT;

When two sessions hold locks in opposite orders, PostgreSQL detects the deadlock and aborts one transaction with SQLSTATE `40P01`. The application must retry the entire aborted transaction. In real systems, standardize lock acquisition order to minimize deadlocks while still handling deadlocks when they occur.

### Testing idempotency under concurrent load

Send multiple concurrent requests carrying the same idempotency key and payload. Once all finish, query the database to verify:

- Only one `request_dedup` row exists for that key.
- Only one corresponding business mutation occurred, such as one ledger entry for the operation.
- Successful requests received the exact same business response.
- No dangling transactions or unintended partial-processing rows remain.

Then resend the same key with a different payload. The application must detect the `request_hash` mismatch and reject the request. It must never silently return the old payload's response as if the new payload were processed.

### Testing the COMMIT window

This is the most critical test for write operations:

1. Send a request with a pre-generated idempotency key.
2. Allow PostgreSQL to execute the transaction and process `COMMIT`.
3. Use a proxy or failpoint to drop server-to-client response bytes before the client receives the `COMMIT` confirmation.
4. Verify the client records an indeterminate outcome and does not generate a new key.
5. Resend the request with the exact original key and payload.
6. Verify the application returns the saved response if the prior transaction committed; if it did not commit, the new request processes and commits exactly once.
7. Reconcile balances, ledgers, idempotency records, and outbox events.

Checking only HTTP status or client exceptions is insufficient. Inspect the final data in PostgreSQL to confirm the system neither duplicated nor dropped effects.

## 9. Criteria for Evaluating Test Results

A thorough resilience test must collect evidence on both the application and database sides.

On the application side, record:

- `SQLSTATE` and underlying root error type.
- Failure stage: connection acquisition, SQL execution, or `COMMIT`.
- Retry counts, backoff timings, and total request duration.
- Whether the broken connection was evicted from the pool.
- Final outcome: success, retryable error, non-retryable error, or indeterminate outcome requiring lookup.
- Idempotency key used (logged as a hash or truncated form if needed to avoid leaking sensitive info).

On the PostgreSQL side, observe sessions via:

    SELECT
        pid,
        usename,
        application_name,
        state,
        wait_event_type,
        wait_event,
        xact_start,
        query_start
    FROM pg_stat_activity
    WHERE datname = current_database()
    ORDER BY xact_start NULLS LAST;

Never log full sensitive payloads into query or application logs merely to trace retries. Correlate events using request IDs, operation names, and protected keys.

Useful metrics include connection failure rate, pool evictions, retry counts by `SQLSTATE`, retry success rate, idempotency key reuse hits, requests exhausting retry budgets, pool wait times, and active connection counts. If retries surge while success rates stay flat, the system may be amplifying an outage.

A passing test suite must prove:

1. Broken connections are evicted and the application acquires fresh connections once PostgreSQL recovers.
2. `40001` and `40P01` trigger full-transaction retries, never retrying only the final statement.
3. Lost `COMMIT` acknowledgments do not cause false rollback assumptions.
4. Resending a request with the same key causes no additional business mutation.
5. Reusing a key with a different payload is rejected.
6. Retries are bounded, use backoff, and respect deadlines.
7. Pools neither retain broken sockets nor trigger connection storms when the database is down.
8. Outboxes and consumers tolerate redelivered events.

## 10. Common Mistakes

**Retrying only the final statement after any error.** This ignores the snapshot, prior checks, and earlier updates within the transaction. For retryable transaction aborts, re-execute the entire business unit.

**Treating timeouts as rollbacks.** A client timeout only shows the client stopped waiting. PostgreSQL may have already finished the transaction or may still be executing if cancellation has not arrived. Writes require idempotency and outcome lookup capability.

**Generating a new idempotency key on each retry.** Every attempt then looks like a brand-new intent, defeating deduplication. Keys must be generated at the business request boundary and preserved across the entire retry lifecycle.

**Storing the key and business data in two separate transactions.** Crashing between transactions can mark a request processed without applying changes, or apply changes without leaving a deduplication record.

**Retrying every SQLSTATE.** Syntax, privilege, data, and constraint errors do not resolve by waiting. Blind retries only increase load and obscure root causes.

**Testing only by shutting down the database.** That fails to reproduce cases where the server committed while the client lost the response. Test the window around `COMMIT` explicitly.

**Assuming an outbox guarantees exactly-once delivery.** An outbox guarantees the event is persisted with the business transaction. Delivery can still repeat; consumers must deduplicate.

**Holding transactions open during external service calls.** This prolongs connection and lock retention. Write to an outbox and dispatch externally outside the transaction.

## 11. Practice Exercises

1. Build a money transfer API accepting an idempotency key. Send the exact same request three times and verify only one ledger write occurs.
2. Use two sessions to trigger a deadlock. Observe SQLSTATE `40P01` and update the application to retry the entire transaction.
3. Run transactions under `SERIALIZABLE` isolation with two conflicting concurrent requests. Observe `40001` and verify retries read fresh data.
4. Terminate a PostgreSQL backend while the application performs a write. Verify the connection pool evicts the dead session and the request causes no duplicate mutation.
5. Use a proxy to drop the `COMMIT` acknowledgment. Resend with the same key and verify both the response and business data.
6. Create an outbox event, let the worker publish it successfully, and kill the worker before marking `published`. Restart the worker and verify the consumer applies the effect only once.
7. Cap connections to trigger `53300`. Observe backoff, deadlines, pool wait times, and behavior when the retry budget expires.

Upon completing the exercises, learners should be able to explain why connection loss during `COMMIT` yields an indeterminate outcome, why `40001` and `40P01` require retrying the entire transaction, and how idempotency keys paired with PostgreSQL transactions protect writes from duplicate submissions.
