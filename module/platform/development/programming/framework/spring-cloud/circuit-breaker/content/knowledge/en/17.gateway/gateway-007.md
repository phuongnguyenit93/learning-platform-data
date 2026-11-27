# Coordination Boundaries with Retry Filter, Timeouts, and LoadBalancer

Spring Cloud Gateway is the entry point that accepts client requests and routes them to downstream services. At the gateway, a request can pass through multiple filters: authentication, routing, load balancing, retry, circuit breaker, and time limiters. How these filters coordinate determines how many times a request is retried, which errors are recorded, how long the client waits, and whether a retry attempt can be sent to another instance.

The Gateway must protect the system at the ingress boundary, while downstream services still need their own protection for the calls they make. Therefore, you must distinguish the Gateway's retry policy from Spring Cloud LoadBalancer's retry and in-service retries, while setting timeouts so total processing time does not exceed the client's response budget.

This lesson focuses on the coordination boundaries among the Gateway Retry filter, the CircuitBreaker filter, HTTP client timeouts, and LoadBalancer. Examples use reactive Spring Cloud Gateway and Resilience4j as the Circuit Breaker provider.

## 1. The Gateway Filter Chain Is Where Policies Meet

A request passing through the Gateway typically follows this general flow:

~~~text
Client
  |
  v
Spring Cloud Gateway
  |
  +--> Global filters
  |
  +--> Route filters
  |      |
  |      +--> Authentication / authorization
  |      +--> CircuitBreaker
  |      +--> Retry
  |      +--> HTTP routing
  |
  v
LoadBalancer: selects service instance
  |
  v
HTTP client: connect timeout / response timeout
  |
  v
Service instance
~~~

The Gateway combines GlobalFilters and route GatewayFilters into a single execution chain. Filters earlier in the chain can process the request before invoking the next filter; after downstream filters complete, execution unwinds back to handle responses or exceptions.

The actual runtime order depends on filter ordering after sorting. Route filters are typically listed in the route definition, while GlobalFilters and ordered filters also participate in the chain. When changing the order of Retry and CircuitBreaker, inspect the effective filter order in the running Gateway version rather than relying solely on YAML reading order.

Each policy should have one clear responsibility:

- Retry decides whether to re-send a request when encountering a recoverable error.
- Circuit Breaker decides whether to keep letting requests through to a dependency showing signs of unhealthiness.
- Timeout bounds the duration of establishing a connection or waiting for a response.
- LoadBalancer selects the target service instance and may apply its own instance-level retry policy.

## 2. Spring Cloud Gateway's Retry Filter

The Retry GatewayFilter lets the Gateway re-execute a request when the response has a status or exception belonging to configured groups. The filter supports bounding retry count, HTTP methods, status codes, status series, exceptions, and backoff.

Example of a route that only retries GET requests when the service returns a server error:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                series:
                  - SERVER_ERROR
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

In the example, retries equal to 2 means up to two retries after the initial call, i.e., up to three attempts total. Backoff starts at 100 ms and grows by a factor of 2, capped at 500 ms. These values are examples for practice; choose them according to your latency budget and service load capacity.

Key properties:

| Property | Meaning |
| --- | --- |
| retries | Number of retries after the initial call |
| methods | HTTP methods permitted to retry |
| series | Status series eligible for retry, e.g., SERVER_ERROR |
| statuses | Specific HTTP statuses eligible for retry |
| exceptions | Exceptions eligible for retry |
| backoff.firstBackoff | Wait duration before the first retry |
| backoff.maxBackoff | Upper bound on backoff duration |
| backoff.factor | Multiplier increasing the wait duration |
| backoff.basedOnPreviousValue | Whether the next backoff is computed from the previous value |

Gateway Retry is usually suitable for GET or operations that already have idempotency mechanisms. Do not retry POST, PATCH, or write requests merely upon seeing a 5xx error. The server may have executed the operation while the response was lost in transit; re-sending can create duplicate orders or transactions.

If you need to retry requests with a body, consider how the Gateway buffers and replays the body. Retaining the body can consume memory, especially for large requests or high traffic. Bound request size, retry counts, and enable retries only for APIs with explicit idempotency rules.

