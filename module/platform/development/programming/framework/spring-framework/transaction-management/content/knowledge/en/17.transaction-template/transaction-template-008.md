# Reusing TransactionTemplate and Avoiding Concurrent Mutation of Shared Configuration

## 1. Objective and Problem

`TransactionTemplate` is Spring Framework's callback-based programmatic transaction tool. A single instance can be reused across many calls, multiple services, and multiple threads. **Critical condition:** the instance's transaction configuration has been stably set before sharing and **is not mutated while threads are using it**.

This is an easily misunderstood point: Spring documentation says `TransactionTemplate` is **thread-safe** because it holds no per-transaction *conversational state*; however, it **does hold configuration state** mutable via setters such as `setPropagationBehavior(...)`, `setIsolationLevel(...)`, `setTimeout(...)`, and `setReadOnly(...)`. If one thread mutates the same instance for its request, another thread can accidentally use an unintended configuration.

This lesson helps you:

1. Distinguish **template configuration state** from **the transaction state of each `execute(...)` call**.
2. Understand why a once-configured `TransactionTemplate` can be a Spring singleton bean, injected into multiple services, and used concurrently.
3. Avoid the anti-pattern of calling `setTimeout`/`setPropagationBehavior`/`setIsolationLevel` right before every `execute` on a shared instance.
4. Create **separate, named, policy-stable templates** for `REQUIRED`, `REQUIRES_NEW`, read-only, or other needs.
5. If a request genuinely needs dynamic configuration, create a **new local template for that request/operation** instead of overwriting a singleton's configuration.
6. Understand that `TransactionStatus`, JDBC connections, and callback data belong to **each transaction/thread**, not state to store on the template or a shared singleton field.
7. Verify with a **Java 17+ / Spring Boot / Spring JDBC / H2 / Maven** project: multiple threads writing through one template, rollback-only in one call, and two distinct transaction policies.
8. Write integration tests confirming policies, isolation/timeouts, committed data, rollbacks, and safe reuse.

**Example scenario:** An API receives two kinds of requests: normal business writes (`REQUIRED`) and recording an event requiring an independent transaction (`REQUIRES_NEW`). Both requests run concurrently. If code uses **one singleton template** and changes propagation per request, the chance of one request accidentally using the other request's propagation is a correctness bug, not merely a performance bug.

## 2. What Does TransactionTemplate Actually Store?

`TransactionTemplate` belongs to package `org.springframework.transaction.support` and implements `TransactionOperations`. It combines:

- A reference to `PlatformTransactionManager`.
- **Transaction definition / configuration**: propagation, isolation, timeout, read-only, name.
- `execute(TransactionCallback<T>)` or `executeWithoutResult(Consumer<TransactionStatus>)` methods to execute a callback inside a transaction scope.

It **is not** an object holding a single `TransactionStatus` shared across all calls. On each `execute`, the manager decides whether to create a new transaction or join an existing one depending on context and propagation, and the callback receives the appropriate status.

```text
                TransactionTemplate singleton
               [manager + stable configuration]
                   /            |             \
                  /             |              \
Thread A: execute(...)   Thread B: execute(...)   Thread C: execute(...)
        |                        |                        |
Transaction scope A      Transaction scope B      Transaction scope C
JDBC resource A          JDBC resource B          JDBC resource C
        |                        |                        |
commit/rollback A       commit/rollback B       commit/rollback C
```

In the example, each thread calls from outside any transaction, so each `REQUIRED` call gets its own transaction. **Do not infer** scopes are always independent: if a callback is invoked inside an existing transaction, `REQUIRED` joins that transaction. Synchronous JDBC transaction context is normally bound to the thread; it does not automatically propagate to another thread created by an `ExecutorService`.

### Thread-Safe Does Not Mean "Every Setter Is Safe to Call Concurrently"

Spring clearly describes two coexisting properties:

- **No per-invocation conversational state:** one template can be shared to call `execute` in parallel.
- **Has configuration state:** attributes such as `timeout`, `propagation`, and `isolation` are read by invocations when creating a scope. If one thread modifies them while other threads are starting transactions, per-request policy behavior is not guaranteed.

Therefore, "TransactionTemplate is thread-safe" must be accurately understood as **safe for executing multiple transactions concurrently when configuration does not change during use**, not a promise that mutating setters concurrently is a safe programming practice.

## 3. Safe Approach: Configure Once and Reuse

Simple pattern inside a service:

```java
@Service
public class PaymentCommandService {
    private final TransactionTemplate transactionTemplate;
    private final JdbcTemplate jdbcTemplate;

    public PaymentCommandService(
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        this.transactionTemplate.setTimeout(20);
        this.jdbcTemplate = jdbcTemplate;
    }

    public void record(long id) {
        transactionTemplate.executeWithoutResult(status -> {
            jdbcTemplate.update(
                    "INSERT INTO payment_command(id) VALUES (?)",
                    id);
        });
    }
}
```

**This is an illustrative fragment**, omitting imports, schema, and main class. Key point to observe: call setters **only in the constructor before the instance is used/shared**; `record(...)` only calls `executeWithoutResult` and does not mutate configuration.

Specific values can be set once when creating a Spring `@Bean`, once in the service constructor, or in XML bean configuration. A Spring singleton bean is usually suitable when the template itself has a uniform policy.

**Benefit:** The service does not need to repeat template creation/configuration mapping on every request. However, do not exaggerate this into "a singleton `TransactionTemplate` uses the same connection". Acquiring/returning connections and transaction lifecycle belong to `PlatformTransactionManager`/`DataSource`/pool. Reusing a template **does not** turn multiple invocations into one physical transaction.

