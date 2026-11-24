# Optimistic Locking, the `version` Column, and Conflict Detection

## 1. The problem: two people modifying the same data concurrently

Suppose an account management system has a row:

| id | balance | version |
| --- | ---: | ---: |
| 1 | 100 | 0 |

Two requests A and B read the same row nearly simultaneously. Both see `balance=100`, `version=0`.

- Request A wants to add 30, intending to write `balance=130`.
- Request B wants to subtract 20, intending to write `balance=80`.
- If the application only runs `UPDATE accounts SET balance = ? WHERE id = ?`, the final record could be `80`: A's operation is **overwritten and lost**, even though A reported success. This is a **lost update**.

**Optimistic locking** handles this situation by checking when writing whether the data still holds the **version that was read**. It assumes conflicts are not overly frequent and **detects conflicts at update time**, rather than holding a lock blocking all readers/writers throughout the entire time a user spends thinking.

Convention: each row has a `version` column. A valid write operation must:

1. Know the `version` at read time, for example `0`.
2. Update only if the current version **is still 0**.
3. **Increment `version` in the same atomic UPDATE statement** upon success.
4. Check the affected row count: `1` = update succeeded; `0` = stale version, row deleted, or another condition did not match.
5. On conflict, **do not report success and do not overwrite**. Return a meaningful error or read the fresh data and decide on a controlled retry.

After this lesson, you will understand the SQL compare-and-swap mechanism, JPA/Hibernate's `@Version` column, how Spring transactions roll back on conflict, and limitations such as *write skew*, bulk updates, and retry/idempotency.

## 2. How does a lost update happen?

### 2.1. Without a version check

```text
Time            Request A                      Request B
----------------------------------------------------------------
t0              Read balance=100               Read balance=100
t1              Compute 100 + 30 = 130         Compute 100 - 20 = 80
t2              UPDATE balance=130             Wait / prepare write
t3              COMMIT                         UPDATE balance=80
t4                                             COMMIT

Final result: balance=80.
A's +30 addition disappears from the final value.
```

This is an illustrative schedule when two requests rely on a **stale snapshot** without a mechanism to detect stale state. Whether the database detects or prevents this depends on isolation and transaction timing; do not assume every default DB isolation prevents lost updates in a **read → process → write** sequence spanning multiple requests.

### 2.2. With `version` and a conditional update

Both requests still read `version=0`, but write conditionally:

```sql
UPDATE accounts
SET balance = 130, version = version + 1
WHERE id = 1 AND version = 0;
```

Request A updates one row; the database now has `balance=130, version=1`.

Request B brings its read version of `0`:

```sql
UPDATE accounts
SET balance = 80, version = version + 1
WHERE id = 1 AND version = 0;
```

By the time B executes its UPDATE, the current row version is `1`, so `WHERE version = 0` **no longer matches**. The `UPDATE` affects **0 rows**. The application must treat this as a **conflict**, not a successful operation.

```text
Initial record:                  balance=100, version=0
A writes with expectedVersion=0: balance=130, version=1  → updatedRows=1
B writes with expectedVersion=0: unchanged              → updatedRows=0
B re-reads new record:           balance=130, version=1
B applies -20 to new data:       balance=110, version=2  → updatedRows=1
```

The final result `110` reflects **both changes in proper business order**. Automatic retries are not always appropriate: if two people edit a name/description concurrently, the system may need to notify the second user to compare and resolve the conflict, rather than silently accepting the newer edit.

## 3. Why must the UPDATE be an atomic check-and-write?

This is a very common **mistake**:

```java
// INCORRECT ILLUSTRATIVE CODE
long currentVersion = repository.readVersion(id);
if (currentVersion == expectedVersion) {
    repository.updateWithoutVersionCheck(id, newBalance);
}
```

Two requests can **both read** `currentVersion=0` in the gap between the two statements. Then both update unconditionally and cause a lost update. Putting an `if` in Java **does not turn two SQL statements into one atomic operation**.

The right approach combines the version condition and the data change **inside a single UPDATE statement**:

```sql
UPDATE accounts
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

The SQL above uses **illustrative named parameters**. With plain `JdbcTemplate`, use `?` placeholders; with `NamedParameterJdbcTemplate`, you use named parameters `:newBalance`, `:id`, `:expectedVersion`.

### 3.1. Meaning of the updated row count

| `updatedRows` | Interpretation and action |
| ---: | --- |
| `1` | Exactly one row matched the condition; the new version was incremented in the same UPDATE statement. |
| `0` | No rows matched. Usually a stale version, though it can also be because the row was deleted or another `WHERE` condition failed. **Never report success.** |
| `>1` | When `id` is the primary key, this is abnormal; check schema/conditions and abort the operation. |

Do not assert that `updatedRows=0` is **always** a version conflict. For example, if the SQL also has `balance >= amount`, 0 rows can also mean insufficient funds. If exact error classification is needed, re-query the state and apply domain policy in an appropriate step, noting that state can continue changing between reads.

### 3.2. Incrementing version on every write path

The mechanism works reliably only if **every significant write path for the same aggregate/row updates the version consistently**:

- Writes from Spring JDBC must include `WHERE version = ?` and increment `version`.
- Writes from Hibernate/JPA via entities with `@Version` are usually handled by the ORM.
- An admin script, background job, stored procedure, or native SQL that modifies data **without incrementing `version`** can prevent stale clients from detecting a stale snapshot.
- Bulk updates/deletes via JPQL or native SQL can **bypass per-entity version checks**. If used, design matching version conditions/increments instead of assuming `@Version` automatically protects every SQL statement.

`version` is not a system timestamp for comparing who updated "more recently." It is a monotonically increasing integer on each meaningful write; do not arbitrarily modify the version yourself when letting the ORM manage it.

## 4. Comparing optimistic locking with pessimistic locking

| Criterion | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Contention handling | Lets parties read/work, **detects conflicts at write time** | Holds database locks to prevent certain concurrent operations |
| Typical mechanism | `version` + conditional `UPDATE` or JPA `@Version` | `SELECT ... FOR UPDATE` / JPA pessimistic lock modes |
| When few users edit the same record | Usually efficient, avoids holding row locks for long periods from read time | Can increase wait time / lock footprint |
| When many users continuously update the same row | Many conflicts, costly retries | May be more suitable depending on lock contention, throughput, timeouts |
| Data edited by a user over several minutes | Easy to keep `version` from form open and detect conflicts on Submit | Holding a transaction/row lock for several minutes is very risky |
| Failure mechanism | `0 rows updated`, ORM optimistic exception | Lock wait, timeout, deadlock, failure to acquire lock |

**Optimistic locking does not mean the database uses no locks at all.** The database can still take a very brief row lock while the `UPDATE` runs, or have its own MVCC/isolation/serialization errors. The difference is that the application **does not intentionally hold an exclusive row lock from read time until the user finishes editing**. Checking `version` detects prior changes before overwriting.

## 5. Where Spring transactions fit in optimistic locking

`@Transactional` and optimistic locking answer **two different questions**:

- `@Transactional`: are a group of resource operations committed/rolled back **together**?
- `version`/optimistic locking: is the data the request intends to modify **still the version that was read**?

A service method can be both a transaction boundary and use a conditional update. With Spring JDBC:

```java
@Transactional
public void applyChange(Snapshot old, long delta) {
    // Insert a journal row inside the current transaction.
    journalRepository.insert(...);

    int changed = jdbc.update(
        "UPDATE accounts SET balance=?, version=version+1 " +
        "WHERE id=? AND version=?",
        newBalance, old.id(), old.version()
    );
    if (changed != 1) {
        throw new OptimisticConflictException(...);
    }
}
```

This is an **illustrative snippet, not a standalone program**; `Snapshot`, `newBalance`, repository, and exception must be defined. On a version mismatch, an unchecked exception escaping the transaction interceptor causes the **entire transaction to roll back**, including the previously inserted journal row.

Without `@Transactional`, or if resources do not participate in the same manager, the journal row **could already be committed** before the conflict is detected. Thus both **conflict detection** and **rolling back internal side effects** matter. Do not catch the exception and return success when a conflict occurred; roll back the proper scope, then return a clear business result.

For long-running workflows, data/snapshots can be read **outside the write transaction**, storing the version in an HTTP form, message, or request DTO. Upon receiving the write command, the service opens a short transaction to run the conditional update with that version. Do not hold a database transaction open for the entire time the user is editing in the UI.

## 6. Runnable hands-on project (Java 17+, Spring JDBC, and H2)

We build a small application with an `accounts` table and a `journal` table. It uses **Java 17+**, **Maven**, **Spring Framework 6.2.8**, and **H2 2.3.232**. No Spring Boot or web server is required.

The lab simulates two requests that **already read the same snapshot** by holding two separate Java objects before updating. It does not spawn two actual threads; this is **intentionally deterministic** to demonstrate stale versions and rollback without depending on scheduler timing. In a real server, two different HTTP requests/threads can produce that exact contention state.

### 6.1. File structure

```text
optimistic-version-demo/
├── pom.xml
└── src/main/java/example/OptimisticVersionDemo.java
```

### 6.2. `pom.xml`

Save the entire block below verbatim into `pom.xml`. **The first line is the XML declaration**; do not add a comment before it.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>optimistic-version-demo</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.OptimisticVersionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides ApplicationContext and bean configuration; `spring-jdbc` provides `JdbcTemplate` and `DataSourceTransactionManager`; `spring-tx` provides `@Transactional`; H2 is the in-memory database. Because `JdbcDataSource` is imported directly, H2 is on the **compile classpath**. Dependency versions in the lesson are pinned for reproducibility, whereas real projects should use a BOM and a security update plan.

### 6.3. `src/main/java/example/OptimisticVersionDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class OptimisticVersionDemo {

    // Snapshot read from the database at a specific point in time.
    // The version in the snapshot will NOT auto-update when the DB changes.
    public record Snapshot(long id, long balance, long version) { }

    // Domain error used in the demo: unchecked so Spring rolls back by default.
    public static final class OptimisticConflictException
            extends RuntimeException {
        public OptimisticConflictException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            AccountRepository repository =
                context.getBean(AccountRepository.class);
            AccountService service =
                context.getBean(AccountService.class);

            repository.initialize();
            printState("Initial", repository);

            // Both clients read BEFORE any client writes.
            Snapshot snapshotA = repository.read(1L);
            Snapshot snapshotB = repository.read(1L);

            System.out.println(
                "Both clients read version: A="
                + snapshotA.version()
                + ", B=" + snapshotB.version()
            );

            // A changes 100 -> 130 and bumps version 0 -> 1.
            service.applyDelta(snapshotA, 30L, "A");
            printState("After A", repository);

            // B still holds stale snapshot version=0 -> conflict.
            try {
                service.applyDelta(snapshotB, -20L, "B");
            } catch (OptimisticConflictException ex) {
                System.out.println("B conflict: " + ex.getMessage());
            }
            printState("After B conflict", repository);
            System.out.println(
                "B journal persisted: " + repository.hasJournal("B")
            );

            // Intentional retry: re-read then re-apply delta.
            Snapshot refreshedB = repository.read(1L);
            service.applyDelta(refreshedB, -20L, "B-RETRY");
            printState("After B retry", repository);
        }
    }

    private static void printState(
        String label,
        AccountRepository repository
    ) {
        Snapshot current = repository.read(1L);
        System.out.println(
            label + ": balance=" + current.balance()
            + ", version=" + current.version()
            + ", journal=" + repository.countJournal()
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:optimistic_version;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public AccountRepository accountRepository(JdbcTemplate jdbc) {
            return new AccountRepository(jdbc);
        }

        @Bean
        public AccountService accountService(AccountRepository repository) {
            return new AccountService(repository);
        }
    }

    public static class AccountRepository {
        private final JdbcTemplate jdbc;

        public AccountRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void initialize() {
            jdbc.execute("DROP TABLE IF EXISTS journal");
            jdbc.execute("DROP TABLE IF EXISTS accounts");

            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL, " +
                "version BIGINT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE journal (" +
                "tag VARCHAR(32) PRIMARY KEY, " +
                "delta BIGINT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts (id,balance,version) VALUES (?,?,?)",
                1L, 100L, 0L
            );
        }

        public Snapshot read(long id) {
            return jdbc.queryForObject(
                "SELECT id,balance,version FROM accounts WHERE id = ?",
                (rs, rowNum) -> new Snapshot(
                    rs.getLong("id"),
                    rs.getLong("balance"),
                    rs.getLong("version")
                ),
                id
            );
        }

        public void insertJournal(String tag, long delta) {
            jdbc.update(
                "INSERT INTO journal (tag,delta) VALUES (?,?)", tag, delta
            );
        }

        public int updateIfVersionMatches(
            long id,
            long expectedVersion,
            long newBalance
        ) {
            return jdbc.update(
                "UPDATE accounts " +
                "SET balance = ?, version = version + 1 " +
                "WHERE id = ? AND version = ?",
                newBalance, id, expectedVersion
            );
        }

        public Integer countJournal() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal", Integer.class
            );
        }

        public boolean hasJournal(String tag) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal WHERE tag = ?",
                Integer.class,
                tag
            );
            return count != null && count == 1;
        }
    }

    public static class AccountService {
        private final AccountRepository repository;

        public AccountService(AccountRepository repository) {
            this.repository = repository;
        }

        @Transactional
        public void applyDelta(Snapshot old, long delta, String tag) {
            long newBalance = Math.addExact(old.balance(), delta);
            if (newBalance < 0) {
                throw new IllegalArgumentException("insufficient balance");
            }

            // Write operation 1: must roll back if the account update conflicts.
            repository.insertJournal(tag, delta);

            // Write operation 2: conditional UPDATE + atomic version increment.
            int updated = repository.updateIfVersionMatches(
                old.id(), old.version(), newBalance
            );

            if (updated != 1) {
                throw new OptimisticConflictException(
                    "expected version " + old.version()
                );
            }
        }
    }
}
```

### 6.4. Why does this code produce the conflict properly?

**One row, two snapshots:** `snapshotA` and `snapshotB` are read before the first write. Both contain `version=0`. Keeping the old snapshot simulates client B having opened a form earlier; there is no need to fake a random race using `Thread.sleep()`.

**One transaction for both journal and account update:** `AccountService.applyDelta()` is a public method on a Spring-managed bean. `main()` retrieves the service via `context.getBean` and calls it through the proxy. `@EnableTransactionManagement` creates the transaction advice; `DataSourceTransactionManager` manages the same H2 datasource used by `JdbcTemplate`.

**Do not confuse with JPA `@Version`:** this is **pure Spring JDBC**, so `@Transactional` protects both operations committing/rolling back together, while the version check is **hand-written in SQL**. Spring JDBC does not auto-generate `WHERE version=?` simply because a table has a column named `version`.

**Conflict must be an exception:** when B uses `version=0` while the database is already at `version=1`, `updateIfVersionMatches` returns 0. The service throws `OptimisticConflictException extends RuntimeException`. Because the exception **escapes the public transactional method**, Spring rolls back B's transaction by default, including `INSERT INTO journal` that ran before the conflict was detected.

**B's retry is a separate transaction:** the caller catches the conflict **after B's proxy has rolled back**, re-reads the current row `balance=130, version=1`, and calls the service through the proxy again. This time the version matches, delta -20 is valid, and the update yields `balance=110, version=2`. Do not retry inside a transaction already marked rollback-only.

### 6.5. Run commands

From the `optimistic-version-demo` directory after creating both files:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Lines printed by the **Java program** as designed, excluding external Maven/Spring logs:

```text
Initial: balance=100, version=0, journal=0
Both clients read version: A=0, B=0
After A: balance=130, version=1, journal=1
B conflict: expected version 0
After B conflict: balance=130, version=1, journal=1
B journal persisted: false
After B retry: balance=110, version=2, journal=2
```

Interpretation:

1. Before any write, the snapshot is `(100,0)`.
2. A succeeds, increasing balance to 130, version to 1, and creating journal A.
3. B uses version 0 so no row matches. The service throws an exception; **journal B is rolled back**. The account record stays `(130,1)`.
4. `B journal persisted: false` proves B's rollback includes the write executed **before** the conflicting UPDATE.
5. Re-reading and retrying as a new transaction, B applies delta -20 to balance 130, resulting in `(110,2)` with journals A and `B-RETRY`.

**Money model warning:** the lab uses integers for illustration and does not cover the full financial domain (currency units, authorization, double-entry debit/credit, balance check during update, idempotency, durable audit, and system-wide concurrency). In real wallet/money systems, additional constraints and dedicated tests are required; do not copy the demo as a production money-transfer system.

## 7. JPA/Hibernate with `@Version`

When using Spring Data JPA/Hibernate, the more common approach is declaring a version column on the entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Account() {
        // Constructor for JPA.
    }

    public void addToBalance(long delta) {
        this.balance = Math.addExact(this.balance, delta);
    }
}
```

