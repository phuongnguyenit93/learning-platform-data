# SUPPORTS and Behavior With or Without an Active Transaction in Spring Framework

## Core Answer

`Propagation.SUPPORTS` means: **if a transaction compatible with the transaction manager in use already exists, join that transaction; if none exists, execute without starting a new physical transaction**. This is a strategy that *accepts having or not having a transaction*, not an option that automatically guarantees atomicity for every call.

```java
@Transactional(propagation = Propagation.SUPPORTS)
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

This is an **illustrative fragment**; it requires `Account`, `repository`, imports, and bean wiring. When calling the method through Spring transaction advice:

- **Caller already has transaction T1:** `findAccount` joins T1. It uses the resources and physical characteristics of T1; if the method raises an error affecting rollback, T1 may be marked rollback-only.
- **Caller has no transaction:** Spring does not open a physical transaction T2 just because it encounters the `SUPPORTS` annotation. The DAO can still read/write, but commit/rollback behavior depends on auto-commit or the resource/backend the DAO is using.
- **Common point of confusion:** in the default configuration of many Spring imperative transaction managers, `SUPPORTS` without a physical transaction **can still activate transaction synchronization**. Therefore, `TransactionSynchronizationManager.isSynchronizationActive()` can be `true` when `isActualTransactionActive()` is `false`.

Distinguish clearly: **having a Spring synchronization scope** does not mean **having a physical database transaction**. JDBC/JPA resources reused in a synchronization-only scope do not thereby become a group of SQL statements capable of atomic rollback.

This article belongs to **Spring Framework – transaction-management**, **Other Propagation** group. It introduces the standard semantics of `SUPPORTS`, Spring's resource management mechanism, usage in services/repositories, rollback rules, risks when nesting other propagations, and a standalone Java 17/Spring JDBC/H2 example.

---

## 1. What question does `SUPPORTS` answer?

Propagation is the policy by which Spring handles **the presence of a transaction at the time of entering a transactional method**. `SUPPORTS` has two branches:

```text
                   Call to @Transactional(SUPPORTS)
                                 |
                                 v
           Is there an active physical transaction with this manager?
                    /                              \
                  Yes                               No
                  |                                 |
                  v                                 v
         Join transaction T1                 Do NOT start T2
         same transaction resource           run without a physical transaction
                  |                                 |
                  v                                 v
         Completion tied to T1               SQL/ORM behaves according to resource
         rollback-only may propagate         and synchronization configuration
```

The word "SUPPORTS" should be read as "**supports the current transaction if one exists**", not "**creates a supporting transaction on its own**". Nor is it `REQUIRES_NEW` or `NESTED`.

### Branch A: transaction already exists

For example, `OrderService.placeOrder()` is a public Spring bean method `@Transactional(REQUIRED)` that has opened T1, and then calls `AccountQueryService.findAccount()` `@Transactional(SUPPORTS)` through the proxy of another bean.

```text
OrderService.placeOrder()        @Transactional(REQUIRED)
  |                              T1: started
  +--> AccountQueryService.findAccount()
                                 @Transactional(SUPPORTS)
                                 joins T1
  +--> OrderRepository.save()
                                 joins T1
  |
  v
commit T1 or rollback T1
```

`findAccount()` **does not open T2**, nor does it commit separately when returning. Its queries can participate in the same connection/persistence context as T1. If T1 rolls back, the write operations belonging to T1 also roll back.

### Branch B: no transaction exists yet

```text
HTTP handler / scheduler
  |
  +--> AccountQueryService.findAccount()
                                 @Transactional(SUPPORTS)
                                 no physical transaction
  |
  +--> laterRepository.update()
                                 may auto-commit independently
```

Spring does not set JDBC `autoCommit=false` just because a `SUPPORTS` method is called outside a transaction. A SQL statement may commit immediately upon execution according to the connection's default. Two consecutive `UPDATE` statements do not automatically become atomic just because they are in the same annotated method.

Whether a real transaction exists **cannot be inferred from the annotation alone**. You must examine the caller, propagation chain, selected transaction manager, and AOP mechanism.

## 2. Quick comparison with other propagations

| Propagation | When no transaction exists | When a transaction already exists |
| --- | --- | --- |
| `REQUIRED` (default) | **Creates a new transaction** | Joins the current transaction |
| `SUPPORTS` | **Does not create a physical transaction** | Joins the current transaction |
| `MANDATORY` | Throws an exception for missing transaction | Joins the current transaction |
| `REQUIRES_NEW` | Creates a new transaction | Suspends outer transaction, opens a new independent transaction |
| `NOT_SUPPORTED` | Runs non-transactionally | Suspends outer transaction, runs non-transactionally |
| `NEVER` | Runs non-transactionally | Throws an exception if a transaction already exists |
| `NESTED` | May create a new transaction depending on manager | Typically uses a savepoint within the same physical transaction, if supported |

Distinguish two commonly confused pairs:

- **`SUPPORTS` vs. `REQUIRED`:** both join T1 if T1 exists; the difference lies in **the branch without T1**: `REQUIRED` opens a new one, while `SUPPORTS` does not.
- **`SUPPORTS` vs. `NOT_SUPPORTED`:** when T1 exists, `SUPPORTS` **joins T1** whereas `NOT_SUPPORTED` **suspends T1** to run outside the transaction. When T1 does not exist, both can run without a physical transaction, yet they still differ in propagation policy and synchronization.

`MANDATORY` is the better choice if the method **must** run inside the caller's transaction. Do not use `SUPPORTS` as a way to "require the caller to have a transaction"; it does not reject callers that lack a transaction.

## 3. Logical scope, physical transaction, and synchronization scope

In Spring, three concepts need to be separated:

1. **Logical transaction scope:** the scope handled by `TransactionInterceptor`, `TransactionTemplate`, or `PlatformTransactionManager`. A `SUPPORTS` method invoked through a proxy can have a logical scope even when there is no database transaction.
2. **Physical transaction:** the actual commit/rollback state managed by JDBC/JPA/JTA/the resource backend. `SUPPORTS` does not create a physical transaction on its own when none exists.
3. **Transaction synchronization:** Spring's mechanism for registering callbacks and binding/reusing resources per execution thread (for imperative transactions). It can be active in an **empty transaction scope** while still having no physical transaction.

Example:

```text
SUPPORTS, caller has no transaction:
    logical scope:             YES
    physical JDBC transaction: NO
    Spring synchronization:    POSSIBLE (depends on manager/config)

