# TransactionTemplate: execute and executeWithoutResult in Spring Transaction Management

## 1. When Is Programmatic Transaction Control Needed?

Most Spring applications manage transactions declaratively:

```java
@Transactional
public void createOrder() {
    // DB operations.
}
```

With `@Transactional`, Spring AOP and `PlatformTransactionManager` determine when to begin, commit, or roll back at the boundary of the proxied method call. This approach is usually concise and should be preferred when most business logic has fixed transaction boundaries.

However, sometimes you need to **select a specific block of code** as a transaction without having the entire enclosing method run inside a transaction. For example: reading data from an API outside a transaction, computing a plan, and wrapping only **the final two SQL statements** in the same transaction. Or a method has multiple branches, each needing different isolation/propagation.

In those cases, Spring provides `org.springframework.transaction.support.TransactionTemplate` for **programmatic** transaction management (in code). It takes a `PlatformTransactionManager` and receives a callback containing the operations that need to run within the transaction scope.

The two APIs covered in this lesson:

```java
<T> T execute(TransactionCallback<T> action);

void executeWithoutResult(
    java.util.function.Consumer<TransactionStatus> action);
```

Both run code within a scope coordinated by the transaction manager, handling starting/joining the transaction and committing or rolling back when the callback completes. The core difference is **whether the callback returns data to the caller or not**.

- `execute(...)`: needs a **return value**, such as an order ID, total amount, a DTO, or a SELECT result.
- `executeWithoutResult(...)`: only needs to **perform an action**, without returning a business value; the method's return type is `void`.

**Important:** both receive `TransactionStatus` in the lambda. `executeWithoutResult` does not mean "cannot manually roll back"; you can call `status.setRollbackOnly()` just as with `execute`.

## 2. Where TransactionTemplate Fits in Spring

Diagram:

```text
Service / application code
   |
   +-- transactionTemplate.execute(callback)
   |       or
   +-- transactionTemplate.executeWithoutResult(callback)
                |
                v
         TransactionTemplate
                |
                v
         PlatformTransactionManager
                |
      +---------+----------+
      |                    |
      v                    v
 JDBC DataSource        JPA EntityManager
 /connection manager    /transaction manager
      |                    |
      +---------+----------+
                |
        Resource transaction:
      begin / participate / commit / rollback
```

`TransactionTemplate` itself **does not** hold DB connections and does not create tables. It needs an appropriate transaction manager:

- With Spring JDBC, you usually use `JdbcTransactionManager` or `DataSourceTransactionManager` bound to the right `DataSource`.
- With JPA, use `JpaTransactionManager` matching the `EntityManagerFactory`.
- With reactive (R2DBC/WebFlux), the corresponding mechanism is `TransactionalOperator`; do not directly apply the imperative callback model to a reactive chain and assume the transaction automatically follows asynchronous signals.

Spring Boot can auto-configure a manager if the right dependencies are present and there is only one suitable resource. In projects without Boot, these beans must be configured explicitly.

**Unlike calls through an `@Transactional` proxy:** when the application calls `transactionTemplate.execute(...)` directly, the template's transaction scope is triggered **by that method call**, regardless of whether the method containing the template call is intercepted by a Spring AOP proxy. Even so, the template still needs the right manager and DAOs must use resources participating in Spring-managed transactions.

## 3. APIs and Callbacks Differ by Return Type

### 3.1. `execute(TransactionCallback<T>)`

`TransactionCallback<T>` has one method that takes `TransactionStatus` and returns `T`:

```java
@FunctionalInterface
public interface TransactionCallback<T> {
    T doInTransaction(TransactionStatus status);
}
```

This is a **simplified signature for explanation**, not code to redefine the interface in your project. `TransactionTemplate.execute(...)` returns the result produced by the callback; in a normal new transaction, commit/rollback is handled by the template after the callback returns.

Example when a newly created ID is needed:

```java
Long id = tx.execute(status -> {
    jdbc.update(
        "INSERT INTO customers(id, name) VALUES (?, ?)",
        42L, "Mai");
    return 42L;
});
```

This example uses `JdbcTemplate` and an already created `customers` table; it is an **illustrative code snippet**. When the callback finishes, the template attempts to complete the transaction and only then does `execute` return the result. The return value can be `null` if the callback returns `null`.

Important:

- `return 42L` inside the lambda **does not** mean "`COMMIT` just executed at the return statement".
- If the code calls `status.setRollbackOnly()` and still executes `return 42L`, the caller **can still receive 42L**, even though the DB changes rolled back. **The callback result is not proof of commit.**
- If the callback throws a `RuntimeException` or `Error` outward, the template usually requests a rollback per contract and propagates the error to the caller.
- If the manager's commit or rollback fails, the caller may receive a `TransactionException`/related exception instead of the callback value.

### 3.2. `executeWithoutResult(Consumer<TransactionStatus>)`

