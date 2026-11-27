# Mapping Response Types, Status Codes, and Exceptions

**RestClient** is Spring Framework's synchronous HTTP client with a fluent API. When using RestClient in a Spring Cloud LoadBalancer system, a call from **Order Service** to **inventory-service** typically goes through two legs: first, LoadBalancer selects a **ServiceInstance** by service ID; second, the HTTP client sends the request to the actual instance and processes the response. The second leg involves three crucial decisions: **which Java type to deserialize the body into**, **how to interpret the HTTP status**, and **which exception to translate error scenarios into**.

For example, the same endpoint GET /api/stock/BOOK-01 can return:

| Response | Meaning | How the caller should interpret it |
| --- | --- | --- |
| 200 + valid JSON | Stock fetched successfully | Deserialize into StockResponse |
| 204, no body | No content returned | Do not force a required DTO |
| 404 + error body | SKU does not exist | Can be translated into business error StockNotFound |
| 409 + error body | State conflict | Do not retry by default |
| 429 + Retry-After | Downstream rate limit | Apply controlled retry/backoff |
| 503 + error body | Downstream or LB layer unavailable | Distinguish an actual HTTP response from an instance-selection failure |
| Timeout or connection error | No valid HTTP response received | Handle transport exception separately |
| 200 + schema-mismatched JSON | Response received but cannot be decoded | Handle contract/message conversion error |

The goal of this lesson is to establish a **clear error contract between the HTTP layer and the business layer**, avoiding the misconception that every response returns a DTO or that every error is an HTTP 500.

**Version scope:** Examples prioritize common APIs from Spring Framework 6.1 onward, where RestClient was introduced. Newer APIs, such as requiredBody() in Spring Framework 7.0.x releases, are noted separately so they do not cause confusion when projects run Spring 6.x. Use a Spring Boot–Spring Cloud BOM compatible with your real system.

## 1. Three layers to distinguish before handling a response

~~~mermaid
flowchart TD
    A["Client calls http://inventory-service/..."] --> B["LoadBalancer finds ServiceInstance"]
    B --> C{"Instance selected?"}
    C -->|No| D["Target selection / no-instance error"]
    C -->|Yes| E["Connect HTTP to actual host:port"]
    E --> F{"HTTP response received?"}
    F -->|No| G["Network, DNS, TLS, timeout error"]
    F -->|Yes| H{"HTTP status"}
    H -->|"2xx / accepted status"| I["Convert body to DTO"]
    I --> J{"Decode succeeded?"}
    J -->|Yes| K["Typed result for business logic"]
    J -->|No| L["Message conversion / contract error"]
    H -->|"4xx / 5xx"| M["Status handler or default throws exception"]
~~~

When investigating an error, separate:

1. **No instance found:** the discovery list is empty or filters eliminated all candidates; the HTTP send step may not have occurred yet.
2. **Transport failure:** a target URI existed, yet connection setup failed, TLS handshake failed, connection reset, or timeout occurred; typically no reliable HTTP status exists.
3. **HTTP error response:** the server or gateway genuinely returned 4xx/5xx; a status, headers, and possibly an error body exist.
4. **Decode failure:** the HTTP response may be 200, yet the body does not fit the Java type, JSON is malformed, or Content-Type is unsupported.

RestClient only handles the HTTP client; Spring Cloud LoadBalancer handles discovery and ServiceInstance selection. Exception mapping inside Order Service's adapter should preserve this distinction so retries, observability, and operational alerts stay accurate.

## 2. Creating RestClient properly in a LoadBalancer-enabled application

For URLs whose host is a service ID, you need a RestClient.Builder integrated with Spring Cloud LoadBalancer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

In the business client:

~~~java
@Service
class InventoryHttpClient {

    private final RestClient client;

    InventoryHttpClient(@LoadBalanced RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

For the code to work, the application needs **spring-cloud-starter-loadbalancer** and an instance source, such as Eureka, Consul, or SimpleDiscoveryClient. Spring Cloud integrates **BlockingLoadBalancerClient** to resolve the service ID into an actual host/port before sending the HTTP request.

**Do not confuse discovery errors with response mapping errors.** If no instance of inventory-service exists, RestClient cannot deserialize an HTTP error body from the server because no server was called. Depending on the adapter and release train, the failure may surface as an exception or an HTTP error response synthesized by the load-balancing layer; inspect the trace and origin rather than forcing every case into a single exception type.

If a client calls a partner endpoint with a fixed URL, usually use a RestClient without LoadBalancer attached. Separate beans/builders can be created to avoid feeding real hosts such as api.partner.example into service-ID lookup.

## 3. From JSON to DTO: body(Class<T>)

RestClient provides a direct way to read the body:

~~~java
record StockResponse(
        String sku,
        int available,
        String warehouse) {
}

StockResponse result = client.get()
        .uri("/api/stock/{sku}", "BOOK-01")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(StockResponse.class);
~~~

With the response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"BOOK-01","available":7,"warehouse":"HCM"}
~~~

Spring selects the **HttpMessageConverter** matching Content-Type and the target type. When Jackson is configured, JSON is converted into the StockResponse record.

Four facts to keep in mind:

- body(StockResponse.class) returns **StockResponse or null** if there is no body.
- The Java object **does not include status or headers**; to inspect them, use toEntity().
- If the response has a 4xx/5xx error HTTP status, the default status handler throws an exception **before** you ever receive a DTO.
- If the HTTP status is accepted yet the body fails to deserialize, that is a **mapping/contract** error, not automatically a 404 or 503.

### 3.1. Do not infer that 200 always carries a valid body

An API can return 200 with an empty body, JSON null, or JSON missing essential fields. Do not treat null as a valid business DTO or continue processing without checking.

~~~java
StockResponse response = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);

