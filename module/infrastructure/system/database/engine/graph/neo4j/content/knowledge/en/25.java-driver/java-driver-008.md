# Classifying Driver, Server, and Transient Errors

A Java application connecting to Neo4j can fail at many points: unable to open a Bolt connection, invalid credentials, invalid Cypher syntax, constraint violations, deadlocks when concurrent transactions contend on locks, or a temporarily unavailable server. These failures require **different handling**. Retrying a syntax-invalid query will not fix the problem, whereas giving up immediately on a brief cluster leader switch makes the application fragile.

This lesson belongs to the **Java Driver** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to store property graphs of nodes, relationships, and properties, query them with Cypher, design indexes/constraints, ingest data, and operate via the Java Driver or Spring Data Neo4j. This lesson focuses on **error classification, deciding whether to retry, managing transaction boundaries, and error observability** in Java applications. Examples use the synchronous API of Neo4j Java Driver 5.26+/6.x; for other versions, check the corresponding API docs, especially methods related to GQLSTATUS.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **error source** (driver/connection vs. server) from **recoverability** (retryable vs. fixing the request).
2. Recognize common exceptions: `Neo4jException`, `ClientException`, `DatabaseException`, `TransientException`, `ServiceUnavailableException`, `SessionExpiredException`, `AuthenticationException`.
3. Inspect `Neo4jException.code()`, GQLSTATUS, and root causes instead of classifying via `getMessage()` strings.
4. Know when to use `executeRead`/`executeWrite` or `Driver.executableQuery()` to leverage automatic retries.
5. Design retry-safe write operations, especially when **it is unclear whether the previous transaction committed**.
6. Log errors, track error counts, and troubleshoot by root cause instead of retrying endlessly.

## 2. Two Classification Axes: Error Source and Retryability

In everyday conversation, errors are often split into "driver errors", "server errors", and "transient errors". One point must be clarified: **"transient" is a recoverability property, not a third mutually exclusive error source**.

~~~mermaid
flowchart LR
    A["Java Application"] --> B["Neo4j Java Driver"]
    B --> C["Network / TLS / Bolt / routing"]
    C --> D["Neo4j Database / cluster"]
    D --> E["Cypher, privileges, constraints,<br/>transactions, resources"]
    B -.-> F["API usage error<br/>or session/result state"]
    C -.-> G["Connection error, timeout,<br/>unreachable address"]
    E -.-> H["Server-returned error<br/>ClientError / TransientError / DatabaseError"]
~~~

| Axis | Category | Examples | Question to answer |
|---|---|---|---|
| **Source** | Driver / application / connection side | Closed session, connection failure, invalid certificate | Must we fix API usage, configuration, or networking? |
| **Source** | Neo4j server side | Invalid Cypher, insufficient privileges, deadlock, database state error | Which status code did the server return? |
| **Recoverability** | **Retryable** | Deadlock, leader switch, recoverable connection drop | At which layer should we retry, and is retrying safe for this operation? |
| **Recoverability** | **Do not retry as-is** | Syntax error, wrong credentials, constraint violation | Which request, data, or configuration must be fixed? |
| **Recoverability** | **Needs investigation** | Persistent internal database error, disk full, broken cluster config | Is operational intervention needed before retrying? |

**Overlap example:** `TransientException` typically represents a transient error from the server, while `ServiceUnavailableException` usually occurs when the driver cannot communicate with the system. Both can be **retryable** according to the driver API even though they originate from different layers.

## 3. Exception Hierarchy in Neo4j Java Driver

Key classes live in `org.neo4j.driver.exceptions`. Most Neo4j errors reported by the driver are subclasses of `Neo4jException`, which is a `RuntimeException`.

| Exception / interface | Source or characteristic | Typical handling |
|---|---|---|
| `Neo4jException` | Base class providing error details, including `code()` when available | Catch at DB access boundaries, classify, and log |
| `ClientException` | Invalid request/operation; can be an error response from the server or improper API usage | Fix Cypher, permissions, data, or resource lifecycle |
| `DatabaseException` | Server reports an internal database problem | Check DB health, logs, resources, and cluster state |
| `TransientException` | Transient error typically detected by the server | Can be retried within bounds when the operation is safe |
| `ServiceUnavailableException` | Driver cannot communicate with the cluster/server | Check connectivity; managed transactions can auto-retry |
| `SessionExpiredException` | Session no longer satisfies initial routing/state conditions, e.g., leader switch | Retry the work on a valid session; leverage managed transactions |
| `AuthenticationException` | Login failed due to invalid credentials | Verify credentials and auth mechanism; do not retry endlessly |
| `ResultConsumedException` | Attempted to use a `Result` that is invalid or already consumed | Fix session/result lifecycle and consumption timing |
| `TransactionNestingException` | Invalid nested transaction usage | Fix transaction call structure |
| `RetryableException` | **Marker interface** for exceptions potentially resolved by retrying | Combine with operation semantics and configured retry policy |

