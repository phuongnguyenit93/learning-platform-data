# Tracking the current step in the message

**Routing Slip** is an Enterprise Integration Pattern (EIP) in which a message carries its own processing itinerary. Rather than each endpoint hardcoding the next step, Spring Integration can read a header containing the legs to traverse and update a **position pointer** after each channel selection.

This lesson belongs to the **Routing slip** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, extensible message flows with testing and per-branch observability.

The focus here is **tracking the current step in the message**: the structure of the `routingSlip` header, the meaning of `routingSlipIndex`, when the pointer changes, how to read it safely, and why it cannot be used as proof that a business step has completed.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Describe how Routing Slip differs from a Router and a static chain of channels.
2. Explain the `routingSlip` header structure consisting of **path** and **index**, where the index starts at 0.
3. Distinguish **currently executing handler**, **leg already selected**, and **leg to be evaluated next**.
4. Identify when Spring Integration uses the routing slip: **a message-producing endpoint produces a reply without an explicit `outputChannel` configured**.
5. Explain why a channel name increments the index, whereas a `RoutingSlipRouteStrategy` can keep the index unchanged across multiple calls.
6. Initialize an itinerary using `HeaderEnricher` or Java DSL, then record progress in a Java application.
7. Write JUnit tests verifying each leg and each index value in a real flow.
8. Recognize scenarios involving infinite loops, lost headers, reply timeouts, retries, serialization, and untrusted data.

## 2. Routing Slip: an itinerary traveling with the message

Suppose an order must be processed through three steps: `prepare`, `validate`, and `save`. One way to configure this is wiring three channels statically. With Routing Slip, you can declare the entry step first and carry subsequent steps directly inside metadata.

~~~mermaid
flowchart LR
    IN["Request / Gateway"] --> EN["HeaderEnricher"]
    EN --> A["prepare"]
    A -->|"routingSlip: validate"| B["validate"]
    B -->|"routingSlip: save"| C["save"]
    C -->|"path exhausted"| R["replyChannel"]
~~~

Example:

~~~text
message payload:
  orderId: ORDER-1001

message headers:
  traceId: trace-1001
  businessCorrelationId: ORDER-1001
  routingSlip:
    path: [validateChannel, saveChannel]
    index: 0
~~~

The snippet above is a **conceptual illustration for learning**, not JSON or Spring's actual serialized format. The message has a dedicated header named `routingSlip` with an internal structure representing path/index.

When the `prepare` handler produces a reply, the framework picks `validateChannel` from the path and increments the pointer in the reply. After `validate` produces a reply, the framework picks `saveChannel` and increments the pointer again. Finally, when no elements remain in the itinerary, normal reply handling resumes.

**Routing Slip is not an audit trail.** It stores the **intended path and routing progress position**, not commit statuses, completion timestamps, or successful side effects of each handler.

### Comparing related patterns

| Model | Purpose | Difference when tracking |
|---|---|---|
| **Content-Based Router** | Pick destination from payload or headers at decision time | Does not inherently retain an itinerary pointer on the message |
| **Header-Based Router** | Map a header value to a channel | Header is typically a routing key, not the full itinerary |
| **Routing Slip** | Message carries step list and next evaluation position | Has **path + index** on the message |
| **Recipient List Router** | Pick multiple recipients conditionally | Can fan out to multiple destinations |
| **Publish–Subscribe** | Broadcast to registered subscribers | Does not inherently manage a sequential itinerary |
| **Process Manager** | Coordinate multi-step processes with complex state | May require external state/persistence/recovery beyond headers |

If a process only has a few always-fixed steps, an `IntegrationFlow` chaining endpoints is easier to understand. Routing Slip is most valuable when **the itinerary can vary per message** or involves dynamic decision strategies.

## 3. What does the routingSlip header contain?

Spring Integration uses the constant `IntegrationMessageHeaderAccessor.ROUTING_SLIP`. When created by `RoutingSlipHeaderValueMessageProcessor`, the value typically has the form **`Map<List<Object>, Integer>`** containing a single entry:

- **Key**: `List<Object>` is the ordered path, containing channel names, strategy beans, or framework-processed strategy components.
- **Value**: `Integer` is `routingSlipIndex`, indicating the next position in the path to evaluate.

~~~text
routingSlip = {
  ["validateChannel", "saveChannel"] : 0
}
~~~

This illustrates the meaning of the map. **There is no separate top-level message header named `routingSlipIndex` automatically created under this model.** To read the index, read the `routingSlip` header value and extract the value of the path/index entry.

### 3.1. Meaning of the index

Suppose `path = ["validateChannel", "saveChannel"]`:

| Index value | Next leg to evaluate | What can be concluded |
|---:|---|---|
| 0 | `validateChannel` | First channel element has not been selected yet |
| 1 | `saveChannel` | Element at position 0 has already been selected as destination |
| 2 | End of path | No static entries left to select |
| Any value outside 0..2 | Data requiring inspection | Never manually mutate index to "keep going" |

