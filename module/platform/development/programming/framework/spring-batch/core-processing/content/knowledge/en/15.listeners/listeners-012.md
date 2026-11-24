# Listeners and Transaction Callbacks

In Spring Batch, **listeners** and **transaction callbacks** both allow an application to react when a processing stage occurs, yet they do not share the same role and do not run at the same point in time.

- **Spring Batch listeners** observe the Job, Step, chunk, or individual item lifecycle. Examples: `beforeStep`, `afterChunk`, `afterWrite`, `onSkipInProcess`.
- **Transaction callbacks** observe the lifecycle of a Spring-managed transaction. Examples: `beforeCommit`, `afterCommit`, `afterCompletion`.
- **Transactional event listeners** receive application events at a specific transaction phase, such as `AFTER_COMMIT` or `AFTER_ROLLBACK`.

What matters is choosing the callback matching when the business effect must happen. If you need to log an item just read, use an item listener. If you need to send a notification only after database data has committed, use an after-commit callback or transactional event. If you must guarantee events are not lost when a process crashes, consider a transactional outbox.

Not every callback with `after` in its name means the transaction has committed. You must understand where each callback sits within the chunk and transaction lifecycles.

## 1. What is a Spring Batch Listener?

Listeners are interfaces or annotations that attach logic to specific points while a Job and Step execute. Listeners are commonly used to:

- Log Job/Step start and completion.
- Collect metrics on items read, processed, and written.
- Record skipped items.
- Observe read, process, or write errors.
- Update a Step's `ExitStatus`.
- Record operational status or emit events.

Common listeners:

| Listener | Observation Scope |
|---|---|
| **JobExecutionListener** | Before and after a `JobExecution` |
| **StepExecutionListener** | Before and after a `StepExecution` |
| **ChunkListener** | Before/after a chunk and when a chunk encounters an error |
| **ItemReadListener** | Before/after each read and on read error |
| **ItemProcessListener** | Before/after each processed item and on process error |
| **ItemWriteListener** | Before/after a chunk write and on write error |
| **SkipListener** | When an item is skipped under the skip policy |

Spring Batch listeners attach observation logic at the right stage, but implementing a listener does not itself start a new transaction. Callbacks normally run either inside the transaction managed by the Step or outside a transaction, depending on listener type.

## 2. What is a Transaction Callback?

Spring transactions provide callbacks so applications know which phase a transaction is in.

| Phase | Timing |
|---|---|
| **beforeCommit** | Immediately before the transaction commits |
| **beforeCompletion** | Before the transaction completes, whether commit or rollback |
| **afterCommit** | After a successful commit |
| **afterCompletion** | After the transaction completes—committed, rolled back, or unknown |

Transaction callbacks are appropriate when logic depends directly on the commit/rollback result of the current transaction. Examples: emitting notifications only after data commits, evicting cache after transaction success, recording final status, or performing cleanup regardless of commit or rollback.

These callbacks belong to Spring's transaction infrastructure, not Spring Batch listeners. A Step can use both mechanisms: Batch listeners to observe progress, and transaction callbacks to react to transaction outcomes.

## 3. Not Every "after" Callback Runs After Commit

In a chunk-oriented Step, each chunk is normally processed in its own transaction. Some callbacks run while the transaction is still active; others run only after the transaction has finished.

~~~text
Chunk transaction starts
        |
        v
ChunkListener.beforeChunk
        |
        v
ItemReadListener
        |
        v
ItemProcessListener
        |
        v
ItemWriteListener.beforeWrite
        |
        v
ItemWriter.write
        |
        v
ItemWriteListener.afterWrite
        |
        v
Update stream / checkpoint / metadata
        |
        v
Transaction commit
        |
        v
ChunkListener.afterChunk
        |
        v
Next chunk
~~~

If the chunk fails and the transaction rolls back, Spring Batch invokes the corresponding error callbacks, including `afterChunkError`.

