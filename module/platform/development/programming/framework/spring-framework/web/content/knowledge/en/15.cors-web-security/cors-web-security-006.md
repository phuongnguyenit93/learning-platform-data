# Responsibility boundaries between Spring Web and Spring Security

## 1. Problem: both handle HTTP, yet not the same responsibilities

A REST API written with Spring Boot can receive requests, parse JSON, validate data, authenticate users, check permissions, defend against CSRF, apply CORS, and return errors. Because both libraries participate in HTTP processing, developers easily mistake `@RestController` as automatically securing an endpoint, or think `SecurityFilterChain` knows how to validate DTOs.

**Spring Web (Spring MVC)** is primarily responsible for the *web request/response application layer*: routing to controllers, binding parameters, selecting converters to read/write bodies, invoking handlers, validating inputs per configuration, rendering views or serializing JSON, and handling MVC exceptions.

**Spring Security** is primarily responsible for *protecting requests and methods*: authentication mechanisms, authorization decisions, storing/propagating `SecurityContext`, defending against web attacks such as CSRF, setting security headers, integrating CORS in the right order, and managing sessions/authentication when using the corresponding mechanisms.

The two libraries **work together rather than replacing each other**. For example:
- `@GetMapping("/orders/{id}")` routes in Spring MVC.
- `http.authorizeHttpRequests(...)` checks whether a user may pass through a URL/method in the security filter chain.
- `@PreAuthorize("hasRole('ADMIN')")` protects a method/service when method security is enabled.
- `@Valid @RequestBody CreateOrder` checks DTO structure/constraints; it does not verify whether the user has permission to place an order.
- `@RestControllerAdvice` turns MVC/service errors into JSON, yet does not automatically catch errors blocked by a filter **before** entering DispatcherServlet.

### Learning outcomes

1. Accurately trace the pipeline: Servlet container → security filters → `DispatcherServlet` → controller/service.
2. Distinguish `SecurityFilterChain` from `HandlerMapping`, and `AuthorizationFilter` from `@RequestMapping`.
3. Know which layer owns CORS, CSRF, authentication, authorization, validation, and business invariants.
4. Distinguish HTTP 400, 401, 403, 404, 415, and 500 and where each originates.
5. Build a realistic Spring Boot 3.x Java 17+ application with Spring MVC + Spring Security + method security + MockMvc tests.
6. Avoid pitfalls with multiple filter chains, multiple `@ControllerAdvice`s, switching to stateless bearer tokens, or handling sessions/cookies.

**Scope:** Servlet-based Spring MVC, Java 17+, using Spring Boot 3.3.5 with Spring Security 6.3.x from the matching BOM. Spring WebFlux uses `SecurityWebFilterChain` and a different reactive architecture, so the exact configuration below does not apply directly.

## 2. Where each component sits in the HTTP pipeline

~~~text
Browser / client
      |
      v
Reverse proxy / load balancer / API gateway (if present)
      |
      v
Servlet container (Tomcat, Jetty ...)
      |
      v
Servlet FilterChain
      |
      +--> Filters outside Spring Security, if any
      |
      +--> DelegatingFilterProxy (usually bean "springSecurityFilterChain")
               |
               v
           FilterChainProxy
               |
               +--> selects SecurityFilterChain matching the request
                      |
                      +--> CORS / CSRF / security headers
                      +--> SecurityContext, authentication
                      +--> authorization, exception translation
                      |
                      v
               continues filter chain
      |
      v
DispatcherServlet (Spring MVC)
      |
      +--> HandlerMapping / @RequestMapping
      +--> HandlerAdapter / argument resolvers
      +--> @RequestBody / @RequestParam / validation
      +--> Controller method --> Service/domain/data
      +--> ReturnValueHandler / HttpMessageConverter / ViewResolver
      +--> HandlerExceptionResolver / @ControllerAdvice
      |
      v
HTTP response flows back through filters/proxy
      |
      v
Browser / client
~~~

This diagram is an architectural model and **does not guarantee a strict fixed order for every individual filter**: filter ordering and count depend on configuration/version, dispatcher types, custom filters, multiple chains, and async/error dispatches. The decisive point is that security filters can **halt the request before MVC runs**; only if it proceeds does MVC route to a controller.

### 2.1. `DelegatingFilterProxy`

The Servlet container manages Servlet `Filter`s, while Spring manages beans. `DelegatingFilterProxy` acts as the bridge: from a container filter to a Spring bean, normally named `springSecurityFilterChain`. Spring Boot/Spring Security normally auto-configures this bridge; there is no need to declare `web.xml` manually in modern Boot starters.

### 2.2. `FilterChainProxy` and `SecurityFilterChain`

`FilterChainProxy` manages multiple `SecurityFilterChain`s; **only the first chain matching the request is applied**. One chain can require session/cookie login, another can handle bearer tokens, and another can apply only to APIs; if a path matches no chain, the request may **not be protected by any of those chains**.

Conceptual example:

~~~text
Chain #1: /api/**       -> bearer token, stateless, API policies
Chain #2: /admin/**     -> web login, session, CSRF
Chain #3: /**           -> fallback deny/explicit policies
~~~

This is not runnable configuration. **Chain ordering is part of the security policy**: a `/**` chain placed before a specialized chain can prevent the specialized one from ever being chosen. Do not conflate "matching a chain" with "permitting a URL":
- `securityMatcher("/api/**")` decides **which chain** handles the request.
- `requestMatchers("/api/public/**").permitAll()` inside `authorizeHttpRequests` decides the **authorization rule** once that chain has selected the request.

`permitAll` does not mean skipping CSRF, CORS, security headers, or logging filters; whereas a path excluded completely via `web.ignoring()` can bypass other protective mechanisms. Usually prefer `permitAll` for public resources when you still want security headers/filters applied.

### 2.3. `DispatcherServlet` and `HandlerMapping`

After security filters, `DispatcherServlet` works with `HandlerMapping`/`HandlerAdapter` to locate `@Controller` or `@RestController`. Spring MVC decides:
- Does `GET /api/orders/42` have a handler?
- Where do `@PathVariable("id")`, `@RequestParam`, `@RequestHeader`, and `@RequestBody` pull data from?
- Can the JSON be deserialized?
- What errors do `@Valid`/method validation report?
- Which converter handles the return DTO? Render a view or write a response body?
- Does any `@ExceptionHandler`/`ResponseEntityExceptionHandler` handle exceptions thrown in MVC?

Spring Security does not automatically create a `POST /api/orders` endpoint just because you configured `requestMatchers(HttpMethod.POST, "/api/orders")`. Conversely, an existing MVC handler **does not guarantee** a user is allowed to reach it. Both configurations must be verified together in tests.

## 3. Responsibility matrix and trust boundaries

| Question | Primary component | Do not confuse with |
| --- | --- | --- |
| Which URL invokes a Java method? | Spring MVC `HandlerMapping`, `@RequestMapping` | User's permission to call the method |
| Deserializing JSON into a DTO? | MVC `HttpMessageConverter` and argument resolvers | Authentication |
| Binding and validating form/query/body? | MVC + Jakarta Bean Validation | Permission/ownership |
| Who is calling? | Spring Security authentication, `Authentication` | Client-supplied `userId` field |
| Is the user allowed to act? | Security request rules, method security, and service/domain authorization | CORS allow-origin |
| Stopping forged form POSTs using cookies? | CSRF protection and cookie/session design | `@Valid` on a DTO |
| Can cross-origin browser read response? | CORS policy coordinated by MVC/Security | User authentication/authorization |
| Setting HSTS, frame options, CSP, ...? | Security header configuration, appropriate proxy/web server | JSON validation |
| API body and success status? | MVC controller/return handlers | Security filter deciding every status |
| Missing credentials / insufficient rights errors? | Security `AuthenticationEntryPoint`, `AccessDeniedHandler` | Default `@RestControllerAdvice` |
| Business invariants and resource permissions? | Domain/service + authorization logic | Checking URL prefixes alone |

A request can **pass CORS yet fail with 401**, **authenticate yet fail with 403**, or **be fully authorized yet fail with 400 due to bad JSON**. These are three distinct causes and should not be lumped under "CORS error" or "Spring controller didn't run."

## 4. Authentication differs from Authorization

**Authentication** answers "who is the principal?". In Spring Security, an `Authentication` typically holds the principal, credentials (being/having been processed), authorities, and authenticated state. The mechanism can be username/password, HTTP Basic, form login, bearer token, OAuth2/OIDC, or custom; not every app uses Servlet sessions.

**Authorization** answers "is the principal permitted to do this?". For example `hasRole('ADMIN')`, `hasAuthority('orders:write')`, owner/tenant checks in a domain service, or denying a locked account.

~~~text
Request --> authenticate identity --> check permissions --> business processing
                |                         |
                |                         +-- insufficient rights --> 403 common
                +-- missing/invalid --> 401 common with HTTP Basic/Bearer
~~~

Do not absolutize status codes:
- Unauthenticated HTTP Basic/Bearer requests typically yield **401 Unauthorized** (the historical HTTP name meaning "unauthenticated"), potentially with `WWW-Authenticate`.
- An authenticated principal lacking a role typically gets **403 Forbidden**.
- `CsrfFilter` blocking a POST without a CSRF token can also return **403** despite valid credentials.
- An endpoint intentionally hiding resource existence may return 404 by policy.
- Authentication mechanism, exception handlers, and filter order all affect the actual status.

### 4.1. `SecurityContextHolder` and principal in controllers

Spring Security binds `SecurityContext` to the request/thread execution per configuration; `Authentication` can be accessed via `SecurityContextHolder` or the `@AuthenticationPrincipal` method argument. In MVC, `Principal` or `Authentication` parameters can also be resolved when Security is integrated.

~~~java
@GetMapping("/api/private/me")
public Map<String, String> me(Principal principal) {
    return Map.of("user", principal.getName());
}
~~~

This is an illustrative fragment; it cannot run standalone. Never read `userId` from a request body and trust it as the caller's identity. For multi-tenant APIs, a tenant ID from path/header **must be matched against the principal/permissions**; checking `authenticated()` alone is insufficient to protect another tenant's objects.

### 4.2. Roles and authorities

Spring Security commonly stores roles with the `ROLE_` prefix. Calling `roles("ADMIN")` on `UserDetails` creates the authority `ROLE_ADMIN`. `hasRole('ADMIN')` checks `ROLE_ADMIN`, whereas `hasAuthority('orders:read')` checks that exact authority. Do not casually mix `hasRole('ROLE_ADMIN')` and `hasRole('ADMIN')` without understanding prefixes and method configuration.

Roles suit coarse permission groups; per-resource, ownership, and tenant permissions may require decisions in the service/domain layer. URL-level `hasRole('ADMIN')` does not replace every business rule.

## 5. Request-level authorization and method security

### 5.1. URL rules inside `SecurityFilterChain`

A request authorization configuration can state:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll())
~~~

This is a fragment inside `HttpSecurity`. It decides whether the request qualifies to pass `AuthorizationFilter`; **it does not yet know which controller handles it, whether the DTO is valid, or whether the data belongs to the user**.

Pay attention to matcher ordering: place specific rules first and the `anyRequest()` fallback last. `permitAll` only means no authenticated principal is required for that route; CSRF may still apply to unsafe HTTP methods and CORS still checks origins.

### 5.2. `@EnableMethodSecurity` and `@PreAuthorize`

In Spring Security 6.x, `@PreAuthorize` on methods/services requires `@EnableMethodSecurity` (or equivalent configuration). The Boot security starter **does not enable method-level authorization by default** for every project.

~~~java
@Service
class ReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public Report readReport(long id) {
        return new Report(id, "internal");
    }
}
~~~

This fragment omits declaring/importing `Report`. Meaning: when the method is intercepted by the Spring-managed proxy per configuration, a user lacking ADMIN is rejected even if the URL level only required `authenticated()`.

**AOP proxy boundary:** self-invocation calling from one method to another **within the same object** normally bypasses the proxy, so the target method's `@PreAuthorize` may not run. Never place critical checks only on an internal method and invoke it via `this.method()`. Test real call paths across Spring bean boundaries, or use another appropriate security strategy.

In the reactive stack, annotation/method interception differs in context propagation; this document focuses on Servlet MVC.

### 5.3. Defense in depth

Good design uses multiple layers:
- Gateway/network layer restricts sources or rate if needed; do not treat the gateway as the sole decider.
- Security filter layer blocks unauthenticated requests and enforces coarse URL rules.
- Method security protects service use cases, even when a different controller invokes the same service.
- Domain/repository enforces owner/tenant/data scope, preventing IDOR (Insecure Direct Object Reference).
- Bean Validation validates input structure/quality; it does not replace permissions.

Never use a client-supplied role string in JSON to decide whether updating `isAdmin` is allowed. Authority sources must come from authentication and authorization configuration, not from the request body.

## 6. Validation differs from Security: HTTP 400 is not 401/403

A request:

~~~http
POST /api/private/notes HTTP/1.1
Authorization: Basic <encoded-credentials>
Content-Type: application/json

{"text":""}
~~~

Involves multiple steps:
1. Browser/client sends the HTTP request.
2. Security CORS/CSRF/authentication/authorization may reject before MVC.
3. If Security lets it pass, MVC parses JSON into the DTO.
4. `@Valid` checks `@NotBlank` and may throw `MethodArgumentNotValidException`.
5. Controller/service runs only after the request clears all required boundaries.

Thus the same request can receive:
- **401** if unauthenticated under HTTP Basic.
- **403** if credentials are present yet CSRF token is missing (with CSRF enabled) or permissions are insufficient.
- **400** if it passes security yet the JSON body is malformed or fails validation.
- **201** if valid and the method creates the resource successfully (when designed to return 201).

Do not depend on a fixed precedence among errors on a request that has multiple simultaneous problems (CSRF, auth, invalid body). Test outcomes against the real `SecurityFilterChain`, rather than guessing from controller annotations.

### 6.1. `@Valid` and `@Validated` are not security rules

`@Valid @RequestBody` triggers Bean Validation on the DTO under Spring MVC rules. Spring's `@Validated` is typically used for validation groups/AOP method validation, which is **different from** `@EnableMethodSecurity` and `@PreAuthorize`. Both involve "method validation/security" phrasing, yet solve completely different goals.

A `@NotNull` on `ownerId` only guarantees it is non-null; it **does not prove** the current user owns `ownerId`. Business authorization must compare against the principal and trusted stored data.

## 7. CORS is the intersection between Web and Security

CORS uses `Origin` and response headers so the browser decides whether a cross-origin script may read the response. It **does not authenticate a principal** and **does not stop curl or server-side HTTP clients from calling the API**.

Spring MVC provides `@CrossOrigin` and `WebMvcConfigurer.addCorsMappings`; Spring Security provides `http.cors(...)` to integrate CORS into the security filter chain at the right moment.

~~~text
Cross-origin browser:
  OPTIONS preflight (usually carries no cookies)
     -> CORS policy evaluates Origin, method, request headers
     -> Only if allowed is the actual request sent
     -> Actual request still goes through authentication, CSRF, authorization
     -> Actual response must still carry matching CORS headers
~~~

If the security filter requires session/login before handling OPTIONS, the browser may get 401/403 on preflight and never send the real POST. The fix is configuring CORS early/properly, not removing authentication on the actual POST.

### 7.1. Sample policy

~~~java
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

This is Java without imports; the complete application section below provides full files. `allowCredentials(true)` requires a specific origin instead of `"*"`. The browser can still block cookies due to `SameSite`, `Secure`, and third-party cookie policies. Conversely, simply because CORS allows an origin does not mean every user from that origin has permission to read private resources.

**Do not equate `Access-Control-Allow-Headers` with permission:** allowing `Authorization` to be sent does not mean the token is valid. Never use the Origin header as authentication proof, and never reflect every origin unconditionally.

## 8. CSRF, authentication cookies, and what stateless means

### 8.1. Why does CSRF exist?

When the browser automatically attaches session cookies (or auto-sent credentials like Basic in certain contexts), a malicious website can make the browser issue a state-changing request to the target site. Even if CORS blocks reading the response, the request **may already have been processed by the server** if it was a simple request. CSRF protection requires an extra proof that a malicious page cannot easily supply.

Spring Security enables CSRF protection by default for many Servlet apps; "unsafe" methods such as POST, PUT, PATCH, and DELETE typically require a valid token when CSRF is enabled.

**CORS does not replace CSRF**; neither do `@Valid` or HTTP method mappings.

### 8.2. Why doesn't the demo disable CSRF?

To clearly demonstrate the boundaries, the complete example keeps CSRF **enabled**. A POST with valid username/password yet missing a CSRF token gets 403 before reaching the controller. A POST test with both authentication and `csrf()` then exercises MVC input/response handling.

In a resource server accepting **bearer tokens solely via the Authorization header** and using no browser-attached credentials, the app has a different CSRF model and may intentionally disable CSRF. However, `SessionCreationPolicy.STATELESS` **does not by itself prove** every browser client is immune to CSRF; evaluate the credential mechanism and state-mutation points before disabling it.

### 8.3. Session state and stateless APIs

`SessionCreationPolicy.STATELESS` tells Spring Security not to create/use `HttpSession` to obtain `SecurityContext` under that policy. It does not completely prevent application code from calling `request.getSession(true)`. HTTP Basic can authenticate every request; bearer token APIs normally need no login session. Form-login web UIs normally use sessions and CSRF tokens.

So never copy a "stateless + csrf.disable()" recipe into every Spring Security app as a universal formula. Choose authentication/cookies/CSRF based on your threat model.

## 9. HTTP error paths: who actually produces the response?

| Scenario | Typical handling point | Typical status |
| --- | --- | --- |
| Missing/invalid HTTP Basic credentials on private route | Security authentication + `AuthenticationEntryPoint` | 401 |
| Authenticated principal lacking role in request rule | Security `AccessDeniedHandler` | 403 |
| POST missing CSRF token (CSRF enabled) | Security `CsrfFilter`/access denied processing | 403 |
| Invalid CORS preflight | CORS processor in filter or handler mapping | Often 403 or browser block |
| Valid route, malformed JSON body | Spring MVC converter / `HandlerExceptionResolver` | 400 |
| `@Valid` DTO fails | Spring MVC validation / advice | 400 |
| Media type unsupported by handler | Spring MVC mapping/converter | 415 |
| No matching handler | MVC can return 404 **if request passes Security** | 404 |
| Method protected by `@PreAuthorize` without role | Method security proxy; error bubbles back | Usually 403 |
| Internal exception in service | Handler/advice/container per configuration | 500 |
| Controller returns DTO normally | MVC return value handler/converter | 200/201... per code |

Note: with `anyRequest().denyAll()`, a URL without an MVC handler can still receive 401/403 **before** MVC ever reaches 404. Therefore **never infer whether a controller mapping exists solely from HTTP status**. When debugging, check whether the request cleared the filter chain.

### 9.1. Why doesn't `@RestControllerAdvice` catch every Security exception?

`@RestControllerAdvice` is invoked by MVC through `HandlerExceptionResolver` inside `DispatcherServlet`. Errors occurring **outside MVC** such as 401 from `AuthenticationEntryPoint` or 403 handled in the filter chain will not automatically reach advice.

Spring Security uses:
- `AuthenticationEntryPoint` when initiating/demanding authentication.
- `AccessDeniedHandler` when handling authorization denials.
- `ExceptionTranslationFilter` to translate certain security exceptions into HTTP responses.

If your API requires a unified RFC 9457 error schema, you can customize those handlers to return `ProblemDetail` or share an error serializer, while preserving **accurate 401/403 statuses**, protocol headers like `WWW-Authenticate` when required, and avoiding auth detail leaks. Never write a catch-all `@ExceptionHandler(Exception.class)` returning 400/500 for all security errors.

### 9.2. Method security exceptions can occur inside MVC calls

`@PreAuthorize` on a service called from a controller normally throws `AccessDeniedException` inside the MVC call chain. Depending on `HandlerExceptionResolver`, filter exception translation, and custom advice, the exception can bubble back to the Security filter and become 403. If you write a catch-all advice swallowing `AccessDeniedException` and turning it into 500/200, you break HTTP semantics and logging. Always test real URLs/services with the full filter chain.

## 10. Spring Boot 3.3.5 example: Web + Security with clear boundaries

The demo app features:
- Public GET requiring no login.
- GET `/api/private/me` requiring HTTP Basic and returning the principal name.
- GET `/api/private/reports/{id}` requiring authenticated at URL level and **ADMIN at the service**.
- POST `/api/private/notes` requiring HTTP Basic, a **CSRF token**, and a valid DTO body.
- CORS for one specific frontend origin. OPTIONS preflight is evaluated without cookies.
- MockMvc tests keeping the real Security filter chain, verifying 200/201, 400, 401, 403, and preflight.

No database or persistent login is used. Hard-coded usernames/passwords are for **local demo only** and must never go to production. Code sizes are kept readable while remaining valid Java files when placed in the proper structure.

~~~text
web-security-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/boundary/
    │   ├── BoundaryApplication.java
    │   ├── config/SecurityConfig.java
    │   ├── config/CorsConfig.java
    │   ├── domain/ReportService.java
    │   └── web/BoundaryController.java
    └── test/java/com/example/boundary/
        └── BoundaryIntegrationTest.java
~~~

### 10.1. Gradle dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'web-security-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Starters:
- Web: Servlet MVC, Jackson, controllers/JSON.
- Security: `SecurityFilterChain`, HTTP Basic, CSRF, request authorization.
- Validation: Jakarta Bean Validation provider for `@NotBlank`.
- `spring-security-test`: `httpBasic()`, `csrf()` helpers in MockMvc.

This example intentionally uses Spring Boot 3.3.5 / Security 6.x APIs. If using Boot 4.x / Security 7.x, check the migration guide because DSLs, packages/modules, and deprecated APIs may change; do not mix versions from "current" docs.

### 10.2. Entry point

`src/main/java/com/example/boundary/BoundaryApplication.java`:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

### 10.3. Security filter chain

`src/main/java/com/example/boundary/config/SecurityConfig.java`:

~~~java
package com.example.boundary.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/private/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-user-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("local-admin-password"))
                        .roles("ADMIN")
                        .build());
    }
}
~~~

**Why is each line here?**
- `cors(...)` connects MVC's CORS policy to the security flow so preflight is processed before auth checks.
- `csrf(...)` keeps CSRF validation for unsafe methods, proving POST without a token gets 403 even when logged in properly.
- Public/Private matchers only decide permissions at the request level.
- `anyRequest().denyAll()` is a closed fallback; a nonexistent URL hitting the fallback can receive 401/403 instead of 404.
- `httpBasic(...)` enables authentication at the Security layer; MVC does not manually decode username/password in controllers.
- `@EnableMethodSecurity` is required so `@PreAuthorize` on `ReportService` is actually enforced.
- In-memory `UserDetailsService` and hard-coded passwords are a local demo, not a production user store pattern. BCrypt is used so raw passwords are not stored in `UserDetails`.
- No `formLogin(...)` is configured because the lesson focuses on HTTP Basic. Never put `@PreAuthorize` on controllers pretending method security exists if proxy support is not enabled.

### 10.4. CORS policy defined by Spring Web, integrated by Security

`src/main/java/com/example/boundary/config/CorsConfig.java`:

~~~java
package com.example.boundary.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

This is an explicit policy at the Web layer; Security's `http.cors(...)` ensures requests flow through proper CORS handling inside the security chain. Only origin `https://app.example.test` is permitted; wildcard `"*"` cannot be combined with credentialed CORS. Preflight can be approved **without authentication**, while actual GET/POST still obey `authorizeHttpRequests`, authentication, and per-method CSRF.

The demo sets `allowCredentials(true)` to illustrate a credentialed interface; this **does not automatically make the frontend send cookies**. Cookies also depend on `fetch(credentials)`, SameSite, Secure, and browser policies; an HTTP Basic header is not automatically allowed past authentication just by CORS.

You do not need a second custom `CorsFilter` when this policy is already properly integrated between Security and MVC. If production uses an API gateway handling OPTIONS or multiple `SecurityFilterChain`s, test the exact end-to-end chain.

### 10.5. Service protected by method security

`src/main/java/com/example/boundary/domain/ReportService.java`:

~~~java
package com.example.boundary.domain;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public record Report(long id, String summary) {}

    @PreAuthorize("hasRole('ADMIN')")
    public Report read(long id) {
        return new Report(id, "internal-demo");
    }
}
~~~

Security request rule `/api/private/**.authenticated()` only requires any valid user, whereas `@PreAuthorize` demands authority `ROLE_ADMIN` for **a specific use case**. Because the controller calls the Spring-managed `ReportService` bean through its proxy, method security enforces the extra permission.

Do not call `this.read(id)` from another method **inside the same bean** if you intend to rely on `@PreAuthorize`'s AOP interceptor. In real systems, sensitive use cases also require database-level object ownership/tenant checks.

### 10.6. Web controller: handling HTTP/application input only

`src/main/java/com/example/boundary/web/BoundaryController.java`:

~~~java
package com.example.boundary.web;

import com.example.boundary.domain.ReportService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.security.Principal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class BoundaryController {

    private final ReportService reports;

    public BoundaryController(ReportService reports) {
        this.reports = reports;
    }

    public record NoteInput(@NotBlank String text) {}
    public record NoteReceipt(String text, String actor) {}

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "UP");
    }

    @GetMapping("/private/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/private/reports/{id}")
    public ReportService.Report report(@PathVariable("id") long id) {
        return reports.read(id);
    }

    @PostMapping(path = "/private/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<NoteReceipt> create(
            Principal principal,
            @Valid @RequestBody NoteInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteReceipt(input.text(), principal.getName()));
    }
}
~~~

`@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestBody`, and `@Valid` are all part of Web/MVC + Bean Validation. There is no "manual HTTP Basic check" code in the controller. For private endpoints, `Principal` is supplied once security authentication succeeds.

`NoteInput` validates that text is not blank; it does not prove the user is authorized to create notes for another object. The demo returns a transient receipt without persisting data; production requires a service/persistence layer, length/content constraints, auditing, and transactions. `ReportService.read()` is where method security operates; the controller still serializes the report to JSON via converter.

## 11. MockMvc integration tests with the real SecurityFilterChain

`src/test/java/com/example/boundary/BoundaryIntegrationTest.java`:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BoundaryIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteIsAccessibleWithoutAuthentication() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void privateRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/private/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthenticationSetsPrincipalForMvc() throws Exception {
        mvc.perform(get("/api/private/me")
                        .with(httpBasic("alice", "local-user-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void methodSecurityBlocksNonAdmin() throws Exception {
        mvc.perform(get("/api/private/reports/9")
                        .with(httpBasic("alice", "local-user-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityAllowsAdmin() throws Exception {
        mvc.perform(get("/api/private/reports/9")
                        .with(httpBasic("admin", "local-admin-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.summary").value("internal-demo"));
    }

    @Test
    void authenticatedPostWithoutCsrfStillFails() throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validPostWithAuthenticationAndCsrfReachesController()
            throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.text").value("hello"))
                .andExpect(jsonPath("$.actor").value("alice"));
    }

    @Test
    void invalidDtoIsMvcValidationNotAuthenticationFailure()
            throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void corsPreflightIsProcessedBeforeAuthentication() throws Exception {
        mvc.perform(options("/api/private/notes")
                        .header("Origin", "https://app.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin",
                        "https://app.example.test"))
                .andExpect(header().string("Access-Control-Allow-Credentials",
                        "true"));
    }

    @Test
    void disallowedOriginCannotUsePreflight() throws Exception {
        mvc.perform(options("/api/private/notes")
                        .header("Origin", "https://evil.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Tests isolating responsibilities:**
- `publicRoute...` proves `permitAll`, needing no Basic credentials.
- `privateRoute...` receives 401 before the controller executes.
- `basicAuthentication...` proves Security authenticates and MVC receives the principal.
- `methodSecurityBlocks...` and `methodSecurityAllows...` prove ADMIN role is enforced on the service, not only URLs.
- `authenticatedPostWithoutCsrf...` proves CSRF is a separate boundary from authentication.
- `validPost...` proves only with auth + CSRF does MVC read/validate the body and return 201.
- `invalidDto...` with full auth/CSRF returns 400 from Web/validation.
- `corsPreflight...` proves OPTIONS needs no username/password to evaluate the CORS policy.
- `disallowedOrigin...` checks the allowlist without echoing arbitrary Origins.

MockMvc has Spring Security test helpers thanks to `spring-security-test`. Never use `@AutoConfigureMockMvc(addFilters=false)` for auth/CSRF tests: doing so bypasses the filter chain and turns 401/403 into wrong results. Never test controllers solely via direct Java method calls when the goal is verifying HTTP security boundaries.

If Spring Security or validation is customized in a real project, statuses/bodies may vary with the entry point/advice. These tests describe the demo app under its current setup. To verify browser cookies, SameSite, reverse proxies, and preflight caching, add end-to-end HTTP/browser tests.

## 12. Running the app via curl: proving each layer

Generate a Gradle wrapper compatible with Java 17/Spring Boot 3.3 if the project does not already have one. Once available:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows use `.\gradlew.bat test` and `.\gradlew.bat bootRun`. Run these in an appropriate terminal/process; `bootRun` typically keeps the server running on port 8080.

### 12.1. Public GET

~~~bash
curl -i 'http://localhost:8080/api/public/ping'
~~~

Expected status 200, body:

~~~json
{"status":"UP"}
~~~

### 12.2. Private GET without credentials

~~~bash
curl -i 'http://localhost:8080/api/private/me'
~~~

Expected HTTP **401** (potentially with `WWW-Authenticate`). Not a missing controller: Security requires authentication for the request.

### 12.3. Private GET with Basic credentials

~~~bash
curl -i -u alice:local-user-password \
  'http://localhost:8080/api/private/me'
~~~

Expected HTTP **200**:

~~~json
{"user":"alice"}
~~~

`curl -u` sends HTTP Basic credentials in the Authorization header after encoding, which is **not encrypted in transit over plain HTTP**. The local demo uses HTTP for convenience; production must use HTTPS and never store demo passwords in Git/public config.

### 12.4. Missing ADMIN role at the service

~~~bash
curl -i -u alice:local-user-password \
  'http://localhost:8080/api/private/reports/9'
~~~

Expected **403 Forbidden**, even though the request was authenticated in `SecurityFilterChain`. That decision comes from `@PreAuthorize` on `ReportService.read`, not from `@GetMapping`.

~~~bash
curl -i -u admin:local-admin-password \
  'http://localhost:8080/api/private/reports/9'
~~~

Expected **200**:

~~~json
{"id":9,"summary":"internal-demo"}
~~~

### 12.5. POST with Basic auth yet missing CSRF

~~~bash
curl -i -u alice:local-user-password \
  -X POST 'http://localhost:8080/api/private/notes' \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}'
~~~

Expected **403** due to CSRF since the demo configuration retains token validation. Do not conclude the password is wrong from this status alone. To test success in integration tests, use `SecurityMockMvcRequestPostProcessors.csrf()` as in section 11.

With a real HTTP client, a valid POST must obtain a token from the `CsrfTokenRepository` mechanism and send the matching cookie/header/parameter per the app. This demo does not expose a CSRF token-issuing endpoint, so **do not invent a token or fake a successful curl command**. If a cookie-based SPA needs one, consider `CookieCsrfTokenRepository` and design a version-appropriate endpoint/CSRF token request handler while defending against XSS.

### 12.6. OPTIONS preflight without Basic credentials

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/private/notes' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

The demo's CORS config permits the origin, method, and headers; expect 2xx status and `Access-Control-Allow-Origin: https://app.example.test` (typically 200). **This does not mean the browser has been authorized to POST**: the actual request still needs authentication, CSRF, and authorization.

A preflight from `https://evil.example.test` is rejected by CORS (typically 403) in the app. curl does not execute browser CORS enforcement itself; it merely sends the exact HTTP request you specify.

## 13. Spring Security and CORS boundaries with multiple chains

### 13.1. Multiple SecurityFilterChains

When building an app with both a form-login web UI and a bearer-token REST API, multiple chains are often required. Conceptual design example:

~~~text
@Order(1): /api/**    -> resource server, bearer auth, API authorization
@Order(2): /**        -> form login, session, CSRF, web pages
~~~

Do not copy this directly as runnable code; you need OAuth2 Resource Server/JWT dependencies, issuer/audience validation, session/CSRF policies, error handlers, and explicit matcher ordering. Design so there are **no gaps** between chains and avoid placing a catch-all chain ahead of specialized chains.

### 13.2. `securityMatcher` vs. `requestMatchers`

~~~java
// Conceptual fragment, not a full configuration file:
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

`securityMatcher` decides whether this chain handles the request; `requestMatchers` decides permissions inside the chain. If you only have a chain scoped to `/api/**` without a fallback chain for `/admin/**`, admin routes may fall outside that `SecurityFilterChain`. **Inspect `FilterChainProxy` and chain-matching logs/debug output** in critical integration tests.

### 13.3. MVC matchers and Security matchers must stay consistent

Spring MVC has semantics for URL patterns, path variables, and context/servlet paths; Spring Security uses corresponding `RequestMatcher`s per config. Mismatched patterns can leave unprotected gaps or cause false denials, especially with custom servlet paths, encoded paths, reverse proxy rewrites, trailing slashes, or matrix variables.

Do not rely on hand-rolled string-prefix checks like `request.getRequestURI().startsWith("/admin")` for authorization. Use proper Spring Security matchers and test encoding/normalization if the app handles complex URL inputs.

## 14. Security headers and infrastructure responsibilities

Spring Security emits security response headers (such as cache-control for protected responses, `X-Content-Type-Options`, `X-Frame-Options`, and HSTS over HTTPS when configured). Spring MVC handles content type/response serialization; reverse proxies or web servers may set TLS, HSTS, Content Security Policy, and other headers.

| Need | Typically responsible component | Note |
| --- | --- | --- |
| HTTPS termination | Proxy/load balancer/container | Forwarded headers must be handled trustworthily |
| HSTS | Spring Security/proxy | Meaningful only over HTTPS when host policy aligns |
| CSP for HTML/JS | Security headers or proxy | Needs frontend-specific policy; avoid reckless script wildcards |
| CORS allowlist | MVC `CorsConfiguration` + Security CORS integration | Does not replace authentication |
| Session cookie flags | Container/Spring Boot/Security/proxy | `Secure`, `HttpOnly`, `SameSite` are separate from CORS |
| Error serialization | MVC `ProblemDetail`/advice; Security entry point/denied handler | Schema consistency requires coordinating both paths |
| Rate limiting | Gateway/filter/dedicated service | Spring Security core does not replace a rate limiter by default |
| Data/tenant authorization | Method security + domain/repository | URL roles alone are insufficient |

Do not assume every security header is enabled by default and suitable for every product. In real deployments, inspect actual responses via browser/HTTP and configure security policies deliberately.

## 15. Common mistakes and diagnostics

| Symptom | Cause | How to verify |
| --- | --- | --- |
| Sees `@RestController` and assumes route is secure | Controller annotations are not authentication/authorization | Check `SecurityFilterChain` and negative tests |
| Security permits `/api/**` yet URL returns 404 | Only security matcher exists, MVC handler does not | Check MVC mappings |
| Controller breakpoint never hits, HTTP 401 | Filter chain requires authentication before MVC | Inspect Basic/bearer entry point and filter chain |
| Logged in yet POST gets 403 | Missing CSRF or permission | Check CSRF token and AccessDeniedHandler |
| HTTP 403 reading report despite `authenticated()` | `@PreAuthorize` requires ADMIN role | Check service method proxy/authorities |
| `@PreAuthorize` has no effect | `@EnableMethodSecurity` missing or self-invocation | Check bean/proxy and integration tests |
| Basic user has `ADMIN` yet is still blocked | Confusing role vs. authority/prefix | Check `ROLE_ADMIN` and `hasRole('ADMIN')` |
| CORS preflight gets 401 | Security demands auth before CORS handling | `http.cors(...)`, source policy, and chain order |
| OPTIONS 200 yet POST still 403 | CORS only permits browser to send; actual lacks auth/CSRF | Inspect actual request filters |
| Browser reports CORS yet backend logs 500 | Error response lacks allow-origin | Check status/logs and CORS on error paths |
| Cookie not sent even though CORS allows | SameSite/Secure/domain/third-party policy | Browser devtools and fetch credentials |
| `@ControllerAdvice` does not catch Basic auth 401 | Error handled in filter before DispatcherServlet | Create `AuthenticationEntryPoint` if custom JSON is needed |
| Catch-all advice turns AccessDeniedException into 500 | Advice swallows security exception inside MVC | Preserve semantics, test full filter chain |
| Unknown route returns 403 instead of 404 | `anyRequest().denyAll()` blocks before MVC | Check fallback policy |
| Security tests always return 200 | Tests disable filters via `addFilters=false` | Keep filter chain active, use `spring-security-test` |
| MVC test misses 400 validation | Missing validation provider/`@Valid` or blocked by Security first | Add starter and verify auth/CSRF first |
| Two security filters behave oddly | Filter registered both manually and via SecurityFilterChain | Check double registration/filter order |
| Multiple security chains, path slips through | Wrong `securityMatcher` or `@Order` | Test every route + fallback |
| Stateless yet JSESSIONID still appears | Another component creates a session, not just SecurityContext | Trace `getSession(true)`, filters/MVC |
| CORS allow-origin `*` with credentials=true | Browsers reject wildcard credentialed responses | Use an exact allowlist |
| Client sends `userId` in JSON and edits another's order | Missing object-level authorization | Compare principal against entity owner/tenant in service |

## 16. Which API to use when? Decision tree

~~~text
What needs to be handled?
|
+-- Route HTTP URL/method?                  -> Spring MVC @RequestMapping
+-- Read query/path/header/JSON?            -> MVC argument resolvers/converters
+-- Validate JSON/form DTO?                 -> Jakarta Bean Validation @Valid
+-- Serialize return value to JSON?         -> @RestController / HttpMessageConverter
|
+-- Identify user/client?                   -> Spring Security Authentication
+-- May user call route?                    -> authorizeHttpRequests
+-- May user call service method?           -> @EnableMethodSecurity + @PreAuthorize
+-- Does user own resource?                 -> domain authorization with principal
+-- Prevent forged cookie-auth POSTs?       -> CSRF policy
+-- Browser cross-origin CORS?              -> MVC CorsConfiguration + Security cors
+-- Protect session/cookies/sec headers?    -> Security/container/proxy
|
+-- Produce error JSON?
      +-- MVC parse/validation/domain exc   -> @RestControllerAdvice
      +-- 401/403 from filters              -> AuthenticationEntryPoint
                                               / AccessDeniedHandler
~~~

**Sensible design order:** determine authentication mechanism and threat model → define request-level and method/domain authorization → define CSRF/CORS/session/header policies → define Web DTOs/validation/responses → test end-to-end across filter chain and MVC. Do not build controllers "just to get them running" and later try to bolt on security with a few URL regexes.

## 17. Implementation and review checklist

1. Verify exact Spring Boot/Spring Framework/Security versions; use matching APIs/docs.
2. Trace the request path from Servlet container through `DelegatingFilterProxy`/`FilterChainProxy` to `DispatcherServlet`.
3. Define one or more `SecurityFilterChain`s with clear matchers and fallback; test chain ordering.
4. Choose an authentication method fitting the client; avoid hard-coded credentials in production.
5. Enable request authorization, and `@EnableMethodSecurity` if using `@PreAuthorize`.
6. Enforce domain ownership/tenant/data scope; prevent IDOR even when roles are valid.
7. Decide where CSRF is enabled/retained based on cookie/credential models; never disable simply because it is REST.
8. Configure the CORS allowlist in one clear source, integrating Security ahead of authentication for preflight.
9. Design request DTOs + Bean Validation separately from authentication/authorization.
10. Standardize 400 from MVC and 401/403 from Security without breaking headers/protocol semantics.
11. Keep the real filter chain active in MockMvc tests; test public/private, roles, method security, CSRF, CORS, and invalid DTOs.
12. Verify cookies/TLS/forwarded headers, response headers, and error paths through E2E/proxy testing.
13. Avoid self-invocation with method security and duplicate filter registration.
14. Check application logs and security diagnostics safely; never log passwords/tokens/cookies.
15. Never assume Spring Security routes MVC or that MVC secures endpoints by itself.

### Self-check questions

**1.** A Spring MVC controller receives invalid JSON and the user is unauthenticated—will HTTP always be 400?

**Answer:** No. Security filters can stop the request before MVC reads the JSON; on an HTTP Basic private route, the response can be 401. To test JSON validation errors, send valid auth/CSRF.

**2.** Why does `@GetMapping("/admin")` not guarantee only admins can enter?

**Answer:** `@GetMapping` only performs routing. Request/method/domain authorization must be configured separately.

**3.** Does `permitAll()` disable CSRF/CORS?

**Answer:** No. It only allows the request past that authorization rule; other protective filters continue to apply.

**4.** Why does a `@PreAuthorize` method still run when called via `this.method()`?

**Answer:** Spring AOP proxies normally do not intercept self-invocation. Call across Spring bean boundaries and test accordingly.

**5.** Does an approved CORS preflight mean the POST will succeed?

**Answer:** No. The actual POST must still pass authentication, CSRF, authorization, MVC validation, and business logic.

**6.** Who normally generates HTTP 401 for an unauthenticated Basic request?

**Answer:** Spring Security's authentication entry point, not an MVC controller `@ExceptionHandler`.

**7.** Why can a nonexistent route return 403 instead of 404?

**Answer:** `anyRequest().denyAll()` in the filter chain can block the request before it ever reaches `DispatcherServlet`.

**8.** Does `@Valid` replace `@PreAuthorize`?

**Answer:** No. `@Valid` validates data; `@PreAuthorize` enforces method invocation permissions.

## 18. Official references

- [Spring Security 6.3 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, and filter ordering.
- [Spring Security 6.3 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `requestMatchers`, and matcher scope.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, AOP proxies, and other annotations.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection in Servlet applications and SPA considerations.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflight before authentication, integration with Spring MVC.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter): `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`.
- [Spring Framework — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): handler mapping, adapters, views, and exception resolution.
- [Spring Framework — Spring MVC Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): mappings, argument resolvers, response bodies.
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, method validation, and error types.
- [Spring Boot 3.3 — Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): auto-configuration and how applications customize `SecurityFilterChain`.

**Key takeaway:** Spring Web handles **how requests are mapped, read, validated, and responded to**; Spring Security handles **who is calling, what they are allowed to do, and how requests are protected**. CORS is an intersection, not authentication; CSRF and authorization are distinct boundaries. Only testing across **filter chain + DispatcherServlet + service** reflects the true behavior and safety of an endpoint.
