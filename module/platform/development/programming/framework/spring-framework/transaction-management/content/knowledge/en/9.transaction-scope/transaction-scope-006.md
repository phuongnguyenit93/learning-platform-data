# setValidateExistingTransaction and Detecting Incompatible Configuration in Spring Transaction Management

## 1. Objective and problem to solve

When multiple services call one another, each method can declare its own transaction attributes via `@Transactional`, for example:

- Outer service: `@Transactional(isolation = Isolation.READ_COMMITTED)`.
- Inner service: `@Transactional(isolation = Isolation.SERIALIZABLE)`.
- Or a read-only outer service: `@Transactional(readOnly = true)`, while the inner service requests read-write access: `@Transactional(readOnly = false)`.

If both methods use `Propagation.REQUIRED` (the default), the inner method typically **joins the same physical transaction** already opened by the outer method. It **does not automatically upgrade isolation** or flip the read-only attribute of the JDBC connection merely because the inner method carries a different annotation. By default, Spring accepts this participation in a fairly *lenient* manner, allowing incompatible configurations to be ignored without an error.

`setValidateExistingTransaction(true)` is an option on several **Spring transaction managers** to switch to strict checking when a method is about to **join an existing transaction**. When a conflict covered by this policy is detected, Spring rejects participation and throws `IllegalTransactionStateException` instead of silently using the outer transaction's attributes.

After this lesson you will:

1. Understand when validation is actually invoked and why outer's isolation/read-only governs.
2. Know how to enable `setValidateExistingTransaction(true)` on the appropriate transaction manager.
3. Accurately distinguish **isolation conflicts**, **one-way read-only conflicts**, `Isolation.DEFAULT`, timeouts, and other propagations.
4. Run a **Java 17 + Spring Boot + JDBC + H2** example to observe results with validation enabled and disabled.
5. Choose a business-appropriate configuration fix instead of turning validation off just to make the error disappear.

> **Core focus:** This is a **compatibility check when joining an existing transaction**, not a general validator for all `@Transactional` attributes, not a data-write security mechanism, and not an algorithm that automatically upgrades database isolation.

## 2. Logical transaction and physical transaction

A familiar example:

```java
@Service
public class OrderService {
    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void placeOrder() {
        // Write order...
        inventory.reserve();
    }
}

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserve() {
        // Write inventory...
    }
}
```

This is **abbreviated illustrative code**; real projects require imports, beans, and repositories. Assume `placeOrder()` is called through a Spring proxy, and `inventory.reserve()` is also a call through the proxy of **another bean**.

With `REQUIRED`, the typical flow is:

```text
Caller
  |
  v
OrderService proxy
  |-- no transaction yet
  |-- create PHYSICAL transaction: READ_COMMITTED
  |-- open logical transaction of placeOrder()
  v
placeOrder()
  |
  v
InventoryService proxy
  |-- detect existing PHYSICAL transaction
  |-- open logical scope of reserve(), join same transaction
  |-- reserve() requests SERIALIZABLE
  |
  +-- validateExistingTransaction=false:
  |      continue with outer's READ_COMMITTED
  |
  +-- validateExistingTransaction=true:
         reject mismatch, IllegalTransactionStateException
```

A **logical transaction** is the boundary declared by each transactional method. A **physical transaction** is the real transaction controlled by the connection/resource transaction manager. With `REQUIRED` joining an existing transaction, both logical scopes share **one** physical transaction.

Therefore:

- An inner method requesting `SERIALIZABLE` does not mean it gets a new `SERIALIZABLE` physical transaction.
- If it truly needs an independent transaction, `REQUIRES_NEW` is a different design choice, **not** a way to change the isolation of an existing `REQUIRED` transaction.
- If the entire business operation needs the same isolation, set a consistent policy at the transaction owner/outer boundary and avoid conflicting declarations on child methods.

## 3. What is `setValidateExistingTransaction` and what is its default?

The key API resides on:

```java
org.springframework.transaction.support.AbstractPlatformTransactionManager
    .setValidateExistingTransaction(boolean validateExistingTransaction)
```

`AbstractPlatformTransactionManager` is the base class for many **imperative** managers, including `DataSourceTransactionManager`, `JdbcTransactionManager`, and `JpaTransactionManager`. This setter is a configuration **on the transaction manager bean**, not an attribute of the `@Transactional` annotation.

