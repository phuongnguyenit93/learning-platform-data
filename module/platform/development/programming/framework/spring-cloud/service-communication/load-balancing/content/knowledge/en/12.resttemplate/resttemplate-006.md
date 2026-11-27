# Reading Responses and Mapping HTTP Errors

When using `RestTemplate` to call a service through Spring Cloud LoadBalancer, selecting the right `ServiceInstance` only completes the **routing step**. The calling application must also read the HTTP status, headers, and body, convert JSON payloads into Java types, and distinguish business errors from the target service from network or instance-lookup failures. Lumping every failure into a single generic exception makes it hard for business code to decide whether to return `404`, report a temporarily unavailable dependency, perform a controlled retry, or fix the request.

This lesson belongs to the **RestTemplate** section of the Spring Cloud LoadBalancer module. The goal is to know how to deserialize responses into typed data, understand `RestTemplate`'s default error-reporting behavior, map HTTP errors into business-appropriate exceptions, and observe failures at each inter-service communication layer.

## 1. What Outcomes Can an HTTP Call Produce?

Suppose `order-service` needs to fetch a product from `catalog-service` using a logical URL:

```text
GET http://catalog-service/api/products/42
```

When `RestTemplate` is integrated with `@LoadBalanced`, Spring Cloud LoadBalancer resolves `catalog-service` to a concrete instance before the HTTP client executes the request. Afterward, outcomes fall into several categories:

| Outcome | Example | Layer to inspect |
|---|---|---|
| HTTP success, valid body | `200 OK`, product JSON | Reading `ResponseEntity` and deserialization |
| HTTP success, no body | `204 No Content` | API contract and empty-body handling |
| Request / business HTTP error | `400`, `404`, `409`, `422`, `429` | Status classification and target service error payload |
| Server or gateway HTTP error | `500`, `502`, `503`, `504` | Target service, proxy/gateway, and retry policy |
| No HTTP response received | Connection refused, timeout, TLS/DNS error | HTTP client connection, selected host/port, timeouts |
| No instance selected | Discovery returns no candidates, filters remove all | Registry, `ServiceInstanceListSupplier`, LoadBalancer |
| Response received but body fails to parse | Malformed JSON, mismatched field types, wrong content type | Data contract and HTTP message converters |

**Key point:** having an HTTP status means something on the other end of the connection sent a response. Timeouts or missing instances can happen **before any HTTP response is ever received**; do not turn those cases into a product `404 Not Found`.

## 2. Configuring a Load-Balanced RestTemplate

A plain `RestTemplate` bean sends requests to the hostname in the URL. To treat `catalog-service` as a **service ID**, declare the bean with `@LoadBalanced` and ensure the application has the Spring Cloud LoadBalancer dependency and an appropriate instance source (discovery client or statically configured instance list).

Example synchronous bean with connect and read timeouts:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class CatalogHttpConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate() {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(2_000);
        requestFactory.setReadTimeout(5_000);
        return new RestTemplate(requestFactory);
    }
}
```

Durations in the example are in milliseconds. Connect timeout bounds how long connection establishment takes; read timeout bounds waiting to read data per the specific HTTP request factory. They **do not equate to a single overall deadline** covering discovery, instance selection, retries, and business processing. When using another HTTP client/request factory, check that implementation's timeout semantics and APIs.

If the application has both a plain `RestTemplate` and a load-balanced `RestTemplate`, use `@Qualifier("catalogRestTemplate")` at the injection point to guarantee service-ID requests go through the right bean.

## 3. Reading Responses: `getForObject`, `getForEntity`, and `exchange`

Three common APIs provide different levels of detail:

| API | Returns | When to use |
|---|---|---|
| `getForObject(url, Type.class, ...)` | Object converted from body | Only body needed, default error handling acceptable |
| `getForEntity(url, Type.class, ...)` | `ResponseEntity<Type>` with status, headers, and body | Need response metadata or to detect empty body |
| `exchange(...)` | `ResponseEntity<T>` | Need custom method, headers, request entity, or generic types |

### 3.1. Reading Status, Headers, and Body with `ResponseEntity`

Suppose `catalog-service` returns JSON:

```json
{
  "id": "42",
  "name": "Mechanical Keyboard"
}
```

In Java, declare a DTO:

```java
public record ProductResponse(String id, String name) { }
```

`RestTemplate` uses a suitable `HttpMessageConverter`—typically a JSON converter when Jackson is on the classpath—to convert the body into `ProductResponse`:

```java
ResponseEntity<ProductResponse> response = restTemplate.getForEntity(
        "http://catalog-service/api/products/{id}",
        ProductResponse.class,
        "42");

