# Proving Rollback Boundaries and Cleaning Up Data After HTTP Tests

## 1. Problem: `@Transactional` on the test, yet records remain in the database

You have a Spring Boot `POST /orders` API that saves an order to the database. A test sends a real HTTP request with `TestRestTemplate`, is annotated with `@Transactional`, and rolls back by default after running. Yet after the test finishes, the `orders` table still holds data.

This is **not necessarily a bug in Spring Transaction Manager**. Under `@SpringBootTest(webEnvironment = RANDOM_PORT)` or `DEFINED_PORT` in a servlet application, the JUnit test method runs on the **HTTP client thread**, while the request is handled by the embedded server on a **server worker thread**. The Spring transaction opened by `TransactionalTestExecutionListener` for the test method is bound to the test thread; it does not propagate across TCP/HTTP to the server. A server-side `@Transactional` service opens, commits, or rolls back **a different transaction**. Once the server completes the POST and commits, rolling back the test thread **does not delete** that committed row.

Official **Spring Boot 3.5.16** documentation states clearly: when a real server starts via `RANDOM_PORT`/`DEFINED_PORT`, the HTTP client and server run in separate threads and transactions; transactions started on the server are not automatically undone by test-managed rollback. By contrast, `MockMvc` is **synchronous**, skips TCP, and typically runs handlers on the calling test thread; a service with `@Transactional(propagation=REQUIRED)` can join the open test transaction and roll back with it. Thus the very same API can leave different database state when tested via `MockMvc` vs real HTTP.

### Learning outcomes

After this lesson, you will be able to:

1. Diagram accurately the boundaries of `JUnit test transaction`, `Spring MVC request transaction`, database connections, and commits.
2. Explain why `@Rollback`/`@Transactional` on a test does not roll back server-side writes after an HTTP request.
3. Use `@SpringBootTest(RANDOM_PORT)`, `TestRestTemplate`, and `@LocalServerPort` within their proper scope.
4. Distinguish `MOCK + @AutoConfigureMockMvc` from `RANDOM_PORT + real HTTP`, and understand MockMvc's limits with async dispatch.
5. Use `@BeforeTransaction`/`@AfterTransaction` to inspect data **after the test-managed transaction has truly rolled back**.
6. Create two records: a **client marker** existing only inside the test transaction and a **server order** committed via HTTP. After rollback: marker = 0, server order = 1.
7. Perform **targeted cleanup** after HTTP tests using unique identifiers and committed transactions/connections.
8. Avoid using `@AfterEach` inside the same test-managed transaction to clean up server data while mistakenly assuming the delete committed.
9. Test rollback on the **server service** when a business exception occurs **before commit**.
10. Compare input validation errors (400), duplicate keys (409), server failures (500), and DB state.
11. Use `@Sql`/`@SqlConfig(transactionMode=ISOLATED)` properly when committed fixtures/cleanup are needed, and understand when cleanup scripts roll back with an outer test transaction.
12. Design fixture ID/namespace conventions allowing test classes to share a database without deleting one another's data.
13. Avoid false positives from Hibernate's first-level cache, missing `flush()`/`clear()`, or asserting before commit/async completion.
14. Write Java 17 / Spring Boot 3.5.16 integration tests runnable via Maven with H2/Spring JDBC and extensible to PostgreSQL Testcontainers.

## 2. Two transactions never share the same HTTP request

### 2.1. Real HTTP: a boundary that cannot be crossed automatically

~~~text
JUnit thread (HTTP client)                     Servlet container worker
---------------------------------             --------------------------------
@Transactional test begins [TX-T]            (no server TX yet)

insert client_marker
  -> uncommitted row in TX-T
  -> visible only to test thread/connection

HTTP POST /orders  --------------------------> Controller
                                               -> OrderService.create()
                                               -> @Transactional begins [TX-S]
                                               -> repository INSERT server_order
                                               -> TX-S COMMIT
                  <-------------------------- HTTP 201 Created

JUnit test assertions
Spring TestContext rolls back [TX-T]
   |
   +-- client_marker ROLLED BACK
   +-- server_order still COMMITTED
~~~

**There is no single JDBC transaction spanning an HTTP request just because both threads live in the same JVM or Spring ApplicationContext.** Spring's imperative transaction management binds transaction state to the current thread via `TransactionSynchronizationManager`. A remote HTTP request could even hit **another process**; never design tests assuming cross-network transactions.

### 2.2. Synchronous MockMvc: usually the same thread

~~~text
JUnit thread, @Transactional test [TX-T]
    |
    +-- MockMvc.perform(POST /orders)
    |      -> DispatcherServlet mock request
    |      -> Controller
    |      -> Service @Transactional(REQUIRED)
    |      -> joins TX-T (same thread)
    |      -> INSERT order, not yet committed
    |
    +-- repository query on same test transaction sees the row
    |
    +-- test method ends
           -> TX-T ROLLBACK
           -> order disappears
~~~

With synchronous `MockMvc` and `REQUIRED` propagation, request processing typically shares the thread and can join the test-managed transaction. That is a **convenience for slice/integration tests without a running server**, not a faithful model of a production HTTP request's commit boundary. If the controller uses `@Async`, async servlet dispatch, `REQUIRES_NEW`, message brokers, or external services, the transaction boundary changes.

### 2.3. What makes up a Spring test transaction?

When JUnit/Spring TestContext runs a transactional test method:
- `TransactionalTestExecutionListener` starts a **test-managed transaction** before `@BeforeEach`/`@Test`.
- `@BeforeTransaction` runs **outside and before** the test transaction.
- `@BeforeEach` and `@AfterEach` run **inside** the test-managed transaction when the test method uses `@Transactional`.
- By default the test transaction **rolls back**, unless configured with `@Commit`/`@Rollback(false)` or `TestTransaction.flagForCommit()`.
- `@AfterTransaction` runs **after** the test transaction completes; this is the right place to verify committed state or run cleanup that must escape the outer transaction.

Never assume `@AfterEach` always runs outside a transaction. That is a very common cleanup mistake.

### 2.4. An easy-to-remember comparison table

| Test setup | Test thread transaction | Server transaction | Does server write roll back with test? |
| --- | --- | --- | --- |
| Non-Spring unit test | None unless manually created | No HTTP server | Not applicable |
| `@JdbcTest`, transactional by default | Yes | No HTTP request | Writes in test TX roll back |
| `@SpringBootTest(MOCK)` + synchronous MockMvc + `@Transactional` | Yes | Service `REQUIRED` may join test TX | Usually yes |
| `@SpringBootTest(RANDOM_PORT)` + `@Transactional` | Yes, on client/test thread | Independent TX on server thread | **No** |
| `@SpringBootTest(RANDOM_PORT)` without `@Transactional` | No | Server-side service TX | No; must clean up |
| Async worker / message consumer | Does not propagate automatically | Worker's own independent TX | Does not auto-roll back with test TX |
| Service `REQUIRES_NEW` called from same-thread MockMvc | Outer test TX temporarily suspended | New service TX commits independently | No if inner TX commits |

“Usually yes” for MockMvc depends on synchronous execution, propagation, and DB/client paths. Do not turn this table into a promise that every MockMvc call always runs in one transaction.

## 3. Why seemingly correct tests still leave data behind

### 3.1. Common anti-pattern

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrdersHttpTest {

    @Autowired TestRestTemplate http;

    @Test
    void createsOrder() {
        http.postForEntity(
                "/orders",
                new CreateOrderRequest("fixed-123", "alice", 2),
                OrderRecord.class);
    }

    // No cleanup.
}
~~~

This is a counter-example snippet, not a file from the lab project. `@Transactional` rolls back only operations on the **test thread**. The POST crossed a real network boundary and the server can commit. A subsequent test run using `fixed-123` can hit duplicate-key errors, creating order dependency and data residue.

### 3.2. `@AfterEach` can still roll back a DELETE

A treacherous variation:

~~~java
@AfterEach
void cleanup() {
    repository.deleteById("fixed-123");
}
~~~

If the class or test method has `@Transactional`, `@AfterEach` still executes **inside the test-managed transaction**. It can see the server-committed row and temporarily delete it, yet when the test transaction rolls back, **the DELETE also rolls back**; the original row stays in the table. Seeing `DELETE FROM orders` in SQL logs does not mean cleanup committed.

Use one of two patterns instead:
- **Recommended for real HTTP tests:** omit `@Transactional` on the test, generate unique IDs, and clean up via the repository in `@AfterEach` using autocommit or an explicit committed transaction.
- **When intentionally demonstrating the TX boundary:** use `@AfterTransaction` or an independent committed `TransactionTemplate` transaction; use a local marker in the test only for contrast.

### 3.3. `@DirtiesContext` does not erase a database

`@DirtiesContext` closes/discards the cached Spring `ApplicationContext`. It **does not mean** rows in an external PostgreSQL DB, Redis keys, Kafka offsets, or persisted files vanish. If the DB happens to be an in-memory H2 instance tied solely to that context and not kept alive externally, closing the context can make state disappear — yet that is a DB-lifecycle side effect, **not a data cleanup contract**. Against any real database server, the next context sees all old rows.

### 3.4. Passing alone, failing in the suite

Typical causes:
- Same fixed ID across multiple methods/classes.
- A POST test succeeds without post-commit cleanup.
- An `@Sql` delete script executes inside a transaction that gets rolled back.
- Parallel tests run a whole-table `DELETE FROM orders`.
- Test A spawns an unfinished async worker and `@AfterEach` cleans up too early.
- JPA entities remain in the persistence context, so assertions read cache instead of fresh DB state.
- A reused Testcontainers backend still contains old schema/data.
- Method execution order masks hidden dependencies.

Investigate **what remains in the DB after the client TX ends**, not just HTTP statuses or green JUnit checkmarks.

## 4. A two-sided measurement plan to prove the boundary

We do not rely on thread names alone to guess whether transactions differ. We prove it directly via **database state**:

1. `@BeforeTransaction` generates two unique IDs: `clientMarkerId` and `httpOrderId`.
2. Inside the test-managed TX, JDBC directly inserts the **client marker**.
3. From the same test method, send a real `POST /orders` via `TestRestTemplate` so the server creates the **HTTP order**.
4. The HTTP server's service is `@Transactional` and returns 201 after completing.
5. The test-managed transaction finishes with a rollback.
6. In `@AfterTransaction`, query the database using a fresh connection/transaction.
7. Assert **client marker does not exist** due to rollback.
8. Assert **HTTP order still exists** because it committed on the server thread.
9. Use `finally` to delete both IDs outside the test transaction.
10. Query again to verify cleanup succeeded.

~~~text
Measured after test-managed rollback:

    client_marker_id -> COUNT(*) = 0
    http_order_id    -> COUNT(*) = 1

