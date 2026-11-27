# Keeping Database Timeouts Smaller Than RPC Deadlines

## 1. Why must database timeouts stay within the RPC deadline?

In **SPRING_GRPC**, an RPC typically performs multiple steps: receiving and validating the request, waiting for a connection from the pool, running queries, waiting on locks, committing the transaction, building the response, and sending it over HTTP/2. The client sets a deadline for the entire call. If a query or pool wait continues longer than the client allows, the server consumes resources for a request whose caller is no longer waiting for the result.

Database timeouts must be smaller than the RPC's remaining time so the server has a chance to stop database work, roll back the transaction if not yet committed, release the connection, and return a controlled error before the overall deadline expires. This is part of an end-to-end time budget, not a fixed number applied uniformly to every request.

This lesson focuses on coordinating:

- Client RPC deadlines and server-side remaining deadlines.
- HikariCP connection acquisition timeouts.
- Database lock timeouts, statement/query timeouts, and transaction timeouts.
- Margins reserved for validation, commit, response mapping, and the network.
- Cancellation, driver query cancellation, and transaction rollback.
- Mapping timeouts to gRPC statuses, retries, and idempotency.
- Metrics and integration tests to prove timeouts work.

## 2. The RPC deadline is an end-to-end time limit

A deadline represents the absolute point in time after which an RPC is no longer permitted to keep waiting. As time passes, the remaining budget shrinks; the server should not start a new database step if insufficient time remains for that step and post-query processing.

For example, suppose the client sets an 800 ms deadline. The server receives the request after 70 ms of transport and queuing delay; the server has roughly 730 ms left. If the server spends 500 ms waiting on the pool, 400 ms on a query, plus commit/serialization time, database work has already exceeded the deadline before a response can finish.

Do not treat the deadline as a separate timeout for each step. Each dependency must use the remaining budget of the same RPC, or a lower service-level cap.

Client stub example:

```java
OrderReply reply = blockingStub
    .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

Do not mint a fresh unlimited deadline at each layer. When calling another service, propagate the remaining budget or an appropriate deadline so total downstream time still fits within the end-to-end deadline.

## 3. Allocating timeouts by layer

A budget model:

```text
RPC deadline (outer bound)
  ├─ decode / validate / application overhead
  ├─ connection pool acquisition
  ├─ database transaction
  │    ├─ lock wait
  │    ├─ statement/query execution
  │    └─ commit
  └─ response mapping / serialization / network margin
```

Let R be the remaining time when the server starts processing. Reserve a portion for non-database processing and response handling:

```text
Database budget < R - application/response reserve
```

Within the database budget:

- Pool acquisition must finish early enough to leave time to run the query.
- Lock timeout should be smaller than statement timeout if the database supports configuring it separately.
- Statement/query timeout must fit inside the database budget.
- Transaction timeout caps the entire transaction and should not exceed the remaining budget allocated to the transaction.
- Commit and cleanup need a safety margin; never set query timeout equal to the full RPC remaining time.

Timeouts can nest or measure overlapping intervals; do not mechanically add lock timeout and statement timeout if the database counts lock wait time inside statement timeout. Understand the semantics of the database and driver in use.

## 4. Reading the remaining deadline from gRPC Context

In a gRPC Java server, the current deadline can be read via Context:

```java
Deadline deadline = Context.current().getDeadline();

if (deadline == null) {
    // Apply a service-level cap if the RPC has no deadline.
}

long remainingNanos =
    deadline.timeRemaining(TimeUnit.NANOSECONDS);
```

Do not assume every client sends a deadline. The service should enforce an internal time cap as an upper bound even when the client omits a deadline. If the deadline has already expired or the remaining budget is insufficient, fail fast before acquiring a connection or starting a query.

Example helper computing a query budget:

```java
long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
long reserve = TimeUnit.MILLISECONDS.toNanos(80);
long queryBudget = remaining - reserve;

if (queryBudget < TimeUnit.SECONDS.toNanos(1)) {
    throw Status.DEADLINE_EXCEEDED
        .withDescription("Insufficient time for database operation")
        .asRuntimeException();
}

int queryTimeoutSeconds =
    (int) TimeUnit.NANOSECONDS.toSeconds(queryBudget);
```

JDBC Statement.setQueryTimeout takes seconds; a value of 0 usually means unlimited. Therefore, if less than one second remains in the budget, do not round down to 0 and accidentally disable the timeout. Fail fast or use a finer-grained timeout supported by the database/driver.

Recompute the remaining deadline right before executing the query, after acquiring the connection. Time spent waiting on the pool also consumes the RPC budget.

## 5. HikariCP connection acquisition timeout

Before a query runs, the application may have to wait for a connection in HikariCP. The connection-timeout property bounds how long to wait when borrowing a connection from the pool.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 500
      validation-timeout: 250
```

