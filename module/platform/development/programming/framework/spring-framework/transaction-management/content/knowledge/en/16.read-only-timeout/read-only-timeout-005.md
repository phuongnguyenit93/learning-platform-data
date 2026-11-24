# Method-Level Read-Only While Joining a Read-Write Transaction

## Core Answer

In the Spring Framework, a method marked `@Transactional(readOnly = true)` **does not automatically convert a caller's existing read–write transaction into a read-only transaction** when that method participates with `Propagation.REQUIRED` (the default value). The transaction manager continues using the **physical transaction** already opened by the outer scope, including that transaction's actual read-only flag, isolation, and timeout. Under the default configuration of common Spring managers, the inner logical scope's read-only request **is ignored for the shared physical transaction**.

Example:

```java
@Service
public class ReportService {

    @Transactional(readOnly = true)
    public Report loadReport() {
        // Reads via a repository using the same transaction manager.
        return repository.loadReport();
    }
}
```

This is an **illustrative fragment**, missing the `Report` class, `repository`, imports, and bean wiring. If a `@Transactional(readOnly = false)` service that already opened T1 calls `loadReport()` through a Spring proxy, this method **joins T1** rather than opening a read-only transaction T2. Spring does not invoke an "elevate/disable write permission" operation to change T1's read-only flag mid-flight.

For a standard imperative JDBC manager, when observed inside the inner method:

```text
OUTER T1: @Transactional(REQUIRED, readOnly=false)
    |
    +--> INNER @Transactional(REQUIRED, readOnly=true)
            |
            +-- joins T1
            +-- T1's physical readOnly remains false
            +-- inner's TransactionStatus.isNewTransaction() = false
            +-- TransactionSynchronizationManager.isCurrentTransactionReadOnly()
                typically returns false
```

**Key point:** the `readOnly=true` annotation expresses **the method's intent**, not a security barrier blocking every SQL `UPDATE`; and when **joining a read–write transaction**, it is not a directive to alter the state of the entire physical transaction. Conversely, if the method starts a **new physical transaction** (caller has no transaction, or `REQUIRES_NEW` is used), the transaction manager has the opportunity to apply the read-only hint to the new resource.

This lesson belongs to the **Read-only and timeout** group in the **Spring Framework – transaction-management** module. The goal is to accurately understand a method's read-only status **when joining a read–write transaction**, without confusing it with its effect when creating a new transaction or with database-level enforcement.

---

## 1. Distinguishing Method Intent from Running Transaction Characteristics

There are three distinct levels of information:

1. **Method-level metadata:** `@Transactional(readOnly = true)` is a declaration on a Java method or class. Spring reads it to construct a `TransactionAttribute`.
2. **Logical transaction scope:** each invocation intercepted by transaction advice can create a logical scope; this scope has its own propagation and rollback rules.
3. **Physical transaction:** an actual JDBC transaction, JPA resource transaction, or equivalent transaction managed by the manager. This is the unit actually committed or rolled back.

A common point of confusion is that **two logical scopes are not necessarily two physical transactions**.

```text
Caller
   |
   v
OrderService.submit()         outer logical scope
@Transactional(REQUIRED,      readOnly=false
               readOnly=false)
   |
   +-- physical T1 begins --------------------+
   |                                          |
   +--> ReportService.loadReport()            |
        @Transactional(REQUIRED,              |
                       readOnly=true)         |
        inner logical scope joins T1          |
        does not change T1's readOnly         |
   |                                          |
   +-- T1 commit/rollback --------------------+
```

Spring can handle rollback-only status per logical scope, yet there is only **one** physical transaction T1. When the inner method returns, T1 still belongs to the outer scope and **does not commit separately**.

This matters if a developer assumes reading data inside the inner method will run in a "read-only optimized" mode distinct from the shared connection. In a join scenario, optimizations applied **when the transaction begins** were usually decided when the outer opened T1.

## 2. `REQUIRED` Is Why the Inner Joins the Outer Transaction

`@Transactional` by default is equivalent to:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false
)
```

Changing `readOnly` to true:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true
)
public void fetchRecords() {
    // ...
}
```

**does not change propagation**. `REQUIRED` means:

- If **no physical transaction exists** for the corresponding manager: create a new transaction.
- If **a physical transaction already exists**: participate in the existing transaction.

Thus, the same method can behave differently depending on the caller:

| Invocation | State Before Method | Physical Transaction After Entering Method | Effective Read-Only |
| --- | --- | --- | --- |
| Called directly via proxy, caller has no T1 | No transaction | Opens new T1 | Manager attempts to apply `readOnly=true` |
| Outer `REQUIRED(readOnly=false)` calls inner `REQUIRED(readOnly=true)` | Read–write T1 exists | Inner joins T1 | T1 continues read-write |
| Outer `REQUIRED(readOnly=true)` calls inner `REQUIRED(readOnly=true)` | Read-only T1 exists | Inner joins T1 | Preserves T1's read-only |
| Outer `REQUIRED(readOnly=true)` calls inner `REQUIRED(readOnly=false)` | Read-only T1 exists | Inner joins T1 in lenient mode | Does not change T1 to read-write |
| Read–write outer calls inner `REQUIRES_NEW(readOnly=true)` | Read–write T1 exists | Suspends T1, opens separate T2 | Manager can apply read-only to T2 |