When no data needs to be returned:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "UPDATE customers SET active = ? WHERE id = ?",
        true, 42L);
});
```

This is also an illustrative snippet: `tx` is a `TransactionTemplate` or `TransactionOperations` with a real manager, and `jdbc` is properly configured.

**Consumer takes one `TransactionStatus` parameter.** The syntax is `status -> { ... }`, **not** a `Runnable` like `() -> { ... }`. The callback does not need to write `return null`. A plain `return;` can be used to exit the `void` callback early while still going through the template's transaction completion logic.

Example marking rollback:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO customers(id, name) VALUES (?, ?)",
        43L, "An");

    boolean rejected = true;
    if (rejected) {
        status.setRollbackOnly();
        return;
    }
});
```

If the template started a new physical transaction and there are no other errors, the record with ID 43 will roll back even though the callback **did not throw an exception**.

### 3.3. A Method Returning No Result Does Not Mean "Fire-and-Forget"

`executeWithoutResult` **runs synchronously**, just like `execute` in the imperative model. The caller does not receive a business value, but Spring still must handle transaction completion before the call returns normally. If the callback throws a runtime exception, the error still propagates to the caller.

Do not confuse `executeWithoutResult` with:

- `@Async`, `CompletableFuture.runAsync(...)`, or offloading work to another thread.
- An auto-committing SQL call independent of transactions.
- A method that only runs writes: a `void` callback can still SELECT or perform other operations.

## 4. Quick Comparison of the Two Methods

| Criterion | `execute(...)` | `executeWithoutResult(...)` |
| --- | --- | --- |
| Input | `TransactionCallback<T>` | `Consumer<TransactionStatus>` |
| Callback signature | Receives `status`, returns `T` | Receives `status`, returns no value |
| API return type | `T` (nullable) | `void` |
| Use when | Generating an ID, returning a DTO, count, business result | Inserting/updating/logging an operation that needs no return value |
| Access to `TransactionStatus`? | Yes | **Yes** |
| Can call `setRollbackOnly()`? | Yes | **Yes** |
| Runtime exception escaping callback | Template rolls back per contract and propagates error | Same |
| Callback completes normally | Template attempts to complete transaction (commit if appropriate) | Same |
| Need to call `commit()` manually? | No | No |
| Works with Java lambdas? | Yes | Yes |
| Suitable when an outer transaction exists? | Yes, per template propagation | Yes, per template propagation |

**Choose the API by return requirement**, not by perceived "safety", not by SELECT/UPDATE statement type, and not by commit intent. Both APIs share the same transaction infrastructure.

## 5. A Typical Transaction Lifecycle

Suppose the transaction manager manages a JDBC connection and the template uses default `PROPAGATION_REQUIRED`:

```text
Caller
  |
  v
transactionTemplate.execute(callback)
  |
  +-- obtain transaction from PlatformTransactionManager
  |       if none exists -> open transaction T
  |       if one exists -> usually join T
  |
  +-- run callback(status)
  |       +-- SQL 1
  |       +-- SQL 2
  |       +-- return result / finish void
  |
  +-- if completed normally and not rollback-only
  |       -> manager attempts to commit new transaction owned by scope
  |
  +-- if callback throws RuntimeException/Error
  |       -> manager handles scope rollback
  |
  +-- if status.setRollbackOnly()
  |       -> manager handles rollback/marking rollback-only
  |
  +-- release/cleanup necessary resources
  v
Caller receives result (execute) / finishes void
or receives exception
```

This picture intentionally distinguishes **logical transaction scope** and **physical transaction**. If the template only joins an already-open outer transaction, the callback ending **does not commit the physical transaction by itself**; the outer scope still decides completion. With `PROPAGATION_NESTED`, rollback can revert to a savepoint if supported by the manager. With `REQUIRES_NEW`, the template opens an independent physical transaction under suitable conditions.

A simplified diagram "execute finished means committed" is only accurate when the template **owns a new transaction**, the manager commits successfully, there are no errors/rollback-only flags, and no outer scope owns the same physical transaction.

### 5.1. What Does `TransactionStatus` Report?

Commonly useful methods:

```java
tx.executeWithoutResult(status -> {
    boolean newTransaction = status.isNewTransaction();
    boolean rollbackRequested = status.isRollbackOnly();

    System.out.println("new=" + newTransaction
        + ", rollbackOnly=" + rollbackRequested);
});
```

If code runs with default `REQUIRED` and no outer transaction, `new=true` is typically observed. However, `isNewTransaction()` is not a check that all SQL has committed; during the callback, the transaction is still executing.

Methods worth knowing:

| `TransactionStatus` API | Meaning |
| --- | --- |
| `isNewTransaction()` | Whether the current scope is a new transaction according to the manager |
| `isRollbackOnly()` | Whether the status is marked rollback-only |
| `setRollbackOnly()` | Requests a rollback outcome when the manager completes the scope |
| `hasSavepoint()` | Whether the status has a manager-created JDBC savepoint |
| `isCompleted()` | Whether the status has completed; normally not completed inside the callback |
| `flush()` | Requests a flush if supported by manager/resource; **not a commit** |