if (response == null) {
    throw new InvalidInventoryResponseException(
            "Inventory returned no body");
}
~~~

InvalidInventoryResponseException here is an **application-defined domain exception**, not a built-in Spring class. Depending on requirements, also validate sku, available, warehouse, and invariants after deserialization; Jackson does not enforce every business rule automatically.

### 3.2. requiredBody() is only available in newer versions

In Spring Framework 7.0.4 and later, **ResponseSpec.requiredBody(...)** requires a non-null result and throws IllegalStateException when no body is present. On Spring Framework 6.1/6.2 or earlier 7.0 releases, do not use this API without verifying availability; instead use explicit null checks as in the example above.

## 4. Mapping generic JSON: ParameterizedTypeReference

Class<T> cannot fully represent generic types like List<StockResponse> or PageResponse<StockResponse> due to Java type erasure. When an API returns a list or generic wrapper, use **ParameterizedTypeReference<T>**:

~~~java
List<StockResponse> stocks = client.get()
        .uri("/api/stocks?warehouse={warehouse}", "HCM")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(new ParameterizedTypeReference<List<StockResponse>>() {});
~~~

Illustrative response:

~~~json
[
  {"sku":"BOOK-01","available":7,"warehouse":"HCM"},
  {"sku":"BOOK-02","available":4,"warehouse":"HCM"}
]
~~~

For a wrapper:

~~~java
record PageResponse<T>(
        List<T> content,
        int page,
        int totalPages) {
}

PageResponse<StockResponse> page = client.get()
        .uri("/api/stocks?page={page}", 0)
        .retrieve()
        .body(new ParameterizedTypeReference<PageResponse<StockResponse>>() {});
~~~

Do not use body(List.class) and cast to List<StockResponse>; elements may deserialize as maps instead of DTOs, leading to ClassCastException or silent bugs in the business layer.

**Note:** ParameterizedTypeReference preserves target type information for the converter. It does not fix schema-invalid JSON, turn 404 into an empty list, or guarantee arbitrary JSON variants deserialize cleanly.

## 5. When status and headers are needed: toEntity()

When a service returns ETag, Location, Retry-After, or an HTTP code that the adapter layer must inspect, use **ResponseEntity<T>**:

~~~java
ResponseEntity<StockResponse> entity = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .toEntity(StockResponse.class);

HttpStatusCode status = entity.getStatusCode();
HttpHeaders headers = entity.getHeaders();
StockResponse stock = entity.getBody();
~~~

Advantages of toEntity():

- Returns **status** and **headers**, even for valid responses without a body.
- Deserializes the body to the declared type when content is present.
- Preserves metadata for cases like 201 Created with Location or 200 with ETag.
- Also provides an overload accepting ParameterizedTypeReference<T> for generic types.

**Common pitfall:** toEntity(...) **does not return a ResponseEntity for 404 or 500 by default**. When using retrieve(), error statuses are still processed by onStatus/default status handlers and typically throw RestClientResponseException. If business logic must treat 404 as a normal branch, define an explicit policy.

### 5.1. Need only status and headers: toBodilessEntity()

~~~java
ResponseEntity<Void> entity = client.post()
        .uri("/api/reservations")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ReserveRequest(sku, quantity))
        .retrieve()
        .toBodilessEntity();

HttpStatusCode status = entity.getStatusCode();
URI location = entity.getHeaders().getLocation();
~~~

This is the right choice when an API returns **201 Created** with a Location header and no useful payload, or returns **204 No Content**.

Do not try to parse a DTO from a 204 response just to tell whether the request succeeded; the status code itself is the primary outcome to record.

## 6. Reading HTTP statuses by semantics instead of only checking 200

| Status | Common scenario | Suggested mapping |
| --- | --- | --- |
| 200 OK | Returns requested data | body(DTO) or toEntity(DTO) |
| 201 Created | New resource created | toEntity()/toBodilessEntity(), read Location if needed |
| 202 Accepted | Accepted for asynchronous processing | Do not treat as business-completed yet; poll later with operation ID |
| 204 No Content | Operation succeeded, empty body | toBodilessEntity() or void domain return |
| 206 Partial Content | Range-based response | Requires chunked download contract, Content-Range |
| 304 Not Modified | Conditional cache indicates unchanged content | Do not expect JSON DTO; handle conditional/cache logic |
| 400 Bad Request | Invalid request | Validation/contract error, normally do not retry |
| 401 Unauthorized | Missing or invalid authentication | Check token and auth flow |
| 403 Forbidden | Insufficient permissions | Authorization error, do not retry blindly |
| 404 Not Found | Missing resource or wrong endpoint | Domain-dependent mapping; separate missing resource from wrong route |
| 409 Conflict | Version/state conflict | Domain conflict; resolve condition before retrying |
| 412 Precondition Failed | ETag/If-Match no longer valid | Refresh state before deciding next action |
| 422 Unprocessable Content | Syntactically valid but semantically invalid data | Input business error |
| 429 Too Many Requests | Rate limiting | Inspect Retry-After, backoff, deadline |
| 500 Internal Server Error | Server-side failure | Report downstream failure; retry only if safe by policy |
| 502 Bad Gateway | Upstream proxy/gateway error | Inspect infrastructure, bounded retry |
| 503 Service Unavailable | Downstream unavailable | Distinguish backend 503 from LB having no instances |
| 504 Gateway Timeout | Gateway timed out calling upstream | Execution may already have happened; avoid non-idempotent retries |

