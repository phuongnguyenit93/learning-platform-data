# Configuring iss, sub, aud, iat, exp, nbf, jti, and scope

## 1. Objectives and Context

In the **Tokens and claims** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson focuses on designing the key claims in JWTs issued by an OAuth 2.0/OpenID Connect Authorization Server. This is part of **designing, configuring, securing, testing, and operating an Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application**.

A JWT Access Token can be validly signed yet still unsuitable for calling a specific API. For example, a token may be issued by a trusted issuer and not yet expired, but carry an audience intended for the Billing API while the request goes to the Orders API. If the Orders API checks only the signature and expiration, the token could be accepted for the wrong target. Likewise, a token with scopes broader than what was approved creates privilege escalation risks.

Claims covered in this lesson:

- **iss**: the issuer that issued the token.
- **sub**: the subject that the token represents.
- **aud**: the audience or intended recipient of the token.
- **iat**: the time at which the token was issued.
- **exp**: the expiration time of the token.
- **nbf**: the time before which the token must not be accepted, if used.
- **jti**: the unique identifier of the token.
- **scope**: the permissions granted to the Access Token.

After this lesson, you will be able to explain the meaning of each claim, distinguish Access Token claims from ID Token claims, configure them via **OAuth2TokenCustomizer<JwtEncodingContext>**, validate them at the Resource Server, and test actual issued tokens rather than just configuration.

## 2. JWT Claims and the Boundary Between Access Tokens and Opaque Tokens

JWT is a token format capable of carrying claims in a Base64URL-encoded payload that is then signed. With a **self-contained JWT Access Token**, the Resource Server can verify the signature and inspect claims without querying the Authorization Server on every request, if the architecture accepts offline verification.

With an **opaque Access Token**, the client only receives a string without a readable JWT payload. The Resource Server typically validates the token via introspection or a state lookup mechanism. Internal claims may still exist in the authorization store, but do not necessarily appear inside a JWT decoded by the Resource Server.

| Characteristic | JWT Access Token | Opaque Access Token |
| --- | --- | --- |
| Contents | Has a Base64URL-encoded header and claims payload, then signed | String that does not publicly expose claim structure |
| Verification | Signature, issuer, audience, timestamps, scope, and policy | Introspection or state verification mechanism |
| Claims | Observable in the payload; **must not be treated as secret** | Payload cannot be read directly from the token |
| Revocation | Limited if the Resource Server only verifies JWTs offline | Can reflect status via introspection, depending on cache/policy |
| Customization in Spring | OAuth2TokenCustomizer<JwtEncodingContext> for JWTs | Uses the claims/context mechanism appropriate to opaque tokens and version |

**This lesson focuses on JWT Access Tokens.** Do not assume that adding a claim to JwtEncodingContext also gives opaque tokens the same payload or changes ID Tokens in the same way as Access Tokens.

## 3. Claim Overview Table

| Claim | Meaning | JWT data type | Primary checks |
| --- | --- | --- | --- |
| iss | Issuer | String | Must match the issuer trusted by the Resource Server |
| sub | Subject | String | Must accurately represent the user/workload per contract |
| aud | Audience | String or array of Strings | Must contain the identifier of the receiving Resource Server |
| iat | Issued At | NumericDate | Must not be too far in the future; helps evaluate token age |
| exp | Expiration Time | NumericDate | Token is no longer valid at or after expiration |
| nbf | Not Before | NumericDate, optional | Token is invalid before this time |
| jti | JWT ID | String | Token identifier; requires a state store if used for revocation/deduplication |
| scope | Granted OAuth2 permissions | Typically a space-delimited string per JWT Access Token Profile | Issue only approved permissions; API checks required permissions |

The claims iss, sub, aud, exp, nbf, iat, and jti are **registered claims** in RFC 7519. RFC 7519 defines their meanings and data types, without requiring every JWT to include all of them in every use case. When issuing JWT Access Tokens under **RFC 9068**, iss, exp, aud, sub, client_id, iat, and jti are mandatory profile components. Scope is an OAuth2 Access Token claim, not a core JWT registered claim.

**Do not look only at claim names.** The Resource Server must verify the issuer, signature, lifetime, audience, token type, and privileges; a JWT containing all eight fields with the wrong audience must still be rejected.