### Distinguishing `final` from Immutability

`private final TransactionTemplate template` prevents reassigning the template **reference**, yet `TransactionTemplate` still has setters. `final` **does not make the underlying object immutable**. What guarantees safety here is **the convention of never modifying configuration after initialization**, ensuring proper publication/wiring, and not allowing other threads to call setters during request flows.

Nor does a Spring singleton service automatically become thread-safe simply because fields are `final`: other mutable fields (such as `ArrayList`, counters, `TransactionStatus`, or `Connection`) still need dedicated concurrency design.

## 4. Anti-Pattern: Mutating a Singleton Template Right Before Every execute

### 4.1. Broken Code

```java
// WRONG if sharedTemplate is used by multiple threads.
public void process(boolean urgent, long id) {
    if (urgent) {
        sharedTemplate.setTimeout(1);
        sharedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    } else {
        sharedTemplate.setTimeout(30);
        sharedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
    }

    sharedTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
                "INSERT INTO job_event(id) VALUES (?)", id);
    });
}
```

This is a fragment **illustrating a design bug**, not to be deployed. Both setter calls mutate **the same configuration object**.

### 4.2. Interleaving Causes Wrong Policies

```text
Thread A: request urgent=true
  A1: sharedTemplate.setTimeout(1)
  A2: sharedTemplate.setPropagationBehavior(REQUIRES_NEW)
                    |
                    v (context switch)
Thread B: request urgent=false
  B1: sharedTemplate.setTimeout(30)
  B2: sharedTemplate.setPropagationBehavior(REQUIRED)
  B3: sharedTemplate.execute(callback B)
                    |
                    v (A resumes)
Thread A:
  A3: sharedTemplate.execute(callback A)
       -> A can receive timeout=30, propagation=REQUIRED
          instead of timeout=1, REQUIRES_NEW
```

Consequences can be severe:

- A transaction needing independence instead joins an outer transaction, then rolls back with outer.
- A transaction meant to be short gets a long timeout, holding locks longer.
- A write request runs while the template was just switched to `readOnly=true` by another request.
- A request expecting `SERIALIZABLE` reads has its isolation lowered by another request.

**Even when calling two setters back-to-back**, there is no atomic configuration transaction; another thread can observe a mixed set of properties. Code may run "fine" in sequential tests, with bugs surfacing only under concurrent load.

### 4.3. Why Is Adding synchronized Around Setters Not Enough?

If a lock only protects the setter block without **protecting the entire span from configuration until the manager creates the transaction**, another thread can still overwrite the configuration before `execute` reads it. Locking around the entire `execute` forces sequential execution, destroying concurrency and creating new problems (especially when callbacks wait on I/O). That is an unnecessary workaround for a design that has much better alternatives.

**Recommendation:** never use one template whose policy mutates per request; pick one of two options:

- **Effectively immutable templates**, one instance per predefined policy.
- **A new local template** inside each call when values truly depend on input and cannot be predefined as profiles.

Do not store `"currentRequestTimeout"` or `"currentTransactionStatus"` as mutable fields on a singleton service to avoid the same race.

## 5. Multiple Policies: Create Multiple Clearly Named TransactionTemplates

### 5.1. Creating Beans by Profile

```java
@Configuration
public class TransactionProfiles {

    @Bean("standardTemplate")
    TransactionTemplate standardTemplate(
            PlatformTransactionManager manager) {

        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);
        template.setName("standard");
        return template;
    }

    @Bean("independentTemplate")
    TransactionTemplate independentTemplate(
            PlatformTransactionManager manager) {

        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(10);
        template.setName("independent");
        return template;
    }
}
```

This is a fragment with Spring configuration structure, requiring imports and the complete application in section 9. The two templates are **two separate instances**; configuration finishes before they are handed to consumers.

- `standardTemplate`: joins current transaction if present, otherwise creates a new one; 30-second timeout when creating a new transaction.
- `independentTemplate`: always creates a new transaction (suspending outer when needed), 10-second timeout for its new transaction.
- Both use the same `PlatformTransactionManager` yet have **different transaction definitions**.
- Never call setters on these two beans after initialization.

### 5.2. Injecting Accurately When Multiple Beans Have the Same Type

```java
public EventWriter(
        @Qualifier("standardTemplate") TransactionTemplate standard,
        @Qualifier("independentTemplate") TransactionTemplate independent,
        JdbcTemplate jdbc) {
    this.standard = standard;
    this.independent = independent;
    this.jdbc = jdbc;
}
```

This is a constructor fragment; full code is in section 9. Use `@Qualifier` or an explicit identification mechanism since both beans have type `TransactionTemplate`.

Do not rely on parameter/field names for ambiguous resolution when multiple beans exist. When an application has multiple `PlatformTransactionManager`s, specify the exact manager per DataSource/tenant/resource rather than picking a template solely by business name while ignoring the transaction's underlying resource.

### 5.3. Is Sharing One Template for Both Reads and Writes Okay?

If reader and writer both accept the same policy, **injecting the same instance is fine**. `TransactionTemplate` stores no request data inside itself. However, if the reader actually needs `readOnly=true` or a different timeout, **do not mutate `standardTemplate` inside the reader**; create a separately configured `readOnlyTemplate`.

Example:

```java
@Bean("readOnlyTemplate")
TransactionTemplate readOnlyTemplate(PlatformTransactionManager manager) {
    TransactionTemplate template = new TransactionTemplate(manager);
    template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    template.setReadOnly(true);
    template.setTimeout(5);
    return template;
}
```

`readOnly` is typically a hint for the transaction manager/driver/database; it is not a guarantee that `INSERT` is impossible on every backend. If hard write restrictions are needed, use DB grants/appropriate transaction manager features rather than relying solely on the setter.

## 6. Dynamic Configuration: Local Template Instead of Mutating a Shared Bean

Some applications vary timeouts per tenant, SLA, or job type. When they cannot be grouped into a few fixed profiles, create a template **scoped to the call**:

```java
public void performWithCustomTimeout(int timeoutSeconds, long id) {
    if (timeoutSeconds <= 0 || timeoutSeconds > 120) {
        throw new IllegalArgumentException("Timeout outside allowed range");
    }

    TransactionTemplate local = new TransactionTemplate(transactionManager);
    local.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    local.setTimeout(timeoutSeconds);

    local.executeWithoutResult(status -> {
        jdbcTemplate.update(
                "INSERT INTO job_event(id) VALUES (?)", id);
    });
}
```

This is a fragment needing `transactionManager`, `jdbcTemplate`, fields/beans, and schema. Because `local` is **a new unshared instance**, request A cannot alter request B's timeout by calling setters on that object.

**Correct explanation:**

- `PlatformTransactionManager` is **shared**; each call does not create a new manager or DataSource.
- The template is a lightweight configuration object, so creating a fresh one in some dynamic flows is usually better than trading off correctness.
- Configure **only before `local.execute(...)`**; do not mutate a template currently executing.
- If `PROPAGATION_REQUIRED` joins an outer transaction, a new timeout on the local template **does not automatically override the deadline** of the outer physical transaction; getting an independent transaction requires `REQUIRES_NEW`, whose consistency implications must be evaluated.
- Always validate input timeouts and set a hard cap instead of letting clients send arbitrarily huge numbers.

### When Selecting Between Two Policies per Request

If there are exactly two profiles, choose between **two preconfigured instances**:

```java
TransactionTemplate template = urgent
        ? independentTemplate
        : standardTemplate;

template.executeWithoutResult(status -> {
    saveBusinessData();
});
```

Choosing a **reference** does not mutate configuration state. Illustrative fragment; requires declaring both templates and helper.

## 7. TransactionStatus, Callbacks, and Resources Must Not Be Shared Carelessly

One template is shared, yet **each call** receives its own `TransactionStatus`:

```java
sharedTemplate.executeWithoutResult(status -> {
    // status belongs to this execute invocation.
    jdbcTemplate.update(
            "INSERT INTO job_event(id) VALUES (?)", uniqueId);
});
```

Do not write:

```java
// WRONG: singleton service holding mutable state of a running request.
private TransactionStatus currentStatus;

public void process(long id) {
    sharedTemplate.executeWithoutResult(status -> {
        currentStatus = status; // Another thread will overwrite this field.
        save(id);
    });
}
```

In synchronous transactions, thread-bound JDBC connections and synchronization are managed by Spring. Do not place `TransactionStatus`, `Connection`, `EntityManager`, or objects containing transaction-bound state into shared fields and use them from other threads. Once the callback finishes, `status` is no longer an open context for reuse.

### A Status Is Not a Transaction Manager

`TransactionStatus` holds information for **one scope** such as `isNewTransaction()`, `setRollbackOnly()`, and completion state. It is not a connection pool handle to pass across threads. The callback should finish cleanly at the `execute(...)` boundary.

Inside `execute(...)`:

- If the callback returns normally and the scope is allowed to commit, the template calls the transaction manager to complete/commit the scope.
- If the callback throws an unchecked exception or error, the Spring template rolls back per contract and propagates the error to the caller.
- If a business error is caught inside the callback yet rollback is still needed, use `status.setRollbackOnly()`.
- `setRollbackOnly()` only affects the current transaction/scope and **does not stick a permanent flag onto the shared TransactionTemplate**. A later call through the same template can commit normally.

**That is the key difference between shared configuration and per-call transaction state.**

### When Using ExecutorService, @Async, or CompletableFuture

Another thread does not automatically inherit the originating thread's JDBC transaction. If each job needs its own transaction, call `sharedTemplate.execute(...)` **inside the job's own thread**. Do not start a transaction on thread A and pass `status`/`Connection` to thread B. If a task comprises multiple writes that must commit atomically together, run all of them in one transaction on a suitable execution context or design distributed coordination; do not expect a singleton template to create a shared transaction across threads.

## 8. Propagation, Timeout, Isolation: Configuration Still Has Semantic Limits

### 8.1. REQUIRED Does Not Mean a Separate Transaction Every Time

```text
Caller has no transaction
  -> standardTemplate.execute(...)
     -> creates new physical transaction, commits/rolls back at end of callback

Caller already has outer transaction T
  -> standardTemplate.execute(...)
     -> joins T, does not physically commit independently
```

If an audit entry must persist even when outer rolls back, `REQUIRED` is not enough. You can use `REQUIRES_NEW` in a separate template — though independent commits carry business and resource consequences.

### 8.2. REQUIRES_NEW Is a Different Physical Transaction

`REQUIRES_NEW` suspends the outer transaction when needed and opens a new transaction. Inner can commit while outer rolls back later. This clearly illustrates why **you must not randomly switch propagation at runtime on a shared template**: one wrong choice can make audit/side-effect data disappear or persist unexpectedly.