Do not treat every **2xx** as the same business outcome. For example, **202** means accepted for processing, not finished; **204** carries no body; **206** requires reassembly logic when fetching ranges.

**3xx** statuses depend on the HTTP request factory's redirect settings. When a 304 response reaches RestClient, do not assume the converter will automatically fetch from cache or build a DTO out of an empty body. Requests sent via LoadBalancer also do not automatically rewrite every Location header or decide whether to follow redirects to another host.

### 6.1. Do not equate HTTP status with domain status

An API might return 200 with payload:

~~~json
{"sku":"BOOK-01","status":"OUT_OF_STOCK"}
~~~

This is **HTTP success** yet **domain out-of-stock state**. Do not convert it into 503 to trigger infrastructure retries. Domain status should be inspected after deserialization and handled per contract.

Similarly, a 409 response caused by optimistic locking is not the same as a 503 caused by a dropped instance connection; applying the same retry policy to both is wrong.

## 7. Default exceptions of retrieve()

In Spring Framework, retrieve() treats **4xx and 5xx** as HTTP errors by default. Common exceptions live in this hierarchy:

~~~text
RestClientException
├── RestClientResponseException
│   ├── HttpStatusCodeException
│   │   ├── HttpClientErrorException  (4xx)
│   │   └── HttpServerErrorException  (5xx)
│   └── other response exceptions depending on API/version
├── ResourceAccessException          (I/O, timeout, TLS ...)
└── other message conversion or request exceptions
~~~

This is a **conceptual diagram of the main branches**, not an exhaustive list of every subclass across all versions. When working against a specific release, consult Javadoc if you need to catch an exact subclass.

Default example:

~~~java
try {
    StockResponse stock = client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);

    return stock;
} catch (HttpClientErrorException.NotFound ex) {
    // Real HTTP 404 from server/adapter.
    throw new StockNotFoundException(sku, ex);
} catch (HttpServerErrorException ex) {
    throw new InventoryUnavailableException("Inventory returned 5xx", ex);
} catch (ResourceAccessException ex) {
    throw new InventoryTransportException("Cannot reach inventory", ex);
}
~~~

In the example, the three exceptions **StockNotFoundException**, **InventoryUnavailableException**, and **InventoryTransportException** are application-defined domain classes. Preserve the **cause** so the original stack trace is not lost, while avoiding exposing raw exceptions/causes to end users.

### 7.1. Extracting details from RestClientResponseException

~~~java
catch (RestClientResponseException ex) {
    int code = ex.getStatusCode().value();
    HttpHeaders headers = ex.getResponseHeaders();
    String rawBody = ex.getResponseBodyAsString();

    log.warn("Inventory HTTP failure: status={}, bytes={}",
            code, rawBody.length());

    throw new DownstreamHttpException(code, ex);
}
~~~

RestClientResponseException can expose status, headers, and response body. However, never log the raw body unconditionally: error payloads can contain tokens, customer info, or sensitive data. If logging is needed, cap size and redact sensitive content first.

When an API has a consistent error JSON schema, you can use **getResponseBodyAs(ErrorDto.class)** on versions supporting error body decoding, or decode manually with a configured ObjectMapper, while handling empty/non-JSON bodies. **Do not assume every HTTP exception carries a schema-compliant error DTO.**

## 8. onStatus(): mapping 404/409/429/5xx to business semantics

**onStatus(Predicate<HttpStatusCode>, ErrorHandler)** attaches a handling rule to responses of the current retrieve call. This is a clean way to translate HTTP statuses into domain exceptions.

~~~java
StockResponse stock = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                (request, response) -> {
                    throw new StockNotFoundException(sku);
                })
        .onStatus(
                status -> status.value() == 409,
                (request, response) -> {
                    throw new StockConflictException(sku);
                })
        .onStatus(
                HttpStatusCode::is5xxServerError,
                (request, response) -> {
                    throw new InventoryUnavailableException(
                            "Inventory status " + response.getStatusCode());
                })
        .body(StockResponse.class);
~~~

Here the custom exceptions are application-created **unchecked exceptions**. The rule runs after the client receives an HTTP response; it cannot directly catch pre-response network errors.

Things to remember:

- The predicate can match **a single specific status** or a whole group, such as HttpStatusCode::is5xxServerError.
- Each handler can throw a domain exception, or refrain from throwing if you intentionally want to ignore a specific HTTP error.
- When **no handler matches**, retrieve()'s default error rules still apply to 4xx/5xx.
- Handler order and scope must be designed to avoid ambiguous overlap, such as placing an all-4xx handler before a specific 404 handler.
- A handler may read the response body if needed, but once the stream is consumed there must be a clear policy on further conversion; typically it is best to **throw an exception immediately after reading the error body**.

### 8.1. Mapping 404 to Optional.empty(): do it in the adapter

