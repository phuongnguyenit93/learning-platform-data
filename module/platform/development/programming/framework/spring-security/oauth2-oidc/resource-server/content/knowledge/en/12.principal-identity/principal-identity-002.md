# Authentication.getName and Choosing a Claim as the Principal Name

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, after an access token is verified, the application often wants to know “who is calling the API?”. A familiar way is calling `Authentication.getName()`:

~~~java
String caller = SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

The value of `caller` is **the principal name as defined by the current `Authentication` object**. It is not automatically an email, username, numeric user ID in the database, or `client_id`. Specifically, with Spring Security's JWT Resource Server, `JwtAuthenticationToken.getName()` by default usually reads from the **`sub` (subject)** claim in the JWT, and you can change which claim is used as the name via `JwtAuthenticationConverter#setPrincipalClaimName(...)`.

Choosing this claim may look like merely swapping a display string, yet it affects logs/auditing, testing, authorization expressions, internal user mapping, and multi-issuer support. Selecting a **mutable or non-unique** claim can introduce subject-identification bugs, or even authorization flaws if the application uses `getName()` as a data access key.

> **Principle:** `Authentication.getName()` is **the principal's name representation in Spring Security**, whereas trusted identity must rely on a **verified token** and a stable identifier convention. For user-bearing access tokens, `(iss, sub)` is usually the appropriate key pair for mapping; resource access permissions must still be checked separately, not based on a display string.

## 1. Placing `getName()` in the Resource Server Flow

Example system:

- **Shop Web**: OAuth2 Client requesting access tokens for users.
- **Identity Server**: Authorization Server, issuer `https://identity.example.test/realms/shop`.
- **Orders API**: Spring Security Resource Server accepting JWT access tokens whose `aud` contains `orders-api`.

Shop Web sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

A JWT access token after decoding its payload may contain these claims:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read",
  "preferred_username": "linh.nguyen",
  "name": "Nguyen Linh",
  "email": "linh@example.test",
  "exp": 1893459600
}
~~~

These values are illustrative only. Not every JWT access token includes `preferred_username`, `name`, or `email`; those claims depend on the issuer and token contract. Spring Security should only use them after the token has passed signature, issuer, audience, and expiration verification.

With the **default** JWT Resource Server configuration:

~~~text
authentication.getName()      -> "user-9f1a"
jwt.getSubject()              -> "user-9f1a"
jwt.getClaimAsString("name")  -> "Nguyen Linh"
jwt.getClaimAsString("email") -> "linh@example.test"
~~~

If the principal claim is explicitly configured as `preferred_username`:

~~~text
authentication.getName()                     -> "linh.nguyen"
jwt.getSubject()                             -> "user-9f1a"
jwt.getClaimAsString("preferred_username")   -> "linh.nguyen"
~~~

**Changing the principal name does not alter the `sub` claim in the JWT.** Nor does it alter `issuer`, `audience`, scopes, or permissions on the order.

### Processing Flow Overview

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"]
    B["JwtDecoder verifies signature and token claims"]
    C{"Token accepted?"}
    D["Reject authentication"]
    E["JwtAuthenticationConverter"]
    F["JwtAuthenticationToken"]
    G["authentication.getName()"]
    H["authentication.getAuthorities()"]
    I["Check scopes and resource permissions"]

    A --> B --> C
    C -->|No| D
    C -->|Yes| E
    E --> F
    F --> G
    F --> H
    H --> I
~~~

`getName()` is used after authentication creation; it is **not a JWT verification step**. Changing the principal claim must never cause the API to skip signature, issuer, audience, expiration, or permission checks.

## 2. `Authentication`, Principal, and Name Are Three Related Yet Distinct Concepts

Spring Security defines the `Authentication` interface to represent either an authentication result or an authentication request. Important methods:

| Method | Meaning | Example in JWT Resource Server |
| --- | --- | --- |
| `getPrincipal()` | Object representing the authenticated subject | Typically the `Jwt` object inside `JwtAuthenticationToken` |
| `getName()` | Principal name string defined by the authentication type | Defaults to `sub`; another claim can be chosen |
| `getAuthorities()` | Set of `GrantedAuthority` objects for authorization decisions | For example `SCOPE_orders.read` |
| `getCredentials()` | Authentication credential info, depending on implementation | Should not be assumed to be a password or name string |
| `isAuthenticated()` | Authentication state of the `Authentication` object | Does not replace authorization checks |
| `getDetails()` | Additional data depending on authentication mechanism | May be web authentication details |

