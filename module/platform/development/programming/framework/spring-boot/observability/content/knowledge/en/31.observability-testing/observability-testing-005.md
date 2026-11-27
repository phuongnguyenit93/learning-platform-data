# Test high-cardinality keys

In the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, high-cardinality key testing is the suite of tests aimed at catching metric tags/labels or attributes that can produce too many distinct values. A tag such as `tenantId`, `userId`, `requestId`, a raw URL, or a SQL statement may look helpful when debugging a single request, but when placed into metrics, every new value can create a new time series in the backend.

Cardinality is a property of the full set of dimensions on a metric, not just a single key in isolation. Therefore, tests must verify data sources (routes, exceptions, tenants, dependencies), normalization logic, the number of combinations created, and histogram impact. A unit test that only checks a tag name or a single fixed request usually fails to catch the issue; you need varied input values, integration tests across framework instrumentation, and budget assertions.

This lesson shows how to build tests that keep high-cardinality keys out of metrics in Spring Boot/Micrometer while preserving detailed investigation capability through controlled logs and traces.

## 1. Learning objectives

After this lesson, you can:
1. Identify metric tag keys and values that carry high-cardinality risk.
2. Distinguish metric labels from trace attributes and structured log fields.
3. Compute an upper bound on series from dimensions.
4. Write unit tests checking MeterRegistry and tag values.
5. Test MeterFilter limits and behavior when thresholds are exceeded.
6. Send multiple HTTP paths/identifiers to verify route normalization.
7. Test custom Observation conventions and instrumentation.
8. Account for histogram bucket multiplication in the series budget.
9. Use generated/property-based inputs to detect dynamic values.
10. Establish a regression gate to prevent unexpected cardinality growth.

## 2. What is a high-cardinality key?

A metric series is typically identified by the metric name and the full set of tag/label values. A key has high cardinality when it takes on many distinct values, especially when values come from individual requests or entities.

| Key | Example value | Risk |
| --- | --- | --- |
| tenantId | tenant-abc | Tenant count can grow continuously. |
| userId | u-10001, u-10002 | One series per user. |
| requestId | UUID per request | Almost one value per request. |
| traceId | Trace ID | Every trace differs. |
| uri | /orders/10001 | Raw path creates series per resource ID. |
| sql | Full SQL text | Literal values and dynamic queries. |
| exception.message | Message with host/input | Unstable values. |
| email | alice@example.com | PII and huge cardinality. |

Key name alone is not enough to judge. `uri` can be safe if its value is the route template `/orders/{orderId}`; `status` can become high-cardinality if code attaches the full error message to it. Tests must check actual values and where they are attached.

## 3. Distinguishing metrics, traces, and logs in tests

Not all high-cardinality information needs to be stripped from observability. What matters is keeping unbounded identifiers out of metric dimensions.

| Signal | Suitable data | What to test |
| --- | --- | --- |
| Metrics | method, route template, status class, outcome, fixed service name | Finite value sets and series budget. |
| Traces | trace/span IDs, policy-approved request-specific attributes | Privacy, sampling, attribute policy, and retention. |
| Logs | request ID or entity ID when legitimately needed for investigation | Masking, access control, and retention. |
| Exemplars | Linking a metric sample to a trace | Backend support, without turning trace ID into a label. |

For example, a test should fail if `requestId` appears in `Meter.Id.tags`, but does not necessarily need to fail if request ID appears in an approved structured log field. Do not apply the exact same rule mechanically across all signals.

## 4. Building an inventory and budget before writing tests

Start by inventorying important metric families: `http.server.requests`, `http.client.requests`, JDBC/connection-pool metrics, business timers/counters, scheduler/task metrics, cache, messaging, and executor metrics.

For each metric, record expected keys, maximum value sets, owner, and budget. A simple upper bound:

~~~text
series_combinations =
    values(method)
    * values(route)
    * values(status)
    * values(outcome)
~~~

Example:

~~~text
method  = 5
route   = 30
status  = 8
outcome = 4

upper bound = 5 * 30 * 8 * 4 = 4,800
~~~

If a `tenantId` key with 2,000 values is added:

~~~text
4,800 * 2,000 = 9,600,000 combinations
~~~

This upper bound assumes every combination can occur. Budget tests should state assumptions explicitly, since some combinations may be invalid in the application.

For classic histograms, multiply further by the number of bucket series and `_count`/`_sum` per the exposition format. Do not merely assert the count of meter objects in the registry and conclude the backend only sees that many series.