Not every 404 means the same thing:

- GET /stock/{sku}: 404 may mean **SKU does not exist yet**, and the domain contract accepts an empty result.
- GET /api/stocks: 404 may mean **wrong route or API version**, which must raise an error.
- A 404 from a reverse proxy may mean **backend not found**, not a missing business resource.

When the contract confirms 404 means resource not found, the most maintainable approach is keeping default HTTP behavior and converting the exception in the adapter:

~~~java
Optional<StockResponse> findStock(String sku) {
    try {
        return Optional.ofNullable(client.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class));
    } catch (HttpClientErrorException.NotFound ex) {
        return Optional.empty();
    }
}
~~~

Advantage: every 404 response remains accurately classified at the HTTP layer, while the **decision that 404 equals Optional.empty()** lives only in the appropriate business API. You avoid configuring a client-wide handler that swallows 404s and hides error signals on other endpoints.

If a caller genuinely wants to suppress 404 via onStatus to return a DTO/null, explicitly test whether the 404 response body is still read and decoded by converters. Do not treat a non-throwing handler as magic that turns 404 into 204.

### 8.2. Using onStatus to handle errors with important headers

Example 429 status with Retry-After:

~~~java
.onStatus(
        status -> status.value() == 429,
        (request, response) -> {
            String retryAfter = response.getHeaders()
                    .getFirst(HttpHeaders.RETRY_AFTER);
            throw new InventoryRateLimitedException(retryAfter);
        })
~~~

The Retry-After header can be **a number of seconds** or an **HTTP-date**. Do not parse the string straight into an integer without handling both formats, maximum wait caps, and total deadlines. Throwing an exception here **does not automatically schedule a retry**.

## 9. Configuring shared status handlers on RestClient.Builder

If a group of APIs shares the same error contract, you can configure defaultStatusHandler on the builder:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder()
            .defaultStatusHandler(
                    HttpStatusCode::is5xxServerError,
                    (request, response) -> {
                        throw new DownstreamUnavailableException(
                                response.getStatusCode().value());
                    });
}
~~~

When calling multiple downstreams, avoid an overly specific global handler such as always turning every 404 into StockNotFoundException: a 404 from payment-service and one from inventory-service can have different meanings.

A clean layering strategy:

- **Global default handler:** handles only generic errors like infrastructure failures or application-wide safety rules.
- **Per-client builder:** maps errors per each downstream's contract.
- **Per-request onStatus:** endpoint-specific mapping.
- **Service adapter:** translates HTTP exceptions into stable domain outcomes for business logic.

Per the API contract, per-request handlers are evaluated before default handlers; default handlers apply when no matching request-level handler applies. Handlers can be combined in registration order, so avoid overly broad predicates that unintentionally swallow special cases.

**Never register a defaultStatusHandler that throws for all statuses**: 200/201/204 must return normally. Choose predicates that truly represent errors to handle.

## 10. exchange(): more flexible, but you own status handling

RestClient offers **exchange(...)** to give the application access to raw request/response inside a callback.

~~~java
int resultStatus = client.get()
        .uri("/api/stock/{sku}", sku)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            if (status >= 400) {
                throw new InventoryUnavailableException(
                        "Inventory returned " + status);
            }
            return status;
        });
~~~

**Important warning:** when using exchange(), **status handlers configured via retrieve().onStatus() or defaultStatusHandler are not applied**. The exchange callback checks status itself and decides whether to throw an exception, read the body, or keep the stream.

When you genuinely need to read the body in exchange, handle these concerns:

1. Read the stream inside the callback while the response is still open.
2. Check status before deserializing per contract.
3. Verify Content-Type and charset.
4. Ensure the body stream is not read twice.
5. Never retain ClientHttpResponse or InputStream for use after the callback completes without lifecycle management.

Example reading a bounded raw error body:

~~~java
String responseText = client.get()
        .uri("/api/stock/{sku}", sku)
        .exchange((request, response) -> {
            int status = response.getStatusCode().value();
            byte[] bytes = response.getBody().readNBytes(4096);
            String text = new String(bytes, StandardCharsets.UTF_8);

            if (status >= 400) {
                throw new DownstreamHttpException(status);
            }
            return text;
        });
~~~

This example illustrates reading **at most 4 KiB**, does not automatically decode JSON, and assumes a UTF-8 body. In a real application, read the charset from Content-Type, bound body size, check response status, and avoid logging raw sensitive data. For normal DTO mapping, **retrieve().body()/toEntity() are simpler and less error-prone than exchange()**.

## 11. Distinguishing HTTP errors from connection, timeout, TLS, and decode errors

| Error group | Example | Typical exception/signal | Reliable HTTP status available? |
| --- | --- | --- | --- |
| HTTP 4xx | 404, 409, 429 | HttpClientErrorException or RestClientResponseException | Yes |
| HTTP 5xx | 500, 503, 504 | HttpServerErrorException or RestClientResponseException | Yes |
| Connect/read timeout | SocketTimeoutException | ResourceAccessException wrapping IOException | Usually no |
| DNS/connection refused | UnknownHostException, ConnectException | ResourceAccessException or corresponding request error | Usually no |
| TLS | SSLHandshakeException | ResourceAccessException with SSLException cause | Usually no |
| Malformed JSON | JSON field has wrong type | RestClientException/message conversion exception | Possibly HTTP 200 |
| Wrong Content-Type | No matching converter | UnknownContentTypeException or RestClientException | Possibly HTTP 200 |
| Service discovery | No ServiceInstance | Error from LoadBalancer/adapter, integration-dependent | Possibly no connection attempted |
| Callback/app domain | StockNotFoundException | Custom exception | Depends on origin |

