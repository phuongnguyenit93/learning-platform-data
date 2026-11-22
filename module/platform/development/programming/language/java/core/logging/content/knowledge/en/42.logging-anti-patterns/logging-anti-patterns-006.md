# Using Logging Instead of Control Flow — An Anti-Pattern in Java Logging

## 1. Nature of the Anti-Pattern

**Using logging instead of control flow** is a design flaw in which an application relies on a log line, a log level, the ability to write logs, or reading back log output to **decide a business branch**. In a Java application, logging is used to **observe** what the program has decided or executed; it does not by itself replace `if`, `return`, `throw`, validation, authorization, transactions, or state machines.

Incorrect example:

```java
// WRONG: warned, yet still executes the side effect.
if (amount > balance) {
    logger.error("Insufficient funds");
}
debitAccount(amount);
```

`logger.error(...)` does not stop the method, does not automatically roll back, and does not cause the caller to receive a rejection result. Without another guard, `debitAccount` still runs.

Correct logic example (snippet in an application with the defined classes):

```java
if (amount > balance) {
    return TransferResult.rejected("INSUFFICIENT_FUNDS");
}

debitAccount(amount);
return TransferResult.succeeded();
```

The orchestration layer can log based on `TransferResult`, but **allowing or preventing the effect** belongs in decision logic, not in the logger. If logging is turned off completely, business rules must still behave correctly.

**An effective thought experiment:** set the log level to `OFF`, remove the appender, or simulate an unavailable collector. If validation, authorization, commit, response, retry, or operation outcome changes as a result, the application is very likely depending improperly on the logging channel.

This lesson focuses on real-world manifestations, fixes at each layer, a standalone runnable Java 17 example, and tests to ensure logging never becomes a business controller.

## 2. Logging Can Be Filtered, Delayed, Failed, or Reconfigured

The typical path:

```text
Business code
    |
    v
SLF4J / Log4j2 / Logback / java.util.logging
    |
    v
Logger threshold / filter
    |
    v
Appender / encoder / Handler
    |
    +--> console / stdout
    +--> file
    +--> async memory queue -> worker
    +--> agent -> collector -> storage/index
```

At each step, the following can happen:

- `DEBUG` or `INFO` is blocked because the effective level is too high.
- A filter on the logger/appender drops the event even though the code called `logger.info(...)`.
- An asynchronous appender has only placed the event into RAM, and the worker has not yet sent it to the sink.
- A full buffer causes events to be dropped or the logging thread to block, depending on the backend and configuration.
- A file cannot be written due to full disk, permission errors, or rotation.
- The collector encounters network errors, returns 429/5xx, or indexes slowly.
- A dashboard does not show the event due to query filters, timezone, retention, or permissions.

Therefore, the following inferences are **invalid**:

```text
Calling logger.error(...) => the business operation automatically fails.
No ERROR log seen => definitely no error occurred.
SUCCESS log seen => the DB definitely committed.
DEBUG is enabled => the business operation is allowed to run.
Collector received the log => the message broker definitely ACKed.
```

A proper system must have a **business source of truth**: result/state in the domain, transaction status, durable message/event, or reconciled state. Logs can help trace that source of truth, but they do not replace it.

## 3. Suspicious Signs in Code Review

| Sign in Java | Core Flaw | Risk |
| --- | --- | --- |
| `if (invalid) logger.warn(...); save();` | Logs only instead of stopping | Invalid data is still saved |
| `catch (Exception e) { logger.error(...); }` | Swallows exception | Caller thinks it succeeded |
| `if (logger.isDebugEnabled()) update();` | Level used as a feature flag | Changing log config alters business logic |
| `if (logger.isErrorEnabled()) throw ...;` | Exception depends on logger | Unstable behavior |
| `logger.debug("saved={}", repository.save(x));` | Side effect inside log argument | Hard-to-spot mutation, still runs when DEBUG is off |
| Parsing stdout with regex to issue payment commands | Log text used as a message bus | Delayed, lost, duplicated, or spoofed |
| Logging `SUCCEEDED` before transaction commit | Observation reports wrong milestone | Reports success despite rollback |
| Logging `DENIED` while still returning data | Log replaces enforcement | Authorization vulnerability |
| Test only does `verify(logger).error(...)` | State not verified | Business bugs slip through tests |
| Deciding to retry because a log line is missing | Dependent on ingest/indexing | May execute duplicate side effects |

Not every case of logging and throwing an exception is wrong. Some boundaries intentionally perform controlled logging and then `throw` or convert to an error response. The anti-pattern occurs when **logging is treated as the primary handling action**, or when the code lacks the corresponding decision action.

## 4. Case 1: Logging a Validation Warning and Continuing Execution

Example of entering a quantity:

```java
// WRONG: no return/throw.
if (quantity <= 0) {
    logger.warn("Invalid quantity {}", quantity);
}
orderRepository.save(new Order(quantity));
```

