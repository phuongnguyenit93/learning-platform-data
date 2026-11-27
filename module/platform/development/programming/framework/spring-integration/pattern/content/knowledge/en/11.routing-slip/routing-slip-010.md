# Comparing routing slip with static flows

## 1. The problem: not every message needs the same itinerary

In Spring Integration, a **static integration flow** declares connected endpoints and message channels upfront. For example, every order request passes through normalization, validation, order persistence, and receipt emission. This structure is transparent, easy to read, and fits when processing steps are relatively stable.

However, not every order needs the exact same task list. Domestic orders may only need normalization and persistence; international orders need an added compliance check; high-value orders also need an approval step. When **the sequence of steps must be chosen individually per message**, the **Routing Slip** pattern becomes a worthwhile option.

~~~mermaid
flowchart LR
    subgraph STATIC["Static flow"]
      S[Input] --> V[Validate]
      V --> N[Normalize]
      N --> P[Persist]
      P --> O[Output]
    end
    subgraph SLIP["Per-message Routing Slip"]
      I[Input] --> PLAN[Route planner]
      PLAN --> PATH{Itinerary}
      PATH -->|Domestic| D["validate → persist"]
      PATH -->|International| X["validate → compliance → persist"]
      PATH -->|High value| R["validate → review → persist"]
    end
~~~

**Routing Slip** is an Enterprise Integration Pattern describing **a message's intended itinerary** as a list of steps/destinations along with current step progress. The message traverses the entries in the list in order until completion or failure. Spring Integration provides support for the Routing Slip pattern; details such as internal headers, route strategy declarations, and automatic forwarding to the next hop depend on framework APIs and versions, so **you cannot just attach an arbitrary header named `routePlan` and treat it as the framework's Routing Slip**.

This lesson belongs to the **Routing slip** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module's goal is implementing Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, testing, and per-branch observability. Comparing Routing Slip with static flows helps choose the right balance of flexibility, clarity, and operational control.

### Learning objectives

After this lesson, you will be able to:

1. Explain **static flow**, **Routing Slip**, **hop**, **route plan**, and **current step cursor**.
2. Point out similarities and differences among Routing Slip, Content-Based Router, Hierarchical Router, Recipient List, and Scatter–Gather.
3. Design endpoint sequences per message type while preserving an **allowlist of permitted endpoints**.
4. Recognize risks involving mid-hop failures, retries, duplicate side effects, lost headers, route loops, and messages without replies.
5. Read a Java DSL example for a static flow and a Java example illustrating itinerary planning.
6. Build tests for itineraries, step order, missing endpoints, business outcomes, tracing, and recovery.

## 2. Static flow: a pre-configured path

### 2.1. Nature of a static flow

In Spring Integration, you can define a path using Java DSL:

~~~text
orders.input
    -> validate
    -> normalize
    -> persist
    -> receipt
~~~

Endpoint connections already exist in the application context configuration. At runtime, messages follow that wiring unless a Router, Filter, error, or other logic alters the outcome.

**A static flow does not mean every message must yield the same outcome.** Handlers can transform data based on payload, Filters can drop messages, and Routers can branch. "Static" in this lesson only emphasizes that **the topology and baseline step sequence are declared upfront in configuration**, not that runtime conditions are forbidden.

### 2.2. Advantages of a static path

- **Easy to read and review:** looking at Java DSL or a diagram immediately shows which endpoints come before/after.
- **Easy to test:** each step and finite branch can be tested directly against configuration.
- **Clear contracts:** input/output types, error channels, transaction boundaries, and reply channels are easy to determine.
- **Predictable operations:** adding a new step normally requires a configuration change or controlled deployment.
- **Optimized observability:** dashboards, metrics, and alerts can rely on a stable set of endpoints.

### 2.3. Limitations of a static flow

If a product has many widely varying processes and tries to cram them all into a single chain, the flow can accumulate Routers and Filters checking conditions everywhere:

~~~text
Validate
  -> Router needs compliance?
      -> Compliance or skip
  -> Router needs review?
      -> Review or skip
  -> Router needs enrichment?
      -> Enrich or skip
  -> Persist
~~~

With a couple of branches, this still works well. As the number of itineraries grows and **different sequences must be chosen per request**, the diagram becomes a hard-to-follow graph. Routing Slip decouples **the message's itinerary plan** from fixed wiring chains.

## 3. Routing Slip: the itinerary as data accompanying the message

### 3.1. Defining the components

| Concept | Example | Role |
|---|---|---|
| **Route plan / itinerary** | `validate → review → persist` | List of steps the message must traverse. |
| **Hop** | `review` | A processing step/destination along the itinerary. |
| **Cursor / current index** | `2` | Index of the current or next step. |
| **Route strategy** | Data-driven destination rule | Computes or resolves a step if the model allows. |
| **Terminal destination** | `orders.completed` / reply | Where execution goes once slip steps finish per contract. |
| **Correlation/business context** | `orderId`, `traceId` | Links steps and tracks outcomes. |

Conceptually, an itinerary can be represented as:

~~~text
RoutePlan {
  version: "v1",
  hops: ["orders.validate", "orders.compliance", "orders.persist"],
  nextIndex: 0
}

After validate:   nextIndex=1
After compliance: nextIndex=2
After persist:    itinerary complete
~~~

**This is an illustrative model**, not an official Spring Integration JSON schema or header name. The framework's Routing Slip support manages itineraries/hops through its own mechanism. In the code examples later, we use a `RoutePlan` DTO to explain planning and testing; it does not replace actual Routing Slip configuration.

### 3.2. Selecting an itinerary per message

Suppose an order has three conditions:

- Market `VN` or `INTL`.
- Whether manual review is required.
- Whether customer enrichment is required.

Message A might carry itinerary:

~~~text
validate -> enrich -> persist
~~~

Message B might carry itinerary:

~~~text
validate -> compliance -> review -> persist
~~~

Message C might carry itinerary:

~~~text
validate -> persist
~~~

**Key point:** endpoints `validate`, `enrich`, `compliance`, `review`, and `persist` must still be **validly defined and registered** in the system. Routing Slip does not turn an arbitrary stage string into runnable code or beans. It only determines **the path across existing, permitted components**.

