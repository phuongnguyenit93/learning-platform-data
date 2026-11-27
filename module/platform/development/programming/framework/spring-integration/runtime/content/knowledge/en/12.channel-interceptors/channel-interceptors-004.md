# Logging, Metrics, and Tracing with Interceptors

In Spring Integration, a channel is the boundary for transferring messages between endpoints. `ChannelInterceptor` lets you observe or adjust messages right at that boundary. It is a useful place to record whether messages were sent or rejected, add context to logs, and collect operational metrics.

Logging, metrics, and tracing answer three different questions: logs record specific events; metrics aggregate system trends and health; traces connect the processing steps of a request across multiple threads or services. An interceptor can support all three, provided you choose the right callback and clearly understand the scope each callback observes.

## 1. What Does ChannelInterceptor Observe?

`ChannelInterceptor` belongs to Spring Messaging and is invoked by the channel around send/receive operations. The main callbacks are:

| Callback | Timing | Observable information |
|---|---|---|
| `preSend` | Before the channel sends the message | Input message, channel, and ability to reject or replace the message |
| `postSend` | After the channel performs the send | Send outcome via the `sent` flag |
| `afterSendCompletion` | When the send process finishes | Final outcome and exception, if any |
| `preReceive` | Before a pollable channel receives a message | Whether to allow performing the receive |
| `postReceive` | After a pollable channel receives a message | The message just retrieved from the channel |
| `afterReceiveCompletion` | When the receive process finishes | Exception and receive completion state |

Not every channel supports receive. Receive callbacks are primarily meaningful for `PollableChannel`, such as `QueueChannel`. `DirectChannel` and `ExecutorChannel` are typically observed via the send path.

Keep in mind that an interceptor observes channel activity. It does not automatically wrap the entire business work of every downstream endpoint. For example, with `QueueChannel`, `postSend` usually records enqueueing; the consumer may process the message later. With `ExecutorChannel`, the send callback may finish once the task has been dispatched, while the handler is still running on a worker thread.

## 2. Choosing the Right Registration Scope

You can register an interceptor directly on a single channel or use `@GlobalChannelInterceptor` to apply it to channels matching a name pattern. Use the narrowest scope that satisfies your observability needs.

Example registering an interceptor for the orders channel group:

~~~java
@Configuration
@EnableIntegration
public class ChannelObservabilityConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*")
    ChannelInterceptor ordersLoggingInterceptor() {
        return new ChannelInterceptor() {

            private final Logger log =
                    LoggerFactory.getLogger("integration.channel.orders");

            @Override
            public Message<?> preSend(Message<?> message,
                                      MessageChannel channel) {
                if (log.isDebugEnabled()) {
                    log.debug("send channel={} messageId={} correlationId={}",
                            channel,
                            message.getHeaders().getId(),
                            message.getHeaders().get("correlationId"));
                }
                return message;
            }

            @Override
            public void afterSendCompletion(Message<?> message,
                                            MessageChannel channel,
                                            boolean sent,
                                            Exception ex) {
                if (ex != null) {
                    log.warn("send failed channel={} messageId={}",
                            channel, message.getHeaders().getId(), ex);
                }
            }
        };
    }
}
~~~

The `orders*` pattern limits the interceptor to channels whose names start with `orders`. Consistent channel naming conventions make logs and metrics easier to correlate. Avoid overly broad patterns if certain internal, control, or high-throughput channels do not need the same level of observation.

If you only need to monitor a single channel, local registration is easier to control. A global interceptor fits when a shared policy applies to a clearly named group of channels.

## 3. Logging: Recording Queryable Events

Logs should show which channel a message passed through, what the send outcome was, and whether any errors occurred. Useful fields typically include:

- Channel name or group.
- Message ID to locate a specific message.
- Correlation ID to group messages belonging to the same business flow.
- Trace ID/span ID if tracing is configured.
- Send outcome and exception type on failure.

Example of `preSend` logging metadata and `afterSendCompletion` logging errors:

~~~java
public class ChannelLoggingInterceptor implements ChannelInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(ChannelLoggingInterceptor.class);

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        if (log.isTraceEnabled()) {
            log.trace("channel={} messageId={} correlationId={}",
                    channel,
                    message.getHeaders().getId(),
                    message.getHeaders().get("correlationId"));
        }
        return message;
    }

    @Override
    public void afterSendCompletion(Message<?> message,
                                    MessageChannel channel,
                                    boolean sent,
                                    Exception ex) {
        if (ex != null) {
            log.warn("channel send failed: channel={} messageId={}",
                    channel, message.getHeaders().getId(), ex);
        }
        else if (!sent && log.isDebugEnabled()) {
            log.debug("channel did not accept message: channel={} messageId={}",
                    channel, message.getHeaders().getId());
        }
    }
}
~~~

