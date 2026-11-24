# Nested Service Calls Do Not Always Create New Transactions

> **Context:** Spring Framework — Transaction Management, **Transaction Scope** section. This lesson explains why one service method calling another service method, even when both have `@Transactional`, may still use **one physical transaction**; when Spring creates an independent transaction; why an internal call within the same bean can bypass transaction advice; and the consequences of rollback-only. Examples use Java 17, Spring Boot 3.5.x, Spring JDBC, and H2.

## 1. Main point: number of methods does not equal number of transactions

Consider two services in the same application:

```java
@Service
class OrderService {
    private final InventoryService inventory;

    OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder() {
        // Write order to the database.
        inventory.reserve(); // Call another service bean.
    }
}

@Service
class InventoryService {
    @Transactional
    public void reserve() {
        // Write inventory reservation to the database.
    }
}
```

This is an **illustrative snippet**, assuming the code uses Spring's `@Service`, `@Transactional`, and has a transaction manager and repositories/JdbcTemplate configured for the right data source. Both methods have `@Transactional`, yet default to `propagation = REQUIRED`.

If `placeOrder()` is called through a Spring proxy **when no transaction exists yet**:

1. `OrderService`'s interceptor starts **one physical transaction**.
2. `OrderService` calls `InventoryService` through **the proxy of another Spring bean**.
3. `InventoryService`'s interceptor sees that a suitable transaction already exists; with `REQUIRED`, it **joins that transaction**, without opening a second physical transaction.
4. Updates sharing the same transaction manager/resource are committed or rolled back **together** when the outer boundary ends.

Therefore, "nested service calls" does not mean "nested independent transactions". The word *nested* describes the **call stack**, whereas the number of physical transactions depends on **propagation, the transaction manager, resources, and routing through the proxy**.

## 2. Distinguishing logical transaction scope and physical transaction

Spring uses two conceptual layers that must be distinguished:

- **Logical transaction scope:** the boundary established by the transaction interceptor when transaction advice is applied to a method. Each intercepted `@Transactional(propagation = REQUIRED)` call can have its own logical scope, carrying its own metadata and rollback-only state.
- **Physical transaction:** the actual resource transaction, for example an active JDBC connection or JPA transaction. One or more logical scopes can point to **one** physical transaction.

Diagram with `REQUIRED`:

```text
Caller
  |
  v
OrderService.placeOrder()  @Transactional(REQUIRED)
  |   [logical scope A]
  |   [physical transaction T1 begins]
  |
  +--> InventoryService.reserve()  @Transactional(REQUIRED)
  |      [logical scope B]
  |      [participates in the same physical transaction T1]
  |
  +--> continues updating
  |
  v
Commit or roll back T1 at the outer boundary
```

The number of intercepted annotated methods in this example is **2**, and the number of physical transactions is **1**.

If an inner scope sets **rollback-only** on T1, the outer scope is still participating in the same T1 and cannot successfully commit that transaction simply because it caught an exception and kept running. Spring can throw `UnexpectedRollbackException` when outer tries to commit to avoid reporting a false success.

Diagram with `REQUIRES_NEW`:

```text
OuterService.outer()  @Transactional(REQUIRED)
    [physical transaction T1 is open]
       |
       | call through proxy
       v
InnerService.inner()  @Transactional(REQUIRES_NEW)
    [T1 is suspended]
    [independent physical transaction T2 begins]
    [T2 commits or rolls back separately]
       |
       v
    [T1 is resumed]
       |
       v
Outer continues T1 and commits/rolls back T1
```

Here, if the transaction manager and datasource allow proper suspend/resume, the number of physical transactions can be **2**, each with its own outcome. But this is a consequence of **`REQUIRES_NEW` actually being intercepted**, not because the method is named `inner`.

## 3. Default `REQUIRED`: join the transaction if one already exists

Spring's `@Transactional` has a default propagation of `Propagation.REQUIRED`:

```java
@Transactional
public void updateProfile() {
    // Equivalent to @Transactional(propagation = Propagation.REQUIRED)
}
```

Behavior:

| State upon entering the method | What does `REQUIRED` do? | Number of new physical transactions |
| --- | --- | --- |
| No matching transaction exists | Starts a new transaction | 1 |
| Matching transaction already exists with same manager/resource | Participates in the existing transaction | 0 |
| Method is not intercepted by a proxy | Annotation does not create a logical scope at that call | 0 from this annotation alone |
| Using a different manager/resource | Cannot infer the same transaction; must inspect the specific configuration | Depends on manager and resource |

