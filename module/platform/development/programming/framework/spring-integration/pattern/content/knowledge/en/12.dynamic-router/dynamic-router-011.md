# Bounding the Complexity of Runtime Routes

## 1. Context and Problem Statement

In the **Dynamic router** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible, and observable message flows. Dynamic Router enables changing how paths are chosen **while the application is running**. This capability is valuable when shifting traffic to a standby system, opening a new processing path, or updating business policies without stopping the entire application.

However, this flexibility introduces another kind of risk: **route complexity is no longer fixed at deployment time**.

Imagine a logistics system receiving `DispatchRequested` events. Initially, each message goes to one of two branches:

- **standardChannel**: ordinary orders.
- **manualReviewChannel**: high-value or risky orders.

Later, operations keeps adding conditions: international orders, priority orders, special-tenant orders, promotional orders, plus audit, notification, regional fulfillment, and fallback branches. If every rule is allowed to add more recipients and those recipients route further, a single message can touch dozens of endpoints, loop infinitely, or overload queues.

~~~mermaid
flowchart LR
    P["DispatchRequested"] --> R["Dynamic Router"]
    R --> A["Standard"]
    R --> B["Review"]
    R --> C["Partner"]
    B --> R2["New router"]
    R2 --> D["Audit"]
    R2 --> E["Notification"]
    R2 --> R
~~~

The arrow from the new router back to Dynamic Router illustrates a **cycle**. Without bounds, the same message can keep circulating through the topology, causing stack overflows on synchronous branches or unbounded backlogs on asynchronous branches.

**Lesson Objectives**

1. Identify the dimensions along which runtime routing complexity grows: rule count, predicate cost, destination count, fan-out, hop count, cycles, configuration versions, and concurrency.
2. Distinguish **a router updating mappings at runtime** from **business rules changing at runtime** and **registering entire new IntegrationFlows at runtime**.
3. Establish verifiable bounds instead of relying solely on vague advice like "fewer rules are better."
4. Build immutable policy snapshots, atomic updates, channel allowlists, and safe fallbacks.
5. Understand Spring Integration APIs such as **setChannelMapping**, **setChannelMappings**, **replaceChannelMappings**, **RecipientListRouterManagement**, and **Control Bus**.
6. Test load, fan-out, route cycles, concurrent updates, rollbacks, and divergence across instances.

## 2. What Is a Dynamic Router in Spring Integration?

At its core, a Router usually performs three tasks:

1. **Compute the channel identifier** from payload, headers, or business logic.
2. **Map the identifier to a channel name**.
3. **Resolve the channel name to a MessageChannel** to send the message.

Spring Integration supports many router styles such as **HeaderValueRouter**, **PayloadTypeRouter**, and SpEL- or POJO-based routers. A router can produce different outcomes per message without truly having "dynamic configuration": the routing expression is fixed when the application initializes.

**Dynamic Router** in Enterprise Integration Patterns emphasizes that **routing rules or mapping tables can change while the system is operating**.

For example, initial mappings:

~~~text
STANDARD -> standardChannel
REVIEW   -> manualReviewChannel
~~~

During review-service maintenance, operations can switch to:

~~~text
STANDARD -> standardChannel
REVIEW   -> reviewBackupChannel
~~~

When changed under proper controls, the application needs no restart to shift traffic. However, if a new rule creates a path back to an upstream router, an outage can happen immediately upon activation.

### 2.1. Four Ways Routing Can Change

| Approach | What changes | Characteristic complexity risk |
| --- | --- | --- |
| **Change channel mappings** | Keys like REVIEW point to a different channel | Wrong bean, cycles, intermediate states during per-key updates |
| **Change key-selection policy** | Thresholds, categories, time/tenant conditions | Growing condition count, hard-to-predict logic, inconsistent outcomes across retries |
| **Add/remove recipients** | Destination count in `RecipientListRouter` | Fan-out, duplicate recipients, one failing branch affecting others |
| **Register `IntegrationFlow` at runtime** | New endpoints, channels, and topology | Lifecycle, resources, bean-name collisions, cleanup, observability |

This lesson focuses on **bounding decision and path complexity**. When registering/removing `IntegrationFlow` instances at runtime, you must also manage lifecycle via `IntegrationFlowContext` and bean ownership; do not treat that as a simple mapping update.

### 2.2. Dynamic Does Not Mean Parallel

A router can select multiple destinations, yet updating a mapping does not spawn new threads by itself. Dispatch behavior depends on the target channel:

- **DirectChannel** typically processes synchronously on the sender thread.
- **ExecutorChannel** hands dispatch off to an executor.
- **QueueChannel** buffers messages for a consumer/poller.
- **PublishSubscribeChannel** can broadcast to multiple subscribers.

Changing topology can alter **latency**, **threads**, **transaction boundaries**, **error propagation**, and backlog potential. Complexity checks must therefore include operational cost, not just condition counts in code.

## 3. Dimensions of Runtime Route Complexity

Define measurable variables rather than merely counting lines in a config file:

| Symbol | Meaning | Risk as it grows |
| --- | --- | --- |
| **R** | Number of rules/predicates to evaluate | CPU, latency, unclear rule precedence |
| **C** | Average or maximum cost per predicate | Blocking I/O, repeated DB queries, timeouts |
| **F** | Number of recipients chosen per message at one router | Fan-out, task count, and side effects |
| **H** | Maximum routing hops along a path | Latency, cycles, and stack depth |
| **V** | Number of simultaneously active configuration versions | Inconsistent replays, difficult rollbacks |
| **Q** | Backlog of messages queued across branches | Memory/disk consumption, processing lag |
| **T** | Number of tenants/groups with custom policies | Cardinality and config-management pressure |
| **E** | Number of valid edges in the channel/endpoint graph | Hard to review route cycles and fan-out |

A router choosing a branch after linearly scanning R rules has a decision cost of **approximately O(R × C)** when all rules must be checked. Looking up a channel name in a hash map after computing a key is usually much cheaper; however, computing the key itself via network queries or heavy scripts can dominate total time.

If a message fans out uniformly to at most F branches per layer, the total node count can grow up to roughly:

\[
1 + F + F^2 + \dots + F^H
= \frac{F^{H+1}-1}{F-1}\quad (F>1).
\]

This is an **illustrative bound for a complete branching tree**, not a claim that every `IntegrationFlow` grows exponentially. In practice, branches can terminate early, converge, or avoid fan-out. The key takeaway is that leaving **both F and H unbounded** produces a massive worst case.

For example, F=3 and H=4 produce up to **121 processing sites** if every branch splits three ways at each layer (including root). Adding just one more layer raises the bound to **364 sites**. If several branches trigger side effects, cost and duplication risk escalate rapidly.

### 3.1. Not All Rules Have the Same Cost

Compare:

~~~java
// Cheap computation, no side effects:
boolean needsReview(OrderEvent event) {
    return event.amountVnd().compareTo(REVIEW_THRESHOLD) >= 0;
}

// Questionable structure: performs a network query on every route.
boolean needsReviewWithRemoteLookup(OrderEvent event) {
    return riskService.lookup(event.customerId()).requiresReview();
}
~~~

The snippet above **illustrates predicate types**, with `OrderEvent`, `REVIEW_THRESHOLD`, and `riskService` as hypothetical dependencies. The second predicate can cause high latency, amplify request load, time out, and create failure loops if `riskService` calls back into the flow.

When routing decisions depend on external service data, consider **enriching the message in a separate step** with timeouts/circuit breakers, then routing with a pure rule over the enriched data. This makes per-step cost and failures easier to test.

## 4. Establishing a Complexity Budget

An organization can define an application-level **route budget** and validate it before activating new rules. The numbers below are **illustrative study examples**, not Spring Integration defaults or hard limits.