## 4. iss — Token Issuer

Iss identifies **which Authorization Server issued the token**. The value is typically a stable public URI, for example:

~~~text
https://auth.example.com
~~~

The issuer is configured in AuthorizationServerSettings. With Spring Authorization Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://auth.example.com")
                .build();
    }
}
~~~

Spring Authorization Server's JWT generator uses the issuer context to populate the issuer claim in tokens. In standard configurations, let the framework produce this claim from AuthorizationServerSettings; only override it in a customizer when there is a clear reason and ensure consistency with discovery metadata, JWKS, and Resource Server settings.

### 4.1. Common Issuer Mistakes

- Token uses https://auth.example.com, while the Resource Server is configured to trust https://auth-staging.example.com.
- A reverse proxy advertises a different hostname than the issuer signed inside the JWT.
- Dev and production share an issuer without separating keys or client registries.
- A Resource Server accepts whatever issuer appears in the token instead of using a trusted configuration.
- The issuer is changed after tokens are issued without updating clients/APIs.

The issuer is an **exact identifier**, not something to match by substring or wildcard hostname. Changing an issuer is a trust boundary change: metadata, JWKS, unexpired tokens, Resource Servers, and affected clients all require a migration plan.

## 5. sub — Subject Represented by the Token

Sub identifies the subject associated with the token, typically the authenticated user. Example:

~~~json
{
  "sub": "user-8f2a91"
}
~~~

Sub must be stable according to the identity contract used by the Resource Server. Do not use a mutable email or username as a long-term identifier if the system needs to associate permissions, audit trails, or data across the account lifecycle.

In Spring Authorization Server, the default subject typically comes from the context principal during JWT creation. Verify which Authentication is used in each grant:

- **Authorization Code:** usually represents the logged-in user.
- **Client Credentials:** the token represents a workload/client; do not assume an end-user exists.
- **Token Exchange:** the subject must reflect the source token and impersonation/delegation policy; never assign subject from untrusted parameters.

### 5.1. Protecting Subject Privacy

Do not put the following into sub without a business justification and dedicated review:

- Email address, phone number, or physical address.
- Employee IDs or sensitive identifiers used across multiple systems.
- Full name or directly identifiable personal information.

An opaque internal identifier or pairwise subject identifier per client/resource domain can be used to reduce cross-system user correlation. Crucially, the Resource Server must have a way to map that identifier to authorized business data.

**Do not confuse sub with client_id.** Sub states who the token represents; client_id states which application requested the token. In the JWT Access Token Profile, these two fields have distinct roles.

## 6. aud — Token Audience

Aud states **who the token is intended to be consumed by**. For an Access Token, the audience is normally the identifier of the Resource Server/API, for example:

~~~json
{
  "aud": ["orders-api"]
}
~~~

A token meant for orders-api must not be accepted by billing-api just because both trust the same issuer. Each Resource Server must verify that the token's audience includes its own identifier.

### 6.1. Access Tokens and ID Tokens Have Different Audiences

| Token type | Audience typically represents | Verifying party |
| --- | --- | --- |
| JWT Access Token | Resource Server/API receiving access privileges | Resource Server |
| OIDC ID Token | OIDC Client that initiated login | OIDC Client |

This is an essential distinction. Do not apply an ID Token's audience (client ID) as if it were an Access Token audience. Also never use an ID Token to call an API instead of an Access Token.

### 6.2. Do Not Take Audience Arbitrarily from the Request

A client may send a resource or audience parameter in flows supporting resource indicators/token exchange, but **that value is a request**, not the final decision. The Authorization Server must validate client, subject, scopes, and resource policy before placing an audience into the token.

Example internal policy:

| Client | Permitted audience |
| --- | --- |
| orders-bff | orders-api |
| billing-bff | billing-api |
| reporting-service | reports-api |

Do not copy the audience straight from the request and sign the token. When a client calls multiple APIs, maintain an approved server-side mapping between client, grant, resource, and scopes.

### 6.3. Configuring Audience in JwtEncodingContext

The example below customizes the audience of a **JWT Access Token** using a static server-side mapping:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenAudienceConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenAudienceCustomizer() {
        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            String clientId = context.getRegisteredClient().getClientId();
            List<String> audiences = switch (clientId) {
                case "orders-bff" -> List.of("orders-api");
                case "billing-bff" -> List.of("billing-api");
                default -> throw new IllegalStateException(
                        "No approved audience mapping for client");
            };

            context.getClaims().audience(audiences);
        };
    }
}
~~~

