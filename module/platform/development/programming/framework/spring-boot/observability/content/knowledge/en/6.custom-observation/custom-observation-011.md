# Avoiding double instrumentation of the same block in Spring Boot Observability

> **Chapter:** Custom observation  
> **Lesson:** Avoiding double instrumentation of the same block  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production.

## 1. The problem: one unit of work measured as two

Suppose an ordering service processes **100 order creation requests**. In a healthy setup, metrics record 100 executions of the `orders.checkout` business operation. Yet after adding a custom observation, dashboards unexpectedly report **200 checkouts** despite zero new traffic. In traces, the same execution block appears as two nearly identical spans.

The culprit may be **double instrumentation**: two mechanisms simultaneously observing **the same unit-of-work boundary with identical semantics**. For example:

- Spring Boot already creates an observation for the HTTP server, yet a developer adds another observation re-measuring the entire same request in the controller.
- A method is AOP-instrumented via `@Observed`, while its method body also calls `Observation.createNotStarted(...)` around the exact same block.
- A metrics or span-creating `ObservationHandler` is registered twice on the same registry.
- The application enables two instrumentation mechanisms for the same library simultaneously (such as an automatic integration alongside equivalent manual instrumentation).
- An operation carries both `@Timed` and `@Observed` with overlapping names/semantics when both the aspect and meter handler are active.

This bug inflates collection costs, distorts throughput, error rates, latency, span counts, and breaks SLI/SLO alerting. If the same observation is recorded twice into a Timer with identical tags, **`_count` can double**. If the two mechanisms record different tag sets, data lands in two separate time series while still double-counting when summed globally.

**What must be protected is the semantic boundary of measurement**: for any single execution of a defined unit of work, exactly one mechanism owns the primary measurement. Seeing two nested spans or two metric types is not automatically a bug: *genuinely distinct* operations within a request should be observed separately when useful.

## 2. Distinguishing double instrumentation from valid nested observations

A single HTTP request can encompass several operations worth measuring:

~~~mermaid
flowchart TD
    A["HTTP POST /api/orders — framework-created server observation"] --> B["orders.checkout — business observation"]
    B --> C["inventory.reserve — stock reservation observation"]
    B --> D["payment.authorize — payment call observation"]
    C --> E["db.query — database instrumentation if enabled"]
    D --> F["http.client.requests — HTTP client instrumentation if enabled"]
~~~

In this example, the HTTP server, checkout business logic, stock reservation, and outbound call have **different scopes, purposes, and names**. They intentionally create nested Timers or spans. Span durations enclose and overlap one another, so **never sum all span durations directly** as total request duration.

Conversely, if two observations both start right upon entering `checkout()`, stop right upon exiting `checkout()`, share the name `orders.checkout`, and both represent "one checkout," that is typically double instrumentation.

| Situation | Classification | Reason |
| --- | --- | --- |
| HTTP server observation and `inventory.reserve` step observation | Valid | Different boundaries and questions |
| `@Observed("orders.checkout")` and manual `orders.checkout` both wrapping the entire method | Duplicate | Measuring the same business operation twice |
| One Observation triggering both a meter handler and a tracing handler | Valid | One instrumentation source producing two signal types |
| Two `DefaultMeterObservationHandler` instances processing one observation | Risk of duplication | Same meter-recording responsibility registered twice |
| Checkout parent span and HTTP client child span | Valid | Parent represents business logic; child represents dependency |
| Two similar HTTP server spans from two agents/instrumentations hooking the request | Investigate | Likely double-measuring the request boundary |

The reliable way to diagnose is checking how many observations with identical semantics **one execution of work** produces, then inspecting which mechanism created each observation. Looking solely at span names or count charts is insufficient.

## 3. Map of what Spring Boot may already auto-instrument

With Spring Boot, Actuator, Micrometer Observation, and compatible libraries, the framework automatically instruments several operations. Exact coverage depends on your Spring Boot version, starters, clients, and auto-configuration.