`RetryableException` **is not a parent exception class** and does not mean "retry unconditionally". It is an **exception-level** signal; your Cypher logic and business rules determine whether retrying is actually safe.

Simplified hierarchy of key relationships:

~~~text
RuntimeException
└── Neo4jException
    ├── ClientException
    │   ├── ResultConsumedException
    │   └── TransactionNestingException
    ├── DatabaseException
    ├── TransientException --------- implements RetryableException
    ├── ServiceUnavailableException implements RetryableException
    └── SessionExpiredException ---- implements RetryableException

RetryableException is a marker interface, not a subclass.
~~~

This diagram does not list every driver exception. Class names, constructors, and additional interfaces may change between versions. Never treat every `ClientException` as an "error inside the Java client": **the server also returns a client error** when a Cypher statement is invalid.

## 4. Server Status Codes: Three Main Groups

Neo4j server returns **Neo4j status codes** (strings typically starting with `Neo.`). Examples:

| Server code group | Example | Meaning | Retry the same request? |
|---|---|---|---|
| `Neo.ClientError.*` | `Neo.ClientError.Statement.SyntaxError` | Cypher has a syntax error | **No**; fix the query |
| `Neo.ClientError.*` | Authorization or constraint error | User lacks permissions or data violates a rule | **No** without fixing the root cause |
| `Neo.TransientError.*` | `Neo.TransientError.Transaction.DeadlockDetected` | Transaction aborted due to deadlock | **Yes**, after the prior transaction rolls back |
| `Neo.TransientError.*` | `Neo.TransientError.Transaction.LeaderSwitch` | Cluster leader changed | **Yes**, once routing/leader stabilizes |
| `Neo.DatabaseError.*` | Internal database processing error | Server failed to complete the operation | Investigate first; do not assume retryable |

**Note:** a database error may stem from either a temporary or a persistent condition; never decide to retry simply because the error name contains "database". If a cluster is out of disk or a database cannot start, unbounded retries only add load.

Starting with **Neo4j 5.26+**, the server adds standard **GQLSTATUS** error details; in modern driver/server combinations, exceptions expose `gqlStatus()`, `statusDescription()`, `classification()` or `rawClassification()`, `diagnosticRecord()`, and `gqlCause()`. GQL error classifications include:

- `CLIENT_ERROR`: error caused by client request, permissions, or data.
- `TRANSIENT_ERROR`: potentially transient error.
- `DATABASE_ERROR`: error originating from database state or internal processing.

**Neo4j status codes** and **GQLSTATUS** are two distinct code systems. GQLSTATUS is typically a five-character code such as `42001` or `50N05` that can describe causes in finer detail. Do not conflate them into one arbitrary field, and do not assume every GQLSTATUS is available from older servers.

## 5. Reading Error Codes Properly

Example of intentionally sending a query missing an expression after `RETURN`:

~~~cypher
MATCH (p:Person) RETURN
~~~

When invoked via the Java Driver, this is a **statement error**. With server releases supporting the Neo4j status codes shown, the driver reports:

~~~text
Exception: org.neo4j.driver.exceptions.ClientException
Neo4j code: Neo.ClientError.Statement.SyntaxError
~~~

Status codes are a much more stable basis for classification than **message strings**, because wording can vary across versions, statement offsets, or locales. In Java Driver 6.x:

~~~java
import org.neo4j.driver.exceptions.Neo4jException;

try {
    // Run query through driver/session.
} catch (Neo4jException e) {
    System.err.println("Neo4j code = " + e.code());
    System.err.println("GQLSTATUS = " + e.gqlStatus());
    System.err.println("Classification = " + e.rawClassification().orElse("UNKNOWN"));
    System.err.println("Description = " + e.statusDescription());
}
~~~

This snippet illustrates reading exception fields; it is not a standalone runnable program without replacing the query call. `rawClassification()` returns an `Optional`, because GQL classification is not always present.

