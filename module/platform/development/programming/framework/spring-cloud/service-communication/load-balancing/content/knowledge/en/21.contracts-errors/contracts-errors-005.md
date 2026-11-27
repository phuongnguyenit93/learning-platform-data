# Handling Empty Responses, Wrong Data Types, and Mismatched Content Types

In a microservices system using **Spring Cloud LoadBalancer**, a client can pick a valid `ServiceInstance` of `catalog-service`, open a connection cleanly, receive HTTP 200, and still **fail to read business data**. The root cause usually lies in the **HTTP/JSON contract**: the response has no body, a field has the wrong data type, the JSON is malformed, or the `Content-Type` is incompatible with what the client expects to decode.

This is a core topic in the **Contracts and Errors** chapter: distinguishing **instance selection**, **HTTP transport**, **HTTP status**, **message conversion**, and **semantic validation** errors. If you lump all of them into a generic "service call error" and retry, the application can keep hitting a replica with an incompatible schema, masking deployment bugs or amplifying load.

This lesson uses `RestClient`, `WebClient`, and Spring Cloud OpenFeign for illustration; the examples assume compatible Spring Boot/Spring Cloud versions, a discovery source for service ID `catalog-service`, and a JSON codec (typically via Jackson).

## 1. LoadBalancer Picks the Instance, Not the Response Contract

A logical request:

~~~http
GET http://catalog-service/products/7
Accept: application/json
~~~

May follow this flow:

~~~mermaid
flowchart TD
    A["Application calls catalog-service"]
    B["Spring Cloud LoadBalancer<br/>selects ServiceInstance"]
    C["HTTP transport to host:port"]
    D{"HTTP response received?"}
    E["Network/timeout error"]
    F["Check status, headers"]
    G{"Body and Content-Type<br/>satisfy contract?"}
    H["Decode JSON to ProductDto"]
    I["Validate business data"]
    J["Return valid ProductDto"]
    K["Contract / decoding / validation error"]
    A --> B --> C --> D
    D -->|"No"| E
    D -->|"Yes"| F --> G
    G -->|"No"| K
    G -->|"Yes"| H --> I
    I -->|"Valid"| J
    I -->|"Invalid"| K
~~~

| Layer | Error examples | How to handle |
|---|---|---|
| Discovery/LoadBalancer | No replicas for `catalog-service` | Check service ID, registry, supplier, health/zone filters |
| Network/HTTP transport | `Connection refused`, connect/read timeout | Check instance URI, network, timeouts, conditional retries |
| HTTP status | `404`, `409`, `429`, `503` | Map according to business contract and error response |
| Body decoding | Corrupt JSON, incompatible data type | Check schema, decoder, and content type |
| Semantic validation | JSON decodes, but `id` missing or `name` blank | Check constraints and contract version |

**HTTP 200 only confirms the request received an HTTP-level success response; it does not prove the body satisfies the application contract.** LoadBalancer has no idea that `ProductDto.id` must be a number or that `Content-Type` must be JSON.

## 2. Distinguishing 204, Empty 200, JSON null, Empty Object, and Empty List

A client expects `ProductDto` with two required fields:

~~~java
public record ProductDto(Long id, String name) {}
~~~

The following responses are **not equivalent**:

| Response | HTTP/payload meaning | If the client expects `ProductDto` |
|---|---|---|
| `204 No Content`, no body | Succeeded and intentionally has no representation | Never fabricate `ProductDto`; can use `ResponseEntity<Void>` |
| `200 OK`, 0-byte body | Succeeded, yet body is empty | Under a contract requiring an object: **contract violation** |
| `200` + body `null` with `application/json` | A valid JSON `null` literal | Java object may decode to `null` or emit no reactive element |
| `200` + body `{}` | Empty JSON object | Can decode to a DTO with `null` fields if unvalidated |
| `200` + body `[]` | Empty JSON array | Valid for `List<ProductDto>` if contract specifies a list |
| `200` + body `{"id":7,"name":"Tea"}` | JSON object with all fields | Can decode into `ProductDto` |
| `200` + body `{"id":"oops","name":"Tea"}` | `id` value does not match expected type | Typically fails deserialization targeting `Long` |
| `200` + truncated JSON | Payload is not complete JSON | Parse/decoding error, not a missing instance |
| `404 Not Found` | Resource does not exist per contract | Handle 404 explicitly; do not infer 204/empty 200 |

