# Poller Sending Errors to an error-channel in Spring Integration

## 1. Problem Statement: Who Receives Exceptions When a Poller Runs on a Schedule?

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`. Some sources—such as File directories, SFTP, or JDBC queries—are typically read by a **polling consumer/source**: a scheduler periodically wakes an endpoint to pull a message and pass it through processing steps.

Suppose an application scans a directory every three seconds:

1. File inbound adapter detects a new CSV file.
2. The poller receives the file as a Spring Message.
3. The message flows through a transformer, service activator, and JDBC outbound handler.
4. The database is temporarily unavailable; the handler throws an exception.

Here there is no HTTP caller waiting on the same call stack to receive the exception. If the task is scheduler-triggered and lacks an appropriate error strategy, the error may only appear in scheduler logs or cause unintended side effects. Spring Integration provides a mechanism to **catch exceptions within a poll cycle and publish an ErrorMessage to an error channel**.

**Poller sending errors to an error-channel** means: when a polling task configured with an error publishing mechanism encounters an exception within the scope it handles, the exception is wrapped as an **ErrorMessage** and sent to a **MessageChannel dedicated to errors**, rather than needing to be returned to an original synchronous caller.

Important points to note immediately:

- **Exceptions do not automatically become ErrorMessages in every flow.** A poller/error handler must actually catch and publish the error.
- **Global `errorChannel` is not a retry queue.** It is a transport path for error messages; recovery must be designed separately.
- **A successfully published ErrorMessage does not prove the source message was retried or rolled back.** File filters, DB transactions, broker acknowledgments, and side effects each have their own lifecycle.
- **An error occurring before a Message is created** (such as failing to connect over SFTP) may lack `failedMessage` or a file payload.
- **A dedicated error channel** for a poller may fit better than global `errorChannel` when quarantine, alerts, retries, or distinct SLAs are needed.

### Learning Objectives

After this lesson, learners can:

1. Distinguish **polling source**, **polling consumer**, and **message-driven endpoint**.
2. Explain which exceptions pass through the poller error handler and the role of **MessagePublishingErrorHandler**.
3. Configure Java DSL so a poller sends `ErrorMessage` to a dedicated error channel.
4. Safely use **ErrorMessage**, **MessagingException**, **failedMessage**, **originalMessage**, and correlation IDs.
5. Distinguish errors in **receive/poll**, **transform/handle**, and **send/outbound**.
6. Design retries, backoff, quarantine, idempotency, and transactions per adapter.
7. Write integration tests, monitor metrics, and handle failures when the error flow itself fails.

## 2. What Is a Poller and Where Does It Sit in the Flow?

Spring Integration provides endpoints that actively fetch data periodically or consume messages from a buffering channel. Examples:

- **File inbound adapter:** scans a directory for files on a schedule.
- **SFTP inbound adapter:** lists/downloads files from a remote server.
- **JDBC polling inbound adapter:** queries pending records.
- **QueueChannel + polling consumer:** pulls messages already in a channel and processes them on a schedule.
- **Custom source:** a custom `MessageSource` calling an API or reading data periodically.

### 2.1. Two Common Patterns

~~~mermaid
flowchart LR
    subgraph SourcePolling["Polling inbound source"]
        T1["Scheduler"] --> P1["Source poller"]
        P1 --> SRC["File / SFTP / JDBC MessageSource"]
        SRC --> CH1["MessageChannel"]
        CH1 --> H1["Handler"]
    end
    subgraph ConsumerPolling["Polling consumer"]
        PROD["Producer"] --> Q["QueueChannel"]
        T2["Scheduler"] --> P2["Consumer poller"]
        P2 --> Q
        Q --> H2["Service activator"]
    end
~~~

A **source poller** actively invokes a `MessageSource` to receive data. A **consumer poller** actively reads from a `PollableChannel`. Both can process messages outside the producer's original call stack.

### 2.2. Not Every Inbound Adapter Is a Poller

An HTTP inbound gateway handles requests when a client connects, needing no periodic poller. JMS/AMQP message-driven inbound adapters and Kafka message-driven inbound adapters usually use **listeners/containers** with their own exception/acknowledgment mechanics. A Kafka consumer actually polls at the client protocol level, yet that **does not mean** the application uses a Spring Integration `PollerSpec`.

Therefore, when talking about **pollers sending errors to an error-channel**, this lesson primarily covers **Spring Integration polling endpoints**, not every JMS, AMQP, or Kafka listener.

### 2.3. A Single Poll Cycle

~~~text
Scheduler wakes the task
   |
   v
Poller calls receive() on MessageSource / PollableChannel
   |
   +-- No message --> poll cycle ends normally
   |
   +-- Message received --> send to output channel / handler
                         |
                         +-- Success: continue per poll policy
                         |
                         +-- Exception: task error strategy handles it
                                              |
                                  ErrorMessage (if published)
                                              |
                                         error-channel
~~~

Whether a poll cycle continues fetching more messages after an exception depends on poller configuration, error handler, advice, and endpoint implementation. Do not assume "one bad file only affects that file" without testing.

## 3. How Does an Exception Travel from a Poller to an ErrorMessage?

### 3.1. Components Involved

| Component | Role in Error Path |
|---|---|
| TaskScheduler or periodic task | Wakes the polling endpoint |
| Polling consumer / source poller | Receives messages and triggers processing |
| Task error handler | Receives exceptions within its covered scope |
| MessagePublishingErrorHandler | A Spring Integration mechanism publishing exceptions as ErrorMessages |
| ErrorMessageStrategy | Builds ErrorMessage from Throwable and supplied context |
| errorChannel / dedicated error channel | MessageChannel delivering errors to subscribers |
| Service Activator / LoggingHandler | Observes, classifies, creates recovery tasks |

Exact behavior can vary by **Spring Integration version**, custom task schedulers, executors, poller advice, and endpoint configuration. Not every arbitrary Spring Framework task scheduler knows about global `errorChannel` by default.

### 3.2. Logical Diagram of the Error Path

~~~mermaid
flowchart TD
    SCH["TaskScheduler"] --> POLL["Spring Integration poller"]
    POLL --> RECEIVE["receive()"]
    RECEIVE --> HANDLE["send/transform/handle"]
    RECEIVE -. "Data receive exception" .-> EH["Poller error handler"]
    HANDLE -. "Exception within poller scope" .-> EH
    EH --> BUILDER["ErrorMessageStrategy"]
    BUILDER --> EMSG["ErrorMessage: Throwable payload"]
    EMSG --> DEST{"Error destination?"}
    DEST -->|"Poller-specific"| LOCAL["filePollErrors"]
    DEST -->|"Global fallback"| GLOBAL["errorChannel"]
    LOCAL --> OWN["Application error handler"]
    GLOBAL --> LOG["Logging/monitoring subscribers"]
~~~

This diagram is a conceptual model and does not guarantee both cases always have complete `originalMessage`/`failedMessage` or that adapters always use this exact handler.

### 3.3. Types of Errors That Can Be Caught

- **Receive-time:** File/SFTP/JDBC source throws while scanning, querying, opening a session, reading a file, or creating a `Message`.
- **Process-time:** transformer or service activator throws during the call inside the poll task.
- **Send-time:** sending the message to a channel/handler fails, e.g., no subscriber or an outbound endpoint throws synchronously.
- **Advice-time:** retry/transaction advice throws the final exception or a recovery callback throws; verify advice ordering and responsibilities.

**Thread boundaries matter greatly.** If a handler hands off work to an `ExecutorChannel`, async outbound client, another scheduler, or a broker, later errors may occur outside the original poller stack. A poller `error-channel` **cannot automatically catch every error from detached-thread tasks**.

## 4. Default errorChannel vs. Poller-Specific Channels

### 4.1. Global Channel

Spring Integration uses the standard name **errorChannel** for the global error channel in typical default setups. In standard framework config, that channel is a **PublishSubscribeChannel** with a `LoggingHandler`. When an error publisher has no dedicated destination, it can send `ErrorMessage` here.

However, **global `errorChannel` is a general observation point**; it should not by default perform specialized data remediation for every flow in the application.

### 4.2. Per-Poller Dedicated Channel

In Java DSL, you can set **errorChannel("filePollErrors")** on the poller specification to route poller-published `ErrorMessage`s to a specific `MessageChannel`. A dedicated channel is convenient to:

- Separate file import errors from JDBC poller errors;
- Assign distinct business owners and SLAs;
- Quarantine bad files, classify SFTP timeouts, and create retry tickets;
- Prevent shared subscribers from applying the wrong recovery policy;
- Test error paths independently.

### 4.3. Does Configuring a Channel Guarantee It Receives Errors?

| Scenario | Expected Outcome to Verify |
|---|---|
| Poller has dedicated error channel and matching publisher | ErrorMessage reaches the dedicated channel |
| Poller uses global fallback | ErrorMessage reaches global errorChannel |
| Request message carries `errorChannel` header | Some error publishers prioritize headers per their mechanics; test with poller |
| Synchronous `DirectChannel` exception outside poll task | Usually thrown back to sender, not auto-published |
| Async error after poller handed off message | Governed by executor/async flow error strategy, not automatically the poller |
| JMS/AMQP/Kafka listener not using PollerSpec | Error path governed by adapter/container policy |

**Error channel selection is not a uniform precedence rule across all adapters.** If the application needs guaranteed routing, explicitly configure the endpoint and write tests verifying the error destination.

### 4.4. Why Adding a Service Activator on errorChannel Is Not Enough

Registering a subscriber only lets you **receive ErrorMessages that were published**. If a source poller uses a custom task scheduler lacking error publishing, or if an exception was caught and recovered by retry advice, no corresponding `ErrorMessage` may exist. Check **where exceptions are caught and whether they are published**.

## 5. Poller ErrorMessage, failedMessage, and originalMessage

### 5.1. Data Structure

**ErrorMessage** is a Spring Message with a `Throwable` payload. The payload may be **MessagingException**, **MessageHandlingException**, **MessageDeliveryException**, or another `Throwable`. If it is a `MessagingException`, **getFailedMessage()** can return the `Message` at the failure point; it may be null.

`ErrorMessage` also exposes **getOriginalMessage()**, present only if the `ErrorMessageStrategy`/constructor received an input message. Never assume every error has an original message.

~~~text
ErrorMessage
  payload: Throwable
    (may be MessagingException)
        failedMessage: Message<?> or null
        cause: Throwable or null
  originalMessage: Message<?> or null
  headers: id, timestamp, ... of error message
~~~

### 5.2. Errors Before Receiving a Message

For instance, an SFTP inbound source fails to open a session and throws **before a File Message exists**. Then:

- An `ErrorMessage` with the connection `Throwable` may be published;
- `failedMessage` or `originalMessage` may be null;
- Never blindly cast `failedMessage.payload` to `File`;
- Use endpoint ID, remote directory, source ID, and safe connection metadata to diagnose;
- Recover via connection/backoff, not by quarantining an unidentified file.

### 5.3. Errors After Receiving a Message

For example, `FileReadingMessageSource` created a message with a `File` payload, and a handler reads CSV and throws:

- `MessagingException` may hold `failedMessage` with the `File` or transformed payload;
- `originalMessage` may hold the input supplied to the error strategy;
- Correlation ID can be read from `failedMessage`, `originalMessage`, or the state store;
- Persist a file reference before retrying, since in-memory messages are not durable storage.

### 5.4. The errorChannel Header

**MessageHeaders.ERROR_CHANNEL** is a control header selecting an error channel when supported by the error publishing component. It is not a `Throwable` payload and does not generate `ErrorMessage` on its own. Never accept an uncontrolled header specifying internal channels from external files/HTTP clients, as that risks misrouting or data exposure.

## 6. Java DSL: Configuring a File Poller to Send Errors to a Dedicated Channel

### 6.1. Scope of the Example

This illustrative example uses **Spring Integration Java DSL** in a Spring app with appropriate core and file adapter dependencies. The app watches `data/inbox` for CSVs; every two seconds the poller scans for files and calls a handler. The handler **intentionally throws an exception** to exercise the error path.

The classes use common modern Spring Integration Java DSL APIs; before using in a real project, verify overloads and configuration types against your chosen dependencies. The project uses a modern enough Java version for these patterns.

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
@EnableIntegration
public class FilePollErrorConfiguration {

    @Bean
    public MessageChannel filePollErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow csvImportFlow() {
        return IntegrationFlow
                .from(Files.inboundAdapter(new File("data/inbox"))
                                .autoCreateDirectory(true)
                                .patternFilter("*.csv"),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("filePollErrors")))
                .handle(message -> {
                    File file = (File) message.getPayload();
                    // Only used to demonstrate poller error handling.
                    throw new IllegalStateException(
                            "Demo parse failure: " + file.getName());
                })
                .get();
    }

    @ServiceActivator(inputChannel = "filePollErrors")
    public void handleFileError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        System.err.println("File poll failure: "
                + failure.getClass().getSimpleName());
    }
}
~~~

This is an academic example that **intentionally throws an error**. In production, use structured logging instead of `System.err`, avoid printing full files or sensitive payloads, and move invalid files to quarantine according to business state.

### 6.2. Reading Each Configuration Piece

1. **Files.inboundAdapter:** creates a `File` source from a directory.
2. **endpoint.poller:** configures a polling endpoint running at fixed intervals.
3. **maxMessagesPerPoll(1):** caps messages fetched per poll per configuration; it does not replace retry counts.
4. **errorChannel("filePollErrors"):** specifies the destination for `ErrorMessage`s published by poller error handling.
5. **filePollErrors bean:** the channel exists in the Spring context.
6. **@ServiceActivator:** subscriber receiving `ErrorMessage`s from the dedicated channel.

When a file is present and the poller runs, exceptions thrown by the handler within the synchronous scope of the polling task are handled by the configured error strategy. In practice, verify via integration tests and logs that messages reach the right channel.

### 6.3. What If errorChannel Is Omitted from PollerSpec?

When the poller uses **MessagePublishingErrorHandler with global fallback**, exceptions can be published to the default **errorChannel**. Subscription config:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class GlobalErrorObserver {

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        System.err.println("Global integration failure: "
                + error.getPayload().getClass().getSimpleName());
    }
}
~~~

Note: Global `errorChannel` usually has a **default `LoggingHandler`**. Another subscriber can log the same error twice. And if a dedicated `filePollErrors` channel is configured, do not assume a global observer also receives a copy of errors from that flow.

### 6.4. Do You Need to Declare an errorChannel Bean Yourself?

No, not just to listen on the framework-provided global channel. Redefining a bean with the same name can alter topology, subscribers, and handling. When you need dedicated policies, prefer creating **filePollErrors** or a clearly named business channel.

### 6.5. Approaches for Annotations or XML

In systems using annotation-based inbound adapters, **@Poller** can be placed on the endpoint to set schedule, max messages, and error channel per that version's API. In Spring Integration XML namespace, the `poller` element can support an **error-channel** attribute. The principle remains identical to Java DSL: **the error destination belongs to the polling endpoint/error handler, not just external message producers**.

If an application declares both a global default poller and an endpoint-specific poller, know which configuration the endpoint receives. Read the actual configuration and test throwing an exception; never assume all endpoints share one error policy.

## 7. Writing a Safe Handler to Read ErrorMessage

### 7.1. Never Assume the Exception Is Always a MessagingException

A `Throwable` from an SFTP source failure might not be wrapped with `failedMessage`. Handlers should check types and fall back to `originalMessage` when available.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class PollingErrorLogger {

    private static final Logger log =
            LoggerFactory.getLogger(PollingErrorLogger.class);

    @ServiceActivator(inputChannel = "filePollErrors")
    public void log(ErrorMessage error) {
        Throwable throwable = error.getPayload();

        Message<?> failed = null;
        if (throwable instanceof MessagingException messageException) {
            failed = messageException.getFailedMessage();
        }

        Message<?> original = error.getOriginalMessage();
        Message<?> context = failed != null ? failed : original;

        Object correlation = context == null
                ? null
                : context.getHeaders().get("correlationId");

        log.error(
                "poller failure type={}, hasFailed={}, hasOriginal={}, correlation={}",
                throwable.getClass().getSimpleName(),
                failed != null,
                original != null,
                correlation,
                throwable);
    }
}
~~~

In production, assess whether logging `Throwable` might expose exception messages containing SQL, URLs with tokens, or personal data. When minimizing risk, log only exception class, error category, safe code, and correlation; store stack traces in access-restricted log systems.

### 7.2. Tracing with Endpoint/Flow IDs

Sometimes both `failed` and `original` lack correlation. Include:

- **Endpoint ID / flow ID:** identifies the polling source in config;
- **Business key:** order ID, batch ID, or sanitized file name;
- **Poll attempt:** timestamp, worker session, attempt count;
- **Source reference:** normalized file path, table/record, remote file ID;
- **Error classification:** data error, permission, network, DB timeout, or unknown.

Do not derive business keys solely from file names if business data can collide or the source is untrusted. Use stable keys normalized in the ingest pipeline.

### 7.3. Subscribers Must Not Retry Infinitely

A handler on `errorChannel` can log or **create a retry request**. Yet immediately re-invoking the entire input flow inside the handler can cause:

- Loops of error → retry → error on the same bad data;
- Re-reading files already accepted by the filter;
- Duplicate side effects in HTTP/JDBC;
- Scheduler/consumer stalls from slow error handling.

Instead, classify the error and create a recovery request with an **attempt limit**, business key, retry schedule, owner, and idempotency. If the source requires replay, rely on actual file/row/queue state rather than keeping `ErrorMessage` in memory.

## 8. Poller Errors in `receive()` Differ from Errors in Handlers

### 8.1. Errors Before a Message Exists

Example:

~~~text
Poller tick
  -> SFTP session factory connect()
  -> Authentication failed
  -> Throwable caught by error strategy
  -> ErrorMessage (no guarantee of failedMessage)
  -> sftpPollErrors
~~~

The right action is usually alerting on credentials/permissions and halting aggressive retries. You cannot quarantine a file that was never downloaded simply because an `ErrorMessage` arrived.

### 8.2. Errors After a Message Exists

~~~text
Poller tick
  -> FileReadingMessageSource.receive() -> Message<File>
  -> transformer parses CSV
  -> Validation failed
  -> ErrorMessage contains Throwable
     -> may hold failedMessage = File or transformed payload
  -> filePollErrors
~~~

Here you can quarantine the file, yet you must know **whether the filter already marked the file or whether the file was moved/deleted**. Error channels do not perform those actions automatically.

### 8.3. Errors When Sending to a Channel Without Subscribers

A poller endpoint received a message, yet the target channel or dispatcher rejects delivery. The error may be `MessageDeliveryException` or similar. Even with `failedMessage`, remediation primarily fixes wiring/availability or preserves input, rather than fixing CSV content.

### 8.4. Stage-Based Classification Table

| Stage | Example | Context Likely Available | Typically Appropriate Recovery |
|---|---|---|---|
| RECEIVE | SFTP session timeout | Flow/source ID, may lack Message | Reconnect, backoff, alert |
| QUERY | JDBC query failure | Query ID, DB exception; may lack row Message | Controlled retry or fix SQL |
| DELIVER | Output channel has no subscriber | Received Message, target channel | Fix config, prevent input loss |
| TRANSFORM | CSV invalid schema | `failedMessage`/File context | Quarantine, report invalid data |
| HANDLE | DB write error | Business key, normalized input | Check commit, idempotent retry |
| OUTBOUND | HTTP timeout | Request ID, endpoint, unknown state | Lookup status/idempotency |
| ERROR_HANDLER | Subscriber failure | `ErrorMessage` and secondary error | Fallback mechanism, prevent loops |

### 8.5. Do Not Treat `receive() == null` as an Error

When a poller finds no files or `QueueChannel` is empty, `MessageSource`/`PollableChannel` can return **null**; this is normal and does not emit an `ErrorMessage`. If the business expects a file every hour and none arrive, **monitor last successful poll / last input**, rather than waiting for `error-channel` to alert.

## 9. Retry Advice vs. error-channel: Which Layer Owns It?

### 9.1. Two Distinct Phases

In many flows, retry advice wraps a handler to retry an operation before the final exception escapes. The error publisher may only receive **the error after retries are exhausted**, depending on advice placement and recovery callbacks.

~~~text
Poller receives Message
   -> Handler with retry advice
      -> attempt 1: fails
      -> attempt 2: fails
      -> attempt 3: fails
      -> exhausted: throw/recover
   -> Poller error strategy
      -> ErrorMessage if exception propagates/publishes
~~~

If a recovery callback **handles the exception and returns a value treated as success**, the poller may see no exception to publish. Conversely, a callback might send an `ErrorMessage` to a recovery channel itself. Test to avoid **two places both sending errors or two places both retrying**.

### 9.2. When to Retry?

| Error Group | Commonly Appropriate Decision |
|---|---|
| Transient network timeout | Retry with exponential backoff, bounded |
| Transient DB connection | Conditional retry with idempotency |
| HTTP 429/503 | Honor `Retry-After`, retry within time budget |
| CSV invalid schema | Do not infinitely retry verbatim; quarantine |
| Rejected credentials/permissions | Alert and fix config; avoid hammering |
| HTTP timeout after POST | Query status or use idempotency key |
| Message duplicated by another consumer | Dedupe/check state, do not repeat side effects |

### 9.3. Total Attempts Can Multiply

If the HTTP client retries 3 times, handler advice retries 3 times, the poller re-reads the file after a restart, and an external broker redelivers, actual requests can far exceed "retry 3 times". Enforce a **global attempt budget per business key** or one primary retry owner per step.

### 9.4. Never Assume ErrorMessage Means Data Is Saved for Retry

`PublishSubscribeChannel` and many `MessageChannel`s operate in memory. If the process crashes, an error message sitting in a channel may not survive recovery. For at-least-once guarantees, use durable inputs, state stores/outboxes, transactions, and proper replay logic.

### 9.5. Advice Chain Ordering Matters

If one advice manages transactions and another retries, the wrapping order around the handler changes rollback boundaries and how many attempts share the same transaction. Never apply a fixed recipe without examining resource types, transaction managers, and real endpoint config; inject faults step-by-step to verify semantics.

## 10. Pollers Receiving Multiple Messages and Behavior When One Fails

### 10.1. Role of maxMessagesPerPoll

**maxMessagesPerPoll** caps how many messages a poller pulls in one trigger per config. It is **not** a retry count. An error on the second message can halt the poll batch or impact remaining messages depending on poller/error strategy behavior.

### 10.2. One Single Failure Should Not Lose the Whole Batch

With CSV files, one file can hold many rows. If the app imports row-by-row with unclear transaction and file-filter design, one failing row can leave:

- Earlier committed rows still persisted;
- The failing row needing correction or quarantine;
- Subsequent rows unprocessed;
- The file marked as seen by the filter;
- Replaying the file reprocessing earlier rows.

Define the **unit of processing and acknowledgment**: per file, per batch, or per record. If the whole file is one transaction, account for external data sources and outbound effects.

### 10.3. Preventing Starvation

A poison file that constantly throws exceptions can consume poll turns, starving valid files. Use quarantine, controlled skip policies, idempotent state, and alerts instead of scanning the same bad data forever.

### 10.4. Backpressure and Concurrency

Raising poll frequency or adding a `taskExecutor` increases throughput but also increases:

- Concurrent SFTP/DB connections;
- Risk of two workers claiming the same file/record;
- Network error rates from overload;
- Difficulty tracing errors once async tasks cross threads;
- Backlog on error channels or recovery queues.

Coordinate **task executors, source locks/claims, idempotency, `receiveTimeout`, and channel capacity**. Never merely raise thread counts to handle more errors.

## 11. File Polling: Managing Filters, File State, and Quarantine

### 11.1. Why Can Files Still Be Lost Even When Errors Hit the Error Channel?

`FileReadingMessageSource` typically combines filters to select files. Once a file is chosen, **filters and metadata stores** can mark the file accepted before the business handler finishes. If the handler throws afterward, an `errorChannel` subscriber that only logs does not undo filter state.

Example:

~~~text
09:00:00  Poller spots invoice-274.csv
09:00:00  Filter accepts file and records state "seen"
09:00:01  JDBC handler fails
09:00:01  ErrorMessage sent to filePollErrors
09:00:01  Error handler logs and finishes
09:00:03  Poller runs again; file skipped due to filter
~~~

In this case, business data never succeeded yet the file may never be re-read. Exact behavior depends on **filters, persistent metadata stores, accept-once settings, file moves/deletes, and restarts**.

### 11.2. State Machine for File Import

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> CLAIMED: Poller claims file
    CLAIMED --> VALIDATING: Read and validate schema
    VALIDATING --> PROCESSING: Valid data
    VALIDATING --> QUARANTINED: Invalid data
    PROCESSING --> PROCESSED: Business write succeeded
    PROCESSING --> RETRY_WAIT: Transient error
    RETRY_WAIT --> PROCESSING: Retry due
    RETRY_WAIT --> MANUAL_REVIEW: Budget exhausted
    PROCESSED --> ARCHIVED: Retained per policy
    QUARANTINED --> [*]
    ARCHIVED --> [*]
~~~

This diagram is a suggested business model, not built-in `FileReadingMessageSource` states. Store state in a durable store or verifiable file move/rename workflows.

### 11.3. Separating Error Recovery from File Replay

| Error | Handling at Error Channel | Handling at File Source |
|---|---|---|
| Malformed CSV structure | Record `INVALID_INPUT`, notify producer | Quarantine file, do not poll infinitely |
| JDBC unavailable | Record `TRANSIENT`, create retry task | Keep safe input copy, idempotent replay |
| File still being written | Record or monitor source state | Wait for file stability before ingest |
| Locked file or permission denied | Alert operations | Fix permissions/locks, avoid aggressive retry |
| Partially processed file | Record `PARTIAL`/`UNKNOWN` | Reconcile per record or transactional batch |

### 11.4. Quarantine Must Have an Owner and Replay Rules

Quarantined files must not sit copied into an `errors` directory forever. Track who owns remediation, error reason, batch/business key, appropriate hash/checksum, parser version, retention, and how to replay after data fixes. **Never modify/copy files directly from `ErrorMessage` if another process may have altered the file**.

### 11.5. File Outbound Failing Inside a Poller

An inbound File poller can call `FileWritingMessageHandler` to emit files. If the outbound handler fails synchronously within the same polling task, the exception can be published by the poller's error handler. However, if a file was partially written, `ErrorMessage` does not delete partial files. Write to a temporary path and rename atomically where the filesystem supports it, verifying outcomes before marking success.

## 12. SFTP Pollers: Sessions, File Sync, and Proper Retries

### 12.1. Two Distinct Error Groups

SFTP inbound can fail **at the remote session level** before a `Message` exists, or **in local downstream handlers** after syncing the file.

~~~mermaid
flowchart TD
    P["SFTP poller"] --> CONN["Open session / list remote directory"]
    CONN -->|"Failed"| NET["Connection/auth/permission error"]
    CONN -->|"Succeeded"| TRANS["Download or fetch remote file"]
    TRANS -->|"Succeeded"| MSG["Message<File> or configured form"]
    TRANS -->|"Partial transfer"| PART["Incomplete file state"]
    MSG --> PARSE["Parse/validate/business handler"]
    PARSE -->|"Error"| DATA["Data processing error"]
    NET --> E["Error publisher if configured"]
    PART --> E
    DATA --> E
    E --> EC["sftpPollErrors"]
~~~

If the session fails before a `Message` forms, handlers must not assume `failedMessage` exists. Meanwhile, parse errors after download may reference the local file; **the remote file is not automatically restored** by `ErrorMessage`.

### 12.2. SFTP Recovery Strategies

| Scenario | Action |
|---|---|
| Timeout or temporary network loss | Backoff, bounded reconnect |
| Authentication failure | Alert, fix secret/credentials; no hot retries |
| Remote permission denied | Verify ACLs and paths |
| Remote file mid-upload | Wait for rename/marker or stability check per contract |
| Partial download | Never pass local partial file to parser |
| Downloaded CSV fails schema | Quarantine local copy, notify partner |
| Outbound upload succeeded, response lost | Verify checksum/remote path before resending |

### 12.3. Remote/Local Boundary

An SFTP inbound system often has a remote filter and a local filter or a metadata store tracking files. Edge cases include:

- Server marked remote file transferred, yet local processing failed;
- Local file exists, yet the message never reached the handler;
- Partner overwrites a remote file using the same name;
- Two pollers across instances spot the same file simultaneously;
- Identical file names with different contents.

Therefore, recovery needs **remote file identity/version, metadata stores, local readiness state, and business-key idempotency**. Setting `.errorChannel("sftpPollErrors")` alone does not prevent lost or duplicated files.

### 12.4. SFTP Outbound Errors During Polling

A polling consumer can pull work from a `QueueChannel` and upload files via SFTP. If the session factory/remote write throws synchronously, the poller can publish an `ErrorMessage`. Yet once the command left the `QueueChannel`, you need to know where it remains stored for retry. For critical workflows, use a **durable task store/queue** or appropriate transaction/ack mechanisms.

### 12.5. Do Not Let Error Handling Disrupt Admin Sessions

Error handlers should avoid repeatedly opening SFTP connections on the same poll thread while the server is down. Sending alert emails or calling inspection APIs synchronously can block the scheduler. Classify quickly, persist a recovery task, and process asynchronously on a resource-bounded worker.

## 13. JDBC Pollers: Query Failures, Row State, and Transactions

### 13.1. Pollers Fetching Records from the DB

JDBC inbound polling can query pending records periodically:

~~~sql
SELECT id, tenant_id, order_id, payload_ref
FROM integration_work
WHERE state = 'PENDING'
ORDER BY created_at;
~~~

This is a conceptual query. Real implementations need row limits, proper indexes, transactions/locking, and multi-instance claim safety; never run unbounded `SELECT`s on large tables.

### 13.2. Errors at Query Time

If the DB is unavailable or SQL is invalid, the source can throw **before building a Message containing a row**. `ErrorMessage` may hold a `DataAccessException` or `MessagingException` with `failedMessage` null. You cannot know which row was targeted solely from the exception, because failure occurred before a successful `receive`.

Operational approach:

- Mark source/DB unavailable and retry with backoff;
- Monitor last-successful-query, pending record counts, and lag;
- Alert on recurring SQL/permission/config failures;
- Never bulk-mark records processed due to a source error event.

### 13.3. Errors After Fetching a Row

Suppose a JDBC inbound poller reads `order-274`, the HTTP outbound handler succeeds on POST, and the JDBC update `state=PROCESSED` fails. The next poll may pick up `order-274` again:

~~~text
PENDING row order-274
    |
    +--> poller reads
    +--> HTTP POST succeeds
    +--> status update fails
    |
PENDING row order-274 remains
    |
next poll may send HTTP POST again
~~~

This demonstrates **at-least-once processing with duplicate side-effect risk**. `ErrorMessage` reports the failure without guaranteeing the earlier HTTP call did not succeed.

### 13.4. Durable State Claiming

One way to manage work uses states **PENDING → CLAIMED → SUCCEEDED/RETRY/FAILED** with leases, worker IDs, attempt counts, and versions. Conditional updates can help:

~~~sql
UPDATE integration_work
SET state = 'CLAIMED',
    worker_id = :workerId,
    attempt = attempt + 1
WHERE id = :workId
  AND state = 'PENDING';
~~~

Treat the claim as successful only when exactly one row is updated. This is logical illustration; multi-worker setups also need work selection strategies, isolation levels, lease expiry, and crash protection. **An error channel does not unstick claims.**

### 13.5. Transactions in Polling Endpoints

A poller can be configured with transaction advice spanning a processing scope. However:

- DB transactions only cover resources managed by the transaction manager;
- HTTP/SFTP do not join local DB transactions automatically;
- Swallowing an exception in an error handler can affect rollback decisions;
- Post-commit errors cannot be rolled back by emitting `ErrorMessage`;
- Verify behavior across poller, advice chain, source, and JDBC handler for your config.

To keep DB state and command/event publishing aligned, consider **transactional outbox/inbox** or durable state machines. Enforce idempotency on re-reads.

## 14. QueueChannel Polling Consumers: What Once a Message Left the Queue?

### 14.1. Difference from File Inbound

`QueueChannel` is a **PollableChannel**. A producer sends a `Message` to `QueueChannel`; the polling consumer pulls it when woken by the scheduler. Once `receive` removes the message from the queue, a handler failure **does not automatically put the message back on the queue**.

This is critical for **in-memory `QueueChannel`s**: on process restart, unprocessed messages can vanish. When durable recovery is required, use appropriate persistence or a durable broker/queue.

### 14.2. Illustrative Java DSL Configuration

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
public class QueuedOrderPollingFlow {

    @Bean
    public QueueChannel pendingOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public MessageChannel orderPollErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow orderWorker() {
        return IntegrationFlow
                .from(pendingOrders(),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(1))
                                        .maxMessagesPerPoll(5)
                                        .errorChannel("orderPollErrors")))
                .handle(message -> {
                    // Simulate OrderCommand processing failure.
                    throw new IllegalStateException("Order service unavailable");
                })
                .get();
    }
}
~~~

`orderPollErrors` needs a subscriber (such as a Service Activator) to receive `ErrorMessage`s. Config syntax depends on DSL version; the key takeaway is **attaching a poller to a `PollableChannel` consumer**, not only to a File `MessageSource`.

### 14.3. Queue Recovery

If a `Message` was pulled from `QueueChannel` and the handler failed, do not blindly push the exact `Message` back onto the channel from the error handler. Instead:

1. Define a business key or command ID;
2. Persist processing state before/at the point requiring durability;
3. On error, classify transient vs. permanent;
4. Save a retry command or move the message to a durable recovery store;
5. Replay only with retry limits, timeouts, and idempotency;
6. Verify side effects before marking success.

**When using `QueueChannel` backed by a persistent `MessageStore` or transaction synchronization**, behavior differs from in-memory queues; explicitly test commit/rollback/receive semantics.

## 15. Pollers and HTTP, JMS, AMQP, Kafka Adapters

### 15.1. HTTP Outbound Called from a Polling Flow

A File or JDBC poller can pass messages to an HTTP outbound gateway. If the HTTP call throws **synchronously within the poller's call stack**, the error can reach the poller's configured `errorChannel`. However:

- Whether 4xx/5xx statuses throw exceptions or return responses depends on client/gateway config;
- An HTTP timeout does not prove the partner did not process the request;
- If the gateway runs asynchronously, error callbacks may occur outside the poller stack;
- Inbound HTTP gateways process incoming requests rather than using this poller.

Retrying HTTP write operations should carry an **Idempotency-Key** per partner contract or perform status lookups to prevent duplicates.

### 15.2. JMS and AMQP Outbound from a Poller

If a polling consumer processes a command and sends to JMS/AMQP via an outbound adapter, synchronous send errors can report to poller error handling. Yet:

- The broker may have accepted the message while the producer response/ack is indeterminate;
- JMS transactions or RabbitMQ publisher confirms have their own handling;
- Publishing an `ErrorMessage` is not proof the source rolled back;
- Once downstream consumers process a message, you cannot simply "unsend" it.

With **JMS/AMQP message-driven inbound**, errors are typically managed by **listener containers**, ack/nack, requeue, transactions, and DLQs. Do not treat those listeners as `PollerSpec` merely because they continuously consume messages.

### 15.3. Kafka Outbound from a Poller

Kafka producers can send asynchronously. The poller completes its handler before the producer callback reports failure; then the failure **does not necessarily return to the poller-specific error channel**. Configure callback/error handling on the Kafka outbound adapter and define producer transactions, acknowledgments, retries, and DLT/recovery per contract.

With **Kafka inbound message-driven adapters**, Kafka listener containers and offset handling use dedicated mechanisms rather than a File poller's `errorChannel`.

### 15.4. Adapter Comparison Table

| Pattern | Role of Poller-Specific Error Channel | Additional Checks Required |
|---|---|---|
| File poller → sync HTTP outbound | Can catch exceptions on poller stack | HTTP status, timeouts, idempotency |
| SFTP poller → JDBC handler | Catches receive/handler errors in poller scope | Remote file state, DB commit |
| QueueChannel poller → JMS send | Observes sync handling/send errors | Source queue durability, broker accept/tx |
| JDBC poller → async Kafka producer | Does not catch later callbacks automatically | Producer callbacks, outbox, acks |
| JMS/AMQP listener → IntegrationFlow | Not a Spring Integration poller by default | Ack/nack, listener error handler, DLQ |
| Kafka listener → IntegrationFlow | Does not use `PollerSpec` by default | Offsets, retries, container error handler, DLT |
| HTTP inbound gateway | Not a periodic poller | HTTP error status/response mapping |

### 15.5. External Systems May Already Have Side Effects

When a handler throws, ask:

- Did the DB commit?
- Did the target HTTP server create the order?
- Did the JMS/AMQP broker accept the message?
- Is the Kafka event already on the topic?
- Was the SFTP file renamed/moved/deleted?

`ErrorMessage` cannot definitively answer all of these. If outcomes are unknown, **reconcile** before retrying or compensating to avoid causing further side effects.

## 16. Designing Error Contracts for Pollers

### 16.1. One ErrorMessage Is Not Enough for Operations

`ErrorMessage` is an internal Spring message type with a `Throwable` payload. It works well for an error handler reading the cause, yet should not serve as the **sole durable format for replays or external events**.

Classify errors with:

- **flowId/endpointId:** which poller ran and which business service owns it;
- **stage:** `RECEIVE`, `TRANSFORM`, `VALIDATE`, `PERSIST`, `OUTBOUND_SEND`, or `ACK`;
- **source reference:** file path/remote path/record ID or queue message ID;
- **correlationId:** links messages across a batch/transaction;
- **business key:** deduplication key;
- **error class and category:** `Throwable`, `TRANSIENT`, `INVALID_INPUT`, `CONFIGURATION`, `PERMISSION`, or `UNKNOWN`;
- **attempt/budget:** retries consumed;
- **disposition:** `RETRY_PENDING`, `QUARANTINED`, `NEEDS_RECONCILIATION`, or `TERMINAL`;
- **observed outcome:** succeeded/failed/unknown at each target system;
- **owner and deadline:** who resolves if self-recovery fails.

### 16.2. Example Standardized Error Event

~~~json
{
  "eventType": "integration.poll.failed",
  "eventVersion": 1,
  "flowId": "sftp-orders-import",
  "endpointId": "sftpInbound",
  "stage": "PERSIST",
  "sourceReference": "incoming/orders-274.csv",
  "businessKey": "order-274",
  "correlationId": "batch-2026-274",
  "exceptionClass": "MessageHandlingException",
  "rootCauseClass": "DataAccessResourceFailureException",
  "category": "TRANSIENT",
  "attempt": 2,
  "maxAttempts": 4,
  "disposition": "RETRY_PENDING",
  "nextAttemptAt": "2026-11-23T09:05:00Z"
}
~~~

This is an **application-defined schema**, not default `ErrorMessage` content. Source references carry sanitized values only; never embed files containing PII, JDBC passwords, bearer tokens, access keys, or full stack traces into events.

### 16.3. Errors Lacking Message Context

If an SFTP session fails before a `Message` exists, the event may contain only `endpointId`, remote host alias, `stage=RECEIVE`, exception type, and timestamp. Never fabricate a fake `businessKey`/`orderId` and try to replay unread data.

### 16.4. Do Not Persist Raw Throwable as an External Contract

Java `Throwable`s carry cause graphs, stack traces, runtime-specific classes, and potential sensitive details; never serialize them arbitrarily over Kafka/JMS or into long-lived databases. For recovery across restarts, persist **valid command/data references** and normalized error info.

### 16.5. Separate Triage from Recovery

An `ErrorMessage` subscriber can emit metrics and open incidents. A separate recovery coordinator decides retry/quarantine/reconcile from state. When recovery tasks must never be lost, persist **durable tasks** within proper transaction/ack boundaries—never just send an in-memory message and claim it was saved.

## 17. Observability: Detecting Both Errors and Silent Pollers

### 17.1. Structured Logging

Logs should include timestamp, endpoint, flow, adapter, correlation, exception type, stage, and outcome. Example:

~~~text
level=ERROR
flow=sftp-orders-import
poller=sftpInbound
stage=RECEIVE
exceptionType=SftpException
errorCategory=TEMPORARY_UNAVAILABLE
attempt=2
outcome=RETRY_SCHEDULED
~~~

Never log raw `failedMessage.toString()` when it may hold financial payloads, sensitive files, tokens, or user data. For source-level errors, log a safe source ID instead of printing raw connection URIs with credentials.

### 17.2. Metrics

| Suggested Metric | Meaning |
|---|---|
| `poll_attempt_total` | Scheduler poll triggers |
| `poll_messages_received_total` | Messages actually returned by source |
| `poll_errors_published_total` | ErrorMessages emitted by poller/error publisher |
| `processing_failures_total` | Handler failures by stage/category |
| `poll_retry_total` | Retries per flow |
| `retry_exhausted_total` | Messages exhausting retry budget |
| `quarantine_backlog` | Files/records awaiting fixes |
| `last_successful_poll_timestamp` | Timestamp of last poll completing cleanly per definition |
| `last_nonempty_poll_timestamp` | Last time input was actually received |
| `oldest_pending_item_age` | Age of oldest waiting work item |
| `error_handler_failure_total` | Failures in the error flow subscriber itself |

These names are **application-definable metrics**. Do not assume Spring Integration emits all of them automatically. Use low-cardinality labels (`flow`, `stage`, `adapter`); never use individual file paths or message IDs as metric labels.

### 17.3. Detecting a Running Poller Receiving No Data

Suppose files are expected every 10 minutes; the poller keeps ticking yet sees no files for 2 hours. Zero exceptions occur and **`errorChannel` stays silent**. Alert on **`last_nonempty_poll`**, expected file cadence, partner heartbeats, or source backlog—not error counts alone.

### 17.4. Detecting a Completely Stopped Poller

A scheduler config failing to start the endpoint, a stopped bean, or an exhausted thread pool can stop polling entirely. Check:

- Endpoint lifecycle/running state;
- Timestamp of most recent poll trigger;
- Scheduler pool utilization and thread exhaustion;
- Receive timeouts and channel capacities;
- Executor/scheduler logs;
- Start/stop config and deployment version.

Silent stalls cannot be solved by adding another `@ServiceActivator` on `errorChannel` when the task itself isn't running.

### 17.5. Distributed Tracing

When a poller pulls a `Message` and calls HTTP/Kafka, propagate correlation/trace context across headers, executors, and adapters appropriately. A `Throwable` or `ErrorMessage` holding partial context does not guarantee full distributed traces; test propagation and persist business keys in the state store.

## 18. Case Study: SFTP Poller Importing Orders to JDBC and HTTP

### 18.1. Business Need

Company A receives CSV files from Partner B over SFTP every 5 minutes. Valid records are persisted to a database, and then the system calls Logistics Partner C over HTTP to book shipment. Business requirements:

1. Files must never be double-processed uncontrollably.
2. Schema-invalid data must be isolated for correction.
3. SFTP network errors must retry with backoff without deleting source files.
4. DB failures after partial saves must have reconciliation/transaction safeguards.
5. HTTP timeouts must never create duplicate shipments.
6. Error handlers must capture enough details for operators to locate failures.

### 18.2. Solution Architecture

~~~mermaid
flowchart TD
    SFTP["SFTP Server B"] --> POLL["SFTP inbound poller"]
    POLL --> FILE["Local file / durable reference"]
    FILE --> PARSE["CSV validation"]
    PARSE --> DB["JDBC persist order"]
    DB --> HTTP["HTTP register shipment C"]
    HTTP --> OK["Processed + archived"]
    POLL -. "Receive exception" .-> ERR["sftpPollErrors"]
    PARSE -. "Handler exception in poller scope" .-> ERR
    DB -. "Handler exception in poller scope" .-> ERR
    HTTP -. "Synchronous exception in poller scope" .-> ERR
    ERR --> CLASSIFY["Classify + read safe context"]
    CLASSIFY --> DEC{"Category?"}
    DEC -->|"Network transient"| RETRY["Backoff / retry task"]
    DEC -->|"Invalid CSV"| QUAR["Quarantine file"]
    DEC -->|"Unknown outcome"| RECON["Reconciliation"]
    DEC -->|"Security/config"| ALERT["Alert / manual fix"]
~~~

Error paths depend on configuration: if an endpoint switches threads, later HTTP/Kafka callbacks may follow a different error strategy. The diagram also cannot fully depict commits/acks; those must be tested.

### 18.3. Scenario A — SFTP Session Fails to Open

The poller times out before downloading a file; `ErrorMessage` arrives from the configured error strategy. `failedMessage` may be null. Error handler:

- Tags `flow=sftp-orders-import`, `stage=RECEIVE`;
- Classifies as transient network error;
- Waits and retries with backoff, bounding new sessions;
- Alerts if overdue;
- Never moves a nonexistent file to quarantine or marks a file processed.

### 18.4. Scenario B — CSV Fails Schema

The file downloaded safely, the transformer receives the File `Message`, and a required column is missing. Handler throws; `ErrorMessage` may hold `failedMessage`. Error handler:

- Extracts safe file reference and correlation;
- Marks the batch/record invalid;
- Moves the file to quarantine per policy;
- Saves masked failure reason for B to fix;
- Stops the poison file from consuming every poll turn.

Never retry the exact invalid CSV until resources exhaust. If the file filter already accepted the file, control re-ingestion after fixes.

### 18.5. Scenario C — JDBC Down Mid-Batch

The file is valid, yet the DB times out mid-batch. If some rows already committed, the next poll could re-insert duplicates. You need:

- Reconciliation of committed rows via business keys;
- Transactions/unique constraints at the right batch granularity;
- Durable, idempotent retry tasks;
- Never mark the file `PROCESSED` simply because an error message was logged.

### 18.6. Scenario D — HTTP Creates Shipment Then Times Out

An order is in the DB, and HTTP POST `CreateShipment` times out. C may have created the shipment even though A missed the response. Never blindly retry with a new request ID. Instead:

- Mark `RESULT_UNKNOWN`;
- Look up shipment by stable key/idempotency key;
- If created, save the shipment ID and advance the step;
- If confirmed not created, retry within budget;
- If indeterminate, route to manual reconciliation.

### 18.7. Scenario E — Poller Emits ErrorMessage, Yet File Is Never Re-Read

Operations sees an error on `sftpPollErrors` and assumes the poller will retry automatically. In reality, the local filter marked the file accepted, so subsequent polls skip it. This causes **silent missing processing** even though alerts fired.

Fix: add durable file state/metadata, quarantine, or retry workers referencing the file and business key, with clear rules for resetting filters or requeueing. Never fix this by disabling all filters, which risks mass duplicates.

### 18.8. Scenario F — Source Stalls During Error Handling

The error handler sends emails/pushes tickets while the logging service stalls for 30 seconds. Running synchronously in the poller error path blocks the task scheduler and delays other files. Keep error observers fast/bounded, offload critical notifications to durable tasks, and decouple alert workers from pollers.

### 18.9. Completion Criteria Table

| Step | Required Evidence |
|---|---|
| Receive | Remote/local file reference, transfer state |
| Parse | Schema/version and per-record or batch validation result |
| Persist | DB commit and business key |
| HTTP outbound | Request ID, result, or unknown state |
| Error notification | `ErrorMessage` received by the expected channel |
| Retry/quarantine | Durable record, attempt, owner |
| Final disposition | Grounded `PROCESSED`, `QUARANTINED`, or `MANUAL_REVIEW` |

### 18.10. Takeaway

**Routing errors to the right channel** is necessary, yet integration quality hinges on **source state, transaction boundaries, timeout semantics, and verifiable replay**. A zero-loss system knows exactly where a message sits after the error handler finishes.

## 19. Testing Poller Error Paths with QueueChannel

### 19.1. Why Test with QueueChannel First?

`QueueChannel` removes filesystem or SFTP dependencies in initial tests. Send a `Message` into an input queue, let the polling consumer pull it and intentionally throw, then read the `ErrorMessage` from a separate **test error channel**.

This verifies:

- The poller is actually running;
- The handler is invoked;
- The exception is published to the configured error destination;
- `ErrorMessage.payload` is a `Throwable`;
- Correlation is retrievable from context if provided.

It does not yet test file filtering, remote transfers, or broker acknowledgments.

### 19.2. JUnit/Spring Integration Test Template

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PollerErrorFlowTest.Config.class)
class PollerErrorFlowTest {

    @Autowired
    QueueChannel testInputs;

    @Autowired
    QueueChannel testErrors;

    @Test
    void publishesFailureToDedicatedErrorChannel() {
        testInputs.send(MessageBuilder
                .withPayload("invalid-order")
                .setHeader("correlationId", "test-batch-1")
                .build());

        Message<?> received = testErrors.receive(5_000);
        assertNotNull(received, "Expected an ErrorMessage");
        ErrorMessage error = assertInstanceOf(ErrorMessage.class, received);
        assertNotNull(error.getPayload());
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        QueueChannel testInputs() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testErrors() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow failingPoller() {
            return IntegrationFlow.from(testInputs(),
                    spec -> spec.poller(
                            Pollers.fixedDelay(Duration.ofMillis(100))
                                    .maxMessagesPerPoll(1)
                                    .errorChannel("testErrors")))
                    .handle(message -> {
                        throw new IllegalArgumentException("demo failure");
                    })
                    .get();
        }
    }
}
~~~

This test uses Spring Integration Java DSL, Spring Test, and JUnit Jupiter. It assumes matching dependency versions and an active task scheduler in the Spring context. The core assertion is that **polling consumer errors arrive on `testErrors`**, not on a global listener. Adjust DSL overloads if your version differs while preserving behavior.

### 19.3. Verify Nullable Context

Add a test simulating a source failure before `Message` creation. The resulting `ErrorMessage` may carry only a `Throwable` without `failedMessage`. Handlers and tests must tolerate null instead of always expecting a `File`.

### 19.4. Verify Global Fallback

Configure another test flow omitting a dedicated error channel, ensure the proper error publisher is enabled, and subscribe an observer on global `errorChannel`. Trigger a failure and verify delivery. Avoid registering subscribers with real side effects in tests, as the default `LoggingHandler` may also run.

### 19.5. Verify No ErrorMessage When No Message Exists

Run an empty `QueueChannel` or a File adapter finding no files; the poller still ticks without error. Tests must not expect `ErrorMessage`s when `receive` returns null. If timeliness matters, write a **separate freshness/heartbeat test**.

### 19.6. Test Errors Outside the Poller Stack

Add an `ExecutorChannel` or async outbound component and trigger failures after the polling task returns. Verify errors go to the executor/adapter's error strategy rather than assuming `testErrors` receives them. This catches bugs when increasing concurrency causes lost exceptions.

### 19.7. Test Duplicates and Restarts

For File/SFTP/JDBC integration tests, also verify:

1. Are already-received messages re-read?
2. Is input durably saved?
3. When a worker crashes, do retry tasks resume after restart?
4. Do business keys block duplicate side effects?
5. Does quarantining invalid files let valid files continue processing?
6. Do permanent errors trigger infinite retry loops?

## 20. Runbook: Investigating When a Poller Fails to Send Errors to the Expected Channel

### Step A — Verify the Poller Is Actually Running

1. Check whether the bean/endpoint is **running** in the Spring context.
2. Check that the scheduler has the task registered and available threads.
3. Inspect logs for latest poll, successful poll, non-empty poll, and backlog.
4. Verify the `MessageSource` or `PollableChannel` actually has data.
5. Verify `maxMessagesPerPoll`, fixed-delay/fixed-rate/cron, and receive timeouts.

If the poller isn't running, don't start by tweaking `@ServiceActivator` on `errorChannel`. Without task execution, no task exception exists to publish.

### Step B — Locate Where the Exception Occurred

**Inside the poller invocation?** Receive or synchronous handler errors can be handled by the poller's error handler.

**Inside an executor/async callback?** The error may be on another thread needing its own error strategy.

**Inside an inbound listener/container?** For message-driven JMS, AMQP, or Kafka, inspect the container's error handler/ack/offset settings.

**Inside an HTTP inbound gateway?** Requests may map to HTTP responses rather than polling task errors.

### Step C — Inspect the Error Destination

1. Is the poller configured with `.errorChannel("...")` or equivalent?
2. Is the channel bean defined in the context?
3. Is a subscriber listening on that exact channel name?
4. Is global `errorChannel` created by the framework with a logging subscriber?
5. Does the message carry an `errorChannel` header, and does the error publisher honor it?
6. Did another endpoint establish its own error flow?
7. Did retry advice or a recovery callback consume the exception before it reached the poller?

**If a dedicated channel received the error**, global `errorChannel` may not receive a duplicate copy. That is intentional routing, not lost errors.

### Step D — Verify the Error Message Contract

1. `ErrorMessage.payload` must be a `Throwable`.
2. If the `Throwable` is a `MessagingException`, read `failedMessage` with a null check.
3. `originalMessage` may also be null.
4. `failedMessage.payload` may no longer match initial input after transformers.
5. Record safe correlation/flow/stage for tracing.
6. Never log payloads containing PII/secrets.

### Step E — Inspect the Source Resource

| Source | Verification Questions |
|---|---|
| File | Did the filter mark the file? Was it moved/deleted/quarantined? |
| SFTP | Did the session fail before download? Partial file? Remote metadata? |
| JDBC | Did the query return rows? Is the row `CLAIMED`/`PROCESSED`? Did the transaction commit? |
| QueueChannel | Did `receive` remove the message from the queue? Is there a durable store? |
| HTTP outbound | Did the server process POST despite caller timeout? |
| Broker outbound | Did the broker accept the publish? On which thread did the error callback fire? |

### Step F — Recover Safely

- For permanent data errors: quarantine, fix data, and replay the right version.
- For transient infrastructure errors: retry with backoff, time budget, and idempotency.
- For unknown outbound outcomes: reconcile before retrying.
- For lost poller heartbeats: fix scheduler/lifecycle/availability.
- For failing error handlers: capture secondary failures and use fallback/recovery stores.
- For SLA breaches: open an incident naming owner and business impact.

### Step G — Close the Incident

Never simply record "saw ErrorMessage". Prove the input reached **`PROCESSED`**, **`QUARANTINED`**, **`RETRY_PENDING` with durable reference**, or **`MANUAL_REVIEW` with an owner**. For critical integrations, reconcile database, file, HTTP, and broker states.

## 21. Preventing Error Loops: When the Error Handler Fails Too

### 21.1. Error-of-Error

A Service Activator listening to `filePollErrors` might call Slack/email, write to a DB, or push events to a queue. If those auxiliary systems fail, the error handler can throw a new exception. Depending on channel and dispatcher, secondary errors can propagate back to the error publisher, get logged, or trigger unintended effects.

**Never assume a second ErrorMessage will automatically reach the right place without data loss.** Design fallbacks and real tests.

### 21.2. Better Design

- Keep frontline handlers lightweight, time-bounded, and resource-bounded;
- Classify errors and strip sensitive data;
- Persist durable incident/recovery requests when required by business rules;
- Dispatch notifications via an independent worker with retry caps;
- Never use the source channel as the error handler's default output;
- Deduplicate notifications by failure ID/correlation;
- Monitor error handler backlogs and failures;
- Ensure source handling/acks align with recovery state persistence.

### 21.3. PublishSubscribeChannel and Duplicate Side Effects

A publish-subscribe channel can deliver `ErrorMessage` to multiple subscribers. If two subscribers both trigger a compensation like "release inventory", the action can run twice. Separate roles clearly:

| Subscriber | Responsibility |
|---|---|
| Logging observer | Writes structured logs |
| Metrics observer | Increments counters by flow/category |
| Recovery coordinator | Single logical owner deciding retry/quarantine/compensation |
| Alerting worker | Sends alerts via durable tasks with rate limits |

Never rely on subscriber ordering as a transactional guarantee for compensation sequencing. When recovery has dependencies, manage them inside a coordinator/state store.

### 21.4. Channels Without Subscribers

For dedicated error channels, when no subscribers exist or the channel rejects sends, behavior may be a `MessageDeliveryException`, a log entry, or quiet completion per config. Some `PublishSubscribeChannel` setups offer **`requireSubscribers`**, though defaults and activation vary by version/bean setup. Test what happens when subscribers are stopped, removed, or the error channel overflows.

## 22. Common Anti-Patterns with Polling Error Flows

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking every exception reaches global errorChannel | Sync or async exceptions missed | Map actual scope of error publishers |
| Adding `@ServiceActivator` without configuring poller/error strategy | Handler never receives expected errors | Check endpoint, channel, publisher |
| Misspelling errorChannel name or missing dedicated bean | Error messages misrouted | Verify bean and subscriber names |
| Reading failedMessage without null checks | `NullPointerException` on pre-receive SFTP/JDBC errors | Handle missing Message context |
| Casting every `failedMessage.payload` to `File` | `ClassCastException` after transformers | Inspect runtime type and stage |
| Logging full error payloads | Exposes PII, tokens, or huge files | Structured logging/masking |
| Treating `ErrorMessage` as automatic retry | Files/rows never reprocessed | Durable retry logic, file state |
| Disabling filters to "fix" lost files | Reprocesses all historical files | Persistent state + controlled replay |
| Retrying poison files endlessly | Starvation, scheduler congestion | Quarantine and limits |
| Catching errors and returning success before persisting recovery | Ack/commit despite business failure | Durable recovery and proper error semantics |
| Treating global error channel as a DLQ | Error messages lost on restart | Durable queues/stores and broker policies |
| Thinking `maxMessagesPerPoll` is retry count | Wrong throughput and attempt expectations | Separate receive limits from retries |
| Sending `ErrorMessage` back to business channels | `Throwable` breaks payload schema | Replay business commands/messages |
| Ignoring unknown HTTP timeout outcomes | Duplicate bookings/orders | Idempotency and reconciliation |
| Assuming Kafka async callbacks go to poller errorChannel | Late producer errors missed | Adapter/callback error strategy |
| Stacking unbudgeted retries at every layer | Retry storms | One unified retry budget |
| Scheduling pollers too tightly for backend capacity | Overloads SFTP/DB/HTTP | Rate limiting, backpressure, pool sizing |
| Not testing whether the scheduler actually runs | Silent error channel goes unnoticed | Heartbeat/last poll metrics |
| Multiple error subscribers compensating simultaneously | Double side effects | Single recovery coordinator, idempotency |
| Not verifying app state after errors | Dashboards show errors while data is lost/duplicated | End-to-end validation and reconciliation |

## 23. Checklist for Pollers Sending Errors to an error-channel

### A. Identify Poller and Errors

- [ ] Identify whether the endpoint is a source poller, consumer poller, or message-driven listener.
- [ ] Know which thread/scheduler/executor runs and where exceptions can arise.
- [ ] Distinguish receive-time, handler-time, and async callback failures.
- [ ] Test both empty polls (`receive` returns null) and `receive` throwing exceptions.
- [ ] Know `maxMessagesPerPoll`, poll schedule, receive timeout, and concurrency.

### B. Configure Error Destination

- [ ] Poller has an error strategy/`error-channel` suited to your active version.
- [ ] Dedicated error channel bean exists with an active subscriber.
- [ ] Global `errorChannel` retains appropriate logging/monitoring.
- [ ] Do not assume both global and local receive the same error.
- [ ] When the `errorChannel` header is used, it is controlled by trusted sources.
- [ ] Error handler tolerates null `failedMessage`/`originalMessage` without unsafe casts.

### C. Data Safety and Retries

- [ ] Business key/correlation ID and safe source reference exist.
- [ ] File/SFTP filters, moves, deletes, quarantine, and replay are designed.
- [ ] JDBC polling uses transactions/claims/idempotency per business state.
- [ ] In-memory `QueueChannel` sources are not mistaken for durable queues.
- [ ] HTTP retries use idempotency/lookups when outcomes are unknown.
- [ ] JMS/AMQP acks/tx and Kafka callbacks/offsets are handled per container.
- [ ] Retries filter by error category, with limits, backoff, and final disposition.
- [ ] Recovery tasks are durably persisted when needed across restarts.

### D. Testing and Operations

- [ ] Test that synchronous `DirectChannel` does not publish errors by default.
- [ ] Test polling sources and consumers publishing to the chosen error channel.
- [ ] Test missing `Message` context, pre-receive errors, and handler failures.
- [ ] Test failing error handlers, subscriberless channels, and overload.
- [ ] Test restarts, replays, duplicates, and poison messages.
- [ ] Metrics exist for polling activity, last success, error rates, backlog, and exhausted retries.
- [ ] Owners and runbooks exist for quarantine/reconciliation/manual recovery.
- [ ] Outcomes are verified on source and target resources, not merely via error logs.

## 24. Self-Check Questions

**Question 1. Why does a poller need a dedicated error strategy instead of just throwing exceptions to the caller?**

**Answer:** Pollers are typically scheduler-triggered with no business caller waiting on the same call stack. An error publishing strategy converts `Throwable`s into `ErrorMessage`s and routes them to an error channel for handling and observation.

**Question 2. Does ErrorMessage have the failing file's data as its payload?**

**Answer:** No. `ErrorMessage` has a `Throwable` payload. The file or business data may reside in `failedMessage`/`originalMessage` if context was provided, or in a durable source reference.

**Question 3. An SFTP poller fails connecting before creating a Message. Can you call getFailedMessage().getPayload()?**

**Answer:** You should not. The `Throwable` might not be a `MessagingException`, or `failedMessage` may be null. Handlers must check types and fall back to source/endpoint metadata.

**Question 4. When setting .errorChannel("filePollErrors") on a poller, will global errorChannel always get a copy too?**

**Answer:** No. Channel selection depends on the error publisher/routing. Once `filePollErrors` is selected, do not assume the global channel also receives a copy; test against your actual configuration.

**Question 5. Does adding @ServiceActivator(inputChannel="errorChannel") route every synchronous exception into that channel?**

**Answer:** No. Synchronous `DirectChannel` flows normally throw back to the sender. Subscribers only receive `ErrorMessage`s published to that channel.

**Question 6. Does maxMessagesPerPoll(5) mean retry up to five times?**

**Answer:** No. It bounds how many messages the poller pulls per trigger per policy. Retries have separate configuration for attempts, eligible errors, and backoff.

**Question 7. Why does a CSV file logged on the error channel fail to reappear on the next poll?**

**Answer:** File filters/metadata may have already marked it accepted. `ErrorMessage` does not reset filters. You need durable state and controlled quarantine/replay mechanics.

**Question 8. JDBC polling reads a row, HTTP POST succeeds, yet DB update fails. Is retrying the row immediately safe?**

**Answer:** Not necessarily. It can cause duplicate POSTs. Use business keys, idempotency keys, target HTTP status checks, or reconciliation before resending.

**Question 9. Does a message pulled from QueueChannel automatically return to the queue when the handler throws?**

**Answer:** Never assume so. Especially in-memory `QueueChannel`s do not guarantee rollback/durable replay. Check channel implementation, transactions, and state recovery.

**Question 10. Does a message-driven Kafka inbound adapter use a File poller's errorChannel to manage offsets?**

**Answer:** No. The listener container/Kafka error handler manages retries, offsets, and DLT. A poller-specific error channel does not replace those policies.

**Question 11. If retry advice catches and recovers an exception, will the poller still always publish an ErrorMessage?**

**Answer:** No. If the exception is not propagated, the poller may see no failure to publish. A recovery callback may emit an error itself by design, so test to avoid double-publishing.

**Question 12. The error handler logs and returns normally; can we conclude the file imported successfully?**

**Answer:** No. Logging only observes the error; it does not prove DB/HTTP completed or that the file entered retry/quarantine. Verify business state at source and target.

**Question 13. Why can logging the entire failedMessage be dangerous?**

**Answer:** Payloads/headers may contain PII, financial data, bearer tokens, secrets, sensitive paths, or large files. Log safe metadata and correlation IDs instead.

**Question 14. When should you use a dedicated filePollErrors channel instead of only global errorChannel?**

**Answer:** When file processing has different retry, quarantine, ownership, or SLA requirements from SFTP/JDBC/HTTP, or needs independent error testing and monitoring.

**Question 15. How can a system still be failing when the poller emits zero ErrorMessages?**

**Answer:** The poller may have stopped running, received no data, hit scheduler starvation, or the source stopped sending files. With no exception there is no `ErrorMessage`; monitor heartbeats, last successful poll, and backlog metrics.

**Question 16. One bad file keeps failing and blocking good files. What should you do?**

**Answer:** Mark it as a poison file, route to dedicated quarantine/recovery, cap retries, and keep ingesting remaining files. Never disable all filters or retry the same file endlessly.

**Question 17. What should you do if the error handler itself throws exceptions?**

**Answer:** Separate lightweight observers from durable recovery workers, add fallbacks/alerts for error-of-error, avoid blocking schedulers, and test channels without subscribers.

**Question 18. A source poller reads a file, then hands off to an ExecutorChannel for async HTTP. Are HTTP failures guaranteed to return to filePollErrors?**

**Answer:** No. Errors after a thread boundary may belong to the executor/HTTP adapter's error strategy. Verify the actual error path with integration tests.

**Question 19. Can global errorChannel be treated as a durable dead-letter queue?**

**Answer:** No. It is a Spring `MessageChannel`; durability, post-restart retries, acknowledgments, and DLQ/DLT require dedicated configuration in the right workflow/broker.

**Question 20. What proves poller error handling works properly?**

**Answer:** Tests showing exceptions reach the right `ErrorMessage` destination, handlers read context safely, source and target systems hold accurate states, retries/quarantine work where needed, and unresolved failures have owners.

## 25. Conclusion and References

### 25.1. Key Takeaways

In **Spring Integration**, pollers actively pull `Message`s from a **MessageSource or PollableChannel**. When a polling task throws within a configured error handler's scope, mechanisms like **MessagePublishingErrorHandler** can build an **ErrorMessage** and send it to an **error-channel**—either the global **errorChannel** by default or a poller-specific channel.

**Configuring the error destination is the first step, not the last.** Clearly verify:

- **Exception capture:** did it occur inside the scheduler/poller or after crossing to another thread?
- **Error routing:** global vs. dedicated error-channel; do subscribers and publishers exist?
- **Error context:** are `Throwable`, `failedMessage`, `originalMessage`, business key, and stage present?
- **Data source:** did file filters, SFTP remote metadata, JDBC row states, or `QueueChannel` retain the message?
- **Side effects:** did the DB commit, HTTP process, or broker accept the message?
- **Recovery:** retry, backoff, idempotency, quarantine, compensation, or manual reconciliation;
- **Verification:** did the message reach its intended terminal state, or is there merely an error log line?

### 25.2. Summary Diagram

~~~mermaid
flowchart LR
    SRC["File / SFTP / JDBC / QueueChannel"] --> P["Poller"]
    P --> H["Message processing"]
    P -. "Receive error" .-> E["Error publisher"]
    H -. "Error in poller scope" .-> E
    E --> EC["errorChannel or dedicated channel"]
    EC --> O["Observe + classify"]
    O --> Q{"Action needed?"}
    Q -->|"Transient"| R["Durable retry + backoff"]
    Q -->|"Permanent data"| C["Quarantine"]
    Q -->|"Unknown"| U["Reconciliation"]
    Q -->|"Fatal/config"| M["Alert / manual intervention"]
    R --> V["Verify source & target"]
    C --> V
    U --> V
    M --> V
~~~

### 25.3. Official Documentation to Cross-Reference

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `errorChannel`, `ErrorMessage`, `MessagePublishingErrorHandler`, and sync/async boundaries.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): polling endpoints, `PollerSpec`, poll schedules, task executors, and advice.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): configuring `IntegrationFlow`, channels, and polling endpoints.
- [Spring Integration Reference — File Support](https://docs.spring.io/spring-integration/reference/file.html): file sources, filters, and file handling.
- [Spring Integration Reference — SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): polling/remote synchronization and file transfers.
- [Spring Framework — ErrorMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): `Throwable` payload, `originalMessage`, and constructors.

Java/JSON/SQL snippets and Mermaid diagrams in this lesson are **educational examples**. Verify your project's Spring Integration, Spring Boot, Java, adapter, and dependency versions, and run integration tests for schedulers, thread boundaries, retries, transactions, and message states before production deployment.
