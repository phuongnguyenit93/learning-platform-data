# Rollback When a Downstream Handler Fails in Spring Integration Adapters

## 1. The Problem: Upstream Handler Succeeds, Downstream Handler Throws

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects external systems via **inbound/outbound adapters**, **gateways**, **pollers**, and **`MessageChannel`**. A message may pass through multiple transformers, filters, service activators, JDBC handlers, HTTP outbound gateways, or broker adapters. When a *downstream* handler fails, the first question is not "was an `ErrorMessage` emitted?"—it is:

**Which operations belong to the same uncommitted transaction, and does the exception actually propagate back across that transaction boundary?**

For example, a CSV file containing orders is received and processed:

~~~text
File inbound poller
    -> validate
    -> JDBC handler: INSERT orders
    -> HTTP outbound gateway: create shipment
    -> downstream handler: publish confirmation
~~~

Suppose the final handler throws an exception. There are at least four possibilities:

| Scenario | What can roll back? | What must NOT be inferred |
|---|---|---|
| JDBC `INSERT` and failing handler share **one uncommitted DB transaction** | The `INSERT` can roll back | Does not mean the file was reset to its initial state |
| JDBC `INSERT` already committed **before** the handler failed | That transaction can no longer roll back via a new exception | Cannot "undo" simply by throwing an exception |
| HTTP `create shipment` was already accepted externally | Cannot roll back HTTP via a DB transaction | Requires idempotency, status lookup, or compensation |
| Downstream runs via `ExecutorChannel`/async callback | Exception may occur on another thread, outside the sender's transaction | Cannot assume errors propagate back to the initial poller/gateway |

**Rollback** is the mechanism for undoing *uncommitted* changes within the scope managed by a transaction manager. It differs from **retry** (re-attempting an operation), **compensation** (issuing a compensating business action for an already-occurred side effect), and **reconciliation** (resolving unknown outcomes).

### Learning Objectives

After this lesson, you will be able to:

1. Identify transaction boundaries, commit points, and where exceptions must propagate to trigger rollback.
2. Distinguish **synchronous `DirectChannel`**, **`QueueChannel`/poller**, and **`ExecutorChannel`/asynchronous** execution paths.
3. Apply **`@Transactional`**, **transactional pollers/advice**, and transaction managers to the appropriate scope.
4. Explain why **`errorChannel`/`ErrorMessage`** neither guarantees a rollback occurred nor proves it did not.
5. Distinguish local JDBC transactions from File, SFTP, HTTP, JMS, AMQP, and Kafka semantics.
6. Design retries, acknowledgments, idempotency, inbox/outbox, compensation, and unknown-outcome states.
7. Test fault injection before/after commit, before/after ack, and across thread boundaries.

## 2. Foundational Concepts to Distinguish

| Concept | Meaning | Example |
|---|---|---|
| Transaction boundary | Scope coordinated by a transaction manager | One JDBC transaction spanning multiple SQL statements |
| Commit | Accepting the transaction's changes | DB persists order + outbox together |
| Rollback | Discarding uncommitted changes inside that transaction | `INSERT` disappears after exception |
| Propagation | How calls join or start a transaction | `REQUIRED`, `REQUIRES_NEW` in Spring |
| Exception propagation | Exception traveling back to the transaction controller | `DirectChannel` handler throwing back to caller |
| Error publishing | Wrapping a `Throwable` into an `ErrorMessage` sent to an error channel | Poller error handler publishing an error |
| Retry | Re-running an operation per policy | Retrying DB connection with backoff |
| Acknowledgment | Source/broker recording a message as received/handled | JMS ack, AMQP ack, Kafka offset |
| Compensation | A new task undoing a completed side effect | Cancel shipment, release reservation |
| Idempotency | Repeating the same request causes no extra business effect | One `orderId` creates only one shipment |

Key point: **database transactions**, **message broker transactions/acks**, and **connection lifecycles** can be completely separate mechanisms. Simply residing inside the same `IntegrationFlow` does not merge them into one global transaction.

### 2.1. Which Resources Does a Transaction Manager Manage?

A **`DataSourceTransactionManager`/`JdbcTransactionManager`** coordinates JDBC connections for its configured `DataSource`. A **`JmsTransactionManager`** manages transactions for its corresponding JMS `Session`. External systems such as SFTP filesystems, HTTP servers, or Kafka producers do not automatically join a local JDBC transaction.

Coordinating atomicity across multiple resources can sometimes use XA/JTA when all resources and infrastructure properly support it, at the cost of operational complexity and risk. **Never treat XA as the default for HTTP/SFTP/Kafka**; use outbox/inbox or sagas where appropriate.

### 2.2. "Downstream Handler" Is a Relative Position

In a flow:

~~~text
M0 -> transformer T -> handler H1 -> channel C -> handler H2
~~~

`H2` is downstream of `H1`. If `H1` and `H2` are invoked synchronously on the same thread, an exception from `H2` **can** travel back to `H1`/caller. If `C` is an async boundary, `H1` may finish before `H2` starts; `H1`'s transaction may already have committed.

### 2.3. A Transaction Does Not Start Just Because a `MessageChannel` Exists

`DirectChannel` is a synchronous dispatch mechanism—it **does not start a database transaction**. `QueueChannel` does not bind messages to a database transaction by default either. A transaction must be opened by a `@Transactional` proxy, `TransactionTemplate`, transaction advice on a polling endpoint, or an application-configured equivalent.

## 3. Four Questions That Decide Rollback

When investigating "the final handler failed yet the DB still has data," walk through in order:

1. **Was a transaction actually opened?** Verify `@Transactional` was applied via a Spring AOP proxy, with the right manager and thread.
2. **Did the DB operation actually join that transaction?** Verify `DataSource`/`EntityManager`, propagation, and transaction manager.
3. **Did the downstream handler execute before the transaction committed?** Distinguish `DirectChannel` from async paths, job queues, and remote side effects.
4. **Was the exception recognized by rollback rules and propagated to the boundary?** Could a catch block, recovery callback, error handler, or exception translation have altered it?

If any answer is "no," rollback of that result **is not guaranteed**. Even if all four are "yes," tests must still verify DB state and external effects.

### 3.1. Common Illusions

- **An exception was logged** does not mean the transaction rolled back.
- **An `ErrorMessage` was published** does not prove whether the transaction committed or rolled back.
- **A method has `@Transactional`** does not prove calls passed through the proxy.
- **Being in the same flow** does not prove sharing the same thread or transaction.
- **A message was redelivered** does not mean all prior side effects were undone.
- **An HTTP timeout** does not prove the target server failed to create the order.

## 4. Synchronous `DirectChannel`: The Easiest Case for Rollback

### 4.1. Call Stack and Transaction

Suppose a `@Transactional` service sends a `Message` to a `DirectChannel`, `H1` writes via JDBC, `H2` throws a `RuntimeException`, and everything executes synchronously on the caller's thread:

~~~mermaid
sequenceDiagram
    participant Caller as Transactional service
    participant TX as JDBC TransactionManager
    participant D as DirectChannel
    participant H1 as H1 - JDBC INSERT
    participant H2 as H2 - downstream
    Caller->>TX: begin transaction
    Caller->>D: send message
    D->>H1: handle
    H1->>TX: INSERT order (uncommitted)
    H1->>H2: dispatch synchronously on same thread
    H2--xH1: RuntimeException
    H1--xD: propagate exception
    D--xCaller: propagate exception
    Caller->>TX: rollback
    TX-->>Caller: INSERT is not committed
~~~

The diagram assumes the exception is not swallowed, `H1` truly participates in the transaction, and no non-DB external work committed. `H2` is a "downstream handler" in processing order, not necessarily called directly by `H1` in Java code: Spring Integration wires endpoints via `DirectChannel`.

### 4.2. Why Does `DirectChannel` Preserve the Boundary?

`DirectChannel` dispatches calls synchronously to its subscriber. The final handler can throw an exception on the **same call stack**; the exception returns to the sender before the `@Transactional` method exits. The transaction interceptor sees the error and rolls back per its rules.

Contrast this with:

~~~text
Transactional sender
   -> ExecutorChannel.send(M)
      -> returns after dispatch/acceptance
   -> transaction commits

Executor thread (later)
   -> downstream handler fails
   -> exception cannot travel backward in time
      to undo transaction already committed
~~~

### 4.3. The Boundary Ends at the Method, Not the Channel Name

Even `DirectChannel` cannot roll back if:

- The caller has no active transaction;
- `H1` starts `REQUIRES_NEW` and commits before `H2` fails;
- `H1` uses a `DataSource` not managed by the active transaction manager;
- `H1` made an external HTTP call outside the DB transaction;
- The exception is caught and handled as success inside the transaction scope;
- The flow switches threads after `H1` and the error surfaces only after the caller returns.

## 5. Java Pattern: `@Transactional` Wrapping a `DirectChannel` Send

### 5.1. Project Assumptions

The application uses Spring Boot/Spring Integration, Spring JDBC, a `DataSource`, and a transaction manager for the same database. A test table:

~~~sql
CREATE TABLE integration_orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

### 5.2. Synchronously Wired Two-Handler Flow

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;

record OrderCommand(String orderId) {}

@Configuration
@EnableIntegration
class OrderRollbackFlowConfiguration {

    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderRollbackFlow(JdbcTemplate jdbcTemplate) {
        return IntegrationFlow.from("ordersInput")
                .handle((payload, headers) -> {
                    OrderCommand command = (OrderCommand) payload;
                    jdbcTemplate.update(
                            "INSERT INTO integration_orders(order_id, status) " +
                            "VALUES (?, ?)",
                            command.orderId(), "RECEIVED");
                    return command; // Forward to the next handler.
                })
                .handle((payload, headers) -> {
                    throw new IllegalStateException(
                            "Simulated downstream failure");
                })
                .get();
    }
}
~~~

In Java DSL, the first handler must **return a `Message` or payload** so the chain forwards to the next handler. A one-way `MessageHandler` that consumes input without returning a reply ends the flow there. This example uses a `GenericHandler` returning the payload to demonstrate the synchronous path.

