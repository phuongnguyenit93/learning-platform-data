# Savepoint Limitations Regarding JPA Persistence Context State

## 1. Key Conclusion

**A JDBC savepoint reverts data state inside the database transaction; it does not revert the state of the JPA persistence context.** If code modifies or loads a managed entity after a savepoint and then rolls back to the savepoint, the `EntityManager` does not automatically restore its identity map, entity fields, dirty-check snapshots, collections, queued actions, or lifecycle state to the pre-savepoint moment.

This is the core of **NESTED and savepoints → Savepoint limitations regarding JPA persistence context state**. Two issues must be distinguished:

1. **Can NESTED execute at all?** `JpaTransactionManager` sets `nestedTransactionAllowed=false` by default. Even if this flag is explicitly enabled, nested still requires `JpaDialect` and JDBC driver support for savepoints. The flag does not turn JPA into a nested transaction management system.
2. **What if JDBC successfully rolls back to the savepoint?** The DB may revert data successfully, while managed entities still hold old values in RAM. Spring/JPA provides no guarantee to rewind the entire persistence context alongside a savepoint.

The Spring Framework Javadoc for `JpaTransactionManager` explicitly states that savepoints apply only to the JDBC connection, not to cached entity objects and related context; JPA itself does not support nested transactions with such semantics.

This lesson provides concepts, execution flows, common pitfalls, a complete Java 17+/Spring Boot 3.3.5/JPA/JDBC/H2 project, and integration tests demonstrating both observations. **The manual JDBC savepoint example inside a JPA transaction is strictly for learning purposes**, not a recommendation to do so in production.

## 2. Two Worlds of State: JDBC and JPA

### 2.1. Savepoints Belong to the JDBC Transaction

A JDBC transaction on a connection can mark a position for partial rollback:

```java
// Illustrative snippet with a Connection already in a transaction.
Savepoint mark = connection.setSavepoint("before_optional_step");
doSomeSqlOnTheSameConnection();
connection.rollback(mark);
connection.releaseSavepoint(mark);
```

`Savepoint` resides in `java.sql`. The snippet above is not a standalone class: it needs `Connection connection`, `doSomeSqlOnTheSameConnection()`, and `SQLException` handling. It requires a DB/driver supporting savepoints, the right connection, and an active transaction. `rollback(mark)` reverses SQL changes belonging to the transaction on that same connection **after** the marker.

```text
Physical transaction T (one JDBC connection)
  ├─ UPDATE A (before savepoint)
  ├─ SAVEPOINT S
  ├─ UPDATE B
  ├─ UPDATE C
  ├─ ROLLBACK TO S           -> discards B and C in the DB
  ├─ UPDATE D
  └─ COMMIT T                -> A and D remain, if commit succeeds
```

There is no second physical transaction. If outer T later rolls back entirely, both A and D are also rolled back. In addition, `ROLLBACK TO SAVEPOINT` does not portably undo HTTP calls, emails, published messages, allocated sequence numbers, or effects outside DB resources.

### 2.2. The Persistence Context Belongs to EntityManager

In JPA, an `EntityManager` manages a persistence context containing entity objects and metadata to synchronize with the DB:

- **Identity map:** an already-managed entity identity is normally returned as the exact same object when `em.find(type,id)` is called again.
- **Managed state:** field values and relationships live in Java memory.
- **Dirty checking:** the provider tracks changes and can emit `UPDATE` during flush/commit.
- **Write-behind:** `persist`/`setXxx` does not necessarily generate SQL immediately.
- **Loaded collections, snapshots, version, and action queue:** part of how the provider maintains/synchronizes entity state.
- **Transaction-scoped first-level cache:** has a lifecycle bound to the `EntityManager`, not to a JDBC savepoint.

Being able to control savepoints **does not mean** there is a JPA API that automatically copies/restores all of the states above. JPA does not define the following methods:

```java
// Pseudo-code: DOES NOT exist in jakarta.persistence.EntityManager.
entityManager.createSavepoint();
entityManager.restorePersistenceContextToSavepoint();
```

Do not use the pseudo-code above as a real library API.

### 2.3. Visualizing One Transaction, Two State Snapshots

