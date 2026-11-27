# Default errorChannel in Spring Integration

## 1. Why Is errorChannel Needed?

**Spring Integration** organizes system integration using **Message**, **MessageChannel**, and endpoints such as inbound/outbound adapters, gateways, transformers, filters, routers, and service activators. A message has a **payload** and **headers**; channels transfer messages between components. Each component can fail due to malformed data, locked files, unresponsive HTTP services, disconnected brokers, failed transactions, or business processing errors.

In a typical synchronous function call, an exception can be thrown back to the caller. However, when processing messages with a **poller** or across **asynchronous** boundaries, the original caller is no longer on the same call stack to receive the exception. Therefore, Spring Integration provides a mechanism to **convert errors into messages** and route them to an error channel.

The **default errorChannel** is the name of the global error channel that Spring Integration provides in standard integration configurations. When an error-handling mechanism is capable of **publishing an ErrorMessage** without specifying a dedicated error channel, the channel named **errorChannel** is the default destination. In the framework's standard configuration, this channel is typically a **PublishSubscribeChannel**, with a **LoggingHandler** registered to log errors. The actual configuration may differ if the application defines or replaces the bean itself, adds subscribers, or integrates with external components.

The core point is that **not every exception in every flow automatically goes to errorChannel**. You need to clearly distinguish:

- **Exceptions thrown directly** in a synchronous flow;
- **Exceptions caught and converted into an ErrorMessage** at a poller, listener, or a component with an error publishing policy;
- **Errors in external resources** managed by the file system, SFTP server, HTTP client/server, JMS/AMQP/Kafka broker, or database itself;
- **Decisions to retry, roll back, reject, dead-letter, or return a response** made by the adapter/transaction/container and application policy.

The channel name `errorChannel` **does not make it a "global retry processor" or a dead-letter queue**. It is first and foremost a **transport path for error information in message form**.

### Learning Objectives

After this lesson, learners can:

1. Explain how the default `errorChannel` is used in Spring Integration.
2. Distinguish synchronous exceptions from asynchronous or poller-generated `ErrorMessage` instances.
3. Read the payload of an `ErrorMessage` and trace the message that caused the error.
4. Register a handler for `errorChannel` and decide when a dedicated error channel is needed.
5. Integrate error flows with File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC without misunderstanding commit/retry mechanics.
6. Design options for **logging, alerting, bounded retry, quarantine, dead-lettering, compensation**, and operational observability.
7. Write tests to verify error paths, avoiding lost messages and swallowed errors.

## 2. Placing errorChannel in the Message Architecture

An integration flow can be described as:

~~~mermaid
flowchart LR
    SRC["External system: file / SFTP / HTTP / broker"]
    IN["Inbound adapter or gateway"]
    CH["MessageChannel"]
    HANDLER["Transformer / Handler / Outbound adapter"]
    TARGET["Target system"]
    PUB["Component catching error and publishing ErrorMessage"]
    ERR["errorChannel (global)"]
    LOG["Default LoggingHandler"]
    OPS["Custom error handler / alert / recovery"]
    SRC --> IN --> CH --> HANDLER --> TARGET
    IN -. "Error in supported poller/listener" .-> PUB
    HANDLER -. "Error caught by error strategy" .-> PUB
    PUB --> ERR
    ERR --> LOG
    ERR --> OPS
~~~

The diagram is a **logical model** and does not imply that every adapter automatically emits an `ErrorMessage` or always continues running after an exception. Actual behavior depends on the endpoint, invocation style, executor configuration, transactions, advice, and the specific adapter.

### 2.1. Related Components

| Component | Function | Relation to Errors |
|---|---|---|
| Message | Payload and headers of a unit of work | Helps trace data and correlation ID |
| MessageChannel | Where messages are sent and received | Can be DirectChannel, QueueChannel, ExecutorChannel, PublishSubscribeChannel... |
| errorChannel | Global error channel name | Default destination for published errors |
| ErrorMessage | A Message with a Throwable payload | Carries the exception and optionally the original message |
| MessagingException | Exception in the messaging system | Often has failedMessage to identify the failed message |
| ErrorMessagePublisher / MessagePublishingErrorHandler | Component that publishes ErrorMessage when used | Can resolve errorChannel from header or fallback |
| LoggingHandler | Endpoint that logs error details | Can be the default subscriber of errorChannel |
| Poller / task executor / listener | Starts processing outside the synchronous caller | Often requires its own error handling strategy |

### 2.2. Default errorChannel Is a Channel, Not an Exception Class

The name **errorChannel** is typically identified by a bean/channel in the Spring context. Framework components recognize this standard name and can route errors to it. Do not confuse:

- **errorChannel**: a message channel;
- **ErrorMessage**: an object wrapping an exception;
- **MessagingException**: an exception type that may carry a failed message;
- **error-channel configuration**: how to specify a dedicated channel on a gateway, poller, or endpoint;
- **dead-letter queue (DLQ)**: a queue storing unprocessable messages, requiring its own mechanism and policy.

## 3. What Does an ErrorMessage Contain?

In Spring Framework, **ErrorMessage** is a message whose **payload is a Throwable**. The content may be a `MessagingException`, `MessageHandlingException`, `MessageDeliveryException`, or another exception, depending on where the error was caught and the message was created.

For `MessagingException` instances, the **failedMessage** property often contains the message associated with the error. An `ErrorMessage` may also hold **originalMessage** if the component creating the error provides it. However, you should not assume every error has a complete `failedMessage` or `originalMessage`: an exception raised before creating a Spring Message, or a component that only forwards a `Throwable`, may lack that context.

### 3.1. Logical Content Example

~~~text
ErrorMessage
  payload:
    MessageHandlingException
      message: "Failed to handle message"
      failedMessage:
        payload: order-274.csv
        headers:
          id: ...
          correlationId: import-2026-001
          file_name: order-274.csv
  originalMessage: ...  (may or may not be present)
  headers:
    id: ...
    timestamp: ...
~~~

Note: this is a structural illustration, **not an exact dump for every version or adapter**. Do not assume that every source header is preserved across message transformations, bridges, or gateways.

### 3.2. Safely Reading the Exception and failedMessage

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class GlobalIntegrationErrorLogger {

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();
        System.err.println("Integration error: " + failure.getClass().getSimpleName());

        if (failure instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            if (failed != null) {
                Object correlation = failed.getHeaders().get("correlationId");
                System.err.println("Correlation: " + correlation);
                // Log only safe metadata; avoid printing sensitive payloads.
            }
        }
    }
}
~~~

The example uses Java with pattern matching for `instanceof`; if the project uses an older Java version, you can cast using the traditional syntax. In production, use SLF4J/structured logging instead of `System.err`, mask personal data, and avoid logging entire payloads, tokens, passwords, or keys.

**Important:** Because the default `errorChannel` typically uses a publish-subscribe mechanism, multiple subscribers can receive the same `ErrorMessage`. Registering a handler does not automatically remove the existing logging subscriber; check the actual configuration if you want to avoid duplicate logging or repeated side effects.

## 4. Synchronous vs. Asynchronous: The Difference That Determines the Error Path

### 4.1. Synchronous Flow with DirectChannel

~~~text
caller --> DirectChannel --> serviceActivator --> outboundAdapter
                         |
                         +-- throw exception --> caller / upstream
~~~

