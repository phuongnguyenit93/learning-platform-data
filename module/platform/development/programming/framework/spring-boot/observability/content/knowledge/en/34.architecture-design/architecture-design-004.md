# Defining Stable Observation Names

In the `SPRING_BOOT_OBSERVABILITY` module, a Spring Boot application uses Micrometer Observation as a single integration point to record activity, then turns that data into metrics, logs, and distributed traces. These signals help teams monitor application behavior, detect errors, and investigate latency in production. For signals to be aggregated and compared across deployments, each observation needs a stable, meaningful name that does not depend on per-request data.

Observation naming is part of observability architecture design. If names change by order ID, actual URL, or username, the same business operation fragments into many separate data groups. Metrics become hard to aggregate, dashboards lose continuity, and pre- and post-release comparisons become unreliable. Conversely, a name that accurately describes the operation type helps metrics and traces tell the same story regardless of instance, version, or environment.

## 1. What Role Does an Observation Name Play?

An observation represents an activity the system wants to measure or observe, such as handling an HTTP request, calling an external service, querying data, or executing a business operation. In Spring Boot, many components are already instrumented out of the box. For custom business flows, the application can create observations using the Micrometer Observation API or the `@Observed` annotation.

`ObservationRegistry` receives observations and dispatches them to registered handlers. Depending on configuration, an observation can be turned into a timer or meter, a span in a tracing system, or information for linking logs with traces. The observation name is the common identifier handlers use to recognize the type of activity.

For example, an inventory reservation operation might be named:

```text
inventory.reservation.create
```

This name describes the kind of work taking place. It does not depend on order ID, product SKU, caller, or the specific outcome of an execution. Therefore, all reservation creations can be aggregated under the same name.

Distinguish between these four components:

| Component | Meaning | Example |
| --- | --- | --- |
| Observation name | Stable identifier for the type of activity | `inventory.reservation.create` |
| Contextual name | Human-readable name providing context for trace viewers | `create inventory reservation` |
| Low-cardinality key-value | Attribute with a bounded value set, suitable for grouping metrics | `inventory.channel=web` |
| High-cardinality key-value | Attribute with many distinct values, useful when investigating a specific trace | `order.id=ORD-84219` |

The observation name answers "what type of activity is this?". The contextual name helps readers understand that activity inside a trace. Key-values describe additional characteristics of a single execution. Do not pack all information into the observation name.

## 2. Rules for Stable Naming

A simple and extensible convention is:

```text
<domain>.<capability>.<operation>
```

Where:

- `domain` is the business domain or component owning the activity, such as `inventory`, `payment`, `checkout`.
- `capability` is the capability or resource being handled, such as `reservation`, `authorization`, `order`.
- `operation` describes the meaningful action, such as `create`, `confirm`, `cancel`, `lookup`.

Not every observation needs all three segments. If a shorter name still expresses the meaning clearly and follows the system's shared convention, you can use `payment.authorization` or `catalog.product.lookup`. What matters is that development teams use the same structure, casing, and level of granularity.

Apply these principles:

1. **Use nouns and verbs describing the business operation.** Name according to what the system performs, not the current class or method name. `payment.authorization` ages better than `PaymentService.authorizeV2`.
2. **Use lowercase letters and dots for hierarchy.** For example, `checkout.order.submit`. Avoid mixing camelCase, underscores, and spaces across names.
3. **Keep names independent of runtime data.** Never concatenate order IDs, customer IDs, IP addresses, full URLs, query strings, or input values into the name.
4. **Preserve the same meaning across deployments.** Renaming a method, package, or class structure should not automatically change the observation name.
5. **Choose the right operation boundary.** Create an observation for an operation meaningful to performance or business logic. There is no need to create observations for every getter, setter, or small helper.
6. **Use consistent names across entry paths.** The same reservation creation operation should share the same name whether invoked from a REST controller, message consumer, or scheduled job.

Names should be specific enough to distinguish operations with different operational characteristics, without splitting so finely that every data variant gets a new name. For example, `payment.authorization` and `payment.refund` are two distinct activities. Meanwhile, `payment.authorization.card` and `payment.authorization.bank` should only be separate names if they truly represent two flows with different lifecycles and measurement goals. If they are simply two payment methods within the same activity, keep one name and put the method in a bounded-value tag.

## 3. Names That Cause Cardinality Explosions

Cardinality is the number of distinct time series or data groups produced by metric names and tags. A constantly changing observation name can cause the metrics system to generate huge numbers of individual series. This increases storage footprint, query costs, and load on the observability backend.

