# Sharing the Same Resource Across Multiple Data Access Layers in Spring Transaction Management

## 1. Lesson Objectives

A business transaction rarely executes only a single SQL statement. It typically flows through **service → multiple DAOs/repositories → JDBC/ORM**. The essential requirement is that operations belonging to **the same transaction boundary** participate together in the Spring-managed transaction, rather than each DAO quietly opening its own connection and committing independently.

For example, when a funds transfer request needs to write:

1. A balance change record via `AccountDao`.
2. A transaction record via `TransactionDao`.
3. An audit log in the same database via `AuditDao`.

If all of these belong to **a single physical transaction**, they must commit together or roll back together. Splitting the code into three Java classes **does not** force Spring to create three transactions. What determines this is the **transaction boundary, transaction manager, datasource/resource factory, and how each layer acquires resources**.

After this lesson, you will be able to:

- Explain **transaction-bound resources**, `ConnectionHolder`, and `TransactionSynchronizationManager`.
- Understand why multiple `JdbcTemplate` instances or multiple DAOs using the **same `DataSource`** can share the **same JDBC `Connection` within a transaction**.
- Distinguish using the **same datasource/connection pool** from actually sharing the **same physical transaction**.
- Use `DataSourceUtils.getConnection()` / `releaseConnection()` properly when writing low-level JDBC; know when to use `TransactionAwareDataSourceProxy`.
- Design the service layer with `@Transactional`, distinguishing `REQUIRED`, `REQUIRES_NEW`, and `NESTED` with respect to the current resource.
- Verify "same resource" with a **runnable Java 17 example using Spring JDBC/H2**: multiple DAOs, an inner `REQUIRED` bean, shared connection, read-your-writes, synchronized rollback; plus a counter-example where a raw connection escapes the transaction.
- Recognize cases involving JPA/Hibernate, MyBatis, multiple datasources, JTA, `@Async`, or reactive transactions, where "same transaction" must be understood more precisely.

**Conclusion up front:** In Spring local JDBC transactions, `DataSourceTransactionManager`/`JdbcTransactionManager` can **bind a connection keyed by datasource onto the thread executing the transaction**. Data access classes using *transaction-aware* APIs and the same datasource retrieve that resource. However, a raw `dataSource.getConnection()` call or a different datasource/transaction manager can bypass that coordination.

## 2. Distinguishing: Same Object, Same DataSource, Same Transaction

The following three statements are **not equivalent**:

- **Same DAO instance:** two services can inject the same `AccountDao` bean. A shared bean **does not mean** every request uses the same connection; a singleton DAO normally serves many threads and many distinct transactions.
- **Same `DataSource`:** two DAOs can use the same datasource bean or the same connection pool. If they run at different times or outside a Spring transaction, each SQL call may borrow a **different connection** and commit separately.
- **Same physical transaction:** SQL statements actually belong to the same database transaction; with a local JDBC manager and the same datasource, they typically execute on the **same connection bound to the thread/transaction**.

Example with two concurrent requests:

```text
Request A (thread A)              Request B (thread B)
---------------------------       ---------------------------
@Service @Transactional           @Service @Transactional
          |                                 |
  JdbcTransactionManager               same manager
          |                                 |
DataSource -> Connection A         DataSource -> Connection B
          |                                 |
 AccountDao / AuditDao               AccountDao / AuditDao
  uses resource A                     uses resource B
          |                                 |
commit/rollback A                   commit/rollback B
```

Both requests share the **singleton DAO and datasource**, yet they do **not** share a physical connection simultaneously. Only operations running **within their respective transaction** reuse their own bound resource.

Within a single request:

```text
TransferService.transfer()  @Transactional(REQUIRED)
            |
            v
JdbcTransactionManager opens transaction T
            |
            +-- bind DataSource X -> ConnectionHolder(Connection C)
            |
            +-- AccountDao:
            |     JdbcTemplate(X)  -> Connection C
            |
            +-- AuditDao:
            |     JdbcTemplate(X)  -> Connection C
            |
            +-- LegacyJdbcDao:
            |     DataSourceUtils.getConnection(X) -> Connection C
            |
            +-- ALL SQL is within the same physical transaction T
            |
            +-- commit or rollback T once at the service boundary
```

Key point: "sharing the same resource" here describes the **same physical JDBC transaction**, not multiple JDBC `Statement`s on the same instance, not merely the same DB URL, and not holding one global JDBC connection shared across threads.

## 3. Mechanism for Binding Resources to a Transaction

### 3.1. Role of the Transaction Manager

For a local JDBC database, Spring provides `DataSourceTransactionManager` and its subclass `JdbcTransactionManager`:

1. When starting a **new physical transaction**, the manager borrows a `Connection` from the configured datasource.
2. The manager prepares the connection: e.g., isolation, read-only hint, and appropriate auto-commit state.
3. It wraps the connection in a `ConnectionHolder`.
4. Through `TransactionSynchronizationManager`, the holder is **bound to the thread under the datasource key** (resource binding).
5. Spring-transaction-aware data access classes look up the bound resource before acquiring a new connection themselves.
6. When the transaction completes, the manager commits/rolls back, clears the binding, restores connection state when needed, and releases the connection back to the datasource/pool.

You can picture it as:

```text
ThreadLocal resource map (conceptual model)
+----------------------------------------------------------+
| key: DataSource X                                        |
| value: ConnectionHolder -> Connection C (transaction T)  |
+----------------------------------------------------------+

TransactionSynchronizationManager:
  getResource(X) -> T's holder while bound
  hasResource(X) -> true if resource X is bound
```

This is **infrastructure machinery**, not a place where business code should call `bindResource()` or `unbindResource()` to create a transaction. Manual interference can corrupt binding state, close/lose connections at the wrong time, or prevent the transaction manager from cleaning up.

### 3.2. Resource-Bound Is Not Synonymous with Database Commit

`TransactionSynchronizationManager.isActualTransactionActive()` indicates an active actual transaction in Spring's context. `isSynchronizationActive()` indicates that resource synchronization is active. These two indicators are not synonymous across all propagations/configurations; in particular, synchronization can be active outside a physical transaction.

Merely seeing:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

is not enough to conclude that an SQL statement on datasource **Y** is managed by datasource **X**'s transaction manager. You must inspect the exact resource key, manager, and connection acquisition path. In local JDBC, each datasource only has its own transaction context; Spring does not automatically combine connections from all datasources into a single distributed transaction.

