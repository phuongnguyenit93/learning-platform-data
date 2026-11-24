# Reading current identity with ReactiveSecurityContextHolder in Spring Security Reactive

## 1. Problem and objectives

In Spring WebFlux, an authenticated request has an **Authentication** describing the caller's identity and permissions. When processing happens deep inside a service rather than directly in a controller, developers often need to read the current identity from **ReactiveSecurityContextHolder**.

After this lesson, you should be able to:

1. Explain the roles of SecurityContext, Authentication, principal, and Reactor Context.
2. Read the username, authorities, or principal from ReactiveSecurityContextHolder.getContext() inside a Mono/Flux.
3. Safely handle cases where the context does not exist, Authentication is null, or the caller is anonymous.
4. Understand how Reactor Context follows the subscription instead of ThreadLocal and how contextWrite affects the pipeline.
5. Know when to use withAuthentication, withSecurityContext, clearContext, and the limits of these APIs.
6. Write a runnable Java 17+ application with Spring Boot WebFlux, test with curl, and verify with StepVerifier.
7. Distinguish reading identity from making authorization decisions on a specific resource.

**Key takeaway:** read identity from a context established by trusted authentication. Calling getContext() itself **does not log in**, **does not verify passwords/tokens**, and **does not grant permissions**.

## 2. Data layers: Reactor Context → SecurityContext → Authentication

Components to distinguish:

| Component | Purpose | What to watch out for |
| --- | --- | --- |
| **Reactor Context** | Data attached to a subscriber/reactive chain | Not a global Map and not pinned to a thread |
| **SecurityContext** | Holds Authentication, may not yet contain Authentication | SecurityContext.getAuthentication() can be null |
| **Authentication** | Principal, credentials, authorities, and authentication status | Concrete type depends on the authentication mechanism |
| **Principal** | Represents identity; can be UserDetails, Jwt, OAuth2 principal, or an application type | Do not cast every principal to UserDetails |
| **Authentication.getName()** | Identity name per the Authentication contract | Not implicitly an immutable business ID |
| **GrantedAuthority** | Mapped permission, role, or scope | ROLE_USER, SCOPE_orders.read have configuration-dependent semantics |
| **ReactiveSecurityContextHolder** | Provides APIs to read/write SecurityContext in Reactor Context | Returns Mono<SecurityContext> instead of synchronous SecurityContext |

Conceptual diagram:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |-- AuthenticationWebFilter / HTTP Basic / JWT / other mechanism
    |-- Authenticator verifies credentials, creates trusted Authentication
    |-- SecurityContext holds Authentication
    v
Reactor Context of the current subscription
    |
    +--> Controller (Mono/Flux)
            |
            +--> Service (Mono/Flux)
                    |
                    +--> ReactiveSecurityContextHolder.getContext()
                            |
                            v
                      Mono<SecurityContext>
                            |
                            v
                      Authentication
                            |
                      name / principal / authorities
~~~

Spring Security Reactive can use **ReactorContextWebFilter** and ServerSecurityContextRepository to populate the context; a succeeding authentication mechanism can also set the context for downstream processing. With sessions, HTTP Basic, and bearer tokens, persistence/restoration across requests differs. Do not infer that an HTTP session or context always exists everywhere.

## 3. Why isn't servlet's SecurityContextHolder sufficient?

In traditional servlets, SecurityContextHolder typically stores the context in a ThreadLocal on the request-processing thread. In WebFlux:

- Multiple requests can pass through the same event-loop thread.
- A request can suspend while waiting for I/O.
- After publishOn/subscribeOn, the pipeline can resume on a different thread.
- A single publisher can be subscribed to multiple times with different contexts.

Example:

~~~text
Request Alice:  thread-A ---> I/O ---> thread-C ---> response
Request Bob:    thread-A ---> I/O ---> thread-B ---> response

Thread-A is not "Alice's thread" forever.
Identity is carried by the Reactor Context of each subscription.
~~~

Use the reactive API:

~~~java
Mono<Authentication> current =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Using ThreadLocal-based SecurityContextHolder.getContext() in WebFlux can yield empty data, wrong timing, or rely on an unverified context bridge. Keep operations inside Mono/Flux or pass the verified user ID as a parameter when needed.

## 4. Core API contract

Important methods:

~~~java
// Read SecurityContext from the current Reactor Context.
static Mono<SecurityContext> getContext();

// Put an Authentication into a new Reactor Context.
static reactor.util.context.Context withAuthentication(
        Authentication authentication);

// Put a SecurityContext Publisher into a new Context.
static reactor.util.context.Context withSecurityContext(
        Mono<? extends SecurityContext> securityContext);

// Return a function that removes the SecurityContext entry from Reactor Context.
static java.util.function.Function<
        reactor.util.context.Context,
        reactor.util.context.Context> clearContext();
~~~

You **cannot** assign Mono to a regular SecurityContext variable:

~~~java
// Wrong type, does not compile.
SecurityContext ctx = ReactiveSecurityContextHolder.getContext();
~~~

Instead, compose with operators:

~~~java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

A call to getContext() creates a **Mono describing how to read the context upon subscription**, rather than immediately fetching identity from a global variable. Do not call block() in a WebFlux handler to force it into a String.

## 5. How to read identity safely

### 5.1. Getting the username

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
~~~

If the context contains Alice's Authentication, the Mono emits "alice". If there is no context or Authentication is null, the Mono normally completes empty. Use Mono.justOrEmpty instead of mapping directly over a potentially null value to avoid errors when mapping null.

### 5.2. Requiring an authenticated identity

~~~java
public Mono<String> requiredUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .filter(authentication ->
                    authentication.isAuthenticated()
                    && !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Authentication required")));
}
~~~

Imports for the illustrative method snippet:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
~~~

**Note:** AnonymousAuthenticationToken can have isAuthenticated() as true. Therefore, using isAuthenticated() alone does not guarantee this is a truly logged-in user identity. At the HTTP layer, prefer configuring Spring Security with .authenticated(), hasRole/hasAuthority, and letting the framework handle anonymous users. When you must check in Java, use an appropriate AuthenticationTrustResolver or check for anonymous explicitly.

An AccessDeniedException in a service can be translated into a response according to the exception-handling configuration; do not assume every service error returns exactly 401. 401 is typically missing/invalid credentials at the entry point, while 403 is typically authenticated without permission. Exact handling depends on the filter chain/handler.

### 5.3. Getting authorities

~~~java
public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(authentication -> authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
}
~~~

Additional imports:

~~~java
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
~~~

With .roles("USER"), the default authority is ROLE_USER. With a Resource Server and default scope mapping, a scope can become an authority such as SCOPE_orders.read. Do not compare permission strings without understanding how your system transforms them.

### 5.4. Getting the principal without exposing sensitive data

~~~java
public Mono<Object> currentPrincipal() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getPrincipal);
}
~~~

The principal can be UserDetails, Jwt, an OAuth2 principal, or a custom type. Do not cast without checking, and do not serialize the entire object straight to JSON because it may contain password hashes, internal claims, tokens, or information not meant for clients. Map it to a DTO with only allowed fields.

### 5.5. Public greetings vs. security decisions

If an endpoint is completely public, you can fall back to a display name:

~~~java
Mono<String> greeting = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
        .map(Authentication::getName)
        .defaultIfEmpty("guest")
        .map(name -> "hello " + name);
~~~

A "guest" fallback is appropriate for **display**; it must not be used as proof of permission to read private data. On protected endpoints, a missing identity must fail safely by denying access.

## 6. How is Reactor Context propagated?

Reactor Context is attached to the Subscriber and propagated along the subscription chain. The **contextWrite** operator creates/transforms the Context seen by operators **upstream** of it.

Example using an Authentication from a trusted source:

~~~java
Authentication trusted = /* already verified by manager */;

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(trusted));
~~~

This is an API illustration; the trusted variable must come from a trusted authentication system or a test fixture, never directly from an arbitrary X-User header sent by a client.

**Why is contextWrite at the bottom?** Subscription signals travel upstream from downstream. A contextWrite placed below a context-reading source puts the value into the context of operators above it. If contextWrite is placed inside an inner publisher, the value may apply only to that inner publisher; it does not automatically alter the entire chain.

Normal Reactor operators such as map, flatMap, publishOn, and subscribeOn preserve Reactor Context access when publishers are properly composed. However, a raw Executor, CompletableFuture, callback, or manually created thread **does not automatically carry all Reactor Context**. When crossing into a non-Reactor system, pass the required verified fields via an explicit contract.

## 7. Why avoid block() or manual subscribe()?

**block():** can stall the event loop and lose the expected context by creating a separate subscription.

~~~java
// Do not do this in a WebFlux service/handler:
String name = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
~~~

**Manual subscribe():** creates a separate subscription outside the request lifecycle, making errors and context hard to control.

~~~java
// Do not use this to fetch identity in a request:
ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .subscribe(name -> audit(name));

return Mono.just("ok");
~~~

If auditing is required inside the processing flow:

~~~java
// Integration illustration: auditService.persist(actorId) returns Mono<Void>.
return requiredUsername()
        .flatMap(actor -> auditService.persist(actor)
                .thenReturn("ok"));
~~~

If auditing must be durable even if the client disconnects, design an independent transaction/outbox or durable queue. Do not rely solely on doFinally or a fire-and-forget subscribe() to guarantee mandatory events are saved.

## 8. Java 17+ Demo: reading identity from Spring Security WebFlux

The demo provides:

- HTTP Basic authenticating two in-memory users.
- /api/me reading identity from **IdentityService** using ReactiveSecurityContextHolder.
- /api/authorities inspecting GrantedAuthority values.
- /api/principal using Mono<Principal> in the controller for comparison.
- /api/user/greeting protected by reactive method security.
- /api/admin/report requiring ROLE_ADMIN in the HTTP filter.

File structure:

~~~text
reactive-current-identity/
├── settings.gradle
├── build.gradle
├── src/main/java/example/identity/IdentityApplication.java
├── src/main/java/example/identity/IdentityService.java
├── src/main/java/example/identity/IdentityController.java
└── src/test/java/example/identity/IdentityServiceTest.java
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'reactive-current-identity'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.3. IdentityApplication.java

~~~java
package example.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }
}
~~~

SecurityWebFilterChain permits /public/ping, requires authentication on /api/**, and only ROLE_ADMIN can enter /api/admin/**. @EnableReactiveMethodSecurity activates @PreAuthorize support for Spring beans returning a Publisher.

Passwords in the demo are for learning only. In production, use appropriate identity sources and secret stores, HTTPS, credential management, and rate limiting.

### 8.4. IdentityService.java

~~~java
package example.identity;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> requiredUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(authentication ->
                        authentication.isAuthenticated()
                        && !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException("Authentication required")));
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> userGreeting() {
        return requiredUsername()
                .map(name -> "service hello " + name);
    }
}
~~~

Key point: the service receives the right identity **at subscription time**, without storing the name in a singleton. @PreAuthorize is applied when the controller calls through the Spring bean/proxy. Internal calls via this.userGreeting() can bypass the proxy and fail to trigger method security.

### 8.5. IdentityController.java

~~~java
package example.identity;

import java.security.Principal;
import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return identityService.requiredUsername()
                .map(name -> "hello " + name);
    }

    @GetMapping("/api/authorities")
    public Mono<String> authorities() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .map(Authentication::getAuthorities)
                .map(auths -> auths.stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .collect(Collectors.joining(",")));
    }

    @GetMapping("/api/principal")
    public Mono<String> fromArgument(Mono<Principal> principal) {
        return principal.map(p -> "principal " + p.getName());
    }

    @GetMapping("/api/user/greeting")
    public Mono<String> greeting() {
        return identityService.userGreeting();
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return identityService.requiredUsername()
                .map(name -> "admin report for " + name);
    }
}
~~~

Two ways to get the identity: the service uses ReactiveSecurityContextHolder directly, while a controller can accept Mono<Principal> via WebFlux's argument resolver. For an endpoint that only needs the principal, receiving it as a parameter can be simpler; for a service reused in multiple places, reading the reactive context avoids passing Principal through every method.

### 8.6. Running the demo

Requires JDK 17+ and Gradle 8.x compatible with Spring Boot 3.3.5:

~~~bash
gradle bootRun
~~~

In another terminal, run the Bash-style commands:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u alice:alice-pass http://localhost:8080/api/me
# hello alice

curl -s -u admin:admin-pass http://localhost:8080/api/me
# hello admin

curl -s -u alice:alice-pass http://localhost:8080/api/authorities
# ROLE_USER

curl -s -u admin:admin-pass http://localhost:8080/api/authorities
# ROLE_ADMIN

curl -s -u alice:alice-pass http://localhost:8080/api/principal
# principal alice

curl -s -u alice:alice-pass http://localhost:8080/api/user/greeting
# service hello alice

curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/api/user/greeting
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/api/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/api/admin/report
# admin report for admin
~~~

The parts after `#` are the **expected demo outputs**, not commands. In PowerShell, use curl.exe and enter each command on a single line; Bash-style line continuations do not apply directly.

| Request | Context/authority | Rule | Result |
| --- | --- | --- | --- |
| GET /public/ping | Identity not required | permitAll | 200 pong |
| GET /api/me without credentials | No trusted Authentication | authenticated | 401 |
| GET /api/me as alice | alice, ROLE_USER | authenticated | 200 hello alice |
| GET /api/authorities as admin | admin, ROLE_ADMIN | authenticated | 200 ROLE_ADMIN |
| GET /api/user/greeting as alice | alice, ROLE_USER | @PreAuthorize USER | 200 service hello alice |
| GET /api/user/greeting as admin | admin, ROLE_ADMIN | @PreAuthorize USER | 403 |
| GET /api/admin/report as alice | alice, ROLE_USER | hasRole ADMIN | 403 |
| GET /api/admin/report as admin | admin, ROLE_ADMIN | hasRole ADMIN | 200 admin report for admin |

HTTP Basic checks credentials on each matching request; the demo does not implement a login session. Do not rely on the response code of a public request to infer that all WebFilters are bypassed.

## 9. Direct testing with StepVerifier

For unit tests without HTTP, you can explicitly supply a trusted Authentication to Reactor Context using **withAuthentication**. This is a fixture technique, not a production input authentication path.

### 9.1. IdentityServiceTest.java

~~~java
package example.identity;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class IdentityServiceTest {

    private final IdentityService service = new IdentityService();

    private static Authentication verified(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void eachSubscriptionHasItsOwnIdentity() {
        Mono<String> username = service.requiredUsername();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("alice"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("bob"))))
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotGrantAccess() {
        StepVerifier.create(service.requiredUsername())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void clearContextMakesIdentityUnavailableToUpstream() {
        Mono<String> username = service.requiredUsername()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                verified("alice")));

        StepVerifier.create(username)
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** the tests PASS and Gradle finishes with BUILD SUCCESSFUL, provided JDK/dependencies are properly installed.

This unit test does not start a Spring proxy, so it is not a test for @PreAuthorize; it directly proves IdentityService reads Reactor Context properly. Full method security testing requires a Spring context/WebTestClient.

### 9.2. Why can the same Mono read two users?

One publisher can be subscribed to in two different Contexts:

~~~text
Mono<String> username
   |
   +-- Subscription 1: Context(Authentication=alice) -> alice
   |
   +-- Subscription 2: Context(Authentication=bob)   -> bob
~~~

There is no global username variable being overwritten. The context applies per subscriber. This is why a request's username should not be cached in a singleton field.

## 10. withAuthentication, withSecurityContext, and clearContext

**withAuthentication(authentication)** creates a Reactor Context containing a Mono<SecurityContext> with the provided Authentication. Suitable for unit tests or trusted framework code, not for turning a client-sent username into a valid Authentication.

**withSecurityContext(Mono<? extends SecurityContext>)** is useful when you already have a SecurityContext or a Publisher of it:

~~~java
Authentication trusted = /* obtained from a verified manager */;
SecurityContext context = new SecurityContextImpl(trusted);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                        Mono.just(context)));
~~~

Additional imports:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
~~~

The snippet above is an **integration example**, where trusted must be replaced with a verified object. Do not turn a self-declared username, role, or authenticated=true from an HTTP header into a trusted context.

**clearContext()** returns a Function<Context,Context> to remove the SecurityContext entry on a pipeline branch. Test example:

~~~java
Mono<String> name = service.requiredUsername()
        .contextWrite(ReactiveSecurityContextHolder.clearContext())
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("alice")));
~~~

Ordering matters: the outer contextWrite adds Authentication on subscription; the inner contextWrite closer to the source clears the context before the service reads it. This is only an operation modifying **Reactor Context within the pipeline**, not a global logout. It does not revoke a JWT, delete a server session, clear cookies, invalidate refresh tokens, or block other requests. Logout must be performed according to the application's session/token mechanism.

## 11. Reading context in asynchronous tasks

In a properly composed Reactor pipeline, context can follow the chain across operators and schedulers. However, when integrating a raw Executor, CompletableFuture, or standalone background task, you must not assume Reactor Context appears automatically on every thread.

A safe design approach:

~~~java
// Integration illustration: jobPublisher is implemented by the application.
return identityService.requiredUsername()
        .flatMap(actorId ->
                jobPublisher.enqueue(actorId, documentId));
~~~

Here actorId has already been extracted from Authentication; if a stable tenantId or subject is needed, extract it from verified principal/claims. The job needs its own authentication, authorization, and auditing controls; never use an empty context to imply system/admin.

Signs of lost context:

- Identity-reading code is called outside the pipeline or from a static initializer.
- The service calls subscribe itself instead of returning Mono/Flux.
- Calling block() and expecting the context to still propagate across threads.
- Not entering the right SecurityWebFilterChain or the authentication filter has not set SecurityContext.
- Placing contextWrite in the wrong position.
- Spawning publishers/async callbacks that are not composed into the request chain.
- Using ThreadLocal SecurityContextHolder as in servlets.

When encountering an unexpectedly empty ReactiveSecurityContextHolder.getContext(), inspect these boundaries in order before changing code. Never create a default Authentication with admin rights to mask an error.

## 12. Reading identity is not enough to check permissions

Consider GET /api/orders/42. The API knows the request belongs to alice, but order 42 may belong to bob. Reading alice from ReactiveSecurityContextHolder only answers **who is calling**, not **whether they may view order 42**.

Illustrative service example:

~~~java
// Integration illustration: OrderDto and orderRepository are defined by the application.
public Mono<OrderDto> readOrder(String orderId) {
    return identityService.requiredUsername()
            .flatMap(username ->
                    orderRepository.findByIdAndOwnerUsername(
                            orderId, username));
}
~~~

The repository must filter by **both orderId and the verified owner/tenant**. If read permissions are more complex, add appropriate policy checks at the service/data layer. Never trust an ownerId or tenantId self-declared by the client.

With JWT, claims such as sub, tenant, and groups are trustworthy only after verifying signature, issuer, audience, expiry, and required constraints. For long-lived user IDs, prefer stable subject/id values rather than assuming username is always immutable.

## 13. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using SecurityContextHolder in WebFlux like servlet ThreadLocal | Identity lost or wrong on thread switches | ReactiveSecurityContextHolder |
| Calling getContext().block() in a handler | Stalls event loop, creates inappropriate subscription | Return Mono/Flux |
| Calling subscribe() manually to read principal | Loses lifecycle and context, errors hard to observe | flatMap/then in the returned pipeline |
| Casting every principal to UserDetails | JWT/OIDC principals have different types | Check type or use getName() |
| Only checking isAuthenticated() | AnonymousAuthenticationToken can be true | Use authenticated/trust resolver |
| Using defaultIfEmpty("admin") in a private API | Missing context is treated as authorized | Fail closed, return error |
| Putting Authentication from client X-User into withAuthentication | Spoofs identity and permissions | Only use results from a verified manager |
| Sending raw Authentication/principal to client | Leaks credentials/internal claims | Map only allowed fields |
| Calling map directly on potentially null Authentication | May emit null errors | Mono.justOrEmpty |
| Caching request username in a singleton | Cross-request data gets mixed | Read at subscription time |
| Treating clearContext() as global logout across requests | Does not clear tokens/sessions outside pipeline | Proper logout and revocation mechanism |
| Treating username as sufficient permission to read a record | IDOR/BOLA, leaks another user's data | Check owner/tenant |
| Placing contextWrite in the wrong position | Reading operators do not see the context | Understand upstream subscription direction |
| Logging the entire SecurityContext or JWT | Sensitive data exposure | Log only filtered actor ID/correlation ID |

## 14. Essential tests

**Unit tests with StepVerifier:**

- Alice and Bob in two isolated subscriptions.
- Missing Context → service requiring identity returns an error.
- AnonymousAuthenticationToken → not treated as a logged-in user.
- Context cleared upstream → access denied.
- No high-privilege fallback on error.

**Integration tests with WebTestClient:**

- /public/ping succeeds without credentials.
- /api/me without credentials is rejected.
- /api/me with two users returns the two correct identities, even when run concurrently.
- ROLE_USER cannot call the admin endpoint.
- @PreAuthorize allows only ROLE_USER into /api/user/greeting.
- If using JWT/sessions/multiple chains, test context against the actual configuration.

**Async tests:** a pipeline with publishOn/subscribeOn preserves context when properly composed; raw background tasks receive actor ID via an explicit contract. Tests for context loss should use StepVerifier and reliable synchronization rather than Thread.sleep guesswork.

**Operational observability:** when auditing who performed an action, log only controlled actor ID/subject, action, resource, permission result, and correlation ID; never log passwords, raw bearer tokens, or the entire principal.

## 15. Self-check questions

1. Does ReactiveSecurityContextHolder.getContext() return SecurityContext or Mono<SecurityContext>?
2. Why is ThreadLocal not safe enough for reading identity in WebFlux?
3. What is the difference between SecurityContext, Authentication, and principal?
4. If getContext() is empty, may you assign role USER by default to allow continued access?
5. Why is isAuthenticated() alone insufficient to exclude anonymous users?
6. Why is contextWrite usually placed below the publisher that needs to read the context?
7. When running two subscriptions of the same Mono in Alice and Bob's Contexts, what should the identities be?
8. Does clearContext() delete a JWT or server session?
9. Why does @PreAuthorize require calling through a Spring bean/proxy?
10. Why does reading alice's username still not permit viewing bob's order?
11. When a service calls a raw Executor, how should actor identity be handled?
12. When only needing the username in a controller, can you accept Mono<Principal> instead of accessing SecurityContext directly?

**Answers:** (1) Mono<SecurityContext>; (2) Reactor switches and shares threads, Context is per subscriber; (3) container, authentication details, and identity object; (4) no, fail closed; (5) anonymous token can have authenticated=true; (6) contextWrite transforms the context seen by upstream; (7) Alice and Bob respectively, without mixing; (8) no, it only removes the key in Reactor Context; (9) annotations are processed via proxy; (10) owner/tenant authorization is required; (11) pass the verified ID and protect the job with its own policy; (12) yes, if the WebFlux resolver supports that parameter.

## 16. References

- Spring Security Javadoc — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html

**Conclusion:** When you need to know who is calling a service in Spring Security Reactive, read **ReactiveSecurityContextHolder.getContext() → Authentication → principal/name/authorities** with Mono/Flux. Ensure the context belongs to the current subscription, trust only Authentication verified by security mechanisms, handle missing context safely, and always combine with authorization checks against the actual resource.