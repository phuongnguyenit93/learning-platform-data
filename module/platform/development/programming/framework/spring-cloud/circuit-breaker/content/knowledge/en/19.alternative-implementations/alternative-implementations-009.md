# Contract Testing and Limitations When Switching Providers

In Spring Cloud CircuitBreaker, an application uses a common API to create and invoke a Circuit Breaker without calling each library's API directly. Through this abstraction, an application can swap implementations—for example, among the integrations supported in the active release train—with fewer changes in calling code. However, the common API does not guarantee that every implementation shares identical behavior, configuration, metrics, or protection capabilities.

When switching Circuit Breaker providers, you must test two kinds of contracts: the contract between the application and the dependent service, and the behavioral contract the application expects from the Circuit Breaker. Testing exposes differences in exceptions, fallbacks, states, timeouts, concurrency limits, reactive pipelines, and operational observability before deploying the new implementation.

## 1. Distinguishing the Service Contract from the Circuit Breaker Contract

There are two contract layers that must remain stable:

| Contract | What Must Be Guaranteed | Example |
|---|---|---|
| Dependency HTTP/API contract | Path, HTTP method, request/response schema, status codes, and business meaning | **GET /products/{id}** returns a Product or 404 error |
| Application protection contract | How the application responds when the dependency is slow or failing, and how the Circuit Breaker controls calls | Timeout routes to fallback; OPEN rejects new calls |

Contract tests for the Catalog service can verify the JSON response, required fields, and the meaning of HTTP 404/503. These tests help the application detect when the service provider changes its API.

Contract tests for the Circuit Breaker focus on application-side behavior: successful calls return normal results; errors are classified properly; fallbacks receive the right cause; the OPEN state prevents calling the dependency; HALF_OPEN allows only the configured number of probes; and the application still emits required metrics.

The two contracts complement each other. An HTTP API that keeps the same schema yet changes a 503 status to 200 with an error payload can still alter how the Circuit Breaker records outcomes. Conversely, the Circuit Breaker provider can change while Catalog's HTTP contract stays unchanged. Therefore, both layers need verification.

## 2. What Does the Spring Cloud CircuitBreaker Abstraction Hide?

Application code can use the common factory to create a Circuit Breaker by name:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.getProduct(id),
            error -> productCache.findById(id)
                .orElseThrow(() ->
                    new CatalogUnavailableException(id, error)
                )
        );
    }
}
~~~

The service uses **CircuitBreakerFactory** and does not need direct knowledge of Resilience4j's registry or builder. This is the part standardized by the abstraction: creating a Circuit Breaker by ID and executing calls with fallback behavior.

However, the factory does not make every implementation detail identical. Remaining differences can include:

- How failure rate, slow-call rate, sliding windows, and OPEN durations are configured.
- How exceptions are identified as recorded, ignored, or treated as success.
- How timeouts and cancellation affect a Future or reactive subscription.
- Bulkhead type, concurrency limits, and how exhaustion rejections behave.
- How Retry interacts with Circuit Breaker and decorator ordering.
- Metric names, tags, events, exposed states, and management APIs.
- Support for blocking, reactive, annotations, and fallbacks per return type.

When switching providers, treat the abstraction as an API boundary for calling code. Do not treat it as a promise that the old provider's configuration or semantics carry over verbatim to the new provider.

## 3. Defining the Behavioral Contract Before Switching Providers

Before replacing an implementation, write down the behavior the application must preserve. A minimal contract can include:

1. Successful calls must return accurate data and never trigger fallback.
2. Technical errors defined as dependency failures must be recorded per policy.
3. Business errors such as ProductNotFound must not inflate the failure rate if they do not reflect service health.
4. When the Circuit Breaker is OPEN, new calls are rejected before the client calls the dependency.
5. Fallback returns the right result type and preserves accurate business meaning.
6. After the wait duration, HALF_OPEN permits only the configured number of probes.
7. If probes succeed sufficiently, the breaker returns to CLOSED; if they fail, the breaker opens again.
8. Timeouts and concurrency limits stay within the application's resource budget.
9. Metrics and logs remain sufficient to distinguish dependency errors, timeouts, rejected calls, and fallbacks.

