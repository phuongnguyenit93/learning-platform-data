# Timeout Is Not Equivalent to Canceling Arbitrary Java Work or Network Calls

## 1. Practical Problem: What Does `@Transactional(timeout = ...)` Protect?

A snippet that commonly causes misunderstandings:

```java
@Transactional(timeout = 2)
public void checkout() {
    callSlowExternalApi();
    saveOrder();
}
```

This is **illustrative code**: `callSlowExternalApi()` and `saveOrder()` are undefined; it is not a standalone program. Authors sometimes assume that right after 2 seconds, Spring will stop the method, cancel the HTTP request, interrupt all threads, revert all side effects, and roll back every system. **That understanding is wrong.**

In the Spring Framework's **imperative** transaction mechanism, `timeout` is a **transaction-management attribute**, not a timer authorized to arbitrarily halt any Java code. A transaction manager can store a **deadline** and use it to govern operations on **resources participating in the transaction**. With `DataSourceTransactionManager`, Spring JDBC can apply remaining time to JDBC `Statement.setQueryTimeout(...)` or detect an expired deadline when preparing a statement. However:

- `Thread.sleep(...)` is not automatically interrupted by the transaction manager just because the transaction timeout expired.
- A CPU loop, Java computation, file read, Java lock wait, queue wait, or external library call is not automatically canceled by Spring transaction timeout.
- HTTP clients have their own timeouts (connect, response/request wait). `@Transactional(timeout=2)` **does not automatically turn into a 2-second HTTP request timeout**.
- A call to a remote system that already produced side effects (sending emails, payments, publishing messages) **is not undone** merely because the caller-side JDBC transaction rolls back.
- Even database timeout errors can depend on the database/driver/transaction manager: never promise that upon reaching the deadline every running JDBC statement stops immediately to the exact millisecond.

**This lesson belongs to the "Read-only and timeout" topic in Spring transaction management.** The goal is to distinguish transaction timeout from work-cancellation mechanisms, then design and test timeouts layer by layer.

### After This Lesson, You Should Be Able To

1. Explain that `@Transactional(timeout = 3)` is a duration configured **in seconds**, applied to a new transaction when supported by the transaction infrastructure.
2. See the exact boundaries among **Spring transaction / JDBC statement / HTTP client / Java thread / request gateway**.
3. Distinguish an expired deadline from a **method actually stopping execution**.
4. Build a Java 17+ example where Java continues running past the transaction deadline, yet a subsequent JDBC operation after the deadline is rejected and prior writes roll back.
5. Configure HTTP timeouts separately, handle `InterruptedException`, cancellation, retries, idempotency, and avoid holding connections/row locks during network waits.
6. Understand why exceptions, rollbacks, and terminating remote work **are not a single event**.

## 2. Which Layer Does Timeout Belong To?

Imagine an HTTP request flowing through controller → service → database and another API:

```text
Client / Load balancer / API gateway
       |
       |  Request deadline / gateway timeout
       v
Spring MVC Controller
       |
       |  Java method execution, worker thread
       v
@Transactional(timeout = 2) Service
       |
       |  Spring transaction deadline, rollback policy
       +------------------------+
       |                        |
       v                        v
Spring JDBC / JPA            Java HttpClient
       |                        |
       | Statement/query        | connect timeout,
       | timeout / lock         | per-request timeout,
       | timeout / DB limits    | cancellation policy
       v                        v
Database                    Remote server
       |                        |
       v                        v
COMMIT / ROLLBACK           Remote side effects
(only resources             (not automatically rolled back
 in the transaction)         by JDBC transaction)
```

| Timeout Type | Controlled Target | Important Limitation |
| --- | --- | --- |
| Spring **transaction timeout** | New physical transaction supported by manager; transaction deadline/resources | Not a Java thread-killer or automatic HTTP timeout |
| JDBC **statement/query timeout** | Execution time of a single SQL statement per driver/database | DB/driver-dependent; not equivalent to the whole Java use case deadline |
| Database **lock timeout** | Time waiting to acquire a lock | Can fail waiting for a lock even when other query time remains |
| HTTP **connect timeout** | Time to establish connection (within client support) | Does not necessarily limit the entire request/response |
| HTTP **request/response timeout** | Wait time of a network call per HTTP client | Does not automatically revert side effects that already occurred remotely |
| Gateway/request timeout | Time caller/gateway waits for a response | Does not guarantee the server worker stopped or the transaction rolled back |
| Application **deadline/cancellation** | Coordination rules across code, APIs, and tasks | Requires coordinating layers; no single annotation guarantees everything |

