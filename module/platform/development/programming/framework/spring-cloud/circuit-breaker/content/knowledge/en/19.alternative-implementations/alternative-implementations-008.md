# Evaluating Sentinel or External Implementations by Actual Artifacts

Spring Cloud CircuitBreaker provides a common API for applications to invoke a circuit breaker through an underlying implementation library. When considering Sentinel or another service-protection library, you must identify exactly which artifacts are present in the project's dependencies and what kind of integration those artifacts provide. A library having circuit-breaking capabilities does not automatically mean it provides a compatible provider for `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory`.

For the **SPRING_CLOUD_CIRCUIT_BREAKER** module, the goal is to evaluate an alternative based on the actual dependency tree, BOM, auto-configuration, and APIs. After verifying those, the team can use an existing integration, invoke the library's API directly, or build a custom adapter for Spring Cloud CircuitBreaker. Do not pick a solution based solely on a dependency name or an example from a different version.

## 1. Distinguishing the Protection Library from a Spring Cloud CircuitBreaker Provider

There are three distinct layers to separate:

1. **Protection engine:** the library executing circuit breaking, rate limiting, flow control, or bulkhead algorithms. For instance, Sentinel core provides APIs and rules to govern resources.
2. **Framework integration:** an artifact connecting the engine to a specific Spring component, such as AOP annotations, Spring Web, WebFlux, Gateway, or Feign.
3. **Spring Cloud CircuitBreaker provider:** an adapter implementing Spring Cloud CircuitBreaker's factory contract, allowing the application to create breakers via the common `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory` API.

These three layers may live in one starter or in separate artifacts. A Sentinel starter might auto-configure filters or annotation interceptors without necessarily providing a `CircuitBreakerFactory` bean. Conversely, a Spring Cloud CircuitBreaker provider may expose the factory without covering every engine-specific feature.

| Found in Dependencies | What You Can Conclude | What You Cannot Conclude Yet |
|---|---|---|
| Sentinel core artifact only | The Sentinel engine is on the classpath. | Does not prove Spring integration or a Spring Cloud CircuitBreaker provider is present. |
| Spring Cloud Alibaba Sentinel starter | The project has a Spring Cloud Alibaba Sentinel integration layer matching the starter version. | Does not prove the starter implements Spring Cloud CircuitBreaker's `CircuitBreakerFactory`. |
| Sentinel integration for Feign, Gateway, or WebFlux | Can protect a specific framework boundary. | Does not prove calls through `CircuitBreakerFactory` use Sentinel. |
| Provider artifact and auto-configuration creating a compatible factory | Basis to use the common API if versions are compatible. | Still must verify beans, configuration, fallback, reactive support, and metrics at runtime. |
| Internal library or custom adapter | An integration may exist outside the main Spring Cloud project. | Must check that adapter's API contract, versioning, and maintenance lifecycle. |

Therefore, the first question is not "Does Sentinel have a circuit breaker?" but rather "Which artifact supplies the protection mechanism, which artifact connects it to Spring, and does any provider actually implement the factory API the application plans to use?"

## 2. Inspecting Actual Artifacts in the Project

Before adding a new dependency, inspect the current Spring Boot version, Spring Cloud release train, and dependency management. Components must be managed under a compatible BOM; do not manually mix versions of Spring Cloud Alibaba, Spring Cloud CircuitBreaker, and Spring Boot merely because they resolve and download together.