Further distinctions:

- **Missing or `null` fields:** some decoders still construct a Java object with `null` fields. Validate required fields at the contract/validation layer.
- **Empty string `""`:** not equal to `null` and not equal to an empty object. If product name cannot be blank, enforce a separate constraint.
- **Array `[]`:** valid when an API returns a zero-element list; **invalid** if the API is declared to return a single object.
- **`204`:** fits operations with no response payload, such as certain `DELETE` calls, when defined by the contract. Do not turn every lookup miss into `204` for convenience.

### Consistent Design Rules

Example API with two endpoints:

~~~text
GET /products/7         -> 200 + ProductDto, or 404 if absent
GET /products?category=x -> 200 + [] if list is empty
DELETE /products/7      -> 204 if deleted successfully without body
~~~

This is **one consistent contract proposal**, not a universal rule for every API. What matters is that client and server **agree upfront** and version any changes.

## 3. Content-Type, Accept, and Content-Encoding Are Three Separate Concepts

Example:

~~~http
GET /products/7
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip

<compressed JSON bytes>
~~~

- **`Accept`:** request header telling the server which representation types the client prefers; a server/proxy may not honor it.
- **`Content-Type`:** response header describing **what data format is being returned**, used by HTTP message converters/codecs to choose a decoder.
- **`Content-Encoding`:** states how the representation was encoded/compressed (e.g., `gzip`); does not replace `Content-Type`.

If a client sends `Accept: application/json` yet the server returns:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<html><body>Proxy maintenance page</body></html>
~~~

then **a successful HTTP status does not turn an HTML body into a `ProductDto`**. The decoding layer should treat this as a contract error for a call expecting JSON. Never silently parse HTML, ignore `Content-Type`, or return a fake DTO to "rescue" the request.

### JSON Media Types and Vendor Types

`application/json` is standard; an API might use `application/vnd.example.product+json`. The `+json` suffix indicates a JSON-based representation, yet **still requires contract agreement** to ensure decoder, schema, and version alignment.

`application/problem+json` is commonly used for structured error payloads such as Problem Details; it must not be decoded into `ProductDto` on a success path by default. On 4xx/5xx responses, handle the status/error contract before trying to decode a business DTO.

## 4. Building a Mock Server to Reproduce Contract Errors

