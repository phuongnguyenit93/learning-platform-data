# REQUIRED — Joining an Existing Physical Transaction in Spring Framework

## 1. Objective and Key Idea

`Propagation.REQUIRED` is the **default propagation mode** for declarative transactions in Spring Framework. When a method annotated with `@Transactional` is invoked through the transaction infrastructure:

- If **no suitable transaction exists**, it starts a new physical transaction.
- If **a physical transaction managed by the corresponding manager already exists**, it **joins the existing transaction**. The inner invoked method has its **own logical transaction scope**, but does not own an independent physical commit.

The key point to remember is: **two `@Transactional(REQUIRED)` methods do not mean two physical transactions**. They are typically two logical transaction scopes controlling the same physical transaction. Only when the outermost scope that created the transaction completes successfully are the changes belonging to the shared transaction actually committed.

Order example:

```text
OrderService.placeOrder()  [REQUIRED — opens transaction T]
  ├─ INSERT orders          [transaction T]
  ├─ InventoryService.reserve() [REQUIRED — joins T]
  │    └─ UPDATE stock      [transaction T]
  └─ INSERT order_items     [transaction T]
End of outer scope          [COMMIT or ROLLBACK transaction T]
```

If the inventory operation fails according to rollback rules, both the order and the inventory change in transaction T are typically rolled back. Because inventory "joined" T, it **cannot commit its own part of T independently** while the outer transaction is still in progress.

After completing this lesson, you will:

1. Distinguish **physical transaction**, **logical transaction scope**, and DB connection/resource.
2. Understand how `REQUIRED` behaves differently with or without an existing transaction.
3. Explain why an inner method returning normally does not guarantee data has been committed.
4. Analyze `rollback-only` and the cause of `UnexpectedRollbackException` when an inner scope fails even though the outer catches the exception.
5. Run a Java 17+, Spring JDBC, and H2 example covering four cases: outer/inner succeed, inner fails and outer catches the error, outer fails, and inner runs standalone.
6. Use `REQUIRED` at the right business boundaries and avoid confusion with `REQUIRES_NEW`, `NESTED`, self-invocation, `readOnly`, or transactions on different managers.

The scope of this lesson is **Spring Framework — transaction management**, specifically **REQUIRED**. The main examples use a single imperative transaction manager managing **one DataSource**. Multi-resource or reactive cases have separate mechanisms.

## 2. What Does "Joining an Existing Physical Transaction" Mean?

### 2.1. Physical transaction

A *physical transaction* is a real transaction managed by the underlying resource: for example, on JDBC, a connection operating between `BEGIN`/SQL operations/`COMMIT` or `ROLLBACK` as implemented by the driver/DB. Spring's `DataSourceTransactionManager` or `JdbcTransactionManager` coordinates the connection from the `DataSource` and that transaction.

When one service calls another service, Spring can create **two logical transaction scopes**, while keeping the same physical transaction T:

```text
                 Request execution thread
    ┌───────────────────────────────────────────┐
    │ OuterService.execute()                     │
    │ @Transactional(REQUIRED)                   │
    │    logical scope A — owner of T            │
    │    ┌──────────────────────────────────┐    │
    │    │ InnerService.apply()             │    │
    │    │ @Transactional(REQUIRED)         │    │
    │    │    logical scope B — joins T      │    │
    │    └──────────────────────────────────┘    │
    └───────────────────────────────────────────┘
                       |
                       v
             One physical transaction T
             on the same JDBC DataSource
                       |
                COMMIT or ROLLBACK
                    by scope A
```

This is **one shared transaction resource**, not B opening a new transaction and later "merging" its result into A.

### 2.2. Logical transaction scope

Each method passing through the Spring transaction interceptor with `REQUIRED` creates a **logical transaction scope**. This scope can:

- Declare its own transaction attributes.
- Join an existing physical transaction.
- Observe the active transaction and use the bound resource.
- Mark rollback-only when a matching exception passes through the advice or when requested by the application.
- End its invocation before the outer scope.

An inner logical scope **does not mean** a separate physical commit. An inner method returning successfully only means it finished its Java execution and its transaction advice completed handling its logical scope. The outer method can still fail in a later step, causing **all of T to roll back**.

### 2.3. Matrix: existing transaction or not?

