# JwtGenerator, OAuth2AccessTokenGenerator, and OAuth2RefreshTokenGenerator

## Lesson Objectives

In the **Tokens and claims** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson explains the three core Spring Authorization Server implementations used to generate tokens: **JwtGenerator**, **OAuth2AccessTokenGenerator**, and **OAuth2RefreshTokenGenerator**. They accept an **OAuth2TokenContext** and are coordinated through **DelegatingOAuth2TokenGenerator** in a **Spring Boot** application using **Spring Security**.

These three generators are not three ways of writing the same token. Each implementation handles a specific token type or format: self-contained JWT, opaque/reference access token, and refresh token. Choosing the right generator affects how the Resource Server verifies tokens, how claims are stored, revocation capability, and key operations.

After this lesson, you will be able to:

- Explain the roles of **OAuth2TokenGenerator**, **OAuth2TokenContext**, and **DelegatingOAuth2TokenGenerator**.
- Distinguish **JwtGenerator** from **OAuth2AccessTokenGenerator** according to **OAuth2TokenFormat.SELF_CONTAINED** and **OAuth2TokenFormat.REFERENCE**.
- Understand why **OAuth2RefreshTokenGenerator** generates refresh tokens separately and does not depend on the access token format.
- Register generators using the default setup or explicit configuration in **OAuth2AuthorizationServerConfigurer**.
- Use **OAuth2TokenCustomizer<JwtEncodingContext>** to customize JWT headers/claims.
- Use **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** to customize opaque access token claims.
- Configure TTLs, refresh token reuse/rotation, and consistent authorization persistence.
- Test tokens across formats, grants, clients, Resource Servers, and revocation lifecycles.

> **Running scenario:** The Authorization Server issues tokens for **inventory-worker** and **employee-portal**. Internal APIs need JWTs for local signature verification, while a partner system wants opaque tokens for centralized status lookup via introspection. Both must use accurate scopes, issuer, audience, and lifetimes; the OIDC application also requires a separate ID Token.

## 1. Overview of Token Generation

After a client is authenticated and the grant is validated, the Authorization Server must generate the requested tokens. Spring Authorization Server provides the **OAuth2TokenGenerator<T extends OAuth2Token>** interface. Its primary method is:

~~~java
T generate(OAuth2TokenContext context);
~~~

The generator receives an **OAuth2TokenContext** containing the grant details and returns a token matching **context.getTokenType()**. If the implementation does not support that token type, it returns **null** so another generator gets a chance to handle it.

Related components:

| Component | Responsibility |
|---|---|
| **OAuth2TokenContext** | Carries client, principal, authorization, grant type, scopes, token type, and Authorization Server runtime context. |
| **OAuth2TokenGenerator** | Generates a specific kind of OAuth2Token from context. |
| **JwtGenerator** | Generates JWTs used as self-contained access tokens or OIDC ID Tokens. |
| **OAuth2AccessTokenGenerator** | Generates opaque/reference access tokens. |
| **OAuth2RefreshTokenGenerator** | Generates refresh tokens. |
| **DelegatingOAuth2TokenGenerator** | Calls child generators sequentially until one returns a non-null token. |
| **OAuth2TokenCustomizer** | Customizes headers/claims while the generator constructs the token. |
| **OAuth2AuthorizationService** | Persists the authorization and related tokens/metadata after the grant provider processes them. |

**Important boundary:** A generator is responsible for **producing token values**. It does not replace client authentication, authorization grant validation, scope approval decisions, authorization storage, Resource Server token verification, or token revocation. Those responsibilities belong to other components of the Authorization Server and Resource Server.

### 1.1. Where Does Token Generation Happen in the Grant Flow?

~~~mermaid
flowchart TD
    A[HTTP request to Token Endpoint or Authorization flow] --> B[AuthenticationConverter]
    B --> C[AuthenticationProvider]
    C --> D[Validate client, grant, scope, and state]
    D --> E[OAuth2TokenContext.Builder]
    E --> F[OAuth2TokenGenerator.generate]
    F --> G{Token type / format}
    G -->|SELF_CONTAINED access token or ID Token| H[JwtGenerator]
    G -->|REFERENCE access token| I[OAuth2AccessTokenGenerator]
    G -->|refresh_token| J[OAuth2RefreshTokenGenerator]
    H --> K[OAuth2Authorization stores token]
    I --> K
    J --> K
    K --> L[Token response or authorization response]
~~~

This diagram is a conceptual model. Each grant provider builds contexts and requests the tokens it needs. For example, Client Credentials typically only needs an access token; Authorization Code may generate an access token, an ID Token when OIDC is used, and a refresh token if policy allows.

