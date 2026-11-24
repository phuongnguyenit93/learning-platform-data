# Creating DefaultTransactionDefinition and Naming Transactions in Spring Framework

## 1. Lesson Objectives and Real-World Context

Spring Framework has two API groups for managing transactions:

- **Declarative:** declare `@Transactional` or XML configuration; the Spring transaction interceptor opens, commits, or rolls back according to metadata.
- **Programmatic:** write code directly using `PlatformTransactionManager`, `TransactionDefinition`, `TransactionStatus`, or use `TransactionTemplate` to decide transaction boundaries.

This lesson focuses on the **direct transaction API**, especially **creating `DefaultTransactionDefinition` and naming a transaction with `setName(String)`**. The name is used by Spring as identifying information for a transaction when it can be exposed via transaction synchronization/monitoring; **it is not a table name, a database-issued transaction ID, or a transaction manager bean name**.

Basic example:

```java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setName("orders.create");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);

TransactionStatus status = transactionManager.getTransaction(definition);
try {
    performDatabaseWork();
} catch (RuntimeException | Error ex) {
    transactionManager.rollback(status);
    throw ex;
}
transactionManager.commit(status);
```

This is an **illustrative pattern**: `transactionManager` and `performDatabaseWork()` must be provided. In the hands-on section there will be a complete Java 17+ project with H2.

After this lesson, you will be able to:

1. Distinguish `TransactionDefinition`, `DefaultTransactionDefinition`, `PlatformTransactionManager`, and `TransactionStatus`.
2. Create a definition and configure `propagation`, `isolation`, `timeout`, `readOnly`, and especially **`name`**.
3. Call `getTransaction(definition)`, decide `commit(status)` or `rollback(status)` yourself, and avoid mistakenly rolling back an already completed status.
4. Read the current name with `TransactionSynchronizationManager.getCurrentTransactionName()` in the imperative model.
5. Explain why an inner `REQUIRED` joining an outer transaction **usually keeps the outer name**, while `REQUIRES_NEW` has its own name and then restores the outer name upon completion.
6. Run a Spring Boot/JDBC/H2 project to verify actual data after commit and rollback, while observing the name in each scope.
7. Design a naming convention that makes logs/tracing useful without leaking sensitive information or creating excessive metric cardinality.

The parent topic is the **direct transaction API** of the **Spring Framework — transaction-management** module. This document covers **imperative transactions** on JDBC; reactive transactions use `ReactiveTransactionManager`/`TransactionalOperator` and a different context propagation model.

## 2. Four Objects That Make Up a Programmatic Transaction

### 2.1. TransactionDefinition Is the Intent-Describing Contract

`org.springframework.transaction.TransactionDefinition` is the interface that provides the configuration a transaction manager receives:

- `getPropagationBehavior()`: for example `PROPAGATION_REQUIRED` or `PROPAGATION_REQUIRES_NEW`.
- `getIsolationLevel()`: desired isolation if the manager opens a new physical transaction.
- `getTimeout()`: timeout in seconds, or the manager's default.
- `isReadOnly()`: read-only hint for the manager/resource.
- `getName()`: logical name of the transaction, which may be `null`.

`TransactionDefinition` does **not** open a connection by itself, does not contain SQL data, and does not call commit. It only describes **how the transaction manager should behave**.

### 2.2. DefaultTransactionDefinition Is a Mutable Configuration Class

`org.springframework.transaction.support.DefaultTransactionDefinition` is the standard implementation, providing setters:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();