### 2.1. `Principal.getName()` Is a Naming Contract, Not a Universal Business Identifier

In Java, `java.security.Principal` represents a principal and exposes `getName()`. Spring Security's `Authentication` interface extends `Principal`, so it also has this method. However, **how the name string is derived depends on the implementation**.

For example:

- With **JWT Resource Server**, `JwtAuthenticationToken` typically uses `sub` or a configured claim.
- With **OIDC login**, the authentication object may hold `OidcUser`; `getName()` is affected by the Client/`OidcUser` user name attribute configuration.
- With **username/password authentication**, `getName()` may reflect the username from `UserDetails`.
- With **opaque access tokens**, Spring Security uses another authentication type; the name depends on the principal/introspection attributes supplied by the library or application.

Therefore, a shared helper method like:

~~~java
String getCurrentUserId(Authentication authentication) {
    return authentication.getName();
}
~~~

is only valid if the system **guarantees that name is a stable user ID** across every authentication mechanism in use. If the application supports JWTs, OAuth2 login, API keys, or service-to-service calls, that assumption usually needs tighter checks and constraints.

### 2.2. The Principal Object Is Not Necessarily a String

In a JWT Resource Server, you may encounter:

~~~java
Authentication authentication = ...;

Object principal = authentication.getPrincipal();
String principalName = authentication.getName();
~~~

`principal` may be a **`Jwt`**, while `principalName` is a **`String`**. Do not cast `(String) authentication.getPrincipal()` just because `getName()` returns a String.

If code needs claims, use the verified JWT object rather than re-parsing the Bearer token from the request header.

## 3. Why Is the `sub` Claim the Default?

**`sub` (subject)** is a registered JWT claim name. It identifies the principal that is the subject of the token within the semantics defined by the issuer and token profile.

In a user-bearing JWT access token:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Spring Security's JWT Resource Server typically creates `JwtAuthenticationToken` with:

~~~text
name = jwt.getSubject()
~~~

This fits the need to tie the principal name to the subject verified by the issuer. However, there are two important limitations:

1. **`sub` is not necessarily a human-readable username.** It may be an internal string, UUID, or pairwise identifier.
2. **`sub` does not necessarily represent an end user.** In the `client_credentials` grant, the token may represent a Client/service; the semantics of `sub` depend on the issuer and token profile.

### 3.1. `sub` Can Differ or Collide Across Issuers

Issuer A issues:

~~~json
{"iss":"https://id-a.example.test","sub":"123"}
~~~

Issuer B also issues:

~~~json
{"iss":"https://id-b.example.test","sub":"123"}
~~~

You must not infer that these two tokens belong to **the same user**. An identifier should ordinarily include the **issuing source**:

~~~text
Identity key = (issuer, subject)
             = (iss, sub)
~~~

When using OIDC, `sub` may be a **pairwise subject** per Client/sector; the same human user can have different `sub` values across different applications. An API must not assume `sub` is a global identifier without a matching identity contract.

### 3.2. `sub` Does Not Prove Permissions by Itself

A token with `sub = user-9f1a` does not automatically grant permission to view all orders of `user-9f1a`, let alone someone else's orders. The Resource Server still has to check `aud`, scope/authorities, tenant, owner, and specific policies. `getName()` is post-authentication naming data, not an authorization conclusion.

## 4. Claims That Can Be Chosen as the Principal Name

Choosing a principal name depends on its **intended use** and **claim stability**.

| Claim | Suitable For | Risks When Used as `getName()` |
| --- | --- | --- |
| **`sub`** | Identifying the subject per issuer; sensible default choice | Needs to be paired with issuer when correlating data across issuers; sometimes not human-readable |
| **`preferred_username`** | Displaying a username issued by the identity system | Can be renamed, collide across tenants/issuers, or be absent |
| **`email`** | Display/contact when the contract allows | Can change, be unverified, or be recycled; carries personal data |
| **`name`** | UI display name | Easily collides, changes, and should not be used as an identity key |
| **`user_id`** (custom) | Internal key if the issuer guarantees stability/uniqueness | Not a standard JWT claim; must verify definition, scope, and issuer |
| **`client_id`** | Identifying an OAuth2 Client in appropriate flows | Does not equate to a human user; does not replace `sub` of a user token |
| **`tenant_id`** (custom) | Identifying tenant context in policies | Not a subject identity; many users share a tenant |

**A human-readable name is not a reliable identity key.** If a user changes their username or email, records keyed by the old value may no longer map properly. Even worse, two users sharing a display name must never be merged into one business principal.