### 1.2. Token Type vs. Token Format

- **Token type** describes the purpose of the token being generated, such as **access_token**, **refresh_token**, or **id_token**.
- **Token format** describes the representation of an access token, such as a self-contained JWT or an opaque/reference token.

Do not confuse **OAuth2TokenType.ACCESS_TOKEN** with **OAuth2TokenFormat.SELF_CONTAINED**. An access token has the access token type, while its format can be either JWT or opaque depending on the RegisteredClient configuration.

## 2. OAuth2TokenContext: The Generator's Input Data

**OAuth2TokenContext** is the shared context for token generation and token customization. Important accessors include:

| Accessor | Meaning |
|---|---|
| **getRegisteredClient()** | RegisteredClient executing the grant. |
| **getPrincipal()** | Authentication of the resource owner or client depending on the grant. |
| **getAuthorizationServerContext()** | Issuer and runtime context of the Authorization Server. |
| **getAuthorization()** | Current authorization if one already exists. |
| **getAuthorizedScopes()** | Scopes actually granted for the grant. |
| **getTokenType()** | Type of token currently requested. |
| **getAuthorizationGrantType()** | Grant type being processed. |
| **getAuthorizationGrant()** | Authentication representing the incoming authorization grant. |

This context helps customizers add claims only in the right situations. For example, a **service_class** claim may apply to **inventory-worker**'s access token, but should not automatically appear in an employee's ID Token.

### 2.1. Example Context Check

~~~java
if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
        && AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                context.getAuthorizationGrantType())
        && "inventory-worker".equals(
                context.getRegisteredClient().getClientId())) {
    // Policy only for M2M access tokens of inventory-worker.
}
~~~

This is an illustrative condition used inside a customizer. Do not inspect a client ID from an arbitrary request parameter once you have the context; use the authenticated **RegisteredClient**. With multiple tenants, identify a trusted tenant source and bind it to the client/principal.

## 3. JwtGenerator: Creating Self-Contained JWTs

**JwtGenerator** implements **OAuth2TokenGenerator<Jwt>** and uses a **JwtEncoder** to sign/encode JWTs. In Spring Authorization Server, this generator is used to create:

- **JWT access tokens** when the RegisteredClient uses **OAuth2TokenFormat.SELF_CONTAINED**.
- **OIDC ID Tokens** when an OIDC flow requires an **id_token**.

A JWT typically has three Base64URL segments:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

The header usually contains **alg** and **kid**; the payload holds claims such as **iss**, **sub**, **aud**, **exp**, **iat**, **jti**, and policy-defined claims. The Resource Server can verify the signature via the public key/JWKS without calling introspection on every request, if the token profile and architecture allow it.

### 3.1. Creating a JwtGenerator

~~~java
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;

JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
~~~

**jwtEncoder** must be configured with an appropriate signing key. A common implementation uses **NimbusJwtEncoder** with **JWKSource<SecurityContext>**. Do not generate a new key on every request; keys must be managed, published via JWKS, and follow a rotation process.

Configuring JWKSource/JwtEncoder is part of the token signing infrastructure. If you already have a **JwtEncoder** or **JWKSource<SecurityContext>** bean, you do not need to create another encoder just to add claims; you can use the default generator and the appropriate customizer.

### 3.2. Customizing JWT Headers and Claims

**JwtGenerator** provides:

~~~java
jwtGenerator.setJwtCustomizer(
        OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer);
~~~

**JwtEncodingContext** allows reading the token context, adding JWS headers, and modifying claims before **JwtEncoder** signs the JWT.

Example:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                        context.getAuthorizationGrantType())
                && "inventory-worker".equals(
                        context.getRegisteredClient().getClientId())) {

            context.getClaims().claim("service_class", "inventory");
            context.getClaims().claim("policy_version", "v2");
        }
    };
}
~~~

The claims here illustrate **non-sensitive** data specific to one client's access token. Do not apply the same logic to ID Tokens unless there is an explicit OIDC requirement. Do not add secrets, private keys, passwords, refresh tokens, or unnecessary personal data.

If custom headers are needed, the context provides **getJwsHeader()**:

~~~java
context.getJwsHeader().keyId("active-signing-key");
~~~

Normally **kid** and the algorithm should be managed by the **JwtEncoder/JWK configuration**. Only modify the header when there is a clear compatibility reason and key rotation process; never force a weak algorithm or a client-requested algorithm.

### 3.3. Do Not Arbitrarily Overwrite Standard Claims

Claims such as **iss**, **sub**, **aud**, **exp**, **iat**, **jti**, and **scope** carry protocol/security semantics. If a customizer alters them incorrectly:

- The Resource Server may reject the token due to an invalid issuer/audience.
- The token may live longer than the configured TTL.
- Scopes in the token may no longer match **OAuth2Authorization.authorizedScopes**.
- The ID Token may become invalid under OIDC Core.
- Auditing and introspection may misinterpret the subject/target.

Only add claims that have an owner, clear meaning, trusted data source, and a validator on the Resource Server. If you need to change the audience, configure it based on the actual target API receiving the token, never from an unverified parameter.

## 4. OAuth2AccessTokenGenerator: Creating Opaque/Reference Access Tokens

**OAuth2AccessTokenGenerator** produces **reference/opaque** access tokens. The token sent to the client is an opaque string that does not self-describe claims like a JWT. The Authorization Server stores token state in **OAuth2AuthorizationService**; the Resource Server typically checks it via **Token Introspection** or a dedicated lookup mechanism.

### 4.1. When Is This Generator Used?

Spring Authorization Server selects the access token format based on **TokenSettings.getAccessTokenFormat()** of the RegisteredClient:

| Access token format | Generator | Token the client receives |
|---|---|---|
| **OAuth2TokenFormat.SELF_CONTAINED** (default) | **JwtGenerator** | Self-contained JWT, verifiable via signature/JWKS. |
| **OAuth2TokenFormat.REFERENCE** | **OAuth2AccessTokenGenerator** | Opaque token; state/claims are stored at the Authorization Server. |

Example client using an opaque access token:

~~~java
RegisteredClient partnerApi = RegisteredClient
        .withId("partner-api-v1")
        .clientId("partner-api")
        .clientSecret(passwordEncoder.encode(partnerSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
~~~

This is an illustrative client registration; it requires a **PasswordEncoder**, secret source, repository, and other beans. With an opaque token, the client still receives an access token to send in the Bearer header; only the Resource Server needs to know how to look up token state.

### 4.2. Customizing Opaque Access Token Claims

**OAuth2AccessTokenGenerator** has the method:

~~~java
accessTokenGenerator.setAccessTokenCustomizer(
        OAuth2TokenCustomizer<OAuth2TokenClaimsContext> accessTokenCustomizer);
~~~

**OAuth2TokenClaimsContext** provides **getClaims()** to add, replace, or remove claims on opaque access tokens. Example:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueAccessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "partner-api".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("integration_tier", "partner");
        }
    };
}
~~~

These claims are not embedded in plaintext inside the opaque token string; they are attached to the authorization/token record so the Authorization Server can return corresponding information during introspection when permitted. Do not assume the Resource Server can Base64-decode an opaque token.

### 4.3. Benefits and Operational Trade-offs

| Characteristic | Opaque/reference |
|---|---|
| Claim visibility | Cannot be read directly from the token string. |
| Status checks | Typically requires introspection or a trusted lookup. |
| Revocation | The Authorization Server can mark the token inactive in storage; effectiveness depends on cache/introspection policy. |
| Network dependency | The Resource Server may need to call the AS, requiring timeouts, caching, and handling AS unavailability. |
| Metadata exposure | The token string does not expose claims directly like a JWT, though the token itself remains a secret Bearer credential. |
| Scalability | Requires DB/storage and introspection capacity aligned with API traffic. |

Opaque tokens are not automatically safer than JWTs in every situation. The choice depends on revocation requirements, latency, HA, claim sensitivity, and introspection operability.

## 5. OAuth2RefreshTokenGenerator: Creating Refresh Tokens

**OAuth2RefreshTokenGenerator** generates **OAuth2RefreshToken** instances used to obtain new access tokens in grants/clients permitted to use refresh tokens. It is a token with its own lifecycle and policy, not a second access token.

Key characteristics:

- The generator is called when **OAuth2TokenContext.getTokenType()** is **refresh_token**.
- The token is normally a random opaque value, not a JWT access token.
- Lifetime is governed by **TokenSettings.refreshTokenTimeToLive(...)**.
- Whether a grant provider requests a refresh token depends on the grant, client registration, and policy.
- **OAuth2RefreshTokenGenerator** does not expose a public **OAuth2TokenCustomizer** like **JwtGenerator** or **OAuth2AccessTokenGenerator** in the standard API.
- Refresh tokens must be strictly protected, because anyone holding one can request new access tokens under valid conditions.

### 5.1. Configuring TTL and Rotation

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(14))
        .reuseRefreshTokens(false)
        .build();
~~~