```text
                Outer transaction
                         |
            +------------+------------+
            |                         |
       JDBC connection           EntityManager
       DB transaction T          persistence context
            |                         |
         SAVEPOINT S             Account#1 managed
            |                         |
         UPDATE row              Account.balance = 250
            |                         |
       ROLLBACK TO S                   |
            |                         |
       DB balance = 100          object may still be 250
            |                         |
            +-------------+-----------+
                          |
                same business operation yet
                two different read results
```

This is not a bug in the JDBC savepoint. It did its job in the DB. The mistake is inferring that it also restored the state managed by `EntityManager` in the JVM.

## 3. How Do `REQUIRED`, `NESTED`, and `REQUIRES_NEW` Differ?

| Propagation | When outer transaction exists | Number of physical transactions | Meaning for JPA |
| --- | --- | --- | --- |
| `REQUIRED` | Joins the outer transaction | Usually one | Uses transaction/persistence context per manager; inner error can mark rollback-only |
| `NESTED` | Usually creates a JDBC savepoint in the existing transaction | One | Only if manager/resources support it; **does not** snapshot JPA context |
| `REQUIRES_NEW` | Suspends outer and opens an independent transaction | Two while nested | Inner has an independent boundary; with compatible managers usually gets its own EntityManager scope |

`@Transactional(propagation = Propagation.NESTED)` is **a request**, not a guarantee that resources support savepoints. Without an outer transaction, `NESTED` per manager typically behaves like starting a new transaction; therefore an outer transaction must exist when testing nested rejection.