def.setName("billing.settle");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15); // seconds
def.setReadOnly(false);
```

This is a valid snippet inside a method with the corresponding imports. It only **creates metadata**, and has not started a transaction yet. When the manager calls `getTransaction(def)`, the properties are read to decide whether to open a new transaction, join an existing transaction, or reject according to propagation.

**Do not modify a shared definition after threads have begun using it.** For simplicity and clarity, create a new definition or configure a fixed object per transaction type. `DefaultTransactionDefinition` has mutable setters, not storage for commit/rollback state.

### 2.3. PlatformTransactionManager Coordinates the Transaction

Three main APIs of `org.springframework.transaction.PlatformTransactionManager`:

```java
TransactionStatus status = manager.getTransaction(definition);
manager.commit(status);
manager.rollback(status);
```

`getTransaction` may create a new physical transaction or have the status join an existing transaction. The two transaction-completion methods **must not be called consecutively on the same status**, for example you must not commit and then roll back that same status.

In JDBC, a commonly used implementation is `DataSourceTransactionManager` or `JdbcTransactionManager`. They must manage the **same DataSource** that `JdbcTemplate`/repositories use; if code writes using a resource outside the transaction manager, rollback will not automatically cover it.

### 2.4. TransactionStatus Describes the Executing Scope

`org.springframework.transaction.TransactionStatus` represents the status returned for each `getTransaction` call. Key methods to know:

| Method | Meaning |
| --- | --- |
| `isNewTransaction()` | Did this scope open a new transaction? |
| `isRollbackOnly()` | Has the status already requested rollback-only? |
| `setRollbackOnly()` | Actively mark so it cannot commit |
| `isCompleted()` | Has the status already completed? |
| `hasSavepoint()` | Does the status have a savepoint managed in a nested transaction? |
| `flush()` | Request a flush according to the status contract if a supporting mechanism exists |

**There is no `status.getName()` in the standard `TransactionStatus` contract.** The name is provided via `TransactionDefinition.getName()` and can be observed with `TransactionSynchronizationManager.getCurrentTransactionName()` in an appropriate imperative context.

## 3. Default Values When Calling new DefaultTransactionDefinition()

When no setters are called, `new DefaultTransactionDefinition()` has these basic characteristics:

| Property | Default value | Explanation |
| --- | --- | --- |
| Propagation | `PROPAGATION_REQUIRED` | Join an existing transaction; create a new one if none exists |
| Isolation | `ISOLATION_DEFAULT` | Follow the DB/manager default level |
| Timeout | `TIMEOUT_DEFAULT` (usually represented by -1) | Manager decides the default timeout |
| Read-only | `false` | Do not request read-only optimization |
| Name | `null` | No explicit name attached to the programmatic transaction |

Several setters accept **integer constants** declared in `TransactionDefinition`; do not pass "magic" numbers (for example `3`) without clear meaning. Choose the constants:

```java
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(20);
def.setReadOnly(true);
def.setName("reports.daily");
```

Note that `setReadOnly(true)` is only a **hint** or constraint depending on the manager/driver/database. It does not grant security permissions by itself or guarantee blocking every INSERT statement. Isolation and timeout are normally applied when **starting a new physical transaction**; if merely joining an existing transaction, the outer transaction has already shaped those physical properties.

### 3.1. Commonly Used Propagation Behaviors

| Propagation | When transaction T already exists | When no T exists |
| --- | --- | --- |
| `REQUIRED` | Join T, do not create a separate physical transaction | Create a new T |
| `REQUIRES_NEW` | Suspend T, create a separate T2 | Create a new T |
| `SUPPORTS` | Join T | Do not create a physical transaction; may have a synchronization scope |
| `MANDATORY` | Join T | Throw an error because a transaction is missing |
| `NOT_SUPPORTED` | Suspend T to run without a transaction | Run without a transaction |
| `NESTED` | May create a savepoint within T if supported by the manager | Usually opens a new T depending on configuration/support |

The demo will use `REQUIRED` and `REQUIRES_NEW` because the **current name** clearly illustrates the difference between a **participating logical scope** and an **independent physical transaction**.

### 3.2. setIsolationLevelName and setPropagationBehaviorName

In addition to overloads accepting integer constants, `DefaultTransactionDefinition` has setters accepting constant name strings in appropriate Spring versions:

```java
def.setPropagationBehaviorName("PROPAGATION_REQUIRED");
def.setIsolationLevelName("ISOLATION_READ_COMMITTED");
```

Use explicit constant names instead of raw numbers. Do not arbitrarily pass the string `"REQUIRED"` when the API expects the constant name `"PROPAGATION_REQUIRED"`. For new Java code, using standard integer constants is easier for the compiler to check.

## 4. setName(String): What Are You Naming?

`setName` records a **logical label** on `DefaultTransactionDefinition`:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("orders.create");
System.out.println(def.getName()); // orders.create
```

At this point, **there is no actual transaction yet**. Everything is still just in metadata.

When calling `transactionManager.getTransaction(def)` to open a new physical transaction through a manager that supports synchronization, Spring can publish the name in the thread-bound context. In an imperative transaction, read it with:

```java
String currentName =
    TransactionSynchronizationManager.getCurrentTransactionName();
```

The result may be the name provided by `setName` while the scope is active, or `null` when no name has been published. This method **does not create a transaction** and is not an API that returns a DB transaction ID.

### 4.1. Name Is Not a Unique Physical Transaction Identifier

Two calls to `getTransaction` with the same `setName("orders.create")` can create **two different physical transactions**, yet they carry the same name. This is completely valid.

The name is used to group/identify the operation type in monitoring; if you want correlation across a request, services, and specific SQL, also use a trace ID, span ID, or business operation ID in a protected observability system. **Do not misuse the transaction name as a trace ID**.

### 4.2. Name Does Not Change the Commit/Rollback Policy

Changing `def.setName("orders.create")` to `def.setName("orders.cancel")` does **not** change isolation, rollback rules, or database state. Two different names can have the exact same propagation and SQL behavior.

Do not use the name as an authorization mechanism, transaction manager selector, or business lock. Those require their corresponding configuration/resources/APIs.

### 4.3. Why Not Set the Name Directly with @Transactional?

According to the Spring documentation, setting an **optional explicit name** is a capability of **programmatic transaction management**. With standard declarative `@Transactional`, the default published name is usually **the fully qualified class name + "." + the method name**.

In particular, writing:

```java
@Transactional("mainTransactionManager")
public void saveOrder() {
    // ...
}
```