Run a **lab-only** controller on `8081` returning different responses by scenario name:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ContractLabController {

    @GetMapping("/lab/products/{scenario}")
    ResponseEntity<?> product(
            @PathVariable String scenario) {

        return switch (scenario) {
            case "valid" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":7,"name":"Tea"}
                          """);

            case "empty-204" ->
                    ResponseEntity.noContent().build();

            case "empty-200" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("");

            case "json-null" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("null");

            case "object-empty" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{}");

            case "field-null" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":null,"name":""}
                          """);

            case "wrong-type" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                          {"id":"oops","name":"Tea"}
                          """);

            case "malformed" -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"id\":7,\"name\":");

            case "json-as-text" -> ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("""
                          {"id":7,"name":"Tea"}
                          """);

            case "html" -> ResponseEntity.ok()
                    .contentType(MediaType.TEXT_HTML)
                    .body("<html><body>Maintenance</body></html>");

            default -> ResponseEntity.notFound().build();
        };
    }
}
~~~

**Note:** here JSON bodies are written as `String`s with forced `Content-Type`s specifically to reproduce malformed cases. In production controllers, normally return DTOs so the framework selects the JSON converter; avoid hand-building JSON via string concatenation.

Test matrix:

| Path | Status | Content-Type | Body |
|---|---:|---|---|
| `/lab/products/valid` | 200 | `application/json` | Valid object |
| `/lab/products/empty-204` | 204 | May be absent | No body |
| `/lab/products/empty-200` | 200 | `application/json` | 0 bytes |
| `/lab/products/json-null` | 200 | `application/json` | `null` |
| `/lab/products/object-empty` | 200 | `application/json` | `{}` |
| `/lab/products/field-null` | 200 | `application/json` | `null`/blank fields |
| `/lab/products/wrong-type` | 200 | `application/json` | Incompatible field type |
| `/lab/products/malformed` | 200 | `application/json` | Truncated JSON |
| `/lab/products/json-as-text` | 200 | `text/plain` | Content looks like JSON |
| `/lab/products/html` | 200 | `text/html` | HTML |

If a proxy/CDN/API gateway sits in front, verify the actual response reaching the client because proxies can rewrite headers, status codes, and bodies.

## 5. Configuring RestClient Through Spring Cloud LoadBalancer

A client using `@LoadBalanced RestClient.Builder` accepts a service-ID URL so Spring Cloud selects an instance:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

In the lab, `SimpleDiscoveryClient` can be used:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

The application requires `spring-cloud-starter-loadbalancer` and compatible HTTP/JSON dependencies. `RestClient` was introduced in Spring Framework 6.1, so this code cannot be applied verbatim on Framework 6.0 apps. When relying on Boot auto-customizers (tracing, codecs, observability), consider `RestClientBuilderConfigurer` rather than creating raw builders blindly.

### Typed Calls and Result Validation

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogRestGateway {

    private final RestClient client;

    CatalogRestGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    ProductDto fetchProduct(String scenario) {
        ResponseEntity<ProductDto> response = client.get()
                .uri("/lab/products/{scenario}", scenario)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(ProductDto.class);

        if (response.getStatusCode().value() == 204) {
            throw new DownstreamContractException(
                    "Expected product body but received 204");
        }

        ProductDto body = response.getBody();

        if (body == null || body.id() == null
                || body.name() == null
                || body.name().isBlank()) {
            throw new DownstreamContractException(
                    "Product response is missing required fields");
        }

        return body;
    }
}

record ProductDto(Long id, String name) {}

class DownstreamContractException extends RuntimeException {
    DownstreamContractException(String message) {
        super(message);
    }

    DownstreamContractException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Key takeaways:

1. `retrieve().toEntity(ProductDto.class)` exposes **status, headers, and body**, not just the body.
2. `204` is explicitly rejected per a contract requiring a product, instead of treating `null` as success.
3. `200` with a 0-byte body or JSON `null` can yield `body == null`. The client rejects missing data.
4. `{}` or `{"id":null,"name":""}` can decode into a DTO yet are rejected by required-field checks.
5. `wrong-type` or `malformed` raises an exception **right during decoding**, before field checks execute.

**Limitation:** because `toEntity(ProductDto.class)` decodes the body before returning `ResponseEntity`, it can throw content-type/JSON errors before your own header checks run. If your contract requires inspecting `Content-Type` **prior to deserialization**, use an API that reads the raw response in a controlled way.

## 6. Strict Contract: Check Status, Content-Type, and Body Before Parsing

For an API where **success strictly requires `200 application/json` and a complete object**, inspect the raw response inside `RestClient.exchange(...)`.

The example below uses `ObjectMapper`, enforces a **64 KiB lab response size limit**, and runs required validation:

~~~java
import java.io.IOException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

class StrictCatalogGateway {

    private static final int MAX_BYTES = 64 * 1024;

    private final RestClient client;
    private final ObjectMapper mapper;

    StrictCatalogGateway(RestClient client, ObjectMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    ProductDto fetch(long productId) {
        return client.get()
                .uri("/products/{id}", productId)
                .accept(MediaType.APPLICATION_JSON)
                .exchange((request, response) -> {
                    int status = response.getStatusCode().value();

                    if (status == 204) {
                        throw new DownstreamContractException(
                                "Product endpoint unexpectedly returned 204");
                    }

                    if (status != 200) {
                        throw new DownstreamContractException(
                                "Unexpected status: " + status);
                    }

                    MediaType mediaType =
                            response.getHeaders().getContentType();

                    if (mediaType == null
                            || !MediaType.APPLICATION_JSON
                                    .isCompatibleWith(mediaType)) {
                        throw new DownstreamContractException(
                                "Expected application/json, got: "
                                + mediaType);
                    }

                    byte[] bytes = response.getBody()
                            .readNBytes(MAX_BYTES + 1);

                    if (bytes.length == 0) {
                        throw new DownstreamContractException(
                                "HTTP 200 with an empty body");
                    }

                    if (bytes.length > MAX_BYTES) {
                        throw new DownstreamContractException(
                                "Response exceeds lab size limit");
                    }

                    ProductDto body;
                    try {
                        body = mapper.readValue(
                                bytes, ProductDto.class);
                    } catch (JsonProcessingException ex) {
                        throw new DownstreamContractException(
                                "Malformed or incompatible ProductDto JSON",
                                ex);
                    }

                    if (body == null || body.id() == null
                            || body.name() == null
                            || body.name().isBlank()) {
                        throw new DownstreamContractException(
                                "ProductDto violates required fields");
                    }

                    return body;
                });
    }
}
~~~

This is a **strict pattern for a specific contract**, not a blanket replacement for Spring's message converters:

- `exchange(...)` hands control of status, headers, and response body directly to your callback. **Status handlers registered via `retrieve().onStatus(...)` do not apply automatically to `exchange(...)`**; handle statuses explicitly here.
- `readNBytes(MAX_BYTES + 1)` sets a lab read cap. If the response exceeds the cap, the callback throws and the response closes per the `exchange` lifecycle; in production, consider streaming, quotas, timeouts, and concrete payload constraints.
- The check here **accepts only `application/json`-compatible types**. If the official API supports vendor `+json`, expand the allowlist intentionally.
- `ObjectMapper` should be an application-managed bean with proper JSON settings; never instantiate a new mapper per request.

Never inspect `Content-Type` via exact string equality like `"application/json;charset=UTF-8"`; Spring's `MediaType` understands charset parameters and media types properly.

## 7. RestClient: Classify Exceptions Before Deciding to Retry

Common failure branches:

| Situation | Possible error types | Characteristics |
|---|---|---|
| HTTP 404/409/429/503 | `RestClientResponseException` or matching subclass | Received error HTTP status under default `retrieve()` |
| `200 text/html` → `ProductDto` | `UnknownContentTypeException` or converter failure | No converter supports target type + media type |
| `200` syntactically invalid JSON | `RestClientException` with JSON/Jackson cause | HTTP succeeded, body failed parsing |
| `200` incompatible field type | `RestClientException` with binding/deserialization cause | Inspect field and schema contract |
| `200` object missing fields | May decode cleanly | Must validate at the contract layer |
| HTTP 204 / 200 empty body | Body may be `null` | Decide whether body is optional or required |
| No instance / connect timeout | LoadBalancer or transport error | Not equivalent to a JSON error |

Exact exception class names depend on Spring Framework, Jackson, the request factory, and whether `retrieve` or `exchange` is used. Diagnostics should record the **entire cause chain** and relevant headers rather than hardcoding logic around a single exception class.

### Do Not "Fix" Malformed Responses with Unconditional Retries

Suppose an instance returns `{"id":"oops"}`. Retrying the same instance almost certainly repeats the error. Retrying onto another instance may "get lucky" if deployments are out of sync, yet that is a **symptom of contract drift** to fix at the backend/version level, not a trustworthy long-term recovery policy.

## 8. WebClient: How Empty Responses Produce Mono.empty()

`WebClient` typically uses `retrieve().bodyToMono(ProductDto.class)`. For a successful response **with no body value to decode**, the publisher can complete **without emitting an element**. A `Mono.empty()` is not `Mono.just(null)`; Reactive Streams forbid `null` elements.

Example client created from `@LoadBalanced WebClient.Builder`:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogGateway {

    private final WebClient client;

    ReactiveCatalogGateway(WebClient client) {
        this.client = client;
    }

    Mono<ProductDto> fetch(String scenario) {
        return client.get()
                .uri("/lab/products/{scenario}", scenario)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductDto.class)
                .switchIfEmpty(Mono.error(
                        new DownstreamContractException(
                                "Expected ProductDto, received empty body")))
                .map(body -> {
                    if (body.id() == null
                            || body.name() == null
                            || body.name().isBlank()) {
                        throw new DownstreamContractException(
                                "Invalid ProductDto fields");
                    }
                    return body;
                });
    }
}
~~~

This handles **204**, **200 with a 0-byte body**, or a JSON `null` response when the decoder completes empty. However, `switchIfEmpty` **does not tell you the response status**. To distinguish an allowed 204 from a contract-violating empty 200, inspect status and body at the `ClientResponse` level.

### WebClient.exchangeToMono to Separate Status and Media Type

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<ProductDto> strictFetch(
        WebClient client, long productId) {

    return client.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                HttpStatusCode status = response.statusCode();

                if (status.value() == 204) {
                    return response.releaseBody()
                            .then(Mono.error(
                                    new DownstreamContractException(
                                            "204 is invalid for product")));
                }

                if (!status.is2xxSuccessful()) {
                    return response.createException()
                            .flatMap(Mono::error);
                }

                MediaType type = response.headers()
                        .contentType().orElse(null);

                if (type == null ||
                        !MediaType.APPLICATION_JSON.isCompatibleWith(type)) {
                    return response.releaseBody()
                            .then(Mono.error(
                                    new DownstreamContractException(
                                            "Unexpected content type: "
                                            + type)));
                }

                return response.bodyToMono(ProductDto.class)
                        .switchIfEmpty(Mono.error(
                                new DownstreamContractException(
                                        "Empty product payload")))
                        .map(dto -> {
                            if (dto.id() == null || dto.name() == null
                                    || dto.name().isBlank()) {
                                throw new DownstreamContractException(
                                        "Invalid product data");
                            }
                            return dto;
                        });
            });
}
~~~

With `exchangeToMono`, Spring manages releasing any leftover body once the returned publisher completes. On branches that skip reading the body, calling `releaseBody()` explicitly signals intent to free resources before failing. Never use the legacy `exchange()` method and ignore the body without managing the connection lifecycle.

**Crucial distinction:** `WebClient` decode failures surface as `DecodingException` or codec errors, whereas HTTP 4xx/5xx responses typically emit `WebClientResponseException` under `retrieve()`. Never conflate these two groups.

## 9. OpenFeign: Decoder, Return Type, and Data Errors

Spring Cloud OpenFeign typically uses `ResponseEntityDecoder` wrapping `SpringDecoder`, backed by Spring's HTTP message converters. When LoadBalancer is on the classpath and no fixed URL is configured, `FeignBlockingLoadBalancerClient` selects an instance before Feign's decoder processes the response.

Example:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping(
            value = "/products/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ProductDto> product(@PathVariable("id") long id);
}
~~~

Here:

- `ResponseEntity<ProductDto>` lets callers inspect status and body after Feign/`SpringDecoder` processing.
- `@GetMapping(produces = ...)` states the expected media type in the Feign/Spring MVC contract; it **does not guarantee the server/proxy actually sends that `Content-Type`**.
- The body can still be `null` on no-content responses. Callers must check explicitly when the endpoint requires an object.
- Error status responses go through **Feign error handling**, such as `FeignException` or a custom `ErrorDecoder`.
- 2xx responses with corrupt/wrong-type JSON raise decoder failures (typically `DecodeException` or Jackson/converter causes). Never treat these as 503 or discovery errors.

### Post-Call Validation

~~~java
ResponseEntity<ProductDto> response = catalogFeignClient.product(7L);

if (response.getStatusCode().value() == 204) {
    throw new DownstreamContractException(
            "Product endpoint returned 204");
}

ProductDto body = response.getBody();

if (body == null || body.id() == null
        || body.name() == null
        || body.name().isBlank()) {
    throw new DownstreamContractException(
            "Product response violates contract");
}
~~~

This check executes **only if Feign decoding succeeded**. With an incompatible `Content-Type` or syntactically invalid JSON, an exception is thrown before `product(...)` returns.

### Never Install a Global Decoder Just to Hide Errors

You can write a custom Feign `Decoder` to check status/content type or handle special formats. However, installing a decoder globally that "guesses JSON even when headers say HTML/text" across all clients risks:

- Masking proxy error pages or backend version mismatches.
- Turning malformed JSON into default DTOs, corrupting business data.
- Bypassing per-endpoint no-content/404 handling.
- Conflicting with `ResponseEntityDecoder` or per-client configurations.

If a custom decoder is truly needed, scope it to a **named client/contextId**, test all status/media-type combinations, and maintain an explicit contract for that API.

## 10. When Do You Need @Valid or Bean Validation?

Jackson/message converters primarily handle **converting bytes into objects**. Successfully deserializing a JSON object **does not guarantee the data satisfies business constraints**.

You can declare the DTO as:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProductDto(
        @NotNull Long id,
        @NotBlank String name
) {}
~~~

If your application has a Jakarta Bean Validation provider, **invoke validation explicitly** on DTOs decoded from downstream:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;

class ProductContractValidator {

    private final Validator validator;

    ProductContractValidator(Validator validator) {
        this.validator = validator;
    }

    ProductDto requireValid(ProductDto product) {
        if (product == null) {
            throw new DownstreamContractException(
                    "Product is required");
        }

        Set<ConstraintViolation<ProductDto>> errors =
                validator.validate(product);

        if (!errors.isEmpty()) {
            throw new DownstreamContractException(
                    "Downstream product violates Bean Validation");
        }

        return product;
    }
}
~~~

**Do not assume `@NotNull` and `@NotBlank` execute automatically just because RestClient/WebClient/Feign decodes the DTO.** Constraints may run automatically at entry points annotated with `@Valid`/method validation, but client code reading responses needs explicit validation or a tested contract adapter layer.

For instance, `{"id":null,"name":""}` can decode into `ProductDto(null, "")`, and only afterward does `Validator` reject it. If `id` is a non-numeric string, failure occurs during **deserialization**, before validation runs.

## 11. Distinguishing Contract Errors from Valid Empty Business Results

For an endpoint returning a list of products, `[]` is a valid empty result:

~~~java
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;

List<ProductDto> products = catalogRestClient.get()
        .uri("/products?category=unknown")
        .retrieve()
        .body(new ParameterizedTypeReference<List<ProductDto>>() {});
~~~

However, if the response actually has an empty body, the call may return `null` instead of `List.of()`. **Do not silently turn every `null` into an empty list** if you want to catch upstream contract violations.

A clear API convention typically looks like:

| Endpoint | Success response by design | When no data exists |
|---|---|---|
| `GET /products/{id}` | `200 + ProductDto` | `404` per contract |
| `GET /products?category=x` | `200 + List<ProductDto>` | `200 + []` |
| `DELETE /products/{id}` | `204` | No body by design |
| Async `POST /jobs` | `202 + Location/status contract` | Does not require the same DTO as GET |

Applications should define upfront how **optional fields**, **optional resources**, **empty collections**, and **no-content statuses** differ. That is a contract boundary, not something LoadBalancer decides.

## 12. Content Negotiation Cannot Fix Wrong Backend Types

Example:

~~~java
ProductDto product = catalogRestClient.get()
        .uri("/products/7")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ProductDto.class);
~~~

`Accept: application/json` asks the server for JSON, yet these scenarios can still occur:

1. An older replica returns `id` as a string while a newer replica returns a number.
2. An API gateway/WAF returns a login/maintenance HTML page while keeping status 200.
3. Backend returns a JSON body with a `text/plain` header.
4. Response `Content-Type` is `application/problem+json` despite a 2xx status due to a bug.
5. A proxy truncates the response mid-stream, leaving incomplete JSON.
6. Backend sends a mismatched charset/encoding or broken gzip stream.

Choose remediation based on root cause:

| Root cause | Preferred fix |
|---|---|
| Backend sets wrong `Content-Type` | Fix server/proxy and add contract tests |
| Incompatible schema change | Version the API, deploy backward-compatibly, or coordinate rollout |
| HTML returned from proxy/login redirect | Fix routing/auth/proxy; never try decoding HTML into DTOs |
| Missing required fields | Add validation; fix source data or contract |
| Truncated JSON due to network/transport | Inspect transfer encoding, timeouts, proxy, and body truncation |
| System intentionally supports vendor `+json` | Configure decoder/media-type allowlist per API, not ad hoc |

You can read `String` to **diagnose** a `text/plain` body, provided you bound size and protect sensitive data. Never make "read as String then parse with Jackson" your default production path solely to bypass `Content-Type` errors.

## 13. Retries and LoadBalancer: Data Errors Do Not Heal When Switching Instances

Spring Cloud LoadBalancer and HTTP clients support retries in appropriate situations, yet **response contract errors** are rarely transient errors suitable for unconditional retry.

A version-skew deployment scenario:

~~~text
catalog-service:
  catalog-1 (v1) -> {"id":"7","name":"Tea"}
  catalog-2 (v2) -> {"id":7,"name":"Tea"}

order-service (new client) -> expects Long id
~~~

With a lenient JSON mapper allowing coercion, `"7"` may convert silently into `Long 7`, hiding the mismatch. Tests should therefore use truly incompatible values like `"oops"` or enable strict coercion checks when required by the contract. Never conclude schemas are fully compatible just because one sample parsed.

If `catalog-1` produces a decode failure:

- Retrying the same instance simply repeats the failure.
- Retrying onto `catalog-2` may succeed and **mask a broken rollout**, making the bug intermittent.
- There is no guarantee a codec exception is automatically treated as retryable by a load-balancer retry policy.
- Blindly retrying every exception triggers request storms and obscures root causes.

**Right approach:** detect per-instance/version discrepancies, fix the contract or roll back/canary, enforce contract tests, and separate server bugs from transport failures.

### When Are Retries Reasonable?

Retries help on transient network failures or certain HTTP 502/503/504 responses per policy, when the operation is safe to repeat and the request body can be replayed. **Do not enable retries on JSON decode failures or wrong `Content-Type` just to "try another replica"** without a clear cause and control mechanism.

For side-effecting POST/PUT operations, verify both idempotency and overall deadlines.

## 14. Observability and Error Classification to Prevent Misdiagnosis

Record the following dimensions via interceptors or observations when configured:

| Field | Meaning |
|---|---|
| `serviceId` | Logical service name in LoadBalancer |
| `instanceId` / host:port | Actual instance selected |
| `httpStatus` | Whether an HTTP response arrived and its status |
| `responseContentType` | Actual media type on the response |
| `expectedType` | DTO or schema the client tried to decode |
| `bodyLength` (bounded and privacy-safe) | Distinguish 0 bytes from JSON `null`/`{}` |
| `errorCategory` | NO_INSTANCE, NETWORK, HTTP_STATUS, MEDIA_TYPE, DECODE, VALIDATION |
| `contractVersion` | Client/server version if supplied |
| `traceId` / `requestId` | Correlate with backend/gateway logs |
| `attempt` | Distinguish initial attempt from retries |

Recommended log example:

~~~text
traceId=demo-42 serviceId=catalog-service instanceId=catalog-2
httpStatus=200 responseContentType=text/html expectedType=ProductDto
errorCategory=MEDIA_TYPE bodyLength=37 attempt=1
~~~

These are **not default fields** auto-generated by Spring Cloud. Extract them from your HTTP client, response handlers, and tracing while bounding cardinality so full URLs with arbitrary IDs never become metric tags.

**Never log full production bodies** when they may contain tokens, customer data, cookies, or sensitive documents. When investigating, record content type, length, a hash, or a redacted/bounded snippet per security policy.

### Diagnostic Decision Flow

~~~mermaid
flowchart TD
    A["Downstream call failed"]
    B{"ServiceInstance selected?"}
    C["Check discovery / LoadBalancer"]
    D{"HTTP response received?"}
    E["Check network / timeouts"]
    F{"Status is 2xx?"}
    G["Map status / error contract"]
    H{"Body required?"}
    I["204/200 empty per contract"]
    J{"Content-Type matches?"}
    K["Media type mismatch"]
    L{"Decode succeeded?"}
    M["JSON / schema mismatch"]
    N{"Validation passed?"}
    O["Missing/semantically invalid data"]
    P["Success"]
    A --> B
    B -->|"No"| C
    B -->|"Yes"| D
    D -->|"No"| E
    D -->|"Yes"| F
    F -->|"No"| G
    F -->|"Yes"| H
    H -->|"No / empty"| I
    H -->|"Has payload"| J
    J -->|"No"| K
    J -->|"Yes"| L
    L -->|"No"| M
    L -->|"Yes"| N
    N -->|"No"| O
    N -->|"Yes"| P
~~~

This diagram is illustrative: determining "instance selected" and "response received" requires instrumentation, not guessing from a single exception.

## 15. Hands-On Lab and Test Matrix

### Part A — RestClient and Mock Server

1. Start the controller from Section 4 on port `8081`.
2. Configure `catalog-service` in `SimpleDiscoveryClient` and `@LoadBalanced RestClient.Builder`.
3. Call every endpoint in the table below, first using `retrieve().toEntity(ProductDto.class)`.
4. Record status, `Content-Type`, presence of body, exception type, and cause.
5. Use the strict gateway from Section 6 to catch errors **before deserialization**; compare with regular decoding.
6. For `object-empty` and `field-null`, confirm that **decoding cleanly does not mean valid**.
7. Try switching the target type to `String.class` to inspect text bodies; **never treat readability as String as proof the API matches its contract**.

### Part B — WebClient

1. Build a `WebClient` from `@LoadBalanced WebClient.Builder`.
2. Call the same endpoints with `bodyToMono(ProductDto.class)`.
3. Use `switchIfEmpty` to reject value-less responses.
4. Use `exchangeToMono` to separate 204 from empty 200 and verify `Content-Type`.
5. Observe how decode/codec failures differ from HTTP-status `WebClientResponseException`s.

### Part C — OpenFeign

1. Register `@FeignClient(name="catalog-service")` and enable `@EnableFeignClients`.
2. Use return type `ResponseEntity<ProductDto>` and call the mock server.
3. Observe that no-content must be handled by the caller; wrong-type JSON throws in the decoder.
4. Prove that `200 text/html` is not "no instance" using target-selection traces and response headers.
5. Do not enable default retries for decode failures.

### Expected Results Checklist

| Scenario | RestClient `toEntity(ProductDto.class)` | WebClient `bodyToMono(ProductDto.class)` | Conclusion |
|---|---|---|---|
| `valid` | Valid DTO | Emits valid DTO | PASS |
| `empty-204` | No DTO; status 204 | Usually completes without emitting DTO | Valid only if contract allows |
| `empty-200` | Body may be `null` | Usually `Mono.empty()` | Violation if body required |
| `json-null` | May produce no DTO | Usually emits no DTO | Valid JSON, missing object |
| `object-empty` | May produce DTO with `null` fields | May emit DTO with `null` fields | Needs validation |
| `field-null` | May produce DTO with null/blank fields | Same | Needs validation |
| `wrong-type` | Usually deserialization error | Usually decoding error | Schema mismatch |
| `malformed` | JSON parse error | JSON parse error | Invalid body |
| `json-as-text` | Usually no converter for `ProductDto` | Usually unsupported media type error | Wrong `Content-Type` |
| `html` | Usually fails decoding to `ProductDto` | Usually media type error | Likely proxy/gateway error |
| Missing endpoint | Status 404; default `retrieve()` errors | Default `retrieve()` emits status error | Handle HTTP error contract |

"Usually" is intentional: Jackson coercion, codecs, custom converters, error handlers, and HTTP client versions can alter exact exceptions or empty-response representation. **Tests must record the behavior of your actual stack version.**

## 16. Pre-Production Checklist

- Does each endpoint clearly specify when to return 204, 404, 200 with `[]`, and 200 with an object?
- Are **required**, optional fields, and constraints defined on the client DTO?
- Do `Accept` and response `Content-Type` match the media types supported by the API?
- Are HTTP 200 0-byte bodies, JSON `null`, and JSON `{}` distinguished?
- Are JSON converters/codecs and coercion settings compatible across server and client versions?
- Is the body validated **after deserialization** rather than relying solely on annotations?
- Do RestClient/WebClient/Feign use proper error handling for both status codes and decoding?
- Are decoder failures ever turned into `null` or default DTOs, causing silent data loss or hidden bugs?
- Are retries restricted to safe transient errors rather than masking contract drift?
- Do logs capture `serviceId`, selected instance, status, content type, decode errors, and contract version?
- Do contract tests cover no-content, malformed JSON, wrong types, missing fields, and wrong media types?
- During rolling deployments, do replicas preserve **backward compatibility** with running clients?

**Conclusion:** Spring Cloud LoadBalancer handles **selecting a `ServiceInstance`**; reading the response belongs to `RestClient`, `WebClient`, or Feign decoders. For reliable inter-service communication, distinguish **missing body**, **present body with broken JSON/schema**, **mismatched Content-Type**, **error HTTP status**, and **transport/discovery failures**. Only accurate classification lets you handle nulls, validate payloads, evolve contracts, diagnose instances, or retry appropriately.

**Official References:**

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Cloud OpenFeign – Features](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