### When the Cause Lies Deeper in the GQL Chain

A top-level GQLSTATUS may represent a broad category while the detailed cause sits in `gqlCause()`. To check for a specific code, recent Java Drivers support:

~~~java
catch (Neo4jException e) {
    if (e.containsGqlStatus("42001")) {
        // Example: syntax error, the query needs to be fixed.
        System.err.println("Invalid Cypher syntax");
    } else {
        System.err.println("Neo4j code: " + e.code());
    }
}
~~~

Never classify errors by searching substrings in `getMessage()`, such as `contains("deadlock")`. Also note that GQLSTATUS `50N42` is a **generic fallback code** when the server did not supply a specific GQL error object; do not build business logic depending on this fallback code. GQL APIs and code sets can evolve across Neo4j/driver versions; when supporting multiple versions, maintain fallback branches using `code()` and exception types.

## 6. Error Classification Flow in a Java Application

~~~mermaid
flowchart TD
    A["A Neo4j query fails"] --> B{"Which layer failed?"}
    B -->|"Driver / network"| C["Check URI, TLS, auth, routing,<br/>session/result state"]
    B -->|"Server error"| D["Inspect code + GQLSTATUS<br/>and cause if present"]
    C --> E{"RetryableException?"}
    D --> E
    E -->|"No"| F["Fix query/data/permissions/config;<br/>do not retry the same request"]
    E -->|"Yes"| G{"Is the operation retry-safe?"}
    G -->|"Unclear"| H["Check commit status;<br/>handle via idempotency key"]
    G -->|"Yes"| I["Use managed transaction<br/>or bounded retries"]
    I --> J{"Succeeded?"}
    J -->|"Yes"| K["Return result"]
    J -->|"No"| L["Log, alert,<br/>propagate error to caller"]
~~~

Before deciding to retry, answer three questions:

1. **Can the error resolve itself?** A deadlock after rollback is usually worth retrying; a Cypher syntax error is not.
2. **Is the Driver already retrying?** Calling `executeWrite` has built-in retries; wrapping it in an outer `while(true)` loop easily multiplies attempt counts excessively.
3. **Is re-running the request safe?** A connection drop right at commit time can leave the application **unsure** whether the write persisted.

## 7. Managed Transactions: The Recommended Retry Mechanism

The Java Driver provides `Session.executeRead(...)` and `Session.executeWrite(...)` for running **managed transactions**. When an error is classified as transient by the driver and time remains in the retry budget, the driver can re-run **the entire callback** in a new transaction. `Driver.executableQuery()` also provides managed transaction/retry handling.

Example writing a customer using a **stable business key**:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;