| Value | When a regular scope joins an existing transaction |
| --- | --- |
| `false` (default) | Permits participation; inner's separate isolation/read-only declarations may be ignored, outer governs |
| `true` | Validates explicit isolation and supported read-only incompatibility; if a conflict is found, throws `IllegalTransactionStateException` before running the inner method |
| No existing transaction to join | There is no "existing transaction" to compare against outer; the new transaction follows its own definition |
| `REQUIRES_NEW` encounters an outer transaction | Suspends outer transaction and opens a separate transaction; not a case of participating in the same physical transaction |

Some documentation refers to `validateExistingTransactions` descriptively in the plural; the **actual Java setter name** to use is `setValidateExistingTransaction(boolean)` (singular).

There is no standard Spring Boot property named `spring.transaction.validate-existing-transaction` that automatically enables this flag for all managers. The reliable way is to **obtain the actual manager bean being used** and call the setter when configuring it. In the example below, `demo.validate-existing` is a **custom property defined by the project**, explicitly read by the application and passed to the setter; it is not a built-in Spring Boot configuration property.

### Conditions for validation to take effect

1. The call to the inner method must pass through the **Spring transaction interceptor** (typically a Spring AOP proxy).
2. The inner method has a transaction definition and propagation that **joins an existing transaction**.
3. Outer and inner are coordinated by the **same transaction manager / related resource**. A manager only controls the transactions it manages.
4. The transaction manager has `validateExistingTransaction=true` configured.
5. A conflict of a type the manager actually checks exists.

Merely changing a field on a manager bean **will not** catch calls that bypass the proxy or transactions opened via standalone connections outside Spring.

## 4. Two mismatch groups that validation primarily detects

### 4.1. Isolation: inner specifies a non-default level that differs from outer