### 3.3. Itineraries must not be arbitrarily modifiable

Carrying the route plan with the message adds flexibility, yet if an external client can supply:

~~~text
["orders.validate", "orders.skipFraud", "orders.persist"]
~~~

that becomes a way to bypass business controls. Therefore, at the **trust boundary**:

1. Compute the route plan from **authenticated data** and application policies.
2. Never accept arbitrary bean/channel name lists requested by clients.
3. Enforce a **stage allowlist**, length limits, ordering, and preconditions.
4. Attach `policyVersion` or an itinerary ID when audit/replay is needed.
5. If a route plan crosses a broker, define how to protect and restore metadata without shipping non-serializable JVM objects.

## 4. Overall comparison table

| Criterion | Static flow | Routing Slip |
|---|---|---|
| **Path** | Fixed by configuration and declared branches. | An itinerary determined per message. |
| **When sequence is chosen** | Primarily at design/wiring time, with local runtime conditions. | Can be planned at runtime per message. |
| **Adding a new itinerary variant** | Usually edits flow, Router, or policy. | Can compose a valid sequence from existing endpoints; new stages still require deployment/config. |
| **Topology readability** | Clear from Java DSL. | Must inspect both endpoint config **and** actual itineraries. |
| **Operational complexity** | Usually lower when branch count is small. | Higher due to cursors, route metadata, and itinerary variants. |
| **Mid-flow errors** | Locate via static steps, call stack/traces. | Also needs current hop, executed plan, and remaining steps. |
| **Retry/recovery** | Per endpoint/transaction/error flow. | Same, plus ensuring no skipped or wrongly repeated hops. |
| **Observability** | Metrics per endpoint, channel, branch. | Adds `routePlanId`, version, current hop, and itinerary status. |
| **Security** | Topology is hard for external input to alter if configured well. | Must guard against route injection/step skipping when untrusted inputs arrive. |
| **Performance** | Fewer coordination components in simple cases. | Has planning/hop-resolution overhead; not inherently faster. |
| **Persistence** | Not automatically durable just by being static. | Not automatically durable just because a slip is in a header. |
| **When to choose** | Relatively stable processes with few, easily declared paths. | Many valid itineraries where step sequence varies per message in a controlled way. |

**There is no rule saying "static flow = rigid, Routing Slip = always better".** A static flow with hierarchical Routers can be flexible enough and easier to maintain than Routing Slip for domains with only a few variants.

## 5. Static flow example with Spring Integration Java DSL

### 5.1. Illustrative problem

The application receives `OrderCommand`, validates the amount, creates `NormalizedOrder`, and returns `Receipt`. Every request passes through the same three steps with topology:

~~~text
Gateway -> orders.input
          -> Filter
          -> Transformer
          -> Service Activator
          -> Gateway reply
~~~

The example targets **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** with the `spring-boot-starter-integration` dependency. Top-level types share a package; in real projects, split `public` types into separate Java files.

### 5.2. Java DSL code

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record OrderCommand(String orderId, BigDecimal amountVnd) {}
record NormalizedOrder(String orderId, BigDecimal amountVnd) {}
record Receipt(String orderId, String status) {}

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orders.input")
    Receipt submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StaticOrderFlowConfiguration {

    @Bean
    IntegrationFlow processOrder() {
        return IntegrationFlow.from("orders.input")
                // Step 1: validation.
                .filter(OrderCommand.class,
                        order -> order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amountVnd() != null
                                && order.amountVnd().signum() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                // Step 2: normalization.
                .transform(OrderCommand.class, order ->
                        new NormalizedOrder(
                                order.orderId().trim(),
                                order.amountVnd()))
                // Step 3: reply-producing handler.
                .handle(NormalizedOrder.class, (order, headers) ->
                        new Receipt(order.orderId(), "ACCEPTED"))
                .get();
    }
}
~~~

**How to read the code:**

- `@MessagingGateway` creates a request–reply entry point for Java callers.
- `Filter` rejects invalid amounts via exception rather than leaving the Gateway waiting for a reply that never arrives.
- `Transformer` builds a new DTO; it does not decide channels or persist results.
- `Service Activator` simulates the processing step and returns `Receipt`. Real systems need persistence, transactions, and appropriate retry/error handling.
- No Routing Slip: endpoint order is declared directly in the DSL.

When invoked:

~~~java
Receipt receipt = orderGateway.submit(
        new OrderCommand("ORD-101", new BigDecimal("1500000")));
// receipt.status() == "ACCEPTED"
~~~

This illustrates a synchronous request–reply path. It does **not** guarantee a DB write because the example has no database yet. With an async outbound adapter or a one-way terminal handler, the Gateway contract must change.

### 5.3. What to do when adding another branch?

Suppose orders of 10 million or more require review. In a static flow, you can place a Content-Based Router after the Filter and split into two handler flows:

~~~text
Filter -> Router(amount >= threshold)
             | normal -> normalize -> persist
             | review -> manualReview -> persist
~~~

This is still a **pre-declared topology**. It does not become a Routing Slip merely because a Router is used. With only two itineraries, an explicit Router and per-branch tests can be simpler than generating per-message itinerary metadata.

## 6. Dynamic itinerary planning example: choosing steps per order

### 6.1. Problem statement

We want to choose one of the following itineraries:

| Order characteristics | Itinerary | Meaning |
|---|---|---|
| Domestic, low value | `VALIDATE → PERSIST` | No extra special steps required. |
| Domestic, high value | `VALIDATE → REVIEW → PERSIST` | Review before persisting in confirmed state. |
| International, low value | `VALIDATE → COMPLIANCE → PERSIST` | Compliance check required. |
| International, high value | `VALIDATE → COMPLIANCE → REVIEW → PERSIST` | Both compliance check and high-value review required. |

The difference from a static flow diagram is that **a planner builds the list of hops for each request**, instead of forcing messages through every branch with "skip if unneeded" Filters.

### 6.2. Pure Java describing a route planner

The snippet below is an **application data model and itinerary policy**. It works for standalone testing, but is **not a complete configuration to activate Spring Integration's built-in Routing Slip**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;

enum Stage {
    VALIDATE, COMPLIANCE, REVIEW, PERSIST
}

record WorkflowOrder(
        String orderId,
        String market,
        BigDecimal amountVnd) {}

record RoutePlan(
        String policyVersion,
        List<Stage> hops) {

    RoutePlan {
        Objects.requireNonNull(policyVersion, "policyVersion");
        Objects.requireNonNull(hops, "hops");
        hops = List.copyOf(hops); // Capture immutable list.
        if (hops.isEmpty()) {
            throw new IllegalArgumentException("Empty route");
        }
    }
}

final class OrderRoutePlanner {
    private static final BigDecimal REVIEW_THRESHOLD =
            new BigDecimal("10000000");
    private static final Set<String> MARKETS = Set.of("VN", "INTL");

    RoutePlan plan(WorkflowOrder order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()
                || order.market() == null
                || !MARKETS.contains(order.market())
                || order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException("Invalid workflow order");
        }

        List<Stage> steps = new ArrayList<>();
        steps.add(Stage.VALIDATE);

        if ("INTL".equals(order.market())) {
            steps.add(Stage.COMPLIANCE);
        }
        if (order.amountVnd().compareTo(REVIEW_THRESHOLD) >= 0) {
            steps.add(Stage.REVIEW);
        }

        steps.add(Stage.PERSIST);
        return new RoutePlan("order-routing-v1", steps);
    }
}
~~~

