# Default Values of propagation, isolation, and readOnly in `@Transactional`

> **Spring Framework — Transaction Management → `@Transactional`.** When you write `@Transactional` with no arguments, how does Spring handle a transaction? This lesson explains the three default values, how they interact when methods have nested transactions, and how to verify them with a standalone runnable Java 17+ example.

## 1. Three Default Values to Remember

For the `org.springframework.transaction.annotation.Transactional` annotation, the three attributes in focus default to:

| Attribute | Default value | Brief meaning |
| --- | --- | --- |
| `propagation` | `Propagation.REQUIRED` | Joins an existing transaction; starts a new transaction if none exists. |
| `isolation` | `Isolation.DEFAULT` | Uses the default isolation level provided by the resource/transaction manager; does not force a specific level like `SERIALIZABLE`. |
| `readOnly` | `false` | Does not request read-only transaction handling; read-write by default. |

The two declarations below have the **same three values**:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void placeOrder() {
    // Business logic using resources belonging to the transaction manager.
}
```

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT,
    readOnly = false
)
public void placeOrder() {
    // For the three attributes above, equivalent to parameterless @Transactional.
}
```

These two snippets are **fragments** of a method inside a Spring bean, not a standalone Java program. Transaction management configuration, an appropriate transaction manager, and calls through the Spring proxy are needed for declarative behavior to take effect.

**Rule of practice:** "Annotation default values" differ from "the physical values currently effective in the database." `REQUIRED` may *join an already-open transaction*, `DEFAULT` inherits existing isolation settings, and `readOnly=false` on a participating method may not alter the read-only nature of an outer transaction.

## 2. `Propagation.REQUIRED`: Join or Open a Transaction

### No Outer Transaction

A `@Transactional` call intercepted by Spring causes the manager to start a new transaction when no matching transaction exists.

```text
Controller / caller (no transaction yet)
       |
       v
Default @Transactional: Service.placeOrder()
       |
       +-- transaction manager starts T1
       +-- SQL 1
       +-- SQL 2
       +-- normal completion => COMMIT T1
       |
       +-- error requiring rollback => ROLLBACK T1
```

With `JdbcTransactionManager`/`DataSourceTransactionManager`, the manager coordinates the associated JDBC `Connection`. With `JpaTransactionManager`, the manager coordinates the JPA `EntityManager` and corresponding resource. `@Transactional` does not automatically pick a different manager simply based on table names or SQL in the method body.

### Outer Transaction Already Exists

Another method already has transaction T1 and calls a default `REQUIRED` method through a Spring proxy, using the same manager/resource:

```text
outer() @Transactional             [outer logical scope]
  |
  +-- start physical transaction T1
  +-- INSERT A
  |
  +-- inner() @Transactional      [inner logical scope]
  |     +-- join T1 (no second physical transaction created)
  |     +-- INSERT B
  |
  +-- COMMIT/ROLLBACK T1 for both A and B
```

**Each method can have its own logical transaction scope, yet they usually share one physical transaction** when `REQUIRED` joins under the same transaction manager. That is why a failure in `inner` can cause `outer`'s operations to roll back as well.

Do not think "every method with `@Transactional` commits on its own." With `REQUIRED`, `inner` finishing normally only completes its logical scope; physical commit still belongs to the outermost transaction boundary.

### When Inner Marks the Transaction as Rollback-Only

Suppose `inner` encounters an error that triggers rollback; Spring marks the shared transaction as `rollback-only`. If `outer` catches the exception and tries to finish normally, the transaction **still cannot commit**. When `outer` attempts to commit, Spring can throw `UnexpectedRollbackException` to report that the actual outcome is a rollback.

```java
@Service
class InnerService {
    @Transactional
    public void inner() {
        throw new IllegalStateException("invalid");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        try {
            inner.inner();
        } catch (IllegalStateException ignored) {
            // Catching the exception here does not clear T1's rollback-only status.
        }
        // When outer finishes, commit may throw UnexpectedRollbackException.
    }
}
```

This is an illustrative fragment requiring `@Service`/`@Transactional` imports and an application with a transaction manager. Whether `UnexpectedRollbackException` occurs depends on the managed transaction and when `rollback-only` is set; do not use this fragment as a standalone program.

### Quick Comparison with Other Propagation Modes