These items form library-agnostic acceptance criteria. When a new provider fails to meet a requirement, the team must decide whether to adjust configuration, add another mechanism, or abort the switch.

## 4. Testing the Dependency HTTP Contract

Contract tests at the HTTP boundary verify that the application and dependency agree on the same protocol. You can use Spring Cloud Contract, Pact, or an HTTP stub in integration tests. The specific tool depends on how the team manages contracts between consumers and providers.

For example, the application expects Catalog to return a Product when found:

~~~json
{
  "id": "SKU-001",
  "name": "Mechanical Keyboard",
  "available": true
}
~~~

The contract should explicitly define:

- Which HTTP method and path the request uses.
- Which fields are required in the response.
- Data types of each field.
- HTTP status codes when found, not found, invalid request, or service temporarily unavailable.
- Error structure and stable error code fields.
- Headers or correlation IDs that must propagate across services.

Do not verify only that the response has status 200. If Catalog returns status 200 with a payload representing a technical error, the Circuit Breaker may treat the call as a success unless the application inspects the payload and converts it into an exception. The contract must capture response semantics, not just JSON structure.

Contract tests should also verify HTTP client timeouts and cancellation propagation if the client supports it. A Circuit Breaker provider cannot compensate for an HTTP client that has no wait limit or leaks resources when a request is canceled.

## 5. Testing the Application Gateway Contract

You can test the gateway layer at the service level by replacing the client with a stub or mock. The goal is to confirm the application passes the right arguments, classifies errors, and returns a meaningful fallback.

Example testing **CatalogGateway** cases:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class CatalogGatewayTest {

    @Test
    void returnsCatalogProductWhenDependencySucceeds() {
        // Arrange: client returns a valid product.
        // Act: call gateway.getProduct("SKU-001").
        // Assert: returns Product from Catalog without invoking cache fallback.
    }

    @Test
    void usesCacheWhenDependencyFails() {
        // Arrange: client throws a technical error and cache holds the product.
        // Act: call gateway.getProduct("SKU-001").
        // Assert: returns the product from cache.
    }

    @Test
    void reportsUnavailableWhenDependencyAndCacheFail() {
        // Arrange: client errors and cache has no entry.
        // Act: call gateway.getProduct("SKU-001").
        // Assert: throws CatalogUnavailableException with the appropriate cause.
    }
}
~~~

These are unit tests for application logic. If the factory is also mocked, tests do not prove that the actual provider transitions states or applies configuration. To verify those behaviors, write integration tests booting the exact starter and implementation in use.

Avoid relying solely on tests that mock **CircuitBreakerFactory**. Mocks verify how the service uses the abstraction, but miss bugs from auto-configuration, wrong instance names, unbound properties, or provider semantics differing from expectations.

## 6. Building a Circuit Breaker Contract Test Suite

A provider test suite should apply the same set of behavioral criteria. You can structure it into independent test cases:

| Test Case | Condition | Expected Outcome to Verify |
|---|---|---|
| Success | Dependency returns valid data | Returns normal result; fallback does not run |
| Technical error | Dependency throws a recorded exception | Failure is counted per exception policy |
| Business error | Dependency throws an ignored exception | No retry and does not increase failure rate if policy specifies ignore |
| OPEN | Enough failure samples collected to trip circuit | New calls are rejected; client is not invoked again |
| HALF_OPEN | OPEN duration elapses | Only the configured number of probes are allowed to execute |
| Recovery | Probes succeed | Breaker returns to CLOSED per policy |
| Continued failure | Probes fail | Breaker returns to OPEN |
| Fallback failure | Backup source also fails | Caller receives a clear fallback error; original cause is not lost |
| Timeout | Dependency exceeds deadline | Caller receives timeout or fallback per contract |
| Bulkhead full | Concurrency limit reached | Calls are rejected with the right type and resources are released |

