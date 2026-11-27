# TransactionSynchronizationFactory

**Chapter:** Transactions  
**Lesson:** TransactionSynchronizationFactory  
**Module:** Spring Integration Adapters (`SPRING_INTEGRATION_ADAPTERS`)  
**Language:** English  
**Context:** Integrating external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; covers File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC processing, focusing on message contracts, errors, transactions, resources, and connection lifecycles.

> **Key Takeaway:** `TransactionSynchronizationFactory` connects the **transaction lifecycle** to **outcome-dependent actions** in a polling flow: what to do before commit, after commit, and after rollback. It **does not** turn file, HTTP, SFTP, or external broker publish operations into part of a database transaction. Achieving reliability requires understanding transaction boundaries, messages bound to transactions, callback failures, retries, and reconciliation capabilities.

## 1. The Problem: Moving a File Only After Processing Completes

Suppose an application uses a **File inbound channel adapter** to read CSV files from an `inbox/` directory, a parser creates Spring Messages, a service activator writes data to JDBC, and then the file needs to be moved:

- **DB write commits successfully:** Move the file to `processed/`.
- **DB rolls back due to error:** Move the file to `failed/` or keep it at the source per retry policy.
- **In progress:** Prevent another poller from picking up the same file.

A naive implementation:

~~~text
read file
insert database rows
move file to processed/
commit database
~~~

This approach can **move the file successfully while the DB commit fails**. On the next poll, the file is no longer in `inbox/`, causing the business operation to be silently lost.

We want to attach the move action to the **transaction outcome**:

~~~mermaid
flowchart TD
    POLL["File inbound poller"] --> TX["Begin JDBC transaction"]
    TX --> READ["Receive File message"]
    READ --> DB["Parse + update database"]
    DB --> DEC{"Transaction outcome?"}
    DEC -->|Commit success| AC["afterCommit: move to processed / publish audit"]
    DEC -->|Rollback| AR["afterRollback: move to failed / keep for retry"]
    AC --> VERIFY["Verify move result and audit log"]
    AR --> VERIFY
~~~

In Spring Integration, **`TransactionSynchronizationFactory`** is a mechanism to register such callbacks against the **poller's transaction**. However, you must distinguish **DB transaction committed** from **file move succeeded**. If the file move fails inside `afterCommit`, the DB cannot automatically roll back.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of `TransactionSynchronizationFactory`, `TransactionSynchronization`, `TransactionSynchronizationProcessor`, and `IntegrationResourceHolder`.
2. Distinguish `beforeCommit`, `afterCommit`, and `afterRollback`, along with the consequences when a callback throws an exception.
3. Use `DefaultTransactionSynchronizationFactory` together with `ExpressionEvaluatingTransactionSynchronizationProcessor` in Java/XML examples.
4. Configure synchronization on a **transactional poller**, understanding `TransactionInterceptor` and `PseudoTransactionManager`.
5. Identify transaction break points across `ExecutorChannel`, `QueueChannel`, another thread, or external APIs.
6. Design file/archive, SFTP, JDBC, HTTP, and broker adapters without making false atomicity promises.
7. Test crash windows, retries, idempotency, callback failures, resource cleanup, and operations.

## 2. Where TransactionSynchronizationFactory Fits in Spring Integration

Spring Integration structures flows around **Message**, **MessageChannel**, **MessageHandler**, and **MessageSource**. A poller pulls a message from `MessageSource.receive()`, sends it into a channel, and invokes downstream handlers.

Spring Framework provides a transaction manager and `TransactionSynchronizationManager` to manage synchronizations bound to the current transaction/thread. Spring Integration leverages that mechanism to associate the **newly polled message** with callbacks.

~~~mermaid
flowchart LR
    SRC["MessageSource/File/JDBC"] --> POLLER["SourcePollingChannelAdapter / poller"]
    POLLER --> INT["TransactionInterceptor"]
    INT --> CH["DirectChannel"]
    CH --> H["Service Activator / JDBC handler"]
    INT --> TSF["TransactionSynchronizationFactory"]
    TSF --> SYNC["TransactionSynchronization"]
    SYNC --> BEFORE["beforeCommit"]
    SYNC --> AFTER["afterCommit"]
    SYNC --> ROLLBACK["afterRollback"]
~~~

**Clarification:** `TransactionSynchronizationFactory` does not invoke the poller, does not start a transaction on its own, and is not the `@Transactional` annotation. It creates synchronization when the polling endpoint is already configured with appropriate transaction advice.

### 2.1. Foundational Components

| Component | Responsibility | What it does NOT guarantee |
| --- | --- | --- |
| `PlatformTransactionManager` | Starts/commits/rolls back transactions managed by this manager | Does not bundle all external systems into one transaction |
| `TransactionInterceptor` | Applies transaction advice to a poll task or method | Does not preserve the transaction across another thread |
| `TransactionSynchronizationFactory` | Creates `TransactionSynchronization` for a specific key/resource | Does not determine whether DB or file operations succeeded |
| `DefaultTransactionSynchronizationFactory` | Default factory accepting a processor and creating synchronization | Does not include business-specific actions by default |
| `TransactionSynchronizationProcessor` | Runs logic before commit, after commit, and after rollback | Does not make file/SFTP/HTTP actions transactional |
| `ExpressionEvaluatingTransactionSynchronizationProcessor` | Evaluates SpEL / sends results to a channel per phase | Does not guarantee an expression's side effect succeeds |
| `IntegrationResourceHolder` | Holds the message and resources/metadata bound to the transaction | Is not a persistent failure store |
| `PassThroughTransactionSynchronizationFactory` | Binds the polled message into context to aid error reporting | Does not perform business compensations |
| `PseudoTransactionManager` | Emits success/failure signals for synchronization when no real transactional resource exists | Does not roll back files or remote requests |

### 2.2. When to Use It?

Suitable when:

- Polling a file, writing to DB; **afterCommit** moves the processed file.
- Polling JDBC, synchronizing state/metrics based on the transaction outcome.
- Calling FTP/SFTP outside a transaction and wanting to **branch post-processing actions** according to the synchronous flow's success/failure.
- Routing a message to a designed recovery/quarantine path after rollback.
- Preserving the original message in error reports when poller transaction advice throws an error.

Should NOT be used as the sole solution for:

- **Cross-system exactly-once across DB and Kafka/RabbitMQ/HTTP**.
- Distributed transactions spanning heterogeneous brokers.
- Callbacks that must be guaranteed to run after the process is killed/crashed.
- Durable retries lasting hours across restarts.
- Business compensation for operations already committed on a remote API.

Those scenarios additionally require **idempotency, outbox/inbox, persistent state, retry queues, and reconciliation**.

## 3. Core API Contracts

The primary interface looks like:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;

public interface TransactionSynchronizationFactory {
    TransactionSynchronization create(Object key);
}
~~~

`key` is the object used by the transaction synchronization mechanism to bind the resource; do not assume `key` is always the payload or business ID. Spring Message details are accessed via `IntegrationResourceHolder` inside the processor.

`TransactionSynchronizationProcessor` exposes three hooks:

~~~java
public interface TransactionSynchronizationProcessor {
    void processBeforeCommit(IntegrationResourceHolder holder);
    void processAfterCommit(IntegrationResourceHolder holder);
    void processAfterRollback(IntegrationResourceHolder holder);
}
~~~

This is an **abbreviated interface description** for learning the API. In actual implementations, imports come from `org.springframework.integration.transaction`, while `TransactionSynchronization` belongs to Spring Framework.

### 3.1. Factory → Synchronization → Processor Relationship

~~~mermaid
sequenceDiagram
    participant P as Poller + TransactionInterceptor
    participant F as TransactionSynchronizationFactory
    participant S as TransactionSynchronization
    participant X as TransactionSynchronizationProcessor
    participant D as JDBC/DataSource
    P->>F: create(key)
    F-->>P: synchronization
    P->>S: register / bind resource
    P->>D: poll + handler updates
    alt Commit
        P->>S: beforeCommit
        S->>X: processBeforeCommit(holder)
        P->>D: commit
        P->>S: afterCommit
        S->>X: processAfterCommit(holder)
    else Rollback
        P->>D: rollback
        P->>S: afterCompletion(rolled back)
        S->>X: processAfterRollback(holder)
    end
    P->>S: completion / cleanup
~~~

The diagram shows the logical sequence. Details of `beforeCompletion`/`afterCompletion` callbacks and Spring Framework's transaction lifecycle binding are managed by the framework; do not write custom code assuming a specific ordering among synchronizations with the same order without verifying.

### 3.2. DefaultTransactionSynchronizationFactory

This is the standard implementation: it takes a `TransactionSynchronizationProcessor` and creates a synchronization that invokes the processor per phase.

~~~java
TransactionSynchronizationProcessor processor = /* application-configured */;
TransactionSynchronizationFactory factory =
        new DefaultTransactionSynchronizationFactory(processor);
~~~

With the default option, resource synchronization follows Spring Integration's cleanup/unbind mechanism. If you write a custom factory and synchronization, **the implementer is responsible for properly unbinding resources when the transaction completes** to avoid memory leaks or leaking the previous poll's message context into the next poll.

### 3.3. IntegrationResourceHolder

`IntegrationResourceHolder` holds the polled Spring Message along with attributes placed into the transaction context by the source/framework.

~~~java
// Inside a custom TransactionSynchronizationProcessor:
Message<?> originalMessage = holder.getMessage(); // may be null depending on context
Map<String, Object> attributes = holder.getAttributes();
~~~

Do not confuse the holder with a persistent `MessageStore`. The holder serves **the current thread's transaction context**; once the transaction ends, it must be cleaned up properly.

## 4. Three Phases: Before Commit, After Commit, After Rollback

| Phase | Timing | Suitable for | Risk to test |
| --- | --- | --- | --- |
| **beforeCommit** | Before the resource transaction is committed | Validate final invariants; detect errors to trigger rollback | External side effects already performed are not auto-undone |
| **afterCommit** | After the DB/transaction manager reports commit success | Archive files, publish best-effort audit/signals, schedule post-commit jobs | Callback failure **does not reverse the commit** |
| **afterRollback** | After rollback is confirmed via completion | Quarantine/mark failed, alert, prepare retry | This action can also fail; do not assume file rollback occurred |

### 4.1. beforeCommit vs. afterCommit

**`beforeCommit`** is still within the lifecycle window where the transaction can be rolled back if the callback throws an appropriate exception. It is useful for validating **invariants** right before completion.

