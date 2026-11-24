# What is Spring Security Reactive and what problem does it solve in WebFlux applications?

## 1. Learning Objectives

After this lesson, you will be able to:
- Explain what Spring Security Reactive is and why a Spring WebFlux application needs a security layer compatible with the reactive model.
- Distinguish **authentication**, **authorization**, and storing/propagating security information across a Reactor pipeline.
- Describe the path of an HTTP request through **SecurityWebFilterChain** before reaching a WebFlux handler.
- Configure an API with public endpoints, authenticated endpoints, and endpoints restricted to the ADMIN role; accurately predict HTTP 200, 401, and 403 status codes.
- Recognize the limitations of the learning example and key considerations when applying it with JWT, sessions, CSRF, CORS, and reactive data sources.

## 2. Context: WebFlux already handles HTTP, so why is Security still needed?

**Spring WebFlux** is Spring's web stack that supports asynchronous processing and reactive types such as \`Mono<T>\` (0–1 result) and \`Flux<T>\` (0–n results). A request may pass through multiple asynchronous stages; work does not necessarily stay on the same thread.

WebFlux is responsible for routing, invoking controllers/handlers, converting data, and producing HTTP responses. Determining **who a caller is, what they are allowed to do, and which resources they can access** is a security policy that must be enforced consistently. If you manually write account checks in every controller, the application can easily miss endpoints, duplicate logic, become hard to test, and handle authentication errors inconsistently.

**Spring Security Reactive** is Spring Security's security capability for WebFlux. It provides mechanisms to identify callers, check access permissions, and integrate with reactive processing pipelines via **WebFilter**s, where the central configuration is typically one or more \`SecurityWebFilterChain\` beans.

The problems it solves go beyond just "adding a login screen":

