# Avoiding Circular Bridges

**Chapter:** Bridge  
**Topic:** Avoiding Circular Bridges  
**Learning Scope:** `SPRING_INTEGRATION_PATTERN` — implementing Enterprise Integration Patterns (EIP) with Spring Integration to build loosely coupled, extensible message flows; combining Bridge with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, testing, and branch observability.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify a **circular bridge (message routing loop)** in a graph of message channels and endpoints.
2. Distinguish direct loops, indirect loops through Router/Transformer, and loops crossing adapter or broker boundaries.
3. Explain why a loop can cause infinite recursion, exhaust CPU/threads, multiply messages, congest queues, or cause repeated business execution.
4. Design a **one-way** Bridge with clearly defined input and output channel roles so processing paths never return to the input.
5. Use graph diagrams, configuration checks, hop limits, correlation, and idempotency to detect and bound loops.
6. Write tests confirming a message traverses a Bridge the exact expected number of times, terminates, and never returns to the source channel.
7. Separate dangerous routing loops from intentional business loops such as bounded retries or state machines with stopping conditions.

## 2. What Does a Bridge Do in Spring Integration?

A **Bridge** is an Enterprise Integration Pattern whose job is to connect two message channels when no payload modification, business branching, or message transformation is needed. In Spring Integration Java DSL, a bridge endpoint is typically declared with `.bridge()`. It receives a message on the input channel and forwards it to the endpoint's output channel.

A valid flow:

~~~mermaid
flowchart LR
    P["Producer"] --> A["ordersIn"]
    A --> B["Bridge"]
    B --> C["ordersToProcess"]
    C --> H["Service Activator"]
    H --> Z["End / record outcome"]
~~~

Here the Bridge provides an organizational boundary between two channels. No edge leads from `ordersToProcess` back to `ordersIn`, so each message does not automatically return to the same Bridge.

Distinguish these concepts:

| Component | Role | Does It Prevent Loops Automatically? |
|---|---|---|
| `Bridge` | Forwards messages to the output channel. | No; it does not traverse the graph to know it was already visited. |
| `DirectChannel` | Dispatches messages synchronously to handlers/subscribers. | No; synchronous loops can recurse on the same call stack. |
| `QueueChannel` | Holds messages for consumers/pollers to pull later. | No; messages can be pulled and sent right back into the original queue. |
| `ExecutorChannel` | Hands processing off to an asynchronous executor. | No; loops can spawn tasks continuously. |
| `Router` | Chooses target channels by condition. | Safe only if every branch has a stopping rule and never routes back to the source improperly. |
| `Filter` | Passes or drops messages by condition. | Can break loops if the condition changes and is tested; not a default loop guard. |
| `Service Activator` | Executes business logic and may emit a result depending on config. | Can accidentally create a back-edge to input if configured with the wrong output channel. |

**Main point:** A Bridge is one link in a **routing graph**. Its safety depends on all connected endpoints and channels, including error paths, retries, and outbound/inbound adapters.

## 3. When Does a Bridge Loop Form?

Model every channel as a vertex and every forwarding action as a directed edge. If there is a path from channel A through one or more endpoints that eventually returns to A, the graph contains a **cycle**.

A cycle is a warning sign. It becomes a dangerous processing loop when a message traverses the cycle **without an effective stopping condition**.

### 3.1 Direct Loop

~~~mermaid
flowchart LR
    A["channelA"] --> B1["Bridge A → B"]
    B1 --> B["channelB"]
    B --> B2["Bridge B → A"]
    B2 --> A
~~~

Here, a message entering `channelA` passes through `channelB` and is pushed back to `channelA`. Without a stopping condition, this repeats forever.

### 3.2 Indirect Loop Across Multiple Patterns

~~~mermaid
flowchart TD
    A["inputChannel"] --> BR["Bridge"]
    BR --> M["mainChannel"]
    M --> R{"Router"}
    R -->|Valid| H["Business handler"]
    H --> DONE["completedChannel"]
    R -->|Misconfigured branch| OLD["legacyChannel"]
    OLD --> T["Transformer"]
    T --> A
