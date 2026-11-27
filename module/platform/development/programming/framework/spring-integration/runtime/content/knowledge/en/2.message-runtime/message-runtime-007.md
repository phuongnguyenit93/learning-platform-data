# Message History and Path Tracing

In Spring Integration, a message can pass through many different channels, endpoints, and processing flows before completing. When a system runs synchronously, asynchronously, with queues, pollers, executors, retries, or error branches, looking solely at the payload is usually not enough to know where a message has traveled, where it stopped, and why the result was delayed or failed.

Message history and tracing help answer those questions. Message history records the components a message has traversed. Logs and metrics provide events, timestamps, and operational numbers. Distributed tracing links executions across multiple threads or services. Combining these layers properly lets you trace a message's path without logging sensitive payloads.

## 1. Distinguishing topology, history, and trace

Before diagnosing, distinguish three types of information commonly lumped together as "trace".

| Type of information | Question answered | Typical sources |
|---|---|---|
| Topology | How is the system wired together? | IntegrationFlow, channel, endpoint, IntegrationGraphServer |
| Message history | Which specific components did this message pass through? | MessageHistory in message headers |
| Runtime observability | When did a component process, how long did it take, and are there errors or backlogs? | Logs, metrics, Micrometer Observation, and tracing |

Topology describes the declared or registered structure. It does not prove that a specific message actually visited every node. Message history describes a message's journey, yet it is not a complete audit trail and does not by itself explain every wait interval. Logs, metrics, and traces add timing, duration, errors, and relationships between executions.

A well-observed system typically combines all three: using the graph to see possible paths, history to find the components a message touched, and logs and metrics to explain what happened at each point.

## 2. Identifying messages via headers

To find the right message in logs or inside a flow handling many concurrent messages, first choose the appropriate identification key.

| Value | Meaning | How to use |
|---|---|---|
| Message ID | Identifies a specific message | Find logs related to a single message |
| Correlation ID | Links multiple messages belonging to the same business process or processing group | Track an order, a request, or messages produced by a splitter |
| Trace ID | Links spans of a single execution across threads or services | Track a request across multiple components and systems |
| Sequence number/size | Position and size of a message sequence | Track split elements waiting for an aggregator to combine |

Message ID does not replace Correlation ID. One business process can create multiple messages, each with its own ID yet sharing the same Correlation ID. Similarly, Correlation ID is not automatically a Trace ID: an order can be processed across multiple requests or attempts, whereas each execution can have its own trace.

Generate a Correlation ID at the ingestion boundary if the system does not already have a reliable business identifier, then preserve it across processing steps. For example, a producer can build a message as follows:

~~~java
Message<Order> message = MessageBuilder.withPayload(order)
    .setHeader("correlationId", businessRequestId)
    .build();

ordersInputChannel.send(message);
~~~

The header name in the example is an application-defined business header. To interoperate with a splitter, aggregator, or tracing system, use the standard headers and propagation mechanisms required by that component. Do not invent a header named traceId and treat it as a complete distributed trace; distributed tracing also requires span management and context propagation across execution boundaries.

Spring Integration supports correlation and sequence headers for flows that split, route, and aggregate messages. When a splitter produces multiple child messages, those messages can share the same correlation while having different message IDs and sequence numbers. An aggregator relies on group metadata to know which messages belong to the same set. When investigating, retain both message ID and Correlation ID to distinguish an individual item from the whole business operation.

## 3. Enabling and reading Message History

Spring Integration provides Message History to record the tracked components a message traverses. History is stored in the message's headers, so it can be read at downstream endpoints without needing a separate lookup store for each step.

You can enable this feature with an annotation in Java configuration:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationConfiguration {
}
~~~

When Message History is enabled, components capable of participating in history tracking append their information to the message. A history entry typically provides component name, component type, and recorded timestamp. Stable component names make matching history against IntegrationFlow and logs much easier. Therefore, give beans, channels, and endpoints clear names instead of letting every component use hard-to-read auto-generated names.

You can read history from a message at an inspection endpoint:

~~~java
@Service
public class TraceInspector {

    private static final Logger log =
        LoggerFactory.getLogger(TraceInspector.class);

    @ServiceActivator(inputChannel = "orders.inspect")
    public void inspect(Message<?> message) {
        MessageHistory history = MessageHistory.read(message);

        log.info("messageId={}, correlationId={}, history={}",
            message.getHeaders().getId(),
            message.getHeaders().get("correlationId"),
            history == null ? "disabled" : history);
    }
}
~~~

