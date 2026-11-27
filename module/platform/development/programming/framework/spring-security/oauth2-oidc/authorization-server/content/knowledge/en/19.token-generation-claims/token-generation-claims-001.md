# OAuth2TokenGenerator and DelegatingOAuth2TokenGenerator

> **Chapter:** Tokens and claims  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Scope:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Illustrated versions:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.x (Servlet stack). For Spring Security 7.x integrating Authorization Server, verify package names and DSLs against the actual version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the `OAuth2TokenGenerator<T extends OAuth2Token>` contract, its `OAuth2TokenContext` input, and the return value of `generate(...)`.
2. Describe how `DelegatingOAuth2TokenGenerator` tries generators in order and **picks the first non-null token**.
3. Distinguish between `JwtGenerator`, `OAuth2AccessTokenGenerator`, and `OAuth2RefreshTokenGenerator`.
4. Understand how `RegisteredClient` and `TokenSettings` determine whether an access token is a self-contained JWT or a reference/opaque access token.
5. Configure `JwtEncoder`, `DelegatingOAuth2TokenGenerator`, and the two types of `OAuth2TokenCustomizer` for JWT and opaque tokens.
6. Distinguish between OAuth2 access tokens, OIDC ID tokens, and refresh tokens so you do not mix up claims, audience, and principal.
7. Test token generators from unit tests to end-to-end tests, covering signature, issuer, audience, TTL, scope, introspection, and refresh.
8. Identify common pitfalls when replacing the default generator, especially missing the JWT or refresh generator or misconfiguring a customizer.

**Key takeaway:** A token generator is **the step that creates a token artifact from an already-processed context**. It does not perform OAuth2 Client authentication, grant approval, consent checking, or Resource Server data access verification on its own.

## 2. Where Does Token Generation Sit in the Authorization Server?

Example Client Credentials Grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

To respond with an access token, Spring Authorization Server needs to:

1. Authenticate/identify the Client according to `RegisteredClientRepository` and the registered authentication method.
2. Verify that the Client is allowed to use `client_credentials`, the requested scope matches, and the grant satisfies policy.
3. The grant `AuthenticationProvider` builds an `OAuth2TokenContext` containing the RegisteredClient, principal, token type, authorized scopes, and related data.
4. `OAuth2TokenGenerator` generates the access token according to policy.
5. `OAuth2AuthorizationService` persists the authorization/token state and appropriate metadata.
6. The token endpoint returns the OAuth2 response with `access_token`, `token_type`, `expires_in`, etc.

~~~mermaid
flowchart TD
    REQ["POST /oauth2/token"]
    CLIENT["Client authentication<br/>RegisteredClient"]
    GRANT["Grant AuthenticationProvider<br/>grant type + scope + policy"]
    CONTEXT["OAuth2TokenContext<br/>tokenType, client, principal, scopes"]
    DELEGATE["DelegatingOAuth2TokenGenerator"]
    JWT["JwtGenerator"]
    OPAQUE["OAuth2AccessTokenGenerator"]
    REFRESH["OAuth2RefreshTokenGenerator"]
    STORE[("OAuth2AuthorizationService")]
    RESP["OAuth2 token response"]
    ERROR["OAuth2 error<br/>no token issued"]

    REQ --> CLIENT --> GRANT
    GRANT -->|"Invalid"| ERROR
    GRANT -->|"Valid"| CONTEXT --> DELEGATE
    DELEGATE --> JWT
    JWT -->|"Not applicable: null"| OPAQUE
    OPAQUE -->|"Not applicable: null"| REFRESH
    JWT -->|"JWT / ID token"| STORE
    OPAQUE -->|"Reference access token"| STORE
    REFRESH -->|"Refresh token"| STORE
    STORE --> RESP
~~~

The diagram summarizes the logic of **a single `generate(context)` call**. A provider may need to call the generator multiple times with different token types within the same grant; the exact timing of saving tokens/authorizations depends on the provider. **The delegating generator does not write directly to the database.**

### 2.1. Separation of Responsibilities

| Component | What does it do? | What does it NOT do? |
| --- | --- | --- |
| `OAuth2ClientAuthenticationFilter` | Authenticates the OAuth2 Client | Does not sign access tokens |
| Grant `AuthenticationProvider` | Checks grant, scopes, code, PKCE, refresh binding | Is not a JWK key store |
| `OAuth2TokenContext` | Carries the normalized token-issuance context | Does not replace the authorization DB |
| `OAuth2TokenGenerator` | Creates an `OAuth2Token` | Does not decide on its own whether a client may use a grant |
| `DelegatingOAuth2TokenGenerator` | Selects the appropriate generator | Does not fall back after a signing error to relax policy |
| `JwtEncoder` and `JWKSource` | Produces the JWT signature | Does not check object-level authorization |
| `OAuth2AuthorizationService` | Stores authorization/token state | Does not verify JWTs at the Resource Server |
| Resource Server | Verifies access tokens and API access rights | Is not the AS token-generation component |

Do not put "permission to read all bookings" logic into the generator just because it can add claims. A client/user with a scope must still pass ownership/tenant checks at the Resource Server.

## 3. The `OAuth2TokenGenerator` Contract

Conceptually key API:

~~~java
public interface OAuth2TokenGenerator<T extends OAuth2Token> {

    @Nullable
    T generate(OAuth2TokenContext context);
}
~~~

This is an abbreviated signature for explanation; obtain exact packages and annotations from the Javadoc for your specific Spring Authorization Server version.

- **Input:** `OAuth2TokenContext` describing the token to be generated and authorization data.
- **Output:** an `OAuth2Token` or a subtype such as `Jwt`, `OAuth2AccessToken`, or `OAuth2RefreshToken`.
- **`null`:** the generator does not produce a token for the current context; `DelegatingOAuth2TokenGenerator` is allowed to try the next generator.
- **Exception:** token generation genuinely failed, for example a signer error. Do not equate an exception with `null`; do not ignore security errors to issue another token type.

### 3.1. Token Type and Java Object Do Not Match One-to-One

| Token type or requirement | Object that may be created | Notes |
| --- | --- | --- |
| `OAuth2TokenType.ACCESS_TOKEN`, self-contained | `Jwt` | Signed JWT, typically converted by the provider into the OAuth2 access token response |
| `OAuth2TokenType.ACCESS_TOKEN`, reference | `OAuth2AccessToken` | Opaque string, metadata stored on the AS side |
| `OAuth2TokenType.REFRESH_TOKEN` | `OAuth2RefreshToken` | Credential used to request a new access token |
| OIDC `id_token` | `Jwt` | An OIDC ID token differs from a JWT access token in purpose and audience |
| `code` | Authorization code managed by the authorization flow | Do not treat an authorization code as a JWT access token |

A `Jwt` implements `OAuth2Token`, but its claims differ from how `OAuth2AccessToken` is stored. The provider and authorization storage connect the generated token to the protocol.

## 4. What Information Does `OAuth2TokenContext` Provide?

According to the Spring Authorization Server core model:

| Accessor | Meaning | Caution |
| --- | --- | --- |
| `getRegisteredClient()` | Client registration recognized by the AS | Not a raw, unverified `client_id` |
| `getPrincipal()` | `Authentication` of the Resource Owner or Client | Client Credentials has no logged-in user |
| `getAuthorizationServerContext()` | AS runtime information, including issuer | Issuer must be the proper HTTPS/public URL |
| `getAuthorization()` | Existing authorization, **may be null** | A new grant does not necessarily have a prior record |
| `getAuthorizedScopes()` | Scopes actually granted | Do not escalate to all registered scopes |
| `getTokenType()` | Type of token being requested | Used to select and customize claims |
| `getAuthorizationGrantType()` | Grant currently being processed | Distinguishes user grants from client grants |
| `getAuthorizationGrant()` | `Authentication` of the processed grant | Do not log credentials |

### 4.1. Registered Scopes Are Not Authorized Scopes

Suppose a Client registers `openid`, `booking.read`, `booking.write`, and `profile`, while the Resource Owner only approves `openid` and `booking.read`.

`RegisteredClient.getScopes()` may contain **four** scopes; `context.getAuthorizedScopes()` in the corresponding grant must only reflect the scopes **that were granted**. A customizer that uses all registered scopes to build claims risks exceeding consent.

Do not take an arbitrary `scope` parameter from the HTTP token request and attach it verbatim to the JWT. The grant provider must validate the request against the client registration and actual authorization.

### 4.2. The Principal Can Be a User or a Client

In Authorization Code, the principal is typically the authenticated Resource Owner. In Client Credentials, the principal is typically the OAuth2 Client. Therefore, the example below can fail:

~~~java
// Not valid for every grant:
UserDetails user =
    (UserDetails) context.getPrincipal().getPrincipal();
~~~

If user-specific claims are needed, restrict by grant type and validate the principal type, or use a service that reads user data from a trusted source. Do not assume that `sub` of every access token is a user ID.

### 4.3. The Context Can Appear Multiple Times in One Grant

In Authorization Code + OIDC, the provider may need an access token, a refresh token (if the grant/client is permitted), and an ID token. Each generation call has a specific `getTokenType()`. The customizer must know **which token type** it is adding claims to and not apply API data indiscriminately to the ID token.

## 5. How Does `DelegatingOAuth2TokenGenerator` Select a Result?

`DelegatingOAuth2TokenGenerator` is initialized with a list of generators. Each generator receives the context in turn; **the first non-null token is returned**.

Pseudocode:

~~~java
// Pseudocode to explain the contract, not framework source code.
OAuth2Token generate(OAuth2TokenContext context) {
    for (OAuth2TokenGenerator<? extends OAuth2Token> generator
            : generators) {
        OAuth2Token token = generator.generate(context);
        if (token != null) {
            return token;
        }
    }
    return null;
}
~~~

Consequences:

1. **Order matters**: earlier generators get the opportunity to decide the result first.
2. **`null` is normal** when a generator does not support the current token type/format.
3. **A non-null result ends the loop**; subsequent generators are not called.
4. **An exception is not a signal to continue**: a JWT signing error must not be swallowed and turned into an opaque token fallback contrary to policy.
5. A provider that needs multiple tokens can call `generate(...)` multiple times with different token types.

### 5.1. Three Common Generators