**DirectChannel** typically invokes the subscriber in the sender's thread. If a handler throws an exception and there is no special advice/catch layer, the exception usually **propagates back to the sender**. It does not automatically become an `ErrorMessage` just because the Spring context has an `errorChannel` bean.

For example, consider an HTTP inbound gateway processing synchronously: the caller is waiting for an HTTP response. An exception may lead to an error response according to the gateway/web layer mechanism or an error flow configuration. If you rely solely on a subscriber of `errorChannel`, the application may fail to return the proper HTTP status/body.

### 4.2. Poller: No Synchronous Caller to Return the Exception To

Inbound File/SFTP/JDBC pollers usually run on a scheduler trigger. If an error occurs while the poller is receiving or processing a message, the error handler configured for the poller can **publish an ErrorMessage** to the selected channel. When no dedicated channel is configured and the global fallback is used, that destination is typically **errorChannel**.

~~~text
Scheduler --> Poller --> MessageChannel --> Handler
                 |                               |
                 +------ exception caught -------+
                              |
                       ErrorMessagePublisher
                              |
                         errorChannel
~~~

Each poller/adapter type has different message acquisition, acknowledgment, and transaction policies. Sending an `ErrorMessage` **does not by itself prove** that the input has been retried or has not already been marked as processed.

### 4.3. Other Asynchronous Boundaries

An `ExecutorChannel`, a `QueueChannel` with a consumer poller, a message-driven inbound adapter, or a task executor can prevent an exception from having a direct throw path back to the original caller. However, **whether it is converted into an ErrorMessage still depends on the actual error handler at the processing point**. A message sent to a `QueueChannel` with no consumer does not automatically generate an error; an executor not configured with an error publisher may only report errors through the executor's own mechanism.

### 4.4. Reference Behavior Table

| Flow | When Handler Fails | What to Configure/Check |
|---|---|---|
| Synchronous DirectChannel | Usually thrown back to sender | Advice, gateway response, exception mapping |
| Polling inbound adapter | Poller error strategy may publish ErrorMessage | Poller's errorChannel, retry, file/DB acknowledgment |
| QueueChannel with consumer poller | Consumer/poller handles error outside original sender | Poller and error handler at the consumer |
| ExecutorChannel | Error occurs on another thread | Error publishing mechanism and executor behavior |
| HTTP inbound gateway | Caller awaits response | HTTP error mapping, status, timeouts, error flow |
| JMS/AMQP/Kafka message-driven | Listener/container participates in error handling | Ack, transaction, redelivery, broker/container error handler |

**Testing rule:** Do not deduce the error path solely from the channel type. Write integration tests that intentionally throw an exception at the processing point and verify both `errorChannel` and the state of the message source/response.

## 5. Global errorChannel and Scoped Error Channels

### 5.1. Error Channel Precedence

Some components using **MessagePublishingErrorHandler** can look up the error channel via the **errorChannel header** of the failed message, then use the fallback/global channel if no suitable channel is found. In other endpoints, users directly configure a dedicated `error-channel`. The exact rules and resolution points **depend on the component**; not every `Message<?>` is automatically routed by header.

Therefore, there are three practical patterns:

1. **Global:** route `ErrorMessage` to `errorChannel`, where shared logging and handlers live;
2. **Per-flow/per-endpoint:** a poller or gateway specifies `fileErrors`, `sftpErrors`, `apiErrors`...;
3. **Per-message:** use the `errorChannel` header when the endpoint/error handler supports header-based resolution.

### 5.2. When to Use Global?

Global `errorChannel` is suitable for:

- Recording errors that have no specific channel;
- Alerting on certain errors not handled in a dedicated flow;
- Tracking overall error rates, correlation/tracing, and classification;
- Providing a final handling step for errors that have already been published.

You should not push every recovery action, retry, alert email, and DLQ send into an unclassified global handler. An SFTP file error needs file rollback, an HTTP 503 needs bounded retry, and schema-invalid data needs quarantine—they have different logic.

### 5.3. When to Use a Dedicated Error Channel?

A flow should use a dedicated channel when it has **distinct SLA, reliability, retry, transaction, or business context requirements**. For example:

| Channel | Error Source | Suggested Policy |
|---|---|---|
| fileErrors | File reading/parsing poller | Quarantine bad file, record reason, avoid repeated reads |
| sftpErrors | SFTP session/transfer | Distinguish network errors from invalid files; backoff |
| httpClientErrors | Outbound HTTP | Classify HTTP status/timeout; bounded retry |
| brokerErrors | JMS/AMQP/Kafka | Coordinate with container, ack/tx, redelivery/DLQ |
| databaseErrors | JDBC query/write | Check transaction, idempotency, and retry constraints |

The names above are examples only. A dedicated channel can be a `DirectChannel`, `PublishSubscribeChannel`, or another channel type depending on topology; the choice of channel type affects concurrency, backpressure, and who receives an `ErrorMessage`.

## 6. Configuring Error Consumption from the Default errorChannel

### 6.1. Minimal Setup: Adding a Service Activator

If Spring Integration is already enabled and using the **default errorChannel**, you can register a subscriber with an annotation without declaring a new channel bean yourself:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationErrorObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IntegrationErrorObserver.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        Throwable cause = error.getPayload();
        String failedMessageId = "unknown";

        if (cause instanceof MessagingException exception
                && exception.getFailedMessage() != null) {
            failedMessageId = exception.getFailedMessage()
                    .getHeaders().getId().toString();
        }

        log.error("Spring Integration failure, failedMessageId={}, type={}",
                failedMessageId, cause.getClass().getSimpleName(), cause);
    }
}
~~~

The class above assumes the application has Spring Integration, SLF4J, component scanning, and the corresponding integration configuration. You can add **@EnableIntegration** on a configuration class if the project has not enabled the annotation infrastructure; with Spring Boot, check the auto-configuration in use. **Do not declare a bean with the duplicate name `errorChannel` just to listen for errors**: declaring a duplicate name can alter the default mechanism and built-in logging subscriber.

The example only shows a **handler receiving ErrorMessages that have been published to the global channel**. It does not catch every synchronous exception in a `DirectChannel`. Nor does it create retries or guarantee that the source system will resend the data.

### 6.2. Why You Should Not Throw Infinite Exceptions from an Error Handler

When an error handler itself fails, the error may be logged again, thrown to the invoking mechanism, or trigger unexpected retries depending on the channel/error strategy. If a handler sending a notification or writing to a DB also fails, you must not create an infinite loop sending errors back to `errorChannel` itself.

A practical error handler should:

- Have small, deterministic logic; avoid blocking threads with slow network operations;
- Distinguish source errors from errors of the error handler itself;
- Not log full sensitive payloads;
- Limit notification attempts or route errors to a durable processing queue when needed;
- Be tested when the log server, DB, or notification provider is unavailable.

### 6.3. Understanding PublishSubscribeChannel Subscribers

In the typical default configuration, global `errorChannel` uses a **PublishSubscribeChannel**, which can deliver one `ErrorMessage` to multiple subscribers:

~~~text
                  +--> LoggingHandler
ErrorMessage --> errorChannel
                  +--> ErrorObserver
                  +--> Metrics/alerting handler
~~~

Therefore, adding an extra logging handler can cause the same error to be logged **twice**. If you want a single recovery pipeline, you can configure a dedicated channel for the flow or design a classifying subscriber. Do not confuse it with `QueueChannel`, where a single message is pulled by one consumer in queue fashion.