The main imports in the example belong to Spring Messaging and Spring Integration:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
~~~

MessageHistory.read(message) returns the history attached to the message; if history is not enabled or is absent from the message, the result may be null. Check for null before reading. The snippet above logs message ID, Correlation ID, and history, without logging the payload. In a real application, TraceInspector is only a sample observation endpoint; place it where the application genuinely needs inspection.

If you do not want to track every component, you can restrict which components are recorded using MessageHistoryConfigurer configuration and component name patterns compatible with your Spring Integration version. Enabling history only for flows or areas under investigation reduces header size and processing overhead on high-throughput paths.

### What can and cannot Message History record?

History is useful for seeing which components a message touched and the order in which history entries were recorded. It does not record payload contents, does not guarantee every internal operation gets a separate entry, and does not replace error logs or metrics. A component that is untracked, lacks a matching name, or sits outside the application boundary may not appear in history.

Do not infer exact endpoint processing duration merely by subtracting two consecutive timestamps. The delta can include processing time, queue wait time, poller wait time, scheduling, and inter-thread latency. To measure the duration of a step, use metrics or spans placed around that operation.

Because history lives in headers, messages must retain headers when transformed or passed through adapters. Steps that construct new messages in custom code must preserve necessary business and tracing headers. When crossing a broker, HTTP, or a serialization boundary, verify which headers are actually transmitted and restored on the receiving side; do not assume all internal headers are preserved.

## 4. Reading paths across channels and endpoints

Messages usually travel through channels to be handed off to endpoints. Channels determine how messages are transferred; endpoints perform work such as filter, transformer, router, service activator, splitter, or aggregator. When tracing history, know the channel type sitting between two endpoints because it determines which thread continues processing and where a message may have to wait.

| Channel | Delivery mechanism | Tracing implication |
|---|---|---|
| DirectChannel | Invokes subscriber on the message-sending thread | Handling errors can usually propagate back to the sender; path is easy to trace within the same call stack |
| ExecutorChannel | Hands off work to an executor | Processing may continue on a worker thread; search logs by ID rather than relying on the original sending thread |
| QueueChannel | Holds message in a queue for a consumer to receive later | There may be a wait gap between send and receive; check queue depth and poller |
| PublishSubscribeChannel | Broadcasts message to multiple subscribers | One message can spawn multiple processing branches; branches can run concurrently if an executor is configured |

An illustrative path combining both synchronous and asynchronous processing:

~~~mermaid
flowchart LR
    P[Producer thread] --> D[DirectChannel]
    D --> F[Filter / Transformer]
    F --> E[ExecutorChannel]
    E --> W[Worker thread]
    W --> Q[QueueChannel]
    Q -->|Poller receives message| T[Polling thread]
    T --> S[Service Activator]
    S --> R[Result or reply channel]
~~~

At the DirectChannel segment, the producer typically waits for the endpoint to finish processing. Crossing ExecutorChannel, work can run on a worker thread and the producer is no longer the thread executing subsequent processing. With QueueChannel, the message can sit in the queue until the Poller/consumer picks it up. Therefore, a long gap between two history entries does not necessarily mean the preceding endpoint ran slowly; the message may simply have been waiting to be dequeued.

When reading a flow, determine in sequence:

1. Which input channel receives the message and whether it has an active subscriber or consumer.
2. What type the next endpoint is: filter, transformer, router, service activator, or another endpoint.
3. Whether the channel after the endpoint is DirectChannel, ExecutorChannel, QueueChannel, or PublishSubscribeChannel.
4. Whether a Poller, TaskExecutor, or scheduling mechanism introduces a thread boundary.
5. Whether any router, publish-subscribe, splitter, or aggregator branch causes the message to take multiple paths.

Do not view an IntegrationFlow as a single linear call stack. A router can pick one branch; PublishSubscribeChannel can broadcast a message to multiple subscribers; a splitter spawns child messages; an aggregator waits for multiple messages and emits a combined result. In these cases, each branch can have its own history and completion time. Use Correlation ID to group messages belonging to the same business operation, then use Message ID to trace each branch.

## 5. Combining history with logs and ChannelInterceptor

History shows which components a message passed through; logs provide contextual events at specific points in time. Logs should be structured and contain at minimum message ID, Correlation ID, channel or endpoint name, processing outcome, and error code if any. This lets you find the same message across threads without depending on log arrival order.

ChannelInterceptor is a suitable extension point for observing sends and receives on channels. For example, in preSend you can record the channel name alongside identifying keys:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    log.debug("send channel={} messageId={} correlationId={}",
        channel,
        message.getHeaders().getId(),
        message.getHeaders().get("correlationId"));
    return message;
}
~~~