| Generator | Primary role | Cases where it returns null |
| --- | --- | --- |
| `JwtGenerator` | Creates self-contained JWT access tokens and JWTs for OIDC ID tokens | `REFERENCE` access token or refresh token requested |
| `OAuth2AccessTokenGenerator` | Creates reference/opaque access tokens | Token type is not access token, or format is not reference |
| `OAuth2RefreshTokenGenerator` | Creates refresh tokens per policy | Not a refresh token, or grant/client is not issued an RT |

A custom generator can be added, but it must accurately support the token type and format. A generator that always returns a token regardless of what the context requests can completely block all remaining generators.

### 5.2. Common Selection Table

| `getTokenType()` | `TokenSettings.accessTokenFormat` | Selected generator | Result |
| --- | --- | --- | --- |
| `ACCESS_TOKEN` | `SELF_CONTAINED` | `JwtGenerator` | Signed JWT |
| `ACCESS_TOKEN` | `REFERENCE` | `OAuth2AccessTokenGenerator` | Opaque/reference access token |
| `REFRESH_TOKEN` | Does not directly depend on access format | `OAuth2RefreshTokenGenerator` | Refresh token, if permitted |
| OIDC `ID_TOKEN` | Does not depend on access format | `JwtGenerator` | JWT ID token when the OIDC flow is valid |
| Extended token type | Per policy and extension | Custom generator | Custom token, requires full contract |

**A JWT access token does not mean the refresh token is also a JWT.** An OIDC ID token is a JWT by protocol and does not switch to opaque when the access token selects `REFERENCE`.

### 5.3. Multi-Generator Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Grant Provider
    participant D as DelegatingOAuth2TokenGenerator
    participant J as JwtGenerator
    participant A as OAuth2AccessTokenGenerator
    participant R as OAuth2RefreshTokenGenerator

    P->>D: generate(context tokenType=ACCESS_TOKEN)
    D->>J: generate(context)
    alt SELF_CONTAINED
        J-->>D: JWT access token
    else REFERENCE
        J-->>D: null
        D->>A: generate(context)
        A-->>D: Opaque access token
    end
    D-->>P: Access token
    opt Grant/client permits refresh
        P->>D: generate(context tokenType=REFRESH_TOKEN)
        D->>J: generate(context)
        J-->>D: null
        D->>A: generate(context)
        A-->>D: null
        D->>R: generate(context)
        R-->>D: Refresh token
        D-->>P: Refresh token
    end
~~~

For OIDC, the provider can continue calling `generate(context tokenType=ID_TOKEN)` so `JwtGenerator` creates the ID token. Delegating only selects the generator; it **does not store tokens or return HTTP responses directly**.

## 6. How Are Default Generators Configured by Spring Authorization Server?

According to the Spring Authorization Server 1.x documentation:

- If the application does not declare an `OAuth2TokenGenerator`, the default configuration can create a `DelegatingOAuth2TokenGenerator` with `OAuth2AccessTokenGenerator` and `OAuth2RefreshTokenGenerator`.
- If a suitable `JwtEncoder` bean or `JWKSource<SecurityContext>` bean exists, `JwtGenerator` is included in the delegating generator set.
- `TokenSettings.accessTokenFormat` defaults to `SELF_CONTAINED`.
- When a client requires a JWT but there is no signing infrastructure, do not expect the AS to automatically switch to opaque to succeed. Configure JWK/JwtEncoder properly.

### 6.1. Why Is `JwtEncoder` Needed?

`JwtGenerator` uses `JwtEncoder` to sign JWTs. A common configuration uses `NimbusJwtEncoder` with `JWKSource<SecurityContext>`.

Regular JWTs are **signed, not encrypted**. The payload can be read by anyone holding the token; keep claims minimal and avoid passwords, client secrets, session cookies, refresh tokens, and unnecessary PII.

Production requires a clear key lifecycle: protected keys, accurate public JWKS, valid `kid` and rotation, stable issuer, and controlled backup/failover. Do not generate a new private signing key on every restart if the Resource Server needs to continue verifying previously issued tokens.

### 6.2. JWT Signing and Resource Server Validation Are Two Sides

The AS uses the private key to sign tokens; the RS uses the public key to verify the JWT, along with validators for `iss`, `aud`, `exp`, `nbf` if present, scopes, and business policies.

If an RS accepts a JWT merely because the signature was signed by the same AS without checking audience, a token issued for API A could be used at API B. Therefore `aud` is a necessary constraint in the design.

## 7. `TokenSettings` Determines the Access Token Format

Example of two clients with different requirements:

- `booking-bff`: short-lived JWT access token for local verification by the RS.
- `admin-integration`: reference token and introspection because centralized state checking is required.

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;

TokenSettings jwtSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .reuseRefreshTokens(false)
    .build();

TokenSettings opaqueSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
    .accessTokenTimeToLive(Duration.ofMinutes(3))
    .build();
~~~

When creating the client:

~~~java
RegisteredClient bookingBff = RegisteredClient.withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://app.example.test/login/oauth2/code/booking-bff")
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .tokenSettings(jwtSettings)
    .build();
~~~

This is a **`RegisteredClient` configuration snippet**, not a standalone runnable AS application. `passwordEncoder` and `secretFromSecureConfig` must be provided by a bean/secret manager; the client must be stored via `RegisteredClientRepository`. Production requires signing keys, an authorization/consent store, issuer, token endpoint, and user login.

