# OAuth Scope and GrantedAuthority in Spring Security

In a **Spring Security OAuth 2.0/OIDC Resource Server**, a valid access token tells the API that **this credential can be trusted**. However, to decide whether a request is allowed to read orders, update products, or perform administrative operations, the API also needs to examine **the permissions granted to the token** and **the resource's access policy**.

Two concepts appear constantly here:

- **OAuth 2.0 scope:** a string representing the permission range that an Authorization Server can grant to an access token; its specific meaning is defined by the OAuth system.
- **Spring Security `GrantedAuthority`:** an object describing an authority that has been placed into `Authentication` in a Java application, so that Spring Security's authorization components can evaluate it.

They are **related, but not identical**. A scope can be converted into a `GrantedAuthority`; in addition to scopes, an `Authentication` can also contain authorities from roles, business permissions, or other authentication mechanisms. Conversely, having an authority in Spring Security does not by itself prove that the caller owns a specific data record.

This lesson explains the path from when a client requests a scope to when the Resource Server checks `hasAuthority("SCOPE_orders.read")`, the default and custom mapping approaches, how scopes differ from roles, and the security boundaries to maintain when using JWT or opaque access tokens.

## 1. Overall model: scope from OAuth, authority in Spring Security

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    C->>AS: Request access token with scope orders.read
    AS->>AS: Authenticate client/user and apply issuance policy
    AS-->>C: Access token with granted scopes
    C->>RS: GET /api/orders, Authorization: Bearer token
    RS->>RS: Verify token and extract granted scopes
    RS->>RS: Convert orders.read into SCOPE_orders.read
    RS->>RS: Check endpoint authority + data permissions
    RS-->>C: 200 / 401 / 403 depending on result
```

In the diagram:

1. **The client requests** access scopes; requesting does not force the Authorization Server to grant them.
2. **The Authorization Server decides** which scopes are actually granted after considering the client, user, grant type, consent, and policy.
3. **The access token carries or references** the granted permissions according to the contract; for JWTs they may be in the `scope`/`scp` claim, and for opaque tokens they may be returned by introspection.
4. **The Resource Server validates the token first**, then converts the verified permission information into authorities if needed.
5. **Spring Security checks authorities** for the URL or method.
6. **The application checks permissions against the data object**, such as the order owner, tenant, and state.

No step allows the frontend to simply add an `orders.write` string to an HTTP header to escalate privileges. If the scope needs to change, the client must obtain a credential **validly issued by the Authorization Server**.

### 1.1. Three non-interchangeable questions

| Question | Commonly used mechanism | Example |
|---|---|---|
| **Is the token trustworthy and intended for this API?** | JWT signature/issuer/audience/time or introspection | Trusted `iss`, `aud` contains `orders-api`, `exp` not expired |
| **What kind of operations was the token granted?** | OAuth scope → `GrantedAuthority`, endpoint policy | `orders.read` → `SCOPE_orders.read` |
| **Which records is the principal allowed to act on?** | Business authorization, ownership, tenant, ACL | `user-842` can only read their own orders |

A secure API must answer **all three** questions according to the contract, not just have a valid signature or a valid scope.

## 2. What is a scope in OAuth 2.0?

According to OAuth 2.0, a scope is a way of representing **the requested or granted access range** for an access token. Scope values are **case-sensitive strings** agreed upon between the Authorization Server and the Resource Server; OAuth itself does not dictate what `orders.read` must mean.

For example:

```text
orders.read
orders.write
inventory.read
payments.refund
```

A system might choose a naming convention like `orders:read` instead of `orders.read`. This is an API design decision. Spring Security does not automatically assume that a dot or colon implies hierarchy; authority matching is usually an **exact string comparison**.

### 2.1. Requested scope vs. actually granted scope

In an authorization request, a client can request multiple scopes:

```http
GET /authorize?response_type=code&client_id=shop-web&scope=openid%20profile%20orders.read&redirect_uri=https%3A%2F%2Fclient.example%2Fcallback&state=xyz HTTP/1.1
Host: idp.example.com
```

The example URL above only illustrates the `scope` parameter, **not a complete authorization request** for production deployment: real applications require PKCE, redirect URI, and state/nonce conditions according to the respective flow.

The Authorization Server can:

- Grant all requested scopes.
- Grant only a subset due to client/user permissions or consent.
- Reject the request because a scope is invalid or not permitted.
- Apply additional rules regarding audience, client type, grant type, and resource policy.

**The Resource Server must rely on the scopes actually granted and verified via the token/introspection**, not on the list of scopes the client originally requested.

For example:

```text
Client requests:         orders.read orders.write
AS grants in token:      orders.read
Resource Server receives: only the orders.read permission
```

The client does not get write permission simply because it sent `scope=orders.write` when requesting the token.

### 2.2. Scopes are a flat permission set, not an implicit expression

Given two scopes:

```text
orders.read
orders.write
```

OAuth 2.0 **does not automatically state** that `orders.write` implies `orders.read`. If an API wants a write scope to automatically include read access, that rule must be explicitly encoded in the authorization policy or the IdP's token issuance rules. A normal `hasAuthority("SCOPE_orders.read")` check will not automatically pass just because the token has `SCOPE_orders.write`.

Similarly:

```text
admin
orders.*
orders.read.all
```

do not have automatic wildcards or role hierarchy unless the application implements them. Do not treat a scope name that looks "stronger" as a substitute permission when the policy checks for an exact string.

### 2.3. A scope is not necessarily a user permission

An access token can be issued via:

- **Authorization Code + PKCE**: typically involves the permissions of a client acting on behalf of an authenticated end-user.
- **Client Credentials**: represents a client/service, with no interactively logged-in user.
- **Token Exchange / multi-hop delegation**: permissions may be narrowed down or bound to an actor/delegation according to a specific contract.

Therefore, `orders.read` does not indicate which user or service the token belongs to. To know the principal, you need to check the token type, `sub`, `client_id`, actor claim, and the issuer's policy for each grant. Do not use a scope as proof that "a user has logged in".

### 2.4. Scope is different from audience

**Audience** answers "which Resource Server is this token intended for?", while **scope** answers "what kind of work is this token allowed to do?".

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

The Orders API should only accept a token when the issuer/key/signature/time and audience are all valid. A token with `scope=orders.read` but `aud=["payments-api"]` **is not an access token with the right recipient for the Orders API**. Do not use scope to bypass audience checks.

## 3. What is Spring Security's GrantedAuthority?

`GrantedAuthority` belongs to Spring Security, not to a standard OAuth field. The interface has the method:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

The common implementation is `SimpleGrantedAuthority`:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority readOrders =
    new SimpleGrantedAuthority("SCOPE_orders.read");

System.out.println(readOrders.getAuthority());
// SCOPE_orders.read
```

