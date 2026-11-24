# AccessDeniedHandler When Identity Lacks Access Permissions — Spring Security Servlet

## 1. The Problem: The Caller's Identity Is Known, Yet Access Is Still Not Permitted

An API typically protects resources using rules such as `hasRole("ADMIN")`, `hasAuthority("reports:read")`, or a document-ownership policy in `@PreAuthorize`. A user can **log in successfully**, yet lack permission to perform a specific operation. In Spring Security Servlet, this is an **authorization denied** scenario and is normally answered with HTTP **403 Forbidden**.

Example:

```text
alice logged in with ROLE_USER
    |
GET /api/admin/reports
    |
Valid authentication: alice / ROLE_USER
    |
Rule requires ROLE_ADMIN
    |
AccessDeniedException
    |
ExceptionTranslationFilter -> AccessDeniedHandler
    |
403 Forbidden
```

The UI or API must return a **safe, consistent, and useful** response. Beyond blocking access, it must avoid leaking internal information and help the client understand that changing passwords or logging in again will not necessarily resolve a **missing permission** issue.

In Spring Security Servlet, the dedicated contract for this scenario is the `AccessDeniedHandler` interface. It differs from `AuthenticationEntryPoint`, which is responsible for initiating the authentication process when the caller does not yet have the required authentication level.

This lesson belongs to the **Error Responses** group and focuses squarely on the topic: **AccessDeniedHandler when identity lacks access permissions**. It explains the filter chain, invocation conditions, differences between 401 and 403, modern configuration with `SecurityFilterChain`, JSON APIs, HTML pages, MockMvc testing, and common implementation mistakes.

The scope is **Spring Security Servlet / Spring MVC**, commonly found in Spring Security 6.x, Java 17+. Examples use **Spring Boot 3.3.5** as a consistent learning baseline, **without claiming it is the latest or still under support** at the time of reading. For real projects, cross-check APIs and choose a version with appropriate security updates.

## 2. Distinguish Authentication and Authorization Before Writing a Handler

**Authentication** identifies who the caller is. For example, `BasicAuthenticationFilter` receives HTTP Basic credentials; `UsernamePasswordAuthenticationFilter` verifies form login; a resource server validates a Bearer token. If authentication succeeds, the framework places an `Authentication` object into `SecurityContextHolder` for the request according to the corresponding mechanism.

**Authorization** decides which URLs or methods/business operations that caller is allowed to invoke. Example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

This is an `HttpSecurity` configuration fragment, not a standalone Java file. For user `alice` who has `ROLE_USER` but lacks `ROLE_ADMIN`, `GET /api/admin/reports` is denied by authorization. At this point, if the authentication is deemed sufficiently trustworthy to distinguish the identity, `AccessDeniedHandler` is where 403 is returned.

Conversely, if the request **has no authentication yet**, or has authentication too weak for the requirement, Spring Security may restart the login flow via `AuthenticationEntryPoint`. Therefore, **never state that every `AccessDeniedException` is guaranteed to invoke `AccessDeniedHandler`**: the choice also depends on anonymous/remember-me state and how the framework classifies authentication.

| Scenario | Key point | Typical response |
|---|---|---|
| No credentials, URL requires login | Not yet authenticated | `AuthenticationEntryPoint` → 401 Basic challenge or form login redirect |
| Wrong credentials / invalid token | Authentication failed | Authentication filter/entry point → typically 401 |
| Authenticated, missing `ROLE_ADMIN` | Authorization denied | `AccessDeniedHandler` → typically 403 |
| Logged in via remember-me, endpoint requires `fullyAuthenticated()` | Insufficient authentication level | May re-commence authentication instead of normal 403 |
| Authenticated, missing permission per `@PreAuthorize` | Method security denied | Typically 403 via exception translation, if exception propagates through the proper chain |
| POST missing CSRF token | CSRF protection rejects request | Typically 403, though **custom handler in `exceptionHandling` is not guaranteed to be called by default** |
| Controller throws business error itself | MVC handles exception per app architecture | Not every error goes through `AccessDeniedHandler` |

**401 does not mean "the user is logged in but lacks permissions."** For HTTP Basic and Bearer, 401 normally indicates authentication is needed or failed. **403 normally indicates the current identity is not permitted for the specific action.** Form login may use redirects instead of 401; status rules should be designed according to client and authentication mechanism.

## 3. Where Does AccessDeniedHandler Sit in SecurityFilterChain?

