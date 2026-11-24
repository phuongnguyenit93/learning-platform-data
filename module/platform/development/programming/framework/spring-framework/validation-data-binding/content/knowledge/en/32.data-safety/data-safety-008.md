# Database Uniqueness Checks and Race Condition Risks

## 1. The Problem: Two Requests Both See "Does Not Exist Yet" and Both Write the Same Value

Suppose a Spring application allows registering accounts with unique usernames. A common check looks like:

```java
if (accountRepository.existsByUsernameKey(usernameKey)) {
    throw new UsernameTakenException();
}

accountRepository.save(new AccountEntity(usernameKey));
```

This is only an **illustrative snippet**, not a safe implementation. Under concurrent requests, it suffers from a **check-then-act / time-of-check-to-time-of-use (TOCTOU)** vulnerability:

```text
Time            Request A                        Request B
---------       -------------------------------  -------------------------------
t1              SELECT EXISTS('lan') -> false
t2                                               SELECT EXISTS('lan') -> false
t3              INSERT username_key='lan'
t4                                               INSERT username_key='lan'
t5              COMMIT
t6                                               COMMIT

If the database has NO unique constraint:
  Both A and B can commit -> two rows with duplicate username.

If the database HAS a unique constraint/index:
  Two committed rows cannot share the same violating key;
  one operation fails (or blocks then fails) depending on transaction/DB.
```

**Core point:** checking `existsBy...` provides an early hint, yet **does not guarantee uniqueness**. Uniqueness must be enforced where the entire dataset is visible and concurrent transactions are coordinated: a **database unique constraint / unique index** (or an equivalent tightly designed constraint in your specific datastore).

The same risk occurs with registration emails, booking codes, invoice numbers, coupon codes, transaction IDs, phone numbers, per-tenant group names, article slugs, and any "create once only" resource.

Within the **Data Safety** topic, this lesson progresses from race condition causes, schema design, Spring Data JPA usage, and exception-to-HTTP mapping to **two-thread concurrency testing**. It also distinguishes Bean Validation checks from database-level data invariants.

**Reference environment:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1, Spring Data JPA, Hibernate ORM, Jakarta Validation, H2 for the demo project, and PostgreSQL for illustrating production SQL choices.

## 2. Three Checking Layers and Their Guarantees

| Layer | Example | Goal | Guarantees no duplicates under concurrency? |
| --- | --- | --- | --- |
| Client/UI | "Check username" button | Input UX | **No** |
| Spring application | `existsByUsernameKey`, custom `@UniqueUsername` | Early feedback, business rule | **No**, because check and insert are not atomic |
| Database schema | `UNIQUE(username_key)`, unique index | Invariant for persisted data | **Yes**, within the scope of the key/constraint and DB semantics |
| Database atomic insert | PostgreSQL `INSERT ... ON CONFLICT` | Concurrent insert/upsert on a unique arbiter | Yes, per database semantics and conflict target |

Distinguish carefully:

- **Input validation errors:** `@NotBlank`, `@Size`, `@Pattern` check formatting or value limits.
- **Business uniqueness:** the username was unused at the instant a query observed it.
- **Persistence invariant:** the database refuses to commit two rows violating a unique key.

`@Valid` / `@Validated` never turns a duplicate-check query into an atomic transaction. `@Column(unique=true)` or `@Table(uniqueConstraints=...)` can help Hibernate emit DDL when schema generation is enabled, yet production should manage constraints via migrations and verify the constraint actually exists in the database.

## 3. Why Doesn't `@Transactional` Solve Check-Then-Insert Automatically?

Much code is written as:

```java
@Transactional
public Account create(String usernameKey) {
    if (repository.existsByUsernameKey(usernameKey)) {
        throw new DuplicateUsernameException();
    }
    return repository.save(new Account(usernameKey));
}
```

This is a **snippet** assuming classes are defined. `@Transactional` wraps a sequence of operations in a transaction, yet it **does not prevent** two concurrent transactions from both reading "does not exist."

Under common `READ_COMMITTED` isolation, two transactions can run the exists query before either commits. Without a unique constraint, both can write. With a unique constraint, the database is forced to resolve the duplicate-key conflict.

### 3.1. How does transaction isolation relate?

- `READ_COMMITTED`: each query sees data committed before the query starts; it does not block two concurrent "exists=false" results.
- `REPEATABLE_READ`: guarantees repeatable reads per database semantics, yet you must not assume a query that "saw no row" locked a nonexistent username.
- `SERIALIZABLE`: the database can detect serialization conflicts and abort a transaction; the application must handle scoped retries. It carries specific database costs and semantics. Never raise isolation levels as a shortcut "to avoid creating a unique index" for a simple uniqueness invariant.
- `SELECT ... FOR UPDATE`: generally locks **existing selected rows**. When no row exists yet, there is no concrete row to lock; some databases have gap/predicate locking, which is non-portable. Never treat `@Lock(PESSIMISTIC_WRITE)` on empty results as a universal solution.

**Practical conclusion:** for username/email uniqueness, a **unique constraint** is the foundational requirement; transactions, locks, retries, and early-check queries are supporting tools for specific workflows.

### 3.2. How does a unique key resolve check-then-act?

When two transactions try to insert the same key, the database engine coordinates uniqueness checks on the unique index/constraint. Depending on the DB and transaction state, one operation may block until the other commits or rolls back. If the first rolls back, the second can proceed; if the first commits, the other receives a conflict error. Never promise **Request A always wins** just because it arrived slightly earlier.

In PostgreSQL, unique constraints are enforced via unique indexes. Its documentation details concurrent inserts and how `INSERT ... ON CONFLICT` uses a unique arbiter. Locking, deadlocks, timeouts, and retries still depend on the database; the application must handle real errors and timeouts.