Measured after committed cleanup:

    client_marker_id -> COUNT(*) = 0
    http_order_id    -> COUNT(*) = 0
~~~

This is direct measurement of the invariant, avoiding conclusions drawn from stack traces or assumptions that “Spring rolls back everything”.

## 5. Maven project: Spring Boot 3.5.16 + Java 17 + H2 + JDBC

### 5.1. Lab functionality

The sample API manages order records:
- `POST /orders` creates an order and returns 201.
- `GET /orders/{id}` reads by ID, returning 200/404.
- `POST /orders/rollback` inserts inside a service transaction then intentionally throws a `RuntimeException`; the handler returns 500 and the database must roll back the server-side insert.
- Duplicate primary key returns 409, leaving the original row unchanged.
- Input validation `quantity < 1` returns 400 and inserts nothing.

Three test classes clarify the contrasting contexts:
1. `RealHttpCleanupIntegrationTest`: real HTTP, **no** test-level transaction; `@AfterEach` targeted cleanup (4 tests).
2. `RealHttpRollbackBoundaryTest`: real HTTP, **with** a test-level transaction; `@BeforeTransaction`/`@AfterTransaction` prove the client marker rolls back while the server order survives, followed by post-TX cleanup (1 test).
3. `MockMvcRollbackContrastTest`: synchronous MockMvc, **with** a test-level transaction; asserts the row exists during the TX yet disappears after rollback (1 test).

Total **6 expected JUnit test methods**. H2 keeps the learning setup lightweight without Docker; for invariants involving locking, isolation, sequences, or vendor dialects, run equivalent tests on PostgreSQL Testcontainers.

### 5.2. Directory tree

~~~text
http-rollback-cleanup-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/httpcleanup/
│   │   ├── HttpCleanupApplication.java
│   │   ├── CreateOrderRequest.java
│   │   ├── OrderRecord.java
│   │   ├── OrderRepository.java
│   │   ├── OrderService.java
│   │   └── OrderController.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/java/com/example/httpcleanup/
    ├── RealHttpCleanupIntegrationTest.java
    ├── RealHttpRollbackBoundaryTest.java
    └── MockMvcRollbackContrastTest.java
~~~

All Java files live under package `com.example.httpcleanup`. The main class sits at the module's root package so Spring Boot component-scans the repository, service, and controller. No mocks or external HTTP dependencies exist outside the test-started server.

### 5.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>http-rollback-cleanup-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Dependency notes:
- `spring-boot-starter-web` provides Servlet Spring MVC and JSON/Jackson.
- `spring-boot-starter-jdbc` provides `JdbcTemplate`, `DataSourceTransactionManager`/JDBC transaction manager, and Hikari.
- `spring-boot-starter-validation` activates validation annotations on request DTOs.
- `h2` runtime makes the lab DB easy to run, **not equivalent to production PostgreSQL for isolation/locking**.
- `spring-boot-starter-test` includes JUnit 5, AssertJ, Spring Test, MockMvc, and `TestRestTemplate` in **Spring Boot 3.5.x**.
- Spring Boot parent/BOM aligns Spring Framework/Jackson/JUnit versions.
- Java 17 is the sample minimum; no Docker is required for the core lab.

### 5.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=http-rollback-cleanup-lab
spring.main.banner-mode=off

spring.datasource.url=jdbc:h2:mem:http_cleanup_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.connection-timeout=10000

spring.sql.init.mode=always
server.address=127.0.0.1

logging.level.org.springframework.transaction=INFO
logging.level.org.springframework.jdbc.core=INFO
~~~

**Why `DB_CLOSE_DELAY=-1`?** The H2 in-memory database stays alive inside the same JVM even when the last JDBC connection closes. This allows all Spring contexts in the lab to see the same database, while emphasizing that **context close or test rollback does not automatically clean the DB**. Tests never depend on class order or a “freshly recreated” database name.

Do not set `server.port=8080`. `@SpringBootTest(RANDOM_PORT)` selects a dynamic port; `MOCK` opens no real server. `server.address=127.0.0.1` restricts the test server to loopback.

This config is for the lab; production uses proper DB migrations/versioning rather than H2 `schema.sql` and an empty password.

### 5.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS demo_orders (
    order_id VARCHAR(100) PRIMARY KEY,
    owner_tag VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 1)
);
~~~

Small schema designed to distinguish:
- **Primary key** preventing duplicate order IDs.
- **Non-null owner tag** providing a cleanup namespace.
- **CHECK constraint** protecting quantity in the database, beyond HTTP boundary validation.
- `IF NOT EXISTS` keeps schema init idempotent on the shared H2 lab DB. In production, use versioned Flyway/Liquibase migrations rather than relying on this clause as a migration strategy.

Each test creates a unique ID; cleanup uses `WHERE order_id = ?`. No runnable test executes a whole-table `DELETE FROM demo_orders`.

### 5.6. HttpCleanupApplication.java

`src/main/java/com/example/httpcleanup/HttpCleanupApplication.java`:

~~~java
package com.example.httpcleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCleanupApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                HttpCleanupApplication.class, args);
    }
}
~~~

No schedulers or async listeners are enabled by default in the lab; this keeps persistence behavior after an HTTP response synchronous and deterministic.

### 5.7. CreateOrderRequest.java

`src/main/java/com/example/httpcleanup/CreateOrderRequest.java`:

~~~java
package com.example.httpcleanup;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
        @NotBlank String id,
        @NotBlank String owner,
        @Min(1) int quantity) {
}
~~~

This Java 17 record is bound by Jackson from JSON. `@Valid` on the controller triggers Bean Validation on the request:
- `id` and `owner` must not be blank.
- `quantity >= 1`.
- If the input is invalid, Spring MVC returns 400 by default for `MethodArgumentNotValidException`, and the service is not invoked.
- Validation only guards the request boundary; database `CHECK` constraints are still necessary if any code path inserts outside HTTP.

Do not reuse a fixed ID across multiple test runs.

### 5.8. OrderRecord.java

`src/main/java/com/example/httpcleanup/OrderRecord.java`:

~~~java
package com.example.httpcleanup;

public record OrderRecord(
        String id,
        String owner,
        int quantity) {
}
~~~

This is a simple DTO/row projection. In a real application, separate domain entities, DTOs, and persistence models, and avoid returning PII or internal fields.

### 5.9. OrderRepository.java

`src/main/java/com/example/httpcleanup/OrderRepository.java`:

~~~java
package com.example.httpcleanup;

import java.util.Objects;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(OrderRecord order) {
        return jdbc.update(
                "INSERT INTO demo_orders "
                        + "(order_id, owner_tag, quantity) "
                        + "VALUES (?, ?, ?)",
                order.id(),
                order.owner(),
                order.quantity());
    }

    public Optional<OrderRecord> findById(String id) {
        return jdbc.query(
                "SELECT order_id, owner_tag, quantity "
                        + "FROM demo_orders WHERE order_id = ?",
                (rs, rowNum) -> new OrderRecord(
                        rs.getString("order_id"),
                        rs.getString("owner_tag"),
                        rs.getInt("quantity")),
                id)
                .stream()
                .findFirst();
    }

    public long countById(String id) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_orders "
                        + "WHERE order_id = ?",
                Long.class,
                id);

        return Objects.requireNonNull(count);
    }

    public int deleteById(String id) {
        return jdbc.update(
                "DELETE FROM demo_orders WHERE order_id = ?",
                id);
    }
}
~~~

`JdbcTemplate` joins the Spring transaction **bound to the calling thread**:
- When `insert` is called from a JUnit thread with an active test-managed TX, the JDBC operation runs inside the test TX.
- When called by a service on a servlet server thread with its own `@Transactional`, the operation runs inside the server transaction.
- When `deleteById` is called outside a transaction in a non-`@Transactional` test, Hikari/JDBC auto-commit normally commits the statement immediately.
- When called in `@AfterTransaction` (outside the test TX), the cleanup statement does not roll back with the already-ended test transaction.
- If an app uses custom explicit transaction managers or connections, verify behavior explicitly instead of assuming defaults.

The repository keeps no in-memory Java Map cache; every assertion reads the real DB via JDBC.

### 5.10. OrderService.java

`src/main/java/com/example/httpcleanup/OrderService.java`:

~~~java
package com.example.httpcleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public OrderRecord create(CreateOrderRequest request) {
        OrderRecord created = new OrderRecord(
                request.id(),
                request.owner(),
                request.quantity());

        repository.insert(created);
        return created;
    }

    @Transactional
    public void createThenFail(
            CreateOrderRequest request) {

        repository.insert(new OrderRecord(
                request.id(),
                request.owner(),
                request.quantity()));

        throw new IllegalStateException(
                "forced rollback before commit");
    }
}
~~~

**Transaction semantics:**
- The controller calls `OrderService` through a Spring proxy, so `@Transactional` applies.
- `create` succeeds and Spring's transaction manager commits **before returning to the controller**.
- `createThenFail` throws unchecked `IllegalStateException`; Spring rolls back the service transaction by default without committing the insert.
- The error handler returns 500 **after** the exception has exited the transaction interceptor, so the handler never turns a rollback into a commit.
- If an exception is caught **inside** a transactional service and returns normally without marking rollback-only, the transaction can commit; tests must prove real DB state, not just HTTP 500.

In production code, use domain-specific exceptions and appropriate 4xx/5xx status mapping; here 500 intentionally models an internal failure before commit.

### 5.11. OrderController.java

`src/main/java/com/example/httpcleanup/OrderController.java`:

~~~java
package com.example.httpcleanup;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderRepository repository;

    public OrderController(
            OrderService service,
            OrderRepository repository) {
        this.service = service;
        this.repository = repository;
    }

    @PostMapping
    public ResponseEntity<OrderRecord> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderRecord created = service.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderRecord> get(
            @PathVariable String id) {

        return repository.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() ->
                        ResponseEntity.notFound().build());
    }

    @PostMapping("/rollback")
    public ResponseEntity<Void> rollback(
            @Valid @RequestBody CreateOrderRequest request) {

        service.createThenFail(request);
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, String>> conflict(
            DataIntegrityViolationException ignored) {

        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(Map.of("code", "ORDER_CONFLICT"));
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<Map<String, String>> failed(
            IllegalStateException ignored) {

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "ORDER_ROLLED_BACK"));
    }
}
~~~

The code uses standard Spring MVC APIs:
- `POST /orders` returns 201.
- `GET /orders/{id}` returns 200 when a row exists, 404 when absent.
- `POST /orders/rollback` invokes the service and maps the exception to 500.
- Duplicate PK `DataIntegrityViolationException` from JDBC maps to 409.
- Invalid input is rejected with 400 by `@Valid`/Spring MVC before the service.
- Error responses do not leak stack traces, passwords, or internal SQL to clients.

