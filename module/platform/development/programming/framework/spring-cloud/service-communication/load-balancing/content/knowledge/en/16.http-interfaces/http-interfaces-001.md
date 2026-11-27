# HTTP Service Interface and Call-Describing Annotations

When communicating between microservices over HTTP, the familiar approach is calling `RestClient.get().uri(...).retrieve()` or `WebClient.get().uri(...).retrieve()` directly in each service. If an application has many endpoints such as fetching products, searching, creating, and updating data, HTTP request construction code can end up repeated in many places.

**HTTP Service Interface** in Spring Framework allows declaring an **HTTP invocation contract as a Java interface**. You describe the HTTP method, URL, and parameters using annotations such as `@HttpExchange`, `@GetExchange`, `@PostExchange`, and `@PathVariable`. Then, `HttpServiceProxyFactory` creates a proxy that executes HTTP requests through a `RestClient` or `WebClient` adapter.

This lesson belongs to the **HTTP Interface** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The goal is not only to know the annotation syntax, but also to understand **how the interface is wired to Spring Cloud LoadBalancer** to call by service ID, leverage discovery and health checks, and handle timeouts, retries, and errors in inter-service communication.

> Keep the distinction clear: **HTTP Service Interface** is a mechanism for declaring an **HTTP client**, not a controller that automatically exposes a server-side API. Nor does it enable load balancing by default; the proxy must be created from an HTTP client integrated with Spring Cloud LoadBalancer.

## 1. From Hand-Written HTTP Clients to Declarative Contracts

A snippet using `RestClient` directly:

~~~java
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

This approach works well for a few calls. However, when there are many operations, the application can duplicate URLs, headers, body conversion, and request construction logic.

HTTP Service Interface moves the call description into an interface:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/api/items")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

In the consuming service, business code becomes concise:

~~~java
ItemDto item = catalogHttpApi.findById(itemId);
~~~

The proxy generated from the interface translates the method call into an HTTP request. Calling code still encounters HTTP/network errors just as before: declaring an interface **does not turn a request into a local call**, does not automatically add distributed transactions, and does not replace timeout or retry policies.

~~~mermaid
flowchart LR
    A["order-service: catalogHttpApi.findById(id)"] --> I["HTTP Service Interface proxy"]
    I --> H["RestClient / WebClient adapter"]
    H --> LB["Spring Cloud LoadBalancer"]
    DISC["ServiceInstanceListSupplier / discovery"] --> LB
    LB --> X["catalog-a"]
    LB --> Y["catalog-b"]
~~~

## 2. Role of Each Component

| Component | Responsibility | What It Does Not Do Automatically |
|---|---|---|
| `@HttpExchange` | Declares shared HTTP metadata at the interface or method level | Does not create a bean or send requests |
| `@GetExchange`, `@PostExchange`, ... | Declares HTTP method, URL, and request metadata | Does not choose an instance itself |
| `@PathVariable`, `@RequestParam`, ... | Maps Java arguments to URL/headers/body | Does not validate server-side business rules |
| `HttpServiceProxyFactory` | Creates a proxy from an interface | Does not provide discovery if the adapter lacks it |
| `RestClientAdapter` | Executes calls via synchronous `RestClient` | Does not make the caller non-blocking |
| `WebClientAdapter` | Executes calls via reactive `WebClient` | Does not guarantee the server returns valid data |
| `@LoadBalanced RestClient.Builder` or `WebClient.Builder` | Attaches LoadBalancer integration to the created HTTP client | Does not synthesize instances when the registry is empty |
| `ServiceInstanceListSupplier` | Supplies candidate `ServiceInstance` entries by service ID | Does not guarantee every instance is currently healthy |
| `RoundRobinLoadBalancer` or another selector | Selects an instance from the candidate set | Does not measure actual load without additional data |

Three independent yet coordinated steps:

1. **Declare the contract**: the interface defines which Java method corresponds to which HTTP request.
2. **Choose the execution engine**: the proxy is connected to `RestClient` or `WebClient`.
3. **Select the target**: if the client is load-balanced, the logical hostname is resolved to a concrete instance.

