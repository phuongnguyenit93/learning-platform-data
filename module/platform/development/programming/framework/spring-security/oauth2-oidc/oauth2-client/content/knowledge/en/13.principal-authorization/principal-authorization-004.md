# 13.4. Accessing the Principal in Controllers and Reactive Chains

## Lesson Objectives

Once Spring Security completes **OAuth 2.0 Login / OpenID Connect (OIDC) Login**, the application holds a **principal** object representing the authenticated user. In a controller, we typically want to know who the user is to display their profile or query data they own. In a **Reactive WebFlux** processing chain, that same requirement must be solved using the **Reactor Context** model rather than assuming the principal always lives in a `ThreadLocal`.

This lesson focuses on the two worlds of Spring Security:

- **Servlet / Spring MVC**: accessing the principal with `@AuthenticationPrincipal`, `Authentication` / `Principal` parameters, or `SecurityContextHolder`.
- **Reactive / Spring WebFlux**: using `@AuthenticationPrincipal` in controllers, `ServerWebExchange.getPrincipal()`, and `ReactiveSecurityContextHolder` inside `Mono` / `Flux` pipelines.

After this lesson, you can:

1. Distinguish `Principal`, `Authentication`, `SecurityContext`, `OidcUser`, and `OAuth2User`.
2. Retrieve verified OIDC details in a Spring MVC controller.
3. Build WebFlux endpoints returning `Mono` and retrieve Authentication inside a reactive chain.
4. Understand why `SecurityContextHolder.getContext()` is not a reliable default for accessing the principal across reactive operators.
5. Pass user identity cleanly from controllers to services, avoiding account mix-ups across requests.
6. Enforce authorization via authorities and business data instead of treating email/ID tokens as access permissions.
7. Know how to obtain an issued **access token** to call APIs rather than using the ID token as a bearer token.
8. Handle missing principals, wrong principal types, account switching, or requests running under multiple authentication mechanisms.

## 1. Context: How Does the Principal Appear After OIDC Login?

Suppose we have a **Customer Portal** application built with Spring Boot and Spring Security OAuth 2.0 Client. Users log in via an enterprise OpenID Provider (OP).

Typical flow:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant Portal as Customer Portal
    participant OP as OpenID Provider
    User->>Browser: Visit /me
    Browser->>Portal: HTTP request
    Portal-->>Browser: Redirect OIDC Authorization Request
    Browser->>OP: Login / consent when needed
    OP-->>Browser: Redirect authorization code
    Browser->>Portal: Callback code + state
    Portal->>OP: Exchange code for tokens
    OP-->>Portal: ID token, access token if granted
    Note over Portal: Validate OIDC, create OidcUser and Authentication
    Portal-->>Browser: Session / response per configuration
    Browser->>Portal: Subsequent request to /me
    Note over Portal: Restore Authentication and principal
    Portal-->>Browser: User's information
~~~

After a successful OIDC callback, Spring Security creates an `Authentication` object. This object contains the principal and the authorities/permissions mapped by the application.

For typical Servlet or WebFlux OIDC Login, the principal usually implements the `OidcUser` interface.

**Key point:** the principal is not an authorization code, not a session ID, and not an access token. The principal is the object describing the identity accepted by the framework in the authentication context.

### 1.1. Example of an OIDC Principal

A verified ID token might contain these claims:

~~~json
{
  "iss": "https://id.example.com/realms/customers",
  "sub": "customer-4872",
  "aud": "portal-web",
  "iat": 1800000000,
  "exp": 1800003600,
  "email": "alice@example.com",
  "name": "Alice Nguyen",
  "email_verified": true
}
~~~

This is merely an illustrative payload. A real ID token must be issued by the OP and validated by the RP under OIDC rules, including signature or appropriate protection mechanism, issuer, audience, expiration, and nonce if requested.

Spring Security can represent that result as an `OidcUser`, allowing the application to read the issuer, subject, email, or name if the corresponding claims are supplied.

## 2. Object Model: Principal, Authentication, and SecurityContext

These concepts are often mentioned together, yet they have distinct responsibilities.

| Component | Role | What Can Be Read? |
|---|---|---|
| `Principal` | Abstraction identifying the subject of a request | Usually has `getName()` |
| `Authentication` | Authentication result, containing principal and authorities | `getPrincipal()`, `getAuthorities()`, `isAuthenticated()` |
| `SecurityContext` | Context holding the current Authentication | `getAuthentication()` |
| `OidcUser` | Principal processed via OIDC Login | `getIdToken()`, `getClaims()`, `getSubject()`, `getEmail()` |
| `OAuth2User` | Principal of OAuth2 Login in general | `getAttributes()`, `getAuthorities()` |
| `OAuth2AuthenticationToken` | Common Authentication type after OAuth2/OIDC Login | Principal, authorities, `getAuthorizedClientRegistrationId()` |

A simple model:

~~~text
SecurityContext
└── Authentication
    ├── principal
    │   └── OidcUser
    │       ├── OidcIdToken
    │       ├── OidcUserInfo (if present)
    │       └── claims / attributes
    ├── GrantedAuthorities
    └── authenticated
~~~