**Handling should proceed from specific to general**. For example:

~~~java
try {
    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
} catch (HttpClientErrorException.NotFound ex) {
    throw new StockNotFoundException(sku, ex);
} catch (HttpClientErrorException.TooManyRequests ex) {
    throw new InventoryRateLimitedException(
            ex.getResponseHeaders() == null
                    ? null
                    : ex.getResponseHeaders().getFirst(HttpHeaders.RETRY_AFTER),
            ex);
} catch (HttpServerErrorException ex) {
    throw new InventoryUnavailableException("Inventory returned 5xx", ex);
} catch (ResourceAccessException ex) {
    throw new InventoryTransportException("Inventory transport failure", ex);
} catch (RestClientException ex) {
    throw new InventoryProtocolException("Unexpected inventory response", ex);
}
~~~

All domain exceptions in the example are application-defined; constructors are shown conceptually. Clear classification lets upper layers decide retries per error group instead of doing **catch(Exception)** and treating everything as an infrastructure error.

Do not infer that a timeout means the server did not process the request: the server may have written to its database and sent the response before the client timed out. That is why safe retries must be designed for requests with side effects.

## 12. Structured error bodies: domain JSON or ProblemDetail

Many APIs return error payloads in a unified schema, such as **application/problem+json** or internal JSON:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://errors.example.net/stock-conflict",
  "title": "Inventory conflict",
  "status": 409,
  "detail": "Reservation was changed by another request"
}
~~~

In Spring MVC, **ProblemDetail** is the data type representing HTTP problem details. However, a client must never assume every HTTP 409 carries that exact schema, because gateways, proxies, and older downstream versions may return HTML, plain text, or different JSON.

An adapter can keep its own contract:

~~~java
record ApiError(
        String code,
        String message,
        String traceId) {
}
~~~

If RestClient's defaultStatusHandler threw RestClientResponseException, you can inspect the response body and try decoding it:

~~~java
try {
    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
} catch (HttpClientErrorException.Conflict ex) {
    ApiError error = null;
    try {
        error = objectMapper.readValue(
                ex.getResponseBodyAsByteArray(),
                ApiError.class);
    } catch (IOException | IllegalArgumentException ignored) {
        // Error body may be empty or not match JSON contract.
    }

    String code = error == null ? "STOCK_CONFLICT" : error.code();
    throw new StockConflictException(code, ex);
}
~~~

In this example, **objectMapper** is a Jackson ObjectMapper injected from the application; StockConflictException is application-defined. The snippet illustrates preferring a structured error body while falling back safely if the body cannot be decoded.

**Avoid overly broad exception swallowing** in the HTTP layer: fall back only on anticipated error-payload parsing failures. Never use catch(Exception) to mask programming errors, null pointers, or business-flow bugs.

### 12.1. The single-read body issue

Inside **onStatus((request, response) -> ...)**, if you read response.getBody() and then return normally, downstream converters may have no remaining data to read. A less error-prone design:

1. The handler receives the error status.
2. Reads the error body once, bounding size and verifying charset/Content-Type.
3. Builds a domain exception with status, a safe message, and the required cause.
4. Throws the exception immediately from the handler.

Never store the whole ClientHttpResponse in an object used after the request finishes. Connection streams have bounded lifecycles; proper resource handling/closing is vital so connection pools do not leak.

## 13. Empty responses, Optional, and return contracts

One of the most common bugs is writing:

~~~java
StockResponse stock = client.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);

int available = stock.available();  // Potential NullPointerException!
~~~

If an HTTP response has no body, body(Class) returns null per the API contract. Therefore, define the contract per endpoint:

| Endpoint | Valid response | How to handle |
| --- | --- | --- |
| GET /stock/{sku} | 200 with mandatory StockResponse | Null is a contract violation |
| GET /stock/{sku} | 404 when SKU does not exist | Optional.empty() or domain not-found per decision |
| DELETE /reservations/{id} | 204 without body | toBodilessEntity() or void method |
| POST /reservations | 201 with Location | Check Location; body per contract |
| POST /jobs | 202 with job ID | Return pending result; do not treat as completed |
| GET /stocks | 200 with [] | Valid empty list, distinct from null response body |

Do not confuse **[]** with **null** or **404**:

- **[]**: the server returned a valid list containing 0 elements.
- **null**: no body (or JSON null), so there is no typed list to use.
- **404**: an HTTP error by default, requiring handling per endpoint contract.

For POST/DELETE returning no body, use:

~~~java
ResponseEntity<Void> result = client.delete()
        .uri("/api/reservations/{id}", reservationId)
        .retrieve()
        .toBodilessEntity();

if (!result.getStatusCode().is2xxSuccessful()) {
    throw new IllegalStateException("Unexpected reservation status");
}
~~~

By default, 4xx/5xx responses already throw an exception before reaching the is2xxSuccessful() check; the guard remains helpful when a contract accepts only 2xx and must avoid inadvertently treating another status as success.

## 14. Mapping errors into domain results: a complete adapter