### 6.4. Is It Safe to Redefine the Global errorChannel?

The framework allows customizing the channel/error handler configuration in certain contexts, but **how to replace the `errorChannel` bean and default `LoggingHandler` depends on the configuration and Spring Integration version**. Before declaring a bean with the same name, check whether the application uses auto-configuration or explicit integration configuration, and the impact on endpoints using the fallback. For an introductory exercise, prefer **subscribing to the existing channel** rather than replacing it.

## 7. Example: File Polling and Error Routing

Inbound File adapters typically use a poller to scan for new files. Unlike a synchronous HTTP gateway, there is no caller waiting for an exception. An illustrative example using **Spring Integration Java DSL**:

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
public class FileImportFlow {

    @Bean
    public MessageChannel fileErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow inboundFileFlow() {
        return IntegrationFlow
                .from(
                        Files.inboundAdapter(new File("data/inbox"))
                                .autoCreateDirectory(true),
                        spec -> spec.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(3))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("fileErrors")))
                .handle(message -> {
                    File file = (File) message.getPayload();
                    throw new IllegalStateException(
                            "Demo failure while importing: " + file.getName());
                })
                .get();
    }

    @ServiceActivator(inputChannel = "fileErrors")
    public void onFileFailure(ErrorMessage message) {
        System.err.println("File poller failure: "
                + message.getPayload().getClass().getSimpleName());
    }
}
~~~

**Compatibility note:** the example depicts a common Java DSL configuration; overload names/spec types and poller options can vary across Spring Integration versions. When implementing, verify the Java DSL against the exact dependency version in your project. The code above **intentionally throws an error** to illustrate the flow, not as a production file handler.

In the example:

1. The File inbound adapter picks up a file when the poller runs;
2. The message goes to the processing handler;
3. The handler throws an exception;
4. **The poller's error handler**, if configured as above and applicable to that error, publishes an `ErrorMessage` to `fileErrors`;
5. The Service Activator on `fileErrors` receives the error details.

If you omit the dedicated channel configuration on the poller, the default mechanism may send errors to the global **errorChannel** when the error publisher uses the global fallback. This must be tested on your specific flow.

**Source file warning:** publishing an `ErrorMessage` does not automatically move the file into a quarantine directory, does not guarantee the file will be re-read, and does not automatically roll back the marker indicating the file was received. These depend on `FileListFilter`, `AcceptOnceFileListFilter`, how files are moved/deleted, idempotency, and the post-error file handling strategy.

### 7.1. Why Should You Not Send an Error Message Containing the Entire File?

An import file may contain personal data or millions of rows. If the error handler logs the entire payload, logs will bloat and may leak data. Instead, capture the **file name, checksum, attempt count, correlation ID, exception type**, and a safe location, then move the file to quarantine under an access-controlled workflow.

### 7.2. Designing Final File Outcomes

| Processing Result | Suggested Action |
|---|---|
| Parse succeeded | Move file to processed or record success state |
| Transient DB/HTTP error | Retry with backoff and limit, using idempotency |
| Unfixable schema error in file | Quarantine, record reason, and request manual intervention |
| File locked/still being written | Wait until file is stable, avoid ingesting incomplete files |
| Permission/path error | Alert operations, do not retry aggressively |

An error can occur **before a Spring Message even exists** (for example, creating a directory or accessing the file system). In that case `failedMessage` may be null or have different context. Pay attention to poller/adapter logs and do not assume `ErrorMessage` always contains a `File` payload.

## 8. Choosing errorChannel by Endpoint or Message

### 8.1. Global Channel vs. Dedicated Channels

If all errors fall into the global `errorChannel`, the handler must classify by flow, source, and exception. In a multi-adapter system, a specific per-endpoint policy is usually easier to maintain:

~~~mermaid
flowchart TD
    FILE["File poller"] --> F["fileErrors"]
    SFTP["SFTP poller"] --> S["sftpErrors"]
    HTTP["HTTP outbound flow"] --> H["httpErrors / advice"]
    BROKER["JMS / AMQP / Kafka listener"] --> B["Broker/container error policy"]
    F --> Q["Quarantine or bounded retry"]
    S --> A["Reconnect/backoff and alert"]
    H --> R["HTTP retry/compensation"]
    B --> D["Broker redelivery / DLQ / DLT if configured"]
    OTHER["Error publisher without dedicated channel"] --> G["global errorChannel"]
    G --> L["Logging / monitoring / triage"]
~~~

This is an illustrative architecture and does not assert that HTTP flows or brokers automatically have channels named `httpErrors`/`brokerErrors`. Those channels must be configured at the appropriate point or via dedicated advice/flows.

### 8.2. The errorChannel Header

Spring Messaging defines the standard header **MessageHeaders.ERROR_CHANNEL**, typically having the header name `errorChannel`. When an error publisher mechanism supports resolving this header, the message can specify the error return channel. Example showing how to attach the header:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder.withPayload("order-274")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "orderErrors")
        .setHeader("correlationId", "import-2026-001")
        .build();
~~~

**Attaching the header does not create an error handler.** There must be an appropriate `orderErrors` channel and an endpoint/error publishing strategy that actually uses that header. A synchronous `DirectChannel` can still throw the exception back to the sender without sending to `orderErrors`. Nor should you allow untrusted callers to arbitrarily specify internal error channels, as that could leak data or misroute messages.

### 8.3. Original Message and Correlation

For pipelines transforming payloads across multiple steps, maintain a **correlation ID** end-to-end and record the adapter/flow name at the point of failure. Do not assume every error has the `originalMessage` of the initial message; sometimes only the `failedMessage` immediately before the failing endpoint is available.

A minimal error event:

~~~json
{
  "flow": "sftp-order-import",
  "adapter": "sftp-inbound",
  "correlationId": "import-2026-001",
  "messageId": "8c8b...example",
  "exceptionType": "MessageHandlingException",
  "stage": "parse-csv",
  "attempt": 2,
  "outcome": "quarantined"
}
~~~

Values are illustrative only; do not take an exception message containing passwords, secret URLs, or customer data and log it verbatim without filtering.

## 9. Where Do Errors Come from in Each Adapter Type?

| Adapter / Gateway | Common Errors | What to Check Before errorChannel |
|---|---|---|
| File inbound | I/O, file permissions, data parsing, unstable file | Poller, file filter, move/delete policy |
| SFTP inbound/outbound | Timeout, authentication, permission, network, file rename | Session factory/caching, poller, remote synchronization |
| HTTP inbound gateway | Request validation, payload conversion, handler exception | HTTP status/response mapping, timeout |
| HTTP outbound gateway/adapter | DNS, connection timeout, HTTP 4xx/5xx, response conversion | Client error handler, sync exception/advice |
| JMS inbound/outbound | Broker down, conversion, listener exception, transaction | Listener container, acknowledgment, redelivery/DLQ |
| AMQP/RabbitMQ | Publish failure, consumer exception, reject/nack | Broker ack, retry/requeue, DLX/DLQ |
| Kafka | Deserialize, poll, listener error, offset/commit | Listener container, CommonErrorHandler/recovery strategy |
| JDBC inbound/outbound | SQL syntax, constraint, deadlock, timeout | Transaction boundary, query/update semantics |

**No single default errorChannel strategy can handle every protocol's errors properly.** File needs to know whether a file will be re-read; HTTP needs to return an appropriate status; JMS/Kafka must consider acknowledgment and transactions; JDBC must handle rollback. The `ErrorMessage` path is only one part of the picture.

