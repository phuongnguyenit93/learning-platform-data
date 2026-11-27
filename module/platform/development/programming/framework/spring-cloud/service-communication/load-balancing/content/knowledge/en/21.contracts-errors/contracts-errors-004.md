# Mapping Each HTTP Client's Exceptions to an Application Model

In a microservices architecture, the exact same event—**`catalog-service` returning HTTP 404**—can surface as `RestClientResponseException` in **RestClient**, `WebClientResponseException` in **WebClient**, or `FeignException.NotFound` in **OpenFeign**. If business services depend directly on these exception types, switching HTTP clients or adding retries spreads error-handling logic everywhere. Worse still, **failing to pick an instance**, **connection loss**, and **receiving HTTP 503** are easily conflated, causing the application to retry wrongly or return misleading responses to users.

This lesson is part of the **Contracts and Errors** chapter in the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The goal is to design a **consistent application error model**, then map signals from **RestClient**, **WebClient**, and **OpenFeign** when calling by service ID via Spring Cloud LoadBalancer. We also distinguish the effects of **discovery, health checks, `ServiceInstance` selection policies, timeouts, retries, and observability** so root causes are never hidden.

> Principle: HTTP library exceptions are **transport-layer details**; the application layer should work with **error semantics** and **recovery policies**. However, never "flatten" all errors into a single `SERVICE_UNAVAILABLE` code, because that erases critical distinctions between API contracts and infrastructure failures.

## 1. One Scenario, Three Exception Types

Suppose `order-service` calls this endpoint:

~~~http
GET /api/items/42 HTTP/1.1
Host: catalog-service
Accept: application/json
~~~

The server may return:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://example.invalid/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "The requested item does not exist",
  "code": "ITEM_NOT_FOUND"
}
~~~

*This is an illustrative JSON sample following the Problem Details format; `code` is an application-defined extension, not a mandatory field of the standard.*

| Client | Typical signal under default config | Note |
|---|---|---|
| RestClient + `retrieve()` | `RestClientResponseException` or status-specific subclass | HTTP response was received |
| WebClient + `retrieve()` | `WebClientResponseException` in `onError` signal | Reactive publisher |
| OpenFeign with default error handling | `FeignException.NotFound` or `FeignException` | Customizable via `ErrorDecoder` |
| Application | `CatalogItemNotFound` or `RESOURCE_NOT_FOUND` | Depends on 404 semantics in the contract |

The core insight: **404 is just a transport status.** If the endpoint is `GET /api/items/{id}`, it may mean *the item does not exist*. If `/api/items/42` returns 404 because a path was misconfigured, that same status is an *integration bug*, and you should not tell the user the item definitely does not exist.

Therefore, mapping requires **operation context**: which endpoint is being called, what response is expected, whether side effects may have occurred, and what downstream error code was returned.

## 2. Layers That Can Produce Errors When Calling by Service ID

A call through Spring Cloud LoadBalancer traverses multiple steps:

~~~mermaid
flowchart TD
    A["Application calls CatalogPort.getItem(id)"] --> B["RestClient / WebClient / Feign"]
    B --> C{"Does discovery/supplier have an instance?"}
    C -->|No| D["Target selection error / no ServiceInstance"]
    C -->|Yes| E["LoadBalancer picks an instance"]
    E --> F{"Connect and send request succeeded?"}
    F -->|No| G["Connect, TLS, network, pool, timeout"]
    F -->|Yes| H{"HTTP response received?"}
    H -->|No| I["Response timeout / reset / unknown outcome"]
    H -->|Yes| J{"HTTP status and body"}
    J -->|4xx/5xx| K["Contract or backend/gateway error"]
    J -->|2xx| L{"Decode into DTO?"}
    L -->|No| M["Schema/media type/codec error"]
    L -->|Yes| N["Application result"]
~~~

**These error classes differ in nature:**

1. **No candidates:** the `ServiceInstance` list is empty due to a wrong service ID, unsynced discovery, health/filters eliminating all instances, or a supplier failure.
2. **Failed to establish/send HTTP:** connection pool exhaustion, DNS/transport error, TLS failure, connect timeout, or reset before receiving a response.
3. **Did not receive response in time:** the server may still be processing or may have already completed the request.
4. **Error HTTP status received:** an HTTP response exists, but its contract meaning must be interpreted accurately.
5. **2xx response cannot be decoded:** likely an incompatible schema change or serialization bug; do not blindly retry.
6. **Application rejects valid JSON data:** for example, an invalid domain value even though JSON decoded cleanly; this is business validation, distinct from HTTP client errors.

**LoadBalancer is not an HTTP error decoder.** It picks an instance based on the supplier and policy; responses and exceptions surface in the client transport or adapter. In some integrations, having no instance manifests as an exception or an error response synthesized at the client/LB layer; you cannot infer origin from status alone without observing the execution path.

## 3. Distinguish Four Information Dimensions Before Mapping

Each failure should carry at least four characteristics:

| Field | Question | Examples |
|---|---|---|
| **Kind** | What happened? | `RESOURCE_NOT_FOUND`, `TRANSPORT_FAILURE`, `RESPONSE_TIMEOUT` |
| **Origin** | Where did the signal come from? | Server response, load balancer, client transport, codec |
| **HTTP status** | Is there a real downstream status? | 404, 429, 503, or absent |
| **Outcome certainty** | Can we conclude whether side effects occurred? | `KNOWN_SUCCESS`, `KNOWN_REJECTED`, `UNKNOWN` |

