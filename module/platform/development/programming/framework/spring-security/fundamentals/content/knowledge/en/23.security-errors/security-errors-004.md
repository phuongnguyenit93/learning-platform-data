# AuthenticationEntryPoint: Requesting Client Authentication Credentials

> **Scope:** Spring Security on the Servlet stack (`HttpSecurity`, `SecurityFilterChain`, `jakarta.servlet`), with configuration compatible with Spring Security 6.x / Spring Boot 3.x. In WebFlux, the corresponding concept is `ServerAuthenticationEntryPoint`, though its API and filters differ.

## 1. The Problem to Solve

Suppose a client calls `GET /api/hello`, but the resource is only for logged-in users. If the request does not yet carry valid authentication credentials, the server needs to **tell the client how to start authenticating**: return HTTP `401 Unauthorized` with an invitation to use HTTP Basic/Bearer, or redirect the browser to a login page.

In Spring Security, **`AuthenticationEntryPoint` decides the response that initiates the authentication process**. The name "EntryPoint" is easily misunderstood: it is not the entry point of the entire security filter chain, and **it does not check passwords, decode JWTs, or grant access permissions itself**. It is invoked when a request requires authentication or when authentication fails in a flow that uses an entry point.

Distinguish three responsibilities:

- **Authentication:** who is the caller, and is their proof valid? Usually handled by authentication filters, `AuthenticationManager`, and `AuthenticationProvider`.
- **Authorization:** is the authenticated identity allowed to access the resource? Decided by `authorizeHttpRequests` rules, `AuthorizationManager`, method security, etc.
- **AuthenticationEntryPoint (initiating authentication):** when authentication is required, what HTTP response tells the client it needs to supply or supplement authentication credentials?

For example: an API requiring login may respond with `401`; a website using form login may respond with `302 Location: /login`. A different `AuthenticationEntryPoint` can be chosen per application type or per request.

## 2. Mechanism with ExceptionTranslationFilter

`ExceptionTranslationFilter` sits inside the Servlet security filter chain, acting as a bridge between **security exceptions** and **HTTP responses**. This filter does not enforce authorization policies itself; it handles `AuthenticationException` or `AccessDeniedException` thrown within the remainder of the chain that it wraps.

Typical processing flow when accessing a protected endpoint while unauthenticated:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as Security filters
    participant A as AuthorizationFilter
    participant E as ExceptionTranslationFilter
    participant P as AuthenticationEntryPoint
    C->>F: GET /api/hello (no credentials)
    F->>E: Continue filter chain
    E->>A: Check permissions for request
    A-->>E: AccessDeniedException (anonymous)
    E->>P: commence(request, response, exception)
    P-->>C: 401 + WWW-Authenticate (or 302 login)
~~~

**Decision points of `ExceptionTranslationFilter`:**

1. When encountering `AuthenticationException`, it starts the authentication process via `AuthenticationEntryPoint`.
2. When encountering `AccessDeniedException` and the caller is anonymous (or when the current authentication level is insufficient according to the trust resolver), it can also use `AuthenticationEntryPoint`: authentication is needed before checking permissions further.
3. When encountering `AccessDeniedException` from a fully authenticated user lacking permissions, it delegates to `AccessDeniedHandler`, typically returning `403 Forbidden`.

Before calling the entry point in the branches above, the filter clears/handles the security context and may save the original request via `RequestCache` to return to after login. Saving the request **depends on configuration**; stateless APIs typically do not need to save it in a session.

**Important limitation:** `ExceptionTranslationFilter` only catches exceptions passing through its `doFilter` scope. An authentication filter placed before it, such as `BasicAuthenticationFilter`, can invoke its own entry point directly when credentials are wrong. Therefore, HTTP Basic authentication error handling sometimes must be configured directly inside `httpBasic(...)`, rather than assuming all errors come from `exceptionHandling(...)`.

## 3. The AuthenticationEntryPoint Interface

Core method on Servlet:

~~~java
void commence(HttpServletRequest request,
              HttpServletResponse response,
              AuthenticationException authException)
        throws IOException, ServletException;
~~~

