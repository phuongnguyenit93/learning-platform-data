# ReactorContextWebFilter and Integrating Security Context into WebFlux Requests

## 1. Goal and Context

When processing an HTTP request with Spring WebFlux, work does not necessarily execute from start to finish on a single thread. A `Mono`/`Flux` sequence can switch threads when encountering `publishOn`, `subscribeOn`, or when asynchronous I/O completes. Therefore, reading user identity via `SecurityContextHolder.getContext()` in the Servlet `ThreadLocal` model is unreliable inside a reactive chain.

This lesson focuses on **`ReactorContextWebFilter`**: it coordinates `ServerSecurityContextRepository` with the **Reactor Context** so downstream processing can read `SecurityContext` through `ReactiveSecurityContextHolder`. After this lesson, you can:

1. Distinguish `ServerWebExchange`, Reactor `Context`, and Spring Security `SecurityContext`.
2. Explain where the filter obtains the security context, when it attaches it to the reactive subscription, and why it does not depend on threads.
3. Trace the context across HTTP Basic authentication, authorization, and WebFlux handlers.
4. Read the current user properly, configure the appropriate repository, and verify with requests/tests.
5. Recognize context-loss bugs caused by calling `subscribe()` manually, using `ThreadLocal`, or spawning tasks outside the reactive chain.

## 2. Three Similarly Named Types of "Context"

| Component | What does it hold? | Scope and access |
| --- | --- | --- |
| `ServerWebExchange` | Request, response, attributes, session, and utilities for a single HTTP exchange. | Flows through `WebFilter` and WebFlux handlers; accessed via the `exchange` parameter. |
| Reactor `Context` | Key/value data attached to a **subscription**, propagated across reactive operators. | `Mono.deferContextual(...)` to read, `contextWrite(...)` to add/modify. It is not itself an HTTP session. |
| Spring Security `SecurityContext` | `Authentication`: principal, authorities, and authentication status. | In reactive flows, use `ReactiveSecurityContextHolder.getContext()`; the API returns `Mono<SecurityContext>`. |

Two additional concepts to understand:

- `ServerSecurityContextRepository` decides **how to load/save** `SecurityContext` across requests (for example, in `WebSession`). It is the source of saved context; Reactor `Context` itself does not persist state across HTTP requests.
- `ReactiveSecurityContextHolder` is the dedicated API for reading/writing security context in **Reactor Context**, not a global storage container. Key APIs to remember are `getContext()`, `withAuthentication(authentication)`, and `withSecurityContext(Mono<SecurityContext>)`.

Picture an already logged-in user: the repository can restore the HTTP session's `SecurityContext`; `ReactorContextWebFilter` attaches a publisher carrying that context to the subscription processing the request; the controller or authorization check can extract the identity from the same reactive chain.

## 3. What Does ReactorContextWebFilter Actually Do?

Full class name: `org.springframework.security.web.server.context.ReactorContextWebFilter`. This is a `WebFilter` in **Spring Security WebFlux**, receiving a `ServerSecurityContextRepository` via its constructor.

According to the source code, its core logic is:

1. Let the rest of the `WebFilterChain` continue processing the request.
2. Attach a `contextWrite(...)` operation to the resulting publisher to configure the Reactor Context for the subscription.
3. If the Reactor Context already contains the key corresponding to `SecurityContext.class`, preserve the existing context. That ensures a context provided by another part of the chain is not overwritten.
4. Otherwise, obtain `Mono<SecurityContext>` from `repository.load(exchange)` and place that publisher into the Reactor Context via `ReactiveSecurityContextHolder.withSecurityContext(...)`.

Subtle point: the filter places **`Mono<SecurityContext>`** into the Context. That does not mean it always has to authenticate the user at the instant the WebFilter is invoked; subscribing and running the context-loading flow happen reactively. `load(exchange)` may return `Mono.empty()` if no context was saved.

Conceptual flow:

```text
HTTP request
    |
    v
Spring Security WebFilter chain
    |
    +--> ReactorContextWebFilter
    |      \-- repository.load(exchange)
    |           \-- provides Mono<SecurityContext> to Reactor Context
    |
    +--> AuthenticationWebFilter (when a matching authentication mechanism is present)
    |      \-- if authentication succeeds: places new Authentication into context
    |
    +--> AuthorizationWebFilter / authorization checks
    |      \-- reads Authentication in the reactive context
    |
    +--> WebFlux handler / service
           \-- ReactiveSecurityContextHolder.getContext()
```

**Do not confuse responsibilities:** `ReactorContextWebFilter` does not verify passwords itself, does not issue tokens, and does not automatically call `save(...)` for every request. Verifying credentials belongs to authentication filters/mechanisms; saving context depends on the repository and successful authentication configuration. This filter primarily **makes the readable context available to the reactive subscription**.

## 4. Position in the Security Chain and Interaction with Other Filters

Spring Security defines `SecurityWebFiltersOrder.REACTOR_CONTEXT` for the position of `ReactorContextWebFilter`. It stands before HTTP Basic, form login, authentication, and authorization positions so the context is ready for subsequent steps. When standard WebFlux security is enabled via `@EnableWebFluxSecurity` and a `SecurityWebFilterChain`, the framework assembles the necessary components; normal applications **do not need to manually instantiate and register an extra `ReactorContextWebFilter`**.

Related roles:

- `AuthenticationWebFilter`: if a request matches the matcher and carries login credentials, converts the request into an `Authentication`, invokes `ReactiveAuthenticationManager`, and places the successful result into `ReactiveSecurityContextHolder`. Depending on configuration, the success handler saves the context via the repository.
- `ReactorContextWebFilter`: provides access to the **`SecurityContext` saved in the repository** when the reactive context does not already have one.
- `SecurityContextServerWebExchangeWebFilter`: makes `ServerWebExchange.getPrincipal()` reference the identity supplied by `ReactiveSecurityContextHolder`. It serves reading the principal from `exchange`, distinct from `ReactorContextWebFilter`'s context-loading role.
- `AuthorizationWebFilter`: uses authentication details to evaluate access rules configured in `authorizeExchange`.

Timeline examples:

**Request A – supplying login credentials:** context in the repository may not exist yet; `AuthenticationWebFilter` authenticates the request's own credentials, puts the new identity into the reactive chain, and may persist the context if the login mechanism is configured to do so.

**Request B – returning with a valid HTTP session:** the repository can load the context from the previous login; `ReactorContextWebFilter` places it into the Reactor Context for downstream components to use.

**Request C – stateless, carrying token/Basic credentials every time:** no session holding an old context is needed; the corresponding authentication filter must authenticate each request's credentials. You cannot rely solely on `ReactorContextWebFilter` to infer identity when the repository saves nothing.

## 5. Runnable WebFlux Example: Reading Authentication from Reactor Context

The example uses **Java 17+**, **Spring Boot 3.5.16**, Maven, WebFlux, and Spring Security. Credentials `demo/secret` and `{noop}` are used **strictly for local practice**; real applications must hash passwords and manage secrets securely.

Project structure:

```text
reactor-context-demo/
├── pom.xml
├── src/main/java/demo/reactorcontext/DemoApplication.java
└── src/test/java/demo/reactorcontext/SecurityContextIntegrationTest.java
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactor-context-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/demo/reactorcontext/DemoApplication.java`:

```java
package demo.reactorcontext;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(basic -> {})
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("demo")
            .password("{noop}secret")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "Hello, " + auth.getName());
    }

    @GetMapping("/principal")
    public Mono<String> principal(ServerWebExchange exchange) {
        return exchange.getPrincipal().map(Principal::getName);
    }
}
```

`securityWebFilterChain` requires an authenticated user at `/whoami` and `/principal`. `httpBasic` handles HTTP Basic authentication; `formLogin` is disabled so requests without Basic credentials are handled as an HTTP API rather than redirected to a login form. `/whoami` reads `SecurityContext` directly from the Reactor Context; `/principal` demonstrates the bridge via `ServerWebExchange.getPrincipal()`.