~~~

An individual Bridge may look properly configured, yet a Router branch or Transformer output accidentally sends messages back to the input channel, creating an indirect loop. Therefore, you cannot inspect a Bridge in isolation while ignoring surrounding edges.

### 3.3 Loop Across Two Services

~~~mermaid
flowchart LR
    subgraph S1["Service A"]
        I1["Inbound adapter A"] --> C1["Channel A"]
        C1 --> O1["Outbound adapter A"]
    end
    O1 --> Q1[("Broker topic/queue 1")]
    Q1 --> I2["Inbound adapter B"]
    subgraph S2["Service B"]
        I2 --> C2["Channel B"]
        C2 --> O2["Outbound adapter B"]
    end
    O2 --> Q2[("Broker topic/queue 2")]
    Q2 --> I1
~~~

At the source-code level of each individual service, you might see no cycle. Yet if A publishes to B and B publishes back to A for **the same event** without distinguishing event types or states, messages can loop across the broker. This cannot be solved merely by a `Bridge` inside one application.

## 4. Consequences by Channel Type

The same cyclic graph behaves differently when channel types change.

| Configuration | Common Symptoms | Why Dangerous? |
|---|---|---|
| Two `DirectChannel`s in a loop | Deep recursion, `StackOverflowError`, application instability. | Synchronous forwarding calls back into the handler on the same thread. |
| `ExecutorChannel` in a loop | Rising task count, busy workers, full executor queue, rejected tasks. | Loop spawns continuous work across threads; breaking the call stack does not eliminate the cycle. |
| `QueueChannel` + poller | Messages dequeued then re-enqueued; abnormal backlog and traffic. | Poller keeps re-emitting messages; queue stays perpetually busy. |
| `PublishSubscribeChannel` in a loop | One message fans out into multiple copies, causing amplification. | Fan-out combined with a back-edge multiplies processing counts rapidly. |
| Broker or Kafka topic | Publish/consume rates spike; lag, cost, and retention suffer. | Each cycle can produce a brand-new record, even when previous ACKs/offsets succeeded. |
| Error/retry flow routing back to source | Continuous exceptions and retries; DLQ becomes hard to control. | One failure immediately triggers the exact same failure with no limit or backoff. |

**Switching from `DirectChannel` to `QueueChannel` does not fix a loop.** It only changes how the loop manifests: from single-stack recursion to an enqueue/dequeue loop over time.

### 4.1 Why `send() == true` Does Not Prove Correct Processing

In a local Bridge, `send()` generally indicates the message was accepted by the channel under its contract. It does not prove that the message:

- took the right route;
- passed through only once;
- was not routed back to the source channel;
- finished processing in the final consumer;
- was durably persisted or ACKed by a broker.

A loop can produce **thousands of successful sends** while business work never completes.

## 5. Example of a Circular Configuration to Avoid

The Java DSL snippet below is **only for recognizing a configuration error—do not run it as an app or unit test**, as it causes infinite recursion when both channels are synchronous.

~~~java
// ANTI-PATTERN: DO NOT RUN.
@Configuration
@EnableIntegration
class CircularBridgeConfig {

    @Bean
    MessageChannel channelA() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel channelB() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow aToB() {
        return IntegrationFlow.from("channelA")
                .bridge()
                .channel("channelB")
                .get();
    }

    @Bean
    IntegrationFlow bToA() {
        return IntegrationFlow.from("channelB")
                .bridge()
                .channel("channelA")
                .get();
    }
}
~~~

These two flows form the graph:

~~~text
channelA → bridge(aToB) → channelB
channelB → bridge(bToA) → channelA
~~~

Suppose a producer sends `OrderPlaced` to `channelA`. `DirectChannel` invokes the first Bridge; that Bridge sends to `channelB`; the second Bridge sends back to `channelA`; from there the call chain repeats. Even though payload and headers remain intact, **the routing is wrong**.

