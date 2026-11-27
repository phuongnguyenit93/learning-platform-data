# Testing Uncommon Paths Such as Data Errors, Retries, and Connection Recovery

## 1. Why Error Paths Must Be Tested

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot applications are processed by Spring AOT and compiled into GraalVM Native Image. A business flow may work smoothly when every service is healthy, yet fail when a response is truncated mid-stream, a database restarts, stale connections in the pool expire, or a message is redelivered after a timeout.

These scenarios rarely surface in happy-path tests, yet they determine reliability in production. The native executable also has specific aspects to confirm: DNS/TLS, truststores, native libraries, connection pools, client creation timing, and the ability to re-establish resources after a connection drops.

This lesson focuses on identifying which errors are recoverable, retrying without duplicating business side effects, re-establishing connections, and verifying identical behavior on both the JVM and the native executable.

One overarching principle: **retry an operation only if retrying has a chance to succeed, and only when retrying does not produce duplicate business side effects**.

## 2. Classifying Errors Before Designing Retries

Not every error should be retried. First distinguish data/request errors, configuration/permission errors, transient infrastructure errors, and unknown-outcome errors.

| Error Category | Examples | Retry? | Resolution |
| --- | --- | --- | --- |
| Invalid data | Malformed JSON schema, missing required fields, invalid currency code | No | Return a clear validation error without calling downstream dependencies |
| Business rule violation | Insufficient balance, disallowed order status | No | Return a domain error and apply the appropriate business flow |
| Authentication/authorization | HTTP 401/403, expired credentials, or missing permissions | Usually do not retry blindly | Refresh credentials if a clear flow exists; otherwise fail fast |
| Configuration error | Wrong host, wrong port, untrusted certificate | Do not retry repeatedly | Fix configuration, truststore, or deployment |
| Transient error | Timeout, connection reset, HTTP 503, database failover | Conditionally | Bounded retries with backoff and idempotency |
| Rate limit | HTTP 429 or temporary quota exhaustion | Conditionally | Respect `Retry-After`, bound retries and load |
| Unknown outcome | Client timed out after the server may have committed | Only if the operation is idempotent | Query status or resend with the same idempotency key |
| Programming bug | `NullPointerException`, broken invariant | No | Fix the code; retrying only repeats the bug |

Classify based on exception type, HTTP status, SQLState/vendor code, and operational context. Do not use a blanket rule like "retry every `RuntimeException`" or "retry every HTTP 5xx." Some 5xx errors are deterministic failures, whereas some 4xx codes like 429 are temporary throttling.

### 2.1. Transient Does Not Mean Safe to Retry

A timeout may indicate only that the client did not receive a response within the allowed window. It does not prove the server never executed the operation.

Example:

1. The client sends a payment creation request.
2. The server records the payment successfully.
3. The response is lost on the network.
4. The client times out and resends the request.
5. If the server does not recognize duplicate requests, the customer could be charged twice.

Therefore, retry decisions must consider both **whether the error is transient** and **whether repeating the operation is safe**.

## 3. Handling Data Errors at Integration Boundaries

### 3.1. Validating Structure Before Calling External Services

A request must be validated before producing side effects:

~~~java
public record CreateTransferRequest(
    @NotBlank String sourceAccount,
    @NotBlank String destinationAccount,
    @NotNull @Positive BigDecimal amount,
    @NotBlank String currency,
    @NotBlank String idempotencyKey
) {
}
~~~

Beyond Bean Validation, the domain layer must enforce rules such as distinct source and destination accounts, supported currencies, and amounts within business limits. Do not rely solely on controller validation because message consumers, batch jobs, or internal callers may invoke services directly.

The processing order should be clear:

1. Parse and validate input structure.
2. Verify invariants and business permissions.
3. Normalize data per contract.
4. Create any required idempotency record or transaction.
5. Call the external service.
6. Persist results and return the response.

Invalid requests must be rejected before calling providers, recording transactions, or publishing messages.

### 3.2. Malformed or Incomplete Responses

Do not assume external systems always return schema-compliant payloads. Cases to verify:

- empty response when the contract requires a body;
- syntactically valid JSON missing a required field;
- new enum value unknown to the client;
- decimal numbers exceeding precision limits or wrong scale;
- timestamps lacking a timezone;
- invalid character encoding;
- truncated responses or mismatched content length;
- repeating pagination cursors causing infinite loops.

