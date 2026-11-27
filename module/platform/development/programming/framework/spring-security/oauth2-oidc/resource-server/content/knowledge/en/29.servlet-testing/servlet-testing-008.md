# Testing JwtAuthenticationConverter and Custom Validators Against the Contract

In a Spring Security Servlet Resource Server, JWT processing has two distinct responsibilities:

1. **Verifying whether the token is accepted**: signature, algorithm, issuer, expiration, audience, and conditions defined by the contract with the Authorization Server.
2. **Converting the verified JWT into an Authentication**: mapping scopes/roles into GrantedAuthorities, selecting the principal name, and producing the Authentication type the application expects.

Spring Security separates these two responsibilities into two primary components:

- `JwtDecoder` decodes, verifies the signature, and runs `OAuth2TokenValidator<Jwt>`.
- `JwtAuthenticationConverter` converts the `Jwt` accepted by the decoder into an `AbstractAuthenticationToken`; this converter typically delegates to a child converter to build the `GrantedAuthority` collection.

Therefore, testing the converter does not prove validators are right; testing validators does not prove scopes/roles are mapped properly. This article defines a concrete token contract, implements a custom converter and validators, and tests them at unit, MockMvc, and filter-chain integration levels.

> **Invariant:** Only a JWT that has passed signature verification and all validators may be converted into an Authentication. Converters must never be used to compensate for missing issuer/audience/token-profile validation. Conversely, validators should not attempt to map business permissions; they only decide whether the token satisfies the authentication contract.

## 1. Defining the JWT contract before writing tests

Suppose the Orders API receives JWT access tokens from an Authorization Server. The API's contract specifies:

| Claim/header | Example | Rule |
| --- | --- | --- |
| JOSE `alg` | `RS256` | Only accept configured signature algorithms |
| `iss` | `https://identity.example.test/realms/shop` | Must match the trusted issuer |
| `aud` | `["orders-api"]` | Must contain the Orders API audience |
| `exp` | Unix timestamp | Token is not expired |
| `nbf` | Unix timestamp | Token has reached its effective time |
| `sub` | `alice-42` | Required, non-blank |
| `scope` | `orders.read orders.cancel` | Space-delimited scope string |
| `roles` | `["ORDER_ADMIN"]` | Internal role claim per custom contract |
| `token_use` | `access` | Only access tokens are accepted |
| `tenant_id` | `tenant-A` | Required if the API requires a tenant context |

Illustrative JWT payload:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-42",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read orders.cancel",
  "roles": ["ORDER_ADMIN"],
  "token_use": "access",
  "tenant_id": "tenant-A"
}
~~~

The claim names above are an **example contract**, not all mandatory claims of OAuth 2.0/OIDC. In particular, `roles`, `token_use`, and `tenant_id` are conventions agreed upon by the Authorization Server and Resource Server. Tests must reflect the actual token profile in use; do not assume every issuer emits the same structure.

### 1.1. Three distinct converters in the pipeline

In Spring Security, the word "converter" can refer to multiple steps:

| Component | Input → output | Role | Where to test |
| --- | --- | --- | --- |
| `MappedJwtClaimSetConverter` | Claim map → normalized claim map | Converts types/adjusts claims when the decoder builds `Jwt` | Unit/decoder tests if custom mapping exists |
| `JwtGrantedAuthoritiesConverter` or custom authority converter | `Jwt` → `Collection<GrantedAuthority>` | Reads scopes/roles and produces authorities | Mapping unit tests |
| `JwtAuthenticationConverter` | `Jwt` → `AbstractAuthenticationToken` | Creates Authentication, principal, and authorities | Converter unit tests + filter-chain tests |

`JwtDecoder` also runs a validation step before the Authentication converter is called:

~~~mermaid
flowchart TD
    A["Authorization: Bearer <token>"]
    B["BearerTokenAuthenticationFilter"]
    C["JwtAuthenticationProvider"]
    D["JwtDecoder"]
    E["Verify JWS signature / trusted algorithm"]
    F["OAuth2TokenValidator<Jwt>"]
    G{"All validators succeed?"}
    H["JwtAuthenticationConverter"]
    I["Jwt -> authorities converter"]
    J["JwtAuthenticationToken / custom Authentication"]
    K["SecurityContextHolder"]
    X["Authentication failure / 401"]

    A --> B --> C --> D --> E --> F --> G
    G -->|No| X
    G -->|Yes| H --> I --> J --> K
~~~

If any validator fails, the Authentication converter should not run. This is an important assertion in integration tests: **a token with the wrong audience must be blocked before permission-mapping code executes**.

### 1.2. Distinguishing validation from authorization

| Check | Appropriate layer |
| --- | --- |
| Signature, issuer, expiration, audience, token type | JwtDecoder / OAuth2TokenValidator |
| Required claims per token contract | OAuth2TokenValidator |
| `scope` to `SCOPE_orders.read` | Granted-authorities converter |
| `roles` to `ROLE_ORDER_ADMIN` | Granted-authorities converter |
| Selecting principal name | JwtAuthenticationConverter / principal converter |
| Endpoint requiring `SCOPE_orders.read` | HttpSecurity authorization |
| User belongs to tenant and owns order | Business/resource authorization |

Do not use a converter to accept a wrong-issuer token simply because it carries the required role. Do not use a validator to decide whether Alice can read Order 42; that is a resource-level permission.

## 2. Creating converters according to the contract

### 2.1. Mapping scopes and roles separately

Suppose the Authorization Server issues `scope` per OAuth2 and `roles` per the domain contract. We want:

~~~text
scope = "orders.read orders.cancel"
    -> SCOPE_orders.read
    -> SCOPE_orders.cancel

roles = ["ORDER_ADMIN", "ORDER_AUDITOR"]
    -> ROLE_ORDER_ADMIN
    -> ROLE_ORDER_AUDITOR