Suppose:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    innerService.requiresSerializable();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void requiresSerializable() {
    // ...
}
```

When `validateExistingTransaction=false`, inner **does not change** the active physical transaction from `READ_COMMITTED` to `SERIALIZABLE`. It continues joining outer's transaction with the already established properties.

When `true` is enabled, Spring compares the isolation declared by inner against the current isolation recorded by **Spring transaction synchronization**. If inner specifies a level **other than `DEFAULT`** that is incompatible with the current level, Spring throws `IllegalTransactionStateException`.

Specifically:

- Inner `isolation=DEFAULT`: validation **does not** require a specific level to compare; it does not fail merely because outer uses `READ_COMMITTED` or `SERIALIZABLE`.
- Inner declares `SERIALIZABLE`, outer declares `READ_COMMITTED`: strict mode rejects participation.
- Inner declares `READ_COMMITTED`, outer declares `READ_COMMITTED`: compatible; participation is allowed.
- Inner declares `READ_COMMITTED`, outer uses `DEFAULT`: current isolation may be recorded by Spring as **unspecified** (`null`), even when the database runs at `READ_COMMITTED` by default. In strict mode, inner requesting an explicit level while current isolation is not explicitly recorded can be rejected. **Do not assume a "coincidentally matching" database default is enough to pass.**

This check compares the **transaction definition and the state tracked by Spring**, not a query tool proving every actual database isolation property for each SQL statement. Even when configuration matches, confirming production isolation/locking behavior still requires testing on the real database engine.

### 4.2. Read-only: the key conflict is read-only outer, read-write inner

Example:

```java
@Transactional(readOnly = true)
public void generateReport() {
    innerService.persistAudit();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false
)
public void persistAudit() {
    // Wants to write data.
}
```

With strict validation, an inner **not marked read-only** (i.e. `readOnly=false`, which is also `@Transactional`'s default) **cannot join an outer transaction marked read-only**. Spring throws `IllegalTransactionStateException` when acquiring the transaction for inner.

**This is not a symmetric Boolean comparison.** `AbstractPlatformTransactionManager`'s read-only check corresponds to the condition:

```java
if (!innerDefinition.isReadOnly()
        && TransactionSynchronizationManager.isCurrentTransactionReadOnly()) {
    throw new IllegalTransactionStateException(/* ... */);
}
```

Outcomes:

| Outer physical transaction | Inner request | `validateExistingTransaction=true` |
| --- | --- | --- |
| `readOnly=true` | `readOnly=false` | **Rejected** |
| `readOnly=true` | `readOnly=true` | Allowed to join |
| `readOnly=false` | `readOnly=true` | **Allowed to join**; physical transaction remains read-write |
| `readOnly=false` | `readOnly=false` | Allowed to join |

**Why is the reverse direction still allowed?** A scope that only wants to read can join an outer read-write transaction. Inner's read-only attribute does not turn the shared connection into read-only. Therefore, do not mistakenly say "strict mode rejects all outer/inner read-only differences".

`readOnly=true` by itself is a **hint/optimization policy**, not a substitute for database permissions. Depending on the transaction manager and database, write operations may still execute or be rejected; `setValidateExistingTransaction` does not scan SQL to guarantee the application writes no data.

### 4.3. Quick comparison of isolation and read-only

| Outer | Inner `REQUIRED` | Validation = `false` | Validation = `true` |
| --- | --- | --- | --- |
| `READ_COMMITTED` | `SERIALIZABLE` | Inner uses outer's transaction | Rejected: isolation mismatch |
| `READ_COMMITTED` | `READ_COMMITTED` | Allowed to join | Allowed to join |
| `READ_COMMITTED` | `DEFAULT` | Allowed to join | Allowed to join |
| `DEFAULT` (Spring records no explicit isolation) | `READ_COMMITTED` | Allowed to join | Can reject because existing isolation is unknown |
| `readOnly=true` | `readOnly=false` | Usually allowed to join, inner does not upgrade to read-write | Rejected: read-only mismatch |
| `readOnly=false` | `readOnly=true` | Allowed to join, outer stays read-write | Allowed to join, outer stays read-write |

The last column assumes the transaction manager has strict mode enabled, a Spring-managed transaction is active, and the inner call actually passes through the interceptor. When both attributes conflict, the isolation check may fail before the read-only check; do not write tests assuming a read-only error message if isolation also mismatches.

## 5. What does this flag **not** do?

`setValidateExistingTransaction(true)` is not a comprehensive "strict mode" for everything named transaction.

| Does not do | Reason |
| --- | --- |
| Does not convert the physical transaction's isolation | A `REQUIRED` participant uses what the transaction owner created |
| Does not compare inner and outer timeouts the same way as isolation | Existing participation validation does not include a similar timeout comparison; timeout on inner `REQUIRED` usually does not reapply to an existing transaction |
| Does not prove the DB executes no UPDATEs in a read-only transaction | It compares definition/metadata, not SQL |
| Does not check whether `rollbackFor`, `noRollbackFor` are "compatible" | Rollback rules apply when an exception escapes through the interceptor, which is a separate mechanism |
| Does not turn `SUPPORTS` without a transaction into a transaction | If there is no physical transaction, there is nothing to "join" |
| Does not replace `Propagation.MANDATORY`/`NEVER` | Those propagations have their own rules regarding existing transactions |
| Does not replace the `UnexpectedRollbackException` mechanism | Rollback-only is an independent state; outer commit can still fail |
| Does not manage multiple independent databases as a distributed transaction | Each transaction manager has its own resource boundary |
| Does not fix self-invocation bugs | `this.innerMethod()` calls do not pass through the transaction proxy in normal proxy mode |

**Specifically about timeout:** If outer `@Transactional(timeout=30)` has opened a transaction and inner `@Transactional(timeout=5)` merely **joins** the same physical transaction, enabling validation **does not** mean Spring will reject the 30/5 mismatch. To enforce a real time limit for the entire operation, set timeout properly on the owner or design a different transaction boundary, then test with the actual transaction manager/database type.

## 6. Runnable example: toggling strict validation in Spring Boot

We build a small application using **Java 17, Spring Boot 3.3.13, Spring JDBC, and H2**. This section uses a fixed set of versions to make the example reproducible; it does not imply this is the latest Spring Boot release. No controller or Spring Data JPA is needed.

**Idea:** run twice with the exact same code:

- `demo.validate-existing=true`: isolation/read-only errors are rejected right when the inner scope tries to join.
- `demo.validate-existing=false`: the inner scope is allowed to join despite declaring different settings from outer; executed statements and observed state still follow outer.

### 6.1. Project structure

```text
tx-validation-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/scope/
    │   ├── TxValidationApplication.java
    │   ├── TransactionManagerConfig.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        └── application.yml
```

Use the Gradle Wrapper generated by Spring Initializr/Gradle; the Gradle version must be compatible with Spring Boot 3.3 and JDK 17.

**`settings.gradle`**

```groovy
rootProject.name = 'tx-validation-lab'
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

`spring-boot-starter-jdbc` provides `JdbcTemplate`, JDBC transaction infrastructure, and a connection pool (typically HikariCP). H2 is an in-memory database to verify commit/rollback. Spring/H2 versions are managed by Spring Boot; do not add individual versions per library.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:scopecheck;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""

demo:
  validate-existing: true
