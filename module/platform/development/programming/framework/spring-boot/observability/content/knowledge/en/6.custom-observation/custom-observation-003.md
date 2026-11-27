# Stable observation names

In a Spring Boot service, two requests performing the same payment operation may belong to different users, carry different order IDs, and execute on different instances. Yet both perform **the exact same kind of work**: authorizing a payment. For Micrometer Observation, they should share **the same observation name**. Differences between two invocations are represented through tags or context, within an appropriate scope and level of detail.

For example:

```text
Request A: checkout.authorize
  channel=web, payment.method=card, order.id=O-123

Request B: checkout.authorize
  channel=mobile, payment.method=wallet, order.id=O-987

Shared observation name: checkout.authorize
Low-cardinality tags: channel, payment.method
High-cardinality trace attribute (if permitted): order.id
```

Conversely, naming them `checkout.authorize.O-123` and `checkout.authorize.O-987` turns each order into a distinct measurement type. Metrics become hard to aggregate, series counts grow, dashboards require constant updates, and pre/post-deployment comparisons lose consistency.

The **Stable observation names** lesson belongs to the **Custom observation** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module's goal is to establish observability for Spring Boot using **Micrometer Observation, metrics, logs, and distributed tracing**, alongside learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and real application behavior. This lesson focuses on one foundational decision: **designing the name of each operation type as a long-term data contract**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why multiple runs of the same operation must share an observation name.
2. Distinguish `Observation name`, `contextualName`, post-exporter metric names, span names, and observation key-values.
3. Design concise, business-meaningful names that remain stable across requests, instances, and application versions.
4. Write a custom observation in Spring Boot with a fixed name and cardinality-controlled tags.
5. Use `ObservationConvention` to centralize naming and metadata rules.
6. Detect drifting or dynamic names through tests, metrics endpoints, or backend queries.
7. Plan safe renames when dashboards, alerts, SLOs, and query systems already depend on the old name.

## 2. What is an observation name and who uses it?

An **Observation** describes an ongoing activity with a lifecycle covering start, scope opening, error/event recording, and stop. `ObservationRegistry` dispatches lifecycle events to matching `ObservationHandler` instances. With proper configuration, one observation can produce a **timer metric** and a **trace span**; an observation itself does not automatically emit every log line.

Three naming concepts must be kept distinct:

| Concept | Example | Primary purpose |
|---|---|---|
| **Observation name** | `checkout.authorize` | Identifies the **operation type**. Meter handlers use it as the canonical timer name before the registry converts it per backend. |
| **Contextual name** | `authorize checkout` | A human-readable name for the activity in a **tracing context**; tracing handlers can use it as the span name. |
| **Key-values / attributes** | `channel=web`, `payment.method=card` | Dimensions to filter or group executions of an operation. They must not cause the operation name to change. |

Thus, this design is sound:

```java
Observation.createNotStarted("checkout.authorize", observationRegistry)
        .contextualName("authorize checkout")
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("payment.method", "card")
        .observe(() -> {
            // Perform one payment authorization.
        });
```

Whereas the following design is flawed:

```java
// Do not do this: a new name for every call.
String name = "checkout.authorize." + orderId;

Observation.createNotStarted(name, observationRegistry)
        .observe(() -> {
            // Process the corresponding order.
        });
```

### 2.1 Names in Java code do not always match backend names

Micrometer recommends canonical **lowercase dot-separated** names, such as `checkout.authorize` or `http.server.requests`. When exported to Prometheus, the registry may normalize dots to underscores and append unit/type suffixes.

```text
In code:                checkout.authorize
Micrometer timer name:  checkout.authorize

Example on Prometheus (depending on registry and config):
  checkout_authorize_seconds_count
  checkout_authorize_seconds_sum
  checkout_authorize_seconds_bucket  (only when appropriate histograms are enabled)

Tracing span name:
  authorize checkout  (if contextualName is set and used by the handler)
```

Do not hard-code Prometheus suffixes by manually appending `_seconds_count` into `Observation.createNotStarted(...)`. That is a **post-exporter transformed name**, not the application-level observation naming contract.

Note: different versions and semantic conventions may alter default metric names or conversion rules. Verify the actual output of `/actuator/metrics` and `/actuator/prometheus` before locking in dashboard queries.

### 2.2 Why not name every operation generically as `operation`?