### 4.1. When Should You Keep the Default `sub`?

Prefer `sub` when:

- The API protects data by **the subject identified by the issuer**.
- Audits need to be tied to an ID that is stable per contract.
- The system maps identity to an internal user record.
- There is no explicit requirement that `Authentication.getName()` must display a username.

With multiple issuers, store the issuer as well or normalize to an **internal user ID** after a trusted mapping step. Do not change the principal name merely to make `sub` look prettier in logs.

### 4.2. When Can You Choose `preferred_username`?

This is viable when the system has a clear contract that:

- Access tokens **always contain** `preferred_username`.
- That claim is issued by a **trusted issuer** and cannot be self-set by Clients.
- `getName()` is only used as a **presentation name or for system compatibility**, not as a sensitive data key.
- If there are multiple tenants/issuers, code does not assume usernames are globally unique.

For example, a legacy application already standardized its principal name as an employee login ID, and the issuer guarantees an immutable `employee_id` claim. In that case, choosing `employee_id` can make sense **if the identity contract is tightly governed**.

### 4.3. When Should You Not Choose Another Claim?

Do not switch `getName()` to `email`, `name`, or a role just to make `@PreAuthorize` expressions shorter. Especially avoid:

~~~text
authentication.getName() = "ADMIN"
~~~

simply because the caller has an admin role. A role is not an individual or service identity. **Principal name**, **GrantedAuthority**, and **resource policy** must keep their distinct meanings.

## 5. Default Spring Security JWT Resource Server Configuration

Example using **Spring Boot 3 / Spring Security 6**, with Orders API accepting signed JWT access tokens. Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Example environment variables:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_API_AUDIENCE=orders-api
~~~

`issuer-uri` is only part of the configuration. The Resource Server must verify signature, issuer, expiration, and **the exact API audience**. How audience is configured depends on your setup/decoder, as illustrated in section 9. Do not assume the same issuer means every token is intended for the Orders API.

Security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

The example assumes `/api/**` is a REST API accepting only Bearer tokens and does not use session cookies for authentication. Therefore, the example disables CSRF in this filter chain and uses stateless sessions. If the same application serves browsers via cookies, handle sessions/CSRF in the appropriate filter chain.

When no custom `JwtAuthenticationConverter` is provided, Spring Security uses its standard mapping: `sub` as the principal name, and valid `scope`/`scp` claims as `SCOPE_...` authorities.

## 6. Customizing `getName()` with `JwtAuthenticationConverter#setPrincipalClaimName`

This is the direct approach if the issuer always provides a **string claim** to serve as the principal name.

### 6.1. Choosing `preferred_username`

Suppose the verified token contains:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "preferred_username": "linh.nguyen",
  "scope": "orders.read"
}
~~~

Converter configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
class PrincipalNameConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        converter.setPrincipalClaimName("preferred_username");
        return converter;
    }
}
~~~

**Important:** Merely declaring a converter bean does not necessarily make every `SecurityFilterChain` use it automatically. You must **wire the converter** into the JWT Resource Server configuration:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

The snippet above is an **alternative variant** of the `apiSecurity` bean in section 5, not a second bean to declare alongside it in the project. When applying it, merge all required rules, CSRF, and session settings for your application model into the proper filter chain.

Once the token is verified, the converter creates `JwtAuthenticationToken` with its name taken from the `preferred_username` claim. Then:

~~~text
authentication.getName()   -> linh.nguyen
jwt.getSubject()           -> user-9f1a
authentication.authorities -> still contains SCOPE_orders.read
~~~

Calling `setPrincipalClaimName(...)` **does not alter scope or role mapping**, does not change the JWT payload, and does not affect signature verification. It primarily changes the principal name string provided by the authentication object.

### 6.2. Externalizing the Principal Claim Name to a Configuration Property

If the issuer contract defines the principal name claim as a fixed configuration value per deployment:

~~~yaml
app:
  security:
    principal-claim: sub
~~~

Code:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
class PrincipalClaimConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            @Value("${app.security.principal-claim}") String claimName) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName(claimName);
        return converter;
    }
}
~~~

In the filter chain, you still need to wire this bean as shown in section 6.1.

**Never let each request choose the claim** via a header, query parameter, or payload:

~~~http
X-Principal-Claim: roles
~~~

The claim name used to determine the principal must be decided by **system contract and trusted configuration**, never requested by the caller.

### 6.3. Missing or Wrongly Typed Claims

If `principal-claim: preferred_username` is configured, yet a service-to-service token lacks this claim, `getName()` may not hold the expected value; exact behavior can vary by converter/customization. Do not rely on assuming the framework will **automatically fall back to `sub`**.

