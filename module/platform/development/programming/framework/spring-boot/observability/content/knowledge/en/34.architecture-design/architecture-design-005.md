# Using Tags with Bounded Values

In Spring Boot observability architecture, tags help group invocations and compare application behavior across metrics, logs, and distributed traces. A tag is useful when its values carry stable meaning and come from a small, predictable set. This is the **bounded values** principle: every dimension used to classify telemetry must have a controlled value domain.

This principle is especially critical for metrics. Every combination of a metric name and tag set can create a separate time series. If a tag accepts unbounded values such as `userId`, `requestId`, or URLs containing resource IDs, the number of time series can grow with traffic and live data. As a result, Prometheus or the metrics backend has to store, query, and process huge amounts of data, while dashboards struggle to aggregate it into useful insight.

This lesson belongs to the **Architecture Design** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; this content focuses on designing tags with finite value domains to monitor errors, latency, and application behavior reliably in production.

## Objectives

After this lesson, you will be able to:

- Explain bounded values and the relationship between tag cardinality and time series count.
- Distinguish low-cardinality key values from high-cardinality key values in Micrometer Observation.
- Normalize incoming data into an allowed set of values before placing it in metric tags.
- Select useful classification dimensions while avoiding personal identifiers or per-request varying values in metrics.
- Verify cardinality during development and operations.

## What Are Bounded Values?

A tag is a key-value pair attached to a metric or observation. For example, a metric counting product lookups can be categorized by intake channel and outcome:

```text
catalog.product.lookup{channel="web", outcome="found"}
catalog.product.lookup{channel="mobile", outcome="not_found"}
```

In this example, `channel` might accept only a few values such as `web`, `mobile`, `partner`, `other`; `outcome` might accept only `found`, `not_found`, `error`. Both tags have small, predefined value domains.

A value does not become bounded merely because its string has a maximum length. For instance, a `customerId` that is always 12 characters long can still have millions of distinct values. Bounded values refers to the **number of distinct values that can appear**, not string length.

The value set must also be small enough to be useful. Even a curated list of tens of thousands of city codes can produce excessive cardinality for a metric. Therefore, the value domain must be bounded according to analytical purpose and the system's cardinality budget.

## How Does Cardinality Affect Metrics?

A tag's cardinality is the number of distinct values that tag can take. For a metric with multiple tags, the number of possible combinations grows as the product of each dimension's value count.

For example, a metric with three tags:

| Tag | Expected Value Count |
|---|---:|
| `channel` | 3 |
| `outcome` | 4 |
| `region` | 5 |

If every combination occurs, the metric can generate up to `3 × 4 × 5 = 60` time series per corresponding meter. Adding `customerId` with 100,000 values raises the theoretical combinations to `60 × 100,000 = 6,000,000` time series.

This is why an innocent-looking tag can still cause major problems. Cost comes not only from one tag in isolation, but from the product of all combined tag dimensions. When time series counts spike rapidly, systems may experience:

- Increased memory, storage footprint, and metric ingestion costs.
- Slower queries and dashboards due to scanning large numbers of series.
- Difficulty writing meaningful alerts because each value spawns a separate series.
- Metrics backends rejecting data or enforcing cardinality limits, causing partial blind spots in system visibility.

The numbers above are theoretical combinatorial upper bounds. Actual time series counts depend on which combinations actually occur, metric types, and how exporters represent meters. Even so, multiplication is a helpful estimation rule when designing tags.

## Low-Cardinality vs. High-Cardinality in Micrometer Observation

Micrometer Observation distinguishes two groups of key-values so handlers can process them appropriately for each signal:

| Key-Value Type | Purpose | Example | Usage |
|---|---|---|---|
| Low-cardinality | Classifies observations with a small value set; suitable for creating metric tags | `channel=web`, `outcome=success`, `method=GET` | Use for analytical dimensions requiring aggregation in metrics |
| High-cardinality | Adds detail that may have many distinct values; typically useful in traces | `product.id=PRD-83921`, `request.id=...` | Add only when needed to investigate a specific request and permitted by data policy |

