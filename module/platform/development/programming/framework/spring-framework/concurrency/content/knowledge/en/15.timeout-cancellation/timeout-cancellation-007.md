# Setting Dedicated Timeouts for Database Access or Network Calls

> **Module:** Spring Framework – concurrency  
> **Parent topic:** Timeouts and Cancellation  
> **Goal:** Understand why timeouts on `Future`, `CompletableFuture`, `@Async`, or inbound HTTP requests **do not replace I/O operation timeouts**; design dedicated timeouts for acquiring connections, running SQL, and making HTTP calls; and coordinate with overall deadlines, task cancellation, transactions, retries, and monitoring in Spring applications.

## 1. The Most Important Rule: Place Timeouts Where Resources Are Waited On

An endpoint or `@Async` worker may be waiting on:

- A free worker in the thread pool, or waiting for the job to be dequeued.
- Borrowing a `Connection` from a JDBC connection pool.
- Establishing TCP/TLS to the database, sending SQL, waiting for query results, or waiting on socket reads.
- Opening a connection to an HTTP service, waiting for a response, and reading data.
- Waiting for a `CompletableFuture` to complete on the caller side.

These are **different wait points**. Setting `future.orTimeout(2, TimeUnit.SECONDS)` only changes the observed state of the future upon expiration; it does not prove a blocking JDBC statement or HTTP request was stopped. The worker may still hold the connection and continue I/O while the caller has already received a timeout.

**Principle:** Enforce limits at the layer **executing the actual operation** (JDBC driver/SQL statement, HTTP client, network stack), while also enforcing an **end-to-end deadline** at the business layer to avoid continuing useless steps past expiration. The two kinds of limits complement each other; one cannot replace all the others.

## 2. Diagram of Timeout Layers in a Spring Job

Example flow fetching an order status from the DB and then calling another system:

~~~text
HTTP request / job handler -- [overall business deadline]
        |
        v
Spring @Async / ThreadPoolTaskExecutor
        |-- queue wait: task may not have started yet
        v
DataSource.getConnection()
        |-- connection-pool acquisition timeout
        |-- JDBC driver connect/login timeout when creating a connection
        v
JdbcTemplate.query(...)
        |-- Statement / query timeout
        |-- JDBC socket read timeout
        |-- database-side statement/lock timeout (if configured)
        v
HTTP client calling dependent service
        |-- TCP connection timeout
        |-- response/request timeout
        |-- connection-pool acquisition, read/write/idle timeout per library
        v
Process result and return response
        |
        +-- Future/CompletableFuture timeout on the caller
~~~

**One timeout does not automatically bound all stages beneath it.** For example, `HikariCP.connectionTimeout=500ms` does not mean a `SELECT` after acquiring the connection also runs for at most 500ms. Likewise, `HttpClient.connectTimeout=400ms` only limits establishing a **new connection**, not the entire time the server takes to process the request and return data.

Interpreting a timeout error requires identifying **which mechanism expired**. A connection-acquisition failure differs from an SQL query timeout, and both differ from a remote HTTP timeout. Without distinguishing them, the system may retry inappropriately or enlarge pool sizes while the true cause lies in the DB or remote server.

## 3. Budget Timeouts by Time Allocation, Not One Single Number

Suppose a business request must complete within roughly **3 seconds**. An illustrative allocation might budget:

| Wait segment | Example duration | Layer where applied |
| --- | ---: | --- |
| Borrowing connection from pool | 250 ms | HikariCP `connectionTimeout` |
| Executing SQL | 800 ms | JDBC `Statement.setQueryTimeout` (second resolution) or appropriate database-side timeout |
| One HTTP call after DB | 1,200 ms total | HTTP client request/response timeout; connect falls **within** the HTTP budget |
| Remaining buffer | 750 ms | Serialization, scheduling, logging, unusual load, timing variance |

These values are **budgeting examples only**, not hardcoded recommended settings. `Statement.setQueryTimeout` takes **whole seconds**, so 800ms cannot be passed directly to it; if sub-second limits are needed, use a DB/driver-specific solution or design appropriate deadlines. Each driver's documentation governs resolution and actual cancellation behavior.

