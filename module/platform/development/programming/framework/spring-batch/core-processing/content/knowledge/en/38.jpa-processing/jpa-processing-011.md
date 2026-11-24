# Entity State After Rollback

When Spring Batch writes data with JPA, each chunk typically runs inside a transaction. If the writer flushes data and another operation in the chunk fails, the transaction can roll back. The database undoes the changes belonging to that transaction, yet **Java objects in memory do not automatically revert to their pre-transaction state**.

This is a frequent source of bugs on retry or restart. An entity may still carry mutated fields, a provider-assigned ID, or an incremented `@Version` from the flush, even though the corresponding row was never committed. After a rollback, do not continue treating old objects as a reliable source of truth. Understand managed/detached states, discard stale persistence contexts, and reload state from the database in a new transaction when needed.

## 1. Entity states in JPA

JPA defines the entity lifecycle using four primary states:

| State | Meaning | Tracked by persistence context? |
|---|---|---:|
| New / transient | Object newly created via `new`, not yet persisted or merged. | No. |
| Managed / persistent | Entity currently belongs to a persistence context. JPA tracks its changes. | Yes. |
| Removed | Managed entity marked for deletion via `remove()`. | Yes, until changes are synchronized and the context ends. |
| Detached | Entity that was previously managed but no longer belongs to a persistence context. | No. |

Example:

```java
Customer customer = new Customer("C001", "Nguyen An"); // New

entityManager.persist(customer);                         // Managed
customer.setName("An Nguyen");                          // Still managed

entityManager.detach(customer);                         // Detached
```

A detached entity remains a regular Java object. Already-loaded fields and relationships stay in memory, but JPA no longer automatically dirty-checks new changes on that object.

## 2. How does rollback affect entities?

Rollback undoes the transaction's database changes. It is not an operation that restores the heap object graph.

For example, an entity starts in the database with this state:

```text
Database before transaction:
  customer C001, name = "Nguyen An", status = READY

Within transaction:
  entity.setName("An Nguyen")
  entity.setStatus(PROCESSED)
  entityManager.flush()

Transaction rolls back:
  Database remains name = "Nguyen An", status = READY
  Java object may still have name = "An Nguyen", status = PROCESSED
```

After a rollback, entities that participated in the persistence context are no longer a trustworthy source of state. Under the JPA lifecycle, rollback leaves entities previously managed in the persistence context detached; Java field values are not restored to their transaction-start snapshots. Applications should discard those instances or reload data in a fresh persistence context/transaction.

Key points:

- Database rollback does not equal Java object rollback.
- `clear()` detaches entities, and likewise does not restore modified fields.
- A detached entity may hold data that diverges from the database.
- To get current database state, `find()` or re-query inside a new transaction.

## 3. Distinguishing rollback, flush, and clear

These operations address different concerns:

| Operation | Impact on database | Impact on in-memory entities |
|---|---|---|
| `flush()` | Sends SQL for pending changes in the persistence context within the current transaction. | Entities stay managed; fields are not reverted. |
| `clear()` | Does not send SQL or commit by itself. | Detaches all entities from the persistence context. Object fields remain unchanged. |
| `rollback()` | Undoes the transaction's database changes. | Does not revert Java fields; entities in the rolled-back persistence context become detached and untrustworthy. |
| `commit()` | Finalizes the transaction if error-free. | Entities remain subject to persistence context lifecycle; transaction-scoped contexts end with the transaction. |

Example:

```java
entity.setStatus(Status.PROCESSED);
entityManager.flush();

// SQL has been sent, yet the transaction can still roll back.
```

`flush()` is not commit. If a constraint violation or exception occurs after flush but before commit, the database can still roll back the sent SQL.

## 4. Example of an entity mutated while the database rolls back

Suppose a service modifies a customer and intentionally throws an error:

```java
@Transactional
public void updateCustomerThenFail(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setStatus(Status.PROCESSED);

    entityManager.flush();

    throw new IllegalStateException("Force rollback");
}
```