public class CustomerRepository implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public CustomerRepository(
            String uri, String user, String password, String database) {
        Config config = Config.builder()
                .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
                .build();
        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public void upsertCustomer(String customerId, String name) {
        try (Session session = driver.session(
                SessionConfig.builder().withDatabase(database).build())) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:Customer {customerId: $customerId})
                    SET c.name = $name
                    """,
                    Map.of("customerId", customerId, "name", name)
                ).consume();
                return null;
            });
        } catch (Neo4jException e) {
            // Error persists after retry mechanism or is non-retryable.
            System.err.println("Customer upsert failed; code=" + e.code());
            throw e;
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

Key points in this example:

- `Driver` is created once and reused across the component lifecycle; a short-lived `Session` is created per operation. `Driver` is thread-safe, whereas `Session` is **not** thread-safe.
- `MERGE` on `customerId` lets the write **re-run without repeatedly creating duplicate nodes**. The uniqueness constraint guarantees no two nodes share the same key.
- `.consume()` consumes the write result **inside the callback** so query errors surface before exiting the callback.
- `.withMaxTransactionRetryTime(30, TimeUnit.SECONDS)` bounds how long the driver retries a managed transaction. It is not a timeout for **each** Cypher query and does not guarantee success.
- If the callback throws a non-retryable error or the retry window expires, the exception propagates to the caller; outer code should log and handle it according to business policy.
- The example assumes `customerId` and `name` are non-null; `Map.of` forbids null values. Validate inputs before calling the repository.

**Never perform external side effects inside a retryable callback**—such as calling a payment API, sending emails, writing a one-off file, or incrementing global variables. The callback may execute **multiple times** even though the app called `executeWrite` once. When external actions are required, use an **outbox/idempotency** design or trigger them post-commit through a dedicated workflow.

### Differences Across Transaction APIs

| Execution API | Default retry behavior | Key takeaway |
|---|---|---|
| `session.executeRead(...)` | Driver retries errors deemed transient per policy | Use for read transactions |
| `session.executeWrite(...)` | Bounded driver retries on eligible errors | Callback must be safe to re-execute |
| `driver.executableQuery(...)` | Driver handles managed transaction/retries | Good for simple queries; specify the database |
| `session.beginTransaction()`, then `commit()` | **No automatic whole-unit retry** like managed transactions | Developer manually manages lifecycle, rollback, and retries |
| `session.run(...)` (implicit/auto-commit) | **Does not carry the same retry guarantees** as managed transactions | Be especially careful with multi-transaction writes |

Starting in Java Driver **6.1**, implicit transactions have **a single limited retry** for a subset of errors marked idempotent by the server; do not expect that behavior in older versions or other situations. Be especially cautious with `CALL { ... } IN TRANSACTIONS` because earlier batches may have already committed before the overall query fails. Never wrap multi-transaction imports in a blind retry loop.

## 8. Retryable Does Not Mean Safe to Retry

Suppose an application needs to "place an order once":

~~~cypher
CREATE (o:Order {amount: 250000, createdAt: datetime()})
RETURN elementId(o) AS orderId;
~~~

If the server commits but the connection drops **before the client receives the response**, the client cannot know the order was created. Re-running `CREATE` risks creating **two orders**.

Assign a **requestId** at the application layer and enforce uniqueness:

~~~cypher
CREATE CONSTRAINT order_request_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.requestId IS UNIQUE;
~~~

~~~cypher
MERGE (o:Order {requestId: $requestId})
ON CREATE SET o.amount = $amount,
              o.createdAt = datetime(),
              o.status = 'NEW'
RETURN o.requestId AS requestId,
       o.amount AS amount,
       o.status AS status;
~~~

After a connection failure, the application can **re-read by `requestId`** to check whether the earlier request already created the order; if not, it can retry within a bounded policy. This also requires handling **the same `requestId` arriving with a different payload**: never silently return another order's data as success.

For money transfers or multi-system workflows, `MERGE` inside Neo4j alone is **insufficient** for end-to-end exactly-once semantics. You need proper cross-system protocols such as idempotency keys, outboxes, external status checks, and reconciliation.

### When Can Retries Add Extra Load?

| Situation | Risk of unbounded retries | Solution |
|---|---|---|
| Brief deadlock | Threads repeatedly contend | Retry with backoff/jitter and reduce lock contention if needed |
| Prolonged database unavailability | Floods connections and requests | Bound retry duration/count, alert, inspect infrastructure |
| Cypher syntax error | Same error repeats | Fix the statement; do not retry |
| Wrong credentials | Locks out accounts or floods auth errors | Fix configuration/secrets |
| Uniqueness constraint violation | Duplicate key writes cannot succeed | Fix creation logic and update policy |
| Unclear whether commit succeeded | Creates duplicate data or external side effects | Query state by idempotency key before retrying |

Managed transactions already include internal retries and backoff. If you add retries at the HTTP API or job queue layer, **coordinate retry budgets across layers** to avoid multiplying attempts unexpectedly.

## 9. Classifying and Handling Exceptions in Java Code

If you need a central error-handling point, catch `Neo4jException` at the **repository/service boundary** and classify by exception type and status code. The pattern below targets **Java Driver 5.26+/6.x** and expresses policy rather than building an outer retry loop on top of managed transactions:

~~~java
import org.neo4j.driver.exceptions.ClientException;
import org.neo4j.driver.exceptions.DatabaseException;
import org.neo4j.driver.exceptions.Neo4jException;
import org.neo4j.driver.exceptions.RetryableException;
import org.neo4j.driver.exceptions.ServiceUnavailableException;
import org.neo4j.driver.exceptions.SessionExpiredException;

public final class Neo4jErrorPolicy {
    public enum Action {
        FIX_REQUEST, INSPECT_OPERATIONS, RETRY_IF_SAFE
    }

    public static Action classify(Neo4jException error) {
        // Distinguish driver-level retry hint from business semantics.
        if (error instanceof RetryableException) {
            return Action.RETRY_IF_SAFE;
        }
        if (error instanceof ClientException) {
            return Action.FIX_REQUEST;
        }
        if (error instanceof DatabaseException) {
            return Action.INSPECT_OPERATIONS;
        }
        return Action.INSPECT_OPERATIONS;
    }

    public static void report(Neo4jException error) {
        Action action = classify(error);
        System.err.println("exception=" + error.getClass().getSimpleName());
        System.err.println("neo4jCode=" + error.code());
        System.err.println("gqlStatus=" + error.gqlStatus());
        System.err.println("action=" + action);

        // Must handle/rethrow to caller; logging alone is not recovery.
    }
}
~~~

This is a **minimal classifier**, not a retry engine. Specific exceptions may warrant specialized policies based on status code and context—for instance, an expired auth token may require token refresh, whereas a wrong static password requires admin intervention.

**Note:** `ServiceUnavailableException` and `SessionExpiredException` are examples of exceptions implementing `RetryableException`. They are imported here to highlight their existence; general logic should check the marker interface rather than hardcoding only those two classes. On drivers older than 5.0, this marker may not exist: check the API compatibility table for your active version.

## 10. Recognizing Four Common Error Scenarios

### 10.1. Cypher Syntax Error — Fix the Statement

~~~cypher
MATCH (c:Customer)
RETURN
~~~

This illustrates `Neo.ClientError.Statement.SyntaxError`; retrying the same query 10 times still fails. Fix it through dev-time testing/query validation, protecting parameters against Cypher injection, and deploying the corrected query.

### 10.2. Constraint Violation — Fix the Request or Data

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE (:Customer {customerId: 'C001', name: 'An'});
CREATE (:Customer {customerId: 'C001', name: 'Binh'});
~~~

In a clean database, the second statement violates the uniqueness constraint. The application must decide whether to **reject the duplicate**, **update by key**, or **return the existing record**. There is no universal "duplicate error → just retry" rule. You can use `MERGE` on the appropriate key, backed by the constraint, if business rules genuinely allow upserts.

### 10.3. Deadlock — Retryable Server Error

When two transactions write to the same nodes but acquire locks in opposite orders, Neo4j aborts one transaction to break the deadlock. Typical status code:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

In a managed transaction, the driver can re-run the callback after rollback. If deadlocks happen frequently, **reduce contention, enforce a consistent resource access order**, and shrink transaction sizes. Retries help survive brief faults; they do not replace fixing workload structure.

### 10.4. Connection Drop During a Write — Commit Outcome May Be Unknown

Suppose a request reaches the DB, the server commits successfully, yet the client never receives the response due to a network drop. The driver may throw `ServiceUnavailableException` or another connection exception. **Never assume** "an exception means no data was written." Before retrying at the business layer, check the idempotency key or reconcile state whenever the write might have committed.

This is the fundamental reason unkeyed `CREATE`s, sending emails inside transaction callbacks, or posting balances to external systems become dangerous under retries.

## 11. Distinguishing Timeouts and Expired Sessions

Not all "timeout" errors mean the same thing:

| Symptom | Layer | What to check |
|---|---|---|
| TCP connection fails to open | Driver / network | URI, Bolt port, firewall, TLS, and DNS |
| Waiting too long for a pool connection | Driver | Pool size, whether sessions are closed, load, and acquisition timeout |
| Reading from connection takes too long | Driver / network | `ConnectionReadTimeoutException`, long-running query, network path |
| Transaction times out on server | Server | Transaction timeout, lock waits, `PROFILE`, and workload |
| `SessionExpiredException` | Driver / routing / cluster | Session no longer meets initial conditions; leader switch or routing change |

**Do not solve every timeout by raising timeouts.** First determine whether the wait is on connection acquisition, locks, Cypher execution, or result streaming. For instance, a transaction scanning a huge graph likely needs an index or query rewrite; raising timeouts merely hides the bottleneck.

Example separating **transaction timeout** from **retry budget**:

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;
import org.neo4j.driver.TransactionConfig;

Config driverConfig = Config.builder()
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();

TransactionConfig txConfig = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "customer-read"))
        .build();

// driverConfig is passed when creating the Driver.
// txConfig is passed to session.executeRead(callback, txConfig).
~~~

`withMaxTransactionRetryTime` limits total managed transaction retry duration; `TransactionConfig.withTimeout` limits server-side execution time for a single transaction. A transaction timeout **is not automatically retryable in every scenario**; inspect the specific exception and status code.

## 12. Useful Error Logging and Monitoring

Good logs answer **which request failed**, **at which layer**, **with what status code**, and **how the application responded**. At minimum, log:

| Field | Purpose |
|---|---|
| Operation name (`findCustomer`, `createOrder`) | Identifies the business flow |
| Database, deployment region, or service | Pinpoints where the error occurred |
| Exception class and `code()` | Stable classification across driver/server |
| `gqlStatus()`, classification, cause when present | Deep diagnostics on modern driver/server versions |
| Request ID / correlation ID | Correlates application logs with server logs |
| Timestamp, latency, attempt count | Detects prolonged incidents or retry storms |
| Idempotency/commit check result | Prevents duplicate writes when handling network errors |

**Never log passwords, auth tokens, personal data, sensitive Cypher parameter values, or full raw request bodies.** Log only approved technical keys/identifiers. Stack traces belong in properly secured internal logs, never returned verbatim from database errors in HTTP responses to end users.

When Neo4j query logging is enabled, attach transaction metadata to correlate with the application:

~~~java
TransactionConfig txConfig = TransactionConfig.builder()
        .withMetadata(Map.of(
                "app", "customer-service",
                "operation", "upsert-customer",
                "requestId", requestId))
        .build();
~~~

`requestId` should be a secret-free technical identifier. Metadata can appear in query logs or `SHOW TRANSACTIONS`, so it must also comply with your system's data policies.

### Operational Metrics to Track

- Error counts by **exception type**, **Neo4j code**, and **GQL classification**.
- Requests that ultimately failed **after driver retries**; where possible, also track attempt counts at the transaction management layer.
- Repository/endpoint `p95`/`p99` latency and pool wait times.
- Frequency of `ServiceUnavailableException`/`SessionExpiredException` coinciding with cluster state changes.
- Deadlocks, lock timeouts, rollback rates, and Neo4j system load.

Errors at one layer do not always equal failed requests: a managed transaction may hit a transient error and then succeed on retry.

## 13. Practicing Error-Handling Verification

There is no need to induce real failures in production. In a **dedicated practice database**:

1. **Syntax error:** run `MATCH (n) RETURN` and inspect `ClientException`/`code()`, confirming the application does not retry it verbatim.
2. **Constraint:** create a uniqueness constraint on `Customer.customerId` and attempt two nodes with the same key; design a clear business response.
3. **Managed transaction:** run a customer `MERGE` via `executeWrite`, then re-run with the same parameters; verify node count does not grow.
4. **Simulate connection loss:** use an authorized test/chaos environment to interrupt connectivity and observe exception classes, retry behavior, and latency.
5. **Inspect logs:** verify operation name, request ID, and status code are present without leaking credentials or sensitive data.

**For connection-interruption exercises,** if you lack isolated fault-injection infrastructure, document the scenario and write unit tests for your classifier; never disrupt a shared Neo4j instance serving real users just to "trigger a real error".

## 14. Common Design Mistakes

| Mistake | Why is it dangerous? | Fix |
|---|---|---|
| `catch (Exception e) { return null; }` | Swallows errors, turning DB failures into silently missing data | Log properly, map to an appropriate business error, or rethrow |
| Retrying every `Neo4jException` | Loops uselessly on syntax, auth, and constraint errors | Classify by type/status and retryability |
| Infinite retries on top of driver retries | Causes load spikes and latency blowups | Coordinate retry budgets across layers |
| Retrying unkeyed `CREATE` | Risks duplicate writes when commit state is unknown | Use request ID, constraints, and proper upserts |
| Calling HTTP/email inside `executeWrite` callback | Callback may run multiple times | Separate side effects using outbox/idempotency |
| Classifying with `getMessage()` | Message text is unstable | Use `code()`, exception type, and GQLSTATUS |
| Reusing a closed or expired `Session` | Resource state errors | Open a fresh session per operation |
| Sharing a `Session` across threads | Session is not thread-safe | Share `Driver`, create separate sessions |
| Not consuming `Result` when confirming writes | Errors may surface late; implicit commits are hard to observe | Call `consume()` / read all records inside transaction scope |
| Raising all timeouts when queries are slow | Masks index/lock/pool/network issues | Identify the exact timeout type and measure root cause |
| Returning raw stack traces in REST APIs | Leaks query structure and internals | Map to controlled API error responses |

## 15. Self-Practice Exercises

### Exercise 1 — Classifying Four Scenarios

Given four errors:

1. `Neo.ClientError.Statement.SyntaxError`.
2. `Neo.TransientError.Transaction.DeadlockDetected`.
3. `ServiceUnavailableException` when the server is unreachable.
4. `AuthenticationException` on an invalid password.

Identify each error's layer, whether it can be retried immediately or requires fixing config/query, and whether idempotency matters.

<details>
<summary>Reference answer</summary>

1. Server error classified as `ClientError`; fix the Cypher, do not retry.
2. Server `TransientError`; transaction can be retried after rollback, requiring a retry-safe callback.
3. Driver/network communication error; may recover once server/network is back, but you must check commit state if writing.
4. Authentication error; fix credentials/permissions or token issuance; retrying the same invalid credentials is futile.

</details>

### Exercise 2 — Fixing an Unsafe Callback

~~~java
session.executeWrite(tx -> {
    emailService.sendWelcomeEmail(email);
    tx.run("CREATE (:Customer {email: $email})", Map.of("email", email));
    return null;
});
~~~

What risks does this snippet carry if the driver retries the transaction?

<details>
<summary>Suggested answer</summary>

The callback may run multiple times and send duplicate emails; `CREATE` also risks creating duplicate nodes if retried at the application layer after an ambiguous commit. Switch to a design with an identifying key and constraint, write data/outbox records inside the transaction, and send emails post-commit via a worker with an idempotency key.

</details>

### Exercise 3 — Same Exception, Different Decisions

Two requests both encounter `ServiceUnavailableException`:

- Request A: reads a product list with `MATCH`.
- Request B: creates an order with `CREATE` and no `requestId`.

Why should both not be retried with the same unbounded loop?

<details>
<summary>Suggested answer</summary>

Pure reads do not mutate data and are generally safer for bounded retries. Creating an order may have committed before the connection dropped; retrying risks duplicates. Request B needs a request identifier, commit-status checks, and idempotency design. Both need bounded retries to avoid overloading an unrecovered system.

</details>

### Exercise 4 — Comparing Transaction APIs

You are using `session.beginTransaction()` and calling `commit()` manually; on a deadlock, does the system automatically re-run the whole business function like `session.executeWrite()`?

<details>
<summary>Answer</summary>

No. Explicit transactions give manual control, but do not provide the full-callback retry mechanism of managed transactions. You may need to manage a fresh transaction lifecycle and application-level retries with proper budgets and idempotency checks.

</details>

### Exercise 5 — Using GQLSTATUS

An application supports both Neo4j 5.20 and Neo4j 5.26+, and a newer driver exposes `gqlStatus()`. Should error handling rely solely on a single specific GQLSTATUS code?

<details>
<summary>Answer</summary>

No. Older servers may not supply detailed GQL error objects. Handle missing GQL fields, fall back to `code()` and exception types, and verify driver/server compatibility. Never branch on error message text.

</details>

## 16. Official Version-Specific References

- [Neo4j Java Driver Manual — Query error handling and GQLSTATUS](https://neo4j.com/docs/java-manual/current/query-simple/#_error_handling)
- [Neo4j Java Driver Manual — Managed and explicit transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Implicit transactions](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Neo4j Java Driver API — Exceptions package](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/exceptions/package-summary.html)
- [Neo4j Java Driver API — RetryableException](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/exceptions/RetryableException.html)
- [Neo4j — Server errors and classification](https://neo4j.com/docs/status-codes/current/errors/)
- [Neo4j — Status codes catalog](https://neo4j.com/docs/status-codes/current/errors/all-errors/)

The `current` links update with the latest release. When upgrading, verify the **driver version**, **server version**, actual exceptions, and matching APIs. In particular, never assume driver 6.1+ retry policies apply to older driver releases without verifying.

## 17. Key Takeaways

- **Error source and retryability are separate axes**: transient errors can originate from either the server or the connection/driver layer.
- **`Neo4jException.code()`, exception type, and GQLSTATUS** are far more reliable than parsing `getMessage()` strings.
- **`ClientException` usually requires fixing the request**; `TransientException`, `ServiceUnavailableException`, and `SessionExpiredException` may be retried under suitable conditions.
- **`executeRead`, `executeWrite`, and `executableQuery` manage retries**; callbacks must be safe to re-execute, whereas explicit transactions require manual control.
- **Network drops around commit time leave transaction state ambiguous**; design idempotency keys and state checks before retrying writes.
- **Bounding retries and observing real errors** lets systems recover from brief faults without worsening prolonged outages.
