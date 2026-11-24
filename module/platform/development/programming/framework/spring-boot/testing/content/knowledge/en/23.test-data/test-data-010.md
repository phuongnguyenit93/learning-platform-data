# Avoiding Order Dependency and Leftover Data from Previous Tests

In **Spring Boot testing**, a test may pass in a full suite yet fail when run alone, or pass alone yet fail when reordered, parallelized, or rerun in CI. The usual cause is **a test implicitly relying on data created by another test**, an earlier test **committing without cleaning up**, fixtures **seeded only once at startup**, or tests sharing **caches, static fields, Spring singletons, or message queues**. That is a test-data management bug, not something to fix by raising timeouts or forcing `@TestMethodOrder`.

The principle of this lesson is that **each test establishes its own preconditions, executes its action, asserts outcomes, and manages every mutation it owns**. Rollback is an excellent choice for repository tests, yet **it does not automatically roll back transactions committed via HTTP, `REQUIRES_NEW`, `@Commit`, other threads, or external systems**.

This lesson uses Java 17, Spring Boot 3.4.5, JUnit Jupiter, Spring Data JPA, H2, and Spring TestContext. It provides complete runnable examples covering **`@DataJpaTest` rollback**, **per-method `@Sql` fixtures**, **`RANDOM_PORT` HTTP tests with cleanup**, **`REQUIRES_NEW` transactions escaping outer rollback**, and **`@Commit`/`@AfterTransaction`**. Final sections cover parallelism, context caching, Testcontainers, and verifying tests pass in isolation and arbitrary order. Reported outcomes are **expected from source inspection**, not logs from an executed Gradle run.

## 1. Invariants of an Independent Test

A trustworthy test upholds these invariants:

- **Self-sufficient input data:** never wait for Test A to run first and create a user, order, or ticket for Test B.
- **No dependence on leftover data:** if prior-run residue could exist, tests must explicitly isolate namespaces, preclean, or use dedicated databases.
- **No dependence on generated IDs:** sequences and identity columns in many databases do not necessarily reset on rollback.
- **Execution-order independence:** running alone, per class, or in a reordered suite produces the same outcome.
- **Clear cleanup rules:** roll back operations inside the test-managed transaction; explicitly delete operations committed outside that transaction.
- **Never delete data owned elsewhere:** scope cleanups by tenant, `externalKey`, `testRunId`, or a disposable database—never run table-wide `DELETE` on shared tables.
- **Independent off-DB state:** caches, files, queues, static variables, HTTP sessions, and mock behaviors must also be scoped or reset.

~~~text
Arrange: establish baseline and create test's own fixtures
   |
   v
Act:     invoke repository/service/HTTP endpoint
   |
   v
Assert:  verify expected response and state
   |
   v
Cleanup: roll back or delete only test-owned data
   |
   v
Post-test invariant: leave no state affecting other tests
~~~

**An individual test does not need to wipe the entire database blank.** It only needs to restore **the state it owns** while respecting shared baselines. In multi-tenant systems, table-wide cleanup can be worse than no cleanup because it destroys other concurrent tests' fixtures.

## 2. Anti-Example: Second Test Passes Only If First Ran Earlier

**Intentionally broken** pattern:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileTicketTests {
    static Long ticketId;

    @Test
    @Order(1)
    void createTicket() {
        ticketId = service.create("A", "shared", "title");
    }

    @Test
    @Order(2)
    void readTicketCreatedEarlier() {
        assertTrue(repository.existsById(ticketId));
    }
}
~~~

This is an **incomplete snippet** missing service, repository, and imports. It exhibits several design flaws: relying on `@Order`, passing an ID via a static field, assuming data survives across test transactions, and failing whenever the read method runs alone. When `create` runs under `@DataJpaTest` rollback, `read` receives an ID **with no matching row left in the DB**.

**Fix:** each test seeds the `Ticket` it needs via the repository or `@Sql`. The creation test asserts on the `Ticket` it just created. The read test creates a `Ticket` to read. Never use one test's output as another test's fixture.

JUnit Jupiter offers `MethodOrderer.Random` to **uncover** some order dependencies, though one randomized pass does not prove independence. Sustainable safety still comes from lifecycle-proper fixtures and cleanup.

### Four Checks Every Good Test Should Pass

**1.** Run alone via `gradle --tests`.

**2.** Run alongside other tests with no ordering constraints.

**3.** Rerun repeatedly in the same managed test environment.

**4.** Under suite parallelism, never collide on shared keys, broad cleanups, or unsynchronized state.

Passing once in one fixed order proves none of those four properties.

## 3. Classifying Data: How Far Does Rollback Reach?

