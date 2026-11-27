# `DelegatingOAuth2TokenValidator` and Composing Validators

When building a **Spring Security OAuth 2.0 Resource Server**, a JWT access token needs more than a valid signature. The API must also confirm that the token was issued by the right **issuer**, targets the right **audience**, is within its valid time window, and satisfies specific claim conditions defined by the access contract. In Spring Security, these rules can be expressed as `OAuth2TokenValidator<Jwt>` implementations and combined using **`DelegatingOAuth2TokenValidator`**.

This lesson aims to show how to **compose multiple independent checks into a maintainable validation chain**, preserve default validators when adding custom ones, and separate **token-validity checks** from **resource-access authorization**. It sits within the *Claim Validation* chapter of the *Spring Security OAuth 2.0 OIDC Resource Server* module, primarily illustrated with a **JWT Resource Server on Servlet/Spring MVC** alongside a comparison with WebFlux.

> Issuer URIs, audiences, tokens, and clients in examples are for learning purposes only. Production systems must align token profiles and validation policies with the Authorization Server. Never send an ID token in place of an OAuth access token to a Resource Server.

## 1. Why Compose Multiple Checks?

Suppose a system has two APIs trusting the same Authorization Server:

~~~text
Issuer:      https://login.example.test/realms/company

Orders API:
  audience:  orders-api
  scopes:    orders.read, orders.create

Billing API:
  audience:  billing-api
  scopes:    invoices.read, invoices.pay
~~~

A token may be validly signed with the issuer's key while carrying `aud=billing-api`. If the Orders API only verifies signature and issuer while omitting audience, it risks accepting tokens minted for another API. Conversely, a token with the right audience that has expired must also be rejected.

Instead of one monolithic validation method, separate concerns:

| Condition | Validator / Responsible Layer | Question Answered |
|---|---|---|
| Signature, key, and JWS algorithm | `JwtDecoder` / JOSE library | Was the token signed with a trusted key and allowed algorithm? |
| Issuer | Issuer validator, e.g., from `JwtValidators.createDefaultWithIssuer(...)` | Did it come from the trusted Authorization Server? |
| Timestamps `exp`, `nbf` | Timestamp validator | Has the token expired or is it not yet valid? |
| Audience `aud` | Custom audience validator or framework support | Is the token intended for this API? |
| Required tenant/client/profile claims | Contract-specific custom validator | Does the token carry all attributes required by this system? |
| Scopes and record-level permissions | `JwtAuthenticationConverter` and authorization | Is the principal allowed to perform this specific request? |

**`DelegatingOAuth2TokenValidator` composes claim/token validators**—it does not replace cryptographic signature verification and does not grant `GrantedAuthority` instances. Respecting this boundary lets policies evolve without weakening the authentication pipeline.

## 2. Where Validators Fit in the Servlet Resource Server Flow

The client sends a token in the header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Overview of the processing flow:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder"]
    E --> F["JWS verification: algorithm + trusted key"]
    F --> G["DelegatingOAuth2TokenValidator<Jwt>"]
    G --> H["Defaults/timestamps + issuer"]
    G --> I["Audience"]
    G --> J["Custom claim/profile"]
    H --> K{"All checks pass?"}
    I --> K
    J --> K
    K -->|No| L["JwtValidationException / Authentication failure"]
    K -->|Yes| M["Verified Jwt"]
    M --> N["JwtAuthenticationConverter"]
    N --> O["JwtAuthenticationToken + GrantedAuthority"]
    O --> P["Authorization rules"]
    P --> Q["Controller / service if authorized"]
~~~

Important logical order:

1. `BearerTokenAuthenticationFilter` extracts the JWT from the HTTP request.
2. `JwtAuthenticationProvider` delegates verification to `JwtDecoder`.
3. The decoder checks cryptography/JWS and runs the configured claim validators.
4. Only after the token passes validation does `JwtAuthenticationConverter` convert `scope`, `scp`, or relevant claims into authorities.
5. `SecurityFilterChain` and business policies decide whether the request may access the API and specific record.

If validation fails, never construct a "temporary" authentication and bypass the error. Being able to JSON-decode a token never makes its claims trustworthy.

## 3. The `OAuth2TokenValidator<T>` Interface

Spring Security models token validation through this interface:

~~~java
public interface OAuth2TokenValidator<T extends OAuth2Token> {
    OAuth2TokenValidatorResult validate(T token);
}
~~~

For JWTs, you typically write:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    // Read claims already decoded by the decoder.
    // Return success or failure.
};
~~~

Related APIs:

| API | Meaning |
|---|---|
| `OAuth2TokenValidator<Jwt>` | A validation rule over a `Jwt` |
| `OAuth2TokenValidatorResult.success()` | Token satisfies the rule |
| `OAuth2TokenValidatorResult.failure(...)` | Token fails, carrying one or more `OAuth2Error` values |
| `OAuth2Error` | Holds error code, brief description, and optional error URI |
| `DelegatingOAuth2TokenValidator<Jwt>` | Combines multiple validators into one composite validator |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Creates the standard default validators including issuer |
| `NimbusJwtDecoder.setJwtValidator(...)` | Sets the validator used by the decoder after JWS verification |

### 3.1. A Minimal Audience Validator

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "JWT audience does not include orders-api",
            null
        )
    );
};
~~~

If `aud` does not include `orders-api`, the validator returns failure. It **does not verify signatures**, **does not check scopes**, and **does not attach itself to the decoder** just by being declared in a Java variable. It must be wired into `JwtDecoder` as shown in later sections.

