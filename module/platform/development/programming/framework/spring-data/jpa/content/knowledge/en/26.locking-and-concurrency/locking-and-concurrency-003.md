# Handling OptimisticLockException and Update Conflicts in Spring Data JPA

When two requests read the same entity and update it nearly simultaneously, the later write can accidentally overwrite the data the earlier request just saved. This is a lost update. Spring Data JPA and JPA providers support optimistic locking to detect this situation using a `@Version` attribute.

When the version in the database has changed since the entity was read, an update or delete using the stale version will match zero rows. The provider throws `OptimisticLockException` and the current transaction must roll back. Spring can translate that error into the `OptimisticLockingFailureException` hierarchy in `org.springframework.dao`.

Handling it properly is not just catching an exception. The application must determine where the conflict occurred, finish the failed transaction, load the fresh state in another transaction, and decide whether the operation can be automatically recomputed or must ask the user to resolve it. This article covers the `@Version` mechanism, errors on update/merge/delete, handling at service/API boundaries, safe retries, pessimistic locking, and how to test two competing transactions.

## 1. How does a lost update happen?

Suppose a document initially has the title `"Draft"` and two users open the edit page at the same time.

| Time | Transaction A | Transaction B |
|---|---|---|
| T1 | Read title Draft | |
| T2 | | Read title Draft |
| T3 | Change title to Approved | |
| T4 | Commit Approved | |
| T5 | | Change title to Review |
| T6 | | Commit Review |

Without concurrency checks, Review overwrites Approved. Transaction B does not know the data it read is stale.

This is a lost update. Similar situations can happen with balances, inventory quantities, order statuses, article contents, or any entity updated by multiple requests.

### 1.1. How does optimistic locking work?

Optimistic locking assumes conflicts do not happen often. Transactions are allowed to read and work concurrently. When writing, the provider checks whether the row's version still matches the version the entity originally read.

If both transactions read version 7:

1. Transaction A updates the row on the condition that version is still 7 and writes the new version 8.
2. Transaction B tries to update the row on the condition that version is 7.
3. The database finds no row still at version 7.
4. The provider sees that the updated row count is 0 and reports an optimistic lock conflict.
5. Transaction B rolls back instead of silently overwriting A.

Optimistic locking does not hold an exclusive lock from read time until the user clicks Save. It detects conflicts during the check/write phase. This approach usually fits well when reads far outnumber writes and conflicts are relatively rare.

## 2. Declaring @Version in an entity

JPA uses the `@Version` annotation to mark the version field. The provider manages this value; the application must not manually increment or assign the version.

Example `Document` entity:

~~~java
package com.example.documents;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Version
    private Long version;

    protected Document() {
    }

    public Document(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String title) {
        this.title = title;
    }
}
~~~

Key points to remember:

- Each entity has at most one version attribute.
- Versions typically use numeric types such as `int`, `Integer`, `short`, `Short`, `long`, or `Long`. Jakarta Persistence also defines several valid temporal types; integer types are usually easy to observe and pass through APIs.
- The version field/property must follow JPA mapping rules, typically on the root entity or mapped superclass and primary table.
- The provider automatically assigns the value on insert and updates it when the entity is written.
- Do not accept a version from the client and call a setter to overwrite the `@Version` field.
- If an entity has no version, JPA does not provide a portable optimistic version check mechanism for that entity.

Using `Long` keeps a new entity's version field initially `null`; after insert, the provider assigns the initial value. Do not manually set the version to 0 or 1 in the constructor.

## 3. SQL the provider uses to detect conflicts

Suppose an entity currently has:

- `id = 42`
- `title = "Draft"`
- `version = 7`

When the entity changes, the provider may generate SQL equivalent to:

~~~sql
UPDATE documents
SET title = ?, version = 8
WHERE id = 42
  AND version = 7;
~~~

If only one transaction writes version 7, the statement updates one row. If another transaction has already updated the version to 8, the statement using version 7 updates 0 rows.