Run the application from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -s http://localhost:8080/public
curl -s -u demo:secret http://localhost:8080/whoami
curl -s -u demo:secret http://localhost:8080/principal
curl -i http://localhost:8080/whoami
```

Body output of the first three commands, in order:

```text
public
Hello, demo
demo
```

The final command receives **HTTP 401 Unauthorized** when valid credentials are not provided; exact error headers and body may vary by version/configuration. `curl -s` does not append a newline, so when run consecutively in a terminal, bodies may appear on the same line even though each output shown above is exact.

Why not manually invoke `new ReactorContextWebFilter(...)`? `@EnableWebFluxSecurity` and `SecurityWebFilterChain` already assemble the security chain; registering a duplicate filter manually can create hard-to-trace execution paths.

## 6. Verifying with WebTestClient

Create `src/test/java/demo/reactorcontext/SecurityContextIntegrationTest.java`:

```java
package demo.reactorcontext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityContextIntegrationTest {
    @Autowired
    WebTestClient client;

    @Test
    void basicCredentialsAreAvailableFromReactorContext() {
        client.get().uri("/whoami")
            .headers(headers -> headers.setBasicAuth("demo", "secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Hello, demo");
    }

    @Test
    void securityRulesApplyToTheRequest() {
        client.get().uri("/whoami")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }
}
```

Run `mvn test`. The test suite observes both links in the chain: HTTP requests pass through the filter chain, and the authenticated identity can be read in the WebFlux handler via `ReactiveSecurityContextHolder`. Both tests are expected to pass. This is a behavioral integration test; there is no need to write tests for the internal code of `ReactorContextWebFilter`.

You can also isolate the Reactor Context mechanism without running an HTTP server:

```java
Authentication auth =
    new TestingAuthenticationToken("alice", "unused", "ROLE_USER");

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(name)
    .expectNext("alice")
    .verifyComplete();
```

This last snippet is **an excerpt inside a test**, not a standalone Java file. You need to import `Authentication`, `TestingAuthenticationToken`, `Mono`, `SecurityContext`, `ReactiveSecurityContextHolder`, `StepVerifier` and include the `reactor-test` dependency in test scope. It proves `contextWrite` attaches an `Authentication` to the **current subscription** so upstream code can read the context; no repository or HTTP filter is invoked in this test.

## 7. Reading and Propagating Context Properly in Services

For example, reading the current user and then calling a reactive service:

```java
public Mono<String> currentGreeting(UserGreetingService service) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> auth.getName())
        .flatMap(service::greetingFor);
}
```

This is an **illustrative method**, assuming `UserGreetingService.greetingFor(String)` returns `Mono<String>`. Keep the pipeline subscribed to by WebFlux; `SecurityContext` information follows the chain of Reactor operators, even when the same chain switches threads using standard Reactor schedulers.

To handle the case when no user is present:

```java
public Mono<String> optionalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> auth.getName())
        .defaultIfEmpty("anonymous");
}
```

Note: `defaultIfEmpty` applies only when the publisher emits no value; it does not replace **authorization checks** at the endpoint. Rules such as `authenticated()`, `hasRole(...)`, or method security remain what decides who may access data.

An important example of Reactor Context propagation direction:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

`contextWrite` at the end of the sequence sets the context for **earlier (upstream) operators** within the same subscription. Reactor Context propagates along the subscribe flow from downstream to upstream. Therefore you should not treat it as a global variable automatically present for every publisher across the application.

## 8. Sessions, Stateless Requests, and Where Identity Is Stored

**`WebSessionServerSecurityContextRepository`** saves/reads `SecurityContext` using WebFlux's `WebSession`. It is useful when the application maintains login across sessions. The repository has two main methods:

- `load(ServerWebExchange) -> Mono<SecurityContext>`: loads the context associated with the request; may return `Mono.empty()`.
- `save(ServerWebExchange, SecurityContext) -> Mono<Void>`: saves the context according to the implementation's policy.

**`NoOpServerSecurityContextRepository`** does not retain context between requests. It fits models where each request authenticates itself via Basic credentials, bearer tokens, etc. However, **complete statelessness** requires checking authentication mechanisms, success handlers, request caches, and any components that might use a session; swapping only the repository used for `load` is not enough to prove the entire application never creates a session.

If you want to customize the repository, the main configuration point is:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        ServerSecurityContextRepository repository) {
    return http
        .securityContextRepository(repository)
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(basic -> {})
        .build();
}
```