### 5.3. Transaction Entrypoint

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderSubmissionService {

    private final MessageChannel ordersInput;

    OrderSubmissionService(MessageChannel ordersInput) {
        this.ordersInput = ordersInput;
    }

    @Transactional
    public void submit(OrderCommand command) {
        boolean accepted = ordersInput.send(
                MessageBuilder.withPayload(command).build());
        if (!accepted) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

Spring's transaction interceptor opens a transaction when this public method is called **through a Spring-managed proxy**. The JDBC handler uses the matching `JdbcTemplate`/`DataSource`; `H2` throws `RuntimeException` before `submit` returns, causing the DB to roll back under default rollback rules.

### 5.4. Conditions for This Example to Work Correctly

- A real `DataSource`/transaction manager must exist; `@Transactional` does not create a "magic transaction."
- `OrderSubmissionService` is obtained from the Spring context and called from another bean, not self-invoked bypassing the proxy.
- The channel is a `DirectChannel` with no async boundary between handlers.
- The JDBC handler uses the **exact `DataSource` managed by the transaction manager**.
- No catch block swallows the exception and returns normally.
- The database table is created before testing; the snippet illustrates the logic only.
- If multiple `MessageChannel` beans exist, inject with `@Qualifier` to avoid wiring the wrong channel.

### 5.5. Wrapped Exceptions

Spring Integration may wrap a `Throwable` in `MessagingException`/`MessageHandlingException`. What matters is that the transaction interceptor sees an **exception matching its rollback rules**. `RuntimeException` typically triggers rollback by default; checked exceptions require explicit configuration. Never rely blindly on wrapper types when business logic performs exception translation.

## 6. Transactional Pollers: Rollback on Errors in a Polling Task

### 6.1. Poller Transaction Boundary

File/SFTP/JDBC inbound adapters and polling consumers can be configured so the scheduler initiates a transaction around **the polling task's unit of work**. Spring Integration Java DSL provides `PollerSpec` and supports attaching transaction advice / a transaction manager per version API.

~~~mermaid
flowchart TD
    S["Scheduler tick"] --> TX["Begin transaction advice"]
    TX --> POLL["Poll MessageSource / PollableChannel"]
    POLL --> H1["H1: JDBC insert/update"]
    H1 --> H2["H2: downstream synchronous handler"]
    H2 --> D{"Throw exception?"}
    D -->|"No"| COMMIT["Commit transaction"]
    D -->|"Yes, propagated"| ROLLBACK["Rollback transaction"]
    ROLLBACK --> ERR["Error handling/reporting, per config"]
~~~

The diagram presents the concept: **advice ordering, error handler setup, and thread boundaries** determine whether rollback happens before or after error publishing. Never assume every exception goes to the global `errorChannel`.

### 6.2. Java DSL Configuring a Transactional Poller

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.integration.core.MessageSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class TransactionalPollingFlow {

    @Bean
    IntegrationFlow transactionalImport(
            MessageSource<?> source,
            JdbcTemplate jdbc,
            PlatformTransactionManager dbTransactionManager) {

        return IntegrationFlow.from(
                        source,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)
                                        .transactional(dbTransactionManager)))
                .handle((payload, headers) -> {
                    jdbc.update(
                            "INSERT INTO integration_orders(order_id, status) " +
                            "VALUES (?, ?)",
                            String.valueOf(payload), "IMPORTED");
                    return payload;
                })
                .handle((payload, headers) -> {
                    throw new IllegalStateException(
                            "Downstream validation failed");
                })
                .get();
    }
}
~~~

This is a **configuration sample** requiring a compatible source bean and payload type; it is not a standalone runnable app. In production, do not use `String.valueOf(payload)` as a business key if `MessageSource` returns a `File` or complex object. Persist real business keys and ensure idempotency.

**Key takeaway:** transaction advice on a poller can wrap synchronous JDBC handlers in the same task. However, it **does not automatically roll back File/SFTP state or an in-memory `QueueChannel`** just because SQL rolled back.

### 6.3. When the Error Handler Sits Outside Transaction Advice

If a poller exception passes through a transaction interceptor and the interceptor rolls back **before** an outer error publisher catches the `Throwable`, an `ErrorMessage` may be published *after the DB rollback has already happened*. That is valid.

Conversely, if an error handler or recovery callback **catches the exception inside the transaction's responsibility scope** and returns as success, the transaction may commit unless marked rollback-only. Never draw conclusions merely from seeing an `ErrorMessage`. Verify interceptor ordering, handlers, and actual transaction state.

### 6.4. Controlling Source Data

With a JDBC polling source, a transaction can govern querying, claiming, and updating rows appropriately. With File/SFTP, the filesystem and SSH server do not automatically join the JDBC transaction. With `QueueChannel`, receive semantics differ between in-memory and persistent `MessageStore`s. **DB rollback does not automatically return a message to its source**.

## 7. Asynchronous Boundaries: Where Rollback Is Most Often Misunderstood

### 7.1. `ExecutorChannel` Changes the Thread and Failure Timing

A flow can run `H1` synchronously and then hand off via `ExecutorChannel`:

~~~mermaid
sequenceDiagram
    participant C as Caller + JDBC transaction
    participant H1 as H1 - DB write
    participant E as ExecutorChannel
    participant W as Worker thread
    participant H2 as H2 - downstream
    C->>H1: Insert order
    H1->>E: Send message
    E-->>H1: Accepted for asynchronous dispatch
    H1-->>C: Return
    C->>C: Commit JDBC transaction
    E->>W: Execute later
    W->>H2: Handle
    H2--xW: Exception
    Note over W: Exception cannot roll back C's commit
~~~

When the executor thread receives the message, it **does not automatically inherit the caller's `ThreadLocal` transaction context**. The caller's transaction has usually already ended; an exception in the worker affects only a separate transaction if the worker configures one.

**Warning:** An `ExecutorChannel` might be configured with a rejection policy (`CallerRunsPolicy`) that runs the task on the caller thread or fails at dispatch time. Behavior differs then; never design transactions around fixed assumptions without checking executor and rejection settings.

### 7.2. Similar Boundaries

| Boundary | What changes | How to maintain consistency |
|---|---|---|
| `QueueChannel` | Message queued/received at a different time | Durable queue/inbox, consumer transaction |
| `ExecutorChannel` | Different executing thread | Separate worker transaction, idempotent commands |
| `PublishSubscribeChannel` with executor | Subscribers may run concurrently | Do not rely on global ordering or one shared transaction |
| Reactive / Flux pipeline | Publisher and subscriber use different schedulers | Matching reactive transaction model and explicit completion |
| HTTP async request/callback | Remote executes outside call stack | Request IDs, idempotency, reconciliation |
| Kafka producer callback | Acknowledgement arrives after the send call | Outbox, retries / producer error strategy |
| JMS/AMQP listener | Broker/container manages message lifecycle | Transactions/acks, inbox/deduplication |

### 7.3. Do Not Stretch a JDBC Transaction Across Network Calls Unnecessarily

Holding a DB transaction open while HTTP waits for seconds pins connections and locks, raising contention, pool exhaustion, and deadlock risks. When the remote call is critical, it is usually safer to:

1. Commit local state and an **outbox command** in one DB transaction;
2. Have a worker read the outbox and call the remote API;
3. Persist outcomes idempotently;
4. Retry or compensate per business rules.

This is not an atomic guarantee between DB and HTTP; it is an **eventual consistency model with recoverable state**.

### 7.4. Rollback Does Not "Travel" Inside Message Envelopes

A Spring `Message` carries payload and headers; it does not carry a distributed transaction context capable of committing/rolling back across arbitrary systems. Putting a transaction ID in a header **does not enroll downstream HTTP/SFTP calls into the transaction**.

## 8. Exception Propagation, Rollback Rules, and Propagation Behavior

### 8.1. Default Rollback Rules

With Spring's `@Transactional`, the common default rolls back when **`RuntimeException` or `Error`** escapes the method and does not roll back for checked exceptions unless configured otherwise. Identify the real exception the transaction interceptor observes.

~~~java
import java.io.IOException;
import org.springframework.transaction.annotation.Transactional;

class OrderProcessingService {

    @Transactional
    public void processWithUncheckedFailure() {
        writeDatabase();
        throw new IllegalStateException("Downstream failure");
        // RuntimeException: rolls back under default rules.
    }

    @Transactional(rollbackFor = IOException.class)
    public void processWithCheckedFailure() throws IOException {
        writeDatabase();
        throw new IOException("External dependency failed");
        // Checked exception: rolls back because rollbackFor is specified.
    }

    private void writeDatabase() {
        // Must use the transaction-managed DataSource.
    }
}
~~~

This snippet illustrates rollback rules, not a runnable integration flow; the service must be Spring-managed/proxied and `writeDatabase()` must operate on a resource owned by the transaction manager.

### 8.2. Catching an Exception Without Rethrowing

~~~java
@Transactional
public void process() {
    repository.insertOrder(...);
    try {
        downstreamCall();
    } catch (RuntimeException failure) {
        logger.warn("Failed: {}", failure.getClass().getSimpleName());
        // Does not rethrow and does not mark rollback-only.
    }
}
~~~

Unless another component marks the transaction rollback-only, the interceptor sees the method finish normally and commits. **Logging a failure is not a rollback signal**.

If catching an exception to translate it into a business result, decide explicitly:

- Should the entire DB transaction roll back?
- Should the transaction be marked rollback-only?
- Can a business outcome be returned with a valid partial commit?
- Should a recovery task be created in a separate transaction?

Do not casually call `setRollbackOnly()` just to "catch errors": it can trigger `UnexpectedRollbackException` in an outer method expecting a commit. Design rollback policies cleanly and report outcomes to callers.

### 8.3. `REQUIRES_NEW` Does Not Roll Back with the Outer Transaction

Suppose:

~~~text
Outer transaction T1
   -> H1 calls auditService in REQUIRES_NEW transaction T2
      -> T2 commits audit record
   -> H2 throws
   -> T1 rolls back
~~~

The audit record committed in `T2` **is not automatically rolled back** when `T1` rolls back, because `T2` is independent. That may be intentional (persisting audits even when business logic fails), but never mistake it for one unified transaction.

### 8.4. Self-Invocation Bypasses the Spring AOP Proxy