The provider relies on the affected row count to detect stale state. The actual SQL, parameter binding, and exact moment the version is incremented depend on the JPA provider, database, and mapping; the example above illustrates the principle.

When deleting a managed entity, the provider can also include the old version in the DELETE condition. If the row was updated or deleted by another transaction, the delete operation can fail because the version no longer matches.

### 3.1. When is the version check performed?

An exception does not always appear right on the line calling `repository.save()`.

The provider may detect conflicts when:

- Calling `EntityManager.merge()` with a detached entity carrying an old version.
- Calling `flush()` or `repository.flush()`.
- The transaction commits and the provider synchronizes pending changes.

Therefore, the snippet:

~~~java
repository.save(document);
return "updated";
~~~

does not mean the database is guaranteed to have committed successfully before the method returns if transaction boundaries have not been considered. With `@Transactional` via a Spring proxy, commit happens when the proxied call finishes; errors at commit time are still returned to the outer caller.

If you want to detect errors earlier inside the service body, you can call `repository.flush()` or `EntityManager.flush()` after making changes. That causes the provider to send the SQL and perform the version check sooner, though the transaction can still encounter other errors at commit time.

## 4. Properly updating a managed entity

A common pattern is loading the entity inside a transaction, validating input data, changing allowed fields, and letting JPA manage the version.

Repository:

~~~java
public interface DocumentRepository
        extends JpaRepository<Document, Long> {
}
~~~

Command received from the client:

~~~java
public record UpdateDocumentCommand(
        Long expectedVersion,
        String title) {
}
~~~

DTO response:

~~~java
public record DocumentView(
        Long id,
        String title,
        Long version) {
}
~~~

Service:

~~~java
@Service
public class DocumentService {

    private final DocumentRepository documents;
    private final EntityManager entityManager;

    public DocumentService(
            DocumentRepository documents,
            EntityManager entityManager) {
        this.documents = documents;
        this.entityManager = entityManager;
    }

    @Transactional
    public DocumentView update(
            Long id,
            UpdateDocumentCommand command) {

        Objects.requireNonNull(command.expectedVersion(),
                "expectedVersion is required");

        Document document = documents.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Document not found"));

        if (!Objects.equals(
                command.expectedVersion(),
                document.getVersion())) {
            throw new StaleDocumentVersionException(id);
        }

        document.rename(command.title());

        entityManager.flush();

        return new DocumentView(
                document.getId(),
                document.getTitle(),
                document.getVersion()
        );
    }
}
~~~

Custom exception:

~~~java
public class StaleDocumentVersionException
        extends RuntimeException {

    public StaleDocumentVersionException(Long id) {
        super("Document " + id + " has changed since it was read");
    }
}
~~~

There are two layers of protection in the example:

1. Comparing `expectedVersion` with the current version to detect a form/API request that was already stale before the new transaction started.
2. `@Version` protects the window from when the service reads the entity until it flushes/commits. If another transaction writes during this window, the provider detects the conflict.

Do not assign `command.expectedVersion()` to `document.version`. The version is only for comparison and returning to the client; the provider is the component that updates the version in the database.

### 4.1. Why compare the version sent by the client?

Suppose a user opens a document when version is 7. Then someone else saves version 8. The first user clicks Save and the server starts a new transaction.

If the service only loads the latest entity from the database, it receives version 8. If the service does not check version 7 in the request, it could apply the user's stale content onto the version 8 entity and successfully write version 9.

In that case, `@Version` does not detect a conflict because the current transaction read the latest version 8. The time between when the user opened the form and when they submitted the request falls outside this transaction.

Therefore, applications editing data across multiple requests should include the read version in commands, responses, or HTTP ETags. Compare expected version with current version to protect the user's think time.

### 4.2. Using flush to detect errors before building the response

`entityManager.flush()` in the service forces the provider to synchronize pending changes to the database. With optimistic locking, this typically triggers the version check at that point.

