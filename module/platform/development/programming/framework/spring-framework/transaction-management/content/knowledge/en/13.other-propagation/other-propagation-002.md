# MANDATORY and Requiring the Caller to Already Have an Open Transaction

> **Topic:** Spring Framework — Transaction Management. **Knowledge group:** Other Propagation. This article accurately explains `Propagation.MANDATORY`: the method **must** be called inside an existing transaction and **does not** create a new transaction when none exists; when a transaction already exists, it **joins the same physical transaction** and shares the commit/rollback outcome. The article includes a Java 17, Spring Boot 3.5.7, Spring JDBC, and H2 example for direct verification.

## 1. What is MANDATORY?

In Spring, `@Transactional` lets you configure propagation — how a method participates in, initiates, or rejects an existing transaction. `Propagation.MANDATORY` expresses a **mandatory requirement on the caller**: the caller must place the call inside a compatible transaction **before** reaching this method.

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.MANDATORY)
public void reserveStock(long productId, int quantity) {
    // This code requires an existing transaction.
}
```

When the call **actually passes through the Spring transaction interceptor**:

- **A compatible transaction already exists:** Spring lets the method join that transaction. The method does not create a new physical transaction; the final commit/rollback is decided by the outer transaction.
- **No transaction exists:** Spring rejects the call and typically throws `org.springframework.transaction.IllegalTransactionStateException` **before executing the method body**.
- **Annotated but does not pass through a proxy** (in Spring AOP proxy mode): the MANDATORY check may **not happen at all**, because the interceptor is never invoked.

The Spring API documentation describes `MANDATORY` as: support a current transaction, throw an exception if none exists. This is a **mandatory contract**, unlike `REQUIRED` — which opens a transaction itself when one is missing.

### The right mindset

If repository/service layer A has an operation that may only run as part of a larger business process, we want **the caller to be responsible for opening the transaction**. `MANDATORY` turns that expectation into a check capable of catching structural mistakes at runtime, instead of accidentally running auto-committed SQL and only discovering corrupt data later.

**However:** `MANDATORY` does not verify "the transaction must have been created by specific method X" or "the transaction must protect every database properly". It only checks whether an **existing transaction exists according to the selected transaction manager**. Guaranteeing caller identity, database scope, or business invariants must be controlled through design, authorization, transaction manager/resource wiring, and testing.

## 2. Distinguishing MANDATORY from REQUIRED and REQUIRES_NEW

| Propagation of called method | When no transaction exists | When transaction `T1` already exists | Can commit independently before outer? |
| --- | --- | --- | --- |
| `REQUIRED` — default | Creates a new transaction | Joins `T1` | No, when joining T1 |
| **`MANDATORY`** | **Throws an error, method body does not run** | **Joins `T1`** | **No** |
| `REQUIRES_NEW` | Creates a new transaction | Suspends T1 and creates separate `T2` | Yes, because T2 is independent |
| `SUPPORTS` | Runs without a transaction | Joins T1 | Does not create one |
| `NEVER` | Runs without a transaction | Throws an error if T1 exists | No |
| `NOT_SUPPORTED` | Runs without a transaction | Suspends T1, runs outside transaction | No |

A common misconception: seeing the word **MANDATORY** and thinking it "forces Spring to create a transaction". That is wrong. MANDATORY **forces the caller to bring a transaction in**; if none exists, it **rejects** rather than creating one.

Two-service example:

```java
@Service
class CheckoutService {
    private final InventoryService inventory;

    CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional // REQUIRED, starts T1 when no tx exists.
    public void checkout() {
        inventory.reserve(); // Call another bean via Spring proxy.
    }
}

@Service
class InventoryService {
    @Transactional(propagation = Propagation.MANDATORY)
    public void reserve() {
        // Joins T1 opened by checkout().
    }
}
```

This is an **illustrative snippet**; it requires importing `org.springframework.stereotype.Service` and the transaction annotations, and is not a standalone program. When `checkout` is called **through a proxy** from a caller without a transaction, `checkout` opens T1 and `reserve` joins that same T1. **There is no T2.**

Conversely, if a controller or job calls `InventoryService.reserve()` **directly** through its proxy without a transaction, MANDATORY will reject it before any database operation occurs.

## 3. Logical transaction scope and physical transaction

To understand commit/rollback with MANDATORY, distinguish:

- **Physical transaction:** the real transaction of a resource such as a JDBC connection/DB transaction, with begin, commit, and rollback.
- **Logical transaction scope:** the transaction scope handled by the Spring interceptor for a transactional method; it carries metadata, rollback rules, and can participate in an already opened physical transaction.

An outer `@Transactional(REQUIRED)` method and an intercepted inner `@Transactional(MANDATORY)` method create **two logical scopes** but usually only **one physical transaction T1**.

```text
Controller / Runner
    |
    v