Do not use `status.isCompleted()` to check commit **inside** the callback; transaction completion happens after Spring returns from the callback and processes completion. Nor does `flush()` make changes durable: the transaction can still roll back.

## 6. Exceptions and Rollback: Identical in Both APIs

### 6.1. Runtime Exception

```java
try {
    tx.executeWithoutResult(status -> {
        jdbc.update(
            "INSERT INTO events(id, label) VALUES (?, ?)",
            10L, "before-error");
        throw new IllegalStateException("business failure");
    });
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
```

This is an illustrative snippet; the `events` table and `jdbc` field must exist. With a new Spring JDBC transaction, the executed INSERT is rolled back, and then the caller receives `IllegalStateException`. If an error arises before the callback begins or from the database/manager itself, a transaction error can also propagate out.

### 6.2. Proactively Rolling Back Without Throwing an Exception

```java
String decision = tx.execute(status -> {
    jdbc.update(
        "INSERT INTO events(id, label) VALUES (?, ?)",
        11L, "will-rollback");

    status.setRollbackOnly();
    return "REJECTED";
});
```

With a new transaction, the callback returns `"REJECTED"` and the template can return this string to the caller **after processing the rollback**. No record with ID 11 exists in the DB. This scenario is useful for returning a business result instead of an exception, but the application must **understand the result code clearly**; never assume that getting a response means it committed.

Void variant:

```java
tx.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO events(id, label) VALUES (?, ?)",
        12L, "also-rollback");
    status.setRollbackOnly();
});
```

The DB outcome is the same, though the caller does not receive a direct business result.

### 6.3. Catching and Swallowing Errors Inside the Callback

```java
tx.executeWithoutResult(status -> {
    try {
        riskyOperation();
    } catch (IllegalArgumentException ex) {
        // Only log, do not rethrow, do not mark rollback-only.
    }
});
```

This is illustrative code with an undefined helper. When the callback completes normally without rollback-only or other transaction errors, the template can **commit** SQL statements executed before the error. An exception caught inside the callback **does not automatically trigger the template's rollback policy**.

When business rules require aborting the operation, do one of the following:

- Let an appropriate exception **escape the callback**; or
- Call `status.setRollbackOnly()` and return a clear failure result; or
- Rethrow after logging, rather than catching and ignoring.

### 6.4. Checked Exceptions in Callback Lambdas

`TransactionCallback.doInTransaction(...)` and `Consumer.accept(...)` **do not declare `throws IOException` or arbitrary checked exceptions**. Therefore, the following snippet **does not compile** if `performIO()` declares `throws IOException` without being caught:

```java
// INVALID if performIO() declares throws IOException:
tx.execute(status -> {
    performIO();
    return "done";
});
```

The error must be adapted to the appropriate contract. For instance, if an I/O error must roll back the transaction:

```java
String result = tx.execute(status -> {
    try {
        performIO();
        return "DONE";
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("I/O failure", ex);
    }
});
```

This is illustrative code; `performIO()` is an undefined method. `IllegalStateException` is a runtime exception, so the template will request rollback and propagate the exception to the caller.

If the checked error is a business outcome that the caller **does not want thrown**:

```java
String result = tx.execute(status -> {
    try {
        performCheckedBusinessStep();
        return "ACCEPTED";
    } catch (BusinessCheckedException ex) {
        status.setRollbackOnly();
        return "REJECTED";
    }
});
```

The helpers/exception are illustrative. This approach requires the caller to treat the `"REJECTED"` string as an **uncommitted** result. If you need to preserve the checked exception in the API, you can pass it via a runtime wrapper and unwrap/convert it at the outer boundary after the transaction has been handled, taking care with the root cause.

**Do not assume `@Transactional(rollbackFor=...)` automatically applies to lambdas inside `TransactionTemplate`.** The template has its own exception/callback rules; it does not inspect annotations on lambdas to add rollback rules.

## 7. Complete Runnable Example: Spring Boot, Java 17, H2

We will build a **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2 in-memory** application. The example uses only **programmatic transactions**; the service has no `@Transactional`. We will observe:

1. `execute` both INSERTing and returning the total record count.
2. `executeWithoutResult` INSERTing without returning a result.
3. `execute` calling `setRollbackOnly()` while still returning a string.
4. `executeWithoutResult` throwing a runtime exception and rolling back automatically.

All of these cases will be verified by reading the DB **after the template call has finished**.

### 7.1. File Structure

