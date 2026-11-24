# Designing JSON or ProblemDetail Responses in Spring Security Servlet Error Handling Components

## 1. Goal: Security Errors Are Also Part of the API Contract

When building a REST API with **Spring Boot 3.x, Spring Security 6.x, and Java 17+ on the Servlet stack**, an endpoint can be rejected **before the controller is ever called**. Therefore, configuring only `@RestControllerAdvice` to convert exceptions into JSON is usually **not enough** if you want consistent formatting for authentication and authorization errors.

Two most important scenarios:

- **401 Unauthorized**: the request requires valid authentication, yet lacks credentials, has wrong/expired credentials, or is not authenticated per policy. With HTTP Basic, you must return a proper `WWW-Authenticate` challenge; Bearer has different challenge rules.
- **403 Forbidden**: the request has been identified yet lacks permission to perform the operation, or another protection mechanism such as CSRF rejects it. Do not treat every 403 as a missing role.

In Spring Security Servlet:

- `AuthenticationEntryPoint` **initiates the authentication process or responds when unauthenticated**. For REST, it can return 401 JSON/`ProblemDetail` instead of redirecting to a login page.
- `AccessDeniedHandler` **handles `AccessDeniedException`** on the appropriate path, typically returning 403 for a principal who is authenticated yet lacks permissions.
- `ExceptionTranslationFilter` bridges security exceptions from downstream filters to the entry point or denied handler, yet **does not catch every exception from every position in the filter chain**.
- `BasicAuthenticationFilter` may also use its own entry point when HTTP Basic credentials are invalid; for uniform responses you must configure this point properly.
- `@RestControllerAdvice` primarily handles errors arising during **Spring MVC handler processing**. An error blocked by a security filter **before `DispatcherServlet`** does not pass through advice by default.

The goal of this lesson is to design **a stable error contract with accurate HTTP semantics and minimal data exposure**, usable by frontends and API clients, while distinguishing **custom JSON** from **RFC 9457 `ProblemDetail`**.

## 2. Request Flow and Error-Handling Positions

~~~text
HTTP Client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy / FilterChainProxy
    |
    +-- Authentication filters (Basic, Bearer, form, ...)
    |       |
    |       +-- Credentials invalid?
    |             -> AuthenticationEntryPoint (used by the filter)
    |
    +-- CsrfFilter, CORS, request constraints, ...
    |       |
    |       +-- Some errors have their own handlers
    |
    +-- ExceptionTranslationFilter
    |       |
    |       +-- Catches AuthenticationException/AccessDeniedException
    |           from downstream components when within scope
    |       |
    |       +-- Unauthenticated -> AuthenticationEntryPoint
    |       +-- Authenticated, missing permissions -> AccessDeniedHandler
    |
    +-- AuthorizationFilter
    |       |
    |       +-- Authorized -> DispatcherServlet -> Controller
    |       +-- Denied     -> ExceptionTranslationFilter
    |
    v
Spring MVC / Controller / Service
    |
    +-- Errors within MVC handler pipeline
    |      -> @ExceptionHandler / @RestControllerAdvice
    |
    v
HTTP Response
~~~

The diagram intentionally **does not depict the exact order of every filter**: exact positions depend on version and configuration. The main point is that errors in the security filter chain and errors in MVC **do not use the same handler by default**.

### 2.1. Which Component Returns Which Error?

| Scenario | Typical handling point | Common HTTP status |
| --- | --- | --- |
| No credentials sent to an API requiring login | `AuthenticationEntryPoint` via `ExceptionTranslationFilter` | 401 with HTTP Basic/Bearer |
| Wrong Basic username/password | Entry point used by `BasicAuthenticationFilter` | 401 |
| Logged in yet missing `ROLE_ADMIN` | `AccessDeniedHandler` via `ExceptionTranslationFilter` | 403 |
| Expired session | Authentication entry point / redirect per flow | 401 or 302 |
| Browser sends unsafe request missing CSRF token | CSRF filter / its own handler | Typically 403; body may differ |
| Resource not found in controller | MVC exception handler | 404 |
| Malformed JSON body | MVC validation/message-converter handler | 400 |
| Business rule failed | Service/MVC exception handler | 4xx or 5xx per contract |
| Unexpected server exception | Application/container error handling | 500 |

**Do not use a single "Access denied" message for all situations.** Clients need to distinguish whether to prompt for login, display "insufficient permissions", fix input, or retry later.

### 2.2. 401 Differs from 403, Beyond Just Status Codes

Example with Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/problem+json

{"type":"urn:demo:problem:authentication-required","title":"Authentication required","status":401,"detail":"Authentication is required to access this resource."}
~~~

Authenticated yet missing permissions:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{"type":"urn:demo:problem:access-denied","title":"Access denied","status":403,"detail":"You do not have permission to access this resource."}
~~~

Headers and JSON are shown for illustration; JSON property order has no meaning, and the server may add security/cache headers.

One endpoint across scenarios:

- Anonymous calls `GET /api/admin` with HTTP Basic → 401 and challenge.
- User `alice` authenticates validly yet lacks `ROLE_ADMIN` → 403.
- User `admin` has `ROLE_ADMIN` → 200.
- If switched to form login, anonymous may get a **302 redirect** instead of 401.
- If using OAuth2 Resource Server, the Bearer challenge and `error`/`scope` fields follow the corresponding specification.

**Do not alter the entry point to return 403 for every unauthenticated request**: clients lose the ability to tell that authentication is needed. Conversely, do not return 401 to an already-logged-in user who merely lacks permissions, unless an explicitly defined special policy calls for it.