When testing state transitions, configure short durations in a test profile and use a clock or bounded wait mechanism. Avoid arbitrary long **Thread.sleep** calls, which make tests slow and flaky. For providers supporting a custom clock, use a fake clock to control time. Otherwise, use polling with an explicit timeout to wait for the target state.

Each test should make clear whether it verifies the common contract or provider-specific traits. For example, specific event or metric names can vary across implementations; common tests should assert essential business signals, while exact metric and event names belong in adapter/provider tests.

## 7. Checking Exception Policy and Fallback When Switching Providers

One major difference is how providers record exceptions. The application must preserve the separation between:

- Technical errors such as connect failures, HTTP 5xx, or timeouts.
- Business errors such as product not found or insufficient stock.
- Circuit Breaker rejections such as **CallNotPermittedException**.
- Internal errors such as exceptions thrown by mappers or application code.

For instance, if **ProductNotFoundException** was previously ignored in failure rate calculations but the new provider counts it as a failure, the Circuit Breaker can open when users search for many nonexistent SKUs. Conversely, if HTTP 503 is treated as a success, the breaker will fail to protect the dependency during overload.

Verify fallbacks across these cases:

1. Fallback is invoked when a technical error occurs.
2. Fallback is invoked when the Circuit Breaker rejects the call.
3. Fallback receives the expected exception or cause the application needs to classify.
4. Fallback returns the expected synchronous or reactive type.
5. Fallback errors propagate outward according to the contract.
6. Fallback never calls back into the failing dependency itself.

If the application uses the **@CircuitBreaker** annotation with **fallbackMethod**, verify fallback signatures, overload resolution rules, and Spring AOP proxies separately. You cannot assume a new provider supports annotations or fallback resolvers identically to the old provider. With Spring Cloud CircuitBreaker's functional API, test passing the supplier and fallback function directly.

## 8. Testing Blocking and Reactive Separately

A provider may support blocking APIs while having limitations or different configuration for reactive flows. Therefore, do not use blocking test results to conclude that reactive flows behave equivalently.

For blocking calls, verify:

- Supplier executes only when permitted by the Circuit Breaker.
- Timeouts do not hold threads or connections past the designed deadline.
- Cancellation affects Futures and clients as expected.
- Fallback returns the appropriate synchronous type.

For reactive calls, verify:

- The source publisher is not subscribed eagerly by accident.
- Synchronous exceptions thrown during Publisher creation are converted into reactive signals if needed.
- **onError** flows through the Circuit Breaker before fallback recovery.
- Subscription cancellation propagates to the client as supported.
- No **block()** calls occur on the event loop.
- Fallback returns a Mono or Flux of the right type and runs only upon subscription.

Reactive example using the common factory:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

class ReactiveCatalogGateway {

    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final ReactiveCatalogClient client;
    private final ProductCache cache;

    ReactiveCatalogGateway(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            ReactiveCatalogClient client,
            ProductCache cache) {
        this.factory = factory;
        this.client = client;
        this.cache = cache;
    }

    Mono<Product> getProduct(String id) {
        return factory.create("catalog").run(
            Mono.defer(() -> client.getProduct(id)),
            error -> cache.findByIdReactive(id)
                .switchIfEmpty(Mono.error(
                    new CatalogUnavailableException(id, error)
                ))
        );
    }
}
~~~

Tests must subscribe to the Mono to trigger the call and verify signals. Merely creating the Publisher without subscribing does not test whether the request or Circuit Breaker executed. When using Reactor Test, use **StepVerifier** to assert values, errors, and completion.

## 9. Provider Configuration Does Not Translate One-to-One