```text
transaction-template-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/
    ├── java/demo/template/
    │   ├── TemplateApplication.java
    │   └── TemplateLedgerService.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

The Gradle Wrapper can be generated by Spring Initializr or `gradle wrapper` with a compatible Gradle version; the structure listing shows where to place the required files.

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-template-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot JDBC starter provides `JdbcTemplate` and transaction infrastructure, automatically managing Spring module versions; the H2 driver is loaded at runtime. There is no need to manually add a separate `spring-tx` version or JPA to run this lab.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:templatelab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_events (
    id BIGINT PRIMARY KEY,
    label VARCHAR(40) NOT NULL
);
```

Spring Boot runs the SQL initializer for the embedded DB at startup, creating an empty table before `CommandLineRunner` executes. In-memory H2 lives per JVM; each new JVM run starts from empty data, so the output below is deterministic. `DB_CLOSE_DELAY=-1` only extends DB lifetime until the JVM stops, without turning it into a disk-persisted database.

### 7.2. Service: Both APIs on the Same TransactionTemplate

**`src/main/java/demo/template/TemplateLedgerService.java`**

```java
package demo.template;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TemplateLedgerService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    public TemplateLedgerService(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {

        this.jdbc = jdbc;
        this.tx = new TransactionTemplate(manager);
    }

    // execute: callback returns the number of records in the transaction.
    public Long createAndCount(long id, String label) {
        return tx.execute(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, label);

            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class);
        });
    }

    // executeWithoutResult: does not return a business value.
    public void writeAudit(long id, String label) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, label);
        });
    }

    // execute: still has a return value even though the transaction rolls back.
    public String rollbackAndReturn(long id) {
        return tx.execute(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, "rollback-only");

            status.setRollbackOnly();
            return "computed";
        });
    }

    // executeWithoutResult: unchecked exception triggers rollback.
    public void insertThenFail(long id) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                "INSERT INTO tx_events (id, label) VALUES (?, ?)",
                id, "will-fail");

            throw new IllegalStateException("simulated failure");
        });
    }
}
```

Explanation of design decisions:

- `TemplateLedgerService` is created by Spring, receiving `JdbcTemplate` and `PlatformTransactionManager` via constructor injection.
- `new TransactionTemplate(manager)` is created **once** and kept as a `final` field. The template holds no per-request conversational state and can be reused when configuration does not change.
- Service methods **do not** need `@Transactional` because the code opens scopes explicitly via the template.
- `createAndCount` returns `Long` from `COUNT(*)`. `COUNT(*)` in H2 is a large integer type; `Long.class` is used for type clarity.
- `writeAudit` uses a void callback because the caller does not need a value; `JdbcTemplate.update` still returns an update count, which the callback intentionally ignores.
- `rollbackAndReturn` requests rollback after INSERT and then returns `"computed"`. This intentionally proves **the return value from `execute` is not proof of a successful write**.
- `insertThenFail` illustrates rollback when a runtime exception escapes a `Consumer<TransactionStatus>` lambda.

### 7.3. Main and Verification Output

**`src/main/java/demo/template/TemplateApplication.java`**

```java
package demo.template;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TemplateLedgerService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + rows(jdbc));

            Long count = service.createAndCount(1L, "create");
            System.out.println("execute result: " + count);
            System.out.println("After execute: " + rows(jdbc));

            service.writeAudit(2L, "audit");
            System.out.println(
                "After executeWithoutResult: " + rows(jdbc));

            String result = service.rollbackAndReturn(3L);
            System.out.println("rollbackOnly result: " + result);
            System.out.println(
                "After rollbackOnly: " + rows(jdbc));

            try {
                service.insertThenFail(4L);
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }
            System.out.println("After exception: " + rows(jdbc));
        };
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, label FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + ":" + rs.getString("label"));
    }
}
```

**Run in the project directory containing the Gradle Wrapper:**

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ignoring Spring/Gradle startup logs, the `System.out.println` lines are printed in order:

```text
Before: []
execute result: 1
After execute: [1:create]
After executeWithoutResult: [1:create, 2:audit]
rollbackOnly result: computed
After rollbackOnly: [1:create, 2:audit]
Caught: simulated failure
After exception: [1:create, 2:audit]
```

**Why is each result right?**

1. The table starts empty.
2. `createAndCount` INSERTs ID 1, runs SELECT COUNT in the same transaction, returns 1, and the manager commits successfully before `execute` completes; DB has ID 1.
3. `writeAudit` INSERTs ID 2 in the void callback, manager commits; DB has 1 and 2.
4. `rollbackAndReturn` INSERTs ID 3, marks rollback-only, and returns the string; the template rolls back before returning. The caller **receives `computed`**, yet the DB still only has IDs 1 and 2.
5. `insertThenFail` INSERTs ID 4 and throws `IllegalStateException`; the template rolls back, and the caller catches the error. The DB still only has IDs 1 and 2.

These values assume no outer transaction wraps the runner, H2/manager behave normally, no other actor modifies the table, and the code matches what is shown. The runner **does not** use `@Transactional` and re-reads the table after each template call, thus measuring completed outcomes.