## 3. Custom JSON vs. ProblemDetail: Which Should You Choose?

Both approaches are valid, provided the API has a **consistent contract** and clients know how to interpret it.

### 3.1. Custom JSON

Example:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "ACCESS_DENIED",
  "message": "You do not have permission to access this resource.",
  "status": 403,
  "requestId": "req-demo-123"
}
~~~

Advantages: control over field names, error codes, and localization; easy compatibility with existing APIs.

Drawbacks: teams may invent inconsistent `error`, `message`, `code`, `status`, and `traceId` fields; clients must learn an internal schema. For new designs, consider the Problem Details standard instead of inventing a bespoke format without clear justification.

**Never** return stack traces, SQL info, raw exception messages, passwords, Bearer tokens, session cookies, or authentication details to clients. If `requestId` is present, it should be generated/controlled by the system or trusted middleware; never echo arbitrary unvalidated headers.

### 3.2. Spring Framework 6 ProblemDetail

`org.springframework.http.ProblemDetail` represents a response body per **Problem Details for HTTP APIs (RFC 9457)**. The standard media type is:

~~~http
Content-Type: application/problem+json
~~~

Standard fields:

| Field | Meaning | Notes |
| --- | --- | --- |
| `type` | URI reference identifying the **problem type** | Defaults to `about:blank` per spec if omitted |
| `title` | Short summary, stable per problem type | Do not include sensitive data |
| `status` | HTTP status code associated with the problem | Must match the HTTP response status |
| `detail` | Specific explanation for this occurrence | Use safe phrasing; do not leak exceptions |
| `instance` | URI reference identifying the specific occurrence | Can be omitted if no safe URI exists |

`type` can be a publicly documented URL or a stable URI/URN defined by the organization. For example, `urn:demo:problem:access-denied` in this lesson **is only an illustrative namespace**, not a global system identifier. Use stable, documented type URIs in real products; clients should distinguish errors by `type` or an extension error code rather than relying on the natural-language text of `detail`.

Creating the object in Spring:

~~~java
ProblemDetail p = ProblemDetail.forStatusAndDetail(
    HttpStatus.FORBIDDEN,
    "You do not have permission to access this resource."
);
p.setTitle("Access denied");
p.setType(URI.create("urn:demo:problem:access-denied"));
~~~

This Java snippet requires importing `ProblemDetail`, `HttpStatus`, and `URI`. `ProblemDetail` **does not write the response itself inside a security filter**: you must choose the serializer, status, headers, and output stream; the complete project in Section 9 demonstrates this clearly.

### 3.3. ProblemDetail Examples for 401 and 403

~~~json
{
  "type": "urn:demo:problem:authentication-required",
  "title": "Authentication required",
  "status": 401,
  "detail": "Authentication is required to access this resource."
}
~~~

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Access denied",
  "status": 403,
  "detail": "You do not have permission to access this resource."
}
~~~

`instance` or extensions are not required in every case. When `instance` is included, avoid URL paths/queries containing tokens, emails, secret IDs, or resource IDs unknown to the caller. `type`/`title` are usually kept stable, while `detail` may vary by language or context. **Clients should not compare `detail` verbatim to drive logic.**

### 3.4. When to Choose Custom JSON?

| Scenario | Recommended choice |
| --- | --- |
| New API with no existing error contract | Usually prefer `ProblemDetail` for a standard structure |
| Existing API with a stable JSON schema used by many clients | Preserve compatibility; consider versioning when migrating |
| Internal requirement for custom `code` and multilingual UI | May use custom JSON or an extension field inside `ProblemDetail` |
| App using only HTML/form login | May use redirects/error pages instead of forcing JSON |
| Machine-to-machine REST with Bearer | `ProblemDetail` works well while preserving the proper Bearer challenge |
| Legacy gateway demanding a specific schema | Align gateway and backend contracts rather than changing responses unilaterally |

Pick one format per API version and test end-to-end. **Do not mix `application/json` with a `ProblemDetail` body or `application/problem+json` with non-standard JSON** without an explicit compatibility intent.

## 4. AuthenticationEntryPoint: Returning 401 Properly

### 4.1. Interface

~~~java
public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
~~~

This is an excerpt of the key signature for study, not a full framework source file. On Spring Boot 3, use `jakarta.servlet.*`, not `javax.servlet.*` from older ecosystems.

A REST entry point typically needs to:

1. Ensure the response is not yet committed.
2. Set `status = 401`.
3. Set the right `Content-Type` for JSON/`ProblemDetail`.
4. Preserve the **required/scheme-appropriate `WWW-Authenticate` challenge**.
5. Omit `authException.getMessage()` from the response since it may leak usernames, tokens, configuration, or internal causes.
6. Serialize a valid body using the available JSON library.
7. Ensure nothing writes to the body after the response is committed.

### 4.2. HTTP Basic Requires WWW-Authenticate

Header:

~~~http
WWW-Authenticate: Basic realm="demo-api"
~~~

tells clients they can supply Basic credentials for the protection space. If you replace `BasicAuthenticationEntryPoint` with a JSON handler and **omit this header**, some HTTP clients will fail to understand how to authenticate or fail to trigger Basic authentication properly.

One way to design the entry point:

~~~text
Not logged in / wrong Basic password
   |
   +-- 401 Unauthorized
   +-- WWW-Authenticate: Basic realm="demo-api"
   +-- Content-Type: application/problem+json
   +-- safe ProblemDetail body
~~~

**Do not force every authentication type to emit a Basic header.** Bearer APIs need a `Bearer` challenge per RFC 6750/OAuth2; form login needs a redirect entry point; and CSRF state has its own handling. If an app mixes Basic + Bearer + session, pick the entry point via request matchers or separate chains instead of hardcoding one global format/header.

