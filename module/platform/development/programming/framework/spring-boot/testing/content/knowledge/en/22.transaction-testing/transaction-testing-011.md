# Reactive Transactions and How They Differ from the ThreadLocal Mechanism in Spring Boot

## 1. Why Can a Familiar @Transactional Behave Differently in WebFlux/R2DBC?

In Spring Boot, many developers are used to writing a synchronous service:

```java
@Transactional
public void moveMoney() {
    debitAccount();
    creditAccount();
}
```

When a service uses JDBC/JPA and is called through a Spring proxy, the transaction is typically bound to the **executing thread**. Yet in a Reactive pipeline, processing a single request can hop across multiple threads, actual work starts only upon **subscription**, and a `Mono`/`Flux` carries a **Reactor Context** dedicated to that subscriber.

The following example looks very similar to synchronous code, yet follows a different contract:

```java
@Transactional
public Mono<Void> moveMoney() {
    return debitReactive()
            .then(creditReactive());
}
```

This is an **illustrative snippet** requiring real reactive methods, bean/service proxies, and a matching `ReactiveTransactionManager`. Reactive transactions are not tracked via JDBC/JPA-style `ThreadLocal`. Spring uses the Reactor Context to bind the **R2DBC Connection, transaction state, and each database operation within the same reactive pipeline**.

**Three core rules:**

1. **Imperative:** `PlatformTransactionManager` (e.g., `JpaTransactionManager`, `DataSourceTransactionManager`) typically binds state/resources to a **thread**.
2. **Reactive:** `ReactiveTransactionManager` (e.g., `R2dbcTransactionManager`) binds state/resources to the **subscriber context**. Threads can change while the transaction remains valid, provided the Reactor Context flows cleanly through the pipeline.
3. **`@Transactional` does not pull out-of-pipeline work into the same transaction.** Calling `.subscribe()` manually, creating another publisher without chaining it, running blocking JDBC outside a transaction, or losing Reactor Context can cause work to escape the intended transaction.

This lesson focuses on **Spring Boot testing**: how to create a real reactive transaction, verify commit/rollback with `StepVerifier`, expose commonly overlooked boundary mistakes, and understand why `@DataR2dbcTest` **does not auto-roll back tests** like `@DataJpaTest`.

Complete code uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, Reactor, R2DBC H2, and JUnit Jupiter**. Spring Boot 4.x changes test slice modules/imports; the Reactor Context principles remain the same.

## 2. ThreadLocal vs. Reactor Context: Two Independent Models

### 2.1. Synchronous Transactions Use Thread-Bound Resources

In JDBC/JPA, Spring has `org.springframework.transaction.support.TransactionSynchronizationManager`. The transaction interceptor opens a transaction, binds the connection/persistence context to the thread, runs the method, and decides commit/rollback.

```text
Thread A:
    Controller -> @Transactional Service -> JdbcTemplate -> DataSource
                  |                        |
                  +-- ThreadLocal tx state-+
    method return -> transaction manager commits/rolls back
```

Calls on the **same thread with the right transaction manager** can reuse the same connection. Yet if code spawns a new thread via `new Thread`, `CompletableFuture`, or an executor, this `ThreadLocal` is **not automatically** inherited by that thread. Adding `@Transactional` does not turn JDBC into a reactive API.

### 2.2. Reactive Transactions Use Subscriber-Bound Context

Spring Framework has `org.springframework.transaction.reactive.TransactionSynchronizationManager`. This is **a different class**, not the static `support.TransactionSynchronizationManager` of imperative code.

```text
Subscriber S1 + Reactor Context { tx resource / R2DBC connection }
    |
    +-- Mono SQL INSERT A
    |
    +-- then / flatMap
    |
    +-- publishOn (may switch to Thread B)
    |
    +-- Mono SQL INSERT B
    |
    +-- onComplete -> commit (per transaction operator)
        onError / cancel -> rollback per semantics
```

It is the **subscription-bound Reactor Context**, not "whatever the current thread is named," that keeps R2DBC operations using the right connection/transaction. When the pipeline is composed properly, a `publishOn` does not mean the transaction is automatically lost.

**Do not confuse Reactor Context with MDC logging `ThreadLocal`.** Carrying a Trace ID or MDC across thread switches may require separate context propagation mechanisms. Missing MDC in logs does not prove the DB transaction vanished; inspect the transaction resource or DB state directly.

### 2.3. Comparison Table

| Characteristic | Imperative JDBC/JPA | Reactive R2DBC |
|---|---|---|
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Example implementations | `JpaTransactionManager`, `DataSourceTransactionManager` | `R2dbcTransactionManager` |
| Resource holder | Spring transaction infrastructure `ThreadLocal` | Reactor Context bound to subscriber |
| When work executes | Usually during synchronous method invocation | When publisher is subscribed and signals are consumed |
| Production API | `TransactionTemplate`, `@Transactional` on regular methods | `TransactionalOperator`, `@Transactional` on `Mono/Flux` |
| Data access | `JdbcTemplate`, `EntityManager` | `DatabaseClient`, `R2dbcEntityTemplate`, reactive repositories |
| Completion boundary | Synchronous method return/throw | Reactive `onComplete`/`onError`/`cancel` |
| Thread switch | Does not auto-propagate `ThreadLocal` to new thread | Reactor Context is normally preserved when composed properly |
| Tested with | JUnit + JDBC/JPA slices, sometimes `TestTransaction` | Reactor Test `StepVerifier`, real R2DBC, explicit operators |
| Auto-rollback in test slice | `@JdbcTest`/`@DataJpaTest` usually roll back | `@DataR2dbcTest` is **not transactional by default** |
| Subscribing twice to one publisher | Not the primary model | Can trigger **two independent executions/transactions** |

## 3. How Does Spring Determine @Transactional Mode?

Spring's `TransactionInterceptor` supports both models. For methods returning a **reactive type** such as `Publisher`/`Mono`/`Flux`, Spring can apply reactive transactions when using a `ReactiveTransactionManager`. Regular methods, including `void`, require an **imperative transaction manager** for standard mechanics.

**Valid** R2DBC example:

```java
@Transactional
public Mono<Void> createOrder(String id) {
    return db.sql(
            "INSERT INTO orders(id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then();
}
```