After a successful flush, the version getter usually reflects the new version updated by the provider. However, do not catch a flush error and continue using a transaction that has been marked rollback-only.

If you do not call flush explicitly, Spring still flushes on commit. The exception may appear when the transaction interceptor completes the method, meaning the caller receives the error even though the method body has finished executing.

## 5. OptimisticLockException and Spring's exception translation

At the JPA layer, the standard exception is:

`jakarta.persistence.OptimisticLockException`

It indicates that a version check or optimistic lock failed. Per Jakarta Persistence, the provider must mark the current transaction for rollback when detecting an optimistic locking conflict.

When using Spring Data repositories and the exception translation mechanism, persistence errors may be converted into types in `org.springframework.dao`:

- `OptimisticLockingFailureException`: Spring's base type for optimistic locking failures.
- `ObjectOptimisticLockingFailureException`: provides additional entity class and identifier information.
- `JpaOptimisticLockingFailureException`: JPA-specific variant.

Depending on the call path, provider, and exception translation layer, code may see a JPA exception, a Spring exception, or a wrapping transaction exception. If a custom DAO calls provider APIs directly without going through a translator, do not assume every error has already been converted to a Spring DAO exception.

### 5.1. Do not merely catch exceptions around repository.save()

The following snippet is not safe enough:

~~~java
try {
    repository.save(document);
} catch (OptimisticLockingFailureException ex) {
    return "conflict";
}
~~~

Reasons:

- `save()` might not have flushed yet.
- The conflict may occur on flush or commit.
- The transaction may already be marked rollback-only.
- Returning a normal response from a rollback-only transaction can result in an error when the transaction finishes.

Let the exception escape the transaction boundary. Handle it in an outer calling layer after the transaction has rolled back.

## 6. Handling conflicts at service boundaries and REST APIs

Do not catch `OptimisticLockException` inside a `@Transactional` method and continue querying, updating, or returning a normal result. The transaction has been marked rollback-only; the persistence context may contain untrustworthy state.

A controllable way to organize this is to let the service throw the error and use `@RestControllerAdvice` to convert it into an HTTP conflict.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler({
        OptimisticLockingFailureException.class,
        OptimisticLockException.class,
        StaleDocumentVersionException.class
    })
    public ResponseEntity<ProblemDetail> handleOptimisticConflict(
            RuntimeException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Data has been updated by another operation. "
                        + "Please reload the data and confirm your changes."
        );

        problem.setTitle("Update conflict");

        return ResponseEntity
                .status(HttpStatus.CONFLICT)
                .body(problem);
    }
}
~~~

Required imports:

~~~java
import jakarta.persistence.OptimisticLockException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
~~~

`@RestControllerAdvice` handles the error after the service call passes back through the transaction proxy and the transaction has failed. In some applications, the exception may be wrapped in a `RollbackException` or another transaction exception; inspect the actual cause chain and exception translation of your stack.

Do not return stack traces, SQL, table names, or internal database details to clients. Responses should provide a stable error code and instruct the user to reload the data.

### 6.1. Why usually return HTTP 409 Conflict?

`409 Conflict` indicates that the request cannot be completed due to a conflict with the current state of the resource. This is an appropriate choice when the client sends the version in the body or command and the server detects that the state has changed.

If the API uses HTTP conditional requests with `ETag` and the `If-Match` header, when the precondition no longer holds, `412 Precondition Failed` is usually more appropriate. Choose a consistent API contract and clearly document how clients send the version.

### 6.2. Example version response

When reading a document, return the version:

~~~json
{
  "id": 42,
  "title": "Draft",
  "version": 7
}
~~~

When updating, the client sends the version it read:

~~~json
{
  "expectedVersion": 7,
  "title": "Approved"
}
~~~

If the database is already at version 8, the server returns a conflict. The client can load the new data, compare changes, and submit a new command based on the current version.

## 7. Handling detached entities and merge