OrderService.placeOrder()            @Transactional(REQUIRED)
    |                                      |
    |                          logical scope OUTER
    |                          BEGIN physical transaction T1
    |
    +--> InventoryService.reserve()   @Transactional(MANDATORY)
    |         |                            |
    |         |                 logical scope INNER
    |         |                 REQUIRE existing transaction
    |         |                 JOIN physical transaction T1
    |         +---- SQL on same T1 --------> |
    |
    +--------- SQL on T1 ------------------> |
    |
    v
Outer ends: COMMIT or ROLLBACK physical transaction T1
```

**MANDATORY does not commit T1 when the inner method returns.** The inner method finishing successfully simply means the inner work has returned to the outer scope. If the outer method later throws a `RuntimeException` and rolls back T1, the changes performed by the inner method inside T1 also roll back.

This fits business steps that must be **atomic together**, such as writing an order and deducting inventory on the same datasource; however, if the inner step truly needs to commit independently to preserve data when the outer transaction rolls back, `MANDATORY` does not meet that requirement, and an intentional `REQUIRES_NEW` boundary may be more suitable.

## 4. What happens when there is no transaction?

Consider the method:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void writeAuditRow() {
    jdbc.update("INSERT INTO audit_log(id) VALUES (1)");
}
```

This is a **snippet**: `jdbc` is a `JdbcTemplate` injected into a bean with transaction advice. If called directly **through a Spring proxy** when no transaction exists:

1. The caller enters the transaction interceptor.
2. Spring resolves the corresponding transaction manager and transaction attribute.
3. The manager sees `MANDATORY` propagation but no compatible existing transaction.
4. It throws `IllegalTransactionStateException`. **The method body does not execute**, so the `INSERT` statement does not run.
5. There is no commit or rollback for this method, because **no new transaction was started**.

This error is usually a **signal of a poorly designed transaction boundary**, not a reason to automatically change `MANDATORY` to `REQUIRED` everywhere.

### Can you use try/catch?

```java
try {
    inventoryService.reserve();
} catch (IllegalTransactionStateException ex) {
    // Report transaction structure error; do not treat reserve as successful.
}
```

This is a diagnostic snippet; it requires importing `org.springframework.transaction.IllegalTransactionStateException`. Catching the exception can help translate the error into a meaningful response/diagnostic, but **cannot turn a rejected operation into a completed one**. Do not swallow the error and return success.

If the business logic legitimately allows standalone calls, you can design an outer `@Transactional(REQUIRED)` method to open the transaction and then call the inner `MANDATORY` method. You should not force every caller to remember to open a transaction manually via a JDBC connection.

## 5. Caller contract: who is responsible for opening the transaction?

A maintainable design splits into two layers:

1. **Orchestration/application service:** responsible for coordinating business logic and opening the transaction for the whole workflow; typically uses the default `@Transactional` (`REQUIRED`).
2. **Participant service:** has operations that are **only valid inside an already open transaction**; uses `MANDATORY` to catch calls that violate the contract.

Example:

```java
@Service
class OrderApplicationService {
    private final OrderWriter orderWriter;
    private final StockWriter stockWriter;

    OrderApplicationService(OrderWriter orderWriter,
                            StockWriter stockWriter) {
        this.orderWriter = orderWriter;
        this.stockWriter = stockWriter;
    }

    @Transactional
    public void placeOrder(long orderId) {
        orderWriter.save(orderId);
        stockWriter.reserve(orderId);
    }
}

@Service
class StockWriter {
    @Transactional(propagation = Propagation.MANDATORY)
    public void reserve(long orderId) {
        // SQL to deduct inventory.
    }
}
```

**Design snippet only:** `OrderWriter` is an application-defined component; these classes are not a standalone Java file. If all writes use **the same JDBC DataSource** and the right transaction manager, when `placeOrder` rolls back, `reserve` rolls back with it. If a controller calls `stockWriter.reserve` directly without T1, that is a **contract violation** and is detected early.

### MANDATORY does not turn the system into a cross-network transaction guarantee

Transaction T1 is a transaction of the resource controlled by the manager. If `reserve()` makes an HTTP call to another service, MANDATORY **does not automatically join service B's physical transaction**. If `OrderWriter` and `StockWriter` use different transaction managers/datasources, "same call stack" does not mean "same physical transaction". Designing XA/2PC or saga/outbox/idempotency is a separate topic; here we must keep the local boundary clear.

## 6. When inner MANDATORY fails: rollback-only and UnexpectedRollbackException