### 4.3. Why Configure Both httpBasic and exceptionHandling?

With HTTP Basic:

~~~java
http
    .httpBasic(basic -> basic.authenticationEntryPoint(problemEntryPoint))
    .exceptionHandling(ex -> ex
        .authenticationEntryPoint(problemEntryPoint)
        .accessDeniedHandler(problemDeniedHandler));
~~~

This snippet belongs inside `HttpSecurity` configuration. It makes explicit that:

- When the Basic filter encounters invalid credentials, it uses the chosen entry point.
- When `ExceptionTranslationFilter` needs to initiate authentication for a protected request, it uses the same entry point.
- When an authenticated principal is denied within the handler's scope, it uses the denied handler.

Not every security exception flows through `ExceptionTranslationFilter`: another filter may handle errors directly or an error may occur before that filter's scope. Test both **no credentials sent** and **wrong credentials sent**, not just one case.

## 5. AccessDeniedHandler: Returning 403 Without Leaking Policy

### 5.1. Interface

~~~java
public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
~~~

`Authentication` and `GrantedAuthority` objects may exist when the handler runs, yet **there is no need** to include them in user-facing JSON. For instance, a user outside tenant B should learn as little as possible about document B; keep the body concise and neutral.

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Access denied",
  "status": 403,
  "detail": "You do not have permission to access this resource."
}
~~~

Avoid:

~~~json
{
  "status": 403,
  "debug": "alice missing ROLE_INTERNAL_BILLING_MANAGER on tenant-x/document-9981",
  "stackTrace": "..."
}
~~~

Role names, tenants, document IDs, and stack traces can leak sensitive data or reveal policy structure. The backend can log denial events safely, separated from what the client receives.

### 5.2. AccessDeniedHandler Does Not Equal Every 403

A `POST` request with a wrong CSRF token can be rejected by `CsrfFilter` before `AuthorizationFilter` evaluates permissions. Some configurations use **`CsrfFilter`'s own handler**, without automatically calling the custom `AccessDeniedHandler` registered on `ExceptionTranslationFilter`.

Therefore, to guarantee **every 403 is a `ProblemDetail`**, audit **all error sources**: CSRF, CORS, firewall, application, gateway, container, servlet error dispatch, etc. Never claim a single handler bean solves everything.

In the demo project, the CSRF test asserts only **status 403**, not that the body always shares the authorization 403 schema. This limitation is stated deliberately, not an overlooked test.

### 5.3. Method Security Exceptions and HTTP Status

If `@PreAuthorize` on a service throws `AccessDeniedException` during controller execution, the 403 result may flow through security exception translation/handlers or MVC exception resolution depending on configuration and registered handlers. Run **real integration tests** over the HTTP path. Never create a catch-all `@ExceptionHandler(AccessDeniedException.class)` returning 200 or swallowing errors, as that produces invalid states and breaks the contract.

## 6. Differences Between Security Filter Errors and @RestControllerAdvice

### 6.1. What Does @RestControllerAdvice Do?

In MVC, you can write:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> invalidInput(
            IllegalArgumentException exception) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Request data is invalid.");
        p.setTitle("Invalid request");
        return ResponseEntity.badRequest().body(p);
    }
}
~~~

This snippet lives in the MVC app's package/configuration and requires imports for `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, and `HttpStatus`. It applies to exceptions that the **MVC exception resolver** gets a chance to handle.

An anonymous request can be blocked by Spring Security in the filter chain **before any controller or advice runs**. Thus, adding only the Advice above may leave Basic 401 returning default text/HTML or a response not matching your desired schema.

### 6.2. Do Not Use sendError When Guaranteeing JSON

In a servlet response, `response.sendError(403)` can trigger a container error dispatch to `/error` or an error page with an unexpected body. Once you decide to return JSON in a handler, **set the status and serialize one body yourself** rather than mixing error dispatches with writing JSON.

In the project:

~~~java
response.setStatus(HttpStatus.FORBIDDEN.value());
response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
mapper.writeValue(response.getOutputStream(), problem);
~~~

This is an abbreviated snippet; the full project also sets charset/cache headers and checks whether the response is committed. If already committed, changing status/headers or writing a new body can fail or have no effect. Never overwrite a committed response from multiple places.

### 6.3. Can HandlerExceptionResolver Be Used from Filters?

You can delegate to `HandlerExceptionResolver` to reuse MVC mechanics for certain exceptions, but evaluate carefully:

- Which resolver is configured, and does it handle `AuthenticationException`/`AccessDeniedException` properly?
- Is it running **before `DispatcherServlet`**, without a controller handler or full MVC context?
- Might a handler for 401 accidentally omit `WWW-Authenticate`?
- Is there a risk of double-writes or forward/error dispatches?
- Are CSRF, Bearer, CORS, proxy, and container errors guaranteed to pass through the resolver?

For security filter authentication/authorization errors, **defining explicit entry points and denied handlers** is usually easier to control. To unify schemas, extract a **shared writer/factory class** used by both MVC and security rather than forcing every error into one `ExceptionHandler`.

## 7. HTTP and Security Rules When Emitting JSON Errors

### 7.1. Status Must Match the Body

Never return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/problem+json

{"status":403,"title":"Access denied"}
~~~

Clients, caches, and monitors seeing HTTP 200 may treat the request as successful. Keep **the HTTP response status and `ProblemDetail.status` identical**, e.g., both 403.

### 7.2. Explicit Content-Type