```

`demo.validate-existing` is a **property of the demo application**: the configuration class below explicitly reads and applies it. `DB_CLOSE_DELAY=-1` only keeps the in-memory H2 alive until the JVM stops; the database does not become durable storage across process restarts.

### 6.2. Configuring the transaction manager at the right place

**`src/main/java/demo/scope/TransactionManagerConfig.java`**

```java
package demo.scope;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionManagerConfig {

    @Bean
    JdbcTransactionManager transactionManager(
            DataSource dataSource,
            @Value("${demo.validate-existing:true}") boolean validate) {

        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        manager.setValidateExistingTransaction(validate);

        return manager;
    }
}
```

Points to observe:

1. The `transactionManager(...)` method creates a bean with the default name `transactionManager`, so `@Transactional` uses this manager in a project with a single transaction manager.
2. `JdbcTransactionManager` inherits the validation mechanism from `AbstractPlatformTransactionManager`. We call the setter **on the exact manager that will be used by the Spring interceptor**.
3. Spring Boot provides the `DataSource` from `spring.datasource.*`. The custom manager bean causes Boot's default transaction manager configuration to back off, avoiding two managers for the same DataSource.
4. `@EnableTransactionManagement` enables proxy-based annotation processing; Boot normally already includes related auto-configuration, but declaring it explicitly keeps the example conceptually self-contained.
5. Changing `demo.validate-existing` in YAML/command line only takes effect when the app rebuilds beans; do not attempt to mutate manager properties arbitrarily while requests are running.

**Important note:** `@Transactional` sits on the service, whereas `setValidateExistingTransaction` sits on the **manager**; there is no syntax like `@Transactional(validateExistingTransaction=true)`.

### 6.3. Inner service: four kinds of transaction requests

**`src/main/java/demo/scope/InnerService.java`**

```java
package demo.scope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void needSerializable() {
        System.out.println(
            "inner requested SERIALIZABLE; currentIsolation=" + isolationLabel());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = false
    )
    public void needReadWrite() {
        System.out.println(
            "inner requested read-write; currentReadOnly="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = true
    )
    public void needReadOnly() {
        System.out.println(
            "inner requested read-only; currentReadOnly="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void needReadCommitted() {
        System.out.println(
            "inner requested READ_COMMITTED; currentIsolation=" + isolationLabel());
    }

    private static String isolationLabel() {
        Integer current =
            TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();

        if (current == null) {
            return "UNSPECIFIED";
        }
        if (current == TransactionDefinition.ISOLATION_READ_COMMITTED) {
            return "READ_COMMITTED";
        }
        if (current == TransactionDefinition.ISOLATION_SERIALIZABLE) {
            return "SERIALIZABLE";
        }
        return String.valueOf(current);
    }
}
```

`TransactionSynchronizationManager` reflects the transaction state managed by Spring in the imperative/thread-bound model. It shows us that **inner does not automatically change outer's isolation/read-only metadata**. Do not treat this API as absolute proof of every active database isolation detail when transactions originate outside Spring or involve special drivers/providers.

If validation rejects participation, the body of the corresponding inner method **does not execute**, so the log line inside that method will not appear either.

### 6.4. Outer service: three conflicts and one valid case

**`src/main/java/demo/scope/OuterService.java`**

```java
package demo.scope;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void isolationMismatch() {
        jdbc.update(
            "INSERT INTO event_log (id, label) VALUES (?, ?)",
            1, "isolation"
        );
        inner.needSerializable();
    }

    @Transactional(readOnly = true)
    public void readOnlyMismatch() {
        inner.needReadWrite();
    }

    @Transactional(readOnly = false)
    public void readWriteCallsReadOnly() {
        inner.needReadOnly();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void matchingIsolation() {
        jdbc.update(
            "INSERT INTO event_log (id, label) VALUES (?, ?)",
            2, "matching"
        );
        inner.needReadCommitted();
    }
}
```

`OuterService` and `InnerService` are **two different Spring-managed beans**, so calls `inner.need...()` go through inner's transaction proxy. That is an essential condition for Spring to detect conflicts.

Four cases:

- `isolationMismatch()`: outer is `READ_COMMITTED`, inner requests `SERIALIZABLE`. Outer's INSERT is already inside the transaction, but when strict validation detects the conflict and the exception escapes through outer's proxy, the INSERT is rolled back.
- `readOnlyMismatch()`: outer is `readOnly=true`, inner requests `readOnly=false`. No write SQL is needed to detect the conflict; Spring checks the **definition** before inner's body runs.
- `readWriteCallsReadOnly()`: outer is `readOnly=false`, inner requests `true`. This case is **allowed**; inner observes the physical transaction is still read-write.
- `matchingIsolation()`: both outer and inner request `READ_COMMITTED`, so participation is allowed and outer's INSERT commits after the method finishes.

### 6.5. Runner that creates the table and prints post-transaction results

**`src/main/java/demo/scope/TxValidationApplication.java`**

```java
package demo.scope;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;

@SpringBootApplication
public class TxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxValidationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            OuterService outer,
            JdbcTemplate jdbc,
            @Value("${demo.validate-existing:true}") boolean validate) {

        return args -> {
            jdbc.execute(
                "CREATE TABLE event_log "
                    + "(id INT PRIMARY KEY, label VARCHAR(30) NOT NULL)"
            );

            System.out.println("validateExisting=" + validate);

            try {
                outer.isolationMismatch();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "isolation rejected: " + ex.getClass().getSimpleName());
            }
            System.out.println("rows after isolation=" + count(jdbc));

            try {
                outer.readOnlyMismatch();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "read-only rejected: " + ex.getClass().getSimpleName());
            }

            outer.readWriteCallsReadOnly();
            outer.matchingIsolation();

            System.out.println("rows at end=" + count(jdbc));
        };
    }

    private static Integer count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM event_log", Integer.class);
    }
}
```

All `outer.*()` calls in the runner go to the Spring-injected bean, **not `new OuterService(...)`**. The runner has no enclosing transaction, so the row counts run **after** each proxied transaction has committed or rolled back. The table is created when the runner starts; no `schema.sql` or Flyway is needed for this small H2 example.

### 6.6. Strict run: `validateExistingTransaction=true`

In the project directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Lines printed by `System.out.println` in order (in addition to Gradle/Spring Boot logs):

```text
validateExisting=true
isolation rejected: IllegalTransactionStateException
rows after isolation=0
read-only rejected: IllegalTransactionStateException
inner requested read-only; currentReadOnly=false
inner requested READ_COMMITTED; currentIsolation=READ_COMMITTED
rows at end=1
```

Line-by-line explanation:

1. `isolationMismatch` creates a `READ_COMMITTED` physical transaction and executes INSERT ID 1, but when inner requests `SERIALIZABLE`, the transaction manager rejects it. The unchecked exception escapes through outer's proxy; outer's transaction rolls back, so count is 0.
2. `readOnlyMismatch` is rejected **before the body of `needReadWrite()` executes**. The outer call ends with an exception caught by the runner; there is no `inner requested read-write` line.
3. `readWriteCallsReadOnly` is allowed; `currentReadOnly=false` shows that outer's property still governs.
4. `matchingIsolation` allows inner to join, and INSERT ID 2 commits. Only one row exists in the table.

This result **does not** mean any validation exception automatically rolls back the database regardless of what the caller does: in the example, the exception escapes the outer transactional method and the default rollback-on-runtime-exception triggers rollback. If outer catches and swallows the exception, the rollback state must be analyzed separately based on the call path and transaction status.

### 6.7. Default/lenient run: `validateExistingTransaction=false`

Re-run in a new JVM (in-memory H2 starts with an empty database):

```bash
./gradlew bootRun --args='--demo.validate-existing=false'
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.validate-existing=false"
```

Program output:

```text
validateExisting=false
inner requested SERIALIZABLE; currentIsolation=READ_COMMITTED
rows after isolation=1
inner requested read-write; currentReadOnly=true
inner requested read-only; currentReadOnly=false
inner requested READ_COMMITTED; currentIsolation=READ_COMMITTED
rows at end=2
```

Meaning:

- Although inner wanted `SERIALIZABLE`, it **did not create a new transaction**; Spring is coordinating outer's `READ_COMMITTED` transaction. INSERT ID 1 commits, count is 1.
- Inner requested read-write yet joined a read-only outer; `currentReadOnly=true`. The demo does not run an UPDATE inside this scope because that can depend on database/provider; the goal is to observe the configuration being "ignored".
- Read-only inner joining read-write outer still observes `currentReadOnly=false`.
- The matched isolation case inserts ID 2 as well; final count is 2.

Comparing the two runs shows why strict validation is valuable: it turns a configuration discrepancy that could silently linger into an error caught early.

## 7. Nature of the check in `AbstractPlatformTransactionManager`

To avoid misunderstanding the scope, the core of the **existing transaction / normal participation** path can be interpreted as follows:

```java
// Illustrative pseudocode, NOT runnable source code.
if (validateExistingTransaction) {

    if (innerDefinition.isolation != DEFAULT) {
        if (currentIsolation == null
                || currentIsolation != innerDefinition.isolation) {
            throw new IllegalTransactionStateException("Isolation mismatch");
        }
    }

    if (!innerDefinition.readOnly && currentTransactionReadOnly) {
        throw new IllegalTransactionStateException("Read-only mismatch");
    }
}

