# Avoiding Optional Dependency Failures Breaking Liveness

In a Spring Cloud application running on Kubernetes, a liveness probe indicates whether the application process is still alive and able to keep running. A readiness probe indicates whether an instance is ready to accept traffic. These two signals serve different purposes. If an optional dependency such as product recommendations, email delivery, or supplementary content lookup fails, the application can still handle most requests using a fallback. An optional dependency failure must not cause liveness to fail and prompt Kubernetes to restart healthy containers.

When every replica checks an external dependency inside liveness, a single dependency outage can mark all replicas unhealthy and trigger continuous restarts. Restarting does not repair an external service; instead, it reduces processing capacity and can amplify the outage. Health checks should be designed around process vitality and the application's ability to accept traffic, while dependencies are tracked using separate signals.

## Distinguishing Liveness, Readiness, and Startup Probes

The three probe types in Kubernetes answer three different questions:

| Probe | Question | On Failure |
|---|---|---|
| **Liveness** | Is the process still alive and able to keep running? | Kubelet may restart the container after the failure threshold is reached. |
| **Readiness** | Can the instance accept and serve current traffic? | The Pod is removed from traffic-receiving endpoints until readiness succeeds again. |
| **Startup** | Has the application finished its startup phase? | Kubelet keeps checking startup and delays liveness/readiness checks until startup succeeds. |

Liveness should reflect internal process health: the application has initialized, event loops or main threads are not severely hung, and it can keep operating. It should not depend on every remote service being healthy.

Readiness can evaluate conditions genuinely required for an instance to accept requests. If a database is mandatory for every endpoint to operate safely, readiness can reflect connectivity or related application state. If a dependency serves only a secondary feature with a fallback, its outage usually should not make the entire instance unready.

A startup probe is useful when an application starts slowly, such as loading configuration or initializing local data. It prevents Kubernetes from evaluating liveness too early before startup completes.

## Why Should Optional Dependencies Not Determine Liveness?

Suppose a product page aggregation API calls three services: catalog, inventory, and product recommendations. Catalog and inventory are core data; product recommendations are an optional feature. When the recommendations service goes down, the application can still return the product page with catalog and inventory data while omitting recommendations or using a cache.

If liveness checks all three services, an outage in recommendations can cause all pods to restart. A dangerous chain of events can unfold:

~~~mermaid
flowchart TD
    A[Recommendations service fails] --> B[Liveness calls or depends on recommendations]
    B --> C[Liveness probe fails]
    C --> D[Kubernetes restarts pods]
    D --> E[Capacity drops and connections are recreated]
    E --> F[Load on remaining services increases]
    F --> G[Outage spreads]
~~~

A circuit breaker stops requests from repeatedly calling a failing dependency. A fallback lets the application preserve core functionality. Liveness should continue succeeding while the process is healthy, even when an optional dependency's circuit breaker is OPEN.

Do not use liveness to force application restarts in an attempt to recover a remote service. Kubernetes restarts your application's container, not the downstream dependency. Mass client restarts can also unleash a burst of new connections and requests right when the system is overloaded.

## Configuring Health Probes with Spring Boot Actuator

Spring Boot Actuator provides health groups for liveness and readiness. When probe support is enabled, the application can expose dedicated endpoints:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

You can enable probes and expose additional short paths on the primary HTTP port:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

With this configuration, Spring Boot provides health groups backed by application availability states. When `add-additional-paths` is enabled, `/livez` and `/readyz` on the main server port let Kubernetes probe the same process serving requests.

Do not add optional dependency health indicators to the liveness group. For instance, an indicator checking the recommendations service, an optional Redis cache, or an email service must not trigger process restarts when those services are unavailable.

Readiness should also be chosen intentionally. If an optional dependency breaks while the application has a fallback and still serves core endpoints, do not automatically include that indicator in the general readiness group. Dependency status can be published in a separate health group for diagnostics.

## Configuring Probes in Kubernetes

Example Deployment using Spring Boot probe endpoints:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: product-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: product-api
  template:
    metadata:
      labels:
        app: product-api
    spec:
      containers:
        - name: product-api
          image: example/product-api:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

Timing values are illustrative only. Tune them for startup time, normal latency, and deployment requirements. The startup probe gives the application time to boot; liveness starts only after the startup probe succeeds. Readiness continuously checks traffic-receiving capability throughout the pod's lifecycle.

