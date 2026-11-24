# The Relationship Between Spring WebFlux, Reactor, and Spring Security

## 1. Lesson Objectives

After this lesson, you will be able to explain the distinct roles of Spring WebFlux, Project Reactor, and Spring Security in a reactive HTTP application; describe how a request passes through the security filters; understand why user information is propagated via Reactor Context; and run a WebFlux API with both public and authenticated endpoints.

**Key point:** Spring WebFlux is the web processing layer; Reactor is the asynchronous programming foundation for processing chains; Spring Security is the authentication, authorization, and request protection layer. Spring Security on WebFlux must participate in Reactor's reactive chain to enforce access control properly.

## 2. Three Components Solving Three Different Problems

| Component | Main responsibility | Typical concepts/APIs |
| --- | --- | --- |
| **Spring WebFlux** | Accepts HTTP, routes requests, reads/writes request-response, and invokes handlers asynchronously without blocking | `WebHandler`, `WebFilter`, `@RestController`, `RouterFunction`, `WebClient` |
| **Project Reactor** | Represents and composes operations that can complete asynchronously; supports Reactive Streams and backpressure | `Mono<T>` (0 or 1 element), `Flux<T>` (0 to many elements), `map`, `flatMap`, `Context` |
| **Spring Security (reactive)** | Authenticates identity, decides access permissions, and provides security context inside the reactive chain | `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveAuthenticationManager`, `ReactiveSecurityContextHolder` |

WebFlux depends on `reactor-core` and typically returns `Mono`/`Flux`. For example, an endpoint returning `Mono<String>` describes work that may produce a string upon completion; the framework manages subscribing and writing the result as an HTTP response. `Mono`/`Flux` does not mean automatically spawning additional execution threads, nor does it turn a JDBC call, `Thread.sleep`, or blocking I/O task into non-blocking work.

Spring Security has two integrations tailored for two web stacks: **Servlet/Spring MVC** and **Reactive/Spring WebFlux**. This lesson focuses on the second approach. WebFlux can use annotated controllers or functional endpoints; the reactive security filters protect both.

## 3. How They Connect When an HTTP Request Arrives

~~~text
Client sends HTTP request
          |
          v
HTTP server (typically Reactor Netty with Boot WebFlux starter)
          |
          v
Spring WebFlux: WebFilter / WebHandler chain
          |
          v
Spring Security: WebFilterChainProxy
    -> selects matching SecurityWebFilterChain
    -> reads credentials and authenticates when needed
    -> puts SecurityContext into Reactor Context
    -> checks authorization rules
          |
          +-- denied --> appropriate error response (e.g., 401/403)
          |
          v
WebFlux handler -> service -> Mono/Flux -> HTTP response
~~~

This is a conceptual diagram, not an exact list or fixed order of every filter. A request may pass through multiple security filters depending on configuration; if multiple `SecurityWebFilterChain` beans exist, Spring Security chooses the matching chain by matcher and precedence order.

Flow to understand:

1. **WebFlux receives the request** via non-blocking HTTP infrastructure and the `WebFilter` chain.
2. **Spring Security hooks into WebFlux via `WebFilter`**; `WebFilterChainProxy` applies the filters inside the selected `SecurityWebFilterChain`.
3. **Authentication**: with HTTP Basic in the example below, the filter extracts credentials and uses the reactive authentication mechanism; typically `ReactiveAuthenticationManager.authenticate(...)` returns `Mono<Authentication>`. Not all login mechanisms use the same filter.
4. **SecurityContext** holds the `Authentication` (principal, authorities, authentication status) and is made available to the Reactor chain handling the request.
5. **Authorization**: rules such as `permitAll`, `authenticated`, `hasRole`, ... decide whether the request is allowed to proceed.
6. **Handler runs and produces a result** as a `Mono`/`Flux`; WebFlux writes the response when the chain completes or handles errors if the chain fails.

**Distinction:** Authentication answers "Who are you?"; Authorization answers "What are you allowed to do?". Do not conclude a request is authorized solely because login succeeded.

## 4. Why Is Reactor Context Especially Important for Security?

In traditional Servlet processing, code often reads `SecurityContextHolder` in the context of the thread handling the request; its default strategy relies on `ThreadLocal`. In the reactive model, a processing flow can switch threads when executing operators or when I/O completes. Therefore, obtaining the "current user" based solely on the thread is very error-prone.

**Reactor Context** attaches data to the **subscription of a Reactor chain**, rather than to a thread. Spring Security reactive uses `ReactiveSecurityContextHolder` to access `SecurityContext` through this mechanism. As long as the chain remains within the appropriate Reactor Context scope, operators can access the same security information even across thread switches.

Example of reading the logged-in username inside a reactive chain:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
~~~

This is an **illustrative snippet inside a class with full imports**, not a standalone program. `getContext()` returns `Mono<SecurityContext>`; if no context is present, the chain may complete without emitting a value. This snippet is suited for an already authenticated request; it does not replace the authorization step.