## 5. Unit tests disallowing identifier keys

You can inspect a meter's tags after invoking instrumented code. Example assertion helper:

~~~java
static void assertNoHighCardinalityKeys(MeterRegistry registry) {
    Set<String> forbidden = Set.of(
            "userId",
            "tenantId",
            "requestId",
            "traceId",
            "email",
            "sql"
    );

    List<String> violations = registry.getMeters().stream()
            .flatMap(meter -> meter.getId().getTags().stream())
            .map(Tag::getKey)
            .filter(forbidden::contains)
            .distinct()
            .toList();

    assertThat(violations).isEmpty();
}
~~~

This is an illustrative example. The forbidden key set must match your project's naming conventions; check `snake_case`, `kebab-case`, or aliases as well if instrumentation mixes conventions.

The test must run after triggering operations that create meters. An empty registry does not prove instrumentation is safe.

### Checking tag values

Beyond key names, verify whether values are raw identifiers. For example, a route tag should only contain route templates:

~~~java
assertThat(uriValues)
        .contains("/orders/{orderId}")
        .doesNotContain("/orders/10001", "/orders/10002");
~~~

Do not only blacklist a couple of hardcoded IDs. It is better to generate hundreds of random identifiers in a test and verify that the number of `uri` values stays at one.

## 6. Integration tests for route normalization

HTTP instrumentation can obtain the route template from the framework once handler mapping completes. Tests should send real requests through MockMvc/WebTestClient or an embedded server to verify the final value.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpMetricCardinalityTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void differentOrderIdsShareOneUriTag() throws Exception {
        for (int id = 1; id <= 100; id++) {
            mockMvc.perform(get("/orders/{id}", id))
                    .andExpect(status().isOk());
        }

        Set<String> uriValues = registry.find("http.server.requests")
                .meters()
                .stream()
                .flatMap(meter -> meter.getId().getTags().stream())
                .filter(tag -> tag.getKey().equals("uri"))
                .map(Tag::getValue)
                .collect(Collectors.toSet());

        assertThat(uriValues).contains("/orders/{id}");
        assertThat(uriValues).doesNotContain("/orders/1", "/orders/100");
    }
}
~~~

The test requires a real controller route and an endpoint returning a deterministic status. Meter/tag names may vary by Boot/Micrometer version and naming convention; inspect the project's registry before fixing assertions.

Additional cases to cover: query parameters containing IDs/emails must not be added to tags; unknown routes must not create raw path values; error routes and exception handlers must still use route templates; nested routes are normalized; HTTP client destinations use logical service names rather than dynamic hosts/paths.

## 7. Testing MeterFilter tag value limits

Micrometer's `MeterFilter.maximumAllowableTags` can limit the number of tag values on a meter. You can test its behavior directly against a registry:

~~~java
@Test
void deniesNewUriValuesAfterLimit() {
    MeterRegistry registry = new SimpleMeterRegistry();
    registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                    "demo.requests",
                    "uri",
                    2,
                    MeterFilter.deny()
            )
    );

    registry.counter("demo.requests", "uri", "/orders").increment();
    registry.counter("demo.requests", "uri", "/customers").increment();
    registry.counter("demo.requests", "uri", "/payments").increment();

    assertThat(registry.find("demo.requests")
            .tag("uri", "/orders").counter()).isNotNull();
    assertThat(registry.find("demo.requests")
            .tag("uri", "/customers").counter()).isNotNull();
    assertThat(registry.find("demo.requests")
            .tag("uri", "/payments").counter()).isNull();
}
~~~

This test illustrates the filter denying registrations beyond the limit. Verify behavior for your Micrometer version, filter order, and specific registry. In real applications, meters may be registered from multiple instrumentation sources; integration tests must use the exact meter name and tag key.

Notes:
- The filter protects when new meters are created; it does not delete existing series.
- The filter does not rewrite raw values into route templates.
- The filter does not apply to logs/traces.
- Tests must verify behavior when the limit is exceeded, not merely that the filter bean exists.

## 8. Testing custom Observation conventions

If the application uses the Observation API, conventions determine names and key-values. Tests must inspect low-cardinality key-values before they are turned into metrics.

~~~java
class OrderObservationConvention
        implements ObservationConvention<ServerRequestObservationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ServerRequestObservationContext;
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of("operation", "order.read"),
                KeyValue.of("outcome", "success")
        );
    }

    @Override
    public String getName() {
        return "order.request";
    }
}
~~~

