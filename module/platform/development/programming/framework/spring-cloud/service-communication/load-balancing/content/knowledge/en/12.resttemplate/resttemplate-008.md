# Interceptors for Authentication, Logging, and Context Propagation

In **Spring Cloud LoadBalancer**, an application calls a service via a service ID like `inventory-service`, and LoadBalancer picks a concrete `ServiceInstance` from discovery. When using `RestTemplate`, cross-cutting concerns such as service authentication, logging, and correlation ID propagation can be implemented in `ClientHttpRequestInterceptor`. This keeps business code from duplicating token attachment, timing, and request context forwarding on every endpoint.

Three responsibilities should stay separated:

- **LoadBalancer**: selects a target from the instance list by service ID, optionally combining health checks, zones, hints, and retries.
- **Security interceptor**: picks the right credentials and attaches the authorization header only for authorized downstream targets.
- **Context/logging interceptor**: forwards approved request-identification metadata, measures latency, and logs safely.

A regular interceptor must neither choose replica addresses itself nor forward every end-user header downstream. This lesson uses blocking `RestTemplate` with Spring Cloud `@LoadBalanced`, combined with OAuth2 client credentials, MDC, correlation IDs, observability, and failure testing.

## 1. How `ClientHttpRequestInterceptor` Works

Spring Framework defines the interface:

~~~java
public interface ClientHttpRequestInterceptor {
    ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution
    ) throws IOException;
}
~~~

| Component | Meaning |
|---|---|
| `HttpRequest request` | HTTP method, URI, and headers before sending |
| `byte[] body` | Request payload; avoid writing directly to logs |
| `ClientHttpRequestExecution execution` | Next step in the interceptor chain or HTTP transport |
| `ClientHttpResponse` | Returned response so RestTemplate can process status and body |
| `IOException` | I/O-related error; `RuntimeException` can also occur during processing |

Simple example:

~~~java
public final class ClientNameInterceptor
        implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        request.getHeaders().set("X-Client-Name", "order-service");
        return execution.execute(request, body);
    }
}
~~~

The key call is `execution.execute(request, body)`. An interceptor can modify headers before the call and inspect the response afterward, but normally invokes `execute` **once**. Calling it multiple times can cause write operations to execute twice; omitting it blocks the request completely.

The interceptor chain behaves like nested layers:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["RestTemplate"]
    B --> C["CorrelationIdInterceptor"]
    C --> D["InventoryTokenInterceptor"]
    D --> E["OutboundLogInterceptor"]
    E --> F["LoadBalancer integration"]
    F --> G["HTTP transport"]
    G --> H["Inventory replica"]
~~~

The diagram shows one possible ordering. The exact position of `LoadBalancerInterceptor` added by Spring Cloud integration relative to user-registered interceptors may vary by configuration or version. To be certain, inspect `restTemplate.getInterceptors()` once Spring finishes initializing the bean.

For a chain I1 → I2 → I3, the wrapping order is typically `I1.before → I2.before → I3.before → HTTP → I3.after → I2.after → I1.after`. Ordering therefore determines what latency is measured, which errors are caught, and which headers are visible at each layer.

## 2. Load-Balanced RestTemplate vs. Plain RestTemplate

A plain RestTemplate resolves URLs via DNS and the HTTP transport. With a URL like `http://inventory-service/api/items/SKU-01`, the hostname `inventory-service` may not resolve via external DNS.

A `@LoadBalanced` RestTemplate receives Spring Cloud logic that uses the URI host as a service ID:

~~~text
REST request from OrderService:
  http://inventory-service/api/items/SKU-01
                  |
                  v
  LoadBalancer client ID: inventory-service
                  |
                  v
  ServiceInstanceListSupplier / DiscoveryClient
                  |
                  +--- inventory-1 -> http://localhost:8081
                  +--- inventory-2 -> http://localhost:8082
                  |
                  v
  Round Robin / Random selects an instance
                  |
                  v
  HTTP request to the selected replica address