The diagram only illustrates conceptual relationships; it does not assert that all objects are always stored inside one specific session structure.

### 2.1. `Principal.getName()` Is Not Necessarily an Email

A common mistake:

~~~java
String username = principal.getName();
// Wrong if assuming username is always an email.
~~~

With OIDC, the principal name may come from `sub` or an attribute configured by the application/provider. Email can change, be missing, or be unverified.

To link an external account to an internal record, a generally safer choice is the pair:

~~~text
issuer  = https://id.example.com/realms/customers
subject = customer-4872

Application-side identity key = issuer + subject
~~~

`sub` is only guaranteed to be a unique identifier within its issuer's scope. Two different providers can assign the same `sub` string to two different people.

### 2.2. `isAuthenticated()` Does Not Mean Having Business Permissions

`Authentication.isAuthenticated()` describes the authentication state of the object. It does not decide whether the user is allowed to view someone else's orders.

For example:

- Alice may log in validly, yet can only view Alice's own orders.
- Bob may have a certain admin authority, yet remains restricted by tenant.
- An account authenticated at the OP is not necessarily activated inside Customer Portal.

Authorization must evaluate **authorities**, ownership, tenant, account status, and business policy.

### 2.3. OIDC Principal Differs from JWT Resource Server Principal

If a request goes through **OIDC Login** in a browser, the principal is typically `OidcUser`.

If the same system has an API accepting bearer JWTs under a **Resource Server** configuration, Authentication is typically `JwtAuthenticationToken` and the principal may be `Jwt`. A controller expecting `@AuthenticationPrincipal OidcUser` will **not automatically match** a request authenticated with a bearer JWT.

Design filter chains, endpoints, and principal types according to the actual authentication mechanism.

## 3. Accessing the Principal in Spring MVC / Servlet

In the Servlet stack, Spring Security normally binds `SecurityContext` to the request-processing thread via `SecurityContextHolder`. The framework can persist and restore context across requests through `SecurityContextRepository`, commonly backed by `HttpSession` for session-based login.

There are three common ways to read the principal.

### 3.1. `@AuthenticationPrincipal`: Injecting `OidcUser` Directly

Controller example:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    UserProfile me(@AuthenticationPrincipal OidcUser user) {
        return new UserProfile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName(),
                user.getEmail());
    }

    record UserProfile(
            String issuer,
            String subject,
            String fullName,
            String email) {}
}
~~~

Explanation:

1. `@AuthenticationPrincipal` retrieves the principal from the current Authentication.
2. `OidcUser` gives access to OIDC claims processed by the framework.
3. `getIdToken().getIssuer()` and `getIdToken().getSubject()` identify the external account.
4. `name` or `email` claims may be absent.

**Example assumption:** `/me` is protected by OIDC Login. If a request is unauthenticated or uses another authentication type, the parameter may not hold an `OidcUser` as expected. A real endpoint must handle that condition instead of dereferencing `null`.

### 3.2. Accepting `Authentication` as a Method Parameter

If both the principal and authorities are needed:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginDetailsController {

    @GetMapping("/login-details")
    LoginDetails details(Authentication authentication) {
        String registrationId = null;

        if (authentication instanceof OAuth2AuthenticationToken oauth) {
            registrationId = oauth.getAuthorizedClientRegistrationId();
        }

        List<String> authorities = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        String subject = authentication.getPrincipal() instanceof OidcUser oidc
                ? oidc.getIdToken().getSubject()
                : null;

        return new LoginDetails(authentication.getName(),
                registrationId, subject, authorities);
    }

    record LoginDetails(
            String principalName,
            String registrationId,
            String subject,
            List<String> authorities) {}
}
~~~

This example accepts the `Authentication` established by Spring Security. It can reveal which registration ID was used when the request came from OAuth2/OIDC Login.

When an application has multiple authentication types, use type checks like `instanceof` or build a unified internal principal abstraction; **do not cast blindly** to `OidcUser`.

### 3.3. Accepting the `Principal` Interface

