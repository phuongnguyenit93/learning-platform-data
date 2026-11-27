# Message history and limiting history size in Spring Integration

## 1. Why is Message History needed when operating message flows?

In **SPRING_INTEGRATION_RUNTIME**, a message can pass through gateways, `MessageChannel`s, transformers, routers, filters, consumer endpoints, pollers, executors, aggregators, retry advice, and error flows. Components are loosely coupled by design: downstream handlers generally do not know which endpoints a message just traversed. That makes flows easy to evolve, yet makes investigating lost messages, misrouted branches, or slow processing much harder.

**Message History** is a Spring Integration mechanism that stores a **list of tracked components a message passed through** inside a message header. When enabled, a component with a matching name/ID can append an entry about itself to the `history` header.

The topic **Observability → Message history and limiting history size** aims to:

1. Understand the `history` header format, how to enable/disable it, and how to read history at runtime.
2. Distinguish message history from distributed tracing, metrics, application logs, and message stores.
3. Explain why history grows in loops, retries, replays, or long flows.
4. Limit **tracking scope**, limit **displayed data**, and when genuinely needed **reset history at a chosen boundary**.
5. Understand Spring Integration 6.3 changes for append-only history and cloning history during fan-out.
6. Integrate observability with threads, pollers, transactions, recovery, correlation, and backend persistence.

**Important rule:** `tracked-components` restricts **which components are recorded**; it does not mean the `history` header is guaranteed to stay capped at N entries. In the referenced Spring Integration documentation/Javadoc, there is no single public configuration property such as `maxHistorySize=20` on `MessageHistoryConfigurer`. When you need a *hard bound*, the application must design explicit boundaries and strategies.

~~~mermaid
flowchart LR
    P["Producer"] --> C1["ordersIn"]
    C1 --> T["normalizeEndpoint"]
    T --> C2["normalized"]
    C2 --> H["ordersHandler"]
    H --> O["Downstream"]
    C1 -.-> X["Message header: history"]
    T -.-> X
    C2 -.-> X
    H -.-> X
    X --> D["Diagnostics / logs / metrics"]
~~~

Conceptual diagram: only **selected trackable components** contribute entries; not every Java method in the flow is recorded automatically.

## 2. What data is inside History?

Spring Integration uses `org.springframework.integration.history.MessageHistory` and a header named by `MessageHistory.HEADER_NAME` (typically `"history"`). `MessageHistory` implements `List<Properties>`. Each element typically contains:

| Entry property | Java constant | Content |
| --- | --- | --- |
| `name` | `MessageHistory.NAME_PROPERTY` | Name/ID of the tracked component |
| `type` | `MessageHistory.TYPE_PROPERTY` | Type of integration component |
| `timestamp` | `MessageHistory.TIMESTAMP_PROPERTY` | Time when the framework recorded the trace at the component |

An illustrative example:

~~~text
history = [
  {name=ordersGateway, type=gateway,         timestamp=1795312800123},
  {name=normalizeEndpoint, type=transformer, timestamp=1795312800125},
  {name=ordersHandler, type=service-activator,timestamp=1795312800131}
]
~~~

**This is intra-application routing information, not an immutable transaction audit trail.** Only selected components that support tracking are recorded. If processing occurs outside tracked component infrastructure, or an adapter rebuilds a message without preserving headers, history can miss that segment.

### What history does NOT guarantee

- Does not automatically capture the full payload of each hop.
- Does not record start/end processing times of individual methods.
- Does not prove a database transaction committed.
- Does not guarantee an event was acknowledged by a broker.
- Does not hold a distributed span context equivalent to OpenTelemetry.
- Does not automatically record `Thread.currentThread().getName()` or every retry attempt.
- Does not guarantee immutability/durability across restarts unless the message is persistently stored.
- Is not a replay mechanism when handling errors.

The timestamps of two consecutive entries can help estimate **the elapsed time between two tracking points**. Their difference is not necessarily handler duration: it may include queue wait, polling intervals, backoff, thread scheduling, and I/O.

## 3. Enabling tracking via Java or XML

### Java configuration

Spring Integration provides `@EnableMessageHistory`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;

@Configuration
@EnableIntegration
@EnableMessageHistory
class MessageHistoryConfiguration {
}
~~~

By default, this configuration tracks **supported components with matching names/IDs**. To narrow the scope, specify names or patterns:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
        "ordersGateway",
        "normalize*",
        "*Outbound"
})
class FocusedHistoryConfiguration {
}
~~~

The patterns above are only examples; they must match actual **component names** in the application context. For beans/endpoints whose names are auto-generated by the DSL, verify their names at runtime. If a pattern does not match, history may be empty or missing entries even while the flow runs normally.

### XML namespace

~~~xml
<!-- XML fragment: requires the int namespace and matching Spring Integration schema. -->
<int:message-history/>

<!-- Or select only a subset of components: -->
<int:message-history
        tracked-components="ordersGateway, normalize*, *Outbound"/>
~~~

**These two fragments are alternatives**; do not declare both in the same application context expecting two independent rule sets to apply.

Spring Integration recommends **a single source of message history configuration** in an application context, via `@EnableMessageHistory` or `<int:message-history/>`. Do not manually declare a generic `MessageHistoryConfigurer` bean to bypass the configuration registrar.

### Why do endpoint IDs matter?

Suppose you have an `orderService.process()` handler whose endpoint receives an unpredictable auto-generated name from annotations or Java DSL. The pattern `"orderService"` might **not match** the recorded component. With the DSL, assign explicit IDs if you want to observe by stable names:

~~~java
// Illustrative Java DSL snippet; requires an OrderService bean and appropriate imports.
@Bean
IntegrationFlow orderFlow(OrderService orderService) {
    return IntegrationFlow.from("ordersIn")
        .handle(orderService, "process",
                e -> e.id("ordersHandlerEndpoint"))
        .get();
}
~~~

In this example, seeing an entry with `ordersHandlerEndpoint` still depends on the trackable component type and where the framework records markers; verify actual history rather than assuming every DSL step emits exactly one entry.

## 4. Reading history safely inside handlers

The official API provides `MessageHistory.read(Message<?>)`:

~~~java
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

static void logHistory(Message<?> message) {
    MessageHistory history = MessageHistory.read(message);

    if (history == null || history.isEmpty()) {
        System.out.println("NO_HISTORY");
        return;
    }

    System.out.println("HISTORY_ENTRIES=" + history.size());

    for (Properties entry : history) {
        String name = entry.getProperty(
                MessageHistory.NAME_PROPERTY, "unknown");
        String type = entry.getProperty(
                MessageHistory.TYPE_PROPERTY, "unknown");
        String timestamp = entry.getProperty(
                MessageHistory.TIMESTAMP_PROPERTY, "unknown");

        System.out.printf("HOP name=%s type=%s at=%s%n",
                name, type, timestamp);
    }
}
~~~

This is a standalone Java method for use in a consumer or diagnostics class. **Do not call `history.toString()` indiscriminately** in production logs if history is very long; formatting it can allocate large strings and increase GC pressure.

Reading directly from headers is also valid:

~~~java
MessageHistory history = message.getHeaders().get(
        MessageHistory.HEADER_NAME, MessageHistory.class);
~~~

Handle `null` gracefully because tracking may be disabled, the message may not have crossed any selected component yet, or a boundary may have stripped the header.

### Do not mutate the list in the header directly

Prior to Spring Integration 6.3, history followed an immutable model: adding a hop generally created a new history instance and copied the message. Since 6.3, the framework uses **append-only**: subsequent `MessageHistory.write()` calls can append entries to the existing history container, reducing object allocations and message copies.

This **does not grant permission** for arbitrary business code to mutate it:

~~~java
// Do not do this to "limit history":
history.clear();
history.remove(0);
history.subList(0, 100).clear();
~~~

Depending on the version and multi-consumer flows, mutating the container directly can corrupt another branch's trace, cause races, or lose diagnostic data. When you need a shortened view, create a **read-only snapshot** or **build a new message at an explicit boundary**.

## 5. Runnable example: recording and reading Message History

Example for Java 17+, Spring Boot, and matching Spring Integration core/starter dependencies. Place the code in `MessageHistoryDemoApplication.java` under package `demo.integration`. `@EnableMessageHistory` enables tracking for named trackable components.

~~~java
package demo.integration;

import java.util.Properties;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
@EnableMessageHistory
public class MessageHistoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageHistoryDemoApplication.class, args);
    }

    @Bean("ordersIn")
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean("normalizedOrders")
    MessageChannel normalizedOrders() {
        return new DirectChannel();
    }

    @Bean
    ApplicationRunner send(
            @Qualifier("ordersIn") MessageChannel input) {

        return args -> input.send(MessageBuilder
                .withPayload(" order-42 ")
                .setHeader("eventId", "evt-42")
                .setHeader("traceId", "trace-42")
                .build());
    }
}

@MessageEndpoint
class HistoryDemoHandlers {

    @Transformer(
            inputChannel = "ordersIn",
            outputChannel = "normalizedOrders")
    public String normalize(String value) {
        return value.trim().toUpperCase();
    }

    @ServiceActivator(inputChannel = "normalizedOrders")
    public void inspect(Message<String> message) {
        MessageHistory history = MessageHistory.read(message);

        System.out.println("PAYLOAD=" + message.getPayload());
        System.out.println("EVENT_ID=" +
                message.getHeaders().get("eventId"));

        if (history == null) {
            System.out.println("NO_HISTORY");
            return;
        }

        System.out.println("HOPS=" + history.size());

        for (Properties entry : history) {
            System.out.printf("HOP name=%s type=%s at=%s%n",
                    entry.getProperty(MessageHistory.NAME_PROPERTY),
                    entry.getProperty(MessageHistory.TYPE_PROPERTY),
                    entry.getProperty(MessageHistory.TIMESTAMP_PROPERTY));
        }
    }
}
~~~

Expected behavior is stable, while exact entry count is not hardcoded:

~~~text
PAYLOAD=ORDER-42
EVENT_ID=evt-42
HOPS=<number of tracked components>
HOP name=... type=... at=...
...
~~~

The exact `HOP` output depends on the component names/types created by the framework and where the active version records markers. Never hardcode a test expecting exactly three entries just because the diagram has three steps.

### What the example demonstrates

- A message carries history across channels, transformers, and service activators.
- Downstream handlers can inspect history without modifying upstream business methods.
- The `eventId` header is preserved to tie message traces to business logic.
- `@EnableMessageHistory` is an observability configuration; it does not create a message store or transactions.
- Synchronous `DirectChannel` makes log ordering clear; when switching to an executor or poller, also observe threads, queue wait, and error handling.

### Enabling selectively instead of tracking everything

If a flow has hundreds of components, consider:

~~~java
@EnableMessageHistory({
        "ordersIn",
        "normalizedOrders",
        "*Endpoint"
})
~~~