| Propagation | If a transaction already exists | If no transaction exists |
| --- | --- | --- |
| `REQUIRED` *(default)* | Joins the existing transaction | Starts a new one |
| `REQUIRES_NEW` | Suspends outer transaction and creates an independent physical transaction | Starts a new one |
| `SUPPORTS` | Joins | Can run without a real transaction |
| `MANDATORY` | Joins | Throws an error |
| `NOT_SUPPORTED` | Suspends outer transaction, runs without a transaction | Runs without a transaction |
| `NEVER` | Throws an error | Runs without a transaction |
| `NESTED` | Uses a nested boundary/savepoint if the manager supports it | Usually behaves like creating a new transaction |

The table describes the general meaning of each propagation; `NESTED` support, suspension behavior, and technical details depend on the actual `PlatformTransactionManager`. In this lesson, master **`REQUIRED` as the default** and never assume a new transaction is always created.

## 3. `Isolation.DEFAULT`: How Is the Effective Isolation Level Chosen?

**Isolation is the policy controlling whether a transaction sees data read/written by other transactions.** Isolation affects dirty reads, non-repeatable reads, phantom reads, and concurrency conflicts, though it does not replace locking strategies or contention error handling.

`Isolation.DEFAULT` means: **Spring does not ask to enforce a specific isolation level for the new transaction**. The effective level comes from the connection, database, connection pool configuration, and transaction manager.

Examples of common isolation levels:

| Spring value | General meaning |
| --- | --- |
| `DEFAULT` *(default)* | Uses the level available from the underlying resource/database. |
| `READ_UNCOMMITTED` | Allows weak isolation; visibility of uncommitted data depends on the DBMS. |
| `READ_COMMITTED` | Prevents dirty reads per standard SQL isolation model. |
| `REPEATABLE_READ` | Guarantees repeatable reads per DBMS policy; phantom handling depends on the DBMS/implementation. |
| `SERIALIZABLE` | Strongest among standard JDBC levels, but may cause waits, deadlocks, or serialization errors requiring retries. |

Do not equate Spring's default with a fixed JDBC number. For instance, PostgreSQL typically defaults to `READ COMMITTED`, while MySQL InnoDB typically defaults to `REPEATABLE READ`; server/connection configurations can change this. Hence two applications both using `@Transactional` may have different effective isolation levels.

### Why Does `DEFAULT` Not Equal `READ_COMMITTED`?

```java
@Transactional(isolation = Isolation.DEFAULT)
public void updateA() { /* ... */ }

@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateB() { /* ... */ }
```

- `updateA()` does not demand a custom isolation level. If the connection is configured as `SERIALIZABLE`, "DEFAULT" does not mean downgrading to `READ_COMMITTED`.
- `updateB()` requests `READ_COMMITTED` **when Spring starts a new transaction** and the transaction manager/database supports that level.
- If both methods **join an existing transaction** via `REQUIRED`, the outer transaction's effective isolation is usually preserved. An annotation on an inner method does not automatically change the isolation of an active transaction.

### Note on Joining an Outer Transaction

Under the lenient default policy of Spring transaction managers, an inner `@Transactional(isolation = Isolation.SERIALIZABLE)` joining a `READ_COMMITTED` transaction via `REQUIRED` normally still runs at the outer transaction's isolation; the inner request does not create another physical transaction just to apply the new level.

You can enable `validateExistingTransaction` on managers extending `AbstractPlatformTransactionManager` to reject isolation mismatches when joining an existing transaction:

```java
// Configuration fragment, when creating a JDBC transaction manager.
JdbcTransactionManager manager =
        new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

When strict validation is enabled, joining with an incompatible isolation level can be rejected, surfacing misconfigurations early. This is validation on the manager, not a way for an inner method to alter the outer's physical isolation.

### When Should You Explicitly Specify Isolation?

Consider it when business logic has specific concurrency requirements and you understand the database behavior:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void reserveUniqueResource() {
    // Just a declaration example; check DB behavior and retry mechanisms.
}
```

`SERIALIZABLE` does not magically make business logic "never fail"; the database may require retries when transactions are aborted due to contention or serialization failures. Choosing isolation should be based on invariants, actual workload, and the transaction manager/DBMS, rather than blindly raising every transaction to the highest level.

## 4. `readOnly=false`: Default Read-Write Does Not Mean "Contains Write Statements"

`@Transactional(readOnly = false)` declares that the transaction **does not request read-only mode**. This is the default value.

It does **not** mean:

- The method is required to write data.
- Spring automatically checks that the method executes `INSERT`/`UPDATE`.
- The database ignores access permissions, constraints, locks, or read-only connection settings.
- A default `readOnly=false` inner method can turn an outer read-only transaction into read-write.
- A read-write transaction cannot execute only `SELECT`; in fact, many read-only queries work completely normally in one.

Example:

```java
@Transactional // readOnly = false
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

This is a fragment using hypothetical `Account` and `repository`. Even though it only queries, the method requests a read-write transaction per default metadata. This does not make the query wrong, though with JPA, explicitly specifying `readOnly=true` when appropriate can give the provider opportunities to optimize, depending on configuration.

### What If You Switch to `readOnly=true`?

```java
@Transactional(readOnly = true)
public Account findAccount(long id) {
    return repository.findById(id).orElseThrow();
}
```

- With JDBC, the transaction manager may call `Connection.setReadOnly(true)`, which drivers commonly treat as a hint; specific configurations may cause some databases to enforce read-only at the SQL level.
- With JPA/Hibernate, Spring can optimize flush behavior and dirty checking depending on framework/provider/version.
- A database/driver may allow writes, reject writes, or behave differently in a read-only transaction. **Do not treat `readOnly=true` as an absolute write barrier or security rule.**
- When a method merely **joins** an existing outer transaction via `REQUIRED`, `readOnly=true` on the inner method does not turn the outer transaction into read-only.

Thus, the default `readOnly=false` means *no read-only hint is sent from this metadata*. It is not a command to "enable write permissions" across all resources.

### Isolation and readOnly Matter When a Transaction Begins

The `isolation`, `timeout`, and `readOnly` attributes in an annotation primarily take effect when the transaction manager starts a new physical transaction with propagation like `REQUIRED` (when no transaction exists) or `REQUIRES_NEW`. When `REQUIRED` joins an active transaction, the existing physical transaction's properties govern.

If `validateExistingTransaction=true` is enabled, certain mismatches (especially a read-write inner attempting to join a read-only outer) can be rejected instead of silently using the outer's configuration. That is why you should not assume annotations at every layer independently dictate `readOnly`/isolation.

## 5. How Do the Three Attributes Work Together?

The table below assumes methods are called **through a Spring proxy**, using the same transaction manager, matching resources, and no custom driver/provider overrides.

| Context | What does `REQUIRED` do? | Effective isolation | Effective read-only |
| --- | --- | --- | --- |
| Default method called when no T1 exists | Creates T1 | Current/default resource level | Read-write request (`false`) |
| Default method called while outer T1 is active | Joins T1 | Follows T1; does not create new isolation | Follows T1 |
| Outer T1 is `readOnly=true`, inner defaults to `readOnly=false` | Inner joins T1 | Follows T1 | T1 stays read-only per outer configuration |
| Outer T1 uses `SERIALIZABLE`, inner defaults to `DEFAULT` | Inner joins T1 | Remains T1's `SERIALIZABLE` | Follows T1 |
| Inner requests `READ_COMMITTED` while T1 is `SERIALIZABLE` | Inner joins T1 | Usually still follows T1; may error under strict validation | Follows T1 |
| Method uses `REQUIRES_NEW` | Creates new physical transaction; outer transaction is suspended | Follows new transaction's attribute / resource default | Follows new transaction's attribute |

A visual way to remember:

```text
Starting a new transaction:
    REQUIRED (when no tx exists) ──> choose isolation and readOnly for new tx
    REQUIRES_NEW               ──> choose isolation and readOnly for new tx

Joining an existing transaction:
    REQUIRED (when tx exists) ────> use existing transaction
                                      |
                                      +-- current isolation
                                      +-- current readOnly
                                      +-- shared physical commit/rollback
```

### Be Careful When Class and Method Annotations Differ

An annotation placed on a method has higher precedence than one on the class. When a method places `@Transactional` with no arguments, it uses **the defaults of the method annotation**, rather than merging undeclared attributes with the class annotation.

```java
@Transactional(readOnly = true)
@Service
public class ProductService {

    public Product view(long id) {
        // Inherits class-level @Transactional(readOnly = true) metadata.
        return repository.getReferenceById(id);
    }