When only the identifier name is needed:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    String hello(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
~~~

This reduces coupling to Spring Security, but **does not provide issuer, subject, or OIDC claims**. Use `OidcUser` when full OIDC identity is needed.

Do not treat `getName()` as proof of email or access rights.

### 3.4. `SecurityContextHolder` in a Servlet Service

A service running on the same request thread can access:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentAuthenticationLookup {

    public Authentication current() {
        return SecurityContextHolder.getContext().getAuthentication();
    }
}
~~~

This is useful in layers that do not receive the principal as a method parameter, though it introduces coupling to active security state.

In testable business code, it is often better for the controller to pass **issuer + subject** or a verified user identity object into the service. That way, the service does not need to care whether the request came from Servlet or Reactive.

### 3.5. Never Store the Current Principal in a Static Variable

Incorrect example:

~~~java
public final class BadCurrentUser {
    static OidcUser lastLoggedInUser;
}
~~~

`static` fields are shared across requests and users. Updating this field in a login handler can cause another user's request to read a stale identity.

Similarly, never cache `Authentication` under a shared key untied to principal/session or store user objects directly on singleton services as mutable state.

## 4. How Do Reactive Chains Differ from Servlet?

With **Spring WebFlux**, requests are processed through a **reactive pipeline** composed of publishers such as `Mono` and `Flux`. Execution can switch threads depending on schedulers and operators; there is no guarantee that the entire execution stays on one Servlet thread tied to a fixed `ThreadLocal`.

In Spring Security Reactive, the `SecurityContext` is stored in the **Reactor Context** and can be accessed via:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

This is the central difference.

| Criterion | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Processing model | Request typically handled on a Servlet thread | Publisher subscribed and executed via reactive pipeline |
| Accessing context in service | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Context API return type | `SecurityContext` | `Mono<SecurityContext>` |
| Context attachment | Typically ThreadLocal per request | Reactor subscriber context |
| Default session for web login | `HttpSession` | `WebSession` / appropriate `ServerSecurityContextRepository` |
| Security filter | `SecurityFilterChain` and Servlet filters | `SecurityWebFilterChain` and WebFilters |
| Non-blocking HTTP client | Can use `RestClient` or `WebClient` as needed | Typically `WebClient` |
| Note on thread switching | ThreadLocal does not follow custom threads automatically | Reactor Context propagates along reactive chains, not arbitrary manual subscribes |

**Do not mix the two context access models mechanically.** Calling `SecurityContextHolder.getContext()` inside a WebFlux `flatMap` may yield empty or incorrect context depending on execution.

## 5. Configuring OIDC Login for Spring WebFlux

### 5.1. Dependencies

For a Spring Boot project using WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

The example uses the **Reactive stack**. In a project containing both Spring MVC and WebFlux starters, Spring Boot has rules for choosing the web application type; do not assume merely adding `webflux` makes all controllers run on WebFlux.

### 5.2. Configuring the OIDC Registration

Client properties mirror Servlet configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/customers
~~~

Meaning:

- `corporate` is the internal `registrationId`.
- `client-id` is the application identifier registered at the OP.
- `client-secret` on the backend must be managed as a secret.
- `scope=openid` requests OpenID Connect.
- `issuer-uri` identifies the trusted OP.
- The callback must be allowed by the OP and match the actual public URL.

### 5.3. Configuring `SecurityWebFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/error", "/assets/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

In WebFlux, the chain is `SecurityWebFilterChain` instead of Servlet's `SecurityFilterChain`.

Spring Security Reactive uses WebFilters and corresponding reactive repositories to handle login, Authentication, and security context. Never write a Servlet filter to protect requests running entirely inside the WebFlux stack.

## 6. Accessing the Principal in WebFlux Controllers

### 6.1. `@AuthenticationPrincipal OidcUser`

Spring Security supports injecting the authenticated principal via annotation in WebFlux handlers/controllers. Example:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveProfileController {

    @GetMapping("/api/me")
    Mono<Profile> me(@AuthenticationPrincipal OidcUser user) {
        Profile response = new Profile(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getFullName());

        return Mono.just(response);
    }

    record Profile(String issuer, String subject, String name) {}
}
~~~

**Note:** Although the handler returns `Mono`, `OidcUser` is resolved by Spring Security at controller entry from the current Authentication. This works well when the principal is already authenticated and the endpoint requires OIDC Login.

If all logic must happen inside a Reactive chain or downstream services need Authentication, access the context via Reactor as shown next.

### 6.2. Using `ServerWebExchange.getPrincipal()`

WebFlux offers another way to obtain the principal from the exchange:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ExchangePrincipalController {

    @GetMapping("/api/principal-name")
    Mono<String> principalName(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous");
    }
}
~~~

`ServerWebExchange.getPrincipal()` returns `Mono<Principal>`. `getName()` is only a name per the `Authentication` implementation; do not assume it is an email.

The illustrative endpoint returns `anonymous` when no principal is present. For APIs requiring authentication, require it in `SecurityWebFilterChain` instead of treating the string `anonymous` as a business identifier.

### 6.3. Reactive Controller Returning Detailed Authentication

If you want to retrieve issuer, subject, and authorities explicitly inside the pipeline:

~~~java
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveIdentityController {

    @GetMapping("/api/identity")
    Mono<IdentityResponse> identity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.UNAUTHORIZED)))
                .flatMap(authentication -> {
                    if (!(authentication.getPrincipal() instanceof OidcUser user)) {
                        return Mono.error(
                                new ResponseStatusException(
                                        HttpStatus.FORBIDDEN,
                                        "OIDC login is required"));
                    }

                    List<String> authorities =
                            authentication.getAuthorities().stream()
                                    .map(GrantedAuthority::getAuthority)
                                    .toList();

                    return Mono.just(new IdentityResponse(
                            user.getIdToken().getIssuer().toString(),
                            user.getIdToken().getSubject(),
                            user.getEmail(),
                            authorities));
                });
    }

    record IdentityResponse(
            String issuer,
            String subject,
            String email,
            List<String> authorities) {}
}
~~~

Here, `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`. All logic extracting Authentication and inspecting the principal executes inside the reactive chain.

The error branches prevent `NullPointerException` when the principal is absent or of the wrong type. In real systems, access policies can live in the filter chain and method security so you do not repeat these checks in every controller.

## 7. How Does `ReactiveSecurityContextHolder` Work?