Rules to remember:

- **ItemWriteListener.afterWrite** is called after the writer call succeeds, yet still before the chunk transaction commits.
- **ChunkListener.afterChunk** is called after the chunk has committed successfully.
- **ChunkListener.afterChunkError** is called after the chunk rolls back.
- **SkipListener** is invoked right before the transaction commits so it can use transactional resources.
- **StepExecutionListener.afterStep** and **JobExecutionListener.afterJob** are Step/Job lifecycle callbacks; do not assume they run inside a chunk transaction.

If an action must happen only after commit, do not use `afterWrite` just because its name starts with `after`. Use `afterChunk` or a transaction callback matching your requirements, while accounting for possible event loss after commit.

## 4. Which Stage Do Item Listeners Run In?

Item listeners observe individual operations of the pipeline.

### ItemReadListener

Callbacks:

- **beforeRead()**: before invoking the reader.
- **afterRead(item)**: after the reader returns an item.
- **onReadError(exception)**: when the reader throws an exception.

~~~java
@Component
public class CustomerReadListener
        implements ItemReadListener<RawCustomer> {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("About to read a customer");
    }

    @Override
    public void afterRead(RawCustomer item) {
        log.debug("Read customer id={}", item.id());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error("Customer read failed", ex);
    }
}
~~~

The reader is invoked during chunk processing. Read callbacks typically run inside the chunk transaction if the Step uses transactions. However, reading a file or calling an API does not automatically make an external source transactional.

### ItemProcessListener

Callbacks:

- **beforeProcess(item)**: before calling the processor.
- **afterProcess(item, result)**: after the processor returns.
- **onProcessError(item, exception)**: when the processor throws an exception.

~~~java
@Component
public class CustomerProcessListener
        implements ItemProcessListener<RawCustomer, Customer> {

    @Override
    public void beforeProcess(RawCustomer item) {
        // Can log or start timing.
    }

    @Override
    public void afterProcess(RawCustomer item, Customer result) {
        // result can be null if the item was filtered.
    }

    @Override
    public void onProcessError(RawCustomer item, Exception ex) {
        // Record processing error.
    }
}
~~~

If the processor returns `null`, `afterProcess` is still invoked with a `null` result. This does not mean the item was skipped due to an exception; filtering and skipping are distinct behaviors.

### ItemWriteListener

Callbacks:

- **beforeWrite(chunk)**: before calling the writer.
- **afterWrite(chunk)**: after the writer returns normally.
- **onWriteError(exception, chunk)**: when the writer throws an exception.

~~~java
@Component
public class CustomerWriteListener
        implements ItemWriteListener<Customer> {

    @Override
    public void beforeWrite(Chunk<? extends Customer> items) {
        // Record item count about to be written.
    }

    @Override
    public void afterWrite(Chunk<? extends Customer> items) {
        // Writer returned normally; chunk is not guaranteed committed yet.
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Customer> items) {
        // Log chunk write error.
    }
}
~~~

`afterWrite` is not an after-commit callback. If the framework later fails while updating metadata or committing the transaction, the chunk can still roll back. An external action executed in `afterWrite` may have already occurred even though database data was never committed.

## 5. ChunkListener and Transaction Boundaries

`ChunkListener` provides three callbacks: `beforeChunk`, `afterChunk`, and `afterChunkError`.

~~~java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.info("Chunk started");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.info("Chunk committed successfully");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk rolled back");
    }
}
~~~

In a chunk-oriented Step:

- `beforeChunk` is called after the transaction starts and before reading chunk data.
- `afterChunk` is called after the chunk commits successfully.
- `afterChunkError` is called after the chunk rolls back.

This listener is helpful for counting successful/failed chunks or writing operational logs. However, a post-commit callback cannot return an already-committed transaction to a rolled-back state. If `afterChunk` calls an API and the API fails, the chunk's database data remains committed. If the callback writes to the database, that operation needs its own transaction if an independent commit is desired.

