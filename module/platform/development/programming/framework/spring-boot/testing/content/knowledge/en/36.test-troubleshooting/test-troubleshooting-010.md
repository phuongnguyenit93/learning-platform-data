# Database constraint fails only after flush or commit

A Spring Data JPA test calls `repository.save(entity)` and receives no exception; the developer concludes the data is valid. Yet when a request goes through a `@Transactional` service in production, the transaction ends and the database returns a unique, foreign key, or check constraint error. Another more dangerous situation: a `@DataJpaTest` passes because it performs **rollback** by default, whereas a real deployment **commits** and a constraint declared as **DEFERRABLE INITIALLY DEFERRED** is only checked at the end of the transaction.

This Knowledge article **“Database constraint fails only after flush or commit”** belongs to the **Test Troubleshooting** group of the **Spring Boot – testing** module. We will understand the exact milestones **persist/save → pending SQL → flush → database statement check → commit**, and then design tests that know *which milestone they are testing*. The focus is on diagnosing failure timing, not merely learning how to add `assertThrows`.

The article uses **Java 17+, Spring Boot 3.5.16, Spring Data JPA, Hibernate 6.x, JUnit Jupiter 5, and H2** for runnable examples without Docker; it adds **PostgreSQL 17** in a separate experimental section to show a constraint actually deferred until commit. The H2 demo verifies the unique error at **flush**; the PostgreSQL example uses `DEFERRABLE INITIALLY DEFERRED` to demonstrate that an error can wait until **commit even after flushing**. All examples explicitly state which layer is being tested and where a real database is required.

**Key takeaway:** `save()` does not mean SQL has been sent, `flush()` does not mean committed, and transaction rollback in tests does not fully verify a constraint evaluated at commit. However, you should not claim “every constraint only fails at commit”: the timing depends on the **JPA provider, ID generator, flush mode, SQL execution, constraint type, DDL, and database**.

## 1. Learning objectives

After this article, you will be able to:

- Distinguish between managed entity/pending changes, SQL execution, flush, commit, and rollback.
- Understand Hibernate **transactional write-behind** and why `repository.save` might not run an INSERT yet.
- Know what `JpaRepository.flush()`, `saveAndFlush()`, and `EntityManager.flush()` actually do.
- Distinguish errors caused by JPA/Bean Validation, immediate database constraints, and PostgreSQL deferred constraints.
- Understand why `GenerationType.IDENTITY` can run INSERT earlier than `UUID/SEQUENCE` and change test timing.
- Explain `FlushModeType.AUTO`, `COMMIT`, query-triggered flushes, and batching.
- Test unique violations with `@DataJpaTest` and `assertThrows` around the **exact flush call**.
- Avoid using `assertDoesNotThrow(repository::save)` to conclude that a unique constraint has been tested.
- Know how to test commit with `TransactionTemplate` when a test method is not wrapped in a test-managed transaction.
- Know that `@DataJpaTest` rolls back by default and why that can hide commit-time errors.
- Understand `TestTransaction.flagForCommit()/end()` as an option when you need to test commit inside a test transaction.
- Distinguish exceptions at the repository proxy, service transaction proxy, and HTTP controller boundary.
- Avoid swallowing persistence exceptions inside a transaction already marked rollback-only and then trying to return success.
- Know common SQLSTATE codes such as PostgreSQL `23505` (unique), `23503` (foreign key), `23502` (not null), and `23514` (check).
- Design safe application error mapping without turning every `DataIntegrityViolationException` into “duplicate email”.
- Use SQL logs and constraint names to investigate without relying on exact localized error messages.
- Verify the final state after rollback/commit by querying in a new transaction, not just inspecting a managed entity.
- Choose between an H2 slice test and PostgreSQL Testcontainers based on actual constraint semantics.
- Recognize common mistakes regarding transaction rollback, query auto-flush, test data isolation, and concurrent writes.

## 2. Timeline: four states that are easy to confuse

```text
HTTP POST /accounts
  |
  v
@Transactional service
  |
  +-- repository.save(new CustomerAccount(...))
  |      - entity is managed in the persistence context
  |      - INSERT might NOT have been sent yet
  |
  +-- repository.flush() or saveAndFlush()
  |      - Hibernate executes pending SQL
  |      - immediate DB constraints are usually checked right away
  |      - transaction has NOT committed yet
  |
  +-- service method body returns
  |
  +-- transaction proxy prepares to COMMIT
  |      - may auto-flush any remaining pending changes
  |      - database may check deferred constraints at COMMIT
  |
  +-- COMMIT succeeds -> changes visible per isolation level
         or COMMIT fails -> rollback/error to caller
```

An error that “only appears on flush or commit” is rarely mysterious: beforehand, **no violating SQL had been executed yet**, or the database received the SQL but was **deferring constraint checking** until the transaction ended.

**Do not equate flush and commit:**

- `flush()` synchronizes pending changes via SQL within the existing transaction.
- `commit()` finishes the transaction successfully; flushing may be needed before commit.
- Flushed data **can still be rolled back**.
- Immediate constraints are usually checked when the statement runs, not necessarily when the transaction commits.
- A PostgreSQL **deferrable** constraint in deferred mode can wait until commit even after insert and flush have completed.
- This mechanism differs from Bean Validation exceptions, which occur before SQL.

## 3. Three cases with the same surface behavior

| Description | Real cause | Detection milestone |
|---|---|---|
| `save` returns normally, `flush` throws unique error | Hibernate defers INSERT; DB has a standard unique constraint | When SQL INSERT runs during flush |
| `saveAndFlush` returns normally, `commit` throws unique error | PostgreSQL constraint is DEFERRED | When the database checks at COMMIT |
| `save` throws immediately | IDENTITY requires INSERT to obtain id, JPA validation, or early SQL execution | Inside save/persist/SQL before explicit flush |

Therefore, a test should state *“with the current entity mapping and provider/DB, the error appears at milestone X”*, rather than asserting a universal rule that `save` can never throw.

### 3.1. Different QA goals

- **Test that mapping/constraint exists:** produce violating data and catch the exception at flush/commit according to the DDL.
- **Test service contract:** the caller of the transactional service receives the right business error/HTTP response.
- **Test transaction correctness:** failure must roll back all changes belonging to the transaction.
- **Test concurrency:** two concurrent transactions do not create duplicates even when the application has an `existsByEmail` precheck.
- **Test DB fidelity:** use real PostgreSQL/Oracle/MySQL and migrations when verifying constraint-specific semantics.

## 4. A JPA persistence context is not a database table

`EntityManager` manages entity instances, the identity map, snapshots, and pending actions. A `repository.save` typically uses `EntityManager.persist` for a new entity or `merge` for an existing one; it places the object into a managed state inside the persistence context. Hibernate can defer INSERT/UPDATE/DELETE statements to batch or reorder them.

Conceptual example:

```java
@Transactional
public void registerTwice() {
    repo.save(new CustomerAccount("duplicate@example.test"));
    repo.save(new CustomerAccount("duplicate@example.test"));

    // Up to here, the second SQL INSERT might not have run yet.
    // No exception does NOT prove the constraint accepted the data.
}
// When the proxy commits: Hibernate auto-flushes, and the DB may report unique violation.
```

This is just a snippet assuming `repo` is injected. In the complete project below, `CustomerAccount` uses a `UUID` ID generated by Hibernate before INSERT, allowing tests to observe two `save` calls finishing before the SQL constraint fails at commit. With `IDENTITY`, the story can differ.

### 4.1. “Data visible through the entity” is not proof of persistence

After `entity.setEmail(...)`, calling `entity.getEmail()` naturally returns the new value in RAM. `EntityManager.find(...)` in the same persistence context can also return the same managed entity via the first-level cache. To verify database state:

1. Perform a flush when SQL is needed.
2. Call `entityManager.clear()` to drop first-level-cache state.
3. Re-query in an appropriate transaction.
4. When a real commit is required, let the transaction finish successfully and then query from a new transaction.
5. Do not ignore errors occurring right at commit/cleanup.

## 5. What is Hibernate flush and when does it happen?

Hibernate `flush` is the process of synchronizing persistence context state into SQL statements. With the commonly used `AUTO` flush mode, a flush can happen:

- When calling `entityManager.flush()` or repository `flush()` explicitly.
- Before transaction commit.
- Before certain JPQL/HQL queries whose queried tables overlap with tables that have pending changes.
- Before certain native SQL queries, depending on bootstrapping and registered synchronizations/query spaces.
- Due to certain APIs/generators forcing SQL earlier.