### 7.1. Reactor Context, Not a Global Variable

Reactor Context is a data structure attached to the **subscriber and reactive execution chain**, not a global map shared across all users.

Spring Security populates a `Mono<SecurityContext>` into the Reactor Context for an authenticated request. In service code:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication);
}
~~~

When this publisher is subscribed **within a request chain carrying a security context**, it reads the matching Authentication.

Do not think of `getContext()` as a synchronous read at object-creation time. Reactive pipelines are lazy: operators run on subscription, so **the context at subscription time** is what matters.

### 7.2. Why Isn't `SecurityContextHolder` the Primary Choice in WebFlux?

An anti-pattern in the Reactive model:

~~~java
return Mono.fromCallable(() ->
        SecurityContextHolder.getContext().getAuthentication()
).map(authentication -> authentication.getName());
~~~

`SecurityContextHolder` typically relies on Servlet `ThreadLocal`. In WebFlux, pipelines can switch schedulers/threads and are not guaranteed to preserve the request's ThreadLocal Authentication.

Testing locally might occasionally appear to work, but never rely on that as a security contract. **Use `ReactiveSecurityContextHolder` or obtain the principal via WebFlux request abstractions.**

### 7.3. `map` and `flatMap` in Principal Chains

When transforming Authentication synchronously:

~~~java
Mono<String> name =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

When calling a reactive repository or service:

~~~java
Mono<CustomerProfile> profile =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(authentication ->
                        customerProfiles.findByExternalName(
                                authentication.getName()));
~~~

In the second snippet, `customerProfiles.findByExternalName(...)` is an illustrative repository API returning `Mono<CustomerProfile>`.

**Note:** beyond illustrating `flatMap`, in real systems you should not use `getName()` as the OIDC identity link key without defining its semantics. A better design extracts `iss` + `sub` and queries the repository by that pair.

### 7.4. Per-Subscriber Context and Scheduler Switches

A Reactor pipeline may include:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.boundedElastic())
        .map(name -> "Hello, " + name);
~~~

Import `reactor.core.scheduler.Schedulers` when using the example above.

In a properly constructed Reactor chain, Reactor Context propagates according to publisher/subscriber rules; switching schedulers with `publishOn` does not mean moving the principal into a static map.

However, if you create a detached subscription outside the request flow, jump into a third-party callback outside Reactor pipelines, or break the chain with non-Reactor APIs, **do not assume the context still exists**.

### 7.5. Why Avoid Calling `subscribe()` Manually in Services?

An error-prone pattern:

~~~java
public void updateSomething() {
    ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .subscribe(auth -> updateDatabase(auth.getName()));
}
~~~

Problems:

- Creates a separate subscription, losing coordination with the original request result.
- Exceptions may not be handled in the same flow.
- Context may not propagate as expected if the subscription lies outside the chain managed by Spring Security.
- Side effects run asynchronously, making transactional boundaries and authorization hard to track.

Always **return `Mono` or `Flux`** so the framework subscribes at the proper boundary.

Better design example:

~~~java
public Mono<Void> updateSomething() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> updateDatabaseReactive(auth.getName()));
}
~~~

Here `updateDatabaseReactive(...)` is an illustrative method returning `Mono<Void>`. Business logic must still rely on trusted identifiers and enforce proper authorization.

### 7.6. Never Call `block()` on the WebFlux Request Path

Pattern to avoid:

~~~java
Authentication auth =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .block();
~~~

`block()` waits synchronously for the result, risking event-loop starvation and missing subscription context. Inside a non-blocking WebFlux request, **compose the pipeline** with `map` / `flatMap` / `switchIfEmpty` instead of forcing a synchronous result.

If you genuinely must invoke a blocking library, isolate it on an appropriate scheduler and evaluate the impact, but **never turn reading the principal into a blocking call**.

## 8. Using the Principal in a Reactive Service to Enforce Ownership

### 8.1. Problem: Viewing Only the User's Own Orders

Suppose Customer Portal has an endpoint:

~~~text
GET /api/orders/{orderId}
~~~

An authenticated user must still not be able to view someone else's order simply by changing `orderId`.

The service layer needs to know:

- The user's issuer.
- The user's subject.
- Whether the order belongs to that subject.
- Whether the user has the required authority/business context.

### 8.2. Designing the Service Around Issuer and Subject

Illustrative abstractions:

~~~java
public record ExternalIdentity(String issuer, String subject) {}

public record OrderView(String id, String description) {}

public interface OrderLookup {
    Mono<OrderView> findOwnedOrder(
            String orderId, String issuer, String subject);
}
~~~

Here `OrderLookup` is an assumed application interface whose implementation must verify ownership in the database or an authoritative service.

Service using `ReactiveSecurityContextHolder`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final OrderLookup orders;

    public OrderService(OrderLookup orders) {
        this.orders = orders;
    }

    public Mono<OrderView> getOwnedOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.UNAUTHORIZED)))
                .flatMap(authentication -> {
                    if (!(authentication.getPrincipal() instanceof OidcUser user)) {
                        return Mono.error(
                                new ResponseStatusException(HttpStatus.FORBIDDEN));
                    }

                    String issuer = user.getIdToken()
                            .getIssuer().toString();
                    String subject = user.getIdToken().getSubject();

                    return orders.findOwnedOrder(orderId, issuer, subject)
                            .switchIfEmpty(Mono.error(
                                    new ResponseStatusException(
                                            HttpStatus.NOT_FOUND)));
                });
    }
}
~~~

