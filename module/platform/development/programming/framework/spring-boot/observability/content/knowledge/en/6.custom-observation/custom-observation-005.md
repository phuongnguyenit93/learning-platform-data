# Conventions for custom observations in Spring Boot

In the **Custom observation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, we learned that Micrometer Observation lets us measure a business operation through one shared API, which is then translated into **metrics**, **distributed traces**, and related signals when the registry has appropriate handlers. However, when multiple developers independently instrument operations, observation names and key-values easily become inconsistent: one place uses `reserve.stock` while another uses `inventory.reservation`; one records `result=ok` while another records `status=success`. Data is still collected, yet it becomes difficult to compare, aggregate, and investigate.

An **Observation convention** solves this by defining a shared **naming and labeling contract** for an observation type. The convention governs the stable operation name, human-readable trace name, and how context data maps to low- and high-cardinality key-values.

This lesson focuses on designing conventions for **custom observations** in Spring Boot, integrating them with `ObservationRegistry`, understanding their effects on metrics/traces/log correlation, and avoiding common production pitfalls.

## 1. Why do we need a convention when we already have the Observation API?

For a stock reservation operation, direct instrumentation might look like this:

```java
Observation.createNotStarted("inventory.reserve", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("warehouse.tier", "primary")
        .observe(() -> reserveInWarehouse());
```

This style works fine for a small example. When the business logic is invoked from HTTP endpoints, scheduled jobs, and message consumers, if each place invents its own names/tags, you end up with three different telemetry shapes for the exact same behavior.

A convention centralizes shared rules into a reusable class:

| Inconsistent | Shared convention |
| --- | --- |
| `stock.lock`, `reserveInventory`, `inventory.reservation` | `inventory.reserve` |
| `channel=online` in service A, `channel=web` in service B | A single bounded value set like `web/pos/partner` |
| Free-form `warehouseId` tag generating values per warehouse | Tag `warehouse.tier=primary/secondary` |
| Span names containing order IDs, hard to group | Short, stable span names; specific references only in permitted contexts |

Conventions help control **cardinality**, preserve comparability across instances, and reduce the risk of breaking dashboards/alerts during code refactoring.

## 2. Components of a custom observation

Micrometer separates **per-execution data** from **rules for interpreting that data**:

```text
Business code
    |
    +--> Observation.Context
    |      Execution details: channel, warehouse tier, ...
    |
    +--> ObservationConvention<Context>
    |      getName()
    |      getContextualName(context)
    |      getLowCardinalityKeyValues(context)
    |      getHighCardinalityKeyValues(context)
    |      supportsContext(context)
    |
    +--> Observation + ObservationRegistry
              |
              +--> ObservationHandler for metrics (if configured)
              +--> ObservationHandler for tracing (if configured)
              +--> corresponding exporters/backends
```

Specific roles:

| Component | Function |
| --- | --- |
| `Observation.Context` | Holds data for one observation instance and state across the measurement lifecycle |
| `ObservationConvention<T>` | Standardizes the name and key-values for contexts of type `T` |
| `ObservationRegistry` | Manages observation configuration, conventions, predicates, filters, and handlers |
| `ObservationHandler` | Receives observation callbacks; depending on the handler, creates metrics, spans, or custom processing |
| Exporter/scraper | Ships signals to collection systems, e.g., Prometheus for metrics or a tracing backend |

A convention **does not create metrics or spans by itself**. It supplies metadata for handlers to process. Therefore, seeing convention code execute does not guarantee data reached the backend; you must still check the registry, tracing bridge, exporter, sampling, and ingestion pipeline.

### Five key methods

For `ObservationConvention<T extends Observation.Context>`:

- `getName()` returns the **stable observation name** used by frameworks and meter handlers. Never put order IDs, dynamic URLs, or usernames here.
- `getContextualName(T context)` provides a **human-readable name for tracing**, usually concise and action-oriented. Never use sensitive data.
- `getLowCardinalityKeyValues(T context)` returns labels with a **bounded set of values** safe for metrics and trace attributes.
- `getHighCardinalityKeyValues(T context)` is meant for context with many distinct values, primarily useful in traces; actual export depends on handlers and data policies.
- `supportsContext(Observation.Context context)` indicates whether the convention supports the passed context type, which is especially critical when registering conventions globally on the registry.

These API names belong to Micrometer Observation; dependency coordinates, default instrumentation support, and registry setup vary by Spring Boot version.

## 3. Complete example: Convention for stock reservation

Suppose an ordering system has a `reserveInventory()` business step. We want to answer two questions: **is stock reservation latency increasing?** and **how does latency vary by order channel and warehouse tier?**. To keep cardinality controlled, use enums for the analytical tag dimensions.

### Step 1: Define a strongly typed context

```java
import io.micrometer.observation.Observation;
import java.util.Objects;

enum OrderChannel {
    WEB, POS, PARTNER
}

enum WarehouseTier {
    PRIMARY, SECONDARY
}

final class InventoryReserveContext extends Observation.Context {
    private final OrderChannel channel;
    private final WarehouseTier warehouseTier;

    InventoryReserveContext(OrderChannel channel, WarehouseTier warehouseTier) {
        this.channel = Objects.requireNonNull(channel);
        this.warehouseTier = Objects.requireNonNull(warehouseTier);
    }

    OrderChannel channel() {
        return channel;
    }

    WarehouseTier warehouseTier() {
        return warehouseTier;
    }
}
```

`InventoryReserveContext` extends `Observation.Context`, adding only the two properties relevant to measurement. There is no need to place the entire `Order`, request body, tokens, or personal information into the context when the convention does not use them.

### Step 2: Write the convention

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import java.util.Locale;

public class InventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of(
                        "order.channel",
                        context.channel().name().toLowerCase(Locale.ROOT)),
                KeyValue.of(
                        "warehouse.tier",
                        context.warehouseTier().name().toLowerCase(Locale.ROOT))
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            InventoryReserveContext context) {
        // This use case does not need dynamic identifiers in traces.
        return KeyValues.empty();
    }
}
```

Expected output:

| Field | Example | Meaning |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Logical name of the operation, stable across runs |
| Contextual name | `reserve inventory` | Human-readable span name if the tracing handler uses contextual names |
| `order.channel` | `web` | Bounded label to compare channels |
| `warehouse.tier` | `primary` | Bounded label to compare warehouse tiers |
| High-cardinality keys | Empty | Do not emit dynamic IDs when there is no investigative need |

The number of combinations from these two labels is at most **3 × 2 = 6** (excluding common labels like instance, service, exception, or handler-added labels). This is far more predictable than attaching a distinct `orderId` to every observation.

### Step 3: Use the convention in a service

The example below illustrates the Observation API alongside hypothetical domain types `ReserveCommand`, `ReservationResult`, and `StockGateway`. These domain types are application-defined; they are not part of Micrometer.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryReserveConvention convention;
    private final StockGateway gateway;

    public InventoryReservationService(
            ObservationRegistry observationRegistry,
            InventoryReserveConvention convention,
            StockGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.convention = convention;
        this.gateway = gateway;
    }

    public ReservationResult reserve(ReserveCommand command) {
        InventoryReserveContext context = new InventoryReserveContext(
                command.channel(),
                command.warehouseTier());

        Observation observation = Observation.createNotStarted(
                convention,
                () -> context,
                observationRegistry);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            ReservationResult result = gateway.reserve(command);
            observation.lowCardinalityKeyValue(
                    "outcome",
                    result.reserved() ? "reserved" : "out_of_stock");
            return result;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }
}
```

The service builds the context first, passes an explicit convention to the observation, and manages the `start → scope → stop` lifecycle. The scope lets child calls pick up the current observation on **the same execution context**. On the error path, `observation.error(ex)` reports the exception to supporting handlers while still rethrowing to the caller. `finally` ensures the measurement closes.