### 3.3. Under Which Key Is the Resource Managed?

`TransactionSynchronizationManager` uses the resource factory as the key—in JDBC, typically the `DataSource` bean managed by the transaction manager. Therefore:

- **The exact same datasource bean** in the transaction manager and DAOs is the most predictable setup.
- **Two different datasource beans**, even with the same URL, username, and underlying connection pool, **do not automatically guarantee** they share the same bound connection.
- **Proxy wrappers** such as `TransactionAwareDataSourceProxy`, `LazyConnectionDataSourceProxy`, or routing datasources must be configured in the proper order; classes may unwrap/delegate according to specific rules. Do not rearrange wrappers arbitrarily and assume resource keys still match.
- With multiple datasources, each datasource may have its own connection bound on the same thread; **having multiple resource bindings** does not mean they belong to **one shared atomic DB transaction**.

## 4. `JdbcTemplate`: The Best Default Integration Path

In JDBC, the standard and Spring-recommended approach is to inject `JdbcTemplate` or `NamedParameterJdbcTemplate` into DAOs:

```java
@Repository
public class AccountDao {
    private final JdbcTemplate jdbc;

    public AccountDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void debit(long accountId, long amount) {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, accountId
        );
    }
}

@Repository
public class AuditDao {
    private final JdbcTemplate jdbc;

    public AuditDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String action) {
        jdbc.update(
            "INSERT INTO audit_events(action) VALUES (?)",
            action
        );
    }
}
```

These are **two example classes in a Spring application**, not a standalone program; they require imports, datasource/schema, and a transaction manager. Both DAOs can be invoked from a service:

```java
@Service
public class TransferService {
    private final AccountDao accounts;
    private final AuditDao audits;

    public TransferService(AccountDao accounts, AuditDao audits) {
        this.accounts = accounts;
        this.audits = audits;
    }

    @Transactional
    public void debitAndAudit(long accountId, long amount) {
        accounts.debit(accountId, amount);
        audits.insert("DEBIT");
        // If a RuntimeException escapes the method, the transaction typically rolls back
        // both the UPDATE and INSERT under default rules.
    }
}
```

**Why don't the two DAOs commit separately?** `JdbcTemplate` acquires connections via `DataSourceUtils`, so if the transaction manager has already bound a resource for the datasource, SQL calls join the active transaction. Marking a DAO bean with `@Repository` or `@Bean` **does not** turn it into an independent transaction; boundaries are determined by `@Transactional`/`TransactionTemplate` and propagation.

### 4.1. Do You Need Exactly One `JdbcTemplate` Instance Application-Wide?

No. Two DAOs can have **two distinct `JdbcTemplate` objects** constructed with the **same `DataSource` bean**:

```java
JdbcTemplate accountJdbc = new JdbcTemplate(dataSource);
JdbcTemplate auditJdbc   = new JdbcTemplate(dataSource);
```

The two templates are different instances, yet both perform connection lookup through the Spring-aware mechanism. **Sharing does not reside in the template object**—it resides in the datasource and transaction context.

Conversely, a single `JdbcTemplate` bean can still handle many distinct transactions across different threads. Do not store a `Connection` in a singleton field just to "force all DAOs to share it."

### 4.2. When One DAO Calls Another DAO

If a service calls `AccountDao`, which in turn calls `AuditDao`, both can still use the same bound resource when the call stack runs synchronously in the same transaction/thread. From a design standpoint, however, it is usually cleaner for **service orchestration** to define transaction boundaries while DAOs focus on SQL/persistence.

Do not place `@Transactional(REQUIRES_NEW)` casually on the audit DAO just to "ensure audit logging." That propagation creates a **different physical transaction**, alters atomicity semantics, and introduces pool/lock risks.

## 5. When Low-Level JDBC Must Be Written: `DataSourceUtils`