**`afterCommit`** executes after the DB transaction has already committed. If a file-move callback fails, **you cannot turn the just-committed JDBC transaction into a rollback** merely by throwing an exception from the callback. You need compensating actions or retries from a failure state.

### 4.2. afterRollback Is Not a Filesystem Rollback

When the DB transaction rolls back, an `afterRollback` callback may execute `Files.move(...)` or publish an error message. Those actions themselves **do not participate in a corresponding filesystem rollback**.

If moving the file to `failed/` fails, the application must log/alert and maintain a clear retry path. With an accept-once source filter or SFTP download metadata, a JDBC rollback **does not guarantee** the filter/source allows the file to be read again.

### 4.3. Do Callbacks Always Run If the Process Is Killed?

No. If the JVM receives `kill -9`, the host crashes, the pod terminates abruptly, or power fails, in-memory callbacks that have not yet run **may never execute**.

~~~text
JDBC COMMIT succeeds
   |
   +-- JVM crashes before afterCommit(file.move)
   |
   +-- File remains in inbox, DB already has data.
~~~

Therefore, **startup reconciliation**, idempotent file handling, and database evidence are necessary. For critical workflows, never rely on a post-commit callback as the **sole mechanism** for mandatory work.

## 5. Transaction Boundaries: Threads Determine Scope

In Spring Framework, the transaction context is typically bound to the **executing thread**. A polling flow using a same-thread `DirectChannel` allows multiple handlers to share the same transaction when using a compatible transaction manager and resource.

~~~text
Poller thread:
  TransactionInterceptor begins
    MessageSource.receive()
    DirectChannel.send(message)
      transformer
      service activator
      JDBC update
  beforeCommit
  JDBC commit
  afterCommit
~~~

### 5.1. ExecutorChannel Breaks the Boundary

~~~text
Thread A (poller transaction):
    MessageSource.receive()
    ExecutorChannel.send(message)
    send() returns after scheduling
    JDBC transaction A commits
    afterCommit runs

Thread B (worker):
    handler starts later
    JDBC update throws
~~~

`afterCommit` on thread A may have already moved the file to `processed/` while the handler on thread B has not even finished. This is an **architectural bug**, not the callback "running early."

### 5.2. Boundaries to Mark on Your Diagram

| Mechanism | Does the transaction propagate automatically? |
| --- | --- |
| Synchronous `DirectChannel` | Typically preserves same-thread transaction context |
| `ExecutorChannel` | **Does not** automatically propagate thread-local transactions |
| `QueueChannel` with a downstream polling consumer | Establishes a new boundary; needs its own transaction/handoff |
| Scheduled/async task `@Async` | Separate transaction if declared |
| JMS/AMQP/Kafka outbound publish | DB transaction does not automatically encompass the broker |
| HTTP/SFTP outbound | Does not automatically roll back with JDBC |
| Reactive flow | Relies on reactive transaction context/manager, not inferred from traditional thread-locals |

**Rule of thumb:** Draw a boundary whenever a message is handed off to another thread or resource. Only attach `afterCommit` actions to work **truly inside the monitored transaction**.

### 5.3. Timeouts and Long-Running Transactions

Placing a 30-second HTTP call inside a handler on the poller thread holds the DB transaction, connection, and locks for the entire wait. When downstream services are frequently slow, consider splitting:

1. Short DB transaction to claim input and write an outbox row.
2. Commit with durable state.
3. Outbound worker sends HTTP/Kafka independently.
4. Use retries/idempotency/reconciliation rather than holding long JDBC transactions.

## 6. XML: Standard Synchronization Configuration Example

Spring Integration supports XML namespace elements for poller transaction synchronization. This example illustrates polling a file, processing synchronously, and branching on transaction outcome:

~~~xml
<!-- Configuration snippet only: real applications need namespaces, beans,
     file filters, database transaction manager, and channels. -->
<int-file:inbound-channel-adapter
        id="inputDirPoller"
        channel="processFileChannel"
        directory="/var/app/inbox"
        filter="fileFilter">
    <int:poller fixed-rate="5000" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"
                synchronization-factory="fileSyncFactory" />
    </int:poller>
</int-file:inbound-channel-adapter>

<int:transaction-synchronization-factory id="fileSyncFactory">
    <int:after-commit
            expression="payload.renameTo(new java.io.File('/var/app/processed/' + payload.name))"
            channel="fileCommitResultChannel" />
    <int:after-rollback
            expression="payload.renameTo(new java.io.File('/var/app/failed/' + payload.name))"
            channel="fileRollbackResultChannel" />
</int:transaction-synchronization-factory>
~~~

**Important note about expression results:** `java.io.File.renameTo()` returns a **Boolean**. When configuring both `expression` and `channel`, the channel receives the **expression result** as its payload, not the original `File` by default. `Boolean.FALSE` means the rename **failed**, yet **no exception** may be thrown.

### 6.1. Why Isn't This XML Snippet Production-Ready?

It does not address:

- Cross-filesystem moves, existing destinations, permissions, or path traversal.
- Files polled concurrently by multiple instances, accept-once metadata, and file locks.
- On rollback, whether a file moved to `failed/` still has an approved retry path.
- If `afterCommit` never runs due to a crash, whether a reconciliation job checks file/DB state.
- If a file holds multiple records, when the entire file is truly complete.
- Where a `false` rename result is alerted or recorded as a failure.
- DB idempotency when re-reading a file containing duplicate records.

### 6.2. Want to Send the Original Message Instead of Boolean?

Per the expression processor's semantics, if you configure only **`channel`** without an expression, the received message can be forwarded to that channel; if you use the expression `payload`, it evaluates to the original payload rather than the rename result.

~~~xml
<int:transaction-synchronization-factory id="auditSyncFactory">
    <int:after-commit channel="afterCommitAuditChannel" />
    <int:after-rollback channel="afterRollbackAuditChannel" />
</int:transaction-synchronization-factory>
~~~

This is an **independent configuration option**. Do not assume a `Boolean` produced by rename is the original Spring Message in the consumer; verify actual payload types and headers with tests.

### 6.3. before-commit

~~~xml
<int:transaction-synchronization-factory id="validatedSyncFactory">
    <int:before-commit
            expression="@fileAuditValidator.validate(payload)"
            channel="beforeCommitAuditChannel" />
    <int:after-commit channel="committedChannel" />
    <int:after-rollback channel="rolledBackChannel" />
</int:transaction-synchronization-factory>
~~~

`fileAuditValidator` is an **application-defined** bean. If validation must guarantee a rollback, the bean should **throw an exception** when invalid, rather than returning `false` and hoping the framework rolls back automatically. Do not use `beforeCommit` to call an API with undoable side effects unless the business accepts that risk.

## 7. Java Config: Creating the Factory with a Processor

You can configure `DefaultTransactionSynchronizationFactory` and `ExpressionEvaluatingTransactionSynchronizationProcessor` programmatically in Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.ExpressionEvaluatingTransactionSynchronizationProcessor;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;
import org.springframework.messaging.MessageChannel;

@Configuration
class FileSynchronizationConfig {

    @Bean
    TransactionSynchronizationFactory fileSyncFactory(
            MessageChannel afterCommitFileChannel,
            MessageChannel afterRollbackFileChannel) {

        var parser = new SpelExpressionParser();
        var processor =
                new ExpressionEvaluatingTransactionSynchronizationProcessor();

        // Expression uses the original Message as evaluation root.
        processor.setAfterCommitExpression(
                parser.parseExpression("payload"));
        processor.setAfterCommitChannel(afterCommitFileChannel);

        processor.setAfterRollbackExpression(
                parser.parseExpression("payload"));
        processor.setAfterRollbackChannel(afterRollbackFileChannel);

        return new DefaultTransactionSynchronizationFactory(processor);
    }
}
~~~

Defining the factory/processor beans **does not automatically attach them to a poller**. You must configure the transactional poller to use this factory, such as via `synchronization-factory` in XML or the corresponding Java DSL/endpoint API for your project's **Spring Integration version**.

`afterCommitFileChannel` and `afterRollbackFileChannel` must be **valid MessageChannel beans** with consumers. Parameter injection may require `@Qualifier` if multiple beans of the same type exist in the context.

### 7.1. Dispatch Actions via Channel Instead of Side Effects in SpEL

A more testable strategy:

~~~text
Transaction callback
  -> publish original File message to afterCommitFileChannel
  -> FileLifecycleHandler
  -> Files.move(verifiedSource, verifiedDestination)
  -> persist file move outcome + metrics
~~~

However, an **in-memory** `MessageChannel` still provides no durability for the callback. If moving the file is mandatory, after the JDBC commit you need a **durable post-commit work record** or startup reconciliation so nothing is missed.

### 7.2. Side Effects in SpEL Are Not a Good Default

The expression `payload.renameTo(...)` is concise for demonstrations. In large applications:

- Business rules and path validation should live in a unit-tested service.
- Every move must verify its outcome, not just log "afterCommit called".
- File operations should use `java.nio.file.Files.move` with explicit error handling and atomic-move/cross-filesystem strategies.
- The service may write a failure record, but a post-commit action failure record must **not pretend to belong to the already-completed DB transaction**.

## 8. Custom Processor: Controlling Callbacks in Java

`ExpressionEvaluatingTransactionSynchronizationProcessor` suits simple SpEL tasks. When you need business rules, structured logging, idempotency, file path validation, or multi-branch state transitions, implement `TransactionSynchronizationProcessor`.

### 8.1. Custom Processor Example

~~~java
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.integration.transaction.TransactionSynchronizationProcessor;
import org.springframework.messaging.Message;

final class AuditedFileSynchronizationProcessor
        implements TransactionSynchronizationProcessor {

    private final FileLifecycleService fileLifecycleService;

    AuditedFileSynchronizationProcessor(
            FileLifecycleService fileLifecycleService) {
        this.fileLifecycleService = fileLifecycleService;
    }

    @Override
    public void processBeforeCommit(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.validateBeforeCommit(message);
    }

    @Override
    public void processAfterCommit(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.onDatabaseCommitted(message);
    }

    @Override
    public void processAfterRollback(IntegrationResourceHolder holder) {
        Message<?> message = requireMessage(holder);
        fileLifecycleService.onDatabaseRolledBack(message);
    }

    private static Message<?> requireMessage(IntegrationResourceHolder holder) {
        Message<?> message = holder.getMessage();
        if (message == null) {
            throw new IllegalStateException(
                    "Transaction synchronization message is missing");
        }
        return message;
    }
}
~~~