The `outcome` tag depends on the result, so it is added from business code while the convention holds the two stable structural labels. This combination avoids placing an unknown business result into the context at creation time. **When handlers read tags can vary**, so if you need `outcome` in both metrics and spans, verify the actual behavior of the handlers/versions in use.

To let Spring inject the convention into the service in this example, register it as a bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryObservationConfiguration {
    @Bean
    InventoryReserveConvention inventoryReserveConvention() {
        return new InventoryReserveConvention();
    }
}
```

An alternative for simple operations that do not need a custom outcome is calling `observe(...)` so Observation manages start, scope, error, and stop automatically:

```java
Observation.createNotStarted(
        convention,
        () -> new InventoryReserveContext(channel, warehouseTier),
        observationRegistry)
    .observe(() -> gateway.reserve(command));
```

Choose the manual approach when you need to record exact return outcomes, events, or additional context during the observation lifecycle.

## 4. Local conventions vs. global conventions

A **local convention** (passed directly when creating an Observation) fits code owned by your team: at the observation creation site, readers immediately see which convention governs the operation.

A **global observation convention** is helpful when multiple instrumentation sources create the same context type and you want to enforce a single contract across the whole registry. Micrometer provides `GlobalObservationConvention<T>`, extending the regular convention interface and selected by the registry when `supportsContext(...)` matches. An implementation can reuse the logic of `InventoryReserveConvention`:

```java
import io.micrometer.observation.GlobalObservationConvention;

final class GlobalInventoryReserveConvention
        extends InventoryReserveConvention
        implements GlobalObservationConvention<InventoryReserveContext> {
    // Inherits name, contextual name, key-values, and supportsContext.
}
```

Spring Boot lets you register global conventions via `ObservationRegistryCustomizer`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class GlobalInventoryObservationConfiguration {
    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> inventoryGlobalConvention() {
        return registry -> registry.observationConfig()
                .observationConvention(new GlobalInventoryReserveConvention());
    }
}
```

**Pick one clear strategy** for each observation type: either pass a local convention at creation time or let the registry resolve a global convention when appropriate. There is no need to register both in a minimal setup. To apply a global convention to a custom context, the instrumentation must still construct **the right context subtype** and matching naming/characteristics so the convention gets selected.

When an explicitly passed convention, a global convention, and a default convention coexist, precedence normally favors the explicit rule first, followed by global and default. Exact behavior can depend on implementations and Micrometer/Spring Boot versions; when customizing framework instrumentation, check whether that source uses registry-provided conventions or holds its own custom convention.

Never write a global convention whose `supportsContext(...)` always returns `true` if it is only intended for inventory: it could apply wrong conventions to HTTP, messaging, or other tracing observations.

## 5. How do ObservationConvention, ObservationFilter, ObservationPredicate, and MeterFilter differ?

The following mechanisms operate at different scopes, even though all sit around observability:

| Mechanism | Responsibility | Example |
| --- | --- | --- |
| **`ObservationConvention`** | Determines name, contextual name, and key-values of an observation type | Standardize `inventory.reserve`, `order.channel` |
| **`ObservationFilter`** | Adds/modifies context and key-values in the observation pipeline | Add a common tag when suitable; not meant to define the core contract for every type |
| **`ObservationPredicate`** | Allows or rejects **an entire observation** before it runs | Drop unnecessary heartbeat observations |
| **`MeterFilter`** | Manages meters and tags inside the metric registry | Limit a metric tag or deny unwanted meters |
| **Tracing sampler** | Controls trace recording/export | Sample a subset of requests to reduce volume |

For example: to standardize `order.channel`, design it in a convention; to modify a shared tag across many observations, consider a filter; to completely skip an unneeded observation type, use a predicate; to cut trace volume while keeping metrics, use a sampler. Using a predicate to "fix a label" can wipe out both spans and metrics for the operation you wanted to monitor.

