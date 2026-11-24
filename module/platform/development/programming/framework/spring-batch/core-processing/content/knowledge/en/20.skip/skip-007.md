# Skipping items and chunk rollback in Spring Batch

In a Spring Batch Job, not every item can be processed successfully. A file line may be malformed, a record may violate a business rule, or the writer may encounter an error when persisting data. For some errors, stopping the entire Step is necessary. For others, business rules allow skipping the invalid item and continuing to process the rest.

Spring Batch provides **skip** to bypass failing items according to a declared policy. In a chunk-oriented Step, skip must be understood alongside **transaction rollback**: an error in the writer can cause the current chunk transaction to roll back before the framework isolates the failing item and continues with valid items. Previously committed chunks are preserved.

This lesson explains how skip works in the reader, processor, and writer; skip limits; the relationship between skip and rollback; using SkipListener; interactions with retry; and how to test to ensure valid data is neither lost, duplicated, nor partially committed.

## 1. What is skip?

Skip is the decision to bypass an item that raises an exception which business rules allow excluding from the current run. The Step continues with other items instead of failing immediately.

For example, an import file has 1,000 lines, one of which is malformed. If policy allows rejecting up to 10 lines, the Job can discard the bad line, record the reason, and continue processing valid lines.

Skip does not mean ignoring every exception. The application must define which error types are skippable, the maximum count, and how skipped item details are stored.

Situations generally suitable for skip:

- A malformed file line where the remaining lines are independent and processable.
- An item violating a data rule that can be routed to a reject file or error table.
- A record causing an isolated write error while other records in the chunk remain valid.
- Business rules allow completing the batch with a controlled number of rejected items.

Situations where you generally should not skip:

- The database or target system is broadly unavailable.
- Misconfiguration, missing permissions, or missing schema.
- Connection loss making it impossible to verify whether data was written.
- An error rendering subsequent items unreliable.
- An integrity violation where continuing could produce corrupted data.

Skip is an intentional business decision. If skipping an item loses critical data, the Step should fail for operators to investigate.

## 2. Chunks and transactions before considering skip

A chunk-oriented Step groups items by commit interval. The framework reads items, invokes the processor if present, and then invokes the writer for the output group. Chunk operations typically run inside a transaction controlled by the Step's transaction manager.

Example:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

With a commit interval of 100, the framework processes up to 100 input items in a chunk before completing that transaction. The final chunk may be smaller when the reader reaches the end.

~~~mermaid
flowchart TD
    A["Start chunk transaction"] --> B["Reader supplies item"]
    B --> C["Processor processes item"]
    C --> D["Writer writes outputs"]
    D --> E{"Chunk succeeded?"}
    E -- "Yes" --> F["Commit"]
    E -- "No" --> G["Rollback per policy"]
    G --> H["Retry, skip, or fail"]
    F --> I["Next chunk"]
~~~

If the chunk succeeds, the transaction commits and data is durably stored. If an error rolls back the transaction, changes participating in the current chunk's transaction are undone. Earlier committed chunks are not rolled back simply because a later chunk fails.

Skip operates within this mechanism. A skipped item may cause the framework to roll back or re-analyze the chunk depending on the stage where the error occurred and the rollback policy. Do not treat skip simply as removing an item from a list with guaranteed no rollback.

## 3. Distinguishing skip, filter, retry, and rollback

These concepts are related but do not replace one another.

| Concept | Meaning | Example |
|---|---|---|
| Filter | Processor returns null to exclude an item under normal business rules | Cancelled order does not need export |
| Skip | Discard item due to an exception permitted by policy | Malformed CSV line |
| Retry | Re-attempt operation when an exception is potentially transient | Database deadlock |
| Rollback | Undo changes within the current transaction | Writer fails mid-chunk |
| Restart | Create a new JobExecution for a failed or stopped JobInstance | Restarting Job after fixing infrastructure issue |

Example processor returning null:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equals(input.status())) {
            return null;
        }

        return mapToOrder(input);
    };
}
~~~

Filtered items do not raise an exception and are not counted as skips. Spring Batch increments filterCount instead of processSkipCount.

Conversely, if the processor throws ValidationException and the exception is configured for skip, that item is counted as a process skip.

### When to use each mechanism?