## 4. Designing Unique Constraints with the Right Scope

### 4.1. Single-column unique key

Illustrative SQL:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username_key VARCHAR(24) NOT NULL,
    CONSTRAINT uk_accounts_username_key UNIQUE (username_key)
);
```

Meaning:

- `id` is the technical primary key.
- `username_key` is the canonicalized value used for uniqueness comparisons.
- `NOT NULL` forbids nulls at the DB layer.
- `UNIQUE` prevents duplicate keys per the DB's collation and data type.
- Naming `uk_accounts_username_key` makes migrations, logging, and exception classification easier to trace.

Note that `NOT NULL` does not guarantee non-blank: an empty string can still be valid in the DB. Input `@NotBlank` and business normalization form a separate layer; if non-Spring writers can write directly, consider a `CHECK` constraint or matching schema strategy.

### 4.2. Per-tenant uniqueness (composite unique)

In multi-tenant applications, the same username may be allowed across different tenants:

```sql
CREATE TABLE tenant_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    username_key VARCHAR(24) NOT NULL,
    CONSTRAINT uk_tenant_username UNIQUE (tenant_id, username_key)
);
```

Do not place a global `UNIQUE(username_key)` if the product rule only forbids duplicates **within each tenant**.

The repository must query with matching scope:

```java
boolean existsByTenantIdAndUsernameKey(
        Long tenantId, String usernameKey);
```

Yet even a query checking both conditions **does not replace** the composite unique constraint. Furthermore, `tenantId` must come from an authenticated/authorized context—never trust a client-supplied tenant value in JSON to determine security scope.

### 4.3. Soft delete and partial unique indexes

A product might allow reusing a username after an old account is soft-deleted. A table-wide unique constraint on `username_key` would keep blocking new accounts. In PostgreSQL, you can choose:

```sql
CREATE UNIQUE INDEX uk_active_username_key
ON accounts (username_key)
WHERE deleted_at IS NULL;
```

This is a **PostgreSQL-specific partial unique index**; do not copy it blindly to every DBMS without checking support. Also understand:

- Restoring a soft-deleted account can conflict if its username has already been reused.
- Soft-delete and restore states require explicit business policies.
- If each tenant allows one active username, the index can use `(tenant_id, username_key) WHERE deleted_at IS NULL`.
- Basic JPA `@UniqueConstraint` cannot fully express partial indexes, so a dedicated SQL migration is needed.
- Rules like "only one active booking per overlapping time window" cannot be solved with `UNIQUE(room_id, start_at)` alone; exclusion constraints or transactional reservation designs may be required.

### 4.4. NULLs and uniqueness

In PostgreSQL, a standard unique constraint treats `NULL`s as distinct when checking uniqueness, allowing multiple rows to contain NULL in a UNIQUE column. PostgreSQL provides `NULLS NOT DISTINCT` when different semantics are required. Other DBMSs have slightly different rules.

For **mandatory** usernames/emails, the clearest approach is declaring `NOT NULL` and validating input. Never treat `UNIQUE` as implying `NOT NULL`.

## 5. Key Canonicalization: Are "Lan" and "lan" Considered Duplicates?

`UNIQUE` enforces uniqueness according to the **stored value and chosen collation**. If the application wants case-insensitive usernames, define a normalization policy and apply it on **every write path**.

In the demo, usernames permit only **ASCII letters, digits, and underscores**. We can canonicalize via:

```java
String key = username.toLowerCase(Locale.ROOT);
```

Given the ASCII input policy, this lowercasing is well-defined for the use case. `Locale.ROOT` avoids host-locale quirks such as language-specific case rules.

Demo behavior table:

| Input | Stored `username_key` | Outcome |
| --- | --- | --- |
| `Lan_01` | `lan_01` | Created if not yet present |
| `LAN_01` | `lan_01` | Conflict if `Lan_01` already exists |
| `lan_02` | `lan_02` | Distinct from `lan_01` |
| `Lan 01` | Fails `@Pattern` | HTTP 400, no insert |
| `Đặng` | Fails ASCII `@Pattern` | HTTP 400 in **demo** |

**Do not generalize this rule blindly to emails or arbitrary Unicode names.** Emails have specific standards and operational realities around local parts, domains, IDNs, plus-addressing, and provider aliases; arbitrarily lowercasing or stripping dots/pluses on emails can create false collisions. Unicode names likewise need product-designed normalization/collation and confusable defenses. For business identifiers, explicitly specify "which two values count as equal" before designing an index.

**Mismatch risk:** checking `existsByUsernameKey(raw)` while inserting `raw.toLowerCase(...)`, or using inconsistent normalization across two services, causes broken UX. Canonicalize in one tested place, constrain the exact stored column, and migrate/backfill consistently.

## 6. Should You Write a Custom Jakarta `@UniqueUsername` Validator?

A custom constraint often looks like:

```java
public class UniqueUsernameValidator
        implements ConstraintValidator<UniqueUsername, String> {

    private final AccountRepository repository;

    @Override
    public boolean isValid(
            String username, ConstraintValidatorContext context) {

        if (username == null) {
            return true;
        }

        return !repository.existsByUsernameKey(
                username.toLowerCase(Locale.ROOT)
        );
    }
}
```

This is an **illustrative snippet**, assuming the `@UniqueUsername` annotation, imports, and repository exist. It can improve UX by reporting "username already taken" in the validation layer, yet a **race remains** between `isValid` and `INSERT`. Never use it as the sole uniqueness mechanism.

Practical limitations:

- Another request can insert immediately after the validator returns true.
- The validator runs a DB query, adding latency and risking N+1 queries when validating collections.
- During profile **updates**, the validator must exclude the record being edited to avoid self-conflict, requiring trusted identity and tenant scope.
- Non-HTTP paths—batch imports, admin tools, event consumers, or migrations—may bypass Bean Validation.
- Never leak sensitive info or enable account enumeration in public messages when disallowed.
- Jakarta Validation is not a lock or transaction manager.
- Misconfigured custom constraints or missing DI/validator providers can fail requests unexpectedly.

With Spring MVC, format checks (`@NotBlank`, `@Pattern`, `@Size`) plus a DB unique constraint are usually sufficient; if availability preview is desired, provide a separate advisory endpoint. Never claim `@UniqueUsername` "solves concurrency" in a code review.

## 7. Spring Data JPA: save, flush, and commit Are Three Different Concepts

### 7.1. save(entity) does not always emit SQL immediately

`JpaRepository#save` operates through the persistence context. The SQL INSERT may execute immediately or be deferred depending on ID generation strategy, flush mode, and the JPA provider. With `GenerationType.IDENTITY`, providers often need an early INSERT to retrieve the generated key; that **does not** mean every entity/DB writes immediately on `save()`.

