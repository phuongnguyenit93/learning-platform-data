# Role of the CircuitBreaker Filter at the Gateway Boundary

## Gateway as a Protective Boundary in Front of Services

In a microservices architecture, Spring Cloud Gateway receives requests from clients, selects a route, and forwards requests to downstream services. If a dependent service is slow or unavailable, the Gateway may continue receiving high request volume and forwarding it to a degraded dependency. Those requests hold connections, increase latency, and can cause the failure to cascade to other components.

The CircuitBreaker GatewayFilter places a protection layer directly on the route. The filter uses Spring Cloud Circuit Breaker to observe the results of forwarding to the target service. When the failure rate reaches the threshold, the breaker opens and the Gateway rejects new calls to that route during the protection window. If configured, the Gateway routes the request to a fallback URI to return an alternative response.

The primary role of the filter is to protect the routing boundary:

- Reduce the number of requests continuing to reach a failing service.
- Reduce waiting time for new requests when the breaker is already `OPEN`.
- Allow the Gateway to return a structured response or forward to a fallback processing flow.
- Create a centralized observation point per route or per downstream dependency.

A Gateway filter does not fix errors in the target service, nor does it guarantee that every internal call in the system is protected. A service may still need its own Circuit Breaker when calling a database, a message broker, or another microservice.

## Processing Flow of the CircuitBreaker Filter

For a route configured with CircuitBreaker, the high-level processing flow is as follows:

1. The client sends a request to the Gateway.
2. The route predicate selects the matching route, for example `/catalog/**`.
3. `GatewayFilterChain` performs the forwarding call to `catalog-service` inside a reactive circuit breaker.
4. The filter records the success result, exception, or HTTP status configured as a failure.
5. When the failure rate exceeds the threshold after the minimum number of calls is reached, the breaker transitions to `OPEN`.
6. In the `OPEN` state, new calls are rejected before being forwarded to the target service; the Gateway can route the request to a fallback URI.
7. After the wait duration, the breaker can enter `HALF_OPEN` to allow a few trial calls and evaluate recovery capability.

The filter typically uses `ReactiveCircuitBreakerFactory`, because Spring Cloud Gateway runs on WebFlux and Reactor. Therefore, the application needs a reactive Circuit Breaker starter matching the chosen provider. You should not introduce blocking calls into the filter chain or call `block()` to wait for results on the event loop.

## Required Dependencies

For a reactive Gateway using Resilience4j, the application typically needs the Gateway starter and the Circuit Breaker Reactor Resilience4j starter. Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

Manage Spring Boot and Spring Cloud versions using a compatible BOM. Artifact names and Gateway packaging may vary across release trains; use dependency management for the exact project version and verify the runtime dependency graph. If the application uses another provider, choose the corresponding reactive starter instead of adding Resilience4j just because this example uses it.

## Declaring the CircuitBreaker Filter on a Route

Example of a route to the catalog service via service discovery:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: lb://catalog-service
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogGateway
                fallbackUri: forward:/fallback/catalog
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
```

Key properties:

| Property | Role |
| --- | --- |
| `name` | Name of the Circuit Breaker created via the factory. This is also the identifier used to link with provider configuration and metrics. |
| `fallbackUri` | URI used when a call fails or is rejected by the breaker. For a Gateway filter, the common form is `forward:/...` to forward internally to a handler inside the Gateway application itself. |
| `statusCodes` | List of downstream response HTTP statuses treated as failures for the Circuit Breaker to record. |

`lb://catalog-service` requires appropriate load balancing and service discovery components. If the route uses a static URI such as `http://localhost:8081`, the CircuitBreaker configuration still works, but no load balancer is needed for that route.

The statuses `500`, `502`, `503`, and `504` in the example are chosen because they typically indicate processing failures or unavailability of the dependency. You should not automatically treat every 4xx code as an infrastructure failure. `400` may be an invalid request, `401` or `403` may be an authentication or authorization issue, and `404` may be a normal business result. Only add a status to `statusCodes` when the API contract defines it as a signal that should open the circuit.

## Configuring Resilience4j Thresholds by Filter Name

When using the Resilience4j provider, the name in `name` can be used to declare a Circuit Breaker instance:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