For critical claims, there are two design approaches:

1. **Require the claim by profile**: The Authorization Server commits to issuing it, and the Resource Server uses a validator to reject tokens with missing/wrongly typed claims before using the principal name.
2. **Customize the converter by context**: Derive the name according to a deterministic policy from the verified token, with a safe fallback, clearly separating user tokens and service tokens.

If a claim is a nested object (for example `realm_access.roles`), `setPrincipalClaimName("realm_access.roles")` **does not interpret dot-separated paths** like JSONPath. This method takes a **claim name** for the converter; reading nested claims requires a custom converter or mapping logic.

## 7. Using `Authentication.getName()` in Controllers and Services

There are several ways to obtain caller information from Spring Security:

| Access Method | What Does It Return? | When to Use? |
| --- | --- | --- |
| `Authentication` parameter | Request's `Authentication` after passing the security chain | When you need `getName()` and authorities |
| `Principal` parameter | The `Principal` interface exposing `getName()` | When you only need the principal name without implementation coupling |
| `@AuthenticationPrincipal Jwt` | Verified JWT object in a JWT Resource Server | When you need to read `iss`, `sub`, custom claims |
| `SecurityContextHolder` | Current `SecurityContext` bound to the thread context | In code outside a web controller; watch out for async contexts |
| `@CurrentSecurityContext` | Retrieves `SecurityContext`/authentication via annotation | When you want security data explicitly declared in parameters |

### 7.1. A Controller Can Read Both Principal Name and Subject

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class IdentityController {

    @GetMapping("/whoami")
    IdentityView whoAmI(
            Authentication authentication,
            @AuthenticationPrincipal Jwt jwt) {

        return new IdentityView(
                authentication.getName(),
                jwt.getIssuer().toString(),
                jwt.getSubject(),
                jwt.getClaimAsString("preferred_username"));
    }

    record IdentityView(
            String principalName,
            String issuer,
            String subject,
            String displayUsername) {}
}
~~~

In this example, `Authentication.getName()` changes when the converter changes the claim, while `jwt.getSubject()` still reads `sub`. The `whoami` endpoint is illustrative only: in real deployments, carefully consider which claims are permitted to be returned and avoid exposing sensitive data in responses.

### 7.2. `Principal` Parameter

If you only want the configured name:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/caller-name")
String callerName(Principal principal) {
    return principal.getName();
}
~~~

This is a convenient API for presentation, yet it still does not guarantee `getName()` is an internal user ID. You must know which authentication mechanism verified the request.

### 7.3. `SecurityContextHolder` and Asynchronous Contexts

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    // No suitable authentication in the current context.
}
~~~

The security context is normally tied to request/thread execution per Spring Security configuration. In `@Async`, manually created executor threads, scheduled jobs, message listeners, or reactive flows, **do not assume the security context is always propagated automatically**.

At the web/controller and service layers, it is often easier to control by obtaining `Authentication`/`Jwt` from the authenticated context, constructing an explicit **CallerContext** data type, and passing it to services that make authorization decisions. If you need to propagate the security context across an executor, use the appropriate Spring Security integration rather than copying unverified tokens yourself.

## 8. Choosing a Display Name Different from the Data Identity Key

A common mistake:

~~~java
// DANGEROUS if authentication.getName() is preferred_username or email!
String ownerId = authentication.getName();
Order order = orderRepository.findByOwnerId(ownerId);
~~~

Suppose `ownerId` in the database is `user-9f1a`, while the converter just switched the principal name to `linh.nguyen`. The lookup now fails. If usernames can change, collide, or be reassigned, the risk is far greater than a “data not found” bug.

### 8.1. Using an Identifier with Stable Semantics

For a verified user token:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;

record IssuedSubject(String issuer, String subject) {