This example illustrates the concept; choose contexts/conventions matching your actual instrumentation. Do not put the request object, principal, tenant ID, or raw URI into low-cardinality values.

If request-specific details are needed, consider high-cardinality trace attributes with a privacy review. Tests should confirm they do not appear in the metrics registry.

## 9. Property-based and generated input tests

Some bugs only surface when values vary continuously. You can feed generated inputs:
- 1,000 user IDs.
- 500 tenant IDs.
- Many order/resource IDs on the same route.
- Random query strings.
- Exception messages containing hosts, UUIDs, or input values.
- SQL statements with varying literals.

Key invariants:
- The number of `uri` tag values equals the number of route templates, not the number of resource IDs.
- No identifier keys exist in metrics.
- Outcome/status values belong to the allow-list.
- Combination counts do not exceed budget.
- Error messages do not become tag values.
- Changing input identifiers does not introduce new metric series.

A property-based testing framework can generate seeded data for reproducible failures. If not using a dedicated framework, a loop of generated inputs can still verify invariants, provided you log the seed when a test fails.

## 10. Histogram and series budget tests

Histograms multiply series counts per label set. With Prometheus classic histograms, there is typically one series per bucket, plus `_count` and `_sum`. For example, 10 finite buckets, the `+Inf` bucket, count, and sum correspond to 13 series per label combination.

Budget tests should:
1. Identify metric families with histograms enabled.
2. Read the bucket configuration per environment.
3. Compute the allowed number of label combinations.
4. Multiply by the bucket/count/sum count.
5. Compare against the metric family's budget.
6. Verify exporter output if the backend format differs.

Do not assert one fixed number across all registries. Native histograms, OTLP histograms, and Prometheus classic histograms have different representations. Budget tests must know the exporter format used in production.

## 11. Testing exemplars and correlation

If the registry/backend supports exemplars, tests can verify that metric samples link to trace context without adding trace ID as a label.

Checks to verify:
- Exemplar support is enabled in the registry/exporter.
- Trace ID does not appear in `Meter.Id.tags`.
- Trace ID only resides in exemplar metadata per backend format.
- Sampling/tracing context is active when recording measurements.
- No sensitive baggage is placed into exemplars or span attributes.

If exemplars are unsupported, use structured logs and the tracing backend for correlation. Never create a `traceId` metric label as a workaround.

## 12. Testing across multiple layers

| Test layer | Goal | Example |
| --- | --- | --- |
| Unit | Verify tag policy/convention. | No `tenantId` in low-cardinality values. |
| MeterRegistry integration | Inspect meters after instrumentation. | No forbidden tag keys. |
| Web integration | Verify framework route normalization. | 100 order IDs produce only one `uri` tag value. |
| Exporter integration | Inspect series exposition/OTLP output. | Histogram series count matches estimate. |
| Load/staging | Verify cardinality under realistic workloads. | Active series do not grow linearly with request IDs. |
| Production monitoring | Detect post-deploy drift. | Alert when active series/churn exceeds baseline. |

Do not replace an integration test by manually creating a meter in a test with a pre-filled route template. Tests must traverse the instrumentation boundary being protected.

## 13. Regression gates in CI

Create a dedicated metric contract test suite and run it whenever metric names/tag keys, Observation conventions, HTTP route/controller mappings, dependency instrumentation, histogram/SLO configurations, Micrometer/Spring Boot versions, or registries/exporters change.

A regression report should list new/changed metric families, added/removed tag keys, before/after upper-bound series counts, histogram multipliers, budget owners, and the test data/seed used for verification.

Not every metric needs the same threshold. Use per-family budgets and require review when adding a new dimension.

## 14. Troubleshooting

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| Tests pass but production cardinality is high | Tests lack realistic data distribution or miss integration boundaries. | Generate identifiers and send requests through a real server. |
| `uri` tag contains IDs | Instrumentation uses raw path instead of route template. | Check route mapping and meter values. |
| Forbidden key still appears | Naming alias missing from blacklist or wrong filter order. | Normalize key names and inspect the full registry. |
| MeterFilter does not deny | Wrong meter name/tag key or filter registered too late. | Check configuration order and exact meter ID. |
| Registry meter count is low but backend series are high | Histograms/exporter multiply series or multiple instances exist. | Inspect exposition format and replica multiplier. |
| Request ID appears in metrics | Custom convention/filter adds dynamic value. | Inspect low-cardinality KeyValues. |
| Flaky test | Shared registry or incomplete asynchronous instrumentation. | Use isolated registries, reset state, and synchronize test lifecycle. |
| Test sees no meters | Endpoint not invoked, filter not triggered, or misconfigured. | Check request status, registry bean, and meter creation. |
| Series jump after upgrade | Binder/convention changed tag sets. | Compare meter metadata before/after version bump. |
| Removing ID tag loses debuggability | Correlation channel missing. | Use structured logs, traces, or exemplars. |