`EntityManager.merge(detachedEntity)` copies the state of a detached entity into a managed instance in the current persistence context. The object returned by merge is the managed instance; the passed-in object remains detached.

If the detached entity holds an old version, the provider must check the version on merge. Depending on the provider, the error may appear immediately on merge, on flush, or on commit.

Example scenario:

1. Request A loads Document version 4.
2. The entity becomes detached after the transaction ends.
3. Request B updates Document to version 5.
4. Request A submits back the detached entity with version 4.
5. Merging the stale entity must detect the stale revision instead of overwriting version 5.

### 7.1. Avoid mapping the entire request to an entity and merging

Pattern prone to business bugs:

~~~java
Document detached = mapper.toEntity(request);
detached.setId(id);
repository.save(detached);
~~~

If the mapper produces an entity with many null/default fields, merge can copy over fields the client never intended to change. This causes unintended data loss even when the version check does not fail.

Usually you should:

1. Receive a command/DTO containing only the allowed modifiable fields and the expected version.
2. Load the managed entity inside a transaction.
3. Compare the expected version.
4. Apply each allowed change onto the managed entity.
5. Let the provider check the version on flush.

If you truly need to merge a detached graph, you must fully understand merge semantics, cascade MERGE, and how the provider checks versions for each entity in the graph.

### 7.2. Do not modify a detached entity's version

Do not use a setter to force a detached entity's version to the latest version. Doing so invalidates the meaning of the snapshot the client read and allows stale requests to overwrite newer data.

If the client sends version 4, the server must preserve that expected version information for checking. The provider manages the version of the managed entity itself.

## 8. Retrying after an optimistic locking conflict

Not every conflict should be retried automatically.

### 8.1. When should you NOT auto-retry?

With user-submitted edit forms, two people may change the same field with two different intentions. Automatically loading the latest version and reapplying all of the old content turns a lost update into an intentional overwrite by code.

In this case:

- Return HTTP 409 or 412 per the API contract.
- Let the client load the new version.
- Display the changed fields.
- Ask the user to choose which content to keep or to merge them.
- Submit a new command with the new expected version.

Do not automatically retry a request carrying stale user data just to reduce visible errors.

### 8.2. When can retry be appropriate?

Retry can be useful when the operation can be recomputed from the new state, for example:

- Incrementing a counter.
- Updating an aggregated value with deterministic rules.
- Writing derived state from the latest data.
- Performing an internal idempotent operation with no external database side effects before commit.

Each retry must load the fresh entity in a new transaction, recompute the operation on the new state, and limit the number of attempts.

### 8.3. Retries must create a new transaction

A transaction that suffered an optimistic lock failure must roll back. Do not reuse the failed transaction or persistence context.

A coordinator can use `TransactionTemplate` so each attempt gets its own transaction:

~~~java
@Service
public class CounterRetryService {

    private static final int MAX_ATTEMPTS = 3;

    private final TransactionTemplate transactionTemplate;
    private final AccountRepository accounts;
    private final EntityManager entityManager;

    public CounterRetryService(
            PlatformTransactionManager transactionManager,
            AccountRepository accounts,
            EntityManager entityManager) {
        this.transactionTemplate =
                new TransactionTemplate(transactionManager);
        this.accounts = accounts;
        this.entityManager = entityManager;
    }

    // Call this method outside an active transaction.
    public AccountView increment(Long accountId) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                return transactionTemplate.execute(status -> {
                    Account account = accounts.findById(accountId)
                            .orElseThrow();

                    account.incrementCounter();

                    entityManager.flush();

                    return new AccountView(
                            account.getId(),
                            account.getCounter(),
                            account.getVersion()
                    );
                });
            } catch (OptimisticLockingFailureException exception) {
                if (attempt == MAX_ATTEMPTS) {
                    throw exception;
                }
            }
        }

        throw new IllegalStateException("Retry loop exhausted");
    }
}
~~~

DTO and entity in the example:

~~~java
public record AccountView(
        Long id,
        long counter,
        Long version) {
}
~~~

~~~java
@Entity
public class Account {

    @Id
    private Long id;

    private long counter;

    @Version
    private Long version;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public long getCounter() {
        return counter;
    }

    public Long getVersion() {
        return version;
    }

    public void incrementCounter() {
        counter++;
    }
}
~~~

The example illustrates retrying a counter increment operation. `TransactionTemplate.execute` completes the transaction (including commit) before returning the result; if commit fails due to a version conflict, the exception is caught in the loop. The next attempt reads the fresh state again.

The coordinator must be called outside an active transaction so each `execute` actually creates a new transaction. Do not place `@Transactional` around the entire retry loop. In a real application, you can add bounded backoff/jitter to reduce repeated simultaneous collisions among requests.

### 8.4. Do not repeat external side effects outside the database

Do not send emails, call payment gateways, or publish messages directly inside each retry attempt. If the transaction rolls back after an email has been sent, the next attempt may send a duplicate.

Use a transactional outbox or record the event in the same transaction and publish after commit. If an external operation must be retried, use an idempotency key and explicitly design for safe repeated execution.

### 8.5. Limit the number of attempts

Infinite retries can overload the system when many requests continuously contend for the same row. Make sure to:

- Set a small, finite number of attempts.
- Only retry optimistic conflict errors that can be resolved by recomputing.
- Do not retry validation or business errors.
- Monitor conflict and retry rates.
- Switch to pessimistic locking or redesign the flow if high contention persists.

## 9. Using an optimistic lock to verify a read-only operation

A versioned entity is not automatically re-checked just because a transaction reads the entity and ends without modifying it.

If the business logic depends on the data remaining unchanged throughout the transaction, you can request an explicit optimistic lock:

~~~java
entityManager.lock(
        document,
        LockModeType.OPTIMISTIC
);
~~~

`LockModeType.OPTIMISTIC` asks the provider to verify the entity's version before the transaction completes. It is useful when a transaction has read data and needs to be sure that the data did not change before a related decision is committed.

If you need to increment the version even when no business field on the entity changed, you can use:

~~~java
entityManager.lock(
        document,
        LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

Force increment is useful for coordinating changes at the aggregate root level or signaling to other transactions that the protected state has changed.

Use explicit optimistic locks only when there is a business reason. Checking the version at the end of a transaction can roll back work already performed if a conflict is detected.

## 10. When to use pessimistic locking?

Optimistic locking fits when conflicts are rare. If many transactions frequently update the same row, repeated retries can waste resources. In that case, pessimistic locking may be a better fit.

Spring Data JPA lets you specify a lock mode using `@Lock`:

~~~java
public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from Document d where d.id = :id")
    Optional<Document> findByIdForUpdate(@Param("id") Long id);
}
~~~

The service calls this method inside a transaction:

~~~java
@Transactional
public DocumentView updateWithDatabaseLock(
        Long id,
        String newTitle) {

    Document document = documents.findByIdForUpdate(id)
            .orElseThrow();

    document.rename(newTitle);

    return new DocumentView(
            document.getId(),
            document.getTitle(),
            document.getVersion()
    );
}
~~~

`PESSIMISTIC_WRITE` asks the database to lock the row so competing transactions must wait or fail depending on the database and lock timeout. The transaction must be kept short because the lock persists for the duration of the transaction.

### 10.1. Comparing the two strategies

| Criterion | Optimistic locking | Pessimistic locking |
|---|---|---|
| When conflicts are detected/prevented | Checked on write or version validation | Database lock acquired before operating |
| Best suited for | Low conflict, read-heavy workloads | Frequent conflicts on the same row |
| Cost on conflict | Transaction must roll back, may retry | Transaction may wait for lock or time out |
| Concurrency impact | Minimal locking during reads | Other transactions may be blocked |
| Operational risk | Retry storm under high contention | Deadlocks, lock timeouts, and waiting queues |
| Mapping requirement | Entity needs a version for portable optimistic checks | Pessimistic locks can also be used on non-versioned entities, depending on API/provider |