Do not conclude "readOnly=true always takes effect" from the code annotation alone. You must know **whether this scope starts a physical transaction** and whether the resource supports read-only.

### 2.1. When There Is No Prior Transaction

If the caller has no T1, a `REQUIRED(readOnly=true)` method opens a new T1 with the read-only hint. With JDBC, Spring can call `Connection.setReadOnly(true)` when preparing the connection. With some ORM integrations, read-only metadata can reduce flushing/dirty checking. However, there is no universal guarantee that every DB will reject `UPDATE`.

### 2.2. When a Read–Write Transaction Already Exists

If the outer already opened T1 with `readOnly=false`, Spring **does not create a new connection** merely because the inner declares `readOnly=true`; the inner's DAO can use T1's exact connection. The inner's read-only metadata does not override the physical characteristics already decided by the outer. Write operations inside T1 can still execute normally according to DB privileges.

### 2.3. Same Method, Outcome Depends on Call Context

The `loadReport()` method may initiate a read-only transaction when called standalone, yet merely join a read–write transaction when called inside a write workflow. Therefore, if you use `@Transactional(readOnly=true)` to express a **side-effect-free** API, verify both code logic and access privileges rather than relying solely on the annotation.

## 3. What Does `readOnly=true` Actually Ask Spring to Do?

Spring documentation defines `@Transactional`'s read-only as **a hint sent to the transaction subsystem**, allowing optimizations where possible. It is not a mandatory contract requiring **every database to throw an exception on writes**.

Mechanisms to keep separate:

| Layer | Example Mechanism | Meaning |
| --- | --- | --- |
| Java annotation | `@Transactional(readOnly = true)` | Declares the method/scope has read-only intent |
| Transaction manager | `TransactionDefinition.isReadOnly()` | Reads metadata when deciding to begin/join |
| Spring thread metadata | `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Read-only status of the current transaction exposed by the manager |
| JDBC connection | `Connection.setReadOnly(true)` | Hint/driver setting when preparing a connection for a new transaction |
| Optional database enforcement | SQL such as `SET TRANSACTION READ ONLY` if manager/backend matches | Can cause DML to be rejected at DB level in a genuinely read-only transaction |
| ORM integration | Provider-dependent flush mode/session read-only optimization | Can optimize entity management; does not imply DB policy matches JDBC |

When an inner **joins a read–write T1**, do not assume it is given its own read-only connection or session. The shared resource still belongs to T1 and retains T1's characteristics.

`readOnly=true` is useful for performance/API intent, but **is not an authorization mechanism**. To prevent modifying sensitive data, use DB privileges, application authorization, schema constraints, and tests.

### 3.1. Read-Only Does Not Automatically Make Data Immutable

Java objects read from a repository can still be mutated in memory. For JPA, whether a change to a managed entity is flushed down to the DB depends on the persistence context and actual flush mode. If participating in an **outer read-write transaction** with normal flushing, do not deduce that an entity mutated inside the inner will not be saved solely because the inner method declares read-only.

This is especially dangerous when a repository returns **managed entities** and code calls setters; ORM dirty checking may flush at the end of the **outer** transaction. The inner's `readOnly` annotation does not create a "read-only Java zone" with default runtime enforcement.

## 4. Mechanism of `PlatformTransactionManager` When Joining

With transaction managers in the `AbstractPlatformTransactionManager` family, the logical flow can be pictured as:

```text
Caller -> TransactionInterceptor
          |
          +-- reads method's TransactionAttribute:
          |       propagation=REQUIRED
          |       readOnly=true
          |
          +-- manager.getTransaction(definition)
                  |
                  +-- detects physical T1 already exists
                  +-- REQUIRED => participate
                  +-- does not call begin for transaction T2
                  +-- does not re-prepare connection as a new tx
                  +-- returns TransactionStatus of inner logical scope
          |
          +-- executes inner method
          +-- finishes logical scope
                  |
                  +-- if normal: does not commit T1 separately
                  +-- if exception matches rule: may mark rollback-only
```

When starting a brand-new physical transaction, the manager prepares resources and can expose transaction characteristics to Spring synchronization. When **joining**, by default the manager leniently uses the outer's characteristics; it does not re-invoke read-only connection preparation.

**Not every transaction manager has a line-by-line identical implementation to the above.** Effective characteristics depend on JDBC, JPA, JTA, reactive managers, and the specific backend. However, the rule of joining the outer transaction instead of re-applying physical read-only is the semantics Spring documents for `PROPAGATION_REQUIRED`.

### 4.1. Inner Transaction Status

`TransactionAspectSupport.currentTransactionStatus()` returns the status of the invocation intercepted by advice. An inner joining T1 typically has:

```text
isNewTransaction() = false
hasTransaction()   = true
```

Depending on Spring version configuration, `TransactionStatus.hasTransaction()` is available in Spring 6.1+; the Java example uses Spring 6.2. It indicates whether the scope is bound to an actual transaction, while `isNewTransaction()` distinguishes a new transaction belonging to this scope from participation.

`isNewTransaction() = false` **does not** mean running outside a transaction: it is also the normal result for an inner `REQUIRED` joining T1.

### 4.2. `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`

In imperative Spring, you can use:

```java
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