The "**same manager/resource**" point is critical: two services calling two different datasources do not automatically share ACID atomicity. A Spring transaction manager typically manages local transactions for the resource it is configured with; having the same annotation name does not guarantee distributed transactions across multiple databases or remote services.

### Why is reusing a transaction useful behavior?

A common workflow: `CheckoutService` calls `OrderRepository`, `InventoryRepository`, and `AuditRepository`, all writing to **the same database**. A transaction at the service boundary ensures those changes are committed together or rolled back together. If every method opened an independent transaction, it would be easy to end up with "order created but inventory not reserved" when a later step fails.

Thus `REQUIRED` is a good default for many call stacks, because steps belonging to one business operation usually need the same physical transaction.

## 4. "Nested service calls" covers two very different cases

### 4.1. Calling from bean A to bean B

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        inner.inner(); // Spring-injected bean, through InnerService's proxy.
    }
}

@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Can open an independent T2 if the call is intercepted.
    }
}
```

This is an **excerpt**, requiring imports for `org.springframework.transaction.annotation.Propagation`, `@Transactional`, and `@Service`. When `InnerService` is injected as a Spring bean proxy and both methods meet proxy eligibility, inner can apply its own propagation.

### 4.2. Calling another method in the **same bean** (self-invocation)

```java
@Service
class SameBeanService {

    @Transactional
    public void outer() {
        inner(); // Equivalent to this.inner(); does not go through the Spring proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Inner's annotation is NOT intercepted in the call above.
    }
}
```

In **Spring AOP proxy mode**, the interceptor only wraps calls **arriving at the proxy from outside**. A method on the target calling another method via `this.inner()` does not pass back through the proxy, so the `REQUIRES_NEW` metadata on `inner` **is not applied separately**.

If `outer()` has already started T1, code inside `inner()` can still use T1 through JdbcTemplate/JPA because the transaction is already bound to the thread/context. However, it **does not create T2**. If outer rolls back, the DB operations inside inner will also roll back with T1.

If `outer()` is not annotated and no other transaction exists, self-invoking `inner()` can cause all that code to run **without any transaction**, even though `@Transactional` is in the source.

> Observing `TransactionSynchronizationManager.isActualTransactionActive() == true` **does not prove** that the annotation on the inner method was handled by the interceptor: the transaction may have been opened by an outer caller.

### 4.3. Visibility, final, and proxy type

Some methods are not intercepted by a proxy due to Java or the proxy type:

- With a JDK interface proxy, the caller must invoke through a **public method on the interface** exposed by the proxy.
- With a class-based proxy, Spring Framework 6.0+ can intercept eligible public/protected/package-visible methods when called through the proxy; older versions had different default policies.
- `private` methods cannot be overridden by a class proxy; `final` methods also cannot be overridden by a subclass proxy.
- Beans created manually with `new` and methods invoked from constructors or `@PostConstruct` should not be treated as normal transaction proxy calls.

These are causes **distinct** from propagation. Before analyzing why `REQUIRES_NEW` did not create a new transaction, verify whether the inner method **actually passed through the interceptor**.

## 5. Comparing common propagations when services call each other

| Inner propagation | When outer already has transaction T1 | When no transaction exists | Notes |
| --- | --- | --- | --- |
| `REQUIRED` | Joins **T1** | Creates a new transaction | Default; inner does not commit independently. |
| `REQUIRES_NEW` | Suspends T1, creates transaction **T2** | Creates a new transaction | T2 commits/rolls back independently; may require an extra connection. |
| `NESTED` | Usually creates a **savepoint in T1** with JDBC support | May create a new transaction like REQUIRED | Rolls back to savepoint; **not an independent T2**. |
| `SUPPORTS` | Runs inside T1 | Runs without a transaction | Does not proactively create a transaction. |
| `MANDATORY` | Joins T1 | Throws an error because a transaction is required | Useful when a method requires the caller to have already opened a transaction. |
| `NOT_SUPPORTED` | Suspends transaction and runs **without a transaction** | Runs without a transaction | Does not automatically make every JDBC/HTTP operation a safe side effect. |
| `NEVER` | Throws an error because transactions are forbidden | Runs without a transaction | Enforces caller contract. |

This table assumes the inner method is handled by the **Spring transaction interceptor** and the transaction manager supports the corresponding behavior. If called via `this.inner()`, the propagation table **is not automatically applied** to the inner annotation.

### Choosing based on business requirements

- Need all database write steps to commit/roll back together: typically use **`REQUIRED`**.
- Need a secondary transaction that can commit **even if outer later rolls back** (e.g., a technical audit log that must be persisted independently), consider **`REQUIRES_NEW`** while accepting independence and potential pool exhaustion/locking.
- Need to try a step, possibly roll back **only that step**, and let outer continue on the same physical transaction: consider **`NESTED`** when the datasource/driver supports savepoints.
- Need a method to be called **only inside** a transaction: `MANDATORY` expresses a clear contract.

Do not choose `REQUIRES_NEW` as a "generic patch" for transaction errors. It **alters business atomicity**, potentially letting inner commit while outer fails.

## 6. Rollback-only and `UnexpectedRollbackException`

This is the scenario that causes the most confusion when two services both use `REQUIRED`.

Suppose:

```java
@Transactional
public void outer() {
    orders.insert(...); // Illustrative code, assuming orders is a repository.
    try {
        inventory.reserve(); // @Transactional(REQUIRED), throws RuntimeException.
    } catch (IllegalStateException ex) {
        // Attempt to ignore the error so outer continues.
    }
    orders.markPrepared(...);
}
```

This is an **excerpt**, with `orders`/`inventory` defined by the application.

Sequence in a typical local transaction:

1. `outer()` opens T1.
2. `inventory.reserve()` through the proxy joins the **same T1** and creates its own logical scope.
3. `reserve()` throws `IllegalStateException` (unchecked).
4. Inner's interceptor, following the default rollback rule, handles the scope's failure and marks T1 **rollback-only**; the inner exception propagates out to outer.
5. Outer **catches the exception**, continues executing code, and **returns normally**.
6. Outer's interceptor tries to commit T1. Because T1 is rollback-only, the transaction is rolled back.
7. Spring can throw **`UnexpectedRollbackException`** to outer's caller: the caller must know that the commit did not happen even though outer's code returned normally.

The meaning of this exception: an inner scope silently marked the physical transaction as uncommittable, while the outer scope expected to commit. Spring reports this explicitly instead of pretending the commit succeeded.

**Not every caught exception leads to `UnexpectedRollbackException`.** For instance, if inner throws an error **without going through a transaction proxy**, or the error is not covered by a rollback rule, or the code uses an appropriate savepoint, the outcome can differ. When analyzing, examine the call path, rollback rules, transaction manager configuration, and how exceptions are handled.

### Checked exceptions and rollback rules

Spring's `@Transactional` by default rolls back when a `RuntimeException` or `Error` escapes through the interceptor; checked `Exception`s usually **do not** trigger rollback by default. You can configure:

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // Transaction rolls back when IOException escapes through the interceptor.
}
```