**Retryability** should be an **evaluation per operation and time budget**, not a fixed property of a status code. For instance, a GET hitting a connection error can undergo bounded retries; a POST after a response timeout is safe to retry only if the server truly supports idempotency.

Also distinguish:

- **Observed signal:** `WebClientRequestException` indicates a request/transport failure; it does not tell you whether the DB server committed.
- **Root cause:** TLS handshake failure, pool acquire timeout, HTTP status 503, or schema-invalid payload.
- **Business meaning:** may map to "not found," "try again later," "verifying outcome," or "integration failure."

A good classifier **never swallows the cause**: it retains the original exception for diagnostics while never exposing raw stack traces to end users.

## 4. Designing a Unified Error Model for the Application Layer

Java 17+ example defining error types shared across all HTTP adapters.

~~~java
package demo.catalog.port;

public enum FailureKind {
    RESOURCE_NOT_FOUND,
    VALIDATION_REJECTED,
    CONFLICT,
    AUTHENTICATION_REJECTED,
    AUTHORIZATION_REJECTED,
    RATE_LIMITED,
    DOWNSTREAM_REJECTED,
    DOWNSTREAM_UNAVAILABLE,
    NO_SERVICE_INSTANCE,
    CONNECT_FAILURE,
    RESPONSE_TIMEOUT,
    DECODE_FAILURE,
    UNEXPECTED_FAILURE
}
~~~

~~~java
package demo.catalog.port;

public enum OutcomeCertainty {
    KNOWN_REJECTED,
    UNKNOWN
}
~~~

`UNKNOWN` here marks a **failure** where the caller cannot verify the outcome of an operation with side effects; for pure read-only GETs, there is usually no business side effect to reconcile. `KNOWN_REJECTED` should only be attached when the API contract guarantees the operation was rejected without mutating state, not applied blanket-style to all 5xx responses.

Also define the **signal origin**, independent of error meaning:

~~~java
package demo.catalog.port;

public enum FailureOrigin {
    HTTP_RESPONSE,
    LOAD_BALANCER,
    TRANSPORT,
    CODEC
}
~~~

A record carrying safe metadata:

~~~java
package demo.catalog.port;

public record DownstreamFailure(
    String serviceId,
    String operation,
    FailureKind kind,
    FailureOrigin origin,
    Integer downstreamHttpStatus,
    OutcomeCertainty outcome,
    String diagnosticCode
) {
}
~~~

And the application exception:

~~~java
package demo.catalog.port;

public final class DownstreamCallException extends RuntimeException {

    private final DownstreamFailure failure;

    public DownstreamCallException(
        DownstreamFailure failure,
        Throwable cause
    ) {
        super(failure.kind().name(), cause);
        this.failure = failure;
    }

    public DownstreamFailure failure() {
        return failure;
    }
}
~~~

**Why not attach `retryable=true` directly to every error?** Because the same `RESPONSE_TIMEOUT` may be retryable for a GET yet dangerous for an order-creation POST lacking idempotency. Better to have a **RetryPolicy** evaluating `FailureKind` + operation semantics + attempt count + remaining deadline.

`diagnosticCode` should be a stable, non-sensitive code such as `CATALOG_HTTP_503`. Never place response bodies containing PII, Authorization headers, or URLs with tokens inside `DownstreamFailure`.

### Business Port Contract

The business layer can define its own port:

~~~java
package demo.catalog.port;

public interface CatalogPort {
    ItemDto getItem(String id);
}
~~~

~~~java
package demo.catalog.port;

public record ItemDto(String id, String name, int stock) {
}
~~~

RestClient/WebClient/OpenFeign serve as **adapters** for this port. Business services know `CatalogPort` and `DownstreamCallException`, without importing `FeignException` or `WebClientResponseException`.

## 5. Contract-Based HTTP Status Mapping Rules

A reference mapping table for `GET /api/items/{id}`:

| Downstream signal | Typical meaning | Suggested application model | Retry? |
|---|---|---|---|
| 400 | Invalid input/query | `VALIDATION_REJECTED` if per contract | Not mechanically |
| 401 | Unauthenticated | `AUTHENTICATION_REJECTED` | Usually fix credentials first |
| 403 | Insufficient permissions | `AUTHORIZATION_REJECTED` | Do not retry with same credentials |
| 404 + `ITEM_NOT_FOUND` | Item does not exist | `RESOURCE_NOT_FOUND` | No |
| 404 with wrong URL/mapping | Integration bug | `DOWNSTREAM_REJECTED`/`UNEXPECTED_FAILURE` | Fix contract |
| 409 | State/version conflict | `CONFLICT` | Depends on resolution strategy |
| 422 | Semantically invalid input | `VALIDATION_REJECTED` | Usually no |
| 429 | Rate limited | `RATE_LIMITED` | Conditional; honor `Retry-After` |
| 500 | Server error | `DOWNSTREAM_UNAVAILABLE` or other upstream error per contract | Conditional |
| 502/503/504 | Gateway/availability/timeout | `DOWNSTREAM_UNAVAILABLE` | Conditional |
| 2xx, JSON fails decoding | Contract mismatch | `DECODE_FAILURE` | Investigate rather than retry |
| No HTTP response | Connection/timeout/discovery | `CONNECT_FAILURE`, `RESPONSE_TIMEOUT`, `NO_SERVICE_INSTANCE` | Depends on operation |

This is a **suggested matrix**, not a built-in Spring rule. In particular, an HTTP 500 can occur **after the server has already persisted data**; for writes, you cannot reliably conclude FAILED solely from status.