This is a **diagnostic fragment**, requiring imports. For an inner `REQUIRED(readOnly=true)` joining a T1 started by the outer with `readOnly=false`, the value is usually **`false`**, because Spring exposes the read-only metadata of the **outer physical transaction**.

Do not confuse the **source annotation** on the inner (which indeed is `readOnly=true`) with the **current thread metadata** (which is `false` while joining T1). Both can be true at the same time.

The check above does not by itself prove whether the database has write permissions, and should not be overused in domain logic: `TransactionSynchronizationManager` primarily serves transaction/resource infrastructure and diagnostics.

## 5. Why Isn't Read-Only "Temporarily Switched On" Mid-Transaction?

There are three reasons:

1. **Same physical resource.** Inner `REQUIRED` does not open T2; the JDBC connection/JPA persistence context is serving T1, with characteristics initialized by the outer.
2. **Read-only is a transaction/resource characteristic, not an independent modifier around every Java method.** Changing it mid-T1 could lead to contradictory behavior between SQL statements already executed and those yet to run.
3. **A transaction can interleave reads and writes.** The outer needs read-write to complete business work; if an inner switched T1 to read-only and failed to restore it properly, subsequent write operations would be unexpectedly affected.

Therefore Spring defaults to **preserving the outer's transaction characteristics**. This is a design choice regarding transaction semantics, not a bug in `@Transactional`.

### 5.1. Before–After Diagram

```text
T1 created by outer: readOnly=false
        |
        +-- UPDATE order
        +-- call inner readOnly=true
        |       +-- SELECT customer
        |       +-- may run UPDATE because T1 is still read-write
        +-- UPDATE inventory
        |
        +-- COMMIT T1
```

SQL changes are rolled back/committed according to the **shared T1**. If the inner issues a write command, the inner's `readOnly=true` annotation **does not automatically create a write-blocking checkpoint** inside T1. Use business validation, APIs, and DB permissions to control permitted write scope.

## 6. Does `validateExistingTransaction(true)` Reject This Case?

Usually **no, not solely because the inner asks for read-only**.

A transaction manager in the `AbstractPlatformTransactionManager` family allows:

```java
JdbcTransactionManager manager =
        new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

This is a **fragment**, requiring `dataSource` and imports. This flag makes the manager **validate participation** more strictly instead of leniently ignoring incompatible isolation/read-only declarations.

However, understand the **mismatch direction** Spring explicitly documents:

- **Outer T1 read-only**, inner requests **read-write** (`readOnly=false`): strict validation can **reject** it because the inner intends to do write work inside a read-only outer transaction.
- **Outer T1 read-write**, inner requests **read-only** (`readOnly=true`): that is **not** a situation required to be rejected under typical manager read-only validation. The inner normally joins T1 and the physical transaction **remains read-write**.

You cannot use `validateExistingTransaction=true` as a mechanism to enforce a "read-only zone" inside a read–write T1. Nor does it turn an inner `readOnly=true` into a read-only T2.

### 6.1. Two-Way Check Table

| Outer T1 | Inner `REQUIRED` | Default Lenient | Strict Validation Enabled |
| --- | --- | --- | --- |
| Read-write | `readOnly=true` | Joins T1, stays read-write | Normally still joins; inner's read-only not enforced |
| Read-only | `readOnly=false` | May join T1, stays read-only | Can be rejected because read-write inner joins read-only outer |
| Read-only | `readOnly=true` | Joins T1, read-only | Joins if no other mismatch |
| Read-write | `readOnly=false` | Joins T1, read-write | Joins if no other mismatch |
| Any | Inner isolation differs from outer | Joins T1, uses outer isolation | Can be rejected due to isolation mismatch |

If the inner also declares an incompatible `isolation`, strict validation can reject it **because of isolation**, even if the read-only direction is allowed. This table assumes the same manager, an active actual transaction, and no other failing characteristics.

### 6.2. Do Not Blindly Disable Strict Validation to "Fix Errors"

If an application enables strict validation and a read-write inner attempts to join a read-only outer, the problem usually lies in improper transaction boundaries or conflicting method contracts. Identify where T1 starts and the business semantics before fixing. Disabling validation merely causes the mismatch to be ignored; it does not ensure data correctness.

## 7. JDBC: A Read–Write Connection Can Still Write Inside Inner `readOnly=true`

In Spring JDBC, `JdbcTransactionManager` or `DataSourceTransactionManager` manages local transactions via a `DataSource`. `JdbcTemplate` uses `DataSourceUtils` to obtain the connection matching the transaction bound to the thread.

When a read–write outer opens T1:

```text
JdbcTransactionManager -> acquires connection C1
                         -> autoCommit=false for T1
                         -> T1's readOnly flag=false
                         -> binds C1 to thread
                               |
                               +--> outer JdbcTemplate UPDATE
                               +--> inner JdbcTemplate SELECT
                               +--> inner JdbcTemplate UPDATE
                               +--> outer JdbcTemplate UPDATE
                         -> commit/rollback C1