~~~

Do not merge scopes and roles into a single shared namespace. `SCOPE_orders.read` denotes a delegated permission from an access token; `ROLE_ORDER_ADMIN` is an application role and must be granted/interpreted under its own contract.

Spring Security provides `JwtGrantedAuthoritiesConverter` to convert scopes or an authority claim into `GrantedAuthority`. When reading multiple claims, use `DelegatingJwtGrantedAuthoritiesConverter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.Collection;

@Configuration
class JwtAuthorityConfiguration {

    @Bean
    Converter<Jwt, Collection<GrantedAuthority>> jwtAuthoritiesConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        // Reads scope/scp and uses prefix SCOPE_ by default.

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        return new DelegatingJwtGrantedAuthoritiesConverter(
                scopes, roles);
    }
}
~~~

This snippet keeps the default `SCOPE_` prefix for scopes and adds `ROLE_` only for the `roles` claim. If the Authorization Server issues `roles` as a string instead of a collection, adjust the converter to match the actual claim type; do not silently parse arbitrary data types.

### 2.2. Do not change scope to ROLE_ just to make tests pass

`JwtGrantedAuthoritiesConverter.setAuthorityPrefix("ROLE_")` changes the prefix of authorities produced by that converter. Applying it to scopes turns `orders.read` into `ROLE_orders.read`; this mixes scopes with roles and can break `hasAuthority("SCOPE_orders.read")` rules.

Keep namespaces separate:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("ORDER_ADMIN")
~~~

`hasRole("ORDER_ADMIN")` is equivalent to checking authority `ROLE_ORDER_ADMIN`. In tests, assertions should verify exact authority strings to catch unintended prefix changes.

### 2.3. Complete Authentication converter

`JwtAuthenticationConverter` takes an authorities converter and produces a `JwtAuthenticationToken`. Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

import java.util.Collection;

@Configuration
class JwtAuthenticationConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>> authoritiesConverter) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);
        converter.setPrincipalClaimName("sub");
        return converter;
    }
}
~~~

With this configuration:

- `Authentication.getPrincipal()` defaults to the `Jwt` object.
- `Authentication.getName()` takes the value of the claim selected as principal name, here `sub`.
- `Authentication.getAuthorities()` contains scopes and roles mapped by the converter.

Do not confuse principal name with an internal user ID unless the application contract explicitly defines it. If a domain-specific principal is needed, use `setJwtPrincipalConverter(...)` or a converter returning an appropriate `AbstractAuthenticationToken`; do not mutate the `sub` claim to force it into an internal username.

### 2.4. Custom Converter when a dedicated Authentication type is needed

When the application needs to attach a tenant or a principal wrapper, you can implement `Converter<Jwt, AbstractAuthenticationToken>`:

~~~java
import java.util.Collection;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

final class ContractJwtAuthenticationConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final Converter<Jwt, Collection<GrantedAuthority>> authorities;

    ContractJwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>> authorities) {
        this.authorities = authorities;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            // This claim should be checked by a validator beforehand.
            throw new IllegalArgumentException("JWT subject is required");
        }

        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("JWT tenant_id is required");
        }

        Collection<GrantedAuthority> mapped = authorities.convert(jwt);
        return new JwtAuthenticationToken(
                jwt, mapped, subject);
    }
}
~~~

This example shows a converter selecting the principal name and authorities. In production, required claims like `sub` and `tenant_id` should be rejected by validators so every path using the decoder enforces the same contract. The converter can assume those invariants are already guaranteed; if re-checking defensively at the boundary, do not throw arbitrary business exceptions and treat that as standard validation.

Attach the converter to the Servlet filter chain:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http,
                       Converter<Jwt, AbstractAuthenticationToken> converter)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
~~~

If using the default `JwtAuthenticationConverter` bean, pass that bean into the DSL. If replacing it with a custom converter, the generic type must be compatible with the API of your Spring Security version.

## 3. Writing custom validators per the token contract

`OAuth2TokenValidator<Jwt>` takes a `Jwt` and returns an `OAuth2TokenValidatorResult`. Validators do not re-sign tokens and do not verify JWS signatures; that belongs to `JwtDecoder`. Validators inspect properties/claims after the decoder has parsed the token.

### 3.1. Preserving default validators

For a fixed issuer, `JwtValidators.createDefaultWithIssuer(issuer)` provides the default validator set, including issuer and timestamp claims such as `exp`/`nbf`. Custom validators can be composed using `DelegatingOAuth2TokenValidator`.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtClaimNames;

@Configuration
class JwtDecoderConfiguration {

    private static final String ISSUER =
            "https://identity.example.test/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        var decoder = (org.springframework.security.oauth2.jwt.NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(ISSUER);

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                    JwtClaimNames.AUD,
                    aud -> aud != null && aud.contains("orders-api"));

        OAuth2TokenValidator<Jwt> accessTokenUse =
                new JwtClaimValidator<String>(
                    "token_use",
                    "access"::equals);

        OAuth2TokenValidator<Jwt> subject =
                new JwtClaimValidator<String>(
                    JwtClaimNames.SUB,
                    sub -> sub != null && !sub.isBlank());

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audience, accessTokenUse, subject));
        return decoder;
    }
}
~~~

`setJwtValidator` replaces the validator currently attached to the decoder. Therefore, the example must compose `standard` with the custom validators. Calling only:

~~~java
decoder.setJwtValidator(customAudienceValidator);
~~~

can accidentally drop previously configured issuer/time validation. This is a very common bug when adding audience checks.

In Spring Boot, you can configure audience with property `spring.security.oauth2.resourceserver.jwt.audiences` if only a static audience allowlist is needed. Use custom validators when the contract is more complex or multiple custom claims must be checked.

### 3.2. Validator for a contract tenant claim

A custom validator can verify that a required claim has the right type and is non-blank:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class RequiredTenantClaimValidator
        implements OAuth2TokenValidator<Jwt> {

    private final OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required tenant claim is missing or invalid",
            null);

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object value = jwt.getClaims().get("tenant_id");
        if (value instanceof String tenant && !tenant.isBlank()) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Add the validator to the chain:

~~~java
OAuth2TokenValidator<Jwt> contract =
        new DelegatingOAuth2TokenValidator<>(
            standard, audience, accessTokenUse,
            subject, new RequiredTenantClaimValidator());
decoder.setJwtValidator(contract);
~~~

This validator only confirms the token carries a well-formed tenant claim. It does **not** prove the user has membership in that tenant, nor does it decide whether the user can read a specific order. Membership and resource authorization still belong to application/domain policy.

### 3.3. Distinguishing audience and scope

A token with the right scope but wrong audience must still be rejected:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

`orders.read` does not mean the token was issued for the Orders API. The audience validator must check the token's target; scope authorization only runs after authentication succeeds.

### 3.4. Checking the access-token profile and typ

Some Authorization Servers follow the **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, where token types and profile claims are strictly specified. Do not apply `typ` rules blindly to every JWT: OIDC ID tokens, access tokens, and internal JWTs have different profiles.

For RFC 9068 tokens, Spring Security provides `JwtValidators.createAtJwtValidator()`. Spring Security documentation illustrates creating a decoder with `validateTypes(false)` and then using this builder to check audience, client ID, and issuer:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .validateTypes(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createAtJwtValidator()
        .issuer(issuer)
        .audience("orders-api")
        .clientId("shop-web")
        .build());
~~~

This is a choice for the RFC 9068 profile per contract; do not copy `validateTypes(false)` into a decoder for another token profile without understanding its impact. If the Authorization Server uses a custom claim like `token_use=access`, the custom validator must reflect that exact contract.

### 3.5. Timestamps and clock skew

Spring Security uses `JwtTimestampValidator` to validate the validity window. The Resource Server's default clock skew is 60 seconds; it can be adjusted based on time synchronization requirements:

~~~java
OAuth2TokenValidator<Jwt> timeAndIssuer =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(Duration.ofSeconds(60)),
        new JwtIssuerValidator(issuer));
~~~

If building the validator chain manually, remember to keep both timestamp and issuer checks. Do not set a huge skew to hide system clock drift; synchronize via NTP and choose a tolerance matching your SLA/threat model. Tests should cover recently expired tokens, tokens before `nbf`, and tokens within the accepted skew window.

### 3.6. Validation is not claim-set mapping

`MappedJwtClaimSetConverter` runs inside the decoder to normalize/adjust claim types or content when creating `Jwt`. It differs from `OAuth2TokenValidator`:

- Claim-set converter: transforms data representation.
- Validator: decides whether the token satisfies the contract.
- Authentication converter: turns an accepted token into principal/authorities.

Never use a claim-set converter to rewrite an invalid issuer or audience into a valid value. Never map a missing claim into a default admin role.

## 4. Designing tests by layer

| Test layer | Input | Component verified | Does not prove |
| --- | --- | --- | --- |
| Authority converter unit test | Test-built Jwt | Scope/role mapping, prefix, duplicate handling | Signature/issuer/audience validation |
| JwtAuthenticationConverter unit test | Test-built Jwt | Authentication type, principal name, authorities | Real filter chain/decoder |
| Validator unit test | Test-built Jwt | Claim contract and success/failure results | JWT/JWKS signature |
| Decoder test | Real signed JWT or invalid JWT | Signature + validator chain | HTTP endpoint authorization |
| MockMvc with `jwt()` | Mock Jwt | Controller, route/method authorization, claims | JwtDecoder and signature; real Authentication converter may be bypassed |
| MockMvc with Authorization header + decoder | Test JWT through filter | Filter → provider → decoder → converter → authorization | Production JWKS/network if using local public key |
| End-to-end with test IdP/JWKS | Token issued by test AS | Real contract between AS and Resource Server | Issuers outside the test |

No single test type replaces all others. Choose the layer according to the question you need to answer.

## 5. Unit tests for the authority converter

### 5.1. Building a test Jwt

A helper can create an unsigned Jwt since this tests conversion logic:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtFixtures {

    static Jwt validContractJwt() {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://identity.example.test/realms/shop")
            .subject("alice-42")
            .audience(List.of("orders-api"))
            .issuedAt(now)
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(600))
            .claim("scope", "orders.read orders.cancel")
            .claim("roles", List.of("ORDER_ADMIN"))
            .claim("token_use", "access")
            .claim("tenant_id", "tenant-A")
            .build();
    }
}
~~~

A Jwt built with the builder is not a signed JWT. Use it only to test converters/validators directly; never use this fixture to conclude signature validation works.

### 5.2. Testing scope and role mapping

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collection;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class JwtAuthoritiesConverterTest {

    @Test
    void mapsScopesAndRolesIntoSeparateAuthorityNamespaces() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        var converter =
                new DelegatingJwtGrantedAuthoritiesConverter(scopes, roles);

        Collection<GrantedAuthority> authorities =
                converter.convert(JwtFixtures.validContractJwt());

        assertThat(authorities)
            .extracting(GrantedAuthority::getAuthority)
            .contains("SCOPE_orders.read",
                      "SCOPE_orders.cancel",
                      "ROLE_ORDER_ADMIN");
    }
}
~~~

This test verifies the converter reads the right claims and prefixes. Do not assert only the authority count; asserting exact strings catches accidental prefix changes or reading the wrong claim.

### 5.3. Testing wrongly typed role claims

If the contract requires `roles` to be a collection of strings, test invalid input:

~~~java
Jwt malformedRoles = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .claim("roles", "ORDER_ADMIN,ORDER_AUDITOR")
    .build();
~~~

Do not assume `JwtGrantedAuthoritiesConverter` will parse a comma-separated string as desired. Either the contract mandates roles as a collection, or you write a custom converter with explicit parsing. If a wrong claim type violates the token contract, reject it in a validator; if it is optional permission data, the converter must handle it per policy without granting extra permissions.

### 5.4. Testing against privilege escalation outside the allowlist

If the `roles` claim comes from an issuer but the application only trusts a specific set of roles, filter with an allowlist:

~~~java
private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_ADMIN", "ORDER_AUDITOR");
~~~

Unit tests should pass `PLATFORM_ADMIN` or `SUPERUSER` and verify it does not become an internal authority if that role is outside the contract. Do not trust a claim named `roles` simply because the JWT signature is valid; claim contents must still be interpreted per issuer policy.

## 6. Unit testing JwtAuthenticationConverter

Check all three key properties:

- Authentication type.
- Principal/name semantics.
- Authorities after mapping.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

class JwtAuthenticationConverterTest {

    @Test
    void createsJwtAuthenticationWithExpectedPrincipalAndAuthorities() {
        Jwt jwt = JwtFixtures.validContractJwt();

        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
                new DelegatingJwtGrantedAuthoritiesConverter(scopes, roles));
        converter.setPrincipalClaimName("sub");

        var authentication = converter.convert(jwt);

        assertThat(authentication)
            .isInstanceOf(JwtAuthenticationToken.class);
        assertThat(authentication.getName()).isEqualTo("alice-42");
        assertThat(authentication.getPrincipal()).isSameAs(jwt);
        assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("SCOPE_orders.read", "ROLE_ORDER_ADMIN");
    }
}
~~~

The example shows a single `Jwt` passed to the converter and the default principal keeping that exact object.

### 6.1. Testing a custom principal claim

If the contract specifies `preferred_username` as the principal name:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .subject("immutable-subject-42")
    .claim("preferred_username", "alice")
    .build();

JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");

var authentication = converter.convert(jwt);
assertThat(authentication.getName()).isEqualTo("alice");
assertThat(authentication.getPrincipal()).isSameAs(jwt);
~~~

This only changes the principal's display name on Authentication. It does not alter the verified `sub` inside the JWT. If subject is the stable identifier for auditing/identity mapping, keep that claim intact in the token and use the appropriate field per contract.

### 6.2. Testing a custom Authentication converter

If using `ContractJwtAuthenticationConverter` from section 2.4, test:

- Jwt with valid `sub` and `tenant_id`: creates Authentication token.
- Missing `sub`/tenant: validators should reject beforehand; converter unit tests can verify the defensive check.
- Authorities are passed through completely without adding extra roles.
- `getName()` matches the chosen subject.

Converter unit tests should not call an Authorization Server, database, or HTTP. If the converter requires a DB lookup, extract the resolver into a separate service and mock it; then add an integration test for the real authentication path.

## 7. Unit testing OAuth2TokenValidator

### 7.1. Testing an audience validator

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;

class AudienceValidatorTest {

    private final OAuth2TokenValidator<Jwt> validator =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains("orders-api"));

    @Test
    void acceptsTokenForOrdersApi() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .audience(List.of("orders-api"))
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsTokenForAnotherAudience() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .audience(List.of("billing-api"))
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

This is a unit test for a pure validator. It does not check signatures, issuer, or expiration; those conditions belong to the decoder and other validators in the chain.

### 7.2. Testing a tenant validator

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class RequiredTenantClaimValidatorTest {

    private final RequiredTenantClaimValidator validator =
            new RequiredTenantClaimValidator();

    @Test
    void acceptsNonBlankTenant() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .claim("tenant_id", "tenant-A")
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsMissingTenant() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsWrongTenantClaimType() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .claim("tenant_id", 42)
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

### 7.3. Testing validators by token profile

For the `token_use` claim, test at least:

| Value | Expectation |
| --- | --- |
| `access` | Succeeds |
| `id` | Fails |
| `refresh` | Fails |
| null/missing | Fails |
| non-String data type | Fails |

If the contract uses `typ=at+jwt` per RFC 9068, use the corresponding validator/profile builder and test the header type separately. Do not combine two different profiles into a "flexible" validator that accepts both ID tokens and access tokens.

## 8. MockMvc tests with jwt() for authorization

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.jwt()` to create a mock JWT authentication. This is very useful when focusing on:

- Whether an endpoint requires the right scope/role.
- Whether controllers read claims/principals as expected.
- Whether method security or request authorization rejects missing authorities.

Example:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Test
void allowsRequestWhenRequiredScopeIsPresent() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()
                .jwt(token -> token
                    .issuer("https://identity.example.test/realms/shop")
                    .subject("alice-42")
                    .audience(List.of("orders-api"))
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void deniesRequestWhenRequiredScopeIsMissing() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()
                .jwt(token -> token
                    .subject("alice-42")
                    .claim("scope", "profile.read"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
~~~

This is a **mock Authentication**, not a signed JWS JWT. Per Spring Security documentation, the request post processor's default JWT has header `alg=none`. It does not go through `JwtDecoder` signature/JWKS validation. When passing `authorities(...)`, the test directly sets authorities on Authentication; if passing a converter to that overload, it is a `Jwt -> Collection<GrantedAuthority>` converter, which does not prove the `JwtAuthenticationConverter` bean configured in the filter chain runs properly.

Therefore:

- Use `jwt()` to test route/method authorization and how controllers use claims.
- Unit test `JwtAuthenticationConverter` directly to test Authentication mapping.
- Send requests with `Authorization: Bearer ...` through the filter chain with a real or mock decoder to test converter wiring.
- Use signed tokens/real decoders to test signature and validator contracts.

### 8.1. Testing authorities via a claim converter

If you only want to check an authorities converter in the request post processor, Spring Security Test allows:

~~~java
.with(jwt().authorities(jwtAuthoritiesConverter))
~~~

This is a useful test for scope/role mapping. Still, it does not prove the `JwtAuthenticationConverter` bean, `JwtDecoder`, or custom validators are wired into the production chain.

### 8.2. When to use authentication() instead of jwt()?

`authentication(authentication)` lets you install a custom-built Authentication directly into the request. It is appropriate when an endpoint expects a custom Authentication type or the test wants full control over principal/authorities. Like `jwt()`, this bypasses real token decoding/validation; do not use it to prove the decoder.

## 9. Testing the decoder with real signed JWTs

To test signature and validators together, generate a dedicated test RSA key pair:

- Test encoder signs tokens with the private key.
- Test decoder receives only the corresponding public key.
- Attach the real validator chain to the decoder.
- Call `decode(tokenValue)` and verify valid tokens or exceptions.

Never use production private keys in tests. Never use `alg=none` to simulate a valid token.

### 9.1. Configuring the decoder with a test public key

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;

RSAPublicKey publicKey = (RSAPublicKey) testKeyPair.getPublic();
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(publicKey).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        accessTokenUseValidator,
        new RequiredTenantClaimValidator()));
~~~

This is a local test decoder configuration; it verifies signatures using a test public key instead of calling JWKS. The validator chain must still check issuer/time and contract claims. If production uses JWKS, add a separate integration test with a test JWKS endpoint to confirm key discovery/rotation.

### 9.2. Creating signed JWTs with Nimbus JwtEncoder

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

static KeyPair generateRsaKeyPair() {
    try {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    } catch (java.security.GeneralSecurityException ex) {
        throw new IllegalStateException(ex);
    }
}

static JwtEncoder encoderFor(KeyPair keyPair) {
    RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) keyPair.getPublic())
        .privateKey((RSAPrivateKey) keyPair.getPrivate())
        .keyID("test-key")
        .build();

    JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(jwk));
    return new NimbusJwtEncoder(source);
}