If a legacy class must work directly with `java.sql.Connection` / `PreparedStatement`, use:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try {
    try (PreparedStatement ps = con.prepareStatement(
            "INSERT INTO audit_events(action) VALUES (?)")) {
        ps.setString(1, "CHECKOUT");
        ps.executeUpdate();
    }
} catch (SQLException ex) {
    throw new IllegalStateException("JDBC operation failed", ex);
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

This is a **snippet inside a class holding a datasource**, requiring imports, illustrating a DAO using a JDBC transaction manager. Key essentials:

1. `DataSourceUtils.getConnection(dataSource)` prefers the connection already bound by Spring to the thread, if present; when no matching resource exists, it can obtain a new connection from the datasource.
2. `DataSourceUtils.releaseConnection(con, dataSource)` is a **transaction-aware** release operation. If the connection is still bound to a Spring transaction, the helper **does not close the active physical transaction connection itself**; cleanup will be handled by the transaction manager.
3. **Properly close `Statement`/`ResultSet` objects** created by the DAO, but do not call `con.commit()`, `con.rollback()`, `con.setAutoCommit(true)`, or `con.close()` directly on a Spring-managed connection.
4. Timeout/statement settings may also require `DataSourceUtils.applyTransactionTimeout(...)`; `JdbcTemplate` handles much of this for you.
5. Outside a Spring transaction, the helper can still supply a normal connection and `releaseConnection` will close/release it appropriately. **Do not** treat calling `getConnection()` as an automatic "start transaction" command.

### 5.1. Why Is Calling `dataSource.getConnection()` Directly Dangerous?

A plain JDBC DAO:

```java
try (Connection con = dataSource.getConnection()) {
    try (PreparedStatement ps =
            con.prepareStatement("INSERT INTO events(label) VALUES (?)")) {
        ps.setString(1, "external");
        ps.executeUpdate();
    }
}
```

With `DriverManagerDataSource` or a standard connection pool, this call may acquire a **different physical connection** with `autoCommit=true`. Even though the caller is inside Spring's `@Transactional`, the operation on the new connection **can commit independently**, failing to roll back when outer fails. This often causes subtle data-consistency bugs.

However, do not claim that every `DataSource.getConnection()` escapes the transaction: a **`TransactionAwareDataSourceProxy`** is designed so legacy code using standard datasource APIs can still participate in a Spring-managed transaction; application-server-managed/JTA datasources may have their own behavior. Distinguish **which datasource was passed to the code** and **which transaction coordinator is active**.

### 5.2. `TransactionAwareDataSourceProxy` for Legacy Libraries

When a library is **forced** to call `DataSource.getConnection()`, you can pass it a `TransactionAwareDataSourceProxy`:

```java
DataSource targetDataSource = /* actual datasource */;
DataSource legacyView =
    new TransactionAwareDataSourceProxy(targetDataSource);

// Library only knows javax.sql.DataSource:
legacyLibrary.setDataSource(legacyView);
```

This is an **illustrative snippet**; `legacyLibrary` is supplied by the application. The proxy returns transaction-aware connection handles so `getConnection()`/`close()` calls align with Spring resource management. **Do not** wrap every new DAO in this proxy out of habit: Spring prefers `JdbcTemplate`/`DataSourceUtils`.

When configuring the manager, pass the **target datasource** (or the proxy type handled properly by the transaction manager) rather than mixing up wrappers. Run real integration tests before stacking multiple `DataSourceProxy` or routing/lazy proxies.

## 6. Runnable Java 17 Example: Multiple DAOs Sharing One Connection, Committing/Rolling Back Together

This lab uses **Spring Framework 6.2**, **JDBC**, **in-memory H2**, and **`JdbcTransactionManager`**. It includes:

- `LedgerDao` using one `JdbcTemplate`.
- `AuditDao` using **another `JdbcTemplate`**, on the same datasource.
- `AuditService` as a separate bean declaring `@Transactional(propagation = REQUIRED)` and invoked through a Spring proxy.
- `RawDao` using `DataSourceUtils.getConnection` + `PreparedStatement`.
- `OuterService` opening the transaction and orchestrating the three DAOs.
- `UnsafeDao` deliberately calling `dataSource.getConnection()` directly in a counter-example scenario.

Observations:

1. **SUCCESS**: multiple DAOs operate within the same transaction; inner `REQUIRED` joins the outer transaction, and all records commit together.
2. **ROLLBACK**: outer throws an unchecked exception; records written by `LedgerDao`, `AuditDao`, and `RawDao` are all rolled back.
3. **UNSAFE**: a DAO opens a **non-transaction-aware** connection to the datasource and writes to a separate table (to avoid lock contention in the demo), auto-committing that record; outer rolls back, yet `UnsafeDao`'s record remains.

**Verification method:** use `DataSourceUtils.getConnection` in the DAOs to compare the **identity of the bound connection** with the outer connection. This is only a reasonable infrastructure measurement with `JdbcTransactionManager` + `DriverManagerDataSource` in a demo; do not write production business logic relying on `Connection == Connection` comparisons across different proxies/drivers. More decisive verification remains **read-your-writes and atomic commit/rollback**.

### 6.1. Directory Structure

```text
spring-shared-resource-demo/
├── pom.xml
└── src/main/java/com/example/resource/Main.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-shared-resource-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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

`spring-context` provides context/beans/AOP, `spring-jdbc` provides `JdbcTemplate` and the transaction manager, and H2 is the in-memory JDBC database. Spring Boot is not needed. Java 17 is the minimum runtime for Spring 6.x. `DriverManagerDataSource` is suitable for a demo, not for a production connection pool.

### 6.3. `src/main/java/com/example/resource/Main.java`

```java
package com.example.resource;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:shared_resource;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public LedgerDao ledgerDao(DataSource ds) {
            return new LedgerDao(ds);
        }

        @Bean
        public AuditDao auditDao(DataSource ds) {
            return new AuditDao(ds);
        }

        @Bean
        public RawDao rawDao(DataSource ds) {
            return new RawDao(ds);
        }

        @Bean
        public UnsafeDao unsafeDao(DataSource ds) {
            return new UnsafeDao(ds);
        }

        @Bean
        public AuditService auditService(AuditDao auditDao) {
            return new AuditService(auditDao);
        }

        @Bean
        public OuterService outerService(
                DataSource ds, LedgerDao ledger, AuditDao audit,
                RawDao raw, AuditService auditService, UnsafeDao unsafe) {
            return new OuterService(ds, ledger, audit, raw,
                    auditService, unsafe);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }
    }

    // Shared utility ONLY for observation purposes in the demo.
    private static boolean sameBoundConnection(
            DataSource ds, Connection expected) {
        Connection current = DataSourceUtils.getConnection(ds);
        try {
            return current == expected;
        } finally {
            DataSourceUtils.releaseConnection(current, ds);
        }
    }

    public static class LedgerDao {
        private final DataSource ds;
        private final JdbcTemplate jdbc;

        public LedgerDao(DataSource ds) {
            this.ds = ds;
            this.jdbc = new JdbcTemplate(ds);
        }

        public void insert(String label) {
            jdbc.update(
                "INSERT INTO ledger_entries(label) VALUES (?)", label
            );
        }

        public boolean same(Connection expected) {
            return sameBoundConnection(ds, expected);
        }
    }

    public static class AuditDao {
        private final DataSource ds;
        private final JdbcTemplate jdbc;

        public AuditDao(DataSource ds) {
            this.ds = ds;
            this.jdbc = new JdbcTemplate(ds);
        }

        // Query via a DIFFERENT JdbcTemplate instance from LedgerDao.
        public boolean seesLedger(String label) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger_entries WHERE label = ?",
                Integer.class,
                label
            );
            return count != null && count > 0;
        }

        public void insert(String label) {
            jdbc.update(
                "INSERT INTO audit_entries(label) VALUES (?)", label
            );
        }

        public boolean same(Connection expected) {
            return sameBoundConnection(ds, expected);
        }
    }

    public static class RawDao {
        private final DataSource ds;

        public RawDao(DataSource ds) {
            this.ds = ds;
        }

        public boolean insertAndSame(String label, Connection expected) {
            Connection con = DataSourceUtils.getConnection(ds);
            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO raw_entries(label) VALUES (?)")) {
                ps.setString(1, label);
                ps.executeUpdate();
                return con == expected;
            } catch (SQLException ex) {
                throw new IllegalStateException("raw JDBC failed", ex);
            } finally {
                DataSourceUtils.releaseConnection(con, ds);
            }
        }
    }

    // COUNTER-EXAMPLE: calling datasource.getConnection() directly,
    // bypassing DataSourceUtils; this H2 connection auto-commits.
    public static class UnsafeDao {
        private final DataSource ds;

        public UnsafeDao(DataSource ds) {
            this.ds = ds;
        }

        public boolean insertOutside(String label) {
            try (Connection con = ds.getConnection();
                 PreparedStatement ps = con.prepareStatement(
                     "INSERT INTO outside_entries(label) VALUES (?)")) {
                ps.setString(1, label);
                ps.executeUpdate();
                return con.getAutoCommit();
            } catch (SQLException ex) {
                throw new IllegalStateException("unsafe SQL failed", ex);
            }
        }
    }

    public static class AuditService {
        private final AuditDao audit;

        public AuditService(AuditDao audit) {
            this.audit = audit;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void record(String label, Connection expected) {
            boolean newTx = TransactionAspectSupport
                    .currentTransactionStatus()
                    .isNewTransaction();
            System.out.println("audit newTransaction=" + newTx);

            audit.insert(label);
            System.out.println(
                "audit sameConnection=" + audit.same(expected)
            );
        }
    }

    public static class OuterService {
        private final DataSource ds;
        private final LedgerDao ledger;
        private final AuditDao audit;
        private final RawDao raw;
        private final AuditService auditService;
        private final UnsafeDao unsafe;

        public OuterService(
                DataSource ds, LedgerDao ledger, AuditDao audit,
                RawDao raw, AuditService auditService, UnsafeDao unsafe) {
            this.ds = ds;
            this.ledger = ledger;
            this.audit = audit;
            this.raw = raw;
            this.auditService = auditService;
            this.unsafe = unsafe;
        }

        private void writeAll(String label) {
            Connection expected = DataSourceUtils.getConnection(ds);
            try {
                System.out.println(
                    "outer active=" +
                    TransactionSynchronizationManager
                        .isActualTransactionActive() +
                    " bound=" +
                    TransactionSynchronizationManager.hasResource(ds)
                );

                ledger.insert(label);
                System.out.println(
                    "ledger sameConnection=" + ledger.same(expected)
                );

                System.out.println(
                    "audit seesLedgerWrite=" + audit.seesLedger(label)
                );
                auditService.record(label, expected);
                System.out.println(
                    "raw sameConnection=" +
                    raw.insertAndSame(label, expected)
                );
            } finally {
                DataSourceUtils.releaseConnection(expected, ds);
            }
        }

        @Transactional
        public void successful() {
            writeAll("success");
        }

        @Transactional
        public void failed() {
            writeAll("rollback");
            throw new IllegalStateException("force rollback");
        }

        @Transactional
        public void unsafeMix() {
            ledger.insert("not-committed");
            boolean autoCommit = unsafe.insertOutside("outside-committed");
            System.out.println("outside autoCommit=" + autoCommit);
            throw new IllegalStateException("unsafe outer rollback");
        }
    }

    private static int count(JdbcTemplate jdbc, String tableName) {
        // tableName only accepts CONSTANTS hard-coded in Main, not
        // taken from user input.
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + tableName,
            Integer.class
        );
        return value;
    }

    private static String counts(JdbcTemplate jdbc) {
        return "ledger=" + count(jdbc, "ledger_entries") +
            ",audit=" + count(jdbc, "audit_entries") +
            ",raw=" + count(jdbc, "raw_entries") +
            ",outside=" + count(jdbc, "outside_entries");
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE ledger_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE audit_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE raw_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE outside_entries (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," +
                "label VARCHAR(80) NOT NULL)"
            );

            OuterService outer = context.getBean(OuterService.class);

            System.out.println("=== SUCCESS ===");
            outer.successful();
            System.out.println("after success " + counts(jdbc));

            System.out.println("=== ROLLBACK ===");
            try {
                outer.failed();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("after rollback " + counts(jdbc));

            System.out.println("=== UNSAFE GET_CONNECTION ===");
            try {
                outer.unsafeMix();
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }
            System.out.println("after unsafe " + counts(jdbc));
        }
    }
}
```

### 6.4. Run Command

Install JDK 17+ and Maven. In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.resource.Main
```