With JDBC, the new inner transaction may need an extra connection from the pool **while outer is still holding a connection**. Consider pool capacity, concurrency, and lock ordering to avoid situations where many threads hold outer connections and all wait for connections for `REQUIRES_NEW`.

### 8.3. Isolation and Timeout Do Not Automatically Override an Outer Transaction

Suppose outer is at `READ_COMMITTED` with a 30-second timeout; inner invokes a `REQUIRED` template configured with `SERIALIZABLE` and a 1-second timeout. If inner merely joins the already-open transaction, the template's new isolation/timeout **usually do not alter the running physical transaction**. You can configure `validateExistingTransaction=true` on the manager to reject isolation mismatches in certain cases, though it still does not turn inner into a new transaction.

Therefore, having two templates does not automatically resolve policy conflicts if the call pattern and propagation are wrong. Write integration tests against the application's **actual transaction boundaries**.

### 8.4. Read-Only and Name

`setReadOnly(true)` is treated as a hint/metadata for the manager and resource. `setName("...")` sets the transaction definition name for logging/monitoring where supported. Both are **configuration state**, so they must also be set **before sharing**, never reassigned per request.

Do not set a request ID or personal info via `template.setName(requestId)` on a shared singleton. If per-request tracing is needed, use the thread's MDC/trace context or suitable instrumentation rather than mutating the transaction definition.

## 9. Complete Java 17+ Project: Two Fixed Templates Shared Across Multiple Threads

The hands-on application uses **Spring Boot 3.5.6**, **Java 17+**, **Spring JDBC**, **H2**, and **Maven**. Fixed release versions are chosen so copying the code is reproducible; for production, update dependencies per your project's security and compatibility policy.

Verification goals:

1. Bean `standardTemplate` is injected into **two services** and used across multiple calls.
2. One callback marking rollback-only does not "taint" the template for subsequent callbacks.
3. A second template `independentTemplate` has an explicit `REQUIRES_NEW` policy without changing `standardTemplate`'s policy.
4. Four jobs run concurrently through the shared template, each committing its own row ID; no configuration race occurs.
5. An outer transaction rolls back while an inner `REQUIRES_NEW` committed; distinguishing the two transaction profiles.
6. Tests verify bean identity, configuration values, and data outcomes.

### 9.1. File Structure

```text
shared-transaction-template-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SharedTemplateApplication.java
    │   │   ├── TemplateConfig.java
    │   │   ├── RecordWriter.java
    │   │   └── RecordReader.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/demo/
        └── SharedTemplateIntegrationTest.java
```

No manual table creation is needed in the runner/test: Spring Boot executes `schema.sql` on embedded H2 when the application context initializes, before `CommandLineRunner` callbacks and test methods.

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>shared-transaction-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

JDBC, H2, JUnit 5, and Spring TestContext dependencies are managed by the Spring Boot BOM. `TransactionTemplate` is available from the Spring transaction dependency brought in by the JDBC starter.

### 9.3. application.properties and schema.sql

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:shared_templates;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=8
spring.sql.init.mode=always
spring.main.banner-mode=off
app.demo.enabled=true
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_record (
    id BIGINT PRIMARY KEY,
    origin VARCHAR(80) NOT NULL
);
```

The H2 in-memory database named `shared_templates` lets multiple connections in the same JVM see one database. A pool of 8 connections serves four concurrent jobs and `REQUIRES_NEW` transactions while outer holds a connection. Do not equate a singleton template with a singleton JDBC connection: each new transaction gets a connection per manager/pool.

### 9.4. TemplateConfig.java — Configure Before Sharing

**`src/main/java/demo/TemplateConfig.java`**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TemplateConfig {

    @Bean("standardTemplate")
    public TransactionTemplate standardTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);
        template.setName("standard");
        return template;
    }

    @Bean("independentTemplate")
    public TransactionTemplate independentTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(10);
        template.setName("independent");
        return template;
    }
}
```

Both Spring beans are **singleton** by default, yet they are two distinct objects. No setter is ever called on them inside runtime request code. This is the configuration boundary you control to avoid race conditions.

Both have `Isolation.READ_COMMITTED` to highlight differences primarily in **propagation** and **timeout**. If production requires `SERIALIZABLE` or another isolation level, verify backend/driver support and configure it as a new profile; do not mutate a profile serving concurrent traffic.

### 9.5. RecordWriter.java — Reusing Templates, Per-Call Rollback-Only, and REQUIRES_NEW

