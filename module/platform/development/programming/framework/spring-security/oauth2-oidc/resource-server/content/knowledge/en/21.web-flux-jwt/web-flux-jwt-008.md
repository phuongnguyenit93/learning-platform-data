# Principal Mapping with Reactive Lookups When Business Logic Requires It

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server using WebFlux**, after a Bearer JWT access token is verified, Spring Security must construct an **`Authentication`** object so the application knows which subject sent the request and what authorities they hold. By default, the principal is typically based on the verified **`Jwt`**, and `Authentication.getName()` is normally derived from the `sub` claim. For many applications, that information is sufficient: the API checks scope, issuer, and audience and makes its decision.

However, real business requirements may demand more: which internal account corresponds to `(iss, sub)`? Is that account enabled? Which customer or employee record in the database is this person linked to? What permissions do they currently hold in the active organization/tenant? Such data is often **not inside the JWT**, or it can change after the JWT was issued.

In WebFlux, you cannot solve this by calling a synchronous repository and invoking `.block()` inside the JWT converter. Instead, **the lookup must live inside a reactive `Mono`/`Flux` chain**, or be deferred to the service/authorization layer when only certain business operations need it. This lesson clarifies both options, how to map principals in the right place, and the security boundaries to uphold.

> **Core principle:** A verified JWT is the source of truth for **external identity and signed claims**, whereas the internal system is the source of truth for **account linking, status, and dynamic business permissions**. When a lookup is needed, follow a **non-blocking** and **fail-closed** model. Not every request needs a database lookup; place a lookup in authentication only when it is a mandatory shared requirement across all protected requests.

## 1. Context: From JWT to Principal in WebFlux

Suppose a retail system consists of:

- **Identity Server**: Authorization Server issuing JWT access tokens.
- **Shop Web**: OAuth2/OIDC Client requesting tokens and calling the API.
- **Orders API**: WebFlux Resource Server verifying JWTs and enforcing authorization.
- **Identity Link Database**: maps external users to internal user IDs.
- **Order Database**: stores orders by owner, tenant, and status.

A request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <signed-jwt-access-token>
~~~

The verified JWT carries illustrative claims:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "external-user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

In the business system, this person may be stored under ID **`user-0042`**, not `external-user-842`. Link table:

| Issuer | External subject | Internal user ID | Status |
| --- | --- | --- | --- |
| `https://identity.example.test/realms/shop` | `external-user-842` | `user-0042` | Enabled |
| `https://identity.partner.example.test` | `external-user-842` | `user-1290` | Enabled |

Two rows with the same `sub` string yet **different issuers** can represent **two completely different accounts**. Therefore, never treat `sub` as a global key if the API can trust multiple issuers, and never assume email/username is a stable identifier.

A processing flow:

~~~mermaid
flowchart TD
    A["HTTP Bearer JWT"]
    B["Spring Security WebFlux SecurityWebFilterChain"]
    C["ReactiveJwtDecoder: signature, issuer, audience, time"]
    D{"Valid JWT?"}
    E["Authentication failure, no principal created"]
    F["Reactive JWT authentication converter"]
    G{"Does business require local account linking for every request?"}
    H["Reactive repository / client: find (iss, sub)"]
    I["Create JwtAuthenticationToken with internal user ID"]
    J["Use default JWT principal"]
    K["Reactive authorization and business policy"]
    L["Look up resource/owner/tenant if endpoint needs it"]
    M["Authorized result"]

    A --> B --> C --> D
    D -->|No| E
    D -->|Yes| F --> G
    G -->|Yes| H --> I --> K
    G -->|No| J --> K
    K --> L --> M
~~~

**Ordering is critically important:** the JWT must be verified **before** the API uses `iss`/`sub` to look up a trusted account. Never read a payload from a JWT whose signature has not been verified and query accounts or grant authorities from that data.

## 2. How Do `Jwt`, Principal, Name, and Authorities Differ?

Spring Security uses `Authentication` to represent the authenticated subject together with permissions.

| Concept | Function | Example |
| --- | --- | --- |
| **`Jwt`** | Access token verified by `ReactiveJwtDecoder` and represented as claims | `iss`, `sub`, `aud`, `scope` |
| **`Authentication`** | Request authentication context | `JwtAuthenticationToken` |
| **`Authentication.getPrincipal()`** | Object representing the principal, usually the `Jwt` itself | A verified `Jwt` |
| **`Authentication.getName()`** | Principal name string for audit/application use | Defaults to `sub`; can map to internal ID |
| **`Authentication.getAuthorities()`** | Set of `GrantedAuthority` used for authorization | `SCOPE_orders.read`, `ROLE_MEMBER` |
| **Local account/profile** | Data owned by the Orders API or enterprise | `internalUserId=user-0042`, `enabled=true` |
| **Resource-level permission** | Permission on order 42, tenant A, assignment, etc. | Is the caller allowed to read **this order**? |

**Do not conflate `Authentication.getPrincipal()` with `Authentication.getName()`.** If you construct `JwtAuthenticationToken(jwt, authorities, "user-0042")`, then:

- `authentication.getPrincipal()` is still the **`Jwt`** object.
- `authentication.getName()` is **`user-0042`**.
- `authentication.getAuthorities()` is the supplied authority set.

This often fulfills the requirement to "rename the principal to an internal ID" **without having to invent a custom authentication token class**.

### 2.1. What Does `@AuthenticationPrincipal Jwt` Receive?

In a WebFlux controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class IdentityController {

    @GetMapping("/token-subject")
    Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(jwt.getSubject());
    }
}
~~~

In default JWT setups or when using `JwtAuthenticationToken`, `@AuthenticationPrincipal Jwt` reads the **JWT principal**; it does not automatically return a `LocalUser` loaded from the database.

If the local user ID is needed, the controller/service can accept `Authentication` and read `getName()` **if the converter set the name to the internal ID**. Otherwise, look up the local account by `(iss, sub)` where business logic needs it. Avoid relying on mutable emails as business data keys.

### 2.2. Scopes Are Not Local Roles

JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

is normally mapped by Spring Security into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Local roles might be:

~~~text
ROLE_MEMBER
ROLE_ORDER_SUPPORT
~~~

These are two distinct permission types. Scopes are granted by the Authorization Server to the client/token; internal roles or assignments may be managed by the business system. **Never promote a scope into an admin role**, and never treat arbitrary `roles` claims in a JWT as trusted authorities without a clear mapping contract.

## 3. What Does "Reactive Lookup" Mean?

In Spring WebFlux, I/O with latency is represented via a **Publisher** such as `Mono<T>` or `Flux<T>`. Account lookups can use:

- **Spring Data R2DBC / `ReactiveCrudRepository`** when the database supports reactive access.
- **Reactive Redis** or a compatible reactive cache/client.
- **`WebClient`** calling an identity/membership service over non-blocking HTTP.
- A reactive service combining multiple sources using `flatMap`/`zip` per policy.

Example:

~~~java
Mono<IdentityLink> linkMono =
    identityLinkRepository.findByIssuerAndSubject(issuer, subject);
~~~