static String signedAccessToken(
        JwtEncoder encoder, String audience, String tokenUse) {
    Instant now = Instant.now();

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(ISSUER)
        .subject("alice-42")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(2))
        .notBefore(now.minusSeconds(2))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .claim("roles", List.of("ORDER_ADMIN"))
        .claim("token_use", tokenUse)
        .claim("tenant_id", "tenant-A")
        .build();

    JwsHeader header = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(header, claims)).getTokenValue();
}
~~~

`ISSUER` is a test constant matching the issuer validator. Create a second encoder from a different `KeyPair` to issue tokens with signatures not trusted by the decoder.

If tests need to vary scopes or claims per scenario, you can use a helper accepting scope:

~~~java
static String signedTokenWithClaims(
        JwtEncoder encoder,
        String audience,
        String tokenUse,
        String scope) {
    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(ISSUER)
        .subject("alice-42")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(2))
        .notBefore(now.minusSeconds(2))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", scope)
        .claim("roles", List.of("ORDER_ADMIN"))
        .claim("token_use", tokenUse)
        .claim("tenant_id", "tenant-A")
        .build();

    JwsHeader header = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();
    return encoder.encode(
        JwtEncoderParameters.from(header, claims)).getTokenValue();
}
~~~

### 9.3. Testing validator pass/fail after signature succeeds

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;