Another client can call `.tokenSettings(opaqueSettings)` to choose `REFERENCE`. **Do not allow an HTTP client to arbitrarily send a "token_format=JWT" parameter to override the registration policy**.

### 7.1. Implications for the Resource Server

| Access token | How the RS handles it | Notes |
| --- | --- | --- |
| Self-contained JWT | `oauth2ResourceServer().jwt()` | Verify signature, issuer, audience, expiry, scope |
| Opaque/reference | `oauth2ResourceServer().opaqueToken()` | Call trusted introspection, check active/metadata/scope |

JWTs generally depend less on the AS per API request once the RS has the keys, but AS revocation is not immediately known to the RS if the RS only verifies locally. Reference tokens let the AS return token status at introspection time, at the cost of network overhead, availability, and cache policy.

## 8. Defining `DelegatingOAuth2TokenGenerator` Manually

If full coordination control is needed, you can declare the generator bean. The following example **keeps all three default generators** and attaches customizers for JWT and reference access tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Configuration
public class TokenGenerationConfig {

    @Bean
    OAuth2TokenGenerator<?> tokenGenerator(
            JwtEncoder jwtEncoder,
            OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
            OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer) {

        JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
        jwtGenerator.setJwtCustomizer(jwtCustomizer);

        OAuth2AccessTokenGenerator accessTokenGenerator =
            new OAuth2AccessTokenGenerator();
        accessTokenGenerator.setAccessTokenCustomizer(opaqueCustomizer);

        OAuth2RefreshTokenGenerator refreshTokenGenerator =
            new OAuth2RefreshTokenGenerator();

        return new DelegatingOAuth2TokenGenerator(
            jwtGenerator, accessTokenGenerator, refreshTokenGenerator);
    }
}
~~~

**Assumption:** There is one `JwtEncoder` bean, one `JwtEncodingContext` customizer bean, and one `OAuth2TokenClaimsContext` customizer bean as shown in sections 9/10. Using explicit generic types helps Spring pick the right bean. The example will fail injection if these beans are not declared yet, which is expected for a learning snippet.

### 8.1. Registering the Generator via the Configurer

You can configure it explicitly:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(
        HttpSecurity http,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, as -> as.tokenGenerator(tokenGenerator))
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());

    return http.build();
}
~~~

In the Spring Authorization Server 1.x branch, the framework can also pick up an `OAuth2TokenGenerator` bean from the application context. If you **declare the generator bean yourself**, wire the customizers **explicitly** as in section 8 rather than relying on the default auto-initialization path.

This example filter chain does not yet include form login, login entry point, JWK/issuer/metadata, and OIDC endpoints; the appropriate beans/policies must be added when deploying a complete AS.

### 8.2. `JwtEncoder` Based on `JWKSource`

If the project has a trusted `JWKSource`:

~~~java
@Bean
JwtEncoder jwtEncoder(JWKSource<SecurityContext> jwkSource) {
    return new NimbusJwtEncoder(jwkSource);
}
~~~

Imports:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
~~~

Do not hardcode production private keys in source code and do not generate temporary keys on every boot. Use a secure key store/KMS/HSM appropriate to your infrastructure.

## 9. `JwtEncodingContext`: Customizing JWT Access Tokens

`JwtGenerator.setJwtCustomizer(...)` accepts an `OAuth2TokenCustomizer<JwtEncodingContext>`. The context provides builders for `JwsHeader` and `JwtClaimsSet`.

### 9.1. Example Attaching Audience for a Known Client

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        String clientId = context.getRegisteredClient().getClientId();

        // AS-controlled mapping; do not take arbitrary audience from HTTP.
        if ("booking-bff".equals(clientId)) {
            context.getClaims()
                .audience(List.of("booking-api"))
                .claim("api_tier", "standard");
        }
    };
}
~~~

This snippet **only illustrates one previously known client**. Production requires complete, governed client/grant/resource -> audience mapping; other clients must also have the proper audience assigned so the RS can validate it.

### 9.2. Do Not Attach Scopes or Permissions Exceeding Authorization

Suppose a client is registered with `booking.read` and `booking.write`, but the user only approves `booking.read`. Do not attach `permissions=["booking.write"]` to the JWT just because that scope is in the registration.

Use `context.getAuthorizedScopes()` and a trusted authorization service to choose claims. For a `tenant_id` claim, verify that the user/client actually belongs to that tenant. Do not trust a `tenant_id` value sent directly in the token endpoint query.

### 9.3. Do Not Apply User-Specific Claims to Client Credentials

~~~text
Client Credentials:
  principal = OAuth2 Client
  no interactive Resource Owner in the request

Authorization Code:
  principal = Resource Owner per flow
  has login/consent and authorization state
~~~

Do not write a customizer that unconditionally casts `context.getPrincipal().getPrincipal()` to `UserDetails`. When a token represents a service, `sub` may represent the client; authorization policy at the RS must account for that.

### 9.4. Do Not Arbitrarily Modify the JWS Header

Although `context.getJwsHeader()` allows modifying headers, avoid:

- Switching `alg` to `none` or a weak algorithm.
- Injecting `jku`/`x5u` from an unverified client-supplied URL.
- Attaching a `kid` that does not correspond to the actual signing key.
- Confusing the `typ` of an access token with that of an ID token.

Key/algorithm decisions must follow AS policy, `JwtEncoder`, and the key rotation mechanism, not depend on untrusted requests.

## 10. `OAuth2TokenClaimsContext`: Customizing Opaque Access Tokens

`OAuth2AccessTokenGenerator` creates opaque/reference access tokens when `TokenSettings.accessTokenFormat` is `REFERENCE`. Metadata/claims can be customized using `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        if ("admin-integration".equals(
                context.getRegisteredClient().getClientId())) {
            context.getClaims()
                .claim("aud", List.of("admin-api"))
                .claim("token_class", "internal");
        }
    };
}
~~~

**Differences compared to JWT:**

- An opaque string carries no payload that the Client can decode on its own to infer claims.
- The AS stores the token/metadata and decides status via `OAuth2AuthorizationService`.
- The Resource Server typically calls Token Introspection (RFC 7662) to receive `active` and permitted metadata.
- Do not assume every custom claim automatically appears in the introspection response across all versions/implementations; test the actual API.
- Do not store passwords, private keys, or unnecessary private data in metadata just because the token is opaque.

### 10.1. The Two Customizer Beans Are Not Interchangeable

| Token to customize | Context | Where attached |
| --- | --- | --- |
| JWT access token | `JwtEncodingContext` | `JwtGenerator.setJwtCustomizer(...)` |
| OIDC ID token (JWT) | `JwtEncodingContext` with token type `id_token` | `JwtGenerator.setJwtCustomizer(...)` |
| Reference access token | `OAuth2TokenClaimsContext` | `OAuth2AccessTokenGenerator.setAccessTokenCustomizer(...)` |

If only a `JwtEncodingContext` customizer exists, a client using `REFERENCE` will **not** receive claims from that customizer.

According to the SAS 1.x documentation, if the application **does not** configure a token generator itself, the framework can automatically pick up a single customizer bean of the appropriate type and attach it to the default generator. When creating the delegating bean yourself, wire them explicitly. Do not declare multiple beans of the same generic customizer type unless you intentionally configure a composite/qualifier.

## 11. OIDC ID Token vs. JWT Access Token

A JWT access token is for the Resource Server. An ID token is for the OpenID Connect Client/Relying Party to verify the login result. Both may be backed by `JwtGenerator`, but **they do not share the same audience or semantics**.

### 11.1. Branching Inside the JWT Customizer

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            customizeAccessToken(context);
        } else if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            customizeIdToken(context);
        }
    };
}
~~~

`customizeAccessToken(...)` and `customizeIdToken(...)` are policy methods defined by your application and are not provided in the snippet above. Import `OidcParameterNames` from `org.springframework.security.oauth2.core.oidc.OidcParameterNames`.

### 11.2. Claims That Require Care

| Claim | Why is it sensitive? |
| --- | --- |
| `iss` | The RS/Client must verify the issuer |
| `sub` | Subject identifier per protocol |
| `aud` | Access tokens target APIs; ID tokens target the OIDC Client |
| `iat`, `exp`, `nbf` | Lifetime and validity window |
| `nonce` | Binds the OIDC request and ID token when applicable |
| `auth_time` | Authentication timestamp, meaningful for OIDC policies |
| `scope` | Access token permissions, not every user role |

Do not remove or overwrite standard claims just to satisfy a temporary UI/API need. A validly signed ID token can still violate the protocol if audience/nonce is altered. A Resource Server must never accept an ID token in place of an access token.

## 12. Refresh Tokens and Generator Boundaries

`OAuth2RefreshTokenGenerator` creates refresh tokens when the grant/provider/policy allows it. It does not decide on its own:

- Whether to issue a refresh token for Client Credentials (RFC 6749 recommends against it).
- Whether the calling client is allowed to use the `REFRESH_TOKEN` grant.
- Whether the old refresh token is active, belongs to the right client, and is not expired.
- During rotation, how to perform revocation/family detection or handle concurrent requests.

Those conditions belong to the grant provider and authorization/token lifecycle. `TokenSettings.refreshTokenTimeToLive(...)` and `reuseRefreshTokens(...)` describe token policy, but **rotation does not automatically constitute full replay detection or family revocation**.

### 12.1. Why Not Drop `OAuth2RefreshTokenGenerator` When You Only Want JWTs?

Suppose the AS issues JWT access tokens to a BFF using Authorization Code + PKCE and permits the Refresh Token Grant. If a custom bean only includes `JwtGenerator`, it may fail to generate the refresh token required by the flow.

The solution is to keep `DelegatingOAuth2TokenGenerator(jwtGenerator, accessTokenGenerator, refreshTokenGenerator)` and test Authorization Code, refresh grant, and token expiration/rotation.

## 13. Claims and `OAuth2AuthorizationService`

An `OAuth2Authorization` can store the authorization code, access token, refresh token, ID token, and flow-specific metadata. If a generated token has claims and supports `ClaimAccessor`, the claims can be read via `OAuth2Authorization.Token.getClaims()` per the core model.

~~~mermaid
flowchart LR
    P["Grant Provider"]
    G["OAuth2TokenGenerator"]
    T["OAuth2Token<br/>ClaimAccessor if applicable"]
    B["OAuth2Authorization.Builder"]
    DB[("OAuth2AuthorizationService")]
    RS["Resource Server"]

    P --> G --> T --> B --> DB
    T -.->|"JWT sent via Client"| RS
    DB -.->|"Introspection metadata for opaque"| RS
~~~

Do not conflate:

- A JWT payload can be read by whoever holds the token.
- An opaque token is just a string; checking its status normally requires introspection.
- The authorization store holds metadata that is not necessarily exposed in full to the Resource Server.
- The ability to issue a token does not mean the user/client has permission to read every resource.

### 13.1. What Data Belongs in an Access Token?

| Claim | Example | Required control |
| --- | --- | --- |
| `iss` | `https://auth.example.test` | Valid issuer |
| `sub` | User ID or Client ID | Depends on grant, do not assume user |
| `aud` | `["booking-api"]` | RS validates audience |
| `client_id` | `booking-bff` | Public ID, does not replace client authentication |
| `scope` | `booking.read` | Must not exceed authorized scopes |
| `iat`, `exp`, `nbf` | Timestamps | TTL and clock skew |
| `jti` | Token ID | Can be used for audit/revocation, but do not log raw tokens |
| `tenant_id` | Tenant ID | Attach only after verifying membership |
| `permissions` | Permission list | Can become stale; does not replace object-level authorization |