Per JWT (RFC 7519), `aud` can be a single string or an array of strings. `Jwt.getAudience()` lets application code inspect the normalized list of audiences. If a token lacks an audience, this sample rule rejects it under the Orders API contract.

### 3.2. `OAuth2Error` Is Not Directly an HTTP Response

When validation fails, `OAuth2Error` becomes part of the authentication error raised by the decoder/provider. The Resource Server typically handles invalid Bearer tokens with HTTP **401 Unauthorized**. Having a custom `OAuth2Error` **does not** mean the framework automatically sends that exact raw description to end users.

Never put raw tokens, client secrets, key material, or sensitive user data inside `description`. Deep operational details belong in secured observability systems, not public responses.

## 4. How `DelegatingOAuth2TokenValidator` Composes Checks

`DelegatingOAuth2TokenValidator<T>` itself implements `OAuth2TokenValidator<T>`. It takes a collection of validators and runs them against the token. The composite validator considers a token valid **only when every member validator succeeds**.

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        validatorA,
        validatorB,
        validatorC
    );
~~~

Logical semantics:

~~~text
Token valid
  = validatorA valid
    AND validatorB valid
    AND validatorC valid
~~~

In standard Spring Security implementations, errors from member validators are aggregated into a failure result rather than stopping once any single validator succeeds. **Never design policies assuming "first matching validator stops" or "passing one validator is enough".**

~~~mermaid
flowchart LR
    T["JWS-verified JWT"] --> V1["Issuer + timestamps"]
    T --> V2["Audience"]
    T --> V3["Required claims"]
    V1 --> R["DelegatingOAuth2TokenValidator"]
    V2 --> R
    V3 --> R
    R -->|"All validators succeed"| S["success"]
    R -->|"At least one failure"| F["failure (OAuth2Error)"]
~~~

### 4.1. Not an OR Combinator

An application might need to accept **audience A or B**. If you write:

~~~java
new DelegatingOAuth2TokenValidator<>(
    requireAudienceA,
    requireAudienceB
);
~~~

that requires **both audience A and audience B**, not "A or B". When policy genuinely permits either one, express the OR logic **inside a single validator**:

~~~java
Set<String> acceptedAudiences = Set.of("orders-api", "orders-api-v2");

OAuth2TokenValidator<Jwt> acceptedAudience = jwt -> {
    boolean matched = jwt.getAudience().stream()
        .anyMatch(acceptedAudiences::contains);
    return matched
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null));
};
~~~

This snippet requires importing `java.util.Set`. These two audiences are **pre-approved** resource IDs, never strings taken from an incoming request. If policy forbids multi-audience tokens, add an explicit constraint (e.g., exactly one audience in the list) rather than accepting arbitrary sets.

### 4.2. Validator Composition Can Be Nested

`JwtValidators.createDefaultWithIssuer(...)` returns an `OAuth2TokenValidator<Jwt>` that itself wraps other validators. You can pass it cleanly into an outer `DelegatingOAuth2TokenValidator`:

~~~java
OAuth2TokenValidator<Jwt> all = new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(trustedIssuer),
    audienceValidator,
    mandatoryClaimsValidator
);
~~~

This preserves all default checks while adding Orders API-specific requirements as clean, independent components.

## 5. Critical Pitfall: `setJwtValidator` Replaces Rather Than Appends

`NimbusJwtDecoder.setJwtValidator(...)` sets the decoder's validator. When calling it with a custom validator, never assume the decoder keeps previously configured validators.

The following snippet can silently drop essential claim checks:

~~~java
// ANTI-PATTERN: checks only audience, losing issuer/time validators.
NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
decoder.setJwtValidator(audienceValidator);
~~~

**The decoder may still verify signatures**, yet claim validation shrinks to only audience. A JWT with the wrong `iss`, past `exp`, or future `nbf` could slip past if default validators were overwritten.

Intentional configuration:

~~~java
OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    );

decoder.setJwtValidator(combined);
~~~

**Rule:** whenever attaching custom validators, explicitly compose all mandatory checks. `JwtValidators.createDefaultWithIssuer(issuer)` is the standard starting point to preserve your Spring Security version's default checks and issuer constraint. If your application adheres to a specific token profile (such as RFC 9068 JWT access tokens), include any additional profile validators required by contract.

Do not rely on "YAML already has `issuer-uri`" to magically inject an issuer validator onto a **custom `JwtDecoder` bean you define yourself**.

## 6. Complete Example: Issuer + Timestamps + Audience in `JwtDecoder`

Suppose the Orders API contract is:

~~~text
Trusted issuer:  https://login.example.test/realms/company
Trusted JWKS:    https://login.example.test/realms/company/protocol/openid-connect/certs
Expected aud:    orders-api
Allowed JWS alg: RS256
GET scope:       orders.read
~~~

First add Servlet dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Put the values in `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` are **application-defined** properties, not Spring Boot auto-configuration properties. They are injected into the bean below.

### 6.1. `JwtDecoder` Bean Retaining Defaults + Issuer and Adding Audience

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token is not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

Walkthrough:

1. `withJwkSetUri(jwksUri)` specifies the trusted **public keys** source for JWS verification. The JWK Set URI must come from issuer operator configuration, never an arbitrary JWT header.
2. `jwsAlgorithm(RS256)` restricts the algorithm for this example. Real contracts may use other algorithms; enable only approved ones.
3. `JwtValidators.createDefaultWithIssuer(issuer)` preserves standard default checks (notably issuer and timestamps).
4. `expectedAudience` requires `aud` to include this API's identifier.
5. `DelegatingOAuth2TokenValidator` combines conditions with logical AND.
6. `setJwtValidator(...)` sets the **complete validator chain**, not audience alone.

