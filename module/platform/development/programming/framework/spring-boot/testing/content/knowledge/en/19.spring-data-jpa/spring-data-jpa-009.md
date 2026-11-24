# Testing Optimistic Locking and Update Conflicts

## 1. The Problem: Two People Editing the Same Record Simultaneously

In a **Spring Boot + Spring Data JPA** application, two requests can read the same inventory row, order, or profile before saving changes. Without conflict detection, the second writer can **overwrite changes already saved by the first writer**, causing a *lost update*.

Suppose row `SKU-7` has `quantity = 10`:

~~~text
Time            User A                       User B
    t0          read quantity=10, version=0  read quantity=10, version=0
    t1          edit to 8                    edit to 9
    t2          write quantity=8, version=1  still holds snapshot version=0
    t3          —                            tries to write quantity=9 with version=0
                                               |
                         @Version -> rejects stale update
    t4          DB stays quantity=8, version=1
~~~

Without version checking, B's write would leave the DB at 9, silently erasing A's intent. With **optimistic locking**, the DB accepts A's change and then detects that B is working from a **stale version**. B receives a conflict signal and can re-read the data or follow an explicitly designed retry policy.

**Optimistic** here means **not holding exclusive locks while users think**; the application lets parties read and work, then checks versions at write time. This usually fits systems with low write contention relative to read frequency.

Objectives of **“Testing optimistic locking and update conflicts”** in the **Spring Data JPA** series:

1. Understand `@Version`, entity versions, persistence contexts, and conditional SQL.
2. Write tests proving **a successful update increments the version**.
3. Create **two independent snapshots** of the same entity; write snapshot A, then verify stale snapshot B **is rejected**.
4. Verify the DB retains the valid write's values without being overwritten by the stale write.
5. Distinguish ORM conflicts inside a transaction from **client-sent version conflicts over HTTP**.
6. Know how to test HTTP `409 Conflict`, `412 Precondition Failed` with precondition mechanisms, and retry policies.
7. Avoid traps around `@DataJpaTest` rollback, context caching, deferred `flush`, and H2 differing from production DBs.

This lesson uses **Java 17, Spring Boot 3.5.x, Spring Data JPA/Hibernate, H2 in tests, and JUnit Jupiter**. Complete program listings are placed in their proper files. Additional SQL/extension snippets are clearly labeled as *illustrative* rather than claiming to be executed test code.

## 2. How Does @Version Detect Conflicts?

JPA defines `jakarta.persistence.Version` for a property representing an entity's version. Hibernate tracks the version value loaded for each record and, when flushing a change, can emit conditional SQL matching both **id and the old version**.

~~~java
@Entity
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private int quantity;
}
~~~

**This is an abbreviated entity for explanation**; the full runnable example in section 5 includes constructors, accessors, table names, and additional fields.

The SQL below illustrates the mechanism without guaranteeing exact column order or syntax across every Hibernate dialect:

~~~sql
-- A read version = 0 and updates validly:
UPDATE inventory_items
SET quantity = 8, version = 1
WHERE id = 17 AND version = 0;
-- 1 row affected

-- B still holds version = 0:
UPDATE inventory_items
SET quantity = 9, version = 1
WHERE id = 17 AND version = 0;
-- 0 rows affected => optimistic locking conflict
~~~

When the `UPDATE` with the old version matches zero rows, Hibernate/JPA treats it as stale data and raises an exception instead of silently overwriting.

### Three Rules You Must Not Confuse

- **`@Version` belongs to the persistent entity**, not merely an arbitrary field on a DTO or JSON payload. The JPA provider manages and increments the version on updates to versioned entities.
- **Never manually write `entity.setVersion(entity.getVersion() + 1)`**. Incrementing and checking versions is the provider's responsibility; mutating the field manually can break comparison conditions or trigger mapping errors.
- **`@Version` alone does not protect a long-lived edit screen** if each HTTP request loads the **latest** entity and applies changes **without carrying the expected version from when the user read it**. In that case, request B writes against the latest version and does not look stale to JPA.

That is why this article implements **two complementary layers of protection**: JPA version checking at flush/commit, and HTTP commands carrying `expectedVersion` to catch users submitting edits based on outdated data.

### When Does Version Increment?

A new entity with `Long version` can start as `null` in Java before persist; once JPA persists/flushes, Hibernate manages the initial value. **Never hard-code that the first version is always 0 across every provider/mapping/database.** In tests, capture the actual returned version and assert that version **increases** after an update.

Merely reading an entity without modifying it does not increment its version just because `findById` ran. In Hibernate, modifying a managed entity can be written via dirty checking at flush—even without calling `save`—when a transaction is active.

## 3. Exception Types and Detection Timing

A stale update can surface across several API layers:

| Layer | Example Type | Meaning |
| --- | --- | --- |
| Jakarta Persistence | `jakarta.persistence.OptimisticLockException` | JPA detected a version conflict |
| Hibernate | `StaleObjectStateException` and related stale errors | Provider-specific report that a stale snapshot cannot be updated |
| Spring ORM/DataAccess | `ObjectOptimisticLockingFailureException` or subclass `OptimisticLockingFailureException` | Spring exception translation for uniform application handling |
| HTTP API | `409 Conflict` or `412 Precondition Failed` per contract | Client learns the request cannot apply against current state |

Do not assert **exact exception message strings** across Spring/Hibernate versions. Messages may contain SQL, IDs, or entity names that vary by version.

