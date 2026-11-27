# Test observation name in Spring Boot

An observation name is the identifier of an instrumented operation. Good names help operators recognize the same kind of operation across requests, service instances, and environments. Unstable names or names containing dynamic data can fragment metrics into many time series, making dashboards hard to aggregate and alerts meaningless. Therefore, testing observation names is part of testing the observability contract, similar to testing API responses or event schemas.

The lesson **Test observation name** belongs to the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in real environments.

After this lesson, you will be able to define a naming contract, test Observation names directly via ObservationHandler, verify a custom ObservationConvention, distinguish observation names from meter/span names, control cardinality, and write regression tests to prevent unintended name changes.

## 1. What does an observation name represent?

An observation name identifies the type of operation being observed, for example:

- orders.lookup
- payment.authorize
- inventory.reserve
- messaging.publish
- report.generate

Names should describe the operation, not a single execution instance. A name such as orders.lookup.ORD-82731 embeds an order identifier into the operation name; each order can create a separate meter name/series or make trace operations difficult to aggregate.

| Stable name | Unstable name |
| --- | --- |
| orders.lookup | orders.lookup.ORD-82731 |
| payment.authorize | payment.authorize.customer-42 |
| report.generate | report.generate.2026-11-22T10:30 |
| messaging.consume | messaging.consume.message-uuid |

Stable names allow data to be aggregated by operation type. Per-call varying details, if genuinely needed, should live in appropriate attributes/log fields subject to policy.

## 2. Observation name differs from meter name and span name

Observation is an abstraction in Micrometer. Handlers can translate the same Observation into multiple signals, and each system has its own naming conventions:

| Concept | Example | Role |
| --- | --- | --- |
| Observation name | orders.lookup | Operation name at the instrumentation layer |
| Meter name | orders.lookup or convention-based name | Meter identifier in the registry |
| Span name | orders.lookup | Span name in the tracing backend |
| Metric tag | outcome=success | Data dimension with controlled cardinality |
| Trace attribute | order.type=retail | Metadata on a span |

Do not assume every handler preserves the observation name verbatim. Meter conventions may append suffixes such as .active or .duration or change formatting; tracing bridges may apply their own conventions. When testing, verify the contract at the specific layer you want to protect.

If the requirement is that business instrumentation does not change its name, test the Observation name directly. If the requirement is that exported metric series or span names follow a specific format, add integration tests for the corresponding registry/bridge.

## 3. Choosing a naming convention

A good naming convention has these characteristics:

- Uses stable operation names with clear business or technical meaning.
- Follows a consistent style, typically lowercase with dot hierarchy.
- Excludes request IDs, user IDs, order IDs, timestamps, or raw URLs.
- Distinguishes different operations when their lifecycles/semantics differ.
- Does not change arbitrarily because dashboards, alerts, and trace searches may depend on it.

Examples:

| Operation | Suggested observation name |
| --- | --- |
| Look up order | orders.lookup |
| Create order | orders.create |
| Authorize payment | payment.authorize |
| Publish message | orders.message.publish |
| Process message | orders.message.process |

Avoid mechanically deriving names from Java method names if method names may change during refactoring while operation semantics stay the same. An observation name is a telemetry contract; choose names around the operation operators need to understand.

## 4. Creating an Observation and testing its name directly

The Micrometer Observation API allows creating an observation with an explicit name. You can register a test handler to capture the lifecycle and context:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.Observation.Context;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ObservationNameTest {
    @Test
    void usesStableOperationName() {
        ObservationRegistry registry = ObservationRegistry.create();
        List<String> observedNames = new ArrayList<>();

        registry.observationConfig().observationHandler(
            new ObservationHandler<Context>() {
                @Override
                public boolean supportsContext(Context context) {
                    return true;
                }

                @Override
                public void onStart(Context context) {
                    observedNames.add(context.getName());
                }
            }
        );

        Observation.createNotStarted("orders.lookup", registry)
            .observe(() -> "order-result");

        assertThat(observedNames).containsExactly("orders.lookup");
    }
}
```

This is an example of testing directly at the Observation layer. Imports and generic types may need adjustment for the Micrometer version in your Spring Boot BOM. The handler only captures the name at start; in real tests you can also capture low-cardinality key-values and lifecycle callbacks.

The advantage of this approach is that the test does not require Prometheus, an OTLP collector, or a tracing backend. It verifies the instrumentation contract before handlers forward data to individual signals.

## 5. Testing a convention instead of hardcoding names everywhere

When names or metadata depend on context, Micrometer lets you use ObservationConvention to standardize naming and tags. A convention should centralize naming policy instead of repeating logic across controllers/services.

Example convention:

```java
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.Observation.Context;