`FileLifecycleService` is an **application-defined interface/service**; it is not a Spring Integration API. Extracting a service keeps logic testable independent of SpEL and persists post-commit results in a managed place.

### 8.2. Wiring the Processor into the Factory

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.transaction.DefaultTransactionSynchronizationFactory;
import org.springframework.integration.transaction.TransactionSynchronizationFactory;

@Configuration
class CustomSynchronizationConfig {

    @Bean
    TransactionSynchronizationFactory auditedSynchronizationFactory(
            FileLifecycleService fileLifecycleService) {

        return new DefaultTransactionSynchronizationFactory(
                new AuditedFileSynchronizationProcessor(fileLifecycleService));
    }
}
~~~

Swapping the processor is one step; **choosing the transaction manager, configuring the poller, and attaching the factory to the poller** is another. If the poller lacks proper transaction advice, do not expect callbacks to fire.

### 8.3. Service Exception Handling Choices

`validateBeforeCommit` can throw an exception to prevent DB commit. However:

- `onDatabaseCommitted` throwing an exception **does not reverse the DB commit**.
- `onDatabaseRolledBack` throwing an exception does not trigger a second rollback; it can mask the original cause if uncontrolled.
- If a callback side effect fails, record an independent signal/error and use a recovery retry mechanism.
- Do not use `catch (Exception ignored)` for a step the business requires to complete.

Callback limitations also apply to custom processors: **a crash before the hook executes means the hook may never run**.

## 9. Implementing a Custom TransactionSynchronizationFactory: When Is It Needed?

The factory interface defines:

~~~java
TransactionSynchronization create(Object key);
~~~

In most situations, **`DefaultTransactionSynchronizationFactory` + a processor** is sufficient. Writing a custom factory should only be considered if you need specialized synchronization that the default framework cannot meet, such as a highly specific source resource lifecycle.

### 9.1. Additional Responsibilities of a Custom Factory

1. Create the proper `TransactionSynchronization` for the given key/resource.
2. Bind, retrieve, and unbind `IntegrationResourceHolder` at the right times.
3. Perform cleanup on commit, rollback, exception, and completion.
4. Avoid sharing mutable holders across polling threads.
5. Do not leak messages, payloads, or connections via `ThreadLocal`.
6. Respect callback ordering and transaction completion semantics.
7. Do not alter the business outcome by swallowing an exception that requires rollback.
8. Write tests for concurrent pollers and restart/error scenarios.

### 9.2. Why Is Unbinding Critical?

If a custom synchronization forgets to unbind the resource, a pooled thread can be reused for the **next message** while still carrying metadata from the previous message. Consequences can include:

- `afterCommit` moving the wrong file.
- `ErrorMessage` referencing the wrong `failedMessage`.
- Memory leaks from retaining large payloads.
- Tenant A data being logged under tenant B's activity.

The default framework uses resource synchronization with an appropriate `shouldUnbindAtCompletion()` to clean up bound resources. Do not replace the default with custom code without a genuine need and corresponding tests.

## 10. Poller Transactions vs. `@Transactional`

Spring Integration has multiple flow entry points:

- **User-initiated:** Controller calls a gateway, or service calls `channel.send()`.
- **Daemon-initiated:** Scheduler or **poller** periodically calls `MessageSource.receive()`.
- **Message-driven adapter:** Broker/listener enters the flow upon delivery.

For user-initiated flows, a Spring service with `@Transactional` can define the DB transaction boundary. For pollers, the **polling task** is not already wrapped in a transaction by an external caller; Spring Integration allows attaching transaction advice to the poller so even `receive()` is wrapped (when the source is a transactional resource).

### 10.1. Poller Transactions vs. Handler `@Transactional`

| Criterion | Poller transaction | `@Transactional` on handler |
| --- | --- | --- |
| Starts | Before/wrapping the poll task | When the proxy invokes the method |
| Wraps `receive()`? | Can wrap it | Usually **no** |
| Binds message source metadata | Poller/synchronization mechanism | Not automatically present |
| Multiple handlers on same thread | Can share the same transaction | Depends on propagation and proxies |
| Thread switch | Boundary ends at handoff | Context does not follow automatically |
| File/SFTP rollback | Not automatically transactional | Also not automatically transactional |

### 10.2. Avoid Blindly Nesting Transactions

If the poller uses `DataSourceTransactionManager` and a handler invokes a service annotated with `@Transactional(propagation = REQUIRES_NEW)`, that service can commit a **separate** transaction. When the poller transaction later rolls back, records committed in the inner transaction may remain persisted.

Therefore, **poller `afterRollback` does not mean all downstream DB writes rolled back** if a handler opened a new transaction or used a different datasource/manager.

### 10.3. Transaction Advice Inside an Advice Chain

When adding extra advice (rate-limit, retry, metrics), Spring Integration supports `<advice-chain>` with transaction advice on the poller. **Advice order** determines which parts are wrapped in the transaction and which outcome callbacks observe.

~~~text
TX advice wrapping Retry advice:
    one transaction may span all attempts;
    one error may mark it rollback-only.

Retry advice wrapping TX advice:
    each attempt can have its own transaction.
~~~

This illustrates the **typical semantics of advice nesting**, not a claim that all configurations behave identically. Specifically with JDBC, a transaction marked rollback-only cannot be "healed" simply by retrying inside the same transaction. Test the actual ordering and watch for `UnexpectedRollbackException`.

## 11. PseudoTransactionManager: Signals Without Resource Rollback

Spring Integration provides `PseudoTransactionManager` for cases where **no real transactional resource exists**, yet you still want callbacks tied to flow outcomes.

Example:

~~~text
File inbound -> validate -> SFTP outbound
    Success: move local file to sent/
    Failure: move local file to retry/ or failed/
~~~

The local filesystem and SFTP server do not natively participate in a JDBC transaction; `PseudoTransactionManager` provides a **begin/success/failure** model to drive hooks.

### 11.1. Illustrative XML Bean

~~~xml
<bean id="pseudoTransactionManager"
      class="org.springframework.integration.transaction.PseudoTransactionManager" />

<int-file:inbound-channel-adapter
        id="filesForUpload"
        directory="/var/app/to-send"
        channel="uploadChannel">
    <int:poller fixed-delay="1000">
        <int:transactional
                transaction-manager="pseudoTransactionManager"
                synchronization-factory="fileSyncFactory" />
    </int:poller>
</int-file:inbound-channel-adapter>
~~~

### 11.2. What a Pseudo Transaction Actually Means

| Event | What does PseudoTransactionManager do? |
| --- | --- |
| Synchronous flow returns normally | Delivers lifecycle signal for commit callbacks |
| Synchronous flow throws matching rollback rules | Delivers lifecycle signal for rollback callbacks |
| SFTP upload succeeded, then another callback fails | **Does not** undo the upload |
| JVM crashes during upload | No guaranteed automatic rollback/cleanup |
| Network timeout after remote success | Unknown whether remote server wrote the file |

**Do not** claim "we used pseudo transactions so File/SFTP/HTTP are as safe as JDBC." A pseudo transaction is a **callback synchronization mechanism**, not XA or a transactional filesystem.

### 11.3. Complementary Solutions for File Transfers

- Upload files to a **temporary remote name**, then rename once transfer completes and checksum/naming conventions pass.
- Use a stable transfer ID to detect duplicate uploads after timeouts.
- Persist a durable **transfer manifest** or job state for restart reconciliation.
- Archive the local source only when upload evidence meets the contract.
- Manage temp-file cleanup and remote file lifecycles separately.

Do not rely solely on `afterCommit` to confirm a remote file is complete; verify against API/protocol guarantees and operational behavior.

## 12. PassThroughTransactionSynchronizationFactory

Since Spring Integration 5.0, when a polling endpoint has a `TransactionInterceptor` in its advice chain without an explicit `TransactionSynchronizationFactory`, the framework can automatically apply `PassThroughTransactionSynchronizationFactory` to bind the polled message to the transaction context.

### 12.1. What Problem Does It Solve?

When transaction advice throws an exception after a message has been polled, the error flow can receive a `MessagingException` carrying **`failedMessage`**, revealing **which message caused the error**, instead of just a raw exception lacking input context.

~~~text
Poller receives Message M
 -> transaction advice / handler fails
 -> MessagingException with failedMessage=M
 -> ErrorMessage(payload=MessagingException)
 -> errorChannel / failure handler
~~~

Exception/error channel routing depends on the poller's error handler and endpoint configuration; the diagram shows **one possible path supported by the framework**, not that every message goes to the global error channel.

### 12.2. What Does It Not Do?

`PassThroughTransactionSynchronizationFactory` **does not replace** `DefaultTransactionSynchronizationFactory` with custom before/after actions when you need to move files or call an audit service. It primarily serves to **bind resource context**, not to archive or quarantine messages automatically.

### 12.3. What to Test

- When advice includes `TransactionInterceptor`, `failedMessage` is preserved on failure.
- With custom transaction advice **other than** `TransactionInterceptor`, check version documentation to see if explicit pass-through factory setup is needed.
- If an exception occurs before any message is polled, `failedMessage` may be null.
- Never use raw `failedMessage.toString()` to log sensitive data.

## 13. File Inbound: Combining JDBC Transactions and File Lifecycle

This is a flagship use case for transaction synchronization. A file containing order records is polled, the DB is the **primary transactional resource**, and moving the file is a **synchronized side effect**.

### 13.1. File States to Distinguish

~~~text
DISCOVERED
   -> CLAIMED
   -> PARSING
   -> DATABASE_COMMITTING
   -> DATABASE_COMMITTED
   -> ARCHIVE_PENDING
   -> ARCHIVED

On error:
   -> DATABASE_ROLLED_BACK
   -> RETRY_PENDING / QUARANTINED
~~~

`ARCHIVE_PENDING` is useful: it indicates the DB committed while the file may not yet have moved. If the app crashes in this window, a **reconciliation job** using DB evidence and file metadata can complete archiving without creating duplicate business records.

### 13.2. Why Not Move the File Before Commit?

~~~text
T0: FileSource polls file F
T1: parser creates records
T2: JDBC INSERT records
T3: file moved to processed/
T4: JDBC commit fails

Result:
    file is gone from inbox
    data is not committed
    no source to reprocess if recovery is missing