| Before calling the `REQUIRED` method | What does the method do? | Creates a new physical transaction? | Who decides the final commit? |
| --- | --- | --- | --- |
| No transaction | Creates transaction T | **Yes** | This scope, barring special manager/outer infrastructure cases |
| Existing transaction T of the same suitable manager/resource | Joins T | **No** | The scope that opened T |
| Another scope is already participating in T | Continues joining T | **No** | The owner scope of T |
| Transaction of another resource/manager | Must analyze the actual manager and resource | Cannot be inferred from annotation alone | Each manager/resource per configuration |
| Direct call to target bypassing proxy (proxy mode) | Transaction advice for this method does not run separately | Not created by that method's annotation | Existing transaction if any; otherwise outside any Spring transaction |

This table assumes `REQUIRED` propagation is actually applied through Spring AOP or a corresponding advice mechanism; an annotation on a method that is not intercepted does not create a new logical scope on its own.

## 3. How Spring Executes REQUIRED

`@Transactional` is metadata. Spring's infrastructure uses `TransactionInterceptor` together with `PlatformTransactionManager` and transaction attributes to open or join transactions.

A standard flow:

```text
Caller → Spring AOP proxy of OuterService
   |
   v
Outer TransactionInterceptor
   |
   +-- getTransaction(REQUIRED), no T yet
   +-- create physical transaction T, bind resource to thread
   |
   v
OuterService.execute()
   |
   +-- Outer SQL uses T
   |
   +-- call Spring AOP proxy of InnerService
        |
        v
      Inner TransactionInterceptor
        |
        +-- getTransaction(REQUIRED), T already exists
        +-- join T (no second BEGIN/transaction connection)
        |
        v
      InnerService.apply()
        |
        +-- Inner SQL uses T
        +-- return or exception
        |
        v
      Inner advice ends logical scope B
   |
   +-- OuterService continues
   |
   v
Outer advice ends logical scope A
   |
   +-- T not rollback-only and no error → COMMIT T
   +-- T rollback-only / error requiring rollback → ROLLBACK T
   |
   v
Caller receives return value or exception
```

In the common imperative JDBC model, Spring binds the connection/resource to the thread via `TransactionSynchronizationManager`. `JdbcTemplate` and `DataSourceUtils` know how to obtain the managed connection. Therefore, outer and inner typically execute SQL on the **same connection within one physical transaction**, provided both use the same `DataSource`.

**One connection does not mean every operation is transaction-safe:** if code opens a connection directly via an API that bypasses Spring's resource binding, uses a different `DataSource`, calls an external system, or switches threads, those operations may not participate in T. What must be verified is the **manager and resource**, not just whether a bean has `@Transactional`.

### 3.1. REQUIRED is the default

The following declarations are normally equivalent in terms of propagation:

```java
@Transactional
public void updateInvoice() {
    // ...
}

@Transactional(propagation = Propagation.REQUIRED)
public void updatePayment() {
    // ...
}
```

This illustrates annotation usage; it is not a standalone class. `Propagation.REQUIRED` belongs to the `org.springframework.transaction.annotation` package. Besides propagation, there are rollback rules, read-only, isolation, and timeout; these are analyzed later.

### 3.2. The concept of isNewTransaction()

In imperative Spring, inside a method intercepted by transaction advice, you can check:

```java
boolean newPhysical =
    TransactionAspectSupport.currentTransactionStatus()
        .isNewTransaction();
```

In a simple example with `DataSourceTransactionManager`:

- Outer starts transaction T: `isNewTransaction() == true`.
- Inner `REQUIRED` joins T: `isNewTransaction() == false`.
- Inner called directly from a caller without a transaction: `isNewTransaction() == true`.

This is a convenient indicator of the current transaction scope's role with respect to the manager, not a conclusion that one database transaction can span every external system.

Be careful: `TransactionAspectSupport.currentTransactionStatus()` requires a transaction status attached to a Spring transaction aspect invocation; calling it in a method not managed by advice can throw `NoTransactionException`.

## 4. Business Example: One Shared Commit for Two Services

Suppose placing an order requires writing an order record and deducting inventory:

```java
@Service
public class OrderService {
    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder() {
        saveOrder();
        inventory.reserveStock();
    }
}

@Service
public class InventoryService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void reserveStock() {
        decreaseStock();
    }
}
```

The code above is an **architectural illustration**, omitting the implementations of `saveOrder`, `decreaseStock`, and imports. When both beans are managed by Spring, the caller goes through the proxy, and both DB operations use the same transaction manager/DataSource:

- `placeOrder` initiates T.
- `reserveStock` joins T without creating a new physical transaction.
- If both methods succeed, T commits when `placeOrder` finishes through the interceptor.
- If `reserveStock` fails with a runtime exception escaping through the proxy, T is normally marked rollback-only; when the outer scope ends, T is not committed.
- If `reserveStock` succeeds but `placeOrder` fails later, the inventory deduction **still rolls back** along with the order.