A name must be **stable yet sufficiently discriminative**. If every business flow used `operation`, dashboards could not tell whether numbers belong to checkout, token validation, or inventory intake without always relying on extra tags. That creates a weak contract and makes querying or access control by operation type difficult.

Good names describe a **meaningful measurement boundary**. For example:

- `checkout.authorize`: from starting payment authorization until a result is returned.
- `inventory.reserve`: duration of a stock reservation attempt.
- `report.generate`: time taken to generate a report.
- `catalog.index.rebuild`: an index rebuild process.
- `invoice.publish`: the work of dispatching an invoice to an external system.

If two code paths measure meaningfully different operations, they should have different names. Do not lump them under one name simply because they live in the same Java class.

## 3. Consequences when names vary with input data

Consider an API:

```text
POST /api/orders/101/checkout
POST /api/orders/102/checkout
POST /api/orders/103/checkout
```

If code uses `"checkout." + orderId`, the count of observation names grows roughly equal to the number of orders. That causes several problems:

1. **Metric explosion**: one timer already spans multiple tag combinations; each dynamic name creates an independent group of meters. Registry memory, storage, and query cost can scale with order count.
2. **Loss of aggregation**: querying `checkout_authorize_seconds_count` returns nothing useful because data is fragmented across countless distinct names.
3. **Brittle dashboards and alerts**: a dashboard filtering on a single name today may show none of tomorrow's requests.
4. **Broken historical comparisons**: when a deployment changes how names are concatenated, data appears to "vanish" even though the app is running.
5. **Hard-to-analyze traces**: if span names also contain IDs, the backend sees too many operation names, making it difficult to group similar traces.
6. **Ineffective telemetry policies**: toggle rules, sampling, retention, or name-based filtering become hard to apply consistently.

Metric series counts typically grow with the combinations of **meter name and labels**. For example, with 3 `channel` values × 4 `payment.method` values × 5 outcomes, one metric can have up to 60 useful label combinations. Adding 100,000 `orderId` values as names or tags can multiply potential series by roughly 100,000x. Exact numbers depend on which label combinations actually co-occur and how the exporter stores them, but cardinality risk is very real.

**Dynamic names are also a form of high cardinality**, even when every tag has a small value set.

## 4. Six principles for designing stable names

### 4.1 Name the kind of work, not an individual execution

Prefer `domain.action` or `subsystem.operation`:

```text
checkout.authorize
inventory.reserve
report.generate
message.consumer.process
```

Avoid entity IDs, UUIDs, user IDs, timestamps, retry attempt numbers, stack traces, or concrete request paths in the name.

### 4.2 Keep a consistent naming convention

Micrometer recommends **lowercase dot notation**. Choose an internal convention upfront, such as:

- Domain/object noun first, verb or action second: `inventory.reserve`.
- Use dots hierarchically; do not arbitrarily mix `checkout-authorize`, `checkoutAuthorize`, and `checkout.authorize`.
- Make names specific enough to understand on a dashboard, yet not so long that they embed full request descriptions.
- Do not include units like `seconds` or `milliseconds` in an `Observation` name that meter handlers will measure with a timer and convert per backend.

This is a **design convention**, not the single mandatory grammar enforced by Micrometer. If a project already follows an official semantic convention, prioritize compatibility with that convention.

### 4.3 Stay stable across environments and deployments

The name `checkout.authorize` should never become:

```text
checkout.authorize.dev
checkout.authorize.prod
checkout.authorize.node-8
checkout.authorize.v42
```

Environment, deployment region, and version should be represented via **resource attributes or controlled common labels** where needed. In Spring Boot you can configure common low-cardinality key-values such as `region=ap-southeast-1` or `stack=prod`. For multi-instance environments, evaluate instance label cardinality and how your backend manages resource identity.

The same kind of call on two instances still shares the same observation name. That enables summing metrics and comparing behavior before and after a rollout.

### 4.4 Same name must preserve the same semantics

Suppose `report.generate` previously measured PDF generation, but new code only measures reading prebuilt data from cache. If you keep the same name, historical latency curves are no longer comparable. **String stability alone is not enough; measurement boundaries and business semantics must remain stable too.**

When scope changes significantly:

- Determine whether it is genuinely a new type of work.
- Choose a new name if semantics differ.
- If it is still the same type of work, keep the name and use a bounded-value dimension to analyze the change, where appropriate.
- Document the impact on dashboards, alerts, and SLOs.