- **accessTokenTimeToLive**: lifetime of the access token.
- **refreshTokenTimeToLive**: lifetime of the refresh token.
- **reuseRefreshTokens(true)**: configures refresh token reuse per the documented default behavior.
- **reuseRefreshTokens(false)**: requests issuing a new refresh token upon successful refresh; verify that the old token is invalidated and cannot be reused within the framework's flow.

**Refresh token rotation is not just swapping strings in the response.** The Authorization Server must persist the new refresh token state, mark the old state per policy, protect against replay, and handle concurrent requests. If a custom generator produces a token without attaching it to **OAuth2Authorization**, the next refresh attempt will fail to find a valid token or may introduce a replay vulnerability.

### 5.2. Refresh Tokens Do Not Exist in Every Grant

| Grant | Refresh token |
|---|---|
| Authorization Code | May be issued if allowed by client/grant/policy. |
| OIDC Authorization Code | May be issued per similar policy; the ID Token does not replace a refresh token. |
| Client Credentials | RFC 6749 section 4.4.3 recommends **SHOULD NOT** be issued. |
| Device Authorization | May be issued depending on grant and client configuration/policy. |
| Refresh Token Grant | Consumes an existing refresh token; may return a new token when rotation is enabled. |

Do not enable **refresh_token** for a client just to extend sessions. With Client Credentials, the client should request a new access token using its own client credentials when the token expires, per RFC 6749 recommendations.

### 5.3. Should You Customize Refresh Tokens into JWTs?

Do not do this just to "standardize the format". A refresh token is a long-lived credential that requires status checking, rotation, and revocation. Self-contained JWTs can be difficult to revoke immediately unless the Resource Server/Authorization Server performs centralized state checks.

If a custom refresh token format is required, implement a controlled **OAuth2TokenGenerator<OAuth2RefreshToken>** and ensure:

- Sufficient entropy to prevent guessing and collisions.
- Accurate TTL, client association, and principal/grant association.
- Persistence and invalidation/replay protection.
- Atomic rotation under concurrent requests.
- No sensitive claims placed inside the token value or logs.

For most systems, keeping the default **OAuth2RefreshTokenGenerator** and using **TokenSettings** to manage TTL/reuse is simpler and easier to verify.

## 6. DelegatingOAuth2TokenGenerator Coordinates the Generators

**DelegatingOAuth2TokenGenerator** takes a list of **OAuth2TokenGenerator** instances. It calls **generate(context)** sequentially; **the first non-null token is returned**. If all return **null**, no generator supported that context.

~~~java
OAuth2TokenGenerator<OAuth2Token> tokenGenerator =
        new DelegatingOAuth2TokenGenerator(
                jwtGenerator,
                accessTokenGenerator,
                refreshTokenGenerator);
~~~

With standard configuration, each generator checks the token type/format and handles only what it supports. For example:

| Context | JwtGenerator | OAuth2AccessTokenGenerator | OAuth2RefreshTokenGenerator |
|---|---|---|---|
| Access token SELF_CONTAINED | Creates JWT | Ignores | Ignores |
| Access token REFERENCE | Ignores | Creates opaque access token | Ignores |
| Refresh token | Ignores | Ignores | Creates refresh token |
| OIDC ID Token | Creates JWT ID Token | Ignores | Ignores |

Order is especially important when a custom generator might handle the same token type as another generator. A custom generator must return **null** when it does not support a context and return a token only when all policy requirements are met. Do not put a catch-all generator at the front of the list returning a default value.

### 6.1. Explicit Generator Configuration

The example below follows the Spring Authorization Server **1.5.x** API. It assumes the application already has a **JWKSource<SecurityContext>** and the required persistence/security beans.

~~~java
package com.example.authserver.config;

import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Configuration(proxyBeanMethods = false)
class TokenGeneratorConfiguration {

    @Bean
    OAuth2TokenGenerator<?> tokenGenerator(
            JWKSource<SecurityContext> jwkSource,
            OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
            OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer) {

        JwtGenerator jwtGenerator =
                new JwtGenerator(new NimbusJwtEncoder(jwkSource));
        jwtGenerator.setJwtCustomizer(jwtCustomizer);

        OAuth2AccessTokenGenerator accessTokenGenerator =
                new OAuth2AccessTokenGenerator();
        accessTokenGenerator.setAccessTokenCustomizer(opaqueCustomizer);

        OAuth2RefreshTokenGenerator refreshTokenGenerator =
                new OAuth2RefreshTokenGenerator();

        return new DelegatingOAuth2TokenGenerator(
                jwtGenerator,
                accessTokenGenerator,
                refreshTokenGenerator);
    }
}
~~~

