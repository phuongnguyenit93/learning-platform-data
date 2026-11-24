# Authentication Scope in Servlet and Reactive Applications

## Learning Objectives

In Spring Security, "authentication scope" answers four questions: **which requests** must authenticate; **which evidence** is verified; **where the authenticated identity** is held and accessed; and **how long** that identity remains valid. Upon completing this lesson, you will be able to:

1. Point out where Spring Security intercepts requests in Servlet/Spring MVC and reactive/Spring WebFlux applications.
2. Distinguish `Authentication`, `SecurityContext`, authentication filters, security chains, and session persistence mechanisms.
3. Explain why Servlet primarily uses `ThreadLocal` while WebFlux uses **Reactor Context**; handle losing the principal when switching execution contexts.
4. Distinguish per-request authentication, session-restored authentication, and per-request bearer-token authentication.
5. Write and run basic configurations for each stack; recognize `200`, `401`, and `403` responses.

**Scope:** authentication for HTTP requests in Spring Security 6+ / Spring Boot 3+. OAuth 2.0/OIDC, JWT, MFA, session management, and in-depth authorization are mentioned where needed to illustrate boundaries; they are not full implementation targets of this overview lesson.

## 1. Where Does Authentication Begin and End?

**Authentication** verifies identity from server-trusted evidence: username/password, HTTP Basic, a cookie pointing to a logged-in session, bearer token, client certificate, or a custom-configured mechanism. **Authorization** uses that outcome to decide access permissions. The two steps are related yet not identical: someone can log in validly and still be denied an endpoint requiring higher privileges.

Core objects:

- `Authentication` holds `principal` (who), `credentials` (evidence; typically erased after authentication), `authorities` (roles/scopes/permissions), and related status.
- `SecurityContext` holds `Authentication` for the current context.
- Authentication filters read evidence, call credential-verifying components, and publish a successful `Authentication` into the context.
- Authorization components rely on the context and endpoint/method protection rules to decide allow or deny.

A request entering Spring Security typically follows this model:

~~~text
Client sends HTTP request
  -> Select security chain matching the request
  -> Load prior SecurityContext (if any)
  -> Read/verify credentials and create Authentication when needed
  -> Check authorization
  -> Controller/handler -> service
  -> Complete request; release execution context
     and save identity for future requests if the mechanism allows
~~~

Every subsequent HTTP request has a fresh processing turn. "Logged in" does not mean a single Java `SecurityContext` object lives permanently in the application. A new request's context can be **restored** via session or **rebuilt** after verifying a token.

**Anonymous does not mean logged in.** An `AnonymousAuthenticationToken` can still return `isAuthenticated() == true`. Therefore, never rely solely on this flag to conclude a real user is authenticated; use `authenticated()` and corresponding Spring Security rules.

Spring Security only protects entry points actually inside a security chain. Scheduled jobs, message consumers, CLIs, post-request background tasks, or calls to other services do not automatically receive a valid HTTP identity.

## 2. Servlet Applications: Authentication Bound to Request and Processing Thread

### 2.1. Spring MVC Filter Chain

In the Servlet stack, `DelegatingFilterProxy` bridges the Servlet container's filter to the Spring Bean `FilterChainProxy`. `FilterChainProxy` finds the first `SecurityFilterChain` matching the request and runs the associated filters; configured via `HttpSecurity`.

| Component | Responsibility |
| --- | --- |
| `SecurityFilterChain` | Defines which requests belong to the chain and which authentication/authorization filters apply |
| `AuthenticationManager` | Interface validating incoming `Authentication`; typically `ProviderManager` |
| `AuthenticationProvider` | Handles one specific type of evidence, such as username/password |
| `SecurityContextHolder` | Holds the current `SecurityContext`, backed by `ThreadLocal` by default |
| `SecurityContextRepository` | Restores/saves context across requests if needed |
| `AuthenticationEntryPoint` | Prompts for login or returns an HTTP authentication challenge when evidence is insufficient |

HTTP Basic example: the client sends header `Authorization: Basic ...`; the filter reads the value, calls `AuthenticationManager`, and on success places `Authentication` into the context. If a request lacks credentials for a path requiring authentication, Spring Security typically responds with `401 Unauthorized` and a challenge. With form login, after logging in once, the browser can send a session cookie on subsequent requests to retrieve the identity.

### 2.2. SecurityContextHolder and the Limits of ThreadLocal

When handling a Servlet HTTP request inside a security chain, synchronous code on the current thread can read:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
~~~