The HTTP adapter layer should be responsible for **translating from HTTP semantics to domain semantics**, so business services do not have to catch HttpClientErrorException directly or understand LoadBalancer internals.

A simple result interface:

~~~java
record StockDto(String sku, int available) {
}

interface InventoryPort {
    Optional<StockDto> findStock(String sku);
}
~~~

Implementation with RestClient:

~~~java
@Service
class RestClientInventoryAdapter implements InventoryPort {

    private final RestClient client;

    RestClientInventoryAdapter(@LoadBalanced RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    @Override
    public Optional<StockDto> findStock(String sku) {
        try {
            StockDto stock = client.get()
                    .uri("/api/stock/{sku}", sku)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(StockDto.class);

            if (stock == null) {
                throw new InventoryProtocolException("Missing stock body");
            }
            return Optional.of(stock);

        } catch (HttpClientErrorException.NotFound ex) {
            // Contract: 404 means SKU does not exist yet.
            return Optional.empty();
        } catch (HttpClientErrorException.TooManyRequests ex) {
            throw new InventoryRateLimitedException(ex);
        } catch (HttpServerErrorException ex) {
            throw new InventoryUnavailableException("Inventory 5xx", ex);
        } catch (ResourceAccessException ex) {
            throw new InventoryTransportException("Inventory transport", ex);
        } catch (RestClientException ex) {
            throw new InventoryProtocolException("Invalid inventory response", ex);
        }
    }
}
~~~

The domain exceptions are project-defined classes. You do not have to map every failure directly to HTTP 500 at every layer; an external REST controller might map InventoryUnavailableException to 503, whereas a batch job might mark the task failed and schedule its own retry.

**Why catch each branch separately?**

- 404 becomes Optional.empty() per the verified contract.
- 429 and 5xx are categorized so retry layers can observe them.
- Transport errors may not have an HTTP status yet.
- Deserialization/contract errors should not be retried as availability failures.

You do not need to declare all these exceptions in InventoryPort's signature; the adapter can provide a stable domain taxonomy across the whole application.

## 15. Retries: only certain exceptions/statuses are safe to retry

In a system with LoadBalancer, a retry may pick a **different ServiceInstance**. However, **re-selecting an instance** and **re-sending the same operation** are two distinct things. A timeout after a POST creating a reservation can happen when the server has already committed the transaction.

| Scenario | Should you retry? | Conditions |
| --- | --- | --- |
| 400 validation | Usually no | Fix the request first |
| 401/403 | Usually no | Only refresh auth per valid policy, no infinite loops |
| 404 resource not found | No in standard contracts | Retry only if confirmed eventual consistency applies |
| 409 optimistic locking | Depends on domain | Re-read fresh state and resolve conflict; do not blindly resend |
| 429 rate limiting | Possibly | Honor Retry-After, bound attempts/deadline |
| 502/503/504 | Possibly | Only for retry-safe operations with backoff |
| Timeout/connection reset | Possibly | Do not assume server didn't process; check idempotency |
| Malformed JSON schema | No | Fix contract, mapping, or version |
| No instance found | Possibly after discovery refresh | Avoid tight loops when registry is empty |

### 15.1. Retrying is not the job of onStatus()

onStatus only **classifies responses into exceptions or custom handling**. It does not resend requests. Retrying requires a dedicated mechanism such as Spring Cloud LoadBalancer retry, Spring Retry, Resilience4j, or business-layer orchestration.

Placing retries at multiple layers multiplies actual requests. For example, 3 attempts in the adapter plus 3 attempts in a proxy can send up to 9 calls downstream for one logical request, triggering a retry storm.

### 15.2. Preserving Idempotency-Key across attempts

Example creating a reservation:

~~~java
ReserveResponse reserve(
        String sku, int quantity, String operationId) {

    return client.post()
            .uri("/api/reservations")
            .header("Idempotency-Key", operationId)
            .contentType(MediaType.APPLICATION_JSON)
            .body(new ReserveRequest(sku, quantity))
            .retrieve()
            .body(ReserveResponse.class);
}
~~~

If a retry layer replays the request, **operationId must stay identical** across every attempt of the same logical operation. The backend must store the key alongside a request fingerprint and result to deduplicate; sending the header alone does not guarantee safety.

A domain exception caused by a timeout should not automatically be treated as “transaction failed”. For operations with side effects, you may need a status-lookup API by operationId to reconcile indeterminate outcomes.

## 16. Testing response and exception mapping

**MockRestServiceServer** in spring-test is well suited for testing that RestClient hits the right URL, maps bodies, headers, and exceptions without starting a real server.

### 16.1. Unit test: 200 + JSON to DTO

~~~java
@Test
void mapsJsonResponseToDto() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/BOOK-01"))
            .andRespond(withSuccess(
                    "{\"sku\":\"BOOK-01\",\"available\":7}",
                    MediaType.APPLICATION_JSON));

    StockDto result = client.get()
            .uri("/api/stock/{sku}", "BOOK-01")
            .retrieve()
            .body(StockDto.class);

    assertEquals("BOOK-01", result.sku());
    assertEquals(7, result.available());
    server.verify();
}
~~~

In this test, StockDto is the record declared in section 14. Import JUnit, MockRestServiceServer, requestTo, withSuccess, and the corresponding Spring Test classes. **Do not attach @LoadBalanced in this unit test:** the goal is testing body mapping, not instance selection.