This is an illustrative method (requires `DatabaseClient db`, table `orders`, Spring proxy, and an R2DBC transaction manager). **The Publisher is returned** for the caller/framework to subscribe. Spring's transaction advice wraps **the execution of the publisher**, not treating building the `Mono` object during the method call as a commit.

**Invalid** example for an R2DBC transaction:

```java
@Transactional
public void createOrderWrong(String id) {
    db.sql("INSERT INTO orders(id) VALUES (:id)")
            .bind("id", id)
            .fetch().rowsUpdated()
            .subscribe();
}
```

This is an **illustrative anti-pattern**, not code from the runnable project. Problems:
- The method returns `void`, providing no publisher for the reactive transaction interceptor to manage.
- `.subscribe()` starts a detached execution; exceptions/rollbacks are not propagated back to the caller.
- If only a `ReactiveTransactionManager` exists, the advice cannot turn a `void` method into a reactive transactional operation.
- Even without a proxy error, a fire-and-forget `subscribe()` can still run outside the expected transaction/pipeline.

Another pitfall is **self-invocation**: `this.createOrder(id)` inside the same bean normally bypasses `@Transactional`'s Spring AOP proxy. Tests must invoke the method through a Spring bean/proxy or use a `TransactionalOperator` inside the pipeline.

## 4. R2dbcTransactionManager and TransactionalOperator

`R2dbcTransactionManager` manages transactions for an R2DBC `ConnectionFactory`, binding the connection to the subscriber's Reactor Context. Spring's `DatabaseClient` and Spring Data R2DBC infrastructure use the corresponding `ConnectionFactoryUtils` to acquire the bound connection.

`TransactionalOperator` is a convenient programmatic API:

```java
TransactionalOperator tx =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Void> work = insertA()
        .then(insertB())
        .as(tx::transactional);
```

This is an **example inside a scope containing a `ReactiveTransactionManager` and R2DBC `Mono` operations**. When `work` is subscribed:
- The transaction operator opens a transaction.
- `insertA()` executes.
- After A completes, `insertB()` executes inside **the same reactive transaction**.
- When the entire pipeline completes normally, the operator commits.
- When the pipeline emits an unrecovered `onError` before the operator boundary, the operator rolls back.
- When the subscriber **cancels**, the transaction also rolls back in modern Spring Reactive mechanics; this detail matters for `take`, `next`, `timeout`, and client disconnects.

**Do not use `Mono.when(insertA(), insertB())` as a recipe for "two parallel SQL statements on the same connection."** Many R2DBC drivers/connections do not allow concurrent statements on a single transaction connection. Use `.then(...)` or `concatMap` when sequential execution is needed, unless you have designed and verified an appropriate concurrency model.

### 4.1. Operator-Style vs. Callback-Style API

Operator-style:

```java
return insertA()
        .then(insertB())
        .as(tx::transactional);
```

Callback-style:

```java
return tx.execute(status ->
        insertA().then(insertB()))
        .then();
```

Inside the callback, `status` is a `ReactiveTransaction`; you can call `status.setRollbackOnly()` when rolling back based on a domain decision without throwing an exception. Usually, however, it is clearer to let errors emit down the pipeline and let the operator roll back by default.

### 4.2. Why Must the Transaction Scope Wrap *All* the Work?

Compare:

```java
Mono<Void> bothInOneTransaction =
        insertA().then(insertB()).as(tx::transactional);
```

with:

```java
Mono<Void> onlyBIsTransactional =
        insertA().then(
                insertB().as(tx::transactional));
```

In the first version, both A and B sit under the **same transaction operator**. In the second version, A runs **before subscribing to B's operator-wrapped publisher**, so A can auto-commit outside B's transaction. If B fails and rolls back, A is not automatically undone.

When reviewing code, do not just check whether `@Transactional` or `TransactionalOperator` is present; determine **which publishers the operator actually wraps**.

## 5. What Is Reactor Context and How Does It Differ from ThreadLocal?

Reactor Context is a **subscription-associated** key/value structure propagated by Reactor operators according to its rules. It supports state like transaction context or tracing without relying on **a single fixed thread**.

### 5.1. A Simple Reactor Context Example Without a Database

File `ReactorContextMiniDemo.java`:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class ReactorContextMiniDemo {
    public static void main(String[] args) {
        String value = Mono.deferContextual(context ->
                Mono.just(context.get("requestId")))
                .publishOn(Schedulers.parallel())
                .contextWrite(context -> context.put("requestId", "REQ-42"))
                .block();

        System.out.println(value);
    }
}
```

**Expected stdout, if run successfully with Reactor Core on the classpath:**

```text
REQ-42
```

This is a **complete Java main class**, requiring the Reactor Core dependency to compile/run. For a Spring Boot project using Reactor, place the class in a test/demo source set and run via Gradle/Maven `JavaExec` or an IDE run with the configured classpath. `.block()` here is used only in a **main demo on a regular thread** to wait for stdout; never copy `.block()` into WebFlux event-loop handlers.

`publishOn` changes the scheduler for downstream signals, yet `contextWrite` and `deferContextual` demonstrate that Context is not simply a `ThreadLocal`. It is not proof of a real R2DBC transaction: a DB transaction requires a **reactive transaction manager** and a real connection.

### 5.2. Inspecting Spring's Transaction Context

When a pipeline is **inside a reactive transaction**, state can be inspected with Spring's API:

```java
Mono<Boolean> active =
        org.springframework.transaction.reactive
                .TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(manager -> manager.isActualTransactionActive())
                .as(tx::transactional);
```

This is an **illustrative snippet** in a class with `TransactionalOperator tx`; Java syntax does not allow line breaks inside a package name directly as shown above when written literally, so import the class as in the next section when using it. The normal result is `true` when an actual reactive transaction is open. Never use this API to manually bind/unbind connections in everyday business services.

**Two completely different `TransactionSynchronizationManager` classes:**

```java
// Imperative: static, thread-bound
org.springframework.transaction.support
        .TransactionSynchronizationManager
        .isActualTransactionActive();

// Reactive: instance, retrieved from Reactor Context
org.springframework.transaction.reactive
        .TransactionSynchronizationManager
        .forCurrentTransaction();