With this configuration, the Circuit Breaker evaluates up to the 20 most recent outcomes and only begins calculating the rate once at least 10 calls have been recorded. If the failure rate reaches or exceeds 50%, the breaker can transition to `OPEN`. After 15 seconds, it can transition to `HALF_OPEN` and permit up to three trial calls according to Resilience4j's policy.

The instance name must match `catalogGateway` in the route filter exactly. If the names do not match, the filter may use the default configuration or another instance depending on how the provider creates the breaker. When investigating configuration, inspect the ID received by the factory and the metrics exported under that ID.

## Creating a Fallback Handler in the Gateway

`fallbackUri: forward:/fallback/catalog` forwards internally to a handler inside the Gateway application. Example of a reactive controller returning status 503 along with a meaningful payload:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    public Mono<ResponseEntity<Map<String, String>>> catalogFallback() {
        Map<String, String> body = Map.of(
            "code", "CATALOG_TEMPORARILY_UNAVAILABLE",
            "message", "The catalog service is currently unable to process the request."
        );

        return Mono.just(ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body));
    }
}
```

The fallback endpoint is part of the Gateway application, not an endpoint of the catalog service. It must be designed not to call back into the failing route. If the handler calls the same dependency through another route, the fallback can create a loop or continue sending load to a degraded service.

Returning HTTP 503 in the example helps the client understand that the service is temporarily unavailable. You should not always return HTTP 200 just to avoid display errors; doing so misleads clients, monitoring, and retry systems about the outcome. If valid cached data or a business alternative is available, the handler can return the corresponding result, but it should clearly indicate the freshness and status of the data.

## Which Errors Does the CircuitBreaker Filter Handle?

There are two main groups of signals:

- **Exceptions from the forwarding process:** connection errors, timeouts, or exceptions thrown by the HTTP client can be fed into the Circuit Breaker according to the provider policy.
- **HTTP statuses from responses:** statuses declared in `statusCodes` are treated by the filter as failures for Circuit Breaker evaluation.

A 500 response does not necessarily turn into an exception automatically in every HTTP client or every filter chain. `statusCodes` tells the Gateway which response statuses should be counted as failures. Conversely, a 404 status not in the list is usually treated as a normal response for the Circuit Breaker, even though the application can still return 404 to the client.

Status classification must align with business semantics. For example, if the catalog service returns 404 when a product does not exist, opening the circuit on 404 could block other valid requests as well. If an API returns 429 when rate-limited, the operations team might want to treat it as an overload signal and include it in the failure list. Align on a shared interpretation between the Gateway, clients, and downstream services.

## Scope of the Breaker: Per Route and Failure Domain

A Circuit Breaker at the Gateway usually represents a dependency or a route. All requests passing through the same breaker name share the statistical window and state within the same Gateway process. If two routes have different failure domains yet share the same breaker name, failures on one route can cause the other route to open under the same state.

For example:

| Route | Dependency | Suggested breaker name |
| --- | --- | --- |
| `/catalog/**` | `catalog-service` | `catalogGateway` |
| `/orders/**` | `order-service` | `orderGateway` |
| `/profiles/**` | `profile-service` | `profileGateway` |

Using distinct names helps configure thresholds, track metrics, and investigate incidents per dependency. Only share a name when routes truly belong to the same policy and failure domain.

Resilience4j state normally resides in the memory of each Gateway process. If the Gateway runs multiple replicas, each replica can have its own breaker window and state; you should not assume all replicas transition to `OPEN` at the same time. Therefore, metrics should be aggregated by instance and route, and system-wide traffic limits must account for the number of replicas.

## Position of the Gateway Filter in a Multi-Layer Protection System

The Gateway Circuit Breaker protects incoming external requests before they enter services. It does not replace Circuit Breakers inside individual services. A request may pass through the Gateway into `order-service`, and from there call `payment-service`. If the Gateway only protects the route to `order-service`, failures on the internal call from order to payment still need to be handled inside `order-service`.

You can visualize the layers as follows:

```text
Client
  |
  v
Spring Cloud Gateway
  |  CircuitBreaker filter for the route
  v
Order Service
  |  CircuitBreaker for internal dependencies
  v
Payment Service
```

The Gateway also does not automatically limit concurrent requests like a Bulkhead. When you need to limit concurrency or protect connection pools, configure a Bulkhead or resource limits at the appropriate layer. Timeouts on the HTTP client or TimeLimiter are still necessary so in-flight calls do not hold resources indefinitely.

## Filter Order, Retries, and Fallbacks

The Gateway allows combining multiple filters on the same route, but order and scope of application can affect the outcome. If using Retry alongside CircuitBreaker, clearly define how many attempts a single business request may send to the dependency. Retries can increase load while a service is degraded; the Circuit Breaker should observe outcomes according to the intended policy.

Do not stack multiple Retry layers around a route without bounding attempt counts, backoff, and deadlines. Check the filter order in your exact Gateway version, then test 5xx responses, connection exceptions, open breaker states, and fallback failures. A fallback should be a controlled termination point, not another route looping back to the same dependency.

## Observing the CircuitBreaker Filter

Track the Circuit Breaker state separately from the outcome received by clients. Useful indicators include:

- Breaker state by route name: `CLOSED`, `OPEN`, or `HALF_OPEN`.
- Counts of recorded calls, successes, failures, and rejections when the circuit is open.
- Failure rate, slow-call rate, and number of trial calls in `HALF_OPEN`.
- Number of times the Gateway fell back and number of times the fallback handler itself failed.
- Latency of the primary route and latency of the fallback.
- Final HTTP status returned to the client.

An HTTP 503 produced by a fallback does not tell you for sure whether the breaker was already open or the supplier just timed out. To determine the root cause, correlate Resilience4j events, Gateway logs, and request traces. Use the breaker name and route ID as bounded labels; avoid putting full URLs, user IDs, or exception messages into metric tags.

If using Spring Boot Actuator and Micrometer, verify that metrics/health endpoints are enabled and properly secured. Do not expose management endpoints publicly just to inspect Circuit Breaker state. Logs should record the route, breaker name, error type, and correlation ID, while avoiding tokens, cookies, or sensitive request data.

## Testing the Gateway CircuitBreaker

Test against a real running Gateway with a mock target service that can return specific statuses or delay responses. Minimum scenarios:

| Scenario | Expected verification |
| --- | --- |
| Dependency returns 200 | Response passes through normally; breaker records a success. |
| Dependency returns 503 and status is declared | Breaker records a failure and fallback is invoked as configured. |
| Dependency returns 404 not in `statusCodes` | 404 is forwarded to the client and not counted as a failure merely for being 4xx. |
| Unable to connect to dependency | Exception is recorded per provider policy and fallback executes. |
| Breaker is already `OPEN` | New requests are not forwarded to the dependency; fallback URI is used if configured. |
| Fallback handler returns 503 | Client receives a meaningful status; fallback response metric increments. |
| Fallback handler also fails | Fallback error is observed separately without creating a route loop. |
| Multiple Gateway replicas | Confirm breaker state can differ across processes and metrics carry the appropriate instance tag. |

When testing, do not check only the fallback body. Verify the actual number of requests reaching the dependency, the breaker state, the rejection count, and the final status. This distinguishes a filter actively protecting a dependency from a fallback controller that merely happens to return a response.

## Common Configuration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Missing reactive Circuit Breaker starter or provider | Gateway cannot create the reactive factory or the filter does not work as expected. | Check starter, runtime classpath, and auto-configuration. |
| `name` does not match configured instance | Breaker uses default configuration or the wrong policy. | Match the filter name against the Resilience4j instance name. |
| `statusCodes` omitted for statuses needing protection | Error responses may not be counted as failures under the desired policy. | List statuses based on the API contract. |
| Treating every 4xx as a dependency failure | Invalid requests or business outcomes can trip the circuit. | Only record statuses that genuinely indicate dependency issues. |
| Fallback calls back into the failing route | Creates a loop or keeps increasing load on the dependency. | Use an internal handler or an independent backup source. |
| Sharing a breaker name across different failure domains | One dependency's failure affects unrelated routes. | Separate breakers per dependency or intentional route group. |
| Monitoring only the final status | Fallback can mask incidents behind the Gateway. | Monitor breaker metrics, primary route metrics, and fallback metrics together. |

The CircuitBreaker GatewayFilter provides a valuable protection layer at the system entry boundary: it reduces requests sent to degraded dependencies and allows the Gateway to return controlled fallback responses. For this protection layer to work properly, choose breaker names by failure domain, classify statuses appropriately, configure loop-free fallbacks, and observe primary route outcomes separately from fallback outcomes. Downstream services still need to protect their own internal dependencies.