**Example:** the gateway returns 504 after 5 seconds. That only confirms the gateway timed out waiting according to its own policy; a task on the server **may still be running** and later commit the database or send a message. To know the actual result, inspect transaction outcomes, tracing, and idempotent operation state.

## 3. How Does Spring Understand `@Transactional(timeout = n)`?

Configuration:

```java
@Transactional(timeout = 3)
public void updateInventory() {
    // Business operations requiring a transaction.
}
```

This is **illustrative**, without class/repository. `timeout = 3` is declared **in seconds**. The default value `-1` means using the transaction system's default timeout (or unlimited if unsupported).

Per the Spring Framework, the `timeout` attribute applies when a **new transaction starts**, typically with `PROPAGATION_REQUIRED` or `PROPAGATION_REQUIRES_NEW`:

- `REQUIRED` when **no transaction exists**: creates a new transaction using the declared timeout if supported by the manager.
- `REQUIRED` when **joining T1**: does not create a physical transaction with a separate deadline; declaring timeout on inner does not automatically override T1's timeout.
- `REQUIRES_NEW`: creates a **separate physical transaction**, which can apply the inner's own deadline. Outer transaction resources are suspended per the manager.
- `NESTED` in JDBC usually uses a **savepoint within the same physical transaction**, without an independent new physical clock/deadline like `REQUIRES_NEW`.

Do not assert that timeout behaves identically across all `PlatformTransactionManager` implementations. JDBC, JPA/Hibernate, JTA, R2DBC resources and individual databases have their own enforcement mechanisms. A manager that does not support a timeout cannot automatically abort arbitrary code; it may even reject the configuration depending on implementation.

### 3.1. Deadline ≠ Immediate Interrupt

Pure Java computation:

```java
@Transactional(timeout = 1)
public void compute() {
    busyCalculation();
}
```

This is an **illustrative snippet**. When the transaction is created by the proxy, the timeout is registered with the transaction manager; however, Spring does not automatically turn `busyCalculation()` into Java code forced to stop after one second. If the computation touches no deadline-checking resource and has no separate cancellation mechanism, it can keep running past that time.

Similarly, `Thread.sleep(1500)` only wakes up after enough time elapses or another thread interrupts it via Java's mechanism; **transaction timeout itself does not call `Thread.interrupt()`** on the sleeping worker. After the wait, code can continue executing subsequent Java statements.

### 3.2. Where Can JDBC Timeout Actually Be Detected?

With `DataSourceTransactionManager` and `JdbcTemplate`:

1. The transaction manager opens a JDBC transaction and binds a connection holder/deadline to the thread.
2. `JdbcTemplate` obtains the connection via Spring-aware APIs (`DataSourceUtils`), using the connection participating in the transaction.
3. When creating/running a JDBC statement, Spring can fetch the **remaining transaction time** to call `Statement.setQueryTimeout(...)`.
4. If the deadline **has already expired** when retrieving remaining time, Spring can throw `TransactionTimedOutException` before the next SQL runs.
5. If an executing SQL statement exceeds the applied time, the driver/database can raise a query timeout error via its own mechanism; the exception class translated to Spring may differ from `TransactionTimedOutException`.
6. If an unchecked exception escapes the `@Transactional` boundary, Spring rolls back the JDBC writes in the transaction by default.

From this follows a crucial detail: **Java code continuing to run past the deadline does not prove the JDBC transaction is still permitted to execute more SQL**. The deadline can be checked **when resources continue to be used**, rather than by a separate thread killing Java code right at second n.

Conversely, **not receiving a timeout exception** does not automatically prove everything finished under the deadline: a manager/driver may not actively check during pure Java computation or at commit. Measure latency and transaction outcomes rather than guessing.

## 4. A Timeline Clearly Separating What Happens