This is an **illustrative mapping example**; production may use a policy repository while preserving the allowlist principle. If one client is allowed to call multiple APIs, add audiences only when authorization and resource policy permit. Do not mechanically use client_id as the audience in place of an API identifier.

**Note on defaults:** the default claim set generated by the JWT generator can vary by version and token context. Decode a test Access Token to confirm the actual aud, then explicitly configure the audience your Resource Server requires. Never guess from client names or documentation for another version.

## 7. iat — Issued-At Timestamp

Iat (Issued At) represents the time the token was created, using the **NumericDate** type per RFC 7519. When serialized in a JWT, NumericDate is the number of seconds since the Unix epoch (optionally fractional); libraries usually handle conversion from Instant.

Example payload:

~~~json
{
  "iat": 1794823200
}
~~~

Iat helps:

- Determine token age.
- Detect tokens issued too far in the future.
- Support investigation, correlation, and time-based revocation policies.
- Analyze issuance time relative to an incident timestamp.

Never use iat as the sole proof that a token is valid. An attacker can craft a payload with a plausible iat without a valid signature; the Resource Server must still verify signature and issuer.

## 8. exp — Expiration Timestamp

Exp (Expiration Time) defines when the token **must no longer be accepted**. Per RFC 7519, a token must not be accepted on or after its expiration time, possibly allowing a small policy-defined clock skew window for clock drift.

Example:

~~~json
{
  "iat": 1794823200,
  "exp": 1794823800
}
~~~

The token has a nominal lifetime of 600 seconds. Actual lifetimes should be set according to risk, client type, scopes, audience, and operational requirements.

### 8.1. Configuring Access Token TTL

Spring Authorization Server configures Access Token lifetime in the RegisteredClient's TokenSettings:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .build();
~~~

The TTL is used by the JWT generator to compute the corresponding exp upon issuance. **Do not confuse** accessTokenTimeToLive with Authorization Code, Refresh Token, or Device Code lifetimes; those are separate policies.

### 8.2. Relationship Between iat and exp

For a newly issued token:

~~~text
iat = issuance time
exp = iat + accessTokenTimeToLive
exp > iat
~~~

Do not set exp too far in the future merely to reduce client refreshes. Long-lived Access Tokens increase exposure if stolen. If a client needs longer sessions, evaluate Refresh Tokens under appropriate grant/client policies instead of extending Access Token lifetimes unchecked.

### 8.3. Clock Skew and Time Synchronization

Authorization Server and Resource Server nodes must keep synchronized clocks. With large clock drift, freshly issued tokens may be treated as not yet valid or already expired. Allow only a small clock skew per policy; never widen skew to minutes or hours to mask NTP failures.

## 9. nbf — Not-Before Timestamp

Nbf (Not Before) is an optional claim. When set, the token must not be accepted **before** this timestamp. Example:

~~~json
{
  "nbf": 1794823200,
  "exp": 1794826800
}
~~~

Nbf can be useful when a token is generated before a permission takes effect, or when a system follows a scheduled issuance flow. For ordinary Access Tokens, nbf is usually unnecessary if the token is valid immediately upon issuance.

### 9.1. When Should nbf Be Set?

- The token is issued ahead of a scheduled session start time.
- A business workflow requires a specific activation timestamp.
- The system has an explicit future-validity policy and Resource Servers handle clocks consistently.

Do not use nbf in place of exp, never set nbf after exp, and do not arbitrarily set nbf in the future to "create a safety delay". If a client receives a token before nbf, the API will reject it until that timestamp arrives.

### 9.2. Example Intentionally Adding nbf

If genuinely needed by business logic, nbf can be added in an Access Token customizer:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class NotBeforeClaimConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> notBeforeCustomizer(Clock tokenClock) {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getClaims().notBefore(tokenClock.instant());
            }
        };
    }
}
~~~

A Clock bean must be provided by the application, such as Clock.systemUTC(). In real applications, only set nbf if required; if the token should be valid immediately, this claim is unnecessary. If you have multiple OAuth2TokenCustomizer<JwtEncodingContext> beans, combine them intentionally so they do not override or replace each other's logic.

