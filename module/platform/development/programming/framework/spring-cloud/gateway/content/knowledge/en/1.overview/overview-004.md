# Request Flow from Client Through the Gateway to a Service

## 1. Where Does the API Gateway Sit in the Processing Flow?

In a microservices system, clients typically know only one shared access point, such as `https://api.example.test`, rather than knowing the addresses of individual order, payment, or user services. **Spring Cloud Gateway** receives HTTP requests at this entry point, selects a target service based on routing rules, executes the necessary filters, and forwards the request. The response from the service travels back through the gateway before reaching the client.

This lesson in the **Overview** chapter on **SPRING_CLOUD_GATEWAY** focuses on answering the question: **which components does an HTTP request actually pass through, at what point, and where can it be modified or blocked?** Route predicates, the filter chain, path/header transformations, and service discovery are placed into a single unified flow. Authentication, rate limiting, circuit breakers, retries, TLS, and request observability are introduced at the exact points where they affect that flow.

The internal component names in this article use **Spring Cloud Gateway Server WebFlux** (typically running on Reactor Netty) as the reference model. The Spring Cloud Gateway Server MVC variant has a different servlet integration mechanism, though its routing and request-filtering goals are similar.

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS request"| G["Gateway HTTP server"]
    G --> P{"Route predicate<br/>matches?"}
    P -->|"No"| N["No matching<br/>route"]
    P -->|"Yes"| F["Filter chain:<br/>pre phase"]
    F -->|"Rejected"| X["Early response<br/>401 / 403 / 429..."]
    F --> U["Build target URL;<br/>discover and select instance"]
    U --> R["Forward request<br/>to microservice"]
    R --> S["Microservice processes"]
    S --> B["Filter chain:<br/>post phase and write response"]
    B -->|"HTTP response"| C
    X --> C
    N -->|"Typically 404"| C
~~~

Key takeaway: **route predicates decide which route a request follows; the filter chain processes the request that matched a route; routing filters perform the forwarding; response processing runs as the result comes back.** The gateway can also reply to the client immediately without calling the target service.

## 2. Six Stages of a Request

| Stage | Component or Mechanism | What Happens |
| --- | --- | --- |
| **1. Ingestion** | HTTP server, WebFlux `WebFilter` (if configured) | Accepts the connection, handles HTTP/TLS at the corresponding layer, and runs WebFlux processors such as Spring Security. A `WebFilter` can reject a request even before route selection. |
| **2. Route lookup** | `RoutePredicateHandlerMapping` | Evaluates predicates across declared routes; selects a matching route and attaches route metadata to the request exchange. |
| **3. Pre-filter execution** | `FilteringWebHandler`, `GlobalFilter`, `GatewayFilter` | Combines and orders filters, then runs pre-forwarding logic: authentication or policy checks, rate limiting, path/header modifications, tracing metadata. |
| **4. Target resolution and invocation** | `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter`, `NettyRoutingFilter` | Builds the outgoing URL; if the URI is `lb://...`, selects an instance; finally sends the HTTP request to the target service. |
| **5. Result reception** | Target service and gateway HTTP client | The service returns status, headers, and body; connection errors, timeouts, or resilience policies may alter the outcome. |
| **6. Post-processing and response** | Post-filters, `NettyWriteResponseFilter` | Adjusts headers/status per configuration, records metrics/logs, and writes the response back to the client. |

### 2.1. Route Predicates Are Checked Before Running Gateway Filters

A **route** consists at minimum of an ID, a target URI, and predicates; it can also have its own filters. A predicate is a condition for selecting a route based on path, HTTP method, host, headers, query parameters, time, and more. For a route with multiple predicates, all conditions must hold for that route to be selected.

For example, `Path=/api/orders/**` and `Method=GET` select `GET /api/orders/42`, but do not select `POST /api/orders/42`. Path modifications performed by `StripPrefix` **happen after** route selection; they do not change the path that was evaluated against `Path`.

If no route matches and no other WebFlux handler processes the request, the client typically receives **404 Not Found**. Do not jump to the conclusion that the backend service returned 404: the request may never have been forwarded.

### 2.2. The Filter Chain Has Two Execution Directions

After matching a route, `FilteringWebHandler` combines two groups of filters:

- **`GlobalFilter`:** applies to every request assigned a route by the gateway, such as recording processing duration or managing correlation IDs.
- **`GatewayFilter`:** attached to a specific route, such as `StripPrefix`, `SetRequestHeader`, `RequestRateLimiter`, or `CircuitBreaker`. Default filters can also apply across multiple routes.

Filters are sorted by **order**. In a typical invocation chain, a filter with a lower order runs its **pre** logic earlier and completes its **post** logic later. A filter can call `chain.filter(exchange)` to proceed, or complete the response immediately to stop the chain. Thus, the same request can be authenticated, have headers added, be routed, have latency measured, and have its response modified at different points.

The **post** phase is not a new call from the client. It is the remainder of the same reactive chain, executed when the downstream call completes (or terminates with an error/cancellation, depending on operators and filters).

### 2.3. `lb://` Is a Target Lookup Step, Not an HTTP Address