Probe endpoints should be lightweight, internal, and fast to respond. Avoid issuing a series of synchronous HTTP calls to every dependency each time kubelet calls a probe. Those network checks can slow probes down, couple them to multiple service timeouts, and turn an external outage into a health failure of the process itself.

## Choosing Which Dependencies Affect Readiness

Not every dependency is optional. Classify them by whether the application can keep serving when the dependency is unavailable:

| Dependency Type | Example | Impact on Liveness | Impact on Readiness |
|---|---|---|---|
| Optional dependency | Product recommendations, email delivery, supplementary content | None | Usually none, if a fallback exists or the feature can be omitted. |
| Critical dependency for a subset of endpoints | Inventory service for reservation operations | None | May affect application readiness if most traffic cannot be handled safely; consider splitting services or routes if scope is narrow. |
| Mandatory dependency for every request | Primary database in an application without a degraded mode | Should not govern process restarts | May fail readiness if no request can be served properly. |
| Essential internal resource | Thread pool completely deadlocked, application cannot process requests | May affect liveness if the process is truly unrecoverable | May affect readiness. |

An important point: failing readiness does not mean the pod is restarted. It primarily stops the pod from receiving traffic through the Service. If an application hosts multiple features with different dependency profiles, marking the whole pod unready because one secondary endpoint failed can reduce capacity for healthy endpoints. In such cases, consider splitting features into separate services or handling degradation per request via circuit breakers and fallbacks.

## Separating Dependency Status into a Dedicated Health Group

You can create a dedicated health group to monitor dependencies or circuit breakers without tying them to Kubernetes probes:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: inventoryCircuitBreaker,recommendationService
          show-details: when-authorized
~~~

Here `inventoryCircuitBreaker` and `recommendationService` are health contributor bean names provided by the application. The group endpoint can be accessed at `/actuator/health/dependencies`, depending on Actuator configuration and security policies.

A separate health group allows operations teams to view dependency status without turning it into a process liveness condition. Restrict access to detailed health endpoints and avoid exposing sensitive information such as internal URLs, credentials, or exceptions containing request data.

When using Resilience4j, circuit breaker state can be tracked through metrics and event listeners. When exposure in a dedicated health group is desired, the application can provide a `HealthIndicator` that reads registry state. The indicator should read local state quickly without making synchronous network calls to the dependency on every check.