This is **illustrative code inside a method of a Servlet application**, not a standalone program. Import `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. In a Spring MVC controller, a `Principal` or `Authentication` parameter is usually clearer than calling the holder directly.

`ThreadLocal` avoids passing identity manually through every synchronous call; however, it **does not safely propagate to other threads automatically**. `@Async`, `ExecutorService`, `CompletableFuture`, out-of-request callbacks, and manually spawned threads may lack the expected context. Depending on the use case, use Spring Security's `SecurityContext` propagation mechanisms (the `DelegatingSecurityContext*` family), or design an independent service identity. Spring Security clears the context after the request so pooled threads do not accidentally carry the previous user's identity.

### 2.3. Living Across One Request or Many?

- **Per-request:** credentials are verified in the current request; the context serves that request's processing.
- **Session-based:** with form login, `SecurityContextRepository` can use `HttpSession` to save/restore identity. The cookie sent by the client is only a way to identify the session, not the entire user data.
- **Bearer token-based:** the client typically sends the token on every request; the resource server validates the token and builds the identity for that call without necessarily relying on `HttpSession`.

Distinguish **setting a temporary context** from **saving for restoration on later requests**. In Spring Security 6+, `SecurityContextHolderFilter` loads the context but does not automatically save every change. If you handle login manually in a custom filter/controller and want login to persist, you must save the context with `SecurityContextRepository.saveContext(context, request, response)`. Built-in login flows handle saving according to configuration.

For Servlet APIs authenticating with tokens, `SessionCreationPolicy.STATELESS` is often used to avoid relying on `HttpSession` for `SecurityContext`. However, a stateless Spring Security configuration does not prove the entire application never creates sessions for other purposes.

## 3. Reactive Applications: Authentication Bound to the Reactor Pipeline

### 3.1. WebFlux Filters and APIs

WebFlux uses `WebFilter`, `ServerWebExchange`, and `Mono`/`Flux` publishers. Spring Security selects a matching `SecurityWebFilterChain` for the request and configures it with `ServerHttpSecurity`:

- `AuthenticationWebFilter` and appropriate authentication web filters convert the request into an incoming `Authentication` (typically via `ServerAuthenticationConverter`).
- `ReactiveAuthenticationManager` handles authentication with an asynchronous interface and returns `Mono<Authentication>`.
- `ReactiveSecurityContextHolder` retrieves the context from **Reactor Context**, i.e., context bound to the reactive subscription.
- `ServerSecurityContextRepository` determines how the context is read/saved; `WebSessionServerSecurityContextRepository` can use `WebSession`.

A proper snippet reading identity in a reactive pipeline:

~~~java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

This is **illustrative code placed inside a WebFlux pipeline where Spring Security has already established the context**. Import `ReactiveSecurityContextHolder`, `SecurityContext` from `org.springframework.security.core.context`, and `Authentication` from `org.springframework.security.core`.

### 3.2. Why Not Use ThreadLocal for WebFlux?

A reactive chain can switch threads across operators or schedulers while still belonging to the same request/subscription. `ThreadLocal` is a property of a thread, so it cannot stably represent the user across the entire reactive stream. Reactor Context follows the publisher/subscription propagation mechanism; Spring Security integrates that mechanism into the HTTP pipeline.

Actions such as calling `subscribe()` manually on a detached stream, creating callbacks outside the pipeline, or bridging into APIs that drop Reactor Context can lose authentication information. Do not substitute `SecurityContextHolder.getContext()` out of Servlet habit; keep the publisher chain intact and obtain `ReactiveSecurityContextHolder.getContext()` where used.

In tests or separately managed flows, Spring Security provides `ReactiveSecurityContextHolder.withAuthentication(authentication)` combined with the `contextWrite(...)` operator. Attaching context must use a verified `Authentication`; never turn a client-claimed username string into a trusted identity.

### 3.3. Reactive Does Not Mean Stateless

WebFlux can still use **WebSession** for form login and preserve identity across multiple requests. If a reactive API uses bearer tokens, you may choose not to save context across exchanges, for instance with `NoOpServerSecurityContextRepository`. Selecting this repository does not automatically disable all `WebSession` features in the application.

An OAuth2 resource server configuration (JWT or opaque token) must validate tokens through a trusted decoder/introspector, while checking conditions such as issuer/audience when appropriate. Spring Security's resource server validates incoming tokens; it does not by default provide an endpoint that issues tokens to clients.

## 4. Direct Comparison of Servlet and Reactive

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP interception point | Servlet `Filter` / `SecurityFilterChain` | `WebFilter` / `SecurityWebFilterChain` |
| DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Reading context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Where context travels by default | Current thread's `ThreadLocal` | Subscription's Reactor Context |
| Persistence across requests | `SecurityContextRepository`, e.g., `HttpSession` | `ServerSecurityContextRepository`, e.g., `WebSession` |
| URL rules | `authorizeHttpRequests().requestMatchers(...)` | `authorizeExchange().pathMatchers(...)` |
| Reading principal in handler | `Principal`/`Authentication` or holder | Reactor Context or appropriate reactive principal parameter |

**Choose according to the application's stack, not inferred from container name.** WebFlux can run on different HTTP runtimes. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are included in one Spring Boot application, Spring MVC is typically chosen by default. Pick one model clearly and use the matching security API set.

## 5. Java 17+ Code for Two Independent Applications

Create **two separate Spring Boot projects** using Spring Initializr (Spring Boot 3.x, Java 17 or 21). For the Servlet project choose **Spring Web** + **Spring Security**; for the reactive project choose **Spring Reactive Web** + **Spring Security**. Place the following files in `src/main/java/com/example/demo/` of each project. The examples use an in-memory user and demo password strictly for local development testing; production requires an appropriate identity source, secret management, and HTTPS.

### 5.1. Servlet: `ServletAuthApplication.java`

~~~java
package com.example.demo;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ServletAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/me")
        String me(Principal principal) {
            return principal.getName();
        }
    }
}
~~~

`/public` allows anonymous access; `/me` requires authentication. The same thread processing the Servlet request can see the context, and Spring MVC injects the identity into the `Principal` parameter. `httpBasic(...)` enables HTTP Basic authentication without writing a custom filter.

### 5.2. WebFlux: `ReactiveAuthApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("public");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
        }
    }
}
~~~