If a bean calls another `@Transactional` method **on itself** via `this.process()`, the call can bypass the Spring proxy; the expected transaction never opens. Fix this by moving the transactional entrypoint to another Spring bean or using `TransactionTemplate`/AspectJ where supported.

### 8.5. Nested Transactions / Savepoints

`NESTED` propagation (when supported by the transaction manager/resource) creates a savepoint inside the outer transaction. That allows rolling back partial DB changes within the supported boundary, **not undoing HTTP calls or published messages**. Do not assume `NESTED` behaves like `REQUIRES_NEW`.

### 8.6. `@TransactionalEventListener` and Post-Commit Callbacks

A listener or callback configured to run **after commit** can throw an exception after the DB has already committed. At that point, the finished transaction cannot roll back. Use an outbox when post-commit processing or retries must be durable.

## 9. `ErrorMessage`, `errorChannel`, and Rollback: The True Relationship

### 9.1. `ErrorMessage` Is an Error Notification, Not a Rollback Command

Spring Integration uses **`ErrorMessage`** carrying a `Throwable` payload. A polling task, executor, or endpoint with an error publisher can send an `ErrorMessage` to an error channel. However, this does not directly drive the transaction manager.

| Error location | Where does the exception go? | Rollback depends on |
|---|---|---|
| Synchronous `DirectChannel` | Usually thrown to sender/caller | Transaction wrapping sender and rollback rules |
| Polling endpoint | Error handler may publish `ErrorMessage` | Ordering of poller transaction advice and error handling |
| `ExecutorChannel` | Worker/executor error strategy | Worker's own transaction and error handling |
| HTTP inbound gateway | May map to error response / error flow | Transaction scope of endpoint/caller |
| JMS/AMQP listener | Container/error handler may receive exception | Ack/transacted session and propagation |
| Kafka listener | Container error handler/recovery per config | Offset/transaction/ack policy |

**Absence of an `ErrorMessage` does not prove no rollback occurred**: a synchronous exception may have rolled back the transaction and propagated to the caller. **Presence of an `ErrorMessage` does not prove rollback occurred**: the error publisher may be reporting a non-transactional or post-commit error.

### 9.2. Where Are Exceptions "Swallowed"?

A recovery callback might:

1. Catch a `Throwable` from `H2`;
2. Send an `ErrorMessage` or log the error;
3. Return without rethrowing.

If that callback runs **inside the transaction boundary** and the transaction isn't marked rollback-only, outer logic may commit. Conversely, if the transaction interceptor already handled the exception and rolled back **before** an outer callback caught it, publishing an `ErrorMessage` won't make the transaction re-commit. Always check **advice ordering and catch locations**.

### 9.3. Observation Rules

Never measure rollback via `ErrorMessage` counts. Instead use:

- Transaction begin/commit/rollback logs in test environments;
- Actual DB state queried after the method/poller finishes;
- Broker acknowledgments/offsets and source state;
- Business keys and event IDs for reconciliation;
- Failure categories, stages, correlation IDs, and retry attempts for debugging.

### 9.4. Never Expose Business Payloads in Logs

An `ErrorMessage` payload may be a `MessagingException` whose `failedMessage` contains HTTP headers, file contents, tokens, or PII. Error subscribers must filter data; never log full `Message.toString()` by default in production.

### 9.5. The `errorChannel` Header Does Not Catch Exceptions

`MessageHeaders.ERROR_CHANNEL` specifies a destination for error publishers that honor that header. Attaching the header to an input `Message` **does not create a transaction, trigger rollback, catch exceptions, or retry**. Configure the poller/gateway/async error handler properly and test error paths.

## 10. JDBC Transactions: Which Operations Actually Roll Back?

### 10.1. Multiple JDBC Handlers Sharing One Transaction

If `H1` inserts an order and `H2` updates inventory using the same **`DataSource`/transaction manager**, running synchronously, and a `RuntimeException` occurs before commit, both SQL changes roll back.

~~~text
BEGIN
    INSERT order-274
    UPDATE inventory reserved += 1
    H3: validate shipment policy -> throws
ROLLBACK

SELECT order-274 -> does not exist
SELECT inventory -> retains pre-transaction value
~~~

Conversely, if `H1` commits on its own or runs in `REQUIRES_NEW`, the order record can survive an outer rollback.

### 10.2. Ensure the Right `DataSource`

A flow might connect to database A and database B via two `DataSource`s. Database A's transaction manager **does not automatically manage** connections to database B. When `H2` throws, A may roll back while B committed.

Distinguish local transactions from distributed consistency. Without supported XA/JTA, consider outbox/saga patterns and reconciliation states.

### 10.3. `TransactionTemplate` for Explicit Boundaries

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

class OrderDatabaseUnit {
    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    OrderDatabaseUnit(TransactionTemplate tx, JdbcTemplate jdbc) {
        this.tx = tx;
        this.jdbc = jdbc;
    }

    void saveOrderAndOutbox(String orderId) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO integration_orders(order_id, status) VALUES (?, ?)",
                    orderId, "PENDING");
            jdbc.update(
                    "INSERT INTO integration_outbox(event_id, order_id) VALUES (?, ?)",
                    "event-" + orderId, orderId);
        });
    }
}
~~~

This snippet assumes a matching outbox schema, both JDBC operations sharing the transaction-managed `DataSource`, and unique constraints preventing duplicates. **Atomicity applies only to the DB**; publishing events to Kafka/AMQP afterward is handled by a worker.

### 10.4. Where Does the Transaction End?

If a `@Transactional` method calls a gateway that dispatches work asynchronously and returns, the transaction may commit **before** the downstream task runs. If the method calls a `DirectChannel` and the final handler throws on the same call stack, the transaction interceptor still has the chance to roll back.

### 10.5. Isolation Levels and Race Conditions

Proper rollback does not replace isolation or concurrency control. Two workers can read inventory concurrently and write corrupted updates if read-modify-write logic lacks locks, atomic SQL, or versioning. Rollback tests should include concurrency, unique constraints, optimistic locking, and deadlocks.

## 11. File/SFTP: DB Transactions Do Not Revert File Operations

### 11.1. File Inbound Poller

`FileReadingMessageSource` finds files and applies filters (such as accept-once or persistent metadata). Once a file is selected, `H1` writes to DB, `H2` fails, and the DB rolls back. **The filter may have already marked the file as accepted**; the file may not reappear on the next poll.

~~~text
File invoice-274.csv selected
    -> filter state says accepted
    -> JDBC INSERT within transaction
    -> downstream handler throws
    -> JDBC ROLLBACK
    -> file state remains as defined by filter/move policy
~~~

Without durable file state or a replay strategy, the application may log the failure and never reprocess the file. Conversely, resetting filters indiscriminately can create duplicates when the DB actually committed in another scenario.

### 11.2. SFTP Remote Side Effects

SFTP may download, rename, delete, or upload a remote file before a downstream handler fails. **The SSH/SFTP server does not automatically join a JDBC transaction**. To recover:

- Record remote path/identity/version and local file reference;
- Never mark a file "processed" before data has verified commit evidence;
- Provide quarantine, retries, or compensation if files were moved/deleted;
- Reconcile remote state after transfer timeouts;
- Use business keys and idempotency to avoid reprocessing duplicate records.

### 11.3. Transaction Synchronization Is Not Real File Rollback

Spring Integration supports **transaction synchronization** on polling endpoints to run callbacks based on completion status. Some designs use **`PseudoTransactionManager`** to drive `afterCommit`/`afterRollback` callbacks for non-transactional resources; it **provides no real filesystem rollback**.

Example logic:

~~~text
On transaction commit:
    move local file to processed/ (per policy)

On transaction rollback:
    move file to retry/ or failed/ (per policy)

These file operations are callbacks that can fail independently.
Do not treat them as atomic with the database transaction.
~~~

If the app calls a remote SFTP API inside an `afterCommit` callback and it fails, the DB has already committed; use a durable recovery reference or outbox rather than assuming callback failure rolls back the DB.

### 11.4. When a File Contains Multiple Records

Define the transaction unit: one record, one file, or one batch. When committing per record, a downstream failure on record 40 **does not roll back the 39 previously committed records**. Use checkpoints, idempotent upserts, record quarantine, and logic to replay remaining items.

### 11.5. What to Test

| Injection point | State to verify |
|---|---|
| Error before File `Message` is created | No `failedMessage` yet; filter/source does not lose file |
| Error after receive, before JDBC commit | DB rolls back; file can be replayed or quarantined |
| Error after remote rename | DB rollback does not undo remote rename |
| Error inside transaction synchronization callback | Alert/recovery exists for failed callback |
| Crash after commit, before archive | Replay produces no duplicate side effects |
| Two pollers pick the same file | Claim/metadata store prevents duplicate processing per policy |

## 12. HTTP Outbound Gateway: JDBC Rollback Does Not Cancel API Calls

### 12.1. Two Cases That Must Be Separated

Suppose `H1` writes JDBC and `H2` calls HTTP POST `CreateShipment`.

**Case A — HTTP clearly fails before the target processes it:** `H2` throws an exception inside the synchronous transaction; JDBC rolls back. Safe retries still require error classification and protecting other side effects.

**Case B — HTTP succeeded at the target, yet the caller timed out:** `H2` throws, JDBC rolls back; the shipment at the partner **may still exist**. Retrying `H1`/`H2` without idempotency risks creating a duplicate shipment.

~~~mermaid
sequenceDiagram
    participant TX as Local DB transaction
    participant H as HTTP outbound gateway
    participant P as Partner API
    TX->>TX: INSERT pending order
    TX->>H: CreateShipment(orderId)
    H->>P: POST /shipments (requestId=R274)
    P->>P: Commit shipment S274
    Note over P,H: Response lost / network timeout
    H--xTX: Timeout exception
    TX->>TX: ROLLBACK order insert
    Note over TX,P: Local rollback does not delete shipment S274
~~~

### 12.2. HTTP Statuses and Exceptions Depend on the Client

Never assume every 4xx/5xx throws a `MessageHandlingException`. Depending on the HTTP client, error handler, and Spring Integration gateway config, statuses may map to exceptions or replies. Rollback tests should force the handler to **throw the expected exception** and check business outcomes on a fake server.