| Data or Side Effect | Lifetime | `@Transactional` Test Rollback |
| --- | --- | --- |
| JPA/JDBC DML inside test-managed transaction | Single test method | **Usually rolled back** |
| `@Sql` script joining the test transaction | Single method | **Rolled back** |
| `@Commit` or `@Rollback(false)` | Row commits | **Not removed by rollback** |
| Spring service `REQUIRES_NEW` | Independent committed transaction | **Not rolled back with outer transaction** |
| HTTP `POST` through a real server | Separate servlet thread and service transaction | **Not automatically rolled back** |
| `@Async` or new executor thread | Separate transaction/thread | **Not automatically rolled back** |
| `data.sql` at `ApplicationContext` startup | Baseline outside test transaction | **Not automatically deleted** |
| Static `Map`, singleton Spring bean | Lives for JVM/context lifetime | **No** |
| Redis, Kafka, filesystem, external API | Outside RDBMS transaction | **No** |
| Reused Testcontainers container | Container DB persists across tests | **Not automatically reset per method** |

**`@SpringBootTest` does not automatically make tests transactional.** With `@SpringBootTest`, add **`@Transactional`** to the test when you want test-managed rollback. Conversely, **`@DataJpaTest`** is transactional and rolls back by default. Both apply only to transactions executing on the Spring TestContext test thread.

### Flush Is Not Commit

In JPA, `repository.save(...)` may only leave a managed entity in memory; some SQL or constraint errors surface only on flush. **`saveAndFlush`** sends SQL to the database inside the test transaction, yet **still does not commit**. At default rollback, the row vanishes; observing `count=1` inside the same transaction does not prove another client or connection can read committed data.

## 4. Test Data Fixtures Must Be Self-Contained and Discriminating

Good fixtures include both positive and negative cases. For example, testing a repository query finding tickets by tenant + external key needs at least:

| Tenant | External Key | Title | Purpose |
| --- | --- | --- | --- |
| A | `ticket-01` | first | Positive match |
| A | `ticket-02` | second | Ensures key filter works |
| B | `ticket-01` | another tenant | Prevents cross-tenant leaks |
| A | `archived-01` | archived | Verifies status/archived filters if present |

Never assert only “count has rows”: a query forgetting the tenant filter can return the same count by coincidence. **Assert exact keys, tenants, and row states—not just total database counts.**

Three core strategies:

**Per-method fixture:** create entities directly in `@Test` or `@BeforeEach`, rolling back with the test when transactional. Clear to read with minimal global coupling.

**Per-method `@Sql`:** explicitly declared SQL script joining the test transaction under default settings. Suits fixed SQL datasets; avoid accidental duplicate seeds via `ISOLATED` mode.

**Committed setup/cleanup:** when HTTP, `@Commit`, or `REQUIRES_NEW` commits rows, use per-test tenants/keys, preclean residue, and postclean outside the transaction—or use a disposable database.

Never use **`@BeforeAll`** to insert a row once and let multiple tests mutate it; that creates shared mutable state outside individual method transactions.

## 5. Runnable Project: Java 17, Boot 3.4.5, JPA, H2, HTTP

The project contains a **`Ticket`** entity with a unique **`(tenantId, externalKey)`** business key pair. `TicketService` writes rows inside a Spring-managed transaction. An HTTP controller exposes `POST /api/tickets` to demonstrate server-thread commits. `IndependentTicketWriter` uses `REQUIRES_NEW` to demonstrate committed rows surviving outer test rollback.

**Goals:**
1. Repository tests use `@DataJpaTest` for automatic rollback.
2. `@Sql` builds a per-method baseline that also rolls back.
3. HTTP tests use per-method unique keys with preclean and postclean.
4. Transactional tests invoking `REQUIRES_NEW` clean up in `@AfterTransaction`.
5. `@Commit` tests assert the row persists post-commit and then clean it up.
6. Every test can run standalone without reading IDs from another test.

### 5.1. File Structure

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/testdata/TestDataApplication.java
src/main/java/com/example/testdata/Ticket.java
src/main/java/com/example/testdata/TicketRepository.java
src/main/java/com/example/testdata/TicketService.java
src/main/java/com/example/testdata/TicketController.java
src/main/java/com/example/testdata/IndependentTicketWriter.java
src/test/resources/sql/seed-ticket.sql
src/test/java/com/example/testdata/RollbackIsolationTest.java
src/test/java/com/example/testdata/SqlSeedIsolationTest.java
src/test/java/com/example/testdata/HttpCommitIsolationTest.java
src/test/java/com/example/testdata/RequiresNewIsolationTest.java
src/test/java/com/example/testdata/CommitCleanupTest.java
~~~

### 5.2. Gradle and application.yml

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-data-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

**`generate-unique-name=true`** lowers the risk of different `ApplicationContext` instances colliding on the same H2 in-memory database name. However, it does not create a fresh database for **every method** in the same context. Because Spring TestContext caches contexts, committed rows still persist across methods and classes. **`ddl-auto=create-drop`** suits demo/test databases only, never production.

