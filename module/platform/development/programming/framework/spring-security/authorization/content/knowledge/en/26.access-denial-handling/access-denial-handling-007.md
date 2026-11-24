# Distinguishing AccessDeniedException from CSRF Errors or Business Errors

> Scope: **Spring Security Authorization on the Servlet stack**, HTTP requests, and Spring MVC (especially Spring Security 6.x with Spring Boot 3.x). This lesson focuses on **the cause of denial, where it originates, where it is handled, and how to return the right error**. For WebFlux, WebSocket/STOMP, or gateway systems, handler component names and error paths may differ.

## 1. What to Understand First

When an API returns `403 Forbidden`, you cannot immediately conclude that the user "lacks permissions". There are at least three causes to distinguish:

1. **Authorization denial:** the user has been identified, but does not have the authority/role/permission on the target resource. The Spring Security layer may throw `AccessDeniedException`.
2. **Invalid CSRF:** the request requires CSRF protection, but the token is missing or invalid. `CsrfFilter` throws `CsrfException`, typically `MissingCsrfTokenException` or `InvalidCsrfTokenException`.
3. **Unsatisfied business rule:** the request has passed authentication, CSRF, and authorization policies, but cannot complete due to business state—such as out-of-stock items, locked orders, or invalid state transitions. Services/controllers typically throw domain-specific exceptions.

**Key point about exception types:** `CsrfException extends AccessDeniedException`. Therefore, "CSRF errors" and "exceptions of class `AccessDeniedException`" are **not mutually exclusive sets**. To classify accurately, you must examine the **subtype and origin**, rather than using `exception instanceof AccessDeniedException` to treat everything as an authorization error.

Goals after this lesson:

- Distinguish `AuthenticationException`, `AccessDeniedException`, CSRF subclasses, and business exceptions.
- Explain the behavior of `CsrfFilter`, `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `@RestControllerAdvice`.
- Choose `401`/`403`/`409`/`422`/`400` appropriately by semantics, without guessing the cause from HTTP status alone.
- Configure a demo API returning distinguishable error codes, then test each scenario with `MockMvc`.

## 2. Looking Across Three Dimensions: Error Type, Origin, Handler

| Scenario | Common Exception Type | Origin | Typical Handler | Typical HTTP Response |
| --- | --- | --- | --- | --- |
| Not logged in or invalid/expired login token | `AuthenticationException` and subclasses | Authentication filter/provider | `AuthenticationEntryPoint` or authentication failure mechanism | `401` for REST; may redirect to login for websites |
| Logged in but missing role/authority at URL | `AccessDeniedException` / `AuthorizationDeniedException` | `AuthorizationFilter` (or corresponding authorization mechanism) | `ExceptionTranslationFilter` → `AccessDeniedHandler` | `403` |
| Missing permission at `@PreAuthorize`, `@PostAuthorize`, or method security | Exception in the `AccessDeniedException` family | Method-security interceptor | May propagate back through the web security chain to the handler if not handled earlier | Typically `403` for authenticated users |
| POST/PUT/PATCH/DELETE requires CSRF but token is invalid | `CsrfException` (`AccessDeniedException` subclass) | `CsrfFilter` | `AccessDeniedHandler` used by the CSRF filter | Typically `403` |
| Order already paid, out of stock, state conflict | Application-defined business exception | Service/domain model | `@RestControllerAdvice`/`@ExceptionHandler` | May be `409` or `422` depending on API contract |
| Payload missing fields, invalid format | `MethodArgumentNotValidException`, data binding errors | Spring MVC validation/binding | MVC exception resolver/advice | Typically `400` |

The table says "typical" because the final HTTP status also depends on authentication configuration, handlers, policies, and how the application maps errors. **There is no rule that "every `AccessDeniedException` is 403"**: if the user is not sufficiently authenticated, `ExceptionTranslationFilter` can route to `AuthenticationEntryPoint`.

### HTTP Servlet Processing Order Diagram

~~~text
HTTP request
   │
   ▼
Spring Security FilterChainProxy
   │
   ├─ Authentication filters
   │      └─ Authentication failed → AuthenticationEntryPoint/failure handler
   │
   ├─ CsrfFilter
   │      ├─ HTTP method needing CSRF + missing/wrong token
   │      │      → CsrfException (is-a AccessDeniedException)
   │      │      → AccessDeniedHandler → usually 403
   │      └─ Valid token / check not needed → proceed
   │
   └─ ExceptionTranslationFilter
          └─ downstream AuthorizationFilter / DispatcherServlet
                  ├─ URL/method security denies
                  │      → AccessDeniedException
                  │      → if anonymous/insufficiently authenticated:
                  │           AuthenticationEntryPoint
                  │        if authenticated:
                  │           AccessDeniedHandler → usually 403
                  │
                  └─ Controller → Service
                         ├─ business succeeds → 2xx
                         └─ business exception
                                → MVC @ExceptionHandler → 4xx/5xx per API
~~~

This diagram outlines a typical filter chain. Filter ordering and configuring multiple `SecurityFilterChain` instances can affect the concrete path. `CsrfFilter` forwards token errors to its handler directly; do not assume all CSRF errors must be thrown through `ExceptionTranslationFilter`.

## 3. Distinguishing AccessDeniedException from AuthenticationException

### 3.1 Authentication: "Who are you?"

`AuthenticationException` indicates an authentication problem: missing required credentials, invalid credentials, expired session, wrong bearer token, etc. A REST API typically returns `401 Unauthorized` with details on how to authenticate. With form login, `AuthenticationEntryPoint` may redirect `302` to the login page.

### 3.2 Authorization: "Are you allowed to do this?"

`AccessDeniedException` belongs to the permission decision stage. A user with authority `ROLE_USER` calling `GET /api/admin/report` which requires `ROLE_ADMIN` will be denied even though the user logged in successfully.

In Spring Security, `ExceptionTranslationFilter` is the bridge between exceptions and HTTP responses; it **does not make authorization decisions itself**. In common cases:

- When receiving `AuthenticationException`, it begins the authentication flow via `AuthenticationEntryPoint`.
- When receiving `AccessDeniedException` for an insufficiently authenticated request (including anonymous and depending on remember-me settings), it begins authentication.
- When receiving `AccessDeniedException` for a fully authenticated principal, it calls `AccessDeniedHandler`. By default, the result is usually `403`.

Example rule:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders/**").authenticated()
    .anyRequest().denyAll()
);
~~~

This is a **configuration snippet**, not a standalone Java class. `hasRole("ADMIN")` by default matches the `ROLE_ADMIN` authority; different from `hasAuthority("ADMIN")`. `authenticated()` verifies login but does not check business permissions on individual orders.

**Note on data-level permissions:** if a validly logged-in user tries to read another user's order, that can be an **object-level authorization error**, even if the check is performed inside a service. It should be represented and handled according to security policy; do not arbitrarily turn it into a "business error" just because it arises after entering the controller. Some APIs intentionally return 404 to avoid disclosing resource existence; that must be a consistent design decision.

## 4. CSRF: Why Is It Still Related to AccessDeniedException?

CSRF (Cross-Site Request Forgery) exploits cases where a browser automatically attaches credentials like session cookies to requests initiated by another site. Spring Security protects potentially state-changing requests by requiring a token that malicious sites are not allowed to retrieve/read. By default in Servlet:

- Methods `GET`, `HEAD`, `OPTIONS`, `TRACE` are considered safe and normally do not require a CSRF token.
- Methods like `POST`, `PUT`, `PATCH`, `DELETE` are checked for CSRF unless configured otherwise.
- If the token is missing or mismatches, `CsrfFilter` terminates the request via `AccessDeniedHandler`. The request never reaches the business endpoint.

Inheritance hierarchy:

~~~text
RuntimeException
   └─ AccessDeniedException
        ├─ AuthorizationDeniedException (in authorization flows)
        └─ CsrfException
             ├─ MissingCsrfTokenException
             └─ InvalidCsrfTokenException
~~~

The CSRF classes reside in package `org.springframework.security.web.csrf`. Distinguish their general meanings:

- `MissingCsrfTokenException`: the protection process did not find the expected token in the repository in the corresponding situation.
- `InvalidCsrfTokenException`: the submitted token did not match the expected one (which can include cases where no header was sent while an expected token existed). Do not rely on the subclass name alone to conclude with certainty "frontend missed the header" or "token expired"; inspect the request, session, repository, and request handler configuration.
- `CsrfException` is the common superclass allowing CSRF errors to be classified accurately regardless of the specific form.

Example of a logged-in user sending `POST /api/orders/checkout`:

~~~text
Cookie: JSESSIONID=...
POST /api/orders/checkout
(no X-CSRF-TOKEN / X-XSRF-TOKEN header)
                 │
                 ▼
CsrfFilter: token missing/invalid
                 │
                 ▼
AccessDeniedHandler: HTTP 403 (CSRF_REJECTED)
                 │
                 └─ Controller and business logic do not run
~~~

Point to remember: **a 403 status from CSRF and a 403 from missing roles can look identical**. Identification must rely on the exception subtype (if observable), security configuration, and request path.

In Spring Security Servlet, `CsrfConfigurer` can use the `AccessDeniedHandler` configured via `exceptionHandling`; the demo below leverages that mechanism to return distinct error codes. If a project has multiple filter chains, custom CSRF handlers, or a custom invalid-session strategy, check which chain actually intercepts the request.

### Is CSRF Always Necessary for REST APIs?

No. The risk depends on **how the browser sends credentials**: cookies/sessions are prone to automatic sending; bearer tokens explicitly placed by JavaScript in the `Authorization` header have a different threat model. However, do not conclude "REST is stateless so disable CSRF" or "using JWT guarantees no CSRF"; if a JWT is stored in an automatically sent cookie, CSRF can still be an issue. Only change CSRF configuration after understanding the frontend, session/cookies, and authentication method.

## 5. Business Errors: Security Accepted the Request, but the Operation Cannot Proceed

An example: the user is allowed to purchase, provides a valid CSRF token, and submits valid input, yet inventory has insufficient stock. This is a business state conflict, not a missing `ROLE_ADMIN` or CSRF token.

You should define domain exceptions/responses, e.g., `OutOfStockException` → `409 Conflict` with `code=OUT_OF_STOCK`. Other applications may choose `422 Unprocessable Content` for certain semantic violations; publish consistent rules in the API contract. Resource-not-found errors typically use `404`, and syntax/field validation errors typically use `400`.

Do not:

- Throw `AccessDeniedException` just because inventory is insufficient, returning 403.
- Throw `OutOfStockException` when the user actually lacks permission to read inventory (that is semantically wrong and can leak information).
- Catch generic `Exception` and convert everything into 403/400. Program and infrastructure errors may require 500; security errors must take their proper handling branch.

Distinguish "lacking permission" from "failing business conditions" through **the permission model and domain business rules**, not simply by whether the exception occurred in a controller or service.

## 6. Complete Example: Same API, Three Distinct Denial Outcomes

The example below uses **Java 17+**, a Spring Boot 3.x (Spring Security 6.x) project, with standard dependencies:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- For testing: `spring-boot-starter-test` and `spring-security-test`

The following Java files are placed in `src/main/java/example/denial/` (package matches the path). Default session and CSRF are used; the demo does not configure a login form or bearer token, instead testing with security test principals. In real integration, the application must configure its own login/authentication mechanism.

### 6.1 Application Entry Point

**DenialDemoApplication.java**

~~~java
package example.denial;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DenialDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DenialDemoApplication.class, args);
    }
}
~~~

### 6.2 Authorization and Security Error Classification

**SecurityConfig.java**

~~~java
package example.denial;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfException;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ObjectMapper json) throws Exception {

        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders/checkout")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                    writeError(response, json, 401, "AUTHENTICATION_REQUIRED")
                )
                .accessDeniedHandler((request, response, exception) -> {
                    String code = (exception instanceof CsrfException)
                        ? "CSRF_REJECTED" : "ACCESS_DENIED";
                    writeError(response, json, 403, code);
                })
            );

        return http.build();
    }

    private static void writeError(
            HttpServletResponse response,
            ObjectMapper json,
            int status,
            String code) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        json.writeValue(response.getOutputStream(), Map.of("code", code));
    }
}
~~~

Explanation:

- `requestMatchers(...).hasRole("ADMIN")` determines URL access permission. A logged-in user missing the role goes through the `AccessDeniedHandler` branch with `code=ACCESS_DENIED`.
- `csrf(Customizer.withDefaults())` enables the default protection configuration. A POST without a valid token is blocked by `CsrfFilter` **before the controller**; the handler receives a `CsrfException` subclass and returns `code=CSRF_REJECTED`.
- `AuthenticationEntryPoint` returns `401` for requests requiring authentication without a valid principal in the demo context. Different authentication mechanisms may return 401 or redirect to login differently.
- Checking `instanceof CsrfException` must logically come **before the general `AccessDeniedException` classification**; checking only the superclass would mistakenly lump CSRF into missing-permission errors.
- The API returns stable public error codes without putting exception details, tokens, cookies, internal permissions, or stack traces into the response.

**Important:** This is an intentional `SecurityFilterChain` configuration for the lesson; in a project with multiple chains or custom handlers, you must apply the same policy to the right chain before concluding responses will match the demo.

### 6.3 Controller and Business Exception

**OrderController.java**

~~~java
package example.denial;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestController
class OrderController {

    @GetMapping("/api/admin/report")
    String adminReport() {
        return "report-ok";
    }

    @PostMapping("/api/orders/checkout")
    String checkout() {
        throw new OutOfStockException();
    }
}

class OutOfStockException extends RuntimeException {
}

@RestControllerAdvice
class BusinessErrorAdvice {

    @ExceptionHandler(OutOfStockException.class)
    ResponseEntity<Map<String, String>> outOfStock(
            OutOfStockException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(Map.of("code", "OUT_OF_STOCK"));
    }
}
~~~

`checkout()` intentionally throws `OutOfStockException` to illustrate a business outcome; a real application checks inventory in a service and handles transactions and idempotency as required. `BusinessErrorAdvice` is a Spring MVC component, handling only errors reaching the MVC phase. It is not meant to replace CSRF/security filters.

### 6.4 Testing Boundaries with MockMvc

**src/test/java/example/denial/DenialDemoApplicationTests.java**

~~~java
package example.denial;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class DenialDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousAdminRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsDenied() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void postWithoutCsrfIsRejectedBeforeBusinessLogic() throws Exception {
        mvc.perform(post("/api/orders/checkout")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("CSRF_REJECTED"));
    }

    @Test
    void validCsrfReachesBusinessRuleAndReturnsConflict() throws Exception {
        mvc.perform(post("/api/orders/checkout")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("OUT_OF_STOCK"));
    }

    @Test
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-ok"));
    }
}
~~~

The tests use MockMvc and mock principals from `spring-security-test`; they **do not test the real login mechanism**, but accurately test the boundaries between 401, 403 CSRF, 403 authorization, and 409 business conflict. Run with the project's test task (such as `./gradlew test` in a Gradle project with the dependencies above). Do not run individual files with plain `javac`, because the classes depend on Spring/JUnit and must run in a Spring Boot context.

Expected HTTP results (the `code` part of JSON; full format is produced by the configuration above):

| Request | Principal and Token | Status | JSON code |
| --- | --- | --- | --- |
| `GET /api/admin/report` | Anonymous | 401 | `AUTHENTICATION_REQUIRED` |
| `GET /api/admin/report` | `ROLE_USER` | 403 | `ACCESS_DENIED` |
| `POST /api/orders/checkout` | `ROLE_USER`, no CSRF | 403 | `CSRF_REJECTED` |
| `POST /api/orders/checkout` | `ROLE_USER`, valid CSRF | 409 | `OUT_OF_STOCK` |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200 | `report-ok` (text body) |

**The two 403 rows have the same status but different causes.** For a POST with valid CSRF, only after passing the security layer is the business condition evaluated to return 409.

## 7. How to Diagnose in Real Projects

Follow this flow instead of guessing from an error page:

### Step 1: Identify the Exact Request and Security Filter Chain

Record the method, path, timestamp, authenticated identity, request correlation ID, and status. Check the exact `SecurityFilterChain` applied to the path (especially with multiple chains, context paths, or reverse proxies). **Do not log CSRF tokens, cookies, Authorization headers, or passwords**.

### Step 2: Check Whether the Error Occurred Before the Controller

- Controller/service was not called; unsafe request; log/handler indicates `CsrfException` → prioritize checking CSRF.
- Controller was not called; `AuthorizationFilter`/URL policy denied → check principal and authorities.
- Controller/service ran → check method security, object-level authorization, validation, and business exceptions. Entering the controller does not mean `AccessDeniedException` cannot occur.

### Step 3: Read the *Original Exception Type* Instead of Error Text

Decision pattern (pseudocode):

~~~text
if cause is CsrfException:
    classification = CSRF_REJECTED
else if cause is AccessDeniedException:
    classification = ACCESS_DENIED
else if cause is AuthenticationException:
    classification = AUTHENTICATION_REQUIRED
else if cause is domain-specific exception:
    classification = BUSINESS_RULE_VIOLATION
else:
    classification = other error
~~~

This is a **root-cause classification pattern**, not advice to bubble every exception up to one global catch. The proper catching and handling locations of each layer in Spring Security/MVC must still be preserved.

### Step 4: Verify with Controlled Comparisons

- Same user, same `GET /api/admin/report`, toggling only role `USER` ↔ `ADMIN`: if the result toggles 403 ↔ 200, this is an authorization issue.
- Same user, same `POST /api/orders/checkout`, toggling only missing/wrong ↔ valid CSRF token: if 403 CSRF ↔ 409 business, CSRF control is working properly.
- With a valid CSRF token, keep user permissions constant and change business inventory state: business errors can toggle between 2xx and 409. If both requests remain 403, inspect authorization or an earlier filter layer.
- Test anonymous separately from "logged in without role"; `ExceptionTranslationFilter` can route the two cases to different handlers.

### Step 5: Keep Responses Stable and Safe

The API can publish a consistent schema, for example:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "You do not have permission to perform this operation.",
  "requestId": "req-7b22"
}
~~~

`requestId` above is illustrative only; in a real system, the value must come from the tracing/correlation mechanism. Response content should avoid naming secret resources/roles or token details; server-side logs can record the exception type and trace ID to aid operations. Never return stack traces to clients.

## 8. Nuances Often Overlooked

### 8.1 Method Security Can Throw AccessDeniedException After URL Authorization

When `@EnableMethodSecurity` is enabled and `@PreAuthorize` is used, a service method can be blocked even if the URL rule is `authenticated()`. For example:

~~~java
// Illustrates a method in an application's @Service.
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    // Further check permissions on invoiceId and process business logic.
}
~~~

Note: this snippet is an **illustrative method**, not a standalone class. If the denial exception propagates back through the servlet filter chain, `ExceptionTranslationFilter` can handle it. If an overly broad `@ControllerAdvice` catches `AccessDeniedException`/`Exception`, the behavior may be altered beforehand; avoid catching them together like that.

### 8.2 A 403 Error Does Not Prove AuthorizationFilter Caused It

A 403 can come from `CsrfFilter`, another security filter, the application itself, or a reverse proxy. CSRF classes inherit from `AccessDeniedException`, so even the parent exception name is insufficient. Rely on origin + subtype + controlled comparison tests.

### 8.3 401 and 403 Can Vary by Authentication Mechanism

For REST using an `AuthenticationEntryPoint` that returns 401, anonymous users typically see 401. For form login, the same branch may redirect. Remembered users (remember-me) may sometimes still be considered insufficiently authenticated for a specific resource. Therefore, first determine **whether it is the authentication or authorization branch**, then consider the configured status/redirect.

### 8.4 ControllerAdvice Does Not Cover the Security FilterChain

`@ExceptionHandler` in MVC handles exceptions once the request reaches `DispatcherServlet` and is processed by an MVC resolver. CSRF and many filter-level authorization decisions happen earlier, so MVC handlers usually **do not receive** them. Configure `exceptionHandling` for HTTP security errors; use `@RestControllerAdvice` for domain/validation errors. If a uniform error format is desired, handlers can share a utility/schema, but they must be registered at the proper layer.

### 8.5 Do Not Turn a 403 Error into a Reason to Drop CSRF Checks

Disabling `csrf()` may make a 409 business test "suddenly pass", while simultaneously removing forged-request protection if the app relies on cookies/sessions. The right fix is usually issuing and sending tokens for appropriate requests, managing token lifecycle after login/logout, or clearly defining the threat model before customizing.

### 8.6 Do Not Equate All Application Errors with "Insufficient Permissions"

A request that passes HTTP authorization yet violates a business rule should be represented with a domain exception and a contract-defined error code. However, if the rule concerns **a user's permissions on an object** (owner, tenant, room member), treat it as authorization to prevent data leaks and apply it consistently with policy.

## 9. Summary Comparison Table for Self-Check

| Question | Authorization Denial | CSRF Rejection | Business Rejection |
| --- | --- | --- | --- |
| Violated condition | Principal lacks permission/authority/resource access | CSRF token invalid when request requires protection | Business state/rule prevents completion |
| Common exception | `AccessDeniedException` and subclasses (excluding CSRF) | `CsrfException`, **also an AccessDeniedException** | Domain custom `RuntimeException` |
| Identifying component | AuthorizationFilter/method interceptor | CsrfFilter | Service/domain/controller |
| Typical handler | ExceptionTranslationFilter → EntryPoint or AccessDeniedHandler | CsrfFilter → AccessDeniedHandler | MVC advice/exception resolver |
| Common status | 403 if logged in; 401/redirect if not | 403 | 409, 422, 400, or another status by error type |
| Best evidence | Role/authority/ownership and denial decision | Exception subtype + CSRF/token state | Domain error code + state |
| Proper fix | Update permissions or policy per business rules | Fix token/client flow and sensible CSRF config | Fix input/state/business workflow |

**Key takeaway:** `AccessDeniedException` describes a family of security errors; `CsrfException` is **one branch in that family**; business errors have **their own origin and representation**. Whenever HTTP 403 is observed, inspect the exception subtype, the filter/handler that processed it, and request evidence before drawing conclusions.

## 10. Official References

- Spring Security — Servlet architecture / Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF protection and Handling AccessDeniedException: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — HTTP authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security API — CsrfException (subclass of AccessDeniedException): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/csrf/CsrfException.html