**Explanation:**

- The planner accepts only two **allowed** markets: `VN` and `INTL`.
- Amounts are assumed **already normalized to VND** before comparison; production code must never compare raw unconverted USD/EUR payloads against a VND threshold.
- `VALIDATE` and `PERSIST` are mandatory steps; `COMPLIANCE` and `REVIEW` are conditional.
- `List.copyOf` prevents callers from mutating the itinerary after planning.
- `policyVersion` helps audit why older requests followed a different itinerary than newer ones.
- `Stage` is a bounded enum, never raw channel strings from unvalidated HTTP headers.

Example planner calls:

~~~java
OrderRoutePlanner planner = new OrderRoutePlanner();

RoutePlan vn = planner.plan(new WorkflowOrder(
        "ORD-1", "VN", new BigDecimal("2000000")));
// [VALIDATE, PERSIST]

RoutePlan intlHigh = planner.plan(new WorkflowOrder(
        "ORD-2", "INTL", new BigDecimal("12500000")));
// [VALIDATE, COMPLIANCE, REVIEW, PERSIST]
~~~

### 6.3. Cursor and the rule to advance only after the current step finishes

In a Routing Slip, **advancing to the next hop is not just incrementing an index arbitrarily**. You must know whether the current step finished according to contract. The standalone Java snippet below illustrates an algorithmically safe cursor:

~~~java
record RouteProgress(RoutePlan plan, int nextIndex) {
    RouteProgress {
        if (plan == null || nextIndex < 0
                || nextIndex > plan.hops().size()) {
            throw new IllegalArgumentException("Invalid cursor");
        }
    }

    boolean done() {
        return nextIndex == plan.hops().size();
    }

    Stage current() {
        if (done()) {
            throw new IllegalStateException("Route already complete");
        }
        return plan.hops().get(nextIndex);
    }

    RouteProgress complete(Stage finishedStage) {
        if (done() || current() != finishedStage) {
            throw new IllegalStateException(
                    "Cannot skip or repeat route step");
        }
        return new RouteProgress(plan, nextIndex + 1);
    }
}
~~~

Simulation:

~~~java
RouteProgress progress = new RouteProgress(intlHigh, 0);
// current() == VALIDATE

progress = progress.complete(Stage.VALIDATE);
// current() == COMPLIANCE

progress = progress.complete(Stage.COMPLIANCE);
// current() == REVIEW

progress = progress.complete(Stage.REVIEW);
progress = progress.complete(Stage.PERSIST);
// progress.done() == true
~~~

**Important warning:** `RouteProgress` is only an academic cursor example. Do not use it to replace Spring Integration's header structure and coordination algorithm. The framework's real Routing Slip mechanism has its own APIs, hop-resolution rules, and forwarding semantics; configure it for your running version. Building a custom dispatcher on top of `RouteProgress` without persistence, concurrency control, timeouts, transactions, and recovery amounts to reinventing a naive workflow engine missing critical guarantees.

### 6.4. Mapping Stages to permitted endpoints

The planner should return **step identifiers from an allowlist**. The integration layer is responsible for mapping them to Spring Integration channels or endpoints:

| Validated Stage | Intended channel/endpoint | Role |
|---|---|---|
| `VALIDATE` | `orders.validate` | Validates data contract. |
| `COMPLIANCE` | `orders.compliance` | Verifies compliance from trusted sources. |
| `REVIEW` | `orders.review` | Executes approval step. |
| `PERSIST` | `orders.persist` | Persists and produces final result. |

The component resolving the hop list must enforce an **allowlist**, verify channel existence, and validate ordering. A stage name's mapping can change without altering business policy only if contracts, versions, and recovery remain compatible.

The approval and check steps in this table are **illustrative**. Never let a client set `COMPLIANCE=PASS` or alter `nextIndex` to jump straight to `PERSIST`.

## 7. Using Routing Slip with Spring Integration: what to understand

### 7.1. Do not equate a custom header with standard Routing Slip

Spring Integration supports Routing Slip as part of its message-coordination capabilities. When configured via the proper framework API, routing-slip metadata describes the destinations/steps to traverse and progress state; infrastructure uses that metadata when determining forwarding targets.

**Two different snippets:**

~~~java
// Custom application header: holds data only.
MessageBuilder.withPayload(order)
        .setHeader("routePlan", List.of(
                "orders.validate", "orders.persist"))
        .build();
~~~