SUPPORTS, caller has T1:
    logical scope:             YES
    physical JDBC transaction: YES, caller's T1
    Spring synchronization:    typically uses T1's context
```

The presence of a status object, transaction name, or synchronization callback does not mean `Connection.commit()`/`Connection.rollback()` is being managed for a new physical transaction.

This is the deep distinction of `SUPPORTS` compared to running completely without any transactional scope at all.

## 4. Why can `isSynchronizationActive()` be `true` even without a transaction?

In Spring imperative transactions, `TransactionSynchronizationManager` is the central store of **per-thread** state, including transaction characteristics, synchronization callbacks, and resources such as JDBC `ConnectionHolder`.

There are two different checks:

```java
boolean actual =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();
```

This is an **illustrative fragment**; it requires importing `org.springframework.transaction.support.TransactionSynchronizationManager`.

- `isActualTransactionActive()` asks whether Spring has marked an **actual transaction** on this thread.
- `isSynchronizationActive()` asks whether the **transaction synchronization** mechanism is currently active.
- `sync=true`, `actual=false` is a valid state when the manager enables synchronization for a `SUPPORTS` scope without a physical transaction.
- `sync=false` is not conclusive proof that no transaction exists in every environment: a manager may use a policy that disables synchronization, or the context may not have been propagated to the current thread.
- `actual=true` indicates the Spring state of the current execution; you still must verify the DAO is using the right resource, because it does not make an arbitrary JDBC connection automatically join T1.

### 4.1. Three synchronization policies

Transaction managers extending `AbstractPlatformTransactionManager` can be configured with:

| Policy | Meaning |
| --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Enables synchronization even for "empty" scopes like `SUPPORTS` with no backend transaction |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Only enables synchronization when there is an actual transaction |
| `SYNCHRONIZATION_NEVER` | Never enables transaction synchronization, even with an actual transaction |

The default of `AbstractPlatformTransactionManager` is **`SYNCHRONIZATION_ALWAYS`**. With a standard `JdbcTransactionManager`/`DataSourceTransactionManager`, when the caller has no transaction and enters `SUPPORTS`, you typically see:

```text
actual=false
sync=true
```

This is the **expected result under the default configuration stated above**, not a mandatory condition for every manager and every application context.

To enable synchronization only for actual transactions, you can configure the manager:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setTransactionSynchronization(
        AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

This is a **configuration fragment**; it requires `dataSource` and imports. When using this policy, a `SUPPORTS` call without T1 typically has `sync=false`. Changing the policy affects how resources are bound/reused and how they interact with other transaction scopes; do not change it arbitrarily in production.

`SYNCHRONIZATION_NEVER` does not mean disabling all physical transactions; it only disables the manager's synchronization infrastructure. A manager can still coordinate begin/commit/rollback according to its resource.

### 4.2. Only one transaction manager may control synchronization at a time

Transaction synchronization is thread-bound context and does not support **multiple transaction managers simultaneously controlling synchronization** on one thread in an arbitrary manner. In applications with multiple datasources/managers, nested scopes, or different resource managers, you need to determine clearly which manager owns synchronization and when it is suspended/resumed.

The Spring Javadoc also warns to use `SUPPORTS` carefully when it internally calls `REQUIRED` or `REQUIRES_NEW`: an empty synchronization scope can bind resources before the new scope begins, leading to synchronization interactions or conflicts. If this structure is hard to avoid, configure the manager appropriately—often considering **synchronization only on actual transaction**—and verify with integration tests on the specific resource.

Not every such nesting is guaranteed to fail, but you should also not assume it is always equivalent to a normal method call.

## 5. Resource reuse: same JDBC Connection yet still no atomicity

The subtlest point: when `SUPPORTS` has no physical transaction but synchronization is active, Spring can **reuse the same JDBC `Connection`** or Hibernate `Session` across the entire logical scope. This provides consistent lifecycle/resource sharing for data access code.

Consider a service using `JdbcTemplate`:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void touchTwoRows() {
    jdbcTemplate.update("UPDATE audit SET touched = touched + 1 WHERE id = 1");
    jdbcTemplate.update("UPDATE audit SET touched = touched + 1 WHERE id = 2");
}
```

This is a fragment; it requires a `jdbcTemplate` bean and an `audit` table. When there is no T1, with a synchronization-always manager and proper JDBC resource integration:

1. Spring activates synchronization for the scope.
2. `JdbcTemplate` uses `DataSourceUtils` to obtain a connection and can bind/reuse the connection across both statements.
3. **There is no `doBegin()` of a physical transaction** just because of `SUPPORTS`; the connection may still remain in its default `autoCommit=true` mode.
4. Each `UPDATE` can commit individually; if the second statement fails, the first statement may already be persisted in the DB.
5. At the end of the scope, synchronization helps clean up and release the resource; cleanup is not a rollback of already auto-committed data.

**Reusing a connection is different from transaction atomicity.** An application cannot simply check that two SQL statements used the same connection and conclude that both statements roll back together.

If a method truly requires all-or-nothing behavior, use `REQUIRED` at the appropriate transaction boundary, and ensure the DAO participates in the right resource manager.

### 5.1. Spring JDBC vs. manually opened connections

`JdbcTemplate` uses Spring's hooks (`DataSourceUtils`) to participate in resource synchronization. If code directly calls `DriverManager.getConnection(...)` or uses another datasource, that connection might **not** be managed by Spring within the scope.

Simply having `@Transactional` on a method does not automatically turn every connection into a connection managed by the transaction manager. Conversely, with `SUPPORTS` without a transaction, even a Spring-synchronized connection is not switched to manual-commit mode because of it.

### 5.2. With JPA/Hibernate

When there is no physical transaction, a persistence context/session may be created or reused according to the framework and provider's management scope. However:

- Some read queries work outside a transaction.
- Many write operations, `flush()`, or lazy access may require an actual transaction, depending on the JPA provider and configuration.
- Do not predict JPA write behavior solely from JDBC/H2 examples.
- A Session reused within a scope does not prove that the SQL ran inside the same database transaction.

The right principle is to distinguish resource synchronization, persistence context, and the backend's physical transaction.

## 6. Analyzing `TransactionStatus`: having a scope does not guarantee having a transaction

Inside an invocation managed by Spring transaction advice, you can inspect status using:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

boolean hasTx = status.hasTransaction();
boolean newTx = status.isNewTransaction();
boolean rollbackOnly = status.isRollbackOnly();
boolean completed = status.isCompleted();
```

This is an **illustrative fragment**, featuring the `hasTransaction()` API introduced in Spring Framework 6.1+. `currentTransactionStatus()` requires an appropriate transactional invocation context; calling it outside a Spring AOP transaction boundary can throw `NoTransactionException`. Section 9 provides a runnable Java 17/Spring Framework 6.2 example.

| Scenario | `hasTransaction()` | `isNewTransaction()` | `isActualTransactionActive()` | `isSynchronizationActive()` |
| --- | --- | --- | --- | --- |
| `SUPPORTS` without T1, synchronization-always manager | `false` | `false` | `false` | usually `true` |
| `SUPPORTS` joining T1 from `REQUIRED` | `true` | `false` | `true` | usually `true` |
| `REQUIRED` called when no transaction exists | `true` | `true` | `true` | usually `true` |
| Unadvised code outside any transaction | No corresponding AOP status | No corresponding AOP status | usually `false` | usually `false` |

This table assumes a standard imperative Spring manager and an appropriate datasource. If the synchronization policy differs or the transaction context is not propagated to the right thread, the last two columns may change. Several `TransactionStatus` flags are properties of the **current logical scope**, not a global statistic across all datasources.

**`isNewTransaction()==false` does not by itself mean there is no transaction**: `SUPPORTS` joining T1 also returns `false`. You must combine `hasTransaction()` with an understanding of the manager/physical resource.

### 6.1. `isCompleted()` does not tell you whether commit succeeded

A logical scope after being completed by the manager can have `isCompleted()==true` for both commit and rollback paths. While the method is running, the status is typically not yet completed. For `SUPPORTS` without a physical transaction, completed only confirms that **Spring has finished the logical scope**, not that the database ever committed or rolled back.

### 6.2. `setRollbackOnly()` in SUPPORTS without T1

If a `SUPPORTS` scope **has no physical transaction**, calling `setRollbackOnly()` on the local `TransactionStatus` cannot undo JDBC writes that already auto-committed on an independent connection. The rollback-only flag is a request on the scope's transaction status; when there is no actual resource transaction, **there is no physical transaction to roll back**.

When `SUPPORTS` **joins T1**, setting rollback-only or throwing an exception matching a rollback rule can affect T1. Therefore, business code should not use `SUPPORTS` under the assumption "if there's a transaction it rolls back, if there's no transaction it still somehow rolls back".

## 7. `@Transactional` attributes in SUPPORTS

### 7.1. `readOnly=true`: metadata/hint, not a DB transaction guarantee

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    readOnly = true
)
public CustomerDetails lookup(long customerId) {
    return repository.getCustomerDetails(customerId);
}
```

This is an illustrative fragment. When the caller already has T1, the method joins T1 and is subject to the outer physical transaction's read-only/isolation/timeout settings. When the caller has no T1, the method does not create a physical transaction just to apply `readOnly=true`; some resource management infrastructure may still receive the read-only metadata of the logical scope.

If the manager uses `SYNCHRONIZATION_ALWAYS`, you may observe `TransactionSynchronizationManager.isCurrentTransactionReadOnly()==true` in a scope without a physical transaction. That **does not mean the DB rejects every `UPDATE`**. Actual read/write permissions depend on the driver, provider, database, and specific policies.