~~~

A `ClientHttpRequestInterceptor` used for authentication or logging does not replace `ServiceInstance` selection. Rewriting the URI to `localhost:8081` manually inside an interceptor can bypass health filtering, retries, and zone-aware routing.

Example dependencies on the caller side (Spring Boot and Spring Cloud versions must be a compatible BOM-managed pair):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
~~~

Spring Security OAuth2 client is used for this service-to-service example; if your architecture uses workload identity, mTLS, or a token-issuing gateway, use the equivalent mechanism mandated by your security architecture.

## 3. Attaching Interceptors to an Inventory-Dedicated RestTemplate

Register the `RestTemplate` bean using the Spring Boot-provided `RestTemplateBuilder`. This preserves configured customizers and instrumentation.

~~~java
package com.example.order.http;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean("inventoryRestTemplate")
    @LoadBalanced
    RestTemplate inventoryRestTemplate(
            RestTemplateBuilder builder,
            CorrelationIdInterceptor correlation,
            InventoryTokenInterceptor authentication,
            OutboundLogInterceptor logging) {

        return builder
                .additionalInterceptors(
                        correlation,
                        authentication,
                        logging
                )
                .build();
    }
}
~~~

In this configuration:

- `@LoadBalanced` marks the RestTemplate that Spring Cloud will integrate with LoadBalancer.
- `additionalInterceptors` appends business interceptors to the builder. Do not confuse this with `setInterceptors`, which can overwrite existing entries.
- The `inventoryRestTemplate` bean serves only inventory calls to avoid sending the wrong token to other services.
- Interceptors should be stateless beans or rely on thread-safe collaborators. Never store `currentUser` or `currentTenant` in mutable fields of a singleton interceptor.
- Once the application is running, avoid mutating `getInterceptors()`/`setInterceptors()` at runtime.

Caller injects using qualifier:

~~~java
package com.example.order.inventory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(
            @Qualifier("inventoryRestTemplate")
            RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public InventoryResponse findBySku(String sku) {
        return restTemplate.getForObject(
                "http://inventory-service/api/items/{sku}",
                InventoryResponse.class,
                sku
        );
    }
}
~~~

`InventoryResponse` is a DTO matching the JSON returned by inventory. If the caller also calls `payment-service`, configure a dedicated RestTemplate or build explicit credential routing; do not share an interceptor that attaches inventory tokens with payment calls by default.

## 4. Authentication Interceptor: Using Tokens for Their Intended Purpose

Never hardcode tokens directly in source code:

~~~java
request.getHeaders().setBearerAuth("TOKEN_HARDCODED");
~~~

In production, tokens must be issued and refreshed per policy, secrets stored securely, and scopes/audiences constrained. When `order-service` calls inventory under the **order application identity**, OAuth2 `client_credentials` is a common choice.

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant A as Authorization Server
    participant L as Spring Cloud LoadBalancer
    participant I as inventory-service

    O->>A: client_credentials when access token is needed
    A-->>O: access token with matching scope
    O->>L: GET http://inventory-service
    L-->>O: select instance
    O->>I: GET /api/items + Bearer token
    I-->>O: Response
~~~

### Spring Security OAuth2 Client Configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: internal-idp
            client-id: order-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          internal-idp:
            token-uri: https://identity.internal/oauth2/token
~~~

`INVENTORY_CLIENT_SECRET` must be injected from the environment or a secret store, never committed to the repository. The `client-id`, `scope`, and token URI above are examples. The authorization server, `inventory-service`, and caller must agree on audience, signature/opaque-token validation, and token policy.

For service calls independent of a user's HTTP servlet request, use `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

~~~java
package com.example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class OutboundSecurityConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, clientService
                );

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### InventoryTokenInterceptor

~~~java
package com.example.order.http;

