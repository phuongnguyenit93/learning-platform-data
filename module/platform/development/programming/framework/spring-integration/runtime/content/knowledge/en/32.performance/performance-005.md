# Message history, logging, and observability cost

When a message passes through multiple Spring Integration <code>MessageChannel</code>s, consumer endpoints, transformers, routers, pollers, executors, and handlers, a failure can surface far from its origin. Operators want to answer: *where did the message travel, where did it sit waiting, which handler ran slowly, and did the error occur before or after transaction commit?* That information is immensely valuable, yet recording the full path or logging every message also consumes CPU, heap, I/O, and observability system resources.

This lesson belongs to the **Performance** chapter of the **SPRING_INTEGRATION_RUNTIME** module. The focus is on **message history**, **logging**, and **observability cost** in the Spring Integration runtime: how to enable them selectively, read the data accurately, understand their impact on throughput/latency/GC, check async/transaction boundaries, and design measurements before locking in production settings.

> **Principle:** Observability must serve a clear operational question. Do not enable history for every component, log full payloads, and emit spans at every hop by default merely because the framework supports it. One log line or one history entry can look cheap in a unit test yet become expensive across dozens of hops under high traffic.

## 1. Distinguishing four observability layers

| Mechanism | Data provided | Where data is held | Primary cost |
|---|---|---|---|
| <code>MessageHistory</code> | Name, component type, and timestamp of tracked hops | Inside **each message's headers** | Increases message size, memory, serialization, copying across branches |
| Framework debug logging | Runtime events in channels/dispatchers/handlers | Logging backend, appenders, log collectors | Log-level checks, formatting/toString, appender queues, disk/network I/O |
| <code>LoggingHandler</code>, DSL <code>.log()</code>, <code>WireTap</code> | Message content or selected fields | Log lines or separate tap branch | Interceptors, formatting, sync/async overhead, payload and sensitive data |
| Micrometer metrics / Observation / tracing | Timers, counters, outcomes, spans, trace context | Meter registry/tracer and export pipeline | Recording, timers, span creation, context propagation, cardinality, export |

These mechanisms **complement but do not replace one another**:

- **History** answers “which tracked components did the message pass through?” but does not by itself prove a transaction committed.
- **Logs** answer “what did a component report at that moment?” but can drop or reorder lines under async appenders or sampling.
- **Metrics** answer “what are the error rate, p95 latency, throughput, and backlog?” but do not show the full path of one specific message.
- **Traces** link intervals across multiple operations and threads/processes when propagation is configured; they are not durable audit records on their own.

~~~mermaid
flowchart LR
    S["Inbound adapter"] --> C["orders.in"]
    C --> V["Validate handler"]
    V --> X["ExecutorChannel"]
    X --> D["JDBC/HTTP handler"]
    D --> O["orders.out"]
    H["MessageHistory header"] -. "hop name/type/time" .-> C
    H -. "hop name/type/time" .-> V
    H -. "hop name/type/time" .-> X
    L["Logs"] -. "event/error" .-> D
    M["Metrics / tracing"] -. "timers/spans" .-> D
~~~

When `ExecutorChannel` hands work off to another worker, message history can still travel with the headers, whereas `ThreadLocal` state such as MDC or a JDBC transaction on the sender thread does **not** follow automatically.

## 2. What does message history store?

Spring Integration implements the **Message History** pattern: the framework adds a header named <code>MessageHistory.HEADER_NAME</code> (typically <code>history</code>) to messages passing through tracked components. Each entry usually contains:

~~~text
[
  {name=orders.input, type=channel, timestamp=...},
  {name=orders.validate, type=service-activator, timestamp=...},
  {name=orders.output, type=channel, timestamp=...}
]
~~~

This is an **illustrative** representation: actual names and component types depend on DSL, bean IDs, and endpoint types. History only records components that are named/have an ID and match the configured patterns; not every Java method or every hop in a flow necessarily gets an entry.

This information is useful to:

1. Verify whether a message reached <code>orders.validate</code> or took another router branch.
2. Investigate at which point a message crossed from <code>DirectChannel</code> into <code>ExecutorChannel</code>.
3. Compare the path of a successful message against a failed message.
4. Detect a message revisiting the same component in a routing loop.
5. Enrich diagnostics in an <code>ErrorMessage</code> when the failed/original message still retains its headers.

**Do not uncritically derive absolute latency from two history timestamps.** A timestamp marks when the component was recorded, not necessarily the exact handler start/end time; it misses parts of queue waits and is subject to clock/resolution effects. For reliable duration measurements, use timers/observations and dedicated queue-lag metrics.

### Reading MessageHistory from a message

~~~java
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import java.util.Properties;

public static void showHistory(Message<?> message) {
    MessageHistory history = MessageHistory.read(message);
    if (history == null) {
        System.out.println("History is not enabled or message has not crossed a tracked component");
        return;
    }

    for (Properties hop : history) {
        System.out.printf("component=%s, type=%s, timestamp=%s%n",
            hop.getProperty(MessageHistory.NAME_PROPERTY),
            hop.getProperty(MessageHistory.TYPE_PROPERTY),
            hop.getProperty(MessageHistory.TIMESTAMP_PROPERTY));
    }
}
~~~