`MANDATORY` joins T1, so special attention must be paid to **rollback-only**.

Suppose outer opens T1 and calls inner through **another bean's proxy**:

```java
@Transactional
public void outer() {
    orders.insert(10); // Illustrative SQL inside T1.
    try {
        inventory.reserveAndFail(); // @Transactional(MANDATORY)
    } catch (IllegalStateException ex) {
        // Outer catches the error and wants to continue.
    }
    orders.insert(11); // May still execute in some cases.
}
```

If `reserveAndFail()` throws `IllegalStateException` (unchecked) **and it escapes through the inner interceptor**:

- The inner logical scope decides on rollback according to default rollback rules.
- Because MANDATORY **does not create T2** and is participating in T1, with a default local transaction manager it typically marks physical transaction T1 as **rollback-only**.
- Outer catching the exception only handles **Java control flow**. Catching the error **does not clear** rollback-only.
- When outer returns normally and the interceptor attempts to commit T1, Spring rolls back instead of committing. The caller of outer typically receives `UnexpectedRollbackException`: signaling that the expected commit did not actually happen.

Not every caught exception guarantees an `UnexpectedRollbackException`: this depends on rollback rules, whether inner went through a proxy, manager configuration (such as `globalRollbackOnParticipationFailure`), resource errors, and rollback-only state. The demo below uses the default `JdbcTransactionManager` to demonstrate the outcome.

### Exception escaping outer

If outer **does not catch** the inner unchecked exception, the exception continues escaping outer. The outer interceptor also sees the error and rolls back T1. In this case the caller may see **the original exception** instead of `UnexpectedRollbackException` (because outer never attempted to commit after swallowing the error).

### Checked exceptions and rollback rules

Under Spring's standard defaults, unchecked `RuntimeException` and `Error` trigger rollback, while checked exceptions like `IOException` **do not** trigger rollback by default. You can configure:

```java
@Transactional(
    propagation = Propagation.MANDATORY,
    rollbackFor = IOException.class
)
public void importDetails() throws IOException {
    // When IOException escapes through the interceptor, Spring applies the rollback rule.
}
```

This is a **snippet**; it requires importing `java.io.IOException`, `Propagation`, and `Transactional`. Because the method participates in T1, this rollback rule can affect **the shared physical transaction**, not just the inner SQL statements. Do not use `noRollbackFor` as a blanket solution to "prevent full rollback" when data consistency has already been compromised.

### Inner method called without going through a proxy

If outer calls `this.innerMandatory()` in **the same bean**, the transaction interceptor **does not see** the inner annotation in Spring AOP proxy mode. Inner may still operate inside the outer transaction if outer already has T1, but **inner's own** rollback rules / propagation attributes are not applied through that internal call.

Therefore, verify both **the physical transaction** and **invocation through the proxy** before blaming MANDATORY.

## 7. MANDATORY does not create its own transaction for isolation, timeout, and readOnly

Suppose a participant method declares:

```java
@Transactional(
    propagation = Propagation.MANDATORY,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void readConsistentReport() {
    // Runs inside the existing transaction, does not open T2.
}
```

This is a **snippet**; it requires importing `org.springframework.transaction.annotation.Isolation`, `Propagation`, and `Transactional`.

Because MANDATORY **only joins an already opened transaction**:

- `isolation = SERIALIZABLE` on inner **does not upgrade** the outer physical transaction's isolation to SERIALIZABLE.
- `timeout = 5` on inner **does not reset** the outer transaction's deadline. The already opened transaction's timeout continues to govern.
- `readOnly = true` on inner **does not turn** an existing read-write outer transaction into a physical read-only transaction.
- Attributes specific to starting a new transaction usually **only take effect at the boundary that actually creates the transaction**.
- **Inner's rollback rules** still matter at the logical scope: when a matching exception escapes, the interceptor can mark the shared physical transaction rollback-only.

Spring provides an existing-transaction validation mode, such as `setValidateExistingTransaction(true)` on an appropriate transaction manager. When enabled, an incompatible isolation level or a read-write inner call attempting to join a read-only outer transaction can be **rejected** instead of ignored. That is **validation**, not creating a new transaction or altering the opened transaction.

### Which transaction does MANDATORY join when there are multiple layers?

The method joins **the currently active transaction** for its manager/resource. For example, if outer T1 calls a `REQUIRES_NEW` method that opens T2, and code inside T2 calls a `MANDATORY` participant through a proxy: the participant joins **T2**, not the suspended T1. MANDATORY **does not know and does not check "whether the transaction opener was specifically OrderService"**.

Therefore, if business rules require the participant to be called only in a specific workflow, you need an API/authorization/business validation layer and corresponding tests; `MANDATORY` only checks transaction presence.