For `GET` endpoints, 404 can be a **valid business result** (returning `Optional.empty()`) instead of an exception. If adopting that design, the application port can return `Optional<ItemDto>`, provided you confirm 404 strictly means missing resource rather than a bad API route.

## 6. Building a Shared HTTP Status Classifier

So all adapters interpret statuses consistently, centralize status rules in a helper:

~~~java
package demo.catalog.port;

public final class CatalogHttpFailureMapper {

    private CatalogHttpFailureMapper() {}

    public static FailureKind classify(
        int status,
        String downstreamCode
    ) {
        return switch (status) {
            case 400, 422 -> FailureKind.VALIDATION_REJECTED;
            case 401 -> FailureKind.AUTHENTICATION_REJECTED;
            case 403 -> FailureKind.AUTHORIZATION_REJECTED;
            case 404 ->
                "ITEM_NOT_FOUND".equals(downstreamCode)
                    ? FailureKind.RESOURCE_NOT_FOUND
                    : FailureKind.DOWNSTREAM_REJECTED;
            case 409 -> FailureKind.CONFLICT;
            case 429 -> FailureKind.RATE_LIMITED;
            case 500, 502, 503, 504 ->
                FailureKind.DOWNSTREAM_UNAVAILABLE;
            default -> FailureKind.DOWNSTREAM_REJECTED;
        };
    }
}
~~~

In practice, `downstreamCode` must be extracted from a **valid error response** matching the agreed schema. Do not assume every 404 carries `ITEM_NOT_FOUND`, and do not attempt to deserialize error payloads of unbounded size.

The examples below focus on status mapping; when the error code has not been parsed yet, they pass `null`. That classifies 404 as `DOWNSTREAM_REJECTED` until there is explicit proof the item does not exist.

### Creating Exceptions in a Uniform Format

~~~java
package demo.catalog.port;

public final class CatalogFailureFactory {

    private CatalogFailureFactory() {}

    public static DownstreamCallException fromHttp(
        String operation,
        int status,
        String contractCode,
        Throwable cause
    ) {
        FailureKind kind =
            CatalogHttpFailureMapper.classify(status, contractCode);

        OutcomeCertainty certainty =
            switch (kind) {
                case RESOURCE_NOT_FOUND,
                     VALIDATION_REJECTED,
                     AUTHENTICATION_REJECTED,
                     AUTHORIZATION_REJECTED,
                     CONFLICT -> OutcomeCertainty.KNOWN_REJECTED;
                default -> OutcomeCertainty.UNKNOWN;
            };

        return new DownstreamCallException(
            new DownstreamFailure(
                "catalog-service",
                operation,
                kind,
                FailureOrigin.HTTP_RESPONSE,
                status,
                certainty,
                "CATALOG_HTTP_" + status
            ),
            cause
        );
    }

    public static DownstreamCallException fromTransport(
        String operation,
        FailureKind kind,
        Throwable cause
    ) {
        return new DownstreamCallException(
            new DownstreamFailure(
                "catalog-service",
                operation,
                kind,
                kind == FailureKind.NO_SERVICE_INSTANCE
                    ? FailureOrigin.LOAD_BALANCER
                    : kind == FailureKind.DECODE_FAILURE
                        ? FailureOrigin.CODEC
                        : FailureOrigin.TRANSPORT,
                null,
                OutcomeCertainty.UNKNOWN,
                "CATALOG_" + kind.name()
            ),
            cause
        );
    }
}
~~~

**Caveat for this example:** `KNOWN_REJECTED` applies only when the downstream contract genuinely guarantees zero side effects for those errors. For POST APIs with different semantics, build a per-operation mapper rather than reusing it mechanically. `UNKNOWN` also does not mean the server definitely succeeded; it means **no conclusion can be drawn** from available evidence.

This classifier demonstrates **decoupling the error taxonomy from each HTTP library**; it does not replace detailed contract design for every downstream.

## 7. RestClient: Mapping HTTP Responses and I/O Errors

With Spring Framework 6.1+ and a compatible Spring Cloud release, create a LoadBalancer-enabled `RestClient`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

In the adapter, `retrieve()` typically turns HTTP 4xx/5xx into `RestClientResponseException` or a subclass. Transport failures appear as `ResourceAccessException`; decoding errors can appear as `RestClientException` or a converter cause.

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
class RestCatalogAdapter implements CatalogPort {

    private final RestClient client;

    RestCatalogAdapter(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    @Override
    public ItemDto getItem(String id) {
        try {
            return client.get()
                .uri("/api/items/{id}", id)
                .retrieve()
                .body(ItemDto.class);
        } catch (RestClientResponseException ex) {
            throw CatalogFailureFactory.fromHttp(
                "getItem", ex.getStatusCode().value(), null, ex);
        } catch (ResourceAccessException ex) {
            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.CONNECT_FAILURE, ex);
        } catch (RestClientException ex) {
            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.DECODE_FAILURE, ex);
        }
    }
}
~~~

**Important limitations of this example:**

- `RestClientResponseException` handles errors carrying an **HTTP status from a response the client received**, though if an intermediary synthesized the response, that status did not necessarily come from the business instance.
- `ResourceAccessException` wraps many I/O failures, including read timeouts and connection resets. Mapping all of them to `CONNECT_FAILURE` as in this minimal example is a **coarse classification**; production code should inspect the cause and request phase to separate `RESPONSE_TIMEOUT` from pre-send connection errors.
- Do not treat **every** remaining `RestClientException` as a decoding error: it could be another request/codec failure. Use exception chains and integration tests to refine the taxonomy.
- **No `ServiceInstance` found** may raise a different exception or synthesize a different response depending on version; these three catch blocks are not guaranteed to cover every variant.
- If `body(ItemDto.class)` can return `null` (e.g., 204/empty body), check the contract instead of passing `null` silently into business code.