## 10. jti — Unique Token Identifier

Jti (JWT ID) uniquely identifies a specific JWT. Example:

~~~json
{
  "jti": "6f6c7d18-4baf-4e93-92a4-8e71d54b1d3c"
}
~~~

Two distinct tokens should have different jti values, even with the same sub, aud, scope, and nearby timestamps. Jti is useful for:

- Correlating tokens with audit events.
- Denylists/revocation lists if the system maintains state.
- Investigating leaked tokens or anomalous usage.
- Detecting duplicates in workflows requiring token identity.

**Jti does not create replay protection by itself.** If a Resource Server only checks signature and expiration, it does not inherently know whether a jti was previously used or revoked. Blocking a specific token requires a state store, introspection, denylist, or another per-request check aligned with requirements.

Spring Authorization Server's default JWT generator normally populates jti for JWTs. There is no need to override it unless specifically required. If a custom generator creates jti, use a cryptographically secure random source and avoid value reuse.

## 11. scope — Permissions Granted in the Access Token

Scope represents the OAuth2 permissions granted to the token. Example:

~~~json
{
  "scope": "orders.read profile"
}
~~~

Scope must reflect **permissions approved by the Authorization Server**, not every scope the client sent in the authorization request. When a user only approves orders.read, never issue a token containing orders.write.

Per the JWT Access Token Profile RFC 9068, when the scope claim is included in a JWT Access Token, it is formatted as a **space-separated string of scopes**. Some converters/frameworks may accept collections in other contexts; when applying the JWT Access Token Profile, verify the serialized format matches the Resource Server contract.

### 11.1. Requested Scopes vs. Authorized Scopes

| Scope set | Source | Meaning |
| --- | --- | --- |
| Requested scopes | Requested by client | Client's wish, not yet granted permissions |
| Registered client scopes | RegisteredClient | Upper bound of scopes the client may request |
| Authorized scopes | Authorization Server after policy/consent | Approved permissions for the authorization/token |
| Token scope claim | Access Token claims | Permissions the Resource Server can use to authorize requests |

In customizers, rely on context.getAuthorizedScopes() instead of parsing scopes from the raw HTTP request. Having a scope in a token does not replace checking permissions on specific resources; APIs must still verify ownership, tenant, data state, and business policy.

### 11.2. Scope Is Not Audience

- aud=orders-api: the token is intended for the Orders API.
- scope=orders.read: the token permits reading orders per policy.

A token with orders.read whose audience is billing-api **must not be used on the Orders API**. Conversely, a matching audience missing the orders.read scope must also be rejected.

## 12. Distinguishing Access Token Claims and ID Token Claims

An OIDC system may issue both JWT Access Tokens and ID Tokens. The two token types share some claim names with different semantics.

| Claim | JWT Access Token | OIDC ID Token |
| --- | --- | --- |
| iss | Authorization Server issuer | OpenID Provider issuer |
| sub | Subject identified for API/token policy | End-user identifier in OIDC |
| aud | Receiving Resource Server/API | OIDC Client that must validate the ID Token |
| iat | Access Token issuance time | ID Token issuance time |
| exp | Access Token expiration time | ID Token expiration time |
| nbf | Optional, depending on policy | Not always present |
| jti | Access Token identifier | Optional depending on generator/profile |
| scope | Granted OAuth2 permissions, per profile | Not a substitute for Access Token scopes |
| nonce | Not used as a substitute claim on Access Tokens | Binds the ID Token to the OIDC request when requested |

**Do not apply an unguarded customizer across all token types.** If an Access Token customizer changes aud to orders-api, it must not accidentally give the ID Token an audience of orders-api; the ID Token must carry the OIDC client's audience per OIDC rules.

## 13. JWT Creation Pipeline in Spring Authorization Server

~~~mermaid
flowchart TD
    A["Token Endpoint / Authorization flow"] --> B["OAuth2TokenContext"]
    B --> C["JwtGenerator"]
    C --> D["Build standard claims: iss, sub, aud, iat, exp, jti..."]
    D --> E["OAuth2TokenCustomizer<JwtEncodingContext>"]
    E --> F["JwsEncoder / JwtEncoder signs JWT"]
    F --> G["OAuth2AuthorizationService stores authorization/token"]
    G --> H["Token response"]
