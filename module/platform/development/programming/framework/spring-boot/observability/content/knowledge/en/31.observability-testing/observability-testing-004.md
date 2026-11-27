# Test low-cardinality keys in Spring Boot

Metrics are useful when they can be grouped and compared across stable dimensions such as operation, outcome, or region. However, a seemingly reasonable tag key can still generate thousands of time series if its value comes from a user ID, order ID, full URL, or free-form text. High cardinality increases memory, storage, query cost, and load on the metrics backend. Therefore, cardinality control should be tested as an instrumentation property, not just treated as a code review convention.

This lesson covers how to test metric tag keys and values in Spring Boot/Micrometer: defining finite dimensions, using a test MeterRegistry to inspect meters, applying MeterFilter to cap tag values, and testing that dynamic/sensitive data does not leak into tags. The goal is to ensure metrics can be grouped by required categories while keeping observability costs bounded.

The lesson **Test low-cardinality key** belongs to the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module focuses on setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

## 1. Learning objectives

After this lesson, you can:

- Explain cardinality and its impact on metrics backends.
- Distinguish a stable tag key from a tag value with a finite set of values.
- Design allow-lists for operation, outcome, channel, and region.
- Write tests with SimpleMeterRegistry to inspect tag keys/values.
- Use MeterFilter.maximumAllowableTags as a guardrail limit.
- Test Observation conventions and custom tags.
- Detect IDs, dynamic URLs, free-text, and PII in metric dimensions.
- Set a cardinality budget and test under varied inputs.

## 2. What is cardinality?

A meter is identified by its name and its set of tag key-values. Each combination of tag values can create a distinct meter identity/time series. If a Timer has two tags:

- operation: 4 values.
- outcome: 3 values.

Then the maximum number of combinations is 4 × 3 = 12 series for one meter name in a single registry, before counting other dimensions, instance labels, or histogram buckets.

Conversely, if you add customer_id with 100,000 values, the series count can grow roughly in proportion to the number of customers. If you add request_id which is nearly unique per request, cardinality can grow at the rate of traffic.

### Key and value

A tag key is the dimension name, such as operation, region, or outcome. A tag value is a specific category, such as read, ap-southeast, or success. A stable key does not guarantee low cardinality: a key like customer_id can still contain unbounded values.

| Tag | Assessment | Reason |
| --- | --- | --- |
| operation=read/write | Usually suitable | Finite set of operations |
| outcome=success/error | Usually suitable | Small set of outcomes |
| region=ap-southeast/eu-west | Can be suitable | Managed set of regions |
| customer_id=... | Unsuitable | Nearly one value per customer |
| request_id=... | Unsuitable | Nearly unique per request |
| url=/orders/12345 | Unsuitable | Path contains dynamic ID |
| email=... | Unsuitable | PII and very high cardinality |

## 3. Setting a cardinality budget before writing tests

A cardinality budget is the expected upper bound on the number of tag value combinations for a meter or group of meters. The budget should reflect operation categories, outcome categories, region/channel/tenant-tier categories, scraped instances/replicas, histogram buckets, and backend label expansion.

For example, the meter http.server.requests with 8 route templates, 5 methods, and 6 outcomes:

\[
8 \times 5 \times 6 = 240
\]

If there are 20 instances and each instance exports the same dimensions, the backend can observe roughly 4,800 series before histogram expansion. Exact numbers depend on registry/backend labels and aggregation configuration.

Do not pick a budget solely from current data. Consider growth: will adding routes, regions, tenant tiers, or status categories cause combinations to spike?

## 4. Testing tag values with SimpleMeterRegistry

SimpleMeterRegistry is well suited for unit tests because it holds meters in memory and requires no Prometheus/OTLP backend. Example service recording a Timer with finite dimensions:

```java
class OrderMetrics {
    private final MeterRegistry registry;

    OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(String operation, String outcome) {
        Timer.builder("orders.operation")
            .tag("operation", operation)
            .tag("outcome", outcome)
            .register(registry)
            .record(() -> performWork());
    }

    private void performWork() {
        // Business operation
    }
}
```