| Avoid | Prefer | Reason |
| --- | --- | --- |
| `order.ORD-84219.submit` | `checkout.order.submit` | Order ID changes with every request |
| `http.server./orders/84219` | `http.server.requests` or a stable business name | Actual URL contains dynamic IDs |
| `payment.authorize.customer-91` | `payment.authorization` | Customer ID is not part of the operation type |
| `inventory.reserve.sku-ABC-001` | `inventory.reservation.create` | SKU can have a huge number of values |
| `db.query.SELECT-...-timestamp` | A structured, stable query observation name | Dynamic SQL or timestamps fragment data |
| `external.call.` plus full host or URL | `partner.api.request` | Host and endpoint should be represented with controlled attributes |

Names containing dynamic data often appear through direct string concatenation:

```java
// Avoid: each orderId can create a different observation name.
String observationName = "order." + orderId + ".submit";
```

Instead, keep the name fixed and classify data using appropriate key-values:

```java
Observation.createNotStarted("checkout.order.submit", observationRegistry)
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> orderService.submit(orderId));
```

In this example, `checkout.order.submit` serves as the stable identifier. `order.id` is an execution attribute declared in the high-cardinality group. Which handler exports this data to which backend depends on configuration; do not assume every high-cardinality key-value is recorded as a metric label.

## 4. Distinguishing Low-Cardinality and High-Cardinality Tags

Once the observation name is chosen, select tags based on how many values can occur and their intended use.

**Low-cardinality** suits attributes with bounded, controlled value sets, such as:

- `payment.method`: `card`, `bank_transfer`, `wallet`.
- `operation.outcome`: `success`, `failure`, `rejected`.
- `inventory.channel`: `web`, `mobile`, `partner`.
- `region`: predefined region codes.

These attributes are useful for grouping and comparing metrics. Before adding a tag, define its valid value set. If values can grow with the number of customers, orders, requests, or sessions, that tag is not low-cardinality.

**High-cardinality** is intended for information with many distinct values, usually helpful when tracing a specific execution:

- `order.id`.
- `request.id`.
- `reservation.id`.

Do not use high-cardinality key-values as a way to bypass data controls. Tracing backends still incur storage and query costs. Record only identifiers genuinely needed for investigation, apply appropriate retention policies, and avoid sensitive data such as access tokens, passwords, emails, phone numbers, or payment details.

Do not place high-cardinality data into low-cardinality tags. For instance, `customer.id` can have millions of values; using it as a metric label creates massive time series counts that are hard to operate. If you need to link to a customer in a trace, evaluate recording that identifier as a high-cardinality attribute according to your system's security policy.

## 5. Creating Observations in Spring Boot