A `WARN` line only describes the violation; it does not prevent the `save` call. The right approach is to return a typed result or throw a typed exception:

```java
// Result approach:
if (quantity <= 0) {
    return PlaceOrderResult.rejected("INVALID_QUANTITY");
}

Order order = orderRepository.save(new Order(quantity));
return PlaceOrderResult.succeeded(order.id());
```

Or:

```java
// Exception approach:
if (quantity <= 0) {
    throw new InvalidOrderQuantityException(quantity);
}
```

These snippets are **illustrative code** requiring corresponding application classes and dependencies, and do not compile standalone. Choose `Result` when rejection is a common business branch; choose a typed exception when the contract requires exiting the execution path and letting a boundary handle it. Whichever you choose, state-mutating calls must not proceed after a failed guard.

### Do Not Use Message Text to Classify Outcomes

Wrong:

```java
// Should not decide based on free-form wording.
if (lastLogLine.contains("Invalid quantity")) {
    return badRequest();
}
```

Right: keep `reasonCode=INVALID_QUANTITY` or an enum/typed error as business data. The message can be localized or reworded without changing the flow.

## 5. Case 2: Catching an Exception, Logging, and Swallowing It

```java
// WRONG: void method completes normally even though the DB did not save.
void updateProfile(Profile profile) {
    try {
        repository.save(profile);
    } catch (SQLException ex) {
        logger.error("Cannot update profile", ex);
    }
}
```

The caller does not see the exception. A controller might return HTTP 200 even though the operation failed. Inside a transaction, swallowing an exception can cause other changes to be committed depending on the transaction policy.

If recovery is not possible, **propagate** the error with its cause:

```java
void updateProfile(Profile profile) {
    try {
        repository.save(profile);
    } catch (SQLException ex) {
        throw new ProfileStorageException(
                "PROFILE_STORAGE_FAILURE", ex);
    }
}
```

If there is an expected error-handling branch, return a result:

```java
UpdateResult updateProfile(Profile profile) {
    try {
        repository.save(profile);
        return UpdateResult.succeeded();
    } catch (KnownVersionConflictException ex) {
        return UpdateResult.conflict("VERSION_CONFLICT");
    }
}
```

These examples are only snippets with hypothetical classes. Do not turn every exception into a business rejection: a database offline error is different from a valid conflict; a timeout after a command was sent may leave an **UNKNOWN** outcome rather than a guaranteed rollback.

### Log-and-Rethrow at Every Layer Is Also Harmful

```text
Repository -> log ERROR, throw
Service    -> log ERROR, throw
Controller -> log ERROR, map HTTP
```

Three stack traces can represent **a single error**. To reduce noise, choose one boundary responsible for logging the exception with full context; lower layers can add a typed exception/cause. Separate audit events may still need to be recorded, but their event type and purpose must be kept distinct.

## 6. Case 3: Using Logger Level as a Feature Flag

Wrong:

```java
// CRITICAL BUG:
if (logger.isDebugEnabled()) {
    transferMoney(source, target, amount);
}
```

When the operations team switches the level from `INFO` to `DEBUG` to investigate an issue, the code starts executing money transfers. When `DEBUG` is off, the business logic does not run. This is a dangerous coupling between **observation** and **decision**.

Use a dedicated policy instead:

```java
if (!authorization.canTransfer(actor, source)) {
    return TransferResult.denied("NOT_AUTHORIZED");
}

if (!featurePolicy.isTransferEnabled(actor)) {
    return TransferResult.rejected("FEATURE_DISABLED");
}

TransferResult result =
        transferService.transfer(source, target, amount);

if (logger.isDebugEnabled()) {
    logger.debug(
        "transfer resultCode={}", result.reasonCode());
}

return result;
```

This is an application snippet, not a standalone class. `featurePolicy` must have a proper configuration/authorization source; it is not an alias for the log level. An `isDebugEnabled()` guard should only wrap **computing diagnostic information that has no required side effects**.

Some teams use a logger to decide observation sampling — that is reasonable if sampling only affects **telemetry**. But if it affects retries, commits, permissions, or responses, it is no longer pure sampling.

## 7. Case 4: Placing Side Effects Inside Logging Arguments

Java evaluates arguments before invoking a method. Therefore:

```java
logger.debug("stored entity={}", repository.save(entity));
```

**`repository.save(entity)` is still called even when DEBUG is turned off**, because it must be evaluated to pass as an argument. This is not lazy evaluation.

Conversely, putting a side effect inside a block that only runs when DEBUG is enabled is also wrong:

```java
// WRONG if persist() is a required business operation.
if (logger.isDebugEnabled()) {
    logger.debug("saved={}", persist());
}
```

Correct approach: separate mutation and logging:

```java
SavedEntity saved = repository.save(entity);
logger.debug("savedEntityId={}", saved.safeId());
```