This configuration **replaces** the argumentless annotation in the example. Depending on actual component names, some expected hops may not appear; tune patterns against verified integration graph/bean names.

## 6. How does Message History differ from logs, metrics, tracing, and audit?

| Mechanism | Unit of observation | Primary data | Best suited for |
| --- | --- | --- | --- |
| **Message History** | One header on the message | Name, type, timestamp of tracked components | Seeing where a message went |
| **Structured logging** | One log event | Context, exception, thread, business event ID | Investigating a specific incident |
| **Micrometer metrics** | Counter/timer/distribution | Error rate, throughput, p95/p99 latency | Dashboards, alerts, and system capacity |
| **Distributed tracing / OpenTelemetry** | Trace/span across processes/services | Span hierarchy, timing, context propagation | Debugging multiple services and async boundaries |
| **Message store** | Stored message or message group | Payload, headers, state/correlation | Durability, aggregation, queueing/replay |
| **Business audit/outbox** | Durable business event | Who/when/what changed, transaction state | Long-term legal/operational traceability |

Message history aids investigations, yet **does not replace** distributed tracing or durable auditing. For example:

~~~text
history:
  ordersIn -> normalizeEndpoint -> shippingGateway

trace:
  service A span -> service B span HTTP 503 -> retry -> response

audit/outbox:
  eventId=evt-42, shipmentStatus=FAILED, committedAt=...
~~~

All three answer different questions. History typically does not record thread names; `timestamp` only marks the hop and cannot separate executor wait time from HTTP call duration in a handler.

## 7. Why can history grow without bound?

A single history entry is not inherently large, but a system can produce **very many entries**.

### Long flows and loops

~~~mermaid
flowchart LR
    IN["Input"] --> A["Transform"]
    A --> B["Router"]
    B --> C{"Completed?"}
    C -->|No| R["Retry / requeue / loop"]
    R --> A
    C -->|Yes| OUT["Output"]
~~~

Each pass through tracked components can append entries to message history if the message retains its history. After N iterations, size grows roughly with the number of tracked hops:

\[
H_{\text{entries}} \approx H_0 + N \cdot k
\]

Where `H0` is the initial entry count and `k` is the number of tracked components per loop. This is a **logical estimate**, not an exact byte-size formula.

### Fan-out and multiple branches

A splitter, `PublishSubscribeChannel`, multi-output router, or wire tap can cause history to be **copied/multiplied per branch**. This increases total memory spent holding histories across messages/branches, even when each individual message's history length looks reasonable.

### Message stores and replay

A `QueueChannel` backed by a persistent message store or an aggregator storing `MessageGroup`s may have to serialize the `history` header too. When history grows long:

- Records written to DB/Redis/Mongo/brokers grow larger.
- Serialization/deserialization and GC costs increase.
- Bytes in queues, payload envelopes, or database rows grow.
- Logs printing full headers become verbose and hard to read.
- On restore/replay, all old entries may be carried forward and appended with new ones.

**Not every adapter preserves the `history` header automatically.** Some external adapters convert to their own wire format; history survives only if header mapping and serialization allow it. Always test on the actual production path.

### Retries

Distinguish carefully:

- `RequestHandlerRetryAdvice` may re-invoke **the same handler invocation** multiple times without creating new messages or re-entering tracked components.
- Broker redelivery typically creates a **new delivery**, possibly reusing payload while keeping or recreating message headers/history depending on the adapter.
- An actual loop re-sending a message through tracked channels grows history with each iteration.

Therefore, **never** assume `history.size() == retryAttempts` or deduce broker delivery counts from history. Track attempt counts and idempotency keys separately when needed.

## 8. Two forms of "limiting size" you must distinguish

There are two completely different problems:

| Requirement | Solution | Does it shrink the original history header? |
| --- | --- | --- |
| Display only the **last N hops** in logs/dashboards | Snapshot / read-only projection | **No** |
| Send less data to external systems | Keep a bounded summary, strip `history` at a chosen boundary | **Yes**, at that boundary |
| Reduce frequency of added entries | `tracked-components` selects fewer components | Does not impose a hard cap on loops |
| Avoid recording history continuously in production | Stop `MessageHistoryConfigurer` or enable only during debug windows | Messages already carrying history keep old entries |
| Keep full trace without bloating message size | External trace/log store keyed by `eventId`/`traceId` | Can drop history at boundary and store trace externally |
| Hard cap at every point in a flow | Requires multi-boundary policies/custom design | Not provided automatically by `@EnableMessageHistory` |

This is the core insight: **truncating a log string** does not truncate the header. **Reducing tracked components** does not guarantee a maximum hop count in a looping flow. **Resetting the header at one boundary** does not bound new hops recorded afterward unless subsequent boundaries also enforce a policy.

## 9. Approach 1: keeping only the last N hops when logging

If you only want concise logs without modifying the message:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

public final class HistoryProjection {

    private HistoryProjection() {
    }

    public static List<String> recentHopNames(
            Message<?> message, int maxEntries) {

        if (maxEntries < 1) {
            throw new IllegalArgumentException(
                    "maxEntries must be positive");
        }

        MessageHistory history = MessageHistory.read(message);
        if (history == null || history.isEmpty()) {
            return List.of();
        }

        // Read-only snapshot; does not delete or mutate the original history header.
        List<Properties> snapshot = new ArrayList<>(history);

        int from = Math.max(0, snapshot.size() - maxEntries);
        List<String> result = new ArrayList<>();

        for (int i = from; i < snapshot.size(); i++) {
            Properties entry = snapshot.get(i);
            result.add(entry.getProperty(
                    MessageHistory.NAME_PROPERTY, "unknown"));
        }

        return List.copyOf(result);
    }
}
~~~