```

These lines are **import/API illustrations**, not a standalone Java file. In real code, import the right class and keep calls valid. Calling the imperative `isActualTransactionActive()` on a reactive thread does not prove whether an R2DBC transaction is open or closed.

## 6. A Complete Spring Boot 3.5 + R2DBC H2 + StepVerifier Project

The goal is to **run real SQL** without bringing JDBC `ThreadLocal` into the test. The example self-tests:
1. Programmatic transaction writes two rows and commits.
2. A mid-pipeline error rolls back the first row.
3. Error recovery **inside** the transaction can turn an error into completion and allow partial writes to commit.
4. Error recovery **outside** the transaction allows rollback before the fallback applies.
5. Reactive `@Transactional` through a Spring proxy.
6. Transaction state via **Reactive `TransactionSynchronizationManager`**.
7. Lazy publishers: merely constructing a `Mono` does not touch the database.
8. Two subscriptions to the same cold publisher can execute the operation **twice**.
9. `publishOn` switches schedulers while Reactor Context stays preserved in a properly composed pipeline.

### 6.1. File Structure

```text
build.gradle
src/main/java/com/example/reactivetx/
    ReactiveTxApplication.java
    LedgerService.java
src/test/resources/
    application.properties
    sql/ledger-schema.sql
src/test/java/com/example/reactivetx/
    ReactiveTransactionTest.java
```

### 6.2. build.gradle (Java 17, Spring Boot 3.5.x)

`build.gradle` using Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    testRuntimeOnly 'io.r2dbc:r2dbc-h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM aligns Reactor, Spring Framework, and driver versions. `r2dbc-h2` is an **R2DBC driver**, not `com.h2database:h2` JDBC driver as a drop-in substitute. If the production app uses PostgreSQL, put `r2dbc-postgresql` in production runtime and isolate H2 to test scope as needed.

`spring-boot-starter-webflux` is unnecessary just to test R2DBC transactions at the service layer; the sample app has no HTTP server. If you want to hit WebFlux endpoints, you can add the WebFlux starter and test client, which is a separate integration scope.

### 6.3. Application Class

File `src/main/java/com/example/reactivetx/ReactiveTxApplication.java`:

```java
package com.example.reactivetx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

### 6.4. Database Configuration for Tests

File `src/test/resources/application.properties`:

```properties
spring.r2dbc.url=r2dbc:h2:mem:///reactive_tx_lab?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:sql/ledger-schema.sql
```

File `src/test/resources/sql/ledger-schema.sql`:

```sql
CREATE TABLE ledger_entries (
    entry_id VARCHAR(120) PRIMARY KEY,
    amount INTEGER NOT NULL CHECK (amount >= 0)
);
```

Reasons for configuration:
- Boot builds a `ConnectionFactory` from `spring.r2dbc.url` and the R2DBC H2 driver.
- Boot can initialize the schema for the `ConnectionFactory` via SQL scripts; we specify the location explicitly and enable `spring.sql.init.mode=always`.
- `DB_CLOSE_DELAY=-1` keeps the H2 in-memory DB alive across connection opens/closes in the same process, preventing tables from vanishing when reactive connections close.
- `entry_id` is supplied by tests rather than relying on `IDENTITY` or generated-key retrieval.
- The table has a primary key and check constraint so duplicate subscriptions produce observable errors rather than inserting silently.

**Caution:** Using H2 proves Spring/R2DBC transaction boundaries in this setup, yet **does not prove** PostgreSQL/MySQL share the same isolation, syntax, or lock semantics. When production-like fidelity is needed, swap the URL/driver for the matching R2DBC Testcontainers setup and manage cleanup/DB lifecycle explicitly.

### 6.5. Real Reactive Service

File `src/main/java/com/example/reactivetx/LedgerService.java`:

```java
package com.example.reactivetx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public LedgerService(
            DatabaseClient db,
            ReactiveTransactionManager transactionManager) {
        this.db = db;
        this.tx = TransactionalOperator.create(transactionManager);
    }

    private Mono<Void> insert(String id, int amount) {
        return db.sql("""
                INSERT INTO ledger_entries (entry_id, amount)
                VALUES (:id, :amount)
                """)
                .bind("id", id)
                .bind("amount", amount)
                .fetch()
                .rowsUpdated()
                .then();
    }

    public Mono<Integer> countForPrefix(String prefix) {
        return db.sql("""
                SELECT COUNT(*) AS total
                  FROM ledger_entries
                 WHERE entry_id LIKE :pattern
                """)
                .bind("pattern", prefix + ":%")
                .map((row, metadata) ->
                        ((Number) row.get("total")).intValue())
                .one();
    }

    public Mono<Void> writePairProgrammatically(String prefix) {
        return insert(prefix + ":a", 10)
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }

    public Mono<Void> writeThenFail(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("forced failure")))
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }

    public Mono<Void> recoverInsideTransaction(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("recover inside")))
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Mono.empty())
                .as(tx::transactional);
    }

    public Mono<Void> recoverOutsideTransaction(String prefix) {
        return insert(prefix + ":a", 10)
                .then(Mono.<Void>error(
                        new IllegalStateException("recover outside")))
                .as(tx::transactional)
                .onErrorResume(
                        IllegalStateException.class,
                        error -> Mono.empty());
    }

    // Spring AOP proxy handles reactive @Transactional on Publisher.
    @Transactional
    public Mono<Void> writePairDeclaratively(String prefix) {
        return insert(prefix + ":a", 10)
                .then(insert(prefix + ":b", 20));
    }

    public Mono<Boolean> reactiveTransactionIsActive() {
        return TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(TransactionSynchronizationManager
                        ::isActualTransactionActive)
                .as(tx::transactional);
    }

    public Mono<Void> writePairAfterSchedulerSwitch(String prefix) {
        return insert(prefix + ":a", 10)
                .publishOn(Schedulers.parallel())
                .then(insert(prefix + ":b", 20))
                .as(tx::transactional);
    }
}
```