| Attribute | Example budget | Action when exceeded |
| --- | ---: | --- |
| Active rules per policy | 24 | Reject new config or split domains deliberately |
| Max recipients per router | 3 | Reject overly broad fan-out configs |
| Routing hops per workflow | 8 | Route to error/quarantine; stop further routing |
| Revisits to the same step for one event | 1, unless flow explicitly models valid loops | Detect cycle and halt |
| Policy versions retained for replay | Per event lifetime | Manage retention and migration |
| Queue capacity per branch | Bounded by throughput/latency SLO | Backpressure or controlled rejection |
| Route decision time | Per latency SLO | Alert and optimize rules; forbid unbounded I/O |

**Budgets only make sense when tied to SLOs and real telemetry.** A route with just two rules where each makes a 10-second API call is still worse than 20 pure rules running in microseconds. Four independent recipients can be reasonable if all are required by business rules and capacity exists, whereas two recipients writing the same side effect can be a bug.

### 4.1. Three Levels of Control

1. **Before activation:** validate rule count, destination names, duplicate recipients, bean references, potential cycles, and compatibility.
2. **During message processing:** enforce hop/fan-out limits via runtime budgets, bounded timeouts, fallback/error flows, and idempotency.
3. **After activation:** monitor metrics, tracing, resource usage, canary rollouts, and roll back to an old snapshot if SLOs are breached.

A static validator cannot catch every loop when routes depend on payloads or runtime-changing strategies. Conversely, relying solely on a runtime hop counter does not prove a topology is safe at deployment time. Both are needed.

## 5. Routing Graphs: Checking Cycles and Fan-Out

Model the topology as a directed graph:

- **Vertices:** Routers, handlers, channels, or step groups with clear semantics.
- **Edges:** paths along which a message can move from one vertex to another.
- **Conditional branches:** edges traversed only when a predicate matches.
- **Cycles:** paths returning to an already visited vertex.

~~~mermaid
flowchart LR
    A["ingress"] --> R1["router A"]
    R1 -->|"STANDARD"| S["standard handler"]
    R1 -->|"REVIEW"| R2["router B"]
    R2 -->|"normal"| C["review handler"]
    R2 -->|"wrong mapping"| R1
~~~

The path **R1 → R2 → R1** is a potential cycle. If the routers run synchronously and keep taking this loop, the call stack can grow uncontrollably. If the loop crosses queues, messages can circulate indefinitely and starve consumers.

### 5.1. Static Checks on Candidate Configurations

Before activation, run **DFS/topological validation** over the edges supplied by the candidate:

1. Identify the list of allowed destinations.
2. Normalize edges and verify endpoint/channel names exist.
3. Detect duplicate edges or duplicate recipient identities.
4. Use DFS to detect cycles if the workflow **must be acyclic**.
5. Estimate maximum fan-out or routing hop depth along valid paths.
6. Reject candidates exceeding the budget; record a clear reason.

If a workflow intentionally loops, such as **bounded retries**, do not reject all cycles unconditionally. Instead, mark allowed retry edges and require explicit **termination conditions** plus an attempt/hop budget. A conditional business retry loop differs from an accidental mapping cycle.

### 5.2. Runtime Control with a Hop Budget

In flows with nested routers, each traversal across a routing boundary should update a server-managed **`routeHops`** counter. Before forwarding:

- If `maxHops` is exceeded, **stop** and route to error/quarantine with metadata.
- If a non-repeatable step has already been visited, flag a cycle.
- When receiving messages from untrusted clients or brokers, **never trust** client-supplied `routeHops` headers.

A hop budget only **limits damage**; it does not replace topology checks. For replays, distinguish **hops within one attempt** from **total attempts**; resetting hops per replay can be valid provided a separate **durable retry budget** prevents infinite loops across restarts.

## 6. Never Turn External Data into Arbitrary Channel Names

The biggest security risk of a dynamic router is using an **untrusted routing key** as a **bean name**. Inputs like **`internalAdminChannel`** or **`routerInputChannel`** must never automatically become valid destinations just because a matching bean exists.

In `AbstractMappingMessageRouter`, **`channelKeyFallback=true`** allows unmapped keys to be treated as channel names. When an application processes untrusted inputs, generally set **`channelKeyFallback(false)`** and map keys from a **fixed allowlist** to vetted channels.

~~~mermaid
flowchart LR
    U["Client / Broker event"] --> B["Validate + authenticate"]
    B --> K["Policy computes routing key"]
    K --> M{"Allowlisted mapping"}
    M -->|"STANDARD"| S["standardChannel"]
    M -->|"REVIEW"| R["reviewChannel"]
    M -->|"Unknown"| Q["quarantineChannel"]
~~~

Additional rules:

- Tenant, role, permissions, and business state must come from **verified** sources, not merely headers claiming to be trusted.
- Never let users inject arbitrary channel names, Java class names, or SpEL expressions into runtime rules.
- If an admin API exists to change rules, separate it from message-submission APIs; require strong authentication, authorization, auditing, and rate limiting.
- Never allow a new route to bypass mandatory auditing, validation, or permission checks.
- When dynamic external destinations are needed, use a **controlled registry/alias** rather than resolving arbitrary bean names from `ApplicationContext`.

**Bounding complexity is also a security control**: it prevents a buggy or abused rule from opening hundreds of branches, creating loops, or invoking unintended endpoints.

## 7. Recommended Architecture: Dynamic Policy, Finite Channel Set

One way to bound complexity is **allowing policies to change** without allowing them to generate arbitrary channel names across the system.

For example, policies can adjust risk thresholds, item categories needing review, or activation schedules. Yet the final decision must stay within three route keys:

~~~text
STANDARD
REVIEW
QUARANTINE
~~~

Topology to these three channels is declared and tested upfront. When the policy changes, the router still has **three possible targets**; it cannot increase recipient count, inject client-supplied channel names, or loop back to input via an unbounded mapping table.

~~~mermaid
flowchart TD
    E["DispatchRequested"] --> V["Validate input + tenant"]
    V --> P["Immutable policy snapshot<br/>version=N"]
    P --> D{"Route decision"}
    D -->|"STANDARD"| S["standardChannel"]
    D -->|"REVIEW"| R["reviewChannel"]
    D -->|"UNKNOWN/INVALID"| Q["quarantineChannel"]
~~~

This is **dynamic business policy** over a **fixed routing topology**. When business requirements only need branch-selection criteria to change, this approach is usually far easier to govern than adding/removing `IntegrationFlow` definitions or recipients continuously at runtime.

### 7.1. Benefits of Immutable Snapshots

- Every routing decision reads **one complete policy**, never seeing a new threshold paired with an old category list.
- Includes a **version** for logging, tracing, and rollback.
- Candidates can be validated before activation.
- An update only swaps the snapshot reference rather than mutating rules in place.
- No long locks needed around the entire routing path.

**Limitation:** `AtomicReference` only ensures atomic reference updates **within one JVM**. It does not synchronize application instances, persist versions across restarts, or ensure every endpoint in a multi-step workflow uses the same snapshot if they keep reading global policy at different times.

## 8. Implementing Policy Snapshots in Java 17+

The following example uses a simple rule:

- Items in a risk category require review.
- Or orders reaching the value threshold require review.
- Everything else goes to standard.

### 8.1. Business Data and Decision Record

~~~java
import java.math.BigDecimal;

record DispatchRequested(
        String eventId,
        String tenantId,
        String category,
        BigDecimal amountVnd) {}

record RoutedDispatch(
        DispatchRequested event,
        String routeKey,
        long policyVersion) {}
~~~

In production, **`tenantId` must come from an authenticated source**; never treat a `tenantId` inside the record as automatically trustworthy. `eventId` must stay stable across retries of the same event.

### 8.2. Defining a Validated Immutable Snapshot