Pessimistic locking is not a cure-all for every conflict. It can reduce throughput if a transaction performs heavy work or calls external services while holding locks.

### 10.2. Lock timeouts and deadlocks

When a pessimistic lock cannot be acquired, the provider may throw `PessimisticLockException` or `LockTimeoutException` depending on the rollback scope reported by the database/provider. Deadlocks can also cause a transaction to fail.

Do not use the same handling logic for all concurrency exceptions. Optimistic conflicts usually need reload/merge; lock timeouts may need a short transaction retry with backoff; deadlocks require reviewing resource access order and transaction design.

## 11. Version only protects the versioned entity

`@Version` protects an entity's state according to JPA rules. It does not automatically create a shared version across all related entities.

For example, an Order has multiple OrderLines. If two transactions update different lines, each OrderLine's version can change independently. The root Order's version does not necessarily increment if only a child entity is updated and no state belonging to Order changes.

If a business invariant depends on the entire aggregate, you need a coordination mechanism:

- Have every operation modifying the aggregate increment the root's version.
- Use `OPTIMISTIC_FORCE_INCREMENT` when the root needs to be validated.
- Or use a pessimistic lock on the root following a protocol obeyed by all writers.
- Use database constraints for invariants that can be expressed as constraints.
- Re-verify all business conditions in the transaction before committing.

Locking the root does not automatically lock or version every child entity. All write flows must follow the same protocol for the root to genuinely act as the coordination point.

## 12. Do bulk updates/deletes bypass optimistic locking?

Yes. JPQL bulk updates/deletes, CriteriaUpdate/CriteriaDelete, and native SQL operate directly on sets of rows in the database. They do not load individual entities and do not run version checks like normal managed-entity updates/deletes.

Consequences:

- Bulk UPDATE does not automatically check the old version of each entity.
- Normal bulk UPDATE does not automatically increment the version via the entity lifecycle mechanism.
- Bulk DELETE does not automatically validate versions as individual entity deletion does.
- The persistence context does not automatically synchronize with the bulk operation's results.
- Database foreign keys with `ON DELETE CASCADE` can still delete child rows via the constraint; that is database behavior, not JPA optimistic locking or cascade callbacks.

If you need compare-and-set for a bulk update, put the expected version in the WHERE clause and increment the version in the statement itself. Illustrative SQL for the inventory table:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND available >= :quantity;
~~~

Interpreting the affected row count:

- `1`: operation succeeded; version was incremented.
- `0`: no matching row. Could be because the version changed, the row does not exist, or quantity is insufficient; additional queries are needed if the API must distinguish the causes.

After a bulk operation, flush beforehand if there are pending changes and clear/refresh the persistence context appropriately. Do not keep using old entity instances as if they had been synchronized.

If you need lifecycle callbacks, cascades, or per-entity optimistic locking, use managed-entity operations instead of bulk updates/deletes.

## 13. Conflicts when updating the same field vs. different fields

Version-based optimistic locking generally protects the entity's entire versioned state. Two transactions modifying two different fields on the same entity can still conflict if both read the same version.

For example:

- Transaction A changes title.
- Transaction B changes description.
- Both read version 10.
- A commits and version becomes 11.
- B tries to write using version 10 and hits a conflict.

This is conservative behavior that helps prevent lost updates when the entity is treated as a single unit of consistency.

If the business logic wants two independent changes to succeed together, consider:

- Splitting state into separate entities with their own lifecycles and versions.
- Using dedicated commands that update a specific field with explicit conditions.
- Using atomic database updates that allow independent increments/decrements or updates.
- Determining which invariants truly need to be protected at the aggregate level.

Do not disable versioning just to reduce conflicts without evaluating the risk of lost updates.

## 14. Testing optimistic locking with two independent transactions