Distinguish parse/schema errors from transient network errors. A schema-invalid response usually belongs in a dead-letter queue/quarantine or should raise an integration error; retrying the same payload rarely fixes bad data.

### 3.3. Partial Failure

A request may complete partially. For instance, in a batch of 100 records, 97 succeed and 3 fail. Retrying the entire batch could reprocess the 97 already-succeeded records.

Proper design:

- track outcomes per item;
- use a business key/idempotency key per item;
- persist success/failure status individually;
- retry only recoverable failed items;
- bound retry attempts and store the final failure reason.

For multi-step workflows, consider sagas/compensation or outbox/inbox patterns instead of trying to wrap multiple independent systems into a single retry.

## 4. Designing Bounded Retries

A retry policy should answer these questions:

- Which exceptions/statuses are retried?
- What is the maximum number of attempts, including the initial call?
- How long is the wait between attempts?
- Are exponential backoff and jitter applied?
- What is the overall request deadline?
- Is the operation idempotent?
- Once retries are exhausted, do we return an error, fall back, or enqueue for later?

No single retry policy fits every dependency. Retries for read queries may differ from writes, and retries against a database may differ from retries against a payment provider.

### 4.1. Exponential Backoff

One way to compute progressively increasing wait intervals:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where:

- \(d_0\): initial wait duration;
- \(n\): retry attempt number;
- \(d_{\max}\): maximum wait cap.

If many instances retry at the exact same moment, they can create a synchronized traffic spike against the dependency. **Jitter** adds randomness to wait durations to spread out attempts.

A common full-jitter formula:

\[
w_n \sim U(0,\min(d_{\max}, d_0 \times 2^{n-1}))
\]

Actual wait times must fit within the overall deadline. If a request only has 100 ms remaining while the planned backoff is 500 ms, do not keep retrying and return a late response.

### 4.2. Limiting Attempts and Retry Budgets

For example, an operation allows at most 3 attempts: the initial call plus 2 retries. If all 3 fail, return the final error or transition to a defined asynchronous handling flow.

A retry budget can cap total retries per dependency or time window. When a dependency is degraded, budgets prevent retries from exhausting application threads, connections, and CPU.

Do not stack multiple retry layers without calculating total attempts. For example, 3 retries in an HTTP client, 3 retries in a service, and 3 retries in a gateway can multiply into up to 27 calls to the target system.

### 4.3. Respecting Deadlines and Timeouts

Each attempt must have a timeout less than or equal to the remaining time budget of the request. Distinguish:

- connect timeout: time to establish a connection;
- response/read timeout: time waiting for data;
- pool acquisition timeout: time waiting to acquire a connection;
- operation deadline: overall limit for the entire operation, including retries and backoff.

The overall deadline should propagate across layers where supported by clients/frameworks. Configuring only per-attempt timeouts without an overall deadline lets a request stretch much longer than intended.

## 5. Idempotency for Write Operations

### 5.1. Idempotency Keys

Clients send a stable key for the same business intent:

~~~http
POST /transfers
Idempotency-Key: 9b77d1a2-transaction-104
Content-Type: application/json
~~~

The server persists the key alongside its state and result:

| State | Behavior When Receiving the Same Key Again |
| --- | --- |
| Key not yet seen | Create record and process for the first time |
| In progress | Return in-progress status or appropriate contract response |
| Succeeded | Return the stored result |
| Permanently failed | Return the stored error without repeating side effects |
| Same key with different payload | Reject because one key represents one unique intent |

Keys must have an appropriate uniqueness scope, such as tenant + operation + key. Store a payload fingerprint to detect cases where a client reuses a key with different content.

### 5.2. Idempotency Is More Than an In-Memory Key Check

In multi-replica applications, an in-memory map inside one process is insufficient. Idempotency records must live in shared storage with appropriate uniqueness constraints/transactions.

For payment or order-creation systems:

- write the idempotency record and business state inside a transaction;
- use a unique constraint to guard against two concurrent requests with the same key;
- store enough result data to replay on subsequent calls;
- set retention matching the window during which clients may retry;
- avoid storing unnecessary sensitive data.

If an external provider supports idempotency keys, forward the same key across all retry attempts. Never generate a fresh key per attempt.

## 6. HTTP Client and External Service Retries

### 6.1. Choosing Retryable Errors

Examples that may warrant conditional retries:

- connection reset before receiving a response;
- connect/read timeouts;
- HTTP 502, 503, or 504 when permitted by the provider contract;
- HTTP 429 following `Retry-After` or quota policy;
- transient DNS errors verified to be recoverable.

