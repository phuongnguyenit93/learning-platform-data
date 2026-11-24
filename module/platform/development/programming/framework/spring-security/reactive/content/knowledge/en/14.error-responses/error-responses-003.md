# ServerAuthenticationEntryPoint for Unauthenticated Requests in Spring Security Reactive

## 1. Objectives

A REST API built with Spring WebFlux has an endpoint `GET /api/me` restricted to logged-in users. When a request has no credentials, the server must request authentication, usually via HTTP **401 Unauthorized** with an appropriate challenge. If a website uses form login, instead of 401 JSON, the browser may be **redirected** to `/login`. The Spring Security reactive component that decides **how to initiate the authentication-request response** is `ServerAuthenticationEntryPoint`.

This lesson helps you:

1. Understand the purpose, position, and reactive `commence(...)` signature of `ServerAuthenticationEntryPoint`.
2. Distinguish requests that are **unauthenticated**, **wrong credentials**, **authenticated but lacking permissions**, and **CSRF rejected**.
3. Configure `ServerHttpSecurity.exceptionHandling(...).authenticationEntryPoint(...)` properly on `SecurityWebFilterChain`.
4. Write a safe 401 JSON entry point while preserving `WWW-Authenticate` per the HTTP Basic/Bearer protocol.
5. Distinguish `ServerAuthenticationEntryPoint` from `ServerAuthenticationFailureHandler`, `ServerAccessDeniedHandler`, `AuthenticationWebFilter`, and `ExceptionTranslationWebFilter`.
6. Run a Java 17+ example and verify results with `curl`, including public, anonymous, wrong password, and missing role cases.
7. Choose the right response style for JSON APIs, browser form login, and OAuth2 Resource Servers.

**Key point:** the entry point **does not verify passwords, grant roles, issue tokens, or authenticate principals**. It completes the response so the client knows what to do to authenticate.

## 2. Position in the WebFilter Chain

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    v
AuthenticationWebFilter / appropriate authentication filter
    |
    +-- No credentials for this mechanism
    |       -> converter may return Mono.empty()
    |       -> filter does not attempt authentication; continues chain
    |
    +-- Credentials present but wrong
    |       -> ReactiveAuthenticationManager emits error
    |       -> ServerAuthenticationFailureHandler
    |
    +-- Valid credentials
    |       -> Authentication authenticated in Reactor Context
    |
    v
AuthorizationWebFilter (and possibly downstream method security)
    |
    +-- permitAll() --------------------> Controller / handler
    |
    +-- unauthenticated while URL requires authenticated()
    |       -> AccessDeniedException
    |       -> ExceptionTranslationWebFilter
    |       -> ServerAuthenticationEntryPoint.commence(...)
    |
    +-- authenticated but lacking role/authority
            -> AccessDeniedException
            -> ExceptionTranslationWebFilter
            -> ServerAccessDeniedHandler
~~~

This is a **responsibility diagram**, not an exact simulation of every internal operator. Some errors from the authentication filter pass through a failure handler before reaching authorization; method security errors outside HTTP also do not automatically produce an HTTP response.

Per the Spring Security WebFlux contract, `ExceptionTranslationWebFilter` handles downstream access denials. When the principal is not considered authenticated, it initiates authentication via the entry point; when the principal is valid but lacks permissions, it invokes the access-denied handler.

### 2.1. API Signature

~~~java
// Abbreviated signature from Spring Security reactive:
@FunctionalInterface
public interface ServerAuthenticationEntryPoint {
    Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception);
}
~~~

This is an **API excerpt for learning**, not a replacement for the Spring library source. Actual imports:

~~~java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.security.core.AuthenticationException;
import reactor.core.publisher.Mono;
~~~

- `ServerWebExchange` provides the HTTP request/response for the reactive chain.
- `AuthenticationException` describes why the authentication mechanism had to be started. Do not infer from it that username/password were wrong; the request might have sent nothing.
- `Mono<Void>` signals that response handling is complete; it does not return `Authentication` or `boolean`.
- Because it is a functional interface, it can be implemented with a lambda, method reference, or dedicated class.

**Do not use** Servlet `AuthenticationEntryPoint` (package `org.springframework.security.web`), which uses `HttpServletRequest` and `HttpServletResponse`. WebFlux requires `ServerAuthenticationEntryPoint` in `org.springframework.security.web.server`.