Key design point: **a use-case-level transaction boundary** protects the invariant "valid order and synchronized inventory". To keep this unit of work atomic, do not casually change inner to `REQUIRES_NEW`: it could commit inventory separately even if outer fails.

## 5. Runnable Demo: REQUIRED Sharing a Physical Transaction

We use **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, and **H2 in-memory**. The runnable project is a small Gradle project requiring no server. It intentionally invokes services through Spring proxies and uses a single `DataSourceTransactionManager` so the results are clear.

### 5.1. Directory structure

```text
required-join-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/required/
    │   ├── RequiredApplication.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'required-join-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'lesson'
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

`spring-boot-starter-jdbc` provides `JdbcTemplate` and Spring transaction infrastructure. H2 is an embedded database, and Spring Boot uses `schema.sql` to initialize the table. Versions in the example are for reproducibility; production deployments should use a currently supported Spring Boot version.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

Each scenario uses different IDs. We read back row counts **after the transaction scope finishes**, avoiding conclusions based on uncommitted data.

### 5.2. InnerService — REQUIRED can join or open a transaction on its own

**`src/main/java/lesson/required/InnerService.java`**

```java
package lesson.required;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(int id) {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("inner newTx=" + newTransaction);
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, "inner"
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeAndFail(int id) {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("innerFail newTx=" + newTransaction);
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, "inner-fail"
        );

        throw new IllegalStateException("inner boom");
    }
}
```

Both methods are marked `REQUIRED`. **They do not unconditionally open a new transaction.** When called from an outer transaction, `isNewTransaction()` is `false`. When called from the runner with no outer transaction, `write(7)` creates a transaction on its own and `isNewTransaction()` is `true`.

In the failure case, `writeAndFail` INSERTs first and then throws `IllegalStateException`. The runtime exception passes through the inner interceptor under the default rollback rule.

### 5.3. OuterService — creates a transaction for the entire unit of work

**`src/main/java/lesson/required/OuterService.java`**

```java
package lesson.required;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            1, "outer-success"
        );

        inner.write(2);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchesInner() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            3, "outer-before-inner-failure"
        );

        try {
            inner.writeAndFail(4);
        } catch (IllegalStateException ex) {
            System.out.println("outer caught=" + ex.getMessage());
        }

        System.out.println("outer reached return");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void failsOuter() {
        showOuterTransaction();

        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            5, "outer-before-own-failure"
        );

        inner.write(6);
        throw new IllegalStateException("outer boom");
    }

    private static void showOuterTransaction() {
        boolean newTransaction =
            TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();

        System.out.println("outer newTx=" + newTransaction);
    }
}
```

In all three public methods invoked from the runner, outer is the owner of the new physical transaction. `inner` is **another injected bean**, so calls to `inner.write(...)` or `inner.writeAndFail(...)` go through a separate proxy and create the inner logical scope.

Do not replace these calls with `this.innerMethod()` and assume there is still separate advice: self-invocation in Spring proxy mode does not execute transactional advice for the inner method, even though it can continue using the transaction already opened by outer.

### 5.4. Application — creates manager, calls proxies properly, reads DB results

**`src/main/java/lesson/required/RequiredApplication.java`**

```java
package lesson.required;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class RequiredApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            OuterService outer, InnerService inner, JdbcTemplate jdbc) {
        return args -> {
            // 1. Outer succeeds; inner joins and commits together.
            outer.success();
            System.out.println("successRows=" + count(jdbc, 1, 2));

            // 2. Inner marks rollback-only; outer catches error and returns.
            try {
                outer.catchesInner();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "caughtOutcome=" + ex.getClass().getSimpleName());
            }
            System.out.println("caughtRows=" + count(jdbc, 3, 4));

            // 3. Inner succeeds but outer fails: both roll back.
            try {
                outer.failsOuter();
            } catch (IllegalStateException ex) {
                System.out.println("outerError=" + ex.getMessage());
            }
            System.out.println("outerFailureRows=" + count(jdbc, 5, 6));

            // 4. No outer transaction; inner's REQUIRED opens a new one.
            inner.write(7);
            System.out.println("standaloneRows=" + count(jdbc, 7, 7));
        };
    }

    private static int count(JdbcTemplate jdbc, int fromId, int toId) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id BETWEEN ? AND ?",
            Integer.class, fromId, toId
        );
        return value;
    }
}
```

**Why is this configuration clear?**

- `@SpringBootApplication` scans the services in package `lesson.required`.
- `@EnableTransactionManagement(proxyTargetClass = true)` enables annotation-driven transaction management with class-based proxies suitable for services without interfaces.
- The `transactionManager` bean uses the same `DataSource` as `JdbcTemplate`. Both outer and inner execute SQL statements under the management of **a single transaction manager**.
- `CommandLineRunner` is created by Spring and injected with the proxied services. The runner has no `@Transactional`, so each call to outer starts a new transaction, and calling `inner.write(7)` directly causes inner to open a new transaction on its own.
- The `count` checks run **after** each service call has finished through its proxy, showing the committed or rolled-back state.

To avoid false conclusions, do not place `@Transactional` on the `demo` method in this lesson. If the runner had an enclosing transaction, `isNewTransaction()` and commit timing would change.

### 5.5. Run and compare stdout

Requires JDK 17+ and a compatible Gradle 8.x. Inside the `required-join-demo` directory, run:

```bash
gradle bootRun
```

If the project has a compatible Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Because the code depends on Spring/H2, do not compile with `javac` using a plain JDK classpath.

Ignoring Spring Boot/Gradle logs, the lines printed by the program in order are:

```text
outer newTx=true
inner newTx=false
successRows=2
outer newTx=true
innerFail newTx=false
outer caught=inner boom
outer reached return
caughtOutcome=UnexpectedRollbackException
caughtRows=0
outer newTx=true
inner newTx=false
outerError=outer boom
outerFailureRows=0
inner newTx=true
standaloneRows=1
```

**Interpretation of the cases:**

| Case | Outer scope | Inner scope | Physical commit/rollback | Query result |
| --- | --- | --- | --- | --- |
| `outer.success()` | Creates T1 | Joins T1 | Commits T1 after outer returns | Both records id 1, 2 exist |
| `outer.catchesInner()` | Creates T2 | Joins T2, throws runtime | Inner marks T2 rollback-only; outer attempts commit → rollback | Both id 3, 4 absent |
| `outer.failsOuter()` | Creates T3, throws runtime | Joins T3, returns normally | Outer rolls back T3 | Both id 5, 6 absent |
| Standalone `inner.write(7)` | None | Creates T4 | Commits T4 when inner returns | Id 7 exists |

### 5.6. Special failure case: outer catches exception yet still rolls back

In `catchesInner()`, outer handled the `IllegalStateException` thrown by inner:

```text
Outer opens T2, INSERT id=3
   |