This is a **complete Spring Boot project when the files are placed in the proper locations with a Gradle Wrapper**. The standalone Java snippets in earlier sections are illustrative fragments, not files runnable with just `javac` without the Spring classpath.

## 8. Writing Tests for Commit and Rollback Outcomes

If you want to turn the conclusions into automated tests, add the file:

**`src/test/java/demo/template/TemplateLedgerServiceTest.java`**

```java
package demo.template;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class TemplateLedgerServiceTest {

    @Autowired
    private TemplateLedgerService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    @Test
    void executeReturnsCountAndCommits() {
        assertEquals(1L, service.createAndCount(100L, "test"));
        assertEquals(
            1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }

    @Test
    void executeWithoutResultAndRollbackOnly() {
        service.writeAudit(101L, "audit");
        assertEquals("computed", service.rollbackAndReturn(102L));
        assertEquals(
            1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }

    @Test
    void runtimeFailureRollsBack() {
        assertThrows(
            IllegalStateException.class,
            () -> service.insertThenFail(103L));
        assertEquals(
            0L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events",
                Long.class));
    }
}
```

Run:

```bash
./gradlew test
```

The test intentionally **does not** have `@Transactional` on the test class or methods. If the test is automatically wrapped in a transaction by Spring TestContext, an outer transaction can affect commit timing and visibility; the test would no longer directly measure a new transaction owned by the template.

When using `@SpringBootTest`, the application's `CommandLineRunner` may run during context startup; the test's `@BeforeEach` clears the demo table before each test, guaranteeing expected counts. Only use this reset SQL in a dedicated test database. If running tests in parallel sharing one H2 database, isolate data/test contexts to avoid races.

**Proper testing requires observing the database after the method has completed**; checking `status.isRollbackOnly()` inside the callback only confirms the flag, not replacing actual rollback verification.

## 9. Declaring TransactionTemplate and Transaction Attributes

### 9.1. Constructor and Default Configuration

Basic way:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
```

`manager` is a configured `PlatformTransactionManager`. The template uses `DefaultTransactionDefinition` defaults:

| Attribute | Common default |
| --- | --- |
| `propagation` | `PROPAGATION_REQUIRED` |
| `isolation` | `ISOLATION_DEFAULT` |
| `timeout` | `TIMEOUT_DEFAULT` (usually `-1`) |
| `readOnly` | `false` |
| `name` | No dedicated name set |

Can be set once when building the bean:

```java
@Configuration
public class TxTemplateConfig {

    @Bean
    TransactionTemplate orderTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.setTimeout(30);
        tx.setReadOnly(false);
        tx.setName("order-processing");
        return tx;
    }
}
```

This is an **illustrative configuration snippet**, requiring imports for `@Configuration`, `@Bean`, `TransactionTemplate`, `TransactionDefinition`, `PlatformTransactionManager`, and appropriate injection/qualifiers if multiple managers/templates exist. Do not add this class to the project in section 7 unless intentionally changing the demo configuration; that project already creates a default template in its service.

`timeout` and `isolation` are mainly meaningful when **a new transaction is opened** and supported by the manager/database. If `REQUIRED` joins an existing transaction, the template's own timeout/isolation are not automatically reapplied to the outer physical transaction. With strict manager validation, an explicit isolation mismatch can throw an error rather than being ignored.

### 9.2. Thread Safety and Sharing Instances

Spring documents `TransactionTemplate` as thread-safe for execution because the template **does not hold per-transaction conversation state**. However, the template has **configuration state** (propagation, timeout, read-only, isolation, name). If multiple services use the same policy, they can share a statically configured template.

**Do not do this in multi-threaded code:**

```java
sharedTx.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE);
sharedTx.execute(status -> doWorkA());