- Custom JSON: `application/json`.
- `ProblemDetail`: `application/problem+json`.
- Charset: UTF-8; use a serializer rather than manual JSON string concatenation that breaks escaping/Unicode.
- `Content-Length` can be left to the container; never compute it from Java character counts when output contains multi-byte UTF-8 text such as Vietnamese.
- Write the body once; avoid writing an exception message via `response.getWriter()` and then writing to the output stream again.

### 7.3. Caching and Sensitive Data

Authentication/authorization responses may carry IDs or permission context. Apply an appropriate cache policy, such as:

~~~http
Cache-Control: no-store
~~~

Other security headers such as `X-Content-Type-Options: nosniff`, HSTS, or CSP depend on the chain/proxy and response type. Never allow public/shared caches to store errors containing personal information without an explicit valid policy.

### 7.4. Never Send Raw Exceptions

Never write directly:

~~~java
problem.setDetail(authException.getMessage());
~~~

because the message may expose account names, login failure reasons, stack details, or sensitive provider data. Use deliberate messages, for example:

~~~text
401: Authentication is required to access this resource.
403: You do not have permission to access this resource.
~~~

More detailed info (error class, request correlation, user ID, policy source) belongs in **controlled structured logs**, never by default in public responses. For failed logins, do not distinguish "username does not exist" from "wrong password" in the body if doing so enables user enumeration.

### 7.5. XSS and Reflected Input

If adding client-supplied `instance`/`path`/`requestId` to JSON, avoid echoing query parameters or URLs containing tokens directly. Jackson escapes JSON strings, yet **escaping is no substitute for limiting reflected data**. Never build HTML error pages by interpolating raw, unescaped URLs or exception text.

### 7.6. Problem Type as an API Contract

Define a stable list of types:

| Illustrative type URI | HTTP status | Meaning |
| --- | --- | --- |
| `urn:demo:problem:authentication-required` | 401 | Valid authentication must be supplied |
| `urn:demo:problem:access-denied` | 403 | Not permitted |
| `urn:demo:problem:invalid-request` | 400 | Invalid input |
| `urn:demo:problem:not-found` | 404 | Resource not found or concealed |
| `urn:demo:problem:internal-error` | 500 | Generic internal error without leaking details |

These are **example types**, without live documentation URLs. In real products, publish error documentation, ownership, and versioning. You can add `code` or `traceId` extensions if their schema/lifecycle are defined; never alter the meaning of an existing type without notifying clients.

## 8. Choosing Representations by Caller and Authentication Mechanism

### 8.1. APIs and HTML Pages Have Different Needs

A Servlet application may serve:
- `/api/**`: JSON clients; 401/403 errors are `ProblemDetail`.
- `/web/**`: browser users; unauthenticated redirects to form login.
- `/assets/**`: public static resources per security policy.
- `/actuator/**`: managed separately under strict policy.

If you attach a JSON-returning entry point to every URL, web users may lose the redirect flow the UI needs. Use multiple `SecurityFilterChain`s with `securityMatcher` or a `DelegatingAuthenticationEntryPoint` with request matchers to pick the right entry point.

**`SecurityFilterChain` order matters:** `FilterChainProxy` picks the first chain whose matcher matches. Missing a catch-all chain can leave URLs outside every chain unprotected by Spring Security. `anyRequest().denyAll()` inside a narrow chain does **not** protect URLs outside that chain.

### 8.2. Basic, Bearer, and Form Login Do Not Share WWW-Authenticate

- HTTP Basic: `WWW-Authenticate: Basic realm="..."` on 401.
- OAuth2 Bearer: `WWW-Authenticate: Bearer ...` per Bearer token standards; may include `error="invalid_token"` or `insufficient_scope` in appropriate cases.
- Form login: typically 302 redirect to `/login` and HTML rather than JSON.
- Session API: depending on contract, may return JSON 401 on expired session, but do not assume browser form login behaves the same way.

When using `oauth2ResourceServer().jwt()`, the framework provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` to support Bearer semantics. **Do not replace them with a fake Basic header** just to share a body format. You may customize the body provided the challenge and HTTP semantics remain intact.

### 8.3. CORS and Error Responses

If a frontend on another origin calls the API via JavaScript, requests may need CORS headers on 401/403 responses as well. A well-formed error body **does not mean the frontend can read it** if CORS policy forbids it.

Configure CORS in Spring Security with a trusted policy source; never set `Access-Control-Allow-Origin: *` with credentials to "fix" auth errors. If `OPTIONS` preflight is blocked, inspect filter order/configuration—do not rush to set `anyRequest().permitAll()`.

### 8.4. CSRF and HTTP Basic

CSRF is a dedicated policy for unsafe methods (`POST`/`PUT`/`PATCH`/`DELETE`). The sample project keeps default CSRF enabled. A `POST` that passes authentication and authorization can still return 403 **for lacking a CSRF token**. Therefore:

- Test positive writes with a valid CSRF token.
- Test missing CSRF receiving 403.
- **Do not claim the CSRF denial body is guaranteed to come from the custom `AccessDeniedHandler`.**
- If an API uses Bearer headers and does not rely on auto-sent browser cookies, evaluate CSRF per threat model; never disable it merely because the API returns JSON.
- To standardize JSON for CSRF, configure and test **`CsrfFilter`'s actual handler** on the version you use.

### 8.5. Proxies and Error Pages

Ingress, API gateways, CDNs, or reverse proxies may generate 401/403/404/5xx themselves. Those bodies **do not pass through Spring Security**. To achieve a uniform response contract end-to-end, inspect every network hop and configure the gateway accordingly. A single Spring bean cannot guarantee the gateway returns `ProblemDetail`.

## 9. Runnable Project: Java 17, Spring Boot 3.3.13, Security 6, ProblemDetail

The complete example below uses **HTTP Basic** and **a single filter chain** for a REST demo. The goal is to build 401/403 `ProblemDetail` responses via the two security handlers while testing public, authenticated, role, wrong password, fallback deny, and CSRF cases.

### 9.1. Directory Structure

~~~text
security-problem-detail/
├── pom.xml
└── src/
    ├── main/java/com/example/securityerrors/
    │   ├── SecurityErrorsApplication.java
    │   ├── SecurityConfig.java
    │   ├── SecurityProblemWriter.java
    │   ├── ProblemAuthenticationEntryPoint.java
    │   ├── ProblemAccessDeniedHandler.java
    │   └── DemoController.java
    └── test/java/com/example/securityerrors/
        └── SecurityErrorResponseTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>security-problem-detail</artifactId>
  <version>1.0.0</version>

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
~~~

### 9.2. Main Application

**`src/main/java/com/example/securityerrors/SecurityErrorsApplication.java`**

~~~java
package com.example.securityerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityErrorsApplication.class, args);
    }
}
~~~

### 9.3. Shared Writer for Both Security Handlers

**`src/main/java/com/example/securityerrors/SecurityProblemWriter.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;

