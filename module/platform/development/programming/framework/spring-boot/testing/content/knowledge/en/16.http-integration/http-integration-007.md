# HTTP Integration: Server-Committed Data and Post-Test Cleanup Strategies

## Learning objectives

When testing a Spring Boot API over real HTTP, many developers put `@Transactional` on the test and expect all data created by requests to automatically roll back after each method. This assumption is **incorrect** in the standard case of `@SpringBootTest(webEnvironment = RANDOM_PORT)` or `DEFINED_PORT`: requests travel over a socket to the web server; HTTP handling executes on a **server thread**, while the JUnit test and Spring TestContext-managed transaction run on the **test thread**. The server's database transaction can **commit independently** before the test finishes.

Without a cleanup mechanism, leftover "dirty" data can cause subsequent tests to fail, create order-dependent results, trigger unique constraint errors, skew record counts, block parallel execution, and become dangerous if pointed at a production database by mistake.

After this lesson, you will be able to:

- Explain the boundary between test transactions, HTTP requests, server transactions, and database commits.
- Compare socket-free `MockMvc` against `@SpringBootTest(RANDOM_PORT)` using real HTTP.
- Prove with a Java 17 test that rolling back a test-thread transaction **does not delete** records already committed through the API.
- Organize safe cleanup using `@AfterEach`, HTTP DELETE APIs, independent transactions, `@AfterTransaction`, `@Sql`, isolated databases/schemas, or Testcontainers.
- Choose a strategy based on data characteristics, test level, DB access permissions, asynchronous processing, and parallel execution.
- Write order-independent tests without dangerously calling global `deleteAll()`.
- Distinguish confirmed committed state from eventual consistency and non-transactional side effects.
- Diagnose test flakiness, connection pool deadlocks, "phantom" rollbacks, unclean data, and wrong database environments.

This lesson includes a runnable example using **Java 17, Spring Boot 3.3.5, Spring MVC, Spring Data JPA, H2, JUnit Jupiter, Gradle, and `TestRestTemplate`**. Snippets outside the runnable project are labeled **illustrative**.

## 1. Two mental tracks: test methods and HTTP handlers do not share a transaction

First, distinguish **the test sending the request** from **the application handling the request**.

A direct service call on the same thread can join the test's existing transaction (depending on transaction manager, propagation, and configuration). However, when a test sends HTTP to a real embedded server, controller/service work executes on a **different thread**. Standard imperative Spring transactions are thread-bound via transaction synchronization; they **do not travel over an HTTP request from the test thread to the server thread**.

~~~text
JUnit test thread                         Spring Boot server thread
-----------------                         -------------------------
@BeforeEach creates fixture
@Transactional test transaction (if any)
    |
    | HTTP POST /api/tasks --------------->|
    |                                       | Controller receives request
    |                                       | Service @Transactional
    |                                       | BEGIN server transaction
    |                                       | INSERT INTO http_tasks ...
    |                                       | COMMIT server transaction
    |<------------- HTTP 201 Created ------|
    |
    | Assert response/GET
    | Test finishes
    | ROLLBACK test transaction
    v
Server-committed data remains in the database
~~~

**Core takeaway:** Two transactions can access the same database yet **are not the same transaction**. Rolling back transaction A on the test thread does not "hunt down and undo" transactions B already committed on the server thread. Once a server transaction commits, the data is visible to other transactions unless an explicit cleanup/compensation mechanism runs.

This behavior is explicitly documented by Spring Boot for `@SpringBootTest` with `RANDOM_PORT` or `DEFINED_PORT`. It is not a bug in JUnit, Spring Data JPA, or H2. Tests must explicitly state **who is responsible for creating data and who is responsible for deleting it**.

### How far does test rollback actually reach?

`@Transactional` on a Spring test (when `TransactionalTestExecutionListener` and a suitable transaction manager are active) can start a **test-managed transaction** that rolls back after the test by default. Repository/service operations **within that transaction's scope** typically participate in it given matching propagation.

However:

- An HTTP client only **sends requests**; it does not carry the test's JDBC transaction over to the server.
- The servlet container accepts requests on a separate worker thread.
- `@Transactional` on the server-side service creates/joins a **server-side transaction**.
- The service returns cleanly after the interceptor commits the transaction; data is typically committed before the response goes out.
- An async API might return `202 Accepted` **before** data is written; in that case test eventual consistency explicitly rather than assuming HTTP 202 means the DB has committed.
- If a service uses `REQUIRES_NEW`, messaging, schedulers, or a different transaction manager, commit boundaries can be even more nuanced.

## 2. Distinguishing Spring test types