Do not log full payloads or all headers. Payloads may contain personal data, tokens, payment details, or large objects. Only log whitelisted fields and adhere to data masking rules.

Logging every message at INFO level can generate massive I/O. Typically, use DEBUG/TRACE for detailed logs and reserve INFO/WARN for meaningful operational events. If sampling is needed, choose clear rates or conditions and ensure critical errors are always recorded.

### Binding MDC to the Message

MDC helps include the correlation ID or trace ID in every log line on the current thread. You can read the correlation ID from the message header, place it into MDC for the processing scope, and then restore or clear it in `finally`.

Do not assume MDC automatically crosses `ExecutorChannel`, pollers, or queues. Thread boundaries require an appropriate context propagation mechanism such as `TaskDecorator` or Micrometer Context Propagation. Avoid leaving MDC values from a previous message on a reused worker thread.

## 4. Metrics: Measuring Counts and Trends

Metrics are well suited for answering questions such as:

- How many messages were accepted by the channel?
- How many times did send return `false`?
- How many exceptions occurred on the send path?
- How does throughput or latency of a channel group change over time?
- Is the queue building up a backlog?

Example using Micrometer `Counter` to count three send outcomes:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders*")
ChannelInterceptor ordersChannelMetrics(MeterRegistry registry) {
    Counter accepted = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "accepted");
    Counter rejected = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "rejected");
    Counter failed = registry.counter(
            "si.channel.send", "channel_group", "orders", "outcome", "failed");

    return new ChannelInterceptor() {

        @Override
        public void postSend(Message<?> message,
                             MessageChannel channel,
                             boolean sent) {
            if (sent) {
                accepted.increment();
            }
            else {
                rejected.increment();
            }
        }

        @Override
        public void afterSendCompletion(Message<?> message,
                                        MessageChannel channel,
                                        boolean sent,
                                        Exception ex) {
            if (ex != null) {
                failed.increment();
            }
        }
    };
}
~~~

In the example, `postSend` distinguishes accepted messages from sends returning `false`; `afterSendCompletion` counts exceptions. These are three separate outcomes, not the count of messages ultimately processed successfully. `accepted` only means the channel accepted/handed off the message according to the channel's semantics.

### Keep Cardinality Low

Metric tags must have a small, stable set of values. You can use `channel_group`, `channel_type`, or `outcome`. Do not use message ID, order ID, email, customer ID, or arbitrary tenant IDs as tags; each new value can create a new time series and overload the metrics backend.

If channels are created dynamically per tenant, do not attach dynamic channel names to metrics. Aggregate by channel group or type instead; use logs/traces to look up a specific message or tenant.

### Measure Timing at the Right Layer

Do not treat the duration around send callbacks as handler processing time for every channel:

| Channel | What send instrumentation typically reflects |
|---|---|
| `DirectChannel` | Synchronous dispatch; may include subscriber/handler time |
| `QueueChannel` | Time to enqueue the message into the queue |
| `ExecutorChannel` | Time to dispatch/submit the task; the handler may run afterward |
| `PublishSubscribeChannel` with executor | Dispatch time per executor and subscriber configuration, not necessarily completion of all branches |

To measure business processing time, instrument endpoints/handlers with Micrometer Observation, timers, or appropriate advice. Before building your own timer in an interceptor, examine callback lifecycles and concurrency; avoid storing `Timer.Sample` by message in a global map just to pair `preSend` with completion, as that increases allocations, synchronization, and risk of state leaks.

## 5. Tracing: Connecting Processing Steps

Distributed tracing connects a single request across multiple endpoints, threads, and services using a trace ID and spans. An interceptor can support tracing by recording the active trace/span ID in logs or adding technical metadata when genuinely needed.

If the application uses Micrometer Tracing, you can read the current span from `Tracer`:

~~~java
public class TraceLoggingInterceptor implements ChannelInterceptor {

    private final Tracer tracer;
    private final Logger log =
            LoggerFactory.getLogger(TraceLoggingInterceptor.class);

    public TraceLoggingInterceptor(Tracer tracer) {
        this.tracer = tracer;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Span span = tracer.currentSpan();
        if (span != null && log.isDebugEnabled()) {
            log.debug("channel={} messageId={} traceId={} spanId={}",
                    channel,
                    message.getHeaders().getId(),
                    span.context().traceId(),
                    span.context().spanId());
        }
        return message;
    }
}
~~~

If there is no current span, the interceptor does not log a trace ID. This is a valid state when a message is not yet part of a trace or when tracing is disabled.