When an Observation is processed by a meter handler, low-cardinality key values become metric tags. High-cardinality key values are excluded from metric tags under Micrometer Observation's default handling; they may be used by tracing handlers as span attributes. Final output depends on configured handlers and exporters.

Do not assume every value placed in high-cardinality is automatically safe. Customer IDs, emails, tokens, IP addresses, or sensitive data still require review under security and privacy policies. High-cardinality merely describes value-count characteristics, not a blanket license to collect arbitrary data.

A practical design rule is: metrics answer **what is happening to a group of requests?**; traces help answer **what happened inside this specific request?**. Use low-cardinality tags for the first question, and add identifying details to traces only when genuinely needed for the second question.

## Designing Value Domains for Tags

### 1. Choose Operationally Meaningful Dimensions

Each tag should help answer a concrete question. For a product lookup operation, the following dimensions are often helpful:

- `channel`: did the request come from `web`, `mobile`, or `partner`?
- `outcome`: did the operation succeed, find nothing, or encounter an error?
- `region`: which deployment region in the configured list handled the request?
- `method`: which HTTP method did the request use?
- `status`: what status code did the response return, or which 2xx/4xx/5xx group?

Avoid adding tags just because data happens to be available. A classification dimension that drives no operational decisions increases combinations without adding observability value.

### 2. Define the Allowed Value Set

Prefer enums, constants, or a normalization function with an explicit allowlist. For example, `channel` accepts only three agreed values. All other values fold into `other`; missing data can be represented as `unknown`.

```java
import java.util.Locale;

static String normalizeChannel(String rawChannel) {
    if (rawChannel == null || rawChannel.isBlank()) {
        return "unknown";
    }

    return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
        case "web" -> "web";
        case "mobile" -> "mobile";
        case "partner" -> "partner";
        default -> "other";
    };
}
```

This normalization function guarantees the `channel` tag only ever has five values: `web`, `mobile`, `partner`, `other`, `unknown`. Even if a client sends a different random string on every request, the metric only sees one of these five values.

Agree on the meaning of `other` and `unknown`. `other` typically means a value was received but falls outside the supported list; `unknown` typically indicates missing or undetermined data. If you merge both cases, ensure doing so does not discard information needed for operations.

### 3. Normalize Paths and Outcomes

For HTTP server metrics, use route templates instead of actual paths. For example:

| Avoid Putting in Tags | Prefer |
|---|---|
| `/orders/982341` | `/orders/{orderId}` |
| `/customers/abc-123/profile` | `/customers/{customerId}/profile` |
| Full URL with query string | Normalized route template |

Actual paths can contain different IDs on every request. Route templates preserve endpoint identity without spawning a series per resource. With Spring Boot Web MVC and WebFlux, keep the default HTTP observation mechanism and ensure the URI tag is the normalized route template; do not replace it with the raw path or query string.

Similarly, map business outcomes to a clear set of values such as `success`, `not_found`, `invalid`, `rejected`, `error`. Never put exception messages, request contents, or external service response prose directly into tags.

### 4. Keep Keys Stable

Tag names should be a fixed set of keys sharing the same meaning across all requests. Do not create dynamic keys like `customer_123_status` or `error_<message>`. Dynamic keys expand dimensionality and make dashboards hard to query consistently.

Do not use variant key names for the same concept, such as `client`, `source`, and `channel` in different places without clear definitions. Standardize vocabulary across the service so metrics remain comparable across versions.

## Attaching Bounded Tags with Micrometer Observation in Spring Boot

Spring Boot integrates Micrometer Observation to provide a single point for recording operations. When an application has Actuator and matching meter/tracing handlers configured, Observations can be turned into metrics and traces. Spring Boot provides an `ObservationRegistry` for applications to use; inject this registry into services rather than creating a separate registry.