```

An inner `@Transactional(readOnly=true)` joining T1 **does not automatically call `Connection.setReadOnly(true)` on C1**. Thus, if schema/DB permissions allow, an UPDATE inside the inner can succeed and be committed along with the outer.

### 7.1. JDBC Read-Only Is Only a Hint by General Contract

When a **new transaction** is declared read-only, Spring normally passes the hint to `Connection.setReadOnly(true)`. JDBC drivers can interpret it differently; some backends do not hard-enforce it. Spring documentation describes `readOnly=true` as a hint, **not guaranteeing that every write access must fail**.

`DataSourceTransactionManager` has the `setEnforceReadOnly(true)` option for backends supporting strong setup via SQL like `SET TRANSACTION READ ONLY`. It runs **when preparing a new transaction** that is read-only, not as a trick to force an inner `REQUIRED(readOnly=true)` to flip the state of an existing read–write T1.

### 7.2. Ensure the `DataSource` Is Consistent

If the manager manages `DataSource A` yet the repository or `JdbcTemplate` uses `DataSource B`, code may open a valid transaction T1 while the repository's SQL **does not participate in T1**. The actual outcome may be auto-committed or coordinated by another manager. Verify the **manager, datasource identity, and connection acquisition** before blaming the `readOnly` annotation.

### 7.3. Connection Pool and Restoration

The JDBC manager is usually responsible for restoring necessary connection state when a transaction ends. Do not manually call `setReadOnly(true/false)` on a Spring-managed connection to control individual inner methods without understanding pooling and lifecycle: doing so can break outer queries/writes or leak state to the next connection borrow.

## 8. JPA/Hibernate: Read-Only Inner Does Not Guarantee Disabling Dirty Checking

In JPA/Hibernate applications, `@Transactional(readOnly=true)` on a **new transaction** can help the provider reduce overhead via flush/session optimizations; exact behavior depends on Spring/JPA provider and version.

However, when an inner service joins an **outer read-write transaction**:

- The inner typically shares the transaction/persistence context serving T1.
- The inner's method-level `readOnly` **does not automatically switch T1's entire `EntityManager`/Session to read-only**.
- If the outer uses automatic flushing/dirty checking, changes to a managed entity made inside the inner **can be flushed at the end of the outer transaction**.
- Calling `repository.save(...)` or an entity setter inside the inner is not automatically blocked by the `readOnly` annotation if the physical transaction and backend are read-write.

Illustrative example:

```java
@Service
public class CustomerViewService {
    private final CustomerRepository customers;

    public CustomerViewService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Customer loadAndRename(long id) {
        Customer customer = customers.findById(id).orElseThrow();
        customer.setName("Updated within outer transaction");
        return customer;
    }
}
```

This is a **fragment**, missing the `Customer` entity, repository, and imports. If the caller already opened a read-write T1, a managed `Customer` entity renamed inside the inner can be flushed by Hibernate when the outer commits. Do not treat the inner's `readOnly` annotation as a contract that "setters will not be persisted".

### 8.1. ORM Read-Only and DB Read-Only Are Different

A Hibernate session may use flush mode to reduce flushes; read-only entities may avoid some dirty checking. The database may use permissions or a read-only transaction mode. Both layers can coexist, yet they are not identical.

If the true requirement is **guaranteeing data is not modified**, separate read models/DTOs, avoid returning mutable entities unnecessarily, and use DB permissions or a dedicated read-only persistence unit, testing the post-commit outcome.

### 8.2. Is `@Transactional(readOnly=true)` at the Repository Layer Still Useful?

It can be beneficial when a repository method is called **standalone**, because it has the chance to open a read-only transaction or pass an appropriate hint. When the repository is called inside an outer read-write transaction, the repository method's `readOnly` does not automatically alter the physical transaction. This is normal in Spring Data JPA: the use-case transaction boundary at the service is usually more important than default annotations on individual repository methods.

## 9. Standalone Runnable Java 17 Example: Inner Read-Only Joins Outer Read-Write

### 9.1. Experiment Goal

This demo uses **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19**, and **in-memory H2 2.3.232**. There are two Spring beans:

- `OuterService` has `@Transactional(propagation=REQUIRED, readOnly=false)` to open a read–write physical transaction T1.
- `InnerService` has `@Transactional(propagation=REQUIRED, readOnly=true)` to demonstrate **standalone invocation** and **joining T1**.

The program has three parts:

1. Call inner directly from a caller without T1: inner **opens a new read-only transaction**; checks metadata only, no DB write.
2. Outer opens read-write T1 and calls inner `readOnly=true`, instructing inner to perform an `UPDATE`: the operation can commit with T1, illustrating that the annotation does not lock out writes when joining.
3. Outer opens read-write T1, inner completes `UPDATE`, then outer throws an unchecked exception: T1 rolls back, showing one shared physical transaction controls the outcome.

This is a JDBC/H2 demo; **do not** use it to infer that every database allows writes in a transaction **genuinely** created as read-only. We deliberately write only in the read-write T1 branches.

### 9.2. Maven Structure

```text
readonly-join-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ReadOnlyJoinDemo.java
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
    <artifactId>readonly-join-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
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

`spring-context` provides IoC and Java transaction configuration; `spring-jdbc` brings in the transaction infrastructure, `JdbcTemplate`, and JDBC manager. H2 is the in-memory database used at runtime. The demo's `DriverManagerDataSource` has no connection pool; production should use a pool and proper security settings.

### 9.3. Complete Java Source