**`spring-boot-starter-web`** provides the live HTTP server; **`spring-boot-starter-data-jpa`** provides Hibernate and repositories; **`spring-boot-starter-test`** provides JUnit and Spring TestContext. H2 runs embedded yet enforces real schemas, transactions, and unique constraints.

### 5.3. Application Class

**src/main/java/com/example/testdata/TestDataApplication.java**

~~~java
package com.example.testdata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestDataApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestDataApplication.class, args);
    }
}
~~~

### 5.4. Entity Ticket

**src/main/java/com/example/testdata/Ticket.java**

~~~java
package com.example.testdata;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "tickets",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_ticket_tenant_key",
        columnNames = {"tenant_id", "external_key"}))
public class Ticket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 40)
    private String tenantId;

    @Column(name = "external_key", nullable = false, length = 100)
    private String externalKey;

    @Column(nullable = false, length = 200)
    private String title;

    protected Ticket() {
        // Required by JPA.
    }

    public Ticket(String tenantId, String externalKey, String title) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.externalKey = Objects.requireNonNull(externalKey);
        this.title = Objects.requireNonNull(title);
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getExternalKey() {
        return externalKey;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = Objects.requireNonNull(newTitle);
    }
}
~~~

The `(tenant_id, external_key)` pair has a unique constraint. A test that skips cleanup and re-inserts the same pair fails immediately, surfacing isolation bugs. **Never remove unique constraints or disable DB checks just to make tests pass.**

**Generated IDs are unreliable fixture keys:** sequences and identity counters keep incrementing across rollbacks. Use a deterministic per-method `externalKey` or log/capture generated keys—never assert that IDs start at 1.

### 5.5. Repository

**src/main/java/com/example/testdata/TicketRepository.java**

~~~java
package com.example.testdata;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TicketRepository extends JpaRepository<Ticket, Long> {
    long countByTenantIdAndExternalKey(
            String tenantId, String externalKey);

    Optional<Ticket> findByTenantIdAndExternalKey(
            String tenantId, String externalKey);
}
~~~

The repository lets tests query rows by **tenant + test key**, independent of generated IDs or leftover data. In multi-tenant apps, every assertion and cleanup must filter by tenant.

### 5.6. Service Creating Tickets

**src/main/java/com/example/testdata/TicketService.java**

~~~java
package com.example.testdata;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TicketService {
    private final TicketRepository repository;

    public TicketService(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long create(String tenant, String key, String title) {
        Ticket saved = repository.saveAndFlush(
                new Ticket(tenant, key, title));
        return saved.getId();
    }
}
~~~

When invoked directly from a `@Transactional` JUnit test, the service's default **`REQUIRED`** propagation joins the test transaction and rolls back with the test. When invoked by an HTTP server thread, the service opens and commits its own transaction; the JUnit client thread does not own that transaction.

### 5.7. HTTP Controller

**src/main/java/com/example/testdata/TicketController.java**

~~~java
package com.example.testdata;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {
    private final TicketService service;

    public TicketController(TicketService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Created> create(@RequestBody Create request) {
        long id = service.create(
                request.tenantId(),
                request.externalKey(),
                request.title());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Created(id));
    }

    public record Create(
            String tenantId, String externalKey, String title) {
    }

    public record Created(long id) {
    }
}
~~~

The HTTP controller demonstrates the **transport and transaction boundary**, omitting production authorization and validation. Over real HTTP `POST`, the service's transaction commits before the `201` response is returned when no async work is involved.

### 5.8. IndependentTicketWriter Using REQUIRES_NEW

**src/main/java/com/example/testdata/IndependentTicketWriter.java**

~~~java
package com.example.testdata;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentTicketWriter {
    private final TicketRepository repository;

    public IndependentTicketWriter(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String tenant, String key) {
        repository.saveAndFlush(
                new Ticket(tenant, key, "independent commit"));
    }
}
~~~

`REQUIRES_NEW` **suspends the outer transaction** and starts a new transaction when called through the Spring AOP proxy. Once the service method completes and commits, rolling back the outer transaction does not undo the row. **Never** call `this.write(...)` inside the same bean expecting propagation behavior, as self-invocation bypasses the proxy.

## 6. Test A — Per-Method Rollback in @DataJpaTest

**src/test/java/com/example/testdata/RollbackIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class RollbackIsolationTest {

    @Autowired
    private TicketRepository repository;

    @Test
    void createsOwnFixtureAndRunsIndependently() {
        String tenant = "ROLLBACK";
        String key = "rollback-first";

        assertEquals(0L,
                repository.countByTenantIdAndExternalKey(tenant, key));

        repository.saveAndFlush(
                new Ticket(tenant, key, "first test"));

        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(tenant, key));
    }

    @Test
    void usesAnotherFixtureWithoutReadingFirstTest() {
        String tenant = "ROLLBACK";
        String key = "rollback-second";

        assertEquals(0L,
                repository.countByTenantIdAndExternalKey(tenant, key));

        Ticket ticket = repository.saveAndFlush(
                new Ticket(tenant, key, "second test"));

        assertTrue(ticket.getId() > 0);
        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(tenant, key));
    }
}
~~~

