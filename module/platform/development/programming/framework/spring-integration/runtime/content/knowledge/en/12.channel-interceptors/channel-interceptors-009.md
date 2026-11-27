# Limiting Interceptor Overhead on the Hot Path

`ChannelInterceptor` is a useful extension point for observing or adjusting messages as they pass through a channel. However, interceptors sit directly on the channel's send/receive path. If a channel processes thousands or millions of messages per minute, every operation inside an interceptor is multiplied by that traffic volume. A single log write, payload serialization, or remote service call can turn a small interceptor into a bottleneck for the entire flow.

Designing an interceptor for the hot path starts with a question: what do we truly need to observe or modify at the channel boundary? Register only within the required scope, choose the minimal callbacks, avoid synchronous I/O, and measure overhead under realistic load.

## 1. Which Boundary Does ChannelInterceptor Run At?

`ChannelInterceptor` belongs to Spring Messaging and is used by `AbstractMessageChannel` to intercept the message send/receive process. An interceptor can observe or modify a message before sending, after sending, or around the receive operation of a pollable channel.

The main callbacks:

| Callback | Timing | When to use |
|---|---|---|
| `preSend` | Before the channel performs the send | Validate metadata, add required headers, or intentionally reject a message |
| `postSend` | After the channel performs the send | Record whether the send succeeded or failed via the `sent` flag |
| `afterSendCompletion` | When the send process finishes, even with an exception | Clean up or record errors after sending |
| `preReceive` | Before a pollable channel receives a message | Decide whether to execute the receive attempt |
| `postReceive` | After the receive operation | Observe the retrieved message; may return a modified message |
| `afterReceiveCompletion` | When receive finishes | Clean up or record receive exceptions |

Not every callback is invoked on every channel type. `preReceive`, `postReceive`, and `afterReceiveCompletion` are meaningful for channels supporting receive, such as `QueueChannel`. With `DirectChannel` or `ExecutorChannel`, the focus is typically on the send path.

An interceptor may be invoked for every message. If there are N interceptors on a channel, a single send may pass through multiple callbacks of each interceptor. Therefore, both the number of interceptors and the cost of each callback affect throughput.

## 2. Separating Channel Cost from Handler Processing Cost

An interceptor measuring time around `send()` does not necessarily measure business processing time.

| Channel | Scope typically wrapped by a send interceptor |
|---|---|
| `DirectChannel` | Synchronous dispatch call, usually including subscriber/handler execution time |
| `ExecutorChannel` | Dispatching or submitting the task to an executor; the handler may run afterward on a worker thread |
| `QueueChannel` | Enqueueing the message into the queue; the consumer retrieves and processes it at another time |
| `PublishSubscribeChannel` with executor | Dispatching to the executor/subscribers per configuration; does not mean all branches have finished processing |

For example, `postSend` on an `ExecutorChannel` may be invoked immediately after the task is accepted by the executor. If you use this duration to report "handler processing time", the metric will underreport actual processing time and lead to wrong conclusions.

To measure handler time, use instrumentation at the endpoint/handler, an `Advice` around the handler method, or an appropriate Observation. Use `ChannelInterceptor` to measure timing and outcomes at the channel boundary: how long sending took, whether the queue accepted the message, or whether receive returned a message.

## 3. Limiting Interceptor Scope

Spring Integration supports registering interceptors directly on a channel or registering global interceptors by channel name patterns. Global interceptors are convenient for shared policies, but overly broad wildcards can impose callback overhead on every channel in the application context.

Example applying an interceptor only to the orders channel group:

~~~java
@Configuration
@EnableIntegration
public class ChannelObservabilityConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*")
    ChannelInterceptor ordersChannelMetrics(MeterRegistry registry) {
        Counter accepted = Counter.builder("si.channel.send.accepted")
                .tag("channel_group", "orders")
                .register(registry);

        Counter rejected = Counter.builder("si.channel.send.rejected")
                .tag("channel_group", "orders")
                .register(registry);

        Counter failed = Counter.builder("si.channel.send.failed")
                .tag("channel_group", "orders")
                .register(registry);

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
}
~~~

The example above illustrates low-cardinality metrics for a fixed channel group. `postSend` distinguishes channel-accepted sends from sends returning `false`; `afterSendCompletion` records exceptions if any. The counters do not attach message IDs, customer IDs, or tenant IDs as tags.

If you only need to observe one channel, registering the interceptor locally on that channel provides a smaller scope. Only use `@GlobalChannelInterceptor` when applying a policy to a clearly named group of channels. Patterns should rely on stable naming conventions, such as `orders*`, `payments*`, or `audit*`.

Do not register a global interceptor with a pattern covering every channel if the task only needs to monitor one branch. Internal channels, control channels, error channels, or high-throughput channels do not necessarily need the same level of observation.

