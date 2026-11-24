# ServerWebExchange in the Request Processing Flow

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what `ServerWebExchange` is, where it is created, and which Spring WebFlux components it flows through.
2. Distinguish request/response, exchange attributes, `WebSession`, `Principal`, and Reactor `Context`.
3. Understand how Spring Security applies authentication and authorization on the same reactive processing flow.
4. Write a `WebFilter` and controller using `ServerWebExchange` without blocking the event loop or breaking the reactive chain.
5. Observe allowed requests, denied requests, and data flowing across filter → handler → response.

**Scope:** Spring WebFlux (reactive stack) and Spring Security WebFlux integration. Servlet/MVC concepts such as `HttpServletRequest`, `HttpServletResponse`, and `FilterChain` belong to a different stack; do not use them to explain the `ServerWebExchange` API.

## 2. What Is ServerWebExchange?

`org.springframework.web.server.ServerWebExchange` is the **context of a single HTTP exchange** on the WebFlux server side. It brings together the objects and utilities needed by multiple processing layers within *the same request*:

- `ServerHttpRequest`: the request's HTTP method, URI, path, headers, cookies, and body.
- `ServerHttpResponse`: the response's status, headers, cookies, and body-writing mechanism.
- `Map<String, Object>` attributes: temporary data bound to the current exchange so components along the processing chain can coordinate.
- `Mono<WebSession>`, `Mono<Principal>`: reactive interfaces for accessing the session and principal.
- Utilities such as `getFormData()`, `getMultipartData()`, `getLocaleContext()`, `getLogPrefix()`, and `mutate()`.

Mental model: **request and response are two sides of the exchange; the exchange is the object encompassing both along with contextual state during processing.** Do not treat the exchange as a request body, a “global context,” or a store that persists across multiple requests.

`ServerWebExchange` lives at Spring WebFlux's `WebHandler` layer, above `HttpHandler` (the layer adapting to an HTTP server such as Reactor Netty). Both annotated controllers and functional routing operate on this WebFlux processing foundation; annotated controllers can accept `ServerWebExchange` directly as a method parameter.

## 3. Position in the HTTP Processing Flow

High-level diagram:

```text
Client
  │ HTTP request
  ▼
HTTP server + HttpHandler adapter
  │ creates / passes request and response to the WebHandler layer
  ▼
WebExceptionHandler (wraps the flow for error handling)
  ▼
WebFilter #1 → WebFilter #2 → ... → WebHandler
                          │
                          ├─ Spring Security: WebFilterChainProxy
                          │    └─ selects the matching SecurityWebFilterChain
                          │       → authentication / security context / authorization
                          │
                          └─ DispatcherHandler (for annotated controllers)
                               → HandlerMapping
                               → HandlerAdapter / Controller
                               → writes the result to ServerHttpResponse
  ▼
HTTP response to client
```

The diagram shows logical relationships; **the exact order among `WebFilter` instances depends on configuration and filter ordering**. Spring Security is itself part of the `WebFilter` chain, not a step guaranteed to occur at one fixed position in every setup. `WebExceptionHandler` can intervene when errors occur; if a filter terminates early, the controller will not be invoked.

A typical GET request passes through these milestones:

1. The HTTP server receives data and the adapter creates Spring's abstractions; `ServerWebExchange` represents that exchange.
2. `WebFilter` instances can read method/path/headers, attach attributes, add response headers, check conditions, or forward to `chain.filter(exchange)`.
3. When Spring Security is configured, `WebFilterChainProxy` selects the appropriate `SecurityWebFilterChain` using `ServerWebExchangeMatcher`. Security filters perform tasks such as loading `SecurityContext`, authenticating credentials, and evaluating access rules.
4. If allowed to proceed, `DispatcherHandler` locates the matching handler; the controller reads the exchange or parameters already resolved by Spring.
5. The handler returns `Mono`/`Flux` or a value converted into a response; WebFlux processes it asynchronously, sends headers/body, and completes the exchange.
6. If authentication/authorization fails, security filters can produce 401 or 403 **without ever entering the controller**.

**Note:** “Non-blocking” does not mean every component runs on the same thread or that a request is processed instantaneously. Work starts and completes according to subscriptions and reactive signals; authentication data should not be stored in an application-managed `ThreadLocal`.

## 4. Key Exchange APIs