## 10. File and SFTP: From ErrorMessage to Safe Reprocessing

### 10.1. File Inbound

With `FileReadingMessageSource`, the poller fetches files according to a filter. A file can be marked as accepted before the business handler finishes, depending on the filter and metadata store. If the handler fails without moving the file or updating state, the file may:

- Not be re-read because the filter already marked it;
- Be re-read after a restart and cause business duplicates;
- Be read in parallel by another pipeline;
- Be deleted/moved by a step not tied to the business commit.

The solution is not merely listening to `errorChannel`; you must design **idempotent processing**, file locking/ready checks, quarantine, state tracking, and controlled replay. If using a persistent filter, understand when metadata is updated and how to reset it.

### 10.2. SFTP Inbound

SFTP inbound can sync files from a remote server to local storage or process them directly depending on configuration. Errors can occur when connecting, listing the remote directory, downloading files, renaming, or parsing content. Classify them:

- **Transient:** connection/timeout — retry with backoff, limit concurrency, and alert if prolonged;
- **Permanent:** wrong password/access permissions — requires configuration intervention, do not hammer with retries;
- **Data failure:** malformed file — quarantine the file and notify the data partner;
- **Partial transfer:** incomplete download — do not pass incomplete files to downstream processing.

**Remote delete/rename must be tied to actual success policies**, rather than assuming publishing an `ErrorMessage` means the failure was handled satisfactorily. Control concurrency when multiple pollers access the same remote file.

### 10.3. An Error Channel for SFTP Is Not Enough to Guarantee "At-Least-Once"

To achieve at-least-once processing, you must design how inputs are re-acquired, bounded retries, proper acknowledgment/deletion, durable state, and duplicate handling. Achieving business-level "exactly-once" effects in a distributed environment usually requires an idempotency key and transactions/reconciliation; it cannot be inferred from an `ErrorMessage`.

## 11. HTTP Inbound/Outbound: errorChannel Does Not Replace the HTTP Response

### 11.1. HTTP Inbound Gateway

An HTTP inbound gateway typically receives a request from a client and must return an **HTTP response** within the timeout window. For example, `POST /orders` passing through a transformer and a service activator:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant G as HTTP inbound gateway
    participant F as Integration flow
    participant E as Error handling / mapping
    C->>G: POST /orders
    G->>F: Message request
    F-->>E: Validation/business failure
    E-->>G: Mapped error result
    G-->>C: HTTP 4xx/5xx + appropriate response
~~~

For synchronous requests, exceptions can propagate back to the gateway. The application must decide the **status code, response body, timeout, and correlation ID**; you cannot simply add a Service Activator on the global `errorChannel` and assume the client will automatically receive a business-appropriate HTTP 400 or 503.

Classification examples:

| Error | Potentially Appropriate HTTP Response | Things to Note |
|---|---|---|
| Request fails schema/missing field | 400 Bad Request | Do not retry invalid data |
| Unauthenticated | 401 Unauthorized | Distinguish from permission denied |
| Authenticated but lacks permission | 403 Forbidden | Do not leak information about other resources |
| Business state conflict | 409 Conflict | Use only when semantically accurate |
| Downstream temporarily unavailable | 503 Service Unavailable | Consider Retry-After when appropriate |
| Unexpected error | 500 Internal Server Error | Log server-side, do not expose stack trace |

These are mapping suggestions, not mandatory rules; the application must adhere to its specific HTTP contract.

### 11.2. HTTP Outbound Gateway/Adapter

An HTTP outbound endpoint can fail when DNS/network is unavailable, the connection resets, the response is invalid, or the target returns 4xx/5xx. Depending on the HTTP client and error handler, those statuses may be converted into exceptions or response messages; **do not assume every 4xx/5xx is published to errorChannel**.

Strategies should distinguish:

- **4xx due to bad request:** usually do not retry the exact same request; route to data correction or business workflow;
- **429/503:** can retry with backoff and honor `Retry-After` if provided;
- **Timeout:** you may not know whether the target server already processed the request; retrying writes requires an idempotency key;
- **5xx:** assess transience and the target's fault tolerance;
- **Conversion exception:** inspect the payload/headers contract and content type.

### 11.3. Does the Error Belong to the Gateway or the Flow?

In a synchronous flow, you can handle errors using advice, error mapping, or by returning a response representing the error. In an asynchronous flow (such as HTTP accepting a request and queuing a job), the gateway may return `202 Accepted` first; errors in the worker will take a different error path, no longer directly connected to the original HTTP caller. In that case, you need **job status**, callbacks, or error notification events for the client—do not try to return an HTTP response from a thread that has already finished.

## 12. JMS and AMQP: errorChannel Does Not Replace Broker Acknowledgment

### 12.1. Two Types of Lifecycle

In broker messaging, distinguish between:

1. Whether the **Spring Integration flow** processed the message successfully;
2. Whether the **broker acknowledged/committed/rejected/redelivered** the source message.

An `ErrorMessage` successfully sent to `errorChannel` **does not by itself determine the ack/rollback outcome**. The outcome depends on the listener container, transaction, acknowledgment mode, and the adapter's error handling/retry configuration.

### 12.2. JMS Inbound

In JMS, session transactions or acknowledgment modes determine whether the broker redelivers a message when the listener fails. If an exception is caught and merely logged in an endpoint so that the transaction sees "success", the broker may not redeliver as expected. Conversely, throwing an exception can trigger rollback/redelivery, leading to an infinite loop if the message is a poison message without a processing limit.

Design points:

- How far the transaction boundary spans around message receipt and business processing;
- Whether errors are rethrown so the container knows processing failed;
- Broker redelivery policy, delay, attempt limit, and DLQ;
- Idempotency when redelivering the same business message;
- Distinguishing permanent payload errors from transient infrastructure errors;
- Marking as processed only when the business action truly succeeds.

### 12.3. AMQP/RabbitMQ

With AMQP, consumers can ack, reject/nack, requeue, or configure a dead-letter exchange (DLX) and dead-letter queue (DLQ). Spring Integration AMQP adapters work alongside RabbitMQ listeners/containers; retry and recover/reject behavior must align with that configuration.

| Scenario | Handling Approach | Risk to Avoid |
|---|---|---|
| Target DB temporarily failing | Retry with limit/backoff | Aggressive redelivery overwhelming the system |
| Unparseable payload | Reject/quarantine/DLQ per policy | Poison message looping forever |
| Downstream wrote DB before ack | Idempotency/dedupe on redelivery | Duplicate writes |
| Wrong broker credentials | Alert/circuit/fix configuration | Infinite retry that cannot resolve the issue |
| Broker offline | Reconnect and monitor | Losing unprocessed messages |

An `errorChannel` subscriber handler can assist with observability or recovery, but **does not replace DLX configuration, acknowledgment, or broker retry**.

### 12.4. When to Use errorChannel in a Broker Flow?

If the adapter/container publishes an `ErrorMessage` per configuration, a subscriber can log the exception and context. However, you must verify **whether sending the ErrorMessage counts as having handled the exception** as far as the listener container is concerned. Integration tests should simultaneously verify:

- Does `errorChannel` or the custom channel receive the error?
- How does broker ack/nack/rollback/commit behave?
- Is the message redelivered, and how many times?
- After exceeding the retry limit, does it go to the DLQ properly?
- Are duplicate side effects avoided?