## 3. @HttpExchange: The Root Annotation

`@HttpExchange` belongs to the `org.springframework.web.service.annotation` package. It can be used at the **interface level** to declare shared attributes, or directly on a method.

Example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {
    // HTTP methods are declared inside
}
~~~

Important attributes:

| Attribute | Meaning | Example |
|---|---|---|
| `url` / shorthand value | Shared path prefix or method path | `"/api/items"` |
| `method` | HTTP method when using `@HttpExchange` directly on a method | `"GET"`, `"POST"` |
| `contentType` | Expected `Content-Type` value of the request | `"application/json"` |
| `accept` | `Accept` value the client expects to receive | `"application/json"` |
| `headers` | Static request headers declared on the exchange | `"X-Caller=order-service"` |

`Content-Type` describes the **format of data being sent**, whereas `Accept` describes the **desired response format**. For a `GET` request without a body, setting `Content-Type` is usually unnecessary. Do not treat these two headers as equivalent.

### Combining Interface-Level and Method-Level Annotations

~~~java
@HttpExchange(url = "/api/items", accept = "application/json")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

When calling `findById("42")` and the client has a base URL of `http://catalog-service`, the logical request is:

~~~http
GET /api/items/42 HTTP/1.1
Host: catalog-service
Accept: application/json
~~~

The base URL identifies the logical service or host. The interface `url` forms the prefix, and the method path adds the specific segment. Attributes declared on a method can override the corresponding interface-level values according to Spring Framework's rules.

Do not declare multiple conflicting HTTP method annotations on the same method, such as both `@GetExchange` and `@PostExchange`. Choose a single clear HTTP contract.

## 4. Annotations by HTTP Method

Spring Framework provides specialized annotations built on top of `@HttpExchange`:

| Annotation | HTTP method | When to Use |
|---|---|---|
| `@GetExchange` | GET | Reading a resource or list |
| `@PostExchange` | POST | Creating a resource or submitting an action |
| `@PutExchange` | PUT | Replacing/updating a resource per contract |
| `@PatchExchange` | PATCH | Partial update |
| `@DeleteExchange` | DELETE | Deleting a resource or sending a deletion request |

Complete declaration example:

~~~java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PatchExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.annotation.PutExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetExchange
    List<ItemDto> search(
        @RequestParam("category") String category,
        @RequestParam("limit") int limit
    );

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ItemDto> create(@RequestBody CreateItemRequest request);

    @PutExchange(
        url = "/{id}",
        contentType = MediaType.APPLICATION_JSON_VALUE
    )
    ItemDto replace(
        @PathVariable("id") String id,
        @RequestBody UpdateItemRequest request
    );

    @PatchExchange(
        url = "/{id}",
        contentType = MediaType.APPLICATION_JSON_VALUE
    )
    ItemDto updatePartially(
        @PathVariable("id") String id,
        @RequestBody PatchItemRequest request
    );

    @DeleteExchange("/{id}")
    ResponseEntity<Void> delete(@PathVariable("id") String id);
}
~~~

Illustrative DTO types:

~~~java
record ItemDto(String id, String name, int stock) {}

record CreateItemRequest(String name, int stock) {}

record UpdateItemRequest(String name, int stock) {}

record PatchItemRequest(Integer stock) {}
~~~

The snippets above can be placed into corresponding Java files in a sample project. To execute successfully, the server must expose matching endpoints and the corresponding JSON schema. Client declarations **do not auto-generate server APIs** for POST/PUT/PATCH/DELETE.

### When to Use `@HttpExchange(method = "...")` Directly?

You can write:

~~~java
@HttpExchange(method = "GET", url = "/{id}")
ItemDto findById(@PathVariable("id") String id);
~~~

This expresses the same thing as `@GetExchange("/{id}")` when no custom configuration is needed. In typical cases, the specialized annotation is easier to read and reduces the risk of mistyping the HTTP method.

## 5. Parameter-Describing Annotations: URL, Query, Header, and Body

Information in the Java method signature is mapped to parts of the HTTP request:

~~~mermaid
flowchart TD
    M["A Java method call"] --> P["@PathVariable → URI path"]
    M --> Q["@RequestParam → query or parameter"]
    M --> H["@RequestHeader → request header"]
    M --> C["@CookieValue → Cookie"]
    M --> B["@RequestBody → request body"]
    M --> F["@RequestPart → multipart part"]
~~~

Common parameter annotations belong to `org.springframework.web.bind.annotation`. They also appear in Spring MVC controllers, but here they are used on the **client side** through HTTP Service Interface.

### `@PathVariable`: Dynamic Values in the Path

~~~java
@GetExchange("/{id}")
ItemDto findById(@PathVariable("id") String id);
~~~

Calling `findById("42")` produces a request to path `/api/items/42`. The name `id` in the template and annotation must match. Prefer specifying parameter names explicitly rather than relying on compiler settings to retain parameter names.

Do not construct URIs by concatenating user input strings when a template can be used. URI building mechanisms handle encoding according to client rules; however, the application must still validate ID formats and must not treat URL encoding as an access-control mechanism.

### `@RequestParam`: Query Parameters

~~~java
@GetExchange
List<ItemDto> search(
    @RequestParam("category") String category,
    @RequestParam("limit") int limit
);
~~~

Calling `search("paper", 20)` corresponds to:

~~~http
GET /api/items?category=paper&limit=20 HTTP/1.1
~~~

For complex filters, you can pass multiple parameters or a type holding query parameters depending on the API and adapter support. When values are optional, agree on how an absent parameter is represented, and do not assume every endpoint treats an empty string as equivalent to a missing parameter.

### `@RequestHeader`: Dynamic Headers

~~~java
@GetExchange("/{id}")
ItemDto findWithTrace(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

Headers help propagate correlation IDs, tenant context, or session-control metadata per contract. Never write access tokens, sensitive cookies, or user IDs directly into logs when debugging requests.

### `@RequestBody`: Outbound Payload

~~~java
@PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
ItemDto create(@RequestBody CreateItemRequest request);
~~~

If the request object is `new CreateItemRequest("Notebook", 7)`, the JSON body can be:

~~~json
{
  "name": "Notebook",
  "stock": 7
}
~~~

Actual serialization depends on the HTTP message converter or codec used by the adapter. Client and server DTOs must have compatible schemas; they do not need to share a common Java module.

### `@CookieValue`: Data from Cookies

~~~java
@GetExchange("/session")
String readSession(@CookieValue("session-id") String sessionId);
~~~

Use this when the target API contract authenticates or identifies a session via cookies. In service-to-service communication, tokens or identity context are usually managed centrally; do not forward a user's cookie to another service without a clear security model.

### `@RequestPart`: Multipart Requests

~~~java
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.RequestPart;

@PostExchange(
    url = "/import",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE
)
String importFile(@RequestPart("file") Resource file);
~~~

The goal is to send a part named `file` in a multipart body. How filename, content type, and size are represented depends on the HTTP adapter's resource/codec handling. For large files, consider streaming and memory limits instead of loading the entire file into RAM. This is an illustrative endpoint and is not tied to any specific inventory API.

### `@RequestAttribute` and Advanced Parameters

Spring Framework also supports passing request attributes and several special parameter types depending on the HTTP adapter. Only use them after verifying adapter support; a **request attribute is local data attached to the client request**, unlike an HTTP header transmitted over the network. When you need to send information to the server, use headers, query parameters, or the request body per the API contract.

## 6. HTTP Interface Is a Client, Not a Server Controller

These two roles are often confused because both use `@PathVariable` and `@RequestBody`.

**Client contract:**

~~~java
@HttpExchange("/api/items")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

**Server implementation:**

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
class CatalogController {

    @GetMapping("/{id}")
    ItemDto findById(@PathVariable String id) {
        return new ItemDto(id, "Notebook", 7);
    }
}
~~~

In the server application, Spring MVC/WebFlux registers HTTP handlers based on `@RestController`/mappings. In the caller application, `HttpServiceProxyFactory` creates a client proxy from `@HttpExchange`. Both sides may describe the same HTTP API, but they **do not automatically synchronize versions**, nor do they automatically provide validation, auth, or OpenAPI.

## 7. Creating an HTTP Interface Proxy with RestClientAdapter

Spring Framework 6.1+ supports HTTP Service Interface on top of `RestClient`. This is the right fit when the caller uses a synchronous/blocking model.

### Step 1: Declare Dependencies

In a project using a compatible Spring Boot + Spring Cloud BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

These two dependencies represent the core setup; the project still needs compatible plugins and dependency management. `RestClient` was introduced in Spring Framework 6.1; older projects cannot apply this configuration verbatim without upgrading the framework.

### Step 2: Define the LoadBalanced Builder and Proxy

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class CatalogHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder
    ) {
        RestClient client = builder
            .baseUrl("http://catalog-service")
            .build();

        RestClientAdapter adapter = RestClientAdapter.create(client);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter)
                .build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