~~~

Using `afterCommit` closes that failure window, yet opens the inverse window:

~~~text
T0: JDBC commit succeeds
T1: JVM crashes
T2: afterCommit file move does not run

Result:
    DB already contains data
    file remains in inbox
    re-polling may generate duplicates
~~~

**Therefore you need both:** well-timed callbacks **and** idempotency/reconciliation.

### 13.3. File.renameTo vs. Files.move

`File.renameTo()` can fail and return `false` without throwing an exception; cross-device behavior depends on the filesystem. In production, `Files.move` with appropriate options enables clearer exception handling.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class SafeFileMover {

    void moveAfterCommit(Path source, Path destination) throws IOException {
        Path normalizedSource = source.toAbsolutePath().normalize();
        Path normalizedDest = destination.toAbsolutePath().normalize();

        // Separate policy must verify trusted root, file owner, and scope.
        Files.createDirectories(normalizedDest.getParent());
        Files.move(normalizedSource, normalizedDest,
                StandardCopyOption.ATOMIC_MOVE);
    }
}
~~~

`ATOMIC_MOVE` can be rejected by the filesystem (`AtomicMoveNotSupportedException`) or behave differently by provider; provide a controlled fallback. **This example only illustrates the API**: production code must guard against path traversal/symlinks, collisions, cross-filesystem moves, existing source/destination checks, and idempotent recovery.

### 13.4. One File Containing Multiple Records

If a splitter emits 100 messages where 99 succeed and 1 fails, the transaction of **one polled File message** may differ from the transaction of **each individual record** after a splitter or thread boundary.

Do not archive the entire file based solely on a single handler's callback. Define explicitly:

- **All-or-nothing file:** Archive only when all 100 records commit within an appropriate transaction/processing boundary.
- **Per-record processing:** Track each record's outcome via key/line ID; archive the file once evidence confirms all records finished or moved to quarantine.
- **Out-of-order processing:** Do not use a simple high-watermark if records can fail and arrive out of order.

## 14. SFTP Inbound and Remote File Lifecycle

SFTP adapters can **download remote files to a local directory** or emit streaming messages depending on the endpoint type. Thus payload types and metadata do not match the `File` inbound adapter in every case.

### 14.1. Do Not Assume the SpEL Payload Is java.io.File

~~~text
File inbound:
    payload may be java.io.File.

SFTP inbound download:
    may receive a local File; remote metadata depends on adapter/headers.

SFTP streaming inbound:
    may receive a stream / session-related resource.
~~~

Copying `payload.renameTo(...)` verbatim from a file adapter into a streaming SFTP handler can produce an **invalid** expression or fail to manage the remote file as intended.

### 14.2. Is Remote Rename/Move Transactional?

Not automatically. `TransactionSynchronizationFactory` can invoke a service performing an SFTP remote rename **after another transaction commits**, but the remote operation is not automatically rolled back if a subsequent step fails.

For example, the remote file was renamed to `archived/` before a DB callback failed, or the rename timed out after the server already executed it. You need remote file IDs, checksums, persisted state, and reconciliation.

### 14.3. Session Lifecycle

SFTP streaming must close/release streams and sessions per the adapter/consumer contract on both success and failure. Never hold a session open across a long JDBC transaction merely waiting for remote file moves.

Test:

1. Does the stream/session close when the handler returns?
2. If the `afterRollback` callback throws an error, is the session still cleaned up?
3. Are duplicate downloads triggered upon restart or filter metadata reset?
4. Are incomplete temporary files left behind after timeouts?
5. Is remote file replay possible if the source has already been deleted/moved?

## 15. JDBC Inbound Polling and Synchronous Transactions

A JDBC inbound adapter typically polls rows using a `SELECT` query and can update status/claim in the same transaction when configured with a matching datasource and transaction manager.

~~~text
Poll JDBC rows (NEW)
  -> claim rows (PROCESSING)
  -> DirectChannel
  -> business validation/upsert
  -> beforeCommit checks
  -> DB commit
  -> afterCommit signal/metrics
~~~

### 15.1. beforeCommit for Invariant Checks

A custom processor can verify conditions are valid right before commit—for instance, ensuring no batch still contains `INVALID` records marked complete. If violated, throw an exception so Spring rolls back the transaction.

Do not abuse `beforeCommit` to make non-rollbackable HTTP POST calls. If the external API succeeds and the DB commit fails, the API **has already executed its side effect**.

### 15.2. Row Claiming and Concurrency

With multiple pollers, **transaction synchronization does not replace database locking or unique constraints**:

- `SELECT ... FOR UPDATE` or database-supported claiming mechanisms.
- Optimistic versioning or `UPDATE ... WHERE status='NEW'`.
- Unique business operation keys to prevent duplicates.
- Leases/timeouts for stuck `PROCESSING` rows.
- Isolation levels matched to actual requirements.

### 15.3. Transaction Status Table Example

~~~sql
-- Illustrative business schema, not a mandatory Spring schema.
CREATE TABLE inbound_jobs (
    job_id           VARCHAR(128) PRIMARY KEY,
    business_key     VARCHAR(240) NOT NULL,
    input_reference  VARCHAR(400) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    processing_owner VARCHAR(120),
    updated_at       TIMESTAMP NOT NULL,
    UNIQUE (business_key)
);
~~~

Suppose a job commits, yet `afterCommit` fails to publish a message; the status table lets you reconcile from **business evidence** instead of guessing whether `afterCommit` finished.

## 16. JMS, AMQP, Kafka: Does the Factory Replace Broker Transactions?

**No.** Poller transaction synchronization does not make JMS, RabbitMQ, or Kafka join a JDBC transaction unless an explicit coordination mechanism is configured and verified.

| Source/Target | Boundary to inspect | Possible role of synchronization |
| --- | --- | --- |
| JMS message-driven inbound | JMS session ACK/rollback, container transaction | Observe/register callbacks if supported by endpoint; does not replace session semantics |
| JMS polling | `receive()` can join a JMS transaction per config | Synchronize secondary actions with the poller's transaction |
| RabbitMQ inbound | ACK/NACK/requeue, listener container transaction | Cannot control broker DLX via callbacks alone |
| RabbitMQ outbound | Publisher confirm/return, routing | `afterCommit` can trigger publish, but post-commit failures need recovery |
| Kafka inbound | Offset commit, ack mode, consumer transaction | Polling endpoint factory does not manage container offsets automatically |
| Kafka outbound | Producer ack/future, Kafka transactions | `afterCommit` triggering send does not mean the record is confirmed |
| JDBC | Local DB commit/rollback per tx manager | Use before/after callbacks bound to the exact DB transaction |

### 16.1. Why Is Publishing to Kafka in afterCommit Error-Prone?

~~~text
JDBC transaction commits
    -> afterCommit calls KafkaTemplate.send(event)
    -> send returns future immediately
    -> callback ends
    -> Kafka publish later fails
~~~

The DB **already committed**, while the Kafka event **does not exist**. Without an outbox, no durable work record remains for retry.

A stronger pattern is writing an **outbox row within the same JDBC transaction**, then having a separate worker publish to Kafka/RabbitMQ and mark `SENT` upon confirmation.

### 16.2. JMS/AMQP Source Acknowledgment

Once an inbound message-driven adapter delivers a message into the flow, the container decides ACK/rollback based on its transaction/config. If a DB `afterCommit` callback fails, do not assume the source broker will redeliver: **DB commit and JMS/Rabbit ACK are separate lifecycles**.

With message-driven adapters, tests should verify the source is actually ACKed/NACKed when the flow and callbacks fail. Do not conclude this from a unit test using only `DirectChannel`.

### 16.3. Kafka Offsets and At-Least-Once

When a consumer succeeds in updating the DB but offset commit fails, Kafka may redeliver the record. Use an **idempotent receiver** or unique constraint on the business key to avoid duplicate side effects.

Conversely, if offsets commit before a durable handoff to the DB/outbox, a crash can lose business events. `TransactionSynchronizationFactory` does not merge two independent commits into a single atomic operation.

## 17. HTTP Inbound/Outbound: What Does afterCommit Mean?

An HTTP API does not join a JDBC transaction merely because it is invoked from a transactional handler. Consider two scenarios:

### 17.1. HTTP Inbound Gateway

An HTTP request arrives, a service opens a JDBC transaction, writes data, and returns an HTTP response. `@Transactional` on the service defines the DB transaction; poller synchronization is **not** the primary mechanism here because HTTP inbound is message-driven/request-driven.

If you want to send the response or emit an event **only after DB commit**, use an appropriate transaction boundary/response contract. Do not apply a poller `TransactionSynchronizationFactory` as a catch-all for HTTP gateways.

### 17.2. HTTP Outbound Inside a Polling Flow

If polling a file → HTTP POST → DB update, the call order and retries can cause duplicates:

~~~text
HTTP POST sent and partner commits
Response times out
JDBC transaction rolls back
afterRollback runs
File is retried
HTTP POST sent again
~~~

**Solution:** Stable idempotency keys, status query/reconciliation with the partner, outbox, or a business state machine. A transaction callback cannot "undo an HTTP POST" already committed on the remote server.

### 17.3. Calling HTTP in beforeCommit?

Usually **not** a good choice for operations with side effects. If the API succeeds before DB commit, the DB transaction may roll back afterward, leaving a mismatch. If the API fails and the callback throws, the DB rolls back, yet you have no guarantee the remote API did not commit.

For critical workflows, **commit local data and an outbox row** first, then send HTTP via a worker with idempotency and retries.

## 18. When Callbacks Fail: Before Commit vs. After Commit

Any synchronization setup must acknowledge that **the callback itself is a failure point**.

### 18.1. beforeCommit Throws an Exception

~~~text
JDBC updates not yet committed
    -> beforeCommit callback validates
    -> callback throws IllegalStateException
    -> transaction rolls back per Spring mechanism
    -> afterRollback path may execute if properly registered/completed
~~~

In this situation, **the DB transaction can still roll back**. Verify that the framework propagates the exception and the transaction status reflects rollback, rather than only checking that the callback ran.

### 18.2. afterCommit Throws an Exception

~~~text
JDBC commit succeeded
    -> afterCommit callback tries file move
    -> file move throws IOException/IllegalStateException
    -> JDBC data remains COMMITTED
    -> recovery must reconcile file/archive state
~~~