~~~text
Spring Integration's Routing Slip:
  - Must be declared using the header/processor mechanism supporting
    Routing Slip for your exact framework version.
  - Requires permitted, resolvable endpoints/channels.
  - Each hop must forward messages according to the appropriate contract.
  - Infrastructure manages slip routing state,
    rather than reading an arbitrary header named "routePlan".
~~~

`setHeader("routePlan", ...)` **does not automatically make Spring Integration route messages**. It only creates application-defined metadata. Avoid setting a header and claiming the framework executes that list automatically.

When implementing real Routing Slip flows, consult the API documentation for your exact `spring-integration-core` version, especially concepts around **Routing Slip header value processors, route strategies, output channels, and reply-producing endpoints**. Never copy DSL syntax from another version without verifying.

### 7.2. Why are reply-producing endpoints important?

In typical Routing Slip configurations, a message can only reach the next step when the current endpoint **emits an output message to proceed**. If you use a one-way handler that merely performs a side effect and stops, the itinerary has no message left to forward to the next hop.

~~~text
Slip: [validate, enrich, persist]

validate receives Message<Order>
   -> returns Message<Order> or valid payload
   -> slip proceeds to enrich

enrich receives Order
   -> returns EnrichedOrder
   -> slip proceeds to persist

persist receives EnrichedOrder
   -> writes DB and returns Receipt / final result per contract
~~~

Conversely:

~~~java
// Illustration of a one-way terminal handler:
.handle(message -> {
    saveToDatabase(message.getPayload());
    // Emits no reply to continue.
})
~~~

If hops remain after this handler, never assume the Routing Slip still continues. When designing an itinerary, **specify each step's input/output schema and message-emission responsibility explicitly**, especially with one-way outbound adapters.

### 7.3. Explicit output channels can affect routing

In static flows, an endpoint normally has a specific `outputChannel` declared in configuration. Routing Slip, by contrast, wants to steer based on the itinerary. If an endpoint has both a **fixed output channel** and routing-slip metadata, destination resolution precedence must be understood for that endpoint type and framework configuration.

Never assume "attaching a Routing Slip automatically overrides every static `outputChannel`". If the static output channel wins, the message may bypass the slip's intent; if the endpoint produces no reply, the slip has nothing to advance either. Testing **a real message traversing all hops** on your chosen Spring Integration version is the best confirmation.

### 7.4. Thread and transport boundaries

When an itinerary runs over `DirectChannel`s on one thread, observing step order is straightforward. With `ExecutorChannel`, `QueueChannel`, or a message broker, consider:

- Are processing order and current step preserved reliably?
- Does the Routing Slip header survive adapters/converters or get stripped?
- Is the reply channel or transport return-address valid?
- If a handler times out mid-flight, what happens to the cursor and business state?
- Can broker retries cause a hop to execute again?

**Routing Slip is not a persistence mechanism by itself.** If a process dies while a message sits in an in-memory queue or between publish and ack, the itinerary may not resume properly without a persistent store/broker and idempotency.

## 8. Errors specific to Routing Slip

### 8.1. Failing to resolve a hop

An itinerary may contain:

~~~text
["orders.validate", "orders.compliance", "orders.persist"]
~~~

yet `orders.compliance` lacks a bean/channel in the application context, was renamed, or its subscribing endpoint has not started. Distinguish these errors:

| Error type | Example | Required response |
|---|---|---|
| **Hop not in allowlist** | Caller sends `orders.skipCompliance`. | Reject immediately when building/receiving itinerary; audit log. |
| **Destination missing** | Bean `orders.compliance` is not registered. | Report config error; never silently skip an important hop. |
| **Channel exists with no subscriber** | `DirectChannel` exists, handler stopped. | Dispatch failure/timeout per contract; never mark hop complete. |
| **Queue full** | Next hop uses bounded `QueueChannel`. | Bounded wait, backpressure, retry, or controlled recovery. |
| **Handler emits no reply** | One-way outbound adapter used as middle hop. | Fix forwarding contract; never mark everything done. |
| **Itinerary header lost** | Crosses HTTP/Kafka/JMS adapter without mapping. | Stop/fail closed or reconstruct from trusted source; never guess. |

Routing Slip enables **varied itineraries**, while increasing the surface of edge cases to guard. Static flows can also suffer channel or handler errors, yet fixed wiring catches many config mistakes earlier.

### 8.2. Failure at an intermediate hop: continue, retry, or abort itinerary?

Suppose a slip has four hops:

~~~text
VALIDATE -> COMPLIANCE -> REVIEW -> PERSIST
~~~

and `COMPLIANCE` times out. Three actions might be proposed, but they are not equivalent:

1. **Retry COMPLIANCE:** if transient and the step has proper idempotency/backoff.
2. **Route to recovery:** e.g., `WAITING_FOR_VERIFICATION` or quarantine with persisted state and deadline.
3. **Fail the whole request:** return an error or unprocessable status; never jump straight to `REVIEW` and `PERSIST`.

**Never advance the cursor past a mandatory step just because it failed.** Skipping compliance checks and persisting the order as compliant is a business bug, even if the technology allows forwarding to the next channel.

### 8.3. Retrying the whole itinerary can duplicate side effects

~~~text
VALIDATE   -> success
COMPLIANCE -> success
REVIEW     -> success
PERSIST    -> timeout after DB may have already committed
~~~

Restarting the itinerary from `VALIDATE` without state and idempotency can repeat steps with external effects. Specifically, a `PERSIST` timeout does not prove the DB write failed. Therefore:

- Attach a stable **business operation ID**, such as `orderId` + `operationType` or `workflowAttemptId` per contract.
- Give each side-effecting hop its own **idempotency key**; never rely solely on `MessageHeaders.ID`, since new messages may carry new UUIDs.
- Persist proof of completed hops durably if crash recovery is required.
- When outcomes are uncertain, **reconcile** target system state before re-executing.
- Distinguish **retrying the current hop** from **replanning the itinerary** when policy changes.

Routing Slip does not automatically provide exactly-once execution across multiple databases, brokers, and HTTP services. Transactions, outboxes, consumer deduplication, and compensation must be designed explicitly.

### 8.4. When Gateway times out before the slip finishes