An `Authentication` holds a collection of authorities:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    for (GrantedAuthority authority : authentication.getAuthorities()) {
        System.out.println(authority.getAuthority());
    }
}
```

This example is only meant to show the API; in real applications, you should not print all user/permission details to uncontrolled production logs. `SecurityContextHolder` normally provides the `Authentication` for the **current request/thread** after Spring Security has authenticated it.

### 3.1. Authority is the "input" to the authorization engine

When configuring:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read"))
```

Spring Security does not directly inspect the raw `scope` claim in this DSL snippet. It checks the `GrantedAuthority` collection of the `Authentication` built from the token. That is why the step of **converting scopes into authorities** is the decisive bridge.

`GrantedAuthority` can represent:

- Scopes granted in an OAuth access token.
- Roles mapped by the application or IdP.
- Internal permissions from a trusted permission source.
- Permissions granted by another authentication mechanism.

Not all authorities necessarily originate from OAuth scopes.

### 3.2. Why is there a SCOPE_ prefix?

By default, Spring Security JWT Resource Server typically converts a scope:

```text
OAuth scope:           orders.read
Spring authority:      SCOPE_orders.read
```

The `SCOPE_` prefix distinguishes **access token scopes** from other authorities such as roles (`ROLE_ADMIN`) or custom-defined permissions. It is a **Spring Security mapping convention**, not a mandatory part of the scope value that the Authorization Server must issue.

Therefore, the IdP usually issues:

```json
{
  "scope": "orders.read orders.write"
}
```

and **does not need** to issue:

```json
{
  "scope": "SCOPE_orders.read SCOPE_orders.write"
}
```

If the IdP already issues `SCOPE_orders.read`, the default converter may prepend the prefix again and produce `SCOPE_SCOPE_orders.read`. The contract between the IdP and the API must align on the raw scope values and the application's mapping.

## 4. From JWT scope/scp claims to GrantedAuthority

For a signed JWT Resource Server, the typical components are:

```mermaid
flowchart LR
    H["Authorization: Bearer JWT"] --> BF["BearerTokenAuthenticationFilter"]
    BF --> JP["JwtAuthenticationProvider"]
    JP --> DEC["JwtDecoder<br/>signature + claims validators"]
    DEC --> JAT["JwtAuthenticationConverter"]
    JAT --> GAC["JwtGrantedAuthoritiesConverter"]
    GAC --> A["JwtAuthenticationToken<br/>principal + authorities"]
    A --> SEC["SecurityContextHolder"]
    SEC --> AUTHZ["hasAuthority / method security"]
```

Note that `JwtAuthenticationProvider` uses the decoder to verify the JWT. Only after the token is validated does the converter turn the trusted claims into authorities. **Base64-decoding the payload and adding authorities before verifying the signature violates the trust boundary**.

### 4.1. JWT with space-separated scope string

Example payload:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "scope": "orders.read orders.write"
}
```

Upon successful authentication with default mapping, `Authentication` typically has:

```text
Principal name:
  user-842

GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
```

A token can carry multiple scopes in **a single space-separated string** according to OAuth rules. Scope names like `orders.read` are treated as whole values; the dot in the scope name does not act as a token separator.

### 4.2. JWT with scp array

Some IdPs use the `scp` claim:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

Spring Security's `JwtGrantedAuthoritiesConverter` supports reading common authority claims such as `scope` or `scp`, capable of accepting string or collection values along its supported processing path. The resulting mapping is usually still:

```text
SCOPE_orders.read
SCOPE_orders.write
```

When an IdP uses another custom claim, such as `permissions` or `authorities`, you need to customize the converter. Do not assume Spring Security understands every claim with a permission-like name.

### 4.3. What if a JWT has both scope and scp?

Some tokens may contain both:

```json
{
  "scope": "orders.read",
  "scp": ["orders.write"]
}
```

You should not expect the default converter to automatically **merge both**. In common versions, `JwtGrantedAuthoritiesConverter` picks one well-known claim according to its lookup order (`scope` before `scp`), or the claim explicitly configured by the application. To avoid confusion:

- Prefer **one unified scope format** in the issuer/API contract.
- If merging multiple sources is genuinely required, write a converter with explicit rules and trusted sources.
- Do not treat scopes in two different claims as additive by default, as this can grant unintended permissions.

### 4.4. When there is no scope

A token may have a valid signature/issuer/audience yet not carry the `orders.read` scope:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "service-42",
  "aud": ["orders-api"],
  "exp": 1893459600
}
```

For an endpoint requiring `SCOPE_orders.read`, an `Authentication` without that authority must be rejected by the policy. Never assume "a valid token grants all scopes". If a client credentials flow uses a custom role claim instead of scopes by contract, the policy must be explicitly designed for that principal type; do not simply remove endpoint protection.

## 5. JwtAuthenticationToken and SecurityContextHolder

When a JWT Resource Server authenticates successfully, Spring Security typically creates a `JwtAuthenticationToken`. This is an `Authentication` implementation; it holds a `Jwt` principal and the collection of authorities converted from scopes/claims.

Example inspection controller:

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentAccessController {

    @GetMapping("/api/me/access")
    public List<String> grantedAuthorities(
            Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(authority -> authority.getAuthority())
            .toList();
    }
}
```

This example is meant to illustrate how to read authorities; this route needs appropriate protection and should not expose sensitive permission details if there is no product requirement. If you only need the JWT subject, you can use `@AuthenticationPrincipal Jwt`; if you only need permissions, `Authentication` is more suitable because it does not depend directly on the token format.

### 5.1. Scopes are checked from the current request's Authentication

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

boolean mayRead = auth != null &&
    auth.getAuthorities().stream()
        .anyMatch(a -> "SCOPE_orders.read".equals(a.getAuthority()));
```

The snippet above demonstrates the existence of the authority. In typical applications, **prefer the authorization DSL or method security** rather than manually repeating collection iteration in every controller.

With a stateless bearer API, each request carries its own token and Spring Security builds an `Authentication` scoped to that request. Never store the authorities of the "most recent caller" in a singleton/static field and reuse them for the next request.

## 6. Distinguishing scope, authority, role, and business permission

Concepts that are easily lumped together as "permissions":

| Concept | Which layer does it belong to? | Example | Limitation |
|---|---|---|---|
| **OAuth scope** | Authorization Server ↔ Resource Server contract | `orders.read` | Does not describe ownership/tenant on its own |
| **GrantedAuthority** | Spring Security `Authentication` | `SCOPE_orders.read` | Just permission data interpreted by authorization rules |
| **Role** | Organizational/application policy, can be expressed as an authority | `ROLE_ADMIN` | Specific meaning is determined by the application |
| **Permission** | Business operation or data rule | "user can edit ORD-123" | May require DB queries and context |
| **Audience** | Token contract | `orders-api` | Not an operational permission |
| **Principal/subject** | Identity | `user-842` or `service-42` | Does not imply permissions on its own |

### 6.1. How do hasAuthority and hasRole differ?

In standard configuration:

```java
.hasAuthority("SCOPE_orders.read")
```

checks for an authority string **exactly equal to** `SCOPE_orders.read`.

Meanwhile:

```java
.hasRole("ADMIN")
```

typically checks for the authority **`ROLE_ADMIN`** because Spring Security uses the `ROLE_` prefix convention for role expressions. The default role prefix can be customized in an application; `hasRole` is not the default way to check OAuth scopes.

Equivalent checks under the default role prefix configuration:

```java
.hasRole("ADMIN")
.hasAuthority("ROLE_ADMIN")
```

However:

```java
.hasRole("orders.read")          // typically looks for ROLE_orders.read
.hasAuthority("SCOPE_orders.read") // looks for the actual scope authority
```

The last two lines **are not equivalent**. To protect an API using default OAuth scopes, explicitly using `hasAuthority("SCOPE_...")` helps avoid misunderstandings.

### 6.2. A role can contain multiple permissions, but has no automatic hierarchy

For example, a product defines the `ORDER_MANAGER` role as able to read/write orders:

```text
ROLE_ORDER_MANAGER
    -> orders.read
    -> orders.write
```

This is a **custom policy**, not an OAuth standard or a default `GrantedAuthority` behavior. To map roles to permissions, the application must have rules, a trusted data source, and corresponding checks.

In an API with both scopes and roles, you can check them in combination:

```java
.access(/* AuthorizationManager representing the combined policy */)
```

or use method security with appropriate conditional expressions. Do not treat a role name in a JWT like `admin` as sufficient to bypass audience, issuer, or resource-level permission checks.

### 6.3. Per-record permission is always a separate decision

Token:

```json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Database:

```text
Order ORD-123:
  owner = user-842
  tenant = tenant-a

