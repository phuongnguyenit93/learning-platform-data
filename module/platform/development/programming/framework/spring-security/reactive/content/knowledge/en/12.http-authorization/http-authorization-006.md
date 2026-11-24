# ReactiveAuthorizationManager<AuthorizationContext> and AuthorizationDecision

## 1. What Problem Does This Lesson Solve?

In **Spring Security Reactive (Spring WebFlux)**, authentication answers the question *who is calling the API?*; HTTP authorization answers the question *is that caller allowed to access this request?*. Common conditions such as `authenticated()`, `hasRole("ADMIN")`, or `hasAuthority("orders:read")` are often sufficient. However, real-world policies may need to evaluate **the current user + HTTP path + path variables + resource state or tenant**. In those cases, Spring Security provides the `ReactiveAuthorizationManager<T>` contract to return an asynchronous decision.

This lesson focuses on two exact concepts:

- **`ReactiveAuthorizationManager<AuthorizationContext>`**: the decision component for a WebFlux HTTP request, receiving `Mono<Authentication>` and `AuthorizationContext`, attached via `ServerHttpSecurity.authorizeExchange(...).access(...)`.
- **`AuthorizationDecision`**: a result with `isGranted()`, indicating allow or deny; in Spring Security 6.4+ it implements `AuthorizationResult`.

By the end of this lesson, you can:

1. Explain the flow **authentication → authorization → continue WebFilterChain or deny**.
2. Distinguish `AuthorizationContext.getExchange()` from `getVariables()` and understand how path variables are extracted by matchers.
3. Distinguish `Mono.just(new AuthorizationDecision(true))`, `false`, `Mono.empty()`, and `Mono.error(...)`.
4. Understand the difference between `check(...)` in Spring Security **6.5.x** and `authorize(...)` in **7.x**, avoiding mixing incompatible signatures.
5. Configure a custom policy via `pathMatchers(...).access(manager)`, combining normal routes with a deny-by-default policy.
6. Write a manager that checks owner or admin without confusing an anonymous token's `isAuthenticated()` with a real login.
7. Build a runnable Spring Boot 3.x / Spring Security 6.5.x Java 17+ application, testing 401/403/200 and policies with `WebTestClient`/`StepVerifier`.
8. Avoid vulnerabilities involving **client-controlled paths**, blocking queries on the event loop, request authorization substituting for object authorization, tenant permissions, and fail-open bugs.

**Parent context:** HTTP Authorization. This lesson covers only **inbound WebFlux**; do not copy Servlet's `AuthorizationManager<RequestAuthorizationContext>` or `HttpSecurity.authorizeHttpRequests`. The demo is intentionally written for Spring Security **6.5.x** running on Spring Boot **3.x**; Section 4 shows how to migrate the contract to Security 7.x.

## 2. The Big Picture: Authenticate First, Authorize Second

Conceptual flow:

```text
Client -> GET /projects/alice
             |
             v
       Spring WebFlux WebFilters
             |
             v
       Spring Security WebFilterChainProxy
             |
             +-- Authentication filter
             |     Basic / Bearer / session / login ...
             |     -> Authentication (principal + authorities)
             |
             +-- Reactor Context / ReactiveSecurityContextHolder
             |
             +-- AuthorizationWebFilter
                   -> select rule in authorizeExchange(...)
                   -> ReactiveAuthorizationManager<AuthorizationContext>
                         Authentication + AuthorizationContext
                         -> Mono<AuthorizationDecision>
                   -> GRANTED ? continue request : access denied
             |
             +-- controller / service / repository if permitted
```

The diagram describes logical roles, **not a complete description of the physical order of every filter**. `AuthorizationWebFilter` handles authorization for the inbound exchange per configuration; `ExceptionTranslationWebFilter` helps translate appropriate access failures into HTTP responses.

Points to keep clear:

- **Authentication**: an `Authentication` verified by the framework; for example, principal `alice` with `ROLE_USER`.
- **Authorization**: the outcome of the policy evaluating the request. The same principal `alice` can access `/projects/alice` but not `/projects/bob`.
- **Role/authority**: `hasRole("ADMIN")` conventionally checks `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` checks the exact string.
- **Response**: `AuthorizationDecision(false)` itself is **not** `HTTP 403`. Filters and entry points/access-denied handlers decide the HTTP status based on authentication state and configuration.

In the hands-on exercise, HTTP Basic is enabled for easy testing. For a client **without credentials**, a request requiring authentication usually receives **401 Unauthorized**. For a logged-in user denied by policy, it usually receives **403 Forbidden**. A form-login configuration may redirect **302** instead of 401 for unauthenticated users. Do not hardcode statuses inside the manager via `setStatusCode`; let the security pipeline handle it.

## 3. Contract of ReactiveAuthorizationManager

### 3.1. Overview of Generic Type T

`ReactiveAuthorizationManager<T>` is a strategy usable for multiple access-controlled targets. `T` represents the **object being authorized**:

- For **WebFlux HTTP `.access(...)` rules**, `T` is typically `AuthorizationContext`.
- For other authorization mechanisms, `T` may differ, such as method invocation; do not replace `AuthorizationContext` with an arbitrary object inside `authorizeExchange`.
- `ReactiveAuthorizationManager` differs from the synchronous `AuthorizationManager<T>` contract of Servlet/some method security paths.

In Spring Security 6.5, notice the signature:

```java
// Abbreviated API from Spring Security 6.5.x for explanation.
// Do not redeclare this interface yourself in a project.
public interface ReactiveAuthorizationManager<T> {

    @Deprecated
    Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        T object
    );

    default Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        T object
    ) {
        // Default 6.5 implementation delegates to check(...)
        // and returns AuthorizationResult.
        throw new UnsupportedOperationException("diagram only");
    }

    default Mono<Void> verify(
        Mono<Authentication> authentication,
        T object
    ) {
        throw new UnsupportedOperationException("diagram only");
    }
}
```

**Important:** This is *signature-explanatory pseudocode*; `throw` and method bodies are placeholders not meant for compilation/implementation; **do not copy into source**. Spring Security provides the real implementations. In **6.5.x**, `check(...)` is still the method you must implement when writing a class implementing the interface, even though it has been `@Deprecated` since **6.4**, while `authorize(...)` is the default method recommended when **calling** a manager. This differs from 7.x.

`check` returns `Mono<AuthorizationDecision>`. `authorize` returns `Mono<AuthorizationResult>`: an interface type allowing additional authorization result forms without coupling callers to one concrete class. `AuthorizationDecision` remains a valid implementation of `AuthorizationResult`. `verify` represents the verification/denial-enforcement contract, returning `Mono<Void>` on success or signaling an error if permission is not granted per policy.

### 3.2. The Two HTTP Parameters

```java
Mono<Authentication> authentication
AuthorizationContext context
```

`authentication` is a **publisher** holding the authentication info for the reactive request, not a synchronous `Authentication`. Never call `authentication.block()` during a request; doing so can block the Netty event loop, lose context, or cause runtime errors.

`context` provides:

- `context.getExchange()`: `ServerWebExchange`, allowing reading method, URL, headers, and request attributes per contract.
- `context.getVariables()`: `Map<String,Object>` containing **URI template variables extracted by the matcher**, e.g., pattern `/projects/{owner}` and request `/projects/alice` yields `owner = "alice"`.

`AuthorizationContext.getVariables()` is not a map of every request parameter; it holds the rule matcher's variables. When a policy needs values from query/headers/body, you must carefully decide how to read data safely and assess risks. For requests with streaming bodies, **do not read and consume the body inside an authorization manager** expecting the controller to still read it normally.

### 3.3. AuthorizationDecision and isGranted

```java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);

boolean a = allow.isGranted(); // true
boolean b = deny.isGranted();  // false
```

`AuthorizationDecision` is an **authorization result**, not an object carrying new roles, a new session, or an HTTP response. If the manager returns allow, it only lets the request proceed through the security filter; the service/repository must still protect the real resource. If the manager returns deny, it denies access via the standard mechanism rather than returning a `"false"` body to the client.

In 6.4+/7.x, `AuthorizationResult` is the abstraction with `isGranted()`; `AuthorizationDecision` implements this interface. Therefore, code reading results from `authorize(...)` should prefer `AuthorizationResult` rather than downcasting back to `AuthorizationDecision`.

### 3.4. Four Reactive Results with Distinct Meanings

| Publisher Value | Meaning | Key Reminder |
|---|---|---|
| `Mono.just(new AuthorizationDecision(true))` | **allow** decision | Security filter may continue the chain |
| `Mono.just(new AuthorizationDecision(false))` | **deny** decision | Security pipeline will deny via the appropriate entry point/denied handler |
| `Mono.empty()` | Manager **abstained / made no decision** | Do not use as a "default deny"; combining decisions depends on consumer/implementation |
| `Mono.error(error)` | Check encountered an **error** | No boolean decision; error propagates/is handled by pipeline |

**Do not** use `Mono.empty()` to represent an unauthorized user. It represents **no decision**, and when combining managers, `switchIfEmpty`/`filter` have specific semantics; always choose an explicit fail-closed approach for sensitive resources.

**Do not** turn exceptions from calling a policy service into `new AuthorizationDecision(true)`. Database/permission backend failures must fail closed or translate into appropriate application errors; masking errors as allow creates an authorization vulnerability.

### 3.5. Mono Executes on Subscription, Not Declaration

A manager should return a publisher, for example:

```java
return authentication.map(auth ->
    new AuthorizationDecision(hasRequiredAuthority(auth)));
```

`hasRequiredAuthority` here is a helper you define; the snippet is not standalone runnable. Do not call `subscribe()` inside a manager and return `Mono.just(true)`: a detached subscription loses error handling, cancellation, and Reactor Context. If you need to read a reactive repository, compose with `flatMap`/`map`/`switchIfEmpty`/`onErrorMap` per the specific policy.

## 4. Differences Between 6.5 and 7.x: Avoid Copying the Wrong Signature

This is **very important** when learning from articles of different ages.

| Spring Security | Method Implemented in Manager Class | Return Type | Notes |
|---|---|---|---|
| 5.x–6.3 | `check(Mono<Authentication>, T)` | `Mono<AuthorizationDecision>` | Pre-6.4 improvement API |
| 6.4–6.5 | `check(...)` (deprecated but still abstract) | `Mono<AuthorizationDecision>` | New default `authorize(...)` exists, returning `Mono<AuthorizationResult>` |
| 7.x | `authorize(Mono<Authentication>, T)` | `Mono<AuthorizationResult>` | Use the new contract; do not keep old `check(...)` override |

With Spring Boot 3.x/Java 17 in the demo below, we write the **exact 6.5 API**:

```java
@Override
@SuppressWarnings("deprecation")
public Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context) {
    return authentication
        .map(auth -> new AuthorizationDecision(auth.isAuthenticated()))
        .defaultIfEmpty(new AuthorizationDecision(false));
}
```

This snippet explains the signature; **real policy logic must handle anonymous tokens**, rather than relying on `auth.isAuthenticated()` alone. The complete class in Section 7 handles that.