Therefore:

```java
repository.save(entity);
```

does not guarantee a unique constraint exception is always thrown **on that exact line**. The error can surface at flush or commit.

### 7.2. saveAndFlush pushes changes to the DB, not yet commit

`JpaRepository#saveAndFlush` saves the entity and flushes immediately within the transaction:

```java
AccountEntity saved = repository.saveAndFlush(entity);
```

This helps detect DB constraint violations early for **immediate/non-deferrable constraints**. Yet `flush` is not `commit`:

- Flush sends pending SQL to the database.
- The transaction can still roll back.
- Deferrable constraints (if supported by the database) may be checked at commit.
- Other transaction/commit failures can still occur when the transaction ends.

**Never promise "`saveAndFlush` guarantees every DB error happens before the method returns."** Understand transaction boundaries.

### 7.3. `@Transactional` on the service changes where exceptions surface

If a service declares:

```java
@Transactional
public AccountEntity create(AccountEntity account) {
    return repository.save(account);
}
```

then commit typically happens **after the service method body finishes**, when the transaction interceptor exits. A `try/catch` **inside** the method body may miss errors raised at commit outside the body. Conversely, a controller calling through the Spring proxy receives the exception after the service method returns.

If `saveAndFlush` throws a constraint error inside a larger transaction, that transaction may already be marked rollback-only or unsafe to continue. **Never** catch `DataIntegrityViolationException` and keep issuing writes inside the same transaction as if nothing happened.

The runnable project below **intentionally omits `@Transactional` on the registration service**: the repository `saveAndFlush` call uses the repository proxy's transaction boundary, and uniqueness errors propagate cleanly to the controller advice. This keeps the demo straightforward. A multi-step production use case needs a proper service transaction with error translation **outside the transaction boundary** or an explicit retry design.

### 7.4. Which exception does Spring translate DB errors into?

In Spring Data/JPA, many unique, not-null, and foreign-key violations are translated into:

```java
org.springframework.dao.DataIntegrityViolationException
```

This exception is **fairly broad**, and not every instance means a duplicate username. The provider may wrap a nested cause such as Hibernate's `org.hibernate.exception.ConstraintViolationException` or a SQL exception carrying SQLSTATE, vendor code, or constraint name.

In our small demo with one clear business uniqueness constraint, the handler maps integrity errors to `DATA_CONFLICT` and HTTP 409. **In real systems**, classify the specific constraint:

- Confirmed violation of the username unique key → map to `USERNAME_ALREADY_TAKEN`, HTTP 409, or the API contract status.
- Foreign key, check, or not-null errors caused by server bugs → should not masquerade as "duplicate username."
- Deadlocks, timeouts, or transient failures → never disguise them as duplicates; apply dedicated retry/backoff policies.
- Never return raw SQL, constraint stack traces, or driver messages to clients.

Depending on the database, PostgreSQL uses SQLSTATE `23505` for `unique_violation`. However, checking SQLSTATE alone may not identify **which constraint** failed when a table has multiple unique indexes. Matching constraint names plus schema domain mapping is clearer; extraction relies on provider/driver behavior and must be tested against the real database.

## 8. Complete Example: Username Registration with Database Enforcement

The project uses Spring Boot 3.3.6, Java 17, Spring Data JPA, Hibernate Validator, and H2.

Goals:

1. `POST /api/registrations` accepts JSON with a username and validates format.
2. Canonicalizes ASCII usernames to lowercase.
3. Database enforces unique constraint `uk_accounts_username_key` on `username_key`.
4. Inserts directly with **no pre-check** on the creation path; the database is the source of truth.
5. When the DB rejects a conflict, the advice returns HTTP **409** with safe code `DATA_CONFLICT`, leaking no SQL.
6. `GET /api/usernames/availability` returns `available` as a UI hint, **without guaranteeing availability at POST time**.
7. Tests two concurrent threads inserting the same username; exactly one row exists afterward.

### 8.1. Project structure

```text
unique-username-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/uniqueusername/
        UniqueUsernameApplication.java
        AccountEntity.java
        AccountRepository.java
        RegistrationRequest.java
        RegistrationResponse.java
        AvailabilityResponse.java
        ApiError.java
        RegistrationService.java
        RegistrationController.java
        RegistrationErrorAdvice.java
      resources/
        application.properties
    test/
      java/com/example/uniqueusername/
        RegistrationIntegrationTest.java
```

### 8.2. Gradle build

File `settings.gradle`:

```groovy
rootProject.name = 'unique-username-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In the demo, `Hibernate` generates the schema from JPA annotations. That is a convenience for learning, not a recommendation to run `create-drop` schema generation in production.

### 8.3. application.properties

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:unique_username_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.hikari.maximum-pool-size=8

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.format_sql=true
```

H2 is an in-memory DB; each restart can recreate the database cleanly. `create-drop` drops/recreates the schema across lifecycle runs—**never use it where real data must persist**. Production SQL migrations are discussed after the test section.

The Hikari pool size line gives the two-thread test ample connections; it provides no uniqueness guarantee by itself.

### 8.4. Main application

File `src/main/java/com/example/uniqueusername/UniqueUsernameApplication.java`:

```java
package com.example.uniqueusername;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UniqueUsernameApplication {

    public static void main(String[] args) {
        SpringApplication.run(UniqueUsernameApplication.class, args);
    }
}
```

### 8.5. Entity and unique constraint

File `src/main/java/com/example/uniqueusername/AccountEntity.java`:

```java
package com.example.uniqueusername;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "accounts",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_accounts_username_key",
                columnNames = "username_key"
        )
)
public class AccountEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "username_key",
            nullable = false,
            length = 24
    )
    private String usernameKey;

    protected AccountEntity() {
        // JPA requires a no-arg constructor.
    }

    public AccountEntity(String usernameKey) {
        this.usernameKey = usernameKey;
    }

    public Long getId() {
        return id;
    }

    public String getUsernameKey() {
        return usernameKey;
    }
}
```

Here `@Table(uniqueConstraints=...)` describes uniqueness in JPA metadata. When Hibernate runs `ddl-auto=create-drop`, it creates the corresponding constraint/index in H2.

**Schema verification is mandatory:** if an application uses `spring.jpa.hibernate.ddl-auto=validate` or `none` on a real database, annotations **do not create schema changes**. Use Flyway, Liquibase, or manual migrations to ensure the constraint actually exists.

### 8.6. Repository

File `src/main/java/com/example/uniqueusername/AccountRepository.java`:

```java
package com.example.uniqueusername;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<AccountEntity, Long> {

    boolean existsByUsernameKey(String usernameKey);

    long countByUsernameKey(String usernameKey);
}
```

`existsByUsernameKey` is solely a read query. It can return false right before another writer inserts the same username. `countByUsernameKey` aids tests and observability, never replacing the unique constraint.

### 8.7. Request, response, and error DTOs

File `src/main/java/com/example/uniqueusername/RegistrationRequest.java`:

```java
package com.example.uniqueusername;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegistrationRequest(
        @NotBlank
        @Size(min = 3, max = 24)
        @Pattern(regexp = "[A-Za-z0-9_]+")
        String username
) {}
```

Supports only ASCII `[A–Z]`, `[a–z]`, `[0–9]`, and underscore, 3 to 24 characters long. This is a **demo domain policy**, not a general Spring limitation.

File `src/main/java/com/example/uniqueusername/RegistrationResponse.java`:

```java
package com.example.uniqueusername;

public record RegistrationResponse(
        Long id,
        String username
) {}
```

File `src/main/java/com/example/uniqueusername/AvailabilityResponse.java`:

```java
package com.example.uniqueusername;

public record AvailabilityResponse(
        String username,
        boolean available
) {}
```

File `src/main/java/com/example/uniqueusername/ApiError.java`:

```java
package com.example.uniqueusername;

public record ApiError(
        String code,
        String message
) {}
```

Success responses return only the ID and canonical username, never exposing the JPA entity directly. Error responses keep a stable **machine code** and controlled message, never reflecting raw DB errors.

### 8.8. Service: INSERT is where the DB decides

File `src/main/java/com/example/uniqueusername/RegistrationService.java`:

```java
package com.example.uniqueusername;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final AccountRepository accounts;

    public RegistrationService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    public RegistrationResponse register(
            RegistrationRequest request) {

        String key = canonical(request.username());

        // NO mandatory pre-check before insert.
        // Database UNIQUE(username_key) is the final barrier.
        AccountEntity saved = accounts.saveAndFlush(
                new AccountEntity(key)
        );

        return new RegistrationResponse(
                saved.getId(),
                saved.getUsernameKey()
        );
    }

    public AvailabilityResponse checkAvailability(String username) {
        if (username == null
                || !username.matches("[A-Za-z0-9_]{3,24}")) {

            return new AvailabilityResponse(username, false);
        }

        String key = canonical(username);

        // Just a snapshot for UX.
        // true DOES NOT mean a subsequent POST will definitely succeed.
        boolean available = !accounts.existsByUsernameKey(key);

        return new AvailabilityResponse(key, available);
    }

    private static String canonical(String username) {
        return username.toLowerCase(Locale.ROOT);
    }
}
```

**Why does `register` omit `@Transactional` on the class/service?**

In this simple example, `JpaRepository#saveAndFlush` has a transaction boundary managed by the Spring Data repository. Without an outer service transaction, the repository call either completes or throws before the service returns. That makes sequential and concurrent tests easy to reason about. Do not copy this pattern mechanically to multi-table workflows needing an atomic transaction; use an explicit service transaction and handle errors **outside** the transaction boundary.

**Why not call `existsBy...` before inserting?**

To highlight the invariant enforced by the unique constraint. A pre-check can be added for UX, yet adds zero guarantee once the database enforces the constraint—and adds an extra round trip to every request. A separate `checkAvailability` endpoint illustrates point-in-time reads.

### 8.9. REST controller

File `src/main/java/com/example/uniqueusername/RegistrationController.java`:

```java
package com.example.uniqueusername;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RegistrationController {

    private final RegistrationService registration;

    public RegistrationController(
            RegistrationService registration) {

        this.registration = registration;
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @ResponseStatus(HttpStatus.CREATED)
    public RegistrationResponse register(
            @Valid @RequestBody RegistrationRequest request) {

        return registration.register(request);
    }

    @GetMapping("/usernames/availability")
    public AvailabilityResponse availability(
            @RequestParam String username) {

        return registration.checkAvailability(username);
    }
}
```

`@Valid` checks username format before the service runs. `@Pattern` and `@Size` do not prove uniqueness. HTTP 201 succeeds only after the repository insert and transaction finish per the demo flow. Multi-step production workflows may also need to consider transaction commits, messaging/outbox patterns, and response timing.

### 8.10. `@RestControllerAdvice` handling 400, 409, and JSON parse errors

File `src/main/java/com/example/uniqueusername/RegistrationErrorAdvice.java`:

```java
package com.example.uniqueusername;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RegistrationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT",
                        "Username must contain 3-24 ASCII letters, "
                                + "digits or underscores"
                )
        );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> dataConflict(
            DataIntegrityViolationException exception) {

        // Demo has one business UNIQUE constraint on username.
        // Return generic code; never expose constraint name/SQL.
        return ResponseEntity.status(409).body(
                new ApiError(
                        "DATA_CONFLICT",
                        "The requested value conflicts with existing data"
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_JSON",
                        "Cannot read the request JSON"
                )
        );
    }
}
```

**Critical demo limitation:** the `DataIntegrityViolationException` handler maps all integrity errors to a generic 409. In a production API with multiple constraints, **never** label every `DataIntegrityViolationException` as `USERNAME_TAKEN`. Identify the exact violated constraint via SQLSTATE/constraint name tested against the real DB; map business conflicts accurately, while classifying foreign-key/not-null/check bugs separately as 400/409/500 depending on client vs. server fault. 409 is an API design choice for resource conflicts, not a rule that every duplicate constraint must return 409.

Specifically, never do:

```java
return ResponseEntity.status(409).body(
        exception.getMostSpecificCause().getMessage()
);
```

Raw DB messages can expose schemas, SQL, table names, user data, or internal details. Return safe machine codes and messages; server logs can capture filtered constraint identifiers and correlation IDs.

## 9. Running the App and Testing with curl

Create the Gradle wrapper if absent; the project includes a wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 9.1. New registration

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"Lan_01"}'
```

**Expected HTTP 201**, illustrative JSON:

```json
{
  "id": 1,
  "username": "lan_01"
}
```

The ID may differ from `1` if the DB already contains data or sequences have advanced. What matters is that the canonicalized username is persisted and the request succeeds.

### 9.2. Duplicate registration differing in letter case

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"LAN_01"}'
```

Because both normalize to `lan_01`, the unique constraint blocks the insert. **Expected HTTP 409**:

```json
{
  "code": "DATA_CONFLICT",
  "message": "The requested value conflicts with existing data"
}
```

Even though the service never called `existsByUsernameKey` in `register`, the database prevented the duplicate.

### 9.3. Availability check is only a snapshot

```bash
curl -i 'http://localhost:8080/api/usernames/availability?username=Lan_01'
```

If `lan_01` is already registered, HTTP 200:

```json
{"username":"lan_01","available":false}
```

If called with an unused username:

```json
{"username":"other_01","available":true}
```

**`available=true`** describes only the instant of the query. Another request can claim `other_01` before this client submits POST. The frontend must still handle 409 gracefully even after displaying a green checkmark.