<code>MessageHistory.read(message)</code> returns <code>null</code> if the header does not exist. History is investigative metadata **attached to the message**, not a centralized audit table or trace store. If a message is evicted from a queue/store or headers are stripped by a header mapper, that history information can disappear too.

## 3. Enabling history for the right components

Spring Integration provides <code>@EnableMessageHistory</code> from package <code>org.springframework.integration.config</code>. Declared without patterns, it tracks all **trackable named components**:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class FullHistoryForLocalDebug {
}
~~~

In production, start with key channels/handlers instead of using the configuration above. For example:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
    "orders.input",
    "orders.validate",
    "orders.payment*",
    "orders.output"
})
public class TargetedHistoryConfig {
}
~~~

Patterns can be exact names or strings with <code>*</code> wildcards. In the example above, the names must **match actual component names** in the Spring context, not Java variable names. If an endpoint receives an auto-generated ID, assign a stable ID or inspect runtime metadata before writing patterns.

A single <code>@EnableMessageHistory</code> configuration source per application context is easiest to manage; do not declare multiple configurers with conflicting patterns. <code>MessageHistoryConfigurer</code> is registered by the framework from the annotation. Do not manually define a generic configurer bean just as a shortcut to turn on history.

### Why is “history enabled yet the header is empty”?

| Scenario | What to check |
|---|---|
| No <code>history</code> header | History is not enabled, the configurer was stopped, or the message has not passed a matching named component |
| Pattern <code>orders.*</code> lacks expected entries | DSL-generated bean/managed component name differs from expected name |
| New message after converter lacks history | Header mapper, custom <code>MessageBuilder</code>, transport mapping, or manual message creation dropped headers |
| Messages in one router branch have different history from another | Each branch crosses different components; history must be interpreted per branch |
| History grows abnormally | Message loops through the same flow, retries/resubscribes, or too many tracked hops |

**Do not treat history as an exactly-once processing guarantee.** A redelivery may carry prior history, lose history, or gain new hops depending on the transport and how messages are reconstructed. Idempotency must rely on a business event ID and an appropriate durable store.

## 4. Java DSL example with history, selective logging, and verifiable output

Illustrative example using Java 17+ and Spring Integration 6.x. The flow receives an order, logs **only essential metadata**, calls a service, and sends the reply to a <code>QueueChannel</code> so a test can read it.

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record OrderResult(String orderId, String status) {}

public class OrderService {
    public OrderResult process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}
~~~

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({"orders.*"})
@EnableIntegrationManagement(defaultLoggingEnabled = "false")
public class OrderHistoryFlowConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean(name = "orders.output")
    QueueChannel ordersOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .log(LoggingHandler.Level.DEBUG, "orders.path", message ->
                "messageId=" + message.getHeaders().getId()
                + ", correlationId=" + message.getHeaders().get("correlationId"))
            .handle(service, "process",
                endpoint -> endpoint.id("orders.process"))
            .channel("orders.output")
            .get();
    }
}
~~~

Key imports:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

**Why is this configuration worth studying?**

- <code>@EnableMessageHistory({"orders.*"})</code> narrows tracking to named components under the <code>orders</code> prefix instead of every flow in the app.
- <code>.log(...)</code> adds logging at one **point** in the flow using logger <code>orders.path</code>; the expression never touches the payload directly.
- <code>LoggingHandler.Level.DEBUG</code> lets the logging backend level control output instead of always logging at INFO.
- <code>@EnableIntegrationManagement(defaultLoggingEnabled="false")</code> reduces routine debug logging in **the main message flow** across supported managed components; it does not disable explicit <code>.log()</code> steps, exception logging, or message history.
- <code>orders.output</code> is a <code>QueueChannel</code>; tests must call <code>receive(timeout)</code> rather than expecting an event-driven subscriber.

Do not create an extra endpoint consuming from the same <code>orders.input</code> if you want to test a single pipeline. The name <code>orders.process</code> is the endpoint ID for management; specific history entries may record related component names depending on the framework.

### Reading history at the output

~~~java
Message<OrderCommand> request = MessageBuilder
    .withPayload(new OrderCommand("O-42", 2))
    .setHeader("correlationId", "checkout-42")
    .build();

ordersInput.send(request);
Message<?> reply = ordersOutput.receive(5_000);
if (reply == null) {
    throw new IllegalStateException("No result received");
}

System.out.println(reply.getPayload());
showHistory(reply);
~~~

<code>MessageBuilder</code> is in <code>org.springframework.integration.support</code>. In this example, <code>ordersInput</code> and <code>ordersOutput</code> are injected beans. A successful <code>send()</code> does not automatically prove all downstream work completed in other topologies, especially with executors or reactive channels.