The values above are illustrative only. HikariCP connectionTimeout is a pool-level setting and does not automatically adjust to each RPC's deadline. Therefore:

- Choose a conservative value based on typical pool wait budgets.
- Check the remaining deadline before starting operations that need a connection.
- Set connectionTimeout small enough not to block threads for too long.
- After acquiring a connection, recompute the remaining budget before running the query.
- Monitor pending threads and acquisition time; if pending threads climb continuously, investigate pool/database causes rather than just increasing the timeout.

If a workload mixes RPCs with widely varying deadlines, add a guard prior to acquisition and consider a dedicated budget-aware acquisition mechanism if needed. Do not claim a static HikariCP configuration automatically understands per-call deadlines.

## 6. Setting JDBC query timeout from the remaining budget

With JDBC, Statement.setQueryTimeout bounds statement execution time in seconds. This can be applied inside JdbcTemplate's StatementCreator; the statement creation callback runs after JdbcTemplate has acquired a connection:

```java
public List<OrderRow> findOrders(String customerId) {
    return jdbcTemplate.query(connection -> {
        PreparedStatement statement = connection.prepareStatement(
            "SELECT id, status FROM orders WHERE customer_id = ?"
        );
        statement.setString(1, customerId);

        int timeoutSeconds = queryTimeoutPolicy
            .remainingBudgetSeconds();
        statement.setQueryTimeout(timeoutSeconds);

        return statement;
    }, orderRowMapper);
}
```

remainingBudgetSeconds() should read the current deadline, subtract the reserve, and apply the service cap. If too little time remains, it must refuse execution rather than returning 0.

A JDBC timeout is a request to the driver; how reliably the query is canceled and when the connection is returned depend on the driver/database. Verify against the production driver. With JPA, query timeout hints and transaction timeout enforcement depend on the provider; test empirically instead of assuming all queries are bounded identically.

## 7. Database-side statement timeout and lock timeout

Database-side timeouts protect the system even if an application thread hangs or driver cancellation does not behave as expected.

For example, PostgreSQL supports statement_timeout and lock_timeout. Limits can be set per transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '150ms';
SET LOCAL statement_timeout = '600ms';

SELECT id, status
FROM orders
WHERE customer_id = 'customer-17';

