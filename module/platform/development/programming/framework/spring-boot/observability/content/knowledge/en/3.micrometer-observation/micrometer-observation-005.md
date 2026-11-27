# ObservationDocumentation in Micrometer Observation

When a Spring Boot application has only a few business operations, developers can name each measurement ad hoc. As the system grows and multiple teams instrument metrics and distributed tracing, inconsistent names or tags fragment dashboards, leave queries incomplete, and make incident investigation harder.

`ObservationDocumentation` is an interface in the `io.micrometer.observation.docs` package. It lets you describe **an Observation type as a contract** consisting of its name, default convention, low/high-cardinality keys, and documentation metadata. The typical implementation is an `enum`, where the enum constants themselves are called when creating Observations. This is a key design element of an observability setup using **Micrometer Observation, metrics, logs, and tracing** in Spring Boot.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the role of `ObservationDocumentation` in the Micrometer ecosystem.
2. Distinguish between `Observation`, `Observation.Context`, `ObservationConvention`, `ObservationRegistry`, and `ObservationHandler`.
3. Declare an `ObservationDocumentation` enum with a default convention and published key sets.
4. Use the enum to instrument business logic in Spring Boot and customize conventions when needed.
5. Manage tags/cardinality and understand the scope of exporters, sampling, and context propagation.
6. Generate documentation for metrics/spans, test the contract, and spot mismatches between docs and actual runtime signals.

## 1. Why Do We Need ObservationDocumentation?

Suppose `order-service` calls `inventory-service` to reserve stock. Three teams might independently create Observations named:

~~~java
Observation.createNotStarted("reserveStock", registry);
Observation.createNotStarted("inventory.reserve", registry);
Observation.createNotStarted("reserve.inventory", registry);
~~~

These are three different name strings even though the business meaning is identical. A dashboard querying `inventory.reserve` will miss data recorded under the other names. Another problem: Team A uses the tag `channel=web`, Team B uses `source=WEB`, and Team C accidentally puts `orderId` into a metric label, causing time series counts to spike.

An Observation contract unifies the following:

| Design question | Responsible component |
| --- | --- |
| Which operation is being measured? | Stable technical name, such as `inventory.reserve` |
| How should the name read in a trace? | Contextual name, e.g., `reserve inventory` |
| Where does per-execution data come from? | `Observation.Context` |
| Which data becomes tags and with what names? | `ObservationConvention` |
| Which keys are published to instrumentation users? | `ObservationDocumentation` |
| At runtime, who creates metrics or spans? | `ObservationHandler` instances registered with `ObservationRegistry` |
| Where do operators check the name/tag contract? | Documentation generated from source via Micrometer Docs Generator |

`ObservationDocumentation` is **not an exporter** and does not record metrics, logs, or spans itself. It declares the contract. Runtime code must still create the Observation, run its lifecycle, and have suitable handlers registered.

### 1.1. Collaborating components

~~~mermaid
flowchart TD
    Doc["ObservationDocumentation enum<br/>Names, keys, default convention"] --> Inst["Instrumentation code"]
    Conv["ObservationConvention<br/>Name and KeyValues from Context"] --> Inst
    Ctx["Observation.Context<br/>Per-execution data"] --> Inst
    Inst --> Obs["Observation"]
    Obs --> Registry["ObservationRegistry + handlers"]
    Registry --> Metrics["Metrics / MeterRegistry"]
    Registry --> Tracing["Tracing / spans"]
    Doc --> Generator["Micrometer Docs Generator"]
    Conv --> Generator
    Generator --> Ascii["AsciiDoc documentation"]
~~~

- **`Observation`** is a concrete execution. It has `start`, `stop`, `Scope`, `Event`, and can record exceptions.
- **`Observation.Context`** holds data relevant to that execution. Not every field in context automatically becomes a tag.
- **`ObservationConvention<T>`** translates a context into a technical name, contextual name, and `KeyValues` at appropriate cardinality levels.
- **`ObservationDocumentation`** publishes metadata: default convention, prefix, and keys. It provides convenience methods to create an Observation with the chosen convention.
- **`ObservationRegistry`** manages convention, predicate, filter, and handler configurations. Handlers watch the lifecycle to record metrics or create spans when configured.

A single Observation can contribute to both **metrics** and **traces**. **Logs** are usually emitted separately via a logging framework; they can correlate with traces via trace ID and span ID carried in context, but the documentation enum does not emit logs on its own.

### 1.2. Technical name vs. contextual name