A very common mistake is reading `routingSlipIndex=1` inside the `validateChannel` handler and concluding that the validate step has completed. In fact, the index was incremented **before the message was even delivered to the validate handler**; that handler may not have performed any business work yet.

### 3.2. Three concepts to keep distinct

1. **Current handler**: name of the endpoint currently processing the message, e.g., `validate`.
2. **Next path index**: position Routing Slip will evaluate next when a reply is produced and needs an output channel, e.g., `1`.
3. **Business completion**: real business state, such as "validation passed", "database committed", or "notification delivered".

The system must record each concept in its proper place. `RoutingSlipIndex` **does not replace** transaction outcomes or tracing spans.

### 3.3. Routing slip differs from other metadata

| Header/field | Meaning |
|---|---|
| `routingSlip` | Coordinates flow path/index |
| `MessageHeaders.ID` | ID of a message instance; can change when a new message is built |
| `traceId` | Traces journey across multiple endpoints/services |
| `businessCorrelationId` | Links messages of the same order/transaction |
| `replyChannel` | Return path for replies in request–reply |
| `errorChannel` | Path for error messages in supported topologies |
| `sequenceNumber`/`sequenceSize` | Metadata for Splitter/Aggregator when grouped |

## 4. When does Spring Integration consult the routing slip?

Routing Slip is integrated into Spring Integration inside the **output channel selection** mechanics of `AbstractMessageProducingHandler`.

Core conditions:

1. The endpoint receives a request message.
2. The endpoint **produces a reply**.
3. The endpoint **has no directly declared `outputChannel`**.
4. The framework inspects the `routingSlip` header to find a channel for the reply.

~~~mermaid
flowchart TD
    I["Request message arrives at endpoint"] --> P{"Produces reply?"}
    P -->|No| STOP["No reply to continue slip"]
    P -->|Yes| FIX{"Endpoint has fixed outputChannel?"}
    FIX -->|Yes| OUT["Use configured outputChannel"]
    FIX -->|No| SLIP{"Routing slip has entries left?"}
    SLIP -->|Yes| NEXT["Evaluate path[index]"]
    SLIP -->|No| REPLY["Use normal replyChannel"]
    NEXT --> SEND["Send reply to chosen destination"]
~~~

**Two important consequences:**

- If you declare `outputChannel="next"` on an endpoint, do not expect the routing slip to pick a different channel at that endpoint. Explicit output channel configuration takes precedence.
- If an endpoint returns `void`, or emits no reply at all, Routing Slip does not automatically "pump" a new message to the next step.

Example of a handler that follows the routing slip:

~~~java
import org.springframework.integration.annotation.ServiceActivator;

public class PrepareHandler {
    @ServiceActivator(inputChannel = "prepareChannel")
    public String prepare(String payload) {
        return payload + "|prepared";
    }
}
~~~

The method above creates a reply with the resulting string and **does not** specify a fixed output channel. If a valid `routingSlip` header is present, the reply can continue along the path.

Conversely:

~~~java
@ServiceActivator(
        inputChannel = "prepareChannel",
        outputChannel = "fixedChannel")
public String prepareWithFixedChannel(String payload) {
    return payload + "|prepared";
}
~~~

Here an output channel is declared, so the endpoint dictates the route instead of Routing Slip.

## 5. How Spring updates routingSlipIndex

### 5.1. Path entry is a channel name

When `path[index]` is a `MessageChannel` bean name, the framework uses that name to resolve the target channel and **increments the index on the reply message**.

Suppose:

~~~text
path = [validateChannel, saveChannel]
index = 0
~~~

After `prepare` produces a reply and selects `validateChannel`, the message arrives at validate with index **1**. When `validate` produces a reply and selects `saveChannel`, the message arrives at save with index **2**.

~~~mermaid
sequenceDiagram
    participant A as prepare
    participant B as validateChannel
    participant C as saveChannel
    participant R as replyChannel

    Note over A: path=[validate,save], index=0
    A->>B: Reply to validate, index=1
    Note over B: B is running, index is already 1
    B->>C: Reply to save, index=2
    Note over C: C is running, path exhausted
    C-->>R: Final reply
~~~

Never call index 1 "validate finished"; it only tells you **validate was selected as the destination** and the pointer moved to the next candidate.

### 5.2. Path entry is a RoutingSlipRouteStrategy

A path can also contain a `RoutingSlipRouteStrategy`. The interface defines the method:

~~~text
RoutingSlipRouteStrategy (Spring Integration API):
    Object getNextPath(Message<?> requestMessage, Object reply)
~~~

This is the **method signature of the library interface**, not a requirement to recreate an identically named interface in application code. The real implementation example in section 5.3 uses the interface imported from Spring Integration.

Special rules:

- If `getNextPath` returns **a valid channel name or channel**, the framework uses that target **without incrementing the index**.
- If `getNextPath` returns `null` or an empty string `""`, the framework **increments the index**, then looks at the next element.
- A strategy can be invoked repeatedly at the same position until no more destinations remain to execute.