Significance:

1. Identity is read from the Reactive SecurityContext.
2. The service does not trust a browser-sent user ID as proof of identity.
3. Ownership queries rely on trusted issuer and subject.
4. If no order belongs to the current subject, the service returns no data.
5. This logic stays inside the `Mono` chain without calling `block()` or creating a separate `subscribe()`.

In real projects, mapping `iss` + `sub` to an internal account may live in a dedicated identity service layer. Account for tenants and delegation rights if the product supports acting on behalf of others.

### 8.3. Controller Returning the Service's Publisher

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/api/orders/{orderId}")
    Mono<OrderView> order(@PathVariable String orderId) {
        return service.getOwnedOrder(orderId);
    }
}
~~~

The controller **does not take `userId` from a query parameter** to substitute for the principal. It returns the service's pipeline for WebFlux to execute.

### 8.4. Alternative: Passing Identity Explicitly

Not every service needs to depend on `ReactiveSecurityContextHolder`. Another option is for the controller to receive `OidcUser` and pass an immutable DTO:

~~~java
public record ExternalIdentity(String issuer, String subject) {
    public static ExternalIdentity from(OidcUser user) {
        return new ExternalIdentity(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/orders/{orderId}")
Mono<OrderView> order(
        @PathVariable String orderId,
        @AuthenticationPrincipal OidcUser user) {

    ExternalIdentity identity = ExternalIdentity.from(user);
    return orderService.getOwnedOrder(orderId, identity);
}
~~~

In this example, `getOwnedOrder(String, ExternalIdentity)` is an overload or separate service API by design. The benefit is that identity is passed explicitly, making the domain service easy to test without reading the Reactive SecurityContext directly.

However, callers must be trusted components; sensitive services must never accept an arbitrary `ExternalIdentity` from a user-supplied request body.

## 9. Differences Between Reading Claims and Authorization

### 9.1. Profile Claims Are Not Authorities

An OIDC ID token may contain:

~~~json
{
  "sub": "customer-4872",
  "email": "alice@example.com",
  "name": "Alice Nguyen",
  "email_verified": true
}
~~~

These claims primarily serve identification and profile display. They do not imply Alice holds `ROLE_ADMIN` or `orders.write`.

Spring Security uses `GrantedAuthority` to represent authorities, and mapping claims from an OP to authorities must be carefully designed.

### 9.2. Inspecting Authorities in a Controller

Example in a reactive pipeline:

~~~java
Mono<List<String>> authorities() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> authentication.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .toList());
}
~~~

In Spring Security, names like `SCOPE_orders.read` or `ROLE_ADMIN` only carry meaning when an explicit mapping mechanism and policy are defined.

OIDC Login does not automatically guarantee every role placed by a provider into a custom claim becomes an application `ROLE_*`. An appropriate authorities mapper or custom OIDC user service is often required.

### 9.3. Reactive Method Security

Spring Security Reactive supports protecting methods via annotations when enabled.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Example reactive service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class ReportsService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> report() {
        return Mono.just("Report content");
    }
}
~~~

This illustrates the syntax; to work in practice, the service must be a Spring-managed bean and the authority must be granted/mapped appropriately onto the request's Authentication.

With OIDC Login, verify how the provider and Spring Security generate authorities. Do not assume that requesting scope `reports.read` in the OAuth client automatically puts `SCOPE_reports.read` on the principal in every configuration.

**Ownership checks are still required**, even when the user has general permission to call an endpoint.

### 9.4. When Multiple Issuers or Multiple Tenants Exist

Suppose two OPs exist:

~~~text
https://id.example.com/realms/customer
https://id.example.com/realms/partner
~~~

Both can issue `sub=12345` for two different subjects. If a service queries records solely by `sub`, there is a risk of cross-tenant access.

Business identity keys must bind issuer/tenant properly. Never treat email, display name, or `getName()` as globally unique unless the identity model guarantees it.

## 10. Accessing an Access Token to Call APIs Is Not Accessing the Principal

After OIDC Login, the client may be issued an access token to call a Resource Server. That token does not live on `OidcUser` in the sense of "calling `getIdToken()` to get an API token".

Distinction:

| Object | Purpose |
|---|---|
| `OidcUser` | Subject authenticated via OIDC |
| `OidcIdToken` | Authentication result consumed by the RP |
| `OAuth2AuthorizedClient` | Authorized client state holding an access token and optionally a refresh token |
| `ReactiveOAuth2AuthorizedClientManager` | Manages obtaining/refreshing tokens reactively |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Integrates OAuth2 access tokens into `WebClient` based on context |

**An ID token is not an access token.** Never routinely send `OidcUser.getIdToken().getTokenValue()` in the Bearer header to a business API.

### 10.1. `WebClient` Supports OAuth2 Client