Usage:

~~~java
List<String> lastFive =
        HistoryProjection.recentHopNames(message, 5);

logger.info("eventId={} historyTail={}",
        message.getHeaders().get("eventId"), lastFive);
~~~

Advantages:

- Simple to understand, minimal impact on the flow.
- Does not break correlation, reply/error headers, or any branches.
- Lets you choose `maxEntries` per log view.
- Useful when a message traverses many hops yet operators only need the tail.

**Limitation:** the full `MessageHistory` **remains in the header**. Memory, serialization, and network overhead of history do not decrease; this approach only bounds **displayed** data.

### Character limits differ from entry limits

If component names are long or log formatters expand text, five hops can still generate a large log line. You can apply a character cap on top:

~~~java
String joined = String.join(" > ", lastFive);
int maxChars = 300;

String bounded = joined.length() <= maxChars
        ? joined
        : "..." + joined.substring(
                joined.length() - (maxChars - 3));
~~~

This is a **string presentation budget**, not a cap on serialized bytes. With Unicode/UTF-8, 300 Java chars do not equal 300 bytes. When enforcing a network/broker budget, measure **actual encoded byte size**.

## 10. Approach 2: selecting fewer tracked components

The least invasive way to curb growth is usually restricting the tracked component list:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
        "ordersGateway",
        "payment*",
        "shippingOutbound"
})
class HistoryOnlyForCriticalPath {
}
~~~

Or:

~~~xml
<int:message-history
        tracked-components="ordersGateway, payment*, shippingOutbound"/>
~~~

Selection guidelines:

1. **Ingress**: gateway/inbound adapter to see where messages enter.
2. **Branching points**: routers, filters, or splitters that decide paths.
3. **Key I/O boundaries**: HTTP/JMS/JDBC outbound gateways.
4. **Completion points**: handlers with business commits, before replies/acks.
5. **Recovery points**: error routes or DLQ-writing endpoints if trackable.

You do not need to track every intermediate transformer or channel when the goal is routing diagnostics. Just ensure component IDs are stable across deploys and patterns match your integration configuration.

### Changing patterns at runtime via MessageHistoryConfigurer

`MessageHistoryConfigurer` has a lifecycle and JMX management (when `IntegrationMBeanExporter` exports the corresponding MBean). Its Javadoc explicitly states **not to change patterns while the configurer is running**: stop it first.

~~~java
// Illustrative internal operational code, assuming a Spring-managed bean.
MessageHistoryConfigurer configurer = ...;

configurer.stop();
try {
    configurer.setComponentNamePatternsString(
            "ordersGateway,payment*,shippingOutbound");
}
finally {
    configurer.start();
}
~~~

This is an operational snippet, not a manual bean definition; the framework should create the configurer via `@EnableMessageHistory` or the XML namespace. Before using in production, verify behavior on your exact Spring Integration version and ensure administrative access controls are enforced.

While the configurer is stopped, messages **do not receive new** entries at those components; existing entries do not vanish. If you change patterns while messages are in flight, a single message's trace may record only part of the path.

### JMX and Control Bus

The MBean is documented with an ObjectName pattern of:

~~~text
<domain>:name=messageHistoryConfigurer,type=MessageHistoryConfigurer
~~~

The domain depends on exporter configuration. JMX tools or internal APIs can stop, update patterns, and start it. Never expose Control Bus/JMX write operations to untrusted clients. Changes to observability settings should be audited: who changed them, when, why, and old/new patterns.

## 11. Approach 3: summarizing and stripping history at a chosen boundary

When facing a **strict byte budget** before a broker, persistent store, or HTTP call, you can design a handoff point:

1. Read history from the current message.
2. Write a **bounded summary** to a log/trace store or small application header.
3. Build a new message without the `MessageHistory.HEADER_NAME` header.
4. Allow downstream components to start fresh history if tracking remains enabled.

This is an **application policy**, not a built-in property on `MessageHistoryConfigurer`.

### Java example: resetting history and keeping a preview of at most 5 hops / 200 chars

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HistoryBoundary {

    private HistoryBoundary() {
    }

    public static <T> Message<T> compactBeforePersistence(
            Message<T> input, int keepLastEntries, int maxChars) {

        if (keepLastEntries < 1 || maxChars < 4) {
            throw new IllegalArgumentException("Invalid history limits");
        }

        MessageHistory history = MessageHistory.read(input);
        if (history == null || history.isEmpty()) {
            return input;
        }

        // Copy for reading; do not mutate the input's shared MessageHistory.
        List<Properties> snapshot = new ArrayList<>(history);
        int from = Math.max(0, snapshot.size() - keepLastEntries);

        List<String> names = new ArrayList<>();
        for (int i = from; i < snapshot.size(); i++) {
            names.add(snapshot.get(i).getProperty(
                    MessageHistory.NAME_PROPERTY, "unknown"));
        }

        String summary = String.join(" > ", names);
        if (summary.length() > maxChars) {
            summary = "..." + summary.substring(
                    summary.length() - (maxChars - 3));
        }

        return MessageBuilder.fromMessage(input)
                .removeHeader(MessageHistory.HEADER_NAME)
                .setHeader("historyPreview", summary)
                .setHeader("historyDroppedEntries",
                        snapshot.size() - names.size())
                .build();
    }
}
~~~