~~~java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Set;

record RoutePolicySnapshot(
        long version,
        BigDecimal reviewThresholdVnd,
        Set<String> riskCategories) {

    RoutePolicySnapshot {
        if (version <= 0) {
            throw new IllegalArgumentException("Invalid version");
        }
        if (reviewThresholdVnd == null
                || reviewThresholdVnd.signum() <= 0) {
            throw new IllegalArgumentException("Invalid threshold");
        }
        Objects.requireNonNull(riskCategories, "riskCategories");
        if (riskCategories.size() > 16) {
            throw new IllegalArgumentException("Too many category rules");
        }
        for (String category : riskCategories) {
            if (category == null
                    || !category.matches("[A-Z0-9_-]{1,40}")) {
                throw new IllegalArgumentException("Invalid category format");
            }
        }
        riskCategories = Set.copyOf(riskCategories);
    }
}
~~~

Here **16** is an illustrative budget for a membership-style rule set, not a Spring Integration limit. The constructor uses **`Set.copyOf`** so external code cannot mutate the collection after snapshot publication. The record prevents reassigning references, while the immutable collection prevents mutating the category set through an alias.

### 8.3. Policy Engine Selecting a Finite Route Key

~~~java
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

final class BoundedRoutingPolicy {
    private final AtomicReference<RoutePolicySnapshot> current;

    BoundedRoutingPolicy(RoutePolicySnapshot initial) {
        current = new AtomicReference<>(
                Objects.requireNonNull(initial));
    }

    RoutedDispatch decide(DispatchRequested event) {
        validate(event);

        // Read exactly one snapshot per decision.
        RoutePolicySnapshot snapshot = current.get();
        String normalizedCategory =
                event.category().trim().toUpperCase(Locale.ROOT);

        boolean review =
                event.amountVnd().compareTo(
                        snapshot.reviewThresholdVnd()) >= 0
                || snapshot.riskCategories().contains(normalizedCategory);

        return new RoutedDispatch(
                event,
                review ? "REVIEW" : "STANDARD",
                snapshot.version());
    }

    void activate(RoutePolicySnapshot next) {
        Objects.requireNonNull(next, "next");

        // Side-effect-free update function, safe under CAS retries.
        current.updateAndGet(previous -> {
            if (next.version() <= previous.version()) {
                throw new IllegalArgumentException(
                        "New version must be greater than current version");
            }
            return next;
        });
    }

    RoutePolicySnapshot currentSnapshot() {
        return current.get();
    }

    private static void validate(DispatchRequested event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.category() == null
                || event.category().isBlank()
                || event.amountVnd() == null
                || event.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid DispatchRequested");
        }
    }
}
~~~

**Key points:**

1. Route keys can only be **STANDARD** or **REVIEW** in this example; the number of destinations does not grow with the number of categories.
2. No database queries, HTTP calls, or script execution occur on each routing decision.
3. Decisions carry **`policyVersion`** to trace which version was used.
4. Updates are rejected unless the version advances; this illustrates monotonic policy versioning.
5. Updating this JVM **does not automatically push** to other JVMs. System-level version distribution, sync confirmation, and rollback mechanisms are needed.

When rolling back a faulty policy, you do not have to reuse the old version number. You can publish a **new version** containing the previous good policy's contents so version numbers keep increasing monotonically with a clean audit trail.

### 8.4. Wiring the Policy with Java DSL

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class BoundedRouterConfiguration {

    @Bean
    BoundedRoutingPolicy boundedRoutingPolicy() {
        return new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1,
                        new BigDecimal("10000000"),
                        Set.of("HAZMAT", "OVERSIZE")));
    }

    @Bean
    MessageChannel dispatchInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel reviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel quarantineChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow boundedDispatchFlow(BoundedRoutingPolicy policy) {
        return IntegrationFlow.from("dispatchInputChannel")
                .transform(DispatchRequested.class, policy::decide)
                .<RoutedDispatch, String>route(
                        RoutedDispatch::routeKey,
                        mapping -> mapping
                                .channelMapping(
                                        "STANDARD", "standardChannel")
                                .channelMapping(
                                        "REVIEW", "reviewChannel")
                                .channelKeyFallback(false)
                                .defaultOutputChannel(
                                        "quarantineChannel"))
                .get();
    }
}
~~~

Target channels must have real **consumers/subflows**. The Transformer step builds `RoutedDispatch` to keep both the event and `policyVersion` together; downstream handlers must expect the updated payload type rather than assuming they still receive `DispatchRequested`.

Quarantine acts as a safe landing path for an unmapped route key. **Invalid input data** in the current policy code throws an exception before reaching the Router, requiring separate error handling/validation. Do not assume `defaultOutputChannel` will automatically catch Transformer exceptions.

**The dynamic part** in this example is `BoundedRoutingPolicy`'s data updated at runtime, while the `channelMapping` table remains finite. This deliberately **bounds runtime route complexity**.

### 8.5. Branch Handlers Perform Only Their Own Responsibilities

~~~java
interface StandardDispatchPort {
    void submit(DispatchRequested event);
}

interface ReviewDispatchPort {
    void review(DispatchRequested event);
}

// Placed inside the @Configuration class above:
@Bean
IntegrationFlow standardFlow(StandardDispatchPort port) {
    return IntegrationFlow.from("standardChannel")
            .handle(RoutedDispatch.class, (decision, headers) -> {
                port.submit(decision.event());
                return null;
            })
            .get();
}

@Bean
IntegrationFlow reviewFlow(ReviewDispatchPort port) {
    return IntegrationFlow.from("reviewChannel")
            .handle(RoutedDispatch.class, (decision, headers) -> {
                port.review(decision.event());
                return null;
            })
            .get();
}
~~~

These two ports are illustrative business abstractions. Real implementations can add idempotency by `eventId + logicalRecipientId`, retries, and appropriate transactions. If an event re-runs after policy changes, determine whether it must follow the **old route** or the new route; see the consistency and replay sections.

## 9. Bounding Fan-Out When Selecting Multiple Recipients

Not every dynamic routing scenario picks just one destination. A system may need to send events conditionally to **audit**, **notification**, **risk review**, and partners. When using `RecipientListRouter`, manage both **recipient count** and **uniqueness of responsibility**.

### 9.1. Do Not Add the Same Destination Multiple Times

~~~java
// Suspicious: the same auditChannel is registered twice.
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                message -> isPriority(message.getPayload()))
        .recipientMessageSelector("auditChannel",
                message -> isInternational(message.getPayload())))
~~~

If audit must receive messages that are **priority or international**, use **one recipient** with an OR condition:

~~~java
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                message -> isPriority(message.getPayload())
                        || isInternational(message.getPayload())))
~~~

Both snippets are **illustrative DSL fragments** assuming `isPriority`/`isInternational` are defined. Do not rely on the framework automatically deduplicating identical entries across all versions/configurations; validate topology and test exact delivery counts.

### 9.2. Never Accept Recipient Lists Directly from External Messages

A user might send a list of 1,000 recipients, whereas business rules only permit internal channels `AUDIT`, `RISK`, and `NOTIFICATION`. You must:

1. Map **recipient identities** into an allowed enum/alias set.
2. Validate permissions, event types, and recipient counts.
3. Use a **Set** to detect or prevent duplicate identities, not to silently hide configuration bugs.
4. Map valid aliases to declared channels.
5. Reject or quarantine when fan-out exceeds budget.

One `RecipientListRouter` call can send to multiple channels; **`send()` returning successfully** does not guarantee all downstream side effects committed, especially across `ExecutorChannel`/`QueueChannel` or async adapters.

### 9.3. `RecipientListRouter` Can Change at Runtime

Spring Integration provides **`RecipientListRouterManagement`** to add/remove recipients via management operations, accessible via **Control Bus/JMX** when enabled. This helps maintain routes without restarts, but does not automatically bound:

- How many recipients can be added.
- Who is authorized to update them.
- Whether duplicate identities or loops are introduced.
- Whether multiple sequential add/remove calls act as one atomic snapshot.
- Whether in-flight messages see a consistent recipient set.

Before performing updates, validate the **candidate recipient set** as a logical unit. If business rules require all messages within a window to see one exact version, design explicit **snapshots/versioning** rather than assuming separate add/remove commands form a transaction.

## 10. Spring Integration's Runtime Mapping Management Mechanisms

For routers extending **`AbstractMappingMessageRouter`**, Spring Integration provides specific management methods:

| API | Effect | Caveats |
| --- | --- | --- |
| **setChannelMapping(key, channelName)** | Add or replace one mapping | Multiple calls do not form a whole-table atomic update |
| **removeChannelMapping(key)** | Remove one mapping | Can leave gaps during config transitions |
| **getChannelMappings()** | Read current mappings for observation | Never treat stale reads as proof of the new version |
| **setChannelMappings(Map)** | Replace mapping table from a map | Validate map first; preferred for programmatic updates |
| **replaceChannelMappings(Properties)** | Replace mapping table, suited for Control Bus | Accepts appropriate string keys/values only |
| **setChannelKeyFallback(false)** | Never use unmapped keys as channel names | Enforces allowlist, reduces loop risks |
| **setDynamicChannelLimit(n)** | Limits dynamic channel names **retained for reporting** | **Not** a quota on fan-out, hops, or allowed destinations |

**Important note:** the method name **`setDynamicChannelLimit`** easily misleads readers into thinking it prevents the router from sending to too many channels. According to the Java API, its purpose is limiting how many **dynamic channel names are remembered for reporting**, not enforcing a security quota on fan-out or flow depth.

### 10.1. Why Multiple Individual Updates Are Dangerous

Suppose the application wants to switch:

~~~text
A -> channel1
B -> channel2
~~~

to:

~~~text
A -> channel3
B -> channel4
~~~

Calling `setChannelMapping(A, channel3)` and then `setChannelMapping(B, channel4)` creates a window between the two calls where the mapping table has **new A, old B**. Concurrent messages can be routed under an unapproved hybrid combination.

~~~mermaid
sequenceDiagram
    participant U as Admin
    participant R as Router
    participant M as Message producer
    U->>R: setChannelMapping(A, channel3)
    M->>R: Message key B
    R-->>M: channel2 from intermediate table
    U->>R: setChannelMapping(B, channel4)
~~~

Official Spring Integration documentation recommends **updating the entire table** when related keys must change atomically. Since Spring Integration 4.0, `replaceChannelMappings` supports whole-table replacement via Control Bus; when updating from Java code, **`setChannelMappings(Map)`** is more strongly typed.

A whole-table update may be atomic for **one router within one process**, but does not simultaneously update **all routers, all instances, and all in-flight messages**. A version/rollout coordinator is still needed if distributed consistency is required.

### 10.2. Example: Enforcing a Budget Before Updating

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.integration.router.HeaderValueRouter;

final class SafeMappingUpdater {
    private static final int MAX_MAPPINGS = 12;
    private static final Set<String> ALLOWED_CHANNELS = Set.of(
            "standardChannel",
            "reviewChannel",
            "reviewBackupChannel",
            "quarantineChannel");

    void activate(
            HeaderValueRouter router,
            Map<String, String> candidate) {

        if (candidate == null
                || candidate.isEmpty()
                || candidate.size() > MAX_MAPPINGS) {
            throw new IllegalArgumentException("Mapping limit exceeded");
        }
        if (!ALLOWED_CHANNELS.containsAll(candidate.values())) {
            throw new IllegalArgumentException(
                    "Destination outside allowlist");
        }
        for (String key : candidate.keySet()) {
            if (key == null
                    || !key.matches("[A-Z0-9_-]{1,40}")) {
                throw new IllegalArgumentException(
                        "Invalid routing key");
            }
        }

        // Additional cycle, permission, and bean-resolution checks
        // can be run here before applying the change.
        router.setChannelMappings(Map.copyOf(candidate));
    }
}
~~~

This is a **pre-update validation** layer. It does not yet check whether channel beans exist, have subscribers, or form route cycles; add topology checks and rollout governance. If the candidate is invalid, the method **never calls `router.setChannelMappings`**.

**Never pass a `Map` directly from an HTTP client** into `setChannelMappings`. Allow updates only through an authenticated, authorized, audited administrative channel; every change should carry `policyVersion`, approver, and reason.

### 10.3. Control Bus Is Not a Public Endpoint

Control Bus allows sending **control messages** to invoke management methods on components. It is a powerful mechanism; exposing it directly to untrusted environments allows outsiders to alter routes or manipulate other beans.

Operational safeguards:

- Restrict control-channel ingress and authenticate admins.
- Validate candidates before constructing control messages.
- Enable audit logging for actor, old/new version, apply result, and rollback.
- Never allow users to submit arbitrary SpEL.
- Never share the Control Bus ingress with untrusted business events.

**Control Bus handles delivering the update**, not policy validation, authorization, or cross-service impact control.

## 11. Runtime Guard: Bounding Hops for a Single Message

Static validators only see paths in approved static configs. When routing conditions change continuously or a branch sends messages back upstream, enforce a **hop limit inside the flow**.

A minimal guard receives a `Message<?>` that has passed the trust boundary, reads the **internally managed** hop count, and builds the next message with the count incremented by one.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class RouteHopGuard {
    private final int maxHops;

    RouteHopGuard(int maxHops) {
        if (maxHops <= 0) {
            throw new IllegalArgumentException("maxHops must be positive");
        }
        this.maxHops = maxHops;
    }

    Message<?> enterNextRouter(Message<?> message) {
        Object raw = message.getHeaders().get("trustedRouteHops");

        int previous;
        if (raw == null) {
            previous = 0;
        } else if (raw instanceof Integer value && value >= 0) {
            previous = value;
        } else {
            throw new IllegalArgumentException(
                    "Invalid hop count header");
        }

        if (previous >= maxHops) {
            throw new IllegalStateException(
                    "ROUTING_HOP_BUDGET_EXCEEDED");
        }

        return MessageBuilder.fromMessage(message)
                .setHeader("trustedRouteHops", previous + 1)
                .build();
    }
}
~~~

**Usage:** place the guard **before every router boundary** whose hops must be counted. If a workflow spans multiple services, each hop must propagate trusted metadata or maintain state with equivalent bounds. When budget is exceeded, route the error to a categorized **error flow/quarantine**, never back into the same channel.

### 11.1. What the Guard Cannot Solve Alone

- If code sends a message directly to a channel **bypassing the guard**, the budget is not enforced on that path.
- If an external producer sets `trustedRouteHops=0` and an adapter copies it straight through, it can **reset** the limit. Strip or verify the header at the trust boundary.
- If each retry builds a fresh message with hop count 0, **infinite retries across attempts** remain possible. Enforce a durable retry budget and workflow TTL.
- If a step both sends messages upstream and spawns child messages, track **total dispatches per event** when a global budget is required, not merely one branch's hop depth.
- When valid loops exist, track a **logical iteration ID** and cap iterations rather than banning all revisits by channel name alone.

**Never enforce a budget with an unsigned header if sources can tamper with headers.** Distributed systems need signed/trusted producers or a reliable state store holding workflow budgets.

### 11.2. Managing the Fan-Out Budget

`maxHops` does not limit how many branches a single router spawns. With recipient lists, enforce:

~~~text
selectedRecipients.size <= maxFanoutPerRouter
~~~

When multiple routers chain together, also bound **`totalDispatchesPerEvent`** or a workflow-wide resource budget if required by business rules. Workflow-wide counters must be updated safely under concurrency/distribution; a local in-JVM variable does not enforce a cluster-wide quota.

**Cost model:** if one message fans out 3 ways at the first layer and each splits 3 ways again, total deliveries grow even at depth 2. On I/O-heavy branches, the fan-out budget matters just as much as hop depth.

## 12. Runtime Routes Changing While Messages Are In Flight

When configuration updates, three message groups can exist:

1. **Already routed** before the update and running downstream.
2. **Mid-decision** computing keys or resolving destinations.
3. **Newly arrived** after the new policy activated.

With immutable snapshots, each **`decide()`** call in our example uses one snapshot to pick a route and attach `policyVersion`. However, that does not lock downstream steps to the same version if they re-read global policy later.

### 12.1. Pinning Version Per Logical Event

If the same event must **keep its initial route** across retries/redeliveries, persist a durable decision:

~~~text
eventId: evt-9001
policyVersion: 12
routeKey: REVIEW
decisionStatus: COMMITTED
~~~

After first accepting the event, the system can persist the route decision alongside `eventId` (inbox/outbox or workflow state). On replay, look up the **committed `routeKey`** instead of recomputing under the new policy. If the old route is retired, apply an explicit migration/quarantine policy rather than silently switching routes if doing so risks duplicate side effects or inconsistent workflows.

If business rules accept **recomputing routes under the new policy** on retry, document that contract explicitly and ensure consumers are idempotent. Both choices can be valid, but they are not interchangeable defaults.

### 12.2. Changing Routes Does Not Undo Prior Side Effects

Suppose an event was sent to `reviewChannel` under version 12, and version 13 switches `REVIEW` to `reviewBackupChannel`. When the producer retries the entire event:

- The old review handler may already have created a review ticket.
- The new review handler may create a second ticket.

To ensure **one logical review request**, use a **stable idempotency key** such as `tenantId + eventId + logicalActionId` and define action ownership. Changing a mapping does not migrate processing state or roll back tickets on the old channel.

### 12.3. Multi-Instance Deployments and Versioned Rollouts

`AtomicReference` inside each JVM does not distribute changes across replicas A/B/C. When updating policy:

1. Publish candidate with **version** and checksum.
2. Each instance loads and validates the candidate.
3. Coordinator awaits sufficient acknowledgments or takes un-synced instances out of consistency-sensitive traffic.
4. Activate version per rollout strategy: coordinated cutover, canary, or gradual.
5. Track which instance is running which version.
6. On rollback, publish a new version with the old policy contents to avoid version-ordering conflicts.

**No single strategy fits all systems.** Canarying works well when events are independent and temporary route differences are acceptable; some workflows require all messages in a correlation group to share one `policyVersion`.

## 13. Error Handling and Default Paths

A dynamic router must distinguish **inability to pick a route** from **a chosen route failing during processing**.

| Scenario | Nature | Action |
| --- | --- | --- |
| Routing key has no mapping | Unknown/unsupported route | Default output channel or fail fast |
| New rule returns non-existent bean name | Config bug or incomplete deploy | Reject pre-activation; alert if seen at runtime |
| Destination `DirectChannel` has no subscriber | Wiring/delivery error | Do not treat as unknown key |
| `ExecutorChannel` rejects task | Backpressure/rejection | Bounded retry; avoid unbounded task creation |
| `QueueChannel` receives message with no poller | Backlog | Monitor depth, wait time, consumer health |
| Handler external API call fails | Downstream error | Per-branch error flow, retry/idempotency |
| Rule is slow or throws exception | Decision-time failure | Fail fast/quarantine; log version and reason |
| Hop/fan-out budget exceeded | Resource policy violation | Stop routing, error/quarantine, alert |

### 13.1. Default Output Channel Is Not a Safety Net for All Errors

A default output channel is used when the router **cannot determine a valid channel** per config. It **does not catch** exceptions thrown by a chosen handler. Post-send errors depend on `DirectChannel`, `ExecutorChannel`, `QueueChannel`, adapters, and error handlers.

If unknown messages go to quarantine, ensure there is a **real consumer persisting them**. A channel named `quarantineChannel` with no subscriber/poller becomes a dead end. Storing messages only in RAM does not preserve replayability across restarts.

### 13.2. `channelKeyFallback` and `resolutionRequired`

In **`AbstractMappingMessageRouter`**:

- **`channelKeyFallback`** controls whether an unmapped key is treated as a **channel name**. Generally disable this for untrusted inputs.
- **`resolutionRequired`** determines whether unresolved channel names are tolerated. Generally set to `true` so bad names fail visibly.
- **`defaultOutputChannel`** specifies the fallback destination when no valid route is found.

Since **Spring Integration 6.0**, setting a default output channel also sets `channelKeyFallback=false` by default. Combining `defaultOutputChannel`, `channelKeyFallback=true`, and `resolutionRequired=true` is rejected at initialization as contradictory.

These options **do not create `maxRules`, `maxHops`, or `maxFanout`**; complexity bounds must still be built at the application/topology layer.

### 13.3. `ignoreSendFailures` Does Not Prevent Fan-Out Overload

In multi-recipient routers, `ignoreSendFailures(true)` lets the router keep sending to remaining recipients after synchronous send failures. It **does not reduce** the number of selected recipients, does not guarantee retries for failing branches, and can mask mandatory-branch failures.

Use **bounded executors/queues**, timeouts, and properly placed error channels. For critical side effects, enforce idempotency and durable delivery when recovery across restarts is required.

## 14. Reducing Rule Evaluation Cost

You do not always need more hardware to handle policies with many rules. Reduce complexity by:

1. **Normalizing data before routing**: valid types/formats for country codes, categories, and `eventType`.
2. **Separating validation and enrichment** from the router so predicates only read prepared fields.
3. **Favoring finite keys**: compute a `routeKey`, then look up the channel in a map instead of scattering branching conditions.
4. **Partitioning rule domains cleanly**: payment rules should not share one rule chain with document ingestion unless required.
5. **Ordering conditions deliberately**: check cheap conditions first without altering business precedence.
6. **Avoiding uncontrolled regex**: bound patterns, input lengths, and forbid user-uploaded expressions/scripts.
7. **Minimizing I/O in predicates**: use TTL/versioned caches or a separate enrichment step; account for data consistency.
8. **Avoiding dynamic `IntegrationFlow` creation per message** when one router and a fixed channel set suffice.

### 14.1. Rule Precedence and Explainability

When multiple rules match, specify:

- **First match wins**: one route chosen by explicit priority order.
- **Highest priority wins**: pick highest-priority rule with defined tie-breaking.
- **All matches**: fan out to all matching recipients, bounded by `maxFanout` and recipient deduplication.

Never mix all three semantics in one router without an explicit contract. During runtime updates, reordering rules can change routes even when every predicate stays unchanged.

**Recommendation:** keep evaluation results explainable, e.g., decisions carry **`routeKey`, `policyVersion`, `ruleId`**. For detailed reason logging, log a bounded `ruleId` rather than entire expressions or payloads.

### 14.2. When Should a Router Be Split Into Layers?

Splitting one 100-rule router into 10 routers is not automatically better. It can reduce predicates evaluated per message if the first layer selects the right domain, yet it adds hops, channels, failure modes, and transaction boundaries.

Evaluate based on **critical-path latency**, average decisions, observability, and topology stability. If one layer can branch into every other layer, cost and cognitive complexity can actually increase.

## 15. Unit Tests for Policy Snapshots

Tests must prove not only startup routing, but also:

- Only valid candidates can be activated.
- Decisions always return a route key from the allowed set.
- A decision consistently pairs **`routeKey + policyVersion`**.
- After an update, new policies apply to new messages.
- Stale or duplicate versions never silently overwrite the active version.

### 15.1. Updating Policy Without Growing Topology

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Set;

import org.junit.jupiter.api.Test;

class BoundedRoutingPolicyTest {

    @Test
    void newSnapshotChangesDecisionWithinFixedRouteKeys() {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1,
                        new BigDecimal("10000000"),
                        Set.of("HAZMAT")));

        DispatchRequested event = new DispatchRequested(
                "evt-100", "tenant-A", "NORMAL",
                new BigDecimal("5000000"));

        RoutedDispatch before = policy.decide(event);
        assertEquals("STANDARD", before.routeKey());
        assertEquals(1, before.policyVersion());

        policy.activate(new RoutePolicySnapshot(
                2,
                new BigDecimal("1000000"),
                Set.of("HAZMAT")));

        RoutedDispatch after = policy.decide(event);
        assertEquals("REVIEW", after.routeKey());
        assertEquals(2, after.policyVersion());
    }

    @Test
    void rejectsBackwardVersionAndExcessiveRules() {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        5, new BigDecimal("10000000"), Set.of()));

        assertThrows(IllegalArgumentException.class,
                () -> policy.activate(
                        new RoutePolicySnapshot(
                                4, new BigDecimal("100000"), Set.of())));

        assertEquals(5, policy.currentSnapshot().version());
        assertThrows(IllegalArgumentException.class,
                () -> new RoutePolicySnapshot(
                        6, BigDecimal.TEN, Set.of(
                                "C01","C02","C03","C04","C05",
                                "C06","C07","C08","C09","C10",
                                "C11","C12","C13","C14","C15",
                                "C16","C17")));
    }
}
~~~

Unit tests **need no Spring context**. They verify the policy engine before wiring it into an `IntegrationFlow`.

### 15.2. Concurrent Updates and Snapshot Consistency

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

class ConcurrentPolicySnapshotTest {

    @Test
    void eachDecisionUsesOneCompleteSnapshot() throws Exception {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1, new BigDecimal("10000000"), Set.of()));
        DispatchRequested event = new DispatchRequested(
                "evt-101", "tenant-A", "NORMAL",
                new BigDecimal("5000000"));

        ExecutorService pool = Executors.newFixedThreadPool(6);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<RoutedDispatch>> results = new ArrayList<>();
            for (int i = 0; i < 200; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    return policy.decide(event);
                }));
            }
            start.countDown();

            policy.activate(new RoutePolicySnapshot(
                    2, new BigDecimal("1000000"), Set.of()));

            for (Future<RoutedDispatch> result : results) {
                RoutedDispatch d = result.get();
                boolean fromVersion1 =
                        d.policyVersion() == 1
                                && "STANDARD".equals(d.routeKey());
                boolean fromVersion2 =
                        d.policyVersion() == 2
                                && "REVIEW".equals(d.routeKey());
                assertTrue(fromVersion1 || fromVersion2);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

The test accepts **both version 1 and version 2** because threads may start before or after `activate`. What it checks is **no half-old, half-new combinations**, such as version 1 paired with `REVIEW` from version 2's threshold.

This test only proves `AtomicReference` snapshots inside **one JVM**. It does not prove all replicas update simultaneously or that every message in a business workflow shares one version. Those require multi-instance and state-store integration tests.

## 16. Testing the Hop Guard and Checking Cycles

### 16.1. Testing Exact Hop Budget Enforcement

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class RouteHopGuardTest {

    @Test
    void permitsEightHopsButRejectsTheNinth() {
        RouteHopGuard guard = new RouteHopGuard(8);
        Message<?> current =
                MessageBuilder.withPayload("dispatch").build();

        for (int i = 0; i < 8; i++) {
            current = guard.enterNextRouter(current);
        }

        assertEquals(8,
                current.getHeaders().get("trustedRouteHops"));

        Message<?> exhausted = current;
        assertThrows(IllegalStateException.class,
                () -> guard.enterNextRouter(exhausted));
    }

    @Test
    void rejectsMalformedHopHeader() {
        RouteHopGuard guard = new RouteHopGuard(8);

        Message<String> externalLikeMessage =
                MessageBuilder.withPayload("dispatch")
                        .setHeader("trustedRouteHops", "invalid")
                        .build();

        assertThrows(IllegalArgumentException.class,
                () -> guard.enterNextRouter(externalLikeMessage));
    }
}
~~~

**Note:** this test exercises the guard function; it does not prove every Spring Integration path invokes the guard. Integration tests must also introduce a cycle in the graph and verify the flow halts via a bounded error path instead of spinning threads or queues endlessly.

### 16.2. Simple DAG Validator

If the system **forbids all route cycles**, validate the candidate graph prior to activation:

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

final class AcyclicRoutingGraphValidator {
    private static final int MAX_NODES = 100;
    private static final int MAX_EDGES = 200;

    private AcyclicRoutingGraphValidator() {}

    static void validate(Map<String, Set<String>> edges) {
        if (edges == null
                || edges.size() > MAX_NODES) {
            throw new IllegalArgumentException("Graph too large");
        }
        long edgeCount = 0;
        for (Map.Entry<String, Set<String>> entry
                : edges.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                throw new IllegalArgumentException("Invalid graph");
            }
            edgeCount += entry.getValue().size();
            if (edgeCount > MAX_EDGES) {
                throw new IllegalArgumentException("Too many edges");
            }
            if (!edges.keySet().containsAll(entry.getValue())) {
                throw new IllegalArgumentException(
                        "Undeclared destination present");
            }
        }

        Set<String> done = new HashSet<>();
        Set<String> visiting = new HashSet<>();
        for (String node : edges.keySet()) {
            if (hasCycle(node, edges, done, visiting)) {
                throw new IllegalArgumentException(
                        "Routing graph contains a cycle");
            }
        }
    }

    private static boolean hasCycle(
            String node,
            Map<String, Set<String>> edges,
            Set<String> done,
            Set<String> visiting) {
        if (visiting.contains(node)) {
            return true;
        }
        if (done.contains(node)) {
            return false;
        }

        visiting.add(node);
        for (String next : edges.getOrDefault(node, Set.of())) {
            if (hasCycle(next, edges, done, visiting)) {
                return true;
            }
        }
        visiting.remove(node);
        done.add(node);
        return false;
    }
}
~~~

Test example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class AcyclicRoutingGraphValidatorTest {

    @Test
    void acceptsSimpleAcyclicGraph() {
        assertDoesNotThrow(() ->
                AcyclicRoutingGraphValidator.validate(Map.of(
                        "ingress", Set.of("router"),
                        "router", Set.of("review", "standard"),
                        "review", Set.of(),
                        "standard", Set.of())));
    }

    @Test
    void rejectsCycleReturningToIngress() {
        assertThrows(IllegalArgumentException.class, () ->
                AcyclicRoutingGraphValidator.validate(Map.of(
                        "ingress", Set.of("router"),
                        "router", Set.of("ingress"))));
    }
}
~~~

This validator checks **an abstract graph with explicitly enumerated nodes and edges**. Extracting Spring Integration topology from `ApplicationContext`, subflows, Control Bus, and code-computed routes is not always statically decidable. When edges depend on runtime data, combine static checks with a **hop guard**, max attempt limits, and real integration tests.

In applications with legitimate business loops, use a specialized validator that recognizes approved looping edges rather than abandoning cycle checks altogether.

## 17. Testing Mapping Replacement Without Exposing Intermediate States

### 17.1. Invalid Candidates Must Not Affect the Live Table

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.integration.router.HeaderValueRouter;

class SafeMappingUpdaterTest {

    @Test
    void rejectUnauthorizedDestinationWithoutChangingMappings() {
        HeaderValueRouter router =
                new HeaderValueRouter("trustedRoute");
        router.setChannelMappings(
                Map.of("STANDARD", "standardChannel"));

        SafeMappingUpdater updater = new SafeMappingUpdater();
        Map<String, String> before =
                Map.copyOf(router.getChannelMappings());

        assertThrows(IllegalArgumentException.class,
                () -> updater.activate(router,
                        Map.of("STANDARD", "privilegedOpsChannel")));

        assertEquals(before, router.getChannelMappings());
    }
}
~~~

This test needs no subscribers to verify mapping validation. In a real app, add **concurrent integration tests**: send many messages while swapping A/B mappings, verifying each message routes under a valid table without observing intermediate combinations.

### 17.2. Cases to Run Against a Real Spring Context

| Scenario | Expected outcome |
| --- | --- |
| Candidate with few rules, all channels exist | Activated successfully; routes as expected |
| Candidate with non-allowlisted channel | Rejected before applying |
| Candidate forming cycle R1 → R2 → R1 | Blocked by validator or halted by hop guard |
| Candidate raises fan-out above max | Rejected or requires special approval flow |
| Channel removed while messages remain | Drain/stop/quarantine policy takes effect |
| Two related keys remapped together | No unintended temporary combinations occur |
| Snapshot updated during active routing | Decision carries consistent version and key |
| Three instances on different versions | Skew detected; rollout policy applied |
| Event replayed after version bump | Uses pinned route or recomputes per contract |
| Remote predicate times out | Error bounded; never hangs router indefinitely |
| Unknown routing key | Default/quarantine or fail fast per policy |
| `DirectChannel` has no subscriber | Wiring error detected; not treated as unknown key |
| Retry after partial side effect | No duplicate business effect created |

### 17.3. Property-Based and Load Testing

Beyond individual cases, generate thousands of valid/random inputs and check **invariants**:

- Route keys always stay within **STANDARD/REVIEW** (or the designed valid route set).
- No channel name falls outside the allowlist.
- Selected recipient count never exceeds `maxFanout`.
- Hop count per attempt never exceeds `maxHops`.
- Same `policyVersion` and same input yield deterministic results when predicates do not depend on external state.
- Every invalid candidate is rejected with the live policy untouched.

Load tests should measure **p95/p99 latency of the routing decision itself**, end-to-end flow time, CPU, queue depth, send-failure rate, and retry volume. A router that is fast in unit tests can still bottleneck if multiple downstream branches are slow or fan-out is large.

## 18. Observability: Measuring the Right Complexity

Track both **decision outcomes** and **workflow expansion**:

| Metric | Purpose |
| --- | --- |
| **route_decisions_total{route,version}** | How many messages pick each route/version |
| **route_decision_duration_seconds** | Time spent computing keys / choosing routes |
| **route_rule_evaluation_errors_total** | Predicate evaluation errors |
| **route_candidate_rejected_total{reason}** | New candidates exceeding budget or failing validation |
| **route_policy_version_active{instance}** | Detect out-of-sync replicas |
| **route_fanout_count** | Recipients per message |
| **route_hop_budget_exceeded_total** | Detect cycles or excessively long paths |
| **route_unmatched_total** | Route keys matching no mapping |
| **route_channel_resolution_errors_total** | Mappings to non-existent channels |
| **route_send_failures_total{channel}** | Destinations rejecting sends |
| **route_queue_depth{channel}** | Backlogs on queued branches |
| **route_replay_count** | Events reprocessed |
| **route_idempotency_skips_total** | Duplicate business effects prevented |

In production, bounded labels like **version**, **instance**, or **channel** are appropriate. Never use **`eventId`, `tenantId`, `userId`, or unbounded raw routing keys** as metric labels because cardinality can explode. Per-event details belong in access-controlled tracing/logs stripped of sensitive data.

### 18.1. Recording the Routing Reason

A structured log might contain:

~~~json
{
  "eventId": "evt-100",
  "policyVersion": 12,
  "routeKey": "REVIEW",
  "matchedRuleId": "HIGH_VALUE",
  "hopCount": 2,
  "decisionDurationMs": 1.8,
  "status": "ROUTED"
}
~~~

This illustrates internal logging only; never log full payloads, payment details, or personal data. In multi-tenant setups, handle tenant IDs according to log access controls and retention policies.

### 18.2. Signals That Trigger Rollback

- Route decision p99 spikes right after activating a new version.
- Sudden surge in unknown keys, failed resolutions, hop-budget-exceeded, or fallbacks.
- Average or p99 fan-out exceeds budget.
- Queue depth and message age climb despite steady inbound rate.
- New loops, transaction timeouts, or repeated consumer failures appear.
- Some instances remain on old policies past the rollout deadline.
- Traffic to a critical branch drops to zero unexpectedly.

**Rollback must be a controlled operation**, not manually flipping one mapping back. If messages already entered the new branch and applied side effects, rollback does not undo them; enforce idempotency and handle remaining backlogs.

## 19. Runbook for Safely Updating Dynamic Router

A runtime change requires rigor comparable to a small deployment. Suppose operations wants to divert `REVIEW` from `reviewChannel` to `reviewBackupChannel` during a maintenance window.

### Step 1 — Create Candidate and Change Rationale

Record:

- Candidate `policyVersion`.
- Planned activation time.
- New routing keys, destinations, and rule logic.
- Affected channels/handlers list.
- Compatibility status between old and new branches.
- Proposer, approver, and rollback plan.

Never update a mapping just because a business request sent a new destination name. Every candidate must originate from an authorized administrative source with an audit trail.

### Step 2 — Validate Offline Before Touching the Live Router

1. Check schema, version, rule count, and fan-out/hop budgets.
2. Check **allowlist** for every destination.
3. Verify required channel beans/endpoints exist and are healthy.
4. Check for graph cycles and duplicate route identities.
5. Run route tests on key sample events and edge cases.
6. Check resource budgets if the new branch has lower throughput.
7. Verify how in-flight messages will be handled during the switch.

If the candidate fails, **do not touch** the live router. Record the rejection reason to help operators fix the policy.

### Step 3 — Apply Atomic Changes Within Supported Scope

- For mapping tables: use **`setChannelMappings(Map)`** or **`replaceChannelMappings(Properties)`** to swap the **entire table** when keys are interrelated.
- For pure Java policies: build an **immutable snapshot**, then swap the reference **once**.
- For multi-instance deployments: coordinate rollout versions and track version skew.
- With `RecipientListRouter` management using multiple add/remove calls: never assume separate calls are atomic; design explicit staging/versioning when consistency is required.

### Step 4 — Observe Canary and Operations

Track route decisions, response latency, queue depth, error channels, retries, and duplicate side effects. When the new branch serves only a slice of traffic, the canary must use a **deterministic cohort selection rule** so retries of the same event do not bounce unexpectedly between branches.

A canary rule drawing a random number **on every receipt** easily sends the same event to branch A on attempt 1 and branch B on attempt 2. Instead, compute cohorts from a **hash of a stable business key**, or persist the event's route decision at ingress.

### Step 5 — Roll Back or Complete

When issues occur, publish a new version pointing back to the prior safe configuration. Flag messages routed by the faulty version, monitor backlogs, and determine whether replay/reconciliation is needed.

**Rolling back a mapping is not rolling back a transaction.** Tasks that already sent emails, reserved stock, charged money, or called partners do not revert just because the mapping changed back.

## 20. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Allowing unlimited runtime rule additions | Unpredictable routing and operational cost | `MAX_RULES` and candidate validation |
| Letting clients supply channel names directly | Can route into unintended internal channels | Allowlist mappings and `channelKeyFallback(false)` |
| Updating interdependent mappings one by one | Messages see hybrid mapping tables | Whole-table atomic replacement within router |
| Using `setDynamicChannelLimit` to cap fan-out | Misunderstanding management API | Enforce `maxRecipients` separately in app code |
| Adding duplicate recipient entries to `RecipientListRouter` | Duplicate deliveries/side effects | Unique recipient identities, merge selectors |
| Using `maxHops` without bounding fan-out | A few layers still explode into too many branches | Bound `maxHops`, `maxFanout`, and total deliveries |
| Only running static DAG checks | Dynamic rules can still create undetected loops | Runtime hop/attempt guard plus tests |
| Only using runtime hop guards | Broken configs still activate and fail live | Preflight topology validation |
| Calling external APIs without timeouts in predicates | Routing holds threads and overloads | Separate enrichment with bounded timeouts/backoff |
| Mutating a shared `Map` entry by entry | Messages observe intermediate configs | Immutable snapshots / whole-table replacement |
| Updating policy inside only one JVM | Replicas run divergent versions | Versioned rollouts, sync confirmations |
| Retrying events and blindly recomputing new routes | Side effects execute on two branches | Pin routes or enforce idempotency per logical action |
| Using default channel to swallow all errors | Hides handler bugs and drops messages | Separate unknown routes from downstream errors |
| Using `ignoreSendFailures` instead of recovery | Mandatory branches may silently fail | Error flows, retries, durable messaging, and monitoring |
| Exposing Control Bus to unauthenticated requests | Unauthorized runtime configuration changes | Separate admin path, RBAC, and auditing |
| Skipping tests when increasing recipient count | Backlogs, thread pools, and targets overload | Load tests, canarying, and capacity planning |

## 21. Hands-On Exercise: Budgeted Dynamic Router

Design an intake flow for:

~~~java
record InvoiceIssued(
        String eventId,
        String tenantId,
        String countryCode,
        java.math.BigDecimal totalVnd,
        String customerTier) {}
~~~

Allowed destinations:

| Route key | Channel | Meaning |
| --- | --- | --- |
| STANDARD | `invoiceStandardChannel` | Standard invoice processing |
| REVIEW | `invoiceReviewChannel` | Inspect invoices needing review |
| HOLD | `invoiceHoldChannel` | Hold for reconciliation |
| QUARANTINE | `invoiceQuarantineChannel` | Non-conforming data/rules |

**Technical Requirements**

1. Runtime policy can change the review threshold and the list of `countryCode` values requiring HOLD.
2. Every policy is an immutable versioned snapshot, validated prior to activation.
3. No more than 20 rules and never routes outside the allowed channel table.
4. No more than two recipients if an event must also copy to audit per requirements.
5. No more than 8 routing hops in one attempt.
6. Policies and graphs must never create a cycle without explicit termination controls.
7. Route decisions carry `policyVersion` and the chosen `routeKey`.
8. Replaying the same `eventId` must use the old route decision or follow an explicitly defined recomputation rule.
9. Fallback exists for unknown keys, yet send failures to a chosen channel are not treated as unknown keys.
10. Include tests for concurrent policy updates, rejected candidates, and rollbacks.

**Exercise Steps**

1. Write `InvoiceRoutingPolicySnapshot` with `reviewThreshold`, country codes, and version; validate schema and sizes in the constructor.
2. Write `InvoiceRouterPolicy` using `AtomicReference` and an I/O-free `decide()` method.
3. Use `IntegrationFlow` Java DSL with explicit `channelMapping` entries and `channelKeyFallback(false)`.
4. Build an adapter updating candidates through an internal service, never directly from a user-facing API.
5. Write `SafeMappingUpdater` with an allowlist and max entry count.
6. Build a graph validator; write a test catching cycles returning to input.
7. Write `RouteHopGuard` and test stopping after the 8th hop.
8. Send 200 requests into the router while activating a new policy; verify `(routeKey, version)` pairs stay valid.
9. Add an audit recipient and simulate a send failure; design separate retry/idempotency for audit.
10. Produce a rollout checklist covering canary, metrics, policy version skew, and rollback.

### Extension Problem: Multi-Tenant Dynamic Routing

Suppose every tenant wants its own review policy. Never spin up a new `IntegrationFlow` per **request**. Manage a **finite set of policies** by tenant group or a versioned policy registry.

Analyze:

- Which tenants are permitted custom policies?
- How many rules is each tenant allowed?
- When tenant count grows 1,000x, how do memory and policy-load times scale?
- How long must old policies be kept for replay?
- Can a Tenant A admin add a channel belonging to Tenant B?
- If a policy version breaks, across which instances must it roll back?

### Self-Check Questions

1. How does a Dynamic Router differ from a router with a fixed expression whose output varies per message?
2. In what order do the three stages—compute key, map key, and resolve channel—occur?
3. Why is a small rule count not enough to prove routing will be fast?
4. With F=3 and H=4, how many processing sites can a complete fan-out tree reach?
5. When are both graph validation and a hop guard needed?
6. Can `setDynamicChannelLimit` be used to prevent excessive fan-out?
7. Is updating two keys via two `setChannelMapping` calls atomic?
8. When should `setChannelMappings` or `replaceChannelMappings` be used?
9. Why is `AtomicReference` alone insufficient to guarantee instances run the same `policyVersion`?
10. How can replaying after a mapping change cause duplicate side effects?
11. Does `defaultOutputChannel` automatically catch exceptions from downstream handlers?
12. When should canarying use a stable `eventId` instead of drawing randomly on every attempt?

## 22. Pre-Production Checklist for Dynamic Router

- Every rule and destination is described by a **versioned schema**.
- **Budgets** exist for **rule count, predicate cost, `maxFanout`, `maxHops`, and queue capacity**.
- New rules are validated before activation, never edited directly on live configs.
- Routing keys derive from verified/normalized inputs, never arbitrary bean names.
- **`channelKeyFallback(false)`** and allowlists are enforced for untrusted sources.
- Mappings swap **as one unit** whenever multiple keys depend on each other.
- With runtime `RecipientListRouter`, candidate recipient sets are checked for duplicates and fan-out.
- Graph validation catches cycles or requires termination controls for valid loops.
- Runtime guards run at every routing boundary requiring hop counting.
- Policy snapshots are immutable and route decisions include `policyVersion`.
- Replay policy is explicit: pin old routes or recompute transparently.
- Idempotency is keyed by logical action whenever routes may differ across attempts.
- Error handling separates unknown routes, missing channels, and downstream failures.
- Control Bus/JMX/admin APIs are secured, audited, and support rollbacks.
- Multi-instance deployments monitor version skew and canary rollouts.
- Metrics/tracing measure decision latency, fan-out, hops, queue depth, retries, and errors.
- Unit, integration, concurrency, cycle, load, and restart tests match durability requirements.

**Conclusion:** Bounding Dynamic Router complexity does not mean freezing every route forever. The goal is **allowing policies to change within verifiable bounds**. Combining a **finite channel set**, **atomic snapshots**, **rule/fan-out/hop budgets**, **topology validation**, **Control Bus security**, **version tracking**, and **replay testing** lets Spring Integration retain runtime flexibility without sacrificing predictability or operability.

## References

- [Spring Integration Reference — Dynamic Routers](https://docs.spring.io/spring-integration/reference/router/dynamic-routers.html): three-step destination resolution, updating mappings, Control Bus/JMX management, and whole-table swaps.
- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): `HeaderValueRouter`, `RecipientListRouter`, and Java/Java DSL configuration.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): `setChannelMappings`, `replaceChannelMappings`, `channelKeyFallback`, and `setDynamicChannelLimit`.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): `defaultOutputChannel`, `resolutionRequired`, `ignoreSendFailures`, and `sendTimeout`.
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): runtime component management and governance safeguards.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, routers, Transformers, and processing branches.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): sync/async channels, queues, executors, and related semantics.
- [Enterprise Integration Patterns — Dynamic Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DynamicRouter.html): foundational Dynamic Router pattern design.