Syntax example:

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    // ...
}
```

This is an illustrative method needing a Spring bean class and proper imports. It does not inherently imply a nested JPA persistence context.

### 3.1. Why Is `JpaTransactionManager` Cautious?

The `JpaTransactionManager` Javadoc notes that `nestedTransactionAllowed` defaults to `false`, because nested savepoints apply only to JDBC connections, not to cached JPA entity objects. You can enable the flag **if you want nested support for JDBC access code participating in a JPA transaction**, yet that still depends on `JpaDialect`/driver support.

```java
JpaTransactionManager manager = new JpaTransactionManager();
boolean allowedByDefault = manager.isNestedTransactionAllowed();
// false on Spring Framework 6.x
```

This snippet only inspects configuration and lacks an `EntityManagerFactory` to actually run. Configuration example:

```java
JpaTransactionManager manager = new JpaTransactionManager(emf);
manager.setDataSource(dataSource);
manager.setNestedTransactionAllowed(true);
```

Distinguish clearly: the last line **only enables attempting the capability**, without adding JPA nested semantics. If `JpaDialect` does not supply a suitable `SavepointManager`, Spring can still throw `NestedTransactionNotSupportedException`. Even when a savepoint is created, rolling back does not automatically resynchronize the JPA persistence context.

### 3.2. Four Independent Conditions

| Condition | How to verify? | Conclusion |
| --- | --- | --- |
| DB and JDBC driver support savepoints | `DatabaseMetaData.supportsSavepoints()`, integration tests | Only proves JDBC capability |
| Manager allows nested | `JpaTransactionManager.isNestedTransactionAllowed()` | Only proves configuration flag |
| `JpaDialect` provides a savepoint manager on the transaction | Check implementation and runtime tests | Determines whether Spring `NESTED` can run |
| EntityManager restores managed objects after savepoint | No portable JPA contract | **Must not be inferred from the three conditions above** |

An application using JPA + Hibernate + H2 may have a DB that supports savepoints, yet `@Transactional(NESTED)` is still rejected by the manager or dialect. And even when savepoints work with JDBC, `em.find()` can still return a stale managed entity.

### 3.3. Warning About Switching Transaction Managers

`DataSourceTransactionManager` generally supports `NESTED` via JDBC savepoints on a `DataSource` when the driver supports it. However, it **does not replace `JpaTransactionManager` in coordinating `EntityManager`/JPA flushes/lifecycle**. Do not switch the manager to JDBC merely to stop an annotation from throwing an exception if the application still needs JPA transaction resources.

## 4. Concrete Scenario: DB Rolls Back Yet JPA Still Sees the Post-Savepoint Value

Suppose table `accounts` initially contains:

```text
id | balance
---+--------
1  | 100
```

Inside an outer JPA transaction, code uses the **exact JDBC connection participating in the transaction**:

1. Create savepoint `S`, when DB has `balance=100`.
2. Run JDBC `UPDATE accounts SET balance=250 WHERE id=1`.
3. **For the first time in this persistence context**, call `entityManager.find(Account.class,1L)`. JPA loads `250` and keeps the object managed.
4. JDBC rolls back to `S`; the DB returns to `balance=100`.
5. Call `entityManager.find(Account.class,1L)` again. The identity map typically returns the already-loaded managed object, with field still `250`.
6. Use `JdbcTemplate` SELECT in the transaction to read the DB; result is `100`.

```text
Moment                   JDBC DB       JPA managed Account
---------------------------------------------------------
Before savepoint          100          not loaded yet
After JDBC UPDATE         250          not loaded yet
After em.find             250          250
After ROLLBACK TO S       100          250
After em.find again       100          250 (from context)
After JDBC SELECT         100          250 (still in RAM)
```

**Conclusion:** a successful `Connection.rollback(savepoint)` does not mean managed entities were refreshed. This is a dangerous mental-model error: outer business logic may compare or validate data based on `250` even though the DB reverted to `100`.

### 4.1. A Second Risk: Unflushed Dirty State

```java
Account account = entityManager.find(Account.class, 1L);
account.setBalance(250); // Dirty in Java memory; SQL may not have run yet.
```

If you only mutate a field in the persistence context without `flush`, **the database does not yet have that SQL operation for a savepoint to roll back**. The entity still holds state `250`. When the outer transaction commits, the provider may flush pending changes to the DB, saving the change you thought was "discarded."

If you flushed earlier and then rolled back JDBC to a savepoint, objects and dirty-check snapshots in the provider can still mismatch the DB; what the next flush does depends on the provider/mapping/transaction state. Do not promise deterministic results across all Hibernate/JPA versions.

### 4.2. Even More Dangerous Variants

Savepoints also do not automatically restore:

- `persist()`ed entities and managed/identifier state after an SQL INSERT is rolled back.
- `@Version` optimistic-locking versions and snapshots used by the provider.
- Relations/collections modified in RAM.
- Queued deletes, updates, lifecycle callbacks, or domain events.
- Entities removed/merged in the persistence context.
- Configured second-level caches and query caches, if used by the application.

Not every scenario produces the exact same error. The invariant is that **there is no portable JPA mechanism** to restore the entire persistence context to a JDBC savepoint.

## 5. Why Are `flush`, `refresh`, and `clear` Not a Savepoint-Based JPA Rollback?

| API | Meaning | Risk when used after JDBC savepoint rollback |
| --- | --- | --- |
| `entityManager.flush()` | Synchronizes pending JPA changes to the DB | Can write dirty data back; does not reload state from DB |
| `entityManager.refresh(entity)` | Reloads a managed entity from the DB | Targets only one entity; can overwrite valid unflushed changes, cascade, and throw errors |
| `entityManager.clear()` | Detaches all managed entities | Discards valid unflushed changes of the entire outer transaction |
| `entityManager.detach(entity)` | Detaches a single entity | Does not restore other entities; can lose pending changes |
| `entityManager.find(type,id)` | Reads by identity | May return already-managed object without issuing SELECT |
| `entityManager.lock(...)` | Locks entity per JPA contract | Does not restore persistence-context snapshots |

The Jakarta Persistence API describes `refresh(entity)` as re-reading state from the DB, overwriting unflushed changes on that entity; `clear()` detaches all managed entities so unflushed changes will not be persisted. These are not safe "partial rollback" tools for arbitrary entities.

**In a read-only experiment on a single entity with no intended business dirty state**, `refresh` can illustrate syncing **one object** back to DB state after a savepoint. However, in an outer transaction with multiple managed entities holding valid changes, `clear()` or mass refreshing can cause unpredictable data/semantic loss. When a persistence context is no longer trustworthy, the safe option is usually **rolling back the entire JPA transaction, closing the context, and starting a new transaction**.

## 6. Runnable Practice — Spring JPA, JDBC, and H2 Savepoints

This project **intentionally separates two behaviors**:

- `@Transactional(NESTED)` via `JpaTransactionManager` is rejected by default when an outer transaction exists. The tests do not pretend JPA nested transactions worked.
- A **manual JDBC savepoint** inside an outer transaction managed by `JpaTransactionManager` demonstrates that the DB can partially roll back while a JPA-managed object retains stale state. This is a **controlled experiment**, not a production pattern to adopt.

The project uses **Java 17+, Spring Boot 3.3.5 (Spring Framework 6.1.x), Hibernate JPA, JDBC, and H2**, with Gradle/JUnit 5.

### 6.1. File Structure

```text
jpa-savepoint-limits/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/jpasavepoint/
    │   │   ├── JpaSavepointApplication.java
    │   │   ├── JpaTransactionConfiguration.java
    │   │   ├── Account.java
    │   │   ├── NestedAttemptService.java
    │   │   └── SavepointScenarios.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/jpasavepoint/
        └── JpaSavepointIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jpa-savepoint-limits'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management supplies compatible Spring, Hibernate, JPA API, H2, and JUnit versions; do not run plain `javac` without configuring the external classpath beyond the JDK.