## 6. SkipListener and When Skipped Records Are Persisted

`SkipListener` is invoked when an item is skipped under the Step's fault-tolerant configuration.

~~~java
public interface SkipListener<T, S> {

    void onSkipInRead(Throwable t);

    void onSkipInWrite(S item, Throwable t);

    void onSkipInProcess(T item, Throwable t);
}
~~~

Example recording skipped items:

~~~java
@Component
public class CustomerSkipListener
        implements SkipListener<RawCustomer, Customer> {

    private final RejectedCustomerRepository repository;

    public CustomerSkipListener(
            RejectedCustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        // No valid item to save if the reader could not produce an item.
    }

    @Override
    public void onSkipInProcess(RawCustomer item, Throwable t) {
        repository.save(
                RejectedCustomer.from(item, t.getMessage()));
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        repository.save(
                RejectedCustomer.from(item, t.getMessage()));
    }
}
~~~

`SkipListener` is invoked immediately before transaction commit so skipped data can be persisted to transactional resources. If recording faulty rows uses the same transaction manager and database as the Step, skip records can commit together with the chunk.

Spring Batch includes mechanisms ensuring `SkipListener` is called once per skipped item within the framework's processing context, preventing duplicate recording from internal rollbacks/retries. Still, do not rely on a listener to provide exactly-once guarantees for external systems. If the listener calls an API or sends an email, those actions do not automatically roll back with the database.

If `onSkipInRead` has no input item because the reader failed to parse it, the callback receives only a `Throwable`. If source line details must be saved, extract them from the specific exception—such as the line number on `FlatFileParseException`—or design the reader/listener to supply appropriate metadata.

## 7. StepExecutionListener and JobExecutionListener

These two listeners observe the lifecycle at a higher level than chunks.

### StepExecutionListener

- **beforeStep(stepExecution)**: before the Step executes.
- **afterStep(stepExecution)**: after the Step finishes; can return an additional or custom `ExitStatus`.

~~~java
@Component
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext()
                .putString("startedBy", "batch-service");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getWriteCount() == 0
                && stepExecution.getStatus() == BatchStatus.COMPLETED) {
            return new ExitStatus("NO_DATA");
        }

        return stepExecution.getExitStatus();
    }
}
~~~

`afterStep` can adjust `ExitStatus` so flow transitions use business outcome codes. It is not a post-commit callback for individual chunks and should not be used under the assumption that a chunk transaction is still open.

### JobExecutionListener

- **beforeJob(jobExecution)**: before the Job runs.
- **afterJob(jobExecution)**: after the Job finishes.

~~~java
@Component
public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Job started, executionId={}", jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Job finished, executionId={}, status={}",
                jobExecution.getId(),
                jobExecution.getStatus());
    }
}
~~~

Job listeners are suited for logging, updating monitoring, or summarizing final outcomes. Do not put actions that must participate in a chunk's transaction inside `afterJob`, as chunk transactions have already finished by then.

## 8. Registering Listeners on a Step or Job

You can register listeners when building a Step:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> reader,
        ItemProcessor<RawCustomer, Customer> processor,
        ItemWriter<Customer> writer,
        ImportChunkListener chunkListener,
        CustomerReadListener readListener,
        CustomerProcessListener processListener,
        CustomerWriteListener writeListener,
        CustomerSkipListener skipListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(chunkListener)
            .listener(readListener)
            .listener(processListener)
            .listener(writeListener)
            .listener(skipListener)
            .faultTolerant()
            .skip(InvalidCustomerException.class)
            .skipLimit(100)
            .build();
}
~~~

Registering a listener on a Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        ImportJobListener jobListener) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(importCustomersStep)
            .listener(jobListener)
            .build();
}
~~~

Spring Batch supports registering listeners through builders and corresponding annotations. For annotation-based listeners, ensure the bean is Spring-managed and in the proper scope. You do not need to call listener methods manually from readers or writers; Spring Batch invokes them per lifecycle once properly registered.