If building a diagnostic summary is expensive but **pure**, you can protect it with a guard:

```java
if (logger.isDebugEnabled()) {
    logger.debug("diagnostic={}",
            computeSummaryWithoutSideEffects(saved));
}
```

SLF4J 2.x has a fluent/lazy supplier API, and JUL has some overloads that accept `Supplier<String>`. These help avoid computing **log content** when the level is disabled; they are not a mechanism for conditionally executing business logic based on logging.

**Review rule:** every expression inside a logger argument or supplier must be treated as **observation with no business side effects**. If an expression calls a repository, makes an RPC, or mutates state, move it outside.

## 8. Case 5: Logging Success Before Commit or ACK

```java
// WRONG: declares success before committing.
logger.info("action=ROLE_CHANGE outcome=SUCCEEDED");
repository.updateRole(userId, role);
transaction.commit();
```

If the transaction rolls back or fails during commit, the log record describes the event inaccurately.

Correct conceptual flow:

```text
Request
   |
   v
Authorize + validate
   |
   +-- DENIED / REJECTED --> return outcome
   |
   v
Execute mutation
   |
   +-- rollback confirmed --> FAILED
   +-- commit ambiguous   --> UNKNOWN / reconciliation
   |
   v
COMMIT confirmed
   |
   v
SUCCEEDED (verified business outcome)
   |
   v
Observe result / durable audit protocol (as required)
```

However, **logging after commit does not guarantee the log is persisted**. The process could crash after the DB commit and before the logger call. If you must guarantee an audit record or emit a domain event, you need a transactional outbox or an event persistence mechanism with its own durability contract (Section 16), not just moving `logger.info`.

Similarly, a message consumer may log `"ACK_SENT"` yet lose the connection before the broker records the ACK. Logging `ACK_ATTEMPTED` is an observation of the attempt, not proof of successful delivery. With Kafka, calling `commitAsync` does not mean the callback has reported commit success.

## 9. Log Level Is Not a Business Outcome

Severity and business outcome are two independent axes:

| Business Outcome | Possible Log Level | Interpretation |
| --- | --- | --- |
| `SUCCEEDED` | INFO or audit store | Operation reached verified milestone |
| `REJECTED` | INFO/DEBUG/audit | Domain rule rejected it |
| `DENIED` | Security audit, INFO/WARN per policy | Authorization denied |
| `NO_CHANGE` | DEBUG/INFO | Idempotent request, no mutation |
| `FAILED` | ERROR if incident requires on-call | Confirmed technical failure |
| `UNKNOWN` | WARN/ERROR based on impact | Unknown whether side effect occurred |
| `PENDING` | INFO or lifecycle event | No terminal result yet |

`logger.error` does not automatically return HTTP 500. `logger.warn` does not automatically turn a response into 409. `logger.info` does not automatically mark a transaction as committed.

When a dashboard uses the count of `ERROR` lines as "failed transactions," it can miscount: business rejections are often logged at `INFO`, an exception after commit might be `ERROR` even though the business operation succeeded, and a single error can produce three log lines if multiple layers log it.

For business metrics, measure from **structured results/events** and verified commit/processing milestones. Use log levels as an operational signal, not as the primary status code.

## 10. Good Design: Decision First, Observation After

A well-aligned architecture:

```text
HTTP / message / scheduled job
        |
        v
Authorization + validation
        |
        v
Domain / application service
        |
        +--> Result / typed exception / state transition
                      |
                      v
             Boundary/policy mapping
             HTTP response / ACK / NACK
             transaction / retry
                      |
                      v
               Logging, metric, tracing
               reflecting the actual decision
```

Each component has a distinct role:

- **Command:** a request to produce a side effect, subject to guards and policies.
- **Domain result:** outcomes such as `SUCCEEDED`, `REJECTED`, `DENIED`, `NO_CHANGE`, or equivalent states.
- **Exception:** signals an abnormal failure or an execution path that cannot continue under the contract.
- **State machine:** manages multi-step workflows and asynchronous states.
- **Domain event:** a business event with its own schema, ID, and delivery semantics.
- **Operational log:** an observation trace that may be filtered or sampled, not durable by default.
- **Audit event:** may require dedicated storage, integrity, retention, and access controls.

An `outcome=SUCCEEDED` event should be produced **from the business outcome**, not by parsing the phrase "payment succeeded" out of a logger message to infer the result.

### An Operation Across Multiple Layers

The domain layer can return `TransferResult`; the application service manages the transaction; the HTTP boundary maps the result to a response while emitting a logging event; monitoring tracks outcome/latency. As a result, replacing Logback with Log4j2 or switching from a text pattern to JSON does not alter business logic.

## 11. Standalone Java 17: INFO Disabled, Business Logic Still Works Correctly

The following program simulates two in-memory accounts without external libraries:

1. Source starts with 100 units, target starts with 0.
2. Transferring 150 is rejected due to insufficient balance, and an `INFO` event is printed.
3. Lowering the log level so `INFO` is filtered out.
4. Transferring 30 still succeeds; even with no new `INFO` event, the balances update accurately.

The code uses JUL (`java.util.logging`) and a test `Handler` with deterministic output, without relying on timestamps or the default `ConsoleHandler`.

### 11.1. Create `LogIsNotControlFlowDemo.java`

```java
import java.text.MessageFormat;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogIsNotControlFlowDemo {
    enum Status { SUCCEEDED, REJECTED }

    record TransferResult(Status status, String reasonCode) {}

    static final class Accounts {
        private int sourceBalance = 100;
        private int targetBalance = 0;

        TransferResult transfer(int amount) {
            if (amount <= 0) {
                return new TransferResult(
                        Status.REJECTED, "INVALID_AMOUNT");
            }

            if (amount > sourceBalance) {
                return new TransferResult(
                        Status.REJECTED, "INSUFFICIENT_FUNDS");
            }

            // Side effect driven by business rules,
            // independent of whether the logger is enabled.
            sourceBalance -= amount;
            targetBalance += amount;

            return new TransferResult(
                    Status.SUCCEEDED, "APPLIED");
        }

        int sourceBalance() { return sourceBalance; }
        int targetBalance() { return targetBalance; }
    }

    private static final Logger LOG =
            Logger.getLogger("example.controlflow.demo");

    private static void observe(TransferResult result) {
        // Decision already made; the logger only observes.
        LOG.log(Level.INFO,
                "action=TRANSFER outcome={0} reasonCode={1}",
                new Object[] {
                    result.status(), result.reasonCode()
                });
    }

    public static void main(String[] args) {
        Level originalLevel = LOG.getLevel();
        boolean originalParentHandlers =
                LOG.getUseParentHandlers();

        AtomicInteger captured = new AtomicInteger();

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord event) {
                if (!isLoggable(event)) {
                    return;
                }

                captured.incrementAndGet();

                String rendered = MessageFormat.format(
                        event.getMessage(),
                        event.getParameters());

                System.out.println(
                        "LOG " + event.getLevel().getName()
                                + " " + rendered);
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        sink.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(sink);

        try {
            Accounts accounts = new Accounts();

            System.out.println(
                    "infoEnabledBefore="
                            + LOG.isLoggable(Level.INFO));

            TransferResult first = accounts.transfer(150);
            observe(first);

            System.out.println(
                    "first=" + first.status()
                            + " source=" + accounts.sourceBalance()
                            + " target=" + accounts.targetBalance());

            // Change only the logging policy.
            LOG.setLevel(Level.WARNING);

            System.out.println(
                    "infoEnabledAfter="
                            + LOG.isLoggable(Level.INFO));

            TransferResult second = accounts.transfer(30);
            observe(second); // INFO is filtered, transfer already ran.

            System.out.println(
                    "second=" + second.status()
                            + " source=" + accounts.sourceBalance()
                            + " target=" + accounts.targetBalance());

            System.out.println(
                    "capturedEvents=" + captured.get());
        } finally {
            LOG.removeHandler(sink);
            sink.close();
            LOG.setLevel(originalLevel);
            LOG.setUseParentHandlers(originalParentHandlers);
        }
    }
}
```

### 11.2. Compile and Run

Use JDK 17 or later:

```bash
javac LogIsNotControlFlowDemo.java
java LogIsNotControlFlowDemo
```

**Exact stdout** when running the program standalone:

```text
infoEnabledBefore=true
LOG INFO action=TRANSFER outcome=REJECTED reasonCode=INSUFFICIENT_FUNDS
first=REJECTED source=100 target=0
infoEnabledAfter=false
second=SUCCEEDED source=70 target=30
capturedEvents=1
```

### 11.3. Why Does This Output Matter?

- While `INFO` is enabled, `TransferResult(REJECTED, INSUFFICIENT_FUNDS)` is determined by the balance check. The logger only prints that result.
- After raising the logging threshold to `WARNING`, `LOG.isLoggable(Level.INFO)` returns `false`. The call to `observe(second)` still executes, but no new `INFO` event reaches the `Handler`.
- `Accounts.transfer(30)` does not depend on the logger, so it still updates the source balance to 70 and the target balance to 30.
- `capturedEvents=1` only counts **`LogRecord`s reaching the in-memory `Handler`**, not the number of business transactions or a guarantee that a collector stored them.
- JUL uses `{0}`/`{1}` placeholders with `MessageFormat`; SLF4J uses `{}` placeholders. Do not mix the two syntaxes.
- The `finally` block removes the `Handler` and restores the configured level and parent-handler flag, preventing test state from leaking into other code.