Meaning of each parameter:

- `request`: the request attempting to access the resource; URI/method can be inspected to choose an appropriate response.
- `response`: where status, headers, content type, and body or redirect are set.
- `authException`: the reason authentication needed to be initiated; **never return verbatim** internal exception messages to the client.

The entry point is expected to write an appropriate response so the client can log in or send authentication credentials. It **does not re-invoke the protected endpoint**, does not create a principal, does not treat the request as authenticated, and does not decide the principal's permissions.

### Common Implementations

| Authentication Method | Typical Entry Point | Response for Unauthenticated Request |
|---|---|---|
| HTTP Basic | `BasicAuthenticationEntryPoint` | `401`, usually with `WWW-Authenticate: Basic realm="..."` |
| Login Page | `LoginUrlAuthenticationEntryPoint` | Redirect to the login URL, usually HTTP `302` |
| OAuth2 Resource Server/Bearer | `BearerTokenAuthenticationEntryPoint` | `401`, `WWW-Authenticate: Bearer` challenge per Bearer spec |
| API needing fixed status | `HttpStatusEntryPoint` | Sends the configured status (e.g., `401`), without designing a challenge itself |
| API with custom JSON errors | Lambda/class implementing `AuthenticationEntryPoint` | Sets status, headers, and JSON per the API contract |

**Choose based on the actual authentication protocol.** With HTTP Basic, `WWW-Authenticate` tells the client to use the Basic scheme. With Bearer, use the entry point provided out of the box by Spring Security to preserve OAuth2-compliant error header parameters; do not return "Basic" for an API that only accepts Bearer.

## 4. 401 and 403: Where Do They Differ?

| Scenario | Typical Handling | Meaning |
|---|---|---|
| Anonymous calls an `authenticated()` resource | Entry point: `401` or login redirect | Authentication must be started |
| HTTP Basic with wrong username/password | HTTP Basic entry point: `401` | Credentials are invalid, must re-authenticate |
| Expired/invalid Bearer token | Bearer entry point: typically `401` | A valid token must be supplied |
| Logged in but missing `ROLE_ADMIN` | `AccessDeniedHandler`: `403` | Identity is known, but lacks permission |
| `permitAll()` endpoint | Returns response from the application | No challenge needed |
| Request rejected by CSRF protection | Usually `403` | A CSRF protection error; not equivalent to a wrong password |

**Note:** `401 Unauthorized` in HTTP essentially means "not validly authenticated yet", while `403 Forbidden` is access denial. Do not infer from the status name `Unauthorized` that this is a missing-role error. Some specialized schemes or entry points respond differently; read the actual configuration.

For web pages, `302 /login` may be right for anonymous requests. For REST APIs, an HTML login redirect usually makes client handling difficult and can obscure the error cause. Determine whether API clients expect `401`/challenge or browsers expect a login page.

## 5. Runnable Example: API Returning 401 JSON + HTTP Basic

This example uses **Java 17, Spring Boot 3.5.16 (Spring Security 6.x), Maven**. The goal is to observe `AuthenticationEntryPoint`; this is a minimal demo, not a production account management pattern.

File structure:

~~~text
security-entrypoint-demo/
├── pom.xml
└── src/main/java/com/example/securitydemo/
    ├── SecurityDemoApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

### 5.1. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>security-entrypoint-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. SecurityDemoApplication.java

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.securitydemo;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEntryPoint apiEntryPoint() {
        return (request, response, authException) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"demo\"");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(
                    "{\"error\":\"unauthorized\","
                    + "\"message\":\"Authentication is required\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationEntryPoint apiEntryPoint)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(apiEntryPoint)
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}pass123")
                    .roles("USER")
                    .build()
        );
    }
}
~~~

**Configuration explanation:**