### When You Need More Granular Timeout Classification

A cause-walking helper can inspect the exception chain for indicators like `SocketTimeoutException`, `ConnectException`, or transport-specific timeout types. Still, **checking exception names alone never tells you whether the server processed the request**. For POSTs, mark read timeouts as `UNKNOWN` outcome and use idempotency/status queries before retrying.

## 8. RestClient: Using onStatus to Translate Errors at the HTTP Boundary

Besides an outer try/catch, `retrieve().onStatus(...)` can convert HTTP statuses into exceptions:

~~~java
ItemDto item = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw CatalogFailureFactory.fromHttp(
                "getItem", 404, "ITEM_NOT_FOUND", null);
        }
    )
    .onStatus(
        status -> status.is5xxServerError(),
        (request, response) -> {
            throw CatalogFailureFactory.fromHttp(
                "getItem", response.getStatusCode().value(), null, null);
        }
    )
    .body(ItemDto.class);
~~~

Here `"ITEM_NOT_FOUND"` is hardcoded as a **contract assumption** for `GET /api/items/{id}`; real APIs should inspect the error body/code rather than inferring solely from 404. If you need to preserve full causes, use a dedicated exception representing the HTTP response with readable metadata. With `onStatus`, `retrieve()`'s default handling still applies to any status not matched by custom handlers.

Do not rely on `onStatus` to catch missing-instance or failed-connect errors: those can occur **before any response exists**.

### exchange() Differs from retrieve()

With `RestClient.exchange(...)`, the callback receives the request and response directly and **bypasses `retrieve()`'s status handlers**. When using `exchange`, the application must check HTTP status and convert the body itself:

~~~java
int status = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .exchange((request, response) ->
        response.getStatusCode().value()
    );
~~~

This snippet only returns the status for illustration; body/error schema handling must be added per contract. Never write a mapper catching only `RestClientResponseException` and assume it catches every 404 when calling `exchange()`.

## 9. WebClient: Mapping via Reactive Error Signals

`WebClient` follows a reactive model. `retrieve().bodyToMono(ItemDto.class)` returns a `Mono<ItemDto>`; HTTP/transport/codec failures typically surface **when subscribed**, not necessarily when the Java method is invoked.

Configuring a LoadBalancer-enabled `WebClient`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder")
        WebClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

A reactive adapter should expose a **dedicated reactive port** (never pretend it is a blocking port):

~~~java
package demo.catalog.port;

import reactor.core.publisher.Mono;

public interface ReactiveCatalogPort {
    Mono<ItemDto> getItem(String id);
}
~~~

And exception mapping:

~~~java
import org.springframework.core.codec.DecodingException;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

@Component
class ReactiveCatalogAdapter implements ReactiveCatalogPort {

    private final WebClient client;

    ReactiveCatalogAdapter(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    @Override
    public Mono<ItemDto> getItem(String id) {
        return client.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class)
            .onErrorMap(
                WebClientResponseException.class,
                ex -> CatalogFailureFactory.fromHttp(
                    "getItem", ex.getStatusCode().value(), null, ex)
            )
            .onErrorMap(
                WebClientRequestException.class,
                ex -> CatalogFailureFactory.fromTransport(
                    "getItem", FailureKind.CONNECT_FAILURE, ex)
            )
            .onErrorMap(
                DecodingException.class,
                ex -> CatalogFailureFactory.fromTransport(
                    "getItem", FailureKind.DECODE_FAILURE, ex)
            );
    }
}
~~~

**Notes:**

- `WebClientResponseException` usually signals an HTTP error response. With `retrieve()`, default 4xx/5xx handling emits an error signal.
- `WebClientRequestException` signals a request/transport error and **does not guarantee** the server had no side effects.
- `DecodingException` covers one common codec error family; other deserialization errors may appear in distinct causes.
- Reactor's `timeout(Duration)` emits `TimeoutException`, bypassing the three branches above; map it explicitly while preserving deadline/operation context.
- Never use `onErrorMap(Throwable.class, ...)` to convert every error into a downstream failure: it can swallow application bugs, corrupt cancellation semantics, or mask internal validation errors.

### When Using exchangeToMono

`exchangeToMono(...)` lets you branch directly on `ClientResponse.statusCode()`. If choosing this route, read or release the response body using the proper API and translate error statuses yourself; do not assume 404/503 automatically emit `WebClientResponseException` as with `retrieve()`.

## 10. WebClient: Classifying Cancellation, Timeout, and Retry

Several reactive signals need distinct handling:

| Signal | Meaning | Suggested classification |
|---|---|---|
| `onError(WebClientResponseException)` | Received HTTP error status | HTTP contract mapping |
| `onError(WebClientRequestException)` | I/O/transport error during request | `CONNECT_FAILURE` or specific transport kind |
| `onError(DecodingException)` | Response failed decoding | `DECODE_FAILURE` |
| `onError(TimeoutException)` | Deadline/operator timeout | `RESPONSE_TIMEOUT` or `DEADLINE_EXCEEDED` if modeled |
| `cancel` | Downstream stopped subscribing | **Not an error by default** |
| `onComplete` with no value | Valid empty `Mono` or missing data per contract | Check business contract |

Example mapping the timeout operator into a failure:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