**Reading the code accurately:**
- `insert(...)` returns `Mono<Void>`; SQL executes only upon **subscription**.
- `.then(...)` executes B after A completes, avoiding sending two concurrent SQL statements over one R2DBC connection.
- `writePairProgrammatically`: the transaction operator wraps **both** inserts.
- `writeThenFail`: after A, emits an `IllegalStateException`, so B does not run and the operator rolls back A.
- `recoverInsideTransaction`: `onErrorResume` sits **before** `.as(tx::transactional)` so the operator sees `onComplete` instead of an error; A can **commit**.
- `recoverOutsideTransaction`: the operator sees the error first, rolls back A, and only then `onErrorResume` **outside** handles the result for the caller.
- `writePairDeclaratively`: uses `@Transactional` on a **public method returning `Mono`**, called through a Spring proxy.
- `reactiveTransactionIsActive`: observes the **reactive** transaction context, not the imperative `ThreadLocal`.
- `publishOn` switches schedulers mid-pipeline without detached `.subscribe()`; Reactor Context flows through standard operators.

**Regarding transaction managers:** Spring Boot with a single suitable R2DBC `ConnectionFactory` normally auto-configures `R2dbcTransactionManager`; the demo has only one reactive manager. With multiple managers, pick the right `@Transactional(transactionManager=...)` or inject an explicitly qualified `ReactiveTransactionManager`. Never assume a `PlatformTransactionManager` and a `ReactiveTransactionManager` can manage the same physical DB transaction together.

### 6.6. Complete JUnit Jupiter + StepVerifier Suite

File `src/test/java/com/example/reactivetx/ReactiveTransactionTest.java`:

```java
package com.example.reactivetx;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.test.context.transaction.TestTransaction;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ReactiveTransactionTest {

    @Autowired
    LedgerService ledger;

    @Autowired
    DatabaseClient db;

    // No @Transactional on the test class. Each JUnit test
    // uses a unique prefix, with explicit cleanup after each method.
    private final List<String> prefixes = new ArrayList<>();

    private String newPrefix() {
        String prefix = "case-"
                + UUID.randomUUID().toString().replace("-", "");
        prefixes.add(prefix);
        return prefix;
    }

    private Mono<Void> cleanOne(String prefix) {
        return db.sql("""
                DELETE FROM ledger_entries
                 WHERE entry_id LIKE :pattern
                """)
                .bind("pattern", prefix + ":%")
                .fetch()
                .rowsUpdated()
                .then();
    }

    @AfterEach
    void cleanupOutsideTransaction() {
        Mono<Void> cleanup = Flux.fromIterable(prefixes)
                .concatMap(this::cleanOne)
                .then();

        // JUnit test thread: StepVerifier subscribes and awaits completion.
        StepVerifier.create(cleanup).verifyComplete();
    }

    @Test
    void programmaticTransactionCommitsTwoRows() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairProgrammatically(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void errorSignalRollsBackEarlierSql() {
        String prefix = newPrefix();

        StepVerifier.create(ledger.writeThenFail(prefix))
                .expectErrorMatches(
                        error -> error instanceof IllegalStateException
                                && "forced failure"
                                        .equals(error.getMessage()))
                .verify();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();
    }

    @Test
    void recoveryInsideTransactionCanCommitPartialWork() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.recoverInsideTransaction(prefix))
                .verifyComplete();

        // Error was turned into completion BEFORE the operator.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(1)
                .verifyComplete();
    }

    @Test
    void recoveryOutsideTransactionPreservesRollback() {
        String prefix = newPrefix();

        // Caller sees completion due to fallback outside transaction.
        StepVerifier.create(
                ledger.recoverOutsideTransaction(prefix))
                .verifyComplete();

        // Yet the transaction received the error and rolled back earlier.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();
    }

    @Test
    void declarativeReactiveTransactionCommitsBothRows() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairDeclaratively(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void reactiveContextHasActualTransactionWhileSubscribed() {
        // Test-managed ThreadLocal transaction is not active.
        assertFalse(TestTransaction.isActive());

        StepVerifier.create(ledger.reactiveTransactionIsActive())
                .expectNext(true)
                .verifyComplete();

        assertFalse(TestTransaction.isActive());
    }

    @Test
    void creatingPublisherDoesNotRunSqlUntilSubscription() {
        String prefix = newPrefix();
        Mono<Void> operation =
                ledger.writePairProgrammatically(prefix);

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(0)
                .verifyComplete();

        StepVerifier.create(operation).verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void subscribingTwiceRepeatsColdSqlExecution() {
        String prefix = newPrefix();
        Mono<Void> operation =
                ledger.writePairProgrammatically(prefix);

        StepVerifier.create(operation).verifyComplete();

        // Second subscription tries to INSERT the same primary keys again.
        StepVerifier.create(operation).expectError().verify();

        // Second transaction rolls back; the first two rows remain.
        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }

    @Test
    void schedulerSwitchWithinPipelineKeepsTransaction() {
        String prefix = newPrefix();

        StepVerifier.create(
                ledger.writePairAfterSchedulerSwitch(prefix))
                .verifyComplete();

        StepVerifier.create(ledger.countForPrefix(prefix))
                .expectNext(2)
                .verifyComplete();
    }
}
```

There are **9 test methods**. Assertions are designed to observe the **real database after completion/error**. Do not infer that two operations committed merely from `StepVerifier.verifyComplete()` on the write publisher; also run an independent query as shown in the tests.

**Why doesn't cleanup roll back in the test?** The test class does not carry TestContext's `@Transactional`; `@AfterEach` uses an R2DBC publisher and `StepVerifier` subscribes to DELETE each prefix. `@DataR2dbcTest` also **does not auto-roll back by default**, so if you switch to that slice you must still manage fixtures/cleanup explicitly. Rows committed during tests persist until cleanup runs or the in-memory database is destroyed.

**Do not fabricate stdout/test-results:** This article provides source code and expected behavior; there is no claim these tests ran on your machine. Run commands and report locations appear in section 7.

## 7. Running Tests and Reading Reports

If the project has the Gradle wrapper, from root:

```bash
./gradlew test --tests "com.example.reactivetx.ReactiveTransactionTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.reactivetx.ReactiveTransactionTest"
```

If using the Maven wrapper with equivalent dependencies/BOM:

```bash
./mvnw -Dtest=ReactiveTransactionTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ReactiveTransactionTest test
```

Gradle reports are normally at `build/reports/tests/test/index.html`, and Maven Surefire at `target/surefire-reports/` of the module. Verify that **9 cases were discovered/executed**, not merely a `NO-SOURCE`, `UP-TO-DATE`, or skipped build. If the H2 connection URL or SQL init fails, examine startup root causes before modifying assertions.