**Expected output printed by the program itself** on H2 with the example configuration (excluding Maven/SLF4J messages if any):

```text
=== SUCCESS ===
outer active=true bound=true
ledger sameConnection=true
audit seesLedgerWrite=true
audit newTransaction=false
audit sameConnection=true
raw sameConnection=true
after success ledger=1,audit=1,raw=1,outside=0
=== ROLLBACK ===
outer active=true bound=true
ledger sameConnection=true
audit seesLedgerWrite=true
audit newTransaction=false
audit sameConnection=true
raw sameConnection=true
caught=force rollback
after rollback ledger=1,audit=1,raw=1,outside=0
=== UNSAFE GET_CONNECTION ===
outside autoCommit=true
caught=unsafe outer rollback
after unsafe ledger=1,audit=1,raw=1,outside=1
```

**Explanation of key lines:**

- `outer active=true bound=true`: Spring has opened a physical transaction and bound a connection holder for the datasource onto the thread.
- `ledger sameConnection=true` and `audit sameConnection=true`: two different DAOs can retrieve the exact same bound connection when checked; each DAO has its own `JdbcTemplate` object.
- `audit seesLedgerWrite=true`: `AuditDao` reads the INSERT just performed via `LedgerDao` **before the transaction commits**. This is read-your-writes within the same transaction, not a dirty read from another connection.
- `audit newTransaction=false`: `AuditService`'s method is called through a Spring proxy and declares `REQUIRED`; it **joins** the outer physical transaction rather than creating a new transaction.
- `raw sameConnection=true`: legacy-style JDBC code using `DataSourceUtils` still receives the bound connection.
- `after rollback ledger=1,audit=1,raw=1`: the first scenario committed one record per table; the second scenario wrote across all three DAOs but rolled everything back, so the counts stay at 1.
- `outside autoCommit=true`: `UnsafeDao` intentionally borrows a new connection directly from `DriverManagerDataSource`, bypassing `DataSourceUtils`, so H2 auto-commits the statement into `outside_entries`.
- `after unsafe ... outside=1`: outer rolls back `ledger.insert("not-committed")`, yet cannot roll back the write performed on a connection outside Spring's transaction.

**Verification note:** comparing `Connection == expected` works in this demo because two `DataSourceUtils` lookups for the same datasource and active transaction return the same bound JDBC handle. A connection proxy from `JdbcTemplate.execute(ConnectionCallback)` may have a **different identity** even though it points to the same underlying connection (`JdbcTemplate` creates a close-suppressing proxy). Do not use object identity comparison across wrappers or pools as the general definition of a transaction. Stronger verification is seeing uncommitted SQL writes and observing atomic rollback/commit.

