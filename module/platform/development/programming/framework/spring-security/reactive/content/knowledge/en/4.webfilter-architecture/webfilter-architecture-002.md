# ServerWebExchange, ServerHttpRequest, and ServerHttpResponse in Security

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the three foundational objects of Spring WebFlux: `ServerWebExchange`, `ServerHttpRequest`, and `ServerHttpResponse`.
- Describe how an HTTP request travels through `WebFilter` and the Spring Security reactive filter chain before reaching a handler.
- Safely read request data, manipulate exchange-scoped attributes, retrieve the principal, and understand the distinct role of Reactor `Context`.
- Add response headers at the right moment, terminate a request early in a controlled manner, and avoid modifying the response after it has been committed.
- Distinguish decorating a request from authenticating a user; recognize common vulnerabilities involving spoofed headers, request bodies, logs, sessions, and responses.

> **Context:** This lesson covers the WebFilter architecture of Spring Security **reactive** on Spring WebFlux. The APIs below belong to `org.springframework.http.server.reactive.*` and `org.springframework.web.server.*`; do not confuse them with `HttpServletRequest`/`HttpServletResponse` in Servlet MVC.

## 1. What Do the Three Objects Correspond To?

| Object | Role | APIs Commonly Used in Security |
|---|---|---|
| `ServerHttpRequest` | Represents the **incoming HTTP request** as a reactive server API. | `getMethod()`, `getURI()`, `getPath()`, `getHeaders()`, `getQueryParams()`, `getCookies()`, `getRemoteAddress()`, `getBody()`, `mutate()`. |
| `ServerHttpResponse` | Represents the **outgoing HTTP response**; supports writing status, headers, cookies, and body via publishers. | `setStatusCode(...)`, `getHeaders()`, `addCookie(...)`, `beforeCommit(...)`, `isCommitted()`, `writeWith(...)`, `setComplete()`. |
| `ServerWebExchange` | The context of **a single request–response exchange** processed jointly by WebFilters and handlers. Wraps the request, response, attributes, principal, and WebFlux utilities. | `getRequest()`, `getResponse()`, `getAttributes()`, `getAttribute(...)`, `getPrincipal()`, `getSession()`, `getFormData()`, `mutate()`. |

The framework creates a `ServerWebExchange` to connect the incoming request with the outgoing response, along with auxiliary data for that processing pass. A `WebFilter` typically receives the **exchange**, because it may need to read the request, write to the response, access the principal, and pass a wrapped exchange to downstream processing.

Relationship:

~~~text
Incoming HTTP request
  └─ ServerHttpRequest ─┐
                        ├─ ServerWebExchange
  ┌─ ServerHttpResponse ┘        │
  │                              ▼
Outgoing HTTP response        WebFilter.filter(exchange, chain)
                                 │
                                 ▼
                              Next WebFilter / Handler
                                 │
                                 ▼
                      Mono<Void> representing processing
~~~

`ServerWebExchange` **is not a global context map**. It is tied strictly to a single HTTP exchange. `ServerHttpRequest` represents the request message; `ServerHttpResponse` controls the response message. The three objects are related but cannot be used interchangeably.

## 2. Where Do They Appear in the WebFilter Architecture?

When WebFlux receives a connection/request, the HTTP adapter layer creates an exchange; `FilteringWebHandler` organizes the `WebFilter` instances and forwards to the handler. When Spring Security WebFlux is enabled, a Spring Security proxy WebFilter selects the matching `SecurityWebFilterChain` and handles authentication, security context, authorization, exception handling, and more according to configuration.

~~~text
Client
  │ HTTP
  ▼
Reactive HTTP server / HttpWebHandlerAdapter
  │
  ▼