Test verifying the expected tags are created:

```java
class OrderMetricsTest {
    private final SimpleMeterRegistry registry =
        new SimpleMeterRegistry();

    @Test
    void recordsOnlyExpectedLowCardinalityTags() {
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.record("read", "success");

        Timer timer = registry.find("orders.operation")
            .tag("operation", "read")
            .tag("outcome", "success")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
```

This example uses AssertJ and JUnit. In a real project, use an injected MeterRegistry and make sure tests close the registry after completion if the registry holds resources.

### Inspecting the actual set of values

You can retrieve meters with the same name and inspect their tags:

```java
List<Meter> meters = registry.getMeters().stream()
    .filter(m -> m.getId().getName().equals("orders.operation"))
    .toList();

Set<String> operations = meters.stream()
    .map(m -> m.getId().getTag("operation"))
    .collect(Collectors.toSet());

assertThat(operations)
    .containsOnly("read", "write");
```

This set assertion helps catch unexpected values. For Java versions prior to Stream.toList(), use Collectors.toList().

## 5. Testing allow-lists for tag values

Do not test only a single valid input. Invoke the instrumentation with multiple inputs and verify the output remains within the allow-list:

```java
enum Operation {
    READ, WRITE, DELETE
}

String operationTag(Operation operation) {
    return switch (operation) {
        case READ -> "read";
        case WRITE -> "write";
        case DELETE -> "delete";
    };
}
```

A parameterized test can verify every enum value and fallback behavior. If input comes from a request or message payload, map it to an enum/category before recording the meter. Never pass a raw string from a caller directly into tag().

### Unknown values

For unrecognized categories, choose explicit behavior: map to other/unknown, reject the input if it is a business validation rule, or omit the tag if the API supports dropping the dimension.

Never use the raw unknown value as the fallback, because an attacker or client could send many distinct values to inflate cardinality.

## 6. Using MeterFilter.maximumAllowableTags

Micrometer provides MeterFilter.maximumAllowableTags to limit the number of tag values for a meter name and tag key. This is a safety guard, not a substitute for proper tag design.

Example:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsConfiguration {

    @Bean
    MeterFilter orderTagCardinalityGuard() {
        return MeterFilter.maximumAllowableTags(
            "orders.operation",
            "operation",
            10,
            MeterFilter.deny()
        );
    }
}
```

When the limit is exceeded, the filter denies new meters according to the supplied policy. Choose an appropriate fallback filter and understand that this behavior applies at meter registration time; the filter does not automatically delete time series that were already exported earlier.

### Testing the filter

You can register the filter on a test registry and create multiple tag values:

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "orders.operation", "operation", 2, MeterFilter.deny()
    )
);

Timer.builder("orders.operation")
    .tag("operation", "read")
    .register(registry);
Timer.builder("orders.operation")
    .tag("operation", "write")
    .register(registry);
Timer.builder("orders.operation")
    .tag("operation", "delete")
    .register(registry);

assertThat(registry.find("orders.operation").meters()).hasSize(2);
```

Exact behavior should be verified against filter ordering and your registry implementation/version. Tests should verify that the excess meter is denied or produces the expected filter outcome, rather than relying only on total count if the registry has common tags or other filters.

## 7. Testing Observation tags and conventions

In Spring Boot, many metrics are produced from Micrometer Observation. Tag values can come from an Observation convention, low-cardinality key-values, or custom instrumentation.

A test can use TestObservationRegistry or an appropriate registry in the project's Micrometer Observation version to verify lifecycle and key-values. Conceptual example:

```java
Observation observation = Observation
    .createNotStarted("orders.process", observationRegistry)
    .lowCardinalityKeyValue("operation", "create")
    .lowCardinalityKeyValue("outcome", "success");

observation.start();
try {
    processOrder();
} finally {
    observation.stop();
}
```