### 2.2. Reactive and Reactor Context

Upon successful authentication, `Authentication` is stored in the `SecurityContext` of the Reactor Context, rather than relying on a traditional Servlet `ThreadLocal`. The entry point is triggered at the appropriate point when the request does not yet have a sufficiently trusted identity. An `AnonymousAuthenticationToken` may exist, but that **does not mean** the caller is considered logged in for the `authenticated()` rule.

## 3. 401, 403, Redirect, and Login Failure Differ

| Case | Who usually handles it? | Example output |
| --- | --- | --- |
| Anonymous calling `/api/me` requiring authenticated | `ExceptionTranslationWebFilter` → `ServerAuthenticationEntryPoint` | HTTP **401**, `WWW-Authenticate`, JSON |
| Client sending wrong HTTP Basic password | `AuthenticationWebFilter` → `ServerAuthenticationFailureHandler` | HTTP **401**, possibly same JSON and challenge |
| Logged in but calling URL requiring `ROLE_ADMIN` | `ServerAccessDeniedHandler` | HTTP **403 Forbidden** |
| Anonymous browser calling `/web/home` | Redirect entry point | HTTP **302** to `/login` |
| Browser submitting form with wrong password | Form-login failure handler | Redirect `/login?error` or error page |
| POST missing CSRF token | `CsrfWebFilter` and CSRF access-denied handling | Usually HTTP **403** |
| Database or IdP outage | Authentication/system error handling | Per error policy, **not** defaulted to "wrong password" |

**The same 401 does not prove the same error source.** For a request missing the Authorization header, the Basic converter may return `Mono.empty()`; the filter does not attempt login and authorization later requires login. For a request with a Basic header and wrong password, the manager emits `BadCredentialsException` and the failure handler handles it.

### 3.1. Why Distinguish Entry Point from Failure Handler?

`ServerAuthenticationEntryPoint` means **"which method will ask the client to authenticate?"** whereas `ServerAuthenticationFailureHandler` means **"what to do when an authentication attempt fails?"**.

An application might configure a JSON entry point for anonymous routes, while wrong passwords still receive the default HTTP Basic failure handler's body/status. To guarantee consistent JSON, test **both branches** and, if needed, wire the failure handler to the same entry point using `ServerAuthenticationEntryPointFailureHandler`.

### 3.2. Why Should 403 Not Be Changed to 401?

A logged-in user with `ROLE_USER` but missing `ROLE_ADMIN` should normally receive 403. Returning 401 instead can cause the frontend to repeatedly prompt for login even though the password is right; that misrepresents the cause. Only use the entry point when authentication is needed; authorization denials for a valid principal should go through `ServerAccessDeniedHandler`.

### 3.3. "No Authorization Header" Is Not an Error on a Public Endpoint

`GET /public` with `permitAll()` must work without a header. The entry point **does not automatically run on every request lacking credentials**. Only when a protection step requires valid authentication that the request lacks does the entry point need to start the authentication-request response.

## 4. Built-in Implementations

Spring Security reactive provides several entry points:

| Class | When appropriate | Typical result |
| --- | --- | --- |
| `HttpBasicServerAuthenticationEntryPoint` | HTTP Basic | 401 + `WWW-Authenticate: Basic ...` |
| `BearerTokenServerAuthenticationEntryPoint` | OAuth2 Resource Server Bearer | 401 + `WWW-Authenticate: Bearer ...` per RFC 6750 |
| `RedirectServerAuthenticationEntryPoint` | Browsers and form login | Redirect to login URL, usually 302 |
| `HttpStatusServerEntryPoint` | Want to return only a status | Chosen status; **does not guarantee Basic/Bearer challenge** |
| `DelegatingServerAuthenticationEntryPoint` | Choose entry point by `ServerWebExchangeMatcher` | Delegates to matching entry point |
| Custom lambda/class | API wants JSON body, error envelope, custom headers | Defined inside `Mono<Void>` |

### 4.1. HTTP Basic

Example response when the server requests Basic authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="my-api"
Cache-Control: no-store
Content-Type: application/json

{"error":"unauthorized"}
~~~

This is an **illustration of a custom JSON entry point**, not the full default output of Spring Security. `WWW-Authenticate` is the **authentication challenge**. HTTP 401 per protocol semantics requires at least one appropriate challenge; a JSON body does not replace the header.