| Component | Typical instrumentation | What to consider before adding custom |
| --- | --- | --- |
| HTTP server (Spring MVC/WebFlux) | Request observation, HTTP server metrics, and potentially server spans | Do not re-wrap the entire controller merely to get request latency |
| HTTP client (RestClient, RestTemplate, WebClient via instrumented builders/config) | Client request observation, propagation headers, HTTP client metrics/spans | Do not add another observation with the same meaning per HTTP exchange if already measured |
| Tracing | Tracing handlers creating spans from Observations; bridge to tracer | Do not register a second set of tracing handlers on the same registry |
| MeterRegistry | Metrics handler turning Observations into Timers/metrics | Do not register meter handlers twice |
| Messaging, scheduling, or supporting libraries | May include built-in instrumentation | Verify actual runtime output before wrapping the exact same boundary |
| Business services | Usually up to developers to decide what business steps to measure | Custom observations add value when representing meaningful business stages |

A common HTTP server metric name is `http.server.requests`; in Prometheus, Timers typically export `http_server_requests_seconds_count` and `http_server_requests_seconds_sum`. These are **convention-based examples**, not a guarantee that every version uses those exact names.

**How to verify active instrumentation:** send a test request, inspect `/actuator/metrics` and `/actuator/prometheus`, check the tracing UI if present, and compare against your code entry/exit points. Know exactly what the framework already measures before adding instrumentation.

## 4. Classic mistake: wrapping one method with both `@Observed` and manual Observation

### 4.1. Flawed design example

When `ObservedAspect` is active, `@Observed` creates an observation around the method invocation via Spring AOP. In the snippet below, the developer also creates **another observation** with the same name and same boundary inside the method:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.annotation.Observed;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class DuplicateCheckoutService {
    private final ObservationRegistry registry;

    public DuplicateCheckoutService(ObservationRegistry registry) {
        this.registry = registry;
    }

    @Observed(name = "orders.checkout", contextualName = "checkout")
    public <T> T checkout(Supplier<T> work) {
        // Avoid: @Observed already wraps this exact checkout method.
        Observation duplicate = Observation.createNotStarted(
                "orders.checkout", registry).start();

        try (Observation.Scope scope = duplicate.openScope()) {
            return work.get();
        } catch (RuntimeException ex) {
            duplicate.error(ex);
            throw ex;
        } finally {
            duplicate.stop();
        }
    }
}
~~~

When the aspect is enabled and calls go **through the Spring proxy**, a single `checkout(...)` invocation creates two nested observations sharing the same name:

~~~mermaid
sequenceDiagram
    participant Caller
    participant AOP as ObservedAspect
    participant Service as checkout()
    participant Registry
    Caller->>AOP: checkout(work)
    AOP->>Registry: start orders.checkout (1)
    AOP->>Service: invoke method
    Service->>Registry: start orders.checkout (2)
    Service->>Service: work.get()
    Service->>Registry: stop orders.checkout (2)
    Service-->>AOP: return
    AOP->>Registry: stop orders.checkout (1)
    AOP-->>Caller: result
~~~

Depending on metadata from the annotation vs. the manual observation, the two recordings may land in different tag sets. Verify actual meters/traces rather than assuming every query doubles by exactly 2x.

`@Observed` requires active AOP instrumentation—typically an `ObservedAspect` bean—to take effect on methods. If the aspect is inactive or an internal self-invocation bypasses the proxy, the annotation is skipped and only the manual observation runs; that **does not make duplicate registration harmless** in other environments.

### 4.2. Fix A: use `@Observed` as the single measurement source

When you only need duration, error status, and operation naming, the annotation is concise:

~~~java
import io.micrometer.observation.annotation.Observed;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    @Observed(name = "orders.checkout", contextualName = "checkout")
    public <T> T checkout(Supplier<T> work) {
        return work.get();
    }
}
~~~

This illustrates usage when **`ObservedAspect` is already registered and aligned with Spring AOP**. There is no need for a manual observation inside the same method.

If an application needs aspect configuration where none exists yet, declare it **once**:

~~~java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ObservationAspectConfiguration {
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Check upfront whether an `ObservedAspect` bean already exists in the application. Never add a second bean merely because metrics are missing—the issue could lie in proxies, scopes, handlers, or exporters.

### 4.3. Fix B: manage one manual Observation

When dynamic metadata, business events, or outcome classification are required, drop `@Observed` and choose **one manual observation**:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry registry;

    public CheckoutService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T checkout(String channel, Supplier<T> work) {
        Observation observation = Observation.createNotStarted(
                "orders.checkout", registry)
            .lowCardinalityKeyValue("channel", normalizeChannel(channel))
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = work.get();
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String input) {
        if ("web".equals(input)) return "web";
        if ("mobile".equals(input)) return "mobile";
        return "other";
    }
}
~~~

This pattern performs one `start()` and `stop()` per business call, closes the scope via `try-with-resources`, and reports errors to handlers on exception. `channel` is normalized to a bounded set to avoid cardinality explosion; `outcome` is added once the result is known, prior to stop.

Special note for `CompletableFuture` or asynchronous work: never call `stop()` right after submitting work if your goal is measuring until real completion. Finish the observation when callbacks receive the final result and propagate context using your executor/Reactor mechanism.

## 5. Avoid re-measuring HTTP server requests already tracked by the framework

Example Spring MVC controller:

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    // May overlap with automatic HTTP request instrumentation.
    @Observed(name = "http.server.requests")
    @PostMapping("/api/orders")
    public String createOrder() {
        return "created";
    }
}
~~~

This annotation can create an extra observation using the default server request name when `ObservedAspect` is active. However, Spring MVC also runs its own HTTP server instrumentation. Two measurements sharing the same name do not guarantee matching conventions or tags; feeding both into one Timer causes inconsistent tags, confusing reports, or double-counted aggregations.

A cleaner design:

~~~java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final CheckoutService checkoutService;

    public OrderController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @PostMapping("/api/orders")
    public String createOrder() {
        // HTTP server is instrumented by Spring when appropriately configured.
        return checkoutService.checkout("web", () -> "created");
    }
}
~~~

Here, the HTTP server observation measures the request boundary while `orders.checkout` measures a **distinct business step**. They nest cleanly while answering separate questions: how slow was the HTTP request, and how long did checkout logic take? To enrich the existing HTTP observation, use framework customization APIs such as `ServerRequestObservationConvention` or supported instrumentation hooks instead of creating a second observation for the same request.

Never rename `http.server.requests` to an arbitrary string just to hide duplicates on a dashboard; fix **who owns the measurement boundary**.

## 6. Duplicate handlers are not the same as duplicate Observations

Even when business code creates only **one** `Observation`, telemetry can still be recorded twice if the same handler responsibility is registered twice.

Standalone Micrometer illustration:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

void configureWrongly(
        ObservationRegistry observationRegistry,
        MeterRegistry meterRegistry) {

    observationRegistry.observationConfig()
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry))
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
}
~~~

Both handlers aim to record Timers into the same `MeterRegistry`. Depending on implementation and tag sets, each handler can record a separate sample for one observation, inflating `count`.

Proper configuration when manually managing the full registry:

~~~java
void configureOnce(
        ObservationRegistry observationRegistry,
        MeterRegistry meterRegistry) {

    observationRegistry.observationConfig()
        .observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
}
~~~

**In Spring Boot with Actuator, do not use either snippet above to register an extra meter handler when the framework already registers one.** Normally inject the Spring Boot-configured `ObservationRegistry` and add custom handlers only for genuinely new behavior. Two common ways duplicate registration occurs:

1. An `ObservationHandler` `@Component` or `@Bean` is automatically registered by Boot.
2. That exact same instance—or an equivalent handler—is added again via `ObservationRegistryCustomizer` or manual `observationConfig().observationHandler(...)`.

Duplicate tracing handlers can likewise emit two spans per observation. Therefore separate two distinct bugs: **two observations tracking one unit of work** vs. **one observation processed by two handlers performing the same job**. Fixes live at different layers.

## 7. All-matching and first-matching: combining signals properly

A single `Observation` can and should generate both **metrics** and **tracing**. That is signal coordination, not duplication.