### 6.5. Why Does the Demo's Transaction Not Fall Prey to Self-Invocation?

`outer.successful()`, `outer.failed()`, and `outer.unsafeMix()` are called from `Main` on a **bean retrieved from the Spring context**, not an instance created manually with `new OuterService(...)`. `AuditService.record()` is likewise called by outer on a **Spring-managed bean**, so the `REQUIRED` advice is applied.

Conversely, if a method in the same class calls `this.newTransactionMethod()`, in Spring proxy mode the call can bypass the proxy and fail to trigger the target method's annotation. Already having a bound resource in outer does not fix this transactional boundary mistake.

### 6.6. Why Does the Counter-Example Use a Separate External Table?

In many databases, T1 may hold table/row locks that another connection also needs to write to. If `UnsafeDao` used a different connection and waited on a lock held by outer, the same call stack would **block itself** and make the example hard to run. A separate `outside_entries` table isolates the lesson about **autocommit outside the transaction** instead of mixing it with lock contention. In real applications, misusing raw connections can also lead to timeouts/deadlocks, not just a stray committed record.

## 7. Where Should Transaction Boundaries Be Defined?

A readable architecture:

```text
Controller
  |
  v
Application service
  @Transactional
  |
  +-- Domain service / repository A
  +-- Domain service / repository B
  +-- Outbox / audit repository (if same-DB atomicity is required)
  |
  +-- return
        |
        v
  Spring transaction interceptor completes the transaction
```

Transaction boundaries are normally placed at the **application service** because the service knows which changes must commit/roll back as a unit. DAOs/repositories do not all need to declare `@Transactional`; when called inside an already open transaction, Spring-aware JDBC APIs participate automatically.

### 7.1. Should Every DAO Method Carry `@Transactional`?

Not required. If a DAO method is called standalone outside a transaction, you may need a boundary at an appropriate layer, yet putting `@Transactional` on every operation indiscriminately makes propagation flows harder to follow.

With `REQUIRED`:
- Valid outer transaction exists → joins outer.
- No transaction exists → creates a new one.
- If a participating scope marks rollback-only due to an error, the entire outer transaction can roll back; the caller may hit `UnexpectedRollbackException` when expecting a successful commit.

`@Transactional`'s default rollback policy is based on unchecked exceptions/`Error`; checked exceptions require considering `rollbackFor` if rollback is desired. Do not simply `catch (Exception)` and swallow the error while expecting Spring to know it should roll back.

### 7.2. `TransactionTemplate` Instead of AOP When a Programmatic Boundary Is Needed

The same multi-DAO model also works with `TransactionTemplate`:

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.executeWithoutResult(status -> {
    accountDao.debit(accountId, amount);
    auditDao.insert("DEBIT");
    legacyDao.insertWithDataSourceUtils("DEBIT");

    if (businessRuleFailed()) {
        status.setRollbackOnly();
    }
});
```

This is a **snippet**; business types/fields/methods must be provided by the application. `TransactionTemplate` manages the transaction on the current thread; DAOs using Spring-aware datasource lookups still receive the bound resource. The advantage is an explicit boundary in code without needing a proxy to **enter** the transaction template; the trade-off is that orchestration code must be aware of the transaction API.

## 8. How Does Propagation Change the Resource?

Calling DAOs in the same call stack does **not always** mean using the old physical transaction. Propagation at a transactional method boundary can change that.

| Inner propagation | When outer already has transaction A | Resource/commit |
|---|---|---|
| `REQUIRED` | Joins A | Usually shares connection resource A; inner does not commit A independently |
| `SUPPORTS` | Joins A if present | When A exists, Spring-aware SQL typically uses resource A; without A, there may be no actual transaction |
| `MANDATORY` | Requires A | If A exists, joins it; without a transaction, throws an error |
| `REQUIRES_NEW` | Suspends A, opens B | B has an independent resource/physical transaction; B completes, then A is restored |
| `NESTED` | With a supporting JDBC manager, uses a savepoint inside A | Still one physical transaction/connection A; nested scope rolls back to savepoint |
| `NOT_SUPPORTED` | Suspends A, runs outside transaction A | JDBC calls inside may use another/nontransactional connection; afterward A is resumed |
| `NEVER` | Forbids A from existing | If A exists, Spring throws an error |

### 8.1. `REQUIRES_NEW` Does Not "Use the Same Resource A"

```text
Outer transaction A
     |
     +-- DAO 1 uses Connection A
     |
     +-- inner @Transactional(REQUIRES_NEW)
     |        suspend resource A
     |        acquire Connection B, start transaction B
     |        DAO 2 uses B
     |        commit or rollback B
     |        resume resource A
     |
     +-- DAO 3 uses Connection A again
     |
     +-- commit/rollback A
```

B can commit even if A later rolls back. B typically needs a second connection, while A may still hold its connection/locks. Spring warns to size the pool large enough when many threads use `REQUIRES_NEW`; do not put it on every DAO just to be "safe."

### 8.2. `NESTED` Is Still One Physical Transaction When Using Savepoints

If the JDBC manager/driver supports it, `@Transactional(propagation = NESTED)` typically creates a savepoint on connection A. Inner rolling back to the savepoint does not mean A ends; outer keeps running. If A later rolls back as a whole, **all** uncommitted changes, including the "successful" nested part, are still lost.

Do not generalize this to every JPA/JTA transaction manager; savepoint/nested support depends on the manager and resource.

### 8.3. `NOT_SUPPORTED` and Non-Transaction-Aware Access Paths

Inside a `NOT_SUPPORTED` block, Spring suspends context A; JDBC code may acquire another connection. Upon leaving the block, A is resumed. This is an **intentional semantic change**, unlike the bug of calling `dataSource.getConnection()` directly when you mistakenly think you are still inside A.

## 9. Sharing the Same Resource Between JDBC and JPA/Hibernate

**Do not equate "same DB" with "same physical transaction" when mixing persistence technologies.** When needing `JpaRepository` + `JdbcTemplate` inside one service transaction, consider:

- `JpaTransactionManager` manages the `EntityManager` of an `EntityManagerFactory` and **can support JDBC access on the same datasource** within the same transaction when the JPA provider/dialect allows exposing the JDBC connection appropriately.
- `JdbcTemplate` must use the datasource tied to the appropriate persistence unit/transaction manager. Creating a **separate `JdbcTransactionManager`** for JDBC and a separate `JpaTransactionManager` for JPA against the same database **does not automatically create a single transaction**.
- A JPA `EntityManager` has a **persistence context/first-level cache** and can defer SQL until `flush()`. Therefore, even when JDBC truly belongs to the same physical transaction, a JDBC query may **not yet see** entity changes if JPA has not flushed the necessary SQL.
- A direct JDBC `UPDATE` can change the DB while managed entities in the persistence context still hold **stale state**. You need clear rules for `flush`, `clear`/`refresh`, optimistic locking, and access ordering.
- Do not call `Connection.commit()` in the JDBC layer just because JPA has not flushed; Spring/the transaction manager owns the lifecycle.

Illustrative example (not a standalone runnable class):

```java
@Service
class InventoryService {
    private final ItemRepository items; // Spring Data JPA
    private final JdbcTemplate jdbc;     // same DB/properly configured resource