- Use filter when the item is valid but should not appear in the output.
- Use skip when a specific exception is defined as skippable.
- Use retry when an error may recover on its own if attempted again.
- Use rollback to ensure transactions do not leave partial changes behind.
- Use restart when a JobExecution ended as failed or stopped and needs to resume from its checkpoint.

## 4. Basic skip configuration

In Spring Batch 5, you can configure skip on a Step using the fault-tolerant builder:

~~~java
@Bean
Step importFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importFileStep", jobRepository)
        .<CustomerInput, Customer>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
~~~

In this example:

- `faultTolerant()` enables skip/retry configuration for the chunk Step.
- `skip(FlatFileParseException.class)` allows bypassing file parse errors of this type.
- `skipLimit(10)` limits the total number of skipped items in the Step.
- Exceptions not declared as skippable fail the Step unless handled by another policy.

If the number of skipped items exceeds the limit, Spring Batch throws SkipLimitExceededException and the Step fails.

### How is skip limit calculated?

The skip limit applies jointly across read, process, and write errors, not as a separate limit per stage.

Suppose `skipLimit(10)` is configured:

- 4 read errors are skipped.
- 3 process errors are skipped.
- 3 write errors are skipped.

Total of 10 items skipped, still within the limit.

If one more skippable item fails, the total becomes 11 and exceeds the limit; the Step fails.

| Stage | Items skipped |
|---|---:|
| Read | 4 |
| Process | 3 |
| Write | 3 |
| Total | 10 |
| Limit | 10 |

The limit is the Step total. Do not configure `skipLimit(10)` three times expecting to skip 30 items.

### Do not configure an overly broad skip limit

A large limit can let the Job complete even when the error rate is very high. Choose the limit based on data quality and business requirements. You can use absolute counts, error rates, or a separate validation Step to control the batch.

## 5. Skipping in the read stage: read skip

Read skip occurs when ItemReader throws an exception and that exception is allowed to be skipped.

Example CSV file with a malformed line:

~~~text
customer_id,full_name,email
C001,An,an@example.test
C002,Binh
C003,Chi,chi@example.test
~~~

If line C002 is missing a column and FlatFileItemReader throws FlatFileParseException, the Step can skip that line if policy permits. Valid lines after it continue to be read.

Configuration example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

With FlatFileParseException, error details are usually accessible via the input line and line number. This is useful for writing reject records or pointing out which line needs fixing.

### Read skip has no input item

In a read skip callback, the reader has not returned a valid item object yet. Thus SkipListener receives Throwable without an item parameter:

~~~java
@Override
public void onSkipInRead(Throwable throwable) {
    if (throwable instanceof FlatFileParseException ex) {
        log.warn(
            "Skipping line {}: {}",
            ex.getLineNumber(),
            ex.getInput()
        );
    }
}
~~~

Do not treat EOF as a read skip. ItemReader returning null per contract means the source ended normally. Read skip only happens when the reader throws an exception allowed to be bypassed by policy.

### Only skip item-level recoverable read errors

A format error on a single line in a file can be a localized error. However, a missing file, lost read permissions, or storage device failure can affect the entire source. Do not lump all IOExceptions into skip if doing so could cause the Job to ignore a serious infrastructure outage.

## 6. Skipping in the process stage: process skip

Process skip occurs when ItemProcessor throws an exception and the exception is allowed to be skipped.

Example:

~~~java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.email() == null || input.email().isBlank()) {
            throw new InvalidCustomerException(
                "Email is required"
            );
        }

        return new Customer(
            input.customerId(),
            input.fullName(),
            input.email()
        );
    };
}
~~~

Step configuration:

~~~java
.faultTolerant()
.skip(InvalidCustomerException.class)
.skipLimit(50)
~~~

If an item has a missing email, the processor throws InvalidCustomerException. Spring Batch can skip that item and continue processing other items.

### Do not turn filters into exceptions

If an item is excluded under normal rules, the processor should return null. Do not throw an exception just to increment skip counts.

For example:

- Order is cancelled and does not need export: return null.
- Customer is missing a required email: throw InvalidCustomerException and skip if business rules permit.
- Customer verification service temporarily times out: can retry.
- Data violates a non-skippable rule: let the Step fail.