## 3. The CircuitBreaker Filter at the Gateway

Spring Cloud Gateway provides the CircuitBreaker GatewayFilter to wrap route calls with the Spring Cloud CircuitBreaker abstraction. With the Resilience4j provider, the name in the filter is linked to the corresponding Circuit Breaker configuration.

Example:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
                statusCodes:
                  - 500
                  - 502
                  - 503
                  - 504
~~~

The name inventory is the Circuit Breaker instance name. Thresholds can be configured in application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

The statusCodes list for the Gateway CircuitBreaker filter specifies HTTP statuses that should be treated as errors. If appropriate statuses are not configured, an HTTP 5xx response can be treated as a normally completed response at the reactive layer, depending on the execution path and provider. Explicitly configure the business-appropriate statuses to count toward the failure rate.

A Fallback URI of the form forward:/... forwards the request internally to a handler in the Gateway application itself. Example fallback controller:

~~~java
package com.example.gateway.fallback;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
public class InventoryFallbackController {

    @GetMapping("/fallback/inventory")
    public Mono<ResponseEntity<Map<String, String>>> inventoryFallback() {
        return Mono.just(
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                    "service", "inventory",
                    "status", "temporarily_unavailable"
                ))
        );
    }
}
~~~

Fallbacks should return meaningful information to clients without leaking stack traces, internal hostnames, or sensitive data. If business rules allow, the fallback can return cached data or a degraded response. When a safe result cannot be provided, return a controlled error.

## 4. Ordering of Retry and CircuitBreaker Changes Statistical Samples

Retry and CircuitBreaker can be nested in two ways. Filter order determines whether the Circuit Breaker records each individual attempt or the final outcome of the entire retry sequence.

### 4.1. Retry Outside, CircuitBreaker Inside

~~~text
Request
  |
  v
Retry filter
  |
  +--> attempt 1 --> CircuitBreaker --> service
  |
  +--> attempt 2 --> CircuitBreaker --> service
  |
  +--> attempt 3 --> CircuitBreaker --> service
~~~

When the Retry filter sits before the CircuitBreaker filter in the effective chain, Retry wraps downstream processing and can re-run that chain. Every attempt passes through the Circuit Breaker, so each attempt outcome can become a sample in the sliding window.

This approach reflects dependency health at the per-attempt level. One logical request with three failed attempts can generate three failure samples. The Circuit Breaker can reach minimumNumberOfCalls faster, but the failure rate no longer equals the rate of failed user requests.

Watch out for CallNotPermittedException. Once the Circuit Breaker is OPEN, subsequent attempts can be rejected immediately. Do not configure Retry to catch every exception and keep retrying CallNotPermittedException, because the request was already rejected by the protection mechanism and immediate retries are futile.

### 4.2. CircuitBreaker Outside, Retry Inside

~~~text
Request
  |
  v
CircuitBreaker filter
  |
  v
Retry filter
  |
  +--> attempt 1 --> service
  |
  +--> attempt 2 --> service
  |
  +--> attempt 3 --> service
  |
  v
Final outcome
~~~

When the CircuitBreaker filter sits before the Retry filter in the effective chain, the Circuit Breaker wraps the entire retry sequence. It records a single outcome after Retry finishes.

If the first attempt fails but the second succeeds, the Circuit Breaker receives one success outcome. If all attempts fail, the Circuit Breaker records one failure. This approach aligns closely with the final logical request failure rate.

This approach also causes the Circuit Breaker to measure total duration across attempts and backoff. A request can be classified as a slow call even if each individual attempt was fast.

### 4.3. Choosing Order by Objective

| Objective | Order to consider |
| --- | --- |
| Measure errors per individual call to the service | Retry outside, CircuitBreaker inside |
| Measure final outcome of the logical request | CircuitBreaker outside, Retry inside |
| Measure user-experienced latency including backoff | CircuitBreaker outside, Retry inside |
| React quickly when consecutive attempts fail | Retry outside, CircuitBreaker inside |