Spring Security Servlet uses `FilterChainProxy` to execute a `SecurityFilterChain` matching the request. Different filters handle loading the security context, authentication, CSRF, exception handling, and authorization.

Simplified flow for a request missing a role:

```text
GET /api/reports/42
   |
Servlet FilterChain -> FilterChainProxy
   |
SecurityContext / Authentication filters
   |
ExceptionTranslationFilter
   |  try {
   |      downstream filters
   |        |
   |        +-- AuthorizationFilter
   |               |
   |               +-- hasRole('ADMIN') = false
   |               +-- AccessDeniedException
   |  } catch (AccessDeniedException) {
   |      check authentication state
   |      if authentication needed -> AuthenticationEntryPoint
   |      if authenticated but lacking permission -> AccessDeniedHandler
   |  }
   |
HTTP 403 and body/redirect/forward depending on handler
```

**`ExceptionTranslationFilter` is not the authorization engine.** It translates certain security exceptions (such as `AuthenticationException` or `AccessDeniedException`) from downstream into an HTTP response or authentication initiation. Depending on the request, it may clear the `SecurityContext`, save the request to resume after login, or invoke the authentication entry point. For a fully authenticated user lacking permission, it delegates to `AccessDeniedHandler`.

### The AccessDeniedHandler Interface

Core contract:

```java
public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
```

This is an illustrative signature matching the Servlet API on Spring Security 6 / Jakarta Servlet. When implementing a real class, import the interface from `org.springframework.security.web.access.AccessDeniedHandler`, the exception from `org.springframework.security.access.AccessDeniedException`, and Servlet classes from `jakarta.servlet.*`.

Three parameters:

- `request` contains method, URI, attributes, security context, and required request metadata.
- `response` lets you set the status code, content type, headers, body, or forward/redirect.
- `accessDeniedException` describes the denial event. **The exception message may contain framework/policy details; do not send raw `getMessage()` to clients in production.**

The handler is a **response boundary**, not a place to modify permissions. It should not grant `ROLE_ADMIN`, clear `SecurityContext` to "let the request through", or re-run the controller under a different identity. Which permissions a user holds must be decided earlier at the authorization layer.

## 4. Default AccessDeniedHandler and Response Options

### 4.1. AccessDeniedHandlerImpl

Spring Security provides `AccessDeniedHandlerImpl`. Depending on configuration, it can send status `403` or forward to a defined error page.

Example using an error page path:

```java
http.exceptionHandling(ex -> ex
    .accessDeniedPage("/access-denied"));
```

This is a configuration snippet, not a complete application. When internally forwarding to an error page, the request remains within the same server-side processing; **do not treat a forward as a new browser redirect**. Ensure the error page endpoint has proper mapping and security policy to avoid loops or being blocked right during the forward.

Design points for HTML web pages:

- The notice page should use user-friendly wording, such as "You do not have permission to perform this action".
- Do not expose internal permission names, object IDs of other tenants, or sensitive details from the exception.
- Do not add a `permitAll("/**")` rule just to make the error page render.
- If displaying user-supplied paths or parameters, encode output to prevent XSS.
- Test `FORWARD`/`ERROR` dispatcher types as well if your system uses them and Spring Security filter mapping applies.
- Do not use a single error page to serve JSON API requirements; HTML and REST clients have different response contracts.

### 4.2. HttpStatusAccessDeniedHandler

Some APIs only need status 403 with no body; `HttpStatusAccessDeniedHandler` or a custom handler can be used where appropriate for the version. For internal APIs with dedicated clients, a machine-readable body is more convenient.

The advantage of a status-only response is minimal information disclosure. The drawback is that clients struggle to distinguish missing-permission errors from other 403 errors without a clear response contract.

### 4.3. Custom JSON AccessDeniedHandler

REST APIs typically want a response like:

```json
{
  "status": 403,
  "code": "ACCESS_DENIED",
  "message": "You do not have permission to access this resource",
  "path": "/api/reports/42"
}
```

The sample payload intentionally omits passwords, session IDs, bearer tokens, raw authorities, stack traces, and exception classes. `path` is only the URI path and can still be sensitive: if URLs embed identifying data, strip it or replace it with a safe template per policy.

Implementation decisions:

1. Set the actual **status 403**—never return HTTP 200 with `"status":403` in the body.
2. Set `Content-Type: application/json` and UTF-8 encoding, using Jackson/`ObjectMapper` to serialize properly.
3. Set `Cache-Control: no-store` for sensitive error responses when appropriate.
4. Return a **stable error code** for clients; do not expose verbatim framework messages externally.
5. Do not call `response.sendRedirect("/login")` for a logged-in user lacking permissions if the API contract expects 403.
6. Do not write a body if the response is already committed, because headers/status cannot be changed reliably once bytes have been sent.
7. If logging/auditing, record minimal normalized identity info and a correlation ID; never log raw `Authorization`/`Cookie` headers.