| API | Meaning | Proper Usage |
| --- | --- | --- |
| `getRequest()` | Returns `ServerHttpRequest` | Read method, path, query, headers, cookies; body is a data stream |
| `getResponse()` | Returns `ServerHttpResponse` | Set status/headers before the response is committed; write body using reactive APIs |
| `getAttributes()`, `getAttribute(...)` | Returns request-scoped data | Pass correlation IDs / intermediate results between filter and handler |
| `getSession()` | `Mono<WebSession>` | Access session asynchronously; calling this API **does not automatically start a new session** |
| `getPrincipal()` | `Mono<T extends Principal>` | Retrieve the principal if present; may be `Mono.empty()` |
| `getFormData()` | `Mono<MultiValueMap<String, String>>` | Access parsed form data when content type matches |
| `getMultipartData()` | `Mono<MultiValueMap<String, Part>>` | Access multipart parts; mind resources and upload size |
| `getLocaleContext()` | Locale information | Supports internationalization based on the active resolver |
| `getLogPrefix()` | Exchange-scoped log prefix | Use when correlating log lines for the same request |
| `mutate()` | Builder creating an exchange wrapper | Swap the apparent request/response/principal for downstream steps |

Example of *reading information without consuming the body* inside a controller:

```java
@GetMapping("/request-info")
Mono<Map<String, String>> requestInfo(ServerWebExchange exchange) {
    ServerHttpRequest request = exchange.getRequest();
    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getPath().value(),
        "requestId", request.getId()
    ));
}
```

This is an **illustrative method**, meant to live inside a `@RestController` with the corresponding imports. `requestId` is generated at runtime and cannot be predicted statically. Never treat path, request ID, or any exchange attribute as proof that a user is authenticated.

### How Do Exchange Attributes, Session, and Reactor Context Differ?

| Storage | Scope | Typical Characteristics |
| --- | --- | --- |
| `exchange.getAttributes()` | One HTTP exchange | Mutable `Map`; shared among steps that see the same exchange; does not automatically persist to the next request |
| `WebSession` | Client session | Can persist across multiple requests when a session mechanism is used; keep data small and intentional |
| Reactor `Context` | Subscription / reactive chain | Propagates metadata across reactive steps even across thread switches; read/written via Reactor APIs |
| `SecurityContext` | Security context for reactive execution | Holds `Authentication`; Spring Security connects it to Reactor `Context` and the configured security context repository |

*Do not conflate them:* putting a `"user"` key in `getAttributes()` **does not authenticate** a user. Checking identity or permissions must rely on Spring Security mechanisms (`Authentication`/`AuthorizationManager` and `SecurityContext`), never trusting headers or attributes that a client can influence.

### The Request Body Is Not a Pre-Loaded String

`exchange.getRequest().getBody()` exposes a `Flux<DataBuffer>`. The body is normally consumed during decoding/binding. A filter that reads the whole body and then expects the controller to read it again can cause missing data; if re-reading is required, you must use proper caching/decoration and manage `DataBuffer` memory carefully. For normal business logic, prefer `@RequestBody Mono<MyDto>` or `ServerRequest.bodyToMono(...)` instead of manually buffering the body in a filter.

## 5. ServerWebExchange and Reactive Spring Security

In WebFlux, web security configuration uses `ServerHttpSecurity` and creates one or more `SecurityWebFilterChain` beans. `WebFilterChainProxy` applies the chain matching the exchange. Internal components can act at different points:

- The filter associated with `ServerSecurityContextRepository` loads/saves security context information according to the configured strategy.
- Authentication filters handle HTTP Basic, form login, bearer tokens, etc., when those mechanisms are enabled.
- Authorization filters inspect path, method, and authentication state to permit or deny access.
- `SecurityContextServerWebExchangeWebFilter` enables `exchange.getPrincipal()` to obtain the principal from `ReactiveSecurityContextHolder` within the appropriate security context.

For example, the rule `pathMatchers("/public/**").permitAll()` only states that the path is accessible without logging in. It **does not guarantee** that `exchange.getPrincipal()` will have a value. Likewise, `authenticated()` requires valid authentication; the exchange API itself does not perform login.

In reactive processing, when you need the `Authentication` itself (roles/authorities, authentication metadata), use:

```java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

This is a **fragment** placed inside code that already has a Spring Security context; the corresponding imports are `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.core.context.SecurityContext`, and `org.springframework.security.core.Authentication`. It may complete empty if no context exists; design the anonymous/unauthenticated case explicitly. Do not pull `Authentication` from Servlet-style `SecurityContextHolder.getContext()` and assume it follows you across every reactive step.

## 6. Runnable Example: filter → exchange → security → controller

The example uses **Java 17+, Spring Boot 3.5.12, and Spring WebFlux/Spring Security 6.x**. We create two GET endpoints:

- `GET /public/exchange`: public, returns method/path and an ID placed in attributes by a `WebFilter`.
- `GET /me`: requires HTTP Basic; returns the username from `exchange.getPrincipal()`.

The `WebFilter` writes the same correlation ID into exchange attributes and a response header **before** invoking the rest of the chain. It does not perform authentication or replace security filters.

### Project Structure

```text
exchange-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/exchange/
    ├── ExchangeDemoApplication.java
    ├── SecurityConfiguration.java
    ├── TraceWebFilter.java
    └── ExchangeController.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'exchange-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**`src/main/java/com/example/exchange/ExchangeDemoApplication.java`**