Do not add `connectTimeout` and request timeout as two independent durations if the request timeout **already covers** the connection-establishment phase. Also, do not equate the sum of configured timeouts with a hard time guarantee: DNS, scheduling, rollbacks, drivers, and external systems can behave differently.

Represent the deadline on each request as an **expiration instant** (using a monotonic clock when measuring durations within the same JVM). Before each remaining step, check remaining time; do not start a call that no longer has a valid chance to finish in time.

## 4. JDBC: Connection Acquisition Timeout Differs from SQL Execution Timeout

When using Spring with `DataSource`/HikariCP, multiple limits typically apply:

| Mechanism | Controls | Does not control |
| --- | --- | --- |
| HikariCP `connectionTimeout` (ms) | Maximum wait time to **borrow** a connection from the pool when none is available | How long an SQL statement runs after borrowing |
| HikariCP `validationTimeout` (ms) | Time allowed to check connection liveness during validation | Business query timeout |
| JDBC driver connect/login timeout | Connecting or logging into the DB, per driver | SQL running on an already-established connection |
| JDBC `Statement.setQueryTimeout(seconds)` | Wait time for statement execution per JDBC and driver support | Time spent waiting earlier for the pool to hand out a connection |
| JDBC driver socket read timeout | Time spent reading from the DB socket per driver (typically per read operation) | Not necessarily equivalent to query timeout or transaction timeout |
| Database statement/lock timeout | Limit enforced by the DB server on statements/locks per engine | HTTP calls happening outside the DB |
| Spring transaction timeout | Time for the transaction when supported by the transaction manager and participating operations are properly wired | Not a master switch to cancel all HTTP/network operations |

Example: a pool has 10 connections, all occupied by 10 long queries. The 11th task may wait until `connectionTimeout` and fail **without executing a single SQL statement**. Even with `JdbcTemplate.setQueryTimeout(2)`, that 2-second SQL limit does not fix waiting to acquire a connection.

Conversely, when a connection is obtained immediately but a `SELECT` runs slowly, the pool acquisition timeout does not bound that query. You need query/statement/server timeouts.

## 5. HikariCP: Setting Connection Wait Time in Spring Boot

If the project uses **Spring Boot + HikariCP**, you can configure pool acquisition timeout with Boot properties:

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 500
      validation-timeout: 400
      maximum-pool-size: 10
~~~

Numbers are in **milliseconds**; this is an example for testing/low-latency contexts, not production values to copy verbatim. Hikari requires `validationTimeout` to be lower than `connectionTimeout` and enforces minimum thresholds. `maximum-pool-size` sets the ceiling on connections managed by the pool; raising it blindly can shift contention from the application pool onto the DB.

When a `DataSource.getConnection()` call cannot be served within `connectionTimeout`, Hikari reports an acquisition error (typically an `SQLException`, translated by Spring if accessed through Spring abstractions). This is a **pool timeout**; do not assume a JDBC statement ran or the DB just cancelled a query.

Also configure **JDBC driver connect/login timeout** if creating a new physical connection can hang for a long time. Pool `connectionTimeout` and driver connect timeout are two separate policies; similar names do not make them identical.

In Spring Framework without Boot, `spring.datasource.hikari.*` keys have no automatic effect. You must configure `HikariDataSource` or your chosen connection pool via the application's own configuration.

## 6. Standard JDBC: Bounding the Query Itself with Statement.setQueryTimeout

JDBC provides `Statement.setQueryTimeout(int seconds)`, inherited by `PreparedStatement`. It enforces an execution timeout on the statement in **seconds**. The driver is expected to detect expiration and attempt to cancel the statement; however, actual stop timing, how the driver sends cancel, connection state, and side-effect outcomes must be verified per driver/DB.

Illustrative JDBC snippet (assuming a valid `DataSource dataSource`):

~~~java
String sql = "select status from orders where id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setQueryTimeout(2);  // 2 seconds, for this statement only
    statement.setLong(1, orderId);

    try (ResultSet rs = statement.executeQuery()) {
        if (!rs.next()) {
            throw new IllegalStateException("Order not found");
        }
        return rs.getString(1);
    }
}
~~~

This is a **snippet to embed in a Java method**, not a standalone program; it requires importing `java.sql.Connection`, `PreparedStatement`, `ResultSet`, `DataSource`, and having `orderId`. `try-with-resources` closes the result set, statement, and connection on both success and error paths.