The following example records a product lookup operation. Assume the application already defines domain types `Product` and `ProductRepository`. `channel` is normalized before becoming a low-cardinality key value. `outcome` also takes only three values defined in code.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ProductRepository productRepository;
    private final ObservationRegistry observationRegistry;

    public CatalogService(
            ProductRepository productRepository,
            ObservationRegistry observationRegistry) {
        this.productRepository = productRepository;
        this.observationRegistry = observationRegistry;
    }

    public Optional<Product> findProduct(String productId, String channel) {
        Observation observation = Observation
                .createNotStarted("catalog.product.lookup", observationRegistry)
                .lowCardinalityKeyValue("channel", normalizeChannel(channel));

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            Optional<Product> result = productRepository.findById(productId);
            observation.lowCardinalityKeyValue(
                    "outcome", result.isPresent() ? "found" : "not_found");
            return result;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    static String normalizeChannel(String rawChannel) {
        if (rawChannel == null || rawChannel.isBlank()) {
            return "unknown";
        }

        return switch (rawChannel.trim().toLowerCase(Locale.ROOT)) {
            case "web" -> "web";
            case "mobile" -> "mobile";
            case "partner" -> "partner";
            default -> "other";
        };
    }
}
```

In this example:

- The observation name `catalog.product.lookup` is stable and describes the operation.
- `channel` is constrained to five values.
- `outcome` can only be `found`, `not_found`, or `error`.
- `productId` is used to query the repository but does not become a metric tag.
- `observation.error(exception)` records the exception on the observation; the exception message is not put into a low-cardinality tag.
- `observation.stop()` is always called to finish the observation, even if the operation throws an exception.

If the tracing backend needs the product identifier to investigate a specific span, consider adding a high-cardinality key value before starting the observation:

```java
observation.highCardinalityKeyValue("product.id", productId);
```

Only add this attribute when there is a clear investigative need, the tracing backend supports it, and data policy permits exporting it. Do not switch `product.id` to low-cardinality merely for convenient dashboard filtering. If you need statistics by product group, map products to a small category set, such as `category=electronics` or `category=home`.

## Values Usually Unsuitable as Metric Tags

| Input Value | Why Unsuitable | How to Handle |
|---|---|---|
| `userId`, `customerId`, `orderId` | Large, constantly changing ID volume | Use in traces when needed and permitted; metrics should only use normalized customer tiers or transaction types |
| `requestId`, `traceId`, `spanId` | Almost every request gets a unique value | Use tracing and logging correlation mechanisms |
| Email, phone number, token | High cardinality and potentially sensitive data | Keep out of metric tags; mask or omit per data policy |
| Raw URL, query string | May contain IDs, search terms, or arbitrary parameters | Use route templates and normalized dimensions |
| Exception message | Content varies by input and may expose sensitive info | Use controlled outcomes or error groups; keep stack traces in logs/traces per policy |
| Pod or container instance name | Changes during scaling or redeployments | Use only where infrastructure analysis is needed; prefer stable dimensions like service, environment, or region |
| Timestamp or random value | Every recording can generate a new value | Use telemetry system timestamps; never turn timestamps into tags |

Not every high-cardinality dimension must be stripped from every signal. An ID may be essential to follow a trace or connect logs with traces. What to avoid is turning that ID into a metric classification dimension. Choose the key-value type based on the consuming signal and investigative purpose.

## Controlling Cardinality in Design and Operations

### Set a Budget per Metric

Before adding a tag, document:

1. The metric or observation name receiving the tag.
2. The tag's meaning and allowed value set.
3. Expected maximum distinct values for each tag.
4. Potential combinations when multiplied with existing tags.
5. The operational question the tag helps answer.

If you cannot bound the value set or explain which decision the tag supports, revisit the design before adding the tag to metrics.

### Test Normalization Functions

Normalization functions are the guardrail protecting cardinality, so test both valid values and anomalous inputs:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ChannelNormalizerTest {
    @Test
    void mapsSupportedChannelsToCanonicalValues() {
        assertEquals("web", CatalogService.normalizeChannel("WEB"));
        assertEquals("mobile", CatalogService.normalizeChannel("mobile"));
        assertEquals("partner", CatalogService.normalizeChannel(" partner "));
    }

    @Test
    void mapsMissingAndUnsupportedChannelsToBoundedValues() {
        assertEquals("unknown", CatalogService.normalizeChannel(null));
        assertEquals("unknown", CatalogService.normalizeChannel("  "));
        assertEquals("other", CatalogService.normalizeChannel("affiliate-9382"));
    }
}
```