sharedTx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED);
sharedTx.execute(status -> doWorkB());
```

Two threads concurrently mutating configuration on a shared instance can cause calls to run under unintended policies. Create **two independently configured `TransactionTemplate` instances**, e.g., one for `READ_COMMITTED` and one for `SERIALIZABLE`, and treat those configurations as immutable after initialization.

**Distinction:** `TransactionStatus` is created per callback execution; do not keep status in a shared field and do not store it for processing after the template finishes.

### 9.3. Some Important Propagations

| Template propagation | When caller already has a physical transaction | Main outcome |
| --- | --- | --- |
| `REQUIRED` | Joins existing transaction | Outer caller owns the final commit |
| `REQUIRES_NEW` | Suspends outer transaction when supported by manager and opens a new transaction | Inner outcome is more independent; may require another connection |
| `NESTED` | Joins physical transaction via savepoint if supported | Inner rollback can revert to savepoint |
| `SUPPORTS` | Joins if present; can run without an actual transaction if absent | Does not guarantee a new transaction |
| `MANDATORY` | Requires outer to exist | Throws error if no transaction exists |
| `NOT_SUPPORTED` | Suspends outer; runs without an actual transaction | Unsuitable if an atomic SQL group like the examples is needed |

`setRollbackOnly()` has different meaning when the template **owns a new transaction** versus when it **joins an outer scope**. With `REQUIRED` joining a shared transaction, Spring can mark **the shared transaction rollback-only**; the outer side trying to commit later may get `UnexpectedRollbackException`. With `NESTED`, a JDBC manager supporting savepoints can roll back just the nested portion. Do not assume every `executeWithoutResult` call owns its own physical transaction.

### 9.4. Transaction Name

`TransactionTemplate` inherits configuration from `DefaultTransactionDefinition`, allowing a name to be set:

```java
tx.setName("settle-invoice");
```

The name can aid logging/monitoring and transaction metadata per supporting manager. Do not reset the name on a shared template per request; if different business operations need different transaction names, create separate templates or manage definitions appropriately. A transaction name is not a global SQL transaction identifier.

## 10. execute and executeWithoutResult When Joining an Outer Transaction

This is the easiest place to get confused if learning only from examples without an outer transaction.

Suppose a facade has already opened transaction T with `@Transactional` and calls a service using default `REQUIRED` `TransactionTemplate`:

```java
@Transactional
public void outerBusinessOperation() {
    // Write A in transaction T.

    helperService.usingTemplate();

    // Write C in transaction T.
}
```

If `helperService.usingTemplate()` calls:

```java
tx.executeWithoutResult(status -> {
    // Write B in the same transaction T if manager/resource align.
});
```

then **the callback completing normally does not commit T on its own**. T is still managed by outer; if outer rolls back, A/B/C can all be discarded.

If inner does:

```java
tx.executeWithoutResult(status -> {
    status.setRollbackOnly();
});
```

it can cause T to be marked rollback-only. If outer catches/continues and tries to commit, Spring may throw `UnexpectedRollbackException`. Avoid using a return value or "callback finished" signal to claim the transaction committed when running inside an outer scope.

**Be careful with overlapping annotations and templates:** A method having both `@Transactional` and a `REQUIRED` template typically creates **two logical scopes participating in the same physical transaction**, not two independent commits. Identify the real boundary instead of nesting just to feel "extra sure".

## 11. Business Flow Example: Narrowing Transaction Hold Time

A clear benefit of the programmatic style is keeping non-DB-transaction activities outside:

```java
public Receipt process(Request request) {
    // 1. Do not hold a DB transaction during long steps.
    ExternalQuote quote = quoteClient.fetchQuote(request);
    ValidatedOrder valid = validator.validate(request, quote);

    // 2. Wrap only the SQL part needing atomicity.
    Receipt receipt = tx.execute(status -> {
        long orderId = orders.insert(valid);
        inventory.reserve(valid);
        return new Receipt(orderId, valid.total());
    });

    // 3. Perform post-commit step only when execute returned normally
    //    and the template genuinely owns the commit boundary.
    notifier.scheduleReceipt(receipt);
    return receipt;
}
```

This snippet is **illustrative Java pseudocode**, with undefined `Request`, `Receipt`, `ExternalQuote`, repositories, and services. Recommended order: prepare/validate outside, use `execute` for the SQL region needing a result, then dispatch notification through a suitable mechanism.

However, there are limits:

- If the `REQUIRED` template **joins an outer transaction** instead of opening its own, code after `execute` **can run before the outer commit**. Do not call it truly after-commit without boundary evidence.
- If `status.setRollbackOnly()` was called yet the callback still returned `Receipt`, subsequent code might process an unsaved receipt.
- If the HTTP/email notification fails after DB commit, the local transaction does not automatically roll back the DB result; outbox/compensation/idempotency are needed per business rules.
- If reliable post-commit event emission is required, use properly designed transaction synchronization/transactional outbox; do not rely mechanically on the position of a Java line.

## 12. Distinguishing TransactionTemplate from @Transactional and Direct Manager Calls

| Criterion | `TransactionTemplate` | `@Transactional` | Direct `PlatformTransactionManager` |
| --- | --- | --- | --- |
| How boundary is defined | Callback code block | Annotation on method/type | Obtaining status and calling commit/rollback manually |
| Manages transaction boilerplate? | **Yes** | **Yes** | Mostly must be written manually |
| Needs Spring AOP proxy for the boundary itself? | **No** | Usually **yes** in proxy mode | No |
| Returns result from boundary? | `execute` returns `T`; void API is separate | Java method returns its value | Organized manually by caller |
| Policy configuration | Properties on template | Annotation attributes | `TransactionDefinition` created in code |
| Coupling to Spring APIs in business code | Higher | Lower | Highest |
| Suitable for | Specific transaction blocks, dynamic scopes | Many service methods with stable boundaries | Framework/infra or very low-level control needs |

Most projects should prefer declarative `@Transactional` to keep business code readable. `TransactionTemplate` is very useful when only **part of a method** needs a transaction or when wanting to configure specific policies. Calling the manager directly:

```java
TransactionStatus status = manager.getTransaction(definition);
try {
    doWork();
    manager.commit(status);
} catch (RuntimeException ex) {
    manager.rollback(status);
    throw ex;
}
```

is an **illustrative fragment** and may require extra handling for failures in `commit`, `rollback`, `Error`, transaction ownership, and lifecycle status. You should not write this boilerplate yourself when `TransactionTemplate` already handles it.

## 13. Common Mistakes and Misconceptions

### 13.1. Returning `null` from `execute` and Thinking the Transaction Won't Commit

`execute` allows the callback to return `null`. That **does not automatically roll back**. If a method only executes SQL and needs no result, `executeWithoutResult` expresses the intent better:

```java
// Valid but verbose:
tx.execute(status -> {
    jdbc.update("DELETE FROM tx_events WHERE id=?", 7L);
    return null;
});

