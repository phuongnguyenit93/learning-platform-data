# Testing ObservationPredicate in Micrometer

In the **Testing observability** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `ObservationPredicate` is a filter that decides whether an observation is allowed to proceed based on the observation name and its context. Testing predicates ensures that operations requiring monitoring still produce metrics/traces while excluded operations are handled according to instrumentation policy.

Predicates are commonly used to skip internal observations, health probes, unmonitored endpoints, or high-volume operations. A wrong filter condition can silently drop metrics and spans, leaving dashboards incomplete or breaking traces. Therefore, tests must verify both accepted and rejected cases, as well as the effect on observation handlers.

In **SPRING_BOOT_OBSERVABILITY**, Observation connects instrumentation to handlers such as metrics or tracing. This lesson focuses on the semantics of `ObservationPredicate`, registration in `ObservationRegistry`/Spring Boot, unit and context tests, negative cases, filter ordering, and avoiding confusion between predicates and sampling.

## 1. What does ObservationPredicate do?

A Micrometer Observation has a name and a context. Instrumentation creates the observation, and then the registry applies configuration to decide whether the observation continues and gets processed by observation handlers. `ObservationPredicate` provides the filtering condition based on name and context.

Conceptually, the predicate receives two pieces of information:

- The observation name, usually a stable name assigned by instrumentation/convention.
- `Observation.Context`, which holds data attached to the operation and may have a specific subtype.

If the predicate returns `true`, the observation is accepted to proceed through its lifecycle. If it returns `false`, the observation becomes a no-op / is not recorded by handlers as a normal observation. Exact lifecycle details and how multiple predicates combine should be verified for your Micrometer version.

```text
Instrumentation creates observation
              |
              v
       ObservationPredicate
          /         \
       true         false
        |             |
        v             v
 Continue lifecycle  No-op / filtered
        |
        v
 Observation handlers
   |              |
   v              v
 Metrics        Tracing
```

A predicate is an Observation-layer decision. It is not a query filter in Prometheus, not a retention policy in a trace backend, and not a sampling policy in a tracing SDK.

## 2. ObservationPredicate vs. ObservationFilter

| Extension point | Role | Question |
| --- | --- | --- |
| ObservationPredicate | Accepts or rejects an observation before its lifecycle is processed as a normal observation | Should this operation be observed? |
| ObservationFilter | Modifies the context after the observation is created, typically to normalize/add metadata | What data should be added or normalized on kept observations? |
| ObservationConvention | Defines names and key-values per instrumentation conventions | What name/tags should describe this observation? |
| Tracing sampler | Decides whether a span/trace is recorded or exported by the tracing SDK | Should this trace be sampled? |

Do not use a predicate to replace a convention or filter if the goal is just to rename or normalize metadata. Conversely, do not use an `ObservationFilter` to try to drop an operation that instrumentation should not record.

## 3. API and registering predicates

In Micrometer Observation, a predicate is registered on `ObservationRegistry` through its observation configuration. Exact APIs may vary slightly across versions; a common method is `observationConfig().observationPredicate(...)`.

Example predicate excluding observations prefixed with `internal.`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ObservationConfiguration {

    @Bean
    ObservationPredicate skipInternalObservations() {
        return (name, context) ->
                name == null || !name.startsWith("internal.");
    }
}
```

The example above illustrates the predicate idea; verify how your Spring Boot/Micrometer version collects `ObservationPredicate` beans and registers them with the registry. In an auto-configured Spring Boot application, predicate beans can be detected and applied by Boot. If you construct an `ObservationRegistry` manually, you must register the predicate on that registry; declaring a bean in the context does not automatically configure manually constructed registries.

Direct registration at the registry level (illustrative API):

```java
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationPredicate((name, context) ->
                name == null || !name.startsWith("internal."));