Order ORD-999:
  owner = user-901
  tenant = tenant-b
```

The `SCOPE_orders.read` authority lets the request pass the **read orders** operation-type check, but the service must still reject ORD-999 if the user/tenant does not have access. Without object-level checks, the API risks **Broken Object Level Authorization (BOLA)**.

## 7. Spring Boot/Spring Security Servlet configuration: using default scopes

Example of a REST API accepting JWT bearer tokens, allowing order reads/writes only by scope. With Spring Boot 3.x, common dependencies are:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

`issuer-uri` declares the trusted issuer, while `audiences` (in Boot versions that support it) enforces that `aud` is intended for the API. The JWT decoder must verify the signature and validate claims; authority mapping **does not replace** those validators.

Example HTTP configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Example for Bearer-header APIs only; does not use
            // cookies/sessions as credentials for write operations.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Explanation:

1. Spring Security extracts the bearer token from the request header according to the resolver rules.
2. `JwtDecoder` verifies the token against the issuer/keys and validators.
3. The default `JwtAuthenticationConverter` reads the appropriate `scope`/`scp` claim.
4. `GrantedAuthority` `SCOPE_orders.read`/`SCOPE_orders.write` is evaluated in the `hasAuthority` rules.
5. `anyRequest().denyAll()` chooses to **deny routes that are not explicitly configured**, rather than accidentally exposing permissions. In large applications with multiple chains, matchers must be calculated thoroughly.
6. Per-order permissions are still checked in the service layer.

The `csrf().disable()` pattern only applies to APIs authenticated via bearer headers that do not rely on cookies. If the application also has form login/cookies/sessions, CSRF protection must be evaluated according to the actual authentication channels.

### 7.1. hasAnyAuthority for multiple alternative scopes

An endpoint allows reading if the token has **at least one** of two scopes:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.read", "SCOPE_reports.admin")
```

This is an **OR** relationship between the two authorities. If the contract requires **both** scopes, do not use `hasAnyAuthority`. You need an expression/`AuthorizationManager` representing AND logic.

Do not invent wildcard scopes assuming `SCOPE_orders.*` will match all child scopes; `hasAuthority` does not interpret wildcards unless a custom policy is implemented.

### 7.2. Using method security