### 4.5 Names must not contain sensitive data

Even when a value never enters metrics, span names still flow into tracing systems where many users can search them. Avoid placing tokens, emails, account numbers, customer names, or private data in both **observation names** and **contextualName**.

### 4.6 Names have owners and documentation

For each important custom observation, the team should maintain a brief contract:

```yaml
# Example contract documentation; not automatic Spring Boot configuration.
observation: checkout.authorize
purpose: "Measures a single payment authorization attempt with the payment provider"
boundary: "From starting the provider call until receiving the final outcome"
contextualName: "authorize checkout"
lowCardinality:
  channel: ["web", "mobile", "partner", "other"]
  payment.method: ["card", "wallet", "bank_transfer", "other"]
owner: "checkout team"
consumers: ["checkout dashboard", "payment latency alert"]
```

The contract should also clarify what counts as an error, duration data types, instrumentation source, and testing responsibilities when changing names. This is descriptive documentation rather than a STEP 4 module metadata file.

## 5. Separating names from varying data

A practical rule of thumb is: **the observation name answers "what work is happening?", tags answer "which category?", and trace attributes help identify "which specific run?"**.

| Information | Where does it go? | Example |
|---|---|---|
| Stable type of work | Observation name | `checkout.authorize` |
| Readable operation name | `contextualName` | `authorize checkout` |
| Payment method from a bounded set | Low-cardinality key-value | `payment.method=card` |
| Normalized access channel | Low-cardinality key-value | `channel=mobile` |
| Outcome from a bounded set | Low-cardinality key-value | `outcome=approved` |
| Near-unique order ID | Consider high-cardinality trace attribute only when allowed | `order.id=O-123` |
| Request/trace ID | Trace context or controlled log correlation | `traceId=...` |
| Pod or deployment instance name | Resource metadata / system labels depending on backend | `service.instance.id=...` |
| Templated HTTP route | Low-cardinality tag of HTTP observation | `uri=/orders/{id}` |
| URL containing concrete IDs | Never use as metric tag/name | `/orders/101` |

Micrometer Observation uses **low-cardinality key-values** for metrics and traces. High-cardinality key-values are better suited to tracing because they are omitted from default meter tags; however, they are **not automatically safe**. You still need to control sensitive data, retention, and backend costs.

To be clear: **high-cardinality attributes are not a workaround for logging sensitive data**. If there is no legitimate investigative need, do not collect specific IDs.

### 5.1 Do not embed labels into the name

Wrong:

```java
String name = "checkout.authorize." + paymentMethod + "." + region;
```

Better:

```java
Observation.createNotStarted("checkout.authorize", registry)
        .lowCardinalityKeyValue("payment.method", methodTag)
        .lowCardinalityKeyValue("region", regionTag)
        .observe(this::authorizePayment);
```

Here `methodTag` and `regionTag` must be normalized to bounded value sets. If `region` accepts arbitrary strings from requests, it can still cause excessive cardinality even after being separated from the name.

## 6. Spring Boot example: using a fixed name in a service

Suppose the system needs to measure payment authorization duration in a business service. Simply inject the `ObservationRegistry` configured by Spring Boot/Actuator. Java 17+ example:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutApplicationService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutApplicationService.class);

    // One constant for one kind of business operation.
    public static final String AUTHORIZE_OBSERVATION = "checkout.authorize";

    private final ObservationRegistry observations;
    private final PaymentGateway gateway;

    public CheckoutApplicationService(ObservationRegistry observations,
                                      PaymentGateway gateway) {
        this.observations = observations;
        this.gateway = gateway;
    }

    public boolean authorize(PaymentChannel channel, PaymentCommand command) {
        // Enum guarantees a bounded tag value set.
        String channelTag = switch (channel) {
            case WEB -> "web";
            case MOBILE -> "mobile";
            case PARTNER -> "partner";
        };

        Observation observation = Observation
                .createNotStarted(AUTHORIZE_OBSERVATION, observations)
                .contextualName("authorize checkout")
                .lowCardinalityKeyValue("channel", channelTag);

        return observation.observe(() -> {
            boolean approved = gateway.authorize(command);
            if (!approved) {
                log.info("Payment authorization declined; channel={}",
                         channelTag);
            }
            return approved;
        });
    }
}

// Business types to be implemented/supplied in a real application.
enum PaymentChannel { WEB, MOBILE, PARTNER }