**Exact meaning:**

- `historyPreview` is a bounded **application header**; it is **not** a standard `MessageHistory`.
- The original `"history"` header is removed from the **new message** crossing the boundary.
- After the boundary, a tracked component can initialize a fresh `MessageHistory` and append new entries. This limit applies only **where the method is called**, not across all downstream stages.
- `historyDroppedEntries` counts entries omitted from the preview by **entry count**, not bytes saved.
- Use header/string types understood by your broker/store serializer; when persisting durably, check compatibility and retention.

Do not pull tricks like `history.subList(...).clear()` and keep reusing the shared message. In Spring Integration 6.3+, history can be a shared append-only container in certain custom fan-out situations; direct mutation corrupts other branches' traces.

### Placing the boundary in a flow

A clean flow structure:

~~~text
source -> tracked handlers -> boundary transformer
       -> persistent QueueChannel / outbound adapter
       -> downstream handlers -> new tracking segment
~~~

At the `boundary transformer`, the message is rebuilt via `HistoryBoundary.compactBeforePersistence(...)`. If that component or the channel right after it is tracked, a few **new** entries may appear before the message hits the store. To control headers **at store-write time**, verify the exact tracking points and the adapter's header mapper.

If a strict byte ceiling is needed **on the wire**, enforce the rule right at the serialization/header-mapping boundary and verify payload + headers **after encoding**. Preview `maxChars` is only one piece of the total byte budget.

### Do not reset history at every endpoint

Dropping the header too early or at every step causes problems:

- You lose the full path needed for investigations.
- Downstream failures lose visibility into early hops.
- Cross-system traces become harder to stitch without `traceId`/`eventId`.
- Splitters/aggregators relying on other headers still need them, yet careless message rebuilding can accidentally drop correlation/sequence/reply/error headers.

Place boundaries intentionally: before brokers/stores, between domains, before network egress, or when transitioning from full diagnostics to compact traces. **Preserve logical event IDs and correlation headers** whenever building a new message.

## 12. Approach 4: exporting traces externally and keeping headers small

If you need to query the **entire path** without carrying a long history on messages:

~~~mermaid
flowchart LR
    M["Message(eventId, traceId)"] --> T["Flow components"]
    T --> O["Observation/log/trace records"]
    O --> S[("Trace/log backend")]
    T --> B["Compact message: eventId + traceId"]
    B --> D["Broker / persistent store"]
    D --> T2["Downstream"]
    T2 --> S
~~~

External span/log records can carry `eventId`, `traceId`, endpoint, start/end times, outcome, and exceptions. During investigations, operators query by ID. This is a different architectural choice from the `MessageHistory` header—not an automatic conversion of framework history into distributed traces.

### When to choose external traces?

| Need | Recommendation |
| --- | --- |
| Debugging short flows inside a single JVM | Selective MessageHistory |
| Flows with heavy branching/retries | MessageHistory + logs/traces by eventId |
| Across services, brokers, and networks | Distributed tracing + explicit trace propagation |
| Messages sitting in stores for days | Bounded headers + external audit/log/trace with retention |
| Proof of committed business work | Durable business audit/outbox, not just history |

Across different services, history does not automatically behave like distributed tracing. A message serializer/adapter may omit the `history` header toward a broker, or a consumer on a different version may not decode outer headers. Carry `traceId` and minimal headers while controlling schemas and mappings.

## 13. Important changes since Spring Integration 6.3

### Before 6.3: copy-on-write logic

The 6.2 documentation describes history as immutable: each tracking step typically created a **new MessageHistory instance** and a new message copy. For long flows, repeated list copying could increase allocations and CPU usage.

### Since 6.3: append-only history container

Newer documentation explains:

- The first tracking step may create a new message with a `MessageHistory` container.
- Subsequent `MessageHistory.write()` calls **append entries** to the existing header, reducing message copies.
- When the framework produces multiple outputs from a single message, components like `PublishSubscribeChannel`, `AbstractMessageRouter`, `WireTap`, or splitters are updated to **clone history** appropriately across branches.

This improves performance, yet **does not mean history size is automatically bounded**. A message passing through thousands of tracked hops can still accumulate thousands of entries.

### Custom fan-out must clone history when building branches

If you write custom components producing multiple messages from one input, prevent two branches from sharing the same mutable history container. With Spring Integration 6.3+ builders, the documented API is:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

// Spring Integration 6.3+ snippet, using Spring Integration's builder.
Message<String> child = MessageBuilder
        .withPayload("child-" + index)
        .copyHeaders(parent.getHeaders())
        .cloneMessageHistoryIfAny()
        .build();
~~~

Here `parent` is the original message and `index` is the branch index. Use this **in custom splitter/multi-output code**, setting correlation/sequence headers as business logic requires. `cloneMessageHistoryIfAny()` gives each branch its own snapshot; do not call it when a single message instance simply continues down one path.

**Import note:** `org.springframework.integration.support.MessageBuilder` differs from `org.springframework.messaging.support.MessageBuilder`. The `cloneMessageHistoryIfAny()` API belongs to Spring Integration's `AbstractIntegrationMessageBuilder`. If your project version lacks this API, check its corresponding header/history copy mechanism instead of pasting an incompatible snippet.

## 14. History across runtime channel/endpoint types

