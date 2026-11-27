# Headers, Query Parameters, Path Variables, and Request Bodies

When one service calls another service's HTTP API, the request typically carries four kinds of information: **path variables** identify the resource, **query parameters** supply query conditions, **headers** pass metadata, and the **request body** carries business data. Separating these roles properly makes APIs easy to read, easy to test, and reliable when communicating through Spring Cloud LoadBalancer.

In the client-side load balancing model, the calling application typically uses a **service ID** as a logical host, such as `http://inventory-service`. Spring Cloud LoadBalancer picks an eligible `ServiceInstance` and forwards the request to that instance. Instance selection does not change the meaning of paths, query parameters, headers, or bodies: these components must still follow the HTTP contract published by the target service.

## 1. How to Read an HTTP Request

An HTTP request consists of a request line, headers, a blank line, and an optional body. With HTTP/1.1, the example below represents a request to create an item inside an order:

```http
POST /api/orders/ORD-2026-001/items?include=product,price HTTP/1.1
Host: order-service
Accept: application/json
Content-Type: application/json
Authorization: Bearer <access-token>
X-Correlation-ID: 8f3c2a1d
Idempotency-Key: create-item-ORD-2026-001-01

{
  "productId": "P-1001",
  "quantity": 2,
  "note": "Deliver with the same order"
}
```

In this example:

| Component | Value | Role |
|---|---|---|
| Path variable | `ORD-2026-001` in `/api/orders/{orderId}/items` | Identifies the order to add the item to. |
| Query parameter | `include=product,price` | Asks the API to return additional product and price information. |
| Header | `Accept`, `Content-Type`, `Authorization`, `X-Correlation-ID` | Passes desired response format, request payload format, authentication credentials, and request tracking ID. |
| Request body | `productId`, `quantity`, `note` | Carries the data required to create the item. |

`Host: order-service` here illustrates the logical host used by the application before service ID resolution. When the request goes through an HTTP client configured with Spring Cloud LoadBalancer, the target host on the actual connection will be the address of the chosen instance.

## 2. Path Variables: Identifying Resources in the Path

A path variable is part of the URL path, typically representing a resource identifier or an element within a resource hierarchy. For example:

```http
GET /api/products/P-1001
GET /api/orders/ORD-2026-001/items/ITEM-07
```

The first path requests product `P-1001`; the second path points to item `ITEM-07` belonging to order `ORD-2026-001`. Readers can tell which resource is being accessed directly from the URL.