    @Transactional // method override, readOnly=false by default
    public void edit(long id) {
        // This method has read-write metadata.
    }
}
```

This is an illustrative fragment. The description above applies when Spring resolves the transaction attribute on the method; runtime behavior still depends on whether an outer transaction exists. **Inside a read-only outer T1, a default `REQUIRED` `edit` method still joins T1**, so it does not automatically make T1 read-write.

## 6. Hands-On Java 17+ Example: Confirming Defaults and Shared Rollback

A complete example using Spring Framework 6.2.x, `JdbcTransactionManager`, and an H2 in-memory database. Two Spring beans have default `@Transactional`: the outer method inserts the first row, the inner method inserts the second row, and then the outer method throws `IllegalStateException`. Because `REQUIRED` is the default, both INSERTs join the same transaction and are rolled back.

A separate `@Transactional(readOnly=true)` method is included to compare the `readOnly` flag.

### 6.1. Create the Project

```text
transaction-defaults/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionDefaultsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-defaults</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TransactionDefaultsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Java Code

Create `src/main/java/dev/learning/TransactionDefaultsDemo.java`:

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionDefaultsDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:defaults;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        OuterService outerService(JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }

        @Bean
        ReadService readService(JdbcTemplate jdbc) {
            return new ReadService(jdbc);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void insertSecond() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    2, "inner");
            System.out.println(
                    "inner.active=" +
                    TransactionSynchronizationManager
                            .isActualTransactionActive());
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void saveThenFail() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    1, "outer");

            System.out.println(
                    "outer.active=" +
                    TransactionSynchronizationManager
                            .isActualTransactionActive());

            System.out.println(
                    "outer.readOnly=" +
                    TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());

            // Call through another Spring bean to go through the proxy.
            inner.insertSecond();

            throw new IllegalStateException("forced failure");
        }
    }

    public static class ReadService {
        private final JdbcTemplate jdbc;

        public ReadService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(readOnly = true)
        public int count() {
            System.out.println(
                    "readService.readOnly=" +
                    TransactionSynchronizationManager
                            .isCurrentTransactionReadOnly());
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM events", Integer.class);
        }
    }

    public static void main(String[] args) throws Exception {
        Transactional declaration =
                OuterService.class.getMethod("saveThenFail")
                        .getAnnotation(Transactional.class);

        System.out.println(
                "annotation.propagation=" +
                declaration.propagation());
        System.out.println(
                "annotation.isolation=" +
                declaration.isolation());
        System.out.println(
                "annotation.readOnly=" +
                declaration.readOnly());

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE events (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            try {
                context.getBean(OuterService.class).saveThenFail();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "caught=" + expected.getMessage());
            }

            Integer remaining = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM events", Integer.class);
            System.out.println("rowsAfterRollback=" + remaining);

            int visible = context.getBean(ReadService.class).count();
            System.out.println("rowsFromReadService=" + visible);
        }
    }
}
```

**Notable configuration details:**

- `@EnableTransactionManagement` enables `@Transactional` processing via Spring transaction infrastructure.
- `JdbcTransactionManager` receives the same `DataSource` that `JdbcTemplate` uses; the manager can bind the JDBC connection to the active transaction.
- `OuterService` and `InnerService` are two distinct beans; `inner.insertSecond()` goes through the Spring proxy, so inner's annotation is processed.
- The code inspecting annotation values via Java reflection **does not depend on a database**. Meanwhile `TransactionSynchronizationManager` checks the transaction state Spring sets while executing the method.
- `ReadService` requests `readOnly=true` in a separate transaction after the outer method has rolled back, showing that Spring's observed read-only flag differs from the `false` default.
- The rollback test intentionally throws an unchecked exception, so both rows roll back.

### 6.3. Compile and Run

Requires **JDK 17+**, Maven 3.x, and Internet access to download dependencies on the first run. In the `transaction-defaults` directory:

```bash
mvn -q clean compile exec:java
```

**Lines printed by the program in order** in this example (excluding extra Maven or logging output):

```text
annotation.propagation=REQUIRED
annotation.isolation=DEFAULT
annotation.readOnly=false
outer.active=true
outer.readOnly=false
inner.active=true
caught=forced failure
rowsAfterRollback=0
readService.readOnly=true
rowsFromReadService=0
```

Explanation:

1. Reflection reads the actual annotation on `saveThenFail()` and returns the exact three defaults.
2. `OuterService.saveThenFail()` is called through the bean proxy. It opens transaction T1 because no prior transaction exists.
3. `InnerService.insertSecond()` has `REQUIRED` propagation, so it joins T1. The two INSERTs do not create two separate physical transactions.
4. Outer throws `IllegalStateException`. Per Spring's default rollback rules, T1 is rolled back. A query outside the transaction afterward sees **0 rows**.
5. `ReadService.count()` runs in a second transaction with flag `readOnly=true`; printing `readService.readOnly=true` reports the metadata Spring applied, not proof that every write statement would be blocked by the database.

If you delete `throw new IllegalStateException(...)`, the outer method completes normally; starting with an empty table, both INSERTs commit and the row count afterward is 2. That is a scenario modification to try yourself, not the output of the code above.

### 6.4. Why Doesn't the Example Print a Fixed Actual Isolation Level?

`annotation.isolation=DEFAULT` is a **Spring metadata setting**. The actual isolation of a JDBC connection can be read at runtime via `Connection.getTransactionIsolation()`, but the returned integer depends on H2/driver and datasource configuration. You should not print a specific database result and call it "Spring's default."

To observe the effective isolation of a JDBC connection **participating in a transaction** inside a service using `JdbcTemplate`:

```java
// Fragment inside a method belonging to a Spring JDBC transaction.
Integer effectiveIsolation =
        jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Integer>)
                connection -> connection.getTransactionIsolation());