## 9. TransactionSynchronization: Direct Spring Transaction Callbacks

If you need to know whether the current transaction committed or rolled back, register a `TransactionSynchronization`.

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {

                @Override
                public void beforeCommit(boolean readOnly) {
                    // Transaction is about to commit.
                }

                @Override
                public void afterCommit() {
                    // Transaction committed successfully.
                }

                @Override
                public void afterCompletion(int status) {
                    if (status == STATUS_COMMITTED) {
                        // Transaction completed with commit.
                    } else if (status == STATUS_ROLLED_BACK) {
                        // Transaction completed with rollback.
                    }
                }
            });
}
~~~

Key callbacks:

- **beforeCommit**: transaction is about to commit; can still roll back if commit fails.
- **beforeCompletion**: transaction is preparing to complete, whether commit or rollback.
- **afterCommit**: runs only on successful commit.
- **afterCompletion**: runs after transaction completion and provides the final completion status.

Check `isSynchronizationActive()` before registering. If no synchronization is active, callbacks cannot attach to a transaction as intended.

### afterCommit cannot roll back already-committed data

When `afterCommit` is called, the primary transaction has committed. If the callback calls an API and the API fails, the database transaction is already finished; committed data cannot be rolled back.

If the callback needs to write additional database records and have that work commit independently, call a service with an appropriate `@Transactional(propagation = Propagation.REQUIRES_NEW)`. Resources from the previous transaction may still be bound during the callback; a new transaction establishes a separate commit boundary.

Do not perform heavy work or wait long on external systems synchronously inside a post-commit callback. That can delay request or processing-thread completion.

## 10. @TransactionalEventListener

Spring provides `@TransactionalEventListener` to handle application events according to transaction phase.

| Phase | Meaning |
|---|---|
| **BEFORE_COMMIT** | Handle before transaction commits |
| **AFTER_COMMIT** | Handle after successful commit |
| **AFTER_ROLLBACK** | Handle after transaction rolls back |
| **AFTER_COMPLETION** | Handle after transaction completes, regardless of outcome |

Example publishing an event when processing an order:

~~~java
public record OrderImportedEvent(Long orderId) {
}
~~~

Service publishing the event inside a transaction:

~~~java
@Service
public class OrderImportService {

    private final ApplicationEventPublisher eventPublisher;
    private final OrderRepository orderRepository;

    public OrderImportService(
            ApplicationEventPublisher eventPublisher,
            OrderRepository orderRepository) {
        this.eventPublisher = eventPublisher;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void importOrder(Order order) {
        orderRepository.save(order);

        eventPublisher.publishEvent(
                new OrderImportedEvent(order.getId()));
    }
}
~~~

The listener receives the event only after the transaction commits:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderImported(OrderImportedEvent event) {
        // Send notification after order data has committed.
    }
}
~~~

By default, `@TransactionalEventListener` uses the `AFTER_COMMIT` phase. If an event is published when no transaction is active, the listener is normally not invoked. You can configure `fallbackExecution = true` to run anyway in that case, though understand there is no transaction bounding execution timing then.

Choose the phase matching your goal:

- **BEFORE_COMMIT**: check or perform work required before commit; exceptions can prevent the transaction from committing.
- **AFTER_COMMIT**: send notifications or update caches after data is confirmed.
- **AFTER_ROLLBACK**: record or trigger handling when a transaction fails.
- **AFTER_COMPLETION**: cleanup needed whether the transaction commits or rolls back.

Do not use `AFTER_COMPLETION` if you only want to react to a successful commit; use `AFTER_COMMIT` or check the completion status.

## 11. Listeners and Transaction Callbacks in a Chunk Step

Consider a chunk writing customer data:

~~~text
Chunk transaction starts
        |
        v
ChunkListener.beforeChunk
        |
        v