record PaymentCommand(String orderReference) {}

interface PaymentGateway {
    boolean authorize(PaymentCommand command);
}
```

The example demonstrates how to instrument the service; to run as a Spring Boot app, you need a bean implementing `PaymentGateway` and a caller invoking `authorize(...)`. You do not necessarily need to create a controller just to measure an observation.

Key points:

- The `AUTHORIZE_OBSERVATION` constant **does not depend on** `channel`, `orderReference`, thread, or HTTP request.
- `contextualName("authorize checkout")` provides a clear span name while still excluding specific IDs.
- `channel` has exactly three values enforced by an enum.
- `PaymentCommand.orderReference` is a business fact, **never placed in the observation name** and not even logged in this example.
- `observation.observe(...)` manages start, opening scope, recording thrown exceptions, closing scope, and stopping. If the callback throws an exception, handlers can record errors on metrics/spans as configured.
- A provider declining payment by returning `false` **is not necessarily an exception**. If you need to measure business decline rates, design a bounded `outcome` tag or a dedicated business counter; do not change the name to `checkout.authorize.declined` on declines.

Spring Boot uses Micrometer Observation to connect metrics/traces measurements. Seeing timers on `/actuator/metrics` requires Actuator and the corresponding meter handler; seeing traces requires adding a tracing implementation, exporter, and compatible backend. Having an `ObservationRegistry` alone does not guarantee every signal appears in monitoring systems.

### 6.1 Minimal dependencies to verify metrics

If your project already uses Spring Boot dependency management matching your version and you only want to verify custom metrics:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Between Spring Boot 3.x and 4.x, starter/tracing dependency names may differ. This example only adds Actuator and the Prometheus registry; choose tracing/exporter integrations according to **the version you are using**.

Configuration for a learning environment:

```yaml
spring:
  application:
    name: checkout-service

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
```

Expose only necessary endpoints in trusted environments. In production, protect management endpoints with network restrictions and proper authorization mechanisms.

### 6.2 Observing the output

After calling `authorize(...)` through the application:

```bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/checkout.authorize
curl "http://localhost:8080/actuator/metrics/checkout.authorize?tag=channel:web"
curl http://localhost:8080/actuator/prometheus
```

If the meter handler is active, the name at the `metrics` endpoint is typically `checkout.authorize`. Calls with different channels contribute to **one meter type**, partitioned by the `channel` tag. Verify `COUNT` and `TOTAL_TIME`, and look for the converted series in the Prometheus output.

PromQL examples if the Prometheus registry exports names like `checkout_authorize_seconds_count`:

```promql
# Payment authorizations per second by channel
sum by (channel) (
  rate(checkout_authorize_seconds_count[5m])
)

# Average processing duration (seconds) over a 5-minute window
sum(rate(checkout_authorize_seconds_sum[5m]))
/
sum(rate(checkout_authorize_seconds_count[5m]))
```

Use illustrative query names only after checking the actual exporter output. To compute p95 in Prometheus, enable appropriate histogram buckets and use `histogram_quantile`; having `_sum` and `_count` alone is not enough to derive p95 distributions.

## 7. Using ObservationConvention when multiple places create the observation

A string literal in a small service may suffice. However, if the same business operation is instrumented across multiple classes or shared libraries, names and tags easily drift:

```text
checkout.authorize
checkout.authorization
checkout.authorise
payment.authorize
```

When multiple instrumentation points truly measure the same kind of work, unify them in an **ObservationConvention**. It separates naming/metadata rules from start/stop logic.

Micrometer supports `ObservationConvention<T extends Observation.Context>`. A dedicated context holds metadata about the activity, while the convention declares the canonical name and key-values.

Standalone example (Java 17+):

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.ObservationRegistry;

final class AuthorizationContext extends Observation.Context {
    private final String channel;

    AuthorizationContext(String channel) {
        this.channel = channel;
    }

    String channel() {
        return channel;
    }
}

final class AuthorizationObservationConvention
        implements ObservationConvention<AuthorizationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof AuthorizationContext;
    }

    @Override
    public String getName() {
        return "checkout.authorize";    // Stable metric contract.
    }

    @Override
    public String getContextualName(AuthorizationContext context) {
        return "authorize checkout";   // Readable and stable span name.
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(AuthorizationContext context) {
        return KeyValues.of(
                KeyValue.of("channel", context.channel())
        );
    }
}

final class AuthorizationInstrumenter {
    private static final AuthorizationObservationConvention CONVENTION =
            new AuthorizationObservationConvention();

    private final ObservationRegistry registry;

    AuthorizationInstrumenter(ObservationRegistry registry) {
        this.registry = registry;
    }

    void record(String normalizedChannel, Runnable task) {
        AuthorizationContext context =
                new AuthorizationContext(normalizedChannel);

        Observation.createNotStarted(CONVENTION, () -> context, registry)
                .observe(task);
    }
}
```