| Mechanism | Meaning | Risk when misused |
| --- | --- | --- |
| `AllMatchingCompositeObservationHandler` | Runs all matching child handlers | Two handlers with the same role can record duplicates |
| `FirstMatchingCompositeObservationHandler` | Picks the first matching child handler in order | An overly broad handler can shadow specialized ones, dropping signals |
| Multiple independent handlers on the registry | Each handler serves its own function | Ensure the same responsibility is not registered twice |

For tracing, `FirstMatchingCompositeObservationHandler` typically selects among:

- `PropagatingSenderTracingObservationHandler` for outbound contexts sent to another service.
- `PropagatingReceiverTracingObservationHandler` for inbound contexts received from another service.
- `DefaultTracingObservationHandler` for normal internal spans.

Place specialized sender/receiver handlers ahead of the default fallback; never put multiple tracing handlers in an all-matching composite to create spans for the same context. Conversely, never lump meter handlers and tracing handlers into **the same first-matching composite** if you want both signals: once one matches, the other is skipped.

~~~mermaid
flowchart LR
    A["Single Observation"] --> B["Meter handler"]
    A --> C["First-matching tracing group"]
    B --> D["One semantically clean set of metrics"]
    C --> E{"Context?"}
    E -->|Sender| F["Tracing sender"]
    E -->|Receiver| G["Tracing receiver"]
    E -->|Other| H["Default tracing"]
    F --> I["Appropriate span"]
    G --> I
    H --> I
~~~

Special case: `TracingAwareMeterObservationHandler` combines meters with the tracer to support exemplars on compatible stacks. When using it, check **which meter responsibility it replaces** so you do not keep an independent meter handler writing the same data alongside it.

## 8. One measurement source per unit of work: ownership map

Before writing custom observations, sketch a small table defining boundaries and measurement owners. For an ordering service:

| Boundary | Primary measurement owner | Signal name / type | Write custom observation? |
| --- | --- | --- | --- |
| HTTP server receiving `POST /api/orders` | Spring MVC instrumentation | `http.server.requests` and server span if tracing enabled | No, not for the same request boundary |
| `checkout` business rule logic | Business service | `orders.checkout` | Yes, choose AOP or manual |
| HTTP client calling `inventory-api` | HTTP client instrumentation if client configured properly | HTTP client request, client span | No, do not re-measure the same HTTP exchange |
| Custom pricing calculation | Business service | `orders.pricing` | Yes, if separate breakdown is needed |
| JDBC/database calls | Corresponding instrumentation when enabled | DB spans/metrics per integration | Add only for a distinct business stage |

This ownership model also guides **meaningful metric names and bounded tag sets**. Never name a custom observation after an existing framework name like `http.server.requests` if its semantics are really checkout processing. Avoid creating multiple observations with nearly identical names and overlapping scopes, which makes dashboards hard to read and corrupts aggregations.

Some operations legitimately occur **multiple times** in a single request: checkout calls inventory twice due to retries, or one request runs two SQL queries. In those cases, the operation's count legitimately exceeds the HTTP request count without being an instrumentation bug. Always clarify what "one count" means for each measurement.

## 9. Verifying with metrics: execution counts and tags

### 9.1. Preparing a controlled test

Assume a single-instance test environment with zero background traffic, no retries, and one request triggering `checkout()` exactly once. Send **10 successful requests** and compare HTTP server metrics against the business metric.

Never compare `http.server.requests` directly 1:1 against `orders.checkout` in multi-route production environments: some HTTP requests may skip checkout or invoke it multiple times. A 1:1 check is valid only when the test scenario strictly guarantees a 1:1 mapping.

### 9.2. Actuator and Prometheus endpoints

In Spring Boot with Actuator and the Prometheus registry:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Example when running on port 8080:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/orders.checkout
curl http://localhost:8080/actuator/prometheus
~~~

Inspect `measurements`, `availableTags`, and the Prometheus series. An `orders.checkout` Timer typically produces `orders_checkout_seconds_count`, `orders_checkout_seconds_sum`, and `_bucket` only if histograms are enabled. Exact names and tags depend on registry, version, and conventions, so always inspect exporter output before writing queries.