**Limitations:** this is a single-threaded simulation using integers, with no authentication, ACID transactions, database, or concurrency. Do not use this `Accounts` class for real money transfers. The code is sufficient to demonstrate that **business control flow is independent of log existence**, not to prove durable logging or duplicate prevention.

## 12. Exception, Result, and State Machine: Choosing the Right Control Flow Tool

### Typed Result for Expected Branches

In Java 17, you can model outcomes like this:

```java
sealed interface CancelResult
        permits CancelResult.Cancelled,
                CancelResult.NoChange,
                CancelResult.Rejected {

    record Cancelled() implements CancelResult {}
    record NoChange() implements CancelResult {}
    record Rejected(String reasonCode)
            implements CancelResult {}
}
```

This is a valid Java 17 declaration in an appropriate file/type context. It represents three semantically distinct outcomes; the logger does not need to decide which one occurred.

### Typed Exception for Error Paths

```java
if (!policy.canCancel(actor, order)) {
    throw new AccessDeniedException("POLICY_DENIED");
}
```

This snippet depends on application classes. `throw` alters control flow; `logger.warn` does not. An outer handler can map `AccessDeniedException` to HTTP 403 or emit a `DENIED` audit record.

### State Machine for Asynchronous Tasks

A long-running job might transition through `ACCEPTED -> RUNNING -> SUCCEEDED/FAILED/CANCELED`. Do not infer `SUCCEEDED` just because a `"worker started"` log line appeared. State should live in the domain/job store with transition rules and reconciliation capability. The logger emits an observation event **after each verified transition**.

If logging fails, the state machine remains governed by the transaction/state store; if the audit/event itself is mandatory, use a durable persistence protocol rather than hoping logs always survive.

## 13. Anti-Pattern: Using Console Logs as a Message Bus

A makeshift integration sometimes looks like this:

```text
Service A:
  logger.info("SEND_EMAIL orderId=O-42")
       |
       v
Log agent / collector
       |
       v
Regex parser
       |
       v
Service B sends email
```

This is driving work through text logs, which is extremely fragile:

- Level/filter change → the "command" disappears.
- Pattern, newline, or JSON encoder change → the parser fails to match.
- Slow async queue/sink → work is delayed with no deterministic deadline.
- Duplicate log retries → the email is sent twice.
- Raw input containing CR/LF → can spoof log lines.
- Retention/index/permission changes → workflows break unpredictably.
- No ACK, retry budget, DLQ, or business-level idempotency.

If System B must perform an action, use an **API, message broker, or domain event** with a proper schema, event ID, delivery acknowledgement, and idempotency. You can still log `EmailDispatchRequested` for diagnostics, but the logger must not be the sole command source.

**Distinction to note:** a *change data capture* (CDC) platform reading a **database transaction log** via a dedicated protocol can emit domain events. That is not `logger.info` text logging, and it does not legitimize grepping stdout to drive business logic.

## 14. Message Consumers: Logging Does Not Replace ACK/NACK, Retry, or DLQ

In a consumer:

```java
// WRONG: fails but does nothing with delivery state.
try {
    processBusinessMessage(message);
} catch (Exception ex) {
    logger.error("Processing failed", ex);
}
// The framework may consider the handler completed depending on configuration.
```

When a handler exits normally, some frameworks or auto-ack configurations treat the message as processed. The attempt will not be retried even though the business operation failed. You need an explicit policy:

```text
Receive
   |
   +-- VALIDATION REJECTED --> ACK or DLQ per contract
   |
   +-- TRANSIENT FAILURE --> retry/backoff, controlled NACK/requeue
   |
   +-- BUSINESS COMMITTED --> ACK/commit offset per broker contract
   |
   +-- COMMIT UNKNOWN --> reconcile/idempotency before repeating
```

ACK/NACK semantics differ across RabbitMQ, Kafka, and frameworks. RabbitMQ supports consumer acknowledgements; Kafka typically commits offsets/positions and does not have per-message NACK with the same semantics. Do not write generic logic based solely on a `"Processed"` log line.

A `logger.info("ACK_SENT")` call can execute before the broker records it; if the connection drops, the broker may redeliver. Use `messageId`/`operationId`, an idempotency store, and the source of truth to detect whether the side effect already occurred.

**Do not use ERROR logs as a retry signal.** Retries require error classification, budgets, backoff, timeouts, and side-effect checks. An error log on the first attempt may correspond to an ultimately successful logical operation; conversely, the absence of an ERROR log does not prove an ACK succeeded.

## 15. Async Logging Makes the Anti-Pattern Harder to Detect

Logback's `AsyncAppender` or async backends can push events into an in-memory queue while a worker thread writes to the sink.

```text
Business thread:
  DB commit -> logger.info("SUCCEEDED") -> response
                      |
                      v
                Async log queue
                      |
                      v
                Agent / collector
```

Because of this:

- A logging API returning does not mean the event is durable.
- Events may appear on dashboards after the response or even after a subsequent request.
- A full queue may discard events or block producers depending on policy.
- Crashing before draining the queue can lose logs.
- Multiple threads, multiple pods, and collector batching can reorder observations.
- Data at the sink may be indexed late or miss fields due to parser errors.

If business logic relies on **"log seen"** to finalize state, race conditions and failure coupling will follow. When business synchronization is needed, use transactions, brokers, futures/acks, or state stores with clear semantics. Do not infer a global log order when the backend does not guarantee one.

**Specifically:** losing an operational log and losing a business message are two separate problems. A message can be processed and ACKed while its log is lost; conversely, an `ACK_ATTEMPTED` log may exist while the broker never received the ACK.

## 16. Mandatory Auditing and Transactional Outbox Are Not Ordinary Text Logs

Some operations, such as permission changes or regulated workflows, may require **persisting evidence** before reporting success. Do not respond by writing:

```java
logger.info("AUDIT action=ROLE_CHANGE outcome=SUCCEEDED");
return success();
```

if policy requires durable auditing: the logger may be filtered, and an async queue may lose events on crash.

One option is a **transactional outbox** for the mutation together with the pending event:

```text
BEGIN DB transaction
  update business state
  insert audit_outbox(eventId, operationId, action, outcome)
COMMIT
       |
       v
Outbox dispatcher -> sink (retry / ACK / dedup)
```

If the DB rolls back, both the mutation and the outbox record roll back. If the dispatcher sends the event and loses the ACK, the event can be resent; the consumer/sink must deduplicate by `eventId`. An outbox **does not by itself provide system-wide exactly-once delivery**, but it establishes a clear durability boundary between the business commit and pending event delivery.

For `DENIED`/`REJECTED` events with no committed mutation, writing inside a transaction that rolls back can also lose the event. A separate audit transaction or channel may be needed. If auditing is unavailable, the organization must choose a policy: fail closed for sensitive operations, durable retry/spooling, or an incident-handling mechanism. **That is a designed and tested decision**, not control flow hidden inside a `logger.error` call.

## 17. Security: Logging Does Not Replace Authorization Enforcement

Severe bug example:

```java
// WRONG: still returns sensitive data.
if (!isAuthorized(actor, resource)) {
    logger.warn("Unauthorized access");
}
return loadSensitiveData(resource);
```

You must block access:

```java
if (!isAuthorized(actor, resource)) {
    throw new AccessDeniedException("POLICY_DENIED");
}
return loadSensitiveData(resource);
```

This snippet requires project classes. A `DENIED` audit log can be recorded per policy, but it is **not the sole reason** access is denied. If the audit sink fails, the resource protection path must still ensure unauthorized callers do not receive data; if policy requires fail closed, enforce it explicitly.

Related risks:

- Users can inject `\r`/`\n` into messages and cause log injection if the formatter/encoder does not escape them.
- Having a log parser treat a spoofed `"ADMIN_APPROVED"` line as an authorization signal is extremely dangerous.
- Never take `actorId` or `outcome` from a client-supplied body and trust it as server evidence.
- Never log passwords, access/refresh tokens, cookies, private keys, or raw request bodies.
- Never use a DTO's `toString()` output as log input without reviewing for PII.
- Reading logs/dashboards must require separate permissions; being allowed to view logs does not grant business permissions.

Any system that reads logs to trigger automated actions (such as SIEM/SOAR) needs policies, source authentication, false-positive controls, and dedicated permissions. It should never treat arbitrary free-form text lines as privileged commands.

## 18. Testing to Detect the Anti-Pattern: Logger OFF Must Yield the Same Result

A **metamorphic test** is useful: run the same operation from **two equivalent initial states**, once with logging enabled and once with `INFO`/`DEBUG` disabled, then compare the business outcomes. The logs may differ, but the result and state must be identical.

Matrix:

| Scenario | Logging | Required Business Outcome |
| --- | --- | --- |
| Transfer 30 with sufficient balance | INFO | SUCCEEDED, debited/credited accurately |
| Transfer 30 on equivalent fixture | OFF | SUCCEEDED, debited/credited accurately |
| Transfer 150 with only 100 available | INFO | REJECTED, no mutation |
| Transfer 150 on equivalent fixture | OFF | REJECTED, no mutation |
| Unauthorized actor | OFF | No data access or mutation |
| Unavailable dependency | OFF | Exception/failure result is not swallowed |
| Business transaction rollback | INFO | No fake success commit |
| Sink/collector outage | INFO | Business policy still applies; audit path follows its own policy |
| Message redelivery | INFO/OFF | Idempotency still prevents double side effects |

### JUnit 5: Verifying Domain Behavior