Example configuring Reactive `WebClient` with beans provided by Spring Boot / Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        registrations, authorizedClients);

        return WebClient.builder()
                .baseUrl("https://orders-api.example.com")
                .apply(oauth.oauth2Configuration())
                .build();
    }
}
~~~

Calling the API within an authenticated request context:

~~~java
import static org.springframework.security.oauth2.client.web
        .reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
        .clientRegistrationId;

public Mono<String> fetchOrders() {
    return ordersWebClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("corporate"))
            .retrieve()
            .bodyToMono(String.class);
}
~~~

`ordersWebClient` is the `WebClient` instance injected into the service. `clientRegistrationId("corporate")` specifies which OAuth client configuration to use, and the filter resolves the authorized client and token according to configuration.

These snippets use Spring Security Reactive APIs only to illustrate the integration pattern. For production use, verify access token scopes/audience, manage refresh/reauthorization, handle missing authorized clients, and enforce rules for using the logged-in user's token.

Never enable attaching tokens by default to **every request** to arbitrary domains unless truly needed. Sending an access token to an untrusted server can leak credentials.

### 10.2. Principal and Authorized Client Have Different Lifecycles

A user may:

- Still have `Authentication` in `WebSession`.
- Have an ID token from the earlier OIDC Login.
- Have an expired access token.
- Have a refresh token permitted to obtain a new access token.
- Have had their API permissions modified recently.

Therefore, **having a principal present does not guarantee a valid access token for every API**. Token management and API authorization are separate responsibilities.

## 11. Reactive Context with `flatMap`, `publishOn`, and External Libraries

### 11.1. Context Propagates Along the Reactor Chain

A typical pipeline:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
                orderService.loadFor(authentication.getName()))
        .map(this::toResponse);
~~~

In this chain, security data comes from the subscriber's Reactor Context. If services return publishers properly, the request pipeline preserves context across composed operators.

### 11.2. Switching Schedulers Does Not Create a New Principal

Example:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.boundedElastic())
        .map(name -> "Current user: " + name);
~~~

Using `publishOn` here is purely illustrative. You do not need to move an entire WebFlux application onto `boundedElastic` just to read the principal; reading context is non-blocking.

Reactor Context propagates per subscriber rather than requiring all operators to execute on the same Java thread.

### 11.3. Tasks Detached from the Request Can Lose Context

A common source of confusion:

~~~text
Authenticated HTTP request
  -> Controller creates Mono
  -> Service calls subscribe() internally
  -> Task moves to a separate scheduler
  -> Reading principal fails as expected context is missing
~~~

The reason is often that the new subscription is detached from the original request's subscriber/context.

Proper design:

- **Return the publisher** for upstream subscription/composition.
- If spawning a background job, pass a verified identity DTO along with needed business data over a trusted channel.
- For standalone tasks with no active user request, use a service identity or appropriate delegation mechanism.
- Never hold `OidcUser` or `Authentication` in a static variable to "carry context".

### 11.4. Using CompletableFuture or Non-Reactor Callback Libraries

Do not assume Reactor Context automatically propagates across every `CompletableFuture`, manually spawned thread, or callback lacking a Reactor bridge.

When integrating them, explicitly define what data crosses the boundary and use supported context-propagation mechanisms or pass an **immutable identity** via trusted parameters.

A controllable business-layer pattern is extracting `ExternalIdentity(issuer, subject)` at the request boundary and passing that value to downstream layers.

## 12. WebSession Is Not HttpSession

In Spring MVC Servlet OIDC Login, the common session is `HttpSession` and `SecurityContextHolder` is typically ThreadLocal-based.

In WebFlux, requests do not use the Servlet API as their primary abstraction. Instead, the system has:

- `WebSession` for WebFlux session data when used.
- `ServerSecurityContextRepository` to save/restore `SecurityContext` reactively.
- `ReactiveSecurityContextHolder` to access context via Reactor.
- `SecurityWebFilterChain` as the request protection chain.

A session-based Reactive Login configuration can store login state in `WebSession`, but **you should never call `HttpServletRequest.getSession()` in a WebFlux handler**.

Additionally, the application's session is **distinct** from the SSO session at the OP. A user may lose their Portal `WebSession` yet still be silently authenticated by the OP upon starting a new OIDC Login if the browser still holds an SSO session.

## 13. Different Principal Types in Mixed Applications

A system might support:

1. **WebFlux UI/OIDC Login**: principal is usually `OidcUser`.
2. **Reactive Resource Server with bearer JWT**: Authentication is usually `JwtAuthenticationToken`, principal may be `Jwt`.
3. **HTTP Basic or custom authentication**: principal has another type.
4. **Anonymous requests**: no authenticated principal or anonymous authentication per configuration.

Therefore, do not put a controller requiring `OidcUser` on an endpoint reachable by multiple login types without defining how to handle them.

### 13.1. Reading Subject Based on the Actual Authentication Mechanism

Illustrative branching example:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

String subject(Authentication authentication) {
    Object principal = authentication.getPrincipal();

    if (principal instanceof OidcUser oidc) {
        return oidc.getIdToken().getSubject();
    }
    if (authentication instanceof JwtAuthenticationToken jwt) {
        return jwt.getToken().getSubject();
    }
    throw new IllegalArgumentException("Unsupported authentication type");
}
~~~