File `src/main/java/demo/ReadOnlyJoinDemo.java`:

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
public class ReadOnlyJoinDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:readonly_join;DB_CLOSE_DELAY=-1");
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
    InnerService innerService(JdbcTemplate jdbc) {
        return new InnerService(jdbc);
    }

    @Bean
    OuterService outerService(InnerService inner) {
        return new OuterService(inner);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ReadOnlyJoinDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE account (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO account (id, balance) VALUES (?, ?)",
                    1, 100);

            InnerService inner = context.getBean(InnerService.class);
            OuterService outer = context.getBean(OuterService.class);

            inner.check("STANDALONE", false);

            outer.commitCase();
            System.out.println("AFTER_COMMIT=" + balance(jdbc));

            try {
                outer.rollbackCase();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_ROLLBACK=" + balance(jdbc));
        }
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1",
                Integer.class);
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = true
        )
        public void check(String label, boolean write) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println(label
                    + ": new=" + status.isNewTransaction()
                    + ", actual="
                    + TransactionSynchronizationManager
                        .isActualTransactionActive()
                    + ", readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());

            if (write) {
                jdbc.update("""
                        UPDATE account
                           SET balance = balance + 10
                         WHERE id = 1
                        """);
            }
        }
    }

    public static class OuterService {
        private final InnerService inner;

        public OuterService(InnerService inner) {
            this.inner = inner;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = false
        )
        public void commitCase() {
            System.out.println("OUTER_COMMIT: readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());
            inner.check("INNER_COMMIT", true);
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            readOnly = false
        )
        public void rollbackCase() {
            System.out.println("OUTER_ROLLBACK: readOnly="
                    + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly());
            inner.check("INNER_ROLLBACK", true);
            throw new IllegalStateException("rollback outer");
        }
    }
}
```

Why does this pattern use **two Spring-managed service beans** instead of `this.innerMethod()`? In default proxy mode, self-invocation bypasses the transaction proxy. Because `OuterService` is injected with `InnerService` from the container and calls the public method through the proxy, Spring actually sees the inner annotation and creates a `REQUIRED` logical scope joining T1.

`@EnableTransactionManagement` enables transaction annotation infrastructure. `JdbcTransactionManager` is supplied for the same `DataSource` as `JdbcTemplate`; update statements join the resource transaction when invoked inside the scope.

### 9.4. Running the Program and Reading Output

From the `readonly-join-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ReadOnlyJoinDemo
```

Lines **printed by the program itself** in the default demo environment (excluding Maven, Spring, or H2 notices/logs):

```text
STANDALONE: new=true, actual=true, readOnly=true
OUTER_COMMIT: readOnly=false
INNER_COMMIT: new=false, actual=true, readOnly=false
AFTER_COMMIT=110
OUTER_ROLLBACK: readOnly=false
INNER_ROLLBACK: new=false, actual=true, readOnly=false
CAUGHT=rollback outer
AFTER_ROLLBACK=110
```

Interpretation by branch:

1. **STANDALONE:** outside any transaction, `inner.check(..., false)` is intercepted by advice and starts a new read-only T1. Read-only metadata is `true` because the manager initializes the new transaction per the definition.
2. **OUTER_COMMIT:** caller starts read-write T2. Inner `REQUIRED(readOnly=true)` joins T2, hence `new=false`, `readOnly=false`. The `UPDATE balance += 10` runs inside T2 and commits when outer returns normally; balance rises from 100 to 110.
3. **OUTER_ROLLBACK:** a new read-write transaction T3 starts. Inner joins T3 and executes `UPDATE`; afterward outer throws `IllegalStateException`, causing T3 to roll back under default rules. Balance after the boundary remains 110, not 120.

The program intentionally **does not write data inside the STANDALONE read-only transaction**. That way it tests the exact core question: "Is an inner `readOnly=true` forced into read-only mode when joining a read-write outer?", without depending on whether H2 allows writes in a newly created read-only transaction.

### 9.5. Corresponding Assertions

An integration test can verify:

```text
Standalone inner: isNewTransaction = true,
                  currentTransactionReadOnly = true

Inside outer read-write: inner.isNewTransaction = false,
                         currentTransactionReadOnly = false

Commit scenario:  final balance = 110
Rollback scenario: final balance remains 110
```

These assertions are meaningful when the test goes through the Spring proxy and uses the same datasource/manager. If the test method itself is annotated with `@Transactional` by Spring Test, the branch you thought was "standalone" might actually join the **test transaction**, distorting the result. Avoid test-level transactions when testing self-opening transaction branches.

## 10. Variant: Using `REQUIRES_NEW` to Actually Start a Read-Only Transaction

If an operation needs to be **independent of the outer read-write transaction** and is itself read-only, you can use:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    readOnly = true
)
public Report loadIndependentReport() {
    return repository.queryReport();
}
```

This is a **fragment**, missing class/repository/imports. When the caller already has read-write T1:

```text
Outer transaction T1 (read-write)  begin ---- suspended ---- resumed ---- commit
Inner transaction T2 (read-only)             begin--read--commit
```

T2 has a separate physical transaction, so the manager can apply the read-only hint to T2. However:

- T2 usually uses a separate connection; if the pool is too small, many concurrent outer transactions waiting for inner connections can exhaust the pool.
- T2 does not see T1's uncommitted data under standard DB isolation handling; do not use T2 assuming it can read every change the outer just wrote.
- T2 can commit/roll back independently. When the outer rolls back, T2's committed result is not automatically undone.
- `readOnly=true` is still not an absolute DB permission; it depends on the resource backend.
- For a use case that simply needs to read within the outer's same snapshot, `REQUIRES_NEW` can **break consistency expectations** or waste resources. Use it only when there is a clear business reason.