This is **an illustrative configuration replacing the bean in section 5**; do not declare two identical `SecurityWebFilterChain` beans at the same time. The `repository` instance must be supplied by the application; how an authentication filter **saves** context may require separate configuration on that filter itself. `ServerHttpSecurity.securityContextRepository(...)` controls the context source used by `ReactorContextWebFilter`; do not assume it changes the entire save policy of every authentication type.

## 9. Common Errors and Diagnostics

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `SecurityContextHolder.getContext()` is empty or wrong user in WebFlux | Reading `ThreadLocal`-based context in an asynchronous sequence. | Use `ReactiveSecurityContextHolder.getContext()` in `Mono`/`Flux`. |
| `ReactiveSecurityContextHolder.getContext()` is empty | No valid session/token; route is unprotected; context was not created/attached to the subscription; or a test built a publisher outside HTTP. | Check matchers/filter chain, auth filter, repository, and in unit tests use `contextWrite(withAuthentication(...))`. |
| Identity present in controller but lost in another task | Calling `subscribe()` manually, creating a new subscription without context, or using `CompletableFuture`/custom executors without propagating context. | Keep processing in a single reactive chain, compose with `flatMap`/`then`, and return the publisher to the framework. |
| Assuming `publishOn` drops context | Confusing Reactor Context with `ThreadLocal`. | With standard Reactor operators, context belongs to the subscription and is independent of thread names; check boundaries leaving the Reactor chain. |
| `exchange.getPrincipal()` differs from expectations | Confusing the principal bridge with `SecurityContext` restoration, or the request is unauthenticated. | Inspect `SecurityContextServerWebExchangeWebFilter`, authentication, and endpoint permissions. |
| Subsequent request is no longer logged in | Stateless repository, missing session/cookie, or the authentication filter did not save context as expected. | Check `ServerSecurityContextRepository`, cookies/sessions, and save configuration in the authentication flow. |
| Can read context locally but cannot call downstream APIs | Reactor Context does not automatically forward tokens over HTTP when calling `WebClient`. | Configure outbound client/OAuth2 token propagation appropriately; never copy credentials arbitrarily. |

A systematic diagnostic order: confirm whether the request goes through the right `SecurityWebFilterChain`; check where credentials are converted into `Authentication`; check whether `repository.load(exchange)` holds a context; finally trace **the same subscription** into the handler. When logging, record only the minimal fields needed for diagnosis; avoid logging passwords, bearer tokens, session cookies, or the entire `SecurityContext`.

## 10. Self-Check Questions

1. **If `ServerSecurityContextRepository.load(exchange)` returns empty, does `ReactorContextWebFilter` create an authenticated user itself?** No. It only provides a path to read context; current authentication must be performed by another authentication mechanism.
2. **Why does `ReactiveSecurityContextHolder.getContext()` return `Mono<SecurityContext>` instead of an immediate object?** Because the value depends on the subscription's Reactor Context and the source of the security context may be asynchronous.
3. **Do you need to manually register `ReactorContextWebFilter` for every `@RestController`?** No, the standard Spring Security WebFlux chain already configures the corresponding filter.
4. **Are `ReactorContextWebFilter` and `SecurityContextServerWebExchangeWebFilter` the same?** No. One brings context from the repository into the Reactor Context; the other integrates `getPrincipal()` on `ServerWebExchange` with the reactive context.
5. **Does `contextWrite` save the user for tomorrow's HTTP request?** No. It affects the current subscription; cross-request state must rely on sessions/tokens or another persistence strategy.
6. **How do you verify real integration?** Send a request with credentials to a protected endpoint, verify the handler reads the right identity, then send a request without credentials and confirm it is rejected.

## 11. Official Documentation

- `ReactorContextWebFilter` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- `ServerSecurityContextRepository` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- `SecurityContextServerWebExchangeWebFilter` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
- WebFlux Security Guide: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- `ReactorContextWebFilter` Source Code: https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/context/ReactorContextWebFilter.java