**Security does not come from how pretty the JSON is.** The handler only makes the response consistent; the authorization policy before it must still be sound.

## 5. AuthenticationEntryPoint Differs from AccessDeniedHandler

These two extension points often sit side by side in `exceptionHandling`:

```java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customAccessDeniedHandler));
```

This is a code fragment; `customEntryPoint` and `customAccessDeniedHandler` must be defined beans/objects, not pre-existing variables.

- `AuthenticationEntryPoint` initiates authentication for a caller who lacks an adequate authentication level. For a Basic API, an example is 401 with `WWW-Authenticate`. For a web form, it may redirect to login.
- `AccessDeniedHandler` handles cases where the user has valid authentication yet lacks authorization. Typically it returns 403.

**Do not use a custom `AccessDeniedHandler` to "unify" all auth errors into 403**, because 401 remains vital for client authentication protocols. If you want both 401 and 403 to return JSON, create **two** separate components and preserve the semantics of each authentication mechanism.

### Anonymous and Remember-Me Are Two Special Cases

On a URL requiring `authenticated()`, anonymous authentication does not count as a valid user. If authorization denies the request, `ExceptionTranslationFilter` may detect anonymous status and invoke `AuthenticationEntryPoint`.

With `RememberMeAuthenticationToken`, `fullyAuthenticated()` demands a higher authentication level than remember-me; the framework may initiate a re-authentication flow. Therefore, do not write rigid tests asserting "every `AccessDeniedException` always receives JSON 403 from the custom handler" while ignoring the actual `Authentication` type.

### Password Changes and Role Updates

If a user is already logged in and their role is later downgraded in the database, the `Authentication` inside a server-side session may still hold stale authorities. `AccessDeniedHandler` **does not re-check roles in the database**; it only responds once the authorization engine denies access. For role reductions to take effect on existing sessions, add session revocation, security versions, or per-request permission revalidation. Do not expect changing a 403 message to close a stale-authorities gap.

## 6. @PreAuthorize Can Also Lead to AccessDeniedHandler

At the service layer:

```java
@PreAuthorize("hasRole('ADMIN')")
public String sensitiveReport() {
    return "SENSITIVE";
}
```

If `@EnableMethodSecurity` is active, the method is called **through a Spring-managed proxy**, and an authenticated user lacking `ROLE_ADMIN` calls the method, the method-security interceptor can throw `AccessDeniedException` (or an appropriate subtype).

When that exception **propagates out of MVC/controller** along the HTTP call stack, `ExceptionTranslationFilter` in the filter chain can handle it with `AccessDeniedHandler`. This is a different path from `AuthorizationFilter` denying a URL. The runnable example includes dedicated tests verifying both.

**Technical note:** if `@ControllerAdvice` or a custom exception resolver catches `AccessDeniedException` inside MVC and writes a response first, the exception may no longer reach security exception translation. This is not necessarily wrong if designed deliberately, but you must ensure 401/403 responses stay consistent and do not mask policy.

If a method security check is bypassed due to self-invocation, `AccessDeniedHandler` never gets a chance to run because no exception is thrown. Thus you must test that the annotation is actually enforced; the handler cannot fix missing enforcement.

## 7. CSRF Can Return 403 Without Passing Through the Handler Configured in exceptionHandling

This is a very easy trap to misread.

A `POST /api/reports` request from an Editor with the right role can still be rejected by **`CsrfFilter`** due to a missing CSRF token. The status is also typically **403**, yet that **does not prove** the custom `AccessDeniedHandler` in `http.exceptionHandling(...)` was called.

Reason: the position of `CsrfFilter` in the chain and CSRF error handling may **use a separate AccessDenied handling path**, instead of always throwing the exception down to `ExceptionTranslationFilter`. Exact hooks depend on version/configuration; do not assume the generic handler's JSON response is a guaranteed contract for every CSRF failure.

When testing roles on `POST`/`PUT`/`PATCH`/`DELETE`, supply a valid CSRF token if CSRF is enabled. Only then can a 403 be clearly attributed to role/service authorization.

MockMvc example:

```java
mvc.perform(post("/api/reports")
        .with(httpBasic("reader", "reader-pass"))
        .with(csrf())
        .contentType(MediaType.TEXT_PLAIN)
        .content("Quarterly"))
    .andExpect(status().isForbidden());
```