**Do not use `REQUIRES_NEW` merely to "optimize" a query** sitting inside an outer read-write transaction; the benefit may not justify the cost and semantic change.

## 11. `NESTED`, `SUPPORTS`, and Other Propagations

The main question focuses on an inner `REQUIRED` joining a read-write outer, yet related propagations help avoid false assumptions:

| Inner Propagation | When Caller Already Has Read-Write T1 | Inner's Read-Only |
| --- | --- | --- |
| `REQUIRED` | Joins T1 | Does not change physical read-only of T1 |
| `SUPPORTS` | Joins T1 | Does not change physical read-only of T1 |
| `MANDATORY` | Joins T1; errors if T1 is missing | Does not change physical read-only of T1 |
| `REQUIRES_NEW` | Suspends T1, opens independent T2 | Can apply read-only to the new T2 |
| `NESTED` | Usually creates a savepoint within the same T1 when supported by manager | No new physical T2 to change read-only |
| `NOT_SUPPORTED` | Suspends T1, runs without a physical transaction | No new physical read-only transaction opened by inner |
| `NEVER` | Rejects if T1 exists | Never reaches opening a read-only transaction |

`NESTED` is not equivalent to `REQUIRES_NEW`: the savepoint still resides inside the **same physical T1**. Do not assume a nested `readOnly=true` method gets its own JDBC connection.

If an inner `SUPPORTS(readOnly=true)` is called **outside** a transaction, it does not start a physical transaction. Spring may activate transaction synchronization and pass read-only metadata for resource management in some setups, yet that is not proof that the DB has a new read-only transaction.

## 12. Rollback Rules Still Take Effect When Joining

An inner `@Transactional(readOnly=true)` method joining a read-write outer can still cause the **entire T1 to roll back**, if an exception escapes transactional advice and matches a rollback rule.

By default:

- `RuntimeException` and `Error` trigger rollback.
- Checked `Exception` usually does not trigger rollback unless a rule is added.
- Spring 6.2 has a global configuration to change the default, such as `@EnableTransactionManagement(rollbackOn=ALL_EXCEPTIONS)`; check your actual configuration.

Example:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true,
    rollbackFor = java.io.IOException.class
)
public void loadAndValidate() throws java.io.IOException {
    // If IOException escapes advice, the rollback rule is evaluated
}
```

This is an **illustrative fragment**. If the method joins a read–write T1 and `IOException` matches the rule, the transaction manager can mark T1 **rollback-only**. An outer that catches the exception and returns normally can still hit `UnexpectedRollbackException` when trying to commit.

This is why you must not conclude "all inner attributes are ignored when joining". Read-only/isolation/timeout belong to **physical characteristics**, typically owned by the outer; rollback rules belong to **logical scope completion** and can still affect T1.

### 12.1. Exception Caught Internally

If the inner catches the error and returns normally, transaction advice may not see the exception. When rollback must be forced, you can use `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` inside a valid invocation. Note that this flag prevents the shared transaction from committing as originally intended; inform the caller of the proper business outcome.

### 12.2. Do Not Turn the Read-Only Flag into a Rollback Rule

`readOnly=true` is not synonymous with "if there is an SQL UPDATE, automatically roll back". That is not a rollback condition. DB/provider mechanisms, exception rules, and business validation are needed if the system must enforce write prohibition.

## 13. Designing Service Boundaries to Avoid Misunderstandings

A common pattern:

```text
Controller / Handler
       |
       v
OrderApplicationService.checkout()   @Transactional(readOnly=false)
       |
       +--> PricingService.lookup()   @Transactional(readOnly=true)
       |                               joins outer T1
       |
       +--> InventoryService.reserve() (joins T1)
       |
       +--> OrderRepository.save()    (joins T1)
       |
       v
