# ServerAuthenticationSuccessHandler and ServerAuthenticationFailureHandler in Spring Security WebFlux

## 1. What Do These Two Handlers Solve?

In a Spring WebFlux application, authentication checks whether a login request truly belongs to the claimed user or client. Once the authentication component returns a result, the application still has to decide **how to respond over HTTP**: redirect to an appropriate page, return JSON, continue the WebFilter chain, or report an error. That is the responsibility of two interfaces:

- `ServerAuthenticationSuccessHandler`: runs **after authentication succeeds**.
- `ServerAuthenticationFailureHandler`: runs **when an authentication attempt fails** with an `AuthenticationException`.

Both belong to `org.springframework.security.web.server.authentication` and operate on WebFlux's **reactive** infrastructure. They do not verify passwords in place of `ReactiveAuthenticationManager`, do not perform authorization themselves, and are not Spring MVC/Servlet handlers.

For example, a user submits a username and password via a form. The manager verifies the credentials. If valid, the success handler may return HTTP 200 with JSON or redirect. If wrong, the failure handler may return HTTP 401 or redirect back to the login page. Whether the authenticated account is allowed to access `/admin` is still decided by **authorization**.

## 2. Position in the Reactive Authentication Flow

Typical flow of `AuthenticationWebFilter`:

1. The request enters `SecurityWebFilterChain`; the matcher determines whether authentication should be attempted for this request.
2. `ServerAuthenticationConverter` reads the request and converts the credentials into an unauthenticated `Authentication` object. If the converter returns `Mono.empty()`, the filter skips authentication and continues the chain.
3. `ReactiveAuthenticationManager` verifies the credentials. A successful outcome carries an authenticated `Authentication`; an authentication error is represented by `AuthenticationException`.
4. The success branch populates `SecurityContext` in the Reactor Context, persists the context via the configured `ServerSecurityContextRepository`, and calls the success handler. The failure branch calls the failure handler.
5. The handler returns `Mono<Void>` representing completion of the response or continuation of processing; WebFlux subscribes to and executes that publisher.

Mental model:

~~~text
HTTP request
  → SecurityWebFilterChain / AuthenticationWebFilter
    → matcher mismatch or empty converter → continue chain
    → converter builds Authentication → ReactiveAuthenticationManager
       ├─ valid → SecurityContext → SuccessHandler → HTTP response/redirect/chain
       └─ AuthenticationException → FailureHandler → HTTP response/redirect
~~~

**Distinction:** requests without credentials, CSRF errors, requests lacking authorization (403), and exceptions thrown inside controllers do not necessarily enter the failure handler. A handler processes only events handed to it by **that specific authentication filter**.

## 3. API Contract and Inputs

The condensed signatures below are for reading the API, not two standalone Java classes to declare yourself:

~~~java
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication
);

Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

| Parameter / type | Role |
| --- | --- |
| `WebFilterExchange` | Wraps `ServerWebExchange` and `WebFilterChain`. Call `getExchange()` to access request/response, and `getChain()` when continuing the filter chain. |
| `Authentication` | Principal, list of authorities, and authenticated state on the success path. Use `getName()` or authorities when deciding valid behavior. |
| `AuthenticationException` | Reason authentication failed, such as bad credentials. Use for internal classification; never expose raw stack traces or sensitive messages to clients. |
| `Mono<Void>` | Completion signal for async work: writing the response, redirecting, or continuing the chain. Not a JSON value returned directly. |

**Reactive rule:** **return** the publisher describing the work to perform. Never call `block()` on the request thread, never manually `subscribe()` and return `Mono.empty()`, and never do event-loop-blocking I/O. If you must call a network service or perform blocking logging I/O, use reactive APIs or offload blocking work to an appropriate scheduler.

## 4. Default Handling and Built-In Implementations

| Context | Common behavior |
| --- | --- |
| WebFlux `formLogin` | By default, success redirects to the saved request if present; otherwise usually `/`. Failure redirects to `/login?error` when using the default login page. |
| `RedirectServerAuthenticationSuccessHandler` | Redirects after login; can use `ServerRequestCache` to send users back to the resource they originally requested. |
| `RedirectServerAuthenticationFailureHandler` | Redirects to a specified URI, such as `/login?error`. |
| `WebFilterChainServerAuthenticationSuccessHandler` | Continues the `WebFilterChain` upon success; this is the default success handler of a directly instantiated `AuthenticationWebFilter`. |
| `ServerAuthenticationEntryPointFailureHandler` | Delegates failure to a `ServerAuthenticationEntryPoint`, such as an HTTP Basic challenge. |
| `DelegatingServerAuthenticationSuccessHandler` | Combines multiple success handlers when multiple compatible actions are needed, per filter configuration. |