The URI `lb://orders-service` denotes a **service ID**. Spring Cloud LoadBalancer requires an instance list from a service discovery mechanism, such as Eureka, Consul, or another `ServiceInstance` source. Only after selecting an instance does the gateway have a concrete address to send the request to, such as `http://10.0.2.15:8080`. To use `lb://`, the application must have appropriate service discovery configured along with Spring Cloud LoadBalancer.

If a static URI such as `http://localhost:8081` is used, the `lb://` instance-selection step is skipped. If no instance can be found for a service, the WebFlux gateway typically returns **503 Service Unavailable** by default (configurable to 404); this error occurs before any backend processes the request.

## 3. Tracing a Concrete Request

Suppose a client calls:

~~~http
GET /api/orders/42?expand=items HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

The gateway has an illustrative route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Source, spring-cloud-gateway
~~~

> The configuration above illustrates the familiar `spring.cloud.gateway.routes` namespace of many Spring Cloud Gateway WebFlux versions. Some newer versions organize properties under `spring.cloud.gateway.server.webflux`. Use the configuration keys corresponding to the Spring Cloud version you are running; the route and filter semantics in the example remain the same.

Assumed progression:

1. **Client → gateway:** The gateway receives `GET /api/orders/42?expand=items`. The HTTPS connection may have TLS terminated at the gateway or at a reverse proxy in front, depending on deployment.
2. **Route selection:** Both `Path=/api/orders/**` and `Method=GET` match. The selected route has ID `orders-api` and logical URI `lb://orders-service`.
3. **Pre-filters:** `StripPrefix=1` removes the first segment `api`, changing the path to `/orders/42`. The query `?expand=items` is preserved. `SetRequestHeader` sets `X-Edge-Source: spring-cloud-gateway` on the forwarded request.
4. **Service discovery:** The gateway asks LoadBalancer to choose an instance of `orders-service`. Suppose the selected instance has address `10.0.2.15:8080`.
5. **Forwarding:** The gateway sends a request corresponding to `GET http://10.0.2.15:8080/orders/42?expand=items`; the service receives the transformed path. Actual Host, connection headers, and forwarding headers depend on proxy configuration. Do not assume every header received from the client is forwarded verbatim.
6. **Service → gateway → client:** The service returns, for example, `200 OK` with the order JSON. The gateway executes the appropriate post-processing steps and writes the response to the client.

You can visualize the boundary before and after the transformation as follows:

| Observation | Illustrative Value |
| --- | --- |
| URL called by client | `https://api.example.test/api/orders/42?expand=items` |
| Selected route | `orders-api` |
| Logical route URI | `lb://orders-service` |
| Path after `StripPrefix=1` | `/orders/42` |
| Selected instance | `10.0.2.15:8080` |
| URL sent down to service | `http://10.0.2.15:8080/orders/42?expand=items` |
| Header set at gateway | `X-Edge-Source: spring-cloud-gateway` |

The IP addresses and responses here are **examples** only, not measurements from a real system.

## 4. Points Where a Request Can Be Stopped or Redirected

The processing flow does not always end with a successful call to the backend. The same request can take the following branches:

| Occurrence Point | Illustrative Condition | Typical Result |
| --- | --- | --- |
| Before routing | Spring Security `WebFilter` fails to authenticate the token | **401 Unauthorized**, no backend call needed |
| During access policy check | Valid identity but insufficient permissions | **403 Forbidden** per applied policy |
| Route selection | No route matches path/method/host | **404 Not Found** if no other handler exists |
| Pre-filter | `RequestRateLimiter` rejects due to exceeding limit | **429 Too Many Requests** by default |
| Load balancing | No available instances remain | Usually **503 Service Unavailable** |
| Calling backend | Connection error, backend failure, or timeout exceeded | May be **5xx** or a fallback response, depending on policy |
| Normal processing | Backend returns a valid `4xx` or `5xx` | Gateway typically forwards that response back; filters can still adjust it |

These status codes are common cases, not immutable guarantees: custom filters, exception handlers, timeout/circuit breaker settings, or fallbacks can change them.

### Authentication and Authorization

The gateway is a convenient place to validate access tokens, block invalid requests, and enforce shared policies. However, **the target service must still check permissions on resources or actions it owns**; validating tokens at the entry point alone does not replace business authorization. Never treat a client-declared header (such as `X-User-Id`) as proof of identity without an authentication mechanism and proper path protection.

### Rate Limiting

The rate limiter usually runs before the routing step. When a threshold is exceeded, the request is rejected immediately, sparing the backend from spending resources on it. With Redis-based configurations, counters/quotas depend on the gateway being able to reach Redis and on how keys are resolved (user, API key, or trusted IP address). Think carefully about behavior when the rate-limiter infrastructure fails.

### Circuit Breaker, Retry, and Timeout

When a service is slow or unhealthy, a circuit breaker can reject certain calls or switch to a fallback if configured. Timeouts cap waiting time; retries can cause **a single client request to generate multiple calls to the backend**. Only enable retries when you understand the operation's idempotency and body replayability: arbitrary retries on order creation or payments can trigger duplicate side effects. Inspect gateway timeouts/circuit breakers alongside backend logs to determine whether a request was actually sent.