ItemReadListener.beforeRead / afterRead
        |
        v
ItemProcessListener.beforeProcess / afterProcess
        |
        v
ItemWriteListener.beforeWrite
        |
        v
ItemWriter.write
        |
        v
ItemWriteListener.afterWrite
        |
        v
SkipListener (if items are skipped)
        |
        v
Update ItemStream / ExecutionContext
        |
        v
Transaction commit
        |
        +--> TransactionSynchronization.afterCommit
        |
        +--> ChunkListener.afterChunk
        |
        v
Next chunk
~~~

The diagram illustrates the conceptual order of major stages; do not treat it as an absolute ordering between every listener and every transaction synchronization across all configurations. Error listeners and retries can cause some callbacks to be invoked multiple times.

Key distinctions:

- Item listeners observe read/process/write operations.
- `SkipListener` observes items skipped during error handling.
- `ChunkListener` observes chunk boundaries.
- `TransactionSynchronization` observes the transaction.
- Step/Job listeners observe higher-level lifecycles.

Pick the callback with the right boundary instead of forcing a single listener to serve every purpose.

## 12. Side Effects Before Commit Can Be Repeated

Suppose `afterWrite` sends an email:

~~~java
@Override
public void afterWrite(Chunk<? extends Customer> items) {
    for (Customer customer : items) {
        emailService.sendWelcomeEmail(customer.email());
    }
}
~~~

The following sequence can happen:

1. The writer writes database records successfully.
2. `afterWrite` sends the email successfully.
3. The framework updates metadata.
4. Transaction commit fails.
5. The chunk rolls back.
6. The Job retries or restarts and reprocesses the items.
7. The email can be sent a second time.

Email does not participate in the database transaction, so a rollback cannot retract a sent email. The same applies to HTTP requests, messages sent to non-transactional brokers, plain file writes, or calls to external systems.

For critical side effects, consider:

- Emitting events only after commit.
- Using idempotency keys to guard against duplicate processing.
- Writing an outbox record in the same transaction as business data.
- Having a separate worker read the outbox and execute external actions.
- Having retry and reconciliation mechanisms when external systems are temporarily unavailable.

## 13. How afterCommit and Transactional Outbox Differ

`afterCommit` guarantees a callback runs only after the current transaction commits successfully. However, the callback still executes within the same application process. If the JVM crashes right after commit and before the callback finishes, the external effect can be lost.

A transactional outbox solves this by persisting the event-emission request in the same database transaction as the business data.

~~~text
Chunk transaction
       |
       +--> INSERT customer
       |
       +--> INSERT outbox_event
       |
       v
     COMMIT
       |
       v
Outbox worker reads unsent events
       |
       v
Send to external system
       |
       v
Mark event as processed
~~~

If the transaction rolls back, both `customer` and `outbox_event` roll back. If commit succeeds and the application stops, `outbox_event` remains in the database for the worker to send once the system recovers.

An outbox does not by itself guarantee exactly-once delivery at the target system. The worker may resend if it misses an acknowledgment or crashes before marking completion. Target systems should still support idempotency or recognize event IDs.

## 14. How Exceptions in Listeners Affect Execution

The impact of an exception depends on which stage the callback runs in.

| Callback | When the Callback Throws an Exception |
|---|---|
| Item listener during chunk processing | Can fail the chunk and roll back the transaction; fault-tolerant policy can affect handling |
| `beforeChunk` | Can prevent the chunk from starting normal processing |
| `afterWrite` | Writer returned but transaction has not committed; exception can roll back the chunk |
| `SkipListener` | Can fail the chunk and prevent skip recording from completing |
| `afterChunk` | Chunk has committed; exception cannot roll back committed data |
| `afterCommit` | Transaction has committed; exception cannot undo that transaction |
| `afterStep` / `afterJob` | Do not rely on exceptions to roll back already-completed chunks |