### 7.2. `isolation` in SUPPORTS

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    isolation = Isolation.SERIALIZABLE
)
public void checkBalance() {
    // ...
}
```

This is an illustrative fragment. If there is no T1, the method does not open a physical transaction to receive `SERIALIZABLE`; if it joins T1, T1's isolation typically continues to govern. Do not treat declaring `SERIALIZABLE` as proof against dirty reads or nonrepeatable reads when called standalone.

When the requested isolation does not match the outer transaction, a manager configured with `validateExistingTransaction=true` may reject participation instead of applying the new isolation level to T1.

### 7.3. `timeout` in SUPPORTS

`@Transactional(propagation=SUPPORTS, timeout=5)` does not promise to abort the method after five seconds when **there is no physical transaction**. If joining T1, T1's deadline continues to govern the actual transaction; the inner scope does not grant a new deadline on its own.

Physical transaction timeout depends on the manager/resource. Query timeout or network timeout outside a transaction is a separate matter and must be configured at the appropriate JDBC/HTTP/client layer.

### 7.4. Rollback rules when T1 already exists

`rollbackFor`/`noRollbackFor` rules can be meaningful on a **logical scope joining T1**, because an exception escaping the inner transactional advice can mark T1 rollback-only. When there is no T1, the rules have no physical transaction to undo auto-committed SQL statements.

Distinguish **business failure** from **transaction outcome**: a method can throw an exception, yet if it ran outside a physical transaction, writes before the exception may already have committed.

## 8. AOP proxy is required for the SUPPORTS annotation to take effect

In standard Spring declarative transactions, `@Transactional` is applied through a Spring AOP proxy. This also holds for `SUPPORTS`.

```text
Caller -> Spring proxy -> TransactionInterceptor
                             |
                             +-- determine propagation=SUPPORTS
                             +-- look up active transaction
                             +-- create/join logical scope
                             +-- invoke target method
                             +-- complete scope / cleanup
```

If the same bean calls `this.supportsMethod()`, the internal call **does not go through the proxy**, so the annotation on `supportsMethod()` does not create an additional logical scope as expected. This can cause the synchronization/readOnly flags you observe to differ from calling through the bean proxy.

Illustrative example:

```java
@Service
public class ReportService {