This configuration creates:
- A JWT generator for self-contained access tokens and OIDC ID Tokens.
- An opaque access token generator for clients configured with the **REFERENCE** format.
- A refresh token generator for grants/providers requiring refresh tokens.

### 6.2. Attaching the Generator to the Authorization Server

In the Authorization Server SecurityFilterChain, configure the token generator:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    var authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, configurer ->
                configurer.tokenGenerator(tokenGenerator))
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is a configuration skeleton; a complete application also requires **AuthorizationServerSettings**, **RegisteredClientRepository**, **OAuth2AuthorizationService**, signing/JWK setup, a login chain, and actual endpoints/features. If using a newer API from the Spring Security branch with integrated Authorization Server support, verify the configurer factory methods and package names against your project's dependencies.

**Note on default configuration:** **OAuth2TokenGenerator** is an optional component. Spring Authorization Server can auto-configure a **DelegatingOAuth2TokenGenerator** consisting of **OAuth2AccessTokenGenerator** and **OAuth2RefreshTokenGenerator**; when a **JwtEncoder** or **JWKSource<SecurityContext>** is present, **JwtGenerator** is added. Once you declare a custom generator bean or call **tokenGenerator(...)** on the configurer, you are responsible for providing implementations for all token types/formats your application supports.

## 7. Two Types of Access-Token Customizers

### 7.1. JWT Claims: OAuth2TokenCustomizer<JwtEncodingContext>

Used for JWTs generated by **JwtGenerator**. The context lets you customize **JwsHeader.Builder** and **JwtClaimsSet.Builder**. Always restrict by token type, grant, and client:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtAccessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "inventory-worker".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("service_class", "inventory");
        }
    };
}
~~~

If the same customizer also runs for ID Tokens, the **ACCESS_TOKEN** check prevents API-only claims from being added to user ID Tokens. To customize ID Tokens, check the corresponding OIDC token type and separate OIDC Core requirements.

### 7.2. Opaque Claims: OAuth2TokenCustomizer<OAuth2TokenClaimsContext>

Used for **OAuth2AccessTokenGenerator**. Example:

~~~java
@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && "partner-api".equals(
                        context.getRegisteredClient().getClientId())) {
            context.getClaims().claim("integration_tier", "partner");
        }
    };
}
~~~

Claims are saved with the token/authorization so introspection can provide them to the Resource Server per policy. The client still sees only an opaque token and cannot decode it to read **integration_tier**.

### 7.3. Do Not Mix Up Customizers

| Requirement | Component to use |
|---|---|
| Add claim/header to JWT access token | **JwtGenerator.setJwtCustomizer(...)** |
| Add claim to JWT ID Token | **JwtGenerator** + customizer checking ID Token context and OIDC rules. |
| Add claim to opaque access token | **OAuth2AccessTokenGenerator.setAccessTokenCustomizer(...)** |
| Generate default refresh token | **OAuth2RefreshTokenGenerator**; manage TTL/reuse via **TokenSettings**. |
| Change access token lifetime | **TokenSettings.accessTokenTimeToLive(...)**. |
| Change refresh token lifetime | **TokenSettings.refreshTokenTimeToLive(...)**. |
| Change access token format | **TokenSettings.accessTokenFormat(...)**. |
| Completely replace token format/algorithm | Custom **OAuth2TokenGenerator** with matching contract/persistence. |

**OAuth2RefreshTokenGenerator** has no claims customizer setter equivalent to the two access-token generators. Do not try to use **JwtEncodingContext** to add claims to default opaque refresh tokens.

## 8. TokenSettings Governs Format and Lifecycle

**TokenSettings** belongs to **RegisteredClient**, allowing per-client policies. Example:

~~~java
TokenSettings settings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(14))
        .reuseRefreshTokens(false)
        .build();

RegisteredClient client = RegisteredClient.withId("employee-portal-v1")
        .clientId("employee-portal")
        // Add client authentication, grant, redirect URI, scope...
        .tokenSettings(settings)
        .build();
~~~

Meaning:

- **SELF_CONTAINED**: access token is a JWT; Resource Server verifies signature and claims.
- **REFERENCE**: access token is opaque; Resource Server typically introspects.
- **accessTokenTimeToLive**: access token lifetime.
- **refreshTokenTimeToLive**: refresh token lifetime.
- **reuseRefreshTokens**: chooses between reusing or issuing a new refresh token on a successful refresh grant.

Do not share one long TTL across all clients when risk levels differ. M2M clients, browser-facing clients, partners, and admin apps may require different token lifetimes, formats, audiences, and refresh policies.

### 8.1. Access Tokens and Refresh Tokens Have Independent Lifecycles