FilteringWebHandler
  │
  ├─ Application WebFilter (e.g., correlation ID)
  │
  ├─ Spring Security WebFilterChainProxy
  │      ├─ selects matching SecurityWebFilterChain
  │      ├─ authentication mechanism
  │      ├─ security context / Reactor Context
  │      ├─ authorization mechanism
  │      └─ handles access errors per configuration
  │
  └─ DispatcherHandler → Controller / handler
                         │
                         ▼
                ServerHttpResponse → Client
~~~

This is a **conceptual model**: the actual order of filters depends on `@Order`, `Ordered`, configured filters, and `SecurityWebFiltersOrder`. Do not infer security ordering solely from the declaration position of methods in Java.

Basic interface:

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ExampleFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        // Read request or prepare response here.
        return chain.filter(exchange);
    }
}
~~~

The snippet above illustrates the interface; to actually register it, you must create a `WebFilter` bean, such as via `@Component` or `@Bean`. `chain.filter(exchange)` returns a `Mono<Void>` representing the rest of processing. **Return that publisher** so the framework coordinates subscription, errors, and cancellation. Do not call `subscribe()` yourself inside a filter.

A filter has two fundamental choices:

1. **Continue**: `return chain.filter(exchange);` (optionally composed with reactive operators).
2. **Stop deliberately**: set up the response and return `response.setComplete()` or a body-writing publisher, and **do not call** `chain.filter(exchange)`.

In security, stopping due to unauthenticated or unauthorized access should be handled by the corresponding Spring Security components; a custom-written filter should not create a shortcut that accidentally bypasses authentication/authorization.

## 3. ServerHttpRequest: Input Data and Trust Boundaries

### 3.1. Reading Method, Path, Query, Headers, and Cookies

Example inside a `filter(...)` method or a handler taking a `ServerWebExchange` parameter:

~~~java
ServerHttpRequest request = exchange.getRequest();

String method = request.getMethod().name();
String path = request.getPath().value();
String accept = request.getHeaders().getFirst("Accept");
String tenantQuery = request.getQueryParams().getFirst("tenant");
String rawAuthorization = request.getHeaders().getFirst("Authorization");
~~~

This is an **illustrative snippet assuming an `exchange` variable is already in scope**; it is not a standalone Java program. Read APIs return what the *client sent*, which is not yet proof that the client is authorized:

- `getMethod()` and `getPath()` are useful for routing, policy matching, and controlled logging. Security rules should be declared using `authorizeExchange(...).pathMatchers(...)` or Spring Security matchers; avoid building URL checks with manual string matching.
- `getHeaders()` returns request information; a client-supplied header, including `X-User`, `X-Role`, or `X-Tenant`, **is not trustworthy by default**. Only use it as identity when the architecture has a trusted proxy/gateway and an explicit verification mechanism.
- `Authorization` is input credential data. Do not log raw tokens/passwords, and do not assign an `Authentication` yourself from the raw header string. Let the appropriate authentication filter (HTTP Basic, Bearer token, OAuth2, etc.) validate it.
- Query parameters can repeat; `getQueryParams()` is a multi-value map. Cookies can also repeat; never assume a cookie represents an authenticated session on its own.
- `getRemoteAddress()` typically refers to the connection peer; behind a reverse proxy, the true client IP depends on `Forwarded`/`X-Forwarded-For` handling configured **only from trusted proxies**. Do not use a client-supplied address to decide access permissions.

**Distinguishing parsing from authentication:** Knowing a request carries an `Authorization` header only proves *header data is present*, not that the credential is valid. Spring Security takes responsibility for parsing, verifying, and constructing an `Authentication`.

### 3.2. Requests Must Not Be Mutated Arbitrarily

Normally you cannot directly modify the original request's method/URI/headers by mutating the returned collections. If you need to create a new request view for **downstream** processing, use the builder/decorator:

~~~java
ServerHttpRequest decoratedRequest = exchange.getRequest()
    .mutate()
    .headers(headers -> headers.set("X-Verified-Tenant", verifiedTenant))
    .build();

ServerWebExchange decoratedExchange = exchange.mutate()
    .request(decoratedRequest)
    .build();