For post-commit callbacks, handle errors as post-commit failures: log, retry via a durable mechanism, or route work to a queue/outbox. Never assume throwing an exception will revert committed data.

For listeners inside a chunk, avoid letting non-critical logging or metrics throw exceptions that disrupt business data. If a listener must persist critical data, clarify whether it participates in the chunk transaction or uses its own transaction.

## 15. Do Post-Commit Callbacks Have an Active Transaction?

Spring transactions may retain resource bindings during part of post-commit callbacks so cleanup can run afterward. However, the primary transaction has already committed and there will be no second commit for changes made during the callback.

Therefore, if `afterCommit` calls a repository and that operation must be persisted durably, do not assume it commits automatically with the finished transaction. Use a new transaction:

~~~java
@Service
public class AuditAfterCommitService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordCommittedOrder(Long orderId) {
        // Write audit in an independent transaction.
    }
}
~~~

Invoke the service through a Spring proxy so propagation applies. Calling a `REQUIRES_NEW` method via self-invocation inside the same bean bypasses the proxy.

For tasks that may be retried or must never be lost, an outbox remains more durable than in-memory callbacks.

## 16. Distinguishing Listener Callbacks from @Transactional

`@Transactional` and listeners are not two names for the same mechanism.

- **@Transactional** defines transaction boundaries for methods managed by a Spring proxy.
- **Spring Batch listeners** are invoked by the framework at Job/Step/chunk/item lifecycle hooks.
- **TransactionSynchronization** registers callbacks with the active transaction.
- **@TransactionalEventListener** handles application events by transaction phase.

Example transactional service:

~~~java
@Transactional
public void updateCustomer(Customer customer) {
    customerRepository.save(customer);
}
~~~

If this method is called from a processor using the same transaction manager, it normally joins the chunk transaction under default `REQUIRED` propagation.

An `ItemProcessListener.afterProcess` does not open a transaction on its own merely because it is a listener. It runs within the processing context invoked by Spring Batch. If the listener calls a transactional service, that service applies propagation against the current transaction and corresponding transaction manager.

Similarly, `@TransactionalEventListener` does not start a new transaction for the event. It binds event processing timing to the transaction that published the event.

## 17. Testing Listeners and Transaction Callbacks

Tests should verify callbacks fire at the right time relative to commit and rollback.

### Testing ItemWriteListener

You can use Mockito to verify the listener is invoked when the writer executes:

~~~java
@Test
void itemWriteListenerReceivesWrittenChunk() throws Exception {
    ItemWriteListener<Customer> listener =
            mock(ItemWriteListener.class);

    Chunk<Customer> chunk =
            new Chunk<>(List.of(customer));

    listener.beforeWrite(chunk);
    listener.afterWrite(chunk);

    verify(listener).beforeWrite(chunk);
    verify(listener).afterWrite(chunk);
}
~~~

This is only a unit test for the listener interface. To confirm callback position relative to transactions, run Step integration tests with a real transaction manager and observe persisted state.

### Testing afterCommit

You can register synchronization in a transaction test:

~~~java
@Test
void callbackRunsAfterSuccessfulCommit() {
    AtomicBoolean committed = new AtomicBoolean(false);

    transactionTemplate.execute(status -> {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        committed.set(true);
                    }
                });

        assertFalse(committed.get());
        return null;
    });

    assertTrue(committed.get());
}
~~~

This test verifies the callback runs only after the transaction template finishes committing successfully.

### Testing rollback

Create a transaction that deliberately rolls back and verify `afterCommit` is not called, while `afterCompletion` receives the rolled-back status.

~~~java
@Test
void afterCommitIsNotCalledWhenTransactionRollsBack() {
    AtomicBoolean committed = new AtomicBoolean(false);
    AtomicInteger completionStatus = new AtomicInteger(-1);

    transactionTemplate.execute(status -> {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        committed.set(true);
                    }

                    @Override
                    public void afterCompletion(int status) {
                        completionStatus.set(status);
                    }
                });

        status.setRollbackOnly();
        return null;
    });

    assertFalse(committed.get());
    assertEquals(
            TransactionSynchronization.STATUS_ROLLED_BACK,
            completionStatus.get());
}
~~~

