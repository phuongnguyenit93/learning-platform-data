# Connection Validation and Handling Broken Connections

The connection pool in Spring Data R2DBC reuses database connections to avoid the overhead of opening a new connection for every operation. Reuse is only safe when the pool can manage connection lifecycles and detect connections that are no longer usable. In practice, the database can restart, the network can drop, a firewall can close idle connections, or a connection can expire under operational policy. Therefore, the application must understand how to validate connections, evict broken connections, handle mid-query errors, and retry in a controlled manner.

Connection validation is part of a pool management strategy, not a guarantee that every subsequent query will succeed. A connection can be valid at the moment of inspection and break immediately afterward. Proper design coordinates validation, eviction, timeouts, reactive error handling, and retries suited to the business operation's semantics.

## 1. Why Is Connection Validation Needed?

A successfully created connection is not guaranteed to remain usable forever. After being returned to the pool, a connection may sit idle for some time. During that interval, an external component may close it without the pool receiving an immediate signal.

Common reasons a connection becomes stale or broken:

- Database restart, failover, or primary/replica switchover.
- The database closes the session due to idle timeout, resource limits, or administrative policy.
- A firewall, NAT, proxy, or load balancer drops an idle TCP connection.
- Transient network loss, route change, DNS change, or TLS error.
- The database proactively terminates the session for exceeding time or resource limits.
- The driver detects a protocol error, I/O error, or invalid connection state.
- The connection has lived too long and exceeded the lifespan allowed by infrastructure.

If the pool reissues a stale connection, the next statement can fail with errors such as connection closed, connection reset, I/O error, or protocol error. Some failures only surface when the application sends a statement or reads results, so checking before issuing a connection only reduces failure probability rather than eliminating it completely.

Validating before use helps the pool catch some dead connections. Eviction removes connections that are too old or have sat idle too long. When an error happens during execution, the application must let the error propagate properly and let the pool/driver manage the connection lifecycle according to its capabilities.

## 2. Validation Timing and Methods

Validation can happen at different points depending on the pool and driver:

| Method | Timing | Purpose | Cost |
|---|---|---|---|
| Validate on acquire (borrowing) | Before handing the connection to the application | Detect stale connections before use | Can add latency to each connection borrow |
| Validate on release or before returning to pool | After the application returns the connection | Verify state before reuse | Adds work on connection return |
| Background eviction | Periodically while the connection is in the pool | Remove expired-lifetime or long-idle connections | Adds background work and may trigger periodic checks |
| Local validation | When the pool/driver checks object state | Detect closed connections or invalid local state | Usually low, but does not confirm the server responds |
| Remote validation | When needing to confirm the database responds | Detect certain network or server failures | May require a round trip to the database |

Not every pool implements every check point or uses the same defaults. Read the documentation for your exact R2DBC Pool and driver versions. Validation configuration must balance reliability, latency, and database load.

### 2.1. Local Validation vs. Remote Validation

The R2DBC SPI defines `ValidationDepth` to express connection check depth:

- `ValidationDepth.LOCAL`: checks validity on the client/driver side, such as whether the connection state is already closed. This check does not necessarily send a request to the database.
- `ValidationDepth.REMOTE`: checks more deeply to confirm the connection can still communicate with the server as supported by the driver. This may require an I/O operation or round trip.

An SPI-level call looks like:

```java
connection.validate(ValidationDepth.REMOTE);
```

`validate(...)` returns a `Publisher<Boolean>`, not a synchronous boolean. You must subscribe and handle the result inside the reactive pipeline. The driver determines how validation is performed and may have specific limitations. `REMOTE` catches many cases where a connection can no longer communicate, yet it cannot guarantee the connection will remain healthy for the next query.

### 2.2. Validation Query

Some pools allow configuring a lightweight SQL statement to check connections. With PostgreSQL, MySQL, and many other databases, a simple statement like the following is commonly used:

```sql
SELECT 1
```

A validation query executes an actual operation against the database. If the statement does not succeed within the allowed time, the pool can mark the connection invalid and discard it per pool policy.