```

Do not configure the same predicate across multiple registries and then test a different registry from the runtime one. Tests must obtain the exact bean/registry that instrumentation actually uses.

## 4. Writing stable predicates

Predicates should rely on stable observation names and context types/metadata. Avoid relying on arbitrary request data or values that change per call.

Examples of suitable conditions:

- Skip observations whose names belong to an `internal.` namespace.
- Skip a specific type of health check with a well-defined context/type.
- Keep key business and dependency observations.
- Apply policy only to a known group of instrumentations.

Avoid filtering on full URLs with dynamic query parameters; using user IDs, tenant IDs, or request IDs as conditions creating unbounded rules; assuming every observation shares the same context subtype; relying on exception messages or payloads; or using span/observation names with dynamic suffixes as long-term policy.

Example predicate checking context type:

```java
ObservationPredicate predicate = (name, context) -> {
    if (context == null) {
        return true;
    }

    if (context instanceof HealthCheckObservationContext) {
        return false;
    }

    return name == null || !name.startsWith("internal.");
};
```

Here `HealthCheckObservationContext` is an illustrative application-defined context type, not a built-in Micrometer class. In real code, replace it with the concrete context type provided by your application's instrumentation. Check for `null` and subtype before casting so the predicate never throws inside the instrumentation path.

## 5. Testing a predicate as a standalone function

If predicate logic has multiple branches, extract a dedicated factory or class so it can be unit tested directly. Unit tests should cover:

1. Observation names in the rejected group.
2. Observation names in the accepted group.
3. Null or empty names per defined policy.
4. Null context if the API/call path allows it.
5. Context subtypes filtered specifically.
6. Unrelated context subtypes still accepted.
7. Names resembling the prefix that do not belong to the excluded namespace.

Example:

```java
class InternalObservationPredicate implements ObservationPredicate {
    @Override
    public boolean test(String name, Observation.Context context) {
        return name == null || !name.startsWith("internal.");
    }
}
```

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class InternalObservationPredicateTest {

    private final InternalObservationPredicate predicate =
            new InternalObservationPredicate();

    @Test
    void rejectsInternalObservation() {
        assertThat(predicate.test("internal.cache.lookup",
                new Observation.Context())).isFalse();
    }

    @Test
    void acceptsBusinessObservation() {
        assertThat(predicate.test("order.submit",
                new Observation.Context())).isTrue();
    }

    @Test
    void acceptsNameWithoutInternalPrefix() {
        assertThat(predicate.test("internalized.operation",
                new Observation.Context())).isTrue();
    }

    @Test
    void acceptsNullNameAccordingToPolicy() {
        assertThat(predicate.test(null,
                new Observation.Context())).isTrue();
    }
}
```

This is a JUnit/AssertJ example; context constructors and APIs must match the Micrometer version in your dependency management. If your version/interface requires a different context setup, use the corresponding test context fixture. What matters is testing prefix boundaries and the null branch according to the chosen policy.

## 6. Testing with ObservationRegistry and handlers

Unit testing the predicate does not prove the runtime registry actually applies it. Add registry-level tests to verify lifecycle and handler behavior.

You can register a test handler counting starts/stops:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

class CountingObservationHandler
        implements ObservationHandler<Observation.Context> {

    final AtomicInteger starts = new AtomicInteger();
    final AtomicInteger stops = new AtomicInteger();

    @Override
    public void onStart(Observation.Context context) {
        starts.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stops.incrementAndGet();
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }
}
```

The test can create a registry, register the predicate and handler, and then run two observations:

```java
ObservationRegistry registry = ObservationRegistry.create();
CountingObservationHandler handler = new CountingObservationHandler();

registry.observationConfig()
        .observationPredicate((name, context) ->
                name == null || !name.startsWith("internal."));
registry.observationConfig().observationHandler(handler);

Observation.createNotStarted("order.submit", registry)
        .observe(() -> {});

Observation.createNotStarted("internal.cache.lookup", registry)
        .observe(() -> {});