This snippet illustrates type differentiation, **not a complete trust policy**. For a JWT Resource Server, `sub` must be evaluated alongside issuer/audience, token type, and tenant per configured token validation.

If the application accepts multiple authentication sources, design an internal `CurrentIdentity` holding issuer, subject, tenant, and authentication source. Converting from `Authentication` to identity should live in a single centrally controlled component.

### 13.2. OIDC Login and Stateless API Calls

A WebFlux application can host both a session-based login UI and a bearer-token API. With properly separated chains:

- The UI OIDC Login chain handles redirects, `WebSession`, and `OidcUser` principals.
- The API Resource Server chain validates JWT/access tokens without needing `WebSession`.
- Controllers sit behind the chain matching their expected authentication mechanism.

Never reuse the UI's `OidcUser` logic to accept an RP's ID token as an API bearer token.

## 14. Common Errors When Accessing the Principal

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `@AuthenticationPrincipal OidcUser` returns `null` | Unauthenticated request or different principal type | Check filter chain, actual authentication, and matchers |
| `getName()` is not an email | Principal name attribute differs from email | Use issuer + subject when linking users |
| WebFlux service reads empty `SecurityContextHolder` | Context lives in Reactor, not current ThreadLocal | Use `ReactiveSecurityContextHolder` |
| Separate `subscribe()` callback lacks context | Detached subscription from request | Compose and return publishers instead of manual `subscribe()` |
| `block()` fails or degrades performance | Blocking inside WebFlux event loop | Use `map`/`flatMap` |
| Logged in via OIDC, yet API returns 401 | API expects an access token with proper audience, not just a principal | Check authorized client and Resource Server |
| Email claim is missing | Scope/OP did not return email | Handle optional claims; never treat missing email as missing subject |
| Role in ID token does not become `ROLE_ADMIN` | Missing authority mapping | Design mapper and policy per provider |
| Two providers share the same `sub`, mixing up users | Stored subject without issuer | Use issuer + subject and tenant binding |
| After logout, principal still appears in another tab | App session/SSO lifecycles differ, or browser holds stale request | Review logout, session, and re-authentication rules |
| Singleton service holds previous request's user | Stored Authentication in shared field | Never keep mutable principal state across requests |
| Background job loses principal on start | Reactor Context does not follow independent jobs | Pass trusted identity or use a service identity |

Each of these cases must be diagnosed by request, chain, Authentication source, and session management; never "fix" them by assigning a default principal to every request.

## 15. Security and Privacy When Using Principals

### 15.1. Return Minimal DTOs; Do Not Serialize Raw `OidcUser`

An OIDC principal may hold the ID token, UserInfo, claims, and authorities. Never return this raw object over HTTP:

~~~java
// Avoid returning the raw principal from an API:
@GetMapping("/unsafe-me")
OidcUser unsafeMe(@AuthenticationPrincipal OidcUser user) {
    return user;
}
~~~

Doing so can expose profile data or unnecessary tokens/metadata.

Prefer returning a DTO containing only fields the screen truly needs, such as display name, permitted email, or a non-sensitive internal ID.

### 15.2. Never Log ID Tokens or Access Tokens

`OidcUser.getIdToken().getTokenValue()` holds the raw ID token. `OAuth2AuthorizedClient.getAccessToken().getTokenValue()` holds the access token.

Never write these tokens to logs, exception messages, traces, or responses. For troubleshooting, log the registration ID, Authentication type, validation outcome, and a non-credential correlation ID.

### 15.3. Never Let the Frontend Self-Declare the Principal

Example request:

~~~http
GET /api/orders
X-User-Id: customer-4872
~~~

Never treat a browser-sent `X-User-Id` as proof of authentication or ownership. If a trusted gateway forwards identity via headers, that is a specialized authentication architecture requiring network isolation, caller verification, signatures, or strict validation—not Spring Security's default behavior.

In standard OAuth/OIDC systems, identity comes from the `Authentication` established by the framework, not from client-supplied query parameters or headers.

### 15.4. Never Elevate Authorities from Undefined Claims

An ID token may list groups or roles using the OP's custom schema. Only use such claims when:

- The OP/issuer is trusted.
- The token has been validated for the intended purpose.
- A well-defined mapping to application permissions exists.
- Permissions are scoped by tenant/resource and dedicated policies.
- Users cannot alter claims to escalate privileges.

Authentication and authorization are always two separate decisions.

### 15.5. Context Propagation Is Also User Isolation

If a background task or static variable accidentally reuses the previous request's principal, another user's data can be read or modified.

Therefore, when propagating identity through reactive chains:

- Keep context scoped to the proper subscription.
- Never store context globally.
- Never attach an unrelated context across multiple users.
- Never use `contextWrite` to inject an arbitrary `Authentication` without a trusted source.
- When checking ownership, combine issuer/subject with business permissions.

## 16. Practice Scenarios

### Scenario A: MVC Profile Page

**Requirement:** after OIDC Login, a Servlet controller displays the user's name and subject.

**Approach:** use `@AuthenticationPrincipal OidcUser`, read `getFullName()` and `getIdToken().getSubject()`, and handle missing name cases.