// If valid, inner scope joins the existing physical transaction.
```

Lessons drawn from this check:

- Isolation comparison is only performed when **inner does not use `DEFAULT`**.
- When Spring's recorded current isolation is **unknown**, an explicit isolation request from inner is not treated as implicitly compatible.
- Read-only comparison is **one-way**: it only rejects a **read-write** inner trying to join a **read-only** outer.
- There is no timeout comparison in this validation block.
- The check happens **before inner's method body**, without waiting for the DB to hit a write SQL statement to fail.

Do not apply this code sketch mechanically to every `TransactionManager` implementation. It reflects `AbstractPlatformTransactionManager`'s flow for existing participation; reactive managers or specialized implementations may use different mechanisms.

## 8. Propagation decides whether participation validation applies

| Inner propagation | When outer already has a transaction | Relation to strict validation |
| --- | --- | --- |
| `REQUIRED` | Joins outer's transaction | **Primary target** of mismatch validation |
| `SUPPORTS` | Joins outer's transaction if present | Can be validated when joining |
| `MANDATORY` | Requires outer transaction and joins | Can be validated if transaction exists |
| `REQUIRES_NEW` | Suspends outer, opens a new physical transaction | Not joining the same physical transaction; inner gets its own settings if supported by DB |
| `NOT_SUPPORTED` | Suspends outer, runs without an actual transaction | Does not join, not this isolation/read-only conflict case |
| `NEVER` | Fails per NEVER rule if outer transaction exists | Propagation error independent of validation flag |
| `NESTED` | Usually uses a savepoint in the same physical JDBC transaction if supported | Separate branch; **do not** infer this flag enforces an independent isolation for nested savepoints |

When **no outer transaction exists**:

- `REQUIRED` can open a new transaction with inner's own isolation/read-only.
- `SUPPORTS` can run without an actual transaction.
- `MANDATORY` throws an error because the required transaction is missing.
- `REQUIRES_NEW` opens a new transaction.

Do not use `REQUIRES_NEW` merely to "make the validation error go away". It alters atomicity: inner can commit separately while outer rolls back, and it may need a second connection from the pool while outer still holds its resource. If business logic requires all operations to commit/roll back together, the right approach is usually to **align isolation at the outer boundary**.

## 9. Equivalent XML configuration

If the project uses XML configuration instead of Java `@Bean`, strict validation can be enabled on the **transaction manager bean**:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="dataSource"/>
    <property name="validateExistingTransaction" value="true"/>
</bean>

<tx:annotation-driven transaction-manager="transactionManager"/>
```

