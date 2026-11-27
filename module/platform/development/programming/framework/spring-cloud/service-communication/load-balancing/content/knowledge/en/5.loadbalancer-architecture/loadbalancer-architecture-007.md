# Response and Cases When No Replica Can Be Selected

Spring Cloud LoadBalancer selects a suitable **ServiceInstance** for each service call made by service ID. The selection result either contains the chosen instance or indicates that no instance is currently available. Applications must handle both outcomes explicitly to avoid obscure errors, pointless retries, or returning incorrect responses to callers.

In this lesson, "replica" refers to an instance serving the same service, not a database data replica.

Within the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module, this lesson connects the instance-selection architecture to the runtime behavior of **RestClient**, **WebClient**, and **OpenFeign**. The focus is on distinguishing LoadBalancer's response from an HTTP response returned by the target service, understanding why instance selection can fail, and designing observable, safely recoverable responses.

## 1. Two Types of Responses in a Service Call

When an application calls a URL using a service ID, such as `http://catalog-service/api/items/42`, two separate phases occur:

1. **Selecting a ServiceInstance**: Spring Cloud LoadBalancer looks up the instance list for `catalog-service` and applies its selection policy.
2. **Sending the HTTP request**: The HTTP client sends the request to the host and port of the selected instance, then receives an HTTP response or a communication error.

Thus, the word "response" in this context can refer to two different objects:

- **LoadBalancer response** is the internal result of the instance-selection step. It may contain a `ServiceInstance`, or indicate that no server was chosen.
- **HTTP response** is the protocol response from the target service, such as status `200`, `404`, or `503`, along with headers and body.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant LB as Spring Cloud LoadBalancer
    participant SD as Instance supplier / Discovery
    participant HTTP as HTTP client
    participant S as Service instance

    App->>LB: Select instance for catalog-service
    LB->>SD: Fetch instance list
    SD-->>LB: ServiceInstance list
    alt Matching instance exists
        LB-->>App: Response containing ServiceInstance
        App->>HTTP: Send request to selected host:port
        HTTP->>S: HTTP request
        S-->>HTTP: HTTP response (2xx/4xx/5xx)
        HTTP-->>App: HTTP result or error
    else No matching instance
        LB-->>App: EmptyResponse / no server
        Note over App,HTTP: HTTP request was not sent to the target service
    end
~~~

If no instance can be selected, the application does not have a target address to send the request to. Consequently, no HTTP status returned by the target service exists for that call. This is a failure during instance resolution or selection, distinct from a scenario where an instance received the request and returned `503 Service Unavailable`.

## 2. Spring Cloud LoadBalancer's Response

Spring Cloud LoadBalancer's instance-selection API represents the outcome with `Response<ServiceInstance>`. Two common results are:

| Result Type | Meaning |
|---|---|
| `DefaultResponse<ServiceInstance>` | An instance was selected; it can be retrieved via `getServer()` |
| `EmptyResponse` | No instance was selected; `hasServer()` returns `false` |

With `RoundRobinLoadBalancer`, when the instance list is empty, LoadBalancer returns an empty result instead of picking a nonexistent address. When instances are present, it picks one element from the list according to the round-robin position and returns a response containing that instance.

A snippet illustrating how to inspect the result:

~~~java
Mono<Response<ServiceInstance>> selection =
    loadBalancer.choose(new DefaultRequest<>());

return selection.flatMap(response -> {
    if (!response.hasServer()) {
        return Mono.error(new IllegalStateException(
            "No instances available for catalog-service"
        ));
    }

    ServiceInstance instance = response.getServer();
    return Mono.just(instance);
});
~~~

This is an API-level example to clarify result checking; in typical applications, `@LoadBalanced` HTTP client integrations invoke LoadBalancer on behalf of business code. If you write a custom selector or adapter, always check `hasServer()` before calling `getServer()`.

Do not assume `getServer()` is always non-null. A custom selector must honor the response contract and represent the no-instance outcome in a way the calling layer can detect.

## 3. When Does LoadBalancer Fail to Select an Instance?

An empty result typically occurs when the input instance list is empty or filters leave no surviving instances. There are several distinct causes.

### Service Not Registered or Not Yet Discovered

Service discovery may not have received the target service's registration yet. This commonly happens when:

- The target service has not started or registered with the registry.
- An instance just started and has not appeared in the next discovery poll yet.
- An instance stopped, or the registry already removed stale registrations leaving none active.
- The calling application uses the wrong service ID, differing from the registered name or the registry's case conventions.
- Applications are using different namespaces, partitions, or discovery environments.

Verify that the service ID in the URL or client annotation matches the registered service name, then inspect the instance list returned by the discovery client.

### List Has Instances, but Filters Eliminate All of Them

The discovery source may return multiple instances, yet the `ServiceInstanceListSupplier` chain may filter them out before the selector sees the list.

For example:

- A zone filter keeps only instances in a specific zone.
- A hint or metadata filter finds no instance with matching attributes.
- A request-based filter keeps only instances satisfying routing rules.
- Health checks mark all instances unhealthy.
- An instance-preference or same-instance policy finds no valid candidate in the current context.

Observe the list before and after each filtering step to identify where the instance count drops to zero. Never look only at the registry and conclude LoadBalancer definitely has candidates, because the final list reaching the selector may be different.

### Health Checks Have Not Succeeded

When `HealthCheckServiceInstanceListSupplier` is configured, LoadBalancer can rely on health check results to supply only healthy instances. If all health check endpoints fail, time out, or return an unacceptable status, the post-filter list can be empty.

Check:

- Whether the health endpoint path matches the target application.
- Whether the endpoint is reachable over the network from the probing caller.
- Whether the health check timeout is too short or the polling interval has not updated status yet.
- Whether the target application is genuinely ready to accept traffic when its health endpoint reports healthy.

A health check is an operational signal, not an absolute guarantee that the next business request will succeed. An instance's state can change after the latest check.

### Cache or Discovery State Is Not Updated Yet

If the instance list is cached, registration changes may not show up immediately on the very next selection. Caching reduces discovery queries but introduces update lag.

Evaluate refresh intervals, cache TTL, registry update mechanisms, and timing when new instances register or old ones are removed. Avoid lowering cache durations arbitrarily, as doing so can increase load on the discovery server.

## 4. Distinguishing Missing Instances from HTTP Errors

The following situations occur at different stages and require different handling:

| Situation | Stage | HTTP Response from Target Service? | Investigation Focus |
|---|---|---|---|
| No `ServiceInstance` | Instance selection | No | Discovery, service ID, supplier, and filters |
| Cannot connect to host/port | Connection setup | No | Network, DNS, port, stopped instance |
| Connect/response timeout | HTTP communication | May lack a complete response | Timeouts, server load, network, and connection pool |
| HTTP `404` | Service received the request | Yes | Path, resource, and API contract |
| HTTP `503` | Service received the request or gateway returned error | Yes | Service health, overload, dependencies |
| HTTP `500` | Server-side processing | Yes | Target service exceptions and logs |

An HTTP `503` may be returned by a gateway or by the target service itself. It can also be synthesized by the calling application when translating a "no instance" error into an HTTP response for an upstream caller. When investigating, determine which component actually generated that status.

Key takeaway: `EmptyResponse` is an outcome of the instance-selection step, whereas `503` is an HTTP status. Do not log both cases with the same message such as "service returned 503" if the request never actually reached the service.

## 5. HTTP Client Behavior When No Instance Exists

Clients annotated with `@LoadBalanced` use Spring Cloud's integration to resolve service IDs. When no instance exists, failure usually occurs before any HTTP request reaches the target service. Exact exception types can vary by client, filter, retry configuration, and Spring Cloud version.

### RestClient

Example builder configuration:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Call using a service ID:

~~~java
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

When an instance exists, the request goes to the selected instance. When none exists, the load balancing step may throw an error before any HTTP response is received. Therefore, `retrieve().onStatus(...)` only handles status codes from an HTTP response; it does not replace handling instance-selection or connection errors.

You can catch errors at the service-call boundary and translate them into a meaningful business exception:

~~~java
public ItemDto getItem(String itemId) {
    try {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
    catch (RestClientException | IllegalStateException ex) {
        throw new CatalogUnavailableException(
            "Cannot retrieve item from catalog-service", ex
        );
    }
}
~~~

This example illustrates handling common client errors alongside the no-instance error often reported as `IllegalStateException` in blocking flows. Exact exception types also depend on version and retry configuration; in real systems, classify more granularly if callers must distinguish HTTP 4xx, 5xx, timeouts, and missing instances.

### WebClient

WebClient represents the call via a publisher:

~~~java
Mono<ItemDto> item = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

If LoadBalancer finds no instance, the pipeline terminates with an error signal. That error can be handled using Reactor operators:

~~~java
public Mono<ItemDto> getItem(String itemId) {
    return webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .bodyToMono(ItemDto.class)
        .onErrorMap(
            ex -> isCatalogUnavailable(ex),
            ex -> new CatalogUnavailableException(
                "catalog-service has no available instance", ex
            )
        );
}
~~~

`isCatalogUnavailable` is an application-defined classifier; inspect the cause chain and actual exception types produced by your active version. Do not turn every error into "no instance," because decoding errors, HTTP errors, and programming bugs should retain their true nature.

If using `retrieve().onStatus(...)`, `onStatus` handles HTTP statuses like `404` or `503`. Errors occurring before an HTTP response still flow down the publisher's error channel.

### OpenFeign

OpenFeign declares clients via interfaces:

~~~java
@FeignClient(name = "catalog-service")
public interface CatalogClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String itemId);
}
~~~

When instances exist, Spring Cloud LoadBalancer selects a target for the Feign call. When none exist, the call can fail inside the LoadBalancer integration layer before Feign receives an HTTP response. If the target service returned an HTTP error, Feign typically represents error statuses with Feign ecosystem exceptions, such as `FeignException`.

You can use a service layer to convert technical exceptions into business exceptions understood by controllers:

~~~java
@Service
class CatalogService {

    private final CatalogClient client;

    CatalogService(CatalogClient client) {
        this.client = client;
    }

    ItemDto getItem(String itemId) {
        try {
            return client.getItem(itemId);
        }
        catch (RuntimeException ex) {
            throw new CatalogUnavailableException(
                "Catalog service call failed", ex
            );
        }
    }
}
~~~

This snippet only illustrates the error-translation boundary. In real applications, catch specific exception types and preserve business errors such as `404` if the caller needs to know an item does not exist.

## 6. Designing Responses When No Instance Can Be Selected

How to respond depends on the service's role in the business workflow.

### Dependency Required to Complete the Business Operation

If an order cannot be confirmed without the catalog service, the application should stop the business flow and return an appropriate error. You can map the internal failure to `503 Service Unavailable` at the API gateway or controller because the system temporarily cannot fulfill the request.

The response should follow a consistent structure, for example:

~~~json
{
  "type": "https://api.example.com/problems/dependency-unavailable",
  "title": "Dependent service temporarily unavailable",
  "status": 503,
  "detail": "Unable to process request because catalog-service currently has no available instances.",
  "service": "catalog-service"
}
~~~

Do not expose internal hostnames, stack traces, registry details, or sensitive infrastructure information in public responses. Include a stable error code so callers and monitoring systems can categorize failures.

### Optional Service or Service with Fallback Data

If a dependency only supplies supplementary data, the application can choose graceful degradation:

- Return cached data with a freshness timestamp if the business permits stale reads.
- Omit the optional section and return the core result.
- Return a "pending update" status if the workflow can complete asynchronously.
- Use a pre-designed, controlled fallback source.

Fallbacks must clearly communicate data limitations. For example, stale product pricing may be unsafe for checkout, whereas a cached profile avatar may be acceptable. Do not apply the same fallback policy to every dependency.

### Never Return Fake Data to Hide Errors

Do not return an empty DTO or default values disguised as success when the business requires real data. Callers may continue processing based on false assumptions, leading to bugs much harder to trace than the original failure.

Fallbacks need an explicit contract, such as a degraded flag, data source, and last-updated timestamp. If result correctness cannot be guaranteed, return an explicit, recognizable error.

## 7. Retrying When No Instance Is Available

Retries can help when an instance just registered, discovery just updated, or one instance momentarily dropped a connection. However, retries are not a cure-all for missing instances.

Distinguish these cases:

- **Empty list**: immediate retries usually still see an empty list if neither the registry nor the supplier has changed.
- **One instance just failed**: a subsequent attempt can choose a different instance if candidates remain and the retry strategy is configured appropriately.
- **Recoverable HTTP error**: retry only when the status code and business operation permit it.
- **Non-idempotent request error**: retrying can trigger duplicate side effects if the server already processed the request and only the response was lost.