A good test must create two separate persistence contexts/transactions. If both operations run in the same transaction and the same persistence context, the test fails to simulate stale entities from two requests.

Example using a Spring Boot integration test and `TransactionTemplate`:

~~~java
@SpringBootTest
class DocumentOptimisticLockingTest {

    private final TransactionTemplate transactions;
    private final DocumentRepository documents;

    DocumentOptimisticLockingTest(
            PlatformTransactionManager transactionManager,
            DocumentRepository documents) {
        this.transactions =
                new TransactionTemplate(transactionManager);
        this.documents = documents;
    }

    @Test
    void staleDetachedEntityCannotOverwriteNewerCommit() {
        Long id = transactions.execute(status ->
                documents.saveAndFlush(
                        new Document("Initial")
                ).getId()
        );

        Document snapshotA = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        Document snapshotB = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        assertThat(snapshotA.getVersion())
                .isEqualTo(snapshotB.getVersion());

        transactions.executeWithoutResult(status -> {
            Document current = documents.findById(id).orElseThrow();
            current.rename("Winner");
            documents.flush();
        });

        assertThatThrownBy(() ->
                transactions.executeWithoutResult(status -> {
                    documents.save(snapshotB);
                    documents.flush();
                })
        ).isInstanceOf(OptimisticLockingFailureException.class);

        Document persisted = transactions.execute(status ->
                documents.findById(id).orElseThrow()
        );

        assertThat(persisted.getTitle()).isEqualTo("Winner");
    }
}
~~~

The transactions in the test finish sequentially before the next transaction starts. Snapshots A and B are loaded in two separate transactions and become detached after commit. The winning update transaction commits first; when stale snapshot B is merged and flushed, the version no longer matches so the operation fails.

This test must not be wrapped in an outer transaction covering the entire method. If using `@DataJpaTest`, disable the test's default transaction or configure independent transactions; otherwise, `TransactionTemplate` calls may participate in the same test transaction by default and distort the simulation.

`saveAndFlush()` and `flush()` help push SQL within the test scope. Exceptions can still surface at transaction commit; therefore, wrap the entire `transactions.execute` call in the assertion, not just a single save call.

### 14.1. Testing expectedVersion from the client

In addition to testing a race between two transactions, test stale requests:

1. Create document version 1.
2. Update document to version 2.
3. Send a command with expectedVersion 1.
4. Verify the service rejects it before modifying the content.
5. Re-read and verify version 2 data was not overwritten.

This test protects the time window between when the client reads data and when it submits the update command, which does not lie within a single database transaction.

### 14.2. Testing exceptions at commit

If the service does not explicitly flush, the test needs to wrap the call through the Spring proxy or transaction template to catch the error at commit time. Asserting only that the method body ran is not sufficient to conclude the transaction succeeded.

### 14.3. Using a production-like database

Basic optimistic version checks can usually be tested on an embedded database, but locking, timeouts, isolation, and deadlocks are database-dependent. For critical concurrency behavior, run integration tests using Testcontainers with an engine and version close to production.

## 15. Observing conflicts in production

Monitor optimistic conflict counts to know whether the current strategy still fits.

Useful metrics:

- Count of `OptimisticLockException` or `OptimisticLockingFailureException` by entity/use case.
- Conflict rate relative to total updates.
- Average retry count and retry success rate.
- Number of requests returning 409/412.
- Transaction duration and lock wait time.
- Frequently contended entity IDs or aggregates, logged with sensitive information masked.

If a particular entity type sees a sudden spike in conflicts, check:

- Many requests are updating the same row.
- Transactions are kept open longer than necessary.
- Clients hold forms open for too long before saving.
- Background jobs and interactive requests write to the same aggregate concurrently.
- Bulk updates or native SQL are bypassing the version.
- The root version is not being incremented when an invariant depends on multiple child entities.

Do not log full entity payloads or personal data just to diagnose conflicts. Log technical IDs, operation type, expected/current version where appropriate, and correlation IDs per security policy.