| Problem in a WebFlux API | How Spring Security Reactive helps |
| --- | --- |
| Unauthenticated callers invoke APIs containing private data | Requires authentication before granting access |
| Authenticated users invoke actions beyond their permissions | Evaluates permissions by path, HTTP method, role/authority, or method |
| Each controller checks tokens manually and returns different errors | Centralizes policy in the security filter chain and standard authentication mechanisms |
| Reactive execution switches threads between steps | Provides \`ReactiveSecurityContextHolder\` backed by **Reactor Context** |
| Application needs HTTP Basic, OAuth2/JWT, or OAuth2 Login | Offers corresponding built-in components, depending on dependencies and configuration |
| Common web security protections are required | Supports configuring security headers, CSRF, CORS integration, and security context management |

**Important boundary:** Spring Security **does not automatically guarantee** that all passwords are stored securely, all DB queries are non-blocking, all business logic checks data ownership, or the system is automatically immune to every type of attack. Actual policies and components still must be designed properly.

## 3. Three Core Concepts

### 3.1. Authentication — verifying "who are you?"

Authentication verifies proof of identity, such as a username/password pair, HTTP Basic credentials, or a valid JWT. The result is an \`Authentication\` object containing the principal (the caller), authentication status, and authorities.

For example: a request sends \`Authorization: Basic ...\`. Spring Security decodes the HTTP Basic credentials, verifies them using the configured mechanism, and creates the authentication details for the request. HTTP Basic is only a convenient mechanism for illustration; real credentials must be protected by HTTPS.

### 3.2. Authorization — determining "what are you allowed to do?"

Once the caller's identity is known, Spring Security compares their permissions against the access policy. For example:
- \`/public\`: accessible to everyone.
- \`/profile\`: requires authentication.
- \`/admin\`: requires the \`ADMIN\` role.

By default convention, \`hasRole("ADMIN")\` checks for the \`ROLE_ADMIN\` authority; whereas \`hasAuthority("SCOPE_read")\` checks for the exact \`SCOPE_read\` authority. With JWT, how claims are converted into authorities must be configured or properly understood according to the mechanism in use.

### 3.3. SecurityContext — security information for the processing flow

\`SecurityContext\` holds the \`Authentication\`. In Spring MVC/Servlet, many examples commonly use \`SecurityContextHolder\` with a \`ThreadLocal\`-based strategy. In WebFlux, you must not assume a request always stays on one thread.

Spring Security Reactive uses **Reactor Context** to attach security information to the reactive processing chain. It is accessed via \`ReactiveSecurityContextHolder.getContext()\`, which returns \`Mono<SecurityContext>\`. Context is propagated across a properly connected Reactor pipeline, even when switching threads; it does not automatically propagate into tasks detached from the pipeline or arbitrary blocking libraries.

## 4. How is an HTTP request protected?

High-level flow:

1. An HTTP request arrives at the server running WebFlux.
2. Security \`WebFilter\` selects the matching **SecurityWebFilterChain** for the request. An application may have multiple chains with different matchers and precedence orders.
3. Security filters apply the relevant steps such as reading credentials/tokens, checking authentication, establishing the security context, or applying other protections.
4. The authorization component evaluates the request against declared rules.
5. If permitted, the request continues to \`DispatcherHandler\`, the controller/functional handler, and the service.
6. The handler returns a \`Mono\`/\`Flux\`; WebFlux completes the response. If the request fails security requirements, processing can terminate early with the corresponding HTTP error.

~~~text
Client
  |
  v
WebFlux HTTP server
  |
  v
Security WebFilter chain
  |-- Authenticate / create Authentication when needed
  |-- Reactor SecurityContext
  |-- Check permissions per request
  |
  +-- Unauthenticated, resource requires login --> 401 Unauthorized
  +-- Authenticated but insufficient permissions --> 403 Forbidden
  |
  v
WebFlux handler/controller --> reactive service --> HTTP response
~~~

This is a conceptual diagram to understand responsibilities; actual filter order also depends on configuration. \`SecurityWebFilterChain\` belongs to **WebFlux**, unlike the Servlet-based \`SecurityFilterChain\` and \`OncePerRequestFilter\` commonly seen in Spring MVC. Do not substitute one for the other.

## 5. Runnable Example: WebFlux API with public, private, and admin endpoints

This example uses **Java 17**, **Spring Boot 3.3.13**, and **Gradle** to provide a reproducible set of versions for learning. This is an illustrative version; real-world production projects should choose a supported Spring Boot branch and check for security updates. The example only includes HTTP GET endpoints to focus on authentication and authorization.

Structure:

~~~text
webflux-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── GreetingController.java
~~~

**\`settings.gradle\`**

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

**\`build.gradle\`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

\`spring-boot-starter-webflux\` provides the reactive web stack; \`spring-boot-starter-security\` brings Spring Security and the appropriate security integration into the application. There is no need to add \`spring-boot-starter-web\` for this example.

**\`src/main/java/demo/DemoApplication.java\`**

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

**\`src/main/java/demo/GreetingController.java\`**

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("Noi dung cong khai");
    }

    @GetMapping("/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("Noi dung can dang nhap");
    }

    @GetMapping("/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("Khu vuc quan tri");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "Xin chao, "
                        + context.getAuthentication().getName());
    }
}
~~~

\`/me\` reads the identity from the request's **reactive security context**. It does not read \`ThreadLocal\`, and is only accessible to authenticated callers in the configuration below. The response strings in the code intentionally use ASCII so that \`curl\` output is easy to compare verbatim; the explanation uses full Vietnamese diacritics.

**\`src/main/java/demo/SecurityConfig.java\`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Meaning of each rule:**
- \`permitAll()\`: allows \`GET /public\` even without logging in; the request still goes through the security filter chain.
- \`hasRole("ADMIN")\`: \`/admin\` requires the \`ROLE_ADMIN\` authority. The \`reader\` account does not have this authority.
- \`anyExchange().authenticated()\`: the remaining endpoints, including \`/private\` and \`/me\`, require authentication.
- \`httpBasic(...)\`: enables HTTP Basic authentication so \`curl -u\` can be used in the lesson.
- \`formLogin(...disable)\`: disables the HTML login screen since the example is an API.
- \`MapReactiveUserDetailsService\`: an **in-memory** user store for the demo, not representative of a production database.

**Warning regarding \`{noop}\`:** It instructs the password encoder not to hash passwords, solely to help verify the flow locally. Do not use hard-coded passwords or \`{noop}\` in real production systems. Use a strong password encoder (such as BCrypt/Argon2 with appropriate configuration), proper secrets management, and a secure account store. The example also keeps the default CSRF configuration; all endpoints are GET and perform no state-changing operations.

### Run and observe the results

From the project directory, use an installed Gradle (or \`./gradlew\` if the project has the Gradle Wrapper):

~~~bash
gradle bootRun
~~~

Open another terminal and run:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u reader:demo123 http://localhost:8080/private
curl -i -u reader:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/admin
curl -i -u reader:demo123 http://localhost:8080/me
~~~

Expected results for the commands above, in order:

| Call | HTTP status | Body/meaning |
| --- | --- | --- |
| \`GET /public\`, no credentials | **200 OK** | \`Noi dung cong khai\` |
| \`GET /private\`, no credentials | **401 Unauthorized** | Login required; HTTP Basic may return \`WWW-Authenticate\` |
| \`GET /private\`, \`reader\` | **200 OK** | \`Noi dung can dang nhap\` |
| \`GET /admin\`, \`reader\` | **403 Forbidden** | Authenticated but lacks the ADMIN role |
| \`GET /admin\`, \`admin\` | **200 OK** | \`Khu vuc quan tri\` |
| \`GET /me\`, \`reader\` | **200 OK** | \`Xin chao, reader\` |

Framework-generated headers and error bodies may vary by version/configuration; the table only specifies the status codes and bodies for successful requests. You can also test \`curl -i -u reader:sai-mat-khau http://localhost:8080/private\`: authentication must be rejected, typically with **401**.

**Distinguishing 401 and 403:** 401 generally means valid authentication has not been provided to access a protected resource (missing or invalid credentials). 403 means access is forbidden, typically when the caller is authenticated but lacks sufficient permissions. This is the expected behavior of the demo configuration; error handling can be customized.

### Why is this example still "reactive"?

The controller returns \`Mono<String>\` and the user details component is \`MapReactiveUserDetailsService\`. Spring Security keeps the login information inside the request's Reactor pipeline so downstream handlers can read it via \`ReactiveSecurityContextHolder\`.

That **does not** mean every piece of code in the application is automatically non-blocking. For example, calling blocking JDBC, \`Thread.sleep\`, \`block()\`, or a synchronous SDK on the event loop can still starve concurrency. When connecting to an external user store, choose an appropriate API/driver and offload blocking I/O off the event loop when truly necessary.

## 6. A Deeper Look at Component Responsibilities

| Component | Primary responsibility |
| --- | --- |
| \`ServerHttpSecurity\` | DSL for describing HTTP security policies for WebFlux |
| \`SecurityWebFilterChain\` | Set of security filters applied to a group of requests |
| \`Authentication\` | Identity/principal along with authorities and authentication status |
| \`ReactiveAuthenticationManager\` | Interface that performs authentication reactively, returning \`Mono<Authentication>\` |
| \`ReactiveUserDetailsService\` | Interface for looking up users reactively; \`MapReactiveUserDetailsService\` is an in-memory implementation |
| \`ReactiveSecurityContextHolder\` | Reads/writes \`SecurityContext\` from Reactor Context |
| \`ServerSecurityContextRepository\` | Strategy-dependent component to load/save security context, e.g., via WebSession |
| \`@EnableReactiveMethodSecurity\` | Enables method-level access control when required |

Not every application needs to implement every interface in the table itself. For instance, a resource server verifying JWTs usually uses a token decoding/validation mechanism and converts claims into authorities instead of looking up passwords via \`ReactiveUserDetailsService\`.

### Why is ThreadLocal-based \`SecurityContextHolder\` error-prone in WebFlux?

A common misconception is reading \`SecurityContextHolder.getContext()\` at an arbitrary point and assuming it will always hold the request's user. In a reactive pipeline, callbacks may execute on a different thread or at a different time. Read the context within the pipeline via \`ReactiveSecurityContextHolder\`, like in the \`/me\` endpoint above, and avoid calling \`subscribe()\` manually to detach work while assuming the request context will still be available.

When access control is needed at the service layer, do not rely solely on controllers; consider \`@EnableReactiveMethodSecurity\` with \`@PreAuthorize\` on appropriate reactive methods. Endpoint authorization and business-layer authorization are two complementary layers, especially when a service is invoked from multiple entry points.

## 7. Applying to a Real-World API

Suppose a WebFlux application serves orders:
- \`GET /products\`: may be public if business rules permit.
- \`GET /orders/me\`: requires authentication.
- \`GET /admin/orders\`: restricted to administrative roles.
- \`GET /orders/{id}\`: beyond authentication, must check whether that order belongs to the caller.

The \`authenticated()\` rule only answers "are you logged in?"; it **does not** automatically check ownership of individual orders. If any authenticated user can read \`/orders/{id}\`, an unauthorized resource access vulnerability (IDOR/BOLA) can occur. Permissions must be checked per **business object** at the service layer or through an appropriate authorization mechanism.

For systems using JWT, a common approach is:
1. The application acts as an **OAuth2 Resource Server** with the corresponding dependency.
2. Configure the issuer/JWK and verification steps for signature, expiration, and issuer/audience as required.
3. Define clearly how claims/scopes are mapped into authorities.
4. Use \`SecurityWebFilterChain\` to require those authorities per endpoint; still enforce data ownership checks in the service.

This is an extension path, **not** an implication that merely adding a dependency or manually inspecting a claim is already secure. JWT can help authenticate requests, but object-level authorization, token lifecycle management, and revocation/session policies must be designed separately.

## 8. Security and Operational Points to Remember

**CSRF:** Spring Security includes CSRF protection in many web configurations. For applications using sessions/cookies or credential mechanisms automatically sent by browsers, state-changing requests require a proper CSRF strategy. Do not disable CSRF just because "this is a REST API." Whether it can be disabled for a truly stateless API that only accepts Bearer tokens must be based on a concrete threat model.

**CORS:** CORS specifies which web origins are allowed to read responses from a browser; it **does not replace authentication/authorization**. CORS must be configured properly with the security chain and handle preflight requests when the API is called cross-origin.

**HTTPS and credentials:** Basic sends credentials Base64-encoded, not encrypted; HTTPS is mandatory outside trusted test environments. Do not log passwords, tokens, or the Authorization header. Do not place production passwords in source code.

**Password storage:** Store passwords using an appropriate hash; use a standard password encoder. Do not use \`{noop}\` outside demos. Implement brute-force protection, session/token management, and monitoring as needed.

**Reactive I/O:** Security does not fix a blocking DB/HTTP client. For account lookups or token introspection, prefer reactive integrations; if a blocking API must be used, isolate it so it does not occupy the event loop. Switching to another scheduler also does not turn the underlying I/O itself into non-blocking I/O.

**Defaults and rule ordering:** Always define a rule covering unmatched requests (\`anyExchange()\`); avoid overly broad \`permitAll()\` declarations. Matcher order matters: a broad rule placed first can prevent more specific rules below it from taking effect as intended. When multiple \`SecurityWebFilterChain\` beans exist, pay attention to matchers and \`@Order\`.

**Policy testing:** With \`WebTestClient\`, test at least three groups: anonymous users receive 401 on protected endpoints; authorized users receive 2xx; users with the wrong role receive 403. Also test authentication failures and specific data-access permissions. Do not test only "login succeeded."

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence / How to handle |
| --- | --- |
| Bringing \`HttpSecurity\` / Servlet \`SecurityFilterChain\` configs into WebFlux | Use \`ServerHttpSecurity\` and \`SecurityWebFilterChain\` for the reactive web stack |
| Assuming \`authenticated()\` means "allowed to view all data" | Add role/authority rules and check permissions on each individual object |
| Using ThreadLocal \`SecurityContextHolder\` as in MVC | Use \`ReactiveSecurityContextHolder\` inside the reactive pipeline |
| Calling \`subscribe()\` or \`block()\` arbitrarily | Maintain the \`Mono\`/\`Flux\` chain; only move blocking code to an appropriate place when unavoidable |
| Confusing \`hasRole("ADMIN")\` with \`hasAuthority("ADMIN")\` | Remember roles are typically mapped to \`ROLE_ADMIN\`; authority checks the exact declared string |
| Checking only HTTP 200 and ignoring unauthorized/forbidden cases | Write tests for 401, 403, and object ownership checks |
| Disabling CSRF or opening CORS \`*\` without considering how browsers send credentials | Design around the actual authentication flow and the principle of least privilege |
| Using \`{noop}\`, default passwords, or logging tokens | Use demo credentials locally only; replace with proper production protections and management |

## 10. Self-Check Questions

1. If an unauthenticated user calls \`/private\`, why does the example configuration return 401? If \`reader\` calls \`/admin\`, why does it return 403?
2. Why is \`ReactiveSecurityContextHolder\` more suitable for WebFlux than relying on \`ThreadLocal\`?
3. Why is \`authenticated()\` not enough to protect \`GET /orders/{id}\`?
4. When moving from the HTTP Basic demo to JWT, which part still holds the access policy, and what additional token validation conditions must be designed?
5. If \`/public\` needs to be called from a browser on a different origin, can \`permitAll()\` be replaced by CORS configuration? Why or why not?

**Key takeaway:** Spring Security Reactive is the **reactive authentication, authorization, and security context management** layer for WebFlux applications. It places consistent security policies in front of handlers while allowing downstream code to safely access identity within the Reactor pipeline. Complete security still requires business-layer authorization, proper web configuration, secure storage infrastructure, and testing of denied cases.

**Official documentation for deeper study:**
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html