When moving to **Spring Security 7.x**, the class must implement the new signature, e.g., this method snippet:

```java
@Override
public Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        AuthorizationContext context) {
    return authentication
        .map(auth -> (AuthorizationResult)
            new AuthorizationDecision(isAllowed(auth, context)))
        .defaultIfEmpty(new AuthorizationDecision(false));
}
```

Above, `isAllowed` is a policy helper you must write, and the code only illustrates the **7.x API**; it cannot be used verbatim as a 6.5 class. Distinguish `@Override` from merely adding a similarly named method that is **no longer the interface contract**. When upgrading versions, the compiler must be the first check, followed by re-testing manager behavior and filter integrations.

**Practical rule:** read the Javadoc of the **exact version present in your dependency tree**, not only the "current" page. An online example using `authorize(...)` for 7.x may fail to compile if you implement a 6.5 class with only that method. The goal of this lesson is mastering the contract and proper migration, not mixing two API generations.

## 5. AuthorizationContext: What Information Is Passed into the Policy?

### 5.1. Exchange and URI Variables

When configuring:

```java
.pathMatchers(HttpMethod.GET, "/projects/{owner}")
.access(ownerAuthorizationManager)
```

Spring Security uses the corresponding matcher, and `AuthorizationContext` may contain the `owner` variable extracted from the path. Inside the manager:

```java
String owner = context.getVariables().get("owner") instanceof String s
    ? s
    : null;

String method = context.getExchange()
    .getRequest().getMethod().name();

String path = context.getExchange()
    .getRequest().getPath().value();
```

This is a Java 17+ snippet depending on a real `AuthorizationContext`. If `owner` is absent due to another matcher/route, **deny** instead of assuming `owner` always exists. Never pull `owner` from an arbitrary client-sent query string and treat it as proof of ownership.

### 5.2. Distinguishing Path Variables from Trusted Data

`/projects/alice` contains a string **chosen by the client**. It does not prove the request actually belongs to Alice's resource. An `auth.getName().equals(owner)` policy can be useful for user-namespaced demo routes, but in real production systems:

- A project may have an owner stored in the database that differs from the path username.
- Admins, members, tenants, and resource-level ACLs may require other conditions.
- URLs can be renamed, IDs can be guessed, and queries/bodies can assert untrusted claims.
- HTTP-layer authorization must be reinforced in the service/repository, especially when the same service is invoked by jobs, message consumers, or other endpoints.

A more trustworthy policy extracts `projectId` from the URL and **looks up owner/tenant/ACL in the repository** via a reactive query, denying if the resource does not exist or permissions are insufficient. For sensitive cases, separate 403 and 404 according to anti-enumeration policies, rather than allowing access merely because a path contains a username matching the caller.

### 5.3. Inspecting Headers Is Not Trusting Headers

`context.getExchange().getRequest().getHeaders()` lets you read headers. However, client-sent `X-User`, `X-Role`, and `X-Tenant` **do not automatically become trusted principals/authorities**. If the architecture uses a reverse proxy injecting trusted identity headers, accept them only over verified network boundaries and proxy authentication, never trusting public headers from the Internet. By default, policies should rely on the `Authentication` verified by Spring Security and resource data from trusted sources.

## 6. Wiring a Custom Manager into authorizeExchange

Partial configuration example:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/public").permitAll()
        .pathMatchers(HttpMethod.GET, "/projects/{owner}")
            .access(ownerAuthorizationManager)
        .anyExchange().denyAll())
    .httpBasic(Customizer.withDefaults())
    .formLogin(form -> form.disable())
    .build();
```

This is a **snippet** inside a `@Bean SecurityWebFilterChain` method; the full code with imports and beans is in Section 7.

Key rules:

1. `authorizeExchange` evaluates rules in **declaration order**; a request uses the first matching rule. Place specific patterns before catch-alls.
2. `permitAll()` allows public content; `authenticated()` only requires authentication; `hasRole(...)`/`hasAuthority(...)` handle simple permissions; `access(...)` is the hook for custom policies.
3. `anyExchange().denyAll()` acts as a **fail-closed** default, avoiding accidentally exposing new URLs.
4. Once `.pathMatchers("/projects/{owner}").access(manager)` is declared, do not expect a subsequent `.pathMatchers("/projects/{owner}").authenticated()` to "AND" into the policy: the first rule already matched. The manager itself must handle unauthenticated/anonymous cases properly.
5. A request that **does not match** the path pattern will not reach that rule's custom manager; subsequent rules decide.
6. If multiple `SecurityWebFilterChain` beans use different `securityMatcher`s, check which chain actually applies before analyzing rules inside the chain.

### 6.1. Built-In Managers Can Be Used as Policy Building Blocks

Spring Security provides `AuthorityReactiveAuthorizationManager.hasAuthority("...")`, `hasRole("...")`, and other built-in policies. For multiple conditions, you can compose publishers instead of reimplementing checks for every authentication type.

Illustrative snippet requiring **both** `ADMIN` and `DBA` roles per the 6.5 API:

```java
ReactiveAuthorizationManager<AuthorizationContext> admin =
    AuthorityReactiveAuthorizationManager.hasRole("ADMIN");
ReactiveAuthorizationManager<AuthorizationContext> dba =
    AuthorityReactiveAuthorizationManager.hasRole("DBA");

return admin.check(authentication, context)
    .flatMap(first -> {
        if (!first.isGranted()) {
            return Mono.just(new AuthorizationDecision(false));
        }
        return dba.check(authentication, context);
    })
    .defaultIfEmpty(new AuthorizationDecision(false));