In this example, the normalization method is package-private so tests in the same package can verify it directly. The test illustrates the contract to preserve: every input maps to a value in the allowlist. In a real project, this logic can be extracted into a dedicated utility or component, or tested through the service's public behavior.

### Observe Actual Series Counts

After deployment, inspect metrics on your endpoint or active metrics backend. With Prometheus, you can list series by metric name and group by label to spot tags with abnormally many values. Compare series counts against your planned budget, especially after adding a new tag or traffic growth.

Verify under these scenarios:

- Send multiple requests with varying IDs and confirm series counts do not grow with ID counts.
- Send unsupported channel values and confirm they all fold into `other`.
- Inspect routes with dynamic IDs to ensure metrics use route templates.
- Compare series counts before and after adding a new tag.
- Check dashboards and alerts to confirm the new tag provides useful filtering.

A healthy sign is that as request counts rise or resource IDs vary, the number of metric series stays stable. Recording counts grow with requests; series counts should not grow per request.

## Common Design Mistakes

### Limiting Only String Length

Truncating `customerId` to 20 characters does not solve cardinality. You must bound the value set—for instance, switching to `customer_tier=standard|premium|enterprise` if the operational question is segment comparison.

### Using an Object's `toString()` as a Tag

`toString()` may include IDs, names, input data, or per-object details. Extract a normalized classification attribute with a clearly bounded value domain instead.

### Using Raw Paths Instead of Route Templates

`/orders/1001` and `/orders/1002` are two different strings even though they hit the same endpoint. Use `/orders/{orderId}` to group them into one stable dimension.

### Assuming High-Cardinality Is Always Safe

High-cardinality key values can aid trace analysis yet still bloat trace storage or leak sensitive data. Carefully govern attributes, retention periods, and access controls under system policy.

### Adding Too Many Low-Cardinality Tags

Each tag individually may look small, yet their product can still be large. For example, 8 channels × 12 regions × 10 outcomes × 6 methods yields up to 5,760 combinations. Calculate total combinations before introducing a new dimension.

### Folding Everything Into One Value Unintentionally

Folding all unknown inputs into `other` curbs cardinality but can mask integration errors or a new client. If you need to monitor out-of-allowlist traffic, use a separate summary metric with a bounded tag like `source=unknown` or controlled logging; never put raw unknown values into metric tags.

## Pre-Production Tag Checklist

- [ ] The tag serves a concrete analytical or operational purpose.
- [ ] Key name is static, never dynamically generated.
- [ ] Value domain is small, explicitly defined, and testable.
- [ ] Out-of-allowlist inputs normalize to `other` or `unknown`.
- [ ] No IDs, emails, tokens, raw URLs, exception messages, or timestamps are used as metric tags.
- [ ] Combinations of the new tag with existing tags have been calculated.
- [ ] Data needed to trace specific requests is evaluated as high-cardinality trace attributes under data policy.
- [ ] Dashboards, alerts, and metrics backends have been verified after deployment.

## Conclusion

Bounded values keep metrics predictable in time series count and straightforward to aggregate. In Spring Boot, use Micrometer Observation's low-cardinality key values for stable classification dimensions, normalize all inputs against an allowlist, and reserve high-cardinality identifiers for suitable signals like tracing when genuinely needed. Good tag design starts with operational questions, controlled value domains, and calculating total combinatorial cardinality before release.