Suppose a service creates T1 with `timeout=1` second:

```text
t = 0 ms
    Spring proxy opens T1; JDBC connection is bound.
    SQL INSERT log_before succeeds (not yet committed).

t = 100 ms
    Java starts waiting via Thread.sleep(1400).
    T1's transaction deadline continues ticking down.

t ≈ 1500 ms
    Thread.sleep returns; Java prints "Java step finished".
    No Spring watchdog automatically aborted the Java execution.

t > 1500 ms
    Java calls JdbcTemplate.update(...) again.
    JDBC infrastructure checks T1's remaining time.
    May throw TransactionTimedOutException / query-timeout failure.

After exception escapes @Transactional method
    Spring transaction interceptor rolls back T1.
    INSERT log_before is undone; post-deadline SQL does not commit.
```

In the demo below, we **deliberately let the second JDBC operation happen after a long enough wait** to exercise Spring JDBC's timeout path. The line `Java step finished` appears **before** the exception. Thus learners observe two distinct events: Java keeps running **and** the transaction can fail when using the resource.

If the scenario replaces `Thread.sleep` with a slow HTTP call, the rule stays the same: **Spring's transaction deadline does not directly configure HTTP client timeout/cancellation**. The HTTP client may keep waiting even after the transaction has passed its deadline.

## 5. Runnable Practice: Java 17, Spring Framework 6.2, and H2

The small program below uses **Java 17+**, **Spring Framework 6.2.8**, **Spring JDBC**, and **H2 2.3.232**; no Spring Boot or HTTP server needed. It verifies three things:

1. A transaction can be active at the start of a method.
2. The method **still executes Java code after a sleep longer than `timeout=1`**.
3. A JDBC statement invoked **after the deadline** triggers a timeout and prior writes in the same transaction roll back.

This is a **local JDBC verification demo**; do not use `Thread.sleep` as a transaction-throttling mechanism in production.

### 5.1. Project Structure

```text
transaction-timeout-boundary/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── TimeoutBoundaryDemo.java
```

### 5.2. `pom.xml`