**Do not confuse the defaults:** `formLogin` builds an `AuthenticationWebFilter` configured with redirects and session persistence for form login; a newly constructed `AuthenticationWebFilter` has its own defaults (success continues the chain, `NoOpServerSecurityContextRepository`, failure sends a Basic challenge). Therefore, you cannot infer from a custom filter's defaults that form login behaves identically.

When simple redirects are needed, prefer built-in implementations:

~~~java
.formLogin(form -> form
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/dashboard"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error"))
)
~~~

This is a **configuration snippet** placed inside `ServerHttpSecurity` configuration. For success redirects, if the request cache holds a valid saved URL, that saved URL may take precedence over `/dashboard`; test the destination in the real flow rather than assuming every login lands on one fixed URL.

## 5. Complete Example: Returning JSON After Form Login

The example uses **Java 17+**, **Spring Boot WebFlux**, and **Spring Security**. Create a Spring Boot app via Spring Initializr with `Spring Reactive Web` (`spring-boot-starter-webflux`) and `Spring Security` (`spring-boot-starter-security`). Choose Maven and let Spring Boot manage compatible library versions. The example uses an in-memory user solely to learn the mechanism, not for real user data.

Create `src/main/java/demo/ReactiveLoginDemoApplication.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveLoginDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        ServerAuthenticationSuccessHandler success = (webFilterExchange, auth) ->
                jsonResponse(webFilterExchange, HttpStatus.OK,
                        "{\"status\":\"authenticated\"}");

        ServerAuthenticationFailureHandler failure = (webFilterExchange, error) ->
                jsonResponse(webFilterExchange, HttpStatus.UNAUTHORIZED,
                        "{\"error\":\"bad_credentials\"}");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login").permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .authenticationManager(manager)
                        .authenticationSuccessHandler(success)
                        .authenticationFailureHandler(failure))
                .build();
    }

    private static Mono<Void> jsonResponse(
            WebFilterExchange webFilterExchange, HttpStatus status, String json) {
        ServerHttpResponse response = webFilterExchange.getExchange().getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class DemoController {
        @GetMapping("/private")
        Mono<String> privateEndpoint() {
            return Mono.just("Only authenticated users can see this");
        }
    }
}
~~~

### Explaining Each Part

- `MapReactiveUserDetailsService` loads user `learner`; `BCryptPasswordEncoder` stores the hash of the demo password. `UserDetailsRepositoryReactiveAuthenticationManager` is the component that **decides whether credentials are valid**, configured with the encoder.
- `ServerHttpSecurity` sets the policy: permit `/login` and require authentication for other URLs. `formLogin` configures form login; `authenticationManager(manager)` uses the declared manager.
- The success branch calls `jsonResponse(...)` and returns `200 OK` with body `{"status":"authenticated"}`. The `auth` object can be used for policy-compliant auditing, though the example intentionally avoids exposing sensitive details.
- The failure branch returns `401 Unauthorized` with body `{"error":"bad_credentials"}`. A fixed message reduces disclosure of user existence or account status.
- Helper `jsonResponse` obtains `ServerHttpResponse`, sets HTTP status and content type, creates UTF-8 bytes, and **returns** the `Mono<Void>` from `response.writeWith(...)` without managing subscriptions manually.

### Running and Verifying Behavior

In the project directory generated by Spring Initializr, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell/CMD use `mvnw.cmd spring-boot:run`. Once the app starts, test in a browser:

1. Open `http://localhost:8080/private` while unauthenticated. Form login directs you to the `/login` page.
2. Log in with `learner` / `learn123`. A valid form POST invokes the **success handler** and the browser displays JSON `{"status":"authenticated"}` with HTTP 200.
3. Keeping the session cookie in the same browser, visit `/private`: the server returns `Only authenticated users can see this`.
4. Open a new private window and try a wrong password. The form POST to `/login` invokes the **failure handler** and responds with HTTP 401 and `{"error":"bad_credentials"}`.

Spring Security enables **CSRF** protection by default for form login. The framework-generated `/login` page includes a valid CSRF token. A manual `curl -d "username=..." -d "password=..."` POST **without the token** may be rejected with HTTP 403 **before** the failure handler runs; that is not a bug in the handler. To automate tests, use WebTestClient with CSRF support from `spring-security-test` and manage session cookies properly.

**Expected outcomes in the example:**

| Action | HTTP / result | Handler |
| --- | --- | --- |
| POST `/login` with valid credentials and valid CSRF | 200, `{"status":"authenticated"}` | Success |
| POST `/login` with wrong password and valid CSRF | 401, `{"error":"bad_credentials"}` | Failure |
| POST missing or invalid CSRF token | Usually 403 | Not the authentication failure handler |
| GET `/private` when unauthenticated | Redirect to login in form config | Entry point / authorization |
| GET `/private` when already logged in, holding session | 200, string from controller | Success handler does not re-run just for visiting a page |

