# RequestInterceptor and Caller Context Propagation

In **Spring Cloud OpenFeign**, applications typically declare a `@FeignClient(name = "inventory-service")` interface to call a service by service ID. Spring Cloud LoadBalancer can pick an appropriate `ServiceInstance` from discovery, yet it does not determine on its own what information about the **caller** must be forwarded downstream. For instance, inventory-service may need a correlation ID to stitch logs, an authenticated application identity, a locale, or an authorized tenant.

`feign.RequestInterceptor` lets the application modify `RequestTemplate` before Feign executes the HTTP request. It is well suited for attaching **permitted** metadata, yet it is not a user authentication mechanism, does not replace dedicated tracing, and does not select instances itself.

The goal of this lesson is to understand how to configure an interceptor **per Feign client**, how to propagate context in Spring MVC and flows without a servlet request, how to avoid leaking bearer tokens, how it interacts with Spring Cloud LoadBalancer, and how to unit-test outbound request contents.

## 1. What Is RequestInterceptor?

Feign provides a simple interface:

~~~java
package feign;

public interface RequestInterceptor {
    void apply(RequestTemplate template);
}
~~~

`RequestTemplate` describes the method, URL, headers, query, and body of the call being prepared by Feign. An interceptor can mutate the request template, for example:

~~~java
import feign.RequestInterceptor;
import feign.RequestTemplate;

public final class ServiceIdentityInterceptor
        implements RequestInterceptor {

    @Override
    public void apply(RequestTemplate template) {
        template.header("X-Calling-Service", "order-service");
    }
}
~~~

| Component | Responsibility |
|---|---|
| `RequestTemplate` | Represents the outgoing request to send, not yet an HTTP response |
| `RequestInterceptor.apply` | Adds/adjusts the template while preparing the call |
| Feign encoder | Converts DTOs and inputs into HTTP body/headers per contract |
| Feign HTTP client | Executes transport and receives the response |
| Spring Cloud LoadBalancer | Uses service ID to pick a target instance when load balancing is integrated |

The interceptor **does not receive a `ClientHttpResponse`** like a RestTemplate interceptor; it is not the place to inspect exact response status/body. Nor does it know which instance LoadBalancer has just picked. If an interceptor throws an exception in `apply`, the call can fail **before** an HTTP request ever reaches a backend.

Interceptors are normally singletons or reused across threads. Never store `currentUser`, `tenantId`, tokens, or request IDs in mutable fields on an interceptor.

## 2. Position of RequestInterceptor in OpenFeign + LoadBalancer

Suppose caller `order-service` calls inventory using a logical URI while discovery provides two replicas:

~~~text
Service ID: inventory-service

ServiceInstance:
  inventory-1 -> localhost:8081
  inventory-2 -> localhost:8082

@FeignClient(name = "inventory-service")
        |
        v
Feign creates RequestTemplate
        |
        v
RequestInterceptor attaches correlation ID, token, etc.
        |
        v
Feign Client integrated with Spring Cloud LoadBalancer
        |
        v
Selects a ServiceInstance and sends HTTP request
~~~

~~~mermaid
flowchart LR
    A["OrderService"] --> B["@FeignClient inventory-service"]
    B --> T["RequestTemplate"]
    T --> R["RequestInterceptor"]
    R --> C["Feign + LoadBalancer Client"]
    D["Discovery / supplier"] --> C
    C --> S["Selected ServiceInstance"]
    S --> H["HTTP transport"]
~~~

For example, the caller builds `GET /api/items/SKU-001`; the interceptor attaches `X-Correlation-Id`, and then LoadBalancer chooses `inventory-2`. The header is sent to the chosen instance. The interceptor does not need to—and should not—rewrite the hostname to `localhost:8082`.

If you want to transform the request **based on metadata of the selected instance**, Spring Cloud OpenFeign provides another extension point, `LoadBalancerFeignRequestTransformer`. That differs from `RequestInterceptor` because by then a concrete `ServiceInstance` has already been chosen.

When `@FeignClient(url = "...")` or a fixed URL via configuration is used, Feign normally calls that URL directly instead of selecting an instance by service ID via Spring Cloud LoadBalancer. Infrastructure DNS, proxies, or VIPs may still load-balance at another layer.

## 3. Three Types of Information Commonly Called Caller Context

