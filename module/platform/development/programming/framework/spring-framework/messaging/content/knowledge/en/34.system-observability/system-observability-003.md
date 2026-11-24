# Monitoring Connections, Sessions, Subscriptions, and Consumers

In a messaging system, an open connection does not guarantee messages are flowing; an existing subscription does not guarantee it is receiving data; and a live consumer does not guarantee it is keeping up with incoming messages. To observe properly, you need to separate the lifecycles of transport connections, protocol sessions, streams/subscriptions, message processing, and broker-side queues.

Spring provides several observability layers through Micrometer, Spring Boot Actuator, Spring Integration, and RSocket callbacks. Some metrics are recorded automatically when the right dependencies and configuration are present; application-specific states such as active RSocket sessions, open streams, or consumer lag must be instrumented where the application actually sees those lifecycles.

## 1. Distinguishing Connections, Sessions, Subscriptions, and Consumers

These concepts are related but cannot be used interchangeably.

| Concept | Meaning | Operational questions to answer |
|---|---|---|
| Transport connection | Physical or logical transport channel such as TCP, WebSocket, or broker connection | How many connections are open? Are connections closing or being recreated frequently? |
| Protocol session | Protocol state tied to a connection or maintained across resume | Is the session still valid? Did resume succeed or get rejected? |
| Subscription / stream | A Reactive Streams flow or RSocket interaction actively receiving data | How many streams are running? Did streams complete, error, or get cancelled? |
| Consumer | Component receiving and processing messages, e.g. MessageHandler, @JmsListener, or subscriber | How many messages is the consumer processing? What are its latency, error rate, and backlog? |
| Queue / backlog | Messages waiting for a consumer or awaiting acknowledgement | Is the queue growing continuously? How long has the oldest message been waiting? |

### 1.1. One connection can carry multiple streams

RSocket supports multiplexing and interaction models such as request-response, request-stream, request-channel, and fire-and-forget. A single transport connection can carry many independent requests/streams. Therefore:

- The number of TCP/WebSocket connections is not the number of active streams.
- One session can have multiple concurrent subscriptions or requests.
- One stream can emit many messages.
- An open connection does not prove that a consumer is processing data.
- When a connection drops, the session can be resumed if both sides retain sufficient state and the implementation supports it.

In RSocket, backpressure propagates across the network boundary. The requester controls demand, and the responder must respect that demand. When a stream stops making progress, check the emitter, receiver, demand, and processing resources rather than looking only at socket state.

### 1.2. Distinguishing RSocket sessions and JMS Sessions

In RSocket, session usually refers to the state of a protocol connection and its resume capability. In Jakarta JMS, Session is an API object that manages creating messages, producers, consumers, and transactions/acknowledgments according to configuration. The two concepts have different lifecycles and semantics.

When naming metrics, use clear names such as rsocket.connection.active, rsocket.session.active, or jms.listener.process to avoid conflating layers.

## 2. Metrics, Logs, and Distributed Tracing

The three observability signals complement one another:

- **Metrics** show overall trends: connection counts, throughput, latency, error rates, queue depth, and resource utilization. Used for dashboards, alerts, and SLO tracking.
- **Logs** record specific events: why a connection closed, which message was rejected, which consumer threw an exception. Use correlation IDs or message IDs to find a specific processing flow.
- **Distributed traces** connect processing steps of a message across producers, brokers, consumers, and downstream services. Traces help identify where time is being spent.

Micrometer Observation provides a single API to instrument an operation once, after which ObservationHandlers can emit metrics and traces. An Observation can record timing, error state, and contextual attributes.

Commonly used meters:

| Meter | Used to measure | Examples |
|---|---|---|
| Counter | Cumulative event counts | Successful messages processed, connections opened, error counts |
| Gauge | Value at observation time | Current connections, active subscriptions, queue size |
| Timer | Duration and count of completed operations | Time to publish or process a message |
| LongTaskTimer | Duration and count of still-running operations | Long-lived streams or in-progress consumer tasks |
| DistributionSummary | Distribution of a numeric value | Payload size, batch size, messages per batch |