Do not assume “Hibernate only flushes at commit”. A single line like `repository.count()` or a JPQL query can inadvertently trigger a flush, causing an exception to appear **earlier than the author expected**.

### 5.1. FlushModeType.AUTO vs COMMIT

```java
entityManager.setFlushMode(FlushModeType.AUTO);
// Allows the provider to flush before queries when needed and before commit.

entityManager.setFlushMode(FlushModeType.COMMIT);
// Hibernate usually defers query-triggered flushes until commit.
```

This is a snippet; it requires importing `jakarta.persistence.FlushModeType` and having a valid `EntityManager`. With JPA `COMMIT`, whether pending changes become visible to queries before commit is **not uniformly guaranteed**. Do not set the flush mode solely to force a test to fail at commit if production uses AUTO; test with the real runtime configuration and state expectations clearly.

**Do not switch to MANUAL** to “silence exceptions”: manual flush can prevent changes from being sent at the intended boundary. Constraint failures must still be resolved at the data, DDL, and transaction boundary levels.

## 6. `save`, `saveAndFlush`, `flush`, and `saveAllAndFlush`

| API | Main effect | Does it commit the whole service transaction by itself? |
|---|---|---|
| `repository.save(entity)` | Persist/merge entity | **No** if participating in an outer transaction |
| `repository.flush()` | Push pending changes through the JPA provider | **No** |
| `repository.saveAndFlush(entity)` | Save entity then flush | **No** |
| `repository.saveAllAndFlush(entities)` | Save multiple entities then flush | **No** |
| `entityManager.flush()` | Synchronize persistence context | **No** |
| `transactionManager.commit(...)` | Complete the transaction | **Yes**, may have to flush first |
| `TransactionTemplate.execute(...)` | Run callback in transaction, commit after callback | Commits at execute boundary, or rolls back on error |

**Warning outside a transaction:** Spring Data repository methods have their own transaction attributes. Calling `saveAndFlush` from a controller **with no outer transaction** can cause the repository's own transaction to end before the controller method returns. Do not write a test assuming “saveAndFlush only flushes and does not commit” without stating **which transaction it participates in**.

In the core example, `AccountService.register` has `@Transactional`; the repository's `saveAndFlush` joins that same service transaction, so an immediate exception occurs at flush, while the commit is executed by the service proxy after the method body.

## 7. ID generation alters INSERT timing

Hibernate supports several generators:

- `GenerationType.IDENTITY` usually must INSERT early to retrieve the primary key from the database, so a unique error can occur immediately during `persist/save`.
- `GenerationType.SEQUENCE` can fetch a sequence value beforehand while deferring the INSERT.
- `GenerationType.UUID` on Hibernate can generate the UUID on the Java side before INSERT, making it suitable for labs observing pending inserts.
- An assigned ID can make Spring Data `save` choose `merge` instead of `persist` if isNew/version is not configured; that affects SELECT/SQL behavior and timing conclusions.
- Hibernate JDBC batching can also alter when statements are sent, though it does not change constraint/transaction definitions.

**Do not build timing tests that unconsciously depend on the generator.** The sample uses `@GeneratedValue(strategy = GenerationType.UUID)` with Java `UUID` so two `save` calls before flush can be observed in Hibernate 6.x. If you switch to IDENTITY, you must re-evaluate the expected exception location.

## 8. Constraint types and when errors can appear

| Constraint | Example | Typical timing |
|---|---|---|
| `UNIQUE` | no duplicate email | Statement execution, or commit if deferrable-deferred |
| `PRIMARY KEY` | no duplicate id | Statement, or commit if DB supports deferrable |
| `FOREIGN KEY` | order.customer_id must exist | Statement, or commit if FK is deferrable-deferred |
| `NOT NULL` | email cannot be null | Usually at statement; Hibernate may block before SQL |
| `CHECK` | quantity > 0 | Usually at statement; PostgreSQL CHECK is not deferrable |
| Application validation | `@Email`, `@NotNull`/business rule | Before SQL, during validation |
| Optimistic locking | `@Version` stale update | At update/flush or commit sync |
| Trigger-defined constraint | Business validation in trigger | When trigger fires, depending on DB trigger |

In PostgreSQL, not every constraint supports `DEFERRABLE`: **UNIQUE, PRIMARY KEY, EXCLUDE, and FOREIGN KEY** support it; **NOT NULL and CHECK have no corresponding deferred form** in `CREATE TABLE`. PostgreSQL also has deferrable constraint triggers, which are a separate mechanism requiring dedicated DDL/tests.

### 8.1. SQLSTATE is more reliable than message strings

In PostgreSQL, several standard codes include:

| SQLSTATE | Common meaning |
|---|---|
| `23505` | unique_violation |
| `23503` | foreign_key_violation |
| `23502` | not_null_violation |
| `23514` | check_violation |
| `23P01` | exclusion_violation |
| `40001` | serialization_failure |
| `40P01` | deadlock_detected |

These codes help classify errors, but **an error's SQLSTATE alone is not always enough to identify the exact business constraint**: `23505` could be email, username, or primary key. Production code should inspect a reliable constraint name from the driver/Hibernate or use an explicit mapping; avoid returning “EMAIL_ALREADY_USED” for every unique failure in the system.

## 9. Bean Validation differs from database constraints

An entity with:

```java
@NotBlank
@Column(nullable = false)
private String email;
```

has **two distinct layers** of checking:

1. Bean Validation (`jakarta.validation.constraints.NotBlank`) runs when validation is enabled, possibly during pre-persist/update lifecycle events, raising `jakarta.validation.ConstraintViolationException`.
2. `@Column(nullable=false)` participates in metadata/schema generation and Hibernate nullability checks; the actual database `NOT NULL` constraint is the last line of defense and can raise `SQLException`.

**Two similarly named exceptions are not identical:**

- `jakarta.validation.ConstraintViolationException`: Bean Validation, with a set of violations.
- `org.hibernate.exception.ConstraintViolationException`: Hibernate database/JDBC integrity violation.
- `org.springframework.dao.DataIntegrityViolationException`: Spring DataAccessException translation category, which may wrap a Hibernate/JDBC cause.

If you want to prove the **database** rejects null/check data, test DDL/driver/JDBC against an appropriate DB instead of only asserting that `@NotBlank` catches the error before SQL. Do not add Bean Validation into the H2 unique demo and accidentally prevent the test from reaching the database.

## 10. SQL constraints can differ between H2 and PostgreSQL

H2 is very useful for fast JPA mapping/repository tests, yet it differs in:

- SQL dialect, index names, execution plans, and generated DDL.
- Locking/isolation, concurrency, and transaction semantics.
- Sequence/identity behavior, timestamps, and case/collation.
- Partial indexes, expression indexes, and materialized views.
- PostgreSQL `DEFERRABLE INITIALLY DEFERRED` and `SET CONSTRAINTS`.
- Constraint names, exception wrapping, and driver messages.
- Triggers/stored procedures, migrations, and schema permissions.

**Do not write an H2 test and conclude that a PostgreSQL commit-time deferred constraint has been verified.** The core H2 demo tests **flush-time immediate unique**; the dedicated PostgreSQL section executes real transactions/commits on the actual provider.

## 11. Runnable project: creating an account with a unique email

The demo application provides:

- `POST /api/accounts` with body `{"email":"Alice@Example.test"}`.
- The email is passed through `strip()` and lowercased with `Locale.ROOT`, so uppercase variants and extra whitespace produce the same canonical email.
- Empty email or one without a valid `@` per the demo's simple rule → HTTP `400`.
- New email → HTTP `201` with UUID `id` and normalized `email`.
- Duplicate email → JDBC unique violation; the service classifies `SQLSTATE 23505` and throws `DuplicateEmailException` so HTTP advice returns **409**.
- Other integrity errors are not disguised as “duplicate email”.
- There is a unique constraint `uk_customer_accounts_email` on table `customer_accounts`.
- The example does not rely on `repository.existsByEmail()` to guarantee uniqueness; the DB constraint is the final authority.

Note: Simple regex/email validation in this demo **is not RFC-compliant validation or email ownership verification**. It focuses strictly on observing when database constraints fail at flush/commit.

### 11.1. Directory tree