class OrderObservationConvention
        implements ObservationConvention<Context> {
    @Override
    public boolean supportsContext(Context context) {
        return context instanceof OrderObservationContext;
    }

    @Override
    public String getName() {
        return "orders.process";
    }
}

class OrderObservationContext extends Context {
    // Add only explicitly approved operation metadata.
}
```

This is an illustrative skeleton. In a real application, context types, convention registration, and specific APIs depend on the instrumentation module/version. A convention can supply names as well as low-cardinality/high-cardinality key-values per contract.

Testing the convention directly:

```java
@Test
void conventionUsesExpectedName() {
    OrderObservationConvention convention =
        new OrderObservationConvention();
    OrderObservationContext context =
        new OrderObservationContext();

    assertThat(convention.supportsContext(context)).isTrue();
    assertThat(convention.getName()).isEqualTo("orders.process");
}
```

If a convention supports multiple context types, test both positive and negative cases. A convention must not mistakenly accept contexts belonging to other operations.

## 6. Testing custom low-cardinality tags alongside the name

A stable name is necessary but not sufficient. Tags must also keep bounded cardinality:

```java
Observation.createNotStarted("orders.lookup", registry)
    .lowCardinalityKeyValue("order.channel", "web")
    .lowCardinalityKeyValue("outcome", "success")
    .observe(() -> orderService.find(orderId));
```

Tests should verify:

- The observation name matches the contract.
- Key names are consistent.
- Channel/outcome belong to the defined value set.
- Order ID/customer ID do not appear in low-cardinality tags.
- No raw URL, query string, or exception message appears in tags.

You can capture the context in a test handler and assert key-values:

```java
// Pseudocode:
// Capture context.getName() at onStart.
// Capture context.getLowCardinalityKeyValues() at onStart/onStop.
// Assert name == "orders.lookup".
// Assert order.channel belongs to {"web", "mobile", "partner"}.
// Assert no key/value contains the request's order ID.
```

The pseudocode illustrates the idea; use the key-values API from your actual Micrometer version. Do not test by asserting only the name, because tag cardinality can cause problems even when the name is stable.

## 7. Testing names when using @Observed

If the application uses @Observed, the name declared on the annotation should be verified via AOP integration:

```java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {
    @Observed(name = "orders.lookup")
    public OrderView lookup(String orderId) {
        return new OrderView(orderId);
    }
}
```

The test must obtain the bean from the Spring ApplicationContext and call it through the proxy so the annotation interceptor actually runs. Instantiating the object with new OrderQueryService() bypasses Spring AOP and does not prove the annotation works.

```java
// Pseudocode:
// @SpringBootTest with observation annotation aspect enabled.
// Register a test ObservationHandler that captures context.getName().
// Autowire OrderQueryService from the application context.
// Call lookup("test-order-1") through the injected bean.
// Assert the captured observation name is exactly "orders.lookup".
```

Also check self-invocation if the method is called from another method in the same bean. Proxy-based AOP normally does not intercept internal calls via `this`.

## 8. Testing names of HTTP server observations

HTTP server instrumentation typically uses route/method conventions provided by the framework. Names/metadata of HTTP observations can differ from custom application observations.

When testing an HTTP route:

1. Send requests via MockMvc/WebTestClient or an appropriate embedded server.
2. Capture observations from the registry/test handler.
3. Verify that the route template is used instead of a raw URI with an ID.
4. Verify method/status/outcome according to the stack's conventions.
5. Distinguish the server observation from method-level observations if both appear.

Do not assert a single universal HTTP server observation name across all Spring Boot versions without checking dependencies/versions. HTTP instrumentation conventions can evolve across framework and Micrometer releases.

## 9. Testing mapping to meter names

If metric naming is part of the contract, test against a concrete meter registry. SimpleMeterRegistry makes it easy to check registered meters without a backend.

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ObservationMeterNameTest {
    @Test
    void recordsTimerForExpectedOperation() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        // Register the Micrometer meter handler appropriate to the
        // application's Micrometer version, then observe the operation.
        Observation.createNotStarted("orders.lookup", observations)
            .observe(() -> "ok");

        // Assert the meter name produced by the configured convention.
        assertThat(meters.getMeters()).isNotNull();
    }
}
```