~~~

Standard claims can be initialized by the generator based on AuthorizationServerContext, principal, RegisteredClient, authorized scopes, and TokenSettings. The customizer allows **adding or modifying claims prior to signing**. Whether a claim has a specific default value should be verified against your exact version and token type.

### 13.1. OAuth2TokenCustomizer<JwtEncodingContext> Extension Point

Minimal example adding claims only for Access Tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenClaimsConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            context.getClaims().claims(claims -> {
                claims.put("client_id", context.getRegisteredClient().getClientId());
                claims.put("scope", String.join(" ", context.getAuthorizedScopes()));
            });
        };
    }
}
~~~

In the example above:

- Applies only to OAuth2TokenType.ACCESS_TOKEN, leaving ID Tokens untouched.
- Uses getRegisteredClient() to read the server-resolved client.
- Uses getAuthorizedScopes() to read approved permissions.
- Formats scope as a space-delimited string per the JWT Access Token Profile.
- Includes client_id to distinguish the requesting client from the subject.

If your version/generator already produces client_id or scope in the desired format, do not overwrite them just to repeat them. Decode a test token and check your Resource Server contract before adding a customizer.

### 13.2. Setting Audience by Resource Policy

You can combine the audience mapping from section 6 with an Access Token customizer. In real applications, place the mapping in a dedicated component/policy instead of accepting arbitrary target lists from requests:

~~~java
List<String> audience = resourceAudiencePolicy.resolve(
        context.getRegisteredClient(),
        context.getAuthorizedScopes());

if (audience.isEmpty()) {
    throw new IllegalStateException("No approved resource audience");
}

context.getClaims().audience(audience);
~~~

resourceAudiencePolicy is an application-defined business component, not a default Spring Authorization Server class. It must reject clients/scopes without a mapping; never return a catch-all audience just to "make it work".

### 13.3. Issuer, Subject, Timestamps, and ID

Spring Authorization Server normally builds iss, sub, iat, exp, and jti inside the JWT generator from the authorization context and TokenSettings. Do not overwrite these claims arbitrarily in every customizer:

- **iss:** comes from issuer context/AuthorizationServerSettings, never from the request host header.
- **sub:** comes from the principal or a trusted subject mapping; never from browser-submitted values.
- **iat:** issuance time determined by the generator/clock.
- **exp:** based on the TTL configured for the token type.
- **jti:** unique identifier created by the generator.

Override only when there is a specific architectural requirement, with controlled clocks, identifiers, and compatibility with Resource Server validators.

## 14. Example Configuring RegisteredClient and JWT Access Token

A backend web client can be registered as follows:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient ordersBff = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-bff")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .scope("profile")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();
~~~

This is an example registration for a single client; encodedClientSecret must be an appropriately encoded secret, never a raw secret in source code. With a JDBC repository, RegisteredClient.id must be generated once and persisted stably across deployments.

RegisteredClient constrains which scopes and grants a client may request. **Audience must still be determined by resource policy** and placed into the Access Token via the appropriate customizer/generator. Never automatically grant all Orders API scopes just because a client is named orders-bff.

## 15. Validating Claims at the Resource Server

Issuing tokens on the Authorization Server is one half of the contract. The Resource Server must verify claims for the resources it protects.

For the Orders API:

- iss must match the trusted issuer.
- Signature must be valid per configured JWK/algorithm.
- exp and nbf must be valid per clock policy.
- aud must contain orders-api.
- scope must contain the required permission, such as orders.read.
- sub/tenant must satisfy authorization on the specific resource.

Example audience validator in Spring Security Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Configuration(proxyBeanMethods = false)
class OrdersJwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.com";
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

This is an illustrative Resource Server configuration for Spring Security 6.x; the issuer/JWKS endpoint must be reachable from the deployment environment and configured according to real trust policies. A complete application also needs a SecurityFilterChain enabling oauth2ResourceServer(...jwt...), authorization rules, and suitable scope/authority converters.

**Do not validate audience only on the Authorization Server.** The Resource Server must verify aud itself because a token could be misrouted or stolen from another system.

## 16. Testing JWT Claims

Tests should read the **signed JWT issued in an integration test**, not merely assert that a builder or customizer was called.