int status = response.getStatusCode().value();
String requestId = response.getHeaders().getFirst("X-Request-Id");
ProductResponse product = response.getBody();
```

This snippet assumes `restTemplate` is a `@LoadBalanced` bean and the request succeeds or receives a status not treated as an error by the error handler. `ResponseEntity.getBody()` **can return `null`**, such as on `204 No Content`. If the API contract requires a body on `200 OK`, explicitly check for that condition before proceeding with business logic.

A common pitfall: with the default error handler, `getForEntity()` **does not return a `ResponseEntity` for you to check `404` or `500` yourself**; `RestTemplate` normally throws an exception upon receiving those statuses, as explained below.

### 3.2. Using `exchange` When Headers and Generic Types Are Needed

Suppose an endpoint returns a list of products. `List<ProductResponse>.class` does not exist in Java, so use `ParameterizedTypeReference` to preserve generic type information:

```java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

HttpHeaders headers = new HttpHeaders();
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
HttpEntity<Void> requestEntity = new HttpEntity<>(headers);

ResponseEntity<List<ProductResponse>> response = restTemplate.exchange(
        "http://catalog-service/api/products?category={category}",
        HttpMethod.GET,
        requestEntity,
        new ParameterizedTypeReference<List<ProductResponse>>() { },
        "accessories");