### 12.3. Idempotency and Unknown Outcomes

For resource-creating endpoints:

- Send a **stable request ID / idempotency key** tied to business intent if the API supports it.
- Persist correlation and real target IDs upon receiving results.
- On timeouts with unknown results, mark `RESULT_UNKNOWN` and **query the partner** before retrying.
- If a resource was created yet the business flow must abort, run **compensation** like `CancelShipment`; do not call it a JDBC rollback.
- Enforce a retry budget and backoff; never multiply uncoordinated retries across client, handler advice, poller, and worker.

### 12.4. HTTP Inbound Gateway and Error Responses

A synchronous HTTP inbound gateway can catch exceptions from a downstream `DirectChannel` and map them to 4xx/5xx responses per contract. Yet returning an HTTP error status **does not prove DB rollback**: a transaction may have committed before the response was built, or writes occurred outside any transaction.

If the API processes asynchronously and returns `202 Accepted`, later failures require status queries/callbacks/events; you cannot "send an HTTP 500" on an already-closed request.

### 12.5. Transaction Scope Best Practice

Avoid holding long JDBC transactions across multiple remote HTTP calls. When external actions must run reliably, save the intent in an outbox, commit the DB, and let a worker call HTTP via an idempotent protocol; embrace eventual consistency with clear state tracking.

## 13. JMS: Listener Transactions, Acknowledgments, and Downstream Failures

### 13.1. Message-Driven JMS Inbound Differs from Polling Consumers

JMS inbound adapters/gateways typically use a listener container to manage message receipt; handler exceptions can propagate to the container. When the container uses a **transacted JMS `Session`** or configured transaction, session rollback lets the broker **redeliver** the message. Exact behavior depends on provider, container, acknowledgment/transaction mode, and exception handling.

Never slap a "Spring Integration transaction" label onto JMS and assume it is atomic with JDBC. A local JMS transaction and a local DB transaction are separate resources unless a supported coordination mechanism is configured.

### 13.2. Two Coexisting Transactions

~~~mermaid
flowchart TD
    BROKER["JMS broker: order-274"] --> LISTENER["JMS listener"]
    LISTENER --> H1["JDBC write (DB TX)"]
    H1 --> H2["Downstream handler"]
    H2 --> DEC{"Exception propagated?"}
    DEC -->|"Yes"| DBRB["DB TX rolls back if still open"]
    DEC -->|"Yes"| JMSRB["JMS session rolls back if container transacted and policy requires"]
    DEC -->|"No, handled"| MAY["Container may treat processing as successful"]
    JMSRB --> REDELIVERY["Broker redelivery per provider policy"]
    DBRB --> VERIFY["Verify DB and side effects"]
~~~

**Bottom line:** inspect **both the DB transaction and JMS delivery state**. If using resource-manager-specific or XA/JTA transactions, behavior differs; do not treat the diagram above as a default two-phase commit.

### 13.3. When Error Handlers Swallow Exceptions

Suppose the JDBC insert fails. The handler catches the error, emits an `ErrorMessage`, and returns without propagating. If the container treats normal return as success, the JMS message **may be acknowledged/committed** and never redelivered, leaving no order in the DB.

If broker redelivery is desired, define clear **throw/rollback** policies. If **acking the source after persisting a durable recovery task** is desired, verify the recovery task is safely stored before acking—not merely an in-memory `ErrorMessage`.

### 13.4. Essential Tests

| Scenario | Verification |
|---|---|
| Handler throws before DB commit | DB rolls back, broker redelivers per policy |
| Handler throws after a separate DB TX already committed | Redelivery does not create duplicate DB inserts |
| Error handler catches without rethrowing | Check actual ack/rollback; do not guess |
| Retries exceed threshold | DLQ/redelivery policy and business record presence |
| Broker failover mid-transaction | No message loss outside contract |
| Listener restarts after credential rotation | In-flight messages recover, idempotency works |

### 13.5. Ordering and Poison Messages

JMS rollback/redelivery can impact ordering and throughput, especially with multiple consumers. A poison message must not redeliver forever, yet routing it to a DLQ can introduce a **business gap**. Decide how subsequent messages sharing the same business key should behave.

## 14. AMQP/RabbitMQ: Ack, Nack, Requeue, and DB Rollback

### 14.1. The AMQP Listener Container Controls Delivery

AMQP inbound adapters typically rely on the Spring AMQP listener container. When a downstream handler throws, the container and configured advice/error handlers decide whether the message is acked, nacked, rejected, requeued, or dead-lettered. This **does not synchronize automatically with a JDBC transaction**.

Example:

~~~text
RabbitMQ queue: OrderCreated(E274)
    -> Listener receives
    -> JDBC inserts order, commits
    -> HTTP handler fails
    -> Rabbit listener requeues message
    -> Redelivery inserts order again -> duplicate key / duplicate effect
~~~

Fixing this requires more than tweaking requeue: implement an **idempotent consumer**, clean transaction boundaries, and safe external side-effect handling.

### 14.2. AMQP Transactions Are Not Identical to JDBC Transactions

RabbitMQ channel transactions, publisher confirms, and consumer acknowledgments follow their own mechanisms. When backend DB commits and broker acks happen in two steps, a crash between them produces duplicate deliveries. Enabling AMQP transactions does not prove exactly-once business processing.

### 14.3. Error Channels Do Not Replace Broker DLQs

Sending a Spring `ErrorMessage` to `errorChannel` does not automatically cause RabbitMQ to route the original delivery to a DLQ. DLX/DLQ, nack/requeue, and poison-message handling must be configured at the broker/container level; verify redelivery metadata and final disposition.

### 14.4. When to Keep DB Transactions Short

If a handler must publish an outbound AMQP message after a JDBC update, use a **transactional outbox** when post-commit delivery must be guaranteed. If publishing succeeds and then the DB rolls back, downstream consumers see an event whose backing DB data never existed; an outbox prevents this inconsistency when properly implemented.

### 14.5. Key Tests

- DB rolls back while consumer avoids acking / triggers redelivery per policy;
- DB commits, then process crashes before ack;
- Nack/requeue causes multiple redeliveries;
- Broker exchange/queue permission errors and network failures before/after publish;
- Downstream pub/sub creates side effects then fails;
- Outbox publisher crashes after broker accept before marking sent;
- DLQ holds records requiring reconciliation, not treated as resolved.

## 15. Kafka: Transactions, Offsets, and Asynchronous Downstream Handlers

### 15.1. Kafka Listeners Do Not Automatically Join JDBC Transactions

Spring Integration Kafka adapters use Spring for Apache Kafka containers/producers. Kafka supports transactions covering Kafka producers and offsets in supported topologies, yet **Kafka transactions do not automatically include DBs or HTTP**.

A downstream handler failure may:

- Propagate to the listener container, triggering error handlers/retries;
- Be recovered/routed to a DLT per policy with an independent offset commit decision;
- Happen after the flow crossed an `ExecutorChannel`, after the listener already returned;
- Happen after a DB commit or HTTP call, where Kafka rollback cannot undo external effects.

### 15.2. Offset Commits Are Separate State from DB State

~~~text
Kafka partition P0 offset 100
    -> listener receives
    -> DB INSERT order-274 commits
    -> application crashes before offset commit
    -> consumer restarts
    -> offset 100 may be redelivered
~~~

Without idempotency, the order may be inserted twice. Conversely, if the offset commits before async work is safely persisted, a later handler failure causes **business-level message loss**.

### 15.3. Kafka Transaction Rollback Does Not Erase Records Already Seen by Other Consumers

Kafka transactions provide isolation/`read_committed` semantics for transactional records under proper configuration. However, an already-sent HTTP request or committed JDBC transaction **is not rolled back by a Kafka transaction**. Separate Kafka-only atomicity from end-to-end business processing.

### 15.4. Producer Callback Fails After DB Transaction

If JDBC `H1` commits and an outbound Kafka producer sends asynchronously, a callback may report failure later. The exception cannot travel back in time into the committed JDBC transaction. Design an outbox and publisher worker with retries, final dispositions, tracing, and idempotent consumers.

### 15.5. Error Handlers / DLTs Do Not Roll Back SQL

Spring for Apache Kafka provides container error handlers (such as `DefaultErrorHandler` depending on version). A DLT isolates failing records per policy; **sending a record to a DLT does not roll back prior DB writes**. Test fault injection at commit and offset boundaries.

### 15.6. Partition Ordering

Kafka orders records by offset within each partition, not globally across partitions. If a listener hands records off to an async executor or retries individual records, business commit order can diverge from offset order. Test **per-key versioning, retry gaps, and late callbacks** alongside transaction rollbacks.

## 16. Retry Advice: Can Alter Transaction Behavior

### 16.1. Retry Before Rollback or Rollback Then Retry?

Two logical arrangements:

~~~text
Option A:
Retry advice
    -> Transaction advice
        -> Handler
    Each attempt opens/rolls back its own TX if configured that way.

Option B:
Transaction advice
    -> Retry advice
        -> Handler
    Multiple attempts may execute within a TX scope.
~~~

**Advice/interceptor order matters.** With DB errors marking a transaction rollback-only, retrying inside the same transaction is futile or causes `UnexpectedRollbackException`. Retrying outside the transaction typically gives each attempt a fresh transaction, though you must consider prior side effects and idempotency.

### 16.2. Retries Are for Recovery, Not a Substitute for Rollback

| Error type | Handling approach |
|---|---|
| Transient DB connection error before commit | Roll back, then retry transaction with backoff |
| JDBC deadlock | Bounded retry in a fresh transaction |
| Permanent data validation error | Roll back/quarantine; do not retry forever |
| Duplicate `eventId` | Deduplicate; treat as handled if invariants hold |
| HTTP timeout, unknown outcome | Reconcile/idempotent retry; do not only roll back DB |
| Permission/authentication denied | Fix credentials/ACLs; limit retries |
| Kafka producer callback fails after DB commit | Outbox retry; never fake SQL rollback |

### 16.3. Recovery Callbacks and Rollback

If retry advice includes a recovery callback that publishes an `ErrorMessage` and returns normally, the final exception may not reach an outer transaction interceptor as expected. Conversely, inner transaction advice per attempt may already have rolled back before the recovery callback runs. Verify **actual rollback rules, advice ordering, and recovery policies** with integration tests.