Spring Security includes:

~~~java
HttpBasicServerAuthenticationEntryPoint basicEntryPoint =
        new HttpBasicServerAuthenticationEntryPoint();
basicEntryPoint.setRealm("my-api");
~~~

This is a snippet inside a configuration class. Import the class from `org.springframework.security.web.server.authentication`. This is useful when you only need a Basic challenge/realm without a custom JSON body. `realm` is not a user/role and does not prove authentication succeeded.

### 4.2. Bearer/OAuth2 Resource Server

JWT/OAuth2 Bearer APIs should use `BearerTokenServerAuthenticationEntryPoint` from `org.springframework.security.oauth2.server.resource.web.server`. When a request lacks a token, the header may be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When a token has been recognized by the parser/decoder but is invalid, the Bearer entry point uses `BearerTokenError` to attach status/challenge/error per **RFC 6750**. Do not assume every missing-token request needs `invalid_token`.

If custom code writes JSON for a Bearer API, it must preserve the scheme-accurate challenge. Do not return `WWW-Authenticate: Basic` for a Bearer-only resource server; nor claim a JWT is verified without a validator checking issuer, audience, signature, and expiration per design.

### 4.3. Browsers and Form Login

Browsers normally expect:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

`RedirectServerAuthenticationEntryPoint` fits form login, while the form authentication failure handler can redirect to `/login?error`. Keep CSRF enabled for form login and state-changing operations using cookie sessions.

If a JavaScript `fetch` client calls an API and gets redirected to HTML login, it may follow the redirect automatically, receive 200 HTML, and fail on `response.json()`. For JSON APIs, returning 401 JSON directly is easier to handle. Split security chains by `/api/**` and `/web/**` if two different authentication mechanisms are needed.

### 4.4. Status-Only Entry Point

`HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED)` can set status 401. However, if using Basic/Bearer, setting status without a challenge can violate HTTP authentication standards. Only choose status-only when the threat model and client protocol permit it or another component ensures the required headers.

## 5. How to Configure in ServerHttpSecurity

### 5.1. Entry Point from Authorization

~~~java
http.exceptionHandling(errors ->
        errors.authenticationEntryPoint(myEntryPoint));
~~~

`myEntryPoint` is a `ServerAuthenticationEntryPoint` variable/bean; this is a DSL snippet, not a standalone application. The `ServerHttpSecurity.ExceptionHandlingSpec.authenticationEntryPoint(...)` method decides how to request authentication when authorization requires it.

### 5.2. Wiring the Failure Handler for HTTP Basic Too

~~~java
http.httpBasic(basic -> basic
        .authenticationEntryPoint(myEntryPoint)
        .authenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(
                        myEntryPoint)));

http.exceptionHandling(errors ->
        errors.authenticationEntryPoint(myEntryPoint));
~~~

This snippet requires a defined `myEntryPoint`. Meaning:

1. `httpBasic.authenticationEntryPoint` replaces the Basic entry point.
2. `ServerAuthenticationEntryPointFailureHandler` **forwards the call** from a failure handler to the entry point, so wrong Basic credentials follow the same response pattern.
3. `exceptionHandling.authenticationEntryPoint` handles cases where authorization requires login.
4. `AuthenticationServiceException` from the authentication source may be rethrown by default by the adapter; do not force infrastructure errors into 401 "wrong password" and hide outages.

**A configuration with only item 3 does not prove all wrong passwords have the same body as anonymous 401.** Always test both missing headers and wrong passwords directly.

### 5.3. Access Denied Handler Handles 403 Independently

~~~java
ServerAccessDeniedHandler forbidden = (exchange, denied) -> {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
};

http.exceptionHandling(errors -> errors
        .authenticationEntryPoint(myEntryPoint)
        .accessDeniedHandler(forbidden));
~~~

This is a snippet requiring imports and `myEntryPoint`. For JSON APIs, the 403 handler can share the same JSON-writing utility with a different status and error code. Do not use the 401 entry point to handle an authenticated user lacking a role.

## 6. Writing a Custom JSON ServerAuthenticationEntryPoint

Since it is a functional interface, you can use a lambda:

~~~java
ServerAuthenticationEntryPoint json401 = (exchange, ex) -> {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.UNAUTHORIZED);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    response.getHeaders().setCacheControl("no-store");
    response.getHeaders().set(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"my-api\", charset=\"UTF-8\"");

    byte[] bytes = "{\"error\":\"unauthorized\"}"
            .getBytes(StandardCharsets.UTF_8);

    return response.writeWith(
            Mono.just(response.bufferFactory().wrap(bytes)));
};
~~~

This snippet belongs in a configuration class and needs imports for `ServerHttpResponse`, `HttpStatus`, `MediaType`, `HttpHeaders`, `StandardCharsets`, `Mono`, and `ServerAuthenticationEntryPoint`. We use a **fixed** JSON body without reflecting exception messages.

### 6.1. Required Details

- `Mono<Void>` is **returned** so WebFlux subscribes within the request lifecycle. Do not call `.subscribe()` or `.block()` manually inside the entry point.
- `Content-Type` matches the JSON body, status is `401`, and `Cache-Control: no-store` reduces the risk of caching errors containing sensitive context.
- `WWW-Authenticate: Basic ...` must match the demo API's scheme. If using Bearer, change the challenge and comply with RFC 6750.
- If dynamic body fields are needed (timestamp, request ID, error code), use a JSON serializer and proper escaping; never concatenate user-supplied data directly into JSON.
- Do not send raw `ex.getMessage()`, stack traces, internal user IDs, raw tokens, or passwords.
- Do not write the response twice after committing, and do not continue to the controller once the entry point finishes a rejection response.

### 6.2. Standardized Error Envelope

`Problem Details` per RFC 9457 can be used if the product adopts that standard:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required"
}
~~~

This is only an **example JSON illustrating Problem Details formatting**, not the output of the demo code in section 7. For real Problem Details, use `Content-Type: application/problem+json` and the standard schema. Only include server-issued correlation IDs/trace IDs, without exposing credentials in `detail`.

## 7. Complete Example with Java 17+ and Spring WebFlux

We build a Boot application using HTTP Basic that returns JSON for 401/403 without redirecting to HTML form login.

Endpoints:

- `GET /public`: public, returns JSON.
- `GET /api/me`: requires authentication.
- `GET /api/admin`: requires `ROLE_ADMIN`.

Local users:

- `reader` / `reader123!` with `ROLE_USER`.
- `admin` / `admin123!` with `ROLE_USER` and `ROLE_ADMIN`.

Sample credentials are only for local learning machines; HTTP Basic **must use HTTPS** in real deployments because Base64 does not encrypt secrets.

### 7.1. pom.xml

Uses Maven, Java 17+, Spring Boot **4.1.2**, and dependencies **Spring Reactive Web** and **Spring Security**. File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-entrypoint-demo</artifactId>
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
~~~

The Boot BOM manages Security/Framework/Reactor versions. Do not add `spring-boot-starter-web` to avoid mixing Spring MVC/Servlet with WebFlux.

### 7.2. Complete Java Source

Create `src/main/java/com/example/entrypoint/ReactiveEntryPointDemoApplication.java`:

~~~java
package com.example.entrypoint;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveEntryPointDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveEntryPointDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader123!"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123!"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint requireAuthentication =
                (exchange, error) -> sendJson(exchange,
                        HttpStatus.UNAUTHORIZED, "unauthorized", true);

        ServerAccessDeniedHandler forbidden =
                (exchange, error) -> sendJson(exchange,
                        HttpStatus.FORBIDDEN, "forbidden", false);

        return http
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(requireAuthentication)
                        .authenticationFailureHandler(
                                new ServerAuthenticationEntryPointFailureHandler(
                                        requireAuthentication)))
                .formLogin(form -> form.disable())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(requireAuthentication)
                        .accessDeniedHandler(forbidden))
                .build();
    }

    private static Mono<Void> sendJson(ServerWebExchange exchange,
            HttpStatus status, String errorCode, boolean basicChallenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setCacheControl("no-store");

        if (basicChallenge) {
            response.getHeaders().set(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"entrypoint-demo\", charset=\"UTF-8\"");
        }

        // errorCode is only an internal literal, containing no client input.
        String body = "{\"error\":\"" + errorCode + "\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class Api {

        @GetMapping("/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("message", "PUBLIC_OK"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(Principal principal) {
            return Mono.just(Map.of("user", principal.getName()));
        }

        @GetMapping("/api/admin")
        Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("message", "ADMIN_OK"));
        }
    }
}
~~~