```

This is a snippet inside a custom policy method, not a standalone class. In 6.5 `check` is deprecated but still present; in new calling code, `authorize` is generally more appropriate and returns `AuthorizationResult`. Note: if the same cold `Mono<Authentication>` is subscribed to multiple times, examine semantics and optimize per workflow; the complete demo in Section 7 reads `Authentication` **only once**.

Do not use `Mono.when(...)` to AND two boolean decisions: `Mono.when` waits for completion and ignores the sources' true/false values, potentially allowing unauthorized requests through.

### 6.2. AND/OR and "Abstain" Cannot Be Combined Arbitrarily

Examples of desired logic:

- **AND:** allow if the caller is a real user AND has scope `orders:read` AND has permission on the resource.
- **OR:** allow if the caller is an admin **or** is the actual owner.
- **Deny:** if there is no identity, missing owner/ACL data, insufficient permissions, or unclear conditions.
- **Error:** if the authorization backend fails, do not silently turn it into allow; fail closed / return 5xx per design.

`filter(AuthorizationResult::isGranted).switchIfEmpty(...)` is easily misunderstood because `filter` turns a deny result into **empty**, which `switchIfEmpty` then treats as no decision. That can work in a tightly designed OR pipeline, yet is dangerous if a deny is accidentally treated as "fall back to default allow". Write tests for every combination and choose an explicit default deny.

## 7. Runnable Spring Boot 3.x + Security 6.5.x + Java 17+ Project

We will build this policy:

> `GET /projects/{owner}` is permitted only if called by the **authenticated owner**, or by a user with authority `ROLE_ADMIN`. Unauthenticated callers, missing `owner` variable, or other non-admin users are denied.

This example is small enough to run and clearly observe `ReactiveAuthorizationManager<AuthorizationContext>` / `AuthorizationDecision`; it does **not** represent a complete production resource-ownership policy.

### 7.1. Initializing the Project

Use [Spring Initializr](https://start.spring.io/) to generate a Gradle Groovy project with **Spring Boot 3.5.x**, **Java 17+**, and dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, **Spring Security Test**, and **Reactor Test**. Spring Boot 3.5.x typically manages Spring Security 6.5.x; check `./gradlew dependencies` to confirm the exact minor version before running.

In the `build.gradle` generated by Initializr, the dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is only the **dependencies block**, not the entire Gradle file. Keep the Spring Boot plugins, Java toolchain, repositories, and Gradle wrapper generated by Initializr. Do not add `spring-boot-starter-web` to the demo: when both Servlet and WebFlux starters are present, Boot 3 typically selects inbound MVC/Servlet.

Structure:

```text
src/main/java/demo/reactiveauthz/
  ReactiveAuthzApplication.java
  SecurityConfig.java
  OwnerAuthorizationManager.java
  ProjectController.java
src/test/java/demo/reactiveauthz/
  OwnerAuthorizationIntegrationTests.java
  OwnerAuthorizationManagerTests.java
```

### 7.2. `ReactiveAuthzApplication.java`

```java
package demo.reactiveauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthzApplication.class, args);
    }
}
```

### 7.3. `OwnerAuthorizationManager.java`: Core Policy

```java
package demo.reactiveauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class OwnerAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object variable = context.getVariables().get("owner");
        String owner = variable instanceof String value ? value : null;

        if (owner == null || owner.isBlank()) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .map(auth -> new AuthorizationDecision(
                isRealUser(auth) &&
                (hasAuthority(auth, "ROLE_ADMIN")
                    || owner.equals(auth.getName()))
            ))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(
            Authentication authentication,
            String authority) {
        return authentication.getAuthorities().stream()
            .anyMatch(granted ->
                authority.equals(granted.getAuthority()));
    }
}
```

This is a **complete Spring Security 6.5.x class** with all required imports. Analysis:

- `ReactiveAuthorizationManager<AuthorizationContext>` receives the context of the HTTP rule being evaluated.
- `context.getVariables().get("owner")` fetches the pattern variable; missing or non-String values **deny**. Avoid unsafe casts that lead to `ClassCastException`.
- `Mono<Authentication>` is transformed with `map`, **without blocking**.
- `isRealUser` excludes anonymous tokens. Never trust `Authentication.isAuthenticated()` alone: in certain configurations, `AnonymousAuthenticationToken.isAuthenticated()` can be `true` even though it is not a logged-in user.
- If the user is an admin or the principal matches `owner`, it returns `new AuthorizationDecision(true)`; otherwise false.
- `defaultIfEmpty(false)` is an **explicit deny** if the publisher emits no `Authentication`.
- Does not take roles from an `X-Role` HTTP header; authorities come from the authentication mechanism trusted by Spring Security.
- `@SuppressWarnings("deprecation")` is specifically because 6.5 requires implementing `check(...)` even though it is deprecated. When migrating to Security 7.x, update as shown in Section 4.

**Limitation of the demo:** comparing the path owner with `Authentication.getName()` makes sense when routes are designed around usernames. With real resource IDs, owner/tenant/ACL must be fetched from a trusted database; users can alter paths, and a URL itself is not proof of resource ownership.

### 7.4. `SecurityConfig.java`: Attaching the Manager to HTTP Policy

```java
package demo.reactiveauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            OwnerAuthorizationManager ownerManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/projects/{owner}")
                    .access(ownerManager)
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }
}
```

Notes:

1. `GET /public` is permitted for everyone.
2. `GET /projects/{owner}` invokes `OwnerAuthorizationManager`. The pattern variable `{owner}` is extracted into `AuthorizationContext.getVariables()`.
3. `anyExchange().denyAll()` denies undeclared URLs/methods.
4. HTTP Basic sends credentials on each request for easy `curl` testing, **without encrypting passwords**: HTTP Basic must run over HTTPS in production. `formLogin` is disabled so API clients do not receive HTML redirects instead of 401.
5. Example passwords are hashed via `PasswordEncoderFactories`; never store sample credentials in real projects.
6. Alice and Bob have `ROLE_USER`, while `admin` has `ROLE_ADMIN`. The policy allows admin or owner without requiring every owner to have `ROLE_USER` (though they must still be a real authenticated user); this is specific to this exercise's design.
7. Default CSRF protection is not disabled; the demo endpoints only use GET, so no POST requests requiring tokens arise.

If a request carries no credentials, `AuthorizationWebFilter` does not grant any roles; the policy returns deny. With `httpBasic` enabled, the typical security entry point returns 401. If Alice sends credentials yet requests `/projects/bob`, the false decision leads to 403. There is no need for the controller to write `if (user.equals(...))` to simulate HTTP-layer blocking.

### 7.5. `ProjectController.java`

```java
package demo.reactiveauthz;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProjectController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/projects/{owner}")
    public Mono<String> project(@PathVariable String owner) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(principal ->
                "projectOwner=" + owner + ";principal=" + principal);
    }
}
```

The controller only returns illustrative content. When user Alice calls `/projects/alice`, the body is `projectOwner=alice;principal=alice`. When `admin` calls `/projects/bob`, the body is `projectOwner=bob;principal=admin`. This makes it clear that **the owner in the URL** and **the actual authenticated identity** are two distinct values.

Do not rely on this controller to protect real project data: real data must be queried by tenant/ACL verified in the service/repository; HTTP rules are **one layer** of defense, insufficient for internal operations that do not go through HTTP.

### 7.6. Running the Application and Verifying Responses

From the root of the Initializr project:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Call the API:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/projects/alice
curl -i -u alice:alice-pass http://localhost:8080/projects/alice
curl -i -u alice:alice-pass http://localhost:8080/projects/bob
curl -i -u bob:bob-pass http://localhost:8080/projects/bob
curl -i -u admin:admin-pass http://localhost:8080/projects/bob
curl -i -u alice:alice-pass http://localhost:8080/not-configured
```