Mono<ItemDto> result = reactiveCatalogPort.getItem("42")
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(
        TimeoutException.class,
        ex -> CatalogFailureFactory.fromTransport(
            "getItem", FailureKind.RESPONSE_TIMEOUT, ex)
    );
~~~

Here, the timeout occurred at the **publisher after the adapter was invoked**; for HTTP calls with side effects, never assume cancellation rolls back the server. Nor are retries enabled simply because `onErrorMap` produces a standardized exception.

For bounded retries, design a policy checking `DownstreamFailure.kind()`, method/operation, attempt number, and deadline. Never retry a streaming `Flux` or non-idempotent POST unboundedly. A resubscribe can issue a brand-new HTTP request and cause LoadBalancer to pick a different instance.

## 11. OpenFeign: FeignException, RetryableException, and ErrorDecoder

OpenFeign typically generates a proxy from `@FeignClient`:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

With `@EnableFeignClients` and Spring Cloud LoadBalancer integration configured, Feign calls `catalog-service` by service ID. Exact client stack, retry policy, and error handling depend on dependencies and the release train.

Typically:

- HTTP error responses surface as `FeignException` or subclasses such as `FeignException.NotFound`.
- Some retryable errors surface as `RetryableException`.
- `ErrorDecoder` can translate HTTP statuses into custom exceptions.
- `Retryer` determines whether Feign retries the request before the final exception reaches business code.

**Do not equate `RetryableException` with "no HTTP response."** An `ErrorDecoder` can instantiate a `RetryableException` for a specific HTTP status, so you must still inspect status and cause.

### Mapping in the Feign Adapter

~~~java
import feign.FeignException;
import feign.RetryableException;
import org.springframework.stereotype.Component;

@Component
class FeignCatalogAdapter implements CatalogPort {

    private final CatalogFeignClient client;

    FeignCatalogAdapter(CatalogFeignClient client) {
        this.client = client;
    }

    @Override
    public ItemDto getItem(String id) {
        try {
            return client.getItem(id);
        } catch (RetryableException ex) {
            if (ex.status() > 0) {
                throw CatalogFailureFactory.fromHttp(
                    "getItem", ex.status(), null, ex);
            }

            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.CONNECT_FAILURE, ex);
        } catch (FeignException ex) {
            if (ex.status() > 0) {
                throw CatalogFailureFactory.fromHttp(
                    "getItem", ex.status(), null, ex);
            }

            throw CatalogFailureFactory.fromTransport(
                "getItem", FailureKind.UNEXPECTED_FAILURE, ex);
        }
    }
}
~~~

**This is a minimal mapper, not exhaustive of every exception Feign can throw.** A project-configured `ErrorDecoder` may return a custom exception that does not extend `FeignException`. Also verify `RetryableException.status()` behavior for your Feign version; if the status is not a real HTTP status, classify by cause rather than inferring from the subclass.

Spring Cloud OpenFeign may configure `Retryer.NEVER_RETRY` by default in certain versions, differing from Feign core defaults. Therefore, seeing `RetryableException` does not prove multiple attempts were made. Check your `Retryer` configuration and actual request counts.

## 12. OpenFeign: ErrorDecoder and Its Relationship to the Application Mapper

To convert a specific status into a custom exception right when Feign receives the response, use `ErrorDecoder`:

~~~java
import feign.Response;
import feign.codec.ErrorDecoder;

final class CatalogFeignErrorDecoder implements ErrorDecoder {

    private final ErrorDecoder fallback = new ErrorDecoder.Default();

    @Override
    public Exception decode(String methodKey, Response response) {
        int status = response.status();

        if (status == 404) {
            return CatalogFailureFactory.fromHttp(
                methodKey,
                status,
                "ITEM_NOT_FOUND",
                null
            );
        }

        return fallback.decode(methodKey, response);
    }
}
~~~

This is a minimal sample **assuming** 404 on the matching method means `ITEM_NOT_FOUND`. If the decoder applies across multiple methods, check `methodKey` and each endpoint's contract before assigning an error code. The decoder must also avoid reading unbounded large or sensitive raw bodies.

A client-scoped Feign configuration:

~~~java
import feign.codec.ErrorDecoder;
import org.springframework.context.annotation.Bean;

class CatalogFeignConfiguration {

    @Bean
    ErrorDecoder catalogErrorDecoder() {
        return new CatalogFeignErrorDecoder();
    }
}
~~~

And registration:

~~~java
@FeignClient(
    name = "catalog-service",
    configuration = CatalogFeignConfiguration.class
)
interface CatalogFeignClient {
    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

The two `CatalogFeignClient` snippets in Section 11 and this section are **alternative options**; do not declare both with the same name in one package. Keep per-client Feign configurations outside general component scanning if you want to avoid accidentally applying `ErrorDecoder` to other clients.

Choosing between **ErrorDecoder** and an **adapter mapper**:

- `ErrorDecoder` fits when translating **HTTP responses per Feign contract**.
- An adapter mapper fits when normalizing **HTTP, transport, decode, and LoadBalancer errors** into the application model.
- You can combine both, provided you avoid **double-mapping** or hiding causes. If `ErrorDecoder` already returns `DownstreamCallException`, let the adapter pass it through instead of catching and re-wrapping it.

## 13. HTTP Interface Proxies Also Follow Their Underlying Adapter

With Spring Framework HTTP Service Interfaces using `@HttpExchange` and `HttpServiceProxyFactory`:

- A proxy backed by `RestClientAdapter` inherits `RestClient` error semantics.
- A proxy backed by `WebClientAdapter` inherits `WebClient` error semantics.
- The Java interface alone does not invent a single shared "HTTP Interface exception" across all adapters.

Therefore, when implementing `CatalogPort`, write mappers **matching the underlying HTTP adapter**, not the interface annotations. This is also a key benefit of port/adapters: switching from Feign to HTTP Interfaces does not force rewriting every business service just to replace `FeignException.NotFound` with `RestClientResponseException`.

When switching an HTTP Interface from `RestClientAdapter` to `WebClientAdapter`, account for the **blocking → reactive** shift, `Mono`/`Flux` return types, and signal-based error handling. You cannot swap HTTP stacks while keeping old assumptions about threads and timeouts.

## 14. Should Every HTTP 404 Become a Business Error?

No. Compare three different APIs:

| API | What HTTP 404 can mean | Appropriate mapping |
|---|---|---|
| `GET /api/items/{id}` | Item does not exist, per contract | `RESOURCE_NOT_FOUND` or `Optional.empty()` |
| `POST /api/orders` | Wrong route or undeployed endpoint | `DOWNSTREAM_REJECTED` / integration bug |
| `GET /api/orders/by-key/{key}` | Operation not visible yet in queried store | Status unknown; **do not infer operation never arrived** |

Even on `GET /api/items/{id}`, a backend may return 404 to hide resource existence for security reasons. If the caller turns it into `ItemMissing` for the user without considering access-control contracts, it can produce misleading responses.

### Prefer Stable Error Codes Over Comparing Detail Strings

An error schema should provide stable `code` values such as `ITEM_NOT_FOUND`, `RATE_LIMIT_EXCEEDED`, `INSUFFICIENT_STOCK`, and `REQUEST_CONFLICT`. Never base logic on natural-language `detail` text:

~~~json
{
  "type": "https://example.invalid/problems/insufficient-stock",
  "title": "Insufficient stock",
  "status": 409,
  "code": "INSUFFICIENT_STOCK",
  "traceId": "trace-example"
}
~~~

`traceId` and `code` are application-contract extension fields; services must agree on the schema and avoid leaking internal data. Callers must also validate status, `Content-Type`, and response size limits before deserializing error bodies.

## 15. Distinguishing No-Instance Errors from HTTP 503

A frequently misclassified failure:

~~~mermaid
flowchart TD
    A["Caller requests catalog-service"] --> B{"Supplier has ServiceInstance?"}
    B -->|No| C["No target: NO_SERVICE_INSTANCE"]
    B -->|Yes| D["Send request to selected instance"]
    D --> E{"Response received?"}
    E -->|No| F["CONNECT_FAILURE / RESPONSE_TIMEOUT"]
    E -->|Yes, HTTP 503| G["DOWNSTREAM_UNAVAILABLE"]
~~~

If `ServiceInstanceListSupplier` returns an empty list, no HTTP request may ever reach a business backend. Depending on the integration, the client may throw an exception or surface a synthesized error HTTP response. Thus, **`status=503` alone cannot prove `catalog-service` returned 503**.

How to verify:

1. Record `serviceId` and candidate count from the supplier.
2. Observe whether a `ServiceInstance` was selected.
3. Check whether an HTTP request was dispatched to the backend.
4. If a response exists, distinguish backend, gateway, or intermediary origin.
5. Attach correlation/trace IDs and root cause to the failure model.

`NO_SERVICE_INSTANCE` points to discovery, cache, health check, or routing policy issues; `DOWNSTREAM_UNAVAILABLE` from a 503 response may mean backend overload or maintenance. Both may end up returning the same HTTP status to end users, yet they **must still be classified differently in logs, metrics, and operations**.

## 16. Retryability Must Not Be Computed Solely from Exception Class

A naive rule like "retry every `IOException`" breaks down on write operations. You must know **whether the operation has side effects** and whether the server enforces **idempotency**.

| Failure type | Read-only GET | Idempotent order POST | Non-idempotent order POST |
|---|---|---|---|
| No instance | Bounded retry if discovery is recovering | Only within deadline with stable key | Do not retry unboundedly |
| Clear pre-send connect failure | Can retry | Can retry with same key | Verify transport first |
| Read/response timeout | Bounded retry within budget | UNKNOWN; query/retry with same key | **Never retry blindly** |
| HTTP 429 | Check `Retry-After` and deadline | Only if contract allows | Be cautious |
| HTTP 503/504 | Conditional retry | UNKNOWN if side effects may have occurred | Do not treat failure as rollback |
| HTTP 400/401/403 | Usually do not retry same request | Fix input/credentials | Fix input/credentials |
| HTTP 404 resource missing | No | Not applicable the same way | Not applicable the same way |
| Decode failure after HTTP 2xx | Investigate schema; usually do not retry | Avoid duplicate side effects | Never retry blindly |

A single `retryable` boolean on `DownstreamFailure` is convenient for logging yet easy to misuse. Final decisions belong to a **resilience policy** at a boundary with full context:

~~~text
shouldRetry = errorKind is recoverable
              AND operation allows repetition / has idempotency
              AND attempts remain within limit
              AND deadline has enough time left
              AND system-wide retry budget permits
~~~

If client, LoadBalancer, gateway, and service mesh all retry, HTTP attempts multiply. The application layer should be aware of total attempt counts rather than looking only at one library's retry setting.

## 17. Indeterminate Outcomes on Write Operations

Suppose `POST /api/orders` is processed successfully by the server, yet the response is lost. The caller may only observe `ResourceAccessException`, `WebClientRequestException`, or `RetryableException`, depending on client and transport.

~~~mermaid
sequenceDiagram
    participant C as order-service
    participant LB as LoadBalancer
    participant A as inventory-a
    participant DB as Database
    participant B as inventory-b