// Clearer intent:
tx.executeWithoutResult(status ->
    jdbc.update("DELETE FROM tx_events WHERE id=?", 7L));
```

Both snippets can produce the same DB result under the same transaction definition, but only the second API intentionally returns `void`.

### 13.2. Writing a Lambda with the Wrong Signature

Wrong:

```java
tx.executeWithoutResult(() -> {
    performOperation();
});
```

Because `executeWithoutResult` accepts `Consumer<TransactionStatus>`, the lambda must take **one** parameter:

```java
tx.executeWithoutResult(status -> {
    performOperation();
});
```

`performOperation()` is an illustrative helper. You do not have to use `status` inside the body, but the parameter is still required in the lambda.

Another mistake:

```java
tx.executeWithoutResult(status -> {
    performOperation();
    return 42; // Does not compile: void callback.
});
```

If 42 is needed, use `tx.execute(status -> { performOperation(); return 42; })`.

### 13.3. Calling `status.setRollbackOnly()` and Still Reporting "Success"

A callback can return a value or return void even after requesting rollback. Choose a clear `FAILED/REJECTED` result or throw an appropriate exception; do not use a successful HTTP response or freshly computed ID as proof that the DB committed.

### 13.4. Catching an Exception Inside the Callback and Swallowing It

If the callback returns normally, the template does not know the application considered an error severe. Let the exception escape or call `setRollbackOnly()`. Do not catch a broad `Exception` and then try to commit a DB transaction that can no longer operate.

### 13.5. Thinking Any Checked Exception Can Be Thrown Straight from the Lambda

`TransactionCallback`/`Consumer` do not declare arbitrary checked `throws`. You must catch and handle, wrap as runtime, or design a result contract. Do not confuse this with `@Transactional(rollbackFor=CheckedException.class)` in the declarative approach.

### 13.6. Creating a Template with the Wrong Transaction Manager

If `JdbcTemplate` uses DataSource A while the template points to the transaction manager of DataSource B, the two parts **do not naturally form the same transaction**. With multiple managers, use the right bean/qualifier and test rollback after real SQL.

### 13.7. Accessing Resources Outside the Transaction

A DAO creating its own connection via `DriverManager.getConnection(...)` may not use the connection bound by Spring on the thread. `TransactionTemplate` does not turn such SQL into a shared transaction merely by wrapping the callback. Use `JdbcTemplate` on the same DataSource or a verified transaction-participating mechanism.

### 13.8. Returning a Lazy Collection/Stream from `execute`

```java
Stream<Order> stream = tx.execute(status -> {
    return repository.streamAllOrders();
});
```

This snippet is illustrative; `Order`/repository are undefined. If the stream must be consumed inside the transaction while the caller only iterates **after `execute` ends**, the persistence context/connection may already be closed or the transaction gone. Return fully materialized values inside the callback, or design appropriate consumption/transaction boundaries.

### 13.9. Thinking `executeWithoutResult` Runs in the Background

Both APIs run **synchronously**; they do not replace queues, threads, or schedulers. If the callback creates a new thread itself, the thread-bound JDBC transaction **does not automatically propagate** to that thread. Let each async task intentionally own its own transaction.

### 13.10. Mutating Template Configuration After Multiple Requests Already Use It

The template is thread-safe for `execute` calls **with stable configuration**; do not change propagation/isolation/timeout on a singleton while other threads are using it. Use multiple independent templates when different policies are needed.

### 13.11. Automatically Assuming Any SQL Error Can Be Retried

Deadlocks, constraint violations, serialization failures, and connection errors have different treatments. Some errors require aborting the transaction and retrying **the entire scope**; some are data errors that should not be retried. In particular, external side effects inside the callback can be duplicated on retry.

## 14. Checklist for Designing a Safe Transaction Callback

Before putting `TransactionTemplate` into production:

1. Identify the **transaction manager and DataSource/EntityManagerFactory** being used; do not choose by vague names when multiple beans exist.
2. Choose `execute` if a value genuinely needs to be returned; use `executeWithoutResult` when there is no result.
3. Put the exact SQL needing atomicity **inside the same callback**. Do not let a related SQL statement accidentally run outside the boundary.
4. Choose propagation intentionally. If `REQUIRED` can join an outer transaction, do not assume the callback finishing means the physical commit is done.
5. Declare isolation/read-only/timeout when there is a verified need; do not arbitrarily raise isolation or hold transactions too long.
6. For exceptions, define which errors must roll back; do not swallow errors and return success.
7. With `setRollbackOnly()`, reflect the failure outcome in the return object/status; do not treat the callback result as a commit receipt.
8. Avoid long network calls, sleep, waiting for user input, or emitting external side effects directly inside the callback.
9. Do not modify a shared template's configuration after initialization.
10. Test success paths, unchecked exceptions, explicit rollback-only, missing data, and DB constraint failures.
11. Test outside automatic test transactions if the goal is to verify **physical commits**.
12. For reactive code, use `TransactionalOperator`, not the imperative template on a publisher assuming the scope stays alive until a subscriber consumes it.

## 15. Self-Assessment Questions

**1. When should you use `execute` instead of `executeWithoutResult`?**

When the callback needs to return a business value to the caller, such as an order ID, SELECT result, DTO, or count. Do not choose based on whether the SQL is SELECT or UPDATE.

**2. Can `executeWithoutResult(status -> ...)` access `TransactionStatus`?**

Yes. The lambda receives `TransactionStatus` and can call `status.setRollbackOnly()`. The method name only states it **does not return a result object** to the caller.

**3. Can `execute(status -> { status.setRollbackOnly(); return 42; })` return 42?**

Yes, if rollback completes normally in a new transaction; the callback return value can be returned even though the DB rolls back. Therefore, 42 is not proof of commit.

**4. Does `executeWithoutResult` automatically launch the task on another thread?**

No. It is a synchronous API managing the transaction scope on the current execution path. If you explicitly create another thread, the transaction does not automatically propagate to that thread.

**5. Why can two SQL statements in the same callback roll back together?**

Because the transaction manager manages the same transaction/resource, and the template wraps the entire callback in one transaction scope according to propagation. If a DAO uses a separate connection outside Spring, this guarantee no longer holds automatically.

**6. When a `REQUIRED` template is called inside an outer `@Transactional`, does the callback returning commit the DB right away?**

Not necessarily. The template usually joins the outer transaction and the outer owner still decides the physical commit.

**7. How does `TransactionCallbackWithoutResult` differ from `executeWithoutResult`?**

`TransactionCallbackWithoutResult` is the older anonymous-class-style callback used with `execute(new TransactionCallbackWithoutResult() {...})`. `executeWithoutResult` is a convenience method accepting `Consumer<TransactionStatus>`, easy to use with lambdas and returning `void`. In Spring 7, the older callback class has been marked deprecated; the newer lambda option is generally clearer.

**8. If the callback catches `IOException` and returns normally, does it roll back?**

Not automatically just because an `IOException` was caught. You need to mark rollback-only or convert the error into a runtime exception escaping the callback when business rules require rollback.

**9. Should you construct a new `TransactionTemplate` on every request and keep changing its configuration?**

Usually unnecessary. You can create it once, keep configuration stable, and share by policy; create another instance if different isolation/propagation is needed.

## 16. Takeaways

`TransactionTemplate` provides programmatic transaction boundaries via a callback mechanism:

- **`execute(TransactionCallback<T>)`**: runs code and returns `T` (nullable).
- **`executeWithoutResult(Consumer<TransactionStatus>)`**: runs code, returns `void`, and still allows interacting with `TransactionStatus`.
- For a new transaction owned by the template, if the callback completes normally and is not rollback-only, the manager attempts to commit; throwing an unchecked exception or calling `status.setRollbackOnly()` rolls back.
- **A return value is not a commit certificate**, and completion of a scope joining an outer transaction is not a physical commit.
- The template is thread-safe when used with a stable configuration, but does not manage one connection/transaction across arbitrary threads regardless of context.
- In most service methods, `@Transactional` remains a great way to express boundaries; use the template when a specific block of code or intentional programmatic policy is needed.

To quickly verify understanding, run the H2 project in section 7: after `execute` and `executeWithoutResult` succeed, the DB has IDs 1 and 2; after the callback returning a string with `setRollbackOnly`, and after the callback throwing a runtime exception, the DB **still only has IDs 1 and 2**.

## Official References

- Spring Framework — *Programmatic Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — *Choosing Between Programmatic and Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-decl-vs-prog.html
- Spring Framework 6.2 — *TransactionTemplate API*: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework 6.0 — *TransactionOperations API* (includes `executeWithoutResult`, available since 5.2): https://docs.spring.io/spring-framework/docs/6.0.3/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework — *TransactionStatus API*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — *TransactionDefinition API*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.3 — *SQL Databases*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