Illustrative example of a health indicator that only observes circuit breaker state:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventoryCircuitBreaker")
public class InventoryCircuitBreakerHealthIndicator
        implements HealthIndicator {

    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakerHealthIndicator(
            CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Health health() {
        CircuitBreaker breaker =
                registry.circuitBreaker("inventory-read");

        CircuitBreaker.State state = breaker.getState();

        if (state == CircuitBreaker.State.OPEN) {
            return Health.status("DEGRADED")
                    .withDetail("circuitBreaker", state.name())
                    .build();
        }

        return Health.up()
                .withDetail("circuitBreaker", state.name())
                .build();
    }
}
~~~

This indicator is intended for diagnostics. When used in a separate health group, the `DEGRADED` status signals that the dependency's circuit is open. Do not add this indicator to the liveness group. If the system customizes Actuator status mappings, define the HTTP status for `DEGRADED` clearly and secure the endpoint with access controls.

## Combining Circuit Breakers and Fallbacks for Optional Dependencies

Health probes do not replace per-call protection mechanisms. For an optional dependency, place a circuit breaker on the client or call flow and provide a suitable fallback.

~~~java
@Service
public class ProductPageService {

    private final RecommendationClient recommendationClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductPageService(
            RecommendationClient recommendationClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.recommendationClient = recommendationClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductPage load(String productId) {
        Product product = loadCoreProduct(productId);

        List<Recommendation> recommendations =
                circuitBreakerFactory.create("recommendations").run(
                        () -> recommendationClient.findFor(productId),
                        error -> List.of()
                );

        return new ProductPage(product, recommendations);
    }
}
~~~

Data types and methods in this example are illustrative. In a real application, the fallback may return the most recently cached recommendation list, or an empty list if the UI allows omitting recommendations. Core product data is still loaded and returned.

When the circuit breaker transitions to OPEN, recommendation calls are fast-rejected and handled by the fallback. Liveness still shows the `product-api` process is running. Readiness can continue succeeding because the application can still render the product page without recommendations.

Fallbacks must fit the feature's semantics. Do not return an empty list if an empty list means "no matching products" in business terms and users could mistake it for a confirmed result. You can add metadata indicating that recommendations are temporarily unavailable.

## Avoiding Health Checks Adding Load to Dependencies

A common design mistake is having a health indicator call external services directly every time Actuator receives a health request. Kubernetes can invoke probes continuously across all replicas. If every probe calls multiple services, check requests can become significant load, especially while the system is degraded.

Follow these principles:

- Liveness checks internal state only; never call databases, brokers, Redis, or optional HTTP services.
- Readiness checks only conditions genuinely required to accept traffic.
- Dependency indicators should rely on existing state data, short timeouts, and rate limits if network checks are unavoidable.
- Never run long retries inside a health indicator.
- Never let a health check wait on a circuit breaker in `HALF_OPEN` or wait for a dependency request to finish.
- Keep probe endpoints simple, fast, and reachable on the appropriate serving port.

If remote dependencies must be checked, do so via metrics, active monitoring, or a separate health group. One slow health check must not tie up threads and slow down the liveness endpoint.

## Monitoring Degradation Without Restarting the Application

When an optional dependency fails, operations teams need clear signals even while liveness and readiness stay green. Track:

- Number of circuit breakers currently OPEN or HALF_OPEN per dependency.
- Failure rate, slow call rate, and dependency call latency.
- Number of fast-rejected calls.
- Fallback rate and proportion of requests returning degraded data.
- Frequency of the dependency health group reporting DEGRADED.
- Error rates of core endpoints versus optional-dependency endpoints.

Do not rely solely on green liveness to conclude all features are healthy. Liveness answers whether the process can keep running; metrics and the dependency health group provide visibility into external integrations.

Alerts should distinguish:
- **Process unhealthy:** liveness failed; investigate the process or internal resources.
- **Instance not ready:** the application cannot safely accept traffic yet.
- **Dependency degraded:** a dependency is failing or a circuit breaker is OPEN, while the application can still serve other features.
- **Fallback elevated:** the application keeps serving, but many requests receive degraded results.

## Testing Probe Behavior When Optional Dependencies Fail

Test both probe statuses and business behavior. Simulate the recommendations service returning 503, timing out, or refusing connections, then observe the circuit breaker, fallback, and health endpoints.

| Scenario | Liveness | Readiness | Expected Behavior |
|---|---|---|---|
| Recommendations service healthy | UP | ACCEPTING_TRAFFIC | Product page includes recommendation data. |
| Recommendations returns 503 and breaker is OPEN | UP | ACCEPTING_TRAFFIC if core features still work | Fallback omits recommendations or uses cache. |
| Optional email service unavailable | UP | ACCEPTING_TRAFFIC | Requests not requiring email still process; email tasks follow their own policy. |
| Core database unavailable and app cannot serve requests | UP if process is still alive | REFUSING_TRAFFIC | Pod receives no traffic; do not restart merely because the database failed. |
| Process deadlocked or unable to serve health endpoint | May fail | May fail | Kubelet may restart the container once liveness crosses threshold. |
| Application starting up | Startup not yet succeeded | Not yet evaluated | Startup probe delays liveness/readiness. |
| Dependency circuit breaker moves HALF_OPEN then CLOSED | UP | ACCEPTING_TRAFFIC | Probe calls succeed; optional feature resumes operating. |

In integration tests, confirm that dependency failures do not cause `/livez` to fail. Also confirm `/readyz` fails only when the application genuinely cannot accept traffic safely per policy. Do not check only probe status codes; verify business requests still serve core functionality and fallbacks run properly.

## Design Workflow

1. Identify core functionality and optional dependencies for each request flow.
2. Design liveness strictly around internal process health.
3. Design readiness around safely serving traffic, considering only mandatory dependencies.
4. Use a startup probe for applications with long boot times.
5. Enable Spring Boot Actuator health groups and expose appropriate probe endpoints.
6. Separate dependency or circuit breaker status into dedicated health groups/metrics.
7. Apply circuit breakers and fallbacks at clients calling optional dependencies.
8. Never run slow network calls or retries inside liveness/readiness handlers.
9. Test dependency failures, OPEN circuit breakers, fallbacks, readiness, and liveness independently.
10. Configure separate alerts for process health, readiness, dependency degradation, and fallback usage.

Liveness signals whether the process can keep running; readiness signals whether it can accept traffic; dependency status is a separate operational signal. When an optional service fails, circuit breakers and fallbacks should contain the impact to that feature while probes continue reflecting the true state of the application. This separation avoids unnecessary restarts and reduces the risk of an external outage cascading into a system-wide disruption.