An access token may live 5 minutes while a refresh token lives 14 days. When the access token expires, the client can use the refresh token if the grant and policy allow it. If the refresh token is revoked or expired, the client must re-initiate authorization via the appropriate grant.

**Do not confuse refresh token lifetime with authorization lifetime** or user login session lifetime. A successful refresh does not necessarily extend consent, session, or business permissions that have already been revoked.

## 9. Persisting Authorizations and Claims

After a generator creates a token, the grant provider places the token into **OAuth2Authorization** and saves it via **OAuth2AuthorizationService**. The authorization model links:

- Internal registered client ID.
- Principal name (resource owner or client).
- Grant type.
- Authorized scopes.
- Corresponding tokens and metadata, such as issued/expiry/invalidated timestamps.
- Grant-related attributes, such as the authorization request or principal.

If a token implements **ClaimAccessor** and carries claims, they can be accessed via **OAuth2Authorization.Token.getClaims()**. This is useful for opaque tokens/introspection and supports controlled auditing/diagnostics.

### 9.1. Why Not Construct Tokens Outside the Provider?

If you manually call **new OAuth2AccessToken(...)** in a controller and return it to a client:

- The token may not be saved in **OAuth2AuthorizationService**.
- Introspection/revocation will not recognize the token.
- Authorized scopes and principal may not match.
- Refresh token rotation will lack old/new state tracking.
- JWTs may not be signed with the proper key/JWS algorithm.
- The token response may return a token incompatible with the provider/Resource Server.

Always let the grant provider invoke the appropriate generator and persist the authorization through the service. If a custom format is required, implement a generator while still integrating with the standard provider/persistence lifecycle.

## 10. Security When Customizing Token Generators

### 10.1. Claim Hygiene and Least Privilege

- Put only data that the Resource Server genuinely needs into tokens.
- Never embed passwords, secrets, private keys, refresh tokens, session data, or unnecessary PII.
- Avoid custom claim names that collide with standard claims or claims defined by OIDC/JWT profiles.
- Never let a client supply role/tenant claims without a verified data source.
- Scopes in the token must reflect actually granted permissions; never escalate scopes in a customizer.
- Distinguish access tokens from ID Tokens; do not put API permissions into an ID Token just because both are created by JwtGenerator.

### 10.2. JWT Signing and Key Management

- Use supported JWS algorithms and explicit policies.
- Manage private signing keys in KMS/HSM/keystore as appropriate; restrict read access and audit usage.
- Publish public keys via JWKS and keep old keys long enough to cover valid tokens during rotation.
- The Resource Server must verify signature, **iss**, **aud**, **exp**, and profile-specific claims.
- Never trust a JWT merely because its payload decodes or its header specifies a desired algorithm.

### 10.3. Opaque Tokens and Introspection

- The introspection endpoint must require an authorized client/resource server.
- Protect cached tokens and never log request bodies containing tokens.
- Cache **active** responses with a TTL aligned with revocation requirements; caching too long can preserve access after a token is revoked.
- If the Authorization Server is unavailable, the Resource Server must fail closed or follow an approved policy; never treat tokens as active by default.
- Keep authorization data consistent across multiple instances.

### 10.4. Refresh Token Rotation and Replay

When **reuseRefreshTokens(false)** is set, test that:

- Old refresh tokens cannot continue to be used after rotation per policy.
- Two concurrent requests cannot both exchange the same refresh token into two valid authorization states.
- New tokens remain bound to the right client, principal, scope, and authorization.
- Logout/revocation/client disablement takes effect per policy.
- Logs never contain raw refresh tokens.

Never invent sequential refresh tokens or use unprotected UUIDs as tokens. A refresh token is a long-lived credential requiring proper entropy, storage, and replay protection.

## 11. Testing the Three Generators and Delegation

### 11.1. Token Type/Format Matrix

| Test | Expectation |
|---|---|
| SELF_CONTAINED access token | **JwtGenerator** returns a JWT with valid signature/claims. |
| REFERENCE access token | **OAuth2AccessTokenGenerator** creates an opaque token; claims cannot be read from the token string. |
| OIDC ID Token | **JwtGenerator** creates an ID Token matching the OIDC context. |
| Refresh token when permitted by grant | **OAuth2RefreshTokenGenerator** creates a refresh token with policy-compliant TTL. |
| Context unsupported by generator | Generator returns **null** so delegation continues. |
| Custom generator returns token | **DelegatingOAuth2TokenGenerator** stops at the first non-null result. |
| JWT customizer | Claims appear only for the intended client/grant/token type. |
| Opaque customizer | Claims are stored in the authorization and appear in introspection if policy allows. |
| Client Credentials | No refresh token issued per standard grant policy. |
| Refresh token rotation | New token is saved and old token cannot be reused per policy. |