If the decoder fails signature verification or any validator fails, `JwtAuthenticationProvider` does not create an authenticated `JwtAuthenticationToken` for the request.

### 6.2. Integrating with the Servlet `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

When the application registers a `JwtDecoder` bean, Spring Boot normally skips creating its default decoder bean. The HTTP security chain above picks up the context bean. If you wire a different decoder directly via `jwt.decoder(...)` on a chain, verify that **the directly wired instance** carries the same validator set; never assume every chain automatically shares the bean above.

Spring Security by default maps `scope="orders.read"` to authority `SCOPE_orders.read`. Passing issuer/audience/timestamp validation **does not automatically grant permission to read or create orders**. Authorities and data-ownership policies must still be enforced in subsequent layers.

### 6.3. Using Issuer Discovery Instead of a Fixed JWKS URI

If you want the decoder to resolve the JWK Set from the trusted issuer's metadata, the builder can use:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience
    )
);
~~~

This is an **alternative way to construct the decoder** from Section 6.1, not a second bean. Discovery uses the configured trusted issuer; never dynamically download metadata from an unverified JWT's `iss` claim.

## 7. Writing Custom Validators for Other Claims

Beyond issuer, timestamps, and audience, an API may enforce domain-specific constraints. For instance, a multi-tenant Orders API might require every token to carry a tenant ID, belong to an allowlisted client, or not exceed a maximum age from issuance. These rules must derive from the **Authorization Server contract**, never guessed from a sample token.

### 7.1. Requiring a Claim to Exist

Suppose the Orders API profile requires every token to carry `exp`. Distinguish two questions:

- If `exp` **is present**, the timestamp validator checks whether the token has expired.
- If `exp` **is absent**, should the application immediately reject the token as invalid?

If `exp` is mandatory, add a validator:

~~~java
OAuth2TokenValidator<Jwt> expiryRequired = jwt -> {
    if (jwt.getExpiresAt() != null) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required exp claim is missing",
            null
        )
    );
};
~~~

Then compose:

~~~java
OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience,
        expiryRequired
    );

decoder.setJwtValidator(combined);
~~~

A token with valid `exp` yet wrong `iss` is still rejected. A token with valid `iss` yet missing `exp` is also rejected under that contract. **Never replace a claim-semantics validator with a mere presence validator.**

### 7.2. Checking That the Client Belongs to an Allowlist

A Resource Server might accept access tokens issued only to approved clients:

~~~java
import java.util.Set;

Set<String> allowedClients = Set.of(
    "orders-web",
    "orders-mobile"
);

OAuth2TokenValidator<Jwt> allowedClient = jwt -> {
    String clientId = jwt.getClaimAsString("client_id");
    if (clientId != null && allowedClients.contains(clientId)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Client is not allowed for Orders API",
            null
        )
    );
};
~~~

`client_id` is not mandatory in every JWT profile. If the issuer uses another claim or represents clients differently, adjust the contract accordingly. Likewise, an `azp` claim in an OIDC ID token **does not automatically serve as `client_id` in every access token**.

### 7.3. Requiring a Valid Tenant ID

Suppose every Orders API token must carry a `tenant_id` belonging to onboarded tenants:

~~~java
Set<String> knownTenants = Set.of("tenant-a", "tenant-b");

OAuth2TokenValidator<Jwt> knownTenant = jwt -> {
    String tenant = jwt.getClaimAsString("tenant_id");
    if (tenant != null && knownTenants.contains(tenant)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Tenant claim is invalid",
            null
        )
    );
};
~~~

This checks **whether the token belongs to a contractually recognized tenant**. It **does not** verify whether the caller may read a particular order inside `tenant-a`. In controllers and services, compare the verified tenant against the target resource's tenant and data permissions.

If the tenant list changes frequently, hardcoding it in the decoder is impractical; you may need a centrally managed tenant-trust registry. Account for config caching, tenant offboarding, and stale state.

### 7.4. Capping Token Age Using `iat`

For sensitive endpoints, the contract may require JWTs issued recently, even if `exp` is still far away. A simple condition:

~~~text
issued-at (iat) must be present
AND iat is not in the future beyond allowed clock skew
AND now - iat <= maximum token age
~~~

Illustrative validator:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Duration maxAge = Duration.ofMinutes(15);
Duration skew = Duration.ofSeconds(60);

OAuth2TokenValidator<Jwt> tokenAge = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant now = clock.instant();

    boolean valid = issuedAt != null
        && !issuedAt.isAfter(now.plus(skew))
        && !issuedAt.isBefore(now.minus(maxAge).minus(skew));

    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Token age is not allowed", null));
};
~~~

This validator **does not replace `exp`/`nbf` checks**; it adds a `iat`-based cap. Fifteen minutes and sixty seconds are illustrative values, not framework defaults. For deterministic tests, inject a `Clock` into the configuration bean instead of hardcoding `Clock.systemUTC()` inside the rule.

### 7.5. Composing Independent Validators Together

When an API enforces multiple rules:

~~~java
OAuth2TokenValidator<Jwt> allRules =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience,
        expiryRequired,
        allowedClient,
        knownTenant,
        tokenAge
    );

decoder.setJwtValidator(allRules);
~~~