## 16. Common mistakes

| Symptom | Cause | How to handle |
|---|---|---|
| Old data overwrites new data | Entity lacks `@Version` or code skips version checks | Add version and audit all write paths |
| Exception occurs at commit, not save | Provider defers version check until flush/commit | Handle at the transaction boundary |
| Caught exception but transaction still rolls back | Transaction was marked rollback-only | Let the exception escape the transaction; handle in the caller |
| User submits stale form with no exception | Service loads new version then applies stale payload | Send expectedVersion/ETag and compare |
| Merge overwrites multiple fields | Mapping full DTO to detached entity | Load managed entity then apply allowed fields |
| Retries keep failing repeatedly | Reusing stale object or old transaction | Reload entity in a new transaction |
| Retry sends emails/messages multiple times | Side effects live inside the retried transaction | Use an outbox and idempotency keys |
| Version unchanged after bulk update | Bulk DML bypasses version lifecycle | Use compare-and-set and explicit version increment |
| Two child entities change without root conflict | Version only protects the versioned entity | Increment root version or use a lock protocol |
| Pessimistic lock causes long request waits | Transaction holds lock for too long | Shorten transactions, configure timeouts, and review contention |
| Test fails to reproduce conflict | Two operations share a transaction/persistence context | Use two independent transactions |
| Disabling @Version to avoid errors | Conflicts are hidden and lost updates can return | Split aggregates or design appropriate update commands |

## 17. Optimistic locking checklist

- [ ] Entities accessed concurrently have an appropriate `@Version` field.
- [ ] The application never modifies the version value directly.
- [ ] DTOs/responses return the version so clients can send expected version when needed.
- [ ] Services validate expectedVersion to detect stale forms/requests.
- [ ] Transactions allow the provider to check for races between load and flush/commit.
- [ ] It is understood that exceptions can appear at merge, flush, or commit.
- [ ] Errors are not caught only to keep using a rollback-only transaction.
- [ ] Spring exception translation is configured and tested.
- [ ] APIs have a clear 409 or 412 contract.
- [ ] Merging detached entities does not overwrite unintended fields.
- [ ] Retries apply only to operations that can be safely recomputed.
- [ ] Each retry attempt uses a fresh transaction and persistence context.
- [ ] Retries are bounded and use appropriate backoff.
- [ ] External side effects outside the database do not repeat on retry.
- [ ] Bulk DML has dedicated compare-and-set/version handling.
- [ ] Aggregate invariants are protected at the proper root or via database constraints.
- [ ] Tests cover both stale requests and two competing transactions.
- [ ] Tests catch exceptions across the entire transaction commit.
- [ ] Conflict rate, retry rate, and transaction duration are monitored.

## 18. References

- [Jakarta Persistence 3.2 — Optimistic Locking](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html) — version attributes, merge, version checks, and rollback requirements on optimistic lock failure.
- [Jakarta Persistence — Version API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/version) — `@Version` annotation and supported version data types.
- [Hibernate ORM 8 — Locking](https://docs.hibernate.org/orm/8.0/userguide/html_single/#locking) — versioned optimistic locking, lock modes, bulk updates/deletes, and stale state.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html) — using `@Lock` to set LockModeType on query methods and CRUD methods.
- [Spring Framework — DAO Support and Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html) — translating JPA/Hibernate exceptions into Spring's `DataAccessException` hierarchy.
- [Spring Framework — ObjectOptimisticLockingFailureException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/ObjectOptimisticLockingFailureException.html) — Spring exception providing entity and identifier details when optimistic locking fails.

Optimistic locking detects updates based on stale versions and prevents lost updates. To handle it properly, protect both the transaction window using `@Version` and user think time using expectedVersion/ETag. When a conflict happens, let the failed transaction roll back, load fresh state in another transaction, and retry only when the business logic can safely recompute. Under high contention or complex invariants, consider lock modes and redesigning aggregate boundaries.