return chain.filter(decoratedExchange);
~~~

This is a **snippet placed inside `WebFilter.filter(...)`**; `verifiedTenant` must be data verified by the system in trusted logic (not a value copied directly from an incoming header). `headers.set(...)` replaces values with the same name rather than accidentally retaining an additional spoofed client header. Creating a decorated exchange only changes the view for subsequent filters/handlers; it does not alter the HTTP packet that already traveled over the network.

Wrapping a request **does not automatically turn a header into authentication**. For identity and access control, use Spring Security's `Authentication` and authorization.

### 3.3. The Body Is a Reactive Stream with Consumption Constraints

`request.getBody()` has type `Flux<DataBuffer>`: byte chunks delivered via reactive signals, not a `String` already sitting in RAM. A filter trying to "pre-read" the body can leave downstream handlers with no data to read; unbounded buffering can cause memory exhaustion; improper `DataBuffer` management can leak resources.

- Prefer WebFlux/Spring Security's built-in mechanisms for handling forms, authentication credentials, multipart uploads, and body decoding.
- If you truly must read/modify the body in a filter, you need size limits, error and cancellation handling, proper `DataBuffer` release/retain discipline, and re-exposing the body via `ServerHttpRequestDecorator` for downstream. That is a specialized problem and cannot be solved by arbitrarily calling `block()` or `subscribe()`.
- Do not log bodies containing passwords, bearer tokens, cookies, or personal data. Avoid turning a single request stream into data shared across multiple requests.

## 4. ServerHttpResponse: Who Writes What and When?

With `ServerHttpResponse response = exchange.getResponse()`, a filter can:

- Set the HTTP status before the response commits: `response.setStatusCode(HttpStatus.BAD_REQUEST)`.
- Add/modify headers before commit: `response.getHeaders().set("X-Correlation-Id", id)`.
- Add cookies according to the relevant policy: `response.addCookie(...)`.
- Register an action to run **before commit**: `response.beforeCommit(Supplier<? extends Mono<Void>>)`.
- Return a publisher that completes the response without a body: `return response.setComplete();`.
- Return a publisher that writes body data (with proper encoding and buffer management): `response.writeWith(...)`.

### 4.1. Commit Timing

Once the response begins to commit (e.g., writing the body or completing the response), the status and headers must be finalized to be sent to the client. After the response is committed, changing status/headers may have no effect or cause an error. Therefore:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.beforeCommit(() -> {
    response.getHeaders().set("X-Correlation-Id", correlationId);
    return Mono.empty();
});
return chain.filter(exchange);
~~~

This is a **snippet inside a `WebFilter.filter(...)`**, where `correlationId` has already been generated. A `beforeCommit` callback must be fast, non-blocking, and is well-suited for adding final metadata prior to commit. Calling `response.isCommitted()` helps inspect state, but **does not replace** managing write timing properly. Do not wait until `doFinally` on an already completed pipeline to attempt adding headers.

### 4.2. Controlled Early Termination

Example of a filter checking a well-defined *non-authentication input condition*:

~~~java
if (invalidRequestShape) {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.BAD_REQUEST);
    return response.setComplete();
}
return chain.filter(exchange);
~~~

This is an **illustrative branch inside a filter**, where `invalidRequestShape` is the result of request syntax validation; this snippet omits the surrounding class declarations. Once stopped, **do not** call `chain.filter(exchange)`. For returning `401 Unauthorized` or `403 Forbidden` in authentication/authorization scenarios, prefer configuring `ServerHttpSecurity`, `ServerAuthenticationEntryPoint`, and `ServerAccessDeniedHandler` with proper semantics, including challenge headers when needed.

For the response body, response writers take responsibility for serialized data and buffers; do not manipulate an `OutputStream` directly or assume synchronous Servlet-style writes.

## 5. ServerWebExchange: Request-Scoped Data, Principal, and Session

### 5.1. Exchange Attributes

