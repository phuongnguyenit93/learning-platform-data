# Wrapping OpaqueTokenIntrospector to Add Contract-Based Checks

In **Spring Security OAuth 2.0/OIDC Resource Server** on the Servlet stack, an access token can be an **opaque** string: the Resource Server does not verify a JWT signature locally from the token string itself, but instead calls the Authorization Server's **OAuth 2.0 Token Introspection Endpoint** to determine whether the token is active and what attributes it carries. Spring Security represents this operation through the **`OpaqueTokenIntrospector`** interface.

However, a successful introspection result with `active=true` **does not automatically guarantee that the token is suitable for every API**. The same Authorization Server may issue tokens for an Orders API, a Payments API, multiple OAuth clients, or multiple tenants. The Orders API may require additional contract-based constraints:

- The token must be **intended for the Orders API**, for example the `aud` claim contains `orders-api`.
- If the introspection response publishes `iss`, the issuer must match the value agreed upon with the API.
- Only OAuth clients on the approved allowlist may call this type of API.
- The token must carry an appropriate tenant; the `tenant_id` claim must not be blank or of the wrong type.
- If the contract requires an expiration time, the token must have a valid `exp`.
- Certain claims or scopes must have the **correct structure and semantics** before being mapped into principal/authorities.

The appropriate extension approach is to **wrap (decorate) a trusted `OpaqueTokenIntrospector`**: call the delegate to perform standard introspection, and return `OAuth2AuthenticatedPrincipal` only when all additional conditions pass. If they fail, the wrapper throws an appropriate exception and **does not produce a trusted principal for the request**.

This lesson focuses on wrapper design, bean configuration with Spring Security, claim structure validation, *fail-closed* error handling, preserving authorities, and the principle of not confusing token validation with business authorization.

> **Key takeaway:** Introspection confirms the token state according to the Authorization Server. The wrapper confirms that the token satisfies **this Resource Server's contract**. After that, HTTP/method authorization must still decide **what actions the caller can perform on which resources**.

## 1. Why Does a Resource Server Need Introspection?

With a self-contained JWT, a Resource Server can use `JwtDecoder` and a public key/JWKS to verify the token locally. With an opaque token, the token string has no claim structure from which the Resource Server is permitted to infer information independently.

Example bearer request:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 5m7y1rs9H9yT0vDb4cWkNQ
```

The string after `Bearer` is a **credential**. The Resource Server cannot look at that string and infer the user, scopes, tenant, or expiration time on its own. It can call the Authorization Server's introspection endpoint over a configured connection and credentials.

Illustrative HTTP introspection example according to RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

For an active token, the response *might* look like this:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://login.example.test/realms/shop",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "exp": 1794718800
}
```

For an inactive token, RFC 7662 allows a minimal response:

```json
{
  "active": false
}
```

**Not every Authorization Server returns all of the claims shown in the active example.** Except for `active`, the remaining fields depend on introspection capabilities, token type, caller privileges, and deployment contract. If the Orders API requires `aud`/`tenant_id`, the Authorization Server must be configured to provide them consistently; you must not assume RFC 7662 forces every AS to emit those claims.

### 1.1. Introspection Response vs. JWT Payload

In the opaque flow, the attributes that `OpaqueTokenIntrospector` receives are **data from a trusted AS introspection response**, not a JWT payload parsed by the API itself.

A token may look like a JWT (three dot-separated parts), yet the system still chooses **introspection** because policy requires online state verification. In that case, inspecting the token's shape alone is not enough to decide whether introspection can be bypassed.

### 1.2. Why Is `active=true` Not Enough?

Suppose the AS issues an active token for the Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read",
  "client_id": "shop-web"
}
```

If the Orders API simply accepts every active token from the same issuer, it may mistakenly accept a token meant for another resource. A wrapper can require `aud` to contain `orders-api` to prevent *token substitution* across Resource Servers.

This is an example of a **contract check**; besides audience, the API can require a client allowlist, tenant, or token type, depending on what the AS commits to returning.

## 2. Position of the Wrapper in the Servlet Filter Chain

Processing flow diagram:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer opaque token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["Unauthenticated BearerTokenAuthenticationToken"]
    C --> D["OpaqueTokenAuthenticationProvider"]
    D --> E["ContractCheckingOpaqueTokenIntrospector"]
    E --> F["Delegate: Nimbus/Spring OpaqueTokenIntrospector"]
    F --> G["Authorization Server introspection endpoint"]
    G --> H{"Token active and introspection valid?"}
    H -- "No" --> X["Authentication failed"]
    H -- "Yes" --> I["OAuth2AuthenticatedPrincipal from delegate"]
    I --> J{"Check aud/iss/client_id/tenant/exp ..."}
    J -- "No" --> X
    J -- "Yes" --> K["Return contract-compliant principal"]
    K --> L["BearerTokenAuthentication + authorities"]
    L --> M["SecurityContext / AuthorizationFilter"]
    M --> N{"Scope and endpoint permissions sufficient?"}
    N -- "No" --> O["Usually 403"]
    N -- "Yes" --> P["Controller / service: record-level permissions"]
    X --> Q["Usually 401 or appropriate error per exception flow"]
```

Key points in this chain:

1. `BearerTokenAuthenticationFilter` extracts the bearer token string according to Spring Security's configuration.
2. `OpaqueTokenAuthenticationProvider` delegates to `OpaqueTokenIntrospector` to verify the token.
3. The delegate introspector calls the Authorization Server, handles the `active` status, and returns `OAuth2AuthenticatedPrincipal` or throws an exception.
4. The wrapper checks additional attributes **that the delegate received from a trusted source**.
5. Only if the wrapper returns a principal does Spring Security build `BearerTokenAuthentication` and its authorities for downstream use.
6. `AuthorizationFilter`/method security decides route, scope, and data permissions.

The wrapper sits at the **authentication/token validation boundary**. It should not replace policies that depend on the HTTP path, order ID, or the state of a specific record.

## 3. Contract of `OpaqueTokenIntrospector`

Spring Security uses an interface conceptually defined as:

```java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

The `token` parameter is the bearer credential string. The return value is `OAuth2AuthenticatedPrincipal`, which holds the information Spring Security will trust after successful introspection.

APIs to know:

| Component | Purpose |
|---|---|
| `OpaqueTokenIntrospector` | Validates a token and returns a principal when the token is accepted |
| `OAuth2AuthenticatedPrincipal` | Accesses principal name, attributes, and `GrantedAuthority` |
| `OpaqueTokenAuthenticationProvider` | Uses an introspector to authenticate `BearerTokenAuthenticationToken` |
| `BearerTokenAuthentication` | Authentication built from an accepted opaque token |
| `BadOpaqueTokenException` | Signals that a token is invalid or does not meet validation conditions |
| `OAuth2IntrospectionException` | Represents an error during introspection, depending on the cause |
| `DefaultOAuth2AuthenticatedPrincipal` | Implementation usable when you need to construct a new principal with controlled attributes/authorities |

The delegate implementation name depends on the library version. Many Spring Security 5.x/6.x projects use `NimbusOpaqueTokenIntrospector`. Newer versions may provide other builder/implementation APIs such as `SpringOpaqueTokenIntrospector`. **The `OpaqueTokenIntrospector` interface itself is the stable extension point needed for the wrapper**; code creating the delegate should match the version in use.

### 3.1. Decorator-Pattern Wrapper

Instead of hand-rolling HTTP requests, JSON parsing, Basic authentication, and `active` checks from scratch, the wrapper **delegates to a delegate**:

```java
public final class DelegatingExampleIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public DelegatingExampleIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        // Additional contract checks go here.
        return principal;
    }
}
```

The wrapper in the example above does not add a policy yet, but it demonstrates the right design:

- Keeps the delegate as the source of token verification.
- Never fabricates `active=true`.
- Never returns a principal when the delegate has thrown an error.
- Never alters permissions just to let a request pass.

## 4. Define the Orders API Introspection Contract Before Writing Code

Suppose the Orders API and Authorization Server have agreed on:

```text
Trusted introspection endpoint:
  https://login.example.test/realms/shop/protocol/openid-connect/token/introspect

Token state:
  active = true (handled by delegate)

API audience:
  aud must contain "orders-api"

Issuer:
  iss must equal "https://login.example.test/realms/shop"
  (AS commits to returning the iss claim in the introspection response)

Allowed OAuth clients:
  client_id in ["shop-web", "trusted-orders-worker"]

Tenant:
  tenant_id must equal "shop-a"
  (this API instance serves shop-a exclusively)

Time:
  exp must exist and be in the future
  nbf, if supplied, must not be in the future
  (AS commits to a compatible NumericDate/Instant format)