With Maven, inspect the dependency tree for the relevant groups:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud,com.alibaba.cloud,com.alibaba.csp,io.github.resilience4j
```

Inspect the applied dependency management:

```bash
mvn help:effective-pom
```

With Gradle, inspect the runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Look specifically for components such as:

| Artifact Group | What to Verify |
|---|---|
| `org.springframework.cloud` | Which Spring Cloud CircuitBreaker starter and provider are pulled in? |
| `com.alibaba.cloud` | Is there a Spring Cloud Alibaba Sentinel starter or Spring Cloud Alibaba adapter? |
| `com.alibaba.csp` | Are Sentinel core and the required integration modules present? |
| `io.github.resilience4j` | Which Resilience4j modules are pulled in directly or transitively? |
| Internal/other vendor artifacts | Is there an adapter module with its version, publishing source, and documentation? |

Do not just check artifact names in `pom.xml`. A dependency may be pulled transitively, excluded, overridden by a BOM, or absent at runtime due to scope. Check both the resolved version and the dependency path leading to that artifact.

## 3. Verifying Whether a Factory Provider Exists

If the goal is to use the common Spring Cloud CircuitBreaker API, check whether the provider supplies and registers the appropriate beans. Look for these signs:

- An implementation of `CircuitBreakerFactory` or a factory class extending the abstraction for the release train in use.
- If reactive is needed, an implementation of `ReactiveCircuitBreakerFactory` and appropriate Reactor integration.
- Auto-configuration or Spring configuration that creates the factory bean when the starter is enabled.
- Ability for the factory to create breakers by ID and, if supported by the version's contract, by group name.
- Support for default and per-ID configuration compatible with the `Customizer` mechanism.
- Fallbacks receiving and propagating the error cause per contract.
- A way to observe states, events, and metrics of the underlying engine.

You can inspect the classpath and auto-configuration via your IDE, a dependency analyzer, or by examining the JAR contents of the exact artifact. In modern Spring Boot, auto-configuration metadata is typically declared in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; some older libraries use different registration mechanisms. A JAR containing a class named `CircuitBreaker` is not sufficient proof that it is a Spring Cloud CircuitBreaker provider.

When the application starts, check the actual beans using Spring Boot Actuator `/actuator/beans` if exposed and properly secured, or use an integration test verifying that the factory bean can be injected. If the factory does not exist, do not assume Spring will automatically switch to Sentinel just because a Sentinel starter is on the classpath.

## 4. What Capabilities Does Sentinel Provide?

Sentinel is a traffic-control and protection system. Depending on the artifact and version used, capabilities commonly of interest include:

- **Flow control:** limits traffic per resource, request count, or supported control strategies.
- **Circuit breaking/degradation:** evaluates error ratio, error count, or slow-request ratio over a statistical window to stop calling a degraded resource.
- **System protection:** protects the application based on system load signals when supported by configuration and runtime.
- **Resource definition:** names resources so rules apply to a call site or group of operations.
- **Block handling:** handles requests blocked by Sentinel, typically via `BlockException` or the integration's corresponding handler.

Sentinel uses the concepts of resources and rules. Resource names must be stable so rules apply in the right place. A single resource can be protected by multiple rule types, such as flow control and degradation. Consequently, when moving from Resilience4j to Sentinel, do not just swap library names—remap the meaning of each rule.

Supported degradation rule types and parameters can vary across Sentinel versions. Inspect the actual artifact to see whether slow request ratio, exception ratio, or exception count strategies are supported, along with parameters like stat interval, minimum request amount, and recovery timeout. Do not assume windows, algorithms, and state transitions match Resilience4j identically.

## 5. Spring Cloud Alibaba Sentinel Does Not Automatically Mean a Spring Cloud CircuitBreaker Provider

In the Spring Cloud Alibaba ecosystem, the Sentinel starter can integrate Sentinel with Spring Cloud components according to the corresponding release train. An application can use the `@SentinelResource` annotation, filters, or Feign/Gateway integrations if provided by that artifact and version.

Example of using the annotation to protect a resource:

```java
import com.alibaba.csp.sentinel.annotation.SentinelResource;
import com.alibaba.csp.sentinel.slots.block.BlockException;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    @SentinelResource(
        value = "inventory:read",
        blockHandler = "handleBlocked",
        fallback = "handleFailure"
    )
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock handleBlocked(String sku, BlockException error) {
        return Stock.temporarilyUnavailable(sku);
    }

    public Stock handleFailure(String sku, Throwable error) {
        return Stock.unavailable(sku);
    }
}
```

In this example, `inventory:read` is the resource name. `blockHandler` handles cases where Sentinel blocks the request based on rules; `fallback` handles exceptions thrown inside the protected method under the annotation mechanism. Handler signatures must follow the rules of the Sentinel version in use, typically accepting the original parameters plus `BlockException` for block handlers. The corresponding AOP/integration dependency is required for the annotation to execute; merely adding the annotation to code does not guarantee the interceptor is active.

This example proves a call site can be protected directly using Sentinel integration. It **does not prove** the application can inject `CircuitBreakerFactory` and use Sentinel as a Spring Cloud CircuitBreaker provider. The two integration approaches have different APIs and lifecycles.

## 6. Evaluating Sentinel for Feign, Gateway, and Reactive

Integration at each boundary must be verified separately. For example, a Spring Cloud Alibaba release might provide Sentinel integration for Feign or Gateway, yet that does not mean internal service calls, `WebClient`, and Reactor publishers are all protected the same way.

| Boundary | What to Verify in the Artifact/Version |
|---|---|
| `@SentinelResource` | Is the AOP aspect configured and is the resource created properly? |
| OpenFeign | Is Feign/Sentinel integration included in the starter; what are the enablement property and fallback factory? |
| Spring Cloud Gateway | Is there a filter or adapter compatible with the Gateway version in use; do rules apply by route or which resource? |
| Spring WebFlux | Is there a filter or reactive integration; how are cancellation and error signals handled? |
| Reactor `Mono`/`Flux` | Is there a reactive operator protecting the full subscription lifecycle; does it block the event loop? |
| Direct HTTP client | Is there an interceptor or decorator compatible with the actual client? |

For reactive code especially, do not assume synchronous annotations automatically cover the full publisher lifecycle. If an integration wraps only publisher creation rather than subscription and completion, permit holding, error recording, and resource release timing can be wrong. Use a reactive adapter/operator documented by the artifact and test `onError`, `onComplete`, cancellation, and multiple subscriptions.

Do not invoke synchronous Sentinel APIs that may wait or block directly on a Reactor event loop. If you need to protect a blocking task, offload it to an appropriate scheduler and bound concurrency; if protecting a reactive flow, use a genuine reactive integration.

## 7. Mapping Concepts Between Resilience4j and Sentinel

Both libraries can solve overlapping problems, yet their configuration models are not identical.

| Need | Resilience4j | Sentinel |
|---|---|---|
| Identifying the protected point | Circuit breaker ID | Resource name |
| Limiting concurrent calls | Bulkhead module | May require flow/concurrency mechanisms or layer-specific limits depending on integration; do not treat a flow rule as fully equivalent to a bulkhead. |
| Stopping calls when dependency degrades | CircuitBreaker state and sliding window | Sentinel's degrade/circuit-breaking rule and state machine. |
| Limiting request rate | RateLimiter | Flow control rule. |
| Handling blocked requests | `CallNotPermittedException` or other policy exception | `BlockException` or integration handler. |
| Retry | Resilience4j Retry | Usually requires coordinating retry in the client/framework or a separate policy; do not assume retry is part of a degradation rule. |
| Timeout | TimeLimiter and client timeouts | Verify integration and client timeouts; Sentinel slow-request degradation does not replace network timeouts. |
| Metrics/events | Micrometer integration and event publisher | Sentinel metrics, dashboard, datasource, or corresponding integration. |

Do not mechanically map `failureRateThreshold` to a Sentinel parameter simply because both are percentages. Inspect the rule strategy, minimum request count, stat interval, recovery timeout, and how slow requests are evaluated in the actual version.

## 8. When Should You Use Sentinel Directly?

Direct Sentinel integration can fit when the application has already standardized Sentinel resource names and rules, needs both flow control and degradation on a single resource, or already operates Sentinel's dashboard/dynamic rule datasources in the system.

In that case, you can keep Sentinel APIs at the service boundary or supported framework boundaries. Organize stable resource names, separate block handlers from business fallbacks, and record separate metrics for Sentinel-blocked requests versus dependency exceptions.

There is no need to force Sentinel behind `CircuitBreakerFactory` if the application has no requirement to use that abstraction. Calling the engine's API directly can be clearer when Sentinel-specific features are the primary requirement. However, business code becomes more coupled to Sentinel, and swapping engines later may require modifying adapters or service boundaries.

## 9. When Do You Need to Write a Spring Cloud CircuitBreaker Adapter?

If the application wants to keep Spring Cloud CircuitBreaker's common API while using Sentinel or another external engine underneath, you can write an adapter. The adapter must translate Spring's contract to the engine's API and back.

An adapter must handle at least the following areas:

1. **Factory:** implement the imperative factory; if the application is reactive, implement a separate reactive factory with non-blocking semantics.
2. **Identity:** map `id` and `groupName` to the engine's resource/rule key; avoid generating unstable per-request IDs.
3. **Configuration:** support default and per-ID configuration following the contract of the active Spring Cloud release train.
4. **Supplier:** execute the supplier only when the engine grants permission; release entries/permits properly across completion, error, or cancellation.
5. **Exception mapping:** distinguish blocked calls from exceptions thrown by the supplier; do not collapse every exception into one generic error type.
6. **Fallback:** pass the right cause to the fallback and avoid losing the original error if the fallback itself fails.
7. **Reactive lifecycle:** tie protection permits to subscription, terminal signals, and cancellation; never block the event loop.
8. **Observability:** expose sufficient state, metrics, and events for operations; define how engine-specific states map cleanly.
9. **Lifecycle:** manage registries, listeners, rule refresh, and shutdown; avoid creating new listeners or engine instances per request.

Generic types, base classes, and extension hooks in Spring Cloud CircuitBreaker can vary across release trains. When implementing an adapter, read the API of your exact dependency and implement the corresponding interface/abstract class; do not copy a skeleton from another version without verifying signatures.

## 10. Exception Mapping Is a Critical Boundary

The adapter must preserve the distinction between:

- **Rejection:** the engine rejected the call before the supplier ran because the circuit breaker is open, a flow rule threshold was exceeded, or capacity is exhausted.
- **Execution failure:** the supplier ran and produced a timeout, connection error, or exception from the dependency.
- **Ignored/business outcome:** an exception classified as not affecting the dependency's health state.

If the adapter turns every `BlockException` into a generic exception and counts it as a dependency execution failure, failure rates can climb due to Sentinel's own blocking policies. Conversely, turning a supplier timeout into a rejection hides from operators that the dependency actually received the request and failed.

When mapping rejections to `CallNotPermittedException`, do so only if the semantics match a call rejected by the circuit breaker and conform to the Spring Cloud CircuitBreaker contract. Flow-control rejections and full bulkheads can carry different meanings; if you group them, preserve the root cause in the cause chain or metadata so fallbacks and metrics can tell them apart.

Because fallbacks receive a `Throwable`, inspect the cause type. Never hot-retry a rejection; never report fake success for write operations; and if the fallback fails, preserve both the primary error and the fallback error under a consistent exception convention.

## 11. Do Not Run Two Circuit Breakers on the Same Call Unintentionally

A common misconfiguration is protecting the exact same Feign or HTTP client call with both Sentinel and Spring Cloud CircuitBreaker/Resilience4j. Then two engines maintain two independent windows, two thresholds, and two states.

Consequences can include:

- One engine rejects requests before the other has a chance to record outcomes.
- Fallbacks get invoked across multiple layers or error causes get altered.
- Metrics report mismatched call counts, failures, and rejections.
- Retries in one layer repeatedly hit an open circuit breaker in another layer.
- Difficulty telling which engine is actively cutting traffic.

If you genuinely need multiple protection layers, assign distinct roles: for instance, Sentinel flow control at ingress to cap route-wide traffic and a circuit breaker on the service client to track one dependency's health. Place them at distinct boundaries, define ordering explicitly, and test actual request counts reaching the dependency. Avoid stacking two equivalent circuit breakers around the same supplier merely because both starters happen to be on the classpath.

## 12. Evaluating an Artifact Outside Sentinel

Other libraries may also provide their own circuit breaker or bulkhead. Before adopting an external artifact, evaluate it against these questions:

| Criterion | Verification Question |
|---|---|
| Source and maintenance | Who publishes the artifact, is it actively maintained, and does it have a clear release policy? |
| Compatibility | Is the version compatible with the project's Java, Spring Boot, Spring Cloud, and Jakarta/Servlet stack? |
| API | Does it offer an imperative API, reactive API, or both? Does it support cancellation? |
| Spring integration | Does it provide a starter/auto-configuration or only a core library? |
| Factory provider | Does it implement `CircuitBreakerFactory` or require a custom internal adapter? |
| Rule semantics | How are thresholds, sliding windows, minimum calls, slow calls, and HALF_OPEN defined? |
| Failure classification | Does it distinguish recorded exceptions, ignored exceptions, and rejected requests? |
| Fallback | Does it support fallbacks or allow integrating fallbacks per the application contract? |
| Timeout/bulkhead/retry | Does it include corresponding modules or require coordinating clients and other libraries? |
| Observability | Does it expose metrics, events, health indicators, dashboards, and resource ID tagging? |
| Configuration | Does it support externalized configuration, rule refresh, and multiple environments? |
| Testing | Can states, timing, concurrency, and shutdown behavior be tested cleanly? |

Do not pick a library simply for a convenient annotation. Factor in operability, observability, rule updates, version compatibility, and adapter maintenance cost.

## 13. Pre-Decision Verification Workflow

Follow this sequence:

1. Record the active Spring Boot, Spring Cloud release train, and Java versions.
2. Export the dependency tree and effective POM/runtime classpath to confirm actual artifacts and versions.
3. Determine whether each artifact is a core engine, a Spring integration, or a factory provider.
4. Inspect auto-configuration and the beans created at application startup.
5. If using Sentinel directly, verify resources, rules, block handlers, and integration for the exact boundary to protect.
6. If using the Spring Cloud CircuitBreaker API, verify whether a compatible provider exists or estimate the scope of a custom adapter.
7. Check exception mapping, fallback, timeouts, reactive lifecycle, and metrics.
8. Test supplier failures, rejections, ignored exceptions, recovery, and shutdown.
9. Document explicitly which engine is the single decision maker for each protection boundary.

## 14. Integration Acceptance Test Scenarios

An integration should be considered ready only when tests prove correct runtime behavior, not merely because the application starts up.

| Scenario | Expected Outcome to Verify |
|---|---|
| Dependency operates normally | Supplier runs and the success outcome is recorded exactly once. |
| Dependency times out or throws an error | Supplier ran; error is classified and recorded according to rules. |
| Circuit breaker is open or Sentinel blocks the resource | Supplier does not run; rejection is distinguished from execution failure. |
| Fallback succeeds | Caller receives a fallback result with clear business meaning. |
| Fallback fails | Both the primary error and fallback error remain traceable. |
| Recovery criteria met | Engine permits probing or closes according to its state machine. |
| Traffic exceeds limit | Flow control/bulkhead rejects per policy without exhausting caller resources. |
| High concurrency | Concurrency, queue depth, and requests hitting the dependency stay within limits. |
| Reactive cancellation | Resources/permits are released properly and the event loop is never blocked. |
| Rule refresh or shutdown | Listeners, registries, and management connections update/close cleanly within lifecycle. |

## 15. How to Make the Decision

Choose **Sentinel directly** when actual artifacts provide the right integration for the resources and boundaries to protect, and the team accepts using Sentinel's API/rules. Choose an **existing Spring Cloud CircuitBreaker provider** when the dependency tree and auto-configuration prove a provider compatible with the project's release train. Choose an **external adapter** when you need to keep the common factory API while the engine artifact provides only core or another layer's integration.

If no factory provider is found in the artifacts, state clearly that Sentinel is integrated via annotations, filters, Feign, or direct APIs; do not describe it as a Spring Cloud CircuitBreaker provider. If an adapter is required, start with one small boundary, preserve rejection versus execution failure semantics, and expand to reactive and metrics once tests are in place.

Under every option, only one circuit breaker policy should govern each specific dependency call unless protection layers have explicitly separated roles. Inspect actual artifacts and versions, verify beans and runtime behavior, and then decide how to integrate. This evaluation approach lets a Spring Cloud CircuitBreaker application adopt Sentinel or an external implementation without relying on false assumptions about starters, factories, or reactive capabilities.