    static IssuedSubject from(Jwt jwt) {
        return new IssuedSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

`IssuedSubject` is constructed from two claims **already verified by the Resource Server per contract**. If there is an internal user record such as `appUserId = 8346`, the application can maintain a mapping table:

~~~text
(iss, sub)                            -> internal appUserId
(https://identity.../shop, user-9f1a) -> 8346
~~~

Then:

- `Authentication.getName()` serves as the principal name per Security conventions.
- `(iss, sub)` identifies the subject at the issuer.
- `appUserId` is the internal key managed by the application.
- Access to Order 42 is checked using the internal ID, tenant, and business rules.

Depending on the system, the user identifier may directly be `sub` or an internal ID; the key rule is **never mix display names with data-access keys**.

### 8.2. What Happens If a Username Changes?

Suppose:

~~~text
Initially:
  sub = user-9f1a
  preferred_username = linh.nguyen

After username change:
  sub = user-9f1a
  preferred_username = linh.n
~~~

If the database links owners by `sub` or an internal user ID, permissions on existing orders remain unaffected. If it links by `getName()` with `preferred_username`, older records may stop matching. This explains why **UI principal names and authorization identifiers should be kept separate**.

## 9. Verify the Token Before Trusting the Principal Name

Choosing a principal claim only makes sense after the token has been authenticated. The Resource Server must verify **signature**, **issuer**, **audience**, **expiration**, **token profile**, and agreed conditions.

### 9.1. Configuring a `JwtDecoder` with Audience Validation

Example using a trusted JWKS endpoint, with issuer and audience from configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Decoder:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TokenValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard,
                        audience));
        return decoder;
    }
}
~~~

The JWKS URI must come from metadata or documentation of a trusted issuer; it is not a fixed default endpoint across all Authorization Servers. Restrict accepted JWS algorithms and token profiles per the real contract. When configuring a decoder yourself, retain all necessary validators; never replace standard validators with a check on a principal-name claim.

### 9.2. A Principal-Name Claim Does Not Grant Permissions

Example:

~~~text
Verified JWT:
  sub = user-9f1a
  preferred_username = linh.nguyen
  scope = orders.read

JwtAuthenticationConverter:
  principalClaimName = preferred_username

Result:
  getName() = linh.nguyen
  authorities include SCOPE_orders.read
~~~

To call `POST /api/orders` when the API requires `orders.write`, the caller still lacks write permission. Changing `getName()` to `linh.nguyen` does not change scopes. To read someone else's order, the caller must still satisfy ownership policies or defined roles/permissions.

## 10. Resource Access Must Not Blindly Depend on `getName()`

An easy-to-write expression:

~~~java
@PreAuthorize("#ownerId == authentication.name")
~~~

It is **only valid** if the application contract defines `ownerId` in the request and `Authentication.getName()` using **the exact same identifier type**. If `getName()` switches from `sub` to username, or the request `ownerId` is self-reported by the Client, the expression can yield wrong results.

### 10.1. Separating Scopes and Record-Level Permissions

Suppose:

~~~text
GET /api/orders/42
  Requires scope orders.read
  AND token must target orders-api
  AND order 42 belongs to an authorized subject/tenant
~~~

A method-security example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orders;

    OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@orderAccess.canRead(authentication, #orderId)")
    public OrderDto readOrder(String orderId) {
        return orders.findDtoById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

The policy bean reads identity info from the **verified `JwtAuthenticationToken`**, instead of relying on the principal name string:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAccess")
class OrderAccess {

    private final OrderRepository orders;

    OrderAccess(OrderRepository orders) {
        this.orders = orders;
    }

    public boolean canRead(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken token)) {
            return false;
        }

        Jwt jwt = token.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        return orders.isVisibleToSubject(
                orderId,
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

`OrderRepository`, `OrderDto`, and `OrderNotFoundException` in the example are **domain components**, not built-in Spring Security classes. The `isVisibleToSubject` method must check authoritative record data, tenant, roles, and appropriate conditions; in multi-tenant systems, matching issuer/subject alone is insufficient. `@EnableMethodSecurity` must be enabled for `@PreAuthorize` to take effect.

Benefit of this design: changing the principal name to `preferred_username` for display **does not alter authorization logic anchored on a stable subject**.

### 10.2. When an API Supports Both User Tokens and Service Tokens

In `client_credentials`, a token may look like:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

`sub = nightly-sync` must not be assumed to be a customer owning orders. For **user-only** endpoints, policies should reject service principals if no applicable rule exists. For service endpoints, check Client identity, scopes, audience, and dedicated service permissions.

If a shared converter uses `principalClaimName = preferred_username`, service tokens may lack that claim. This is why it is usually better to **keep `sub` as the default principal name**, and handle subject/Client kinds with explicit policies instead of forcing every token to carry a “human username”.

## 11. Multiple Issuers: Identical Principal Names Do Not Mean the Same Identity

Suppose Orders API trusts two issuers for two customer groups:

~~~text
Issuer A:
  iss = https://id-a.example.test
  sub = 123
  preferred_username = admin

Issuer B:
  iss = https://id-b.example.test
  sub = 123
  preferred_username = admin
~~~

If the application runs:

~~~java
String currentUser = authentication.getName();
~~~

then with a converter using `sub`, both may return `123`; with a converter using `preferred_username`, both may return `admin`. Yet those are **two distinct identities** if the issuers/contracts differ.

### 11.1. Binding Identity to the Issuing Source

The data model should enforce a corresponding unique key:

~~~text
Issuer A + sub 123 -> internalUserId = 7001
Issuer B + sub 123 -> internalUserId = 8824
~~~

Do not create a global map like:

~~~text
sub 123 -> some arbitrary internal user
~~~

unless an approved federation/linking mechanism is in place. In a multi-issuer Resource Server, each issuer needs its own key set, audience, token profile, claim mapping, and policies. Never merge roles from issuer A with roles from issuer B merely because both carry the string `ADMIN`.

### 11.2. If You Want `getName()` to Represent Both Issuer and Subject

`JwtAuthenticationConverter#setPrincipalClaimName(...)` picks **one claim**, and does not concatenate `iss` and `sub`. If you need a name in the form `issuer|subject`, write a **custom converter** that constructs `JwtAuthenticationToken` with a name computed by the application from verified claims.

Example:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class IssuerSubjectJwtConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        // Apply only after the decoder has validated the JWT.
        String principalName = issuer + "|" + subject;

        return new JwtAuthenticationToken(
                jwt,
                scopes.convert(jwt),
                principalName);
    }
}
~~~

Wiring the converter:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(
        new IssuerSubjectJwtConverter())))
