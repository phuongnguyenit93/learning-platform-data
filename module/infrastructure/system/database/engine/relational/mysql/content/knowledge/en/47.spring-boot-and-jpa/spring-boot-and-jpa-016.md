# Connection Loss, Bounded Retries, and Preventing Duplicate Business Writes

In a Spring Boot application using JPA to write to MySQL, losing a connection does not guarantee the transaction rolled back. If the network drops after the application sends `COMMIT` but before receiving the response, MySQL may have committed successfully while the application sees only an error. Resending the request blindly can create duplicate orders, payments, or business records.

To recover safely, the application must combine three mechanisms: classifying errors by root cause and failure point, executing bounded retries in fresh transactions, and protecting write operations with idempotency keys. This lesson belongs to the **DATABASE_MYSQL** module, focusing on operating MySQL from Java/Spring Boot/JPA applications, handling flaky connections, transactions, connection pools, and business correctness.

## 1. Understanding Connection Loss Errors

A request from an application to MySQL traverses multiple layers:

~~~text
HTTP client
    |
Spring Controller
    |
Application Service
    |
Spring Transaction Manager
    |
JPA / Hibernate / EntityManager
    |
JDBC / MySQL Connector/J
    |
Connection Pool
    |
Network / Proxy / Load Balancer
    |
MySQL Server
~~~

Failures can occur at any layer. For example:

- The connection pool hands out a connection already closed by MySQL or a firewall.
- DNS, routing, or firewall rules prevent opening a new connection.
- MySQL restarts or fails over mid-request.
- A proxy closes idle connections according to its own timeout.
- A socket timeout fires while the server is executing a query.
- The client loses the response after the server has already committed the transaction.

Crucially, the application only observes that no response arrived. It cannot always know whether the server received, executed, or committed the statement.

### Three States to Distinguish

| State | Meaning | Handling Strategy |
|---|---|---|
| Definitely never sent | Connection failed before the request reached the server | Can open a new connection and retry if within the request deadline |
| Operation clearly failed | Server returned a deterministic error and rolled back the transaction | Classify error code; retry only if transient |
| Outcome indeterminate | Connection lost while sending, executing, or waiting for `COMMIT` response | Look up business state by request key before re-executing |

Never treat every **CommunicationsException**, socket timeout, or SQLState class 08 error as proof that the transaction did not commit. That mistake is the #1 cause of duplicate writes.

## 2. JPA Transactions and Retry Boundaries

In Spring, **@Transactional** is typically implemented via proxies and a transaction manager. When a method is invoked through the proxy, Spring starts a transaction, binds an `EntityManager` to it, and commits or rolls back upon method exit.

A typical business method:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Order order = Order.from(command);
        return orderRepository.save(order);
    }
}
~~~

If the connection drops while the transaction is committing, the exception may surface only as the proxy finishes the call. The method body may have reached its final line while the commit remained unconfirmed to the client.

By default, Spring marks a transaction for rollback when a transactional method throws a **RuntimeException** or **Error**. Checked exceptions do not trigger automatic rollback under default settings. If business logic uses checked exceptions to report errors, declare **rollbackFor** appropriately or translate them to runtime exceptions per application conventions. Before retrying, ensure the previous transaction rolled back cleanly with no half-written state remaining.

### Why Never Retry Inside the Same Transaction?

Once a transaction rolls back or its connection breaks:

- The current transaction is no longer a safe environment to continue.
- The `EntityManager` may hold a persistence context with stale entities and inconsistent state.
- Certain exceptions mark the transaction rollback-only.
- Prior statements in the transaction may have rolled back; re-running only the last statement will not replay earlier work.

Retries must start a brand-new transaction, reload required data, and re-verify business invariants. Never reuse managed entities from a failed persistence context to decide the next write.

### Note on Open EntityManager in View

If **Open EntityManager in View** is enabled, Spring may keep a single `EntityManager` bound to the web request throughout its lifecycle. Consequently, starting a new transaction does not always mean starting a fresh persistence context. After a rollback or connection failure, never reuse managed entities from the previous attempt. Reload data in the new transaction, consider disabling Open EntityManager in View for retryable write flows, or enforce explicit persistence context boundaries per your JPA setup.

### Avoid Proxy Self-Invocation

Inside the same bean, calling another method via **this** normally bypasses the Spring proxy. Thus, code like the following fails to start a new transaction per attempt:

~~~java
public void retryOperation() {
    for (int i = 0; i < 3; i++) {
        this.writeInTransaction();
    }
}

@Transactional
public void writeInTransaction() {
    // ...
}
~~~

Place the transactional execution in a separate bean or use **TransactionTemplate** to define transaction boundaries explicitly.

## 3. Classifying Spring/JPA/MySQL Errors

Spring translates `SQLException` and JPA/Hibernate exceptions into the **DataAccessException** hierarchy. The outermost exception class varies by driver, provider, and layer where the failure occurred. Therefore, never catch a single exception class and assume every error of that type is retryable.

### Common Failures

| Error or Group | Example | Handling Direction |
|---|---|---|
| Deadlock | MySQL 1213, SQLState 40001 | Roll back the entire transaction and retry from the beginning if permitted |
| Lock wait timeout | MySQL 1205, typically SQLState HY000 | Roll back the entire transaction in the app, inspect blockers, then consider retrying |
| Communications failure | Connector/J `CommunicationsException`, client codes 2006/2013 | Acquire new connection; if commit is indeterminate, look up idempotency state |
| Unable to acquire connection | `CannotGetJdbcConnectionException` or resource error | Check pool, endpoint, and infrastructure; retry only if transient and within deadline |
| Optimistic lock conflict | `OptimisticLockingFailureException` or `OptimisticLockException` | Reload data and retry the whole use case if business logic permits |
| Pessimistic lock conflict | `CannotAcquireLockException` or `PessimisticLockingFailureException` | Bounded retry after rollback |
| Duplicate key | MySQL 1062, `DataIntegrityViolationException` | Check business/idempotency rules; never retry blindly |
| Invalid SQL or schema | MySQL 1054, 1064 | Fix code or schema; never retry |
| Permission/auth error | MySQL 1045, 1142 | Fix configuration or grants; never retry continuously |

### Distinguishing Transient vs. Non-Transient

Spring defines exception categories such as:

- **TransientDataAccessException:** errors that may be temporary and recoverable upon retry.
- **NonTransientDataAccessException:** retrying the exact same operation will usually continue failing.
- **ConcurrencyFailureException:** transaction contention errors, such as optimistic locking conflicts.
- **DataIntegrityViolationException:** data violated constraints like unique keys or foreign keys.
- **DataAccessResourceFailureException:** database resource access failed; does not automatically mean the error is transient.

Never retry every **DataAccessException**. Errors caused by invalid data, missing privileges, or broken schemas will fail identically on retry. Conversely, connection drops may require replacing the connection and checking transaction outcomes rather than blindly re-invoking the method.

### Inspecting Root Causes

When diagnosing, record:

- Outermost exception type.
- Full cause chain and `SQLException` chain.
- SQLState and vendor error code if present.
- Operation in flight: acquiring connection, executing SQL, flushing, committing, or rolling back.
- Whether the transaction could already have committed.

With Hibernate, root causes may be wrapped inside JPA or Spring exceptions. Traverse the full cause chain rather than inspecting only top-level controller exceptions.

## 4. Bounded Retries and Backoff

Retries help recover from contention or brief resource blips. Unbounded or aggressive retries amplify outages: when a database is overloaded, synchronized retries flood it with extra connections, queries, and transactions.

A sound retry policy defines:

1. An explicit allowlist of retryable errors.
2. Maximum attempt count.
3. Exponential backoff intervals with jitter.
4. Overall request deadline.
5. Conditions for opening a fresh transaction.
6. Idempotency protection for writes.
7. Metrics tracking retry counts and exhausted failures.

### Exponential Backoff and Jitter

Reference formula:

**delay = min(maxDelay, baseDelay × 2^(attempt - 1)) + randomJitter**

Example:

| Next Attempt | Base Backoff | Sample Jitter | Total Wait |
|---:|---:|---:|---:|
| 2 | 50 ms | 12 ms | 62 ms |
| 3 | 100 ms | 25 ms | 125 ms |
| 4 | 200 ms | 18 ms | 218 ms |

Jitter spreads retrying requests over time, preventing multiple instances from thundering-herd retrying at the exact same instant. Tune values to your target latency and remaining request budget.

Never sleep for backoff while a transaction remains open. Roll back and release the connection first, wait outside any transaction, and only then begin the next transaction.

## 5. Retrying with TransactionTemplate