**Each method creates its own data.** `@DataJpaTest` is transactional by default and rolls back at method end. The two methods use distinct keys, share no static ID fields, and declare no `@TestMethodOrder`. Running the second method alone still creates everything it needs.

**`saveAndFlush`** sends SQL to the database inside the test transaction to catch mapping/constraint errors early. `count = 1` reflects state inside the transaction, not proof of a commit. The identity ID is asserted only to be **greater than 0**, never hardcoded as `1` or `2`.

## 7. Test B — @Sql Seeds a Fresh Baseline Before Each Method

A fixed SQL fixture can be seeded **before each method**, provided the script joins the test-managed transaction and rolls back at method end.

**src/test/resources/sql/seed-ticket.sql**

~~~sql
INSERT INTO tickets (tenant_id, external_key, title)
VALUES ('SEED', 'seed-key', 'Original');
~~~

**src/test/java/com/example/testdata/SqlSeedIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
@Sql(
    scripts = "/sql/seed-ticket.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Execution(ExecutionMode.SAME_THREAD)
class SqlSeedIsolationTest {

    @Autowired
    private TicketRepository repository;

    @Test
    void fixtureHasOriginalValueEveryTime() {
        Ticket ticket = repository
                .findByTenantIdAndExternalKey("SEED", "seed-key")
                .orElseThrow();

        assertEquals("Original", ticket.getTitle());
        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(
                        "SEED", "seed-key"));
    }

    @Test
    void modificationStaysInsideThisMethodTransaction() {
        Ticket ticket = repository
                .findByTenantIdAndExternalKey("SEED", "seed-key")
                .orElseThrow();

        ticket.rename("Changed only here");
        repository.flush();

        assertEquals("Changed only here",
                repository.findByTenantIdAndExternalKey(
                        "SEED", "seed-key")
                        .orElseThrow().getTitle());
    }
}
~~~

Spring TestContext runs `@Sql BEFORE_TEST_METHOD` inside the test transaction under **default transaction handling** when `@DataJpaTest` opens a transaction. The script inserts one row before each method; when the method ends, all `INSERT`/`UPDATE` changes roll back. Thus `fixtureHasOriginalValueEveryTime` works whether it runs before or after the modification method.

**`@Execution(SAME_THREAD)`** ensures methods in this class never run concurrently on the same fixed `seed-key` even if JUnit parallel mode is enabled globally; however, another class using the same `seed-key` could still collide if run in parallel against a shared DB. For full-suite parallelism, use dedicated namespaces or databases instead of sharing one fixed key.

### `@SqlConfig(transactionMode=ISOLATED)` Is a Different Choice

If the seed script runs in an **`ISOLATED` transaction**, it commits independently. `@DataJpaTest` rollback **will not delete rows committed by the script**. Subsequent runs will then hit duplicate unique-key errors. Never switch `transactionMode` to `ISOLATED` unless you intentionally need a committed baseline and pair it with explicit cleanup.

Similarly, **`data.sql`** typically runs once at application context initialization rather than per test method. Whenever tests mutate a committed baseline, use rollback or per-method reset/re-seed—never assume context caching resets the database between methods.

## 8. Test C — Real HTTP Requests Commit, So Clean Up Outside the Test Transaction

**`@SpringBootTest(webEnvironment = RANDOM_PORT)`** starts a real embedded HTTP server. A `POST` to that server runs on a servlet thread, so the `@Transactional` service commits independently of the HTTP client / JUnit test thread.

The safe pattern in this demo is **omitting `@Transactional` on the HTTP test** and using **`@BeforeEach` preclean** plus **`@AfterEach` cleanup** via `JdbcTemplate`. Each method derives its key from the method name, so no test depends on another to prepare data.

**src/test/java/com/example/testdata/HttpCommitIsolationTest.java**

~~~java
package com.example.testdata;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class HttpCommitIsolationTest {
    private static final String TENANT = "HTTP";

    @LocalServerPort
    private int port;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private String key;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, key);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, key);
    }

    @BeforeEach
    void prepare(TestInfo info) {
        key = "http-" + info.getTestMethod()
                .orElseThrow().getName();
        clean(); // Idempotent pre-clean after a previous crash.
        assertEquals(0L, count());
    }

    @AfterEach
    void tearDown() {
        clean(); // Runs without test-managed @Transactional.
        assertEquals(0L, count());
    }

    private void postAndVerify() throws Exception {
        String body = mapper.writeValueAsString(Map.of(
                "tenantId", TENANT,
                "externalKey", key,
                "title", "created via HTTP"));

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:"
                        + port + "/api/tickets"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());
        assertTrue(mapper.readTree(response.body())
                .path("id").asLong() > 0);
        assertEquals(1L, count());
    }

    @Test
    void firstPostOwnsItsKey() throws Exception {
        postAndVerify();
    }

    @Test
    void secondPostOwnsItsKey() throws Exception {
        postAndVerify();
    }
}
~~~