In real tests, use the transaction manager and transaction template configured for the same `DataSource` as the Step.

## 18. Common Mistakes

### Using afterWrite as afterCommit

`afterWrite` runs after the writer call yet before the chunk transaction commits. Side effects in the callback can execute and then the chunk rolls back.

### Sending emails in ItemProcessListener

The processor can be re-invoked on retry or rollback. Sent emails are not automatically retracted. Move side effects to an outbox or post-commit handling with deduplication.

### Thinking afterChunk can roll back a chunk

`afterChunk` is called after the chunk commits successfully. Exceptions in the callback cannot roll back an already-finished transaction.

### Thinking afterJob is inside the last transaction

`afterJob` is a Job lifecycle callback. Step transactions have already ended; do not rely on it to join a chunk transaction.

### Using transaction callbacks without an active transaction

`TransactionSynchronizationManager.registerSynchronization` requires active synchronization. Check status before registering and define fallback behavior when a callback cannot attach to a transaction.

### Writing to the database in afterCommit expecting it to commit with the old transaction

The old transaction has already committed. If independent persistence is needed, use a new transaction. If crash reliability is required, consider an outbox.

### Using afterCompletion without checking status

`afterCompletion` runs on both commit and rollback. If you only want action after commit, check completion status or use `afterCommit`.

### Relying on callbacks for external exactly-once delivery

Callbacks do not replace idempotency or a transactional outbox. Process crashes and network errors can still lose or duplicate side effects.

## 19. Choosing the Right Callback by Goal

| Goal | Mechanism to Consider |
|---|---|
| Log before/after Job | `JobExecutionListener` |
| Modify Step `ExitStatus` | `StepExecutionListener.afterStep` |
| Count successful/failed chunks | `ChunkListener` |
| Observe read items | `ItemReadListener` |
| Observe processed or failing items | `ItemProcessListener` |
| Observe chunk write calls | `ItemWriteListener` |
| Persist skipped records in transaction | `SkipListener` |
| Run logic right before commit | `TransactionSynchronization.beforeCommit` or `BEFORE_COMMIT` event |
| Run only on successful commit | `TransactionSynchronization.afterCommit` or `AFTER_COMMIT` event |
| Run when transaction rolls back | `afterCompletion` checking status or `AFTER_ROLLBACK` event |
| Cleanup after any transaction outcome | `TransactionSynchronization.afterCompletion` |
| Emit durable events to external systems | Transactional outbox |

No single callback fits every case. Choose by asking: which lifecycle needs observation, does the callback run before or after commit, and does the triggered action participate in the transaction?

## 20. Safe Listener Design Checklist

When adding a listener or transaction callback to a Job, determine:

1. Is the listener at Job, Step, chunk, or item level?
2. Does the callback run before writer, after writer, before commit, or after commit?
3. Is a transaction active when the callback runs?
4. Do actions executed by the callback use the same transaction manager and resources?
5. If the chunk rolls back, will side effects revert or could they repeat?
6. If a post-commit callback fails, does the application have a retry mechanism?
7. If the JVM crashes after commit but before the callback runs, will events be lost?
8. Are idempotency keys or a transactional outbox needed?
9. Can the listener throw exceptions that disrupt the chunk?
10. Have tests verified callbacks on both commit and rollback branches?

Use Spring Batch listeners to observe Job, Step, chunk, and item milestones. Use transaction callbacks when logic depends on transaction commit/rollback outcomes. For external effects requiring reliability, persist event-emission requests inside the same transaction via an outbox and handle them idempotently. Clearly distinguishing these lifecycles prevents sending notifications before data commits, recording skips at the wrong time, or assuming a callback can roll back confirmed data.