Once the exception exits the transaction boundary and the transaction rolls back:

- The database row retains its old status.
- The `customer` object that was used may still hold `PROCESSED`.
- Do not cache that object assuming it represents the database.
- Subsequent processing must reload a fresh entity in a new transaction.

Example reloading in a new transaction:

```java
Customer current = transactionTemplate.execute(status ->
        entityManager.find(Customer.class, customerId));
```

This snippet illustrates the principle. In real applications, ensure `TransactionTemplate` uses a compatible JPA transaction manager and `EntityManager` is a Spring-managed proxy.

## 5. Generated IDs may still remain after rollback

A confusing case is when an entity persisted in a rolled-back transaction still retains an ID on the Java object.

Example:

```java
Customer customer = new Customer("C999", "Temporary");
entityManager.persist(customer);
entityManager.flush();

Long generatedId = customer.getId();
// Afterward the transaction rolls back.
```

Depending on ID generation strategy and provider, the ID may be assigned before commit. With sequences, database sequences normally do not roll back with transactions; an allocated value may leave a gap. With `IDENTITY`, an insert may execute early to obtain the ID. Thus, the object can retain an ID even though no row exists after rollback.

Never infer from a non-null ID that an entity committed successfully. After a rollback, inspect the database in a new transaction if you need to check whether the row exists.

Do not reuse an object from a failed persist as a brand-new entity merely because the row rolled back. Depending on ID strategy/provider, the object may retain an identifier and lifecycle state unsuitable for re-persisting. Construct a fresh entity instance from input data or reload by business key.

## 6. @Version values after rollback

With optimistic locking, JPA/the provider manages the `@Version` field. When an update flushes, the version on the entity may be incremented to reflect the pending update.

Example:

```java
@Entity
class Customer {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;
}
```

Suppose the database has `version = 4`. Inside the transaction, the entity changes status and flushes; the provider may update the object to `version = 5`. If the transaction rolls back, the database still holds `version = 4`, whereas the Java object still holds `5`.

Using that stale object for a later update can trigger optimistic locking stale-state errors or confusing behavior. Reload the entity in a fresh persistence context to obtain the current version.

Never manually decrement the version on a Java object to "match" the database. Version is a JPA/provider concurrency mechanism; only database state read in a new transaction is authoritative.

## 7. New, managed, and removed entities on rollback

Common scenarios:

| Before rollback | What happened in transaction | Database after rollback | How to handle the object |
|---|---|---|---|
| New | `persist()` and flush insert | No new row if the insert belonged to the rolled-back transaction. | Discard the old object; create a fresh instance if retrying. |
| Managed | Mutated fields and flushed update | Row retains its pre-transaction values. | Reload a fresh entity; do not treat old fields as current state. |
| Managed | `remove()` and flush delete | Row still exists if the delete rolled back. | Reload the entity in a new transaction. |
| Detached | `merge()` created/updated managed copy then rolled back | Database retains pre-transaction state. | Input object remains detached; managed copy is untrustworthy. Reload data. |

Rollback does not replace existing objects in Java variables with a fresh object graph. References held by code continue pointing to the exact same objects with their current fields.

## 8. merge() does not make the input object managed

`EntityManager.merge(detached)` copies state from the input object into a managed instance and returns that instance. The passed-in object itself does not become managed.

```java
Customer detached = loadEarlier();
detached.setName("Updated");

Customer managedCopy = entityManager.merge(detached);
```

In this example:

- `detached` remains a detached object.
- `managedCopy` is the managed instance in the current persistence context.
- Changes on `managedCopy` are tracked by JPA.

If the transaction rolls back, do not continue using `managedCopy` as a managed entity in a new transaction. The original `detached` object may also still hold edited fields. Reload state from the database and decide explicitly which updates to reapply.

## 9. Persistence context after rollback

Applications should treat a persistence context that participated in a rolled-back transaction as unfit for continuing business logic with the old entities.