The example uses two test patterns:
- `StepVerifier.create(writePublisher).verifyComplete()`: consumes the **entire** write publisher until completion, allowing the transaction to commit.
- `StepVerifier.create(readPublisher).expectNext(...).verifyComplete()`: creates a **separate subscription** to observe DB state beyond the commit/rollback boundary.

**Note that SQL operations can return `Mono<Void>`**: `verifyComplete()` has no `expectNext` because the publisher only completes or signals an error. If you change the service to return `Mono<Long>` from `rowsUpdated()`, assert the appropriate `onNext` value and completion.

## 8. Why Does @DataR2dbcTest Differ from @DataJpaTest?

In Spring Boot 3.5:

| Annotation | Stack | Default test-managed rollback? |
|---|---|---|
| `@JdbcTest` | JDBC (`PlatformTransactionManager`) | **Yes** in standard setups |
| `@DataJdbcTest` | Spring Data JDBC | **Yes** |
| `@DataJpaTest` | JPA/Hibernate | **Yes** |
| `@DataR2dbcTest` | Spring Data R2DBC | **No** |
| `@SpringBootTest` without `@Transactional` | Full context | **No** |
| `@SpringBootTest @Transactional` JDBC/JPA | Test's thread-bound transaction | Usually yes, though excludes HTTP server threads |
| Reactive `@Transactional` service returning `Mono/Flux` | `ReactiveTransactionManager` | Each **subscription/publisher call** has its own scope; not a full JUnit method rollback |

`@DataR2dbcTest` configures `R2dbcEntityTemplate`, Spring Data R2DBC repositories, and a matching test database from the classpath; it does not automatically create a **test-managed reactive transaction** wrapping the JUnit method. Thus a `repository.save(entity)` that gets subscribed can **commit for real** and survive after the test.

When writing R2DBC slice tests:
1. Create an isolated test database and clear schema/fixtures.
2. Use `StepVerifier` or an appropriate subscriber so the publisher executes.
3. Wrap the pipeline requiring atomicity in **`TransactionalOperator`** or invoke a real reactive `@Transactional` service method through its proxy.
4. Clean up data outside the transaction or recreate the database/container.
5. Never assume TestContext's `@Rollback`/`TestTransaction` replaces Reactor Context transaction mechanics.

**Regarding `@Transactional` on a reactive test method:** traditional Spring TestContext test-managed transactions attach to `PlatformTransactionManager`/threads, which differs from `ReactiveTransactionManager`. Do not add `@Transactional` on a `void` JUnit test expecting `Mono`s subscribed inside to auto-roll back. What needs protection is the **transactional pipeline/service path**, not an annotation placed at the wrong layer.

## 9. Subscription: Where a Reactive Transaction Actually Begins

`DatabaseClient` and Spring Data R2DBC return cold publishers for many operations. When constructing:

```java
Mono<Void> operation = db.sql(
        "INSERT INTO ledger_entries(entry_id, amount) VALUES (...)")
        .fetch()
        .rowsUpdated()
        .then();
```

This is a syntax illustration with incomplete SQL binds to explain laziness. At the moment `operation` is created, **no SQL has been sent yet**. Once a subscriber arrives, execution happens. If the publisher includes `TransactionalOperator`, the transaction is also created as the subscriber flows through the operator.

### 9.1. Two Subscriptions Can Be Two Transactions

```java
Mono<Void> save = service.writePairProgrammatically(prefix);

StepVerifier.create(save).verifyComplete();
StepVerifier.create(save).expectError().verify();
```

This snippet assumes the service, prefix, and test scope. Because `writePairProgrammatically` returns a cold publisher as in the demo:
- Subscription 1: INSERTs A/B, commits.
- Subscription 2: tries to INSERT A/B again, hits primary key violation, and rolls back.
- Data committed in subscription 1 remains.

**Do not treat a `Mono` object as "an operation that runs exactly once."** It is an execution blueprint; multiple subscribers can repeat the same side effects multiple times. Use idempotency keys/unique constraints/transaction isolation per business requirements instead of relying on holding a `Mono` reference.

### 9.2. Manual `.subscribe()` Breaks Error Propagation

Anti-pattern:

```java
public Mono<Void> createBroken(String id) {
    repository.save(id).subscribe();
    return Mono.empty();
}
```

This is an illustrative snippet requiring an appropriate repository type. The caller receives an immediately completing `Mono.empty()`, while the save operation runs detached; if save fails, the error may never reach the caller, and an outer transaction does not necessarily encompass the work.

Correct way:

```java
public Mono<Void> createComposed(String id) {
    return repository.save(id).then();
}
```

When `createComposed` is wrapped in a reactive transaction, the save publisher itself sits **inside the same pipeline**, and error/completion signals flow up to the interceptor/operator.

### 9.3. `.block()` Is Not How You "Keep a Transaction"

Calling `.block()` on a WebFlux event-loop thread can be rejected (`IllegalStateException`) or stall processing; moreover, `.block()` creates **a new subscription**, not automatically inheriting the enclosing publisher's Reactor Context transaction.

Do not use:

```java
@Transactional
public Mono<Void> brokenTransfer() {
    firstReactiveWrite().block();
    return secondReactiveWrite();
}
```

This is an illustrative anti-pattern. In reactive code, **compose**:

```java
@Transactional
public Mono<Void> correctTransfer() {
    return firstReactiveWrite().then(secondReactiveWrite());
}
```

In JUnit/command-line tests, you can call `block()` **at the outermost boundary on a non-event-loop thread** to await results, though `StepVerifier` usually expresses signals and error expectations better. Never call `block()` **inside** a reactive transactional service just to write code like JDBC.

## 10. Error Recovery Can Make a Transaction Commit Unintentionally

This is one of the most important lessons. Consider two pipelines:

```java
Mono<Void> inside =
        firstInsert()
          .then(Mono.<Void>error(
                  new IllegalStateException("failure")))
          .onErrorResume(error -> Mono.empty())
          .as(tx::transactional);
```

```java
Mono<Void> outside =
        firstInsert()
          .then(Mono.<Void>error(
                  new IllegalStateException("failure")))
          .as(tx::transactional)
          .onErrorResume(error -> Mono.empty());
```