Errors in `afterCommit` may be reported to the caller or error handler depending on transaction synchronization and endpoint configuration, yet **cannot reverse the completed commit**.

**Secondary risk:** If an upstream broker sees this exception and redelivers while the DB is already committed, you can receive a **duplicate** business message. The DB layer needs idempotency/unique keys to handle it.

### 18.3. afterRollback Throws an Exception

~~~text
JDBC rolls back
    -> afterRollback callback tries file quarantine
    -> destination disk full / permission denied
    -> callback fails
    -> original DB rollback still happened
    -> file needs separate recovery or retry
~~~

Keep **original error details** and **cleanup error details** distinct. If the error handler logs only the final stack trace, the initial business cause can be obscured.

### 18.4. Is It Safe to Write to the DB Again Inside afterCommit?

Do not assume so. When `afterCommit` runs, the previous resource transaction may still be thread-bound during completion, yet **it can no longer commit further work for that transaction**.

For durable post-commit DB operations:

- Prefer inserting an **outbox row inside the main transaction**, rather than waiting for `afterCommit` to create it.
- If an independent transaction is genuinely required, call a service/proxy with `REQUIRES_NEW` and test failure/retry behavior.
- Never rely on a JDBC write inside `afterCommit` lacking a new transaction and assume the record committed.

### 18.5. Which Callback Should Never Handle Mandatory Work?

If the application must deliver an event to a partner system **even if the JVM crashes**, an in-memory `afterCommit` callback **is not a durable job queue**. Persist an outbox record inside the primary transaction and let a worker publish it later.

## 19. ErrorChannel, ErrorMessage, and failedMessage

Spring Integration handles errors via `ErrorMessage`, `errorChannel`, poller error handlers, and endpoint retry/recovery mechanisms.

### 19.1. Where Can an Error Surface?

| Boundary | Typical error path |
| --- | --- |
| Synchronous `DirectChannel` | Exception propagates to caller/poller on the same thread |
| Poller task | Error handler may publish an `ErrorMessage` |
| `ExecutorChannel` / async | Error occurs on another thread, requiring async error handling |
| `TransactionInterceptor` | Exception may trigger rollback per rollback rules |
| `beforeCommit` | Can prevent DB commit by throwing an exception |
| `afterCommit` | DB already committed; callback error needs separate recovery |
| `afterRollback` | DB already rolled back; cleanup failure needs separate reporting |
| Broker listener | Container ACK/rollback/nack depends on source configuration |

### 19.2. Why Does the Original Message Matter?

When a poll task fails, the error handler needs to know:

- Which file, row, or source record failed?
- What correlation ID / business operation ID did the message carry?
- Did the preceding transaction commit or roll back?
- Can the exact original input be replayed?

`PassThroughTransactionSynchronizationFactory` or suitable out-of-the-box factories retain the message in the transactional resource context so a `MessagingException` carries `failedMessage` for error reporting.

An `ErrorMessage` payload may be a `MessagingException` with `getFailedMessage()` populated when the message was bound; **do not assume it is always present**.

### 19.3. Error Channel vs. afterRollback Channel

`afterRollbackChannel` on the expression processor provides **transaction completion notifications** per configuration. It **is not automatically**:

- A durable queue.
- A broker DLQ.
- A source containing the exception cause if the expression returns only a `File` or `Boolean`.
- A controller of broker redelivery.

To implement dead-lettering, build a real **error/recovery flow** that persists failures with ownership, retention, and replay logic.

### 19.4. Never Log Raw Payloads in Callbacks

A Spring Message may carry order details, personal data, tokens, or large documents. `Message.toString()` and stack traces in error handlers can expose sensitive data.

Use structured summaries:

~~~json
{
  "event": "file.transaction.after_commit.failed",
  "flow": "file-to-jdbc",
  "fileReference": "file-20261123-42",
  "businessOperationId": "batch-T42-971",
  "databaseOutcome": "COMMITTED",
  "fileArchiveOutcome": "FAILED_RETRYABLE",
  "errorCategory": "FILE_MOVE_IO_ERROR",
  "correlationId": "trace-84021"
}
~~~

This schema is an **application-defined log format**, not default Spring Integration output. Never log raw payloads or credentials.

## 20. Retries and Redelivery: How Many Times Does a Callback Run?

This is a key question when combining `TransactionInterceptor` with retry advice or container redelivery.

### 20.1. One Business Operation Can Span Multiple Transactions

~~~text
Source message K
  -> attempt 1, transaction 1 -> rollback -> afterRollback
  -> attempt 2, transaction 2 -> rollback -> afterRollback
  -> attempt 3, transaction 3 -> commit   -> afterCommit
~~~

This is a **possible scenario** when retry and transaction advice are arranged with one transaction per attempt. Do not assume every retry policy creates three separate transactions; it depends on advice order and listener/poller configuration.

### 20.2. Consequences for Callbacks

- `afterRollback` may be invoked **multiple times** for the same business key across attempts.
- `afterCommit` may run more than once if the source redelivers after commit due to an ACK failure.
- Sending an alert on every rollback can trigger an **alert storm**.
- Renaming the file on the very first rollback can make it disappear before the second retry.
- Generating a fresh UUID event on each attempt makes downstream deduplication difficult.

### 20.3. Idempotent Callbacks

A well-designed callback should use a stable operation key:

~~~text
businessKey = tenant + sourceFileGeneration + recordId

afterCommit archive:
    if already archived for businessKey:
        verify checksum/result; return idempotently
    else:
        move safely and persist archive outcome

afterRollback handling:
    record attempt failure with unique attemptId
    preserve businessKey for next retry
~~~

Never use `MessageHeaders.ID` as a stable key if each redelivery generates a new Spring Message ID.

### 20.4. Total Retry Budget

If the source broker performs 4 deliveries and the handler retries 3 attempts per delivery, side effects can be invoked **12 times**, excluding HTTP SDK retries. Tests should count requests hitting **external systems**, not merely callback invocations.

### 20.5. Non-Retryable Errors

Invalid schemas, permission violations, or missing business keys usually need **quarantine/alerting** rather than endless retries. An `afterRollback` callback should only record **status requiring handling**; never loop the message endlessly back into the same handler.

## 21. Idempotency and Transactional Inbox/Outbox

### 21.1. Why Is TransactionSynchronizationFactory Not Enough?

Consider two events:

1. DB commit succeeds, yet `afterCommit` never runs because of a crash.
2. `afterCommit` calls an API successfully, the response is lost, and the callback retries.

In both cases, correctness cannot be proven by **a single hook alone**. You need a way to answer "has the business action already occurred?" using **durable business state**.

### 21.2. Transactional Inbox Pattern

~~~text
Receive message K
    -> inside JDBC transaction:
         insert inbox(K) with unique constraint if absent
         apply business change
         mark inbox(K, COMPLETED)
    -> commit transaction
    -> source redelivery K:
         read COMPLETED -> do not apply again
~~~

If the handler fails before commit, the transaction rolls back both the inbox entry and business state by design. Do not merely write a `seen` marker to Redis and consider it finished.

### 21.3. Transactional Outbox Pattern

~~~text
Inside JDBC transaction:
    update orders
    insert outbox(eventId, payloadRef, status=PENDING)
commit

Outbox worker:
    read PENDING event
    publish to Kafka/Rabbit/HTTP
    wait for target outcome/confirm per contract
    mark SENT or RETRY_PENDING/UNKNOWN
~~~

`afterCommit` can serve as a **wake-up signal to the outbox worker** to cut latency, while the **outbox row** remains the crash-durable source of work. If the wake-up signal is missed, the worker still polls the outbox.

### 21.4. Illustrative Schema