Do not put password hashes, raw passwords, client secrets, refresh tokens, or unnecessary personal data into claims.

## 14. When Should You Write a Custom Generator?

There are cases requiring tokens in a specialized format, but in most cases **you only need a token customizer** rather than writing a new generator.

Consider a custom generator only when:

- There is a proprietary token format that token consumers and the RS genuinely support.
- A specialized signing or encoding mechanism permitted by security policy is required.
- Lifecycle and persistence requirements have been designed.
- There are clear tests for issuer, audience, TTL, claims, token type, scope, revocation, and error responses.

A new custom generator must:

1. Check `context.getTokenType()` and the appropriate format.
2. Check RegisteredClient/token policy from the context that already passed grant validation.
3. **Return `null`** if it is not responsible for the current token.
4. Refuse to issue a token when context is insufficient or secure signing/encryption is unavailable.
5. Coordinate with the provider to persist token/metadata and respond according to the protocol.
6. Never "swallow errors" and issue an access token with broader privileges.
7. Have unit and integration tests proving it does not break the default grants.

### 14.1. Anti-Pattern Example

~~~java
// AVOID: creating only JwtGenerator and replacing the entire default bean.
@Bean
OAuth2TokenGenerator<?> tokenGenerator(JwtEncoder encoder) {
    return new JwtGenerator(encoder);
}
~~~

This bean can prevent reference clients and refresh flows from generating the tokens they need. Use a delegating generator with the full set of components.

### 14.2. Anti-Pattern: Generator Always Returns a Token

If a custom generator always returns a token string regardless of `tokenType`, it can block `JwtGenerator`, `OAuth2AccessTokenGenerator`, and `OAuth2RefreshTokenGenerator` behind it. This corrupts formats, lifetimes, and permissions.

### 14.3. Anti-Pattern: Falling Back After a JWT Signing Error

A system should not catch every `JwtEncoder` exception and switch to an opaque token "so the API stops failing" when the client is registered to receive JWTs. A signing failure is an issuance/token infrastructure error that must report an appropriate error and be fixed at its root cause, not silently alter the security contract.

## 15. Booking API Architecture Example

Suppose `batch-reporter` is a confidential client using Client Credentials and receiving a JWT for `booking-api`.

### 15.1. Client Sends Request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

The `RegisteredClient` for `batch-reporter` **must have `AuthorizationGrantType.CLIENT_CREDENTIALS`** and `booking.read` registered. Do not reuse the `booking-bff` registration from section 7 (which only has Authorization Code/Refresh Token) and expect this machine-to-machine request to succeed.

### 15.2. Response and Illustrative JWT

~~~json
{
  "access_token": "eyJ...signed.jwt...placeholder",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

A JWT payload might carry:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["booking-api"],
  "sub": "batch-reporter",
  "client_id": "batch-reporter",
  "scope": "booking.read",
  "iat": 1893455700,
  "exp": 1893456000
}
~~~

These are **illustrative values**, not a real JWT. `sub` represents the client/service in Client Credentials. Scopes may be represented differently depending on profile; the RS must use consistent mapping and validation.

### 15.3. Resource Server Verification

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Example API policy:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

The Resource Server dependency, `JwtDecoder`, and audience checking are required. **`issuer-uri` does not replace configuring an audience validator for the API**. The system must still enforce object-level authorization and tenant checks. Multiple applications may share an issuer, but each RS must only accept tokens intended for itself.

## 16. Testing Token Generators and Claims

### 16.1. Test Matrix