## 4. Choosing Minimal Callbacks

Every additional callback increases method invocations on the hot path. Choose only the callbacks you need:

- Only counting accepted sends: use `postSend` and check `sent`.
- Need to record send exceptions: use `afterSendCompletion`.
- Need to validate or add metadata before sending: use `preSend`.
- Need to observe pollable channel receives: use `postReceive` or the corresponding receive callbacks.
- If receive observation is unnecessary, do not override the receive callbacks.

`preSend` can return `null` to prevent a message from being sent. This is a control behavior, not merely an observation callback. If the goal is filtering messages by business conditions, use a `Filter` endpoint so that logic is visible in the flow with its own discard channel and metrics. Avoid using interceptors as hidden business filters.

Do not construct `MessageBuilder`, copy payloads, or alter headers without a concrete requirement. Messages in Spring Messaging are immutable; creating a new message and copying headers incurs allocation overhead. If metadata needs to be added, do it once at message creation or at a dedicated endpoint rather than repeating it on every channel.

## 5. Avoiding I/O and Heavy Work Inside Interceptors

The following operations are generally unsuitable for the hot path:

| Operation | Why it is costly | Alternative |
|---|---|---|
| HTTP or database calls | Adds network latency, timeouts, and failures to the send path | Move into a dedicated processing endpoint or emit an async event |
| Serializing entire payloads for logging | CPU, allocations, and risk of exposing sensitive data | Log message ID, type, size, or whitelisted metadata fields |
| Writing a log line for every message | Formatting, appenders, and I/O can block threads | Use metric counters; log details via sampling or on errors |
| Complex regex/JSON parsing | Repeated CPU and allocations per message | Parse once at ingress or use normalized metadata |
| Waiting on global locks or `synchronized` | Producers contend on the same lock, reducing parallelism | Avoid shared mutable state; use thread-safe metrics or partitioned state |
| Creating many temporary objects | Increases allocation rate and GC pressure | Keep callbacks short; reuse safe structures when genuinely needed |

Interceptors should avoid blocking calls. A 50 ms remote operation on a channel handling 2,000 messages/second can tie up many threads waiting and cause backlogs to grow rapidly. Moving that work into a dedicated endpoint allows independent concurrency limits, timeouts, retries, and observability.

Do not catch and ignore exceptions just to preserve throughput. Doing so can cause messages to silently lose metadata or metrics to become inconsistent. If an interceptor cannot perform a mandatory function, let the error surface cleanly per the flow's contract or use an intentional fallback.

## 6. Low-Cardinality Metrics

Metrics should answer operational questions without creating millions of time series. Values like message ID, order ID, email, arbitrary tenant IDs, or dynamic URL paths should not be used as metric tags.

Use tags with a small, stable set of values:

- `channel_group`: `orders`, `payments`, `notifications`.
- `channel_type`: `direct`, `queue`, `executor`, `publish_subscribe`.
- `result`: `accepted`, `rejected`, `failed`.
- `environment`: `dev`, `staging`, `prod` if the system already manages this tag at the registry level.

Specific channel names should only be used as tags when the list of channels is finite, controlled in configuration, and free of runtime data. If channels are created dynamically per tenant, tagging by channel name can cause unbounded cardinality growth. In that case, aggregate by channel group or channel type.

Counters suit counting sends/receives/outcomes. Timers suit measuring operation duration. Gauges suit current state such as queue depth. Do not use metrics as a substitute for per-message detail logs; use message ID/Correlation ID in logs or traces when looking up a specific transaction.

## 7. Selective Logging

When logging metadata is necessary, keep messages brief and check the log level before formatting strings. Example:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (log.isTraceEnabled()) {
        log.trace("channel={}, messageId={}",
                channel, message.getHeaders().getId());
    }
    return message;
}
~~~

Do not log entire payloads or all headers. Headers can contain tokens, personal data, large objects, or internal metadata. Log only whitelisted fields and comply with data masking policies.

In production, you can enable trace logging briefly to investigate a specific flow, but restrict it by package/channel and turn it off once finished. If sampling is needed, choose an explicit sampling rate or condition; avoid random generation or expensive computation on every message when simple metrics suffice.

## 8. Avoid Holding Per-Message State in Interceptors

Do not use a global `HashMap` to store message IDs and timestamps in `preSend` and wait for `postSend` to remove them. This can introduce race conditions, memory leaks when callbacks do not execute as expected, and synchronization overhead.

In particular, an interceptor must not assume one send always corresponds to one handler execution. With `ExecutorChannel`, the send callback finishes after dispatching the task; the handler completes later on a worker. To measure end-to-end handler time, measure at the handler/observation scope rather than stitching two channel callbacks into a business processing lifecycle.