import java.io.IOException;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public final class InventoryTokenInterceptor
        implements ClientHttpRequestInterceptor {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryTokenInterceptor(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        var authorizeRequest = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-client")
                .principal("order-service")
                .build();

        var authorizedClient = manager.authorize(authorizeRequest);

        if (authorizedClient == null
                || authorizedClient.getAccessToken() == null) {
            throw new IllegalStateException(
                    "Cannot obtain inventory-service access token"
            );
        }

        request.getHeaders().setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()
        );

        return execution.execute(request, body);
    }
}
~~~

The OAuth2 manager can reuse cached authorized clients and request a fresh token when needed. Avoid calling the authorization server manually on every request without reason. `principal("order-service")` in this example represents the client application, **not** an end-user identity.

When the authorization server fails, the interceptor may throw an exception **before** any HTTP request reaches inventory. Separate token-acquisition failures from individual inventory replica failures. Never swallow authentication failures and send an unauthenticated request when the API requires security.

### Token Relay Is Not Client Credentials

If downstream needs **user permissions**, use a controlled token relay or token exchange design: validate audience/scope, delegation rights, and trust policies across services. Never grab the inbound `Authorization` header and copy it to every URL; doing so can leak tokens to unauthorized services.

| Requirement | Typical mechanism |
|---|---|
| Caller acts under its own identity | `client_credentials` or workload identity |
| Downstream requires user permissions | Token relay/exchange with explicit policy |
| Attaching an ID for logging | Correlation/tracing context |
| Identifying tenant/role | Verified identity data; never trust client-supplied headers |

## 5. Propagating Correlation IDs via Servlet Filter and MDC

A correlation ID ties logs for a single request across multiple services. It is neither a credential nor a tracing system's `traceparent`/trace ID. The following example uses `X-Correlation-Id` to propagate a UUID across services in Spring MVC.

### Generating or Validating the ID on Caller Ingress

~~~java
package com.example.order.web;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-Id";
    public static final String MDC_KEY = "correlationId";

    private static final Pattern UUID_PATTERN = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String incoming = request.getHeader(HEADER);
        String correlationId = incoming != null
                && UUID_PATTERN.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        String oldValue = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            if (oldValue == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, oldValue);
            }
        }
    }
}
~~~

At untrusted boundaries, you may choose to **always generate a fresh UUID** rather than trusting client-supplied IDs. The validation in this example reduces header injection and log pollution risks. Because `MDC` is largely backed by `ThreadLocal`, clean it up inside `finally` so reused servlet threads never retain an old request's correlation ID.

### Attaching the ID to Outbound HTTP Requests

~~~java
package com.example.order.http;

import com.example.order.web.CorrelationIdFilter;
import java.io.IOException;
import org.slf4j.MDC;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;

@Component
public final class CorrelationIdInterceptor
        implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        String id = MDC.get(CorrelationIdFilter.MDC_KEY);

        if (id != null && !id.isBlank()) {
            request.getHeaders().set(CorrelationIdFilter.HEADER, id);
        }

        return execution.execute(request, body);
    }
}
~~~

When RestTemplate is invoked **synchronously on the same thread** as the inbound servlet request, the interceptor can read MDC. If business code uses `@Async`, a separate executor, or reactive pipelines, `MDC` does not cross threads automatically; configure proper context propagation or pass context explicitly.

In background jobs without an inbound HTTP request, generate a correlation ID at the job boundary instead of defaulting to an empty ID.

## 6. Propagate Only Trusted Context

Never copy all incoming headers downstream. Headers such as `Authorization`, `Cookie`, `Host`, `Content-Length`, and hop-by-hop headers carry specific semantics and may contain sensitive data or become invalid when forwarded.

For `X-Tenant-Id` or role metadata, verify permissions and origin:

~~~text
HTTP request
  -> authenticate user/service
  -> validate permissions and tenant claim
  -> trusted request context
  -> interceptor copies only allowlisted headers
  -> downstream still performs authentication and authorization
~~~

Never use a client-supplied `X-Tenant-Id` as the basis for granting permissions downstream. When forwarding a tenant to another service, extract the value from an authenticated security context or validated claim, enforce format bounds, and ensure downstream validates authorization independently.