This is an HTTP-layer demonstration. Crucial assertions in the tests below still inspect **database state**, never inferring rollback from HTTP status alone.

## 6. Test 1: Real HTTP, no `@Transactional`, cleanup after request

### 6.1. RealHttpCleanupIntegrationTest.java

`src/test/java/com/example/httpcleanup/RealHttpCleanupIntegrationTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpCleanupIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository repository;

    private String orderId;

    @BeforeEach
    void uniqueDataPerMethod() {
        orderId = "http_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void deleteOnlyThisTestsRow() {
        if (orderId != null) {
            repository.deleteById(orderId);

            assertThat(repository.countById(orderId))
                    .as("targeted cleanup committed")
                    .isZero();
        }
    }

    @Test
    void post201PersistsAndGetReadsCommittedRow() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 3);

        ResponseEntity<OrderRecord> created =
                http.postForEntity(
                        "/orders",
                        request,
                        OrderRecord.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(created.getBody())
                .isEqualTo(new OrderRecord(
                        orderId, "http-test", 3));

        // Query via repository independently of controller code path:
        assertThat(repository.countById(orderId))
                .isEqualTo(1L);

        ResponseEntity<OrderRecord> loaded =
                http.getForEntity(
                        "/orders/{id}",
                        OrderRecord.class,
                        orderId);

        assertThat(loaded.getStatusCode())
                .isEqualTo(HttpStatus.OK);

        assertThat(loaded.getBody())
                .isEqualTo(created.getBody());
    }

    @Test
    void serverExceptionRollsBackItsOwnInsert() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 5);

        ResponseEntity<String> failed =
                http.postForEntity(
                        "/orders/rollback",
                        request,
                        String.class);

        assertThat(failed.getStatusCode())
                .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);

        // HTTP 500 by itself does NOT prove rollback.
        assertThat(repository.countById(orderId))
                .isZero();

        ResponseEntity<String> notFound =
                http.getForEntity(
                        "/orders/{id}",
                        String.class,
                        orderId);

        assertThat(notFound.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void invalidPayloadCannotInsert() {

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "http-test", 0);

        ResponseEntity<String> invalid =
                http.postForEntity(
                        "/orders",
                        request,
                        String.class);

        assertThat(invalid.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(repository.countById(orderId))
                .isZero();
    }

    @Test
    void duplicateKeyReturns409WithoutReplacingOriginal() {

        CreateOrderRequest first =
                new CreateOrderRequest(
                        orderId, "http-test", 2);

        ResponseEntity<OrderRecord> created =
                http.postForEntity(
                        "/orders",
                        first,
                        OrderRecord.class);

        assertThat(created.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        CreateOrderRequest duplicate =
                new CreateOrderRequest(
                        orderId, "http-test", 99);

        ResponseEntity<String> conflict =
                http.postForEntity(
                        "/orders",
                        duplicate,
                        String.class);

        assertThat(conflict.getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);

        assertThat(repository.findById(orderId))
                .contains(new OrderRecord(
                        orderId, "http-test", 2));

        assertThat(repository.countById(orderId))
                .isEqualTo(1L);
    }
}
~~~

### 6.2. What these tests prove

**Test `post201`:**
- Request traverses a **real embedded HTTP server**.
- Service transaction commits before the controller returns a success response.
- Independent repository query sees the row.
- GET endpoint reads the row as well.
- `@AfterEach` deletes only the row with this test's ID.

**Test `rollback`:**
- Server service inserts then throws an exception inside the transaction.
- HTTP handler returns 500, yet assertions do not stop at status.
- Direct DB query confirms zero rows.
- GET returns 404.
- No test-managed transaction accidentally masks server rollback behavior.

**Test `validation`:**
- `quantity=0` is rejected at the MVC boundary.
- Zero rows created.
- Does not rely on the database CHECK constraint as the sole proof of 400.

**Test `duplicate`:**
- First insert succeeds.
- Second insert with the same PK is rejected by JDBC, returning HTTP 409.
- Original row retains `quantity=2` without being overwritten.
- Cleanup deletes the existing row cleanly.

### 6.3. Why is `@AfterEach` cleanup safe here?

The class does **not** place `@Transactional` on the test or class. When `repository.deleteById(orderId)` runs after the response:
- No test-managed TX wraps `@AfterEach`.
- The JDBC statement borrows a connection, executes the delete, and commits under default autocommit in the lab.
- The test re-reads `COUNT(*)=0` to verify the delete took effect.
- Unique IDs avoid interfering with other methods or classes.

**No whole-table cleanup occurs.** If a test fails after HTTP POST and before assertions, `@AfterEach` still gets a chance to delete its own ID. If the JVM is killed or the server crashes mid-run, callbacks may not run; CI environment cleanup, TTLs, or schema isolation handle hard aborts.

### 6.4. Risk if repository auto-commit differs from expectations

If you add an outer transaction, a custom `PlatformTransactionManager`, or a datasource with autocommit disabled, a targeted delete might not commit. In that situation:
- Explicitly identify the cleanup transaction boundary.
- Use `TransactionTemplate.executeWithoutResult(...)` for an explicit commit.
- Or run `@Sql(..., transactionMode=ISOLATED)` with an appropriately scoped script.
- Verify with a **post-commit query** on a fresh connection.

Never slap `@Transactional` onto the entire test class just because it “looks like standard integration testing”; that annotation changes cleanup lifecycle.

## 7. Test 2: Proving two different fates after rollback

### 7.1. RealHttpRollbackBoundaryTest.java

`src/test/java/com/example/httpcleanup/RealHttpRollbackBoundaryTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class RealHttpRollbackBoundaryTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository repository;

    private String clientMarkerId;
    private String httpOrderId;
    private boolean httpCreated;

    @BeforeTransaction
    void createIdsOutsideTheTestTransaction() {
        clientMarkerId = "client_" + UUID.randomUUID()
                .toString().replace("-", "");
        httpOrderId = "server_" + UUID.randomUUID()
                .toString().replace("-", "");
        httpCreated = false;
    }

    @Test
    void testThreadRollbackCannotUndoCommittedHttpWrite() {

        // Inside test-managed transaction [TX-T]:
        repository.insert(new OrderRecord(
                clientMarkerId, "client-marker", 1));

        assertThat(repository.countById(clientMarkerId))
                .isEqualTo(1L);

        // Real HTTP uses a server thread and transaction [TX-S].
        ResponseEntity<OrderRecord> response =
                http.postForEntity(
                        "/orders",
                        new CreateOrderRequest(
                                httpOrderId, "server-request", 7),
                        OrderRecord.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        assertThat(response.getBody())
                .isEqualTo(new OrderRecord(
                        httpOrderId, "server-request", 7));

        httpCreated = true;

        // Do not call repository.delete() here.
        // Test thread [TX-T] will roll back automatically after the method.
    }

    @AfterTransaction
    void compareCommittedStatesAndCleanupAfterRollback() {
        if (clientMarkerId == null || httpOrderId == null) {
            return;
        }

        try {
            // Marker created on the test thread must vanish
            // after the test-managed transaction rolls back.
            assertThat(repository.countById(clientMarkerId))
                    .as("test-thread marker was rolled back")
                    .isZero();

            if (httpCreated) {
                // Row committed by the server-side transaction,
                // unaffected by TX-T rollback.
                assertThat(repository.countById(httpOrderId))
                        .as("HTTP server write remained committed")
                        .isEqualTo(1L);
            }
        }
        finally {
            // @AfterTransaction runs OUTSIDE TX-T.
            // Targeted cleanup runs even if an assertion fails.
            repository.deleteById(httpOrderId);
            repository.deleteById(clientMarkerId);
        }

        assertThat(repository.countById(clientMarkerId))
                .isZero();

        assertThat(repository.countById(httpOrderId))
                .isZero();
    }
}
~~~

### 7.2. Meaningful checkpoints

| Checkpoint | clientMarkerId | httpOrderId |
| --- | --- | --- |
| Before test | Absent | Absent |
| During test, after inserting marker | Present in TX-T, uncommitted | Absent |
| After real HTTP POST 201 | Present in TX-T | Committed via TX-S |
| `@AfterTransaction` after default rollback | **0** | **1** |
| After cleanup outside TX-T | **0** | **0** |

This test **intentionally** uses `@Transactional` to demonstrate that rollback applies only to the JUnit thread's marker; the HTTP order stays committed. In an ordinary integration suite, omitting `@Transactional` and using the cleanup pattern from the previous class is simpler.

### 7.3. Why is `@BeforeTransaction` needed?

`@BeforeTransaction` runs **before** the test-managed TX. In the lab it generates IDs without writing to the DB. It can also:
- Check database baseline from a connection outside the test TX.
- Seed fixtures that must be committed before the HTTP request runs.
- Measure the pre-test count.
- Verify no stale row from an earlier run exists when IDs have external lifecycles.

**Be careful:** inserting a fixture in `@BeforeEach` of a transactional test normally leaves it inside TX-T so **the server thread cannot read uncommitted data**. That is a frequent cause of 404 or foreign-key failures in real HTTP tests.

### 7.4. Why is `@AfterTransaction` needed?

This callback runs after the test transaction ends. Therefore:
- Queries are outside the old TX-T.
- It sees the true persisted state post-rollback.
- Cleanup commits independently via JdbcTemplate/lab autocommit.
- `finally` ensures cleanup even if assertions fail.

Using `@AfterEach` in the same class runs **inside TX-T**, meaning a DELETE on the HTTP row can roll back and leave the row behind. Hence we **never** put server-row cleanup in `@AfterEach` on this class.

### 7.5. Why does the `httpCreated` flag exist?

An HTTP request can fail before the server processes it completely. If the test body never received HTTP 201, we cannot confidently assert the server order committed. `httpCreated` becomes true only after a 201 response. Yet `finally` still attempts to delete the order ID even after mid-flight request/response errors, reducing the chance of leftover data if the server committed while the client lost the response.

Network timeouts where server work continues **after** cleanup are harder: they require operation IDs, idempotency, and completion/settling protocols rather than `@AfterTransaction` or sleeps. The lab intentionally uses a synchronous service call to keep the contract crisp.

### 7.6. An important detail on test method failures

If an HTTP response assertion fails, `@AfterTransaction` still runs during normal test lifecycle to clean up. If the JVM is killed or times out hard, callbacks are not guaranteed. Cleanup is a testing mechanism, not a durable production compensation pattern. For unstable test servers, isolate DBs/containers per run.

## 8. Test 3: Synchronous MockMvc can roll back together with the JUnit test

### 8.1. MockMvcRollbackContrastTest.java

`src/test/java/com/example/httpcleanup/MockMvcRollbackContrastTest.java`:

~~~java
package com.example.httpcleanup;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class MockMvcRollbackContrastTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    OrderRepository repository;

    private String orderId;

    @Test
    void synchronousMockMvcRequestJoinsTestTransaction()
            throws Exception {

        orderId = "mock_" + UUID.randomUUID()
                .toString().replace("-", "");

        CreateOrderRequest request =
                new CreateOrderRequest(
                        orderId, "mock-test", 4);

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                objectMapper.writeValueAsString(
                                        request)))
                .andExpect(status().isCreated());

        // Synchronous MockMvc processes the request on the test thread.
        // @Transactional(REQUIRED) service joins the test TX.
        assertThat(repository.countById(orderId))
                .isEqualTo(1L);
    }

    @AfterTransaction
    void verifyNoCommittedRowAfterTestRollback() {
        if (orderId == null) {
            return;
        }

        try {
            assertThat(repository.countById(orderId))
                    .as("synchronous MockMvc write rolled back")
                    .isZero();
        }
        finally {
            // Safety cleanup only, in case implementation changes.
            repository.deleteById(orderId);
        }
    }
}
~~~

### 8.2. Comparing with real HTTP

Synchronous `MockMvc.perform` invokes the Servlet/MVC chain in the test process and usually on the same test thread. The `@Transactional` service uses default `REQUIRED` propagation, so the JDBC write can join TX-T. The test method sees the row inside the transaction, yet `@AfterTransaction` confirms the row vanished.

Real HTTP:
- Request goes over a socket.
- Server worker thread owns TX-S.
- TX-S commits independently.
- TX-T rollback has no effect on the server order.

**Never mistake a passing MockMvc test as proof that production HTTP requests auto-roll back with JUnit tests.** MockMvc is very valuable for controllers, filters, JSON, and security, yet **has a different boundary** and can fail to catch data residue from actual HTTP requests.

### 8.3. When MockMvc no longer shares the same transaction

Things that alter that behavior:
- Async servlet controllers/`Callable`/`DeferredResult` dispatching to another worker thread.
- `@Async` dispatches from the service.
- Service `REQUIRES_NEW`, explicit `TransactionTemplate`, or a different transaction manager.
- DB calls over message brokers or remote services.
- Reactive R2DBC context propagation rather than imperative `ThreadLocal`.
- Tests using `@Transactional(propagation=NOT_SUPPORTED)`/`TestTransaction.end()`.

On those paths, explicitly verify the transaction context and committed state. Never claim every MockMvc execution “always rolls back”.

## 9. Running the lab and reading reports properly

### 9.1. Prerequisites

- JDK 17+.
- Apache Maven.
- Dependencies downloadable from Maven Central/local cache.
- No Docker needed (in-memory H2).
- HTTP port assigned dynamically by the OS, no need to hardcode 8080.

### 9.2. Run commands

~~~bash
mvn -q clean test

mvn -q -Dtest=RealHttpCleanupIntegrationTest test

mvn -q -Dtest=RealHttpRollbackBoundaryTest test

mvn -q -Dtest=MockMvcRollbackContrastTest test
~~~

**Designed test method count:**
- `RealHttpCleanupIntegrationTest`: 4.
- `RealHttpRollbackBoundaryTest`: 1.
- `MockMvcRollbackContrastTest`: 1.
- Total **6** JUnit methods when fully discovered and executed by Surefire.

Key assertions:
- Real HTTP 201 → row exists after response → targeted cleanup = 0.
- Real HTTP 500 from service exception → database row = 0.
- Real HTTP 400 invalid request → database row = 0.
- Real HTTP 409 duplicate → original row intact.
- Real HTTP + test-managed `@Transactional` → test marker rollback = 0, server row = 1 **after TX rollback**, cleanup = 0.
- Synchronous MockMvc + test-managed `@Transactional` → row inside TX = 1, after rollback = 0.

### 9.3. Do not claim unexecuted results

Code snippets follow Java 17 / Spring Boot 3.5.16 APIs and were reviewed for structure, imports, and flow. However, **Maven/JUnit was not executed while authoring this lesson**; the figures above are **expectations to verify when running**, not an observed `Tests run: 6, Failures: 0` report.

When actually running:
- Inspect Maven's exit code.
- Inspect `target/surefire-reports`.
- Check executed, failed, errors, and skipped counts.
- Verify no lingering rows remain for test IDs.
- Do not rely solely on “BUILD SUCCESS” if tests were skipped or failed on rerun.

### 9.4. Observing transactions through logs

When investigating, turn on test-only logging:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.jdbc.support.JdbcTransactionManager=DEBUG
logging.level.org.springframework.test.context.transaction=DEBUG
~~~

Exact loggers depend on Spring version and transaction manager; not every category necessarily logs. Goals:
- Correlate transaction begin/commit/rollback with thread names and service methods.
- Observe test-managed rollback on the JUnit thread.
- Observe service transaction commit on the HTTP worker.
- Never log credentials or PII.
- Never assert exact framework log strings as a business contract; use database state as the primary evidence.

### 9.5. Asserting the HTTP response is only the first step

HTTP 201 does not prove **durable data** if the application:
- Returns a response before async writes complete.
- Writes to an in-memory cache without committing to the DB.
- Publishes an event to a broker before a consumer processes it.
- Swallows an exception and returns 201.
- Uses fire-and-forget `@Async`.

The lab uses a synchronous `@Transactional` service and JDBC insert. If a real application uses async processing, await the proper completion/idempotency/commit signal and inspect the DB on an independent connection.

## 10. Why doesn't `@Transactional` cross threads?

### 10.1. `TransactionSynchronizationManager`

Spring's imperative transaction management stores resource bindings and transaction metadata per thread. In practice:
- `DataSourceTransactionManager`/`JdbcTransactionManager` binds a `ConnectionHolder` to the thread.
- `JdbcTemplate` acquires the current connection through Spring datasource utilities.
- `@Transactional` proxies begin, join, or suspend transactions on the calling thread.
- That `ThreadLocal` is **never automatically copied** to a Tomcat HTTP worker thread or executor thread.

An outbound HTTP request cannot carry an open JDBC `Connection` from the test thread over a socket and magically enlist the server's JDBC connection into the same TX. Distributed transactions require dedicated protocols/schemes; normal REST apps do not use them.

### 10.2. Does `@Transactional` on the controller make a difference?

If a controller method has `@Transactional`, that transaction still belongs to the **server thread**. It may span the controller/service flow, yet remains **independent of the JUnit test transaction**. Therefore do not propose “add `@Transactional` to the controller” as a cleanup fix after HTTP tests.

### 10.3. `Propagation.REQUIRED`

When a transactional service method is invoked on a thread that already has a transaction:
- Default `REQUIRED` joins the active transaction.
- Under synchronous MockMvc inside a test-managed TX, the service can join it.
- Under a real HTTP server thread without a test TX, the service opens a new transaction.

Hence the **same annotation** produces different external state; behavior depends on the **caller thread and active transaction**, not the annotation name alone.

### 10.4. `Propagation.REQUIRES_NEW`

`REQUIRES_NEW` normally suspends the outer transaction and opens a separate physical transaction. In a same-thread MockMvc test, a `REQUIRES_NEW` service can commit data that the test transaction's rollback **cannot** undo. To test this boundary, write a dedicated test and clean up after the TX; never introduce `REQUIRES_NEW` casually and expect default rollback to clean up all rows.

### 10.5. `Propagation.NESTED`

`NESTED` uses savepoints when supported by the transaction manager and database, which does not mean “a new remote/HTTP transaction”. Nested rollback may revert only to a savepoint inside the parent TX, while real commit still depends on the parent transaction. JDBC and JPA managers differ in support. Do not confuse it with `REQUIRES_NEW`.

### 10.6. `@Rollback` and `@Commit`

Spring test annotations:
- `@Rollback` or `@Rollback(true)`: rolls back the test-managed TX.
- `@Rollback(false)` / `@Commit`: commits the test-managed TX.
- They **do not control** an independent HTTP server thread's transaction.
- On a non-transactional test method, they do not magically create a TX.
- Using `@Commit` on tests can persist test data, requiring stronger cleanup.

Do not sacrifice isolation just to “test commit” without clear post-test cleanup.

### 10.7. `TestTransaction`

Spring TestContext provides `TestTransaction` to control the **test-managed transaction**:
- `isActive()`.
- `flagForRollback()` / `flagForCommit()`.
- `end()`.
- `start()`.

Illustrative example (not part of the three runnable test classes):

~~~java
@Test
@Transactional
void inspectCommittedStateOutsideCurrentTestTx() {
    // test transaction is active
    assertThat(TestTransaction.isActive()).isTrue();

    TestTransaction.flagForRollback();
    TestTransaction.end();

    assertThat(TestTransaction.isActive()).isFalse();

    // Queries here run outside the test transaction,
    // reading committed DB state from a new connection.

    TestTransaction.start();
    // New test transaction will roll back when the method ends.
}
~~~

This snippet requires Spring TestContext/JUnit/AssertJ imports and a configured transactional Spring test context. It **does not commit or roll back server TX-S over HTTP**; it only shifts the test thread's own perspective. Never call `end()` without an active test transaction.

### 10.8. Preemptive timeouts and transaction visibility