Distinguish:

1. `setQueryTimeout(2)` does not include the time `dataSource.getConnection()` already spent above it.
2. On SQL timeout, JDBC may throw `SQLTimeoutException`; Spring JDBC typically translates `SQLException`s into the `DataAccessException` hierarchy. Do not hard-couple application logic to a specific exception message across different drivers.
3. Timeout usually **requests** cancelling the statement, which does not mean every command already executed, committed, or side-effected on the DB is undone.
4. JDBC query timeout does not replace network socket timeouts: the driver may need to wait on the cancel protocol or lose connectivity depending on implementation.
5. SQL batching, large result streaming, and `ResultSet` fetching can have different timeout scopes across drivers. Check driver docs and test against the real DB.

Do not rely on `Thread.interrupt()` or `CompletableFuture.orTimeout()` as the sole way to bound blocking SQL. Driver/server mechanisms are the primary point for issuing cancel signals and avoiding unbounded waits.

## 7. Spring JdbcTemplate: Configuring Query Timeout

Spring JDBC provides `JdbcTemplate.setQueryTimeout(int)`. `JdbcTemplate`'s default is **-1**: do not apply an explicit timeout to statements and let the driver use its default. When set to a positive value, `JdbcTemplate` attempts to apply the limit when creating statements.

A Spring Framework configuration sharing one template:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class DatabaseTimeoutConfig {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setQueryTimeout(2); // seconds
        return template;
    }
}
~~~

This is a **Spring integration configuration snippet**, requiring `spring-jdbc` and an already-configured `DataSource` bean. When a service uses this `JdbcTemplate` to run SQL, statements managed by the template inherit the configured query timeout unless overridden by another constraint (notably a transaction timeout).

Service usage example:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusReader {
    private final JdbcTemplate jdbc;

    public OrderStatusReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String status(long orderId) {
        return jdbc.queryForObject(
            "select status from orders where id = ?",
            String.class,
            orderId);
    }
}
~~~

This is a **project-integrated example**, assuming the DB has an `orders` table with `id` and `status` columns; it cannot run standalone without a datasource/schema. `queryForObject` can also fail due to zero rows or too many rows, which is completely different from a timeout; do not lump them under the same retry rule.

**Subtle point:** When a transaction timeout is active, `JdbcTemplate` normally uses **the remaining time of the transaction** on statements, overriding its own query timeout value. Do not write a false rule claiming the system always automatically picks the smaller of the two numbers you declared. Verify your Spring transaction manager and actual behavior.

## 8. Transaction Timeout Is Not a Clock That Cancels All I/O

Spring provides `@Transactional(timeout = n)` where **n is in seconds**, subject to transaction manager support. In JDBC with `DataSourceTransactionManager` (or equivalent configuration), Spring can propagate the remaining transaction time down to statements created by `JdbcTemplate`.

~~~java
@Service
public class InventoryService {
    private final JdbcTemplate jdbc;

    public InventoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 4, readOnly = true)
    public Integer available(long skuId) {
        return jdbc.queryForObject(
            "select quantity from inventory where sku_id = ?",
            Integer.class,
            skuId);
    }
}
~~~

This snippet requires importing Spring JDBC, `@Transactional`, `@Service`, and must be invoked through the Spring transaction proxy; it is not a standalone runnable project. Exact timeout behavior depends on the transaction manager, active propagation, JDBC driver, and transaction scope.

**Misconceptions to avoid:**

- `@Transactional(timeout=4)` does not guarantee an HTTP call made inside the transaction is also cancelled after four seconds.
- Not every transaction manager propagates deadlines identically to every resource/driver.
- If a method joins an existing transaction, the new annotation's timeout does not necessarily start a fresh clock; the timeout attribute is defined according to propagation and transaction creation.
- Spring transaction timeout does not replace pool connection acquisition timeout or driver socket timeouts in all configurations.
- `@Transactional` on a self-invoked `this.method()` in proxy mode can be bypassed. With `@Async`, imperative transactions also do not automatically flow from the caller thread to the async worker.

If a business flow uses both the DB and a remote API, **do not hold a transaction and DB connection open across a slow network call** unless carefully evaluated. Doing so holds locks/connections and can push the pool into exhaustion. Usually you should split transaction boundaries or design an appropriate outbox/saga pattern.