In Spring MVC, declare a path variable using `@PathVariable`:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{productId}")
    ProductResponse getProduct(
            @PathVariable("productId") String productId) {
        return productService.findById(productId);
    }
}
```

When calling this endpoint, the value `P-1001` in the URL is bound to the `productId` parameter.

Use path variables when:

- The value is an identifier needed to locate the resource.
- Resources have a clear hierarchical relationship, such as `/orders/{orderId}/items/{itemId}`.
- The endpoint represents an operation on a specific resource, such as `GET /products/{id}`, `PUT /products/{id}`, or `DELETE /products/{id}`.

Avoid putting optional filters, search keywords, or large data sets into the path. That information belongs in query parameters or the body. Also encode special characters according to URL rules; never concatenate strings arbitrarily if values may contain `/`, spaces, or reserved characters.

## 3. Query Parameters: Supplying Query Conditions

Query parameters appear after the `?` in a URL. Multiple parameters are separated by `&`. They are commonly used for filtering, searching, pagination, sorting, or requesting expanded data.

```http
GET /api/products?category=book&active=true&page=0&size=20&sort=name,asc
GET /api/products/P-1001?include=stock,price
```

The first example retrieves active products in the `book` category on the first page, 20 items per page, sorted ascending by name. The second example retrieves a specific product and asks to include stock and price.

In Spring MVC, use `@RequestParam`:

```java
@GetMapping
List<ProductResponse> searchProducts(
        @RequestParam(required = false) String category,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(defaultValue = "name,asc") String sort) {
    return productService.search(category, page, size, sort);
}
```

With `required = false`, the parameter can be omitted. With `defaultValue`, Spring uses the default value when the parameter is absent or empty. The application still needs to validate bounds, such as preventing `size` from exceeding a maximum limit or `page` from being negative.

A parameter may appear multiple times, such as `?tag=java&tag=spring`. You can receive these values as `List<String>` or `MultiValueMap<String, String>` depending on your needs. If an API uses a comma-separated list convention like `?sort=name,asc`, that convention should be clearly documented in the API contract.

Use query parameters when:

- The information only changes how results are queried or presented, not the resource identifier.
- The parameter is optional, has a default value, or combines with other filters.
- The client needs pagination, sorting, or a subset of related data.

Query values must be URL-encoded. Do not put passwords, access tokens, or secret data in the query string: URLs frequently appear in access logs, browser histories, monitoring systems, and certain referrer headers.

## 4. Headers: Passing Request Metadata

Headers are name-value pairs placed before the blank line separating the body. Headers describe the request or processing context, such as data format, authentication, caching, update preconditions, and observability metadata.

Common headers:

| Header | Meaning |
|---|---|
| `Accept` | Response formats accepted by the client, for example `application/json`. |
| `Content-Type` | Format of the request body, for example `application/json`. |
| `Authorization` | Authentication credentials, commonly carrying a Bearer token in OAuth 2.0 systems. |
| `X-Correlation-ID` | Application-defined correlation ID used to link logs for a single request across multiple services. |
| `traceparent` | W3C Trace Context header used to propagate distributed tracing context. |
| `Idempotency-Key` | Application-defined key used to identify repeated submissions of a safely repeatable request. |

The two easiest headers to confuse are `Accept` and `Content-Type`:

- `Accept` tells the server what format the client wants to **receive** the response in.
- `Content-Type` tells the server what format the body the client **is sending** has.

For example, the client sends JSON and wants to receive JSON:

```http
Content-Type: application/json
Accept: application/json
```

In Spring MVC, use `@RequestHeader` to read a header:

```java
@GetMapping("/{productId}")
ProductResponse getProduct(
        @PathVariable String productId,
        @RequestHeader("X-Correlation-ID") String correlationId) {
    return productService.findById(productId, correlationId);
}
```

If a header is optional, set `required = false` or specify a default value. Spring also supports receiving multiple headers as `HttpHeaders` or `Map<String, String>` when an endpoint needs flexible handling.

Header names are case-insensitive per HTTP rules. Still, avoid inventing custom headers when a suitable standard header already exists. Custom headers like `X-Correlation-ID` need a consistent convention across services.

Headers arriving from a client are still untrusted input. The server must validate tokens, check permissions, and verify values such as tenant IDs before using them to decide which data can be accessed. Do not log access tokens, cookies, or sensitive information.

## 5. Request Body: Sending Business Data

The request body follows the blank line in an HTTP message. It typically carries data to be created or updated. The body can use JSON, XML, form data, multipart, or another format depending on the API contract. For REST APIs in Spring applications, JSON is a common choice.

Example product creation request:

```http
POST /api/products HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "sku": "BOOK-001",
  "name": "Spring Cloud in Practice",
  "initialQuantity": 25
}
```

In Spring MVC, use `@RequestBody` to bind the body content to a DTO. Combine `@Valid` with Bean Validation to validate data before running business logic:

```java
public record CreateProductRequest(
        @NotBlank String sku,
        @NotBlank String name,
        @PositiveOrZero int initialQuantity) {
}

