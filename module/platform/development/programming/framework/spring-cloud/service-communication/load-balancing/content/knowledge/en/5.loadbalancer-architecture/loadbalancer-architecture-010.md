# The Boundary Between Instance Selection and HTTP Execution

In the **Spring Cloud LoadBalancer** architecture, two very different decisions occur when one microservice calls another:

1. **Instance selection:** what logical service is requested, which `ServiceInstance` candidates exist, and which instance should be chosen?
2. **HTTP execution:** once the target address is known, how is the connection opened, how is the request sent, how long to wait for a response, and how are network errors or HTTP status codes handled?

Separating these two parts pinpoints where to configure routing algorithms, discovery, health checks, retries, timeouts, and error observability. Spring Cloud LoadBalancer handles **target selection** on the client side; transmitting HTTP data to that target is performed by the HTTP client and its underlying transport layer.

## 1. Which Components Does a Request Pass Through?

Suppose `order-service` calls the catalog service via a logical URL:

~~~http
GET http://catalog-service/products/42
~~~

The system has two replicas of `catalog-service`:

| Service ID | Instance ID | Physical URI |
|---|---|---|
| `catalog-service` | `catalog-1` | `http://10.0.1.21:8081` |
| `catalog-service` | `catalog-2` | `http://10.0.1.22:8082` |

When the HTTP client has LoadBalancer integration enabled, it recognizes `catalog-service` as a **service ID**, requests a `ServiceInstance` selection, and sends the request to the chosen instance's URI. For example, if `catalog-2` is chosen, the target call becomes:

~~~http
GET http://10.0.1.22:8082/products/42
~~~

Even though the initial URL looks like a normal HTTP URL, the `catalog-service` hostname here is a logical identifier for LoadBalancer to look up an instance; OS-level DNS does not need to resolve `catalog-service` to an IP address in the usual way when the integration is working properly.