This snippet belongs inside a test with `mvc` and full imports already present. `with(csrf())` eliminates missing-token CSRF as the cause in the request above, so Reader's failure is attributable to lacking POST permissions. In another test that intentionally omits CSRF, assert only status/behavior per CSRF policy—**do not assert that the custom handler's JSON payload always matches the authorization case**.

If an API uses a Bearer `Authorization` header that browsers do not attach automatically, CSRF policy may differ; nevertheless, never disable CSRF globally just to make every test pass. For form/cookie/Basic in browsers, analyze all automatically sent credential mechanisms thoroughly.

## 8. Bearer/JWT APIs: Do Not Accidentally Break WWW-Authenticate

An OAuth 2.0 resource server API using Bearer tokens has its own challenge semantics:

- Missing, invalid, or expired tokens typically cause authentication failure, 401, and a `WWW-Authenticate: Bearer ...` header per the appropriate contract.
- Valid tokens lacking a scope can cause 403 with appropriate Bearer-specific header/metadata, such as `insufficient_scope`, depending on scenario and configuration.
- Spring Security provides `BearerTokenAccessDeniedHandler` for this use case.

If you override every `AccessDeniedHandler` with plain JSON and **omit the required `WWW-Authenticate` header**, OAuth clients may no longer understand the error per protocol. Consider delegating to the Bearer handler / preserving headers and then adding an appropriate body, or separating `SecurityFilterChain` beans by client type.

**The main example** uses HTTP Basic, not OAuth2 Resource Server; therefore, do not assume the demo's custom JSON handler is production-ready for bearer-protected APIs. Depending on framework version, verify `BearerTokenAccessDeniedHandler` APIs and available-scope details against official documentation.

## 9. Choosing Status and Level of Detail in Denial Errors

For object-level permissions, whether a request returns 403 or 404 can be a decision about **leaking resource existence**. For example, a document belonging to another tenant: returning 403 can reveal that a valid ID exists.

Possible design:

- For administrative routes where a logged-in user lacks the role: return 403 with code `ACCESS_DENIED`.
- For a resource not belonging to the caller's tenant: scope the query by tenant, and when not found return 404 per policy to avoid distinguishing "does not exist" from "not visible".
- For a resource locked by business rules, consider `409 Conflict` or `423 Locked` only when it genuinely carries the right semantics and leaks no information.
- For an unauthenticated account, return 401/redirect per `AuthenticationEntryPoint` and login policy.

**`AccessDeniedHandler` should not blindly turn every 403 into 404.** Decisions about hiding resource existence belong at the resource/tenant policy layer; a generic handler lacks the context to know which resources should be hidden. Tests should cover cross-tenant users and non-existent resources, not merely ADMIN vs. USER roles.

### Never Expose Raw Exceptions in the Response

Wrong:

```java
// Not recommended for production:
response.getWriter().write(ex.getMessage());
```

Messages can expose class names, permission expressions, account details, or wording that varies across framework versions. Use a stable error code, a friendly message, and if needed an unpredictable correlation ID. Server-side logs should also never print raw credentials, cookies, session IDs, or bearer tokens.

### Status Code Matters More Than a Faked Body

Never return:

```json
{"status":403,"message":"denied"}
```

with HTTP status 200. Clients, HTTP caches, monitoring, and response policies all rely on the real status code; a body cannot substitute for HTTP status.

## 10. Runnable Sample Project: Spring Boot 3.3.5, Java 17, Maven

This self-contained example features:

- HTTP Basic with accounts `reader`, `editor`, `admin`.
- `GET /api/reports/{id}` restricted to `ROLE_ADMIN`.
- `POST /api/reports` for `EDITOR` or `ADMIN`, requiring CSRF.
- `GET /api/service-report` requiring only `authenticated` at HTTP level, but checked for `ROLE_ADMIN` at the service via `@PreAuthorize`.
- `GET /public` public.
- Undeclared URLs blocked with `denyAll()`.
- `JsonAccessDeniedHandler` returning shared JSON 403 for authorization denials traversing `ExceptionTranslationFilter`.

The demo intentionally modifies no real data, has no database, and is not a production project. Hardcoded passwords are only for local testing—**never deploy them to public environments**. HTTPS is mandatory for using Basic credentials safely over a network.

### 10.1. Directory Structure