Tests must verify that handlers receive the expected low-cardinality values. highCardinalityKeyValue can be suitable for trace/span attributes in some systems, but must not be turned into metric labels. Verify the actual convention/handler and registry output.

### Testing custom conventions

If a custom convention extracts route, tenant tier, or operation from a request, test route templates rather than raw paths containing IDs, allow-listed tenant tiers rather than tenant IDs, normalized HTTP methods/status codes, unknown routes/values falling back to a category, and no authorization headers, cookies, or payloads in tags.

## 8. Tests to detect dynamic data and PII

A useful test supplies risky-shaped inputs and verifies they do not appear in tag values:

```java
@Test
void doesNotUseCustomerIdAsMetricTag() {
    metrics.recordCustomerOperation(
        "customer-7f3a9d2c",
        "read"
    );

    assertThat(registry.getMeters())
        .noneMatch(m -> m.getId().getTags().stream()
            .anyMatch(tag -> tag.getValue().equals("customer-7f3a9d2c")));
}
```

This is an example checking a sentinel value. You can use sentinel emails, order IDs, fake tokens, and raw URLs in tests; never use real data. For logs/traces, test those signals separately because MeterRegistry tests do not inspect logging appenders or span exporters.

## 9. Testing cardinality under multiple inputs

Tests should generate many distinct inputs to guarantee the meter count does not grow per request:

```java
@Test
void customerIdsDoNotCreateNewTimeSeries() {
    for (int i = 0; i < 500; i++) {
        service.process("customer-" + i, "read");
    }

    long matchingMeters = registry.getMeters().stream()
        .filter(m -> m.getId().getName().equals("orders.operation"))
        .count();

    assertThat(matchingMeters).isLessThanOrEqualTo(4);
}
```

The budget of 4 in the example must match the designed operation/outcome combinations. The test should clearly specify which meter dimensions are permitted; otherwise the threshold may be too loose or break when a valid category is added.

### Property-based testing

If tag values derive from complex input, property-based tests can generate many random strings and verify that the number of distinct tag values stays within the allow-list, raw input never appears in metric tags, null/blank/unknown values normalize consistently, and the resolver never throws on contract-valid inputs.

You do not need to create millions of meters in a unit test; a moderately large count is enough to prove meter identity does not depend on ID/request values.

## 10. Testing exporter/backend differs from testing the registry

SimpleMeterRegistry checks instrumentation and tag identity in-process. It does not prove Prometheus scraping, OTLP export, or remote backends work.

| Test level | What it verifies |
| --- | --- |
| Unit test | Tag keys/values, allow-list, fallback, and meter count |
| Spring context test | Auto-configuration, ObservationRegistry, filters, and conventions |
| Endpoint test | Actuator /metrics or /prometheus returns expected meters |
| Integration test | Exporter sends data to a test Collector/backend |
| Load test | Cardinality, memory, scrape/export throughput under traffic |

Do not put a remote exporter into every unit test. Use an in-memory registry for fast, stable tests; only integration tests need a simulated Collector/backend or test environment.

## 11. Cardinality and histogram buckets

A Timer/distribution summary can produce many series per tag combination if histogram buckets are enabled. For example, a Timer with 12 tag combinations and 10 histogram buckets plus count/sum can produce far more than 12 series.

A cardinality budget should account for tag value combinations, histogram bucket count, instance/replica labels, registry-specific labels, and exporter/backend transformations.

Tests can verify histogram configuration separately, but should not assume the backend series count equals the number of Meter objects in SimpleMeterRegistry. Inspect the exposition format or scrape output when assessing actual series counts.