**Invariants upheld:**

- **`@LocalServerPort`** captures the real port of the `RANDOM_PORT` server without hardcoding `8080`.
- `@BeforeEach` computes a method-specific key and deletes any old residue scoped by `TENANT`/key.
- HTTP `POST` returns `201` with JSON `id > 0`, and `JdbcTemplate` observes the row committed by the server service.
- `@AfterEach` deletes only the committed row and asserts it is gone.
- Both methods are independent and can run standalone or in any order.

If a request fails an assertion after the server commits, `@AfterEach` still runs in JUnit's normal lifecycle to clean up. If the JVM is killed before teardown, the next run's preclean or a fresh ephemeral database cleans up the residue.

**Never add `@Transactional` to this class expecting `@AfterEach` `DELETE` to commit.** When a test has an outer test transaction, `@AfterEach` runs inside that transaction and the `DELETE` rolls back, leaving the HTTP server's committed row intact. Keep the HTTP server thread's transactions separate from the JUnit client thread's transactions.

## 9. Test D — `REQUIRES_NEW` Commits Are Not Cleaned by Outer Rollback

`IndependentTicketWriter` uses `Propagation.REQUIRES_NEW`. In the test below, the outer test-managed transaction rolls back by default, yet the inner service transaction commits independently. To observe and clean up properly, use **`@BeforeTransaction` and `@AfterTransaction`**, both of which execute outside the outer transaction.

**src/test/java/com/example/testdata/RequiresNewIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class RequiresNewIsolationTest {
    private static final String TENANT = "INNER";
    private static final String KEY = "requires-new-fixture";

    @Autowired
    private IndependentTicketWriter writer;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, KEY);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, KEY);
    }

    @BeforeTransaction
    void clearCommittedResidue() {
        clean();
        assertEquals(0L, count());
    }

    @Test
    void innerCommitSurvivesOuterRollback() {
        assertTrue(TestTransaction.isActive());
        writer.write(TENANT, KEY);
        // No assertion relying on outer transaction visibility.
    }

    @AfterTransaction
    void assertInnerCommitThenClean() {
        try {
            assertEquals(1L, count());
        } finally {
            clean();
        }
        assertEquals(0L, count());
    }
}
~~~

**Transaction timeline:**

~~~text
@BeforeTransaction: cleanup, count=0
BEGIN outer test transaction
    @Test invokes writer bean via Spring proxy
       suspend outer transaction
       BEGIN REQUIRES_NEW
       INSERT Ticket
       COMMIT inner transaction
       resume outer transaction
ROLLBACK outer test transaction
@AfterTransaction:
    row still exists from inner commit
    cleanup outside transaction, count=0
~~~

Do not try to clean up an inner committed row inside `@AfterEach` of a transactional test: `@AfterEach` still runs **inside the outer test transaction**, so the `DELETE` rolls back. Also, calling a private or self-invoked `REQUIRES_NEW` method bypasses the Spring AOP proxy and alters semantics; injecting the `@Autowired` bean preserves proper proxying.

**Connection pool note:** `REQUIRES_NEW` requires a second physical connection while the outer transaction holds its connection. This test uses H2/Hikari via Spring Boot; in production with high concurrency, size pools accordingly. Never use `REQUIRES_NEW` just to bypass test rollback; choose propagation to match real domain requirements.

## 10. Test E — `@Commit` to Verify Data Persists After the Test

Rollback is the right default for most repository tests. Occasionally you need an **intentional commit**, such as testing `@TransactionalEventListener(AFTER_COMMIT)`, transaction synchronization, or cross-transaction visibility. Whenever using **`@Commit`** or **`@Rollback(false)`**, clean up outside the test transaction.