| Test case | Expectation |
| --- | --- |
| `SELF_CONTAINED` access token | Signed JWT with accurate issuer/audience/TTL/scope |
| `REFERENCE` access token | Opaque token, valid authorization metadata and introspection |
| Grant requiring refresh token | Generator includes RT, issued per policy |
| Client Credentials | Do not assume a refresh token is issued |
| OIDC ID token | Correct OIDC Client audience, no accidental API claims |
| JWT customizer | Runs for the right access token type |
| Opaque customizer | Runs for reference access tokens |
| JWT with invalid signature | Rejected by RS |
| JWT with wrong audience | Rejected by RS |
| Expired JWT | Rejected by RS |
| Opaque `active: false` | Rejected by RS |
| Key rotation | Tokens signed by old/new keys valid during transition window |
| Signing key outage | AS reports error, does not fall back against policy |
| Custom generator returns null | Delegating tries the next generator |
| Custom generator returns token | Subsequent generators are not called |
| Customizer wrong principal type | Handled safely, no ClassCastException |
| Refresh rotation | Old/new RT states are accurate |
| Multi-instance | Consistent authorization/key store |

### 16.2. Unit Testing the Delegating Mechanism

The following core code verifies that a generator returning `null` yields to the next generator:

~~~java
OAuth2TokenGenerator<OAuth2Token> noMatch = context -> null;

OAuth2AccessToken expected = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "test-token-only",
    Instant.now(),
    Instant.now().plusSeconds(60),
    Set.of("booking.read")
);

OAuth2TokenGenerator<OAuth2Token> match = context -> expected;

DelegatingOAuth2TokenGenerator delegating =
    new DelegatingOAuth2TokenGenerator(noMatch, match);

// With a valid OAuth2TokenContext fixture:
// assertThat(delegating.generate(context)).isSameAs(expected);
~~~

This is a **conceptual** unit test without the `context` builder/fixture. It does not verify JWT signatures or grant authorization. Also test that when the first generator returns a token, the second generator is not called, and when the first generator throws an exception, it is not treated as `null`.

### 16.3. MockMvc: Client Credentials End-to-End

~~~java
@Test
void clientCredentialsIssuesAccessToken() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "booking.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

The test fixture must provide the `RegisteredClient` for `batch-reporter`, Client Credentials, scope, hashed secret, token generator/keys/issuer, and authorization store. This snippet **only proves a token response was received**. To verify a real JWT, extract the token, decode/verify it with a real `JwtDecoder`, and assert `iss`, `aud`, `exp`, `scope`, and the signature.

### 16.4. Testing Metadata and Introspection

For clients using `REFERENCE`, test that:

1. The access token has an opaque format per contract (do not check only for dots).
2. `OAuth2AuthorizationService` stores the token and appropriate metadata.
3. Introspection with valid client credentials returns `active: true` and permitted metadata.
4. Invalid/expired/revoked tokens return `active: false`.
5. The RS rejects tokens on introspection timeout/outage rather than letting them through.
6. Scope, audience, and business permissions are enforced at the RS.
7. You do not rely on a JWT customizer to supply opaque metadata.

### 16.5. OIDC-Specific Testing

For OIDC, test that the ID token is signed and contains `iss`/`aud`/`sub`/`exp` and other profile-compliant claims; `nonce` is verified by the Client when applicable. APIs **must not accept an ID token** as an access token.

`@WithMockUser` and `jwt()` from `spring-security-test` are useful for testing authorization rules, but **do not prove that the token generator created and signed the token properly**.

## 17. Operations, Security, and Observability

### 17.1. Signing Key Management

- Private keys must be protected according to policy (secret manager/KMS/HSM or an appropriate key store).
- Public JWKS must accurately reflect valid keys, `kid`, and algorithms.
- During rotation, keep the old public key long enough to verify already-issued tokens, unless an emergency revocation is required.
- Multiple AS instances must share a consistent key set.
- Do not generate new signing keys on every restart if old tokens still need to be used.
- Treat signer failures as operational incidents; do not blindly fall back to another format.

### 17.2. Data and Privacy

- Minimize claims containing PII.
- Do not insert passwords, session IDs, client secrets, or refresh tokens into access tokens.
- Do not read user/tenant claims from unverified parameters.
- Roles/permissions can become stale in JWTs; apply TTL, revocation, or supplementary RS policies.
- Do not log raw access tokens, ID tokens, refresh tokens, or private keys.
- Do not put tokens into analytics URLs, stack traces, or metrics labels.

### 17.3. Useful Monitoring

| Metric | Meaning |
| --- | --- |
| Token issuance by grant/token type | System load and behavioral shifts |
| JWT signing failures/latency | Signer/key issues |
| JWT vs. opaque distribution | Client/token format migration |
| Token generator exception count | Configuration or runtime errors |
| Introspection failures/latency | Reference token operability |
| RS rejects by issuer/audience/expiry | AS-RS mismatch |
| Key rotation/JWKS cache misses | Key distribution check needed |
| Refresh failures/rotation races | Policy/token store concurrency |

Logs should include correlation ID, authenticated client ID, token type, error code, and processing duration; **never raw bearer credentials**.

## 18. Troubleshooting