**TransactionTemplate** lets you wrap each attempt in its own dedicated transaction. This cleanly ensures commit-time exceptions surface outside the retry loop.

Example configuration:

~~~java
@Configuration
public class TransactionRetryConfig {
    @Bean
    TransactionTemplate retryTransactionTemplate(
            PlatformTransactionManager transactionManager) {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setTimeout(5);
        return template;
    }
}
~~~

Transactional business writer bean:

~~~java
@Service
public class OrderWriter {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderWriter(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public OrderResult place(CreateOrderCommand command) {
        int changed = inventory.reserve(
                command.sku(), command.quantity());

        if (changed != 1) {
            throw new OutOfStockException(command.sku());
        }

        Order order = Order.create(
                command.requestId(),
                command.customerId(),
                command.sku(),
                command.quantity());

        orders.save(order);
        return OrderResult.from(order);
    }
}
~~~

Retry facade outside any transaction:

~~~java
@Service
public class RetryingOrderService {
    private final TransactionTemplate transactionTemplate;
    private final OrderWriter orderWriter;

    public RetryingOrderService(
            TransactionTemplate transactionTemplate,
            OrderWriter orderWriter) {
        this.transactionTemplate = transactionTemplate;
        this.orderWriter = orderWriter;
    }

    public OrderResult place(CreateOrderCommand command) {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return transactionTemplate.execute(
                        status -> orderWriter.place(command));
            } catch (RuntimeException error) {
                if (!RetryDecider.isRetryableTransactionError(error)
                        || attempt == maxAttempts) {
                    throw error;
                }

                RetryDelay.sleepWithJitter(attempt);
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
~~~

**RetryDecider**, **RetryDelay**, **CreateOrderCommand**, and repositories are illustrative components to implement per your application. Configuring **REQUIRES_NEW** ensures each invocation creates a new transaction; ideally, call the facade from a flow not already holding an outer business transaction. If an outer transaction exists, it is suspended while still holding its own connection/locks, complicating inner retries.

Key detail: **transactionTemplate.execute(...)** returns only after both the callback and the commit step finish. If commit throws an exception, the outer loop catches it. Never put the retry loop inside the callback, as attempts would share the same transaction.

## 6. Ordering @Retryable and @Transactional Properly

You may use Spring Retry or your project's managed retry mechanism. However, interceptor/proxy ordering is critical.

Desired structure:

~~~text
Retry interceptor
    |
    +-- Transaction interceptor: begin transaction 1
    |       execute use case
    |       commit / rollback
    |
    +-- Transaction interceptor: begin transaction 2
    |       execute use case again
    |       commit / rollback
    |
    +-- Transaction interceptor: begin transaction 3
            execute use case again
            commit / rollback
~~~

Every attempt must run in an independent transaction. If the transaction interceptor wraps outside the retry interceptor, the retry loop executes inside one shared transaction. Once that transaction is marked rollback-only, subsequent attempts are futile and lead to **UnexpectedRollbackException**.

To avoid proxy pitfalls:

- Place the retry method and transactional method in two separate beans.
- Never call the transactional method via self-invocation.
- Verify the retry interceptor wraps outside the transaction interceptor.
- Test that each attempt gets a fresh transaction ID or connection/transaction.
- Prefer `TransactionTemplate` if annotation ordering is hard to verify.

Never catch all exceptions with **@Retryable**. Configure only explicitly identified transient errors; never retry validation errors, constraint violations, permission errors, or schema mismatches.

## 7. Preventing Duplicate Writes with Idempotency Keys

Idempotency ensures that repeating the same business request produces the business effect only once. This is essential protection whenever a client cannot tell whether a prior transaction committed.

Assign each request a stable identifier, such as:

- A client-generated ID sent in a request header.
- A payment request ID from an orchestrating system.
- A UUID generated once at the entry point of the business flow and preserved across all retries.

Never generate a fresh idempotency key on each retry attempt. Changing the key causes the database to treat each retry as a brand-new request.

### Table Design

~~~sql
CREATE TABLE idempotency_request (
    request_key VARCHAR(100) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (request_key)
) ENGINE=InnoDB;
~~~

Fields:

- **request_key:** unique identifier of the business request.
- **request_hash:** hash of the canonicalized payload, catching reuse of the same key with different contents.
- **status:** processing state, e.g., `COMPLETED`.
- **response_json:** stored result to replay on duplicate submissions.
- **created_at/updated_at:** supports auditing and retention cleanup.

In multi-tenant systems where request keys are unique only per tenant, include tenant ID in the unique key, e.g., `UNIQUE(tenant_id, request_key)`. Compute the payload hash from a canonicalized representation of the business data so identical payloads with reordered JSON fields do not yield different hashes.

### Writing Idempotency in the Same Transaction

Within one transaction:

1. Attempt to insert the request key and request hash.
2. If insertion succeeds, perform the business state changes.
3. Save the response and mark status `COMPLETED`.
4. Commit all changes together.

If the transaction rolls back, both the idempotency record and business changes roll back together. If commit succeeds yet the response is lost, a retry with the same key hits a duplicate key conflict and can read back the stored result.

### Handling Concurrent Duplicate Requests

The unique primary key on `request_key` acts as the synchronization point across concurrent requests. When two instances process the same key simultaneously:

- One transaction inserts the key first.
- The other blocks waiting on the unique constraint check.
- If the first commits, the second receives a duplicate key error.
- If the first rolls back, the second proceeds with insertion.

On a duplicate key error, do not immediately return a generic error. Open a transaction to read the committed idempotency record, compare request hashes, and replay the stored response if the payload matches. If the key matches but the payload hash differs, return a business conflict error.

Never store an `IN_PROGRESS` status in one transaction and execute business logic in a separate transaction unless you have designed leases, timeouts, and recovery sweeps. Otherwise, crashed workers leave requests permanently stuck in progress. For simple synchronous flows, storing key, business changes, and response in one atomic transaction is far easier to keep consistent.

### Idempotency Key Retention

Never delete idempotency records immediately after returning a response. Retention must outlast client retry windows, incident recovery intervals, and any window during which the business can legitimately receive the same request again. Purging keys too early allows replayed old requests to be treated as brand-new transactions. Enforce an explicit retention policy via batched cleanup jobs that never purge keys still under lookup or reconciliation.

## 8. Example Idempotent Flow with JPA

One clean implementation isolates a dedicated transactional writer service:

~~~java
@Service
public class IdempotentOrderWriter {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;

    public IdempotentOrderWriter(
            IdempotencyRepository idempotency,
            OrderRepository orders) {
        this.idempotency = idempotency;
        this.orders = orders;
    }

    @Transactional
    public OrderResult execute(CreateOrderCommand command) {
        IdempotencyRequest request = IdempotencyRequest.started(
                command.requestId(),
                command.payloadHash());

        idempotency.saveAndFlush(request);

        Order order = Order.create(command);
        orders.save(order);

        OrderResult result = OrderResult.from(order);
        request.complete(result.toJson());
        return result;
    }
}
~~~

**saveAndFlush** forces Hibernate to emit the idempotency `INSERT` early so duplicate keys are caught inside the current transaction. It does not commit the transaction. The idempotency record, order, and response still commit or roll back atomically together.

An outer facade handles the existing-key case:

~~~java
public OrderResult handle(CreateOrderCommand command) {
    try {
        return writer.execute(command);
    } catch (DataIntegrityViolationException duplicate) {
        return lookupCompletedRequest(command);
    }
}
~~~

Narrow exception handling in production: treat only duplicate-key violations on the **request_key** constraint as idempotency collisions. Never treat every `DataIntegrityViolationException` as a replayable success, since it might stem from another unique constraint, foreign key, or `NOT NULL` violation.

After catching a constraint error, the failed transaction may already be rollback-only. Query the committed idempotency record through a separate service/transaction outside the failed attempt, and validate the request hash before returning the stored response.

## 9. Handling Indeterminate COMMIT Outcomes

When Connector/J reports a communications failure during commit, you cannot use that same connection to ask whether the transaction committed. Instead:

1. Close the failed connection and let the pool evict it.
2. Acquire a fresh connection.
3. Look up the idempotency key or stable business identifier.
4. If a `COMPLETED` record exists with a matching payload hash, return the stored result.
5. If no record exists, re-attempt the operation using the exact same request key.
6. If status remains unavailable because the original transaction is still finishing or failover is in progress, wait briefly and re-check within the request deadline.

Never generate a new request key to bypass a duplicate key error. Never assume a connection reset implies server rollback.

### For Read Requests

Pure read queries are generally easier to retry when re-execution produces no side effects. Still, subsequent reads may observe newer data. If a request requires a consistent snapshot or deterministic pagination, preserve clear business semantics.

### For Write Requests

Write requests require idempotency or an equivalent outcome-verification mechanism before re-sending. Operations such as order creation, stock deduction, payment capture, invoice issuance, or entitlement grants must carry stable business keys.

## 10. Transactional Outbox for External Side Effects

A database transaction cannot roll back an already-sent email, an HTTP payment charge, or a message already published to a broker.

Avoid doing this:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    orderRepository.save(Order.create(command));
    paymentClient.charge(command.payment());
    emailClient.sendConfirmation(command.email());
}
~~~

If the database transaction rolls back after the external service executed, system state diverges. If the entire method retries, payments or emails execute twice.

Use a transactional outbox:

1. In the same transaction, persist the order and an event row into an outbox table.
2. Commit the database transaction.
3. A background worker reads unpublished events and publishes them or calls external services.
4. Record delivery completion and let the worker retry by event ID.
5. Consumers deduplicate using the event ID.

Minimal example schema:

~~~sql
CREATE TABLE outbox_event (
    event_id BINARY(16) PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
) ENGINE=InnoDB;
~~~

The outbox guarantees event creation commits atomically with business data. It does not guarantee at-most-once broker delivery—a worker can re-publish if it loses the broker acknowledgment. Consumers still require idempotency keyed by event ID.

## 11. Connection Pool and Timeouts in Spring Boot

Spring Boot normally configures a `DataSource` and connection pool such as HikariCP. The pool reuses connections, yet connections can expire due to MySQL, proxies, firewalls, or load balancers.

Properties to evaluate:

| Property | Layer | Role |
|---|---|---|
| `connectionTimeout` | Pool | Maximum wait time to borrow a connection from the pool |
| `maxLifetime` | Pool | Maximum age of a connection before the pool retires it |
| `idleTimeout` | Pool | Idle duration before excess connections may be evicted |
| `keepaliveTime` | Pool | Liveness checks on idle connections when supported by pool version |
| `connectTimeout` | Connector/J | TCP socket connection timeout |
| `socketTimeout` | Connector/J | Socket read wait timeout |
| `innodb_lock_wait_timeout` | MySQL/InnoDB | InnoDB row lock wait timeout |
| Transaction timeout | Spring | Upper bound on transaction duration |

Setting **maxLifetime** shorter than proxy or database connection age limits reduces the risk of handing out connections already closed by infrastructure. Never pick timeouts arbitrarily; measure query durations, proxy idle limits, and server policies before tuning.

### Illustrative Configuration

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.com:3306/app?sslMode=VERIFY_IDENTITY
    username: DB_USER_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      connection-timeout: 3000
      max-lifetime: 1500000
      idle-timeout: 300000
      validation-timeout: 1000
~~~

These values are illustrative only, not universal defaults for every system. In particular, choose `socketTimeout` and transaction timeouts according to SLAs, legitimate query durations, and cancellation mechanisms.

Never embed passwords in source control or logged URLs. Use a secret manager or securely managed environment variables.

## 12. Never Retry Business Rule or Configuration Errors

The following errors normally cannot be fixed by retrying the same request unchanged:

- Unique key violations from invalid input or duplicate requests.
- Foreign key or `NOT NULL` violations.
- SQL syntax errors or references to nonexistent columns.
- Missing `SELECT`/`INSERT`/`UPDATE` privileges.
- Wrong password or incompatible authentication plugin.
- Invalid payloads or data type conversion errors.
- Business state forbidding the action, such as zero stock.

Retrying these errors merely wastes capacity and pollutes logs. Return a clear business error or fix the configuration/code.

### Note on Optimistic Locking Errors

With **@Version** entities, Hibernate detects concurrent modifications. The application may retry if the use case allows reloading fresh state and recomputing the outcome. Never swallow `OptimisticLockException` and re-save the stale entity; doing so risks overwriting another transaction's changes.

## 13. Testing Retries and Connection Loss

Safe retry logic cannot be proven merely by unit-testing a loop. Run integration tests against real MySQL or a production-like environment.

Scenarios to test:

1. Deadlock 1213: transaction rolls back and the next attempt reloads fresh data.
2. Lock wait timeout 1205: application rolls back the full transaction before retrying.
3. MySQL restart before request dispatch: request succeeds once server recovers.
4. Connection closed mid-result read: broken connection is evicted from the pool.
5. Response lost after `COMMIT`: replaying the same request key produces only one order.
6. Two instances receive the same request key concurrently: unique constraint yields only one business outcome.
7. Same request key with a different payload: system returns a conflict error.
8. Outbox worker publishes message then loses response: consumer never processes the event twice.
9. Retries exhausted: application returns a controlled error and logs the correlation ID.

Simulating response loss after commit requires a test harness capable of severing connections at exact points, such as a fault-injecting proxy. Randomly restarting the database does not guarantee exercising the indeterminate commit window.

## 14. Observability and Alerting

Logs and metrics should answer:

- Did the failure occur during connection acquisition, SQL execution, flush, or commit?
- What were the SQLState, vendor code, and root cause?
- Did the request carry an idempotency key?
- Which retry attempt failed?
- How many requests exhausted retries?
- How many requests ended with an indeterminate commit outcome?
- Is the pool exhausting connections or churning new connections continuously?
- Is MySQL experiencing deadlocks, lock wait timeouts, restarts, or failovers?

Metrics to track:

- Error counts by SQLState class and MySQL error code.
- Communications failures per datasource/endpoint.
- Retry rate and retry exhaustion rate.
- Backoff wait time and total request latency.
- Duplicate idempotency key hits and payload hash mismatches.
- Active, idle, pending connections, and connection creation rate.
- Deadlocks, lock wait timeouts, and transaction duration.
- Pending outbox event backlog and oldest unpublished event age.

Never log passwords, access tokens, personal data, or sensitive bind parameters. Use request/correlation IDs to trace logs across APIs, transactions, workers, and external systems.

## 15. Incident Response Procedure

When an application reports connection loss errors:

1. Identify the affected endpoint, instance, timestamp, and network components.
2. Inspect SQLState, vendor code, exception class, and cause chain.
3. Determine whether failure occurred before execute, during execute, at flush, or at commit.
4. Close the broken connection and check pool health.
5. If the transaction clearly rolled back and the error is retryable, re-run the entire use case in a fresh transaction.
6. If commit outcome is indeterminate, look up the idempotency key on a fresh connection.
7. If a `COMPLETED` entry exists with matching payload hash, return the stored result.
8. If no entry exists and time remains within the deadline, retry using the same request key.
9. If state remains unclear, return an indeterminate processing status or instruct the client to query by request ID; never mint a new key.
10. Inspect the database, proxy, network, and connection pool to fix the root cause.

## 16. Deployment Checklist

**Transactions**

- [ ] Retries sit outside transaction boundaries.
- [ ] Every attempt creates a new transaction and fresh persistence context.
- [ ] No retries bypass proxies via self-invocation.
- [ ] Transactions roll back before sleeping for backoff.

**Retries**

- [ ] Only explicitly classified transient errors are retried.
- [ ] Maximum attempt count, jitter, and overall deadline enforced.
- [ ] Never blindly retry communications failures during commit.
- [ ] Data, permission, and schema errors are never retried automatically.

**Idempotency**

- [ ] Every write request carries a stable request key.
- [ ] Request key is backed by a unique constraint in the database.
- [ ] Key, business changes, and response commit in the same transaction.
- [ ] Payload hash verified when a key already exists.
- [ ] Idempotency key retention outlasts retry and business replay windows.
- [ ] External side effects use a transactional outbox or idempotent APIs.

**Operations**

- [ ] Broken connections are evicted from the pool.
- [ ] Timeouts align with SLAs and infrastructure limits.
- [ ] Metrics track retries, communications failures, and pool saturation.
- [ ] Post-COMMIT response loss and concurrent duplicate requests tested.
- [ ] Procedure exists to query outcomes by request ID.

## References

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [MySQL Reference Manual — InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-error-handling.html)
- [MySQL Connector/J — Exception Handling](https://dev.mysql.com/doc/connector-j/en/connector-j-exceptions.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)

## Conclusion

Connection losses in Spring Boot/JPA must be handled according to when they happen and the transaction's state. Deadlocks or lock wait timeouts can be retried after rolling back the full transaction; communications failures during `COMMIT` must be treated as indeterminate until business state is checked. Place retries outside transactions, open a fresh transaction per attempt, bound attempts with jittered backoff, guard writes with idempotency keys, and isolate external side effects with a transactional outbox. Combined with connection pool monitoring and fault-injection testing, applications can recover reliably while preserving business correctness.