| Strategy call at index 0 | Return value | Index after decision | Interpretation |
|---|---|---:|---|
| 1 | `"reviewChannel"` | 0 | Continue review |
| 2 | `"reviewChannel"` | 0 | Continue review again |
| 3 | `null` | 1 | Skip past strategy, evaluate next item |
| Item 1 is `"archiveChannel"` | `"archiveChannel"` | 2 | Selected archive |

**Warning:** if a strategy always returns the same channel without a stop condition, the message can loop forever. Enforce iteration limits, timeouts, and retry/idempotency policies.

### 5.3. Example of a conditional strategy

~~~java
import org.springframework.integration.routingslip.RoutingSlipRouteStrategy;
import org.springframework.messaging.Message;

// Illustrative domain type:
record ReviewState(int remainingChecks) {}

public final class OptionalReviewStrategy
        implements RoutingSlipRouteStrategy {

    @Override
    public Object getNextPath(
            Message<?> requestMessage, Object reply) {

        if (reply instanceof ReviewState state) {
            return state.remainingChecks() > 0
                    ? "reviewChannel"
                    : null;
        }
        return null;
    }
}
~~~

This is an example of **policy**, not a complete flow configuration. In practice, `reply` can be a **domain object**, `Message<?>`, or `AbstractIntegrationMessageBuilder` depending on the endpoint. Strategies must handle the exact types actually passed to them; never assume it is always `ReviewState`.

If controlled iteration is desired, the handler must return a `ReviewState` updating `remainingChecks`; once no steps remain, the strategy returns `null` so the index increments. **Never use `routingSlipIndex` itself as an iteration counter**, since the index stays unchanged while the strategy keeps returning channels.

## 6. Properly initializing a Routing Slip

Spring Integration provides `RoutingSlipHeaderValueMessageProcessor`, a header processor used with `HeaderEnricher`. It creates the proper path/index structure and prepares channel/strategy name resolution.

### 6.1. Java configuration using HeaderEnricher

~~~java
import java.util.Collections;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.transformer.HeaderEnricher;
import org.springframework.integration.transformer.support.RoutingSlipHeaderValueMessageProcessor;

@Configuration
class RoutingSlipHeaderConfiguration {

    @Bean
    @Transformer(
            inputChannel = "slip.input",
            outputChannel = "slip.prepare")
    HeaderEnricher routingSlipHeaderEnricher() {
        return new HeaderEnricher(
                Collections.singletonMap(
                        IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                        new RoutingSlipHeaderValueMessageProcessor(
                                "slip.validate",
                                "slip.finish")));
    }
}
~~~

Meaning:

- `slip.input` is the channel receiving messages that do not yet have a routing slip.
- Header enricher creates `routingSlip` with path containing `slip.validate` and `slip.finish`, initial index 0.
- Header enricher declares **`outputChannel=slip.prepare`**, so the `prepare` leg runs first.
- The `prepare` handler has no output channel, so it uses the routing slip to reach `slip.validate`; then `validate` uses the next element.

**Do not put both configuration variants in this lesson into a single Spring context**: the next section provides a separate complete configuration to illustrate the flow.

### 6.2. Java DSL equivalent