| Test type | Real HTTP server? | How is the controller invoked? | What can rollback affect? |
| --- | --- | --- | --- |
| JUnit unit test, `new Service(...)` | No | No HTTP | No Spring test transaction unless created manually |
| `@DataJpaTest` | No | Calls repository/JPA on test thread | Typically rolls back operations inside the test-managed transaction |
| `@WebMvcTest` + `MockMvc` | No | Mock Servlet request in JVM, normally same test thread | Does not imply real HTTP server/transaction; depends on context and operations |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | No | `MockMvc.perform(...)` | Can join the test transaction for same-thread synchronous handling; consider propagation/async |
| `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Yes | Real HTTP over socket → server thread | Test-thread rollback **does not roll back server-side commits** |
| `@SpringBootTest(DEFINED_PORT)` + HTTP client | Yes | Real HTTP on configured port | Same transaction semantics as `RANDOM_PORT`; adds port collision risk |
| End-to-end test from another process/container | Yes | HTTP over network/proxy | Shares no local test transaction; must clean up via API/DB/fixtures |

**Do not equate "full context" with "real HTTP".** `@SpringBootTest` defaults to `MOCK`, which starts no real server. When the goal is testing database commits across network API calls, use `RANDOM_PORT` and a real HTTP client. When only checking HTTP mapping/validation, `MockMvc` may be enough and faster.

### Why can MockMvc mislead learners?

Suppose:

~~~java
@Transactional
@Test
void createsAndRollsBackInMockMvc() throws Exception {
    mockMvc.perform(post("/api/tasks")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"demo\"}"))
        .andExpect(status().isCreated());
}
~~~

This is an **illustrative snippet**, omitting class/imports. In many synchronous MVC cases, `MockMvc` runs the handler on the test thread; repository operations can join the test transaction and get rolled back. Switching the test to `TestRestTemplate` against a real server **changes transaction semantics**, even if the request URL, payload, and assertions look identical.

Furthermore, if the MVC handler uses `@Async`, `REQUIRES_NEW`, event listeners, or other threads, even a MockMvc test should not assume "all side effects definitely roll back". Always inspect the actual boundary.

## 3. How do "HTTP 201" and "database committed" relate?

In a typical synchronous API:

1. Controller receives POST.
2. Service is invoked via its `@Transactional` proxy.
3. Service calls `repository.save(...)`.
4. The transaction interceptor **commits** if the service exits normally.
5. Controller builds the 201 response.

Thus, when the client receives 201, writes in **that service transaction** have usually committed. Yet this is a **conditional pattern**, not a universal law across all architectures.

Exceptions to know:

- The API returns **202 Accepted** and enqueues a job; the DB may not have changed yet.
- Writes happen via an event listener / `@Async` after the response.
- The DB transaction commits while publishing a message fails, or vice versa.
- The service merely calls `save` inside a longer caller-managed transaction; the commit happens after the method returns.
- The API only writes to a cache/broker, with no database record yet.
- The response drops on the network **after the server commits**; the client sees a timeout while the data already exists.
- Reads come from a read replica with replication lag; an immediate follow-up GET might not see data committed on primary yet.

When writing tests, name precisely what you want to prove: "POST returns 201", "the record committed to the primary database", "a separate GET reads the record", or "eventual consistency settles within a time bound". These are **different observable conditions**.

## 4. Principles for choosing a data cleanup strategy

Cleanup should meet at least five criteria:

1. **Proper scope:** delete only data created by this test, never other tests' data or production data.
2. **Proper timing:** clean up **after** the server has finished writing/side effects within test scope.
3. **Proper transaction:** cleanup statements must **commit**, not get rolled back alongside a test transaction.
4. **Failure safety:** use `@AfterEach`, `try/finally`, or fixture lifecycles so cleanup runs even when assertions fail.
5. **Independence and repeatability:** tests run standalone, as a full suite, or in parallel without order dependencies.

Common approaches:

| Approach | Pros | Limits/risks |
| --- | --- | --- |
| `@AfterEach` + repository delete by ID/test key | Explicit, narrow scope, easy to read | Must execute outside a rolled-back transaction and requires DB access |
| Cleanup via HTTP DELETE endpoint | Exercises public lifecycle, no direct DB access needed in test | DELETE API may lack permissions, fail on network errors, or miss non-API side effects |
| Cleanup in `finally` | Guaranteed to run when assertions throw inside the JVM | Does not run if process is killed/crashes; can mask original exception if cleanup throws |
| `@AfterTransaction` | Hook running after the test transaction ends | Only runs for transactional tests; requires understanding transaction lifecycle |
| `@Sql(AFTER_TEST_METHOD)` with right transaction mode | Manages test data cleanly with SQL | Table-wide scripts are dangerous; default transaction mode may not fit |
| `TransactionTemplate` with a new transaction | Explicit commit/rollback control | Requires proper propagation and transaction manager config |
| Separate database/schema per test/class | Strong isolation, easy reset via drop schema | Costs startup/migration/resources |
| Testcontainers lifecycle | Production-like DB engine; isolates infrastructure | Reused/shared containers still need cleanup; startup time |
| `@DirtiesContext` | Discards a state-polluted Spring `ApplicationContext` | **Does not roll back or delete data already committed in external DBs** |
| Database snapshot / full truncate | Fast in a dedicated test DB, thorough reset | Unsafe when tests share a DB; check FKs/sequences/parallelism |

A strong strategy **need not** rely on just one technique: for instance, use Testcontainers PostgreSQL isolated from production, assign a namespace per test, clean up by test ID after HTTP requests, and tear down the container when the suite ends.

## 5. Runnable example: Spring Boot, JPA, H2, and real HTTP

This example demonstrates a minimal task-management application. We want to verify:

- `POST /api/tasks` creates a record and returns 201.
- `GET /api/tasks/{id}` called by a **separate HTTP request** reads the committed record.
- Rolling back a transaction started on the **test thread** does not undo a task already committed by the server thread.
- `DELETE /api/tasks/{id}` deletes via HTTP and a follow-up GET returns 404.
- Invalid input returns 400 and leaves no record behind.
- Each test generates a unique task title shaped `it-<UUID>`; `@AfterEach` cleanup deletes **only the record with that title** via a repository query in its own transaction.

### 5.1. Why use a random task title?

Many test examples call `repository.deleteAll()` before/after every method. That is only relatively safe when the database is **exclusively dedicated to a single isolated test** with no other suite running concurrently. If methods/classes run in parallel against the same DB, test A's `deleteAll()` can wipe test B's data.

This project uses a unique `title` per test as a **cleanup key**. This is a simple way to teach the mindset of "delete only what you created", not a recommendation to turn titles into security identifiers in production. Real systems should use a **`testRunId`, dedicated test tenant, correlation ID, or tracked resource IDs** governed by proper permissions and contracts.

### 5.2. Directory structure

~~~text
http-commit-cleanup-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/httpcommit/
    │   ├── HttpCommitApplication.java
    │   ├── TaskEntity.java
    │   ├── TaskRepository.java
    │   ├── TaskService.java
    │   └── TaskController.java
    └── test/java/com/example/httpcommit/
        └── HttpServerCommitIntegrationTest.java
~~~

This is a **complete project in terms of source**. If you do not have the Gradle Wrapper yet, generate it using a compatible Gradle installation or use the repository's committed wrapper; `gradle-wrapper.jar` is a binary file that cannot be hand-typed.

**`settings.gradle`**

~~~groovy
rootProject.name = 'http-commit-cleanup-demo'
~~~

**`build.gradle`** — Java 17, Spring Boot 3.3.5, Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

- `spring-boot-starter-web` starts the embedded Servlet server when using `RANDOM_PORT`.
- `spring-boot-starter-data-jpa` provides JPA, Hibernate, the transaction manager, and Spring Data repositories.
- H2 lives only on the **test runtime classpath** to run an in-memory DB in tests without external DB servers.
- `spring-boot-starter-test` provides Spring TestContext, JUnit Jupiter, and `TestRestTemplate`.
- `junit-platform-launcher` and `useJUnitPlatform()` configure JUnit Platform for Gradle.

Never carry `spring.jpa.hibernate.ddl-auto=create-drop` from the example into production: that setting is **strictly for creating/dropping test schemas**. In production, use controlled migration/schema management.

### 5.3. Spring Boot application

**`src/main/java/com/example/httpcommit/HttpCommitApplication.java`**

~~~java
package com.example.httpcommit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCommitApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpCommitApplication.class, args);
    }
}
~~~

The class sits in root package `com.example.httpcommit`, so Boot component scan finds the controller/service and repository/entity.

### 5.4. JPA entity

**`src/main/java/com/example/httpcommit/TaskEntity.java`**

~~~java
package com.example.httpcommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "http_tasks")
public class TaskEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String title;

    protected TaskEntity() {
        // Required by JPA
    }

    public TaskEntity(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

`GenerationType.IDENTITY` uses database-assigned IDs, supported by H2 in this setup. `unique = true` keeps the demo simple: one test title corresponds to at most one record. In real products, titles are usually **not unique keys**; when applying cleanup strategies, use resource IDs, tenant/test markers, or contract-appropriate business keys.

### 5.5. Repository supporting scoped cleanup

**`src/main/java/com/example/httpcommit/TaskRepository.java`**

~~~java
package com.example.httpcommit;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface TaskRepository
        extends JpaRepository<TaskEntity, Long> {

    long countByTitle(String title);

    @Modifying
    @Transactional
    @Query("delete from TaskEntity t where t.title = :title")
    int deleteByExactTitle(@Param("title") String title);
}
~~~

`deleteByExactTitle` is a JPQL bulk DELETE scoped to the **test's title**:

- `@Modifying` tells Spring Data JPA this is a modifying query.
- `@Query` specifies the DELETE explicitly without relying on derived method-name inference.
- `@Param` binds `:title` without depending on bytecode parameter names.
- `@Transactional` ensures the repository runs the delete in a transaction when called outside an existing one and **commits when the method completes normally**.
- Returning `int` gives the deleted row count; zero is valid if the DELETE API already removed it or POST failed.

**Limitation:** If this method is called **inside a test-managed transaction that rolls back**, default `@Transactional` (`REQUIRED` propagation) can join that transaction and roll back the cleanup too. Therefore, the project **does not annotate the test class/method with `@Transactional`**; the rollback proof uses `TransactionTemplate` in a small isolated scope.

Never run a JPQL delete without a `WHERE` clause on a shared database. In multi-table systems, cleanup must also respect foreign keys/aggregates and related side effects; never assume deleting one parent row cleans everything.

### 5.6. Service: server transaction commits independently

**`src/main/java/com/example/httpcommit/TaskService.java`**

~~~java
package com.example.httpcommit;

import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TaskEntity create(String title) {
        return repository.saveAndFlush(new TaskEntity(title));
    }

    @Transactional(readOnly = true)
    public Optional<TaskEntity> findById(Long id) {
        return repository.findById(id);
    }

    @Transactional
    public boolean delete(Long id) {
        if (!repository.existsById(id)) {
            return false;
        }
        repository.deleteById(id);
        return true;
    }
}
~~~

`@Transactional` on public methods of `@Service` is applied by the Spring proxy when invoked by the controller. When `create` finishes normally, the transaction interceptor commits before returning control to the controller. `saveAndFlush` pushes SQL to the database before the method exits, yet **flush is not commit**; commit still happens when the transaction completes. This distinction matters: data can be flushed within a transaction and still roll back later.

Similarly, `delete` runs inside a server-side transaction. When HTTP DELETE returns 204 after the service finishes, the deletion has typically committed to the DB in this synchronous example.

A production application must handle races between `existsById` and `deleteById`, optimistic locking/idempotency, and deletion permissions. The demo is minimal to focus on **transaction boundaries and cleanup**, without claiming to be a full concurrent API design.

### 5.7. Controller providing POST, GET, and DELETE

**`src/main/java/com/example/httpcommit/TaskController.java`**

~~~java
package com.example.httpcommit;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    public record CreateTaskRequest(String title) {
    }

    public record TaskResponse(Long id, String title) {
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @RequestBody CreateTaskRequest request) {

        if (request == null || request.title() == null
                || request.title().isBlank()
                || request.title().length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid title");
        }

        TaskEntity saved = service.create(request.title());
        TaskResponse body = new TaskResponse(
                saved.getId(), saved.getTitle());

        URI location = URI.create(
                "/api/tasks/" + saved.getId());

        return ResponseEntity.created(location).body(body);
    }

    @GetMapping("/{id}")
    public TaskResponse find(@PathVariable("id") Long id) {
        TaskEntity found = service.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "task not found"));

        return new TaskResponse(
                found.getId(), found.getTitle());
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @PathVariable("id") Long id) {

        if (!service.delete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "task not found");
        }

        return ResponseEntity.noContent().build();
    }
}
~~~

**Demo API contract:**

| HTTP | Success | Data/side effect |
| --- | --- | --- |
| POST `/api/tasks` | 201 Created + JSON `id`, `title` + `Location` | Creates a task in a server transaction |
| GET `/api/tasks/{id}` | 200 OK + JSON | Reads existing data |
| DELETE `/api/tasks/{id}` | 204 No Content | Deletes the task in a server transaction |
| GET/DELETE non-existent ID | 404 Not Found | Creates no task |
| POST with empty/blank or >100-char title | 400 Bad Request | Writes no data |

The service returns an internal JPA entity while the controller maps it to a **response record** to avoid directly serializing entities/database contracts. The code requires no login because the demo omits Spring Security; in real products, enforce auth/authorization and prevent unauthorized users from deleting arbitrary resources.

## 6. JUnit integration test: real commits and proper cleanup

**`src/test/java/com/example/httpcommit/HttpServerCommitIntegrationTest.java`**

~~~java
package com.example.httpcommit;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import com.example.httpcommit.TaskController.CreateTaskRequest;
import com.example.httpcommit.TaskController.TaskResponse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = HttpCommitApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "spring.datasource.url="
                + "jdbc:h2:mem:http_commit_demo;DB_CLOSE_DELAY=-1",
            "spring.datasource.username=sa",
            "spring.datasource.password=",
            "spring.jpa.hibernate.ddl-auto=create-drop",
            "spring.jpa.open-in-view=false"
        })
class HttpServerCommitIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private TaskRepository repository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private String testTitle;

    @BeforeEach
    void setUp() {
        testTitle = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanCommittedData() {
        // Test is NOT annotated with @Transactional.
        // Repository method opens a cleanup transaction and commits.
        // Deletes only the record whose title was created by this test method.
        repository.deleteByExactTitle(testTitle);
    }

    private TaskResponse createThroughHttp() {
        ResponseEntity<TaskResponse> response =
                client.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(testTitle),
                        TaskResponse.class);

        assertEquals(HttpStatus.CREATED,
                response.getStatusCode());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().id());
        assertEquals(testTitle, response.getBody().title());

        return response.getBody();
    }

    @Test
    void postCommitsAndAnotherHttpGetSeesTheData() {
        assertTrue(port > 0);

        TaskResponse created = createThroughHttp();

        // Repository query runs on test thread AFTER HTTP response.
        // No test-managed transaction wraps this method.
        assertEquals(1L, repository.countByTitle(testTitle));

        ResponseEntity<TaskResponse> fetched =
                client.getForEntity(
                        "/api/tasks/{id}",
                        TaskResponse.class,
                        created.id());

        assertEquals(HttpStatus.OK, fetched.getStatusCode());
        assertNotNull(fetched.getBody());
        assertEquals(created.id(), fetched.getBody().id());
        assertEquals(testTitle, fetched.getBody().title());
    }

    @Test
    void rollingBackClientThreadDoesNotUndoServerWrite() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.executeWithoutResult(status -> {
            // HTTP handler runs on a different server thread/transaction.
            createThroughHttp();

            // Rolls back ONLY the transaction running on the TEST THREAD.
            status.setRollbackOnly();
        });

        // After test-thread rollback, the server write remains committed.
        assertEquals(1L, repository.countByTitle(testTitle));
    }

    @Test
    void deleteThroughHttpCommitsAndNextGetReturns404() {
        TaskResponse created = createThroughHttp();

        ResponseEntity<Void> deleted =
                client.exchange(
                        "/api/tasks/{id}",
                        HttpMethod.DELETE,
                        HttpEntity.EMPTY,
                        Void.class,
                        created.id());

        assertEquals(HttpStatus.NO_CONTENT,
                deleted.getStatusCode());

        assertEquals(0L, repository.countByTitle(testTitle));

        ResponseEntity<String> afterDelete =
                client.getForEntity(
                        "/api/tasks/{id}",
                        String.class,
                        created.id());

        assertEquals(HttpStatus.NOT_FOUND,
                afterDelete.getStatusCode());
    }

    @Test
    void invalidPostDoesNotCreateAnyRecord() {
        ResponseEntity<String> response =
                client.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest("   "),
                        String.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals(0L, repository.countByTitle(testTitle));
    }
}
~~~

### Why does this project use `TransactionTemplate`?

In the second test, `TransactionTemplate` starts **a local transaction on the JUnit thread**. Inside the callback, the test sends an HTTP POST via `TestRestTemplate`. The service on the server thread creates its own transaction, writes the task, and commits. Then the callback calls `status.setRollbackOnly()`; only the test-thread transaction rolls back.

After the callback exits, `repository.countByTitle(testTitle)` runs **outside the rolled-back transaction** and still finds 1 row. Thus the test directly proves the difference without putting `@Transactional` on the whole test class — because doing so could cause `@AfterEach` to execute **inside the test transaction and get rolled back too**.

### Why can `@AfterEach` clean up data properly here?

- Neither the class nor the test method has test-level `@Transactional`, so `@AfterEach` runs outside any test-managed transaction.
- Repository `deleteByExactTitle` is marked `@Transactional`, so Spring opens a fresh transaction when needed and commits the DELETE.
- Server-committed data is visible to the repository at cleanup time under the synchronous conditions of this example.
- `@AfterEach` is invoked by JUnit even if an assertion inside the test method throws normally, making it the default cleanup path per test case.
- If the DELETE test already removed the task, cleanup returns 0 rows — which is not an error.
- If POST was rejected, cleanup likewise deletes nothing, staying idempotent.

**Do not confuse this with an absolute cleanup guarantee:** `@AfterEach` does not run if the JVM is killed, the machine crashes, the process hits a fatal error, or the container vanishes. For long-lived test infrastructure, add TTLs, schema teardown, database resets, or run-ID-based cleanup jobs where appropriate.

### Why use a unique title instead of `deleteAll()`?

Each test generates `testTitle = "it-" + UUID.randomUUID()`, so even if multiple methods run concurrently against the same demo database, method A will not call `deleteAll()` and wipe tasks created by method B. `countByTitle(testTitle)` assertions are also unaffected by other tests' records.

However, a UUID title is not a replacement for **security ownership**; it is merely a test fixture key in a dedicated in-memory test database. When real applications allow duplicate titles, use a `testRunId`/test tenant marker or track created resource IDs rather than adding a unique constraint just for test cleanup.

## 7. Running the tests and verifying results

From the project root containing `settings.gradle`, `build.gradle`, and `gradlew`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run just this class:

~~~bash
./gradlew test --tests 'com.example.httpcommit.HttpServerCommitIntegrationTest'
~~~

There are **4 `@Test` methods**, with no `@ParameterizedTest` or `@RepeatedTest` in the project. With the right demo configuration, expect **4 passing tests**.

Gradle/JUnit reports typically appear at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.httpcommit.HttpServerCommitIntegrationTest.xml
~~~

There is no `System.out.println` in the source, so **there is no fixed business stdout**; Gradle reports `BUILD SUCCESSFUL` when the build succeeds. If the task hits the cache and shows `UP-TO-DATE`/`FROM-CACHE`, results may be reused; when investigating, force re-execution with:

~~~bash
./gradlew test --rerun-tasks
~~~

The Gradle Wrapper must be generated from a compatible Gradle version or use the repository's existing wrapper; for this Java 17 / Spring Boot 3.3.5 demo you can bootstrap it, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, and `gradle-wrapper.jar` to VCS per team policy. On CI, a matching JDK 17 is still required; the wrapper does not automatically provision a JDK in every setup.

### What the tests actually prove

| Test | Proof | What it does not automatically prove |
| --- | --- | --- |
| `postCommitsAndAnotherHttpGetSeesTheData` | POST 201, repository reads row, separate HTTP GET returns data | Production DB behaves identically to H2 |
| `rollingBackClientThreadDoesNotUndoServerWrite` | Test-thread transaction rollback does not erase server write | All transaction/async modes share identical semantics |
| `deleteThroughHttpCommitsAndNextGetReturns404` | API DELETE removes record in the demo | All non-DB side effects were also removed |
| `invalidPostDoesNotCreateAnyRecord` | Invalid input returns 400, no row matches test key | No errors/side effects occurred anywhere in the system |

Using a **new GET after POST** is crucial: it prevents tests from trusting only the POST response or a JPA persistence context holding an uncommitted entity in a single transaction. It creates an observation from an independent request, close to a real HTTP consumer.

## 8. Why not put `@Transactional` on the entire real-HTTP test class?

Consider this abbreviated snippet:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class MisleadingHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void createsTask() {
        client.postForEntity(
                "/api/tasks",
                new CreateTaskRequest("sample"),
                String.class);

        // Spring TestContext will roll back the test's transaction
        // but does NOT automatically roll back server-committed transactions.
    }
}
~~~

This is a **warning snippet**, lacking full imports/type declarations. When Spring TestContext wraps the test method in a transaction, the test transaction rolls back by default, yet the server-side transaction can still commit.

Worse yet, if you add:

~~~java
@AfterEach
void cleanup() {
    repository.deleteAll();
}
~~~

inside a **transactional test class**, JUnit's `@AfterEach` normally runs **inside the test-managed transaction**. That `deleteAll()` can join the test transaction and get rolled back afterward, making cleanup **completely ineffective** against server-committed data. This is the classic trap where the author thinks cleanup ran while the database still retains the records.

### When is `@AfterTransaction` useful?

Spring TestContext provides the hook:

~~~java
@AfterTransaction
void cleanupAfterTestTransaction() {
    repository.deleteByExactTitle(testTitle);
}
~~~

This snippet is **only illustrative** for tests already configured with `@Transactional` and a suitable transaction manager. `@AfterTransaction` runs **after the test-managed transaction ends**, allowing repository cleanup to open a fresh transaction and commit. Requirements: the test key must still be held on the test instance and the cleanup method must be executed by Spring TestContext per lifecycle.

Do not use `@AfterTransaction` as a default hook for tests **without a test-managed transaction**; it is not a general replacement for `@AfterEach` across JUnit tests. For real-HTTP integration tests, the simplest and easiest-to-review pattern is usually **omitting `@Transactional` on the test class** and explicitly cleaning up created resources.

### Can `TransactionTemplate` with `REQUIRES_NEW` be used for cleanup?

Yes, when explicit transaction control is truly needed:

~~~java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.executeWithoutResult(status ->
        repository.deleteByExactTitle(testTitle));
~~~

This snippet uses injected fields and `TransactionTemplate`/`TransactionDefinition` imports. `REQUIRES_NEW` creates an independent transaction and suspends any existing one. However:

- If the test already holds a database connection open, opening a second connection can exhaust the pool during parallel runs.
- `REQUIRES_NEW` will not fix pointing at the wrong DB or writing an overly broad DELETE query.
- `REQUIRES_NEW` is not always necessary: when the test method is non-transactional like the runnable project, `@Transactional` with default propagation on the repository cleanup method suffices.
- When multiple transaction managers exist, explicitly specify the **right manager/DataSource**.

## 9. `@Sql` after tests: usable, but you must understand transaction mode

Spring TestContext provides `@Sql` to execute SQL scripts across test lifecycle phases. A common pattern:

~~~java
@Sql(
        scripts = "/sql/cleanup-tasks.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
class TaskHttpTest {
    // ...
}
~~~

This is an illustrative snippet: it requires a real script file, imports, and Spring test context. In a real-HTTP test whose test method has `@Transactional`, a cleanup script running inside the **test transaction and then rolling back** will fail its goal unless you pick the right transaction semantics.

One option when SQL cleanup needs an independent commit is:

~~~java
@Sql(
    scripts = "/sql/cleanup-tasks.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

This illustrates `ISOLATED` so the script runs in its own transaction with matching configuration. **Do not copy a raw `"DELETE FROM http_tasks"` script into a shared DB**: the script must scope by test key/schema or run against a completely isolated database. Because SQL scripts are static resources, passing per-test random markers into a script may require extra fixture tooling; in the runnable example, a repository query by `testTitle` is easier to control.

### Why isn't `@Sql` the best choice for every case?

- SQL cleanup is coupled to the real dialect and schema.
- Static scripts struggle to target resources dynamically created by **a randomized test method**.
- With foreign keys, deletion order matters.
- With multiple DataSources, you must configure the right datasource and transaction manager in `@SqlConfig`.
- SQL cleanup does not clean file storage, message brokers, search indices, or caches.
- In CI where multiple jobs share a DB, `TRUNCATE` can destroy another job's data.

Choose `@Sql` when fixtures are static data, the DB is isolated, or scripts have explicit scoped conditions. Use repository/API cleanup when tracking dynamically created resources.

## 10. Cleaning up via HTTP DELETE: when is it suitable?

Another strategy is **cleaning up through the public API**:

~~~text
POST /api/tasks  ->  201 + id
GET  /api/tasks/{id} -> 200
DELETE /api/tasks/{id} -> 204
GET /api/tasks/{id} -> 404
~~~

Pros:

- The test needs no direct DataSource access.
- The test exercises the real workflow and verifies deletion permissions/behavior through the API.
- Well suited for E2E tests running in a separate process or container.

Limitations:

- The API might not support hard deletion (soft delete/archive).
- DELETE may require authentication/authorization, tenant context, and CSRF/tokens.
- If POST commits yet the response times out or drops, the test may **lack the ID** to DELETE.
- If DELETE merely enqueues a job, 204/202 does not guarantee data is gone immediately.
- The DELETE API only cleans its own API aggregate; files, caches, messages, or billing side effects may linger.
- A failing test that wants to preserve records for debugging may clash with cleanup policies; resolve this via isolated test environments and bounded retention.

Therefore, **API cleanup** fits black-box tests well, whereas **repository/DB cleanup** fits when tests own the database fixture. In the example, `deleteThroughHttpCommitsAndNextGetReturns404` both tests the delete API and keeps `@AfterEach` as a title-based safety net.

### `try/finally` and preserving the original failure

When a test creates multiple resources, you might write:

~~~java
Long createdId = null;
try {
    createdId = createTaskOverHttp();
    assertTaskVisible(createdId);
} finally {
    if (createdId != null) {
        deleteTaskOverHttp(createdId);
    }
}
~~~

This snippet illustrates a resource-control pattern, not a runnable project; helpers must be defined. Weakness: if cleanup throws an exception, it can obscure the original assertion failure. In a rigorous test harness, record both primary and cleanup errors (e.g., suppressed exceptions or controlled logging) rather than silently swallowing cleanup failures.

**`@AfterEach`** can also report its own cleanup exception. Never treat "assertions passed yet cleanup failed" as success: leftover rows can break subsequent tests.

## 11. Isolated databases/schemas and Testcontainers

In large systems, deleting individual records after tests may be insufficient or overly complex. Instead, tests can run against a **dedicated database/schema** and drop it entirely after the suite or class.

### In-memory H2 as an example

- Fast, requires no Docker.
- Databases can be separated by JDBC URL name and Spring `ApplicationContext`.
- Does not necessarily match production PostgreSQL/MySQL dialects, transaction isolation, constraints, or migrations.
- With `DB_CLOSE_DELAY=-1`, an H2 database can stay alive until JVM shutdown; context caching and pools also affect lifecycle.
- `ddl-auto=create-drop` creates/drops the schema on persistence unit / context lifecycle, **not between individual test methods**.
- **Do not rely on context eviction** to assume data is clean in every scenario.

### Testcontainers PostgreSQL

When JPA/native SQL behavior depends on the database engine, run an ephemeral PostgreSQL container in tests. Spring Boot 3.3 supports `@ServiceConnection` with the Testcontainers starter, or `@DynamicPropertySource` to inject JDBC URL/user/password. Combine with `@SpringBootTest(RANDOM_PORT)` and test the API over real HTTP.

Illustrative flow:

~~~text
JUnit suite
    |
    +-- PostgreSQLContainer / dedicated test schema
    |      +-- migrations run on test DB
    |
    +-- Spring Boot embedded HTTP server RANDOM_PORT
    |      +-- TaskService @Transactional
    |      +-- DataSource -> PostgreSQL container
    |
    +-- POST/GET/DELETE over real HTTP
    |
    +-- cleanup by testRunId/resource IDs
    |
    +-- container/schema teardown when suite completes
~~~

A starter snippet for JUnit 5:

~~~java
@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PostgreSqlHttpIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired TestRestTemplate, test methods, cleanup...
}
~~~

This is **not a standalone project**: it needs Testcontainers dependencies, database schemas, entities/repositories, and application fixtures. The Boot Testcontainers classpath and container runtime must be working. Do not copy this snippet into an environment lacking a Docker/Podman-compatible runtime.

### Does one container per class guarantee clean data between methods?

**No.** If the same database/container is reused across multiple test methods, data committed by an earlier method remains. You must:

- Delete resources by test ID;
- Use a separate schema/database per test;
- Clean up with scoped SQL inside the test DB;
- Or spin up fresh containers at the right isolation boundary.

Reusing containers across JVM/test runs speeds up feedback yet can retain state and cause hard-to-reproduce bugs. If enabling Testcontainers reusable mode, define explicit cleanup rules and never use a database with sensitive data.

### Not just the database: infrastructure with other side effects

A POST can create:

- Files/objects in S3 or on local disk;
- Messages in Kafka/RabbitMQ;
- Redis cache entries;
- Search index documents;
- Emails or webhooks;
- Payment/billing transactions;
- Scheduled jobs or outbox events.

**JDBC rollback does not undo any of these side effects.** When integration tests cover end-to-end workflows, fixtures need tailored cleanup/compensation per resource, typically using dedicated test namespaces and sandbox credentials. Avoid triggering production payments or emails in tests.

## 12. Parallel tests: clean up by namespace, never wipe whole tables

A suite can be configured in JUnit/Gradle to run methods or classes in parallel. If tests share a database, any table-wide cleanup becomes a point of contention.

**Unsafe pattern on a shared database:**

~~~java
@BeforeEach
void resetEverything() {
    repository.deleteAll();
}
~~~

This method can wipe records just created by another test, causing test B to lose its data. It also risks deleting non-test data if connected to the wrong DB.

**Better pattern in a controlled test database:**

~~~java
@BeforeEach
void prepare() {
    testKey = "it-" + UUID.randomUUID();
}

@AfterEach
void clean() {
    repository.deleteByTestKey(testKey);
}
~~~

This snippet illustrates the architecture; `deleteByTestKey` must be declared/implemented and test entities must carry an appropriate marker. In the demo, `testTitle` plays a similar role. Do not add test-only fields to domain models **solely** to tag test data if it pollutes the domain; instead use dedicated test tenants/accounts, business correlation IDs, or DB/schema-level isolation.

### When can `deleteAll()`/`TRUNCATE` be used?

When you are **certain** the database/schema belongs exclusively to **one unshared test job**, table-wide resets can be simple and fast — for example, a fresh container per test class with no concurrent readers/writers. Even then, ensure:

- Verification that the environment is genuinely a test DB;
- No external traffic;
- Proper transaction/FK/sequence handling;
- No async jobs still writing after the reset;
- No unauthenticated `DELETE ALL` endpoints exposed in production environments.

A test worker lacking broad delete privileges should never bypass controls using production credentials or dangerous profiles. Better isolation comes from provisioning dedicated test DBs/schemas.

### Why clean both before **and** after tests?

- **Before test:** ensures a clean fixture if a previous run crashed before cleaning up.
- **After test:** reduces leftover junk after the suite and minimizes interference with subsequent tests.

However, "clean before" must be **safely scoped**; never delete data you do not own. With a freshly randomized marker, there are normally no pre-existing records to clean beforehand — you can start by asserting count 0 in your private namespace. Post-test cleanup remains essential; if a DB is job-scoped, suite-level schema/container teardown catches leftovers when a JVM dies mid-run.

## 13. What happens if a POST response times out after the server commits?

A very realistic failure mode:

~~~text
Client sends POST to create task
          |
          v
Server INSERT + COMMIT succeeds
          |
          v
Network drops before client reads response
          |
          v
Client receives timeout/IOException
          |
          v
DB has the task, yet test never learns the new ID
~~~

Hence, cleanup relying solely on an ID parsed from the response can **miss orphaned data** when requests fail after commit. Generating a **`testRunId` or idempotency key before sending the request** lets tests locate and clean up data even when the response is lost.

In the demo, `testTitle` is created in `@BeforeEach` prior to the HTTP POST, so cleanup can find the record by title even if the client never reads the ID. That is a key **advantage of pre-assigned cleanup keys**.

### Idempotency and retries

Clients should never blindly retry non-idempotent POST requests. If the response drops after commit, retrying can create duplicate records or hit unique constraints. Important APIs should consider `Idempotency-Key` or stored request IDs with duplicate handling.

Tests should cover:

1. Send POST with key `K`.
2. Simulate a lost/timed-out response if the test harness supports it.
3. Resend with the same key `K`.
4. Verify the API does not create duplicate records when idempotency is contracted.
5. Clean up by key/resource IDs.

This extends the commit/cleanup topic; the basic demo does not implement idempotency, so **do not claim** the example solves production retry handling.

## 14. Eventual consistency and asynchronous cleanup

If a POST API returns `202 Accepted`, writing may be handed off to a queue/worker. Or the DB transaction commits first while search indices or caches update later. In those cases:

- A GET immediately after POST may temporarily return 404 or stale state.
- Cleanup in `@AfterEach` might run **before** the async worker writes the record.
- A worker might re-create a record **after** test cleanup ran.
- A DELETE call might also merely enqueue deletion and return 202.

For async workflows, use **bounded polling** against an observable condition:

~~~text
POST -> receives jobId
    |
    v
Poll GET /jobs/{jobId} until COMPLETED or finite timeout
    |
    v
Assert final state per contract
    |
    v
DELETE/cleanup by test key
    |
    v
Poll cleanup completion if the system is eventually consistent
~~~

Never use a fixed `Thread.sleep(5000)` hoping the worker finishes: it slows tests down and turns flaky under CI load. Use Awaitility or a polling helper with timeout/backoff to wait for conditions, **never polling infinitely**.

That said, bounded polling is for **genuinely asynchronous** systems. In the demo project, the service is synchronously `@Transactional` and GET reads the primary H2 DB, so right after POST 201 the row is expected to exist immediately. Needing a sleep in the synchronous demo indicates a transaction or test setup bug.

## 15. Transaction propagation: REQUIRED, REQUIRES_NEW, and tricky cases

Spring uses transaction propagation to decide whether a method joins an active transaction or starts a new one. Notable cases in tests:

| Propagation | Common meaning | Effects to consider |
| --- | --- | --- |
| `REQUIRED` (default `@Transactional`) | Joins current thread-bound transaction if present; otherwise starts new | Test thread and server thread are still separate |
| `REQUIRES_NEW` | Suspends current transaction and starts a brand-new one | Can commit independently; watch connection pool |
| `SUPPORTS` | Joins if present; runs non-transactionally otherwise | Hard to predict rollback across callers |
| `NOT_SUPPORTED` | Runs outside transactions; suspends active one | No default rollback for separately committed operations |
| `NESTED` | Nested transaction via savepoints when supported | Does not share transactions across HTTP/network |

With `@SpringBootTest(RANDOM_PORT)`, transaction A on the test thread and transaction B on the server thread **do not share a thread-bound context**. Server-side `REQUIRED` cannot "join A" merely because A initiated an HTTP call.

### Connection pool deadlock inside test transactions

If the test thread opens a transaction holding one DB connection and then makes an HTTP call to the server, the server thread needs a **second connection**. If the pool size is **1 connection**, the server waits for a connection while the test thread waits for the HTTP response — causing a deadlock/timeout.

In the demo project, the default Hikari pool has multiple connections, and `TransactionTemplate` holds no long-locked DB writes across the HTTP call. In real applications, avoid keeping transactions open across HTTP calls unnecessarily. If testing transaction traps, isolate them into small focused tests with appropriate pool sizing rather than mistaking timeouts for rollback behavior.

### Database isolation and "GET sees the data"

A `GET` from a separate request is a helpful observation, yet results also depend on isolation levels and DataSource routing:

- Read Committed normally sees data after commit.
- An already-open transaction with an older snapshot may miss new rows depending on isolation level.
- Read replicas can lag.
- Caches can serve stale entries.
- A query inside the same JPA persistence context can read from the first-level cache rather than proving a fresh DB round-trip.

In the demo, GET issues a separate request, the service opens a new read-only transaction, and reads the H2 primary; that matches the lesson's goal.

## 16. `@DirtiesContext` is not a rollback command for external state

`@DirtiesContext` tells Spring TestContext to mark the `ApplicationContext` dirty and evict it from cache. It is useful when a test mutates **bean/context state** that cannot be safely reset. However:

- It does not send `ROLLBACK` for server transactions already committed.
- It does not delete rows in an external PostgreSQL/MySQL instance.
- It does not purge Kafka messages, S3 objects, or Redis keys.
- It does not guarantee an H2 database shares the context lifecycle if `DB_CLOSE_DELAY` or another connection keeps data alive.
- It increases suite runtime because contexts must rebuild.

**Do not slap `@DirtiesContext` onto every real-HTTP test expecting clean data.** For real isolation, use dedicated databases/schemas, scoped cleanup, or container teardown.

## 17. When is database cleanup not needed?

Not every HTTP integration test writes data. A GET test over read-only fixtures may skip cleanup if it genuinely mutates no DB, cache, or external state. Simpler cases include:

- `@WebMvcTest` mocking controller collaborators, touching no DB.
- Service unit tests with fake repositories and no Spring context.
- Read-only GET endpoints querying prebuilt fixtures with zero side effects.
- Same-thread/in-memory DB tests whose transaction rollback demonstrably covers every write.

Watch out for **hidden side effects**: access logs, audit events, counters, outboxes, cache warm-up, "last seen" timestamps, or session creation. If a test claims to be read-only while the handler updates the database, isolation/cleanup is still needed.

## 18. Protecting tests from touching the production database

Before running any test with cleanup, verify **which database is actually connected**. `@AutoConfigureTestDatabase(replace = NONE)`, test profiles, or Testcontainers configs do not automatically form a shield if credentials/URLs accidentally point to production.

Safety rules:

- Tests must use dedicated test databases/schemas/containers.
- Never use production credentials with DELETE/TRUNCATE privileges.
- Restrict CI network access to production DBs wherever possible.
- Assign clear prefixes/namespaces to test resources with TTLs or run IDs.
- Optionally assert `DatabaseMetaData.getURL()`/`getDatabaseProductName()` in integration setup per project policy; never print secrets.
- If a test performs broad cleanup, fail fast when the database is outside an allowlist of test environments.
- Never run destructive migrations against databases containing real data.
- For object stores/email/payments in tests, use isolated sandbox/test buckets and fake/sandbox credentials.

**This lesson's H2 setup is scoped inside test properties** and test-runtime H2. The project holds no production passwords, opens no external DB connections, and exposes no `DELETE ALL` endpoints.

### Checking the JDBC URL in tests when environment safety matters

Illustrative snippet:

~~~java
try (Connection connection = dataSource.getConnection()) {
    String url = connection.getMetaData().getURL();

    assertTrue(url.startsWith("jdbc:h2:mem:"));
}
~~~

This is **not a standalone test**; it requires an injected `DataSource` and imports. With Testcontainers PostgreSQL, you can assert product name `PostgreSQL` and confirm host/DB/schema belong to test infrastructure. Avoid logging URLs containing credentials or relying solely on a profile named `"test"`.

## 19. Cleanup techniques for multi-table aggregates

An order-creation API often writes across multiple tables:

~~~text
POST /orders
   |
   +-- orders
   +-- order_items
   +-- inventory_reservations
   +-- outbox_events
   +-- audit_log
~~~

If cleanup deletes only `orders`, it may leave orphaned reservations/outbox/audit rows or fail on foreign-key constraints. Map out a clear **resource graph** before picking a cleanup strategy:

1. Identify parent/child tables and foreign keys.
2. Decide on hard delete, soft delete, archiving, or compensation per contract.
3. Delete in dependency order or use designed/approved database cascades.
4. Record IDs/`testRunId` for every created resource.
5. For outboxes/messages, wait for consumers to stop or clean up within the test's namespace.
6. Ensure cleanup never triggers dangerous unintended business workflows (refunds, emails, billing).

For complex aggregates with many side effects, **dropping the schema/container** after each isolated test run is sometimes safer than maintaining dozens of manual DELETE statements — provided test infrastructure guarantees isolated namespaces and shares no production resources.

### What to watch out for with bulk JPQL DELETE

`@Modifying @Query("delete ...")` runs bulk updates/deletes directly against the DB, **without synchronizing entities already held in the JPA persistence context**. If a test holds managed entities from earlier queries, you may need `flush/clear` or a fresh transaction before asserting. The demo reads and cleans up in separate transactions without reusing a long-lived `EntityManager` across tests.

In real systems, bulk deletes also bypass ORM-level entity lifecycle callbacks and cascades compared to entity-by-entity deletion. Design cleanup queries against the actual schema rather than treating bulk delete as equivalent to application-level deletion logic.

## 20. Common failures and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Test passes alone, fails in suite | POST data from prior test committed; cleanup missing | Use unique test keys, `@AfterEach`, or DB isolation |
| `@Transactional` test still leaves rows | HTTP handler runs on server thread in its own transaction | Do not rely on test rollback; commit cleanup outside test transaction |
| `@AfterEach` runs delete yet rows remain | Cleanup ran inside test-managed transaction and rolled back | Remove `@Transactional` from real-HTTP test or use `@AfterTransaction`/ISOLATED cleanup |
| `@DirtiesContext` fails to clean PostgreSQL | Only evicts Spring context cache | Delete resources / tear down database explicitly |
| Other tests lose their data | `deleteAll()/TRUNCATE` ran on a shared DB | Scope deletes by `testRunId`/ID or isolate DBs |
| HTTP returns 201 yet DB lacks row | Async commit, read replica, open txn, wrong DB | Check transaction timing/DB routing; bounded polling if eventual |
| Client times out yet DB has record | Server committed before response dropped | Clean up by pre-generated key; consider idempotency |
| GET returns 404 right after 201 | Replica lag, wrong ID/context, async state | Check primary/replica, path, eventual consistency |
| Cleanup deadlocks/times out | Long txn holding locks, exhausted pool, running async writer | Avoid long txns around HTTP; size pool/ordering; wait for jobs |
| Cleanup leaves child records | Multi-table aggregate / side effects | Build resource cleanup graph or drop schema |
| Test rolls back yet query sees stale row | Reading JPA persistence context cache or another test's fixture | Use fresh query/clear context; verify namespace |
| `DataIntegrityViolationException` on rerun | Hardcoded unique key with leftover rows | Use unique test data, scoped cleanup, DB isolation |
| POST test 500 due to missing schema | Test DB lacks valid migrations/DDL | Initialize schema via proper migrations/test config |
| Hit production database by mistake | Profile/env URL/credentials leaked | Allowlist test DBs, fail fast, revoke prod rights |
| Cleanup via DELETE API fails | Auth/CSRF/ownership/soft-delete/async delete | Supply test credentials, assert cleanup, add safe fallback |
| Suite runs way too slow | Full context per method, repeated container restarts | Balance context caching and DB isolation; avoid blanket `@DirtiesContext` |
| MockMvc rolls back yet `RANDOM_PORT` does not | Different thread/network boundaries | Write tests at the right layer; never assume identical transaction semantics |
| `@Sql` script gets rolled back | Wrong `TransactionMode` for real-HTTP cleanup | Use `ISOLATED` or non-transactional repository cleanup |
| Row counts keep failing | Parallel tests / shared fixtures | Count by test key, never assert table-wide row counts |
| Container teardown fails | Hanging container/runtime resources | Manage lifecycle/CI cleanup independently of method hooks |

### Workflow to diagnose a "leaked" row after a test

1. Confirm whether the test used **real HTTP** or MockMvc.
2. Check where `@Transactional` sits (**test class**, **service**, **repository**, or everywhere); sketch thread/transaction boundaries.
3. Determine whether the server committed before the response or runs asynchronously.
4. Check whether the cleanup method executed and which transaction it belonged to.
5. Check whether the cleanup query used the right key, datasource, schema, and tenant.
6. Verify state after cleanup in a **fresh** transaction rather than a stale persistence context.
7. Check if concurrent tests or consumers are recreating the record.
8. Read the root cause from Gradle/Spring logs rather than "fixing" the assertion to expect 1 row.

## 21. Workflow to apply in real projects

A reviewable workflow:

**Step 1 — Lock down the testing goal.** Do you need to prove real HTTP + DB commit? For controller mapping only, prefer MVC slices; for business rules only, unit tests.

**Step 2 — Provision a safe test DB.** H2 for simple CRUD, Testcontainers PostgreSQL for engine-specific SQL/transactions; zero production credentials in the environment.

**Step 3 — Choose `RANDOM_PORT`.** Send client requests to a real server; use `TestRestTemplate`/`WebTestClient` with an appropriate base URL, never hardcoding 8080.

**Step 4 — Generate a test marker before the request.** A `testRunId`/UUID/tenant fixture lets you locate and clean up resources even if responses drop.

**Step 5 — Send request and verify contract.** Assert HTTP status/body/`Location`, then inspect commits via GET or a repository read **in a fresh transaction**.

**Step 6 — Implement proactive cleanup.** `@AfterEach` + repo delete in its own transaction, DELETE API, or schema/container isolation. Do not put `@Transactional` blindly across real-HTTP tests.

**Step 7 — Handle non-DB side effects.** Files, caches, outboxes, queues, jobs, email sandboxes; separate fakes from integration by scope.

**Step 8 — Verify repeated and parallel runs.** Run the class repeatedly, shuffle order, enable parallel execution if supported, and confirm zero state leakage.

**Step 9 — Verify cleanup failures are surfaced.** If deletion fails, the test must fail visibly rather than swallowing the error silently.

**Step 10 — Add infrastructure-level teardown.** If a JVM crashes before `@AfterEach`, CI lifecycle jobs or TTL policies still reclaim leftover DBs/containers/namespaces.

## 22. Practice exercises

**Exercise A — observe commits after HTTP:** Run `postCommitsAndAnotherHttpGetSeesTheData`. Explain why the second GET and post-response repository count prove more than merely asserting POST 201.

**Exercise B — prove rollback does not "cross HTTP":** Run `rollingBackClientThreadDoesNotUndoServerWrite`. Change the assertion from 1 to 0 to watch it fail, then revert. Diagram the two threads and two transactions.

**Exercise C — intentionally break cleanup:** On a dedicated test DB branch, temporarily remove `@AfterEach`. Re-run a test with a fixed title to observe state leakage / unique constraint failures. Restore cleanup and randomized keys afterward.

**Exercise D — `@Transactional` test method:** Create an illustrative real-HTTP test method annotated with `@Transactional` and `@AfterEach` repository delete. Verify cleanup can get rolled back with the test transaction; switch to `@AfterTransaction` or drop test-level `@Transactional`.

**Exercise E — clean up by ID instead of title:** Update the fixture to track IDs of tasks created in the test. For each ID, call DELETE or repository delete in cleanup. Analyze the case where the response drops before the test learns the ID and why a pre-generated marker is still needed.

**Exercise F — parallel check:** Write two tests, each with its own marker, and run them in parallel against the same test DB. Ensure test A's cleanup never removes test B's row; explain why `deleteAll()` fails here.

**Exercise G — production-like DB engine:** Replace H2 with Testcontainers PostgreSQL, run migrations, verify the DB product name, and check DELETE/GET behavior. Compare startup cost and container teardown strategies.

**Exercise H — eventual consistency:** Change POST to return 202 + an async worker in a test sandbox. Write bounded polling until the record appears, then wait for worker completion before cleanup. Avoid fixed sleeps to mask asynchrony.

**Exercise I — non-DB side effects:** After POST, simulate writing an outbox event and an object into a test bucket. Write scoped cleanup by run ID for both the database and event/object. Never use sandbox credentials that have production access.

**Exercise J — transaction propagation:** In the task-creation service, experiment with `REQUIRES_NEW` in a dedicated test. Observe independent commits and small connection pool risks; distinguish from test-managed rollback.

## 23. Checklist before merging DB-backed HTTP integration tests

- [ ] Have I confirmed this is **real HTTP on `RANDOM_PORT`/`DEFINED_PORT`**, not MockMvc?
- [ ] Do I know which code runs on the test thread and which runs on the server thread?
- [ ] If `@Transactional` is present on the test, am I avoiding the assumption that it rolls back server commits?
- [ ] Do I verify POST status **and** observable persistence outside the creating transaction?
- [ ] Does test data have a unique marker/ID created **before** the request when needed?
- [ ] Does cleanup delete only test-owned resources without wiping shared DBs?
- [ ] Does the cleanup hook run **outside the rolled-back transaction** and commit its own changes?
- [ ] Is cleanup still attempted when assertions fail, and are cleanup errors surfaced clearly?
- [ ] Are tests independent of method/class ordering and safe for configured parallel runs?
- [ ] Have I distinguished synchronous commits from async jobs / 202 / eventual consistency?
- [ ] If POST times out after committing, can resources still be traced and deleted?
- [ ] Are DB/test credentials isolated so production can never be touched accidentally?
- [ ] Does cleanup account for aggregates, foreign keys, outboxes, caches, and storage side effects?
- [ ] Is `@DirtiesContext` avoided as a substitute for proper database cleanup?
- [ ] Do `@Sql` scripts specify clear transaction modes, datasources, and scoped conditions?
- [ ] Do Gradle/JUnit reports confirm tests actually executed rather than returning `"UP-TO-DATE"`?
- [ ] If the JVM/CI dies, is there an infrastructure TTL/teardown mechanism for leftover resources?

## 24. Authoritative references

The following links explain Spring Boot 3.3 and Spring Framework 6.x behavior underlying the example project. When using different Boot/Spring versions, re-check Javadocs and matching semantics for your codebase.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest` with `RANDOM_PORT`/`DEFINED_PORT`, separate server/client threads and transactions, test rollback does not roll back server.
- [Spring Framework 6.1 — Transaction Management in TestContext](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/tx.html): test-managed transactions, `@Rollback`, `@BeforeTransaction`, `@AfterTransaction`, and lifecycle.
- [Spring Framework 6.1 — TransactionalTestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html): test transaction orchestration.
- [Spring Framework — SQL Scripts in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phases, and transaction modes.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): repository method transactions and setting boundaries at services.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): test containers and `@ServiceConnection`.
- [JUnit Jupiter — Lifecycle Methods](https://docs.junit.org/5.10.2/user-guide/#writing-tests-annotations): `@BeforeEach`, `@AfterEach`, and fixture lifecycle.

**Remember:** When tests send **real HTTP**, transactions committed on the **server thread** do not vanish merely because the test method has `@Transactional` and rolls back. To keep tests independent, **create explicit test keys, observe commits from a separate request/transaction, run cleanup in a committed transaction, and delete only your own resources**. For complex systems, combine dedicated DBs/schemas/containers with teardown hooks to handle abrupt test terminations as well.