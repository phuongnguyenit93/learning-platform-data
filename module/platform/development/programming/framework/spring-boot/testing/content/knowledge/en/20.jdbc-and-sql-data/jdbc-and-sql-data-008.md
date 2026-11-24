# JDBC Transactions vs. Reactive Transactions in Testing

## 1. Why Do SQL Transactions Test Differently Across Stacks?

In Spring Boot, a database write workflow may go through **JDBC (imperative/blocking)** or **R2DBC (Reactive Relational Database Connectivity)**. Both rely on SQL transactions: multiple writes **commit together** or **roll back on failure**. However, **Spring attaches transactions to the execution flow differently**.

- **JDBC** typically uses `DataSource`, `JdbcTemplate`, and a `PlatformTransactionManager` such as `JdbcTransactionManager` or `DataSourceTransactionManager`. Transactions bind to the **current thread** via Spring's `TransactionSynchronizationManager` and the corresponding connection.
- **R2DBC** typically uses `ConnectionFactory`, `DatabaseClient`/`R2dbcEntityTemplate`, and a `ReactiveTransactionManager` such as `R2dbcTransactionManager`. Transactions travel with the **subscription's Reactor Context**, independent of a fixed thread.
- In Spring Boot 3.x, **`@JdbcTest` is transactional and rolls back after each test by default**, whereas **`@DataR2dbcTest` is non-transactional by default**. This difference is crucial when running a test suite and checking for leftover data.
- A created R2DBC Publisher that has **not been subscribed to** normally has not executed any SQL yet. In contrast, `jdbcTemplate.update(...)` is an imperative call that executes immediately when invoked.
- `@Transactional` on an ordinary JUnit test method **does not automatically create a Reactor transaction** for Publishers executed inside it. Spring TestContext's test-managed transaction requires a `PlatformTransactionManager`; an R2DBC reactive transaction requires wrapping the **pipeline** with `TransactionalOperator` or invoking a properly configured proxied reactive `@Transactional` method.

**Lesson goal:** understand transaction boundaries; know how to test commits, rollbacks, subscriptions, and visibility; avoid extrapolating JDBC's default rollback to R2DBC; and write deterministic tests on Java 17+, JUnit Jupiter, and Spring Boot 3.x.

After this lesson, you will have two test suites **separated into two independent projects/modules**:

1. **JDBC + H2 + `@JdbcTest`:** 5 JUnit tests verifying test-managed rollback, `TestTransaction`, and `TransactionTemplate` commit/rollback.
2. **R2DBC + H2 + `@DataR2dbcTest`:** 6 JUnit tests verifying lazy subscription, `TransactionalOperator` commit/rollback, in-transaction visibility, and the impact of `onErrorResume` placement.

No WebFlux HTTP server, Docker, or production database is needed. Each sample has its own `schema.sql`; **do not put both dependency sets into a single Boot app without explicit configuration**, because `DataSource`/`ConnectionFactory` and auto-configurations may interact or disable one another.

## 2. What Is a Transaction and What Gets Rolled Back?

A SQL transaction typically provides four ACID properties: atomicity, consistency, isolation, and durability. For testing, we focus especially on:

- **Atomicity:** changes inside the same transaction commit or roll back together.
- **Isolation:** which changes another transaction can see, depending on the database's isolation level.
- **Transaction boundary:** when a transaction starts, ends, commits/rolls back, and which connection participates.
- **Error boundary:** which exceptions or error signals cause the transaction manager to roll back.
- **Cleanup:** whether committed data is properly cleaned up after the test.

A SQL `INSERT` returning without error **does not mean** it committed. A test reading back data **within the same open transaction** does not prove another transaction sees that data either.

### 2.1. The Three-Layer Picture

```text
                IMPERATIVE JDBC
JUnit thread ─── TransactionTemplate / @Transactional ─── JDBC
                 │ thread-bound TransactionStatus
                 └── DataSource Connection -> SQL -> commit/rollback

                REACTIVE R2DBC
JUnit thread ─── builds Mono/Flux (assembly)
                 │
                 └── StepVerifier.subscribe()
                       │ Reactor subscriber Context
                       └── TransactionalOperator
                             └── ConnectionFactory Connection
                                   -> SQL publishers -> commit/rollback
```

This diagram illustrates the architectural model: Spring provides multiple transaction manager implementations, and exact syntax varies by project and Spring version. Still, the distinction between **thread-bound vs. subscription-context-bound** is the core principle.

### 2.2. Do Not Confuse a Transaction with Any Arbitrary Connection

With JDBC, Spring normally binds the connection to the current thread's transaction. When using `JdbcTemplate` with the **same DataSource** and appropriate transaction manager, SQL statements inside the transactional callback join the same transaction.

However:

- Calling `DriverManager.getConnection(...)` directly may open a separate connection that does not participate in the Spring-managed transaction.
- Running queries on a new thread or executor loses the original `ThreadLocal` transaction.
- `@Transactional(propagation = REQUIRES_NEW)` suspends the outer transaction and starts a new one.
- Using multiple DataSources or multiple managers can produce independent transactions.

With R2DBC, Spring attaches the connection to the **Reactor Context**. Spring-managed `DatabaseClient`/R2DBC operations normally reuse the connection inside the active reactive transaction. Opening a separate connection manually or calling `subscribe()` to spawn a detached subscription can lose the intended transaction scope.

## 3. Comparison Table: JDBC vs. R2DBC in Spring Boot Testing

| Criterion | JDBC | R2DBC |
|---|---|---|
| DB access model | Imperative, usually blocking | Reactive Publisher, asynchronous orchestration |
| Entry point | `DataSource` / `JdbcTemplate` | `ConnectionFactory` / `DatabaseClient` |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Example managers | `JdbcTransactionManager`, `DataSourceTransactionManager` | `R2dbcTransactionManager` |
| Where transaction context lives | `ThreadLocal` of the executing thread | Reactor subscriber `Context` |
| Typical programmatic API | `TransactionTemplate` | `TransactionalOperator` |
| When SQL runs | `jdbcTemplate.update(...)` runs during method call | Publisher SQL normally runs **on subscribe** |
| Write result | Affected row count returned immediately | `Mono<Long>` / result Publisher |
| Boot 3 test slice | `@JdbcTest` | `@DataR2dbcTest` |
| Default slice transaction/rollback | **Yes**, rolls back after test | **No**, must be managed explicitly |
| Test framework rollback support | `TransactionalTestExecutionListener` / `TestTransaction` | Does not auto-start reactive rollback for `void` test methods |
| Asserting completion/error signals | JUnit assertions, `assertThrows` | `StepVerifier` + terminal signals |
| Commit | Callback/method exits cleanly per manager | Transactional publisher completes cleanly |
| Rollback | Runtime exception, rollback-only, or policy | Publisher emits terminal `onError`, rollback-only, or cancel per Spring reactive semantics |
| Post-test verification | Read in a new transaction | Subscribe a fresh query **outside** the checked transaction |

**Do not treat the table as absolute:** transaction propagation, timeouts, rollback rules, reactive stream cancellation, drivers, and isolation levels can all affect outcomes. With `@Transactional`, the active manager and the method's return type determine the imperative vs. reactive path.

## 4. Why Does `@Transactional` Not Mean the Same Thing for Every Call?

### 4.1. JDBC: Thread-Bound Transaction

With Spring transaction AOP enabled, an imperative method can declare:

```java
@Transactional
public void transfer(String from, String to, int amount) {
    jdbcTemplate.update("update accounts set balance = balance - ? where id = ?",
            amount, from);
    jdbcTemplate.update("update accounts set balance = balance + ? where id = ?",
            amount, to);
}
```

**Illustrative snippet**, assuming `JdbcTemplate` and an `accounts` table. When the method is **invoked through the Spring proxy**, Spring starts or joins a transaction. If an exception triggers manager rollback, neither statement commits individually.