Spring Framework warns that test-managed TXs are thread-bound. APIs executing bodies on another thread (such as JUnit's `assertTimeoutPreemptively(...)` or certain timeout modes) escape the test TX; writes will not roll back as expected. Use bounded waits and non-preemptive timeouts when testing transaction semantics, then verify committed DB state after the transaction completes.

## 11. Scoped data cleanup

### 11.1. Approach 1: unique ID + targeted delete

Suited to most HTTP integration tests:

~~~java
@BeforeEach
void setUp() {
    id = UUID.randomUUID().toString();
}

@AfterEach
void cleanup() {
    repository.deleteById(id);
}
~~~

**Mandatory condition:** cleanup must run outside any test-managed transaction or inside its own committed transaction. If the class has `@Transactional`, `@AfterEach` violates that condition.

Advantages:
- Never deletes other tests' data.
- Compatible with parallel tests.
- Tests own their fixtures.
- Easy to trace leftover rows by ID.
- Avoids restarting the application context or container.

Limitations:
- If the entity has many FK/child rows, cleanup must follow dependency order or proper cascades.
- If async operations are still running, delete can run too early.
- If the process crashes, callbacks do not execute.
- With materialized views, outboxes, or caches, deleting the main row alone is not enough.
- If DB isolation requires a dedicated transaction, use an explicit boundary.

### 11.2. Approach 2: post-transaction cleanup via `@AfterTransaction`

Suited when **intentionally testing rollback boundaries** like `RealHttpRollbackBoundaryTest`:
- JUnit rolls back the test TX first.
- `@AfterTransaction` observes committed state.
- Cleanup executes outside the test TX.
- Post-cleanup assertions run.

Wrap cleanup in `finally` in case state assertions fail. `@AfterTransaction` does not fire on non-transactional tests. Never put it on a class without `@Transactional` expecting the callback to execute.

### 11.3. Approach 3: `TransactionTemplate`

When explicit cleanup is needed, especially when a test has an outer TX:
- Inject the appropriate `PlatformTransactionManager`.
- Choose the propagation behavior.
- Use `TransactionTemplate` to open a dedicated committed transaction, possibly `PROPAGATION_REQUIRES_NEW` to separate from the outer transaction.
- Watch for database locks: the outer TX may hold locks causing the cleanup transaction to wait or time out; executing after the outer TX finishes is cleaner.
- Verify cleanup using a query outside the cleanup transaction.

Illustrative example in an integration test with a configured transaction manager:

~~~java
TransactionTemplate cleanup = new TransactionTemplate(txManager);
cleanup.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

cleanup.executeWithoutResult(status ->
        repository.deleteById(orderId));
~~~

This snippet is **not** magical cross-thread cleanup; it opens a transaction **on the calling thread**. Ensure no outer test-managed transaction is holding conflicting locks that cause deadlocks. Placing cleanup in `@AfterTransaction` lets the new transaction commit more cleanly.

### 11.4. Approach 4: `@Sql` `AFTER_TEST_METHOD`

Spring TestContext supports:

~~~java
@Sql(
    scripts = "/cleanup-owned-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Test
void writesCommittedDataThroughHttp() {
    // ...
}
~~~

**This is an illustrative snippet**; there is no SQL script file in the Maven project. Cleanup scripts must match a test's **exclusive** fixture namespace; static SQL annotations do not easily accept runtime `UUID`s. Use a dedicated test schema/database when scripts run `TRUNCATE` or fixed IDs. Never run a global `DELETE FROM demo_orders` on a shared parallel DB.

### 11.5. `TransactionMode.DEFAULT` vs `ISOLATED`

`@SqlConfig(transactionMode=DEFAULT)` lets Spring infer transaction semantics from the DataSource, transaction manager, and current test TX:
- The script may run **inside** the test-managed transaction.
- If a delete script runs inside the test TX and the test rolls back, the delete can roll back too.
- `ISOLATED` requests running the script in an independent transaction that commits on success per Spring's SQL test infrastructure.
- `AFTER_TEST_METHOD` defines **timing relative to the test method**, not guaranteed isolation or commit in every scenario.

Therefore specify **both `executionPhase` and `transactionMode`** when aiming for committed cleanup of HTTP writes. Even with `ISOLATED`, still manage data ownership and lock contention.

### 11.6. `@Sql BEFORE_TEST_METHOD` and committed fixtures

The HTTP server thread needs to see fixtures (customer, account, parent order) before the request arrives. If you seed via:
- `@BeforeEach` in a `@Transactional` test: fixtures are usually **uncommitted**, invisible to the server.
- `@Sql(..., transactionMode=DEFAULT)` in a transactional test: the script may run in the test TX, uncommitted.
- `@Sql(..., transactionMode=ISOLATED)`: commits the fixture independently before the request, fitting test needs.

Instead of global SQL scripts, you can use `@BeforeTransaction` or a committed `TransactionTemplate` seed with unique IDs. Afterward, clean up those exact IDs and dependent rows.

### 11.7. `@Sql AFTER_TEST_CLASS`

Spring Framework 6.1+ supports class-level SQL scripts before/after a test class. Useful for class-owned schemas/fixtures, yet **does not** prevent row leaks if multiple classes share a DB and end-of-class cleanup wipes another class's records. In parallel suites, class-level cleanup must scope namespaces/owners strictly. Never rely on “end of class” to guarantee all asynchronous requests have finished.

### 11.8. `@TestInstance(PER_CLASS)` and data state

If a test class uses `@TestInstance(PER_CLASS)`, fields persist across test methods. Never share a mutable `id` field across parallel methods without isolation. Generate per-method UUIDs/namespaces; for class-scoped resources, keep clear ownership and avoid overwriting other rows at teardown.

## 12. Why can DELETE execute while data still remains?

### 12.1. DELETE inside a transaction gets rolled back

~~~text
Client TX-T starts
HTTP server TX-S inserts id=server-1
HTTP server TX-S COMMIT
Client @AfterEach executes DELETE id=server-1 in TX-T
Client TX-T ROLLBACK

Final DB: server-1 STILL EXISTS
~~~

This is a classic trap when JDBC logs show a `DELETE` yet cleanup is not durable. Adding transaction logging or an `@AfterTransaction` query exposes it.

### 12.2. DELETE filters by the wrong tenant or ID

SQL:

~~~sql
DELETE FROM demo_orders WHERE order_id = ?;
~~~

only deletes a record when the ID matches. Assert affected row counts when contractually appropriate:
- 1 row if creation succeeded.
- 0 rows if validation/rollback prevented creation.
- For best-effort cleanup after failures, 0 rows can be valid.
- Do not assert every cleanup affects 1 row if tests include negative cases.

Replacing whole-table wipes with targeted deletes is safer, provided you pass **the ID sent over HTTP**, not a newly generated ID during teardown.

### 12.3. An async worker writes the row after delete

If an endpoint returns `202 Accepted` and processes later:
- The test runs DELETE before the worker commits.
- The worker INSERTs afterward.
- After the suite finishes, the row reappears.

Use an operation ID, a completion signal/event status, a bounded await, and cleanup after reaching a terminal state. Never use `Thread.sleep(5000)` as proof a worker completed.

### 12.4. Cascades, foreign keys, and outboxes

Deleting the parent order may hit FK constraints from line items, outbox rows, or payment receipts. Options:
- `ON DELETE CASCADE` in the schema when business semantics match.
- Delete child rows before parent rows.
- Isolate per test via tenant/schema/container.
- Clean up via `TransactionTemplate` in one atomic transaction.
- Clean up off-DB artifacts by owner, not only the core row.

Never disable FK constraints in tests just to “skip cleanup” if production relies on them.

### 12.5. Soft delete

In apps using `deleted_at` or a flag, `DELETE` at the repository/service layer may be a soft delete (unlike SQL DELETE in this lab). When tests need a clean DB, use an appropriate admin/persistence cleanup path without bypassing security/tenant scopes into other tests' data.

### 12.6. `@AfterEach` does not run on every crash

JUnit callbacks run in normal lifecycles, including assertion failures. However:
- The JVM is killed.
- A test hits a hard timeout hang.
- A CI job is canceled.
- The Docker host crashes.
- The test process terminates forcibly.

In those cases cleanup may not execute. Per-run isolated schemas/containers and TTL/CI teardown serve as a second line of defense.

## 13. Clean-data checks must assert specific invariants

### 13.1. Never run a whole-table `COUNT(*)` in a shared suite

~~~sql
SELECT COUNT(*) FROM demo_orders;
~~~

Results can include rows from concurrently running tests. “Table must be empty” is a valid invariant only when **the test owns the entire database/schema exclusively**. In shared DBs:
- `WHERE order_id = ?`.
- Or `WHERE owner_tag = ?` if the owner tag is unique per test.
- Or schema-per-test / tenant-per-test.
- Or a dedicated DB/container for global assertions.

### 13.2. A single UUID does not guarantee full cleanup if retries spawn multiple rows

One operation may create:
- An order row.
- Payment attempt rows.
- Outbox events.
- Audit records.
- Cache entries.

Identify the **full set of resources created by the test** and clean up by operation ID. Deleting only the order ID is insufficient if events keep firing or outbox rows stay pending.

### 13.3. Synthetic data

Use synthetic IDs and owner tags such as `http_<uuid>`, `server_<uuid>`, `test-run-...`; never real customer accounts or emails. Keep tokens, JDBC passwords, and sensitive data out of logs and CI artifacts. If test requests authenticate, manage secrets within the test environment.

### 13.4. Retries and idempotency

A `POST` may be retried by a client after a timeout even though the server already committed. Never treat “did not receive 201” as proof the DB lacks an order. Use stable operation idempotency keys; querying by key or checking the record reveals the final state. Cleanup should delete records matching the **sent** key, not only when a 201 status was observed.

### 13.5. Parallel tests and transaction isolation

Two distinct tests:
- Each test has UUID IDs → minimizes key collisions.
- Each transaction has its own connection → the DB handles concurrent work.
- `DELETE ALL`/`TRUNCATE` → unsafe in shared environments.
- Unique owner tags for cleaning up compound resources.
- For global fixtures, use per-schema/per-container isolation, or JUnit `@ResourceLock` only to coordinate tests inside **the same engine**, not as a distributed DB lock.

Rolling back test A's transaction does not undo test B's commit, nor does it undo A's own server request.

## 14. Practical differences between testing MockMvc and real HTTP

### 14.1. Where is MockMvc useful?

- Controller mappings, statuses, and headers.
- JSON serialization/deserialization.
- Validation errors.
- Filter/security behavior when properly configured.
- Handler method exceptions.
- MVC advice.
- Fast integration for synchronous Spring MVC dispatch.

MockMvc **opens no TCP port**, does not measure handshakes, network behavior, or real server concurrency, and sometimes shares the test transaction. Therefore a cleanly rolling-back MockMvc test is never enough to conclude that real HTTP endpoints clean up automatically.

### 14.2. Where is real HTTP useful?

- Embedded server startup and port configuration.
- Serialization across a real socket.
- Request/response boundaries.
- Transaction separation between client and server.
- Realistic security headers, cookies, and auth flows.
- Server-side commit/rollback outcomes.
- Compression, streaming, and redirect behavior.
- Server thread pools, concurrency, and timeouts.
- Integration with external services when present.

In exchange, real HTTP requires explicit data cleanup, database readiness, port ownership, and careful thread/lifecycle management.

### 14.3. `@WebMvcTest` vs `@SpringBootTest(MOCK)`

`@WebMvcTest` is a web slice; it normally injects `@MockitoBean` for service collaborators because the full DB/service stack is absent. It does not test real service transaction commits. `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` loads the full application context (unless customized) and exercises real service/database logic **in-process**.

Neither is real `RANDOM_PORT` HTTP. Pick test scope based on the invariant you need to prove.

### 14.4. `@WebFluxTest` and reactive transactions

Spring WebFlux reactive pipelines do not rely purely on imperative `ThreadLocal` like MVC/JDBC; reactive transaction contexts propagate through Reactor `Context` along the reactive chain. When testing with `WebTestClient`/WebFlux/R2DBC, analyze subscriptions, schedulers, and reactive transaction operators. Never copy “MockMvc runs on the same thread” directly to WebFlux and assume reactive transactions join automatically.

### 14.5. Thread boundaries in async MockMvc

With `Callable`, `DeferredResult`, or `@Async` services:
- The request may start on the test thread.
- Business work runs on a worker thread.
- Worker JDBC operations do not automatically join the test-managed TX.
- `MockMvc.perform` with async starts must follow proper `asyncDispatch`/completion testing.
- Tests can leave committed rows behind even without opening a TCP server.

What matters is the **transaction owner and active context of the actual write**, not just the name of the test client library.

## 15. Server rollback: testing the failure path properly

### 15.1. Throwing before transaction commit

The lab uses:

~~~java
@Transactional
public void createThenFail(CreateOrderRequest request) {
    repository.insert(new OrderRecord(
            request.id(),
            request.owner(),
            request.quantity()));

    throw new IllegalStateException(
            "forced rollback before commit");
}
~~~

`IllegalStateException` is an unchecked exception. Under Spring's default rollback rules, the transaction interceptor rolls back. Tests do not stop at checking 500; they query the database and verify GET returns 404.

### 15.2. Catching exceptions inside `@Transactional`

Watch out for:

~~~java
@Transactional
public void suspicious(CreateOrderRequest request) {
    try {
        repository.insert(new OrderRecord(
                request.id(), request.owner(), request.quantity()));
        riskyOperation();
    }
    catch (RuntimeException error) {
        log.warn("operation failed", error);
    }
}
~~~

**Counter-example snippet**, not part of the runnable project. If the method returns normally without marking the transaction rollback-only, Spring can commit the insert despite the `"operation failed"` log. To roll back on business errors, propagate the exception or mark rollback-only per contract, and assert final DB state.

### 15.3. Checked exceptions

By default, Spring declarative transactions roll back on `RuntimeException` and `Error`; checked exceptions usually do not trigger rollback unless `rollbackFor`/rollback rules are configured. An HTTP path returning 500 because of a checked exception **does not prove** data rolled back. Verify specific transaction attributes.

### 15.4. `@Transactional` self-invocation

A method inside the same bean calling `this.createThenFail(...)` can bypass default proxy advice. Code may then run non-transactionally or join a different transaction. Split transactional boundaries across Spring beans called via proxies, or use suitable AOP wiring. Tests should traverse real controller/service wiring just like the lab.

### 15.5. Transaction commit can fail after the service body

With JPA/Hibernate, SQL may only flush at commit. A method body returning normally does not prove the commit passed if the commit interceptor throws afterward. HTTP 201 must only be returned after the service proxy returns with a successful commit; if commit throws, controller exception handling must handle it appropriately. Tests must assert actual DB state, not just a `"save called"` log.

### 15.6. Which negative outcomes must be asserted?

A robust transaction test verifies:
- Contractual HTTP status.
- Stable response body/error code.
- DB row count / lookup by ID.
- No partial outbox or inconsistent child line items.
- Retry behavior if supported by the API.
- Idempotency key behavior for payment-like operations.
- Post-test data cleanup.

Never assert exact stack traces or JDBC exception text as a public API contract.

## 16. JPA/Hibernate: add `flush` and `clear` when needed

The lab uses `JdbcTemplate`, so every query reads the DB directly without a JPA first-level persistence context cache. If you use Spring Data JPA:
- `repository.save(entity)` can defer SQL until flush/commit.
- `EntityManager` maintains a first-level cache and dirty checking.
- Queries in the same persistence context can return a managed entity rather than reflecting another thread's transaction as you expected.
- `entityManager.flush()` sends pending SQL inside the transaction.
- `entityManager.clear()` detaches managed entities before re-reading; use when appropriate for transaction/visibility checks.
- For post-commit verification, read from a fresh transaction/`EntityManager` or `@AfterTransaction`.
- `TestEntityManager.flush()` exposes deferred constraint violations in JPA slice tests.

**Yet flush ≠ commit.** A row flushed in TX-T may still be invisible to the HTTP server thread and roll back after the test. Never treat “flushed” as “visible to the server”.

### 16.1. Example JPA probe (snippet)

~~~java
@PersistenceContext EntityManager em;

@Test
@Transactional
void flushIsNotCommit() {
    repository.save(new CustomerEntity(...));
    em.flush();

    // SQL has been sent to the DB inside the test TX, but not COMMITTED.
    // The HTTP server on another connection usually cannot see the row
    // until the test transaction commits.
}
~~~

This is an illustrative snippet, **not** part of the Maven JDBC project, and does not compile standalone without `CustomerEntity`/repository imports. It simply highlights the flush/commit boundary.

### 16.2. OSIV does not merge two requests into one transaction

Spring Boot may enable Open Session in View in Servlet/JPA apps depending on configuration. OSIV keeps an `EntityManager` open across a request for lazy loading, yet never merges the JUnit test transaction and HTTP server transaction into one. Distinguish `EntityManager` lifetime, transaction lifetime, and HTTP request lifecycle.

### 16.3. Database isolation levels

Under `READ_COMMITTED`, another transaction can see a committed row after commit; under `REPEATABLE_READ`, snapshot semantics differ. If the client test TX-T starts before the server commits, a query **inside** TX-T might not reflect server state depending on DB/isolation. `@AfterTransaction` is a far more reliable place to assert final committed state outside TX-T. PostgreSQL and H2 differ in implementation; never infer production isolation rules from H2 alone.

## 17. Testcontainers when a real database is needed

### 17.1. Why isn't H2 enough for every case?

H2 is useful for:
- Demonstrating thread/transaction boundaries.
- Fast JDBC CRUD.
- Checking validation and basic constraints.
- Local repeatable training.

It does not replace PostgreSQL/MySQL for:
- Locking and MVCC isolation anomalies.
- Sequence behavior.
- JSONB/array/vendor-specific types.
- SQL syntax and collations.
- Native upserts and CTEs.
- Transaction deadlocks and serialization retries.
- Flyway migrations using real database dialects.

When API contracts depend on those behaviors, run integration tests with **Testcontainers PostgreSQL**.

### 17.2. Test-only bean + `@ServiceConnection`

With Spring Boot 3.5:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresIntegrationConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("http_rollback_it");
    }
}
~~~