```java
package com.example.exchange;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExchangeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExchangeDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/exchange/SecurityConfiguration.java`**

```java
package com.example.exchange;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("LEARNER")
            .build();
        return new MapReactiveUserDetailsService(learner);
    }
}
```

`{noop}` is only appropriate for **local demos** to observe the request flow; in real applications, use a secure password encoder, secret management, and an appropriate authentication mechanism. Do not ship demo accounts to production. The example keeps CSRF protection enabled by default; all verification requests use GET, so disabling CSRF is unnecessary.

**`src/main/java/com/example/exchange/TraceWebFilter.java`**

```java
package com.example.exchange;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String traceId = exchange.getRequest().getId();
        exchange.getAttributes().put("demo.traceId", traceId);
        exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);
        return chain.filter(exchange);
    }
}
```

`@Order(Ordered.HIGHEST_PRECEDENCE)` places the example filter at high priority, allowing it to attach the ID before downstream steps run. It does not read the principal because at this early stage the security context may **not yet** be populated. `return chain.filter(exchange)` is an essential detail: it continues the publisher for the rest of the chain while letting the framework control subscription and response completion.

**`src/main/java/com/example/exchange/ExchangeController.java`**

```java
package com.example.exchange;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangeController {
    @GetMapping("/public/exchange")
    public Mono<Map<String, String>> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        String traceId = exchange.getAttributeOrDefault("demo.traceId", "unavailable");

        return Mono.just(Map.of(
            "method", request.getMethod().name(),
            "path", request.getPath().value(),
            "traceId", traceId
        ));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.<Principal>getPrincipal()
            .map(principal -> Map.of(
                "user", principal.getName(),
                "path", exchange.getRequest().getPath().value()
            ));
    }
}
```

In `inspect`, the controller reads the exact attribute that the filter wrote **within the same exchange**. In `me`, `getPrincipal()` is the identity source provided by Spring Security integration after the security chain allows the request to reach the controller. There is no `block()`, `subscribe()`, or unnecessary session access.

### Running and Verifying

Requires JDK 17+ and a Gradle version compatible with Spring Boot 3.5 (or use the Gradle Wrapper generated for the project). Inside the `exchange-demo` directory:

```bash
gradle bootRun
```

If the project has a wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Plain `javac`/`java` commands are not sufficient here because the example needs Spring libraries and its dependency graph; Gradle resolves the classpath and launches the main class.

Open another terminal:

```bash
curl -i http://localhost:8080/public/exchange
curl -i http://localhost:8080/me
curl -i -u learner:demo123 http://localhost:8080/me
```

Expected:

| Request | Status | Observation |
| --- | --- | --- |
| GET `/public/exchange` without credentials | `200 OK` | JSON has `method=GET`, `path=/public/exchange`, `traceId`; header `X-Trace-Id` has the same value |
| GET `/me` without credentials | `401 Unauthorized` | Security rejects before the `me` controller runs; HTTP Basic may return `WWW-Authenticate` |
| GET `/me` with HTTP Basic `learner:demo123` | `200 OK` | JSON has `user=learner` and `path=/me` |

Sample JSON for the last request (field order may vary):

```json
{"user":"learner","path":"/me"}
```

The `traceId` value **changes per request**; do not hardcode a fake static output. If a client/browser automatically sends credentials or changes the `Accept` header, challenge/response details may differ, but the permit or authentication rules in the configuration above remain unchanged.

### Step-by-Step Walkthrough of the Example

1. The client sends `GET /me`. `TraceWebFilter` receives `ServerWebExchange`, reads `ServerHttpRequest.getId()`, and writes the attribute and response header.
2. Spring Security applies `SecurityWebFilterChain` and the `anyExchange().authenticated()` rule.
3. If credentials are missing, security issues a 401 challenge; `ExchangeController.me` is not invoked. The trace header may still be sent because the filter ran before security.
4. If HTTP Basic is valid, Spring Security holds a valid `Authentication` in the reactive context. Security lets the processing chain proceed.
5. `DispatcherHandler` routes to `me`, the exchange parameter is injected, `getPrincipal()` emits the principal, and `map(...)` constructs the JSON data.
6. WebFlux serializes the result and completes the response; surrounding filters can observe completion/error signals in their configured order.

## 7. When to Use exchange.mutate()?