Copy the exact contents of this code block into `pom.xml`. **The XML declaration is the first line**; do not place comments before that line.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>transaction-timeout-boundary</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.TimeoutBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` manages beans/proxies; `spring-jdbc` provides `JdbcTemplate` and `DataSourceTransactionManager`; `spring-tx` provides `@Transactional`/timeout exceptions; H2 supplies the in-memory database and is on the compile classpath because Java imports `JdbcDataSource`.

### 5.3. `src/main/java/example/TimeoutBoundaryDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionTimedOutException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TimeoutBoundaryDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TimeoutService service = context.getBean(TimeoutService.class);

            jdbc.execute(
                "CREATE TABLE events (" +
                "id INT PRIMARY KEY, label VARCHAR(40) NOT NULL)"
            );

            System.out.println("CASE 1: Java work after deadline");
            service.onlyJava();
            System.out.println("Java-only method returned");

            System.out.println("CASE 2: JDBC after deadline");
            try {
                service.jdbcAfterDeadline();
                System.out.println("Unexpected: JDBC completed");
            } catch (TransactionTimedOutException expected) {
                System.out.println("Outcome: TransactionTimedOutException");
            }

            Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM events", Integer.class
            );
            System.out.println("Committed rows after rollback: " + rows);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:timeout_boundary;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TimeoutService timeoutService(JdbcTemplate jdbcTemplate) {
            return new TimeoutService(jdbcTemplate);
        }
    }

    public static class TimeoutService {
        private final JdbcTemplate jdbc;

        public TimeoutService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(timeout = 1)
        public void onlyJava() {
            System.out.println(
                "Transaction active: "
                    + TransactionSynchronizationManager
                        .isActualTransactionActive()
            );
            pause(1400);
            System.out.println("Java continued after 1400 ms");
            // No more SQL used after the deadline.
            // In local JDBC demo, there is no watchdog auto-interrupting.
        }

        @Transactional(timeout = 1)
        public void jdbcAfterDeadline() {
            jdbc.update(
                "INSERT INTO events (id, label) VALUES (?, ?)",
                1, "before"
            );

            pause(1400);
            System.out.println("Java continued, trying another JDBC write");

            // JdbcTemplate checks transaction deadline when creating statement.
            // Deadline expired -> TransactionTimedOutException, rollback.
            jdbc.update(
                "INSERT INTO events (id, label) VALUES (?, ?)",
                2, "after"
            );
        }

        private static void pause(long milliseconds) {
            try {
                Thread.sleep(milliseconds);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Interrupted", ex);
            }
        }
    }
}
```

**What is verified:**

- `TimeoutService` is registered via `@Bean` and fetched from `ApplicationContext`. It is a Spring-managed bean eligible for proxying; not an arbitrary object created with `new` in `main()`.
- `@EnableTransactionManagement` enables annotation-driven transaction interception.
- `DataSourceTransactionManager` manages the sole H2 datasource, the same datasource used by `JdbcTemplate`.
- Both public methods are called **externally through the bean proxy**, avoiding self-invocation.
- `@Transactional(timeout=1)` applies to a **new physical transaction** in each case, as there is no enclosing outer transaction.
- `pause(1400)` makes the Java thread wait over 1 second. Nothing calls `Thread.interrupt()` merely because Spring's deadline elapsed.
- Case 1 performs no SQL after the sleep. It illustrates that **Java code still finishes** and the JDBC transaction manager is not a mechanism that stops Java statements by wall-clock time.
- Case 2 inserts a row into the DB **before** sleeping, then runs another JDBC statement **after** the deadline. With `JdbcTemplate` + `DataSourceTransactionManager`, checking remaining time can throw `TransactionTimedOutException`. The unchecked exception escapes the proxy; Spring rolls back the entire transaction, erasing the previously inserted row.

### 5.4. Running the Program

From the `transaction-timeout-boundary` directory, with JDK 17+ and Maven 3.9+:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

**Expected output** for Spring Framework 6.2.8 + H2 local JDBC as configured in this lesson (ignoring extra Maven/Spring logs, assuming the thread is not externally interrupted):

```text
CASE 1: Java work after deadline
Transaction active: true
Java continued after 1400 ms
Java-only method returned
CASE 2: JDBC after deadline
Java continued, trying another JDBC write
Outcome: TransactionTimedOutException
Committed rows after rollback: 0
```

This is an example **expected under Spring JDBC local transaction semantics**, not a promise that every database/JPA/JTA driver will throw the exact same exception at the exact same moment. If changing managers/drivers, observe the actual exception and transaction outcome rather than comparing stdout character-by-character.

### 5.5. Why Do the Two Cases Seem Opposite?

**Case 1:** Spring opens a transaction, Java sleeps longer than the timeout, prints a log, and returns. Along this execution path **there is no new JDBC statement after the deadline** asking Spring to apply query timeout. With a local JDBC transaction manager like the demo, no independent component forces the Java thread to stop. This shows timeout is not `Future.cancel(true)` or a background scheduler that kills arbitrary Java work.

**Case 2:** Spring opens T2; the first JDBC insert lives inside T2 and is uncommitted. Java sleeps past the timeout and still prints the log; right at the **next JDBC operation**, the deadline has expired so the resource holder can throw `TransactionTimedOutException`. The exception passes through the transaction interceptor, and Spring rolls back T2. The query outside the transaction subsequently counts 0 rows. Thus:

```text
Java continues running after deadline   = yes
New JDBC operation after deadline       = rejected in the example
Data written before timeout committed   = no; transaction rolled back
Spring automatically aborts Thread.sleep() = no
```

A transaction timeout can never guarantee that **all remote side effects have vanished**. If before sleeping we sent an HTTP request to place an order in another system, rolling back H2 does not automatically undo the remote order.

## 6. HTTP Call Timeout Is a Separate Configuration

Spring's transaction manager controls the transaction; the **HTTP client** controls HTTP wait time. With Java 17 `java.net.http.HttpClient`, an illustrative example:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class RemoteLookup {
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

    public String lookup() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.example.com/status"))
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        return response.body();
    }
}
```

This is an **illustrative HTTP example, not run in the Maven demo in section 5**, and the URL is a placeholder endpoint. It distinguishes:

- `connectTimeout(Duration.ofSeconds(2))`: timeout policy for **establishing the connection** within the HTTP client's scope.
- `HttpRequest.Builder.timeout(Duration.ofSeconds(3))`: time limit allotted for the **request** per the HTTP client API.
- No line relates directly to `@Transactional(timeout=1)`. If an outer Spring transaction needs a different deadline, configure the transaction separately.

When an HTTP request times out, the client may throw `HttpTimeoutException`. That **does not confirm the remote server did not process the request**. Especially with POST requests creating payments/orders: the server may have succeeded while the response was delayed; the caller timing out and blindly retrying will cause **duplicate processing**. Use idempotency keys, operation statuses, request IDs, and reconciliation mechanisms.

### 6.1. `@Transactional(timeout = 2)` Does Not Automatically Set HTTP Timeout to 2 Seconds

Code that easily goes wrong:

```java
@Transactional(timeout = 2)
public void slowCheckout() {
    externalClient.callWithoutRequestTimeout(); // May wait longer than 2 seconds.
    repository.saveOrder();                     // May fail because T1 exceeded deadline.
}
```

This is **illustrative**, without defining dependencies. A 20-second remote call can still finish normally or be cut off by the HTTP stack itself; `@Transactional(timeout=2)` does not automatically create a watchdog setting `HttpClient` timeout to 2 seconds. When calling JDBC afterward, Spring may detect the expired deadline and roll back the local DB write, yet the remote side effect that already happened **can still exist**.

### 6.2. Connect, TLS, Response Read, and Total Deadline

HTTP stacks (Java HttpClient, OkHttp, Apache HttpClient, WebClient, gateways, service meshes) expose different timeouts: DNS/connect/TLS, request, read/response, idle timeout, call timeout, or deadline. Not every timeout measures the same phase. When building production services, know the **exact timeouts on the library and version you use**; do not set a single number assuming it covers DNS, TLS, streaming bodies, and all retries.

If an API has a 4-second total budget, giving each HTTP retry 4 seconds and attempting 5 times will not ensure completion within 4 seconds. You need an **end-to-end deadline** and must reduce remaining wait time for each step.

## 7. Cancellation in Java Is Cooperative, Not Forcible Abortion

### 7.1. `Thread.interrupt()` Is a Signal

Java generally has no safe mechanism to forcibly terminate any arbitrary thread at an exact timestamp. `Thread.interrupt()` is a cooperative signal: operations supporting interruption (like `Thread.sleep`) respond with `InterruptedException`; CPU-bound code must check interrupt or cancellation flags itself to stop.

Handling pattern:

```java
try {
    Thread.sleep(5000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", ex);
}
```

This is **illustrative code**, not a complete Java file. In the Maven example, we used the same idea: **restore the interrupted flag**, then throw an unchecked exception so the transaction interceptor can roll back if the method is advised. Do not swallow interruption and proceed with write operations as if nothing happened.

Yet even once the Java worker stops due to interruption, **an HTTP POST or SQL already executed by a remote server is not automatically reversed**. Distinguish **stopping waiting**, **stopping local execution**, **stopping remote work**, and **reverting side effects**.

### 7.2. `Future.cancel(true)` and `CompletableFuture.orTimeout` Are Not Magic

`Future.cancel(true)` can **request interrupting** the running thread, but the task must support interruption/cancellation; it does not guarantee external I/O stops on time. With `CompletableFuture.orTimeout(...)`, the future is completed exceptionally at the deadline, yet that **does not automatically guarantee** the underlying work or remote operation stopped. Other async APIs have their own cancellation semantics; check the library implementation.

```java
// Illustrative example, without declaring executor/future:
future.orTimeout(2, TimeUnit.SECONDS)
      .exceptionally(ex -> {
          recordTimeout(ex);
          return fallbackResult();
      });
```

This snippet is **not standalone compilable**. Observing `fallbackResult()` does not prove the original task stopped running. If the task continues running and writes to the database after the caller returns a timeout, you need cancellation propagation, idempotency, and proper transaction boundary control.

### 7.3. `@Async` and Transaction Context