| Symptom | Common cause | What to check |
| --- | --- | --- |
| JWT not issued | Missing JwtEncoder/JWKSource, signer failure | Key configuration, issuer, bean wiring |
| JWT missing custom claims | Customizer not attached, wrong token type | `setJwtCustomizer`, JWT vs. opaque |
| Opaque missing metadata | Only JwtEncodingContext customizer exists | `OAuth2TokenClaimsContext` |
| Client expects opaque but gets JWT | Wrong TokenSettings or overly broad custom generator | RegisteredClient format |
| Client expects JWT but gets opaque | Custom fallback violates policy | Delegating order and signer |
| Refresh token not issued | Missing RefreshTokenGenerator or disallowed by grant/client | Delegating list, grant policy |
| OIDC ID token missing | OIDC not enabled, missing encoder or token provider | OIDC config, JWK, claim policy |
| ClassCastException during Client Credentials | Casting principal to UserDetails | Check grant/principal type |
| RS returns 401 despite valid JWT signature | Mismatched issuer/audience/TTL/algorithm | JwtDecoder and validators |
| RS returns 403 | Insufficient scope or object-level permission | Token claims + API authorization |
| Old JWT still works after revocation | RS only verifies locally | TTL/denylist/online check |
| Claim role change not reflected | Issued JWT holds stale data | TTL/revoke/session policy |
| Tokens break after AS restart | Different key store or lost authorization store | Persistence, multi-instance |
| Introspection lacks custom claims | Metadata not saved or response mapping missing | Authorization store/contract |

## 19. Self-Check Questions

**Question 1.** Under what condition does `DelegatingOAuth2TokenGenerator` stop?

**Answer:** When the first generator in order returns a non-null token. Subsequent generators are not called.

**Question 2.** Why should you not equate `null` and an exception from `generate(...)`?

**Answer:** `null` means the generator is not responsible for that token type. An exception indicates a genuine issuance error; you must not silently try another format to bypass a security failure.

**Question 3.** Does `JwtGenerator` create an access token for a Client with `REFERENCE` format?

**Answer:** In the default generator set, the JWT generator does not handle reference access tokens; `OAuth2AccessTokenGenerator` creates the opaque token.

**Question 4.** Why does a customizer using `JwtEncodingContext` not affect reference tokens?

**Answer:** Reference/opaque tokens are created by `OAuth2AccessTokenGenerator` and use `OAuth2TokenClaimsContext` when claim metadata is needed.

**Question 5.** Is `context.getPrincipal()` always the Resource Owner?

**Answer:** No. In Client Credentials, the principal is usually the OAuth2 Client. Avoid casting to a user type across all grants.

**Question 6.** Should you use `RegisteredClient.getScopes()` to build permission claims when a user only consented partially?

**Answer:** No. Use authorized scopes and verified policies for the corresponding authorization.

**Question 7.** Why should you not register only a `JwtGenerator` bean to replace the entire delegating bean?

**Answer:** Because it can remove the ability to generate reference access tokens and refresh tokens required by other clients/grants.

**Question 8.** Can an ID token and a JWT access token be used interchangeably?

**Answer:** No. An ID token is for the OIDC Client, while an access token is for the Resource Server. Their audiences and purposes differ.

**Question 9.** Is a validly signed JWT enough to allow reading all bookings?

**Answer:** No. The RS must still verify issuer, audience, expiry, scope, and permissions on each object/tenant.

## 20. Checklist

- [ ] Client/grant is authenticated before the generator creates a token.
- [ ] `OAuth2TokenContext` uses server-verified data sources.
- [ ] Delegating generator includes Jwt, opaque access token, and refresh generators as needed.
- [ ] Custom generators return `null` for out-of-scope token types.
- [ ] Signing exceptions are never swallowed to switch formats against policy.
- [ ] `TokenSettings.accessTokenFormat` and TTL are explicitly declared per RegisteredClient.
- [ ] JwtEncoder/JWKSource/issuer/rotation are managed securely.
- [ ] JWT has the proper audience and the RS validates issuer/audience/signature.
- [ ] Opaque tokens have introspection and a durable authorization store.
- [ ] JwtEncodingContext customizer only injects access token claims into access tokens.
- [ ] OAuth2TokenClaimsContext customizer is attached properly to OAuth2AccessTokenGenerator.
- [ ] Scopes or roles/tenants are never escalated from unverified requests.
- [ ] Refresh tokens are issued per grant/client and policy, not mixed up with access tokens.
- [ ] OIDC ID tokens satisfy the proper audience and claim profile.
- [ ] Tests cover Jwt, opaque, refresh, ID token, TTL, signature, audience, scope, and restart.
- [ ] Raw tokens, signing keys, and client secrets are never logged.

## 21. Official Documentation and Conclusion

Read against the **exact version** of Spring you are deploying:

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Customize JWT access token claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html)

**Conclusion:** `OAuth2TokenGenerator` generates tokens from `OAuth2TokenContext`. `DelegatingOAuth2TokenGenerator` coordinates generators and picks the **first non-null result**. `JwtGenerator` serves JWT access tokens and ID tokens based on context; `OAuth2AccessTokenGenerator` serves opaque/reference access tokens; `OAuth2RefreshTokenGenerator` serves refresh tokens when policy permits. When configuring and customizing claims, preserve the proper token type, client, scopes, audience, key lifecycle, and Resource Server role; end-to-end testing is what proves the OAuth 2.0/OIDC system issues tokens securely.