| Component | What happens to the message? | Notable observation |
| --- | --- | --- |
| `DirectChannel` | Synchronous dispatch on sending thread | Hops roughly mirror call stack; exceptions can return to sender |
| `ExecutorChannel` | Handoff to worker thread | Gap between two timestamps may include queue wait |
| `QueueChannel` + poller | Message waits until polled | Gap may include poll interval/timeout and backlog |
| `PublishSubscribeChannel` | One input to multiple subscribers | Separate history needed per branch on multiple outputs |
| Router | Branches by routing key | Each branch should retain its own trace |
| Splitter | One input into many messages | Parent history must be cloned appropriately for children |
| Aggregator/resequencer | Collects multiple messages into a group | Output history does not prove full histories of all merged parts |
| Retry advice | Handler may run multiple attempts | History entry count is not retry count |
| Outbound gateway | Calls externally and awaits reply | Header mapping and reply flow determine how history survives |

When using executors, pollers, or brokers, **timestamp gaps do not diagnose why something is slow**. You need executor queue metrics, poll durations, handler timers, connection pools, and spans to pinpoint where latency sits.

### Aggregators and correlation

`MessageHistory` describes the path of **one specific message**. An aggregator handles multiple messages sharing a `correlationId` with different `sequenceNumber`s. History on the **output message** may reflect only part of the story; it does not replace inspecting `MessageGroupStore` to see every message in the group.

When debugging a stuck group:

1. Check correlation strategy and how many parts the group has received.
2. Check `sequenceNumber`, `sequenceSize`, and release strategy.
3. Inspect the history of **each input message** if still available.
4. Check the message store, locks, transactions, and expiry.
5. Use eventId/correlationId to join logs/spans rather than looking at a single history header.

## 15. ErrorMessage, recovery, and history up to failure

When a handler throws an exception, the failure can:

- Propagate to the caller on `DirectChannel`.
- Be wrapped into an `ErrorMessage` by a poller/executor error handler.
- Be retried within the same invocation by retry advice.
- Be sent to a recovery channel by a recovery callback.
- Become a reactive `onError` signal in another publisher.

**There is no guarantee that `ErrorMessage` always carries its own history representing the full path of the failed message.** On a `MessagingException`, inspect `getFailedMessage()`; on an `ErrorMessage`, inspect `getOriginalMessage()` if provided.

~~~java
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public static Message<?> failedMessage(ErrorMessage error) {
    Message<?> original = error.getOriginalMessage();
    if (original != null) {
        return original;
    }

    Throwable cause = error.getPayload();
    if (cause instanceof MessagingException messaging) {
        return messaging.getFailedMessage();
    }

    return null;
}
~~~

Then:

~~~java
Message<?> failed = failedMessage(error);
MessageHistory history = MessageHistory.read(failed);

logger.warn("eventId={} hopCount={} failure={}",
        failed == null ? "unknown" :
            failed.getHeaders().get("eventId"),
        history == null ? 0 : history.size(),
        error.getPayload().getClass().getSimpleName());
~~~

This snippet is for an error consumer; wrap it in an appropriate class with `logger` and imports. `MessageHistory.read(null)` returns `null` per the API, so there is no need to fabricate a dummy message.

### Do not use history to prove retries

The same message can be retried multiple times **without adding new hops** when advice wraps a single handler invocation. Conversely, a loop re-sending a message across channels can add many hops for a single logical event. To observe retries accurately, measure **attempt count** in the retry policy, assign a stable idempotency key, and record outcomes at recovery.

## 16. History across persistent Message Stores and brokers

When messages are stored in `JdbcChannelMessageStore`, Redis, or MongoDB, encoding the outer `Message<?>` may have to handle the `history` header too. Risks include:

- Serializer/provider unable to read the header representation after upgrades.
- Oversized headers increasing record sizes, network I/O, or allocations.
- Replayed messages carrying old history plus newly appended entries.
- Header mappings dropping history when crossing a broker.
- No indexing/searching by history in the store unless explicitly designed.

### Size-budget scenario when persisting

Suppose a system sets a **16 KiB budget for all encoded headers**. If each encoded hop averages around **250 bytes** in testing, 50 hops already consume roughly **12.5 KiB** before counting other headers. This is an **illustrative assumption**, not a default Spring Integration size or limit.

Planning formula:

\[
B_{\text{headers}} \approx B_{\text{base}} + n \times B_{\text{hop}}
\]

In practice, measure `B_headers` **after serialization** with your actual backend. Java `Properties` has different in-memory overhead than JSON/protobuf bytes; a small JSON header can weigh considerably more on the heap due to object counts.

### Measurements you should take

1. Gather representative messages: short flows, long flows, retries, splitters, many headers.
2. Measure `history.size()` at key endpoints.
3. Encode using the **real** serializer/header mapper of your broker/store.
4. Measure total bytes, header bytes, and history bytes if the mapper allows.
5. Test long message histories on both sending and receiving sides across restarts.
6. Monitor GC, heap, throughput, poll/serialization latency, and queue depth.
7. If a broker enforces a hard cap, verify the contract measures **total** payload + headers and related limits.

Never turn an unmeasured bytes-per-hop guess into an SLA.

## 17. Observability overhead and production trade-offs

Message History is an **observability feature with real cost**.