List<ProductResponse> products = response.getBody();
```

If the API requires a bearer token or correlation header, place it in the request `HttpHeaders` per your system's authentication and tracing mechanism. Never arbitrarily copy all headers from external inbound requests to internal services.

### 3.3. `2xx` Does Not Guarantee Usable Content

A `200` response with malformed JSON schema can still cause a deserialization failure. A `204` response is HTTP-successful yet cannot be read as a populated `ProductResponse`. Conversely, `404` does not mean the JSON was unreadable: the default error handler detected the status and threw an exception before normal success handling completed.

Therefore, calling code should verify **two independent conditions**: the HTTP status matches the contract, and the body/headers satisfy business preconditions.

## 4. Default Error Behavior of `RestTemplate`

`RestTemplate` uses `DefaultResponseErrorHandler` by default. The error handler flags **4xx** and **5xx** responses as errors and creates exceptions containing status, headers, and potentially the response body.

| Error group | Common exception | Example |
|---|---|---|
| HTTP 4xx | `HttpClientErrorException` and subtypes such as `NotFound` | API returns `404 Not Found` |
| HTTP 5xx | `HttpServerErrorException` and subtypes if applicable | API returns `503 Service Unavailable` |
| Error HTTP status unrecognized by standard enum | `UnknownHttpStatusCodeException` in relevant versions/cases | Non-standard status code |
| No HTTP response due to I/O | `ResourceAccessException` | Connection refused, read timeout |
| Data conversion or other HTTP processing error | Subtypes of `RestClientException` | JSON parse failure, wrong converter |

Exceptions tied to an HTTP response can be caught via the superclass `RestClientResponseException`. It provides APIs such as:

```java
int status = ex.getStatusCode().value();
HttpHeaders responseHeaders = ex.getResponseHeaders();
String errorBody = ex.getResponseBodyAsString();
```

In this snippet, `ex` is a `RestClientResponseException` and assumes Spring Framework 6.x or equivalent APIs. The body may be empty; when logging, truncate length and strip tokens or personal data. Subtype names and handling of unusual status codes can vary by version, but separating **error responses** from **I/O failures without a response** must always remain clear.

`RestTemplate` does not automatically retry every HTTP `500` or `503` simply because they are server errors. If the application configures retries via Spring Cloud LoadBalancer or a custom mechanism, the final observed exception may represent the result after multiple attempts; record every attempt during analysis.

## 5. Mapping Status Codes to Business-Meaningful Errors

Avoid having every controller and service catch `RestClientException` and return the same status. A **gateway/adapter** for `catalog-service` can translate integration failures into exceptions meaningful to the business layer. Common mapping guidelines:

| Response from `catalog-service` | Meaning to verify | Handling in `order-service` |
|---|---|---|
| `400` or `422` | Data sent to catalog is invalid | Check request contract; do not automatically blame the end user |
| `401`, `403` | Missing/invalid token or insufficient permissions | Verify service-to-service credentials; do not blindly retry |
| `404` | Requested resource not found | Map to product-not-found error if defined by the API contract |
| `409` | State conflict | Handle per update/ordering rules; check idempotency |
| `429` | Rate limited | Honor `Retry-After` if present; avoid aggressive retries |
| `500` | Processing failure inside target service | Treat as dependency failure; inspect logs/traces and consider safe retry |
| `502`, `503`, `504` | Gateway or service temporarily failing/overloaded | Treat as dependency failure; check timeouts, retries, and fallback options |

An HTTP `404` returned by `catalog-service` does not automatically equate to a `404` returned by `order-service`'s own API. That depends on domain semantics: for instance, a deleted product might prevent order creation, but the final response code should follow the contract of the user-facing API. Always **preserve the original status in diagnostic metadata** while isolating the mapping decision at the business boundary.

### Example Adapter with Clear Error Handling

The example below uses a `@LoadBalanced` `RestTemplate` injected by bean name. Custom exceptions are declared inline to illustrate the flow; in real projects, place them in an appropriate package.

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

@Component
class CatalogGateway {

    private final RestTemplate restTemplate;

    CatalogGateway(
            @Qualifier("catalogRestTemplate") RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    ProductResponse requireProduct(String id) {
        try {
            ResponseEntity<ProductResponse> response = restTemplate.getForEntity(
                    "http://catalog-service/api/products/{id}",
                    ProductResponse.class,
                    id);

            if (!response.getStatusCode().is2xxSuccessful()
                    || response.getBody() == null) {
                throw new CatalogProtocolException(
                        "Catalog did not return a usable product response");
            }
            return response.getBody();

        } catch (HttpClientErrorException.NotFound ex) {
            // 404 may indicate product not found under the catalog contract.
            throw new ProductNotFoundException(id, ex);

        } catch (RestClientResponseException ex) {
            // HTTP response received with error status: 4xx, 5xx, or special status.
            throw new CatalogHttpException(ex.getStatusCode().value(), ex);

        } catch (ResourceAccessException ex) {
            // I/O error: timeout, connection refused, TLS, or network.
            throw new CatalogTransportException(ex);
        }
    }
}

record ProductResponse(String id, String name) { }

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String id, Throwable cause) {
        super("Product not found: " + id, cause);
    }
}

class CatalogProtocolException extends RuntimeException {
    CatalogProtocolException(String message) {
        super(message);
    }
}

class CatalogHttpException extends RuntimeException {
    private final int status;

    CatalogHttpException(int status, Throwable cause) {
        super("Catalog returned HTTP " + status, cause);
        this.status = status;
    }

    int getStatus() { return status; }
}

class CatalogTransportException extends RuntimeException {
    CatalogTransportException(Throwable cause) {
        super("Cannot reach catalog-service", cause);
    }
}
```

With default configuration, `404` enters the `HttpClientErrorException.NotFound` branch; other HTTP errors are caught by `RestClientResponseException`, and connectivity issues are caught by `ResourceAccessException`. `CatalogProtocolException` covers responses failing expected conditions, such as `204` when the API must return a product.

The example keeps the status code inside `CatalogHttpException` so the business layer can differentiate `409`, `429`, `503`, and other errors. Never forward raw error bodies from internal services verbatim to external callers; bodies may contain technical details or sensitive data unsuitable for disclosure.

**Example limitation:** when discovery has no instances or LoadBalancer fails before an HTTP response exists, the exact exception depends on version and integration. There is no guarantee every instance-selection failure is wrapped in `ResourceAccessException`. Log and handle routing failures separately based on observed application behavior instead of catching `RuntimeException` wholesale and treating it as a timeout.

## 6. When You Need to Read 4xx/5xx Responses Directly

Sometimes an API uses a non-2xx HTTP status as part of its data contract, or an adapter needs to inspect the raw status and error body directly before deciding. With `RestTemplate`, this requires a **custom `ResponseErrorHandler`**, because by default `getForEntity()` and `exchange()` throw exceptions on 4xx/5xx errors.

Example bean for inspecting raw responses:

```java
import java.io.IOException;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.DefaultResponseErrorHandler;
import org.springframework.web.client.RestTemplate;

@Bean
@LoadBalanced
RestTemplate rawStatusRestTemplate() {
    RestTemplate template = new RestTemplate();
    template.setErrorHandler(new DefaultResponseErrorHandler() {
        @Override
        public boolean hasError(ClientHttpResponse response) throws IOException {
            return false;
        }
    });
    return template;
}
```

