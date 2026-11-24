# Difference Between Memory Writes, Flush, and Commit in Spring Transaction Management

## 1. Three different stages of the same change

When working with Spring Framework, JPA/Hibernate, and a relational database, the phrase "data has been saved" can describe three very different states:

1. **In-memory application write**: a managed Java object (*managed entity*) has changed inside the `Persistence Context`. The change may currently exist only in the state tracked by JPA/Hibernate.
2. **Flush**: JPA/Hibernate synchronizes pending changes from the `Persistence Context` down to the database via the appropriate SQL statements. These statements run **inside the current transaction**.
3. **Commit**: the database management system confirms the transaction succeeded, making the changes a committed outcome under the database's guarantees.

**Key takeaway: flush is not commit; an in-memory change also does not guarantee SQL has run.** A transaction can still `ROLLBACK` after `flush()` succeeds.

| Criterion | In-memory change | `flush` | `commit` |
| --- | --- | --- | --- |
| Where the change lives | Java object / `Persistence Context` | Database received and executed required SQL within the transaction | Database confirmed the transaction |
| Has SQL definitely executed? | Not necessarily | Pending operations from this flush were synchronized; the provider may have run some SQL earlier | Required changes were processed for a successful commit |
| Is data committed yet? | Cannot be inferred | **No**, merely because flush happened | **Yes**, if the commit actually succeeded |
| Can other transactions see it? | Cannot be concluded from Java state | Usually not, under `READ COMMITTED` isolation | Visible depending on the reader's isolation level, snapshot, and query timing |
| Can DB changes be rolled back? | Yes, if changes belong to an uncommitted transaction | **Yes**, for transactional DB operations | A finished transaction cannot be undone using its rollback |
| Possible errors | Java business errors | SQL errors, foreign key, unique, optimistic locking... | Deferred constraint errors, conflicts, connection drops, or commit-step errors |

This table describes the common case: Spring manages transactions, JPA/Hibernate acts as the ORM, and the database supports transactions. Do not equate "written to memory" with "database flushed to disk": database buffers, write-ahead logs, ORM caches, and the Java heap are distinct layers.

## 2. What does "in-memory write" mean in JPA/Hibernate?

### 2.1. Persistence Context and managed entities

`EntityManager` maintains a `Persistence Context`, usually bound to a transaction in a Spring application. This is where JPA tracks managed entities, their identities, and changes that must be synchronized with the database.

Example:

```java
@Transactional
public void changeBalance(Long accountId) {
    Account account = entityManager.find(Account.class, accountId);
    account.setBalance(200L); // Modifies state of a managed entity
    // No explicit SQL UPDATE statement at this setter line.
}
```

In the example above, if `account` is a managed entity, JPA detects modified state through *dirty checking* and generates SQL when flushing is needed. **There is no need to call `save()` after every setter on a managed entity.**

Keep three states in mind:

- **Managed**: the entity is attached to the `Persistence Context`; modifications to persistent fields are tracked by JPA.
- **New/transient**: an object created with `new` does not automatically become persistent; it needs `persist()` or a mechanism like `repository.save()`.
- **Detached**: an object detached from the `Persistence Context`; changing its fields does not synchronize automatically. `merge()` can copy state onto a managed instance; the newly returned reference is the instance to continue working with.

"Having called a setter" does not mean the database saved it. Conversely, you also cannot conclude "flush hasn't been called so no SQL ran": ID generation strategies like `IDENTITY`, queries, or other operations can prompt the provider to execute SQL early.

### 2.2. Distinguishing memory layers

- **Java objects and Persistence Context (L1 cache)**: entity state inside the application, tied to the JPA context.
- **Hibernate action queue / write-behind mechanism**: scheduled operations managed for batching and ordering before synchronization.
- **Database buffer/cache and transaction log**: internal DBMS mechanisms, independent of whether a Java object remains managed.

Therefore, "written to memory" must specify which memory layer. For this topic, we primarily mean **modifying entity state inside the Persistence Context**.