**Error timing matters:**

- `repository.save(entity)` may not emit SQL immediately, especially on managed entities. The error can surface only at **flush or commit**.
- `repository.saveAndFlush(entity)` forces a flush before the method returns; without an outer transaction, the Spring Data repository method manages its own transaction.
- If a test transaction wraps operations and only **rolls back** at the end, unflushed dirty updates never test version conflicts.
- Once a transaction throws an optimistic lock exception, do not continue mutating/committing in the failed transaction. Roll back and open a **new** transaction for any follow-up handling.

Tests should assert the **exception family** at the proper boundary and re-read data after the failed transaction, instead of trusting a log mentioning “stale”.

## 4. @DataJpaTest: The Default Transaction Trap

`@DataJpaTest` focuses on JPA entities, repositories, `EntityManager`, and the test datasource. It is ideal for testing optimistic locking at the persistence layer. However, by default `@DataJpaTest` **opens a transaction per test and rolls back afterward**.

This can make a conflict test produce misleading results:

~~~java
@DataJpaTest
class MisleadingTest {
    // Both findById calls inside the same test-managed transaction
    // may retrieve the same managed entity from the persistence context.
}
~~~

Calling `findById(id)` twice inside the **same persistence context** allows the JPA identity map to return the **exact same managed object**, not two independent snapshots. Assigning them to separate variables `a` and `b` does not prove two “users” read two copies.

~~~java
InventoryItem a = repository.findById(id).orElseThrow();
InventoryItem b = repository.findById(id).orElseThrow();
// Within the same persistence context, a == b may be true.
~~~

Such a test **does not simulate stale versions** properly. Another bug is expecting `save(...)` to throw immediately without flushing, causing assertions to miss when SQL actually executes.

### Strategy Used in This Lesson

For the JPA tests below, apply:

~~~java
@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class InventoryOptimisticLockingTest {
    // No outer test-managed transaction.
}
~~~

Without an outer test transaction, each repository call gets its own transactional boundary per Spring Data JPA. The entity returned by `findById` is **detached once the repository call's transaction/persistence context closes**. Two consecutive reads produce two independent snapshots of the current row. A's save commits, while B still holds the old version and must be rejected on write.

**Note:** this is a **sequential yet deterministic** conflict simulation, not two requests hitting the exact same nanosecond. It faithfully creates **two copies read before the first write**, then checks the stale write. To verify real deadlocks, lock waits, transaction isolation, and live races, write concurrency integration tests with separate connections/transactions on a production-like DB.

## 5. Setting Up the Spring Boot 3.5 + Java 17 Project

We build a small inventory-quantity management app. JPA tests run against in-memory H2; a small HTTP API demonstrates a client sending a version and receiving `409`.

Structure:

~~~text
build.gradle
src/main/java/com/example/jpaoptimistic/
  LockingDemoApplication.java
  InventoryItem.java
  InventoryItemRepository.java
  InventoryView.java
  UpdateQuantityRequest.java
  InventoryService.java
  InventoryController.java
  InventoryApiAdvice.java
  ApiProblem.java
src/test/java/com/example/jpaoptimistic/
  InventoryOptimisticLockingTest.java
  InventoryHttpConflictTest.java
~~~

**`build.gradle` (Gradle Groovy DSL, Java 17):**

~~~groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-data-jpa` provides Spring Data JPA and Hibernate; `starter-web` serves the API; `starter-validation` enables `@Valid`/Jakarta constraints; `starter-test` includes JUnit Jupiter/AssertJ/TestRestTemplate; H2 is in **test runtime** only.

This build file is for **demo tests**. Because H2 is `testRuntimeOnly`, running `bootRun` standalone requires configuring a runtime DB/datasource; never put H2 or test passwords into production config as a default.

Examples use package `com.example.jpaoptimistic` so Spring Boot scans the entity, repository, service, controller, and exception advice using standard layout.

### Entry Point

**`src/main/java/com/example/jpaoptimistic/LockingDemoApplication.java`:**

~~~java
package com.example.jpaoptimistic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LockingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockingDemoApplication.class, args);
    }
}
~~~

## 6. @Version Entity and Real Repository

### 6.1. Entity with id, version, and Mutable Data

**`src/main/java/com/example/jpaoptimistic/InventoryItem.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        setQuantity(quantity);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "Quantity must not be negative"
            );
        }
        this.quantity = quantity;
    }
}
~~~

Key points:

- `@Version` comes from **`jakarta.persistence.Version`**, not a same-named annotation from another library.
- `Long version` is managed by JPA; the class **exposes no version setter**.
- `protected` no-arg constructor for JPA entity instantiation.
- The entity is a mutable class per the JPA persistence lifecycle, **not** a Java record.
- `quantity` is mutated on the entity, and `version` advances on every actual update.
- `@Column(unique=true)` supports SKU uniqueness in Hibernate's demo DDL. In a real DB, manage unique constraints via migrations.

Do not fabricate entity copies by constructing `new InventoryItem("SKU-7", ...)` and injecting `id`/`version` via reflection in tests: that over-mocks and skips the JPA lifecycle you want to test.

### 6.2. Repository