If PowerShell has a `curl` alias, use `curl.exe`. Never pass real passwords directly in shell commands because they can be recorded in shell history/process lists; these are demo credentials.

Expected:

| Request | HTTP status | Body on 200 |
|---|---:|---|
| No auth: `GET /public` | 200 | `public` |
| No auth: `GET /projects/alice` | 401 | Not fixed |
| Alice: `GET /projects/alice` | 200 | `projectOwner=alice;principal=alice` |
| Alice: `GET /projects/bob` | 403 | Not fixed |
| Bob: `GET /projects/bob` | 200 | `projectOwner=bob;principal=bob` |
| Admin: `GET /projects/bob` | 200 | `projectOwner=bob;principal=admin` |
| Alice: `GET /not-configured` | 403 | Not fixed |

HTTP status and challenge headers are influenced by entry point/access-denied handler configuration; these values are **expected for the demo configuration**. Do not assert default 401/403 response bodies because the format may change across versions.

## 8. End-to-End Testing with WebTestClient

Authorization lessons need tests for **HTTP outcomes**: a policy might return the right boolean while the security chain/route matcher never calls it due to wrong config order. `WebTestClient` runs through the WebFlux security chain and verifies status/body like a real client.

Create `src/test/java/demo/reactiveauthz/OwnerAuthorizationIntegrationTests.java`:

```java
package demo.reactiveauthz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OwnerAuthorizationIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void unauthenticatedUserCannotAccessProject() {
        client.get().uri("/projects/alice")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnProject() {
        client.get().uri("/projects/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=alice;principal=alice");
    }

    @Test
    void ordinaryUserCannotReadAnotherProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void secondOwnerCanReadOwnProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("bob", "bob-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=bob;principal=bob");
    }

    @Test
    void adminCanReadAnotherUsersProject() {
        client.get().uri("/projects/bob")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("projectOwner=bob;principal=admin");
    }

    @Test
    void denyAllCatchesUnlistedRoute() {
        client.get().uri("/not-configured")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

These tests verify 7 scenarios: public, anonymous, owner, another user, second owner, admin, and an unlisted route outside policy. The tests **do not use `mockUser`**, instead sending real HTTP Basic credentials to the in-memory user store, thus integrating both authentication and authorization. The tests return 401/403 at the security layer before the controller.

### 8.1. Unit Testing the Manager Itself with StepVerifier

Integration tests are crucial, yet to catch detailed logic bugs (e.g., missing `owner` variable, empty authentication publisher), we unit-test the manager directly. Create `src/test/java/demo/reactiveauthz/OwnerAuthorizationManagerTests.java`:

```java
package demo.reactiveauthz;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OwnerAuthorizationManagerTests {

    private final OwnerAuthorizationManager manager =
        new OwnerAuthorizationManager();

    private Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private Authentication admin() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "admin", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
    }

    private AuthorizationContext contextWithOwner(String owner) {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/projects/" + owner).build());
        return new AuthorizationContext(
            exchange, Map.of("owner", owner));
    }

    @Test
    void ownerIsGranted() {
        StepVerifier.create(manager.check(
                Mono.just(alice()), contextWithOwner("alice")))
            .assertNext(decision ->
                assertTrue(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void anotherOwnerIsDenied() {
        StepVerifier.create(manager.check(
                Mono.just(alice()), contextWithOwner("bob")))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void administratorIsGranted() {
        StepVerifier.create(manager.check(
                Mono.just(admin()), contextWithOwner("alice")))
            .assertNext(decision ->
                assertTrue(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void emptyAuthenticationIsDenied() {
        StepVerifier.create(manager.check(
                Mono.empty(), contextWithOwner("alice")))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }

    @Test
    void missingOwnerVariableIsDenied() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/projects/alice").build());
        var context = new AuthorizationContext(exchange, Map.of());

        StepVerifier.create(manager.check(Mono.just(alice()), context))
            .assertNext(decision ->
                assertFalse(decision.isGranted()))
            .verifyComplete();
    }
}
```

This is a JUnit5 class requiring `spring-boot-starter-test`, `reactor-test`, and `spring-security-test` per the dependencies in Section 7. Double-check: the `AuthorizationContext(exchange, variables)` constructor exists in the WebFlux Security API, and `MockServerWebExchange` is in Spring Framework's test library.

Unit tests only call `manager.check` with a trusted mocked `Authentication` *within test scope*; they **do not** prove real passwords are verified. Integration tests handle that part. On Spring Security 7.x, test the `authorize` method with `AuthorizationResult` directly instead of `check`.

Run:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

Expect **12 tests to pass** (7 integration and 5 unit) with the configuration shown, provided the project uses the proper Spring Boot 3.5 / Spring Security 6.5, Java 17, and dependencies. This is the **expected result from the source code**, not a claim that the tests have been run. Do not assert thread names or default 401/403 body contents. If results differ, check versions, actual HTTP status/headers, rule matchers, and classpath.

## 9. AuthorizationDecision Does Not Replace Protecting Real Resources

### 9.1. Preventing IDOR/BOLA

The `/projects/{owner}` path is illustrative. In real project management apps, URLs are typically `/projects/{id}`. Users can guess or swap `id`; if a policy only checks `auth.isAuthenticated()`, the request risks **IDOR/BOLA (Broken Object Level Authorization)**.

A better design:

```text
GET /projects/853
  -> Authentication principal + tenant membership
  -> AuthorizationContext has projectId="853"
  -> ProjectPermissionRepository.existsAllowed(user, tenant, projectId)
       returns Mono<Boolean> from R2DBC/reactive store
  -> AuthorizationDecision(allowed)
  -> service/repository still queries with the same tenant/ACL constraint
  -> response only contains permitted records
```

Protect at **two layers** when needed: route policy protects the HTTP boundary, while the service/repository ensures no secondary code path (message consumer, batch job, internal call) accesses data outside permissions.

### 9.2. Asynchronous, Non-Blocking Query Pattern

Example **code snippet inside a custom manager** with a project-defined reactive repository:

```java
return authentication
    .filter(auth -> auth.isAuthenticated()
        && !(auth instanceof AnonymousAuthenticationToken))
    .flatMap(auth ->
        permissionRepository.canRead(
            auth.getName(), tenantId, projectId))
    .map(AuthorizationDecision::new)
    .defaultIfEmpty(new AuthorizationDecision(false));
```

Assumes `permissionRepository.canRead(...)` returns `Mono<Boolean>`, and `tenantId`/`projectId` were extracted and validated per design. This is not a standalone class; test 401/403, nonexistent records, permission store failures, tenant mismatches, and race conditions.

If the permission repository returns `Mono.empty()` for "not found", `defaultIfEmpty(false)` ensures denial. If the backend emits `Mono.error`, the error propagates; never use `onErrorReturn(new AuthorizationDecision(true))`. For sensitive data systems, choose fail-closed and monitor operational errors; never mask 500 as 200.

### 9.3. TOCTOU Risks and Permission Caching

Permissions can change **after HTTP-layer authorization checks** yet before the service reads/writes the resource (time-of-check vs. time-of-use). For sensitive operations, include tenant/owner/ACL conditions inside the data query or appropriate transaction. Caching permission decisions requires explicit TTL/invalidation with cache keys containing identity, tenant, resource, action, and policy version; never cache a boolean `true` solely by URL across all users.

### 9.4. Do Not Confuse Authentication with Authorization

When calling `Authentication.isAuthenticated()`, an anonymous token can return `true` in the framework's internal sense. Use built-in `authenticated()`/`fullyAuthenticated()` managers when policies only need authentication level, or a suitable `AuthenticationTrustResolver`/type check in custom logic. The demo excludes `AnonymousAuthenticationToken` to avoid treating `anonymousUser` as a regular user.

Never construct an `Authentication` from query strings, bodies, or headers without verification and call `withAuthentication` just to make a custom manager return allow. That is **authentication bypass**, not dynamic authorization.

## 10. Rules for Production-Quality ReactiveAuthorizationManager

### 10.1. Fail Closed, Without Turning Every Error into 403

- Missing valid `Authentication` → do not allow.
- Missing path/resource variable, invalid tenant → deny or return 400 per validation layer; never allow.
- User has `Authentication` but lacks permission → deny.
- Permission backend fails → propagate error and handle at the appropriate layer (usually 5xx), ensuring no data is returned. Never turn backend failures into "user allowed".
- If 404 is needed to avoid disclosing resource existence, that is an **application policy** that must be designed consistently, not accidentally masking permission failures as resource not found.
- If a manager intends to return `Mono.empty()` to abstain in a multi-manager composition, there must be an **explicit** fallback policy and tests; do not treat empty as deny or allow by guesswork.

### 10.2. Never Execute Blocking Logic on the Event Loop

Wrong:

```java
return authentication.map(auth -> {
    boolean allowed = jdbcRepository.checkPermission(auth.getName());
    return new AuthorizationDecision(allowed);
});
```

This snippet is **wrong in WebFlux** if `jdbcRepository.checkPermission` is blocking JDBC running on the Netty event loop: requests can stall. Use a reactive repository such as R2DBC when appropriate.

If you must bridge a legacy synchronous service, wrap the blocking part properly:

```java
return authentication.flatMap(auth ->
    Mono.fromCallable(() ->
            legacyService.hasPermission(auth.getName(), resourceId))
        .subscribeOn(Schedulers.boundedElastic())
        .map(AuthorizationDecision::new)
).defaultIfEmpty(new AuthorizationDecision(false));
```

This is a **snippet** requiring imports for `Schedulers`, `Mono`, and project-specific `legacyService` and `resourceId`. `boundedElastic` avoids blocking the event loop but does not make the task non-blocking; cap concurrency/connection pools, timeouts, and capacity appropriately. Never call `block()` inside a manager.

### 10.3. Avoid Unnecessary Network Calls on Every Request

A policy calling a remote authorization service for **every** URL couples availability to that service, increasing latency and load. Use built-in `permitAll`/`authenticated`/`hasAuthority` for simple rules; call remote policies only when needed and cache carefully. Set timeouts, circuit breakers, fail-closed fallbacks, correlation IDs, and p95/p99 metrics; never log tokens/passwords or full security contexts.

### 10.4. Separate Policy from Controllers and Test Independently

A manager should hold **authorization rules**, not response-rendering logic or UI redirects. Resource services can provide reactive ACL queries to managers, but managers must never encode JSON responses or set cookies themselves. Write unit tests for every branch (allow, deny, no auth, missing variable, backend error) and integration tests for the full HTTP chain.

### 10.5. Be Careful with Methods and Paths

- `GET /projects/{owner}` does not automatically protect `POST /projects/{owner}` or other endpoints; write explicit rules per method, with `anyExchange().denyAll()` as the safety net.
- If the same resource has alias endpoints, webhooks, GraphQL resolvers, or message consumers, an HTTP rule on one URL does not protect those other code paths.
- Path matchers normalize URIs per the framework; do not compare `getPath().value().startsWith(...)` manually against uncanonicalized input for sensitive decisions when built-in matchers exist.
- Never let clients specify roles/tenants via query parameters and trust that input while skipping authoritative membership checks.
- Never put `permitAll()` on all of `/projects/**` expecting a subsequent `access(...)` rule to still run. Rules have priority order.

## 11. Common Mistakes Table

| Symptom | Cause | Fix |
|---|---|---|
| `@Override check` fails to compile in Spring Security 7 | Interface switched to `authorize` | Implement `authorize(Mono<Authentication>, T) -> Mono<AuthorizationResult>` |
| 6.5 class implements only `authorize`, compiler still requires `check` | `check` is still abstract in 6.5 | Implement `check` for 6.5 or upgrade versions consistently |
| `getVariables().get("owner")` is `null` | Matcher has no variable or another rule matched first | Check `pathMatchers` and ordering, deny when variable is missing |
| Anonymous accesses endpoint with owner `anonymousUser` | Checked only `isAuthenticated()` | Use trust resolver / built-in policy or exclude anonymous tokens |
| Regular user views another user's data | Trusted client-chosen path/query as ACL proof | Query permissions/ownership from a trusted source, protect service/repo |
| Policy returns `Mono.empty()` when lacking permission | Confused abstain with deny | Return `AuthorizationDecision(false)` and keep a deny fallback |
| Manager calls `subscribe()` itself | Creates detached subscription, loses lifecycle/errors | Compose publishers and return |
| Manager calls `block()` or direct JDBC | Blocks event loop | Use reactive repositories or bounded blocking offload |
| 401 when missing credentials | HTTP Basic entry point requesting authentication | Expected API behavior; do not manually change to 403 |
| 403 when logged in without role | Authorization denied | Inspect actual roles/authorities and policy |
| Redirect to login instead of 401 | Interactive form login / entry point active | Design security chain to match client type |
| `/projects/{owner}` returns 404 despite valid manager | Controller mapping does not match URL | Distinguish security authorization from WebFlux routing |
| Policy backend fails yet app returns 200 | Used `onErrorReturn(true)` / fail-open | Fail closed, monitor errors, and verify results |
| `.authenticated()` placed after `.access(...)` has no effect | First matching rule already applied | Combine conditions in one policy or reorder rules |
| Manager unit tests pass yet HTTP route is open | Manager not wired / chain does not match | Write `WebTestClient` integration tests through the security filter |
| Wrong `AuthorizationContext` class | Used Servlet's `RequestAuthorizationContext` | Use `org.springframework.security.web.server.authorization.AuthorizationContext` |

## 12. Exercises and Answers

**Exercise 1 — What does `AuthorizationDecision(true)` mean?** A manager returns `Mono.just(new AuthorizationDecision(true))`. Has Spring Security already authenticated the user, and does the controller automatically receive `ROLE_ADMIN`?

**Answer:** It is an allow decision for the evaluated policy. It does not authenticate credentials, grant new roles, alter the principal, or protect services outside the HTTP path. Authentication must still come from a trusted mechanism before the manager decides.

**Exercise 2 — How does empty differ from false?** A manager returns `Mono.empty()` when the user does not own the resource. Why should you avoid this?

**Answer:** `Mono.empty()` means no decision (abstain), whereas `AuthorizationDecision(false)` is an explicit denial. Consumers/compositions may treat empty differently from deny; for sensitive resources, return false and configure an explicit deny fallback.

**Exercise 3 — Is the owner in the URL enough?** The client calls `/projects/alice` logged in as Alice. Is all database data returned guaranteed to belong to Alice?

**Answer:** No. The path is client-chosen input and does not guarantee real record ownership/tenant. Permissions must be checked against authoritative data in the repository/service, specifically to prevent BOLA/IDOR.

**Exercise 4 — 401 or 403?** An API enables HTTP Basic. Sending no credentials to `/projects/alice` usually returns what? Logging in as Alice and calling `/projects/bob` usually returns what?

**Answer:** No credentials: 401 from the authentication entry point; authenticated but denied: 403 from access-denied handling. Exact status codes depend on the security entry point and configuration and must never be hardcoded in `AuthorizationDecision`.

**Exercise 5 — Why does the policy method accept `Mono<Authentication>`?** Can you call `authentication.block()` and use it like synchronous Java in WebFlux?

**Answer:** No. Reactor uses lazy publishers and Context to run an asynchronous request pipeline. `block()` can stall the event loop and break the reactive contract. Compose with `map`/`flatMap` and return the publisher.

**Exercise 6 — Is an admin without `ROLE_USER` permitted?** Per the manager in Section 7, user `admin` has `ROLE_ADMIN` but not `ROLE_USER`. Can `admin` access `/projects/bob`?

**Answer:** Yes, because the policy is "real authenticated user AND (`ROLE_ADMIN` OR username equals owner)"; there is no mandatory `ROLE_USER` condition. If the product requires both roles, change the policy and tests.

**Exercise 7 — How do you migrate the manager to Security 7.x?** The 6.5 code currently has `@Override check(Mono<Authentication>, AuthorizationContext) -> Mono<AuthorizationDecision>`.

**Answer:** In 7.x, implement `authorize(Mono<Authentication>, AuthorizationContext) -> Mono<AuthorizationResult>`, which can return `AuthorizationDecision` since it implements `AuthorizationResult`. Update the signature per your dependency version and re-test.

**Exercise 8 — Which test matters most?** Why is a unit test calling `manager.check(Mono.just(alice),context)` insufficient to prove a route is protected?

**Answer:** Unit tests only test the manager's logic. Integration tests through `SecurityWebFilterChain` verify the right matcher, ordering, authentication, entry point, and HTTP response. Both are needed.

**Exercise 9 — What if the permission service returns an error?** If the repository cannot connect, should the manager return `new AuthorizationDecision(true)` for logged-in users to "preserve user experience"?

**Answer:** No. That is fail-open and risks leaking data. Propagate errors / fail closed and return an appropriate operational error without exposing sensitive data.

**Exercise 10 — Why not route every endpoint through one custom manager?**

**Answer:** `permitAll`, `authenticated`, and `hasAuthority` are fast, easy to audit for simple rules, and avoid unnecessary policy backend calls. Use a custom manager only when conditions genuinely require complex data/context; keep `anyExchange().denyAll()`.

## 13. Project Checklist

- [ ] Use `ServerHttpSecurity`/`SecurityWebFilterChain` for WebFlux, without confusing Servlet APIs.
- [ ] Document the Spring Security version; for 6.5 implement `check`, for 7.x implement `authorize`.
- [ ] Attach `ReactiveAuthorizationManager<AuthorizationContext>` to the right `pathMatchers(...).access(...)`.
- [ ] Specific rules before `anyExchange().denyAll()`; verify ordering across multiple chains.
- [ ] In custom policies, never trust `isAuthenticated()` alone for anonymous tokens.
- [ ] Missing principal / path variable / explicit ACL -> explicit deny.
- [ ] Never use `Mono.empty()` in place of deny or discard error signals.
- [ ] Never call `block()`/`subscribe()` inside a manager; use reactive composition.
- [ ] Client-controlled paths/headers/queries never replace verified resource ownership/tenant ACLs.
- [ ] Avoid fail-open backend authorization; manage timeouts and safe fallbacks.
- [ ] Managers do not set HTTP responses directly; let the framework handle 401/403.
- [ ] Test 401 unauthenticated, 403 unauthorized, and 200 authorized using `WebTestClient`.
- [ ] Test data permissions in services/repositories and non-HTTP code paths.
- [ ] Monitor policy latency/denies/errors without excessively logging tokens/passwords/PII.
- [ ] Protect tenant boundaries, resource ownership, and concurrent permission changes.

## 14. Quick Summary

```text
Reactive HTTP request
    |
    v
Verified Authentication
    |
    v
AuthorizationWebFilter
    |
    v
ReactiveAuthorizationManager<AuthorizationContext>
    |-- Mono<Authentication>             : who is calling?
    |-- AuthorizationContext.getExchange : HTTP request/exchange?
    |-- AuthorizationContext.getVariables: path variables?
    |
    +-- AuthorizationDecision(true)  -> pass rule
    +-- AuthorizationDecision(false) -> deny
    +-- Mono.empty()                 -> no decision
    +-- Mono.error(e)                -> pipeline error

Spring Security 6.5: check(...) deprecated, authorize(...) default
Spring Security 7.x: implement authorize(...) -> Mono<AuthorizationResult>

HTTP Basic unauthenticated -> usually 401
Authenticated, insufficient permission -> usually 403
Form login unauthenticated -> may redirect /login
```

Bottom line: **`ReactiveAuthorizationManager` decides access based on trusted identity and request context; `AuthorizationDecision` is the outcome**, not a way to create authentication or write HTTP responses. For real data, always protect permissions at the resource/service/repository layer, not only by URL names.

## 15. Official Documentation

- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security 7.x — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — AuthorizationDecision API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [Spring Security — AuthorizationResult API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Testing WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/test/web/)
- [Spring Security — AuthorityReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorityReactiveAuthorizationManager.html)
- [Spring Security — AuthorizationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationWebFilter.html)