Do not conclude "at-least-once" or "exactly-once" solely from a channel name.

## 13. Kafka: errorChannel and Kafka Container Error Mechanisms

Kafka adds an important dimension: **offset**. Consumers poll records, the application processes them, and then offsets are committed based on ack/transaction/configuration. An `ErrorMessage` does not automatically rewind offsets or send a record to a dead-letter topic.

### 13.1. Where Errors Can Occur

| Stage | Example Error | Commonly Involved Tools/Config |
|---|---|---|
| Deserialization | Bytes cannot be converted to object | Deserializer/error-handling deserializer, container |
| Poll/consume | Broker, authentication, rebalance | Kafka consumer/container |
| Spring Message conversion | Header, mapping, payload conversion | Adapter/converter |
| Flow handler | Validation, business exception | Error flow, retry advice |
| Outbound producer | Serialization, send failure, timeout | Producer callback/error handling, transaction |
| Offset commit | Commit failure, consumer fencing | Container/consumer configuration |

In configurations using Spring for Apache Kafka, **CommonErrorHandler**, **DefaultErrorHandler**, or recovery/publishing strategies are the specialized mechanisms for managing retries, offsets, and dead-letter topics. When Spring Integration Kafka adapters are involved, understand the **specific coupling between the adapter and the listener container**, rather than assuming the global `errorChannel` covers every failure.

### 13.2. Retrying One Record Does Not Mean Retrying the Whole Flow

Suppose record K is passed into a Spring Integration handler, and the handler throws an exception. Different possibilities exist:

- The container's error handler manages record retry by offset;
- The exception is published as an `ErrorMessage` to an error flow;
- A recovery component sends the record to a dead-letter topic;
- The offset is committed or not depending on configuration and transaction state;
- The record is processed repeatedly, producing duplicate side effects if not idempotent.

Therefore, you must test the path end-to-end. For order data, use a business key to prevent duplicate updates on redelivery.

### 13.3. Dead-Letter Topic vs. errorChannel

A **DLT (dead-letter topic)** is a Kafka topic created/managed by policy to receive unprocessable records. **errorChannel** is a Spring `MessageChannel`; they are two distinct concepts. An error handler can forward error info or the record to a DLT using a specialized mechanism, but **you do not automatically get a DLT just by having errorChannel**.

### 13.4. Testing Offsets and Side Effects

When writing tests for Kafka:

1. Send a valid record and verify the handler processes it once per test setup;
2. Send a record causing a transient error, observe retries and processing count;
3. Send a poison record, verify it lands in the DLT/is quarantined per policy;
4. Verify offset/commit does not cause the record to be lost or processed infinitely;
5. Verify the `errorChannel` subscriber only receives errors the adapter/container is designed to publish;
6. Test consumer restarts and duplicate handling via idempotency keys.

## 14. JDBC, Transactions, and Database Adapter Errors

### 14.1. Polling Inbound Database

A JDBC inbound adapter can use a poller to fetch pending records. If the query succeeds but downstream processing fails, what happens to the source row? The answer depends on how SQL marks state, transactions, and post-processing update mechanics.

Example:

~~~text
pending_order table
  id=274, status=NEW

poller SELECT status=NEW
  --> handler sends HTTP to partner
  --> updates status=PROCESSED if successful
~~~

If the HTTP call succeeds but the DB update fails, the next poll may resend it. If the DB marks `PROCESSED` first and then HTTP fails, the message may be skipped in subsequent polls. **errorChannel cannot fix the ordering and atomicity across two systems**.

### 14.2. Transaction Boundary

Within a single DB transaction, an error can trigger a rollback if the exception is properly propagated to the transaction manager. However, an HTTP request or sending to another broker does not automatically participate in the same local transaction. Therefore you need:

- Outbox/inbox design or workflow state to ensure recoverability;
- Conditional retry and idempotency keys;
- Distinguishing transient deadlock/timeout errors from unrecoverable schema/constraint errors;
- Not marking "processed" before the appropriate commit decision;
- Reconciliation when an external action succeeded but the ack/DB commit did not complete.

### 14.3. Where Are SQL Exceptions Published?

In a synchronous flow, `JdbcMessageHandler`/JDBC outbound adapter can throw an exception to the caller/poller. Errors reach `errorChannel` only when an error publisher mechanism is configured and applies. Do not assume every `DataAccessException` becomes an `ErrorMessage`. If a transaction must roll back, verify whether catching the exception in a handler alters the transaction outcome.

## 15. Designing Retry, Backoff, Circuit Breaker, and Recovery

### 15.1. ErrorMessage Does Not Retry Automatically

An error handler that logs and finishes **does not automatically replay the message**. Retries must be configured at the right layer:

- Advice around a handler/outbound endpoint, such as Spring Integration's retry advice;
- Poller/scheduler or stateful file re-read logic;
- HTTP client or job retry queue;
- JMS/AMQP broker redelivery;
- Kafka container retry/error handler;
- Database transaction/retry coordination.

Do not place retries at every layer simultaneously without calculating the total count. For instance, an HTTP client retrying 3 times, handler advice retrying 3 times, and broker redelivery 5 times can produce dozens of requests to the same downstream service.

### 15.2. Classifying Transient vs. Permanent

| Category | Examples | Handling Approach |
|---|---|---|
| Transient infrastructure | Network timeout, broker temporarily unavailable | Bounded retry, exponential backoff + jitter |
| Overload/rate limit | HTTP 429, overloaded service | Respect limits, honor Retry-After when appropriate |
| Permanent data | Malformed JSON/CSV schema, unsupported enum | Quarantine or notify producer to fix data |
| Authorization/config | Expired credentials, wrong permissions | Alert and fix config; avoid aggressive retry |
| Concurrency conflict | DB deadlock or optimistic lock | Conditional retry and idempotency |
| Business rejection | Invalid order, rejected by policy | Record business state; usually do not retry verbatim |

### 15.3. Bounding Retries

A good retry policy specifies:

1. **Retry condition:** which exception classes/status codes are eligible;
2. **Max attempts:** prevent infinite loops;
3. **Backoff:** delay and jitter to avoid retry storms;
4. **Idempotency:** avoid duplicate side effects;
5. **Time budget:** total timeout and cancellation when the request is no longer meaningful;
6. **Termination:** move to quarantine/DLQ/DLT, mark failure, alert, or compensate;
7. **Evidence:** attempt number, last error, and owner.

### 15.4. Circuit Breakers and Rate Limits

When an external service continuously fails, a circuit breaker can reduce pressure by stopping new requests for a period. However, when the breaker is open, error handling still needs to record business state and schedule recovery; do not assume "sent an ErrorMessage" means the message is durably preserved.

### 15.5. Recovery Is Not Catch-and-Ignore

If an error handler catches an exception, logs a WARN, and returns success, upstream may believe processing succeeded even though data was never persisted. Establish clear policies:

- Only **swallow** when the business truly accepts dropping the message;
- Rethrow when transaction/ack needs to roll back;
- Send to a durable recovery store if intending to process later;
- Return an error result to a synchronous gateway per contract;
- Record the reason and correlation so operators can replay accurately.

## 16. Error Contracts: Treating ErrorMessage as a Business Event

### 16.1. Classifying Errors to Decide Action