If a `@MessagingGateway` waits for the result of a multi-step itinerary:

~~~text
HTTP client
  -> Gateway reply timeout: 5 s
        -> compliance HTTP timeout: 4 s
        -> review processing: 3 s
        -> persist: 1 s
~~~

the Gateway deadline can expire before the message reaches the final hop. The caller receiving a timeout **does not mean** every hop was cancelled. An asynchronous message may keep processing, producing a late reply and side effects.

Design must specify:

1. **Overall deadline** and per-downstream deadlines.
2. Status returned when completion is not yet known, such as `PENDING` or a queryable error.
3. **Late reply** handling and cleanup.
4. Client retry rules to avoid spawning two workflows for one order.
5. Where state lives if work outlasts an HTTP request.

For approval steps spanning hours or days, a bare Routing Slip is generally **insufficient** as a workflow orchestrator; you need durable state persistence, timeouts, resume, compensation, and operator controls.

## 9. Avoiding loops and overly long itineraries

### 9.1. Risky sequences

An itinerary from a buggy policy or spoofed input may contain the same hop multiple times:

~~~text
VALIDATE -> REVIEW -> VALIDATE -> REVIEW -> ...
~~~

Or a mid-hop route strategy might return the channel that just ran, creating a cycle even when the initial list looked acyclic. With `DirectChannel`, this can cause recursive dispatch; with executors/queues, it can drive load until exhaustion.

### 9.2. Safety invariants

**A valid route plan** for the order example should satisfy:

- `VALIDATE` is first, `PERSIST` is last.
- `COMPLIANCE` is allowed only for market `INTL`.
- `REVIEW` is allowed only when trusted policy requires approval.
- No stage repeats unless the workflow explicitly designs a valid loop.
- Enforce **`maxHops`**, e.g., 8 per application policy.
- Every stage belongs to a known allowlist, and every output channel has a valid consumer/contract.
- Cursor advances only after completing the step at the expected position.
- Every attempt has a deadline and error state to prevent infinite loops.

Pure Java illustration of a route plan validator:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class RoutePlanValidator {
    private static final int MAX_HOPS = 8;

    void validate(RoutePlan plan) {
        List<Stage> hops = plan.hops();

        if (hops.size() > MAX_HOPS
                || hops.get(0) != Stage.VALIDATE
                || hops.get(hops.size() - 1) != Stage.PERSIST) {
            throw new IllegalArgumentException(
                    "Invalid itinerary boundaries");
        }

        Set<Stage> unique = new HashSet<>(hops);
        if (unique.size() != hops.size()) {
            throw new IllegalArgumentException("Duplicate hop");
        }
    }
}
~~~

This checks only a few **structural invariants**; it does not yet check whether the order is international or whether review is mandatory. For strict policies, the validator should also accept validated business data or planner inputs to verify **mandatory steps are never omitted**. Also, never treat `MAX_HOPS=8` as a Spring Integration built-in default; it is an illustrative application-chosen cap.

### 9.3. Beware route plan changes while messages are in flight

Suppose:

~~~text
T1: policy-v1 -> validate, compliance, persist
T2: validate completed
T3: system deploys policy-v2 -> validate, fraud, compliance, persist
T4: message continues running
~~~

Should the itinerary automatically mutate mid-flight to apply `policy-v2`? Not by default. Changing mid-flight can skip or repeat steps, breaking replay and audit. Define clearly:

- **Plan snapshot:** freeze itinerary and version at intake.
- **Replanning checkpoint:** change policy only at permitted points with migration and audit.
- **Compatibility:** older stages must remain supported while in-flight messages exist.
- **Recovery:** messages waiting in brokers/stores must still parse old-version plan metadata.

Static flows also need deployment compatibility strategies, yet Routing Slip makes **per-message itinerary versioning** much more prominent.

## 10. Routing Slip, Hierarchical Router, Recipient List, and Scatter–Gather

### 10.1. All say "route", yet answer different questions

~~~mermaid
flowchart TB
    Q{Need}
    Q -->|Pick one branch right now| R[Content-Based Router]
    Q -->|Multi-level tree decisions| H[Hierarchical Router]
    Q -->|Follow a varying sequence of steps| S[Routing Slip]
    Q -->|Broadcast to multiple recipients| L[Recipient List / Publish–Subscribe]
    Q -->|Send multiple requests and await results| G[Scatter–Gather / Aggregator]
~~~

| Design question | Suitable pattern | What to add |
|---|---|---|
| "Domestic goes to branch A, international to branch B?" | Content-Based Router. | Channel mapping, default/error route. |
| "Inside international, split further by risk tier?" | Hierarchical Router. | Per-tier observability, handling branches with no consumer. |
| "Each message has its own step itinerary?" | Routing Slip. | Plan/cursor, allowlisting, reply-producing steps, retry/recovery. |
| "Send one event simultaneously to audit, email, analytics?" | Recipient List or Publish–Subscribe. | Per-branch delivery/retry/error handling. |
| "Need both fraud and inventory results before confirming?" | Scatter–Gather/Aggregator. | Correlation, expected recipients, release strategy, timeouts. |

A real flow can **combine** patterns. For instance, Routing Slip carries a message to the `validate` hop, where a Router selects detailed validation branches. Still, the more routing mechanisms you combine, the more critical it becomes to verify ordering, skip conditions, and retry behavior.

### 10.2. Routing Slip is sequential traversal, not automatic fan-out

If an itinerary is:

~~~text
validate -> fraud -> persist
~~~

that means **traversing steps sequentially** by design—it does not spawn three concurrent messages. If Fraud and Inventory should run in parallel, add fan-out at an appropriate step with aggregation rules when combined results are needed. Never write a sequential stage list expecting the framework to parallelize and gather automatically.

### 10.3. Routing Slip does not replace a state machine for multi-day processes

Credit approval taking several days involves states like `WAITING_FOR_APPROVAL`, `APPROVED`, `REJECTED`, `EXPIRED`, plus compensation or operator overrides. That is a **durable stateful workflow** problem. Routing Slip can assist by pointing to endpoints during technical phases, but does not provide persistence, timers, signal handling, authorization, and full long-running recovery on its own.