The snippet above is a skeleton: creating SimpleMeterRegistry alone does not automatically register an Observation-to-Meter handler, so the final assertion does not yet prove a timer was recorded. A complete test must register the appropriate handler, usually provided via the application's Micrometer Observation/metrics integration, and then assert the actual meter name, count, and tags.

Do not hardcode a meter name solely based on the observation name. Timer conventions may append suffixes or normalize names. Read meter names from the registry in tests to verify the contract for your dependency version.

## 10. Testing mapping to span names

If the application uses a Micrometer Tracing bridge or OpenTelemetry, you can test span names with an in-memory/test exporter. The goal is to verify that the bridge converts the observation into a span with the right name and context:

- The span name is correct or mapped properly by the convention.
- Trace ID is preserved across parent/child operations.
- Error/status is recorded according to semantics.
- Low/high-cardinality attributes are mapped accurately.
- No duplicate spans are created for the same operation.

Testing an Observation handler does not replace testing the exporter. It only verifies the name at the Observation layer. Exporter tests verify the span payload after the processor/bridge.

## 11. Testing that names contain no dynamic data

Execute multiple invocations with different identifiers and verify the name stays identical:

```java
@Test
void operationNameDoesNotDependOnOrderId() {
    List<String> names = new ArrayList<>();

    observeLookup("order-100", names);
    observeLookup("order-200", names);
    observeLookup("order-300", names);

    assertThat(names).containsExactly(
        "orders.lookup",
        "orders.lookup",
        "orders.lookup"
    );
}
```

In a real test, the observeLookup helper creates an Observation with a fixed name and captures the context name in a handler. This test prevents someone from accidentally concatenating an order ID into the observation name during refactoring.

Do not only check the number of distinct names. Assert the exact contract name and verify that identifiers do not appear in names/tags used for metrics.

## 12. Testing exceptions and lifecycle

An observation name must remain the same whether the operation succeeds or fails. Test start, error, and stop:

```java
@Test
void keepsNameWhenOperationThrows() {
    List<String> names = new ArrayList<>();
    ObservationRegistry registry = registryCapturingNames(names);

    assertThatThrownBy(() ->
        Observation.createNotStarted("payment.authorize", registry)
            .observe(() -> {
                throw new IllegalStateException("declined");
            })
    ).isInstanceOf(IllegalStateException.class);

    assertThat(names).containsExactly("payment.authorize");
}
```

registryCapturingNames is a test helper to be implemented using an ObservationHandler. Do not assert the exception message as a tag; messages can contain unsafe data. Additional tests can verify that the handler receives onError and onStop according to the lifecycle.

## 13. Naming contracts and version changes

Observation names are commonly used by dashboards, alerts, trace searches, and runbooks. Renaming can leave old dashboards empty or split history into two series.

When renaming:

1. Identify the reason and semantic change.
2. Find consumers of the old name in dashboards/alerts/queries.
3. Decide on aliasing/dual publishing if a migration is needed.
4. Update tests before merging.
5. Update dashboards and runbooks according to the rollout plan.
6. Monitor both old and new names during the transition window if the pipeline supports it.

Do not rename just to match a Java method rename if operation semantics remain unchanged. Conversely, if semantics genuinely change, using a new name can help distinguish data before and after the change.