```text
jpa-constraint-timing/
  settings.gradle
  build.gradle
  src/main/java/com/example/constrainttiming/
    ConstraintTimingApplication.java
    CustomerAccount.java
    CustomerAccountRepository.java
    AccountService.java
    RegisterAccountRequest.java
    AccountCreated.java
    InvalidEmailException.java
    DuplicateEmailException.java
    AccountController.java
    ApiErrorAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/constrainttiming/
    AccountServiceTest.java
    CustomerAccountRepositoryFlushTest.java
    CustomerAccountCommitBoundaryTest.java
    AccountHttpIntegrationTest.java
```

Core tests do not require PostgreSQL or Docker. For PostgreSQL deferrable unique, see the dedicated SQL in section 29 and optional Testcontainers combination in section 30.

## 12. Gradle and test properties

**`settings.gradle`**

```groovy
rootProject.name = 'jpa-constraint-timing'
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

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/test/resources/application.properties`**

```properties
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

# Enable when diagnosing specific SQL (optional):
# logging.level.org.hibernate.SQL=DEBUG
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

For an H2 training database, `create-drop` creates the schema from annotations. **Do not use `ddl-auto=create-drop` on a production database.** Real projects use Flyway/Liquibase migrations, and integration tests must apply those exact migrations. Bind parameter logging can expose emails/sensitive data; enable it only in tests with synthetic data.

## 13. Spring Boot application

**`src/main/java/com/example/constrainttiming/ConstraintTimingApplication.java`**

```java
package com.example.constrainttiming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConstraintTimingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ConstraintTimingApplication.class, args);
    }
}
```

`@SpringBootApplication` in the root package ensures Spring Boot scans JPA entities/repositories/controllers/services in the right namespace. A `@DataJpaTest` builds only the JPA slice without loading the full web/controller layer.

## 14. Entity with UUID ID and unique constraint

**`src/main/java/com/example/constrainttiming/CustomerAccount.java`**

```java
package com.example.constrainttiming;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
        name = "customer_accounts",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_customer_accounts_email",
                columnNames = "email"))
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 160)
    private String email;

    protected CustomerAccount() {
        // Required by JPA
    }

    public CustomerAccount(String email) {
        this.email = email;
    }

    public UUID getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

**Why UUID?** Hibernate can assign the ID on the Java side so `save` does not need to send an INSERT immediately just to obtain a generated primary key. That makes comparing save/flush/commit in the lab much clearer. If replaced with IDENTITY, SQL may execute earlier; tests should verify the actual generator's behavior rather than forcing the initial assumption.

**Important:** `@Table(uniqueConstraints=...)` in this demo is used by Hibernate schema generation. With production migrations, do not trust annotations alone: verify the real table has the expected constraint name/columns/mode. For composite unique constraints or partial indexes, more detailed DDL and tests are required.

## 15. Repository, DTOs, and domain exceptions

**`src/main/java/com/example/constrainttiming/CustomerAccountRepository.java`**

```java
package com.example.constrainttiming;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, UUID> {

    Optional<CustomerAccount> findByEmail(String email);

    long countByEmail(String email);
}
```

**`src/main/java/com/example/constrainttiming/RegisterAccountRequest.java`**

```java
package com.example.constrainttiming;

public record RegisterAccountRequest(String email) {
}
```

**`src/main/java/com/example/constrainttiming/AccountCreated.java`**

```java
package com.example.constrainttiming;

import java.util.UUID;

public record AccountCreated(UUID id, String email) {
}
```

**`src/main/java/com/example/constrainttiming/InvalidEmailException.java`**

```java
package com.example.constrainttiming;

public class InvalidEmailException
        extends IllegalArgumentException {
}
```

**`src/main/java/com/example/constrainttiming/DuplicateEmailException.java`**

```java
package com.example.constrainttiming;

public class DuplicateEmailException
        extends RuntimeException {

    public DuplicateEmailException(Throwable cause) {
        super("Email address already exists", cause);
    }
}
```

`DuplicateEmailException` is a public domain exception; the original cause stays in controlled server logs rather than serializing causes, raw SQL, or absolute paths into the HTTP response. When SQLSTATE is not `23505`, the demo does not blindly turn it into an email conflict.

## 16. Service: flushing explicitly to catch immediate unique at the right boundary

**`src/main/java/com/example/constrainttiming/AccountService.java`**

```java
package com.example.constrainttiming;

import java.sql.SQLException;
import java.util.Locale;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final CustomerAccountRepository repository;

    public AccountService(CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public AccountCreated register(String email) {
        String normalized = normalize(email);

        try {
            CustomerAccount saved = repository.saveAndFlush(
                    new CustomerAccount(normalized));

            // DB immediate constraint has been checked by the flush.
            // The enclosing service transaction has NOT committed yet.
            return new AccountCreated(
                    saved.getId(), saved.getEmail());

        } catch (DataIntegrityViolationException failure) {
            if (hasSqlState(failure, "23505")) {
                // Throw a new RuntimeException so Spring rolls back.
                throw new DuplicateEmailException(failure);
            }
            throw failure;
        }
    }

    private String normalize(String email) {
        if (email == null) {
            throw new InvalidEmailException();
        }

        String value = email.strip()
                .toLowerCase(Locale.ROOT);

        // Deliberately simple training validation, not RFC email parsing.
        if (value.isEmpty() || value.length() > 160
                || value.indexOf('@') < 1
                || value.endsWith("@")) {
            throw new InvalidEmailException();
        }

        return value;
    }

    private boolean hasSqlState(
            Throwable throwable, String state) {

        for (Throwable cause = throwable;
             cause != null;
             cause = cause.getCause()) {

            if (cause instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }

        return false;
    }
}
```

**Why catch immediately after `saveAndFlush`?** With H2 immediate uniqueness, INSERT runs at flush, and the repository proxy translates the DB error into `DataIntegrityViolationException`. The service classifies SQLSTATE 23505 and throws the domain exception. The service transaction is rolled back because of the unchecked exception. Controller advice can then map it to 409.

**Intentional limitation:** Relying solely on SQLSTATE `23505` does not identify which unique constraint failed. In the demo, the table has only one unique business constraint (email), so this mapping works for learning. In production, you should inspect the **reliable constraint name** via Hibernate/driver (with a safe fallback) or use constraint-specific operation/exception mapping; do not turn every 23505 (including primary key) into a duplicate email.

**Important for PostgreSQL deferred constraints:** `saveAndFlush` might **not throw** with `DEFERRABLE INITIALLY DEFERRED`. The commit error will happen **after the method body returns**, inside Spring's transaction interceptor/proxy, so the `catch` above will **not necessarily catch it**. For deferred constraints, error mapping must live at a boundary wrapping transaction execution (controller advice or orchestration outside the transaction), paired with integration tests that perform real commits; see sections 28–31.

### 16.1. Do not swallow exceptions and keep committing

Anti-pattern:

```java
@Transactional
public boolean registerAndIgnore(String email) {
    try {
        repository.saveAndFlush(new CustomerAccount(email));
        return true;
    } catch (DataIntegrityViolationException ignored) {
        return false; // Transaction may already be marked rollback-only.
    }
}
```

After a database failure, the JDBC transaction (especially in PostgreSQL) can be aborted; the Spring transaction can also be marked rollback-only. Continuing to query or commit can throw `UnexpectedRollbackException` or secondary SQL errors. Design **clear transaction boundaries and let exceptions propagate**, or handle retries in a **new transaction** outside the failed one, with idempotency and bounded attempts.

## 17. Controller and HTTP advice

**`src/main/java/com/example/constrainttiming/AccountController.java`**

```java
package com.example.constrainttiming;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<AccountCreated> register(
            @RequestBody RegisterAccountRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.register(request.email()));
    }
}
```

**`src/main/java/com/example/constrainttiming/ApiErrorAdvice.java`**

```java
package com.example.constrainttiming;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ApiError(String code) {
    }

    @ExceptionHandler(InvalidEmailException.class)
    public ResponseEntity<ApiError> invalidEmail() {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_EMAIL"));
    }

    @ExceptionHandler(DuplicateEmailException.class)
    public ResponseEntity<ApiError> duplicateEmail() {
        return ResponseEntity.status(409)
                .body(new ApiError("EMAIL_CONFLICT"));
    }
}
```

**Timing distinction:** The controller calls `service.register(...)` through a Spring proxy. For a transaction created by the service, the proxy returns control to the controller only after transaction completion succeeds. If commit fails, the controller never receives `AccountCreated` normally. HTTP 201 should only be returned after the service call completes; this sample does not use asynchronous fire-and-forget writes.