class SignedJwtDecoderTest {

    @Test
    void acceptsSignedTokenThatMatchesTheContract() {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "access");

        var jwt = decoder.decode(token);

        assertThat(jwt.getSubject()).isEqualTo("alice-42");
        assertThat(jwt.getAudience()).contains("orders-api");
        assertThat(jwt.getClaimAsString("tenant_id"))
            .isEqualTo("tenant-A");
    }

    @Test
    void rejectsSignedTokenWithWrongAudience() {
        String token = signedAccessToken(
                trustedEncoder, "billing-api", "access");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(JwtValidationException.class);
    }

    @Test
    void rejectsSignedIdTokenProfile() {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "id");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(JwtValidationException.class);
    }

    @Test
    void rejectsTokenSignedByAnUntrustedKey() {
        String token = signedAccessToken(
                attackerEncoder, "orders-api", "access");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(org.springframework.security.oauth2.jwt.JwtException.class);
    }
}
~~~

This is a test skeleton: `decoder`, `trustedEncoder`, and `attackerEncoder` are created in the test fixture/configuration. An invalid signature case may throw `BadJwtException` or another `JwtException` subtype depending on the decoder; do not lock tests to a specific internal error message.

### 9.4. Distinguishing signature failures from validation failures

| Test case | Signature | Validators | Result |
| --- | --- | --- | --- |
| Valid token | Valid | All pass | Decodes successfully |
| Wrong audience | Valid | Audience fails | `JwtValidationException` |
| Wrong `token_use` | Valid | Profile validator fails | `JwtValidationException` |
| Missing tenant claim | Valid | Required-claim validator fails | `JwtValidationException` |
| Expired token | Valid | Timestamp validator fails | `JwtValidationException` |
| Signed with different key | Invalid for trusted key | Never reaches valid validator step | `JwtException` |

Do not lump every error into "invalid JWT signature". In operations, signature failures and claim-contract failures have different root causes; public responses should still keep information minimal, while internal metrics/logs can classify by error code without logging tokens.

## 10. MockMvc integration tests through the Resource Server filter chain

To prove `JwtAuthenticationConverter` is actually invoked, send an HTTP request with an Authorization header and let Spring Security run the normal pipeline. Do not pre-install Authentication with `jwt()` or `authentication()` in this test.

A minimal test setup needs:

- `SecurityFilterChain` using `oauth2ResourceServer().jwt(...)`.
- A real `JwtDecoder` (can use a local test public key).
- `JwtAuthenticationConverter` wired into the DSL.
- A test controller reading `Authentication.getName()` or the principal.
- MockMvc with the Spring Security filter chain enabled.

Endpoint example:

~~~java
@RestController
class TestOrdersController {

    @GetMapping("/api/orders")
    String orders(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Chain configuration:

~~~java
@Bean
SecurityFilterChain testApi(
        HttpSecurity http,
        JwtDecoder decoder,
        JwtAuthenticationConverter converter) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt
                .decoder(decoder)
                .jwtAuthenticationConverter(converter)))
        .build();
}
~~~

With the test configuration in section 9, MockMvc sends a token signed with the test private key:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwtAuthenticationHttpTest {

    @Autowired MockMvc mvc;
    @Autowired JwtEncoder trustedEncoder;

    @Test
    void validSignedTokenPassesThroughDecoderAndConverter()
            throws Exception {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "access");

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-42"));
    }
}
~~~

This is a skeleton combining the test controller, decoder, encoder, and filter chain from earlier sections. In real projects, use the appropriate test application context (e.g., `@WebMvcTest` + `@Import` or `@SpringBootTest`) and ensure the filter chain is enabled.

### 10.1. Testing that validators block before the converter

For a token with a valid signature but wrong audience, the decoder must reject the request before the converter is used. You can use a spy/mock bean for the converter or service to observe:

~~~java
@Test
void wrongAudienceIsRejectedBeforeControllerRuns() throws Exception {
    String token = signedAccessToken(
            trustedEncoder, "billing-api", "access");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verify(orderService, never()).listOrders(any());
}
~~~

`orderService` is a mocked controller dependency in the test. The primary expectation is that the controller/service does not run when the decoder rejects the token. To prove directly that the converter is not called, inject a spy for the converter and verify no invocations; spy declaration syntax depends on your Spring Boot/Spring Test version.

### 10.2. Testing missing scope is 403, not a validator failure

A token with the right issuer, signature, audience, tenant, and token type, but only `profile.read`:

~~~java
@Test
void validTokenWithoutRequiredScopeIsForbidden() throws Exception {
    String token = signedTokenWithClaims(
            trustedEncoder,
            "orders-api",
            "access",
            "profile.read");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
~~~

In this test the decoder/converter succeed; the request is blocked at authorization because `SCOPE_orders.read` is missing. This is the key distinction between **401 authentication failure** and **403 authorization denial**.

### 10.3. Testing invalid tokens are not "rescued" by the converter

Never write a converter like:

~~~java
if (jwt.getAudience().isEmpty()) {
    return new JwtAuthenticationToken(jwt, ADMIN_AUTHORITIES);
}
~~~

Validators must reject missing/wrong audiences. The converter only maps claims according to the contract. Wrong-audience tests must assert 401 and that controllers/services are never invoked.

## 11. Contract testing matrix

| ID | Token fixture | Layer expected to fail/pass | Expected HTTP |
| --- | --- | --- | --- |
| C01 | Valid signature, issuer, audience, scope | Passes decoder + converter + authorization | 200 |
| C02 | Valid signature, different issuer | Issuer validator | 401 |
| C03 | Valid signature, different audience | Audience validator | 401 |
| C04 | Invalid signature / untrusted key | Signature verification | 401 |
| C05 | `exp` in the past | Timestamp validator | 401 |
| C06 | `nbf` in the future beyond skew | Timestamp validator | 401 |
| C07 | Missing `sub` | Required-claim validator | 401 |
| C08 | Missing `tenant_id` | Contract validator | 401 |
| C09 | `token_use=id` | Access-token profile validator | 401 |
| C10 | Right scope, right role | Authority converter | Authentication has full authorities |
| C11 | Missing scope | Request authorization | 403 |
| C12 | Role claim contains non-allowlisted role | Role mapping policy | Does not grant privileged authority |
| C13 | Wrong data type for `roles` | Contract validator/converter policy | Fails per contract |
| C14 | Duplicate or repeated scopes | Authority converter | Grants no extra permissions; deterministic result |
| C15 | Valid JWT, but tenant/resource does not belong to caller | Domain authorization | 403/404 per API policy |
| C16 | Optional claim absent | Per defined contract | Does not synthesize authority |

Not all cases have the same status. Token/claim contract violations are usually 401; valid tokens missing a scope are usually 403; unauthorized resources may return 403 or 404 depending on disclosure policy.

## 12. Verifying the converter is wired into the filter chain

Unit testing the converter directly only proves the converter object works. You also need a test proving `JwtAuthenticationProvider` actually calls the configured converter.

There are two common ways:

### 12.1. Using a mock decoder to isolate converter wiring

Replace `JwtDecoder` with a mock returning a Jwt fixture, while sending requests with an Authorization header so the request still flows through the Bearer filter and provider:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwtConverterWiringTest {

    @Autowired MockMvc mvc;
    @MockBean JwtDecoder jwtDecoder;

    @Test
    void bearerRequestUsesConfiguredAuthenticationConverter()
            throws Exception {
        Jwt jwt = JwtFixtures.validContractJwt();
        given(jwtDecoder.decode("test-token")).willReturn(jwt);

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer test-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-42"));
    }
}
~~~

In this test, `JwtDecoder` is mocked so real signatures, issuers, and validators are not tested. Its dedicated goal is to prove the filter/provider calls the decoder and then uses the converter wired into `SecurityFilterChain`. To verify converter invocation directly, spy on the converter bean and verify it receives the right Jwt.

Spring Boot/Spring Framework may use `@MockBean` or `@MockitoBean` depending on version. Use the annotation matching your project's test stack; the test idea does not depend on the annotation name.

### 12.2. Using a real decoder to test the entire pipeline

A stronger test configures `NimbusJwtDecoder` with a test public key and sends a signed JWT via:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <signed-jwt>
~~~

The request passes through:

1. `BearerTokenAuthenticationFilter` extracts the token.
2. `JwtAuthenticationProvider` calls the decoder.
3. The decoder verifies the signature and runs validators.
4. When the token is valid, the provider calls `JwtAuthenticationConverter`.
5. Authentication is placed into the SecurityContext.
6. Request authorization checks scopes/roles.

For a token with the wrong audience but valid signature, the test must receive 401 and neither the converter nor controller runs. For a valid token missing a scope, the converter still runs, and then authorization returns 403.

### 12.3. Testing validator-before-converter ordering

If using a spy/mock for the converter:

~~~java
@Test
void invalidAudienceDoesNotReachAuthenticationConverter()
        throws Exception {
    String token = signedAccessToken(
            trustedEncoder, "billing-api", "access");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verify(authenticationConverter, never()).convert(any(Jwt.class));
}
~~~

`authenticationConverter` is a spy injected for the exact bean used by the filter chain. This test verifies a key invariant: **when a validator fails, the converter has no chance to build an Authentication**.

## 13. Testing errors and contract changes

### 13.1. 401 and 403 must be distinguished

| Result | Cause | Does the converter run? |
| --- | --- | --- |
| 401 no token | No credentials | No |
| 401 invalid signature | Decoder cannot verify token | No |
| 401 wrong issuer/audience/exp/token profile | Validator rejects | No |
| 200 | Valid token and authorization permits | Yes |
| 403 missing scope | Valid authentication, missing authority | Yes |
| 403 insufficient role | Valid authentication, role policy denies | Yes |
| 403/404 wrong tenant or owner | Domain authorization denies | Yes |

Do not test by checking only status across all cases. For 401 cases, confirm controllers/services are not called; for 403 cases, confirm authentication succeeded but authority/resource policy was insufficient.

### 13.2. Ensuring converter errors are not swallowed

If the converter can throw an error due to invalid claim data, tests must ensure the error never turns into a default Authentication with broad privileges. A better approach is having validators check required claims upfront so the converter is a mapping function with guaranteed inputs.

Avoid dangerous fallbacks:

~~~java
try {
    return mapAuthorities(jwt);
} catch (RuntimeException ex) {
    return List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

If permission data cannot be interpreted, fail closed per contract. Never return a default list containing privileged roles.

### 13.3. Testing contracts when the Authorization Server changes claims

Suppose the IdP migrates from `scope` to `scp` or changes `roles` from a collection to a string. Do not silently modify the converter to accept every shape without a versioning contract.

Maintain representative fixtures for:

- Current token profile.
- Legacy token profile during a transition window if still accepted.
- Tokens with missing or wrongly typed claims.
- Tokens from another issuer sharing the same claim name.

If two schemas must be supported during migration, clearly define precedence and deprecation deadlines. Tests must ensure a malformed claim cannot override permissions from another trusted claim.

### 13.4. Testing multiple issuers and tenants

If the API accepts multiple issuers, each issuer may have different claim naming/role semantics. Use separate validators/decoders per issuer allowlist and corresponding converters, or normalize the contract explicitly after the issuer is verified.

Negative tests:

- Issuer not in allowlist.
- Issuer A emitting `roles` claims with different semantics than issuer B.
- Tenant A token carrying a role meaningful only in tenant B.
- Two issuers sharing the same `sub` without representing the same identity.
- Missing or wrongly typed tenant claim.

Do not select a converter or JWKS URL based on an unverified issuer from the payload. Multi-issuer routing must use a configured trust list.

## 14. Common mistakes when writing tests

**Using `@WithMockUser` to test JWT claims.** This annotation creates a simple user authentication and does not test the Jwt principal, claims, or `JwtAuthenticationConverter`. Use it when endpoints only need a generic UserDetails principal; use JWT test support or signed tokens when code depends on `Jwt`.

**Using `jwt()` and concluding the decoder/validators ran.** The request post processor creates a mock Jwt/Authentication and does not verify JWS signatures or JWKS. You must have decoder tests and signed-token integration tests.

**Testing only authority count.** Two authorities could have wrong prefixes or wrong names. Assert exact `SCOPE_...` and `ROLE_...` strings.

**Changing all prefixes to ROLE_.** Scopes and roles have different meanings; keep namespaces separate.

**Adding an audience validator while forgetting default validators.** `setJwtValidator` replaces the current validator; compose default issuer/time validators with custom validators.

**Testing a wrong-audience token with `jwt()` and expecting 401.** Because mock JWTs do not go through the decoder, the audience validator never runs. Use validator unit tests or signed tokens through the decoder.

**Using synthetic `alg=none` tokens to test signatures.** Such fixtures are only for converter/authorization unit tests. Signature tests require real JWSs and trusted public keys.

**Putting business authorization into the converter.** Converters should map identity/authorities. Tenant membership and resource permissions should be checked in service/method authorization.

**Using a validator to map roles.** Validators only accept/reject the token contract; authority converters produce `GrantedAuthority`.

**Accepting missing claims with a default admin role.** Missing or invalid claims must fail closed per contract; never auto-escalate privileges.

**Asserting the exact error message of the decoder.** Messages can change across versions/providers. Prefer exception types/error codes/statuses and verify no side effects occur.

**Not testing missing scopes.** A token may be completely valid yet unauthorized to call an endpoint. Add dedicated 403 tests after authentication succeeds.

**Not testing unwired converters.** A bean unit test may pass while the filter chain still uses the default converter. Send real Authorization headers through MockMvc and verify principal/authorities.

**Using a mock decoder for all tests and concluding all security is tested.** Mock decoders bypass signatures and validators. Keep wiring tests and real-decoder tests separate.

## 15. Test suite handoff checklist

### Token contract

- [ ] Document issuer, audience, algorithm, expiration, and access-token profile.
- [ ] Document required claims, data types, and blank/null rules.
- [ ] Distinguish scope, role, tenant, and identity claims.
- [ ] Specify which claims are mandatory and which are optional metadata.
- [ ] Maintain fixtures for valid tokens and every invalid token variant per contract.

### Validator/decoder

- [ ] Signatures are verified with trusted public keys/JWKS.
- [ ] Only configured algorithms are accepted.
- [ ] Issuer validator is preserved when adding custom validators.
- [ ] Audience validator matches the exact Resource Server.
- [ ] Timestamp validator and clock skew are configured intentionally.
- [ ] Token type/profile and required claims are checked.
- [ ] Custom validators fail closed when claims are missing/invalid.
- [ ] Unit tests cover success/failure; decoder tests cover signed tokens.

### Converter/Authentication

- [ ] Scopes map with the right authority prefix.
- [ ] Roles map separately and only from claims trusted per contract.
- [ ] Principal name has clear semantics.
- [ ] Principal object matches the type expected by controllers/method security.
- [ ] Converter never grants default roles when claims are invalid/missing.
- [ ] Unit tests assert exact authority strings and Authentication type.
- [ ] Filter-chain tests prove the converter is wired.

### Servlet/MockMvc integration

- [ ] Use `jwt()` purposefully for authorization tests, never to simulate signature validation.
- [ ] Send Authorization headers to test the Bearer filter/provider/decoder/converter chain.
- [ ] Include signed JWT tests through a real decoder.
- [ ] Include tests for invalid signature, wrong issuer, wrong audience, expired token, and violated claim contracts.
- [ ] Include tests for valid tokens missing scope/role returning 403.
- [ ] When a token is rejected, controllers/services are not invoked.
- [ ] Avoid asserting internal error messages prone to change across versions.

## 16. Practice scenarios

**Scenario A.** A token has a valid signature, right issuer, and scope `orders.read`, yet `aud` is `billing-api`. Should the converter add `SCOPE_orders.read` and let the request through?

**No.** The audience validator must reject the token before the converter runs. Having the right scope does not turn a token intended for the Billing API into one for the Orders API.

**Scenario B.** The `JwtAuthenticationConverter` unit test passes and creates `ROLE_ORDER_ADMIN` properly. Can we conclude the production filter chain uses this converter?

**Not yet.** You need to test an Authorization header request through MockMvc/Servlet filter chain and verify the converter bean is wired into `oauth2ResourceServer().jwt(...)`.

**Scenario C.** MockMvc uses `jwt()` with a token fixture carrying invalid `iss` and `aud` claims, yet the request passes authentication. Why?

`jwt()` creates a mock JWT Authentication to test authorization; it does not call the decoder and does not run signature/issuer/audience validators. Use validator unit tests or signed tokens through a real decoder.

**Scenario D.** An audience validator was added via `decoder.setJwtValidator(audienceValidator)`. Afterward, expired tokens are still accepted. Where is the bug?

It replaced the default validator and dropped timestamp validation. Compose `JwtValidators.createDefaultWithIssuer` with the custom audience validator using `DelegatingOAuth2TokenValidator`.

**Scenario E.** A valid token missing `SCOPE_orders.read` gets 403. Is the converter broken?

Not necessarily. The decoder and converter may be working properly; authorization denied the request due to a missing authority. Check the authority list and route policy.

**Scenario F.** The `roles` claim contains `PLATFORM_ADMIN`, which is not in the application's allowlist. Should it be mapped verbatim to `ROLE_PLATFORM_ADMIN`?

Not by default. Only map roles permitted by the contract and application policy; a validly signed token does not mean every role string grants permissions in the application.

**Scenario G.** A custom converter detects a missing `tenant_id` and defaults it to `tenant-default`. Is this safe?

Only if the contract explicitly defines a default tenant and doing so never escalates privileges. For APIs requiring a tenant context, reject via a validator; do not infer tenants automatically.

**Scenario H.** The JWT signature is invalid, yet the scope claim contains `orders.cancel`. Can the request reach the service?

No. The decoder must reject before the converter and authorization; the service must never execute.

**Scenario I.** The converter unit test succeeds, while the signed-token integration test returns 401 due to an issuer mismatch. Should the issuer validator be removed so the test passes?

No. The unit test checks mapping; the integration test is catching a token that violates the trust contract. Fix the issuer/config/token fixture to match the true contract.

**Scenario J.** The Authorization Server changes `roles` from a list to a comma-separated string. What must change?

Perform a controlled contract update: update the converter or validator for the new schema, add fixtures for the migration window, and test that roles outside the allowlist are not created. Never accept arbitrary data shapes implicitly.

---

## Conclusion

Testing `JwtAuthenticationConverter` and custom validators should be divided by responsibility. **Validators/decoders decide whether a JWT is trusted** based on signature, issuer, expiration, audience, and claim contracts. **The Authentication converter decides what principal and authorities a trusted token becomes**. The authority converter is a sublayer dedicated to mapping scopes/roles; it does not replace validators and does not decide per-resource permissions.

Use unit tests to verify scope/role mapping, principal names, and individual validators; use `jwt()` in MockMvc to test authorization/controllers when signing tokens is unnecessary; use Authorization headers through the filter chain to test converter wiring; and use real signed JWTs through `JwtDecoder` to verify signatures and validator contracts. A strong test suite distinguishes **401 from authentication/token-contract failures** from **403 from valid tokens lacking permissions**, while proving rejected requests never execute business logic.

## References

1. [Spring Security 7.1 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security 7.1 — Testing OAuth 2.0 / JWT with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
3. [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
4. [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
5. [Spring Security API — DelegatingOAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html)
6. [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
7. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