    public void generate() {
        loadData();  // self-invocation: bypasses proxy
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void loadData() {
        // query data
    }
}
```

This is a fragment, not a standalone program. If `generate()` is non-transactional, the internal call to `loadData()` does not receive `SUPPORTS` infrastructure from the AOP proxy. To establish a clear boundary, place the annotation on `generate()` or extract `loadData()` into another injected bean.

If `generate()` is already `@Transactional(REQUIRED)`, the internal call can still run inside the **existing transaction**, but `loadData()`'s own annotation does not create an additional advice boundary. Avoid confusing these two situations.

AspectJ weaving mode can intercept self-invocation, but it requires `spring-aspects` and actual bytecode weaving; simply changing the mode configuration is not enough. For typical use cases, designing public boundaries across Spring-managed beans remains simpler.

## 9. Standalone runnable example: without T1 UPDATE auto-commits, with T1 it rolls back

A **Java 17+**, **Spring Framework 6.2.14**, **H2 in-memory 2.3.232**, **Maven 3.9+** example demonstrating both branches of `SUPPORTS`.

Objectives:

1. Call `@Transactional(SUPPORTS, readOnly=true)` outside a transaction; read `hasTransaction`, `isNewTransaction`, actual/synchronization flags, and read-only metadata.
2. Call `@Transactional(SUPPORTS)` to execute a SQL write and then throw a `RuntimeException` **outside T1**: the SQL may already have auto-committed and cannot be rolled back.
3. Reset the test balance, then have a `@Transactional(REQUIRED)` bean call the same SUPPORTS bean and let the exception propagate: the inner call **joins T1** and the update is rolled back.
4. Observe stdout to confirm that **the execution path depends on the caller**, not on changing the SUPPORTS annotation between the two runs.

### 9.1. Project structure

```text
supports-propagation-demo/
├── pom.xml
└── src/main/java/demo/SupportsDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>supports-propagation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides IoC/Java configuration, `spring-jdbc` provides `JdbcTemplate` and `JdbcTransactionManager`, and H2 is the in-memory JDBC database. The example uses only **one** transaction manager and **one** datasource to eliminate multi-resource complexities.

### 9.2. Complete Java source

File `src/main/java/demo/SupportsDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Configuration
@EnableTransactionManagement
public class SupportsDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:supports_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    SupportsService supportsService(JdbcTemplate jdbc) {
        return new SupportsService(jdbc);
    }

    @Bean
    OuterService outerService(SupportsService supports) {
        return new OuterService(supports);
    }

    public static void main(String[] args) {
        try (var ctx =
                     new AnnotationConfigApplicationContext(SupportsDemo.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            SupportsService supports = ctx.getBean(SupportsService.class);
            OuterService outer = ctx.getBean(OuterService.class);

            supports.inspect("OUTSIDE_SUPPORTS");

            try {
                supports.debitAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("OUTSIDE_FAIL=" + ex.getMessage());
            }

            System.out.println("AFTER_OUTSIDE=" + balance(jdbc));

            // Reset data to 100 to compare both branches with the same input.
            jdbc.update("UPDATE wallet SET balance = 100 WHERE id = 1");

            try {
                outer.callInnerAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("INSIDE_FAIL=" + ex.getMessage());
            }

            System.out.println("AFTER_INSIDE=" + balance(jdbc));
        }
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1",
                Integer.class);
    }

    public static class SupportsService {
        private final JdbcTemplate jdbc;

        public SupportsService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.SUPPORTS,
            readOnly = true
        )
        public void inspect(String label) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println(label
                    + ": hasTx=" + status.hasTransaction()
                    + ", new=" + status.isNewTransaction()
                    + ", actual="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive()
                    + ", sync="
                    + TransactionSynchronizationManager
                            .isSynchronizationActive()
                    + ", readOnly="
                    + TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void debitAndFail() {
            System.out.println("UPDATE: actual="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "UPDATE wallet SET balance = balance - 10 WHERE id = 1");

            throw new IllegalStateException("planned failure");
        }
    }

    public static class OuterService {
        private final SupportsService supports;

        public OuterService(SupportsService supports) {
            this.supports = supports;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void callInnerAndFail() {
            supports.inspect("INSIDE_SUPPORTS");
            supports.debitAndFail();
        }
    }
}
```

**Why are there two separate service classes?** `OuterService` receives the `SupportsService` bean from the Spring container. Therefore `supports.inspect()` and `supports.debitAndFail()` go **through the inner bean's proxy**, rather than being self-invocations within the same class. `@Transactional(SUPPORTS)` is then actually processed by Spring's transaction interceptor.

**Why use H2 and `DriverManagerDataSource`?** `DriverManagerDataSource` does not use a pool and opens JDBC connections with H2's default auto-commit for calls outside a transaction. `DB_CLOSE_DELAY=-1` keeps the in-memory database alive for the lifetime of the JVM so the program can read the balance again after each scope. This is an experiment, not a production configuration.

### 9.3. Run command

From the `supports-propagation-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SupportsDemo
```

Lines **printed by the application itself** with the default `SYNCHRONIZATION_ALWAYS` manager (excluding Maven/Spring logs):

```text
OUTSIDE_SUPPORTS: hasTx=false, new=false, actual=false, sync=true, readOnly=true
UPDATE: actual=false
OUTSIDE_FAIL=planned failure
AFTER_OUTSIDE=90
INSIDE_SUPPORTS: hasTx=true, new=false, actual=true, sync=true, readOnly=false
UPDATE: actual=true
INSIDE_FAIL=planned failure
AFTER_INSIDE=100
```

### 9.4. Result analysis

**OUTSIDE run:**

- The caller has not opened T1. `inspect()` is intercepted by advice with `SUPPORTS(readOnly=true)` but does not start a physical transaction.
- `hasTx=false`, `new=false`, `actual=false`; due to the default synchronization-always policy, `sync=true`. The scope's read-only metadata is `true` even though no DB transaction exists.
- `debitAndFail()` runs outside any physical transaction. The H2 JDBC connection has auto-commit enabled, so the `UPDATE` subtracting 10 takes effect even though the method throws an exception afterwards.
- The caller catches `IllegalStateException`; the balance read back is 90. Spring cannot roll back an auto-committed SQL statement executed outside a physical transaction.

**INSIDE run:**

- `OuterService.callInnerAndFail()` opens T1 because of `REQUIRED` and because the caller has no transaction yet.
- `inspect()` with `SUPPORTS` joins T1: `hasTx=true`, `new=false` (does not create T2), `actual=true`, `sync=true`. `readOnly=false` is the state of the outer physical transaction, even though `inspect()`'s annotation requested `readOnly=true`.
- `debitAndFail()` joins T1 and executes the `UPDATE` on the connection coordinated by the manager; `actual=true`.
- The exception escapes `debitAndFail()` and continues escaping the outer transactional invocation. The manager rolls back T1, so reading back shows the balance is still 100.

**What cannot be inferred from stdout:** isolation/timeout was not tested, multi-datasource cases were not checked, and not every JPA provider is guaranteed to behave identically to JDBC/H2. The example only demonstrates the two branches of `SUPPORTS` and the role of the resource transaction.

### 9.5. Trying a different synchronization policy

In the example, replace the `transactionManager` bean with the following snippet:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
    manager.setTransactionSynchronization(
        org.springframework.transaction.support
            .AbstractPlatformTransactionManager
            .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
    return manager;
}
```

This is a **replacement snippet**, not an additional second manager bean. Because synchronization is only enabled when an actual transaction exists, the `OUTSIDE_SUPPORTS` run will no longer show `sync=true` in the scope without T1. Other key facts remain true: without a physical transaction, JDBC SQL outside a transaction is not rolled back atomically; when the inner method joins T1, the outer physical transaction governs the outcome.

In practice, if code relies on sharing the same Session/Connection inside a SUPPORTS scope, changing the policy can alter resource lifecycles, so integration tests against your actual application and backend are needed.

## 10. Rollback and exceptions: logical scope differs from physical outcome

A `SUPPORTS` method can throw a `RuntimeException`, a checked exception, or call `setRollbackOnly()`. However, **physical rollback capability** still depends on whether it is participating in a physical transaction.

| Case | Main outcome |
| --- | --- |
| `SUPPORTS` without T1, DAO updates via auto-commit connection | Updates may already be committed; a subsequent exception is not undone by a Spring transaction |
| `SUPPORTS` joining T1, unchecked exception escapes advice | The manager may mark T1 rollback-only or the outer transaction rolls back depending on the path |
| `SUPPORTS` joining T1, checked exception escapes advice | Follows rollback rules; by default does not roll back for checked exceptions unless configured otherwise |
| `SUPPORTS` joining T1, calls `setRollbackOnly()` | Can force the shared transaction to roll back according to manager semantics |
| `SUPPORTS` without T1, calls `setRollbackOnly()` | No physical transaction exists to roll back already auto-committed SQL |

An error-prone pattern:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void updateAndMaybeFail() {
    repository.updateA();
    if (problemDetected()) {
        throw new IllegalStateException("cannot proceed");
    }
    repository.updateB();
}
```

This is an **illustrative fragment** with `repository` and `problemDetected()` undefined. When the caller has no T1, `updateA()` may already have committed before the exception. If the business contract requires both operations to commit together or roll back together, use `REQUIRED` at the true boundary.

**A subtle case:** inner `SUPPORTS` joins T1 and throws an unchecked exception; outer catches and swallows the exception and returns normally. The inner transaction advice may still have marked T1 rollback-only. When outer tries to commit, it may receive `UnexpectedRollbackException`; catching in outer does not necessarily restore the transaction's ability to commit.

Do not use `SUPPORTS` as a mechanism to hide exceptions or avoid rollbacks. Rollback rules belong to transaction advice and the manager; propagation determines which transaction can be affected.

## 11. When `SUPPORTS` wraps `REQUIRED` or `REQUIRES_NEW`

Spring documentation warns that calling stronger scopes inside `SUPPORTS` requires attention to synchronization.

```text
Caller has no transaction
    |
    +--> SUPPORTS: empty logical scope
           |
           +--> REQUIRED: manager wants to start T1
```

If `SUPPORTS` has activated synchronization and a DAO has already bound a Connection or Session, the inner `REQUIRED` must deal with the existing resource/synchronization state. Depending on the manager and resource, constraints or conflicts may arise; **do not assume this nesting is always equivalent to calling REQUIRED directly from a non-transactional caller**.

Better design alternatives:

- If the whole use case needs atomicity: place `REQUIRED` on the **outer** method from the start.
- If one layer only gathers data and conditionally opens a transaction, clearly separate the non-transactional and transactional phases into different beans/public methods.
- If you must keep an outer `SUPPORTS`, consider `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` for the corresponding manager **after** evaluating resource sharing impacts, and then test each path.
- With `REQUIRES_NEW`, you must account for resource suspension, connection pools, and T2's independent commit/rollback.

Do not manually call `DataSourceUtils.releaseConnection(...)` or `TransactionSynchronizationManager.unbindResource(...)` to fix synchronization conflicts unless you understand which transaction manager owns the resource; it easily breaks cleanup and correctness.

### 11.1. When the caller already has T1

If the caller already has T1, an outer `SUPPORTS` typically joins T1; an inner `REQUIRED` can also join T1, while an inner `REQUIRES_NEW` creates T2. This is standard propagation semantics. The synchronization-only warning primarily matters for the branch **without a physical transaction** that **already has a synchronization scope**.

### 11.2. Multiple transaction managers

If `SUPPORTS` is advised by manager A while inner `REQUIRED` uses manager B, they are not automatically in the same transaction. With thread-bound synchronization, coordinating multiple managers requires explicit design to avoid misusing resources or assuming rolling back A will roll back B. A local JDBC manager only coordinates its own resources.

## 12. When should `SUPPORTS` be used?

`SUPPORTS` makes sense when a method **can validly run both inside and outside a transaction**.

Examples:

- A **read** service used by both an order-updating transaction and a standalone query. When the caller has T1, it reads within T1; when the caller has no T1, it reads under normal database/resource mode.
- A metadata-fetching helper that does not strictly require multi-operation atomicity.
- A repository/service layer that lets callers decide the transaction boundary, with a clearly documented contract.
- Certain flows needing resource/synchronization reuse within a well-defined scope, verified against the specific transaction manager.

**Do not use `SUPPORTS`** if:

- The method writes to multiple tables/rows and must roll back together regardless of caller.
- The use case requires every call to run inside a transaction (use `MANDATORY` to fail fast when T1 is missing).
- The method requires real isolation/timeout even when called standalone (use `REQUIRED` or a stronger boundary).
- You are avoiding adding a transaction boundary just because you think `SUPPORTS` is "lightweight" and therefore still safe for writes.
- Correctness depends on whether the caller happened to open a transaction without the contract stating so.

A design rule of thumb: transaction boundaries for **business consistency** usually belong in application services; read helpers can use `SUPPORTS` if running outside a transaction is acceptable. Do not implicitly push atomicity responsibility onto the caller.

## 13. Common mistakes

### Mistake 1 — Thinking `SUPPORTS` means `REQUIRED`

`REQUIRED` opens a transaction when none exists. `SUPPORTS` **does not**. The two annotations may look identical when the caller already has T1, but behave very differently when the caller has no T1.

### Mistake 2 — Checking `isSynchronizationActive()==true` and concluding the DB is in a transaction

An empty `SUPPORTS` scope can enable synchronization without a physical transaction. Also check `isActualTransactionActive()` and the transaction manager/resource instead of conflating these two flags.

### Mistake 3 — Believing "same JDBC Connection" means "same rollback unit"

Synchronization may reuse a connection within the scope, but a connection outside a physical transaction may have auto-commit enabled. Two SQL statements run on the same connection can still commit individually. Use `REQUIRED` if atomicity is needed.

### Mistake 4 — Using `@Transactional(SUPPORTS)` for critical writes

A method works fine when the caller has T1, but silently performs partial commits when invoked standalone by a scheduler or handler. Switch to `REQUIRED` at the business boundary or use `MANDATORY` if the caller must own T1.

### Mistake 5 — Assuming `readOnly=true` always forbids writes

Read-only is typically a hint/metadata. In the SUPPORTS branch without a transaction, read-only metadata may exist in Spring's synchronization scope without enforcing DB permissions. Write access control must use DB/application policies.

### Mistake 6 — Using `setRollbackOnly()` and believing non-transactional SQL is undone

Without a physical transaction, there is no corresponding rollback unit. With JDBC auto-commit, previously succeeded SQL statements may already have committed before the setter call.

### Mistake 7 — Forgetting rollback rules on an inner call joining T1

When inner SUPPORTS has T1, an exception matching a rule can mark T1 rollback-only. Catching the exception in the outer method does not guarantee restoring the ability to commit.

### Mistake 8 — Thinking `SUPPORTS` requires a transaction

It accepts having no transaction. If the method must have T1, use `MANDATORY`; if the method is responsible for its own transaction when called standalone, use `REQUIRED`.

### Mistake 9 — Annotation is not intercepted

In proxy mode, self-invocation `this.supportsMethod()` does not create transaction advice for the inner method. Extract into another bean or place the annotation on the right public boundary, and verify the actual proxy.

### Mistake 10 — Confusing transaction context across different threads

Imperative transaction synchronization and JDBC resource binding are typically thread-bound. `@Async`, executors, or `new Thread` do not automatically transfer T1 to the new thread. A SUPPORTS method running on a worker thread may see `actual=false` even while the caller thread holds T1.

### Mistake 11 — Different synchronization configuration across environments while still asserting `sync=true`

A manager might use `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` or `SYNCHRONIZATION_NEVER`. The result of `isSynchronizationActive()` must be interpreted according to the actual configuration, not treated as an invariant of every SUPPORTS scope.

### Mistake 12 — Nesting `REQUIRED` inside an empty SUPPORTS and ignoring resource sharing warnings

The `TransactionDefinition.PROPAGATION_SUPPORTS` Javadoc warns about potential synchronization conflicts. If you need that structure, inspect the manager, connection/session lifecycle, and consider switching to an appropriate synchronization policy.

## 14. Testing `SUPPORTS` properly

A reliable test suite should have **two caller groups**:

1. **Without T1:** call the SUPPORTS bean from a non-transactional runner/handler.
2. **With T1:** call SUPPORTS from another `@Transactional(REQUIRED)` service through its proxy.
3. Read **both** `TransactionStatus.hasTransaction()` and `TransactionSynchronizationManager.isActualTransactionActive()`.
4. Check `isSynchronizationActive()` separately to see that an empty synchronization scope does not mean an actual transaction.
5. In a JDBC test environment, write a change and then throw an exception, reading the post-condition **after the boundary** to prove whether rollback occurred.
6. Test a case where the exception is caught in the outer caller; distinguish rollback-only participation from normal return.
7. Try a different manager synchronization policy in a separate test; do not change global production config just to make flag values look nice.
8. Verify resource identity: same datasource/manager, right pool, JDBC template, or ORM integration.
9. Test outer `SUPPORTS` calling inner `REQUIRED` if the architecture actually uses this pattern; observe classloader/thread/resources.
10. If using Spring Test with `@Transactional` test methods, remember that the test framework may open T1 itself. In that case, a SUPPORTS method you thought was testing "no transaction" actually **joins the test's T1**.

### 14.1. `@Transactional` test methods easily hide bugs

Example:

```java
@SpringJUnitConfig(AppConfig.class)
@Transactional
class AccountServiceTest {
    @Test
    void checkSupport() {
        service.supportsMethod();
    }
}
```

This is an **illustrative fragment**; it requires Spring Test/JUnit dependencies and real beans. When a test method is wrapped in a transaction by the Spring test framework, the SUPPORTS method sees T1, causing tests to pass even though a production handler calling outside a transaction behaves differently.

To test the branch without T1, configure the test not to open a test transaction or explicitly suspend/adjust the boundary, and verify the DB result after the scope ends.

### 14.2. Logging and observability

In an application using an appropriate logging backend, enable logs in development environments:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

This is a logging configuration fragment commonly seen in Spring Boot, **not** a required part of the `AnnotationConfigApplicationContext` example above. Logs can help inspect begin/join, suspension, synchronization, and cleanup. However, logs do not replace verifying data outcomes after the method; do not enable TRACE broadly in production without good reason.

## 15. `SUPPORTS` with reactive transactions

In the imperative Spring JDBC/JPA model, transactions and synchronization are typically bound to a **thread**. With reactive R2DBC, transaction context is propagated via the **Reactor Context**, and the transaction manager/synchronization APIs are reactive variants rather than relying on the same ThreadLocal.

What is conceptually the same: `SUPPORTS` joins a transaction if one exists; otherwise it does not start a new transaction. What **must not** be copied mechanically: calling the imperative API `TransactionSynchronizationManager.isActualTransactionActive()` inside a reactive pipeline and trusting the result to reflect an R2DBC transaction.

In reactive code, use `ReactiveTransactionManager`, `TransactionalOperator`, reactive transaction synchronization, and the appropriate reactive context. Since this article's example is imperative Java JDBC, the thread-local flags in Section 9 are only meaningful within that scope.

## 16. Self-check questions

**Question 1.** `@Transactional(SUPPORTS)` is called from a non-transactional controller. Does Spring automatically open a JDBC transaction?

**Answer:** No. `SUPPORTS` runs without a physical transaction if no compatible T1 exists. Data-access operations may auto-commit depending on the resource.

**Question 2.** `@Transactional(SUPPORTS)` is called from a `@Transactional(REQUIRED)` service that already opened T1. Does it open T2?

**Answer:** No. It joins T1; T1's physical transaction attributes typically govern the resource accesses inside.

**Question 3.** Inside a SUPPORTS scope, `isSynchronizationActive()==true` while `isActualTransactionActive()==false`. Is this a contradiction?

**Answer:** No. The manager can enable synchronization for an empty scope under the `SYNCHRONIZATION_ALWAYS` policy, even when there is no real database transaction.

**Question 4.** Two SQL statements use the same JDBC Connection in SUPPORTS without T1. If the second fails, is the first guaranteed to roll back?

**Answer:** No. If the connection auto-commits, the first statement may already have committed independently. Connection reuse does not create atomicity.

**Question 5.** If a method must definitely have a transaction whether or not the caller has one, which propagation should be used?

**Answer:** `REQUIRED`: joins if one exists, opens a new one if none exists. To require that the caller must have already opened T1, use `MANDATORY`.

**Question 6.** `SUPPORTS` with `readOnly=true` outside T1 shows metadata readOnly=true. Does that prove the DB blocks UPDATEs?

**Answer:** No. Read-only metadata/hints in Spring do not by themselves guarantee database-level enforcement.

**Question 7.** Inner SUPPORTS joins T1 and throws an unchecked exception through advice; outer catches it and returns normally. Is T1 guaranteed to commit?

**Answer:** No. The inner advice may have marked T1 rollback-only; outer commit can fail with `UnexpectedRollbackException`.

**Question 8.** To avoid synchronization-only when SUPPORTS has no T1, what option is available?

**Answer:** For managers in the `AbstractPlatformTransactionManager` family, you can consider `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`. Changing the policy must be accompanied by testing resource sharing/lifecycle.

**Question 9.** Does `this.supportsMethod()` within the same class create a SUPPORTS advice scope in proxy mode?

**Answer:** No. Self-invocation bypasses the proxy. If the outer method already has a transaction, the internal call can still run inside T1, but the inner annotation does not create a new advice boundary.

**Question 10.** Is `SUPPORTS` the same as `NOT_SUPPORTED` when the caller already has T1?

**Answer:** No. `SUPPORTS` joins T1; `NOT_SUPPORTED` suspends T1 and runs non-transactionally.

**Question 11.** Why does the Javadoc warn about SUPPORTS wrapping REQUIRED/REQUIRES_NEW?

**Answer:** Because an empty SUPPORTS scope can activate synchronization and bind resources, creating interactions with an inner boundary that wants to start a new physical transaction. Appropriate manager configuration and testing are required.

**Question 12.** A `@Transactional` test calling SUPPORTS produces `actual=true`. Can that test be used to prove SUPPORTS always opens a transaction?

**Answer:** No. The test framework created T1 beforehand; SUPPORTS merely joined it.

## 17. Codebase usage checklist

Before choosing `SUPPORTS`, ask yourself:

- Must the method guarantee **atomicity** when the caller has no transaction? If yes, `SUPPORTS` is usually not appropriate.
- Is the method called through a Spring-managed bean/proxy, or is self-invocation bypassing advice?
- Does the caller have T1 with **the same transaction manager/resource**?
- What two states are `isActualTransactionActive()` and `isSynchronizationActive()` reflecting?
- Does the DAO use `JdbcTemplate`/JPA resources participating in the manager, or open connections outside Spring's infrastructure?
- Are you relying on connection reuse or on a physical transaction? Those are two different things.
- On exceptions, could a partial commit occur outside T1 or could rollback-only propagate to an outer T1?
- Is `SYNCHRONIZATION_ALWAYS` or another policy configured? Is there an empty synchronization scope?
- Are there nested `REQUIRED`, `REQUIRES_NEW`, multiple managers, `@Async`, or test-level transactions changing the context?
- If business logic requires T1, should `MANDATORY` be used to fail fast? If it needs to create T1 itself, should `REQUIRED` be used?
- Have both the **with-transaction** and **without-transaction** caller branches been tested against a real database?

**One-sentence takeaway:** `SUPPORTS` **joins the current transaction if one exists, and runs outside a physical transaction if none exists**, even though Spring may still open a **synchronization scope** to manage resources. Only a genuine physical transaction, properly coordinated by the manager and resource, establishes the expected atomic commit/rollback boundary.

## Official References

- [Spring Framework 6.2 — `Propagation.SUPPORTS` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/annotation/Propagation.html)
- [Spring Framework 6.2 — `TransactionDefinition.PROPAGATION_SUPPORTS`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/TransactionDefinition.html)
- [Spring Framework 6.2 — `AbstractPlatformTransactionManager` and synchronization policies](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework 6.2 — `TransactionSynchronizationManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)