### 16.4. Total Retry Budget

Suppose the HTTP client retries 3 times, Spring Retry advice retries 4 times, and the message broker redelivers 5 times. Remote calls can multiply dramatically and cause duplicate side effects. Enforce a **business attempt budget** or clearly assign retry ownership per stage.

### 16.5. After Retries Are Exhausted

Do not merely log. Define:

- `RETRY_EXHAUSTED` with error category;
- Quarantine/DLQ/DLT per adapter (DLT for Kafka);
- Durable recovery reference and owner;
- Resolution deadline/SLA;
- Evidence of whether the DB transaction rolled back or committed;
- External side effects needing reconciliation or compensation.

## 17. Outbox, Inbox, and Compensation: When Local Rollback Isn't Enough

### 17.1. The Dual-Write Problem

A handler both writes to a database and publishes to a broker:

~~~text
BEGIN DB TX
    INSERT order
    Publish OrderCreated to Kafka
COMMIT DB TX
~~~

What can happen:

1. Kafka publish succeeds, DB commit fails → consumers saw an event for a non-existent order.
2. DB commit succeeds, Kafka publish fails → order exists without an event.
3. DB commit succeeds, producer times out even though broker saved the event → retry may send a duplicate.

A local transaction does not eliminate these three possibilities.

### 17.2. Transactional Outbox

Persist **business state and outbox intent** in one DB transaction:

~~~mermaid
flowchart LR
    IN["Inbound event"] --> TX["Local DB transaction"]
    TX --> ORD["Order row"]
    TX --> OUT["Outbox row"]
    ORD --> C["DB commit / rollback with OUT"]
    OUT --> C
    C --> WORK["Publisher worker"]
    WORK --> MSG["Kafka / AMQP / HTTP"]
    MSG --> ACK["Confirm and mark sent / retry"]
~~~

An outbox prevents the state where **the DB committed without recording send intent** when the schema and transaction are implemented properly. However, the worker can still crash **after publishing and before marking sent**, so idempotent receivers or deduplication remain essential.

### 17.3. Transactional Inbox / Idempotent Consumer

When receiving JMS/AMQP/Kafka messages, store the **processed event ID and business state** atomically in the DB if using the same `DataSource`. On broker redelivery, the consumer checks `eventId` and skips repeating the DB side effect.

Pseudocode example:

~~~text
transaction:
    if inbox.contains(eventId):
        return ALREADY_PROCESSED
    validate expectedVersion
    apply business state change
    insert inbox(eventId, outcome)
    commit

ack source according to broker/container policy
~~~

A crash window remains between DB commit and broker ack, yet redeliveries are deduplicated. If the side effect involves external HTTP calls, a DB inbox alone is insufficient—you also need remote idempotency/reconciliation.

### 17.4. Compensation for Already-Committed Side Effects

An order was created at the shipment service, and then a downstream billing handler failed. You cannot use a SQL `ROLLBACK` to cancel the shipment. Issue a **compensation command**:

~~~json
{
  "commandId": "cancel-shipment-order-274",
  "sagaId": "saga-274",
  "operation": "CANCEL_SHIPMENT",
  "targetReference": "shipment-S274",
  "idempotencyKey": "saga-274-cancel-shipment-v1",
  "status": "PENDING",
  "reason": "BILLING_STEP_FAILED"
}
~~~

This is an illustrative business schema, not a built-in Spring Integration DTO. The compensation step must verify saga ownership, permissions, cancellation windows, and real outcomes. HTTP `202` may mean only "accepted," not yet cancelled.

### 17.5. Not Every Downstream Error Requires Compensation

If the event broker is temporarily unavailable while the business goal remains valid, retry the outbox instead of immediately cancelling the order. If input validation fails before any side effect, no compensation is needed. If a timeout leaves an unknown outcome, **reconcile first** to avoid compensating erroneously.

### 17.6. Driving Decisions by Business State

| State | Action |
|---|---|
| `DB_TX_ROLLED_BACK` | Input needs replay/abort per source policy |
| `DB_COMMITTED_OUTBOX_PENDING` | Publisher retries; do not blindly re-run the DB transaction |
| `REMOTE_OUTCOME_UNKNOWN` | Query status; never invent arbitrary new request IDs |
| `COMPENSATION_REQUIRED` | Persist a durable compensation command |
| `COMPENSATING` | Worker executes each compensation step with retries/ownership |
| `COMPENSATED` | Actual compensation verified |
| `MANUAL_REVIEW` | Insufficient evidence to retry or compensate safely automatically |

These state names are application-defined, **not a built-in Spring Integration enum**.

## 18. Transaction Synchronization and Source State

### 18.1. Transaction Completion Does Not Equal Source Message Completion

When a poller reads File/SFTP/JDBC or `QueueChannel`, "receiving a `Message`" differs from "DB committed" and from "source marked processed." The application must define when source state transitions:

- File: move from inbox to processed/failed only after verified business outcomes;
- SFTP: remote rename/delete or archive after confirmation;
- JDBC: transition row `PENDING` → `PROCESSING` → `PROCESSED`/`RETRY`;
- `QueueChannel`: persist durable command/ack state rather than relying solely on in-memory removal;
- Broker listener: ack/offset aligned with the transaction/recovery contract.

### 18.2. Post-Commit and Post-Rollback Callbacks

Spring transaction synchronization can invoke callbacks on commit/rollback. That helps coordinate file moves or cleanup, **but callbacks do not join filesystem or HTTP transactions**.

If a post-commit callback fails, JDBC changes remain committed. If a post-rollback callback fails, the file may sit in an intermediate location. Maintain metadata, durable recovery references, and alerts.

### 18.3. What Is `PseudoTransactionManager`?

For non-transactional sources (File/SFTP), some Spring Integration setups use **`PseudoTransactionManager`** to supply a transaction synchronization context for `afterCommit`/`afterRollback` callbacks. However, **no real resource manager is rolled back by a pseudo transaction**.

Never use `PseudoTransactionManager` to claim "file download, SFTP rename, and JDBC insert are atomic." If JDBC rollback is needed, use a real JDBC transaction manager and manage file state explicitly.

### 18.4. Business Unit Determines Rollback Scope

A file containing 1,000 records:

- If all-or-nothing is required, process DB work inside one transaction when size and resources permit; still protect the source file.
- If processing in small batches, each committed batch is a checkpoint; a later batch failure **does not roll back prior batches**.
- If each record has an idempotent business key, the file can be replayed while skipping/verifying already-committed records.

Never hold an overly long DB transaction just to "look like an atomic file import" if it causes locks, pool exhaustion, or timeouts.

## 19. Testing Rollback Against a Real JDBC Database in a Spring Context

### 19.1. Test Goals

The core test must prove:

1. `H1` actually executes `INSERT` while a transaction is active.
2. `H2` throws an exception **before commit** on the same call stack.
3. The exception reaches the `@Transactional` entrypoint.
4. The transaction manager rolls back.
5. Afterward, querying from another transaction **does not see** the record.

Checking "an exception was thrown" without querying the DB afterward **does not prove rollback**.

### 19.2. JUnit 5 Checking Both Exception and Data

The example below uses the `OrderSubmissionService`, `OrderRollbackFlowConfiguration`, and `integration_orders` table from section 5 in a test context with Spring's JDBC transaction manager:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        OrderRollbackFlowConfiguration.class,
        OrderRollbackTestInfrastructure.class
})
class OrderRollbackIntegrationTest {

    @Autowired
    OrderSubmissionService submission;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clearRows() {
        jdbc.update("DELETE FROM integration_orders");
    }

    @Test
    void downstreamFailureRollsBackJdbcInsert() {
        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> submission.submit(new OrderCommand("order-274")));
        Throwable root = thrown;
        for (int i = 0; i < 32 && root.getCause() != null; i++) {
            if (root.getCause() == root) {
                break;
            }
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM integration_orders WHERE order_id = ?",
                Integer.class, "order-274");
        assertEquals(0, remaining);
    }
}
~~~

This is a component test template: `OrderRollbackTestInfrastructure` must supply `DataSource`, `JdbcTemplate`, transaction manager, `@EnableTransactionManagement`, and the `OrderSubmissionService` bean so Spring applies its proxy. An illustrative H2 in-memory infrastructure can be defined as:

~~~java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
class OrderRollbackTestInfrastructure {

    @Bean
    DataSource testDataSource() {
        return new EmbeddedDatabaseBuilder()
                .setType(EmbeddedDatabaseType.H2)
                .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource testDataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(testDataSource);
        jdbc.execute(
                "CREATE TABLE integration_orders (" +
                "order_id VARCHAR(80) PRIMARY KEY, " +
                "status VARCHAR(30) NOT NULL)");
        return jdbc;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            DataSource testDataSource) {
        return new JdbcTransactionManager(testDataSource);
    }

    @Bean
    OrderSubmissionService orderSubmissionService(
            @Qualifier("ordersInput") MessageChannel input) {
        return new OrderSubmissionService(input);
    }
}
~~~

This is an **H2 learning fixture**: include version-compatible Spring Integration, Spring Test, JUnit Jupiter, Spring JDBC, and H2 dependencies. In real projects, use Testcontainers to test against the target database, and avoid registering duplicate `DataSource` or `TransactionManager` beans. When multiple transaction managers exist, qualify explicitly which manager `@Transactional` uses. The test checks the **root cause** rather than assuming the original exception is always thrown unwrapped, because Spring Integration can wrap it in a `MessagingException`.

### 19.3. Do Not Blindly Put `@Transactional` on This Test

If the test method itself runs inside a Spring Test transaction that rolls back at test end, `COUNT=0` may come from **the test framework's rollback**, not the business entrypoint's rollback. To prove the application path, run the test method **without test-level `@Transactional`** or use `TransactionTemplate`/separate transactions for verification.

### 19.4. Control Test

Another valuable test:

1. Configure `H2` not to throw an exception;
2. Submit another `OrderCommand`;
3. Verify the `INSERT` commits;
4. Enable fault injection in `H2`;
5. Verify the same DB transaction rolls back on failure.

This prevents false positives where the JDBC handler never ran or the SQL `INSERT` always failed before reaching `H2`.