This is an **illustrative JPA entity snippet**, not part of the JDBC project above; running it requires a JPA provider dependency, datasource, and appropriate Spring Boot/JPA persistence configuration.

### 7.1. What does JPA do with `@Version`?

- Hibernate manages the version attribute, recording the version when the entity is loaded.
- When the entity is modified and flushed, the ORM generates a conditional UPDATE/DELETE checking the old version (conceptually: `WHERE id=? AND version=?`).
- When the write succeeds, the version is incremented per provider rules.
- If the version in the database has changed, the provider must not silently overwrite the stale snapshot; it raises an optimistic locking failure (for example `jakarta.persistence.OptimisticLockException` or a Hibernate-specific exception; Spring can translate it to `ObjectOptimisticLockingFailureException` or `OptimisticLockingFailureException`).
- **Detection timing** may be at `flush()` or at transaction commit, not necessarily right at `save(...)`. When the Spring proxy commits after the method body, the caller may receive the error even though the method body already returned.

Hibernate/JPA typically manages the version for you. **Do not manually increment the `@Version` field in application code** to "make sure" it changes; doing so can break provider mechanics. Update the business attributes and let the ORM handle the version.

### 7.2. Limitations of `@Version`

**Does not protect every SQL statement:** calling `JdbcTemplate` or native SQL directly on the table, or running bulk JPQL `UPDATE/DELETE`, can **bypass entity-level version checking**. When using those paths alongside JPA, you must explicitly check and increment the version or apply a corresponding synchronization strategy.