Conditions:

- `@Transactional` is metadata requiring Spring transaction infrastructure/proxies.
- **Self-invocation** such as `this.transfer(...)` inside the same class normally bypasses the AOP proxy.
- The transaction binds to the **thread**; offloading work to another thread does not inherit the connection/transaction.
- Default rollback rules roll back on `RuntimeException` and `Error`; checked exceptions need explicit rules/config.
- An outer test-managed transaction can be affected if code uses `REQUIRES_NEW` or `NOT_SUPPORTED`.

### 4.2. R2DBC: Transaction Attached to Publisher/Subscription

A reactive service may write:

```java
@Transactional
public Mono<Void> transfer(String from, String to, int amount) {
    return debit(from, amount)
            .then(credit(to, amount));
}
```

This is an **illustrative snippet**; `debit`/`credit` must return Publishers using compatible R2DBC infrastructure/transactions, and the method must be intercepted by the Spring proxy. With `ReactiveTransactionManager`, Spring opens the transaction when the Publisher is subscribed to via reactive transaction interceptors—not by "opening a transaction on the JUnit thread and letting it follow every step".

If a test merely calls:

```java
Mono<Void> result = service.transfer("A", "B", 10);
assertNotNull(result);
```

that is an **anti-example**: no subscription happens, and no SQL, commit, or rollback is verified. Instead, use `StepVerifier.create(result).verifyComplete()` or assert the corresponding error.

### 4.3. Spring TestContext Test-Managed Transactions Are Not Reactive Contexts

Per Spring Framework, TestContext's `TransactionalTestExecutionListener` requires a `PlatformTransactionManager` to support test-managed transactions. With `@JdbcTest`, the test annotation enables transactional execution; the JUnit method runs inside a listener-created transaction and rolls back afterward.

**Do not infer** that:

```java
@DataR2dbcTest
@Transactional
class ReactiveRepositoryTest {
}
```

will automatically roll back every Publisher after each test. That is an **unreliable anti-pattern**: reactive transactions must wrap the pipeline, whereas JUnit test methods normally return `void` and TestContext listeners do not open reactive transactions with `ReactiveTransactionManager` the way they do with `PlatformTransactionManager`.

To test R2DBC rollback, wrap the Publisher in `TransactionalOperator` or call a proxied reactive `@Transactional` method, then inspect database state outside the transaction after termination.

## 5. When SQL Executes: Method Call vs. Subscribe

### 5.1. Imperative JDBC

```java
int affected = jdbcTemplate.update(
        "insert into ledger_entries(code, amount) values (?, ?)",
        "J-001", 100);
```

Once the method returns cleanly, the JDBC statement has executed on the connection. Yet **the transaction may not have committed**, especially inside `@JdbcTest`. If the test-managed transaction rolls back, the new row is undone.

### 5.2. Lazy R2DBC Publisher

```java
Mono<Long> pending = databaseClient.sql(
        "insert into ledger_entries(code, amount) values (:code, :amount)")
        .bind("code", "R-001")
        .bind("amount", 100)
        .fetch()
        .rowsUpdated();

// Only built a Mono; no subscription from the test yet.
```

This snippet uses Spring R2DBC's `DatabaseClient` and usually only **describes** the SQL work; it gives no proof that `INSERT` ran. Once the test calls:

```java
StepVerifier.create(pending)
        .expectNext(1L)
        .verifyComplete();
```

subscription is triggered and the transaction (if wrapped) gets a chance to run and finish.

**Note:** do not claim every Publisher is cold; some hot sources produce side effects independently of subscription. With Spring's default `DatabaseClient`, SQL execution defers until subscription. For custom repositories or adapters, verify their actual semantics.

### 5.3. Never Call Detached subscribe() Inside a Transaction

Anti-pattern:

```java
Mono<Void> work = saveFirst()
        .doOnNext(value -> saveSecond().subscribe())
        .then();
```

This is an **anti-pattern snippet**, assuming `saveFirst`/`saveSecond` exist with matching types. Calling `subscribe()` inside a side-effect operator spawns a separate subscription; the second operation can execute outside the transaction context, finish after the main pipeline, or fail unobserved by the test.

Replace with **composition**:

```java
Mono<Void> work = saveFirst()
        .then(saveSecond())
        .then();
```

When both Publishers are chained in the same reactive pipeline and properly wrapped in a transaction, the Reactor Context propagates to both operations. Tests must verify termination of the **composed pipeline**, not merely the first publisher.

## 6. Programmatic Transactions: TransactionTemplate vs. TransactionalOperator

### 6.1. JDBC with TransactionTemplate

```java
TransactionTemplate template =
        new TransactionTemplate(platformTransactionManager);

template.executeWithoutResult(status -> {
    jdbcTemplate.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "J-A", 10);
    jdbcTemplate.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "J-B", 20);
});
```

This is a **snippet** in a context that already has the manager/template, not a standalone program. When the callback completes normally, the transaction manager commits per policy; when it throws a runtime exception, the transaction rolls back. Calling `status.setRollbackOnly()` forces rollback even if the callback returns normally.

A `TransactionTemplate` must never be used to "wrap" an async Publisher without awaiting execution; the callback can return and close the transaction **before the Publisher's database operations run**.

### 6.2. R2DBC with TransactionalOperator

```java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Long> work = insertOne()
        .then(insertTwo())
        .thenReturn(2L)
        .as(operator::transactional);

StepVerifier.create(work)
        .expectNext(2L)
        .verifyComplete();
```

**Illustrative snippet**: `insertOne`/`insertTwo` return corresponding R2DBC `Mono`s. `.as(operator::transactional)` wraps the publisher in a reactive transaction, and `StepVerifier` subscribes. When `work` succeeds and completes, the transaction commits.

If an upstream operation emits `onError` unrecovered **inside the transaction**, the operator rolls back. If downstream cancels the transactional publisher, Spring Framework 5.3+ applies **rollback-on-cancel** semantics. Operators like `take(n)`, `next()`, or timeouts can trigger cancellation; keep this in mind when working with multi-element `Flux` streams.

### 6.3. Three Critical Moments When Testing R2DBC

```text
Assembly:
    Mono<?> work = ... .as(transactionalOperator::transactional)
    Not subscribed yet -> transaction has not started for work.

Subscription:
    StepVerifier.create(work).verify(...)
    Spring opens reactive transaction, acquires/holds connection in Reactor Context.

Termination:
    onComplete -> commit (unless rollback-only)
    onError    -> rollback (per policy)
    cancel     -> rollback in Spring reactive tx since Framework 5.3+
```

A fast-completing `Mono.just(...)` proves nothing about DB transactions if `work` contains no SQL Publisher. A `StepVerifier.expectNext(...)` that **forgets `verify`** never runs the test subscription either.

## 7. Complete Java 17+ Example — Standalone JDBC Project

The JDBC sample uses `@JdbcTest`, H2, and `JdbcTemplate`. Tests roll back by default; tests aiming to observe a **real commit** mark the JUnit method with `Propagation.NOT_SUPPORTED` and then use `TransactionTemplate` to open an independent transaction.

**Target stack:** Spring Boot 3.x, Java 17+, JUnit Jupiter, Spring JDBC, and H2. The sample is designed to live in an **independent JDBC project**, without `spring-boot-starter-data-r2dbc`. Package name: `com.example.jdbctx`.

### 7.1. JDBC Dependencies

Gradle Groovy DSL, dependency block in a build file **already configured with Spring Boot plugin/BOM, repositories, and Java 17 toolchain**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven with Spring Boot parent/BOM and an appropriate test runner:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

These are **excerpts**, not complete build files. H2 runtime sits on the test runtime classpath; Boot `@JdbcTest` can use an appropriate embedded DB. No HTTP server, Reactor, R2DBC, or Spring Data JPA is needed.