## 5. Key change in Spring Integration 6.3: append-only history

Spring Integration documentation describes two different history storage mechanisms by version:

| Version | How history is written | Performance consequence |
|---|---|---|
| Before 6.3 | When adding a track, the framework creates a new <code>MessageHistory</code> and rebuilds the message to reflect the updated header | Higher allocation and copying on multi-hop flows |
| From 6.3 onward | The first write creates the container; subsequent <code>MessageHistory.write()</code> calls can **append** entries to the existing container without rebuilding a new message on every track | Substantially reduces message copying, though history still consumes memory and serialization |

This change **does not make history free**. Every entry holds metadata and travels with the message, which is particularly costly if messages linger in queues/delayers/group stores or traverse a broker.

### Fan-out requires cloning history per branch

~~~mermaid
flowchart TD
    M["Original message<br/>history: input"] --> R["Router / PublishSubscribeChannel"]
    R --> A["Branch A<br/>history: input → A"]
    R --> B["Branch B<br/>history: input → B"]
    A --> A1["Audit"]
    B --> B1["Notification"]
~~~

Because history since 6.3 is append-only within a container, if two branches **shared one mutable container** and both appended entries, history could mix paths from both branches. Framework-managed fan-out components such as <code>PublishSubscribeChannel</code>, routers, <code>WireTap</code>, and splitters already handle **cloning history** when needed.

If you write a custom component that emits multiple independent messages from one original message, follow the proper clone/copy mechanism. Spring Integration provides <code>AbstractIntegrationMessageBuilder.cloneMessageHistoryIfAny()</code> for custom branching use cases. Never mutate <code>MessageHistory</code> directly in application code and never assume copying a header reference onto another message yields an independent path.

**When upgrading from 6.2 to 6.3+:** re-measure allocation/throughput instead of relying on old numbers; check custom splitters/routers, serializable headers, any handler rebuilding messages manually, and how history is snapshotted for auditing.

## 6. Logging in Spring Integration: costs distinct from history

Spring Integration has two groups of logs:

1. **Framework debug logging** inside channels, dispatchers, handlers, or endpoints when the log level permits.
2. **Flow-added logging endpoints/wiretaps**, such as <code>LoggingHandler</code> and Java DSL <code>.log(...)</code>.

They are not the same mechanism. Turning off routine debug logging via <code>@EnableIntegrationManagement(defaultLoggingEnabled="false")</code> does not turn off all loggers, exceptions, metrics, or <code>LoggingHandler</code> instances.

An important principle in high-throughput environments: even checking <code>isDebugEnabled()</code> can carry overhead depending on the logging subsystem. Spring Integration provides <code>defaultLoggingEnabled</code> specifically to avoid logging checks/calls in the main flow when needed.

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(defaultLoggingEnabled = "false")
class QuietManagedComponentsConfig {
}
~~~

This setting applies only as a default for components **without manually configured loggingEnabled**. A channel calling <code>setLoggingEnabled(true)</code> retains its explicit override. Exception/debug logs emitted on other error-handling paths remain active by design.

### Do not log the full message just to see one header

~~~java
// May inadvertently call toString() on the entire payload and headers:
.log(LoggingHandler.Level.INFO, "orders.flow")

// Better: log only the metadata needed for investigation.
.log(LoggingHandler.Level.DEBUG, "orders.flow", message ->
    "messageId=" + message.getHeaders().getId()
    + ", correlationId=" + message.getHeaders().get("correlationId"))
~~~

The snippets above are **Java DSL fragments** illustrating operator placement in a flow. Log expressions to avoid:

- <code>payload.toString()</code> when payloads are large, have deep object graphs, or contain sensitive data;
- serializing the entire message to JSON just to extract an ID;
- repeating logs across too many channels around the same business step;
- shipping raw payloads to a log collector with no size limits or retention controls;
- creating dynamic logger categories per tenant/request.

When a logger is disabled, the backend may skip writing to sinks, but never assume every API variant **skips evaluating** the log expression. If an expression is expensive, measure it empirically or control/sample it in the design.

## 7. Java DSL .log() and WireTap: “observation” still sits on the processing path

The Spring Integration Java DSL <code>.log()</code> operator is implemented via a **<code>WireTap</code> channel interceptor** paired with a <code>LoggingHandler</code> receiving messages on a side branch. It is an observation point, not a business handler automatically producing replies.

~~~text
Producer → Channel + WireTap → Business Handler → Output
                 │
                 └→ LoggingHandler → log appender
~~~

If the tap runs synchronously on the sender thread and the log backend formats or writes slowly, **send latency** rises even if the business handler is unchanged. Moving the tap to an executor shifts part of the cost off the critical path, but introduces queue backlog, memory usage, and overflow/rejection policies on the logging branch.

**Distinguish wiretaps from durable auditing:**