If `channelB` is replaced by a `QueueChannel` with a poller, synchronous recursion stops, yet messages are polled and sent right back to `channelA`. The result is still a logical loop.

**You do not need to execute a broken configuration to “prove” it is dangerous.** The dependency graph already reveals the cycle; unbounded tests can hang your test runner.

## 6. Proper Configuration: One-Way Bridge to a Terminal Endpoint

Problem: the application receives `OrderPlaced` events and places them into a queue for a worker to generate invoices. The Bridge only needs to connect the **intake channel** to the **processing queue**, and the worker must finish processing instead of returning the message to the intake channel.

~~~mermaid
flowchart LR
    P["Order publisher"] --> I["ordersIngress"]
    I --> BR["Bridge"]
    BR --> Q[["ordersQueue"]]
    Q --> POL["Poller"]
    POL --> H["Invoice handler"]
    H --> DB[("Invoice DB")]
~~~

Java DSL example illustrating a one-way configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

record OrderPlaced(String eventId, String orderId) {}

interface InvoiceService {
    void createInvoiceOnce(String eventId, String orderId);
}

@Configuration
@EnableIntegration
public class SafeOrderBridgeConfig {

    @Bean
    MessageChannel ordersIngress() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel ordersQueue() {
        return new QueueChannel(100);
    }

    @Bean
    IntegrationFlow ordersBridgeFlow() {
        return IntegrationFlow.from("ordersIngress")
                .bridge()
                .channel("ordersQueue")
                .get();
    }

    @Bean
    IntegrationFlow invoiceProcessingFlow(InvoiceService invoiceService) {
        return IntegrationFlow.from(
                    "ordersQueue",
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(500)
                               .maxMessagesPerPoll(5)))
                .handle(OrderPlaced.class, (event, headers) -> {
                    invoiceService.createInvoiceOnce(
                            event.eventId(), event.orderId());
                    return null; // Complete one-way flow.
                })
                .get();
    }
}
~~~

Explanation:

1. `ordersIngress` receives the initial message.
2. The Bridge forwards one-way to `ordersQueue`.
3. The poller delivers the message to `InvoiceService`.
4. The handler returns `null` to end the one-way flow; it **does not resend** the `OrderPlaced` event to `ordersIngress`.
5. `createInvoiceOnce` is the business idempotency contract. A real implementation must record `eventId` with a unique constraint or appropriate deduplication mechanism.

`QueueChannel(100)` is in-memory and **does not guarantee recovery across restarts**. If the problem requires durable delivery, consider a persistent message store or appropriate broker and test transactions, ACKs, and redelivery. That is a separate concern from whether the graph has a cycle.

### 6.1 Distinguishing a Terminal Branch from a Reply Branch

If the system needs to notify success after creating an invoice, use a **dedicated outcome channel** such as `invoiceCompleted` or a clearly defined reply destination. Never reuse `ordersIngress` itself as the output for completion events.

An easy-to-follow routing example:

~~~text
ordersIngress
    → Bridge
    → ordersQueue
    → InvoiceHandler
    → invoiceCompleted
    → NotificationHandler
    → end
~~~

If `NotificationHandler` needs to emit a follow-up event, it should create a new semantic event such as `InvoiceCreated` with clear business identifiers and send it to the corresponding topic/channel—never republish the raw `OrderPlaced` back to the same source.

## 7. Graph Inspection Rules Before Running

For every configuration, represent forwarding paths as a **directed graph**. Record all edges from:

- Bridge: input channel → output channel.
- Router: input → every selectable channel.
- Transformer/Service Activator with output: input → output.
- Publish/subscribe: input → all subscriber branches that can forward further.
- Gateway or request–reply: request, reply, and timeout/error paths if they lead to other channels.
- Retry and error handlers: where failed or retried messages are sent.
- Outbound/inbound adapters: links across topics, queues, destinations, or HTTP callbacks if traffic can return to the same service.