Implementations can use different terminology, structures, and capabilities. For instance, Resilience4j configuration may include **slidingWindowType**, **minimumNumberOfCalls**, **failureRateThreshold**, **slowCallRateThreshold**, **waitDurationInOpenState**, and **permittedNumberOfCallsInHalfOpenState**. Another provider may lack properties with those names or use a different algorithm.

Do not simply rename YAML prefixes and assume the policy has been migrated. Build a mapping table:

| Business Requirement | Old Provider Config | Representation in New Provider |
|---|---|---|
| Minimum samples before evaluation | **minimumNumberOfCalls** | Verify whether the provider has an equivalent concept |
| Count-based or time-based window | **slidingWindowType**, **slidingWindowSize** | Inspect window algorithm and units |
| Failure threshold | **failureRateThreshold** | Verify calculation method and opening trigger |
| Slow-call threshold | **slowCallRateThreshold**, **slowCallDurationThreshold** | May require separate metrics or timeouts if unsupported by provider |
| OPEN duration | **waitDurationInOpenState** | Verify wait duration and transition to probing |
| HALF_OPEN probe count | **permittedNumberOfCallsInHalfOpenState** | Verify limits and concurrent probe handling |
| Timeout | TimeLimiter | May require HTTP client config or a separate mechanism |
| Bulkhead | Semaphore or thread-pool bulkhead | Verify isolation type and queue bounds |

If the new provider lacks an equivalent feature, document the gap explicitly. You can keep TimeLimiter or Bulkhead in an independent layer if architecture permits, provided you test coordination order and exception semantics. Never silently drop a mechanism that is an operational requirement.

## 10. Limitations When Switching Providers

The abstraction layer reduces direct library coupling, but does not eliminate these constraints:

**State machine differences.** Providers may differ in sample counting, OPEN triggers, HALF_OPEN timing, and handling in-flight probes. Identical numeric thresholds do not guarantee identical trip times.

**Exception differences.** Exception class names, wrapping, and error ignoring rules can change. Fallbacks or Retries matching specific exception classes may need adjustments.

**Fallback differences.** Functional fallbacks in **run** versus annotation fallbackMethod can differ in support, signatures, or resolvers. Overload-based fallback resolution should not be treated as a universal contract unless guaranteed by the provider.

**Timeout and cancellation differences.** One provider may integrate TimeLimiter with Futures, while another relies on HTTP clients or reactive operators. Caller timeouts do not guarantee the server stopped processing.

**Bulkhead and Retry differences.** Providers may support concurrency limits, retries, or decorators differently. Coordination order affects how many times the dependency is called and how many samples the Circuit Breaker records.

**Reactive differences.** Not every implementation provides the same support for Mono/Flux, cancellation, and backpressure. Verify the exact starter and reactive factory for your release train.

**Metric and event differences.** Metric names, tags, event publishers, and state query APIs can change. Dashboards and alerts may need updates even when business behavior stays unchanged.

**Auto-configuration differences.** Starters, dependency management, property prefixes, and bean creation conditions can differ. An application starting cleanly does not prove the provider was activated or configuration bound.

## 11. Controlled Provider Migration Process

You can execute a switch in these steps:

1. **Record baseline:** capture configuration, states, error rates, timeouts, fallback rates, call volumes, and latency of the current provider.
2. **Define contract:** document behavior for success, technical errors, business errors, OPEN, HALF_OPEN, timeouts, Bulkhead, and fallback.
3. **Verify new provider capabilities:** confirm release train, starter, blocking/reactive support, and required features.
4. **Map configuration:** translate policies by intent rather than mechanically copying property names.
5. **Run contract tests:** execute the same suite against old and new providers; compare outcomes, exceptions, call counts, and states.
6. **Run integration tests:** verify auto-configuration, properties, service discovery, fallbacks, and metrics in the real application.
7. **Roll out gradually:** deploy to a staging environment or a limited subset of instances before expanding.
8. **Compare operations:** monitor error rates, timeouts, rejected call counts, fallbacks, resource usage, and latency.
9. **Keep rollback ready:** retain artifacts and configuration for the old provider to roll back if contracts or SLOs are missed.

