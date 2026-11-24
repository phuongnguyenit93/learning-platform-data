# Choosing Optimal Scope While Preserving Independence and Bug-Detection Capability

A Spring Boot test suite can run slowly because every class starts a new `ApplicationContext`, yet forcing every test into a Mockito unit test can miss bugs in dependency injection, transactions, serialization, `SecurityFilterChain`, or JPA mappings. Another team optimizes by sharing both `ApplicationContext` and mutable singleton/DB state across tests: the suite runs fast in one lucky order, then fails randomly when run individually, in parallel, or reordered. Neither extreme meets quality standards.

The knowledge lesson **“Choosing Optimal Scope While Preserving Independence and Bug-Detection Capability”** belongs to the **Context cache and performance** section of **Spring Boot – testing**. Its guiding principle is:

> Pick the **narrowest test scope that still fails when the important bug we need to catch occurs**, then share **stable Spring context configurations**—never sharing **mutable business state** between tests.

This lesson explains the differences between **test breadth** (unit → slice → full context → real HTTP), **TestContext cache reuse**, and **data/side-effect isolation**. It then presents a hands-on project in **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit Jupiter 5, Mockito, MockMvc, Spring Data JPA, and H2** demonstrating the same book stock reservation flow across five test layers. The lab also shows how a full-context test with `@Transactional` can still mask a missing `@Transactional` on the service, and how a real HTTP test closes that gap.

**Scope commitment:** Sample code was reviewed against Spring Boot 3.5/Spring Framework 6.2 APIs. Any timings, cache hits, Gradle results, or failure rates appearing in examples are explicitly noted as **illustrative/expected**, not measurements taken in the learner's repository.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish **single-test-method speed** from **total suite duration**, and context reuse from data independence.
- Choose among plain JUnit/Mockito, `ApplicationContextRunner`, `@JsonTest`, `@WebMvcTest`, `@RestClientTest`, `@DataJpaTest`, `@SpringBootTest(MOCK)`, and `@SpringBootTest(RANDOM_PORT)`.
- Formulate a **bug hypothesis** before picking a test scope, avoiding "fastest wins" as the sole criterion.
- Understand that the TestContext cache uses a **context configuration key**, defaults to **max 32 contexts**, evicts via LRU, and stores static state inside a single JVM process.
- Recognize that `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@MockitoBean`, and test configurations can fragment the cache.
- Know when `@DirtiesContext` is right and when it hides an easier cleanup problem.
- Write order-independent tests that avoid leaking data, clock, cache, or Mockito state.
- Understand default rollback in `@DataJpaTest` and why `RANDOM_PORT` is not rolled back by the test thread's transaction.
- Know what `@WebMvcTest` **does not** load, what `@DataJpaTest` **does not** test, and why some full-integration cases remain necessary.
- Test business services with mocked repositories, repositories with an embedded database, controllers with mocked services, and end-to-end wiring with a real DB in context.
- Measure context load counts, cache hits/misses, and test timings with evidence rather than guessing.
- Identify the balance between bug detection, feedback time, reproducibility, and CI cost.
- Present reports explicitly stating which bug classes each test **detects** and **does not detect**.

## 2. Three axes to optimize simultaneously

| Axis | Question | If optimized poorly |
|---|---|---|
| **Scope / fidelity** | Which layers, proxies, filters, serializers, and repositories are real? | Over-mocking lets wiring/transaction/security bugs slip through |
| **Independence / isolation** | Can every test run alone, reordered, or in parallel and stay accurate? | Flaky suite, leftover rows, static/singleton leaks |
| **Performance / feedback** | How much time goes to context startups, Docker/DB, and test execution? | Slow CI waits, delayed feedback, developers skip running the suite |

There is no single "optimal" annotation for all tests. A fast `@WebMvcTest` that overlooks a service transaction is **not a solution** when protecting transactions is the goal. A full `@SpringBootTest` where every class declares a different `@MockBean`/property **fails to leverage the cache well**.

### 2.1. Mental formula for suite duration

```text
T_total (approx)
  = sum of startup costs for context keys that actually must load
  + sum of test method execution times
  + startup/wait times for DBs, containers, and external dependencies
  + JVM fork, build/test discovery, and instrumentation overhead
  + contention/retry overhead under parallel execution.

Context caching reduces the startup portion when the same cache key is reused;
it does not clean the database or reset mocks as expected on its own.
```

More test methods does not mean contexts scale proportionally. One hundred methods sharing **one key** can reuse one context; ten test classes with ten differing bean override sets can spawn ten contexts. Still, do not treat 1 or 10 as a guarantee because environment, cache eviction, and JVM forks affect the outcome.

## 3. "Smallest" must be defined by bug type

Ask before choosing an annotation:

1. If a **calculation** is broken, will a test fail?
2. If `@Transactional` is removed from a service, will a test fail?
3. If a controller has the wrong path, query parameter, JSON field, or HTTP error mapping, will a test fail?
4. If a JPA column name changes or a query is wrong, will a test fail?
5. If the application is missing a bean, has a bad profile/property, or has two colliding beans of the same type, will a test fail?
6. If `SecurityFilterChain` specifies the wrong role, does the test execute real filters?
7. If a request travels over TCP and the transaction runs on a **server thread**, does the test observe the commit?
8. If the real database handles SQL differently from H2, will an H2 test catch it?
9. If a background worker/queue writes outside the transaction, does test-thread rollback clean up the side effect?

A narrow test is only good when the **failure mode to guard against sits inside that scope**. When the bug hypothesis falls outside, step up one level or add a targeted test—without elevating the entire suite to full context.

## 4. Scope classification and bug detection

| Test type | Breadth | Proves well | Does not prove on its own |
|---|---|---|---|
| **Plain JUnit / Mockito** | Java objects + mocks | Rules, branches, call counts, no false side effects | Spring proxies, transactions, MVC, DB |
| `ApplicationContextRunner` | Small per-case config | Auto-config class/bean/property conditions | Full app scanning and HTTP |
| `@JsonTest` | JSON serializers/mappers | Format, custom Jackson config in slice | Controller, database, security |
| `@WebMvcTest` | MVC controllers/filter subset | Routing, validation, JSON, advice, selected security | Service transactions/real repositories |
| `@RestClientTest` | HTTP client bean + mock request factory | Outbound request/headers/status mapping | TCP timeouts, real network pools |
| `@DataJpaTest` | JPA entities/repositories/embedded DB | Mapping, queries, constraints, dirty checking | App MVC/service AOP (unless imported) |
| `@SpringBootTest + @AutoConfigureMockMvc` | Near-full app, mock servlet transport | Controller→Service→JPA wiring, filter chain, transactions | TCP/server threads/real proxy network |
| `@SpringBootTest(RANDOM_PORT)` | Full app + real embedded HTTP | TCP, committed effects, cookies/filters | Production cluster/cloud if still using H2/mocks |
| Testcontainers + real DB | App/repo + real dependency | SQL dialect, migrations, isolation | Entire production infra |
| Production-like E2E | Multi-service realistic topology | End-to-end journeys and system dependencies | Every small edge case (high cost) |

**No test type is automatically "better" than another.** An optimal mix is required: many small tests, enough slice tests to catch per-layer Spring integration bugs, and a small set of full-flow tests verifying cross-layer assumptions.

## 5. Examples of two bugs slipping past slices

**Bug A — service missing transaction:** `@WebMvcTest` mocks `ReservationService` to return HTTP 200 JSON; no JPA dirty checking executes, so it cannot tell if `@Transactional` was deleted.

**Bug B — broken repository query:** a Mockito unit test always returns `Optional.of(book)`, even if `findByTitleIgnoreCase` actually targets the wrong property or lacks case-insensitivity. Only a JPA repository test or real DB test catches it.

Conversely, to test that `quantity=-1` is rejected by the service **before calling the repository**, starting H2/MVC is unnecessary. Plain JUnit/Mockito is the exact right scope.

## 6. Counter-example: a full context can still give weak signal

A test:

```java
@SpringBootTest
class WeakTest {
    @Test
    void contextStarts() {
        // Asserts no business behavior.
    }
}
```