When a fallback is present, account for the fallback's position in the chain. If CircuitBreaker is inside Retry and the fallback turns an error into a success response, Retry may treat that attempt as complete and stop retrying. If you want Retry to handle errors first and only fall back afterward, place the fallback at the outer boundary of the retry chain or design statuses/exceptions so Retry still recognizes the failure.

## 5. Gateway HTTP Client Timeouts

Timeouts limit how long the Gateway waits for connections and responses from downstream services. They are the direct mechanism for releasing waiting requests when a dependency hangs or responds too slowly.

There are two types of timeouts that typically need configuration:

- **Connect timeout:** maximum time to establish a connection to a service instance.
- **Response timeout:** maximum time waiting for a response over an established connection.

Global configuration:

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 1000
        response-timeout: 2s
~~~

Connect timeout in this example is 1000 ms. Response timeout is 2 seconds.

You can set route-specific timeouts via metadata:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          metadata:
            connect-timeout: 300
            response-timeout: 800
~~~

The metadata connect-timeout and response-timeout values in the example are in milliseconds. Check configuration rules for your specific version of Spring Cloud Gateway.

The HTTP client timeout bounds a single exchange with the service. If Retry runs multiple times, total request processing time can exceed response-timeout because each attempt can consume its own timeout budget plus backoff between attempts.

For example, with two retries, each attempt waiting up to 800 ms, and backoffs of 100 ms and 200 ms:

\[
3 \times 800\text{ ms} + 100\text{ ms} + 200\text{ ms}
= 2{,}700\text{ ms}
\]

Actual total time can also include instance selection, filter processing, serialization, and other overhead. Therefore, set an overall deadline at the client or ingress matching the API's latency budget.

## 6. Distinguishing Timeout from Slow-Call Threshold

Timeouts and slow-call thresholds are related but do not replace each other.

| Mechanism | Role |
| --- | --- |
| HTTP connect timeout | Stops waiting when a connection cannot be established within the allowed time |
| HTTP response timeout | Limits wait time for a response at the HTTP client |
| Circuit Breaker slowCallDurationThreshold | Marks a call as completed yet taking too long |
| Circuit Breaker failureRateThreshold | Opens the circuit when failure rate reaches the threshold |
| Retry backoff | Waits between retry attempts |

Slow-call threshold only classifies calls when the Circuit Breaker evaluates outcomes. It does not cancel an HTTP request by itself or replace response timeout. If the HTTP client lacks an appropriate timeout, calls can hold resources far too long before the Circuit Breaker ever receives an outcome to record.

When a timeout occurs, the exception from the HTTP client can be recorded as a failure by the Circuit Breaker. Verify actual exceptions and configure record/ignore exceptions to classify errors accurately. A timeout at the gateway also does not guarantee the downstream service cancelled its work; the server may still be executing if cancellation is not propagated or supported.

## 7. LoadBalancer and the lb:// URI

The Gateway can route to a logical service name instead of a fixed hostname:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
~~~

The URI lb://inventory-service instructs Spring Cloud LoadBalancer to look up instances registered under the service ID inventory-service. Instance selection happens at runtime based on the instance list and configured LoadBalancer strategy.

The application typically needs the Spring Cloud LoadBalancer starter and a source of service instances, such as DiscoveryClient or static instance configuration for test environments. If no suitable instance is found, the Gateway can return a routing error rather than calling a specific host.

LoadBalancer and Gateway Retry have different boundaries:

- Gateway Retry repeats the request/filter chain when a response or exception matches retry conditions.
- LoadBalancer Retry focuses on retrying when selecting or invoking a service instance, potentially according to a policy to retry the same instance or another instance.
- In-service retry applies to calls made by the service itself to its own downstream dependencies.

Do not assume that every Gateway Retry is guaranteed to pick a new instance. Whether the LoadBalancer filter re-runs and how instances are chosen depends on effective filter order and the integration mechanism. If the requirement is to try a different instance after the current one fails, configure and test Spring Cloud LoadBalancer's retry policy instead of relying on Gateway Retry.

## 8. Avoiding Multiplying Retries Between Gateway and LoadBalancer