The advice sample only maps domain exceptions. If a deferred constraint throws `TransactionSystemException` / `DataIntegrityViolationException` at commit, 409 mapping may need to be designed at a boundary outside the transaction based on reliable error classification—do not assume the code above already handles every commit-time variant.

## 18. Unit test for normalization and error classification

**`src/test/java/com/example/constrainttiming/AccountServiceTest.java`**

```java
package com.example.constrainttiming;

import java.sql.SQLException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AccountServiceTest {

    @Mock
    CustomerAccountRepository repository;

    AccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountService(repository);
    }

    @Test
    void normalizesEmailBeforeSave() {
        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenAnswer(call -> call.getArgument(0));

        AccountCreated result = service.register(
                "  Alice@Example.test  ");

        ArgumentCaptor<CustomerAccount> saved =
                ArgumentCaptor.forClass(CustomerAccount.class);
        verify(repository).saveAndFlush(saved.capture());

        assertEquals("alice@example.test", result.email());
        assertEquals(
                "alice@example.test", saved.getValue().getEmail());
        // ID generation is not run in a Mockito-only unit test.
    }

    @Test
    void invalidEmailNeverCallsRepository() {
        assertThrows(InvalidEmailException.class,
                () -> service.register("  "));

        verifyNoInteractions(repository);
    }

    @Test
    void uniqueSqlStateBecomesDomainConflict() {
        DataIntegrityViolationException duplicate =
                new DataIntegrityViolationException(
                        "integrity failure",
                        new SQLException("duplicate", "23505"));

        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenThrow(duplicate);

        DuplicateEmailException error = assertThrows(
                DuplicateEmailException.class,
                () -> service.register("same@example.test"));

        assertEquals(duplicate, error.getCause());
    }

    @Test
    void foreignKeySqlStateDoesNotBecomeEmailConflict() {
        DataIntegrityViolationException other =
                new DataIntegrityViolationException(
                        "integrity failure",
                        new SQLException("missing parent", "23503"));

        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenThrow(other);

        assertThrows(DataIntegrityViolationException.class,
                () -> service.register("other@example.test"));
    }
}
```

These **4 unit tests** do not start a Spring context or DB. They verify canonicalization, rejecting invalid input, and classifying errors by SQLSTATE in the cause chain. They **do not prove H2/PostgreSQL actually emits that SQLSTATE**, because the `SQLException` was constructed by Mockito. That is the job of the JPA/DB tests that follow.

**ID note:** Mockito returns the entity without going through Hibernate, so `getId()` can be null; the unit test does not assert a generated ID. Integration JPA/HTTP tests verify that the UUID is generated.

## 19. Repository slice test: unique violation exposed at flush

**`src/test/java/com/example/constrainttiming/CustomerAccountRepositoryFlushTest.java`**

```java
package com.example.constrainttiming;

import jakarta.persistence.EntityManager;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class CustomerAccountRepositoryFlushTest {

    @Autowired
    CustomerAccountRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void validAccountIsQueryableAfterFlushAndClear() {
        String email = "ok-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount saved = repository.save(
                new CustomerAccount(email));

        assertNotNull(saved.getId());

        repository.flush();
        entityManager.clear();

        assertEquals(email, repository.findById(saved.getId())
                .orElseThrow().getEmail());
    }

    @Test
    void twoSavesMayFinishBeforeUniqueFailureAtFlush() {
        String email = "duplicate-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount first = repository.save(
                new CustomerAccount(email));
        CustomerAccount second = repository.save(
                new CustomerAccount(email));

        // UUIDs were assigned before the pending INSERTs.
        assertNotNull(first.getId());
        assertNotNull(second.getId());

        // Immediate database UNIQUE violation happens during SQL flush.
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.flush());

        // No further JPA queries in this failed transaction.
        // @DataJpaTest's test transaction rolls back after the method.
    }

    @Test
    void saveAndFlushMakesSecondViolationImmediate() {
        String email = "early-" + UUID.randomUUID()
                + "@example.test";

        repository.saveAndFlush(new CustomerAccount(email));

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CustomerAccount(email)));
    }
}
```

**3 JPA slice tests.** H2 has an immediate unique constraint, and Hibernate's UUID ID generator allows `save` to create managed entities before INSERT. The second test intentionally catches the error only at `repository.flush()`; after a failed flush, the transaction must roll back—**do not run further queries or repository calls on a failed transaction**.

`@DataJpaTest` **rolls back the transaction by default** after each test method, so these test emails/rows are not committed and do not need `deleteAll()`. However, default rollback can also mask a constraint that is only checked **at commit**; therefore, the test in section 20 opts out of the test-managed transaction and uses `TransactionTemplate` to commit explicitly.

### 19.1. Why must `assertThrows` wrap flush?

Wrong:

```java
// Anti-pattern: may FAIL because save has not sent the INSERT yet.
assertThrows(DataIntegrityViolationException.class,
        () -> repository.save(new CustomerAccount(duplicate)));
```

Better when testing an immediate unique constraint:

```java
repository.save(new CustomerAccount(duplicate));
assertThrows(DataIntegrityViolationException.class,
        () -> repository.flush());
```

These are snippets. With `GenerationType.IDENTITY` or pre-SQL validation, `save` may already throw, so align tests with the actual fixture/generator/DB rather than forcing all tests to look like the UUID example.

## 20. Commit-boundary test: callback succeeds but transaction commit fails

**`src/test/java/com/example/constrainttiming/CustomerAccountCommitBoundaryTest.java`**

```java
package com.example.constrainttiming;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class CustomerAccountCommitBoundaryTest {

    @Autowired
    CustomerAccountRepository repository;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void commitFlushFailsAfterCallbackCompletes() {
        String email = "commit-" + UUID.randomUUID()
                + "@example.test";

        AtomicBoolean reachedEndOfCallback =
                new AtomicBoolean(false);

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        assertThrows(RuntimeException.class,
                () -> tx.execute(status -> {

                    repository.save(new CustomerAccount(email));
                    repository.save(new CustomerAccount(email));

                    // Hibernate UUID generator may not need INSERT yet.
                    reachedEndOfCallback.set(true);
                    return null;
                }));

        assertTrue(reachedEndOfCallback.get(),
                "Work callback completed before commit failed");

        // The transaction was rolled back; query in a new boundary.
        assertEquals(0L, repository.countByEmail(email));
    }
}
```

**1 commit-boundary test.** `@Transactional(propagation = NOT_SUPPORTED)` disables the test-managed transaction that `@DataJpaTest` creates by default. `TransactionTemplate.execute` starts a transaction, runs the callback, and then performs commit **after the callback returns**. With the Hibernate UUID generator and H2 immediate unique, pending SQL INSERTs can be flushed **during the commit step**; the callback completed normally, yet commit throws an exception. `AtomicBoolean` shows that the callback itself was not where the failure occurred.

**Do not confuse the mechanisms:** In this test, the unique constraint is still **immediate**; it only surfaces at commit because Hibernate **had not flushed SQL beforehand**. This differs from PostgreSQL deferred unique constraints, where SQL has already executed at flush but **the database deliberately waits until commit to evaluate it**. Both cases appear as “fails at commit”, yet the fixes and test approaches differ.

### 20.1. Exception types at commit may vary

Do not hard-code that every commit error is `DataIntegrityViolationException` where the test calls `TransactionTemplate.execute`. Spring `JpaTransactionManager`/ORM can wrap or translate it into `DataIntegrityViolationException`, `TransactionSystemException`, or another `RuntimeException` depending on root cause and timing. The core test catches `RuntimeException` to verify that commit **did not succeed**, then checks that the callback finished and the data does not exist. For deeper diagnosis, inspect the root `SQLException`/SQLSTATE and Hibernate constraint name in the cause chain.

**Do not indiscriminately apply a “catch RuntimeException” pattern** to verify domain business errors: public API tests must still assert exact contract errors; this core test is specifically for observing the *commit boundary*.

## 21. Full HTTP integration: unique violation must never return 201

**`src/test/java/com/example/constrainttiming/AccountHttpIntegrationTest.java`**