## 11. Observing Routing Slip vs. static flows

### 11.1. Static flow: topology known from configuration

With a static flow:

~~~text
orders.input -> filter -> transform -> handler
~~~

During investigations, you can rely on configuration diagrams, channels, and per-endpoint metrics to know where a message is **expected** to go. Without dynamic branching, the set of paths is small.

### 11.2. Routing Slip: need both topology and actual itinerary

With Routing Slip, the overall diagram shows only **which stages can run**; explaining a single request requires knowing **the selected route plan** and **executed hops**.

~~~text
event=ROUTE_PLANNED orderId=ORD-2002 traceId=T-2002
  planVersion=order-routing-v1
  hops=[VALIDATE,COMPLIANCE,REVIEW,PERSIST]

event=HOP_STARTED orderId=ORD-2002 traceId=T-2002
  planVersion=order-routing-v1 hopIndex=1 hop=COMPLIANCE

event=HOP_FAILED orderId=ORD-2002 traceId=T-2002
  hopIndex=1 hop=COMPLIANCE reason=HTTP_TIMEOUT retryable=true

event=HOP_RETRIED orderId=ORD-2002 traceId=T-2002
  hopIndex=1 hop=COMPLIANCE attempt=2
~~~

This is a **suggested application log schema**, not Spring Integration's default output. Key fields:

| Field | Explanation |
|---|---|
| `orderId` / business ID | Traces business entity across rebuilt messages. |
| `traceId` | Correlates logs/spans across endpoints and services. |
| `planVersion` | Identifies which rules built the itinerary. |
| `planId` / workflow attempt ID | Distinguishes multiple executions of the same order. |
| `hopIndex` and `hop` | Pinpoints failure location and waiting step. |
| `attempt` | Distinguishes a hop retry from a brand-new step. |
| `outcome` / `failureReason` | Shows completed, permitted skip, failed, or waiting. |

Never log full payloads containing sensitive data or use `orderId`/`traceId` as high-cardinality metric labels.

### 11.3. Message History differs from itinerary

**Message History** can record which Spring Integration components a message visited when enabled. However:

- **Itinerary** expresses **intended** steps.
- **Message History** expresses components **tracked by the framework**.
- **Business outcome log** expresses whether a step actually processed, recorded, or committed successfully.
- **Distributed trace** links spans across threads/processes when propagation is configured.

Never use Message History as a substitute for a **durable audit trail** for approvals or compliance verification. A hop can appear in history even if a downstream side effect later fails.

### 11.4. Recommended metrics

| Metric | Static flow | Routing Slip |
|---|---|---|
| Input/processed rate per endpoint | Yes | Yes |
| Error/retry/timeout rate per endpoint | Yes | Yes |
| Queue depth, executor saturation | Yes if async | Yes if async |
| Messages by itinerary version | Optional | Recommended |
| Average/max hop count | Less needed if topology is simple | Useful to detect plan bloat |
| Route-plan validation failures | Less relevant | Recommended |
| Stuck routes / oldest unfinished itinerary | Per workflow if any | Critical if resumption is needed |
| Hop transition failures | Per dispatch/handler | Critical because many next targets exist |

Metrics keyed by `hop` and `planVersion` should use bounded value sets. Keep business/trace IDs in retention-controlled logs/traces rather than labels.

## 12. Testing both approaches

### 12.1. Unit testing the route planner

With `OrderRoutePlanner` and `RoutePlan` from section 6, use JUnit 5 to verify exact itineraries per order type:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderRoutePlannerTest {
    private final OrderRoutePlanner planner =
            new OrderRoutePlanner();

    @Test
    void domesticLowValueHasTwoSteps() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-1", "VN",
                        new BigDecimal("9999999")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void domesticAtThresholdRequiresReview() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-2", "VN",
                        new BigDecimal("10000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.REVIEW, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void internationalLowValueRequiresCompliance() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-3", "INTL",
                        new BigDecimal("5000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.COMPLIANCE,
                        Stage.PERSIST),
                plan.hops());
    }

    @Test
    void internationalHighValueRequiresBothChecks() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-4", "INTL",
                        new BigDecimal("25000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.COMPLIANCE,
                        Stage.REVIEW, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void unknownMarketDoesNotProduceAnItinerary() {
        assertThrows(IllegalArgumentException.class, () ->
                planner.plan(new WorkflowOrder(
                        "O-5", "UNKNOWN",
                        new BigDecimal("3000000"))));
    }

    @Test
    void invalidAmountDoesNotProduceAnItinerary() {
        assertThrows(IllegalArgumentException.class, () ->
                planner.plan(new WorkflowOrder(
                        "O-6", "VN", BigDecimal.ZERO)));
    }
}
~~~

**Passing tests only verify itinerary selection policy**, not that Spring Integration actually dispatched messages along the itinerary. To test real Routing Slip mechanics, configure the framework's header processor/route strategy and test forwarding endpoints on your exact version.

### 12.2. Unit testing that the cursor cannot skip steps

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteProgressTest {

    @Test
    void completesAllHopsInDeclaredOrder() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.COMPLIANCE, Stage.PERSIST));
        RouteProgress progress = new RouteProgress(plan, 0);

        assertEquals(Stage.VALIDATE, progress.current());
        progress = progress.complete(Stage.VALIDATE);

        assertEquals(Stage.COMPLIANCE, progress.current());
        progress = progress.complete(Stage.COMPLIANCE);

        assertEquals(Stage.PERSIST, progress.current());
        progress = progress.complete(Stage.PERSIST);
        assertTrue(progress.done());
    }

    @Test
    void cannotSkipRequiredComplianceHop() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.COMPLIANCE, Stage.PERSIST));
        RouteProgress progress = new RouteProgress(plan, 1);

        assertThrows(IllegalStateException.class, () ->
                progress.complete(Stage.PERSIST));
        assertFalse(progress.done());
    }

    @Test
    void duplicateHopIsRejectedByExampleValidator() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.REVIEW,
                Stage.REVIEW, Stage.PERSIST));

        assertThrows(IllegalArgumentException.class, () ->
                new RoutePlanValidator().validate(plan));
    }
}
~~~