Both applications share the **same URL policy**, yet WebFlux returns publishers and reads the principal via Reactor Context. Do not port the WebFlux snippet to `HttpSecurity` / `SecurityContextHolder` without changing the application model.

### 5.3. Running and Expected Results

Run one project at a time, since both use port 8080 by default:

~~~bash
./mvnw spring-boot:run
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong-password http://localhost:8080/me
~~~

If creating a Gradle project, use `./gradlew bootRun`; on Windows PowerShell you can call `curl.exe` to avoid aliases with different behavior.

| Request | Expected status | Observable body content |
| --- | --- | --- |
| `GET /public` without credentials | `200 OK` | `public` |
| `GET /me` without credentials | `401 Unauthorized` | Basic challenge, no username leaked |
| `GET /me` with `alice:demo-pass` | `200 OK` | `alice` |
| `GET /me` with wrong password | `401 Unauthorized` | No username leaked |

Do not assume exact header order or charset since it may depend on runtime. Each `/me` request authenticates the evidence used by the filter; this example does not demonstrate enabling session persistence. Both endpoints use only GET, so CSRF does not need to be disabled for testing.

## 6. "Passing Through the Chain" Differs from "Must Log In"

This is the most commonly confused configuration boundary, especially when an application has multiple authentication flows:

1. **Selecting a chain:** `securityMatcher(...)` decides which requests belong to a `SecurityFilterChain` / `SecurityWebFilterChain`. When multiple chains exist, Spring Security evaluates priority order and uses the first matching chain.
2. **Permission decisions inside the chain:** `requestMatchers("/public").permitAll()` (Servlet) or `pathMatchers("/public").permitAll()` (WebFlux) lets public requests proceed but **does not remove other authentication filters** in the chain.
3. **No matching chain:** HTTP requests are not protected by those Spring Security chains. This can be a dangerous configuration gap, not equivalent to a `permitAll` rule inside a managed chain.

For example, an application has `/api/**` for bearer tokens and `/web/**` for form login: each part can use its own chain. In that case, matchers and ordering must be explicit; an overly broad chain prioritized first can prevent the other chain from ever running. A `GET /public` request carrying invalid credentials may still be rejected by a filter before the `permitAll` rule is evaluated, depending on the mechanisms enabled in the chain.

HTTP rules also do not replace business-method authorization. With Servlet, enable `@EnableMethodSecurity` if `@PreAuthorize` is needed on services; with WebFlux use `@EnableReactiveMethodSecurity`, and design appropriate reactive return types/methods. Add checks in the service layer when the same business logic is invoked from multiple entry points.

## 7. Time Scope: Session, Basic, Bearer, and Other Backends

### Browser Login with Sessions

The browser sends credentials the first time. If authentication succeeds and saving to a session is configured, the client holds a session identifier cookie. Subsequent requests still **go through the security chain**, yet the server can restore identity from `HttpSession` (Servlet) or `WebSession` (WebFlux) without making the user re-enter their password. Session lifetime differs from a single-request context lifetime. Logout, session timeout, cookie flags, CSRF, and session fixation are related security concerns with their own policies.