boots the whole app yet only proves "the current context loads". It **does not** protect 401/403, JSON contracts, repository queries, or rollbacks. A good test needs assertions matching the bug hypothesis, not just a "big" annotation.

A full-context test that uses `@MockitoBean` to replace the very service carrying `@Transactional` also **does not test that service's transaction**. Similarly, mocking a payment adapter makes tests fast without proving the real HTTP client/TLS/retries. Document clearly where mocks sit.

## 7. Context cache: the big gap between test scope and test speed

Spring TestContext Framework caches `ApplicationContext` by a **context configuration key**. When another test requests the same key in the **same JVM test process** and the context has not been evicted, Spring returns the exact same `ApplicationContext` object instead of reloading. This skips the heaviest part of Spring integration tests: bean initialization, Hibernate metamodel, embedded servers, filters, auto-config, and clients.

**The cache defaults to max 32 contexts**, using a least-recently-used (LRU) policy. 32 is the **default max**, not a guarantee the cache always holds 32 entries. Configurable via:

```text
-Dspring.test.context.cache.maxSize=64
```

This parameter is a **test JVM system property** or `SpringProperties` setting, not a magic annotation that speeds up any suite instantly. Raising `maxSize` when each context consumes heavy memory can cause GC thrashing or OutOfMemory errors in CI. First measure fragmentation and eliminate needless variants before adjusting size.

### 7.1. What belongs to the cache key?

Per Spring Framework 6.2 TestContext docs, the cache key depends on metadata including:

- `locations`, `classes` from `@ContextConfiguration`.
- `contextInitializerClasses`, `contextLoader`.
- `contextCustomizers` (including bean overrides such as `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, `@DynamicPropertySource` methods, and Spring Boot customizations).
- `contextParent` for context hierarchies.
- `activeProfiles` from `@ActiveProfiles`.
- `propertySourceDescriptors`/`propertySourceProperties` from test properties.
- `resourceBasePath` for web contexts.

**Important:** Two classes with identical code where one adds a `@MockitoBean` or different property will have **different keys**. Two tests in the same class naturally share a key unless dynamic configuration or lifecycle changes alter behavior.

## 8. Why can `@MockitoBean` field names fragment the cache?

In Spring Framework 6.2, bean overrides use qualifiers to identify targets. Without `@Qualifier`, the **field name** acts as a fallback qualifier. Thus:

```java
// Test A:
@MockitoBean
PaymentGateway paymentGateway;

// Test B (same type, different name):
@MockitoBean
PaymentGateway gateway;
```

These are snippets assuming type `PaymentGateway`, not demo files. When field names serve as qualifiers, they can force the framework to create separate `ApplicationContext`s; official docs recommend consistent naming when mocking the same bean across test classes.

**Do not rename fields blindly** when multiple candidates exist in the app; in that case, an explicit qualifier is needed to mock the right bean. And **do not mock extra beans needlessly just to "align" annotations**, because doing so hides more real logic. Standardize only **genuinely needed** mocks across classes sharing a test scope.

### 8.1. `@MockitoBean` can create a new bean

By default `@MockitoBean` uses the **REPLACE_OR_CREATE** strategy: if no target bean exists, the framework creates a fresh mock. In `@WebMvcTest`, that is normal because services sit outside the slice. Yet if a **full integration test** must guarantee the production bean actually exists, use `@MockitoBean(enforceOverride=true)` where appropriate to fail if the target bean is missing—or better yet, **do not mock the bean whose wiring you want to test**.

Notably, a mock replaces a proxied bean with a fake object, stripping away the original bean's AOP advisors (transactions/caching/method security). A test that mocks a service **never verifies real transactional/security proxies**.

## 9. Small changes that break cache reuse

| Difference between test classes | Possible cache impact | Should you standardize? |
|---|---|---|
| `@ActiveProfiles("test")` vs. `("local")` | Different key | Yes if no differing semantics needed |
| `@TestPropertySource(properties="feature=true")` vs. false | Different key | Only unify if truly the same scenario |
| `@MockitoBean A` vs. `@MockitoBean A,B` | Different key | Never add B if B is under test |
| Different mock field qualifier/name | Can produce different key | Name consistently when targeting same bean |
| Different `@DynamicPropertySource` method | Can produce different key | Consolidate stable config when reasonable |
| Different `@Import(TestConfig.class)` | Different key | Share minimal fixture when suitable |
| `@SpringBootTest(MOCK)` vs. `RANDOM_PORT` | Different key | Do not unify—different transport |
| `@WebMvcTest` vs. full context | Different key, different nature | Do not force together |
| `@DirtiesContext` | Evict + close context | Use rarely, when truly needed |
| Separate JVM fork | Cache not shared | Build strategy decision |

**Never sacrifice bug detection to boost cache hits.** For instance, dropping a `feature=false` test just because its key differs eliminates negative-branch coverage. Fewer contexts is **not** a quality KPI if coverage drops.

## 10. Caching does not mean context state is clean

An `ApplicationContext` typically holds **singleton beans** and JVM caches/pools. When a context is reused:

- An `AtomicInteger` inside a singleton retains call counts from prior tests.
- A `ConcurrentHashMap` caching bean keeps entries inserted by another test.
- A mutable/test `Clock` advances and stays unreset.
- Custom `SecurityContextHolder` `ThreadLocal` values can linger if cleanup is buggy.
- `@Scheduled` jobs can keep firing on background threads.
- HTTP client pools and retry/circuit-breaker states remain open.
- An in-memory database tied to the context retains committed rows.
- A Testcontainers container retains tables, queues, or object data.
- Static fields live **outside** the Spring context and are not reset by `@DirtiesContext` by default.

Hence the rule:

**Reuse the expensive-to-initialize object graph; reset or roll back every piece of state that can affect test outcomes.** If you do not know whether a bean holds state, investigate the code instead of reflexively adding `@DirtiesContext` to avoid understanding it.

## 11. `@DirtiesContext`: when should it be used?

`@DirtiesContext` signals that the context has been altered in a way making reuse unsafe. Spring removes it from the cache and closes it. Legitimate cases:

- A test alters **bean definitions**, programmatically registering or removing beans.
- A test mutates infrastructure config that cannot be reverted via supported APIs.
- A test corrupts global context state where safe reset is impractical.
- A test uses a container/service whose lifecycle renders the context unusable afterward.

**Illustrative example**, not part of the runnable project:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatesUnresettableBeanGraphTest {
    // Test genuinely mutates context configuration.
}
```

**Never** slap `@DirtiesContext` onto every `@SpringBootTest` just because a repository has leftover rows. Whenever DB rollback, scoped deletion, in-memory cache clearing, or clock/mock reset works, do that to preserve cache reuse. When using `@ContextHierarchy`, understand `hierarchyMode` because eviction can cascade across multiple child contexts.

## 12. Independent tests do not mean every test loads a new context

An independent test satisfies these properties:

1. **Passes alone** when launched from an IDE.
2. **Passes reordered** with any other test.
3. **Repeats** N times on the same environment without accumulating interfering data.
4. **Runs in parallel** without fighting over global fixtures if the suite allows parallelism.
5. Created data, sent messages, cache entries, files, and queue messages have explicit cleanup.
6. Mock interactions do not bleed over from earlier tests.
7. Does not rely on a fresh context to reset state when context caching is enabled.

It **does not** require spawning a fresh `ApplicationContext` per method. `@DataJpaTest` uses transaction rollback for data independence while many methods reuse one JPA context. `@WebMvcTest` reuses the controller slice with `@MockitoBean` while Mockito resets mocks between methods per the test framework lifecycle.

## 13. DB isolation: transaction rollback has limits

In Spring/JUnit:

- `@DataJpaTest` is transactional by default and **rolls back** at the end of every test method.
- `@SpringBootTest` does not make tests transactional automatically; add `@Transactional` to the test if the goal is rolling back data within the same test-managed transaction.
- `@SpringBootTest + @AutoConfigureMockMvc` invokes the controller via a mock servlet, normally on the same test thread, so `@Transactional(REQUIRED)` on the service joins the test transaction.
- `@SpringBootTest(RANDOM_PORT)` starts a real server: the HTTP client and server run on **different threads/transactions**, so test-thread rollback **does not roll back server commits**.
- `@Async`/scheduled jobs/new threads and calls to external brokers/filesystems sit outside the test transaction's rollback.
- `@Transactional(propagation=REQUIRES_NEW)` or code opening manual transactions commits independently depending on execution flow.

**Especially important:** Running only a full-context MockMvc test with class-level `@Transactional` can **mask a missing `@Transactional` on the service**, because the test transaction wraps JPA updates from the outside. That is why this demo adds a real HTTP integration test **without `@Transactional` on the test class**, asserting DB state after the request. A client-to-server test across separate threads exercises transaction boundaries much closer to production.

## 14. Isolating Redis, Kafka, filesystems, and Clock

JPA rollback **does not revert**:

- Published Kafka messages.
- Redis keys/cache TTLs.
- Multipart temp files/object storage objects.
- Outbound HTTP requests.
- Scheduled jobs running on background threads.
- Mutated system properties and static singletons.
- Unreset in-memory queues/caches.

Boundary-appropriate solutions: separate test topics/consumer groups, UUID-prefixed Redis keys, `@TempDir`, fake SMTP, per-test object prefixes, disabling/controlling schedulers and `Clock`, and explicit `@AfterEach` cleanup. If a test emits an event consumed after the test ends, await bounded completion before cleaning up or isolate the environment. Never treat `@DirtiesContext` as a distributed transaction across all dependencies.

### 14.1. Mutable Clock and static fixtures

A `Clock.fixed` bean is safe to reuse because it is immutable. A `MutableClock` singleton can be advanced by test A to tomorrow, making test B think tokens expired. Safe approaches: pass a dedicated `Clock` directly to domain objects in pure unit tests; if injecting a mutable `Clock` into a Spring context, reset it in each test's lifecycle and ensure no scheduled/background consumer reads it concurrently.

## 15. Guiding path from bug hypothesis to annotation

```text
Where does the target bug live?
  |
  +-- Pure domain rule?
  |      -> Plain JUnit, mocking only ports needing isolation
  |
  +-- Auto-configuration / bean conditionals?
  |      -> ApplicationContextRunner
  |
  +-- JSON module / date formatting?
  |      -> @JsonTest
  |
  +-- Controller path / JSON / advice / security filters?
  |      -> @WebMvcTest + MockMvc + real SecurityFilterChain
  |
  +-- Repository query / JPA mapping?
  |      -> @DataJpaTest + matching DB (H2 or Testcontainers)
  |
  +-- Outbound HTTP client status/headers?
  |      -> @RestClientTest + MockRestServiceServer
  |
  +-- Cross-layer wiring / @Transactional / AOP / DB state?
  |      -> @SpringBootTest + MockMvc, mindful of test transactions
  |
  +-- Real inbound HTTP / server-side commits?
  |      -> @SpringBootTest(RANDOM_PORT)
  |
  +-- Real DB dialect / distributed IO / infra?
         -> Testcontainers/external integration test
```

**Minimum escalation path:** If a bug involves JSON mapping, do not immediately spin up a Postgres container. If a bug involves a transaction boundary, do not mock the transactional service with Mockito. Pick scope by *where the bug can exist*, not by generic feature names.

## 16. Runnable project: book stock reservation domain

The sample app stores a `books` table with:

- `id`: book identifier.
- `title`: book title to verify a case-insensitive repository query.
- `priceCents`: integer price in cents, avoiding floating point.
- `stock`: remaining copies available to reserve.
- `version`: JPA optimistic locking field (not a substitute for full concurrency testing).

HTTP API:

- `GET /api/books/{id}` → `BookView` and current stock.
- `POST /api/books/{id}/reserve` accepting `{"quantity":2}`.
- Quantity outside 1–10 → HTTP 400.
- Non-existent ID → HTTP 404.
- Insufficient stock → HTTP 409, **without reducing stock**.
- Valid → HTTP 200 and `ReservationReceipt` with updated remaining stock.

**One workflow, five test layers:**

1. `ReservationServiceTest` — plain JUnit + mock repository.
2. `BookRepositoryTest` — `@DataJpaTest` with embedded H2.
3. `ReservationControllerMvcTest` — `@WebMvcTest` with mocked service.
4. `ReservationFlowMockMvcTest` — full context + MockMvc + H2 + test transaction rollback.
5. `ReservationRealHttpTest` — full context + real HTTP, **no test transaction**, verifying server commit.

The demo uses H2 to teach boundaries; it does not guarantee identical semantics to Postgres/MySQL in production. Concurrent updates, unique constraints, distributed locks, migrations, and security require dedicated tests on appropriate infrastructure.

## 17. Project directory tree

```text
test-scope-context-cache/
  settings.gradle
  build.gradle
  src/main/java/com/example/testscope/
    TestScopeApplication.java
    Book.java
    BookRepository.java
    ReserveRequest.java
    BookView.java
    ReservationReceipt.java
    InvalidQuantityException.java
    BookNotFoundException.java
    InsufficientStockException.java
    ReservationService.java
    ReservationController.java
    ReservationAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/testscope/
    ReservationServiceTest.java
    BookRepositoryTest.java
    ReservationControllerMvcTest.java
    ReservationFlowMockMvcTest.java
    ReservationRealHttpTest.java
```

The project needs only Java 17+, Gradle 8.x compatible with Spring Boot 3.5.16, and Maven Central for dependencies. No Docker required; the embedded H2 datasource runs in the test JVM. `application.properties` under `src/test/resources` applies only to test runs, not production DB configuration.

## 18. Minimal Gradle configuration

**`settings.gradle`**

```groovy
rootProject.name = 'test-scope-context-cache'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
```

**`src/test/resources/application.properties`**

```properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.datasource.generate-unique-name=true
spring.jpa.open-in-view=false
```

`spring.datasource.generate-unique-name=true` prevents two Spring contexts from accidentally sharing the same H2 in-memory database name. `create-drop` is for demos/tests—**never use it in production with real data**. H2 has `runtimeOnly` scope in the demo so `bootRun` also has a datasource if learners launch the app; when shipping an application, configure environment-appropriate databases.

If the project lacks a Gradle wrapper yet, generate it first; these two Gradle files **do not create `gradlew` automatically**. The test runner uses `useJUnitPlatform()` to discover Jupiter tests.

## 19. Spring Boot application

**`src/main/java/com/example/testscope/TestScopeApplication.java`**

```java
package com.example.testscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestScopeApplication.class, args);
    }
}
```

A single `@SpringBootApplication` gives test slices and full contexts a clear application root. `@WebMvcTest` does not load services or repositories even though it finds `@SpringBootApplication`; it applies type-exclude filters and MVC-specific auto-configuration. `@DataJpaTest` similarly loads only JPA-related components.

## 20. JPA entity and optimistic locking

**`src/main/java/com/example/testscope/Book.java`**

```java
package com.example.testscope;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @Column(length = 100)
    private String id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private long priceCents;

    @Column(nullable = false)
    private int stock;

    @Version
    private Long version;

    protected Book() {
        // JPA constructor
    }

    public Book(
            String id, String title,
            long priceCents, int stock) {

        if (id == null || id.isBlank()
                || title == null || title.isBlank()
                || priceCents < 0 || stock < 0) {
            throw new IllegalArgumentException(
                    "Invalid book fields");
        }

        this.id = id;
        this.title = title;
        this.priceCents = priceCents;
        this.stock = stock;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public int getStock() {
        return stock;
    }

    public void reserve(int quantity) {
        if (quantity < 1 || quantity > 10) {
            throw new InvalidQuantityException();
        }
        if (stock < quantity) {
            throw new InsufficientStockException();
        }
        stock -= quantity;
    }
}
```

`@Version` lets JPA detect stale writes on the same entity version during flush/commit, yet **does not automatically guarantee all concurrent reservations succeed**. If production requires high-concurrency safety, test two real concurrent transactions and define how optimistic-lock exceptions are mapped or retried. The demo omits a concurrency stress test.

## 21. Repository and DTOs

**`src/main/java/com/example/testscope/BookRepository.java`**

```java
package com.example.testscope;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<Book, String> {

    Optional<Book> findByTitleIgnoreCase(String title);
}
```

**`src/main/java/com/example/testscope/ReserveRequest.java`**

```java
package com.example.testscope;

public record ReserveRequest(int quantity) {
}
```

**`src/main/java/com/example/testscope/BookView.java`**

```java
package com.example.testscope;

public record BookView(
        String id,
        String title,
        long priceCents,
        int available) {
}
```

**`src/main/java/com/example/testscope/ReservationReceipt.java`**

```java
package com.example.testscope;

public record ReservationReceipt(
        String bookId,
        int reserved,
        int remaining) {
}
```

Using Java records keeps JSON field names consistent. `@WebMvcTest` checks JSON field names; `@DataJpaTest` checks the repository query. A unit test mocking `BookRepository` cannot verify whether `findByTitleIgnoreCase` works on H2 or a production database.

## 22. Domain exceptions and service

**`src/main/java/com/example/testscope/InvalidQuantityException.java`**

```java
package com.example.testscope;

public class InvalidQuantityException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/BookNotFoundException.java`**

```java
package com.example.testscope;

public class BookNotFoundException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/InsufficientStockException.java`**

```java
package com.example.testscope;

public class InsufficientStockException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testscope/ReservationService.java`**

```java
package com.example.testscope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {

    private final BookRepository repository;

    public ReservationService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BookView read(String id) {
        Book book = repository.findById(id)
                .orElseThrow(BookNotFoundException::new);
        return new BookView(
                book.getId(),
                book.getTitle(),
                book.getPriceCents(),
                book.getStock());
    }

    @Transactional
    public ReservationReceipt reserve(
            String id, int quantity) {

        if (quantity < 1 || quantity > 10) {
            throw new InvalidQuantityException();
        }

        Book book = repository.findById(id)
                .orElseThrow(BookNotFoundException::new);

        book.reserve(quantity);

        // No explicit save() needed for a managed entity
        // under JPA dirty checking in the active transaction.
        return new ReservationReceipt(
                book.getId(), quantity, book.getStock());
    }
}
```

**Behaviors to protect:**

- Invalid quantity → throws before touching repository.
- Unknown ID → `BookNotFoundException`.
- Insufficient stock → does not alter `stock`.
- Valid → `book` entity is managed inside the service transaction, `reserve` runs, and JPA dirty checking flushes/commits.
- `readOnly=true` optimizes the read path; do not treat it as access-control protection.

**Why test scope matters here:** If `@Transactional` is removed from `reserve`, a unit test instantiating the service with a mock repository still sees `book.stock` decrement, and a full-context MockMvc test wrapped in **test `@Transactional`** still has an active outer transaction. Yet a real HTTP test does not wrap the server thread in the test transaction; without the service transaction, managed entity lifecycles diverge and the DB update fails to commit. A socket-based test asserting DB state after the request catches this bug under the demo's behavior.

## 23. HTTP controller and error advice

**`src/main/java/com/example/testscope/ReservationController.java`**

```java
package com.example.testscope;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class ReservationController {

    private final ReservationService service;

    public ReservationController(ReservationService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookView read(@PathVariable String id) {
        return service.read(id);
    }

    @PostMapping(
            path = "/{id}/reserve",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ReservationReceipt reserve(
            @PathVariable String id,
            @RequestBody ReserveRequest request) {

        return service.reserve(id, request.quantity());
    }
}
```

**`src/main/java/com/example/testscope/ReservationAdvice.java`**

```java
package com.example.testscope;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ReservationAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ErrorBody> invalidQuantity() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_QUANTITY"));
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ErrorBody> missingBook() {
        return ResponseEntity.status(404)
                .body(new ErrorBody("BOOK_NOT_FOUND"));
    }

    @ExceptionHandler(InsufficientStockException.class)
    public ResponseEntity<ErrorBody> insufficientStock() {
        return ResponseEntity.status(409)
                .body(new ErrorBody("INSUFFICIENT_STOCK"));
    }
}
```

This HTTP code omits authentication/Spring Security to keep the demo focused on context caching. In apps requiring authorization, `@WebMvcTest` with the real filter chain imported/scanned and full-context security tests are mandatory. Never cite the demo endpoint returning 200 as evidence of a real app's security policy.

## 24. Unit test: fast, independent, no Spring startup

**`src/test/java/com/example/testscope/ReservationServiceTest.java`**

```java
package com.example.testscope;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReservationServiceTest {

    @Mock
    BookRepository repository;

    ReservationService service;

    @BeforeEach
    void setup() {
        service = new ReservationService(repository);
    }

    @Test
    void reserveDecrementsEntityInMemory() {
        Book book = new Book("b1", "Domain", 1500, 5);
        when(repository.findById("b1"))
                .thenReturn(Optional.of(book));

        ReservationReceipt result = service.reserve("b1", 2);

        assertEquals(2, result.reserved());
        assertEquals(3, result.remaining());
        assertEquals(3, book.getStock());
        verify(repository).findById("b1");
    }

    @Test
    void badQuantityFailsBeforeRepositoryCall() {
        assertThrows(InvalidQuantityException.class,
                () -> service.reserve("b1", 0));

        verifyNoInteractions(repository);
    }

    @Test
    void missingBookThrowsDomainError() {
        when(repository.findById("missing"))
                .thenReturn(Optional.empty());

        assertThrows(BookNotFoundException.class,
                () -> service.reserve("missing", 1));
    }

    @Test
    void insufficientStockDoesNotMutateEntity() {
        Book book = new Book("b2", "Domain", 1500, 2);
        when(repository.findById("b2"))
                .thenReturn(Optional.of(book));

        assertThrows(InsufficientStockException.class,
                () -> service.reserve("b2", 3));

        assertEquals(2, book.getStock());
    }

    @Test
    void readMapsDomainObjectWithoutMutation() {
        Book book = new Book("b3", "Testing", 2400, 6);
        when(repository.findById("b3"))
                .thenReturn(Optional.of(book));

        BookView view = service.read("b3");

        assertEquals("Testing", view.title());
        assertEquals(2400, view.priceCents());
        assertEquals(6, view.available());
    }
}
```

There are **5 test methods**. They cleanly catch broken quantity branches, DTO mappings, or stock math without Spring, H2, or HTTP. However, `@Transactional` and JPA dirty checking **do not run** on `new ReservationService(repository)` — only annotation metadata exists, with no Spring AOP proxy created. Never report this test as proof of DB commits.

## 25. Repository slice: `@DataJpaTest` and rollback

**`src/test/java/com/example/testscope/BookRepositoryTest.java`**

```java
package com.example.testscope;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    BookRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void derivedIgnoreCaseQueryMatchesTitle() {
        repository.saveAndFlush(
                new Book("jpa-b1", "Spring Boot", 3200, 8));

        assertTrue(repository.findByTitleIgnoreCase(
                "sPrInG bOoT").isPresent());
    }

    @Test
    void managedEntityDirtyCheckingPersistsAfterFlush() {
        Book book = repository.saveAndFlush(
                new Book("jpa-b2", "JPA", 2000, 5));

        book.reserve(2);
        entityManager.flush();
        entityManager.clear();

        Book reloaded = repository.findById("jpa-b2")
                .orElseThrow();

        assertEquals(3, reloaded.getStock());
    }
}
```

There are **2 methods**. `@DataJpaTest` is transactional by default; each method rolls back, so sharing the context leaves neither `jpa-b1` nor `jpa-b2` behind for the next test. The second test calls `flush`/`clear` so the assertion does not merely inspect the managed entity in the first-level cache without proving the SQL update ran.

**H2 limitation:** It checks Spring Data derived queries and JPA mappings on H2. If production uses PostgreSQL-specific SQL/locks/constraints, `@DataJpaTest` or full-context integration with **PostgreSQL Testcontainers**, real migrations, and scoped data is required. Never turn "H2 passed" into "every DB passes".

## 26. Controller slice: `@WebMvcTest` keeps only the MVC boundary

**`src/test/java/com/example/testscope/ReservationControllerMvcTest.java`**

```java
package com.example.testscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReservationController.class)
@Import(ReservationAdvice.class)
class ReservationControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ReservationService reservationService;

    @Test
    void successfulReservationHasCorrectHttpJson()
            throws Exception {

        when(reservationService.reserve("b1", 2))
                .thenReturn(new ReservationReceipt("b1", 2, 3));

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":2}"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.bookId").value("b1"),
                        jsonPath("$.reserved").value(2),
                        jsonPath("$.remaining").value(3));

        verify(reservationService).reserve("b1", 2);
    }

    @Test
    void invalidQuantityMapsTo400() throws Exception {
        when(reservationService.reserve("b1", 0))
                .thenThrow(new InvalidQuantityException());

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":0}"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_QUANTITY"));
    }

    @Test
    void missingBookMapsTo404() throws Exception {
        when(reservationService.read("no-book"))
                .thenThrow(new BookNotFoundException());

        mvc.perform(get("/api/books/no-book"))
                .andExpectAll(
                        status().isNotFound(),
                        jsonPath("$.code").value("BOOK_NOT_FOUND"));
    }

    @Test
    void insufficientStockMapsTo409() throws Exception {
        when(reservationService.reserve("b1", 9))
                .thenThrow(new InsufficientStockException());

        mvc.perform(post("/api/books/b1/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":9}"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("INSUFFICIENT_STOCK"));
    }

    @Test
    void getMappingSerializesBookView() throws Exception {
        when(reservationService.read("b1"))
                .thenReturn(new BookView(
                        "b1", "Spring", 3000, 5));

        mvc.perform(get("/api/books/b1"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Spring"),
                        jsonPath("$.priceCents").value(3000),
                        jsonPath("$.available").value(5));
    }
}
```

**There are 5 methods.** They catch broken routes/HTTP methods, JSON record fields, and advice mappings. However, `@MockitoBean ReservationService` replaces the real service, so:

- `ReservationService.reserve` does not run.
- `@Transactional` proxy does not run.
- JPA queries, flushes, and optimistic locks do not run.
- DB rollback is not proved.
- Real HTTP sockets are not exercised.

**A dangerous signal:** If someone deletes the quantity-validation code in the service, `invalidQuantityMapsTo400` still passes because **the mock is programmed to throw the exception**. `ReservationServiceTest.badQuantityFailsBeforeRepositoryCall` catches the service branch, while full-flow tests verify wiring.

## 27. Full-context MockMvc: controller → service → JPA

**`src/test/java/com/example/testscope/ReservationFlowMockMvcTest.java`**

```java
package com.example.testscope;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ReservationFlowMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    BookRepository repository;

    @Autowired
    EntityManager entityManager;

    @BeforeEach
    void seedBook() {
        repository.saveAndFlush(
                new Book("mvc-book", "Context", 2500, 5));
    }

    @Test
    void successfulPostUpdatesRealJpaState()
            throws Exception {

        mvc.perform(post("/api/books/mvc-book/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":2}"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.remaining").value(3));

        entityManager.flush();
        entityManager.clear();

        assertEquals(3,
                repository.findById("mvc-book")
                        .orElseThrow().getStock());
    }

    @Test
    void forbiddenByBusinessRuleDoesNotReduceStock()
            throws Exception {

        mvc.perform(post("/api/books/mvc-book/reserve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":7}"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("INSUFFICIENT_STOCK"));

        entityManager.flush();
        entityManager.clear();

        assertEquals(5,
                repository.findById("mvc-book")
                        .orElseThrow().getStock());
    }

    @Test
    void getReadsPersistedBookThroughAllLayers()
            throws Exception {

        mvc.perform(get("/api/books/mvc-book"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Context"),
                        jsonPath("$.available").value(5));
    }
}
```

**There are 3 methods.** Spring loads the full application context, controller/service/repository are **all real**, and MockMvc uses no TCP. The test class carries `@Transactional`; each method and `@BeforeEach` run inside a test-managed transaction that rolls back at the end of each test. This is a **cheap isolation strategy** for DB operations in mock-servlet tests, allowing context cache reuse.

**Bug-detection warning:** If `@Transactional` is removed from the service, this test still receives a transaction from the **test class**. The entity can stay managed and dirty checking still flushes; the test can pass even though production would break. To guard the service-created transaction on the server thread, `ReservationRealHttpTest` below **omits `@Transactional` on the test class**.

### 27.1. Do not confuse test transaction rollback with "service does not commit"

Rolling back the test transaction at the end does not mean the application returned an error. Under same-thread MockMvc, operations share a transaction with read-your-writes semantics. If production requires committing before publishing an event or before a second request arrives, test outside a test-managed transaction or use an appropriate real HTTP/integration context.

## 28. Real HTTP: catching the real transaction gap

**`src/test/java/com/example/testscope/ReservationRealHttpTest.java`**

```java
package com.example.testscope;

import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReservationRealHttpTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    BookRepository repository;

    private String id;

    @BeforeEach
    void createUniqueBook() {
        id = "http-" + UUID.randomUUID();
        repository.saveAndFlush(
                new Book(id, "Real HTTP", 2800, 5));
    }

    @AfterEach
    void deleteOnlyOurBook() {
        if (id != null) {
            repository.deleteById(id);
        }
    }

    @Test
    void httpPostActuallyCommitsStockChange() {
        ResponseEntity<ReservationReceipt> response =
                http.postForEntity(
                        "/api/books/{id}/reserve",
                        new ReserveRequest(2),
                        ReservationReceipt.class,
                        id);

        assertEquals(200, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals(3, response.getBody().remaining());

        // A separate repository call observes committed state.
        assertEquals(3,
                repository.findById(id).orElseThrow()
                        .getStock());
    }

    @Test
    void unknownIdThroughTcpReturns404() {
        ResponseEntity<ReservationAdvice.ErrorBody> response =
                http.getForEntity(
                        "/api/books/{id}",
                        ReservationAdvice.ErrorBody.class,
                        "not-present-" + UUID.randomUUID());

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals(
                "BOOK_NOT_FOUND", response.getBody().code());
    }
}
```

**There are 2 methods**, with the server listening on a real random port. The test omits `@Transactional`, so `@BeforeEach` seeds and commits via the repository transaction, the HTTP request executes on the server thread inside the service transaction, and `@AfterEach` cleans up **strictly the ID created by the test**. Even if a test fails after the request, `@AfterEach` still runs in the test lifecycle, preventing leftover rows.

**Another limitation:** `@AfterEach` is not guaranteed if the process receives `kill -9` or a CI host dies. Shared environments need isolated schemas/databases/containers or an owning janitor process. In the H2 in-memory demo, the context/datasource closes when the test JVM exits. Never wipe an entire shared database just to save a few lines of code.

### 28.1. Why does the transaction boundary catch the bug?

When the service has `@Transactional`, the entity fetched by the repository stays inside the service transaction, gets mutated, and JPA dirty checking flushes on transaction commit. If the annotation is deleted, `repository.findById`'s transaction (a read-only method boundary) finishes before the service mutates the entity; the entity becomes detached, so the mutation fails to commit. The real HTTP test inspects **DB state after the response**, catching this behavior in the demo topology.

**Do not overgeneralize** that every service missing `@Transactional` fails: a service calling `save(...)` explicitly starts a transaction, or a caller may provide one. Tests must match the specific transaction contract of the application.

## 29. Total test count and target distribution

| Test class | `@Test` count | Scope | Bugs caught best |
|---|---:|---|---|
| `ReservationServiceTest` | 5 | Pure unit | Business validation, stock math, errors |
| `BookRepositoryTest` | 2 | Data JPA slice | Derived query, entity dirty checking |
| `ReservationControllerMvcTest` | 5 | MVC slice | Routes, JSON, advice, mappings |
| `ReservationFlowMockMvcTest` | 3 | Full context, mock HTTP | Controller–service–JPA wiring and data |
| `ReservationRealHttpTest` | 2 | Full context, TCP | Server-side commits and real HTTP |
| **Total** | **17** | Deliberate multi-scope | Sensible overlap without redundancy |

This is **not** "17 tests = 17 contexts". Plain JUnit needs no context. JPA, MVC, full-context MockMvc, and full-context HTTP have distinct configuration keys. Methods within a class share their context while rolling back/cleaning **data** per their own strategy. The goal is for each scope to have **at least one unique bug-detection reason**, rather than creating 50 full contexts repeating identical assertions.

### 29.1. Run commands

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Run a selected class to debug:

```bash
./gradlew test --tests com.example.testscope.ReservationRealHttpTest
```

The **expected** result with compatible JDK/Gradle/dependency resolution is `BUILD SUCCESSFUL` with the report at `build/reports/tests/test/index.html`. **This expectation comes from code review; I did not execute Gradle in the learner's repository.** Context startup timings and hit counts have no fixed stdout values; they depend on the CI/local machine.

## 30. How to measure the real TestContext cache instead of guessing

Spring TestContext supports logging cache statistics under the category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Add that line to `src/test/resources/application.properties` when debugging and run the suite. Logs appear at multiple lifecycle points, reflecting `hitCount`/`missCount`/context `size` for that **JVM test process**. Never assume "one hit = one test method"; listeners and Spring integrations can access the context multiple times per method.

Investigation steps:

1. Run a baseline of the full suite on CI with fixed hardware, saving the Gradle report and cache DEBUG output.
2. Record context counts, `missCount`/`hitCount`, total elapsed time, GC, and container startup.
3. Re-run enough times to separate cold cache (fresh JVM) from warm reuse **within the same JVM**.
4. Group test classes by configuration keys (profiles, overrides, properties, web environment).
5. Fix **differences with no testing value**, leaving negative scenarios intact.
6. Re-run with the same load, JVM/forks, and concurrency settings.
7. Compare **suite time, failures, flaky rate, and coverage/bug detection**, not just cache hits.

**Important:** If the build runs Gradle with multiple forked JVMs or Maven Surefire forked processes, the static TestContext cache is **not shared** across processes. Raising `cache.maxSize` in one fork cannot help test classes in another fork reuse contexts.

## 31. Gradle forks and parallelism: an often-overlooked trade-off

Settings like `maxParallelForks` and `forkEvery` in Gradle control how test JVMs are spawned/reused. **Illustrative example only, not a general recommendation**:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    maxParallelForks = 2
    forkEvery = 0
}
```

`forkEvery=0` tells Gradle not to force a new test process every N test classes, giving the TestContext cache a chance to reuse within each fork. `maxParallelForks=2` can raise throughput on multi-core machines while creating **two independent caches**, increasing memory, contention, and duplicated context costs across the two forks. Never assume "2 forks is twice as fast".

If tests touch a shared DB, port, queue, or filesystem, running in parallel can increase flakiness. Use **unique fixture IDs, DB schemas, ephemeral ports, test-owned prefixes**, restrict non-parallel-safe tests, or add JUnit resource locks. Never solve races by running everything in one fixed order and calling the tests independent.

### 31.1. Context cache and JUnit method-level parallelism

The TestContext cache is designed for thread-safe lookups at the framework level, yet **beans inside may not be thread-safe**. Two test methods mutating a shared singleton map through the same context can race. If enabling JUnit parallel execution, verify state ownership, mock resets, repository fixtures, and test container lifecycles. When the test framework resets mocks between methods, parallel execution can let test A verify a mock while test B resets/records interactions; design per-test fixtures or disable parallelism on shared-mock groups.

## 32. `@DynamicPropertySource` and Testcontainers: the cache key is not enough to protect dynamic data

`@DynamicPropertySource` is handy for injecting Testcontainers URLs/ports/usernames/passwords into the Spring `Environment`. Yet distinguish carefully:

- The **configuration key** considers method metadata as a context customizer.
- **Dynamic values computed at runtime** tie to specific container ports/lifecycles.
- Two subclasses inheriting the same dynamic property method while pointing to different containers risk **reusing a context with stale configuration**, unless container lifecycles are kept stable.
- Container databases retain rows even when the Spring context is reused.
- A cached context holding HTTP clients/pools pointed at a stopped/restarted container will not refresh all endpoints automatically.

**Right approach:** Use containers with matching lifecycles and one stable dynamic-property source for grouped test classes; or intentionally isolate contexts/`@DirtiesContext` when container endpoints truly change. Then use scoped DB transactions/truncation and unique test data; never expect a fresh container or fresh cache alone to guarantee isolation.

### 32.1. Example dynamic property definition — snippet, not part of the demo

```java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {

    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Here `postgres` is a created Testcontainers `PostgreSQLContainer`; the snippet requires imports and proper lifecycle. Do not copy without deciding whether the container is per-class or shared. Especially when using reusable containers, never let one test run wipe data owned by another user or service.

## 33. `@ActiveProfiles` and property permutations: when are multiple contexts needed?

An app has a feature toggle:

```text
feature.tax.enabled=true
feature.tax.enabled=false
```

If behaviors under the two profiles/properties **truly differ**, keep both tests. Yet if 50 classes each declare the same set of properties in slightly different forms or orders, unnecessary cache fragmentation arises.

Principles:

- Define a **small** set of purposeful test configurations (e.g., default, security-enabled, feature-off, real-http).
- Place **common fixtures** in a shared minimal test config when semantics stay unchanged.
- Use `@Nested`/parameterized pure unit tests when only **runtime inputs** change, not the Spring bean graph.
- Use `ApplicationContextRunner.withPropertyValues(...)` when testing **auto-configuration conditional properties** — spawning tiny contexts instead of booting the whole app per property case.
- Never load one context with feature=true, mutate `Environment` to false at runtime, and pretend Spring bean definitions re-evaluate; conditions are normally evaluated at startup.

**A new context is a worthwhile cost when it tests an important configuration code path.**

## 34. Mocks, spies, static state, and subtle isolation bugs

| State source | Symptom | Resolution |
|---|---|---|
| Mockito mock in context | Test B sees A's interactions | Rely on Spring Mockito reset lifecycle or verify/reset cleanly; avoid parallel conflicts |
| `@MockitoSpyBean` | Real method side effects run during stubbing | Use `doReturn/doThrow` on spy, not `when(spy.realMethod())` |
| Static registry/`AtomicInteger` | Passes alone, fails in suite | Explicit reset or avoid static mutables |
| In-memory cache singleton | Test depends on cache-warm ordering | Clear scoped entries in lifecycle |
| `SecurityContext` `ThreadLocal` | User from previous test appears | Spring Security Test cleanup + custom context cleanup |
| Mutable `Clock` | Test B sees time advanced by A | Per-test clock or reset |
| HTTP pool/client | Stub server stopped yet client keeps connection | Align container/server lifecycle isolation |
| DB rows | Random duplicate ID/constraint failures | Unique per-test IDs/rollback/cleanup |
| Scheduler/async executor | Events arrive after `@AfterEach` | Disable jobs or await bounded completion |
| Temp files/shared directory | Windows file locks/collisions | JUnit `@TempDir`, close streams |
| System property | One class changes setting affecting another | Save/restore in `finally` or separate JVM |
| Kafka/Redis | Messages/keys left from earlier test | Per-test topic/group/prefix + cleanup |

**Independence matters more than a suite running fast in one lucky order.** Caching is only a safe optimization when test-owned state is isolated separately.

### 34.1. Do not overuse `Mockito.reset(mock)`

Spring Framework/Boot test support automatically resets `@MockitoBean` mocks according to the test lifecycle. Calling `Mockito.reset` mid-test can erase interactions that code under test needs to verify and mask bugs. For long-lived manual mocks, clarify ownership; in pure unit tests, instantiating fresh mocks in `@BeforeEach` is usually cleaner.

## 35. `@DirtiesContext` and cache thrashing

If every test class carries:

```java
@DirtiesContext
@SpringBootTest
class EveryTestReloadsContext {
    // ...
}
```

cache hits are destroyed and Hibernate/embedded servers/clients restart continuously. Worse, tests may hide state leaks instead of fixing them. Before adding it, ask:

- Is this **data** needing cleanup, or was a bean definition truly altered?
- Does DB rollback suffice?
- Is there a safe cache-clear API per test key?
- Can the test fixture generate a fresh UUID?
- Is a background thread mutating state after cleanup?
- Did a test break the shared context in an irreversible way?

If the last question is "yes", `@DirtiesContext` makes sense. If only a book row was inserted, rollback or deleting the test-owned ID is far more appropriate. Note that context hierarchies have broader eviction rules than single classes; consult Spring docs when using parent/child contexts.

## 36. Context failure threshold and cascading failures

Since Spring Framework 6.1, TestContext enforces a default **context failure threshold** of **1** per cache key. If loading a context fails the first time, subsequent tests using the same key receive an `IllegalStateException` stating the framework **preemptively skipped** reloading instead of failing repeatedly dozens of times.

This **does not mean every failing test has a separate bug**. When a suite reports dozens of classes failing with "ApplicationContext failure threshold exceeded", locate the **first root startup failure** for that context key (configuration error, port conflict, missing dependency) and fix the root cause. You can set `spring.test.context.failure.threshold` via a JVM property for diagnostics, yet never disable the mechanism just to get longer logs.

**Never judge a cache refactor as broken solely by the count of red tests**: one config typo causing 40 errors can still be **a single root context error**.

## 37. Mutation testing / regression checks: measuring bug detection

After selecting scopes, test with hypothetical mutations to ask "does anything still guard this?":

| Mutation/bug | Unit | MVC slice | JPA slice | Full MOCK | Real HTTP |
|---|---|---|---|---|---|
| Quantity 0 allowed | Catches | Can **miss** if mocked service still throws | Does not check | Catches | Catches |
| JSON field renamed | Misses | Catches | Misses | Catches | Catches if field asserted |
| `findByTitleIgnoreCase` query wrong | Misses if repo mocked | Misses | Catches | Only if flow uses that query | Only if flow uses that query |
| Service `@Transactional` removed | **Misses** | **Misses** | JPA slice omits service | Can miss due to test transaction | Real HTTP DB assertion can catch |
| `@Version` removed | Unit sees no concurrency | Misses | Only if testing concurrency | Misses if single-threaded | Misses if single-threaded |
| `/reserve` route wrong | Misses | Catches | Misses | Catches | Catches |
| Wrong production DB dialect | Misses | Misses | H2 can miss | H2 can miss | H2 can miss |
| Wrong security authority | Misses without security test | Catches with real filter/test | Misses | Catches with real filter | Catches with real auth |
| Data leak between users | Misses without ownership test | Masked by service mock | Misses | Catches if testing user A/B | Catches if testing user A/B |
| Duplicate async event published | Misses if unasserted | Misses | Misses | Can miss | Needs broker/async integration |

**Crucial point:** Scope choice cannot be separated from **assertions**. A real HTTP test asserting only HTTP 200 can still miss an uncommitted DB update. A unit test with sharp assertions can deliver more value than a weak E2E test. This matrix reflects the sample code and specific bug types, not a blanket guarantee for every test of that kind.

## 38. Evidence-based test suite optimization workflow

1. **Inventory tests:** record each class's annotations, mocks, profiles, dynamic properties, containers, and side effects.
2. **Classify bug hypotheses:** business rules, controllers, repository mappings, transactions, HTTP, security, persistence semantics.
3. **Baseline:** measure total suite time, unique context key count, cache hits/misses, container starts, and CI failures.
4. **Pick the narrowest scope sufficient to catch bugs:** move pure rules out of full context, use slices for MVC/JPA/clients, keep full-flow tests for AOP/wiring.
5. **Standardize genuinely equivalent configs:** profiles, shared test configs, mock names/qualifiers; do not add extra mocks.
6. **Isolate data:** roll back at the right boundary, use unique IDs, and clean up non-DB resources.
7. **Check negative scenarios:** missing transactions, broken queries, bad JSON, invalid auth, concurrency, failure paths.
8. **Run the suite reordered and run selected tests alone** to flush out hidden dependencies.
9. **Re-measure in the same environment:** cache misses, wall-clock, memory, CPU, timeouts, and flakiness.
10. **Keep wider-scope tests that offer unique bug-detection value.** Never delete a real HTTP transaction test solely because it is slower than a unit test.
11. **Document trade-offs:** H2 vs. production DB; mocks vs. network; test vs. production threads.
12. **Track over time:** a refactor cutting test duration today can accumulate fragmented cache keys months later.

### 38.1. Useful metrics

| Metric | Interpretation | Easy to misread |
|---|---|---|
| Gradle test task wall-clock | Real feedback wait for developers | Does not split startup/test/container |
| TestContext cache hits/misses | Reuse frequency per key | One method can trigger multiple accesses |
| Unique context count | Fragmentation and memory | Fewer contexts does not guarantee coverage |
| Hibernate/DB startup time | JPA portion of cost | H2 and Postgres differ |
| Context failure count | Cache keys failing startup | May share one root cause |
| CI retry/flaky ratio | Test isolation/capacity issues | Passing on retry does not fix the bug |
| p95 test execution time | Stability under CI load | Differs from service runtime latency |
| Mutation score | Behavioral coverage on selected mutations | Does not replace threat models/E2E tests |
| Local developer feedback | Iteration speed for a class/suite | Not proof of test correctness |

## 39. Anti-patterns and fixes

| Anti-pattern | Consequence | Replace with |
|---|---|---|
| `@SpringBootTest` for every pure calculator | Heavy startup, slow feedback | Plain JUnit |
| Using `@WebMvcTest` to prove transactions | Service is mocked | Full real service/DB test |
| Asserting only `contextLoads` | Almost zero behavioral coverage | Specific behavior assertions |
| Unnecessary unique `@MockBean` per class | Fragmented cache keys | Minimal boundary mocks, consistent naming |
| `@DirtiesContext` on every class | Constant cache misses/reloads | Rollback/fixture cleanup |
| Hardcoded book ID without rollback | Flaky on re-run | Unique IDs or test transactions |
| `@Transactional` around real HTTP expecting rollback | Server thread commits independently | Explicit cleanup/DB isolation |
| Full test transaction hiding missing service transaction | False confidence | Real HTTP/non-test-transaction scenario |
| Using H2 to claim PostgreSQL locking works | Dialect/isolation differences | Testcontainers with real DB |
| Caching bean state to "avoid fixture setup" | Order dependency | Per-test fixtures |
| Static `MutableClock` left unreset | Other tests see wrong time | Per-test clock/reset |
| Mocking the service under test | Bypasses target logic | Mock downstream ports, keep real service |
| Disabling security filters in security MVC tests | Endpoints falsely allowed | Include real `SecurityFilterChain` |
| Parallel runs with shared Mockito mocks | Verification/reset races | Isolate mocks or constrain parallelism |
| Raising cache `maxSize` repeatedly | Rising memory/GC | Curb key explosion first |
| Setting `forkEvery=1` to cure data contamination | Masks leaks, kills cache reuse | Fix cleanup; fork only when genuinely needed |
| Container port collisions across test classes | Collisions and false failures | Random ports/unique environments |
| Reading only the last context error log | Misses root cause | Find first failed context key |
| Deleting slow full-flow tests because slices pass | Loses AOP/wiring coverage | Keep a small set of high-value full tests |
| Counting only test methods | Ignores time/cost/coverage | Track context and bug-detection metrics |

## 40. Comprehension check exercises

### A — Choosing scope

A method computes shipping fees from weight and region code, using no Spring beans. Should `@SpringBootTest` be used?

**Answer:** No. Plain JUnit with boundary values is usually enough; add an integration test only if outcomes depend on external config/serialization that unit tests cannot cover.

### B — Mock names

Two `@WebMvcTest` classes mock the same `PaymentGateway` bean using different field names. Is context reuse guaranteed?

**Answer:** No. The field name can act as a fallback qualifier and alter the context key. Use consistent names when targeting the same bean/qualifier and scope, without weakening other assertions.

### C — Dirty context

A test inserts a row in H2 with `@Transactional` rollback, yet a developer adds `@DirtiesContext` "to keep it clean". Is it needed?

**Answer:** Usually no. Transaction rollback already isolates DB state within that boundary; `@DirtiesContext` causes needless context reloads.

### D — Unit passes, prod fails

A service unit test reduces stock from 5 to 3, yet the real HTTP app fails to commit. What test layer is missing?

**Answer:** A test using the real transactional service bean and checking server-side persisted state; a real HTTP/non-test-managed transaction test helps here.

### E — GET via MockMvc

Does `@SpringBootTest + @AutoConfigureMockMvc` open a socket to embedded Tomcat?

**Answer:** No. MockMvc invokes the servlet stack in-memory; `RANDOM_PORT` is needed to exercise real TCP/server threads.

### F — Test transaction on random port

A real HTTP test class carries `@Transactional`, and a server POST writes to the DB. After the test, is the row guaranteed to roll back?

**Answer:** No. The client test thread and server thread use separate transactions. Use scoped cleanup, DB isolation, or container/transaction boundaries at the service layer.

### G — Query bug

A repository has `findByTitleIgnoreCase`, and a unit test mocks it to always return a book. Will a mutation deleting `IgnoreCase` be caught by the unit test?

**Answer:** No. Only `@DataJpaTest` executing the derived query against a DB catches that bug.

### H — Cache `maxSize`

A suite has 100 context keys due to 100 differing properties, each context expensive. Is raising `maxSize` 32→128 always the right fix?

**Answer:** No. It can spike memory/GC; first remove pointless differences and measure actual cache evictions before experimenting with `maxSize`.

### I — Independence

Test A sets a static `flag=true`, while test B expects `false`. The suite passes when B runs first. Can these be called independent?

**Answer:** No. That is state leakage; reset the flag or remove static mutables, and add reordered/parallel runs to expose leaks rather than hardcoding order.

### J — `@MockitoBean`

A full-context test places `@MockitoBean` on `ReservationService` itself and asserts HTTP 200. Does it verify the service's `@Transactional`?

**Answer:** No. The mock replaces the original bean and its AOP interceptors; the real service must stay unmocked.

### K — Testcontainers

A `@DynamicPropertySource` method uses a per-subclass container, yet the cache reuses a context bound to the old container port. How do you fix it?

**Answer:** Align container lifecycle and config keys, or separate contexts/`@DirtiesContext` per actual differing endpoint. Never assume a dynamic supplier automatically refreshes cached client beans.

### L — Spring cache per JVM

Gradle launches two forked JVMs. Do they share the static TestContext cache?

**Answer:** No. Each JVM process holds its own cache. Balance parallel throughput, memory, and reuse.

### M — Context failure threshold

Dozens of tests report "failure threshold exceeded" after one context startup error. How many bugs do you fix?

**Answer:** Investigate the first root failure for that context key; a single misconfiguration can cause all of them to fail fast.

### N — Optimizing the wrong goal

After refactoring, CI is 30% faster yet `@DataJpaTest` and real HTTP tests were deleted, leaving only mocked MVC tests. Can you claim quality improved?

**Answer:** No. Verify bug detection, DB semantics, and integration coverage were not lost. Speed cannot stand alone.

### O — Mutation

Deleting the service's `@Transactional` leaves the suite green. Should you immediately add `@DirtiesContext`?

**Answer:** No. Add a test without an outer test-managed transaction wrapping the service, checking persist-and-readback across the server/client boundary; `@DirtiesContext` does nothing to catch missing transactions.

### P — Concurrency

A JPA rollback test works sequentially, yet enabling parallel execution causes two tests using the same ID to collide on row creation. How do you fix it?

**Answer:** Per-test unique IDs/schemas/transaction isolation, or disable parallelism for tests sharing state; a new context will not necessarily solve a shared DB collision.

## 41. Pre-merge acceptance checklist

- [ ] Every test group has an explicit bug hypothesis and verification scope.
- [ ] Pure Java rules are tested without Spring wherever possible.
- [ ] Controller mappings/JSON/advice are tested with an MVC slice.
- [ ] Repository mappings/queries are tested with a JPA slice and matching DB.
- [ ] AOP/`@Transactional`/security integration boundaries remain real in at least a subset of tests.
- [ ] At least one end-to-end path protects critical cross-layer wiring.
- [ ] Real HTTP tests are distinguished from MockMvc.
- [ ] Test transactions and server-side commits are clearly distinguished.
- [ ] Mocks do not replace the very bean logic the test intends to prove.
- [ ] Tests do not treat "context starts" as complete coverage.
- [ ] `@ActiveProfiles`/property variants each have a justified reason to exist.
- [ ] `@MockitoBean` names/qualifiers are consistent when targeting the same bean.
- [ ] Bean overrides do not accidentally synthesize fake beans hiding missing production wiring.
- [ ] Context cache keys are understood via metadata, not simplistic class names.
- [ ] Aware of default 32-context/LRU cache and that forks do not share caches.
- [ ] Recorded baseline cache hits/misses and suite elapsed times before optimizing.
- [ ] `@DirtiesContext` used only when the context is genuinely dirtied.
- [ ] Database data isolated via rollback or properly bounded cleanup.
- [ ] Real HTTP tests explicitly clean up committed data.
- [ ] Test data is unique by ID/tenant under parallel/shared DB runs.
- [ ] In-memory caches, clocks, scheduled jobs, and static state are reset/isolated.
- [ ] Mocks are free from parallel reset/verification races.
- [ ] Testcontainers lifecycle aligns with `@DynamicPropertySource`/context cache.
- [ ] Not testing production DB dialects solely with H2 and claiming all SQL works.
- [ ] Negative tests exist for invalid quantity, missing data, and insufficient stock.
- [ ] Positive tests verify persisted state after service operations.
- [ ] Suite can run any class standalone without relying on fixed order.
- [ ] No unbounded sleeps; async tests use bounded timeouts.
- [ ] External resources (files, Redis keys, queue events) have clear ownership/cleanup.
- [ ] Strategy exists for test data left after CI crashes in shared environments.
- [ ] Not sacrificing valuable unique full-flow tests solely to raise cache hits.
- [ ] Re-measured performance and flakiness after changes.
- [ ] QA report explicitly states whether test source was reviewed or actually executed.

**Conclusion:** Optimal test scope is neither "smallest in every situation" nor "`@SpringBootTest` everywhere to be safe". It is **the narrowest scope that still catches important bugs**. The context cache lets integration tests amortize startup cost across matching configurations, yet requires **isolating mutable data and state per test**. Use unit tests for domain rules, slice tests for HTTP/JPA/client contracts, and a small strategic set of full-context/real HTTP tests for AOP, transactions, and system wiring; measure cache keys, CI time, and flakiness before refactoring. If an optimization makes tests pass faster while masking transaction, query, security, or cross-layer bugs, it is not a quality optimization.

### Official Documentation

- Spring Framework 6.2 — Context Caching, cache keys, LRU/maxSize=32, and DEBUG stats: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — `@DirtiesContext` and eviction semantics: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — `@MockitoBean`/`@MockitoSpyBean`, qualifiers, field names, and context reuse: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework 6.2 — Bean overriding / AOP proxies: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Spring Framework 6.2 — Context failure threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Transaction management in tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — `@DynamicPropertySource`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
- Spring Boot 3.5 — Testing Spring Boot Applications: `@WebMvcTest`/`@DataJpaTest`/`@RestClientTest`/`@SpringBootTest`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Auto-configured Data JPA tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-spring-data-jpa
- JUnit Jupiter — Parallel execution, lifecycle, and resource locks: https://junit.org/junit5/docs/current/user-guide/
- Gradle — Test task, `maxParallelForks`, and `forkEvery`: https://docs.gradle.org/current/userguide/java_testing.html