`exchange.getAttributes()` is a `Map<String,Object>` used to share metadata within **a single HTTP exchange**:

~~~java
private static final String AUDIT_TRACE_KEY =
    "com.example.security.auditTraceId";

// In WebFilter:
exchange.getAttributes().put(AUDIT_TRACE_KEY, "req-123");

// In downstream handler/filter using the same key:
String traceId = exchange.getAttribute(AUDIT_TRACE_KEY);
~~~

These are illustrative snippets in separate locations, not a standalone program. Use namespaced keys to avoid collisions with libraries/frameworks. Attributes are useful for data tied to processing a request, such as a server-generated request ID, request arrival timestamp, or verified parsing results.

Do not confuse exchange attributes with application-wide shared memory, and do not store this mutable state in a singleton shared across multiple requests.

### 5.2. Principal and SecurityContext

`exchange.getPrincipal()` returns `Mono<Principal>`. In an exchange passing through Spring Security reactive, the principal can reflect the authenticated `Authentication`, depending on how the filter chain is configured. When there is no principal, the publisher may be empty.

~~~java
Mono<String> username = exchange.getPrincipal()
    .map(java.security.Principal::getName)
    .defaultIfEmpty("anonymous");
~~~

This example is for **displaying a name or safe logging**. Do not use the `"anonymous"` fallback value to grant permissions or infer that authentication succeeded. In some cases Spring Security denies the request before the handler runs.

Core reactive authentication data is managed by Spring Security through `ReactiveSecurityContextHolder` and the **subscription-scoped Reactor Context**, for example:

~~~java
Mono<String> authenticatedName =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext -> securityContext.getAuthentication())
        .map(authentication -> authentication.getName());
~~~

This snippet requires importing `org.springframework.security.core.context.ReactiveSecurityContextHolder`. This publisher only emits a value when the appropriate security context has been placed into the subscription; do not call `block()` to read it in a WebFlux service.

These three scopes differ:

| Channel | What it stores | Lifecycle / Scope |
|---|---|---|
| Request headers/cookies | Data sent by the HTTP client/proxy | HTTP message; untrusted until verified |
| `exchange.getAttributes()` | Internal metadata of a single HTTP exchange | Exchange passed across filters/handlers |
| Reactor `Context` / `ReactiveSecurityContextHolder` | Subscriber-scoped metadata, including reactive security context | Reactive chain and corresponding subscription |

**Do not copy the `Authorization` header into an exchange attribute and treat it as an authenticated principal.** A proper security filter must create or restore an `Authentication` from verified data; authorization rules operate on that.

### 5.3. Session and Body Convenience APIs

`exchange.getSession()` returns `Mono<WebSession>`, related to WebFlux sessions if the application uses them. Calling the session API does not imply the user is authenticated or that the security context necessarily lives in the session. Where the security context is stored depends on `ServerSecurityContextRepository` and configuration (e.g., a stateless bearer-token app differs from an app using web sessions).

`exchange.getFormData()` and `getMultipartData()` support reading form/multipart data parsed through WebFlux's mechanism. Use them only when actually needed while considering size limits and sensitive content; do not perform a "read form for every request" step in a global filter.

## 6. Hands-On Exercise: Controlled WebFlux + Spring Security

This example uses **Java 17**, **Spring Boot 3.3.5**, WebFlux, and Spring Security reactive. It simultaneously demonstrates:

1. A WebFilter generating a server-side correlation ID and storing it in **exchange attributes**.
2. The filter placing the ID into the **Reactor Context** for the downstream pipeline.
3. The filter adding the ID to a response header via `beforeCommit`.
4. A controller reading the **request** from the exchange; a public route uses the ID; a private route requires Spring Security **Basic authentication**.
5. `exchange.getPrincipal()` on the private route reflects the principal from the security filter chain.

This is a standalone application for learning purposes and does not depend on code in the current module.

### 6.1. Directory Structure