### 9.4. Malformed input

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"bad name"}'
```

The username contains a space, violating `@Pattern`. **Expected HTTP 400** with `INVALID_INPUT`. This is a validation error, distinct from a uniqueness conflict occurring during DB insert.

## 10. Integration Tests: Verifying the Unique Index and Race Conditions

File `src/test/java/com/example/uniqueusername/RegistrationIntegrationTest.java`:

```java
package com.example.uniqueusername;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RegistrationService registration;

    @Autowired
    AccountRepository accounts;

    private ResultActions postUsername(String username)
            throws Exception {

        return mvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + username + "\"}"));
    }

    @Test
    void registrationCreatesCanonicalUsername() throws Exception {
        postUsername("Alpha377")
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.username").value("alpha377"));

        assertEquals(1, accounts.countByUsernameKey("alpha377"));
    }

    @Test
    void duplicateUsernameReturnsConflict() throws Exception {
        postUsername("Beta377")
            .andExpect(status().isCreated());

        postUsername("Beta377")
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("DATA_CONFLICT"));

        assertEquals(1, accounts.countByUsernameKey("beta377"));
    }

    @Test
    void caseVariantsUseTheSameUniqueKey() throws Exception {
        postUsername("Camel377")
            .andExpect(status().isCreated());

        postUsername("CAMEL377")
            .andExpect(status().isConflict());

        assertEquals(1, accounts.countByUsernameKey("camel377"));
    }

    @Test
    void availabilityIsOnlyAReadSnapshot() throws Exception {
        mvc.perform(get("/api/usernames/availability")
                .param("username", "Find377"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("find377"))
            .andExpect(jsonPath("$.available").value(true));

        postUsername("Find377")
            .andExpect(status().isCreated());

        mvc.perform(get("/api/usernames/availability")
                .param("username", "FIND377"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.available").value(false));
    }

    @Test
    void invalidFormatFailsBeforePersistence() throws Exception {
        postUsername("bad name")
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        assertEquals(0, accounts.countByUsernameKey("bad name"));
    }

    @Test
    void malformedJsonIsNotUniquenessFailure() throws Exception {
        mvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void concurrentRegistrationsProduceOneWinner() throws Exception {
        // Do not put @Transactional on the test: worker threads
        // need their own repository transactions.
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<String> attempt = () -> {
            ready.countDown();

            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timed out");
            }

            try {
                registration.register(
                        new RegistrationRequest("Race377")
                );
                return "CREATED";
            } catch (DataIntegrityViolationException expected) {
                return "CONFLICT";
            }
        };

        try {
            Future<String> one = executor.submit(attempt);
            Future<String> two = executor.submit(attempt);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            List<String> outcomes = List.of(
                    one.get(15, TimeUnit.SECONDS),
                    two.get(15, TimeUnit.SECONDS)
            );

            assertEquals(
                    1, Collections.frequency(outcomes, "CREATED")
            );
            assertEquals(
                    1, Collections.frequency(outcomes, "CONFLICT")
            );
            assertEquals(
                    1, accounts.countByUsernameKey("race377")
            );
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    @Test
    void differentNamesAreBothAllowed() throws Exception {
        postUsername("DistinctA377")
            .andExpect(status().isCreated());

        postUsername("DistinctB377")
            .andExpect(status().isCreated());

        assertEquals(1, accounts.countByUsernameKey("distincta377"));
        assertEquals(1, accounts.countByUsernameKey("distinctb377"));
    }
}
```

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Eight tests are expected to PASS** in an environment with the proper dependencies, H2, and Java 17. This is expected behavior of the sample code; no claim is made that JUnit/Gradle was executed while authoring this lesson.

### 10.1. Why is a concurrency test valuable?

The `concurrentRegistrationsProduceOneWinner` test uses two threads, each calling the service once. Two `CountDownLatch` instances align both tasks to start nearly simultaneously; the test then verifies **exactly one success, one conflict, and one persisted row**.

This does not prove two `exists` SELECTs ran concurrently, since production code skips the pre-check. It proves DB uniqueness is enforced even when two inserts race against each other.

**Race tests must never assume which request wins.** Both race to register `Race377`; the expected result is the multiset `{CREATED, CONFLICT}`, not "thread A always wins." Nor should the test assume identity ID values, per-insert latency, or log order.

When targeting a real database (PostgreSQL/MySQL), run additional integration tests via Testcontainers or an equivalent CI environment. H2 is helpful for demonstration, yet cannot substitute for testing production DB locks/isolation, SQLSTATEs, deferrable constraints, and race behavior.

### 10.2. Why is `@Transactional` omitted from the test?

In Spring Test, a `@Transactional` test method starts a transaction and rolls it back on completion. If the test spawns new threads, the transaction context does not propagate across worker threads automatically, causing unpredictable visibility or unexpected isolation.

For this concurrency test, `@Transactional` is omitted on the test class/method; each repository call runs in its own transaction. When the test finishes, committed rows can be queried directly.

Never rely on `Thread.sleep(100)` as primary synchronization; sleeping establishes no clear happens-before start gate. `CountDownLatch` reduces timing flakiness, though reproducing exact races still requires appropriate DB and thread orchestration.

## 11. Seeing the Flaw in Check-Then-Insert via Deterministic Scheduling

The runnable project protects via a unique constraint. To understand why pre-checks are weak, examine the logical schedule:

```text
Repository.existsByUsernameKey("demo") in T1 -> false
Repository.existsByUsernameKey("demo") in T2 -> false

T1: INSERT accounts(username_key) VALUES ('demo')
T2: INSERT accounts(username_key) VALUES ('demo')

If UNIQUE exists:
  one transaction must be rejected or handle conflict per DB policy.

If NO UNIQUE exists:
  T1 and T2 can both commit -> duplicate data.
```

A mocked unit test:

```java
when(repository.existsByUsernameKey("demo"))
        .thenReturn(false)
        .thenReturn(false);
```

only proves two checks can both return false; **it does not test database contention**. Mocks do not simulate MVCC, locks, transaction commits, or constraint violations. To verify the invariant, run integration tests against a real or test database with the unique constraint.

If you want a deliberate race reproduction for vulnerable code, place a barrier between the exists check and the insert inside a test-only service. **Never** ship barriers/sleeps in production just to make races reproducible. Without a unique constraint, the test can observe two rows; with a unique constraint, a conflict occurs.

## 12. PostgreSQL UPSERT and ON CONFLICT: When to Use?

In PostgreSQL, when the requirement is "create only if absent, do not raise an exception on duplicate," you can use:

```sql
INSERT INTO accounts (username_key)
VALUES ('lan')
ON CONFLICT (username_key) DO NOTHING
RETURNING id;
```

On conflict, the statement inserts no row and `RETURNING` yields no rows. The application must define UX:

- Return 409 because the username is already taken.
- Return an idempotent response if the same principal is retrying an operation **defined as idempotent**.
- Never assume "DO NOTHING" means creation succeeded; the client might wrongly believe it owns the account.

Another option:

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-1', 1)
ON CONFLICT (sku)
DO UPDATE SET quantity = inventory.quantity + 1;
```

This is a purposeful upsert example for counter/inventory logic, not advice to upsert accounts. `DO UPDATE` has **overwrite/update** semantics requiring authorization, race analysis, and isolation/idempotency care. Never use "upsert user" to bypass rules when a username already belongs to someone else.

PostgreSQL `ON CONFLICT DO UPDATE` guarantees atomic insert-or-update per unique arbiter within the engine's rules. Still, it does not solve business concerns such as duplicate emails, double charges, or ownership policies.

**Other databases use different syntax:** MySQL uses `INSERT ... ON DUPLICATE KEY UPDATE`; SQL Server has its own constructs and `MERGE` concurrency caveats. Never copy one syntax across all RDBMSs assuming identical semantics.

## 13. A Unique Constraint Does Not Equal Idempotency

Sending "create account username=lan" twice can produce:

1. First request succeeds with 201.
2. Second request gets 409 from the unique constraint.

That protects data integrity, yet **does not make** the second request a safe retry of the same operation. A request can lose its HTTP response after the DB already committed; a retrying client will not know whether its earlier attempt succeeded. APIs requiring idempotency need a dedicated design.

For example, a payment system with header:

```http
Idempotency-Key: 5ef...unique-per-operation...
```

The server can persist a request-ID record scoped by principal and operation with a matching unique index, comparing payload hashes, in-progress state, and completed results. If the same idempotency key arrives with a different payload, reject explicitly. Never add `UNIQUE(email)` alone and claim duplicate transactions are solved.

A common strategy:

- Scoped `UNIQUE(idempotency_key, principal_id)`.
- Atomic transaction linking the idempotency record and business writes.
- Explicit processing states, appropriate TTL/retention, and concurrency claim handling.
- Returning the stored prior response on valid retries per API contract.

This is a broader design than username uniqueness; keeping them distinct prevents double-order and double-charge bugs.

## 14. Updates, Restores, Deletes, and Migrations Must Also Preserve Uniqueness

### 14.1. Conflicts do not happen only on INSERT

When renaming a username:

```sql
UPDATE accounts
SET username_key = 'lan'
WHERE id = 42;
```

If `lan` already belongs to another account, the unique constraint blocks the UPDATE as well. A "rename" service can pre-check for early feedback, yet must still handle the final DB conflict.

### 14.2. Find and clean up duplicates before adding constraints

If an existing table already holds duplicates, creating a unique index will fail. Illustrative check SQL:

```sql
SELECT username_key, COUNT(*) AS occurrences
FROM accounts
GROUP BY username_key
HAVING COUNT(*) > 1;
```

For case-insensitive policies, backfill the canonical key first and check duplicates **on the canonical key**, not only the display value. Decide ownership, merges, renames, or controlled conflict resolution. Never delete one of two conflicting accounts arbitrarily just to make a migration pass.

In large systems, online/concurrent index creation involves locking considerations, staged rollouts, and rollback plans. In PostgreSQL, `CREATE UNIQUE INDEX CONCURRENTLY` reduces write blocking compared to regular index creation, with its own caveats (it can fail on duplicates and leave an invalid index to clean up). Never run risky migrations without consulting the docs for your exact database and version.

### 14.3. Distinguishing `@Column(unique=true)` from migrations

JPA:

```java
@Column(unique = true)
private String usernameKey;
```

is a DDL/schema mapping hint; convenient for demos. In production, schemas are usually managed with Flyway/Liquibase using named constraints and controlled rollouts. Ensure code/JPA mappings, SQL migrations, and actual database schemas align. **Seeing a Java annotation does not prove the DB has the constraint.**

### 14.4. Multiple services writing to the same table

If an HTTP service, batch job, and event consumer all write accounts, validation in the HTTP controller leaves the other two writers unprotected. A database unique index governs every writer to that datastore, serving as a natural barrier.

If multiple independent datastores or regions use eventual consistency, you cannot simply infer global uniqueness from local DB unique indexes. You need appropriate ID allocation, partition ownership, consensus, or conflict-resolution strategies. Distributed concurrency extends beyond a single RDBMS.

## 15. Error Semantics: 400, 409, 422, and 500

There is no single mandatory HTTP status for every uniqueness violation; agree on an API contract. Reference mapping:

| Scenario | Common status | Notes |
| --- | --- | --- |
| Username has invalid characters | 400 Bad Request or 422 | Input validation |
| Username is already taken (verified) | 409 Conflict | Avoid leaking sensitive details |
| Duplicate idempotency key with same payload | May return prior request result | Per idempotency contract |
| Duplicate idempotency key with different payload | 409 or matching business code | Never silently treat as success |
| Foreign key violation from service bug | Usually 500 or appropriate mapping | Never misreport as "duplicate username" |
| Database deadlock/timeout | 5xx / retry policy per case | Not a duplicate |
| Malformed JSON | 400 | DTO could not be constructed |
| Missing required field | 400 | `@Valid` or DB not-null depending on where caught |

In the demo, the advice returns generic `DATA_CONFLICT` for `DataIntegrityViolationException` so learners do not couple to H2-specific messages or SQLSTATEs. If a product needs specific messages like "Username already taken," identify **the exact constraint**, never catch every integrity failure indiscriminately.

### 15.1. Avoiding information disclosure

Availability endpoints and 409 responses can become username/email enumeration vectors. For personal emails, many systems return neutral messages on sign-up or password reset; policy depends on identity verification flows, abuse controls, and UX.

- Rate-limit availability queries and registration attempts.
- Never expose raw SQL exceptions.
- Never echo rejected secrets in messages.
- Never return the ID or profile details of the account holding the username.
- Record metrics by error code and verified constraint; avoid logging passwords or tokens.
- Keep authorization separate from uniqueness. "A conflicting record exists" never grants the client rights to read or edit that record.

## 16. Common Mistakes

**1. Relying solely on `existsBy...`.** Two concurrent requests can both observe false; without a DB unique constraint, duplicates can be written.

**2. Believing `@Transactional` makes exists+insert atomic.** Transactions do not lock nonexistent values by default; understand isolation levels and constraints.

**3. Using `@NotBlank`/`@Email`/`@Pattern` instead of `UNIQUE`.** Format validation cannot enforce invariants across rows.

**4. Writing a custom `@UniqueUsername` and omitting the unique index.** The validator still has a check-then-act race and is only a UX optimization.

**5. Putting `@Column(unique=true)` on the entity and assuming prod DB changed.** Without migrations or schema generation, the constraint may not exist.

**6. Failing to canonicalize before both reads and writes.** `Lan` and `lan` may collide by business rules while storing different keys, or pre-checks query the wrong column.

**7. Canonicalizing emails with arbitrary rules.** May merge distinct addresses or miss aliases; use a domain-appropriate policy.

**8. Using `UNIQUE` while forgetting `NOT NULL`.** Many DBs permit multiple NULLs under unique semantics; required values could still be missing.

**9. Adding a global unique constraint when rules are per-tenant.** Wrongly blocks other tenants; use a composite unique key.

**10. Soft-deleting and reusing keys with a table-wide unique constraint.** Design a partial index or archive/restore policy.

**11. Assuming `save()` always throws on that exact line.** Hibernate may send SQL at flush or commit.

**12. Assuming `saveAndFlush()` equals commit.** Flush does not end the transaction; deferrable errors can occur later.

**13. Catching `DataIntegrityViolationException` inside a transaction and continuing writes.** The transaction may be rollback-only or the persistence context corrupted.

**14. Catching every `DataIntegrityViolationException` and returning `USERNAME_TAKEN`.** Foreign key/not-null/check errors and other unique constraints share that exception family.

**15. Catching generic `Exception` and returning 409.** Masks bugs, timeouts, deadlocks, and system outages.

**16. Returning SQLSTATE or raw DB messages to clients.** Can leak schema details and sensitive data.

**17. Retrying duplicate inserts indefinitely.** Duplicates are persistent business conflicts; retrying will not make a taken username free.

**18. Using `@Lock(PESSIMISTIC_WRITE)` for nonexistent rows assuming it locks the "gap."** Semantics vary by DB/isolation and are non-portable.

**19. Using `SERIALIZABLE` to avoid creating unique constraints.** More expensive, causes serialization failures and retries; uniqueness invariants still belong in constraints.

**20. Using `ON CONFLICT DO NOTHING` and unconditionally returning 201 Created.** You do not know whether a row was actually created; inspect the result.

**21. Using UPSERT for account registration without ownership checks.** Risks updating someone else's existing record.

**22. Using `MockRepository` to prove race safety.** Mocks do not simulate transactions, indexes, or database concurrency.

**23. Testing single-threaded only.** Misses check-then-insert concurrency; write concurrent tests and verify schema constraints.

**24. Putting `@Transactional` on a concurrency test expecting threads to share the transaction.** Thread-bound transaction contexts do not work that way.

**25. Treating `available=true` as a reservation guarantee.** It is only a snapshot; creation must still handle 409.

**26. Adding a unique index to a table with existing duplicates without migration prep.** Index creation fails; perform inventory, cleanup, and staged rollout.

## 17. Code Review Checklist

1. Is the business key clearly scoped: global or per-tenant for username/email/code?
2. Are canonicalization/collation and case, Unicode, and null behaviors defined?
3. Does an actual **UNIQUE** constraint/index exist in database migrations?
4. Does the constraint have the exact columns and soft-delete predicate?
5. Does input have Bean Validation for format, length, and required fields?
6. Are `existsBy...` or custom validators avoided as the sole protection layer?
7. If an availability check exists, does the UI treat `available` strictly as a snapshot?
8. Are DB unique conflicts handled even right after a pre-check returned "available"?
9. Are save/flush/transaction boundaries clear, especially where exceptions are caught?
10. Are exceptions caught **outside** rolled-back transactions, avoiding further writes after a DB error?
11. Are specific constraints distinguished when a table has multiple unique/FK/check rules?
12. Are safe HTTP statuses/codes returned without leaking SQL or driver internals?
13. Is there a migration/backfill cleaning duplicates before index creation?
14. Are invalid inputs, sequential duplicates, case variants, and concurrency all tested?
15. Do race tests assert **exactly one row** and **exactly one conflict** without assuming which thread wins?
16. Are tests run on a production-like database when SQL/locking semantics matter?
17. If UPSERT is used, are ownership, authorization, and retry semantics verified?
18. Is dedicated idempotency designed if safe retries are required?
19. Are unique conflicts, timeouts, and deadlocks monitored without logging sensitive data?
20. Is there a safe schema rollout/rollback plan?

**Conclusion:** "Checking if it exists" is an observation **without a reservation**. Two requests can both read "does not exist" and both insert. To preserve uniqueness under contention, **define a unique constraint/index in the database**, canonicalize keys consistently, handle write errors at the proper transaction boundary, and return safe HTTP responses. `existsBy...` or custom `@UniqueUsername` validators improve UX only and **never replace database invariants**. Real systems also need constraint classification, concurrency testing on production-like databases, and separating uniqueness from idempotency.

## 18. References

- [PostgreSQL — Constraints / Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — single/composite unique keys, null semantics, named constraints, and partial indexes.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html) — atomic conflict handling, DO NOTHING/DO UPDATE, and caveats.
- [PostgreSQL — Index Uniqueness Checks](https://www.postgresql.org/docs/current/index-unique-checks.html) — how unique indexes coordinate with MVCC and concurrent transactions.
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html) — default repository transaction boundaries and service orchestration.
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html) — `saveAndFlush`, `flush`.
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html) — Spring DAO exception family.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — `@Transactional` and transaction interceptors.
- [Jakarta Persistence — UniqueConstraint API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/uniqueconstraint) — declaring unique constraint metadata in schema DDL.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html) — validation constraints, not a substitute for DB integrity invariants.