These are **illustrative** snippets in a class with `firstInsert()` and the operator. In `inside`, the error is turned into normal completion **before the transaction operator inspects the result**; the operator can commit `firstInsert`. In `outside`, the operator receives the error and rolls back first, and only afterward does the fallback make the caller see completion.

In the code suite from section 6, we test this directly:
- `recoverInsideTransaction` → counts **1 row**.
- `recoverOutsideTransaction` → counts **0 rows**.

**Scope limitation:** the example throws a deliberate Java error after a successful SQL statement, not a JDBC/R2DBC database error. A real constraint violation can put the transaction/resource into a rollback-only/aborted state; an inner `onErrorResume` then **does not guarantee** commit will succeed. Never violate domain policy by swallowing every `DataAccessException` just to silence errors in the pipeline.

### 10.1. onErrorComplete Is Even More Dangerous When Used Carelessly

`onErrorComplete()` turns any error into completion. Placed before the transaction boundary, you can accidentally preserve partial changes that succeeded earlier. If the use case is all-or-nothing, let the exception pass through the operator/interceptor and handle the response **outside**.

### 10.2. doOnError Only Observes

`doOnError(log::warn)` does not swallow errors; the error continues downstream and the transaction still rolls back per rules. Completely different from `onErrorResume` or `onErrorComplete`. Logging also does not replace `StepVerifier`/error assertions.

### 10.3. Retries and Transaction Boundaries

A `retryWhen` can create a **new subscription** after an error. Placed **outside** `TransactionalOperator`, each retry is usually a fresh attempt with its own transaction; placed **inside**, semantics change and the transaction after a DB failure may no longer be usable. Ensure:
- Each attempt gets a fresh transaction without committed side effects from prior attempts.
- Only clearly classified transient errors are retried, with backoff and a retry budget.
- Idempotency keys and retry limits are used when operations can write outside SQL.

Never enable unbounded retries for financial transfers assuming DB rollback alone suffices: emails/Kafka/HTTP calls emitted during earlier attempts are not undone automatically.

## 11. Cancellation: onCancel Differs from onComplete

Reactive Streams allows subscribers to **cancel**: no longer wanting remaining elements. Several operators can trigger cancellation:
- `take(1)` or `next()` on a multi-item `Flux`.
- `timeout(Duration)` when upstream does not finish in time.
- HTTP client disconnecting, propagating downstream cancellation upstream.
- A subscriber calling `cancel()` explicitly.

Spring Framework since 5.3 treats cancellation of a transactional publisher as a **rollback** signal. That can surprise developers when code emits a `Flux` inside a transaction while downstream reads only the first element.

Example worth thinking carefully about:

```java
Flux<Item> items =
        streamAndWriteItems()
                .as(tx::transactional);

Mono<Item> first = items.next();
```

This is an illustrative snippet, not standalone source code. `next()` can cancel the upstream publisher after the first item; the transaction may roll back instead of committing, even after the client received one item. Do not assume `Mono<Item>` completing means the entire `Flux` inside the transaction completed.

**Better design:** when all-or-nothing atomicity is required for a batch write, run the entire write pipeline to completion in one transaction **before** streaming results to the client, or split the use case into clear boundaries. For very long streams, never hold a DB transaction open while the user reads; use short per-batch/command transactions with explicit consistency semantics.

**Do not write cancellation tests using fixed sleeps** hoping an operation reached a particular row. When testing this behavior, use `StepVerifier`, publishers with synchronization signals, and inspect DB state after actual transaction cleanup/rollback.

## 12. Context Propagation Across publishOn/subscribeOn and When It Is Lost

A common misconception: "switching threads loses reactive transactions just like JDBC." That is **generally false**. `Reactor Context` belongs to the subscription and is maintained by Reactor operators.

```java
return writeA()
        .publishOn(Schedulers.parallel())
        .then(writeB())
        .as(tx::transactional);
```

Snippet inside a scope with `Mono<Void>`, `Schedulers`, and the tx operator. The test `schedulerSwitchWithinPipelineKeepsTransaction` confirms that in the R2DBC/H2 setup, both A and B complete successfully under the transaction operator.

**What breaks boundaries more easily than switching schedulers:**
- Calling `subscribe()` manually to launch a detached subscription.
- Calling `block()` nested inside a pipeline, spawning a new subscription and blocking the thread.
- Offloading work to `CompletableFuture`, callback-based APIs, or custom `Executor`s without bridging back into the Reactor chain properly.
- Taking a publisher out and subscribing to it in another bean so the transaction operator no longer wraps the publisher that needs commit/rollback.
- Placing `contextWrite` at the wrong position and assuming it fabricates an R2DBC transaction resource; you cannot conjure a valid transaction simply via `context.put("transaction", true)`.

**Subtle point:** Context is **per subscriber**. Two requests running concurrently on the same event-loop thread can still hold two completely independent Reactor Contexts/transactions. That is why you should never stash a "current transaction id" in a global static field or hand-rolled `ThreadLocal` across reactive requests.

## 13. @Transactional Rollback Mechanics in Reactive

With Spring declarative transactions, `RuntimeException` or `Error` rolls back by default; checked exceptions may require `rollbackFor` per declared policies. On the reactive path, the transaction interceptor inspects the publisher's **error signal** and rolls back accordingly.

| Publisher outcome | Typical effect inside transaction operator |
|---|---|
| Normal `onComplete` | Commits if transaction/resources are healthy |
| Unrecovered `onError(RuntimeException)` | Rolls back |
| `onError(checked Exception)` per annotation policy | Commit/rollback rule depends on configuration |
| `cancel` | Rolls back in modern Spring reactive |
| `onErrorResume` swallowing error **before operator** | Operator sees completion; can commit earlier work |
| `onErrorResume` **after operator** | Operator gets to roll back, then caller receives fallback |
| DB error marks transaction rollback-only | Commit not guaranteed; DB/provider decides |
| Not subscribed yet | No SQL execution/transaction yet |

Never write tests asserting only `Mono.error(...)` with the right exception and conclude data rolled back: **query the DB after the error** to prove earlier rows were erased. Especially in multi-database setups, one operation could use a different connection manager and sit outside that reactive transaction.

### 13.1. `@Transactional(readOnly=true)` Is Not an Absolute Write Barrier