This is an **assembly snippet** assuming those validator variables are defined in the same config and genuinely belong to the Orders API contract. Never pile on validators just because you can write them: every extra required claim can break valid clients if the Authorization Server has not committed to emitting it.

## 8. `JwtClaimValidator` and Built-In Spring Security Validators

Not every validator needs a custom lambda from scratch. Spring Security ships helpful implementations:

| Class / Method | Purpose |
|---|---|
| `JwtIssuerValidator` | Validates issuer |
| `JwtTimestampValidator` | Validates time validity |
| `JwtClaimValidator<T>` | Validates a single claim with an application-provided predicate |
| `JwtValidators.createDefault()` | Provides version-appropriate default validations |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Default validations plus issuer check |
| `DelegatingOAuth2TokenValidator<Jwt>` | Composes multiple validators requiring all to pass |

### 8.1. Using `JwtClaimValidator` for Audience

This example expresses the audience check as a predicate:

~~~java
import java.util.List;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;

OAuth2TokenValidator<Jwt> audienceRule =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        aud -> aud != null && aud.contains("orders-api")
    );
~~~

`JwtClaimValidator` takes a **claim name** and a predicate. For audience, pay attention to the post-conversion claim type produced by Spring Security: custom setups might yield a different type or missing claim. When issuer profiles vary, writing a validator directly over `Jwt.getAudience()` often states intent more clearly.

### 8.2. What If You Need to Adjust Clock Skew?

`JwtTimestampValidator` accepts a clock skew duration:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestamps =
    new JwtTimestampValidator(Duration.ofSeconds(45));
~~~

**Never casually append a new timestamp validator next to a default timestamp validator assuming it replaces the default skew.** If both run, the JWT must satisfy both simultaneously; whichever has the smaller skew still dominates.

When overriding default timestamp behavior, inspect the exact validator set used by your Spring Security version and assemble the final validator chain while preserving issuer, audience, token profile, and any other defaults. Simply adding a timestamp validator to `DelegatingOAuth2TokenValidator` never reconfigures an existing timestamp validator.

### 8.3. Using `JwtValidators.createDefaultWithIssuer` to Avoid Missing Checks

Instead of:

~~~java
// May omit other default rules depending on version/profile.
new DelegatingOAuth2TokenValidator<>(
    new JwtIssuerValidator(issuer),
    myAudienceValidator
);
~~~

prefer starting with:

~~~java
new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    myAudienceValidator
);
~~~

The second form makes intent explicit: **keep the framework's default validations** and add audience. Profile-specific rules—such as requiring `exp` presence, RFC 9068 `typ`, `client_id`, or tenant—still must be agreed upon separately and added as corresponding validators.

## 9. Boundary Between JWT Claim Validation and Authorization

A verified JWT might contain:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

In the Orders API, there are two decision layers:

**Authentication / validation layer**:

~~~text
Valid signature and trusted key?
Right issuer?
Not expired? Reached nbf?
Token issued for orders-api?
Required tenant/client/profile valid?
          |
          v
      Jwt accepted
~~~

**Authorization layer**:

~~~text
Does GET /api/orders/42 require SCOPE_orders.read?
Does the token carry that scope?
Which subject/tenant owns order 42?
May this user/service view this exact record?
          |
          v
    Allow or deny request
~~~

### 9.1. Never Use Token Validators for Arbitrary URL Checks

A JWT validator normally has no direct view of the HTTP path, method, or target database record. To specify which scope `GET /api/orders/**` requires, use `authorizeHttpRequests` or method security. To check record owner or tenant, use service/domain authorization.

Writing a JWT validator that peeks at request state via static or global variables makes security policies brittle and unsafe under concurrent requests.

### 9.2. Never Use a Converter to Bypass Validators

`JwtAuthenticationConverter` maps `scope` to `SCOPE_orders.read`, yet it runs only on JWTs accepted by the decoder. A matching `scope` **never compensates** for a wrong audience or wrong issuer. A converter must never "repair" a token by rewriting `iss`/`aud` or minting authorities for an unverified token.

### 9.3. Distinguishing `401` and `403`

| Case | Failing Stage | Typical HTTP Status |
|---|---|---|
| Invalid JWT signature | Decoder/JWS | 401 |
| Expired JWT | Token validator | 401 |
| JWT with `aud=billing-api` sent to Orders API | Audience validator | 401 |
| JWT `iss` not from trusted issuer | Issuer validator | 401 |
| Valid JWT lacking `orders.read` | HTTP/method authorization | 403 |
| Valid JWT with scope, caller does not own the order | Domain authorization | 403 or 404 depending on policy |

Spring Security can return RFC 6750 Bearer challenges:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Exact challenge headers depend on exception handlers, security configuration, and the request. An upstream outage reaching JWKS/issuer may yield a different status than an invalid JWT; **never allow unverified requests through when upstream dependencies fail**.

## 10. When to Compose AND, OR, or Dependent Conditions

`DelegatingOAuth2TokenValidator` is the natural choice when independent conditions must **all pass**:

~~~text
valid issuer
AND valid timestamps
AND valid audience
AND valid token profile
~~~

Special policy shapes require care:

**OR across values of the same claim**:

~~~text
aud contains orders-api
OR aud contains orders-api-v2
~~~

Express this inside **one audience validator** backed by an allowlist set.

**Mutual dependency between two claims**:

~~~text
If grant_type == client_credentials
    → client_id must be in approved service group.
If token represents an end-user
    → sub must be present per profile.