## 6. When Should You Write Custom Handlers?

**Traditional web pages:** if navigation after login is needed, using the two `RedirectServerAuthentication...Handler` classes is usually enough. You can configure fixed URIs or request caching and display error messages on the login page.

**JSON-returning login:** SPAs or custom clients may want 200/401 with a consistent body. Custom handlers then take responsibility for the exact response format as in the example. However, **replacing the response with JSON does not turn form login into a REST authentication API**: form matchers, field names, CSRF, cookies/sessions, and the existing SecurityContext flow still apply. To accept JSON credentials or Bearer tokens, design dedicated converters/filters and an appropriate state model.

**Post-login side tasks:** you can emit audit logs, record login timestamps, redirect by role, or set appropriate cookies. Those actions must be safe, bounded, and chained into the `Mono`. Never move credential verification into handlers, and never leak passwords, tokens, stack traces, or detailed rejection reasons.

**Custom authentication filters:** when constructing `AuthenticationWebFilter` yourself, use:

~~~java
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
~~~

These two lines are an **illustrative configuration snippet**, not a complete app: you also need `ReactiveAuthenticationManager`, `ServerAuthenticationConverter`, matchers, filter ordering, a security context repository, and proper error handling. For WebFlux, work with `SecurityWebFilterChain` and `ServerHttpSecurity`; do not wire `HttpSecurity`, `SecurityFilterChain`, or Servlet `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` by mistake.

## 7. Comparing with Easily Confused Components

| Component | What does it decide? |
| --- | --- |
| `ReactiveAuthenticationManager` | Whether credentials/tokens are valid. |
| `ServerAuthenticationSuccessHandler` | After **authentication succeeds**, what to return or where to redirect/continue. |
| `ServerAuthenticationFailureHandler` | After **authentication fails**, how to handle the response. |
| `ServerAuthenticationEntryPoint` | When an **unauthenticated** client requests a protected resource, how to initiate login/challenge. |
| `ServerAccessDeniedHandler` | When a request is **denied access** by policy—typically authenticated yet lacking authority—what to return (usually 403). |
| `ServerSecurityContextRepository` | Saves/loads `SecurityContext` across requests when using stateful authentication. |

A login POST with a wrong password and an unauthenticated GET to a protected resource are **two distinct events**. The first belongs to the authentication filter's failure handler; the second typically belongs to the entry point mechanism. Likewise, a logged-in user lacking a role does not mean login failed.

## 8. Common Mistakes and How to Fix Them

1. **Using Servlet APIs in WebFlux:** mistakenly importing `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `HttpServletRequest`, or configuring `HttpSecurity`. Fix by using `Server`-prefixed interfaces, `WebFilterExchange`, and `ServerHttpSecurity`.
2. **Returning `Mono.empty()` after calling `subscribe()` yourself:** the response may complete before async work finishes. Fix by returning the actual `Mono<Void>` from `writeWith`, the redirect strategy, or a publisher chain ending with `then()`.
3. **Assuming a custom handler is always invoked:** the matcher did not match, the converter produced no `Authentication`, CSRF was rejected, or another filter handled the request first. Check paths, HTTP methods, security chains, and test scenarios.
4. **Sending exception details to users:** contents can expose account status, configuration, or sensitive data. Return a stable message while logging/auditing internally under controlled data limits.
5. **Confusing 401 and 403:** 401 is for unauthenticated/failed authentication per API design; 403 is usually for access denial or CSRF failure. Pick statuses based on context and the app's HTTP contract.
6. **Ignoring sessions with form login:** to persist state after POST, you need a security context repository and session cookie. For stateless APIs, design a proper token strategy; a response handler alone does not make an app stateless.
7. **Open or unsafe redirects:** never take unvalidated redirect URLs directly from query parameters. When redirecting to saved requests, understand how the request cache works and allow only trusted destinations.
8. **Writing the response twice:** once a response is committed, you cannot switch to a redirect or write another JSON body. Choose one terminal action or compatible handler chain; watch ordering when using delegating handlers.

## 9. Self-Check Questions

- Why must `ReactiveAuthenticationManager` and the success handler remain two separate responsibilities?
- How does a login POST with the wrong password differ from an unauthenticated GET `/private`?
- Why might a login POST missing a CSRF token never reach the failure handler?
- When should you use `RedirectServerAuthenticationSuccessHandler` vs. returning JSON?
- What happens if a handler performs blocking I/O or calls `subscribe()` manually?

If you can answer these five questions and run both login branches in the example, you understand where handlers attach, what data they receive, their responsibility for the response, and key constraints in the reactive authentication pipeline.

## 10. Official Documentation

- [Spring Security — ServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html)
- [Spring Security — ServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
