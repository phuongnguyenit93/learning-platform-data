# NoRollbackExceptionClasses in Spring Batch

In chunk-oriented processing, Spring Batch normally rolls back the chunk's transaction when an exception escapes from reading, processing, or writing. Rollback restores uncommitted transactional changes to the pre-chunk state, yet not every exception means the transaction has been corrupted. Some exceptions simply indicate that a single item is invalid and can be excluded without undoing other operations in the chunk.

`NoRollbackExceptionClasses` refers to the set of exception classes configured **not to trigger a rollback** in a fault-tolerant step. Spring Batch provides the `.noRollback(...)` method to declare those exception types. This configuration changes how the transaction responds to an exception; it does not by itself decide whether an item is skipped.

## 1. Default Rollback in a Chunk Step

A chunk is normally processed inside a transaction. If an exception occurs and is treated as requiring rollback, the current transaction is undone:

```text
BEGIN CHUNK TRANSACTION
        |
        v
READ -> PROCESS -> WRITE
        |
        v
Exception escapes
        |
        v
ROLLBACK
        |
        v
Chunk may be retried/skipped or step fails
```

Rollback protects consistency when the writer has already modified the database and another part of the chunk fails. Operations participating in the same transaction manager are undone. Previously committed chunks remain intact.

However, some exceptions do not modify transactional data. For example, a processor validates an order and detects a missing required field. If that item is allowed to be skipped, rolling back the entire chunk may be unnecessary because the processor only performed computations and has not written data. In this scenario, the application can configure the validation exception not to trigger a rollback.

## 2. What Is NoRollbackExceptionClasses?

In Spring Batch, the exception classes listed via `.noRollback(...)` form the group of exceptions that do not require rolling back the transaction under the step configuration.

Common API in Spring Batch 5:

```java
.faultTolerant()
.noRollback(InvalidOrderException.class)
```

Multiple types can be declared:

```java
.noRollback(
    InvalidOrderException.class,
    OptionalFieldMissingException.class
)
```

By default, exceptions in chunk processing are handled according to the step's rollback rules. `noRollback` adds exception types classified as not requiring rollback. This setting is typically combined with a skip policy when the application wants to discard an invalid item and continue the chunk without rolling back the transaction solely for that validation exception.

The name `NoRollbackExceptionClasses` describes the class list; in application code, the configuration point is the `.noRollback(...)` method on the fault-tolerant step builder.

## 3. noRollback Does Not Mean Skip

This is the most important distinction:

| Configuration | Responsibility |
| --- | --- |
| `.noRollback(ExceptionType.class)` | Decides whether the exception rolls back the transaction. |
| `.skip(ExceptionType.class)` or `SkipPolicy` | Decides whether the exception may be skipped so the step continues. |
| `.noSkip(ExceptionType.class)` | Marks an exception as non-skippable in skip classification. |
| `.retry(ExceptionType.class)` | Allows retrying the operation when the exception matches the retry policy. |

Example:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noRollback(InvalidOrderException.class)
.skipLimit(50)
```

The first two settings answer two separate questions:

- `skip(...)`: can the item be discarded because of this validation error?
- `noRollback(...)`: when this exception occurs, must the chunk transaction roll back?

If you declare only `.noRollback(...)` without allowing skip, the exception can still cause the step to fail. Not rolling back does not turn an exception into success and does not instruct the framework to skip the item.

Conversely, declaring only `.skip(...)` does not mean the transaction will not roll back. By default, the framework can still roll back to handle the exception through the fault-tolerance flow. Add `noRollback` only when you have confirmed rollback is truly unnecessary and the transaction stays consistent.

## 4. Example Validation Exception That May Not Need Rollback

Suppose a processor validates an order before producing output. If the order lacks a customer ID, the processor throws `InvalidOrderException`. No database write is performed inside the processor:

```java
public class OrderProcessor
        implements ItemProcessor<Order, OrderEntity> {

    @Override
    public OrderEntity process(Order order) {
        if (order.getCustomerId() == null) {
            throw new InvalidOrderException(
                "Missing customer id for order " + order.getId()
            );
        }

        return new OrderEntity(order.getId(), order.getCustomerId());
    }
}
```

The step can allow skipping this exception without rolling back solely for the validation error:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .noRollback(InvalidOrderException.class)
        .skipLimit(50)
        .build();
}
```