## 12. Troubleshooting

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| Meter count grows with customer IDs | Raw ID used as tag value | Check custom tags/conventions and normalize |
| Filter denies valid meter | Budget too low or mismatched tag key | Check filter order and expected categories |
| Unit test passes but production cardinality is high | Common tags/auto-instrumentation add extra dimensions | Inspect registry output and backend labels |
| Tag key does not appear | Meter not registered or convention did not run | Check invocation/Observation lifecycle |
| Tag value is a full URL | Raw URI used instead of route template | Normalize to route pattern |
| PII appears in metrics | Resolver or instrumentation copies request fields | Redact/allow-list and add regression test |
| Flaky test meter count | Registry shared across tests or state not reset | Create a fresh registry per test and close after |
| Filter does not cap as expected | Filter applied to wrong meter name/key or order | Check matcher and registration sequence |
| Prometheus series exceed registry meter count | Histogram buckets or labels added on export | Inspect scrape exposition and backend labels |
| Flaky exporter test | Unit test depends on network/Collector | Separate unit tests and integration tests |
| Unknown values create new series | Fallback returns raw input | Map to other or reject |

### Review checklist

1. List all tag keys for the meter under test.
2. Define allow-listed values and the cardinality budget.
3. Check value sources: enum, request, database, message, or custom resolver.
4. Test valid, unknown, null, dynamic ID, and PII sentinel inputs.
5. Inspect MeterRegistry meters and tag sets.
6. Test the MeterFilter guard for the chosen limit.
7. Check Observation conventions/custom tags.
8. Check histogram buckets and exported series if needed.
9. Verify the registry is reset between tests.

## 13. Practice: controlling cardinality for order metrics

**Scenario:** order-service records the Timer orders.operation. Initially the metric had tags operation and outcome, but a change added customerId, causing series counts to surge. The team needs tests to prevent regressions.

### Part A — Preparation

1. Use SimpleMeterRegistry for unit tests.
2. Define the operation allow-list: read, write, delete.
3. Define the outcome allow-list: success, error.
4. Set a maximum budget of 3 × 2 = 6 meter identities.
5. Configure the resolver to map unknown operation/outcome values to the chosen category.
6. Add a MeterFilter capping tag values as a safety guard.

### Part B — Verification

| Case | Input | Expected observation |
| --- | --- | --- |
| A — Valid | read/success | Meter has exactly two tags |
| B — All categories | All valid operations/outcomes | No more than 6 identities |
| C — Unknown | Arbitrary operation from caller | Normalized or rejected, no new series created |
| D — Dynamic ID | 500 distinct customer IDs | Meter count does not grow with customer count |
| E — PII sentinel | Fake email/token | Does not appear in metric tags |
| F — Filter guard | Exceeds tag value budget | New meter is denied per policy |
| G — Observation | Create Observation with low-cardinality keys | Handler/registry receives expected values |
| H — Histogram | Enable percentile histogram in integration test | Assess series expansion in scrape output |

### Part C — Self-assessment questions

1. What factors determine a meter's cardinality?
2. Why can a stable tag key still have high cardinality?
3. What does SimpleMeterRegistry help verify?
4. How does MeterFilter.maximumAllowableTags protect the system?
5. Why is a filter not a replacement for instrumentation-level allow-lists?
6. How do you test that unknown values do not create new series?
7. Why does testing the registry not prove the exporter/backend received metrics?
8. How do histogram buckets affect series counts?
9. How do sentinel tests catch PII in tag values?
10. Why must a cardinality budget consider replicas and combined dimensions?

## 14. Key takeaways

**Testing low-cardinality keys** verifies that metric dimensions have finite value sets and do not depend on per-request or per-user data. Use SimpleMeterRegistry to inspect meter identity, tag keys/values, and meter counts; use MeterFilter.maximumAllowableTags as an additional guardrail, not as a substitute for allow-lists and normalization in instrumentation.

Test valid, unknown, null, dynamic ID, and PII sentinel inputs. For Observations, test conventions and low-cardinality key-values before handlers create meters. A cardinality budget should account for the product of dimensions, replicas, and histogram buckets; exported series can outnumber Meter objects in the registry. Separate unit tests from endpoint/integration/load tests to verify each layer properly. When these tests run in CI, instrumentation regressions can be caught before they increase memory usage, drive up metrics backend costs, or leak data.