## 3. Flush: synchronizing SQL without ending the transaction

`EntityManager.flush()` requests synchronizing pending changes in the `Persistence Context` with the database. Hibernate usually translates the pending operations into `INSERT`, `UPDATE`, and `DELETE` statements.

```java
@Transactional
public void changeBalanceAndFlush(Long accountId) {
    Account account = entityManager.find(Account.class, accountId);
    account.setBalance(200L);

    entityManager.flush(); // Synchronizes SQL with the DB inside the current transaction

    // The transaction is still open inside this method body.
    // A subsequent RuntimeException can still cause the transaction to roll back.
}
```

What `flush()` provides:

- Pushes pending changes to the database at a more deliberate moment instead of waiting until commit.
- Can surface DB errors **early**, such as foreign key, unique constraint, not-null, or version lock failures.
- Makes SQL already run in the transaction visible to subsequent SQL statements in the **same transaction** per DB rules.
- Can acquire locks or incur I/O/round-trip cost earlier; flushing too frequently reduces batching opportunities.

What `flush()` does **not** provide:

- Does not call `COMMIT`.
- Does not guarantee other transactions immediately see the changes.
- Does not guarantee results will remain durable if the transaction later rolls back or fails to commit.
- Is not synonymous with `fsync` or a command "pushing every byte from RAM to disk."
- Is not limited to the last saved entity: a single flush can process **multiple pending changes in the same Persistence Context**.

Some databases support *deferrable* constraints checked at commit time; hence **a successful flush does not guarantee commit will succeed**.

Calling `EntityManager.flush()` without an active transaction or when the Persistence Context has not joined a transaction may cause JPA to throw `TransactionRequiredException`; flush should not be treated as a transaction-independent persistence mechanism.

## 4. Commit: confirming the entire transaction

In a Spring method called **through a transaction proxy** with `@Transactional`, the transaction interceptor typically opens or joins a transaction before invoking the method body. When the method body finishes, Spring uses the appropriate `PlatformTransactionManager` to decide commit or rollback.

With typical JPA usage, before a successful commit, required persistent changes are flushed/synchronized. Thus **you do not need manual `flush()` calls just to "make sure data is saved" in every transactional method**.

Typical sequence:

```text
Call into @Transactional proxy
    -> start or join transaction
    -> load managed entity
    -> modify field: state in Persistence Context changes
    -> (possible auto-flush before query or manual flush)
    -> business method returns
    -> Spring completes transaction: required flush and COMMIT
    -> proxy returns result to caller if commit succeeds
```

If an exception triggers rollback:

```text
modify managed entity -> flush -> SQL UPDATE executed
    -> RuntimeException -> Spring ROLLBACK
    -> uncommitted UPDATE is undone by the database
```

**The commit boundary is the transaction boundary, not the `repository.save(...)` or `entityManager.flush()` line.** With `Propagation.REQUIRED` (default), the method usually joins an existing transaction; in that case, the final commit belongs to the owner of the outer transaction.

By Spring default, `RuntimeException` and `Error` trigger rollback; checked exceptions normally do not trigger rollback unless configured with rollback rules. Swallowing an exception can let the call exit normally and proceed to commit; error handling must match rollback intent.

## 5. Spring Data JPA example: flush and still roll back

The code fragments below illustrate a **Java 17+, Spring Data JPA, Jakarta Persistence (`jakarta.persistence`)** application. These files belong in a Spring Boot project configured with `spring-boot-starter-data-jpa` and a database; they are **not a standalone Java program runnable with `javac` alone**.

**`Account.java`**

```java
package demo.transaction;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long balance;

    protected Account() {
        // JPA requires a no-arg constructor.
    }

    public Account(Long id, long balance) {
        this.id = id;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public long getBalance() {
        return balance;
    }

    public void setBalance(long balance) {
        this.balance = balance;
    }
}
```

**`AccountRepository.java`**

```java
package demo.transaction;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository extends JpaRepository<Account, Long> {
}
```