~~~text
exchange-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ExchangeSecurityDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'exchange-security-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

File `src/main/java/example/ExchangeSecurityDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;
import reactor.util.context.Context;

@SpringBootApplication
public class ExchangeSecurityDemo {

    private static final String TRACE_ATTRIBUTE =
        "example.ExchangeSecurityDemo.traceId";
    private static final String TRACE_CONTEXT = "traceId";

    public static void main(String[] args) {
        SpringApplication.run(ExchangeSecurityDemo.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Simple credential for local demo only.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Order(Ordered.HIGHEST_PRECEDENCE)
    @org.springframework.stereotype.Component
    static final class CorrelationFilter implements WebFilter {
        @Override
        public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

            String traceId = UUID.randomUUID().toString();

            // Metadata scoped only to the current exchange.
            exchange.getAttributes().put(TRACE_ATTRIBUTE, traceId);

            ServerHttpResponse response = exchange.getResponse();
            response.beforeCommit(() -> {
                response.getHeaders().set("X-Correlation-Id", traceId);
                return Mono.empty();
            });

            // Reactor Context propagates with the subscriber, even across thread switches.
            return chain.filter(exchange)
                .contextWrite(Context.of(TRACE_CONTEXT, traceId));
        }
    }

    @RestController
    static final class ApiController {

        @GetMapping("/public")
        public Mono<Map<String, String>> publicRoute(
            ServerWebExchange exchange) {

            ServerHttpRequest request = exchange.getRequest();

            return Mono.deferContextual(ctx ->
                Mono.just(Map.of(
                    "method", request.getMethod().name(),
                    "path", request.getPath().value(),
                    "traceId", ctx.<String>getOrDefault(
                        TRACE_CONTEXT, "missing")
                )));
        }

        @GetMapping("/private")
        public Mono<Map<String, String>> privateRoute(
            ServerWebExchange exchange) {

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "principal", principal.getName(),
                    "path", exchange.getRequest().getPath().value()
                ));
        }
    }
}
~~~

### 6.2. Run and Observe

Requires JDK 17+ and a compatible Gradle or Gradle Wrapper (if the project does not have a wrapper yet, use the `gradle` command). From the `exchange-security-demo` directory:

~~~bash
gradle bootRun
~~~

If a Gradle Wrapper has been generated, the equivalent is `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

In another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:demo-pass http://localhost:8080/private
~~~

Expectations for the **running demo configuration**:

| Call | Expected HTTP Status | Content to Verify |
|---|---|---|
| `GET /public` without credentials | 200 | JSON has `method=GET`, `path=/public`, `traceId` is a UUID; response header `X-Correlation-Id` equals the `traceId` value. |
| `GET /private` without credentials | 401 | Spring Security blocks before the controller returns private data; the HTTP Basic challenge depends on the entry point configuration. |
| `GET /private` with Basic `learner:demo-pass` | 200 | JSON has `principal=learner`, `path=/private`. |

UUIDs change on every request and JSON field ordering is not guaranteed; therefore, do not specify a hardcoded JSON or status+header string as "exact stdout". This is an HTTP response, not the stdout of the `java` command. When using PowerShell, if `curl` is a different alias, invoke `curl.exe`.

**Security note:** `{noop}` permits unencoded passwords and hardcoded demo accounts. Use only in local testing environments; production environments require a secure encoder, secret management, and an appropriate authentication flow. Never use Basic authentication over unencrypted HTTP in production; HTTPS is required. The demo uses GET routes and therefore does not disable CSRF just "to make it work".

### 6.3. Why Does the Example Store the Trace ID in Two Places?

`exchange.getAttributes()` lets filters/handlers receiving the same exchange access internal metadata. `contextWrite` supplies information to reactive operators that read via `Mono.deferContextual(...)`. Both scopes can carry **the same value**, but they are two distinct mechanisms. The `.contextWrite(Context.of(...))` call is placed downstream of `chain.filter(exchange)` so that publishers upstream of the chain can read the context when subscribed to.