This is an **illustrative XML snippet**, needing `<beans>` and corresponding `xmlns:tx`/schema declarations; `dataSource` must exist. `validateExistingTransaction` is a setter property on the manager, **not** an attribute of `<tx:method>`.

If the application uses `DataSourceTransactionManager` for JDBC, or `JpaTransactionManager` for JPA, you can apply the corresponding setter if that manager extends `AbstractPlatformTransactionManager` and actually manages the service's transactions. With JPA, select the right `EntityManagerFactory`/transaction manager; do not replace the active JPA manager with a JDBC manager just to get the setter.

**Scope impact:** this is a policy of one **manager bean**. If multiple transaction managers exist, enabling the flag on manager A does not automatically enable it on B; `@Transactional(transactionManager="...")` or qualifier/bean routing decides which manager a method uses. A multi-resource project must review configuration per manager, rather than assuming a single arbitrarily named bean.

## 10. Configuration scenarios that easily cause confusion

### 10.1. Outer `DEFAULT` while the database actually defaults to `READ_COMMITTED`

Inner declaring `READ_COMMITTED` can be rejected by strict validation because outer **did not explicitly declare** isolation, so Spring tracks `currentIsolation=null`. Even if the database's `SHOW transaction_isolation` returns `read committed`, do not treat that output as proof that validation will pass. If you want all scopes to declare a specific level, explicitly design/declare the level on the outer owner, re-test, and monitor the transaction manager.

### 10.2. Forgetting that `@Transactional` defaults to `readOnly=false`

An inner method annotated only with `@Transactional`, or `@Transactional(propagation=REQUIRED)`, defaults to **readOnly=false**. When called from a `readOnly=true` outer, strict mode can reject it **even if inner's body only runs SELECT**, because validation checks metadata rather than analyzing SQL logic. If the method is truly a query, declare `readOnly=true` semantically; if the method writes, redesign the transaction boundary.

### 10.3. Inner `readOnly=true` cannot narrow an outer read-write transaction