## 6. Naming and controlling cardinality

Conventions are the ideal place to enforce naming and key-value rules:

| Rule | Prefer | Avoid |
| --- | --- | --- |
| Observation name | `inventory.reserve`, `payment.authorize` | `inventory.reserve.ORDER-12345` |
| Contextual name | `reserve inventory`, `authorize payment` | Concatenating usernames, raw URLs, or tokens |
| Low-cardinality values | `outcome=reserved/out_of_stock/error` | `exception.message=<free-form text>` |
| Source type | `order.channel=web/pos/partner` | Arbitrary client-supplied headers |
| Transaction reference | Consider only in controlled traces/logs with proper security policies | Order IDs as metric labels |
| Technical label | `provider=internal/partner_a/partner_b` | Unnormalized hostnames or query strings |

Time series combinations can approach the product of each label's distinct values, multiplied further by dimensions such as instance, route template, and status. Adding a 50,000-value label to a metric that originally had 12 combinations can create up to **600,000 combinations** before counting extra tags. This impacts memory, storage cost, query latency, and dashboard usability.

**Low cardinality** does not mean "few values right now"; it must mean **bounded by design**. For example, `warehouse.tier=primary/secondary` is safer than `warehouse.id=...` when the number of warehouses can grow without bound.

**High cardinality** is not permission to write arbitrary data into traces. Restrict personal info, tokens, session IDs, emails, card numbers, and sensitive content. Handlers/collectors may strip or transform data as configured; do not assume every exporter handles keys identically.

## 7. Conventions and the three signals: metrics, traces, and logs

A well-designed convention helps unify signals without turning them into redundant copies of each other.

### Metrics

When a metric observation handler is active, stable names and low-cardinality tags support aggregating counts, durations, and errors across bounded dimensions. Actual metric names in the backend may be normalized or suffixed by the registry/exporter. Never build dashboard queries on a name that has not been verified against real exported output.

If you want to alert on `p95 inventory.reserve increasing`, verify histograms/percentiles and backend aggregation: merely creating an observation does not automatically give you an accurate cross-instance p95 query.

### Distributed tracing

When tracing bridges, handlers, and exporters are configured, a custom observation can create a business span sitting between the HTTP server span and HTTP client or database spans:

```text
HTTP POST /checkout
    └─ inventory.reserve       (custom observation)
         └─ database/client   (library instrumentation, if present)
```

The contextual name should make traces easy for humans to read, while `getName()` keeps the logical identity for system aggregation. If an HTTP call already has a client observation, avoid creating another observation measuring the exact same boundary unless the custom observation represents **a distinct business step**.

### Logs and signal correlation

A convention **does not configure logging/MDC on its own**. When Spring Boot is configured with tracing and log correlation, logs emitted within an observation's scope can carry `traceId`/`spanId` for matching against spans. For work crossing `@Async`, executors, queues, or other services, you need an appropriate **context propagation** mechanism; opening a scope on one thread does not automatically transfer context to another thread.

Sampling only decides which traces are recorded/exported according to your tracing setup. A missing trace may be caused by sampling, exporter settings, context propagation, or predicates, rather than a bug in the convention. Metrics from the same observation can still exist when a trace is not sampled, since metric handlers operate independently.

## 8. Common pitfalls when creating conventions

**1. Variable names.** Implementing `getName()` as `"inventory.reserve." + orderId` causes metric/span names to grow unboundedly. Names should describe *the kind of work*, not *a single execution*.

**2. Context holding unnecessary data.** Putting an entire request or domain entity into the context just for convenience when extracting tags can drag in sensitive data, tighten coupling, and create risks during logging or trace export. Keep only fields approved for telemetry.

**3. Using high-cardinality keys for metrics.** In standard handlers, high-cardinality key-values typically target traces and are excluded from default metric tags; however, custom handlers can behave differently. Verify the actual export pipeline rather than relying solely on method names for safety.