### 19.5. Assert Rollback State, Do Not Rely on Logs

Raising transaction log levels aids debugging, yet assertions should query the DB from a separate connection after the transaction completes. With multiple databases/resources, query each resource; if one sits outside the manager, the test should expose the lack of atomicity.

### 19.6. Test Against the Production DB Engine

In-memory H2 is handy for basic unit/integration tests, yet deadlocks, isolation levels, lock waits, and retries can differ on PostgreSQL/MySQL/Oracle. Maintain integration tests against the real engine or an equivalent environment to verify concurrency, rollbacks, and retries.

## 20. Fault-Injection Matrix by Transaction Boundary

| Case | Fault injection point | What to verify |
|---|---|---|
| T01 | Before transaction begins | No DB side effect; clear source state |
| T02 | After `H1` `INSERT`, before `H2` | JDBC rolls back when exception propagates |
| T03 | `DirectChannel` `H2` throws `RuntimeException` | Exception reaches caller, DB row not committed |
| T04 | `H2` throws checked exception without `rollbackFor` | Observe actual commit/rollback per rules |
| T05 | `H2` exception caught and returns normally | DB may commit; detects flawed policy |
| T06 | `H1` `REQUIRES_NEW` commits, `H2` throws | Inner transaction does not auto-rollback |
| T07 | `H2` behind `ExecutorChannel` | Upstream TX may commit; worker fails separately |
| T08 | Poller receives File, JDBC rolls back | Filter/file source retained/replayed/quarantined properly |
| T09 | SFTP remote rename before DB error | Remote is not auto-undone; recovery defined |
| T10 | HTTP POST remote commits, response lost | DB rolls back while shipment may exist |
| T11 | JMS listener fails and rolls back transacted session | Redelivery/ack and DB state match policy |
| T12 | AMQP listener catches error and returns | Ack/nack/DB state not misassumed |
| T13 | Kafka offset committed before async handler fails | Durable recovery prevents business loss |
| T14 | DB commits, Kafka publish fails | Outbox retains pending event |
| T15 | Publisher crashes after Kafka accept, before marking sent | Consumer deduplicates; no extra side effects |
| T16 | Retry inner/outer transaction advice order flipped | Attempt counts, transaction counts, final state |
| T17 | Error handler itself fails | Fallback exists, recovery reference not lost |
| T18 | App restarts between rollback and source retry | Input remains recoverable without uncontrolled duplicates |
| T19 | Two workers target the same business key | Optimistic locking/idempotency prevents lost updates |
| T20 | Credentials/TLS expire during retries | Failure classified cleanly without a retry storm |

**Note:** fault injection must clean up data, use isolated namespaces/topics, and never hit real production APIs from test commands. Use fake servers/brokers or approved integration environments.

### 20.1. Four Unskippable Crash Points

~~~text
P1  Before external send
P2  After external send but before response
P3  After DB commit but before broker acknowledgment
P4  After broker acknowledgment but before downstream async completion
~~~

At `P2`, the remote outcome may be unknown; at `P3`, the source may redeliver; at `P4`, the message can be lost if async work is not durable. **No single JDBC rollback solves all four windows**.

### 20.2. Testing Execution Ordering

With `ExecutorChannel` or multiple consumers, use a `CountDownLatch`/barrier to force `H2` to throw after `H1` has already returned/committed. This exposes the true transaction boundary. Check event versions, committed state, and retry outcomes—not only log ordering.

## 21. Case Study: SFTP Order Import, JDBC Write, HTTP Call, Kafka Event

### 21.1. Business Context

Platform A receives order files from supplier B over SFTP. Spring Integration polls files every minute, validates data, saves orders in JDBC, creates shipments via partner C's HTTPS API, and publishes `OrderAccepted` to Kafka for billing and analytics.

Requirements:

- Each `orderId` has at most one order record and one corresponding shipment;
- No lost orders if a file was downloaded before DB commit;
- Downstream billing failure must not make the system treat the order as completed;
- Temporary Kafka unavailability must not force cancelling already-valid orders;
- Ability to reconcile HTTP requests sent without receiving a response;
- Auditable evidence across rollbacks, retries, compensations, or manual reviews.

### 21.2. Wrong Version: Assuming One JDBC Transaction Covers the Whole Flow

~~~mermaid
flowchart LR
    S["SFTP poller"] --> P["Parse CSV"]
    P --> DB["JDBC INSERT"]
    DB --> H["HTTP CreateShipment"]
    H --> K["Kafka send"]
    K --> END["Complete"]
    H -. "Failure" .-> ERR["Error flow"]
    K -. "Failure" .-> ERR
    ERR --> RB["Assume ROLLBACK ALL (wrong)"]
~~~

If the DB transaction rolls back after HTTP succeeded, the shipment may still exist. If a Kafka publish reached the broker, a subsequent JDBC rollback does not delete the published Kafka record. If a Kafka callback error arrives late, the DB may already have committed before the callback fires.

### 21.3. Approach 1 — Short DB Transactions + Outbox

Split into steps:

1. **SFTP input:** download the file safely, retain a durable file reference/batch ID; do not mark processed yet.
2. **Local DB transaction:** validate, `INSERT`/`UPSERT` the order, and `INSERT` an outbox `CreateShipment` command in one transaction.
3. **After DB commit:** a worker reads the outbox and calls partner C over HTTPS using `requestId`/idempotency key.
4. **Once shipment is verified:** record shipment status and `OrderAccepted` outbox intent in a local transaction.
5. **Kafka worker:** publish `OrderAccepted`, retry safely, and mark sent after appropriate confirmation.
6. **File state:** archive per policy once business criteria are satisfied, not merely upon receiving an `ErrorMessage`.

If `H1` JDBC fails, rollback discards only **uncommitted local writes**; the file stays tracked via state. If partner C's HTTP call fails, the order remains in pending-shipment status and the worker retries/reconciles. If Kafka fails, the outbox preserves the intent.

### 21.4. Suggested States

| Component | States | Meaning |
|---|---|---|
| Import file | `DETECTED`, `CLAIMED`, `IMPORTED`, `QUARANTINED` | Tracks SFTP source |
| Order | `PENDING_SHIPMENT`, `SHIPMENT_CONFIRMED`, `COMPLETED`, `CANCELLED` | Tracks business lifecycle |
| Outbox | `PENDING`, `IN_FLIGHT`, `SENT`, `RETRY`, `FAILED` | Tracks outbound commands |
| Remote shipment | `UNKNOWN`, `CREATED`, `CANCELLED` | Reconciles partner C side |
| Saga | `RUNNING`, `COMPENSATING`, `COMPLETED`, `MANUAL_REVIEW` | Coordinates side effects |

These states are illustrative design choices, not auto-generated by Spring Integration. Transitions require version checks and auditing, especially when multiple workers handle an order concurrently.

### 21.5. Incident A — Downstream Validation Throws Inside the DB Transaction

~~~text
Begin TX
  -> Insert order-274
  -> Validate duplicate policy
  -> RuntimeException
Rollback TX
  -> order-274 is absent from DB
  -> source file remains tracked via file state
~~~

Tests required:

- Assert the expected exception;
- `SELECT` confirms `order-274` is absent from DB;
- Confirm no outbox event was committed;
- File remains replayable or quarantined per policy;
- No HTTP `CreateShipment` request was sent if validation preceded outbound.

### 21.6. Incident B — HTTP C Creates Shipment, Response Lost

The DB order sits in `PENDING_SHIPMENT`; partner C already created shipment `S274`. The worker times out with an unknown outcome. The coordinator sets `RESULT_UNKNOWN`, queries C by `requestId` or idempotency key, saves the real resource ID, and decides whether to proceed or compensate.

**Do not blindly roll back/DELETE the order and re-send HTTP with a brand-new request ID.** A shipment absent from A's database can still exist at C.

### 21.7. Incident C — Kafka Unavailable After HTTP Success

The `OrderAccepted` outbox remains `PENDING`/`RETRY`. The Kafka worker retries with backoff using a stable event ID. If the outage exceeds the business deadline, coordinate with the owner to cancel/compensate or route to manual review. Never trigger `CancelShipment` solely because a Kafka producer callback failed transiently when policy allows continuing.

### 21.8. Incident D — Worker Crashes After Publish

The Kafka broker received the event, yet the worker crashed before updating outbox to `SENT`. Upon restart, the worker may publish again. The billing consumer must deduplicate by `eventId`/business key. This is **at-least-once delivery with idempotent effects**, not "exactly-once" inferred from DB rollback.

### 21.9. Incident E — SFTP File Marked Accepted by Filter, Then JDBC Rolls Back

The error channel receives `MessageHandlingException`; the app logs it and returns to polling. If the filter already marked the file accepted, the file may not be read again. Maintain persistent import state/retry references and controlled replay rather than merely slapping JDBC transactions onto a File poller.

### 21.10. Invariants to Assert

| Invariant | How to verify |
|---|---|
| One `orderId` never creates two order rows | Unique key + DB query |
| One `orderId` never creates two shipments | Stable idempotency key + remote query |
| No outbox `SENT` without publish confirmation | Outbox state + broker evidence |
| When downstream DB handler fails, uncommitted local writes roll back | Transactional integration test |
| File is never lost after rollback | File state/filter/replay test |
| Duplicate Kafka delivery never bills twice | Consumer inbox/idempotency test |
| Unknown outcome always has a failure owner | Saga state + audit |
| System recovers across restarts | Fault injection + retry backlog verification |

## 22. Observability: Measuring Rollbacks, Transactions, and Message Lifecycles

### 22.1. Essential Signals

| Suggested metric | Meaning |
|---|---|
| `db_transaction_rollback_total` | DB transaction rollbacks by stage/category |
| `db_transaction_commit_total` | DB transaction commits |
| `downstream_handler_failures_total` | Downstream handler failures |
| `integration_error_messages_total` | `ErrorMessage`s published per flow |
| `retry_attempts_total` | Retry attempt count |
| `retry_exhausted_total` | Failures exhausting retries |
| `outbox_pending_count` | Commands/events awaiting publish |
| `inbox_deduplicated_total` | Duplicate messages blocked |
| `source_replay_pending_count` | Files/rows/queue messages needing replay |
| `kafka_consumer_lag` | Consumer group lag |
| `amqp_unacked_count` | Unacked messages if provider metric available |
| `jms_redelivery_total` | Message redeliveries per integration/provider metric |
| `external_result_unknown_count` | HTTP or remote side effects with unknown outcomes |

