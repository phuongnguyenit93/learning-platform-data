# TransactionSynchronizationFactory in Spring Integration Runtime

## Lesson objectives

In **SPRING_INTEGRATION_RUNTIME**, a flow can start from a polling consumer, read messages through channels, perform database updates, invoke endpoints, and finally pass results to another system. A successful DB commit **does not mean** all actions outside the DB have occurred; conversely, when the DB rolls back, you sometimes need to move the source file to a failure directory or record information for later handling.

**TransactionSynchronizationFactory** is Spring Integration's extension point that allows registering actions based on the **transaction outcome** of a poll run. It is especially useful when you want to handle the message source after the synchronous flow completes, such as marking a file as processed, routing a notification to a success or failure channel, and preserving original message information when an error occurs.

After this lesson, you will be able to:

- Understand the relationship among **TransactionSynchronizationFactory**, **TransactionSynchronization**, **TransactionSynchronizationProcessor**, and **IntegrationResourceHolder**.
- Accurately distinguish the three lifecycle points: **beforeCommit**, **afterCommit**, and **afterRollback**.
- Configure synchronization for a **transactional poller**, using either XML namespace or Spring JavaConfig.
- Know when you need **DefaultTransactionSynchronizationFactory**, **PassThroughTransactionSynchronizationFactory**, or **PseudoTransactionManager**.
- Diagnose the impact of **DirectChannel, ExecutorChannel, poller, transaction advice, retry, errorChannel, MessageStore**, and correlation.
- Avoid confusing synchronization with distributed transactions or **exactly once** event delivery guarantees.

## 1. Practical problem: processing files and updating a DB

Suppose an application scans a directory containing order files:

~~~text
/inbox/order-42.json
    ↓ File inbound adapter + transactional poller
    ↓ DirectChannel
    ↓ JSON transformer
    ↓ Service activator
    ↓ Write order and line items to DB
    ├─ COMMIT   → move file to /processed/
    └─ ROLLBACK → move file to /failed/ or leave it for retry
~~~

If the handler both writes to the DB and moves the file directly in code:

~~~java
void process(File file) {
    saveOrderToDatabase(file);  // May belong to the DB transaction.
    moveFile(file, processedDir); // The file system does not belong to the DB transaction.
}
~~~

then calling **moveFile** before the DB commit finishes can cause a situation where the file has already been moved yet the transaction rolls back. On the next poll, the file is no longer there, even though the DB has no order.

**Transaction synchronization** lets you defer actions according to transaction status:

- If the transaction ends with a commit, run the **afterCommit** step.
- If the transaction rolls back, run the **afterRollback** step.
- If a condition needs to be checked right before commit, run **beforeCommit**.

However, there is an important limitation: **timing coordination is different from atomicity**. The file system, HTTP APIs, or a message broker do not automatically become a shared transactional resource with the DB just because they are called inside a callback. If the app dies right after DB commit but before moving the file, recovery via another mechanism may still be needed.

## 2. What is TransactionSynchronizationFactory?

In the **org.springframework.integration.transaction** package, the core interface has the general contract:

~~~java
public interface TransactionSynchronizationFactory {
    TransactionSynchronization create(Object key);
}
~~~

The factory creates a **TransactionSynchronization** object for the corresponding transaction context. **The key parameter is a context key passed by the framework**; you should not assume it is the payload, message ID, or business key. When the original message is needed, use the **IntegrationResourceHolder** mechanism supported by Spring Integration.

Spring Integration provides:

| Component | Role |
| --- | --- |
| **TransactionSynchronizationFactory** | Strategy that creates synchronization for a processing context |
| **DefaultTransactionSynchronizationFactory** | Built-in implementation that accepts a **TransactionSynchronizationProcessor** and creates a synchronization delegating callbacks to the processor |
| **TransactionSynchronizationProcessor** | Contract consisting of **processBeforeCommit**, **processAfterCommit**, and **processAfterRollback** |
| **ExpressionEvaluatingTransactionSynchronizationProcessor** | Built-in processor that evaluates **SpEL** expressions in the before-commit, after-commit, and after-rollback phases; can send results to channels |
| **IntegrationResourceHolder** | Holds a reference to the Spring Message being polled and related resource/attributes; provides **getMessage()** |
| **PassThroughTransactionSynchronizationFactory** | Minimal synchronization, mainly associating the polled message with the transaction context to aid error diagnostics |
| **PseudoTransactionManager** | Provides commit/rollback callback semantics when there is no real transactional resource; **does not** roll back external operations like files or FTP |