@Component
public class SecurityProblemWriter {

    private final ObjectMapper mapper;

    public SecurityProblemWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(
            HttpServletResponse response,
            HttpStatus status,
            String type,
            String title,
            String detail) throws IOException {

        // An already-committed response cannot safely write a new error.
        if (response.isCommitted()) {
            return;
        }

        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(status, detail);

        problem.setType(URI.create(type));
        problem.setTitle(title);

        response.setStatus(status.value());
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(
            StandardCharsets.UTF_8.name());
        response.setHeader(
            HttpHeaders.CACHE_CONTROL, "no-store");

        mapper.writeValue(response.getOutputStream(), problem);
    }
}
~~~

**Explanation:**

- Spring Boot `spring-boot-starter-web` provides `ObjectMapper` via Jackson auto-configuration unless excluded.
- `ProblemDetail` has standard fields `type`/`title`/`status`/`detail`, serialized by Jackson. The example does not rely on custom extension properties.
- `response.setStatus(...)` matches `ProblemDetail.status`.
- `application/problem+json` clearly distinguishes Problem Details from custom JSON.
- UTF-8 supports Vietnamese text; do not compute `Content-Length` manually from Java `String` length.
- `Cache-Control: no-store` reduces the risk of caching permission-sensitive errors.
- `instance` is not populated from the request URI to avoid accidentally reflecting sensitive paths/queries.
- When the response is already committed, the writer avoids writing again; in production, add safe logging/metrics to detect committed-response cases without exposing raw exceptions to callers.

**The writer does not attach `WWW-Authenticate` itself.** That header is the responsibility of **the entry point for each authentication scheme**. Separating responsibilities lets the writer serve Basic, Bearer, or other error handling without emitting the wrong challenge.

### 9.4. Entry Point Returning 401 While Preserving Basic Challenge