With `@EnableMethodSecurity`:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String orderId) {
        return loadAndCheckBusinessAccess(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public OrderDto updateOrder(String orderId, UpdateOrderCommand command) {
        return updateAfterBusinessChecks(orderId, command);
    }
}
```

The `loadAndCheckBusinessAccess`, `updateAfterBusinessChecks` methods and the DTO/command types are illustrative application-defined components. Having `@PreAuthorize` check scopes at the method level does not eliminate the need for owner/tenant checks inside the service itself.

**Proxy note:** method security relies on Spring AOP/proxies in standard configurations. Calling an annotated method from another method **within the same bean** can bypass the proxy, causing the annotation not to be enforced as expected. Establish clear service/authorization boundaries and do not rely on self-invocation.

## 8. Opaque access tokens: scopes can also become GrantedAuthority

Not all OAuth access tokens are JWTs. An API can use **introspection**: the Resource Server sends the token to the Authorization Server to find out whether the token is still `active` and retrieve the granted permission metadata.

Illustrative introspection response:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "exp": 1893459600
}
```

In Servlet Resource Server opaque-token support, Spring Security can use `OpaqueTokenIntrospector` to fetch metadata and construct a `BearerTokenAuthentication`. Returned scopes are typically mapped to `GrantedAuthority` with the `SCOPE_` prefix, just like JWTs.

Configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

A token validated via introspection can still have authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Therefore, the same rule:

```java
.hasAuthority("SCOPE_orders.read")
```

can be used for either JWT or opaque tokens **if the authority mapping contract between the two modes is equivalent**.

### 8.1. Do not assume an opaque token has a Jwt principal

With JWT, the principal is typically `Jwt`. With an opaque token, the principal is typically `OAuth2AuthenticatedPrincipal`. A controller/service that only needs the name and authorities should accept `Authentication`; code that casts to `Jwt` where opaque authentication is used will fail.

```java
@GetMapping("/api/me/authorities")
public List<String> currentAuthorities(Authentication authentication) {
    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .toList();
}
```

This example requires importing `Authentication`, `GrantedAuthority`, `List`, and the corresponding Spring MVC annotations. It does not depend on the token's principal type.

### 8.2. Introspection returning active=true does not mean permissions are sufficient

`active: true` indicates that the credential is still active according to the IdP response; it does not allow the API to skip audience, scope, tenant, or custom policies. If the introspection endpoint does not return the information needed to check the audience, the contract with the Authorization Server must be adjusted—do not treat an active token as usable across every Resource Server.

## 9. Customizing how scopes map to GrantedAuthority

When the IdP uses a different claim or naming convention, Spring Security provides `JwtGrantedAuthoritiesConverter`. Common options include:

- `setAuthoritiesClaimName(...)`: specifies the claim from which to read authority strings/scopes.
- `setAuthorityPrefix(...)`: changes the prefix, e.g., `SCOPE_` or empty string.
- `setAuthoritiesClaimDelimiter(...)`: defines how string values are split in supported versions.

Customization may be necessary, but **it must respect the validated-token boundary** and must not grant permissions beyond the contract.

### 9.1. Customizing the scp claim and keeping the SCOPE_ prefix

Suppose the IdP always issues:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

You can configure the converter explicitly:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class TokenAuthorityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        scopes.setAuthoritiesClaimName("scp");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
```

With a custom converter, you need to wire it into the JWT Resource Server DSL:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
```

The snippet above illustrates **wiring the converter into the filter chain**. JWT issuer/audience/signature requirements must still be configured on the decoder. Simply defining a `@Bean JwtAuthenticationConverter` without plugging it into the authentication pipeline may result in the custom mapping not being applied as expected.

### 9.2. Changing the prefix: impact on hasAuthority

Suppose:

```java
scopes.setAuthorityPrefix("");
```

The generated authority is `orders.read`, not `SCOPE_orders.read`. The policy must then use:

```java
.hasAuthority("orders.read")
```

If you keep `hasAuthority("SCOPE_orders.read")`, requests carrying a token with `orders.read` will receive 403 because the authorities do not match. You must keep **both the converter and the authorization rules** aligned when changing the prefix.

Usually it is best to keep `SCOPE_` to distinguish scopes from roles and authorities from other sources. Only change the prefix if there is a clear compatibility contract and corresponding route/method tests.

### 9.3. Changing the principal name does not change authorities

`JwtAuthenticationConverter` can set the principal claim:

```java
converter.setPrincipalClaimName("preferred_username");
```

This affects `Authentication.getName()`, **and does not automatically alter the authorities collection**. If you want to map `scope`/`scp`, you must configure `JwtGrantedAuthoritiesConverter`. If you want permissions from another claim, you need an appropriate converter; do not confuse identity claims such as `email` or `preferred_username` with action permissions.

In multi-issuer systems, `preferred_username` is not a globally stable identifier. To identify the subject and ownership, you typically must use `iss + sub` or an internal principal mapping.

## 10. Combining scopes and another group of authorities

Some IdPs issue both:

```json
{
  "scope": "orders.read",
  "app_roles": ["ORDER_MANAGER"]
}
```

By default, `JwtGrantedAuthoritiesConverter` only handles well-known scope claims and **does not automatically turn every element in `app_roles` into `ROLE_...`**. If the application is permitted to trust the `app_roles` claim from this issuer, a combined converter can be added.

### 10.1. Converter pattern that preserves scopes before adding roles

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ScopeAndRoleAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<GrantedAuthority> result = new ArrayList<>();

        // Keep default scope authorities: SCOPE_...
        result.addAll(scopes.convert(jwt));

        // Only use this claim if the issuer and token contract
        // allow the Resource Server to trust app_roles as a role source.
        List<String> roles = jwt.getClaimAsStringList("app_roles");
        if (roles != null) {
            for (String role : roles) {
                if (role.equals("ORDER_MANAGER")) {
                    result.add(
                        new SimpleGrantedAuthority("ROLE_ORDER_MANAGER"));
                }
            }
        }
        return result;
    }
}
```

Then attach it to `JwtAuthenticationConverter`:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
    new ScopeAndRoleAuthoritiesConverter());
```

Key takeaways from the example:

1. **Preserve default scopes** instead of replacing all authorities with roles alone.
2. Only map **specific roles accepted by the contract**.
3. Do not take every string in the `app_roles` claim and unconditionally prepend `ROLE_`, especially when the IdP is shared across multiple clients or the claim is not guaranteed by the issuer.
4. Do not use roles to skip `aud`, `iss`, JWT expiration, or ownership/tenant checks.

If the application supports multiple issuers, the origin and meaning of `app_roles` may differ. Do not trust a role solely based on a claim name in a JWT from another issuer, even if that issuer is accepted for a specific set of endpoints.

### 10.2. When should roles not be placed in a JWT?

Some permissions change frequently or depend on current data—for example, an employee changes teams, an order changes owners, or a project is locked. A self-contained JWT can hold stale claims until it expires. If decisions must reflect changes immediately, you should:

- Check current permissions in a database or policy service.
- Use introspection or revocation status per the contract.
- Keep the access token TTL appropriately short.
- Only store relatively stable, clearly scoped permissions in the token.

Do not treat role claims inside a JWT as a permanent replica of the business authorization system.

## 11. Multi-layer authorization rules

An Orders API system may have:

```text
Layer 1 — Token validation:
  iss, signature, aud, exp, nbf

Layer 2 — Endpoint authorization:
  GET /api/orders/{id} requires SCOPE_orders.read

Layer 3 — Domain authorization:
  Is the actor allowed to view this specific order id?
  Does the tenant match?
  Is the order in a restricted state?
```

Example of an actor constructed from a verified JWT:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

Controller:

```java
@GetMapping("/api/orders/{orderId}")
public OrderDto getOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    return orderService.findReadableOrder(actor, orderId);
}
```

Service:

```java
public OrderDto findReadableOrder(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    boolean sameTenant =
        order.getTenantId().equals(actor.tenantId());

    if (!isOwner || !sameTenant) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

The `Order`, `OrderDto`, `OrderNotFoundException`, `repository`, `mapper`, and `orderService` types are application-specific domain components. The example assumes a policy where a user can only read orders they own within the corresponding tenant; for admins, delegated access, or other cases, explicit additional policies are needed.

**Note:** In the controller, `@AuthenticationPrincipal Jwt` is only suitable for JWT routes; for opaque tokens, obtain `Authentication`/`OAuth2AuthenticatedPrincipal` and map it to an equivalent actor.

### 11.1. Should both authority and ownership be required?

Yes. They address two different levels:

```text
SCOPE_orders.read
    -> Allowed to use the order-reading capability within the API scope

owner/tenant policy
    -> Allowed to read which specific orders within that scope
```

If you only check ownership and omit scope, a client that was never granted order-reading permission could still use a token with an unrelated scope. If you only check scope and omit ownership, a user could read data that does not belong to them.

## 12. OIDC scopes are not synonymous with API permission scopes

An OIDC authorization request can ask for:

```text
openid profile email
```

These scopes serve **OpenID Connect** semantics, such as requesting OpenID authentication and accessing user claims under the OIDC protocol. You should not infer:

```text
openid => allowed to call every protected API
profile => allowed to view every user's profile
email => allowed to read every customer's email
```

A Resource Server serving the Orders API should require a dedicated scope such as `orders.read` per the API contract. Tokens carrying `openid profile email` without `orders.read` must not automatically pass endpoints that require reading orders.

**An ID token is not an access token.** An OIDC ID token has the OIDC client as its audience and is meant for the client to understand the authentication result; it does not become a valid access token for the Orders API merely because it has a valid signature and identity claims.

### 12.1. Resource indicators and audience still matter

When there are multiple APIs, OAuth can use resource indicators (per contract/IdP) to request tokens targeted at each resource. For example:

```text
Client requests orders.read for orders-api
  -> access token aud=orders-api, scope=orders.read

Client requests payments.refund for payments-api
  -> access token aud=payments-api, scope=payments.refund
```

If the Orders API calls the Payments API downstream, having `SCOPE_orders.read` in the Orders API's `SecurityContext` **does not automatically grant access to the Payments API**. The target API must validate a separate credential with the appropriate audience and scopes; token exchange/on-behalf-of or client credentials may be used depending on the architecture.

## 13. HTTP 401, 403, and insufficient_scope

There are two error categories learners often confuse:

### 13.1. Missing or invalid token: 401

Example request missing a token:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
```

Or sending an expired token, invalid signature, wrong issuer, or wrong audience. For protected endpoints, the Resource Server typically returns **401 Unauthorized** with `WWW-Authenticate: Bearer` per the appropriate mechanism.

Here, the system **does not yet have a valid access-token authentication**. Do not resolve this by adding a dummy authority in the controller.

### 13.2. Valid token but missing scope: 403

Suppose the token is valid:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "scope": "orders.read"
}
```

Request:

```http
POST /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer VALID_TOKEN_WITH_ORDERS_READ_ONLY
```

The policy requires `SCOPE_orders.write`, while `Authentication` only has `SCOPE_orders.read`. The Resource Server has authenticated the token, and then authorization rejects it → typically **403 Forbidden**.

Per RFC 6750, when a required scope is missing, the Bearer challenge may carry `error="insufficient_scope"` and the required scope details depending on how the framework/API is configured. Do not assume every 403 response has the exact same header or body; the exact content depends on the entry point, access denied handler, and configuration.

### 13.3. Valid token with sufficient scope but rejected by business policy

```text
Authentication:
  sub=user-842
  authority=SCOPE_orders.read

Request:
  GET /api/orders/ord-999

Database:
  ord-999.owner=user-901