You should not try to mutate every field on a request directly, because WebFlux abstractions typically use wrappers/decorators to represent changes. For example, a `WebFilter` that needs to add an **internal** header for downstream steps:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
    var newRequest = exchange.getRequest().mutate()
        .header("X-Internal-Lesson", "exchange")
        .build();

    ServerWebExchange updated = exchange.mutate()
        .request(newRequest)
        .build();

    return chain.filter(updated);
}
```

This is an **illustrative fragment** of a `WebFilter`, not a standalone application. `updated` is still the exchange for the same HTTP request, wrapped so downstream layers see the modified request. Never use adding a header yourself as a way to grant permissions or spoof a principal; client-supplied headers must be controlled at the trust boundary.

When you want to terminate early (for example, a filter proactively returning a status), return a publisher that completes the response instead of calling `chain.filter`. However, authentication/authorization policies should be managed by Spring Security; arbitrarily returning 403 from a custom filter easily breaks security sequencing.

## 8. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | Recommended Practice |
| --- | --- | --- |
| Calling `chain.filter(exchange).subscribe()` inside a filter and returning `Mono.empty()` | Creates a subscription outside the request lifecycle, breaking ordering and error handling | `return chain.filter(exchange)`, composing with reactive operators when needed |
| Calling `block()` in a controller/filter on the event loop | Blocks the non-blocking processing thread, hurting throughput or causing deadlock in some situations | Keep `Mono`/`Flux`; use reactive APIs; isolate blocking libraries on an appropriate scheduler when unavoidable |
| Reading `getPrincipal()` in a filter running before Spring Security and assuming a user is always present | Security context may not exist yet; public endpoints may also have no principal | Check filter ordering; read security context after authentication completes |
| Storing `Authentication` in a `ThreadLocal` manually | Reactive execution can switch threads | Use `ReactiveSecurityContextHolder` / Reactor `Context` |
| Trusting `exchange.getAttributes().get("role")` for authorization | Attributes are not trustworthy authentication results | Use security authorization and actual authorities |
| Reading the full `getBody()` in a filter and expecting the controller to read it again | The body stream may already be consumed; mishandling `DataBuffer` causes memory leaks | Let the framework decode or decorate/cache the body in a controlled way |
| Writing headers after the response has committed | Status/headers can no longer be modified | Write before the chain commits or use an appropriate response hook |
| Abusing `getSession()`/attributes for large data | Consumes memory, creates coupling, and can retain unintended state | Keep only small metadata with the proper lifecycle |
| Assuming `permitAll()` always provides a principal | `permitAll()` is an access decision, not an authentication directive | Handle `Mono.empty()` if the endpoint allows anonymous access |
| Using the Servlet `HttpSecurity` DSL for WebFlux | Does not match the reactive security stack | Use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `WebFilter` |

### Diagnosing a Request That Never Reaches the Controller

First check: does the HTTP method/path match the mapping; which `WebFilter` short-circuited early; which security matcher was selected; which rule denied access; did the request include valid credentials; did an error occur before the handler was called. Distinguish 401 (not validly authenticated) from 403 (authenticated, but insufficient permissions) within the specific configuration. Correlation IDs from the exchange help tie logs together, but never log passwords, Authorization headers, session cookies, or full sensitive bodies.

## 9. Self-Check

1. **How does `ServerWebExchange` differ from `ServerHttpRequest`?** The exchange wraps the request, response, and processing context; the request only describes the incoming request side.
2. **Why does `getPrincipal()` return `Mono`?** Because retrieving the principal follows the reactive model and may not be ready/present; you cannot assume `Principal` is available synchronously.
3. **Can `getAttributes()` replace a session?** No. Attributes live for the current exchange; a session can be managed across multiple requests.
4. **If `/me` returns 401, does the `me` controller run?** Under the example configuration, no. Security blocks the request before entering the controller.
5. **How do you pass a value from a filter to a controller within the same request?** Write `exchange.getAttributes().put(key, value)` in the filter, read `getAttribute(...)` in the controller, and continue with `chain.filter(exchange)`.
6. **What should you use to get roles/authorities for permission checks?** Spring Security authorization mechanisms or `Authentication` from the reactive security context; never trust query/header/attribute values on their own.

## 10. Takeaways

- `ServerWebExchange` is the **central object of a single HTTP exchange** in WebFlux; `WebFilter` instances and handlers share access to it.
- Spring Security in WebFlux is implemented via a **reactive `WebFilter` chain**, where `ServerWebExchange` serves as the input for matching, authentication, and authorization logic.
- Exchange attributes share data **within one request**; WebSession, Reactor Context, and SecurityContext have different scopes and semantics.
- Reactive flows must be **returned and composed**, never manually `subscribe()`d or blocked with `block()` inside handlers/filters.
- The final observable state is the **HTTP response**; 401/403 can be produced before the controller runs.

### Official References

- Spring Framework, Reactive Core / WebHandler and WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework, annotated controller arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework, `ServerWebExchange` API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Security, WebFlux configuration: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, authorize HTTP requests (reactive): https://docs.spring.io/spring-security/reference/7.2/reactive/authorization/authorize-http-requests.html
- Spring Security, `SecurityContextServerWebExchangeWebFilter` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