```java
package com.example.constrainttiming;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AccountHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    CustomerAccountRepository repository;

    private final List<UUID> ownedIds = new ArrayList<>();

    private String uniqueEmail() {
        return "http-" + UUID.randomUUID() + "@example.test";
    }

    private AccountCreated create(String email) {
        ResponseEntity<AccountCreated> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest(email),
                        AccountCreated.class);

        assertEquals(201, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().id());
        ownedIds.add(response.getBody().id());
        return response.getBody();
    }

    @AfterEach
    void removeOnlyRowsCreatedByThisTest() {
        for (UUID id : ownedIds) {
            repository.deleteById(id);
        }
    }

    @Test
    void firstInsertPersistsCanonicalEmail() {
        String email = uniqueEmail();
        AccountCreated created = create(
                "  " + email.toUpperCase() + "  ");

        assertEquals(email, created.email());
        assertEquals(email, repository.findById(created.id())
                .orElseThrow().getEmail());
    }

    @Test
    void secondInsertOfSameEmailReturns409AndNoExtraRow() {
        String email = uniqueEmail();
        create(email);

        ResponseEntity<ApiErrorAdvice.ApiError> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest(email),
                        ApiErrorAdvice.ApiError.class);

        assertEquals(409, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("EMAIL_CONFLICT",
                response.getBody().code());
        assertEquals(1L, repository.countByEmail(email));
    }

    @Test
    void invalidEmailReturns400WithoutPersistingData() {
        long before = repository.count();

        ResponseEntity<ApiErrorAdvice.ApiError> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest("   "),
                        ApiErrorAdvice.ApiError.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_EMAIL",
                response.getBody().code());
        assertEquals(before, repository.count());
    }
}
```

**3 HTTP integration tests** running an embedded server on a random TCP port, with real controller/service/repository/H2. The unique error from `saveAndFlush` is not swallowed, the Spring transaction rolls back, and controller advice returns HTTP 409. The second test also asserts that the database contains only **one** record with that email, rather than only asserting the response status.

**Scope:** This tests integration with H2 immediate uniqueness; it does not prove PostgreSQL deferred uniqueness. Test data uses unique UUIDs and `@AfterEach` deletes only the rows created by that test. There is no class-level `@Transactional`: HTTP requests execute on a server thread, outside any test-thread rollback transaction.

## 22. Total number of test methods in the H2 demo

| Test class | `@Test` count | Evidence |
|---|---:|---|
| `AccountServiceTest` | 4 | Normalization and SQLSTATE classification unit tests |
| `CustomerAccountRepositoryFlushTest` | 3 | Immediate unique on flush/saveAndFlush |
| `CustomerAccountCommitBoundaryTest` | 1 | Auto-flush during commit after callback |
| `AccountHttpIntegrationTest` | 3 | Real HTTP, rollback, 201/400/409, and DB state |
| **Total** | **11** | Distinguishing pending SQL/flush/commit and public contract |

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

A Gradle Wrapper is needed in the project; if absent, generate it using an appropriate Gradle/IDE setup. The **expected** result when dependencies/JDK 17+/Gradle are configured properly is `BUILD SUCCESSFUL`, with reports at `build/reports/tests/test/index.html`. **The code has been reviewed but Gradle/JUnit has not been executed on a real repository**; do not treat this expectation as an execution report.

Assertions focus on exception type/SQLSTATE/business state, **not exact Hibernate SQL log text**, method ordering, UUID values, or raw database error messages.

## 23. Why can a rolled-back test produce a “false green”?

Counterexample:

```java
@DataJpaTest
class MisleadingTest {

    @Autowired
    CustomerAccountRepository repo;

    @Test
    void apparentlySavedTwice() {
        repo.save(new CustomerAccount("same@example.test"));
        repo.save(new CustomerAccount("same@example.test"));
        // No flush, no query, test finishes.
        // @DataJpaTest rolls back; SQL may never have run.
    }
}
```

The test neither asserts a constraint nor requires a commit. It can finish normally because rollback discards pending work. Thus a comment claiming “two saves succeeded” does not prove the database accepted uniqueness.

**Fixes by goal:**

- Test **immediate constraint** → `repository.flush()` or `saveAndFlush` in the test.
- Test **deferred constraint** → the transaction must **actually commit** on PostgreSQL, not merely flush.
- Test HTTP contract → invoke the real service/controller across the boundary and assert 409 + database unchanged.
- Test rollback after error → catch the error and query state in a new transaction.
- Test concurrency uniqueness → two independent transactions, data race synchronized via barriers/latches.

If a test uses `@Rollback(false)` or `@Commit` to force a commit, it can pollute the test DB; use an isolated database/schema, explicit cleanup, and managed lifecycles. `TestTransaction` or `TransactionTemplate` helps place assertions around the exact transaction boundary instead of hoping an exception surfaces outside the test method when a listener commits.

## 24. `TestTransaction`: explicit commit in Spring transactional tests

Spring Framework provides `org.springframework.test.context.transaction.TestTransaction` for tests with a test-managed transaction. It allows flagging commit/rollback and ending the transaction **right inside the method** to assert the outcome, rather than waiting for post-test listeners.

Illustrative snippet for `@DataJpaTest` (not a standalone runnable file):

```java
@Test
void forcedCommitFailsInsideTest() {
    repository.save(new CustomerAccount("demo@example.test"));
    repository.save(new CustomerAccount("demo@example.test"));

    TestTransaction.flagForCommit();

    assertThrows(RuntimeException.class, TestTransaction::end);

    // Do not continue using the failed transaction.
}
```

You need to import `TestTransaction`, `Test`, `assertThrows`, and have the appropriate repository fixture. `TestTransaction.end()` terminates the flagged test transaction; errors can arise during flush/commit. This is useful for verifying **real commits** in Spring tests, though it alters the lifecycle: after `end()`, there is no active test transaction until `TestTransaction.start()`; do not keep querying inside a failed transaction.

**In the runnable demo**, we choose `TransactionTemplate` with method-level `Propagation.NOT_SUPPORTED` so the commit boundary is clearer and does not depend on `@DataJpaTest`'s test-managed transaction.

## 25. Flush is not commit and rollback still takes effect

Suppose:

```text
BEGIN TRANSACTION
save(account A)
flush()   -> INSERT A has run and the database sees A in this transaction
ROLLBACK  -> A does not exist after rollback
```

A successful `flush()` only confirms the database accepted the SQL **at that moment**. You must not report “permanently saved” before the transaction commits. Commit-time errors can still come from:

- PostgreSQL deferred constraints.
- Serialization failures and deadlocks.
- Network/connection errors during commit.
- Resource manager/JTA issues.
- DB transaction timeout or lock timeout.
- A transaction already marked rollback-only.
- Deferred constraint triggers.

**A test catching an exception at flush still does not cover all errors that can occur at commit.** For services requiring strong consistency, test transaction boundaries and verify state after commit/rollback, not only entity state inside the persistence context.

## 26. Unique errors and “check-before-write” still race

Common counterexample:

```java
if (!repository.existsByEmail(email)) {
    repository.save(new CustomerAccount(email));
}
```

Two concurrent requests can both observe `existsByEmail=false`, both INSERT, and one transaction suffers a unique violation. Prechecking is a UX optimization, **not a uniqueness guarantee**.

```text
Transaction T1                 Transaction T2
--------------                 --------------
exists(email)=false            exists(email)=false
save(email)                    save(email)
flush / commit                 flush / commit
SUCCESS                        UNIQUE VIOLATION
```

Depending on isolation/DB locks, the second transaction may **wait** for the first transaction and then fail after T1 commits. A concurrency integration test must use a real database, synchronization barriers, adequate connection pools, and finite timeouts; do not rely on `Thread.sleep` to “hope” two threads arrive together. With production PostgreSQL, test the actual unique index/DDL from migrations.

**Do not retry endlessly** on every 23505. If the request carries an idempotency key, returning the already-created result may make sense; if the business rule is “email already exists”, 409 may be appropriate. Every decision needs a clear contract—never use a precheck to replace an integrity constraint.

## 27. Immediate and deferred constraints in PostgreSQL

PostgreSQL defines:

- `NOT DEFERRABLE` (default): checked per statement, cannot be postponed to transaction end.
- `DEFERRABLE INITIALLY IMMEDIATE`: can be switched to deferred inside a transaction via `SET CONSTRAINTS`; checked immediately by default.
- `DEFERRABLE INITIALLY DEFERRED`: checked at transaction commit unless switched to immediate.
- `SET CONSTRAINTS ALL IMMEDIATE` forces pending violations to be checked when that command executes instead of waiting for commit.
- Not every constraint allows deferral: PostgreSQL supports it only for certain types such as UNIQUE/PK/FK/EXCLUDE, not CHECK/NOT NULL.