Counters generally increase monotonically over a process lifetime. Gauges can go up and down. Timers store both count and time distribution; when monitoring latency, look at percentiles/histograms or SLO buckets rather than only averages.

## 3. Metrics to Track at Each Layer

### 3.1. Transport connection

Track:

- Number of open connections.
- Total connections opened and closed over a time window.
- Connection lifetime.
- Number of reconnects, connect timeouts, and handshake failures.
- Disconnect counts grouped by cause.
- Rate of abnormal connection closures.
- Number of pending or establishing connections if the transport exposes it.

A dashboard showing only current active connections can miss constant reconnecting. Pair an active connection gauge with opened/closed counters and a connection lifetime timer. If active connections are steady while opened/closed counts climb rapidly, the system may be churning connections.

For connection pools or broker clients, also track connections in use, idle connections, requests waiting for a connection, and connection acquisition wait time. Do not merge pool connections with logical sessions at the messaging layer.

### 3.2. Protocol session

For RSocket, track:

- Number of active logical sessions.
- Number of newly established sessions.
- Number of successful and failed resumes.
- Number of expired or rejected sessions.
- Session age and reconnect count per session.
- Keepalive timeouts or protocol errors if the implementation exposes them.

Resume is a mechanism for preserving protocol state across temporary transport interruptions. If a new connection resumes an old session, do not count it as an entirely new logical session. Maintain an internal session identifier to distinguish connection generations from logical sessions, but do not put per-session identifiers into metric tags.

### 3.3. Subscription and stream

Track:

- Number of active subscriptions.
- Number of subscriptions created, completed, errored, and cancelled.
- Subscription lifetime.
- Time from subscribe to the first element.
- Number of messages emitted and messages processed.
- Number of streams emitting no data for an extended period.
- Demand/backpressure, internal buffers, or queues if the implementation can measure them.
- Number of streams aborted when connections close or consumers stop.

For RSocket request-stream and request-channel, distinguish an open stream from messages actively flowing. A subscription can stay alive for a long time without new messages because the producer is idle, the requester has not requested more demand, or the source is backpressured.

### 3.4. Consumer and message processing

On the consumer side, track:

- Messages received and messages finished processing.
- Processing duration and wait time before processing begins.
- Error counts grouped by cause.
- Redeliveries, retries, acknowledgements, and rejects if provided by the broker.
- Messages routed to a dead-letter queue (DLQ).
- Number of active consumers and actual concurrency.
- Queue depth, oldest message age, and consumer lag.
- Batch size, messages per poll, and empty poll counts.

Do not count only received messages. A message that is received but not yet processed, failed during processing, or not yet ACKed has different states. Define the exact point where each counter is incremented.

### 3.5. Executors and processing resources

Asynchronous consumers often depend on executors or schedulers. Track:

- Active threads and pool size.
- Queue size and remaining capacity.
- Number of rejected tasks.
- Time tasks spend waiting in the queue.
- Task execution duration.
- CPU, heap, garbage collection, and thread utilization.

If the executor queue grows while active threads stay maxed out, the consumer may lack concurrency or handlers may be slow. If tasks are rejected, check queue capacity and the rejection policy.

## 4. What Spring Already Instruments Out of the Box

Not every Spring Messaging application gets the same set of metrics automatically. Observability depends on modules, component types, dependencies, and configuration.

### 4.1. Spring Framework Observation for JMS

Spring Framework integrates Micrometer's Jakarta JMS instrumentation when the io.micrometer:micrometer-jakarta9 dependency is on the classpath. The two primary observations are:

- jms.message.publish: time to send a message to a destination, typically via JmsTemplate.
- jms.message.process: time for the application to process a received message, typically via MessageListener or @JmsListener methods.

There is currently no default jms.message.receive observation to measure time spent waiting to receive a message. Processing duration is measured separately after the message has been received.

JMS observations include low-cardinality keys such as error, messaging.destination.temporary, and messaging.operation. Conversation ID, destination name, and message ID are high-cardinality keys; they belong in traces rather than metric tags.