~~~mermaid
flowchart TD
    A["Business code<br/>GET http://catalog-service/products/42"]
    B["LoadBalancer integration<br/>interceptor / filter / HTTP adapter"]
    C["ServiceInstanceListSupplier<br/>candidate list"]
    D["LoadBalancer selector<br/>picks catalog-2"]
    E["HTTP integration<br/>builds target URI"]
    F["HTTP transport<br/>DNS, TCP, TLS if needed"]
    G["Server catalog-2<br/>10.0.1.22:8082"]
    H["HTTP response or error"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> A
~~~

This diagram illustrates responsibilities at a conceptual level. In practice, integrations may coordinate selection and execution across multiple interfaces or adapters.

## 2. Instance Selection: From Service ID to ServiceInstance

The **input** to the selection process is typically the service ID (e.g., `catalog-service`), optionally accompanied by a request context for applying routing policies. The **output** is a `ServiceInstance` representing the chosen endpoint, or a result indicating no suitable instance exists.

Three primary responsibilities belong here:

1. **Supplying candidates:** `ServiceInstanceListSupplier` returns the instance list for the service ID. Data may come from `DiscoveryClient`, static configuration, or a custom source.
2. **Filtering or ordering candidates:** suppliers or additional policies may apply health checks, zone preference, hints, metadata, or caching.
3. **Choosing one instance:** the selector may use round-robin or another strategy suited to the application.

Example list provided by a supplier:

~~~text
catalog-service
  ├─ catalog-1  10.0.1.21:8081
  └─ catalog-2  10.0.1.22:8082

Selection result: catalog-2
~~~

This result tells you **which target to call**, not that a connection has been established or that the HTTP request has reached the server.

### API Expressing the Selection Boundary

In the reactive model, LoadBalancer performs selection via `ReactorServiceInstanceLoadBalancer`, returning a `Mono<Response<ServiceInstance>>`:

~~~java
// API shape illustration, not a complete application.
Mono<Response<ServiceInstance>> result = loadBalancer.choose();
~~~

`Response<ServiceInstance>` here is **LoadBalancer's instance-selection result**, not a `ClientResponse`, `ResponseEntity`, or HTTP code returned by the server. Receiving a valid `Response<ServiceInstance>` does not mean the backend successfully processed the request.

On the blocking integration side, APIs like `LoadBalancerClient.choose(serviceId)` also perform target selection. Some integration APIs provide methods that orchestrate request execution as well, yet the responsibility of choosing an instance and the responsibility of sending HTTP still need to be separated during design, testing, and troubleshooting.

## 3. HTTP Execution: From Instance to Response

Once a `ServiceInstance` is obtained, the HTTP integration builds the target address and passes the request to the underlying HTTP client. Tasks that typically belong here include:

- Combining the instance's `scheme://host:port` with the request's path, query, and data.
- Building and sending HTTP headers, body, cookies, and appropriate credentials.
- Establishing the TCP connection, performing the TLS handshake if using HTTPS, and managing connection pools.
- Reading response headers, response body, status codes, or transport errors.
- Enforcing timeouts, request cancellation, and resource cleanup per the HTTP client's mechanics.

These operations are executed by the active HTTP client and transport, such as the HTTP infrastructure beneath `RestClient`, Reactor Netty, or an OpenFeign `Client`. Spring Cloud LoadBalancer does not turn itself into an HTTP server or a network transport for every client type.

Note: a supplier may itself execute **HTTP health checks** to probe instance status. Those are dedicated health-probing requests belonging to the supplier, not an indication that LoadBalancer transports business requests after selecting a target.

## 4. Responsibility Separation Table

| Concern | Primary Responsible Component | Practical Implication |
|---|---|---|
| Which replicas map to a service ID | Discovery and `ServiceInstanceListSupplier` | Inspect registry data and candidate lists |
| Which instance gets selected | LoadBalancer algorithm/policy | Configure round-robin, zone preference, or another algorithm |
| Translating logical URL to target URL | LoadBalancer-integrated adapter/interceptor/filter | Preserves request details and substitutes service ID with instance URI |
| Opening connections, TCP, and TLS | HTTP client/transport | Check network, SSL, and connection pool settings |
| Connect timeout, response/read timeout | HTTP client/transport and its configuration | Tune timeouts to match service-call behavior |
| 4xx/5xx codes from backend | HTTP server and client response handling layer | Distinguish application errors from connection failures |
| Retrying a call | Configured retry mechanism | May need to re-run HTTP execution and pick a different instance |
| Filtering out unhealthy instances | Registry/supplier/health checks per config | Registered instances are not guaranteed ready by default |
| Metrics, logs, tracing | LoadBalancer layer and HTTP client/observability | Record both the selected target and the request outcome |

An application typically needs to configure **both sides**: sensible instance selection and an HTTP client with proper timeouts, pooling, and error monitoring.

## 5. Why Adapters Are Needed for RestClient, WebClient, and OpenFeign

All three HTTP clients can call services by service ID, yet they use different integration mechanisms. What they share is an adapter sitting between the HTTP client API and the instance selector.

### RestClient: Selecting a Target Before the HTTP Client Sends the Request

With Spring Framework's `RestClient`, a `RestClient.Builder` annotated with `@LoadBalanced` can be wired by Spring Cloud with load balancing for requests carrying logical hostnames.

Configuration example:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CatalogHttpConfiguration {

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Using this builder to call by service ID:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient restClient;

    CatalogGateway(
            @Qualifier("catalogRestClientBuilder") RestClient.Builder builder
    ) {
        this.restClient = builder.baseUrl("http://catalog-service").build();
    }

    ProductDto getProduct(long id) {
        return restClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);
    }
}

record ProductDto(long id, String name) {}
~~~

This example assumes the project uses Spring Boot/Spring Cloud versions supporting `RestClient`, along with the `spring-cloud-starter-loadbalancer` dependency and an appropriate instance source. `@LoadBalanced` attaches instance selection to the request flow; business code only uses logical URLs.

After selection, the HTTP request is still sent through the request factory and HTTP transport used by `RestClient`. Changing the LoadBalancer algorithm does not change connect timeouts or connection pool management.

### WebClient: Selecting a Target Inside a Reactive Filter Chain