Clear distinction ensures filterCount, processSkipCount, and retry metrics accurately reflect behavior.

## 7. Skipping in the write stage: write skip

Write skip occurs when ItemWriter throws an exception and the exception is allowed to be skipped.

This is the case where understanding rollback matters most because the writer usually receives the whole chunk rather than a single item.

Example writer persisting a batch to a database:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO customer_result(customer_id, full_name, email)
            VALUES (:customerId, :fullName, :email)
            """)
        .beanMapped()
        .build();
}
~~~

If one record violates a unique constraint, the batch write can throw an exception. When the exception rolls back the transaction, changes in the current chunk participating in the transaction are undone.

To identify the failing item, Spring Batch's fault-tolerant mechanism can roll back the chunk and then re-execute writes in a way that isolates the failing item. Valid items are written again; the failing item is skipped if policy permits.

~~~mermaid
flowchart TD
    A["Writer receives chunk A, B, C, D"] --> B["Write batch"]
    B --> C{"Error on an item?"}
    C -- "No" --> D["Commit chunk"]
    C -- "Yes" --> E["Roll back chunk transaction"]
    E --> F["Framework isolates failing item"]
    F --> G["Rewrite valid items"]
    G --> H["Skip failing item if policy allows"]
    H --> I["Commit valid results"]
~~~

The diagram is a conceptual model. Exact scanning behavior and writer invocation counts depend on fault-tolerant configuration, rollback classifier, and writer implementation.

### Why can the writer be invoked multiple times?

The writer receives a Chunk containing multiple items. When an item throws an exception, the framework needs to know which item failed. During error isolation, the writer may be invoked again with subsets of items or individual items.

Therefore:

- One write() call does not necessarily correspond to one commit.
- The writer can receive the same item multiple times during retry/scan.
- Side effects outside the transaction can be executed repeatedly.
- The writer needs to be idempotent or perform only transaction-bound operations.

Do not design a writer assuming each item is delivered to the writer exactly once.

## 8. What does chunk rollback mean?

Rollback undoes changes made within the current transaction. In a chunk Step, this usually covers JDBC/JPA statements participating in the Step-managed transaction.

Suppose a chunk has 4 items A, B, C, D:

1. Writer starts writing the items.
2. A and B are inserted successfully inside the transaction.
3. C causes a constraint error.
4. Writer throws an exception.
5. The chunk transaction rolls back.
6. The inserts for A and B inside that transaction are also undone.
7. The framework handles the error per retry/skip policy.
8. If C is skipped and remaining items write successfully, the corresponding transaction commits.

Rollback does not mean all Job data is erased. Previously committed chunks remain intact.

Example:

~~~text
Chunk 1: A, B, C -> COMMIT
Chunk 2: D, E, F -> writer error -> ROLLBACK
Chunk 3: not yet executed

Result:
- A, B, C remain persisted.
- Changes for D, E, F in chunk 2's transaction are undone.
- Step handles chunk 2 according to policy.
~~~

### Transactions only roll back transactional resources

If a writer writes via JdbcTemplate using the same DataSource and transaction manager, database changes can roll back with the chunk.

If a writer sends emails, calls HTTP APIs, writes files with the Files API, or publishes messages to a non-transactional broker, those side effects do not vanish when the database rolls back.

Thus, rollback is not a system-wide undo mechanism. It only protects resources inside the transaction boundary.

## 9. Relationship between skip and rollback by stage

Transaction behavior depends on exception location, rollback classifier, and resources. Do not assume all skips roll back in the same manner.

| Stage | Exception | Behavior to understand |
|---|---|---|
| Reader | Item read error | Reader returns no item; policy may skip read error and continue |
| Processor | Item process error | Item may be skipped; transaction behavior depends on rollback policy and configuration |
| Writer | Chunk write error | By default writer errors usually roll back the chunk transaction; framework can isolate failing item when skip is configured |
| Listener | Callback error | Can fail the Step; not an automatic item skip |

Key points:

- Skip decides whether the failing item is bypassed.
- Rollback classifier decides whether the exception rolls back the current transaction.
- Retry policy decides whether the exception is retried.
- Skip policy decides whether the exception is allowed to be bypassed.

Policies can interact. Test real exceptions at the exact stage, using the exact transaction manager and writer used by the application.

### Why distinguish them?

If an exception does not roll back the transaction after the writer already performed partial changes, continuing can leave inconsistent data. Conversely, overly broad rollbacks can discard work done in the chunk even when an exception only pertains to one item.

Do not alter the rollback policy just for speed. Understand transactional resources, side effects, and how the framework recovers the chunk.

## 10. Using noRollback only when truly necessary

FaultTolerantStepBuilder provides `noRollback(...)` to declare exceptions that do not trigger transaction rollback.

Example:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidRecordException.class)
    .skipLimit(20)
    .noRollback(InvalidRecordException.class)
    .build();
~~~

This configuration illustrates classifying InvalidRecordException as skippable and not requiring rollback under Step policy.

However, `noRollback` does not mean the exception is automatically skipped. The skip policy must still allow that exception. If the exception is not skippable, the Step can still fail.

### Exercise caution when using noRollback

Do not use noRollback for writer errors that may have already written partial data without understanding the transaction. If the transaction does not roll back, changes made before the exception may remain in the transaction and be committed alongside subsequent operations.

Only use noRollback when:

- The exception does not corrupt transaction state.
- Operations executed prior to the exception remain valid.
- The behavior of involved resources is well understood.
- Tests prove the final result is consistent.

In many cases, letting a writer exception roll back the chunk and having the framework isolate the failing item makes integrity easier to guarantee.

## 11. Skip limit and SkipLimitExceededException

Skip limit is a guardrail preventing the Step from continuing when corrupt data exceeds the allowed threshold.

Example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(25)
~~~

Two exception types are skippable, but the total number of skipped items must not exceed 25.

If a 26th failing item needs skipping, the Step fails with SkipLimitExceededException. This prevents the Job from silently completing when the data source has excessive errors.

### Skip limit of 0

If skip is not configured or the limit is set to 0, an exception not allowed to be skipped by policy fails the Step. If business rules tolerate zero bad data, this is the appropriate behavior.

### Data-rate-based thresholds

An absolute skip limit may not fit every batch size. For instance, allowing 20 errors in a 100-item batch equals 20%, whereas in a 1,000,000-item batch it is a tiny rate.

You can combine:

- Absolute skip limit to cap the maximum count.
- A validation Step to compute the error rate.
- A custom ExitStatus if the error rate exceeds the business threshold.
- A reject report so operations can decide whether to publish.

The Step's skip limit remains an item count. If a percentage is needed, compute and verify it separately.

## 12. Skipping multiple exception types and excluding exceptions

You can allow multiple exceptions:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skip(InvalidOrderAmountException.class)
.skipLimit(50)
~~~

You can exclude a specific exception using `noSkip(...)`:

~~~java
.faultTolerant()
.skip(Exception.class)
.noSkip(FileNotFoundException.class)
.skipLimit(50)
~~~

The second example is very broad and should only be used with a clear justification. Allowing all Exceptions to be skipped can cause the Job to bypass programming bugs, configuration errors, and infrastructure failures.

Prefer declaring specific exceptions. If a superclass is skipped while a specific subclass is disallowed, test exception classification and precedence in the Spring Batch version you are using.

### Do not classify by message

Avoid writing skip logic based on message text like "temporary" or "invalid" when dedicated exception types can be used. Messages can change by driver, locale, or library version.

Create business exceptions with stable semantics at application boundaries.

## 13. Using a custom SkipPolicy

When skip rules are complex, you can implement SkipPolicy instead of declaring a simple exception list.

Interface:

~~~java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
        throws SkipLimitExceededException;
}
~~~

Example policy allowing up to 10 skips for parse errors, but never skipping file-not-found errors:

~~~java
public class ImportSkipPolicy implements SkipPolicy {

    private final long limit;

    public ImportSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof FileNotFoundException) {
            return false;
        }

        if (throwable instanceof FlatFileParseException
                || throwable instanceof InvalidCustomerException) {
            if (skipCount < limit) {
                return true;
            }

            throw new SkipLimitExceededException(
                "Skip limit exceeded",
                skipCount,
                throwable
            );
        }

        return false;
    }
}
~~~

Registering the policy:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<CustomerInput, Customer>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skipPolicy(new ImportSkipPolicy(10))
    .build();
~~~

A custom policy is useful when skip decisions depend on exception type, metadata, or error counts. The policy should be pure and deterministic; avoid calling APIs or performing side effects in `shouldSkip` because it may be invoked during error classification.

When using a custom SkipPolicy, test the limit and exception types independently. Do not simultaneously configure skip limits in a way that causes ambiguity about which policy decides.

## 14. SkipListener records discarded items

SkipListener provides callbacks to record items actually skipped:

~~~java
public interface SkipListener<T, S> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInWrite(S item, Throwable t);

    void onSkipInProcess(T item, Throwable t);
}
~~~

Where:

- `onSkipInRead` receives the exception because the reader could not construct an item.
- `onSkipInProcess` receives the input item and exception from the processor.
- `onSkipInWrite` receives the output item and exception from the writer.

Example:

~~~java
@Bean
SkipListener<CustomerInput, Customer> customerSkipListener(
        RejectedCustomerService rejectedCustomerService) {

    return new SkipListener<>() {

        @Override
        public void onSkipInRead(Throwable throwable) {
            if (throwable instanceof FlatFileParseException ex) {
                rejectedCustomerService.recordReadError(
                    ex.getLineNumber(),
                    ex.getInput(),
                    ex.getMessage()
                );
            }
        }

        @Override
        public void onSkipInProcess(
                CustomerInput item,
                Throwable throwable) {
            rejectedCustomerService.recordProcessError(
                item.customerId(),
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInWrite(
                Customer item,
                Throwable throwable) {
            rejectedCustomerService.recordWriteError(
                item.customerId(),
                throwable.getMessage()
            );
        }
    };
}
~~~

Attaching the listener to the Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<CustomerInput, Customer>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skip(InvalidCustomerException.class)
    .skipLimit(20)
    .listener(customerSkipListener)
    .build();
~~~

### SkipListener vs. ItemProcessListener and ItemWriteListener

ItemProcessListener.onProcessError is invoked when the processor throws an exception; the item might be retried and eventually succeed. SkipListener.onSkipInProcess reflects the decision that the item was skipped.

ItemWriteListener.onWriteError observes an error on a writer call; it does not imply every item in the chunk is skipped. SkipListener.onSkipInWrite is invoked for the item actually discarded after the framework isolates the failing item.

Therefore, use SkipListener for final reject records. Use other listeners to observe every attempt or invocation.

### Timing of SkipListener invocation

Spring Batch calls SkipListener near chunk commit time, after determining which items were skipped. This organization reduces the risk of writing duplicate reject records when a chunk rolls back and is reprocessed.

If SkipListener writes reject records using the same transaction manager and database, reject records can commit together with the valid chunk. If the listener calls external APIs or writes external files, those side effects do not automatically roll back. Design appropriate idempotency and listener error handling.

## 15. Writer failures and failing-item isolation mechanism

This is the scenario where newcomers most frequently misunderstand skip and rollback.

Suppose the writer receives a chunk containing A, B, C, D. Record C violates a unique constraint:

~~~text
write([A, B, C, D])
    -> database reports error caused by C
    -> transaction rollback
~~~

If the exception is skippable, the framework must pinpoint the failing item. For writers that can be safely re-invoked, Spring Batch can perform a scan to isolate the failing item:

~~~text
Attempt writing item subsets / individual items
A -> succeeds
B -> succeeds
C -> fails
D -> succeeds

C is skipped
A, B, D are rewritten in the valid chunk
Transaction finally commits if all required operations succeed
~~~

This is a conceptual description of failing-item isolation. The implementation may call the writer multiple times and split chunks according to the framework's specific strategy.

### Why roll back before scanning?

If the first write already inserted A and B and then failed on C, transaction rollback undoes the partial inserts of A and B. Then the framework can re-execute the valid items and skip C.

Without rollback, scanning could write A and B a second time, causing duplicates or inconsistent data.

### Principles writers must follow

- Use transaction-bound resources when writing to a database.
- Do not manually commit connections inside the writer.
- Do not send emails or API requests inside each write without idempotency.
- Do not maintain mutable state assuming each item appears only once.
- Be safe to re-invoke with the same item or different subsets of items.
- If a writer aggregates multiple delegates, understand each delegate's side effects.

### When a writer cannot scan safely

Some writers can only write in batches and cannot pinpoint a failing item by retrying item-by-item. Some writers have irreversible side effects. In such cases, design the writer or error handling differently, such as pre-validating before writing, using smaller chunks, recording rejects separately, or failing the Step for investigation.

Do not enable write skip with a writer that has non-idempotent side effects without testing how the framework re-invokes the writer.

## 16. Reader buffering and rollback

When a chunk rolls back, the framework may need to re-read items already supplied by the reader for that chunk. With standard readers, Spring Batch usually buffers items in the chunk so they can be replayed without consuming the source again.

This matters for sources that cannot easily reread, such as cursors or file readers.

With a transactional queue, the situation differs: messages may be returned to the queue when the transaction rolls back. In that case, extra buffering in the framework may be inappropriate. You can configure the Step with `readerIsTransactionalQueue()` to indicate that the reader pulls items from a transactional queue and the framework should not use standard buffering for those items.

Configuration example:

~~~java
return new StepBuilder("queueImportStep", jobRepository)
    .<Message, ProcessedMessage>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(messageProcessor)
    .writer(messageWriter)
    .readerIsTransactionalQueue()
    .faultTolerant()
    .skip(InvalidMessageException.class)
    .skipLimit(10)
    .build();
~~~

The API and queue integration depend on the transaction manager, broker, and Spring Batch version. Verify that messages are acknowledged or rolled back at the proper time.

### Do not acknowledge messages too early

If a reader acknowledges a message before the chunk commits, the database may roll back while the message is already gone from the queue. On restart, that item is no longer available for reprocessing.

With queues, coordinate transactions or acknowledgment modes so messages are acknowledged only once the corresponding work reaches a safe state.

## 17. Combining retry and skip

An exception can be both retryable and skippable if business rules want to retry first and discard the item once retries are exhausted.

Example:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientRemoteServiceException.class)
    .retryLimit(3)
    .skip(TransientRemoteServiceException.class)
    .skipLimit(20)
    .build();
~~~

Intended semantics:

1. Upon encountering a transient service error, retry up to the limit.
2. If an attempt succeeds, the item continues processing.
3. If retries exhaust and the exception persists, the skip policy can drop the item if the skip limit still allows.
4. If not skippable or the skip limit is exceeded, the Step fails.

Test the exact order and attempt counts of the Spring Batch/Spring Retry version in use. Retry limit and skip limit are two separate counters.

### When should you not combine them?

If the error is a widespread database disconnection, skipping items after a few retries can let the Job finish with massive missing data. For broad infrastructure outages, failing the Step is usually better than skipping item by item.

Only combine retry and skip when the ultimate failure can genuinely be treated as an item-specific error and business rules permit discarding it.

## 18. Skip and rollback for transactions outside the database

The Step's transaction manager only manages resources participating in that transaction.

Suppose a writer does:

1. Insert data into the database.
2. Send a message to a broker.
3. Then hit an error on another item.
4. The database transaction rolls back.

The database can roll back the insert, yet the sent message may remain in the broker. If the framework retries or scans the writer, the message could be sent again.

Safe design approaches:

- Write database state and an outbox event in the same transaction.
- Publish the outbox after the chunk commits.
- Use stable message IDs and consumer deduplication.
- Use idempotency keys for APIs.
- Write file outputs to a temporary file and publish in a separate Step.
- Write reject records to the database in the same transaction when appropriate.

Do not treat a database rollback as a system-wide rollback.

## 19. Restart after skip or rollback

Skip happens within a running JobExecution. Restart happens after a JobExecution fails or stops.

Suppose:

~~~text
Chunk 1: 100 items -> commit
Chunk 2: some failing items -> skipped within limit -> commit
Chunk 3: writer hits non-skippable error -> rollback -> Step FAILED
~~~

When restarting the same JobInstance:

- Committed Chunk 1 is retained.
- Committed Chunk 2 along with its skip outcomes is retained.
- Chunk 3 is reprocessed according to checkpoint and reader state.
- The reader must support restart or have a position-recovery mechanism.
- The writer needs to be idempotent to prevent duplicate data if external side effects exist.

If an item was skipped and its chunk committed, a normal restart should not reintroduce that item into the same Step's pipeline. Reprocessing rejected items requires a separate workflow reading reject data or a new JobInstance per business policy.

### Reject data needs identifiers

When recording a skipped item, store:

- Batch ID.
- Source identifier or file name.
- Line number if available.
- Item business key if already read.
- Exception type.
- Sanitized error message.
- Timestamp and StepExecution ID.

This information allows reprocessing reject records without rescanning the entire source or guessing which items were dropped.

## 20. Tracking skips and rollbacks via StepExecution

Spring Batch stores counters in StepExecution:

| Counter | Meaning |
|---|---|
| readCount | Number of items successfully read |
| writeCount | Number of items successfully written by writer |
| filterCount | Number of items filtered by processor returning null |
| readSkipCount | Number of read errors skipped |
| processSkipCount | Number of process errors skipped |
| writeSkipCount | Number of write errors skipped |
| commitCount | Number of commits |
| rollbackCount | Number of rollbacks |

Total skip count can be accessed via `stepExecution.getSkipCount()`. When investigating, inspect each stage separately to locate where errors originate.

Example:

~~~text
readCount        = 1000
writeCount       = 970
filterCount      = 10
readSkipCount    = 5
processSkipCount = 10
writeSkipCount   = 5
~~~

These numbers show 20 skips and 10 filters. However, do not simply add counters assuming they always obey a simple formula under every retry, rollback, or writer-scan scenario. Cross-check with source data and actual logs.

### Logging and alerting

You can log statistics when the Step finishes:

~~~java
@Bean
StepExecutionListener skipSummaryListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // No pre-step action needed in this example.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, writeSkip={}, rollback={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getRollbackCount()
            );
            return null;
        }
    };
}
~~~

Alert if total skips exceed a business-rate threshold, even before hitting skipLimit. Do not log entire items if they contain sensitive data.

## 21. Producing a custom ExitStatus when skips occur

A Step can technically finish with BatchStatus COMPLETED yet have skipped items. If business rules prohibit publishing outputs when skips occurred, you can produce a custom ExitStatus in a StepExecutionListener.

Example:

~~~java
@Bean
StepExecutionListener skipStatusListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getSkipCount() > 0) {
                return new ExitStatus("COMPLETED_WITH_SKIPS");
            }

            return null;
        }
    };
}
~~~

The flow can branch:

~~~java
.start(importStep)
    .on("COMPLETED").to(publishStep)
.from(importStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(importStep)
    .on("*").fail()
~~~

This approach allows:

- Publishing immediately if there are no skips.
- Routing to review if rejects exist.
- Failing if the Step returns an unsupported ExitStatus.

Do not assume skip automatically changes ExitStatus to COMPLETED_WITH_SKIPS. If the flow must distinguish it, actively return the custom status code.

## 22. Testing skip and rollback

Tests must verify both metrics and database data state. Checking only that the Job is COMPLETED is insufficient.

### Testing process skip

Create a processor throwing InvalidRecordException for one item:

~~~java
ItemProcessor<InputRecord, OutputRecord> processor = item -> {
    if (item.id().equals("BAD")) {
        throw new InvalidRecordException("Invalid record");
    }

    return map(item);
};
~~~

Expectations:

- Item BAD does not reach the writer.
- processSkipCount increments by 1.
- Valid items are still written.
- SkipListener receives the corresponding item and exception.

### Testing write skip and chunk rollback

Prepare a chunk containing A, B, C, D and make the writer fail when writing C.

Verify:

1. The initial chunk write throws an exception.
2. The chunk transaction rolls back.
3. No partial writes remain from the first attempt.
4. The framework isolates item C as the failing item.
5. C is skipped if policy allows.
6. A, B, and D are written successfully.
7. writeSkipCount increments accurately.
8. No duplicate data exists due to writer re-invocation.

Use a real transactional test database to verify rollback. A mock writer can check invocation counts, but it does not prove the database transaction actually rolled back.

### Testing exceeding the skip limit

With a skipLimit of 2, create three skippable failing items. Verify:

- The first two items are skipped.
- The next failing item fails the Step for exceeding the limit.
- Previously committed chunks remain intact.
- The current chunk follows the rollback policy.
- JobExecution and StepExecution reflect the failure status.

### Testing noSkip

Declare an exception under a broad skippable group while excluding a specific exception via noSkip. Verify the excluded exception fails the Step instead of being skipped.

### Testing retry then skip

Have an item throw an exception that is both retryable and skippable. Verify attempt counts, skip timing, skip count, and reject data match policy.

### Testing reader buffering and queues

With a standard reader, trigger a writer failure mid-chunk and verify items replay properly after rollback. With a transactional queue, test acknowledgment/redelivery to make sure messages are not lost.

## 23. Common design mistakes

### Skipping all exceptions

Overly broad skip(Exception.class) configuration can mask programming bugs, configuration errors, or infrastructure failures. Only skip exceptions with clear business meaning.

### Setting skip limit too high

The Job can complete with an unacceptable volume of corrupt data. Set limits and inspect error rates per batch.

### Confusing filter with skip

A processor returning null is a filter, not an exception skip. Use the right mechanism so metrics reflect reality.

### Assuming skip never rolls back

Skip and rollback are separate decisions. Especially in the writer, chunk transactions typically roll back before the framework isolates the failing item.

### Writer unsafe under re-invocation

The writer can receive the same item or subset multiple times during scanning, retry, or rollback. Side effects outside the transaction can repeat.

### Using noRollback to dodge rollback without understanding data

Disabling rollback can retain changes made prior to the exception. Only configure it when transaction state stays valid and has been tested.

### Recording rejects on every onWriteError

onWriteError observes a failed writer call; the writer may be called again. Use SkipListener to record items actually skipped.

### Skipping infrastructure errors

Broadly skipping database or API errors can produce incomplete outputs. Infrastructure errors should usually use bounded retry and fail if unrecovered.

### Publishing messages or calling APIs in a non-idempotent writer

Database rollback does not revoke messages or requests already handled by external systems. Use an outbox, idempotency keys, or post-commit publishing.

### Not testing real rollback

Tests that only check callbacks do not prove the database rolled back. Use transactional integration tests and verify table rows.

## 24. Safe skip design workflow

When building a Step with skip, follow this sequence:

1. **Classify errors:** distinguish isolated data errors, transient errors, and infrastructure failures.
2. **Identify the stage:** determine whether the error originates in the reader, processor, or writer.
3. **Define exceptions:** use specific, stable exception types.
4. **Set skip limit:** specify the maximum error count for the entire Step.
5. **Design rollback:** check which exceptions roll back and which resources participate in the transaction.
6. **Consider retry:** retry transient errors before skipping if business rules allow.
7. **Persist reject data:** use SkipListener to store identifiers and causes of skipped items.
8. **Ensure idempotency:** writers and listeners must be safe under re-invocation.
9. **Monitor metrics:** track read/process/write skips, filters, commits, and rollbacks separately.
10. **Test:** verify stage-level skips, write scans, rollbacks, limit exceedance, retries, and restarts.

## 25. Key takeaways

- Skip allows bypassing items encountering exceptions defined as skippable.
- Configure skip using faultTolerant(), skip(...), and skipLimit(...).
- Skip limit is the Step's total skipped items, covering read, process, and write.
- Reader skip occurs when the reader throws an exception; EOF null is not a skip.
- Processor returning null is a filter; processor throwing an exception can trigger a process skip.
- Writer skip is more complex because the writer receives an entire chunk and errors can roll back the transaction.
- When the writer fails, the framework may roll back and then isolate the failing item; the writer can be called multiple times.
- Rollback only undoes transaction-bound resources; external emails, APIs, files, and messages do not roll back automatically.
- noRollback changes rollback classification; it does not automatically make an exception skippable.
- SkipListener records items actually discarded; ItemProcessListener and ItemWriteListener observe processing/writer attempts.
- Retry and skip can be combined; retry limit and skip limit are two distinct limits.
- Use reader buffering or transactional queues matching the source mechanism.
- Monitor readSkipCount, processSkipCount, writeSkipCount, filterCount, commitCount, and rollbackCount.
- Test rollback against a real database in integration tests, not only with a mock writer.

Properly designed skip lets Spring Batch keep processing valid items while recording failing data. By understanding transaction rollback, especially in the writer, and bounding external side effects, applications can bypass localized errors while protecting the integrity of both chunks and the overall Job.