### 7.2. JDBC Project File Tree

```text
jdbc-tx-project/
└── src/
    ├── main/java/com/example/jdbctx/
    │   └── JdbcTxApplication.java
    └── test/
        ├── java/com/example/jdbctx/
        │   └── JdbcTransactionTest.java
        └── resources/
            └── schema.sql
```

### 7.3. Application File

**`src/main/java/com/example/jdbctx/JdbcTxApplication.java`**

```java
package com.example.jdbctx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcTxApplication.class, args);
    }
}
```

No manual DataSource or transaction manager declaration is needed. The Boot JDBC starter and embedded H2 enable auto-configuring JDBC infrastructure for the slice.

### 7.4. Test SQL Schema

**`src/test/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

The schema is deliberately simple with no triggers, sequences, or identity columns. Each test uses a distinct key. The script is run by Spring Boot's SQL initializer when the test context starts under suitable configuration, **not re-run after every transaction**.

### 7.5. Complete JDBC Test Class

**`src/test/java/com/example/jdbctx/JdbcTransactionTest.java`**

```java
package com.example.jdbctx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@JdbcTest(properties = "spring.sql.init.mode=always")
class JdbcTransactionTest {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PlatformTransactionManager transactionManager;

    private void insert(String code, int amount) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, amount);
    }

    private int count(String code) {
        Integer result = jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class,
                code);
        return result == null ? 0 : result;
    }

    @Test
    void jdbcSliceStartsRollbackOnlyTestTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        insert("J-ROLLBACK-DEFAULT", 10);
        assertThat(count("J-ROLLBACK-DEFAULT")).isEqualTo(1);

        // Row is readable within the test transaction;
        // @JdbcTest rolls it back when the test method ends.
    }

    @Test
    void explicitEndShowsRollbackAndNewTestTransaction() {
        insert("J-ROLLBACK-END", 20);
        assertThat(count("J-ROLLBACK-END")).isEqualTo(1);
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        TestTransaction.end();
        assertThat(TestTransaction.isActive()).isFalse();

        TestTransaction.start();
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count("J-ROLLBACK-END")).isZero();
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void transactionTemplateCommitsWhenCallbackReturns() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        try {
            template.executeWithoutResult(status ->
                    insert("J-COMMIT", 30));

            // Callback completed: transactionTemplate has committed.
            assertThat(count("J-COMMIT")).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    "J-COMMIT");
        }
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void transactionTemplateRollsBackOnRuntimeException() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        assertThatThrownBy(() ->
                template.executeWithoutResult(status -> {
                    insert("J-ERROR", 40);
                    throw new IllegalStateException("reject");
                }))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("reject");

        assertThat(count("J-ERROR")).isZero();
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void rollbackOnlyWorksEvenWithoutAnException() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.executeWithoutResult(status -> {
            insert("J-ONLY", 50);
            status.setRollbackOnly();
        });

        assertThat(count("J-ONLY")).isZero();
    }
}
```

**Expected outcome:** **5 JUnit Jupiter test methods pass** in a Spring Boot 3.x/H2 project built from the files above. No intentional stdout is produced by the sample. The H2 schema is created on test context startup; Spring/Gradle/Maven may emit their own logs.

**Note:** the `TransactionStatus` import in the snippet is not strictly required in the current code and could be omitted since the callback infers the type; it does not prevent Java compilation. `@Transactional(NOT_SUPPORTED)` on the final three tests is intentional: they **do not receive an enclosing test-managed transaction**, allowing `TransactionTemplate` to commit/roll back per callback and be observed by the post-callback `SELECT`. Without `NOT_SUPPORTED`, the template would by default **join the existing test transaction**, and the post-callback `SELECT` would still read data inside that outer transaction rather than proving an independent commit.

### 7.6. Breakdown of Each JDBC Test

| Test | Practical Meaning |
|---|---|
| `jdbcSliceStartsRollbackOnlyTestTransaction` | `@JdbcTest` creates a test transaction, sees INSERT immediately inside it, and rolls back on method completion |
| `explicitEndShowsRollbackAndNewTestTransaction` | `TestTransaction.end()` triggers rollback, and `start()` opens a new transaction proving the row vanished |
| `transactionTemplateCommitsWhenCallbackReturns` | No outer test tx; callback returns normally, transaction commits, test cleans up row in `finally` |
| `transactionTemplateRollsBackOnRuntimeException` | Callback throws a runtime error, rolls back, and propagates the exception to the test |
| `rollbackOnlyWorksEvenWithoutAnException` | `status.setRollbackOnly()` forces rollback even though the callback did not throw |

The last two tests leave no leftover fixtures because their transactions rolled back. The commit test has explicit cleanup. If running parallel suites against a shared DB, create isolated schemas/databases or unique keys with reliable cleanup; this sample uses an embedded DB in a dedicated test project.

## 8. Complete Java 17+ Example — Standalone R2DBC Project

This section is **symmetrical in domain logic, yet distinct in transaction boundaries**. The R2DBC sample uses `@DataR2dbcTest`, `DatabaseClient`, the H2 R2DBC driver, `ReactiveTransactionManager`, and `TransactionalOperator`. **Do not** add `@Transactional` to the JUnit test class expecting "auto-rollback"; every tested transaction wraps its Publisher explicitly.

**Target stack:** Spring Boot 3.x, Java 17+, JUnit Jupiter, Project Reactor, Spring R2DBC, and the H2 R2DBC driver. Package name: `com.example.r2dbctx`. Both projects share the same table name while using **separate in-memory databases**, and are not intended to test distributed JDBC + R2DBC transactions on a single database.

### 8.1. R2DBC Dependencies

Gradle Groovy DSL — inside a project with the Spring Boot plugin/BOM, repositories, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — dependency section of a project with Boot parent/BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

R2DBC has its own driver/protocol; **never use `jdbc:h2:...` as an R2DBC URL**. Example H2 R2DBC in-memory URLs use the form `r2dbc:h2:mem:///...`. Depending on the driver release, H2 options are passed via query parameters; the example uses syntax from the official `r2dbc-h2` documentation.

### 8.2. R2DBC File Tree

```text
r2dbc-tx-project/
└── src/
    ├── main/java/com/example/r2dbctx/
    │   └── ReactiveTxApplication.java
    └── test/
        ├── java/com/example/r2dbctx/
        │   └── ReactiveTransactionTest.java
        └── resources/
            └── schema.sql
```

### 8.3. Application Class

**`src/main/java/com/example/r2dbctx/ReactiveTxApplication.java`**

```java
package com.example.r2dbctx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

There is no JDBC starter or JPA starter in this project. Spring Boot can auto-configure `ConnectionFactory`, `DatabaseClient`, and the R2DBC transaction manager when classpath and conditions match.

### 8.4. Dedicated R2DBC Schema

**`src/test/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

With embedded H2 and Boot SQL initialization, the script runs via the R2DBC `ConnectionFactory`. The sample sets `spring.sql.init.mode=always` to make intent explicit, and the URL keeps the in-memory DB alive when connections close during tests.

### 8.5. Complete R2DBC Test Class

**`src/test/java/com/example/r2dbctx/ReactiveTransactionTest.java`**