Spring Cloud LoadBalancer includes retry support for client integrations. Exact configuration and behavior depend on the version, client type, and active retry policy. Some configurations can use a supplier aware of previously attempted instances to avoid picking the same instance again on the next retry. Verify this policy in your application rather than assuming every retry automatically switches to a different instance.

A retry policy should include:

1. A small, bounded maximum number of attempts.
2. An overall deadline that does not exceed the caller's time budget.
3. Backoff and jitter to prevent many clients from retrying simultaneously.
4. Clear classification of retryable errors; never blindly retry 4xx or business errors.
5. Idempotency guarantees or idempotency keys for write operations.
6. Retry coordination across layers to avoid nested retries between the HTTP client, LoadBalancer, and gateway.

If all instances are absent or unhealthy, retrying only prolongs failure time and amplifies load. In that case, controlled fail-fast behavior protects caller threads, connections, and resources far better.

## 8. Observing and Diagnosing Instance Selection Failures

When a call fails, logs and metrics should help answer four questions: which service ID the application tried to call, how many instances the supplier provided, whether LoadBalancer selected an instance, and whether the error happened before or after sending the HTTP request.

Consider recording the following fields:

| Field | Purpose |
|---|---|
| `serviceId` | Identifies the logical service called |
| `traceId` / `correlationId` | Links logs across services |
| Instance count before/after filtering | Pinpoints the step where the list became empty |
| Selected instance | Identifies the chosen host/port or metadata |
| LoadBalancer result type | Whether an instance was found or `EmptyResponse` |
| Instance selection duration | Detects slow discovery or suppliers |
| HTTP status | Distinguishes server responses from pre-HTTP failures |
| Exception class and cause | Classifies the failure accurately |
| Retry attempt | Shows attempt count and instances tried |

Do not log sensitive bodies, tokens, credentials, or personal data. When logging instance addresses, comply with your system's security policies and log access controls.

You can structure an investigation workflow like this:

~~~mermaid
flowchart TD
    A["HTTP client call failed"] --> B{"Was an instance selected?"}
    B -->|No| C["Check service ID and discovery"]
    C --> D["Check supplier, cache, and filters"]
    D --> E["Check health checks / metadata / zone"]
    E --> F["Identify why the list is empty"]
    B -->|Yes| G{"Was an HTTP response received?"}
    G -->|No| H["Check DNS, connection, timeouts, and pool"]
    G -->|Yes| I["Check status, body, and server logs"]
    F --> J["Restore registration or adjust configuration"]
    H --> K["Fix network or resource issues"]
    I --> L["Fix endpoint or business logic error"]
~~~

When deeper visibility is required, you can use LoadBalancer lifecycle hooks such as `LoadBalancerLifecycle` to observe selection start, request start, and completion. Combining correlated logs with metrics on successful selections, missing-instance occurrences, retries, timeouts, and request distribution helps detect early when a service loses capacity.

## 9. Configuration and Testing Checklist

Before deploying an integration to production, verify:

- The service ID in the URL or `@FeignClient(name = ...)` matches the registered name in discovery.
- Discovery returns the expected instance list to the calling application.
- The supplier and filters do not unintentionally eliminate all candidates.
- Health endpoints are reachable and reflect true readiness.
- Caching and refresh intervals match the rate of instance churn.
- The client handles missing-instance scenarios and distinguishes them from HTTP errors.
- Timeouts, retries, backoff, and deadlines are bounded.
- Fallbacks align with business data correctness requirements.
- Logs and metrics separate instance-selection errors, connection errors, and HTTP errors.

Test at least the following scenarios:

| Scenario | Outcome to Observe |
|---|---|
| Discovery returns an empty list | LoadBalancer selects no instance; application returns a controlled dependency error |
| One instance is running | Requests are routed to that instance |
| Multiple instances are running | Requests are distributed per the configured selection policy |
| All health checks fail | Post-health-filter list is empty and the error is classified properly |
| Instance stops right after selection | Connection error is recorded; retries follow policy only |
| Server returns `404` | Application preserves resource-not-found semantics |
| Server returns `503` | Status from server/gateway is distinguished from no-instance error |
| Discovery updates after an instance starts | Subsequent calls can pick the new instance once the supplier refreshes |

Do not test only the happy path. An empty list is a normal part of a distributed system's lifecycle: services can start slowly, be deregistered, fail health checks, or briefly lose connectivity. When those states are represented and handled explicitly, applications can return clear errors, retry within bounds, and recover smoothly once instances become available again.