Do not retry automatically:

- HTTP 400 caused by an invalid payload;
- HTTP 401/403 without a valid credential-refresh step;
- HTTP 404 when the resource genuinely does not exist in business terms;
- response validation/schema errors;
- TLS certificate/hostname mismatches;
- endpoint or protocol configuration errors.

Some providers follow different conventions. Rely on the provider's contract and specific error codes, not solely on status-code classes.

### 6.2. Respecting Retry-After

When a server returns HTTP 429 or 503 with a `Retry-After` header, the client should honor that value if it fits within the deadline and policy. The header may express seconds or an HTTP date. If the wait exceeds the deadline, fail fast or switch to asynchronous handling rather than holding the request indefinitely.

### 6.3. Example Resilience4j Retry Configuration

Example configuration for a data-reading adapter:

~~~yaml
resilience4j:
  retry:
    instances:
      archiveRead:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        enable-randomized-wait: true
        randomized-wait-factor: 0.5
        retry-exceptions:
          - java.io.IOException
        ignore-exceptions:
          - com.example.billing.InvalidDocumentException
~~~

This is an illustrative configuration; verify property names and dependency integration for your Resilience4j version. `max-attempts` typically includes the initial call. Adjust the exception list to match the actual client and avoid retrying every I/O error if it could indicate a permanent misconfiguration.

Place retries at the adapter boundary so policies stay tied to specific dependencies. For write operations, enable retries only when idempotency or outcome-lookup mechanisms exist.

### 6.4. Do Not Retry Inside Every Layer

If the service calls an adapter, the adapter retries, and a gateway also retries, total attempts can grow exponentially. Designate one retry owner per dependency and clearly document maximum attempts, overall deadline, retryable errors, where idempotency keys are stored, and exhaustion behavior.

## 7. Database Connection Recovery

### 7.1. Connection Pools Can Hold Dead Connections

Spring Boot applications typically use a connection pool such as HikariCP. During a database failover, restart, or network interruption, a borrowed connection may become unusable. The pool must detect and evict broken connections; the application must also handle failures of in-flight operations.

Do not assume simply calling `getConnection()` again recovers any transaction. The old connection may already be broken, the transaction may have rolled back, or the commit outcome may be unknown.

### 7.2. Environment-Appropriate Pool Configuration

Examples of Hikari properties commonly reviewed:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      maximum-pool-size: 10
~~~

These values merely illustrate configuration syntax, not universal recommendations. Choose `maxLifetime` shorter than any connection limit enforced by the database, proxy, or load balancer, and set `keepalive` to fit infrastructure limits. Never set `keepalive` greater than or equal to `maxLifetime`. Check support and applicability for your HikariCP version.

Validation normally occurs when the pool needs to verify a connection; do not enable a custom validation query mechanically when the driver already supports JDBC validation. Monitor pool active/idle/pending counts and timeouts to diagnose issues.

### 7.3. Retrying a Transaction as a Fresh Unit

When a connection fails mid-transaction, do not continue using the broken transaction/connection. If the operation can be retried safely, the next attempt must run inside a fresh transaction.

One way to structure this is an outer layer coordinating retries while a separate bean executes the transaction:

~~~java
@Service
class TransferFacade {

    private final Retry retry;
    private final TransferTransaction transaction;

    TransferFacade(Retry retry, TransferTransaction transaction) {
        this.retry = retry;
        this.transaction = transaction;
    }

    TransferResult transfer(TransferCommand command) {
        return Retry.decorateSupplier(
            retry,
            () -> transaction.execute(command)
        ).get();
    }
}

@Service
class TransferTransaction {

    @Transactional
    public TransferResult execute(TransferCommand command) {
        // Read state, verify invariants, and persist changes
        // within a new transaction for this attempt.
        return performTransfer(command);
    }
}
~~~

This structure illustrates Resilience4j `Retry` combined with a Spring transaction proxy. `TransferTransaction` is a separate bean so calls pass through the `@Transactional` proxy; do not call transactional methods via self-invocation inside the same object. Configure appropriate transaction propagation and ensure no outer transaction wraps the entire retry loop.

Do not retry constraint violations, invalid data, or business errors. For commit failures with unknown outcomes, query by idempotency/business key before rerunning.

### 7.4. Classifying SQL Errors

Spring translates many JDBC exceptions into the `DataAccessException` hierarchy. You may consider retrying certain transient errors such as temporary connection failures, deadlocks, or serialization failures depending on the specific database.