This is an **excerpt**, importing `java.io.IOException`. Custom rules can alter outcomes even for an inner scope participating in T1. If you **catch the exception within the same method** and neither rethrow it nor mark rollback-only, the interceptor may only see the method succeed, unless the resource has already failed/been marked rollback-only for another reason.

### Why fixing it with catch or `noRollbackFor` is not necessarily right?

If an inner step fails yet outer business logic still wants to succeed, you must clearly design what may be skipped and what data state remains valid. Merely catching the exception can leave the transaction rollback-only. Conversely, adding `noRollbackFor` indiscriminately can retain incomplete changes.

If the inner step can be discarded while outer continues, `NESTED` with savepoints (when supported) or intentionally separating into an independent transaction will be clearer. Determine the **desired commit/rollback outcome** before choosing propagation.

## 7. Complete Java 17 example: counting rows to observe transaction boundaries

This section provides a minimal Spring Boot project, **runnable** with Maven, Java 17, and H2. Outcomes are measured by the persisted data after the methods finish, rather than merely reading annotations in code.

We test 5 cases in **the same database**:

1. Both outer and inner are `REQUIRED`; outer fails ⇒ both inserts roll back.
2. Inner `REQUIRED` fails, outer catches the exception ⇒ T1 is rollback-only and outer commit fails.
3. Inner `REQUIRES_NEW` succeeds, outer fails ⇒ T2 still commits, T1 rolls back.
4. Outer calls a `REQUIRES_NEW` method via `this` in the same bean ⇒ inner annotation is not intercepted; both inserts belong to T1.
5. Inner `NESTED` fails, outer catches the error ⇒ rolls back to inner's savepoint; both valid inserts in outer commit.

### 7.1. Project structure

```text
nested-transaction-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/
        │       └── example/
        │           └── nested/
        │               ├── NestedTransactionApplication.java
        │               ├── OuterService.java
        │               └── InnerService.java
        └── resources/
            └── application.properties
```

### 7.2. `pom.xml`

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
    <artifactId>nested-transaction-demo</artifactId>
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

- `spring-boot-starter-jdbc` provides Spring JDBC and the transaction infrastructure.
- `h2` is an in-memory JDBC database.
- `spring-boot-maven-plugin` creates an executable jar from the Boot project.
- No separate database server needs to be running.