Do not rely solely on exception class names to decide whether to retry. The same `IllegalStateException` can represent a programming bug, invalid data, or an unready system. Include **stage**, **adapter**, **business key**, **response status**, **attempt number**, and **recoverability**.

| Logical Category | Example | Handling Approach |
|---|---|---|
| INVALID_INPUT | CSV missing required field | Quarantine and request data fix |
| TEMPORARY_UNAVAILABLE | SFTP timeout, HTTP 503 | Bounded retry with backoff |
| PERMISSION_DENIED | HTTP 403, SFTP auth fail | Alert, verify credentials/policy |
| DUPLICATE | orderId already processed | Idempotent success or business rejection |
| CONFLICT | Optimistic locking, HTTP 409 | Reload state, conditional retry |
| POISON_MESSAGE | Message always crashes parser | DLQ/DLT or quarantine |
| UNKNOWN | Unclassified exception | Log safe metadata, investigate |

Global `errorChannel` should keep the role of general error recording and routing. Adapter-specific recovery rules should live close to their respective flows to avoid a single global handler with too many branches and uncontrolled side effects.

### 16.2. Business Error Event

~~~json
{
  "eventType": "integration.processing.failed",
  "flowId": "sftp-orders-import",
  "adapterType": "SFTP_INBOUND",
  "stage": "persist-order",
  "correlationId": "order-import-274",
  "businessKey": "order-274",
  "classification": "TEMPORARY_UNAVAILABLE",
  "exceptionType": "DataAccessResourceFailureException",
  "attempt": 3,
  "maxAttempts": 3,
  "disposition": "REQUIRES_RETRY_WORKER",
  "occurredAt": "2026-11-23T08:00:00Z"
}
~~~

This is an **application-defined event model**, not the default structure of `ErrorMessage`. A handler can transform an `ErrorMessage` into an event like the one above to send to a durable recovery store per design. If the event is not saved successfully, you cannot claim the data has been preserved for later processing.

### 16.3. Preserving the Message Contract Across Steps

A flow may transform a payload from `File` to `String` and then to `OrderCommand`. Agree on:

- Which business key is used for identification and deduplication?
- Is the correlation ID generated inbound or received from the partner?
- Which headers must be preserved across transformers/routers/gateways?
- Which payload parts are permitted in logs or recovery events?
- Should replay start from the original file, normalized message, or business command?
- Which reference and version must the error event carry to avoid reprocessing stale data?

**Do not send an ErrorMessage back into an input channel expecting OrderCommand**: an `ErrorMessage` payload is a `Throwable`. Replay must recreate a message conforming to the contract and enforce idempotency, not retry endlessly due to missing error classification.

## 17. Observability for errorChannel

### 17.1. Structured Logging

Information to include: flow and adapter name, correlation ID, message ID, sanitized business key, exception class, stage (`receive`/`transform`/`send`/`ack`/`commit`), attempt, recovery outcome, and timestamp. Do not log verbatim tokens, passwords, private keys, entire files containing personal data, or sensitive HTTP bodies.

### 17.2. Metrics to Monitor

| Metric | Purpose |
|---|---|
| integration_errors_total by flow and type | Count errors, detect rising error rates |
| integration_retries_total | Track retry cost |
| retries_exhausted_total | Identify messages that did not self-recover |
| quarantine_items or DLQ depth | Measure backlog requiring handling |
| message_processing_latency | Detect latency/timeouts |
| last_successful_poll_timestamp | Detect silent pollers |
| consumer_lag/unacked_count | Track broker backlog when applicable |
| error_handler_failure_total | Detect when the error handler itself is failing |

Do not put unique `messageId` or `businessKey` values as metric labels because that causes high cardinality; use logs/traces to query by correlation ID.

### 17.3. Tracing Across Adapters

A message flowing through SFTP, Spring Integration, JDBC, and HTTP may cross multiple threads or services. Trace context is preserved only when infrastructure and code properly propagate headers/context. Do not assume `ErrorMessage` always carries complete span context, especially after multiple message transformations.

### 17.4. Zero Errors Can Still Be an Incident

A poller may stop picking up files without throwing an exception; the `ErrorMessage` count is 0 while data is delayed. Besides error-rate alerts, alert on **no successful poll**, backlog age exceeding SLA, queue depth, last-successful-send, retries exhausted, and permission failures. A single transient timeout that succeeds on retry usually should not page as a critical incident.

## 18. Case Study: SFTP → CSV → JDBC → HTTP → Kafka

### 18.1. Context

An application watches an SFTP directory where a distributor uploads order files. Each file contains multiple rows. The system downloads the file, parses CSV, validates data, persists orders to a DB, calls an HTTP outbound gateway to confirm, and emits a Kafka event upon completion.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound poller"]
    CSV["CSV parser and validator"]
    DB["JDBC persistence"]
    HTTP["HTTP outbound"]
    KAFKA["Kafka outbound"]
    GLOBAL["Default errorChannel"]
    LOCAL["Dedicated error channel / advice / container strategy"]
    OPS["Logging, metrics, triage"]
    SFTP --> CSV --> DB --> HTTP --> KAFKA
    SFTP -. "Poller error if published globally" .-> GLOBAL
    CSV -. "Error caught and published" .-> LOCAL
    DB -. "SQLException" .-> LOCAL
    HTTP -. "HTTP failure" .-> LOCAL
    KAFKA -. "Producer failure" .-> LOCAL
    GLOBAL --> OPS
    LOCAL --> OPS
~~~

This diagram does not describe a single distributed transaction spanning SFTP, JDBC, HTTP, and Kafka; **each system has its own state mechanism**.

### 18.2. Scenario A — SFTP Timeout Before Downloading File

The poller fails to connect. There may not yet be a `Message` representing a file, so `failedMessage` can be null. The poller's error strategy may publish an `ErrorMessage` with a connection exception. You need to:

1. Log the adapter, sanitized host identifier, `stage = connect/list`, and exception type;
2. Retry with backoff without opening unbounded new sessions;
3. Monitor time without receiving files and alert if a threshold is exceeded;
4. Avoid passing partially downloaded files into the parser;
5. Upon reconnection, reconcile remote/local files and filter state.

### 18.3. Scenario B — CSV Fails Schema Validation

The file was downloaded, but a row is missing the order ID. The handler throws a validation error. If the error strategy publishes an `ErrorMessage`, you can inspect `failedMessage` to identify the failing file/row, though payload content depends on the stage.

**Do not infinitely retry** a file with permanent data errors. Quarantine the file, record the reason and correlation ID, request a fix from the sender, and then perform a controlled replay from valid input. When the file has already been marked by a file filter, check how to reset or manage metadata to avoid both losing the file and duplicate reads.

### 18.4. Scenario C — DB Fails Midway

Some rows were committed before the DB became unavailable. Retrying the whole file could create duplicate orders. Use appropriate DB transactions, business keys/unique constraints, and idempotent writes. `ErrorMessage` cannot roll back rows that have already committed. When uncertain which rows were written, reconcile by business key before replaying.

### 18.5. Scenario D — HTTP Timeout After Downstream Processed the Request

The application sends a POST to confirm an order. The partner processes it successfully, but the response is lost on the network. Uncontrolled retry could confirm twice. Use an idempotency key if the API supports it, or query status before retrying. If the outcome is indeterminate, mark it **needs reconciliation** rather than assuming the request completely failed.

### 18.6. Scenario E — Kafka Producer Reports Failure