When outer has a read-write transaction, a read-only inner still joins; strict mode does not reject this direction. If you need a guarantee that no write SQL executes, use database permissions, tests, reviews, and a separate boundary rather than trusting inner's `readOnly` to constrain an existing physical transaction.

### 10.4. Different timeout configurations, yet strict mode reports no error

An inner `timeout=5` joining an outer `timeout=30` transaction does not make this flag report a "timeout mismatch". Set the timeout on the transaction owner or use an independent transaction when business logic genuinely requires it, while evaluating resources and atomicity.

### 10.5. Not passing through the proxy due to self-invocation

```java
@Service
public class SameBeanService {
    @Transactional(readOnly = true)
    public void outer() {
        inner(); // Internal call within the same bean.
    }

    @Transactional(readOnly = false)
    public void inner() {
        // ...
    }
}
```

In **standard Spring proxy mode**, `outer()` called through a proxy can open a transaction, but `inner()` called via `this` does not pass through the interceptor again. Therefore, the validation flag **does not check inner's declaration** on that call path. To verify properly, call the service through another Spring-managed bean, like `OuterService -> InnerService` in the full example.

### 10.6. Multiple transaction managers or different resources

If service A uses `transactionManagerA` and service B uses `transactionManagerB`, they do not necessarily share a physical transaction. An expected mismatch may not be checked because B is not joining A's transaction. Do not use this flag as a test for distributed transactions or resource routing. If atomicity across multiple resources is needed, evaluate a dedicated transaction strategy.

### 10.7. Swallowing `IllegalTransactionStateException` and assuming everything rolled back

The validation flag throws the exception when **acquiring the transaction for inner**. If the exception escapes the outer `@Transactional` method, Spring rolls back by default for unchecked exceptions. However, if outer catches and swallows the error, the outer transaction **can** continue/commit depending on state and code; do not conclude that validation rejecting participation automatically marks outer rollback-only.

The safe approach is usually to let configuration errors **fail fast**, fix the policy, and not catch-and-ignore in business code.

### 10.8. Confusing `IllegalTransactionStateException` with `UnexpectedRollbackException`

- `IllegalTransactionStateException` in this article: Spring sees that the joining scope's transaction definition is **incompatible** and rejects participation.
- `UnexpectedRollbackException`: a physical transaction was already marked rollback-only (for example, an earlier inner scope failed); outer expected to commit but actually could not commit.

Both errors can appear in multi-scope systems, but **have different causes and timings**. The validation flag does not replace rollback-only detection.

### 10.9. Confusing with `setEnforceReadOnly(true)`

`DataSourceTransactionManager` also has `setEnforceReadOnly(true)` for certain databases to actively apply read-only mode via the corresponding SQL statement for new transactions. **That is a different mechanism** from `setValidateExistingTransaction(true)`:

- `setValidateExistingTransaction`: compares definitions when **joining** an existing transaction; does not parse or block arbitrary write statements.
- `setEnforceReadOnly`: aims to enforce read-only at the database layer when opening a transaction, depending on backend/driver support.

Do not substitute one setter for the other, and do not assume all DBs/drivers enforce read-only identically.

## 11. How to design a consistent transaction policy

Before enabling strict validation on a live system:

1. **Map transaction owners**: which controller/service facade actually opens physical transactions? Are there nested `REQUIRED` calls?
2. **Audit inner attributes**: is isolation declared explicitly or left as DEFAULT? Is read-only accidentally left at its false default on query-only methods?
3. **Choose an intentional transaction-level policy**: if business logic requires higher isolation, set it at the outer owner and verify DB support instead of hoping inner upgrades it.
4. **Keep inner scope semantics clear**: write methods should not be called deep inside a read-only outer; read-only methods should declare it accurately if strict mode needs to distinguish them.
5. **Evaluate `REQUIRES_NEW` carefully**: use it only when an independent transaction is genuinely needed, as it alters commit boundaries and connection demand.
6. **Enable validation in test/staging first**: new errors may surface on call paths previously silently ignored. Record the service/manager/method pair and fix the policy rather than immediately turning off the flag.
7. **Test on a production-like DB**: isolation support and read-only behavior depend on the database; H2 only illustrates Spring logic.
8. **Observe rollback after exceptions**: inspect the DB after the service proxy completes. If tests themselves are wrapped in `@Transactional`, the test transaction can skew conclusions.
9. **Audit multiple managers**: each manager needs intentional configuration; verify the actual bean and `@Transactional(transactionManager=...)` when multiple transaction types exist.
10. **Keep regression tests and alerts** when refactoring services, because changing boundaries/propagations can cause a previously checked mismatch to stop being checked.