## 8. Runnable Java 17 project: MANDATORY blocks callers without a transaction

Practical goal: use Spring Boot 3.5.7 (Spring Framework 6.2), Java 17, Maven, H2, and `JdbcTransactionManager`. Verify four scenarios:

1. **Without T1:** call inner `MANDATORY` directly through proxy → `IllegalTransactionStateException`; method body does not run.
2. **With T1, both succeed:** outer `REQUIRED` calls inner `MANDATORY` → both INSERTs commit together.
3. **Outer fails after inner succeeds:** outer throws an unchecked exception → both INSERTs roll back.
4. **Inner fails, outer catches exception:** inner joins T1, marks rollback-only → outer fails to commit and caller receives `UnexpectedRollbackException`.

Do not use sleep or query timeouts to evaluate MANDATORY; the reliable criteria are **the remaining DB data and exceptions at the right boundaries**.

### 8.1. Project structure

```text
mandatory-transaction-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/mandatory/
        │       ├── MandatoryApplication.java
        │       ├── OuterService.java
        │       └── MandatoryService.java
        └── resources/
            └── application.properties
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>mandatory-transaction-demo</artifactId>
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

`spring-boot-starter-jdbc` brings in Spring JDBC and transaction infrastructure. `h2` is an in-memory database requiring no separate installation. Spring Boot auto-configures `DataSource` and `JdbcTemplate` from properties; here we declare the JDBC transaction manager explicitly so we know clearly which manager controls the transaction.

### 8.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:mandatory_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` keeps the in-memory database alive across connections within the same JVM. The demo creates the table using `JdbcTemplate` before running the services; the JDBC transaction manager and `JdbcTemplate` share the same data source.

### 8.4. `src/main/java/vn/example/mandatory/MandatoryService.java`

```java
package vn.example.mandatory;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MandatoryService {

    private final JdbcTemplate jdbc;

    public MandatoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void insertThenFail(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
        throw new IllegalStateException("Inner operation failed");
    }
}
```

Both methods are **public** on a `@Service` bean so the Spring transaction proxy can intercept them. `insert` is only valid when a transaction already exists; `insertThenFail` intentionally throws an unchecked exception **after** the SQL statement to verify rollback-only behavior.

`MandatoryService` does not own the final commit decision. It is a participant joining a transaction created by the caller.

### 8.5. `src/main/java/vn/example/mandatory/OuterService.java`

```java
package vn.example.mandatory;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {

    private final JdbcTemplate jdbc;
    private final MandatoryService participant;

    public OuterService(JdbcTemplate jdbc, MandatoryService participant) {
        this.jdbc = jdbc;
        this.participant = participant;
    }

    @Transactional
    public void commitBoth() {
        insertOuter(10, "outer-commit");
        participant.insert(11, "inner-commit");
    }

    @Transactional
    public void rollbackBoth() {
        insertOuter(20, "outer-rollback");
        participant.insert(21, "inner-rollback");
        throw new IllegalStateException("Outer operation failed");
    }

    @Transactional
    public void catchInnerFailure() {
        insertOuter(30, "outer-before-inner-error");
        try {
            participant.insertThenFail(31, "inner-error");
        } catch (IllegalStateException expected) {
            // Java exception was caught, but rollback-only remains.
        }
        insertOuter(32, "outer-after-inner-error");
        // Method returns normally; T1 commit still fails.
    }

    private void insertOuter(int id, String label) {
        jdbc.update(
            "INSERT INTO journal_entries(id, label) VALUES (?, ?)",
            id, label
        );
    }
}
```

Because `OuterService` injects the **Spring-managed MandatoryService** through its constructor, the calls `participant.insert(...)` and `participant.insertThenFail(...)` go through **another bean's proxy**, not `this.innerMethod()`.

The outer methods do not specify propagation, so they default to `REQUIRED`. When the runner calls from outside a transaction, each outer method creates a T1. Inner `MANDATORY` joins that same T1; no additional T2 is created.

### 8.6. `src/main/java/vn/example/mandatory/MandatoryApplication.java`