**Why does this code hit the mark?**

1. `@EnableWebFluxSecurity` and `SecurityWebFilterChain` use WebFlux reactive APIs; Servlet `HttpSecurity` is not imported.
2. `MapReactiveUserDetailsService` provides in-memory users and a real `PasswordEncoder` (delegating encoder choosing an appropriate default algorithm); `{noop}` is not used for passwords.
3. `/public` uses `permitAll()`, so anonymous callers can receive public data.
4. `/api/me` requires authentication and triggers the entry point when anonymous.
5. `/api/admin` requires a role; `reader` is authenticated but lacks permission, so the access-denied handler returns 403.
6. `httpBasic(...).authenticationFailureHandler(...)` handles **wrong passwords** with the same 401 JSON logic.
7. `formLogin(...disable())` ensures no HTML redirect from form login in the demo chain.
8. `sendJson(...)` returns a `Mono<Void>` writing the response, including `WWW-Authenticate` only on 401 and avoiding echoing exception text.
9. The example only has GET endpoints; **there is no need to disable CSRF**. If adding POST APIs using cookies or browser-cached credentials, CSRF must be analyzed separately.
10. Hard-coded passwords are for local use only. Production requires a proper identity store, HTTPS, MFA/rate limiting, and secure auditing.

### 7.3. Running

In the directory containing `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

On Windows, use `.\mvnw.cmd clean package` and `.\mvnw.cmd spring-boot:run`. If no wrapper is present, use `mvn clean package` then `mvn spring-boot:run` with an installed Maven. By default the server listens on `http://localhost:8080`.

### 7.4. Testing with curl

Open a second terminal:

~~~bash
# Public, no Authorization sent
curl -i http://localhost:8080/public

# Anonymous calling endpoint requiring authentication
curl -i http://localhost:8080/api/me

# Basic credentials present but wrong password
curl -i -u 'reader:wrong' http://localhost:8080/api/me

# Valid credentials
curl -i -u 'reader:reader123!' http://localhost:8080/api/me

# Logged in but missing role
curl -i -u 'reader:reader123!' http://localhost:8080/api/admin

# Sufficient role
curl -i -u 'admin:admin123!' http://localhost:8080/api/admin

# API-only policy does not rely on Accept
curl -i -H 'Accept: text/html' http://localhost:8080/api/me
~~~

On Windows PowerShell, use `curl.exe` if `curl` is an alias. Do not enable `-L` when checking redirects; the example does not use form login so 302 is not expected.

| Request | Status | Expected body | Meaning |
| --- | --- | --- | --- |
| Anonymous `/public` | **200** | `{"message":"PUBLIC_OK"}` | Entry point not needed |
| Anonymous `/api/me` | **401** | `{"error":"unauthorized"}` | Authorization requires authentication |
| Reader wrong password `/api/me` | **401** | `{"error":"unauthorized"}` | Basic authentication failure |
| Reader valid `/api/me` | **200** | `{"user":"reader"}` | Authentication succeeded |
| Reader `/api/admin` | **403** | `{"error":"forbidden"}` | Authenticated but missing `ROLE_ADMIN` |
| Admin `/api/admin` | **200** | `{"message":"ADMIN_OK"}` | Has `ROLE_ADMIN` |
| Anonymous `/api/me`, `Accept: text/html` | **401** | `{"error":"unauthorized"}` | Does not auto-redirect to HTML |

In both 401 branches, verify `Content-Type: application/json`, `Cache-Control: no-store`, and `WWW-Authenticate: Basic realm="entrypoint-demo", charset="UTF-8"`. In the 403 branch, the code **does not attach a Basic challenge**. Extra server/framework output may vary by version, while the custom body and status codes in these branches are deterministic.

If later returning a multi-field `Map` object, JSON key order is not guaranteed by `Map.of`; unit/integration tests should assert **JSON field values**, not a fixed-order string.

## 8. When an Application Has Both Browser and REST API

An application can share the same user store with two UX contracts:

- Browser `/web/**`: form login, WebSession cookie, redirect `/login`, HTML errors.
- API `/api/**`: JSON 401/403, Basic/Bearer or another token, no form redirect.