### 16.1. Required Checks

| Claim | Test case | Expectation |
| --- | --- | --- |
| iss | Token from test issuer | Matches configured issuer URI |
| sub | Logged-in user | Correct subject identifier per policy, no unnecessary PII exposed |
| aud | Token for Orders API | Contains orders-api; contains no targets outside allowlist |
| iat | Fresh token | Present, not too far in the future |
| exp | Fresh token with 10-minute TTL | After iat, matches configured TTL |
| nbf | Token with future-validity policy | Rejected by Resource Server before that timestamp |
| jti | Two separate token issuances | Distinct identifiers |
| scope | Authorization approved only for orders.read | No orders.write; serialized format matches profile |

### 16.2. Example Asserting Claims After Decoding

Suppose the test completed the flow and obtained accessTokenValue from the Token Endpoint:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;

import static org.assertj.core.api.Assertions.assertThat;

class AccessTokenClaimsIntegrationTest {

    @Autowired
    JwtDecoder jwtDecoder;

    @Test
    void issuedAccessTokenContainsExpectedClaims() {
        String accessTokenValue = obtainAccessTokenFromTestFlow();
        Jwt jwt = jwtDecoder.decode(accessTokenValue);

        assertThat(jwt.getClaimAsString("iss"))
                .isEqualTo("https://auth.example.com");
        assertThat(jwt.getSubject()).isEqualTo("user-8f2a91");
        assertThat(jwt.getAudience()).containsExactly("orders-api");
        assertThat(jwt.getIssuedAt()).isNotNull();
        assertThat(jwt.getExpiresAt()).isAfter(jwt.getIssuedAt());
        assertThat(jwt.getId()).isNotBlank();
        assertThat(jwt.getClaimAsString("scope")).isEqualTo("orders.read");
        assertThat(jwt.getClaimAsString("client_id")).isEqualTo("orders-bff");
    }

    private String obtainAccessTokenFromTestFlow() {
        // Execute Authorization Code + PKCE in the test fixture,
        // complete login/consent, and exchange the code at the Token Endpoint.
        throw new UnsupportedOperationException("Provide the project's test flow");
    }
}
~~~

obtainAccessTokenFromTestFlow() is a placeholder describing the fixture step, not a standalone runnable implementation. Real tests must obtain tokens through the actual Authorization Server and the decoder must verify the test issuer's signature.

### 16.3. Negative Testing

- Token with valid issuer/signature but wrong aud -> Resource Server rejects.
- Expired token -> rejected.
- Token with future nbf -> rejected before activation time.
- Token with profile scope when API requires orders.read -> rejected.
- Token with valid sub belonging to a different tenant -> business authorization rejects.
- Token signed by an untrusted key or different issuer -> rejected.
- Two independently issued JWTs sharing a jti unexpectedly -> inspect token generator and uniqueness.

**Passing a JWT decode test does not prove every API checks claims.** Run Resource Server integration tests against protected endpoints to prove audience and scopes are actually enforced.

## 17. Common Design Mistakes

### 17.1. iss Present but Not Checked by Resource Server

Having an issuer inside a JWT does not make that issuer trustworthy. The Resource Server must use a configured issuer and verify the signature against the corresponding keys. Never extract iss from the token and dynamically trust new issuers.

### 17.2. Using client_id as aud for All Access Tokens

Client_id identifies the client; aud identifies the recipient. If the Resource Server expects orders-api, a token whose audience is only orders-bff may fail or be mis-scoped. Define audience mappings per resource and enforce them at the API.

### 17.3. Using Email as sub

Emails can change, be recycled, or reveal personal data. Use a stable subject identifier per policy; if email is needed, include it in a dedicated claim only when the Resource Server genuinely requires it.

### 17.4. Increasing exp to Reduce Refresh Errors

Long-lived Access Tokens increase risk if stolen. Set TTLs from your threat model and use Refresh Tokens under appropriate grant/client conditions.

### 17.5. Setting nbf Too Far in the Future

The client receives a token, yet the API rejects it because it is not yet active. Only set nbf when genuinely required; verify clocks and error handling properly.

### 17.6. Assuming jti Prevents Replay on Its Own

Jti is only an identifier. Without a state store/denylist or other online check, an offline Resource Server does not know a token was revoked.