A validation query should be:

- Lightweight, fast, and not read large amounts of data.
- Free of data modifications or side effects.
- Independent of business tables that might be renamed or dropped.
- Supported by the target database/dialect and driver.
- Paired with an appropriate timeout so a validation check does not hold a connection too long.

`SELECT 1` is a common example, not mandatory syntax across every database. Verify syntax supported by your target database management system.

### 2.3. Avoid Excessive Checking

Running a remote validation query before every SQL statement can increase round trips and reduce throughput, especially when each request already runs a short query. Conversely, skipping checks on idle connections in an environment that frequently drops connections can cause the first requests after idle gaps to fail.

Policies should match infrastructure characteristics:

- If a firewall closes TCP connections after a fixed idle period, set `maxIdleTime` below that threshold and consider validation on acquire.
- If the database enforces a session lifetime limit, set `maxLifeTime` below the operational limit.
- If the network is stable and round trips are costly, rely more on idle/lifetime eviction and only remote-validate where appropriate.
- If the workload is sensitive to first-connection failures after idle gaps, increase acquire-time validation reliability.

## 3. Configuring Validation in R2DBC Pool

R2DBC Pool offers options to limit connection lifetime and validate connections before reuse. In Spring Boot, configuration typically goes under `spring.r2dbc.pool` when pooling is enabled and the required dependency is present.

`application.yml` example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 20m
      max-life-time: 2h
      max-acquire-time: 5s
      validation-query: SELECT 1
