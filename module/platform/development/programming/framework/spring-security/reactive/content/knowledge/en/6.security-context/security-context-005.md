# Accessing the user with @AuthenticationPrincipal, Principal, and ServerWebExchange

> **Context:** Spring Boot 3.3, Spring Security 6, Spring WebFlux, and Java 17+. This lesson explains how to retrieve the identity authenticated by Spring Security in a reactive controller, how to choose among `@AuthenticationPrincipal`, `java.security.Principal`, or `ServerWebExchange`, and how to carry that information through `Mono`/`Flux` chains without depending on the current thread.

## 1. Practical question: who is calling the API?

Suppose a user calls `GET /api/me` with HTTP Basic, a session cookie, or a bearer token. The controller needs to know **the caller authenticated by Spring Security**, then return some public info, or use that identity to authorize data access.

There are three common ways in a WebFlux controller:

```java
// Retrieve the principal object inside Authentication:
@AuthenticationPrincipal UserDetails user

// Retrieve generic identity information provided by WebFlux:
Principal principal

// Retrieve the HTTP exchange context, then access the principal reactively:
ServerWebExchange exchange
// exchange.getPrincipal() -> Mono<Principal>
```

**Prerequisite:** the request must pass through the security chain (`SecurityWebFilterChain`) and have a configured authentication mechanism. Adding a `principal` parameter to a method does not verify tokens, perform login, or grant permissions.

### Flow diagram

```text
HTTP request (Authorization/cookie)
       |
       v
Spring WebFlux: ServerWebExchange
       |
       v
Spring Security WebFilter / SecurityWebFilterChain
       | verify credentials, create Authentication
       | provide SecurityContext in Reactor Context
       v
@Controller / @RestController
       |-- @AuthenticationPrincipal -> Authentication.getPrincipal()
       |-- Principal                -> generic name/identity
       |-- Mono<Principal>          -> reactive identity
       |-- ServerWebExchange        -> exchange.getPrincipal()
       |
       v
Service -> authorize data -> Mono/Flux -> HTTP response
```

When a request is accepted, these access mechanisms can represent the same user, yet **their Java types and the amount of information they expose are not identical**.

## 2. Comparing the three access approaches

| API/Parameter | Value received | When to choose | Key points to remember |
|---|---|---|---|
| `@AuthenticationPrincipal UserDetails user` | The value of `Authentication.getPrincipal()`, if type matches | Need the authenticated user object in the controller | Principal type depends on the auth mechanism, not always `UserDetails` |
| `@AuthenticationPrincipal Jwt jwt` | `Jwt` object in an appropriate JWT resource server configuration | Need verified claims from a JWT | Requires real resource server/JWT setup; cannot cast Basic demo principal to `Jwt` |
| `Principal principal` | `java.security.Principal` with `getName()` | Only need the name/ID exposed by principal | Not equivalent to full `Authentication.getPrincipal()`; less coupled to Spring Security |
| `Mono<Principal> principal` | Publisher emitting the principal when present, or empty | Want to keep reactive style in handler | Do not `block()`; process via `map`/`flatMap` |
| `ServerWebExchange exchange` | HTTP exchange object; `getPrincipal()` returns `Mono<Principal>` | Need request metadata/response besides identity | Do not read identity from self-declared headers instead of principal |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>` in Reactor Context | Service/operator needs `Authentication` without HTTP parameters | Depends on subscription Context; does not replace authorization |

**Main difference:** `@AuthenticationPrincipal` accesses **the principal inside the Authentication object**; `Principal` is **the identity object at the Spring WebFlux interface**, usually an `Authentication` implementing `Principal`. If you only need the name, call `getName()`. If you need authorities, work with `Authentication` using a type check or access `SecurityContext`.

## 3. Underlying mechanism in a reactive application

Spring Security creates/restores `Authentication` after authentication. An `Authentication` commonly has these parts:

- `getPrincipal()`: the identity object (for example `UserDetails` on username/password login, or `Jwt` with a properly configured JWT resource server).
- `getName()`: display name for the authenticated object. Exact meaning can be username, subject, or a mapped name; **do not assume it is a numeric database ID**.
- `getAuthorities()`: the set of granted permissions/authorities.
- `isAuthenticated()`: status of the Authentication; must be interpreted within the security policy and token type in use, never using this boolean alone in place of full authorization.

In WebFlux, Spring Security integrates with **Reactor Context**. Reactive operators can switch threads; thus fetching the user with Servlet-style ThreadLocal `SecurityContextHolder.getContext()` is not a reliable default for WebFlux logic. Accessing via controller parameters or `ReactiveSecurityContextHolder` is more appropriate.

```text
Authentication
  ├─ principal: UserDetails / Jwt / OidcUser / custom user / ...
  ├─ name: "alice" (depends on auth mechanism)
  ├─ authorities: [ROLE_USER, ...]
  └─ credentials, details, authentication status