These names are **instrumentation suggestions**, not all automatically exported by Spring Integration. Define data sources clearly and never infer transaction outcomes from `ErrorMessage` counts.

### 22.2. Business-Correlated Logging

~~~text
flow=orders-sftp-import
businessKey=order-274
messageId=M274
transactionScope=jdbc-orders
stage=DOWNSTREAM_HANDLER
exceptionCategory=TRANSIENT
dbOutcome=ROLLED_BACK
sourceDisposition=RETRY_PENDING
remoteOutcome=UNKNOWN
attempt=2
~~~

**`dbOutcome=ROLLED_BACK`** should only be logged when backed by transaction completion or state checks, not merely because a handler threw. A single message may span multiple transaction scopes; label each accurately.

### 22.3. Never Log Secrets or Sensitive Data

`MessagingException.failedMessage` may contain `File` paths, HTTP `Authorization` headers, Kafka headers, or customer payloads. Error handlers must log minimal metadata—flow, stage, exception class, correlation—mask tokens and PII, and control error-event retention. Never dump full `Message` objects or raw stack traces onto public dashboards.

### 22.4. Impact-Based Alerts

- Unusually high rollback rates;
- SFTP/JDBC poller stalled or missing `last-successful-poll`;
- Aging outbox backlog or rising Kafka lag;
- Spikes in message redeliveries or DLQ volume;
- HTTP `remoteOutcome=UNKNOWN` exceeding SLA;
- Files received without reaching a terminal processing state;
- Transaction commit succeeds yet downstream business confirmation is missing;
- Error handler failing or recovery queue making no progress.

**Zero new `ErrorMessage`s does not prove a flow is healthy**: the poller might be unscheduled or the broker listener might have stopped.

## 23. Runbook: Downstream Failed—Did Rollback Actually Happen?

### Step 1 — Define Scope

Record precisely:

- Source adapter (File/SFTP/JDBC/JMS/AMQP/Kafka/HTTP);
- Flow ID, endpoint IDs, and `MessageChannel` between `H1`/`H2`;
- Transaction manager and managed resources;
- Thread/executor and asynchronous handoff points;
- Business key/correlation ID, timestamp, and observed error.

### Step 2 — Draw the Transaction Timeline

~~~text
t0  Input received
t1  Transaction begin?
t2  JDBC operation H1
t3  Any remote side effect?
t4  H2 fails or async work dispatched?
t5  Transaction commit/rollback?
t6  Source ack/filter/offset updated?
t7  ErrorMessage published / recovery scheduled?
~~~

If `t5` happened **before `t4`**, `H2` cannot roll back the already-completed transaction. If `t4` happened before `t5` yet the exception was swallowed, the transaction may commit unless rollback-only was set.

### Step 3 — Read Exceptions Properly

If an `ErrorMessage` exists:

1. Extract the `Throwable` payload;
2. If it is a `MessagingException`, inspect `failedMessage` if present;
3. Check `originalMessage`, understanding it may be null;
4. Identify the root cause and stage;
5. Do not confuse `ErrorMessage` headers with input `Message` headers;
6. Never log raw payloads or secrets.

If no `ErrorMessage` exists, inspect synchronous caller exceptions or adapter/container error handlers before assuming no error occurred.

### Step 4 — Verify Resource State

| Resource | What to verify |
|---|---|
| JDBC DB | Does the row still exist, what version is it, did the TX commit or roll back? |
| File | Did the filter accept it; was the file moved/deleted/quarantined? |
| SFTP | Was the remote file renamed/deleted/downloaded/processed? |
| HTTP | Did the external API create the resource, and under which `requestId`? |
| JMS | Message ack/rollback/redelivery state per provider? |
| AMQP | Ack/nack/requeue/DLQ and consumer side effects? |
| Kafka | Offset/transaction/DLT and producer publish result? |
| Outbox/inbox | Do the event intent and deduplication record exist? |

### Step 5 — Choose Recovery

- **Uncommitted, DB rolled back cleanly:** retry input if still valid and safe.
- **DB committed, then callback/downstream failed:** outbox retry, compensation, or reconciliation per contract.
- **HTTP outcome unknown:** query external state before retrying.
- **Broker redelivery:** deduplicate by `eventId`/business key.
- **File filter retains file despite DB rollback:** controlled replay or quarantine.
- **Insufficient context:** `MANUAL_REVIEW` with an owner; never fabricate resource IDs.

### Step 6 — Prevent Recurrence

Add tests covering all four crash points, strengthen correlation/idempotency, review transaction advice ordering, verify listener ack policies, and monitor source states. Never "fix" this by opening excessively long global transactions or disabling error handling.

### Step 7 — Close Incident

Close only when terminal business state is evidenced, source messages have a clear disposition, external side effects are resolved/reconciled, and no unowned retries or compensations remain pending. Protect all investigation artifacts according to data classification.

## 24. Common Anti-Patterns

| Anti-pattern | Consequence | Remedy |
|---|---|---|
| Assuming same `IntegrationFlow` means same DB transaction | Upstream handlers commit before downstream errors | Map transaction scope and thread boundaries |
| Adding `@Transactional` yet self-invoking | Interceptor never opens expected transaction | Use a proxy entrypoint or `TransactionTemplate` |
| Calling `DirectChannel` transactional without a manager | JDBC auto-commits each statement | Configure manager and test rollback |
| Expecting `ExecutorChannel` to pass TX across threads | Upstream commits before worker fails | Durable work handoff and worker transactions |
| Writing DB via a `DataSource` outside the manager | One DB commits while another rolls back | Explicit resource management, saga/XA when suitable |
| Using `REQUIRES_NEW` expecting outer rollback to undo it | Inner records remain committed | Understand propagation and independent commits |
| Catching exceptions, logging, and returning normally | Transaction commits despite business failure | Propagate, intentionally mark rollback-only, or persist recovery |
| Treating `ErrorMessage` as proof of rollback | Skips verifying commit state | Inspect transaction completion and DB |
| Treating absence of `ErrorMessage` as no rollback | Misses synchronous exceptions | Inspect call stack and transaction interceptor |
| Setting `errorChannel` header expecting auto-rollback | No transactional effect | Configure transactions and error publishers properly |
| Ordering retry advice wrongly | Retries on a rollback-only transaction | Test advice ordering; separate attempts |
| Retrying every exception infinitely | Poison loops, lockouts, overload | Classify, backoff, budget, quarantine |
| Enabling transactions on File/SFTP expecting file rollback | Lost or duplicate files after errors | Durable file state, sync callbacks, replay policy |
| Using `PseudoTransactionManager` like a real DB manager | No real resource rollback | Use only for synchronization callbacks when appropriate |
| Sending HTTP POST in DB TX expecting DB rollback to delete it | Remote side effect persists | Idempotency / reconciliation / compensation |
| Inferring DB rollback from HTTP 500 | Data may have committed before response | Test database/transaction outcomes directly |
| Acking JMS/AMQP before recovery is persisted | Lost business messages | Durable inbox/recovery and ack policies |
| Requeuing messages after DB commit without dedupe | Duplicate rows and side effects | Idempotent consumers |
| Treating DLQ/DLT as rollback | Record isolated while DB stays unchanged | Business reconciliation |
| Committing Kafka offset before async work is durable | Message lost after crash | Commit/ack aligned with durable completion |
| Expecting Kafka rollback to undo HTTP/JDBC | Cross-system inconsistency | Outbox/inbox/saga |
| Committing DB then publishing directly without outbox | Dual-write gap | Transactional outbox |
| Non-idempotent outbox publisher | Duplicate events after restart | Stable `eventId` and consumer dedupe |
| Asserting only exception thrown in tests | Doesn't prove rollback | Query committed DB state and source |
| Putting `@Transactional` on test and reading inside it | False positive | Separate test transaction from business transaction |
| Testing only H2 when prod runs a different DB | Misses lock/isolation differences | Integration tests on real DB engine |
| Logging full `failedMessage` or `Throwable` | Leaks tokens, SQL params, or PII | Structured safe metadata |
| Closing incident upon seeing `ErrorMessage` | Recovery incomplete | Verify business state and ownership |

## 25. Transaction and Rollback Design Checklist for `IntegrationFlow`

### A. Business Contract

- [ ] Defined the atomic business unit: record, batch, file, order, or workflow.
- [ ] Listed all side effects in order: DB, File, SFTP, HTTP, JMS, AMQP, Kafka.
- [ ] Defined criteria for `COMPLETED`, `FAILED`, `RETRY_PENDING`, or `MANUAL_REVIEW`.
- [ ] Established business keys, `eventId`, correlation IDs, and idempotency policies.
- [ ] Classified permanent errors, transient errors, and unknown outcomes.

### B. Transaction Scope

- [ ] Verified which transaction manager governs each `DataSource`/JMS/Kafka resource.
- [ ] Identified how transactions start: `@Transactional`, `TransactionTemplate`, or poller advice.
- [ ] Verified `@Transactional` entrypoints are invoked via Spring proxies, not self-invoked.
- [ ] Ensured JDBC handlers needing atomicity share the same transaction-managed `DataSource`.
- [ ] Checked no unexpected `REQUIRES_NEW` commits survive outer rollback.
- [ ] Verified exception rollback rules (`RuntimeException`/checked/`rollbackFor`).
- [ ] Ensured exceptions are not swallowed before the interceptor when rollback is required.
- [ ] Avoided confusing transaction synchronization callbacks with real File/SFTP transactions.

### C. Topology and Threads