| Type | Example | Can It Be Used Directly for Authorization? |
|---|---|---|
| Calling service identity | `order-service` | No, if only a plain text header; requires valid credentials/mTLS |
| End-user identity | User's JWT/opaque token | Only when downstream validates the token and enforces permissions |
| Request context | `X-Correlation-Id`, locale, trace ID | No; used for correlation and contextual handling |

A request arriving at `order-service` may originate from a real user, a scheduled job, or a message listener. You cannot assume every Feign call has an active `HttpServletRequest`.

For example, an `X-Tenant-Id: tenant-A` header supplied by the client is untrusted input. If tenant must be propagated for access control, the application must derive it from verified authentication, check permissions, and downstream must still enforce authorization.

## 4. Forward Only Approved Headers

| Header / Context | Recommended Policy |
|---|---|
| `X-Correlation-Id` | Allowed once length and format are validated/normalized |
| `Accept-Language` | Forward when locale is needed and values are bounded |
| `X-Tenant-Id` | Derive only from authenticated sources; never relay raw from client |
| `Authorization` | Forward only via token relay/exchange with valid audience, scope, and policy |
| `traceparent` and `tracestate` | Let Micrometer Tracing/OpenTelemetry manage them |
| `Cookie`, `Host`, `Connection`, `Content-Length` | Never copy blindly between services |
| Other sensitive headers | Do not forward by default unless there is an approved need |

Avoid writing code that iterates over all `HttpServletRequest.getHeaderNames()` and copies everything into `RequestTemplate`. Doing so can leak tokens/cookies, produce invalid HTTP requests, and trick downstream services into trusting self-declared client context.

## 5. Initializing a Feign Client in Spring Cloud

Maven dependencies in the caller:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Use compatible Spring Boot and Spring Cloud BOMs. You may need Eureka/Consul/Kubernetes or another discovery source if not using a static instance list.

~~~java
package com.example.order;

import com.example.feign.client.InventoryFeignClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = InventoryFeignClient.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Feign client:

~~~java
package com.example.feign.client;

import com.example.feign.config.InventoryFeignConfiguration;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignConfiguration.class
)
public interface InventoryFeignClient {

    @GetMapping("/api/items/{sku}")
    InventoryResponse findBySku(@PathVariable("sku") String sku);
}
~~~

Response DTO:

~~~java
package com.example.feign.client;

public record InventoryResponse(
        String sku,
        int available,
        String instanceId
) {
}
~~~

`name = "inventory-service"` is the target service ID. `contextId`, if declared, primarily distinguishes Feign client contexts/beans and must not be confused with the caller's application identity.

## 6. Registering a RequestInterceptor for a Single Feign Client

Keep the interceptor configuration class **outside the component scan packages** of `com.example.order`:

~~~text
com.example.order
    OrderApplication
    web/IncomingCorrelationFilter

com.example.feign.client
    InventoryFeignClient
    InventoryResponse

com.example.feign.config
    InventoryFeignConfiguration
~~~

Configuration code:

~~~java
package com.example.feign.config;

import feign.RequestInterceptor;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;

public class InventoryFeignConfiguration {

    @Bean
    RequestInterceptor inventoryContextInterceptor() {
        return template -> {
            String id = MDC.get("correlationId");

            if (id != null && !id.isBlank()) {
                template.header("X-Correlation-Id", id);
            }

            template.header("X-Calling-Service", "order-service");
        };
    }
}
~~~

`InventoryFeignConfiguration` is imported into `@FeignClient(configuration = ...)`'s context rather than component-scanned as global configuration. A `RequestInterceptor` bean placed in the parent ApplicationContext can affect more Feign clients than intended. This is especially dangerous for an interceptor adding `Authorization` meant exclusively for inventory.

When configuring via properties, Spring Cloud OpenFeign supports per-client `requestInterceptors` in corresponding release trains:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1500
            readTimeout: 3000
            loggerLevel: basic
            requestInterceptors:
              - com.example.feign.interceptor.InventoryContextInterceptor
~~~

For interceptors requiring injected dependencies, declaring a `@Bean` in client configuration is usually clearer. Do not register the same interceptor in both bean config and properties unless you have verified it will not be applied twice.

## 7. Generating a Correlation ID from Inbound Requests