| Design | Strength | Risk |
|---|---|---|
| Direct <code>.log()</code> | Easy to add/remove during debugging; needs no broker | In-runtime cost; logs carry no delivery guarantee |
| WireTap → dedicated channel/handler | Isolates observation point; easy to filter and test | Adds extra subscriber/queue and failure modes in tap branch |
| Async appender | Offloads synchronous I/O from handler thread | Full buffer can block or drop events per logging policy |
| Persistent audit/outbox | Clear retention contract, transactions, and replay | DB/storage cost and dedicated handling logic |

In Spring Integration 6.0+, <code>.log()</code> is designed not to alter flow results whether placed in the middle or at the end; if a flow is **one-way** and has no consumer/reply after logging, use <code>.nullChannel()</code> or a proper terminal handler. Never repurpose LoggingHandler as a business endpoint merely to avoid no-subscriber errors.

## 8. Why logging alters order, threads, and when errors are observed

A system might have this topology:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as DirectChannel + WireTap
    participant L as LoggingHandler / Appender
    participant H as Business Handler
    P->>C: send(M)
    C->>L: log selected fields
    L-->>C: return
    C->>H: handle(M)
    H-->>P: business result
    Note over P,L: Synchronous logging can increase send latency
~~~

The diagram is an **illustrative synchronous-cost model**, not a claim that every wiretap setup always invokes logging before the handler in an invariant order. Interceptor/dispatcher ordering and executor usage must be verified in the actual topology.

If logs go to an <code>ExecutorChannel</code> or async appender, a log line can appear **after** the handler's logs even if the observed event started earlier. Therefore:

- Do not use log line ordering across threads to infer strict *happens-before* relationships.
- Attach message IDs, correlation IDs, and boundary-aligned timers/trace spans.
- Never treat a “message received” log as proof a transaction committed.
- When an async logging queue fills up, know its block/drop policy; never treat it as a reliable audit trail.
- If a handler retries or a broker redelivers, multiple log lines can appear for **the same business event**, which is not necessarily a logging bug.

## 9. Estimating observability cost before enabling system-wide

Costs span multiple layers and cannot be summed up as “each history entry is just a few bytes”.

| Layer | Overhead source | Production symptom |
|---|---|---|
| CPU | Creating metadata, timestamps, pattern/level checks, string formatting, serialization | CPU rises despite unchanged business logic and traffic |
| Heap/GC | Per-hop history growth, log event objects, async queues, trace/span context | Higher allocation rate, longer GC pauses/heap usage |
| Latency | Synchronous logging, appender locks, slow exporters or networks | p95/p99 end-to-end latency climbs |
| Throughput | Workers held by log I/O or exporters; full queues triggering backpressure | TPS drops, poller lag or executor backlog grows |
| Message size | History and trace headers crossing brokers/DB/Redis | Larger records, slower deserialization, higher bandwidth/storage |
| Telemetry backend | Metric series, trace spans, log ingestion and indexing | Scrape/export queues grow, storage and query costs climb |
| Data safety | Payloads/headers containing PII, tokens, and business IDs | Log collector retains sensitive data beyond necessary scope |

### Memory model using Little's Law

Suppose:

- <code>λ</code>: average message arrival rate entering the flow (messages/second).
- <code>W</code>: average time a message stays in the system (seconds), including queue waits.
- <code>k</code>: average number of history entries per active message.
- <code>b</code>: **measured additional bytes** per entry (including objects, metadata, and collection overhead per JVM/version).

Then the estimated extra live memory from history is:

\[
\text{History bytes in flight} \approx \lambda \times W \times k \times b
\]

**Hypothetical sizing example (not a real benchmark):** 5,000 messages/second, each staying an average of 0.2 seconds across 8 tracked hops; if each entry adds 160 measured bytes:

~~~text
In-flight ≈ 5,000 × 0.2 = 1,000 messages
Additional history ≈ 1,000 × 8 × 160 B = 1,280,000 B (~1.28 MB)
~~~

If queue residence jumps from 0.2 to 20 seconds, in-flight messages increase 100x and heap used by history **can grow proportionally**, even at the same throughput. With persistent stores, also account for serialized size and how the DB/broker buffers messages.

This is only a directional model. Object layout, alignment, Java version, reference sharing, compression, payloads, and fan-out history cloning can significantly alter measurements. Always **measure allocations/JFR and real message sizes** before using this for capacity planning.

### Log volume model

Raw log volume is relatively straightforward to estimate:

\[
\text{Bytes/s} \approx \text{messages/s} \times \text{log points/message} \times \text{bytes/log event}
\]

For example: 10,000 messages/second, each emitting 3 log events of 300 formatted bytes, equals **9 MB/second** or roughly **778 GB/day** of raw logs in decimal units, *before* collector indexes, replication, logging system metadata, and compression. That cost can arise solely from three <code>.log()</code> calls at high volume.

With async appenders, events sit temporarily in a heap queue. If the sink is slower than the producer, the queue fills; the system then **blocks**, **drops**, **spills**, or **fails** per backend config. Never assume async makes the cost vanish.

## 10. Message history across different channel types