System.out.println("jdbcIsolation=" + effectiveIsolation);
```

The returned value is a JDBC constant, such as `Connection.TRANSACTION_READ_COMMITTED` (2) or `Connection.TRANSACTION_REPEATABLE_READ` (4), depending on the database and connection. In real applications, decode the integer to constant names and check your DBMS documentation for isolation details.

## 7. Explicitly Overriding Defaults When Business Requirements Demand It

Parameterless `@Transactional` should be a deliberate choice. When customization is needed, declare the exact attributes of the transaction boundary:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true
)
public ReportSummary buildIndependentReport() {
    // Fragment: uses appropriate resources of a new transaction.
}
```

Meaning:

- `REQUIRES_NEW` requests an independent physical transaction and suspends any outer transaction.
- `READ_COMMITTED` requests a specific isolation level for the new transaction, if supported by the backend.
- `readOnly=true` sends a read-only hint to the transaction infrastructure/backend; it does not guarantee every write mechanism is blocked.

However, a long reporting query does not necessarily need `REQUIRES_NEW`; independent propagation consumes extra resources and connections. If you need to guarantee it does not run inside an existing transaction, pick propagation based on real requirements, not just because "reading needs a new transaction."

### Setting readOnly on the Class, Overriding on a Method

```java
@Service
@Transactional(readOnly = true)
public class InventoryService {

    public StockView find(long productId) {
        // Uses readOnly=true from class-level annotation.
    }

    @Transactional // readOnly=false; propagation=REQUIRED; isolation=DEFAULT
    public void reserve(long productId, int amount) {
        // Method-level annotation takes precedence.
    }
}
```

This fragment assumes `StockView` is declared and cannot compile standalone. A method with its own annotation receives **the full set of defaults** for unmentioned attributes; do not think the method annotation only changes the attributes explicitly listed.

### Setting a Different Isolation on Inner Does Not Alter an Existing Transaction

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    inventoryService.inner();
}