**src/test/java/com/example/testdata/CommitCleanupTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class CommitCleanupTest {
    private static final String TENANT = "COMMIT";
    private static final String KEY = "commit-fixture";

    @Autowired
    private TicketRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, KEY);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, KEY);
    }

    @BeforeTransaction
    void baseline() {
        clean();
        assertEquals(0L, count());
    }

    @Test
    @Commit
    void commitNeedsExplicitCleanup() {
        repository.saveAndFlush(
                new Ticket(TENANT, KEY, "committed fixture"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyCommittedRowThenDelete() {
        try {
            assertEquals(1L, count());
        } finally {
            clean();
        }
        assertEquals(0L, count());
    }
}
~~~

**`@Commit` is equivalent to `@Rollback(false)`** regarding how a **test-managed transaction** ends; it does not start a transaction if `@Transactional` is absent. Here `@SpringBootTest` + `@Transactional` open the transaction, `@Commit` requests a commit when the listener finishes, and `@AfterTransaction` verifies `count = 1` outside the transaction before cleaning up.

**`@Commit` does not automatically roll back on assertion failure.** It sets commit policy; the final outcome depends on rollback-only state, commit exceptions, and listeners. If the test fails before cleanup, the `finally` block in `@AfterTransaction` still attempts to remove the row. If the JVM crashes, preclean on the next run acts as a second safety net.

## 11. `@BeforeEach` and `@AfterEach` vs. `@BeforeTransaction` and `@AfterTransaction`

Inside a test method with a TestContext-managed **Spring `@Transactional`**:

| Lifecycle Hook | Where It Runs | Typical Usage |
| --- | --- | --- |
| `@BeforeTransaction` | Outside test transaction | Preclean / check committed baseline |
| `@BeforeEach` | Inside test transaction | Create fixtures that roll back with the test |
| `@Test` | Inside test transaction | Execute and assert |
| `@AfterEach` | Inside test transaction | In-transaction checks; insufficient for deleting rows committed in other transactions |
| `@AfterTransaction` | Outside test transaction | Observe final commit/rollback state and clean up |

In **`HttpCommitIsolationTest`**, the class is **not `@Transactional`**, so `@BeforeEach`/`@AfterEach` run outside any test-managed transaction and `JdbcTemplate` cleanup commits normally.

**`@AfterTransaction` never runs when a test has no test-managed transaction.** Never copy an `@AfterTransaction` method into a non-transactional HTTP test expecting it to clean up.

### `@Sql AFTER_TEST_METHOD` Does Not Automatically Mean “Outside Transaction”

Spring's **`SqlScriptsTestExecutionListener`** executes `@Sql` scripts according to the transaction mode resolved from `@SqlConfig` and `PlatformTransactionManager`. An `AFTER_TEST_METHOD` script **can join the test transaction** and get rolled back afterward. To clean up committed data, use **`@AfterTransaction`** or a carefully controlled `@SqlConfig(transactionMode=ISOLATED)` aware of locks and execution order. Never assume a teardown script marked “after” automatically leaves all committed deletes persisted.

## 12. Spring TestContext Cache and `@DirtiesContext` Do Not Replace DB Cleanup

Spring TestContext caches `ApplicationContext` instances to reduce startup time. Two test classes sharing the same configuration reuse the same Spring beans, datasource pool, embedded H2 DB, and singleton state.

**`@DirtiesContext`** marks a context for closing or rebuilding, **not a `DELETE` command on the database**. With external PostgreSQL, MySQL, or Testcontainers databases, committed rows outlive context shutdown. Even with H2, DB lifetime depends on connections, JDBC URL, and `DB_CLOSE_DELAY`; never assume closing the context wipes the entire DB.

| Tool | What Problem Does It Solve? |
| --- | --- |
| `@DataJpaTest` rollback | DML inside test-managed transactions |
| `@DirtiesContext` | Spring context/cache state when bean definitions must rebuild |
| `@AfterTransaction` cleanup | Rows committed outside the test transaction |
| Per-method `@Sql` seed | Reproducible test baselines |
| Per-schema/per-job Testcontainers | Isolated physical databases or namespaces |
| Unique test keys | Preventing collisions across test methods |
| Explicit mock/cache resets | Shared in-memory state |

**Two separate contexts can still hit the same real database** if their JDBC URLs match. Conversely, one shared context can safely run tests if each method isolates its fixtures with solid rollback/cleanup. Track **physical database identity**, not just Spring context cache keys.

## 13. Parallel Tests Are Not Automatically Safe Because of Rollback

Two tests passing sequentially with rollback can still fail in **parallel** if both INSERT the same unique key, DELETE from the same table, write to a global cache, or touch an external resource. Rollback does not prevent two active transactions from contending on rows or locks.

Strategies:
- Assign **unique external keys per method**, plus per CI run when multiple jobs share a DB.
- When using fixed keys in `@Sql`, apply **`SAME_THREAD`**, `@ResourceLock`, or isolated databases/schemas; note that `@ResourceLock` coordinates only within a single JUnit launcher, not across separate CI jobs.
- Never run `DELETE FROM tickets` against a shared DB in a parallel suite.
- Avoid mutable static fields and singleton test fixtures.
- When tests share a fixture, keep it **immutable/read-only** or copy it into each test's transaction.
- For external systems, isolate namespaces: Redis key prefixes, per-run Kafka topic keys, dedicated object-storage paths.
- Wait on async side effects using completion signals rather than guessing with `Thread.sleep` and cleaning up too early.

**UUID keys do not replace cleanup.** They lower collision odds, yet without deletion the database accumulates residue. Across CI jobs sharing a DB server, prefer per-job schemas/databases over relying on probability and broad cleanups.

## 14. Verifying Independence Systematically

**First: run each class and method in isolation.** Example Gradle commands with a Java 17-compatible Wrapper:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.testdata.RollbackIsolationTest
./gradlew test --tests com.example.testdata.SqlSeedIsolationTest
./gradlew test --tests com.example.testdata.HttpCommitIsolationTest
./gradlew test --tests com.example.testdata.RequiresNewIsolationTest
./gradlew test --tests com.example.testdata.CommitCleanupTest
./gradlew test --tests com.example.testdata.RollbackIsolationTest.createsOwnFixtureAndRunsIndependently
~~~

On Windows, replace `./gradlew` with `gradlew.bat`. These tests are **designed to PASS** with the files and configuration above; no actual build stdout was captured here.

**Next:** run the full suite repeatedly, test alternate method orders, and test CI parallelism if supported. Whenever a test fails only in the full suite, check:
- Did a unique key leak from an earlier run?
- Did `@Commit` or `REQUIRES_NEW` commit without cleanup?
- Did an HTTP request execute on a server thread?
- Did an `@Sql` seed run with `ISOLATED` transaction mode?
- Did `@BeforeAll` create shared setup mutated by other tests?
- Is there static/singleton mutable state or caching?
- Is a database surviving across `ApplicationContext` lifetimes?

**Using JUnit random order solely for detection:**

~~~java
@TestMethodOrder(MethodOrderer.Random.class)
class RandomizedTestExamples {
    // Every @Test must still set up and clean up independently.
}
~~~

This is an **illustrative snippet** needing JUnit imports and test methods to run. Random order helps expose hidden dependencies without fixing the root cause; reproduce failures using the seed and fix the underlying fixture or cleanup.

### Truly Independent When Run Alone

A common anti-pattern is creating an account in class-level `@BeforeAll` and mutating it across multiple test methods. When running a single method via an IDE or Gradle filter, `@BeforeAll` still executes, creating an illusion of independence while methods actually share mutable state. Verify every method requiring pristine state resets it via `@BeforeEach`, `@Sql`, or fresh entities.

Never let Test B read static variables or IDs from Test A even if `@BeforeAll` builds a baseline. Read-only baselines can be valid, provided mutations stay scoped.

## 15. Testcontainers and Production Database Semantics

H2 is fast, enforces real schemas and constraints, and works nicely for unit/slice tests. However, production databases can differ in:
- Sequence/identity behavior after rollback.
- Unique/FK constraints, isolation levels, locking, and deadlocks.
- SQL dialects, collations, data types, and native queries.
- Read/write concurrency across connections.
- Flyway/Liquibase migrations.
- Transaction visibility on commit vs. rollback.

When behavior depends on these details, add **Testcontainers** using the closest matching engine and version. Remember containers may be **reused across test classes**, and databases inside containers **do not auto-reset before each method**. Pick one schema/database per class or job, or enforce clean transactions and fixture cleanup.

**`@DirtiesContext` does not reset Testcontainers.** It refreshes the Spring context without wiping the physical database running inside the container. Ordinary few-second tests shouldn't start and stop containers per method needlessly; balance speed against isolation needs.

## 16. Common Pitfalls and Fixes

| Symptom | Common Cause | Remedy |
| --- | --- | --- |
| Test B passes only after Test A | B relies on A's fixture | Set up B's data inside B |
| `@TestMethodOrder` makes suite pass, single run fails | Ordering masks missing fixtures | Remove dependency; never force order |
| Unique constraint violation on rerun | Committed row from prior test/run | Preclean/postclean or dedicated DB |
| Row appears inside `@DataJpaTest` then vanishes | Default rollback | Intended behavior; avoid adding `@Commit` needlessly |
| Data remains after `@SpringBootTest` | Test lacks `@Transactional` or service commits externally | Identify TX boundaries and clean up explicitly |
| HTTP test leaves rows despite `@Transactional` on JUnit test | Server thread runs its own transaction | Clean up outside the test TX |
| `REQUIRES_NEW` row survives outer rollback | Inner transaction committed | Clean up in `@AfterTransaction` |
| `@AfterEach` `DELETE` leaves committed rows behind | `DELETE` joined outer TX and rolled back | Move cleanup outside the transaction |
| Duplicate `@Sql` seed | `ISOLATED` seed or committed baseline from earlier run | Check `@SqlConfig` and teardown |
| `@DirtiesContext` leaves DB dirty | Context cache differs from DB lifecycle | Reset DB or `DELETE` specific keys |
| Generated ID differs from expected number | Identity counter does not roll back | Assert business keys and row behavior |
| Tests fail under parallel execution | Shared business keys, broad deletes, locks | Unique namespaces/schemas, `@ResourceLock` |
| Shared mutable fixture altered by another test | `@BeforeAll`/singleton/static state | Per-test fixtures or read-only baselines |
| Test passes once, fails on rerun | Residue from previous run | Idempotent preclean |
| Async row appears after cleanup | Cleanup ran before async task finished | Await completion before cleaning up |
| `@Sql AFTER_TEST_METHOD` cleanup fails to persist | Ran in rolling-back transaction | `@AfterTransaction` or intentional `ISOLATED` |
| H2 passes, production DB fails | Dialect/isolation differences | Testcontainers with production engine |
| Cleanup wipes another test's data | `DELETE` lacks tenant/key filter | Scoped cleanup, ephemeral DBs |
| `@Commit` test fails and leaves row | Commit policy applied, teardown skipped | `finally`/post-clean and preclean |
| Preemptive timeout leaks data | Test body runs on another thread | Avoid `assertTimeoutPreemptively` with test transactions |

## 17. Self-Test Questions

**1.** Test B uses `ticketId` created by Test A. Running B alone fails. Fix with `@Order`? **No**; B must create its own `Ticket`/fixture.

**2.** `@DataJpaTest` calls `saveAndFlush` and sees `count=1`. Does the row persist after the method? **Not by default**, because of rollback.

**3.** Does `@SpringBootTest` automatically roll back every test method? **No**; it requires `@Transactional` on the test or an explicit policy.

**4.** An HTTP `POST` executes on a server thread and commits. Does `@Transactional` on the JUnit client roll back that data? **Not automatically.**

**5.** Is an inner `REQUIRES_NEW` commit inside a transactional test undone by outer rollback? **No.**

**6.** Does `@AfterEach` in a transactional test run before or after outer rollback? **Before the transaction ends**, so `DELETE` can roll back.

**7.** What can `@AfterTransaction` do that `@AfterEach` cannot? **Observe the final committed/rolled-back state outside the test transaction and clean up committed rows.**

**8.** Can default `@Sql` inside `@DataJpaTest` roll back with the test method? **Yes**, when the script joins the test transaction per configuration.

**9.** Does `@SqlConfig(transactionMode=ISOLATED)` create committed fixtures? **It can**, because the script runs and commits in its own transaction.

**10.** Does `@DirtiesContext` automatically truncate PostgreSQL? **No.**

**11.** Does in-memory H2 automatically create a new DB for every method in one context? **No.**

**12.** Must generated IDs reset to 1 after rollback? **No**; sequence/identity values can continue incrementing.

**13.** Are UUID test keys alone enough? **No**; cleanup and external state isolation are still required.

**14.** If two parallel tests both `DELETE` all `Ticket` rows before running, are they independent? **No**; they can wipe each other's fixtures.

**15.** Does one passing `MethodOrderer.Random` run prove order independence? **No**; it is only a detection aid.

**16.** Can `@Commit` leave data behind after a test fails? **Yes**, because commit policy is separate from assertion results.

**17.** Does Testcontainers always spin up a fresh DB before every method? **No**, that depends on lifecycle and reuse settings.

**18.** Is it safe for `@BeforeAll` to create one entity mutated by multiple tests? **No**, unless shared mutable state is reset properly.

**19.** Should table-wide `DELETE` cleanup be run on a shared test DB? **No**; scope by tenant/key or use ephemeral DBs.

**20.** What is the single most important invariant? **Each test owns and manages its own data, needing no predecessor and leaving no residue affecting other tests.**

### QA Checklist

- Does every test create its own fixtures and run standalone?
- Are static IDs and `@TestMethodOrder` avoided for hiding dependencies?
- Is it clear which tests are transactional with default rollback?
- Is JPA flush distinguished from DB commit?
- Are `@Sql` scripts clearly joining the test transaction or `ISOLATED`?
- Do tests use per-tenant/per-method/per-run keys instead of asserting hardcoded generated IDs?
- Are HTTP, `REQUIRES_NEW`, `@Commit`, and async side effects cleaned up outside test rollback?
- Are `@BeforeEach`/`@AfterEach` vs. `@BeforeTransaction`/`@AfterTransaction` placed properly?
- Is `@DirtiesContext` never mistaken for DB cleanup?
- Are collisions prevented when running in parallel or sharing a CI database?
- Is every cleanup scoped to exact rows without touching other tests or production data?
- Are baseline fixtures safe from un-rolled-back mutations?
- Have tests been verified standalone, repeatedly, and in alternate orderings?
- Do production DB semantics have integration tests against the matching engine?
- Do off-DB states (caches, files, queues, sessions) have independent lifecycles?

**Conclusion:** An independent test **needs no data left behind by earlier tests** and leaves the environment predictable after finishing. Use **`@DataJpaTest` rollback** for in-transaction DB operations, **per-method `@Sql`** for baselines, and **genuine out-of-transaction cleanup** for data committed via HTTP, `REQUIRES_NEW`, or `@Commit`. Add dedicated keys, context/database isolation, and randomized/parallel order checks as needed. That turns a Spring Boot suite from “green only in one familiar order” into a reliable test suite.

## Official References

- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Executing SQL Scripts with @Sql: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Data JPA — Reference Documentation: https://docs.spring.io/spring-data/jpa/reference/
- JUnit 5 — Test Execution Order and Parallel Execution: https://junit.org/junit5/docs/current/user-guide/
- Spring Framework — Transaction Propagation REQUIRES_NEW: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