```

The HTTP authority layer may let the request through, but the service must reject it under the owner/tenant policy. The application may return 403 or 404 depending on its policy for avoiding record-existence disclosure. This **is not a missing OAuth scope error** if `orders.read` was granted.

### 13.4. Standardizing safe error messages

Avoid returning:

```text
Token eyJ... of user-842 does not have ROLE_ADMIN and
resource ORD-999 belongs to user-901...
```

Responses do not need to leak the token or the identity of the record owner. Filtered metadata can be logged according to observability policies, but never log raw bearer credentials.

## 14. Common scope-related pitfalls

| Situation | Why it happens | How to handle it |
|---|---|---|
| Token has `orders.read` but endpoint requires `SCOPE_orders.read` | Matches default mapping; if still getting 403, inspect token/chain/converter | Safely inspect authorities after authentication |
| IdP sends `scp` while converter is forced to read `scope` | Expected claim is not found | Align the claim or configure `setAuthoritiesClaimName("scp")` |
| Token has both `scope` and `scp` but only one set is read | Default converter does not necessarily merge both | Contract on one source; if merging, write explicit rules |
| IdP sends scopes already prefixed with `SCOPE_` | Converter may add the prefix a second time | Issue raw scopes or adjust mapping to match contract |
| Using `hasRole("orders.read")` | Looks for `ROLE_orders.read` instead of scope authority | Use `hasAuthority("SCOPE_orders.read")` |
| Using `hasAuthority("orders.read")` with default converter | Does not match `SCOPE_orders.read` | Use the proper prefix or keep converter and policy in sync |
| Using a role claim without configuring a converter | Roles do not automatically become `ROLE_...` | Add explicit mapping from a trusted source |
| Token has `orders.write`, endpoint requires `orders.read` | No implicit scope inheritance by default | Grant both scopes or define the corresponding policy |
| Token has the right scope but `aud` targets another API | Token is not intended for the current Resource Server | Validate audience; do not bypass |
| Token has the right scope but is expired | Authentication must reject before authorization | Validate `exp`/`nbf` and signature |
| Client requested `orders.write` but token only granted `orders.read` | AS restricted the scope | Rely on the granted token, not the requested scope |
| A user's role changes while an old JWT still holds permission claims | Self-contained token remains valid until expiry | Enforce short TTL/revocation/introspection/live business checks |
| JWT role ADMIN bypasses all tenants | Mixing functional roles with object-level permissions | Check tenant/owner or define explicit admin rules |
| Using mock JWT tests to conclude the decoder validates properly | Mocks may bypass decoding/validators | Separate authorization tests from real JWT integration tests |

## 15. Testing scope mapping and authorization at the right layer

Tests should separate three objectives:

1. **Token validation:** Does the JWT properly verify signature/issuer/audience/time?
2. **Authority mapping:** What authorities are claims converted into?
3. **Authorization policy:** Do the authorities and actor have sufficient permissions for the endpoint/record?

### 15.1. Unit testing JwtGrantedAuthoritiesConverter

Example using JUnit 5 and AssertJ with a synthetic token (no real signature):

```java
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtScopeMappingTest {

    @Test
    void convertsSpaceSeparatedScopeToAuthorities() {
        Instant now = Instant.now();
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("user-842")
            .issuedAt(now.minusSeconds(60))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders.read orders.write")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        assertThat(converter.convert(jwt))
            .extracting(authority -> authority.getAuthority())
            .containsExactlyInAnyOrder(
                "SCOPE_orders.read",
                "SCOPE_orders.write");
    }
}
```

This test verifies **mapping from a `Jwt` object to authorities**; it does not test real JWT signatures, the bearer filter, or the audience validator. It is useful for catching prefix/claim name mismatches when changing the converter.

### 15.2. Unit test for the scp converter

```java
@Test
void readsScpArrayWhenConfigured() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scp", List.of("orders.read", "orders.write"))
        .build();

    JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();
    converter.setAuthoritiesClaimName("scp");

    assertThat(converter.convert(jwt))
        .extracting(GrantedAuthority::getAuthority)
        .contains("SCOPE_orders.read", "SCOPE_orders.write");
}
```

This snippet is an additional test method inside a test class that has JUnit/AssertJ, `Jwt`, `List`, and `GrantedAuthority` imports. When using a different version's `Jwt` builder, you may need to supply required claims/timestamps per that version's API.

### 15.3. Testing HTTP authorization

Spring Security Test supports `MockMvc` and the `jwt()` request post-processor to mock a JWT principal/authorities:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void readOrderRequiresScope() throws Exception {
    mockMvc.perform(get("/api/orders/ord-123")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}
```

`mockMvc`, the controller, the service, and test data must be wired according to the real application; the example assumes the route returns 200 when business conditions are also satisfied. Using `jwt().authorities(...)` **assigns mocked authorities**, so it does not prove that the JWT decoder verified signatures or that the default converter read the `scope` claim properly.

To test the decoder and real authentication pipeline, you need to send requests carrying a bearer JWT signed with a trusted test key, configure a test decoder/JWKS, and send tokens with valid/invalid issuer, audience, expiration, and scopes through the filter chain.

### 15.4. Important negative test cases

| Token/Request | What to verify |
|---|---|
| JWT with invalid signature but valid scope | Authentication is rejected |
| JWT with valid signature but wrong issuer | Authentication is rejected |
| JWT with valid issuer but wrong audience | Authentication is rejected |
| Expired JWT with `orders.write` | Authentication is rejected |
| Valid JWT with only `orders.read`, POST request requiring write | Authorization is rejected |
| Valid JWT with `orders.write`, valid POST request | Proceeds to business policy |
| Valid JWT with scope, but order belongs to another owner/tenant | Business policy rejects |
| JWT with `scp` array, converter configured with wrong claim | Expected scope authority is absent |
| JWT using custom prefix while route still checks `SCOPE_` | Policy does not match authority |
| Active opaque token without required scope | Authorization rejects |

Do not test only the happy path with full scopes; negative test cases help catch dropped scope mappings or mixed-up authentication/authorization checks.

## 16. Scopes in multi-API architectures and least-privilege principles

Suppose a system has Orders API, Payments API, and Reporting API:

```text
Orders API:
  audience = orders-api
  scopes   = orders.read, orders.write

Payments API:
  audience = payments-api
  scopes   = payments.read, payments.refund

Reporting API:
  audience = reporting-api
  scopes   = reports.read
```

You should request and grant **the minimum scope needed for the task being performed**. A client that only needs to read orders should not request `orders.write` or `payments.refund`. A backend service using client credentials should only be granted the scopes and audiences needed for that function.