With this configuration, the invalid order can be skipped according to the skip policy. Remaining valid orders continue processing. Because the processor writes no side effects and the exception solely represents an item error, the transaction does not need to roll back merely to skip that order.

This example fits when the processor is a pure transformation/validation step. If the processor has already written to the database, called an API, or modified external state before throwing, the "no rollback needed" assumption may no longer hold.

## 5. Impact by Phase: Read, Process, and Write

The impact of `noRollback` depends on where the exception occurs and what operations ran beforehand.

| Phase | Example Exception | Risk When Not Rolling Back |
| --- | --- | --- |
| Read | Reader encounters a line with an invalid format. | Usually no write data for that item, but the reader must be able to continue at the next record. |
| Process | Processor throws a validation error before producing output. | Generally safe if the processor has no side effects and has not modified transactional resources. |
| Write | Writer wrote partially and then threw an exception. | May commit partial data if those operations remain in the transaction and the exception is configured not to roll back. |

Therefore, `noRollback` is much easier to justify for processor validation exceptions where no writes have happened yet. For write exceptions, exercise extreme caution. The writer may have written several items before hitting an error on another item. If the transaction does not roll back, part of the chunk could be committed even though the step is handling an error.

Do not configure one shared exception as no-rollback across all phases if it can be thrown from reader, processor, and writer with different resource states. Separating exception classes by meaning and phase provides clearer transaction control.

## 6. noRollback and Transaction Boundaries

`noRollback` changes how a transaction reacts to an exception, but it does not alter chunk boundaries. Each chunk still has a transaction per commit interval; earlier committed chunks remain independent.

If a no-rollback exception escapes the transaction interceptor, the transaction may commit instead of rolling back while the exception still propagates to the handling flow. In a fault-tolerant step, the framework also applies skip/retry classification to determine the final outcome. Consequently, inspect both the step status and the actual post-transaction data.

One way to visualize it:

```text
Chunk transaction
    |
    +-- Processor throws InvalidOrderException
    |
    +-- noRollback classifier: do not roll back
    |
    +-- SkipPolicy: allow skipping item
    |
    +-- Remaining items are processed
    |
    +-- Chunk completes and commits
```

If the exception is not skipped and escapes outward, the step can still end in failure. Because the transaction is classified as no-rollback, changes already executed inside the transaction risk being committed. This is why `noRollback` must never be treated as a "safe default" setting for exceptions.

## 7. Exception Classes and Inheritance Hierarchy

`.noRollback(...)` accepts exception classes. When designing the hierarchy, determine which specific exceptions truly mean rollback is unnecessary.

Example:

```java
public class OrderException extends RuntimeException {
    public OrderException(String message) {
        super(message);
    }
}

public class InvalidOrderException extends OrderException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class OrderPersistenceException extends OrderException {
    public OrderPersistenceException(String message) {
        super(message);
    }
}
```

If you declare:

```java
.noRollback(OrderException.class)
```

the rule spans subclasses according to the framework's class-classification mechanism. This can cause `OrderPersistenceException` not to roll back either, even though database write errors normally require rollback.

It is better to declare the specific class:

```java
.noRollback(InvalidOrderException.class)
```

Do not use a shared superclass for validation, persistence, integration, and programming errors if they have different transaction requirements. When exceptions are wrapped inside another exception, check the actual exception type fed into classification in your Spring Batch version and write tests covering wrappers/cause chains.

## 8. Combining noRollback with skipLimit