## 14. Common pitfalls

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| Observation not captured | Handler not registered or supportsContext returns false | Check registry and handler matching |
| @Observed does not produce expected name | Missing AOP aspect or call bypassed proxy | Fetch bean from context and check proxy |
| Meter name differs from observation name | Meter convention adds suffix/normalizes | Assert registry meter name in integration test |
| Span name differs from meter name | Tracing bridge uses its own convention | Inspect span exporter output |
| Multiple time series for same operation | Name or tags contain dynamic identifiers | Capture names/tags across multiple inputs |
| HTTP route name contains ID | Raw URI used instead of route template | Check server observation convention |
| Test passes but production name differs | Test uses NOOP/simple handler only | Add test with production-equivalent registry/bridge |
| Name changed after dependency upgrade | Convention/version changed | Pin contract tests and review migration |
| Duplicate observation | Instrumentation at multiple layers with same name/lifecycle | Define operation boundaries and ownership |

## 15. Practical scenario: refactoring increases metric cardinality

**Hypothetical scenario:** After a refactor, dashboards show thousands of meter names such as orders.lookup.1001 and orders.lookup.1002. Metrics registry memory grows and Prometheus has too many series.

Procedure:

1. **Capture names:** use a test ObservationHandler to record the context name across multiple order IDs.
2. **Find the dynamic source:** identify the annotation/convention concatenating the ID into the observation name.
3. **Standardize:** change back to the fixed name orders.lookup.
4. **Move metadata:** if order ID is needed for investigations, put it into a controlled log field or trace attribute, not a metric name/tag.
5. **Regression test:** run multiple distinct inputs and assert only one operation name and a finite set of low-cardinality tags.
6. **Metric verification:** check registry/Prometheus series count after the change.
7. **Dashboard migration:** update queries if the old name was already used in dashboards/alerts.

A stable name allows the registry to aggregate measurements for the same operation rather than creating a meter per entity.

## 16. Self-check exercises

**Exercise 1.** Should an observation name represent an operation or a single execution?

*Hint:* It represents the operation type; it must not contain request/order/customer IDs.

**Exercise 2.** What does testing an ObservationHandler prove?

*Hint:* It verifies the name/context at the Observation layer; it does not prove an exporter or backend received spans.

**Exercise 3.** Why can a meter name differ from an observation name?

*Hint:* Meter conventions may add suffixes, normalize characters, or map to a specific meter type.

**Exercise 4.** How do you test that @Observed is intercepted?

*Hint:* Invoke the bean through the ApplicationContext proxy and capture the name with a test ObservationHandler.

**Exercise 5.** Why should you test names with multiple IDs?

*Hint:* To catch dynamic names that cause cardinality to grow with entity/request counts.

**Exercise 6.** When should you test span names using an exporter?

*Hint:* When tracing bridge/span naming is a contract to protect; an Observation handler does not verify that mapping step.

**Exercise 7.** Should you rename an observation just because a Java method was renamed?

*Hint:* Not necessarily; telemetry names are tied to operation semantics and dashboards, not just method names.

**Exercise 8.** When renaming an observation already used by dashboards, what should you do?

*Hint:* Plan a migration for queries/alerts, update contract tests, and monitor both old and new data.

## 17. Key takeaways

- An observation name is a stable operation identifier; never embed request IDs, entity IDs, timestamps, or raw URLs in the name.
- Test names directly with an ObservationHandler to verify the instrumentation-layer contract without needing a backend.
- Observation name, meter name, and span name can differ due to conventions/handlers; test at the exact layer you need to protect.
- Use ObservationConvention to centralize naming/tags; test both supported and rejected contexts.
- With @Observed, call the bean through a Spring proxy; test self-invocation and AOP limitations if applicable.
- Test low-cardinality tags alongside names; a stable name is not enough if tags still contain dynamic identifiers.
- Use registry integration tests for meter names and in-memory/test exporters for span names/attributes.
- Treat observation names as a telemetry contract: changes require regression tests and updates to dashboards/alerts/runbooks.