### 4.2. Configuring ObservationRegistry for JMS

For manually created JmsTemplates, set ObservationRegistry on the template. For listener containers, configure the registry on the DefaultJmsListenerContainerFactory used by @JmsListener.

~~~java
import io.micrometer.observation.ObservationRegistry;
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;

@Configuration
class JmsObservabilityConfiguration {

    @Bean
    JmsTemplate observedJmsTemplate(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setObservationRegistry(observationRegistry);
        return template;
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory,
            ObservationRegistry observationRegistry) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setObservationRegistry(observationRegistry);
        return factory;
    }
}
~~~

This is a sample configuration for applications declaring JMS beans manually. In Spring Boot, JmsTemplate beans and @JmsListener methods support auto-instrumentation when the required dependencies and configuration are present. If an application has multiple listener container factories, confirm each @JmsListener references the properly configured factory.

### 4.3. Spring Boot Actuator and Micrometer

Spring Boot auto-configures MeterRegistry and the corresponding registry exporter when dependencies are declared. Commonly available instrumentation includes:

- JVM metrics: memory, buffer pools, garbage collection, and thread utilization.
- System/process metrics: CPU, file descriptors, uptime, and disk.
- ThreadPoolTaskExecutor and ThreadPoolTaskScheduler metrics when an underlying ThreadPoolExecutor is available.
- JMS metrics for JmsTemplate and @JmsListener.
- Other instrumentation such as HTTP client/server and datasources depending on the stack.

The /actuator/metrics endpoint is for inspecting registered meters and viewing current values. It is a diagnostic tool, not a metrics backend to scrape in production. Export metrics to Prometheus or your chosen registry/backend. When using the Prometheus registry, you can expose the Prometheus endpoint via Actuator configuration and secure it according to your system's access policy.

### 4.4. Spring Integration metrics for channels and handlers

When Spring Integration has a MeterRegistry, common components extending AbstractMessageChannel, AbstractMessageHandler, and AbstractMessageSource are automatically instrumented.

Commonly encountered meters:

| Meter | Component | Meaning |
|---|---|---|
| spring.integration.send | MessageChannel | Send duration, tagged with type=channel |
| spring.integration.receive | Pollable MessageChannel | Receive count and outcome |
| spring.integration.send | MessageHandler | Handler processing duration, tagged with type=handler |
| spring.integration.receive | MessageSource | Number of messages provided by the source |
| spring.integration.channels | Gauge | Number of MessageChannels in the application |
| spring.integration.handlers | Gauge | Number of MessageHandlers in the application |
| spring.integration.sources | Gauge | Number of MessageSources in the application |
| spring.integration.channel.queue.size | Gauge | How many messages are currently in a QueueChannel |
| spring.integration.channel.queue.remaining.capacity | Gauge | How much capacity remains in a QueueChannel |

Channel/handler metrics usually carry tags name for the component name, result for success/failure, and exception for none or the exception class name. For QueueChannel, steadily increasing queue size and falling remaining capacity indicate the consumer is not keeping up with the producer.

The metrics above belong to Spring Integration and its supported components; do not assume every custom MessageChannel in spring-messaging automatically registers these meters.

## 5. Observing RSocket Connections, Sessions, and Streams

Spring Framework provides RSocketRequester, RSocketMessageHandler, @MessageMapping, and @ConnectMapping. RSocket supports asynchronous interaction models and backpressure, but applications must choose the right instrumentation points to measure connection and stream lifecycles.

### 5.1. Tracking connection setup

@ConnectMapping handles the SETUP frame at the start of an RSocket connection as well as subsequent METADATA_PUSH frames. Therefore, it is a connection-level callback, not a per-message request callback. If you use it to record connections, you must distinguish initial setup from metadata pushes so you do not increment the connection count multiple times.

If using Spring Integration RSocket, ServerRSocketConnector emits RSocketConnectedEvent when a client connects. The connector can also retain client RSocketRequesters in a registry keyed by a configured clientRSocketKeyStrategy. This event is useful for recording established connections and associating them with logical clients.