In Spring, an `EntityManager` injected via `@PersistenceContext` is typically a proxy resolving the `EntityManager` bound to the current transaction. When a transaction ends or rolls back, the transaction-scoped `EntityManager` is managed by Spring/JPA lifecycles. The next transaction receives a fresh persistence context.

If an application creates its own `EntityManager` via `EntityManagerFactory.createEntityManager()`, the application owns its lifecycle. After a rollback, close and discard that `EntityManager` per contract, and create a new context for subsequent work. Never reuse a manually created `EntityManager` that participated in a failed transaction.

With extended persistence contexts or specialized setups, lifecycle details vary by container/provider. The safe rule remains: never trust entity state in a rolled-back context; reload in a clean context.

## 10. Spring Batch retries may encounter already-mutated objects

In a chunk-oriented step, a chunk typically executes:

```text
BEGIN transaction
  read items
  process items
  writer writes data
  update checkpoint
COMMIT
```

If the writer or another operation in the chunk throws an exception, the transaction rolls back. Spring Batch may retry according to fault-tolerance settings, or the step may fail and restart later.

Database state and in-memory item state have different lifecycles:

- The database rolls back changes made in the transaction.
- Java items may have been mutated directly by the processor.
- Merged or persisted entities may have received new IDs or versions in memory.
- Objects inside the persistence context are not reset to initial state.
- How the framework retains, caches, or re-reads items depends on the reader, retry policy, and step configuration.

Therefore, processors and writers must be designed for safe re-execution. Never assume a retry always receives brand-new objects or entities whose state has been reset.

## 11. Avoid mutating input entities directly in the processor

If the processor mutates entities returned by the reader directly, retries may encounter objects already carrying changes from the previous attempt.

Error-prone example:

```java
@Bean
ItemProcessor<Customer, Customer> processor() {
    return customer -> {
        customer.setStatus(Status.PROCESSED);
        customer.setName(customer.getName().trim());
        return customer;
    };
}
```

If `customer` is managed or retained across attempts, object mutations happen immediately on the heap before transaction commit. Database rollback does not undo setter calls.

A more controllable approach uses immutable DTOs as input and produces new output objects:

```java
@Bean
ItemProcessor<CustomerInput, CustomerUpdate> processor() {
    return input -> new CustomerUpdate(
            input.customerId(),
            input.name().trim(),
            Status.PROCESSED);
}
```

The writer then loads the current entity within the chunk transaction and applies `CustomerUpdate`. This decouples read data from managed entities and makes retries predictable.

## 12. Does the reader return detached or managed entities?

Not every JPA reader returns entities in the same state:

- `JpaPagingItemReader` has its own `EntityManager` lifecycle for page reading; entities may detach once the reader clears the context or finishes a page.
- A custom reader may return entities from the chunk's transaction-scoped `EntityManager`, depending on injection and transaction configuration.
- JDBC readers generally return DTOs or plain objects not managed by JPA.
- Readers using projections normally do not return managed entities.

Determine the actual item state before designing processors and writers. Never assume entities returned by a reader are always managed in the writer's transaction.

If the reader returns detached entities, the writer can use `merge` to apply state, while accounting carefully for stale data and optimistic locking. If only a few fields are needed, DTOs/projections are usually simpler.

## 13. JpaItemWriter and rollback

`JpaItemWriter` writes chunk items using JPA. Depending on configuration, it uses `merge()` or `persist()`, then flushes and may clear the persistence context.

Example:

```java
@Bean
JpaItemWriter<Customer> customerWriter(EntityManagerFactory emf) {
    JpaItemWriter<Customer> writer = new JpaItemWriter<>();
    writer.setEntityManagerFactory(emf);
    writer.setUsePersist(false);
    writer.setClearPersistenceContext(true);
    return writer;
}
```

If `JpaItemWriter` flushes successfully yet a listener or subsequent step fails and rolls back the chunk:

- The database undoes inserts/updates from that transaction.
- Clearing (if invoked) only detaches entities; it does not reset Java fields.
- Input entities may retain updated IDs, versions, or mutated fields.
- Retries and restarts must rely on checkpoints and fresh database state, never on old objects reverting to pre-write state.