`linkMono` is **a lazy/asynchronous computation description**, not an `IdentityLink` already materialized when the method returns. Only when Spring Security subscribes to the authentication chain does the repository execute the I/O via the publisher mechanism.

**Never call:**

~~~java
// WRONG on the WebFlux event loop:
IdentityLink link = repository
    .findByIssuerAndSubject(issuer, subject)
    .block();
~~~

`block()` turns reactive work into synchronous waiting, risking stalling the Netty event loop, reducing throughput, or triggering Reactor errors for blocking calls on non-blocking threads.

Nor should you do:

~~~java
// WRONG: manual subscribe then immediately returning authentication.
repository.findByIssuerAndSubject(issuer, subject)
    .subscribe(link -> updateGlobalPrincipal(link));

return Mono.just(defaultAuthentication);
~~~

Because `subscribe()` runs work detached from the authentication chain, **the request can proceed before the lookup finishes**. Errors are not propagated to the right place, state can leak across requests, and fail-open/race conditions easily arise.

**Right:** return a `Mono<AbstractAuthenticationToken>` containing the lookup; Spring Security waits for the publisher to complete before considering authentication conversion finished.

## 4. When Is a Lookup Needed Directly Inside the JWT Authentication Converter?

A lookup **at authentication time** makes sense when every protected request **must** satisfy an internal identity condition:

- Every user must be linked to a local account.
- A disabled local account must not invoke any protected API.
- Auditing and downstream systems strictly require an internal user ID.
- The API needs a common authority derived from verified account status.

Example policy:

~~~text
JWT verified
  -> find local account by (issuer, subject)
  -> account exists?
  -> enabled?
  -> create JwtAuthenticationToken with name = internalUserId
  -> evaluate endpoint scopes
~~~

When every protected endpoint requires a local account, this is a clear **authentication contract**. However, if some public or service-to-service endpoints do not need a user account, forcing a mandatory lookup on every request can unnecessarily block valid traffic.

### 4.1. When Only a Few Endpoints Need Business Data

Example:

- `GET /api/public/catalog` requires no login.
- `GET /api/catalog` may require only a token/`catalog.read`.
- `GET /api/me/profile` needs a local account/profile.
- `GET /api/orders/42` needs a local account and permission on Order 42.

In this case, **do not force every access token to query the Profile DB inside the converter** solely to serve `/api/me`. Keep authentication JWT-based, then look up the profile in the **reactive service** of the endpoints that need the data.

**Design boundary:** "Who is the caller?" can be established by the JWT; "what status/permissions does this person currently have in the database?" is a decision for the local account service or resource policy, checked when actually needed.

### 4.2. Lookup Placement Decision Table

| Need | Recommended placement | Why |
| --- | --- | --- |
| Need only `sub`, `scope`, issuer | No lookup; default converter | Avoids unnecessary I/O |
| Want principal name from a verified JWT claim | `ReactiveJwtAuthenticationConverter.setPrincipalClaimName(...)` | No database needed |
| All protected endpoints require an enabled local account | Custom **reactive JWT converter** | Global auth depends on account state |
| Only `/api/me` needs a DB profile | Reactive controller/service | Avoids reading profile on every request |
| Authorization on Order 42, current tenant | Reactive authorization/service/repository | Per-resource permission, unsuitable for global principal |
| Every request needs live DB roles | Reactive converter or authorization manager with cache policy | Roles can change after JWT issuance |
| Permission based on URL path and order state | Service/method-level resource policy | Order ID is unknown in a generic converter |

A pragmatic rule: **place the lookup at the narrowest layer that satisfies the security requirement**, rather than turning the authentication converter into a massive business workflow.

## 5. JWT Pipeline in Spring Security WebFlux

In a WebFlux Resource Server:

~~~text
ServerWebExchange
  |
  v
SecurityWebFilterChain
  |
  v
Bearer token extraction
  |
  v
ReactiveJwtDecoder
     verify signature, issuer, audience, exp/nbf...
  |
  v
Converter<Jwt, Mono<AbstractAuthenticationToken>>
     default: claims -> JwtAuthenticationToken
     custom: reactive lookup -> mapping -> JwtAuthenticationToken
  |
  v
Authentication in Reactor Context
  |
  v
authorizeExchange, reactive method security, service policy
~~~

**WebFlux differs from Servlet in how context is stored**. Never assume `SecurityContextHolder` on a `ThreadLocal` will follow a request across all threads in Reactor. In WebFlux, access the security context reactively via **`ReactiveSecurityContextHolder`**, or receive the principal via controller argument resolution.

### 5.1. Commonly Used Classes and Types

| Type | Purpose |
| --- | --- |
| `ReactiveJwtDecoder` | Non-blocking JWT verification and decoding in a reactive pipeline |
| `Jwt` | JWT claims accepted by the decoder |
| `Converter<Jwt, Mono<AbstractAuthenticationToken>>` | Reactively transforms JWT into authentication |
| `ReactiveJwtAuthenticationConverter` | Default/configurable reactive converter mapping JWT authorities/name |
| `ReactiveJwtAuthenticationConverterAdapter` | Wraps a **synchronous** converter to fit the reactive API; **does not make blocking I/O non-blocking** |
| `JwtGrantedAuthoritiesConverter` | Maps JWT `scope`/`scp` to `SCOPE_...` (synchronous, CPU-only) |
| `JwtAuthenticationToken` | Common authentication holding `Jwt` as principal |
| `ReactiveSecurityContextHolder` | Reads/writes security context in Reactor subscriber context |
| `SecurityWebFilterChain` | Protects exchanges and selects HTTP rules |
| `@EnableReactiveMethodSecurity` | Enables reactive method security |

When porting Servlet code to WebFlux, **never** copy synchronous `JwtAuthenticationConverter` and call a reactive repository with `.block()`. Choose a `Mono`-returning converter or move the lookup to a reactive service.

## 6. Preparing Identity Link Data

Suppose the application uses PostgreSQL and Spring Data R2DBC. Illustrative table:

~~~sql
CREATE TABLE identity_links (
    id BIGSERIAL PRIMARY KEY,
    issuer VARCHAR(320) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    internal_user_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_identity_issuer_subject UNIQUE (issuer, subject)
);
~~~

**The unique constraint on `(issuer, subject)` protects uniqueness**, not just lookup speed. An OAuth subject can collide across issuers, so storing `sub` alone is usually insufficient.