If both Gateway and LoadBalancer retry, the actual number of calls can exceed the count declared at a single layer.

For example, the Gateway permits two retries after the first attempt, meaning up to three downstream executions. If within each execution LoadBalancer can make three instance attempts, the total number of requests sent can multiply across the two limits:

\[
3 \times 3 = 9 \text{ max attempts}
\]

This is an estimate for when both layers exhaust their full retry counts; actual behavior depends on error conditions, filter order, and retry policies.

To avoid load amplification:

1. Pick one primary layer responsible for retrying each error type.
2. Use Gateway Retry for responses/exceptions that the gateway can evaluate and handle safely.
3. Use LoadBalancer Retry when the specific goal is retrying service instances under a same-instance or next-instance policy.
4. Cap attempt counts across all layers.
5. Add backoff and jitter if many clients may retry concurrently.
6. Account for total attempts and maximum wait time within the latency budget.
7. Monitor logical requests, HTTP attempts, and service instance switches separately.

## 9. Example Coordinating CircuitBreaker, Retry, Timeouts, and LoadBalancer

An Inventory route can place CircuitBreaker outside Retry so the Circuit Breaker tracks the final outcome of the logical request. The Gateway HTTP client bounds connect and response wait times. The lb:// URI lets LoadBalancer select instances.

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 500
        response-timeout: 800ms
      routes:
        - id: inventory
          uri: lb://inventory-service
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
                statusCodes:
                  - 500
                  - 502
                  - 503
                  - 504

            - name: Retry
              args:
                retries: 2
                methods:
                  - GET
                series:
                  - SERVER_ERROR
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 300ms
                  factor: 2
                  basedOnPreviousValue: false

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

This configuration illustrates CircuitBreaker placed before Retry in the route filter list. Verify the effective filter chain order in your running version. With this ordering, the Circuit Breaker is expected to wrap Retry processing and receive the final outcome of the retry sequence. If you want the Circuit Breaker to record every attempt, intentionally alter the filter order and re-verify fallback behavior.

The 800 ms response-timeout bounds wait time per HTTP exchange in Gateway configuration. Two retries plus backoff can push total time beyond 800 ms. Therefore, clients calling the Gateway need a deadline suited to the total budget, rather than copying a single attempt's response-timeout.

The Fallback URI forwards requests internally to the /fallback/inventory endpoint. If Retry cannot recover from failures, the Circuit Breaker receives the final outcome and can transition to fallback. When the Circuit Breaker is OPEN, new requests can go straight to fallback without calling any service instance.

## 10. Fallbacks and Status Codes Must Agree

A fallback at the Gateway is a contract with the client. Decide which responses represent degraded data, which signal temporary dependency unavailability, and which tell clients to retry later.

Some principles:

- Do not return HTTP 200 for incomplete data if clients could mistake it for an accurate result.
- Return HTTP 503 when functionality cannot be served and the client may retry later.
- If returning cached data, clearly mark stale data or degraded status.
- Never put exception messages, stack traces, or internal service addresses in responses.
- Configure the CircuitBreaker filter's statusCodes to match statuses that should count toward failure rate.
- Do not let fallback mask errors before Retry has a chance to act, if the goal is to retry first and fall back only afterward.

If fallback executes in a filter located inside Retry, Retry may treat the fallback response as a completed result and stop retrying. If you want Retry to handle failures first, place fallback outside the retry boundary or ensure the fallback response is still recognized by Retry as a retryable condition.

## 11. Protecting Write Requests and Requests with Bodies

Gateway Retry is easier to apply to GET because read operations can usually be repeated without side effects. For POST or PATCH, do not retry based solely on 5xx statuses.

Before retrying a write request, require:

- A unique idempotency key for the business operation.
- A mechanism storing processing outcomes by idempotency key in the target service.
- Rules for handling repeated submissions of the same key.
- Bounds on body size and memory used to replay requests.
- Verification of whether the request was already processed by the target service before resending.

Without idempotency, a timeout can occur after the service has committed a transaction. The Gateway cannot tell whether the operation succeeded on the server. Retrying can create a duplicate record or transaction.