~~~

Express this in a single validator inspecting both claims with conditional logic. Never wire both `requireServiceClient` and `requireEndUser` into `DelegatingOAuth2TokenValidator` if the two conditions are mutually exclusive across token kinds.

**Multiple issuers**:

~~~text
Issuer A → decoder/JWKS/policy A
Issuer B → decoder/JWKS/policy B
~~~

Never combine `JwtIssuerValidator(issuerA)` and `JwtIssuerValidator(issuerB)` via AND when valid tokens come from **either** issuer. Instead, use a resolver or registry of **trusted** issuers and apply the appropriate validator suite per issuer. An unverified `iss` claim may only select from a strict allowlist, after which signature and issuer are verified against the matching key source.

## 11. Multiple Validation Errors and Error Propagation

A single JWT can violate several rules simultaneously, e.g.:

~~~json
{
  "iss": "https://unknown-issuer.example.test",
  "aud": ["billing-api"],
  "exp": 1700000000,
  "client_id": "unknown-client"
}
~~~

Suppose the signature passed against a test key source and the API enforces issuer, timestamp, audience, and client rules. Running `DelegatingOAuth2TokenValidator`, each failing validator produces an error:

~~~text
issuer validator       → invalid_token
timestamp validator    → invalid_token
audience validator     → invalid_token
allowed client         → invalid_token
              |
              v
DelegatingOAuth2TokenValidator
              |
              v
OAuth2TokenValidatorResult.failure([...])
~~~

In Spring Security, `OAuth2TokenValidatorResult` can carry **multiple `OAuth2Error` entries**, not just one. Each validator simply returns `success()` when its own rule passes or `failure(...)` when it fails.

### 11.1. Inspecting `OAuth2TokenValidatorResult`

Illustrative check on a single validator:

~~~java
OAuth2TokenValidatorResult result = audienceValidator.validate(jwt);

if (result.hasErrors()) {
    for (OAuth2Error error : result.getErrors()) {
        // Handle error details per internal policy.
        // Never log the raw JWT.
        String code = error.getErrorCode();
    }
}
~~~

Here `jwt` represents a `Jwt` under inspection in illustrative code. **Never manually decode an unverified payload inside an HTTP endpoint, invoke a validator directly, and treat it as complete JWT authentication.** In a running Resource Server, let `JwtDecoder` handle JWS verification and validator execution.

### 11.2. Never Depend on Error Ordering for Business Policy

Because multiple validators can fail at once, never rely on "which error appears first" to decide whether a request continues. Any mandatory validation failure rejects the JWT. Errors can be categorized cleanly:

| Error Category | Operational Use | Public Response |
|---|---|---|
| `invalid_token` for issuer | Verify trusted issuer config | Do not expose infrastructure internals |
| `invalid_token` for audience | Verify client/AS resource ID | Do not publish internal audience lists |
| `invalid_token` for timestamps | Check TTL and clock sync | Standard Bearer challenge |
| `invalid_token` for custom claim | Check token profile/issuer mapping | Avoid echoing sensitive claim values |

Never include the raw JWT payload or `Authorization` header in exception messages. For observability, record **normalized reason categories**, request IDs, and non-sensitive context.

### 11.3. What Does Fail-Closed Mean?

If a validator throws due to a bug, the decoder cannot load the JWK Set, or validation cannot conclude safely, the request must never fall through to a controller as an authenticated principal.

That does not mean every infrastructure outage must masquerade as an expired-JWT response. A network failure reaching a JWK endpoint may map to a **service error** depending on configuration; the invariant is **never accepting an unverified token**.

## 12. Customizing `JwtDecoder` Does Not Mean Rewriting Every Validator from Scratch

An API may only need:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

When using the auto-configured decoder, Spring Security applies the issuer/timestamp checks provided by that configuration. If your framework version supports configuring audience via official properties, you can prefer that to minimize custom code.

Conversely, if your application defines:

~~~java
@Bean
JwtDecoder decoder() {
    // Custom decoder.
}
~~~

Spring Boot normally **stops creating the default `JwtDecoder` bean** once a user-defined bean exists. Your custom code must therefore explicitly declare **key sources, algorithms, issuer/timestamp checks, and custom validators**. Leaving properties in YAML does not guarantee a custom bean loads all of them automatically.

### 12.1. Wiring Rules at the Right Layer

~~~mermaid
flowchart TD
    A["Need to add a check to Resource Server"] --> B{"What kind of check?"}
    B -->|"Signature / algorithm / key"| C["Configure JwtDecoder / JOSE"]
    B -->|"iss, exp, nbf, aud, token profile"| D["OAuth2TokenValidator<Jwt>"]
    B -->|"scope, role → authorities"| E["JwtAuthenticationConverter"]
    B -->|"HTTP operation / method"| F["SecurityFilterChain / method security"]
    B -->|"Record owner, tenant"| G["Service/domain authorization"]
    D --> H["DelegatingOAuth2TokenValidator + default validators"]
~~~

A small validator change can impact many OAuth 2.0 clients and flows. For instance, requiring `client_id` on every token when the issuer still mints some valid token profiles without it will break existing callers. Publish new requirements in the **token contract** before enforcing them.

### 12.2. Can You Use `JwtClaimValidator` Without Creating a Decoder Bean?

That depends on how your framework version exposes validator customization. A standalone `JwtClaimValidator` bean or variable that is never attached to a decoder **has no effect on authentication**. If you customize or replace a decoder to add validators, verify that the security filter chain actually uses that decoder—especially when multiple security chains exist.