In imperative Spring, JDBC transaction resources are typically bound to the **current thread**. Calling `@Async` or spawning a `CompletableFuture` on another thread **does not automatically carry transaction T1 to the new thread**. The async method can open its own transaction if called through a Spring proxy and properly configured. T1's timeout does not automatically govern that new transaction's deadline, and T1 rolling back does not by default roll back an independent transaction on another thread.

With reactive programming (R2DBC, Project Reactor), Spring uses **Reactor Context** for reactive transactions rather than thread-bound JDBC resources; apply timeout/cancellation mechanisms suited to reactive pipelines. Do not copy conclusions about `Thread.sleep`/`JdbcTemplate` onto reactive chains without checking the actual APIs.

## 8. Timeout, Rollback, and Remote Data Are Three Different Questions

| Question | Mechanism to Inspect | Accurate Conclusion |
| --- | --- | --- |
| Overall time budget exceeded? | Request deadline, tracing, elapsed time | May be overdue even while task keeps running |
| JDBC statement stopped? | Spring JDBC timeout, driver, database query timeout | Depends on where deadline is checked / driver |
| Local transaction rolled back? | Transaction manager and commit/rollback outcome | Only guaranteed for resources participating in the transaction |
| HTTP client stopped waiting? | HTTP request/call timeout | Does not prove remote server did not process |
| Java worker actually stopped? | Thread/cancellation state, task completion | Future/caller timeout does not prove it |
| Remote side effect canceled? | Protocol/idempotency/compensation/remote status | JDBC rollback does not answer this question |

### 8.1. Do Not Catch Timeouts and Return Fake Success

Business-broken code:

```java
@Transactional(timeout = 1)
public void updateOrder() {
    repository.writeFirstStep();
    try {
        repository.writeSecondStep(); // May throw timeout.
    } catch (RuntimeException ex) {
        // Wrong: swallows error and returns as if transaction succeeded.
    }
}
```

This is **illustrative**. Once SQL timed out or the database reported an error, the transaction state may already be rollback-only or the resource no longer safe to continue. If caught and swallowed, the caller may see a false success result; subsequent commit may fail. The simple, predictable approach is **letting the error escape through the transaction boundary**, rolling back, and handling it in the orchestrator/caller layer. Retry (if appropriate) in a **new transaction**, with idempotency.

### 8.2. Timeout Does Not Replace a Business Deadline

Example checkout with a 3-second total budget:

```text
Gateway deadline:                     3000 ms
  Local checks/validation:             150 ms
  Remote API with request timeout:    1200 ms
  Short DB transaction:                500 ms
  Buffer for commit and response:     remaining
```

Numbers are **design examples**, not a universal SLA recommendation. A system must measure real latency to allocate budgets. Do not keep a database transaction open across a slow HTTP call if the design allows separating it outside the transaction. If consistent state between database and remote API is needed, look into saga/compensation, transactional outbox, and idempotency.

### 8.3. What If the Remote Call Succeeds Yet the DB Rolls Back?

What can happen:

```text
Local T1 starts
  |
  +-- Remote HTTP POST creates resource successfully
  |
  +-- Java continues, JDBC statement checks expired deadline
  |
  +-- Local T1 rolls back
  |
  +-- Remote resource may still exist
```

This cannot be fixed by increasing `@Transactional(timeout=...)`. You need contracts for creating/canceling remote resources, idempotency keys, business transaction states, outbox/saga, or designing the workflow in durable steps.

## 9. Designing Short Transaction Boundaries and Multi-Layer Timeouts

### 9.1. Avoid Long Remote I/O Inside Transactions

Risky pattern:

```java
@Transactional(timeout = 5)
public void placeOrder() {
    repository.reserveItems();
    remoteShippingApi.createShipment(); // Can block for a long time.
    repository.markReady();
}
```

**Illustrative code:** class/dependencies are undefined. The issue is not only timeout: the transaction can hold connections and row locks while waiting on the remote service, increasing lock contention, pool starvation, and risk of unrolled-back remote side effects.

Alternative design (at workflow level):

```text
1. Validate input, fetch reference data (without holding DB locks long).
2. Open a SHORT transaction.
3. Write order + outbox event atomically, commit.
4. Worker/outbox publisher calls remote with HTTP timeout/retry/idempotency.
5. Save remote operation status, retry/compensate if needed.
```