Values like `Accept-Language` or `X-Correlation-Id` can safely propagate on an allowlist once normalized. `traceparent`, by contrast, should be managed by observability instrumentation rather than assembled manually inside an interceptor.


## 7. Logging Requests, Responses, and Latency Without Leaking Data

A logging interceptor should measure duration with `System.nanoTime()` and log only essential fields such as method, target host, status, elapsed time, or exception class. Avoid logging full URIs with query parameters, headers, bearer tokens, request bodies, and response bodies.

~~~java
package com.example.order.http;

import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;

@Component
public final class OutboundLogInterceptor
        implements ClientHttpRequestInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(OutboundLogInterceptor.class);

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        long start = System.nanoTime();
        String host = request.getURI().getHost();
        String method = request.getMethod().name();

        try {
            ClientHttpResponse response =
                    execution.execute(request, body);

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

            log.info(
                    "outbound_http method={} targetHost={} status={} elapsedMs={}",
                    method,
                    host,
                    response.getStatusCode().value(),
                    elapsedMs
            );

            return response;
        } catch (IOException | RuntimeException error) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

            log.warn(
                    "outbound_http_failed method={} targetHost={} errorType={} elapsedMs={}",
                    method,
                    host,
                    error.getClass().getSimpleName(),
                    elapsedMs
            );

            throw error;
        }
    }
}
~~~

This pattern neither reads the response body nor alters the status. After `execution.execute` returns, RestTemplate still needs to read the response stream. If an interceptor consumes `response.getBody()` for logging without re-exposing the stream, JSON decoding downstream may see an empty body or fail. `BufferingClientHttpRequestFactory` can support re-reading bodies in certain cases, but incurs significant memory overhead and should not be enabled unconditionally for large payloads or sensitive data.

### Why Not Log the Raw URI?

A URI can contain `?token=...`, email addresses, phone numbers, or sensitive identifiers. Logging only host and method is a safer baseline. When path details are needed for API analysis, normalize to route templates like `/api/items/{sku}`, control cardinality, and verify data-protection policies.

Even exception messages generated by libraries can include URIs or credentials. The example logs `error.getClass().getSimpleName()` to categorize errors; log stack traces only in sanitized, access-controlled log pipelines.

### Correlation ID in Log Patterns

You can configure your logging pattern or structured logger to include the `correlationId` field from MDC. That links outbound log lines with inbound log lines via the same ID without storing mutable fields inside the interceptor.

Never place access tokens, sensitive tenant IDs, or full request headers into MDC. MDC is a logging utility, not a secure store for credentials.

## 8. Interceptor Ordering Affects Observed Data and Latency

In the `InventoryHttpConfiguration` example, the application-registered order is:

~~~text
CorrelationIdInterceptor
    -> InventoryTokenInterceptor
        -> OutboundLogInterceptor
            -> other integration interceptors / HTTP transport
~~~

When a request is dispatched:

1. The correlation interceptor reads the ID from MDC and adds `X-Correlation-Id`.
2. The authentication interceptor calls the OAuth2 manager to get an access token and attaches `Authorization`.
3. The logging interceptor starts its timer.
4. Remaining interceptors run, including load balancing logic and HTTP transport.
5. The logging interceptor records status/exception and elapsed time.
6. The response or exception unwinds back through the outer two interceptors.

This yields important consequences:

- Because the logging interceptor sits **after** auth, its elapsed time excludes time spent fetching a token from the authorization server.
- To measure total time **including** token acquisition, place timing outside auth or measure at the service method / observation layer.
- Placed before load balancing, `request.getURI().getHost()` still reads `inventory-service`; placed after, it may observe the physical host.
- When Spring Cloud injects additional interceptors at startup, the full chain includes more than just the application's three interceptors.

To inspect the actual runtime chain in a test environment, check it once after `ApplicationContext` startup:

~~~java
for (var interceptor : inventoryRestTemplate.getInterceptors()) {
    System.out.println(interceptor.getClass().getName());
}
~~~

Never run diagnostic code like this on every HTTP request in production. Do not infer active policies solely from interceptor class names; verify with real requests and metrics.

### Do Not Confuse a Logging Interceptor with LoadBalancer Lifecycle

`OutboundLogInterceptor` logs the logical request from its own vantage point. To see the **selected instance** and load-balancing outcomes, use tracing, Spring Cloud LoadBalancer metrics/lifecycle hooks, or backend logs. Seeing a logical URI in logs does not prove LoadBalancer is inactive.

## 9. Retries and Timeouts: One Business Request May Have Multiple Attempts

When `inventory-service` has multiple replicas, Spring Cloud LoadBalancer can be configured to retry eligible failures. RestTemplate, gateways, or resilience libraries can also perform retries.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant R as RestTemplate/Interceptor
    participant L as LoadBalancer Retry
    participant A as Inventory A
    participant B as Inventory B

    O->>R: GET /api/items/SKU-01
    R->>L: Logical call
    L->>A: Attempt 1
    A--xL: Timeout
    Note over L: Retry only if configured and eligible
    L->>B: Attempt 2
    B-->>L: HTTP 200
    L-->>R: Result after retry
    R-->>O: InventoryResponse
~~~

If the logging interceptor sits outside retry logic, it may emit one event per **logical request** with elapsed time spanning multiple attempts. If it sits inside a retry layer, each attempt may be logged separately. Never compare outbound log counts directly against backend access logs without accounting for retry layers.

### Do Not Implement Ad-Hoc Retries Inside an Authentication Interceptor

Avoid writing:

~~~java
try {
    return execution.execute(request, body);
} catch (IOException error) {
    // Do not blindly retry without an explicit retry policy.
    return execution.execute(request, body);
}
~~~

A POST request may have succeeded on the backend before the connection timed out. Resending it can create duplicate orders or payments. Retries belong in a dedicated mechanism with bounded attempts, backoff, deadlines, and proper idempotency keys.

### Timeouts Span Multiple Paths

A single inventory call may accumulate time across:

~~~text
RestTemplate interceptor
   |
   +--- Fetch token from authorization server (if needed)
   |
   +--- LoadBalancer selects instance / discovery (if needed)
   |
   +--- HTTP transport connect timeout
   |
   +--- Wait for inventory response
   |
   +--- Retry/backoff if configured
~~~

`spring.cloud.loadbalancer.service-discovery.timeout` is not the HTTP transport timeout. RestTemplate connect/read timeouts must be configured on the request factory or builder supported by your Spring Boot version. Token-acquisition requests also need their own timeout.

If the business deadline is 2 seconds and the token interceptor takes 1.8 seconds, setting only the inventory read timeout to 2 seconds will not keep total latency under 2 seconds. Design end-to-end deadlines and bound retry layers.

## 10. Distributed Tracing: Avoid Modifying `traceparent` Manually

If the application already uses Spring Boot Actuator, Micrometer Observation, and Micrometer Tracing, a RestTemplate created via Spring-managed `RestTemplateBuilder` receives HTTP client instrumentation automatically. When configured properly, the tracing system manages spans and propagates trace context via standard headers like `traceparent`.

Never fabricate `traceparent` in an interceptor using a UUID or random string. Tracing headers follow strict formatting and parent/span relationships; manual edits break span linkage and corrupt distributed trace trees.

| Metadata | Purpose | Source |
|---|---|---|
| `X-Correlation-Id` | Querying logs for a request/business flow | Application/filter |
| `traceparent` | Linking spans across a distributed trace | Micrometer Tracing/OpenTelemetry instrumentation |
| `Authorization` | Authentication and authorization | OAuth2/workload identity |
| `X-Tenant-Id` | Verified tenant context | Trusted security context |

You can use both correlation ID and trace ID when each serves a distinct purpose. Avoid putting user IDs, tokens, or request paths with identifying parameters into metric tags, as that leaks data and drives high cardinality.