Interceptors can be registered directly on a channel or applied globally by pattern via the global channel interceptor mechanism. Restrict patterns to the channels needing observation to avoid generating excessive logs across the entire system. If you need visibility in both directions, consider appropriate send and receive callbacks of ChannelInterceptor, keeping in mind that receive callbacks apply only to pollable channels supporting receive.

Do not log full payloads by default. Payloads can contain personal data, business secrets, or large data volumes. Log IDs, message types, sizes, statuses, and selected permitted fields. If a business value must be logged for investigation, apply the system's data-masking rules and log retention policies.

When using MDC or ThreadLocal to attach Correlation ID to logs, watch executor boundaries. Context bound to the sending thread does not automatically appear on worker threads. Use context propagation suited to your TaskExecutor or application tracing library; also ensure context is cleared after task completion to prevent leaking IDs to other messages.

## 6. Tracking errors, retries, and transactions

A message appearing in history does not mean the business operation committed successfully. History may have been recorded before the transaction ended. If the transaction rolls back, the message may be redelivered or reprocessed, while logs from the previous attempt remain. Therefore, when investigating the final outcome, check transaction outcome, retries, and persistence state as well.

### Error flow

When an endpoint raises an exception, how the error is observed depends on the execution boundary. With synchronous handling on DirectChannel, exceptions can typically propagate back to the caller. With asynchronous handling via an executor or poller, the original sender may have already returned before the error occurred; in that case, check errorChannel and the corresponding error handler.

Spring Integration represents errors dispatched to an error flow using ErrorMessage. The payload of an ErrorMessage is usually the exception; for MessagingException, inspect failedMessage to locate the failing message and cause to find the root cause. When logging errors, include message ID, Correlation ID, endpoint name, exception type, and failed message metadata. Do not log only a stack trace without keys linking the error back to the original message.

### Retry

Retries can cause the same operation to execute multiple times. Do not look at a single history line and conclude the message was processed only once. Record attempt counts explicitly via the active retry/advice mechanism, distinguish transient errors from final failures, and inspect backoff policies. For operations with side effects, ensure idempotency or duplicate-processing guards so retries do not create duplicate business outcomes.

### Transactions and Message Store

Pollers can be configured to run inside a transaction. When investigating, distinguish when the endpoint starts processing from when the transaction commits. A "processed" log written before commit is not sufficient proof that data was persisted. If strong evidence is needed, record outcomes post-commit or use an audit/outbox mechanism aligned with the application's transaction.

MessageStore and MessageGroupStore store messages or message groups for scenarios such as aggregators, resequencers, and stateful processing. They are useful for recovery and state management, yet do not automatically serve as a complete audit log. If requirements call for querying long-term business history, design a dedicated audit store with appropriate retention, lookup keys, and integrity guarantees.

## 7. Inspecting topology and runtime state

When history stops at a component, the next step is verifying whether the downstream component exists and is active. Spring Integration provides IntegrationGraphServer to represent components and links in the integration context. In applications configured with Spring Boot Actuator, this topology can also be published via the integration graph endpoint if enabled and exposed.

The graph is useful for spotting channels with no consumers, endpoints not registered as expected, or wiring that differs from design. The graph does not display the full journey of a specific message, nor does it replace metrics on queue depth or executors. Cross-reference the graph with MessageHistory and logs.

For dynamically registered flows, inspect flow lifecycle in IntegrationFlowContext: has the flow been registered, have endpoints started, or were they stopped or unregistered during investigation? When flows change, runtime topology changes too. An older message may carry history from the previous structure, while newer messages traverse the structure after re-registration.

To check bottlenecks, inspect appropriate operational metrics as well:

- QueueChannel: queued message count, enqueue/dequeue rates, and wait times.
- ExecutorChannel: pool size, active workers, task queue depth, and rejected task count.
- Poller: polling interval, messages per poll, processing duration, and empty poll count.
- Endpoint: received/processed message count, error count, and processing duration if instrumentation is enabled.
- Error flow: error count by type, messages entering errorChannel, and error handling outcomes.

Micrometer metrics and Micrometer Observation can add metrics and spans for instrumented components. When cross-service tracing is needed, integrate with Micrometer Tracing or OpenTelemetry and ensure trace context propagates across relevant protocols. Message History remains helpful inside Spring Integration, while distributed traces provide parent-child relationships and durations across execution boundaries.