For a business operation, you can create observations directly via `ObservationRegistry`. The example below illustrates stable naming for creating a reservation. The sales channel has a bounded value set so it is recorded as low-cardinality; the order ID is kept as a high-cardinality attribute to aid trace investigation.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final ObservationRegistry observationRegistry;
    private final InventoryRepository inventoryRepository;

    public ReservationService(
            ObservationRegistry observationRegistry,
            InventoryRepository inventoryRepository) {
        this.observationRegistry = observationRegistry;
        this.inventoryRepository = inventoryRepository;
    }

    public Reservation reserve(
            String orderId,
            String sku,
            int quantity,
            SalesChannel channel) {

        return Observation
                .createNotStarted("inventory.reservation.create", observationRegistry)
                .contextualName("create inventory reservation")
                .lowCardinalityKeyValue(
                        "inventory.channel", channel.name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("order.id", orderId)
                .observe(() -> inventoryRepository.reserve(orderId, sku, quantity));
    }
}
```

Here, the observation name does not contain `orderId`, `sku`, or `channel`. The name remains identical for every reservation creation. The contextual name makes traces easier to read. `inventory.channel` supports grouping by a controlled value set; `order.id` helps trace an order when the tracing backend supports this attribute.

The example above uses `String` for the channel to keep the illustration concise. In production code, normalize enum values consistently, such as using `Locale.ROOT` when lowercasing, and ensure the enum does not accept arbitrary user-supplied values.

If using annotations, `@Observed` attaches an observation to a method:

```java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @Observed(
            name = "payment.authorization",
            contextualName = "authorize payment")
    public PaymentResult authorize(PaymentCommand command) {
        // Perform payment verification and authorization.
        return paymentGateway.authorize(command);
    }
}
```

For the annotation to take effect, the application must register `ObservedAspect` with `ObservationRegistry`. A typical configuration is:

```java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry observationRegistry) {
        return new ObservedAspect(observationRegistry);
    }
}
```

The application also needs appropriate AOP configuration so Spring applies the aspect. With proxy-based AOP, internal calls from one method to another on the same instance bypass the proxy; therefore, do not rely on `@Observed` on internal methods to create observations. Place the annotation at bean boundaries invoked through a Spring proxy, or use the Observation API directly when explicit lifecycle control is needed.

Choose one instrumentation approach per boundary. If a method is both wrapped by `@Observed` and manually creates an observation for the same purpose, traces may show two nested spans and metrics may double-count. Nested observations should only be created when each layer genuinely represents a separate activity of investigative value.

## 6. Keeping Names Consistent with Built-in Instrumentation

Spring Boot and Micrometer libraries can automatically create observations for HTTP servers, HTTP clients, data access, and supported components. Leverage built-in instrumentation before adding manual observations. If the framework already measures an HTTP request, there is no need to create a second observation solely to record the same request lifecycle.

Business observations should add a perspective that technical instrumentation cannot express. For example, an HTTP observation shows which endpoint a request hit and how long it took; `checkout.order.submit` shows which business operation the system performed inside that request.

Do not arbitrarily rename default framework observations. Standard names may be relied upon by dashboards, alerts, exporters, or tracing tools. If you need to adjust representation, check the conventions and configuration of your Spring Boot/Micrometer version, and assess the impact on downstream data consumers.

For custom-defined observations, maintain a naming catalog within the development team. The catalog can document the name, meaning, instrumentation location, allowed low-cardinality tags, and owner. This prevents two teams from using two different names for the same operation or reusing the same name for two different operations.

## 7. Verifying Observation Names

After adding an observation, verify both its semantics and the actual emitted data:

1. **Inspect the name in source code.** The name must be constant, accurately describe the operation, and contain no input data. Search for string concatenations to catch dynamically constructed names.
2. **Invoke the operation with varied datasets.** For example, create reservations across different orders, SKUs, and channels. Every invocation of the same operation must retain the same observation name.
3. **Check metrics.** Inspect meter names and tag sets received by the exporter/backend. Ensure all grouping dimensions have bounded value domains and no dynamic IDs appear in metric labels.
4. **Check traces.** Confirm spans have readable names, child spans reflect accurate parent-child relationships, and expected attributes appear in the right places.
5. **Check logs and signal correlation.** When the application logs within an observation's scope, verify trace ID/span ID are linked according to the app's logging and context propagation configuration.
6. **Monitor cardinality after deployment.** Watch time series counts, tag value counts, and ingestion costs. If cardinality spikes abnormally, hunt for tags or names containing dynamic data.

An observation name does not guarantee every backend exports data under the exact same name or structure. Handlers, conventions, registries, and exporters may map observations into meters or spans in their own ways. Therefore, inspect actual emitted output rather than inferring solely from source code names.

For asynchronous flows, also verify context propagation across executors, message brokers, or thread boundaries. An observation name may be correct yet traces still break if context is not propagated. This is separate from naming, yet must be verified so spans belonging to the same operation link together properly.

## 8. Managing Name Changes Over Time

Once an observation name is used in metrics, traces, dashboards, or alerts, treat it as part of your operational data contract. Renaming it can create a new metric series, splitting historical charts and breaking alerts against prior data.

Renaming a method or refactoring packages is not sufficient reason to change an observation name. Keep the name if business semantics and measurement boundaries remain the same. If the operation's meaning changes substantially, a new name may be warranted; in that case, update dashboards, alerts, runbooks, and data migration plans accordingly.

Before promoting a new name to production, review:

- Does the name describe a clear activity and remain stable across releases?
- Does the name contain IDs, URLs, queries, user data, or runtime values?
- Which attributes are low-cardinality, and are their value sets controlled?
- Are high-cardinality attributes genuinely needed for trace investigation and compliant with data policies?
- Does the observation duplicate default instrumentation or an observation at another layer?
- Do existing dashboards, alerts, and queries depend on this name?

A sound naming convention keeps metric cardinality controllable, traces readable, and logs linked to the right operations. With Spring Boot and Micrometer Observation, keep observation names fixed to business semantics, use contextual names for readability, and place variable data in appropriate key-values. Following these principles lets teams track the same operation across application layers and deployments without breaking observability data continuity.