Read-only configuration can be applied by the driver/DB as a hint or enforcement depending on transaction manager/dialect. Never write `@Transactional(readOnly=true)` and claim every `INSERT` is blocked across all R2DBC drivers. Verify on a production-like database if that requirement matters.

### 13.2. Multiple ReactiveTransactionManager Beans

If the application has multiple `ConnectionFactory` instances or multiple `ReactiveTransactionManager`s, you must:
- Specify the right `@Transactional(transactionManager="...")` bean.
- Inject operators with matching qualifiers.
- Confirm each `DatabaseClient` uses the connection factory managed by that manager.
- Never assume a transaction on PostgreSQL A automatically covers Cassandra/Mongo/Redis or HTTP call B.

A standard R2DBC transaction normally manages **one database connection factory**; it does not become a distributed transaction automatically.

## 14. R2DBC Repositories, Entity Templates, and SQL Transactions

Spring Data R2DBC provides `R2dbcEntityTemplate` and reactive repositories; they also return `Mono`/`Flux` and participate in transactions when subscribed inside the appropriate Reactor Context.

```java
public Mono<Void> changeTwoEntities() {
    return entityTemplate.update(first)
            .then(entityTemplate.update(second))
            .then()
            .as(tx::transactional);
}
```

Illustrative snippet inside a class with an entity template, entities, and `tx`. Splitting the two calls into separate `.subscribe()` calls breaks the shared transaction.

**R2DBC is not reactive JPA.** It has no JPA `EntityManager`/first-level persistence context or Hibernate-style dirty checking. Assumptions from JPA such as "modified entities flush automatically on commit" do not carry over directly to Spring Data R2DBC. To update a row, invoke an actual update/save operation and subscribe to it.

With `@DataR2dbcTest`, the test slice focuses on repositories/templates and matching DB infrastructure, typically skipping regular `@Service` beans unlike a full context. To test a `@Transactional` service, `@Import` the service/manager configuration or use `@SpringBootTest` as in section 6. **Using the slice does not conjure TestContext rollback.**

## 15. What Assertions Should Reactive Transaction Tests Make?

A test suite protecting business logic should answer:

1. **Was there an actual subscription?** Creating a `Mono` without subscribing provides zero proof SQL ran.
2. **On success, does the DB end up with the right rows?** After `verifyComplete()`, use an independent `SELECT` publisher.
3. **On error, does the DB keep rows written before the error?** Test rollback by querying after the error.
4. **When a fallback sits inside, does it accidentally commit?** Test `onErrorResume` placement.
5. **For declarative `@Transactional`, does it go through the Spring proxy?** Test the bean from the context, not `new Service(...)`.
6. **Across scheduler switches, does Context stay in the chain?** Test `publishOn` inside the pipeline.
7. **When one publisher is subscribed twice, do side effects repeat?** Use primary keys/idempotency.
8. **When cancelling a `Flux` mid-stream, what is the DB state?** Never assume commit just because the client received one item.
9. **Do tests retain state across methods?** `@DataR2dbcTest` does not roll back by default; clean up via subscribed publishers.
10. **Are you testing the right DB dialect?** H2 verifies basic mechanics; production-like DBs verify locking/isolation/vendor constraints.

### 15.1. Why Is StepVerifier Better Than Just Asserting a Mono Object?

`StepVerifier` **subscribes** to the publisher and asserts every signal type:
- `expectNext(...)` for emitted values.
- `verifyComplete()` for normal completion.
- `expectErrorMatches(...)` for predicate-matched errors.
- `thenCancel().verify()` for cancellation when tests have proper synchronization.

`assertNotNull(service.save(...))` only checks that the Java reference to the `Mono` is non-null; it **executes no SQL**, commits nothing, and proves no rollback.

### 15.2. Do Not Use @Transactional on a Test Method to Mask Logic Under Test

Putting `@Transactional` on a `void` JUnit test with `@DataR2dbcTest` does not create a reactive test-managed transaction for subsequent subscriptions. Recommended patterns:
- Plain JUnit/slice test + calling a **real transactional reactive service**.
- Or wrapping the pipeline under test with `TransactionalOperator` inside the test.
- Cleaning up data outside transactions with explicit R2DBC publishers.

Do not try to force imperative TestContext's `TestTransaction.end()/start()` into R2DBC tests to mimic JDBC testing: they operate on completely different transaction contexts.

## 16. Common Issues and Fixes

| Symptom | Common cause | Fix |
|---|---|---|
| `@Transactional` does not roll back R2DBC | Method returns `void`, bypasses proxy, or lacks reactive manager | Return `Mono/Flux`, call through bean proxy, verify manager |
| Test gets a `Mono` yet DB is empty | Never subscribed | Use `StepVerifier`/framework subscription |
| DB keeps row despite test failure | Error swallowed by `onErrorResume` **before** tx boundary | Move fallback outside or make rollback policy explicit |
| DB keeps row after test ends | `@DataR2dbcTest` does not auto-roll back | Independent cleanup, isolated DB |
| `TestTransaction.isActive()` is false in R2DBC test | That API tracks imperative `ThreadLocal`, not Reactor Context | Use test queries/Reactive TSM for diagnostics |
| Static `TransactionSynchronizationManager` shows inactive | Imported imperative `support` package by mistake | Use reactive `org.springframework.transaction.reactive` |
| `block()` fails on event-loop | Blocking disallowed or deadlock/latency | Compose with `then/flatMap`, avoid blocking in handlers |
| Errors never reach caller | Detached `.subscribe()` / fire-and-forget | Return publisher, do not subscribe manually |
| Transaction lost when calling async task outside chain | Created detached subscription or unbridged context | Compose inside Reactor pipeline, check boundaries |
| Assuming `publishOn` always loses tx | Confusing Reactor Context with `ThreadLocal` | Test composed pipeline and DB state, not thread names |
| Same `Mono` executes SQL twice | Publisher subscribed twice | Idempotency keys, control subscription count |
| `take(1)`/timeout loses commit | Upstream cancelled | Consume transaction publisher fully or separate streaming from write tx |
| Concurrent statements on same tx connection fail | `flatMap`/`when` executes parallel SQL on one connection | Use `then/concatMap` when sequential execution is required |
| Rollback test passes on H2 yet differs on PostgreSQL | Dialect/constraints/locking/isolation differ | Use Testcontainers with production-like DB |
| Transaction marker active yet wrong database | Mismatched connection factories/managers | Check qualifiers and Spring Data client resources |
| `@Transactional` self-invocation does not activate | `this.method()` bypasses AOP proxy | Call via proxied bean or `TransactionalOperator` |
| `onErrorComplete` hides error, partial data remains | Error turned into completion inside operator | Do not swallow errors before tx boundary if all-or-nothing |
| Retry writes duplicates | Retry creates a new subscription/attempt | Idempotency, retry policy, and per-attempt transactions |
| Long reactive transaction causes locks | Holding transaction open during long HTTP streams | Split writes into bounded units, commit before streaming |
| R2DBC write sits outside tx | Client acquires connection bypassing Spring utilities | Use Spring `DatabaseClient`/repository or `TransactionAwareConnectionFactoryProxy` |
| Non-DB side effects do not roll back | Kafka/email/Redis/HTTP sit outside R2DBC tx | Outbox/compensation and separate integration tests |
| Tests did not run yet build looks green | Runner skipped JUnit class/`NO-SOURCE` | Read reports, verify executed test count |