### 6.2. Database Configuration

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:jpa_savepoints;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.jpa.hibernate.ddl-auto=none
spring.jpa.open-in-view=false
spring.datasource.hikari.maximum-pool-size=5
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance INTEGER NOT NULL
);
```

JPA schema generation is explicitly disabled because `schema.sql` creates the table. In tests, account 1 starts with `balance=100` and account 2 starts with `balance=10`. H2 is chosen because it supports JDBC savepoints; retest on your application's production DB before applying conclusions about drivers/flushing/locking.

`src/main/java/com/example/jpasavepoint/JpaSavepointApplication.java`:

```java
package com.example.jpasavepoint;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaSavepointApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaSavepointApplication.class, args);
    }
}
```

### 6.3. An Explicit JPA Transaction Manager

`src/main/java/com/example/jpasavepoint/JpaTransactionConfiguration.java`:

```java
package com.example.jpasavepoint;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JpaTransactionConfiguration {
    @Bean("transactionManager")
    public JpaTransactionManager transactionManager(
            EntityManagerFactory emf, DataSource dataSource) {

        JpaTransactionManager manager = new JpaTransactionManager(emf);
        manager.setDataSource(dataSource);
        // Do not enable nestedTransactionAllowed: default is false.
        return manager;
    }
}
```

There is exactly one transaction manager bean here. `@EnableTransactionManagement` activates proxy transaction advice. `JpaTransactionManager` manages Hibernate's `EntityManagerFactory` while also knowing the same `DataSource` used by `JdbcTemplate`. This lets JDBC code using Spring `DataSourceUtils` join the transaction-bound connection in the fixture.

**Do not replace this manager with `DataSourceTransactionManager` assuming JPA is still coordinated equivalently.** Resources and semantics differ.

### 6.4. JPA Entity and Inner Bean with NESTED

`src/main/java/com/example/jpasavepoint/Account.java`:

```java
package com.example.jpasavepoint;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "balance", nullable = false)
    private int balance;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public int getBalance() {
        return balance;
    }

    public void setBalance(int balance) {
        this.balance = balance;
    }
}
```

`src/main/java/com/example/jpasavepoint/NestedAttemptService.java`:

```java
package com.example.jpasavepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedAttemptService {
    private final JdbcTemplate jdbc;

    public NestedAttemptService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedChange() {
        // When an outer JPA transaction is active and flag nested=false,
        // Spring rejects NESTED before entering this method.
        jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independentChangeThenFail() {
        jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
        throw new IllegalStateException("Independent step failed");
    }
}
```

`NestedAttemptService` is a **separate bean** so the outer service calls it through a proxy. Calling `this.nestedChange()` inside the same object in proxy mode would skip the interceptor for the inner method and the test would not prove what it needs to prove.

### 6.5. Service Probing JDBC Rollback and JPA Cache

`src/main/java/com/example/jpasavepoint/SavepointScenarios.java`:

```java
package com.example.jpasavepoint;

import java.sql.Connection;
import java.sql.Savepoint;
import java.sql.SQLException;

import javax.sql.DataSource;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SavepointScenarios {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final NestedAttemptService nested;

    @PersistenceContext
    private EntityManager entityManager;

    public SavepointScenarios(
            JdbcTemplate jdbc,
            DataSource dataSource,
            NestedAttemptService nested) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.nested = nested;
    }

    public record Snapshot(
            int atInitialJpaLoad,
            int inJpaContextAfterRollback,
            int inDatabaseAfterRollback) {
    }

    @Transactional
    public void nestedAnnotationRejectedByDefault() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        nested.nestedChange();
    }

    @Transactional
    public void jdbcOnlySavepointKeepsEarlierOuterWork() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");

        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            Savepoint point = connection.setSavepoint("jdbc_only");
            jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
            connection.rollback(point);
            connection.releaseSavepoint(point);
        } catch (SQLException ex) {
            throw new IllegalStateException("Savepoint operation failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional
    public Snapshot staleManagedEntityAfterRollback() {
        return snapshotAfterSavepoint(false);
    }

    @Transactional
    public Snapshot refreshedEntityAfterRollback() {
        return snapshotAfterSavepoint(true);
    }

    private Snapshot snapshotAfterSavepoint(boolean refresh) {
        // Only an experiment on JDBC state and JPA first-level cache.
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            Savepoint point = connection.setSavepoint("probe");
            jdbc.update("UPDATE accounts SET balance = 250 WHERE id = 1");

            // First time loading Account#1 in this persistence context.
            Account managed = entityManager.find(Account.class, 1L);
            int atLoad = managed.getBalance();

            connection.rollback(point);
            connection.releaseSavepoint(point);

            if (refresh) {
                // Safe in this experiment since there are no valid
                // dirty changes on this entity to preserve.
                entityManager.refresh(managed);
            }

            int inContext =
                    entityManager.find(Account.class, 1L).getBalance();
            Integer inDatabase = jdbc.queryForObject(
                    "SELECT balance FROM accounts WHERE id = 1",
                    Integer.class);

            return new Snapshot(atLoad, inContext, inDatabase);
        } catch (SQLException ex) {
            throw new IllegalStateException("Savepoint operation failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional
    public void independentInnerRollback() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        try {
            nested.independentChangeThenFail();
        } catch (IllegalStateException expected) {
            // REQUIRES_NEW rolls back its own transaction.
        }
    }

    @Transactional
    public void fullTransactionRollback() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        throw new IllegalStateException("Abort entire transaction");
    }
}
```

Code explanation:

- `@PersistenceContext` injects a shared proxy pointing to the current transaction's `EntityManager`.
- `DataSourceUtils.getConnection(dataSource)` acquires the connection Spring has bound to the transaction, rather than opening a connection outside the transaction.
- `JdbcTemplate` accesses the same `DataSource`, so SQL in the demo uses the matching resource.
- `connection.rollback(point)` undoes the JDBC UPDATE on account 1. However, JPA had already loaded the object with `250` after that UPDATE and keeps it managed.
- The second `entityManager.find` can return the cached `250` object without re-querying the DB; the `JdbcTemplate` SELECT after rollback returns `100`.
- The `refresh=true` branch refreshes **one entity** for illustration, without restoring the whole context.
- Every `@Transactional` method is called through an external Spring proxy. Private helpers do not create separate transaction boundaries.
- `DataSourceUtils.releaseConnection` does not close a connection still bound to an active transaction; the transaction manager handles cleanup after the boundary.
- `SQLException` from savepoint operations is converted to a runtime exception so the whole transaction rolls back in the fixture. If a real resource encounters a severe error, do not try to continue inside a potentially broken context.

**Note:** Using a manual JDBC savepoint directly inside this JPA transaction is an **intentional anti-pattern created for the lesson**, not a standard solution for implementing nested JPA.

### 6.6. Integration Tests

`src/test/java/com/example/jpasavepoint/JpaSavepointIntegrationTest.java`:

```java
package com.example.jpasavepoint;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.NestedTransactionNotSupportedException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class JpaSavepointIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private SavepointScenarios scenarios;

    @Autowired
    private JpaTransactionManager transactionManager;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM accounts");
        jdbc.update("INSERT INTO accounts(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO accounts(id, balance) VALUES (2, 10)");
    }

    private int balance(long id) {
        Integer value = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, id);
        return value;
    }

    @Test
    void nestedFlagDefaultsToFalseForJpaManager() {
        assertFalse(transactionManager.isNestedTransactionAllowed());
    }

    @Test
    void nestedRequestInsideExistingJpaTransactionIsRejected() {
        assertThrows(NestedTransactionNotSupportedException.class,
                scenarios::nestedAnnotationRejectedByDefault);

        assertEquals(100, balance(1));
        assertEquals(10, balance(2));
    }

    @Test
    void jdbcSavepointRevertsOnlyWorkAfterSavepoint() {
        scenarios.jdbcOnlySavepointKeepsEarlierOuterWork();

        assertEquals(100, balance(1));
        assertEquals(20, balance(2));
    }

    @Test
    void managedEntityCanRemainStaleAfterJdbcRollback() {
        var snapshot = scenarios.staleManagedEntityAfterRollback();

        assertEquals(250, snapshot.atInitialJpaLoad());
        assertEquals(250, snapshot.inJpaContextAfterRollback());
        assertEquals(100, snapshot.inDatabaseAfterRollback());
        assertEquals(100, balance(1));
    }

    @Test
    void targetedRefreshReloadsThisOneEntityInTheFixture() {
        var snapshot = scenarios.refreshedEntityAfterRollback();

        assertEquals(250, snapshot.atInitialJpaLoad());
        assertEquals(100, snapshot.inJpaContextAfterRollback());
        assertEquals(100, snapshot.inDatabaseAfterRollback());
        assertEquals(100, balance(1));
    }

    @Test
    void requiresNewInnerRollbackDoesNotUndoOuterJdbcUpdate() {
        scenarios.independentInnerRollback();

        assertEquals(100, balance(1));
        assertEquals(20, balance(2));
    }

    @Test
    void outerRuntimeExceptionRollsBackEverything() {
        assertThrows(IllegalStateException.class,
                scenarios::fullTransactionRollback);

        assertEquals(100, balance(1));
        assertEquals(10, balance(2));
    }
}
```

**Seven tests** verify: default nested flag, rejecting `NESTED`, JDBC savepoint rollback, JPA managed state diverging from DB, targeted refresh, `REQUIRES_NEW`, and full rollback.

Do not put `@Transactional` on the test class. If the test opens its own transaction, a `REQUIRED` service may simply join the test's transaction, and checking "commit" would only observe uncommitted state. Here `balance(...)` runs **after the proxy finishes the service call**, meaningfully checking final state in the fixture.

### 6.7. Running and Reading Results

With Gradle Wrapper:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

If the project was created manually without a wrapper, use an installed Gradle version compatible with Boot 3.3.5 to generate the wrapper or run `gradle test`. The fixture's expected outcome is **7 tests passing**; there is no fixed Java stdout from JUnit tests. Inspect `build/reports/tests/test/index.html` after running. This codebase was **explained and statically checked**, with no claim that tests were actually executed on your machine.

| Scenario | Expected Result |
| --- | --- |
| Default `JpaTransactionManager` | `nestedTransactionAllowed=false` |
| `@Transactional(NESTED)` when outer JPA transaction is active | `NestedTransactionNotSupportedException` before inner body |
| Plain JDBC savepoint | Account 1 reverts to 100; outer update of account 2 to 20 still commits |
| JPA loads 250 after JDBC UPDATE then savepoint rollback | Managed entity stays 250, JDBC query sees 100 |
| `em.refresh` in experiment without dirty state | Managed entity reloads 100 |
| `REQUIRES_NEW` inner independent rollback | Account 1 = 100, account 2 = 20 |
| Outer runtime exception | Whole transaction rolls back, account 1 = 100, account 2 = 10 |

**Note on reliability:** the example uses H2 + Hibernate and a transaction-bound connection. If your driver/provider/`JpaDialect` does not expose the same connection to JDBC, or a custom cache/flush mode changes when data is loaded, the experiment must be adjusted on your actual stack. That is precisely why `JPA + savepoint` should not be treated as a portable capability.

## 7. How to Design Instead of Trying to Restore Persistence Context with Savepoints

### 7.1. If JPA Work Must Be Atomic: Roll Back Everything

When multiple managed entities must commit or roll back together, choose one clear JPA transaction and let unrecoverable errors roll back the entire transaction:

```java
@Transactional
public void updateOrderAndInventory() {
    // Update JPA entities in the same transaction.
    // If an invariant fails, throw an appropriate exception
    // and let the manager roll back the whole transaction.
}
```

This is an illustrative snippet, not a standalone class. Spring rolls back runtime exceptions/`Error` by default; checked exceptions require matching rollback rules, or global configuration depending on framework/version.

Advantage: when the transaction ends, the persistence context closes/detaches according to its proper lifecycle instead of continuing calculations in a state that just underwent a JDBC savepoint rollback unknown to JPA.

### 7.2. If a Sub-Step Needs an Independent Transaction: `REQUIRES_NEW`

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentRecord() {
    // ...
}
```