Inner joins T2, INSERT id=4
   |
Inner throws IllegalStateException
   |
Inner transaction advice checks rollback rule
   |
T2 is marked GLOBAL rollback-only
   |
Outer catches IllegalStateException, returns normally
   |
Outer interceptor attempts to commit T2
   |
T2 rolls back → UnexpectedRollbackException reaches runner
```

**Why does Spring deliberately throw `UnexpectedRollbackException`?** Because the caller should not receive a successful result from the outer method when the physical transaction ultimately **rolled back**. This is a mechanism to prevent a "silent/false commit" even though the outer code returned normally. The exception appears **at the outer boundary**, not inside outer's `catch` block.

Here `rollback-only` is a transaction state flag, not an early undo of a single INSERT/UPDATE. The inner scope **does not** roll back id 4 as an independent transaction and then let outer commit id 3; all of T2 is rolled back together.

The usual default behavior of `AbstractPlatformTransactionManager` is that when a participating scope fails and requires rollback, it marks the physical transaction rollback-only. The final outcome still depends on rollback rules, the transaction manager, propagation, and whether the error passes through advice.

### 5.7. Why can inner still lose its data even after succeeding?

In `outer.failsOuter()`, inner returns normally, but outer continues and throws `IllegalStateException`. Inner did not commit independently: it only completed its logical scope. When outer rolls back T3, **both id 5 and id 6 disappear**. This preserves the "single unit of work" semantics at the outer level.

**Most valuable observation:** an inner `REQUIRED` method can succeed locally, yet its results **only persist durably when the physical transaction is committed by the scope that owns it**.

### 5.8. Calling inner standalone

In the `inner.write(7)` call, the runner has no transaction and there is no outer scope. `REQUIRED` now **creates T4 on its own**, so `inner newTx=true`. When the method call completes successfully through the proxy, Spring commits T4.

Nothing is "different" in inner's annotation between id 2 and id 7; only the **transaction context before the call** differs.

## 6. Transaction Status: Distinguishing Local and Global Rollback-Only

When Spring manages propagation, there can be different levels of status:

- **Local rollback-only:** a logical scope requests rollback, for example code calling `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` within its scope.
- **Global rollback-only:** the shared physical transaction has been marked uncommittable, for instance because a participating scope threw an exception and the manager applies rollback-on-participation-failure, or the underlying resource reported that the transaction was aborted.

An outer scope may not have set local rollback-only itself, yet the shared transaction is already global rollback-only because of inner. Thus `outer.return` does not mean `commit` will succeed.

### 6.1. Where you catch the error determines the outcome

Compare two patterns:

**Pattern A — Inner exception passes through proxy, then outer catches it:**

```java
@Transactional
public void outer() {
    try {
        innerService.doWork(); // doWork() has @Transactional(REQUIRED)
    } catch (IllegalStateException ex) {
        // Inner interceptor already handled the error and may mark rollback-only.
    }
}
```

If `doWork`'s inner interceptor actually observes the RuntimeException, the shared physical transaction is usually already rollback-only. Returning from outer can still result in `UnexpectedRollbackException`.

**Pattern B — Inner catches the exception itself before returning:**

```java
@Transactional
public void doWork() {
    try {
        performStep();
    } catch (IllegalStateException ex) {
        // No rethrow, no setRollbackOnly.
    }
}
```

Provided there is no transaction resource error and no other scope has already marked rollback-only, `doWork`'s advice sees a normal return, so it **does not mark rollback-only because the exception was swallowed**.

Both examples only illustrate the mechanism; definitions of `innerService` and `performStep` are omitted. Do not swallow errors merely to force a commit. Design clear error messages, rollback rules, and business invariants.

### 6.2. Explicitly marking rollback-only

In an imperative transaction, a method can call:

```java
TransactionAspectSupport.currentTransactionStatus()
    .setRollbackOnly();