~~~

This is **an optional approach**, not mandatory. When using a concatenated string as a business key, you must ensure unambiguous encoding/splitting; it is better to keep `issuer` and `subject` as **two separate fields** in the domain model. Furthermore, this converter assumes issuer/subject are required and valid; policies/validators must guarantee that.

### 11.3. Tenant Is a Separate Dimension

Beyond issuer and subject, a multi-tenant application also needs to determine the subject's permissions within a **specific tenant**. Someone may be an admin in tenant A while only a regular customer in tenant B. You cannot safely handle that by setting `getName()` to `"tenant-A/admin"` while ignoring tenant records and resource policies.

## 12. OIDC Login and Resource Server Do Not Necessarily Share the Same Principal Name

In an architecture consisting of:

- **Shop Web** signing in via Spring Security `oauth2Login()`.
- **Orders API** protecting endpoints via `oauth2ResourceServer().jwt()`.

Shop Web processes OIDC ID tokens and may produce `OAuth2AuthenticationToken` or an `OidcUser` principal. Orders API receives **OAuth 2.0 access tokens** and creates `JwtAuthenticationToken`.

| Aspect | OIDC Client/Login | JWT Resource Server |
| --- | --- | --- |
| Primary token for the task | ID token/OIDC user information | OAuth 2.0 access token |
| Common `Authentication` | `OAuth2AuthenticationToken` / OIDC principal | `JwtAuthenticationToken` |
| Name derivation | Per `OidcUser` and Client's name attribute config | Per `JwtAuthenticationConverter`, default `sub` |
| Audience to verify | ID token targeting the OIDC Client | Access token targeting the Resource Server |
| Goal | Confirm login at the Client | Verify caller and enforce API permissions |

Do not assume:

~~~text
shopWebAuthentication.getName()
    == ordersApiAuthentication.getName()
~~~

in every architecture. The two objects may be created from tokens with different purposes, different token profiles, and different principal configurations. If cross-system identity linking is needed, define **an issuer/subject mapping** and OIDC login relationship rather than relying on two name strings looking alike.

In particular, **ID tokens must not be sent as Bearer access tokens to APIs**. Same issuer and same `sub` do not mean the two token types are interchangeable.

## 13. Opaque Tokens and Other Authentications

Some Resource Servers do not use JWTs and instead use **opaque access tokens** verified via introspection. In that case the authentication flow is different, and `JwtAuthenticationConverter#setPrincipalClaimName(...)` **has no effect** on opaque-token authentication.

Example opaque configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

With opaque tokens, principal information may come from attributes returned by introspection and the converter or Spring Security implementation in use. If an application needs to normalize names across JWTs and opaque tokens, design **two mapping paths** and verify the results rather than assuming one `JwtAuthenticationConverter` serves both.

Similarly, a system using API keys or session authentication may derive `Authentication.getName()` from another source. When writing a shared utility to retrieve the current caller, standardize on a **caller model** (user/service, issuer, subject, Client, tenant) instead of relying solely on a name string.

## 14. Testing Principal Claim Selection