RSocketConnectedEvent is a connection signal. To maintain an accurate active connection gauge, attach corresponding handling to the RSocket or transport close/dispose lifecycle to decrement the gauge when the connection ends. Do not maintain an active gauge solely by incrementing on connect events without a decrement path on close.

### 5.2. Separating connection generations and logical sessions

With Resume, a logical session can survive transport connection replacements. Design separate metrics:

- rsocket.connections.active: number of open transport connections.
- rsocket.connections.opened: total connections established.
- rsocket.connections.closed: total connections closed.
- rsocket.sessions.active: number of active logical sessions.
- rsocket.sessions.resumed: number of successful resumes.
- rsocket.sessions.resume.failed: number of failed resumes.
- rsocket.sessions.expired: number of expired sessions.

The names above are application-defined metrics, not Spring default meter names. Update the session gauge according to logical state and avoid counting a resume as a new session when an existing session is restored.

### 5.3. Tracking subscriptions and streams

On the requester side, each subscription to a Flux can initiate a request stream or a data consumption flow. You can use Flux.defer to increment active subscriptions upon real subscription and doFinally to decrement when the stream completes, errors, or is cancelled.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

final class RSocketSubscriptionMetrics {

    private final MeterRegistry registry;
    private final AtomicInteger active = new AtomicInteger();

    private final Counter received;
    private final Counter completed;
    private final Counter failed;
    private final Counter cancelled;
    private final Timer duration;

    RSocketSubscriptionMetrics(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder(
                "app.rsocket.subscriptions.active",
                this.active,
                AtomicInteger::get)
            .description("Active RSocket stream subscriptions")
            .register(registry);

        this.received = Counter.builder("app.rsocket.subscription.messages")
                .tag("transport", "rsocket")
                .register(registry);

        this.completed = Counter.builder("app.rsocket.subscription.completed")
                .tag("transport", "rsocket")
                .register(registry);

        this.failed = Counter.builder("app.rsocket.subscription.failed")
                .tag("transport", "rsocket")
                .register(registry);

        this.cancelled = Counter.builder("app.rsocket.subscription.cancelled")
                .tag("transport", "rsocket")
                .register(registry);

        this.duration = Timer.builder("app.rsocket.subscription.duration")
                .tag("transport", "rsocket")
                .register(registry);
    }

    Flux<String> observe(Flux<String> source) {
        return Flux.defer(() -> {
            this.active.incrementAndGet();
            Timer.Sample sample = Timer.start(this.registry);

            return source
                    .doOnNext(item -> this.received.increment())
                    .doFinally(signal -> {
                        this.active.decrementAndGet();
                        sample.stop(this.duration);

                        if (signal == SignalType.ON_COMPLETE) {
                            this.completed.increment();
                        }
                        else if (signal == SignalType.ON_ERROR) {
                            this.failed.increment();
                        }
                        else if (signal == SignalType.CANCEL) {
                            this.cancelled.increment();
                        }
                    });
        });
    }
}
~~~

This component illustrates application-level subscription tracking; it does not automatically measure every stream in an RSocket server. Call observe() where the Flux is created or returned to the requester. Flux.defer ensures active increments only when an actual subscription occurs; doFinally runs on complete, error, or cancel so active is decremented exactly once per subscription.

If a Flux is subscribed to multiple times, each subscription is independent and measured separately. Consider cold/hot publisher semantics so you do not accidentally create extra subscribers just for instrumentation.

### 5.4. Backpressure and stalled streams

RSocket uses Reactive Streams demand. The requester can ask for more messages; the responder must respect demand. When a stream stalls, monitor:

- Active subscription count and subscription age.
- Messages emitted and messages finished processing.
- Time from subscribe to the first element.
- Demand/requested amount if instrumentable at the publisher or protocol layer.
- Buffer sizes, queue depth, and executor saturation.
- Cancellation counts and terminal signals.

A long-lived active subscription is not necessarily an error: an event stream may be designed to stay open continuously. Combine subscription age with idle time without messages, expected heartbeats, demand, and the route's SLO to detect stuck streams.