`clearPersistenceContext` is not a rollback recovery mechanism for entities. It is a memory and managed-state management step after the writer processes a chunk.

## 14. Never reuse an EntityManager after rollback as if nothing happened

Once a transaction rolls back, the persistence context and entity states may no longer be consistent. Do not keep running operations on the same context with old entities without clear lifecycle management.

With a Spring-managed `EntityManager`:

- Let the Spring transaction manager finish the transaction.
- Never call `EntityTransaction.rollback()` manually on a shared `EntityManager` proxy.
- Start a new transaction for the next attempt.
- Reload needed entities in the new transaction.

With an application-managed `EntityManager`:

- Terminate the transaction using the proper API.
- Close the `EntityManager` if required by lifecycle or when the context is compromised.
- Never share a manual `EntityManager` across threads or transactions.
- Create a fresh context for the next attempt.

Once a transaction is marked rollback-only, catching an exception and continuing to write inside that same transaction will not make the transaction valid again. Let the transaction finish and start a new transaction.

## 15. Refresh and reload after rollback

`refresh(entity)` reloads database state into a **managed** entity. It is not a general way to rescue a detached entity after rollback.

If an entity is still managed in a valid context, `refresh()` can overwrite current state with database state. After a rollback, however, prefer a new transaction/persistence context and re-query the entity:

```java
Customer current = entityManager.find(Customer.class, customerId);
```

If an old object is detached and needs merging, remember `merge()` returns a new managed instance:

```java
Customer managed = entityManager.merge(detachedCustomer);
```

Do not keep mutating `detachedCustomer` expecting post-merge changes to be dirty-checked. Use `managed` when working inside the current context.

However, merging a whole detached entity can overwrite newer database fields with stale values from the old object. For retries after rollback, reloading by ID and selectively reapplying business changes is usually safer than blind merging.

## 16. Optimistic locking and retry after rollback

When two transactions update the same entity, `@Version` detects stale updates. After a rollback, the old entity may carry a version that no longer matches the database.

Example:

```text
Initial database: id=10, version=3, status=READY

Transaction A:
  load version 3
  update status
  flush -> expected version in DB transaction becomes 4
  rollback

Database after rollback:
  id=10, version=3, status=READY

Object A on heap:
  may still carry version 4 and modified status
```

If another transaction subsequently commits version 4, Object A becomes even staler. The retry should load a fresh entity, inspect current state, and decide whether business logic can still apply or needs conflict handling.

Never retry `OptimisticLockException` blindly forever. Retrying helps only with a reload strategy, business-precondition revalidation, and a bounded attempt limit.

## 17. Chunk rollback and reader checkpoints

Spring Batch persists checkpoints alongside transactions/chunks per step lifecycle. When a chunk rolls back, the uncommitted chunk's checkpoint is not recorded as completed; a retry or restart can re-read items belonging to that chunk.

Example:

```text
Chunk 1: items 1-100 -> committed successfully
Chunk 2: items 101-200 -> writer flushes, then errors -> rollback

Database:
  chunk 1 changes retained
  chunk 2 changes rolled back

Checkpoint:
  retains committed position after chunk 1

Retry/restart:
  reprocesses chunk 2 items per reader semantics
```

This does not mean Java objects from chunk 2 were reset. The reader may re-read items from the source or the framework may replay cached items during retry; exact behavior depends on the reader and fault-tolerance configuration.

Consequently, never use mutable entity instances to store batch progress. Progress belongs in `ExecutionContext`/`JobRepository` or a store with clear transactional semantics.

## 18. Retry, skip, and entity state

Retries and skips can cause the same item to go through multiple attempts. Distinguish:

| Behavior | Meaning |
|---|---|
| Retry | Re-attempts a failed operation per policy; the previous attempt's transaction may have rolled back. |
| Skip | Accepts dropping a faulty item per skip policy after framework transaction/error handling. |
| Restart | Creates a new `JobExecution` for the same `JobInstance` and restores from the committed checkpoint. |