**Note:** `/actuator/metrics` reflects current in-memory registry counts at query time; Prometheus also runs on a scrape interval. After generating requests, wait for a scrape before checking backend graphs. In local tests, the before/after delta is stronger evidence than glancing at an accumulated `count` from earlier runs.

### 9.3. PromQL queries to spot duplication

If the exporter emits `orders_checkout_seconds_count`, the checkout rate over a 5-minute window is:

~~~promql
sum(rate(orders_checkout_seconds_count[5m]))
~~~

Compare it with the HTTP request rate on the corresponding route:

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    uri="/api/orders",method="POST"
  }[5m])
)
~~~

If `orders.checkout` runs once per request, both rates are **expected to align closely** once scraped under controlled conditions. A ratio near 2x may signal duplication, though it could also stem from retries, a controller calling checkout twice, internal requests, or differing measurement semantics.

If two instrumentations emit series with different `channel` or `outcome` labels, summing across all tags inflates counts; drill down by tags:

~~~promql
sum by (channel, outcome) (
  rate(orders_checkout_seconds_count[5m])
)
~~~

Do not assume every exporter carries those labels—the query only works when your code attaches them. For exact verification on a single test run, inspect before–after Timer/counter deltas directly in the registry and cross-check a concrete request.

## 10. Verifying with tracing: spotting duplicate spans

Tracing offers a second perspective: one request exports a trace containing spans along business and dependency boundaries. When suspecting double instrumentation:

1. Pick a request whose trace was **sampled** and exported successfully; note its trace ID from logs or UI.
2. Open the trace and inspect parent–child hierarchy, span names, start times, and durations.
3. Look for two spans with the same name and nearly identical boundaries—for instance, both named `orders.checkout` wrapping the same code execution.
4. Identify the origin of each span: framework instrumentation, `@Observed`/AOP, manual observation, tracing bridge, agent, or custom handler.
5. After removing the duplicate source, run an equivalent request to confirm span counts and parent–child structure.

~~~mermaid
flowchart TD
    A["HTTP server span"] --> B["orders.checkout (AOP)"]
    B --> C["orders.checkout (manual)"]
    C --> D["HTTP client: inventory"]
    E["Likely duplicate"] -.-> B
    E -.-> C
~~~

If both AOP and manual observations wrap the same method, back-to-back `orders.checkout` spans are a strong warning sign. Yet **two identically named spans alone do not prove a bug**: two legitimate retries or two distinct code blocks can share a name. Use timestamps, call paths, events, and instrumentation origins to tell them apart.

Sampling can hide duplicates in the trace backend. Failing to spot duplicate spans on one request is **not enough** to conclude there is no duplication. In a test environment, use consistent sampling or in-memory inspection tools while keeping production sampling policies intact.

## 11. Verifying at handler level with a minimal registry