Two ordered chains can be used:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(rules ->
                    rules.anyExchange().authenticated())
            .httpBasic(basic -> basic
                    .authenticationEntryPoint(json401EntryPoint)
                    .authenticationFailureHandler(
                            new ServerAuthenticationEntryPointFailureHandler(
                                    json401EntryPoint)))
            .formLogin(form -> form.disable())
            .exceptionHandling(errors ->
                    errors.authenticationEntryPoint(json401EntryPoint))
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(rules -> rules
                    .pathMatchers("/", "/login").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(basic -> basic.disable())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

**Architectural snippet, not a standalone project:** `json401EntryPoint` is a bean/parameter that must be defined; imports for `@Bean`, `@Order`, `PathPatternParserServerWebExchangeMatcher`, `Customizer`, and the mentioned interfaces are required. When applying to the demo project, **replace** the old security bean rather than declaring overlapping match-all chains without understanding ordering.

`@Order` decides which chain goes first; `securityMatcher(...)` decides which requests belong to which chain. `authorizeExchange(...).pathMatchers(...)` decides permissions **inside a chain**. Do not confuse these three.

**Important:** if an SPA uses cookie sessions to call a JSON API, do not casually configure the API as stateless or disable CSRF. Returning JSON responses does not mean the browser stops sending cookies automatically. Separate the authentication model, session repository, CORS, CSRF, and cookie policy according to the threat model.

### DelegatingServerAuthenticationEntryPoint

`DelegatingServerAuthenticationEntryPoint` is another option if you only need one entry point choosing between JSON and redirect based on `ServerWebExchangeMatcher`. However, it **only routes authentication-request behavior**; it does not automatically disable form login, swap password converters, or separate sessions/tokens. When mechanisms genuinely differ, multiple `SecurityWebFilterChain` beans are usually clearer.

## 9. Edge Cases

### 9.1. Missing vs Invalid vs Unsupported Credentials

A request with no Authorization header may be skipped by the Basic converter. A request with `Authorization: Bearer ...` when only Basic is configured may also be skipped by the Basic converter; that **does not prove the Bearer token is invalid** because there is no Bearer decoder yet. A request with properly formatted Basic credentials but a wrong password takes the authentication failure path.

Even though all these cases may ultimately return 401, **they should not be logged/alerted as the exact same incident type**. Wrong-password counts matter for rate limiting; missing headers on a public API can be normal.

### 9.2. Authentication Infrastructure Errors

A database or identity provider timeout is not always "BadCredentials". The `ServerAuthenticationEntryPointFailureHandler` adapter has a default option to rethrow `AuthenticationServiceException`. Keep that distinction so monitoring reports the real error instead of turning every exception into 401 and making clients think they just need to re-enter a password.

### 9.3. Form Login Failure Differs from Login Prompt

In form login, an unauthenticated request to a private page normally leads to a **login page redirect**. However, a user entering a wrong password usually triggers the **form failure handler**, which may redirect to `/login?error`. Using the anonymous-route entry point to replace a failure handler in the wrong place easily causes redirect loops.

### 9.4. CSRF Has Its Own Handler

A `POST` without a valid CSRF token may receive 403 from `CsrfWebFilter`. Setting only `exceptionHandling.accessDeniedHandler(...)` does not guarantee all CSRF responses go through it. Test and configure the CSRF handler if the application wants a unified JSON format, rather than replacing CSRF errors with 401.

### 9.5. Once Response Is Written, Do Not Write Again

In `commence(...)`, return the publisher that writes the data and completes. Do not continue controller processing after sending the challenge, and do not call `response.setComplete()` manually and then try to write a body again. Once the response is committed, resetting status/headers may have no effect; this is not something that can be "fixed" with `block()`.

### 9.6. HTTP 401 and WWW-Authenticate

Per HTTP authentication semantics, a 401 response needs an appropriate challenge. For Basic, `Basic realm="..."`; for a Bearer resource server, `Bearer` and parameters per RFC 6750. Using a JSON body does not waive protocol requirements. If you do not want browsers to pop up the native Basic dialog, choose a different appropriate authentication mechanism/UX instead of stripping the challenge header and hoping all Basic clients stay compliant.

## 10. Testing at the Entry Point Level

When writing unit tests for an entry point, you can use `MockServerWebExchange` from Spring Test and `StepVerifier` from Reactor Test. Procedure:

1. Create a mock exchange for `GET /api/me`.
2. Create an `AuthenticationException` indicating login is required, e.g., `AuthenticationCredentialsNotFoundException`.
3. Call `entryPoint.commence(exchange, exception)`.
4. Subscribe with `StepVerifier`; verify the publisher completes.
5. Assert status 401, content type, `WWW-Authenticate`, and body.
6. Ensure raw exception text is not written into the response.

Snippet for a test method:

~~~java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/me"));

AuthenticationException reason =
        new AuthenticationCredentialsNotFoundException(
                "Authentication required");

StepVerifier.create(entryPoint.commence(exchange, reason))
        .verifyComplete();

assertEquals(HttpStatus.UNAUTHORIZED,
        exchange.getResponse().getStatusCode());
assertEquals(MediaType.APPLICATION_JSON,
        exchange.getResponse().getHeaders().getContentType());
~~~

This is a **test snippet**, not a standalone runnable JUnit class: `entryPoint` must be injected or created from config, and imports `MockServerWebExchange`, `MockServerHttpRequest`, `StepVerifier`, and `assertEquals` must be present in the test class along with compatible Spring Test, Reactor Test, and JUnit dependencies. To inspect the body, decode the mock response's `DataBuffer` instances using the version-appropriate Spring Test API.

### 10.1. Practical Test Matrix

| Case | What to assert |
| --- | --- |
| Public anonymous | 200, entry point not called |
| Private anonymous | 401 JSON + Basic challenge, no redirect |
| Private wrong Basic password | 401 JSON + challenge via failure handler |
| Private valid credentials | 200, controller runs |
| User missing admin role | 403 JSON, no Basic challenge |
| Admin with sufficient role | 200 |
| `Accept: text/html` to API | Still follows API policy, does not auto-return HTML login |
| Unauthenticated browser to browser chain | Redirects per form login |
| Missing/invalid Bearer token in resource server | Appropriate Bearer challenge, no Basic challenge |
| Invalid CSRF token | Outcome per `CsrfWebFilter`, not forced into 401 |
| Auth database/IdP failure | Appropriate infrastructure error signal, no leaked stack trace |

Check **status, Content-Type, WWW-Authenticate, Location, Cache-Control**, and body, not just a single HTTP number. For WebFlux HTTP-level tests, `WebTestClient` and Spring Security test support can simulate users/headers; for standalone entry points, testing the publisher catches uncompleted `Mono<Void>` bugs.

### 10.2. Safe Debugging

In dev environments, you can use:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Logs should distinguish `credentials_absent`, `authentication_failed`, `authorization_denied`, `csrf_denied`, and `authentication_service_unavailable`. Never log tokens, Basic headers, passwords, or session cookies; if a request ID exists, log only IDs permitted by the observability policy. Never use verbatim `exception.getMessage()` as an HTTP response.

## 11. Common Mistakes

**Mistake 1 — Using Servlet AuthenticationEntryPoint for WebFlux.** The Servlet API uses `HttpServletRequest`/`HttpServletResponse`; the reactive API uses `ServerWebExchange` and `Mono<Void>`. Check package imports and do not copy `HttpSecurity` code into `ServerHttpSecurity`.

**Mistake 2 — Changing the entry point in exceptionHandling, yet wrong passwords still have a different format.** Basic authentication failures go through the failure handler. Configure `ServerAuthenticationEntryPointFailureHandler` when you want the same JSON entry point for the wrong-credentials branch.

**Mistake 3 — Returning 401 for an authenticated user lacking a role.** That case requires `ServerAccessDeniedHandler` returning 403; returning 401 makes the frontend unnecessarily re-prompt for login.

**Mistake 4 — Omitting WWW-Authenticate on Basic/Bearer 401.** A JSON body does not replace the challenge. Protocol-compliant clients may require that header.

**Mistake 5 — Basic entry point in a Bearer-only API.** Sends the wrong scheme challenge; use `BearerTokenServerAuthenticationEntryPoint` and RFC 6750 policy instead.

**Mistake 6 — Assuming returning JSON eliminates CSRF.** APIs using cookies/browser-cached credentials still face CSRF risk; response format does not change the threat model.

**Mistake 7 — Using ControllerAdvice to handle all security errors.** Security WebFilters run before controllers; entry points, authentication failure handlers, and access-denied handlers must be configured in the security layer.

**Mistake 8 — Writing body after response commit.** The reactive publisher writing the response must be returned, without manual subscribing, double-writing, or blocking the event loop.

**Mistake 9 — Testing only missing headers, not wrong passwords.** The two requests follow different paths; the same status does not guarantee consistent body/headers.

**Mistake 10 — API redirecting to /login.** Inspect `SecurityWebFilterChain` matchers, `@Order`, formLogin, and browser fallbacks; `Accept` alone does not guarantee JSON.

**Mistake 11 — Error messages disclosing account information.** Do not include passwords, non-existent usernames, provider secrets, or stack traces in JSON; use generic messages/error codes.

**Mistake 12 — Turning all infrastructure errors into "bad credentials".** Monitor and handle user store/JWK/IdP outages properly instead of silently trading accuracy/safety away.

## 12. Production Checklist

1. Clearly define which routes use Basic, Bearer, browser form login, or sessions.
2. Use reactive `ServerAuthenticationEntryPoint`, never confusing it with Servlet.
3. 401 entry points have challenge/status/body matching the authentication scheme.
4. Configure Basic/Bearer authentication failure handlers properly if unified JSON is desired.
5. Access-denied handler distinguishes 403 for authenticated users lacking permissions.
6. CSRF has its own policy for cookies/browsers; never disable it to "fix" a status code.
7. With multiple chains, verify `securityMatcher`, `@Order`, and fallbacks so no URLs slip through.
8. Do not disclose exception details, credentials, tokens, session IDs, or internal info.
9. Do not perform blocking I/O, `block()`, or manual `subscribe()` in `commence(...)`.
10. Test anonymous, wrong credentials, authenticated, wrong role, malformed token, Bearer challenge, browser redirect, and service errors.
11. Have an error envelope and logging consistent with other business error codes.
12. For Basic, run only over HTTPS; for Bearer, validate JWTs thoroughly using a supported library/server.
13. Verify the Spring Security version from the Boot BOM before copying APIs or imports.
14. Inspect `curl -i` for both headers and body; do not let redirect-following hide the root cause.

## 13. Self-Assessment

**Question 1.** When `GET /api/me` lacks credentials and requires `authenticated()`, what does `ServerAuthenticationEntryPoint` do?

**Answer:** Initiates the authentication-request response, e.g., 401 + Basic challenge or login redirect depending on the mechanism. It does not check passwords.

**Question 2.** Does a wrong Basic password definitely go through the entry point in `exceptionHandling`?

**Answer:** No. A failed authentication attempt usually runs `AuthenticationWebFilter`'s `ServerAuthenticationFailureHandler`; `ServerAuthenticationEntryPointFailureHandler` can be used to delegate to the entry point.

**Question 3.** User `reader` is authenticated but calls `/api/admin`; should 401 or 403 be returned?

**Answer:** 403 if only `ROLE_ADMIN` is missing; use `ServerAccessDeniedHandler`.

**Question 4.** Why does custom JSON 401 for HTTP Basic still need `WWW-Authenticate`?

**Answer:** Per HTTP semantics, 401 must include an authentication challenge; Basic clients need to know the scheme/realm. The JSON body only provides supplementary info.

**Question 5.** Can `HttpBasicServerAuthenticationEntryPoint` be used in a Bearer-only API?

**Answer:** No. A Bearer resource server needs a Bearer/RFC 6750 challenge, usually via `BearerTokenServerAuthenticationEntryPoint`.

**Question 6.** Does a `permitAll` API request without an Authorization header invoke the entry point?

**Answer:** Not necessarily; if no authentication is required and no authentication attempt failed, public requests can be processed normally.

**Question 7.** Why can a POST missing a CSRF token get 403 even if the user is not logged in?

**Answer:** The CSRF filter makes its own error decision for state-changing requests; do not use a 401 entry point to mask a CSRF situation.

**Question 8.** Can `@RestControllerAdvice` replace an entry point?

**Answer:** Not reliably for all pre-controller security errors. Configure proper entry point/failure/denied handlers at the WebFlux Security layer.

## 14. Official References

- [Spring Security — ServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html)
- [Spring Security — ExceptionTranslationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Spring Security — ServerHttpSecurity.HttpBasicSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html)
- [Spring Security — ServerAuthenticationEntryPointFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationEntryPointFailureHandler.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — HttpBasicServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html)
- [Spring Security — BearerTokenServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — HTTP Basic in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — OAuth2 Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