```java
package com.example.r2dbctx;

import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@DataR2dbcTest(properties = {
        "spring.r2dbc.url=r2dbc:h2:mem:///reactive_tx_demo"
                + "?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.sql.init.mode=always"
})
class ReactiveTransactionTest {

    @Autowired
    DatabaseClient client;

    @Autowired
    ReactiveTransactionManager transactionManager;

    private TransactionalOperator tx() {
        return TransactionalOperator.create(transactionManager);
    }

    private Mono<Long> insert(String code, int amount) {
        return client.sql(
                "insert into ledger_entries(code, amount) "
                + "values (:code, :amount)")
                .bind("code", code)
                .bind("amount", amount)
                .fetch()
                .rowsUpdated();
    }

    private Mono<Long> count(String code) {
        return client.sql(
                "select count(*) from ledger_entries where code = :code")
                .bind("code", code)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    private Mono<Long> delete(String code) {
        return client.sql(
                "delete from ledger_entries where code = :code")
                .bind("code", code)
                .fetch()
                .rowsUpdated();
    }

    @Test
    void buildingPublisherDoesNotExecuteSqlWithoutSubscribe() {
        Mono<Long> prepared = insert("R-NOT-SUBSCRIBED", 10);

        assertThat(prepared).isNotNull();

        StepVerifier.create(count("R-NOT-SUBSCRIBED"))
                .expectNext(0L)
                .verifyComplete();

        // Did not subscribe to prepared -> INSERT has not run.
    }

    @Test
    void transactionCommitsOnSuccessfulCompletion() {
        Mono<Long> operation = insert("R-COMMIT", 20)
                .then(count("R-COMMIT"))
                .as(tx()::transactional);

        try {
            StepVerifier.create(operation)
                    .expectNext(1L)
                    .verifyComplete();

            // A NEW subscription, outside the completed transaction.
            StepVerifier.create(count("R-COMMIT"))
                    .expectNext(1L)
                    .verifyComplete();
        }
        finally {
            StepVerifier.create(delete("R-COMMIT"))
                    .expectNextCount(1)
                    .verifyComplete();
        }
    }

    @Test
    void transactionRollsBackOnTerminalError() {
        Mono<Void> operation = insert("R-ROLLBACK", 30)
                .then(Mono.<Void>error(
                        new IllegalStateException("reject")))
                .as(tx()::transactional);

        StepVerifier.create(operation)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "reject".equals(error.getMessage()))
                .verify();

        StepVerifier.create(count("R-ROLLBACK"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void writesAreVisibleInsideTransactionButRolledBack() {
        AtomicLong seenInside = new AtomicLong(-1L);

        Mono<Void> operation = insert("R-INSIDE", 40)
                .then(count("R-INSIDE"))
                .doOnNext(seenInside::set)
                .then(Mono.<Void>error(
                        new IllegalArgumentException("rollback me")))
                .as(tx()::transactional);

        StepVerifier.create(operation)
                .expectErrorMessage("rollback me")
                .verify();

        assertThat(seenInside.get()).isEqualTo(1L);

        StepVerifier.create(count("R-INSIDE"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void recoveringErrorInsideTransactionCanCommit() {
        Mono<Void> operation = insert("R-RECOVER-IN", 50)
                .then(Mono.<Void>error(
                        new IllegalStateException("upstream failed")))
                .onErrorResume(error -> Mono.empty())
                .as(tx()::transactional);

        try {
            StepVerifier.create(operation)
                    .verifyComplete();

            StepVerifier.create(count("R-RECOVER-IN"))
                    .expectNext(1L)
                    .verifyComplete();
        }
        finally {
            StepVerifier.create(delete("R-RECOVER-IN"))
                    .expectNextCount(1)
                    .verifyComplete();
        }
    }

    @Test
    void recoveringErrorOutsideTransactionKeepsRollback() {
        Mono<Void> operation = insert("R-RECOVER-OUT", 60)
                .then(Mono.<Void>error(
                        new IllegalStateException("upstream failed")))
                .as(tx()::transactional)
                .onErrorResume(error -> Mono.empty());

        StepVerifier.create(operation)
                .verifyComplete();

        StepVerifier.create(count("R-RECOVER-OUT"))
                .expectNext(0L)
                .verifyComplete();
    }
}
```

**Expected outcome:** **6 JUnit Jupiter tests pass** with compatible Spring Boot 3.x / Reactive H2 driver / JUnit 5. Code emits no explicit stdout; summaries are formatted by the test runner.

Why does the second test use `try/finally`? `@DataR2dbcTest` does not auto-rollback each test. A publisher completing cleanly inside `TransactionalOperator` commits; therefore **the test itself must delete the committed fixture**. In the two tests where errors pass through the operator, the transaction rolls back so no row remains. Distinct `code` names reduce collisions within the same context.

### 8.6. Why `.then(...)` and `.as(tx::transactional)` Matter

In the test:

```java
Mono<Long> operation = insert("R-COMMIT", 20)
        .then(count("R-COMMIT"))
        .as(tx()::transactional);
```

- `insert(...)` returns a `Mono` for the SQL INSERT.
- `then(count(...))` subscribes to `count` only after `insert` completes cleanly; `count` executes in the **same pipeline**.
- `as(tx()::transactional)` wraps the **entire pipeline** in the transaction scope.
- `StepVerifier.create(operation).verifyComplete()` (or with value assertions) triggers subscription and awaits termination.
- After terminal completion of the transactional Publisher, the operator has executed its commit path per manager semantics; querying outside the operator measures committed data.

If you wrapped only `insert` with the operator and called `count` afterward, `count` would run outside the transaction. That may be intentional, yet it differs from testing "reads within the same transaction".

### 8.7. Why Where You Place `onErrorResume` Matters

The final two tests form a contrast pair:

**Recovery placed inside the transaction scope**:

```java
insert("A", 1)
        .then(Mono.error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

If the outer operator observes only a clean `onComplete`, it **can commit** changes even though an upstream stage errored and recovered into empty completion.

**Recovery placed outside the transaction scope**:

```java
insert("B", 1)
        .then(Mono.error(new IllegalStateException("failed")))
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> Mono.empty());
```

Now the transactional operator sees `onError` first and rolls back, and only then does the outer consumer convert the error to completion. The test finishes green, yet row B was never committed.

This is a subtle hazard in reactive business services: **a test asserting only `verifyComplete()` does not prove a commit happened**. You must query after completion and understand **error/recovery boundaries**.

## 9. Running Both Test Suites

Run each project/module in its own directory; they do not share an application context, database, dependencies, or transaction manager.

### 9.1. JDBC Project

Linux/macOS:

```bash
./gradlew test --tests "com.example.jdbctx.JdbcTransactionTest"

# Or if using Maven Wrapper:
./mvnw -Dtest=JdbcTransactionTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jdbctx.JdbcTransactionTest"

# Or Maven:
.\mvnw.cmd "-Dtest=JdbcTransactionTest" test
```

### 9.2. R2DBC Project

Linux/macOS:

```bash
./gradlew test --tests "com.example.r2dbctx.ReactiveTransactionTest"

# Or if using Maven Wrapper:
./mvnw -Dtest=ReactiveTransactionTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.r2dbctx.ReactiveTransactionTest"