| Cost | Why it happens | How to reduce |
| --- | --- | --- |
| Allocation/heap | `Properties` entries and history containers | Track a subset, bound loops, summarize at boundaries |
| CPU | Recording hops, copying/cloning branches, serialization | Disable when unneeded, measure overhead, use tracing/metrics |
| GC pressure | Many live messages and history entries | Lower message retention, reduce hop counts |
| Network/backend bytes | Headers entering queues/brokers/stores | Strip full history across boundaries when unnecessary |
| Log volume | Formatter printing full headers/history | Log last N entries + eventId/traceId |
| Privacy | Component names/topology can expose internal details | Mask/redact, limit exports and retention |
| Debug ambiguity | Missing hops due to patterns, toggles, or dropped headers | Record active config/version and verify behavior |

**Turning off history everywhere is not the only optimization.** You can enable it temporarily during an incident window, track strategic components only, log at DEBUG level, and rely on distributed tracing/metrics for continuous low-overhead latency monitoring.

### When should tracking be turned off?

- A flow loops many times, leaving each message with thousands of entries.
- The persistent store or broker enforces a small header limit.
- A trace/log backend already supplies the needed path at lower cost in your environment.
- Profiling shows CPU/heap dominated by history tracking.

Before turning it off, ensure `eventId`, `traceId`, correlation, and error records remain sufficient for investigations.

## 18. Useful metrics and dashboards

| Suggested metric | Meaning | Notes |
| --- | --- | --- |
| `message.history.entries` distribution | Entry count when a message reaches a checkpoint | p50/p95/p99, per endpoint |
| `message.history.over_budget` count | Messages exceeding the entry budget | Never tag full message IDs |
| `message.history.preview.length` | Summary/log length | Does not replace byte-size measurement |
| `message.header.encoded.bytes` | Total header bytes after serialization | Per adapter/store format |
| `message.flow.duration` | End-to-end latency | Based on tracing/timestamps at proper boundaries |
| `message.store.write.latency` | Persistence cost | Separate encoding from DB I/O |
| `poller.duration` / `queue.oldest.age` | Backlog / slow poller | History gaps may include queue wait |
| `handler.error.count` / `retry.attempts` | Actual errors and attempts | Do not infer from history size |

The names above are **instrumentation suggestions**; not all exist out of the box in Spring Integration or Micrometer.

Never use `eventId`, `orderId`, or the full history string as **metric labels**, because cardinality becomes far too high. Use endpoint name, channel, outcome, and application version. Put correlation IDs and business IDs in logs/traces per security policy.

An example budget warning in a handler:

~~~java
MessageHistory history = MessageHistory.read(message);
int entries = history == null ? 0 : history.size();

if (entries > 32) {
    logger.warn("history budget exceeded: endpoint={} entries={} eventId={}",
            "ordersHandler", entries, message.getHeaders().get("eventId"));
}
~~~

This snippet **warns** without trimming the header. To actually reduce overhead, use the tracking scope and boundary compaction techniques described above.

## 19. Versions and APIs: what to verify before upgrading

| Version / aspect | Key detail |
| --- | --- |
| Spring Integration 6.2 and earlier | Immutable/copy-on-write history model as documented for those versions |
| Spring Integration 6.3+ | Append-only history inside the container; framework clones at known fan-out points |
| `@EnableMessageHistory` | Selectively enables component names/patterns; no documented `maxEntries` setting |
| `MessageHistoryConfigurer` | Has runtime lifecycle/JMX; must stop configurer before changing patterns |
| `MessageHistory.read(message)` | Reads header; may return `null` |
| `cloneMessageHistoryIfAny()` | 6.3+ Spring Integration builder API for custom fan-out |
| Persistent stores | Must verify serializer/headers/schema and legacy data across restarts |
| Running endpoints | Not all components are named or trackable identically |

When upgrading from 6.2 to 6.3+, business code **must not** assume `MessageHistory` is always a fresh immutable instance. Audit cases where splitters/custom routers produce multiple outputs and any code holding references to old messages' histories.

## 20. Diagnosing common scenarios

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Message has no `history` header | Not enabled, pattern mismatch, no tracked component traversed yet | Check `@EnableMessageHistory`, IDs, `MessageHistory.read()` |
| History has only a few hops | Subset tracked or unsupported segment | Compare component list with integration graph |
| History disappears after a broker | Header mapper/serializer stripped header | Inspect actual encoded headers and adapter |
| History grows very rapidly | Flow loop, requeue through tracked channels | Look for repeating `name/type` in timeline |
| History size differs from retry count | Retry advice runs handler invocations without adding hops | Measure retry counter separately |
| Fan-out branches share mixed history | Custom multi-producer shares mutable history (6.3+) | Clone history per branch |
| `history.toString()` bloats logs | Logging full headers | Log only tail N with character cap |
| Message store size grows | Persisted headers carry many entries | Measure encoded bytes, reduce tracked components/reset at boundary |
| Long timestamp gaps appear | Queue wait, scheduler, I/O, or retries | Correlate poller/executor/handler metrics |
| Handler reports success yet DB rolls back | History tracks path only, not commit outcome | Inspect transaction logs/DB |
| ErrorMessage has no history | Missing original message or failed message | Inspect `getOriginalMessage()`/`getFailedMessage()` |
| Runtime pattern change rejected | Configurer is currently running | Stop configurer, change patterns, restart |
| Tracked patterns differ across nodes | Each application context configured differently | Align configs, verify deployed version |
| Message history exceeds broker limit | No limit enforced at serialization boundary | Bounded summary + remove header, test real bytes |

### Evidence-based debugging workflow