**`src/main/java/demo/RecordWriter.java`**

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RecordWriter {
    private final TransactionTemplate standard;
    private final TransactionTemplate independent;
    private final JdbcTemplate jdbc;

    public RecordWriter(
            @Qualifier("standardTemplate") TransactionTemplate standard,
            @Qualifier("independentTemplate") TransactionTemplate independent,
            JdbcTemplate jdbc) {
        this.standard = standard;
        this.independent = independent;
        this.jdbc = jdbc;
    }

    public void save(long id, String origin) {
        standard.executeWithoutResult(status ->
                insert(id, origin));
    }

    public void rejectAndRollback(long id) {
        standard.executeWithoutResult(status -> {
            insert(id, "rejected");
            status.setRollbackOnly();
        });
    }

    public void saveIndependent(long id) {
        independent.executeWithoutResult(status ->
                insert(id, "independent"));
    }

    public void outerFailsAfterIndependentWrite(
            long outerId, long independentId) {
        standard.executeWithoutResult(status -> {
            insert(outerId, "outer");

            // Method in the same bean, yet the transaction is created
            // by independent.execute(...) — not relying on AOP.
            saveIndependent(independentId);

            throw new IllegalStateException("outer failed");
        });
    }

    private void insert(long id, String origin) {
        jdbc.update(
                "INSERT INTO tx_record(id, origin) VALUES (?, ?)",
                id, origin);
    }
}
```

Scenarios:

- `save(...)` uses the shared `standard` template with `REQUIRED`. When the caller has no transaction, each `execute` creates its own transaction; multiple threads can call it concurrently.
- `rejectAndRollback(...)` calls `status.setRollbackOnly()` **on this callback's status**. It does not alter `standard`'s configuration, so other `save(...)` calls do not roll back with it.
- `saveIndependent(...)` uses a **different** template to create a `REQUIRES_NEW` physical transaction.
- `outerFailsAfterIndependentWrite(...)` opens an outer transaction via `standard`, writes the outer row, and then calls `saveIndependent`. Inner commits independently; outer throws `IllegalStateException` and rolls back. `standard` never needs to be mutated to `REQUIRES_NEW`.

**Note on self-invocation:** Calling `saveIndependent(...)` in the same class does not suffer from `this.method()` bypassing `@Transactional`, because the transaction boundary here is **the explicit `independent.execute(...)` call**, not an AOP annotation on the called method. If switching code to declarative `@Transactional`, proxy/self-invocation must be handled differently.

## 9.6. RecordReader.java — Injecting One Template into a Second Bean

**`src/main/java/demo/RecordReader.java`**

```java
package demo;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RecordReader {
    private final TransactionTemplate standard;
    private final JdbcTemplate jdbc;

    public RecordReader(
            @Qualifier("standardTemplate") TransactionTemplate standard,
            JdbcTemplate jdbc) {
        this.standard = standard;
        this.jdbc = jdbc;
    }

    public List<Long> ids(long fromInclusive, long toInclusive) {
        return standard.execute(status ->
                jdbc.queryForList(
                        "SELECT id FROM tx_record "
                                + "WHERE id BETWEEN ? AND ? ORDER BY id",
                        Long.class,
                        fromInclusive, toInclusive));
    }
}
```

`RecordReader` and `RecordWriter` both inject **the bean named `standardTemplate`**. Under the default singleton scope, that is **the same object**; you do not need to create a copy for each service if the policy is identical.

In the demo, the standard template does not set `readOnly=true` because it serves both reader/writer. In a real application, if reads have their own transaction policy (read-only, short timeout, etc.), create a third `readOnlyTemplate` instead of calling `standard.setReadOnly(true)` before the query and resetting it afterward.

### 9.7. SharedTemplateApplication.java — Sequential and Concurrent Runs

**`src/main/java/demo/SharedTemplateApplication.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SharedTemplateApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedTemplateApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.demo.enabled",
            havingValue = "true",
            matchIfMissing = true)
    CommandLineRunner demonstrate(
            RecordWriter writer,
            RecordReader reader) {
        return args -> {
            writer.save(1L, "single");
            writer.rejectAndRollback(2L);
            writer.saveIndependent(3L);

            try {
                writer.outerFailsAfterIndependentWrite(4L, 5L);
            } catch (IllegalStateException ex) {
                System.out.println("outer failure: " + ex.getMessage());
            }

            ExecutorService pool = Executors.newFixedThreadPool(4);
            try {
                List<Future<?>> tasks = new ArrayList<>();
                for (long id = 10L; id <= 13L; id++) {
                    long recordId = id;
                    tasks.add(pool.submit(
                            () -> writer.save(recordId, "parallel")));
                }
                for (Future<?> task : tasks) {
                    task.get(10, TimeUnit.SECONDS);
                }
            } finally {
                pool.shutdownNow();
            }

            System.out.println("standard rows: " + reader.ids(1L, 1L));
            System.out.println("rollback rows: " + reader.ids(2L, 2L));
            System.out.println("independent rows: " + reader.ids(3L, 3L));
            System.out.println("outer rows: " + reader.ids(4L, 4L));
            System.out.println("inner rows: " + reader.ids(5L, 5L));
            System.out.println("parallel rows: " + reader.ids(10L, 13L));
        };
    }
}
```

In `CommandLineRunner`, there is no outer transaction, so each `writer.save(...)` has its own `REQUIRED` scope. `ExecutorService` creates four threads; each thread enters **the same `RecordWriter` instance and the same `standardTemplate`**, yet the transaction manager assigns appropriate per-thread transaction resources.

**Why does `pool.submit(...)` not make all four jobs share one transaction?** Spring JDBC transaction context is bound to the thread. A singleton template **does not** propagate transaction context from the main thread to worker threads. Thus they are four independent transactions in this lab, even though the configuration is reused.

The code awaits `Future.get(...)` for all jobs so the SELECTs only run **after all callbacks and transactions have completed**. Do not query row counts while a job is still running, as you could observe mid-flight state or race with commit timing.

### 9.8. Running the Program

In the `shared-transaction-template-demo` directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Output lines printed **by the program itself** (ignoring Spring/Maven logs):

```text
outer failure: outer failed
standard rows: [1]
rollback rows: []
independent rows: [3]
outer rows: []
inner rows: [5]
parallel rows: [10, 11, 12, 13]
```

Explanation:

| Test | Policy | Result |
| --- | --- | --- |
| `save(1)` | Shared `REQUIRED` | Commits row `1` |
| `rejectAndRollback(2)` | Shared `REQUIRED` + per-call `setRollbackOnly` | No row `2` |
| `saveIndependent(3)` | `REQUIRES_NEW` template | Commits row `3` |
| `outerFailsAfterIndependentWrite(4,5)` | Outer `REQUIRED` + inner `REQUIRES_NEW` | Row `4` rolls back, row `5` remains |
| Four `save(10..13)` jobs | **Same standard template**, per-thread transactions | Commits all rows `[10,11,12,13]` |

This result illustrates two principles: **the same configuration can be reused concurrently**, and **each transaction callback has its own state**. It is not a test proving that mutating setters is safe; on the contrary, the demo **has no setters in the request path**.

## 10. Integration Test: Bean Identity, Policy, and Concurrency

Create **`src/test/java/demo/SharedTemplateIntegrationTest.java`**:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = "app.demo.enabled=false")
class SharedTemplateIntegrationTest {
    @Autowired
    @Qualifier("standardTemplate")
    private TransactionTemplate standard;

    @Autowired
    @Qualifier("independentTemplate")
    private TransactionTemplate independent;

    @Autowired
    private RecordWriter writer;

    @Autowired
    private RecordReader reader;

    @Test
    void policyBeansAreDistinctAndConfiguredOnce() {
        assertNotSame(standard, independent);

        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW,
                independent.getPropagationBehavior());

        assertEquals(
                TransactionDefinition.ISOLATION_READ_COMMITTED,
                standard.getIsolationLevel());
        assertEquals(
                TransactionDefinition.ISOLATION_READ_COMMITTED,
                independent.getIsolationLevel());

        assertEquals(30, standard.getTimeout());
        assertEquals(10, independent.getTimeout());
    }

    @Test
    void rollbackMarkerIsPerInvocationNotOnTemplate() {
        writer.rejectAndRollback(101L);
        writer.save(102L, "after-rollback");

        assertEquals(List.of(), reader.ids(101L, 101L));
        assertEquals(List.of(102L), reader.ids(102L, 102L));
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
    }

    @Test
    void requiresNewCommitsIndependentlyOfOuterRollback() {
        assertThrows(IllegalStateException.class,
                () -> writer.outerFailsAfterIndependentWrite(201L, 202L));

        assertEquals(List.of(), reader.ids(201L, 201L));
        assertEquals(List.of(202L), reader.ids(202L, 202L));
    }

    @Test
    void manyThreadsCanReuseOneStableTemplate() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (long id = 301L; id <= 308L; id++) {
                long recordId = id;
                tasks.add(pool.submit(
                        () -> writer.save(recordId, "parallel-test")));
            }
            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
        }

        assertEquals(
                List.of(301L, 302L, 303L, 304L,
                        305L, 306L, 307L, 308L),
                reader.ids(301L, 308L));

        assertEquals(30, standard.getTimeout());
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
    }
}
```