# Or Maven:
.\mvnw.cmd "-Dtest=ReactiveTransactionTest" test
```

Do not run both Gradle and Maven if a project uses only one build system. For multi-module builds, invoke the proper module task. If your IDE fails to detect JUnit Jupiter, check test runtime dependencies, `useJUnitPlatform()`, or Surefire compatibility. Across both projects there are **11 tests total (5 JDBC + 6 R2DBC)**, not 11 test methods inside a single class.

### 9.3. Contract Expectations

| Case | JDBC | R2DBC |
|---|---|---|
| Default test slice behavior | Transactional + rollback | Not transactional automatically |
| Executing INSERT | `jdbc.update(...)` runs on call | `DatabaseClient...rowsUpdated()` executes on subscribe |
| Success in programmatic transaction | `TransactionTemplate` commits | `TransactionalOperator` commits |
| Unrecovered exception/error | Runtime exception -> rollback | `onError` -> rollback |
| Marking rollback explicitly | `TransactionStatus.setRollbackOnly()` | `ReactiveTransaction` supports `setRollbackOnly()` via operator callback |
| Post-commit visibility | New JDBC query sees row | New R2DBC Publisher query sees row |
| Test data cleanup | Test rollback or post-commit cleanup | Explicit cleanup; do not rely on slice rollback |
| Testing errors synchronously vs. asynchronously | Throw exception directly in callback | `StepVerifier` must subscribe and verify terminal signal |

## 10. `@JdbcTest`, `@DataJdbcTest`, `@DataJpaTest`, and `@DataR2dbcTest` Are Not Equivalent

Spring Boot supplies distinct test slices across data-access technologies. Similar annotation names do not imply identical transaction behavior.

### 10.1. `@JdbcTest`

- Focuses on `DataSource` and `JdbcTemplate`.
- Typically uses an available embedded database.
- **Transactional, rolls back by default**.
- Does not focus on Spring Data JDBC repository mapping.
- Useful for testing manual SQL, `RowMapper` mapping, batch updates, and JDBC transaction semantics.

### 10.2. `@DataJdbcTest`

- Focuses on Spring Data JDBC repositories and aggregate mapping.
- Has test-managed transactions and default rollback in Spring Boot 3.x.
- May require custom repository converters or aggregate configuration.
- Do not confuse Spring Data JDBC with JPA: Spring Data JDBC **has no Hibernate-style persistence context/dirty checking**, and `save` semantics differ.

### 10.3. `@DataJpaTest`

- Focuses on JPA entities/repositories and the Hibernate/JPA persistence context.
- Transactional, rolls back by default.
- JPA `flush` and the first-level cache form an extra layer outside the SQL transaction.
- `repository.save(...)` can defer SQL; `flush`/`clear`/JDBC checks are often needed when verifying persisted state.

Do not port a JDBC example straight to JPA expecting SQL statements to execute at the exact same moment as `JdbcTemplate.update(...)`.

### 10.4. `@DataR2dbcTest`

- Focuses on Spring Data R2DBC repositories, `R2dbcEntityTemplate`, `DatabaseClient`, and reactive infrastructure.
- Per Spring Boot 3.5 docs, configures an embedded DB by default if an appropriate driver is present, yet **does not wrap each test in a transaction by default**.
- Testing reactive transactions requires `ReactiveTransactionManager` and a transactional Publisher via `TransactionalOperator` or proxied reactive `@Transactional`.
- Once a Publisher commits, clean up via a separate reactive Publisher, isolated schema, or container reset.

**Key takeaway:** carrying the "every test auto-rolls back" habit from JDBC/JPA slices into R2DBC can leave leftover rows, create test-order coupling, and cause hard-to-reproduce CI failures.

## 11. `@Transactional` on Reactive Services: Watch Return Types and Proxies

### 11.1. Method Return Type Must Fit Reactive Transactions

Spring supports `@Transactional` on reactive return types when the matching transaction manager is active. A method like this can use reactive transaction AOP:

```java
@Service
public class ReactiveLedgerService {

    private final DatabaseClient client;

    public ReactiveLedgerService(DatabaseClient client) {
        this.client = client;
    }

    @Transactional
    public Mono<Void> recordPair() {
        return client.sql("insert into ledger_entries(code, amount) "
                + "values ('A', 10)")
                .fetch().rowsUpdated()
                .then(client.sql("insert into ledger_entries(code, amount) "
                        + "values ('B', 20)")
                        .fetch().rowsUpdated())
                .then();
    }
}
```

**Illustrative snippet**, not a standalone runnable file in either sample project. It needs Spring `Service`, `Transactional`, Reactor `Mono`, and `DatabaseClient` imports, an appropriate transaction manager, and fixtures avoiding duplicate primary keys. It demonstrates the principle: **return a Publisher composing all operations** so Spring's reactive interceptor can wrap it.

If a method returns `void`, `String`, or an imperative type, it does not have a reactive return shape. With a `ReactiveTransactionManager`, Spring transaction management expects a reactive pipeline; it does not automatically turn imperative methods into valid R2DBC transactions.

### 11.2. Self-Invocation and Objects Instantiated with `new`

If a test runs:

```java
ReactiveLedgerService service =
        new ReactiveLedgerService(databaseClient);

Mono<Void> result = service.recordPair();
```

you constructed an object **bypassing the Spring proxy**. `@Transactional` on the method will not be applied by Spring AOP for objects created with `new`.

Similarly, `this.recordPair()` from another method in the same class normally bypasses the proxy in Spring's default proxy mode. When writing unit tests without starting a Spring context, **use `TransactionalOperator` explicitly** or test business pipeline logic against a fake repository, backed by a separate integration test for annotation/proxy wiring.

### 11.3. Using Multiple Transaction Managers

An application having both a JDBC/JPA manager and an R2DBC manager must specify which transaction manager governs each operation. You might have:

- `PlatformTransactionManager` for `DataSource`/JPA;
- `ReactiveTransactionManager` for `ConnectionFactory`.

These are **two distinct SPIs** typically using two separate connections. Never expect an ambiguous `@Transactional` to commit atomically across both JDBC and R2DBC. Define explicit boundaries/manager selection and verify commit/rollback ordering whenever a system spans multiple resource managers.

## 12. TestThread, Reactor Context, and Thread-Switching Traps

### 12.1. JDBC Transaction ThreadLocal

When `@JdbcTest` starts a test transaction, Spring binds transaction metadata to the test-executing thread. If inside a test you run:

```java
CompletableFuture.runAsync(() ->
        jdbcTemplate.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                "ASYNC-J", 1));
```

this is an **anti-pattern snippet**, assuming `CompletableFuture` is imported. Launching an async task without joining lets the JUnit test exit before the SQL runs; even if joined, the task executes on another thread and does not inherit the test's `ThreadLocal` transaction. It can acquire a fresh autocommit connection and leave rows behind despite test rollback.

A similar trap is JUnit's `assertTimeoutPreemptively(...)`: preemptive timeouts can run the lambda on a different thread from the one to which TestContext bound the transaction. Spring docs explicitly warn that side effects may **fail to roll back** with the test-managed transaction.

To test timeouts while preserving transaction semantics, prefer non-preemptive timeouts or manage transactions explicitly inside the worker thread via `TransactionTemplate` with reliable cleanup.

### 12.2. R2DBC Transactions Rely on Context, Not a Fixed Thread

Reactor propagates Context along the pipeline. An operator like `publishOn(...)` can switch worker threads, yet when the pipeline and Context are wired properly, transaction scope does not depend strictly on staying on a single thread name.

What actually breaks transactions is not "switching threads", but rather:

- calling `subscribe()` manually inside the pipeline, creating a **detached subscription**;
- calling `block()` where event loops forbid blocking or accidentally breaking pipeline boundaries;
- invoking blocking JDBC inside a reactive pipeline while expecting JDBC to join the R2DBC reactive transaction;
- opening raw R2DBC connections manually instead of using Spring-managed connections;
- losing Reactor Context when integrating Publisher libraries that break context propagation.

### 12.3. Never Put `JdbcTemplate` Inside `TransactionalOperator` Expecting One Transaction

Anti-pattern:

```java
Mono<Void> operation = Mono.fromRunnable(() ->
        jdbcTemplate.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                "MIXED", 10))
        .as(reactiveOperator::transactional)
        .then();