Instantiating `new RestTemplate()` manually bypasses Spring Boot's builder and customizers, which can omit expected instrumentation. That is another reason to build beans through `RestTemplateBuilder`.

## 11. Unit Testing Interceptors Independently of Load Balancing

Unit tests can verify `ClientHttpRequestInterceptor` behavior without starting discovery or an HTTP server. Use `MockClientHttpRequest` and `MockClientHttpResponse` from `spring-test` alongside a stub `ClientHttpRequestExecution`.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.mock.http.client.MockClientHttpRequest;
import org.springframework.mock.http.client.MockClientHttpResponse;

class CorrelationIdInterceptorTest {

    @Test
    void forwardsCorrelationIdFromMdc() throws Exception {
        String id = "e41c139f-8057-4e88-84bc-af4fc1c414a2";
        MDC.put("correlationId", id);

        try {
            var request = new MockClientHttpRequest(
                    HttpMethod.GET,
                    URI.create("http://inventory-service/api/items/42")
            );

            ClientHttpRequestExecution next = (outbound, body) -> {
                assertEquals(
                        id,
                        outbound.getHeaders()
                                .getFirst("X-Correlation-Id")
                );

                return new MockClientHttpResponse(
                        new byte[0],
                        HttpStatus.OK
                );
            };

            var response = new CorrelationIdInterceptor()
                    .intercept(request, new byte[0], next);

            assertEquals(HttpStatus.OK, response.getStatusCode());
        } finally {
            MDC.remove("correlationId");
        }
    }
}
~~~

Add the `CorrelationIdInterceptor` import for your actual package. `spring-boot-starter-test` normally supplies JUnit and `spring-test` for the corresponding Spring Boot project.

Additional tests to include:

- When MDC is absent, the interceptor does not accidentally forward a stale correlation ID.
- When the OAuth2 manager cannot issue a token, the auth interceptor throws an exception and **does not invoke** the transport.
- When a token exists, requests to the intended service receive `Authorization: Bearer ...`, while the token never appears in logs.
- The logging interceptor forwards the body and response unchanged without consuming the stream.
- I/O errors propagate instead of turning into a fake 200 response.
- The RestTemplate dedicated to payment does not contain `InventoryTokenInterceptor`.
- A single call invokes `execution.execute` only once when the interceptor is not responsible for retries.

**Interceptor unit tests do not prove RestTemplate is load-balanced.** Write a separate integration test starting the Spring context, discovery, and two backends to confirm `http://inventory-service` reaches real instances while carrying valid headers.

## 12. Hands-On End-to-End Observation

In a test environment:

1. Run `inventory-service` on ports 8081 and 8082, both registered in discovery under service ID `inventory-service`.
2. Run `order-service` on 8080 with the `@LoadBalanced` RestTemplate and all three interceptors.
3. If testing auth end-to-end, use a test identity provider issuing client-credentials tokens with the proper scope; never hardcode real credentials.
4. Create a demo controller `GET /orders/demo-inventory/{sku}` calling `InventoryClient.findBySku(sku)`.
5. Send requests with a UUID correlation header to trace logs and see which backend handled each call.

In PowerShell:

~~~powershell
$correlationId = [guid]::NewGuid().ToString()
Invoke-RestMethod -Uri "http://localhost:8080/orders/demo-inventory/SKU-01" -Headers @{ "X-Correlation-Id" = $correlationId }
~~~

These endpoints are illustrative and should be implemented in the test app. To measure distribution, send multiple requests and have each backend return `instanceId` or write access logs containing both instance ID and correlation ID.

Check step by step:

- Caller holds the matching correlation ID in MDC and outbound headers.
- Token is issued for the right client registration and never appears in logs.
- When both 8081 and 8082 are healthy, requests reach multiple replicas via Spring Cloud LoadBalancer.
- Toggle a backend into failure: logs distinguish timeouts, HTTP errors, token errors, and discovery errors.
- Attach correlation ID to backend logs to follow the event trail across services.
- Measure differences between logical call counts, HTTP attempt counts, and backend received counts when retries are active.