**`src/main/java/com/example/securityerrors/ProblemAuthenticationEntryPoint.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

@Component
public class ProblemAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final SecurityProblemWriter writer;

    public ProblemAuthenticationEntryPoint(
            SecurityProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        if (response.isCommitted()) {
            return;
        }

        // HTTP Basic requires a challenge. For Bearer, use Bearer;
        // DO NOT copy this Basic header to a JWT API.
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"demo-api\"");

        // Do not include exception.getMessage() in public responses.
        writer.write(
            response,
            HttpStatus.UNAUTHORIZED,
            "urn:demo:problem:authentication-required",
            "Authentication required",
            "Authentication is required to access this resource.");
    }
}
~~~

Both missing Basic credentials and invalid Basic credentials must use the same **entry point** to keep the body uniform. Configuring the entry point inside both `httpBasic(...)` and `exceptionHandling(...)` in the next section clarifies this.

Do not return detailed errors like `"User alice not found"` or `"Password expired for account ..."` to callers; that enables user enumeration. For supportable errors, return a safe request correlation ID and keep details inside access-controlled logs.

### 9.5. AccessDeniedHandler Returning 403

**`src/main/java/com/example/securityerrors/ProblemAccessDeniedHandler.java`**

~~~java
package com.example.securityerrors;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class ProblemAccessDeniedHandler
        implements AccessDeniedHandler {

    private final SecurityProblemWriter writer;

    public ProblemAccessDeniedHandler(SecurityProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException {

        writer.write(
            response,
            HttpStatus.FORBIDDEN,
            "urn:demo:problem:access-denied",
            "Access denied",
            "You do not have permission to access this resource.");
    }
}
~~~

`AccessDeniedException` is **not** serialized into the body. The response still provides a machine-readable error code (`type`) and a neutral message. When using 403 to avoid leaking resource details, omit resource titles, owner names, and required role lists.

### 9.6. SecurityConfig Wiring Handlers into Spring Security

**`src/main/java/com/example/securityerrors/SecurityConfig.java`**

~~~java
package com.example.securityerrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ProblemAuthenticationEntryPoint entryPoint,
            ProblemAccessDeniedHandler deniedHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(entryPoint))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            // CSRF is not disabled; POST requests require a token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoded)
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Points to read carefully:**

1. `/api/public` is `permitAll`, yet still traverses the security filter chain. It requires no `Authentication`.
2. `/api/admin` requires `ROLE_ADMIN`. User `alice` with `ROLE_USER` receives 403.
3. `/api/profile` requires `authenticated`. Anonymous receives 401 and a Basic challenge.
4. `/api/notes` uses POST; by default Spring Security CSRF protects unsafe methods. Test with and without a CSRF token separately.
5. `anyRequest().denyAll()` blocks requests outside explicit policies, even for an authenticated `ADMIN`.
6. `httpBasic(...authenticationEntryPoint(entryPoint))` ensures the invalid Basic credentials error path uses the demo's writer.
7. `exceptionHandling(...authenticationEntryPoint(entryPoint))` ensures unauthenticated protected requests routed by `ExceptionTranslationFilter` use the same entry point.
8. `accessDeniedHandler(deniedHandler)` handles authorization denials within `ExceptionTranslationFilter`'s scope, **without claiming to catch every 403 from CSRF/container**.
9. Never use `web.ignoring()` or `anyRequest().permitAll()` as a fix for JSON error formatting, as that accidentally drops authorization.

### 9.7. Minimal Controller

**`src/main/java/com/example/securityerrors/DemoController.java`**

~~~java
package com.example.securityerrors;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }

    @PostMapping("/api/notes")
    public Map<String, String> createNote() {
        return Map.of("status", "created");
    }
}
~~~

The controller does not handle security exceptions directly. Spring Security blocks unauthorized/forbidden requests before they reach the controller. In practice, resource-level permissions and ownership must also be checked at the service/method layer; an authenticated user does not automatically have permission on every record.

### 9.8. MockMvc Integration Tests Checking Body, Headers, and HTTP Semantics

**`src/test/java/com/example/securityerrors/SecurityErrorResponseTests.java`**

~~~java
package com.example.securityerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityErrorResponseTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void missingCredentialsGet401ProblemAndBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401))
            .andExpect(jsonPath("$.title")
                .value("Authentication required"))
            .andExpect(jsonPath("$.type")
                .value("urn:demo:problem:authentication-required"));
    }

    @Test
    void invalidBasicCredentialsUseSame401Contract()
            throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403Problem()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.title").value("Access denied"))
            .andExpect(jsonPath("$.type")
                .value("urn:demo:problem:access-denied"));
    }

    @Test
    void authenticatedUserMayAccessOwnAllowedRoute()
            throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }

    @Test
    void fallbackDeniedEvenForAdminGets403Problem()
            throws Exception {
        mvc.perform(get("/not-listed")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(403));
    }

    @Test
    void csrfIsIndependentOfAuthorizationErrorWriter()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Valid token lets the request pass through the CSRF filter.
        mvc.perform(post("/api/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("created"));
    }
}
~~~

**Why is this exact test suite needed?**

- Anonymous `GET /api/profile`: tests the `ExceptionTranslationFilter` path and 401 response.
- Wrong Basic password: tests the `BasicAuthenticationFilter` error path so you do not forget to configure the entry point on `httpBasic`.
- Regular user hitting admin: tests `AccessDeniedHandler` returning the 403 `ProblemDetail` body.
- Admin hitting an unlisted endpoint: tests fallback deny—being `ADMIN` does not bypass missing rules.
- Checks that `status` inside the body **matches the HTTP status**.
- Checks `Content-Type: application/problem+json` instead of `text/html` or custom JSON with the wrong media type.
- Checks `WWW-Authenticate` is present on HTTP Basic 401.
- Checks missing CSRF gets 403 **without asserting its body is produced by the denied handler**.
- Checks a request with a valid CSRF token still reaches the controller.
- Uses `httpBasic(...)` from `spring-security-test` to send real Basic credentials through the filter chain instead of bypassing with `@WithMockUser`.

If your organization uses browsers/SPAs, in addition to MockMvc you need **end-to-end tests with a browser** to verify CORS, cookies, redirects, and credential handling. MockMvc does not simulate every browser or reverse-proxy behavior.

### 9.9. Running the Project and Observing

Install **JDK 17+**, Maven, ensure dependency downloads work, and create the files at the paths in Section 9.1:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Expected result:** the test suite passes and Maven prints `BUILD SUCCESS` in a compatible setup/environment. The code was described and statically checked in this lesson; **no claim is made that Maven was executed live**.

In another terminal:

~~~bash
curl -i http://localhost:8080/api/public
# Expected 200 OK, body {"status":"public-ok"}

curl -i http://localhost:8080/api/profile
# Expected 401, WWW-Authenticate: Basic realm="demo-api"
# Content-Type: application/problem+json, status=401

curl -i -u alice:wrong-password \
  http://localhost:8080/api/profile
# Expected 401 ProblemDetail, Basic challenge

curl -i -u alice:demo-pass \
  http://localhost:8080/api/profile
# Expected 200 OK, body {"username":"alice"}

curl -i -u alice:demo-pass \
  http://localhost:8080/api/admin
# Expected 403, ProblemDetail type access-denied

curl -i -u admin:demo-pass \
  http://localhost:8080/api/admin
# Expected 200 OK, body {"status":"admin-ok"}

curl -i -u admin:demo-pass \
  http://localhost:8080/not-listed
# Expected 403, ProblemDetail from fallback denyAll

curl -i -u alice:demo-pass -X POST \
  http://localhost:8080/api/notes
# Expected 403 due to missing CSRF token (body may differ)
~~~

On Windows PowerShell, use `curl.exe` if `curl` is aliased to another cmdlet. **Only test HTTP Basic on localhost with demo credentials.** Basic credentials are Base64-encoded, **not encrypted by Base64**; production must use HTTPS and real authentication policies.

## 10. Custom JSON Alternative Instead of ProblemDetail

If an API already has a contract like:

~~~json
{
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Authentication is required.",
    "status": 401
  }
}
~~~

you can swap the writer that builds `ProblemDetail` for a custom DTO. The critical part **remains unchanged**: `EntryPoint`/`DeniedHandler` must keep the HTTP status and headers accurate; only the body and `Content-Type` differ.

Example of a clean DTO:

~~~java
public record ApiError(
    String code,
    String message,
    int status
) {
}
~~~

Place this snippet in `ApiError.java` if choosing the custom JSON approach. Response:

~~~java
response.setStatus(HttpStatus.UNAUTHORIZED.value());
response.setContentType(MediaType.APPLICATION_JSON_VALUE);
response.setCharacterEncoding(StandardCharsets.UTF_8.name());

ApiError error = new ApiError(
    "AUTHENTICATION_REQUIRED",
    "Authentication is required.",
    HttpStatus.UNAUTHORIZED.value()
);

mapper.writeValue(response.getOutputStream(), error);
~~~

This snippet sits inside a writer where `response`, `mapper`, and proper imports already exist; it **does not replace the whole Section 9 project** unless you intentionally choose custom JSON. If you want the nested `{"error": {...}}` structure from the earlier example, you need a wrapper DTO—do not use a flat `ApiError` and claim the JSON is nested.

An API should choose **one** public schema for its error contract, define versioning, and test it. When migrating from legacy JSON to `ProblemDetail`, clients reading `$.error.code` instead of `$.type` can break; support migration or versioning rather than changing silently.

## 11. Localization, Request ID, and Observability

### 11.1. Prefer Stable Error Codes Over Natural-Language Messages

`title`/`detail` can be translated into Vietnamese/English based on `Accept-Language` if the product requires it, but the **type URI or code** should stay stable so clients never depend on translated text.

Example 403:

~~~json
{
  "type": "urn:demo:problem:access-denied",
  "title": "Không có quyền truy cập",
  "status": 403,
  "detail": "Bạn không có quyền thực hiện thao tác này."
}
~~~

When localizing, evaluate response `Content-Language`, cache policy, fallback locale, and frontend responsibilities; never expose internal authentication provider messages just to provide user-facing detail.

### 11.2. Safe Correlation IDs

When incident support is needed, you can return a controlled `requestId` or `traceId` extension. The goal is to let support look up internal logs without exposing exceptions.

- Generate the ID at a trusted gateway/server, or strictly validate client-supplied IDs.
- Never embed tokens, passwords, session IDs, or full request bodies in the ID.
- Never return raw stack traces, database queries, or internal system names.
- Align the ID with distributed tracing/logging where available.
- Restrict log read access and retention.

Without tracing infrastructure, it is better to **omit the extension** than to return a random ID the system cannot look up.

### 11.3. Metrics Worth Monitoring

- 401 rate by endpoint/API client and grouped cause (without recording passwords).
- 403 rate by chosen route/policy.
- Requests with CORS preflight failures.
- CSRF errors if the app uses cookies/sessions.
- Count of responses already committed before the error handler wrote the body.
- 5xx / gateway error rate, separated from 4xx.
- Anomalous spikes in 401 on login/resources, backed by appropriate rate limiting.

**Do not put unsanitized usernames/emails into high-cardinality metric labels** or leak data. Use stable tags such as route template, status, and error type.

## 12. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only `@RestControllerAdvice` for filter errors | 401/403 bypasses advice | Configure `AuthenticationEntryPoint`, `AccessDeniedHandler` |
| Returning 200 with JSON `status=401` | Clients/caches mistake it for success | HTTP status and `body.status` must match |
| Returning 401 without `WWW-Authenticate` on Basic | Violates HTTP Basic semantics | Keep the Basic challenge |
| Copying Basic challenge onto a JWT Bearer API | OAuth2 clients misinterpret it | Use scheme-appropriate Bearer entry point/handler |
| Putting `authException.getMessage()` in the body | Leaks auth/username/internal info | Use a fixed safe message |
| `response.sendError(403)` then writing JSON | Container error dispatch or double-write | `setStatus` + serialize once |
| Building JSON via string concatenation | Escaping/Unicode bugs, injection risk | Use `ObjectMapper`/serializer |
| Registering 403 handler and assuming it catches CSRF 403 | CSRF filter uses another handler | Test and configure CSRF explicitly if needed |
| Disabling CSRF just because API returns JSON | Risk for cookie-based auth | Evaluate by credentials/threat model |
| Setting `anyRequest().permitAll()` to avoid 403 | Exposes sensitive endpoints | Keep fallback deny and declare proper rules |
| Putting path/query into `instance` regardless of privacy | Reflects tokens/resource IDs | Keep `instance` safe or omit it |
| Always returning full stack traces to frontend | Exposes implementation details | Keep in restricted logs; neutral response |
| Using `application/json` while claiming `ProblemDetail` | Non-standard media contract | Use `application/problem+json` |
| Changing `type`/error code per language | Clients forced to parse messages | Keep `type`/code stable |
| Not testing wrong passwords | `BasicFilter` may use another entry point | Test both missing and invalid credentials |
| Not testing frontend over CORS | Browser cannot read the body | E2E test CORS and credentials |
| Thinking Spring handlers control gateway errors | Gateway generates responses outside app | Configure contract at the gateway |
| Not checking `response.isCommitted()` | Handler writes error a second time | Check committed, log and investigate flow |
| Using one JSON entry point for all web form pages | Breaks redirects/login UX | Split chains or delegate entry points |

## 13. Pre-Production Error Contract Testing Checklist

1. **Unauthenticated GET** to a protected endpoint → HTTP 401 with the right auth scheme; leaks no credentials.
2. **Bad credentials** → same schema as missing credentials; does not distinguish user existence.
3. **Authenticated missing role** → HTTP 403; body leaks no roles, users, or tenants of other resources.
4. **Authenticated with permission** → normal 200/201; error writer does not interfere.
5. **Fallback deny** for unlisted routes → does not automatically allow `ADMIN` past missing rules.
6. **Missing/invalid CSRF token** → rejected per policy; verify actual body of the corresponding handler instead of assuming.
7. **CORS preflight and cross-origin error responses** → frontend can read status/body when origin is allowed.
8. **Cache headers** and security headers are not stripped during error handling.
9. **Parseable JSON body**, valid UTF-8, right `Content-Type`, no double-write.
10. **HTTP status matches `ProblemDetail.status`** and `type` is stable.
11. **No logging/serializing raw exceptions** or tokens into responses.
12. **Test form login and Bearer separately** when supporting multiple auth schemes, especially `WWW-Authenticate`.
13. **Verify Method Security** with `@PreAuthorize`/`@PostAuthorize` and object-level errors.
14. **Verify error dispatch** for `/error`, servlet filters, and proxies.
15. **Verify expired sessions**, disabled/locked accounts per authentication provider, and refresh-token failures if applicable.
16. **Verify gateway/CDN 4xx/5xx** outside Spring Security.
17. **Frontend/mobile contract tests** rely on `code`/`type` rather than parsing messages.
18. **Load/security tests** ensure error storms cannot overwhelm logs or storage.

## 14. Self-Check Questions

**Question 1.** Why is `@RestControllerAdvice` insufficient to standardize all 401/403 responses?

**Answer:** Security filters can reject requests before reaching Spring MVC. Handle them in `AuthenticationEntryPoint`/`AccessDeniedHandler` or the corresponding filter handling point.

**Question 2.** When should you return 401 vs. 403?

**Answer:** 401 when valid authentication is required per the API flow; 403 when authenticated yet missing permissions or blocked by another policy. Actual status also depends on the auth scheme/filter—do not assume every denial is 403.

**Question 3.** Why does HTTP Basic 401 need `WWW-Authenticate`?

**Answer:** To issue a challenge specifying the Basic scheme/realm to the client, conforming to HTTP authentication semantics.

**Question 4.** Should a Basic challenge be returned when the API uses JWT Bearer?

**Answer:** No. Emit a Bearer challenge per the corresponding resource server/OAuth2 mechanism.

**Question 5.** What `Content-Type` does `ProblemDetail` use?

**Answer:** `application/problem+json` with a JSON representation per RFC 9457.

**Question 6.** What are the standard fields of `ProblemDetail`?

**Answer:** `type`, `title`, `status`, `detail`, `instance`; some are optional, and well-designed extensions may be added.

**Question 7.** Should `type` or `detail` be used as the stable error code?

**Answer:** `type` (or a stable extension code) is more suitable. `detail` is a description that can change or be localized.

**Question 8.** Why not use `authException.getMessage()` as the response `detail`?

**Answer:** It can leak username existence, tokens, password policies, internal metadata, or provider details. Use reviewed public messages.

**Question 9.** Is a custom `AccessDeniedHandler` guaranteed to format every CSRF 403?

**Answer:** No. `CsrfFilter` may use a different handler; test and configure the CSRF handling point itself if you want the same schema.

**Question 10.** In the example, where does a wrong Basic password go?

**Answer:** Through the HTTP Basic authentication filter using the entry point configured under `httpBasic(...)`. Hence wrong passwords must be tested in addition to missing credentials.

**Question 11.** Why prefer `setStatus` over `sendError` when writing JSON yourself?

**Answer:** `sendError` can trigger a servlet error page/dispatch, leading to HTML or double-writes. When serializing intentionally, set the status and write the body once.

**Question 12.** Is HTTP 200 with body `{"status":403}` reasonable?

**Answer:** No for normal HTTP error reporting. The real status must reflect failure so clients, monitors, and caches behave accurately.

**Question 13.** Is an error response without `instance` non-compliant?

**Answer:** No. `instance` is optional; if URLs could expose sensitive information, omitting it can be safer.

**Question 14.** Why might a 403 from a gateway differ from the body in Spring Security?

**Answer:** The gateway builds the response before the request reaches the Spring app, so the application's handlers never run.

**Question 15.** Can both custom JSON and `ProblemDetail` coexist in the same system?

**Answer:** Yes, across well-defined API versions, client types, or endpoints; never silently break schemas that existing clients depend on.

**Question 16.** When form login is designed for browsers, what do anonymous visitors typically receive?

**Answer:** They may receive a 302 redirect to the login page instead of 401 JSON; preserve the right UX per flow rather than forcing every endpoint into one response.

**Question 17.** Why does role-based authorization not replace per-resource permission checks?

**Answer:** A user with `ROLE_USER` still must not view another user's or tenant's documents. Service/method policies must check owner/tenant/permissions explicitly.

**Question 18.** How do you verify a writer does not break security error behavior?

**Answer:** Test HTTP status, content type, body fields, 401 challenges, 403 permission denials, missing/invalid credentials, CSRF, CORS, fallback deny, and committed-response cases against the real system.

**Remember:** **Errors from Spring Security Servlet do not pass through MVC advice automatically. Use `AuthenticationEntryPoint` for login-initiation flows and `AccessDeniedHandler` for access denials within its scope; preserve accurate HTTP statuses and `WWW-Authenticate`, design stable JSON/`ProblemDetail` payloads, avoid information disclosure, and verify CSRF/Bearer/gateway as distinct error paths.**