When calling `catalogHttpApi.findById("42")`:

1. The proxy reads `@HttpExchange` and `@GetExchange` metadata.
2. The adapter turns the method call into a `RestClient` request.
3. Because the `RestClient` was built from a `@LoadBalanced` builder, host `catalog-service` is treated as a service ID.
4. `ServiceInstanceListSupplier` supplies instances; LoadBalancer chooses one instance.
5. The request is sent to the actual host/port; the response is read and mapped to `ItemDto`.

It is `@LoadBalanced` and Spring Cloud integration that connect HTTP Interface to LoadBalancer. **Simply creating a proxy via `RestClientAdapter` does not enable discovery** if the underlying `RestClient` is created normally.

### Example Usage from a Business Service

~~~java
import org.springframework.stereotype.Service;

@Service
class ItemQueryService {

    private final CatalogHttpApi catalog;

    ItemQueryService(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    ItemDto loadItem(String id) {
        return catalog.findById(id);
    }
}
~~~

`CatalogHttpApi` is the type-safe dependency used by the business service. The proxy still performs synchronous HTTP I/O; do not assume the method completes instantaneously just because the Java signature looks like a local call.

## 8. Configuring Discovery for Service-ID Calls

To run a lab without Eureka or Consul, declare two instances:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Run two `catalog-service` server instances with the same `GET /api/items/{id}` endpoint on two ports:

~~~bash
java -jar catalog-service.jar --server.port=18081
java -jar catalog-service.jar --server.port=18082
~~~

These two commands assume the server application has been built into `catalog-service.jar`. If the server returns an instance identifier in a test header, you can observe which instance received each request. `@HttpExchange` does not generate the service ID; the service ID must match the name used in `baseUrl("http://catalog-service")` and discovery.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as order-service
    participant Proxy as CatalogHttpApi proxy
    participant RC as @LoadBalanced RestClient
    participant LB as LoadBalancer
    participant Disc as Discovery / supplier
    participant B as catalog-b:18082

    App->>Proxy: findById("42")
    Proxy->>RC: GET http://catalog-service/api/items/42
    RC->>LB: catalog-service
    LB->>Disc: Fetch instances
    Disc-->>LB: [A, B]
    LB-->>RC: B
    RC->>B: GET /api/items/42
    B-->>RC: 200 JSON
    RC-->>Proxy: ItemDto
    Proxy-->>App: ItemDto
~~~

If you call a hostname that does not exist in discovery, no instance can be selected; check the service ID, discovery source, cache, health checks, and filters before concluding that the annotation URL is wrong.

## 9. Creating an HTTP Interface Proxy with WebClientAdapter

When reactive or streaming processing is needed, use `WebClientAdapter` instead of forcing every call to return a synchronous DTO.

**Dependencies:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Dedicated reactive interface:**

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record StockEvent(String sku, int quantity) {}

@HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ItemDto> findById(@PathVariable("id") String id);