```java
package vn.example.mandatory;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class MandatoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(MandatoryApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc,
                           MandatoryService participant,
                           OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE journal_entries (" +
                "id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)"
            );

            try {
                participant.insert(1, "direct-without-transaction");
                throw new AssertionError("MANDATORY should reject no tx");
            } catch (IllegalTransactionStateException expected) {
                System.out.println(
                    "direct=IllegalTransactionStateException"
                );
            }
            System.out.println("directRows=" + count(jdbc, 1));

            outer.commitBoth();
            System.out.printf("committed=%d,%d%n",
                count(jdbc, 10), count(jdbc, 11));

            try {
                outer.rollbackBoth();
                throw new AssertionError("Expected outer failure");
            } catch (IllegalStateException expected) {
                // Outer T1 has rolled back.
            }
            System.out.printf("outerRollback=%d,%d%n",
                count(jdbc, 20), count(jdbc, 21));

            try {
                outer.catchInnerFailure();
                throw new AssertionError("Expected rollback-only");
            } catch (UnexpectedRollbackException expected) {
                System.out.println(
                    "innerCaught=UnexpectedRollbackException"
                );
            }
            System.out.printf("innerCaughtRows=%d,%d,%d%n",
                count(jdbc, 30), count(jdbc, 31), count(jdbc, 32));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM journal_entries WHERE id = ?",
            Integer.class, id
        );
    }
}
```

**Why are the results reliable in this demo configuration?**

- `@EnableTransactionManagement(proxyTargetClass = true)` enables transaction advice via class-based proxies.
- `JdbcTransactionManager` manages JDBC transactions for the single `DataSource` bean that `JdbcTemplate` also uses.
- `CommandLineRunner` is a caller in a different bean without `@Transactional`; it calls `MandatoryService` directly when there is no T1, and calls `OuterService` through its proxy for the remaining cases.
- `IllegalTransactionStateException` is thrown by Spring **before entering `participant.insert`** on the direct call.
- In `catchInnerFailure`, the default `JdbcTransactionManager` marks the physical transaction rollback-only after the unchecked error in the participating inner scope.
- Data is read back **after the outer calls finish**, without using the failed transaction itself to judge the outcome.

### 8.7. Run command