Performance impact depends on topology, not merely hop count:

| Runtime boundary | How will history/logging affect it? | What to measure |
|---|---|---|
| <code>DirectChannel</code> | Handlers, interceptors, and synchronous logs sit inside sender latency | <code>send()</code> duration, p99 latency, sender CPU |
| <code>ExecutorChannel</code> | Thread handoff and task queue; tasks hold references to messages with headers/history | Executor queue wait, active threads, heap |
| In-memory <code>QueueChannel</code> | History stays with queued messages | Queue depth × message size, GC, and receive lag |
| <code>JdbcChannelMessageStore</code> | History header is written/read with messages per serializer | Row size, serialize/deserialize time, DB I/O |
| <code>MessageGroupStore</code> aggregator | Many fragments carry history; groups held until release/timeout | Group size, group age, store size, retention |
| Delayer | Messages can keep headers in the store for a long time | Delayed count, expired age, storage, and reschedule cost |
| <code>PublishSubscribeChannel</code>/router | Fan-out creates separate history paths; total entries multiply across branches | Branch count, copied headers, payload size |
| Broker inbound/outbound adapters | History survives transport only if header mappers/serializers allow it | Header size, broker quota, network throughput |
| Reactor <code>FluxMessageChannel</code> | Subscription/backpressure and context propagation have distinct semantics | Demand, prefetch, worker wait, onError, headers |

An important note: adding a <code>ThreadPoolTaskExecutor</code> to move logging onto separate threads can improve **sender-observed latency**, yet will not raise overall throughput if the logging backend remains the bottleneck and the queue accumulates an unbounded backlog.

## 11. Metrics and tracing: they do not replace history, yet still need a budget

Spring Integration 6.x supports Micrometer/Observation. Configure <code>@EnableIntegrationManagement</code> to select which managed components produce Observations:

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(
    defaultLoggingEnabled = "false",
    observationPatterns = {
        "orders.process",
        "orders.outbound*"
    })
class TargetedObservationConfig {
}
~~~

This example is a **standalone configuration choice**, not a second bean to add alongside <code>OrderHistoryFlowConfig</code> if management is already enabled there. In a real app, consolidate annotations into one configuration so there is no ambiguity about which configurer applies.

<code>observationPatterns</code> by default **does not enable Observation for all components**; an <code>ObservationRegistry</code> and matching <code>ObservationHandler</code> are required to export meters/traces. With Spring Boot Actuator, inspect existing auto-configuration before defining a second registry or handler.

| Observation | When metrics/tracing fits | When history fits |
|---|---|---|
| Handler error rate over 5 minutes | Counters/timers with outcome tags | Inefficient to aggregate message-by-message |
| Handler p95/p99 latency | <code>spring.integration.handler</code> timer when Observation is enabled | Hop timestamps do not replace duration |
| Queue lag and backlog | Queue depth, age, dedicated enqueue-to-start timer | History may lack exact wait times |
| A message took the wrong router branch | Traces + selective history | Very helpful for verifying visited hops |
| Context across broker/process | Tracing propagator + message headers | Only if history headers are preserved |
| Mandatory audit surviving crashes | Transactional persistent audit/outbox with retention | Insufficient as a sole source of truth |

Observation-based meters typically have names such as <code>spring.integration.handler</code> or <code>spring.integration.producer</code>. With legacy meters, you may see <code>spring.integration.send</code> and <code>spring.integration.receive</code>. Never build dashboards on unverified meter names: Spring Integration/Micrometer versions and instrumentation configuration determine which meters actually exist.

### Cardinality is a cost independent of log volume

If every message has a distinct <code>orderId</code> and you turn order IDs into a **metric tag**, the registry/Prometheus may have to track millions of time series. Use only low-cardinality tags such as stable component names, environment, result, and handler type. Business IDs belong in **traces/logs with retention policies** or business query stores—never as default timer tags.

With dynamic tenant flows, managed names generated per tenant UUID can also inflate cardinality when each tenant creates a new series. Decide upfront whether metrics are needed per tenant or only per tenant tier/flow type, and configure meter filters/sampling accordingly.

## 12. Controlled runtime toggling of message history

<code>MessageHistoryConfigurer</code> supports changing component-name patterns and has its own lifecycle. Documentation requires **stopping the configurer before updating patterns**, then starting it again:

~~~java
@Component
public class MessageHistoryController {
    private final MessageHistoryConfigurer configurer;

    public MessageHistoryController(MessageHistoryConfigurer configurer) {
        this.configurer = configurer;
    }

    public synchronized void trackOrdersOnly() {
        configurer.stop();
        try {
            configurer.setComponentNamePatternsString("orders.*");
        } finally {
            configurer.start();
        }
    }
}
~~~

<code>MessageHistoryConfigurer</code> lives in <code>org.springframework.integration.history</code>. The snippet assumes the application context has <code>@EnableMessageHistory</code> enabled and a single matching configurer exists.