`noRollback` does not set a limit on how many items may be skipped. The skip limit is managed separately:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noRollback(InvalidOrderException.class)
.skipLimit(25)
```

In this example, at most 25 items may be skipped under the step's skip policy. The skip limit applies to the combined skips across read, process, and write, not 25 per phase.

If a 26th item requires skipping, the step can fail for exceeding the limit. `noRollback` does not remove the limit; it only affects the exception's rollback classification.

When the skip limit is exceeded, examine the transaction state at the moment the final exception is thrown. If the exception is marked no-rollback, transactional changes already performed within the transaction may not be undone. Therefore, do not configure an exception representing partial writer failure as both skippable and no-rollback unless a design guarantees data consistency.

## 9. Combining noRollback with Retry

Retry and no-rollback serve different purposes. Retry generally needs to re-attempt a failing operation; rollback may be necessary to release locks, discard partial changes, or return the transaction to a clean state before the next attempt.

Example retry configuration:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

For transient database access errors, default rollback is usually appropriate because the transaction may be in an unreliable state. If you add:

```java
.noRollback(TransientDataAccessException.class)
```

clearly establish why the transaction remains safe to continue or commit after the error. A timeout or deadlock can occur after partial operations have executed; skipping rollback may leave behind partial changes or unintended locks/state.

Do not combine retry and noRollback for the same exception merely to reduce overhead. Verify retry ordering, transaction boundaries, and resource behavior with integration tests before using it in production.

## 10. noRollback Does Not Replace noSkip

`noSkip` and `noRollback` have similar names but control two different classifiers:

```java
.faultTolerant()
.noSkip(AccessDeniedException.class)
.noRollback(InvalidOrderException.class)
```

Meaning:

- `AccessDeniedException` must not be skipped; access-control errors must fail the step according to flow.
- `InvalidOrderException` is classified as not requiring rollback. If you want the step to continue by discarding the item, configure `.skip(InvalidOrderException.class)` or a corresponding policy.

You can configure an exception as both `noSkip` and `noRollback`, though that is a special decision: the exception fails the step without rolling back the transaction. This case can commit modified data even though the job fails, so it requires a clear business justification and tests proving consistency.

## 11. Exceptions from the Writer: When to Avoid noRollback

Suppose a writer processes chunk `[A, B, C]`. The writer inserts A and B into the database, then fails when writing C:

```text
BEGIN
  INSERT A
  INSERT B
  INSERT C -> exception
```

If A, B, and C participate in the same transaction and the exception triggers rollback, both A and B are undone. Spring Batch can handle the exception per retry/skip policies to isolate the failing item.

If the exception is configured as no-rollback, the transaction may commit changes performed before the exception escaped. Then A and B may persist while C was not written, even though the chunk did not complete as intended. This can produce partial writes and make restarts unpredictable.

For write exceptions, consider no-rollback only if the writer guarantees the exception occurs before any transactional mutation, or the writer has a separately verified atomic contract. In most database-writing scenarios, keeping default rollback is the safer choice.

## 12. Processors Should Be Pure Transformations When Using noRollback

A pure processor typically receives an item, validates/transforms it, and returns output without writing data or performing side effects:

```java
public class OrderValidationProcessor
        implements ItemProcessor<Order, OrderEntity> {

    @Override
    public OrderEntity process(Order order) {
        if (order.getCustomerId() == null) {
            throw new InvalidOrderException("Customer id is required");
        }

        return new OrderEntity(order.getId(), order.getCustomerId());
    }
}
```

In this case, if the exception only indicates an invalid item and the item is skipped, the processor made no business changes that need rolling back. This is a clear use case for no-rollback classification.

Conversely, the processor should not:

- Write to a database via another transaction and then throw an exception.
- Send emails or messages before the writer completes.
- Call transaction-creating APIs without idempotency.
- Mutate shared state while relying on rollback to restore it.

If the processor has side effects, noRollback can allow remaining transactional changes to commit while the side effects already occurred independently. It is better to move side effects to the writer/outbox or a separate step with explicit state.

## 13. noRollback and Listeners

`SkipListener` is invoked when an item is actually skipped. `noRollback` does not trigger the listener by itself and does not alter the listener's responsibilities.

Example:

```java
public class InvalidOrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    @Override
    public void onSkipInRead(Throwable t) {
        // Record parse/read error if source identifier is available.
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        // Record business key of skipped item.
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        // Record output item that could not be written.
    }
}
```

If the listener saves a quarantine record in the same database transaction, that record can commit with the chunk when the transaction succeeds. If the listener writes to a system outside the transaction, that side effect is not protected by database rollback. Use idempotency or an outbox when you need durable audit trails without duplicate writes.

Do not use a listener to "fix" a transaction after configuring noRollback. Listeners only observe skip events; transaction behavior is still governed by the transaction manager and rollback classifier.

## 14. Testing noRollback with a Real Database Transaction

A unit test checking only that the builder was called with the desired configuration does not prove the transaction actually commits or rolls back properly. Use integration tests with a real test database and transaction manager.

A test for processor validation can:

1. Supply three items: two valid and one invalid.
2. Have the processor throw `InvalidOrderException` for the invalid item.
3. Configure the step with skip and noRollback for that exception.
4. Have the writer write the two valid outputs.
5. Verify the step completes, process skip count equals one, and two valid records are committed.

Example assertions:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

StepExecution step = execution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(step.getProcessSkipCount()).isEqualTo(1);
assertThat(step.getWriteCount()).isEqualTo(2);
assertThat(orderRepository.count()).isEqualTo(2);
```