### 11.2. Testing the Self-Contained Format

For JWT access tokens:

1. Obtain a token from the Token Endpoint in the test environment.
2. Use **JwtDecoder** or a Resource Server test to verify the signature.
3. Assert **iss**, **aud**, **exp**, **scope**, and custom claims.
4. Tamper with the payload or signature; the token must be rejected.
5. Test a validly signed token with the wrong audience; the Resource Server must reject it.

Do not rely solely on a Base64 decoder and JSON comparison; that does not verify signatures.

### 11.3. Testing Opaque Tokens

For **REFERENCE**:

1. Register a client with **TokenSettings.accessTokenFormat(OAuth2TokenFormat.REFERENCE)**.
2. Request a token using a valid grant.
3. Submit the token to the introspection endpoint using an authorized client.
4. Verify **active**, client, scope, and appropriate claims.
5. Revoke the token/authorization and call introspection again per cache policy.
6. Verify the token cannot be used once the server marks it inactive (accounting for acceptable cache delay).

### 11.4. Testing Refresh Tokens

- Authorization Code/OIDC clients allowed to refresh receive tokens per policy.
- Client Credentials does not receive a refresh token under standard policy.
- Expired or revoked tokens cannot be refreshed.
- With rotation enabled, old refresh tokens cannot be reused.
- Invalid client authentication or mismatched client IDs are rejected.
- Scopes after refresh cannot escalate beyond previously granted permissions.
- Authorization persistence after refresh accurately reflects the new token and old token state.

### 11.5. Small Test Example for Generator Delegation

The snippet below demonstrates the first-non-null principle and does not replace framework integration tests:

~~~java
OAuth2TokenGenerator<OAuth2Token> delegate =
        new DelegatingOAuth2TokenGenerator(
                context -> null,
                context -> expectedToken);

OAuth2Token actual = delegate.generate(tokenContext);

assertThat(actual).isSameAs(expectedToken);
~~~

Real tests must build a valid **OAuth2TokenContext** and token fixtures; this example only verifies delegation semantics. Standard generators must also be tested against token types, token formats, and grants.

## 12. Common Pitfalls and Fixes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Client expects JWT but gets opaque | RegisteredClient uses **REFERENCE** or JwtGenerator is missing from delegate. | Check **TokenSettings**, **JwtEncoder/JWK**, and token generator config. |
| Client receives JWT but API fails to verify | Wrong key/JWKS, issuer, audience, or algorithm. | Check signing key, JWKS, validators, and clock. |
| Custom claims missing from JWT | **jwtCustomizer** not attached to JwtGenerator or token type/client condition mismatches. | Check customizer bean and context. |
| Custom claims missing from opaque introspection | Wrong customizer type or authorization does not store claims. | Use **OAuth2TokenClaimsContext** and check storage/introspection mapping. |
| OIDC ID Token loses claims | Customizer only handles access tokens or generator config lacks JWT. | Check OIDC context and **JwtGenerator**. |
| Refresh token not issued | Grant/client/provider does not request it or policy forbids it. | Check grant, client settings, and authorization flow type. |
| Old refresh token still works after rotation | Incorrect reuse policy, persistence, or invalidation. | Check **reuseRefreshTokens** and authorization state. |
| No generator supports context | Delegate is missing a generator for that format/type. | Add the corresponding generator, keep proper order, and test null returns. |
| Custom generator breaks other grants | Generator catches all contexts or returns wrong token type. | Return null when unsupported and restrict by context. |
| Token rejected by Resource Server after customizer | Standard claim overwritten or invalid audience/issuer. | Add only necessary claims and preserve protocol claims. |
| Revoked token still accepted by API | Offline JWT validation or overly long introspection cache. | Shorter TTL, introspection/cache policy, or revocation mechanism. |
| Sensitive claims appear in logs | Logging full context/token/authorization objects. | Redact, log only approved metadata, and never log raw tokens. |

## 13. Hands-On Exercise

**Context:** The Authorization Server issues tokens for three clients:

- **inventory-worker** using Client Credentials, JWT access token, scope **inventory.read**.
- **partner-api** using Client Credentials, opaque access token, scope **orders.read**.
- **employee-portal** using Authorization Code + OIDC, requiring ID Token and refresh token per policy.

Requirements:

1. Configure **TokenSettings** for each RegisteredClient with the appropriate access token format/TTL.
2. Create a **JwtGenerator** using **NimbusJwtEncoder** and a managed JWK source.
3. Create an **OAuth2AccessTokenGenerator** and an **OAuth2RefreshTokenGenerator**.
4. Combine them using **DelegatingOAuth2TokenGenerator** and register with **OAuth2AuthorizationServerConfigurer**.
5. Create an **OAuth2TokenCustomizer<JwtEncodingContext>** that adds claims only to **inventory-worker**'s access token.
6. Create an **OAuth2TokenCustomizer<OAuth2TokenClaimsContext>** for **partner-api**'s opaque access token.
7. Verify that **JwtGenerator** still generates OIDC ID Tokens for **employee-portal**.
8. Configure **refreshTokenTimeToLive** and **reuseRefreshTokens(false)** for clients allowed to refresh.
9. Test introspection, JWT signature/audience, refresh rotation, revocation, and invalid requests.
10. Verify that logs/tracing contain no tokens, secrets, sensitive claims, or private keys.

**Completion criteria:** Each client receives the token format matching its registration; JWT and opaque claims are customized in the right context; ID Tokens remain unaffected; refresh tokens are issued only when the grant permits; authorization persistence, introspection, and rotation behave consistently.

## 14. Pre-Deployment Checklist

- [ ] Token type and token format are clearly distinguished.
- [ ] **JwtGenerator** uses **JwtEncoder**/JWK and generates JWTs for the intended contexts.
- [ ] **OAuth2AccessTokenGenerator** is used only for reference/opaque access tokens.
- [ ] **OAuth2RefreshTokenGenerator** generates refresh tokens per grant/provider policy.
- [ ] **DelegatingOAuth2TokenGenerator** includes all required generators with verified ordering.
- [ ] JWT and opaque customizers use the right context types.
- [ ] Claims are scoped to client, grant, token type, and trusted data sources.
- [ ] Standard **iss**, **sub**, **aud**, **exp**, **iat**, **jti**, or scopes are never overwritten contrary to policy.
- [ ] TokenSettings format/TTL/reuse match each RegisteredClient.
- [ ] AuthorizationService durably stores tokens/claims and invalidation state.
- [ ] Resource Server verifies signature/issuer/audience or introspection per policy.
- [ ] Refresh rotation has replay protection and concurrency tests.
- [ ] Key rotation/JWKS, caching, revocation, and multi-replica behavior are accounted for.
- [ ] Logs/traces contain no raw access tokens, refresh tokens, client secrets, or private keys.
- [ ] JWT, opaque, OIDC ID Token, refresh token, and all supported grants are tested.

## Summary

**JwtGenerator**, **OAuth2AccessTokenGenerator**, and **OAuth2RefreshTokenGenerator** are the three implementations serving different token generation needs in Spring Authorization Server. **JwtGenerator** creates self-contained JWTs for access tokens/ID Tokens; **OAuth2AccessTokenGenerator** creates opaque/reference access tokens; **OAuth2RefreshTokenGenerator** creates refresh tokens. **DelegatingOAuth2TokenGenerator** coordinates them by choosing the first generator that returns a non-null result.

Choosing the right generator must go hand in hand with **TokenSettings**, the right context customizer, **OAuth2AuthorizationService**, and Resource Server policy. Never use a customizer to escalate privileges, never create tokens outside a grant provider, and never treat JWT signing as a substitute for introspection/revocation when your system requires centralized state.

## References

1. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2TokenContext, OAuth2TokenGenerator, default generators, token customizers, and token claims.
2. [Spring Authorization Server 1.5.3 — JwtGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/JwtGenerator.html): generating JWT access tokens/ID Tokens and setJwtCustomizer.
3. [Spring Authorization Server 1.5.3 — OAuth2AccessTokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2AccessTokenGenerator.html): opaque access tokens and setAccessTokenCustomizer.
4. [Spring Authorization Server 1.5.3 — OAuth2RefreshTokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2RefreshTokenGenerator.html): refresh token generation.
5. [Spring Authorization Server 1.5.8 — DelegatingOAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/DelegatingOAuth2TokenGenerator.html): delegation by first non-null result.
6. [Spring Authorization Server 1.5.3 — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): interface for generating tokens from context.
7. [Spring Authorization Server 1.5.3 — TokenSettings API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): access format, access/refresh TTL, and refresh token reuse.
8. [Spring Authorization Server — Custom JWT Claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): JWT customizer examples.
9. [Spring Authorization Server — Extension Authorization Grant](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): integrating token generators with custom grant providers.
10. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and standard claims.
11. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile and validation.
12. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): looking up opaque/reference token state.
13. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoking access tokens and refresh tokens.