## 15. Runbook when tests detect a high-cardinality key

1. Identify the offending metric name and tag key.
2. Trace the instrumentation source: binder, Observation convention, annotation, filter, or custom meter.
3. Collect multiple real values and classify identifier/route/exception dimensions.
4. Determine whether the metric family needs that dimension for any alert or dashboard.
5. If not needed, remove the key from metrics.
6. If grouping is needed, map values to a finite allow-list.
7. For HTTP, use route templates; for SQL, use stable operations/fingerprints.
8. Move request-specific details to logs/traces per privacy policy.
9. Update upper-bound budgets and histogram multipliers.
10. Write a regression test with generated inputs and integration paths.
11. Re-run the suite and verify exporter output.
12. Monitor active series/churn after deployment to confirm the fix.

## 16. Self-check exercises

### Exercise 1 — Identifying keys

A Timer has tags `method`, `uri`, `tenantId`, and `outcome`. Which keys need inspection or removal from the metric?

**Answer:** `tenantId` typically has high cardinality and should move to logs/traces or be grouped into tenant tiers. `uri` is safe only if it is a route template. `method` and `outcome` normally have finite value sets.

### Exercise 2 — Single-request test

A test sends one request to `/orders/1` and confirms a meter exists. Why is that insufficient?

**Answer:** A single request does not reveal whether raw URIs create a separate series per ID. You must send multiple IDs and assert the count of `uri` values still equals the number of route templates.

### Exercise 3 — Filter limit

`maximumAllowableTags` is set to a limit of 100. Does that prove the tag design is good?

**Answer:** No. The filter only blocks new meters after the threshold; 100 raw values may still be excessive. Normalize at the source and set budgets based on use cases.

### Exercise 4 — Histogram

A metric has 2,000 label combinations and 13 bucket series plus count/sum. Estimate the series count.

**Answer:** 2,000 × 15 = 30,000 series under the assumed classic histogram format.

### Exercise 5 — Trace ID

A test confirms `traceId` is absent from metric tags. Should trace ID be removed from traces and logs too?

**Answer:** Not automatically. Traces/logs may need request-specific correlation per policy; protect privacy, sampling, access, and retention separately.

### Exercise 6 — Production drift

CI passes, yet active series surge after release. What should be checked?

**Answer:** Input distribution, replicas, histogram config, binder/convention changes, exporter format, and instrumentation sources not covered in CI.

## 17. Implementation checklist

- [ ] Maintain an inventory of metric families and permitted tag keys.
- [ ] Identify high-cardinality keys by actual values, not key names alone.
- [ ] Unit tests check for forbidden keys in MeterRegistry.
- [ ] Tests verify tag values and upper-bound combinations.
- [ ] Integration tests send multiple IDs through real route mapping.
- [ ] Raw paths/query parameters do not become metric tags.
- [ ] Tenant/user/request/trace IDs are absent from metric labels.
- [ ] Exception messages and raw SQL do not become tag values.
- [ ] MeterFilter limits are tested with threshold-exceeding cases.
- [ ] Observation conventions only place bounded values into low-cardinality keys.
- [ ] Histogram buckets/count/sum are factored into series budgets.
- [ ] Exporter output format is checked by integration tests.
- [ ] Exemplars are used if metric-to-trace correlation is needed and supported by the backend.
- [ ] Logs/traces retain identifiers under privacy, sampling, and retention policies.
- [ ] CI regression gates run when metrics/tags/configs/versions change.
- [ ] Production active series and churn are monitored after deployment.

**Takeaway:** Testing high-cardinality keys must inspect values and series combinations through actual instrumentation paths. Use generated identifiers, route integration tests, MeterRegistry assertions, MeterFilter tests, and histogram budget calculations. Metrics keep only finite dimensions; request-specific details belong in logs/traces or exemplars under policy. Combine CI regression gates with post-deploy active series monitoring to catch cardinality drift.