For `LogIsNotControlFlowDemo` from Section 11, add JUnit Jupiter to the project and place the test in the same package:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LogControlFlowTest {
    @Test
    void transferResultIsIndependentOfObservation() {
        var withLogging = new LogIsNotControlFlowDemo.Accounts();
        var withoutLogging = new LogIsNotControlFlowDemo.Accounts();

        var a = withLogging.transfer(30);
        var b = withoutLogging.transfer(30);

        assertEquals(a, b);
        assertEquals(70, withLogging.sourceBalance());
        assertEquals(70, withoutLogging.sourceBalance());
        assertEquals(30, withLogging.targetBalance());
        assertEquals(30, withoutLogging.targetBalance());
    }

    @Test
    void rejectDoesNotMutateBalances() {
        var accounts = new LogIsNotControlFlowDemo.Accounts();
        var result = accounts.transfer(150);

        assertEquals(
                LogIsNotControlFlowDemo.Status.REJECTED,
                result.status());
        assertEquals("INSUFFICIENT_FUNDS", result.reasonCode());
        assertEquals(100, accounts.sourceBalance());
        assertEquals(0, accounts.targetBalance());
    }
}
```

**Scope:** this test verifies that domain logic is decoupled from the logger; it **does not actually toggle the logger on or off**. To test independence end-to-end, invoke through an application boundary with real logging enabled, vary the logger level across independent fixtures, compare DB/results, and capture events at the appender to verify the difference in the observation channel. Do not mistake a simple unit test for full pipeline verification.

### What Else Should Be Tested Beyond the Happy Path?

1. **Validation:** invalid input produces no mutation even when the logger is `OFF`.
2. **Authorization:** policy blocks before the repository reads or writes sensitive data.
3. **Exceptions:** dependency exceptions are not swallowed just because `catch` logged them.
4. **Transactions:** rollback is confirmed and no fake `SUCCEEDED` event is emitted.
5. **Concurrency:** concurrent requests do not rely on a global `lastLogMessage` or logger state.
6. **Async:** message ACK/retry follows actual state, not log text.
7. **Collector outage:** operational logging fails while business/audit policies still hold.
8. **Security:** input containing CR/LF or fake tokens is not turned into a business command by a parser.

With async appenders, use a latch/queue/ack with a finite timeout to wait; do not call `Thread.sleep(200)` and assume the event arrived or was filtered. If you need to assert **no event**, use a drain/barrier mechanism appropriate for the backend.

## 19. Test Oracle: Log Assertions Do Not Replace State Checks

Weak assertions:

```java
verify(logger).error("Insufficient funds");
assertTrue(logText.contains("ROLLBACK"));
assertTrue(logText.contains("ACK_SENT"));
```

They only show a method call or a substring; they do not prove a transaction rolled back or a broker ACKed. Use proper oracles:

| Requirement | Primary Oracle | Supplementary Log Check |
| --- | --- | --- |
| Insufficient funds must not debit | Account/DB state + Result | `REJECTED/INSUFFICIENT_FUNDS` |
| Unauthorized caller cannot fetch data | Authorization outcome/response | `DENIED` audit |
| Errors must propagate to caller | `assertThrows` or API error result | Throwable/cause |
| Transaction rollback | DB state after rollback | No fake success |
| Bounded job retry | Retry scheduler/broker attempt state | `RETRY_SCHEDULED` |
| Broker received ACK | Client/broker contract | `ACK_ATTEMPTED/CONFIRMED` |
| Outbox event committed | DB outbox in same transaction | Dispatcher logs |
| Logger does not drive business logic | State/result across log levels | Event count at sink |
| Collector receives logs | Sink query/receipt by event ID | Appender status |
| Logging error budget | Source-to-sink reconciliation | Drop/latency metrics |

Logging tests should verify `level`, `message template`, `arguments`, `MDC`, `Throwable`, and structured fields when those properties are part of the contract. Do not pin full timestamps, thread names, or stack frames to pretend you are testing business outcomes.

## 20. Avoid Coupling Business Logic to Logging Backend Failures

Distinguish three kinds of systems:

**Best-effort operational logging:** when writing a log fails, it should generally not alter the outcome of a business transaction. Use dedicated metrics/health checks and alerts for log loss.

**Mandatory auditing:** if a sensitive operation requires durable evidence before confirmation, build a transaction/ack/fail-closed policy. An unavailable audit store may block the operation per contract, but that is a **designed enforcement condition**, not an accidental exception thrown by a logger.

**Domain event delivery:** when downstream services must act, use an outbox/broker/API with event IDs, retries, deduplication, and reconciliation. Do not rely on a consumer "seeing an INFO log" in the collector.

### Failure Questions to Ask

- If the collector goes down for 20 minutes, are business requests still allowed to proceed?
- If a `DENIED` log is dropped, does authorization still block properly?
- If a custom logging appender throws an exception, at which boundary must the application catch, degrade, or fail closed?
- If a transaction commits but the audit event has not been sent yet, is there a durable outbox holding it?
- If an event reaches the collector twice due to retries, who deduplicates it and by which ID?
- If the log level is changed during an incident, is there any case that suddenly enables or disables mutations?
- If log formatting changes due to a library upgrade, does any system use regex on logs to make business decisions?

Clear answers to each of these questions indicate that the architecture properly separates concerns.

## 21. Workflow for Refactoring the Anti-Pattern in a Codebase

1. **Locate suspicious code paths:** `logger.error` in a guard without `return`/`throw`; `catch` blocks that only log; `isDebugEnabled` wrapping mutations; side effects in log arguments; services parsing log text.
2. **Clarify business obligations:** which checks must block, which errors must propagate, and which states must commit or roll back?
3. **Define outcome contracts:** `Result`/enum/typed exceptions with stable `reasonCode`s, not derived from formatted log messages.
4. **Move side effects to the right place:** run guards before mutations, define clear transaction boundaries, and keep required actions out of the logger.
5. **Return logging to an observational role:** emit events with `action/outcome/reasonCode/operationId` derived from verified decisions.
6. **Choose the right logging boundary:** avoid logging the same exception at three layers; preserve root causes for technical errors.
7. **Replace log-driven workflows:** use domain events, outboxes, message brokers, or APIs with ACKs and idempotency where needed.
8. **Add regression tests:** logger `OFF`, unexpected exceptions, rollbacks, conflicts, retries, authorization, concurrency, and collector outages.
9. **Check monitoring compatibility:** if alerts currently rely on text messages, plan a migration to structured fields and metrics.
10. **Monitor after rollout:** track business outcome rates, duplicate effects, error rates, audit backlog, and logging pipeline health.

Do not mechanically convert every `logger.warn` into a `throw`: some warnings are purely informational, or a fallback has already handled the situation successfully. Understand the **side-effect and outcome contract** before changing code.

## 22. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Logging an ERROR makes the method fail | The logger does not alter control flow; you need `return`/`throw`/state. |
| No ERROR log means no error occurred | Logs can be filtered or lost, or the error was never logged. |
| Using DEBUG as a feature flag | Runtime log policy is not business authorization. |
| The logger automatically rolls back transactions | Commit/rollback is handled by the transaction manager. |
| Catching and logging lets the caller know about the error | The exception is swallowed unless propagated or mapped. |
| Enabling a lazy supplier runs business logic when needed | The supplier might not run; use it only for pure diagnostics. |
| Code in log arguments won't run when DEBUG is off | Java evaluates arguments before calling the logger. |
| Parsing `SUCCESS` from stdout is reliable integration | Log text lacks proper delivery, schema, and idempotency contracts. |
| Putting INFO into an async queue means it's durable | Enqueuing is not a collector ACK or storage commit. |
| Seeing a log in a test means business logic is right | You must verify state, result, exceptions, and side effects. |
| Any retry is safe if an ERROR log exists | The side effect may have happened; you need idempotency/reconciliation. |
| Auditing only needs `logger.info` | It may require a durable store, retention, integrity, and separate permissions. |

## 23. Code Review Checklist

- [ ] Business guards use `return`, `throw`, typed results, or state transitions; they do not just log and continue.
- [ ] `isDebugEnabled`, log levels, and filters do not control authorization, validation, mutations, or transactions.
- [ ] No critical side effects appear inside logger arguments or lazy suppliers.
- [ ] Exceptions are intentionally propagated, mapped, or recovered from; they are not swallowed just because they were logged.
- [ ] `SUCCEEDED` is logged only after the business effect is verified; never before commit.
- [ ] Text logs, grep, or regex are never used to decide retries, ACKs, DLQs, API responses, or commands.
- [ ] Business outcomes use stable codes/enums, not inferences from severity or message strings.
- [ ] Logging boundaries are clear, without duplicating the same exception across every layer.
- [ ] Authorization still blocks properly when logging is `OFF` or the audit sink is unavailable.
- [ ] Mandatory audits/events have their own delivery/durability contracts where appropriate.
- [ ] Tests compare state and outcomes across different logging levels on equivalent fixtures.
- [ ] Tests cover exceptions/rollbacks, concurrency, idempotency, lost broker ACKs, and collector outages as applicable.
- [ ] Logs do not contain tokens, raw request bodies, unescaped user input, or unnecessary sensitive data.
- [ ] Metrics/alerts for business health and logging reliability are separated, with runbooks for sink failures.
- [ ] Refactoring preserves monitoring compatibility and properly documents changes to log schemas.

**Conclusion:** logging should only **describe what happened**. Enabling/disabling logs, appender failures, or collector lag must never arbitrarily dictate business rules. Use `Result` types, exceptions, state machines, transactions, and domain events to enforce and control behavior; then use logging as a controlled observation channel. If mandatory auditing or guaranteed delivery is required, design a dedicated durability contract rather than treating log strings as hidden control switches.