    C->>LB: POST key=K
    LB-->>C: Pick A
    C->>A: POST /reserve key=K
    A->>DB: COMMIT reservation #101
    A--xC: Response lost
    Note over C: Caller timeout => UNKNOWN
    C->>LB: Retry with same key K if policy allows
    LB-->>C: May pick B
    C->>B: POST /reserve key=K
    B->>DB: Look up key K in shared store
    DB-->>B: #101 already exists
    B-->>C: Return #101 result without creating duplicate
~~~

If a system tags `RESPONSE_TIMEOUT` with `outcome=KNOWN_REJECTED`, it can create duplicate orders when retrying with a fresh key. **Outcome certainty must reflect actual evidence**, not the caller's wishful thinking.

Rules for write operations:

- Generate and keep a fixed **Idempotency-Key** for the entire business operation.
- Use a **shared durable dedup store** with unique keys/transactions or an equivalent mechanism.
- Expose a status-query endpoint by operation ID/key for reconciliation.
- Never turn `UNKNOWN` into `FAILED` merely because the caller stopped waiting.
- When LoadBalancer retries can pick another instance, never store idempotency keys only in one instance's RAM.
- For side effects outside the DB, use a dedicated deduplication protocol or outbox/saga/reconciliation.

## 18. Returning Inbound API Errors Without Leaking Downstream Internals

A calling service is often also an HTTP server for upstream clients. After the adapter translates a failure into `DownstreamCallException`, the inbound layer can map it to Spring Framework's **ProblemDetail**:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiFailureAdvice {

    @ExceptionHandler(DownstreamCallException.class)
    ResponseEntity<ProblemDetail> onDownstreamFailure(
            DownstreamCallException ex) {

        FailureKind kind = ex.failure().kind();

        HttpStatus outboundStatus = switch (kind) {
            case RESOURCE_NOT_FOUND -> HttpStatus.NOT_FOUND;
            case VALIDATION_REJECTED -> HttpStatus.BAD_REQUEST;
            case CONFLICT -> HttpStatus.CONFLICT;
            case RATE_LIMITED -> HttpStatus.SERVICE_UNAVAILABLE;
            case NO_SERVICE_INSTANCE,
                 DOWNSTREAM_UNAVAILABLE,
                 CONNECT_FAILURE,
                 RESPONSE_TIMEOUT -> HttpStatus.SERVICE_UNAVAILABLE;
            default -> HttpStatus.BAD_GATEWAY;
        };

        ProblemDetail problem = ProblemDetail.forStatus(outboundStatus);
        problem.setTitle("Unable to complete request");
        problem.setDetail(
            "The requested operation could not be completed at this time");
        problem.setProperty(
            "code",
            ex.failure().kind().name()
        );

        return ResponseEntity.status(outboundStatus).body(problem);
    }
}
~~~

**This is an illustrative policy, not a mandatory mapping.** Public APIs may choose different statuses per contract—such as `502 Bad Gateway` when a downstream breaks its contract or `504 Gateway Timeout` for a true gateway timeout. Never pass a downstream HTTP 401 straight through as HTTP 401 to end users if the issue was **service-to-service credentials**: that causes pointless re-logins or leaks internal auth details.

Keep in mind:

1. **Downstream HTTP 404** does not always correspond to the resource that the caller's inbound API reports as missing.
2. **Downstream HTTP 409** can be a business conflict, or an internal version/contract error.
3. **Downstream HTTP 429** does not necessarily mean the external user exceeded a quota; the calling service itself may have sent too many requests.
4. Never include `serviceId`, host/port, raw response bodies, stack traces, or access tokens in public `ProblemDetail` payloads by default.
5. For `UNKNOWN` write operations, define a clear contract for pending-verification status/operation IDs; claiming "definitely failed" is wrong.

## 19. Do Not Use Fallbacks to Mask Contract Errors

Fallbacks are useful when supplementary data can be omitted, but dangerous when failures carry business meaning.

| Situation | Acceptable fallback | Dangerous fallback |
|---|---|---|
| Product recommendations fail | Return empty list marked degraded | Mark the order completed |
| Catalog product read fails | Serve cached read with TTL/stale flag | Invent unconfirmed prices/stock |
| Payment request times out | Return `UNKNOWN/PENDING` with operation ID | Return fake success or create a new payment |
| HTTP 404 means item absent | Return business NotFound | Retry repeatedly or return a fake object |
| Decoder cannot read new schema | Report integration error and alert | Silently drop critical fields |

A fallback must make **data trustworthiness** explicit rather than disguising a broken system as a healthy result. In reactive pipelines, avoid `onErrorResume(error -> Mono.empty())` across all errors: downstream stages will never know the dependency failed.

## 20. Logging, Tracing, and Telemetry You Must Not Drop

When normalizing failures into a shared model, preserve origin details for operations:

| Metadata | Role |
|---|---|
| `serviceId` | Logical service called |
| Operation/route template | Endpoint and business meaning; avoid URLs with PII |
| `selectedInstance` if present | Target chosen by LoadBalancer, for diagnostics |
| Root exception class/cause | Distinguish HTTP, I/O, TLS, codec |
| HTTP status and response origin | Know whether status came from backend, gateway, or was synthesized |
| `FailureKind` and `diagnosticCode` | Stable failure category for the application |
| Request attempt / retry count | Know how many attempts occurred |
| Timeout type | Pool, connect, read, total deadline |
| `OutcomeCertainty` | Prevent wrong assumptions about side effects |
| Trace ID/correlation ID | Link caller, LoadBalancer, and server |
| Time-to-first-byte, duration | Pinpoint slow stages |
| Response schema/media type | Diagnose decoding errors |