From the `mandatory-transaction-demo` directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/mandatory-transaction-demo-1.0.0.jar
```

The lines **explicitly printed by the demo program** when running with Spring Boot 3.5.7/H2/JDBC manager as above are:

```text
direct=IllegalTransactionStateException
directRows=0
committed=1,1
outerRollback=0,0
innerCaught=UnexpectedRollbackException
innerCaughtRows=0,0,0
```

Spring Boot may print additional startup, HikariCP, and shutdown logs; the block above only shows the **explicit business stdout** from the code.

### 8.8. Reading each output line

| Output | Meaning |
| --- | --- |
| `direct=IllegalTransactionStateException` | MANDATORY rejected a caller with no transaction. |
| `directRows=0` | The body of `MandatoryService.insert(1, ...)` did not run. |
| `committed=1,1` | Outer and inner committed successfully together in T1. |
| `outerRollback=0,0` | Outer rolling back T1 also rolled back the SQL executed in inner MANDATORY. |
| `innerCaught=UnexpectedRollbackException` | Inner MANDATORY marked T1 rollback-only; outer caught the error and tried to commit, which failed. |
| `innerCaughtRows=0,0,0` | Outer's work before the error, inner's work at the error, and outer's work after catch all rolled back. |

This is the practical reason for using MANDATORY: the caller must deliberately choose the transaction boundary, while the inner method neither opens its own transaction nor commits independently. At the same time, it helps catch callers that accidentally invoke a participant from the wrong layer.

## 9. Notes on self-invocation, proxies, and bean lifecycle

### 9.1. Self-invocation can disable MANDATORY

```java
@Service
class BadBoundary {
    public void startWithoutTransaction() {
        mandatoryStep(); // Internal call this.mandatoryStep().
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void mandatoryStep() {
        // In proxy mode, the annotation is not applied on self-calls.
    }
}
```

This is a **snippet**, not a complete program. If `startWithoutTransaction()` is called externally without a transaction, `mandatoryStep()` may still run **without throwing `IllegalTransactionStateException`**, because the call bypasses the interceptor. That is not Spring "letting MANDATORY run incorrectly"; it is **you bypassing the proxy**.

**The fix is usually simple:** extract the participant method into another Spring bean or place the transaction boundary on a public method called by an outside bean through the proxy. Avoid self-proxy hacks when the design can separate responsibilities more cleanly.

### 9.2. Annotation on private/final methods

Class-based proxies cannot override `private`/`final` methods; JDK proxies only expose public interface methods. With Spring Framework 6.x, class-based proxies may consider eligible non-public methods when called through the proxy, but still do not intercept private/final methods. With MANDATORY, the consequence can be serious: **losing the transaction presence check**.

Therefore, for business logic that must be guaranteed to run inside a transaction, a **public method on a separate Spring-managed bean** is the easiest boundary to reason about and test.

### 9.3. Constructors, `@PostConstruct`, and objects created with `new`

Do not call a MANDATORY transactional method inside a constructor, `@PostConstruct`, or on an object created manually with `new` expecting the Spring proxy to run automatically. During construction/initialization, the proxy may not be ready; a manually created object is not a proxied bean. Call it after context initialization through a Spring-injected bean, or use a programmatic transaction API when needed.

## 10. When is MANDATORY appropriate, and when is it not?

### Appropriate

- Write operations that **must not commit independently** of the outer workflow.
- A service module explicitly designed as a **participant**, with an outer service responsible for orchestration and the transaction boundary.
- When you want early detection of invalid calls from a controller, scheduler, or batch job that has not opened a transaction.
- When sharing the same transaction manager/resource and wanting to roll back **all** business data if any step fails.

Model example:

```text
CheckoutService.checkout()       REQUIRED: opens T1
  ├── OrderWriter.save()         MANDATORY: joins T1
  ├── StockWriter.reserve()      MANDATORY: joins T1
  └── LedgerWriter.record()      MANDATORY: joins T1
                                 |
                                 v
                    T1 commits or rolls back together
```

Note: even when all three methods specify MANDATORY, they only truly share a physical transaction when using the same transaction manager and properly configured connection/resource.

### Not appropriate

- A method that needs both to be used by callers inside a transaction **and** to work standalone from a job/CLI without a transaction. `REQUIRED` may fit better, or provide a separate outer API to open the transaction.
- Inner needs to **commit immediately** even if outer rolls back. Only `REQUIRES_NEW` provides an independent transaction; MANDATORY does not.
- Inner needs to roll back only a portion via savepoint; consider `NESTED` when the JDBC driver/manager supports it, though that is a different mechanism.
- Code that primarily performs HTTP/gRPC calls, message broker publishing, or operations outside databases not managed by the transaction manager. MANDATORY does not make remote side effects ACID.
- Using multiple transaction managers/datasources without clearly identifying the right manager; merely checking "is there a transaction" on one manager does not prove all resources are participating.

## 11. When there are multiple transaction managers

An annotation can select a manager explicitly:

```java
@Transactional(
    transactionManager = "ordersTransactionManager",
    propagation = Propagation.MANDATORY
)
public void updateOrderLine() {
    // Requires the proper Orders DataSource/repository.
}
```

This is a **snippet**, assuming the `ordersTransactionManager` bean exists. MANDATORY checks for an existing transaction **compatible with that manager**. A transaction for `paymentsTransactionManager` **does not automatically** become a transaction for `ordersTransactionManager`, even on the same calling thread.

If a service is called with T1 from manager A while inside the method it touches manager B, you must understand precisely which transaction is being checked, which data source provides connections, and how the manager is selected. Do not try to "fix" errors by changing every method to `REQUIRED` if that causes data to run across two independent physical transactions that you mistakenly believe are atomic.

Some architectures use `JtaTransactionManager`, JPA transaction managers, or reactive transaction managers. The general semantics of MANDATORY remain **requiring an existing transaction**, while how the manager detects transactions, enlists resources, and handles suspend/rollback depends on the specific integration.

## 12. When the caller suspends the transaction before calling MANDATORY

Having an outer T1 does not mean **every nested call stack** still has T1. If execution enters a `NOT_SUPPORTED` scope, the transaction manager can **suspend** T1 and run the inner code outside any transaction.

```java
@Service
class NonTransactionalStep {
    private final MandatoryService mandatory;