1. **Identify the message:** eventId, correlationId, traceId, and source.
2. **Cross-reference the graph:** which components actually have IDs, which endpoints are started/stopped.
3. **Inspect the configurer:** is tracking enabled, which patterns are active, what app version is running.
4. **Read history:** use `MessageHistory.read()` and capture a short snapshot for analysis.
5. **Examine timing:** do timestamp gaps align with queue wait, poll intervals, or I/O?
6. **Spot loops/retries/fan-out:** distinguish message looping from single-handler retries.
7. **Check actual bytes:** does the serializer/broker/store preserve history, and how large are headers?
8. **Evaluate mitigations:** select fewer components, log tails, or compact at boundaries.
9. **Retest:** restarts, async, splitters, aggregators, and recovery paths.
10. **Confirm business completion only** when the DB/broker/error store verifies the outcome.

## 21. Hands-on exercises

1. **Toggle on/off:** run `MessageHistoryDemoApplication` with and without `@EnableMessageHistory`, comparing `MessageHistory.read()` and logs.
2. **Filter components:** replace the annotation with patterns matching `ordersIn` and `normalizedOrders`; explain which entries remain and which disappear.
3. **Measure long history:** create a bounded loop in a test environment and measure `history.size()` by iteration count (avoid infinite loops).
4. **Tail projection:** use `HistoryProjection.recentHopNames(message, 5)`; confirm logs show at most five names while the original header stays untouched.
5. **Character cap:** cap the summary at 300 chars; compare the character limit against UTF-8 bytes after encoding.
6. **Boundary reset:** insert `HistoryBoundary.compactBeforePersistence(...)` before a test channel/store; compare size before/after and observe fresh history starting if downstream is tracked.
7. **Fan-out:** on Spring Integration 6.3+, build a two-branch custom splitter; clone history and observe branch-specific hops.
8. **Executor:** place an `ExecutorChannel` between two handlers, log threads and timestamps, and explain why gaps are not purely handler latency.
9. **Poller:** add a `QueueChannel` and polling consumer, letting messages wait a few seconds; compare history gaps, queue age, and poller duration.
10. **Retries:** add `RequestHandlerRetryAdvice` causing a handler to fail twice before succeeding; compare retry attempt count against history entries.
11. **Error flow:** throw an exception in a handler and read history from `ErrorMessage.originalMessage` or `MessagingException.failedMessage` if present.
12. **Persistence:** use a real persistent message store, write and restart, and verify history/header serialization and length after replay.
13. **Runtime toggle:** if JMX exporter is enabled, stop `MessageHistoryConfigurer`, update tracked patterns, restart it, and note which events lacked tracking during the transition.
14. **Observability budget:** determine the target adapter/broker's header byte limit, measure real data, and write a compaction/alerting policy.
15. **Compare with tracing:** enable tracing/Micrometer for your stack and identify what Message History captures that spans miss, and vice versa.

### Self-check questions

- How do `MessageHistory` and `MessageStore` differ?
- Does `tracked-components` guarantee history stays under 20 entries? Why or why not?
- When can `MessageHistory.read(message)` return `null`?
- Why does logging only the last 5 hops fail to shrink persisted messages?
- What changed in Spring Integration 6.3 for history appending and cloning?
- When a message is retried three times, must history grow by three entries?
- Why are `timestamp` gaps insufficient to infer handler processing time?
- When crossing a broker, how do you verify whether history was actually serialized?
- Can `MessageHistoryConfigurer` change patterns while running?
- Does a message with a complete history prove a database transaction committed?

## 22. Pre-production checklist

- Stable IDs/patterns exist for components needing tracking; enabled only for genuinely useful scope.
- Never assume `@EnableMessageHistory` enforces an automatic entry cap.
- Know the **actual header byte limits** of your store/broker/adapters.
- Avoid logging full history unnecessarily; use projections and character limits.
- When resetting history, do so at explicit boundaries while preserving required `eventId`, `traceId`, correlation, and sequence headers.
- On 6.3+, custom multi-producers clone history so branches do not interfere with each other.
- Metrics exist for history size, message latency, errors/retries, and queue/store pressure.
- Tested loops, retries, fan-out, executors, pollers, and restarts.
- Never use history to infer commits, acks, exactly-once delivery, or business audits.
- Control Bus/JMX tracking configuration is access-restricted and audited.
- Handle data privacy: internal topology/component names are not leaked to public logs/brokers.
- Have a runbook if history causes memory/serialization pressure: narrow patterns, log tails, compact at boundaries, and re-measure.

## 23. Official references

- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): enabling, `tracked-components`, JMX configurer, and append-only changes since 6.3.
- [Spring Integration 6.2 — Message History](https://docs.spring.io/spring-integration/reference/6.2/message-history.html): pre-6.3 behavior.
- [Spring Integration API — MessageHistory](https://docs.spring.io/spring-integration/api/org/springframework/integration/history/MessageHistory.html): `read`, `write`, `HEADER_NAME`, `NAME_PROPERTY`, `TYPE_PROPERTY`, `TIMESTAMP_PROPERTY`.
- [Spring Integration API — MessageHistoryConfigurer](https://docs.spring.io/spring-integration/api/org/springframework/integration/history/MessageHistoryConfigurer.html): lifecycle, patterns, requirement to stop before modifying.
- [Spring Integration API — AbstractIntegrationMessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/AbstractIntegrationMessageBuilder.html): `cloneMessageHistoryIfAny()`.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics-management.html): integration management, observability, and version-specific metrics.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistence and header interaction.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, ExecutorChannel, QueueChannel, PubSub.
- [Micrometer Observation Documentation](https://docs.micrometer.io/micrometer/reference/observation.html): observations and tracing/metrics.