**`src/main/java/com/example/jpaoptimistic/InventoryItemRepository.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

`JpaRepository` provides `save`, `saveAndFlush`, `findById`, `deleteAll`, and standard methods. Hibernate/JPA enforces `@Version` when the repository saves the entity; **no `@Lock` is needed on `findById`** for ordinary optimistic locking on updates.

## 7. JPA Test Suite: Reproducing Stale Updates Without Sleeps or Threads

**`src/test/java/com/example/jpaoptimistic/InventoryOptimisticLockingTest.java`:**

~~~java
package com.example.jpaoptimistic;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class InventoryOptimisticLockingTest {

    @Autowired
    InventoryItemRepository repository;

    private InventoryItem seeded;

    @BeforeEach
    void seedIndependentState() {
        // No test-managed transaction; repository methods commit themselves.
        repository.deleteAll();
        seeded = repository.saveAndFlush(
                new InventoryItem("SKU-7", 10)
        );
    }

    @Test
    void newEntity_hasManagedNonNullVersion() {
        assertThat(seeded.getId()).isNotNull();
        assertThat(seeded.getVersion()).isNotNull();

        InventoryItem stored = repository.findById(seeded.getId())
                .orElseThrow();

        assertThat(stored.getQuantity()).isEqualTo(10);
        assertThat(stored.getVersion()).isEqualTo(seeded.getVersion());
    }

    @Test
    void successfulUpdate_incrementsVersion() {
        Long before = seeded.getVersion();

        InventoryItem current = repository.findById(seeded.getId())
                .orElseThrow();
        current.setQuantity(8);

        InventoryItem saved = repository.saveAndFlush(current);

        assertThat(saved.getVersion()).isGreaterThan(before);
        assertThat(repository.findById(seeded.getId()).orElseThrow()
                .getQuantity()).isEqualTo(8);
    }

    @Test
    void staleDetachedCopy_failsAndDoesNotOverwriteCommittedData() {
        Long id = seeded.getId();

        // Each repository read is a separate transaction/context.
        InventoryItem snapshotA = repository.findById(id).orElseThrow();
        InventoryItem snapshotB = repository.findById(id).orElseThrow();

        assertThat(snapshotA).isNotSameAs(snapshotB);
        assertThat(snapshotA.getVersion())
                .isEqualTo(snapshotB.getVersion());

        Long versionBefore = snapshotA.getVersion();

        snapshotA.setQuantity(8);
        InventoryItem firstWrite = repository.saveAndFlush(snapshotA);
        assertThat(firstWrite.getVersion())
                .isGreaterThan(versionBefore);

        snapshotB.setQuantity(9);

        assertThatThrownBy(
                () -> repository.saveAndFlush(snapshotB)
        ).isInstanceOf(OptimisticLockingFailureException.class);

        InventoryItem afterConflict = repository.findById(id)
                .orElseThrow();

        assertThat(afterConflict.getQuantity()).isEqualTo(8);
        assertThat(afterConflict.getVersion())
                .isEqualTo(firstWrite.getVersion());
    }

    @Test
    void freshReadAfterFirstCommit_canUpdateAgain() {
        Long id = seeded.getId();

        InventoryItem first = repository.findById(id).orElseThrow();
        first.setQuantity(8);
        InventoryItem updatedA = repository.saveAndFlush(first);

        InventoryItem fresh = repository.findById(id).orElseThrow();
        assertThat(fresh.getVersion()).isEqualTo(updatedA.getVersion());

        fresh.setQuantity(6);
        InventoryItem updatedB = repository.saveAndFlush(fresh);

        assertThat(updatedB.getQuantity()).isEqualTo(6);
        assertThat(updatedB.getVersion())
                .isGreaterThan(updatedA.getVersion());
    }

    @Test
    void independentRows_doNotConflict() {
        InventoryItem second = repository.saveAndFlush(
                new InventoryItem("SKU-8", 20)
        );

        InventoryItem itemA = repository.findById(seeded.getId())
                .orElseThrow();
        InventoryItem itemB = repository.findById(second.getId())
                .orElseThrow();

        itemA.setQuantity(7);
        itemB.setQuantity(19);

        repository.saveAndFlush(itemA);
        repository.saveAndFlush(itemB);

        assertThat(repository.findById(itemA.getId())
                .orElseThrow().getQuantity()).isEqualTo(7);
        assertThat(repository.findById(itemB.getId())
                .orElseThrow().getQuantity()).isEqualTo(19);
    }
}
~~~

### 7.1. Why Is the Stale Test the Most Important?

The test creates **two copies loaded prior to any update**. It proves:

1. Both snapshots start with the same version.
2. They are **not the same Java object**, because there is no long outer test-managed transaction.
3. Snapshot A writes successfully and the DB version increments.
4. Snapshot B still holds the old version, and `saveAndFlush` fails with Spring's `OptimisticLockingFailureException`.
5. The DB retains `quantity = 8` and A's version, uncorrupted by stale snapshot B.

No `Thread.sleep` or extra Java threads are needed to verify **stale write rejection**. This sequential approach is fast, repeatable, and better at isolating version-mapping bugs than flaky race tests.

### 7.2. When Might the Exception Not Appear Yet?

If you omit `saveAndFlush`, call `save`, and keep an outer transaction open, Hibernate may only detect the stale state later at commit/flush. Place assertions where the DB update is forced to execute. When testing failures at `flush()` inside a test-managed transaction, ensure the transaction has not already rolled back before the target SQL runs.

### 7.3. Shared Test Data Concerns

Because the test uses `Propagation.NOT_SUPPORTED`, successful updates **genuinely commit to the test DB**. `@BeforeEach` calls `repository.deleteAll()` and re-seeds one `SKU-7` row so every test starts cleanly. Never omit this setup assuming `@DataJpaTest` still rolls everything back automatically: the propagation annotation explicitly disabled that behavior.

When tests run in parallel against the **same datasource**, whole-table `deleteAll` setups will collide. The demo assumes sequential JUnit execution; production suites running in parallel should give each test its own DB/schema/tenant or unique IDs with isolated cleanup.

## 8. @Version Does Not Replace Client HTTP “Expected Version”

A user opens a form at T0:

~~~text
GET /api/inventory/42

{
  "id": 42,
  "sku": "SKU-7",
  "quantity": 10,
  "version": 0
}
~~~

Five minutes later, they click Save. Meanwhile, someone else updated the entity to version 1. If the API executes:

~~~java
InventoryItem current = repository.findById(id).orElseThrow();
current.setQuantity(request.quantity());
repository.saveAndFlush(current);
~~~

it just loaded the **latest** version, succeeds under JPA, and **overwrites the other user's decision**. There is no signal that the request was based on stale data.

For controlled edits, requests should carry **`expectedVersion`**, or use HTTP **`If-Match` + ETag**:

~~~http
PUT /api/inventory/42/quantity
Content-Type: application/json

{"expectedVersion":0,"quantity":8}
~~~

The service compares the current version against what the client read. If they differ, it throws a deliberate conflict error. However, **manual version comparison at the start of a transaction is insufficient under concurrent races**: two transactions can both read version 0, pass the check, and both attempt to write. JPA's `@Version` remains the guard at flush/commit.

Two levels must be tested separately:

| Level | Where Does Stale Data Come From? | Proof |
| --- | --- | --- |
| ORM optimistic locking | Two stale entity snapshots in independent persistence contexts | Hibernate rejects stale `UPDATE` |
| HTTP business conflict | Two clients hold the same `expectedVersion` when sending requests | Server does not silently accept a request built on an old version |

## 9. DTOs and `@Transactional` Service for the HTTP API

### 9.1. DTO Returning Data and Version

**`src/main/java/com/example/jpaoptimistic/InventoryView.java`:**

~~~java
package com.example.jpaoptimistic;

public record InventoryView(
        Long id,
        String sku,
        int quantity,
        Long version
) {
    public static InventoryView from(InventoryItem item) {
        return new InventoryView(
                item.getId(),
                item.getSku(),
                item.getQuantity(),
                item.getVersion()
        );
    }
}
~~~

The version is returned to the client so the client can send it back on writes. In applications with sensitive fields, review what is exposed; never return JPA entities directly if that risks exposing relationships/lazy proxies.

### 9.2. Update Payload

**`src/main/java/com/example/jpaoptimistic/UpdateQuantityRequest.java`:**

~~~java
package com.example.jpaoptimistic;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record UpdateQuantityRequest(
        @NotNull Long expectedVersion,
        @NotNull @Min(0) Integer quantity
) {
}
~~~

Uses `Integer quantity` instead of `int` to distinguish a **missing field** from a valid zero. `@Valid` in the controller together with Jakarta validation rejects null or negative payloads.

### 9.3. Real Service with Transaction Boundaries

**`src/main/java/com/example/jpaoptimistic/InventoryService.java`:**

~~~java
package com.example.jpaoptimistic;

import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryItemRepository repository;

    public InventoryService(InventoryItemRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    @Transactional(readOnly = true)
    public InventoryView get(Long id) {
        InventoryItem item = repository.findById(id)
                .orElseThrow(ItemNotFound::new);
        return InventoryView.from(item);
    }

    @Transactional
    public InventoryView changeQuantity(
            Long id,
            UpdateQuantityRequest request
    ) {
        Objects.requireNonNull(request, "request");

        InventoryItem current = repository.findById(id)
                .orElseThrow(ItemNotFound::new);

        if (!Objects.equals(
                current.getVersion(), request.expectedVersion()
        )) {
            throw new StaleVersion();
        }

        current.setQuantity(request.quantity());

        // Force detection before returning from the service method.
        InventoryItem saved = repository.saveAndFlush(current);
        return InventoryView.from(saved);
    }

    public static class ItemNotFound extends RuntimeException {
    }

    public static class StaleVersion extends RuntimeException {
    }
}
~~~

Spring AOP `@Transactional` wraps `changeQuantity`. The service checks the client's expected version, mutates the **managed** entity, and calls `saveAndFlush` to push the update to the DB before returning the DTO.

If two concurrent requests read the same version and pass `Objects.equals`, Hibernate's optimistic lock check at flush/commit still prevents the stale write. The error can arise during the repository call or when the proxy commits the transaction; the web layer must handle both **`StaleVersion`** and **`OptimisticLockingFailureException`**.

Never retry by calling `saveAndFlush(current)` again inside the **same failed transaction**. The transaction may be rollback-only and entity state is unsafe to reuse.

## 10. Controller and HTTP 409 Conflict

**`src/main/java/com/example/jpaoptimistic/InventoryController.java`:**

~~~java
package com.example.jpaoptimistic;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public InventoryView get(@PathVariable Long id) {
        return service.get(id);
    }

    @PutMapping(
            value = "/{id}/quantity",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public InventoryView update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateQuantityRequest request
    ) {
        return service.changeQuantity(id, request);
    }
}
~~~

**`src/main/java/com/example/jpaoptimistic/ApiProblem.java`:**

~~~java
package com.example.jpaoptimistic;

public record ApiProblem(String code) {
}
~~~

**`src/main/java/com/example/jpaoptimistic/InventoryApiAdvice.java`:**

~~~java
package com.example.jpaoptimistic;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryApiAdvice {

    @ExceptionHandler({
            InventoryService.StaleVersion.class,
            OptimisticLockingFailureException.class
    })
    public ResponseEntity<ApiProblem> conflict(Exception ignored) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiProblem("VERSION_CONFLICT"));
    }

    @ExceptionHandler(InventoryService.ItemNotFound.class)
    public ResponseEntity<ApiProblem> notFound(Exception ignored) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiProblem("ITEM_NOT_FOUND"));
    }
}
~~~

This defines an **explicit HTTP contract**:

- Successful GET → **200** with `InventoryView` (including `version`).
- PUT with current expected version → **200** and incremented version after update.
- PUT with old version → **409 Conflict** and JSON `{"code":"VERSION_CONFLICT"}`.
- Nonexistent ID → **404 Not Found**.
- Request missing expected version or negative quantity → **400 Bad Request** via Bean Validation.

**409 is not the only valid status code for conflicts.** If an API implements HTTP conditional requests with `ETag` and `If-Match`, a mismatched precondition is standardly expressed as **412 Precondition Failed**; the API may also return `428 Precondition Required` when a client omits the precondition. This example uses JSON `expectedVersion` and intentionally selects 409.

`@ExceptionHandler(OptimisticLockingFailureException.class)` translates persistence errors into a stable response, though in complex architectures with outer exception wrappers, verify that the transaction/translation layer actually exposes the intended cause; never leak stack traces or SQL to clients.

## 11. HTTP Integration Test: Client Sends Stale Version

This test uses a **real server** via `@SpringBootTest(RANDOM_PORT)` and `TestRestTemplate`. Rather than merely invoking a Java method, it exercises HTTP serialization, controller, service, repository, and the H2 DB. No browser is needed to verify the API conflict contract.

**`src/test/java/com/example/jpaoptimistic/InventoryHttpConflictTest.java`:**

~~~java
package com.example.jpaoptimistic;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class InventoryHttpConflictTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    InventoryItemRepository repository;

    private Long id;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        id = repository.saveAndFlush(
                new InventoryItem("SKU-7", 10)
        ).getId();
    }

    private HttpEntity<UpdateQuantityRequest> json(
            Long expectedVersion,
            Integer quantity
    ) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return new HttpEntity<>(
                new UpdateQuantityRequest(expectedVersion, quantity),
                headers
        );
    }

    private InventoryView getCurrent() {
        ResponseEntity<InventoryView> response = http.getForEntity(
                "/api/inventory/{id}",
                InventoryView.class,
                id
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        return response.getBody();
    }

    @Test
    void staleClientVersion_returns409AndPreservesFirstWrite() {
        InventoryView before = getCurrent();

        ResponseEntity<InventoryView> first = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 8),
                InventoryView.class,
                id
        );

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(first.getBody()).isNotNull();
        assertThat(first.getBody().quantity()).isEqualTo(8);
        assertThat(first.getBody().version())
                .isGreaterThan(before.version());

        ResponseEntity<ApiProblem> stale = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 9),
                ApiProblem.class,
                id
        );

        assertThat(stale.getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(stale.getBody())
                .isEqualTo(new ApiProblem("VERSION_CONFLICT"));

        InventoryView after = getCurrent();
        assertThat(after.quantity()).isEqualTo(8);
        assertThat(after.version())
                .isEqualTo(first.getBody().version());
    }

    @Test
    void newVersionAfterRefresh_allowsAnotherUpdate() {
        InventoryView before = getCurrent();

        ResponseEntity<InventoryView> first = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(before.version(), 8),
                InventoryView.class,
                id
        );

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(first.getBody()).isNotNull();

        ResponseEntity<InventoryView> second = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(first.getBody().version(), 6),
                InventoryView.class,
                id
        );

        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(second.getBody()).isNotNull();
        assertThat(second.getBody().quantity()).isEqualTo(6);
        assertThat(second.getBody().version())
                .isGreaterThan(first.getBody().version());

        assertThat(getCurrent().quantity()).isEqualTo(6);
    }

    @Test
    void missingExpectedVersion_returns400WithoutChangingRow() {
        InventoryView before = getCurrent();

        ResponseEntity<String> invalid = http.exchange(
                "/api/inventory/{id}/quantity",
                HttpMethod.PUT,
                json(null, 8),
                String.class,
                id
        );

        assertThat(invalid.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);

        InventoryView after = getCurrent();
        assertThat(after.quantity()).isEqualTo(before.quantity());
        assertThat(after.version()).isEqualTo(before.version());
    }

    @Test
    void unknownId_returns404() {
        ResponseEntity<ApiProblem> response = http.getForEntity(
                "/api/inventory/{id}",
                ApiProblem.class,
                Long.MAX_VALUE
        );

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody())
                .isEqualTo(new ApiProblem("ITEM_NOT_FOUND"));
    }
}
~~~

### 11.1. What Is Verified?

- **Response carries current version:** client learns the current revision before editing.
- **First write A succeeds:** HTTP 200, quantity 8, version incremented.
- **Second write B with old version fails:** HTTP 409 and specific error code.
- **DB is not overwritten:** subsequent GET still returns quantity 8 and A's version.
- **Client refreshing can write again:** passes the new version as expected version.
- **Payload missing expected version:** HTTP 400 before touching data.
- **Nonexistent ID:** HTTP 404, distinct from version conflicts.

This HTTP test verifies sequential **request-level conflicts** via `expectedVersion`. Meanwhile, `InventoryOptimisticLockingTest` in section 7 verifies **the ORM's own version enforcement**. Both are needed: manual version checks in the service do not replace JPA optimistic locking when requests arrive truly concurrently.

### 11.2. Why Not Add @Transactional to the HTTP Test?

In `@SpringBootTest(RANDOM_PORT)`, the test method acts as an HTTP client while the server handles requests in separate threads/transactions. `@Transactional` on the test client **does not automatically roll back** commits performed inside the HTTP server's transactions. The example uses `@BeforeEach` to seed/reset data and operates on one test row. In a real suite running tests in parallel, replace table-wide `deleteAll` with isolated fixtures.

**Do not hard-code port 8080:** Boot-configured `TestRestTemplate` resolves relative URLs directly to the embedded test server. JSON payloads and expected versions are fully controlled, eliminating `Thread.sleep` or guesswork over request ordering.

## 12. Distinguishing JPA Conflicts from Business Rule Conflicts

The same `409 Conflict` can represent very different causes:

| Conflict | How Detected | Example |
| --- | --- | --- |
| Optimistic lock stale entity | `@Version` and SQL affected row count | Two snapshots with same version write sequentially |
| Stale client expected version | Service compares against current version | Form opened before another user edited it |
| Business invariant | Domain check inside proper transaction | Cannot reduce stock below zero |
| Unique constraint | Database unique index | Two requests insert the same SKU |
| Pessimistic lock/timeout | DB lock or transaction timeout | Resource locked by another transaction |

Never catch **every `RuntimeException`** and return 409; programming bugs, dropped datasource connections, or malformed client payloads are not version conflicts.

Likewise, **optimistic locking alone does not prevent overselling** when business rules span multiple rows or aggregate stock totals. With per-item versions, invariants spanning multiple rows still need appropriate transaction isolation, locks/constraints, or coordination protocols.

### If the API Uses ETag and If-Match

A standard HTTP API might return:

~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/json

{"id":42,"sku":"SKU-7","quantity":10}
~~~

The client writes:

~~~http
PUT /api/inventory/42/quantity
If-Match: "7"
Content-Type: application/json

{"quantity":8}
~~~

When the ETag does not match the resource's current version, **412 Precondition Failed** accurately expresses the failed precondition. Still, distinguish **strong vs. weak ETag semantics** and representation-based ETag generation; do not naively stick a string version into the header and claim full `If-Match` compliance. The runnable example in this article **does not implement ETags**, opting instead for `expectedVersion` in JSON with 409.

## 13. Bulk Updates/Deletes and Paths That Bypass @Version

`@Version` protects ordinary ORM entity operations. However, **JPQL bulk updates/deletes**, native SQL, and jobs writing straight to the database can **bypass automatic version checks and increments**.

Example query that can be dangerous if used carelessly to overwrite quantity:

~~~java
@Modifying
@Query("""
       update InventoryItem i
       set i.quantity = :quantity
       where i.id = :id
       """)
int replaceQuantityWithoutVersionCheck(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

This is an **illustrative repository method snippet**, absent from the runnable `InventoryItemRepository` in section 6. It does **not** check the old version and normally does **not** increment the version. If one job uses this path while regular requests use the ORM, optimistic locking protection can silently break.

A controlled approach puts the version in the `WHERE` clause and inspects the affected row count:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
       update InventoryItem i
       set i.quantity = :quantity,
           i.version = i.version + 1
       where i.id = :id
         and i.version = :expectedVersion
       """)
int updateIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") Long expectedVersion,
        @Param("quantity") int quantity
);
~~~

This is also an **illustrative extension** for a numeric `Long` version, requiring `@Transactional` at the service/caller, `@Modifying`/`@Query`/`@Param` imports, and return-value handling:

- `rows == 1`: updated exactly one row matching the version.
- `rows == 0`: version mismatch **or nonexistent id**; differentiate them if the API uses distinct error codes.
- Bulk queries **bypass managed persistence context state**. If the entity was already loaded in the same transaction, flush/clear appropriately or avoid mixing bulk updates with dirty managed entities to prevent stale reads.

This is not a drop-in replacement for all versioned JPA entity operations. It requires dedicated tests for affected row counts, transaction boundaries, missing IDs, error handling, and DB dialect support. **Never use bulk queries without a version predicate** when stale writers must be blocked.

## 14. Optimistic vs. Pessimistic Locking; @Lock Is Not @Version

| Attribute | Optimistic `@Version` | Pessimistic `PESSIMISTIC_WRITE` |
| --- | --- | --- |
| Approach | Detects conflicts at write time via version check | Acquires DB lock on the row for the transaction |
| Best suited for | High reads, low writes; client think time | High write contention or mandatory DB serialization |
| Primary risks | Writers must handle conflicts/retries | Lock waits, timeouts, deadlocks, lower throughput |
| Hold duration | No lock held while waiting on users | Lock held for the transaction's duration |
| Tests needed | Stale snapshots, version increments, no lost updates | Two real transactions, lock waits/timeouts/isolation |

Example repository method requesting a lock on read:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findForUpdate(@Param("id") Long id);
~~~

This is an **extension snippet**, requiring `jakarta.persistence.LockModeType`, Spring Data `@Lock`, `@Query`, `@Param`, and an active transaction. It **differs** from `@Version`: calling `findForUpdate` outside a proper transaction cannot hold the DB lock across operations.

JPA also offers `LockModeType.OPTIMISTIC` and `OPTIMISTIC_FORCE_INCREMENT` to verify versions or force version increments during certain reads or aggregate coordination. Never treat them as a silver bullet for multi-table invariants without a clear transaction/coordination protocol.

## 15. Testing Real Concurrency Against a Production-Like Database

The sequential two-snapshot test in section 7 proves the **stale version mechanism**. To test production-like behavior when two transactions execute concurrently, write separate integration tests using **PostgreSQL/MySQL matching production via Testcontainers**, or an equivalent test DB.

### Two-Transaction Concurrency Scenario

~~~text
Create item version V
         |
     split into 2 real transactions
         |
   Tx A reads version V         Tx B reads version V
         |                            |
   wait until both read         wait until both read
         |                            |
   A updates / commits          B tries to update / commit
         |                            |
   A succeeds                   B conflicts or blocks on DB
         |                            |
   final check: A's data, version V+1
~~~

This is a **scenario diagram**, not executed thread-scheduling code. In real tests:

1. Use two separate transactions; never share one `EntityManager` across two threads because `EntityManager` is not thread-safe.
2. Use a barrier/latch to guarantee **both read the same version** before allowing updates.
3. Control commit ordering deterministically if the test requires A to win; never rely on `Thread.sleep(200)`.
4. Account for DB isolation: some DBs report serialization failures, deadlocks, or lock timeouts at different steps rather than a tidy JPA exception.
5. Do not hardcode one DB's exact exception class before verifying your dialect/isolation behavior.
6. After the failing transaction rolls back, re-query using a **fresh** persistence context to assert final database state.
7. Never share transactions between a test method and server threads in HTTP integration tests.
8. Avoid running concurrency tests that share SKUs/DBs in parallel without isolation.

**H2 does not substitute for PostgreSQL/MySQL** regarding transaction isolation, lock semantics, collations, generated SQL, and deadlocks. H2 is great for fast version-mapping tests; production-critical transaction properties should be tested on the target DB.

### Testing “Exactly One Succeeds”

In a race test where two writers edit the same row from version V, goals typically are:

- **No lost updates:** both writers must never succeed from the same version V.
- **One valid result is saved:** verify the final row and version.
- **Losing writer gets a clean failure signal:** classified as optimistic/serialization/timeout per design.
- **No stuck transaction state** after the test finishes.

If a requirement demands “strictly one writer succeeds and one receives an optimistic exception”, control isolation/commit order and the DB environment carefully. Do not expect every DB to raise the **exact same exception class** during races across different drivers/providers.

## 16. Retries: Not Every Conflict Should Be Retried Automatically

After a stale version conflict, an application may:

1. **Return 409 to the client:** user reviews the changes and decides whether to resubmit against the latest data.
2. **Re-read in a fresh transaction and reapply the operation:** valid only when business logic permits re-evaluating against the new state.
3. **Intentionally merge:** combine edits to independent fields with domain rules catching conflicting edits on the same field.
4. **Never auto-retry:** when actions have non-idempotent side effects such as transferring money, booking tickets, capturing payments, or dispatching deduplication-less notifications.

For instance, “increment by 1” differs sharply from “set quantity = 9”:

- For **increment +1**, re-reading and applying another increment can work if invariants and idempotency hold.
- For **set = 9**, blindly retrying would overwrite someone else's valid update. The API should surface the conflict so the client refreshes or confirms the overwrite.

When retrying **after an optimistic lock exception**, the failed transaction must roll back first. Each retry needs a **brand-new transaction**, freshly loaded data, and a bounded retry limit. Putting `@Retryable` on a self-invoked method can bypass the Spring proxy; verify AOP/transaction ordering carefully and test with a controlled conflict scenario.

**Never treat raising retry counts as a cure-all for high contention.** If the domain requires serialized updates or cannot tolerate high-traffic conflicts, consider pessimistic locks, command queues, atomic DB updates, idempotency keys, or aggregate redesign.

## 17. Common Mistakes

1. **Creating two Java variables in one persistence context.** `a` and `b` can point to the exact same managed entity. **Fix:** use two independent transactions/persistence contexts or real detached snapshots.
2. **Relying on `@DataJpaTest` default rollback to test commits.** Rollback can mask flush/commit timing and cross-transaction effects. **Fix:** choose transaction boundaries deliberately.
3. **Calling `save` and asserting an exception too early.** SQL hasn't run yet. **Fix:** use `saveAndFlush`/`flush` or assert after commit.
4. **Manually incrementing `version` in Java.** Breaks provider-managed semantics. **Fix:** let JPA manage the version.
5. **Asserting the initial version must equal 0.** Depends on provider/mapping. **Fix:** record the actual version and assert it increments.
6. **Asserting only the exception without re-reading the DB.** An error might be raised while another path already corrupted the data. **Fix:** check final state after rollback.
7. **Catching every exception and returning 409.** Masks infrastructure/coding bugs. **Fix:** handle version conflicts and defined business errors specifically.
8. **Having `@Version` while requests omit `expectedVersion`.** Stale UI edits overwrite newer versions if the service always loads fresh. **Fix:** round-trip version/ETag from GET to PUT.
9. **Checking `expectedVersion` manually without `@Version`.** Two concurrent transactions can both pass the check. **Fix:** combine with JPA versioning or atomic SQL compare-and-update.
10. **Using JPQL bulk updates without incrementing version.** Bypasses entity protection. **Fix:** include version predicate + row count check or use the versioned entity path.
11. **Writing race tests with `Thread.sleep`.** Does not guarantee transaction ordering. **Fix:** barriers/latches, separate transactions, bounded timeouts.
12. **Using H2 to conclude Postgres locking/isolation is sound.** DB semantics differ. **Fix:** Testcontainers on the target DB when needed.
13. **Retrying inside the failed transaction.** Transaction may be rollback-only. **Fix:** roll back, reload fresh, start a new transaction.
14. **Auto-retrying absolute overwrites, causing semantic lost updates.** Non-commutative operations. **Fix:** return 409 and provide conflict resolution/confirmation.
15. **Forgetting to test stale deletes.** `@Version` can guard entity deletion depending on provider, while bulk deletes can bypass it. **Fix:** add delete tests when versioned records can be deleted.
16. **Failing to separate version conflicts from unique constraints.** Different remediations. **Fix:** map error codes/HTTP statuses by cause.
17. **Putting `@Transactional` on HTTP client tests assuming the server rolls back.** Wrong transaction boundary. **Fix:** seed/clean up outside server requests explicitly.
18. **Returning version in responses while omitting it from update requests.** UI cannot prove which revision it edited. **Fix:** send expected version or `If-Match`.
19. **Not testing updates on unrelated rows.** Easy to miss locking bugs that block the entire table. **Fix:** test independent rows.
20. **Missing migrations for the version column in production.** Auto-created test schemas pass while deployment fails. **Fix:** Flyway/Liquibase and dedicated migration tests.

## 18. QA Checklist for Optimistic Locking

When reviewing a Spring Data JPA test or pull request:

- [ ] Does the entity have `@Version` with a JPA-supported type?
- [ ] Is there zero code manually assigning/incrementing the version?
- [ ] Does the DB schema/migration include the version column?
- [ ] Do positive tests prove valid updates succeed and increment the version?
- [ ] Are the two snapshots in stale tests **genuinely independent**, not sharing an identity map?
- [ ] Is there a real flush/commit forcing stale update detection at the right time?
- [ ] Do tests assert stale writers are rejected with the appropriate exception family?
- [ ] Do tests reload the DB in a fresh context and confirm the winning writer's data survived?
- [ ] Are tests independent of method execution order, ports, or random timing?
- [ ] If using `@DataJpaTest`, were default rollbacks accounted for and transaction boundaries explicitly designed?
- [ ] Do HTTP edit commands carry `expectedVersion` or ETag/preconditions when think-time overwrites must be prevented?
- [ ] Are there HTTP tests for stale version → 409 or 412 per contract?
- [ ] Are there tests where the client refreshes the version and writes again successfully?
- [ ] Are there tests for missing version or invalid quantity → 400?
- [ ] Are JPA, business, and DB constraint exceptions kept distinct instead of merged into one vague error?
- [ ] Do JPQL/native/batch writers enforce version predicates or explicit synchronization?
- [ ] Are retries bounded, run in fresh transactions, and protective of idempotency/invariants?
- [ ] Do real concurrency tests use a production-like DB when domain logic relies on isolation/lock waits?
- [ ] Avoided putting `@Transactional` on HTTP test clients expecting server request rollback?
- [ ] Avoided claiming `@Version` protects multi-table aggregates without an explicit coordination protocol?

### Commands to Run the Test Suite

From the directory containing the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.jpaoptimistic.InventoryOptimisticLockingTest"
./gradlew test --tests "com.example.jpaoptimistic.InventoryHttpConflictTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.jpaoptimistic.InventoryOptimisticLockingTest"
.\gradlew.bat test --tests "com.example.jpaoptimistic.InventoryHttpConflictTest"
~~~

This lesson includes **5 `@DataJpaTest` methods and 4 `@SpringBootTest` HTTP methods**, totaling **9 JUnit cases**. With Spring Boot 3.5, H2, transaction boundaries, and dependencies configured as described, all assertions are expected to PASS. **This is an expectation from reading the code, not a log of an actual test run performed during writing.** There are no `System.out.println` statements, so the code produces no fixed stdout to copy; Gradle/JUnit output varies by environment.

**Core summary:** `@Version` lets Hibernate catch stale updates at the **persistence boundary**, while `expectedVersion`/`If-Match` lets the HTTP API know **which revision** the client edited. Tests must keep two snapshots independent, force flush/commit, assert the conflict, and **verify final database state**, scaling up to real-DB concurrency tests when production races are a business concern.

### Official References

- [Spring Boot 3.5 — @DataJpaTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Hibernate ORM — Locking and Optimistic Versioning](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#locking-optimistic)
- [Jakarta Persistence — @Version](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version)
- [Spring Framework — Transaction Management and Test Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework — OptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/OptimisticLockingFailureException.html)
- [HTTP Semantics — 409 Conflict and 412 Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.10)