The goal is not having extra beans in the application context, but ensuring **every request to protected endpoints goes through a decoder enforcing the contract validators**.

## 13. Using the Same Composition Pattern on Spring WebFlux

A Spring WebFlux Resource Server uses `ReactiveJwtDecoder` instead of synchronous `JwtDecoder`. Yet **claim validators still implement `OAuth2TokenValidator<Jwt>`**, and composition works identically.

Typical dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example reactive decoder bean (assuming `app.security.jwt.*` from Section 6):

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ReactiveOrdersDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceRule = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is invalid",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceRule
            )
        );

        return decoder;
    }
}
~~~

Example `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

These snippets belong to the **WebFlux stack** as the reactive equivalent, not code to mix into a Servlet config. Spring Security wires `ReactiveJwtDecoder` from the context when configured properly.

**WebFlux note:** `OAuth2TokenValidator<Jwt>` is a synchronous check over in-memory claims. Never perform blocking HTTP calls to external services inside a validator lambda in a Reactive Resource Server, as doing so blocks the event loop. If policy requires external lookups, design an asynchronous check/authorization layer or reactive trust mechanism suited to WebFlux.

### Comparison Table

| Aspect | Servlet / Spring MVC | WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Decoder | `JwtDecoder` / `NimbusJwtDecoder` | `ReactiveJwtDecoder` / `NimbusReactiveJwtDecoder` |
| Claim validator | `OAuth2TokenValidator<Jwt>` | `OAuth2TokenValidator<Jwt>` |
| Composition | `DelegatingOAuth2TokenValidator<Jwt>` | `DelegatingOAuth2TokenValidator<Jwt>` |
| Decoder custom API | `setJwtValidator(...)` | `setJwtValidator(...)` |
| Resulting authentication | `JwtAuthenticationToken` | `JwtAuthenticationToken` in reactive security context |

Issuer, audience, timestamp, and token-profile rules **do not change** when moving from Servlet to WebFlux.

## 14. Opaque Tokens and `OAuth2TokenValidator`: Do Not Mix Pipelines

`DelegatingOAuth2TokenValidator<Jwt>` composes checks on `Jwt` objects. By contrast, an **opaque token** is typically validated via an **introspection endpoint** using `OpaqueTokenIntrospector` or `ReactiveOpaqueTokenIntrospector`.

~~~text
JWT access token:
    JwtDecoder
      → JWS validation
      → OAuth2TokenValidator<Jwt>
      → JwtAuthenticationToken

Opaque access token:
    OpaqueTokenIntrospector
      → HTTP introspection to trusted AS
      → active + attributes + authorities
      → BearerTokenAuthentication
~~~

If an application uses `oauth2ResourceServer(o -> o.opaqueToken(...))`, defining a `DelegatingOAuth2TokenValidator<Jwt>` bean **does not make introspection automatically check audience or tenant**. Enforce policies at the introspection provider or customize the introspector around the attributes returned by the Authorization Server.

Conversely, a JWT decoder checking `iss`/`aud` does not replace OAuth 2.0 Token Introspection. Both approaches can share the same **access contract**, yet their verification mechanisms and extension points differ.

## 15. Illustrating Standalone Validator Checks

The examples in this section show how a validator inspects claims on an existing `Jwt`—**not** real JWT signature verification. In a running application, only `JwtDecoder` backed by a trusted key source determines whether an incoming HTTP token is authentic.

### 15.1. Constructing a Sample `Jwt` for Validator Logic

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

Instant now = Instant.parse("2026-11-15T10:00:00Z");

Jwt exampleJwt = Jwt.withTokenValue("for-validator-example-only")
    .header("alg", "RS256")
    .issuer("https://login.example.test/realms/company")
    .subject("user-123")
    .audience(java.util.List.of("orders-api"))
    .issuedAt(now.minusSeconds(60))
    .notBefore(now.minusSeconds(60))
    .expiresAt(now.plusSeconds(600))
    .claim("scope", "orders.read")
    .build();
~~~

`Jwt.withTokenValue(...)` constructs a Java object for logic demonstration. **It does not sign a token, does not prove a signature, does not perform HTTP discovery**, and `"for-validator-example-only"` is not a Bearer JWT accepted by any API. The fixed `now` illustrates claim checks; when running a real timestamp validator, it reads its configured clock, so timestamps or clocks must be aligned in test setups.

### 15.2. Illustrating Audience Validator Outcomes

~~~java
OAuth2TokenValidator<Jwt> audienceRule = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

OAuth2TokenValidatorResult goodResult =
    audienceRule.validate(exampleJwt);

// goodResult.hasErrors() == false
~~~

Changing the audience:

~~~java
Jwt wrongAudience = Jwt.withTokenValue("example-wrong-audience")
    .header("alg", "RS256")
    .claim("iss", "https://login.example.test/realms/company")
    .claim("sub", "user-123")
    .claim("aud", java.util.List.of("billing-api"))
    .issuedAt(now.minusSeconds(60))
    .expiresAt(now.plusSeconds(600))
    .build();

OAuth2TokenValidatorResult wrongResult =
    audienceRule.validate(wrongAudience);

// wrongResult.hasErrors() == true
~~~

Here `wrongAudience` might have a valid issuer and timestamps in a test scenario, yet it lacks `aud=orders-api` and fails the audience rule. Note that this snippet invokes only the single validator; it **does not** check issuer, expiration, or signature here.

### 15.3. Illustrating a Composite Validator

~~~java
OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(
        "https://login.example.test/realms/company");

OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        issuerAndTime,
        audienceRule
    );

OAuth2TokenValidatorResult result = combined.validate(exampleJwt);
~~~

With real timestamp validation, the outcome depends on execution time and the validator's clock/skew. **Never hardcode a fixed year like 2026 in a long-lived test expecting the token to remain unexpired forever.** For deterministic automated tests, either compute timestamps relative to runtime or inject a controlled clock via the appropriate API.

## 16. Scenario Matrix to Document in the Contract

For the Orders API:

~~~text
Trusted issuer = https://login.example.test/realms/company
Expected aud   = orders-api
Required GET scope = orders.read
Mandatory claim = exp
Allowed client_id = orders-web or orders-mobile
~~~

| Scenario | Validator / Handling Layer | Expected Outcome |
|---|---|---|
| Valid signature, right issuer, right audience, unexpired, allowed client | Decoder + all claim validators | Token authenticated; authorization proceeds |
| Forged signature | JWS verification | Rejected before trusting claims |
| `alg` not in allowlist | JWS verification | Rejected |
| `iss` from another issuer | Default/issuer validator | Authentication rejected |
| `exp` in the past | Timestamp validator | Authentication rejected |
| Token before `nbf` | Timestamp validator | Authentication rejected |
| Missing `exp` when profile requires it | `expiryRequired` | Authentication rejected |
| `aud` contains only `billing-api` | `expectedAudience` | Authentication rejected |
| `aud` is `orders-api` but `client_id` disallowed | `allowedClient` | Authentication rejected |
| Missing `tenant_id` when required by API | `knownTenant` | Authentication rejected |
| `iat` too old relative to max age | `tokenAge` | Authentication rejected |
| Wrong issuer **and** wrong audience | Multiple validators | Composite returns failure |
| Valid JWT missing `orders.read` | Authorization via `SCOPE_orders.read` | Typically `403` |
| Valid JWT with scope, order not owned by principal | Business authorization | Denied per policy |

A test using `SecurityMockMvcRequestPostProcessors.jwt()` is great for testing HTTP `hasAuthority(...)` rules, yet it normally **bypasses the real decoder**. It therefore does not prove signatures, issuer, audience, timestamps, or `DelegatingOAuth2TokenValidator` actually executed.

To verify end-to-end, use **real signed test JWTs** paired with test public JWKs configured on `JwtDecoder`, sent via `Authorization: Bearer` to the application. Test bad issuer/audience/timestamps and invalid signatures as distinct cases. Never use production private signing keys in tests.

## 17. An Extensible Code Organization Pattern

As an API's contract grows, avoid dumping all validator lambdas directly inside the decoder bean. Instead, encapsulate each validator into a focused class or factory.

Example reusable audience validator:

~~~java
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ApiAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public ApiAudienceValidator(String expectedAudience) {
        this.expectedAudience =
            Objects.requireNonNull(expectedAudience);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT audience is not accepted",
                null
            )
        );
    }
}
~~~

The decoder bean stays focused on wiring the conditions:

~~~java
OAuth2TokenValidator<Jwt> validation =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new ApiAudienceValidator(audience),
        expiryRequired
    );

decoder.setJwtValidator(validation);
~~~

Benefits of this organization:

- Each rule states a single clear condition and rejection reason.
- Easy to assemble tailored validator chains per Resource Server.
- Cleanly separates **mandatory token conditions** from downstream authorities and policies.
- When introducing a custom claim, you can evaluate its impact on existing token profiles independently.

Still, never turn a pure data validator into a place that queries databases, makes external HTTP calls, or mutates `SecurityContextHolder`. Policies needing request details or record permissions belong in the authorization layer.

### 17.1. Configuring Applications with Multiple Resource Servers or Multiple Issuers

A platform may expose multiple APIs or trust multiple issuers. Validator sets must maintain **exact boundaries**:

~~~text
Orders API:
  iss = issuer-A
  aud = orders-api
  required claims = orders profile

Billing API:
  iss = issuer-A
  aud = billing-api
  required claims = billing profile

Partner API:
  iss = issuer-B (allowlisted)
  aud = partner-api
  required claims = partner profile
~~~

Never share one audience validator accepting **every API audience** just because services share an issuer. If an app has multiple security chains, verify matchers select the right decoder and policy. With multiple issuers, select the right trusted decoder/JWK source first before applying claim validators.

## 18. Common Configuration Mistakes

### 18.1. Adding Audience While Losing Timestamp Validation

~~~java
// Wrong if this becomes the sole validator after overriding:
decoder.setJwtValidator(new ApiAudienceValidator("orders-api"));
~~~

Always compose `JwtValidators.createDefaultWithIssuer(issuer)` or equivalent defaults **together with** audience. Dropping defaults is one of the biggest real-world risks when customizing `JwtDecoder`.

### 18.2. Using an AND Validator for Two Mutually Exclusive Issuers

~~~java
// No normal JWT has two different iss values at once:
new DelegatingOAuth2TokenValidator<>(
    new JwtIssuerValidator(issuerA),
    new JwtIssuerValidator(issuerB)
);
~~~

If the system accepts Issuer A **or** B, use an allowlisted multi-issuer architecture and verify each token using the selected issuer's own key source and validators.

### 18.3. Using an AND Validator for Two Audiences Meant as OR

~~~text
Wrong: require audience A AND require audience B
Right when policy permits either:
    audience contains A OR audience contains B
    → one audience validator with an allowlist
~~~

If policy requires a token to target only a single audience, express that constraint explicitly. Never assume multi-audience tokens are safe for every Resource Server.

### 18.4. Validating Claims Without Trusted Key Verification

A JWT asserting valid `iss`, `aud`, and `scope` is worthless if its signature was not verified using a trusted key and allowed algorithm. `DelegatingOAuth2TokenValidator` does not perform JWS verification; that belongs to the decoder/JOSE layer.

### 18.5. Treating a Missing Claim as Equivalent to a Valid Value

Example:

~~~java
// Wrong if policy requires tenant to be present:
boolean allowed = jwt.getClaimAsString("tenant_id") == null
    || knownTenants.contains(jwt.getClaimAsString("tenant_id"));
~~~

This accepts tokens missing a tenant. If the contract mandates a claim, **reject when missing**. Conversely, for profiles where a claim is optional, do not impose baseless presence requirements.

### 18.6. Using `scope` as a Global Token-Validity Condition Across All Endpoints

A token can validly hold `orders.read` without `orders.create`. If a global custom validator requires `orders.create` on every token, read-only tokens fail with `401`. Action-specific scopes belong in authorization rules, rather than turning every scope into a **universal token-validity gate**.

### 18.7. Confusing `DelegatingOAuth2TokenValidator` with `JwtAuthenticationConverter`

Validators return **valid/invalid results**, not `GrantedAuthority` instances. Converters turn verified claims into principal and authorities. They serve different purposes at different stages.

### 18.8. Defining a Validator Without Wiring It into the Active Decoder

An `OAuth2TokenValidator<Jwt>` bean or variable never attached to `JwtDecoder` has zero effect on HTTP requests. Verify where the decoder is constructed and which decoder `SecurityFilterChain` actually uses, especially in multi-chain apps.

### 18.9. Leaking Sensitive Data in Custom Validator Errors

Avoid error messages containing raw JWTs, PII claims, access tokens, signing keys, or internal IdP details. Use concise error codes and short descriptions, categorizing internal metrics per policy.

### 18.10. Trying to Replace Timestamp Validation by Appending a Duplicate Validator

If you need a new clock skew, never assume adding a second `JwtTimestampValidator` replaces the default one. Validators run with AND semantics, so rebuild the timestamp validator chain intentionally while keeping all other default rules.

## 19. Self-Check Questions

**Question 1.** Does `DelegatingOAuth2TokenValidator` combine validators with AND or OR?

With **AND**: a token is valid only when every component validator succeeds. If you need OR logic for a claim, write that OR condition inside a dedicated validator.

**Question 2.** Why can calling `setJwtValidator(audienceValidator)` be risky?

Because `setJwtValidator` replaces the decoder's validator rather than appending to existing ones. Without re-attaching default/timestamp/issuer validators, expired or wrong-issuer tokens may no longer be rejected per contract.

**Question 3.** Does `DelegatingOAuth2TokenValidator` verify RSA/ECDSA signatures itself?

No. JWS verification against trusted keys belongs to `JwtDecoder` and the JOSE layer. Claim validators run after decoder signature verification.

**Question 4.** When is an audience validator needed?

Whenever a Resource Server must verify that an access token was issued for that exact API/resource, especially when one issuer mints tokens for multiple APIs. Always use the official resource identifier from the contract.

**Question 5.** A valid token has `scope=orders.read` without `orders.create`. Should it be rejected during decoding?

Not necessarily. If both scopes are valid under the profile, the read-only token should authenticate cleanly. When calling `POST /api/orders`, HTTP authorization rejects it for lacking `SCOPE_orders.create`.

**Question 6.** Should you read an unverified `iss` claim and dynamically discover JWKS from any URL?

No. Issuers must belong to a pre-configured trusted list; decoder and key-source selection must follow policy. An unverified issuer value may only act as a routing hint inside a strictly allowlisted resolver.

**Question 7.** With opaque tokens, does adding an `OAuth2TokenValidator<Jwt>` bean make introspection validate audience automatically?

No. Opaque tokens go through `OpaqueTokenIntrospector` and require corresponding policy enforcement at introspection or inside the Resource Server.

## 20. Remembering Composition Patterns

A recognizable configuration pattern:

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new ApiAudienceValidator("orders-api"),
        extraClaimValidator
    );

decoder.setJwtValidator(validators);
~~~

Here `trustedIssuer`, `decoder`, and `extraClaimValidator` are objects/values configured per contract; the snippet illustrates structure, not a standalone class.

JWT acceptance condition at the Resource Server:

~~~text
JWT accepted
    =
    Valid signature with trusted key and allowed algorithm
    AND Right issuer
    AND Token valid in time
    AND Audience matches API
    AND Other required claims/profile valid
~~~

Followed by:

~~~text
Request authorized
    =
    Authentication succeeded
    AND Scope/authority matches HTTP action
    AND Business permissions on resource/tenant satisfied
~~~

**`DelegatingOAuth2TokenValidator` is the tool for composing independent token-validation rules**, letting you extend API requirements without cramming everything into one giant validator. Pairing it with `JwtValidators.createDefaultWithIssuer(...)` is crucial for **adding** audience, client, or token-profile checks **without accidentally dropping** default safeguards. Remember, it only takes effect when attached to the live decoder protecting the Resource Server.

## References

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security — OAuth2TokenValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
- [Spring Security — DelegatingOAuth2TokenValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html)
- [Spring Security — JwtClaimValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtClaimValidator.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