SecurityContext
  └─ Authentication

Reactor Context of request/subscription
  └─ SecurityContext, ready for Spring Security reactive access
```

**Do not confuse the two cases:** `exchange.getPrincipal()` retrieves the request's principal via WebFlux, while `@AuthenticationPrincipal` extracts `Authentication.getPrincipal()`. With default username/password, both usually yield the same name, yet **not the same object type**.

## 4. Complete example: five ways to read the same identity

Goal: build a WebFlux application with endpoints returning the username and the name of the retrieval approach. Spring Security requires authentication for `/api/me/**`, while `/api/public` is readable without logging in. HTTP Basic is used solely for localhost testing; never use demo credentials in production.

Structure:

```text
reactive-principal-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/identity/
    │   ├── IdentityApplication.java
    │   └── SecurityConfiguration.java
    └── test/java/demo/identity/
        └── IdentityApplicationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-principal-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.identity'
version = '1.0.0'

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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/demo/identity/SecurityConfiguration.java**

```java
package demo.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Configuration explanation:

- `/api/public` is a public GET exception to illustrate the rule.
- Remaining requests must authenticate before reaching controllers.
- `httpBasic(...)` enables Basic auth; `formLogin(...disable())` keeps curl from being redirected to an HTML login page during tests. For browser apps with sessions/forms, configure appropriately.
- Do not disable CSRF just for a GET example. This setup uses only GET so CSRF does not need adjustment.
- No custom user store is declared: Spring Boot WebFlux can still generate a development user named `user` with a random password on startup. Obtain the password from the startup log, and test on localhost only.

**src/main/java/demo/identity/IdentityApplication.java**

```java
package demo.identity;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    public record UserView(String username, String source) {}

    @GetMapping("/api/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    // 1. Object inside Authentication.getPrincipal()
    @GetMapping("/api/me/annotation")
    public Mono<UserView> fromAnnotation(
            @AuthenticationPrincipal UserDetails user) {
        return Mono.just(
            new UserView(user.getUsername(), "@AuthenticationPrincipal"));
    }

    // 2. Pure Java API: java.security.Principal
    @GetMapping("/api/me/principal")
    public Mono<UserView> fromPrincipal(Principal principal) {
        return Mono.just(new UserView(principal.getName(), "Principal"));
    }

    // 3. Same Principal, passed as a Mono
    @GetMapping("/api/me/mono")
    public Mono<UserView> fromMono(Mono<Principal> principal) {
        return principal.map(p -> new UserView(p.getName(), "Mono<Principal>"));
    }

    // 4. Retrieve Principal from ServerWebExchange reactively
    @GetMapping("/api/me/exchange")
    public Mono<UserView> fromExchange(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .map(p -> new UserView(p.getName(), "ServerWebExchange"));
    }

    // 5. When Authentication is needed in a Reactor chain
    @GetMapping("/api/me/context")
    public Mono<UserView> fromReactorContext() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> new UserView(auth.getName(), "Reactor Context"));
    }
}
```

**Why does each snippet fit the API's role?**

- `fromAnnotation` receives `UserDetails` as the principal during Basic authentication with Boot's user store. We only read `getUsername()` and construct a DTO; **do not serialize the whole UserDetails**, as it has sensitive fields such as the hashed password.
- `fromPrincipal` uses `getName()`. The controller does not need to know the login mechanism's implementation.
- `fromMono` shows WebFlux's reactive support for the `Principal` argument; `map` runs only when a principal is emitted.
- `fromExchange` shows `ServerWebExchange.getPrincipal()` returns `Mono<Principal>`. No `block()` or manual `subscribe()`.
- `fromReactorContext` shows how to read `Authentication` from Reactor Context in reactive processing. In simple controllers, the first three are easier to read; there is no need to invoke the context holder in every endpoint.

Because all `/api/me/**` routes require authentication, the demo can safely call `user.getUsername()` without handling `null` directly. If you change an endpoint to `permitAll()`, you must explicitly handle unauthenticated users and incompatible principals; never keep that assumption.

### Running and trying it out

Requires JDK 17+ and Gradle compatible with Spring Boot 3.3. In the project directory:

```bash
gradle bootRun
```

If a wrapper is present, use `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Look for `Using generated security password: ...` in the startup log. The default account is `user` when Boot creates an in-memory user store.

With the curl CLI, `-u user` prompts for the password in the terminal, avoiding pasting passwords into commands:

```bash
# Public
curl -i http://localhost:8080/api/public

# Unauthenticated
curl -i http://localhost:8080/api/me/principal

# Enter the password printed in the startup log when prompted
curl -i -u user http://localhost:8080/api/me/annotation
curl -i -u user http://localhost:8080/api/me/principal
curl -i -u user http://localhost:8080/api/me/mono
curl -i -u user http://localhost:8080/api/me/exchange
curl -i -u user http://localhost:8080/api/me/context
```

On PowerShell, use `curl.exe` if `curl` is aliased to another command.

| Request | Expected main result |
|---|---|
| `GET /api/public` without credentials | HTTP 200; body `public` |
| `GET /api/me/principal` without credentials | HTTP 401 (because Basic is configured without form login) |
| `GET /api/me/annotation` with valid Basic | HTTP 200; JSON with `username: "user"`, `source: "@AuthenticationPrincipal"` |
| `GET /api/me/principal` with valid Basic | HTTP 200; `username: "user"`, `source: "Principal"` |
| `GET /api/me/mono` with valid Basic | HTTP 200; `username: "user"`, `source: "Mono<Principal>"` |
| `GET /api/me/exchange` with valid Basic | HTTP 200; `username: "user"`, `source: "ServerWebExchange"` |
| `GET /api/me/context` with valid Basic | HTTP 200; `username: "user"`, `source: "Reactor Context"` |

Sample response of `GET /api/me/annotation` after successful authentication:

```json
{
  "username": "user",
  "source": "@AuthenticationPrincipal"
}
```

The username here is `user` from Boot's default user store; in real systems, `principal.getName()` can represent a subject or another identifier.

## 5. `@AuthenticationPrincipal`: getting the right principal type

The annotation is imported from:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
```

Its role is to resolve a handler argument from `Authentication.getPrincipal()`. It is not an independent authentication mechanism.

### 5.1 When using username/password

For users loaded via `ReactiveUserDetailsService`, the principal is typically an implementation of `UserDetails`:

```java
@GetMapping("/api/me/name")
Mono<String> name(@AuthenticationPrincipal UserDetails user) {
    return Mono.just(user.getUsername());
}
```

This snippet is **an illustrative method only**, to be placed in a controller with matching imports; do not add it on the same route already declared in the example without avoiding mapping conflicts.

If you only need one property of the principal, you can use SpEL:

```java
@GetMapping("/api/me/username")
Mono<String> username(
        @AuthenticationPrincipal(expression = "username") String username) {
    return Mono.just(username);
}
```

`expression = "username"` works when the principal actually has a `username` property, such as `UserDetails`. If the authentication mechanism changes to JWT or another principal type, this expression does not automatically map to the `sub` claim.

### 5.2 When using a JWT resource server

A resource server can declare:

```java
@GetMapping("/api/me/subject")
Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
```

This **is not standalone runnable code inside the Basic demo**. It requires `org.springframework.security.oauth2.jwt.Jwt`, the `spring-boot-starter-oauth2-resource-server` dependency, valid JWT verification configuration (issuer/JWK, proper validation), and a request carrying an accepted token. In default JWT resource servers, the principal is typically `Jwt`; in OAuth2 Login, it may be `OAuth2User`/`OidcUser`; in Basic, usually `UserDetails`. Never force every authentication flow into one type.

### 5.3 When the principal type does not match

If Spring Security has no suitable principal object or it is incompatible with the parameter type, the annotation can resolve to `null` (by default `errorOnInvalidType = false`). To surface type mismatches early during development, declare:

```java
@AuthenticationPrincipal(errorOnInvalidType = true) UserDetails user
```

This option surfaces type mismatches as a `ClassCastException`; it **does not grant extra permissions**, turn a public endpoint into a protected one, or replace data validation. For applications supporting multiple auth mechanisms, choose an appropriate principal type and write an explicit identity mapping layer.

### 5.4 UserDetails is not a response DTO

Never return raw `UserDetails`, `Jwt`, or `Authentication` objects in JSON responses. They can contain credentials, token metadata, sensitive claims, or internal details. Use a DTO containing only safe attributes needed by the current feature, such as `username` and display name.

## 6. `Principal`: compact option when only the name is needed

`java.security.Principal` has the primary method `getName()`. It is a JDK interface, not a Spring Security class.

```java
@GetMapping("/api/me/welcome")
Mono<String> welcome(Principal principal) {
    return Mono.just("Hello " + principal.getName());
}
```

This is an **illustrative method**. Spring WebFlux can resolve a `Principal` argument in handlers. If a handler is public, unauthenticated requests may have no principal; never rely on `principal.getName()` without ensuring an identity exists.

### Principal and Authentication

Spring Security's `Authentication` **extends `Principal`**, so an `Authentication` object has `getName()` as well as `getPrincipal()`, `getAuthorities()`, and other metadata. Although Spring Security usually provides an `Authentication`, choose the parameter according to need:

- Need only the name for display: `Principal`.
- Need specific properties from `Authentication.getPrincipal()`: `@AuthenticationPrincipal` with the right type.
- Need roles/authorities or pipeline processing: read `Authentication` from the reactive security context, or check `instanceof` if you already have `Principal`.

Type-checking illustration, **not a complete controller**:

```java
if (principal instanceof Authentication authentication) {
    boolean canRead = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("SCOPE_profile.read"));
    // Only one permission condition; resource authorization is still required.
}
```

Import `org.springframework.security.core.Authentication` and pick authorities matching how your system grants permissions. A username alone does not prove the user owns `orderId` or has rights in another tenant.

### Reactive argument

WebFlux also supports a `Mono<Principal>` argument in controllers:

```java
@GetMapping("/api/me/async")
Mono<String> async(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
```

If the publisher is empty, `map` produces no value; this **does not mean HTTP 401 is automatically returned**. The security chain must enforce authentication policy; on routes allowing anonymous access, the handler must define an appropriate response if needed.

## 7. `ServerWebExchange`: accessing request info and reactive principal

`ServerWebExchange` represents the entire WebFlux HTTP exchange, including request, response, attributes, session info, and principal.

```java
@GetMapping("/api/me/from-exchange")
Mono<String> fromExchange(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
```

**Characteristics:**

1. `getPrincipal()` returns `Mono<Principal>` (more precisely, generic `Mono<T extends Principal>` per the API).
2. Use `map`/`flatMap`, never call `block()` on the event loop.
3. If there is no principal, the publisher can be empty. If you want a fallback value on a public endpoint, you can use `defaultIfEmpty("guest")`, while checking whether the app uses anonymous authentication and its response policy.
4. `exchange.getRequest().getHeaders()` can read HTTP headers; self-sent headers like `X-User-Id` or `X-Role` **are not trustworthy as authenticated identity**.

**Security anti-pattern** example (never use for authorization):

```java
String userId = exchange.getRequest().getHeaders().getFirst("X-User-Id");
// Clients can forge this header; never use it as the current authenticated user.
```

The right approach is to get the principal from the security mechanism, extract the verified ID per system conventions, and then authorize data access. Choose `ServerWebExchange` when the controller genuinely needs additional HTTP info; if only the name is needed, `Principal` is usually cleaner.

## 8. Moving into Services and Reactor operators

### 8.1 Reactor Context and SecurityContext

In WebFlux, a chain can run across multiple threads. Spring Security reactive uses Reactor Context to carry `SecurityContext` across operators in the same subscription chain.

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is an **illustrative method**, requiring imports for `Mono`, `ReactiveSecurityContextHolder`, `SecurityContext`, and `Authentication`. When called inside a pipeline whose context is set by Spring Security, it reads the authenticated username. Without a context, the publisher may be empty.

A pattern in a service needing an asynchronous chain:

```java
Mono<String> loadGreeting() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> messageRepository.findGreetingByUser(auth.getName()));
}
```

`messageRepository` here is an illustrative dependency to be defined separately; **the snippet is not a standalone program**. When a service already receives a verified user ID from the controller, passing that ID as an explicit parameter is also a clean, easily testable design.

### 8.2 Things that lose or corrupt context

- Do not create a custom `ThreadLocal` to track users in WebFlux; requests can switch threads.
- Do not manually call `subscribe()` inside a service or handler and assume the detached task preserves the SecurityContext and request lifecycle. Always **return the Publisher** so the framework manages the subscription.
- `publishOn` and `subscribeOn` **do not drop Reactor Context by default**; the risk lies in detaching subscriptions, callbacks outside the chain, or crossing to other APIs without actively propagating context.
- Do not call `block()` to read the principal in a controller/reactive service; blocking the event loop can exhaust resources and fail on non-blocking threads.
- When publishing events to a queue/background job, do not assume the request's HTTP context exists when the consumer runs later. Pass minimal required identity data from a trusted source and re-authorize on the receiving side.

### 8.3 Multiple paths should see the same identity

`@AuthenticationPrincipal` in a controller, `ServerWebExchange.getPrincipal()`, and `ReactiveSecurityContextHolder` can all reflect the same authentication session, though you should test consistency across your system's Basic, form login, and JWT mechanisms. When authentication is swapped or claim mappings differ, the `principal` type or `getName()` value can vary. Do not treat three matching demo results as a universal guarantee for every mechanism.

## 9. Identity and data authorization are two different tasks

Suppose user A is logged in and calls:

```http
GET /api/orders/892
Authorization: Bearer <access-token-of-A>
```

Knowing `principal.getName()` is A **does not prove** order 892 belongs to A. Perform object-level authorization in the service or repository using the verified identity/tenant:

```text
currentUser = authenticated principal or verified subject
requestedOrderId = path variable supplied by client

authorization:
  verify currentUser has access to requestedOrderId
  verify tenant boundary and required action

if allowed:
  query/return an approved response DTO
else:
  return 403 or 404 according to the API policy
```

This is **pseudocode**, not runnable Java. In multi-tenant apps, avoid taking `tenantId` directly from query params, JSON bodies, or client headers as proof of permission; identity source and permission scope must be enforced by authentication and business checks.

Do not use `Principal.getName()` as a database ID unless the system guarantees a durable mapping. Usernames can change; JWT `sub` values may not be global across multiple issuers. When a stable ID is needed, build a mapping layer from verified identity (such as issuer + subject) to an internal ID and enforce tenant/authorization checks.

## 10. Automated testing: all paths return the same user

To test the demo from section 4 without relying on a randomly generated password, the test configures Boot's account **in the test context only**. Never deploy sample passwords to real environments.

**src/test/java/demo/identity/IdentityApplicationTest.java**

```java
package demo.identity;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.security.user.name=alice",
        "spring.security.user.password=test-only-password"
    }
)
@AutoConfigureWebTestClient
class IdentityApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedEndpointRejectsAnonymousRequest() {
        client.get().uri("/api/me/principal")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void principalSourcesAgreeOnUsername() {
        for (String path : List.of(
                "/api/me/annotation",
                "/api/me/principal",
                "/api/me/mono",
                "/api/me/exchange",
                "/api/me/context")) {
            client.get().uri(path)
                .headers(headers ->
                    headers.setBasicAuth("alice", "test-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
        }
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/me/annotation")
            .headers(headers ->
                headers.setBasicAuth("alice", "invalid-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

Expect **4 test methods PASS** if Gradle/JDK versions are compatible and dependencies are resolved. The third test sends requests through all five paths and checks the JSON value. The second test confirms the controller is not acting as the authentication gate: unauthenticated requests are blocked before reaching protected endpoints.

This is application-level testing with `WebTestClient` and runs with the same `settings.gradle`, `build.gradle`, and Java classes from section 4. For projects using JWT/OIDC or custom user sources, replace the auth test fixture accordingly rather than assuming Boot's auto-created `alice` account.

## 11. Common mistakes

| Mistake | Why it is wrong | Fix |
|---|---|---|
| Injecting `@AuthenticationPrincipal UserDetails` in a JWT app | JWT principal can be `Jwt`, not `UserDetails` | Use the type matching the actual authentication |
| Assuming `@AuthenticationPrincipal` authenticates the request | The annotation only reads from context | Configure `SecurityWebFilterChain` and real authentication |
| Treating `Principal.getName()` as authorization for every object | Authentication only provides identity | Enforce object/tenant permissions on the server |
| Using `X-User-Id` as the current user | Clients can forge headers | Read from verified principal/context |
| Casting `Principal` to `UserDetails` without checking | `Principal` is usually `Authentication`; the inner principal may be `UserDetails` | Use `@AuthenticationPrincipal` or explicit type checks |
| Using ThreadLocal `SecurityContextHolder` as in MVC | Reactive execution is not pinned to one thread | Use controller parameters or `ReactiveSecurityContextHolder` |
| Calling `exchange.getPrincipal().block()` | Blocks the pipeline, may fail on event loop | Use `map`/`flatMap` and return `Mono` |
| Calling `subscribe()` manually inside a handler | Creates a subscription with hard-to-control lifecycle/context | Return the publisher for the framework to subscribe |
| Returning raw `UserDetails`/`Authentication` as JSON | May expose sensitive details | Return a DTO with only needed fields |
| Using `@AuthenticationPrincipal` on a public route assuming non-null | Principal or matching type is not guaranteed | Handle anonymous/absent principals per policy |
| Equating username with an immutable ID | Usernames/claims can change or collide across issuers | Define an internal identity mapping |
| Testing only valid requests | Cannot tell if URL policy protects routes | Test anonymous, bad credentials, wrong roles, wrong objects |

## 12. Practice exercises

1. Run the example with `gradle bootRun`, log in using Boot's generated dev account, and compare the `username` field across all five `/api/me/**` endpoints.
2. Change `fromAnnotation` to `@AuthenticationPrincipal(expression = "username") String username` and explain why it works when the principal is `UserDetails`.
3. Request `/api/me/principal` without credentials and note `401`. Then inspect the `anyExchange().authenticated()` rule and explain why the controller never executed.
4. Create a public endpoint using `ServerWebExchange.getPrincipal()` and handle the missing-principal case with an intentional response; do not assume anonymous users share the same username across every config.
5. Create a route `/api/orders/{id}` allowing only the resource owner to read it. Explain why `Principal` authentication alone is insufficient, and write a test accessing another user's ID.
6. Suppose the project migrates from Basic to JWT. List the places assuming `UserDetails` that must change to `Jwt`/a dedicated identity model, while verifying token issuer, audience, signature, and scopes.
7. Move a context-reading operation into a `flatMap` followed by `publishOn`; observe that context does not disappear simply from switching schedulers. Contrast that with creating a detached subscription outside the request.

## Remember

- `@AuthenticationPrincipal` extracts **the object inside** `Authentication.getPrincipal()` and must match the type; suitable when you need `UserDetails`, `Jwt`, or a custom principal.
- `Principal` and `Mono<Principal>` are clean choices when you only need `getName()`; they are not equivalent to arbitrarily casting to `UserDetails`.
- `ServerWebExchange` provides the principal as a `Mono` alongside other request/response info; use only when HTTP context is needed.
- In reactive services, prefer passing the verified ID as an explicit parameter or reading `ReactiveSecurityContextHolder` inside the proper Reactor pipeline.
- Authenticated identity **does not replace** authorization by action, object, tenant, or business data permissions.

## Official documentation

- Spring Framework — WebFlux annotated controller method arguments (supporting `Principal`, `Mono<Principal>`, and `ServerWebExchange`): https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — `ServerWebExchange.getPrincipal()`: https://docs.spring.io/spring-framework/docs/6.1.22/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Security — `@AuthenticationPrincipal`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/annotation/AuthenticationPrincipal.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security / Reactor Context: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Boot — Spring Security for WebFlux: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