## 9. Drivers and Databases Also Have Their Own Timeouts

Even under the same JDBC concept, driver details vary widely. With **PostgreSQL JDBC (pgJDBC)**, common URL parameters include:

~~~text
jdbc:postgresql://db.example.invalid:5432/orders?connectTimeout=3&socketTimeout=8
~~~

This is an **illustrative URL**, not a real DB address and containing no credentials. In pgJDBC, `connectTimeout` is the socket establishment limit in seconds, and `socketTimeout` is the socket read limit in seconds. The driver also supports `queryTimeout` as a default parameter when a statement has no explicit timeout set.

Do not take pgJDBC's unit table and apply it to MySQL, SQL Server, or Oracle JDBC: another driver may use milliseconds, different property names, or different cancellation mechanics. Follow your project's actual driver and version.

On the **PostgreSQL server** side, there are also `statement_timeout` to bound statements directly on the DB, and `lock_timeout` for lock waits. Example within a controlled transaction:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SELECT status FROM orders WHERE id = 42;
COMMIT;
~~~

This is **illustrative PostgreSQL SQL**, requiring valid tables and DB privileges; do not apply verbatim on other databases. `SET LOCAL` scopes the timeout to the transaction. Avoid altering session-level settings and returning the connection to the pool without proper reset management.

Server timeouts add a layer of protection when the caller/driver stops waiting, though not every operation with side effects automatically undoes itself per business intent. For writes, transaction design and commit state are decisive.

## 10. HTTP: Connect Timeout Is Not Request/Response Timeout

When calling a service over the network, distinguish:

| Limit | Meaning | When useful |
| --- | --- | --- |
| Connect timeout | Time to establish a **new connection** to the remote endpoint | Host unresponsive to TCP connect, firewall/drop |
| Connection pool acquisition timeout | Time waiting for an available connection from the **HTTP client connection pool**, if the library pools connections | Client exhausts connections even while remote is healthy |
| Request/response timeout | Time expected for the remote to return a response per client policy | Server processes slowly or response is delayed |
| Socket read/idle timeout | Time a read operation receives no data, depending on library and transport | Connection stalls or streaming makes no progress |
| Total deadline | Instant by which the entire business operation must complete | Avoid continuing steps after the result has lost validity |

Not every HTTP client exposes all of these properties or assigns them the same meaning. In particular, **read timeout is not always the total duration of the entire response body**: if a library only measures silence between reads, a server trickling one byte periodically can stretch total time arbitrarily. For streaming, add total duration or payload-size limits if required.

A reused connection normally **does not go through a new connect**, so setting only a connect timeout does not protect against a slow remote server. Calls can wait a very long time for a response even on an existing connection.

## 11. Java 17 HttpClient: Configuring Separate Connect and Request Timeouts

JDK 17 supports `java.net.http.HttpClient` and `HttpRequest`:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(500))
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.invalid/orders/42"))
    .timeout(Duration.ofSeconds(2))
    .GET()
    .build();

HttpResponse<String> response =
    client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

This is an **integration snippet**, requiring imports for `HttpClient`, `HttpRequest`, `HttpResponse`, `URI`, `Duration`, plus handling `IOException` and `InterruptedException`; the `example.invalid` hostname is illustrative only, not a real endpoint.

Mechanics:

- `HttpClient.Builder.connectTimeout(Duration)` applies to **establishing a new connection**. When a connection is reused, this timeout is not an independent timer bounding the whole response.
- `HttpRequest.Builder.timeout(Duration)` sets the **request** timeout; in the JDK 17 API, if the response is not received within the limit, `HttpTimeoutException` is thrown by `send` or completes `sendAsync` exceptionally. This is not merely a “TCP socket read timeout”.
- `HttpConnectTimeoutException` is a subtype of `HttpTimeoutException`, allowing you to distinguish connection failures from response failures when needed.
- Every timeout `Duration` used here must be **positive**; do not pass `Duration.ZERO` assuming it means infinite.
- A remote HTTP server **may still process the request** after the client times out. Especially on side-effecting POST/PUT calls, retries need idempotency keys or status-lookup mechanisms.

