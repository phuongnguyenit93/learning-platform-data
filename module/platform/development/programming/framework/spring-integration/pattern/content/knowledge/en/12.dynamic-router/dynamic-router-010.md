# Testing Route Configuration Snapshots

## 1. The Problem: Routes Changing While the System Is Processing

In a **Dynamic Router**, the decision of which channel receives a message can change while the application is running. For example, domestic orders initially flow into `orders.vn.primary`, and then operations switches them to `orders.vn.canary` to test a new processing approach without modifying producers. This ability to switch routes is useful, yet raises critical questions:

- Should a message already being processed when configuration changes use **the old or new rule version**?
- Could an update involving multiple mappings expose readers to **half old configuration, half new configuration**?
- How do we prove every supported key still resolves to a valid channel after an update?
- On rollback, how should messages that already went through the new version be handled?
- Is there a way to test a new configuration **before sending live traffic through it**?

A **route configuration snapshot** is a *logical* capture of the entire rule set needed at a point in time: including **version**, **routing key → destination key/channel** mappings, conditions, and required metadata. Ideally, a snapshot is **immutable**; when changing policy, the application builds a new snapshot, validates it, and **publishes the entire new version as one unit**. Each routing decision should reference **one consistent snapshot**, never piecing together multiple separate config reads.

~~~mermaid
flowchart LR
    A[Producer OrderCreated] --> R{Dynamic Router}
    V1["RouteSnapshot v1: VN → primary"] -. active .-> R
    V2["RouteSnapshot v2: VN → canary"] --> P[Validate & publish atomically]
    P -. swap active snapshot .-> R
    R -->|v1| C1[(orders.vn.primary)]
    R -->|v2| C2[(orders.vn.canary)]
    C1 --> H1[Primary Handler]
    C2 --> H2[Canary Handler]
~~~

The diagram illustrates a **decision-time** change. It does not guarantee that all currently running messages immediately switch to v2: a message already dispatched to primary may continue processing there. That is usually the desired behavior to avoid changing itineraries mid-flight.

This lesson belongs to the **Dynamic router** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration, building loosely coupled and extensible flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, and per-branch testing/observability.

**Objective:** understand what a route configuration snapshot is; distinguish immutable snapshots from live partially mutable configs; design route validation and atomic swaps; write unit/integration tests for versioning, rollback, concurrent updates, and message paths; and build operational evidence when routes change.

## 2. What Does "Snapshot" Mean Here?

### 2.1. Not a UI Screenshot

In this lesson, a **configuration snapshot** is an **immutable data value representing the entire routing configuration at a specific version**. It is neither a screenshot nor solely a "golden snapshot" file from a test framework.

Example snapshot at time T1:

~~~yaml
version: route-policy-v1
routes:
  VN: vnPrimary
  INTL: international
~~~

New snapshot prepared at T2:

~~~yaml
version: route-policy-v2
routes:
  VN: vnCanary
  INTL: international
~~~

These two YAML examples are solely for presenting **data**, not configuration files automatically loaded by Spring Integration into a `DynamicRouter`. The Java section below shows how the application reads and uses snapshots.

### 2.2. Distinguishing Three Concepts

| Concept | Content | What to test |
|---|---|---|
| **Route configuration snapshot** | Immutable routing rule table at a specific version. | Keys, values, rules, version, validation, and immutability. |
| **Snapshot/golden test** | An expected fixture saved or written in tests to detect unintended changes. | Compare actual config against expected in a stable, intentional form. |
| **Runtime routing decision** | Destination selection result for **one** message under **one** snapshot. | Message hits the right target; version and key recorded without mixing two versions. |

For example, a test asserting only `VN → vnPrimary` without checking `INTL` **does not prove the snapshot is valid as a whole**. Conversely, a test checking every key in a snapshot still **does not prove the channels exist with running subscribers**; integration tests are required.

### 2.3. What Should Be Inside a Snapshot?

A route snapshot can contain:

| Field | Example | Purpose |
|---|---|---|
| `version` | `route-policy-v2` | Auditing and comparison/rollback. |
| `routes` | `VN → vnCanary` | Mapping rules used for decisions. |
| `effectiveFrom` (if needed) | Timestamp permitted for activation. | Scheduled rollouts and distinguishing staging/active. |
| `policyHash` (if needed) | Digest of canonical contents. | Detecting config skew across nodes. |
| `schemaVersion` (if needed) | `1` | Controlling parsing/validation as schemas evolve. |
| `owner/approval metadata` (if needed) | Approved change ID. | Tracing who activated the rule and why. |

Adding every possible metadata field is not always better. Any field used for **decisions** must have clear semantics; operational fields must not secretly alter policy behavior. In our example, we only use `version` and `routes` to keep focus on testability.

## 3. What Goes Wrong Without Snapshots?

### 3.1. Per-Mapping Updates Expose Intermediate States

Suppose the running config has two keys:

~~~text
Version v1
  VN   -> vnPrimary
  INTL -> international
~~~

Operations wants to switch to:

~~~text
Version v2
  VN   -> vnCanary
  INTL -> internationalV2
~~~

If two entries of a shared `Map` are modified sequentially, a request arriving between the two updates can observe:

~~~text
VN   -> vnCanary
INTL -> international   // entry not yet updated
~~~

This is a **hybrid** state that was never approved or tested. Worse, if updated via `clear()` followed by `putAll()`, a reader could see an **empty** map midway.

### 3.2. Swapping the Map Non-Atomically with Version

A subtle bug:

~~~java
// Not recommended: two independent mutable variables.
currentVersion = "v2";
currentRoutes = newRoutes;
~~~

Between those two assignments, a request might log `version=v2` while routing under `v1`. Adding `volatile` to each variable separately does not make the **pair of values** update as one unit. A snapshot must place **version and mappings inside the same immutable object**, then swap the reference as a single unit.

### 3.3. Snapshot Tests Check Configuration Only, Not Delivery

Even when a snapshot is valid:

~~~text
VN -> vnCanary
~~~

the `orders.vn.canary` channel might not exist, might have no consumer, might be stopped, or might be overloaded. Therefore:

1. **Snapshot unit tests** prove rules and data updates are consistent.
2. **Routing integration tests** prove Spring Integration dispatches to the right channel.
3. **Operational validation** proves the receiving branch is active, has capacity, and has error handling.

These three verification layers complement one another; they must not be conflated.

## 4. Immutable Snapshot Architecture and Atomic Swap

### 4.1. Lifecycle of a Configuration Change

~~~mermaid
flowchart TD
    D[Draft RouteSnapshot v2] --> S[Validate schema / required keys]
    S --> W[Validate destination allowlist]
    W --> T[Unit / integration checks]
    T --> A[Approval / rollout gate]
    A --> CAS{Atomic compare-and-set}
    CAS -->|Success| ACTIVE[Active RouteSnapshot v2]
    CAS -->|Version conflict| REJECT[Reject / reload / reconcile]
    ACTIVE --> R[Decide each message from 1 snapshot]
    R --> OBS[Log version + route decision]
~~~

In a single-JVM application, one implementation uses `AtomicReference<RouteSnapshot>`. Each request **reads the reference once**, holds that snapshot while computing the destination, and produces a result containing both version and route key. When updating, construct a new object and `compareAndSet` against the active version/identity.

### 4.2. Invariants to Maintain

| Invariant | Why it matters |
|---|---|
| Snapshot **cannot be mutated** after publication. | Requests holding v1 cannot have data changed underneath them. |
| `version` and `routes` live in the same object. | Prevents logging a new version while using old mappings. |
| Every required key always has a mapping. | Prevents missing-destination gaps mid-rollout. |
| Every destination belongs to an allowlist. | Prevents resolving arbitrary user-configured channel names. |
| Each decision reads only one snapshot. | Prevents picking a key under v1 and a channel under v2. |
| Updates enforce conflict control. | Two operators cannot silently overwrite each other's changes. |
| Rollback publishes a validated snapshot. | Never revert individual entries non-atomically. |

**Important:** this atomic swap applies only within **one process/JVM**. If the application runs multiple replicas, each node holds its own `AtomicReference`. There is no guarantee that every node switches to v2 in the exact same nanosecond; cluster-level config distribution, versioning, canary rollouts, and drift detection are required.

## 5. Java: Defining Snapshots and Update Policies

The examples below target **Java 17+, Spring Boot 3.x, and Spring Integration 6.x**. The pure Java code in Section 5 is **framework-independent** for easy unit testing; Section 7 wires the policy outcome into Spring Integration Java DSL.

### 5.1. Snapshot, Decision, and Route State

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

record RouteSnapshot(String version, Map<String, String> routes) {
    private static final Set<String> REQUIRED_MARKETS =
            Set.of("VN", "INTL");

    private static final Map<String, Set<String>> ALLOWED =
            Map.of(
                    "VN", Set.of("vnPrimary", "vnCanary"),
                    "INTL", Set.of("international"));

    RouteSnapshot {
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("Version is required");
        }
        Objects.requireNonNull(routes, "routes");

        // Copy before publishing: callers cannot mutate the snapshot.
        routes = Map.copyOf(routes);

        if (!routes.keySet().equals(REQUIRED_MARKETS)) {
            throw new IllegalArgumentException(
                    "Missing or unsupported market keys");
        }
        for (var entry : routes.entrySet()) {
            if (!ALLOWED.get(entry.getKey()).contains(entry.getValue())) {
                throw new IllegalArgumentException(
                        "Destination is not allowlisted: " + entry);
            }
        }
    }
}

record RouteDecision(
        String version,
        String market,
        String channelKey) {}

final class RouteState {
    private final AtomicReference<RouteSnapshot> active;

    RouteState(RouteSnapshot initial) {
        this.active = new AtomicReference<>(
                Objects.requireNonNull(initial, "initial"));
    }

    RouteSnapshot snapshot() {
        return active.get();
    }

    RouteDecision decide(String market) {
        // Linearization point: read exactly one snapshot.
        RouteSnapshot selected = active.get();
        String key = selected.routes().get(market);
        if (key == null) {
            throw new IllegalArgumentException(
                    "Unsupported market: " + market);
        }
        return new RouteDecision(selected.version(), market, key);
    }

    boolean swapIfVersion(
            String expectedVersion, RouteSnapshot next) {
        Objects.requireNonNull(expectedVersion, "expectedVersion");
        Objects.requireNonNull(next, "next");

        RouteSnapshot previous = active.get();
        if (!previous.version().equals(expectedVersion)
                || previous.version().equals(next.version())) {
            return false;
        }
        return active.compareAndSet(previous, next);
    }
}
~~~

### 5.2. Explaining How the Code Protects Snapshots

- `Map.copyOf` builds an immutable map (with immutable `String` keys/values in this example); mutating the source `Map` after creating `RouteSnapshot` does not affect the snapshot.
- `REQUIRED_MARKETS` fixes the two keys `VN` and `INTL` for this **exercise**. Production code must define keys per module contract rather than hardcoding two markets arbitrarily.
- `ALLOWED` prevents routing `VN` into an international branch or an unknown bean. Adding a new channel requires updating policy/allowlist and verifying registration.
- `decide()` binds one local variable `selected` so `version` and `channelKey` always travel together.
- `swapIfVersion()` implements **compare-and-set**: it only publishes `next` if the active snapshot is still the exact object read and its version matches `expectedVersion`.
- If another writer updates between `active.get()` and `compareAndSet(...)`, CAS returns `false`; the caller must reload/reconcile rather than blindly re-sending its stale edit as a forced overwrite.

**Known limitations:** `RouteState` does not implement durable config storage, change authorization, auditing, cross-JVM distribution, cluster-wide rollout checks, or automated rollback. Those belong in operational services; never infer from `AtomicReference` that the app has a distributed config store.

### 5.3. A Controlled Update

~~~java
RouteSnapshot initial = new RouteSnapshot(
        "route-policy-v1",
        Map.of("VN", "vnPrimary", "INTL", "international"));

RouteState state = new RouteState(initial);
RouteDecision before = state.decide("VN");
// before.version() == "route-policy-v1"
// before.channelKey() == "vnPrimary"

RouteSnapshot candidate = new RouteSnapshot(
        "route-policy-v2",
        Map.of("VN", "vnCanary", "INTL", "international"));

boolean published =
        state.swapIfVersion("route-policy-v1", candidate);
// published == true

RouteDecision after = state.decide("VN");
// after.version() == "route-policy-v2"
// after.channelKey() == "vnCanary"
~~~

If a message was already routed to `orders.vn.primary` before the swap, it can keep running there. Snapshots keep **made decisions consistent** without rolling back side effects or moving already-dispatched messages to canary.

## 6. Unit Tests: Immutable, Complete, and Versioned Snapshots

### 6.1. Validating Snapshot Integrity

Every snapshot must pass **data validity** checks before integration tests run. With JUnit 5:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RouteSnapshotValidationTest {

    @Test
    void validSnapshotContainsEveryRequiredRoute() {
        RouteSnapshot snapshot = new RouteSnapshot(
                "v1",
                Map.of("VN", "vnPrimary",
                        "INTL", "international"));

        assertEquals("v1", snapshot.version());
        assertEquals(Map.of(
                "VN", "vnPrimary",
                "INTL", "international"), snapshot.routes());
    }

    @Test
    void missingRequiredMarketIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad",
                        Map.of("VN", "vnPrimary")));
    }

    @Test
    void unexpectedMarketIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international",
                        "UNKNOWN", "vnPrimary")));
    }

    @Test
    void destinationNotOnAllowlistIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("bad", Map.of(
                        "VN", "international",
                        "INTL", "international")));
    }

    @Test
    void blankVersionIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                new RouteSnapshot("   ", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international")));
    }

    @Test
    void laterChangesToInputMapCannotChangeSnapshot() {
        Map<String, String> source = new HashMap<>();
        source.put("VN", "vnPrimary");
        source.put("INTL", "international");
        RouteSnapshot snapshot = new RouteSnapshot("v1", source);

        source.put("VN", "vnCanary");

        assertEquals("vnPrimary", snapshot.routes().get("VN"));
        assertThrows(UnsupportedOperationException.class, () ->
                snapshot.routes().put("VN", "vnCanary"));
    }
}
~~~

**Limitation:** these tests catch bad mappings, missing keys, non-allowlisted targets, and unintended mutations. They do not know whether `orders.vn.primary` and `orders.vn.canary` beans exist, have subscribers, or have downstream permissions; that belongs to integration tests and runtime checks.

### 6.2. Testing One Decision Uses One Version

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteStateVersionTest {

    private static RouteSnapshot v1() {
        return new RouteSnapshot("v1", Map.of(
                "VN", "vnPrimary",
                "INTL", "international"));
    }

    private static RouteSnapshot v2() {
        return new RouteSnapshot("v2", Map.of(
                "VN", "vnCanary",
                "INTL", "international"));
    }

    @Test
    void aPublishedUpdateChangesNewDecisionsNotOldOnes() {
        RouteState state = new RouteState(v1());
        RouteDecision oldDecision = state.decide("VN");

        assertTrue(state.swapIfVersion("v1", v2()));
        RouteDecision newDecision = state.decide("VN");

        assertEquals(new RouteDecision("v1", "VN", "vnPrimary"),
                oldDecision);
        assertEquals(new RouteDecision("v2", "VN", "vnCanary"),
                newDecision);
    }

    @Test
    void staleWriterCannotOverwritePublishedSnapshot() {
        RouteState state = new RouteState(v1());
        assertTrue(state.swapIfVersion("v1", v2()));

        RouteSnapshot staleChange = new RouteSnapshot(
                "v3-stale", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international"));

        assertFalse(state.swapIfVersion("v1", staleChange));
        assertEquals("v2", state.snapshot().version());
        assertEquals("vnCanary", state.decide("VN").channelKey());
    }

    @Test
    void aSecondPublishWithSameVersionIsRejected() {
        RouteState state = new RouteState(v1());

        assertFalse(state.swapIfVersion("v1", v1()));
        assertEquals("v1", state.snapshot().version());
    }
}
~~~

**Point to remember:** after `swapIfVersion` succeeds, a request holding `oldDecision` retains v1's decision, while subsequent requests may use v2. That is the goal of snapshot consistency.

Do not infer from single-JVM tests that **two servers** running v1/v2 simultaneously will auto-synchronize. Multi-node setups need separate coordination mechanisms.

### 6.3. How Does a "Golden Snapshot Test" Detect Drift?

A snapshot test can compare a canonicalized configuration against a reviewed **expected fixture**:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

final class SnapshotFormat {
    static String canonical(RouteSnapshot snapshot) {
        String lines = snapshot.routes().entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(e -> e.getKey() + "=" + e.getValue())
                .collect(Collectors.joining("\n"));

        return snapshot.version() + "\n" + lines;
    }
}
~~~

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RouteGoldenSnapshotTest {
    @Test
    void activePolicyMatchesReviewedSnapshot() {
        RouteSnapshot snapshot = new RouteSnapshot("v1", Map.of(
                "VN", "vnPrimary",
                "INTL", "international"));

        String expected = "v1\n"
                + "INTL=international\n"
                + "VN=vnPrimary";

        assertEquals(expected, SnapshotFormat.canonical(snapshot));
    }
}
~~~

Calling `sorted(Map.Entry.comparingByKey())` is essential: **iteration order of `Map.of`/`Map.copyOf` is not a guaranteed sort order**. Serializing directly in map iteration order can cause golden tests to flake due to output ordering rather than rule changes.

**How to review an intentional change:** before updating the expected fixture for v2, inspect the exact diff such as `VN=vnPrimary` → `VN=vnCanary`, verify the rollout rationale, allowlist compliance, and safety preconditions. Never blindly "update snapshot" whenever a test fails—that can approve a broken configuration without anyone reviewing it.

### 6.4. Snapshot Tests Should Compare *Meaning*, Not Noisy Data

If configs carry fields such as `generatedAt`, `lastPolledAt`, or ephemeral tokens, byte-for-byte comparison of the whole object creates brittle tests. Normalize and snapshot only fields **carrying routing semantics**:

- `version` and the approved rule set.
- Rule order **only if order actually affects decisions**; do not reorder meaningful priority predicates.
- Destination keys, default/fallback policies, and branch-selection conditions.
- Bounds such as max routes, timeouts, or feature flags if they alter behavior.

Conversely, an **unordered** key→value map can be sorted by key to build a stable fixture. That is the difference between a **useful snapshot test** and an arbitrary dump.

## 7. Integrating Snapshots with Spring Integration Dynamic Router

### 7.1. Dynamic Policy, Static Channel Registry

Spring Integration offers various ways to build dynamic routing and update mappings at runtime depending on the router type and framework API. In this example, we choose a **simple and testable** approach: valid channels are registered **statically** when the application context starts, while **the policy selecting routing keys** is updated through `RouteState`.

~~~mermaid
flowchart LR
    I[(orders.input)] --> R{Router + RouteState}
    S["AtomicReference<RouteSnapshot>"] -. versioned policy .-> R
    R -->|vnPrimary| A[(orders.vn.primary)]
    R -->|vnCanary| B[(orders.vn.canary)]
    R -->|international| C[(orders.international)]
    A --> HA[Primary Handler]
    B --> HB[Canary Handler]
    C --> HC[International Handler]
~~~

**Intentional boundary:** this lesson does not create or destroy endpoint beans when swapping snapshots. To add a **new channel**, deploy/register the channel and consumer appropriately before letting any snapshot reference it. Atomically swapping a `Map` does not create technical destinations on its own.

### 7.2. Complete Java DSL Configuration

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record OrderEvent(String eventId, String market) {}

final class RouteProbe {
    final AtomicInteger primary = new AtomicInteger();
    final AtomicInteger canary = new AtomicInteger();
    final AtomicInteger international = new AtomicInteger();
}

@Configuration
@EnableIntegration
class DynamicOrderRoutingConfiguration {

    @Bean
    RouteState routeState() {
        return new RouteState(new RouteSnapshot(
                "v1",
                Map.of("VN", "vnPrimary",
                        "INTL", "international")));
    }

    @Bean
    RouteProbe routeProbe() {
        return new RouteProbe();
    }

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn.primary")
    MessageChannel primary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn.canary")
    MessageChannel canary() {
        return new DirectChannel();
    }

    @Bean(name = "orders.international")
    MessageChannel international() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow routeOrders(RouteState state) {
        return IntegrationFlow.from("orders.input")
                .route(OrderEvent.class, event -> {
                    RouteDecision decision =
                            state.decide(event.market());
                    // Structured logging/metrics point:
                    // eventId, decision.version(),
                    // decision.market(), decision.channelKey().
                    return decision.channelKey();
                }, routes -> routes
                        .channelMapping("vnPrimary", "orders.vn.primary")
                        .channelMapping("vnCanary", "orders.vn.canary")
                        .channelMapping("international",
                                "orders.international"))
                .get();
    }

    @Bean
    IntegrationFlow primaryFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.vn.primary")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.primary.incrementAndGet();
                    return null; // One-way event handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow canaryFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.vn.canary")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.canary.incrementAndGet();
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow internationalFlow(RouteProbe probe) {
        return IntegrationFlow.from("orders.international")
                .handle(OrderEvent.class, (event, headers) -> {
                    probe.international.incrementAndGet();
                    return null;
                })
                .get();
    }
}
~~~

**Explanation:**

1. `routeOrders` is wired **once** in the context, yet each message calls `state.decide(...)`, so the effective route can change after publishing a new snapshot.
2. Routing keys `vnPrimary`/`vnCanary`/`international` are explicitly mapped to channel beans; arbitrary strings from payloads are never used as bean names.
3. `decide` reads **one snapshot**, producing `RouteDecision` with both version and key. That is the right place to log/emit decision metrics; never call `state.snapshot()` a second time just for logging, as the version could change between reads.
4. Handlers only increment counters so integration tests can observe channel delivery. There are no Gateway replies or real side effects in this example.
5. All channels here are `DirectChannel`. When switching to `ExecutorChannel`/`QueueChannel`, revisit accepted/processed semantics, backpressure, timeouts, and error flows.

**Do not conflate:** this example uses a **dynamic policy on a DSL Router** to teach snapshot consistency. It **does not claim** to use a specific `DynamicRouter` class or Spring Integration's internal runtime mapping update APIs. Whenever mutating a router's mappings directly via management APIs, verify **that API's concurrency semantics** rather than assuming multiple entry updates automatically publish as one atomic snapshot.

### 7.3. A Decision Must Be Logged with the Exact Version Used

Because policy can change right after `decide`, this logging pattern is error-prone:

~~~java
// Anti-pattern: reading the snapshot a second time after routing.
String chosen = state.decide(event.market()).channelKey();
String loggedVersion = state.snapshot().version();
// chosen might come from v1 while loggedVersion is v2.
~~~

Correct approach:

~~~java
RouteDecision decision = state.decide(event.market());
String chosen = decision.channelKey();
String loggedVersion = decision.version();
// Both chosen and loggedVersion belong to the exact same snapshot.
~~~

If downstream endpoints need the version, **pass `RouteDecision` or `policyVersion` as metadata created from the same decision** in one atomic flow step; never enrich a header with one policy read and route in a later step with a separate read. Across broker/adapter boundaries, validate and map this metadata properly.

## 8. Integration Test: A New Snapshot Actually Changes Target Channels

### 8.1. Test Path

For `DynamicOrderRoutingConfiguration` in Section 7, test:

~~~text
Snapshot v1
  OrderEvent(market=VN)
    -> Router -> orders.vn.primary -> primary counter +1

Publish snapshot v2
  OrderEvent(market=VN)
    -> Router -> orders.vn.canary -> canary counter +1

OrderEvent(market=INTL) under both v1/v2
    -> Router -> orders.international
~~~

A unit test proving only that `RouteState.decide("VN")` returns `vnCanary` is not enough. You must prove that **Spring Integration's routing keys and channel mappings** connect to the real consumer.

### 8.2. JUnit 5 + Spring Test

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(DynamicOrderRoutingConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DynamicOrderRoutingIntegrationTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private RouteState routeState;

    @Autowired
    private RouteProbe probe;

    private void publish(String id, String market) {
        assertTrue(input.send(
                MessageBuilder.withPayload(
                        new OrderEvent(id, market)).build(),
                1_000));
    }

    @Test
    void initialSnapshotUsesPrimaryRoute() {
        assertEquals("v1", routeState.snapshot().version());
        assertEquals(Map.of(
                "VN", "vnPrimary",
                "INTL", "international"),
                routeState.snapshot().routes());

        publish("EVT-1", "VN");

        assertEquals(1, probe.primary.get());
        assertEquals(0, probe.canary.get());
        assertEquals(0, probe.international.get());
    }

    @Test
    void changingSnapshotMovesNewEventsToCanary() {
        publish("EVT-OLD", "VN");

        RouteSnapshot next = new RouteSnapshot("v2", Map.of(
                "VN", "vnCanary",
                "INTL", "international"));
        assertTrue(routeState.swapIfVersion("v1", next));

        publish("EVT-NEW", "VN");
        publish("EVT-INTL", "INTL");

        assertEquals(1, probe.primary.get());
        assertEquals(1, probe.canary.get());
        assertEquals(1, probe.international.get());
        assertEquals("v2", routeState.snapshot().version());
    }
}
~~~

**Test interpretation:**

- `@DirtiesContext` isolates mutable state in `RouteState` and `RouteProbe` across tests, avoiding test-order dependencies.
- The v1 test verifies **both the snapshot and the channel actually receiving messages**, making it stronger than a mapping unit test alone.
- The v2 test proves **the same flow bean** stays running while **new messages** switch destinations after an update.
- Counters only prove the mock handlers received messages via `DirectChannel`; they do not prove external side effects or persistence.

When switching target channels to `ExecutorChannel`, `QueueChannel`, or a broker, immediate counter assertions after `send` no longer hold universally. Use latches/awaits with timeouts and test **accepted**, **processed**, and **committed** states separately.

### 8.3. Testing a "Valid" Snapshot Whose Channel Has No Consumer

In this example, snapshot `VN → vnCanary` is valid because `vnCanary` is in the allowlist. Yet if `orders.vn.canary` has no registered handler, what happens?

1. **Policy layer** still returns a valid key.
2. **Spring Integration router** can still resolve the channel bean name.
3. **Dispatch layer** fails because the channel has no subscriber or the consumer is stopped.
4. **Business result** cannot be considered successful based only on steps 1 and 2.

Therefore, write a separate test with a context missing a consumer or controlling endpoint lifecycle, and verify the error/timeout per channel semantics. With `DirectChannel`, a channel without subscribers **does not automatically buffer messages for later processing**.

### 8.4. Where Should Versions Be Logged for Test Verification?

A helpful structured record:

~~~text
event=ROUTE_DECIDED eventId=EVT-NEW
  routeVersion=v2 market=VN channelKey=vnCanary
  destination=orders.vn.canary

event=BRANCH_ENTERED eventId=EVT-NEW
  subscriber=canaryHandler destination=orders.vn.canary

event=BRANCH_COMPLETED eventId=EVT-NEW
  outcome=SUCCESS
~~~

This is an **illustrative application log schema**, not Spring Integration's default log output. Tests can capture these events in a test logger/collector, while avoiding brittle dependencies on irrelevant log ordering or framework message IDs that change when flows build new messages.

## 9. Testing Concurrent Changes and In-Flight Requests

### 9.1. Two Operators Publishing from v1 Simultaneously

A realistic scenario:

~~~text
Active = v1

Operator A:
  expected=v1, candidate=v2-canary

Operator B:
  expected=v1, candidate=v2-primary

Whoever publishes first wins.
The other must receive a conflict, reload state, and decide again.
~~~

Without a version check, B could silently overwrite A's change without realizing it.

### 9.2. JUnit Test Verifying CAS Accepts Only One Writer

~~~java
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConcurrentRouteUpdateTest {

    @Test
    void twoWritersFromSameVersionCannotBothWin()
            throws Exception {
        RouteState state = new RouteState(new RouteSnapshot(
                "v1", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international")));

        RouteSnapshot candidateA = new RouteSnapshot(
                "v2-canary", Map.of(
                        "VN", "vnCanary",
                        "INTL", "international"));
        RouteSnapshot candidateB = new RouteSnapshot(
                "v2-primary", Map.of(
                        "VN", "vnPrimary",
                        "INTL", "international"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<Boolean> a = pool.submit(() -> {
                ready.countDown();
                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timeout");
                }
                return state.swapIfVersion("v1", candidateA);
            });
            Future<Boolean> b = pool.submit(() -> {
                ready.countDown();
                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Start timeout");
                }
                return state.swapIfVersion("v1", candidateB);
            });

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int successCount = (a.get(10, TimeUnit.SECONDS) ? 1 : 0)
                    + (b.get(10, TimeUnit.SECONDS) ? 1 : 0);
            assertEquals(1, successCount);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

This is not a strict timing test: latches line up both writers closely, while **correctness** rests on CAS and the expected-version check. Even when thread scheduling staggers them, when both writers supply `expected=v1`, **at most one** publish can succeed.

In production, if the config-update API returns a conflict, the administrator must **review the diff against the latest snapshot** rather than auto-retrying by swapping `expectedVersion` and overwriting someone else's policy.

### 9.3. Testing No Mixed Reading of Version and Route Key

A useful multi-threaded test repeatedly computes decisions while another thread publishes v2, then asserts every result matches one of two valid pairs:

~~~text
Allowed decisions:
  (version=v1, channelKey=vnPrimary)
  (version=v2, channelKey=vnCanary)

Forbidden:
  (version=v1, channelKey=vnCanary)
  (version=v2, channelKey=vnPrimary)
~~~

Have reader threads call `state.decide("VN")` in a loop while a writer thread swaps the snapshot once. The test **must not** assert a fixed v1/v2 ratio because scheduling varies; only assert **consistency of each pair**. That tests **single-immutable-reference reading** far better than fragile timing assertions.

### 9.4. Testing In-Flight Events Are Not "Shifted" Mid-Flight

An advanced test using a `CountDownLatch` in the Primary Handler:

1. Set active snapshot v1; send `EVT-OLD` on a separate thread.
2. Primary handler signals `started` and waits on a latch.
3. While `EVT-OLD` is inside the primary handler, publish snapshot v2.
4. Send `EVT-NEW` and verify it enters the Canary Handler.
5. Release the latch so primary completes; verify `EVT-OLD` finishes on primary and is never rerouted to canary.

**Why is a separate thread needed?** `DirectChannel` is synchronous: calling `send(EVT-OLD)` on the main test thread while the handler blocks on a latch would block the test thread from publishing v2. Always release latches in `finally` and use bounded deadlines.

This test verifies **the route decision at dispatch time stays intact for the in-flight message**. It does not prove an entire multi-Router workflow afterward uses v1: if downstream steps **compute routes from live state again**, they could still pick v2. For workflows requiring **cross-step version pinning**, carry the decision/snapshot ID on the message and make later steps honor the chosen version instead of reading "latest" again.

## 10. Rollbacks and Testing Recovery Configurations

### 10.1. Rollback Is Not Reverting Entries One by One

After canary hits errors, never run:

~~~text
routeMap.put("VN", "vnPrimary")
routeMap.put("INTL", "international")
currentVersion = "v1"
~~~

Those operations can expose intermediate states, confuse change history, and hamper auditing. Instead, create a new snapshot from the approved good configuration:

~~~java
RouteSnapshot rollback = new RouteSnapshot(
        "v3-rollback",
        Map.of("VN", "vnPrimary",
                "INTL", "international"));

boolean restored =
        state.swapIfVersion("v2", rollback);
// restored == true if active was still v2.
~~~

The new version `v3-rollback` distinguishes **a fresh activation** from v1's original event. Rollback only changes decisions for **subsequently routed messages**, without undoing side effects canary already caused.

### 10.2. Tests Must Prove Three Phases

| Phase | Active snapshot | Expected `VN` route |
|---|---|---|
| Before rollout | v1 | `vnPrimary` |
| After canary rollout | v2 | `vnCanary` |
| After rollback | v3-rollback | `vnPrimary` |

A rollback test should prove:

- No invalid snapshot can be published.
- Rollback carries `expectedVersion` so it does not overwrite a newer change by another operator.
- New messages return to primary.
- Messages **already dispatched to canary** are not assumed to vanish or auto-revert side effects.
- Metrics and logs record `v3-rollback` rather than disguising it as a v1 run.

### 10.3. Results Already Processed Under v2

If canary sent emails, updated a database, or called an external API, rolling back the route config **does not roll back side effects**. Business recovery needs idempotency, reconciliation, targeted retries at the failure point, or contracted compensation.

Specifically, if a client times out and retries after a rollback, the two attempts may be handled by **two different route versions**. Design stable operation IDs, decide whether retries must stick to the old itinerary or may use the new route, and log the version for diagnostics.

## 11. One Snapshot in a JVM vs. One Snapshot Across a Cluster

### 11.1. Config Skew Across Replicas

Suppose a system has three instances:

~~~text
app-A: route-policy-v2   VN -> vnCanary
app-B: route-policy-v1   VN -> vnPrimary
app-C: route-policy-v2   VN -> vnCanary
~~~

Every process may be **internally consistent**, yet a VN request through the load balancer might hit primary or canary depending on which node handles it. That is a bug if the product demands simultaneous cutover; or it may be an **intentional rollout** if canarying node by node.

**This cannot be solved by an imaginary shared `AtomicReference`.** Each JVM has its own reference. When using a central config store, change-notification bus, or deployment rollout, define:

| Question | Decision needed |
|---|---|
| Who is the source of truth? | Which approved config store/DB/versioned artifact? |
| When do nodes update? | Periodic pull, push events, or reload on deploy? |
| What if a node misses an update event? | Reconcile/poll active config; verify versions rather than assuming single delivery. |
| How are versions ordered? | Prevent late v1 events from overwriting v2; add epoch/sequence if needed. |
| Are concurrent versions permitted? | Gradual/canary rollout or mandatory simultaneous cutover? |
| May skewed nodes serve traffic? | Readiness gates, alerts, or explicit canary policies. |
| What if the config store disconnects? | Continue with last-known-good or fail closed based on criticality? |

If cluster-wide simultaneous updates are not required, logs for each decision should record **nodeId, policyVersion, and channelKey** for traceability. When all nodes must synchronize before accepting traffic, use a deployment/activation protocol rather than publishing a snapshot on a single node.

### 11.2. Checking Hashes and Drift

A helpful operational check:

~~~text
node=A  version=v2  policyHash=sha256:abc...
node=B  version=v1  policyHash=sha256:def...
node=C  version=v2  policyHash=sha256:abc...
~~~

`policyHash` is the **digest of a canonicalized representation** of meaningful route fields. For stable hashing, sort unordered maps, normalize encoding, and exclude transient timestamps. Having the same version with different hashes is a severe anomaly: two nodes may have read **two different contents under the same version label**.

Do not treat a hash as proof of business results. It only detects config drift, not target handler health.

### 11.3. Cluster-Level Tests

An integration/system test plan:

1. Start two nodes with the same v1; confirm both report matching version/hash.
2. Publish v2 through the real config-distribution mechanism.
3. Wait within a valid deadline; verify required nodes apply v2 before sending consistency-sensitive traffic.
4. Send messages through each node; cross-check logged route versions against actual receiving destinations.
5. Simulate a node temporarily losing update connectivity, then reconnecting and reconciling.
6. Deliver a stale update late to verify the node does not silently regress.
7. Test canary behavior if the system **intentionally allows** multiple versions concurrently.

These steps are **not** unit tests of `RouteState`; they test config distribution and behavior across replicas.

## 12. What Other Failures Can Happen with Dynamic Routes?

### 12.1. Valid Snapshot, Yet the Router Still Fails

~~~mermaid
flowchart TD
    A[Incoming message] --> R[Select snapshot + routing key]
    R -->|Invalid key| E1[Validation / routing error]
    R -->|Valid key| M[Map to channel]
    M -->|Missing channel| E2[Resolution error]
    M -->|Channel exists| D[Dispatch]
    D -->|No consumer / queue full| E3[Delivery error]
    D -->|Consumer accepts| H[Handler]
    H -->|Downstream error| E4[Processing error]
    H -->|Completed| OK[Outcome per contract]
~~~

Distinguish **policy failure**, **destination resolution failure**, **delivery failure**, and **processing failure**. They require different dashboards, retries, and recovery:

| Failure source | Does immediately retrying the message help? | Suggested handling |
|---|---|---|
| Invalid market/key | Usually no. | Validation/business rejection; never map arbitrarily to another tenant. |
| Snapshot missing a mapping | Faulty snapshot should never be published. | Catch in preflight, roll back candidate, alert. |
| Missing channel bean | Retrying will not create the bean. | Ensure destinations are deployed/registered before activation. |
| Consumer stopped | Potentially transient. | Readiness/maintenance, buffer per semantics or reject explicitly. |
| Queue/executor overloaded | Possible, with bounded retries. | Backpressure, timeouts, scaling, and capacity. |
| Downstream HTTP timeout | Possible, if business rules support it. | Backoff, idempotency/reconciliation when outcome is uncertain. |
| Handler throws permanent error | Usually no. | Error flow, DLQ/manual repair; avoid retry storms. |

### 12.2. Synchronous vs. Asynchronous Differences

With `DirectChannel`, router/handler exceptions typically propagate back to the sender on the same call stack. With `ExecutorChannel`, polled `QueueChannel`, or broker adapters, exceptions can occur **after upstream acceptance**, routing into `ErrorMessage`/`errorChannel` in configured contexts.

**Never assume** all errors automatically land on one shared error channel. In an async `IntegrationFlow`, inspect error handling for the specific adapter, poller, gateway, and transport. An error reaching an error channel does not automatically guarantee retries or rollback of business side effects.

### 12.3. Never Blindly Re-Route Retries Using "Latest"

Suppose v1 sends `EVT-42` to primary and the primary handler times out; immediately afterward the active snapshot switches to v2 and a retry goes **back to the Router input**. The retry may go to canary, causing **the same business operation** to execute on two paths.

Choose explicitly among these strategies:

- **Sticky route per operation:** preserve `routeDecision.version` and the chosen destination, retrying on the same branch.
- **Re-evaluate latest snapshot:** allow retries to use the new policy, paired with idempotency and route-change auditing.
- **Recovery routing:** send failures to DLQ/quarantine or let operators trigger replay under a chosen version.

No single rule fits all domains. For payments, invoicing, or inventory updates, consistency/idempotency usually outweighs "always picking the newest version."

### 12.4. Dynamic Router Does Not Replace Authorization

If a message carries `market=VN`, verify where that value originated. On public APIs, callers might submit `market=INTL` or a forged `routeKey` header. `RouteSnapshot` only enforces **the allowed key and destination sets**, not whether the client is authorized for that market.

At trust boundaries:

1. Authenticate identity and tenant.
2. Normalize market from validated business data.
3. Compute the routing key via server-side policy.
4. Permit only destinations in an approved registry.
5. Audit configuration changes and critical decisions.

Never expose a route-update API without authentication, authorization, approvals, and auditing. A rule can redirect data to a different channel; it is a **business control surface**, not harmless configuration.

## 13. Deployment Workflow for a New Snapshot

A practical workflow can be broken into six phases:

~~~mermaid
flowchart LR
    A[Prepare] --> B[Validate]
    B --> C[Test]
    C --> D[Approve]
    D --> E[Activate]
    E --> F[Observe / rollback]
~~~

**Prepare:** build `RouteSnapshot v2` with a new version and a diff from v1. Check schema, required keys, destination allowlist, and change metadata.

**Validate:** verify destination beans/channels are registered in the matching release, endpoints meet readiness, reject/fallback paths are defined, and rule combinations have no gaps.

**Test:** run `RouteSnapshotValidationTest`, `RouteStateVersionTest`, golden snapshot tests, and v1→v2 integration tests. For major changes, test canary/staging over real transports.

**Approve:** an authorized approver confirms the diff, rollout scope, version/hash, and rollback plan. Avoid rubber-stamping just because snapshot tests updated expected fixtures.

**Activate:** publish atomically using `expectedVersion`. If CAS/central config update reports a conflict, **reload and re-review** rather than forcing an overwrite.

**Observe:** monitor route decisions, per-branch processing, errors/timeouts/backlogs, and per-node versions; if error thresholds are breached, publish a new rollback snapshot per policy.

### 13.1. Signals Needed Immediately After Activation

| Signal | Question |
|---|---|
| `route_policy_active_version` | Which version is each node running? |
| `route_policy_hash` | Does the same version carry identical contents? |
| `route_update_attempts/conflicts` | Are there config contentions or failed updates? |
| `route_decisions_total{version,key}` | How is real traffic distributed by version and branch? |
| `route_resolution_errors_total` | Are any keys/channels failing to resolve? |
| `branch_received_total{destination}` | Are target handlers actually receiving messages? |
| `branch_completed/failed_total` | What are business outcomes per branch? |
| `queue_depth` / `oldest_message_age` | Is canary backing up or stalling? |

These are **illustrative application-defined metric names**, not built-in Spring Integration meters. Never put `orderId`, `eventId`, or `traceId` in metric labels due to high cardinality; use access-controlled logs/tracing.

### 13.2. Canary Rollouts and Snapshot Tests

A canary rollout may apply a v2 snapshot to a subset of traffic or nodes. Control **stable distribution**: never use an unseeded random function to pick paths and expect tests to stay repeatable.

If routing conditions are percentage-based, snapshots should specify a rule with a deterministic seed/hash, e.g., based on a verified `customerId` or `orderId`. Tests should verify not just aggregate percentages, but also that **the same request ID** consistently gets the same result under a snapshot version. Changing seeds or versions can alter decisions; define explicit retry/replay policies.

**Canary percentages were omitted from `RouteState` in Section 5** because it only illustrates deterministic `VN → primary/canary` mapping. Weighted routing requires adding rules with dedicated semantics and tests.

## 14. Route Configuration Snapshot Test Matrix

| Category | Scenario | What must be proven |
|---|---|---|
| Schema | Missing or blank version | Snapshot rejected before publication. |
| Schema | Missing `INTL` key or extra unknown key | Snapshot rejected. |
| Security | Destination outside allowlist | Snapshot never activated. |
| Immutability | Caller mutates source `Map` | Active snapshot unchanged. |
| Immutability | Caller mutates `snapshot.routes()` | Throws unsupported/cannot mutate. |
| Determinism | Serialize expected with `Map.of` | Canonical snapshot is stable, independent of iteration order. |
| Functional | v1 + VN | Decides `vnPrimary` and primary handler receives message. |
| Functional | v2 + VN | Decides `vnCanary` and canary handler receives message. |
| Regression | v1/v2 + INTL | Continues routing to `orders.international`. |
| Version | Swap snapshot v1→v2 | Old decisions stay v1, new decisions use v2. |
| Version | Two writers from expected v1 | Only one update succeeds; the other gets a conflict. |
| Version | Publish new snapshot reusing old version name | Rejected by update policy; external config store must also enforce uniqueness. |
| In-flight | Event in primary when active changes | That event is not auto-rerouted to canary. |
| Unknown input | Unsupported market | Clear error/rejection; never routes arbitrarily. |
| Channel | Valid mapping but missing bean | Deployment/integration test catches error before rollout. |
| Subscriber | Canary endpoint stopped | Never declares business success just because key resolved. |
| Capacity | Canary queue full | Producer sees overload/timeout/recovery per contract. |
| Retry | v1 fails then v2 activates | Explicit sticky/re-evaluate policy and tested idempotency. |
| Rollback | v2 fails and rolls back to v3 | New messages return to primary; old events remain traceable to v2. |
| Cluster | One replica misses update | Drift detected and handled per rollout policy. |
| Ordering | Stale update event arrives after newer one | Node does not silently regress to older version. |
| Observability | Route decision logs | Version/key/destination come from **one** decision. |

A strong test suite combines **unit**, **integration**, **concurrency**, and **system/cluster tests**. Not every CI job needs heavy multi-node tests, but the release pipeline must carry evidence proportional to the risk of configuration changes.

## 15. Common Pitfalls

| Misconception | Consequence | Correct practice |
|---|---|---|
| "A snapshot is a `Map` we can edit directly." | Readers see hybrid data or missing keys. | Immutable copy and atomic whole-object swap. |
| "Making version and map `volatile` makes updates atomic." | Version and mappings can mismatch. | Bundle both inside `RouteSnapshot`. |
| "Testing only `VN` proves the snapshot works." | Other keys break undetected. | Test all required keys/fallbacks and allowlists. |
| "`Map.of` has a fixed order." | Flaky golden tests. | Canonicalize/sort before comparing. |
| "Passing snapshot tests means routes work end-to-end." | Channels/consumers may be missing or failing. | Integration tests and completed-outcome observability. |
| "Updating policy automatically creates new channels/handlers." | Router points to non-existent destinations. | Deploy/register destinations before activation. |
| "Reading active state again when logging version is accurate." | Logs v2 even though v1 chose the route. | Read `RouteDecision` from a single snapshot lookup. |
| "`AtomicReference` applies across all replicas." | Divergent routes across nodes go undetected. | Versioning/hashing and config distribution/rollout policy. |
| "Retries after an update always use the new route." | One operation runs on two targets with duplicate side effects. | Sticky/re-evaluate policy and idempotency. |
| "Rollback erases all canary effects." | v2 side effects remain. | Separate business remediation and auditing. |
| "Updating expected golden files on failure is enough." | Accidentally approves broken rules. | Review diffs and require explicit sign-off on intentional changes. |
| "Client `market` header suffices to select tenant." | Route spoofing, cross-tenant data leakage. | Authenticate, normalize, and authorize source. |
| "Dynamic Router handles all retry/error-channel failures automatically." | Dropped errors, retry storms. | Classify failure modes and design explicit recovery. |

## 16. Hands-On Exercises

1. **Configure v1:** create `RouteSnapshot` for `VN → vnPrimary` and `INTL → international`; write completeness and immutability tests.
2. **Create v2:** change `VN → vnCanary`, compare canonical snapshot against expected, explain the diff and which channels must exist before activation.
3. **Atomic update:** implement `swapIfVersion`, have two operators simultaneously submit expected `v1`, and verify only one new version wins.
4. **In-flight:** use a latch to pause Primary Handler for a v1 event, publish v2, and send a v2 event; prove the old event is not auto-rerouted.
5. **Invalid mapping:** add `VN → orders.secret` or omit `INTL`; verify the snapshot is rejected at construction time.
6. **No subscriber:** stop the canary endpoint or omit its handler bean in a test context; distinguish snapshot errors, channel resolution errors, and delivery errors.
7. **Async channel:** replace canary with a bounded `QueueChannel` and poller; prove `send` succeeding does not mean the handler completed.
8. **Golden fixture:** build canonical v1; intentionally alter a mapping without updating expected. Review the test failure and accept only approved diffs.
9. **Rollback:** deploy `v3-rollback` back to primary, recording decision versions before and after rollback.
10. **Cluster drift:** simulate two v1/v2 nodes exposing version/hash in health/admin status; define when a node may accept traffic.
11. **Replay:** an operation fails under v1 and retries when v2 is active. Choose and prove either a sticky route or safe policy re-evaluation.
12. **Canary rule:** add a deterministic condition using business ID and canary percentage; test stable output per snapshot version.
13. **Observability:** log `ROUTE_DECIDED` and `BRANCH_COMPLETED` with `eventId`, `policyVersion`, and `destination`; trace a failing event.
14. **Security:** attempt sending a client `routeKey` header requesting a non-allowlisted channel; prove the system never selects arbitrary beans.

### Self-Check Questions

**Question 1:** A reader holds snapshot v1 while a writer publishes v2. Should that reader be allowed to finish using v1? **Yes.** That is the desired behavior of immutable snapshots during an in-progress decision.

**Question 2:** If the logged version is read separately from the routing key, what mismatch can occur? **Version v2 gets logged while v1 actually chose the key**, making audits inaccurate.

**Question 3:** Why is `Map.copyOf` insufficient if version and mappings remain in two separate mutable variables? **Because** updating two variables is non-atomic, allowing readers to see a hybrid state.

**Question 4:** Does a golden snapshot test checking `VN → vnCanary` prove the canary endpoint is running? **No.** Integration/lifecycle/readiness tests are needed.

**Question 5:** Should two writers both expecting v1 be allowed to silently overwrite each other? **No.** Use CAS/version conflicts and re-review the latest version.

**Question 6:** After rolling back from v2 to v3, do events already inside canary automatically return to primary? **No.** Rollback affects new decisions; side effects and in-flight work need separate recovery.

**Question 7:** Does `AtomicReference<RouteSnapshot>` synchronize three Spring Boot replicas? **No.** It only guarantees consistent reads/updates inside one JVM; clusters need dedicated distribution mechanisms.

**Question 8:** When retrying an operation after a route change, should the newest route always be computed by default? **No.** You need a sticky-route or re-evaluation contract, idempotency, and version auditing.

**Question 9:** Should an HTTP client be allowed to pass raw channel name `orders.admin` as a routing key? **No.** Require authentication, allowlists, and separation between business keys and destination beans.

## 17. Conclusion

**Testing route configuration snapshots** is not merely comparing a YAML file against an expected string. It means proving a routing policy is **complete, immutable, versioned, atomically published, and consistently applied per message**. Alongside validation/golden-snapshot unit tests, you need integration tests showing Spring Integration sends to real target channels, concurrency tests for atomic updates, in-flight tests, rollback tests, and drift checks across replicas.

In `SPRING_INTEGRATION_PATTERN`, Dynamic Router lets policies change while keeping flows loosely coupled. To stay safe, separate **routing rules** from the **channel registry**, prevent messages from picking arbitrary beans, record route decisions and versions from **one snapshot read**, handle retries/idempotency/error channels per branch, and monitor actual outcomes rather than just `send=true`. That turns snapshot tests into a reliable guardrail against route changes that directly impact business behavior.