**Not every read is re-verified:** an entity that is only read without modification does not automatically report a conflict merely because it has `@Version`. If business logic requires ensuring the read data's version remained unchanged even without an update, study `LockModeType.OPTIMISTIC` and flush/commit semantics.

**Does not automatically solve stale HTTP forms:** if a request sends an old version, yet the service always loads the **latest** entity right before writing and ignores the expected version from the request, the ORM only protects the newly loaded transaction; it does not automatically know the user viewed an older version. You must compare the request's expected version against the current version, or preserve the detached version per your persistence model, and handle conflicts explicitly.

**Does not automatically enforce multi-row invariants:** if two transactions read different rows and then write different rows, each row can still have a valid version while violating a global rule (write skew). You need database constraints, suitable isolation, pessimistic locks, or an aggregate-level version as required.

### 7.3. Returning conflicts to the client

In HTTP APIs, stale versions usually map to **409 Conflict**. If using HTTP conditional requests and ETag/`If-Match`, **412 Precondition Failed** can be used per the API contract. Do not return 200 OK when an update failed due to a version mismatch.

The response should inform the client that the data needs refreshing/merging per policy (optionally returning the current version and necessary fields without leaking unauthorized data). Never expose ORM stack traces as a public interface.

## 8. Retrying on conflict: when is it appropriate, and when is it not?