### 7.1 Cycle Detection Algorithm

A standard approach is DFS with three node states:

- `UNVISITED`: not yet explored.
- `VISITING`: currently on the active DFS path.
- `VISITED`: all outgoing paths from this node have finished exploring.

When DFS reaches a node currently in state `VISITING`, a cycle exists in the modeled edges.

~~~text
detectCycle(graph):
    state = {node: UNVISITED for node in graph}

    visit(node):
        state[node] = VISITING

        for next in graph.outgoing(node):
            if state[next] == VISITING:
                reportCycle(node, next)
            else if state[next] == UNVISITED:
                visit(next)

        state[node] = VISITED

    for node in graph.nodes:
        if state[node] == UNVISITED:
            visit(node)
~~~

DFS runs in `O(V + E)` time for vertices `V` and edges `E` in the collected graph. It identifies suspicious configurations **before sending a single test message**.

You can use strongly connected components algorithms (Tarjan/Kosaraju) to list groups of endpoints/channels that can reach one another. Any strongly connected component with multiple vertices, or a vertex with a self-loop, deserves review.

**Limitation:** dynamic Router expressions, data-driven routing keys, external services, and broker topologies can leave edges missing from a static graph. “No cycles found when scanning code” holds only within the inspected configuration scope; integration tests and runtime monitoring are still required.

### 7.2 Determining Whether a Cycle Is Truly Dangerous

Not every cycle in a topology is wrong. A business retry loop can be **intentional**, provided all of these conditions are proven:

1. The repeat condition is clearly specified.
2. There is a measurable attempt limit, time bound, or termination condition.
3. Each iteration does not cause uncontrolled duplicate business effects.
4. Backoff and resource limits exist.
5. Once limits are exhausted, the message moves to a place that **does not re-enter the loop**, such as quarantine/DLQ or a terminal failure state.

If any of these conditions is missing, the cycle remains a risk that requires redesign.

## 8. Bounded Retries Differ from a Circular Bridge

Consider a payment API failure. Wrong design:

~~~mermaid
flowchart LR
    IN["paymentIn"] --> B["Bridge"]
    B --> H["Payment handler"]
    H -->|Any error| IN
~~~

It immediately pushes the exact same message back to the source without classifying the error or bounding attempts.

A better design:

~~~mermaid
flowchart TD
    IN["paymentIn"] --> H["Payment handler"]
    H --> S{"Outcome"}
    S -->|Success| DONE["Completed"]
    S -->|Transient error| C{"attempt < maxAttempts?"}
    S -->|Permanent error| Q["Quarantine / DLQ"]
    C -->|Yes| D["Backoff / delayed retry"]
    D --> H
    C -->|No| Q
~~~

There is still a path returning to the handler, yet **only within a bounded retry policy** with an explicit terminal destination. Depending on infrastructure, use retry advice, retry topics, delayed queues, or an appropriate scheduler. Never build a circular Bridge to achieve retries.

### 8.1 Hop Limit Is Only a Secondary Defense Layer

Some systems attach an `xHopCount` header to count how many boundaries a message has crossed. For example, the Java helper below increments hop count and rejects once the limit is reached:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HopGuard {

    private HopGuard() {}

    public static Message<?> nextHop(
            Message<?> original, int maxHops) {
        Object raw = original.getHeaders().get("xHopCount");
        int current = raw instanceof Number number
                ? number.intValue()
                : 0;

        if (current < 0 || maxHops <= 0 || current >= maxHops) {
            throw new IllegalStateException(
                    "Message hop limit exceeded: " + current);
        }

        return MessageBuilder.fromMessage(original)
                .setHeader("xHopCount", current + 1)
                .build();
    }
}
~~~

If placed at a mandatory boundary, a message can cross **that boundary** at most `maxHops` times. Still, there are limitations:

- `xHopCount` is metadata; it can be stripped or altered by a Transformer, adapter, header mapper, or another publisher.
- A loop that bypasses the guard is not counted.
- A fan-out can spawn **multiple copies** with the same hop count; hop limits do not fully prevent message amplification.
- When the guard throws an exception, there must be a terminal error handler, and the error flow itself must not loop back.
- Incrementing a header is a **metadata-mutation step**; do not treat it as a default feature of a plain Bridge.

Hop limits are useful to **contain damage and aid diagnosis**; the primary fix remains removing invalid cycles from the topology.

### 8.2 Using Event ID and Business State

If the same `eventId` keeps reappearing, determine whether it is:

- legitimate broker redelivery after an error;
- a routing loop;
- producer republishing on timeout;
- or multiple child events sharing a correlation ID.

Keep `eventId`, `correlationId`, `messageId`, `retryAttempt`, and `traceId` distinct. To prevent duplicate side effects, use the business `eventId` or a stable idempotency key; **never rely solely on Spring's `MessageHeaders.ID`**, because an event can be rebuilt into a new message.

## 9. Router, Filter, Transformer, and Gateway Can Create Indirect Loops

### Router

A Router picks branches dynamically; a misconfigured default output channel pointing back to the input channel sends every unmatched message right back to the start.

Example:

~~~text
ingress -> Router
               |-- type=INVOICE --> invoiceChannel -> done
               |-- type=PAYMENT --> paymentChannel -> done
               |-- default ------> ingress          (WRONG)
~~~

Fix: send unrecognized types to `unknownTypeChannel` and quarantine/alert, or terminate with explicit handling. Never default to “just loop back to input to try again,” because unchanged data produces the exact same classification result.

### Filter

A Filter drops invalid messages. If a Filter routes rejected messages back to the channel right before the Bridge, a loop forms whenever the evaluated fields remain unchanged.

Distinguish **valid skips** (such as an already-processed event), **permanent data errors** (quarantine), and **transient errors** (bounded retry).

### Transformer

A Transformer can build a new payload and alter headers. If a Transformer accidentally changes an event type back to one that causes a Router to pick the prior branch again, an indirect loop arises without an obvious Bridge B → A. Tests should assert the sequence of traversed channels and expectations at each state.

### Gateway and Request–Reply

A Gateway expecting a reply can spawn a new request if the reply is misrouted into the request channel. For instance, a misconfigured `replyChannel` mapping causes the result message to be reinterpreted as an initial request.

With request–reply over a broker, cleanly separate request destinations from reply destinations, correlation IDs, timeouts, late-reply handling, and duplicates. Never share a single topic/queue bidirectionally without unambiguous message classification rules.

## 10. Splitter, Aggregator, and Message Amplification

A Splitter turns one message into multiple child messages. If a branch of child messages loops back to an upstream Splitter or Bridge without a stopping condition, message volume can grow exponentially.

For example, one message splits into three parts, each part loops back to the Splitter head, and splits into three again:

~~~text
Round 0: 1 message
Round 1: 3 messages
Round 2: 9 messages
Round 3: 27 messages
Round 4: 81 messages
~~~

This is a theoretical amplification model where each part produces three new parts; actual numbers depend on Splitter logic, Filters, and which branch loops.

With an Aggregator, duplicated child messages can bloat groups unexpectedly, trigger wrong release strategies, or complete with duplicate data. Define:

- `correlationId` for grouping.
- `sequenceNumber`, `sequenceSize`, or custom release rules.
- Child message identifiers for deduplication.
- Persistent `MessageGroupStore` if groups must survive restarts.
- Timeout rules and handling for incomplete groups.

A plain Bridge does not manage sequence/release state. Do not expect a Bridge to deduplicate repeated child messages.

## 11. Error Channels Can Also Create Loops

Suppose processing fails and sends an `ErrorMessage` to `errorChannel`. If the error handler tries to “recover” by resending the **raw failed message** back to input without limits, the failure can repeat immediately.