If the processor mutates input entities, retries may receive objects with already-altered fields. If the writer merges an entity whose ID/version changed in an earlier attempt, retries can trigger stale-state or conflict errors.

Safe design practices:

- Keep processors as side-effect-free as possible.
- Prefer immutable DTOs or instantiate fresh output objects.
- Have the writer reload entities by business key inside the active transaction when updating.
- Use optimistic locking to detect conflicts instead of silent overwrites.
- Restrict retry policies to recoverable errors; never retry permanent data errors.
- Use skip listeners or rejected-record stores to audit dropped items.

## 19. External side effects do not roll back with JPA

Database rollback undoes only resources participating in that transaction. If a processor or writer sent an email, called an HTTP API, published a message, or wrote a file outside the transaction, those side effects remain after the database rolls back.

Example:

```text
Chunk transaction:
  update Order in database
  payment API call succeeds
  subsequent database write fails
  transaction rolls back

Result:
  database does not retain Order update
  payment API may still have processed the payment
```

Never place non-idempotent side effects inside a processor expecting rollback to undo them. Common patterns:

- Transactional outbox: record events inside the same database transaction and publish after commit.
- Idempotency keys: send a stable key so receivers recognize repeated requests.
- Reconciliation: reconcile state between the database and external systems.
- Staging/publish: write temporary files and publish only after the transaction or job completes.

Entity state after rollback and external side effects are related yet distinct concerns; both must be engineered for retry and restart.

## 20. Transaction manager and JPA rollback

In Spring Batch, the step should use a transaction manager compatible with `EntityManagerFactory` so the JPA writer properly participates in chunk transactions.

Example:

```java
@Bean
JpaTransactionManager jpaTransactionManager(EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}

@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        JpaTransactionManager jpaTransactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        JpaItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(200, jpaTransactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

In applications with multiple datasources or transaction managers, specify explicitly which manager governs the step and which resources participate in the transaction. Never assume an arbitrary JDBC transaction manager will synchronize a JPA persistence context.

## 21. Never catch exceptions and continue in a rollback-only transaction

A persistence failure can mark a transaction rollback-only. If code catches the exception inside the same transaction and keeps writing, final commit will still fail or the transaction manager will throw `UnexpectedRollbackException`.

Anti-pattern example:

```java
@Transactional
public void process(Customer customer) {
    try {
        repository.save(customer);
        entityManager.flush();
    } catch (PersistenceException exception) {
        log.warn("Write failed", exception);
        // Continuing to work in a transaction that may already be rollback-only.
    }
}
```

Let exceptions reach the transaction boundary for a clean rollback, then handle retry or recovery in a new transaction. If you need to catch an error to branch business logic, explicitly design transaction propagation and rollback rules rather than using a broad `catch`.

## 22. Entity graphs and relationships after rollback

Rollback does not reconstruct the state of an entire object graph. If a processor mutates both sides of a relationship in memory:

```java
order.setCustomer(customer);
customer.getOrders().add(order);
```

the database rolls back the foreign-key change, yet Java collections and references retain the added link. Reusing old objects can expose a relationship that does not exist in the database.

For bidirectional relationships, applications must maintain both owning and inverse sides properly when transactions succeed. After a rollback, never trust the old object graph to reflect database state. Reload the aggregate or related entities in a new persistence context.

For lazy collections, detached entities cannot load uninitialized data. Query and fetch needed data in a fresh transaction instead of trying to access old proxies.

## 23. Entity state with savepoints or nested transactions

Some databases and transaction managers support savepoints or nested transactions at the JDBC layer. However, JPA persistence contexts do not necessarily have partial-rollback semantics matching savepoints.

If partial SQL rolls back to a savepoint while the persistence context still retains mutated entities, in-memory state can diverge from the database. Do not assume savepoints automatically restore entity fields or versions.

When nested or partial rollback is required:

- Verify whether the transaction manager and provider support that model.
- Determine how the persistence context is synchronized or cleared after rolling back to a savepoint.
- Reload needed entities whenever state is uncertain.
- Write integration tests against the real database.

In batch processing, it is usually simpler and safer to use explicit chunk transactions, Spring Batch skip/retry policies, and one transaction boundary per chunk rather than managing savepoints manually inside a writer.

## 24. Handling entities after rollback in a service

A service may need to run compensation or record failures after a rollback. Separate that work into a new transaction:

```java
@Service
public class CustomerRecoveryService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String customerId, String reason) {
        // Write audit/recovery record in a new transaction.
    }
}
```

`REQUIRES_NEW` starts an independent transaction when invoked through a Spring proxy. Account for connection pool sizing, locking, and the fact that the audit transaction commits even when the outer batch transaction rolls back.

Never pass an old managed/detached entity into a recovery service assuming its state is accurate. Pass the business key and error details; if recovery needs current state, re-query inside the new transaction.

## 25. Testing entity state after rollback

Tests should prove two independent outcomes:

1. The database retains none of the rolled-back transaction's changes.
2. Java objects do not automatically revert to their initial values.

Example test with `TransactionTemplate`:

```java
@Test
void rollbackDoesNotRestoreJavaObjectFields() {
    Customer customer = new Customer("C001", "Nguyen An");

    assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
        entityManager.persist(customer);
        entityManager.flush();

        customer.setName("Changed in memory");
        entityManager.flush();

        throw new IllegalStateException("Force rollback");
    }));

    // Java object may still hold the modified value.
    assertThat(customer.getName()).isEqualTo("Changed in memory");

    // Query in a new transaction to verify database state.
    String databaseName = transactionTemplate.execute(status ->
            entityManager.createQuery(
                    "select c.name from Customer c where c.customerId = :id",
                    String.class)
                    .setParameter("id", "C001")
                    .getResultStream()
                    .findFirst()
                    .orElse(null));

    assertThat(databaseName).isNull();
}
```

This example assumes `customerId` has a unique constraint and `EntityManager` is Spring-injected. In real tests, never use the same rolled-back transaction to query results; run verification queries in a new transaction.

## 26. Testing generated IDs and versions

If the application relies on IDs or versions, test on the real database/provider:

- Persist a new entity and flush so the provider assigns an ID.
- Force a transaction rollback.
- Verify the row does not exist in a new transaction.
- Observe whether the Java object retains an ID, without treating reset as a guaranteed contract.
- Update a `@Version` entity, flush, and roll back.
- Verify the database version retains its pre-transaction value.
- Verify a fresh load receives the database version rather than the stale object's version field.

Different ID strategies behave differently. Do not write tests requiring every provider to reset IDs to null after rollback when JPA/providers do not guarantee that.

## 27. Testing Spring Batch retry after rollback

Integration tests should exercise a multi-chunk step with a writer or processor that fails in a controlled manner:

1. The reader emits items with stable business keys.
2. The processor creates fresh output or the writer loads entities within the chunk transaction.
3. The writer persists several entities and throws an exception on the first attempt.
4. Verify the chunk transaction rolls back and the database holds no uncommitted changes.
5. Allow retry or restart according to configuration.
6. Verify items are reprocessed with the right semantics.
7. Verify stale IDs/versions do not cause faulty writes.
8. Verify no data is lost or duplicated.

Tests should not assert only `COMPLETED` status at the end. Check business keys, row counts, versions, and side-effect invocation counts.

## 28. Testing that the processor does not mutate input

For DTO or entity inputs, verify the processor builds a fresh output without modifying input:

```java
@Test
void processorCreatesOutputWithoutMutatingInput() throws Exception {
    CustomerInput input = new CustomerInput(
            "C001", "  Nguyen An  ", Status.READY);

    CustomerUpdate output = processor.process(input);

    assertThat(input.name()).isEqualTo("  Nguyen An  ");
    assertThat(output.name()).isEqualTo("Nguyen An");
}
```

For mutable entities, similar tests can verify the processor never calls setters on the input. This reduces the risk of retries encountering objects already mutated by an earlier attempt.

## 29. Common pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Database rolled back, yet object still holds new values | JPA does not revert Java fields on transaction rollback. | Discard old objects and reload inside a new transaction. |
| Non-null ID, yet no row found | ID was assigned before commit; transaction rolled back. | Never use a non-null ID alone as proof of commit; re-query the database. |
| Optimistic locking errors on retry | Object holds stale `@Version` or an in-memory incremented version. | Reload the entity and re-evaluate changes in a new transaction. |
| Old entity still treated as managed | Persistence context rolled back, yet code reuses old references. | Treat entities as detached/untrusted; open a fresh context. |
| Mutating the wrong object after `merge()` | Code keeps mutating the input object instead of the returned instance. | Use the managed instance returned by `merge()`. |
| Retry writes duplicate data | Processor/writer has non-transactional or non-idempotent side effects. | Use idempotency keys, unique constraints, or an outbox. |
| Java relationships diverge from database | Rollback does not revert both sides of an object graph. | Reload the aggregate in a new persistence context. |
| Lazy loading fails after rollback | Entity is detached or context closed/cleared. | Re-fetch required data in a new transaction. |
| `UnexpectedRollbackException` | Exception was caught after transaction was marked rollback-only. | Let exceptions propagate to the boundary and handle in a new transaction. |
| Stale data overwrites newer state on merge | Merging an entire detached object after the database changed. | Reload and selectively apply business updates. |
| Files/APIs changed despite chunk rollback | Side effects did not participate in the database transaction. | Use staging, outbox, idempotency, and reconciliation. |

## 30. Workflow for handling entities after rollback

When a chunk or JPA transaction fails, proceed in order:

1. **Let the transaction finish:** do not continue writing in a rollback-only transaction.
2. **Distinguish database state from Java state:** confirm which changes the rollback undid.
3. **Discard stale references when needed:** never treat entity instances from a failed transaction as current truth.
4. **Start a fresh transaction/persistence context:** use the Spring-managed transaction manager.
5. **Reload by business key or ID:** fetch the latest state from the database.
6. **Check version and business preconditions:** decide whether changes can be reapplied or a conflict occurred.
7. **Rebuild output cleanly:** prefer fresh DTOs/commands rather than mutating old entities.
8. **Retry with bounds:** retry transient faults, never permanent data errors.
9. **Control side effects:** use outbox/idempotency for APIs, messages, and files.
10. **Test restarts:** confirm checkpoints and database state stay in sync without dropped or duplicate items.

## 31. Key takeaways

- JPA entities have four states: new, managed, removed, and detached.
- Rollback undoes the database transaction; it does not revert Java object fields to pre-transaction values.
- Entities in a persistence context that undergoes rollback become detached under the JPA lifecycle; never rely on stale state to continue business logic.
- `flush()` sends SQL without committing; flushed SQL can still be rolled back.
- `clear()` detaches entities without resetting fields, IDs, or versions on objects.
- Generated IDs may survive rollback; sequence/identity strategies can leave gaps.
- `@Version` fields on in-memory objects may differ from the database version after rollback.
- `merge()` returns a new managed instance; the passed-in object remains detached.
- After rollback, start a new transaction and reload entities when current database state is needed.
- Never assume Spring Batch retries always create new objects or reset old ones; design processors and writers for safe re-execution.
- Prefer immutable DTOs and non-mutating processors; have writers load and apply changes in the current transaction.
- Entity graphs and lazy associations on old objects may not match the database after rollback.
- Side effects outside the database transaction do not roll back automatically; use outbox, idempotency, or reconciliation.
- Test database state, Java object state, generated IDs/versions, and chunk retry/restart separately.

Entity state after rollback should be treated as in-memory state separate from database state. Spring Batch may re-read items after a chunk rollback, but JPA does not automatically revert objects modified during the previous attempt. End the failed transaction, discard or distrust old entities, reload data in a fresh persistence context, and apply changes idempotently. This prevents retries and restarts from relying on stale state and keeps batch results consistent with the database.