When you need to set authentication for a manually constructed reactive chain (for example, in tests), you can use:

~~~java
Authentication auth = new UsernamePasswordAuthenticationToken(
        "demo", "N/A", List.of(new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

This second illustrative snippet assumes the corresponding imports from `org.springframework.security.authentication`, `org.springframework.security.core.authority`, `org.springframework.security.core.context`, `java.util`, and Reactor. When subscribing to `username`, the chain emits `demo`. `contextWrite(...)` puts the authentication into the Context visible to upstream operators; calling `contextWrite` does not authenticate credentials by itself.

In a WebFlux application with Spring Security, the security infrastructure establishes the context for the request according to the configured mechanism; normally **you do not manually call `contextWrite` in every controller**. Nor should you use Servlet-style `SecurityContextHolder.getContext()` in place of `ReactiveSecurityContextHolder.getContext()`.

## 5. Runnable Example with Java 17+ and Spring Boot WebFlux

### 5.1. Create the project

At [Spring Initializr](https://start.spring.io/), choose **Maven**, **Java 17 or higher**, a stable Spring Boot version compatible with the chosen Java version, group `com.example`, and artifact `reactive-security-demo`. Add two dependencies:

- **Spring Reactive Web** (`spring-boot-starter-webflux`): WebFlux and Reactor.
- **Spring Security** (`spring-boot-starter-security`): reactive security for WebFlux applications.

Do not add `spring-boot-starter-web`/MVC to the demo project. If you want to inspect the `pom.xml` generated by Initializr, the core dependencies section looks like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

This is a **dependencies snippet** for reference, not the entire `pom.xml`. The complete build file and dependency versions are managed by Spring Initializr.

### 5.2. Create the Java file

Replace the code in `src/main/java/com/example/reactivesecuritydemo/ReactiveSecurityDemoApplication.java` (or use the exact package generated by Initializr; keep the path, `package` line, and class name aligned) with:

~~~java
package com.example.reactivesecuritydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/user").hasRole("USER")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails user = User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("Cong khai");
        }

        @GetMapping("/user")
        Mono<String> userEndpoint() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(authentication -> "Xin chao, " + authentication.getName());
        }
    }
}
~~~

In this code:

- `@EnableWebFluxSecurity` enables security configuration for WebFlux; `SecurityWebFilterChain` defines the HTTP policy.
- `ServerHttpSecurity` is the security configuration API for the reactive stack; `authorizeExchange` evaluates permissions per request.
- `/public` allows unauthenticated access; `/user` requires the `ROLE_USER` authority because `hasRole("USER")` checks for the corresponding authority; all other paths require authentication.
- `httpBasic` accepts username/password via HTTP Basic. `MapReactiveUserDetailsService` provides an in-memory account, enough for testing without a database.
- The controller returns `Mono<String>`. The `/user` endpoint retrieves identity from `ReactiveSecurityContextHolder`, demonstrating the coordination between Reactor and Spring Security.
- `formLogin` is disabled so the example only uses HTTP Basic and does not redirect to a login form. **CSRF retains its default configuration**; the example only has HTTP GET endpoints, so no adjustment is needed. The `"{noop}"` prefix is only used to avoid setting up a password encoder in this exercise; **never use plaintext passwords in production**.

### 5.3. Run and verify

In the project directory (where `pom.xml` is located), run the command appropriate for your OS:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell or Command Prompt, use `.\mvnw.cmd spring-boot:run`. After the server starts at `http://localhost:8080`, run in another terminal:

~~~bash
curl -s http://localhost:8080/public
curl -s -u demo:demo123 http://localhost:8080/user
curl -i http://localhost:8080/user
~~~

The response bodies for the first two requests, in order, are:

~~~text
Cong khai
Xin chao, demo
~~~

The last command (sending no credentials) receives **HTTP 401 Unauthorized** with the HTTP Basic configuration; exact headers and body may vary by version/configuration. If a user is authenticated but lacks sufficient permissions, the typical result is **HTTP 403 Forbidden**. To test a 403 scenario, you need to add another account or corresponding authorization rule; the example currently has one user with `ROLE_USER`, so it does not produce a 403 on its own.

### 5.4. Mapping back to lesson objectives

- **WebFlux** receives `GET /user` and passes the request to the filter chain, then to the controller if allowed.
- **Spring Security** checks HTTP Basic, creates `Authentication`, and evaluates `hasRole("USER")`.
- **Reactor** provides `Mono` for both asynchronous steps and the controller return value; `ReactiveSecurityContextHolder` reads the authentication from Reactor Context.
- **Outcome**: missing credentials → 401; valid credentials → controller responds with the username.

## 6. Things to Remember When Building Real-World Applications

### 6.1. Choose the right reactive APIs