Do not create a new span in every interceptor callback just to get extra logs. `preSend` and `afterSendCompletion` describe the channel send boundary; with `ExecutorChannel` or `QueueChannel`, they do not wrap the entire asynchronous processing. Prefer Observation/tracing instrumentation on endpoints and use context propagation to link spans across executors. When crossing HTTP or brokers, use standard propagators such as W3C Trace Context and configure the corresponding header mappers.

A business Correlation ID does not replace a Trace ID. An order can retain the same Correlation ID across multiple attempts or multiple requests, whereas each execution can create its own trace.

## 6. Distinguishing Logging, Metrics, and Tracing

| Aspect | Logging | Metrics | Tracing |
|---|---|---|---|
| Goal | Record specific events | Measure trends and overall health | Follow the path of a request/message |
| Data | Message ID, channel, errors, whitelisted metadata | Counters, timers, gauges, and low-cardinality tags | Trace ID, span ID, parent-child relationships, and duration |
| Querying | Find a specific event or message | Dashboards, alerts, and time-series comparisons | Open a trace to spot slow or failing spans |
| Where it fits | Interceptors and endpoints | Interceptors for channel outcomes; instrumentation for endpoints/queues | Observation/tracing instrumentation and propagators |

Do not use metrics to store per-message data, do not use payload logs as tracing, and do not use a homegrown trace ID instead of distributed tracing. The three signal types complement one another.

## 7. When Should You Use Built-In Instrumentation?

Before writing a custom interceptor, check whether the Micrometer/Observation instrumentation provided by your Spring Integration and Spring Boot versions already covers that channel or endpoint. Built-in instrumentation understands component lifecycles and avoids manually pairing callbacks with mismatched scopes.

A custom interceptor is appropriate when you need application-specific metadata, specialized logging rules, or outcome metrics not already provided by existing instrumentation. Do not build a parallel tracing layer alongside Micrometer Tracing if the framework already instruments the same operation; doing so can create duplicate spans or break parent-child relationships.

## 8. Cost and Safety on the Hot Path

An interceptor may run for every message. Therefore:

- Keep callbacks short and avoid HTTP/database calls.
- Do not serialize payloads just to log them.
- Do not create metric tags from high-cardinality values.
- Do not use global locks or per-message state maps unless necessary.
- Do not log detailed entries at INFO level for every message on high-throughput channels.
- Register global interceptors only for channel patterns that need observation.
- Measure throughput and p95/p99 latency before and after enabling instrumentation.

If durable auditing is required, write audit events via a dedicated endpoint or outbox. `ChannelInterceptor` is not an audit store, and a send callback does not prove a business transaction committed.

## 9. Diagnosing with Logs, Metrics, and Traces

| Symptom | Data to inspect | Investigation direction |
|---|---|---|
| Message does not reach endpoint | Send logs, accepted/rejected metrics, topology | Does the channel have a subscriber? Did the router select the right output? |
| Send succeeds but business logic fails | Error logs, endpoint traces, error flow | Handler failed after the channel accepted the message |
| `ExecutorChannel` sends fast but processing is slow | Executor queue, worker utilization, handler spans | Separate dispatch latency from handler latency |
| Queue backlog grows | Queue depth, oldest message age, consumer throughput | Slow consumer, stopped poller, or producer exceeding capacity |
| Trace breaks after async boundary | Trace ID before/after executor, context propagation | Check Observation and TaskDecorator/propagator |
| Metric backend cardinality grows | Tag list and number of time series | Remove message/tenant IDs from metric tags |
| Logs contain wrong correlation ID | MDC and thread reuse | Check context propagation and cleanup in `finally` |

An effective investigation workflow is to use metrics to spot an anomalous channel or endpoint group, traces to locate the slow span, and logs by message ID/Correlation ID to examine specific events and exceptions.

## 10. Implementation Checklist

- [ ] Choose a local interceptor scope or a narrow global pattern.
- [ ] Use `preSend` to log essential metadata and `afterSendCompletion` to log exceptions.
- [ ] Use `postSend` to distinguish accepted sends from rejected ones.
- [ ] Never log sensitive payloads or headers.
- [ ] Use low-cardinality metric tags.
- [ ] Measure timing at the right layer: channel dispatch vs. handler processing.
- [ ] Use Micrometer Observation/Tracing for spans and context propagation.
- [ ] Avoid creating spans that duplicate built-in instrumentation.
- [ ] Verify MDC/trace context across `ExecutorChannel`, pollers, and broker adapters.
- [ ] Measure instrumentation overhead under production-like load.

Interceptors are a useful observation point at the channel boundary, but each callback only reveals part of the message lifecycle. By using logs for events, metrics for trends, and tracing for end-to-end paths—while respecting synchronous/asynchronous boundaries—you can observe Spring Integration without mistaking channel acceptance for completed business processing.

## References

- [Spring Framework API: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration Reference: Micrometer Observation](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/)