In a Spring MVC caller, you can use `OncePerRequestFilter` to extract a valid correlation ID, generate one if missing or malformed, put it in MDC, and echo it in the response header.

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
public class IncomingCorrelationFilter extends OncePerRequestFilter {

    private static final Pattern UUID_PATTERN = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String incoming = request.getHeader("X-Correlation-Id");
        String id = incoming != null && UUID_PATTERN.matcher(incoming).matches()
                ? incoming : UUID.randomUUID().toString();

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", id);
        response.setHeader("X-Correlation-Id", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
~~~

Flow:

~~~mermaid
sequenceDiagram
    participant U as HTTP Client
    participant O as OrderService
    participant F as Feign RequestInterceptor
    participant L as LoadBalancer
    participant I as Inventory

    U->>O: GET /orders/stock + X-Correlation-Id
    Note over O: Validate/generate ID; MDC.put
    O->>F: InventoryFeignClient.findBySku
    Note over F: Read MDC; attach X-Correlation-Id
    F->>L: Feign request + service ID
    L-->>F: Select ServiceInstance
    F->>I: GET /api/items + correlation header
    I-->>O: HTTP response
    Note over O: MDC restored/cleared in finally
    O-->>U: Response + X-Correlation-Id
~~~

Client-supplied IDs are not necessarily trustworthy. Some systems always mint a new UUID at the edge to prevent spoofing; accepting a valid client ID depends on ingress policy.

Cleaning up MDC in `finally` is mandatory: Spring MVC uses a thread pool, so leaving an old ID behind can mix up logs for the next request.

## 8. Context on Other Threads: @Async, Scheduled Jobs, Message Listeners

`MDC` typically uses ThreadLocal. The interceptor in the example calls `MDC.get` from the thread executing Feign. For a blocking call on the same servlet thread, the value may be available. However, when:

- `@Async` methods run on a separate executor;
- Scheduled tasks call Feign with no inbound servlet request;
- Kafka/RabbitMQ listeners process messages;
- Reactive pipelines switch execution threads;
- The servlet context has already ended;

then MDC or `RequestContextHolder` may be empty. Do not blindly enable `InheritableThreadLocal` inside thread pools as a general fix because context can leak across tasks belonging to different requests.

The proper solution is to **pass context explicitly** alongside messages/commands, use a `TaskDecorator` that snapshots/restores context, or initialize a correlation ID at the job/message-consumer boundary. With Reactor, use Reactor `Context` and proper context propagation integration rather than assuming ThreadLocal works automatically.

Never store the latest correlation ID in a field on a singleton interceptor to "reuse" it; that causes cross-request data leaks.

## 9. Can RequestContextHolder Be Used?

You can read the request currently bound to the servlet thread:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

RequestAttributes attrs = RequestContextHolder.getRequestAttributes();

if (attrs instanceof ServletRequestAttributes servletAttrs) {
    HttpServletRequest incoming = servletAttrs.getRequest();
    String rawId = incoming.getHeader("X-Correlation-Id");

    // Forward a header only after validating and normalizing it.
}
~~~

This technique only works when a servlet request is genuinely bound to the current thread. It does not replace a context propagation model across workload types. If used, handle `attrs == null` and never copy all incoming headers automatically.

An immutable context structure separates validated data from raw headers:

~~~java
public record CallerContext(
        String correlationId,
        String tenantId,
        String locale
) {
}
~~~

You can construct `CallerContext` after ingress authentication/validation and pass it across layers, or use a context holder with a clear lifecycle that is cleared after processing.

## 10. Tenant and Permissions Must Never Come from Arbitrary Headers

A client can send:

~~~http
X-Tenant-Id: tenant-admin
~~~

If the caller relays this value verbatim and inventory trusts it for authorization, the system risks cross-tenant access. Tenant should be derived from verified identity or checked permissions.

~~~text
Incoming request
  -> Spring Security authenticates identity
  -> Verify tenant the user is allowed to access
  -> Create TrustedCallerContext
  -> Feign RequestInterceptor forwards approved tenant
  -> Inventory still authenticates and authorizes
~~~

If the application uses a JWT resource server, it can read the tenant ID from `JwtAuthenticationToken` claims **after** the JWT is validated and permissions are checked. Do not treat arbitrary claims as authorization proof without an authorization policy.

An `X-Tenant-Id` header can be useful for routing or logging, yet does not replace an access token verified by downstream. Similarly, `X-Calling-Service` is metadata; only validated tokens, mTLS, or workload identity prove service identity.


## 11. Distinguishing Client Credentials from Token Relay

"Propagating caller context" does not mean **always forwarding the end user's raw access token**. There are at least two models:

| Need | Identity Needed at Inventory | Appropriate Approach |
|---|---|---|
| Order service synchronizes inventory data on its own | **Application identity of `order-service`** | OAuth2 `client_credentials` or workload identity |
| Inventory must act on behalf of user permissions | **End-user identity** | Token relay or token exchange with explicit policy |
| Only linking log lines | Correlation/trace ID | Observability header; grants no permissions |

This is an anti-pattern:

~~~java
// Do not use by default for every downstream!
template.header(
        "Authorization",
        incomingServletRequest.getHeader("Authorization")
);
~~~

A user's token may be issued only for the gateway/order-service, making its audience invalid at inventory. Uncontrolled token copying both leaks credentials and risks granting improper permissions downstream. When user delegation is needed, define audience, scope, lifetime, token exchange, and verification at the target service.

Also avoid trusting `X-User-Id` or `X-Role` headers supplied by external requests as security proof. Those headers may help contextually after validation, yet access control must still be enforced by the security system.

## 12. OAuth2 Client Credentials with Spring Cloud OpenFeign

Spring Cloud OpenFeign includes OAuth2 client integration. When the corresponding dependencies/beans are present, you can enable this support so the framework manages access tokens instead of writing manual token-request logic.

Example `application.yml`:

~~~yaml
spring:
  cloud:
    openfeign:
      oauth2:
        enabled: true
        clientRegistrationId: inventory-client

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

Add the OAuth2 client dependency to the caller:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

This is only an illustrative pattern. `INVENTORY_CLIENT_SECRET` must be loaded from an environment variable or secret store; never embed real values in source code. The target service must have resource-server authentication or an appropriate token validation mechanism; issuing a token on the caller does not mean inventory automatically trusts it.

When OAuth2 support is enabled, Spring Cloud OpenFeign can configure `OAuth2AccessTokenInterceptor` to attach `Authorization`. Some options of this mechanism have **application-wide scope**. If multiple Feign clients require different audiences and registrations, verify scope before enabling a shared registration ID.

**Do not simultaneously enable the automatic OAuth2 interceptor and a custom RequestInterceptor that also attaches Authorization** for the same client without explicit coordination rules. Doing so can overwrite the header or produce unwanted multiple values.

## 13. When a Per-Client OAuth2 Interceptor Is Needed

If built-in OAuth2 support does not fit a multi-downstream configuration, you can use `OAuth2AuthorizedClientManager` and a dedicated `RequestInterceptor` for inventory.

For service-to-service flows without a servlet user, use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a `client_credentials`-capable provider:

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
public class OutboundOAuth2Configuration {

    @Bean
    OAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations,
                        clientService
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

Then declare the interceptor:

~~~java
package com.example.feign.config;

import feign.RequestInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public class InventoryOAuth2FeignConfiguration {

    @Bean
    RequestInterceptor inventoryBearerTokenInterceptor(
            OAuth2AuthorizedClientManager manager) {

        return template -> {
            var authorizeRequest = OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-client")
                    .principal("order-service")
                    .build();

            var client = manager.authorize(authorizeRequest);

            if (client == null || client.getAccessToken() == null) {
                throw new IllegalStateException(
                        "Cannot obtain inventory-service token"
                );
            }

            template.header(
                    "Authorization",
                    "Bearer " + client.getAccessToken().getTokenValue()
            );
        };
    }
}
~~~

This is an **alternative** to the auto-configured OAuth2 interceptor. In this case, do not enable both Authorization mechanisms at once. Reference the class via `@FeignClient(configuration = ...)` or combine beans into `InventoryFeignConfiguration`; do not let per-client configuration classes get component-scanned into global configuration.

Operational details to keep in mind:

- The manager can reuse an authorized client and fetch a fresh token when needed; do not call the token endpoint manually on every request unnecessarily.
- Client secrets, access tokens, and Authorization headers must never be logged.
- If the token server is slow or failing, the Feign call can fail **before** any request reaches inventory; monitor this failure category separately.
- The token must carry appropriate scope/audience. Inventory still needs to validate the token and enforce permissions.
- The interceptor runs on Feign's **blocking** request path; network token acquisition adds to overall latency, so configure timeouts for the token endpoint.
- Do not store the current token in mutable singleton state; let the OAuth2 manager/client service manage its lifecycle.

## 14. Multiple RequestInterceptors and Application Order

Feign can have multiple `RequestInterceptor`s for one client. Do not rely on arbitrary interceptor collection ordering to decide who overwrites `Authorization`, `X-Tenant-Id`, or `X-Correlation-Id`.

Principles:

- Each sensitive header has **one clear owner**.
- If multiple dependent steps are needed, use a single composite interceptor with explicitly written and tested ordering.
- Do not assume `template.header(...)` always has the exact overwrite semantics you expect across every Feign version. Inspect the actual template when duplicate headers could occur.
- If requests must be signed with HMAC, do not sign before the body/query is properly canonicalized; choose an extension point that supports exact signing.
- Separate observability context from authorization context.

Example ownership table:

| Data | Owning Component |
|---|---|
| `X-Correlation-Id` | Caller context/Correlation RequestInterceptor |
| `Authorization` | A single appropriate OAuth2/token interceptor |
| Tenant ID | Trusted caller context created after authentication |
| `traceparent` | Micrometer Tracing/OpenTelemetry |
| Instance host/port | Spring Cloud LoadBalancer/Feign HTTP client |
| Response status | Feign client/decoder/ErrorDecoder/observability |

Not every header has to go in a RequestInterceptor. If only one method needs a specific `X-Feature-Flag`, a `@RequestHeader` parameter on that method may be clearer. Avoid turning global interceptors into dumping grounds for business logic.

## 15. Distributed Tracing, Logging, and MDC

A correlation ID is a key for linking logs. It is **not the same** as a trace ID/span ID. When an application has Spring Boot Actuator + Micrometer Observation/Tracing and appropriate OpenFeign instrumentation, the framework can create spans and propagate W3C trace context via headers such as `traceparent`.

Do not synthesize `traceparent` with a UUID inside a RequestInterceptor: tracing headers have specific formats, sampling flags, and parent-child relationships.

Three layers of observability:

~~~text
Logs in order-service:
  correlationId = 4f6e...
  Feign client = inventory-service
  method = GET
  outcome = success/error

Tracing:
  traceId / spanId managed by instrumentation

LoadBalancer lifecycle:
  serviceId = inventory-service
  selected instance (with appropriate metrics/tracing)

Logs in inventory-service:
  correlationId = 4f6e...
  instanceId = inventory-2
  status = 200
~~~

Never log access tokens, client secrets, cookies, or full request bodies. Be careful with Feign `Logger.Level.FULL` because it can log headers and bodies. Even `BASIC` can log URLs containing sensitive query parameters.

A conservative configuration:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            loggerLevel: basic
~~~

If debug logging is enabled for Feign, review masking/redaction policies and log sink access controls. Metrics should use labels with bounded cardinality; do not attach raw user IDs or dynamic SKUs as metric labels.

## 16. Retries Can Make Interceptor Execution Count Differ from Expectations

OpenFeign supports `Retryer` and can integrate with retries in Spring Cloud LoadBalancer or another resilience layer. Spring Cloud OpenFeign typically registers `Retryer.NEVER_RETRY` by default, differing from some core Feign retry behaviors. When a project configures custom retries, every assumption must be re-verified.

~~~mermaid
sequenceDiagram
    participant O as OrderService
    participant F as Feign RequestInterceptor
    participant L as LoadBalancer/Retry
    participant A as Inventory A
    participant B as Inventory B

    O->>F: findBySku("SKU-001")
    Note over F: Attach token and correlation ID
    F->>L: HTTP request by service ID
    L->>A: First attempt
    A--xL: Timeout
    Note over L: Retry if policy exists and conditions match
    L->>B: Next attempt
    B-->>L: 200 OK
    L-->>O: Return DTO
~~~

Depending on the retry mechanism and the layer wrapped by retries, Feign may rebuild templates or invoke `RequestInterceptor` multiple times. **Do not use RequestInterceptor as a counter for a logical business call**. To count logical calls, measure at the service method; to count attempts, use HTTP client, retry listener, or LoadBalancer lifecycle instrumentation.

Key takeaways:

- The correlation ID of a single business request should remain unchanged across attempts.
- Token providers should cache tokens appropriately rather than requesting a new token unconditionally on every attempt.
- Retrying a payment POST or write operation can cause duplicate side effects; idempotency is required.
- Never call the same Feign client recursively from inside a RequestInterceptor to implement retries; that easily causes infinite recursion and unmanageable timeouts.

## 17. Timeouts and Errors Are Not RequestInterceptor's Responsibility

Timeout configuration example:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1500
            readTimeout: 3000
~~~

These common values are interpreted in **milliseconds** in the corresponding OpenFeign configuration. Connect timeout governs connection setup; read timeout governs waiting to read the response. They do not always bound the *total duration* including token acquisition, discovery, retries, backoff, and business processing.

| Concern | Appropriate Configuration Point |
|---|---|
| Token acquisition | Spring Security OAuth2 client/identity provider |
| Correlation ID, caller context | RequestInterceptor and caller context provider |
| Instance list and health checks | Discovery/`ServiceInstanceListSupplier` |
| Instance selection | Spring Cloud LoadBalancer |
| Connect/read timeout | Feign client/HTTP transport |
| Retry/backoff | Feign Retryer, LoadBalancer retry, or resilience layer |
| HTTP error mapping | Feign ErrorDecoder and business error handling |
| Metrics/tracing | Micrometer/Feign/LoadBalancer instrumentation |

When a Feign call returns 503, it may mean no instances exist, the backend failed, or infrastructure returned the response; classify using logs/metrics and discovery sources. Never tweak a request header to "heal" a dead instance.


## 18. Unit Testing a RequestInterceptor

You do not need to run an HTTP server to verify how an interceptor attaches headers. You can instantiate a `RequestTemplate` and invoke `apply` directly.

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import feign.RequestInterceptor;
import feign.RequestTemplate;
import java.util.Collection;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class CorrelationInterceptorTest {

    @Test
    void addsIdWhenMdcContainsCorrelationId() {
        String id = "c2c6380a-5f8d-4cc4-b244-08f1c64380cb";
        MDC.put("correlationId", id);

        try {
            RequestInterceptor interceptor = template -> {
                String value = MDC.get("correlationId");

                if (value != null && !value.isBlank()) {
                    template.header("X-Correlation-Id", value);
                }
            };

            RequestTemplate template = new RequestTemplate();
            interceptor.apply(template);

            Collection<String> values =
                    template.headers().get("X-Correlation-Id");

            assertTrue(values != null && values.contains(id));
        } finally {
            MDC.remove("correlationId");
        }
    }
}
~~~

Additional cases to test:

1. When MDC is absent, do not accidentally pick up a previous request's correlation ID.
2. Malformed user-supplied headers are normalized or replaced by the ingress filter.
3. The inventory interceptor does not appear on another Feign client dedicated to payment.
4. When the OAuth2 manager fails to obtain a token, the call aborts rather than attaching an empty bearer token.
5. No two interceptors inject duplicate `Authorization` headers.
6. Propagated tenant values originate from a verified source.
7. When called from `@Async`, context is propagated explicitly or falls back intentionally.

A `RequestTemplate` unit test only tests the interceptor logic; it **does not prove** that Spring Cloud LoadBalancer integration picks the right instance. Verifying which backend actually receives requests requires integration testing.

## 19. Practice Lab with Two Inventory Replicas

To test the flow end-to-end, use `SimpleDiscoveryClient` to declare two instances on the caller:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Run the same inventory application on ports 8081 and 8082. Each instance exposes `GET /api/items/{sku}` returning `sku`, `available`, and `instanceId`, and logs `X-Correlation-Id` in its own logs.

On the caller, use the created `InventoryFeignClient` and add a controller:

~~~java
package com.example.order.web;

import com.example.feign.client.InventoryFeignClient;
import com.example.feign.client.InventoryResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderInventoryController {

    private final InventoryFeignClient inventory;

    public OrderInventoryController(InventoryFeignClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/orders/stock/{sku}")
    public InventoryResponse stock(@PathVariable String sku) {
        return inventory.findBySku(sku);
    }
}
~~~

Send multiple requests from PowerShell:

~~~powershell
$correlationId = [guid]::NewGuid().ToString()
1..12 | ForEach-Object { Invoke-RestMethod -Uri "http://localhost:8080/orders/stock/SKU-001" -Headers @{ "X-Correlation-Id" = $correlationId } }
~~~

This example is a lab: services, controllers, and endpoints must be implemented before running the command. If you do not yet have an identity provider, verify the correlation/context interceptor first before enabling OAuth2 in a properly secured environment.

Results to observe:

- Response `instanceId` belongs to `inventory-1` or `inventory-2`; with Round Robin and a stable list, the two backends generally alternate across selections.
- Logs in order and inventory share the same validated correlation ID.
- No access tokens, client secrets, or cookies appear in logs.
- When stopping one replica, inspect discovery, health suppliers, timeouts, and retries before assuming RequestInterceptor is broken.
- When adding another Feign client for payment, ensure the inventory interceptor is not registered on payment.

## 20. Common Error Diagnostics

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Correlation ID does not reach backend | Interceptor not registered or MDC empty | Check `@FeignClient(configuration=...)`, inbound filter, and thread |
| Old correlation ID reappears | MDC not cleared or singleton holds state | Use `finally`, test concurrently |
| `@Async` loses caller context | ThreadLocal does not propagate automatically | Use TaskDecorator or pass context explicitly |
| Inventory token sent to payment | Interceptor scanned as global bean | Move client config outside scan scope |
| HTTP 401/403 | Wrong token audience/scope or downstream validation | Check identity provider and authorization policy |
| Token server error mistaken for inventory error | OAuth2 manager failed before HTTP transport | Classify token acquisition failures separately |
| Tenant ID spoofed | Copied raw tenant header from inbound request | Derive from verified authentication |
| `UnknownHostException` with service ID | LoadBalancer not integrated or wrong discovery | Check starters and client name |
| Only one replica receives requests | Supplier has one candidate or health/zone filtering | Check actual `ServiceInstance` set |
| RequestInterceptor does not see real host | Interceptor runs before instance selection | Use `LoadBalancerFeignRequestTransformer` when needed |
| Duplicate Authorization headers | Multiple interceptors attaching tokens | Keep a single auth policy per client |
| Feign FULL log leaks credentials | Overly detailed logging of headers/body | Lower log level, redact, restrict log access |
| One business call sends multiple HTTP requests | Multi-layer retries | Check retry budget and idempotency |

## 21. Pre-Deployment Checklist

- [ ] Service ID in `@FeignClient(name=...)` matches the `ServiceInstance` source.
- [ ] Only forward necessary context, using an allowlist instead of copying all incoming headers.
- [ ] Generate/validate correlation ID at ingress and restore/clear MDC in `finally`.
- [ ] Have an explicit strategy for `@Async`, scheduled jobs, and message consumers.
- [ ] Interceptors hold no mutable request state in singletons.
- [ ] Per-client interceptor beans do not accidentally become global.
- [ ] Never trust client-supplied user/tenant/role headers for authorization.
- [ ] Distinguish service-to-service tokens from user token relay/exchange.
- [ ] Each client has only one policy attaching Authorization.
- [ ] Never hard-code secrets or log tokens, cookies, or sensitive bodies.
- [ ] Use tracing framework instrumentation for `traceparent`.
- [ ] Do not use RequestInterceptor to pick instances or implement retries manually.
- [ ] If modifying requests based on the selected instance, use the proper LoadBalancer-layer extension point.
- [ ] Set appropriate connect/read timeouts, retry budgets, and idempotency guarantees.
- [ ] Have `RequestTemplate` unit tests and two-replica integration tests.
- [ ] Track logical calls and HTTP attempts separately when retries exist.

## References

- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@FeignClient`, RequestInterceptor, client configuration, LoadBalancer, OAuth2, and observability.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service ID, `ServiceInstance`, discovery, health checks, and retries.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClientManager`, client credentials, and access token management.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics, tracing, and context propagation.

**Conclusion:** `RequestInterceptor` helps OpenFeign inject **permitted and normalized context** into requests so services understand execution flow without repeating boilerplate in every Feign method. Yet a correlation ID is not a credential, a tenant header does not grant access, and forwarding access tokens must respect scope/audience. Spring Cloud LoadBalancer remains responsible for choosing a `ServiceInstance`; Feign's transport executes HTTP; and auth, tracing, and resilience must be configured at the proper extension points, bounded, and tested.