~~~sql
CREATE TABLE inbound_inbox (
    operation_key       VARCHAR(220) PRIMARY KEY,
    payload_fingerprint VARCHAR(128) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    result_reference    VARCHAR(240),
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE outbound_outbox (
    event_id            VARCHAR(220) PRIMARY KEY,
    aggregate_id        VARCHAR(220) NOT NULL,
    destination         VARCHAR(160) NOT NULL,
    payload_reference   VARCHAR(400) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    attempts            INT NOT NULL DEFAULT 0,
    updated_at          TIMESTAMP NOT NULL
);
~~~

This is an **illustrative business schema**: add indexes, locking, cleanup, payload encryption, and transaction isolation per product requirements. If the same event targets multiple destinations, the unique key may need to include `destination`.

### 21.5. Do Not Equate "After Commit" with "Exactly Once"

Even when the outbox is written atomically alongside business data, the publisher can resend after the target received the event but before marking `SENT`. Downstream must have a **stable event ID and an idempotent receiver**.

## 22. Practical Walkthrough: File → JDBC → Kafka

A system receives revenue files via a local directory synced from SFTP. Each file contains multiple records, requiring database updates and publishing a Kafka event once data is confirmed.

### 22.1. Initial Design (Flawed)

~~~mermaid
flowchart LR
    F["File poller"] --> DB["JDBC transaction"]
    DB --> COM["Commit"]
    COM --> HOOK["afterCommit"]
    HOOK --> K["Kafka producer send"]
    K --> D["Kafka topic"]
~~~

If the callback invokes `send` asynchronously and the process crashes, Kafka might never receive the record while the DB has already committed. Without an outbox, the application has no record that the event needs resending.

### 22.2. Improved Design

~~~mermaid
flowchart TD
    FILE["File inbound adapter"] --> POLL["Transactional poller"]
    POLL --> PARSE["Parse/validate"]
    PARSE --> TX["JDBC transaction"]
    TX --> DATA["Upsert business rows"]
    TX --> OB["Insert outbox events"]
    DATA --> COMMIT["DB commit"]
    OB --> COMMIT
    COMMIT --> AC["afterCommit: signal archive worker"]
    AC --> ARCH["Archive file + audit"]
    OB --> WORK["Independent outbox publisher"]
    WORK --> KAFKA["Kafka topic"]
    KAFKA --> CONF["Producer result"]
    CONF --> MARK["Update outbox SENT / UNKNOWN"]
    ARCH --> REC["Startup reconciliation"]
    MARK --> REC
~~~

Key differences:

1. **Business rows and outbox rows commit in the same DB transaction**.
2. `afterCommit` only reduces latency for archiving/signaling; the system can **reconcile state on restart**.
3. Kafka publishing is handled by a dedicated worker checking results/confirmations.
4. Kafka consumers use idempotent keys to tolerate redelivery.
5. Files are archived with durable state and failure handling when moves fail.

### 22.3. Message Contract

~~~yaml
# Illustrative application contract; not default Spring Integration YAML.
fileGeneration: "sales-20261123-sha256-example"
batchId: "batch-T42-971"
businessKey: "sales-import:T42:971"
source:
  adapter: "file-from-sftp"
  fileName: "sales-2026-11-23.csv"
database:
  state: "COMMITTED"
fileLifecycle:
  state: "ARCHIVE_PENDING"
kafka:
  outboxEventId: "sales-imported:T42:971"
  state: "PENDING"
~~~

Do not cram all these fields into a single metadata store string and assume the framework guarantees them. This is an application-maintained **business state machine**.

### 22.4. Scenario A: Successful Processing

~~~text
T0  Poll file F
T1  Begin JDBC TX
T2  Parse + validate all rows
T3  Upsert business rows + insert outbox
T4  beforeCommit validation PASS
T5  DB commit succeeds
T6  afterCommit signals archive
T7  Archive file succeeds
T8  Outbox worker publishes Kafka and records outcome
~~~

What to verify: DB data, outbox row, archived file, Kafka record, correlation, and logs/metrics.

### 22.5. Scenario B: Validation Failure

~~~text
T0 Poll file F
T1 Begin JDBC TX
T2 Validate row 42 -> INVALID_SCHEMA
T3 Throw exception
T4 DB rollback
T5 afterRollback -> quarantine or record retry
~~~

If the quarantine move fails, do not treat that as a failed DB rollback; log a **secondary failure** and preserve reprocessability. If the file needs data correction, establish a clear owner and correction workflow.

### 22.6. Scenario C: Crash After Commit

~~~text
T0 DB commit succeeds
T1 JVM crashes before afterCommit
T2 Application restarts
T3 Reconciliation job finds batch DB COMMITTED, file still in inbox
T4 Job archives file idempotently; outbox worker publishes Kafka
~~~

This case is mandatory when designing around post-commit hooks. Never treat "hook registered" as a guarantee the hook always executes.

### 22.7. Scenario D: Kafka Publish Occurred, Result Lost

~~~text
Kafka broker accepted event
Producer callback/future result lost
Outbox row remains IN_FLIGHT/UNKNOWN
Worker retries with same eventId
Target consumer ignores duplicate business effect
~~~

Do not regenerate `eventId` on each retry; doing so defeats deduplication.

## 23. Transaction Synchronization and File Accept-Once Filters

File inbound adapters frequently use **accept-once** or persistent file filters to avoid re-polling the same file. The source filter may record that a file **was selected**, without knowing whether the downstream DB transaction committed.

### 23.1. Failure Window

~~~text
File F accepted by persistent filter
JDBC transaction fails
afterRollback executes
File remains in source directory

Next poll:
    file filter says already accepted
    -> F may not be emitted again
~~~

Configuring `afterRollback` alone does not automatically reset every file filter's state. If file retry is needed, understand **filter metadata rollback/removal** for your implementation and select a verified recovery option.

### 23.2. Design Options

| Approach | Pros | Risks |
| --- | --- | --- |
| Use persistent filter and reset key on rollback per contract | Retries the same file | Incorrect reset causes duplicates or multiple workers picking the same file |
| Move failed files to quarantine | Prevents infinite poller loops | Requires owned repair/replay job |
| Persist per-file processing state in DB | Durable evidence across restarts | More complex, needs transactions/unique keys |
| Use staging + claim/lease | Reduces competing polls | Must handle stale leases/crashes |
| Use per-record inbox | Line-level recovery once file is loaded | Needs stable record keys and clear file lifecycle |

Never use arbitrary `Files.move` calls to "clear the filter" without understanding remote/local file semantics.

## 24. SpEL Pitfalls and How to Diagnose Them

### 24.1. Wrong Payload Type

Expression:

~~~text
payload.renameTo(new java.io.File('/processed/' + payload.name))
~~~

This only works when the payload is genuinely `java.io.File`. With an SFTP stream, Kafka `ConsumerRecord`, HTTP DTO, or JDBC `Map` payload, this expression will fail with a type error.

Solution: safely log/inspect the **class name** and test each adapter's contract instead of guessing types from channel names.

### 24.2. Expression Returning `false` Is Not an Exception

With `File.renameTo`, `Boolean.FALSE` can still be published normally to `afterCommitChannel`.

~~~text
afterCommit expression evaluated -> false
channel receives payload=false
no exception thrown
DB already COMMITTED
~~~

The channel's consumer must **inspect the boolean** and raise an alert/recovery action; tests must not merely assert "message received."

### 24.3. Expression Returning null/void

Per `ExpressionEvaluatingTransactionSynchronizationProcessor`'s contract, if an expression evaluates to null/void, **no message may be sent to the channel** on the expression-result branch.

If you simply want to forward the received message to the channel, configure the **channel without an expression** as supported by the API/namespace. Write tests asserting expected payload and headers.

### 24.4. Wrong Bean Name in SpEL

~~~text
@fileLifecycleService.archive(payload)
~~~

The bean name must exist in the appropriate `ApplicationContext`/`EvaluationContext`, and the method must be permitted for invocation. Avoid evaluating SpEL constructed from untrusted input, as it is **expression code capable of invoking methods and beans**.

### 24.5. Missing Original Message

When the poller has not yet received a message or the transaction context was never bound, `holder.getMessage()` may be null. A custom processor must not fabricate a business key. Instead:

- Log error category `MISSING_POLLED_MESSAGE_CONTEXT`.
- Fall back to a trusted metadata/trace source if designed.
- Ensure you do not ACK/quarantine a different message by mistake.
- Verify resource cleanup in custom factories.

## 25. Unit Testing a Custom Processor

To verify callback logic, you can test `TransactionSynchronizationProcessor` independently of the poller. Example using Mockito:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.transaction.IntegrationResourceHolder;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.mockito.Mockito.*;

class AuditedFileSynchronizationProcessorTest {

    @Test
    void callsAfterCommitServiceWithOriginalMessage() {
        FileLifecycleService service = mock(FileLifecycleService.class);
        var processor = new AuditedFileSynchronizationProcessor(service);

        Message<String> message = MessageBuilder
                .withPayload("file-reference-123")
                .setHeader("businessOperationId", "batch:T42:971")
                .build();
        IntegrationResourceHolder holder = new IntegrationResourceHolder();
        holder.setMessage(message);

        processor.processAfterCommit(holder);

        verify(service).onDatabaseCommitted(message);
        verify(service, never()).onDatabaseRolledBack(any());
    }

    @Test
    void callsRollbackServiceWithOriginalMessage() {
        FileLifecycleService service = mock(FileLifecycleService.class);
        var processor = new AuditedFileSynchronizationProcessor(service);

        Message<String> message = MessageBuilder.withPayload("file-ref")
                .build();
        IntegrationResourceHolder holder = new IntegrationResourceHolder();
        holder.setMessage(message);

        processor.processAfterRollback(holder);

        verify(service).onDatabaseRolledBack(message);
        verify(service, never()).onDatabaseCommitted(any());
    }
}
~~~

`FileLifecycleService` is an **application-defined** interface/service as in the earlier example. Mockito/JUnit require appropriate test dependencies.

**Test limitation:** Calling `processAfterCommit()` directly **does not prove a real transaction committed** or that the framework registered the callback correctly. To test the transaction lifecycle, run an **integration test with a real poller + transaction manager**.

### 25.1. Testing Pre-Commit Validation

~~~java
FileLifecycleService service = mock(FileLifecycleService.class);
doThrow(new IllegalStateException("file contract invalid"))
        .when(service).validateBeforeCommit(any());

assertThrows(IllegalStateException.class,
        () -> processor.processBeforeCommit(holder));
~~~

This test proves the processor propagates the error. An integration test is still needed to prove **JDBC transaction rollback** under the actual configuration/proxies.

### 25.2. Never Mock Messages Containing Full Sensitive Data

Create fixtures with only payload references and minimal headers. Add assertions confirming error logs do not leak raw PII, access tokens, file contents, or SQL credentials.

## 26. Integration Testing: Real Transactions and Real Files

A quality test suite must prove that the **poller transaction actually registers synchronization**, and callbacks execute **in the correct phase after JDBC commit/rollback**.

### 26.1. Test Environment

Components:

- Spring Test / JUnit 5 with a dedicated test context.
- `FileReadingMessageSource` or a real file inbound adapter pointing to a temporary directory.
- Poller configured with `TransactionInterceptor` and `TransactionSynchronizationFactory`.
- `DataSourceTransactionManager` backed by H2 or a test database.
- `DirectChannel` across the segment intended to share the transaction.
- Fake business service capable of throwing exceptions at chosen points.
- `afterCommit`/`afterRollback` handlers recording observable state.
- Bounded waits instead of fixed sleeps.

If using an embedded database solely for logic tests, remember **H2 does not reproduce all semantics** of PostgreSQL/Oracle/MySQL regarding locks, isolation, and crash recovery. For critical concurrency paths, add integration tests against a real database via containers.

### 26.2. Test Case T1: Successful Commit

~~~text
Given:
    valid temp file F.csv
    empty DB
    transactional poller + synchronization factory active

When:
    poller receives F
    service writes DB rows
    transaction commits

Then:
    DB rows exist
    afterCommit runs as designed
    afterRollback does not run
    file archive is verified
    metadata/correlation are consistent
~~~

Do not only verify `afterCommit` was invoked: check that the file actually resides at the destination and is gone from the source (or in the expected state when using copy+archive).

### 26.3. Test Case T2: Business Error Before Commit

~~~text
Given:
    temp file F.csv
    service writes first row then throws RuntimeException

When:
    poller runs inside JDBC transaction

Then:
    JDBC row count matches pre-transaction state
    afterRollback executes as configured
    afterCommit does not run
    source file remains recoverable/replayable
~~~

### 26.4. Test Case T3: beforeCommit Fails

~~~text
Given:
    JDBC handler succeeds
    beforeCommit validator throws

Then:
    JDBC transaction rolls back
    afterCommit not executed
    failed message context available when configured
    failure handling has durable record or safe source retention
~~~

### 26.5. Test Case T4: afterCommit Fails

~~~text
Given:
    JDBC commit succeeds
    Files.move throws IOException

Then:
    JDBC rows remain committed
    file archive state remains pending/failed
    alert/reconciliation exists
    no false rollback claim
~~~

This test **separates two distinct truths**: the DB commit succeeded, and file archiving is not yet complete.

### 26.6. Test Case T5: Crash After Commit

Using a separate container/process:

1. Commit DB and record `ARCHIVE_PENDING`.
2. Terminate the process before the file-move callback runs.
3. Restart the bridge.
4. Run reconciliation.
5. Verify the file gets archived **without inserting duplicate DB rows**.

You cannot accurately simulate a crash by throwing an exception inside a callback: the JVM is still alive and lifecycle callbacks keep running. At least one **restart/failure-injection test** in an isolated environment is needed for critical guarantees.

## 27. Test Matrix by Adapter

| Adapter | Failures to inject | What must be verified |
| --- | --- | --- |
| File inbound | DB rollback, file move failure, crash after commit | File lifecycle, accept-once filter, idempotency |
| SFTP inbound | Remote timeout, incomplete download, stream close failure | No lost source / no session leak, replay works |
| HTTP outbound | Remote commits then response drops | Outcome unknown, reconciliation before retry |
| JMS inbound | Listener rollback, ACK failure after commit | Redelivery produces no duplicate business effects |
| AMQP inbound | NACK/requeue, misrouted DLX | No infinite poison loop, DLQ holds the record |
| Kafka inbound | Rebalance/offset commit fail, DLT publisher fail | Idempotency, correct offset/replay |
| JDBC inbound | Competing row claims, exception before commit | Transaction rollback, consistent row state |
| Async poller | `ExecutorChannel` fails after callback | Callback is not mistaken for whole-flow success |
| Pseudo transaction | SFTP upload succeeds, then callback fails | Never claims remote rollback |
| Multiple instances | Two pollers target same file/key | Claim/lock/dedupe matches topology |

### 27.1. Assertion Plan for failedMessage

For a poller with appropriate pass-through/default synchronization and transaction advice:

~~~text
Simulate handler failure after poller received message M.
Read errorMessage from configured error channel.
Find MessagingException if published by the error handler.
Assert:
    failedMessage matches M by safe business key/correlation.
    root cause is expected exception.
    no raw PII/credentials leaked to logs.
~~~

This is an **assertion plan**, not a guarantee that `failedMessage` exists on every exception path.

### 27.2. Verifying Channel Result Types

When an expression returns `Boolean.FALSE`, `afterCommitChannel` may receive a Boolean message payload. If the consumer expects a `File`, tests will expose the contract mismatch.

Test:

- Expression `payload` → payload retains original type.
- Expression `payload.renameTo(...)` → payload is Boolean.
- Channel only, no expression → original message forwarded per contract.
- Null/void expression → no result message per processor behavior.

### 27.3. Testing Transaction Advice Ordering

Have the handler fail transiently once and then succeed. Test both advice-ordering configurations permitted by your project:

- One new transaction per attempt.
- One transaction spanning multiple attempts.

Measure:

1. Counts of `beforeCommit`/`afterRollback`/`afterCommit`.
2. Counts of JDBC commits and rollbacks.
3. Whether the message was marked rollback-only.
4. Whether the source poller redelivered.

Results must match **the guarantee your project requires**, not merely the attempt count.

## 28. Failure-Injection Matrix by Timing

| Point | Possible outcome | Recovery strategy |
| --- | --- | --- |
| F1. Before poll `receive()` | Source still has message/file | Polls normally on next cycle |
| F2. After poll, before JDBC write | File passed filter, DB unchanged | Source state or retry job must retain responsibility |
| F3. After JDBC write, before commit | DB can roll back | Redelivery/retry; inspect filter |
| F4. Inside `beforeCommit` | Transaction can roll back | Quarantine invariant violation, preserve evidence |
| F5. After commit, before `afterCommit` | DB succeeded, post-processing not run | Reconciliation / `ARCHIVE_PENDING` |
| F6. `afterCommit` move returns false | DB committed, file not archived | Inspect return value and retry safely |
| F7. After archive, before marking archived | File moved, DB status still pending | Idempotent path+checksum reconciliation |
| F8. `afterRollback` failure | DB rolled back, quarantine incomplete | Alert secondary failure, retain source |
| F9. After HTTP remote commit, before response | Remote outcome UNKNOWN | Idempotency key + remote status query |
| F10. Kafka publish succeeds, outbox mark fails | Event may be re-emitted | Stable event ID on consumer |
| F11. Source broker ACK fails after DB commit | Redelivery | Transactional inbox / unique constraint |
| F12. Instance restart or scale-out | Duplicate/contended claim | Shared store, locking, startup reconciliation |

Each row should have a **test ID**, owner, adapter type, priority, and evidence tied to the runtime version. Any critical design lacking F5/F6/F11 tests often harbors gaps even when happy-path tests are green.

## 29. Observability: Measuring Commit Facts and Callbacks Separately

### 29.1. Suggested Metrics

| Metric | Role |
| --- | --- |
| `poller_transaction_started_total` | Count of polling transactions started |
| `poller_transaction_committed_total` | Count of observed commits |
| `poller_transaction_rolled_back_total` | Count of observed rollbacks |
| `transaction_sync_before_commit_total` | Invocations of before-commit callback |
| `transaction_sync_after_commit_total` | Invocations of after-commit callback |
| `transaction_sync_after_rollback_total` | Invocations of rollback callback |
| `transaction_sync_callback_failed_total` | Errors executing callbacks |
| `file_archive_pending` | Files DB-committed but not yet archived |
| `file_archive_failed_total` | Archive failures |
| `inbox_pending_oldest_age` | Age of unconfirmed inbox work |
| `outbox_pending_oldest_age` | Age of unpublished outbox events |
| `poller_source_lag` | Inbound lag |
| `error_flow_persist_failed_total` | Failures writing to the failure store |
| `reconciliation_recovered_total` | Cases recovered after crashes |

These are **application metric suggestions**, not built-in Spring Integration defaults. Choose low-cardinality tags such as `flow`, `adapter`, `phase`, and `result`; never use `filePath`, `tenantId`, or `operationId` as metric labels.

### 29.2. Phase-Based Tracing

~~~text
Trace businessOperationId=batch-T42-971
  -> poll.receive
  -> transaction.begin
  -> parse.validate
  -> jdbc.update
  -> transaction.before_commit
  -> transaction.commit
  -> transaction.after_commit
  -> file.archive
  -> outbox.publish (different worker)
  -> reconciliation
~~~

Not all spans share the same transaction or thread. Across async/outbox boundaries, propagate the **business correlation ID** and build proper tracing contexts—never confuse a trace span with a commit guarantee.

### 29.3. Alerts Worth Configuring

- `file_archive_pending` climbs while JDBC commits continue steadily.
- `afterCommit` callbacks fail repeatedly due to filesystem permissions.
- Source files get re-polled despite records already existing in the DB.
- `afterRollback` file moves fail or quarantine fills up.
- Rising count of `failedMessage` entries missing a business key.
- Transaction timeouts, deadlocks, or connection pool saturation.
- JDBC commits increase while Kafka outbox `SENT` counts stagnate.
- Resource cleanup fails after callbacks, growing session/thread usage.
- Restarts/rebalances cause abnormal spikes in retry attempts.

## 30. Security and Sensitive Data

Transaction synchronization is often configured close to source files, databases, and privileged beans. Enforce boundaries:

1. **SpEL input:** Never evaluate expressions constructed from untrusted user or remote payloads.
2. **Bean access:** Callback services should hold only minimal required permissions, never admin DB/file accounts.
3. **File paths:** Only move within approved directories; guard against path traversal and symlink attacks.
4. **Multi-tenancy:** Never allow one tenant to pick another destination via an unverified header.
5. **Sensitive payloads:** Never log full `Message` objects, SQL parameters, or Authorization headers.
6. **Outbox/failure store:** Encrypt payload references or data where required and enforce retention policies.
7. **SFTP credentials:** Rotate secrets and enforce session timeouts; never store passwords in failure envelopes.
8. **Audit:** Record who modifies transaction/poller/factory configurations, destinations, or deletes metadata.
9. **Replay authorization:** Only authorized owners/operators may replay operations with side effects.

### 30.1. Path Handling Example

~~~text
BAD:
  targetPath = "/var/app/processed/" + message.header("fileName")
  // header could be "../../etc/..."

BETTER:
  fileId = validatedSourceMetadata.fileId
  targetPath = approvedRoot.resolve(safeGeneratedName(fileId))
  verify targetPath.normalize().startsWith(approvedRoot.normalize())
~~~

This is pseudocode for **input validation**. `normalize` alone is insufficient against symlink races; enforce filesystem permissions and trusted directory controls per your threat model.

## 31. Runbook: When afterCommit Fails to Archive Files

**Scenario:** The JDBC transaction committed, yet the file remains in `inbox/`; dashboards show `file_archive_pending` rising.

### 31.1. Triage

1. Confirm the DB transaction **genuinely COMMITTED** via business records/transaction logs.
2. Inspect source file path, file generation/checksum, business key, and poll timestamp.
3. Verify `afterCommit` was registered and executed.
4. If the callback ran: inspect the `renameTo` Boolean result or `Files.move` exception.
5. Check file permissions, existing destination files, full disk / cross-device issues, and file locks.
6. Check whether the source file filter/accept-once metadata permits re-polling.
7. Check for app restarts/kills/timeouts before callbacks and across thread boundaries.
8. Check whether outbox/Kafka events have already been sent to avoid triggering duplicate side effects.

### 31.2. Reconcile Before Manual Intervention

| Evidence | Action |
| --- | --- |
| DB COMMITTED, file unarchived | Archive idempotently using verified file ID/checksum |
| DB ROLLED_BACK, file still in inbox | Retry/reprocess per policy if source filter allows |
| DB ROLLED_BACK, file in failed/ | Review quarantine then perform controlled replay |
| DB UNKNOWN, file moved to processed/ | Inspect commit logs/inbox before replaying |
| File missing, no DB record | Data incident; locate backup / original SFTP / failure store |
| File archived, outbox PENDING | Let outbox worker proceed; do not re-read the file just to publish |
| Remote API outcome UNKNOWN | Query by stable operation key; never blindly re-POST |

### 31.3. Remediation and Incident Closure

- Do not wipe all accept-once metadata or flush Redis just to "unstick the poller."
- Do not shuffle files in and out of `inbox/` repeatedly before knowing the business outcome.
- Restore DB/file state using stable keys and throttle concurrency during replay.
- Record before/after evidence, owner/approval, and outcome.
- Close the incident only when **DB, file lifecycle, source filter, outbox, and error records** are consistent, or remaining exceptions have an owner and deadline.

## 32. Common Anti-Patterns

| Anti-pattern | Why it is wrong | Solution |
| --- | --- | --- |
| Believing `TransactionSynchronizationFactory` starts transactions | The factory only creates synchronizations | Configure transaction manager/advice on the poller |
| Using `afterCommit` to roll back files | File operations are not transactional | Compensation/reconciliation |
| Calling Kafka/HTTP in `afterCommit` without an outbox | Crashes can lose events | Durable outbox + worker |
| Using `beforeCommit` for side-effecting APIs | DB rollback does not undo the API call | Move to outbox/idempotency |
| Using `ExecutorChannel` and expecting shared TX | Thread-local transaction is severed | Clear TX boundaries + durable handoff |
| Ignoring `renameTo` returning `false` while marking `ARCHIVED` | Silent archive failure | Check Boolean / `Files.move` + alert |
| Moving to `failed/` in `afterRollback` on first retry | Source disappears before next retry | Align retry policy and file lifecycle |
| Treating `PseudoTransactionManager` as XA | Cannot roll back files/SFTP | State guarantees accurately, reconcile |
| Writing custom factory and forgetting unbind | Leaks messages/tenants and memory | Use default factory or test cleanup |
| Treating `afterCommit` invocation as guaranteed success | Side effect itself can fail | Verify actual target state |
| Ignoring accept-once filter state | File never re-polled after rollback | Transaction-aware source recovery |
| Omitting stable business keys | Redelivery causes duplicates | Inbox / unique constraints |
| Multi-layer retries without a budget | Retry storms and latency | End-to-end retry budget |
| Logging raw `failedMessage` | Leaks PII/secrets | Correlation, redaction, and payload references |
| Treating `errorChannel` as a durable DLQ | Failed messages can still be lost | Durable failure store / broker DLQ |
| Using `REQUIRES_NEW` without analysis | Partial DB commits survive poller rollback | Design propagation intentionally and test |
| Skipping kill tests between commit and callback | Misses critical failure windows | Restart/reconciliation tests |
| Advancing high-watermarks past uncommitted file records | Data loss | Per-record state/gap tracking |
| Conflating Kafka offsets with JDBC commits | Broken at-least-once assumptions | Idempotent consumers and commit ordering |
| Deleting all metadata after an incident | Mass replay of duplicate side effects | Scoped metadata fixes with approval |

## 33. Self-Check Questions

### Question 1. Does the factory start a transaction by itself?

**Answer:** No. `TransactionSynchronizationFactory` creates synchronization; the poller needs appropriate transaction advice/manager to bind the lifecycle.

### Question 2. If `afterCommit` throws an exception, does JDBC roll back?

**Answer:** An already-committed transaction cannot be rolled back simply because a post-commit callback fails. Persist post-processing state and handle recovery/reconciliation independently.

### Question 3. What is `beforeCommit` used for?

**Answer:** Validating conditions and executing work that must occur prior to resource commit. The callback can trigger rollback by throwing an appropriate exception. Avoid irreversible remote side effects here.

### Question 4. Does `afterRollback` undo an SFTP upload?

**Answer:** No. It can execute compensating logic if implemented, but an upload that already occurred requires separate handling and has no native atomic rollback.

### Question 5. What is the role of `PseudoTransactionManager`?

**Answer:** It provides success/failure lifecycle signals for synchronization in flows lacking a real transactional resource; it does not turn filesystems, FTP/SFTP, or HTTP into transactional resources.

### Question 6. Why is `ExecutorChannel` dangerous here?

**Answer:** It switches threads; the poller transaction can commit and invoke `afterCommit` before the async worker finishes. Use durable handoffs or separate transactions.

### Question 7. If `File.renameTo` returns `false`, what does the channel receive?

**Answer:** When a rename expression and channel are configured, the Boolean result can be sent as the channel payload; `false` is a failure you must handle, not an automatic exception.

### Question 8. What is the PassThrough factory used for?

**Answer:** Keeping the polled message bound to the transaction context so advice errors can attach `failedMessage` for error reporting; it does not archive files or produce business results.

### Question 9. If the DB committed but the file remains in inbox after restart, what should happen?

**Answer:** Use business keys/DB evidence and file generation/checksums to reconcile and archive safely; never blindly re-run all DB inserts.

### Question 10. Does sending to Kafka in `afterCommit` guarantee exactly-once?

**Answer:** No. Producer sends can be async/fail or succeed right before a crash. You need a transactional outbox, stable event IDs, producer confirmations, and idempotent targets.

### Question 11. Does `afterRollback` always run if the app receives `kill -9`?

**Answer:** No. In-process callbacks are not guaranteed to execute on abrupt process termination; rely on durable work queues and startup reconciliation.

### Question 12. Why does a multi-record file complicate callbacks?

**Answer:** The transaction of a single polled file message does not automatically encompass all records if the flow splits threads or commits per record. Define whole-file vs. per-record completion semantics explicitly.

## 34. TransactionSynchronizationFactory Implementation Checklist

1. **Right use case:** Coordinating callbacks with poller transaction outcomes, not mimicking distributed transactions.
2. **Real transaction manager:** `DataSourceTransactionManager` for JDBC or the manager matching your source; verify datasource/connections.
3. **Intentional pseudo transactions:** Only when success/failure hooks are needed without real transactional resources.
4. **Attach factory to poller:** Do not just declare the bean and expect it to wire itself.
5. **Correct thread boundaries:** Audit Direct, Executor, and Queue channels.
6. **Correct advice ordering:** Transaction vs. retry vs. custom advice and `@Transactional` propagation.
7. **No hard-to-undo remote effects in `beforeCommit`** when DB atomicity is required.
8. **Never treat `afterCommit` as a durable job queue**; add reconciliation or an outbox when mandatory.
9. **Give `afterRollback` error handling** and a clear replay source.
10. **Prefer default factory before custom:** Use `DefaultTransactionSynchronizationFactory` + processor where suitable.
11. **Resource cleanup:** Custom factories must unbind holders on completion.
12. **Original message:** Verify holder/`failedMessage` and correlation along actual error paths.
13. **File types:** Never copy `File` expressions onto SFTP streams or JDBC DTOs.
14. **File move outcomes:** Inspect Booleans or handle `IOException`, collisions, and cross-filesystem moves.
15. **File filter state:** Never assume rollback resets accept-once filters.
16. **Per-record semantics:** Maintain per-record status/commit evidence when required.
17. **Source ack/offsets:** Test JMS/AMQP/Kafka with real containers/brokers; do not infer from callbacks.
18. **HTTP idempotency:** Timeouts can happen after remote commit.
19. **Outbox:** Insert within the same DB transaction when post-commit event publishing must be guaranteed.
20. **Retry budget:** Count attempts across handlers, SDKs, containers, and brokers.
21. **Durability:** Test restarts/crashes before and after commit and callbacks.
22. **Observability:** Track DB commits, callbacks, file archives, outbox, and replays as distinct states.
23. **Security:** Restrict SpEL/bean access, sanitize paths, enforce tenant isolation, redact secrets.
24. **Failure store:** Assign ownership, retention, auditing, and controlled replay.
25. **Runbook:** Document how to reconcile committed DB state when callbacks did not run.
26. **Version verification:** Check XML namespaces, Java DSL, and APIs against your project's Spring Integration BOM.

## 35. References

Official documentation for understanding APIs and verifying version-specific configurations:

1. **Spring Integration — Transaction Support:**  
   https://docs.spring.io/spring-integration/reference/transactions.html
2. **Spring Integration — DefaultTransactionSynchronizationFactory Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/DefaultTransactionSynchronizationFactory.html
3. **Spring Integration — ExpressionEvaluatingTransactionSynchronizationProcessor Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/ExpressionEvaluatingTransactionSynchronizationProcessor.html
4. **Spring Integration — IntegrationResourceHolder Javadoc:**  
   https://docs.spring.io/spring-integration/api/org/springframework/integration/transaction/IntegrationResourceHolder.html
5. **Spring Integration — File Support:**  
   https://docs.spring.io/spring-integration/reference/file.html
6. **Spring Integration — SFTP Support:**  
   https://docs.spring.io/spring-integration/reference/sftp.html
7. **Spring Integration — JDBC Support:**  
   https://docs.spring.io/spring-integration/reference/jdbc.html
8. **Spring Framework — Transaction Synchronization:**  
   https://docs.spring.io/spring-framework/reference/data-access/transaction.html

**Note on examples:** XML, Java, SQL, YAML, and diagrams in this lesson illustrate API contracts and failure scenarios. Bean names like `FileLifecycleService`, database schemas, and audit channels are **application-built components**. Verify against your Spring Integration/Spring Boot versions, compile, and run integration tests before deploying examples to production. This lesson's scope **has not built or executed tests in a repository**.

## 36. Summary

`TransactionSynchronizationFactory` bridges **transaction outcomes** and **transaction-lifecycle-synchronized actions** in Spring Integration. The factory creates `TransactionSynchronization` and commonly uses `DefaultTransactionSynchronizationFactory` with `TransactionSynchronizationProcessor` or `ExpressionEvaluatingTransactionSynchronizationProcessor` to run `beforeCommit`, `afterCommit`, and `afterRollback`. `IntegrationResourceHolder` binds the message to the transaction context; `PassThroughTransactionSynchronizationFactory` helps retain `failedMessage` for error reporting; `PseudoTransactionManager` enables success/failure hooks when no real transactional resource exists.

However, **synchronization does not mean atomicity across all adapters**. JDBC transactions can roll back DB data, whereas File/SFTP/HTTP/Kafka/JMS/AMQP have protocol-specific ACKs, publishes, and side effects. A failing `afterCommit` does not uncommit the DB; an `ExecutorChannel` can let callbacks run before async business work completes; and file accept-once filters or broker offsets do not automatically align with handler transactions.

A resilient design combines **clear transaction boundaries, complete original message/correlation metadata, idempotent callbacks, verified file moves, bounded error/retry policies, transactional inbox/outbox, startup reconciliation, and crash-window testing**. A File/SFTP → JDBC → broker flow can only be considered safely handled when **business outcomes have durable evidence**, any missed post-commit actions can be recovered, and messages are neither lost nor duplicated beyond the chosen contract.