**Avoid:** relying on `principal.getName()` and assuming it is an email.

### Scenario B: WebFlux Fetching User-Owned Orders

**Requirement:** a Reactive service returns an order by ID only if the caller owns it.

**Approach:** use `ReactiveSecurityContextHolder.getContext()` inside `Mono`, extract issuer/subject from `OidcUser`, query the repository with ownership filtering, and return `Mono<OrderView>`.

**Avoid:** calling `block()` or trusting `userId` from a query parameter.

### Scenario C: Switching Threads While Running Reactor

**Requirement:** a flow uses `publishOn` to switch schedulers and still needs the principal.

**Approach:** use Reactor Context along the pipeline rather than relying on Servlet `ThreadLocal`.

**Avoid:** storing `Authentication` in a static field to "preserve" the principal.

### Scenario D: Service Calling an External API

**Requirement:** Portal calls Orders API on behalf of the user.

**Approach:** use `OAuth2AuthorizedClient` / reactive client manager and an OAuth2-configured `WebClient` to send an **access token** with the proper audience and scopes.

**Avoid:** sending the ID token in `Authorization: Bearer` to the API.

### Scenario E: Same URL Supporting OIDC Login and Bearer JWT

**Requirement:** an endpoint may be accessed from a logged-in browser or a service sending a bearer token.

**Approach:** clearly design filter chains, principal conversion, and policies. If unifying identity, construct an internal abstraction only after verifying issuer/audience and Authentication type.

**Avoid:** casting every principal to `OidcUser` or accepting an RP's ID token as an API bearer access token.

### Scenario F: Background Job Running After the Request

**Requirement:** the user clicks a button requesting a background report generation.

**Approach:** authenticate/authorize when receiving the request, record the job with verified issuer/subject or internal user ID, and execute the job with an appropriate authorization mechanism.

**Avoid:** expecting `ReactiveSecurityContextHolder` or `Authentication` to remain in a job running after the request finishes without an explicit security context.

## 17. Self-Check Questions

**Question 1.** In Spring MVC, what is the simplest way to obtain the OIDC user in a controller?

**Answer:** Use `@AuthenticationPrincipal OidcUser` if the endpoint is exclusively for OIDC Login, or accept `Authentication` and check the principal type.

**Question 2.** In WebFlux, why shouldn't you rely on `SecurityContextHolder.getContext()` inside every `flatMap`?

**Answer:** Reactive pipelines do not guarantee the same `ThreadLocal` across their lifecycle. Spring Security Reactive propagates context via Reactor subscriber context; use `ReactiveSecurityContextHolder`.

**Question 3.** What type does `ReactiveSecurityContextHolder.getContext()` return?

**Answer:** `Mono<SecurityContext>`. Compose it with reactive operators rather than calling `block()` on the request path.

**Question 4.** If `OidcUser.getEmail()` returns null, does that mean the user is not logged in?

**Answer:** No. The email claim might not be issued by the OP. OIDC identity should rely on issuer/subject from a verified token.

**Question 5.** Is `Authentication.isAuthenticated()` enough to allow viewing any order?

**Answer:** No. Ownership, tenant, and business permissions must be checked.

**Question 6.** In a reactive service, why is calling `subscribe()` manually error-prone?

**Answer:** It detaches the subscription from the request flow, breaking context propagation, exception handling, and result coordination. Return `Mono`/`Flux` so upstream can compose it.

**Question 7.** After OIDC Login, which token is used to call a business API?

**Answer:** An access token targeted at the Resource Server, usually managed via `OAuth2AuthorizedClient`—not the ID token.

**Question 8.** Can you retrieve the principal from `ServerWebExchange`?

**Answer:** Yes. `exchange.getPrincipal()` returns `Mono<Principal>`, suitable for WebFlux handlers.

**Question 9.** Two OPs issue the same `sub`. Can they be treated as the same account?

**Answer:** No. Account for the issuer and account-linking policy; typically use `iss` + `sub`.

**Question 10.** If a background job has no active HTTP request, can you assume the user's Reactor SecurityContext is still available?

**Answer:** No. The job must receive a verified identity/delegation explicitly or run under an appropriate service identity.

## Key Takeaways

- **Principal** describes the authenticated subject; `Authentication` holds the principal and authorities; `SecurityContext` holds the Authentication for the current context.
- In **Spring MVC Servlet**, use `@AuthenticationPrincipal`, `Authentication`, or `SecurityContextHolder` where appropriate.
- In **Spring WebFlux**, use `@AuthenticationPrincipal` in controllers, `ServerWebExchange.getPrincipal()`, or **`ReactiveSecurityContextHolder`** inside `Mono`/`Flux`. `SecurityContext` belongs to **Reactor Context**, not a global or thread-local variable guaranteed to follow every operator.
- When identifying OIDC users, prefer **`iss` + `sub`**; never assume name/email is a durable key or a source of permissions.
- **Do not use ID tokens as access tokens** when calling APIs. Use authorized clients and an OAuth2-aware `WebClient` with matching scopes/audience.
- **Do not manually subscribe or block in reactive requests**, never share principals via singletons/statics, and never skip ownership/authority checks simply because the user is authenticated.