```text
access-denied-demo/
├── pom.xml
└── src/
    ├── main/java/example/accessdenied/
    │   ├── AccessDeniedApplication.java
    │   ├── SecurityConfig.java
    │   ├── JsonAccessDeniedHandler.java
    │   ├── ReportService.java
    │   └── ReportController.java
    └── test/java/example/accessdenied/
        └── AccessDeniedFlowTest.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>access-denied-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
```

Do not add individual versions to Spring Security dependencies when the Spring Boot BOM manages them, to avoid mixing incompatible versions.

### 10.3. Entry Point

File `src/main/java/example/accessdenied/AccessDeniedApplication.java`:

```java
package example.accessdenied;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessDeniedApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessDeniedApplication.class, args);
    }
}
```

### 10.4. JsonAccessDeniedHandler

File `src/main/java/example/accessdenied/JsonAccessDeniedHandler.java`:

```java
package example.accessdenied;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class JsonAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper mapper;

    public JsonAccessDeniedHandler(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       AccessDeniedException denied) throws IOException {
        // If the response has already sent headers/body, status cannot be reliably changed.
        if (response.isCommitted()) {
            return;
        }

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", HttpServletResponse.SC_FORBIDDEN);
        body.put("code", "ACCESS_DENIED");
        body.put("message", "You do not have permission to access this resource");
        body.put("path", request.getRequestURI());

        mapper.writeValue(response.getWriter(), body);
    }
}
```

**Why use Jackson?** `ObjectMapper` properly serializes Unicode characters (such as Vietnamese) and escapes JSON strings supplied by the request, avoiding manual concatenation like `"\"" + path + "\""`. The demo body intentionally omits query strings. Production systems may drop `path` when URLs contain sensitive data, replacing it with an error ID and trace correlation.

**Why not use `sendError(403)`?** `sendError` gives the container an opportunity to dispatch to a default error page; if you want exact control over the JSON body, you can use `setStatus` and write JSON directly. Using `sendError` is not wrong, but its interaction with the container/error page must be understood clearly. The handler in this example writes the body once and does not forward or redirect.

**Why not re-throw `AccessDeniedException` inside the handler?** The handler is where exceptions are converted into responses. Re-throwing unintentionally can produce a 500 or be re-processed at another layer. For an actual `IOException`, log and handle it per general policy rather than returning a fake-success JSON response.

**Committed response:** when an error is thrown after a response has begun streaming, you cannot safely convert a committed response into a new HTTP 403. Design stream/async error handling separately and log safely. The guard in the example only avoids writing invalid status/body—it does not mean the request was fully controlled.

### 10.5. SecurityConfig — Configuring Both Method and HTTP Security

File `src/main/java/example/accessdenied/SecurityConfig.java`:

```java
package example.accessdenied;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    JsonAccessDeniedHandler jsonDenied(ObjectMapper mapper) {
        return new JsonAccessDeniedHandler(mapper);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http, JsonAccessDeniedHandler deniedHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/service-report")
                    .authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler(deniedHandler))
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Meaning:

- `@EnableMethodSecurity` ensures `@PreAuthorize` on `ReportService` is enforced via a Spring proxy.
- `httpBasic()` is the authentication mechanism. Missing/wrong HTTP Basic credentials normally generate a **401 challenge** via the entry point; a custom `AccessDeniedHandler` **does not alter** that behavior.
- `GET /api/reports/{id}` is `ADMIN`-only in HTTP authorization. Logged-in `reader` is denied and receives JSON 403.
- `POST /api/reports` allows `EDITOR` or `ADMIN`. CSRF remains enabled; a `POST` with the right role but missing CSRF can be blocked by the CSRF filter.
- `GET /api/service-report` only requires `authenticated` at the HTTP layer, while the service method requires `ADMIN`, verifying that method-security denials are handled too.
- `anyRequest().denyAll()` prevents undeclared paths/methods from being allowed by default. Real resources also require authorization at the object/tenant layer.

**Important:** the configuration does not disable CSRF. It intentionally allows a test to prove that a 403 response from CSRF can differ from the JSON produced by `exceptionHandling`. Never use "the handler was not called on the CSRF case" as an excuse to disable CSRF.

### 10.6. Service with @PreAuthorize

File `src/main/java/example/accessdenied/ReportService.java`:

```java
package example.accessdenied;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String sensitive() {
        return "SERVICE_REPORT";
    }
}
```

Method security throws an exception before running the method if the caller lacks `ROLE_ADMIN`. If the annotation is omitted or the call bypasses the Spring proxy, the `reader` test on `/api/service-report` will catch the missing policy.

### 10.7. Simple Controller

File `src/main/java/example/accessdenied/ReportController.java`:

```java
package example.accessdenied;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/reports/{id}")
    public String byId(@PathVariable long id) {
        return "REPORT:" + id;
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody String title) {
        return "CREATED:" + title;
    }

    @GetMapping("/api/service-report")
    public String sensitive() {
        return reports.sensitive();
    }
}
```

The controller returns fixed strings only to test statuses/bodies. There is no database and no real reports are saved; handlers and security code must be tested appropriately in an application with real business logic.

### 10.8. MockMvc Integration Tests

File `src/test/java/example/accessdenied/AccessDeniedFlowTest.java`:

```java
package example.accessdenied;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessDeniedFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousAdminRequestGetsAuthenticationChallenge() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate",
                containsString("Basic")));
    }

    @Test
    void incorrectPasswordReturns401NotCustom403() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("admin", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerIsDeniedByHttpAuthorizationWithJson403()
            throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.path").value("/api/reports/42"))
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void forbiddenResponseDoesNotRevealExceptionClass() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().string(
                not(containsString("AccessDeniedException"))));
    }

    @Test
    void adminCanReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT:42"));
    }

    @Test
    void readerIsDeniedByServiceMethodSecurityAsJson403()
            throws Exception {
        mvc.perform(get("/api/service-report")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.path").value("/api/service-report"));
    }

    @Test
    void adminMayCallSecuredService() throws Exception {
        mvc.perform(get("/api/service-report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("SERVICE_REPORT"));
    }

    @Test
    void editorMayCreateWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED:Quarterly"));
    }

    @Test
    void readerIsDeniedPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void editorWithoutCsrfIsDeniedIndependentlyOfRole()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isForbidden());
        // Do not assert that the common JSON handler is called for CSRF 403.
    }

    @Test
    void unknownRouteIsDeniedByFallback() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }
}
```

The suite contains **12 test cases**, covering:

1. Public endpoint returning 200 for anonymous.
2. Anonymous hitting a private endpoint getting 401 with a Basic challenge.
3. Wrong password getting 401 instead of JSON 403.
4. Authenticated `reader` missing the role at the HTTP rule receiving JSON 403 with code/path/cache header.
5. Response not leaking the `AccessDeniedException` class name.
6. `admin` accessing the resource with `ROLE_ADMIN`.
7. `reader` hitting a service method with `@PreAuthorize` getting JSON 403 — distinct from denial at `AuthorizationFilter`.
8. `admin` calling the service method successfully.
9. `editor` with valid CSRF performing POST.
10. `reader` with valid CSRF still getting 403 due to missing role; JSON handler observed.
11. `editor` with the right role but missing CSRF getting 403; the test intentionally does **not** assert the same JSON.
12. Undeclared URL blocked by `denyAll()`, custom handler returning 403.

**These are expectations from the lesson code, not a claim of actual execution.** To confirm in practice, create the exact files, run Maven tests in an environment with dependencies, and inspect the results. Nor do these tests substitute for testing reverse proxies, multiple filter chains, async streaming, or OAuth2 Resource Server.

### 10.9. Run Commands

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

If the app runs on `localhost:8080` (default when the port is free):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/reports/42
curl -i -u reader:reader-pass http://localhost:8080/api/reports/42
curl -i -u admin:admin-pass http://localhost:8080/api/reports/42
```

Expected statuses/bodies:

```text
GET /public anonymous           -> 200 PUBLIC_OK
GET /api/reports/42 anonymous   -> 401 + WWW-Authenticate: Basic ...
GET /api/reports/42 reader      -> 403 + JSON ACCESS_DENIED
GET /api/reports/42 admin       -> 200 REPORT:42
```

Sample passwords are for exercise purposes only. Never use `curl -u username:password` with real credentials when shell history/process lists can capture them; production must use TLS and proper secret management.

## 11. Common Mistakes When Writing AccessDeniedHandler

### 11.1. Confusing 401 and 403

**Wrong:** returning 403 for both unauthenticated requests and authenticated requests missing a role. That breaks the HTTP Basic/Bearer challenge contract and leaves clients unsure whether they should authenticate.

**Right:** use `AuthenticationEntryPoint` for insufficient authentication, and `AccessDeniedHandler` for authorization denials when authentication is sufficient per the trust resolver.

### 11.2. Returning HTTP 200 with a JSON 403 Error

A status field in the body does not replace HTTP status. Use `response.setStatus(HttpServletResponse.SC_FORBIDDEN)` and a machine-readable error code, and test both.

### 11.3. Sending Raw exception.getMessage() Externally

That message can leak internal policies, role names, object IDs, Java classes, or implementation details. Use a generic message and a stable error code. To aid debugging, a correlation ID should point only to protected audit logs.

### 11.4. Handler Modifying Authentication or Authorities

The handler is a response boundary. Never promote a user to admin or re-execute a request under different permissions; permissions must be computed in the authorization manager/policy from a trusted source.

### 11.5. Adding Only @RestControllerAdvice

`@ControllerAdvice` handles errors within the MVC lifecycle, whereas Spring Security filters can reject requests **before the controller is called**. Hence an MVC handler does not fully replace an `AccessDeniedHandler` configured on the security filter chain.

### 11.6. Configuring Only an Error Page and Forgetting API Clients

HTML may make sense for a web browser; REST clients need status/content-type and a JSON schema. If the same app serves both client types, split filter chains or select handlers by route/`Accept` header with clear policies. Never return HTML 200 to AJAX just because the error page renders nicely.

### 11.7. Disabling CSRF to Make JSON 403 Uniform

The CSRF filter has its own handling path for a good reason. Do not disable CSRF just so POST tests stop returning 403; send a valid token first, then test the role. For another API architecture, re-evaluate CSRF based on credentials automatically sent by browsers.

### 11.8. Replacing the Bearer Handler and Dropping Headers

If an OAuth2 API requires `WWW-Authenticate`/`insufficient_scope`, a custom handler must preserve the required protocol semantics. Do not copy an HTTP Basic demo verbatim onto a Bearer resource server.

### 11.9. Forwards/Redirects Creating a Loop

An access-denied page can itself be blocked by security if accessing/forwarding to it is not permitted by configuration. Check the error page URL, filter mapping, dispatcher type, and rule order. Do not open every route with `permitAll("/**")` just to make the error page work.

### 11.10. Committed Responses

The handler cannot alter a status already sent over the network. For streaming, async, and Servlet error dispatches, design early error handling or stream-protocol error signaling; never let an exception turn into a false-success response.

### 11.11. Mixing Application Errors with Missing Permissions

A `NullPointerException`, repository timeout, or HTTP 409 from a business conflict is **not** an `AccessDeniedException`. Do not catch every exception and return 403: doing so hides outages and hampers operations. Conversely, when policy actually denies access, do not return 500 with a stack trace.

### 11.12. Failing to Trace Where the "Denial" Came From

HTTP authorization, method security, CSRF, route policies, CORS, gateways, and object-level policies can all yield "cannot access". Start debugging by checking method/path, authentication type, authorities, matched chain, rule, CSRF, and invoked handler; avoid drawing conclusions from status 403 alone.

## 12. Notes When Deploying Multiple SecurityFilterChains

An application may configure:

```text
/api/** -> API SecurityFilterChain:
           Basic/Bearer, JSON error, no form redirect

/web/** -> Web SecurityFilterChain:
           Form login, HTML access-denied page

fallback -> deny-by-default
```

Each chain can have its own `exceptionHandling`, with corresponding entry point and denied handler. Because `FilterChainProxy` selects the **first matching chain**, an overly broad matcher ordered earlier can send API traffic into the web chain and return unintended HTML/redirects.

When splitting chains, always test:

- Anonymous API → proper 401/`WWW-Authenticate`.
- Authenticated API lacking permission → proper 403 JSON.
- Unauthenticated web → proper login redirect.
- Logged-in web lacking permission → error page with right status/forward policy.
- Unknown route/method → strict fallback.
- CSRF and bearer-specific semantics on each chain.

Do not check only that a bean named `JsonAccessDeniedHandler` exists; that bean must actually be wired into the **`SecurityFilterChain` matching the request** to take effect.

## 13. Logging, Audit, and Observability

Access denials are useful security signals, yet logging every 403 with a full stack trace quickly floods logs and leaks data. A controlled operational field set might include:

- Timestamp and server-generated/normalized correlation/request ID.
- Authentication principal identifier permitted by policy for logging (prefer ID over full email).
- Method and **route template** such as `GET /api/reports/{id}` instead of a URL containing sensitive data.
- Security policy/matcher name or stable error code group.
- Outcome `ACCESS_DENIED`, HTTP 403, application/module.
- Trace ID to look up internal logs under tiered access control.

**Never log** raw HTTP Basic headers, JWTs, session cookies, CSRF tokens, passwords, secrets, or full request bodies containing PII. Never concatenate `exception.getMessage()` into user-facing JSON or unredacted metrics labels.

For an endpoint frequently returning 403, distinguish misconfiguration (legitimate users blocked) from scanning/bot/abuse traffic. Rate limiting, WAFs, or threat detection do not replace authorization logic.

## 14. Pre-Release Checklist

- [ ] Understand the difference between `AuthenticationEntryPoint` and `AccessDeniedHandler`; anonymous/remember-me are handled per authentication level.
- [ ] Have proper `hasRole`/`hasAuthority` policies and object-level authorization, not just custom JSON error bodies.
- [ ] Custom handler sets real HTTP status 403, stable error code, properly encoded JSON body, and accurate content type.
- [ ] Handler does not leak exception text, credentials, or unnecessary internal details.
- [ ] Handle already-committed responses; avoid duplicate bodies or unintended redirects.
- [ ] Basic/Bearer APIs preserve proper challenges/headers; OAuth2 Resource Servers do not lose required `WWW-Authenticate`.
- [ ] 401/403 tested separately for anonymous, invalid credentials, and authenticated but missing permissions.
- [ ] CSRF 403 tested separately; POST method-role tests supply valid CSRF.
- [ ] Method security enabled with `@EnableMethodSecurity`; tests cover both HTTP and service denials.
- [ ] If using HTML web pages, forward/redirect access-denied pages are tested for status, URL, dispatcher type, and loops.
- [ ] With multiple chains, each chain wires the proper handler and entry point for its clients.
- [ ] Object/tenant access policies enforce consistent resource-existence hiding rules (403/404) where needed.
- [ ] Logs and audits capture investigative context without raw secrets or sensitive data.
- [ ] Sensitive error responses carry appropriate cache policies, such as `no-store`.
- [ ] Never use response formatting as a substitute for enforcing security authorization.

### Self-Check Questions

**1.** A user is logged in with `ROLE_USER` and calls `GET /api/admin/reports`, which requires `ROLE_ADMIN`. Which extension point typically produces the response?  
**Answer:** When authentication is sufficient to distinguish identity and authorization denies access, `AccessDeniedHandler` typically returns 403.

**2.** An anonymous user visits a private URL. Why can we not assert that a custom `AccessDeniedHandler` will always return 403?  
**Answer:** `ExceptionTranslationFilter` can classify the user as anonymous and call `AuthenticationEntryPoint` to request authentication (401 or login redirect).

**3.** HTTP Basic with a wrong password returns 401—is that an `AccessDeniedHandler` error?  
**Answer:** No. That is an authentication failure handled by the authentication mechanism/entry point.

**4.** A POST from Editor with sufficient permissions but missing a CSRF token gets 403. Why might the body differ from the custom 403 JSON?  
**Answer:** The CSRF filter has its own error-handling path; `exceptionHandling.accessDeniedHandler(...)` is not guaranteed to be invoked for every CSRF denial.

**5.** `@PreAuthorize` denies at the service layer, yet the JSON handler is not called. Which causes should be checked?  
**Answer:** Whether method security is enabled, whether the call goes through a Spring proxy, whether an MVC resolver/controller advice intercepted the exception, and whether the request ran through the expected `SecurityFilterChain`.

**6.** Should you always use `response.getWriter().write(exception.getMessage())`?  
**Answer:** No. Exception text can expose implementation/policy details; use safe codes and messages, and log internally per procedure.

**7.** A Bearer API returns 403 for insufficient scope; what can happen if it returns only JSON and omits `WWW-Authenticate`?  
**Answer:** OAuth2 clients may fail to interpret protocol semantics; keep the appropriate header/handler.

**8.** Should the handler be treated as a place to update roles, permissions, or revoke sessions?  
**Answer:** No. It responds once authorization has already been denied. Modifying permissions or sessions belongs to separate policies.

**9.** Why does the test checking that POST `reader` gets 403 need `with(csrf())`?  
**Answer:** So the request is not blocked by the CSRF filter before reaching authorization, thereby genuinely verifying the missing-role check.

**Conclusion:** In Spring Security Servlet, `AccessDeniedHandler` is **the point that turns a valid authorization denial decision into an HTTP response**, typically 403 for an authenticated caller lacking permissions. Distinguish it clearly from `AuthenticationEntryPoint` for 401/re-login, from CSRF handling paths, and from other business errors. A solid implementation **keeps real status codes, avoids leaking information, preserves HTTP Basic/Bearer semantics, tests both URL and method security**, and never uses pretty responses to mask a broken authorization policy.