COMMIT T1
```

The pricing service can be called standalone, in which case its read-only hint applies to the new transaction. During checkout, it joins read-write T1. This can be the **right design**, because the whole use case needs one consistent transaction; the read-only annotation on pricing simply expresses use-case expectation when run standalone.

### 13.1. If You Want to Guarantee a Helper Does Not Modify Data

Do not rely solely on the inner `readOnly` annotation. Stronger options:

- Expose only read methods (`get...`, `find...`) in the API contract, avoiding repository write methods inside the helper.
- Return immutable DTOs or projections rather than returning mutable managed entities to read-only logic.
- Use read-only database user/role privileges or a dedicated datasource when business logic requires enforcement.
- Add static analysis/lint rules and integration tests to detect writes inside read helpers.
- Separate into an independent read transaction/scope when needed, while understanding `REQUIRES_NEW` has different semantics and cost.
- Monitor emitted SQL in test environments; verify no unexpected `UPDATE`/`INSERT` runs in read workflows.

### 13.2. If the Method Is One Step of a Writing Workflow

Place the outer transaction boundary at the **application service**, where the atomicity requirement of the entire operation is defined. Inner read helpers can declare readOnly for standalone usage; do not expect that hint to alter a physical transaction handling both reads and writes.

### 13.3. Do Not Call Annotated Methods with `this.method()`

In Spring proxy mode, self-invocation bypasses the proxy; the inner method's annotation is not read for a new advised invocation. If you truly want to test join semantics, use two Spring beans or invoke through a valid proxy.

With AspectJ weaving, self-invocation can be intercepted if real weaving is configured; flipping a single flag without weaving classes is not enough. The runnable example avoided this issue by using separate `InnerService` and `OuterService` beans.

## 14. Common Errors and Diagnostics

| Symptom / Expectation | Possible Cause | How to Check |
| --- | --- | --- |
| Inner `readOnly=true` yet `isCurrentTransactionReadOnly()` reports `false` | Inner is joining outer read-write T1 | Check inner's `isNewTransaction()` and outer's annotation |
| Inner `readOnly=true` still writes SQL successfully | Physical T1 is read-write; inner hint does not alter T1 | Verify datasource/manager and read DB after commit |
| Set `validateExistingTransaction=true` yet read-only inner still joins | Read-only validation does not require rejecting outer RW → inner RO | Understand the mismatch direction; do not treat as a bug |
| Read-write inner rejected when outer is read-only | Strict validation blocks mismatch | Adjust transaction boundary or propagation appropriately |
| Inner called standalone reports `readOnly=true` yet inside service reports `false` | One path opens new T1, the other joins old T1 | Check caller and propagation |
| JPA entity is modified despite readOnly method | Inner joins shared read-write persistence context | Check ORM dirty checking/flushing at outer commit |
| New read-only JDBC transaction still allows UPDATE | Backend/driver treats read-only only as a hint | Check DB enforcement and `setEnforceReadOnly` config where appropriate |
| Only seeing `readOnly=false` in tests | Test framework opened an outer read-write transaction | Avoid test-level transactions when testing standalone branches |
| Inner annotation has no effect | Self-invocation or bean created with `new` | Call through Spring-managed proxy |
| Data writes do not roll back despite outer transaction | DAO uses a different datasource or connection not bound to T1 | Check `JdbcTemplate`'s datasource and transaction manager |
| `UnexpectedRollbackException` on outer commit | Inner scope marked T1 rollback-only | Check exception path and rollback rules |
| Changed inner to `REQUIRES_NEW` and now cannot read data outer just wrote | T2 is an independent transaction, cannot see uncommitted T1 | Review consistency needs and whether T2 is actually needed |

### 14.1. What Should Be Logged?

In development or integration test environments, enable Spring transaction logs to observe begin, join, and commit/rollback; log JDBC or SQL if analyzing write operations. Do not carelessly enable sensitive SQL parameter/bind logging in production.

Example properties for applications with a compatible logging backend:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

This is a **logging config fragment** common in Spring Boot; it is not required for the `AnnotationConfigApplicationContext` demo in section 9.

### 14.2. Reading Status in the Right Scope

Inside an invocation with transaction advice:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
System.out.println(status.isNewTransaction());
System.out.println(
        TransactionSynchronizationManager.isCurrentTransactionReadOnly());
```

This is an illustrative snippet. If run outside advice, `currentTransactionStatus()` can throw `NoTransactionException`; if there are multiple managers/threads, the status is interpreted per the corresponding execution context.

Do not replace DB behavior verification with a boolean: read postconditions **after the transaction boundary** to prove commit/rollback outcomes.

## 15. Testing Both Call Paths Properly

A minimal integration test suite should include:

1. **Standalone read-only:** call inner through proxy from a caller with no transaction; confirm `isNewTransaction()==true` and Spring metadata `readOnly=true` (with a supporting manager).
2. **Join outer read-write:** outer starts read-write T1; inner `REQUIRED(readOnly=true)` through proxy sees `isNewTransaction()==false`, readOnly metadata `false`.
3. **Commit:** in read-write T1, perform an update from inner; confirm changes commit when outer returns.
4. **Rollback:** outer throws an unchecked exception after inner update; confirm the entire T1 rolls back.
5. **Strict validation same direction:** enable `setValidateExistingTransaction(true)` and verify read-only inner can still join read-write outer when there are no other mismatches.
6. **Strict validation reverse direction:** read-only outer, read-write inner; verify the manager rejects participation per semantics.
7. **REQUIRES_NEW:** read-only inner gets a new physical transaction and its own metadata; verify resource independence and connection pooling.
8. **ORM behavior:** in real JPA/Hibernate, mutate a managed entity in a joining inner and verify flush behavior at outer commit.
9. **Proxy interception:** avoid self-invocation and confirm the method actually passes through the Spring proxy.
10. **Resource ownership:** correct transaction manager/datasource; a different datasource may not participate in T1's rollback.

### 15.1. Spring Test Can Accidentally Create an Outer Transaction

A JUnit test method annotated with `@Transactional` can be automatically wrapped in T1 by the Spring Test framework. If you call a `readOnly=true` inner from there, you are testing the **join branch** rather than the **new-transaction branch**. When testing both, separate test configurations or call from a non-transactional context, then verify post-commit results.

### 15.2. Do Not Claim Connection-Level Enforcement From H2 Alone

The H2 example is valuable because its results and transaction metadata are deterministic, not because it represents every database. With PostgreSQL, MySQL, Oracle, and SQL Server, read-only JDBC/SQL transaction enforcement can differ. Add integration tests against the actual database/driver if the application relies on read-only enforcement.