`normalizedChannel` must come from a value set normalized before entering the context. In a real project, you can expose the convention and instrumenter as shared components of a business module, or define `ObservationDocumentation` to declare the full contract and generate documentation.

**When do you need a convention?**

- When multiple call sites must use the exact same name and tag set.
- When you want to change labels without editing business logic everywhere.
- When a library/module wants to provide a default convention while allowing applications to customize it.
- When you need to align the contract with operations teams and document it.

**When is it unnecessary yet?** If there is only a single simple observation, a name constant and `createNotStarted(...)` may be clearer. Avoid adding abstraction solely to avoid writing a literal once.

### 7.1 How do global convention, filter, and predicate differ?

| Tool | Responsibility | Relation to stable naming |
|---|---|---|
| `ObservationConvention` | Defines name, contextual name, and key-values for a specific context type. | Good place to govern the naming contract by operation type. |
| `GlobalObservationConvention` | Applies convention to supported contexts in the registry when no higher-priority custom convention is given. | Control `supportsContext` and scope carefully to avoid unintended observation renames. |
| `ObservationFilter` | Can modify `Observation.Context`, such as adding/removing key-values, before `onStop`. | Useful for cross-cutting metadata; not the default choice for structuring all business naming. |
| `ObservationPredicate` | Decides whether an observation is created/recorded or becomes a no-op. | Can filter by name; dynamic names make filtering rules inconsistent. |
| `ObservationDocumentation` | Describes observations, conventions, and key names belonging to a domain. | Helps publish name/tag contracts across services and generate docs. |

These components **do not share the same role**. In particular, `ObservationFilter` can alter the name in the context, yet runs at a different stage from predicates and start callbacks; renaming at stop time should not be treated as a full replacement for a convention designed upfront.

## 8. Distinguishing Observation name from tracing span name

A trace describes multiple operations:

```text
traceId = T
└─ span "POST /checkout" (HTTP server)
   ├─ span "authorize checkout"
   └─ span "reserve inventory"
```

In code, business spans might originate from:

```text
checkout.authorize -> contextualName = "authorize checkout"
inventory.reserve  -> contextualName = "reserve inventory"
```

At the tracing layer, the **span name** is used to group and search operation types. Keeping it short, readable, and stable is just as important, though span names **do not necessarily match** timer metric names. That depends on conventions and tracing handlers.

Do not do this:

```java
observation.contextualName("authorize order " + orderId);
```

An individual span already has a trace ID and span ID. If there is a valid need to correlate a specific order, consider adding a controlled attribute or log correlation context. Putting IDs into span names makes it hard for backends to group by operation and introduces security risks.

### 8.1 Stable names do not automatically guarantee cross-service traces

Even when Order Service and Payment Service both use consistent names, cross-service traces still require **context propagation**. Spring-managed HTTP clients with proper tracing instrumentation propagate trace context via headers. For `@Async`, custom executors, or reactive pipelines, configure the corresponding propagation support.

When propagation breaks, two spans may have great names yet belong to **two different trace IDs**. Conversely, when sampling drops a trace, metrics with the same name may still be recorded. Do not confuse missing traces with an observation failing to run.

## 9. Observation names in Spring Boot auto-instrumentation

Spring Framework already publishes many standard observation names, for example:

| Operation | Common name in Micrometer conventions | What should you do? |
|---|---|---|
| Incoming Spring MVC/WebFlux request | `http.server.requests` | Keep the default convention unless there is a specific integration reason to change it. |
| HTTP clients such as `RestClient` or `WebClient` | `http.client.requests` | Use Spring-managed builders to receive auto-instrumentation where appropriate. |
| `@Scheduled` execution | `tasks.scheduled.execution` | Check your stack/version to confirm instrumentation is enabled. |
| Application-specific business logic | `checkout.authorize`, `inventory.reserve` | Create custom observations with stable names and appropriate tags. |