### 16.2. Unit test: default 404 throws exception

~~~java
@Test
void maps404ToHttpClientErrorException() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/UNKNOWN"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":\"STOCK_NOT_FOUND\"}"));

    assertThrows(HttpClientErrorException.NotFound.class, () ->
            client.get()
                    .uri("/api/stock/{sku}", "UNKNOWN")
                    .retrieve()
                    .body(StockDto.class));

    server.verify();
}
~~~

Static imports for the example: requestTo, withStatus, assertThrows. The test confirms **by default retrieve does not return a DTO on 404**, throwing an exception instead.

### 16.3. Unit test: 204 with no body

~~~java
@Test
void handlesNoContentWithoutDto() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");
    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/reservations/123"))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

    ResponseEntity<Void> response = client.delete()
            .uri("/api/reservations/{id}", "123")
            .retrieve()
            .toBodilessEntity();

    assertEquals(HttpStatus.NO_CONTENT, response.getStatusCode());
    assertNull(response.getBody());
    server.verify();
}
~~~

### 16.4. Unit test: onStatus maps 409 to domain exception

~~~java
@Test
void mapsConflictToDomainException() {
    RestClient.Builder builder = RestClient.builder()
            .baseUrl("http://inventory-service");
    MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();
    RestClient client = builder.build();

    server.expect(requestTo(
                    "http://inventory-service/api/stock/BOOK-01"))
            .andRespond(withStatus(HttpStatus.CONFLICT));

    assertThrows(StockConflictException.class, () ->
            client.get()
                    .uri("/api/stock/{sku}", "BOOK-01")
                    .retrieve()
                    .onStatus(
                            s -> s.value() == 409,
                            (req, resp) -> {
                                throw new StockConflictException("BOOK-01");
                            })
                    .body(StockDto.class));

    server.verify();
}
~~~

StockConflictException is an application-defined domain exception. The test verifies mapping logic without requiring a registry deployment.

### 16.5. Unit test: exchange() does not apply status handlers

A necessary test to avoid logic bugs:

~~~java
int status = client.get()
        .uri("/api/stock/{sku}", "MISSING")
        .exchange((request, response) ->
                response.getStatusCode().value());
~~~

If the mock server returns HTTP 404, **status can equal 404 without the default handler throwing an exception**, because exchange() bypasses status handlers. Add a comparative test with retrieve() against the same mock response to verify.

### 16.6. Recommended test matrix

| Mock input | Called API | Expectation |
| --- | --- | --- |
| 200 JSON DTO | body(Class) | Valid StockDto |
| 200 JSON array | body(ParameterizedTypeReference) | List<StockDto> |
| 201 + Location | toBodilessEntity | Retrieves status and Location |
| 204 empty | body(Class) / toBodilessEntity | null or ResponseEntity<Void> |
| 404 | Default retrieve | HttpClientErrorException.NotFound |
| 409 | Custom onStatus | StockConflictException |
| 429 + Retry-After | Custom onStatus | RateLimit exception with Retry-After info |
| 503 | Default retrieve | HttpServerErrorException or RestClientResponseException |
| 200 invalid JSON | body(Class) | Deserialization error |
| 200 unsupported Content-Type | body(Class) | Converter error |
| 404 | exchange() | Callback handles or returns status |
| Read timeout | Real mock HTTP server | ResourceAccessException/transport error |

MockRestServiceServer is not sufficient to verify **real timeouts, TLS, connection pooling, or ServiceInstance selection**. To test I/O and LoadBalancer, use a running stub server (e.g., WireMock/MockWebServer) together with SimpleDiscoveryClient or a test registry, then inspect the rewritten target endpoint.

## 17. Testing in a system with Spring Cloud LoadBalancer

To verify mapping on a request from Order Service to Inventory Service, you can declare two instances using SimpleDiscoveryClient:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

The two stub servers return responses with different instanceId fields:

~~~json
{"sku":"BOOK-01","available":7,"instanceId":"inventory-a"}
~~~

~~~json
{"sku":"BOOK-01","available":4,"instanceId":"inventory-b"}
~~~

Send multiple requests via a RestClient built from **@LoadBalanced RestClient.Builder**, then verify:

1. The URI in code is **http://inventory-service/api/stock/BOOK-01**.
2. LoadBalancer selects one of the two declared instances.
3. The body is deserialized into the DTO as expected.
4. Server-returned 404/503 are handled as real HTTP errors.
5. Stopping one stub server produces a transport error, distinct from a running server returning 503.
6. When no instances remain from the supplier, an error can occur before sending HTTP.
7. Tracing/logs indicate service ID, selected instance, and error category without exposing tokens or sensitive raw bodies.

**Do not confuse three 503 scenarios**:

- The inventory server itself returns HTTP 503.
- An intermediate gateway returns HTTP 503 when unable to reach upstream.
- LoadBalancer finds no instances and the adapter reports a target-selection error, which may surface as a status or exception depending on integration.

They may look identical by status at the controller layer, yet differ in origin, retry policy, and incident troubleshooting.

## 18. Observability, logging, and security when mapping errors

When handling exceptions, try to preserve attributes with operational value:

| Attribute | Purpose | Notes |
| --- | --- | --- |
| serviceId | Identify which logical downstream | inventory-service |
| instanceId | Identify the chosen replica | Not always directly available to the client |
| HTTP method | Separate GET from POST with side effects | Do not log request bodies |
| Path template | Identify the endpoint | Avoid recording sensitive values from real paths |
| Status code | Classify 4xx/5xx | Only present when an HTTP response was received |
| Error category | HTTP, transport, decode, discovery | Useful for alerting |
| Duration/timeout | Track SLOs | Separate total deadline and individual attempts |
| Retry attempt | Detect retry storms | Track actual send counts |
| Trace/correlation ID | Stitch service calls together | Do not treat as security data |

Avoid logging full URLs if queries contain access tokens, emails, or customer data. Avoid logging the full **getResponseBodyAsString()**. For error bodies, record the status, a normalized error code, and at most a safe message snippet.

In Spring Boot, HTTP client observations can use Micrometer Observation. When constructing RestClient.Builder via **new RestClient.builder()** or manual bean setup, verify that observation registries, interceptors, auth, and timeouts are properly wired. Exception mapping should not strip trace IDs or causes.

Do not treat **RestClientResponseException** as retryable by default; inspect **status**, HTTP method, and idempotency.

## 19. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using body(DTO) for every status and checking status later | 4xx/5xx already threw an exception earlier | Use toEntity for successful responses, onStatus/catch for errors |
| Treating 204 as a mandatory JSON DTO | Null or downstream failures | Use toBodilessEntity and explicit contracts |
| Using body(List.class) | Loses generic element type | ParameterizedTypeReference<List<DTO>> |
| Returning Optional.empty for every 404 | Masks routing/registry bugs | Apply only to endpoints whose contract defines 404 = not found |
| Swallowing all 4xx in defaultStatusHandler | Invalid requests continue silently | Narrow, intentional handlers |
| Using exchange() and expecting onStatus to run | 404/503 can slip into success branch | Check status explicitly inside callback |
| Catching RestClientException and retrying everything | Retries validation or JSON schema errors | Separate HTTP/transport/decode before deciding |
| Using onStatus as a retry mechanism | Does not actually retry | Configure retries independently with budgets and idempotency |
| Logging full error bodies | Sensitive data leakage | Redaction, size limits, and structured logging |
| Using non-@LoadBalanced RestClient with service ID | UnknownHost or bypasses LB | Proper bean/builder and dependency |
| Not configuring timeouts | Threads block too long | Set connect/read/pool timeouts on request factory |
| Treating POST timeout as guaranteed failure | Duplicate side effects on retry | Idempotency key and operation status check |

## 20. Practical checklist

- [ ] RestClient is configured with proper HTTP client factory, timeouts, and LoadBalancer when calling by service ID.
- [ ] Each endpoint clearly specifies DTO, generic body, empty response, or ResponseEntity.
- [ ] Never dereference body() before null checking when the contract does not guarantee it.
- [ ] Use ParameterizedTypeReference for generic types.
- [ ] Distinguish 200/201/202/204/206 per contract.
- [ ] Map 404/409/422 per business rules; do not treat all 4xx as retryable.
- [ ] Parse Retry-After in proper format when handling 429/503 with retry policies.
- [ ] Use onStatus at the right level; understand ordering between per-request and global default handlers.
- [ ] With exchange(), check status manually and read responses within lifecycle bounds.
- [ ] Separate HTTP errors, transport errors, decode errors, and discovery errors.
- [ ] Preserve cause, service ID, status, and trace ID when constructing domain exceptions.
- [ ] Bound retries by attempts, backoff, deadline, and idempotency protection.
- [ ] Have unit tests for 2xx/4xx/5xx, empty bodies, invalid JSON, and custom onStatus.
- [ ] Have separate integration tests for @LoadBalanced and real URIs/service instances.
- [ ] Never log credentials, tokens, cookies, or sensitive raw response bodies.

## 21. Conclusion

**Response mapping in RestClient consists of three separate responsibilities:** converting the HTTP body into a Java type; deciding how to interpret HTTP statuses; and translating HTTP/transport/deserialization failures into appropriate exceptions or domain results.

With **retrieve()**, body(Class) and body(ParameterizedTypeReference) return a DTO or null when no body is present; toEntity() retains status/headers; toBodilessEntity() suits responses needing no content. By default, 4xx/5xx generate HTTP exceptions, which can be customized via onStatus() or defaultStatusHandler(). With **exchange()**, the application must manage status and body itself because default handlers are not applied.

In Spring Cloud LoadBalancer, the ServiceInstance list and selection algorithm only decide **where the request is sent**. They do not define the business meaning of 404, 409, 429, 503, timeouts, or malformed JSON. Designing a proper HTTP adapter layer, a clear error taxonomy, and status-matrix tests makes RestClient inter-service communication more reliable, easier to diagnose, and safer to retry.

## 22. References

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, body mapping, ResponseEntity, onStatus, and exchange.
- [RestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestClient.ResponseSpec.html): body, requiredBody (version-specific), toEntity, toBodilessEntity, onStatus, and error defaults.
- [RestClient.RequestHeadersSpec Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html): retrieve, exchange, and working with requests.
- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): RestClient integration, BlockingLoadBalancerClient, instance suppliers, and retries.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestClient.Builder and service discovery.
- [Spring Framework Testing – Client-side REST Tests](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer for testing HTTP clients.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): HTTP status semantics, safe/idempotent methods.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): standard format for returning error details over HTTP APIs.
