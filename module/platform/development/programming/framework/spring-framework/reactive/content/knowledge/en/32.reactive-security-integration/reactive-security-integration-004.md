# Propagating Authentication Context in Reactive Chains — Spring WebFlux and Spring Security

In traditional Spring MVC, logged-in user information is usually accessed through SecurityContextHolder, which relies on a strategy binding SecurityContext to the currently executing thread. In Spring WebFlux, a single request may resume on different threads due to publishOn, subscribeOn, asynchronous I/O, or network events. Therefore, attaching identity to ThreadLocal is insufficient to retain the right user throughout a reactive pipeline.

Reactive Spring Security uses the **Reactor Context**, bound to the subscription, to store and propagate SecurityContext. The central API is ReactiveSecurityContextHolder. Once WebFlux Security has authenticated an HTTP request, security filters place the context into the reactive chain; downstream services, reactive method security, and asynchronous operations within the same chain can read the right Authentication regardless of thread name.

This lesson belongs to the **Security Integration** module and focuses on how context is created, read, modified, and propagated across operators; contextWrite placement; subscription boundaries; safety when calling WebClient; and how to test so concurrent requests never mix up users.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish SecurityContext, Authentication, principal, and GrantedAuthority.
- Understand why ThreadLocal-based SecurityContextHolder is not the primary approach for WebFlux.
- Explain that Reactor Context is immutable per-subscription data, not a global map.
- Read the context using ReactiveSecurityContextHolder.getContext().
- Populate context for a subscriber using withAuthentication() and withSecurityContext().
- Clear context within a scope using clearContext().
- Understand the downstream-to-upstream propagation direction of contextWrite().
- Explain context preservation across map, flatMap, publishOn, and subscribeOn.
- Identify boundaries created by manual subscribe, detached tasks, and CompletableFuture.
- Understand how the Spring Security WebFilter chain supplies Authentication to WebFlux.
- Use reactive method security with @EnableReactiveMethodSecurity and @PreAuthorize.
- Distinguish internal Authentication propagation from forwarding bearer tokens upstream via WebClient.
- Avoid credential leaks, context leakage, or principal spoofing.
- Write a Java 17+ Spring Boot WebFlux application along with authentication/context tests.

## 2. Core Security Concepts

SecurityContext is the object holding the active Authentication for a processing scope. Authentication typically includes:

- Principal: the authenticated identity, such as a user ID or UserDetails.
- Credentials: authentication data or token, which may be erased after authentication.
- Authorities: permissions such as ROLE_USER or SCOPE_orders.read.
- Authenticated flag: whether the token has been authenticated.
- Details: auxiliary metadata provided by the system.

Example retrieving name and authorities when an Authentication is present:

~~~java
String username = authentication.getName();

List<String> permissions = authentication.getAuthorities()
    .stream()
    .map(GrantedAuthority::getAuthority)
    .toList();
~~~

getName() is the identity name from Authentication. Do not assume that a username in a request body has equivalent authentication validity. The server must use the Authentication established by the security layer after verifying credentials.

### SecurityContextHolder vs. ReactiveSecurityContextHolder

| Model | Access Method | Data Scope |
| --- | --- | --- |
| Typical Servlet/MVC | SecurityContextHolder.getContext() | Typically ThreadLocal-based per security strategy |
| Reactive WebFlux | ReactiveSecurityContextHolder.getContext() | Reactor Context belonging to the subscriber |
| Manual propagation | contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth)) | Only upstream operators within the scope of contextWrite |

Do not use SecurityContextHolder.getContext() as the default authentication source inside a WebFlux reactive chain. When a scheduler switches threads, ThreadLocal may be empty or hold stale data. Even when an application enables a context-propagation bridge, security code should still use the official reactive API.

## 3. Reactor Context Is Not ThreadLocal

Reactor Context is a structurally immutable key-value context attached to a Subscriber at subscription time. It is well suited for data flowing across multiple operators without changing every method signature.

~~~text
Incoming HTTP request
      |
      v
Spring Security filters: authenticate user alice
      |
      v
Subscriber Context contains Mono<SecurityContext>
      |
      +--> Controller
      |       |
      |       +--> Service
      |               |
      |               +--> flatMap database
      |               +--> publishOn another scheduler
      |
      +--> Reactive method authorization
      |
      v
HTTP response
~~~

Properties to remember:

1. Context is bound to a subscription, not to the entire JVM.
2. Context is not a static/global variable.
3. Two concurrent requests can carry different SecurityContexts on the same thread.
4. Context is attached at the subscription boundary or via contextWrite.
5. contextWrite affects operators upstream of it.
6. map, flatMap, and standard reactive operators can access context when in the same subscription chain.
7. Starting a separate independent subscription via subscribe() can lose the original context.