A conflict is **not a transient error that should always be auto-retried**. There are two different groups of use cases.

### 8.1. Commands that can be re-applied to fresh state

For example, "increment counter by 1" or "add 30" can be recomputed on the fresh record, if business rules still hold. The proper sequence is:

```text
Attempt 1: read snapshot version 0
      open short transaction
      conditional UPDATE → conflict
      roll back transaction
      close scope/connection

Attempt 2: re-read snapshot version 1
      re-check business rule against fresh data
      open NEW transaction
      conditional UPDATE → succeed (or conflict again)
```

Bound the retry count, use backoff/jitter under high load, and monitor metrics. Every attempt must have a **new transaction**, because a failed transaction or one marked rollback-only is unsuitable for attempting another commit. In the Spring proxy model, call a public transactional method again through the proxy; do not accidentally use self-invocation and assume a new transaction was opened.

### 8.2. Manual user text edits

If A and B both edit `displayName` or a shipping address from two different snapshots, auto-retrying by blindly writing B's old value can **overwrite A's intentional edit**. Usually you should report the conflict and let the user:

- View the current data.
- Compare against their edits.
- Decide to merge, intentionally overwrite, or cancel.

If the product explicitly permits last-write-wins, that is a **business decision**; do not call it true optimistic locking when stale versions are ignored.