The processor contract:

~~~java
public interface TransactionSynchronizationProcessor {
    void processBeforeCommit(IntegrationResourceHolder holder);
    void processAfterCommit(IntegrationResourceHolder holder);
    void processAfterRollback(IntegrationResourceHolder holder);
}
~~~

In real code, these interfaces reside in Spring Integration packages; **TransactionSynchronization** comes from Spring Framework's transaction mechanism. The factory does not create a new transaction manager and does not actively start transactions. It works with the transaction/transaction advice **already configured on the poller**.

### How does the factory differ from @Transactional?

**@Transactional** or **TransactionInterceptor** controls **when a transaction begins, commits, or rolls back**, based on the wrapped invocation and rollback rules. **TransactionSynchronizationFactory** registers callbacks **along that transaction lifecycle**. The two mechanisms complement each other; a factory alone does not make data processing transactional.

Example:

~~~text
TransactionInterceptor:
  begin transaction → poll message → run flow → commit/rollback

TransactionSynchronizationFactory:
  create synchronization for polled message/resource
  → beforeCommit / afterCommit / afterRollback at the appropriate time
~~~

## 3. Execution sequence in a transactional poller

For a flow that stays on the same thread, the general model is:

~~~mermaid
flowchart TD
    P["Poller triggered by scheduler"] --> TX["TransactionInterceptor<br/>begins transaction"]
    TX --> R["MessageSource.receive() / receive message"]
    R --> B["Bind message/resource to<br/>transaction synchronization"]
    B --> F["Synchronous flow via DirectChannel<br/>transformer / handler / DB"]
    F --> OK{"Can flow and transaction<br/>commit?"}
    OK -- "Yes" --> BC["beforeCommit"]
    BC --> COM{"beforeCommit succeeded?"}
    COM -- "Yes" --> DB["Commit transaction"]
    DB --> AC["afterCommit"]
    AC --> DONE["Finish / cleanup"]
    COM -- "No" --> RB["Rollback transaction"]
    OK -- "No" --> RB
    RB --> AR["afterRollback"]
    AR --> FIN["Finish / cleanup"]
~~~

This is a **simplified logical diagram**. In practice, Spring Framework has additional transaction lifecycle callbacks, resource management, and exception/cleanup handling. A successful **beforeCommit** does not guarantee commit will succeed; the DB can still fail during the commit step.

### Phases and consequences

| Phase | Has the transaction committed yet? | Appropriate examples | Risks |
| --- | --- | --- | --- |
| **beforeCommit** | **Not yet** | Checking preconditions before commit, running logic that may error to roll back the transaction | Do not emit irreversible side effects; even if this phase succeeds, commit can still fail |
| **afterCommit** | **Committed** | Emitting completion signals, moving files to a success directory, starting post-processing | If the callback fails, the DB has already committed; throwing an exception cannot roll back the DB |
| **afterRollback** | Transaction rolled back | Recording failure, moving files to an inspection area, routing to controlled retry | Does not undo side effects that happened outside the DB; not every abnormal termination is a definite rollback |

**beforeCommit** can cause the transaction to roll back if the expression or downstream processing in this phase throws an exception. However, if you send an event over the network in beforeCommit and then the DB rolls back, the event may already have been sent. **afterCommit** reduces that ordering mistake, yet a gap still exists between DB commit and event emission; use a **transactional outbox** when durable event publishing is required.

## 4. XML configuration for a transactional poller

Spring Integration documentation illustrates synchronization on a **file inbound adapter**. Below is a typical namespace snippet, assuming the beans/channels **transactionManager**, **fileFilter**, **orders**, **committedFiles**, and **rolledBackFiles** are already declared in the application context:

~~~xml
<int-file:inbound-channel-adapter
        id="orderFileInbound"
        directory="/data/inbox"
        filter="fileFilter"
        channel="orders">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"
                synchronization-factory="orderSyncFactory"/>
    </int:poller>
</int-file:inbound-channel-adapter>

<int:transaction-synchronization-factory id="orderSyncFactory">
    <int:after-commit
            expression="payload"
            channel="committedFiles"/>
    <int:after-rollback
            expression="payload"
            channel="rolledBackFiles"/>
</int:transaction-synchronization-factory>
~~~

**Notes:**

1. The poller opens a transaction via **int:transactional** and the configured transaction manager. The factory is linked using **synchronization-factory**.
2. **orders** is the channel for the service activator/transformer to process the file. The synchronous processing chain can share the same DB transaction when properly configured.
3. **expression="payload"** returns the payload of the **originally polled** message. The result is sent to **committedFiles** or **rolledBackFiles**, so in this example subscribers can receive the **File** and decide to move the file, log, or quarantine it.
4. Specifying an **expression** with a non-null result and a **channel** creates a message containing the expression result. If no expression is specified and only a channel is given, Spring Integration can forward the **received message** to that channel.
5. The file adapter, filter, transaction manager, channels, and handlers must all be wired into a real flow. This XML snippet illustrates **only the synchronization portion**, not a standalone runnable project when copied on its own.
6. In a real flow, check policies to prevent polling the same file repeatedly, duplicate filenames, unavailable failure directories, and behavior when moving a file fails.

### What data do SpEL expressions see?

With **ExpressionEvaluatingTransactionSynchronizationProcessor**, **#root** is the original polled Spring Message. Therefore:

~~~text
payload
    → payload of the original message

headers['correlationId']
    → correlationId value of the original message (if present)

payload.name
    → File name if payload is indeed a java.io.File
~~~

Depending on the **MessageSource**, the framework may expose additional SpEL variables. The official documentation gives examples like **#mongoTemplate** for the MongoDB message source or **#store** for the Redis store message source. Do not use such variables on another adapter if its message source does not publish them.

### Moving files in callbacks: the result is not a business message

A common documentation example:

~~~xml
<int:transaction-synchronization-factory id="moveFilesSyncFactory">
    <int:after-commit
        expression="payload.renameTo(new java.io.File('/data/processed/' + payload.name))"
        channel="moveSuccessResults"/>
    <int:after-rollback
        expression="payload.renameTo(new java.io.File('/data/failed/' + payload.name))"
        channel="moveFailureResults"/>
</int:transaction-synchronization-factory>
~~~

This is an **example of a file operation**, not a file system transaction. The **File.renameTo()** expression returns a **boolean**; messages sent to the two channels above carry **true/false**, **not a File**. A false value must be handled, because the method may not throw an exception on failure. Details such as moving files across partitions, write permissions, and races between poller and retry must be designed separately.

If downstream needs the full payload or correlation, send the **original payload/message** to a dedicated handler, where the operation executes in a controlled manner, records results, alerts on failure, and ensures idempotency. For high volume or audit requirements, split it into a durable processing command rather than relying solely on an in-memory callback.

## 5. Creating the factory from JavaConfig

XML is not required to declare the processor. Modern APIs let you construct **ExpressionEvaluatingTransactionSynchronizationProcessor** and wrap it with **DefaultTransactionSynchronizationFactory**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.ExpressionEvaluatingTransactionSynchronizationProcessor;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class OrderSynchronizationConfiguration {

    @Bean
    TransactionSynchronizationFactory orderSynchronizationFactory(
            @Qualifier("committedFiles") MessageChannel committedFiles,
            @Qualifier("rolledBackFiles") MessageChannel rolledBackFiles) {
        SpelExpressionParser parser = new SpelExpressionParser();

        ExpressionEvaluatingTransactionSynchronizationProcessor processor =
                new ExpressionEvaluatingTransactionSynchronizationProcessor();

        processor.setAfterCommitExpression(
                parser.parseExpression("payload"));
        processor.setAfterCommitChannel(committedFiles);

        processor.setAfterRollbackExpression(
                parser.parseExpression("payload"));
        processor.setAfterRollbackChannel(rolledBackFiles);

        return new DefaultTransactionSynchronizationFactory(processor);
    }
}
~~~