Framework instrumentation names can change when an application selects **OpenTelemetry semantic conventions** instead of Micrometer conventions. Recent Spring Boot versions support choosing the convention set via configuration; switching convention sets must be treated as a change impacting dashboards and alerts, even without modifying business code.

**Do not name a custom observation `http.server.requests`** to measure a business operation. Two measurements with different semantics will be mixed under one name, making interpretation difficult.

### 9.1 Using `@Observed`: names still require design

Micrometer supports annotations like:

```java
@Observed(name = "checkout.authorize", contextualName = "authorize checkout")
public void authorizeCheckout() {
    // ...
}
```

For the annotation to work with Spring Boot, configure annotation scanning/AOP and supporting dependencies for your version. Spring Boot 4.x includes the `management.observations.annotations.enabled=true` property and appropriate AspectJ integration.

This snippet only illustrates naming; do not assume the annotation is automatically active in every project. Avoid **double-instrumenting** a controller or method already automatically measured by Spring Framework. For small business blocks, the direct `Observation` API can be easier to control.

If you rename the Java method `authorizeCheckout` to `execute`, the fixed `name` on the annotation preserves the contract. Relying purely on inferred class/method names can cause telemetry to shift unexpectedly during a refactor.

## 10. Renaming an observation: treat it as a telemetry interface change

Suppose the team wants to rename `checkout.process` to `checkout.authorize` because the old name was too broad. Even though business logic stays the same, this change can cause:

- New Prometheus series to appear while old series stop receiving data.
- Dashboards querying `checkout_process_seconds_count` to return zero new data points.
- Alerts and SLOs tied to the old name to lose signal or fire falsely.
- Trace operation name queries to stop matching if the contextual name also changed.
- Filter, sampling, or retention rules keyed by observation name to require updates.
- Runbooks, documentation, and tests referencing the old name to become outdated.

To rename safely:

1. **Clarify the reason and semantics**: only rename if the old name is genuinely misleading or the measurement boundary has changed.
2. **Inventory consumers**: dashboards, alerts, recording rules, SLOs, reports, trace queries, saved searches, docs, tests, and filtering configs.
3. **Define the new contract**: new name, key/value set, measurement scope, owner, and effective date.
4. **Update consumers before or alongside rollout**: use transitional queries supporting both old and new names, while **avoiding double counting** if the same execution is measured twice.
5. **Deploy and observe**: verify the new name receives data, the old name tapers off as planned, and alerts still reflect incidents.
6. **Complete the transition**: once all services have migrated and historical retention aligns, remove old queries/alerts.

Example transitional rollout query (illustrative):

```promql
# Only sum both names when each event is recorded by exactly
# one of the two instrumentations, avoiding double-counting requests.
sum(rate(checkout_process_seconds_count[5m]))
+
sum(rate(checkout_authorize_seconds_count[5m]))
```

If a transitional code version creates **two Observations for a single call**, summing them doubles traffic metrics. In practice, prefer **switching the metric source across deployments and updating consumers cleanly** rather than duplicating instrumentation broadly.

### 10.1 Renaming is not always necessary

If you only need to separate `approved` and `declined` results, in most cases you should **add a bounded `outcome` tag** or a dedicated business metric rather than splitting the name into `checkout.authorize.approved` and `checkout.authorize.declined`.

However, if `checkout.process` previously measured the entire checkout flow and now measures only the provider call, the boundary has shifted significantly; a new name may be warranted to preserve historical accuracy.

## 11. Troubleshooting scenario caused by unstable naming

**Scenario:** After a deployment, the "checkout latency" dashboard goes blank even though the application continues processing successfully.

Investigation steps:

1. **Inspect application output**: query `/actuator/metrics` and search for names near `checkout`. If multiple `checkout.authorize.<id>` entries appear instead of a single `checkout.authorize`, the bug lies in instrumentation.
2. **Inspect Prometheus exposition**: search for `checkout_authorize_seconds_*` series. If registry names changed due to exporter or semantic convention updates, check conversion rules.
3. **Compare before/after deployment**: review diffs for observation names, `ObservationConvention`, annotations, and related properties.
4. **Check tags**: even when names match, changing a tag key from `payment.method` to `method` can break existing PromQL queries.
5. **Inspect traces**: if contextual names changed or span names include IDs, the tracing UI may fragment by operation; inspect trace IDs and timestamps to rule out propagation/sampling issues.
6. **Confirm recovery**: monitor live traffic, verifying count/rate, latency, alerts, and error rates after fixing; do not stop just because a dashboard line reappears.