## 13. Common Implementation Pitfalls

| Symptom | Common cause | How to resolve |
|---|---|---|
| `UnknownHostException` when calling service ID | Using plain RestTemplate or wrong bean | Check `@LoadBalanced`, dependencies, and bean qualifier |
| Downstream always returns 401 | Missing token, wrong audience/scope, or validation error | Inspect OAuth2 registration and security policy; do not log tokens |
| Inventory token sent to payment | Sharing one RestTemplate with auth interceptor across all targets | Separate beans per downstream or route credentials explicitly |
| Correlation ID appears only inbound | Missing outbound interceptor or empty MDC | Check beans, filter, and execution flow |
| Correlation ID leaks across requests | MDC not cleared on reused threads | Use `finally` cleanup and test concurrency |
| `@Async` calls lose correlation ID | `ThreadLocal` does not propagate automatically | Use context propagation or pass context explicitly |
| Response body lost after logging | Interceptor consumed body stream | Do not read body in logs, or design bounded buffering |
| One request generates multiple outbound logs | Retries across multiple layers or logger running per attempt | Separate logical calls from HTTP attempts; inspect interceptor order |
| Logs show only `inventory-service` | Logger inspects URI before LoadBalancer | Use backend logs or lifecycle metrics to see chosen instance |
| Token server failure mistaken for inventory error | Authorization happens prior to network call | Classify exceptions by stage |
| Interceptor does not run on WebClient | WebClient uses a different filter mechanism | For WebClient use `ExchangeFilterFunction`; do not reuse RestTemplate interceptors verbatim |
| Modifying interceptor list at runtime causes errors | RestTemplate bean mutated under concurrent use | Finish configuration before serving traffic |

## 14. Production Readiness Checklist

- [ ] Use `@LoadBalanced` on RestTemplate beans calling service IDs and confirm the Spring Cloud LoadBalancer dependency.
- [ ] Build RestTemplate via Spring-managed builder when instrumentation/customizers are needed.
- [ ] Give each interceptor a clear responsibility; never store per-request state in singleton fields.
- [ ] Issue and refresh credentials securely; never hardcode, log, or arbitrarily relay tokens.
- [ ] Scope tokens strictly to the intended downstream, scope, and audience.
- [ ] Propagate only allowlisted, normalized headers.
- [ ] Derive tenant/role from trusted security context; downstream still enforces authorization.
- [ ] Generate or validate correlation IDs on ingress and clear MDC in `finally`.
- [ ] Configure dedicated context propagation for `@Async` or reactive flows.
- [ ] Log only method/host/status/elapsed time; omit bodies, full URIs, headers, and secrets.
- [ ] Inspect runtime interceptor ordering and the timing scope measured.
- [ ] Never implement ad-hoc retries in interceptors without idempotency, budgets, and deadlines.
- [ ] Configure timeouts for both the authorization server and HTTP client; do not confuse with discovery timeout.
- [ ] Let tracing instrumentation manage `traceparent` instead of generating headers manually.
- [ ] Maintain interceptor unit tests and LoadBalancer integration tests with at least two backends.
- [ ] Observe both caller and backend to separate logical requests from individual attempts.

## References

- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate, client request interceptors, and HTTP client configuration.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `@LoadBalanced RestTemplate`, `ServiceInstance`, retries, and lifecycle.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClientManager`, client registration, and `client_credentials`.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Observation, tracing, and Spring-configured HTTP clients.

**Conclusion:** in a RestTemplate integrated with Spring Cloud LoadBalancer, interceptors provide a clean extension point for authentication, logging, and context propagation. However, they do not replace instance selection, grant user permissions, or make failing requests safe to retry. By separating responsibilities, configuring ordering carefully, protecting tokens, and testing failure/async/retry scenarios, inter-service communication becomes far easier to observe and operate safely.