## 6. Cardinality: Never Put Per-Message Identifiers in Metric Tags

A metric can generate many time series if a tag accepts too many values. This is the cardinality problem.

Typically low-cardinality tags:

- application, environment, region.
- transport: tcp, websocket, jms.
- interaction: request-response, request-stream, request-channel, fire-and-forget.
- outcome: success, error, cancelled.
- error.category: timeout, unavailable, validation, authentication.
- consumer group or destination template if the count is bounded.

Typically high-cardinality values:

- Individual sessionId, connectionId, clientId.
- messageId, correlationId, traceId.
- userId, email, or tenantId if the count is large.
- URLs/paths containing dynamic values.
- Timestamps or payload values.

Putting per-message or per-session IDs into metric tags can create hundreds of thousands or millions of time series, driving up memory, storage, and query costs. Keep these IDs in logs or traces. Metrics use finite groups to answer aggregate questions.

With Micrometer Observation, low-cardinality key values go into metrics; high-cardinality key values belong in traces. This is an intentional separation to keep metrics stable.

## 7. Propagating Tracing Context Across Messages

A request often crosses multiple threads and may pass through brokers or other services. If tracing context is not propagated in message headers, traces break into disconnected fragments.

Spring Integration provides observation propagation on channels and consumers. When observation is enabled on both channel and consumer, tracing data is written into message headers before the message moves to a consumer thread or store; the consumer restores that data to create a child Observation.

For JMS, publish observations can propagate tracing information via message headers, and process observations on listeners restore context for message processing. For other adapters or custom channels, verify the actual observation propagation configuration.

A useful trace should show:
1. Producer creates and sends the message.
2. Broker receives and holds the message.
3. Consumer receives the message.
4. Consumer starts processing.
5. Downstream calls during processing.
6. Consumer completes, errors, or ACKs/rejects.

Do not use traces as a replacement for metrics. Traces help find the cause of one slow message; metrics show whether the proportion of slow messages is rising system-wide.

## 8. Dashboards and Alerting

An operational dashboard can be divided into these groups:

| Group | Charts to include | Signs requiring investigation |
|---|---|---|
| Connection | Active, opened/closed rate, reconnects, lifetime | Connection churn, reconnect spikes, sudden active drop |
| Session | Active sessions, resume success/failure, expired | Rising resume failures, premature session expirations |
| Subscription | Active streams, started/completed/error/cancel, duration | Active streams growing without emitting data |
| Consumer | Process rate, processing latency, error rate, redelivery | Falling throughput, rising latency, rising DLQ |
| Backlog | Queue depth, oldest message age, consumer lag | Continuously growing queue or messages waiting too long |
| Executor | Active threads, pool size, queue size, rejected tasks | Worker saturation, rejected tasks |
| JVM/process | Heap, GC pauses, CPU, threads, uptime | Resource pressure coinciding with processing degradation |

Alerts should be based on SLOs and baseline system behavior rather than one fixed threshold for all applications. Examples:

- Queue age exceeds the processing target across a sustained window.
- Consumer error rate or DLQ rate exceeds threshold.
- Active connections drop abnormally while request rate stays high.
- Reconnect/resume failures spike suddenly.
- Executor queue grows continuously and rejected tasks appear.
- Subscriptions stay open longer than business limits or show no progress despite demand.

Do not alert solely because active subscriptions are high if the system is designed for long-lived streams. Compare against baselines, incoming load, and actual messages processed.

## 9. Symptom-Based Diagnostics

### 9.1. Active connections steady but message throughput is zero

Check whether subscriptions are still active, consumers are registered on the right routes, publishers are still emitting data, and requesters are supplying demand. With RSocket, a live connection does not mean streams are making progress.

### 9.2. Connections opened/closed climbing rapidly

Check network resets, load balancer timeouts, keepalive settings, connection pools, broker restarts, and retry policies. Correlate logs by timestamp and transport endpoint to pinpoint the cause. Do not put individual connection IDs into metric tags.

