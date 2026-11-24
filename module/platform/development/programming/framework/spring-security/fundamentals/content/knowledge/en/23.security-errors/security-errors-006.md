# Corresponding Error-Handling Components in Reactive Applications (Spring Security WebFlux)

## 1. Context and Goals

In Spring Security applications running on **Spring WebFlux**, security errors are handled through `WebFilter` and `ServerWebExchange`, instead of Servlet/MVC's `Filter`, `HttpServletRequest`, and `HttpServletResponse`. When migrating configuration from MVC to WebFlux, you must use the proper **reactive interfaces and filters**; Servlet error-handling classes cannot be plugged directly into `SecurityWebFilterChain`.

After this lesson, you will be able to: find the reactive component corresponding to Servlet's security error-handling mechanism; distinguish authentication-required errors (401) from insufficient-permission errors (403); configure responses in `ServerHttpSecurity`; and recognize cases where errors occur directly inside the authentication filter.

## 2. Servlet ↔ Reactive Comparison Table

| Role | Servlet/MVC | Spring Security WebFlux |
| --- | --- | --- |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Chain-dispatching filter | `FilterChainProxy` | `WebFilterChainProxy` |
| Translating security exceptions into HTTP responses | `ExceptionTranslationFilter` | `ExceptionTranslationWebFilter` |
| Initiating authentication request when unauthenticated | `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| Handling authenticated users with insufficient permissions | `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| Handling a failed login attempt inside the authentication filter | `AuthenticationFailureHandler` | `ServerAuthenticationFailureHandler` |
| Returning a status code when authentication is required | `HttpStatusEntryPoint` | `HttpStatusServerEntryPoint` |
| Returning a status code when access is denied | `HttpStatusAccessDeniedHandler` | `HttpStatusServerAccessDeniedHandler` |
| HTTP Basic authentication | `BasicAuthenticationFilter` | `AuthenticationWebFilter` configured for HTTP Basic |
| Filter deciding HTTP access permissions | `AuthorizationFilter` / `FilterSecurityInterceptor` (depending on config) | `AuthorizationWebFilter` |

**Three central components of this topic:**

- `ExceptionTranslationWebFilter`: observes security errors from the downstream processing chain and chooses an appropriate response. It **does not make authorization decisions itself**; those belong to an authorization component such as `AuthorizationWebFilter`.
- `ServerAuthenticationEntryPoint`: functional interface `Mono<Void> commence(ServerWebExchange exchange, AuthenticationException ex)`. It asks the client to authenticate—for example returning 401, sending `WWW-Authenticate`, or redirecting to a login page—depending on the authentication mechanism.
- `ServerAccessDeniedHandler`: functional interface `Mono<Void> handle(ServerWebExchange exchange, AccessDeniedException ex)`. The typical case is a logged-in user lacking permissions, returning 403.

These are reactive APIs: the `Mono<Void>` result represents asynchronously writing and completing the response. Never manually call `subscribe()` or `block()` inside a handler to "force" the response to finish.

## 3. When 401, When 403?

| Request State | Meaning | Typical Handling |
| --- | --- | --- |
| No credentials provided, accessing a login-required resource | Unauthenticated | `ServerAuthenticationEntryPoint` → usually **401** for APIs |
| Invalid/expired credentials sent | Authentication failed | Authentication filter may call `ServerAuthenticationFailureHandler` → usually **401** |
| Authenticated, but missing role/access permission | Authorization denied | `ServerAccessDeniedHandler` → usually **403** |
| Anonymous accessing a resource requiring a higher role | Not yet authenticated for permission check | Exception translator usually calls entry point, usually **401** instead of 403 |
| State-changing request with missing/wrong CSRF token (when CSRF is enabled) | CSRF rule violation | Can trigger `AccessDeniedException` and **403**, even with a valid account |