The method must be invoked through the proxy of a Spring-managed bean, not `this.method()` in default proxy mode. This is a different physical transaction that can commit/roll back independently. It is not a savepoint and **changes workflow atomicity**. Sufficient connection pool capacity is required, and the outer persistence context can still become stale if the independent inner transaction modifies records the outer already loaded.

### 7.3. If Only a Few SQL Statements Need Rollback: Design a JDBC-Only Substep

For code using only `JdbcTemplate` on a local JDBC transaction with no managed JPA entities in the rollback region, `DataSourceTransactionManager`/`PROPAGATION_NESTED` can work well if the DB supports savepoints.

In mixed JPA + JDBC applications, verify matching manager/resources, connection binding, and `JpaDialect` capability if planning to use `NESTED`. Do not declare a parallel `DataSourceTransactionManager` bean assuming all JPA repositories will still join the right transaction. A JDBC-only sub-work using manual savepoints remains an advanced option requiring test coverage for DB state, JPA state, and failure paths.

### 7.4. If Business Logic Has Steps That Cannot Share a Transaction: Explicit State Workflows

For operations involving external systems, consider business states like `PENDING`, `CONFIRMED`, `FAILED`, a transactional outbox, or saga/compensation. DB savepoints do not reverse sent API calls or JVM entity state. Workflow designs with observable states and idempotency are usually clearer than an ambiguous chain of nested transactions.