## 12. Monitoring and Diagnostics at the Gateway Boundary

Observe both logical requests and underlying attempts. Useful metrics include:

| Metric | Meaning |
| --- | --- |
| Request count by route | Number of requests clients send to the Gateway |
| Retry attempts | Number of times the Gateway retried a request |
| Retry exhaustion | Number of requests that exhausted all retries |
| Circuit Breaker state | Share of time spent in CLOSED, OPEN, and HALF_OPEN |
| Circuit Breaker failure/slow-call rate | Health of the supplier wrapped by the Circuit Breaker |
| Timeout count | Number of connect or response timeouts |
| LoadBalancer selected instance | Instance chosen for each attempt |
| Fallback count | Number of requests handled via fallback |
| End-to-end latency | Actual time the client waited |

Logs should contain route ID, correlation ID, trace ID, service ID, and attempt number if available. Never log Authorization headers or access tokens. For distributed tracing, use an instrumented HTTP client to propagate trace context to downstream services.

When investigating a slow request, identify where time was spent: waiting for instance selection, connect, response, backoff, or fallback. A request with high total latency is not necessarily caused by slow service processing; it may have gone through multiple attempts and multiple backoff intervals.

## 13. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Requests sent too many times | Retries enabled simultaneously at Gateway, LoadBalancer, and service | Pick a primary retry layer and calculate total attempts |
| Circuit Breaker opens too slowly | Circuit Breaker is outside Retry and receives only one sample per retry chain | Adjust minimumNumberOfCalls or pick the right measurement boundary |
| Circuit Breaker opens too fast | Circuit Breaker is inside Retry and records each attempt in the sliding window | Evaluate failure rate at attempt level and tune thresholds |
| Retry does not run | Status or exception does not match configuration | Check actual responses, series, statuses, exceptions, and methods |
| Fallback runs before Retry finishes | Fallback sits inside the Retry boundary | Adjust filter order or fallback placement |
| Requests exceed client deadline | Each attempt has its own timeout plus backoff | Compute total latency budget and set an overall deadline |
| Service instance not found | Wrong service ID or discovery has not supplied instances | Check lb:// URI and service instance source |
| Retries always hit the same instance | Gateway Retry makes no guarantee to pick another instance | Configure LoadBalancer retry policy and observe selected instances |
| POST creates duplicate transactions | Retrying write requests without idempotency | Use an idempotency key or disable retries for that operation |
| HTTP 5xx does not raise Circuit Breaker failure rate | Missing appropriate statusCodes in Gateway CircuitBreaker filter | Add statuses that should count as errors |

## 14. Policy Design Process for a Route

When adding a new route, follow this sequence:

1. Identify the service ID and discovery source LoadBalancer will use.
2. Set connect timeout and response timeout according to the route's latency budget.
3. Determine which request methods are safe to retry.
4. Choose recoverable statuses and exceptions; cap retry counts.
5. Decide whether the Circuit Breaker measures per-attempt or final request outcomes.
6. Set filter order and fallback placement to match that goal.
7. Decide whether LoadBalancer needs to try another instance and avoid unintended retry multiplication.
8. Test slow services, 5xx responses, missing instances, OPEN Circuit Breaker, and fallbacks.
9. Measure request count, attempt count, timeouts, fallbacks, and end-to-end latency before rollout.

The Gateway is the request coordination boundary between clients and downstream services. The Retry filter handles request retries, timeouts bound wait times, the CircuitBreaker filter cuts off requests when a dependency is unhealthy, and LoadBalancer picks target instances. When responsibilities, filter ordering, attempt counts, and latency budgets are clearly defined, Spring Cloud Gateway can recover from transient errors without amplifying load or making clients wait beyond allowed limits.

## References

- [Spring Cloud Gateway reference](https://docs.spring.io/spring-cloud-gateway/reference/)
- [Spring Cloud Gateway Retry GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html)
- [Spring Cloud Gateway CircuitBreaker GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter.html)
- [Spring Cloud Gateway HTTP timeouts](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html)
- [Spring Cloud LoadBalancer reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