**Fundamental difference:** With a deferred UNIQUE constraint, `entityManager.flush()` can succeed because the database **has not been asked to check uniqueness yet**, not because Hibernate failed to send SQL. A test like `assertThrows(..., entityManager::flush)` can fail (no exception thrown), while committing the transaction will fail.

**Do not expect H2 to accurately emulate this DDL.** Use a real PostgreSQL instance/container for tests covering deferrable constraints.

## 28. PostgreSQL lab: error appears only at COMMIT even though both INSERTs succeed

The following commands run in a **PostgreSQL test database**, such as a `psql` console. Do not run them against a production DB. Use a temporary table in the current session so application tables are untouched.

```sql
CREATE TEMP TABLE deferred_accounts (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    CONSTRAINT uk_deferred_accounts_email
        UNIQUE (email) DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

INSERT INTO deferred_accounts (id, email)
VALUES (1, 'same@example.test');

INSERT INTO deferred_accounts (id, email)
VALUES (2, 'same@example.test');

-- Both INSERTs can succeed even though the email is duplicated.
-- The database holds the pending uniqueness check until commit.

COMMIT;
-- ERROR: duplicate key value violates unique constraint
--        "uk_deferred_accounts_email"
-- SQLSTATE 23505.
-- The transaction does not commit; both INSERTs are rolled back.
```

**Observed outcomes to prove:**

1. Both INSERTs executed without throwing an immediate error.
2. The error occurred at `COMMIT`.
3. The unique error code is `23505`; the exact localized message may vary by version/locale.
4. Rows from the failed transaction are not committed.
5. When re-running in the same `psql` session, the temporary table still exists (because DDL ran before BEGIN), while data from the failed transaction does not exist.

### 28.1. Pulling the error forward with SET CONSTRAINTS IMMEDIATE

After the transaction above has failed/rolled back, start a new transaction:

```sql
BEGIN;

INSERT INTO deferred_accounts (id, email)
VALUES (10, 'new@example.test');

INSERT INTO deferred_accounts (id, email)
VALUES (11, 'new@example.test');

SET CONSTRAINTS uk_deferred_accounts_email IMMEDIATE;
-- Error 23505 can be detected IMMEDIATELY at SET CONSTRAINTS.
-- The transaction enters an aborted state; ROLLBACK is required.

ROLLBACK;
```

`SET CONSTRAINTS ... IMMEDIATE` does not commit on its own; it changes the **checking timing** and checks the corresponding pending changes. It is a diagnostic tool inside a transaction when you want to detect deferred constraint violations before commit, but it should not be applied indiscriminately to override application semantics; for workflows that legitimately allow temporary violations inside a transaction before fixing them prior to commit, forcing immediate checking too early breaks valid behavior.

### 28.2. What happens if JPA saveAndFlush targets this PostgreSQL table?

If Hibernate maps an entity to a table with a `DEFERRABLE INITIALLY DEFERRED` unique constraint inside an active transaction:

```text
repository.save(...)
entityManager.flush()   -> INSERT runs and is temporarily accepted by PostgreSQL
service method returns  -> no error yet
commit                  -> PostgreSQL checks deferred unique, ERROR 23505
```

Therefore, tests must assert at the **transaction commit boundary**. If a service catches `DataIntegrityViolationException` only around `saveAndFlush`, that catch block may **never run** because Spring's transaction proxy performs the commit after the method body finishes. This is one reason DB errors sometimes appear only in integration tests rather than unit/mocked repository tests.

## 29. Production DDL: migrations must reflect the real constraint mode

Entity annotations have no portable syntax to express every PostgreSQL deferrable constraint. In practice, a Flyway/Liquibase migration might use:

```sql
CREATE TABLE customer_accounts (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL
);

ALTER TABLE customer_accounts
    ADD CONSTRAINT uk_customer_accounts_email
    UNIQUE (email)
    DEFERRABLE INITIALLY DEFERRED;
```

This is a PostgreSQL DDL example, **not the schema for the H2 runnable demo**. Applying this migration in a project that also lets Hibernate generate a duplicate unique constraint with the same name will cause a conflict; production should treat migrations as the single source of truth for schema, typically setting `ddl-auto=validate`/none appropriately rather than letting Hibernate auto-create tables and then altering them redundantly.

**Caution:** PostgreSQL does not allow a deferrable unique constraint to serve as the arbiter in an `INSERT ... ON CONFLICT` clause. If your system uses upsert/`ON CONFLICT(email)`, changing the unique constraint to DEFERRABLE can break the upsert path. Choose deferrable for a real business requirement involving temporary inconsistent state, not simply to postpone errors to commit.

## 30. PostgreSQL integration test with JDBC/Testcontainers: the right approach

To automate testing commit-only behavior, add a **separate** test running against real PostgreSQL via Testcontainers, JDBC, and JUnit. Unlike the H2 demo, this test requires a Docker runtime and Testcontainers/Postgres driver dependencies.

**Optional** extra dependencies, not present in the core `build.gradle` in section 12:

```groovy
// Add to dependencies when PostgreSQL container tests are enabled.
testImplementation 'org.testcontainers:postgresql:1.21.3'
testImplementation 'org.testcontainers:junit-jupiter:1.21.3'
testRuntimeOnly 'org.postgresql:postgresql'
```

**Illustrative snippet** example (not part of the 11 core test methods; requires appropriate imports and file setup):

```java
// Requires org.testcontainers.junit.jupiter.Container/Testcontainers;
// PostgreSQLContainer and java.sql imports.
@Testcontainers
class DeferredUniqueJdbcTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    @Test
    void duplicatesFailOnlyWhenCommitting() throws Exception {
        try (Connection setup = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
             Statement ddl = setup.createStatement()) {

            ddl.execute("""
                CREATE TABLE deferred_email_probe (
                  id integer primary key,
                  email text not null,
                  CONSTRAINT uk_probe UNIQUE(email)
                    DEFERRABLE INITIALLY DEFERRED
                )
                """);
        }

        try (Connection conn = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword())) {

            conn.setAutoCommit(false);

            try (PreparedStatement insert =
                    conn.prepareStatement(
                        "INSERT INTO deferred_email_probe"
                        + " (id, email) VALUES (?, ?)")) {

                insert.setInt(1, 1);
                insert.setString(2, "same@example.test");
                insert.executeUpdate();

                insert.setInt(1, 2);
                insert.setString(2, "same@example.test");
                insert.executeUpdate();
            }

            SQLException error = assertThrows(
                    SQLException.class, conn::commit);

            assertEquals("23505", error.getSQLState());
            conn.rollback();
        }
    }
}
```

**Scope of this snippet:** It uses **plain JDBC** to isolate PostgreSQL deferred semantics from Hibernate's flush queue; both `executeUpdate()` calls genuinely send SQL, and the error comes from `Connection.commit()`. Running it requires adding JUnit/Testcontainers/`java.sql` imports, a JVM test runner, and Docker. The test creates its table inside a test-owned container and must never point to any other real database. When you want to test **Spring/JPA commit exception translation**, add a `@SpringBootTest` or JPA slice with a transaction manager targeting **that PostgreSQL container** via `@ServiceConnection`/`@DynamicPropertySource` and the corresponding migration.

**Never label an H2 unit test as having verified a PostgreSQL commit-time deferrable constraint.** The two tests answer different questions.

## 31. JPA flush vs JDBC commit: what evidence actually counts?

A reliable diagnosis should state:

| Observation | Valid conclusion | Not yet proven |
|---|---|---|
| `save()` throws no error | The current `save` call finished normally | SQL has run, or constraint passed |
| `flush()` throws no error | Pending SQL was sent validly under the current transaction/provider | Commit will succeed |
| `flush()` throws unique error | Immediate constraint/triggers violated when SQL ran | Every constraint in the DB is immediate |
| `commit()` throws unique error after successful flush | Commit-time validation or another state/transaction failed | Cause is definitely deferred unique if DDL has not been checked |
| `@DataJpaTest` rollback passes | Code inside the test and rollback threw no visible error | Commit-time constraints will pass |
| `RANDOM_PORT` test returns HTTP 409 | App mapping/call path returned conflict in the test topology | Production DB/migrations match H2 |
| Querying entity in same context sees changed field | Java managed state changed | Another DB transaction can see the commit |
| Querying after commit sees row | Write transaction committed and row is visible to that query | Exactly-once under concurrent requests |
| PostgreSQL JDBC commit throws 23505 on deferred unique | Constraint deferral really checked at commit | Spring 409 exception mapping is correct |

## 32. Using logging/diagnostics to locate the root cause

