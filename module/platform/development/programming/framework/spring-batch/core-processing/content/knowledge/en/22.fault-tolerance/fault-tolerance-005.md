# No rollback exception

In Spring Batch, a chunk-oriented Step typically reads, processes, and writes items inside a transaction. When an exception occurs, the framework must decide whether the current transaction needs to roll back. By default, an exception from `ItemWriter` causes the chunk transaction to roll back because the writer may have already written partial data before the error appeared.

However, there are cases where the writer detects a problem before making any changes. For example, the writer checks business rules and throws `ValidationException` prior to writing to the database. In this case, a rollback may not be necessary. Spring Batch allows declaring exceptions that do not roll back the transaction via `noRollback()` in a fault-tolerant Step configuration.

`noRollback` only controls the transaction's rollback decision. It does not skip the exception on its own, does not retry on its own, and does not turn the Step into a success. Whether execution continues or fails still depends on the skip policy, retry policy, and how the exception is handled.

## 1. Rollback in chunk-oriented processing

In a chunk-oriented Step, Spring Batch reads a group of items, processes them, and calls the writer. The chunk transaction is normally committed after the writer completes successfully.

```text
Begin transaction
       |
       v
  ItemReader
       |
       v
 ItemProcessor
       |
       v
  ItemWriter
       |
       v
Commit transaction
```

If an exception occurs during writing, Spring Batch must consider whether the changes in the transaction are still valid. If the writer has written several items and then fails, committing the partial write can leave inconsistent data. Therefore, by default an exception from `ItemWriter` causes the Step's transaction to roll back.

For example, the writer performs these operations:

1. Insert order A.
2. Insert order B.
3. Insert order C, but encounter a constraint error.

If all three operations participate in one database transaction and the transaction rolls back, inserts A and B are also undone. Afterward, Spring Batch can perform retry or skip according to the Step configuration.

Rollback is not a manual record-deletion operation. It is the behavior of the transaction manager/database to undo uncommitted changes belonging to the current transaction across participating transactional resources.

## 2. What is a no rollback exception?

A no rollback exception is an exception type declared so that it does not trigger a rollback of the chunk transaction when it occurs. Spring Batch provides the `noRollback()` API on fault-tolerant Step configuration.

Example:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .noRollback(ValidationException.class)
            .build();
}
```

In this example, `ValidationException` is marked as an exception that does not roll back the transaction. If this exception occurs in a situation where no operation has invalidated the transaction, the framework can keep the transaction rather than rolling back solely because of that exception.

A valid use case is a writer that validates the entire chunk before performing any writes. If it detects an invalid item, the writer throws `ValidationException` right in the validation phase, before writing any item. If this exception is configured for skip and no-rollback, the Step can skip the item per policy without rolling back writes that never happened.

Do not configure `noRollback()` merely to avoid rollback overhead. First, know precisely when the exception is thrown and what changes the writer has already made.

## 3. Configuring `noRollback()` in Spring Batch 5

In Java configuration, `noRollback()` is called after `faultTolerant()` on the Step builder:

```java
@Bean
Step validateAndWriteOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("validateAndWriteOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .noRollback(ValidationException.class)
            .build();
}
```

`ValidationException.class` is the exception type used for rollback classification. Multiple exception types can be declared with multiple `noRollback()` calls once each type has been evaluated individually.

Do not use an overly broad exception such as `Exception.class` or `RuntimeException.class` as a no-rollback rule for the whole Step. Those exceptions can include database errors, partial write failures, infrastructure failures, or programming bugs where the transaction must roll back.

### Declaring both skip and noRollback

In many scenarios, the goal is to skip an invalid item and simultaneously avoid rolling back the chunk because the writer validated before writing. In that case, declare both the skip policy and the no-rollback rule:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(ValidationException.class)
        .skipLimit(50)
        .noRollback(ValidationException.class)
        .build();
```

The two configurations have different roles:

- `skip(ValidationException.class)` allows the Step to skip the item when this exception occurs, within the skip limit.
- `noRollback(ValidationException.class)` states that this exception does not require rolling back the transaction.

If you only declare `noRollback()` without configuring an appropriate skip or retry policy, the exception can still cause the Step to fail. No-rollback is not an exception-swallowing mechanism.

## 4. No rollback does not mean skip

This is the most important point when using this feature. `noRollback` and `skip` answer two different questions:

- **Skip:** is the item allowed to be bypassed so the Step can continue?
- **No rollback:** does the exception require the current transaction to roll back?

For example:

| Configuration | Item decision | Transaction decision |
|---|---|---|
| `skip()` only | Item may be dropped if policy permits | Follows default rollback classification |
| `noRollback()` only | Does not drop the item; exception may still fail the Step | Configured exception does not require rollback |
| `skip()` and `noRollback()` | Item may be skipped | That exception does not trigger transaction rollback |
| Neither | Exception typically fails the Step unless handled elsewhere | Exception from writer rolls back by default |

For example, the processor throws `ValidationException` and the Step allows skipping. The framework can remove that item from the processing stream and continue with other items. `SkipListener` records the skipped item.

If the writer throws an exception, the transaction rolls back by default. When the exception is declared no-rollback, the framework does not roll back solely because of that exception type. Still, whether the item is skipped or the Step fails remains a separate fault-tolerance decision.

## 5. No rollback does not mean retry

Retry means the framework re-attempts an operation or item when the exception is classified as retryable. No-rollback only changes the transaction rollback decision for the configured exception.

| Mechanism | Question addressed | Example |
|---|---|---|
| Retry | Should we retry after the error? | Temporary deadlock, short-lived timeout |
| Skip | Can we drop the failing item and continue? | A record with invalid business data |
| No rollback | Must this exception roll back the transaction? | Writer rejects an item before writing any data |

For deadlock errors, the transaction normally must roll back to release locks and start a fresh attempt in a new transaction. Do not mark deadlocks as no-rollback just to avoid a rollback. For validation errors occurring before writes, skip combined with no-rollback may be more appropriate.

When the same exception is declared across multiple policies, check the interaction between retry, skip, and rollback in the Spring Batch version you use. Do not assume `noRollback()` automatically enables retry or skip.

## 6. Why do writer exceptions roll back by default?

`ItemWriter.write()` receives a group of items. The writer may execute multiple operations before throwing an exception. By default, the framework cannot know how many items the writer already wrote or what internal state can be restored.

Example:

```java
@Component
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            repository.save(order);

            if (order.amount().signum() < 0) {
                throw new ValidationException("Negative order amount");
            }
        }
    }
}
```

The code above has a design flaw: the writer saves item by item and only detects the invalid item afterward. If `ValidationException` is configured as no-rollback, the saves before the exception may commit even though the failing item caused the writer to throw an exception. The result can be a partially written chunk.