**Optional snippet** requiring `spring-boot-testcontainers`, `org.testcontainers:postgresql` test dependencies, and imports; it is not in the Maven H2 lab. Import the config into `@SpringBootTest` via `@Import`. A Spring-managed bean aligns PostgreSQL's lifetime with the cached `ApplicationContext`, preventing JUnit extensions from stopping it while client contexts still need it.

### 17.3. Container reuse does not clean up data

Even with a Spring bean container, JVM singleton, or opt-in reuse:
- Rows committed over HTTP remain.
- `@DirtiesContext` may close one context, yet an external shared DB is not automatically reset.
- Tests still need unique IDs/schemas and explicit cleanup.
- Stopping a container is infrastructure teardown, not proof each test isolated business state.

### 17.4. Dynamic JDBC URLs

Testcontainers maps hosts/ports dynamically. Never hardcode `jdbc:postgresql://localhost:5432` when a container binds a random port. `@ServiceConnection` supplies connection details; or use `@DynamicPropertySource` with matching lifecycle. A cached `DataSource` pointing at an old port after an improperly owned container restart causes connection refused — not a rollback bug.

### 17.5. Cleaning PostgreSQL safely in parallel

Strategies:
- Per-test UUID order IDs.
- Per-test unique owner tags.
- Targeted child-before-parent deletion.
- Dedicated schemas when tests need `TRUNCATE` or global counts.
- Dedicated containers/contexts when tests need database-wide migrations/resets.
- If teardown fails, CI post-job cleanup scoped to resources owned by the job.
- Never `DROP SCHEMA public CASCADE` on a DB shared with other tests.
- For high confidence: query committed state from a fresh connection after cleanup.

## 18. Async work, messaging, and after-commit side effects

### 18.1. HTTP response before async completion

An endpoint might:
1. Receive POST.
2. Persist request status `PENDING`.
3. Enqueue a job.
4. Return HTTP 202.
5. Have a worker update DB/Redis/Kafka later.

Test client rollback does not touch the worker's transaction. `@AfterEach` cleanup right after 202 can run **before** the worker, which then writes the row afterward. Approach:
- Track an operation ID.
- Await a terminal job state with a bounded condition-based wait.
- Query durable DB state after completion.
- Clean up by operation ID once no workers remain pending.
- Never replace job completion with a fixed sleep.

### 18.2. `@TransactionalEventListener(AFTER_COMMIT)`

If a service publishes an application event handled by `@TransactionalEventListener(phase=AFTER_COMMIT)`:
- The listener runs for that phase only when the publishing transaction commits (subject to listener/fallback settings).
- Under real HTTP, server transaction commit triggers the handler.
- Under synchronous MockMvc using a rolling-back test transaction, the `AFTER_COMMIT` listener never runs because TX-T rolls back.
- Thus MockMvc vs real HTTP can differ in **side effects too**, not just DB rows.
- If the listener writes to the DB after commit, clarify transaction semantics (often `REQUIRES_NEW`) and test outbox/durable behavior.

### 18.3. `AFTER_COMMIT` does not make side effects atomic with the DB

An after-commit handler can fail while the DB order is already committed. When delivery guarantees matter, use a transactional outbox, idempotent consumers, and retries. Rollback-boundary tests should verify:
- Main row committed?
- Outbox event committed?
- Handler delivered/acknowledged?
- Duplicate operations prevented?
- Cleanup removes both outbox and test-owned data?

An HTTP 201 does not prove an external broker publish succeeded unless the architecture binds them together.

### 18.4. `@Async` transaction boundaries

`@Async` or `CompletableFuture` runs on a different thread and does not inherit the JUnit test's `ThreadLocal` TX. When testing:
- Inject a controlled executor.
- Wait for completion with `Future.get(timeout)` or Awaitility.
- Inspect committed/rolled-back rows from an independent transaction.
- Shut down test-created executors per context lifecycle.
- Clean up after completion.
- Never stop a shared executor in `@AfterEach` if the context serves other classes.

### 18.5. Kafka/RabbitMQ consumers

An HTTP endpoint may publish a Kafka/Rabbit message while a consumer processes it in its own DB transaction:
- Test client rollback does not roll back broker offsets/acks.
- Unique topics/groups/queues and eventIds provide isolation.
- If a consumer remains active after the test, teardown may delete fixtures before processing finishes.
- Use durable completion signals and bounded awaits.
- Clean up only your topic/event/cache namespace instead of resetting a shared broker.

### 18.6. Other external systems