A common misconception is blaming "Prometheus is broken" when an existing query turns empty. Separate **no traffic**, **scrape failure**, **meter not created**, **renamed metric**, and **mismatched label filters** using independent evidence.

## 12. Ensuring stability with tests

For naming, the most valuable tests verify **the observable contract**, not just searching for a literal in source code.

### 12.1 Testing timer output with `SimpleMeterRegistry`

The standalone code below verifies that **the same meter name** is used across two channels. It runs with Micrometer core + observation, requiring no Prometheus or Zipkin backend.

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;

public class ObservationNamingCheck {
    public static void main(String[] args) {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        observations.observationConfig()
                .observationHandler(
                        DefaultMeterObservationHandler.builder(meters).build());

        Observation.createNotStarted("checkout.authorize", observations)
                .lowCardinalityKeyValue("channel", "web")
                .observe(() -> {});

        Observation.createNotStarted("checkout.authorize", observations)
                .lowCardinalityKeyValue("channel", "mobile")
                .observe(() -> {});

        long webCount = meters.get("checkout.authorize")
                .tag("channel", "web")
                .timer()
                .count();

        long mobileCount = meters.get("checkout.authorize")
                .tag("channel", "mobile")
                .timer()
                .count();

        if (webCount != 1 || mobileCount != 1) {
            throw new AssertionError("Unexpected observation counts");
        }

        System.out.println("Stable name verified for both channels");
        meters.close();
    }
}
```

Depending on the Micrometer version, verify the exact package of `DefaultMeterObservationHandler` and builder API against your project's pinned dependencies; the example above uses APIs from current Micrometer Observation. In production code, remove unused imports and convert the verification into a proper unit test.

**What to verify:**

- Both calls use **one canonical name** `checkout.authorize`, with two tag values.
- Neither `checkout.authorize.web` nor `checkout.authorize.mobile` meter exists.
- The timer records data only after the observation stops.
- When tracing is enabled, span names do not vary with IDs or arbitrary inputs.

### 12.2 Application-level checks

With a local Spring Boot app running and traffic generated:

```bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/checkout.authorize
curl http://localhost:8080/actuator/prometheus
```

You can add tests / CI checks:

- Execute the same business operation with varied inputs and assert that the set of **observation names stays fixed**.
- Cross-check observed names/tags against the published contract.
- Enforce upper bounds on distinct values for `low-cardinality` tags.
- Test behavior when switching `ObservationConvention` or semantic conventions.
- Verify no duplicate observations are created at boundaries already covered by auto-instrumentation.

**Avoid testing the wrong thing:** grepping for `"checkout.authorize"` in source code will not catch another call site dynamically building names at runtime. Test what the registry actually receives.

## 13. Common naming pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Every request creates a new metric name | Concatenating request ID/order ID into the name | Use a fixed name; move valid details to trace attributes/logs. |
| One business flow appears under multiple similar names | Teams naming independently | Publish a shared contract; use constants or `ObservationConvention`. |
| Dashboards blank after refactor | Name tied to class/method or convention changed | Check old/new names and update consumers following a migration plan. |
| Traces have thousands of operation names | Using IDs/concrete URLs as `contextualName` | Keep span names fixed; use trace IDs and attributes to look up calls. |
| PromQL query uses wrong name despite data in `/actuator/metrics` | Backend converts dots, units, or suffixes | Inspect exporter output; write queries against actual metric names. |
| Old metric name still appears after partial code change | Other call sites or old worker versions still running | Locate remaining emitters, check rollout progress and ownership. |
| Metric recording counts doubled | Instrumenting the same activity twice | Pick one boundary; inspect auto-instrumentation vs. custom instrumentation. |
| Total traffic distorted after rename | Summing two metrics that measure overlapping events | Switch by deployment version/time window; avoid double counting. |
| Stable name yet cardinality still explodes | `userId`/`orderId` tags or raw URLs | Constrain low-cardinality tags and use route templates. |
| Metrics look fine but traces are disconnected | Missing propagation, tracing/exporter/sampling | Check trace context, scopes, and the tracing pipeline. |
| Same name measures two different durations | Business boundary changed without updating contract | Evaluate renaming/migration and document semantics. |

## 14. Design and code review checklist

Before accepting a new custom observation, answer:

- **Does the name describe the type of operation?** For example, `checkout.authorize` is clearer than `execute`.
- **Does the name vary by request, instance, environment, or user data?** If so, fix it.
- **Does the name follow lowercase dot notation or the chosen convention?**
- **Do two runs of the same kind share the same name?** Are semantically distinct operations wrongly grouped under one name?
- **Does the contextual name for spans contain IDs, raw URLs, or secrets?**
- **Do metric tags have small, normalized value sets?** Should any tag actually be a trace attribute or removed altogether?
- **Are the start/stop boundaries of the observation well-defined?** If boundaries change, will historical metrics remain comparable?
- **Does equivalent auto-instrumentation already exist?** If so, avoid duplicate measurement.
- **Who consumes the name/tags?** Have dashboards, alerts, SLOs, trace queries, and runbooks been listed?
- **Is there a practical verification check?** Do `/actuator/metrics`, Prometheus exporter, or registry tests confirm the expected name?

Applying a naming contract from the beginning allows a service to refactor code, add exporters, enable tracing, or change runtime environments while keeping operational queries consistent.

## 15. Practice exercises

### Exercise 1: Choose the right name

Among three ways of naming a stock reservation, choose the best option:

```text
A. inventory.reserve.8ea4c01b
B. inventory.reserve
C. inventory.reserve.prod.pod-17
```

Explain why the other two approaches create risks. Propose where to store `success/rejected` outcomes and order IDs when lookup is genuinely needed.

### Exercise 2: Refactor broken telemetry

What naming flaws exist in the following snippet?

```java
String observationName = "payment." + customerId + "." + Instant.now();