A common loop:

~~~mermaid
flowchart LR
    I["inputChannel"] --> H["Handler"]
    H -->|Throw| E["errorChannel"]
    E --> R["Error handler: resend"]
    R --> I
~~~

How to improve:

1. Classify errors as `transient` or `permanent`.
2. Cap retries and add backoff instead of an immediate resend loop.
3. Ensure writing error/DLQ records is **terminal** or uses a separate policy that does not return to the source.
4. If the error handler itself fails, define alerting or propagation rules to avoid generating a new error that loops back to the same channel endlessly.
5. When using inbound broker adapters, clarify who controls ACK/NACK, rollback, and offset commit. Errors appearing on an error channel **do not automatically guarantee** broker redelivery.

**Note:** an exception on `DirectChannel` can propagate synchronously back to the caller; a failure on a poller or async boundary can be emitted as an `ErrorMessage`. Detecting loops requires examining both exception propagation and how error flows tie into transports.

## 12. Broker Loops: ACKs and Durable Messages Do Not Break Cycles

Suppose Service A reads from `orders.in`, forwards through a Bridge to an outbound adapter publishing to `orders.out`. Service B reads `orders.out` and, due to misconfiguration, publishes back to `orders.in`. Both services can ACK/commit successfully **on every single execution** while the system-wide loop keeps spinning.

This exposes three myths:

- “The broker ACKed, so the message is done and won't come back”: false, because a service can publish a brand-new message representing the same event.
- “A durable queue protects the system”: durability preserves messages on crashes, **it does not stop cyclic routing**.
- “Transport exactly-once prevents loops”: duplicate suppression within one transport/transaction scope does not eliminate faulty republishing logic across multiple services or external systems.

Effective defenses include separating topics/queues by message semantics, clarifying producer/consumer roles, event types and versions, routing keys, idempotency, hop/causation metadata, and an intentionally acyclic topology.

Example separation:

| Destination | Role | Valid Consumers |
|---|---|---|
| `orders.created` | Order creation event | Billing, Inventory, Analytics |
| `billing.invoice.requested` | Request to create an invoice | Billing worker |
| `billing.invoice.created` | Invoice creation outcome | Notification, Order status |
| `billing.invoice.failed` | Classified failure event | Recovery/quarantine/operations |

If a consumer of `billing.invoice.created` emits `orders.created` for **the exact same order**, re-examine the business design—that can be an event loop even though topic names differ.

## 13. Runtime Observability and Loop Detection

Beyond static graph reviews, monitor runtime symptoms of message loops.

| Signal | Possible Meaning | Diagnostic Action |
|---|---|---|
| One `eventId` appears many times in a short window | Loop, retry storm, or continuous republishing | Inspect channel/endpoint chain and retry metadata. |
| High `send` counts with few business completions | Messages are cycling through internal steps | Measure terminal completions per event ID. |
| Rising CPU/threads, stack overflow errors | Synchronous loop or async overload | Audit `DirectChannel`, `ExecutorChannel`, and back-edges. |
| Queue depth/consumer lag climbs steadily | Loop regenerating messages or consumer falling behind | Correlate enqueue/dequeue rates and event lineage. |
| DLQ fills with the same payload | Poison message or broken error/requeue policy | Inspect error handlers and stopping conditions. |
| `xHopCount` climbs continuously | Message repeatedly crosses guard boundary | Use traces to pinpoint the cycle. |
| Aggregator groups grow huge / never release | Child messages duplicated or broken correlation/release | Check sequence, duplicates, and group store. |

### 13.1 Logging Enough to Trace the Path

A useful observability record:

~~~text
eventId=evt-501
correlationId=order-723
messageId=<Spring message UUID>
sourceEndpoint=ordersInboundAdapter
currentChannel=ordersIngress
nextChannel=ordersQueue
hopCount=2
retryAttempt=1
traceId=<distributed trace ID>
outcome=forwarded | completed | retried | quarantined
~~~