### APIs Using Basic or Bearer Tokens

HTTP Basic sends credentials on every request; use only over HTTPS. With bearer JWTs, the server typically validates the token on every request (signature/issuer/expiration and related policies), builds the current `Authentication`, and checks permissions. JWTs do not inherently require sessions, nor does a resource server automatically issue JWTs. The `Authorization` header must be kept secret; never place tokens in URL queries or logs.

### Reverse Proxy / API Gateway

If a gateway authenticates users and forwards identity down to a backend, the backend must have a verifiable **trust boundary**: protected transport channel, direct-access restrictions, or appropriate signatures/mTLS. Never blindly trust self-declared headers like `X-User-Id` from arbitrary clients. Spring Security on the backend knows only the evidence the backend itself actually verifies.

### Scheduled Jobs, WebSockets, and Message Consumers

A scheduled task or message listener does not automatically have an HTTP request's `SecurityContext`. A WebSocket handshake may involve the initial HTTP identity, yet the connection/message lifetime needs its own policy. For background tasks, design a service principal/token or check permissions for that entry point directly; never retain references to an already-finished request's context.

## 8. Scope Across Threads and Asynchronous Tasks

**Servlet:** `SecurityContextHolder` binds to `ThreadLocal` by default. A synchronous call within the same request usually sees the identity; calls running via `@Async`/executors may not. If business logic needs to carry user identity across that boundary, use a supported propagation mechanism and control when context is cleared to prevent leakage across tasks.

**WebFlux:** context flows through publishers/subscriptions. Chains of `flatMap`, `map`, or scheduler switches can still access Reactor Context when staying inside the proper pipeline. However, creating a detached subscription outside the context or calling callback libraries that do not propagate context can lose the principal. Avoid `block()` on the event loop, and never fix the issue by setting a global `SecurityContextHolder`.

A helpful debugging question: **who creates the new execution boundary, and does it propagate the verified identity across that boundary?** Solutions depend on the stack and task semantics, not solely on Spring Security method names.

## 9. Quick Diagnostics for 401, 403, and Lost Context

| Symptom | What to check |
| --- | --- |
| `401 Unauthorized` | Request missing/invalid credentials, bad/expired token, Basic challenge, or authentication mechanism failed |
| `403 Forbidden` | Authenticated but missing matching authority; for state-changing requests also check CSRF and related config |
| URL meant to be private returns `200` | Wrong chain matcher/order, overly broad `permitAll`, or request matched no chain |
| Servlet loses principal in async tasks | `ThreadLocal` does not follow new executor/thread automatically; check context propagation |
| WebFlux sees empty principal outside pipeline | Subscription was detached or wrong holder used; need Reactor Context |
| Custom login succeeds then next request is anonymous | Context was only set temporarily, not saved to `SecurityContextRepository`/`ServerSecurityContextRepository` when needed |
| Preflight `OPTIONS` fails before login | Configure CORS at gateway/chain, because preflight normally carries no credentials like the main request |
| Service-layer authorization does not run | Method security not enabled, bean bypassed proxy, or unsupported execution style |

When debugging, log only necessary metadata such as request path, status, auth mechanism type, and correlation ID. **Never log passwords, session cookies, raw JWTs, or full Authorization headers.** Never disable CSRF on an application with browser sessions/cookies just to bypass a `403`.

## 10. Self-Check with a Real Application

Verify in order:

1. Does the project use Spring MVC/Servlet or WebFlux/reactive? Is the right `SecurityFilterChain` or `SecurityWebFilterChain` used?
2. Which chain does the request enter? Do matchers and priority order cover every sensitive endpoint?
3. Who is the principal, where are credentials extracted from, and which component verifies them?
4. Is the call's context loaded from a session or freshly built from a token? Is the persistence policy appropriate?
5. Are controllers and services reading context via `ThreadLocal` or Reactor Context? Do any async boundaries drop it?
6. Have you verified public paths (`200`), missing credentials (`401`), valid credentials (`200`), and insufficient permissions (`403` when role/authority rules exist)?
7. Are there non-HTTP entry points (jobs, messages, gateway callbacks) needing independent authentication/authorization mechanisms?

**Knowledge takeaway:** Spring Security identifies the caller at protected request boundaries and places the identity into `SecurityContext` for downstream steps. Servlet passes context via **threads** by default, while WebFlux passes it via **Reactor subscriptions**. Sessions and tokens govern how callers are re-identified on subsequent requests; they are an orthogonal dimension to the execution scope of the current request.

## References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