If you want to use no-rollback for validation, validate the entire chunk upfront:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        if (order.amount() == null || order.amount().signum() < 0) {
            throw new ValidationException(
                    "Invalid order: " + order.orderId());
        }
    }

    repository.saveAll(chunk.getItems());
}
```

In this example, validation occurs before calling `saveAll`. If a validation exception is thrown, the writer has not started writing yet. This is the kind of scenario that is easier to evaluate when considering no-rollback.

However, `saveAll()` or a repository implementation may still execute multiple statements; understand the transaction and actual behavior of the persistence provider. Never rely solely on a method name to conclude that no partial write occurred.

## 7. Complete example: validation exception skipped without rollback

Suppose the writer receives a chunk of orders. Before writing, the writer validates chunk-level rules. If an item is invalid, the writer throws `ValidationException`. Business rules allow skipping the invalid item and continuing to process valid data.

An illustrative configuration:

```java
@Bean
Step writeValidatedOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipListener skipListener) {

    return new StepBuilder("writeValidatedOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(ValidationException.class)
            .skipLimit(20)
            .noRollback(ValidationException.class)
            .listener(skipListener)
            .build();
}
```

In this example:

1. The Reader provides input items.
2. The Processor transforms them into `Order`.
3. The Writer validates rules applicable to the chunk.
4. If the Writer throws `ValidationException`, the exception belongs to the skippable group.
5. The no-rollback rule indicates this exception does not require rolling back the transaction.
6. `SkipListener` records the skipped item via the corresponding callback during fault-tolerance handling.

Details of how Spring Batch isolates the failing item in the writer depend on the fault-tolerance mechanism and reader/writer. This example only illustrates declaring both policies; ensure the writer executes no side effects before throwing the validation exception and test actual behavior with your application's framework version.

If the writer cannot pinpoint the failing item or may write part of the chunk, do not use no-rollback for that exception. Keeping the default rollback is safer.

## 8. No-rollback and exceptions from Reader, Processor, and Writer

Chunk components behave differently when exceptions occur. Understand where the error originates before selecting a rollback policy.

### Exceptions in ItemReader

The Reader has a forward-only reading contract. When the Step is configured with skip, some read exceptions can be handled without rolling back the chunk transaction. For readers backed by transactional sources such as a JMS queue, reading a message can participate in the transaction; on rollback, the message may be returned to the queue. Spring Batch has the `readerIsTransactionalQueue()` option for cases where the reader uses a transactional queue, so the framework does not buffer items in the usual way.

Do not assume every reader exception has identical rollback behavior. Check the reader type, skip policy, and whether the data source is transactional.

### Exceptions in ItemProcessor

The Processor transforms individual items. Exceptions in the processor can be handled by retry/skip policies. If the processor only performs calculations and has no side effects, reprocessing is usually easier to control. If the processor calls a write API or mutates an external system, a database rollback cannot undo those side effects.

### Exceptions in ItemWriter

The Writer writes a group of items. By default, an exception from the writer rolls back the transaction because the framework cannot tell whether the writer already performed partial writes. This is where `noRollback()` is commonly considered if the writer can throw an exception before executing any write operation.

| Component | What to evaluate |
|---|---|
| Reader | Is the source transactional? Are items buffered? Is skip configured? |
| Processor | Are there non-transactional side effects? Can the item be safely retried/skipped? |
| Writer | Could partial writes occur before the exception? If so, is rollback required? |

## 9. A no-rollback exception does not make the Step succeed automatically

A common misconception is that declaring `.noRollback(MyException.class)` makes the Step ignore the error. That is false.

No-rollback only specifies that the exception does not roll back the transaction. The exception still passes through the Step's error-handling mechanism. If the exception is not skipped, not successfully retried, and not handled elsewhere, the Step can still transition to `FAILED`.

Example:

```java
.faultTolerant()
.noRollback(ValidationException.class)
```

This snippet does not say `ValidationException` is skippable. To let the Step bypass the exception and continue, add a skip policy:

```java
.faultTolerant()
.skip(ValidationException.class)
.skipLimit(20)
.noRollback(ValidationException.class)
```

Conversely, if the exception represents a serious error that must stop the Job, do not configure skip merely to avoid rollback. Separately define the desired business outcome and the transaction behavior.

## 10. Risks of misusing noRollback

No-rollback can cause a transaction to commit changes that occurred before the exception was thrown. Therefore, an overly broad configuration or choosing the wrong exception can be more dangerous than the default rollback.

Key risks:

- **Partial write:** the writer writes several items and then throws an exception; no-rollback can leave partial data behind.
- **Inconsistent data:** related operations are no longer committed/rolled back together as designed.
- **Step fails while changes committed:** the exception can still fail the Step while the transaction did not roll back.
- **Repeated side effects:** when the Job restarts, non-transactional operations may run again.
- **Misclassified infrastructure errors:** using a broad superclass can stop deadlocks, timeouts, or write failures from rolling back.

A practical rule: only configure no-rollback for an exception with clear semantics that is thrown at a point guaranteed to have no changes needing rollback in the current transaction.

## 11. NoRollback in Spring Batch vs `@Transactional(noRollbackFor=...)`

Spring Framework has the `noRollbackFor` attribute on `@Transactional`. Spring Batch has the `noRollback()` method in fault-tolerant Step configuration. The two mechanisms are conceptually related but reside at different configuration layers.

| Mechanism | Scope |
|---|---|
| `.noRollback(ValidationException.class)` | Rollback classification of a chunk-oriented Step in Spring Batch |
| `@Transactional(noRollbackFor = ValidationException.class)` | Rollback rule for a transaction managed by Spring's transaction interceptor on the annotated method |

If a service invoked inside a chunk has `@Transactional`, understand the propagation and transaction manager in use. The service transaction may join the current transaction or start its own depending on propagation. Step-level `noRollback` should not be treated as a substitute for the rollback rule of an independent inner service transaction.

Avoid configuring conflicting rules in two places without integration tests. An exception may cross multiple transaction boundaries; determine which transaction is making the commit or rollback decision.

## 12. No rollback and transactional readers

A typical reader in chunk processing is treated as forward-only. Spring Batch buffers read items so that when a chunk rolls back, the framework can reuse items without asking the reader to rewind.

For a reader reading from a transactional resource such as a JMS queue, fetching a message can participate in the transaction. When the transaction rolls back, the message is returned to the queue. In that case, you can configure:

```java
@Bean
Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<MessageRecord> reader,
        ItemWriter<MessageRecord> writer) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<MessageRecord, MessageRecord>chunk(20, transactionManager)
            .reader(reader)
            .writer(writer)
            .readerIsTransactionalQueue()
            .build();
}
```

`readerIsTransactionalQueue()` adjusts how the Step buffers input for a transactional queue. This is a setting related to the reader/transactional resource, not a no-rollback exception. Do not use the two concepts interchangeably.

## 13. How to choose exceptions for noRollback

Before adding an exception type to `noRollback()`, answer these questions:

1. Is the exception thrown from the reader, processor, or writer?
2. By the time the exception is thrown, has the transaction made any changes?
3. Without rollback, what changes could be committed?
4. Should the exception be skipped, retried, or fail the Step?
5. If the Step restarts, is there a risk of repeated side effects or duplicate data?
6. Does the exception have an overly broad superclass covering other errors?
7. Can success, skip, and failure scenarios all be tested?

Exception categories that typically require separate consideration:

| Exception category | Decision to consider |
|---|---|
| Validation exception before writing | Can be skipped and no-rollback if guaranteed no changes occurred |
| Deadlock or lock acquisition failure | Usually needs rollback and retry in a new transaction |
| Database connection failure while writing | Usually roll back; avoid generic no-rollback |
| Constraint violation after some writes | Usually needs rollback to avoid partial writes |
| Programming error like `NullPointerException` | Should not be arbitrarily no-rollback or skipped; usually needs Step failure |
| External API error | Evaluate side effects, retry/idempotency; DB rollback does not undo API calls |

This is guidance based on error characteristics, not an absolute rule for every database or writer. Rely on actual transactions and the writer's contract.

## 14. Testing rollback behavior

Because no-rollback can allow data changes to be committed when an exception occurs, integration tests with a real transaction manager and database are required.

Scenarios to test:

- Writer throws exception before writing: verify the no-rollback rule applies as intended.
- Writer writes partially and then throws exception: verify the configuration does not leave partial data unexpectedly.
- Skipped exception: verify the item is bypassed and remaining items are processed properly.
- Non-skipped exception: verify the Step gets the proper failed status even if the transaction did not roll back per rule.
- Retried exception: verify transactions and writes are safe across attempts.
- Step restart after error: verify no duplicate records or invalid business state.
- Listener/audit recording skips: verify audit records have proper transaction boundaries.

Do not merely mock `PlatformTransactionManager` and conclude rollback behavior is correct. Run integration tests to verify database state after commit/rollback.

## 15. Common mistakes

**Confusing noRollback with skip:** noRollback does not drop items by itself. To let the Step continue after an exception, configure skip or handle the exception appropriately.

**Confusing noRollback with retry:** noRollback does not re-attempt the operation. Retry is a separate policy and typically requires a new transaction when the previous attempt rolled back.

**Using noRollback for all exceptions:** can commit partial writes or inconsistent changes. Use only for specific, well-understood exceptions.

**Configuring noRollback for writer errors after partial writes:** can leave incomplete data behind. The writer must validate before writing or keep the default rollback.

**Assuming the Step is guaranteed COMPLETED:** exceptions can still fail the Step even if the transaction does not roll back.

**Skipping transaction tests:** reading logs alone is not enough to know which data was committed. Check database state after each scenario.

**Confusing `readerIsTransactionalQueue()` with noRollback:** one option controls buffering for transactional readers; the other classifies exceptions for rollback.

**Duplicate or conflicting rules with `@Transactional(noRollbackFor=...)`:** identify which transaction is managed at each layer and the actual propagation.

## Conclusion

`noRollback()` in a fault-tolerant chunk Step declares exceptions that do not require rolling back the transaction. It is useful when an exception such as validation is thrown before the writer makes any changes, and business rules allow handling the item under a skip policy. No-rollback does not skip, retry, or make the Step succeed on its own; those decisions belong to separate policies. Because writer exceptions roll back the transaction by default to protect chunk atomicity, only disable rollback for specific exception types where the application is certain no partial writes need undoing. Test transactions against a real database, distinguish this from `@Transactional(noRollbackFor=...)` and transactional readers, and ensure restarts do not create duplicate data or inconsistent business state.