Authorization after authentication:
  GET /api/orders/** requires SCOPE_orders.read
  POST /api/orders/** requires SCOPE_orders.write

Business authorization:
  caller may only operate on Orders permitted by tenant/ownership/ACL
```

This is an **illustrative contract**; issuer/tenant/expiration conditions are not mandatory defaults for every introspection server. If the AS only returns `active`, `scope`, and `sub`, you must **agree on additional data with the AS** or use another resource-binding mechanism, rather than inventing missing claims to "pass" policy.

### 4.1. Why Is Audience an Important Condition?

One OAuth client may use multiple APIs:

```text
client_id = shop-web

Access token A:
  aud = orders-api

Access token B:
  aud = payments-api
```

If you only check `client_id=shop-web`, the Orders API could accept token B, which was intended for the Payments API. **`client_id` identifies the calling application; `aud` indicates where the token is permitted to be used.** Do not use those two fields interchangeably.

### 4.2. Why Not Hardcode the Tenant for a Multi-Tenant API?

Suppose an API instance serves both `shop-a` and `shop-b`. If the wrapper requires `tenant_id=shop-a`, every valid token for `shop-b` will be rejected right at authentication.

When a Resource Server is multi-tenant, the wrapper rule might only require that `tenant_id` is present, has the right type, and belongs to a trusted list/relationship. **Whether the caller has permission for a specific order in a given tenant** must still be checked in the service. Do not turn an object-level policy into a token-wide condition if the policy depends on the resource being accessed.

## 5. First Wrapper: Checking Audience After Introspection

A minimal example:

```java
public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object audience = principal.getAttribute("aud");

        boolean matched =
            audience instanceof String text &&
                expectedAudience.equals(text);

        if (audience instanceof Collection<?> values) {
            matched = values.stream()
                .anyMatch(expectedAudience::equals);
        }

        if (!matched) {
            throw new BadOpaqueTokenException(
                "Access token is not intended for this API"
            );
        }

        return principal;
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

How it works:

1. The delegate is called first; if `active=false` or introspection fails, the wrapper **does not continue**.
2. The wrapper reads `aud` from the principal returned by the delegate.
3. It allows a single string `"orders-api"` or a set/list of values containing `"orders-api"`.
4. If the expected audience is not found, it throws `BadOpaqueTokenException`.
5. It returns the **unchanged** principal only when the token complies with the policy.

**Never overwrite `aud` to `orders-api` when the claim is wrong.** Doing so would turn a token for another API into an improperly accepted token.

### 5.1. What If `aud` Is Missing?

Under this policy, `aud=null` causes `matched=false` and the token is rejected. That is **fail closed**.

Keep in mind, however, that RFC 7662 does not force every AS to return audience. If the Orders API needs audience verification, there must be a clear contract that the introspection response always supplies a trusted audience value, or another AS-guaranteed resource-targeting mechanism must be used.

### 5.2. What If `aud` Has an Unexpected Type?

For example:

```json
{"aud": {"resource": "orders-api"}}
```

The wrapper does not try to guess what the object means, and instead rejects it for violating the contract. **Do not use `String.valueOf(...)` to normalize arbitrary data types**; for security-sensitive claims, only accept representations that have been agreed upon.

## 6. Full Wrapper: Issuer, Audience, Client, Tenant, and Expiry

The next example builds an **intentionally strict** implementation for an Orders API instance serving only the `shop-a` tenant.

Assumed introspection contract:

- `active` has already been verified by the delegate.
- `iss` is a URI string or `URI` and must match the expected issuer.
- `aud` is a string or a collection of strings.
- `client_id` is a string in the allowlist.
- `tenant_id` is a string matching the expected tenant.
- `exp` is an `Instant`, numeric epoch seconds, or a date type normalized by the delegate.
- `nbf` is optional; if present, it must be valid with respect to time.

```java
public final class ContractCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;
    private final Set<String> allowedClientIds;
    private final String expectedTenant;
    private final Clock clock;

    public ContractCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience,
            Set<String> allowedClientIds,
            String expectedTenant,
            Clock clock) {

        this.delegate = Objects.requireNonNull(delegate);
        this.expectedIssuer = Objects.requireNonNull(expectedIssuer);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
        this.allowedClientIds = Set.copyOf(allowedClientIds);
        this.expectedTenant = Objects.requireNonNull(expectedTenant);
        this.clock = Objects.requireNonNull(clock);

        if (this.allowedClientIds.isEmpty()) {
            throw new IllegalArgumentException(
                "At least one OAuth client must be configured"
            );
        }
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate must perform introspection first.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Map<String, Object> attributes = principal.getAttributes();

        String issuer = readText(attributes.get("iss"));
        if (!expectedIssuer.equals(issuer)) {
            reject("Issuer does not match the API contract");
        }

        if (!containsAudience(
                attributes.get("aud"), expectedAudience)) {
            reject("Audience does not match the API contract");
        }

        String clientId = readText(attributes.get("client_id"));
        if (!allowedClientIds.contains(clientId)) {
            reject("OAuth client is not allowed");
        }

        String tenant = readText(attributes.get("tenant_id"));
        if (!expectedTenant.equals(tenant)) {
            reject("Tenant does not match the API contract");
        }

        Instant expiration = readInstant(attributes.get("exp"));
        if (expiration == null ||
                !clock.instant().isBefore(expiration)) {
            reject("Token has no valid expiration");
        }

        Object rawNotBefore = attributes.get("nbf");
        if (rawNotBefore != null) {
            Instant notBefore = readInstant(rawNotBefore);

            if (notBefore == null ||
                    clock.instant().isBefore(notBefore)) {
                reject("Token is not yet valid");
            }
        }

        // Preserve the delegate's name, claims, and authorities.
        return principal;
    }

    private static String readText(Object value) {
        if (value instanceof String text) {
            return text;
        }
        if (value instanceof URI uri) {
            return uri.toString();
        }
        return null;
    }

    private static boolean containsAudience(
            Object rawAudience, String expected) {

        if (rawAudience instanceof String text) {
            return expected.equals(text);
        }

        if (rawAudience instanceof Collection<?> values) {
            return values.stream().anyMatch(expected::equals);
        }

        return false;
    }

    private static Instant readInstant(Object rawValue) {
        if (rawValue instanceof Instant instant) {
            return instant;
        }

        if (rawValue instanceof Date date) {
            return date.toInstant();
        }

        if (rawValue instanceof Long seconds) {
            return Instant.ofEpochSecond(seconds);
        }

        if (rawValue instanceof Integer seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }

        // Do not guess uncontracted time strings or numeric types.
        return null;
    }

    private static void reject(String reason) {
        throw new BadOpaqueTokenException(reason);
    }
}
```

Imports:

```java
import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.util.Collection;
import java.util.Date;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

### 6.1. Understanding the Scope of the Example

This is an **illustrative contract**, not a list of mandatory claims under every RFC.

- `expectedIssuer`: Check only when the AS commits to returning an issuer. The trusted introspection URL is configured separately and protected by TLS/credentials.
- `expectedAudience`: Prevents tokens issued for another API.
- `allowedClientIds`: Blocks clients not agreed upon to use this API; **does not replace audience**.
- `expectedTenant`: Suitable only for an instance serving a fixed tenant.
- `exp`: The example intentionally **requires** expiry. An AS might only return `active`; in that case, a different contract is needed instead of synthesizing `exp`.
- `nbf`: If the AS returns `nbf`, check when validity starts.

`readInstant(...)` intentionally restricts the types accepted by the contract. If a delegate implementation returns another type, design an explicit converter rather than catching any value and guessing. In RFC 7662, `exp` is described as integer epoch seconds; whether the delegate converts it to `Instant` or another type depends on the implementation.

### 6.2. Clocks and Clock Skew

The example uses `clock.instant()` to decide validity:

```java
Clock systemClock = Clock.systemUTC();
```

If the system needs a small tolerance between the AS and Resource Server clocks, the rule must be defined clearly. For example, a **contract allowing 30 seconds of skew** could apply:

```java
Duration skew = Duration.ofSeconds(30);
Instant now = clock.instant();

boolean notExpired =
    expiration != null &&
    now.isBefore(expiration.plus(skew));

boolean started =
    notBefore == null ||
    !now.plus(skew).isBefore(notBefore);
```

This only illustrates tolerance logic; when putting it into a wrapper, you must still **reject missing or wrong-typed `exp`** if required by the contract, and clarify inclusive/exclusive boundary semantics.

**Do not set an overly wide skew** to mask NTP failures. Moreover, introspection is online: the AS may already have evaluated time and returned `active=false`. The wrapper must not "resurrect" an inactive token just because the application accepts a larger tolerance.

### 6.3. Why Not Catch Delegate Exceptions and Return a Principal?

Seriously wrong:

```java
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "anonymous-fallback",
        Map.of("scope", "orders.read"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
}
```

The snippet above is an **unsafe example** and must never be used. An introspection endpoint network error or inactive response **is not a reason to create a valid principal**. The right approach: let the exception propagate through the authentication mechanism or handle infrastructure errors while remaining **fail closed**.

### 6.4. Why Does the Wrapper Return the Original Principal?

When all conditions pass, `return principal;` preserves:

- `principal.getName()`.
- `principal.getAttributes()`.
- `principal.getAuthorities()`.

This preserves the delegate's consistency, avoiding accidentally dropping `SCOPE_...` or adding permissions not granted by the AS. If you need to map authorities/attributes, see the dedicated design section below and ensure there is an agreement with the AS.

## 7. Registering the Wrapper as a Bean in Spring Boot

Common dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Example `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/realms/shop/protocol/openid-connect/token/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

The `INTROSPECTION_CLIENT_SECRET` environment variable is illustrative only. Do not hardcode production secrets in source code or write them to logs. Here, `client-id` / `client-secret` are the **Resource Server's credentials for calling the introspection endpoint**, not the `client_id` of the application that requested the access token.

### 7.1. Bean Creating the Delegate and Contract Wrapper

Example with `NimbusOpaqueTokenIntrospector` in Spring Security versions that still provide this constructor:

```java
@Configuration
public class OpaqueTokenSecurityConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                String resourceServerClientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                String resourceServerSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                resourceServerClientId,
                resourceServerSecret
            );

        return new ContractCheckingOpaqueTokenIntrospector(
            delegate,
            "https://login.example.test/realms/shop",
            "orders-api",
            Set.of("shop-web", "trusted-orders-worker"),
            "shop-a",
            Clock.systemUTC()
        );
    }
}
```

Imports:

```java
import java.time.Clock;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

**Library versions:** `NimbusOpaqueTokenIntrospector` is the familiar implementation in Spring Security 5.x/6.x, though some newer versions use/deprecate other APIs. If your project's dependency does not have the constructor in the example, use the introspector builder/implementation appropriate **for your actual version** and pass it into the same wrapper. Do not rewrite HTTP introspection from scratch just because the builder API changed.

### 7.2. Why Does a Custom Bean Affect Auto-Configuration?

Spring Boot can auto-configure an introspector from `spring.security.oauth2.resourceserver.opaquetoken.*`. When the application registers its own `OpaqueTokenIntrospector` bean, auto-configuration normally **backs off**, and **the application-created bean becomes the actual source of introspection**.

Therefore, do not just declare:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

and assume your custom bean has already received those values if it does not bind those properties. The example above uses `@Value` to retrieve them.

In systems with complex Spring configuration, avoid creating a **circular bean dependency** by trying to inject `OpaqueTokenIntrospector` into the very bean of the same type it is building. Create a separate delegate or use explicit names/qualifiers.

## 8. Connecting the Introspector to a Servlet `SecurityFilterChain`

A reference configuration:

```java
@Configuration
public class ApiSecurityFilterConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Here, the `opaqueToken(...)` branch uses the configured `OpaqueTokenIntrospector`. When the wrapper bean successfully returns `OAuth2AuthenticatedPrincipal`, the provider creates an Authentication so HTTP authorization can evaluate authorities.

Avoid overly broad rules like:

```java
.requestMatchers("/api/**").authenticated()
```

and thinking the wrapper's `aud`/`tenant_id` checks alone are enough. A valid token without the `orders.write` permission must still be rejected on a POST requiring write permission.

### 8.1. Using the DSL to Specify the Introspector Explicitly

In some configurations, you can pass the introspector directly to the opaque token branch:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(opaque ->
        opaque.introspector(contractIntrospector)
    )
)
```

`contractIntrospector` is an object created or supplied to the configuration appropriately. This is useful when there are multiple beans or when you need explicit control over which introspector is used for a specific chain.

**When there are multiple `SecurityFilterChain`s**, verify that the request actually selects the chain configured for opaque tokens. `securityMatcher(...)` defines the scope of the entire chain, while `requestMatchers(...)` defines rules inside that chain.

## 9. Introspection Client Credentials vs. OAuth Caller `client_id`

This is a very common point of confusion:

| Information | Party | What Is It Used For? |
|---|---|---|
| `opaquetoken.client-id` in Spring config | Resource Server | Authenticating when calling the introspection endpoint |
| `opaquetoken.client-secret` in Spring config | Resource Server | Secret for authenticating to the introspection endpoint |
| `client_id` claim in introspection result | OAuth client that requested/holds the token, per AS | Can be used for policy about the calling application |
| `aud` claim | Resource Server/API the token is intended for | Checking whether the token is intended for the Orders API |
| `sub` claim | Principal associated with the token | User/service identity depending on grant/profile |

For example, the Resource Server calls introspection with credentials `orders-api-introspection`, and the AS returns:

```json
{
  "active": true,
  "client_id": "shop-web",
  "aud": ["orders-api"]
}
```

**There is no conflict**: the two client IDs serve two different roles.

A common mistake is a wrapper comparing the `client_id` claim against the client ID used to authenticate the introspection request. That will reject valid tokens from the `shop-web` application, or lead to opening policy to an unintended value.

## 10. Checking `iss` When the Introspection Response Does or Does Not Include Issuer

In JWTs, the `iss` claim is typically the token's issuer. With RFC 7662 introspection, `iss` is an attribute that may be returned, but **not every AS returns the issuer**.

If the AS commits to publishing the issuer:

```java
String issuer = readText(principal.getAttribute("iss"));
if (!expectedIssuer.equals(issuer)) {
    throw new BadOpaqueTokenException("Unexpected issuer");
}
```

This is a valid policy.

If the AS **does not return an issuer**, yet the introspection endpoint is authenticated via a dedicated URL/TLS and credentials, the Resource Server cannot fabricate an issuer claim on its own and call that validation. Consider:

1. Agreeing that the AS returns `iss` for active tokens.
2. Using a dedicated trusted introspection endpoint per tenant/realm, under a contract that responses apply only to tokens from that realm.
3. Using an AS-supported mechanism to bind tokens to an issuer/resource.
4. Never allowing acceptance for another issuer just because the claim is missing.

**Do not mix tokens from multiple ASes into a shared introspector** without proper trusted issuer resolution. Routing to an AS based on unverified token data must stay within a governed allowlist/logic.

## 11. Audience and Resource Binding

If an active token is intended only for the Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read"
}
```

The Orders API must reject it if policy requires `aud` to contain `orders-api`. Because `active=true` only states that the token is still active in the AS's context, not that it may be used at every Resource Server.

### 11.1. String Form vs. List Form

Depending on the contract, `aud` can be:

```json
"aud": "orders-api"
```

or:

```json
"aud": ["orders-api", "inventory-api"]
```

The `containsAudience(...)` helper in the example supports both. If the AS returns a list containing another type such as an object, the wrapper rejects it unless the AS defines a formal conversion.

### 11.2. Multiple Audiences Do Not Mean Accepting the Token for Every API

A multi-audience token may be used across multiple resources permitted by the AS. Still, the Orders API must verify that **it itself is in the audience**. Do not alter `aud` or treat `client_id` as the audience just because all tokens belong to one OAuth client.

### 11.3. Scope and Audience Are Two Independent Constraints

A token with `scope=orders.read` but `aud=payments-api` still must not be used at the Orders API. A token with `aud=orders-api` but without `orders.read` must also not call a read endpoint requiring that scope.

The wrapper checks audience; `authorizeHttpRequests(...)` and the service check operation and object permissions.

## 12. Checking `client_id`: Bounded Allowlist

Some APIs serve only approved enterprise applications:

```text
allowed clients:
  shop-web
  trusted-orders-worker
```

A wrapper can check:

```java
String clientId = readText(principal.getAttribute("client_id"));

if (!allowedClientIds.contains(clientId)) {
    throw new BadOpaqueTokenException("Client not allowed");
}
```

Keep in mind:

- `client_id` is only trustworthy when a trusted AS's introspection response commits to that meaning.
- The allowlist is a **Resource Server rule**, never taken from the bearer request body/query.
- Client ID does not replace audience.
- Client ID does not prove the end user is the owner of an order.
- With multiple tenants, a client might be permitted in tenant A but not in B; check the `(client, tenant)` pair constraint if required by the contract.

### 12.1. Do Not Use a Client Allowlist in Place of OAuth Scopes

If `shop-web` is a valid client, yet the token was only granted `profile`, the caller still does not have `orders.write`. The allowlist checks **the application**; scope/authority checks **the capabilities granted to the token**.

### 12.2. Client Credentials Case

A client-credentials token may represent a service principal:

```json
{
  "active": true,
  "client_id": "trusted-orders-worker",
  "sub": "service-order-sync",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

If policy requires that only a specific set of service clients may synchronize, the wrapper can be one layer of defense. However, object-level policy must still restrict **the set of orders belonging to the permitted integration/tenant**, not let the service read all data just because the client is on the allowlist.

## 13. Checking Tenant: Claim Validation vs. Object Permissions

Suppose the AS returns:

```json
{
  "active": true,
  "tenant_id": "shop-a",
  "aud": ["orders-api"]
}
```

For an Orders API serving only `shop-a`, the wrapper can demand an exact tenant match. But for an Orders API serving multiple tenants, the policy should differ:

```java
Object rawTenant = principal.getAttribute("tenant_id");

if (!(rawTenant instanceof String tenant) ||
        tenant.isBlank()) {
    throw new BadOpaqueTokenException("Invalid tenant_id");
}
```

Then object policy verifies whether the user/service is allowed to read the specific order.

```text
Token:
  tenant_id = shop-a
  scope = orders.read

Request:
  GET /api/tenants/shop-b/orders/order-99

Wrapper:
  does token have a valid tenant? Possibly yes

Service policy:
  does caller have access to shop-b/order-99? No
```

Never overwrite `tenant_id=shop-b` just because the URL asks for `shop-b`. Path/query parameters sent by the caller are request data, **not proof of authorization**.

### 13.1. When Membership Changes

An active opaque token may return claims from introspection reflecting AS state, which does not automatically mean every tenant permission update in the business database has been reflected. Sensitive systems may need to look up current membership/assignments, especially when permissions are revoked.

Do not use a token-wide wrapper to replace all per-record owner/tenant binding logic.

## 14. Checking Expiration with `exp` and `nbf`

RFC 7662 describes:

- `exp`: when the token expires, as a NumericDate (if returned).
- `iat`: when the token was issued (if returned).
- `nbf`: the token is not allowed to be used before this time (if returned).

The AS is typically responsible for deciding `active`. Under a strict contract, however, a Resource Server may want to add a rule that "the token must have `exp`" or verify `nbf` if published by the AS.

### 14.1. Never Assume `exp` Is Always Present

A response like:

```json
{
  "active": true,
  "scope": "orders.read"
}
```

does not violate RFC 7662 merely because `exp` is absent. If the application mandates expiry, that is an **additional requirement** that must be supported by the Authorization Server.

Do not synthesize `exp=now+1h` for a token missing expiry to make the wrapper accept it. Doing so fabricates a claim the AS did not confirm.

### 14.2. When `exp` Is Required, Fail Closed

```java
Instant expires = readInstant(principal.getAttribute("exp"));

if (expires == null || !clock.instant().isBefore(expires)) {
    throw new BadOpaqueTokenException("Missing or expired exp");
}
```

If there is a small clock drift between the AS and RS, a reasonable clock skew can be defined. But skew must never cause the wrapper to accept a token the delegate already determined to be inactive. **`active=false` must always be rejected**.

### 14.3. `iat` Does Not Replace `exp`

A token issued 10 minutes ago may still be valid or already expired depending on the AS. The `iat` claim is only the issuance timestamp and does not prove TTL on its own.

If the API needs to limit token age by `iat`, it must explicitly define a dedicated policy and clock/tolerance rather than inferring it from the claim name.

## 15. Checking Token Type and Profile

An introspection response may contain:

```json
"token_type": "Bearer"
```

Under RFC 7662, `token_type` is the token type if published by the AS. Some systems also include custom attributes describing an access token or refresh token.

The Resource Server must **accept tokens matching the type and purpose it supports**. If the AS can introspect refresh tokens or tokens intended for other purposes, the contract must prevent using them as bearer access tokens on the API.

An illustrative rule when the AS commits to `token_type=Bearer`:

```java
Object rawType = principal.getAttribute("token_type");

if (!(rawType instanceof String type) ||
        !"Bearer".equalsIgnoreCase(type)) {
    throw new BadOpaqueTokenException("Unsupported token type");
}
```

**Do not apply this rule blindly to every AS**: some ASes do not return `token_type` in the response or use a custom profile. You must understand the specification your system actually implements.

Do not use an OIDC ID token in place of an access token merely because it shares the same issuer and contains a subject. The Resource Server needs to verify the token is intended for the API, especially via audience and the AS contract.

## 16. Mapping Scopes and Authorities: Keep As-Is or Customize?

After successful introspection, `OAuth2AuthenticatedPrincipal` provides:

```java
principal.getAttributes();
principal.getAuthorities();
principal.getName();
```

In common configurations, Spring Security may create authorities such as:

```text
SCOPE_orders.read
SCOPE_orders.write
```

from the `scope` response according to the implementation's rules.

**A contract-checking wrapper should not arbitrarily grant additional permissions.** Wrong example:

```java
List<GrantedAuthority> elevated = List.of(
    new SimpleGrantedAuthority("ROLE_ADMIN")
);

return new DefaultOAuth2AuthenticatedPrincipal(
    principal.getName(),
    principal.getAttributes(),
    elevated
);
```

If the AS only granted a read scope, having the wrapper assign `ROLE_ADMIN` without basis is **privilege escalation**.

### 16.1. When Claims Need Normalization Before Mapping Authorities

Suppose the AS uses a custom claim:

```json
{
  "active": true,
  "permissions": ["orders:read", "orders:export"]
}
```

To map them to authorities, you need a **contracted policy**:

- Which authority does `orders:read` correspond to?
- Are audience/tenant or client type checks required?
- Is the `permissions` claim guaranteed to come from a trusted AS?
- Are admin roles allowed, or only API scopes?
- Should the delegate's authorities be preserved?

An example that **only adds a validated display attribute**, without granting new permissions:

```java
Map<String, Object> attributes =
    new LinkedHashMap<>(principal.getAttributes());

Object tenant = attributes.get("tenant_id");

if (tenant instanceof String text && !text.isBlank()) {
    attributes.put("internal_tenant_code", text);
}

OAuth2AuthenticatedPrincipal enriched =
    new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        attributes,
        principal.getAuthorities()
    );
```

Imports:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
```

This snippet only illustrates how to construct a new principal when you **truly need** to add an internal alias. For a check-only wrapper, `return principal;` is best. Never turn an alias into proof that a claim was independently issued by the AS.

### 16.2. When You Want to Change the Principal Name

In an opaque Resource Server, `OAuth2AuthenticatedPrincipal.getName()` may be based on subject/username information from the AS depending on the implementation. If you need a stable identity, define a `sub`/issuer/tenant contract or account mapping in your system. Never merge identities across multiple issuers using username or email merely because they look the same.

For object authorization, you may need the **`(issuer, subject)`** identity pair, not just the principal name.

## 17. The Wrapper Does Not Replace HTTP Authorization

Once the wrapper has accepted a token:

```text
active = true
correct iss
aud contains orders-api
allowed client_id
valid tenant
valid exp
```

the request still needs HTTP conditions:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
```

A token with the `orders.read` scope must not be allowed to call POST if POST requires `orders.write`. Conversely, a token with `orders.write` does not automatically have read access if the API policy separates the two scopes.

### 17.1. Object-Level Authorization Remains Mandatory

Suppose `user-123` has a valid token for the Orders API with `SCOPE_orders.read`, and tries to read `user-456`'s order.

The wrapper **has no order ID/DB resource context** to decide ownership. The service must check:

```text
canReadOrder(actor, order):
  actor has SCOPE_orders.read
  AND actor tenant is allowed
  AND (
       actor is owner
       OR share ACL permits
       OR assigned support policy permits
  )
```

Do not put per-request DB queries inside a token-wide introspector just to check a specific order; otherwise, a token that is valid for another endpoint could be rejected at authentication due to a rule at the wrong layer.

## 18. Errors from the Delegate vs. the Wrapper Must Be Distinguished

Common failures:

| Case | Detecting Component | Meaning |
|---|---|---|
| `active=false` | Delegate introspector | Token is no longer active or not confirmed by the AS |
| Invalid introspection credentials | Delegate/HTTP layer | Resource Server could not authenticate to the AS |
| AS timeout/TLS/DNS failure | Delegate/HTTP layer | Introspection infrastructure is unavailable |
| `aud` does not contain `orders-api` | Wrapper | Token is not intended for the API |
| `client_id` not in allowlist | Wrapper | Client does not satisfy contract |
| `tenant_id` missing or wrong | Wrapper | Token does not satisfy tenant constraint |
| `exp` missing when required | Wrapper | Contract requiring expiry is not met |
| Token passes introspection, missing `SCOPE_orders.read` | AuthorizationFilter | Caller lacks operation permission |
| Token has scope, not allowed to view `order-42` | Service/method security | Caller lacks object permission |

### 18.1. `BadOpaqueTokenException`

When the wrapper determines that a token **does not meet the validation contract**, it can use:

```java
throw new BadOpaqueTokenException(
    "Audience does not match the API contract"
);
```

Spring Security handles the exception in the authentication chain according to the configured provider, entry point, and handlers. In many Resource Servers, an invalid token error leads to `401 Unauthorized` with a bearer error such as `invalid_token`.

Example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

The exact HTTP status/header depends on exception propagation and configuration. You should not conclude that every introspection failure always produces the exact same response.

### 18.2. Network Errors and Token Errors Are Two Different Categories

If the AS returns `active=false`, there is a basis to consider the token inactive. If the AS times out, the Resource Server **does not have enough information to validate the token**, though that does not prove the token was revoked by the AS.

The system must still **fail closed**. In internal observability, distinguish:

```text
AUTH_TOKEN_INACTIVE
AUTH_CONTRACT_WRONG_AUDIENCE
AUTH_CONTRACT_INVALID_TENANT
INTROSPECTION_TIMEOUT
INTROSPECTION_TLS_ERROR
INTROSPECTION_CREDENTIAL_FAILURE
```

Never catch all exceptions broadly and return a fake principal. Nor should you return full stack traces, sensitive internal URLs, or introspection credentials in client responses.

## 19. Do Not Create Infinite Introspection Loops

A common configuration mistake is a wrapper invoking the very introspector bean it is replacing:

```java
@Bean
OpaqueTokenIntrospector myIntrospector(
        OpaqueTokenIntrospector introspector) {
    return token -> introspector.introspect(token);
}
```

If bean wiring creates a circular dependency or self-reference, the application may fail to start or behave incorrectly. The right approach is to instantiate a **concrete delegate** using a trusted implementation and pass it into the wrapper; or declare a separate delegate bean with an explicit qualifier:

```java
@Bean("baseIntrospector")
OpaqueTokenIntrospector baseIntrospector(...) {
    // Instantiate Spring Security's implementation according to your version.
}

@Bean
@Primary
OpaqueTokenIntrospector contractIntrospector(
        @Qualifier("baseIntrospector")
            OpaqueTokenIntrospector delegate) {
    return new ContractCheckingOpaqueTokenIntrospector(
        delegate, ISSUER, AUDIENCE, CLIENTS, TENANT, Clock.systemUTC()
    );
}
```

The second snippet illustrates *wiring*, using hypothetical constants `ISSUER`, `AUDIENCE`, `CLIENTS`, `TENANT`, and the delegate body must be implemented per the project's configuration. `@Primary` is only needed when there are multiple beans of the same type and you want to designate a default; prefer explicit DSL/qualifiers if different `SecurityFilterChain`s use different policies.

## 20. Never Let the Token Determine the Introspection URL

Suppose a client sends a bearer token:

```text
token = https://attacker.example.test/token/abc
```

or a token structured so an attacker embeds a URL inside the string. The Resource Server **must never extract a URL from the token** to call introspection arbitrarily. Doing so can cause SSRF or trust an unconfigured AS.

The introspection URI must be **trusted configuration**. With multiple issuers/tenants, endpoint selection must rely on a governed allowlist/mapping, never calling a URL from unverified data.

### 20.1. TLS and Credentials

The introspection endpoint typically requires the Resource Server to prove its identity to the AS (e.g., HTTP Basic with client credentials, `private_key_jwt`, mTLS, or another mechanism depending on the AS). You need:

- HTTPS with valid certificate verification.
- Secrets supplied from a controlled secret manager/env, never hardcoded.
- Introspection client permissions limited strictly to performing introspection.
- Never logging the `Authorization: Basic` header or the token sent for introspection.
- Controlled timeouts, connection pooling, and retry/backoff.
- Explicit egress/network policies.

**Do not use a frontend/mobile app's OAuth client secret** as the introspection secret. A public client cannot protect a secret like a server-side client; introspection authentication must be configured appropriately with the AS.

## 21. Timeouts, Retries, and Availability

Opaque introspection typically depends on the network during the authentication flow. If every request requires a roundtrip:

```text
Client → Orders API → AS introspection → Orders API → Controller
```

AS latency or outages can directly impact the Orders API.

Operational strategies:

| Strategy | Benefit | Risks / Conditions |
|---|---|---|
| HTTP connect/read timeouts | Prevents requests from hanging too long | Too-short timeouts cause false failures |
| Connection pooling | Reduces connection setup overhead | Must manage lifecycle and connection limits |
| Bounded retries | Helps survive transient failures | Can overload the AS under synchronized retries |
| Circuit breaker | Protects infrastructure during prolonged AS failures | Must still fail closed when the breaker is open |
| Rate limiting | Reduces bearer request abuse | Must not block legitimate traffic |
| Observability | Distinguishes network errors vs. invalid tokens | Never log secrets |

Do not "optimize availability" by granting temporary access when the AS is unreachable. A token that has not been introspected successfully **cannot be considered authenticated**.

## 22. Should You Cache Introspection Results?

Caching can reduce latency and load on the AS, but it changes the meaning of "checking the current token state."

Pros:

- Reduces introspection calls for the same bearer token.
- Reduces endpoint latency.
- Reduces network dependency on the AS within the valid cache window.

Security downsides:

- A token revoked after an introspection call may still be accepted until the cache entry expires.
- Membership/tenant/permission changes in the AS may not be reflected yet.
- The cache holds sensitive data from tokens.
- An unsafe cache key can expose the bearer token.

### 22.1. Principles Before Enabling Caching

1. Cache only after both the delegate and contract wrapper **have accepted** the token.
2. Define a maximum TTL smaller than the relevant token/contract expirations.
3. Evaluate revocation detection latency requirements.
4. Never use raw bearer tokens as keys in logs/metrics.
5. Protect the cache and principal data; consider a hash/HMAC lookup key, and avoid logging keys from which the bearer token could be recovered.
6. Invalidate per policy if permissions/tenants change.
7. During an AS outage, **never extend cache TTLs indefinitely** to keep accepting stale credentials.

Cache placement also matters:

```text
Bearer token
  -> contract-checked cache?
  -> delegate introspection on cache miss
  -> wrapper checks
  -> result
```

If caching **before the wrapper**, every cache hit must still run contract checks, especially when expected audience/tenant/client allowlists may change. If caching after the wrapper, the cache stores policy-checked results, so you must handle policy versioning/invalidation when the contract changes.

### 22.2. Revocation and Short-Lived Tokens

One reason to choose opaque introspection is being able to ask the AS about `active`. If you cache for a very long time, the benefit of online revocation is diminished. Agree on revocation detection targets and choose TTLs according to API risk.

There is no single "right" TTL across all organizations. Payment APIs or administrative operations may need tighter bounds than low-sensitivity document-reading APIs.

## 23. Never Turn Introspection Claims into Out-of-Contract Permissions

A dangerous mistake:

```java
if (principal.getAttribute("client_id") != null) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        principal.getAttributes(),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
}
```

The mere presence of a `client_id` claim **does not prove every client is an admin**. Authority mapping must correspond to permissions/scopes granted by the AS and business policy.

Another wrong rule:

```java
if (principal.getAttribute("aud") == null) {
    attributes.put("aud", "orders-api");
}
```

If the API requires `aud` and the AS does not return the claim, fix the contract or reject the token. Filling in the audience yourself turns a security check into a condition that is always true.

Similarly, never patch `exp` when a token has expired, assign `tenant_id` from the request path, or fill in `sub=admin` when missing.

## 24. Testing the Wrapper with Isolated Unit Tests

An advantage of the decorator pattern is easy testing with a fake delegate **without making real network calls**.

Suppose a simple wrapper only checks audience:

```java
@Test
void acceptsMatchingAudience() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of(
                "sub", "user-123",
                "aud", List.of("orders-api")
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        );

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(delegate, "orders-api");

    OAuth2AuthenticatedPrincipal result =
        introspector.introspect("test-token");

    assertEquals("user-123", result.getName());
}
```

Wrong audience case:

```java
@Test
void rejectsWrongAudience() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of(
                "sub", "user-123",
                "aud", List.of("payments-api")
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_payments.read")
            )
        );

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(delegate, "orders-api");

    assertThrows(
        BadOpaqueTokenException.class,
        () -> introspector.introspect("test-token")
    );
}
```

Illustrative imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

**These unit tests do not call the AS introspection endpoint and do not prove a real token is active.** They only verify wrapper behavior when the delegate returns a mocked principal.

### 24.1. Testing That a Delegate Exception Remains Fail-Closed

```java
@Test
void doesNotRecoverFromInactiveToken() {
    OpaqueTokenIntrospector inactiveDelegate = token -> {
        throw new BadOpaqueTokenException("Inactive token");
    };

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(
            inactiveDelegate, "orders-api");

    assertThrows(
        BadOpaqueTokenException.class,
        () -> introspector.introspect("inactive-token")
    );
}
```

The key point is that the wrapper **does not return a principal when the delegate has already rejected the token**.

### 24.2. Scenarios to Cover in Test Design

| Introspection/Delegate | Wrapper Contract | Expected Outcome |
|---|---|---|
| Delegate throws `BadOpaqueTokenException` (inactive) | No further checks | Reject |
| Delegate throws network error | Do not turn into success | Fail closed |
| Active, matching `aud` | Remaining conditions pass | Accept |
| Active, `aud` only for Payments API | Wrong audience | Reject |
| Active, missing `aud` when contract requires it | Wrong audience | Reject |
| Active, `client_id` outside allowlist | Wrong client | Reject |
| Active, wrong/missing tenant | Wrong tenant | Reject |
| Active, missing `exp` when contract requires it | Invalid expiry | Reject |
| Active, expired `exp` | Invalid time | Reject |
| Active, all contract checks pass, missing read scope | Wrapper accepts; HTTP authorization rejects | Usually 403 |
| Active, valid read scope, order belongs to another user | Wrapper accepts; service policy rejects | 403/404 depending on policy |

### 24.3. Integration Tests with a Real AS Contract

In addition to unit tests, when a test environment is available, verify:

- Spring Boot uses the **actual wrapper introspector bean**, not accidentally falling back to a different auto-configured delegate.
- The introspection HTTP request is authenticated with the Resource Server's correct credentials.
- An `active=false` response is rejected.
- An `active=true` response with the wrong `aud` is rejected.
- Authorities after the wrapper remain those granted by the AS/mapper.
- Endpoints apply `hasAuthority(...)` properly.
- Error paths do not leak bearer tokens/secrets.
- Timeout/TLS failures do not create an Authentication.
- Public and protected requests pass through the right `SecurityFilterChain`.

You can use an HTTP stub server instead of a real AS to simulate introspection responses, keeping in mind that stubs cannot replace verifying production policy and configuration.

## 25. Introspection May Return Wrong-Typed Timestamps or Unstable Claims

For example, an AS returns:

```json
{
  "active": true,
  "tenant_id": 42,
  "aud": "orders-api",
  "exp": "1900000000"
}
```

If the contract requires:

```text
tenant_id: String
exp: integer NumericDate
```

then this response **violates the contract**. Do not arbitrarily coerce a numeric tenant and string `exp` into the expected types without agreement.

An implementation might convert claims before the wrapper sees them. Rather than guessing from sample JSON, base your logic on the actual data returned by `OAuth2AuthenticatedPrincipal.getAttributes()` and the library/AS contract.

### 25.1. Intentional Type Conversion

If the issuer officially commits that a tenant ID can be either an integer or a string with the same meaning, you can convert it strictly. For example:

```java
String tenantCode(Object raw) {
    if (raw instanceof String text && !text.isBlank()) {
        return text;
    }
    if (raw instanceof Integer number) {
        return number.toString();
    }
    return null;
}
```

However, for identifiers with leading zeros or very large numbers, type conversion can lose information. For claims used in authorization, it is best if the issuer emits **a single stable format**.

### 25.2. Converters Must Never Fix Policy Violations

If the `aud` claim is `payments-api`, you cannot "normalize" it to `orders-api`. If `exp` is expired, you cannot extend expiry. If the AS does not return a tenant, you cannot assign one from the URL and treat it as verified.

**Type conversion** is valid only when it preserves the exact semantics of the data promised by the AS.

## 26. Multi-Tenant and Multi-Issuer Considerations When Wrapping an Introspector

A system may accept tokens from two realms:

```text
Issuer A:
  https://login.example.test/realms/shop

Issuer B:
  https://login.example.test/realms/partners
```

Each issuer may have its own introspection endpoint, credentials, audience, client rules, and tenant semantics. **Do not use a single overly broad endpoint or policy** just because they belong to the same login server.

A viable architecture can:

1. Select among **allowlisted issuers** via a trusted resolver.
2. Use the introspection client credentials matching the issuer/realm.
3. Delegate to the corresponding introspection endpoint.
4. Run the contract wrapper for that issuer/resource.
5. Return a principal with an unambiguous identity, avoiding subject collisions between two issuers.
6. Apply authorization by resource and tenant.

If two realms both have `sub=user-123`, they may be two independent accounts. When evaluating ownership, identity often requires the **`(issuer, subject)`** pair or a trusted internal mapping.

Never allow a caller to specify a new `introspection_uri` and ask the Resource Server to trust responses from it.

## 27. Distinguishing Configuration Errors, Contract Errors, and Authorization Errors

A diagnostic table:

| Symptom | Common Cause | Investigation Path |
|---|---|---|
| Every token returns 401 right after adding the wrapper | The AS does not return a claim newly required by the wrapper | Compare the introspection contract against what the AS actually returns |
| Only a new client gets 401 | `client_id` is not in the allowlist | Check client registration/policy |
| A Payments API token calling Orders API gets 401 | Audience is properly rejected | Do not widen audience to "fix" it |
| Token is active but returns 401 due to tenant | Token tenant does not match contract | Check which tenant the API instance serves |
| Sudden timeout/5xx errors | AS or introspection network is having issues | Check TLS/DNS/egress/timeouts; do not disable authentication |
| Token passes wrapper, but GET returns 403 | Missing `SCOPE_orders.read` | Check scope-to-authority mapping |
| Token passes HTTP rules, but order returns 403/404 | Insufficient object permissions | Check owner/tenant/share/assignment |
| One pod accepts while another rejects | Different policy/allowlist/AS endpoint config | Compare rollout and instance configurations |
| Revoked token still works | Introspection cache TTL too long or broken invalidation | Review TTL/revocation design |

You cannot deduce from an HTTP status code alone that the AS revoked a token. Categorized internal logs/metrics are needed, without exposing secrets.

## 28. A Runbook for Rolling Out a New Wrapper

### Step 1 — Document the Contract Before Coding

Identify which fields the AS returns consistently, which are optional, and which need checking at the Resource Server. In particular: `active`, `aud`, `iss`, `exp`, `client_id`, `tenant_id`, `scope`.

### Step 2 — Keep the Trusted Introspection Delegate Intact

Never write a naive implementation that always returns a principal. The delegate must verify `active`, HTTP security, and the AS response per its implementation.

### Step 3 — Add One Token-Wide Rule at a Time

For example, check audience first; then client allowlist; then tenant. If the AS is missing a claim, make a **contract decision** rather than silently filling in values.

### Step 4 — Separate Authentication from Authorization

A token passing the wrapper does not automatically have read/write permission or access to every object. Add appropriate `requestMatchers(...)` and service authorization.

### Step 5 — Observe Failures Safely

Log categories:

```text
request_id=req-123
authn=FAILED
component=contract_introspector
reason=INVALID_AUDIENCE
configured_audience=orders-api
route=/api/orders/{id}
```

Never log bearer token strings or HTTP Basic secrets.

### Step 6 — Verify Multi-Instance Rollout

Ensure all instances share the same expected issuer/audience, client allowlist, tenant policy, and wrapper version. Never leave one instance failing open or using an unchecked delegate.

### Step 7 — Account for Performance and Availability

Define timeouts, bounded retries, metrics, AS capacity, fail-closed circuit breakers, and an appropriate caching/revocation policy.

### Step 8 — Test AS Failure Modes

If the AS returns inactive or the network fails, the API must reject the token. Keep internal error categories clear enough for operations.

## 29. Mistakes to Avoid

### Mistake A — Treating `active=true` as Permission for Every API

`active=true` does not mean the token is intended for the Orders API. If the contract requires it, check audience/resource binding.

### Mistake B — Replacing the Delegate with a Fake Principal

Never skip the introspection request or fabricate authorities when the AS does not respond. That is *fail open*.

### Mistake C — Catching All Exceptions and Accepting

A network error does not prove a token is valid. You must reject when verification cannot be completed.

### Mistake D — Using Introspection Credentials as the `client_id` Claim

They serve two different roles. The Resource Server has client credentials to call the AS; the user or application calling the API has its own `client_id` in the token.

### Mistake E — Checking `client_id` and Skipping `aud`

A client can request tokens for multiple APIs. A client allowlist does not replace audience.

### Mistake F — Hardcoding a Tenant on a Multi-Tenant Resource Server

Valid tokens from other tenants get rejected unnecessarily. Define the token-wide contract and object-level policy according to your design.

### Mistake G — Granting `ROLE_ADMIN` Whenever an Arbitrary Claim Exists

Never escalate authorities on your own. Only map permissions granted by the AS and allowed by policy.

### Mistake H — Caching Active Tokens Indefinitely

Revoked tokens may remain accepted for too long. TTL and invalidation are security decisions, not just performance tuning.

### Mistake I — Logging Raw Bearer Tokens for Debugging

A token is a reusable credential. Log request IDs and error conditions instead of the token string.

### Mistake J — Reading the Introspection URL from the Token

This can cause SSRF and trust an attacker's AS. The endpoint must come from trusted configuration.

### Mistake K — Using the Wrapper to Check Ownership of an Order ID

A token-wide wrapper is not suited for object-specific authorization. Order permissions belong in the service/domain layer.

### Mistake L — Treating 401 and 403 Responses as Identical

401 is typically an authentication/token failure; 403 means authenticated but lacking endpoint/object permissions. Inspect the right layer.

### Mistake M — Disabling Validation When Upgrading the AS

If the AS changes the format of `aud`, `exp`, or `tenant_id`, review the contract and conversion code—do not remove checks to suppress errors.

### Mistake N — Sharing One Contract Across Issuers with Different Claim Meanings

Issuer A's `tenant_id` claim does not necessarily share a namespace with Issuer B. Mapping and policy must be explicit per issuer.

## 30. Example Separating Three Policies for an Endpoint

Suppose the endpoint is:

```http
GET /api/orders/order-42
Authorization: Bearer <OPAQUE_TOKEN>
```

**Policy 1 — Token contract (wrapper):**

```text
delegate.introspect(token) succeeds
AND aud contains orders-api
AND iss matches trusted issuer, if contract requires iss
AND client_id allowed
AND tenant_id well formed
AND exp valid when contract requires it
```

**Policy 2 — HTTP action authorization:**

```text
Authentication has SCOPE_orders.read
```

**Policy 3 — Object authorization:**

```text
order-42 belongs to an allowed tenant
AND (caller is owner OR is permitted through ACL/support assignment)
```

The three policies address three different failure modes:

- A token belonging to another API.
- A token for the right API without read permission.
- A token with read permission targeting an order that does not belong to the caller.

This structure enables least privilege and consistent incident analysis.

## 31. References

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): configuring introspection and customizing `OpaqueTokenIntrospector`.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): introspection interface contract.
- [Spring Security API — NimbusOpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/NimbusOpaqueTokenIntrospector.html): delegate implementation for supported versions.
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): attributes, principal name, and authorities.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection request/response structure, protected resources, and returned information.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token transport, authentication/authorization errors.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): requesting tokens targeted at the appropriate resource.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, scopes, and authorization.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): per-object API authorization.

**Conclusion:** Wrapping `OpaqueTokenIntrospector` with a decorator lets a Resource Server **preserve standard Authorization Server introspection** while adding contract-based constraints such as audience, issuer, client, tenant, time, or profile. The wrapper must **fail closed** when the delegate or a rule fails, keep authorities intact unless there is a contracted reason to change them, never log bearer credentials, and never fabricate claims to legitimize an invalid token. Once the token is authenticated, HTTP/method authorization and service-level object policy still determine **which endpoints and objects** the caller may operate on.