Using this bean, you can fetch 404/503 responses as `ResponseEntity<String>` to read the status and body yourself:

```java
ResponseEntity<String> response = rawStatusRestTemplate.getForEntity(
        "http://catalog-service/api/products/{id}",
        String.class,
        "unknown");

int status = response.getStatusCode().value();
String rawBody = response.getBody();
```

**Do not replace the error handler across every `RestTemplate` application-wide just for convenience reading errors.** When an error handler stops flagging 4xx/5xx as errors, callers may accidentally treat an error payload as a success payload if they forget to check status. Using a dedicated bean with thorough status/contract checks, or keeping the default and reading the body from `RestClientResponseException`, is usually simpler and safer.

If the error body is JSON, parse it into a separate error DTO rather than the success DTO. Do not deserialize an error body into `ProductResponse` or assume every service uses the same error schema. You can read `ex.getResponseBodyAsString()` and parse according to an agreed error contract, guarding against empty bodies, invalid JSON, or mismatched `Content-Type`.

## 7. Distinguishing HTTP Errors from Network, Discovery, and Conversion Errors

In a request routed through Spring Cloud LoadBalancer, the overall path looks like this:

```mermaid
flowchart TD
    A[order-service business code] --> B[@LoadBalanced RestTemplate]
    B --> C[LoadBalancer selects ServiceInstance]
    C --> D{Valid instance?}
    D -->|No| E[Target selection error / no instance]
    D -->|Yes| F[HTTP client connects host:port]
    F --> G{HTTP response received?}
    G -->|No| H[I/O error: timeout, connection, TLS]
    G -->|Yes| I{HTTP status?}
    I -->|4xx/5xx| J[DefaultResponseErrorHandler throws exception]
    I -->|Success| K[HttpMessageConverter reads body]
    K --> L{Valid body?}
    L -->|Yes| M[ResponseEntity / DTO]
    L -->|No| N[Conversion / data contract error]
```

How to isolate a failing request:

1. **No instance:** compare the service ID in the URL against the registry, client-side discovery list, and `ServiceInstanceListSupplier` filters. Do not blame HTTP responses when no request reached a server.
2. **Instance found but connection failed:** verify host, port, scheme, DNS/TLS, network routing, firewall, and timeouts from the client's runtime environment.
3. **HTTP 4xx:** check request method, path, auth headers, body, and business contract. Retry only when the failure is known to be transient, such as `429` with `Retry-After`.
4. **HTTP 5xx:** collect trace/request ID, response status, duration, and target instance logs. Do not assume LoadBalancer automatically evicts instances returning 500.
5. **Success status but parsing failed:** inspect `Content-Type`, DTO fields, Jackson/message converter config, encoding, and required properties.

A `400` returned by `catalog-service` is **not equivalent** to a connection error. Conversely, connection refused normally has no HTTP status to map. Separating these groups ensures retries, fallbacks, and error messages serve their exact intended purpose.

## 8. Timeouts, Retries, and Their Impact on Error Interpretation

**Timeouts** prevent a request from waiting indefinitely; **retries** are a decision to try again. They operate in a different scope from instance selection:

| Mechanism | Purpose | Note |
|---|---|---|
| Connect timeout | Bounds connection establishment time | Does not cover discovery or body processing time |
| Read timeout | Bounds waiting to read data per HTTP client | Does not guarantee total request time equals the timeout |
| Spring Cloud LoadBalancer | Picks an instance via service ID and supplier chain | Does not fix error responses or guarantee success |
| Retry policy | Decides whether, when, and how many times to retry | May issue multiple calls across one or more instances |
| Circuit breaker/fallback (if used) | Limits blast radius of failing dependencies or returns fallback data | Must be configured; not a built-in feature of `RestTemplate` |

Never retry all HTTP 4xx errors. In particular, `400`, `401`, `403`, and `404` rarely succeed when replaying the exact same request. For `429`, respect rate limits and `Retry-After`. For `502`, `503`, `504`, or transient network errors, retries can help, provided attempt count, backoff, and total duration are bounded.

For order-creating `POST` or other state-mutating operations, **the server may have processed the request successfully while the response was lost**. Retrying without an idempotency key or deduplication mechanism can cause duplicate side effects. Therefore, retry decisions must follow the business contract, not merely the exception class.