Run:

```bash
mvn test
```

**Expected:** all four tests pass once dependencies are downloaded and the project structure is created properly.

### Why Disable the Runner in Tests?

`@SpringBootTest(properties = "app.demo.enabled=false")` prevents the demo `CommandLineRunner` from writing IDs 1–13 when the test context starts. The `tx_record` table is still created by `schema.sql`. Tests use separate IDs (101–308) to avoid colliding with the demo, without adding unnecessary outer transactions.

### Why Not Annotate the Whole Test with @Transactional?

Spring TestContext can open a test-managed transaction for tests marked `@Transactional`. Then `REQUIRED` `standardTemplate` would join the test's transaction, changing commit timing and rollback boundaries. In particular, the `REQUIRES_NEW` test needs to clearly observe the outer transaction created by `writer`, rather than being accidentally wrapped by a test transaction. The tests above have **no `@Transactional`** on class or methods.

### Why Not Write a Test Mutating the Template Concurrently?

Because the lesson is **do not do that**, you should not try to write a test expecting a race condition to reproduce reliably. Scheduler-driven races are typically non-deterministic: a test might pass thousands of times and fail only under load. Instead, verify that template configuration **remains unchanged** across invocations and there are no setters in request-handling paths. To prove bugs, use code review/static analysis or check bean design and sharing conditions.

## 11. Spring Patterns for Larger Projects

### 11.1. Singleton @Bean Is the Suitable Default Choice

A `@Bean` created by `@Configuration` is singleton by default in the Spring container. That lets one clear policy be reused across multiple services without duplicating configuration. Under dependency injection, consumers receive the same instance when injecting the same bean name.

**A singleton is not strictly mandatory:** each service can instantiate its own fixed `TransactionTemplate` in its constructor using the same manager. What matters is not forcing a singleton at all costs, but **never mutating configuration shared across concurrent calls**.

### 11.2. When There Are Multiple Transaction Managers

In systems with multiple `DataSource`s, pin both the manager and the policy of each template:

```java
@Bean("billingTemplate")
TransactionTemplate billingTemplate(
        @Qualifier("billingTransactionManager")
        PlatformTransactionManager manager) {

    TransactionTemplate template = new TransactionTemplate(manager);
    template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    template.setTimeout(15);
    return template;
}
```

This is a configuration fragment; the `billingTransactionManager` bean must be declared beforehand. Do not call `template.setTransactionManager(...)` on a shared instance across tenants/requests. A save/rollback on DataSource A does not automatically control SQL written on DataSource B.

### 11.3. When Policies Depend on Tenant or Job Type

There are three strategies to consider:

| Need | Choice | Avoid |
| --- | --- | --- |
| One shared policy | One shared template configured once | Calling setters per request |
| A few fixed policies | One named bean per policy; choose per request | Changing propagation/timeout on a single bean |
| Many dynamic values | Create a local `TransactionTemplate` per operation | Putting `TransactionStatus` in a singleton field |
| Multiple transaction managers | Create templates bound to the matching manager | Swapping managers on a shared object |
| Multiple threads | Each thread calls `execute` on a stable template | Passing the same `Connection`/`TransactionStatus` across threads |
| Reactive programming | Use `TransactionalOperator`/`ReactiveTransactionManager` | Using JDBC thread-bound assumptions to reason about reactive semantics |

If caching templates by policy is needed, consider a key including manager, propagation, isolation, timeout, read-only, and transaction name; every instance in the cache must still have a stable configuration after publication. Do not turn a cache into a place that mutates one shared object just to save a few allocations.

### 11.4. Expressing Policy in Code Structure

Name beans and wrapper services by **business purpose** rather than generic names like `template1` and `template2`. For example:

- `orderWriteTemplate` for standard order transactions.
- `auditIndependentTemplate` for intentionally designed independent audits.
- `reportReadOnlyTemplate` for reporting queries with a controlled timeout.

Use `TransactionDefinition.PROPAGATION_REQUIRED` and `PROPAGATION_REQUIRES_NEW` constants rather than memorizing magic numbers 0 and 3. Any policy change should come with regression tests verifying transactional outcomes, because differing propagation can affect committed data.

## 12. Common Misconceptions

### 12.1. "Thread-safe" Means You Can Call setTimeout from Multiple Threads

**False.** Thread safety in Spring's documentation refers to reusing the template when executing callbacks, not granting permission to mutate configuration state arbitrarily in concurrent flows. A setter run by thread A can change thread B's policy.

### 12.2. Same Template Means Same JDBC Connection

**False.** The template holds the manager and transaction definition. Connections are managed by the transaction manager and DataSource per transaction/thread. Sharing a template does not automatically share connection/transaction state.

### 12.3. private final Already Makes Config Immutable

**False.** `final` only fixes the reference; it does not prevent `template.setTimeout(...)`. You need the convention of finishing configuration before publishing/accepting requests and not exposing mutating APIs through the service.

### 12.4. Creating a New Template Each Time Creates a New DataSource

**False.** `new TransactionTemplate(existingManager)` only creates a new wrapper/definition object, still using the injected manager. Never create a new `DataSourceTransactionManager` per request just to change a timeout.

### 12.5. Switching to REQUIRES_NEW on a Shared Template for "Just This Request" Is Harmless

**False.** The setter mutates a shared object, potentially affecting other requests and altering their commit/rollback boundaries. Create fixed profiles or a local instance.

### 12.6. Every Callback Has Its Own TransactionStatus, So Mutating Configuration Is Safe

**False.** Per-callback status and shared configuration are two different kinds of state. Even though status is independent, the manager still reads the definition from the template when starting the scope; a concurrently modified definition can lead to wrong behavior.

### 12.7. A Template Used Inside @Async Continues the Caller's Transaction

**False in the standard thread-bound JDBC model.** Worker threads normally do not carry the caller's context. An `execute` inside the worker creates/joins *the worker's* transaction, not automatically joining the calling thread's transaction.

### 12.8. To Make It Read-Only, Call setReadOnly(true), Query, Then Call setReadOnly(false)

**False if the template is shared.** That mutates configuration during concurrent runtime. Use a separate read-only template. Additionally, `readOnly` does not strictly block write SQL on every database.

### 12.9. A Callback Marking Rollback-Only Makes the Template Permanently Roll Back

**False.** `status.setRollbackOnly()` affects the current scope without modifying the template. Later callbacks in independent transactions can commit; the integration test above verifies this.

### 12.10. REQUIRES_NEW Is Always Better Than REQUIRED to Avoid Outer Interference

**Incorrect.** `REQUIRES_NEW` creates a separate physical transaction, which can commit data out of sync with outer and increase connection pool demand. Choose propagation by business atomicity, not merely to dodge rollback exceptions.

### 12.11. A Short Timeout on Inner REQUIRED Always Applies

**False if inner joins an existing outer transaction.** A transaction definition's timeout normally applies when creating a new physical transaction; inner `REQUIRED` does not automatically reset outer's deadline.

### 12.12. Passing Concurrent Tests Are Enough to Prove Code Has No Races

**No.** The scheduler may not hit the problematic interleaving in tests. Proper design means never mutating shared configuration, combined with tests verifying data and operational monitoring under heavy load.

## 13. Pre-Production Review Checklist

- [ ] Shared `TransactionTemplate`s are **initialized and configured once**, before serving concurrent requests.
- [ ] No calls to `setTimeout`, `setIsolationLevel`, `setPropagationBehavior`, `setReadOnly`, `setName`, or `setTransactionManager` on singleton templates inside runtime request methods.
- [ ] Different transaction profiles use **separate template instances**; `@Qualifier` specifies which bean to use.
- [ ] Templates use the right `PlatformTransactionManager`/`DataSource`.
- [ ] Dynamic values are validated and configured only on an unpublished **local instance**.
- [ ] `TransactionStatus`, JDBC `Connection`, and mutable request state are never stored in shared fields.
- [ ] Rollback-only callbacks only mark the specific `status` passed to that invocation.
- [ ] Dedicated tests cover `REQUIRED` joining outer and `REQUIRES_NEW` committing independently if business logic uses both.
- [ ] Developers understand that an inner participating transaction's timeout/isolation does not automatically override an outer physical transaction.
- [ ] Thread pools, connection pools, timeouts, and lock contention are properly sized/monitored.
- [ ] Integration tests run concurrently and inspect data **after transactions finish**, not just counting callback invocations.
- [ ] Code does not assume Java thread interruption automatically cancels JDBC transactions/SQL.
- [ ] With multiple tenants/managers, policies and resources are determined before use; managers are not swapped on shared templates.
- [ ] For reactive code, thread-local JDBC models are not applied to `TransactionalOperator`.
- [ ] `REQUIRES_NEW` is used only when independent commits and the consequences of outer rollback are acceptable.