### 9.3. Active subscriptions rising while completions drop

Long-lived streams may be normal by design, or streams may be hung. Check subscription age, time since last item, demand, backpressure, cancellation, and resource cleanup. If a stream errors without terminating, check whether the publisher holds the subscription without emitting a terminal signal.

### 9.4. Consumer lag or queue age rising

Compare incoming rate with processed rate. Check concurrency, executor queues, processing duration, downstream latency, redeliveries, and repeated errors. If consumers are slow due to a downstream dependency, adding more workers can overload that dependency further.

### 9.5. JMS publish looks healthy while processing is slow

Compare jms.message.publish with jms.message.process and broker metrics for queue depth/oldest message age. The publish timer measures send time; the process timer measures processing time inside the application. Time spent sitting in the broker requires broker-side metrics or application-recorded enqueue/receive timestamps.

### 9.6. Active connection metric does not drop after client disconnects

Check whether close/dispose signals are wired to the gauge decrement code. Ensure each connection decrements at most once, even when both close and error callbacks fire. Use a handle with an atomic flag to avoid double decrements.

## 10. Testing Instrumentation

Instrumentation needs testing just like application logic.

- Opening a connection increments the opened counter and increases the active gauge by one.
- Closing a connection increments the closed counter and decreases the active gauge by one.
- Repeated close callbacks do not drive the active gauge negative.
- Resuming the same logical session is not miscounted as a new session.
- Each actual subscription increments active exactly once.
- Complete, error, and cancel all decrement active.
- Message counters increment only when items actually flow through the subscription.
- Consumer processing timers stop both when the handler succeeds and when it throws an exception.
- Metric tags only use finite values.
- Trace context propagates across executors/channels and consumer threads.
- When ApplicationContext closes, listener containers, connections, and executors are released.

You can use SimpleMeterRegistry to verify meters in unit tests. With reactive streams, StepVerifier helps verify complete/error/cancel and inspect gauges/counters after the stream terminates. With a real broker, use integration tests to confirm ACKs, redeliveries, queue depth, and consumer lifecycle.

## 11. Production Deployment Checklist

- [ ] Clearly define connection, logical session, stream/subscription, and consumer.
- [ ] Track active connections alongside opened/closed rates and lifetime.
- [ ] Track session resumes, timeouts, and expirations if using RSocket Resume.
- [ ] Track subscription start, active, complete, error, cancel, and duration.
- [ ] Track consumer throughput, processing latency, failures, redeliveries, and DLQ.
- [ ] Track queue depth, oldest message age, and consumer lag from the broker or corresponding adapter.
- [ ] Enable Spring Boot Actuator/Micrometer and configure an exporter to the metrics backend.
- [ ] Enable ObservationRegistry for JMS templates and listener containers where instrumentation is needed.
- [ ] Enable Spring Integration metrics for channels/handlers/sources when using those components.
- [ ] Instrument RSocket lifecycle at the connector/transport and do not confuse connect callbacks with disconnect callbacks.
- [ ] Propagate tracing context across message headers, channels, and consumers.
- [ ] Do not put sessionId, connectionId, messageId, or traceId into metric tags.
- [ ] Set dashboards and alerts based on SLOs, backlog, and processing progress.
- [ ] Test repeated close, resume, stream cancellation, consumer failures, and cleanup.

## References

- Spring Framework Reference — Observability Support, JMS messaging instrumentation: https://docs.spring.io/spring-framework/reference/integration/observability.html
- Spring Framework Reference — RSocket, interaction models and @ConnectMapping: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot Reference — Actuator Metrics, JMS metrics and task executor metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Integration Reference — Metrics and Management, channel/handler/source meters and QueueChannel gauges: https://docs.spring.io/spring-integration/reference/metrics.html
- Spring Integration Reference — RSocket Support, RSocketConnectedEvent and requester registry: https://docs.spring.io/spring-integration/reference/rsocket.html
- Micrometer Reference — Observation Components, ObservationHandler and low/high cardinality: https://docs.micrometer.io/micrometer/reference/observation/components.html