**`AccountService.java`**

```java
package demo.transaction;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository accounts;
    private final EntityManager entityManager;

    public AccountService(AccountRepository accounts, EntityManager entityManager) {
        this.accounts = accounts;
        this.entityManager = entityManager;
    }

    @Transactional
    public void changeNormally(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        // Dirty checking; JPA will flush when needed, usually before commit.
    }

    @Transactional
    public void changeWithFlush(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        entityManager.flush(); // SQL may have run, still not committed.
        // If no error occurs, the proxy will complete the transaction after the method returns.
    }

    @Transactional
    public void changeWithFlushThenFail(Long id, long newBalance) {
        Account account = accounts.findById(id).orElseThrow();
        account.setBalance(newBalance);
        entityManager.flush();

        throw new IllegalStateException("Error after flush");
        // RuntimeException causes Spring to roll back under default settings.
    }

    @Transactional
    public void saveAndFlushThenFail(Account account) {
        accounts.saveAndFlush(account);
        throw new IllegalStateException("Error after saveAndFlush");
    }
}
```

**Analysis starting from initial record `accounts(id=1, balance=100)`:**

| Call through Spring bean proxy | After call finishes | Explanation |
| --- | --- | --- |
| `service.changeNormally(1L, 200L)` | Normally: balance = 200 | Transaction commits successfully even without manual flush |
| `service.changeWithFlush(1L, 200L)` | Normally: balance = 200 | Early flush; commit is still decided by the transaction manager |
| `service.changeWithFlushThenFail(1L, 200L)` | Balance remains 100, if rollback succeeds | SQL flushed, yet RuntimeException caused transaction rollback |
| `service.saveAndFlushThenFail(new Account(1L, 200L))` | With valid entity and successful rollback: record retains pre-transaction value | `saveAndFlush` does not replace commit; may actually `merge` object with existing ID |

Outcomes assume no DB errors occur beyond those stated. When testing cases sequentially, **restore initial data before each case** so they remain independent; the last case passes an object with a matching ID to illustrate `merge`, which is unnecessary when updating a managed entity.

Do not call `changeWithFlushThenFail` from another method on **`AccountService` itself** expecting the transaction proxy to apply independently: normal self-invocation bypasses the proxy. Call from another bean or a real integration test through the Spring container.

## 6. How `save()`, `saveAndFlush()`, `flush()`, and `@Transactional` interact

| API / operation | Actual meaning | Misconception to avoid |
| --- | --- | --- |
| `account.setBalance(...)` on managed entity | Changes state tracked by JPA, subject to dirty checking | "Setter definitely sends UPDATE immediately" |
| `entityManager.persist(newEntity)` | Makes new entity managed; SQL timing depends on provider/ID strategy | "persist always INSERTs immediately" |
| `repository.save(entity)` | Spring Data JPA uses `persist` for new entities or `merge` for entities not recognized as new | "save = commit" |
| `entityManager.flush()` | Synchronizes pending Persistence Context changes with DB in the transaction | "flush = commit" |
| `repository.flush()` | Asks JPA to flush pending changes | "Only flushes this repository's entity" |
| `repository.saveAndFlush(entity)` | Saves and then requests immediate flush | "Definitely committed, cannot roll back" |
| Transaction finishes and `commit` succeeds | Confirms DB operations belonging to the transaction | "Must manually call flush beforehand" |

**Subtlety around transaction boundaries:** Without `@Transactional` on the service, Spring Data repository methods like `save()` or `saveAndFlush()` typically have their own transaction and may **commit before returning**. When the service has an enclosing transaction, repository calls normally **join that transaction**; when `saveAndFlush()` returns, the enclosing transaction has still not committed. The two call patterns yield different observations despite the same API name.

Transaction framing example:

```java
@Transactional
public void updateTwoAccounts(Long firstId, Long secondId) {
    Account first = accounts.findById(firstId).orElseThrow();
    Account second = accounts.findById(secondId).orElseThrow();

    first.setBalance(150L);
    accounts.flush();         // May synchronize changes to first.
    second.setBalance(250L);  // Continue modifying entities in the same transaction.

    // If the transaction rolls back, both changes belonging to the transaction are discarded.
}
```