    NonTransactionalStep(MandatoryService mandatory) {
        this.mandatory = mandatory;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void callMandatoryOutsideTx() {
        mandatory.insert(77, "invalid");
    }
}
```

This is a **snippet**, assuming the `MandatoryService` class from the demo. When `callMandatoryOutsideTx()` is called **through a proxy** while T1 is active, it requests suspending T1. The call to `mandatory.insert(...)` through a proxy inside the suspended scope has no eligible transaction, so MANDATORY throws `IllegalTransactionStateException`. Spring resumes the suspended transaction when finishing the scope according to the manager's mechanism.

**Key point:** "the original caller once opened a transaction" is not enough. MANDATORY requires a transaction **currently active at the moment the method's interceptor is entered**. A suspended T1 does not satisfy that condition.

If a `REQUIRES_NEW` method has opened T2 and calls MANDATORY, MANDATORY joins the new T2. It has no awareness of the outer suspended T1.

## 13. MANDATORY across different threads or reactive models

### Imperative / JDBC

With `JdbcTransactionManager` or `DataSourceTransactionManager`, the imperative transaction context is typically stored in Spring's **ThreadLocal**. T1 from a request thread does not automatically propagate to a `new Thread(...)`, thread pool, or `@Async`.

**Warning snippet** example:

```java
@Transactional
public void submitAsync() {
    executor.execute(() -> {
        mandatoryService.insert(99, "async");
    });
}
```

Assuming `executor` and `mandatoryService` are application dependencies and the worker thread call goes through the proxy, MANDATORY on the worker thread can throw `IllegalTransactionStateException` because it **does not see** the calling thread's T1, even though `submitAsync()` is in a transaction.

If the worker thread truly needs a transaction, create a separate transaction boundary **where the worker runs** with appropriate propagation; do not try to arbitrarily share a thread-bound JDBC connection/transaction across threads.

### Reactive

With `ReactiveTransactionManager`, the transaction context typically lives in the **Reactor Context**, not an imperative ThreadLocal. MANDATORY in a reactive pipeline still requires an existing transaction per the manager/reactive context; switching schedulers or detaching publishers from the pipeline improperly can cause the context to be lost. Do not treat imperative JDBC examples as proof that transactions automatically cross every reactive publisher.

### Remote services

An HTTP/gRPC request sent to service B does not carry service A's JDBC physical database transaction. If B has an endpoint calling a MANDATORY method, B must have a transaction context **on B's side** or the call is rejected; `@Transactional` in service A does not propagate automatically to B. Do not treat MANDATORY as an atomic guarantee across microservices.

## 14. How to verify a MANDATORY boundary truly works

### 14.1. Using `TransactionSynchronizationManager` for diagnostics

Inside the participant method:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

System.out.println("active=" + active);
```

This is a **snippet**, importing `org.springframework.transaction.support.TransactionSynchronizationManager`. If the call is intercepted, a compatible T1 exists, and the method is running, `active=true` is usually true. However, **active=true does not prove MANDATORY was advised**: an unintercepted method can still see a transaction opened by an outer caller.

Therefore, **two separate tests** are required:

- Call MANDATORY through the proxy **without a transaction** → must throw `IllegalTransactionStateException` before SQL runs.
- Call MANDATORY through the proxy **with a transaction** and then make outer roll back → inner SQL must roll back with outer.

These two tests verify both **the entry constraint** and **physical transaction participation**.

### 14.2. Enabling logs to observe the transaction interceptor

In dev/test environments you can enable:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs help you see which methods go through transaction advice and when the manager begins/joins/ends a transaction. Do not rely solely on logs if DB data shows a different outcome, and avoid logging sensitive details in production.

### 14.3. Be careful with Spring TestContext

A `@Transactional` test method can have a **test-managed transaction** opened by Spring TestContext before calling the service. In that case, a direct `MANDATORY` invocation in the test **has a transaction**, so it will not throw an exception. To test the "no transaction" failure, the test method must **not be wrapped in a test transaction**, or must explicitly manage the test transaction with the appropriate API.

Similarly, a test that auto-rolls back at the end can mask whether the outer service boundary actually commits/rolls back as you expect. Design tests that both check transaction state and read data from an appropriate boundary **after the call**.

## 15. Common mistakes and misconceptions

| Misconception or mistake | What is actually true | How to handle it |
| --- | --- | --- |
| "MANDATORY always creates a transaction." | It **requires an existing transaction**; throws if missing. | Put `@Transactional(REQUIRED)` on the outer boundary or change the contract if standalone is needed. |
| "Inner MANDATORY will commit before outer." | MANDATORY **joins T1**, there is no T2. | Let outer decide commit/rollback; use `REQUIRES_NEW` only if independence is genuinely needed. |
| "A controller calling MANDATORY directly still works." | Without T1 and called via proxy, Spring rejects it. | Have the controller call an orchestration service that opens a transaction. |
| "Catching the inner exception means outer will definitely commit." | Inner may have marked T1 rollback-only. | Define rollback rules; handle error contracts; test `UnexpectedRollbackException`. |
| "isActualTransactionActive=true proves the MANDATORY annotation ran." | It does not prove advice ran on this method itself. | Test calling outside a transaction and test actual rollback. |
| "`this.innerMandatory()` also checks MANDATORY." | Self-invocation bypasses proxy mode. | Extract to another bean, call the Spring-injected proxy. |
| "Timeout/isolation on MANDATORY changes T1." | MANDATORY does not create a new transaction. | Set attributes on the boundary creating T1; validate mismatches when needed. |
| "Once T1 is opened, every child method always sees T1." | `NOT_SUPPORTED` can suspend T1; other threads/async do not inherit it. | Verify active transaction at the exact call site. |
| "Having a transaction in another manager is enough." | The transaction must be compatible with the method's manager. | Select manager/datasource explicitly, test with a real DB. |
| "MANDATORY protects HTTP/email too." | It does not roll back side effects outside transactional resources. | Design outbox/idempotency/saga when needed. |
| "Private/final methods also get the annotation applied." | Spring AOP proxies have interception limits. | Use public service boundaries through bean proxies. |
| "`IllegalTransactionStateException` is a SQL error." | It is a **pre-method transaction state** error. | Inspect caller, proxy, and manager before looking at SQL. |

## 16. Checklist for using MANDATORY

- [ ] The method is only allowed to run **when a transaction already exists**; this is a business requirement, not a habit.
- [ ] The orchestration caller has `@Transactional(REQUIRED)` or another transaction boundary **actually active** when calling the participant.
- [ ] The MANDATORY method is on a Spring-managed bean and called **through a proxy**, not via `new` or `this`.
- [ ] The correct `PlatformTransactionManager` is confirmed, and repositories/`JdbcTemplate` use the matching resource.
- [ ] MANDATORY is not expected to open a new transaction or commit independently.
- [ ] Inner rollback rules and rollback-only consequences for outer are understood.
- [ ] The scenario where outer catches an inner exception and still fails to commit has been checked.
- [ ] Isolation, timeout, or read-only on the participant is not relied upon to alter an already opened physical transaction.
- [ ] If `NOT_SUPPORTED`, `REQUIRES_NEW`, or async/threads exist, the **actual active transaction** at the call site has been verified.
- [ ] Integration test calling **without a transaction** throws `IllegalTransactionStateException`.
- [ ] Integration test with caller transaction succeeding persists both outer and inner data.
- [ ] Integration test with caller rolling back reverts both outer and inner data.
- [ ] Tests do not accidentally have a transaction auto-opened by Spring TestContext.
- [ ] MANDATORY is not assumed to create a global transaction across multiple datasources or microservices.

## 17. Self-check questions

**Question 1.** A public `@Transactional(propagation = MANDATORY)` method is called through a proxy, with no transaction. Does it create a transaction automatically?

**Answer:** **No.** It throws `IllegalTransactionStateException` before running the method body.

**Question 2.** Outer `REQUIRED` opens T1, and inner `MANDATORY` is called on another bean. How many physical transactions exist?

**Answer:** Typically **one** T1, when using the same compatible manager/resource. Inner joins T1.

**Question 3.** Inner `MANDATORY` returns normally, and then outer throws an unchecked exception. Does the inner SQL remain?

**Answer:** No, if both share physical transaction T1 and outer rolls back successfully; inner has not committed independently.

**Question 4.** Inner `MANDATORY` throws an unchecked exception, and outer catches it and returns normally. Is outer guaranteed to commit?

**Answer:** **No.** Inner may have marked T1 rollback-only. With a default manager like in the demo, outer receives `UnexpectedRollbackException` when attempting to commit.

**Question 5.** Outer T1 calls a `NOT_SUPPORTED` bean, which then calls MANDATORY. Does MANDATORY see T1?

**Answer:** No, if `NOT_SUPPORTED` **suspended T1** under the same manager and the call goes through a proxy. MANDATORY requires an active transaction at the time its interceptor is entered.

**Question 6.** Outer T1 calls `REQUIRES_NEW` opening T2; inside T2 it calls MANDATORY. Which transaction does inner MANDATORY belong to?

**Answer:** It joins the currently active **T2**, not the suspended T1. MANDATORY only checks that a compatible transaction exists, not who originally opened the outer transaction.

**Question 7.** `this.participant()` in the same bean has `@Transactional(MANDATORY)`, with no transaction. Is an exception guaranteed?

**Answer:** No in Spring proxy mode, because self-invocation can bypass the interceptor. Separate beans/call through a proxy and write tests to enforce the constraint.

## Official References

- Spring Framework — [`Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Propagation.html): `MANDATORY` requires a current transaction, unlike `REQUIRED` and `REQUIRES_NEW`.
- Spring Framework — [`TransactionDefinition` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html): `PROPAGATION_MANDATORY` and the current-transaction contract.
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): annotations, propagation, rollback rules, isolation/timeout/readOnly.
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical transactions, participation, and `UnexpectedRollbackException`.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies and self-invocation.
- Spring Framework — [`IllegalTransactionStateException` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/IllegalTransactionStateException.html): error when transaction state is incompatible with propagation.
- Spring Framework — [TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): risk of tests inadvertently supplying a transaction to a MANDATORY method.

**Core takeaway:** `MANDATORY` is a **requirement that the caller open a transaction beforehand**, not a request for Spring to open one automatically. When a compatible transaction already exists, the inner method joins **the same physical transaction** and commits/rolls back with the outer method; when none exists, the method is rejected **before execution**. This guarantee only holds when the call **passes through a Spring transaction proxy** with the right transaction manager/resource.