The DB wrote the order and HTTP ran, but the Kafka outbound producer failed to emit the event. You cannot roll back HTTP from `ErrorMessage`. You can use a **transactional outbox** tying the DB commit to the intent to publish the event, then have a publisher retry sending to Kafka and record publish status. Recovery must ensure no unintended duplicate events or that consumers are idempotent.

### 18.7. Lessons Learned

Global `errorChannel` is useful for observing published exceptions that lack a dedicated error destination. However, safe recovery must consider **SFTP file state, JDBC transactions, HTTP idempotency, Kafka producer/offset, and data contracts**. A `Throwable` alone cannot determine replay safety without knowing which side effects already occurred.

## 19. Testing Default errorChannel and Dedicated Error Channels

### 19.1. Testing Synchronous DirectChannel

Create a `DirectChannel` flow with a handler that intentionally throws `IllegalStateException`. Send a message in a test and verify:

- The exception propagates to the caller in the synchronous flow or is handled by advice/gateway as configured;
- Do not expect global `errorChannel` to receive an `ErrorMessage` if no error publishing mechanism exists;
- When a gateway is present, the response code/body matches the contract;
- No side effect is treated as successful if the handler did not complete.

**Takeaway:** a synchronous exception and a published `ErrorMessage` are two distinct technical events.

### 19.2. Testing a Poller

Create a File inbound adapter or `QueueChannel` consumer with a poller; have the handler throw an exception. Configure an error channel for the poller or verify the fallback. Verify:

1. The poller picks up the message and invokes the handler;
2. An `ErrorMessage` is sent to the expected channel;
3. `ErrorMessage.payload` is a `Throwable`;
4. If `failedMessage` is present, its message ID/correlation links to the test input;
5. The failure is not accidentally treated as success;
6. Retry, quarantine, rollback, or replay executes per the designed policy.

### 19.3. Using QueueChannel to Capture Errors in Tests

For tests, a dedicated `QueueChannel` makes receiving an `ErrorMessage` and asserting results easy to control. Example bean configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;

@Configuration
class TestErrorChannelConfig {

    @Bean
    QueueChannel testErrors() {
        return new QueueChannel();
    }
}
~~~

Once the test flow is configured to **send ErrorMessage to `testErrors`** and executed, you can assert:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// testErrors is obtained from the Spring context and wired in the test flow.
Message<?> received = testErrors.receive(5_000);

if (!(received instanceof ErrorMessage)) {
    throw new AssertionError("Expected ErrorMessage on testErrors");
}

Throwable problem = ((ErrorMessage) received).getPayload();
if (problem == null) {
    throw new AssertionError("Missing Throwable payload");
}
~~~

This is an illustrative assertion snippet, not a standalone runnable test class without setting up the flow. In real tests, use JUnit/AssertJ, bounded timeouts, and clean up state after each test. **Do not replace production's global `errorChannel` with a `QueueChannel` just for test assertions**.

### 19.4. Testing Missing Subscribers or Error Handler Failures

For custom error channels, clarify:

- What happens if there are no subscribers or the channel rejects the send?
- Does `QueueChannel` have a capacity limit, and how does it behave when full?
- Does the error handler throw an exception if downstream alerting/DB fails?
- Does it trigger an error-of-error loop or send duplicate alerts?
- Are failures still counted/alerted even if the custom error handler fails?

Behavior depends on channel type and properties such as send timeout / `requireSubscribers`. Test against the actual configuration instead of guessing from the channel name.

### 19.5. Adapter Test Matrix

| Adapter | Error Trigger | Verification Criteria |
|---|---|---|
| File | Malformed CSV | Error observed, file quarantined, clear replay |
| SFTP | Timeout or permission denied | Backoff, no partial download, alert |
| HTTP inbound | Schema-invalid request | 4xx response, no stack trace returned |
| HTTP outbound | Timeout/503 | Retry budget, idempotency, and outcome |
| JMS | Handler throws | Transaction, redelivery, and DLQ per config |
| AMQP | Poison message | Proper reject/nack/requeue/DLQ |
| Kafka | Undeserializable record | Container error strategy, offset, and DLT |
| JDBC | SQLException | Transaction rollback/row state and replay |

You do not need to run every external system to understand global `errorChannel`. However, **do not treat a unit test on `ErrorMessage` as equivalent to testing real broker delivery semantics and transactions**.

## 20. Error Diagnosis Runbook in Spring Integration

### Step A — Locate the Error

1. Identify the flow name, message source, endpoint/adapter, and correlation ID;
2. Check whether the exception appeared in the caller, poller, executor, container, or HTTP response;
3. Check whether an `ErrorMessage` was published, and on which channel;
4. Determine whether `failedMessage`/`originalMessage` exists and contains useful metadata;
5. Distinguish source errors, transform errors, handler errors, outbound send errors, and ack/commit errors.

### Step B — Assess How Far Data Was Processed

1. Was the file downloaded, marked received, moved, or deleted?
2. Which DB rows committed, and were there side effects?
3. Did HTTP downstream receive/execute the request despite a caller timeout?
4. Did the broker ack/commit the offset, or is redelivery occurring?
5. Is the API client/connector experiencing configuration or authentication failures?
6. Could the same message be processed concurrently, causing duplicates?

### Step C — Choose Remediation

| Finding | Action |
|---|---|
| Transient and safe to retry | Retry with backoff, limit, and idempotency |
| Permanently invalid data | Quarantine/DLQ/DLT, notify producer |
| Incorrect broker acknowledgment | Fix listener/container transaction/ack config |
| Partial DB commit | Reconcile transaction and business key |
| Indeterminate HTTP outcome | Query status or perform reconciliation |
| Error handler losing info | Add safe error event/context |
| Error not producing ErrorMessage | Inspect throw point and error strategy |

### Step D — Verify Recovery

Confirm no input was lost, no unintended duplicate processing occurred, log access is protected, retries do not overload systems, DLQ/quarantine has an owner, and alert metrics are updated. After fixing, test **both the success path and failure path** to ensure the flow was not altered unintentionally.

### Step E — Close the Incident with Evidence

Document root cause, failure point, configuration version, impact window, number of failed messages, replayed messages, data needing reconciliation, and preventive actions. Do not merely write "handled in errorChannel"; prove **which final state each business message reached**.

## 21. Common Mistakes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Assuming all exceptions go to errorChannel | Synchronous errors missed | Analyze throw points and error publishers |
| Listening only to global channel, ignoring per-flow handlers | Errors in specialized flows go unobserved | Check routing and per-adapter mechanisms |
| Treating LoggingHandler as a retry mechanism | Failed messages left behind or lost | Design dedicated retry/recovery |
| Catching exception and returning success | Ack/commit despite business failure | Preserve failure semantics, proper transactions |
| Retrying every error type | Poison messages and retry storms | Classify transient/permanent, bound retries |
| Multiple retry layers without a budget | Downstream call count multiplies sharply | Calculate total retries and timeouts |
| No idempotency | Replay creates duplicate orders | Business key, dedupe/outbox |
| Logging full error payloads | Data leaks, log overload | Structured metadata, masking |
| Sending ErrorMessage back to business input | Consumer receives Throwable violating contract | Replay proper original message/command |
| Confusing errorChannel with JMS DLQ or Kafka DLT | Misunderstood delivery/offset semantics | Configure container/broker separately |
| Ignoring file filter state | Files lost or reprocessed wrongly | Metadata store, quarantine, restart tests |
| Treating HTTP timeout as definitely unprocessed | Duplicate side effects | Idempotency key/reconciliation |
| Watching only error count | Silent poller death goes undetected | Monitor last poll, backlog, latency |
| Error handler throwing back into itself | Error loops and duplicate alerts | Isolate recovery, limit side effects |
| Using PublishSubscribeChannel expecting one consumer | Multiple handlers act simultaneously | Separate responsibilities, idempotent notifications |
| Not testing transactions and acks | Lost/duplicated records when broker fails | Integration test container and offset/ack |