- [ ] Mapped `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and async endpoints.
- [ ] Clarified whether `H2` runs before or after transaction commit.
- [ ] For pollers, verified how far transaction advice wraps receive and handlers.
- [ ] For `taskExecutor`, callbacks, or `Flux`, configured separate worker transactions/recovery.
- [ ] Configured `ErrorMessage`/`errorChannel` on the right endpoints without mistaking them for rollback APIs.
- [ ] Tested what happens if error handlers or retry recovery callbacks swallow exceptions.

### D. Adapter-Specific Semantics

- [ ] Handled file filters and SFTP remote state when JDBC rolls back.
- [ ] Added idempotency or status-query APIs for HTTP outbound unknown outcomes.
- [ ] Configured matching ack/transaction/redelivery policies on JMS listeners.
- [ ] Configured AMQP ack/nack/requeue/DLQ and tested downstream failures.
- [ ] Tested Kafka offsets/producer transactions/DLT alongside async boundaries.
- [ ] Tested JDBC transactions, isolation, concurrency, unique constraints, and retries.
- [ ] Implemented outbox/inbox to resolve dual-writes and duplicate deliveries.
- [ ] Never promised rollback of committed external side effects; provided compensation where needed.

### E. Testing

- [ ] Unit-tested rollback rules and state machines.
- [ ] Integration-tested `DirectChannel`: `H1` write → `H2` throw → DB row absent.
- [ ] Positive-tested `H1`/`H2` success → DB row committed.
- [ ] Tested failures before/after commit, before/after ack, before/after remote requests.
- [ ] Tested different catch/rethrow exception paths.
- [ ] Verified async downstream failures do not roll back prior DB commits.
- [ ] Verified poller source state when DB rolls back.
- [ ] Tested JMS/AMQP/Kafka redeliveries and duplicate business keys.
- [ ] Tested restarts, outbox/inbox, exhausted retries, and compensation failures.
- [ ] Tested critical paths against the production DB engine and transaction settings.

### F. Operations

- [ ] Defined metrics for commits/rollbacks, retries, source backlog, and outbox lag.
- [ ] Stripped secrets/PII from `ErrorMessage`s and uncontrolled logs.
- [ ] Prepared runbooks to verify DB state, HTTP outcomes, broker acks/offsets, and file states.
- [ ] Assigned owners/deadlines for unresolved recoveries.
- [ ] Required post-incident state evidence, not only error log messages.

## 26. Self-Check Questions

**Question 1.** `H1` runs a JDBC `INSERT` and `H2` throws `RuntimeException` on the same `DirectChannel`, yet there is no `@Transactional` or transaction advice. Can you be sure the `INSERT` rolls back?

**Answer:** No. A synchronous `DirectChannel` does not start a transaction by itself. JDBC may auto-commit; you need a transaction manager and a boundary wrapping both handlers.

**Question 2.** `@Transactional` is on the method calling `DirectChannel`, and `H2` throws before the method returns. What conditions are required for JDBC to roll back?

**Answer:** The transaction must actually open through a proxy, `H1` must participate using the same resource/manager, and the exception must match rollback rules and propagate to the interceptor before commit.

**Question 3.** An exception on an `ExecutorChannel` worker occurs after the sender committed the DB. Can it roll back the earlier commit?

**Answer:** No. The worker runs across a separate async/transaction boundary; you need durable commands, worker-side transactions, retries, or compensation.

**Question 4.** `H1` writes JDBC and `H2` throws a checked `IOException`. Does it roll back by default?

**Answer:** Under traditional Spring defaults, checked exceptions do not trigger rollback unless `rollbackFor` or an equivalent rule is declared. Check exception wrappers and your version's configuration.

**Question 5.** A handler catches `RuntimeException`, logs it, and returns normally. Why might the DB commit?

**Answer:** The transaction interceptor sees the method finish normally unless the transaction was marked rollback-only; logging is not a rollback signal.

**Question 6.** `H1` runs in `REQUIRES_NEW` and commits, then `H2` fails in the outer transaction. Is `H1` rolled back?

**Answer:** Not automatically. The independent inner transaction already committed. Design propagation intentionally.

**Question 7.** A `@Transactional` method calls another `@Transactional` method via `this.method()`. Can you rely on the second transaction opening?

**Answer:** Not with standard proxy-based AOP. Self-invocation bypasses the proxy; use a separate bean entrypoint or another supported mechanism.

**Question 8.** An `ErrorMessage` appears on the global `errorChannel`. Does that prove the DB rolled back?

**Answer:** No. `ErrorMessage` merely carries a published `Throwable`. Inspect transaction completion or committed DB state.

**Question 9.** No `ErrorMessage` is emitted, yet the caller receives a `MessagingException`. Could the DB have rolled back?

**Answer:** Yes. Synchronous errors can propagate back to a `@Transactional` caller, triggering rollback without an error publisher.

**Question 10.** A file poller picks up a file, then the DB rolls back. Will the file definitely be re-polled?

**Answer:** No. File filters/metadata may already have marked it accepted; manage file state and replay policies explicitly.

**Question 11.** Does using `PseudoTransactionManager` with SFTP automatically undo a remote rename?

**Answer:** No. Pseudo transactions drive synchronization callbacks but do not turn a remote filesystem into a transactional resource.

**Question 12.** HTTP `CreateShipment` times out, then the DB rolls back. Can you be sure the shipment does not exist?

**Answer:** No. The server may have created the shipment. Use idempotency keys and status reconciliation before retrying or compensating.

**Question 13.** A JMS listener throws an exception, yet an error handler swallows it. Will the message definitely redeliver?

**Answer:** No. Ack/redelivery depends on container/transaction/error policies; if the container sees success, it may acknowledge the message.

**Question 14.** An AMQP message is nacked/requeued after a DB commit. What can redelivery cause?

**Answer:** Duplicate DB rows/side effects if the consumer is not idempotent. Use an inbox/unique keys and explicit state.

**Question 15.** Does a Kafka transactional producer guarantee rolling back a prior HTTP request?

**Answer:** No. Kafka transactions cover their supported Kafka scope and do not automatically govern remote HTTP or local JDBC outside compatible coordination.

**Question 16.** A Kafka offset committed, then async `H2` fails afterward. Is the source record still available for automatic replay?

**Answer:** Not by default. Persist durable work/recovery records before committing offsets if downstream processing is not finished.

**Question 17.** Why does a transactional outbox still need consumer idempotency?

**Answer:** The publisher can crash after the broker accepts the event and before marking `SENT`, then resend it. Stable `eventId`s and deduplication prevent duplicate side effects.

**Question 18.** Should an inbox deduplication record be written in a separate transaction from the business update?

**Answer:** When both live in the same DB for the same business goal, commit them atomically to avoid windows where one succeeded without the other.

**Question 19.** How does retry advice outside transaction advice differ from retry inside transaction advice?

**Answer:** Outside can create a fresh transaction per attempt; inside may retry on a transaction already marked rollback-only. Test actual advice ordering and policies.

**Question 20.** Should you keep a JDBC transaction open while an HTTP API responds slowly?

**Answer:** Usually avoid it because it holds connections and locks without providing atomicity across HTTP. Consider an outbox and idempotent workers.

**Question 21.** An integration test has `assertThrows` and `COUNT=0`, yet the test method itself is `@Transactional` and rolls back at test end. Does that prove application rollback?

**Answer:** Not yet. It may be Spring Test's rollback. Design the test without unwanted outer test transactions and query after the business transaction ends.

**Question 22.** After `H2` fails, the DB has no order, yet Kafka has `OrderCreated`. What should you do?

**Answer:** Reconcile the dual-write and downstream consumers, emit compensating events if needed, and fix the design with an outbox or proper consistency mechanism.

**Question 23.** Does a record landing in a Kafka DLT or RabbitMQ DLQ mean the DB rolled back?

**Answer:** No. DLQ/DLT are message routing/error-storage mechanisms; DB transactions have independent state.

**Question 24.** Why must you test crashes after DB commit and before broker ack?

**Answer:** The broker may redeliver the message after restart, causing duplicates without idempotency. This is a common failure window.

**Question 25.** What is the most reliable evidence that rollback occurred when a downstream handler failed?

**Answer:** A verified transaction boundary, an exception matching rollback policy, committed DB state free of unauthorized changes, and source/remote/broker states independently verified per contract.

## 27. Conclusion and References

### 27.1. Core Takeaways

Rollback when a downstream handler fails **does not depend on where a handler sits visually in a flow diagram**—it depends on **which resources the transaction manager governs, when commit happens, whether the handler runs inside that boundary, and whether the exception triggers rollback rules**.

In Spring Integration:

1. **`DirectChannel` + synchronous transactions** allow downstream exceptions to trigger upstream JDBC rollback when all calls share the same uncommitted transaction.
2. **Transactional pollers** can wrap synchronous processing in a polling task, yet database rollback does not automatically restore File/SFTP messages to their initial state.
3. **`ExecutorChannel`, `QueueChannel`, and async HTTP/Kafka callbacks** introduce time/thread boundaries; later exceptions cannot roll back commits already completed by the sender.
4. **JMS/AMQP/Kafka delivery states** have their own transaction/ack/error-handler rules and must be tested with realistic broker/container configurations.
5. **Already-executed HTTP/SFTP side effects** require idempotency, reconciliation, or compensation; a single annotation cannot promise rollback across all adapters.
6. **`ErrorMessage`/`errorChannel`** is an error-notification mechanism, neither proof of commit/rollback nor a replacement for durable retry workflows.
7. **Outbox/inbox, unique constraints, transaction-aware retries, state machines, and fault injection** deliver business correctness when no single global transaction exists.

The most important operational habit is **verifying state at each resource's commit point**. A logged exception or a published `ErrorMessage` is never enough to declare a clean rollback, especially alongside remote side effects, broker redeliveries, or async processing.

### 27.2. Further Reading

- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction support, poller advice, and transaction synchronization.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/async exceptions, `ErrorMessage`, and `errorChannel`.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and dispatch semantics.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, AOP proxies, rollback rules, and propagation.
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` and explicit boundaries.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): container error handling, offsets, transactions, retries, and DLT.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): listener acknowledgments, transactions, and DLQs.

**Version note:** Code snippets and diagrams are educational examples for Spring Integration Adapters. Java DSL APIs, poller transaction specs, callback ordering, adapter/container behavior, and JDBC transaction managers may vary across Spring Boot/Spring Integration/JDK/driver versions. Before deploying to production, verify against actual APIs and run integration tests on the target resources. This lesson completes documentation authoring and does not substitute for downstream Content QA.