Do not blindly retry all `DataAccessException` instances. For example, a unique constraint violation is usually deterministic; immediately rerunning the same statement will not clear it. Rely on SQLState/vendor codes and driver exception translation.

For deadlocks/serialization failures, retries must rerun the entire transaction to reread data and recompute business decisions. Never replay only the final SQL statement inside a failed transaction.

## 8. Recovering HTTP, Message Broker, and SDK Connections

### 8.1. Create Clients Once, Recover Transport Properly

HTTP clients, database pools, and message broker clients typically manage internal connection pools/event loops. Do not create a new client per request just to work around connection errors. Doing so leaks sockets, increases threads, and multiplies handshakes.

Instead:

- use client beans with clear lifecycles;
- configure connect/read timeouts and pool eviction;
- let the client evict broken connections through the library's API;
- apply retries at the operation boundary with deadlines;
- close clients on `ApplicationContext` shutdown;
- monitor connection pools and reconnect errors.

If an SDK does not support safe automatic reconnect, determine whether to recreate the client or restart the integration component. Never call `close()`/`reconnect()` concurrently from multiple threads unless the vendor guarantees thread safety.

### 8.2. Message Brokers and Redelivery

Message brokers commonly provide at-least-once delivery. A consumer may finish processing and crash before acknowledging; the broker redelivers the message.

Consumers must be idempotent:

- use a message ID or business key to record processed messages;
- commit data changes and the inbox/processed marker in the same transaction when possible;
- acknowledge only after durable work completes;
- distinguish transient errors from poison messages;
- bound redeliveries and route unprocessable messages to a dead-letter queue.

Do not retry poison messages indefinitely. A schema-invalid payload will fail on every redelivery and can stall a partition/queue.

### 8.3. Outbox/Inbox for Multi-System Side Effects

When a database transaction needs to emit an event, use a transactional outbox to write business state and the event in the same transaction. A publisher delivers the event afterward; the consumer uses an inbox/idempotency check to prevent duplicate processing.

An outbox does not create exactly-once delivery across all systems. It ensures events are persisted atomically with transactions and can be republished; consumers still must handle duplicates safely.

## 9. Circuit Breakers, Bulkheads, and Fallbacks

Retries help during brief glitches. If a dependency stays unreachable for an extended period, continuous retries only amplify load and prolong requests.

### 9.1. Circuit Breakers

A circuit breaker tracks dependency call outcomes:

- **Closed:** lets requests pass through and records outcomes.
- **Open:** short-circuits calls for a cooldown period once failure rates cross a threshold.
- **Half-open:** permits a few probe calls to verify whether the dependency has recovered.

Retries and circuit breakers solve two different problems. Retries handle transient glitches within one operation; circuit breakers stop many operations from hammering a degraded dependency.

### 9.2. Bulkheads

Bulkheads cap concurrent requests to a dependency. When a provider slows down, waiting threads/connections cannot grow without bound. Concurrency limits, queues, and timeouts must match the external system's real capacity.

### 9.3. Fallbacks Must Preserve Semantics

Valid fallbacks include:

- returning cached data clearly marked as stale when business rules allow;
- queuing a command for asynchronous processing;
- returning a pending status;
- failing gracefully with a retryable error code for the caller.

Never return a fake success response when side effects have not completed. For example, do not report "paid" merely because the payment provider timed out. Return an unknown/pending state and provide a way to query status.

## 10. Testing Errors and Recovery with Fault Injection

Happy-path tests do not reproduce rare network and system conditions. Use fault-simulation tools at integration boundaries:

| Tool/Technique | What It Can Simulate |
| --- | --- |
| WireMock or MockWebServer | HTTP 429/503, timeouts, connection closes, schema-invalid responses |
| Testcontainers | Starting real databases/brokers in containers, stopping and restarting services |
| Toxiproxy | Latency, bandwidth limits, resets, timeouts, and dropped links between two components |
| Fault injection in test doubles | Per-attempt failures: fail on attempt 1, succeed on attempt 2; repeated errors; partial responses |
| Chaos tooling in test environments | Pod restarts, network disruptions, unavailable dependencies |

Fault injection should remain controlled: test environments, isolated data, bounded timeouts, and clean teardown. Never run destructive connection-breaking experiments in production without an approved process.

### 10.1. Testing Controlled Retries

Example HTTP stub returning 503 twice followed by 200:

~~~java
stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs(Scenario.STARTED)
    .willReturn(aResponse().withStatus(503))
    .willSetStateTo("second-attempt"));

stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs("second-attempt")
    .willReturn(aResponse().withStatus(503))
    .willSetStateTo("available"));

stubFor(get(urlEqualTo("/documents/doc-1"))
    .inScenario("temporary-outage")
    .whenScenarioStateIs("available")
    .willReturn(okJson("{\"id\":\"doc-1\"}")));
~~~

The test verifies that the operation ultimately succeeds, attempt counts match policy, total completion time stays within the deadline, and no extra requests occur after success.

In unit tests, inject a fake `Clock`, `Sleeper`, or scheduler to avoid waiting in real time. In integration tests, use short wait durations while still asserting attempt counts and deadlines.

### 10.2. Testing That Permanent Errors Are Not Retried

Stub HTTP 400 caused by an invalid payload. Assert that the client makes only one call, returns the appropriate validation/integration error, and creates no extra side effects.

### 10.3. Testing Timeouts After Server Commit

Simulate a server executing the side effect but dropping the response. The client times out and retries with the same idempotency key. Assert that only one transaction is created and the retry receives the stored result.

### 10.4. Testing Database Restarts

With Testcontainers or Toxiproxy:

1. Start the database and application.
2. Execute a successful query.
3. Stop the database or sever the connection.
4. Invoke operations while the database is unavailable.
5. Restart the database.
6. Confirm the pool evicts broken connections, new operations reconnect, and data remains consistent.

Do not check only for a "reconnected" log line. Execute a real business operation after recovery.

## 11. Specific Testing on Native Image

The native executable must be tested in an environment close to the deployment target. JVM integration tests do not fully validate native behavior because runtimes, TLS, DNS, reflection, class initialization, and native libraries can differ.

Categories to exercise on native:

- startup while a dependency is unavailable;
- retries after connection resets and timeouts;
- reconnecting to databases/brokers after restarts;
- TLS handshakes and truststores/CA bundles;
- schema-invalid HTTP responses and boundary data;
- connection pools after idle periods;
- graceful shutdown while requests or messages are in flight;
- native libraries/drivers using JNI or service loading.

### 11.1. Configuration Must Be Read at Runtime

Environment-specific endpoints, credentials, timeouts, regions, and trust material must be supplied at runtime. Do not open database connections, HTTP connections, or read secrets during static initializers/AOT processing.

Verify:

- no credentials appear in generated code or the image heap;
- environment variables/config trees bind properly in the native executable;
- CA/truststore files are packaged or mounted as designed;
- paths and read permissions are correct inside the container;
- no dependence on local files existing only on the build machine.

### 11.2. Native Image and TLS

If the JVM connects over HTTPS while the native executable hits trust/certificate errors, check:

- whether the CA certificate is in the truststore used by the native runtime;
- whether a custom truststore is supplied at runtime;
- whether DNS/hostname/SNI matches the certificate;
- whether the certificate chain and validity period are valid;
- whether the library's SSL configuration requires extra resource metadata or native support.

Never disable hostname verification or trust all certificates to "fix" a failing test. Fix the trust chain and certificate configuration properly.

### 11.3. Running Identical Scenarios on JVM and Native

Keep the same contract suite and test data. Run once against the JVM artifact and once against the native executable with matching dependency versions and equivalent configuration. Record differences:

| Observation | JVM | Native |
| --- | --- | --- |
| First call after dependency restart | Succeeds/fails per policy | Succeeds/fails per same policy |
| Retry count | Actual count | Actual count |
| Overall deadline | Measured duration | Measured duration |
| Business outcome | Record/state | Record/state |
| Reconnect | Pool/client recovers | Pool/client recovers |
| TLS and resources | Certificates/resources found | Certificates/resources found |

Compare results and correctness before comparing performance. Fast native startup cannot compensate for a retry policy that produces duplicate transactions.

## 12. Observing Retries and Recovery in Production

Each dependency should have dedicated metrics:

- initial call counts and retry counts;
- retry counts by exception/status;
- exhausted retries;
- circuit breaker states and transitions;
- request latency and deadline exceeded counts;
- connection pool active/idle/pending/timeout counts;
- reconnect successes/failures;
- message redeliveries and dead-letter counts;
- idempotency duplicate hits/conflicts.

Logs should include correlation ID, operation ID, dependency name, attempt number, elapsed time, and error category. Never log tokens, passwords, payloads containing personal data, or connection strings with credentials.