```

Meaning of the main properties:

| Property | Meaning |
|---|---|
| `enabled` | Enables or disables the R2DBC connection pool if supported by the Spring Boot version and dependencies |
| `initial-size` | Number of initial connections the pool attempts to create |
| `max-size` | Maximum number of connections the pool can allocate |
| `max-idle-time` | Maximum duration a connection stays idle before becoming eligible for eviction under pool policy |
| `max-life-time` | Maximum lifetime of a connection measured from creation |
| `max-acquire-time` | Maximum time a request waits to borrow a connection from the pool |
| `validation-query` | SQL query used to validate connections if supported by pool/driver configuration |

Property names, value types, and support depend on Spring Boot and R2DBC Pool versions. Inspect configuration metadata and documentation for your running version. Not every low-level builder option has a corresponding property in every Spring Boot version.

### 3.1. Configuring via the R2DBC Pool API

When creating a pool manually, you can configure directly with `ConnectionPoolConfiguration`:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(5)
        .maxSize(20)
        .maxIdleTime(Duration.ofMinutes(20))
        .maxLifeTime(Duration.ofHours(2))
        .maxAcquireTime(Duration.ofSeconds(5))
        .validationQuery("SELECT 1")
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

This example demonstrates common properties in R2DBC Pool. Specific builder methods may differ across versions. If the application already lets Spring Boot auto-configure the pool, do not create an extra manual pool for the same `ConnectionFactory` without making clear which bean `DatabaseClient` uses.

### 3.2. Choosing `maxIdleTime` and `maxLifeTime`

`maxIdleTime` and `maxLifeTime` solve two different problems:

- `maxIdleTime` limits how long a connection goes unused. It helps when firewalls, NATs, or databases enforce idle timeouts.
- `maxLifeTime` limits the total age of a connection, even if it is used regularly. It helps when infrastructure requires periodic connection rotation.

For instance, if the network closes connections after 30 minutes of inactivity, setting `maxIdleTime` below 30 minutes lets the pool evict connections before the network drops them. If the database forces sessions to rotate after a period, `maxLifeTime` should be lower than that limit with a safety margin.

Numbers in examples are illustrative only. Factor in real idle timeouts, network latency, maximum connection count, and new connection creation costs. Setting lifetime too short forces constant creation and destruction; setting it too long gives stale connections more chance to linger.

## 4. Distinguishing Different Types of Timeouts

A system can have several timeouts active at once. Do not treat them as a single property:

| Timeout | What It Bounds | When Expired |
|---|---|---|
| Acquire timeout | Wait time for an available connection in the pool | Connection acquisition request fails |
| Create connection timeout | Time to establish a new connection to the database | Connection creation attempt fails |
| Validation timeout | Time to validate a connection | Validation fails or pool treats connection as invalid |
| Query/statement timeout | SQL statement execution time | Statement times out per driver/database |
| Transaction timeout | Allowed lifespan for a transaction | Transaction is cancelled or rolled back per management mechanism |
| Network/socket timeout | I/O wait time at the network layer | Driver receives an I/O or timeout error |

For example, `maxAcquireTime: 5s` does not mean a SQL query can run for at most 5 seconds. It only caps waiting for a connection from the pool. Once the connection is issued and a query runs for 60 seconds, a query timeout or database-side timeout controls execution duration.

Set timeouts in sensible relation to one another. Validation should not hold a connection too long; acquire timeout should fit the request SLA; query timeout should fit the query class; transaction timeout must cover the business work inside the transaction.

## 5. Eviction and Connection Lifecycle

Eviction is the process of removing a connection from the pool. A connection can be evicted because:

- It exceeded `maxIdleTime`.
- It exceeded `maxLifeTime`.
- Validation failed.
- The driver reported the connection is closed or invalid.
- The pool detected an error during use or release per supported policy.
- An administrator or the application explicitly closed the pool.

Eviction lets the pool gradually replace old connections with new ones. It is especially valuable in environments with database failover, proxies, load balancers, or periodic session termination policies.

Some pools support background eviction, periodically scanning idle connections. Others check only on acquire or release. Do not assume a connection reaching `maxIdleTime` is closed at that exact millisecond; actual timing depends on eviction schedules and pool state.

The pool must be closed on application shutdown to free connections and background resources. In Spring applications, the bean lifecycle normally closes the pool bean when declared properly. If creating a pool outside a container, ensure a dispose/close step runs on shutdown.

## 6. Connections Breaking During Use

Pre-acquire validation cannot prevent every error. A connection can drop right after validation or mid-statement. For example:

1. The pool validates the connection and finds it healthy.
2. The application receives the connection.
3. The network resets or the database restarts.
4. The application sends SQL or reads results.
5. The driver emits an I/O error, connection closed error, or protocol error.

This is a normal scenario to handle in distributed systems. The application must let the error propagate to a layer that can decide whether to return an error to the client, retry, or enqueue work.

### 6.1. Do Not Reuse Known Broken Connections

When the driver or pool determines a connection is invalid, that connection must be removed from reuse. The pool can automatically mark and dispose of the connection in several scenarios, depending on the pool and driver.

For connections obtained manually from `ConnectionFactory`, always manage lifecycle with reactive cleanup. Example using `Mono.usingWhen`:

```java
Mono<Integer> readHealth(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(connection.validate(ValidationDepth.REMOTE))
            .map(valid -> valid ? 1 : 0),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

This example illustrates ensuring cleanup when the publisher completes, errors, or is cancelled. Calling `Connection.close()` on a pooled connection normally returns it to the pool; it does not necessarily close the physical socket. If a connection is known to be broken and must be discarded, use the invalidation/disposal mechanism supported by your specific pool's documentation. The common R2DBC SPI does not define a universal discard API for all pools.

Do not store a `Connection` in a singleton field or cache to reuse across requests. Acquire within the operation scope, execute, and release according to lifecycle. With `DatabaseClient`, Spring manages connection acquire/release for normal operations; the application does not manually close the client's internal connections.

### 6.2. Let Errors Propagate Through the Reactive Pipeline

Do not turn connection errors into fake success results:

```java
// Avoid: hides the error and tricks the caller into thinking the query succeeded.
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

If business logic needs to translate technical errors into application errors, preserve the underlying cause:

```java
return repository.findById(id)
    .onErrorMap(R2dbcException.class, error ->
        new CustomerStoreUnavailableException(
            "Unable to access customer data", error));
```

The web layer can map this error to an appropriate HTTP status, while background processors can log and reschedule according to policy. Do not return empty data when the database is actually unreachable, unless the business contract explicitly specifies that fallback behavior.

## 7. Retrying When Connections Fail

Retries can help for transient errors, but not every database error should be retried. Some errors are permanent configuration or data errors, such as invalid SQL, constraint violations, missing permissions, or bad input data. Retrying those errors only adds load and lengthens response times.

Cases worth considering for retry:

- Brief network resets or transient connection failures.
- Completed database failover where the new node can accept connections.
- Unexpectedly closed connections when the operation can be safely re-executed.
- Certain transient overload errors, with proper backoff and load limits.

Cases requiring caution:

- Query timeouts when the server may still be executing the work.
- Lost connections during transaction commit.
- `INSERT`/`UPDATE` operations with side effects where the client does not know if commit succeeded.
- Constraint, syntax, or permission errors.

### 7.1. Bounded Retries and Backoff

For idempotent read operations, you can use Reactor Retry to attempt a bounded number of retries with backoff:

```java
Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> customerRepository.findById(id))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isTransientConnectionFailure));
}
```

In this example:

- `Mono.defer` creates a fresh read operation on each re-subscription.
- `Retry.backoff(2, ...)` allows up to two retries after the initial attempt.
- `maxBackoff` caps the growing delay.
- `jitter` adds randomness so multiple clients do not retry simultaneously.
- `filter` permits retries only for errors classified as transient.

`isTransientConnectionFailure` is application logic that should inspect exception types, SQL state codes, drivers, and specific database semantics. Never use unbounded `retry()` for arbitrary errors.

### 7.2. Retries and Transactions

If an operation runs inside a transaction, where retry is placed matters greatly. After a connection or SQL failure, the current transaction may already be rolled back or unusable. Retrying inside the same transaction could continue using a broken context or connection.

For safely retryable operations, typically place retry outside the transaction boundary so each attempt starts a fresh transaction:

```java
Mono<Order> createOrder(Command command) {
    return Mono.defer(() ->
            transactionalOperator.transactional(createOrderOnce(command)))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientConnectionFailure));
}
```

This snippet is only safe if `createOrderOnce` ensures idempotency. If the prior attempt committed and the client lost the response, retrying can create a duplicate order. Use an idempotency key, unique constraint, appropriate upsert, or deduplication mechanism to guarantee the same request does not cause repeated side effects.

### 7.3. Ambiguous Commit Outcomes

A dangerous scenario is a connection dropping mid-commit. The application may not know whether the database committed the transaction. Automatically re-sending a write command can execute the business action twice.

Common solutions:

- Generate a unique idempotency key per business request.
- Persist the key alongside the processing result inside the transaction.
- Enforce a unique constraint so the database prevents duplicate processing.
- On retry, look up any existing result by key before creating new records.
- For critical workflows, store processing state and use an outbox/inbox or suitable deduplication mechanism.

Retry is merely re-execution. Idempotency is what makes re-execution safe.

## 8. Classifying Errors Before Retrying or Falling Back

Not every `R2dbcException` is a connection error. Errors can be grouped as follows:

| Error Category | Examples | Typical Handling |
|---|---|---|
| Connection/network | Connection reset, closed connection, I/O failure | Discard broken connection; consider bounded retry if operation is safe |
| Overload/transient | Pool acquire timeout, database temporarily rejecting connections | Backoff, concurrency limits, review load and pool |
| Statement timeout | Statement timeout, query timeout | Optimize SQL or tune timeout; retry only if safe |
| SQL/data | Syntax error, type mismatch, constraint violation | Fix SQL or data; normally do not retry |
| Auth/permissions | Invalid credentials, permission denied | Fix secret or permissions; do not keep retrying |
| Config/protocol | Wrong URL, missing driver, TLS/certificate error | Fix configuration or dependency; do not retry blindly |

SQL state codes can help classification, though exact codes and meanings depend on the database. Do not rely solely on exception message text, which can change across drivers or versions. Inspect the cause chain, exception types, SQL state, and driver documentation.

## 9. Controlling Load When the Pool Has No Healthy Connections

If the database loses connectivity or the pool cannot open new connections, requests begin waiting on acquire and eventually time out. During such an outage, raising `max-size` will not necessarily help: if the database cannot accept new connections, a larger pool only creates extra pressure once the database recovers.

Measures to combine:

- Set `max-size` based on database connection budget and application instance count.
- Set `max-acquire-time` so requests do not wait indefinitely.
- Limit concurrency at the service or API layer to avoid flooding the pool.
- Use a circuit breaker when needed to stop hitting the database during sustained failures, with sensible half-open and recovery windows.
- Use bulkheads or queue bounds so a database outage does not exhaust resources across the entire application.
- Return clear errors or meaningful business fallbacks when the database is temporarily unavailable.

Circuit breakers and retries must be coordinated carefully. Too many retries before a circuit breaker opens amplify load. Keeping a circuit breaker open too long prevents recovery checks even after the database returns. Monitor states and base thresholds on observed latency and error rates.

## 10. Observing Connection Pool Health

To detect broken connections and pool exhaustion before users report errors, monitor both pool metrics and database metrics.

Useful metrics:

| Metric | Operational Meaning |
|---|---|
| Allocated/total connections | Total connections created or managed by the pool |
| Acquired/active connections | Number of connections currently in use by the application |
| Idle connections | Number of connections ready to be issued |
| Pending acquire | Number of requests waiting for a connection |
| Acquire latency | Time from request until a connection is received |
| Creation failures | Number of times the pool failed to create a new connection |
| Validation failures | Number of connections failing validation |
| Evicted/disposed connections | Number of connections removed from the pool |
| Connection lifetime/idle time | Connection age and idle duration |
| Query latency/error rate | Query latency and error rates at application/database layers |

Exact metric names depend on R2DBC Pool, Micrometer, Spring Boot Actuator, and versions in use. Check the actual exported metric list instead of assuming identical names across all pools.

Signals to watch:

- Pending acquire steadily rising: pool may be too small, connections held too long, or database slow.
- Idle at 0 and acquired hitting `max-size`: pool is saturated.
- Validation failures spiking after idle periods: network or database may be closing idle connections.
- Creation failures rising after a database restart: database not yet ready or connection configuration broken.
- Acquire latency rising while query latency is normal: bottleneck likely in pool or connection lifecycle.
- Query latency and lock waits rising together: database likely overloaded or experiencing lock contention.

Alert on sustained trends rather than a single transient validation failure.

## 11. Testing Validation and Broken Connection Handling

Testing should cover both healthy operation and failures encountered across the pool lifecycle.

### 11.1. Basic Validation Testing

With a pool configured with a validation query, run a simple operation via `DatabaseClient` or a repository multiple times, returning the connection between calls, and observe validation/eviction metrics. Verify that connections are recreated when the pool evicts invalid ones.

### 11.2. Simulating Database-Closed Idle Connections

In an isolated test environment:

1. Acquire a connection and execute a successful query.
2. Return the connection to the pool.
3. Use a database admin command or test tool to terminate that session, or configure the environment to expire idle connections.
4. Have the application request the next connection.
5. Verify the pool detects the dead connection, removes it, and creates/issues a new valid connection.

Do not kill sessions in production to test. Use an isolated test environment and identify which session belongs to the test application.

### 11.3. Testing Network Resets or Failover

You can simulate network loss or database restarts in a test environment. Verify that:

- Errors propagate through the reactive pipeline.
- Broken connections are not reused as healthy connections.
- The pool can create new connections once the database recovers.
- Retries are bounded and never enter infinite loops.
- Requests receive appropriate errors or responses while the database is unavailable.
- Transactions and data are not duplicated under retries.

### 11.4. Testing Cancellation and Cleanup

When a subscriber cancels a publisher or a request times out, connections must be released via cleanup paths. If connections stay held, the pool can exhaust even while the database is healthy. Use acquired/idle/pending metrics to verify recovery after completion, error, and cancellation cases.

## 12. Common Design Mistakes

| Practice | Consequence | Fix |
|---|---|---|
| Assuming created connections always stay healthy | Server or network can close connections while idle | Configure suitable validation and eviction |
| Remote validating before every query without measuring | Increases round trips and database load | Choose validation timing suited to workload |
| Treating local validation as proof the server is alive | Local checks do not necessarily probe the network | Use remote validation or validation queries when server reachability matters |
| Setting `max-idle-time` longer than firewall idle timeout | Pool may issue connections already dropped by the network | Set idle time lower than infrastructure limits with a safety margin |
| Not setting an acquire timeout | Requests can wait on the pool indefinitely | Set timeouts per SLA and handle overload |
| Increasing `max-size` on every acquire timeout | Can overload the database further | Measure connection usage, query latency, and connection budget |
| Catching errors and returning `Mono.empty()` | Hides database outages and produces wrong results | Propagate errors or map to clear application exceptions |
| Retrying all exceptions | Loops on permanent errors and adds load | Classify errors and use bounded retries with backoff |
| Retrying non-idempotent writes | Can write data twice when commit outcomes are ambiguous | Use idempotency keys and unique constraints |
| Retrying inside an already broken transaction | May continue using an invalid transaction/connection | Place retries outside the transaction boundary to start fresh |
| Keeping connections in fields or caches | Connections go stale and bypass pool lifecycle management | Acquire and release within the operation scope |
| Skipping cleanup on manual connection acquisition | Connection leaks exhaust the pool | Use `usingWhen` or appropriate resource management APIs |

## 13. Runbook When Detecting Broken Connections

When connection errors occur in production, follow this sequence:

1. **Identify the error class:** capture root cause exceptions, SQL state, driver details, and timestamps.
2. **Check database/network health:** identify restarts, failovers, connection exhaustion, firewall resets, or auth errors.
3. **Inspect the pool:** examine acquired, idle, pending, creation failures, validation failures, and acquire latency.
4. **Let the pool replace bad connections:** verify the driver/pool discards invalid connections; if explicit invalidation is needed, use the API supported by your specific pool.
5. **Throttle incoming requests:** apply acquire timeouts, concurrency limits, or circuit breakers to contain impact.
6. **Decide on retries:** only retry transient errors and safe operations; use backoff, jitter, and bounded attempts.
7. **Resolve uncertain commit outcomes:** for commit-time failures, look up state via idempotency key or business status before re-issuing writes.
8. **Verify recovery:** monitor connection creation, validation failures, pending acquire, and query success after database recovery.

## 14. Configuration Guidelines

- Use validation to reduce the risk of issuing stale connections, while still handling mid-query failures.
- Use local validation for local state and remote validation/validation queries when verifying server communication.
- Pick `maxIdleTime` based on database and network idle timeouts; pick `maxLifeTime` based on session lifespan policies.
- Set acquire timeouts to bound pool wait times; do not confuse them with query timeouts.
- Keep validation queries lightweight, side-effect-free, and compatible with the database.
- Let `DatabaseClient` manage standard connections; if acquiring manually, always clean up on complete, error, and cancel.
- Never reuse known broken connections; use the specific pool's discard mechanism when explicit removal is required.
- Bound retries with backoff, jitter, and transient-error filtering; never blindly retry writes.
- Place retries outside transactions that need to restart on failure and ensure idempotency for side effects.
- Monitor pool, database, and network metrics to tune configuration from real data.

A connection pool enables efficient resource reuse, but operates reliably only when the application manages connection lifecycles and responds properly to failures. Validation, idle/lifetime eviction, and timeouts reduce the odds of issuing stale connections to requests. When failures still happen during execution, reactive error handling, cleanup, bounded retries, and idempotency allow the system to recover without hiding errors or creating duplicate side effects.