**Stop here means stopping history recording**, not stopping all <code>IntegrationFlow</code>s or discarding queued messages. Messages that already carry a history header can still retain prior metadata through subsequent hops; changing patterns does not “retroactively erase” history from in-flight messages.

When JMX is configured, the configurer can be exposed as an MBean to adjust patterns during incident investigations. Do not expose this operation publicly; flipping system-wide tracking during peak traffic can spike costs and message header sizes.

### Procedure for using history as a diagnostic switch

1. Identify the flow and component names to investigate from the runtime graph.
2. Record baseline CPU/latency/heap/log ingest in the current state.
3. Enable a narrow pattern for one group of components, logging start time and planned turn-off time.
4. Collect a few sample messages from allowed tests or error paths and inspect history for missing hops.
5. Adjust logging/observation if needed, never turning everything on at once automatically.
6. After diagnosis, restore the configurer to production-policy patterns and verify metrics/costs return to baseline.

**Do not change patterns by repeatedly creating additional annotations or runtime beans.** When multiple configurers coexist, it becomes hard to tell which source is effective and can violate Spring Integration's single-source requirement.

## 13. Optimizing logging without losing investigability

A priority-based logging policy:

| State | What to log | What to avoid logging |
|---|---|---|
| Normal | Business event ID, correlation, endpoint, and summary outcome at key boundaries | Every hop, full payloads, all headers |
| Latency spike | p95/p99 metrics, thread/queue lag, logs for a few slow messages | Leaving DEBUG enabled on every package for long periods |
| Handler failure | Exception chain, permitted failed message metadata, retry count, transaction outcome | Repeating the same stack trace at every layer, dumping sensitive data |
| Tracing a batch | Narrow message history pattern, valid correlation-based trace sampling | High-cardinality batch IDs in metric tags |
| Suspected message loss | Source ACK/redelivery, store state, error channel, and audit records | Relying solely on a “message received” line |

### Redaction and data access

Logging full headers can expose sensitive data such as tokens, cookies, emails, tenant identifiers, payload PII, or connection strings. A <code>LoggingHandler</code> expression like <code>m.getHeaders()</code> looks handy for debugging but is unsafe to enable broadly.

Recommendations:

- use an allowlist of permitted fields instead of a denylist of “known dangerous” fields;
- never call <code>toString()</code> on uncontrolled payloads/objects;
- log correlation IDs and masked/hashed business IDs when needed;
- bound log event length, retention, and read access permissions;
- separate debug logs from durable auditing;
- avoid using payload contents as sampling keys or metric tags without a security review.

<code>MessageHistory</code> normally records only name/type/timestamp metadata, yet component names can reveal tenant or operational info. Do not treat this header as automatically safe to forward to external systems or store indefinitely.

## 14. Benchmarking cost: controlled A/B testing

A performance measurement test should not just send a few messages and average <code>System.nanoTime()</code>. JIT warm-up, GC, logging appenders, persistence backends, thread contention, and schedulers can all skew results.

Suggested four A/B configurations on **the exact same topology and workload**:

| Config | History | Logging | Metrics/tracing |
|---|---|---|---|
| A — baseline | Off | Minimal INFO, no per-message logs | Basic system metrics |
| B — history | Pattern selecting only 3–5 hops | Same as A | Same as A |
| C — log | Same as A | One metadata log at one hop | Same as A |
| D — selective observability | Same pattern as B | Same metadata log as C | Observation on key handlers |

Hold constant: Java/Spring versions, JVM flags, CPU/memory limits, thread pools, DB/broker latency, payload size, message rate, tenant count, and error/retry rates. Especially verify the source does not bottleneck early and trick you into concluding that extra logging “had no impact”.

### Metrics to collect

1. **Throughput:** business messages successfully processed/second, not merely accepted <code>send()</code> calls.
2. **End-to-end latency:** receipt to completion/commit/ACK per contract; inspect p50/p95/p99 and tail latency.
3. **CPU, allocation, GC:** user/system CPU, allocation rate, heap, GC pauses, object histograms; use JFR/JMC or an appropriate profiler.
4. **Threading:** active executors, queue wait, poller lag, thread dumps on stalls.
5. **Log system:** events/second, bytes/second, appender queue depth, drop/block counts, export time.
6. **Persistence/network:** message size before/after history, DB read/write latency, broker bytes/second.
7. **Correctness:** lost/duplicate counts, side effects, error channel, retry attempts, intact correlation.

**Never optimize throughput by dropping mandatory logs or ACKing unprocessed messages early.** Results must be compared under the same delivery contract; if D looks “faster” because it skipped audit/transaction persistence, the comparison is invalid.

### Structured benchmark report template

~~~text
Runtime: Java 17, Spring Integration 6.x
Topology: inbound → DirectChannel → validation
             → ExecutorChannel → JDBC handler → outbound
Load: [message rate, payload size, duration, concurrency]
Run: warm-up and multiple measured rounds, identical input dataset

             A baseline   B history   C logging   D combined
