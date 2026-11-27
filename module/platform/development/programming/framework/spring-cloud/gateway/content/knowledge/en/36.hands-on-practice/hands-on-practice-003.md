# Standardizing Paths, Headers, and Error Codes for Backend APIs

## 1. Practice Objectives

An API Gateway typically accepts URLs and headers defined by a public contract, whereas backend microservices may use different paths, internal headers, and error representations. Without a shared convention, clients must know which URL each service uses, which headers are trustworthy, and how to parse each error body. That makes the API hard to evolve and prone to security bugs.

In this hands-on lab, we build a Gateway in front of a Catalog service. The Gateway standardizes:

1. **Paths:** the client calls `/api/catalog/v1/items/42`; the Catalog service receives `/v1/items/42`.
2. **Request headers:** strip self-asserted identity headers from clients, forward a validated correlation ID, and add Gateway-controlled internal metadata.
3. **Response headers:** apply a consistent response policy, avoid duplicate headers, and reduce server information leakage.
4. **Error codes:** downstream returns a stable error contract based on RFC 9457 Problem Details; the Gateway fallback also returns the same structure when upstream is unavailable.
5. **Verification:** use curl to verify paths, headers, status codes, bodies, and behavior when the backend fails.

### Expected Results

The client only needs to know the public contract:

```http
GET /api/catalog/v1/items/42?lang=vi
X-Correlation-Id: lab-request-42
```

The Gateway forwards the request to the backend:

```http
GET /v1/items/42?lang=vi
X-Correlation-Id: lab-request-42
X-API-Contract: catalog-v1
```

Clients cannot spoof identity via `X-User-Id` or `X-User-Role`; the Gateway removes those headers before forwarding. If the product does not exist, the client receives HTTP 404 and a machine-readable code such as `PRODUCT_NOT_FOUND`. If the Catalog service is unavailable, the Gateway fallback returns HTTP 503 with `CATALOG_UNAVAILABLE`.

### Technical Scope