### 8.3. Idempotency and side effects outside the database

If an attempt already sent an email, called an HTTP endpoint, or published a message **before** the conditional update conflicted, JDBC rollback **does not automatically undo** those external side effects. Retrying may replay the side effect multiple times. For payments, orders, or event processing, idempotency keys, outbox/after-commit, or proper orchestration are required.

The lab example inserts `journal` inside the **same local JDBC transaction**, so the journal rolls back on conflict. That does not guarantee an operation outside the database rolls back automatically.

## 9. Tricky scenarios in real applications

### 9.1. Early vs. late conflict detection

In Spring JDBC, `JdbcTemplate.update(...)` returns the affected-row count right after the SQL statement; conflicts can be thrown inside the transactional service body. In JPA, entity mutations accumulate in the persistence context and SQL may be emitted at flush/commit. Integration tests must therefore check errors **after the transaction boundary ends**, not merely assert that `repository.save(...)` returned.

### 9.2. Balance condition alongside version condition

A real account needs domain constraint checks at write time. Sometimes update conditions can be combined:

```sql
UPDATE accounts
SET balance = balance - :amount,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND balance >= :amount;
```

This is **illustrative SQL with named parameters**. If 0 rows return, you must distinguish: insufficient balance, version mismatch, or deleted account. Do not use a single `optimistic conflict` message to mask all business errors. Also, if a request brings an old snapshot and computes a `newBalance` in the application, ensure both computation and validation remain valid after retry.

### 9.3. Aggregate scope and write skew

Suppose the rule "at least one doctor must be on-call" is represented by two rows. Two transactions both read both rows, and then each marks **a different row** off-call. Each row's version may not collide, yet the result leaves nobody on-call. This is a form of **write skew**: per-row versions are insufficient to protect an invariant **spanning multiple rows**.

You may need suitable unique/check constraints, serializable isolation, locking a representative aggregate row, or updating a shared aggregate version. Choose the solution based on the database and actual contention frequency.

### 9.4. Row deletion and re-creation

If a client holds version 5 but the row was deleted, `WHERE id=? AND version=5` returns 0. If the id is reused and the version is re-initialized improperly, a stale client can hit an "ABA"-like situation (values appear to return to an old state). Avoid reusing identities, manage version/epoch, and classify record-not-found errors per contract.

### 9.5. Versions and caching

If a cache/API serves stale snapshots, conflicts increase on update. This does not mean optimistic locking is broken; it shows the mechanism is **detecting stale data**. Monitor cache invalidation, TTL, latency, and failed update rates. Never remove `WHERE version=?` just to reduce visible errors.

### 9.6. Hot rows and performance

Optimistic locking works best when collisions are rare. On a hot row (for example a system-wide counter) with thousands of requests per second, every request reading the same version and retrying can cause a thundering herd, contention, and high latency. An atomic SQL `UPDATE counters SET n=n+1 WHERE id=?` can be better if the operation only needs to increment a counter and does not require detecting stale snapshots. When complex invariants are needed, consider pessimistic locking, sharded aggregates, queues, or serialized writes. **No single propagation/isolation is optimal for all loads.**

### 9.7. Transaction isolation does not arbitrarily replace version checks

Isolations like `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` affect what is read and what conflicts the database blocks. Some DBs at higher isolation detect serialization failures; however, a user reading a form, waiting several minutes, and submitting usually **spans multiple HTTP transactions**. Keeping the version in the form/request and checking it at write time remains valuable. Distinguish a **database snapshot within one transaction** from an **application snapshot across multiple requests**.

## 10. Deep enough testing to avoid false confidence

A proper test suite should cover:

1. **Single update:** initial version 0; update succeeds on exactly 1 row; version becomes 1, data accurate.
2. **Stale write:** two clients hold the same version 0; A succeeds, B using version 0 receives 0 rows or an optimistic exception.
3. **No side effects before conflict:** if the transaction wrote a journal before hitting a conflict, verify the journal **does not exist** after rollback.
4. **Valid retry:** B re-reads version 1, re-checks business rules, and updates successfully to version 2.
5. **No auto-retry on text edits:** two users edit different content; API returns 409/412 per contract instead of silently overwriting.
6. **Missing record:** updating a nonexistent id returns 0; verify how 404/409 are distinguished per policy.
7. **Failed business precondition:** e.g., insufficient balance returns a clear domain error; avoid lumping everything into conflict.
8. **Other write paths:** do native SQL, batch updates, and background jobs increment version properly?
9. **JPA flush/commit:** verify exceptions at the right transaction boundary, not just the repository method.
10. **Real concurrency conflict:** add an integration test with two transactions/threads and a barrier to create contention, not just deterministic snapshots. Outcomes can depend on DB/isolation, so tests must classify both optimistic conflicts and serialization errors per policy.
11. **Idempotency:** when retrying a command with the same request ID, verify journals or external side effects are not duplicated.
12. **Multi-row scope:** test invariants across multiple rows, since single-row `version` does not solve write skew by itself.

### 10.1. Checklist when code reports "version conflict"

| Question | Why it matters |
| --- | --- |
| Which read did the request's `expectedVersion` come from? | Is the client stale or guessing a version? |
| Does the UPDATE include `WHERE id=? AND version=?`? | Without it, stale writes are not detected. |
| Does the UPDATE increment version in the same statement? | If not incremented, subsequent clients can still overwrite each other. |
| Is `updatedRows` checked strictly? | 0 rows must lead to conflict/missing/precondition, not success. |
| Does the transaction wrap both journal and account update? | To roll back all writes when a conflict is detected. |
| Do service calls go through the Spring proxy? | `@Transactional` does not run on self-invocation or raw `new` targets in proxy mode. |
| Where is the conflict caught? | Do not swallow it inside the same transaction and try to commit. |
| Does the retry re-read state and open a new transaction? | Repeating the exact same stale version will keep failing. |
| Do multiple update paths bypass version? | Background SQL/bulk JPQL can cause lost updates. |
| Are there multi-row invariants? | Must protect the aggregate, not just individual rows. |

## 11. Exercises

**Exercise 1 — Drop the version condition:** in the demo, temporarily change the UPDATE to `WHERE id=?` and drop expected version from the parameters. Predict the outcome after requests A/B based on stale snapshots; explain why the output no longer reflects both deltas. Do this only on a test database.

**Exercise 2 — Forget to increment version:** keep `WHERE version=?` but remove `version=version+1`. Two requests can continue matching the old version. Fix it and prove with a test.

**Exercise 3 — Compute balance in the database:** change from `SET balance=?` to `SET balance=balance+?` combined with `WHERE version=?`. Analyze when a version check is still required, and when a SQL atomic increment alone suffices.

**Exercise 4 — Retry policy:** add a loop capped at three attempts, each time re-reading state and calling the public transactional service through the Spring proxy. If conflict persists, return an error rather than looping infinitely.

**Exercise 5 — Separate side effects:** try emitting a mock notification outside the transaction before the UPDATE, then trigger a conflict. Explain why database rollback does not cancel the notification and why outbox/idempotency must be considered.

**Exercise 6 — JPA:** map the same table to an entity with `@Version`; create two persistence contexts reading the same entity then edit/commit sequentially, observing the error on the second flush/commit. Do not replace `JdbcTemplate` code with `@Version` expecting `JdbcTemplate` to manage versions automatically.

**Exercise 7 — Detecting write skew:** design two records participating in one invariant. Create two transactions writing to different rows and explain why per-row versions fail to detect the cross-row conflict.

**Conclusion:** optimistic locking is a mechanism to **detect whether data changed since it was read**, typically via `version` and an `UPDATE ... WHERE version = expectedVersion` that increments version **in the same statement**. When affected rows = 0, the application must **handle the conflict genuinely**, never silently overwriting. `@Transactional` ensures rollback of operations within the same boundary; JPA's `@Version` can automate checking, but does not replace managing retries, transactions, stale data across requests, and multi-row invariants.

## 12. References

- [Hibernate ORM — User Guide: Locking](https://docs.hibernate.org/orm/8.0/userguide/html_single/) — optimistic/pessimistic locking concepts, version checks, entity versioning, bulk update limitations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — Spring transaction interceptor and rollback of a group of JDBC writes.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — annotation metadata, propagation, AOP proxy scope.
- [Spring Framework — JDBC `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html) — executing SQL and reading affected-row counts.
- [Jakarta Persistence — `@Version`](https://jakarta.ee/specifications/persistence/) — contract for optimistic locking via the version attribute.