Do not switch providers at the same time as changing dependency APIs, timeouts, retry policies, and fallbacks. When multiple variables change together, it is hard to pinpoint causes when results diverge from baseline. Changing one layer at a time while keeping the contract test suite stable isolates issues quickly.

## 12. Pre-Acceptance Test Matrix for a New Provider

The table below serves as a review checklist. Specific thresholds should be tuned to the service's SLA and traffic.

| Category | Required Verification | Acceptance Criteria |
|---|---|---|
| API contract | Schema, status, error code, HTTP timeout | Consumer and provider share the same semantics |
| Normal path | Dependency succeeds | Outcomes and latency within limits |
| Failure classification | Business 4xx, technical 5xx, connect errors | Recorded/ignored per policy |
| Circuit state | CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN | Transitions match contract |
| Rejection | Calls during OPEN or after probes exhausted | Dependency receives no rejected calls |
| Fallback | Cache hit, cache miss, cache error | Meaningful response; fallback errors are not hidden |
| TimeLimiter | Dependency slower than timeout | Caller receives timeout/fallback on time |
| Cancellation | Future or subscription canceled | Resources released as supported by client |
| Bulkhead | Exceeds concurrency limit | Controlled rejection without exhausting resources |
| Reactive | Subscribe, onError, cancellation | Pipeline behaves correctly without blocking event loop |
| Observability | Metrics, tags, events, logs, and alerts | Dashboards distinguish root causes accurately |
| Compatibility | Starter, BOM, auto-configuration | Only the intended implementation is active |

Beyond PASS/FAIL outcomes, record measured metrics for each provider: requests reaching the dependency, retry counts, fallback rate, open duration, probe counts, and p95/p99 latency. These numbers reveal behavioral differences that a single functional test might miss.

## 13. Practical Scenario

A Spring Boot application uses Resilience4j via Spring Cloud CircuitBreaker to protect Catalog. The team wants to evaluate another implementation supported in the current release train.

Before switching, the team records the contract:

- Circuit Breaker ID is **catalog** and stays stable per dependency.
- HTTP 503, connect failures, and timeouts are classified as technical errors.
- HTTP 404 is a business error per contract and must not raise the failure rate.
- While OPEN, the Catalog client must not be invoked.
- After the wait period, only two probes are permitted in HALF_OPEN.
- Fallback reads from cache and returns Product or throws CatalogUnavailableException.
- Reactive APIs must return Mono and never block the event loop.
- Dashboards must distinguish timeouts, dependency failures, and rejected calls.

The team then:

1. Keeps services using **CircuitBreakerFactory** and **ReactiveCircuitBreakerFactory**.
2. Swaps the implementation starter per the active Spring Cloud version's guide.
3. Maps the requirements above to the new provider's configuration; flags features lacking a direct equivalent.
4. Runs the same test suite with mock dependencies and HTTP contract tests.
5. Starts the application with an integration profile to confirm the factory is injected and the **catalog** instance picks up configuration.
6. Induces a failure sequence to test OPEN, probes during OPEN to verify zero HTTP requests are sent, then tests HALF_OPEN and recovery.
7. Compares metrics, fallbacks, timeouts, and latency against the Resilience4j baseline.

If the new provider does not support the required probe cap or cannot distinguish business errors from technical errors as required, the team cannot treat the switch as equivalent yet. They must add a dedicated mechanism, get contract changes approved, or retain the existing implementation until the gap is resolved.

## Conclusion

Spring Cloud CircuitBreaker reduces coupling to a single library's API, but it does not give providers identical semantics. Before switching implementations, test both the dependency HTTP contract and the Circuit Breaker behavioral contract; verify exceptions, fallbacks, state machines, timeouts, Bulkhead, reactive support, and observability. Accept the new provider only when the same contract test suite passes and all configuration or feature differences have been clearly evaluated.