Technical names like `inventory.reserve` need to remain stable for querying and aggregation. Contextual names like `reserve inventory` help trace readers understand the operation. Backends may transform names according to registry or exporter conventions, so always verify actual exported data.

Never include request-varying data in the name, such as `inventory.reserve.order-123`. Keep the name stable and use tags with bounded value sets for grouping.

## 2. Designing a Contract for Stock Reservation

This lesson uses a Spring Boot `order-service` calling an inventory system as an example. We want to measure the latency of each reservation, observe that call step in a distributed trace, and group by origin channel.

| Element | Sample value | Meaning |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Technical name of the operation |
| Contextual name | `reserve inventory` | Display name in traces |
| Key prefix | `inventory` | Unified namespace |
| Low-cardinality key | `inventory.channel` | `web` or `batch` |
| Low-cardinality key | `inventory.operation` | Value `reserve` |
| High-cardinality key | `inventory.attempt.id` | Internal attempt identifier for correlation |

The `inventory.attempt.id` value is an opaque identifier specific to an operation and contains no personal data, tokens, or order contents. Because it takes many distinct values, it must not be used as a metric label; keep it in traces only when needed for investigation and permitted by data policies.

### 2.1. Context holding data for a single run

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    InventoryReserveContext(String channel, String attemptId) {
        this.channel = channel;
        this.attemptId = attemptId;
    }

    String channel() {
        return channel;
    }

    String attemptId() {
        return attemptId;
    }
}
~~~

`channel` must be normalized **before creating the context** so it only takes two values: `web` and `batch`. Do not use free-form client fields as low-cardinality tags. For inputs from other sources, define an `other` value or expand the allowed list through a reviewed contract change.

## 3. Creating a Default ObservationConvention

`ObservationConvention` determines the **values emitted at runtime**, derived from the context. An interface tailored to the context type lets instrumentation consumers swap conventions without modifying processing logic.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

interface InventoryReserveObservationConvention
        extends ObservationConvention<InventoryReserveContext> {

    @Override
    default boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }
}

final class DefaultInventoryReserveObservationConvention
        implements InventoryReserveObservationConvention {

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
                InventoryReserveObservationDocumentation.LowCardinalityKeyNames
                        .CHANNEL.withValue(context.channel()),
                InventoryReserveObservationDocumentation.LowCardinalityKeyNames
                        .OPERATION.withValue("reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                InventoryReserveObservationDocumentation.HighCardinalityKeyNames
                        .ATTEMPT_ID.withValue(context.attemptId()));
    }
}
~~~

`supportsContext` identifies the context type. `getName` and `getContextualName` define the names. `getLowCardinalityKeyValues` and `getHighCardinalityKeyValues` return the tag values. Here, key names are referenced from the enum we define in the next section to avoid repeating key strings in multiple places.

Changing `getName()` in a running system can break dashboards and alerts. Adding a low-cardinality key can also increase series counts, so it is not a purely internal change.

## 4. Defining the ObservationDocumentation Enum

The standard pattern is `enum implements ObservationDocumentation`. Each enum constant represents one operation type. `KeyName` in `io.micrometer.common.docs` describes each tag name.

~~~java
package com.example.orders.observation;

import io.micrometer.common.docs.KeyName;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.docs.ObservationDocumentation;

/** Telemetry contract for operations against inventory-service. */
public enum InventoryReserveObservationDocumentation implements ObservationDocumentation {

    /** A single stock reservation in the inventory system. */
    RESERVE {
        @Override
        public Class<? extends ObservationConvention<? extends Observation.Context>>
                getDefaultConvention() {
            return DefaultInventoryReserveObservationConvention.class;
        }

        @Override
        public String getContextualName() {
            return "reserve inventory";
        }

        @Override
        public String getPrefix() {
            return "inventory";
        }

        @Override
        public KeyName[] getLowCardinalityKeyNames() {
            return LowCardinalityKeyNames.values();
        }

        @Override
        public KeyName[] getHighCardinalityKeyNames() {
            return HighCardinalityKeyNames.values();
        }
    };

    /** Key names with bounded values, suitable for metrics. */
    public enum LowCardinalityKeyNames implements KeyName {
        /** Call source normalized to web or batch. */
        CHANNEL {
            @Override
            public String asString() {
                return "inventory.channel";
            }
        },
        /** Type of operation being tracked. */
        OPERATION {
            @Override
            public String asString() {
                return "inventory.operation";
            }
        }
    }

    /** Key names with many values, used selectively when tracing is needed. */
    public enum HighCardinalityKeyNames implements KeyName {
        /** Opaque attempt identifier containing no sensitive data. */
        ATTEMPT_ID {
            @Override
            public String asString() {
                return "inventory.attempt.id";
            }
        }
    }
}
~~~