Counts and step names in the example must match your actual fixture. Inspect both metadata and database data to confirm the failing item was skipped while valid items committed.

## 15. Testing the Difference Between Rollback and noRollback

To understand transaction impact, you can write two separate tests using the same exception:

| Test | Configuration | What to Observe |
| --- | --- | --- |
| Baseline | Allow skip without declaring noRollback | Verify default rollback behavior and how many times chunks/processors run in the fixture. |
| No rollback | Allow skip and declare noRollback for the exception | Verify the transaction does not roll back solely for this classified exception while valid outputs are still written. |

Do not draw conclusions solely by comparing `commitCount` or `rollbackCount`. Cross-check those counters against actual data, listener invocations, and execution status. The transaction manager, reader buffering, and phase where the exception arises all affect the outcome.

To test writer risk, create a writer that writes one item and then throws an exception. Do this only in an isolated test database and explicitly verify which data commits when the exception is marked noRollback. This test demonstrates why noRollback should not be broadly applied to write errors.

## 16. Testing Exception Hierarchies and Wrappers

If a policy uses a superclass, also test unintended subclasses. If an exception might be wrapped in `ItemStreamException`, `UnexpectedInputException`, or another wrapper, verify which exception type Spring Batch actually classifies.

A test suite should cover:

- The specific validation exception marked no-rollback.
- Subclasses of the configured exception.
- Persistence exceptions not accidentally marked no-rollback via a shared superclass.
- Exception wrappers/cause chains handled as expected.
- Unlisted exceptions still rolling back by default.

Testing the hierarchy prevents a small code change introducing a new exception subclass from inadvertently altering transaction behavior.

## 17. Common Mistakes When Using noRollback

**Assuming noRollback means skip:** noRollback only changes rollback classification. A skip policy is required to discard the item and continue.

**Declaring noRollback without declaring skip:** the exception can still fail the step; the transaction may still not roll back even though the step failed.

**Applying it to every exception:** writer, database, or infrastructure errors can leave partial changes behind if the transaction commits.

**Using an overly broad superclass:** persistence exceptions may inherit from a class marked no-rollback. Choose specific classes and test the hierarchy.

**Using noRollback for transient errors needing retry:** the transaction may not return to a clean state before the next retry attempt. Keep default rollback unless there is a verified reason.

**Ignoring phases:** the same exception class might be thrown in both processor and writer; the transaction risks of the two phases differ.

**Believing non-database data will roll back:** files, APIs, emails, and messages do not automatically join transactions. Use staging, outboxes, or compensation.

**Checking only job status:** a step can be FAILED while the transaction still committed due to no-rollback classification. Always check the actual data.

## 18. Workflow for Selecting NoRollbackExceptionClasses in Production

First, identify what the exception represents and in which phase it arises. Select only exceptions indicating that an individual item is invalid while the current transaction remains consistent and safe to continue. Pure processor validation is the easiest case to justify; writer failures after partial writes are usually unsuitable.

Next, declare the specific exception using `.noRollback(...)`. If items should be discarded, configure `.skip(...)` or a separate `SkipPolicy` with an appropriate `skipLimit`. Do not use `noRollback` as a substitute for retry or noSkip. Check exception hierarchies and wrappers to avoid unintended broad classification.

Finally, run integration tests with a real transaction manager and database. Verify `JobExecution`/`StepExecution` status, skip counts, commit/rollback counts, and final database state. Test processor and writer failures separately to understand partial-write differences. For non-transactional side effects, use idempotency, outboxes, or compensation.

`NoRollbackExceptionClasses` allows Spring Batch to handle certain exceptions without rolling back the chunk transaction. This configuration is useful when an exception simply indicates an invalid item and no changes need undoing, especially in pure processors combined with a skip policy. Choose narrow classes, understand the failing phase, and verify with transaction tests to avoid committing partial data when a step encounters errors.