This snippet only creates the factory bean; **you must reference that bean from the transactional poller configuration**. Versions of Spring Integration also provide **TransactionSynchronizationFactoryBean**, supporting builder-style expression/channel declaration in JavaConfig. Choosing the declaration style does not change transaction semantics.

Never use SpEL expressions controlled directly by user input. Expressions have access to runtime objects/messages; they must be trusted, tested, and access-controlled configuration.

### Writing a custom processor when specialized logic is needed

When merely forwarding a message to a channel, the built-in processor is usually enough. For specialized requirements, you can implement **TransactionSynchronizationProcessor**:

~~~java
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.integration.transaction.TransactionSynchronizationProcessor;
import org.springframework.messaging.Message;

class AuditSynchronizationProcessor
        implements TransactionSynchronizationProcessor {

    private final AuditRecorder recorder;

    AuditSynchronizationProcessor(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    public void processBeforeCommit(IntegrationResourceHolder holder) {
        // Do not emit side effects outside the transaction here unless necessary.
    }

    @Override
    public void processAfterCommit(IntegrationResourceHolder holder) {
        Message<?> polledMessage = holder.getMessage();
        recorder.recordCommitted(
                String.valueOf(polledMessage.getHeaders().get("requestId")));
    }

    @Override
    public void processAfterRollback(IntegrationResourceHolder holder) {
        Message<?> polledMessage = holder.getMessage();
        recorder.recordRolledBack(
                String.valueOf(polledMessage.getHeaders().get("requestId")));
    }
}

interface AuditRecorder {
    void recordCommitted(String requestId);
    void recordRolledBack(String requestId);
}
~~~

This is **contract-illustrative code**, not yet a reliable audit mechanism: the **requestId** header needs null/value checks, and **recorder** needs idempotency and separate error handling. Calling the DB in **afterCommit** does not belong to a new transaction by default; to write durable status after commit, you must define a new transaction and handle the case where the callback dies before writing.

When creating a completely custom **TransactionSynchronizationFactory** and synchronization, you must properly manage the lifecycle of resources bound to the transaction. Spring Integration explicitly states that a custom factory is responsible for **unbinding resources** when the transaction completes; by default, the framework uses an implementation based on **ResourceHolderSynchronization** to avoid resource leaks across polls on the same thread.

## 6. PassThroughTransactionSynchronizationFactory and ErrorMessage

Not every flow needs user-declared success/failure callbacks. Yet when a poller runs under transaction advice, keeping the **polled message** is important for diagnosing exceptions.

Since **Spring Integration 5.0**, when a polling endpoint has a **TransactionInterceptor** in its advice chain without a custom factory declared, the framework typically uses **PassThroughTransactionSynchronizationFactory** by default. Its job is to associate the polled message with the transaction context so that when an exception occurs downstream after the transaction advice, the error can be wrapped into a **MessagingException** carrying **failedMessage**.

~~~text
Poller
  → transaction advice
  → message A (headers: requestId, correlationId)
  → handler throws error
  → MessagingException
       ├─ failedMessage = message A
       └─ cause = root error
  → ErrorMessage on errorChannel (per endpoint mechanism)
~~~

Benefit: an error consumer can access the **payload, requestId, correlationId** of the message instead of seeing only a stack trace. If using custom transaction advice **other than TransactionInterceptor**, you may need to configure **PassThroughTransactionSynchronizationFactory** explicitly to get similar behavior.

**Do not misunderstand:** A pass-through factory does not mean **afterCommit/afterRollback business actions** are configured. When you want to publish a message to a channel after commit or rollback, you must configure an appropriate processor.

In error flows, inspect both **ErrorMessage.getOriginalMessage()** (if present) and **MessagingException.getFailedMessage()**; do not assume ErrorMessage headers automatically carry business correlation. Errors occurring **before the poll obtains a message** may also lack a failedMessage.

## 7. PseudoTransactionManager: callbacks without a DB transaction

A flow that only processes files and sends via FTP might not use a transactional resource like JDBC or JMS. Even so, there is still a need for "if the flow finishes, move the file to processed; if it errors, move it to failed."

**PseudoTransactionManager** lets you run callbacks based on the flow's completion status, even without a real transaction on files or FTP:

~~~xml
<bean id="transactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager"/>
~~~

When attaching the pseudo transaction manager to a transactional poller along with a factory:

- Flow ends successfully → **beforeCommit** and **afterCommit** can run.
- Flow fails/rolls back → **afterRollback** is invoked.
- **No real resource commit or rollback occurs** for files, SMTP, FTP, or HTTP. An uploaded file is not "automatically retracted" when the flow reports an error.

This fits workflows coordinated by processing outcome, and is **not** suitable when business rules require atomicity across independent systems. For strong recovery guarantees, use durable auditing, idempotency, controlled retries, and reconciliation/compensation mechanisms.

## 8. Thread boundaries: where does the transaction end?

Traditional Spring transactions are bound to a **thread**. If a poller opens a transaction and all subsequent channels/handlers run synchronously on the same thread, compatible resources can participate in that same context.

~~~mermaid
flowchart LR
    P["Poller + transaction"] --> D["DirectChannel"]
    D --> H["Handler DB"]
    H --> C["Commit / rollback"]
    C --> S["Sync callback"]
~~~

But if the flow crosses an **ExecutorChannel** or a pollable channel leading to another consumer:

~~~mermaid
flowchart LR
    P["Poller + transaction A"] --> E["ExecutorChannel"]
    E --> ACK["Handoff succeeds"]
    ACK --> CA["Commit A<br/>sync afterCommit"]
    E -. "Different thread" .-> H["Handler DB / HTTP"]
    H --> B["Transaction B if configured"]
~~~

**Transaction A does not automatically propagate across the new thread.** A's afterCommit callback can run while the asynchronous handler is still running or has not finished yet. Therefore, an "afterCommit message" on the poller **cannot be interpreted as meaning all async downstream work succeeded**.

| Component | Impact on the transaction from the poller |
| --- | --- |
| **DirectChannel** | Invokes the handler synchronously on the current thread; usually preserves the same transaction context |
| **ExecutorChannel** | Switches to a thread pool; sender's transaction/ThreadLocal does not propagate by default |
| **QueueChannel + another polling consumer** | Hands off the message, ending the earlier poller's transaction; the downstream consumer needs its own transaction |
| **Synchronous gateway** | Can join the same thread/transaction if the flow has no async boundary |
| **Broker/HTTP adapter** | Delivering a message to an external system does not create a distributed transaction with JDBC by default |

If messages must be preserved across an async boundary, consider a **transactional message store, broker transaction**, or outbox, while explicitly defining **each side's transaction**. Putting a callback on the poller does not rejoin asynchronous downstream work into the old transaction.

## 9. Callbacks do not replace idempotency or outbox

Suppose a business rule requires "write the order to the DB, then emit the OrderCreated event." If the event is emitted in the handler **before commit**, there is a risk the event reaches consumers while the DB has not committed yet or ultimately rolls back.

If the event is emitted in **afterCommit**, premature emission is avoided, yet risks remain:

~~~text
T0: DB commit succeeds.
T1: Application crashes before afterCommit sends the event.
T2: DB has the order, but the event was never emitted.
~~~

Another case:

~~~text
T0: DB commit succeeds.
T1: afterCommit sends the event to the broker.
T2: Broker receives the event; response is lost.
T3: Callback reports failure or application restarts; replay may send the event again.
~~~

Therefore, **afterCommit is a timing callback**, not an exactly-once guarantee between DB and broker. When the event is mandatory, consider a **transactional outbox**:

~~~mermaid
flowchart LR
    H["Handler"] --> DB[("DB transaction<br/>Order + OutboxEvent")]
    DB -->|commit| W["Outbox publisher"]
    W --> Q["Broker"]
    Q --> C["Idempotent consumer"]
~~~

The outbox event is written **in the same DB transaction** as the order; the publisher reads and republishes as needed. Consumers must have duplicate-handling mechanisms. You can still use TransactionSynchronizationFactory to **wake the publisher after commit** to reduce latency, while the outbox/polling guarantees delivery even if the callback is lost.

### Moving files also requires idempotency

With a file inbound adapter:

- Derive a stable business key from **file ID/checksum + source**, or from an ID inside the payload.
- Configure a file filter and persist processed state appropriately across restarts.
- If moving the file in afterCommit fails, the DB may already have committed; the next poll must not create the same order again.
- If afterRollback moves the file to failed, there must be a recovery/quarantine workflow and safeguards against infinite retries.
- If the file moved yet the process died before writing audit state, there must be a way to **reconcile directories and the DB**.

## 10. Retry, error handling, and correlation

TransactionSynchronizationFactory observes **the outcome of the transaction wrapping the poll run**; it does not define retry policy itself. When a flow involves **RequestHandlerRetryAdvice**, broker redelivery, and transaction rollback, examine which layer is retrying.

Example where a handler fails twice and succeeds on the third attempt:

~~~text
Poll message A (requestId=O-42)
  → RetryAdvice: attempt 1 throws
  → RetryAdvice: attempt 2 throws
  → RetryAdvice: attempt 3 succeeds
  → transaction commit
  → afterCommit runs for the transaction
~~~

Conversely, if retries are exhausted and an exception is thrown:

~~~text
Poll message A
  → retry exhausted
  → transaction rollback
  → afterRollback runs
  → source may redeliver per receive/ack/adapter policy
~~~

**Pitfalls to avoid:**

1. Handler **catches the exception and only logs** → flow appears successful; transaction may commit and **afterCommit** is called even though business logic failed.
2. Recovery callback **swallows the exception** after retries are exhausted → outer transaction may commit if not marked rollback-only; model the recovery outcome explicitly.
3. Retry placed **inside a transaction already marked rollback-only** → subsequent attempts may fail even if logic succeeds; review retry/transaction advice ordering.
4. Transaction commits at the poller before async downstream finishes → **afterCommit does not mean async business work is done**.
5. afterRollback sends a message directly to a non-idempotent system → when rollbacks recur, notifications or side effects may also repeat.

To trace failures, preserve **correlationId**, **requestId/idempotency key**, business key, and message source metadata. For callbacks evaluated against the original message, only headers **present at poll time** are accessible as part of the original message; data produced in downstream handlers should be persisted to a store or durable event by design, rather than assuming callbacks automatically see every transformed payload.

## 11. MessageStore, restarts, and IntegrationFlow lifecycle

A transaction synchronization is typically registered **in memory on the thread/process handling the transaction**. It is not a durable queue that recovers itself after a crash. Hence:

- Application dies **before commit**: the DB transaction typically rolls back per resource/connection semantics; Java callbacks in the dead process **never get to run**.
- Application dies **after commit** but **before/during callback**: the DB has committed, yet callback state may not have been recorded or side effects executed only partially.
- A persistent **MessageStore** can preserve messages/aggregator groups across restarts, but by default it does not save or replay missed callbacks.
- Stopping/starting an **IntegrationFlow** changes consumer/poller lifecycle; in-flight messages and incomplete transactions must be evaluated under timeouts, shutdown, and the transaction manager.
- When multiple instances poll the same source, account for **locking/claim-check**, duplicates, atomic reads, ordering, and coordinated state; synchronization in one JVM cannot lock a source in another JVM.

For recovery requirements, identify the **source of truth**: DB/outbox, durable message store, broker, or reconcilable file state. The callback is only one step in that workflow.

## 12. Diagnosing when beforeCommit/afterCommit/afterRollback does not behave as expected

A sequential investigation checklist:

| Symptom | Diagnostic questions |
| --- | --- |
| No callback runs | Does the poller have transaction advice and the right factory? Did MessageSource return a message in this poll run? |
| afterCommit runs even though handler failed | Did the handler catch and drop the exception, did recovery return normally, or did the error happen **after an async boundary**? |
| afterRollback does not run | Did the transaction actually roll back, or was the exception converted into a normal return? Did the error happen outside the transaction? |
| afterCommit does not send a message | Did SpEL return **null/void**? Is the channel declared and does a subscriber exist? |
| Channel receives an unexpected payload type | Did the expression return **Boolean**, **File**, or another object; what type does the consumer expect? |
| Event lost despite DB commit | Did the app crash between commit and callback? Is there an outbox or durable audit? |
| Error lacks correlation | Did the polled message have a correlationId? Did SpEL/handler create a new message dropping headers? |
| Loops even after retries exhaust | Does the broker/poller have separate redelivery? Did afterRollback move the file or does the source keep re-ingesting it? |
| Thread exhaustion or throughput drop | Is the callback performing slow I/O on the poller thread? Is it awaiting HTTP or holding long locks? |

### Minimal observability

Include these fields in logs/traces:

~~~text
flow=orderImport
endpoint=orderFileInbound
requestId=O-42
correlationId=import-batch-2026-11
thread=order-poller-1
transactionPhase=AFTER_COMMIT
businessOutcome=COMPLETED
callbackOutcome=FILE_MOVE_FAILED
~~~

Distinguish **businessOutcome**, **transactionOutcome**, and **callbackOutcome**. For example, DB commit succeeding while moving the file fails is a post-commit post-processing failure, and should not be lumped together as "DB rollback."

Useful metrics:

- Poll count, messages received, empty polls, transaction commits/rollbacks.
- Callbacks per phase, callback latency, callback failures, and events needing reconciliation.
- Queue size, executor saturation, poller duration, and transaction latency.
- Messages missing requestId/correlationId, unmoved files, DLQ/quarantine backlog.
- Duplicate messages or outbox events not yet confirmed by the publisher.

## 13. Testing transaction synchronization behavior

When testing, use a **transaction manager matching the resource under test**; tests with H2/JDBC differ from tests using only files/FTP. Avoid drawing conclusions from calling processor methods directly — that only tests the handler, **not the real transaction lifecycle**.

### A. Happy path: commit

1. Have the poller receive a message with a fixed requestId.
2. Have the handler execute a DB insert/update inside the open transaction.
3. Wait for the transaction to finish and verify the DB **committed**.
4. Verify **afterCommit** receives the original message with the right requestId; **afterRollback** does not receive it.
5. If the callback moves a file, verify the file actually exists in the target directory; do not check only that the expression was evaluated.

### B. Failure path: rollback

1. Make the handler intentionally throw a **RuntimeException** after the DB update.
2. Verify the DB rolls back, **afterRollback** is invoked, and afterCommit does not run.
3. Verify correlation/requestId remain sufficient to trace the failed message.
4. Check whether the poller source redelivers the message and whether that matches operational expectations.

### C. beforeCommit failure

Have **beforeCommit** throw an exception during condition validation. Verify the transaction rolls back per policy and afterCommit does not run. Verify external side effects were not executed before commit.

### D. afterCommit failure

Have the afterCommit handler/channel throw an exception or have the file move return false. Verify the DB **still committed** and the system has a **detection/recovery mechanism for post-processing**. Do not write a test expecting the DB to roll back after commit has already completed.

### E. Async boundary

Insert an **ExecutorChannel** before a downstream handler that can fail. Verify the poller's callback is based on the **synchronous handoff** result, not on the late async processing outcome. If the business requires success after async work, design a separate state-recording/transaction point on the consumer.

### F. Crash/restart

Simulate interrupting the process between DB commit and the post-processing step (via an appropriate integration testing mechanism). Verify the restarted process can **reconcile and complete** using the outbox/audit/source data, rather than expecting the old callback to run again.

## 14. Practice exercise: designing a reliable order import flow

**Problem statement:** Every minute, poll 100 order files, write to the DB, move processed files, and emit events to a downstream system. Files occasionally contain invalid JSON; the system runs two application instances in parallel and may restart during new version deployments.

**Minimum design considerations:**

1. **Inbound/poller:** Filter/locking to prevent two instances from processing the same file; define poller task count, timeout, and transaction policy.
2. **Handler:** Validate the message, insert the order by **unique business key**, throw exceptions on real failures; preserve requestId/correlationId.
3. **DB transaction:** Insert the order and write an **outbox event** in the same transaction; clearly define rollback rules.
4. **Synchronization:** afterCommit signals a worker to move the file or wakes the outbox publisher; afterRollback transitions state to quarantine/retry depending on error type.
5. **Recovery:** If the app crashes between DB commit and file move, a worker reconciles DB/files; do not create duplicate orders on reprocessing.
6. **Error handling:** Invalid JSON goes to quarantine; transient DB errors use bounded retry; downstream events have idempotent consumers.
7. **Observability:** Separate DB, outbox, file, and callback states; log correlation end-to-end.

### Two comprehension check questions

**Question 1:** afterCommit sends an HTTP request, which the server receives and then responds with a timeout. Is the DB transaction rolled back?

**Explanation:** **No**, the DB committed before afterCommit ran. You need an idempotency key, status query, or reconciliation because the HTTP request may already have taken effect.

**Question 2:** The poller has a transaction, and a handler behind an ExecutorChannel fails after 5 seconds. Does the poller's afterRollback run automatically because of that error?

**Explanation:** **Not automatically**. Crossing threads broke the poller's transaction boundary; if the handoff succeeded, the poller may commit and invoke afterCommit before the async error surfaces. The downstream consumer needs its own transaction and error handling mechanism.

## 15. Pre-production checklist

- Is there a **real transaction manager** or is **PseudoTransactionManager** being used? Which resources are protected by the transaction?
- Does the transaction start at the **poller** or at the handler? Have the advice chain and rollback rules been tested?
- Is the factory attached to an **active poller**, or only declared as a bean?
- Are the semantics of **beforeCommit, afterCommit, and afterRollback** clearly defined?
- What **File/Boolean/message** does SpEL return? Does the channel have an appropriate consumer and error recording when callbacks fail?
- Does an **ExecutorChannel/QueueChannel** cut the transaction boundary?
- Could a handler swallow exceptions and cause afterCommit to run contrary to business intent?
- Are **failedMessage, correlationId, and requestId** preserved on the error path?
- Could multi-layer retry/redelivery cause duplicates, and is the idempotency key stable across attempts?
- Is the **DB commit → callback → event/file move** gap handled via an outbox, audit, or durable reconciliation?
- Across stop/restart/multiple instances, are in-flight files, message stores, and missed callbacks accounted for?
- Have commit, rollback, beforeCommit failure, afterCommit failure, async boundary, crash/restart, and duplicate cases been tested?

## Conclusion

**TransactionSynchronizationFactory** is Spring Integration's mechanism for coordinating actions **according to the transaction outcome when polling messages**. It creates synchronizations and can use **ExpressionEvaluatingTransactionSynchronizationProcessor** to run SpEL and send messages during **beforeCommit**, **afterCommit**, and **afterRollback**. This mechanism helps separate primary processing from post-processing, preserve message context for diagnostics, and support flows combining a DB with non-transactional sources.

To use it properly at runtime, you must examine the entire **thread boundary, transaction manager, retry/recovery, message store, error flow, and correlation**. Synchronization does not turn files, HTTP, and brokers into a single transaction and does not by itself guarantee callbacks survive crashes. For operations that must reliably occur after commit, combine a durable source of truth, idempotency, and outbox/reconciliation rather than relying solely on callbacks.

## References

- [Spring Integration Reference — Transaction Support and Transaction Synchronization](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration API — DefaultTransactionSynchronizationFactory](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/DefaultTransactionSynchronizationFactory.html)
- [Spring Integration API — ExpressionEvaluatingTransactionSynchronizationProcessor](https://docs.spring.io/spring-integration/docs/6.4.6/api/org/springframework/integration/transaction/ExpressionEvaluatingTransactionSynchronizationProcessor.html)
- [Spring Integration API — IntegrationResourceHolder](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/IntegrationResourceHolder.html)
- [Spring Integration API — TransactionSynchronizationFactoryBean](https://www.springframework.org/spring-integration/docs/6.4.x/api/org/springframework/integration/transaction/TransactionSynchronizationFactoryBean.html)
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