Enable selectively in test environments:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa=DEBUG
```

**Do not enable bind TRACE on production logs containing emails, tokens, PII, or payment data.** For CI training, use synthetic emails and ensure artifacts do not leak secrets.

Log-reading method:

1. Find where the entity is persisted/merged and identify its ID generator.
2. Check whether `INSERT/UPDATE/DELETE` appears before the exception line.
3. If no SQL appears before `save`, check flush mode, batching, and transaction boundaries.
4. If SQL runs and an exception follows at `flush`, look for immediate constraints/foreign keys/checks.
5. If flush succeeds and commit fails, check **deferrable DDL**, isolation/locks/deadlocks/JTA.
6. Locate SQLSTATE, constraint name, root SQLException, and exception translation layers.
7. Determine whether the transaction rolled back or was marked rollback-only; do not keep querying through a failed session.
8. Query state after rollback in a new connection/transaction to prove there are no partial writes.
9. If only CI fails, compare database engine/version/schema migrations/parallel jobs.
10. If a query “unexpectedly makes save fail”, check query-triggered auto-flush.

### 32.1. Stack traces show which layer raised the error

A stack trace may mention:

- `SimpleJpaRepository.save` / `EntityManager.persist`: persistence call/generator.
- `SessionImpl.flush` / `DefaultFlushEventListener`: flush synchronization.
- `JpaTransactionManager.doCommit`: transaction completion.
- `TransactionInterceptor.invoke`: AOP transactional boundary.
- `org.hibernate.exception.ConstraintViolationException`: JDBC integrity error.
- `org.springframework.dao.DataIntegrityViolationException`: Spring translated exception.
- `org.springframework.transaction.UnexpectedRollbackException`: the transaction was already rollback-only when the outer flow tried to commit.

**Do not draw conclusions solely from the class at the top of the stack trace**; read the cause chain, SQLSTATE, constraint name, and preceding operations.

## 33. Common mistakes when writing assertThrows

| Anti-pattern | Consequence | Replacement |
|---|---|---|
| Wrapping only `save` when SQL is deferred | Assertion misses the exception | Flush or commit at the right milestone |
| Using `assertDoesNotThrow(save)` to prove uniqueness | False confidence | Constraint violation test |
| Calling `entityManager.clear` before flush | Pending unsent changes are lost | Flush before clear when needed |
| Catching any `RuntimeException` and treating it as constraint | Masks logic bugs | Assert SQLSTATE/type/root cause |
| Querying the DB inside a transaction after a failed flush | Poisoned transaction, secondary errors | Roll back; query in a new transaction |
| Catching unique error without checking rollback | Partial side effects may remain | Assert DB state after failure |
| Asserting exact English error message text | Database/provider locale differs | SQLSTATE/constraint name/category |
| Assuming `saveAndFlush` always commits | Wrong outer transaction boundary | Separate flush vs commit |
| Using `@DataJpaTest` rollback to test deferred commit | Never actually commits | TransactionTemplate/TestTransaction |
| Using H2 to test PostgreSQL DEFERRABLE | Semantics differ | PostgreSQL Testcontainers |
| `@Transactional` on HTTP test expecting server rollback | Different threads/transactions | Scoped cleanup |
| Swallowing integrity error in `@Transactional` | Rollback-only, UnexpectedRollback | Propagate; handle outside transaction |
| Only calling `existsByEmail` before insert | Concurrent request race | DB UNIQUE + conflict mapping |
| Mapping every `23505` to duplicate email | Confuses other unique constraints | Inspect constraint name |
| Ignoring SQL flush mode/ID generator | Non-reproducible test timing | Pin config/DDL/ID strategy |
| Using `REQUIRES_NEW` casually to “force save” | Breaks outer transaction atomicity | Use only with an explicit requirement |
| Asserting only managed entity fields in tests | Does not verify persisted state | Flush/clear/new-transaction readback |
| Leaving `ddl-auto=create-drop` in production | Risks destroying data | Migrations and validate |
| Running Postgres tests against a shared DB | Data/test tables pollute others | Isolated container/schema |

## 34. When should flush be placed in a service and when should it not?

`saveAndFlush` is useful when business logic needs to detect an immediate database violation **before taking the next step** in the same transaction—for instance, checking uniqueness before building a response or performing a step with non-transactional side effects. However:

- Flushing has overhead and affects batching.
- Flushing does not commit; deferred errors can still occur at commit.
- External side effects (email/Kafka/HTTP) **do not roll back** if the transaction ultimately fails.
- “Send email after flush” is still dangerous because the database can roll back at commit; use transactional outbox/after-commit logic appropriately.
- Do not add flush to every repository method just to make tests pass; understand production write paths and performance.
- If you must reliably return 409, the transaction boundary must complete or error mapping must sit outside the transaction.
- For workflows that legitimately allow temporary uniqueness violations and fix them before commit, forcing flush/`SET CONSTRAINTS IMMEDIATE` may be inappropriate.
- Do not treat count/existence prechecks as a substitute for constraints.

**Design tip:** Keep transactions short, make database integrity the source of truth, normalize errors at a boundary where the transaction outcome has been definitively observed, and never let the API return 201 before commit. For message publishing, use an outbox/idempotency pattern to coordinate commit and external effects.

## 35. Data cleanup, test isolation, and concurrent execution

Essentials to ensure when testing database constraints:

1. Each test uses a `UUID`-based unique email/title unless **intentionally** creating duplicates.
2. `@DataJpaTest` rollback usually cleans up DB rows within the same test transaction.
3. Tests using `TransactionTemplate` that **succeed** in committing need explicit cleanup for test-owned rows.
4. A `RANDOM_PORT` HTTP server commits independently; clean up by created IDs.
5. Do not call `deleteAll()` on a shared DB/container/tenant if tests run in parallel.
6. Failed PostgreSQL transactions must roll back before reusing the connection.
7. If database migrations are the DDL source, tests must apply the exact migrations.
8. Container/schema ownership must be clear, especially if CI is killed mid-run.
9. DDL creating/modifying constraints can acquire locks; never run it on a DB serving live data.
10. Verify tests are order-independent and do not reuse fixed emails across CI jobs.

**Concurrency:** A UNIQUE violation when two transactions race does not necessarily occur at the exact same point under every thread schedule; use barriers, deadlines, and separate transactions rather than arbitrary `sleep` calls. A green local run does not guarantee production isolation levels/locking.

## 36. Troubleshooting by symptom

| Symptom | Common cause | Check |
|---|---|---|
| `save` succeeds, commit fails | Pending SQL auto-flush or deferred constraint | SQL trace, flush mode, DDL |
| `saveAndFlush` does not throw, commit fails | Deferred PostgreSQL unique/FK or another commit error | `pg_constraint.condeferrable`, SQLSTATE |
| `@DataJpaTest` passes but API fails | Test rollback never commits | TransactionTemplate or real HTTP |
| `assertThrows(save)` fails | INSERT has not run due to generator/flush | Use explicit flush |
| `save` throws immediately with IDENTITY | Early DB insert to retrieve ID | Verify strategy/generator |
| `repo.count()` throws unique violation | AUTO flush before query | SQL/query spaces and pending changes |
| Query finds entity while row is uncommitted | First-level cache/read-your-writes | Read in a new transaction |
| Duplicate API returns HTTP 500 instead of 409 | Commit exception type differs from service catch | Advice outside transaction, cause mapping |
| Duplicate returns 201, then server logs SQL error | Async write or response sent before commit | Ensure synchronous transaction completion |
| `UnexpectedRollbackException` after catch | Transaction already rollback-only | Do not swallow persistence errors |
| Unique test passes alone, fails in suite | Fixed email or leaked DB state | UUIDs, rollback, cleanup |
| H2 passes while Postgres fails | Dialect/DDL/constraint mode differs | Postgres Testcontainers |
| NOT NULL violation has no SQL log | Hibernate/Bean Validation blocked earlier | Cause type, validation config |
| Inserted and published event, then commit failed | Side effect outside DB transaction | Transactional outbox |
| Error message changes on CI | Driver/locale/DB version differs | SQLSTATE + constraint name |
| PostgreSQL connection keeps reporting 25P02 | Transaction aborted after prior error | Roll back before running new queries |

### 36.1. 10-step investigation workflow

1. Reproduce with a **minimal test fixture**, without real user data.
2. Identify the exception/root type, SQLSTATE, and constraint name.
3. Read the actual schema from migrations instead of relying purely on annotations.
4. Identify the ID strategy and provider/dialect.
5. Check which transaction boundary is active at each layer.
6. Place an explicit flush at the right test boundary when checking an immediate constraint.
7. If flush passes yet commit fails, inspect PostgreSQL DEFERRABLE constraints or other transaction failures.
8. Do not keep querying or continuing an aborted transaction; roll back and then verify postconditions.
9. Verify HTTP status/business contract outside the transaction proxy.
10. Explicitly record whether the result comes from an H2 flush test, commit test, or PostgreSQL deferred constraint test.

## 37. Practice exercises with answers

### A. Two saves, no flush

A test calls `repo.save(new Account(sameEmail))` twice, and then the method ends with rollback. Can you conclude UNIQUE passed?

**Answer:** No. SQL may never have executed; rollback discards pending actions. Use flush to test immediate uniqueness or a commit test to verify deferred constraints.

### B. Flush succeeds

`repository.saveAndFlush` completed with no exception. Can you report “the transaction is guaranteed to commit successfully”?

**Answer:** No. Flush does not commit; deferred constraints, deadlocks/isolation issues, and connection errors can still happen at commit.

### C. SQLSTATE 23505

Does every `23505` in the Orders schema mean a duplicate email?

**Answer:** No. It only indicates a unique violation; you need constraint/table/operation context to map the right business code.

### D. GenerationType.IDENTITY

A test that previously threw only at flush starts throwing immediately at `save` after switching the ID strategy to IDENTITY. Is this definitely a Hibernate regression?

**Answer:** No. IDENTITY typically requires an early INSERT to obtain the ID. Check the mapping, generated SQL, and test intent.

### E. @DataJpaTest rollback

You want to test a PostgreSQL deferred FK that only fails at commit, but `@DataJpaTest` rolls back by default. What should the test change?

**Answer:** Ensure a real commit using `TransactionTemplate` outside the test-managed transaction, `TestTransaction.flagForCommit/end`, or real HTTP/DB integration with dedicated cleanup.

### F. Flush and clear

You call `entityManager.clear()` right after `save()` without flushing. What can be lost?

**Answer:** Unsynchronized pending changes can be discarded when entities are detached; when the goal is persisted state, flush before clearing.

### G. Query triggers the error itself

`repo.findByEmail(...)` after two pending duplicates suddenly throws a unique error. Why?

**Answer:** Under AUTO flush, a related query can trigger a flush before executing the query.

### H. H2 and PostgreSQL

An H2 unique flush test passes, while Postgres uses DEFERRABLE INITIALLY DEFERRED. Can you use the H2 result to prove the error also happens at flush on Postgres?

**Answer:** No. Postgres can wait until commit even after SQL has run; you must test against the real provider/DDL.

### I. Catching errors inside the service

A service catches `DataIntegrityViolationException` and returns false inside `@Transactional`. Why might `UnexpectedRollbackException` still appear?

**Answer:** The transaction may already be rollback-only/aborted, so the outer interceptor cannot commit successfully. Handle outside the transaction or let the exception propagate.

### J. Checking postconditions

An API returns 409 on a duplicate, yet the test does not query the DB. What could it miss?

**Answer:** A side effect/partial write or broken transaction semantics where another row/data changed. Re-query in a new transaction and assert the exact record count.

### K. SET CONSTRAINTS IMMEDIATE

In PostgreSQL, two duplicate INSERTs into a deferrable unique column succeed; `SET CONSTRAINTS ALL IMMEDIATE` reports an error. What does that prove?

**Answer:** The database had deferred the check, and switching to immediate forced pending violations to be evaluated before commit.

### L. Precheck race

Two requests both see `existsByEmail=false`. What guarantees only one row gets created?

**Answer:** A database unique constraint (plus transaction semantics), with the application mapping conflicts/retries per policy. A precheck alone is not enough.

### M. Entity getter

After mutation, `getEmail()` returns the new value while the database row still holds the old one. Why?

**Answer:** Managed entity state in RAM differs from committed SQL state. Use flush/clear/new-transaction readback according to your test goal.

### N. Commit exception type

A provider throws `TransactionSystemException` instead of `DataIntegrityViolationException` at commit. Should you attach a global handler catching any RuntimeException → 409?

**Answer:** No. Inspect the cause/SQLSTATE/constraint name at a safe boundary; keep 500 for unclassified errors.

### O. Business side effect

A service sends an email after flush, and then commit fails due to a deferred constraint. The recipient got a confirmation email while the DB rolled back. How do you fix this?

**Answer:** Decouple side effects until after a successful commit using an outbox/after-commit delivery mechanism with retries, idempotency, and monitoring.

## 38. End-of-article checklist and references

### Checklist

- [ ] I distinguish between `save/persist`, pending SQL, flush, commit, and rollback.
- [ ] I know flush can run before queries or before commit, not only when called explicitly.
- [ ] I know ID generators/batching affect SQL execution timing.
- [ ] Tests for immediate unique constraints assert at the appropriate `flush/saveAndFlush` boundary.
- [ ] Tests for deferred constraints genuinely commit against a supporting database.
- [ ] I do not use `@DataJpaTest` rollback to conclude a deferred constraint will pass on commit.
- [ ] I know how to use `TransactionTemplate` or `TestTransaction` to commit explicitly in tests.
- [ ] I do not treat an entity getter or first-level-cache read as persisted state.
- [ ] After a flush error, the test stops running queries on the failed transaction.
- [ ] Post-rollback/commit state is queried in a new transaction.
- [ ] I do not substitute H2 for PostgreSQL when testing DEFERRABLE/migration-specific behavior.
- [ ] I know Postgres only allows DEFERRABLE on certain constraint types.
- [ ] I know `SET CONSTRAINTS IMMEDIATE` can pull pending violation checks forward.
- [ ] I distinguish Jakarta Bean Validation from Hibernate JDBC integrity exceptions.
- [ ] I know SQLSTATE 23505 only means unique, not which specific business constraint failed.
- [ ] HTTP 201 is not sent before the transaction outcome completes.
- [ ] API 409 is returned only when the relevant unique error is accurately identified.
- [ ] Persistence errors are not swallowed inside a rollback-only transaction.
- [ ] Duplicate prechecks are not used instead of a database unique constraint.
- [ ] Tests use synthetic, method-unique emails/IDs and scoped cleanup.
- [ ] No CREATE/ALTER/DROP constraints are run on a production database.
- [ ] SQL logs/bind TRACE do not expose sensitive data.
- [ ] Real tests provide SQL/SQLSTATE/DDL/transaction boundary evidence.
- [ ] Concurrent writes are tested when the feature faces races in production.
- [ ] The impact of flush on batching/performance and external side effects has been reviewed.
- [ ] QA conclusions distinguish code review from actually executed tests.

**Conclusion:** “Database constraint fails only after flush or commit” involves at least **two distinct mechanisms**: Hibernate deferring SQL until flush/commit, and a database like PostgreSQL **deferring evaluation of constraints on already-received SQL** until commit. Mechanically wrapping `assertThrows` around `save` misses both; only forcing `flush` is still insufficient when DDL uses deferrable constraints. Proper tests identify the **constraint type, generator, flush mode, transaction boundary, and DB provider**, flush or commit explicitly as appropriate, and then verify data after rollback/success. In Spring Boot, remember that `@DataJpaTest` rolls back by default, and controller/service transaction proxies can cause errors to surface **after the method body returns**.

### Official references

- Hibernate ORM — User Guide: Flushing, AUTO/COMMIT modes, query-triggered synchronization: https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing
- Hibernate ORM — Transactions and transactional write-behind: https://docs.hibernate.org/stable/orm/userguide/html_single/#transactions
- Spring Data JPA — JpaRepository `flush/saveAndFlush/saveAllAndFlush`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Spring Boot 3.5 — Testing Spring Boot applications, `@DataJpaTest` rollback and `RANDOM_PORT` transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — TransactionTemplate: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework 6.2 — Test-managed transactions, `TestTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework — DAO exception translation/DataAccessException: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- PostgreSQL 17 — `CREATE TABLE`, DEFERRABLE, constraint types: https://www.postgresql.org/docs/17/sql-createtable.html
- PostgreSQL 17 — `SET CONSTRAINTS`: https://www.postgresql.org/docs/17/sql-set-constraints.html
- PostgreSQL 17 — Error codes, Class 23 integrity constraint: https://www.postgresql.org/docs/17/errcodes-appendix.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Jakarta Persistence — EntityManager flush, persistence context semantics: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager
