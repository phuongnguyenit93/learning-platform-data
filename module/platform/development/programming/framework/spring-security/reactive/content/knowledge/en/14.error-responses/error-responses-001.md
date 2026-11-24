# Distinguishing Authentication, Authorization, and Business Errors

## 1. Why Must Error Types Be Distinguished Properly?

A Spring Security Reactive application on WebFlux does not only return successful data; it must also explain accurately **why a request was not processed**. Three situations are easily conflated:

1. **Authentication failure:** the server has not verified the caller's identity, for example missing access token, wrong password, or expired token.
2. **Authorization failure:** the identity has been verified, but is not permitted to access the resource or operation.
3. **Business/domain error:** the request has passed the required security checks, but the data or business state does not satisfy the conditions; for example out of stock, order cannot be cancelled, or invalid discount code.

These three error types should not be returned identically. If every error becomes HTTP 401, the client will keep prompting to log in when the real error is out of stock. If every error becomes HTTP 500, operations monitoring will think there is a server outage even though this is an expected business rule. If "insufficient permissions" returns 200 with a body saying "failed", many clients/caches/monitoring tools may misinterpret it.

### After This Lesson, You Can

- Clearly state the meaning of HTTP **401**, **403**, **400**, **404**, **409**, **422**, **429**, and **5xx** in the WebFlux context.
- Distinguish `AuthenticationException`, `AccessDeniedException`, and custom domain exceptions.
- Identify which errors are handled inside the **Spring Security WebFilter chain** and which come from controllers/services or the WebFlux error infrastructure.
- Configure `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` appropriately without losing the HTTP Basic challenge.
- Return business errors using `ProblemDetail` (RFC 9457) and `@RestControllerAdvice`.
- Run a Java 17+, Spring Boot WebFlux, and `WebTestClient` example, testing the 401/403/400/404/409/422 cases independently.
- Design an error contract that avoids leaking sensitive data, does not swallow errors, does not mix validation errors with access permissions, and does not break the reactive pipeline.

This lesson belongs to the **Error Responses** group of the Spring Security Reactive module. The examples use HTTP Basic for easy verification; with OAuth2 Resource Server/JWT, the error classification principles remain the same, while the challenge, body, and authentication mechanism change according to the actual configuration.

## 2. Three Questions at Three Layers

Imagine a request `GET /api/orders/42` passing through three decision layers:

~~~text
HTTP request
      |
      v
(1) AUTHENTICATION
    "Who are you? Are the credentials valid?"
      |
      +-- Missing/wrong credentials --> authentication error
      |                                 usually 401
      |
      v
(2) AUTHORIZATION
    "Is that identity allowed to call this route / view this order?"
      |
      +-- Not permitted -----------> authorization error
      |                              usually 403;
      |                              may be 404 to avoid leaking existence
      |
      v
(3) BUSINESS / DOMAIN
    "Do the data and state allow performing the business operation?"
      |
      +-- Malformed input --------> 400 or 422 depending on contract
      +-- Object does not exist --> 404
      +-- State conflict ---------> 409
      +-- Other rules ------------> appropriate 4xx
      |
      v
Success: 2xx
~~~

The diagram is conceptual, **not an absolute ordering of every WebFilter**. For example, the CSRF filter may reject a POST with **403** before the controller or authorization handles it; HTTP syntax errors may be detected early by WebFlux/the HTTP server. Do not infer "every 403 is a missing role" or "every 400 is caused by business logic".

The three questions can be independent:
- "Wrong password" happens before there is a trusted authenticated principal.
- "Correct password but missing role ADMIN" is not a password error.
- "Authorized user but out of stock" is not a security error.

## 3. Quick Comparison Table

| Criterion | Authentication | Authorization | Business |
| --- | --- | --- | --- |
| Question | Has the identity been proven? | Is the caller allowed to do this? | Do the data/state conditions allow the operation? |
| Examples | Missing/expired/invalid-signature token, wrong username/password | Regular user calling an admin API; reading an object not belonging to the tenant | Quantity exceeds stock; shipped order cannot be cancelled |
| Common exceptions | `AuthenticationException`, `BadCredentialsException`, and variants | `AccessDeniedException`, authorization manager errors | `DomainException` or application-specific exceptions |
| Typical handling point | Authentication filter/entry point/failure handler | Authorization filter, `ServerAccessDeniedHandler` | Service/controller, `@ExceptionHandler`, or WebFlux error handler |
| Common HTTP status | **401** | **403** | **400/404/409/422** (depending on error) |
| What client should do | Obtain/update credentials, log in again if needed | Do not retry identically just by refreshing the token; need permissions/change resource | Fix input, resolve conflict, display business message |
| Logging/metrics | Label auth_failure | Label access_denied | Specific domain error code, do not leak secrets |

**Note:** 401/403 can also come from mechanisms outside these three columns: HTTP server, reverse proxy, WAF, CSRF, or API gateway. The table describes typical application design and does not replace investigating the layer that actually produced the response.

## 4. HTTP 401: Authentication Not Yet Succeeded

**401 Unauthorized** in HTTP signals that the server requires valid **authentication** for the resource. The name "Unauthorized" is rather misleading; its practical usage is **authentication has not succeeded**, not "authenticated but lacking permissions".

Common situations:
- Missing `Authorization` header for an API requiring credentials.
- Basic header with wrong username/password.
- Bearer token expired, invalid signature, wrong issuer/audience, or invalid according to the Resource Server.
- Authentication mechanism received no information to prove identity.

With HTTP Basic, a protocol-compliant response usually has:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

The `WWW-Authenticate` header issues a challenge so the client knows which mechanism to use. If writing a custom error handler strips the challenge, browsers or HTTP clients may fail to handle the authentication flow as expected.

With a Bearer Resource Server, the challenge may take the form `WWW-Authenticate: Bearer ...` per the relevant specification, and `invalid_token` or scope details may appear depending on configuration. Do not copy raw sensitive information from the token into the error message.

### 4.1. A 401 Result Does Not Automatically Guarantee a JSON Body

A Spring Security WebFilter may only set the status and headers, without a `ProblemDetail`-like body from a controller. Therefore, clients should not assume every 401 has a JSON body like business errors. If an API requires a unified error envelope, it must be configured **directly at the entry point/failure handler** of Spring Security, not merely by adding `@RestControllerAdvice`.

### 4.2. What Should the Client Do?

- If credentials are missing and the user is not logged in: direct the user to the appropriate authentication flow.
- If the access token is expired: use a protected refresh flow if available, with a retry limit.
- If wrong password/invalid token: report an appropriate error and avoid infinite retries.
- **Do not self-grant additional permissions** or remove authorization rules to "fix 401".
- Do not include raw passwords, Authorization headers, or tokens in frontend/server logs.

## 5. HTTP 403: Identity Verified, Insufficient Permissions

**403 Forbidden** usually means the server understood the request but **refuses to authorize** the action. Examples:
- User with `ROLE_USER` calling `/api/admin/metrics` which requires `ROLE_ADMIN`.
- User reading an order belonging to someone else.
- User lacking the required authority/scope.
- Tenant/ABAC policy or a `denyAll()` rule rejects the request.

Unlike 401, resending the **exact same** credentials usually does not resolve a 403. The client needs to adjust the target resource, account/permissions, or request access through a valid process.

### 5.1. 403 Is Not Always a Role Authorization Error

In Spring Security WebFlux, **CSRF** can return **403** for a POST/PUT/PATCH/DELETE request with a missing or invalid token, even when HTTP Basic/JWT is valid. Reverse proxies and WAFs can also return 403. Therefore, record the error source properly via logs/traces, and do not guess that every 403 is caused by `hasRole`.

### 5.2. Does a Blocked Anonymous User Always Get 403?

No. When authorization requires permissions but the request does not yet have suitable authentication, Spring Security may trigger the authentication entry point, resulting in **401** instead of routing the request to the access-denied handler. An application can also redirect to a login page in a browser model.

You must consider **authentication state** together with the exception type and handler configuration. Do not hard-code the assumption "AccessDeniedException is always 403".

### 5.3. When to Return 404 to Hide a Resource?

For a resource only its owner should know about, an API sometimes intentionally returns **404 Not Found** to unauthorized callers so as not to disclose its existence. This decision must be consistent with the threat model and data-access policy; 404 **does not replace permission checks**.

Do not perform an unauthorized lookup and then leak data via timing, messages, cache, or authorization ordering. There must be a consistent service pattern protecting resource ownership.

## 6. Business Errors: Not Every Error Is 401/403

When identity and permissions are valid, a request may still fail due to **business conditions**. Some common mappings:

| HTTP | Situation | Why it fits |
| --- | --- | --- |
| **400 Bad Request** | Parameter syntax/format error, missing required field, unconvertible data type | Request violates the input contract |
| **404 Not Found** | Resource ID does not exist/is not disclosed to the caller | Requested resource was not found |
| **409 Conflict** | Current state conflicts with the operation: out of seats, stale update version, competing inventory | Current state conflict needs resolution |
| **422 Unprocessable Content** | Input has valid format but violates a defined semantic rule, e.g., quantity must be greater than 0 | Content is understood but cannot be processed per rules |
| **429 Too Many Requests** | Rate limit exceeded per policy | Need to slow down or wait; may include `Retry-After` |
| **503 Service Unavailable** | Critical dependency temporarily unavailable or system in maintenance/overloaded | Temporary infrastructure error, not a user data error |
| **500 Internal Server Error** | Unexpected server error: bug, NullPointerException, broken configuration | Do not turn stack traces into client content |

There is no single HTTP mapping for **every** domain. For example, "expired discount code" might be designed as 400/409/422 depending on the published contract, but it must be **consistent**, have a machine-readable error code, and have tests.

### 6.1. Distinguishing 400, 409, and 422 by Example

Order preview API:

~~~text
GET /api/orders/preview?quantity=abc
    -> 400: query parameter cannot be converted to an integer

GET /api/orders/preview?quantity=0
    -> 422: data type is valid, but quantity violates the > 0 rule

GET /api/orders/preview?quantity=9
    -> 409: quantity is semantically valid, but current stock cannot satisfy it

GET /api/orders/preview?quantity=2
    -> 200: preview can be created
~~~

This is a **read-only GET**: it does not place an order, decrement stock, or execute a transaction. If later changed to a real order-creation POST endpoint, you must add authorization checks, transaction/idempotency, and CSRF when browser clients use ambient credentials. Do not use GET with side effects to avoid sending a CSRF token.

### 6.2. Business Errors Are Not System Exceptions

An expected business rejection should not throw `NullPointerException` just to report "out of stock". Use dedicated domain exceptions/models with clear names and codes, such as `InsufficientStockException` or `OrderAlreadyShippedException`.

Conversely, a lost database connection is not "order not found". Do not map every repository/timeout error to 404 or 409 just so the client will not see 500. Preserve the true nature of incidents so operations can recognize them.

## 7. Error Handling Points in Spring Security Reactive Differ from WebFlux Controllers

In a WebFlux application, processing typically includes:

~~~text
Incoming HTTP
     |
     v
SecurityWebFilterChain
     |
     +--> AuthenticationWebFilter
     |       +--> Authentication conversion / manager
     |       +--> authentication failure handler
     |
     +--> ExceptionTranslationWebFilter / authorization
     |       +--> ServerAuthenticationEntryPoint (usually 401/challenge)
     |       +--> ServerAccessDeniedHandler (usually 403)
     |
     v
DispatcherHandler / RouterFunction / Controller
     |
     +--> @ExceptionHandler / @RestControllerAdvice
     |       +--> Domain exceptions -> 404/409/422
     |       +--> Binding/validation errors -> 400...
     |
     v
WebFlux ErrorWebExceptionHandler / framework error handling (when needed)
     |
     v
Response
~~~

**The diagram is conceptual and does not assert the exact order of every filter.** Authentication failure handlers, exception translation, CSRF, and routing have their own mechanisms. Errors from security filters can be handled before the controller is ever invoked.

### 7.1. Classes to Remember

| Component | Responsibility |
| --- | --- |
| `AuthenticationWebFilter` | Performs an authentication attempt, invokes converter/manager, handles success/failure |
| `ServerAuthenticationEntryPoint` | Initiates authentication when identity is required; may return 401 + challenge or redirect |
| `ServerAuthenticationFailureHandler` | Handles a rejected authentication attempt, depending on mechanism |
| `ServerAccessDeniedHandler` | Responds when access is denied, usually 403 for an authenticated user |
| `ExceptionTranslationWebFilter` | Routes downstream `AccessDeniedException` to the appropriate entry point or access-denied handler |
| `@RestControllerAdvice` + `@ExceptionHandler` | Maps exceptions from handlers/controllers/services to HTTP responses |
| `ErrorWebExceptionHandler` | Low-level error handling mechanism of WebFlux/Boot |
| `ProblemDetail` | RFC 9457 compliant body format for API errors; does not itself choose where security exceptions are caught |

**Do not use `ExceptionTranslationFilter` (Servlet) for WebFlux.** The reactive counterpart is `ExceptionTranslationWebFilter` and interfaces named `Server...`. Do not bring Servlet's `HttpSecurity`, `HttpServletRequest`, or `AuthenticationEntryPoint` over to `ServerHttpSecurity`.

### 7.2. Why Does @RestControllerAdvice Not Catch All 401/403 Errors?

`@RestControllerAdvice` operates in the controller handling layer and related errors. A request can be rejected by Spring Security **before reaching DispatcherHandler**. In that case, `@ExceptionHandler(AuthenticationException.class)` placed in controller advice is not guaranteed to be called.

If the API needs a unified security error body, configure **entry point** and **access denied handler** in `ServerHttpSecurity.exceptionHandling(...)`, and also check the authentication mechanism's failure handler. Do not just put a global `@ExceptionHandler(Exception.class)` and hope to catch all filter exceptions.

### 7.3. Do Not Swallow AccessDeniedException

Incorrect example in the service/controller layer:

~~~java
// WRONG: turns insufficient permissions into a success state.
return service.loadSensitiveData()
        .onErrorResume(AccessDeniedException.class,
                ex -> Mono.just(new DataDto("hidden")));
~~~

This is an illustrative snippet, not a standalone runnable class. If a service emits `AccessDeniedException` due to missing permissions, replacing it with fake data and HTTP 200 can mask a security violation. Only handle exceptions when there is an explicit policy and ensure the response semantics are not wrong.

Similarly, an `onErrorResume(Throwable.class, ...)` placed too high in the pipeline can accidentally turn 401/403/500 into 200. Every fallback must be scoped to specific error types and have tests.

## 8. Designing the Response Body: Using ProblemDetail and Business Codes

Spring Framework WebFlux supports **RFC 9457 Problem Details for HTTP APIs** via `org.springframework.http.ProblemDetail`. An example response:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Requested quantity is not available",
  "instance": "/api/orders/preview",
  "code": "INSUFFICIENT_STOCK"
}
~~~

Standard fields:
- `type`: URI identifying the problem type; by default may be `about:blank`.
- `title`: short summary title, usually unchanging across occurrences.
- `status`: corresponding HTTP status code.
- `detail`: explanation safe to display to the client.
- `instance`: URI of the affected request.
- `code` in the example is an **application-added extension property**, not a required field in RFC 9457.

Clients should rely on the **HTTP status** for general handling and a **stable error code** for business actions, rather than parsing English/Vietnamese sentences in `detail`.

### 8.1. Why Standardize the Error Contract?

- Frontend can display login, insufficient-permission, and out-of-stock errors with the right message.
- Mobile/backend clients can decide whether to retry or ask the user to fix input.
- Dashboards can distinguish auth failure, denied, invalid input, conflict, and server outage.
- Backend does not need to expose raw exception messages, SQL, or stack traces.
- API/OpenAPI documentation can declare 4xx/5xx responses with clear schemas.

However, **standardizing the contract does not necessarily force every response to have a body**. Some HTTP statuses or standard authentication mechanisms have mandatory/important headers; do not drop `WWW-Authenticate` for HTTP Basic/Bearer just to return JSON. If adding a body to security responses, design and test it separately.

### 8.2. Enabling Problem Details Support for Standard WebFlux Errors

Spring Boot supports:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

It enables many **built-in WebFlux errors** to be represented as Problem Details. This setting **does not automatically turn every error inside Spring Security WebFilters** into JSON ProblemDetail. Authentication/authorization errors handled at the security layer still need corresponding entry points/handlers if a unified body is desired.

## 9. Complete Java 17+ Example: Security First, Business Logic After

We will build a small WebFlux API with:
- Public endpoint.
- Endpoint requiring a logged-in user.
- Admin-only endpoint.
- Input error: 400.
- Resource not found error: 404.
- Quantity condition error: 422.
- Stock conflict error: 409.
- Authentication error: 401.
- Authorization error: 403.

To make running with `curl` easy, the demo uses HTTP Basic with in-memory accounts. **Use only on localhost** because the demo passwords have `{noop}` and Basic credentials are not encrypted by Base64. Production requires HTTPS, strong password hashing, rate limiting, auditing, and an appropriate login mechanism.

Uses Spring Boot **3.5.7**, Java 17, Gradle, and Spring Security Reactive 6.x. The example code is designed per public APIs; the HTTP results are expected when running the project properly, not a report of an actual build run.

### 9.1. File Structure

~~~text
reactive-error-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ApiController.java
    │   │   ├── DomainExceptions.java
    │   │   └── DomainErrorAdvice.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── ErrorResponseTest.java
~~~

### 9.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-error-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages WebFlux, Spring Security, and Reactor library versions via dependency management. When deploying to a real system, choose a Boot branch supported by your organization with the latest patches; the version here is only for a clear demo configuration.

### 9.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactive-error-demo
  webflux:
    problemdetails:
      enabled: true
~~~

This option allows standard framework errors (e.g., failing to convert parameter `quantity=nope` to `int`) to produce a Problem Details response when resolved by the corresponding WebFlux handler. It does not replace custom `@ExceptionHandler` methods for domain errors or Spring Security handlers.

### 9.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/products/**",
                                "/api/orders/preview")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new HttpBasicServerAuthenticationEntryPoint())
                        .accessDeniedHandler(
                                new HttpStatusServerAccessDeniedHandler(
                                        HttpStatus.FORBIDDEN)))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Analysis of each decision:**
1. `/api/public` does not require login.
2. `/api/admin/metrics` requires the `ADMIN` role.
3. `/api/products/**` and `/api/orders/preview` require authentication, but not ADMIN.
4. `anyExchange().denyAll()` blocks undeclared routes/methods. This can cause a URL that matches no controller to return 403 **before** WebFlux would intend to return 404.
5. HTTP Basic is used for the demo to test 401, not as the default choice for a real product.
6. `HttpBasicServerAuthenticationEntryPoint` is the Reactive entry point for Basic: it can generate 401 with the `WWW-Authenticate` challenge.
7. `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)` responds with 403 when authorization denies access and that handler is applied.
8. `formLogin` is disabled so there is no 302 redirect to an HTML login page in the example.
9. CSRF remains at its default. The demo endpoints only use GET, so no CSRF token is needed for these test commands. If POST is added, CSRF must be evaluated properly.
10. In-memory users and `{noop}` are mocks unsafe for production.

**Do not confuse role with authority:** `hasRole("ADMIN")` normally checks the `ROLE_ADMIN` authority; `hasAuthority("ADMIN")` is a different string. The two demo users only have their declared roles.

### 9.6. DomainExceptions.java

`src/main/java/demo/DomainExceptions.java`:

~~~java
package demo;

// Package-private classes are valid in the same Java file;
// the file has no public class so there is no public filename constraint.

final class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException() {
        super("Product not found");
    }
}

final class InvalidQuantityException extends RuntimeException {
    InvalidQuantityException() {
        super("Quantity must be positive");
    }
}

final class StockConflictException extends RuntimeException {
    StockConflictException() {
        super("Requested quantity exceeds available stock");
    }
}
~~~

Each exception has its own **domain semantics** and does not need to depend on Spring Security. These are expected errors in the use case, distinct from `BadCredentialsException` or `AccessDeniedException`.

### 9.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ProductView(long id, String name) {
    }

    public record PreviewView(String status, int quantity, int stock) {
    }

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> adminMetrics() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/products/{id}")
    public Mono<ProductView> product(@PathVariable long id) {
        if (id != 1L) {
            return Mono.error(new ProductNotFoundException());
        }
        return Mono.just(new ProductView(1L, "Notebook"));
    }

    @GetMapping("/api/orders/preview")
    public Mono<PreviewView> preview(@RequestParam int quantity) {
        if (quantity < 1) {
            return Mono.error(new InvalidQuantityException());
        }
        if (quantity > 5) {
            return Mono.error(new StockConflictException());
        }
        return Mono.just(new PreviewView("AVAILABLE", quantity, 5));
    }
}
~~~

**Why use `Mono.error`?** In Reactor, an error is a terminal signal of a Publisher. `Mono.error(new InvalidQuantityException())` does not turn the error into a success value; WebFlux can route it to appropriate exception handling.

The controller only performs **read-only** operations to illustrate status codes. Stock data is hard-coded to 5; a real system must check inventory inside an appropriate transaction when confirming an order. A 200 preview **does not guarantee** stock remains available when the user later submits a POST order.

Note:
- `quantity=nope` will fail **input type conversion** before domain logic checks `quantity < 1`.
- `quantity=0` converts to `int` successfully before violating the business rule.
- `quantity=9` is a valid value that conflicts with the illustrative stock.
- `id=99` matches the route and authorization, but no data exists so the domain returns 404.
- Do not put role checks inside the controller to "patch" security; the controller only accepts requests that have already passed the required HTTP rules.

### 9.8. DomainErrorAdvice.java

`src/main/java/demo/DomainErrorAdvice.java`:

~~~java
package demo;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DomainErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail productNotFound(ProductNotFoundException ignored) {
        return problem(
                HttpStatus.NOT_FOUND,
                "Product not found",
                "The requested product does not exist",
                "PRODUCT_NOT_FOUND");
    }

    @ExceptionHandler(InvalidQuantityException.class)
    public ProblemDetail invalidQuantity(InvalidQuantityException ignored) {
        return problem(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "Invalid quantity",
                "Quantity must be at least 1",
                "INVALID_QUANTITY");
    }

    @ExceptionHandler(StockConflictException.class)
    public ProblemDetail stockConflict(StockConflictException ignored) {
        return problem(
                HttpStatus.CONFLICT,
                "Stock conflict",
                "Requested quantity is not available",
                "INSUFFICIENT_STOCK");
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String title,
            String detail,
            String code) {

        ProblemDetail result = ProblemDetail.forStatusAndDetail(status, detail);
        result.setTitle(title);
        result.setProperty("code", code);
        return result;
    }
}
~~~

**Key points to understand:**
- `@RestControllerAdvice` only registers mappings for **domain exceptions** raised in the WebFlux handler/controller flow; do not try to catch `AuthenticationException` from Security filters.
- `ProblemDetail.forStatusAndDetail(...)` sets the appropriate status and detail.
- `setProperty("code", ...)` adds a **machine-readable code** to the JSON; Spring WebFlux/Jackson handles extension properties per the ProblemDetail mechanism.
- `@Order(HIGHEST_PRECEDENCE)` gives this advice high priority over other advice beans, yet because handlers only accept three concrete classes, it does not swallow standard WebFlux errors.
- There is no catch-all `@ExceptionHandler(Exception.class)` that turns every error into 409/500 or hides security errors.
- Public details intentionally **do not contain SQL, sensitive inventory, usernames, tokens, secrets, or stack traces**.

With `spring.webflux.problemdetails.enabled=true`, built-in WebFlux binding errors like `quantity=nope` can be handled by Boot/Spring as 400 per RFC 9457 without forcing them into `InvalidQuantityException`.

## 10. Testing with curl and Comparing Each Layer

In the project directory:

~~~bash
gradle bootRun
~~~

If Gradle Wrapper is present, use `./gradlew bootRun` on macOS/Linux or `gradlew.bat bootRun` on Windows. By default the HTTP server listens on `http://localhost:8080`.

**The following commands are for local demo only**. In real environments, HTTP Basic must go over HTTPS; do not type real passwords into shell history.

~~~bash
# 1. Public, no credentials
curl -i http://localhost:8080/api/public

# 2. Missing credentials on a route requiring authentication
curl -i http://localhost:8080/api/products/1

# 3. Wrong Basic password
curl -i -u reader:wrong http://localhost:8080/api/products/1

# 4. Valid credentials, returns data
curl -i -u reader:readerpass http://localhost:8080/api/products/1

# 5. Authenticated but missing ADMIN role
curl -i -u reader:readerpass http://localhost:8080/api/admin/metrics

# 6. Valid ADMIN role
curl -i -u admin:adminpass http://localhost:8080/api/admin/metrics

# 7. Business: product does not exist
curl -i -u reader:readerpass http://localhost:8080/api/products/99

# 8. Request input wrong type
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=nope'

# 9. Valid data type but violates semantic rule
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=0'

# 10. Business conflict: requested quantity exceeds stock
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=9'

# 11. Success
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=2'
~~~

Expected results table:

| Command | HTTP | Decision layer | Notable content |
| --- | --- | --- | --- |
| 1 | **200 OK** | Public authorization | `public` |
| 2 | **401 Unauthorized** | Authentication entry point | May include `WWW-Authenticate: Basic ...` |
| 3 | **401 Unauthorized** | Authentication failure handler | Wrong password |
| 4 | **200 OK** | Authentication + route + domain | JSON product id=1 |
| 5 | **403 Forbidden** | Authorization | Reader lacks ADMIN |
| 6 | **200 OK** | Authorization for ADMIN | `admin-only` |
| 7 | **404 Not Found** | DomainErrorAdvice | `code=PRODUCT_NOT_FOUND` |
| 8 | **400 Bad Request** | WebFlux request parameter binding | Query cannot be converted to int |
| 9 | **422 Unprocessable Content** | DomainErrorAdvice | `code=INVALID_QUANTITY` |
| 10 | **409 Conflict** | DomainErrorAdvice | `code=INSUFFICIENT_STOCK` |
| 11 | **200 OK** | Successful use case | `status=AVAILABLE` and `quantity=2` |

**Caution:** the table lists expected statuses from the sample code and configuration. Built-in error bodies/headers may vary by version, content negotiation, and entry point. Do not write assertions comparing the entire JSON when the response has changing `instance` or timestamp fields.

### 10.1. Example Domain ProblemDetail

When calling `quantity=9`, a reasonable body:

~~~json
{
  "type": "about:blank",
  "title": "Stock conflict",
  "status": 409,
  "detail": "Requested quantity is not available",
  "instance": "/api/orders/preview",
  "code": "INSUFFICIENT_STOCK"
}
~~~

The `instance` field may be automatically added by the framework per request. Do not require a fixed JSON key order. For 401/403 security errors, the body may be empty because they are handled at the filter layer; status and challenge/headers remain the important HTTP contract.

## 11. Testing WebFlux with WebTestClient

Manual testing helps understand requests; **automated tests** prevent bugs when refactoring security or domain logic. Tests use Spring Security Test to apply the security chain to WebTestClient when binding the application context.

`src/test/java/demo/ErrorResponseTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ErrorResponseTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/products/1")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueMatches("WWW-Authenticate", "Basic.*");
    }

    @Test
    void wrongCredentialsReturn401() {
        client.get().uri("/api/products/1")
                .headers(h -> h.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotCallAdminEndpoint() {
        client.get().uri("/api/admin/metrics")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallAdminEndpoint() {
        client.get().uri("/api/admin/metrics")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void knownProductIsSuccessful() {
        client.get().uri("/api/products/1")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.name").isEqualTo("Notebook");
    }

    @Test
    void missingProductIsDomain404() {
        client.get().uri("/api/products/99")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
                .jsonPath("$.status").isEqualTo(404);
    }

    @Test
    void malformedQuantityIsFramework400() {
        client.get().uri("/api/orders/preview?quantity=nope")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void zeroQuantityIsDomain422() {
        client.get().uri("/api/orders/preview?quantity=0")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_QUANTITY");
    }

    @Test
    void excessQuantityIsDomain409() {
        client.get().uri("/api/orders/preview?quantity=9")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INSUFFICIENT_STOCK");
    }

    @Test
    void validPreviewIs200() {
        client.get().uri("/api/orders/preview?quantity=2")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("AVAILABLE")
                .jsonPath("$.quantity").isEqualTo(2);
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**11 tests** are expected to pass with the stated files/dependencies. This is a code analysis so learners can try it themselves, **not a claim that Gradle was executed here**.

Highlights:
- The 401 missing-credentials test also checks `WWW-Authenticate` to preserve the Basic protocol.
- The 403 test has valid credentials but lacks the role.
- The 404/409/422 tests verify errors emitted by the domain along with a stable `code`, without parsing `detail` as text.
- The 400 test verifies invalid data types are rejected by WebFlux before business validation.
- There are no POST tests because the demo is GET-only; adding write operations requires considering CSRF, HTTP semantics, transactions, and idempotency.

## 12. Why Do "Business" Errors Sometimes Become 500?

Suppose business logic emits:

~~~java
return inventoryRepository.reserve(id, quantity)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Insufficient stock")));
~~~

This is only an illustrative snippet, missing the repository and not a standalone runnable class. Without a matching handler, `IllegalStateException` may fall into generic error handling and return 500. Therefore:
- Do not use generic system exceptions to represent every expected business rule.
- Define clear domain exceptions/error codes.
- Map accurately in `@ExceptionHandler` or a properly scoped error mapper.
- Do not catch all `Exception` types and return 409 automatically, as that hides real programming or infrastructure errors.

### 12.1. Why Not Use onErrorResume to Turn Errors Into 200?

Anti-pattern example:

~~~java
// WRONG: client receives 200 even though placing the order failed.
return orderService.placeOrder(command)
        .onErrorResume(ex -> Mono.just(
                new OrderResult("FAILED", null)));
~~~

Without `@ResponseStatus` or `ResponseEntity`, the controller typically returns 200 with a "FAILED" body. Some clients may treat that as success and skip retry/rollback handling.

Appropriate pattern:

~~~java
return orderService.placeOrder(command)
        .onErrorMap(OutOfStockRepositoryException.class,
                ex -> new StockConflictException());
~~~

This is an illustrative snippet, not a standalone runnable example. It converts **only errors related to business state** into domain exceptions; other errors continue propagating with their true nature.

### 12.2. Risk of Response Already Committed

With WebFlux streaming (`Flux`, Server-Sent Events), the response may have already sent headers/the first bytes. If the Publisher emits an error **after the response is committed**, the server can no longer change status 200 to 409/500. You need to:
- Perform authentication, authorization, and verifiable checks **before** starting the stream.
- Design an in-stream error-reporting protocol if the business operation genuinely streams events.
- Not assume an `@ExceptionHandler` can always build a new HTTP response after headers are sent.
- Avoid buffering the entire stream just to change status if it hurts memory/latency unnecessarily.

## 13. Returning Unified JSON for 401/403: How to Design It?

The demo code keeps security error responses per the HTTP Basic protocol (status/challenge), while domain errors use ProblemDetail. Many APIs want an envelope with `code` for security errors as well; this is achievable, but must be implemented **at the right layer**.

### 13.1. Entry Point and Denied Handler

In Spring Security Reactive:

~~~java
// Conceptual signatures of the two functional interfaces:
// NOT a standalone runnable Java class.

ServerAuthenticationEntryPoint entryPoint =
        (exchange, authenticationException) -> {
            // set 401, WWW-Authenticate if required by scheme,
            // serialize body safely, end with Mono<Void>
            return Mono.empty();
        };

ServerAccessDeniedHandler deniedHandler =
        (exchange, accessDeniedException) -> {
            // set 403 and serialize body safely
            return Mono.empty();
        };
~~~

**Important:** the snippet above only illustrates the callback interface; using `Mono.empty()` directly without setting status/headers is **not a working implementation**. In production, use standard implementations or write a response writer that ensures status, content type, headers, body serialization, and error propagation.

It can be configured:

~~~java
// Inside the constructed SecurityWebFilterChain.
.exceptionHandling(ex -> ex
        .authenticationEntryPoint(customEntryPoint)
        .accessDeniedHandler(customDeniedHandler))
~~~

This is a snippet wiring already-declared beans, not a standalone program. If using HTTP Basic, keep `WWW-Authenticate` when returning 401; if using Bearer, keep the compliant Bearer challenge. Do not just write `application/problem+json` and drop the authentication protocol requirements.

### 13.2. Authentication Failure Handler Is an Additional Point

Some authentication mechanisms have a **dedicated failure handler** in `AuthenticationWebFilter`. Therefore, a custom `ServerAuthenticationEntryPoint` for anonymous authorization **does not automatically guarantee** that every wrong password/token produces the same JSON body. Check:
- Request missing credentials.
- Request with wrong credentials.
- Request with expired token.
- Request authenticated but lacking authority.
- POST request missing CSRF token.

Each case may go through a different entry point, failure handler, access-denied handler, or CSRF handler. A single test for 401 is not enough to prove error envelope consistency.

### 13.3. Should ProblemDetail Be Used for Security Errors?

The RFC 9457 format can be used in 401/403 if an appropriate writer is implemented. However, choosing a format must not alter semantics: 401 stays 401 and the challenge must remain; 403 must not be changed to 401 just to make the frontend open login; 404 hides existence only when policy decides so.

An error code can be `AUTHENTICATION_REQUIRED`, `INVALID_CREDENTIALS`, or `ACCESS_DENIED`, but be careful not to reveal whether a username exists, what specific permissions a token has, or whether a resource exists in another tenant.

## 14. How Clients Should React to Each Status

| HTTP | UI/Mobile | Backend/service client | Retry |
| --- | --- | --- | --- |
| 401 | Prompt login/re-authentication or refresh token properly | Re-issue valid token, alert on credentials configuration | Can try **limited** retries after refresh, no infinite loop |
| 403 | Display insufficient permissions or navigate to allowed area | Do not resend identically like 401 | No unless permissions/policy change |
| 400 | Ask to fix malformed input | Fix serialization/contract | Do not retry same payload |
| 404 | Report not found or no permission to view per policy | Verify ID, namespace, tenant | Do not retry blindly |
| 409 | Ask to refresh data or resolve conflict | Reload latest state, use optimistic locking/idempotency | Only retry after conflict is resolved |
| 422 | Display specific validation/semantic error | Fix payload/domain logic | Do not retry same payload |
| 429 | Notify to wait, reduce request rate | Bounded backoff; respect Retry-After | Yes, with backoff and limit |
| 500 | Display system error and support request ID | Log/trace; appropriate circuit breaker | Depends on idempotency and operation type |
| 503 | Notify temporary outage | Backoff/circuit breaker, check Retry-After | Yes, avoid thundering herd |

Clients must not decide on their own that "403 means token expired" and refresh continuously. Handling of error codes/statuses must be agreed upon in the API contract and covered by frontend/backend integration tests.

### 14.1. Idempotency Matters When Retrying

Retrying an order-creation POST can duplicate transactions if the server processed it but the response was lost. For write operations, design an **idempotency key** or transaction/version control for safe retries; status 409/503/timeout alone does not determine whether retrying is safe.

### 14.2. Do Not Use Natural-Language Messages for Logic

Instead of:

~~~javascript
if (problem.detail.includes("stock")) {
  // ...
}
~~~

rely on a stable code:

~~~javascript
if (response.status === 409 && problem.code === "INSUFFICIENT_STOCK") {
  // Display the insufficient stock scenario.
}
~~~

Both snippets are illustrative JS; in real code, check `Content-Type` and parse JSON safely because security errors or gateway responses do not always have `application/problem+json`.

## 15. Logging, Observability, and Avoiding Information Leakage

A good error contract must be useful for both users and operations without disclosing sensitive data.

### 15.1. What Can Be Logged

- Generated and validated correlation/request ID.
- HTTP method, route template (do not put tokens/passwords in the path).
- HTTP status, safe error code such as `PRODUCT_NOT_FOUND`.
- Internal exception type, processing duration, source subsystem.
- Policy-relevant evidence at an appropriate level, without logging full credentials.
- Aggregated metrics such as counts of 401, 403, 409, 500 per route.

### 15.2. What Should Not Be Returned/Logged

- `Authorization` header, raw passwords, Bearer tokens, session IDs, CSRF tokens.
- SQL queries containing user data, stack traces, internal server details.
- Secret permission/role lists, undisclosed tenant IDs.
- Diagnostics like "this username exists but password is wrong" when user enumeration is a risk.
- Unsanitized upstream exception details.
- Full response bodies of sensitive transactions.

Clients receive a stable error code and a safe generic message; server logs may store stack traces in an access-controlled system when truly needed for debugging. Do not equate 4xx with "no monitoring needed": an unusual spike in 401/403/409 may indicate an attack, a client bug, or system contention.

### 15.3. 401 and 403 in Metrics

If an auth filter returns 401 and the controller does not run, exception counters in `@ControllerAdvice` will **not see** that error. Observe at the appropriate HTTP server/filter/gateway/observability layer to capture all statuses, avoiding dashboards that only measure business errors and conclude there are no auth failures.

## 16. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Returning 403 for wrong password | Client confuses permissions with authentication | Return 401/appropriate challenge |
| Returning 401 when logged-in user lacks role | Frontend needlessly retries login | Usually use 403 |
| Returning 500 for all business errors | Hides true nature and triggers false incident alerts | Map domain errors to appropriate 4xx |
| Domain exception for missing role | Authorization gets mixed into the business error contract | Use authorization/AccessDeniedException or resource policy |
| `@RestControllerAdvice` trying to catch all security filter errors | Does not run when filters reject early | Configure entry point/denied/failure handler |
| Custom 401 dropping `WWW-Authenticate` | Basic/Bearer clients struggle to handle auth properly | Preserve protocol challenge |
| Assuming every 403 is a missing role | CSRF, WAF, deny-all may be the cause | Investigate the originating layer |
| `permitAll` on sensitive route just to see 404 | May accidentally expose new endpoints | Keep deny-by-default and define 404 policy clearly |
| `onErrorResume(Exception.class, ...)` returning 200 | Swallows security/domain/infra errors | Catch only specific errors, keep proper status |
| Error JSON containing stack trace or token | Secret leakage | Sanitized ProblemDetail and safe logging |
| 422 for every invalid input | Mixes parsing failures and domain validation | Clearly define 400 vs 422 in the contract |
| 409 for database timeout | Client mistakes it for conflict | Keep 5xx/503 for temporary infrastructure errors |
| 404 for unauthorized user without checking ownership | Masks real authorization flaws | Check permissions first, choose status per policy |
| Using `block()` in WebFlux to catch errors | Blocks event-loop and breaks reactive model | Use `Mono.error`, `onErrorMap`, handlers |
| Calling `subscribe()` manually to log/write response | Detaches subscription/cancellation and request lifecycle | Compose publishers, use observability framework |
| Retrying 401/403/409 infinitely | Increases load and may duplicate transactions | Classify retries and idempotency |
| Testing only the 200 happy path | 401/403/404/409 mappings can regress | Write negative tests at each boundary |

## 17. Checklist When Designing Errors for a New Endpoint

Before shipping an endpoint to production, answer:

1. **Unauthenticated client:** what is the status and challenge? Which login/refresh flow applies?
2. **Client with wrong credentials:** which failure handler handles it? Are usernames/tokens leaked?
3. **Client lacking permissions:** use 403 or intentionally 404 to hide the resource? Is the rule consistent?
4. **Malformed request structure:** how are invalid JSON, wrong query types, and missing fields returned as 400?
5. **Valid structure but invalid domain logic:** 422 or which status? Is the error code stable?
6. **State conflict:** when do stale versions, insufficient stock, or duplicate transactions return 409?
7. **Resource does not exist:** could 404 leak data from another tenant?
8. **Server/dependency failure:** how are 500/503, traces, and safe messages preserved?
9. **Reactive:** is the error emitted before or after response committed? How are Flux/SSE handled?
10. **Security chain:** which filter handles 401/403, and which controller advice handles domain errors?
11. **CSRF/CORS:** can browser POSTs get 403 due to CSRF? Is preflight resolved?
12. **Client info:** are there standard HTTP statuses and a machine-readable `code`?
13. **Headers:** are `WWW-Authenticate`, `Retry-After`, or caching headers accurate?
14. **Monitoring:** do metrics/traces capture errors from both security filters and business handlers?
15. **Tests:** are there cases for anonymous, wrong credentials, wrong role, invalid input, domain conflict, missing resource, and happy path?

### 17.1. Additional Scenarios to Test

- Undeclared route receives response from `anyExchange().denyAll()`, not default 404.
- Add a resource belonging to another tenant; verify permissions are not bypassed by role-only checks.
- Expired/wrong-issuer/wrong-audience JWT token with proper Resource Server config, not misclassified as domain 404.
- Unparseable JSON request body vs invalid model binding.
- Browser POST missing CSRF token vs missing authentication; do not infer from status alone.
- Domain conflict occurs **after** permission checks, not leaking stock info before auth.
- Service timeout, unreachable database, transaction rollback, committed streaming response.
- Error body contains no stack traces/credentials in production.

## 18. Self-Check Questions

**Question 1.** A user sends no credentials to a protected GET endpoint. What kind of error is this?

> Incomplete authentication; usually HTTP 401, with `WWW-Authenticate` for Basic.

**Question 2.** A user has valid username/password but lacks ROLE_ADMIN. What kind of error is this?

> Authorization. Usually HTTP 403, not 401.

**Question 3.** A user has permission to call the API but requests more than available stock. Should 401 or 403 be returned?

> No. That is a domain conflict; for example return 409 + code `INSUFFICIENT_STOCK`.

**Question 4.** What is the difference between `quantity=nope` and `quantity=0`?

> `nope` fails to parse as an integer: 400 input error. `0` parses successfully but violates the positive rule: e.g., 422 domain error.

**Question 5.** Does 403 always mean a missing role?

> No. CSRF, deny-all, gateways, or other policies can also reject with 403.

**Question 6.** Why might `@RestControllerAdvice` fail to catch 401?

> The request is blocked by a Spring Security WebFilter before reaching the controller; an entry point/failure handler at the security layer is needed.

**Question 7.** What is `ProblemDetail` used for?

> Representing HTTP errors per RFC 9457 with type/title/status/detail/instance and extension properties such as `code`.

**Question 8.** Should we catch every exception and return 409 so the frontend can handle it easily?

> No. Server errors, network errors, and programming errors are not business conflicts.

**Question 9.** Does returning 404 instead of 403 automatically protect a resource?

> No. Real permission checks are still required; 404 is only a response choice per information-disclosure policy.

**Question 10.** Why not retry POST infinitely upon receiving 503/timeout?

> The operation may have already completed before the response was lost. Retries must be bounded and idempotency designed.

**Question 11.** Why does Basic 401 usually need `WWW-Authenticate`?

> It is the HTTP authentication challenge telling the client which mechanism to provide credentials for.

**Question 12.** In reactive streaming, why can't 200 always be changed to 500 when a Flux emits an error?

> Once the response has committed headers/body, the HTTP status can no longer be changed; validate early or use an in-stream error protocol.

## 19. Summary

Authentication errors, authorization errors, and business errors **are not the same category**:

~~~text
Missing/wrong credentials   --> AUTHENTICATION --> usually 401
Logged in, missing perms    --> AUTHORIZATION  --> usually 403
Malformed input structure   --> WEB INPUT      --> usually 400
Resource does not exist     --> DOMAIN/ROUTE   --> 404 (per policy)
Conflicting state           --> DOMAIN         --> 409
Syntactically valid input violating rules
                            --> DOMAIN         --> 422 per contract
System/infra error          --> SYSTEM         --> 5xx
~~~

In **Spring Security Reactive**, use the right extension points: `ServerAuthenticationEntryPoint` or an authentication failure handler for authentication errors; `ServerAccessDeniedHandler` and authorization policies for insufficient-permission errors; `@RestControllerAdvice`/`ProblemDetail` for controller/service domain errors. Use clear HTTP statuses, preserve authentication challenges, provide stable error codes, and test every layer with `WebTestClient`.

### Official References

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Javadoc — `ServerHttpSecurity` (exceptionHandling): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — `HttpBasicServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html
- Spring Security Javadoc — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security Javadoc — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Framework — Error Responses in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Boot — Reactive Web Applications, Problem Details: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110