    @GetExchange(value = "/events", accept = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<StockEvent>> watchEvents();
}
~~~

In this example, `/api/items/events` must actually be an SSE endpoint on the server; the GET-by-ID lab backend above does not provide that endpoint. `Mono<ItemDto>` represents at most one response DTO, while `Flux<ServerSentEvent<StockEvent>>` represents a potentially long-lived event stream.

**Creating the proxy:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class ReactiveCatalogHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    ReactiveCatalogHttpApi reactiveCatalogHttpApi(
        @Qualifier("loadBalancedWebClientBuilder")
        WebClient.Builder builder
    ) {
        WebClient client = builder
            .baseUrl("http://catalog-service")
            .build();

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                WebClientAdapter.create(client))
                .build();

        return factory.createClient(ReactiveCatalogHttpApi.class);
    }
}
~~~

Note that this is **an alternative execution approach** for the same kind of contract; you do not necessarily need to register both `RestClient` and `WebClient` in one application. If you want both, bean naming and injection must be explicit.

### Blocking and Reactive Are Two Different Models

| Aspect | RestClientAdapter | WebClientAdapter |
|---|---|---|
| Underlying client | RestClient | WebClient |
| Typical model | Synchronous, blocking | Reactive, non-blocking |
| Typical return types | DTO, `ResponseEntity<T>`, `void` | `Mono<T>`, `Flux<T>`, and compatible types |
| Error handling | Exceptions on synchronous calls | Publisher error signals |
| Streaming responses | Not a good default for long-lived SSE | Better suited for SSE/streaming |
| LoadBalancer wiring | `@LoadBalanced` RestClient builder | `@LoadBalanced` WebClient builder |

Do not call `block()` on a Reactor event-loop thread to turn a reactive HTTP interface into a synchronous call. When using `WebClient` inside a reactive pipeline, return the `Mono`/`Flux` so the framework manages subscription and cancellation.

## 10. How Do Annotations Describe Return Types?

The interface method return type determines how the adapter converts the response into a Java type:

~~~java
@HttpExchange("/api/items")
interface CatalogResponses {

    @GetExchange("/{id}")
    ItemDto getBody(@PathVariable("id") String id);

    @GetExchange("/{id}")
    ResponseEntity<ItemDto> getEntity(@PathVariable("id") String id);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") String id);
}
~~~

- `ItemDto`: requires a matching response body to deserialize into the DTO.
- `ResponseEntity<ItemDto>`: the application receives status/headers/body when the HTTP response is processed successfully.
- `void`: discards the body when the contract does not require returned data.
- With `WebClientAdapter`, you can use `Mono<ItemDto>`, `Mono<ResponseEntity<ItemDto>>`, and `Flux<T>` according to the response type.

**`ResponseEntity<T>` does not automatically turn every 4xx/5xx into a normal return value.** With default adapter and status-handling policies, HTTP error statuses can be converted into exceptions or error signals before the method can return a successful entity.

If an API returns `204 No Content`, do not require deserializing a mandatory DTO. Design an appropriate return type/contract, such as `void` or a status-only response.

### Generic Types

For lists or generic wrappers:

~~~java
@GetExchange
List<ItemDto> list(@RequestParam("category") String category);
~~~

HTTP Service Proxy can capture the return type from the method signature, unlike calling `RestClient` directly where `ParameterizedTypeReference<List<ItemDto>>` must be supplied in many calls. Actual decoding still depends on the media type and the adapter's converters/codecs.

## 11. Shared Headers, Dynamic Headers, and Security

Static headers can be defined with `@HttpExchange`:

~~~java
@HttpExchange(
    url = "/api/items",
    headers = {"X-Caller=order-service"},
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {
    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Use static headers for non-sensitive, unchanging metadata. For per-request values, use `@RequestHeader`:

~~~java
@GetExchange("/{id}")
ItemDto findById(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

**Do not hardcode Bearer tokens or API keys in annotations** and commit them to source code. Authentication should be managed by appropriate client configuration components (interceptors/filters or credential mechanisms) with an explicit trust boundary.

HTTP Interface simplifies request declaration; it does not automatically govern credential forwarding between services. You must determine whether tokens represent a user or a service account, define access permissions, and enforce log masking rules.

## 12. Distinguishing HTTP Service Interface from OpenFeign

Both HTTP Interface and OpenFeign let you write Java interfaces representing remote HTTP APIs. However, they **differ in execution framework and registration mechanism**:

| Criterion | Spring HTTP Service Interface | Spring Cloud OpenFeign |
|---|---|---|
| Interface declaration | `@HttpExchange`, `@GetExchange`, `@PostExchange`... | `@FeignClient` and corresponding mappings/contracts |
| Client creation | `HttpServiceProxyFactory` + adapter | Feign client factory managed by OpenFeign |
| HTTP stack | RestClient, WebClient, or compatible adapter | Feign client and configured HTTP transport |
| LoadBalancer | Requires underlying HTTP client integrated with `@LoadBalanced` | Integrates with Spring Cloud LoadBalancer via config/dependencies |
| Reactive return | Supports `Mono`/`Flux` with `WebClientAdapter` | Not reactive in the same way as `WebClient` by default |
| Status/exception | Follows adapter and response handling config | Follows Feign error decoder/response handling |

**Do not place `@FeignClient` on an HTTP Service Interface assuming `HttpServiceProxyFactory` will use Feign**, or swap Feign's `@GetMapping` for `@GetExchange` without updating the proxy creation mechanism. These are two distinct mechanisms that must be configured separately.

Choose based on your project architecture: `RestClientAdapter` fits synchronous Spring stacks; `WebClientAdapter` suits reactive/streaming workloads; OpenFeign fits projects already built around Feign and its configuration workflow.

## 13. Handling HTTP Statuses, Missing Instances, and Connection Errors

A Java method signature such as `ItemDto findById(...)` hides the HTTP plumbing, but **does not hide failure modes**:

~~~mermaid
flowchart TD
    A["Call catalog.findById(id)"] --> B["HTTP proxy builds request"]
    B --> C{"LoadBalancer selects an instance?"}
    C -->|No| D["No ServiceInstance available error"]
    C -->|Yes| E{"Send request / receive response?"}
    E -->|I/O error| F["Connect timeout / reset / TLS"]
    E -->|Response received| G{"HTTP status"}
    G -->|2xx| H["Decode body"]
    G -->|4xx| I["Client error per contract"]
    G -->|5xx| J["Server / dependency error"]
~~~

| Scenario | Response from Target Service? | Example Handling |
|---|---|---|
| Service ID does not exist or supplier has no instances | No | Check discovery, service name, filters, and health |
| Connect refused, connect timeout | No | Check network, instance, port, and bounded retries |
| HTTP 404 | Yes | Missing resource or wrong route |
| HTTP 429 | Yes | Throttle/rate limit per contract |
| HTTP 503 | Possibly from backend/gateway when a response is actually received | Investigate overload, health, dependencies |
| Response JSON violates schema | Possibly 2xx received but decoding fails | Cross-check DTO and API version |

With `RestClientAdapter`, HTTP status errors typically go through `RestClient`'s handling and may throw `RestClientResponseException` or a subclass. With `WebClientAdapter`, status errors typically appear in the error signal, such as `WebClientResponseException`. There are also connection errors, codec errors, and cases where no instance can be selected; **do not catch everything with a single HTTP status exception type**.

Even when using `ResponseEntity` as the return type, you must check the underlying client's status policy. HTTP Service Interface does not provide a single universal "error decoder" completely independent of the adapter.

### Example Categorized Catch in a Synchronous Caller

~~~java
try {
    ItemDto item = catalogHttpApi.findById("42");
    // Handle item
} catch (org.springframework.web.client.RestClientResponseException ex) {
    int code = ex.getStatusCode().value();
    // Received error HTTP response; classify 404 / 429 / 5xx.
} catch (org.springframework.web.client.RestClientException ex) {
    // I/O or decode errors may fall into this group;
    // inspect the cause before retrying.
}
~~~

Some instance-selection failures before HTTP execution may surface through different exception types depending on the integration/version. Therefore, this catch example **does not claim to cover every possible error**. Design handling at the service boundary, log the exception class/cause, and separate discovery failures from HTTP server errors.

## 14. Timeouts and Retries Must Be Configured on the Underlying Client

The `@GetExchange` annotation says nothing about connect timeout, read timeout, or retry count. Those belong to the **HTTP client/connector and resilience layers**.

Example for `RestClient` using `SimpleClientHttpRequestFactory`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

    factory.setConnectTimeout(2000);
    factory.setReadTimeout(3000);

    return RestClient.builder().requestFactory(factory);
}
~~~

This is an **alternative** to the builder bean in section 7, not a second bean to register alongside it. The unit for the two integer values in this API example is milliseconds; verify actual timeout behavior against the HTTP request factory and version in use.

When using `WebClient` with Reactor Netty, configure the corresponding connector/response timeouts. For long-lived SSE streams, timeouts cannot be derived from short JSON requests: heartbeats and dedicated idle controls may be needed.

Retries can cause `catalogHttpApi.create(...)` to execute multiple times if the backend processed the request but the response was lost. Therefore:

- Only retry recoverable error classes; bound the attempt count and total deadline.
- For `POST` or operations with side effects, use an **idempotency key** paired with real server-side deduplication if needed.
- Do not assume a retry after failure will pick a different instance; that depends on the retry/LoadBalancer configuration.
- Avoid stacked retries across HTTP client, gateway, and service mesh that amplify traffic.
- Do not treat HTTP 404 as a transient error unless the business contract states otherwise.

An idempotency key can be declared as a dynamic header on the interface:

~~~java
@PostExchange(
    contentType = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ItemDto> create(
    @RequestBody CreateItemRequest request,
    @RequestHeader("X-Idempotency-Key") String key
);
~~~

This is an example method inside an interface that already has the `@HttpExchange("/api/items")` prefix; do not repeat `/api/items` in `@PostExchange` to avoid doubling the path. A header alone is not enough to guarantee idempotency unless the server implements key handling.

## 15. Mini Lab: Two Instances, One Interface

**Goal:** confirm that `findById` routes to different instances via service ID, and understand why the proxy method can still fail when one instance stops or discovery is empty.

### Setup

1. Build a server service with `@GetMapping("/api/items/{id}")` returning the same `ItemDto` shape on ports 18081 and 18082.
2. Configure `SimpleDiscoveryClient` in the caller as in section 8.
3. Create a `CatalogHttpApi` bean using `HttpServiceProxyFactory` and a `@LoadBalanced` `RestClient.Builder`.
4. Write an endpoint in the caller that invokes the proxy:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallerDemoController {

    private final CatalogHttpApi catalog;

    CallerDemoController(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/demo/items/{id}")
    ItemDto item(@PathVariable String id) {
        return catalog.findById(id);
    }
}
~~~

5. Send multiple requests:

~~~bash
curl -i http://localhost:18090/demo/items/42
curl -i http://localhost:18090/demo/items/42
curl -i http://localhost:18090/demo/items/42
~~~

To see which instance was actually selected, add an `instanceId` field/response header on the server in the lab, or inspect backend logs/tracing. Because both servers return identical DTOs, **identical JSON bodies alone do not prove load balancing is happening**.

### Verifying Behavior When One Instance Fails

Stop the instance on port 18082 and keep calling the caller. There may be a window of connection errors if the static discovery source still lists 18082 or the health check has not updated yet. LoadBalancer does not automatically detect and remove every dead address instantaneously.

If a health-check supplier is enabled, observe the candidate list before and after probes update. When the instance recovers, verify it is re-added according to policy; do not infer from a single successful response that everything has converged.

### Test Cases to Verify

| Scenario | Verification Expectation |
|---|---|
| Only one instance registered | Proxy still succeeds if that instance is healthy and the endpoint exists |
| Two instances registered | Both instances can be observed being selected per policy |
| Wrong service ID in `baseUrl` | No matching instance or target resolution error |
| Wrong path in annotation URL | Backend returns HTTP 404 if the server still receives the request |
| Backend returns 500 | Proxy/adapter represents the HTTP error per configuration |
| Dead instance still in list | Connection errors or timeouts may occur before the list updates |
| DTO schema changes | Decoding error may occur even when HTTP status is successful |
| Client uses non-`@LoadBalanced` `RestClient.Builder` | Logical host may be resolved via normal DNS |
| `POST` retried when response is lost | Must prove backend avoids creating duplicate resources |
| `WebClient` SSE stream | One HTTP request stays pinned to the selected instance; events do not round-robin automatically |

Do not assume identical output/exception types across all Spring Cloud versions. Testing must rely on real HTTP requests, actual client configuration, registry state, and server responses.

## 16. Common Design Pitfalls

1. **Confusing a client interface with a REST controller:** declaring `@HttpExchange` alone does not create a server endpoint.
2. **Forgetting to create the proxy:** Spring does not automatically register every `@HttpExchange` interface as a bean without proper configuration.
3. **Forgetting `@LoadBalanced`:** proxies via `RestClientAdapter`/`WebClientAdapter` still require a LoadBalancer-integrated underlying client to resolve service IDs.
4. **Duplicating path prefixes:** interface has `@HttpExchange("/api/items")` and method also has `@PostExchange("/api/items")`, producing an invalid path.
5. **Arbitrarily using `@GetMapping`/`@PostMapping` instead of `@GetExchange`/`@PostExchange`:** MVC annotations target server mappings or different contracts, not the metadata expected by HTTP Service Proxy.
6. **Omitting explicit parameter names:** placeholder `{id}` mismatches `@PathVariable("itemId")`.
7. **Using `@RequestParam` instead of `@RequestBody`:** query strings and JSON bodies are two different ways of passing data.
8. **Confusing `Content-Type` and `Accept`:** expecting a JSON response does not mean the request always sends JSON.
9. **Hardcoding credentials in annotations or request logs:** leaks keys and tokens.
10. **Treating `ResponseEntity` as a way to ignore all HTTP errors:** default status handling may throw an exception beforehand.
11. **Using reactive return types on `RestClientAdapter` without verifying support:** choose the matching adapter and return types.
12. **Missing timeouts and retry budgets:** the proxy looks simple, yet still performs network I/O and can block threads for a long time.
13. **Retrying `POST` without idempotency:** the previous request may already have been processed by the server.
14. **Ignoring discovery/health on failures:** a "Java method throwing an error" can be caused by having no `ServiceInstance` before any HTTP request is sent.
15. **Not verifying Framework/Cloud versions:** factory and adapter APIs must match actual dependency versions.

## 17. Implementation Checklist and Conclusion

Before using HTTP Service Interface in production, confirm that:

- The interface declares `@HttpExchange` properly at the shared level and one HTTP method annotation per method.
- Interface-level + method-level paths produce the intended URL without duplicated prefixes.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody`, and `@RequestPart` follow the HTTP contract.
- DTOs and generic return types match the server's schema and content types.
- `HttpServiceProxyFactory` is built from the right adapter for the active HTTP client.
- If the URL host is a service ID, the HTTP client is created from a `@LoadBalanced` builder and discovery has matching instances.
- `RestClientAdapter` is paired with synchronous models; `WebClientAdapter` is paired with reactive publishers when needed.
- Missing-instance errors, connection errors, HTTP 4xx/5xx, and decode errors are classified separately.
- Timeouts, retry/backoff, idempotency, and total deadlines match SLOs.
- Logs/traces capture service ID, selected instance, HTTP status, and exception cause without exposing sensitive data.
- Integration tests cover at least one successful response, HTTP error responses, and unavailable-instance scenarios.

**Conclusion:** HTTP Service Interface helps define **declarative, type-safe, and reusable** HTTP client contracts. `@HttpExchange` sets shared configuration, `@GetExchange`/`@PostExchange`/`@PutExchange`/`@PatchExchange`/`@DeleteExchange` describe the HTTP method, and `@PathVariable`/`@RequestParam`/`@RequestHeader`/`@RequestBody`/`@RequestPart` bind request data. To call **by service name**, create the proxy from `RestClientAdapter` or `WebClientAdapter` with a client integrated with **Spring Cloud LoadBalancer**, and combine it with discovery, health checks, timeouts, retries, and observability. It is these operational components — not annotations alone — that keep inter-service communication reliable when instances change or fail.