With `WebClient`, integration usually relies on a `@LoadBalanced WebClient.Builder` or equivalent filter components. The filter intercepts requests with logical URLs, coordinates with LoadBalancer to pick an instance, builds the target URI, and passes the request onward through the `ExchangeFunction` chain and HTTP connector.

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveClientConfiguration {

    @Bean("catalogWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`WebClient` manages asynchronicity and backpressure at the HTTP client/connector layer; LoadBalancer feeds the instance-selection result into that flow. If a request times out waiting for a backend response, that is not inherently a bug in the instance-selection algorithm.

### OpenFeign: LoadBalancer Coordinating with the Feign Client

With Spring Cloud OpenFeign, a Feign interface describes the API via annotations. When configured with a service name alongside Spring Cloud LoadBalancer, the integration can use `FeignBlockingLoadBalancerClient` to choose an instance and delegate HTTP execution to the Feign `Client`.

Example:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/products/{id}")
    ProductDto getProduct(@PathVariable("id") long id);
}
~~~

Feign builds the request from the interface and delegates HTTP transmission to the configured `Client`. LoadBalancer decides the target instance for that request. When adjusting Feign's `connectTimeout` and `readTimeout`, developers are configuring HTTP call behavior, not altering the instance-selection algorithm.

## 6. Simple Experiment to Observe the Boundary

To visualize the two phases clearly, run two replicas of the service on localhost and configure `SimpleDiscoveryClient` for the calling application:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
~~~

Suppose both replicas serve `GET /products/42`, with each replica logging a distinct instance ID.

When `CatalogGateway` uses a LoadBalancer-integrated `RestClient`, a request passes through events such as:

~~~text
1. Application calls      http://catalog-service/products/42
2. Supplier provides      [127.0.0.1:8081, 127.0.0.1:8082]
3. LoadBalancer picks     127.0.0.1:8082
4. HTTP client sends      http://127.0.0.1:8082/products/42
5. Server processes       GET /products/42
6. HTTP client receives   HTTP/1.1 200 OK + response body
~~~

Step 3 reveals the **selected instance**. Step 6 reveals the **HTTP execution outcome**. The two outcomes can succeed or fail independently in different ways.

In the localhost example, the replicas and client must run on the same host or network namespace able to reach `127.0.0.1`. In Docker/Kubernetes, replace URIs with hosts and ports reachable from the client's environment.

## 7. Classifying Errors by Phase

A "failed to call service" error can happen either before or after an instance is selected.

| Symptom | Likely Phase | Investigation Focus |
|---|---|---|
| No instances for service ID | Discovery, supplier, or selection | Check service ID, registry, health filtering, cache |
| List still contains a stopped instance | Discovery/cache/health filtering | Check expiration intervals, sync, and instance health |
| Invalid target URI | Adapter or `ServiceInstance` data | Check host, port, scheme, and path |
| `Connection refused` | HTTP transport | Check whether the server is listening on that port |
| DNS/TLS handshake failure | HTTP transport | Check DNS, TLS configuration, and certificates for the target |
| Connect timeout | HTTP transport | Check network path, connect timeout, connection latency |
| Read/response timeout | HTTP transport or slow backend processing | Check request, backend load, and wait timeouts |
| HTTP 404 from server | HTTP execution / backend application | Check path and actual API; do not blame LoadBalancer immediately |
| HTTP 500 from server | Backend business processing | Inspect server-side logs/traces |
| HTTP 503 due to no server | May be returned by LoadBalancer adapter | Verify whether the request reached the backend or was blocked due to an empty list |

Depending on the client type and configuration, a missing-instance failure may surface as HTTP 503, 404 (when configured to use 404), or a client-side exception. Rely on the HTTP client type, exception details, and integration logs to determine the cause rather than inferring the failure phase from status codes alone.

### Case 1: Instance Selected, Backend Returns HTTP 500

If LoadBalancer selected `catalog-2` and the HTTP client received `500 Internal Server Error`, target selection already happened. The 500 error came from HTTP execution or from an intermediary/backend system along the path. Investigate the response, application logs, and retry policy if configured.

### Case 2: Empty Instance List

If the supplier returns an empty list, LoadBalancer has no target to pick. The adapter can fail immediately before opening an HTTP connection to `catalog-service`. Increasing the HTTP client's read timeout will not conjure new instances; inspect discovery, the supplier, and registration status.

### Case 3: Right Instance Selected, Connection Fails

If a stopped instance remains listed, LoadBalancer can pick an unreachable endpoint. A connection error occurs at the transport layer. Fix discovery/cache staleness or strengthen failing-endpoint filtering, while using reasonable timeouts and retries to limit blast radius.

## 8. Where Do Retries and Timeouts Sit Relative to the Boundary?

**Timeouts** typically bound HTTP operations such as opening a connection or awaiting a response. Exact property names and semantics depend on the HTTP client (`RestClient` request factory, `WebClient` connector, or Feign client). A shorter connect timeout does not make round-robin switch instances faster; those are two separate mechanisms.

**Retries** are conditional re-executions of a request after failure. Depending on the configured retry layer, a retry attempt may:

- Call the same instance again.
- Ask LoadBalancer to pick a different instance.
- Be skipped because the error is not in the retryable category.

An HTTP call is **not automatically** retried simply because the application includes Spring Cloud LoadBalancer. Check the retry configuration of your integration, retry policy, and active HTTP client.

For instance, if a request to `catalog-2` times out, a retry strategy can pick `catalog-1` on the next attempt **when retries are enabled and configured properly**. For operations with side effects such as creating orders or processing payments, retries can cause duplicate execution if the server already accepted the first request; evaluate idempotency, idempotency keys, and retry conditions carefully.

### Health Checks Differ from Retries

Health checks evaluate or filter candidates **before target selection**. Retries react to errors **during a call**. Health checks do not replace retries, and retries cannot fix a discovery list that persistently contains wrong instance addresses.

## 9. Observing Both Routing Decisions and HTTP Outcomes

A system may record a successful LoadBalancer instance selection while the HTTP request still fails. To diagnose accurately, separate telemetry by phase:

| At Selection Time | At HTTP Execution Time |
|---|---|
| Service ID called | Actual target URI |
| Candidate count | Connection duration and response duration |
| Selected instance ID/host/port | HTTP status or exception type |
| Applied selection policy or filters | Retry count, timeouts, and total call duration |
| Whether a suitable instance existed | Which endpoint actually received the request |

Illustrative target log format:

~~~text
requestId=abc123 serviceId=catalog-service candidates=2 selected=catalog-2
requestId=abc123 target=http://10.0.1.22:8082/products/42 status=200 durationMs=45
~~~

When a call fails, logs structured like this distinguish "no instance available" from "instance selected but connection refused." Trace IDs/correlation IDs tie together events across client, proxy, and backend when observability is fully wired.

Do not log sensitive values such as access tokens, cookies, or full payloads containing personal data just to diagnose LoadBalancer.

## 10. How This Boundary Helps Design and Testing

When writing tests, you can test each part fairly independently:

1. **Selection tests:** feed a mock instance list to the supplier and verify the selector follows the intended policy. No real HTTP calls are required.
2. **Adapter tests:** verify URLs containing a service ID translate to the right physical endpoints in the integration pipeline.
3. **HTTP client tests:** use a mock server returning 200, 404, 500, or artificial delays to test parsing, timeouts, and error handling.
4. **Integration tests:** run multiple instances, stop one instance, and observe discovery lists, instance-selection decisions, and request outcomes.

Do not use "request succeeded" alone to conclude LoadBalancer followed the intended selection policy. A request can succeed even if routing logic is skewed, or fail in the backend even when the instance-selection decision was completely valid.

When errors occur, a helpful chain of questions is: **Did the service ID resolve to a candidate list? Which instance did LoadBalancer pick? Which URL did the adapter build? How did the HTTP transport connect and receive the response?** Each question isolates a specific boundary of responsibility, helping tune the right component for more reliable service-to-service communication.

Spring Cloud LoadBalancer provides the flexibility to swap selection algorithms and `ServiceInstance` sources while keeping business code calling by service ID. The HTTP client retains responsibility for connections, timeouts, and request/response transport. Keeping these two halves cleanly separated is the foundation for configuring discovery, health checks, retries, and error observability accurately in microservices systems.