An immutable Reactor Context does not mean the SecurityContext or Authentication stored inside it is an immutable object. Avoid mutating an Authentication shared across multiple subscribers; prefer creating a new context for a new authentication scope.

## 4. The ReactiveSecurityContextHolder API

Spring Security provides the class:

~~~java
org.springframework.security.core.context.ReactiveSecurityContextHolder
~~~

Key methods:

| API | Return Type | Purpose |
| --- | --- | --- |
| getContext() | Mono<SecurityContext> | Read the subscriber's security context |
| withAuthentication(Authentication) | Context | Create a Reactor Context containing a SecurityContext from Authentication |
| withSecurityContext(Mono<? extends SecurityContext>) | Context | Create a Reactor Context storing a SecurityContext Mono |
| clearContext() | Function<Context, Context> | Remove the security context from the Reactor Context within the applied scope |

### Reading the Context

~~~java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

In a subscription without a SecurityContext, getContext() may complete empty. Do not assume an authenticated object always exists.

### Setting Context in a Test Pipeline

~~~java
Authentication alice =
    new UsernamePasswordAuthenticationToken(
        "alice",
        "n/a",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

onNext result: alice, followed by onComplete.

withAuthentication() does not write Authentication into a static variable. It creates a Context applied by contextWrite for that specific subscription.

### Setting Context with Mono<SecurityContext>

~~~java
SecurityContext securityContext =
    new SecurityContextImpl(alice);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(
            Mono.just(securityContext)));
~~~

This is explicit when you already have a SecurityContext instance or need to supply it as a Mono.

### Clearing Context Within a Scope

~~~java
Mono<String> noSecurityContext =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous-for-demo")
        .contextWrite(ReactiveSecurityContextHolder.clearContext())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Result: anonymous-for-demo. clearContext() removes the security key from the context seen upstream. This example only illustrates scoping; never use clearContext to bypass authentication/authorization in production endpoints.

## 5. When Is the Context Actually Read?

Reactor publishers are generally lazy. Code constructing a Mono does not yet execute the logic querying ReactiveSecurityContextHolder.

~~~java
Mono<String> operation =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

When `operation` is constructed, no thread carrying a user is needed. Only at subscription time does the operator query that subscriber's Reactor Context.

~~~java
Mono<String> aliceOperation = operation.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobOperation = operation.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bob));
~~~

Two publishers can share the same `operation` definition while reading different contexts upon subscription. This is essential for multi-user and multi-tenant safety.

### Do Not Capture the Current Principal at Bean Creation Time

Do not write:

~~~java
@Bean
MyService myService() {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

    return new MyService(current);
}
~~~

Singleton beans are normally created at startup, not during a specific HTTP request. Storing Authentication in a singleton field can cause every subsequent request to use the wrong identity.

Retrieve context at request execution time inside Mono/Flux, or pass the already authenticated user ID into service methods.

## 6. In Which Direction Does contextWrite Propagate Context?

Reactor Context propagates from the downstream subscriber toward upstream operators when the subscription is established.

~~~text
Source (upstream)
      |
      v
flatMap(...)
      |
      v
contextWrite(withAuthentication(alice))
      |
      v
Subscriber (downstream)

Context flows upstream from subscriber to source.
Data and onNext signals flow downstream from source to subscriber.
~~~

A valid example:

~~~java
Mono<String> username =
    Mono.just("start")
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Result: alice. contextWrite appears after flatMap in code, yet it supplies context to everything upstream (including flatMap).

### Placing contextWrite in the Wrong Position

~~~java
Mono<String> result =
    Mono.just("start")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice))
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("no-context"));
~~~

Result: no-context if no other context comes from the subscriber. contextWrite only modifies the context seen by the upstream Mono.just; flatMap sits downstream and therefore does not receive this SecurityContext.

Reactor is not dropping the context; the operator's scope was simply placed in the wrong location.

### Practical Rule

When explicitly attaching an Authentication for an entire pipeline (typically in tests or an intentional internal scope), place contextWrite downstream of all sources that need to read it. In normal WebFlux requests, let Spring Security filters populate the context; never set a request's Authentication from unverified data.

## 7. Context Across map, flatMap, and Async Branches

A service can build a multi-step pipeline:

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}

public Mono<String> loadGreeting() {
    return Mono.just("load")
        .flatMap(ignored -> currentUsername())
        .map(name -> "Hello " + name);
}
~~~

If loadGreeting() is invoked in a subscription containing alice's SecurityContext, the result is Hello alice. flatMap subscribes to the inner publisher via Reactor's machinery and forwards the context appropriately within the chain.

### publishOn and subscribeOn

~~~java
Mono<String> result =
    Mono.just("work")
        .publishOn(Schedulers.parallel())
        .flatMap(ignored -> currentUsername())
        .map(name -> "user:" + name)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

Result: user:alice. Switching execution threads via publishOn does not lose the subscriber Context.

Similarly, when using subscribeOn to switch the source subscription thread, Context still belongs to the subscription:

~~~java
Mono<String> result = currentUsername()
    .subscribeOn(Schedulers.boundedElastic())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
~~~

There is no need to copy Authentication into ThreadLocal simply because an operator runs on a different scheduler. A real boundary occurs only when code creates a completely independent subscription or leaves Reactive Streams.

## 8. Subscription Boundaries and Detached Tasks

A common mistake:

~~~java
public Mono<Void> triggerAction() {
    backgroundService.doWork().subscribe();
    return Mono.empty();
}
~~~

This creates a subscription detached from the HTTP request's chain:

- The caller no longer awaits completion/errors of doWork().
- Cancellation and timeouts are not coordinated properly.
- The request's SecurityContext does not necessarily propagate to the new subscription.
- Exceptions may only go to global error hooks/logs and become hard to observe.
- When the request finishes, ongoing work may be orphaned.

If the work must complete within the same request, return the publisher and compose:

~~~java
public Mono<Void> triggerAction() {
    return backgroundService.doWork();
}
~~~

If work must actually be queued, construct a command containing the verified identifier (or required identity/provenance), enqueue the command under a verified contract, and process it under the consumer's own security boundary. Do not assume an HTTP request's Reactor Context automatically crosses Kafka, RabbitMQ, scheduled jobs, or other processes.

## 9. CompletableFuture, Callbacks, and Blocking Libraries

Reactor Context does not automatically become ThreadLocal for arbitrary Java callbacks outside Reactor.

Dangerous example:

~~~java
CompletableFuture.supplyAsync(() ->
    SecurityContextHolder.getContext()
        .getAuthentication()
        .getName());
~~~

A common-pool thread does not necessarily hold the WebFlux request's SecurityContext; this code can throw NullPointerException or return the wrong identity if an unmanaged custom ThreadLocal strategy exists.

The safe approach is to read the principal inside the reactive pipeline and pass only the minimal required value:

~~~java
public Mono<Profile> findProfile() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            Mono.fromCallable(() -> legacyDao.findByUser(username))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

This is an illustrative fragment: legacyDao.findByUser is a blocking API in the application. BoundedElastic is more suitable than the event loop for bounded blocking operations; queue/thread capacity and timeouts must be controlled. Never copy full credentials onto a blocking thread when only the username is needed.

If a library supports Context Propagation or Micrometer ContextSnapshot, a bridge can be configured as needed for MDC, tracing, or specific ThreadLocals. This does not change the standard API for querying Spring Security in reactive code and does not guarantee every detached task automatically receives Authentication.

## 10. How Does Spring Security Create Context in WebFlux?

When an application uses spring-boot-starter-security and configures a reactive SecurityWebFilterChain, Spring Security processes HTTP requests via a WebFilter chain:

~~~text
HTTP request
      |
      v
SecurityWebFilterChain
      |
      +-- Authentication filter:
      |     Read Basic/Bearer/session credentials
      |     Authenticate via manager/provider
      |
      +-- SecurityContext persistence/loading:
      |     ServerSecurityContextRepository (as configured)
      |
      +-- ReactorContextWebFilter:
      |     Integrate SecurityContext into Reactor Context
      |
      +-- Authorization:
      |     Decide whether the request may proceed
      |
      v
Annotated controller / functional route
      |
      v
Service with ReactiveSecurityContextHolder
      |
      v
Reactive repository / downstream operations
~~~

This is a conceptual diagram and does not depict the exact order of every security filter. Details depend on HTTP Basic, OAuth2 Resource Server, session, form login, or custom filters.

In WebFlux Security, ReactorContextWebFilter integrates the SecurityContext from the repository into the Reactor Context. Authentication filters can also supply the appropriate context after authenticating. Application code does not need to manually call contextWrite(withAuthentication()) on every incoming HTTP request when Security is configured properly.

### Distinguishing Authentication and Authorization

- **Authentication:** verifies who the identity is.
- **Authorization:** verifies which actions the identity is permitted to perform.

Having an Authentication in the context does not automatically grant permission for every operation. Method security or authorization checks must still evaluate GrantedAuthority, tenant, ownership, and the target resource.

## 11. Reading Principal in Controllers and Services

In a WebFlux controller, several options exist:

~~~java
@GetMapping("/identity")
public Mono<String> identity(
        @AuthenticationPrincipal Mono<UserDetails> principal) {
    return principal.map(UserDetails::getUsername);
}
~~~

This injection example applies when the actual principal is UserDetails; with JWT, the principal is typically Jwt or provider-specific, so the signature must match. Do not assume every Authentication has a UserDetails principal.

A less coupled alternative is taking Principal:

~~~java
@GetMapping("/identity-name")
public Mono<String> identityName(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

When logic lives deep inside a service and you do not want to thread Principal through every method, ReactiveSecurityContextHolder.getContext() is the appropriate reactive approach:

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

For sensitive operations, prefer passing the verified user ID across service/repository boundaries if that clarifies authorization and reduces reliance on ambient context. Either way, never take a user ID from a query param as an implicit access grant.

## 12. Reactive Method Security

Spring Security supports @PreAuthorize on reactive methods when method security is enabled:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfiguration {
}
~~~

Service example:

~~~java
@Service
public class ReportsService {

    @PreAuthorize("hasRole('USER')")
    public Mono<String> report() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "report-for:" + auth.getName());
    }
}
~~~

When the caller has ROLE_USER, the publisher emits report-for:alice. When the caller only has ROLE_GUEST, reactive method security emits AccessDeniedException; HTTP security exception handling typically maps this to 403 Forbidden.

### Important Conditions

- The method must be invoked through a Spring AOP proxy so the interceptor protects it.
- With Spring Security reactive method security, protected methods should return Mono/Flux or a supported Publisher; do not expect identical semantics on synchronous String-returning methods.
- Do not call a @PreAuthorize method from another method in the same class and assume the proxy still applies; self-invocation can bypass advice.
- hasRole('USER') checks authority ROLE_USER using the default prefix.
- If permissions depend on a resource ID, add owner/tenant or fine-grained permission checks instead of relying solely on roles.

Method security uses the same Reactor Context, so a service call composed within an HTTP request reads the exact Authentication established by WebFlux Security.

## 13. When to Use withAuthentication or withSecurityContext?

In an HTTP request already processed by Spring Security, you normally **do not need** to call withAuthentication manually. Intentional scenarios include:

- Unit testing a publisher that requires Authentication.
- A reactive job with its own verified security boundary that needs to establish a local scope.
- Integration code that has already verified credentials through a trusted mechanism and bridges into a reactive API.
- Testing context isolation and operator placement.

Test example:

~~~java
Authentication testAuth =
    new UsernamePasswordAuthenticationToken(
        "test-user",
        "unused",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

StepVerifier.create(
        service.currentName()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(testAuth)))
    .expectNext("test-user")
    .verifyComplete();
~~~

Never do this:

~~~java
Authentication forged =
    new UsernamePasswordAuthenticationToken(
        request.getQueryParams().getFirst("username"),
        "n/a",
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
~~~

to populate an authentication context. Any caller could pass username=admin; this is a severe security vulnerability. Let the authentication manager verify credentials/identity and produce a trusted Authentication.

## 14. Outbound WebClient: Internal Context Is Not HTTP Authorization

Reactor Context exists only inside the process's reactive execution; it does not travel across TCP to another service.

If Service A's controller handles user alice and calls Service B via WebClient, Service A having ReactiveSecurityContextHolder does not mean Service B automatically receives the same SecurityContext. For Service B to know the identity, use an appropriate authentication protocol:

- Forward an OAuth2 access token when permitted by the security contract.
- Use token exchange or an on-behalf-of flow when required by the architecture.
- Use a service identity for machine-to-machine calls.
- Pass a trusted signed claim, never an arbitrary username header.

### Spring Security Bearer Token Propagation

With a reactive OAuth2 Resource Server, you can use ServerBearerExchangeFilterFunction:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder
        .filter(new ServerBearerExchangeFilterFunction())
        .baseUrl("https://downstream.example.com")
        .build();
}
~~~

This fragment requires OAuth2 Resource Server dependencies and importing org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction. It is not included in the complete HTTP Basic project below.

The filter looks up the current Authentication from the reactive security context and extracts an OAuth2 AbstractOAuth2Token credential to add Authorization: Bearer ... to the outbound request. With HTTP Basic Authentication, there is no bearer token to relay automatically. The filter also does not refresh expired tokens automatically.

### Security Warnings When Relaying Tokens

- Relay only to permitted destinations; avoid sending user tokens to untrusted hosts.
- Verify that the token audience and scopes fit the downstream service.
- Never log access tokens or place them carelessly into arbitrary Reactor Context entries.
- Never blindly copy the incoming Authorization request header to call arbitrary URLs.
- Token relay does not replace Service B's own authorization.
- For OAuth2 client authorization code flows, you may need OAuth2AuthorizedClientManager instead of simple bearer relay.

Context propagation within an application and token propagation across applications are two separate problems.

## 15. Context Across Parallel Processing and Concurrent Requests

Imagine two HTTP requests running nearly simultaneously:

~~~text
Request A: alice -------------------+
                                    |-- Reactor event-loop X
Request B: bob ---------------------+       |
                                    |    publishOn
                                    v       |
                                Scheduler Y
                                    |
                 Alice Context --> A operators
                 Bob Context   --> B operators
~~~

Both may execute on the same thread at different moments. If code uses an unmanaged ThreadLocal, it may read the wrong identity or null. Using Reactor Context within each subscription ensures each request receives its own context.

### Independent Context per Subscription

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> aliceFlow = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobFlow = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bob));
~~~

Both publishers share the `who` definition yet hold different contexts. Each subscription reads its respective context.

### Parallelism Does Not Mean Context Loss

Standard publishOn and subscribeOn preserve the Reactor subscriber Context within a reactive chain. Context loss typically stems from creating detached subscriptions, leaving Reactor APIs without passing needed data, or placing contextWrite in the wrong scope.

With parallel() and runOn(), still review operator design and concurrency; never try to fix it with a static thread-keyed map of user IDs.

## 16. Controlling Authentication Changes and Clearing Context

Reactor Context is immutable as a map, though the value stored inside it may be a mutable SecurityContext. When executing a branch under another trusted identity, enforce an explicit policy.

Examples:

~~~java
Mono<String> scoped = service.currentName()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(systemAuthentication));
~~~

This is valid only when systemAuthentication is created by a component authorized to do so, never from untrusted input.

If a branch must run without context:

~~~java
Mono<String> noContext = service.currentName()
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

When currentName() treats missing context as an error, this publisher emits an error. clearContext() does not erase global authentication, does not log out a browser session, and does not replace a logout handler. It only modifies the Context for upstream operators in that scope.

### Do Not Use Context to Bypass Permissions

Never mutate a user's Authentication or GrantedAuthority to bypass a @PreAuthorize check in business logic. SecurityContext must reflect the identity verified by the security boundary; any elevated privilege must have separate policy, auditing, and checks.

## 17. Complete Java 17+ Spring Boot WebFlux Example

The example builds an API with HTTP Basic authentication:

- GET /api/me: returns the current caller's name via ReactiveSecurityContextHolder.
- GET /api/async: switches schedulers with publishOn and reads context inside flatMap.
- GET /api/report: protected by reactive method security, requiring ROLE_USER.
- User alice with ROLE_USER.
- User eve with ROLE_GUEST.

The example uses simple Basic authentication to avoid complex OAuth2/JWT setup obscuring the focus on context propagation. Passwords prefixed with {noop} are **only for local learning**; never store passwords this way in production.

### Project Structure

~~~text
reactive-security-context-demo/
├── pom.xml
└── src
    ├── main/java/com/example/securitycontext
    │   ├── ReactiveContextApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── IdentityService.java
    │   └── IdentityController.java
    └── test/java/com/example/securitycontext
        └── ReactiveContextIntegrationTests.java
~~~

### pom.xml

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>reactive-security-context-demo</artifactId>
  <version>1.0.0</version>

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
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

Spring Boot 3.3.5 manages Spring Framework, Spring Security, and Reactor versions compatible with Java 17.

### ReactiveContextApplication.java

~~~java
package com.example.securitycontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
~~~

### SecurityConfiguration.java

~~~java
package com.example.securitycontext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}password")
            .roles("USER")
            .build();

        UserDetails eve = User.withUsername("eve")
            .password("{noop}password")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(alice, eve);
    }
}
~~~

SecurityWebFilterChain requires authentication for /api/**. HTTP Basic validates credentials on the request and creates the user's Authentication. Method security is enabled with AuthorizationManager. The code intentionally leaves default CSRF enabled; all illustrated APIs are GET, so no state-changing requests need CSRF token handling.

Never hardcode passwords or use {noop} in production. Use a proper password encoder and securely managed secret/user stores.

### IdentityService.java

~~~java
package com.example.securitycontext;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class IdentityService {

    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .filter(auth ->
                auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authenticated principal is required")));
    }

    public Mono<String> nestedOnAnotherScheduler() {
        return Mono.just("work")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUser())
            .map(username -> "async-user:" + username);
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> userReport() {
        return currentUser()
            .map(username -> "report-for:" + username);
    }
}
~~~

Explanation:

1. currentUser() reads Authentication from the reactive subscriber Context, not ThreadLocal.
2. Mono.justOrEmpty() handles cases where SecurityContext contains no Authentication.
3. AnonymousAuthenticationToken is filtered out; the service does not treat anonymous principals as logged-in users.
4. switchIfEmpty() turns missing authentication into an explicit exception rather than fabricating an identity.
5. nestedOnAnotherScheduler() switches execution threads and then invokes currentUser() inside flatMap.
6. userReport() uses @PreAuthorize to verify permissions before executing publisher logic.

### IdentityController.java

~~~java
package com.example.securitycontext;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me() {
        return identityService.currentUser()
            .map(username -> Map.of("user", username));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return identityService.nestedOnAnotherScheduler()
            .map(value -> Map.of("result", value));
    }

    @GetMapping("/report")
    public Mono<Map<String, String>> report() {
        return identityService.userReport()
            .map(value -> Map.of("result", value));
    }
}
~~~

The controller does not read a username from query params to decide permissions. All responses retrieve identity from the security context managed by Spring Security.

## 18. Integration Tests: Authentication, Scheduler Switching, and Method Security

Testing uses Spring Boot's WebTestClient. Real HTTP requests to an embedded server verify the security filter chain, controller, and service. StepVerifier tests create scoped Authentications to verify ReactiveSecurityContextHolder without HTTP requests.

### ReactiveContextIntegrationTests.java

~~~java
package com.example.securitycontext;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveContextIntegrationTests {

    @Autowired
    private WebTestClient client;

    @Autowired
    private IdentityService identityService;

    private Authentication authentication(
            String username,
            String role) {

        return new UsernamePasswordAuthenticationToken(
            username,
            "unused",
            AuthorityUtils.createAuthorityList(role));
    }

    @Test
    void httpBasicAuthenticationIsAvailableToController() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"user\":\"alice\"}");
    }

    @Test
    void contextSurvivesSchedulerChangeAndNestedFlatMap() {
        client.get()
            .uri("/api/async")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"result\":\"async-user:alice\"}");
    }

    @Test
    void reactiveMethodSecurityAllowsRoleUser() {
        client.get()
            .uri("/api/report")
            .headers(headers ->
                headers.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .json("{\"result\":\"report-for:alice\"}");
    }

    @Test
    void reactiveMethodSecurityRejectsGuestRole() {
        client.get()
            .uri("/api/report")
            .headers(headers ->
                headers.setBasicAuth("eve", "password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unauthenticatedHttpRequestIsRejected() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void contextWriteProvidesAuthenticationToPublisher() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectNext("unit-alice")
            .verifyComplete();
    }

    @Test
    void identityRemainsIsolatedAcrossSubscriptions() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");
        Authentication bob =
            authentication("unit-bob", "ROLE_USER");

        Mono<String> source = identityService.currentUser();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("unit-alice")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("unit-bob")
            .verifyComplete();
    }

    @Test
    void publisherKeepsContextAcrossSubscribeOn() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectNext("unit-alice")
            .verifyComplete();
    }

    @Test
    void clearContextRemovesUpstreamAuthentication() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> user = identityService.currentUser()
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(user)
            .expectError(AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void contextWriteDoesNotAffectDownstreamFlatMap() {
        Authentication alice =
            authentication("unit-alice", "ROLE_USER");

        Mono<String> result = Mono.just("work")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice))
            .flatMap(ignored ->
                ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .defaultIfEmpty("no-context"));

        StepVerifier.create(result)
            .expectNext("no-context")
            .verifyComplete();
    }
}
~~~

The tests do not use sleep or assert Thread.currentThread().getName(). What needs to be proven is that identity is read from the context after switching schedulers, not which named thread executed.

Run from the directory containing pom.xml:

~~~bash
mvn -q test
~~~

When all 10 tests pass, Maven exits with exit code 0. If Maven or JDK 17+ is absent, install the required tools first. This describes expected results; it does not substitute for running tests in your environment.

## 19. Running the Application and Testing HTTP

Start:

~~~bash
mvn spring-boot:run
~~~

By default the embedded server listens on localhost:8080 unless server.port is configured differently.

### Caller alice Checking Identity

~~~bash
curl -i -u alice:password http://localhost:8080/api/me
~~~

Expected response status: HTTP 200 OK.

~~~json
{"user":"alice"}
~~~

### Context Across Schedulers

~~~bash
curl -i -u alice:password http://localhost:8080/api/async
~~~

Expected response status: HTTP 200 OK.

~~~json
{"result":"async-user:alice"}
~~~

### Method Security for ROLE_USER

~~~bash
curl -i -u alice:password http://localhost:8080/api/report
~~~

Expected response status: HTTP 200 OK.

~~~json
{"result":"report-for:alice"}
~~~

### Caller eve Without ROLE_USER

~~~bash
curl -i -u eve:password http://localhost:8080/api/report
~~~

Expected response status: HTTP 403 Forbidden. The error body is handled by Spring Boot; do not assume a fixed JSON structure.

### Without Credentials

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected response status: HTTP 401 Unauthorized; it must never return {"user":"anonymousUser"} as authenticated data.

## 20. Common Context Propagation Mistakes

1. **Using SecurityContextHolder.getContext() in a reactive service.** ThreadLocal does not guarantee the right identity when the pipeline switches threads; use ReactiveSecurityContextHolder.
2. **Reading Authentication during singleton bean creation.** Startup does not belong to a specific request; read at subscription time or receive a trusted user ID via method parameters.
3. **Calling subscribe() manually in a controller/service.** Creates a detached subscription and breaks error/cancellation/context scopes; compose by returning Mono/Flux.
4. **Placing contextWrite before the read site in code order.** Downstream operators may not see the context; check the subscription direction.
5. **Assuming publishOn always drops context.** In a normal Reactor chain, the subscriber Context is preserved; never "fix" it with a static ThreadLocal.
6. **Assuming CompletableFuture automatically inherits SecurityContext.** Code outside Reactor does not automatically receive the subscriber Context; pass the minimal required data.
7. **Failing to handle Mono.empty() when getContext() is absent.** Can turn missing identity into null or implicit behavior; define the outcome/error explicitly.
8. **Treating an anonymous principal as an authenticated user.** AnonymousAuthenticationToken has specific semantics; enforce proper policy checks.
9. **Assuming authentication equals authorization.** Having a user does not mean having ROLE_USER or resource ownership.
10. **Calling withAuthentication from user input.** Easily allows principal spoofing and privilege escalation; only set from trusted authentication.
11. **Using @PreAuthorize without going through the proxy.** Self-invocation can bypass advice; call via a Spring bean or redesign.
12. **Using synchronous method security while expecting Reactor Context.** Reactive method security requires publisher-compatible methods; check versions and signatures.
13. **Forwarding Authorization automatically to every upstream.** Risks leaking bearer tokens; restrict destinations and audiences.
14. **Assuming ServerBearerExchangeFilterFunction works with HTTP Basic.** The filter relays OAuth2 bearer tokens; it does not mint bearer tokens from Basic credentials.
15. **Failing to check token audience/scope in Service B.** Relayed tokens still require independent authorization downstream.
16. **Logging Authentication.toString() or credentials.** May leak sensitive data; log only minimal user IDs and event IDs.
17. **Caching Mono<Authentication> or SecurityContext application-wide.** Can share context with the wrong user; scoped publishers must stay within their request/subscription.
18. **Launching background jobs via detached subscribe while expecting request context.** Use a queue and a dedicated security boundary.
19. **Failing to test with multiple distinct identities.** Context leakage is easy to miss; test alice/bob across two subscriptions.
20. **Failing to test contextWrite placement.** Positive and negative unit tests clarify upstream/downstream semantics.
21. **Using {noop} passwords in production.** That is only a demo shortcut; use proper password hashing and credential stores.
22. **Ignoring CSRF when deploying cookie-based browser authentication.** CORS and Reactor Context do not replace CSRF protection; evaluate based on the login mechanism.

## 21. Checklist for Designing Secure Reactive Applications

Before releasing a WebFlux API, verify:

- Does SecurityWebFilterChain authenticate requests before reaching controllers?
- Is ReactiveSecurityContextHolder used instead of SecurityContextHolder in reactive logic?
- Does Authentication come from a trusted mechanism, not a query param?
- How does the service handle an empty getContext()?
- Are anonymous, authenticated, and authorized clearly distinguished?
- Is contextWrite placed downstream of operators that need to read the context?
- Are there any detached subscribe() calls outside the HTTP request lifecycle?
- Have publishOn/subscribeOn and flatMap been tested with context?
- Do CompletableFuture or blocking libraries receive user IDs via explicit parameters?
- Are @PreAuthorize methods invoked through a Spring proxy?
- Do protected methods return appropriate Mono/Flux types?
- Does outbound WebClient relay tokens selectively without sending them to arbitrary hosts?
- Do relayed tokens match the target audience/scopes?
- Are credentials or raw tokens logged in MDC or exceptions?
- When creating a system identity, are granting policies and auditing in place?
- Do unit tests verify the same publisher with two different Authentications?
- Do HTTP integration tests verify 200, 401, and 403 responses?
- Are user identity and resource ownership evaluated separately where needed?
- Are cleanup and cancellation handled for background work?
- Does production have proper password encoding/secret management and TLS?

## 22. Self-Check Exercises

**Question 1.** Why is ThreadLocal insufficient for Spring WebFlux?  
**Answer:** A reactive request can run across multiple threads; ThreadLocal does not automatically follow the subscription.

**Question 2.** Which API reads the reactive subscriber's SecurityContext?  
**Answer:** ReactiveSecurityContextHolder.getContext() returning Mono<SecurityContext>.

**Question 3.** What does withAuthentication() return?  
**Answer:** A Reactor Context containing a new Mono<SecurityContext> corresponding to the supplied Authentication.

**Question 4.** Does contextWrite affect upstream or downstream operators?  
**Answer:** Upstream, following the subscription's context propagation direction.

**Question 5.** Does publishOn automatically erase the Reactor Context?  
**Answer:** Not in a normal Reactor chain; the subscriber Context remains readable.

**Question 6.** What problems does calling subscribe() manually cause?  
**Answer:** It creates an independent subscription, breaks error/cancellation coordination, and may lose the request's security context.

**Question 7.** Which context does reactive method security use?  
**Answer:** The Reactor Context provided by ReactiveSecurityContextHolder.

**Question 8.** What authority does @PreAuthorize("hasRole('USER')") check by default?  
**Answer:** ROLE_USER.

**Question 9.** What happens to getContext() if no context exists?  
**Answer:** The Mono may complete empty; the service should define appropriate handling for missing authentication.

**Question 10.** Does Reactive Context automatically travel across WebClient to another microservice?  
**Answer:** No; a token or service identity mechanism over the network protocol is required.

**Question 11.** What is ServerBearerExchangeFilterFunction used for?  
**Answer:** In a reactive OAuth2 resource server, it retrieves the appropriate bearer token from the current Authentication and attaches it to outbound HTTP requests.

**Question 12.** Should withAuthentication be used to elevate privileges from a username in the request?  
**Answer:** No; that is authentication spoofing and creates a privilege escalation vulnerability.

**Question 13.** Does clearContext() log out an HTTP session?  
**Answer:** No; it only removes the security key within the Reactor Context scope where it is applied.

**Question 14.** Can context be tested with StepVerifier?  
**Answer:** Yes; use contextWrite(withAuthentication(testAuth)) and assert the results upon subscription.

**Question 15.** Why can an authenticated user still receive 403?  
**Answer:** Because the user lacks the authority, role, or resource permission required by the endpoint/method.

## 23. Key Takeaways

Reactive Spring Security places SecurityContext in the subscriber's Reactor Context. ReactiveSecurityContextHolder.getContext() is the primary query API; withAuthentication() and withSecurityContext() set context within a specified scope; clearContext() removes the key within that scope. Do not use ThreadLocal SecurityContextHolder as the identity source for a WebFlux reactive pipeline.

contextWrite affects upstream; standard map, flatMap, publishOn, and subscribeOn preserve the subscriber Context when all work stays within the same reactive chain. Conversely, manual subscribe(), background jobs, and callbacks outside Reactor create new boundaries where identity must be handled explicitly.

In WebFlux HTTP, SecurityWebFilterChain authenticates and injects context into the chain. Reactive method security checks permissions against that same context; authentication does not replace authorization. When calling other services via WebClient, Reactor Context does not cross the network automatically: only relay OAuth2 tokens to permitted destinations or use a properly contracted service identity.

The best way to verify is to write unit tests for contextWrite, clearContext, and two subscribers with different identities, alongside HTTP integration tests confirming 200, 401, and 403 outcomes and context preservation across scheduler switches.

### References

- Spring Security, [Reactive method security](https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html).
- Spring Security, [Reactive WebFlux security](https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html).
- Spring Security Javadoc, [ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- Spring Security, [OAuth2 Resource Server – Bearer Token Propagation](https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/resource-server/bearer-tokens.html).
- Project Reactor, [Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- Project Reactor, [Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
- Spring Framework, [Annotated Controllers and Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html).
- Spring Boot, [Testing Web Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