@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
ProductResponse createProduct(
        @Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
```

`Content-Type` must match the body format supported by the endpoint. If the server does not support the format sent, the request may receive `415 Unsupported Media Type`. If the JSON is invalid or fails validation, the application typically returns `400 Bad Request` with appropriate error details.

HTTP methods are typically used as follows:

- `POST`: send data to create a resource or execute an operation.
- `PUT`: send a full representation to replace the state of the resource identified by the URL.
- `PATCH`: send the partial changes to apply to a resource.
- `GET` and `HEAD`: should not depend on a request body. Body semantics for these methods are not uniformly defined, and some proxies or servers may ignore or reject the body.

When updating an existing resource with an identifier, usually place the identifier in the path, such as `PUT /api/products/P-1001`, while the body contains the properties to update. Avoid carrying the same identifier in both the path and body where they could diverge; if the contract requires both, the server must verify they are consistent.

## 6. Combining All Four Components in One Controller

The example below illustrates a product API. The endpoint that reads a product takes the identifier from the path, an optional expansion field via query, and the correlation ID from a header. The endpoint that creates a product receives business data from the body.

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{productId}")
    ProductResponse getProduct(
            @PathVariable String productId,
            @RequestParam(name = "include", required = false) String include,
            @RequestHeader(name = "X-Correlation-ID", required = false)
                    String correlationId) {
        return productService.find(productId, include, correlationId);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ProductResponse createProduct(
            @Valid @RequestBody CreateProductRequest request,
            @RequestHeader(name = "X-Correlation-ID", required = false)
                    String correlationId) {
        return productService.create(request, correlationId);
    }
}
```

Each parameter has a clear source. API readers can distinguish resource identifiers, query options, request metadata, and business payloads without guessing from variable names.

## 7. Sending Requests Through Spring Cloud LoadBalancer

When one service calls another, the client can use a service ID instead of a specific instance's hostname. For example, `inventory-service` is the logical name of the inventory management service. An HTTP client attached to Spring Cloud LoadBalancer resolves the service ID to a `ServiceInstance` before sending the request.

With `RestClient`, you can declare a load-balanced builder:

```java
@Configuration
class InventoryHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Then use this builder to create the client. The GET example below passes `productId` in the path, `include` in the query, and `X-Correlation-ID` in a header:

```java
@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    ProductResponse getProduct(
            String productId, String include, String correlationId) {
        return restClient.get()
                .uri(uriBuilder -> uriBuilder
                        .scheme("http")
                        .host("inventory-service")
                        .path("/api/products/{productId}")
                        .queryParamIfPresent(
                                "include", Optional.ofNullable(include))
                        .build(productId))
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Correlation-ID", correlationId)
                .retrieve()
                .body(ProductResponse.class);
    }

    ProductResponse createProduct(
            CreateProductRequest request,
            String correlationId,
            String idempotencyKey) {
        return restClient.post()
                .uri("http://inventory-service/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Correlation-ID", correlationId)
                .header("Idempotency-Key", idempotencyKey)
                .body(request)
                .retrieve()
                .body(ProductResponse.class);
    }
}
```

`ProductResponse` and `CreateProductRequest` are application DTOs. The example assumes the application already has Jackson and the required HTTP client configuration. With `RestClient`, the request body is serialized by a message converter matching `Content-Type`.

With `WebClient`, use a `WebClient.Builder` marked with `@LoadBalanced`, after which you can keep the same separation of path, query, headers, and body:

```java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
```

```java
@Service
class InventoryReactiveGateway {

    private final WebClient webClient;

    InventoryReactiveGateway(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<ProductResponse> getProduct(
            String productId, String include, String correlationId) {
        return webClient.get()
                .uri("http://inventory-service/api/products/{id}?include={include}",
                        productId, include)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Correlation-ID", correlationId)
                .retrieve()
                .bodyToMono(ProductResponse.class);
    }
}
```

With OpenFeign, the service ID name is declared in `@FeignClient`. Spring MVC annotations continue to express the placement of each value in the request:

```java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/products/{productId}")
    ProductResponse getProduct(
            @PathVariable("productId") String productId,
            @RequestParam("include") String include,
            @RequestHeader("X-Correlation-ID") String correlationId);