## 14. Questions and Exercises

**Exercise 1.** Two requests both call `sharedTemplate.execute(...)` on two threads. The template was configured once in the constructor, with no setters called afterward. Is it necessary to create one template per request?

**Answer:** No. Per Spring's contract, a template can be reused concurrently when its configuration is stable. Each `execute` receives transaction status/resources appropriate to its context.

**Exercise 2.** Thread A calls `shared.setTimeout(1)`; thread B calls `shared.setTimeout(30)` right before `execute`. Why can the program still be wrong even if both threads use `try/catch` properly?

**Answer:** Both are modifying **the same configuration**. The transaction definition used by the manager may carry the other thread's timeout. `try/catch` does not isolate shared mutable configuration.

**Exercise 3.** Is `private final TransactionTemplate template` enough to disable setters?

**Answer:** No. `final` only locks reference reassignment; the object itself remains mutable. You must finish configuration before sharing and never mutate afterward.

**Exercise 4.** One callback calls `status.setRollbackOnly()`, then another request uses the same template and commits successfully. Does that violate thread safety?

**Answer:** No. `TransactionStatus` is per-invocation state; rollback-only is not written into the template's configuration, so other requests do not automatically roll back with it.

**Exercise 5.** You need `REQUIRED` for normal operations and `REQUIRES_NEW` for independent audits. Which is safer: calling `setPropagationBehavior` each time or creating two fixed templates?

**Answer:** Create **two instances**, configure each once, and select by purpose. Never mutate one shared object in a concurrent processing path.

**Exercise 6.** While the caller has an open outer transaction, a `REQUIRED` template with a 1-second timeout is called. Is that timeout guaranteed to change outer's deadline?

**Answer:** No. When joining an existing physical transaction, the new definition usually does not alter outer's timeout/isolation. Design the policy at the right transaction boundary.

**Exercise 7.** You want timeouts varying from 1 to 120 seconds depending on the job. How should you do this?

**Answer:** Validate the input and create a local `new TransactionTemplate(existingManager)`, set the timeout before `execute`, and never publish the instance to shared state. If the number of policies is finite, you can pre-create named templates.

**Exercise 8.** Why shouldn't you put `TransactionStatus` in a singleton service field for convenient tracking of the running transaction?

**Answer:** Concurrent requests would overwrite/misread each other's status. The status object and context belong to one transaction scope; keep them inside the callback or an appropriate scope, never shared cross-thread.

**Exercise 9.** Two services both inject `@Qualifier("standardTemplate")`. Why does this not automatically make them share one physical transaction?

**Answer:** The template bean is only a configuration/coordination object. Physical transactions are created/joined by the manager according to context at each `execute`. A singleton template does not mean a singleton transaction.

**Exercise 10.** In the project, outer `REQUIRED` writes row 4, inner `REQUIRES_NEW` writes row 5, and outer throws an error. Which result is right and why?

**Answer:** Row 4 rolls back, while row 5 committed independently and remains. Two different profiles alter transaction boundaries; that is why you must choose explicit policies rather than flipping setters on a shared template.

**Exercise 11.** Should you call `template.setName(requestId)` on a singleton to log each request's ID?

**Answer:** No. That mutates configuration state. Use tracing/MDC or a per-request mechanism that does not touch the shared template's policy.

**Exercise 12.** If concurrent tests pass 1,000 times in a row, can you skip code review for mutations on templates?

**Answer:** No. Concurrency bugs depend on interleaving; passing tests do not prove absence of races. Maintain the invariant: **never mutate shared template configuration during concurrent runtime**.

## 15. Official Documentation

- Spring Framework — **Programmatic Transaction Management**: the `Using the TransactionTemplate` and `Specifying Transaction Settings` sections state clearly that instances can be shared and are thread-safe for execution, yet hold configuration state so distinct policies require separate templates: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework Javadoc — `TransactionTemplate`: constructors, `execute`, transaction manager, and callback lifecycle: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc — `TransactionOperations` / `executeWithoutResult`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework Javadoc — `DefaultTransactionDefinition` and setters: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework — **Transaction Propagation** and `REQUIRED` / `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **JDBC Connections / DataSourceTransactionManager**: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Boot 3.5.6 release (version used in the lab): https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now

**Takeaway:** Reusing one fixed `TransactionTemplate` across many calls or multiple threads is valid because it holds no per-callback transaction state. However, **do not mutate setters on a shared instance**. Configuration is shared mutable state; `TransactionStatus`, transaction-bound connections, and rollback/commit outcomes are per-scope. If policies differ, create **separate templates**; if configuration is truly dynamic, create a **local template** for that operation. Verify behavior at the actual transaction boundary rather than inferring from bean names or sequential test runs.