COMMIT;
```

SET LOCAL applies only to the current transaction and automatically expires when the transaction ends; this is safer than changing long-lived session settings on pooled connections. Avoid concatenating user data into SQL strings; use parameterized queries or the appropriate database API to set dynamic values.

Lock timeout should be smaller than statement timeout if you want to detect lock contention early. Statement timeout caps the individual statement; transaction timeout and the RPC deadline still need to cap overall execution.

Setting names and units vary by database. PostgreSQL, MySQL, SQL Server, and Oracle have different mechanisms; follow the documentation and driver behavior of the deployed database.

## 8. Spring transaction timeout as an additional safeguard

Spring allows setting a timeout at the transaction boundary:

```java
@Transactional(timeout = 2)
public OrderResult updateOrder(UpdateOrderCommand command) {
    // Database work
}
```

This timeout is typically declared statically per method and acts as an extra safeguard on the transaction. It does not automatically read each request's gRPC deadline. Whether the timeout propagates down to statements depends on the transaction manager, DataSourceUtils/JdbcTemplate, and the JPA provider.

Do not treat @Transactional(timeout=2) as proof that every JDBC operation is guaranteed to cancel after exactly two seconds. Combine transaction timeouts with statement timeouts/database-side timeouts and test on the real stack.

If you need a dynamic transaction budget based on remaining deadline, create a per-invocation transaction definition rather than mutating a shared TransactionTemplate across threads. Ensure the implementation guarantees the transaction manager actually applies the timeout to the active resource.

## 9. Leaving time for commit and response

A common misconfiguration is setting the statement timeout equal to the RPC deadline. The query might finish right near the deadline, yet the server still needs to:

- Flush/commit the transaction.
- Handle constraints or deferred database work.
- Close/release resources.
- Convert the domain result to Protobuf.
- Send the response and terminal signal.

Therefore, the query budget must be lower than the remaining RPC budget by a reserve margin. The reserve depends on actual latency; measure p95/p99 of commit, mapping, and response sending instead of picking arbitrarily.

In transactions with multiple statements, never grant the full deadline anew to each query. Total transaction budget must decrease as elapsed time is consumed. A request with 4 queries must not allow 700 ms per query if the whole RPC only has 1 second remaining.

## 10. Cancellation does not automatically stop database queries

When the client deadline expires or the client cancels, the gRPC server context is canceled. However, that does not guarantee the JDBC statement has stopped immediately or the transaction has rolled back instantaneously.

Combine multiple controls:

- Check Context cancellation before starting new database steps.
- Query/statement timeouts at both JDBC and database levels.
- Transaction timeout to bound the transaction scope.
- Driver/database statement cancellation support.
- Rollback when a query timeout or error causes the transaction to fail.
- Never catch a timeout exception and return a normal result when rollback is required.

If work runs on another executor, propagate the appropriate cancellation/deadline context and open the transaction on the worker thread. Spring imperative transactions are typically thread-bound; do not assume a transaction propagates automatically into async callbacks.

## 11. Commit timeouts and uncertain outcomes

If a client receives DEADLINE_EXCEEDED, it cannot conclude the database definitely did not commit. The server might have committed successfully while the response was lost, or the query/commit may not have completed and the transaction rolled back.

For commands with side effects:

- Use a stable idempotency key for the same business intent.
- Save the idempotency record and business update in the same transaction.
- On retry with the same key, return the committed result instead of executing the side effect again.
- When the outcome is uncertain, provide an operation/status query or retry with the same key.
- For external events, write an outbox record in the same transaction.

Do not blindly retry a payment or order creation command merely because the client observed a timeout. A timeout describes the caller's wait limit, not proof of rollback.

## 12. Mapping timeouts to gRPC status

Statuses should reflect causes the caller can act on:

| Situation | Commonly Used Status | Notes |
| --- | --- | --- |
| RPC deadline has expired | DEADLINE_EXCEEDED | Caller ran out of time budget |
| Caller actively canceled | CANCELLED | Does not guarantee prior transaction did not commit |
| Pool temporarily cannot provide a connection | UNAVAILABLE or RESOURCE_EXHAUSTED | Choose per overload/quota contract |
| Database query exceeded operation budget | DEADLINE_EXCEEDED | Record internal timeout type in logs |
| Optimistic locking conflict | ABORTED | Re-read and retry the entire use case |
| Invalid request | INVALID_ARGUMENT | Do not retry the exact same request |

Do not return SQL, connection strings, stack traces, or internal details in status descriptions. Server logs need correlation IDs, RPC method, remaining budget at each step, and timeout type for analysis.

## 13. Observing and testing the timeout hierarchy

Collect separate metrics for each layer:

- Remaining RPC deadline when the server starts processing.
- Connection wait time and acquisition timeout count.
- Query/statement duration and query timeout count.
- Lock wait, transaction duration, commit duration, and rollback count.
- Number of canceled or deadline-exceeded requests.
- Number of queries still running after the caller canceled.
- Pool active/idle/pending counts and database CPU/I/O/lock metrics.

Test through a real gRPC server and a database matching production whenever possible:

| Test | What to verify |
| --- | --- |
| Short RPC deadline | Server does not start the query when budget is insufficient |
| Pool exhausted | Acquisition wait is bounded and status is accurate |
| Slow query | Statement/database timeout stops the query within budget |
| Lock contention | Lock timeout is smaller than statement timeout |
| Commit near deadline | Query still leaves reserve for commit/response |
| Client cancel | Query is canceled per driver/database capability; transaction rolls back if uncommitted |
| Missing client deadline | Service-level cap still bounds duration |
| Retry after timeout | Idempotency prevents duplicate side effects |
| Streaming RPC | Each database operation uses fresh remaining budget, not stale initial budget |

Load tests must include slow queries, lock contention, and pool saturation. Testing a single query timeout in isolation does not prove the full timeout hierarchy works.

## 14. Review checklist

- Client sets deadlines aligned with the RPC's SLO.
- Server reads remaining deadline from gRPC Context and enforces a service-level cap when absent.
- Reserve margin exists for commit, response mapping, and network.
- Pool acquisition timeout fits the wait budget; team recognizes HikariCP timeout is a static pool config.
- Query/statement timeout is applied after borrowing the connection and right before execution.
- Lock timeout is smaller than statement timeout when supported by the database.
- Transaction timeout acts as an extra safeguard, not a replacement for query timeout.
- Database-side timeouts are configured and safely scoped/reset on pooled connections.
- Cancellation is coordinated with the driver/database; never assuming gRPC automatically cancels JDBC.
- Timeout exceptions trigger rollback when the transaction has not committed.
- Commands with side effects use idempotency; events use outbox.
- Status mapping distinguishes DEADLINE_EXCEEDED, CANCELLED, UNAVAILABLE, and ABORTED.
- Metrics separately measure RPC, pool wait, query, lock, and transaction duration.
- Integration tests verify timeouts on the real database/driver.

In **SPRING_GRPC**, the RPC deadline is an end-to-end budget; pool acquisition, lock waits, queries, and transactions must consume smaller slices of that budget while leaving room for commit and response delivery. Combine timeouts across HikariCP, JDBC/driver, database, and Spring transactions according to each layer's semantics. When a timeout occurs, handle cancellation and rollback in a controlled manner while using idempotency to protect commands in case commit succeeded but the response was lost.