This configuration is better than only calling `CompletableFuture.orTimeout` on the outside because the HTTP client protocol enforces the timeout on the actual request. Even so, exact cancellation and connection closing still depend on transport, body handler, version, and circumstances.

## 12. Standalone Runnable Java 17+ Example: HTTP Server Intentionally Responding Slowly

To observe timeouts **without internet access or an external server**, use the JDK's local HTTP server. The server delays 700ms before sending a response; the client sets a 120ms request timeout. The program prints a deterministic line when the client detects the timeout.

Create file **NetworkTimeoutDemo.java**:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

public class NetworkTimeoutDemo {
    private static void slowResponse(HttpExchange exchange) {
        try {
            Thread.sleep(700);
            byte[] body = "ready".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (IOException disconnected) {
            // Client may have timed out before this response was written.
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverWorkers = Executors.newSingleThreadExecutor();
        server.setExecutor(serverWorkers);
        server.createContext("/slow", NetworkTimeoutDemo::slowResponse);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(300))
                .build();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                        + server.getAddress().getPort() + "/slow"))
                .timeout(Duration.ofMillis(120))
                .GET()
                .build();

            try {
                client.send(request, HttpResponse.BodyHandlers.ofString());
                System.out.println("Unexpected: request succeeded");
            } catch (HttpTimeoutException timeout) {
                System.out.println("HTTP request timed out");
            }
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Run on **JDK 17+**:

~~~bash
javac NetworkTimeoutDemo.java
java NetworkTimeoutDemo
~~~

**Stdout when the machine allows creating a normal local server/client**:

~~~text
HTTP request timed out
~~~

This demo was compiled and run successfully; no Spring dependencies, database, or internet are needed. The server binds only loopback `127.0.0.1` on an auto-selected free port. Because the response is slower than the request timeout, `HttpTimeoutException` is caught and the program prints the message. `finally` stops the server and shuts down the server executor.

**Key learning point:** client expiration **does not mean the server was ordered by the client JVM to stop work**. If the server is executing a side-effecting operation, server-side state may still change even though the caller stopped waiting for a response. This test only proves the client enforces request-level timeouts at the I/O layer.

`com.sun.net.httpserver.HttpServer` belongs to the **`jdk.httpserver`** module bundled with the **JDK** for local testing demos; it is not Spring Boot's embedded server and is not intended to replace a production web server.

## 13. Spring RestClient: Choosing a Request Factory and Configuring HTTP Timeouts

In **Spring Framework 6.2**, a `RestClient` using `JdkClientHttpRequestFactory` can take a JDK `HttpClient` configured with a connect timeout while setting the response/read timeout on the request factory:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientTimeoutConfig {
    @Bean
    RestClient stockRestClient() {
        HttpClient jdkClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(2));

        return RestClient.builder()
            .requestFactory(factory)
            .baseUrl("https://stock.example.invalid")
            .build();
    }
}
~~~

This is a **Spring configuration snippet**, requiring `spring-web` and a real remote URL at runtime; `example.invalid` intentionally does not point to a real system. The pair of values illustrates connect/response timeouts, not a fixed recommendation for every API.

The `setReadTimeout` method name and how it maps to the native HTTP client **depend on the request factory/version**. Do not copy the exact values to Apache HttpComponents, Reactor Netty, Jetty, or OkHttp and assume identical semantics. Spring supports multiple `ClientHttpRequestFactory` implementations; verify which factory is actually chosen at runtime.

With **Spring WebClient** backed by Reactor Netty, timeouts are normally configured on the Reactor Netty `HttpClient`: connect timeout and response timeout are separate mechanisms. Changing a property that is not wired into the actual `WebClient` has no effect. In reactive systems, avoid `block()` on event-loop threads and apply pipeline-appropriate timeouts and cleanup.

**Do not equate** Spring MVC's `spring.mvc.async.request-timeout` with the HTTP client timeout for calling external services. Inbound server-side timeouts do not replace outbound `RestClient`/`WebClient` timeouts.

## 14. @Async and CompletableFuture: Outer Timeouts Do Not Stop Inner JDBC/HTTP Calls

A commonly misunderstood snippet:

~~~java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> blockingJdbcCall(),
        ioExecutor);

future.orTimeout(2, TimeUnit.SECONDS);
~~~

This is an **illustrative snippet**, requiring `blockingJdbcCall`/`ioExecutor` and appropriate imports. `orTimeout` can complete the future **exceptionally** after two seconds. It **does not guarantee** `blockingJdbcCall()` or the JDBC connection is interrupted/closed/rolled back once running. The worker can keep holding the JDBC connection and executing SQL after the caller thinks it “cancelled”.

A better design configures timeouts **directly in JDBC** for `blockingJdbcCall`: `JdbcTemplate.setQueryTimeout(...)`, JDBC `Statement.setQueryTimeout(...)`, and driver/server timeouts. Similarly, if the callback uses an HTTP client, request timeouts must be configured on the HTTP client/request, not solely on the returned future.

For example, a `CompletableFuture<HttpResponse<String>>` from `HttpClient.sendAsync(...)` benefits from `HttpRequest`'s timeout because the native HTTP client enforces that policy. Adding `future.orTimeout(...)` on top is an **additional observation clock**, not a substitute for configuring the request timeout.

**Distinguish three behaviors:**

1. **Timed-out caller:** the waiter stops waiting or the future completes with a timeout.
2. **Cancellation attempt:** the system attempts to interrupt/cancel the underlying task via driver/client APIs if supported.
3. **Remote work actually stopped:** the DB/server has genuinely stopped processing and released resources.

These three are not equivalent. With JDK `CompletableFuture.cancel(true)`, the `mayInterruptIfRunning` flag has no effect to force-interrupt a running worker. With the JDK HTTP client, cancelling the async future should also not be interpreted as confirmation that the remote side stopped processing.

## 15. Overall Deadline, Retry Budget, and Propagation

A task with DB → HTTP steps needs an **end-to-end deadline**. For instance, an inbound request is given 3 seconds, and by the time HTTP starts only 900ms remain. If you still configure a 2-second HTTP request timeout without checking remaining time, the result may arrive after the inbound response has already expired.

One way to compute this **within the same Java process** using a monotonic clock:

~~~java
long deadlineNanos =
    System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

// After completing the DB step...
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Request deadline exceeded");
}
Duration requestBudget = Duration.ofNanos(remainingNanos);
~~~

This is a **snippet to embed in a method**, requiring imports for `TimeUnit`, `Duration`, `TimeoutException`; it is not a standalone class. `System.nanoTime()` is suited for measuring **elapsed time within one JVM**, not as a meaningful timestamp across machines. Handle overflow and tiny remaining budgets appropriately when designing shared APIs.

Pass `requestBudget` into the actual HTTP request builder, optionally subtracting a safety margin for serialization and logging. For SQL, if an API only accepts whole-second timeouts, do not round down to 0 and accidentally disable the timeout; instead choose a valid rounding policy, a driver/server setting with finer resolution, or reject the step if insufficient time remains.

**Retries:** every retry must fit inside the overall deadline with enough budget left for waiting plus execution. Do not retry immediately when DB/HTTP has timed out, as that can amplify overload and duplicate side effects. Only retry genuinely transient errors, using backoff + jitter, max attempts, and idempotency, and honoring `Retry-After` when the remote signals it appropriately.

## 16. When Timeouts Occur: Resources, Transactions, and Uncertain Outcomes

For DB:

- A statement timeout may trigger a cancellation attempt, but verify whether the real driver/DB actually stopped the query.
- The transaction may need rollback; if Spring sees an unchecked `DataAccessException` cross the transaction interceptor, default Spring rules normally mark it for rollback. However, if you **catch and swallow the error** before the interceptor sees it, rollback will not occur automatically.
- An `UPDATE` or stored procedure may have done partial work before timing out; commit/rollback state determines the final outcome, which cannot be deduced from the timeout message alone.
- Close `ResultSet`/`Statement`/`Connection` via `try-with-resources`; when using Spring JDBC, let the template/transaction manager handle resources rather than improperly closing a transaction-bound connection.
- A connection suffering a severe network error may no longer be safe to reuse; let the driver/pool validate and evict it per their mechanisms.

For HTTP:

- A client timeout does not prove the remote **never received POST/PUT/PATCH**. The request may have succeeded before the response was lost.
- Do not blindly retry mutations as brand-new requests. Use a **stable idempotency key** across attempts or a status-lookup API.
- For large streaming responses, release response bodies/subscribers/connections through the proper abstraction; do not let a task time out while the body stream keeps holding resources.
- Distinguish connect errors, request timeouts, server `408`/`429`/`503` responses, and deserialization errors; they have different retry semantics.

When a task runs on an `@Async` worker, I/O timeouts should be **surfaced into the outcome state**: with methods returning `CompletableFuture`, callers can observe exceptional completion. With `@Async void`, uncaught exceptions pass to `AsyncUncaughtExceptionHandler` if invoked via the Spring proxy, rather than returning to the caller as a synchronous exception.

## 17. Ordering Timeouts to Avoid Self-Inflicted Bottlenecks

A good policy considers relationships with real resources:

1. **DB connection acquisition timeout smaller than overall deadline.** If the pool is exhausted, fail fast instead of holding workers pointlessly.
2. **Query timeout matched to SQL characteristics and SLO.** Long batch queries may need a dedicated pool/API rather than raising the global timeout for all requests.
3. **Driver socket timeout protects the DB transport.** Depending on the driver, it needs enough headroom for cancel/query-timeout handshakes; setting it too low can break connections before the DB confirms cancelling a statement.
4. **Short yet realistic HTTP connect timeout** for the deployment network; request/response timeout bounds the remote work itself. Add a pool acquisition timeout if the HTTP client uses a connection pool.
5. **Overall deadline leaves buffer for downstream and cleanup.** Do not spend all time on SQL and then start HTTP after the caller has already expired.
6. **Retries must never reset the overall deadline** to a fresh unbounded budget.
7. **Queue time is also latency.** If an `@Async` task sits in the executor queue for 5 seconds before starting, a 2-second SQL timeout does not ensure the job finishes within 2 seconds of submission.
8. **Measure concurrency and connection pools.** Every worker stuck in JDBC/HTTP means one fewer worker for other tasks; I/O timeouts are part of preventing thread starvation.

Allow exceptions by workload type: a background report allowed 2 minutes may need a different worker pool, DB statement timeout, and deadline than an interactive endpoint requiring sub-second response. No single configuration fits every task.

## 18. Observing and Testing Timeouts Layer by Layer

**Metrics/tracing should separate:**

| Component | What to measure |
| --- | --- |
| ThreadPoolTaskExecutor | Active threads, queue length, task wait time, rejected submissions |
| Connection pool | Active/idle/pending connections, acquisition latency, acquisition timeouts |
| SQL/JDBC | Query duration, statement timeouts, lock wait, SQLState/vendor errors, transaction rollbacks |
| HTTP client | Connection establishment, response latency, HTTP status, connect timeouts, request timeouts, pool wait |
| Business | End-to-end latency, remaining deadline, retry attempts, late completions, duplicate prevention |

Keep metric labels low-cardinality; never put raw SQL containing personal data, URLs with tokens, request bodies, or user IDs into metric tags. Use structured tracing/logging with security policies when drill-down is needed.

**Suggested test suite:**

1. **DB pool exhausted:** hold all connections in a test, request a new connection, and verify the pool acquisition timeout fires; do not confuse it with a query timeout.
2. **Long SQL:** execute a query intentionally slowed by the test DB (e.g., `pg_sleep` on a PostgreSQL test environment) and verify driver/server timeout and how connections are returned to the pool.
3. **Slow HTTP:** use a local/mock server returning responses slower than the request timeout; verify error types and resource cleanup as in the demo.
4. **Connect failure:** test in a controlled network-fault environment; do not assume every bad address triggers a connect timeout (it may be rejected immediately).
5. **Late result:** let the caller/future expire first while downstream finishes late; confirm it does not overwrite final state or create duplicate side effects.
6. **Retry storm:** multiple callers hit timeouts concurrently; verify retries are bounded, use backoff/jitter, and do not amplify load indefinitely.
7. **Cancellation:** test `Future.cancel` and verify whether the JDBC/HTTP client/DB actually releases resources; do not assert only `isCancelled()`.
8. **Transaction boundary:** trigger a timeout inside `@Transactional`, then inspect rollback and table state after failure against a real DB.
9. **Queue wait:** hold workers with a latch to measure queue delay separately from SQL/network execution time.

Use **controllable clocks** or latches in unit tests whenever possible; avoid writing `Thread.sleep` tests expecting exact timings. For drivers and networking, real integration tests are essential because timeouts are affected by the OS, JDK, and infrastructure configuration.

## 19. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`CompletableFuture.orTimeout` stops the JDBC query.” | It expires the future; underlying I/O may keep running. |
| “`HikariCP.connectionTimeout` is an SQL query timeout.” | It primarily limits how long to wait to borrow a connection from the pool. |
| “`@Transactional(timeout=...)` auto-cancels all HTTP requests.” | Transaction timeout only applies to resources supported by and integrated with the transaction manager. |
| “With `connectTimeout`, remote APIs will never hang.” | Connect only limits establishing a new connection; the remote can still respond slowly. |
| “Every `readTimeout` bounds total request duration.” | Many clients only bound silence between reads or responses per their own policy. |
| “`Statement.setQueryTimeout(2)` includes connection acquisition time.” | Query timeout starts at the statement; acquisition precedes it. |
| “`setQueryTimeout(500)` means 500ms.” | JDBC takes **seconds**; that is 500 seconds if applied directly by the driver. |
| “All drivers specify `socketTimeout` in milliseconds.” | Names and units are driver-specific; pgJDBC uses seconds. |
| “A timeout means the remote did not create the order/payment.” | The remote may have executed it, with only the response failing to arrive in time. |
| “On client timeout, the transaction definitely rolls back.” | Verify actual commit/rollback; the two systems have separate boundaries. |
| “Just setting a 3-second overall deadline frees all threads/connections.” | Deadlines must pair with real timeouts/cancellation at each I/O boundary. |
| “Setting tiny timeouts is always better.” | Causes false errors, retry storms, churned connections, and lower throughput; tune to SLO/load. |

## 20. Pre-Deployment Checklist

- Identify every wait point: executor queue, DB pool acquire, DB connect, SQL execution, DB socket, HTTP connect, HTTP response, and caller wait.
- Place timeouts at **the exact layer executing I/O**; do not place timeouts only on an outer future.
- Document the **units** of each property: Hikari milliseconds, JDBC statement seconds, JDK HTTP `Duration`, pgJDBC driver properties per docs.
- Enforce an overall deadline and do not start new steps when no time remains.
- Verify the exact version/driver/request factory running in production; do not copy assumptions from other libraries.
- Use query timeouts, driver/network timeouts, and server timeouts where needed, understanding transaction-timeout override conditions.
- Choose proper rollback, error-propagation, and cleanup policies on timeout.
- Avoid holding DB transactions/connections across slow remote calls when boundaries can be separated.
- Never auto-retry endlessly; for state-changing operations, use idempotency keys and reconciliation.
- Monitor pending pool connections, active workers, query/HTTP latency, timeout rates, retries, and late completions.
- Test slow queries, slow HTTP, connection pool saturation, network errors, transaction rollbacks, and late-arriving side effects.

**Conclusion:** An `@Async` task may already be expired from the caller's perspective while still waiting on JDBC/HTTP on the worker. To avoid holding threads and connections indefinitely, you must **configure dedicated timeouts at the DB driver/statement/server and HTTP client/request layers**, while managing business deadlines, retries, cancellation, cleanup, and the consequences of uncertain outcomes.

## Official References

- [Java SE 17 – Statement.setQueryTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): JDBC statement execution limit and `SQLTimeoutException`.
- [Spring Framework – JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `setQueryTimeout`, default -1, and interaction with transaction timeout.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction timeout and propagation.
- [Spring Framework – DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): how transaction timeout is propagated to JDBC statements when properly integrated.
- [HikariCP – README](https://github.com/brettwooldridge/HikariCP): `connectionTimeout`, `validationTimeout`, `maximumPoolSize`.
- [PostgreSQL JDBC – Connection parameters](https://jdbc.postgresql.org/documentation/use/): `connectTimeout`, `socketTimeout`, `queryTimeout`, and units.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): connect timeout and HTTP client configuration.
- [Java SE 17 – HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): timeout for a single HTTP request.
- [Spring Framework – JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): `setReadTimeout(Duration)`.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout`, `cancel`, and task-cancellation limits.