### 17.7. Issuing Scopes Directly from the Raw Request

Never copy client-requested scopes directly into tokens. Use authorizedScopes after the server evaluates grant, RegisteredClient, consent, and policy.

### 17.8. Applying One Customizer to Both Access Tokens and ID Tokens

Always check context.getTokenType() before modifying claims. An Access Token's audience is the Resource Server; an ID Token's audience is the OIDC Client. Mixing the two breaks client/API validation.

### 17.9. Putting Secrets into Claims

Never place passwords, client secrets, refresh tokens, private keys, code verifiers, or unnecessary sensitive data into JWTs. JWT payloads are typically only Base64URL-encoded, not encrypted by default; anyone holding the token can read its claims.

## 18. Implementation Checklist

1. **Issuer:** iss matches AuthorizationServerSettings and public metadata; Resource Server trusts the exact issuer.
2. **Subject:** sub is stable, follows privacy policy, and distinguishes users from clients/workloads.
3. **Audience:** aud names the Resource Server permitted to receive the token; never taken arbitrarily from requests.
4. **Issued At:** iat reflects issuance time, and node clocks are synchronized.
5. **Expiration:** exp follows TokenSettings with an appropriately short TTL and is never accidentally extended by customizers.
6. **Not Before:** set nbf only when needed; nbf < exp and verified by Resource Server.
7. **JWT ID:** jti is unique; if revocation/deduplication is required, pair with a state store or live check.
8. **Scope:** uses only authorized scopes, serialized per profile, and enforced by Resource Server.
9. **Token type:** Access Token customizers do not corrupt ID Tokens or opaque tokens.
10. **Resource Server:** verifies signature, issuer, audience, timestamps, scopes, and business authorization.
11. **Privacy:** no secrets or unnecessary PII in claims; never log raw JWTs.
12. **Tests:** assert claims on signed tokens, reject wrong audience/issuer/time/scope, and verify API behavior.

## 19. Exercises and Self-Assessment Questions

**Exercise A — Distinguishing Audience.** An OIDC Client has ID orders-bff, and a Resource Server has ID orders-api. Specify the proper aud for the Access Token and the ID Token, and explain why the same value cannot be used for both.

**Exercise B — Designing Subject.** A user changes their email while keeping the same account. Choose a stable sub value and explain the risks of using email.

**Exercise C — TTL.** An Access Token is issued at 10:00:00 with accessTokenTimeToLive of 600 seconds. Determine the expected iat and exp; analyze the impact if a Resource Server clock is off by 5 minutes.

**Exercise D — Scope.** A client requests orders.read orders.write, but the user approves only orders.read. Write a customizer using context.getAuthorizedScopes() and test that the token omits orders.write.

**Exercise E — Audience Validator.** Write a Resource Server validator accepting only aud=orders-api, then test a JWT with audience billing-api but a valid issuer and signature.

**Exercise F — jti and Revocation.** A JWT with a unique jti is stolen. Explain why having jti alone is insufficient to revoke the token and design an appropriate state-checking mechanism.

**Review questions:**

1. How does iss differ from aud?
2. Why should sub be a stable identifier rather than an email?
3. How does an Access Token's aud differ from an ID Token's aud?
4. Which data type do iat, exp, and nbf use in JWTs?
5. How should a Resource Server handle a token whose nbf is in the future?
6. Does jti automatically prevent replay or revoke JWTs?
7. Why should scope come from authorized scopes rather than requested scopes?
8. Does OAuth2TokenCustomizer<JwtEncodingContext> apply to opaque tokens?
9. Why is an OAuth2TokenType.ACCESS_TOKEN guard needed before setting audience?
10. If a JWT has a valid signature but the wrong audience, what must the Resource Server do?
11. When upgrading Spring Authorization Server, what should you verify about default claims?
12. Why must client secrets or Refresh Tokens never be placed in JWT claims?

## 20. References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)

**Key takeaway:** iss answers **who issued it**, sub answers **whom the token represents**, aud answers **who is intended to receive it**, iat/exp/nbf define the **validity window**, jti identifies **a single token**, and scope describes **granted permissions**. The Authorization Server must issue claims from a verified context; the Resource Server must verify them for the target API. A valid JWT signature never replaces issuer, audience, timestamp, and permission checks.