- Spring Cloud Gateway Server WebFlux 5.0.x.
- Spring Boot 4.x and Spring Framework WebFlux.
- Java 17+ (or the Java version required by the project's Spring Boot BOM).
- An HTTP Catalog service running on local port 8081.
- The Gateway running on local port 8080.

Service names, hosts, and data in the lab are illustrative. If your application uses Spring Cloud Gateway Server Web MVC, the filter/security APIs differ from WebFlux; do not copy `GlobalFilter` and `ServerWebExchange` classes into MVC.

## 2. Sketching the Public and Internal Contracts

### 2.1. Path Mapping

| Public API | Internal API | Meaning |
|---|---|---|
| `GET /api/catalog/v1/items/{id}` | `GET /v1/items/{id}` | Read a single product |
| `GET /api/catalog/v1/items/{id}?lang=vi` | `GET /v1/items/{id}?lang=vi` | Query string is preserved |
| `GET /api/catalog/v1/items/999` | `GET /v1/items/999` | Backend returns Problem Details 404 |

The client does not need to know whether the Catalog service has a `/v1` context path or changes hostname. The Gateway owns the public prefix `/api/catalog`; the backend owns its internal path.

An important rule: **rewrite only once at the Gateway boundary**. Do not let the Gateway strip a prefix, a BFF strip another prefix, and the backend guess the path. Document both the input path and output path explicitly in the route contract.

### 2.2. Header Contract

| Header | Who creates/is trusted? | Policy in this lab |
|---|---|---|
| `X-Correlation-Id` | Client may send; Gateway validates format | Keep if valid, otherwise generate a new UUID; send to backend and return in response |
| `X-User-Id` | Do not trust values sent by public clients | Remove before proxying; identity must come from validated JWT/principal |
| `X-User-Role` | Do not trust values sent by public clients | Remove before proxying; downstream verifies permissions independently |
| `Authorization` | Credential per security contract | Forward/relay only when policy requires; do not log or alter arbitrarily |
| `X-API-Contract` | Gateway-generated | Set to `catalog-v1` so the backend knows which public contract/hop was selected |
| `Forwarded`, `X-Forwarded-*` | Trust only from configured proxy/ingress | Do not trust headers sent by Internet clients; restrict trusted proxies at the infrastructure layer |
| `Cache-Control` | Gateway or backend per response policy | Personalized APIs in the lab are set to `no-store` |

Headers are metadata, not an authentication mechanism. Removing `X-User-Id` does not replace JWT verification; adding `X-API-Contract` does not prove the caller is authorized to access data.

### 2.3. Error Contract

Backend APIs use the same Problem Details structure:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "The requested product does not exist.",
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "lab-request-42"
}
```

Problem Details includes standard members such as `type`, `title`, `status`, `detail`, and `instance` (optional per response); extension fields such as `code` and `correlationId` are added per the API contract. Responses use the media type `application/problem+json`.

HTTP status and error code solve two different concerns:

- HTTP status helps clients, proxies, and caches understand the outcome category.
- `code` lets clients handle business logic reliably without parsing the `detail` sentence.

Never use exception class names, internal hostnames, stack traces, or database messages as public error codes.

## 3. Normalizing Paths with RewritePath

### 3.1. Creating the Catalog Route

In Gateway Server WebFlux 5.0, route properties live under the `spring.cloud.gateway.server.webflux` namespace. Local configuration:

```yaml
server:
  port: 8080

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
```

For the request `/api/catalog/v1/items/42?lang=vi`, the `RewritePath` regex captures the remainder as `v1/items/42`, then changes the path to `/v1/items/42`. The query string `?lang=vi` is preserved. The backend at `localhost:8081` receives the request.

### 3.2. Why Escape the Replacement in YAML?

The Gateway uses a regex replacement expression. In YAML configuration, the `/$\{remaining}` form is used so Spring's property placeholder resolver does not mistakenly process a dollar-brace property placeholder string before the filter receives the regex replacement. When writing in the Java DSL, the replacement syntax may differ from the YAML escaping.

### 3.3. When to Use StripPrefix vs. RewritePath?

| Filter | When appropriate | Example |
|---|---|---|
| `StripPrefix=2` | Only need to drop the first N path segments | `/api/catalog/v1/items/42` → `/v1/items/42` |
| `PrefixPath=/internal` | Backend needs a fixed prefix prepended | `/items/42` → `/internal/items/42` |
| `SetPath=/v1/items/{id}` | Target path has a simple structure and captured parameters | Transform path from template |
| `RewritePath` | Need regex, prefix replacement, or keeping remaining path | `/api/catalog/**` → `/**` |

Choose the most readable filter for the rule at hand. Do not stack multiple rewrite filters if a single filter can express the mapping.

### 3.4. Path Edge Cases to Test

- Trailing slash: `/api/catalog/v1/items/42/`.
- Query string: `/api/catalog/v1/items/42?lang=vi&page=2`.
- Missing path portion after prefix: `/api/catalog/`.
- Similar but invalid prefix: `/api/catalogue/v1/items/42`.
- Path containing percent-encoded segments or encoded slashes.
- Path with unusual dot segments or consecutive slashes.

Do not arbitrarily decode `%2F`, normalize slashes, or strip `..` with ad-hoc string replacements. Path normalization must be consistent across the ingress, Gateway, and backend to prevent path traversal, route bypass, or two layers interpreting the same URL differently. For encoded slashes/ambiguous paths, choose a clear rejection policy and test it on the exact HTTP server/proxy stack.

## 4. Normalizing Request Headers

### 4.1. Removing Untrusted Identity Headers

Public clients can send any custom header:

```http
GET /api/catalog/v1/items/42 HTTP/1.1
Host: api.example.test
X-User-Id: administrator
X-User-Role: SUPER_ADMIN
```

If the backend directly trusts these two headers, a client can claim someone else's privileges. The route must remove them:

```yaml
filters:
  - RemoveRequestHeader=X-User-Id
  - RemoveRequestHeader=X-User-Role
```

If the system needs user context, validate JWT/OAuth2 at the Gateway and use principal/token relay or token exchange according to the security contract. Downstream must still verify signature, issuer, audience, scope, and resource/tenant permissions. Do not replace authentication with a Gateway-added header that lacks integrity protection.

### 4.2. Setting Gateway-Owned Internal Metadata

Example:

```yaml
filters:
  - SetRequestHeader=X-API-Contract, catalog-v1
```

`SetRequestHeader` overwrites any value sent by the client (if present), whereas `AddRequestHeader` can append an extra value. For headers that require a single canonical value, prefer `SetRequestHeader`.

Do not treat this metadata header as a secret or authorization grant. If downstream needs to verify that a request came from the Gateway, use mTLS, workload identity, or a token with an appropriate audience.

### 4.3. Do Not Arbitrarily Modify Authorization and Forwarded Headers

- Do not remove `Authorization` if downstream needs to validate the bearer token itself and no replacement mechanism is in place.
- Do not log tokens, cookies, or API keys.
- Do not trust `X-Forwarded-For`, `X-Forwarded-Host`, or `X-Forwarded-Proto` from Internet clients.
- Accept forwarded metadata only from ingress/proxies inside the trust boundary, and configure trusted proxies at the appropriate layer.
- Do not forward hop-by-hop headers such as `Connection`, `Keep-Alive`, `Transfer-Encoding`, or `Upgrade` using ordinary header filters; the HTTP proxy handles them according to transport semantics.

If both the ingress and Gateway add `X-Forwarded-*`, inspect the proxy chain and trust order. A wrong client IP address can break IP-based rate limiting, auditing, and access control.

### 4.4. Correlation ID: Validate, Generate, and Return

The Gateway should provide an ID to link access logs, backend logs, and traces. Use a `GlobalFilter` for matched routes:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class CorrelationIdGlobalFilter implements GlobalFilter, Ordered {

    public static final String HEADER = "X-Correlation-Id";
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        String supplied = exchange.getRequest()
            .getHeaders().getFirst(HEADER);

        String correlationId =
            supplied != null && SAFE_ID.matcher(supplied).matches()
                ? supplied
                : UUID.randomUUID().toString();

        ServerHttpRequest request = exchange.getRequest().mutate()
            .headers(headers -> headers.set(HEADER, correlationId))
            .build();

        ServerWebExchange mutated = exchange.mutate()
            .request(request)
            .build();

        mutated.getResponse().beforeCommit(() -> {
            mutated.getResponse().getHeaders()
                .set(HEADER, correlationId);
            return Mono.empty();
        });

        return chain.filter(mutated);
    }
}
```

**Explanation:**

1. Keeps a correlation ID only if it has 1–64 characters from the ASCII allowlist; any other value is replaced with a UUID.
2. `headers.set(...)` ensures downstream receives a single value even if the client sends duplicate headers.
3. `beforeCommit` adds the same ID to the response before headers are sent.
4. The ID is strictly for correlation; do not use it for authentication, authorization, or tenant identity.
5. `GlobalFilter` runs only after the Gateway has selected a route. Unmatched requests may not pass through this filter; if you need a correlation ID on every request—including pre-routing 404s—place the logic in a WebFlux `WebFilter` or at the ingress layer.

If Micrometer Tracing already generates trace/span IDs, continue using W3C Trace Context for distributed tracing. `X-Correlation-Id` is a supplementary business/investigation ID, not a replacement for `traceparent`.

## 5. Normalizing Response Headers

### 5.1. Setting Headers According to API Policy

For APIs containing per-user/tenant data, the lab sets:

```yaml
filters:
  - SetResponseHeader=Cache-Control, no-store
  - SetResponseHeader=X-Content-Type-Options, nosniff
  - RemoveResponseHeader=Server
  - RemoveResponseHeader=X-Powered-By
```

- `Cache-Control: no-store` prevents caches from storing personalized responses per the lab's policy. Public catalog data may have a different cache policy; do not apply `no-store` to every route if it degrades performance unnecessarily.
- `X-Content-Type-Options: nosniff` prevents browsers from MIME-sniffing.
- `Server` and `X-Powered-By` are removed to reduce stack details in responses; this is metadata hygiene only and does not replace hardening.

`SetResponseHeader` sets a canonical value, whereas `AddResponseHeader` can append an additional value. For single-valued headers like `Cache-Control` in this policy, avoid adding multiple values.

### 5.2. CORS Must Have Only One Owner

If both the Gateway and Catalog configure CORS, the response may contain two `Access-Control-Allow-Origin` or two `Access-Control-Allow-Credentials` headers. Choose a single layer as the CORS owner. If you must deduplicate headers from a legacy backend:

```yaml
filters:
  - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin RETAIN_FIRST
```

The `RETAIN_FIRST` policy only handles duplicate headers; it does not fix an incorrect allow-origin or make wildcard-with-credentials valid. Origin allowlists, credentials, and preflight handling must be verified separately.

### 5.3. Do Not Blindly Overwrite Backend Security Headers

Before using `SetResponseHeader`, determine whether a header belongs to the Gateway or the service:

- The Gateway may own `Cache-Control` at the public API boundary.
- The service owns `ETag`, `Last-Modified`, and resource-level cache semantics if the Gateway does not alter the representation.
- CORS needs a single owner.
- `Content-Type`, `Content-Length`, `Content-Encoding`, and body-related headers should not be altered by a generic filter unless the body is transformed accordingly.
- Do not remove `WWW-Authenticate` if clients need the challenge to authenticate.

When modifying response bodies, you must account for content length, encoding, streaming, range headers, and signatures; this practice lab does not transform the response body of successful API calls.

## 6. Standardizing Error Codes with Problem Details

### 6.1. Why Are Stable Error Codes Needed?

Suppose Catalog returns:

```json
{"error":"item missing","message":"No row for id 999"}
```

Pricing returns:

```json
{"status":"NOT_FOUND","description":"offer absent"}
```

Inventory returns:

```json
{"errorCode":"404-INV","detail":"No inventory record"}
```

Clients have to understand three different schemas and may become coupled to wording. Instead, each service should map domain errors to a shared contract, for example:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "The requested product does not exist.",
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "lab-request-42"
}
```

### 6.2. Sample Error Code Table

| HTTP | Error code | Meaning | What the client should do |
|---:|---|---|---|
| 400 | `INVALID_REQUEST` | Invalid query/body/path | Fix input |
| 401 | `AUTHENTICATION_REQUIRED` | Unauthenticated or invalid token | Sign in/refresh token per flow |
| 403 | `ACCESS_DENIED` | Authenticated but lacks permission | Do not retry; check permissions |
| 404 | `PRODUCT_NOT_FOUND` | Resource does not exist | Display not found |
| 409 | `RESOURCE_CONFLICT` | Business state conflict | Refresh state or handle conflict |
| 422 | `VALIDATION_FAILED` | Syntactically valid data violating domain rules | Fix data per field errors |
| 429 | `RATE_LIMITED` | Quota exceeded | Respect `Retry-After` if present |
| 502 | `UPSTREAM_BAD_RESPONSE` | Gateway received an invalid response from upstream | Bounded retry if request is idempotent |
| 503 | `UPSTREAM_UNAVAILABLE` | Dependency unavailable | Backoff; check status |
| 504 | `UPSTREAM_TIMEOUT` | Deadline exceeded | Bounded retry if safe |
| 500 | `INTERNAL_ERROR` | Unexpected error | Send correlation ID to support |

Error codes are part of the API contract; keep them stable across releases. Do not use `detail` as a logic key because wording may be edited or translated.

### 6.3. Domain Exception in the Catalog Service

Define the business exception:

```java
package com.example.catalog.error;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long productId) {
        super("Product " + productId + " does not exist");
    }
}
```

Illustrative controller:

```java
package com.example.catalog.api;

import com.example.catalog.error.ProductNotFoundException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    @GetMapping("/v1/items/{id}")
    public Item getItem(@PathVariable("id") long id) {
        if (id == 999) {
            throw new ProductNotFoundException(id);
        }
        return new Item(id, "Wireless Headphones");
    }

    public record Item(long id, String name) {}
}
```

The `id == 999` condition simply creates a deterministic case for the lab. In a real application, the repository/service layer throws the exception when the resource is not found.

### 6.4. Mapping Exceptions to ProblemDetail

In the Catalog WebFlux service:

```java
package com.example.catalog.error;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

@RestControllerAdvice
public class CatalogProblemHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> productNotFound(
            ProductNotFoundException exception,
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested product does not exist.");

        problem.setType(URI.create(
            "https://api.example.test/problems/product-not-found"));
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        String correlationId = exchange.getRequest()
            .getHeaders().getFirst("X-Correlation-Id");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

**Note:** this is a handler for a specific domain exception. Validation, authentication, and system errors need corresponding handlers/mappings. Do not create an `@ExceptionHandler(Exception.class)` that returns full exception messages to clients; if you need a catch-all, log the exception internally in a controlled way and return a generic `INTERNAL_ERROR`.

### 6.5. The Gateway Should Not Rewrite Every Upstream Error Body

A standard Gateway proxy preserves the upstream status and body. This behavior is helpful when the backend already follows Problem Details. Avoid writing a global body rewrite to convert every 4xx/5xx into a new schema because:

- It can lose domain error codes that clients depend on.
- It can corrupt `Content-Length`, `Content-Encoding`, and `Content-Type`.
- Streaming bodies or large responses may be buffered unexpectedly.
- Business 404 errors are different from 404 errors caused by no matching route.

Standardize the error contract inside each service or in a BFF/adapter that owns the public contract. The Gateway should only generate structured fallbacks with clear error codes for infrastructure errors it directly handles.
## 7. Structured Fallback When Upstream Is Unavailable

### 7.1. Adding a CircuitBreaker to the Route

So the Gateway returns a consistent error when Catalog times out or cannot be reached, add the Spring Cloud CircuitBreaker Reactor Resilience4j dependency. Example route:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-User-Role
                - SetRequestHeader=X-API-Contract, catalog-v1
                - name: CircuitBreaker
                  args:
                    name: catalogCircuit
                    fallbackUri: forward:/_internal/fallback/catalog
                    statusCodes:
                      - "500"
                      - "502"
                      - "503"
                      - "504"
```

`statusCodes` specifies which upstream HTTP statuses count as circuit breaker failures. Timeouts/connection errors can also route to the fallback. Tuning sliding window, minimum calls, wait duration, and permitted calls in the half-open state must be based on real traffic/latency; do not copy one default threshold to every service.

### 7.2. Fallback Handler Returning ProblemDetail

In the Gateway app:

```java
package com.example.gateway.fallback;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/_internal/fallback/catalog")
    public ResponseEntity<ProblemDetail> catalogUnavailable(
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog service is temporarily unavailable.");
        problem.setType(URI.create(
            "https://api.example.test/problems/upstream-unavailable"));
        problem.setTitle("Upstream service unavailable");
        problem.setProperty("code", "CATALOG_UNAVAILABLE");

        String correlationId = exchange.getRequest()
            .getHeaders().getFirst("X-Correlation-Id");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

The `/_internal/fallback/catalog` path is an internal handler invoked via `forward:`. In production, configure Spring Security so clients cannot call this path directly (deny direct requests), while verifying that internal forwarding still works. Never treat an obscure URL as a security measure.

This fallback represents **the entire Catalog upstream being unavailable**, so it returns 503. It is not a fallback for a nonexistent product; 404 `PRODUCT_NOT_FOUND` is still returned by the Catalog service and proxied untouched by the Gateway.

### 7.3. Distinguishing Three Error Sources

| Source | Example | Error contract |
|---|---|---|
| Domain service | Catalog cannot find item | 404 `PRODUCT_NOT_FOUND` |
| Gateway resilience | Catalog refuses connection/times out or returns breaker-caught 5xx | 503 `CATALOG_UNAVAILABLE` |
| Gateway routing | No route matches the URL | Default Gateway 404 or separate custom error handler |

Do not collapse nonexistent-route errors into `PRODUCT_NOT_FOUND`; one means the public URL is not configured, while the other means the domain resource does not exist. If all Gateway-generated errors (404 no route, 429 limiter, 401/403 security) must follow Problem Details, standardize them at each corresponding error boundary; a route's fallback cannot catch errors occurring before a route is selected.

## 8. Complete Gateway Lab Configuration

Combine the route, request/response headers, and fallback:

```yaml
server:
  port: 8080

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-User-Role
                - SetRequestHeader=X-API-Contract, catalog-v1
                - SetResponseHeader=Cache-Control, no-store
                - SetResponseHeader=X-Content-Type-Options, nosniff
                - RemoveResponseHeader=Server
                - RemoveResponseHeader=X-Powered-By
                - name: CircuitBreaker
                  args:
                    name: catalogCircuit
                    fallbackUri: forward:/_internal/fallback/catalog
                    statusCodes:
                      - "500"
                      - "502"
                      - "503"
                      - "504"
```

With service discovery, replace `uri: http://localhost:8081` with `uri: lb://catalog-service` and add Spring Cloud LoadBalancer along with the corresponding discovery client. Do not use `lb://` without configuring an instance lookup mechanism.

In a real project, keep filters within a reviewed route contract; if multiple routes share the same policies, move common filters into `default-filters` or a custom filter. Do not create broadly applied `default-filters` if some routes have different cache/header semantics.

## 9. Running the Lab and Testing with curl

### 9.1. Starting Both Applications

Run the Catalog service on port `8081` and the Gateway on port `8080`. Ensure the Gateway has:

- The Spring Cloud Gateway Server WebFlux starter.
- Spring Cloud CircuitBreaker Reactor Resilience4j if using the fallback.
- Versions managed by a compatible Spring Boot/Spring Cloud BOM.

Example Maven dependencies for the Gateway (versions managed by BOM):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

The lab Catalog service only needs `spring-boot-starter-webflux` for reactive controllers; add Spring Security if the backend validates bearer tokens itself. Do not pin individual versions when the project already uses a compatible Spring Boot/Spring Cloud BOM.

The two security starters in the Gateway example support the OAuth2 configuration in section 10. If running only the local lab without an identity provider, you can omit those two dependencies and `GatewaySecurityConfiguration` for now; enable them once a test issuer/JWK is configured.

Example `application.yml` for the Catalog service:

```yaml
server:
  port: 8081
spring:
  application:
    name: catalog-service
```

The Catalog service needs the WebFlux starter and the controller/exception handler from section 6. In a lab environment, authentication can be omitted to focus on testing rewrites/headers/error contracts; production requires real authentication and authorization.

### 9.2. Successful Request: Checking Path, Query, and Headers

```bash
curl -i \
  -H "X-Correlation-Id: lab-request-42" \
  -H "X-User-Id: administrator" \
  -H "X-User-Role: SUPER_ADMIN" \
  "http://localhost:8080/api/catalog/v1/items/42?lang=vi"
```

Items to verify:

- Backend logs path `/v1/items/42`, not `/api/catalog/v1/items/42`.
- Backend receives query `lang=vi`.
- Backend receives `X-Correlation-Id: lab-request-42`.
- Backend does not receive `X-User-Id` or `X-User-Role`.
- Backend receives `X-API-Contract: catalog-v1`.
- Response contains `X-Correlation-Id`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`.

If the request path is not rewritten, check the route predicate, regex capture group, and replacement escaping. If the backend receives a spoofed identity header, check that the route has the right `RemoveRequestHeader` filter and no other route matched earlier.

### 9.3. Invalid Correlation ID

```bash
curl -i \
  -H "X-Correlation-Id: bad value with spaces" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

The Gateway must generate a new UUID; the response and backend logs use the same new ID. Do not assert a fixed UUID; only verify the header is present, matches the format, and matches across logs/request/response.

### 9.4. Domain Error: Product Not Found

```bash
curl -i \
  -H "X-Correlation-Id: lab-not-found-999" \
  "http://localhost:8080/api/catalog/v1/items/999"
```

Expected results:

- HTTP 404.
- `Content-Type: application/problem+json`.
- Body contains `type`, `title`, `status=404`, `code=PRODUCT_NOT_FOUND`.
- `correlationId` matches `lab-not-found-999`.
- Gateway does not turn 404 into 503.

### 9.5. Upstream Unavailable: Testing the Fallback

In an authorized local environment, stop the Catalog service or cause the upstream connection to fail, then send:

```bash
curl -i \
  -H "X-Correlation-Id: lab-catalog-down" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

When the CircuitBreaker opens or catches a connection/timeout error, the expected fallback response is HTTP 503, `Content-Type: application/problem+json`, `code=CATALOG_UNAVAILABLE`, and the same correlation ID. Opening the breaker may require enough calls/thresholds per configuration; do not assume a single failed request always opens the circuit.

### 9.6. Unmatched Public Path

```bash
curl -i "http://localhost:8080/api/catalogue/v1/items/42"
```

This request does not match `/api/catalog/**`; the Gateway may return its default 404. This is a routing error, not `PRODUCT_NOT_FOUND`. If the system requires a unified error body for no-route responses, implement a dedicated error boundary and test it independently.

### 9.7. Calling the Backend Directly

```bash
curl -i \
  -H "X-Correlation-Id: direct-backend-test" \
  -H "X-User-Id: administrator" \
  "http://localhost:8081/v1/items/42"
```

This direct request **bypasses the Gateway**, so it may lack standardized headers. In production, the backend needs network policies and service authentication so only authorized workloads can call it; do not rely on clients being "instructed" to go through the Gateway.

## 10. Protecting the Fallback and Verifying the Security Boundary

### 10.1. Blocking Clients From Calling the Fallback Handler Directly

The fallback controller has an internal URL on the same HTTP listener. If a public application does not block this path, clients can call the fallback endpoint directly even when there is no upstream failure. Place a deny rule for internal paths ahead of broader rules:

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain gatewayApiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/_internal/fallback/**").denyAll()
                .pathMatchers("/api/catalog/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Issuer/JWK validation must be configured in the application, for example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/platform
```

`identity.example.test` is only an illustrative hostname. For production, use the real issuer, verify audience, and map scopes/roles per your identity provider. If the Gateway already has a `SecurityWebFilterChain`, integrate the deny rule into the existing chain instead of creating overlapping chains without explicit matchers.

Requests entering `/api/catalog/**` are authenticated first; when CircuitBreaker internally forwards to the fallback handler, the same exchange is processed within the active flow. Integration-test both cases: a client calling `/_internal/fallback/catalog` directly is rejected, while a request to `/api/catalog/...` hitting the fallback returns 503 according to the contract.

### 10.2. Identity Headers Are Not a Principal

In the lab, `X-User-Id` and `X-User-Role` are removed to demonstrate that the Gateway does not trust public headers. When OAuth2 is enabled:

- The Gateway validates the JWT against the issuer/JWK and required checks.
- Route authorization determines whether the caller has the scope to read Catalog.
- If downstream needs identity, use token relay/token exchange or service identity with an appropriate audience.
- Downstream still validates the token and resource/tenant permissions.

Do not add `SetRequestHeader=X-User-Role, ADMIN` to pass privileges to the backend. A header set by the Gateway carries no signature and does not prove the user was granted that role.

### 10.3. Limiting the Surface of Header Spoofing

`X-User-Id` and `X-User-Role` are not the only headers that can be spoofed. Build an inventory of headers that downstream trusts:

| Header group | Examples | How to handle |
|---|---|---|
| Identity | `X-User-Id`, `X-Role`, `X-Tenant-Id` | Strip from public input; regenerate from authenticated identity if contract requires |
| Client IP | `X-Forwarded-For`, `Forwarded` | Trust the proper proxy chain; do not treat raw client headers as IP |
| Internal routing | `X-Internal-Service`, `X-Region` | Created only by trusted infrastructure; enforce allowlist |
| Correlation | `X-Correlation-Id` | Validate charset/length; never use for authorization |
| Content metadata | `Content-Type`, `Accept`, `Content-Encoding` | Validate per endpoint/body; do not modify arbitrarily |
| Credential | `Authorization`, cookies, API keys | Forward only per security contract; redact logs |

Do not strip all `X-*` headers indiscriminately if the application relies on valid headers like correlation, idempotency, or tracing. Policy must be based on inventory and ownership.

## 11. End-to-End Test Matrix

The tests below use the local Gateway and Catalog mock/service. Results represent acceptance criteria for the lab, not test runs executed against a specific project.

| ID | Request/Condition | Result to verify |
|---|---|---|
| T01 | `GET /api/catalog/v1/items/42` | Backend receives `/v1/items/42` |
| T02 | Request has `?lang=vi&page=2` | Query string is preserved |
| T03 | `GET /api/catalogue/v1/items/42` | Does not match the Catalog route |
| T04 | `GET /api/catalog/` | Does not generate an out-of-contract backend path; returns appropriate route/backend error |
| T05 | Path with trailing slash | Trailing slash behavior is documented and consistent |
| T06 | Path with `%2F` | Rejected or handled per defined policy; no route bypass |
| T07 | Client sends `X-User-Id: administrator` | Backend does not receive this header |
| T08 | Client sends `X-User-Role: SUPER_ADMIN` | Backend does not receive this header |
| T09 | Client sends `X-API-Contract: attacker` | Backend receives Gateway-set value `catalog-v1` |
| T10 | Client sends valid correlation ID | Request and response use the same ID |
| T11 | Client sends correlation ID with spaces/disallowed chars | Gateway replaces with a safe UUID |
| T12 | Client sends duplicate correlation IDs | Backend receives a single canonical value |
| T13 | Normal response | Contains `X-Correlation-Id` and configured policy headers |
| T14 | Catalog throws `ProductNotFoundException` | HTTP 404, `application/problem+json`, `PRODUCT_NOT_FOUND` |
| T15 | Catalog returns HTTP 500 | CircuitBreaker handles per `statusCodes`; fallback 503 when policy triggers |
| T16 | Catalog connection refused | Fallback Problem Details `CATALOG_UNAVAILABLE` |
| T17 | Circuit is OPEN | Request does not call backend; returns stable fallback |
| T18 | Client calls fallback path directly | Rejected by Spring Security |
| T19 | Public path matches no route | Routing 404 is distinguished from domain 404 |
| T20 | Backend returns duplicate CORS headers | CORS owner/dedupe policy works properly |
| T21 | Personalized API returns response | `Cache-Control: no-store` per route policy |
| T22 | Response includes `Server`/`X-Powered-By` | Headers removed if policy requires |
| T23 | Downstream needs bearer token | `Authorization` is relayed per security contract, not stripped unintentionally |
| T24 | Request via trusted ingress | Forwarded metadata reflects configured proxy chain |
| T25 | Direct request to backend from untrusted network | Rejected by network/service authentication policy |
| T26 | Send POST to GET-only path | Does not match GET route; does not rewrite to another endpoint |
| T27 | Catalog 404 | Not converted by CircuitBreaker into `CATALOG_UNAVAILABLE` |
| T28 | Fallback response | Has status 503, `code`, `type`, correlation ID, and no stack trace |
| T29 | Unmatched request with app-wide correlation requirement | WebFilter/ingress handles correlation since GlobalFilter does not run before route selection |
| T30 | Both Gateway and backend configure CORS | Only one layer owns CORS or headers are deduplicated per policy |

### 11.1. Testing Status and Body with curl

For domain 404:

```bash
curl -sS -D - \
  -H "X-Correlation-Id: lab-not-found-999" \
  "http://localhost:8080/api/catalog/v1/items/999"
```

Check status 404, the Problem Details media type, and that the body contains `PRODUCT_NOT_FOUND`. Do not check only `detail`, since descriptive wording may change by language.

For fallback:

```bash
curl -sS -D - \
  -H "X-Correlation-Id: lab-catalog-down" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

Check 503 and `CATALOG_UNAVAILABLE`. If the circuit has not yet met the threshold to OPEN, requests may still reflect the upstream error depending on configuration; distinguish per-call fallback from circuit state.

### 11.2. Testing Header Spoofing

Send a request with both valid and spoofed headers:

```bash
curl -i \
  -H "X-Correlation-Id: lab-header-check" \
  -H "X-User-Id: root" \
  -H "X-User-Role: ADMIN" \
  -H "X-API-Contract: forged" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

At the backend, observe the received headers:

- `X-Correlation-Id` equals `lab-header-check`.
- `X-User-Id` and `X-User-Role` are absent.
- `X-API-Contract` equals `catalog-v1`.

Do not conclude safety solely from the Catalog response body if the backend does not echo headers. Use redacted debug logs or an echo endpoint that exists only in the lab profile and is never exposed in production.

## 12. Troubleshooting

| Symptom | Possible cause | How to verify/fix |
|---|---|---|
| Gateway returns 404 while Catalog is running | Path predicate does not match | Check prefix, slashes, and route ID |
| Backend receives original /api/catalog/... | Rewrite filter not applied or another route matched | Check route predicates/order and regex |
| Backend receives /items/42 instead of /v1/items/42 | Stripped/rewritten too much | Use only a single path transformation |
| Backend receives path / | Request contains only prefix or empty capture group | Reject paths missing the resource portion per contract |
| Query string lost | Custom path/body handler builds URI incorrectly | Check rewrite filter; avoid rebuilding URI unnecessarily |
| Regex does not substitute capture group | Wrong replacement escaping or named group | Check named group `remaining` and dollar-brace escaping in YAML |
| Client spoofs X-User-Role and backend still sees it | Missing RemoveRequestHeader, another route matched, or header re-added | Check combined filter chain and proxies before/after Gateway |
| Backend loses Authorization | Filter or security config stripped the token | Strip only if downstream uses a replacement identity mechanism |
| Backend receives two correlation IDs | Used Add instead of Set, or proxy added another header | Use `headers.set` and inspect all hops |
| Correlation ID missing on 404 no-route | GlobalFilter did not run because no route matched | Use WebFilter or ingress for all requests |
| Correlation ID missing in error response | Error handler ran outside filter path or response already committed | Test each error boundary; add ID in WebFilter/ProblemDetail handler |
| Gateway fallback path callable directly by client | Internal path not denied | Add Spring Security rule and test direct calls |
| Backend 404 converted to 503 | CircuitBreaker statusCodes misconfigured or fallback too broad | Include only statuses that are actual upstream failures |
| Backend 500 still returned directly as 500 | Status not added to breaker or filter/dependency inactive | Check CircuitBreaker dependency, route config, and breaker events |
| Single failed request did not trigger circuit-open fallback | Circuit threshold/minimum calls not yet reached | Distinguish fallback-on-call from OPEN state |
| application/problem+json changed to application/json | Handler/codec/content negotiation did not set proper content type | Set `MediaType.APPLICATION_PROBLEM_JSON` |
| Error body contains stack trace | Catch-all handler returned raw exception | Return generic detail and log exception internally |
| Client text error parsing fails after language change | Client coupled to detail | Rely on stable error code |
| CORS reports duplicate allow-origin | Both Gateway and backend own CORS | Choose one owner or dedupe after reviewing policy |
| Browser cache keeps private responses | Inappropriate cache policy | Set Cache-Control per resource/identity; do not apply no-store blindly |
| Server header still appears | Proxy/ingress added header after Gateway | Inspect response across each hop; remove at the outermost edge |
| Wrong client IP | Trusted forwarded header from untrusted source | Configure trusted proxy chain and network boundary |
| Direct backend request succeeds from Internet | Backend is public or firewall is open | Enforce private service/network policy and service auth |
| CircuitBreaker fallback cannot find handler | Wrong forward path or handler not component-scanned | Check package scan and URL mapping |
| Security deny on fallback also blocks internal forward | Security chain/dispatch behavior differs from expectation | Integration-test forward on actual version; design appropriate internal fallback handler/route |

## 13. Pre-Production Standardization Checklist

### 13.1. Path Contract

- [ ] Maintain a public path → internal path mapping table for every route.
- [ ] Only one layer owns path rewriting.
- [ ] Query parameters are preserved or transformed per contract.
- [ ] Route predicates do not unintentionally match similar prefixes.
- [ ] Policy exists for trailing slashes, encoded slashes, duplicate slashes, and dot segments.
- [ ] Do not rewrite paths using client-supplied header values.
- [ ] Route order and route IDs are reviewed so broad routes do not shadow specific routes.

### 13.2. Request/Response Headers

- [ ] Inventory all identity headers trusted by backends.
- [ ] Strip client-supplied identity headers before proxying.
- [ ] Relay Authorization only per security contract and appropriate audience/scope.
- [ ] Correlation ID has length/charset constraints and is applied using set.
- [ ] Correlation ID is never used for authorization or tenant identity.
- [ ] Forwarded headers are trusted only from proxies/ingress inside the trust boundary.
- [ ] Response headers have a single clear owner for CORS, caching, and security policies.
- [ ] Do not modify Content-Length/Encoding/Type unless the body is transformed accordingly.
- [ ] Do not log tokens, cookies, API keys, or sensitive bodies.

### 13.3. Error Contract

- [ ] Error responses use `application/problem+json` per RFC 9457.
- [ ] Include appropriate type, title, status, detail; and instance if required by contract.
- [ ] Provide a stable error code for clients.
- [ ] Distinguish domain 404 from routing 404 and upstream unavailable.
- [ ] Never return raw exceptions, internal hostnames, or stack traces.
- [ ] Gateway fallback catches only defined failures and does not mask business errors.
- [ ] CircuitBreaker statusCodes include only upstream statuses considered failures.
- [ ] Direct access to the fallback handler is denied.

### 13.4. Operations

- [ ] Metrics exist per route/status and circuit breaker state.
- [ ] Logs include correlation ID to link Gateway and backend.
- [ ] Distributed tracing uses trace context; do not replace it with a custom correlation ID.
- [ ] Tests cover route matching, rewrites, header spoofing, Problem Details, and fallback.
- [ ] Backend is not directly public or enforces service authentication/network policies.
- [ ] Spring Boot/Spring Cloud versions are managed by a compatible BOM.
- [ ] Rollback plan exists if rewrite/header contract breaks legacy clients.

## 14. Exercises and Self-Check Questions

**Exercise 1 — Path mapping.** Client calls `/api/catalog/v1/items/42`; backend only accepts `/v1/items/42`. Write the appropriate route predicate and `RewritePath`.

**Exercise 2 — StripPrefix.** When is `StripPrefix=2` more readable than `RewritePath`? Give one case where regex is a better fit.

**Exercise 3 — Query string.** Why should normal path rewriting not drop `?lang=vi&page=2`?

**Exercise 4 — Prefix collision.** Why must `/api/catalogue/...` not match the `/api/catalog/**` route? How would you test that?

**Exercise 5 — Encoded slash.** What is the risk when ingress, Gateway, and backend decode `%2F` differently?

**Exercise 6 — Header spoofing.** Why can `X-User-Role: ADMIN` sent by a client never be used for authorization?

**Exercise 7 — Remove vs Set.** Distinguish `RemoveRequestHeader`, `SetRequestHeader`, and `AddRequestHeader`.

**Exercise 8 — Authorization.** Why shouldn't `Authorization` be stripped on every route via a default filter?

**Exercise 9 — Correlation ID.** Why must client-supplied IDs be validated for length/charset? Why is an ID not an identity?

**Exercise 10 — GlobalFilter.** Why might a `GlobalFilter` not run when the Gateway finds no matching route?

**Exercise 11 — WebFilter.** When should you use a `WebFilter` instead of a `GlobalFilter` to generate a correlation ID?

**Exercise 12 — Forwarded headers.** Why should `X-Forwarded-For` never be trusted directly from Internet clients?

**Exercise 13 — Response headers.** Why is `SetResponseHeader` preferred over `AddResponseHeader` for headers requiring a single canonical value?

**Exercise 14 — CORS.** What problem can occur when both Gateway and backend add `Access-Control-Allow-Origin`? How do you handle it?

**Exercise 15 — Cache.** Why is `Cache-Control: no-store` not necessarily suitable for every public catalog response?

**Exercise 16 — Problem Details.** Distinguish HTTP status from the error code in the body.

**Exercise 17 — Domain 404.** Why should `PRODUCT_NOT_FOUND` not be converted into `CATALOG_UNAVAILABLE`?

**Exercise 18 — Fallback.** When should the route's CircuitBreaker return `CATALOG_UNAVAILABLE`? Why does a fallback not replace domain error handlers?

**Exercise 19 — No-route.** Why cannot a route fallback standardize 404s occurring before the Gateway selects a route?

**Exercise 20 — Security.** Why must the internal fallback endpoint deny direct access even if its URL starts with `/_internal/`?

**Exercise 21 — Body rewrite.** Name three risks when a Gateway global filter buffers and rewrites every upstream error body.

**Exercise 22 — Observability.** How do a Correlation ID and W3C trace context differ?

**Exercise 23 — Service-to-service.** If a backend needs user identity, should you use custom headers or token relay/token exchange? What conditions must be checked?

**Exercise 24 — Production test.** List the layers that must be verified beyond a curl to localhost: ingress, network, direct backend, identity, and all instances.

### Suggested Answers

1. `Path=/api/catalog/v1/items/**` and `RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}`; verify the backend receives `/v1/items/42`.
2. `StripPrefix=2` when simply dropping two segments; `RewritePath` when regex or complex prefix restructuring is needed.
3. Query parameters are part of the request target that the backend may need for locale/pagination/filtering; losing them alters semantics.
4. Route prefixes must match the exact path contract; send `/api/catalogue/...` and confirm it does not reach the Catalog backend.
5. Can enable path traversal or authorization bypass if layers interpret URLs differently; define a reject/normalize policy and test end-to-end.
6. Clients can set headers themselves; authorization must rely on a verified principal/token and resource policies.
7. Remove deletes the header; Set overwrites to keep a single value; Add appends a value and can create duplicate headers.
8. Some downstream services need to verify bearer tokens themselves; stripping the token breaks auth or pushes teams toward unsafe headers.
9. Constraints prevent oversized/malformed headers and log injection; correlation only links logs and does not prove identity or permissions.
10. `GlobalFilter` runs after route selection, so no-route requests never enter a route's filter chain.
11. When a correlation ID is needed for all requests including pre-routing no-route/404s, use a `WebFilter` or ingress.
12. Clients can spoof IPs; trust only values appended by proxies inside the configured trust boundary.
13. Set replaces the old value; Add can create multiple values causing client/server interpretation mismatches.
14. Can produce duplicate headers causing browsers to reject CORS; pick a single owning layer or dedupe after verifying policy.
15. Public catalog data can be safely cached with ETag/TTL; `no-store` can reduce cache hits and increase load.
16. HTTP status describes the response category at transport level; error code is a stable identifier for client logic.
17. 404 is an intentional domain outcome; 503 means a dependency is unavailable. Merging them causes clients to retry or render messages incorrectly.
18. On upstream timeout/connection errors or configured failure 5xx statuses; domain 404 still passes through as a business response.
19. The CircuitBreaker filter only runs after a route matches; no-route happens before that filter runs.
20. An internal URL is still an HTTP handler on the listener; without deny rules, clients can call it directly and receive fallback responses.
21. May lose domain error codes, break content-length/encoding/content-type, and buffer large/streaming responses causing memory spikes.
22. Correlation ID is an application ID for linking logs; trace context carries W3C-standard trace/span relationships and instrumentation.
23. Use service identity or token relay/token exchange with proper audience/scope; downstream must validate tokens and resource permissions.
24. Verify ingress/public paths, network policies/firewalls, direct backend access, JWT/service identity, route configs, and all Gateway instances.

## Official References

- [Spring Cloud Gateway Server WebFlux 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html) — route matching, filter chain, and request proxying.
- [Spring Cloud Gateway Server WebFlux 5.0 — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html) — RewritePath, request/response header filters, and CircuitBreaker.
- [Spring Framework — Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux, WebFilter, ServerWebExchange, and reactive handlers.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html) — ProblemDetail, ErrorResponse, and exception advice.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — SecurityWebFilterChain and request authorization.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — issuer/JWK validation and JWT authorities.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — standard error representation and extension members.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — traceparent and propagation across services.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — request target, status codes, and header semantics.