A good test suite separates **converter unit tests** from **integration tests with real JWT verification**.

### 14.1. Converter Unit Tests: Default and Custom

JUnit Jupiter example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

class JwtPrincipalNameTest {

    private Jwt sampleJwt() {
        return Jwt.withTokenValue("test-token-not-for-production")
                .header("alg", "RS256")
                .claim("iss", "https://identity.example.test/realms/shop")
                .claim("sub", "user-9f1a")
                .claim("aud", java.util.List.of("orders-api"))
                .claim("preferred_username", "linh.nguyen")
                .claim("scope", "orders.read")
                .build();
    }

    @Test
    void defaultNameUsesSubject() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        var authentication = converter.convert(sampleJwt());
        assertEquals("user-9f1a", authentication.getName());
    }

    @Test
    void customNameDoesNotChangeSubject() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");

        JwtAuthenticationToken authentication =
                (JwtAuthenticationToken) converter.convert(sampleJwt());

        assertEquals("linh.nguyen", authentication.getName());
        assertEquals("user-9f1a", authentication.getToken().getSubject());
    }
}
~~~

This is a **principal name mapping unit test**. `Jwt.withTokenValue(...)` constructs a `Jwt` object for testing and **does not verify signatures**; do not conclude this test proves issuer/JWKS/audience validation.

### 14.2. Testing Missing and Malformed Claims

Tests should cover these scenarios:

| Token Profile / Scenario | Design Expectation |
| --- | --- |
| User token with valid `sub` | Default principal name equals `sub` |
| User token with valid `preferred_username`, custom converter | `getName()` matches chosen claim |
| Token missing a claim required by converter | Rejected by validator or handled by defined fallback, never silently granting access |
| Chosen claim has unexpected type | Never cast arbitrarily; enforce clear policy |
| Two issuers sharing `sub` | Domain identity remains separated by issuer |
| Username changes, `sub` stays unchanged | Business permissions bound to stable ID stay intact |
| Client credentials token without username | Apply service identity; do not assume human user |
| Tokens with different scopes but same `getName()` | Authorities and access change according to actual scopes |

### 14.3. Integration Tests with Real JWTs

In integration tests, use JWTs genuinely signed with a test key, mock a trusted JWKS/issuer, and invoke the API with `Authorization: Bearer ...`:

1. Token with valid signature, issuer, audience, and timestamps → decoder creates JWT; converter selects expected principal claim.
2. Token with payload tampered after signing → JWT decoder rejects; no trusted principal created.
3. Valid token missing required endpoint scope → authentication may succeed, authorization must deny.
4. Valid token and matching scope but wrong owner/tenant → data policy denies.
5. Token issued by another issuer with same `sub` → identities are not merged.

`SecurityMockMvcRequestPostProcessors.jwt()` is helpful for testing HTTP rules and mock/provided converters in isolation, but **does not verify real JWT signatures**. Do not confuse mock principal tests with JWS/JWKS security testing.

## 15. Impact of Changing the Principal Name in a Running System

Changing:

~~~text
principalClaimName = sub
~~~

to:

~~~text
principalClaimName = preferred_username
~~~

is not merely a UI change if existing code uses `getName()` across multiple places.

### 15.1. Areas Where Impact Must Be Understood

| Usage Area | Risk When Changing `getName()` | Design Direction |
| --- | --- | --- |
| Audit logs | Old and new entries record different names for the same subject | Store stable identity key; keep display name as a separate attribute |
| Database owner/creator | Records not found or matched to wrong owner | Use internal user ID or `(iss, sub)` |
| Cache keys | Data keyed by old username, collisions across issuers | Namespace by issuer/subject/tenant |
| `@PreAuthorize` | Name comparison no longer matches ID type | Compare normalized identity and object policies |
| Jobs/events | Consumers interpret principalName as email/user ID | Version event schemas; add explicit identity fields |
| Logs/metrics | Cardinality spikes or PII leakage | Limit sensitive fields; use opaque/correlation IDs where appropriate |
| User-facing UI | Displayed name changes | Read dedicated display claim or fetch from profile service |
| Third-party services | Principal name mappings stop matching | Align contracts or run a controlled migration |

This is especially important when some services still assume `getName() = sub` while another service switches to `preferred_username`. If services exchange principal names via headers or events without a clear schema, they can misinterpret identities.

### 15.2. Do Not Put Username into Audits as the Sole Identifier

An ambiguous audit record:

~~~json
{
  "action": "ORDER_READ",
  "principal": "linh.nguyen",
  "orderId": "42"
}
~~~

A clearer model:

~~~json
{
  "action": "ORDER_READ",
  "issuer": "https://identity.example.test/realms/shop",
  "subject": "user-9f1a",
  "displayUsername": "linh.nguyen",
  "orderId": "42"
}
~~~

This is an example log/audit structure; adjust it according to your organization's privacy and retention rules. For sensitive data, it is not necessary to log every claim verbatim. Always avoid logging raw Bearer tokens, session cookies, or credentials.

## 16. Common Pitfalls

### “`Authentication.getName()` always returns the login username”

Incorrect. In a JWT Resource Server, the default is usually `sub`. Across other authentication types, implementations may pick another name.

### “Setting the principal claim to `email` is enough for identification”

Emails can change, collide across contexts, or be unverified per contract. It is not an immutable identity key by default.

### “Changing the principal claim also changes `jwt.getSubject()`”

No. `JwtAuthenticationConverter` can change the **Authentication's name**, not modify the signed payload.

### “Just creating a converter bean makes Spring Security attach it to every filter chain”

Do not assume that. Explicitly configure `jwt.jwtAuthenticationConverter(...)` on the filter chain handling Bearer JWTs.

### “`setPrincipalClaimName("realm_access.roles")` automatically reads nested claims”

No. It takes a claim name, not an arbitrary JSON navigation expression. Nested data requires an appropriate converter.

### “Using `@AuthenticationPrincipal Jwt` means access to all data is already granted”

No. A verified JWT may have limited scopes, and permissions on individual records/tenants must still be verified.

### “Two tokens with the same `getName()` belong to the same person”

Not if the issuer or identity context differs. Use issuer and subject per contract, adding tenant or internal user mapping when needed.

### “Changing `getName()` also changes roles”

No. Authorities depend on permission claims and converters, such as `scope` → `SCOPE_orders.read`; principal name is separate.

### “`client_credentials` always includes a human username”

No. The token may represent a Client/service. Never apply end-user permissions unless the token represents that subject type per contract.

### “Decoding the payload and reading `sub` is equivalent to `Authentication.getName()`”

No. Base64URL decoding does not verify signatures or issuer/audience; Resource Server `Authentication` is only trusted after JWT validation.

## 17. Sample Principal Convention for a System

An integration contract might document:

~~~yaml
# Illustrative contract document; not automatically read by Spring.
api: orders-api
issuer: https://identity.example.test/realms/shop
token_use: oauth2_access_token
expected_audience: orders-api
principal:
  spring_get_name_claim: sub
  identity_key:
    - iss
    - sub
  display_claim: preferred_username
  internal_user_mapping: issuer_subject_to_app_user_id
  service_principal_policy: separate_from_end_user
authorization:
  required_scope_for_read: orders.read
  data_policy: check_owner_and_tenant
~~~

From that contract, the team implements:

1. **Authorization Server:** issues access tokens with the right issuer/audience, consistent `sub`, and agreed supplementary claims.
2. **Resource Server:** validates tokens, keeping `getName()` on `sub` or an intentionally selected claim.
3. **Application:** uses `(iss, sub)` to look up internal users; reads display username from a claim or profile service when needed.
4. **Policy:** checks scopes and resource permissions without treating principal name as proof of admin or ownership when identifier types mismatch.
5. **Testing:** verifies default/custom converters, missing-claim tokens, multiple issuers, service tokens, and username changes.

### Questions to Decide Before Changing the Claim

- Is `getName()` used for display or as a database/audit key?
- Is the new claim guaranteed to exist in **access tokens** (not just ID tokens)?
- Is the new claim stable and unique within the scope the application requires?
- Are there multiple issuers, multiple tenants, or `client_credentials` flows?
- Which token profile is accepted, and which validator guarantees the required claim?
- Do other services still assume principal name equals `sub`?
- Should the identity key be mapped to an internal user ID instead of changing the principal name?
- Does current authorization rely on `authentication.name` in SpEL?

---

**Conclusion:** `Authentication.getName()` returns **the principal name according to the active Authentication type and converter**. In a Spring Security JWT Resource Server, this name defaults to the **`sub`** claim, and can be changed via **`JwtAuthenticationConverter#setPrincipalClaimName(...)`** wired into the `SecurityFilterChain`. However, **principal name does not equal a globally unique system identity**: separate display usernames/emails from **`(iss, sub)`** and internal user IDs, especially with multiple issuers/tenants or Client Credentials. Always verify the JWT before trusting claims, and enforce scopes, authorities, and actual resource permissions rather than making decisions on the `getName()` string alone.