### 4.1. Reading the contract method by method

| Method | Role |
| --- | --- |
| `getDefaultConvention()` | Declares the default convention class, useful for the contract and docs generator tools |
| `getContextualName()` | Contextual name metadata, e.g., `reserve inventory` |
| `getPrefix()` | Required tag prefix, e.g., `inventory` |
| `getLowCardinalityKeyNames()` | List of key names with bounded values |
| `getHighCardinalityKeyNames()` | List of key names that may take very many values |
| `KeyName.asString()` | Returns the actual key name string |

The convention determines the tag **values**; the enum publishes the tag **names and classification**. Both parts must stay consistent. For example, `getPrefix() = "inventory"` pairs with `inventory.channel` and `inventory.operation`; a bare key `channel` would not conform to that prefix rule.

`getDefaultConvention()` returns a `Class` to describe the convention. At runtime, the application still passes a suitable convention **instance** when creating the Observation. The enum does not automatically register that instance into the registry.

### 4.2. The contract does not verify everything at runtime by itself

The enum does not automatically prevent other code from adding undeclared tags; it does not guarantee every key appears on every executed Observation; and it does not guarantee exporters are healthy or high-cardinality keys are data-safe. Those properties must be verified through unit/integration tests and backend checks.

## 5. Instrumenting Business Logic with Enum Constants

In Spring Boot with Actuator/Micrometer, `ObservationRegistry` is managed as a bean and can be injected into services. Here is an example calling stock reservation via the enum's `.observation(...)` helper API:

~~~java
package com.example.orders.observation;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {
    private final ObservationRegistry registry;
    private final InventoryGateway gateway;

    public InventoryReservationService(ObservationRegistry registry,
                                       InventoryGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void reserve(String sku, int quantity, String channel, String attemptId) {
        // channel is already normalized to web or batch.
        InventoryReserveContext context = new InventoryReserveContext(channel, attemptId);

        InventoryReserveObservationDocumentation.RESERVE
                .observation(
                        null, // No custom convention: pick global or default.
                        new DefaultInventoryReserveObservationConvention(),
                        () -> context,
                        registry)
                .observe(() -> gateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

The example is split into snippets to focus explanations; in a real project, place each public type in its own matching Java file and provide an `InventoryGateway` implementation. When `.observe(...)` runs, Micrometer starts the Observation, opens its scope, executes the lambda, records any thrown exception, closes the scope, and stops the Observation. Handlers configured on the registry determine which signals are recorded.

### 5.1. Precedence order when selecting a convention

When creating an Observation with a **custom convention**, **default convention**, **context supplier**, and **registry**, Micrometer selects the convention in this order:

1. Custom convention passed directly, if non-`null`.
2. Global convention registered on the registry that supports the context type.
3. Default convention passed into the call, when neither of the above applies.

A `CustomInventoryReserveObservationConvention` can rename or add a label like `inventory.region` (with a bounded value set) without changing the code calling the gateway. When changing names/tags, update the contract, documentation, queries, and related alerts together.

If you need to add a fixed tag to **every** observation regardless of which convention is selected, consider an appropriate `ObservationFilter`; `ObservationPredicate`, on the other hand, decides whether to create a real Observation or a no-op. Both mechanisms are distinct from declaring metadata in `ObservationDocumentation`.

## 6. Connecting to Metrics, Traces, Logs, and Propagation

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant Doc as ObservationDocumentation
    participant Reg as ObservationRegistry
    participant Metric as Metrics handler
    participant Trace as Tracing handler
    participant Inventory as inventory-service
    Order->>Doc: RESERVE.observation(...)
    Doc->>Reg: Create Observation with context/convention
    Order->>Reg: observe(...)
    Reg->>Metric: onStart / onStop
    Reg->>Trace: onStart / onStop
    Order->>Inventory: HTTP with traceparent when instrumented
    Inventory-->>Order: Reservation result
~~~

- **Metrics:** when a metrics handler and a suitable `MeterRegistry` are present, an Observation can record timings and low-cardinality tags. Exported formatting for Prometheus may transform names—for instance, a timer is represented as series such as `_seconds_count` and `_seconds_sum`.
- **Tracing:** a tracing handler can create spans, combining low- and high-cardinality info as appropriate. Whether spans appear in a backend depends on sampling, exporters, collectors, and tracing bridge configuration.
- **Logs:** the application logger records events separately. MDC can carry trace ID/span ID so logs belonging to the same trace can be found, but the documentation enum does not emit logs itself.
- **Propagation:** when one service calls another, an instrumented HTTP client and W3C Trace Context propagation (typically the `traceparent` header) are required. For `@Async` or executors, matching context propagation mechanisms must be configured. `ObservationDocumentation` does not automatically prevent traces from breaking across those boundaries.

Example Gradle dependencies when the application uses Spring Boot's version-managing BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

These are reference dependencies for Spring Boot lines with compatible Micrometer integration. To view metrics at `/actuator/prometheus`, configure endpoint exposure and appropriate access restrictions. To view traces, configure the exporter, Collector/backend, and sampling; adding libraries alone does not mean data reaches a backend.

## 7. Cardinality: A Good Contract Keeps Costs Under Control

| Tag | Illustrative values | Cardinality | Recommendation |
| --- | --- | --- | --- |
| `inventory.channel` | `web`, `batch` | Low | Suitable for metric aggregation |
| `inventory.operation` | `reserve` | Low | Valid, though possibly redundant if the name is already clear |
| `inventory.outcome` | `success`, `failure` | Low | Can be added, but update the enum and convention |
| `inventory.attempt.id` | One ID per attempt | High | Do not put into metric labels |
| `inventory.order.id` | One ID per order | High | Do not put into metric labels; requires security review |
| Raw `http.url` | `/orders/123456` | High | Use template `/orders/{id}` instead |

If a metric has 3 regions, 2 channels, 4 outcomes, and 100 instances, label combinations can reach **3 × 2 × 4 × 100 = 2,400** for that single metric alone, before adding other labels. This is an example of multiplying value-set sizes, not a default Micrometer limit.

A high-cardinality key is not automatically "internal only": it can be exported in traces, stored in backends, and queried by observability users. Therefore, you must still enforce data classification, access permissions, retention periods, and sensitive-data scrubbing policies.

When adding an `inventory.outcome` key, ensure the value is set right when the outcome is decided, the label set stays consistent across success and failure paths, and the contract documents it. Never attach dynamic tags from request IDs, exception messages, or unnormalized URLs.

## 8. Generating Documentation with Micrometer Docs Generator

**Micrometer Docs Generator** is a standalone tool that scans source code containing `ObservationDocumentation` and conventions to generate AsciiDoc documentation for metrics, spans, and conventions. The tool does not run automatically just because Actuator is on the classpath.

~~~mermaid
flowchart LR
    Doc["ObservationDocumentation enum"] --> Generator["Docs Generator"]
    Conv["Default Convention"] --> Generator
    Generator --> M["_metrics.adoc"]
    Generator --> S["_spans.adoc"]
    Generator --> C["_conventions.adoc (configurable)"]
    M --> Docs["Technical docs / runbooks"]
    S --> Docs
    C --> Docs
~~~

A reference Gradle task (declare `micrometerDocsVersion` in your project's version management):

~~~groovy
configurations {
    observabilityDocs
}

dependencies {
    observabilityDocs "io.micrometer:micrometer-docs-generator:$micrometerDocsVersion"
}

tasks.register('generateObservabilityDocs', JavaExec) {
    mainClass = 'io.micrometer.docs.DocsGeneratorCommand'
    classpath = configurations.observabilityDocs
    // Source root, inclusion pattern, output folder.
    args project.rootDir.absolutePath, '.*',
            layout.buildDirectory.dir('generated-observability-docs').get().asFile.absolutePath
}
~~~

After picking a compatible version, adding required repositories, and configuring the task, you can run:

~~~bash
./gradlew generateObservabilityDocs
~~~

Output typically includes tables of metric/span names and tag sets in files like `_metrics.adoc` and `_spans.adoc`. Depending on version and options, the tool can also generate convention docs. Always inspect the actual generated output: file names, fields, and generator options can vary. Never treat generated docs as proof that an exporter works or that a trace was stored.

Example content we expect readers to find in the documentation (illustrative table, **not verbatim tool output**):

| Metadata | Expected value |
| --- | --- |
| Observation | `RESERVE` |
| Default convention | `DefaultInventoryReserveObservationConvention` |
| Technical name | `inventory.reserve` |
| Low-cardinality keys | `inventory.channel`, `inventory.operation` |
| High-cardinality keys | `inventory.attempt.id` |

JavaDoc comments on the enum and each key constant let the generated documentation explain meaning rather than merely listing names. When changing a contract, regenerate the docs and review the diff as part of code review.

## 9. Testing the Contract and Runtime Signals

The `micrometer-observation-test` library provides `TestObservationRegistry` to verify actual Observation lifecycle, names, and keys. Example JUnit 5 unit test:

~~~java
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryReservationServiceTest {

    @Test
    void recordsReservationWithDocumentedKeys() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        InventoryGateway gateway = (sku, quantity) -> { /* success */ };
        InventoryReservationService service =
                new InventoryReservationService(registry, gateway);

        service.reserve("SKU-DEMO", 2, "web", "attempt-demo-1");

        assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasLowCardinalityKeyValue("inventory.operation", "reserve")
                .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-demo-1")
                .doesNotHaveError();
    }
}
~~~

Place the test in the same package as the package-private types in the example or adjust visibility. You should also add a test for the exception path to verify error recording, and a test ensuring the keys declared in the enum match the keys returned by the convention. Those are much stronger contract tests than simply checking that the enum exists.

| Check level | What to verify |
| --- | --- |
| **Metadata** | Enum declares the right convention, prefix, key lists, and descriptions |
| **Runtime** | Service creates the Observation via the enum; lifecycle, name, and tags are accurate |
| **Metrics** | Backend receives data; no attempt ID appears in metric labels |
| **Traces** | Appropriate span exists, parent/child links are intact, sampling limits are understood |
| **Logs** | Trace ID appears when correlation is enabled; no sensitive data leaked |
| **Exporter** | Collector/backend receives data and pipeline errors are surfaced |
| **Documentation** | Docs Generator produces name/key tables matching the instrumentation |

If a trace is missing, do not immediately conclude the Observation never ran. Tracing can drop spans via sampling, context headers can be lost in an HTTP client, scopes can break across thread switches, or the exporter/collector may fail to deliver spans. Metrics and logs help distinguish among these possibilities.

## 10. Common Mistakes When Using ObservationDocumentation

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Having an enum yet still creating Observations with raw string names | Backend names diverge from docs | Create via enum constants |
| Convention adds undeclared keys | Docs omit actual runtime tags | Sync enum, convention, and tests |
| Putting high-cardinality keys into metrics | Uncontrolled series growth | Use only low-cardinality labels with bounded values |
| Putting IDs/tokens into high-cardinality tags | Data-exposure risk in trace backend | Minimize collection, use opaque IDs and access control |
| Changing `getName()` without updating alerts | Dashboards/alerts lose data | Manage contract changes alongside queries |
| Assuming the enum emits metrics/spans by itself | No runtime signals | Configure registry/handlers/exporters and invoke Observation |
| Confusing contextual name with metric name | Hard to search or compare | Standardize both names and verify actual output |
| Checking only generated documentation | Misses exporter and propagation issues | Verify both runtime and backend |

When renaming a tag or observation already in production, identify all queries, dashboards, SLO alerts, historical data, and old-schema retention periods. Renaming a metric does not break an HTTP API, yet it can blind alerting systems during an incident.

## 11. Hands-on Exercise

**Scenario:** A Spring Boot application has two reservation sources: requests from `POST /orders` and a scheduled job. The operations team wants to compare latency between the two sources, open traces of slow reservations, and use the same contract across code and documentation.

**Tasks:**

1. Write `InventoryReserveObservationDocumentation`, `InventoryReserveContext`, and the default convention following the sample; document each key with JavaDoc.
2. Normalize channel to `web` or `batch`, execute one successful Observation and one Observation that throws an exception.
3. Use `TestObservationRegistry` to verify name, lifecycle, low/high-cardinality tags, and error information.
4. Run Docs Generator if the project has the tool configured; compare generated docs with the convention in code.
5. Check metrics in the backend, open a sample span, and cross-reference the trace ID in logs when tracing integration is active.
6. Suppose someone proposes adding `inventory.order.id` to low-cardinality tags. Analyze how the value count can grow and propose an alternative.
7. Simulate a missing trace; check sampling, propagation, exporter, and collector in sequence before drawing a conclusion.

**Expected deliverable:** a readable contract, tests verifying runtime behavior, name/tag tables in generated docs, and notes explaining the metrics/traces/logs signals observed in the test environment.

## 12. Takeaways

`ObservationDocumentation` is how you keep **the observability contract close to source code**: an operation has a name, a default convention, and a published set of keys. `ObservationConvention` produces runtime values; `ObservationRegistry` and handlers connect the lifecycle to metrics/tracing; Micrometer Docs Generator turns that contract into documentation. Real-world observability quality in a Spring Boot application still depends on cardinality, context propagation, exporters, sampling, and how logs and traces are correlated in practice.

**References:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Micrometer Docs Generator — Overview](https://docs.micrometer.io/micrometer-docs-generator/reference/)