## 8. Procedure for diagnosing a delayed or lost message

Suppose an order was sent into a flow but no result appears. You can trace it in the following order:

1. **Lock in the search key.** Grab the message ID if investigating a single specific message; grab the Correlation ID if you need to gather all messages for an order or a single processing run.
2. **Read history.** Find the last component appearing in history. Verify whether Message History is enabled, whether the component is tracked, and whether headers survived adapters.
3. **Cross-reference topology.** Use component names in history to locate the next channel and endpoint on IntegrationFlow or IntegrationGraphServer.
4. **Check channel type.** If DirectChannel, inspect the sending thread's call stack and exceptions. If ExecutorChannel, check workers, task queues, and logs by ID. If QueueChannel, check queue depth and consumer pollers.
5. **Check branches.** If there is a router or publish-subscribe, determine which branch was selected or which subscribers received the message. If there is a splitter/aggregator, check sequence and group state by Correlation ID.
6. **Check errors and retries.** Look for ErrorMessage, failedMessage, exception causes, attempt counts, and final retry status.
7. **Check transactions and storage.** Verify whether transactions committed or rolled back, whether the message was redelivered, and whether MessageStore/MessageGroupStore is holding pending state.
8. **Measure intervals.** Use metrics or spans to determine whether the message waited in a queue, waited for an executor, waited for a poller, or ran inside an endpoint. Do not attribute the entire history timestamp delta to endpoint execution time.

Some common symptoms:

| Symptom | Possibilities to check |
|---|---|
| No history | History not enabled, component excluded from pattern, newly constructed message dropped headers, or message crossed a header-stripping boundary |
| History stops at input channel | No subscriber/consumer, endpoint not started, flow not registered, or message waiting for consumer |
| History shows ExecutorChannel step but no following step | Executor overloaded, task rejected, worker failed, or logs on another thread not yet correlated by ID |
| History shows QueueChannel but next step appears late | Queue backlog, slow poller, stopped consumer, or max-messages-per-poll limit |
| Same Correlation ID but multiple Message IDs | Could be splitter, retry, publish-subscribe, or multiple messages for the same business operation; classify by sequence and branch |
| History present but business operation incomplete | Check exceptions, retries, transaction rollbacks, incomplete aggregator group, or uncommitted side effects |

## 9. Keeping tracing useful and safe in production

Message History increases metadata on every message. For long flows or high-throughput systems, enabling history globally can increase message creation, header copying, serialization, and logging overhead. Restrict component patterns, enable high detail only for the time window needed if possible, and monitor impact on throughput and memory.

Name channels and endpoints after business domains or functions, such as orders.validate, orders.persist, or orders.error. Use the same naming convention across flows, logs, and dashboards so on-call operators can correlate quickly. Avoid embedding runtime data such as customer IDs or per-request IDs into component names.

Do not use Message History as an immutable audit store. Headers can be stripped, altered, or omitted across an adapter; history also does not prove a transaction committed. If business requirements demand proof of processing, write structured audit events to durable storage and attach message ID/Correlation ID for lookup.

For distributed tracing, ensure trace context propagates correctly over HTTP, messaging brokers, and executors. Check sampling to know which traces are retained; a missing trace may be due to sampling or unconfigured propagation rather than an unprocessed message. Avoid recording tokens, credentials, sensitive payloads, or personal data in span attributes.

## 10. Implementation checklist

- [ ] Assign stable names to channels, endpoints, and IntegrationFlows.
- [ ] Generate or receive a Correlation ID at the ingestion boundary and preserve it across processing steps.
- [ ] Enable Message History at the needed scope and verify with MessageHistory.read(message).
- [ ] Write structured logs with message ID, Correlation ID, component, outcome, and error code.
- [ ] Identify DirectChannel, ExecutorChannel, QueueChannel, and Poller boundaries in the flow.
- [ ] Inspect ErrorMessage, retries, and transaction outcomes when errors or repeated processing occur.
- [ ] Use IntegrationGraphServer to cross-check runtime topology; use metrics/spans to measure duration and backlogs.
- [ ] Verify header propagation across adapters and serialization boundaries.
- [ ] Bound log/history data, avoid logging sensitive payloads, and evaluate overhead in production.

By combining Message History, Correlation ID, structured logs, IntegrationGraphServer, and metrics/tracing, you can trace a message from ingestion to final endpoint, identify where messages wait, distinguish synchronous from asynchronous errors, and verify processing outcomes alongside transactions. Each tool answers a different part of the question; using them together yields a more reliable runtime picture.
