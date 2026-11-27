# Instrumenting at the Right Boundary

Instrumentation is the placement of observability recording points in an application to measure the duration, outcome, and context of an activity. In Spring Boot, Micrometer Observation provides a unified API so an activity can be transformed into metrics, tracing, and related signals through configured handlers.

Telemetry quality depends heavily on where instrumentation is placed. Measuring every method floods traces with tiny spans, inflates metric cardinality, and makes data hard to read. Measuring only at an overly broad point tells you the entire request was slow, but makes it hard to identify which piece of work caused the latency. Therefore, select boundaries that reflect meaningful operations for operators, while leveraging Spring Boot and Micrometer auto-instrumentation at layers already supported.

This lesson belongs to the **Architecture Design** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; this content focuses on choosing the right boundaries to correlate signals and investigate errors and latency in production applications.

## Objectives

After this lesson, you will be able to:

- Explain instrumentation boundaries and their role in observability architecture.
- Choose measurement points at HTTP, use case, dependency, and messaging boundaries.
- Distinguish auto-instrumentation from application-created Observations.
- Use `ObservationRegistry` and the Observation API to wrap a business operation.
- Avoid duplicate recording, overly fine-grained spans, or putting inappropriate data into tags.
- Handle scope, transactions, and asynchronous flows with proper lifecycles.

## What Is an Instrumentation Boundary?

A boundary is the start and end demarcation of an activity we want to observe independently. A good boundary has a stable name, clear business or technical semantics, a well-defined execution duration, and produces data that helps answer an operational question.

For example, when a user submits a checkout request, the application might record these activities:

1. The HTTP server receives the request and routes it to the controller.
2. The `checkout.submit` use case coordinates cart validation, inventory reservation, and payment.
3. The HTTP client calls the payment service.
4. The repository persists the order.
5. The result is returned to the client.

Each activity has a distinct boundary. The HTTP server boundary answers how long the request took and what status it returned. The use-case boundary answers how long the checkout business flow took and what outcome it reached. The HTTP client boundary answers how the payment service responded. When these boundaries are properly linked, the trace shows the path from request ingress through dependencies.

Not every method makes a useful boundary. A getter, DTO mapper, or single-line internal helper usually adds no operational insight. Measure meaningful activities rather than tiny implementation steps.

## Choosing Boundaries by Architectural Layer

A Spring Boot application typically has the following layers and integration points:

| Location | Question to Answer | Appropriate Instrumentation Approach |
|---|---|---|
| HTTP ingress | Which requests are slow, failing, or returning which statuses? | Prefer built-in Spring Boot/Micrometer HTTP server instrumentation |
| Application service or use case | How long did a business flow like checkout or reserve inventory take, and what was its outcome? | Create a manual Observation at the use case entry point when default signals do not express business semantics |
| Domain objects and pure functions | Do calculation rules or data transformations have an independent activity worth tracking? | Usually do not instrument individual methods; measure a heavy computation only if there is a clear operational reason |
| HTTP/RPC client | Where are external dependencies responding slowly or failing? | Use built-in client auto-instrumentation when supported; create Observations for custom clients/protocols |
| Database and repository | Which queries or persistence operations are slow? | Leverage JDBC/R2DBC instrumentation; add a business boundary when you need to know which use case triggered the query |
| Messaging producer/consumer | How long does publishing or processing a message take, and where do errors happen? | Instrument at publish and consume boundaries; ensure context propagation across messages when supported |
| Scheduled job or batch | Did a job/batch run succeed or fail, and how long did it take? | Create a boundary for a single run or a meaningful chunk; avoid creating observations per record unless necessary |

Spring Boot and Micrometer can auto-instrument components like HTTP servers, HTTP clients, JDBC, or messaging depending on dependencies, versions, and configuration. Exact coverage depends on the application stack. Before manually adding an Observation, check whether that component is already instrumented to avoid emitting two spans or two metrics for the same activity.

### Ingress: Request-Receiving Boundary