    InventoryService(ItemRepository items, JdbcTemplate jdbc) {
        this.items = items;
        this.jdbc = jdbc;
    }

    @Transactional
    public void reserve(long id) {
        Item entity = items.findById(id).orElseThrow();
        entity.decreaseAvailable(1);

        // Depending on the JPA provider, entity changes may not have flushed to SQL yet.
        items.flush();

        // JdbcTemplate reads the DB after JPA SQL has been flushed.
        Integer left = jdbc.queryForObject(
            "SELECT available FROM items WHERE id = ?",
            Integer.class, id
        );
        // Continue business logic based on the value read.
    }
}
```

This is an **application snippet requiring the matching repository/entity/configuration**. Calling `items.flush()` does not change the commit principle: flush sends SQL, yet **does not commit the physical transaction**. An outer rollback can still undo flushed changes. Test against a real DB and check which transaction manager is selected if multiple manager beans exist.

## 10. Sharing the Same Resource Between MyBatis and Spring JDBC

MyBatis-Spring provides `SqlSessionTemplate` so mappers participate in Spring transactions. According to the MyBatis-Spring documentation:

- `SqlSessionTemplate` uses a `SqlSession` bound to the current transaction and manages its lifecycle on behalf of the application.
- The datasource of `SqlSessionFactoryBean` must match the datasource of `DataSourceTransactionManager`/the Spring transaction manager; **having the same URL is not enough** for automatic participation.
- `SpringManagedTransactionFactory` is the standard choice with MyBatis-Spring.
- Do not manually call `commit()`, `rollback()`, or `close()` on a Spring-managed `SqlSession`; MyBatis-Spring coordinates this.
- Manually using `SqlSessionFactory.openSession()` or `DefaultSqlSession` can bypass the Spring-managed session and lead to consistency bugs.

High-level configuration diagram:

```text
Same DataSource bean
      |
      +-- JdbcTransactionManager/DataSourceTransactionManager
      |
      +-- JdbcTemplate (DAO A)
      |
      +-- SqlSessionFactoryBean -> SqlSessionTemplate (Mapper B)
                                      |
                                      v
                        SQL participates in the current Spring transaction
```

This is an **integration model**, not a guarantee that any arbitrary MyBatis configuration works. When using mappers with different executor types, MyBatis-Spring also restricts arbitrarily changing `ExecutorType` inside an already-existing transaction.

## 11. Multiple DataSources: Same Thread, Yet Not the Same Atomic Transaction

This is a major misconception in Spring applications:

```java
@Transactional("ordersTransactionManager")
public void placeOrder() {
    ordersJdbc.update("INSERT INTO orders ...");  // orders datasource
    billingJdbc.update("INSERT INTO charges ..."); // billing datasource
}
```

This is an **illustrative snippet**, not standalone runnable code. `ordersTransactionManager` may manage only the orders datasource. If `billingJdbc` uses a different billing datasource, the billing operation is **not automatically included in the same physical transaction**. It may auto-commit independently or require a separate transaction manager.

The fact that code lives in the same Java method or runs on the same thread does not turn two connections to two DBs into **one ACID unit**.

### 11.1. Architectural Options

1. **One DB/connection for tables requiring atomicity:** simplest when domain boundaries allow.
2. **Distributed transactions/JTA/XA:** when multiple XA resources participate under a suitable transaction coordinator, they can be coordinated as a distributed transaction, subject to operational trade-offs and driver/resource support. Do not equate "same resource" with "same JDBC connection"; each resource still has its own connection and transaction branch.
3. **Outbox, saga, compensation:** when XA is undesirable or unavailable, design for eventual consistency, idempotency, and step-by-step failure handling.

Do not "solve" this by stacking `@Transactional` across two datasource managers and trusting Spring to apply two-phase commit automatically. **An annotation does not turn two local transaction managers into a global transaction manager.**

### 11.2. Selecting the Right Transaction Manager

If an application has multiple `PlatformTransactionManager` beans, select by qualifier:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void saveOrder() {
    // Only resources managed by the corresponding manager
    // are guaranteed to participate in this transaction.
}
```

This is a snippet. In Spring, you can also configure a default transaction manager via application configuration. Be consistent in selecting managers across services and repositories; if method A uses manager X and method B uses manager Y, participation/rollback may not behave as one transaction.

## 12. Thread Boundaries and Reactive Transactions

### 12.1. `@Async` or a New Thread Does Not Carry JDBC Resource Bindings Along

Imperative Spring transaction synchronization relies on a **thread-bound context**. Code like:

```java
@Transactional
public void process() {
    accountDao.update();
    asyncAuditService.recordAsync(); // @Async -> different thread
}
```

is an **illustrative snippet**. `@Async` usually runs on a different thread; that thread **does not automatically inherit** the connection bound by Spring to the calling thread. It may open its own new transaction or run non-transactionally, depending on annotations/managers. If atomicity with the account update is required, **do not** move mandatory audit writes into an async method and expect them to roll back with the original transaction.

Do not copy the `TransactionSynchronizationManager` resource map to another thread to "share the connection": JDBC connections and persistence contexts are generally **not safe for concurrent use across threads**, and transaction managers are not designed to manage lifecycles across manual copies.

### 12.2. Reactive Transactions Differ from Imperative Transactions