## 8. Debug Checklist for JPA + Savepoint Situations

1. Identify which transaction manager bean executes the `@Transactional` method; is it actually `JpaTransactionManager`?
2. Check whether `@Transactional(propagation=NESTED)` passes through a Spring proxy and whether an outer transaction exists at that moment.
3. Check `manager.isNestedTransactionAllowed()`; remember the JPA manager defaults to false.
4. If the flag was enabled, verify whether the actual `JpaDialect` supports savepoints; some providers do not supply a compatible `SavepointManager`.
5. Check whether the connection to which the savepoint applies is the exact connection shared by SQL/JPA.
6. Trace the exact ordering of `em.persist`, `em.find`, field mutations, `flush`, JDBC UPDATE, and rollback.
7. Compare managed entities (`em.find`) with a JDBC query after rollback inside the transaction; do not assume both results mean the same thing.
8. Inspect dirty state, flush mode, optimistic versions, and pending changes before outer commit.
9. When the resource/ORM has thrown a severe error, do not assume you can continue and commit just because outer caught it.
10. Inspect the DB after the outer transaction boundary using an independent transaction/connection; do not inspect only cache inside a `@Transactional` test.
11. Do not wipe the first-level cache wholesale with `em.clear` if valid outer unflushed changes exist.
12. Choose full rollback, `REQUIRES_NEW`, or clearly bounded JDBC-only nested design and test on a production-compatible database.