@Transactional(isolation = Isolation.SERIALIZABLE)
public void inner() {
    // With default REQUIRED and the same manager, typically still uses
    // outer's physical transaction at READ_COMMITTED.
}
```

This illustrates the logic; in a real application both methods must be properly intercepted through Spring proxies, and inner does not change isolation on its own. If a new isolation is mandatory, evaluate `REQUIRES_NEW` and concurrency costs, or enable strict validation to reject mismatches.

## 8. Common Misunderstandings

### Mistake 1: "`REQUIRED` means every method entry opens a new connection and transaction"

Wrong. `REQUIRED` joins an existing transaction when appropriate. A call chain service A → B with the same manager can consist of two logical scopes but one physical transaction. The count of `@Transactional` annotations does not equal the count of physical transaction commits.

### Mistake 2: "`Isolation.DEFAULT` is always `READ_COMMITTED`"

Wrong. `DEFAULT` means **no specific isolation requested**, so the effective level depends on the DBMS/connection configuration. Read the connection's value and verify via datasource configuration and DBMS documentation.

### Mistake 3: "`readOnly=false` makes Spring block `SELECT` or forces writes"

Wrong. `false` simply does not enable the read-only transaction hint. `SELECT` executes normally inside a read-write transaction.

### Mistake 4: "`readOnly=true` always prevents `UPDATE`"

Do not assume this. Most APIs treat it as a hint; some backends/configs may enforce it. You must test on the specific datastore/driver. Safe write permissions must rely on DB permissions, business rules, and API design.

### Mistake 5: "If inner has `readOnly=false`, an outer `readOnly=true` turns into read-write"

Wrong when a `REQUIRED` inner joins outer's physical transaction. Outer's flag still governs the physical transaction. `validateExistingTransaction` can help catch obvious incompatibilities.

### Mistake 6: "Catching the error in outer is enough for a transaction marked rollback-only by inner to commit"

Wrong. Once an inner scope marks the physical transaction as rollback-only, outer cannot undo that merely by catching the exception. `UnexpectedRollbackException` protects the caller from mistaking a rollback for a commit.

### Mistake 7: "Calling a `@Transactional` method internally on the same object always runs advice"

Wrong in Spring's default proxy mode:

```java
public void call() {
    save(); // self-invocation: does not go through proxy.
}

@Transactional
public void save() {
    // Not automatically intercepted when called via this.save().
}
```

Extract the transaction boundary to another bean, call through a Spring-managed proxy, or consider `TransactionTemplate` when appropriate.

### Mistake 8: "Every exception rolls back by default"

In default declarative configuration, Spring rolls back when `RuntimeException` or `Error` escapes the boundary; checked `Exception`s do not trigger rollback by default. If business rules require otherwise, use `rollbackFor` or configure rollback rules:

```java
@Transactional(rollbackFor = Exception.class)
public void importData() throws Exception {
    // Even an escaping checked Exception triggers rollback.
}
```

This mistake connects directly to `REQUIRED`: when multiple operations join the same transaction and an error does not trigger rollback, the transaction can commit unexpectedly.

### Mistake 9: "`@Transactional` on a method always controls isolation/readOnly, even without a transaction manager"

An annotation is metadata. Active Spring infrastructure, an intercepted method call, a matching manager, and participating resources are required. If you do `new Service()` instead of using a Spring bean, or hit self-invocation, the defaults do not automatically produce database effects.

### Mistake 10: "Inside a reactive pipeline you can apply ThreadLocal JDBC checks verbatim"

Imperative `PlatformTransactionManager` typically binds state to a thread; `ReactiveTransactionManager` uses Reactor `Context`. With R2DBC, you need a reactive chain and matching manager. Do not use imperative `TransactionSynchronizationManager` to infer R2DBC transaction state the same way.

## 9. How to Verify Defaults in a Real Application

### Check Annotations Without Confusing Them with Runtime State

Using reflection as in Section 6's runnable example shows the three values **declared on the method**. If the annotation sits on the class or comes from a meta-annotation, use Spring's transaction attribute resolution instead of calling `getAnnotation` directly on the method.

```java
// Fragment: method and targetClass are already determined.
var source =
        new org.springframework.transaction.annotation
                .AnnotationTransactionAttributeSource();

var attributes = source.getTransactionAttribute(method, targetClass);

