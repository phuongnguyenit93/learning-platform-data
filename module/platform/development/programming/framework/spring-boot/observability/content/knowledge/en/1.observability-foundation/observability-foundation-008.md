# When Do You Need Custom Instrumentation in Spring Boot?

In the **SPRING_BOOT_OBSERVABILITY** module, observability is the ability to understand what an application is doing from **metrics, logs, and distributed traces**, especially when investigating errors, latency, and production behavior. Spring Boot Actuator and Micrometer supply many built-in measurements; **custom instrumentation** is deliberately adding measurements for behavior the system does not yet observe at the needed level. The decision to add instrumentation should start from a **specific operational or business question**, rather than simply wanting more data.

For example, a `POST /checkout` request takes 2 seconds. HTTP metrics tell you the endpoint is slow, and an HTTP trace might show one network call took 1.6 seconds, yet still leave unanswered: *was time spent in inventory checks, coupon validation, or payment authorization?* If those steps matter for diagnostics or SLOs, you need to instrument them directly.

## 1. Identifying Gaps in Built-In Signals

With the right dependencies and configuration, Spring Boot and Micrometer can automatically provide observability for many components, such as the HTTP server, supported HTTP clients, and various framework integrations. Actual coverage **depends on your Spring Boot version, libraries, client initialization style, and configuration**. Never assume every database query, background job, queue, or third-party library is already instrumented.

Example processing flow:

```text
POST /checkout                       <-- HTTP server observation usually built in
  ├─ validateCart()                  <-- Business rules: may be missing
  ├─ reserveInventory()             <-- Business step: may be missing
  ├─ authorizePayment()             <-- Business step: may be missing
  │    └─ POST /provider/authorize  <-- HTTP client observation may be built in
  └─ publishOrderConfirmed()        <-- Queue/events: depends on integration
```

Typically, you **do not need** another timer or span around all of `POST /checkout` if the framework already measures it accurately. However, you may need an observation named `payment.authorize` around payment authorization logic: its meaning remains stable even if you swap the HTTP provider for an SDK, and it lets you separate *approved*, *declined*, and *error* outcomes.

Check your dashboards, actual traces, and dependency instrumentation documentation before deciding what to add.

## 2. When Should You Add Instrumentation and When Shouldn't You?

| Situation | Decision | Why? |
| --- | --- | --- |
| Want total RPS, 5xx errors, or p95 latency on an endpoint already measured by Actuator | **Prefer built-in signals** | Re-measuring the same scope easily creates duplicate metrics/spans and extra cost |
| Need to separate durations of `validateCart`, `reserveInventory`, and `authorizePayment` | **Add Observations** at diagnostically valuable steps | HTTP metrics do not expose internal business structure |
| Want to count orders routed to manual review by reason | **Add a business counter** | This is a business event, not request latency |
| Background jobs, schedulers, batches, or consumers lack useful traces/metrics | **Consider instrumenting** task boundaries | You need duration, outcome, and correlation to the originating task |
| Need to distinguish two payment providers from a bounded set | **Add a low-cardinality key-value** | Lets you filter and compare latency/error rates by provider |
| Want to put `userId`, `orderId`, or full URLs on every time series | **Do not use as metric tags** | Tag combinations grow with data volume and introduce privacy risk |
| Only need one detail when investigating a specific transaction | **Prefer structured logs or suitable trace attributes** | No need to spawn new metric series per transaction |
| HTTP client already emits a child span; considering a second span for the exact same HTTP call | **Skip the duplicate span** | A new span helps only if it represents a distinct business boundary |

**Selection rule:** add instrumentation when it answers an open question, drives clear investigation or alerting actions, and carries acceptable cardinality/volume cost.

## 3. Picking the Right Tool for the Question

In Micrometer, the three signal types are related but do not fully replace one another:

| Goal | Suitable Tool | Example |
| --- | --- | --- |
| Measure **duration and outcome** of an operation; emit metrics and traces depending on config | `ObservationRegistry` + `Observation` | `payment.authorize` |
| Count a **business event** not tied to an operation's duration | `MeterRegistry` with `Counter` | `orders.manual_review` |
| Measure queue depth, active tasks, or current state | `Gauge` or stateful meter with clear lifecycle | Pending jobs count |
| Record diagnostic context, error reasons, or branching decisions | Structured logs | `outcome=declined reason=insufficient_funds` |
| Follow execution path and causality across services | Traces/spans and context propagation | Checkout → Payment → Provider |

**Observation** is an operation-level API. It flows through configured `ObservationHandler`s and conventions. Depending on setup, an observation may produce a metric, a span, both, or emit nothing externally. Therefore, merely calling `Observation.createNotStarted(...)` **does not prove** traces reached a backend or metrics were scraped; verify your registry, handlers, tracing bridge, and exporters in the target environment.

**MeterRegistry** fits when you genuinely need a specialized counter, timer, or gauge. Never create both an `Observation` and a manual `Timer` for the exact same operation with the same meaning: numbers can be double-counted in dashboards. To query reliable p95 across multiple instances, also configure histograms/percentiles compatible with your metrics backend.

## 4. Example: Instrumenting the Payment Authorization Business Boundary