Record and repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("identity_links")
public record IdentityLink(
        @Id Long id,
        String issuer,
        String subject,
        String internalUserId,
        boolean enabled) {
}
~~~

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface IdentityLinkRepository
        extends ReactiveCrudRepository<IdentityLink, Long> {

    Mono<IdentityLink> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

Dependencies if using Spring Data R2DBC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Dependency versions are managed by the Spring Boot BOM when using the corresponding dependency management. Never treat a synchronous Hibernate/JPA repository as an R2DBC repository just because a wrapper method returns `Mono`: **the underlying I/O must genuinely be non-blocking** or isolated in a controlled manner.

### 6.1. Do Not Store Every Claim as a Canonical Profile

An identity link needs only the minimal data required for mapping and checking account state. Never automatically copy `email`, `roles`, `groups`, or the full JWT payload into the database on every request. Those fields can change, carry privacy implications, or require a separate synchronization contract.

### 6.2. Who May Create an Identity Link?

**Never auto-create a privileged account simply because a JWT contains a new `email` or `sub`**. Account linking/onboarding must follow policy:

- Issuer belongs to the trusted set.
- Subject has passed token verification.
- Email may change or may not be verified per profile.
- Never auto-merge accounts solely on matching email across two issuers.
- New links may require an invitation, tenant membership, or an approval step.
- A Client Credentials token does not represent a user account.

If no link is found, the API can reject at authentication **when the contract requires every caller to have a local account**, or return an explicit onboarding status at endpoints allowing unlinked subjects.

## 7. Custom Reactive JWT Converter: Lookup Then Create Authentication

This core example satisfies the exact requirement: **verified JWT → reactive identity link query → account check → internal principal name**.

### 7.1. Converter Implementing `Converter<Jwt, Mono<AbstractAuthenticationToken>>`

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class LinkedPrincipalJwtConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final IdentityLinkRepository links;
    private final JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    public LinkedPrincipalJwtConverter(IdentityLinkRepository links) {
        this.links = links;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        // Reached only after ReactiveJwtDecoder has verified the JWT.
        String issuer = jwt.getIssuer() != null
                ? jwt.getIssuer().toString()
                : null;
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            return Mono.error(new BadCredentialsException(
                    "Verified issuer or subject is missing"));
        }

        return links.findByIssuerAndSubject(issuer, subject)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException(
                    "No local account is linked to this identity")))
            .flatMap(link -> {
                if (!link.enabled()) {
                    return Mono.error(new DisabledException(
                            "Local account is disabled"));
                }

                Collection<GrantedAuthority> tokenScopes =
                        scopeConverter.convert(jwt);
                List<GrantedAuthority> authorities =
                        new ArrayList<>();

                if (tokenScopes != null) {
                    authorities.addAll(tokenScopes);
                }

                // Grant only a generic role based on valid account data.
                authorities.add(new SimpleGrantedAuthority(
                        "ROLE_MEMBER"));

                AbstractAuthenticationToken authentication =
                        new JwtAuthenticationToken(
                                jwt,
                                authorities,
                                link.internalUserId());

                return Mono.just(authentication);
            });
    }
}
~~~

### 7.2. Why Is This Reactive?

- `IdentityLinkRepository.findByIssuerAndSubject(...)` returns **`Mono<IdentityLink>`**; there is no `block()`.
- `switchIfEmpty(...)` rejects unlinked identities per the **example contract**.
- `flatMap(...)` continues the chain once I/O completes.
- If the account is disabled, the chain ends with **`Mono.error(...)`**, returning no fake authentication.
- If the account is valid, the converter returns **`Mono<AbstractAuthenticationToken>`**.
- The original JWT stays inside `JwtAuthenticationToken`; `getName()` is now the local user ID.

**This is not a complete user/role system.** The example grants only `ROLE_MEMBER` to enabled local accounts. Adding tenant-specific roles requires an explicit membership lookup and policy. Never treat everyone in an identity-link table as **`ROLE_ADMIN`**.

### 7.3. Why Use `iss + sub` Instead of Only `sub`?

A JWT with `sub = user-842` issued by Issuer A can represent an entirely different user from `sub = user-842` issued by Issuer B. Using `(iss, sub)` prevents **identity collision/cross-issuer account confusion**. However, this only holds when **`ReactiveJwtDecoder` has already verified the issuer/token from a trusted source**, never letting an arbitrary JWT fill in `iss` and query local accounts.

### 7.4. Why Keep `JwtAuthenticationToken`?

When only an **internal name and authorities** are needed, keeping `JwtAuthenticationToken` brings benefits:

- `getPrincipal()` remains the verified JWT.
- `@AuthenticationPrincipal Jwt` continues to work.
- Components aware of OAuth2 Bearer authentication still see the expected token family.
- You avoid writing a custom `Authentication` subtype and handling every token attribute, credential, and exception integration.

**Trade-off:** `getPrincipal()` **does not become an `IdentityLink` or domain `User`**. If a controller needs the full user object, look it up via a reactive service when needed, or deliberately design an authentication subtype holding the domain principal and test compatibility with Spring Security Bearer handling.

### 7.5. Missing Identity Link: 401 or 403?

In this example, **local account linking is a global authentication condition**. Missing links or disabled accounts cause the converter to emit an `AuthenticationException`, and requests typically fail authentication with 401.

Another system, however, might allow users with a valid JWT to reach `/api/onboarding` before a local account exists. In that case, do not put `switchIfEmpty(BadCredentialsException)` on **every** protected endpoint. Keep JWT-based authentication and check the account link in the onboarding/business service; lacking access to a specific resource once authenticated normally yields 403/404 per policy.

**Choose status codes according to the contract**, not merely based on whether a repository returned a row.

## 8. Wiring the Converter into `SecurityWebFilterChain`

A WebFlux Resource Server configuration with Java 17+, Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server
        .ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.core.convert.converter.Converter;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class WebFluxOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            Converter<Jwt, Mono<AbstractAuthenticationToken>>
                    jwtAuthenticationConverter) {

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .build();
    }
}
~~~

`LinkedPrincipalJwtConverter` from Section 7 is a `@Component` Spring bean implementing `Converter<Jwt, Mono<AbstractAuthenticationToken>>`, so it can be injected as a parameter into `apiChain(...)`. Do not register a second converter bean of the same type where Spring's bean choice becomes ambiguous.

### 8.1. `application.yml` Configuring the JWT Decoder

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

The issuer URI and JWKS URI are **configuration examples**; pull real values from your Identity Server. The Resource Server must verify the JWT **before** the converter. Configuring issuer/JWKS alone **does not mean every version automatically checks the audience expected by your application**; configure an audience validator for `orders-api` appropriate to `ReactiveJwtDecoder` and your version.

Token type/profile, expiration, allowed algorithms, and JWKS rotation handling must also be defined in the security contract. **Never solve JWT validation by putting logic in a controller** or trusting claims not yet verified by the decoder.

### 8.2. CSRF in the Sample Configuration

`csrf(...disable)` is used here assuming the API authenticates solely via **Bearer tokens explicitly sent by clients in the Authorization header**, never accepting session cookies/token cookies as web credentials. If an API relies on auto-sent cookies, design CSRF properly regardless of stateless JWT processing.

### 8.3. HTTP Rules Still Need Business Authorization

`GET /api/orders/42` passes the HTTP rule if the authentication holds `SCOPE_orders.read`. **Never infer that all orders belong to the user.** Check owner, tenant, or assignment inside the reactive service/repository.

### 8.4. URL Paths and WebFlux Differ from Servlet

WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity.authorizeExchange(...)`, not the Servlet stack's `SecurityFilterChain`/`HttpSecurity.authorizeHttpRequests(...)`. Security code across the two models cannot be mechanically renamed with expectations that filters and context behave identically.

## 9. When Only Changing the Name from a JWT Claim: No Database Needed

If the Authorization Server already provides a trusted claim suitable as the principal name, configure `ReactiveJwtAuthenticationConverter` **without any I/O lookup**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverter;

@Bean
ReactiveJwtAuthenticationConverter simpleJwtConverter() {
    ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
    converter.setPrincipalClaimName("sub");
    return converter;
}
~~~

`sub` is usually a more stable choice than a display name/email within an issuer. If using another claim such as `preferred_username`, remember it can change and is not guaranteed unique. **Choosing a principal name is an identification decision**, not an authorization step.

Default `ReactiveJwtAuthenticationConverter` can map scopes/authorities from the JWT per Spring's conventions. When DB-backed permissions are needed, use a reactive converter as in Section 7 or a `Converter<Jwt, Flux<GrantedAuthority>>` for authorities per your version's support.

### 9.1. `ReactiveJwtAuthenticationConverterAdapter` Does Not Make JDBC Reactive

This adapter can wrap a **synchronous, CPU-only** JWT converter for use in a WebFlux pipeline:

~~~java
// Illustrative idea: a synchronous converter reading only JWT claims
// can be adapted to the reactive API.
new ReactiveJwtAuthenticationConverterAdapter(
    new JwtAuthenticationConverter());
~~~

Yet if that synchronous converter calls JPA/JDBC, blocking LDAP, or `WebClient.block()`, wrapping it with the adapter **does not make the I/O non-blocking**. Use a reactive repository or move the lookup into a genuinely reactive service.

## 10. Second Approach: Look Up Only When Business Endpoints Need It

This is often the better choice when the API **does not require every caller to have a local account**. `SecurityWebFilterChain` can use the default JWT converter:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

Once the token is verified, the controller/service queries the database for endpoints that need a profile or resource policy.

### 10.1. Controller Receiving the Verified JWT and Calling a Reactive Service

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/me")
class MyProfileController {

    private final MyProfileService profiles;

    MyProfileController(MyProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping
    Mono<ProfileDto> myProfile(
            @AuthenticationPrincipal Jwt jwt) {

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        return profiles.findByExternalIdentity(issuer, subject);
    }
}
~~~

`MyProfileService` and `ProfileDto` are illustrative business components. This fits well when `/api/me` needs a local profile, sparing other endpoints from paying the same I/O lookup cost.

### 10.2. Reactive Service Handling a Missing Profile

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class MyProfileService {

    private final IdentityLinkRepository links;
    private final ReactiveProfileRepository profiles;

    MyProfileService(
            IdentityLinkRepository links,
            ReactiveProfileRepository profiles) {
        this.links = links;
        this.profiles = profiles;
    }

    Mono<ProfileDto> findByExternalIdentity(
            String issuer, String subject) {

        return links.findByIssuerAndSubject(issuer, subject)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not linked")))
            .flatMap(link -> profiles
                .findByInternalUserId(link.internalUserId()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found")));
    }
}
~~~

`ReactiveProfileRepository`/`ProfileDto` are application-specific components. **Missing profile** could return 404, 403, or an onboarding response per contract. Do not assume 404 is always right; the snippet illustrates one policy for `/api/me`.

### 10.3. How Does This Differ from Looking Up During Authentication?

| Lookup in converter | Lookup in business service |
| --- | --- |
| Every protected authentication triggers a lookup | Only endpoints using a local account trigger a lookup |
| Missing link can prevent the JWT from authenticating | JWT can still authenticate while a business operation is denied |
| `Authentication.getName()` can be the internal user ID | Default name is usually JWT `sub` |
| Easy to enforce an API-wide active-account gate | Easy to separate user/service/onboarding flows |
| Increases database dependency for all protected requests | Limits dependency to features needing that data |
| Risks bloating the converter into business logic | Keeps per-resource policy in the right service |

No single option is always right for every system. **Place the lookup according to the invariant**: API-wide requirements can live in the converter; operation/resource-specific requirements belong in the service/authorization layer.

## 11. Reactive Security Context: Do Not Rely on ThreadLocal

In the Servlet stack, many examples read:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, a single request may run across multiple operators and threads under Reactor. Therefore, **do not use ThreadLocal `SecurityContextHolder` as the default source in reactive services**. Use:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication());
}
~~~

`ReactiveSecurityContextHolder` uses the **Reactor Context**, propagated along the subscription context when the pipeline is properly composed.

### 11.1. Reading the Internal Principal Name in a Service

When using the converter from Section 7, `Authentication.getName()` is `internalUserId`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class OrderQueryService {

    private final ReactiveOrderRepository orders;

    OrderQueryService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    Mono<OrderDto> getOwnOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED)))
            .flatMap(authentication -> {
                if (!(authentication
                        instanceof JwtAuthenticationToken)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.UNAUTHORIZED));
                }

                String internalUserId = authentication.getName();
                // Prefer also filtering by tenant in multi-tenant systems.
                return orders.findByIdAndOwnerUserId(
                        orderId, internalUserId);
            })
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found")));
    }
}
~~~

`ReactiveOrderRepository.findByIdAndOwnerUserId(...)` and `OrderDto` are illustrative components. The query must **filter by owner in the database**, rather than fetching all orders and relying on the UI to hide data. In multi-tenant systems, filter by tenant and status per policy as well.

**Error note:** the 404 response here limits disclosing whether someone else's order exists. Another API may choose 403 per contract. What is mandatory is **never returning data or performing changes when the caller lacks permission**.

### 11.2. Receiving Authentication via Method Argument

A WebFlux controller can also receive `Authentication`/principal via argument resolution:

~~~java
@GetMapping("/me/id")
Mono<String> internalId(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

Rely on `authentication.getName()` being the internal ID only when **the converter guarantees it**. With the default converter, the name is likely still `sub`. **Never mix the two conventions** across endpoints.

### 11.3. Never Use a Static/Global Variable to Hold the Principal

~~~java
// SEVERE MISTAKE:
static String currentUserId;
~~~

WebFlux requests run concurrently and may interleave multiple subscribers. Storing identity in a static field or a mutable per-request singleton causes **cross-user data leakage**. Reactor Context or method arguments are the proper mechanisms.

## 12. Reactive Role/Permission Lookup Differs from Principal Lookup

Many systems need to load **roles** from the database based on the identity link:

~~~text
JWT (iss, sub)
  -> identity link
  -> internal user ID
  -> roles / memberships from DB
  -> GrantedAuthority
~~~

This is an option, yet distinguish clearly:

- **Principal mapping**: links external identity to a local account.
- **Authority mapping**: turns trusted permissions into `GrantedAuthority` instances.
- **Resource authorization**: checks whether the user may act on a **specific order/tenant**.

### 12.1. Reactive Authorities Converter

Spring Security provides `ReactiveJwtAuthenticationConverter`, which can be customized with an authorities converter returning `Flux<GrantedAuthority>` per your version's interface.

Conceptual example, if a reactive role repository returns **allowlisted** role codes:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverter;

import reactor.core.publisher.Flux;

ReactiveJwtAuthenticationConverter converter =
        new ReactiveJwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Flux<GrantedAuthority> scopeAuthorities =
            Flux.fromIterable(scopes.convert(jwt));

    Flux<GrantedAuthority> roleAuthorities =
            roleRepository.findAllowedRolesByIssuerAndSubject(
                    jwt.getIssuer().toString(), jwt.getSubject())
                .map(roleCode -> (GrantedAuthority)
                    new SimpleGrantedAuthority("ROLE_" + roleCode));

    return Flux.concat(scopeAuthorities, roleAuthorities);
});
~~~

`roleRepository` is a reactive repository/service **built by the application**, and returned role codes must be constrained to an **allowlist**. This example demonstrates **reactive authority loading**; it does not change `JwtAuthenticationToken.getName()` to the local user ID. When both internal user ID and roles are needed, a combined custom converter like Section 7 or a coordinating reactive service may be more suitable.

**Warning:** `Flux.fromIterable(scopes.convert(jwt))` assumes the converter returns a non-null collection; depending on custom converters and framework version, handle empty/null per contract. Never let a scope-mapping error cause the API to add default out-of-policy permissions.

### 12.2. Do Not Embed Every Tenant Role into Global Authentication

Suppose a user is admin in Tenant A but only reader in Tenant B. If the converter emits:

~~~text
ROLE_TENANT_ADMIN
~~~

without tenant context, a Tenant B endpoint might misinterpret that role and grant excess privileges.

Safer practices:

- Grant global authorities only when genuinely global.
- Scope tenant entitlements with explicit namespacing **if policy is designed for it**.
- When accessing Order 42, check tenant and membership/assignment **for Order 42**.
- Never trust `X-Tenant-Id` or a client-sent path tenant as proof the caller belongs to that tenant.

**Database-loaded roles do not automatically eliminate BOLA/IDOR**. You must still verify object-level permissions.

## 13. Reactive Resource-Level Authorization

`SCOPE_orders.read` permits a **read operation category**, not necessarily reading another user's order.

Suppose an Order:

~~~json
{
  "id": "42",
  "ownerUserId": "user-0042",
  "tenantId": "tenant-A",
  "status": "PAID"
}
~~~

A request:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <jwt-of-user-0042>
~~~

must verify all of:

~~~text
JWT valid + aud = orders-api
AND scope orders.read
AND identity maps to user-0042
AND order belongs to a tenant allowed for this caller
AND caller is owner or assigned support under policy
~~~

### 13.1. Data-Filtering Directly in the Repository

For an endpoint allowing only the order owner to view:

~~~java
Mono<OrderDto> findByIdAndOwnerUserId(
        String orderId, String ownerUserId);
~~~

If multi-tenant:

~~~java
Mono<OrderDto> findByIdAndTenantIdAndOwnerUserId(
        String orderId, String tenantId, String ownerUserId);
~~~

`tenantId` must come from **verified membership/policy** (or server-verified context), never blindly accepted from query parameters or headers. Filtering at the database avoids fetching unauthorized data only to block it in the controller.

### 13.2. Reactive Authorization Manager When Policy Lives at the HTTP Layer

In some cases, you can use `ReactiveAuthorizationManager<AuthorizationContext>` to combine `Authentication` and permission-check I/O:

~~~java
// Pseudocode illustrating flow, not a complete class/config:
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context) {

    String id = context.getVariables().get("id");
    return authentication
        .flatMap(auth -> accessPolicy.canReadOrder(
                auth.getName(), id))
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

Depending on the Spring Security version, `ReactiveAuthorizationManager`/`AuthorizationContext` types and path-variable access must be configured accurately in the `authorizeExchange` DSL. **This is pseudocode** illustrating policy placement, not standalone runnable configuration.

For complex systems, checking permissions in a **reactive domain service** is often clearer because the service holds business state and can perform checks/data transactions in the right place. Even when enforcing policy at the HTTP layer, still protect alternate service entry points if business methods can be called by background jobs or message consumers.

### 13.3. Method Security in WebFlux

`@EnableReactiveMethodSecurity` enables `@PreAuthorize` on proxy-protected methods. Example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderDto> getOrder(String orderId) {
    return orderQueryService.getOwnOrder(orderId);
}
~~~

**A method-level scope check does not replace looking up permissions on the Order**. In real code, ensure the method is invoked through a Spring proxy and returns a supported reactive type. If authorization depends on tenant/assignment state, the logic should use a reactive policy service without blocking.

## 14. Special Danger: Looking Up Data Before Verifying the Token

An architectural flaw:

~~~text
HTTP Bearer JWT
  -> manually Base64-decode payload
  -> extract sub and email
  -> query DB and build principal with ROLE_MEMBER
  -> verify signature afterward
~~~

Never do this. An unverified JWT payload can be altered arbitrarily. An attacker can fill in someone else's `sub` or privileged `roles`.

Proper pipeline:

~~~text
Bearer token
  -> ReactiveJwtDecoder verifies signature + validators
  -> only upon success is Jwt received
  -> Converter uses verified iss/sub for lookup
  -> Authentication/authorities
  -> endpoint/resource authorization
~~~

**Audience reminder:** a JWT validly signed by the right issuer yet meant for the Billing API must not be accepted by the Orders API. Enforce `aud` per contract, not just signature validity.

### 14.1. Email Linking Carries Specific Risk

Suppose two issuers emit the same `email`, a user changes email, or `email_verified` is not guaranteed by the profile. If the API auto-links by email:

~~~text
email = user@example.test
  -> find local account matching email
  -> assume that user by default
~~~

it can cause **account takeover or identity confusion**. Prefer an approved mapping by **`(iss, sub)`** with a secure onboarding/account-linking workflow, never auto-merging accounts merely on matching email.

### 14.2. Client Credentials Tokens Are Not User Tokens

A `client_credentials` access token may carry a service's subject/client ID:

~~~json
{
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

If a custom converter mandates a user account for **every token**, valid service tokens will be blocked. When an API supports both user and service callers, design distinct profiles:

- User JWT: map identity via `(iss, sub)` to a local user.
- Service JWT: verify client identity/audience and a dedicated service policy.
- Never turn `client_id` into an `internalUserId` or order ownership.
- Never grant `ROLE_MEMBER`/`ROLE_ADMIN` to every token merely because authentication succeeded.

## 15. Do Not Block the Netty Event Loop

In WebFlux, blocking I/O inside a converter can severely degrade throughput. Wrong:

~~~java
@Override
public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
    // WRONG example: blocking JPA call on the event loop
    LocalUser user = jpaRepository.findByExternalSubject(
            jwt.getSubject());
    return Mono.just(createAuthentication(jwt, user));
}
~~~

A synchronous JPA/JDBC repository remains **blocking** even when wrapped in `Mono.just(...)`. `Mono.just(...)` only wraps an **already-computed value**; it never turns blocking I/O into non-blocking execution.

### 15.1. Prefer Reactive Drivers and Clients

~~~text
Spring Data R2DBC / reactive identity service
  -> Mono<IdentityLink>
  -> flatMap(account validation)
  -> Mono<Authentication>
~~~

If a legacy system **must** use a blocking API, a temporary isolation pattern is:

~~~java
Mono<LocalUser> userMono = Mono.fromCallable(
        () -> legacyBlockingRepository.findUser(issuer, subject))
    .subscribeOn(Schedulers.boundedElastic());
~~~

This is a **transitional workaround**, not making the driver reactive. Bound concurrency, timeouts, connection pools, and observe load. Do not run large volumes of blocking lookups on the event loop, and do not rely on bounded elastic indefinitely to hide architectural debt. When a database/service supports reactive clients, use a genuinely reactive client.

### 15.2. Do Not Use `parallel()` Arbitrarily

Increasing parallelism does not make a database faster if the connection pool or downstream lacks capacity. A request may need profile, groups, and membership; if calling three services in parallel, manage fan-out, timeouts, connection counts, and behavior when one dependency fails.

`Mono.zip(...)` can help when lookups are independent, yet **never return `Authentication` before all mandatory conditions complete**.

## 16. Latency, Caching, Stale Roles, and Availability

Placing a lookup inside the authentication converter means **every protected request** may incur database/network access. That introduces costs:

- P50/P95/P99 latency rises due to an extra hop.
- The database/identity service becomes an authentication dependency.
- Connections, threads, and concurrent requests must be reasonably bounded.
- If downstream becomes unavailable, the API may fail to authenticate requests even with valid JWTs.
- Dynamic permissions are fresher than JWTs, though caching reduces freshness.

### 16.1. Should Identity Links Be Cached?

Possibly, provided you clearly define:

| Aspect | Decision required |
| --- | --- |
| Cache key | At minimum distinguish `issuer + subject`, plus tenant/context if results depend on tenant |
| TTL | Bounded by risk, account disabling, and freshness policy |
| Revocation | How quickly must disabled users or revoked links take effect? |
| Authorities | Are dynamic roles cached? If so, what is the maximum revocation delay? |
| Invalidation | Are there events/policy versions when roles/memberships change? |
| Cache miss | Normal reactive lookup, never auto-allow |
| Outage | May valid cached snapshots be used? Under what conditions? |

Calling `Mono.cache()` on **a single Publisher** caches only that publisher's outcome; it does not turn every JWT request into a proper cache with TTL and invalidation. Conversely, an unbounded global cache can keep an **account enabled** even after the user is locked.

### 16.2. Authentication Lookup Failures Must Fail Closed

Do not write:

~~~java
// WRONG: A DB error does not mean the caller is an admin.
return links.findByIssuerAndSubject(issuer, subject)
    .onErrorResume(ex -> Mono.just(adminIdentityLink));
~~~

An I/O failure leaves the system **without trusted evidence to bind an identity**. Never create valid authentication from fabricated data. Return a 5xx dependency error per policy/exception handling or reject authentication accordingly; **never execute protected actions**.

### 16.3. Distinguish "Link Not Found" from "DB Failing"

~~~text
Mono.empty():
  -> no record exists per contract
  -> may reject unlinked account/onboarding

Mono.error(databaseTimeout):
  -> account cannot be determined
  -> dependency failure, must not pass
~~~

**Do not turn every network error into "account does not exist"** when investigating incidents, nor turn every network error into "account is valid." Logs and metrics must distinguish them without leaking sensitive details to the client.

### 16.4. Time-of-Check / Time-of-Use

Suppose the converter confirms the account is enabled at T1, yet permissions are revoked at T2 before updating an order. For highly sensitive actions, re-checking permissions at **write time** or within the transaction/policy may be necessary.

**A principal snapshot at the start of a request does not solve every permission race condition.** That is why resource policies belong close to business mutations, not solely as roles attached at authentication.

## 17. Testing the Converter with Reactor Test `StepVerifier`

Because the converter returns `Mono<AbstractAuthenticationToken>`, you can unit test its logic without running a web server.

### 17.1. Creating a JWT Fixture

~~~java
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

static Jwt jwt(String subject) {
    return Jwt.withTokenValue("test-jwt-not-signed")
        .header("alg", "RS256")
        .issuer("https://identity.example.test/realms/shop")
        .subject(subject)
        .audience(List.of("orders-api"))
        .claim("scope", "orders.read")
        .build();
}
~~~

This is a **mock `Jwt` object for unit tests**, not a real signed or verified token. It is only suitable for testing logic **after the decoder**. Signed-JWT integration tests must use tokens signed with test keys and a real decoder.

### 17.2. Testing the Mapped Principal Name

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class LinkedPrincipalJwtConverterTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/shop";

    @Test
    void mapsVerifiedExternalIdentityToLocalPrincipalName() {
        IdentityLinkRepository repo =
                mock(IdentityLinkRepository.class);
        when(repo.findByIssuerAndSubject(
                ISSUER, "external-user-842"))
            .thenReturn(Mono.just(new IdentityLink(
                1L,
                ISSUER,
                "external-user-842",
                "user-0042",
                true)));

        var converter = new LinkedPrincipalJwtConverter(repo);

        StepVerifier.create(
                converter.convert(jwt("external-user-842")))
            .assertNext(authentication -> {
                assertTrue(authentication
                        instanceof JwtAuthenticationToken);
                assertEquals("user-0042",
                        authentication.getName());
                assertTrue(authentication.getAuthorities()
                    .stream()
                    .anyMatch(a ->
                        a.getAuthority().equals(
                            "SCOPE_orders.read")));
            })
            .verifyComplete();
    }
}
~~~

`jwt(...)` is the helper from Section 17.1 and should be placed in the test class or a shared helper. JUnit/Mockito/Reactor Test are used strictly within **converter unit test** scope, without running Gradle or using production-signed JWTs.

### 17.3. Testing Missing Local Account

~~~java
@Test
void rejectsUnlinkedIdentity() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "unknown-subject"))
        .thenReturn(Mono.empty());

    var converter = new LinkedPrincipalJwtConverter(repo);

    StepVerifier.create(converter.convert(jwt("unknown-subject")))
        .expectError(BadCredentialsException.class)
        .verify();
}
~~~

If the system allows onboarding without a local account, adapt this test to **that contract** rather than copying it verbatim.

### 17.4. Testing Disabled Account and DB Failure

~~~java
@Test
void rejectsDisabledAccount() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "external-user-842"))
        .thenReturn(Mono.just(new IdentityLink(
            1L, ISSUER, "external-user-842", "user-0042", false)));

    var converter = new LinkedPrincipalJwtConverter(repo);
    StepVerifier.create(converter.convert(jwt("external-user-842")))
        .expectError(DisabledException.class)
        .verify();
}

@Test
void doesNotAuthenticateWhenRepositoryFails() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "external-user-842"))
        .thenReturn(Mono.error(
            new IllegalStateException("Database unavailable")));

    var converter = new LinkedPrincipalJwtConverter(repo);
    StepVerifier.create(converter.convert(jwt("external-user-842")))
        .expectError(IllegalStateException.class)
        .verify();
}
~~~

These are **illustrative test methods** using the same imports/fixtures as the previous section. They verify there is no fallback granting permissions when the lookup returns empty, disabled, or errors.

### 17.5. Testing the Same Subject Across Two Issuers

An important test:

~~~text
iss=shop,    sub=user-842 -> internal user-0042
iss=partner, sub=user-842 -> internal user-1290
~~~

The verifier must confirm the repository is queried with the **exact issuer and subject** in each case, and authentication names never mix. This is a negative test for identity confusion/cross-issuer mapping.

## 18. WebFlux Testing with `WebTestClient`

Spring Security Test supports `mockJwt()` for WebFlux to inject an authentication with simulated claims/authorities.

Illustrative example:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

**Important:** `mockJwt()` can **bypass `ReactiveJwtDecoder` and the custom converter** by inserting a simulated authentication directly into the web test. It is a great tool for testing authorization/handlers **once an Authentication exists**, but it does not prove the reactive identity lookup was called or that JWT signatures are valid.

### 18.1. Test Suites to Keep Separate

| Test level | Tool | What is proven |
| --- | --- | --- |
| Converter unit | `StepVerifier` + mock reactive repository | `(iss, sub)` mapping, disabled account, authority/name, error propagation |
| HTTP authorization | `WebTestClient` + `mockJwt()` | `pathMatchers` rules, scopes, and 401/403 paths with mocked auth |
| JWT decoder integration | Signed test JWT + mock JWKS + real `ReactiveJwtDecoder` | Signature, issuer, audience, timestamps, and decoder |
| Authentication integration | Signed JWT + real converter + test R2DBC/service | Non-blocking lookup runs before building authentication |
| Business policy | Repository/service tests | Owner, tenant, membership, no cross-user access |
| Load/resilience | Controlled dependency latency/failures | Timeouts, pool pressure, fail-closed fallback |

### 18.2. End-to-End Test Scenarios

~~~text
1. Valid signed JWT, account enabled, sufficient scope
   -> authenticated, name = localUserId, passes HTTP rule

2. Valid signed JWT, missing account link
   -> rejected under mandatory-linking contract

3. Valid signed JWT, disabled account
   -> rejected

4. Valid signed JWT, insufficient scope
   -> authentication may succeed, HTTP authorization 403

5. Invalid JWT signature
   -> rejected by decoder; converter/repository not treated as trust source

6. Wrong issuer/audience
   -> rejected by decoder/validator before lookup

7. Valid JWT, enabled account, right scope,
   yet Order 42 belongs to another tenant
   -> rejected by business policy

8. Identity DB timeout
   -> no fake valid authentication, protected action does not execute

9. Client Credentials service JWT
   -> not mistakenly forced through user-only policy if endpoint supports services
~~~

Also assert **no database writes or business events** occur when a request is rejected. A final HTTP 403 status is insufficient if side effects already happened earlier.

### 18.3. Simulating Asynchrony to Verify Pipeline Behavior

In unit tests, have the repository return `Mono.defer(...)` or a delayed publisher to confirm authentication **never materializes before the lookup completes**. Never call `subscribe()` inside the converter to "speed up" execution.

A test may use `StepVerifier.withVirtualTime(...)` when the publisher uses an appropriate scheduler/clock; this is a Reactor testing technique, not a replacement for real database connectivity tests. The goal is for the **authentication chain to await the real outcome**, not to increase subscription counts.

## 19. Observability, Data Security, and Operations

A reactive principal lookup places the **identity service/database on the hot path of authentication**. Monitor:

- `ReactiveJwtDecoder` token verification duration.
- Converter lookup rates: hit/missing/disabled/error.
- Identity repository latency (P95/P99), connections, and pool usage.
- Timeout, saturation, rate-limit, or circuit-breaker counts.
- Rate of insufficient-scope rejections after authentication.
- Count of denials due to tenant/owner checks.

**Never log raw JWTs**, `Authorization` headers, refresh tokens, or client secrets. `iss`/`sub`/local user IDs can also be identifying data governed by audit/PII rules. For wrong issuers or unverified JWTs, treat every claim read from the token as **caller-controlled input**, never using it as an unbounded metric label.

### 19.1. Permissions and Identity Can Change While a JWT Is Unexpired

A JWT may have `exp` 30 minutes away while the local account is locked after 5 minutes. If the converter always queries whether the account is enabled, requests after locking can be rejected promptly per the database. If principals/roles are cached for a long time, disabled accounts may not be reflected immediately.

API protection depends on these decisions:

- Do user/role revocations need near-real-time effect, or is some delay acceptable?
- Cache by `(iss, sub)`, token, or tenant?
- Are invalidation events available?
- When the identity database is down, may cached active statuses still within TTL be accepted?
- If an identity link is reassigned, could stale cached authentication attach the wrong user?

This is a **trade-off between performance, availability, and permission freshness**, which cannot be solved with a one-line `.cache()`.

### 19.2. Never Use a Global Mutable Principal

WebFlux serves many concurrent requests. A singleton with a `currentPrincipal` field or a static `currentUserId` is broken by design: User A's value can be overwritten by User B. Use immutable data, Reactor Context, method arguments, and permission-scoped database queries.

### 19.3. When AS/JWKS Is Down vs. When the Identity DB Is Down

These are two distinct failure modes:

| Dependency | Role | When unavailable |
| --- | --- | --- |
| Authorization Server / JWKS | Supplies keys/metadata to verify JWTs | Decoder may use valid cached keys per policy; never accept unverified tokens |
| Identity Link DB | Maps external principal to local user | Converter requiring linking cannot finish authentication without a trusted result |
| Order DB | Checks permissions and returns resources | Never return resources when resource policy cannot be verified |

**Never turn an outage into `permitAll()` or default `ROLE_ADMIN`.** Distinguish operational failures from identity-not-found in internal logs without exposing sensitive tokens/PII to the client.

## 20. Common Implementation Pitfalls

### "Using `.block()` in the reactive JWT converter is faster to write"

Breaks the WebFlux model and can stall the event loop. Use reactive R2DBC/`WebClient` and return `Mono<Authentication>`.

### "Wrapping JPA in `Mono.just(jpaRepository.find(...))` makes it non-blocking"

No. JPA already blocked the thread **before `Mono.just` ran**. Use a reactive driver or isolate legacy blocking I/O on a bounded scheduler as a transitional measure.

### "`ReactiveJwtAuthenticationConverterAdapter` automatically turns a blocking repo into reactive"

No. The adapter only wraps the synchronous converter API; it does not make internal I/O non-blocking.

### "The converter runs before the JWT decoder verifies the signature"

Not in the standard pipeline. The Resource Server converter receives a `Jwt` after the decoder accepts the token. Never write a custom filter that decodes unverified payloads to look up permissions.

### "`sub` is unique enough across all issuers"

Not when the system trusts multiple issuers. Bind both issuer and subject.

### "Matching email means auto-link the account"

Dangerous due to mutable emails, cross-issuer collisions, and differing verification rules. Account linking needs an explicit workflow.

### "Changing `getName()` automatically makes `getPrincipal()` a domain `User`"

No. `JwtAuthenticationToken(jwt, authorities, name)` keeps `Jwt` as the principal and only changes the name.

### "Need permission on Order 42, so look it up in the authentication converter"

Usually inappropriate: the converter does not know the specific resource and may run for endpoints that have nothing to do with orders. Check permissions in a reactive business policy or resource authorization layer.

### "Every user and service token must have a local user ID"

Not if the API supports Client Credentials service principals. Separate contracts and permissions for users vs. services.

### "One global `ROLE_TENANT_ADMIN` suffices for every tenant"

No. A role in Tenant A must not grant Tenant B access without scope/tenant binding and resource checks.

### "When the repository lookup fails, create a guest/admin principal to avoid downtime"

Fail open. Without valid identity proof, protected actions must never run.

### "`Authentication.getName()` is email because OIDC login has email"

Not by default. The name depends on the converter; a JWT Resource Server is not the same as an OAuth2/OIDC Client login principal.

### "Use ThreadLocal `SecurityContextHolder` in every reactive operator"

Unsafe with Reactor thread switching. Use `ReactiveSecurityContextHolder` or WebFlux argument resolvers.

### "`mockJwt()` `WebTestClient` passing means the reactive converter works"

No. `mockJwt()` can bypass the decoder/converter; unit test the converter and integration test with signed JWTs.

### "Having the right scope lets you view every order"

No. Check owner, tenant, assignment, and data policies.

### "A cache without TTL boosts performance without affecting permissions"

Wrong. Disabled status, roles, and memberships become stale. Use TTLs/invalidation and protect cache keys.

## 21. Checklist When Building Principal Mapping in WebFlux

1. Is the JWT verified by `ReactiveJwtDecoder` with contract-compliant issuer/audience/timestamps before the converter runs?
2. Is `(iss, sub)` the identity-linking key guaranteed by the AS?
3. Is local user lookup required for **every** protected endpoint?
4. If only a few endpoints need a profile, has the lookup been moved to the appropriate service?
5. Are the repository and HTTP client genuinely non-blocking?
6. Are `.block()` and manual `.subscribe()` absent from the security flow?
7. Do missing/disabled accounts fail closed per contract?
8. Are DB outages distinguished operationally from account-not-found?
9. Are `Authentication.getName()` and `getPrincipal()` properly defined and never confused?
10. Do token authorities and local roles have clear prefixes and allowlist mappings?
11. Are tenant-specific permissions checked against the specific tenant/resource?
12. Do Client Credentials JWTs need a separate policy?
13. Does caching have TTLs, invalidation, and keys that cannot collide across users?
14. Do services read context via Reactor or receive `Authentication` properly?
15. Do tests cover signed JWTs, `WebTestClient`, `StepVerifier`, and negative cases?
16. Are rejected requests guaranteed to produce **no side effects**?

## 22. Scenario Exercises

**Scenario A:** A properly signed JWT has `sub=external-user-842`, while the database stores `user-0042`. To make `Authentication.getName()` return `user-0042` in WebFlux, what should you do?

**You can** use a custom `Converter<Jwt, Mono<AbstractAuthenticationToken>>` to reactively look up `(iss, sub)` and construct `JwtAuthenticationToken(jwt, authorities, "user-0042")`. A custom principal subtype is not strictly necessary if only an internal name is needed.

**Scenario B:** A developer writes `identityLinkRepository.findByIssuerAndSubject(...).block()` in the JWT converter. What is the risk?

**Blocking the event loop**, reducing concurrency and risking Reactor errors. Return a `Mono` from the converter and let Spring subscribe; use a real reactive repository/client.

**Scenario C:** Two issuers both have `sub="user-842"`, mapping to two different local users. What happens if you look up by `sub` alone?

It can **link the wrong account**, causing cross-issuer privilege and data leakage. Look up by `(iss, sub)` per contract, after the JWT has been verified.

**Scenario D:** The API has a catalog endpoint requiring only a scope, yet the converter always demands a user profile. When the Profile DB goes down, the protected catalog also goes down. What is a better design?

If account linking **is not a global requirement**, keep the JWT principal at authentication and look up profiles only at endpoints that need them. Moving the lookup reduces unnecessary coupling.

**Scenario E:** A token has scope `orders.read` and an enabled local account, yet Order 42 belongs to another tenant. Should access be allowed?

**No.** Authentication mapping and HTTP scopes can succeed; resource permissions must still reject based on owner/tenant.

**Scenario F:** A Client Credentials token has `client_id=nightly-sync` and no local user. The converter forces a user lookup and returns 401. Is the token broken?

**Not necessarily.** The service token may be valid yet **mismatch a user-only converter contract**. If the API supports services, define a separate principal/policy rather than assuming a service is a user.

**Scenario G:** A unit test using `mockJwt()` and `WebTestClient` returns 200. Does that prove the reactive database lookup ran?

**No.** `mockJwt()` can inject authentication directly. Test the converter with `StepVerifier` and run integration tests through the real chain with signed JWT + decoder + repository.

**Scenario H:** A JWT has 30 minutes left, the account is disabled, yet the local account cache has an infinite TTL. What is the risk?

The API may continue accepting a disabled account. Configure TTL/invalidation aligned with revocation policy and never cache indefinitely.

**Scenario I:** The converter queries the repository via `subscribe()` and returns `Mono.just(authentication)` immediately. What is wrong?

Authentication can complete **before the lookup**, errors fail to propagate down the pipeline, and race conditions arise. The lookup result must sit inside the **same `Mono<Authentication>` chain** awaited by Spring Security.

**Scenario J:** You change `JwtAuthenticationToken` name to the local user ID, then inject `@AuthenticationPrincipal Jwt jwt`. Does the controller receive the domain user?

**No.** The principal is still `Jwt`; only `getName()` changed. To obtain the domain user, perform a reactive lookup where needed or design an authentication subtype with an explicit contract.

---

## Conclusion

In a **Spring Security JWT Resource Server using WebFlux**, principal mapping with internal data lookups must respect **two boundaries**: **the JWT is verified first**, and then **identity/business permission lookups run via a non-blocking reactive pipeline**. When every protected request requires an enabled local user, a custom **`Converter<Jwt, Mono<AbstractAuthenticationToken>>`** can query `(iss, sub)` via R2DBC/`WebClient` and build a `JwtAuthenticationToken` whose `getName()` is the internal user ID. Never use `.block()`, manual `.subscribe()`, or fallback permission grants when a repository fails.

When only certain operations need profiles or resource permissions, keep **JWT authentication lightweight** and **perform reactive lookups in the service/authorization layer when business logic genuinely needs them**. `ReactiveSecurityContextHolder`, Reactor `Mono`/`Flux`, and reactive repositories propagate identity cleanly across WebFlux. In every option, never confuse `sub` across issuers, never infer admin roles from arbitrary token/local lookups, always enforce tenant/owner on the resource, and use **`StepVerifier`, `WebTestClient`, and signed-JWT integration tests** to verify both allowed and denied paths.