TPS          <measured>   <measured>  <measured>  <measured>
p99 latency  <measured>   <measured>  <measured>  <measured>
alloc MB/s   <measured>   <measured>  <measured>  <measured>
GC pause     <measured>   <measured>  <measured>  <measured>
log MB/s     <measured>   <measured>  <measured>  <measured>
~~~

The <code>&lt;measured&gt;</code> cells are **data you must collect empirically**, not measurements taken in this lesson. For tiny per-method overhead, JMH can evaluate allocations/operation cost; for Spring Integration runtime, only **end-to-end load tests** reflect contention across CPU, stores, network, and logging backends.

## 15. Testing history and logging at runtime

### 15.1. Testing that history appears after passing a tracked component

Example using the Spring context of <code>OrderHistoryFlowConfig</code> from section 4:

~~~java
@SpringJUnitConfig(OrderHistoryFlowConfig.class)
class OrderHistoryFlowTest {

    @Autowired
    @Qualifier("orders.input")
    DirectChannel input;

    @Autowired
    @Qualifier("orders.output")
    QueueChannel output;

    @Test
    void messageHasTrackedHistoryAfterPassingFlow() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-77", 1))
            .setHeader("correlationId", "checkout-77")
            .build();

        assertTrue(input.send(request));
        Message<?> reply = output.receive(3_000);
        assertNotNull(reply);
        assertEquals(new OrderResult("O-77", "ACCEPTED"),
            reply.getPayload());

        MessageHistory history = MessageHistory.read(reply);
        assertNotNull(history);
        assertFalse(history.isEmpty());
        assertTrue(history.stream().anyMatch(hop ->
            String.valueOf(hop.get(MessageHistory.NAME_PROPERTY))
                .startsWith("orders.")));
    }
}
~~~

<code>@SpringJUnitConfig</code> is in <code>org.springframework.test.context.junit.jupiter</code>; assertions are from JUnit Jupiter. Check <code>history.isEmpty()</code> and component prefixes rather than hardcoding exact timestamps/entry ordering: framework-generated components and message structure can change across version upgrades.

If a test pushes multiple messages into the same <code>QueueChannel</code>, **drain/reset the fixture** after each case so leftover messages from an earlier test are not read by mistake. If switching to an <code>ExecutorChannel</code>, use a latch/timed condition wait rather than asserting the handler finished immediately after <code>send()</code>.

### 15.2. Testing that log formatting does not dump payloads

A simple test can verify the chosen **log expression** before wiring it into <code>.log()</code>:

~~~java
Function<Message<?>, String> safeLog = message ->
    "messageId=" + message.getHeaders().getId()
    + ", correlationId=" + message.getHeaders().get("correlationId");

Message<String> message = MessageBuilder
    .withPayload("secret-card-token")
    .setHeader("correlationId", "corr-100")
    .build();

String line = safeLog.apply(message);
assertTrue(line.contains("corr-100"));
assertFalse(line.contains("secret-card-token"));
~~~

<code>Function</code> is in <code>java.util.function</code>. This test only verifies the expression **excluded the payload**; it does not prove the logging backend, appenders, or other logs in the application redact properly. To test actual log output, use a capturing appender at the logging framework layer and test multiple error sources.

### 15.3. Testing that fan-out does not mix history

Design a test with <code>PublishSubscribeChannel</code> and two distinct output branches:

1. Send one message with a unique <code>correlationId</code> into the channel before fan-out.
2. Route each branch through its own named component into a separate queue/sink.
3. Read <code>MessageHistory</code> from the message at each sink.
4. Confirm upstream entries are preserved; branch A's entries do not leak into branch B and vice versa per the tested framework version's behavior.
5. Repeat under concurrency and when custom routers/splitters construct new messages.

This test is especially valuable when migrating from before **6.3** to 6.3+ or when custom components clone/multiply messages.

## 16. Observing errors without accidentally altering retries/transactions

Logging and history **are not recovery advices**. A handler throwing an exception on <code>DirectChannel</code> may propagate the exception back to the sender; across <code>ExecutorChannel</code>, errors occur on the worker and must be observed via the corresponding error handler/error flow.

| Scenario | Why is it easy to misread? | Evidence actually needed |
|---|---|---|
| “received” log with no “completed” log | Could be blocked, crashed, canceled, timed out, or log dropped | Handler completion/error, queue, transaction, trace |
| History includes <code>orders.handler</code> | Does not prove downstream side effects committed | DB state, transaction outcome, outbox/ACK |
| History lists the same handler multiple times | Could be retries, loops, or valid multiple passes | Retry attempts, message ID, business event ID |
| ErrorMessage contains history | History usually shows hops up to failure, not which step rolled back | Failed/original message, cause, transaction |
| Log appears after sender timeout | Async task or buffered logger finished after timeout | Thread traces, completion boundary |
| Trace ends OK while business logic failed | Recovery turned exception into completion or outcome measured at wrong boundary | Business result, DLQ, recoverer, and error policy |