If temporary state is needed during a synchronous send, account for nested sends, multiple threads, and all exception paths. Usually, built-in metrics or endpoint-level instrumentation is simpler and safer than managing per-message maps yourself.

## 9. Interceptors Do Not Replace Business Endpoints

Certain responsibilities do not belong in an interceptor:

| Requirement | More appropriate mechanism |
|---|---|
| Filtering messages by business rules | `Filter` endpoint |
| Routing messages to another channel by headers | Router endpoint |
| Transforming payloads | Transformer endpoint |
| Calling services or writing to databases | Service Activator |
| Retrying operations with side effects | Retry advice around handler/service with proper idempotency |
| Measuring business processing duration | Handler advice, Micrometer Observation, or service instrumentation |
| Durable audit events | Dedicated audit/outbox service or storage |

Interceptors fit cross-cutting concerns at the channel boundary, such as checking technical metadata, send/receive metrics, trace/log metadata, or simple access checks. When logic requires independent configuration, retries, transactions, or error flows, dedicated endpoints make the flow easier to read and operate.

## 10. Measuring Interceptor Overhead

Do not assume an interceptor is lightweight just because its callback is only a few lines of code. Measure on the real path with production-like message sizes and concurrency.

Measurement steps:

1. **Baseline:** run the flow with the same channels and handlers but without the interceptor; record throughput, p50/p95/p99 latency, CPU, allocation rate, and GC.
2. **Minimal single interceptor:** add only the essential counter or callback; re-measure under the same load.
3. **Incremental additions:** enable features one at a time, such as logging, header inspection, or timers; do not enable everything at once.
4. **Compare channels:** measure `DirectChannel`, `ExecutorChannel`, and `QueueChannel` separately because their send paths cover different scopes.
5. **Test under high load:** increase concurrency and message size, observing lock contention, executor queues, and rejected tasks.
6. **Evaluate tail latency:** an interceptor may add only a few microseconds on average while spiking p99 sharply when a log appender or remote call blocks.

For microbenchmarks, JMH can measure individual callbacks or metadata processing. For end-to-end evaluation, run load tests with warm-up, sufficient duration, matching JVM flags, and realistic downstream behavior. Never use a single unit test run as a conclusion about production performance.

## 11. Diagnosing an Interceptor Bottleneck

| Symptom | Possible causes | Investigation direction |
|---|---|---|
| Throughput drops noticeably after enabling interceptor | Callback runs on every message or too many interceptors | Disable interceptors one by one, re-measure, and narrow patterns |
| p99 increases while CPU remains low | Blocking log appender, network, or lock | Thread dumps, profiler, and I/O/lock wait times |
| CPU and allocations increase | Payload serialization, regex, object creation, or log formatting | Allocation profiling and eliminating repeated work |
| Metric backend time series count grows | Tag contains dynamic IDs/tenants/channels | Check cardinality and switch to fixed group tags |
| `ExecutorChannel` sends fast but handler is slow | Interceptor only measures dispatch | Measure at handler and executor queue as well |
| Messages rejected unexpectedly | `preSend` returns `null` or callback modifies message improperly | Inspect interceptor chain and log send outcomes |
| Logs contain sensitive payloads | Interceptor dumps full message | Whitelist metadata and mask data |

When profiling, determine whether time is spent in `preSend`, `postSend`, `afterSendCompletion`, the dispatcher, or the handler. Looking only at total producer latency makes it hard to separate interceptor overhead from downstream duration.

## 12. Hot-Path Checklist

- [ ] Register interceptors only on channels that need observation or control.
- [ ] Use global interceptors with narrow patterns and stable channel names.
- [ ] Choose minimal callbacks; do not override callbacks just to leave them empty.
- [ ] Keep callbacks short, non-blocking, and free of database/HTTP calls.
- [ ] Never serialize or log full payloads/headers.
- [ ] Do not allocate objects or copy messages unnecessarily.
- [ ] Never use message IDs, customer IDs, or arbitrary tenants as metric tags.
- [ ] Never hold global per-message state inside interceptors.
- [ ] Distinguish send/dispatch latency from handler processing latency.
- [ ] Use endpoints for filters, routers, transformers, and business logic.
- [ ] Measure baseline and tail latency before and after adding interceptors.
- [ ] Test exceptions, `preSend` returning `null`, and cleanup across all termination paths.

A well-designed hot-path interceptor does very little work: reading a few essential metadata fields, updating low-cardinality metrics, or attaching small technical attributes. Narrow scope and short callbacks keep channels focused on moving messages, while detailed logging, I/O, and business processing happen where they can be bounded and observed independently.

## References

- [Spring Framework API: ChannelInterceptor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration Reference: Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration API: GlobalChannelInterceptor](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)