HTTP server instrumentation is typically the starting point of a trace. It records incoming requests, routes, methods, statuses, and processing duration according to library conventions. With Spring MVC or WebFlux, preserve normalized route templates so requests like `/orders/1001` and `/orders/1002` group under the same `/orders/{orderId}` endpoint.

Controllers are usually adapters translating HTTP into application service calls. If HTTP server instrumentation already records requests, do not create another Observation just to wrap an entire controller method with duplicate information. Create Observations at the use case if you want a protocol-independent business perspective.

### Application Boundary: Use-Case Boundary

This is usually the right place to create manual Observations. Application services orchestrate activities users or downstream systems care about, such as `checkout.submit`, `inventory.reserve`, or `invoice.issue`. This boundary can encompass multiple domain operations and dependency calls without manually creating spans for every internal method.

Observation names should describe a stable action, without IDs or input data. Low-cardinality tags should express useful classification dimensions like `channel`, `operation`, or `outcome`, with bounded value sets.

### Outbound Boundary: Dependency Call Boundary

Calls to payment gateways, inventory services, or other systems are frequent sources of latency and failures. When using `RestClient`, `WebClient`, HTTP clients, or libraries supported by Micrometer instrumentation, prefer built-in instrumentation to preserve proper propagation and conventions.

If the application uses a custom client or proprietary protocol, wrap the call with a manual Observation. Create only one Observation per meaningful dependency call. Do not add another span layer around an already auto-instrumented client if it adds no new information.

### Persistence Boundary: Data Access Boundary

JDBC or R2DBC instrumentation shows how long queries take and whether they failed. A use-case Observation in the application service adds business context: which business operation triggered that query. Both perspectives serve different purposes and can coexist.

Avoid manually instrumenting every repository method if the driver or framework already emits matching spans/metrics. If a specific business query needs dedicated measurement, pick a stable name and add only bounded classification tags; never put interpolated SQL, record IDs, or arbitrary parameters into metric tags.

## Example: Instrumenting at the Use-Case Boundary with Micrometer Observation

Suppose an application has `CheckoutApplicationService`, which orchestrates the checkout workflow. Internal HTTP client and database calls are already auto-instrumented by application configuration. We want an additional view for the overall `checkout.submit` use case to track processing duration and business outcomes.