```

This is an **anti-pattern snippet**, assuming `jdbcTemplate` and `reactiveOperator`; it has no atomic transaction guarantee with R2DBC. `JdbcTemplate` uses `DataSource`/a thread-bound manager; `TransactionalOperator` uses the reactive manager/`ConnectionFactory`. Wrapping JDBC in a `Mono` does not turn a JDBC connection into a reactive connection.

If both JDBC and R2DBC must access the same database:

1. Assign each piece of logic to one primary transaction manager.
2. Never assume two managers merge or share a connection.
3. Separate transactions and use saga/outbox/idempotency patterns across multiple resource managers.
4. Test commit/rollback at **each boundary** and verify partial-failure handling.
5. For true atomic distributed commits, use a dedicated distributed transaction architecture/protocol and verify real support; **never assume shared XA** across R2DBC + JDBC.

## 13. Reactive Cancellation: `onComplete`, `onError`, and `cancel` Are Not the Same

In Reactive Streams, a subscription can terminate via:

- `onComplete` — normal publisher completion;
- `onError` — terminal error;
- `cancel()` from the subscriber — cancels the subscription without necessarily awaiting a terminal signal;
- timeouts or operators like `take`/`next`, which can emit `cancel` under specific conditions.

Per Spring Framework's programmatic transaction documentation, **cancelling a transactional reactive Publisher triggers rollback** starting in Spring Framework 5.3. Therefore, if code streams rows through a `Flux` and the client only takes the first item, test **how the transaction may roll back on cancellation before the rest of the pipeline finishes**.

### 13.1. Anti-Pattern: Using `take(1)` to Judge Commit

```java
Flux<Event> stream = saveAndStreamEvents()
        .as(transactionalOperator::transactional);

StepVerifier.create(stream.take(1))
        .expectNextCount(1)
        .verifyComplete();
```

**Illustrative snippet**, not a standalone runnable test. Downstream `take(1)` cancels the upstream transactional `Flux` after the first element. Even though the outer subscriber sees completion, the inner transactional operator can receive cancellation and roll back. Thus, `verifyComplete()` on `take(1)` does not prove earlier SQL committed.

### 13.2. When You Need to Test Cancellation

Design tests with an **explicit signal confirming SQL executed inside the transaction before cancellation**. For example, use a controlled upstream with `PublisherProbe`, a latch/signal with timeout, or a `TestPublisher`. After cancellation, run a **separate subscription outside the transactional operator** to query the database and verify the row rolled back.

Do not write tests like:

```java
StepVerifier.create(insert("R-CANCEL", 1)
        .then(Mono.never())
        .as(transactionalOperator::transactional))
        .thenCancel()
        .verify();
```

and claim "rollback is proven", because cancellation can fire **before the real INSERT ever runs**. A valid cancellation test proves progress occurred prior to cancel, preferably using explicit schedulers/demand/callbacks rather than `Thread.sleep(50)`.

## 14. Test Database Isolation and Test Data Lifecycle

### 14.1. What `@JdbcTest` Rollback Helps With — and What It Does Not

Inside a JDBC test-managed transaction:

- `INSERT`/`UPDATE`/`DELETE` on the same transactional `DataSource` normally rolls back after the test.
- A `REQUIRES_NEW` transaction can commit independently.
- An async task/thread outside the test transaction can commit independently.
- External systems such as queues, files, and remote HTTP endpoints do not roll back.
- DDL may auto-commit or follow database-specific semantics.
- Preemptive timeouts can detach execution from the thread-bound transaction.

Thus, default rollback is very helpful, yet it is not a universal cleanup guarantee for **every side effect**.

### 14.2. `@DataR2dbcTest` Needs Explicit Cleanup

Reactive tests must verify:

- Was the Publisher subscribed to and verified?
- Does `TransactionalOperator` wrap the full write pipeline?
- Was termination complete, error, or cancel?
- Did SQL commit or roll back?
- Is committed data left over from an earlier test in the same H2 context?
- Was cleanup itself actually subscribed to and awaited to completion?

A cleanup call like:

```java
client.sql("delete from ledger_entries where code = :code")
        .bind("code", "R-COMMIT")
        .fetch()
        .rowsUpdated();
```

only **builds a Publisher** — it does not delete anything yet. Use:

```java
StepVerifier.create(
        client.sql("delete from ledger_entries where code = :code")
                .bind("code", "R-COMMIT")
                .fetch()
                .rowsUpdated())
        .expectNextCount(1)
        .verifyComplete();
```

If cleanup could error, let the test fail loudly when cleanup fails to run. For large integration suites, give each test group its own schema/database/container or controlled seed/reset rather than relying on execution order.

### 14.3. H2 Does Not Represent Every Behavior of PostgreSQL/MySQL

H2 enables fast reproducibility and verifies core transaction boundaries. Differences that still require testing on the real engine include:

- isolation levels and read phenomena;
- lock waits/deadlocks, snapshot semantics, MVCC;
- SQL dialects and data types;
- generated keys/identities/sequences;
- constraint timing and duplicate-key errors;
- DDL transaction semantics;
- pool, driver, and network timeout behaviors.

When confidence on PostgreSQL is required, run PostgreSQL Testcontainers with **both separate drivers** (JDBC for JDBC tests, R2DBC Postgres for R2DBC tests). Sharing the same database server **does not** put JDBC and R2DBC into a single transaction.

### 14.4. Testcontainers and Migrations

When adding Flyway/Liquibase to tests:

- Do not assume JDBC migrations automatically apply to an R2DBC `ConnectionFactory` without configuring a matching `DataSource`/migration setup.
- Illustrative `schema.sql` suffices for a lesson; in real projects, let schema migrations create tables before tests run.
- Avoid running both Flyway/Liquibase and `schema.sql` against the same tables unintentionally.
- Ensure migrations finish **before** test queries rather than expecting `StepVerifier` to create schemas.
- Never run destructive schema setups against a production database.

## 15. Isolation and Visibility: Seeing a Row Does Not Mean It Committed

With JDBC:

```text
TX-JDBC:
  INSERT code='X'
  SELECT code='X' -> sees X within the same transaction
  ROLLBACK
OUTSIDE TRANSACTION:
  SELECT code='X' -> X is gone
```

With R2DBC:

```text
Subscriber -> TransactionalOperator:
  INSERT code='Y'
  SELECT code='Y' in same Reactor Context -> sees Y
  onError -> ROLLBACK
New subscriber / new operation:
  SELECT code='Y' -> Y is gone
```

The fourth test case in the R2DBC suite proves this cleanly: `AtomicLong seenInside` captures `1` inside the transaction before the pipeline errors; after rollback, a fresh query sees `0`.

If transaction B reads while transaction A **has not committed**, B may see old rows or block depending on isolation and engine. **Never infer a transaction flushed or committed simply from a query on the same connection.**

### 15.1. Rollback Tests Must Observe Outside the Boundary

In JDBC tests, `TestTransaction.end()` lets you inspect immediately after rollback. In R2DBC tests, `StepVerifier` must wait for the transactional Publisher to terminate, and **only then run** a query in a subscription outside the operator to read the state.

A test that merely asserts an exception class and exits does not prove rollback left the database clean. Pair two assertions: **terminal error** and **post-transaction database count**.

### 15.2. Commit Tests Must Clean Up Data

To prove a commit, observe data after the transaction completes and then clean up. Both sample projects have a commit test that deletes its fixture in `finally`. Never invoke `@DirtiesContext` thinking it clears committed database rows: that annotation manages the Spring TestContext cache, not database row cleanup.

## 16. Error Recovery and Rollback Rules: Three Distinct Failure Cases

### 16.1. JDBC Exception Inside Callback

```java
template.executeWithoutResult(status -> {
    jdbc.update("insert into ledger_entries(code, amount) values (?, ?)",
            "J-FAIL", 1);
    throw new IllegalStateException("failed");
});
```

`TransactionTemplate` catches the runtime exception and rolls back. In tests, `assertThatThrownBy(...)` verifies the error, and a post-callback JDBC query proves no row remains.

### 16.2. R2DBC Terminal Error

```java
Mono<Void> work = insert("R-FAIL", 1)
        .then(Mono.<Void>error(new IllegalStateException("failed")))
        .as(transactionalOperator::transactional);