R2DBC and reactive Spring transaction management attach context to the **Reactor Context**, not JDBC imperative's `ThreadLocal ConnectionHolder` model. Use `R2dbcTransactionManager`/`TransactionalOperator` and the corresponding operators/reactive data APIs.

Mixing blocking `JdbcTemplate` with an R2DBC pipeline does not guarantee the same transaction; a JDBC datasource and an R2DBC `ConnectionFactory` are **two different resource models**. Do not infer atomic commit simply because subscriptions share the same request ID.

## 13. Read-Only, Isolation, and Timeout Are Also Shared per Physical Transaction

When multiple DAOs join the **same physical transaction**:

- **Isolation:** SQL executed on the current physical transaction is subject to the isolation configured by the manager/connection; an inner `REQUIRED` method declaring a different isolation level **normally does not upgrade the isolation** of an already-running outer transaction.
- **Read-only:** if outer has `@Transactional(readOnly=true)`, an inner DAO does not automatically turn it into read-write; write-blocking enforcement depends on the DB/driver/manager. `readOnly` is primarily a hint in Spring's API, not a default SQL firewall.
- **Timeout:** statements can be subject to the remaining transaction timeout; `JdbcTemplate` has mechanisms to apply timeouts when preparing statements. Manual JDBC code must integrate `DataSourceUtils.applyTransactionTimeout` if needed.
- **Rollback-only:** if one participating scope marks the transaction rollback-only, every DAO inside the physical transaction can be rolled back together; there is no "roll back only DAO B" just because DAO B has its own annotation.

When `REQUIRES_NEW` opens another physical transaction, the inner transaction has its own isolation/read-only/timeout and a new resource. This changes concurrency behavior, transaction locks, and independent commit capability.

## 14. Common Bugs, Symptoms, and Remedies

| Symptom | Common Cause | What to Check |
|---|---|---|
| DAO A rolls back while DAO B already committed | DAO B used raw `dataSource.getConnection()` with auto-commit or a different manager | Check datasource object, connection lookup, transaction boundary, SQL after rollback |
| Two DAOs use the same DB URL yet do not share a transaction | Two different datasource beans/managers, separate resource bindings | Check bean wiring and which transaction manager is active |
| Legacy DAO closes the connection mid-transaction | Calling `con.close()` directly instead of `DataSourceUtils.releaseConnection` | Use the helper or `TransactionAwareDataSourceProxy` for legacy code |
| `JdbcTemplate` and raw JDBC show `Connection == false` | One side uses a proxy/wrapper; may still share the underlying resource | Compare the right target/holder in tests; more importantly verify actual commit/rollback |
| ORM writes data but a JDBC SELECT does not see it yet | Hibernate/JPA has not flushed changes to SQL yet | Use explicit flush, inspect SQL, ensure same manager/provider |
| JDBC updates DB yet JPA entity still returns old values | Persistence context cache holds already-loaded entity | Understand flush/clear/refresh, avoid stale managed state |
| MyBatis mapper does not join Spring transaction | `SqlSessionFactory` uses a different datasource, raw `openSession()` | Use `SqlSessionTemplate`, configure `SpringManagedTransactionFactory` and matching DS |
| Inner `@Transactional(REQUIRED)` expected to start a new transaction | `REQUIRED` joins outer by design | Check `status.isNewTransaction()` in tests, understand propagation |
| Inner `REQUIRES_NEW` commits even though outer rolls back | Expected semantics of an independent physical transaction | Use only when business logic requires independent writes |
| Pool exhausted when many requests call `REQUIRES_NEW` | Outer holds one connection while inner demands a second connection | Measure pool usage, limit concurrency, size pool appropriately |
| `@Async` does not roll back with caller | Resources are thread-bound; async runs on another thread | Keep in the same synchronous boundary or use an outbox |
| `TransactionSynchronizationManager.isActualTransactionActive() == true` yet DB B still commits separately | Thread flag does not prove datasource B participates in manager A | Check resource key, transaction manager, and SQL outcome |
| Seeing only "Creating new transaction" in logs and assuming atomicity is right | Not guaranteed that all DAOs use the right connection | Write an integration test inserting into multiple tables then forcing rollback |
| Using `@Transactional` on private/self-invoked methods | Proxy advice is bypassed | Use public service methods invoked via proxy or use `TransactionTemplate` |
| Trying `@Transactional` across two datasources to get XA | Two local managers remain independent | Consider JTA/XA or saga/outbox |
| Calling `commit()` in a raw DAO | Breaks Spring-managed lifecycle; outer rollback loses expected meaning | Never manually commit/rollback a bound connection |

### 14.1. How to Debug Connection Binding Properly

In an integration test **strictly for diagnostics**, you can inspect:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean bound =
    TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
    TransactionSynchronizationManager.getResource(dataSource);