Suppose the application already has domain types `PaymentGateway`, `PaymentRequest`, and `PaymentResult`. Use Spring's `ObservationRegistry` to measure the entire **payment authorization decision**, covering service processing and the gateway call; the observation name stays independent of the provider's physical endpoint.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentAuthorizationService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentAuthorizationService(
            ObservationRegistry observationRegistry,
            PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentRequest request) {
        // method() and provider() return enums with bounded value sets.
        String method = request.method().name().toLowerCase(java.util.Locale.ROOT);
        String provider = gateway.provider().name().toLowerCase(java.util.Locale.ROOT);

        Observation observation = Observation
                .createNotStarted("payment.authorize", observationRegistry)
                .contextualName("authorize payment")
                .lowCardinalityKeyValue("payment.method", method)
                .lowCardinalityKeyValue("payment.provider", provider);

        observation.start();
        try (Observation.Scope ignored = observation.openScope()) {
            PaymentResult result = gateway.authorize(request);
            observation.lowCardinalityKeyValue(
                    "outcome", result.approved() ? "approved" : "declined");
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

*`PaymentRequest`, `PaymentResult`, and `PaymentGateway` are illustrative domain types; substitute your project's actual types. The example focuses on the Observation lifecycle.*

Here:

1. `createNotStarted` creates the observation under a **stable name** free of transaction IDs; `contextualName` supplies a readable span name when supported by the tracing handler.
2. `start()` begins timing, and `openScope()` binds the observation to the current thread's scope so child operations inherit the parent context. `Scope` closes automatically.
3. `outcome=approved` or `declined` captures business results. A payment decline can be a valid outcome and **is not necessarily an exception**.
4. When a technical failure occurs, `error(ex)` records the error for configured handlers; the exception is rethrown to preserve program behavior.
5. `stop()` in `finally` ensures the measurement finishes on both success and failure paths.

If the HTTP client is auto-instrumented, the resulting trace can look like this:

```text
server: POST /checkout
  └─ custom: payment.authorize (outcome=approved)
       └─ client: POST /payments/authorize
```

The manual observation expresses **payment authorization business logic**; the HTTP client observation expresses the **network call**. Because these two measurements serve different purposes, they can coexist without duplicating semantics. If the provider times out, investigators can immediately tell whether latency sits in the gateway or internal logic. Seeing full parent/child spans still depends on tracing being enabled, sampling, and proper propagation.

### Using `@Observed` When the Boundary Is a Method

When you only need duration and errors around a Spring bean method, an annotation reduces `start/stop` boilerplate:

```java
import io.micrometer.observation.annotation.Observed;

@Observed(
    name = "pricing.calculate",
    contextualName = "calculate price",
    lowCardinalityKeyValues = {"component", "pricing"})
public PriceQuote calculate(PriceRequest request) {
    return pricingEngine.calculate(request);
}
```

This annotation requires active **AOP interception**, typically Spring AOP plus an `ObservedAspect` bean registered with `ObservationRegistry`; placing the annotation alone does not guarantee instrumentation. Example Spring Boot AOP configuration:

```java
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ObservedConfiguration {
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
```

With Spring proxy AOP, **internal calls from one method to another on the same object** (self-invocation) normally bypass the proxy, so the annotation may not apply. Also avoid double-wrapping HTTP/framework methods that are already instrumented. When you need dynamic outcome-dependent tags, domain-specific error handling, or complex scope management, the manual `Observation` API is usually clearer.

## 5. Naming Rules and Cardinality Management

Metric backends store data by tag combinations. With three tags having 4, 5, and 1,000 values respectively, combinations can reach **4 × 5 × 1,000 = 20,000** series for a single metric before counting other dimensions. That is why key-values must be bounded from design time.

| Element | Prefer | Avoid |
| --- | --- | --- |
| Observation name | `payment.authorize`, `inventory.reserve` | `payment.authorize.abc123` (ID inside name) |
| Low-cardinality key | `payment.method=card/bank_transfer/wallet` | `payment.customer_id=...` |
| Status | `outcome=approved/declined/error` | Raw exception messages as tags |
| Provider | Normalized name from a bounded list | User-supplied hostnames/URLs |
| High-cardinality key | Policy-vetted internal correlation ID, only when needed | Emails, tokens, card numbers, sensitive identifiers |

In Micrometer Observation, `lowCardinalityKeyValue` is typically used for **metric tags and trace attributes**; `highCardinalityKeyValue` targets detailed trace context and is normally ignored by default metric handlers so it does not spawn time series. Custom handlers, however, can behave differently. Check your actual pipeline, collection limits, and data protection rules before adding even high-cardinality attributes.

Stable names and key sets act as a **telemetry contract**: renaming them can break dashboards, alerts, and historical queries. Favor an agreed key dictionary and finite state enums. Never turn raw request data into metric keys or values.

## 6. When Should You Use a Manual Metric Instead of Adding a Span?

A business action might need to **count occurrences** without needing a separate duration or span. For instance, every order routed to manual review only needs a counter:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public void recordManualReview(MeterRegistry registry, ReviewReason reason) {
    // ReviewReason is a bounded enum: FRAUD_RULE, LIMIT, OTHER...
    Counter.builder("orders.manual_review")
            .description("Orders sent to manual review")
            .tag("reason", reason.name().toLowerCase(java.util.Locale.ROOT))
            .register(registry)
            .increment();
}
```

A `Counter` tells you **how often** orders hit that branch; it does not model execution duration. Conversely, if you need p95 of `inventory.reserve` correlated with checkout traces, `Observation` is usually a better starting point. If you need the current number of pending jobs, use a `Gauge` reading live state rather than summing counters to infer it.

Note: when an `Observation` already records invocation counts and duration for an operation, add another counter only if it measures **an event with distinct semantics**. Adding meters "just in case" clutters dashboards and complicates interpretation.

## 7. Instrumentation Across Threads, Queues, and Services

For asynchronous work, a single request's duration and trace often fail to capture work occurring **after the HTTP response returns**. In those cases, consider measuring at task boundaries:

- **Schedulers/batches:** create an observation per job run or meaningful batch; record a bounded `outcome` and processed item count via suitable meters. Avoid one span per item when volumes are huge.
- **Message producers/consumers:** check built-in framework instrumentation first. If missing, measure message processing duration and outcome, defining ack/retry/dead-letter boundaries clearly. Do not treat a retried message as one undifferentiated transaction if retries carry distinct semantics.
- **Async executors/`CompletableFuture`:** observation scope normally relies on thread-bound context; hopping threads can drop parent/child linkage. Use context propagation supported by the framework and Micrometer, such as executor/task decorators or Micrometer Context Propagation, matching your stack.
- **Across services:** continuous traces require compatible tracing bridges and propagators, typically W3C Trace Context via library/framework support. Never invent your own `traceId` and pass ad-hoc headers in place of standard propagation.

Two essential checks: (1) child spans actually attach to the right parent trace across thread/service boundaries, and (2) worker logs correlate with traces when tracing and MDC correlation are configured. **Opening an observation scope on the originating thread does not automatically guarantee propagation** to every executor.

Sampling affects how many traces are kept or exported. A missing trace may result from sampling, exporter issues, or broken propagation—never conclude the operation didn't run. Metrics can still be recorded from observations even when the corresponding trace is not sampled, depending on handler configuration.

## 8. Common Design Pitfalls

**Overlapping scope measurement.** Placing `@Observed` on an HTTP controller that already has server observations, and adding a `Timer` for the entire request, emits redundant signals with the same meaning. Place instrumentation at unmeasured boundaries, such as pricing or inventory reservation.

**Unbounded tag values.** Putting `orderId`, URLs with query strings, raw exception messages, or emails into low-cardinality key-values explodes time series, drives up storage costs, and risks data exposure.

**Conflating technical errors with business outcomes.** A valid payment decline (`declined`) differs from a network timeout (`error`). Collapsing both into a single failure tag degrades alert precision.

**Omitting failure paths.** Forgetting `stop()` when exceptions are thrown, or catching exceptions without calling `observation.error(ex)`, skews recorded durations and error signals.

**Too many tiny spans.** Adding spans to every getter, every item in a massive batch, or every loop iteration adds overhead and makes traces noisy. Pick operationally meaningful boundaries and measure overhead under high load.

**Confusing logs with metrics.** Per-request logs are great for investigation but do not automatically yield reliable error rates; aggregated metrics are great for alerting but lack per-transaction details. Design all three signals to complement each other and link via trace context where appropriate.

## 9. Decision and Verification Workflow

Before adding custom instrumentation, answer four questions:

1. **What decision do we need to make?** For example: "Did payment authorization p95 rise due to internal service processing or the external provider?" A sharp question reveals the right boundary to instrument.
2. **Are existing signals already sufficient?** Inspect HTTP metrics, client spans, logs, built-in observations, and library version coverage. Separate telemetry gaps from unbuilt dashboards.
3. **How will names and tags evolve?** List the observation name, every tag, and maximum value sets; evaluate PII, overhead, sampling, and exporter costs before shipping.
4. **In which three scenarios can we verify it?** Run success, business decline, and technical failure paths; verify exact names, durations, outcomes, errors, parent/child span relationships, and log correlation.

For the `payment.authorize` example, minimum acceptance criteria are:

| Scenario | Expectation |
| --- | --- |
| Provider returns `approved` | `outcome=approved`; duration recorded; no exception flagged |
| Provider returns valid `declined` | `outcome=declined`; not automatically marked as a technical error |
| Gateway throws an exception | `outcome=error`; observation is stopped; exception propagates to caller |
| Tracing and propagation enabled | Business span (if sampled) is a child of the checkout trace; outbound HTTP call links properly |
| Inspecting metrics | Series exists with bounded labels; no tokens, emails, transaction IDs, or dynamic URLs in tags |

Depending on the backend, also verify the **export path**: Actuator/Micrometer produces data → observation handlers/tracing bridge → registry/exporter → backend (such as Prometheus or trace collector) → dashboards and alerts. A missing measurement is not always a bug in business code: it may stem from exporters, scrape endpoints, sampling, or telemetry filters.

**Rule of thumb:** Custom instrumentation is worthwhile when it turns a vague operational question into an actionable, cross-checkable signal: *which step is slow, which error type is climbing, which retry failed, what happened after the request finished*. A small set of well-placed measurements with bounded tags, clear error semantics, and intact context propagation beats a flood of noisy spans and metrics every time.