Calling `flush()` in the middle does not split the method into two transactions or turn the first operation into a separate commit. If two independent transactions are desired, design corresponding transaction/propagation boundaries; that is a separate business decision, not the purpose of flush.

## 7. When does flush happen automatically?

JPA specifies synchronization according to flush mode; Hibernate implements concrete triggers:

- **`FlushModeType.AUTO` (default)**: the provider ensures relevant changes are reflected when executing queries that could be affected, and synchronizes before transaction commit. Hibernate typically flushes before JPQL/HQL queries touching pending changes; rules for native SQL and other APIs can differ.
- **`FlushModeType.COMMIT`**: primarily defers synchronization until commit; do not rely on queries inside the transaction before commit always returning the same results as `AUTO`.
- **Manual flush**: `entityManager.flush()` explicitly requests immediate synchronization.
- **Hibernate-specific modes** like `MANUAL` should not be equated with standard Jakarta Persistence values; understand their configuration and consequences.

The following situations can cause SQL to execute before a manual `flush()`:

1. A query requires up-to-date state under flush mode rules.
2. The provider must INSERT early to obtain generated IDs under certain key strategies, typically `IDENTITY`.
3. The application calls a flushing repository method or another path forcing synchronization.

Therefore, do not use the count of `save()` calls or the appearance of an ID to infer commit; check **actual SQL, transaction boundaries, and commit timing**.

## 8. Observing with two independent SQL connections

The PostgreSQL example below illustrates **transaction isolation**. The `UPDATE` in session A corresponds to the idea of "SQL has reached the DB" after a JPA flush. Two independent database connections/sessions are required; run each block in its designated session.

**Initialization (once; the init transaction auto-commits):**

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL
);