`@Order(Ordered.HIGHEST_PRECEDENCE)` on the demo filter registers the response callback early and wraps the downstream chain with context. Do not use this example as justification to arbitrarily reorder internal security filters managed by Spring Security.

## 7. Where Should Security Logic Live?

**Not everything that needs to inspect a request has to be a custom-written application WebFilter.** Choose the right mechanism based on responsibility:

| Need | Preferred Mechanism | Why |
|---|---|---|
| Basic, Bearer JWT, OAuth2 Login authentication | Spring Security `SecurityWebFilterChain` and appropriate authentication components | Manages credentials, authentication, context, and standard error handling |
| URL/method authorization | `authorizeExchange(...)`, method security when appropriate | Clear, consistent policies; avoids manual URL string comparisons |
| Reading identity in a reactive service | `ReactiveSecurityContextHolder.getContext()` or framework-provided principal APIs | Does not rely on `ThreadLocal` or client-supplied headers |
| Correlation ID, timing, technical headers | Application `WebFilter` | Attaches cross-cutting request/response logic for the whole pipeline |
| Interpreting incoming data into an Authentication | `ServerAuthenticationConverter` with `ReactiveAuthenticationManager` and the matching authentication filter | Separates credential extraction from verification |
| Returning a custom response on denial | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` | Preserves 401/403 semantics and security ordering |
| Configuring session/repository-based security context | `ServerSecurityContextRepository` | Avoids ad-hoc storing/restoring of security context in attributes |

In particular, a custom WebFilter must never "let through" a sensitive request merely because it sees `X-User: admin` or a familiar cookie name. Client-created signals never replace the authentication step.

## 8. Common Misconceptions and Implementation Mistakes

### Mistake 1: Treating ServerWebExchange as SecurityContext

`exchange.getAttributes().put("user", "...")` only sets metadata. Spring Security does not automatically treat a custom attribute key as an Authentication. If you need the authenticated identity, use the principal/security context through the proper flow.

### Mistake 2: Trying to Change Status After the Controller Has Written the Body

The response may already be committed. Writing headers too late results in headers missing over the wire or errors. Register `beforeCommit` before calling downstream, or set up the response before writing.

### Mistake 3: Calling `chain.filter(exchange)` Without Returning the Publisher

~~~java
// WRONG: the publisher may not be subscribed to properly.
chain.filter(exchange);
return Mono.empty();

// RIGHT: return the downstream publisher.
return chain.filter(exchange);
~~~

These two snippets only illustrate the `filter` method body. A reactive pipeline is a task description; creating a `Mono` does not mean the task has executed.

### Mistake 4: Calling `subscribe()`/`block()` Manually Inside a WebFilter

Manual subscription can create a detached subscription, lose Reactor Context/SecurityContext, mispropagate errors, and break the request lifecycle; `block()` can block an event-loop thread. Compose with `flatMap`, `then`, or `onErrorResume` as appropriate and return a single publisher to the framework.

### Mistake 5: Reading the Request Body and Forwarding the Original Request

A reactive body is not data you can read arbitrarily multiple times. If a filter needs to inspect the body, the proper solution must account for bounded buffering, a decorator for the downstream request, backpressure, and `DataBuffer` management. Avoid blocking/collecting the entire body just "for a quick read".

### Mistake 6: Trusting Unverified IP, Role, or Tenant Headers

`X-Forwarded-For`, `X-Role`, `X-Tenant`, or `Authorization` are all untrusted inputs. Trust them only after they pass an appropriate verification mechanism; reverse proxies must be explicitly configured to strip or overwrite headers that clients are not allowed to assert.

### Mistake 7: Leaking Sensitive Data via Logs or Responses

Do not log raw bearer tokens, passwords, or session cookies; do not return stack traces, security contexts, or internal attributes to the client. A correlation ID should be an opaque identifier containing no personal data.

### Mistake 8: Sharing Mutable State Across All Requests

Storing `ServerWebExchange`, the response, or user identity in a singleton bean's field causes concurrent access issues and cross-request data leaks. Keep the exchange scoped per invocation; store request metadata in exchange attributes or Reactor Context with the proper scope.

### Mistake 9: Assuming `getSession()` Always Means Logged In

A session's presence does not prove an Authentication exists. Stateless bearer JWT applications can authenticate without maintaining a server-side session. Base authorization decisions on Authentication/security context and policies.

### Mistake 10: Attaching 401/403 Responses Manually While Bypassing Spring Security

A status code is not the entire security error-handling flow. Spring Security also manages the authentication entry point, HTTP Basic challenge, access-denied logic, and security context. Custom responses belong in the appropriate extension points.

## 9. Review Checklist for a Security-Related WebFilter

Before accepting code, verify:

1. **Scope:** Which requests does the filter run on? Is a global WebFilter truly needed, or should it sit inside `SecurityWebFilterChain`?
2. **Data sources:** Are method/path/headers/body read from `ServerHttpRequest` treated as untrusted and verified before being used for permissions?
3. **Forwarding:** Do all continuation branches return `chain.filter(exchange)`, and do termination branches complete the response without calling the chain further?
4. **Context:** Are exchange metadata and Reactor Context used with the right scope; does the principal originate from real authentication?
5. **Response:** Are headers/status set before commit; is the `beforeCommit` callback non-blocking; are there no attempts to modify after commit?
6. **Body and resources:** No repeated body reads, no unbounded buffering, no `DataBuffer` leaks, and no `block()` calls on the event loop?
7. **Data protection:** No credentials logged, no sensitive info returned in responses, no trusting spoofed headers?
8. **Testing:** Are there test cases for anonymous/authenticated/denied, errors and cancellation, correlation ID on both success and failure, and concurrent requests not mixing up metadata?

Practical test scenarios that should be covered:

- `GET /public` returns 200 and a matching correlation ID between body and header.
- `GET /private` without credentials is denied; with valid credentials returns the right principal.
- A request with `X-User: admin` is not automatically authenticated.
- Two concurrent requests receive distinct correlation IDs; neither response carries the other's ID.
- When the controller fails before or while writing the body, the filter does not attempt to write headers after commit and the error is still handled properly.
- When behind a gateway/reverse proxy, `Forwarded` data is used only according to a verified trust configuration.

## 10. Self-Assessment Questions

**1. Where do you read the current request's path inside a WebFilter?**

From `exchange.getRequest().getPath()`. It provides request data; authorization rules should be defined using Spring Security matchers.

**2. Once a handler has started sending the response, can you reliably change the HTTP status?**

No. Once the response is committed, status/headers can no longer be freely changed. Set them before commit; consider `beforeCommit` for headers that need to be added.

**3. Are `exchange.getAttributes()` and `ReactiveSecurityContextHolder` the same store?**

No. Attributes belong to the exchange; `ReactiveSecurityContextHolder` relies on the subscription's Reactor Context.

**4. If a client sends `X-Role: ADMIN`, can the endpoint automatically grant admin permissions?**

No. Client-asserted headers are untrusted. Spring Security must authenticate the identity and evaluate policies based on an Authentication/authorities built from verified data.

**5. When you want to return 400 and stop processing in a filter, are you required to call the chain?**

No. You can set the status and `return response.setComplete()`, but only in an intentional branch. Do not use it to replace Spring Security's authentication/authorization error-handling mechanisms.

## Official Documentation

- Spring Framework WebFlux — `WebFilter` and Web Handler API: https://docs.spring.io/spring-framework/reference/web/webflux-webhandler-api.html
- Spring Framework Javadoc — `ServerWebExchange`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework Javadoc — `ServerHttpRequest`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework Javadoc — `ServerHttpResponse`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