Again, this tests the **lesson-defined** cursor algorithm, not the framework's internal implementation details.

### 12.3. Integration test for the static flow

With `StaticOrderFlowConfiguration` from section 5, using Spring Test and JUnit 5:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(StaticOrderFlowConfiguration.class)
class StaticOrderFlowTest {

    @Autowired
    private OrderGateway gateway;

    @Test
    void validOrderPassesStaticPipeline() {
        Receipt receipt = gateway.submit(
                new OrderCommand(" ORD-7 ",
                        new BigDecimal("2000000")));

        assertEquals("ORD-7", receipt.orderId());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void invalidAmountIsRejectedByFilter() {
        assertThrows(MessagingException.class, () ->
                gateway.submit(new OrderCommand(
                        "ORD-8", BigDecimal.ZERO)));
    }
}
~~~

This test proves the **static flow**'s Filter/Transformer/handler work in the example configuration. There is no database, transaction, external gateway, or retry yet. The exact exception type in tests can depend on how the framework and gateway wrap errors; on a specific version, inspect the cause as needed.

### 12.4. Integration test matrix for a real Routing Slip

When adding real routing slip configuration with your Spring Integration version's API, also test:

| Case | What needs to be proven |
|---|---|
| Plan `VALIDATE → PERSIST` | Only those two hops receive messages; `COMPLIANCE` and `REVIEW` never run. |
| Plan `VALIDATE → COMPLIANCE → REVIEW → PERSIST` | Exact hop order; nothing skipped or added. |
| A hop does not exist | Explicit error reported; message does not jump to the next step. |
| Middle endpoint is a one-way handler | Per contract, detect itinerary stopped; never return "complete". |
| A hop throws an exception | Error/retry policy applies at the right hop; cursor never skips mandatory steps. |
| Reply-producing handler creates new message | Metadata needed to continue the itinerary is preserved or propagated properly. |
| Adapter loses routing-slip metadata | Explicit error/recovery; never blindly falls back to a default route. |
| Next hop is a `QueueChannel` | Poller/consumer, timeout/backpressure, and full-queue behavior tested. |
| A step is retried after timeout | No duplicate side effects if the first attempt may have committed. |
| Gateway times out mid-way | Late outcome handled; request is not marked completed prematurely. |
| Client plan contains unknown stage | Rejected by allowlist; never resolves arbitrary bean names. |
| Route has a cycle or too many hops | Hop-limit guard and loop policy actually take effect. |
| Deploy changes plan version while messages wait | Old itineraries are not altered unexpectedly. |

For asynchronous steps, use **latches/await with finite timeouts** rather than `Thread.sleep` to guess state. Never run a dangerous loop test without max-steps/deadlines and a circuit-breaker; a synchronous loop can overflow the stack very quickly.

## 13. Deciding between static flow and Routing Slip

### 13.1. A decision tree

~~~mermaid
flowchart TD
    Q{Do messages follow nearly the same sequence?}
    Q -->|Yes| STATIC[Static flow]
    Q -->|No| V{Only a few clear branching choices?}
    V -->|Yes| ROUTER[Static flow + Router/Filter]
    V -->|No| W{Many valid itineraries per message?}
    W -->|Yes| SLIP[Consider Routing Slip]
    W -->|No| STATIC
    SLIP --> LONG{Wait externally for hours/days?}
    LONG -->|Yes| ENGINE[Durable workflow/state machine]
    LONG -->|No| CHECK[Guard plan, hops, retries, security, metrics]
~~~

Do not pick Routing Slip for every flow with two or three conditions. The added complexity must pay off in sequence flexibility and decoupling between the planner and endpoints.

### 13.2. Evaluating by requirement

| Requirement | Recommendation | Why |
|---|---|---|
| Always validate → transform → persist | Static flow | Less indirection, easier to test and observe. |
| Two normal/review branches | Router or conditional static flow | Small branch count, easy to express directly. |
| Domestic and international with two decision trees | Hierarchical Router | Each branch has clear rules, wiring remains transparent. |
| Each request picks from dozens of valid policy itineraries | Routing Slip worth considering | Sequence is per-request data, decoupling planning from execution. |
| Event sent simultaneously to audit and analytics | Pub/Sub or Recipient List | Fan-out, not a sequential step chain. |
| Must wait for both fraud and inventory before confirming | Scatter–Gather/Aggregator | Must combine responses rather than merely routing along a list. |
| Manual approval spanning days | Durable workflow engine/state machine | Needs timers, persistence, signals, timeouts, compensation. |
| Need tracing, retries, and monitoring | Both need them | Routing Slip does not replace error flows or observability. |

### 13.3. Operational costs to factor into the decision

Routing Slip can reduce the number of statically declared branches, yet typically adds costs:

- Approval and versioning processes for the route planner.
- Security controls over itineraries and destinations.
- Logging/metrics by hop, route version, and route outcome.
- Testing validity across all itinerary combinations.
- Recovery when a message finished partially before an application crash.
- Compatibility between in-flight messages and new deployments.
- Handling paused hops, full queues, or late replies.

Without operational capacity for these concerns, a static flow with a few explicit Routers is usually safer and easier to manage.

## 14. Common mistakes

| Misconception | Consequence | Right practice |
|---|---|---|
| "Static flows cannot contain Routers." | Unnecessary Routing Slips created. | Static flows can use Routers/Filters and pre-declared branches. |
| "Routing Slip sends in parallel to multiple recipients." | Confuses sequential itineraries with fan-out. | Use Recipient List/Publish–Subscribe when multiple targets should receive together. |
| "Attaching `routePlan` header makes the framework route automatically." | Message never advances to the next hop. | Use Spring Integration's actual Routing Slip mechanism for your version. |
| "Routing Slip creates new stages from a string." | Invalid destination resolution or route-injection risk. | Stages must be pre-configured and inside an allowlist. |
| "Routing Slip is always faster than a static flow." | Adds planning/hop-resolution overhead. | Measure workloads; pick based on complexity and requirements. |
| "A one-way middle handler still forwards automatically." | Itinerary stops before reaching the final hop. | Define output/replies on every intermediate endpoint. |
| "With a static `outputChannel`, the slip still wins." | Message may take an unintended path. | Understand endpoint/framework output resolution precedence. |
| "Failed compliance steps can be skipped to finish." | Violates business rules. | Never advance the cursor when mandatory conditions fail. |
| "Retrying the whole itinerary is always safe." | Duplicates already committed side effects. | Use idempotency, checkpoints/recovery, and per-hop retries. |
| "Routing Slip in a header equals durability." | Plans vanish when messages/processes are lost. | Use stores/brokers, retention/acks, and persistence where needed. |
| "Message ID stays identical across all hops." | Broken traces after Transformers/adapters. | Use business IDs, trace IDs, and proper correlation. |
| "With a slip, no `errorChannel` is needed." | Errors go unhandled and unobserved. | Design retry/error/recovery per hop according to execution model. |
| "Deploying a new policy should auto-rewrite running slips." | Uncontrolled itinerary shifts mid-flight. | Use version/snapshots or audited checkpoint migrations. |
| "Unit testing the planner proves routing works." | Leaves dispatch, subscribers, replies, adapters untested. | Unit test planner plus integration test every hop. |
| "Routing Slip is a long-running workflow engine." | Lacks state/timers/compensation/durable resume. | Add orchestration/state machines when required. |

## 15. Practice exercises

1. **Static flow:** implement `Filter → Transformer → Service Activator` as in section 5. Write tests where invalid payloads are rejected and valid payloads return `Receipt`.
2. **Add a Router:** add a review branch for orders ≥ 10 million to the static flow. Draw the new topology and compare endpoint count against the routing slip approach.
3. **Route planner:** use `OrderRoutePlanner` to generate itineraries for all four order types. Write a truth table covering market, amount tier, and hops to execute.
4. **Cursor:** use `RouteProgress` to simulate traversing hop by hop, intentionally attempting to complete `PERSIST` before `COMPLIANCE` finishes to verify rejection.
5. **Allowlist:** inject an unknown stage into a client request. Design rejection before channel resolution and logging that leaks no sensitive data.
6. **Real Spring Routing Slip:** following your project's Spring Integration version API docs, configure the routing-slip header/processor and reply-producing endpoints. Test one message taking two hops and one taking four hops.
7. **One-way endpoint:** convert an intermediate hop into a reply-less outbound adapter. Explain why the itinerary may stall and fix the forwarding contract.
8. **Mid-route failure:** make `COMPLIANCE` time out; retry only that hop under a bounded policy without skipping to `PERSIST`.
9. **Duplicates:** simulate `PERSIST` committing while the reply is lost. Use operation IDs/idempotency keys to prevent creating two orders on client retry.
10. **Adapters:** pass a slip-carrying message over a broker; verify metadata maps and restores properly without serializing internal `replyChannel` objects.
11. **Versioning:** plan under `policy-v1`, then simulate deploying `policy-v2` before the message finishes. Define when a plan is permitted to change.
12. **Observability:** log `planVersion`, `hopIndex`, `HOP_STARTED`, `HOP_FAILED`, and `HOP_COMPLETED`; pinpoint the failing hop from a trace.
13. **Long-running coordination:** replace `REVIEW` with waiting three days for a human approver. Evaluate why durable state/timers are needed instead of relying solely on a routing-slip header.

### Self-check questions

**Question 1:** A static flow has a Content-Based Router splitting into three branches. Does it automatically become a Routing Slip? **No.** A Router chooses a destination at one decision point; Routing Slip describes a per-message step itinerary.

**Question 2:** If a message carries a custom header `routePlan=["A","B"]`, will Spring Integration automatically run A then B? **No.** You need the framework-supported Routing Slip mechanism, valid endpoints/channels, and proper forwarding rules.

**Question 3:** An intermediate hop finishes its side effect without emitting an output message. Can we conclude the slip continues to the next hop? **No.** Check reply-producing endpoint contracts and how the framework routes outputs.

**Question 4:** Does adding a Routing Slip make messages in an in-memory `QueueChannel` survive restarts automatically? **No.** Durability depends on persistent stores/brokers and explicit acknowledgement mechanisms.

**Question 5:** If `COMPLIANCE` times out, should we skip ahead to `PERSIST` when that hop is mandatory? **No.** Raise an error, perform bounded retries, or enter recovery—never increment the cursor automatically.

**Question 6:** Which itinerary does a high-value international order get in the example? **`VALIDATE → COMPLIANCE → REVIEW → PERSIST`**, provided the data has been validated.

**Question 7:** When both fraud and inventory branches must run in parallel and return results, is a sequential Routing Slip the best fit? **Not necessarily.** Consider Scatter–Gather/Aggregator with correlation, release strategies, and timeouts.

**Question 8:** Does a thoroughly unit-tested route planner prove the production flow hits the right channels? **Not yet.** You need integration tests covering the routing-slip processor, channels, endpoints, metadata, and failure modes.

## 16. Conclusion

**Static flows** fit when processing sequences are relatively stable and topology is cleanly expressed via Java DSL and finite Routers/Filters. **Routing Slip** fits when each message requires a distinct step itinerary and sequence planning should be decoupled from individual endpoint implementations.

Routing Slip brings flexibility, yet demands discipline: **allowlisting steps, pinning plan versions, managing hops/cursors, preserving metadata across adapters, understanding reply/output semantics, never skipping mandatory steps, designing retries/idempotency, and instrumenting every hop**. It does not automatically provide fan-out, aggregation, persistence, or long-running orchestration.

In `SPRING_INTEGRATION_PATTERN`, choose the simplest pattern that accurately expresses the business contract: static flow + Router when branches are few and clear; Routing Slip when per-message itineraries are genuinely needed; Recipient List/Publish–Subscribe for fan-out; Scatter–Gather/Aggregator when gathering multiple results. Combine error channels, correlation, distributed tracing, and end-to-end path testing so flows remain both loosely coupled and safe to operate and recover.