## 22. Production Readiness Checklist for Error Flows

### A. Understanding Error Paths

- [ ] Identify which channels/endpoints are synchronous, polling, or message-driven.
- [ ] Know which exceptions propagate to the caller and which are published.
- [ ] Can trace `ErrorMessage` back to a message or business key when available.
- [ ] Know all subscribers on global `errorChannel` and whether duplicate logging occurs.
- [ ] Flows requiring custom recovery have dedicated error channels/advice/container policies.

### B. Message Contracts and Security

- [ ] Payload, headers, and correlation ID are defined.
- [ ] Error taxonomy and stages exist to classify retries.
- [ ] Logs and error events do not leak passwords, tokens, private keys, or sensitive data.
- [ ] Untrusted callers cannot use the `errorChannel` header to arbitrarily route internally.
- [ ] Replay uses schema-valid messages with idempotency.

### C. Delivery and Transactions

- [ ] File/SFTP controls file readiness, filters, move/quarantine, and replay.
- [ ] HTTP has timeouts, status mapping, idempotency keys, and time budgets.
- [ ] JMS/AMQP has ack/tx, redelivery, retry limits, and DLQ where needed.
- [ ] Kafka has container recovery, offset/commit, and DLT where needed.
- [ ] JDBC has transactions/outbox or mechanisms preventing partial commits.
- [ ] Retries apply only to recoverable failures, with backoff and limits.

### D. Operations

- [ ] Metrics exist by flow, stage, retries exhausted, backlog, and error handler failures.
- [ ] Alerts fire if a poller has not succeeded within the expected window.
- [ ] Quarantine/DLQ/DLT has an owner and replay procedure.
- [ ] Both direct synchronous exceptions and poller-published `ErrorMessage` are tested.
- [ ] Poison message, transient timeout, transaction failure, and restart are tested.
- [ ] Error outcomes are verified end-to-end, not just by observing logs.

## 23. Self-Check Questions

**Question 1. What is the primary function of the default errorChannel?**

**Answer:** It is a global `MessageChannel` that receives **published ErrorMessages** from error handling mechanisms using this fallback. It does not automatically catch every exception and does not automatically retry, roll back, or push data to a DLQ.

**Question 2. Why does a handler on DirectChannel throw an exception without the errorChannel subscriber seeing the error?**

**Answer:** `DirectChannel` usually processes synchronously; the exception propagates back to the sender. Only when a layer is designed to catch and publish an `ErrorMessage` will the error channel receive it.

**Question 3. What is the payload of an ErrorMessage?**

**Answer:** A `Throwable`. It may be a `MessagingException` containing `failedMessage`. An original message may also exist if provided, but you should not rely on both fields always being populated.

**Question 4. Does registering @ServiceActivator(inputChannel = "errorChannel") replace the default LoggingHandler?**

**Answer:** Not necessarily. When `errorChannel` is a `PublishSubscribeChannel`, multiple subscribers can receive the same message, including the existing logging subscriber. Check the context to avoid duplicate logs/side effects.

**Question 5. A File inbound poller throws an exception and errorChannel logs it. Has the file been reprocessed?**

**Answer:** Cannot be concluded yet. You must check the file filter, metadata, move/delete policy, any transactions, and retry workflow. Logging does not guarantee retry.

**Question 6. An HTTP inbound gateway fails validation. Should you only send an ErrorMessage to global errorChannel?**

**Answer:** Not sufficient. The HTTP caller needs an appropriate status/body and clear timeout handling. Exception/response mapping at the gateway/web layer or a dedicated error flow is required.

**Question 7. In JMS, can ErrorMessage replace broker rollback?**

**Answer:** No. Acknowledgment, rollback, redelivery, and DLQ are governed by the listener container, session transaction, and broker policy. They must be tested together with the error flow.

**Question 8. If Kafka has errorChannel, does it automatically have a dead-letter topic?**

**Answer:** No. Kafka DLT/offset/recovery must be configured separately on the adapter and Kafka listener/container. A Spring `MessageChannel` is not a Kafka topic.

**Question 9. Does an HTTP POST timeout mean the server did not process the request?**

**Answer:** No. The server may have committed the operation while the response was lost. Retrying write operations requires an idempotency key or status check to prevent duplicate effects.

**Question 10. Why log a correlation ID instead of logging the entire payload?**

**Answer:** A correlation ID enables tracing data across steps without exposing sensitive information. Payloads may contain personal data, secrets, or be very large, creating security and operational risks.

**Question 11. Can a handler receiving ErrorMessage resend that same ErrorMessage to the input channel to replay?**

**Answer:** You should not. Business input typically expects a different schema, whereas `ErrorMessage` has a `Throwable` payload. Replay must reconstruct a contract-compliant command/message, check side-effect state, and enforce idempotency.

**Question 12. Why monitor pollers even when errorChannel has zero errors?**

**Answer:** A poller can stop running or stop picking up data due to configuration without emitting an `ErrorMessage`. You need last-successful-poll, backlog, age of oldest item, and health signals.

**Question 13. When should you separate a dedicated fileErrors channel from errorChannel?**

**Answer:** When the file flow requires dedicated handling such as quarantine, retries, or a different SLA from HTTP/broker flows. A dedicated channel separates recovery policy and ownership, while the global channel can retain high-level monitoring.

**Question 14. What problem can a retry at the handler plus a retry at the broker cause?**

**Answer:** Total execution attempts can multiply, causing overload or duplicate side effects. You must calculate an end-to-end retry budget, backoff, and duplicate handling.

**Question 15. What evidence proves error handling succeeded?**

**Answer:** Not just log output. You must prove the input succeeded, was retried with a result, was placed into quarantine/DLQ, or is in an owned error state; meanwhile file/DB/HTTP/broker states and acknowledgments must be consistent.

## 24. Conclusion

In **Spring Integration Adapters**, the **default errorChannel** is a key mechanism for **receiving errors converted into ErrorMessages**, especially in poller scenarios and flows without a synchronous caller to receive exceptions. Typically the global channel has a logging subscriber; applications can add Service Activators to observe or classify errors. However, **the actual error path depends on the endpoint, channel, error strategy, advice, and adapter**, so you cannot equate "throwing an exception" with "arriving on errorChannel".

Reliable design requires combining **message contracts, correlation IDs, error classification, bounded retries, idempotency, acknowledgments, transactions, and owned recovery**. For File/SFTP, manage file state and replay; for HTTP, handle responses and timeouts; for JMS/AMQP/Kafka, understand broker/container acknowledgments and dead-lettering; for JDBC, verify commits and side effects. Global `errorChannel` gives visibility into incidents, but **per-system policies** determine whether a message is properly reprocessed, rejected, or quarantined.

Key takeaway: **catching an error is not the same as recovering the integration flow**. Only with end-to-end verification that the business message reached the intended state or was safely stored for later processing can the system consider the failure fully handled.