Not every project needs an outbox; however, if a side effect must happen **after commit** with guaranteed delivery, this is a much sounder direction than holding a JDBC transaction open while waiting on the network.

### 9.2. Choosing Timeouts by Layer

- **Database statement/query timeout** short enough to curb stuck queries; add lock timeout when supported by the DB.
- **Transaction timeout** matching the cost of the actual DB transaction portion. Do not configure it expecting it to abort arbitrary Java work.
- **HTTP request/call timeout** independent, specifying timeout types (connect/read/total) per the specific library.
- **End-to-end request deadline** covering multiple steps and all retries, with a buffer for commit/cleanup.
- **Cancellation propagation** and error handling when the caller leaves; avoid workers continuing infinite side effects.
- **Idempotency + final state** for commands with out-of-transaction side effects.

Choose concrete numbers based on percentile latency, contention, SLOs, and real retry budgets; there is no universal "timeout=3" right for every system.

## 10. Common Pitfalls When Using `@Transactional(timeout = ...)`

### Pitfall 1 — "When timeout expires, Spring interrupts the Thread"

No. The Spring transaction interceptor does not by default send `Thread.interrupt()` to arbitrary running Java code. The demo uses `Thread.sleep(1400)` with `timeout=1` to observe Java continuing execution past the deadline.

### Pitfall 2 — "HTTP calls inside a transaction automatically share the same timeout"

No. `HttpClient`, WebClient, RestClient, or other libraries need their own timeouts. Changing only transaction timeout is not enough when remote services are slow.

### Pitfall 3 — "With a timeout, nothing can commit after the deadline"

There is no universal rule like that across all managers/drivers. Local JDBC systems may check the deadline when creating statements rather than running an active watchdog canceling the entire transaction at expiration. Case 1 illustrates Java finishing even after the deadline passed. Always inspect actual outcomes and DB configs.

### Pitfall 4 — "Inner `REQUIRED(timeout=1)` always gets a new deadline"

No. An inner `REQUIRED` joining outer's physical transaction does not get an independent physical deadline just by adding an annotation. `timeout` targets **newly created** transactions; `REQUIRES_NEW` can create a separate transaction with its own timeout.

### Pitfall 5 — "JDBC timeout ensures HTTP side effects are undone"

No. JDBC rollback only affects JDBC resources participating in the transaction. Separate idempotency/compensation/remote protocols are needed.

### Pitfall 6 — "Just catch `TransactionTimedOutException` and proceed to commit"

Unsafe. A timeout exception may indicate the transaction/resource is in an error or rollback-only state. Let the error pass through the transaction boundary and design retries at the caller, starting a new transaction if valid.

### Pitfall 7 — "`Future.orTimeout` means the task has stopped"

Not guaranteed. The future can complete exceptionally while the worker/remote operation is still running. Cooperative cancellation and real state observation are required.

### Pitfall 8 — "Having the annotation means timeout is active"

Not if the method is not intercepted by Spring transaction infrastructure: self-invocation in the same bean, objects created with `new`, unproxyable methods/classes, beans managed by another context, or mismatched managers/resources. First check that the bean is Spring-managed and the caller invokes **through the proxy**.

### Pitfall 9 — "Hitting transaction timeout rolls back all work across the system"

No. A single use case may hit multiple databases, emit messages, and spawn async tasks; not everything shares one transaction. Map physical transactions and side-effect boundaries explicitly.

### Pitfall 10 — "The gateway returned an error so the backend definitely stopped"

No. Proxy/gateway timeouts may only stop **waiting for a response**; the backend worker may continue or the remote side effect may already have occurred. Investigate via request IDs, traces, idempotency keys, and transaction audits.

## 11. Self-Check, Exercises, and Testing

### Exercise 1 — Reading Demo Output

In case 2, why does the line:

```text
Java continued, trying another JDBC write
```

appear **before** `Outcome: TransactionTimedOutException`? Explain where Spring checks the deadline in the JDBC statement path.

### Exercise 2 — Removing the Second JDBC Statement

Modify `jdbcAfterDeadline()` so it does not call `jdbc.update(...)` after `pause(1400)`, and re-run. Observe output/DB in the local H2 environment; explain why timeout is not a watchdog canceling Java work. Do not extrapolate that result to JTA/other database drivers.