Continuously climbing retry metrics may signal a degraded dependency or overly aggressive timeouts. If you measure only final request success rate, retry storms can stay hidden because users still get responses while the system generates heavy extra load.

## 13. Common Design Mistakes

| Practice | Consequence | Fix |
| --- | --- | --- |
| Retrying every exception | Repeats validation, auth, and code bugs | Allowlist transient errors |
| Retrying writes without idempotency | Creates duplicate transactions/side effects | Use idempotency keys and durable state |
| Unbounded retries | Exhausts threads, connections, and queues | Cap attempts, deadlines, and retry budgets |
| Fixed backoff across all instances | Many clients retry simultaneously | Use exponential backoff and jitter |
| Retrying across multiple layers | Amplifies call counts | Assign one retry owner per dependency |
| Continuing a failed transaction | Uses an invalid connection/transaction | Start a new transaction per attempt |
| Creating a new HTTP client on every error | Leaks sockets/threads, adds handshakes | Manage client lifecycle and pools |
| Acking messages before commit | Loses messages if process crashes | Acknowledge after durable work completes |
| Retrying poison messages forever | Blocks queues/partitions | Bound redeliveries and dead-letter |
| Fake-success fallbacks | Callers believe side effects completed | Return pending/unknown and provide status lookup |
| Testing only mocked happy paths | Misses network/metadata failures | Run fault injection and native contract tests |

## 14. Incident Handling Workflow for Connectivity Issues

When a dependency becomes flaky, follow this sequence:

1. **Classify the error:** determine whether it is a timeout, reset, 429, 5xx, TLS error, auth error, or data error.
2. **Determine business state:** check whether the operation may have committed; query by business key/idempotency key if needed.
3. **Inspect retry policy:** attempts, backoff, jitter, deadline, and retry budget.
4. **Inspect client/pool:** are dead connections evicted, does the pool have capacity, and does the client support reconnect?
5. **Restore the dependency:** verify DNS, network, TLS, database/broker, and credentials.
6. **Run a fresh operation:** use a valid transaction/connection and the same idempotency key when retrying the same intent.
7. **Verify the outcome:** confirm data committed, messages acked, and no duplicate side effects occurred.
8. **Record root cause:** metrics, attempt counts, recovery time, and final error.

Do not mark an incident resolved solely because a health check returns 200. Confirm that the actual business flow can read/write through the dependency.

## 15. Pre-Release Checklist

- [ ] Errors are classified into permanent, transient, or outcome-unknown.
- [ ] Data validation runs before any side effects.
- [ ] Schema-invalid/partial payloads have explicit handling.
- [ ] Retries apply only to recoverable errors.
- [ ] Attempt counts, backoff, jitter, deadlines, and retry budgets are bounded.
- [ ] HTTP 429/503 responses honor `Retry-After` per contract.
- [ ] Write operations have idempotency keys or outcome-lookup mechanisms.
- [ ] Transaction retries execute in fresh transactions.
- [ ] Database pools/clients have proper lifecycles and timeouts.
- [ ] Message consumers handle duplicates, redeliveries, and poison messages.
- [ ] Circuit breakers/bulkheads/fallbacks preserve business semantics.
- [ ] Fault injection has tested timeouts, resets, unavailability, bad responses, and dependency restarts.
- [ ] Identical scenarios have been executed on both JVM and native executable.
- [ ] Native runtime reads endpoints, secrets, CAs, and config from runtime sources.
- [ ] Metrics exist for retries, exhaustion, reconnects, pools, and dead letters.
- [ ] Logs contain no credentials or sensitive payloads.

**Key Takeaway:** Error paths must be designed and tested as part of the integration contract. Classify errors first, retry with deadlines and idempotency, start fresh transactions/connections when needed, and verify business state after recovery. Run a fault-injection suite against the native executable in a production-like environment to uncover differences that JVM tests cannot prove.

## References

- [Spring Framework — Data Access and Transaction Management](https://docs.spring.io/spring-framework/reference/data-access.html): exception translation and transaction management.
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource and connection pool configuration.
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): attempts, interval functions, and retry configuration.
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): closed/open/half-open states and call limiting.
- [Testcontainers for Java](https://java.testcontainers.org/): testing with real databases, brokers, and dependencies in containers.
- [Toxiproxy](https://github.com/Shopify/toxiproxy): simulating network errors, latency, and connection interruptions.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata required for reflection, resources, and dynamic accesses.