- `/public` is a URL requiring no login, `/api/hello` requires a valid `Authentication`, `/api/admin` requires `ROLE_ADMIN`.
- `apiEntryPoint()` produces HTTP `401`, a Basic challenge header, and a stable JSON body. It does **not** handle password checking.
- `.exceptionHandling(...authenticationEntryPoint(...))` handles cases where an unauthenticated request is rejected by the authorization filter.
- `.httpBasic(...authenticationEntryPoint(...))` uses the **same entry point** for errors occurring directly when the HTTP Basic authentication filter checks credentials; if not configured, this error path may use a separate handler.
- `SessionCreationPolicy.STATELESS` ensures requests authenticate independently and do not use a session as the `SecurityContext` store; HTTP Basic sends credentials on every request.
- `{noop}` and password `pass123` are only so the demo can run; real systems must use an appropriate password encoder, protect secrets, and use **HTTPS**.
- The example **keeps default CSRF protection**. All test requests are `GET`; if adding state-changing endpoints (`POST`, `PUT`, `DELETE`), configure CSRF for the corresponding client model. Do not disable CSRF solely because an API uses HTTP Basic: browsers can send Basic credentials automatically.

### 5.4. DemoController.java

~~~java
package com.example.securitydemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/hello")
    public String hello(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
~~~

### 5.5. Running and Verifying

In the directory containing `pom.xml`, use JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Open another terminal to test:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:wrong http://localhost:8080/api/hello
curl -i -u alice:pass123 http://localhost:8080/api/hello
curl -i -u alice:pass123 http://localhost:8080/api/admin
~~~

Results to verify (omitting environment-dependent headers):

| Request | HTTP status | Body / key signal |
|---|---|---|
| `GET /public` | `200` | `public` |
| `GET /api/hello` without credentials | `401` | `WWW-Authenticate: Basic realm="demo"` and `unauthorized` JSON |
| `GET /api/hello` with `alice:wrong` | `401` | Also goes through the entry point attached to HTTP Basic |
| `GET /api/hello` with `alice:pass123` | `200` | Exact `hello alice` |
| `GET /api/admin` with `alice:pass123` | `403` | Authenticated, but missing `ROLE_ADMIN`; not 401 |

**JSON body of both 401 cases** generated by `apiEntryPoint()`:

~~~json
{"error":"unauthorized","message":"Authentication is required"}
~~~

The `Content-Type` header may include a charset; header order, `Date`, `Content-Length`, etc. depend on the servlet container. For `403`, only assert the status; do not depend on Spring Boot's default error body.

The important point in this experiment is that the two `401` errors have **different entry paths**: the request without credentials is detected by authorization and triggers `ExceptionTranslationFilter`; invalid Basic credentials are detected by `BasicAuthenticationFilter`, which then invokes the entry point configured for Basic. Both produce consistent responses because they share the same bean.

## 6. Same Goal, Different Challenge Styles

### HTTP Basic — Asking the Client to Send Username/Password

A sample response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
Content-Type: application/json;charset=UTF-8

{"error":"unauthorized","message":"Authentication is required"}
~~~

After the challenge, the client can retry with:

~~~http
GET /api/hello HTTP/1.1
Authorization: Basic <base64(username:password)>
~~~

Base64 is **only an encoding**, not security encryption. The protocol must run over HTTPS to avoid exposing credentials in transit. Never log this header's value.

### Form Login — Taking the Browser to the Login Page

`LoginUrlAuthenticationEntryPoint` typically responds with a `302` redirect to the configured login page, such as `Location: /login`. The user enters credentials in the form; the login-processing filters then perform authentication. The entry point merely brings them to where credentials are entered. After successful authentication, the saved request can return them to the original URL if a corresponding `RequestCache` is configured.

### OAuth2 Resource Server — Requesting a Bearer Token

For APIs using OAuth2 access tokens, the HTTP challenge uses the `Bearer` scheme, not `Basic`. Requests typically carry the `Authorization: Bearer <token>` header. Spring Security provides `BearerTokenAuthenticationEntryPoint` to return `WWW-Authenticate: Bearer` and an appropriate error description when a token is invalid.

Illustrative example of a token error:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Actual challenge parameters depend on the cause and configuration. Never dump the full exception or token into the response. With OAuth2, a **valid token missing a scope** error can be `403` and handled through the access-denied path; do not assume all Bearer errors are 401.

## 7. When Should You Configure a Custom AuthenticationEntryPoint?

A custom entry point is useful when an API has a consistent error contract, such as JSON containing `error`, `message`, and a trace ID, while preserving authentication-protocol status/headers. You can use an `AuthenticationEntryPoint` lambda as in the example, or create a dedicated class if reuse is needed.

When an application has both a website and an API, differentiate requests: browsers usually need a login redirect, while API clients usually need an explicit `401`. You can configure separate `SecurityFilterChain` beans using `securityMatcher` and appropriate ordering, or select entry points via `defaultAuthenticationEntryPointFor` / `DelegatingAuthenticationEntryPoint` with a `RequestMatcher`. Do not accidentally send APIs into a redirect flow just because the app also has form login.

**Distinguishing similarly named hooks:**

- `AuthenticationEntryPoint`: initiates authentication for a request to a protected resource.
- `AuthenticationFailureHandler`: handles failure of a login attempt actively executed by a login filter (e.g., form login POST).
- `AccessDeniedHandler`: handles access denial when the caller is authenticated but not allowed access.
- `AuthenticationProvider`: verifies credentials and returns an authentication result; not responsible for designing HTTP error bodies.

## 8. Common Errors and How to Diagnose Them

1. **Returning 403 for all anonymous requests:** check whether `AccessDeniedHandler` or an entry point hardcoding 403 was mistakenly used; check anonymous conditions, request matchers, and authentication schemes.
2. **Returning 401 for logged-in users missing a role:** check that `hasRole("ADMIN")` corresponds to the `ROLE_ADMIN` authority; the standard access-denial path uses `AccessDeniedHandler`.
3. **API receives login page HTML instead of JSON:** the application is applying form login or an entry point to the wrong scope; separate API/browser configurations.
4. **Wrong Basic credentials produce 401, but the body does not match the JSON template:** `BasicAuthenticationFilter` may be using a separately configured entry point. Check both `httpBasic(...)` and `exceptionHandling(...)`.
5. **Entry point never seems to run:** the exception may be handled by another filter, the request may be `permitAll`, or the response may already be committed; inspect the security filter chain and enable selective DEBUG logging.
6. **POST gets 403 even when unauthenticated:** the CSRF filter may be blocking the request before authorization logic runs. Check the CSRF token / credential model before blaming the entry point.
7. **Returning only `401` while forgetting the challenge:** if using Basic/Bearer, preserve the scheme's `WWW-Authenticate` requirement; default handlers are often safer than writing custom ones missing headers.
8. **Leaking sensitive data via errors:** avoid embedding `authException.getMessage()`, stack traces, passwords, tokens, or configuration details in responses. Log in a controlled way on the server and use stable client messages.
9. **Using Servlet APIs in WebFlux:** WebFlux uses `ServerAuthenticationEntryPoint`, `ServerHttpSecurity`, and reactive security filters; `HttpServletResponse` cannot be substituted directly into a reactive flow.

To observe execution flow, you can enable `logging.level.org.springframework.security=DEBUG` in development and inspect filter chains/blocked rules. Do not leave sensitive logging enabled indiscriminately in production; never log `Authorization` headers.

## 9. Self-Check Knowledge

- Anonymous calls `GET /api/admin`: why does the request usually reach `AuthenticationEntryPoint` before evaluating whether a real principal has `ROLE_ADMIN`?
- `alice` logs in successfully but only has `ROLE_USER`: why is the result `403` instead of a Basic challenge?
- In the example, if you only configure `exceptionHandling().authenticationEntryPoint(...)` and omit the configuration on `httpBasic()`, which processing path could produce a different response?
- Why should a Bearer token entry point not return `WWW-Authenticate: Basic`?
- Why can changing an entry point never turn a wrong password into a valid one or grant additional permissions to a user?

**Mastery criteria:** be able to explain **who detects the authentication/authorization error**, **who translates the error into an HTTP response**, **what the entry point asks the client to do next**, and demonstrate it with the four requests `200`, `401`, `401`, `403` in the example above.

## Official Documentation

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Handling Security Exceptions / ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter)
- [Spring Security — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [Spring Security — OAuth2 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — CSRF on Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