### Exercise 3 — Reducing Java Delay

Change sleep from 1400 ms down to 100 ms with `timeout=1`. In a normal environment, the second statement can run before the deadline and the transaction commits. When writing tests, avoid timings too close to the deadline because schedulers, slow machines, and CI can introduce flakiness.

### Exercise 4 — Transaction Timeout vs. HTTP Timeout

Given a service with `@Transactional(timeout=2)` yet an HTTP request timeout of 6 seconds: if a remote call takes 5 seconds, what **can** happen to the HTTP response, Java execution, and the subsequent JDBC command? Break the answer down by layer rather than saying "the entire request is canceled after 2 seconds".

### Exercise 5 — Intentionally Testing Query Timeout

In a test database, run a slow SQL supported by the driver/database with a short transaction timeout. Record the exception type, actual elapsed time, and rollback. Do not claim `Statement.setQueryTimeout` is enforced by every driver to the exact same millisecond.

### Exercise 6 — Interruption

In a copy of the demo, interrupt the worker while it is sleeping. Verify `InterruptedException`, restoring the interrupted flag, and rollback when throwing an unchecked exception through the transaction interceptor. Distinguish this experiment from transaction timeout: **the interrupt is sent by the test**, not automatically generated by `@Transactional(timeout=...)`.

### Exercise 7 — Designing by Deadline

An HTTP endpoint has a total 4-second budget comprising validation, an outbound HTTP call, a DB transaction, retry, and returning the response. Draw a timeline and allocate timeouts with buffers. Ensure total retry budget does not exceed the deadline, and address idempotency if the outbound call has side effects.

### Production Verification Checklist

| Question | How to Verify |
| --- | --- |
| Is `@Transactional` actually intercepted? | Bean from Spring, right `ApplicationContext`, proxy/call path |
| Which manager handles timeout? | `PlatformTransactionManager` and actual datasource |
| Does timeout apply to a new transaction or a join? | `REQUIRED` / `REQUIRES_NEW` propagation |
| Does JDBC use the transaction-bound connection? | `JdbcTemplate` / `DataSourceUtils`; do not grab connections outside manager |
| How do statement/query timeouts behave on the real driver? | Integration tests, SQL logs, database metrics |
| Does the HTTP client set connect/request timeouts? | HTTP client configuration and slow-endpoint tests |
| Do retries have a budget and idempotency? | Trace request ID, status, side-effect count |
| Does timeout exception escape through transaction boundary? | Transaction logs and rollback outcome |
| Does the worker actually stop when caller times out? | Thread/task lifecycle, async job state |
| Do remote side effects persist after DB rollback? | Read remote/reconciliation state rather than guessing |

## 12. Key Takeaways

`@Transactional(timeout = n)` is a **deadline for a transaction managed by the transaction manager**, taking effect primarily through resources participating in the transaction and manager/driver mechanisms. It **is not a self-destruct switch for Java threads**, does not apply timeouts to arbitrary HTTP calls, and does not revert side effects in remote systems.

To give a use case safe time limits, combine **transaction timeout, JDBC statement/database timeout, HTTP request timeout, end-to-end deadline, cooperative cancellation, rollback/error handling, and idempotency**. Keep transaction boundaries short, do not hold database locks during long network waits, and test both **what got committed** and **which tasks are still running** when a timeout occurs.

## 13. Official References

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html) — `timeout` in seconds; applies only to new transactions (`REQUIRED`/`REQUIRES_NEW` per context); rollback rules.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) — `DataSourceTransactionManager`/`DataSourceUtils`, transaction-bound connections, and JDBC statement query timeouts.
- [Spring Framework — `DataSourceUtils` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) — `applyTransactionTimeout(...)` and `applyTimeout(...)`.
- [Spring Framework — `ResourceHolderSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/ResourceHolderSupport.html) — deadlines and `TransactionTimedOutException` when out of time.
- [Spring Framework — `@Transactional` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html) — definition of the `timeout` attribute.
- [Java 17 — `HttpClient` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) and [`HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — connection/request timeouts.
- [Java 17 — `Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html) — interruption; cooperative cancellation.