### TLS and Headers from Reverse Proxies

The **client → gateway** and **gateway → service** connections are two separate hops; each hop can use HTTP, HTTPS, or mTLS depending on the architecture. If a load balancer/reverse proxy sits in front, `Forwarded` and `X-Forwarded-*` headers are only trustworthy when the proxies sending them are explicitly identified and the gateway is configured to handle them appropriately. Headers describing origin IP, scheme, or identity must never be blindly accepted from the Internet.

## 5. Writing a GlobalFilter to Clearly See Pre/Post

The example below measures the time spent traversing the rest of the chain. The filter starts before calling downstream and logs when the pipeline completes, errors, or is canceled.

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class RequestTimingFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        long start = System.nanoTime(); // pre

        return chain.filter(exchange)
                .doFinally(signal -> { // after the chain finishes
                    long ms = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - start);
                    log.info("method={} path={} status={} durationMs={} signal={}",
                            exchange.getRequest().getMethod(),
                            exchange.getRequest().getURI().getPath(),
                            exchange.getResponse().getStatusCode(),
                            ms,
                            signal);
                });
    }
}
~~~

`return chain.filter(exchange)` is the operation that continues the chain. In an authorization filter, if policy denies the request, the filter can set the status and complete the response instead of calling the chain. This timing example **does not perform authentication** and does not need to call `subscribe()` or `block()` manually; blocking I/O in a reactive processing flow can reduce the gateway's concurrency capacity.

Order `-100` places this filter's pre logic ahead of many filters with higher order values, while `doFinally` runs when everything downstream of it finishes. The measured time is the duration observed at the filter, including forwarding and downstream processing, not solely the microservice's internal execution time. If a request is blocked by a WebFlux `WebFilter` before route selection, the `GlobalFilter` above may not run at all.

## 6. Observing and Troubleshooting Stage by Stage

To trace requests across multiple services, propagate **trace context** such as `traceparent` and use Micrometer Observation/Tracing with corresponding logging. During investigation, useful data includes receipt timestamp, method/path, **route ID**, response status code, processing duration, selected destination, trace ID, and failure cause. Avoid logging access tokens, cookies, personal data, or raw bodies containing sensitive information.

Spring Cloud Gateway can expose request metrics and Actuator endpoints for inspecting routes when the proper components and settings are enabled. For instance, the route list from the Actuator gateway endpoint is useful for confirming the application loaded its configuration; operational endpoints must be secured and never exposed publicly on the Internet.

When troubleshooting, follow this sequence:

1. **Did the request reach the gateway?** Check TLS, DNS, upstream reverse proxies, and access logs. If the error happened before entering the gateway, routes/filters cannot fix it.
2. **Did a route match?** Compare the original request against `Path`, `Method`, `Host` predicates and the order/priority of potentially overlapping routes.
3. **Did a pre-filter block it?** Check security, rate limiters, path transformations, and headers; distinguish a status returned by the gateway from one returned by the service.
4. **Could the target URI be resolved?** For `lb://`, inspect the service ID, registry, instance list, and LoadBalancer status.
5. **What path/headers did the backend receive?** Compare gateway data with the actual request arriving at the service to catch `StripPrefix`, `RewritePath`, or header-forwarding bugs.
6. **Where was the response altered?** Compare the service's status/body against what the client received, factoring in post-filters, timeouts, retries, circuit breakers, and traces.

For example, a client calls `/api/orders/42` while the service only declares `/orders/{id}`: if `StripPrefix=1` is missing, the route can still **match successfully**, the gateway can still **send the request successfully**, yet **the backend returns 404** because it received the wrong path. Distinguishing these two types of 404 speeds up fault isolation.

## 7. Mini Practice: Verifying the Path

You can spin up a mock `orders-service` running on `http://localhost:8081` returning JSON from `GET /orders/42`. To test the flow without service discovery yet, temporarily replace the example route URI with `http://localhost:8081`, keeping the predicates and `StripPrefix=1`.

~~~bash
# Matches route, service receives GET /orders/42?expand=items
curl -i "http://localhost:8080/api/orders/42?expand=items"

# Does not match Method=GET of the example route
curl -i -X POST "http://localhost:8080/api/orders/42"

# Does not match Path=/api/orders/**
curl -i "http://localhost:8080/api/customers/42"
~~~

Assuming the gateway listens on port `8080` and has no other routes/handlers for the last two requests, only the first request is forwarded; the other two receive 404. Logs from `RequestTimingFilter` show requests that **matched a route**, while logs on the service confirm the actual path and the `X-Edge-Source` header. Afterward, switch back to `lb://orders-service` and enable discovery/LoadBalancer to observe the instance-selection step appear between the filter chain and the backend.

**Remember the main flow:** client → WebFlux/TLS → route selection via predicate → pre-filter execution → URL/instance resolution → forwarding to microservice → response reception → post-filter/response writing → client. Mechanisms like security, rate limiting, retries, circuit breakers, and observability each attach to one or more steps in this chain; understanding their exact positions is the foundation for designing and operating a secure API Gateway.