To isolate **instrumentation logic** from networking/exporters, count callbacks on a standalone `ObservationRegistry`. Example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public final class DuplicateHandlerDemo {
    static final class CounterHandler
            implements ObservationHandler<Observation.Context> {

        private final AtomicInteger stops;

        CounterHandler(AtomicInteger stops) {
            this.stops = stops;
        }

        @Override
        public boolean supportsContext(Observation.Context context) {
            return "orders.checkout".equals(context.getName());
        }

        @Override
        public void onStop(Observation.Context context) {
            stops.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger stops = new AtomicInteger();

        // Register only one handler.
        registry.observationConfig()
            .observationHandler(new CounterHandler(stops));

        for (int i = 0; i < 10; i++) {
            Observation.createNotStarted("orders.checkout", registry)
                .observe(() -> {
                    // Single business execution, no exporter needed.
                });
        }

        System.out.println(stops.get()); // Expected: 10
    }
}
~~~

This snippet only checks `onStop` callback counts, not exported metric series or spans. To reproduce duplicate handler registration, register **two handlers incrementing the same counter**: total callbacks jump to 20 for 10 observations. That proves the bug lies at the handler layer, independent of Prometheus or tracing.

In a real Spring Boot app, write integration tests verifying registry configuration and a full request flow; never swap in a fresh registry inside a service merely to make counts "look right" in tests. A standalone registry lacks the application's configured handlers, predicates, filters, and tracers.

## 12. When counts double without double instrumentation

Several valid causes produce similar symptoms:

| Symptom | Possible valid explanation | How to distinguish |
| --- | --- | --- |
| `orders.checkout` count is double HTTP POSTs | Each request calls checkout twice | Inspect call paths and correlated business logs |
| Client shows multiple HTTP spans | Retries or redirects generated extra HTTP exchanges | Check outbound request count and test with retries disabled |
| Two instances show identical counts | Each instance handles its own traffic; cluster `sum` adds normally | Group by `instance`, `pod`, or deployment labels |
| Both Timer count and Counter count exist | One operation measured by two metrics with **different names and purposes** | Avoid summing two metrics as one request unit |
| Business latency and HTTP server latency both rise | Two measurements of nested boundaries | Never add nested durations as independent costs |
| Traces are sparser than metrics | Sampler exports only a subset of traces | Check sampling before suspecting broken tracing handlers |
| One exporter ships to two collectors | Duplicate ingestion/pipeline in backend, not double Observation creation | Compare counts at app/registry vs. backend |
| Annotated method emits no span | Aspect inactive or internal call bypassed Spring proxy | Check AOP/proxy before immediately adding manual code |

A "double measurement" in real operations can also reflect **two real events**. For example, checkout might perform a validation step and a retry step both calling the same API; if your metric counts *attempts*, two counts are accurate. If your metric counts *logical checkouts*, define it at a higher boundary.

Therefore, before deleting instrumentation, document the **counting unit**: HTTP request, business operation, attempt, message delivery, or database call.

## 13. Safe remediation workflow ordered by root cause

1. **Define the boundary:** specify where "one `orders.checkout`" begins and ends; agree on metric name and required tags.
2. **Inventory measurement sources:** framework auto-instrumentation, `@Observed`, `@Timed`, custom `Observation`, agents, interceptors, meter/tracing handlers, and registry customizers.
3. **Classify the duplication:** two observations on the same boundary, one observation with two handlers doing the same job, or data duplicated downstream of exporters.
4. **Pick one owner:** use built-in instrumentation where it already covers the boundary; use one custom observation for uncovered business steps. If using annotations, do not wrap manually over the same scope.
5. **Fix at the source:** remove the duplicate annotation/manual wrapper or duplicate handler bean/registration. Never simply rename the metric or add query filters to mask the symptom.
6. **Verify behavior:** run a known fixed workload; verify before–after Timer deltas, span counts/parent–child links on sampled traces, and per-request logs.
7. **Confirm downstream impact:** ensure request latency, error rates, custom business metrics, propagation, and metrics–logs–traces correlation remain accurate.

In large applications, fixing duplication impacts dashboards and alerts built on the old metric. If a duplicated metric previously fed SLOs, revisit formulas and thresholds afterward because the corrected data reflects accurate semantics. Avoid comparing pre/post periods without annotating the instrumentation change.

### Caution regarding `ObservationPredicate`

`ObservationPredicate` lets you conditionally drop observations, yet it should not be your first tool to cure double instrumentation. A broad name-based predicate can accidentally drop valid observations, erasing metrics and traces for other operations sharing that name. Always find and remove **the duplicate instrumentation source** first; use predicates only for deliberate policies specifying which observations to suppress.

## 14. Production scenario: checkout counts jump 100% after deploy

**Context.** The `order-api` service normally handles ~40 checkout requests/sec with ~0.5% errors. After adding an annotation to monitor business flow, metrics show `orders.checkout` jumping to 80/sec while HTTP server traffic remains flat. Traces occasionally show two `orders.checkout` spans covering nearly the exact same span of execution.

**Investigation.** The team compares a retry-free test request against `checkout()`. The method already created a manual observation to attach `channel` and `outcome`, and `@Observed(name = "orders.checkout")` was newly added to the same method. With `ObservedAspect` active, every invocation creates two observations. Because the two observations can carry different tags, dashboards summing by metric name double-count.

**Resolution.** The team keeps the manual observation—since post-execution `outcome` classification is needed—and removes the annotation from the method. Sending 20 test requests and checking Timer count deltas, label sets, and sampled traces confirms `orders.checkout` returns to matching valid checkout requests with no duplicate span pairs. HTTP server instrumentation and dependency spans continue working normally.

**Lesson.** It was neither an exporter bug nor a sampling quirk; the root cause was **two instrumentation sources owning the same code block**. Assigning one owner per business boundary and verifying with a known-count test workload resolves it cleanly.

## 15. Hands-on exercises

### Exercise A — classify duplicate vs. valid

For each pair below, classify and explain:

1. Server span `POST /api/orders` and service span `orders.checkout`.
2. `@Observed("orders.checkout")` on a method whose body also runs manual `Observation.createNotStarted("orders.checkout", ...)` around the entire method body.
3. One `orders.checkout` observation handled by both a meter handler and a tracing handler.
4. Two `DefaultMeterObservationHandler` instances registered on one registry sharing the same `MeterRegistry`.
5. One client span for the initial request and one client span for a real retry after timeout.

Expected: cases 2 and 4 require fixing duplication; cases 1, 3, and 5 are generally valid when representing genuinely distinct operations or signals.

### Exercise B — refactor the service

Given a `CheckoutService` mixing `@Observed` and manual observation, pick **one** mechanism while guaranteeing:

- Full duration measurement for the synchronous operation.
- On error, `Observation` receives `error(ex)` (if manual).
- Tags `channel=web/mobile/other` and `outcome=success/error` when using manual control.
- Neither `orderId` nor `requestId` placed in metric labels.
- Scope closed and observation stopped across both success and failure paths.

### Exercise C — quantitative verification

In a test environment with zero background traffic, call the API exactly 50 times. Before and after the run:

1. Measure the delta in `http.server.requests` for that specific route.
2. Measure the delta in `orders.checkout` Timer count.
3. Open a sampled trace and inspect one business checkout span alongside real dependency spans.
4. Temporarily re-enable the duplicate instrumentation in the test environment to observe how metrics and traces change.
5. Remove the duplicate source and confirm counts return to true semantics.

Do not rely on PromQL before/after snapshots without accounting for `rate()` windows and scrape intervals. To verify exact event counts in a test, prefer in-memory counter/Timer counts or counter deltas over a controlled interval.

### Self-check questions

1. Why are two nested spans not necessarily a duplicate?
2. If `@Observed` appears inactive, what should you check before adding a manual observation?
3. When two meter handlers are registered for one observation, does the actual number of created observations increase?
4. Why can a `sum(rate(...))` query double even when the two time series carry different labels?
5. What problem does first-matching prevent for sender/receiver/default tracing handlers?
6. How does sampling affect your ability to spot duplicate spans?
7. Why can "fixing" duplication by renaming one metric hide the bug and corrupt dashboard semantics?
8. In a system with retries, how do you distinguish an "attempt" from a "logical business transaction"?

**Completion criteria:** ability to explain sources of duplicate instrumentation in Spring Boot; design one measurement owner per boundary; distinguish independent signals from duplicate observations; detect and resolve bugs across code, registries, metrics, and traces; and preserve proper tags/cardinality, context propagation, and sampling.

## 16. Key takeaways

- **One boundary, one primary instrumentation source.** A single observation producing multiple signals via appropriate handlers is not double instrumentation.
- Spring Boot Actuator may already instrument HTTP servers/clients and other integrations; check before re-wrapping the same code.
- Never combine `@Observed` and manual `Observation` on the same method if they measure the same semantics; likewise avoid registering duplicate meter/tracing handlers.
- **All-matching** coordinates distinct handler functions; **first-matching** picks one specialized tracing handler per context.
- Diagnose using controlled workloads, Timer count deltas, labels, trace waterfalls, and handler inventories; always distinguish real retries from duplicate measurement.
- After fixing, re-verify dashboards/SLOs and check propagation, cardinality, exporters, and sampling so observability signals remain accurately correlated.

## References

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