System.out.println(attributes.getPropagationBehavior());
System.out.println(attributes.getIsolationLevel());
System.out.println(attributes.isReadOnly());
```

This fragment requires appropriate `java.lang.reflect.Method method` and `Class<?> targetClass`; when no transactional metadata is present, `getTransactionAttribute` may return `null`. The values reflect Spring's attribute resolution; still distinguish them from the running **physical transaction**.

### Check Current Transaction State (Imperative)

Inside a method genuinely running through Spring transaction advice:

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer configuredIsolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

`configuredIsolation` may be `null` if Spring did not attach an explicit isolation level to the transaction. **`null` does not mean the database has "no isolation"**; to learn the JDBC constant in use, query the connection inside the transaction.

### Verify with Integration Tests

- Call outer from another bean through the proxy and observe the activated transaction.
- Inside one transaction, perform two INSERTs and throw an unchecked exception: verify both roll back.
- Check Spring's `readOnly` flag on default methods and `readOnly=true` methods; avoid using "INSERT did not error" as the sole test for `readOnly`.
- Set an explicit isolation level for a new transaction and read `Connection.getTransactionIsolation()`; only use levels supported by the DBMS/driver.
- Call a `REQUIRED` inner inside a read-only outer and verify the physical transaction does not automatically become read-write.
- Test the case where inner marks rollback-only and outer catches the error; verify `UnexpectedRollbackException` handling.
- If multiple datasources/transaction managers exist, verify the right manager manages the right resource; annotation defaults do not create distributed transactions.

Special note on **Spring TestContext**: transactions managed by the test framework have their own rules regarding which annotation attributes are supported; do not put `@Transactional(isolation=..., readOnly=...)` on a test method and infer that every attribute is applied by TestContext. Check in real service integration tests and the testing documentation.

## 10. A Short Code Review Checklist

| Question | What to check? |
| --- | --- |
| Is the method actually intercepted? | Spring bean/proxy, not self-invocation; `@EnableTransactionManagement` or auto-configuration. |
| Who is the transaction manager? | Right `PlatformTransactionManager`/`ReactiveTransactionManager` and resource/factory. |
| Is `REQUIRED` creating a new one or joining? | Is there a matching outer transaction before the method? |
| What effective isolation does `DEFAULT` produce? | Connection and database configuration; do not infer from the annotation. |
| Is `readOnly=false` intentional? | If read-only, is `readOnly=true` beneficial; does the provider support the hint? |
| Does an inner annotation conflict with outer? | By default inner usually follows outer's physical attributes; consider `validateExistingTransaction`. |
| Do errors roll back as required? | Unchecked/checked exceptions, caught/swallowed exceptions, rollback-only, propagation. |
| Is the transaction scope too long? | Keep the transaction open only for work requiring atomicity. |

## 11. Self-Check Questions

**Question 1:** Does parameterless `@Transactional` always open a new transaction?

*Answer:* No. `REQUIRED` joins the active transaction if one exists, and only creates a new one when no matching transaction exists.

**Question 2:** Two databases use two different default isolation levels. Can both be valid with `@Transactional(isolation=DEFAULT)`?

*Answer:* Yes. `DEFAULT` does not impose a specific isolation level; the effective level depends on the underlying resource.

**Question 3:** Outer `@Transactional(readOnly=true)` calls default `@Transactional` inner through a Spring proxy. Is inner guaranteed to be able to write?

*Answer:* No. With `REQUIRED`, inner joins outer's transaction, so outer's physical read-only attribute can still govern; write-blocking behavior depends on the backend.

**Question 4:** Is a method that only runs `SELECT` with default `readOnly=false` syntactically wrong?

*Answer:* No. `readOnly=false` does not forbid `SELECT`. You may specify `readOnly=true` when appropriate to pass an optimization hint.

**Question 5:** Why does outer still encounter `UnexpectedRollbackException` even after catching inner's error?

*Answer:* Inner caused the shared physical transaction to be marked rollback-only; catching the exception does not restore the transaction's ability to commit.

**Question 6:** Does setting `isolation=SERIALIZABLE` on a `REQUIRED` inner automatically raise the isolation of an outer currently using `READ_COMMITTED`?

*Answer:* Usually no. Inner joins the existing physical transaction; strict validation may reject the mismatch. To get a new transaction with its own isolation, design an appropriate boundary such as `REQUIRES_NEW` on a supporting resource.

## 12. Takeaways to Remember

- **`propagation=REQUIRED`:** uses an existing transaction or opens a new one if none exists.
- **`isolation=DEFAULT`:** does not request a fixed isolation level; the actual value is determined by the transaction/database/connection.
- **`readOnly=false`:** defaults to read-write, does not force writing data, and does not clear read-only from an outer transaction.
- With **inner `REQUIRED`**, physical isolation/readOnly usually follow the outer transaction. To change boundaries, check propagation and the manager rather than just adding an annotation.
- Verify with the right transaction manager, Spring proxy, integration tests, and observation of real resources.

## Official References

1. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): list of defaults, class/method precedence, and annotation attributes.
2. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, logical/physical transactions, rollback-only, `REQUIRES_NEW`.
3. [Spring Framework — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): exact defaults for `propagation`, `isolation`, and `readOnly`.
4. [Spring Framework — `TransactionDefinition`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): propagation/isolation/timeout constants and meaning of transaction settings.
5. [Spring Framework — `AbstractPlatformTransactionManager`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `validateExistingTransaction`, participating scopes, and transaction synchronization.
6. [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): specific limitations of `@Transactional` in Spring TestContext.