- Redis: key writes do not roll back with JDBC transactions.
- Email/SMS: real sends cannot be rolled back by a DB; use fake gateways/test inboxes.
- S3/blob storage: object writes need test-owned prefixes and cleanup.
- Payment gateways: use idempotency keys and sandboxes, never real money.
- Search indexes: eventual indexing requires bounded awaits and cleanup.
- Audit logs: determine whether they are part of the contract and when they are written.
- Filesystem: `Files.writeString` does not participate in JDBC rollback.

Rollback belongs to a **specific transaction manager and resource set**, not “undo every side effect in the program”.

## 19. Pitfalls with `@Sql` and test fixtures

### 19.1. Seeding inside the test TX while sending real HTTP

~~~java
@BeforeEach
void seedCustomer() {
    customerRepository.save(new Customer("c1"));
}
~~~

In a `@Transactional` HTTP test, the saved row may still be uncommitted. The HTTP server handling a POST referencing customer `c1` queries on **another connection**, potentially failing to see `c1` → 404/FK error. Some “fix” this with `Thread.sleep` or disabling FKs; both are wrong. Seed committed fixtures before the real HTTP request via `@BeforeTransaction`, `@Sql(ISOLATED)`, or `TransactionTemplate`.

### 19.2. `@Sql(... AFTER_TEST_METHOD)` alone is not enough