**4. Overly broad `supportsContext`.** A global convention mistakenly matching HTTP observations can strip standard labels and break framework dashboards.

**5. Confusing business outcomes with exceptions.** `out_of_stock` can be a valid outcome, whereas a database timeout is a technical error. Dumping both into `outcome=error` skews error rates. Separate them right in the tag structure.

**6. Adding labels at the wrong time.** A tag known only after an operation finishes cannot appear in logic running at start time. Test both the metric handler and tracing handler for your active version, especially when consistent `outcome` tags are required.

**7. Changing conventions without checking consumers.** Renaming `outcome` to `result` or `inventory.reserve` to `stock.reserve` can break PromQL queries, alerts, and historical dashboards. Treat names/keys as a telemetry API requiring change management.

## 9. Design and verification workflow

Start from a concrete operational question: "When inventory slows down, can we distinguish web vs. POS channels, primary vs. secondary warehouses, and technical errors vs. out-of-stock declines?" From there, choose the context, convention, and observation boundaries.

A practical team workflow:

1. **Choose the business boundary:** identify operations not already covered by existing signals; avoid overlapping HTTP server/client observations.
2. **Define stable names:** agree on a logical name such as `inventory.reserve` and a readable contextual name.
3. **Design a minimal context:** use enums or normalized values for analytical dimensions. List data that must never be exported.
4. **Write the convention:** define `getName()`, `getContextualName()`, low/high key-values, and `supportsContext()`; choose local or global registration.
5. **Integrate into the service:** create the observation, open scopes cleanly, record outcomes/errors, and always stop the measurement.
6. **Verify along the export pipeline:** metric registry, tracing handler, exporter/scrape, sampling, log correlation, and dashboards.
7. **Review operational impact:** time series count, span volume, latency overhead, and practical investigation capability.

Example verification matrix for `inventory.reserve`:

| Scenario | Metrics | Tracing/logs | Application behavior |
| --- | --- | --- | --- |
| WEB + PRIMARY, reservation succeeds | Tags `order.channel=web`, `warehouse.tier=primary`, `outcome=reserved` when handler supports | Business span sits under parent trace when sampled | Inventory reserved successfully |
| POS + SECONDARY, valid out-of-stock | `outcome=out_of_stock`; not marked as technical error | Trace/log helps locate rejection step | Returns valid business result |
| Gateway throws exception | `outcome=error`; duration still finishes | Observation records exception via supporting handlers | Exception still propagates to caller |
| Invoked from another executor | Metrics still accurately reflect the operation | Parent-child/spanId accurate when propagation is configured | Job still executes |
| Sampler skips the trace | Metrics can still be recorded | Missing span is expected sampling behavior | Business behavior unchanged |
| Adding or updating an order channel | Metric combinations grow within predictable bounds | Convention keeps naming consistent | No impact on domain logic |

During verification, inspect **actual emitted signals**, not just code: a syntactically valid `ObservationConvention` can still yield unexpected output if handlers, naming conventions, registries, or exporters are misconfigured.

## 10. When should you create a dedicated convention?

A dedicated convention is particularly valuable when a **kind of business behavior** appears multiple times or across multiple adapters (HTTP, message consumers, scheduled jobs), when the business needs stable dashboards/SLIs, or when the team wants centralized governance over cardinality and key-value standards.

If you only have one short instrumentation point with one name and a couple of constant labels, attaching them directly to `Observation` can still be enough. As the number of observation emitters grows, conventions prevent semantic fragmentation. They form a **metadata contract**, while overall observability quality still depends on accurate measurement boundaries, configured handlers/exporters, and proper context propagation.

**Key takeaway:** Use `Observation.Context` to hold known facts about a single execution; use `ObservationConvention` to standardize naming and classification; use `ObservationRegistry` and handlers to turn observations into investigable signals. Keep names stable, bound tag cardinality, distinguish business outcomes clearly, and verify metrics–logs–traces correlation in a realistic environment.