INSERT INTO accounts(id, balance)
VALUES (1, 100)
ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance;
```

**Session A — open a transaction and write without committing:**

```sql
BEGIN;
UPDATE accounts SET balance = 200 WHERE id = 1;
SELECT balance FROM accounts WHERE id = 1;
-- Result in session A: 200
```

**Session B — another connection, READ COMMITTED level (PostgreSQL default):**

```sql
SELECT balance FROM accounts WHERE id = 1;
-- Result: 100, because session A has not committed.
```

**Session A — roll back:**

```sql
ROLLBACK;
```

**Session B — query again:**

```sql
SELECT balance FROM accounts WHERE id = 1;
-- Result: 100. UPDATE in transaction A was undone.
```

If `ROLLBACK` is replaced with `COMMIT` in session A, a new query in session B under `READ COMMITTED` normally reads `200`. If session B is inside a long-lived `REPEATABLE READ` transaction, its snapshot may continue seeing the old version until it finishes; never interpret "once committed, every reader instantly sees the same value" while ignoring isolation.

The SQL illustrated here has no JPA `flush()` API: with direct JDBC/SQL, the `UPDATE` has already been sent, yet remains uncommitted until `COMMIT`.

## 9. Common confusions in real-world applications

### 9.1. Re-reading inside the same transaction

After modifying a managed entity, `entityManager.find()` with the same ID usually returns the managed entity from the Persistence Context; the new value can be read **even before flushing**. Similarly, queries within the transaction can trigger auto-flush. Thus "I can read the new value myself" **does not prove commit occurred**.

### 9.2. Reading from another transaction

Under common isolation levels such as `READ COMMITTED`, another connection does not see uncommitted updates, even if flush already sent SQL. Exact behavior depends on the DB, isolation level, query type, and snapshot. `READ UNCOMMITTED`, if the DB actually supports dirty reads, can behave differently.

### 9.3. Flush succeeds yet commit fails

Deferred constraint errors, deadlocks, connection failures, rollback-only transactions, or commit-time conflicts can still fail the entire transaction. Never return `"payment completed"` solely because `saveAndFlush()` threw no exception.

### 9.4. Deferred flush surfaces errors late

`repository.save()` may return normally, and then a SQL exception appears at auto-flush or commit time. Calling `flush()` deliberately before the next step **can detect some errors early**, but does not guarantee catching all commit errors. After a persistence/flush error, you normally must roll back the current transaction; never assume the Persistence Context remains safe to continue using.

### 9.5. Sending emails, publishing events, or calling external APIs before commit

The database can roll back while external emails/APIs do not roll back with it. If an action must run only after DB commit succeeds, consider transaction-bound events (`@TransactionalEventListener(phase = AFTER_COMMIT)`) or a transactional outbox so event delivery matches system requirements. **Flush provides no guarantees for external side effects.**

### 9.6. JDBC has no JPA dirty checking

With `JdbcTemplate` or raw JDBC, `executeUpdate()` typically sends SQL immediately; the connection's transaction controls commit/rollback. With JDBC batching, `executeBatch()` is when the batch of statements is sent for execution. This is not the same concept as JPA's `EntityManager.flush()`. `flush()` methods on I/O streams, `Writer`s, or files are also unrelated to database transaction commits.

### 9.7. `@Transactional(readOnly = true)`

This is an optimization hint/configuration for read operations and may influence Hibernate's flush mode depending on Spring/provider; do not expect normal entity modification, flushing, and committing inside a read-only method. At the same time, `readOnly` is **not an authorization mechanism or an absolute guarantee that the DB will reject every write statement**.

## 10. When should you explicitly call flush?

**Usually unnecessary:** a `@Transactional` service simply reading/updating entities and completing normally. Let the provider synchronize per flush mode and the transaction manager commit.

**Potentially useful:** when you must detect a DB error early before a subsequent business step; when prior SQL must be processed by the DB before a dependent query; or when controlling batch size in bulk imports (often combining `flush` and `clear` per batch, with awareness of detached state).

**Avoid overuse:** calling `flush()` per record increases round-trips, lock duration, and diminishes JDBC batching benefits. `flush()` does not make commits more certain; it only changes **synchronization timing**.

Questions to ask before calling flush:

1. Am I in the right transaction?
2. Did the prior step modify a **managed**, **new**, or **detached** entity?
3. Do I need SQL sent early, or do I actually need **commit** so another system can see the data?
4. Which errors can appear at flush, and which still wait until commit?
5. If a later step fails, do I want **the entire transaction to roll back**?

## 11. Check your understanding with four statements

- **"Calling `save()` means the DB committed." — False as a general rule.** Inside an outer transaction, save usually just joins that transaction. Without an outer transaction, the repository may create/commit its own transaction.
- **"Once flushed, rollback no longer works." — False.** Flush still belongs to an uncommitted transaction; the database rolls back uncommitted changes.
- **"Without calling flush manually, no SQL executes." — False.** The provider may auto-flush or emit SQL early due to queries, ID strategies, or other operations.
- **"A successful commit means the database confirmed the transaction; controlling non-DB side effects requires separate design." — True.** Commit applies to resources inside the transaction; it does not automatically confirm emails, HTTP calls, external caches, or instantaneous replica synchronization.

**Final takeaway:** **set/managed state** answers "what changes is the application holding"; **flush** answers "which changes has the ORM synchronized as SQL within the transaction"; **commit** answers "did the database accept the transaction successfully or not." Always verify the **transaction owner**, **flush mode**, and **isolation** before concluding an operation has "finished saving."

## Reference documentation

- Jakarta Persistence, `EntityManager` and `flush()`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html
- Jakarta Persistence 3.2, Synchronizing Persistence Context with DB: https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html
- Hibernate ORM User Guide, *Flushing*: https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html
- Spring Data JPA, `JpaRepository.flush()` and `saveAndFlush()`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Spring Data JPA, *Persisting Entities*: https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html
- Spring Framework, transaction proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, `@Transactional` configuration and rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