If retries are enabled, logs at the outermost call site may reflect only the final attempt's error. When investigating, examine attempt count, the instance chosen on each attempt, error type, and per-attempt duration. Avoid analyzing the final exception as if only a single HTTP request happened.

## 9. Observing and Mapping Errors at the API Boundary

When `order-service` calls `catalog-service`, record enough diagnostic context to tie an HTTP failure back to a specific instance:

- Logical `serviceId` (`catalog-service`), HTTP method, and route template, avoiding raw URLs containing sensitive data.
- Instance ID/host:port chosen by LoadBalancer if selection instrumentation is configured.
- Trace ID, attempt count, duration, HTTP status if present, and exception class if no response arrived.
- Business mapping outcome, such as `PRODUCT_NOT_FOUND` or `DEPENDENCY_UNAVAILABLE`.

Never dump full request/response bodies, tokens, cookies, or user identifiers indiscriminately into logs. When logging an error body for debugging, bound length and redact sensitive fields; `ex.getResponseBodyAsString()` may contain unexpected content returned by the target service.

Example layered mapping:

| Error detected in CatalogGateway | Meaning to `order-service` | Illustrative API response direction |
|---|---|---|
| `ProductNotFoundException` | Input product does not exist | Contract-dependent: `404` or validation message |
| `CatalogHttpException` status `409` | Catalog rejected action due to state | Resolve business conflict before deciding external status |
| `CatalogHttpException` status `429` | Catalog rate-limited the caller | Backoff/rate limit; consider `503` or contract-defined response |
| `CatalogHttpException` status `5xx` | Dependency returned error | Architecture-dependent: `502`/`503` with controlled message |
| `CatalogTransportException` | No HTTP response received | Treat as transient dependency failure; inspect connectivity/timeouts |
| `CatalogProtocolException` | Response violated contract | Investigate API/DTO version mismatch; do not treat as missing product |

This table is only an application-policy example. **There is no universal mapping from downstream HTTP status codes to external API status codes.** A gateway may pass through original statuses in specific contexts, whereas a domain service should decide based on its own contract with its callers.

## 10. Hands-On: Testing Response Scenarios

To observe these behaviors clearly, create test endpoints on `catalog-service` or use a mock HTTP server returning responses for the scenarios below. `order-service` calls through a `@LoadBalanced` `RestTemplate` bean and records exceptions, statuses, bodies, and selected instances.

| Scenario | Simulated response or fault | Expected outcome |
|---|---|---|
| A | `200`, valid DTO JSON | `ResponseEntity` returns status, headers, and `ProductResponse` |
| B | `204`, empty body | No body; adapter handles per contract |
| C | `404`, JSON error payload | `HttpClientErrorException.NotFound` with default handler; mapped to `ProductNotFoundException` if appropriate |
| D | `409` or `429` | HTTP exception carrying status for business layer decision |
| E | `503`, JSON error | Server HTTP exception, preserving status and trace for investigation |
| F | Port closed or network dropped on instance | I/O/transport exception, typically with no HTTP status |
| G | `200`, JSON with mismatched field types | Data conversion error; inspect API schema |
| H | No instances for service ID | LoadBalancer/discovery error; check config and candidate list |

Also try returning a `404` from an HTTP mock with an error body and `X-Request-Id` header, then catch `RestClientResponseException` to verify the application can read status, headers, and error body. Test a connect/read timeout to confirm **no status code exists** for that category. When testing across multiple instances, track which request hit which instance to separate routing errors from target application response errors.

A short diagnostic checklist for every call: **service ID → candidate list → selected instance → connection → HTTP status → body/converter → business mapping**. Recording these steps in order prevents confusing a missing product with an unavailable service.

## 11. Key Takeaways

`RestTemplate` can return `ResponseEntity` to read status, headers, and body whenever the response is not flagged as an error by the error handler. By default, HTTP 4xx/5xx responses are converted into exceptions holding response details, whereas timeouts and connection failures belong to I/O exceptions without an HTTP status. In Spring Cloud LoadBalancer, discovery or instance-selection errors form yet another layer occurring before HTTP transmission. Clearly map **resource/business errors**, **dependency HTTP errors**, **transport errors**, and **data contract errors**; configure timeouts, retries, and observability properly so service calls stay resilient and easy to diagnose.