```

This is a Spring API call inside a transaction-advised invocation. If the scope is participating in T, when the scope finishes, rollback-only can propagate to the shared transaction. It fits when you want to return a business result from the method yet **cannot allow the transaction to commit**.

However, this couples business code to the transaction framework, and with multi-scope `REQUIRED` it can cause outer to hit `UnexpectedRollbackException` even if outer returns normally. If you do not need to return a result-style response, throwing a well-typed domain exception and handling it outside the boundary can be clearer.

### 6.3. Checked exceptions do not automatically mark rollback-only

Under Spring declarative transaction default rules, `RuntimeException` and `Error` lead to rollback; a checked `Exception` such as `IOException` normally **does not**.

If an inner `REQUIRED` method throws `IOException` without `rollbackFor`, the interceptor may **not mark T rollback-only**. If outer catches the checked exception and continues, T can commit if no other issue occurs. If the business semantics require rolling back the entire order, configure `@Transactional(rollbackFor = IOException.class)` on the appropriate transaction boundary, or use runtime/domain exceptions with a consistent rollback policy.

Do not assume "any exception in an inner service always rolls back the whole transaction"; you must know the **actual exception class**, the **rule**, and **whether it escapes through the advice**.

## 7. How Outer Transaction Characteristics Are Preserved

A common misconception is that an inner `@Transactional(REQUIRED)` can alter the isolation, read-only setting, or timeout of an already-opened physical transaction. Under default configuration, when inner joins T, the physical characteristics of T are **primarily determined when T starts**.

| Attribute declared on inner REQUIRED | When inner creates a new transaction | When inner joins existing T |
| --- | --- | --- |
| `propagation = REQUIRED` | Creates T | Joins T |
| `isolation = READ_COMMITTED` | Manager may apply the isolation level | Does not automatically change T's isolation; by default inner declaration is ignored at the physical level |
| `readOnly = true` | May apply read-only hint/enforcement depending on manager/DB | Does not automatically turn a read-write T into read-only |
| `timeout = 5` | May set timeout for the new transaction | Does not automatically change the deadline of an already-opened T |
| `rollbackFor = ...` | Decides when error escapes inner advice | Still evaluated; can mark shared T rollback-only |
| `noRollbackFor = ...` | May allow commit despite matching throwable | Does not clear rollback-only already set by another scope |

Example:

```java
@Transactional(readOnly = false)
public void updateAndReport() {
    updateData();
    reportService.readReport(); // @Transactional(readOnly = true)
}
```

With `REQUIRED`, the report service usually **joins the existing read-write transaction**. The `readOnly` annotation on inner does not "downgrade" the physical transaction. Conversely, an inner writer attempting to join an outer read-only transaction must not be assumed to be upgraded to read-write; depending on the driver/DB, writes may be rejected.

### 7.1. validateExistingTransactions

Some Spring transaction managers (inheriting from `AbstractPlatformTransactionManager`) have a `validateExistingTransaction(s)` setting. When `validateExistingTransaction=true` is set, the manager can **reject** mismatched isolation declarations when a new scope joins an existing transaction; in strict validation mode, a read-write inner joining a read-only outer may also be rejected.

Illustrative Java configuration example:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

The code above is a configuration snippet requiring imports and a valid `DataSource`; do not add this bean to the demo project if a bean with the same name already exists. **Only use strict validation when the application clearly understands which services join outer transactions**; it can surface design mismatches in read-only/isolation that were previously ignored silently.

### 7.2. Do not treat readOnly as a security constraint

`@Transactional(readOnly = true)` does not necessarily make every database reject INSERTs. Its effect depends on the transaction manager, JDBC driver, ORM, and DB; it may only optimize flushing or provide a hint. Use DB permissions/constraints and service design to protect data.

## 8. REQUIRED vs. REQUIRES_NEW and NESTED

Choosing the right propagation is a requirement of the **business invariant**, not just a workaround for seeing rollback-only errors.

| Propagation | When outer already has T | Connection/physical transaction | Inner succeeds, outer later rolls back |
| --- | --- | --- | --- |
| `REQUIRED` | Joins T | One shared physical transaction | Inner changes also roll back |
| `REQUIRES_NEW` | Suspends T and opens independent T2 (when supported by manager) | Separate T2, usually requires another connection | Already-committed T2 typically keeps its results |
| `NESTED` | Joins physical transaction T, creates savepoint if supported | One physical transaction and a savepoint | Outer rolling back T still discards all changes, including inner changes whose savepoint was released |

### 8.1. Why not use REQUIRES_NEW to "avoid UnexpectedRollbackException"?

If inventory reservation uses `REQUIRES_NEW`, it can commit inventory in its own transaction even if the outer order placement rolls back. This **does not preserve** the invariant "order and inventory succeed together"; it changes the business semantics. `REQUIRES_NEW` is sometimes appropriate for audit logs that must be preserved independently or system records, but you still need to understand partial success, connection pools, and deadlock risk.

In addition, an outer transaction holding an active connection while an inner `REQUIRES_NEW` needs an extra connection can exhaust the connection pool under concurrent requests. Do not switch to it just to "make things look okay".

### 8.2. How does NESTED differ from REQUIRED?

With a JDBC transaction manager supporting savepoints, `NESTED` can create a marker to roll back part of the inner changes to the savepoint without forcing the entire outer transaction to roll back in certain appropriate error-handling cases. However, **there is still only one physical transaction**, so an eventual outer rollback erases everything. `NESTED` is not supported identically across all managers or drivers; with JPA, you must specifically check savepoint/JDBC capabilities.

**In summary:** `REQUIRED` = join T together; `REQUIRES_NEW` = independent T2; `NESTED` = savepoint within T if supported. Choose based on whether inner needs to commit independently and the required level of business consistency.

## 9. When the Inner Method Does Not Go Through a Proxy

A `this.method()` call within the same Spring bean **does not** go through that method's proxy in default Spring AOP proxy mode:

```java
@Service
class BillingService {
    @Transactional
    public void createInvoice() {
        this.reserve(); // Does not trigger reserve()'s own advice.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // SQL ...
    }
}
```

This code is illustrative only. If `createInvoice()` was called from outside through a proxy, it can open T, and the code inside `reserve()` still executes SQL within T despite having no inner advice. However:

- `reserve()` does not create a **separate logical transaction scope** through a proxy.
- Inner-specific attributes such as `rollbackFor`/`REQUIRES_NEW` on `reserve()` are not applied by an internal call.
- If `createInvoice()` has no transaction and only `reserve()` is annotated, self-invocation can cause `reserve()` to run **without a Spring transaction**.

Therefore, when you want to observe two `REQUIRED` logical scopes as in the demo, call **another injected bean**. Use non-final public methods and appropriate proxy configuration. Do not use self-invocation as an example proving inner transaction advice runs.

## 10. Threads, Resources, and Managers: When Joining Cannot Happen Automatically

### 10.1. Thread-bound imperative transactions

A conventional Spring imperative transaction is bound to a thread via `TransactionSynchronizationManager`. Switching to `@Async` or spawning another thread does not automatically carry over the transaction context.

Illustrative example:

```java
@Transactional
public void process() {
    repository.save();
    executor.execute(() -> otherService.saveMore());
}
```

This is Java pseudocode missing variables/implementations. `saveMore` runs on a different thread and does not automatically join `process`'s physical transaction, even if that method is also `REQUIRED`. It may open a new transaction on its own if intercepted by a proxy on the new thread. Moreover, when the asynchronous task runs, the outer transaction may not have committed yet or may already have rolled back.

### 10.2. Multiple DataSources

If outer and inner use two different `DataSource`s/transaction managers, a `REQUIRED` annotation does not automatically turn operations across two DBs into an XA transaction. You need an appropriate manager, distributed transaction design, or eventual workflow design. With two independent local transactions, partial commits can occur. Check which connection each repository uses.

### 10.3. Reactive transactions

With Spring reactive and `ReactiveTransactionManager`, transaction context is propagated via Reactor context rather than imperative thread-locals, and methods must participate properly in the reactive pipeline. The `REQUIRED` rule of joining an existing transaction still applies conceptually, but implementation and verification differ from the JDBC demo. Do not use `TransactionAspectSupport.currentTransactionStatus()` as universal proof for reactive transactions.

## 11. Exceptions, Commit, and "Saved" Must Be Verified at the Right Time

### 11.1. After inner returns, data is not necessarily durable yet

If an inner `REQUIRED` method has sent an UPDATE successfully, the result may still be **uncommitted data**. A query within the same T can see that change (*read-your-writes*), yet that does not prove the data was committed. When outer rolls back, the change vanishes.

Consequently, tests that assert values right inside the outer transaction easily produce false positives. You must let the outer scope finish and then read back using an appropriate independent transaction/connection.

### 11.2. An exception at commit does not always mean rollback

`UnexpectedRollbackException` in the inner-marks-rollback-only scenario has a clear meaning: outer attempted to commit while the transaction was already marked for rollback; the manager rolled back and notified the caller. It should not be equated with **every** exception occurring at commit time.

If the connection drops before the caller receives acknowledgment from the DB, the commit outcome may be ambiguous. You need operation IDs, idempotency, and reconciliation. `REQUIRED` does not by itself resolve uncertainty at the DB/network boundary.

### 11.3. Late flushes and constraints

With JPA/Hibernate, many INSERTs/UPDATEs can be deferred until `flush` or commit. An inner method returning normally does not guarantee all constraints have been accepted by the DB, especially while the outer transaction has not ended. With JDBC, SQL is usually sent earlier, yet commit remains the final event making changes durable. Tests must account for whether JDBC or JPA is used and avoid assuming all write operations happen at the exact same moment.

## 12. Testing REQUIRED and Common Pitfalls

### 12.1. Recommended test suite

- **No outer transaction:** call inner `REQUIRED` standalone, verify it creates and commits its own transaction.
- **Outer + inner both succeed:** verify inner `isNewTransaction=false`, and both records are committed together.
- **Inner throws RuntimeException, outer catches it:** verify T is global rollback-only, outer returns normally at the Java level yet the proxy throws `UnexpectedRollbackException`, and changes from both scopes are absent.
- **Outer throws RuntimeException after inner succeeds:** verify both changes roll back.
- **Inner throws a checked exception:** check whether `rollbackFor` is declared and test the final state.
- **Outer read-only/inner read-write or different isolation:** verify whether the manager ignores the difference or has `validateExistingTransaction` enabled; test against the real resource.
- **Self-invocation:** ensure you do not confuse SQL running inside outer T with inner annotation being intercepted separately.
- **New thread/other resource:** verify they do not automatically join the imperative transaction T.

### 12.2. @Transactional on tests can mask issues

In Spring TestContext, a test method annotated with `@Transactional` can create its own transaction and roll it back after the test. If the test calls inner `REQUIRED`, inner will **join the test's transaction** instead of opening its own; the behavior differs from production when a controller has no transaction. Checking `isNewTransaction` and DB state after the test can produce unexpected results.

To prove commit/rollback when a real outer transaction ends, use integration tests that do not wrap everything in a test transaction, or use `TestTransaction` to control scope appropriately. Do not rely solely on the absence of records at the end of a test to conclude the service rolled back properly.

### 12.3. Enable transaction logs when needed

You can temporarily enable:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Logs can show when the transaction manager creates a new transaction, joins an existing transaction, marks rollback-only, or rolls back/commits. However, "joining a transaction" in logs must be cross-checked against the connection/resource and DB state; do not use logs as a substitute for verifying data after the outer scope completes.

## 13. Common Misconceptions About REQUIRED

| Misconception | Correct understanding |
| --- | --- |
| "Each `@Transactional(REQUIRED)` is a different DB transaction." | Multiple logical scopes can share a single physical transaction. |
| "Inner returning means inner has committed." | When joining T, inner does not commit separately; outer can roll everything back. |
| "If outer catches RuntimeException from inner, T can still commit." | Inner advice may have marked T rollback-only, causing outer to hit `UnexpectedRollbackException`. |
| "Outer rollback doesn't affect inner because inner already finished." | On the same T, an outer rollback discards inner's changes as well. |
| "Setting `readOnly = true` on inner turns the outer transaction read-only." | Physical properties of T are decided when T starts; inner does not change T on its own. |
| "Setting custom timeout/isolation on inner definitely overrides outer." | Inner joining T usually does not reconfigure physical attributes, and may be rejected if validation is enabled and incompatible. |
| "REQUIRED always opens a new connection." | When T already exists, inner normally uses the same managed resource/connection. |
| "REQUIRES_NEW is the perfect fix for rollback-only errors." | It changes atomicity, potentially letting inner commit even when outer rolls back. |
| "NESTED and REQUIRED are the same." | NESTED can create savepoints; REQUIRED does not create an independent savepoint. |
| "Self-invocation runs full inner transaction advice." | Under default proxy mode, `this.method()` bypasses inner's interception. |
| "One REQUIRED manager covers two DBs and email." | Only resources actually managed by the transaction manager participate. |

## 14. Design Checklist Before Using REQUIRED

Before placing `@Transactional(propagation = REQUIRED)`:

1. Have you identified the **business unit of work** whose steps must commit or roll back together?
2. Which outer method **owns the real boundary**, and when does the physical transaction end?
3. Is the inner service called through a Spring proxy and using the same manager/DataSource?
4. If inner fails, should outer be allowed to handle the error and continue, or must the entire unit of work be aborted?
5. Do exception types and rollback policies reflect the business outcome?
6. Do any steps use `REQUIRES_NEW`, a separate connection, another thread, or an external system?
7. If inner declares its own isolation/read-only/timeout, does it genuinely need a separate physical transaction or should outer's configuration be checked?
8. Do tests read DB state **after outer commit/rollback** and check for `UnexpectedRollbackException`?

For a use case requiring atomicity across multiple steps on **the same database**, the default `REQUIRED` is usually a great fit: outer creates T; inner services join T; the commit/rollback outcome applies to **the entire unit of work**. If independent outcomes are needed, change the transaction design intentionally rather than assuming each annotation corresponds to a COMMIT.

## 15. Self-Check Questions

**Question 1.** Outer `@Transactional(REQUIRED)` calls inner `@Transactional(REQUIRED)` through a proxy. How many physical transactions are there?

**Answer:** Usually just **one**, if both use the same transaction manager/resource and outer opened T. There are two logical scopes, with inner joining T.

**Question 2.** Inner `REQUIRED` returns normally, and outer throws `IllegalStateException` afterward. Does inner's data commit?

**Answer:** No, if inner joined the same T and outer rolls T back successfully. Inner did not commit separately.

**Question 3.** Inner `REQUIRED` throws `IllegalStateException`, outer catches it and returns normally. Why might the caller receive `UnexpectedRollbackException`?

**Answer:** The inner interceptor marked physical T rollback-only. When outer tries to commit, Spring rolls back T and throws the exception so the caller does not mistakenly believe the transaction committed.

**Question 4.** The same inner `REQUIRED` is called with no outer transaction. Does it behave differently?

**Answer:** Yes. It can create a new physical transaction on its own and own committing/rolling it back when the method ends.

**Question 5.** Inner declares `@Transactional(readOnly = true)` and joins an outer read-write T. Does T automatically switch to read-only?

**Answer:** No. The physical characteristics of T are established when outer opens the transaction; inner `REQUIRED` does not change them on its own.

**Question 6.** Should `UnexpectedRollbackException` be fixed by changing inner to `REQUIRES_NEW`?

**Answer:** Only if the business logic genuinely wants inner to commit/roll back independently. Otherwise, that breaks atomicity and can cause partial state.

**Question 7.** Why is self-invocation not a good example for demonstrating two transaction scopes?

**Answer:** Because `this.inner()` does not go through a separate Spring proxy in proxy mode; inner's annotation is not intercepted, even though the code may run inside the already-opened outer transaction.

**Question 8.** If an inner checked exception is not configured for rollback, and outer catches it and returns, is T guaranteed to roll back?

**Answer:** No. Checked exceptions normally do not mark rollback-only under default rules. T may commit if there are no errors or rollback-only flags from other sources.

## References

- Spring Framework — Transaction Propagation, `PROPAGATION_REQUIRED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Javadoc — `AbstractPlatformTransactionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html

**Summary:** `REQUIRED` **does not create a new physical transaction when a suitable transaction already exists**. It opens a logical scope that joins T, sharing commit/rollback with outer. An inner failure can mark T rollback-only; outer catching the exception is not enough to "save" T. Verify scope, transaction manager, resource, and DB state after the outer boundary to use `REQUIRED` properly.