**401 Unauthorized** in HTTP actually indicates the request needs valid authentication credentials; the status name is misleading. **403 Forbidden** indicates the server understands the request but refuses to allow it. Not every app returns these two codes verbatim: browser form-login configs may redirect **302** to a login page; Bearer-token APIs also have `WWW-Authenticate` header requirements.

For example: `GET /admin` requires `ROLE_ADMIN`. Sending no token/password requires authentication; logging in with an account having only `ROLE_USER` results in permission denial. `hasRole("ADMIN")` automatically checks the `ROLE_ADMIN` authority; do not pass the string `ROLE_ADMIN` to `hasRole`.

## 4. Processing Flow in the Reactive Chain

`SecurityWebFilterChain` contains the `WebFilter`s configured from `ServerHttpSecurity`. When a request goes through the permission check:

1. `AuthorizationWebFilter` evaluates policies like `permitAll()`, `authenticated()`, `hasRole()`. If denied, the reactive flow may emit `AccessDeniedException`.
2. `ExceptionTranslationWebFilter` catches security exceptions within the part of the chain it wraps. For unauthenticated/anonymous users, it routes to `ServerAuthenticationEntryPoint`; for authenticated users lacking permissions, it calls `ServerAccessDeniedHandler`.
3. The handler sets status/headers/body on `exchange.getResponse()` and returns a `Mono<Void>` representing response completion.

```text
Request
   │
   ▼
WebFilterChainProxy → SecurityWebFilterChain
   │
   ├─ Authentication (if credentials present) ── failed
   │                                              └─ ServerAuthenticationFailureHandler
   ▼
Authorization check (AuthorizationWebFilter)
   │
   ├─ Allowed ──────────────────────────► Controller / Handler
   │
   └─ AccessDeniedException
          │
          ▼
   ExceptionTranslationWebFilter
          ├─ Unauthenticated ──────────────► ServerAuthenticationEntryPoint
          └─ Authenticated, missing perms ─► ServerAccessDeniedHandler
```

**Distinguishing two important error paths:** `ExceptionTranslationWebFilter` handles exceptions propagated to it from the protected chain; meanwhile, `AuthenticationWebFilter` has **its own failure path** when actively checking credentials. `ServerAuthenticationFailureHandler#onAuthenticationFailure(WebFilterExchange, AuthenticationException)` is not identical to `ServerAuthenticationEntryPoint#commence(ServerWebExchange, AuthenticationException)`. You can use `ServerAuthenticationEntryPointFailureHandler` to forward a login failure to an entry point, but the two API contracts remain distinct.

## 5. Configuring a Runnable Example with Java 17

The example uses Spring Boot **3.5.7**, Spring WebFlux, and Spring Security, configured with HTTP Basic to easily observe 401/403 codes. Use only `spring-boot-starter-webflux` for the web layer; avoid adding `spring-boot-starter-web` because it alters the application type Boot selects when both stacks are present.

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-error-demo</artifactId>
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

**File `src/main/java/demo/ReactiveErrorDemoApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReactiveErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(
                                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED))
                        .accessDeniedHandler(
                                new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails demoUser = User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(demoUser);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/private")
        String privateEndpoint() {
            return "private";
        }

        @GetMapping("/admin")
        String adminEndpoint() {
            return "admin";
        }
    }
}
```

Key points in the configuration:

- `authorizeExchange` sets rules in order: public, admin, then remaining paths. The `demo` account has `ROLE_USER`, so it can access `/private` but not `/admin`.
- `httpBasic(...)` enables HTTP Basic authentication; `formLogin(...disable)` keeps the API example from redirecting to a login page.
- `exceptionHandling(...)` registers two reactive handlers. `HttpStatusServerEntryPoint` and `HttpStatusServerAccessDeniedHandler` are built-in implementations suited for when you only want to return an HTTP status.
- `"{noop}demo123"` **is only to keep the demo easy to run**; never store plaintext passwords in real systems. Use a proper password encoder and a secure user store.
- The example uses GET, so CSRF defaults do not need changes. For POST/PUT/DELETE operations from browsers using cookies or Basic Auth, consider CSRF protection separately; do not disable CSRF just to make a test request succeed.