    @PostMapping(
            value = "/api/products",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ProductResponse createProduct(
            @RequestBody CreateProductRequest request,
            @RequestHeader("X-Correlation-ID") String correlationId);
}
```

When OpenFeign is integrated with Spring Cloud LoadBalancer, the client can resolve `inventory-service` and select an appropriate instance. Whether using `RestClient`, `WebClient`, or OpenFeign, the endpoint's HTTP contract still governs which data belongs in the path, query, headers, and body.

High-level processing flow:

```mermaid
flowchart LR
    A[Calling service] --> B[RestClient / WebClient / OpenFeign]
    B --> C[Spring Cloud LoadBalancer]
    C --> D[Select ServiceInstance]
    D --> E[HTTP request: path, query, header, body]
    E --> F[Target service controller]
```

LoadBalancer resolves the instance address by service ID. It does not fix a wrong path, add missing query parameters, generate authentication headers, or transform a body to fit an API. Those responsibilities belong to the client and the contract between services.

## 8. Impact on Retries, Security, and Observability

HTTP components also affect how errors are handled when communicating across multiple instances:

- **Retry:** `GET` requests can usually be safely resent if the API adheres to read semantics. For a `POST` that creates data, resending can create duplicate records. If a creation operation needs retries, both sides should agree on an idempotency mechanism, such as accepting `Idempotency-Key` and storing the outcome tied to that key.
- **Timeout:** timeouts apply to the entire call or individual phases depending on client configuration. Overly broad queries, oversized bodies, or slow endpoints can all cause a request to exceed its timeout; appropriate limits and API design are needed.
- **Security:** transmit authentication credentials via headers according to the agreed mechanism, use TLS where appropriate, and verify permissions in the target service. Never treat an internal service ID or client-supplied header as proof of authentication.
- **Tracing and logging:** propagate trace context or correlation IDs across calls to link logs between caller and callee. Logs should prioritize method, path template, service ID, selected instance, status code, and duration; avoid logging tokens or bodies containing sensitive data.

When a request through LoadBalancer fails, distinguish service ID resolution or no-instance errors from HTTP errors returned by the target service. A request reaching a valid instance with the wrong path will still return `404 Not Found`; LoadBalancer cannot fix API contract mismatches.

## 9. Reading HTTP Errors to Find the Right Component to Check

| Status code | Common cause | Component to check |
|---|---|---|
| `400 Bad Request` | Invalid path/query, malformed JSON, or validation failure. | Path variables, query parameters, and body. |
| `401 Unauthorized` | Missing or invalid authentication credentials. | `Authorization` and authentication configuration. |
| `403 Forbidden` | Identity is authenticated but lacks permission for the operation. | Access permissions and security policies. |
| `404 Not Found` | Wrong endpoint, wrong path variable, or resource does not exist. | Path and target resource. |
| `406 Not Acceptable` | Server cannot produce a response in the format requested by the client. | `Accept`. |
| `415 Unsupported Media Type` | Server does not support the format of the sent body. | `Content-Type` and converter configuration. |
| `429 Too Many Requests` | Client sent too many requests within a time window. | Rate-limiting policy and retry cadence. |
| `5xx` | Target service or request-handling infrastructure encountered an error. | Logs of the chosen instance, timeouts, and service health. |

When investigating errors, record the service ID and the actual selected instance along with the correlation ID. That helps determine whether the request stopped at instance selection, in transit, or inside the target service's controller.

## 10. Rules for Choosing the Right Place for Data

| Question | Where should it go? | Example |
|---|---|---|
| Which resource is being accessed? | Path variable | `/products/{productId}` |
| How should results be filtered, paginated, or expanded? | Query parameter | `?page=0&size=20&include=stock` |
| What metadata or processing context does the request need? | Header | `Authorization`, `Accept`, `X-Correlation-ID` |
| What data needs to be created or updated? | Request body | JSON containing `sku`, `name`, `quantity` |

Before finalizing an inter-service endpoint, check the following points:

1. Paths express resources and stable identifiers; queries contain only query options.
2. Headers have a clear purpose, use HTTP standards whenever possible, and no secrets are placed in URLs.
3. Bodies have a defined schema, an appropriate `Content-Type`, and input validation.
4. The client sends the correct service ID when using Spring Cloud LoadBalancer, while preserving the target service's HTTP contract.
5. Retries are enabled only when the operation can be safely resent or an idempotency mechanism is in place; correlation IDs/trace context are propagated for cross-service tracking.

When all four components are used in their proper roles, APIs become clear and clients can call services across multiple instances without altering the meaning of the request.