## 17. Timing Model: subscribe, onComplete, onError, cancel

```text
Caller receives Mono<Void> from service
              |
       [not subscribed]
              |
              v
       StepVerifier.subscribe()
              |
              v
     TransactionalOperator
       opens R2DBC transaction T1
              |
              v
     INSERT A -- then --> INSERT B
              |
       +------+---------+
       |                |
    onComplete        onError
       |                |
     COMMIT T1       ROLLBACK T1
       |                |
    verifyComplete   verifyError
       |                |
       +-------+--------+
               |
   SELECT via another subscription
   to observe rows beyond boundary

mid-stream cancel -> rollback (modern Spring reactive)
```

**The boundary wraps the subscribed publisher**, not "when the Java method is called to assemble the `Mono`." This is the biggest difference from `ThreadLocal`-based transaction thinking.

## 18. Version Notes for Boot 3.5 / Boot 4

Complete code in this lesson uses Spring Boot **3.5.x**, where:
- R2DBC/Spring Data Redis? **No**: this lesson uses only R2DBC, no Redis/JDBC transactions.
- `R2dbcTransactionManager` lives in Spring Framework `org.springframework.r2dbc.connection`.
- `ReactiveTransactionManager` lives in `org.springframework.transaction`.
- `TransactionalOperator` lives in `org.springframework.transaction.reactive`.
- `DatabaseClient` lives in `org.springframework.r2dbc.core`.
- `@DataR2dbcTest` (when using the slice) lives in `org.springframework.boot.test.autoconfigure.data.r2dbc`.

In **Spring Boot 4.x**, test slices split into dedicated modules; `@DataR2dbcTest` moves to module `spring-boot-data-r2dbc-test`, package `org.springframework.boot.data.r2dbc.test.autoconfigure`. Do not copy Boot 4 imports into a Boot 3.5 runtime or mix Spring Framework 6 and 7 just to silence IDE errors.

The core principles hold across versions: reactive transactions require a manager and publisher, Reactor Context follows the subscriber, cancellation/error semantics must be tested, and `@DataR2dbcTest` does not replace explicit transactions/cleanup. Always rely on your project's **BOM/version** for exact APIs.

## 19. End-of-Lesson Checklist

- [ ] Chose the right transaction manager type: `PlatformTransactionManager` (JDBC/JPA) vs. `ReactiveTransactionManager` (R2DBC).
- [ ] For R2DBC, placed `@Transactional` on public methods returning `Mono/Flux`, invoked via Spring proxy.
- [ ] Publisher contains **all** operations requiring atomicity and is wrapped by the operator/transactional advice.
- [ ] Avoided manual `subscribe()` launching half a use case and dropping errors.
- [ ] Avoided calling `block()` inside WebFlux event loops or reactive transactions to imitate JDBC.
- [ ] On a single tx connection, avoided parallel SQL when the driver/semantics do not support it.
- [ ] Understood `publishOn/subscribeOn` thread switches do not erase Reactor Context.
- [ ] Remembered **each subscription** can spawn a separate execution/transaction.
- [ ] Tested `onErrorResume` **inside** and **outside** the operator; verified DB state, not merely completion signals.
- [ ] With `Flux`, accounted for cancellation from `take/next/timeout` leading to rollback.
- [ ] Used `StepVerifier` to consume publishers and assert completion/errors.
- [ ] Did not assume `@DataR2dbcTest` rolls back data after the method; used explicit cleanup/isolated database.
- [ ] Verified commit/rollback by **querying outside the transaction** after the operator finished.
- [ ] When multiple managers exist, matched datasources/connection factories properly.
- [ ] When failures depend on dialect/locking, used PostgreSQL/MySQL Testcontainers instead of H2 alone.
- [ ] Actually ran the test runner and checked reports before concluding runtime PASS.

## 20. Official References and Further Reading

- [Spring Framework 6.2 — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html): distinguishing thread-bound `PlatformTransactionManager` from `ReactiveTransactionManager`'s Reactor Context.
- [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `TransactionalOperator`, rollback on cancellation, operator and callback styles.
- [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `ConnectionFactory`, `DatabaseClient`, `R2dbcTransactionManager`, and subscriber-bound connections.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataR2dbcTest` non-transactional default, compared with JDBC/JPA slices.
- [Spring Boot 3.5 — SQL Databases / R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): R2DBC `ConnectionFactory`, R2DBC embedded H2, `DatabaseClient`.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): SQL schema initialization for JDBC/R2DBC.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): per-subscriber Context and `deferContextual`/`contextWrite`.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` assertions and testing publishers.

**Conclusion:** Spring Reactive transactions bind to **Reactor Context and a subscription**, rather than JDBC/JPA `ThreadLocal`. `@Transactional` covers the right scope only when wrapping a `Mono/Flux` executed through a proxy, or when code uses `TransactionalOperator` to compose all R2DBC work. Completion, errors, and cancellation determine commit/rollback; misplaced recovery can let **partial writes commit**. When testing, use `StepVerifier`, a real R2DBC database, post-transaction DB assertions, and explicit cleanup — especially since `@DataR2dbcTest` does not auto-roll back like `@DataJpaTest`.