Observation.createNotStarted(observationName, registry)
        .observe(() -> paymentGateway.authorize(command));
```

Rewrite it with a fixed name, a stable contextual name, and a normalized `payment.method`. Do not place `customerId` into metric tags.

### Exercise 3: Investigate missing dashboard data

After a deploy, `checkout_process_seconds_count` stops increasing, while `/actuator/metrics` shows `checkout.authorize`. Outline steps to identify the cause and plan a migration path for dashboards/alerts to the new name without double counting.

### Exercise 4: Same name, different semantics

Previously `report.generate` measured total report creation time; now that name measures only the data-fetching step. Should you keep the same name or create a new one? Why is preserving the string alone insufficient?

### Exercise 5: Control cardinality

A service has one name `order.submit` with tags `channel` (3 values), `status` (4 values), `country` (10 values), and `orderId` (100,000 values). Estimate the upper bound on combinations and suggest a fix. Should `country` be kept? What data policies and query needs should guide that decision?

**Suggested answers:** Exercise 1: choose B; outcome can be a low-cardinality tag/business counter, and IDs belong in traces/logs only when allowed. Exercise 2: fixed name `payment.authorize`. Exercise 3: verify the rename and update consumers prior to/during rollout. Exercise 4: evaluate a new name because semantics changed. Exercise 5: up to 3 × 4 × 10 × 100,000 = 12,000,000 potential combinations; remove `orderId` from metric tags and evaluate whether the `country` dimension is truly needed.

## 16. Official references

- [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): lowercase dot notation, backend renaming rules, and cardinality safety.
- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): observation lifecycle, names, low/high-cardinality key-values, and `ObservationRegistry`.
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): `ObservationConvention`, `ObservationDocumentation`, handlers, filters, and predicates.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): custom observation examples, common key-values, annotation instrumentation, and context propagation.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metric names and HTTP observation conventions.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): default observation names such as `http.server.requests` and convention customization.
- [Micrometer Tracing — Configuring with Observation](https://docs.micrometer.io/tracing/reference/configuring.html): contextual names, span creation, and low/high cardinality in tracing.
- [Prometheus — Naming](https://prometheus.io/docs/practices/naming/): Prometheus metric naming and unit conventions.

**Remember:** **An observation name identifies a kind of work, not the identity of a single execution.** Design stable and meaningful names, preserve the semantics of measurement boundaries, use low-cardinality tags for bounded groups, use appropriate trace contexts/attributes to investigate individual runs, and treat renaming as a telemetry contract change requiring impact checks across metrics, logs, and traces.