The example below injects the Spring Boot-configured `ObservationRegistry`. `channel` is normalized into a small value set. `outcome` describes the use case result. `orderId` is still used in business logic without being added as a metric tag.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CheckoutApplicationService {
    private final CheckoutWorkflow checkoutWorkflow;
    private final ObservationRegistry observationRegistry;

    public CheckoutApplicationService(
            CheckoutWorkflow checkoutWorkflow,
            ObservationRegistry observationRegistry) {
        this.checkoutWorkflow = checkoutWorkflow;
        this.observationRegistry = observationRegistry;
    }

    public CheckoutResult submit(CheckoutCommand command) {
        Observation observation = Observation
                .createNotStarted("checkout.submit", observationRegistry)
                .lowCardinalityKeyValue(
                        "channel", normalizeChannel(command.channel()));

        observation.start();
        try (Observation.Scope scope = observation.openScope()) {
            CheckoutResult result = checkoutWorkflow.execute(command);
            observation.lowCardinalityKeyValue(
                    "outcome", result.accepted() ? "accepted" : "rejected");
            return result;
        } catch (RuntimeException exception) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(exception);
            throw exception;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String rawChannel) {
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

- `checkout.submit` is a stable business activity name, independent of URLs or order IDs.
- `channel` only ever takes `web`, `mobile`, `partner`, `other`, or `unknown`.
- `outcome` only takes `accepted`, `rejected`, or `error`.
- `checkoutWorkflow.execute` coordinates business logic; internal dependencies can produce child spans via configured instrumentation.
- `observation.error(exception)` records the exception on the Observation. Exception messages are not put into low-cardinality tags.
- `observation.stop()` always executes to end the Observation, even when the use case throws an exception.

`Observation.Scope` places the current Observation into context while the use case executes. Components supporting Micrometer Context Propagation can use this context to correlate signals. The scope must be closed before stopping the Observation; try-with-resources in the example guarantees this.

If a rejection outcome is a normal business scenario, represent it with `outcome=rejected` rather than throwing a synthetic exception solely to mark failure. Use `observation.error(...)` for execution failures that should be recorded as exceptions. This separates valid business rejection rates from technical error rates.

## Combining Auto-Instrumentation and Manual Instrumentation

Auto-instrumentation and application-created Observations serve different perspectives:

| Instrumentation | Example Activity Name | Value Provided |
|---|---|---|
| Automatic HTTP server | `http.server.requests` or server span per library convention | Measures requests at app edge, route, method, status, and duration |
| Manual use case | `checkout.submit` | Measures a business flow spanning multiple internal steps |
| Automatic HTTP client | Client request span/metric | Measures individual dependency calls and trace propagation |
| Automatic JDBC/R2DBC | Database operation span/metric | Pinpoints slow queries or persistence operations |
| Custom Observation | `partner.message.publish` | Measures custom components lacking built-in instrumentation |

A trace can include a server span, a use-case span, and child client/database spans. This hierarchy narrows down where slowdowns occur. However, if every layer creates spans for the exact same activity without distinct meaning, traces become bloated and hard to read. Inspect actual traces to confirm parent-child relationships and remove duplicate instrumentation.

For metrics, keep in mind that an Observation can be converted into meters depending on handlers and conventions. Add manual Observations only when that business metric answers a distinct question. Avoid creating metrics for every method, as meter counts and tag combinations will grow without adding useful information.

## Choosing the Time Scope to Measure

A boundary defines when the clock starts and stops, so decide clearly which activities fall inside it.

- When measuring an entire use case, start before the first orchestration step and end after business logic completes.
- When measuring a specific dependency, wrap just the dependency call or rely on auto-instrumentation.
- When measuring a batch job, choose a single run or a chunk as the unit of measurement; avoid creating an Observation per record by default.
- If measurement must include transaction commit, place the Observation outside the call through the transactional proxy or deliberately configure interceptor ordering.

The end of a `@Transactional`-annotated method may occur before the transaction interceptor completes the commit, depending on proxy/interceptor ordering. Thus, an Observation created inside the method might exclude commit time. If commit falls within the required scope, instrument at the caller outside the transactional bean or explicitly control execution order.

Do not stretch an Observation merely to span periods belonging to unrelated activities. For instance, user think time between two requests should not be measured by keeping an Observation open across an entire session. Measure each individual request or job execution.

## Context and Asynchronous Flows

In synchronous flows, opening a scope around a call keeps the current Observation active during execution. When work moves to another thread, executor, `@Async` method, or callback, context does not always propagate automatically across every implementation pattern.

Never leave an `Observation.Scope` open across an asynchronous boundary and close it from a different thread. Instead, use context propagation mechanisms supported by the Spring/Micrometer stack, configure executors appropriately, and inspect traces after execution. For message brokers, context typically needs to be transmitted via message headers according to the corresponding instrumentation convention.

If an asynchronous operation has its own lifecycle, define separate boundaries for sending the message and consuming the message. The producer finishes when publishing completes; the consumer starts when the message is received and processed. Linking both sides via trace context enables cross-service investigation without holding a synchronous scope open while waiting on a queue.

## Designing Observation Names and Tags

Observation names should describe the action, remain stable across versions, and stay independent of specific data. For example:

| Prefer | Avoid |
|---|---|
| `checkout.submit` | `checkout.order-93821` |
| `inventory.reserve` | `reserve.product-ABC` |
| `invoice.issue` | `invoice.issue.customer@example.com` |
| `partner.message.publish` | `partner.message.<random-id>` |

Low-cardinality tags should reflect operational questions: `channel`, `outcome`, `payment.type`, or `region` from a finite configured list. Never use `orderId`, `customerId`, `requestId`, emails, raw URLs, or exception messages as metric tags. If traces need an identifier to investigate a specific transaction, consider high-cardinality attributes in accordance with data policy and tracing backend capabilities.

Keep keys consistent across use cases. If the same concept is called `channel` in one place, `source` in another, and `clientType` elsewhere, aggregating dashboards and comparing operations becomes harder. Defining a shared vocabulary makes instrumentation a cohesive part of architecture.

## Common Mistakes When Choosing Boundaries

### Instrumenting Every Small Method

Creating spans for getters, mappers, or helpers fills traces with nodes without explaining system behavior. Choose meaningful use cases or dependency calls rather than individual internal methods.

### Instrumenting Only Controllers

HTTP server metrics show overall request behavior without revealing which use case or dependency consumed time. Add an application boundary and use client/database instrumentation to create the necessary hierarchy.

### Creating Manual Observations Around Auto-Instrumented Components

Duplicate measurement of HTTP clients or JDBC produces redundant spans and confusing metrics. Verify active auto-instrumentation before adding manual wrappers.

### Choosing Overly Broad Boundaries

Lumping multiple independent jobs or the entire application lifecycle into one Observation makes duration and errors impossible to attribute to a single unit of work. Split by request, use case, job run, or message.

### Choosing Overly Narrow Boundaries

Measuring individual statements without a use-case Observation makes it hard for operators to see which business flow those statements served. Combine a business boundary with technical spans when each contributes distinct insight.

### Embedding Input Data in Names or Tags

Names and tags containing IDs drive up cardinality, consume resources, and risk leaking data. Keep names stable and normalize tags against an allowlist.

### Overlooking Transactions or Async Context

Observations may stop before commit or lose correlation across thread handoffs. Define the intended time scope and test propagation across real boundaries.

## Verifying Instrumentation

After placing boundaries, validate both the semantics and technical behavior of telemetry:

1. Invoke a successful use case and verify the Observation/trace has a stable name, reasonable duration, and accurate `outcome`.
2. Trigger a business rejection and confirm it classifies as `rejected`, not miscounted as an exception when it is a normal outcome.
3. Trigger a technical error and confirm the exception attaches to the Observation while tags remain within the defined value set.
4. Call a slow dependency or simulate a failure to verify client spans appear beneath the use-case span when instrumentation is supported.
5. Execute a database query to verify auto-instrumentation is not duplicated.
6. Send multiple requests with varying IDs and confirm metric series counts do not grow per ID.
7. For asynchronous or messaging flows, verify trace context propagates and links accurately across thread or message boundaries.
8. If measured duration must include transaction commit, verify the span finishes after commit completes.

You can use Micrometer Observation test handlers or meter registries in tests to assert Observation names, tags, and states. In a running environment, inspect metrics endpoints, tracing backends, and logs with correlation context. Only consider instrumentation complete when traces accurately reflect boundaries and telemetry answers the intended operational questions.

## Pre-Release Checklist

- [ ] Every Observation corresponds to a meaningful business or technical activity.
- [ ] Boundaries have clear start points, end points, and units of measurement.
- [ ] Auto-instrumentation was checked before adding manual Observations.
- [ ] Use-case boundaries add business context not captured by HTTP/client/database instrumentation.
- [ ] Observation names are stable and contain no IDs or request data.
- [ ] Low-cardinality tags have bounded value sets and are normalized.
- [ ] Normal business outcomes are distinguished from technical exceptions.
- [ ] Scopes are closed before Observations are stopped.
- [ ] Transactions and async/message contexts are handled within proper scopes.
- [ ] Traces have no duplicate or overly fine-grained spans; metrics show no abnormal cardinality.

## Conclusion

Placing instrumentation at the right boundaries makes telemetry reflect the real structure of the application. Leverage built-in instrumentation for HTTP, clients, databases, and messaging where supported; add manual Observations at application/use-case boundaries to capture business semantics. Keep names and tags stable, define exact time scopes, and verify transactions and context propagation so traces, metrics, and logs support investigation consistently.