~~~java
@Sql(
    statements = "DELETE FROM demo_orders",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
~~~

This snippet **must not be copied into a shared suite**: it lacks namespacing, risks deleting other tests' rows, and its transaction semantics may surprise you. Always determine:
- **When** does the script execute?
- Inside **which transaction** does it run?
- Does the cleanup statement commit?
- Could it delete another test's data?

### 19.3. Class-level SQL scripts before/after classes

`@Sql` at class phase can set up shared test fixtures, yet:
- Class-level fixtures do not automatically isolate parallel methods.
- If multiple contexts share a DB, schema init/migrations can race.
- `@SqlMergeMode` affects merging/overriding class vs method scripts.
- Class-level cleanup might run after another background consumer has already read the fixture.
- Static scripts struggle with dynamic per-method UUIDs; when per-test IDs are needed, use code + repositories.

### 19.4. `TransactionalTestExecutionListener` and `@AfterTransaction`

Spring Framework's transaction test listener already provides proper hooks; never call `TransactionAspectSupport.currentTransactionStatus()` from a test trying to force rollback of a server TX — the test thread does not own the server's status. Use `@AfterTransaction` to inspect post-test-TX state and perform explicit cleanup.

### 19.5. `@Commit`/`@Rollback(false)` for fixture setup

When you need committed fixtures before HTTP:
- Do not mark the entire test `@Commit` just so the server sees data.
- Create fixtures in an **independent committed transaction step**, run HTTP, and clean up afterward.
- Committing the entire test persists incidental test writes and dirties the suite.

### 19.6. Swallowed SQL cleanup script errors

If `DELETE` fails due to an FK constraint or wrong schema, tests should surface that cleanup error explicitly. Never swallow exceptions to keep a build green. When cleanup fails, run a post-test row count and fail with a clear diagnostic message. Under production-like schemas, test cleanup code deserves the same review rigor as app code.

## 20. Analyzing by data instead of guessing from logs

### 20.1. Standard diagnostic timeline

~~~text
[JUnit main] BEFORE_TRANSACTION
  prepare client_marker_id and http_order_id

[JUnit main] TX-T BEGIN
  JDBC INSERT client marker

[JUnit main] HTTP POST httpOrderId
  [Tomcat worker] TX-S BEGIN
  [Tomcat worker] INSERT httpOrderId
  [Tomcat worker] TX-S COMMIT
[JUnit main] HTTP 201

[JUnit main] test ends
[Spring TestContext] TX-T ROLLBACK

[JUnit main] AFTER_TRANSACTION
  COUNT(client_marker_id) = 0
  COUNT(http_order_id)    = 1
  DELETE http_order_id (committed)
  COUNT(http_order_id)    = 0
~~~

This represents the **expected sequence of events**, not measured logs with real timestamps. Thread, manager, and callback names may vary by version. Correlate logs using test IDs and operation IDs while keeping secrets out of logs.

### 20.2. Seeing SQL INSERT does not mean commit

SQL loggers may print INSERT before the transaction commits. If an exception follows, the DB rolls back. Only after the transaction manager commits and a fresh connection queries the state do you have proof of a durable row.

### 20.3. Seeing DELETE does not mean cleanup finished

A DELETE inside the test TX can roll back. A DELETE in a new transaction can fail at commit. Re-query after cleanup using an appropriate transaction/connection instead of just counting SQL statements.

### 20.4. False results from DB connection/session caching

When a JPA `EntityManager` caches managed entities, `findById` may serve from the first-level cache. Querying after `em.clear()` or via a separate `JdbcTemplate`/connection shows committed DB state more faithfully. Still, even a fresh query inside a `REPEATABLE_READ` snapshot TX is not guaranteed to see a concurrent server commit; verify after the test TX ends.

### 20.5. Auditing server-side transaction events

When distinguishing threads and transactions:
- Log the operation ID.
- Log the thread name.
- Log `TransactionSynchronizationManager.isActualTransactionActive()` in the service (diagnostics only).
- Log transaction begin/commit/rollback categories.
- Log affected SQL row counts.
- Never expose SQL credentials or PII.
- Do not rely on thread names as the sole oracle, as schedulers/pool names vary.

The final business assertion remains the row count and invariant.

## 21. Troubleshooting table for common symptoms

| Symptom | Likely cause | Evidence | Fix |
| --- | --- | --- | --- |
| HTTP 201 yet row remains after `@Transactional` test | Server committed on another thread | `@AfterTransaction` count=1 | Targeted committed cleanup |
| JUnit marker disappears, HTTP order remains | TX-T rolled back, TX-S committed | Two IDs checked post-TX | Expected boundary behavior |
| `@AfterEach` DELETE runs yet row stays | DELETE ran inside TX-T and rolled back | Transaction logs + post-TX count | `@AfterTransaction`/independent TX |
| MockMvc test rolls back cleanly, real HTTP doesn't | Same-thread vs cross-thread | Contrast the two test types | Explicit real-HTTP cleanup |
| HTTP server cannot see fixture | Fixture uncommitted in JUnit TX | Fresh connection query | Committed setup before POST |
| HTTP 500 yet row remains | Exception caught/swallowed or commit preceded error | Post-error DB count | Fix server transaction boundary |
| HTTP 500 and row=0 | Proper server-side rollback | Fresh DB query | Keep regression test |
| Invalid POST 400 yet row exists | Wrong validation/side-effect ordering | DB count | Validate before writing, tx rollback |
| Duplicate 409 yet original row changed | Bad update/upsert logic | Compare persisted row | Constraint + conflict handling |
| `@DirtiesContext` still leaves DB rows | External state not reset | Query DB after context close | Targeted cleanup/schema isolation |
| `@Sql` cleanup fails to commit | `TransactionMode.DEFAULT` inside test TX | `@Sql` config + post-TX query | `ISOLATED` / post-TX cleanup |
| `@Sql` deletes another test's data | Global DELETE on shared DB | Owner tags/parallel timeline | Unique namespace/targeted delete |
| `@TransactionalEventListener` skipped in MockMvc | Test TX rolled back, no `AFTER_COMMIT` | Event logs/post-TX | Test real commit path |
| Async worker writes row after `@AfterEach` | Cleanup ran before completion | Future/event status timeline | Await terminal state then clean up |
| H2 test green, PostgreSQL fails | Different SQL/locking/isolation | Testcontainers PG | Production-like DB test |
| Tests hit intermittent duplicate IDs | Fixed test fixture ID | Row ID collision | UUID per method/operation |
| Rerun after CI failure yields 409 | Prior committed data left behind | Owner ID from prior run | Dedicated DB/schema/cleanup |
| Parallel test methods delete each other | Shared cleanup SQL | IDs/owner tags | Per-test IDs or isolation |
| Query inside TX-T misses HTTP commit | Snapshot isolation/visibility | Post-TX fresh query | Check outside TX |
| Connection refused between test classes | Container stopped vs cached context | Testcontainers lifecycle | Managed container bean |
| DataSource pool exhausted | Unclosed connections/too few connections | Hikari metrics | Close leaks/budget concurrency |
| Test transaction misses `@Async` rollback | Thread-bound context not propagated | Worker DB query | Worker cleanup/tx handling |
| `@Commit` leaves fixtures behind | Explicit test TX commit | Post-test count | Cleanup matching owner |
| `@AfterTransaction` never runs | Test method not transactional | Annotations/lifecycle | Use `@AfterEach` if no test TX |
| HTTP GET 404 right after POST 201 | Wrong ID, replica lag, rollback, async | Correlation ID/DB query | Fix consistency path |
| CI green yet tests skipped | Discovery/config issue | Surefire XML executed count | Enforce test execution |
| All tests pass yet residual rows remain | Missing post-cleanup invariant check | Per-test owner count | Add post-cleanup assertion |

## 22. Designing the right test suite for a real project

### 22.1. Sound test layering

An application can combine:
- Unit tests for business calculations, without Spring/DB.
- `@WebMvcTest` controller slices for mapping/validation/JSON with mocked services.
- `@JdbcTest`/`@DataJpaTest` repository tests for SQL/mapping with default rollback.
- Full `@SpringBootTest(MOCK) + MockMvc` for synchronous filter/controller/service composition.
- Full `@SpringBootTest(RANDOM_PORT)` for real HTTP serialization/commit/network boundaries.
- Testcontainers integration for production DB/broker dialects.
- E2E tests against external service sandboxes.

Avoid forcing one annotation to do everything. Clearly specify which tests rely on clean rollback and which verify committed state and clean up afterward.

### 22.2. Contract of an HTTP test

Every test should state:
- Given: committed persisted fixtures or an independent request needing none.
- When: HTTP operation using a unique ID.
- Then: status/body and **durable state**.
- Cleanup: scoped by ID/owner namespace inside a committed transaction.
- Isolation: never touches other tests' rows.
- Completion: zero pending background work prior to teardown.
- Failure: cleanup inside `finally`/callbacks even when assertions fail.

This structure is easy to review and low-flake.

### 22.3. Data ownership rule

Tests only delete artifacts they own. With parent/child tables:
- Generate `runId`/`testId`.
- Store an owner tag on all rows needing cleanup or link via FK.
- Delete child rows before parents or cascade per contract.
- Verify post-cleanup counts using the owner tag.
- Off-DB resources (Redis/Kafka/S3) use matching namespaces.

Never delete shared global seed/reference data; provision dedicated test containers/schemas instead.

### 22.4. Speeding up without cutting corners

- Reuse Spring contexts when configurations match.
- Reuse containers with aligned lifetimes if CI budgets require it.
- Use unique IDs instead of rebuilding contexts per test.
- Use targeted cleanup rather than `TRUNCATE` across the DB.
- Avoid blanket `@DirtiesContext`.
- Use slices/MockMvc for non-network contracts and real HTTP tests for the socket boundary.
- Enable context cache `DEBUG` logs when profiling performance.
- Never use long timeouts or sleeps to mask startup readiness or async races.

### 22.5. CI and parallel execution

When running multiple workers/forks:
- Each JVM maintains its own Spring TestContext cache.
- In-memory `H2 mem:...` is per-JVM; each process gets a separate in-memory DB unless configured as an external H2 server.
- PostgreSQL Testcontainers can create one or multiple containers depending on ownership.
- Unique IDs prevent key collisions across tests yet do not make global cleanup SQL safe.
- If a test needs a database/schema-wide `COUNT(*)`, give it an **exclusive schema/DB**.
- JUnit `@ResourceLock` coordinates resource keys only inside the same test engine, not as a distributed lock.
- Test classes must remain order-independent.
- Verify executed counts and cleanup inside every worker.

## 23. Extension exercises

1. Run all three lab classes and record the six executed test methods (if your environment permits).
2. Add `@Transactional` to `RealHttpCleanupIntegrationTest` while keeping `@AfterEach`; predict why the DELETE can roll back, then **restore the correct code right after the experiment**.
3. In `RealHttpRollbackBoundaryTest`, log `TransactionSynchronizationManager.isActualTransactionActive()` on both the test thread and server service.
4. Assert `clientMarkerId=0` and `httpOrderId=1` inside `@AfterTransaction`; explain why you cannot rely solely on assertions in the test body.
5. Remove `@BeforeTransaction` and seed the DB inside `@BeforeEach`; let the HTTP server query the uncommitted fixture and explain why it is invisible.
6. Use `@SqlConfig(transactionMode=ISOLATED)` to commit a fixture before HTTP, ensuring the SQL script touches only owned data.
7. Use `@Sql(... AFTER_TEST_METHOD)` with a script scoped to a dedicated test schema; verify cleanup commits.
8. Add `@Rollback(false)` to a test, inspect post-test state, then clean up; explain why it should not be the default.
9. Call `TestTransaction.flagForRollback(); TestTransaction.end()` to query the DB outside the TX; avoid calling it after the TX has already ended.
10. Add a `@Transactional(propagation=REQUIRES_NEW)` service method and call it via synchronous MockMvc; verify the row can persist past test rollback.
11. Add an `@Async` controller or async servlet handler; contrast its thread/transaction boundary with synchronous MockMvc.
12. Add an endpoint returning 202 and use a bounded completion signal before cleanup.
13. Write a `@TransactionalEventListener(AFTER_COMMIT)` test and compare event side effects between real HTTP and MockMvc rollback.
14. Throw a checked exception inside a transactional service, check default rollback rules and `rollbackFor`.
15. Add a Hibernate/JPA repository, use flush/clear and a fresh transaction to avoid first-level cache false positives.
16. Create an H2 row with a foreign-key child; write child-first targeted cleanup.
17. Use a unique `ownerTag` per test and query `countByOwner` after cleanup.
18. Run class A then B in randomized order, confirming zero data leaks or duplicates.
19. Enable JUnit parallel classes and verify why global SQL DELETE is dangerous unless scoped to an isolated schema.
20. Swap H2 for PostgreSQL Testcontainers using a typed `@ServiceConnection` container.
21. Inspect `JdbcTemplate` transaction boundaries when POST and test use two Hikari connections.
22. Trigger a duplicate key in POST, verifying 409 and that the original row is unchanged.
23. Trigger a validation 400, verifying zero side effects in DB and a simulated outbox.
24. Make a fake gateway throw 500 **after** a DB commit in a non-transactional service; prove HTTP status does not determine rollback.
25. Intentionally catch `RuntimeException` inside a transactional service, verify why SQL still commits, and fix it.
26. Add `@DirtiesContext` to an HTTP test and prove external persisted rows are not deleted automatically.
27. Test data cleanup when a test assertion throws; ensure `finally`/callbacks still run in normal lifecycles.
28. Simulate a client timeout after server commit, look up by operation ID, and run best-effort cleanup.
29. Write a Redis key with a unique test prefix; prove JDBC rollback does not undo Redis writes.
30. Add an outbox message consumer and await after-commit processing before cleanup.
31. Use Maven Surefire XML to check executed/skipped/error counts instead of only `BUILD SUCCESS`.
32. Write a checklist for your own module covering transactions, owners, cleanup, timeouts, parallelism, and external state.
33. Read Spring Boot 3.5 docs on separate HTTP client/server threads and trace the timeline against real code.
34. Read Spring Framework tx docs to distinguish in-TX `@BeforeEach` from out-of-TX `@BeforeTransaction`.
35. Design a CI schema-per-run setup with post-job cleanup for when a test process is killed.

## 24. Testing and review checklist

- [ ] Identified whether the test uses synchronous MockMvc or real HTTP?
- [ ] For real HTTP, understood client and server use different threads/transactions?
- [ ] Not assuming `@Transactional` on the test rolls back server writes?
- [ ] Verifying database state after the response, not just HTTP status?
- [ ] Distinguishing `REQUIRED` from `REQUIRES_NEW`?
- [ ] Aware that `@AfterEach` in a transactional test belongs to the test TX?
- [ ] Real HTTP cleanup does not run inside a transaction that will roll back?
- [ ] For transactional tests, using `@AfterTransaction` or independent committed cleanup?
- [ ] Server-side `@Transactional` boundaries clearly defined?
- [ ] Failure path throwing before commit is tested?
- [ ] Not relying on HTTP 500 alone to claim rollback?
- [ ] 400/409 success/negative cases leave no dirty DB state?
- [ ] Every method/HTTP operation generates a unique ID?
- [ ] Cleanup deletes only rows/artifacts owned by the test?
- [ ] No whole-table DELETE/TRUNCATE on shared parallel DBs?
- [ ] `@Sql AFTER_TEST_METHOD` reviewed together with `transactionMode`?
- [ ] `@Sql ISOLATED` used when scripts must commit?
- [ ] Fixtures needed by the server are committed before HTTP calls?
- [ ] Not confusing `flush` with `commit` in JPA?
- [ ] Not relying on a cached `EntityManager` to prove durable DB state?
- [ ] Querying final state after test-managed rollback?
- [ ] Cleanup placed in `finally`/callbacks when assertions fail?
- [ ] Cleanup statements committed and verified by a fresh query?
- [ ] Async workers/consumers finished before cleanup?
- [ ] Not using `Thread.sleep` as a commit/completion signal?
- [ ] Testcontainers backends properly own context lifetimes?
- [ ] Important production DB dialects tested against a real DB?
- [ ] `@DirtiesContext` not mistaken for database cleanup?
- [ ] Tests pass standalone, repeatedly, and in randomized order?
- [ ] JUnit forks/parallel workers never share fixed IDs or cleanup?
- [ ] Zero secrets or customer data in test fixtures/logs?
- [ ] Maven runs verified against Surefire executed counts and actual failures?
- [ ] Results labeled “expected” whenever unexecuted?
- [ ] Regression tests guard the HTTP commit/rollback boundary?

## 25. Claims you must NOT overstate

- **“A `@Transactional` test always rolls back everything”: false.** It guarantees rollback only for the test-managed TX and resources bound to it, never across HTTP.
- **“MockMvc is always in the same transaction”: too broad.** Only synchronous/compatible paths normally join the test's `ThreadLocal` transaction.
- **“HTTP 500 means DB rolled back”: false.** The server could have committed before failing or swallowed an exception.
- **“SQL DELETE ran so cleanup committed”: false.** The DELETE may roll back.
- **“`@AfterEach` runs outside the test transaction”: false when the test uses `@Transactional`** (normal Spring TestContext lifecycle).
- **“`@DirtiesContext` resets the database”: false for external/shared DBs.**
- **“`@Sql AFTER_TEST_METHOD` guarantees committed cleanup”: must check `transactionMode` and data ownership.**
- **“`EntityManager.flush()` committed”: false.** Flush sends SQL, yet the transaction can still roll back.
- **“`DB COUNT(*)` must equal 0 after every test”: valid only when the test owns the whole DB/schema.**
- **“H2 PASS proves PostgreSQL production locking”: false.**
- **“POST returning 201 always means all async side effects finished”: false.**
- **“If the API timed out, the server definitely didn't commit”: false.**
- **“Increasing timeouts or adding `@DirtiesContext` fixes data leaks”: unsubstantiated.**
- **“Test/CI exit code 0 means cleanup ran”: requires post-cleanup assertions and test counts.**
- **“`TestTransaction.end()` on client rolls back server TX”: false.**
- **“All DB/Redis/Kafka/S3 state shares one transaction”: false in typical architectures.**

## 26. Conclusion

This practical lesson proves a decisive boundary: **rolling back the JUnit test thread does not roll back a transaction committed by an HTTP server thread**. With `@SpringBootTest(RANDOM_PORT)`, treat post-POST data as a real side effect requiring **explicit, committed, targeted cleanup**; with test-managed transactions, use `@AfterTransaction` to observe post-rollback state and avoid placing DELETE inside `@AfterEach` of that same transaction. Also distinguish this from synchronous MockMvc, where `REQUIRED` services commonly join the test transaction and roll back together with the test.

The value of the experiment lies in direct evidence:
- Marker inserted by the JUnit transaction → **vanishes after rollback**.
- Order inserted by the HTTP server transaction → **remains after test rollback**.
- Cleanup executed outside the test transaction → **deletes that exact order and re-verifies the DB**.
- A server-side exception before commit → **zero partial rows**.

When moving from the H2 lab to a real application, keep the same methodology while adopting production-like databases/Testcontainers for concurrency/isolation, awaiting async completion, cleaning up by operation ID/tenant/schema, and guarding all external side effects against cross-test contamination.

## 27. Official references

- Spring Boot 3.5.16 — Testing Spring Boot Applications, `RANDOM_PORT`, `TestRestTemplate`, client/server separate threads and transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — Test-managed Transaction Management, `@BeforeTransaction`, `@AfterTransaction`, `TestTransaction`, preemptive timeouts: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Executing SQL scripts, `@Sql`/`@SqlConfig` transaction modes, `AFTER_TEST_METHOD`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Framework 6.2 — TestContext caching and context lifecycle: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — `@DirtiesContext` and cache invalidation: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — Declarative Transaction Management and rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2 — Transaction Propagation and `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.5 — JDBC/SQL databases and initialization: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Testcontainers / `ServiceConnection`: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Spring MVC/MockMvc Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.with-mock-environment
- Spring Framework 6.2 — Test-managed Transactions and ORM false positives/flush: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Maven Surefire — Test selection and XML reports: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