In test/dev environments, logging can help:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa=DEBUG
logging.level.org.hibernate.SQL=DEBUG
```

Do not tie assertions to fixed log strings. Log order and wording can change; DB commits and JPA context consistency must be proved via data state, not just a DEBUG line.

## 9. Common Mistakes

1. **"NESTED is a child EntityManager transaction."** False: JDBC savepoints do not create an independent JPA context.
2. **"Setting `setNestedTransactionAllowed(true)` solves it."** False: manager/dialect/driver and JPA state are separate conditions.
3. **"The DB supports savepoints so Hibernate JPA will support NESTED too."** There is no such guarantee.
4. **"Savepoint rollback automatically discards JPA managed entity changes."** False if changes remain in Java memory or context snapshots.
5. **"`em.find` always reads the DB."** False when the entity is already managed.
6. **"`em.flush` is a rollback."** False: flush sends pending changes to the DB.
7. **"`em.clear` only discards the sub-step's changes."** False: it detaches the entire persistence context.
8. **"`em.refresh` restores every entity automatically."** False: targeted refresh can overwrite legitimate outer changes.
9. **"Switching to `DataSourceTransactionManager` makes JPA nested work."** Do not swap out the JPA manager arbitrarily.
10. **"`REQUIRES_NEW` is like `NESTED` only safer."** They have different atomicity semantics; both require careful design/testing.
11. **"Once SQL is rolled back, callbacks/events outside the database are reversed too."** False.
12. **"A `@Transactional` test seeing the row means it committed."** It may just be viewing uncommitted data.
13. **"No exception means the persistence context and DB are definitely in sync."** Not true after JDBC savepoint interventions unknown to JPA.

## 10. Self-Check Questions

**Question 1.** JDBC savepoint rollback succeeds. Is `EntityManager.find` guaranteed to return pre-savepoint fields?

**Answer:** No. `EntityManager` keeps its own identity map and managed state; there is no snapshot/restore contract tied to JDBC savepoints.

**Question 2.** Does `JpaTransactionManager` allow `NESTED` by default?

**Answer:** No, `nestedTransactionAllowed` defaults to false. With an existing outer JPA transaction, a `NESTED` request can be rejected before entering the method body.

**Question 3.** If `nestedTransactionAllowed=true` is enabled and the driver supports savepoints, is that enough?

**Answer:** Not yet. `JpaDialect` must also support the savepoint mechanism used by the manager. Even with JDBC savepoints, the JPA context is still not restored.

**Question 4.** Why does the managed entity have `balance=250` while the JDBC query returns `100`?

**Answer:** The entity was loaded while the DB temporarily held 250; the savepoint rollback reverted SQL to 100, yet the cached entity still holds 250 in the persistence context.

**Question 5.** What can calling `flush` after a savepoint rollback cause?

**Answer:** It can write pending dirty changes into the DB, including changes business logic thought were discarded.

**Question 6.** Why is `clear` dangerous inside an outer JPA transaction?

**Answer:** It detaches all entities and can lose valid unflushed changes from outer, not just from the sub-operation.

**Question 7.** Can `refresh` help in an experiment with a read-only entity that has no pending changes?

**Answer:** It can reload that specific entity from the DB, yet it does not turn a savepoint into a JPA nested rollback.

**Question 8.** If a step can commit independently, what should be considered?

**Answer:** `REQUIRES_NEW` on a separate bean/proxy with tests and a sufficiently sized pool; understand it is a different physical transaction and the outer JPA context may still need re-reading.

**Question 9.** What is the most reliable way to measure a transaction outcome?

**Answer:** Call the method through a proxy, wait for completion, inspect the DB via an independent connection/transaction, and also inspect managed state if testing cache divergence.

## Official References

- [Spring JpaTransactionManager Javadoc — nested savepoints and JPA context](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)
- [Spring Framework — Transaction propagation and NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction advice and implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring JpaDialect Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaDialect.html)
- [Spring NestedTransactionNotSupportedException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/NestedTransactionNotSupportedException.html)
- [Spring — JDBC connection handling/DataSourceUtils](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Jakarta Persistence EntityManager Javadoc — flush, refresh, clear](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html)
- [Hibernate ORM User Guide — Persistence context and dirty checking](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Spring — Test-managed transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