`hopCount`, `retryAttempt`, and `traceId` must be configured or supplied by the application; Spring Integration does not automatically ensure every message carries all of these fields.

Do not log entire payloads containing personal data, access tokens, or sensitive fields just to detect loops. Identifier metadata, timestamps, processing outcomes, and context are sufficient for investigation.

### 13.2 Inspecting Runtime Graphs

If your environment enables Spring Integration management/observability, use the integration graph and endpoint metrics to verify actual topology against design diagrams. Keep in mind a local graph usually does not show multi-microservice hops or broker republishing.

When metrics indicate a loop, the first step is **identifying the edge returning to the source** and fixing the routing. Rate limiting and pausing the amplifying source can reduce blast radius during an incident, but do not fix the underlying topology bug.

## 14. How to Test for Loops Without Hanging

Do not run a synchronous circular Bridge configuration waiting for a `StackOverflowError`. Prefer tests that are **bounded, timed out, and assertion-driven**.

### 14.1 Static Topology Tests

From declared configuration, collect the edge list:

~~~text
ordersIngress -> ordersQueue
ordersQueue   -> invoiceHandler
invoiceHandler -> terminal
~~~

Verify there is no path from `ordersQueue` or `invoiceHandler` back to `ordersIngress`. With Routers or dynamic endpoints, include every possible target branch, including default/error/retry destinations.

An edge list can serve as a fixture to run `detectCycle(graph)`; you do not even need to boot the full application to execute an infinite loop.

### 14.2 Single-Pass Local Forwarding Test

The test below uses a **one-way Bridge configuration with only two channels**. This is a dedicated fixture for observing output easily; no poller competes for messages.

~~~java
@Configuration
@EnableIntegration
class BridgeOnlyTestConfig {

    @Bean
    MessageChannel testInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel testOutput() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow testBridge() {
        return IntegrationFlow.from("testInput")
                .bridge()
                .channel("testOutput")
                .get();
    }
}
~~~

And the JUnit 5 test:

~~~java
@SpringJUnitConfig(BridgeOnlyTestConfig.class)
class BridgeOnlyTest {

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    PollableChannel output;

    @Test
    void forwardsExactlyOneMessageToTerminalQueue() {
        Message<String> sent = MessageBuilder
                .withPayload("order-723")
                .setHeader("eventId", "evt-501")
                .build();

        assertTrue(input.send(sent));

        Message<?> first = output.receive(1_000);
        assertNotNull(first);
        assertEquals("order-723", first.getPayload());
        assertEquals("evt-501",
                     first.getHeaders().get("eventId"));

        // No edge republishes into testOutput.
        assertNull(output.receive(100));
    }
}
~~~

Spring, JUnit, and Spring Test imports are omitted in the snippet to focus on the pattern. The test verifies **one enqueue and one receive** in an isolated setup. It does not prove an entire multi-service system is cycle-free; that requires graph review and integration testing of the real topology.

### 14.3 Business Tests on Real Paths

In a controlled integration test environment, verify:

1. Send a valid `eventId` to the source channel.
2. Wait for completion at the target channel/DB within a finite deadline.
3. Count how many times the business handler runs; under at-least-once delivery, distinguish **invocations** from **committed effects**.
4. Observe how many times the same `eventId` appears at each endpoint; set reasonable thresholds for expected retries.
5. Verify no publish returns to the source for completed event types.
6. Inject transient handler errors and confirm bounded retries followed by DLQ termination once exhausted.
7. Also test fan-out, Router default paths, failing error handlers, and restarts.

Every test must use timeouts or deadlines; when iteration counts exceed bounds, halt the test source and capture traces rather than letting CI jobs run indefinitely.

## 15. Pre-Deployment Configuration Review Process

A practical review workflow:

| Step | What to Check | Required Outcome |
|---|---|---|
| 1. List channels | Names, channel types, application scope | Clear list of inputs/outputs and owners. |
| 2. List endpoints | Bridge, Router, Filter, Transformer, Splitter, Aggregator, Gateway, adapters | Every endpoint has clear inputs/outputs or terminal role. |
| 3. Build graph | Mark normal, error, retry, and reply edges | Visibility into every path able to return to a source. |
| 4. Detect cycles | DFS/SCC on static graph; evaluate dynamic routing | All cycles classified, justified, and bounded. |
| 5. Verify identity | `eventId`, `correlationId`, headers, and trace context | Ability to track messages across iterations and deduplicate. |
| 6. Check resources | Queue capacities, executors, poll rates, retry delays | No unbounded fast-send loops or explosive fan-out. |
| 7. Test failures | Timeouts, rollbacks, handler errors, ACK/offsets, dead-letter | No unintended returns to source; terminates per policy. |
| 8. Monitor | Hop counts, per-event counts, message age, lag, completed counts | Early anomaly detection and cycle localization. |

When a cycle is found, prioritize **removing the wrong edge** or separating channel roles. Add hop-count guards only after fixing the architecture so guards serve as a second line of defense.

## 16. Common Design Mistakes

1. **Setting a Bridge's output equal to its own input** or creating symmetric Bridges A → B and B → A.
2. **Confusing async with loop removal:** switching `DirectChannel` to an executor/queue only hides the loop as continuous tasks or enqueues.
3. **Pointing a Router's default channel back to ingress:** unmatched messages loop back to the Router forever.
4. **Using a Bridge for retries:** immediately resending raw messages with no attempt limit or error classification.
5. **Error handler sending failed messages back to input:** creates an error loop, potentially spawning new errors while writing to DLQ.
6. **Ignoring paths across adapters and brokers:** each service looks acyclic in isolation, yet the combined system cycles.
7. **Failing to distinguish a new event from a redelivered event:** causes duplicate business effects under distinct message IDs.
8. **Ignoring fan-out:** a loop through Splitter/PublishSubscribe multiplies message counts.
9. **Testing only `send() == true`:** misses verifying completion, endpoint visit counts, or loop prevention.
10. **Missing stopping conditions and monitoring:** even an intentional retry loop can become a retry storm when a dependency goes down.

## 17. Practice Checklist

- [ ] Flow diagram accurately shows all input/output channels, Bridges, and Router branches.
- [ ] No path returns forwarded messages to a source channel unless intentional and bounded.
- [ ] Every intentional cycle has `maxAttempts` or a quantitative stopping rule, backoff, DLQ/quarantine, and documentation.
- [ ] Reviewed error, retry, reply, dead-letter paths, and cross-service broker loops.
- [ ] `DirectChannel` cannot recurse infinitely; `ExecutorChannel` and queues have resource bounds.
- [ ] Stable business `eventId`, correlation, deduplication, and idempotent consumers are in place.
- [ ] Static graph check/diagram, bounded tests, timeouts, and endpoint visit-count assertions exist.
- [ ] Metrics exist for per-event repeats, queue depth, consumer lag, retry count, hop count, and completions.
- [ ] Where durable messages/transactions/ACKs are used, recovery is tested independently rather than conflated with loop checks.
- [ ] Terminal outputs and error terminals are clearly defined with operational owners.

## 18. Conclusion

A Bridge connects two channels in Spring Integration without needing payload changes. When Bridges or other endpoints form a **forwarding cycle**, messages can return to where they started. With synchronous channels, cycles quickly trigger deep recursion; with queues, executors, or brokers, they become prolonged redelivery loops, resource exhaustion, or message amplification.

The durable fix is designing **one-way paths to terminal endpoints**, inspecting the system-wide graph across Routers, Gateways, adapters, retries, and error flows, and testing messages at final destinations. Intentional business loops must enforce stopping conditions, resource bounds, idempotency, and observability. Hop limits soften the blast radius when bugs happen, but never replace removing invalid routing edges.