### 7.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:nested_scope_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
```

The pool can hand out multiple connections; for example `REQUIRES_NEW` holds T1's connection while T2 needs another connection. This is only a sequential demo, not a production sizing formula.

### 7.4. `src/main/java/vn/example/nested/InnerService.java`

```java
package vn.example.nested;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void joinRequired(int id) {
        insert(id, "required-inner");
    }

    @Transactional
    public void requiredAndFail(int id) {
        insert(id, "required-inner-error");
        throw new IllegalStateException("inner REQUIRED failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independent(int id) {
        insert(id, "requires-new-inner");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedAndFail(int id) {
        insert(id, "nested-inner-error");
        throw new IllegalStateException("inner NESTED failed");
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)",
            id, description
        );
    }
}
```

All `@Transactional` methods are `public` and run on a separate Spring bean; the caller receives this bean via constructor injection, so calls from outer are intercepted by the transaction proxy.

Note: `NESTED` works via **JDBC savepoints** when the transaction manager/driver supports them. Do not automatically assume `NESTED` is supported identically by JPA, NoSQL, or every driver.

### 7.5. `src/main/java/vn/example/nested/OuterService.java`

```java
package vn.example.nested;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void requiredOuterFails() {
        insert(11, "outer-required");
        inner.joinRequired(12);
        throw new IllegalStateException("outer REQUIRED failed");
    }

    @Transactional
    public void requiredFailureIsCaught() {
        insert(21, "outer-before-inner-error");
        try {
            inner.requiredAndFail(22);
        } catch (IllegalStateException expected) {
            // Inner has already marked the physical transaction rollback-only.
        }
        insert(23, "outer-after-inner-error");
        // Returns normally, yet the commit can still be rejected.
    }

    @Transactional
    public void requiresNewOuterFails() {
        insert(31, "outer-requires-new");
        inner.independent(32);
        throw new IllegalStateException("outer failed after inner commit");
    }

    @Transactional
    public void selfInvocationOuterFails() {
        insert(41, "outer-self-invocation");
        requiresNewOnSameBean(42); // this.method(): bypasses the proxy.
        throw new IllegalStateException("outer self-call failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewOnSameBean(int id) {
        insert(id, "self-inner");
    }

    @Transactional
    public void nestedRecovery() {
        insert(51, "outer-before-savepoint");
        try {
            inner.nestedAndFail(52);
        } catch (IllegalStateException expected) {
            // Inner rolls back to the JDBC savepoint.
        }
        insert(53, "outer-after-savepoint");
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO audit_log(id, description) VALUES (?, ?)",
            id, description
        );
    }
}
```

There is no `@Transactional` on the `insert()` private helper: it runs inside the caller's connection/transaction when the caller has a transaction. In `selfInvocationOuterFails()`, `requiresNewOnSameBean(42)` is a call within the same bean. Because it does not go through the proxy, the inner method's `REQUIRES_NEW` annotation does not open T2. Rows 41 and 42 still belong to T1 opened by outer; when outer rolls back, both disappear together.

The `requiredFailureIsCaught()` case is where surprises often happen: outer catching the exception does not mean rollback-only was cleared. Inner `REQUIRED` is intercepted and throws an unchecked exception, so the transaction manager marks the physical transaction as uncommittable. Outer continues to insert row 23, yet all of 21/22/23 roll back when outer completes.

### 7.6. `src/main/java/vn/example/nested/NestedTransactionApplication.java`

```java
package vn.example.nested;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class NestedTransactionApplication {

    public static void main(String[] args) {
        SpringApplication.run(NestedTransactionApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demonstrate(JdbcTemplate jdbc,
                                  OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_log (" +
                "id INT PRIMARY KEY, " +
                "description VARCHAR(60) NOT NULL)"
            );

            expectFailure(outer::requiredOuterFails);
            System.out.printf("required=%d,%d%n",
                count(jdbc, 11), count(jdbc, 12));

            try {
                outer.requiredFailureIsCaught();
            } catch (UnexpectedRollbackException expected) {
                System.out.println(
                    "requiredCaught=UnexpectedRollbackException"
                );
            }
            System.out.printf("requiredCaughtRows=%d,%d,%d%n",
                count(jdbc, 21), count(jdbc, 22), count(jdbc, 23));

            expectFailure(outer::requiresNewOuterFails);
            System.out.printf("requiresNew=%d,%d%n",
                count(jdbc, 31), count(jdbc, 32));

            expectFailure(outer::selfInvocationOuterFails);
            System.out.printf("selfInvocation=%d,%d%n",
                count(jdbc, 41), count(jdbc, 42));

            outer.nestedRecovery();
            System.out.printf("nested=%d,%d,%d%n",
                count(jdbc, 51), count(jdbc, 52), count(jdbc, 53));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectFailure(Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected simulated failure");
        } catch (IllegalStateException expected) {
            // Simulated error thrown from outer.
        }
    }
}
```

Intentional design choices:

- `@EnableTransactionManagement(proxyTargetClass = true)` allows transaction advice to run through class-based proxies.
- `JdbcTransactionManager` manages **one** H2 `DataSource` auto-configured by Boot; `JdbcTemplate` uses the same datasource.
- `CommandLineRunner` is invoked by Spring after the context starts, and calls the injected `OuterService` through its proxy. There is no pre-existing transaction on the runner.
- `JdbcTransactionManager` builds on `DataSourceTransactionManager`, enabling nested transactions via JDBC savepoints when the driver/database supports them. H2 meets this requirement in the demo.
- `count(...)` runs after each method outside outer's transaction, so it observes actual committed/rolled-back results.

### 7.7. Run command and stdout to observe

From the `nested-transaction-demo` directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/nested-transaction-demo-1.0.0.jar
```

With Java 17, Spring Boot 3.5.7, and the configuration above, the lines **printed by the demo itself** are:

```text
required=0,0
requiredCaught=UnexpectedRollbackException
requiredCaughtRows=0,0,0
requiresNew=0,1
selfInvocation=0,0
nested=1,0,1
```

Spring Boot may print its own startup log lines. The lines above are the expected business output when the test runs on the stated stack.

### 7.8. Reading each result

| Case | Surviving rows | Reason |
| --- | --- | --- |
| `required=0,0` | Neither 11 nor 12 | Outer and inner `REQUIRED` share T1; outer throws an unchecked exception ⇒ rolls back T1. |
| `requiredCaughtRows=0,0,0` | None of 21/22/23 | Inner `REQUIRED` already marked T1 rollback-only; catching does not restore commit permission. |
| `requiresNew=0,1` | Only 32 | Inner T2 commits independently; outer T1 rolls back. |
| `selfInvocation=0,0` | Neither 41 nor 42 | `REQUIRES_NEW` annotation on a method in the same bean is not intercepted via `this`; both inserts belong to T1. |
| `nested=1,0,1` | 51 and 53 present, 52 absent | Inner rolls back to the savepoint in T1, outer continues and then commits T1. |

The row counts here are determined by the example's **actual transaction constraints**, not based on a hypothetical assumption such as "every annotated method creates a new connection".

## 8. `REQUIRES_NEW`: independent, yet comes with costs and risks

`@Transactional(propagation = Propagation.REQUIRES_NEW)` requests a **new** physical transaction for the intercepted scope:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentEvent() {
    // This transaction can commit even if outer subsequently rolls back.
}
```

If outer T1 already exists, the manager needs to suspend the current transaction, start T2, finish T2, and then resume T1. For JDBC with the same datasource, outer typically keeps holding T1's connection while inner acquires an additional connection for T2.

Consequently:

1. **Connection pool:** many concurrent requests holding T1 and all waiting for T2 can exhaust the pool, or even cause pool deadlock if every connection is held by outer transactions. Spring's documentation recommends a sufficiently large pool, with at least one more connection than concurrent threads in typical scenarios; in practice you must account for nesting depth and workload.
2. **Locks:** T1 might be holding a row lock that T2 wants to update. Because T1 is waiting for T2 to finish while T2 waits for T1's lock, a deadlock/timeout can occur. Do not use `REQUIRES_NEW` to update the same row currently locked by outer.
3. **Independent commit:** once T2 commits, it is not undone just because outer rolls back. This **is a real business change**, not a harmless technical optimization.
4. **Separate isolation/readOnly/timeout:** T2 can use its own transaction configuration because it is a new transaction, provided the manager/database supports it.

A valid use case is writing an independent technical audit record that must persist even when the business transaction rolls back, provided that audit does not lock data held by the business transaction. You must clearly decide whether the business transaction should proceed if the audit fails.

## 9. `NESTED`: savepoint, not an independent transaction

`Propagation.NESTED` is typically applied with a JDBC transaction manager and driver that support **savepoints**:

```text
BEGIN T1
  INSERT row A
  SAVEPOINT S1
    INSERT row B
    -- B fails:
  ROLLBACK TO SAVEPOINT S1
  INSERT row C
COMMIT T1

Result: A and C remain; B is undone.
```

Compared to `REQUIRES_NEW`:

| Comparison point | `NESTED` | `REQUIRES_NEW` |
| --- | --- | --- |
| Physical transaction | Typically **one** T1 | Independent T1 + T2 |
| Inner mechanism | JDBC savepoint inside T1 | New transaction |
| When inner fails | Can roll back to savepoint, outer continues | T2 rolls back separately, outer continues |
| When outer ultimately rolls back | All changes still in T1, including inner work that "succeeded", roll back | Changes already committed by T2 remain |
| JDBC connection | Typically uses T1's same connection | Typically needs another connection while T1 is still held |
| Compatibility | Depends on manager/driver nested support and savepoints | Depends on suspend capability/resources and pool |

Do not confuse "inner nested completed without error" with "inner nested committed independently". When using only savepoints, **the final commit is still decided by outer T1**.

JPA's `JpaTransactionManager` does not by default support nested transactions for the entity persistence context equivalent to JDBC savepoints. Depending on the manager/driver, `NESTED` may be rejected (`NestedTransactionNotSupportedException`) or restricted. Do not rely on the H2 demo to claim all persistence stacks behave the same way.

## 10. Isolation, timeout, and readOnly of inner `REQUIRED`

Suppose:

```java
@Transactional(isolation = Isolation.READ_COMMITTED, timeout = 30)
public void outer() {
    inner.run();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void run() {
    // Inner is called through the proxy, but joins outer's transaction.
}
```

These are **two signature excerpts from different beans**, not a complete class. Import `org.springframework.transaction.annotation.Isolation` and `Propagation`.

If `run()` joins **T1** opened by `outer()`:

- Spring by default keeps the characteristics of the **existing physical transaction**. `timeout=5` does not automatically reset the timer of T1 which has timeout 30.
- T1's isolation does not automatically escalate to `SERIALIZABLE` just because the inner annotation specifies it.
- `readOnly=true` on inner does not convert an already opened read-write transaction into a physically read-only one.
- Some transaction managers can be configured with `setValidateExistingTransaction(true)` to **reject** mismatched isolation or invalid read-only declarations instead of silently ignoring them. This is validation of the transaction-joining policy, **not** a mechanism to upgrade isolation or reset timeout.

The `isolation`, `timeout`, and `readOnly` attributes take clear effect when a method **starts a new transaction** (such as an outermost `REQUIRED` or an intercepted `REQUIRES_NEW`). If "inner must have its own short timeout" is a hard requirement, consider a new transaction boundary or a dedicated timeout on the query/HTTP operation itself; do not assume merely adding the annotation suffices.

## 11. Designing boundaries that are easy to understand and test

### 11.1. Place the transaction on the orchestration service

When a workflow involves multiple changes to **the same database**, placing the transaction on a public service method is usually the clearest option:

```java
@Service
class CheckoutService {
    private final Orders orders;
    private final Inventory inventory;

    CheckoutService(Orders orders, Inventory inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(long orderId) {
        orders.markPending(orderId);
        inventory.reserve(orderId);
        orders.markConfirmed(orderId);
    }
}
```

**Illustrative snippet:** `Orders` and `Inventory` are application interfaces, not built-in Spring APIs. When both use the same transaction manager/database and do not open independent transactions, they can participate in the same physical transaction.

### 11.2. Extract a separate bean when a distinct propagation is truly needed

If a step requires `REQUIRES_NEW` or `NESTED`, place it in a **separate Spring bean** and inject that bean. The structure is far more transparent than hoping self-invocation gets proxy-intercepted.

You can consider `TransactionTemplate` to express a boundary explicitly right in code:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.executeWithoutResult(status -> {
    jdbc.update(
        "INSERT INTO audit_log(id, description) VALUES (?, ?)",
        999, "independent"
    );
});
```

This is an **excerpt** with `manager` and `jdbc` provided. Import `org.springframework.transaction.support.TransactionTemplate` and `org.springframework.transaction.TransactionDefinition`. The programmatic API creates a transaction via the manager right at the callback, suitable when a boundary needs deliberate control; you must still consider connections/locks/independent commit.

### 11.3. Do not use "catch the exception and continue" as a substitute for a transaction decision

If outer needs to continue after inner fails, clearly determine what data was written and whether partial rollback or independent commit is allowed. With `REQUIRED`, an inner exception by default can mark the entire transaction rollback-only. You must change the propagation design or handle errors according to the business contract, not merely add `try/catch` to bypass it.

## 12. Other cases that do not automatically propagate transactions

### 12.1. `@Async`, new threads, and schedulers

Imperative transactions managed by `PlatformTransactionManager` are typically bound to the **current thread's** context. When a method creates `new Thread(...)`, runs via `@Async`, or uses a thread pool, the transaction does not automatically propagate to the other thread.

```java
@Transactional
public void submit() {
    executor.execute(() -> {
        repository.save(...); // Runs on a different thread.
    });
}
```

This is an **excerpt**, with `executor` and `repository` defined by the application. Code in the new thread does not automatically have `submit()`'s T1. If a worker thread needs a transaction, design a transaction boundary bean/method at the worker and account for consistency, retries, and execution ordering.

### 12.2. Reactive transactions

With `ReactiveTransactionManager`, the transaction context typically flows with the **Reactor context**, rather than ThreadLocal as in the JDBC imperative model. Publishers must be in the **same reactive pipeline/context** to participate in the transaction. Do not take conclusions from `JdbcTransactionManager` in this example and apply them mechanically to reactive code, or mix reactive and imperative without understanding the underlying resources.

### 12.3. Calling REST/gRPC to another microservice

An HTTP call to service B does not automatically propagate A's physical database transaction, even if both sides have `@Transactional`. Each service may open its own local transaction, with different commit/rollback timings. If cross-system business guarantees are needed, you must design API contracts, idempotency, outbox, saga, or distributed transactions when all participants genuinely support them.

### 12.4. Two transaction managers in the same application

If one method uses `ordersTransactionManager` and inner uses `paymentsTransactionManager`, you must examine the two actual datasources/resources. `REQUIRED` is evaluated within the **context of the corresponding manager**; do not conclude they participate in the same physical transaction merely because of a nested call stack. Selecting a manager can be declared explicitly:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder() {
    // Needs the repository/JdbcTemplate matching the right DataSource.
}
```

This is an **excerpt**, assuming the manager bean already exists. Two local managers do not automatically turn into XA/2PC.

## 13. Common mistakes and how to diagnose them

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Inner `@Transactional` does not open a second transaction | Default `REQUIRED` **joins T1** | Check propagation, manager, and whether an outer transaction exists. |
| Inner `REQUIRES_NEW` still rolls back with outer | Self-invocation or call bypassing the proxy | Inspect call graph and bean proxy; move inner to a separate bean. |
| Outer catches inner error yet ends up throwing `UnexpectedRollbackException` | Inner `REQUIRED` marked T1 rollback-only | Check stack trace, rollback rules, and actual commit outcome. |
| Inner `REQUIRES_NEW` committed while outer rolled back | Two independent transactions, expected design behavior | Verify this is the business requirement, not a framework bug. |
| Inner `NESTED` does not run | Manager/driver does not support savepoints | Check transaction manager and JDBC savepoint capability. |
| Inner annotation has `timeout=5` yet does not fail after 5 seconds | Inner joins T1; T1's timeout governs | Check transaction boundaries and separate query timeout. |
| Class has `@Transactional` but no advice runs | Used `new`, private/final method, self-call, proxy config | Check Spring bean lifecycle, proxy type, and visibility. |
| Test reports successful rollback even though method is not intercepted | Test method already opened a transaction | Run test outside test-managed transaction; verify data after commit/rollback. |
| `REQUIRES_NEW` causes app to hang under load | Pool exhaustion or lock contention between T1 and T2 | Measure active/idle/pending connections, lock waits, concurrent threads. |
| Inner service runs on another thread | Imperative transaction does not automatically cross threads | Create a separate boundary on the worker thread. |

### Distinguishing "a transaction exists" from "a new transaction"

The following API is often used for observation:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("active=" + active);
```

This is an **excerpt**, importing `org.springframework.transaction.support.TransactionSynchronizationManager`. `active=true` only confirms there is an active transaction on the thread. It **does not prove** inner created T2. To distinguish `REQUIRED` from `REQUIRES_NEW`, inspect rollback/commit outcomes and transaction manager info, or use a controlled test similar to section 7.

### Transaction logging in development environments

You can enable:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

These logs can help identify transaction begin, participation, suspend/resume, and commit/rollback, though details depend on the Spring version and transaction manager. Do not turn sensitive logs into public output in production; verifying actual data remains the ultimate test.

## 14. Testing tailored to each goal

1. **Test REQUIRED joining:** call outer through a Spring proxy, outer calls inner `REQUIRED`; intentionally fail at the end of outer and verify **both** inserts roll back.
2. **Test rollback-only:** inner `REQUIRED` throws an unchecked exception, outer catches it; verify outer's caller receives `UnexpectedRollbackException` and no rows commit.
3. **Test REQUIRES_NEW independence:** inner in another bean commits; outer rolls back; verify inner's data remains in the database.
4. **Test self-invocation:** place a `REQUIRES_NEW` method in the same target and call it via `this`; prove the result **differs** from calling through another bean's proxy.
5. **Test NESTED:** if the transaction manager supports savepoints, inner rolls back to the savepoint and outer commits the rest; do not assume support across every stack.
6. **Test exception rules:** compare unchecked exceptions, checked exceptions with/without `rollbackFor`. Ensure the test does not inadvertently open an outer transaction beforehand.
7. **Test pool and concurrency:** test outer + inner `REQUIRES_NEW` under multiple concurrent requests and different locks; configure realistic timeouts/pools and monitor pending connections.
8. **Test transaction manager selection:** when multiple datasources exist, verify the right manager and resource for each method.

**Pitfall in Spring TestContext:** a test method itself annotated with `@Transactional` typically opens a test-managed transaction and rolls it back at the end of the test. It can cause inner `REQUIRED` to join a transaction **opened by the test**, differing from the boundary you think you are testing. Use a test method without `@Transactional` when verifying service boundaries, or explicitly understand and control `TestTransaction` when needed.

## 15. Transaction scope design checklist

- [ ] Identify which transaction manager and database are being managed.
- [ ] Draw the call graph and mark which methods are actually called through a Spring proxy.
- [ ] Remember `@Transactional` defaults to `REQUIRED`, not automatically creating T2 if T1 already exists.
- [ ] Distinguish **logical scope** from **physical transaction**.
- [ ] Evaluate the propagation of each inner method against real business requirements.
- [ ] If using `REQUIRES_NEW`, accept independent commit/rollback and prepare an adequate pool/locking strategy.
- [ ] If using `NESTED`, verify savepoint support and rollback-to-savepoint semantics.
- [ ] If inner `REQUIRED` can fail, define the policy for rollback-only and `UnexpectedRollbackException`.
- [ ] Do not assume `try/catch` automatically makes a transaction clean again after it is marked rollback-only.
- [ ] Do not rely on `this.inner()` to trigger separate propagation annotations in proxy mode.
- [ ] Do not apply separate timeout/isolation/readOnly on inner `REQUIRED` as if they could modify an already open physical transaction.
- [ ] Test commit/rollback using database state, not just annotations or `active=true`.
- [ ] Avoid holding long-lived transactions while waiting on HTTP calls, other threads, or non-database operations.
- [ ] When multiple managers or distributed systems are involved, identify the actual boundaries of each transaction.

## 16. Self-check questions

**Question 1.** `A.foo()` and `B.bar()` both have default `@Transactional`; `A.foo()` opens T1 and calls `B.bar()` through a proxy. How many physical transactions are there?

**Answer:** Usually **one** T1, if sharing the same compatible manager/resource. `B.bar()` creates a logical scope participating in T1, with no T2.

**Question 2.** `B.bar()` declares `REQUIRES_NEW` and is called through a proxy while T1 is active. What happens?

**Answer:** T1 is suspended; an independent T2 begins; T2 finishes and then T1 is resumed. T2's commit is not undone by outer T1 rolling back.

**Question 3.** `A.foo()` calls `this.bar()` in the same bean; `bar()` declares `REQUIRES_NEW`. Is there a T2?

**Answer:** **No** under default proxy mode, because the call does not go through `bar()`'s transaction interceptor. If `foo()` already opened T1, `bar()`'s code typically runs inside T1.

**Question 4.** Inner `REQUIRED` fails, outer catches the exception, and the outer method returns normally. Is commit guaranteed?

**Answer:** **No**. If the inner interceptor marked T1 rollback-only, outer's commit is rolled back and may throw `UnexpectedRollbackException`.

**Question 5.** `NESTED` and `REQUIRES_NEW` are both "nested"; are they the same?

**Answer:** **No**. `NESTED` typically rolls back to a **savepoint on T1**, whereas `REQUIRES_NEW` creates an **independent physical T2**. If T1 later rolls back, writes in T1 disappear, while an already committed T2 remains.

## Reference materials

- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): distinguishes physical/logical transaction scopes, `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and `UnexpectedRollbackException`.
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default propagation and rollback rules.
- Spring Framework — [Understanding Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor, proxy, imperative/reactive context.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/class-based proxies and self-invocation.
- Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC transactions and savepoint/nested support.
- Spring Framework — [Testing Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): boundaries of test-managed transactions.

**Core conclusion:** A chain of calls across multiple services **does not guarantee multiple transactions**. With `REQUIRED`, multiple logical scopes typically share one physical transaction. `REQUIRES_NEW` can create an independent transaction, but must be called **through a proxy** and carries commit/rollback, connection, and locking consequences. `NESTED` is typically a savepoint within the existing transaction. Verify with **actual commit/rollback outcomes** and inspect the call graph before concluding how propagation behaves.