## 16. Self-Check Questions

**Question 1.** Outer `@Transactional(readOnly=false)` opens T1. What is the default propagation of inner `@Transactional(readOnly=true)`?

**Answer:** `REQUIRED`. When outer already has T1 on the same manager, inner joins T1; it does not open its own read-only transaction.

**Question 2.** What does `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` return inside an inner joining read-write T1?

**Answer:** Under standard imperative managers, usually `false` because the current flag reflects the outer transaction T1, not the inner annotation's private metadata.

**Question 3.** Can the inner execute an `UPDATE` successfully even though its annotation is `readOnly=true`?

**Answer:** Yes, it can. Because physical T1 remains read-write, the inner annotation does not block writes by default. Check actual DB permissions and resource behavior.

**Question 4.** Does `validateExistingTransaction=true` necessarily throw an error for read-write outer, read-only inner?

**Answer:** No. Strict read-only validation primarily rejects **read-only outer, read-write inner**; the reverse direction is normally allowed to join.

**Question 5.** If the inner is called standalone when no T1 exists yet, what does `readOnly=true` mean?

**Answer:** The `REQUIRED` method opens a new T1, and the manager can pass the read-only hint to the JDBC/ORM resource when starting the transaction. It does not guarantee every DB automatically blocks DML.

**Question 6.** Should you use `REQUIRES_NEW(readOnly=true)` to always isolate inner from outer?

**Answer:** Only when business logic truly needs an independent transaction. T2 gets its own snapshot/resource, may not see T1's uncommitted data, and consumes an extra JDBC connection.

**Question 7.** Outer writes an entity, read-only inner mutates a managed entity, outer commits. Is it guaranteed the inner's change will not be flushed?

**Answer:** No. The inner joins the shared read-write persistence context; flush/dirty checking can still persist the entity. The inner's `readOnly` annotation is not an immutability guarantee.

**Question 8.** Can an exception in a read-only inner roll back a read-write T1?

**Answer:** Yes. Rollback rules are evaluated on the logical scope participating in T1, so a matching error can mark T1 rollback-only.

**Question 9.** Does `readOnly=true` mean queries will be faster in every case?

**Answer:** No. It is a hint; if the inner joins read-write T1, new-transaction read-only optimizations may not apply. Performance depends on the provider/DB/query plan.

**Question 10.** Does an inner `SUPPORTS(readOnly=true)` called outside a transaction open a read-only physical transaction?

**Answer:** No. `SUPPORTS` does not automatically open a physical transaction when none exists, although resource synchronization may use read-only metadata in some setups.

**Question 11.** Does `NESTED(readOnly=true)` inside read-write T1 get a new connection with read-only automatically applied?

**Answer:** Not under normal savepoint semantics; the nested scope uses the same physical T1 when supported by the manager.

**Question 12.** How do you accurately verify that an inner method is joining rather than opening T2?

**Answer:** Call via proxy, read `TransactionStatus.isNewTransaction()`, Spring metadata, and verify commit/rollback behavior in the DB after the outer boundary.

## 17. Checklist for Real Applications

Before depending on `readOnly=true` on a method:

- Determine **whether the method is intercepted by Spring transaction advice**, or whether self-invocation/`new` bypassed the proxy.
- Determine **whether the caller already has a physical transaction** with the same manager/resource.
- If the caller has read–write T1 and inner uses `REQUIRED`, assume by default inner **joins T1**, and the current read-only flag remains T1's.
- Check `TransactionStatus.isNewTransaction()` and Spring read-only metadata at the right place rather than inferring from the annotation alone.
- If the transaction is new, does the manager/driver/ORM support the desired read-only hint or DB enforcement?
- If **strictly no writes** are required, use APIs/DTOs/DB permissions and tests; do not treat the annotation as authorization.
- If using `validateExistingTransaction(true)`, note Spring focuses on the **outer RO + inner RW** mismatch; **outer RW + inner RO** is not necessarily rejected.
- Place the transaction boundary at the application service if the entire use case needs atomicity, avoiding pointless nested transactions.
- Consider `REQUIRES_NEW` only when an independent transaction is desired; watch snapshot visibility, connection pooling, and separate commit outcomes.
- With ORM, observe entity dirty checking/flushing when an inner joins a read-write outer.
- Verify exception/rollback rules: the read-only flag does not cancel the rollback-only mechanism of a participating scope.
- Test **standalone**, **join**, **commit**, **rollback**, **strict validation**, and the real persistence provider.

**Takeaway:** An inner method's `@Transactional(readOnly=true)` is a **declaration of preference**, while the running physical transaction has characteristics determined by the **outer boundary**. When `REQUIRED` joins a read–write T1, Spring **does not automatically convert T1 to read-only**. If an independent physical read-only transaction is truly needed, you must open a separate transaction via appropriate propagation/architecture; even then, read-only still does not replace write-permission controls.

## Official Documentation

- [Spring Framework — Transaction Propagation: participating REQUIRED and outer characteristics](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Using @Transactional and readOnly](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 API — @Transactional.readOnly](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2 API — AbstractPlatformTransactionManager.validateExistingTransaction](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework 6.2 API — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework 6.2 API — DataSourceTransactionManager.setEnforceReadOnly](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JDBC connections and Spring-managed resources](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Understanding declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)