Never use <code>onErrorResume</code>, <code>catch (Exception)</code>, or an <code>ErrorMessage</code> consumer that returns normally just to log while forgetting to propagate the error per contract. Doing so can make the source ACK a message prematurely and skip retries even though business work failed.

In systems with retries, attach the **attempt number** to structured logs at the retry boundary (using information available from the retry context) and use a stable **business idempotency key**. Random message IDs or history entry counts are insufficient to determine how many times a side effect executed.

## 17. Diagnosing slowdowns after enabling history/logging

| Symptom | Hypothesis to check | Action |
|---|---|---|
| p99 <code>DirectChannel.send()</code> climbs | Synchronous log/wiretap or expensive payload <code>toString()</code> | Profile formatter/appender, switch to metadata-only, narrow log points |
| Allocation rate and GC jump sharply | History across too many hops, fan-out clones, or log events | Narrow patterns, check Java/Spring versions, JFR allocations |
| Queues grow when DEBUG is enabled | Threads/executors blocked by log I/O or logging pool full | Measure queue wait and appender saturation; inspect drop/block policy |
| JDBC store grows rapidly | History header persisted with messages, many pending groups | Measure message bytes/row and retention/group timeouts |
| Broker rejects message/header too large | Headers/history/trace baggage exceed quota | Inspect header mappers and header/payload caps; separate audit |
| One tenant generates tons of metric series | Dynamic managed names/tags per tenant | Fix naming, meter filters, and cardinality |
| Traces disconnect across queue/broker | Context propagation not enabled properly on producer/consumer | Verify ObservationRegistry, propagation, and header mappers |
| DEBUG turned off yet CPU stays high | History/tracing still active, logging handler uses INFO, or expensive appender | Inspect **each** observability layer independently |
| History enabled yet unhelpful for debugging | Pattern mismatch, custom branch drops history | List component names, inspect headers and custom message builders |

### Ordered runbook

1. Confirm **workload** is unchanged: ingress rate, payload size, retry/error ratio, and topology.
2. Measure end-to-end p95/p99, CPU/GC, queue depth, and logging/export backends.
3. Inventory active message history patterns, <code>LoggingHandler</code>/<code>.log()</code> points, framework log levels, Observation patterns, and tracing samplers.
4. Disable/reduce **one** observability layer in a controlled way and re-measure (do not turn everything off at once during an active incident).
5. For long-lived messages, measure actual header size in QueueChannel/JDBC stores/brokers.
6. If multiple branches or custom splitters exist, verify history cloning and per-branch message counts.
7. Verify business correctness remains intact: outputs, ACK/commit, retries, error channels, idempotency.
8. Pick the minimal production configuration that meets on-call needs; document limits and costs with measurements.

## 18. Production checklist

- [ ] Enable <code>@EnableMessageHistory</code> only when needed and narrow patterns to key named components.
- [ ] Verify Spring Integration version; understand append-only behavior and fan-out cloning from 6.3 onward.
- [ ] Never use the history header as an audit store or proof of transaction commit.
- [ ] Use <code>LoggingHandler</code>/<code>.log()</code> with allowlisted metadata; avoid full payloads and sensitive headers.
- [ ] Understand that <code>defaultLoggingEnabled=false</code> affects only managed framework logging, not all logs/metrics/history.
- [ ] Measure latency/throughput/heap/GC and log bytes/second with key observability layers enabled.
- [ ] Know the overflow policies and lifecycles of async appenders and telemetry exporters.
- [ ] Account for history/header size in persistent queues, delayed messages, aggregator groups, and brokers.
- [ ] Use low-cardinality component/tag names for traces/metrics; never put message IDs or order IDs in default meter tags.
- [ ] Have a runbook to enable history temporarily, stop the configurer before changing patterns, and revert after investigation.
- [ ] Test history headers, log redaction, branch isolation, errors/retries, and correctness across thread/transaction boundaries.
- [ ] Balance observability against data security, retention, log access controls, and durable audit requirements.

**Conclusion:** <code>MessageHistory</code> shows *which tracked components a message visited*, logging narrates events at chosen checkpoints, and metrics/tracing surface rate- and time-based issues. All of them carry a cost. In the Spring Integration runtime, the sustainable approach is **stable component naming → tracking a few critical hops → logging safe metadata → measuring end-to-end overhead → expanding only for specific investigative questions**. That preserves your ability to diagnose threading, correlation, retry, and message store issues without turning observability itself into the message flow's bottleneck.

## References

- [Spring Integration Reference — Message History](https://docs.spring.io/spring-integration/reference/message-history.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-adapter.html)
- [Spring Integration Reference — Java DSL log() Operator](https://docs.spring.io/spring-integration/reference/dsl/java-log.html)
- [Spring Integration 6.5 Javadoc — MessageHistory](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/history/MessageHistory.html)
- [Spring Integration 6.5 Javadoc — MessageHistoryConfigurer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/history/MessageHistoryConfigurer.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