selects the **transaction manager qualifier** (equivalent to the annotation's `value`/`transactionManager` attribute), and **does not set the transaction name** to `"mainTransactionManager"`. This illustrative snippet has no class; it only explains the meaning of the annotation.

Do not confuse `@Transactional`'s `value` with `DefaultTransactionDefinition.setName`. The two APIs serve different purposes.

## 5. Standard Begin/Commit/Rollback Lifecycle

### 5.1. Diagram

```text
Create DefaultTransactionDefinition + setName("orders.create")
                              |
                              v
         PlatformTransactionManager.getTransaction(def)
                              |
                     TransactionStatus s
                              |
             +----------------+----------------+
             |                                 |
       Work succeeds                     Work fails
             |                                 |
             v                                 v
        commit(s)                         rollback(s)
             |                                 |
             +---------------+-----------------+
                             |
                     status completed
                             |
                   Do not reuse status
```

A transaction status returned by the manager is **a single participation in a specific scope**; do not store it in a singleton and reuse it for subsequent requests.

### 5.2. Java Pattern Handling RuntimeException and Error

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("inventory.reserve");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

TransactionStatus status = manager.getTransaction(def);
try {
    performBusinessWrites();
} catch (RuntimeException | Error ex) {
    manager.rollback(status);
    throw ex;
}
manager.commit(status);
```

This snippet is an **illustrative pattern**; it requires an injected manager and an implementation of `performBusinessWrites`.

Two important details:

1. `commit(status)` sits **outside the try-catch around the business work**. Once commit has started and throws an error, attempting a second `rollback(status)` can be wrong because the transaction has already been cleaned up/completed; the commit outcome when an ACK is lost may also be indeterminate.
2. Catching `RuntimeException | Error` is **a policy chosen by your code**, not Spring automatically applying declarative rules to every low-level call. If the business method throws a checked exception, you must design a rollback path for it when needed.

In the hands-on example, we deliberately roll back a failure case to prove the DB state.

### 5.3. Checked Exceptions with the Direct API

Unlike transaction advice that has a default rollback rule, when using `PlatformTransactionManager` **directly**, the caller **must decide** when to call rollback/commit. For example, a file import operation throws a checked `IOException`, yet all DB operations must be atomic:

```java
TransactionStatus s = manager.getTransaction(def);
try {
    importFileAndPersist(); // May throw IOException.
} catch (IOException | RuntimeException | Error ex) {
    manager.rollback(s);
    throw ex;
}
manager.commit(s);
```

This illustrative code requires an `importFileAndPersist` method, a definition, and a manager. It expresses a policy of "aborting the entire transaction for IOException and unchecked errors". If the business logic allows committing despite a checked exception, the code must decide explicitly; do not assume the low-level API will automatically roll back when a Java method exits via a checked exception.

### 5.4. setRollbackOnly() Differs from rollback(status)

`status.setRollbackOnly()` marks an **intent not to commit**, whereas `manager.rollback(status)` ends (or acts on) the transaction scope through the manager. For a **participating `REQUIRED` scope** in a shared transaction, rollback usually marks the shared physical transaction rollback-only; it does not perform an independent physical commit/rollback for the inner scope.

If the outer scope attempts to commit a physical transaction that an inner scope has already marked rollback-only, it may receive `UnexpectedRollbackException`. This is important behavior when using the direct API and nested declarative services.

### 5.5. Do Not Commit and Then Rollback the Same Status

Incorrect example:

```java
TransactionStatus status = manager.getTransaction(def);
manager.commit(status);
manager.rollback(status); // Wrong: status is already completed.
```

The result may be `IllegalTransactionStateException`. If you need another transaction, create an appropriate definition and call `getTransaction` again to obtain a **new status**. In a flow that experiences an exception during commit, do not use a "rollback just to be safe" fallback if the manager has already cleaned up; handle uncertain outcomes with idempotency and data state lookups.

## 6. Runnable Hands-On Project: Transaction Names and Nested Scopes

The project uses **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, **H2 in-memory**, and **Gradle 8.x**. We use `PlatformTransactionManager` directly; no `@Transactional` is needed on the demo class.

Five key observations:

- **A — Commit:** set name `orders.create`, open T, INSERT, then commit; the DB retains the record.
- **B — Rollback:** set name `orders.fail`, INSERT, then actively roll back on a runtime error; the DB no longer has the record.
- **C — Inner REQUIRED:** outer has name `orders.batch`, inner proposes `inventory.join` but actually joins T. `getCurrentTransactionName()` still shows the outer name; committing inner does not physically commit, and outer rolls back both records.
- **D — Inner REQUIRES_NEW:** outer `checkout.outer`, inner `audit.persist` opens a separate T2. Inside inner the name is `audit.persist`; after inner commits, the outer name is restored; outer rolls back yet the audit record still exists.
- **E — Completed scope:** outside transactions, the current name returns to `null`.

The verification **does not require running two threads**: nesting transactions via `getTransaction` and `REQUIRES_NEW` on the same thread is enough to demonstrate suspend/resume; each physical transaction uses an appropriate connection from the pool.

### 6.1. Directory Structure

```text
named-tx-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/edu/transactionnames/
    │   ├── TransactionNamesApplication.java
    │   └── TransactionNamesDemo.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'named-tx-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'edu'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` brings in `JdbcTemplate` and transaction support. We register an explicit `DataSourceTransactionManager` so every `getTransaction` call manages the same JDBC `DataSource`. Since we do not use declarative `@Transactional` in the demo, the AOP starter is not required to understand the programmatic mechanism.

**`src/main/resources/application.properties`**

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:named_tx;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

Pool size 5 is only to ensure the `REQUIRES_NEW` demo can borrow a second connection while the outer transaction holds one. Production must size pools according to concurrency and nesting depth; do not take the number 5 as a general optimal configuration.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

Each case uses a different id; H2 in-memory starts empty on every new JVM startup. If connecting to a persistent DB, you must reset test data to avoid primary key collisions.

### 6.2. Spring Boot Application: One Manager per DataSource

**`src/main/java/edu/transactionnames/TransactionNamesApplication.java`**

```java
package edu.transactionnames;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TransactionNamesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionNamesApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner run(TransactionNamesDemo demo) {
        return args -> demo.demonstrate();
    }
}
```

The application has no web server. `CommandLineRunner` calls the demo bean, which is **not** annotated with `@Transactional`. Therefore, at the start/end of the runner there is no transaction; each `getTransaction` call in `TransactionNamesDemo` creates or joins a transaction according to its definition.

### 6.3. TransactionNamesDemo: A Complete Java File

**`src/main/java/edu/transactionnames/TransactionNamesDemo.java`**

```java
package edu.transactionnames;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class TransactionNamesDemo {
    private final PlatformTransactionManager manager;
    private final JdbcTemplate jdbc;

    public TransactionNamesDemo(
            PlatformTransactionManager manager, JdbcTemplate jdbc) {
        this.manager = manager;
        this.jdbc = jdbc;
    }

    public void demonstrate() {
        System.out.println("before name=" + currentName());

        committed();
        rolledBack();
        requiredJoin();
        requiresNew();

        System.out.println("after name=" + currentName());
    }

    private void committed() {
        DefaultTransactionDefinition def =
            definition("orders.create",
                TransactionDefinition.PROPAGATION_REQUIRED);

        // Reference additional properties when creating a new transaction.
        def.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
        def.setTimeout(10);
        def.setReadOnly(false);

        TransactionStatus status = manager.getTransaction(def);
        try {
            System.out.println(
                "A name=" + currentName() +
                " new=" + status.isNewTransaction());
            insert(1, "committed");
        } catch (RuntimeException | Error ex) {
            manager.rollback(status);
            throw ex;
        }
        manager.commit(status);
        System.out.println("A count=" + count(1));
    }

    private void rolledBack() {
        TransactionStatus status = manager.getTransaction(
            definition("orders.fail",
                TransactionDefinition.PROPAGATION_REQUIRED));

        try {
            System.out.println(
                "B name=" + currentName() +
                " new=" + status.isNewTransaction());
            insert(2, "should-disappear");
            throw new IllegalStateException("intentional");
        } catch (RuntimeException | Error ex) {
            manager.rollback(status);
            if (!(ex instanceof IllegalStateException)
                    || !"intentional".equals(ex.getMessage())) {
                throw ex;
            }
            System.out.println("B rolledBack=" + ex.getMessage());
        }
        System.out.println("B count=" + count(2));
    }

    private void requiredJoin() {
        TransactionStatus outer = manager.getTransaction(
            definition("orders.batch",
                TransactionDefinition.PROPAGATION_REQUIRED));
        try {
            System.out.println(
                "C outer=" + currentName() +
                " new=" + outer.isNewTransaction());
            insert(3, "outer-required");

            TransactionStatus inner = manager.getTransaction(
                definition("inventory.join",
                    TransactionDefinition.PROPAGATION_REQUIRED));
            try {
                System.out.println(
                    "C inner=" + currentName() +
                    " new=" + inner.isNewTransaction());
                insert(4, "inner-required");
            } catch (RuntimeException | Error ex) {
                manager.rollback(inner);
                throw ex;
            }
            manager.commit(inner);

            System.out.println("C afterInner=" + currentName());
        } catch (RuntimeException | Error ex) {
            manager.rollback(outer);
            throw ex;
        }

        // Deliberately roll back outer to prove inner REQUIRED did not commit separately.
        manager.rollback(outer);
        System.out.println(
            "C counts=" + count(3) + "," + count(4));
    }

    private void requiresNew() {
        TransactionStatus outer = manager.getTransaction(
            definition("checkout.outer",
                TransactionDefinition.PROPAGATION_REQUIRED));
        try {
            System.out.println(
                "D outer=" + currentName() +
                " new=" + outer.isNewTransaction());
            insert(5, "outer-will-rollback");

            TransactionStatus inner = manager.getTransaction(
                definition("audit.persist",
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW));
            try {
                System.out.println(
                    "D inner=" + currentName() +
                    " new=" + inner.isNewTransaction());
                insert(6, "inner-commits");
            } catch (RuntimeException | Error ex) {
                manager.rollback(inner);
                throw ex;
            }
            manager.commit(inner);

            System.out.println("D resumed=" + currentName());
        } catch (RuntimeException | Error ex) {
            manager.rollback(outer);
            throw ex;
        }

        // Inner has committed independently. Outer now rolls back.
        manager.rollback(outer);
        System.out.println(
            "D counts=" + count(5) + "," + count(6));
    }

    private static DefaultTransactionDefinition definition(
            String name, int propagation) {
        DefaultTransactionDefinition def =
            new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(propagation);
        return def;
    }

    private void insert(int id, String eventName) {
        jdbc.update(
            "INSERT INTO tx_event(id, event_name) VALUES (?, ?)",
            id, eventName
        );
    }

    private int count(int id) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id = ?",
            Integer.class, id
        );
        return result;
    }

    private static String currentName() {
        return TransactionSynchronizationManager
            .getCurrentTransactionName();
    }
}
```

The imports/classes/methods here match Java 17 and Spring Framework 6.1 bundled with Spring Boot 3.3. The helpers `definition`, `insert`, `count`, and `currentName` all have implementations in the same file.

**Why doesn't the code use `@Transactional`?** The goal is to learn `DefaultTransactionDefinition` and `PlatformTransactionManager` directly. Annotations are not needed for the manager to create a transaction; the `getTransaction` call establishes the transaction boundary itself.

**Why are the statuses different?** Each `getTransaction(def)` call returns a `TransactionStatus` for a logical scope. Inner REQUIRED has its own status, yet `isNewTransaction() == false`; inner REQUIRES_NEW has its own status and `isNewTransaction() == true`, because the manager opens a new physical transaction.

### 6.4. Running the Application and Expected Console Output

In the `named-tx-demo` directory with JDK 17+ and a compatible Gradle 8.x:

```bash
gradle bootRun
```

If the project has an appropriately configured Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. On the first run Gradle needs to download dependencies; this Java code cannot be compiled with plain `javac` on the JDK classpath due to Spring/H2 dependencies.

Ignoring logs from Gradle/Spring/Hikari, **the expected `System.out.println` lines in order**:

```text
before name=null
A name=orders.create new=true
A count=1
B name=orders.fail new=true
B rolledBack=intentional
B count=0
C outer=orders.batch new=true
C inner=orders.batch new=false
C afterInner=orders.batch
C counts=0,0
D outer=checkout.outer new=true
D inner=audit.persist new=true
D resumed=checkout.outer
D counts=0,1
after name=null
```

This is **expected output from the code** under clean H2 demo conditions, not a log captured from a build execution. If it differs, check whether there is a transaction outside the runner, whether the manager bean has the right DataSource, whether stale data remains in H2, and whether any other code enables transaction synchronization.

### 6.5. Interpreting the Key Figures

| Case | Current name | Physical transaction | Data result |
| --- | --- | --- | --- |
| Before runner | `null` | None | Nothing written |
| A: create `orders.create` | `orders.create` | New T1 | id 1 committed, count 1 |
| B: create `orders.fail` | `orders.fail` | New T2 | id 2 rolled back, count 0 |
| C: outer `orders.batch` | `orders.batch` | New T3 | id 3 pending commit |
| C: inner `inventory.join` REQUIRED | Still `orders.batch` | **Joins T3** | id 4 not committed separately |
| C: outer rollback | No name in scope | T3 rolled back | id 3 and id 4 both 0 |
| D: outer `checkout.outer` | `checkout.outer` | New T4 | id 5 not committed |
| D: inner `audit.persist` REQUIRES_NEW | `audit.persist` | Independent T5 | id 6 committed separately |
| D: resume and outer rollback | `checkout.outer` then `null` | T4 rolled back | id 5 = 0; id 6 = 1 |

**Key observation:** inner `REQUIRED` configures `setName("inventory.join")`, yet the name published by Spring remains `orders.batch` because it **joins an existing physical transaction** and does not create a new synchronization context replacing the outer one. Inner `REQUIRES_NEW` actually opens a new physical transaction, so it has the name `audit.persist` inside inner and then restores the outer name upon resume.

Do not treat the name as the sole proof of atomicity. The readback result `C counts=0,0` versus `D counts=0,1` is what demonstrates the physical commit/rollback difference.

### 6.6. Why Didn't C Inner Commit Keep id 4?

In case C:

```text
getTransaction("orders.batch", REQUIRED)   -> new T3
  INSERT id=3
  getTransaction("inventory.join", REQUIRED) -> join T3
    INSERT id=4
  commit(innerStatus)                        -> ends logical scope
  [T3 is still not committed]
rollback(outerStatus)                        -> rolls back T3
SQL readback id=3 = 0, id=4 = 0
```

`manager.commit(innerStatus)` when inner only participates via `REQUIRED` **is not equivalent to `JDBC Connection.commit()` for all of T3**. The transaction manager knows this status is participating rather than owning the physical transaction.

### 6.7. Why Did D Inner Have Its Own Name and Then Return to the Outer Name?

In case D:

```text
getTransaction("checkout.outer", REQUIRED) -> new T4
  [Spring current name: checkout.outer]
  INSERT id=5

  getTransaction("audit.persist", REQUIRES_NEW)
    suspend T4 / outer synchronization
    begin T5
    [Spring current name: audit.persist]
    INSERT id=6
  commit(innerStatus) -> COMMIT T5
    resume T4 / outer synchronization
  [Spring current name: checkout.outer]

rollback(outerStatus) -> ROLLBACK T4
SQL readback id=5 = 0, id=6 = 1
```

This is a property of **REQUIRES_NEW**, not `setName` causing an independent transaction. If you keep propagation REQUIRED and only change the inner name to `audit.persist`, inner still joins T4.

**Production note:** inner REQUIRES_NEW usually has to request an additional JDBC connection while outer still holds its resource. Too small a pool or an inner operation touching rows locked by outer can cause waiting/deadlock-like timeouts. Use it only when the business logic genuinely allows inner to commit/roll back independently.

## 7. The Current Transaction Name Is Not Data from the Database

### 7.1. Thread-Bound Metadata in Imperative Spring

`TransactionSynchronizationManager.getCurrentTransactionName()` reads information published by the Spring transaction infrastructure on the **current thread**. It does not run `SELECT transaction_id`, does not query the DB session, and does not allocate a transaction ID.

You can have:

```text
Def A name="orders.create" -> JDBC transaction T1
Def B name="orders.create" -> JDBC transaction T2
```

Two separate transactions, same label. Conversely, when an inner `REQUIRED` joins T1, it can have a different definition name while the **current name does not change** because outer owns the current context.

### 7.2. Sync Active and Actual Transaction Active

The APIs:

```java
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

boolean actual =
    TransactionSynchronizationManager.isActualTransactionActive();
```

The two values are not always equal. `SUPPORTS` without a physical transaction can still have a synchronization scope depending on `AbstractPlatformTransactionManager` configuration; a non-null current name or active sync **is not sufficient proof that a JDBC transaction has started**. To verify commit/rollback, you need the right data source and DB readback.

### 7.3. Do Not Call setCurrentTransactionName Directly to "Rename"

`TransactionSynchronizationManager.setCurrentTransactionName(...)` is an infrastructure API used by the manager during begin/cleanup. Business code **should not call it directly** to "name the transaction" while the manager is managing the scope; doing so can easily corrupt metadata, break restore behavior on nested/suspend, and make logs confusing.

The right way to set the name is **before** `getTransaction` via `DefaultTransactionDefinition.setName(...)`, or via `TransactionTemplate.setName(...)` when using a template.

### 7.4. How Other Propagation Behaviors Affect the Name

| Scenario | Typical result on DataSourceTransactionManager |
| --- | --- |
| No outer, named `REQUIRED` | Manager creates physical T, current name is the definition name |
| Existing outer T, named inner `REQUIRED` | Inner joins T, current name remains the outer name |
| Existing outer T, named inner `REQUIRES_NEW` | Suspends outer; inner gets its own name; resume restores outer name |
| `NESTED` with savepoint | Does not open a separate physical transaction; do not assume it changes outer name |
| `SUPPORTS` without T | Logical/synchronization scope may exist; check manager mode, do not equate current name with physical T |
| After commit/rollback cleanup | Current name is restored/cleared by the manager for the scope; outside transactions usually `null` |

The statements in the table describe the **imperative model of the manager and synchronization**, not a contract for all reactive/JTA/vendor transactions. With multiple managers or custom synchronization modes, results may differ.

## 8. Naming for Observability Without Causing Operational Issues

A convention should help operators identify the **business operation type**, without exposing personal information:

| Suggested name | Reason |
| --- | --- |
| `orders.create` | Stable, describes a transaction type |
| `payments.capture` | Indicates the managed operation |
| `inventory.adjust` | Easy to group by processing flow |
| `reports.monthly.close` | Distinguishes batch/report with clear purpose |
| `audit.persistAttempt` | Suggests if an independent transaction is used for auditing |

Avoid:

- `"orders.create.customer-email@example.com"`: leaks PII.
- `"orders.create.cardNumber=..."`: risk of leaking sensitive data.
- `"orders.create#" + UUID.randomUUID()`: too many unique values can make metric/log cardinality very high.
- Naming everything just `"transaction"`: provides no debugging help.
- Names that misrepresent semantics, such as `"committed"` before knowing whether the transaction commits successfully.

**Separate transaction names (low cardinality) from correlation IDs (high cardinality)**. Correlation IDs belong in a dedicated trace/MDC/context; you must also follow security policies and restrict sensitive data.

Names in Spring are only useful with tools that actually collect/display them. Do not assume every APM automatically attaches the transaction name to every SQL span; verify the deployed instrumentation/agent.

## 9. Choosing Direct PlatformTransactionManager or TransactionTemplate?

Spring recommends `TransactionTemplate` for many **imperative programmatic transaction** cases because it reduces begin/commit/rollback boilerplate. `DefaultTransactionDefinition` remains useful for understanding metadata and when direct manager control is needed.

Comparison:

| Criterion | Direct manager | TransactionTemplate |
| --- | --- | --- |
| Create transaction | `getTransaction(def)` | `execute(callback)` |
| Complete transaction | Call `commit`/`rollback` yourself | Handled by template |
| Set name | `DefaultTransactionDefinition.setName` | `TransactionTemplate.setName` |
| Propagation/isolation/timeout | Definition setters | Template setters |
| Control multiple nested scopes | Explicit but more code | Can create separate templates per scope |
| Risk of forgetting rollback or double-completing status | Higher | Lower thanks to callback |

### 9.1. A TransactionTemplate Example with Name

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setName("inventory.reserve");
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE inventory SET quantity = quantity - 1 WHERE id = ?", 5);
});
```

This is an **illustrative code snippet**: it needs a manager, jdbc, an inventory table, and imports. The template also uses the transaction manager; `setName` configures similar metadata, and then the callback runs within the transaction boundary.

### 9.2. Template Has Mutable Configuration

`TransactionTemplate` holds configuration state; one instance can be reused across threads as long as **setters are not modified while in use**. If you need multiple different names/propagations, create separate configured instances or an appropriate factory; do not mutate a singleton template per concurrent request.

### 9.3. TransactionTemplate and Exceptions

When the callback throws an unchecked exception, `TransactionTemplate` handles rollback automatically according to the template mechanism. When you want to roll back without throwing an exception, the callback can call `status.setRollbackOnly()`. For checked exceptions in the callback, Java lambdas/functional interfaces require an appropriate conversion/handling design; do not assume all checked exceptions propagate straight through like the low-level API.

In this lesson, the demo uses the manager directly to clearly show **`DefaultTransactionDefinition` → `getTransaction` → `TransactionStatus` → `commit/rollback`**.

## 10. Common Mistakes with getTransaction, setName, and rollback

### Mistake 1 — Thinking setName Opens a Transaction Immediately

`def.setName("orders.create")` only modifies metadata. Only when the manager receives `getTransaction(def)` does it create or join a scope.

### Mistake 2 — Thinking the Name Is a Physical Transaction ID

One name can repeat across many calls; one physical transaction can have multiple logical scopes with differently named definitions. If you need to identify the transaction on the DB side, use DB-specific tools and reliable correlation.

### Mistake 3 — Reading Current Name Before Calling getTransaction

`TransactionSynchronizationManager.getCurrentTransactionName()` when there is no transaction context yet typically returns `null`, even if you just created a named `DefaultTransactionDefinition`.

### Mistake 4 — Inner REQUIRED Sets a Different Name but No New Name Appears

If inner joins an already open transaction, the manager may keep the outer synchronization/name. Changing inner to `REQUIRES_NEW` just to see a different name is wrong if the business logic still requires shared atomicity.

### Mistake 5 — Catching an Exception and Forgetting to Rollback

With the direct manager API, a Java `catch` does not automatically end the transaction. You must call `rollback(status)` or design with `TransactionTemplate`; otherwise, the connection may stay held and data can end up in a hard-to-control state.

### Mistake 6 — Committing and Then Trying to Rollback in a Shared Catch

If `commit(status)` is placed inside the same try-catch wrapping the whole flow, an error during commit itself can cause the catch block to call `rollback(status)` **a second time**. The manager may have already completed/cleaned up the status, or the DB commit outcome may be unclear. Separate business error handling from commit and design idempotency if needed.

### Mistake 7 — Reusing a TransactionStatus for Another Transaction

A status belongs to a single logical scope. After commit/rollback it is completed; never store it in a static/singleton field to reuse for a subsequent request.

### Mistake 8 — Interpreting setReadOnly(true) as a Guaranteed Write Block

Read-only is a hint/behavior dependent on the manager and DB. It does not replace DB permissions, constraints, and business validation.

### Mistake 9 — Expecting Inner REQUIRED Isolation/Timeout to Override Outer

An inner REQUIRED joining an existing T normally does not change the physical isolation/timeout already established by outer. You can enable the manager's validation mode to detect mismatches instead of expecting an override.

### Mistake 10 — Using the Wrong Manager or DataSource

A programmatic transaction managed by manager A will not automatically roll back operations using connection B that does not participate in the same resource. Verify the actual beans, DataSource, EntityManagerFactory, and repositories.

### Mistake 11 — Enabling Transaction Names Without Protecting Data

If a transaction name contains a username, token, email, or identifying ID, that information can flow into logs/tracing/metrics. Use stable business labels and separately governed correlation IDs.

### Mistake 12 — Opening a Transaction and Calling a Long Network API

A physical transaction can hold a DB connection and row locks while waiting. Keep scopes short and use idempotent/outbox/saga workflows when coordinating with external systems; naming the transaction does not reduce lock contention.

## 11. Debugging When currentName Does Not Match Expected

If `getCurrentTransactionName()` returns `null` or a different name:

| Question to ask | How to check |
| --- | --- |
| Was `getTransaction(def)` called yet? | Check call order and manager logs |
| What is `def.getName()` right before the call? | Assert the name; avoid mutating a shared definition |
| Did the manager open a new transaction/synchronization? | `status.isNewTransaction()` and `TransactionSynchronizationManager` flags |
| Was an outer transaction created earlier? | `REQUIRED` only joins; current name may be outer's |
| Is inner truly `REQUIRES_NEW`? | Check status, suspend/resume, transaction manager |
| Are there multiple transaction managers? | Check the actual injected bean and corresponding DataSource |
| Is code running on a different thread? | Imperative synchronization/name is thread-bound |
| Did something manually call `setCurrentTransactionName`? | Search for infrastructure code interfering with lifecycle |
| Is the measurement outside the transaction scope? | After cleanup, current name is usually null |
| Is a test transaction wrapping it? | Spring TestContext may open T before demo code |

Temporary logs you can enable:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

With the **direct manager API**, transaction manager logs matter more than interceptor logs because the code may not go through declarative `TransactionInterceptor`. Do not judge success solely from "name printed"; read back the DB and scope status to verify commit/rollback.

### 11.1. When Running @Async or Executor

The imperative `TransactionSynchronizationManager` model is bound to the thread. `@Async` or an `Executor` does not automatically carry the transaction context/name to another thread. If another method runs on a worker thread, it needs its own transaction context and its own name; do not use a currentName string on the request thread to infer that DB changes on the worker thread participate in the old T.

### 11.2. When Using the Reactive Stack

Spring reactive uses `ReactiveTransactionManager` and `org.springframework.transaction.reactive.TransactionSynchronizationManager`, which differ from the static thread-bound imperative model. Do not extrapolate from the JDBC examples above to assume a Reactor subscriber can read via imperative static methods. Use `TransactionalOperator` and the appropriate Reactor context.

### 11.3. When the Transaction Has Ended but the DB Result Is Uncertain

If an exception occurs at commit and the connection/ACK is lost, the commit state can sometimes be **indeterminate**. A transaction name is only a label; you need a durable operation ID, idempotency, and reconciliation to determine whether the business operation was carried out.

## 12. Testing Accurately: Name, Scope, and Data

A meaningful test should verify **both metadata and post-transaction DB state**:

1. Use a real Spring context with a `PlatformTransactionManager` bound to the right resource.
2. Create a new definition, `setName("test.operation")`, call `getTransaction`, and assert the current name inside the scope.
3. Check `status.isNewTransaction()` when there is no outer transaction.
4. INSERT a record and commit, then read back on an appropriate connection/transaction after the boundary; assert the record persists.
5. INSERT another record and roll back, then read back; assert the record has disappeared.
6. Open outer `REQUIRED` named A and inner `REQUIRED` named B; assert inner new=false and current name remains A in the demo manager.
7. Open outer `REQUIRED` named A and inner `REQUIRES_NEW` named C; assert C inside inner, and after inner finishes assert outer name A is restored.
8. Roll back outer after inner NEW commits to verify inner committed independently; roll back outer after inner REQUIRED succeeds to verify inner did not commit separately.
9. After each call, assert no transaction/name leaks into another run step.

### 12.1. The @Transactional Pitfall on Test Methods

If Spring TestContext opens a transaction for a test method annotated with `@Transactional`, a programmatic `REQUIRED` may **join the test's transaction** instead of creating a new physical transaction. In that case `isNewTransaction()` may be false, currentName is the test/outer's, and inner scope commits will not persist data like in the demo.

To test like a real caller with no active transaction, use a test method without `@Transactional`, or actively control the test transaction with `TestTransaction` and read back at the exact boundary.

### 12.2. Checking rollback-only and UnexpectedRollbackException

If an inner status participates in the same T, calling `manager.rollback(innerStatus)` can mark the shared T rollback-only. Outer code may still return normally, yet when `manager.commit(outerStatus)` runs, Spring may roll back and throw `UnexpectedRollbackException`. That is not a "commit bug": the manager intentionally refuses to report a false commit.

If the business logic requires inner to commit independently, `REQUIRES_NEW` is an option, though it changes atomicity. Do not change propagation just to suppress an exception without checking the remaining data after an error.

## 13. Knowledge Self-Check

**Question 1.** Does `DefaultTransactionDefinition def = new DefaultTransactionDefinition();` open a DB transaction by itself?

**Answer:** No. This is only metadata; you must call `PlatformTransactionManager.getTransaction(def)`.

**Question 2.** Does `def.setName("report.monthly")` make the DB-side physical transaction name become that string?

**Answer:** Not guaranteed. It is a logical name that Spring can publish/expose to transaction monitoring. Do not use it as a DB transaction ID.

**Question 3.** How do you read the current name in imperative Spring?

**Answer:** `TransactionSynchronizationManager.getCurrentTransactionName()` within an appropriate scope. It may return `null` when no name/context is present.

**Question 4.** Outer opens T named `"orders.batch"`, inner `REQUIRED` calls setName `"inventory.join"`. Which name does inner see in the demo?

**Answer:** `"orders.batch"`, because inner joins the existing T; it does not open a new physical context to replace the outer name.

**Question 5.** Change inner to `REQUIRES_NEW` with name `"audit.persist"`. What happens?

**Answer:** Spring suspends outer's T and opens a new T2; inside inner you see `"audit.persist"`, and after T2 commits/rolls back and outer resumes you see the outer name again.

**Question 6.** Inner `REQUIRED` has called `manager.commit(innerStatus)`. Has inner's data physically committed yet?

**Answer:** Not necessarily. If inner only joined outer T, committing the inner status does not physically commit T; a subsequent outer rollback cancels inner's changes as well.

**Question 7.** Should you call `rollback(status)` in a catch block when `commit(status)` throws an exception?

**Answer:** Do not do so blindly. The status may already be completed/cleaned up or the DB-side outcome may be unclear. Handle it according to manager lifecycle and business idempotency.

**Question 8.** Does `@Transactional("transactionManager")` set the transaction name to `"transactionManager"`?

**Answer:** No. That string selects the transaction manager bean/qualifier, not the transaction name set with `DefaultTransactionDefinition.setName`.

**Question 9.** Can `TransactionTemplate` be used to set a name?

**Answer:** Yes. `TransactionTemplate` has `setName(...)` and uses `execute`/`executeWithoutResult` to reduce direct boilerplate.

**Question 10.** Why should you use `"orders.create"` instead of `"orders.create#UUID"` in metrics?

**Answer:** A stable name groups transactions of the same type without unbounded cardinality growth or identifier exposure. Request/operation IDs belong in a separate trace context with protection policies.

## 14. Official References

- Spring Framework — Programmatic Transaction Management, `Using the PlatformTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.1 — `DefaultTransactionDefinition` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework 6.1 — `TransactionDefinition` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework 6.1 — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html

**Takeaway:** `DefaultTransactionDefinition` describes how a transaction will be managed; `setName` sets a **logical name for observability**, and does not open a transaction by itself. `PlatformTransactionManager.getTransaction` returns a status for your code to **commit/rollback exactly once**. When joining `REQUIRED`, the current name may remain the outer's; with `REQUIRES_NEW`, inner gets its own name and then resumes the outer name. Use stable names and verify both the thread-bound name and the **post-transaction DB state**.