**Compile and start** (Java 17+, Maven, run in the directory with `pom.xml`):

```bash
mvn -q -DskipTests package
java -jar target/reactive-error-demo-0.0.1-SNAPSHOT.jar
```

**Test HTTP in another terminal:**

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u demo:demo123 http://localhost:8080/private
curl -i -u demo:demo123 http://localhost:8080/admin
curl -i -u demo:wrong http://localhost:8080/private
```

| Command | Expected Status | Meaning |
| --- | --- | --- |
| `GET /public` without credentials | `200 OK`, body `public` | Public endpoint |
| `GET /private` without credentials | `401 Unauthorized` | Authentication required |
| `GET /private` with `demo:demo123` | `200 OK`, body `private` | Authenticated and authorized |
| `GET /admin` with `demo:demo123` | `403 Forbidden` | Authenticated, missing `ROLE_ADMIN` |
| `GET /private` with wrong password | `401 Unauthorized` | Authentication failure at the filter |

Note: `curl -i` displays headers, status, and body. Some headers may vary by authentication mechanism and library version; check the **status code** and do not assume every 401 response has the same body or is produced by the same handler.

## 6. When an API Needs to Return Custom Error JSON

The `HttpStatusServerEntryPoint` and `HttpStatusServerAccessDeniedHandler` classes only handle the status code. To standardize JSON responses for an API, you can implement both interfaces using reactive lambdas. The example below is **a standalone Java file** providing two handler factories; use it in place of the two `HttpStatus...` objects in section 5.

**`src/main/java/demo/SecurityErrorResponses.java`:**

```java
package demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class SecurityErrorResponses {
    private SecurityErrorResponses() {}

    public static ServerAuthenticationEntryPoint authenticationEntryPoint() {
        return (exchange, exception) ->
                send(exchange, HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED");
    }

    public static ServerAccessDeniedHandler accessDeniedHandler() {
        return (exchange, exception) ->
                send(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED");
    }

    private static Mono<Void> send(
            ServerWebExchange exchange, HttpStatus status, String code) {
        var response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] bytes = ("{\"error\":\"" + code + "\"}")
                .getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }
}
```

Replace only the handler registration snippet in `securityWebFilterChain(...)` with:

```java
.exceptionHandling(ex -> ex
        .authenticationEntryPoint(SecurityErrorResponses.authenticationEntryPoint())
        .accessDeniedHandler(SecurityErrorResponses.accessDeniedHandler()))
```

When the entry point branch is used, the returned JSON is `{"error":"UNAUTHENTICATED"}` with status 401; when the access-denied branch is used, the returned JSON is `{"error":"ACCESS_DENIED"}` with status 403. **There is no guarantee** that every wrong-password attempt goes through this entry point: `AuthenticationWebFilter` has its own `ServerAuthenticationFailureHandler`. To apply the same format to direct login errors, configure the appropriate failure handler for that specific authentication mechanism.

In production, consider your API's error response standard, stable error codes, and server-side logging. Never include stack traces, passwords, tokens, or internal info in JSON sent to clients. Before writing the body, the response is uncommitted; a handler must never attempt to write a second time after the response has completed.

## 7. Cases Requiring Proper Mechanism Handling

### Form Login and HTTP Basic

Browser apps with `formLogin` can use `RedirectServerAuthenticationEntryPoint` to redirect to the login page instead of returning 401 JSON. HTTP Basic has `HttpBasicServerAuthenticationEntryPoint` and may require the `WWW-Authenticate: Basic ...` header. The JSON/status config example in section 5 is for an API demo; do not apply a status-only entry point across all apps while ignoring the client's authentication contract.

### OAuth2 Resource Server (Bearer Tokens)

For JWT or opaque tokens, Spring Security provides `BearerTokenServerAuthenticationEntryPoint` and `BearerTokenServerAccessDeniedHandler`. These implementations generate proper Bearer responses, including `WWW-Authenticate` when needed. For invalid/expired tokens, error details may be placed in the header per protocol. If replacing them with a custom JSON handler, preserve the corresponding RFC 6750 requirements; do not arbitrarily strip challenges or expose sensitive details.

### Method Security and Reactive Context

When using `@EnableReactiveMethodSecurity` and `@PreAuthorize`, exceptions from method-level permission checks can also propagate to the HTTP chain for handling. If a task runs outside an HTTP request, there is no `ServerWebExchange` to apply these WebFlux handlers; handle errors at the task boundary. Reactive security context is propagated in the Reactor `Context`, rather than relying on reading `ThreadLocal` as in traditional synchronous threads.

### Application Errors That Are Not Security Errors

`ExceptionTranslationWebFilter` is not a general-purpose handler for all errors. For instance, data validation errors, `ResponseStatusException` thrown by a controller, 404, or 500 belong to the WebFlux error-handling layer (such as `@RestControllerAdvice` / `@ExceptionHandler`, `WebExceptionHandler`, `ErrorWebExceptionHandler` depending on context). Do not mix everything into 401/403; do not use an `@ExceptionHandler(Exception.class)` that accidentally masks security error semantics.

## 8. Common Implementation Mistakes

1. **Copying Servlet code to WebFlux:** importing `AuthenticationEntryPoint` or `AccessDeniedHandler` from servlet packages, using `HttpSecurity` / `HttpServletResponse` in a WebFlux bean. The right way is `ServerHttpSecurity` along with the `Server...`-prefixed interfaces.
2. **Treating every `AccessDeniedException` as 403:** an anonymous request to an endpoint requiring login is usually routed to the entry point (401 or redirect); distinguish the current identity.
3. **Confusing login failure with insufficient permissions:** a wrong password at `AuthenticationWebFilter` is different from a logged-in user rejected by `AuthorizationWebFilter`. Inspect the handler at the right spot.
4. **Blocking the reactive thread:** using `block()`, `Thread.sleep()`, heavy synchronous I/O, or manually calling `subscribe()` in a handler can cause resource and ordering issues. Return `Mono<Void>`.
5. **Disabling CSRF/CORS to "fix" 403:** first determine whether the error comes from authorization, CSRF, or CORS preflight; each has its own resolution.
6. **Replacing Bearer handlers without keeping `WWW-Authenticate`:** can break OAuth2-compliant client behavior. Test headers, statuses, and invalid/expired/insufficient-scope tokens.
7. **Forgetting to scope security chains:** with multiple `SecurityWebFilterChain`s, a request only applies the matching chain by matcher and order; placing handlers in the wrong chain will have no effect.
8. **Reading only the status to guess the cause:** 403 can also come from CSRF; 401 can come from an authentication mechanism's failure handler. Enable appropriate logs and reproduce scenarios with and without credentials.

## 9. Verification Checklist and Self-Practice Questions

- Does an anonymous request to a path requiring authentication reach the entry point and return the status/challenge expected by the client type?
- Does an authenticated request lacking a role reach the access-denied handler and return 403?
- Are wrong credentials handled by the authentication filter's failure handler?
- With Bearer tokens, is the `WWW-Authenticate` header correct when the token is missing, invalid, or lacks scope?
- Did it accidentally affect CSRF, form login, or another `SecurityWebFilterChain`?
- Does the handler return `Mono<Void>` and leak no sensitive information?

**Self-answer:** (1) Why can `/admin` return 401 for anonymous guests but 403 for `demo`? (2) When entering a wrong Basic password, why can you not assume by default that `ExceptionTranslationWebFilter` generated the response? (3) When switching from HTTP Basic to Bearer tokens, why must you pay attention to challenge headers even though the status is still 401?

## 10. Official Reference Documentation

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [API — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [API — AuthenticationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