In Spring Integration versions with `HeaderEnricherSpec.routingSlip(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow routeEntrance() {
    return IntegrationFlow.from("slip.input")
            .enrichHeaders(h ->
                    h.routingSlip("slip.validate", "slip.finish"))
            .channel("slip.prepare")
            .get();
}
~~~

Use **one** configuration for the `slip.input` intake; do not simultaneously declare an annotated enricher and a DSL flow listening to the same `DirectChannel` if your intent is a single sequential chain.

### 6.3. Do not set routingSlip manually as a string

~~~java
// Anti-pattern: not the routingSlip structure expected by the framework.
MessageBuilder.withPayload("ORDER-1001")
        .setHeader("routingSlip", "slip.validate;slip.finish")
        .build();
~~~

A valid routing slip consists of path/index. Attaching an arbitrary string does not mean Spring will parse it like a processor-generated header. Use HeaderEnricher/DSL or the official API matching your library version.

## 7. Tracking step-by-step by reading a snapshot

To observe a routing slip, write a function that only **reads** and creates a snapshot. Never cast directly to `Map<List<String>, Integer>` because the path can contain strategy objects, not just strings.

### 7.1. A data type for observation

~~~java
public record StepObservation(
        String stage,
        int nextIndex,
        int pathSize,
        String nextEntry,
        String traceId
) {}
~~~

Field meanings:

- `stage`: handler where state is recorded.
- `nextIndex`: routing slip index at the moment of observation.
- `pathSize`: number of elements in the path.
- `nextEntry`: next candidate name if it is a channel string, or a generic label.
- `traceId`: separate metadata linking observations together.

### 7.2. Reading a routingSlip header

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public final class SlipInspector {

    private SlipInspector() {}

    public static StepObservation snapshot(
            String stage, Message<?> message) {

        Object raw = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.ROUTING_SLIP);

        if (!(raw instanceof Map<?, ?> slip) || slip.size() != 1) {
            throw new IllegalArgumentException(
                    "Routing slip header is missing or malformed");
        }

        Map.Entry<?, ?> entry =
                slip.entrySet().iterator().next();

        if (!(entry.getKey() instanceof List<?> path)
                || !(entry.getValue() instanceof Integer index)) {
            throw new IllegalArgumentException(
                    "Expected path list and integer index");
        }

        if (index < 0 || index > path.size()) {
            throw new IllegalArgumentException(
                    "Invalid routing slip index");
        }

        String nextEntry;
        if (index == path.size()) {
            nextEntry = "<end>";
        } else if (path.get(index) instanceof String name) {
            nextEntry = name;
        } else {
            nextEntry = "<strategy-or-channel>";
        }

        return new StepObservation(
                stage,
                index,
                path.size(),
                nextEntry,
                message.getHeaders().get("traceId", String.class));
    }
}
~~~

This function demonstrates reading the **path/index structure** without mutating the header. In production, you might log only `stage`, `index`, and `size`, or **allowlist** channel names safe to log so you avoid exposing internal bean names, expressions, or sensitive details.

### 7.3. Why not modify the header directly?

~~~java
// Do not manually mutate the map inside routingSlip:
Object raw = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.ROUTING_SLIP);

// Avoid casting and calling put(...), editing the path list, or "incrementing index" by hand.
~~~

`MessageHeaders` has a readable map structure, yet header values can still contain complex objects. Mutating path/index outside the framework mechanism can corrupt state, cause loops, or skip steps. Let Spring update the pointer when it selects a channel for a reply.

## 8. Three-leg example: prepare, validate, finish

A complete flow lets you see the index advance **0 → 1 → 2**. Handlers use `@ServiceActivator` and **do not declare `outputChannel`**, so their replies can follow the routing slip.

### 8.1. Handler recording observations for testing

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

public final class SlipStages {

    private final List<StepObservation> states =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "slip.prepare")
    public String prepare(Message<String> input) {
        states.add(SlipInspector.snapshot("prepare", input));
        return input.getPayload() + "|prepared";
    }

    @ServiceActivator(inputChannel = "slip.validate")
    public String validate(Message<String> input) {
        states.add(SlipInspector.snapshot("validate", input));
        return input.getPayload() + "|validated";
    }

    @ServiceActivator(inputChannel = "slip.finish")
    public String finish(Message<String> input) {
        states.add(SlipInspector.snapshot("finish", input));
        return input.getPayload() + "|finished";
    }

    public List<StepObservation> observations() {
        return List.copyOf(states);
    }

    public void resetForTest() {
        states.clear();
    }
}
~~~

The `CopyOnWriteArrayList` here is an observation fixture for testing; real applications need logging/metrics/tracing rather than storing unbounded lists in memory.

### 8.2. Configuring the channels

~~~java
import java.util.Collections;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.transformer.HeaderEnricher;
import org.springframework.integration.transformer.support.RoutingSlipHeaderValueMessageProcessor;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class SlipFlowConfiguration {

    @Bean(name = "slip.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "slip.prepare")
    public MessageChannel prepareChannel() {
        return new DirectChannel();
    }

    @Bean(name = "slip.validate")
    public MessageChannel validateChannel() {
        return new DirectChannel();
    }

    @Bean(name = "slip.finish")
    public MessageChannel finishChannel() {
        return new DirectChannel();
    }

    @Bean
    @Transformer(
            inputChannel = "slip.input",
            outputChannel = "slip.prepare")
    public HeaderEnricher routingSlipHeaderEnricher() {
        return new HeaderEnricher(Collections.singletonMap(
                IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                new RoutingSlipHeaderValueMessageProcessor(
                        "slip.validate", "slip.finish")));
    }

    @Bean
    public SlipStages slipStages() {
        return new SlipStages();
    }
}
~~~

This is the **complete configuration for the example**, replacing `RoutingSlipHeaderConfiguration` from section 6. If placing all these classes in a project, put them in appropriate packages with imports; keep only one `slip.input` declaration and one header-initializing endpoint.

### 8.3. Timeline inside the message

~~~mermaid
sequenceDiagram
    participant E as HeaderEnricher
    participant A as prepare
    participant B as validate
    participant C as finish
    participant R as replyChannel

    E->>A: path=[validate,finish], index=0
    Note over A: Observes index=0, next=validate
    A->>B: Reply, index=1
    Note over B: Observes index=1, next=finish
    B->>C: Reply, index=2
    Note over C: Observes index=2, next=end
    C-->>R: Final reply
~~~

| Currently executing handler | Observed index | Next element | What must NOT be inferred |
|---|---:|---|---|
| `prepare` | 0 | `slip.validate` | Validate has not necessarily been called yet |
| `validate` | 1 | `slip.finish` | Validate has not necessarily finished business logic |
| `finish` | 2 | End of path | DB write has not necessarily committed |
| Final reply | Itinerary exhausted | `replyChannel` if present | Does not mean another system received the data |

## 9. Testing the Spring Integration flow and routingSlipIndex

Create a temporary `QueueChannel` to receive the reply, matching the behavior a Gateway expects in a request–reply flow. The test requires no broker or HTTP server.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = SlipFlowConfiguration.class)
class RoutingSlipProgressTest {

    @Autowired
    @Qualifier("slip.input")
    MessageChannel input;

    @Autowired
    SlipStages stages;

    @BeforeEach
    void clearObservations() {
        stages.resetForTest();
    }

    @Test
    void followsPathAndTracksTheNextIndex() {
        QueueChannel replies = new QueueChannel();

        boolean accepted = input.send(
                MessageBuilder.withPayload("ORDER-1001")
                        .setHeader("traceId", "trace-1001")
                        .setReplyChannel(replies)
                        .build());

        assertTrue(accepted);

        Message<?> reply = replies.receive(1000);
        assertNotNull(reply);
        assertEquals(
                "ORDER-1001|prepared|validated|finished",
                reply.getPayload());

        List<StepObservation> observed = stages.observations();

        assertEquals(
                List.of("prepare", "validate", "finish"),
                observed.stream()
                        .map(StepObservation::stage)
                        .toList());

        assertEquals(
                List.of(0, 1, 2),
                observed.stream()
                        .map(StepObservation::nextIndex)
                        .toList());

        assertEquals(
                List.of("slip.validate", "slip.finish", "<end>"),
                observed.stream()
                        .map(StepObservation::nextEntry)
                        .toList());

        assertTrue(observed.stream().allMatch(s ->
                s.pathSize() == 2
                        && "trace-1001".equals(s.traceId())));
    }
}
~~~

This tests **Spring Integration's behavior**, unlike a unit test calling `prepare(...)` directly. When running synchronously with `DirectChannel`, observed order is deterministic in a simple flow. If switching to an executor/broker or scaling concurrency, use independent tests, proper wait timeouts, and avoid sharing state across messages.

### 9.1. Unit test for the routing-slip reader

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class SlipInspectorTest {

    @Test
    void readsIndexAndNextCandidate() {
        List<Object> path = List.of("first", "second");

        Message<String> message = MessageBuilder
                .withPayload("payload")
                .setHeader(
                        IntegrationMessageHeaderAccessor.ROUTING_SLIP,
                        Map.of(path, 1))
                .setHeader("traceId", "trace-42")
                .build();

        StepObservation observed =
                SlipInspector.snapshot("first", message);

        assertEquals(1, observed.nextIndex());
        assertEquals(2, observed.pathSize());
        assertEquals("second", observed.nextEntry());
        assertEquals("trace-42", observed.traceId());
    }

    @Test
    void rejectsMissingHeader() {
        Message<String> message =
                MessageBuilder.withPayload("payload").build();

        assertThrows(IllegalArgumentException.class,
                () -> SlipInspector.snapshot("unknown", message));
    }
}
~~~

This test only checks the **observer** on a map matching the contract; it is not meant to advise constructing `routingSlip` headers manually with `Map.of(...)` in production flows. In real flows, use `HeaderEnricher` to initialize the header via the proper API.

## 10. RoutingSlipRouteStrategy and a repeatable index

Consider the path:

~~~text
path = [reviewStrategy, archiveChannel]
index = 0
~~~

The strategy may pick `reviewChannel` multiple times before returning `null` to advance to `archiveChannel`.

~~~mermaid
flowchart TB
    START["index=0, reviewStrategy"] --> Q{"More review needed?"}
    Q -->|Yes| REVIEW["reviewChannel"]
    REVIEW -->|reply updates state| Q
    Q -->|No: null| NEXT["index=1"]
    NEXT --> ARCHIVE["archiveChannel"]
    ARCHIVE --> END["index=2, end of path"]
~~~

**Tracking takeaway:** even if review runs 5 times, the index on the strategy element can remain **0** across several consecutive passes. To know the review count, track `reviewAttempt` or another application-owned business state field.

### 10.1. Using the index pointer to count completed steps is wrong

~~~java
// Semantically wrong:
int completedSteps = routingSlipIndex;

// Better: track outcomes from each endpoint, correlation,
// and separate iteration counts managed by the application.
~~~

Even when a path contains only channel names, the index increments when **selecting the destination**, not after a downstream DB transaction commits.

### 10.2. Testing the termination condition

A test suite for a strategy should cover:

- When review is needed, `getNextPath` returns a valid channel.
- When finished, `getNextPath` returns `null` or `""`.
- With a maximum review count, the system does not loop forever.
- If the reply has an unexpected type, never cast blindly.
- When the strategy stops, the pointer advances to the next entry.
- When a review invocation fails, retry/idempotency policies apply at the right handler.

Extract decision logic into a pure function when possible for fast testing; add integration tests to confirm Spring actually routes to the right channels.

## 11. Observing with logs, Wire Tap, and traces

Routing Slip helps diagnose **the next planned leg**. To know where a message actually went and whether processing succeeded or failed, record observations at endpoints or channels.

### 11.1. Which fields should be logged?

| Field | Purpose | Note |
|---|---|---|
| `stageName` | Leg currently observed | Obtained from endpoint, never guessed from index |
| `routingSlipIndex` | Next entry to evaluate | Never treat as commit status |
| `pathSize` | Number of entries in itinerary | Not equal to total completed handlers |
| `nextCandidate` | Next destination if known | Only log controlled channel names |
| `traceId` | Trace across multiple spans | Never use as a high-cardinality metric label |
| `businessCorrelationId` | Links same order/transaction | Not synonymous with `MessageHeaders.ID` |
| `eventId` | Identifies event across replays | Supports idempotency |
| `outcome` | SUCCESS/REJECT/ERROR | Derived from actual result |
| `durationMs` | Processing time | Measured at endpoint |

A structured log entry:

~~~text
traceId=trace-1001
stage=validate
routingSlipIndex=1
routingSlipPathSize=2
nextCandidate=slip.finish
outcome=SUCCESS
durationMs=14
~~~

This log entry means `validate` was observed and `nextCandidate` is currently `slip.finish`. **You cannot conclude from that line alone that `slip.finish` processed successfully**.

### 11.2. At what point do Wire Tap and interceptors observe state?

If a `ChannelInterceptor` logs when a message **just arrives** at `slip.validate`, it observes the index already incremented by the previous endpoint when choosing the validate channel. Placing an observation **after** a handler reveals the new reply with an updated pointer.

When multiple executors run concurrently:

- Log lines can appear out of order across threads.
- A single timestamp cannot establish causality.
- Combine trace spans, `eventId`, correlation, and stage names.
- Never log full strategy objects, sensitive headers, or payloads containing personal data.

### 11.3. Useful metrics

You can measure:

- `routing_stage_invocations_total{stage}`.
- `routing_stage_failures_total{stage,type}`.
- `routing_stage_duration_seconds{stage}`.
- `routing_slip_exhausted_total`.
- `routing_strategy_iterations_total{strategy}`.

Only use labels with small value sets; keep `traceId`, `orderId`, and `eventId` in access-controlled logs/traces rather than metric labels.

## 12. Routing Slip and metadata across a Transformer

A Transformer may alter the payload while the Routing Slip must remain on the message. If a Transformer **returns a payload**, Spring Integration typically builds an output message and propagates appropriate headers by default. If a Transformer **returns a complete `Message<?>`**, your code must explicitly preserve required headers.

Example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> normalize(Message<String> input) {
    return MessageBuilder.withPayload(
                    input.getPayload().trim().toUpperCase())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`copyHeaders` suits trusted internal flows; when messages cross brokers/APIs, filter headers selectively at the security boundary. Never blindly copy `replyChannel`, `errorChannel`, tokens, or non-serializable objects to external systems.

If code returns a new message and **drops `routingSlip`**, downstream endpoints lose their itinerary. If it drops `replyChannel`, the Gateway may wait for a reply that never arrives. Add propagation tests across steps that construct new messages.

## 13. With Filter, Router, Splitter, and Aggregator

Routing Slip does not replace the other patterns.

### 13.1. Filter

A Filter decides whether a message may proceed. If it rejects a message without producing a reply, **the Routing Slip path does not advance automatically**. Provide a `discardChannel`, error flow, or explicit rejection result per contract.

### 13.2. Router

A Router picks a branch from payload/headers. Routing Slip carries **an itinerary plan**. If a Router endpoint has an explicit output channel or multiple targets, verify its interaction with the routing slip rather than assuming the index increments like a normal linear leg.

### 13.3. Splitter/Aggregator

A Splitter creates multiple parts with correlation and sequence metadata; Routing Slip is the message's itinerary, not a grouping key. When parts follow different branches:

- Each child message needs metadata appropriate for its own itinerary.
- Avoid sharing mutable payloads or paths across threads.
- The Aggregator needs its own correlation/release strategy and timeout.
- One discarded part can prevent the group from completing.

Never use `routingSlipIndex` in place of `sequenceNumber` or `correlationId`.

### 13.4. Publish–Subscribe

Publish–Subscribe broadcasts one message to multiple subscribers. Routing Slip typically guides one message through a **sequence** of legs. If a fan-out shares a routing slip containing mutable objects, branch behavior becomes unpredictable; design itineraries at the right per-branch level and use immutable snapshots.

## 14. Routing Slip with Gateway and replyChannel

A Gateway sends a request and typically waits for a result within a timeout. Example journey:

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant E as HeaderEnricher
    participant A as prepare
    participant B as validate
    participant C as finish

    G->>E: Request + replyChannel
    E->>A: Slip index=0
    A->>B: Reply index=1
    B->>C: Reply index=2
    C-->>G: Reply when path exhausted
~~~

Once the path is exhausted, Spring Integration reverts to normal `replyChannel` rules. If the reply header is stripped, the final handler returns void, or a looping strategy never stops, the Gateway can time out or fail depending on topology.

Test that the final reply genuinely reaches the Gateway, errors are classified, and deadlines are met. **Index 2 is not confirmation that the Gateway received the reply.**

## 15. Errors, retries, and idempotency

### 15.1. An incremented index does not mean durable success

The framework increments the index when deciding the output channel; sending over the channel, invoking the handler, writing to the DB, or publishing to a broker can fail afterwards. For example, the index already incremented from 0 to 1 when choosing `validateChannel`, yet validation threw an exception before committing.

The system must record the **true outcome** of each step. On retry, know:

- Which handler to retry?
- Which side effects already succeeded before the error?
- Which event ID prevents duplicate processing?
- Should the routing slip replay from the start, or resume from persisted state?
- Which legs are safe to re-run?

### 15.2. Routing Slip does not provide exactly-once

A message can be retried or replayed and wrapped into a new `Message` with a different `MessageHeaders.ID`. Having a particular routing-slip pointer value **does not create idempotency** or transactions across DB/email/broker boundaries.

Use a durable `eventId`, per-side-effect idempotency keys, transactions/outbox where needed, and bounded retries.

### 15.3. Error channel and asynchronous handling

On synchronous channels, exceptions may propagate back to the caller thread. In async flows, errors may route as an `ErrorMessage` to `errorChannel` depending on configuration. Routing Slip does not automatically classify exceptions into retryable vs. permanent data errors.

Place retry/error handling at sensible boundaries and preserve correlation on the error branch. With looping strategies, a permanent error must never send a message back into the same leg forever.

## 16. Routing Slip in distributed environments

Spring Integration documentation highlights an important limitation: **inline SpEL expressions** in a routing slip can be converted by the framework into `ExpressionEvaluatingRoutingSlipRouteStrategy` holding a dependency on `BeanFactory`. Such objects are not convenient serializable data; sending messages across brokers or a persistent `MessageStore` can raise `NotSerializableException`.

Recommendations:

1. Prefer **registered strategy bean names** rather than inline expressions embedded as objects in headers when crossing serialization boundaries.
2. Verify that channel/strategy names make sense in the exact `ApplicationContext` receiving the message.
3. Never assume a `MessageChannel` object in JVM A works directly in JVM B.
4. Test real serialization/deserialization against the adapter or store you deploy.
5. Never let untrusted senders dictate internal channel lists via the `routingSlip` header.
6. If processes must restart/resume after crashes, use persistent state rather than relying solely on in-memory routing slips.

For itineraries spanning multiple services, treat the routing slip as part of a **controlled communication contract**, complete with versioning/allowlists and security policies.

## 17. Common errors and how to diagnose them

### Error 1 — Looking at index and falsely assuming a step completed

**Symptom:** logs show `index=1` inside validate; operators assume validate finished.

**Fix:** also log `stageName` and `outcome`. Index is a routing pointer; handler/transaction outcomes must be logged separately.

### Error 2 — Index never increments

**Possibilities:** path entry is a `RoutingSlipRouteStrategy` that keeps returning a channel; endpoint has a fixed `outputChannel`; observer logs on the same side of a leg.

**Fix:** inspect the path entry type at the index, check how the handler produces replies, and verify interceptor placement.

### Error 3 — Handler has a fixed outputChannel

**Symptom:** reply goes to the fixed channel instead of the routing slip step.

**Fix:** remove `outputChannel` configuration on handlers meant to follow the slip, or intentionally accept that fixed routing takes precedence.

### Error 4 — Strategy loops infinitely

**Symptom:** the same leg runs repeatedly while the index stays unchanged.

**Fix:** strategies must have exit conditions and iteration caps; use dedicated business state, not the index as a counter.

### Error 5 — Handler returns void

**Symptom:** flow stops at a leg even though the path is not exhausted.

**Fix:** endpoints must produce replies to advance, or design an explicit message-forwarding mechanism. Routing Slip does not synthesize replies.

### Error 6 — Header lost after Transformer

**Symptom:** message stops following the path after constructing a new `Message`.

**Fix:** preserve `routingSlip` and required metadata; check whether the method returns a payload or `Message` and verify header propagation settings.

### Error 7 — Path exhausted yet Gateway times out

**Symptom:** index equals path size, caller receives no reply.

**Fix:** check `replyChannel`, whether the final handler emits a reply, and the error flow. Write a test using `QueueChannel` as the reply channel.

### Error 8 — Malformed routingSlip format

**Symptom:** handler or observer cannot interpret header; cast exceptions or routing errors occur.

**Fix:** use `HeaderEnricher` / `routingSlip(...)` instead of attaching arbitrary strings/maps. Validate path/index before inspecting.

### Error 9 — Serialization failure

**Symptom:** `NotSerializableException` when persisting messages or sending across a broker.

**Fix:** avoid non-serializable inline expressions/strategy objects in paths; use bean names as recommended and test with the real adapter.

### Error 10 — Using client data to build unrestricted paths

**Symptom:** callers can pick an unauthorized internal channel.

**Fix:** enforce authentication/authorization and allowlists at ingress; only trusted sources may attach or alter routing slips.

## 18. Practice exercises

**Exercise 1 — Three legs and the pointer.** Use the `prepare → validate → finish` configuration; record stage, path, and index. Assert the three indices **0, 1, 2** and that the final payload passes through all three steps.

**Exercise 2 — Fixed output channel.** Add an `outputChannel` to the validate endpoint, then observe that the routing slip no longer selects the leg at that point. Explain the behavior using Routing Slip eligibility conditions.

**Exercise 3 — One-way handler.** Change `validate` to return `void`; observe whether the message continues and whether the Gateway receives a reply. Add an appropriate reject/error mechanism.

**Exercise 4 — Iterative strategy.** Place a `RoutingSlipRouteStrategy` in the path that returns `reviewChannel` twice and then `null`. Verify the index stays unchanged while the strategy returns a channel, then increments once it stops.

**Exercise 5 — Side-effect-free header observation.** Write `SlipInspector` to take snapshots and test missing headers, malformed structures, negative indices, and indices exceeding path size.

**Exercise 6 — Correlation.** Send multiple distinct orders concurrently; use `traceId` and `businessCorrelationId` to reconstruct per-message observations without grouping by `routingSlipIndex`.

**Exercise 7 — Retries.** Simulate `save` succeeding followed by a failure sending the reply. Design idempotency using `eventId` and describe how replays avoid duplicate writes.

**Exercise 8 — Cross-JVM.** Compare a routing slip containing only channel/bean names against a path containing an inline SpEL object during serialization; verify a configuration supported by your broker/store.

### Self-check questions

1. Where is `routingSlip` stored, and where does the index live inside that header value?
2. Does index 1 inside `validate` prove `validate` has finished?
3. Why can an endpoint with a fixed `outputChannel` bypass the routing slip?
4. If an endpoint emits no reply, does the routing slip automatically generate the next message?
5. When a path entry is a channel name, when does the pointer increment?
6. Why can a strategy be invoked multiple times while the index stays the same?
7. If a strategy always returns the same channel, what happens?
8. When no path entries remain, which mechanism receives the reply?
9. Can `routingSlipIndex` replace Aggregator's `sequenceNumber`?
10. How do you observe true outcomes rather than inferring from the pointer?
11. Why can inline SpEL objects cause errors when serializing messages?
12. What kinds of tests are needed to guarantee reply/error paths and flow safety?

## 19. Implementation checklist

- [ ] Use Routing Slip only when dynamic itineraries add clear value over a static flow.
- [ ] Build the header via `HeaderEnricher` or official routing-slip APIs.
- [ ] Understand path/index and clearly identify **the next index to evaluate**.
- [ ] Endpoints using the slip produce replies and omit unintended fixed `outputChannel`s.
- [ ] Strategies have stop conditions and iteration limits.
- [ ] Never manually mutate the path/index map inside the header.
- [ ] Keep `traceId`, `eventId`, and correlation separate from `routingSlipIndex`.
- [ ] Log each stage with its real outcome, not just the index.
- [ ] Test flows through real channels and assert the index sequence.
- [ ] Check header propagation whenever a Transformer creates a new `Message`.
- [ ] Have `replyChannel`, error flows, timeouts, and retry/idempotency policies.
- [ ] Test header serialization when using brokers or persistent stores.
- [ ] Never allow untrusted callers to choose channels/strategies arbitrarily.
- [ ] Never use Routing Slip as an audit log or sole persistence mechanism.

## 20. Summary

In Spring Integration, **Routing Slip** attaches a **path** and an **index** to a message to determine the next itinerary leg. When an `AbstractMessageProducingHandler` produces a reply without a fixed `outputChannel`, the framework inspects the current element. A **channel-name path entry** increments the index in the reply; a **`RoutingSlipRouteStrategy` path entry** can keep the index unchanged until the strategy returns `null` or `""`. Once the path is exhausted, reply delivery continues via normal `replyChannel` mechanics.

To **track the current step**, combine the pointer with the observed endpoint name, trace/correlation metadata, and processing outcomes. **`RoutingSlipIndex` is not a count of committed steps** and does not replace integration flow testing, retries, idempotency, or monitoring. Using `HeaderEnricher` properly, bounded strategies, structured observability, and strict trust boundaries keeps **SPRING_INTEGRATION_PATTERN** systems flexible, testable, and diagnosable in production.

### References

- Spring Integration Reference — Routing Slip: https://docs.spring.io/spring-integration/reference/router/routing-slip.html
- Spring Integration API — RoutingSlipHeaderValueMessageProcessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/support/RoutingSlipHeaderValueMessageProcessor.html
- Spring Integration API — RoutingSlipRouteStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/routingslip/RoutingSlipRouteStrategy.html
- Spring Integration API — HeaderEnricherSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html
- Spring Integration Reference — Message endpoints: https://docs.spring.io/spring-integration/reference/endpoint.html