| Servlet/MVC style | Equivalent in WebFlux |
| --- | --- |
| `HttpSecurity` + `SecurityFilterChain` | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| `Filter` / `HttpServletRequest` | `WebFilter` / `ServerWebExchange` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `SecurityContextHolder` (typically thread-bound) | `ReactiveSecurityContextHolder` (Reactor Context) |

The two stacks share similar concepts, but **their beans and filters are not directly interchangeable**. If you mistakenly configure a Servlet-style `SecurityFilterChain` in a WebFlux application, reactive requests will not be protected as expected.

### 6.2. Reactive does not automatically make every task non-blocking

`Mono.just(blockingCall())` still executes `blockingCall()` immediately when constructing the `Mono`; this is not a solution for avoiding blocking the event loop. For databases, HTTP clients, or external authentication systems, prefer truly reactive APIs (e.g., R2DBC, WebClient, `ReactiveAuthenticationManager`). If you must integrate a blocking library, isolate it intentionally on an appropriate scheduler (typically `Schedulers.boundedElastic()`), load-test it, and guard resource limits. Never arbitrarily call `block()` inside reactive handlers or security filters.

### 6.3. Context is not a global variable

`ReactiveSecurityContextHolder` depends on the Reactor chain currently being subscribed to. If you manually offload work to a separate thread, an independent `CompletableFuture`, or a callback outside the chain without propagating context properly, do not assume authentication will appear automatically. Reactor Context is not synonymous with a servlet session, is not a mechanism for permanently storing users automatically, and is not used to share data across independent requests.

### 6.4. Protecting endpoints alone is not enough

Authorization in `authorizeExchange` protects requests by HTTP path/method. For business logic requiring per-object permissions (e.g., viewing only one's own orders), the service must still check ownership or the relevant policy. Reactive method security can be enabled via `@EnableReactiveMethodSecurity` when appropriate; reactive method security relies on Reactor Context and requires special attention to methods returning `Publisher` (`Mono`/`Flux`).

### 6.5. Configuration for production environments

- Use HTTPS; never hard-code usernames/passwords, never use `{noop}`; store passwords using an appropriate password encoder.
- Clearly choose the authentication mechanism: session/cookie, HTTP Basic, OAuth2 login, or JWT resource server; each choice requires different security configuration.
- Keep CSRF protection whenever there is a risk of forged browser requests; disable it only after evaluating the authentication model and attack surface of the API.
- Define rules from specific to general, testing both public endpoints and role-restricted endpoints; remember that a default `anyExchange().authenticated()` is only a policy and does not express business permissions automatically.
- If a Boot application includes both MVC and WebFlux starters, Spring Boot typically chooses the **MVC** configuration by default. Determine the actual web application type before concluding that `SecurityWebFilterChain` is active.

## 7. Common Misconceptions

1. **"Using Mono means the request is completely asynchronous."** False: an operator may still call blocking I/O; inspect the data source and execution model.
2. **"Each reactive request always runs on one fixed thread."** False: schedulers and asynchronous boundaries can switch threads; use Reactor Context to carry security information.
3. **"Putting `hasRole` in the controller is enough."** Configuring HTTP authorization in the security chain blocks unauthorized access early; business permission checks still belong in the appropriate layer.
4. **"`permitAll` bypasses all security filters."** False: it allows the request past that authorization step; other filters may still run as configured.
5. **"Having the Spring Security dependency guarantees endpoints are protected as intended."** The dependency may activate default protection, but policies still need to be explicitly defined, tested, and matched to the reactive/servlet stack.
6. **"You can retrieve Principal from `ThreadLocal` anywhere."** False in a Reactor chain; read it through the reactive APIs supported by the framework.

## 8. Self-Check Questions

**Question 1.** If WebFlux can handle HTTP without Spring Security, why add Spring Security?

**Answer:** WebFlux manages the protocol and handlers; Spring Security adds authentication, authorization, and defensive mechanisms. Reactor enables security steps to run along with the asynchronous chain.

**Question 2.** Both endpoints return `Mono<String>`. Why is `/public` accessible while `/user` requires credentials?

**Answer:** The difference lies in `SecurityWebFilterChain`: `permitAll` applies to `/public`, whereas `hasRole("USER")` applies to `/user`. The `Mono` return type does not determine access permissions.

**Question 3.** If execution switches to another thread in a Reactor chain, what should be used to read the current user?

**Answer:** `ReactiveSecurityContextHolder.getContext()` or the reactive Principal mechanism provided by WebFlux/Spring Security. Do not assume `ThreadLocal` remains valid.

**Question 4.** What needs attention when switching from `MapReactiveUserDetailsService` to a real data store?

**Answer:** You need a data-reading and authentication solution compatible with the reactive pipeline, with error handling, secure passwords, and proper business permission rules; avoid calling a blocking database directly on the event loop.

## 9. Official Documentation for Further Reading

- [Spring Framework — WebFlux: Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html)
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