assertThat(handler.starts).hasValue(1);
assertThat(handler.stops).hasValue(1);
```

This is an integration-test sketch. Handler APIs, predicate chaining, and no-op behavior must match the version in use. The key check is that accepted observations flow through the handler while rejected observations do not trigger normal observation callbacks. If using multiple handlers, check each relevant handler rather than counting only one.

## 7. Verifying the impact on metrics

In Spring Boot, metrics handlers typically turn observations into timers/counters or meters according to conventions. If a predicate drops an observation, the associated meter will not be updated by that observation.

A metrics test should verify that kept observations cause the meter to appear or increment; rejected observations do not increment the meter count; meter names and tags remain stable per convention; no new series are created for request IDs, user IDs, or dynamic URLs; and a rejected observation does not accidentally drop an important business metric.

Example using `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

// Attach the metrics handler as supported by your Micrometer version.
// Register the predicate on this same registry before running observations.
```

The snippet only sketches the setup because attaching `DefaultMeterObservationHandler` and conventions depends on version. In projects, prefer configuring handlers like production or using a Spring Boot test context to verify actual auto-configuration.

Do not assert meter names purely by guessing. Read the registry after running the test and confirm meter names/tags for your Micrometer version and conventions.

## 8. Predicates do not replace tracing sampling

`ObservationPredicate` and a tracing sampler can both affect observed data, but at two different layers:

| Scenario | Predicate | Tracing sampler |
| --- | --- | --- |
| Exclude internal observations | Can drop observations before handlers | Not its primary purpose |
| Keep metrics but drop traces | Unsuitable if it drops the whole observation | Can sample traces/spans per tracing setup |
| Keep traces but skip metrics | Requires dedicated handler/registry design or policy | Sampler only controls tracing |
| Reduce trace volume | Can drop the entire observation and all handlers | Sampler selects traces per policy |
| Drop meters by convention | Can drop observations | Sampler does not govern metrics |

If the requirement is to keep metrics while reducing trace volume, configure the tracing sampler or a tracing-specific policy rather than dropping the entire observation. If a predicate returns `false` before handlers receive the observation, both metrics and tracing can be affected.

Tests must verify the exact goal: a filtered observation, a sampled-out span, and an export failure are three distinct states. A trace missing from the backend does not automatically prove the predicate dropped the observation.

## 9. Combining multiple predicates

An application may receive multiple predicates from auto-configuration and custom beans. Combination order, short-circuit behavior, and registration depend on API/version. Do not assume execution order solely from bean declaration order.

When you have multiple policies, group related logic into a clearly named predicate or check ordering via the mechanism supported by the framework. Test cases where one predicate accepts and another rejects; multiple predicates all accept; prefixes overlap; specific vs. general context types; and environment-specific policies.

Avoid creating predicates with confusing conflicting conditions, such as one predicate rejecting `http.server.requests` while another tries to keep all HTTP observations. Document policies clearly and test actual execution order.

## 10. Testing Spring Boot auto-configuration

A `@SpringBootTest` or context runner test can verify that Boot applies predicate beans to the auto-configured registry. This matters because predicate unit tests do not verify wiring.

Points to check:

1. The predicate bean is present in the application context.
2. The `ObservationRegistry` injected into instrumentation is the expected registry.
3. Observations created by real Spring components go through that registry.
4. The test handler receives accepted observations.
5. The handler does not receive rejected observations.
6. Manually created registries are not confused with the auto-configured registry.
7. Test profiles/configuration reflect environment policies.

If the application context contains multiple registries, log or inspect bean identity in the test to confirm which registry the component actually uses. Do not merely assert the predicate bean exists and conclude all instrumentation is filtered.

## 11. Negative cases and common pitfalls

| Pitfall | Consequence | How to verify |
| --- | --- | --- |
| Predicate prefix too broad | Loss of business metrics/traces | Test boundaries and similar names |
| Dynamic URL in rule | Fragile rule, may fail to match route template | Use stable names/contexts |
| Unchecked context subtype cast | `ClassCastException` inside instrumentation | Check `instanceof` and `null` |
| Predicate registered on wrong registry | Runtime is not filtered | Verify bean identity and actual instrumentation |
| Confusing predicate with sampler | Drops metrics when only aiming to reduce traces | Test metrics and tracing separately |
| Unclear ordering across multiple predicates | Unexpected results | Check chaining/order per version |
| Test only calls predicate method directly | Misses Spring wiring bugs | Add registry/context tests |
| No-op path untested | Downstream code assumes context is always present | Test instrumentation when predicate returns `false` |

Some instrumentation code may look up the current observation/span or rely on context. When a predicate rejects an observation, ensure application code does not assume a current observation always exists. Never use an observation to store mandatory business state.

## 12. Practical policy example

Suppose a service wants to ignore health probes and internal cache operations while keeping HTTP server requests and business operations:

```java
ObservationPredicate productionPredicate = (name, context) -> {
    if (name == null) {
        return true;
    }

    if (name.startsWith("internal.cache.")) {
        return false;
    }

    if (name.startsWith("http.server.requests") &&
            context instanceof HealthProbeContext) {
        return false;
    }

    return true;
};
```

`HealthProbeContext` is an illustrative context type. Actual HTTP server observation context types depend on your Spring/Micrometer version; health probes can be identified by URI/route or metadata added by conventions. Do not invent a fake context class and expect auto-instrumentation to use it automatically.

If health probes must be excluded by route, use stable route templates/metadata rather than comparing raw URIs containing ports, query strings, or path variables. Test both the exact health route and similar business routes to avoid false positives.

In many systems, keeping separate health probe metrics is still useful for tracking probe latency/failures. You can use distinct tags/names or dashboard filters instead of dropping the entire health observation. Base the decision on operational goals.

## 13. Case study exercise

A Spring Boot application has a custom predicate:

```java
return !name.startsWith("http.");
```

After deployment, dashboards no longer show HTTP server request metrics. The team only wanted to ignore a health probe endpoint because probes are called very frequently.

**Questions:**

1. Why does the current predicate drop all HTTP observations?
2. Which prefix or context should replace the rule?
3. How do you test that health observations are excluded while business routes are kept?
4. If you only want to reduce tracing for health probes while keeping metrics, which layer should you change?
5. What should you verify to be sure the predicate bean is applied to the runtime registry?

**Analysis hints:**

- `startsWith("http.")` rejects every observation in the `http` namespace, including server/client requests depending on convention.
- The rule should identify the health route via route template or stable context metadata, checking for null and avoiding raw dynamic URLs.
- Test at least one health observation and one business HTTP observation; use a handler/registry to verify callbacks, then test metrics output.
- To keep metrics while reducing traces, configure a tracing sampler or tracing-specific policy; do not drop the whole observation.
- Use a Spring Boot context test, obtain the actual `ObservationRegistry`, and verify handlers receive or skip observations per policy.

### Completion checklist

| Topic | Able to explain/verify |
| --- | --- |
| Predicate semantics | Understand `true`/`false` and filter point |
| Context/name | Use stable names and contexts |
| Registration | Register on the right `ObservationRegistry` |
| Unit tests | Test accepted, rejected, null, and prefix boundaries |
| Handler tests | Verify lifecycle callbacks |
| Metrics tests | Check meters/counts/tags |
| Tracing distinction | Distinguish predicate from sampler and exporter |
| Multiple predicates | Check ordering/chaining per version |
| Spring Boot wiring | Verify auto-configuration and runtime registry |
| No-op path | Do not assume a current observation always exists |

**Takeaway:** `ObservationPredicate` decides whether an observation continues through the registry or is skipped. Base predicates on stable names and contexts; check for null/subtypes and avoid overly broad rules. Unit tests only verify logic, while registry/handler and Spring Boot context tests confirm wiring and real effects on metrics/tracing. Distinguish filtered observations from tracing sampling and export failures: if you want to keep metrics while reducing traces, adjust tracing policy instead of dropping the whole observation.