Tests should cover at least the following cases (within the same manager, calls via proxy):

| Case | Expected in strict mode |
| --- | --- |
| Outer `READ_COMMITTED` → inner `SERIALIZABLE REQUIRED` | Throws `IllegalTransactionStateException`, inner body does not run |
| Outer `READ_COMMITTED` → inner `READ_COMMITTED REQUIRED` | Runs normally |
| Outer `READ_COMMITTED` → inner `DEFAULT REQUIRED` | Runs normally |
| Outer `readOnly=true` → inner `readOnly=false REQUIRED` | Throws `IllegalTransactionStateException` |
| Outer `readOnly=false` → inner `readOnly=true REQUIRED` | Runs normally; physical transaction remains read-write |
| No outer → inner `REQUIRED` | Creates new transaction; nothing to compare against outer |
| Outer transaction → inner `REQUIRES_NEW` | Independent new transaction, does not "join" physical outer |
| Outer `timeout=30` → inner `timeout=5 REQUIRED` | Validation flag **does not** automatically detect a timeout mismatch |

The goal of tests is to confirm runtime behavior **using real Spring bean proxies**, not just checking whether annotations exist in source code.

## 12. Self-check questions

**1. Why did an inner method declare `SERIALIZABLE` yet at runtime run only at `READ_COMMITTED`?**

Because `REQUIRED` joins the transaction already opened by outer. With the default validation `false`, Spring ignores the participant's different isolation request and outer's transaction continues to govern.

**2. If I want Spring to reject mismatched requests, should I write `@Transactional(validateExistingTransaction=true)`?**

No. This property lives on the **transaction manager** via the `setValidateExistingTransaction(true)` setter.

**3. Does strict mode reject a read-write outer + read-only inner?**

No, according to `AbstractPlatformTransactionManager`'s check. It rejects a **read-write inner joining a read-only outer**, not the reverse direction.

**4. Why can outer `Isolation.DEFAULT` and inner `READ_COMMITTED` still be rejected even though the DB default is READ_COMMITTED?**

Because Spring may record current isolation as `null` when outer does not specify an explicit isolation. Validation relies on transaction metadata tracked by Spring, without assuming the DB default matches inner's request.

**5. Does this flag detect an inner timeout of 5 seconds when outer timeout is 30 seconds?**

No. This is not a validator for every transaction attribute; a participant's timeout is not matched the way isolation is.

**6. Can `REQUIRES_NEW` establish an independent isolation level?**

With a supporting transaction manager/DB, `REQUIRES_NEW` opens a new physical transaction so inner's definition applies; in exchange, it is independent in commit/rollback and resources, so use it only when business requirements justify it.

**7. Why do I still see no exception after enabling the flag on a transaction manager bean?**

Verify whether that bean is actually used by the transaction interceptor; whether outer has an existing transaction; whether inner goes through the Spring proxy; whether propagation joins; and whether the mismatch type falls within validation scope.

**8. Does a validation mismatch automatically roll back outer even if outer catches and ignores the exception?**

Do not assume so. In the complete example, the unchecked exception **escaped outside outer**, so outer's interceptor rolled back. If outer swallows the exception, inspect transaction status and error-handling design rather than relying on the flag as a general rollback-only marker.

## 13. Summary

`setValidateExistingTransaction(true)` helps detect **incompatible transaction declarations early when a scope joins an existing transaction**. It is especially useful when:

- Outer and inner explicitly declare different isolations.
- Outer is `readOnly=true` while inner defaults to or explicitly declares `readOnly=false`.
- A system has many `REQUIRED` services, making it easy to mistakenly assume inner creates a transaction with new attributes.

Exact rule to remember:

**Strict validation compares inner's explicit isolation against the isolation Spring recorded on outer; rejects a read-write inner entering a read-only outer; does not check timeouts as a similar mismatch; and does not replace transaction boundaries, proxies, rollback rules, or database permissions.**

The architectural fix is typically to place the desired attributes on the **transaction owner**, ensure participating scopes have compatible declarations, and use independent transactions only when genuinely needed. Verification with Spring proxy calls and the database is an indispensable step.

## Official reference documentation

- Spring Framework — *Transaction Propagation* (REQUIRED, REQUIRES_NEW, validation): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *Understanding Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.1 API — *AbstractPlatformTransactionManager* and `setValidateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework API — *JdbcTransactionManager*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework source — *AbstractPlatformTransactionManager* (`handleExistingTransaction` branch): https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java
- Spring Boot 3.3 — *SQL Databases and JDBC*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