```

Upon subscription, the operator rolls back on `onError`. Tests assert `expectErrorMatches(...)` followed by a post-transaction query.

### 16.3. R2DBC Error Recovered Before the Transaction Boundary

```java
Mono<Void> work = insert("R-RECOVER", 1)
        .then(Mono.<Void>error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

The operator sees normal completion and can commit. This behaves very differently from placing recovery **outside** the operator. Test names, code reviews, and application transaction boundaries must make clear **whether rollback is an intentional business policy or an accidental artifact of operator ordering**.

### 16.4. Checked Exceptions and Business Errors

For declarative JDBC `@Transactional`, default rollback rules treat checked exceptions differently from runtime exceptions (configurable depending on Spring Framework version). Spring Framework 6.2+ also supports global default rollback rule configuration; do not generalize that checked exceptions always commit in every app.

Reactive Publishers signal failures via `onError(Throwable)`; Spring's reactive transaction operator normally rolls back on any `onError`. When business rules demand partial commits or `setRollbackOnly()`, write explicit tests for that exact policy rather than guessing from whether a Java exception is checked or unchecked.

## 17. Common Errors and How to Fix Them

| Symptom | Likely Cause | Fix |
|---|---|---|
| JDBC test inserts, then row vanishes after test | `@JdbcTest` rolls back by default | Expected behavior; use `TestTransaction` to inspect |
| R2DBC test inserts, and next test still sees row | `@DataR2dbcTest` is non-transactional by default | Wrap transactions properly and clean up committed rows |
| R2DBC SQL "doesn't run" | Built Publisher without subscribing/verifying | `StepVerifier` terminal `verify...` |
| R2DBC test green just from `assertNotNull(mono)` | Verified assembly only, never ran DB | `StepVerifier` asserting values/errors/completion |
| R2DBC rollback test still leaves a row | Error recovered **before** operator, or write ran on separate subscription | Fix boundary placement; query DB after terminal signal |
| JDBC `TransactionTemplate` commit test cannot see commit outside tx | Template joined outer test-managed transaction | Use `NOT_SUPPORTED` on test or create an explicit boundary |
| JDBC test rolls back, yet async task commits | Another thread lacks `TransactionSynchronizationManager` | Avoid detached async work; use separate tx and cleanup |
| `@Transactional` on R2DBC test fails to roll back | Listener does not open reactive tx with `ReactiveTransactionManager` | Use `TransactionalOperator` or proxied reactive service |
| R2DBC `@Transactional` on `new`-created class is ignored | Bypassed Spring AOP proxy | Test via Spring bean or programmatic operator |
| `selfInvocation()` lacks transaction | Proxy bypassed | Refactor via proxied public bean/method or programmatic API |
| JDBC and R2DBC share DB yet are not atomic | Two distinct managers/connections | Separate transactions / saga / outbox; never assume auto-join |
| JDBC inside reactive pipeline blocks event loop | Blocking `JdbcTemplate` | Use R2DBC on reactive DB path or controlled offload; do not expect shared tx |
| R2DBC query reads 1 inside tx, 0 outside | Rolled back or different isolation | Check terminal/error signals, boundaries, and DB engine |
| `StepVerifier` passes, yet DB is dirty | Asserted values/terminal only, forgot cleanup | Post-transaction query + explicit delete/schema reset |
| `VirtualTime` hangs DB tests | Virtual scheduler does not speed up R2DBC driver/network | Use real bounded timeouts; avoid mocking DB I/O time |
| R2DBC test cancels and fails to commit | Spring rollback-on-cancel | Inspect downstream `take`/`next`/timeout and rollback |
| H2 test passes, PostgreSQL fails | Different driver/dialect/isolation/locking | Integration tests on production DB engine |
| Schema table not found | SQL initializer skipped or wrong DB/schema URL | Verify `schema.sql` path, mode, URL, and init order |
| "No qualifying bean ReactiveTransactionManager" | Missing R2DBC tx auto-config or multi-manager ambiguity | Check starter, `ConnectionFactory`, and tx manager beans |
| Both JDBC and R2DBC auto-configs unexpectedly missing | Mixing both stacks in one Boot module alters auto-config | Split modules or configure managers/`DataSource`/`ConnectionFactory` explicitly |
| SQL duplicate key passes alone, fails in suite | R2DBC left committed data or shared schema | Cleanup, isolated DB/schema, unique fixtures |

### 17.1. Ordered Debugging Checklist

1. **Check the test annotation:** `@JdbcTest` or `@DataR2dbcTest`?
2. **Check the manager bean:** `PlatformTransactionManager` or `ReactiveTransactionManager`?
3. **Locate the transaction boundary:** test listener, proxy method, or operator?
4. **For R2DBC:** is there a real subscription and terminal verification?
5. **Inspect the composed pipeline:** any detached `subscribe()`, `flatMap`, or dropped `then`?
6. **Inspect signals:** `onComplete`, `onError`, or `cancel`?
7. **Inspect error recovery placement:** inside or outside the operator?
8. **Check the resource used:** `JdbcTemplate`/`DataSource` vs. `DatabaseClient`/`ConnectionFactory`?
9. **Check the DB post-boundary:** query in a new transaction/subscription.
10. **Check cleanup and isolation:** leftover rows, shared schemas, parallel workers.
11. **If only production fails:** DB engine, driver, pool, locks, isolation, network timeouts.
12. **Check the test runner:** did JUnit methods really run rather than being skipped or falsely cached?

## 18. Notes on Timeouts, Concurrency, and Sensitive Data

### 18.1. Timeouts in JDBC Tests

JUnit's `assertTimeoutPreemptively` can run the body on another thread, detaching it from the `ThreadLocal` test-managed transaction for SQL inside. Spring TestContext docs warn explicitly about this case. When asserting duration while relying on TestContext rollback, prefer **non-preemptive** timeout assertions or manage a separate transaction with deterministic cleanup inside the worker thread.

### 18.2. Timeouts in Reactor Tests

`StepVerifier.verify(Duration)` bounds how long verification waits. It **cannot undo an already-committed SQL transaction** if another Publisher subscribed and committed outside the operator.

Example:

```java
StepVerifier.create(transactionalWork)
        .expectNext(1L)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

This is an illustrative snippet requiring `Duration` import. Against a real R2DBC DB, base timeouts on realistic latency/CI budgets; overly tight timeouts cause flaky tests. Timeouts can trigger cancellation/rollback if the subscription is cancelled; verify exact semantics rather than guessing from a JUnit timeout failure.

### 18.3. Parallel Tests and Databases

- Never reuse the same fixed primary key across parallel tests sharing a database.
- In-memory H2 works well for learning, yet multiple contexts sharing a named memory URL can share the same DB.
- For committed data, clean up in `finally` or subscribed fixture teardowns.
- Tests performing transactions/cleanup must not run in parallel against a shared table without row partitioning or isolation.
- Never place customer data, secrets, or production DSNs in tests.
- When debugging, logging bind parameters can expose data; use synthetic fixtures and proper masking.

## 19. Practice Exercises

### Exercise A — Disappearing Data in a JDBC Test

A test uses `@JdbcTest`, calls `jdbcTemplate.update(...)`, and reads `COUNT` as `1` in the same method. Afterward, the row is missing from the DB. Is Spring broken?

**Answer:** No. `@JdbcTest` creates a test-managed transaction that rolls back by default. Querying inside the same transaction sees uncommitted writes; end-of-test rollback reverts the row.

### Exercise B — R2DBC Test Writes Nothing

Code:

```java
Mono<Long> inserted = client.sql(
        "insert into ledger_entries(code, amount) values ('A', 10)")
        .fetch().rowsUpdated();
```

No row appears in the DB. Why?

**Answer:** No subscription happened. Publishers from `DatabaseClient` normally only describe work. Call `StepVerifier.create(inserted).expectNext(1L).verifyComplete()` or compose it into a subscribed reactive service.

### Exercise C — R2DBC Tests Differ from JDBC Default Rollback

If you migrate from `@JdbcTest` to `@DataR2dbcTest` while still assuming automatic end-of-test rollback, what can go wrong?

**Answer:** `@DataR2dbcTest` does not start a test-managed transaction by default. Reactive writes can commit and break subsequent tests. Use `TransactionalOperator`/proxied reactive `@Transactional` and explicit cleanup.

### Exercise D — Where Was the Error Recovered?

Compare:

```java
Mono<Void> a = insertA()
        .then(Mono.error(new IllegalStateException()))
        .onErrorResume(e -> Mono.empty())
        .as(op::transactional);

Mono<Void> b = insertB()
        .then(Mono.error(new IllegalStateException()))
        .as(op::transactional)
        .onErrorResume(e -> Mono.empty());
```

When subscribed, both complete cleanly from the test's perspective. Which one can commit?

**Answer:** `a` can commit because the operator receives completion after recovery. `b` rolls back inside the operator because the operator receives the error before outer recovery. Always verify with a post-terminal DB query.

### Exercise E — JDBC Transactions and CompletableFuture

Inside a test-managed JDBC transaction, `CompletableFuture.runAsync(...jdbcTemplate.update...)` runs on a worker thread. The test thread rolls back, yet the row remains. Why?

**Answer:** Imperative transaction context binds to the thread via `ThreadLocal` and does not propagate to worker threads. The worker can use a separate autocommit connection. Manage transactions and cleanup explicitly instead of relying on test-thread rollback.

### Exercise F — Reactive Test Cancels Before INSERT Runs

You write `StepVerifier.create(insert().then(Mono.never()).as(op::transactional)).thenCancel().verify()` and observe `0` afterward. Have you proved rollback?

**Answer:** Not necessarily. Cancellation may happen before `insert()` is even subscribed/executed. Confirm SQL completed **inside the transaction** prior to cancelling, then query the DB after cancellation.

### Exercise G — JDBC and R2DBC Pointing to the Same DB

A `TransactionTemplate` using JDBC and a `TransactionalOperator` using R2DBC connect to the same PostgreSQL instance. Can they form one atomic transaction?

**Answer:** No. They use two distinct transaction managers and connections and do not auto-join into a distributed transaction. Design workflows, events/outbox, or proper protocols per requirements, and test partial-failure cases.

### Exercise H — `@Transactional` and Self-Invocation

A reactive service has `@Transactional Mono<Void> save()`, and another method on the same instance calls `this.save()`. Is proxy interception guaranteed?

**Answer:** No, under standard Spring proxy mode. Self-invocation bypasses the proxy. Refactor through an injected proxied bean or use `TransactionalOperator` for explicit control.

### Exercise I — Committing a Set of R2DBC Writes

You wrap two writes in `TransactionalOperator`. The test only calls `verifyComplete()` without querying the DB afterward. Have you proved the commit succeeded per contract?

**Answer:** Only that the transactional Publisher completed without error in the test. To prove data committed with the right contents, query in a separate subscription outside the operator after termination, then clean up.

## 20. Checklist Before Finalizing Transaction Tests

- [ ] Identified whether the stack is JDBC/JPA (imperative) or R2DBC (reactive).
- [ ] Identified the active manager: `PlatformTransactionManager` or `ReactiveTransactionManager`.
- [ ] Never assumed `@JdbcTest` and `@DataR2dbcTest` share the same rollback defaults.
- [ ] For JDBC, checked whether a test-managed transaction is active and flagged for rollback.
- [ ] For R2DBC, verified which exact pipeline is wrapped by `TransactionalOperator`.
- [ ] For R2DBC, subscribed to every DB Publisher and awaited terminal signals.
- [ ] Never used `assertNotNull(Mono)` as proof that SQL executed.
- [ ] Never called detached `subscribe()` inside a transactional pipeline.
- [ ] Never wrapped blocking JDBC in a `Mono` pretending it joined an R2DBC transaction.
- [ ] Checked Spring AOP proxying when using `@Transactional` on services.
- [ ] Distinguished error recovery inside vs. outside reactive transactions.
- [ ] Tested cancel/timeout rollback impacts when part of the contract.
- [ ] Never confused same-transaction visibility with committed visibility.
- [ ] Verified rollback via a query **outside the transaction boundary**, not just asserting exceptions.
- [ ] Verified commits by querying in a fresh transaction and cleaning up.
- [ ] Avoided JUnit preemptive timeouts when relying on thread-bound JDBC test transactions.
- [ ] Treated H2 strictly as a test DB and added production-engine integration tests for isolation/locking/SQL semantics.
- [ ] Verified schemas/resources/SQL init run cleanly against the `DataSource` or `ConnectionFactory`.
- [ ] Avoided mixing JDBC and R2DBC auto-configs in one module without explicit manager/resource control.
- [ ] Never used production databases, endpoints, or credentials in tests.
- [ ] Verified JUnit test counts, Gradle/Maven versions, and dependencies in the target environment.
- [ ] Never used `@DirtiesContext` as a substitute for cleaning up committed rows.
- [ ] Never called `block()` on reactive event loops when production requires non-blocking behavior.
- [ ] Added dedicated tests for caching, retries, optimistic locking, or isolation where applicable.

## 21. Summary

**JDBC transactions and R2DBC reactive transactions both solve SQL atomicity, yet they do not share the same context mechanism.**

- **JDBC:** work happens imperatively on thread-bound connections; `TransactionTemplate` or `@Transactional` with `PlatformTransactionManager` manages the transaction. In Spring Boot 3.x, `@JdbcTest` rolls back test transactions by default.
- **R2DBC:** work lives inside Publishers and starts on subscribe; `TransactionalOperator` or proxied reactive `@Transactional` with `ReactiveTransactionManager` manages transactions via Reactor Context. `@DataR2dbcTest` is **non-transactional** by default.
- **Proper testing:** assert both signals/outputs and **database state after commit/rollback**. Never infer rollback from annotation names alone, and never infer commit from reading a row inside the same open transaction.
- **Safe design:** compose reactive operations into a single pipeline, avoid detached subscriptions and blocking JDBC inside reactive transactions, clean up committed data explicitly, and test against the production DB engine when proving isolation or locking.

Clear reasoning about transaction boundaries makes JDBC and R2DBC tests reliable, prevents data leakage, and eliminates tests that pass in CI while losing consistency in production.

## Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest` default rollback, `@DataR2dbcTest` non-transactional default.
- [Spring Boot 3.5 — Test Slice Auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): `DataSource`/JDBC and `ConnectionFactory`/R2DBC configuration per slice.
- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed transactions, `PlatformTransactionManager`, rollback, `TestTransaction`, and preemptive-timeout caveats.
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): `PlatformTransactionManager` vs. `ReactiveTransactionManager`, thread-bound and reactive transaction SPIs.
- [Spring Framework — Declarative Transaction Explained](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): imperative vs. reactive `@Transactional`, return types, Reactor Context.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `TransactionTemplate`, `TransactionalOperator`, and rollback on cancel.
- [Spring Framework — R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html): lazy SQL, `rowsUpdated`, `bind`, `ConnectionFactoryUtils`, and `R2dbcTransactionManager`.
- [Spring Data Relational — R2DBC Getting Started](https://docs.spring.io/spring-data/relational/reference/r2dbc/getting-started.html): R2DBC SQL, H2 driver, and setup.
- [R2DBC H2 Driver — Documentation](https://github.com/r2dbc/r2dbc-h2): in-memory URL, connection options, transactional support.
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): subscribe, terminal verification, async publisher behavior.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): `schema.sql` and initialization for JDBC/R2DBC; version-dependent.