```

The lines above are a snippet requiring `TransactionSynchronizationManager` imports and a datasource variable. With a JDBC manager, the resource is typically a `ConnectionHolder`. Do not pass this `resource`/`Connection` to another thread or store it in a singleton. Do not log raw JDBC credentials, SQL parameters, or user-sensitive data.

Enabling DEBUG for `org.springframework.transaction` and `org.springframework.jdbc.datasource` can reveal create/join/suspend/resume/cleanup events. However, logs are only secondary evidence; the decisive check remains **whether the tables commit/roll back together in reality**.

### 14.2. What Should an Integration Test Verify?

Instead of merely unit-testing that DAO A and DAO B were called, run a test with a **real database / Testcontainers**:

1. Configure the real service, proper Spring transaction proxy, and transaction manager.
2. Call the service to perform multiple mutations across **different data access layers**.
3. Within the transaction, have DAO B read DAO A's uncommitted changes to verify read-your-writes.
4. Deliberately throw an unchecked exception after **all DAOs** have run.
5. Catch **outside the boundary**; after rollback, open another connection/transaction to re-read the tables. All changes in the unit of work must be gone.
6. Run the success case and confirm all tables have the data.
7. Also exercise raw JDBC paths, JDBC wrappers/proxies, and MyBatis/JPA if the system uses them.
8. Test async and multi-datasource call paths separately; never assume they share the same transaction.
9. If `NESTED`/`REQUIRES_NEW` are used, write separate test cases per propagation mode.
10. Test commit failures/connection loss and retry/idempotency strategies when business-critical.

**Strongest counter-evidence:** If a DAO still leaves a record behind after the outer Spring transaction has rolled back, first inspect that DAO's connection/datasource/manager/propagation—do not rush to blame Spring transactions as broken.

## 15. Design Principles to Apply

### 15.1. Place Boundaries Around Business Operations, Not Individual Queries

If a business operation requires both ledger and audit writes to commit together, put `@Transactional` on the orchestrator service and let repositories participate. Avoid splitting into two physical transactions unless independence is required.

### 15.2. Inject the Exact Same DataSource/Manager Into DAOs Sharing a DB

One clear `DataSource` bean, one appropriate transaction manager, and DAOs using `JdbcTemplate`/`DataSourceUtils`. If multiple datasources/managers exist, use explicit qualifiers instead of relying on accidental bean names. Document the dependency graph for easier review.

### 15.3. Never Manipulate a Spring-Managed Connection Directly

Inside DAOs, do not arbitrarily call `setAutoCommit`, `commit`, `rollback`, or `close`. If using raw JDBC, close your own statements/result sets and release the connection via `DataSourceUtils`.

### 15.4. Distinguish Read-Your-Writes from Cross-Transaction Isolation

DAO B seeing DAO A's uncommitted SQL **within the same transaction** is normal behavior. That does not mean a second connection in another transaction is allowed to read dirty data. Isolation levels and the DB engine govern visibility **between** transactions.

### 15.5. Control Resources Outside the Database

Sharing a JDBC transaction does not make HTTP calls, file writes, Redis updates, or message broker publishes atomic with the DB. When you need "emit event only after commit," consider an outbox or proper after-commit synchronization. When consistency across resources is required, design JTA/XA or deliberate eventual consistency.

### 15.6. Ensure Transactions Are Not Unnecessarily Long

Sharing one connection across multiple DAOs within a transaction enables atomicity, yet also extends how long connections/locks are held. Do not put slow external HTTP calls, sleeps, or unrelated computations inside a transaction if they can be safely separated. Monitor timeouts, connection pools, and concurrent transaction counts.

## 16. Self-Check Questions

1. **Can two different `JdbcTemplate` instances sharing the same datasource participate in the same transaction?** — Yes, when inside the same Spring-managed transaction/resource context and using proper connection lookup.
2. **Does having singleton DAOs mean all requests share the same connection?** — No. Each transaction/thread gets its own resource.
3. **In a local JDBC transaction, what does Spring store so DAOs can reuse it?** — Typically a `ConnectionHolder` bound under the `DataSource` key in `TransactionSynchronizationManager`.
4. **Why can DAO B read DAO A's uncommitted INSERT?** — Because they share the same physical transaction/connection, not because the DB allows dirty reads across transactions.
5. **When writing raw JDBC in Spring, how should connections be acquired and released?** — `DataSourceUtils.getConnection(ds)` and `DataSourceUtils.releaseConnection(con, ds)`.
6. **Why can raw `dataSource.getConnection()` break atomicity?** — It may acquire a different auto-commit connection that does not participate in the bound Spring transaction.
7. **When is `TransactionAwareDataSourceProxy` useful?** — When integrating legacy libraries forced to use standard JDBC datasource/`getConnection` calls that cannot be changed to Spring-aware lookup.
8. **Which connection does an inner `REQUIRED` use when outer already has a JDBC transaction?** — Usually the same outer connection; it does not open a new physical transaction.
9. **Does an inner `REQUIRES_NEW` use outer's connection A?** — No, per independent physical transaction semantics; outer is suspended, inner uses another resource, then outer resumes.
10. **How does `NESTED` differ from `REQUIRES_NEW`?** — `NESTED` typically uses a savepoint on one physical transaction; `REQUIRES_NEW` has its own physical transaction.
11. **Do `JpaRepository` and `JdbcTemplate` on the same datasource always see each other's data immediately?** — Not automatically. The transaction manager/provider must be configured properly and you must account for JPA flush/persistence context.
12. **Which MyBatis mappers participate properly in Spring transactions?** — Mappers/`SqlSession`s managed by MyBatis-Spring's `SqlSessionTemplate` and configured with the matching datasource/manager.
13. **Do two datasources pointing to the same DB server automatically form one ACID transaction?** — No. Local managers normally manage one resource each; distributed transaction coordination or another workflow is required.
14. **Does `@Async` automatically share the caller's bound JDBC connection?** — No; the imperative transaction context is per-thread.
15. **What is the strongest proof that DAO A and DAO B are truly atomic?** — Integration tests verifying both success and rollback after both execute, querying the data in a new transaction.
16. **Is comparing `Connection == expected` universal proof?** — No. Proxies/wrappers can yield different handles; inspect transaction semantics and actual outcomes.

## 17. Summary

- **The same datasource alone is not enough; the same transaction boundary + right manager + transaction-aware lookup are what matter.**
- In a local Spring JDBC transaction, DAOs using `JdbcTemplate` or `DataSourceUtils` with the same datasource can retrieve the same bound connection and participate in **one physical transaction**.
- `DataSourceTransactionManager`/`JdbcTransactionManager` handles begin/commit/rollback and resource bind/unbind/release. DAOs must not commit/close transactional connections themselves.
- `TransactionAwareDataSourceProxy` is a compatibility adapter for certain legacy libraries; not needed for new code using `JdbcTemplate`.
- `REQUIRED` typically joins outer's resource, `REQUIRES_NEW` uses an independent transaction/resource, and `NESTED` typically uses a savepoint on the current resource.
- JPA/ORM, MyBatis, multiple datasources, and async/reactive each have their own binding conditions; never assume "same resource" just from being in the same method or sharing a DB URL.
- **Verify via DB state after commit/rollback**, not merely an active transaction boolean, bean name, or Java object identity.

## Official References

- Spring Framework — Controlling Database Connections (`JdbcTemplate`, `DataSourceUtils`, `TransactionAwareDataSourceProxy`, transaction manager): https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Transaction Propagation (REQUIRED / REQUIRES_NEW / NESTED): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `DataSourceUtils` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `DataSourceTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JdbcTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `JpaTransactionManager` Javadoc (JPA/JDBC integration): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- MyBatis-Spring — Transactions: https://mybatis.org/spring/transactions.html
- MyBatis-Spring — `SqlSessionTemplate`: https://mybatis.org/spring/sqlsession.html