### 16.1. Do not forward tokens with the wrong audience

```mermaid
flowchart LR
    C["Client"] -->|"Token aud=orders-api<br/>scope=orders.read"| O["Orders API"]
    O -->|"Needs to call Payments API"| T["Token exchange<br/>or client credentials"]
    T -->|"Token aud=payments-api<br/>appropriate scope"| P["Payments API"]
```

The Orders API has no authority to turn an `aud=orders-api` token into an `aud=payments-api` token simply by altering JSON. If the Payments API checks the audience properly, the Orders API's token will be rejected. Service-to-service contracts may require token exchange/on-behalf-of or client credentials.

### 16.2. Scope is not idempotency or replay protection

A token with `payments.refund` does not by itself prevent a refund request from being submitted multiple times. Appropriate idempotency mechanisms and transaction state checks are required. A JWT with `jti` also does not guarantee "can only be called for a single request", because bearer access tokens are typically reused multiple times within their validity window.

### 16.3. Scopes do not update automatically when permissions change

With self-contained JWTs, scopes reside inside the signed token and can be used by the Resource Server until the token expires or is rejected by another stateful mechanism. Updating a user's permissions in the IdP does not automatically mutate already-issued JWTs. If changes must take effect sooner:

- Use short-lived access tokens.
- Enforce live business policies per resource.
- Use token introspection or revocation/denylist if required by the contract.
- Manage the impact of changing client grants or role mappings.

Do not treat scopes inside a token as permanent permissions of the principal.

## 17. Design questions for the scope ↔ authority contract

Before writing `hasAuthority` rules, the API and IdP teams should agree on:

| Question | Example decision |
|---|---|
| Which strings are the scopes? | `orders.read`, `orders.write` |
| Is the naming convention case-sensitive? | Yes; exact match |
| Which clients may request which scopes? | `shop-web` requests read/write per policy; batch only read |
| Which API is the token intended for? | `aud` must contain `orders-api` |
| Which claim does the JWT use? | Space-separated `scope` string |
| Where does opaque introspection return permissions? | `scope` in response per RFC 7662/contract |
| How does Spring Security map them? | `orders.read` → `SCOPE_orders.read` |
| Are there separate roles? | `ROLE_ORDER_MANAGER` from a controlled role source |
| Which rules enforce a scope? | GET requires read; POST/PUT/DELETE require write |
| Are there relationships between scopes? | No implicit inheritance; if needed, must be defined |
| Who checks owner/tenant? | Service/domain policy |
| When do permission changes take effect? | JWT TTL, introspection, or live business permissions |
| Who verifies issuer, signature, and expiration? | Resource Server JWT decoder / introspector |

The key is **a single unified source of truth for semantics**: the Authorization Server knows which scopes were granted, the Resource Server knows which operations each scope allows, and Spring Security is configured to match the mapped authority names.

### 17.1. Signs of a misplaced policy boundary

If any of the following statements appear in a design, review it carefully:

- "The bearer token is authenticated, so the endpoint doesn't need `hasAuthority`."
- "Having `openid` or `profile` allows calling any API."
- "Role names in a token are always automatically converted by Spring Security into `ROLE_...`."
- "The frontend sending `X-Scope: orders.write` is enough for the backend to allow writes."
- "`orders.write` automatically includes `orders.read` because the scope name looks stronger."
- "Once scope is checked, checking owner/tenant is no longer necessary."
- "A token with `scope=orders.read` works for any API sharing the same IdP."
- "An issued JWT will automatically update its scopes when roles in the database change."

All of these can cause authorization flaws or unintended privilege escalation.

## 18. Summary to remember

```text
OAuth 2.0
  Client requests scope
         |
         v
  Authorization Server evaluates and grants scope
         |
         v
  Access token contains/references granted scope
         |
         v
Spring Security Resource Server
  Verify JWT or introspect token
         |
         v
  Converter turns scope -> GrantedAuthority
  orders.read -> SCOPE_orders.read
         |
         v
  HTTP/method authorization
  hasAuthority("SCOPE_orders.read")
         |
         v
  Business authorization
  owner / tenant / state / ACL of the record
```

**Scope is OAuth terminology and permission data; `GrantedAuthority` is how Spring Security represents permissions inside `Authentication`.** Default mapping for JWT/opaque Resource Servers usually uses the `SCOPE_` prefix so rules like `hasAuthority("SCOPE_orders.read")` check operation-type permissions.

Two final reminders:

1. **Scope does not replace access token verification**: you still must check issuer, audience, signature/expiration, or introspection.
2. **Authority does not replace business permissions**: you still must check whether the caller has access to the specific requested resource.

When both boundaries are preserved and the claim → authority → policy mapping is consistent, the Resource Server can use scopes clearly, testably, and with minimal over-privileged access.

## References

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 3.3 Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): meaning, representation, and issuance of OAuth scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials, 401/403, and `insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, and token metadata.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): specifying resource/audience when requesting tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access tokens and the `scope` claim.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC scopes and distinguishing ID tokens from access tokens.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, `scope` → `SCOPE_`, and authentication converter.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and mapping scope authorities.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `hasRole`, and HTTP policies.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and method-level authorization.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): customizing claims and authority prefixes.