Never put raw **request IDs or idempotency keys** into high-cardinality metric labels. For detailed logs, redact sensitive data and use access-controlled traces/logs. Server, gateway, and caller may record different HTTP statuses for the same transaction; use trace and operation IDs to reconcile boundaries.

### Why Not Count Only 5xx?

A request can fail **before an HTTP response exists**, so `http.client.response.status=5xx` metrics miss connect errors, pool acquisition timeouts, and missing-instance failures. Add metrics for error causes, `NO_SERVICE_INSTANCE`, and `UNKNOWN` outcomes.

## 21. Testing Mapping Contracts for Each Client

Use the same mock/stub API (such as WireMock, MockWebServer, or a test server) and the same test matrix across RestClient, WebClient, and OpenFeign. Unit tests can mock client exceptions to test mappers, while integration tests must send real HTTP traffic to verify responses and causes.

| Scenario | RestClient | WebClient | OpenFeign | Expected FailureKind |
|---|---|---|---|---|
| HTTP 404 + `ITEM_NOT_FOUND` | `RestClientResponseException` | `WebClientResponseException` | `FeignException.NotFound` | `RESOURCE_NOT_FOUND` |
| HTTP 404 wrong route | HTTP response | HTTP response | HTTP response | `DOWNSTREAM_REJECTED` |
| HTTP 409 business conflict | HTTP response | HTTP response | HTTP response | `CONFLICT` |
| HTTP 429 | HTTP response | HTTP response | HTTP response | `RATE_LIMITED` |
| Backend HTTP 503 | HTTP response | HTTP response | HTTP response | `DOWNSTREAM_UNAVAILABLE` |
| No `ServiceInstance` | Depends on LB integration | Depends on LB integration | Depends on LB integration | `NO_SERVICE_INSTANCE` once origin verified |
| Connect refused | `ResourceAccessException` or cause | `WebClientRequestException` or cause | Feign transport exception | `CONNECT_FAILURE` |
| Read timeout | I/O exception/cause | Request/timeout signal | Feign transport/cause | `RESPONSE_TIMEOUT` |
| HTTP 200 with bad JSON | Converter exception | Codec/DecodingException | Feign decoder exception | `DECODE_FAILURE` |
| POST committed, response lost | I/O failure | Request/error signal | Feign exception | `UNKNOWN` outcome |

**Hard part of testing:** if a mapper only inspects status without reading the contract error code, it **cannot tell apart** the first two 404 rows. Add a valid error-body parser, per-operation contracts, and matching tests.

### Testing LoadBalancer with Two Instances

With `SimpleDiscoveryClient`, configure two instances `catalog-a` and `catalog-b`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Key test cases:

1. Valid service ID and two healthy instances: requests can reach both.
2. Remove all instances from the supplier: verify **no request is sent** to backends and map `NO_SERVICE_INSTANCE` according to your real integration.
3. Instance A is dead while supplier still lists A: connection error is distinguished from HTTP 503 returned by B.
4. Proxy/gateway returns 503: record response origin so it is not mistaken for `NO_SERVICE_INSTANCE`.
5. Backend returns 200 with an invalid body: ensure it does not map to generic `DOWNSTREAM_UNAVAILABLE`.
6. POST times out after commit: preserve `UNKNOWN` outcome and never retry with a new idempotency key.

## 22. Pre-Rollout Checklist for Your Error Model

- Do you have an **application error taxonomy** independent of RestClient, WebClient, and Feign?
- Are **instance selection, transport, response status, decoding, and business validation errors** separated?
- Are HTTP statuses mapped per **operation and contract code**, rather than by raw number alone?
- Are exception causes and safe metadata preserved for debugging?
- With Feign, have you verified `ErrorDecoder` and actual `Retryer` behavior?
- With RestClient, have you distinguished `retrieve()` from `exchange()`?
- With WebClient, are errors mapped in the reactive pipeline without turning every `cancel` into an error?
- Are POST read timeouts/unknown outcomes properly classified?
- Does your retry policy evaluate idempotency, deadlines, and attempt budgets?
- Do inbound error responses avoid leaking URLs, tokens, raw bodies, and stack traces?
- Do downstream HTTP 401/403/404/409/429 truly mean the same thing on the inbound API?
- Have you tested both schema-invalid 2xx bodies and missing `ServiceInstance` cases?
- Do traces/logs capture `selectedInstance` and response origin?
- When falling back, is degraded/unknown state recorded instead of faking success?
- Are pre-HTTP failures monitored alongside 5xx charts?

## 23. Conclusion

**RestClient**, **WebClient**, and **OpenFeign** expose different exception types and error-handling APIs. They are merely **communication adapters**; the application layer should receive a **unified error model** capturing **FailureKind, signal origin, HTTP status if present, outcome certainty, and cause**. Accurate mapping depends on the **endpoint's contract**, not status codes or exception names alone.

In Spring Cloud LoadBalancer, issues across **discovery, health checks, caches, and `ServiceInstance` selection policies** can prevent requests from ever reaching a server. Conversely, timeouts or lost responses can happen **after the server has already produced side effects**. Separating these two possibilities enables proper error responses, budgeted retries, idempotency, safe fallbacks, and reliable reconciliation. A good error model does not hide infrastructure details—it **translates them into stable business semantics while retaining enough evidence for operations and testing**.
