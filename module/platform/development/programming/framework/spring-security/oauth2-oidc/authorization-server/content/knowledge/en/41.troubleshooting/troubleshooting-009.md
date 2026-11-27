# OIDC UserInfo Errors, Missing JwtDecoder, and Inconsistent Subject

OIDC UserInfo is the endpoint that returns claims about the logged-in user, such as name and email. In Spring Authorization Server, this endpoint works properly only when OIDC is enabled, the access token is authenticated, appropriate scopes are granted, and the `sub` claim is consistent with the ID Token.

Three common, closely related errors are:

- Client calls UserInfo and receives `401`, `403`, or `404`.
- Application fails at startup because no `JwtDecoder` bean is found.
- UserInfo returns a `sub` claim different from the `sub` claim in the ID Token, causing the OIDC client to reject the response.

This lesson explains how to trace a request from discovery to UserInfo, configure Spring Security to validate access tokens, verify scopes, and design a shared subject identifier for both ID Token and UserInfo.

## 1. Understanding the OIDC UserInfo Flow

UserInfo is an OAuth 2.0 protected resource defined by OIDC. The client uses the **access token** received from the token endpoint to call UserInfo. The ID Token is authentication evidence for the client; it is not a bearer token for calling UserInfo.

Basic flow:

~~~mermaid
sequenceDiagram
    participant C as OIDC Client
    participant AS as Authorization Server
    participant U as UserInfo Endpoint

    C->>AS: Authorization Request (scope=openid profile email)
    AS->>AS: Authenticate user and obtain consent
    AS-->>C: Authorization Code
    C->>AS: Token Request (authorization_code + PKCE)
    AS-->>C: ID Token + Access Token
    Note over C: Store ID Token and read sub claim
    C->>U: GET UserInfo with Bearer Access Token
    U->>U: Verify signature, exp, issuer, and scope
    U-->>C: JSON claims including sub
    Note over C: Compare UserInfo.sub with ID Token.sub
~~~

Key rules:

1. The Authorization Request must include the `openid` scope to qualify as an OIDC request.
2. The client sends the access token in the `Authorization: Bearer` header when calling UserInfo.
3. The access token must still be valid and issued for an appropriate purpose.
4. UserInfo returns only claims that the client is permitted to receive based on scope, consent, and application policy.
5. The `sub` claim in UserInfo must match the `sub` claim in the ID Token for the same End-User and authentication session exactly.

Example of a valid request:

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

Do not send the ID Token in this header. If the client sends an ID Token instead of an access token, the server may reject it due to wrong token type, wrong audience, or non-acceptance at the resource endpoint.

## 2. Identifying Errors by Symptom

| Symptom | Common Cause | Where to Check |
|---|---|---|
| `userinfo_endpoint` missing from discovery | OIDC is not enabled or metadata is not published properly | OIDC config and `/.well-known/openid-configuration` |
| Calling UserInfo returns `404` | Wrong path, endpoint rewritten by proxy, or OIDC UserInfo not enabled | `userinfo_endpoint` in discovery and `AuthorizationServerSettings` |
| Calling UserInfo returns `401` | Missing bearer token, expired token, invalid signature, wrong issuer, or unaccepted token | Authorization header, access token, and JwtDecoder |
| Receiving `403` or scope error | Access token lacks required scope or claim policy denies it | Token scopes and consent |
| App fails to start due to missing `JwtDecoder` | Resource Server JWT is enabled without a decoder to verify bearer tokens | SecurityFilterChain and JwtDecoder bean |
| `JwtDecoder` reports key fetch or signature verification failure | Wrong JWKSource/JWKS, out-of-sync signing keys, or missing `kid` | JWKSource, JWKS, and key rotation process |
| Client reports UserInfo `sub` mismatches ID Token | ID Token and access token/UserInfo generate subject differently | Token customizer, principal mapping, and UserInfo mapper |
| UserInfo lacks `name` or `email` | Missing scope, missing consent, or mapper omits claims from response | `profile`, `email` scopes, and UserInfo mapper |

Do not begin by changing multiple configurations at once. Identify whether the failure happens during discovery, access token validation, scope authorization, or subject comparison.

## 3. Checking OIDC Discovery Before Editing Code

The discovery document tells you which endpoints the Authorization Server publishes and which issuer the client must use.

~~~bash
curl -i https://auth.example.com/.well-known/openid-configuration
~~~

Check these fields:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "jwks_uri": "https://auth.example.com/oauth2/jwks"
}
~~~

This is an abbreviated illustrative JSON. Actual values must be taken from the server's response.

- `issuer` must be the Authorization Server's stable public identifier.
- `userinfo_endpoint` must point to the exact deployed endpoint.
- `jwks_uri` must publish public keys used to verify JWTs.
- The client must use the configured issuer to verify the ID Token.

If `userinfo_endpoint` does not appear, check whether OIDC is enabled in the Authorization Server configurer. If the endpoint is published yet calling it returns `404`, inspect reverse proxy, ingress, context path, and endpoint settings. Do not hardcode paths from examples; use the discovery document as the client's source of truth.

With Spring Authorization Server, OIDC must be enabled explicitly:

~~~java
http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
        .oidc(Customizer.withDefaults());
~~~

If the application uses the newer configurer API, place the `oidc(...)` configuration directly on the `OAuth2AuthorizationServerConfigurer` attached to the Authorization Server SecurityFilterChain. Do not enable OIDC on a separate chain that does not handle Authorization Server endpoints.

## 4. Fixing Missing JwtDecoder Errors

### 4.1. Why Does UserInfo Need a JwtDecoder?

UserInfo receives the access token via bearer authentication. When configured with self-contained JWT access tokens, Spring Security must verify the signature and security claims before letting the request enter UserInfo handling.

When configuring:

~~~java
http.oauth2ResourceServer(resourceServer ->
        resourceServer.jwt(Customizer.withDefaults()));
~~~

Spring Security enables bearer JWT authentication. This mechanism requires a `JwtDecoder` to decode and verify tokens. If no suitable decoder is found, the application may fail while initializing SecurityFilterChain or starting the context.

### 4.2. Using the Authorization Server's Own JWKSource

In Spring Authorization Server, the standard approach when access tokens are signed by keys managed by the Authorization Server is creating the decoder from the same `JWKSource` used to sign tokens and serve JWKS.

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

This bean assumes the application already has a valid `JWKSource<SecurityContext>`. Use the same key source as the Authorization Server so that:

- JWT access tokens are signed with the corresponding private key.
- The decoder can obtain the matching public key to verify signatures.
- The JWKS endpoint publishes public keys whose `kid` matches the tokens.
- Replicas share the same key configuration and token verification capability.

Never generate a separate random key pair just for the decoder. If the decoder uses a different key set than the token generator, UserInfo requests will be rejected even though access tokens are issued successfully.

### 4.3. Enabling Resource Server JWT in the Right SecurityFilterChain

The example below illustrates configuration with the `applyDefaultSecurity` API common in earlier Spring Authorization Server versions. If your project uses the newer configurer API, keep the same principle: OIDC UserInfo and Resource Server JWT must reside in the chain handling Authorization Server endpoints.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);

    http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
            .oidc(Customizer.withDefaults());

    http.oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

If the existing chain already configures OIDC, simply add Resource Server JWT configuration to that same chain and verify the decoder bean. Do not create a second chain with overlapping matchers for the same endpoints; chain ordering can route UserInfo requests into the wrong configuration.

With the newer configurer API, the structure typically looks like:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()))
        .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));
~~~

This snippet illustrates only wiring the configurer and Resource Server; preserve authorization rules, exception handling, and any other settings required by your application.

### 4.4. Distinguishing a Local Decoder from an HTTP JWKS Decoder

There are two common ways for a Resource Server to verify JWTs:

- Use the Authorization Server's local `JWKSource` to build `JwtDecoder`. This fits when UserInfo lives inside the Authorization Server itself and shares the same key store.
- Use `issuer-uri` or `jwk-set-uri` to configure a standalone Resource Server verifying tokens via metadata/JWKS endpoints.

Example configuration for a standalone Resource Server:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.com
~~~

Or configuring the JWKS address directly:

~~~properties
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://auth.example.com/oauth2/jwks
~~~

Do not configure a decoder to loop back out through the Authorization Server's own public ingress unnecessarily. That introduces DNS, TLS, proxy, and network dependencies into request validation. Within the same application, using the local JWKSource is usually simpler with fewer failure points.

If the application uses opaque/reference access tokens, `JwtDecoder` cannot decode those tokens. Use an introspection mechanism fitting the Resource Server architecture and verify how your Spring Authorization Server version supports that token format for UserInfo. Do not try to turn opaque tokens into JWTs by parsing the token string directly.

## 5. Verifying the Access Token Before Calling UserInfo

Even with a decoder in place, you must still verify that the access token satisfies endpoint requirements.

### 5.1. Sending the Right Token Type

The client must send the access token obtained from the token endpoint:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  https://auth.example.com/userinfo
~~~

Do not send:

- Authorization code.
- ID Token.
- Refresh token.
- Client secret.
- An arbitrary JWT signed by the same private key that was not issued as an access token.

Never record full access tokens in logs, tickets, or screenshots. When correlation is needed, record only non-sensitive metadata such as `kid`, issuer, expiration, and a request identifier.

### 5.2. Checking Security Claims

When the access token is a JWT, check at minimum:

| Claim or Attribute | What to Verify |
|---|---|
| Signature | Signature is valid against the matching public key |
| `iss` | Matches the trusted issuer |
| `exp` | Token has not expired |
| `nbf` | Token has reached its valid-from time |
| `aud` | Audience matches resource policy |
| `sub` | Identifies the right End-User in the user flow |
| `scope` | Contains required permissions to return claims |
| `kid` | Exists in the JWKS used by the decoder |

Not every access token carries the same set of claims. Inspect actual tokens and the application's issuance policy. A client credentials token does not represent an End-User; do not use it to query personal information via OIDC UserInfo.

### 5.3. Checking Scope and Consent

OIDC scopes commonly tied to UserInfo:

| Scope | Claim Group Typically Permitted |
|---|---|
| `openid` | Enables the OIDC flow |
| `profile` | Name, display name, picture, locale, and other profile claims |
| `email` | Email and email verification status |
| `address` | Address |
| `phone` | Phone number and phone number verification status |

Scopes requested in the authorization request are not guaranteed to be granted in full. Verify which scopes were consented by the user, permitted for the client, and recorded in the authorization/access token.

For example, an authorization request may contain:

~~~text
scope=openid%20profile%20email
~~~

If only `openid` was granted, the client should not expect UserInfo to return email or full profile claims. Do not solve missing-claim errors by returning all user attributes to every client.

## 6. Fixing Inconsistent Subject

### 6.1. Mandatory OIDC Rule

`sub` is the End-User's identifier at the issuer. For the same End-User within the same authentication session, the `sub` value in UserInfo must match the `sub` value in the ID Token identically.

Valid example:

~~~json
{
  "id_token": {
    "iss": "https://auth.example.com",
    "sub": "usr_7d91a2",
    "aud": "mobile-client"
  },
  "userinfo": {
    "sub": "usr_7d91a2",
    "name": "Nguyen Van A",
    "email": "user@example.com"
  }
}
~~~

Invalid example:

~~~json
{
  "id_token": {
    "sub": "usr_7d91a2"
  },
  "userinfo": {
    "sub": "user@example.com"
  }
}
~~~

In the invalid example, the ID Token uses an internal user ID while UserInfo uses an email address. Emails can change and are not a suitable OIDC substitute for subject. The client is entitled to reject the response because the two values disagree.

### 6.2. Common Causes of sub Divergence

- ID Token uses `Authentication.getName()`, while the UserInfo mapper uses email or username.
- A token customizer alters `sub` on the ID Token without altering subject in the JWT access token.
- One place uses a database ID while another uses an external identity ID.
- UserInfo looks up the user by a changed email or a renameable username.
- Replicas run different versions of subject mapping logic.
- The application migrated from public subjects to pairwise subjects, updating only one token flow.
- Client or user profile data was migrated without preserving old subject mappings.

Choose one stable identifier source and one unified subject-generation rule. Never use display name, phone number, or email as subject if those attributes can change.

### 6.3. Reading sub from the Access Token When Building UserInfo

When the JWT access token already carries the right subject, the UserInfo mapper can use that token's subject directly as the `sub` claim. Example:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

authorizationServerConfigurer.oidc(oidc -> oidc
    .userInfoEndpoint(userInfo -> userInfo
        .userInfoMapper(context -> {
            JwtAuthenticationToken jwtPrincipal =
                    (JwtAuthenticationToken) context.getPrincipal();

            String subject = jwtPrincipal.getToken().getSubject();
            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();

            UserProfile profile = userProfileService.findBySubject(subject);

            Map<String, Object> claims = new HashMap<>();
            claims.put(IdTokenClaimNames.SUB, subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.getDisplayName());
            }

            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.put("email", profile.getEmail());
                claims.put("email_verified", profile.isEmailVerified());
            }

            return new OidcUserInfo(claims);
        })
    )
);
~~~

`UserProfile` and `userProfileService` are application components. Look up the profile by the stable identifier corresponding to the subject, then include in the response only claims permitted by scopes and consent.

This mapper assumes the endpoint authenticates JWTs and the principal is `JwtAuthenticationToken`. If your application uses another principal type, adapt the mapper to the actual authentication type; do not cast blindly and swallow authentication errors.

### 6.4. Sharing One Subject Resolver Across ID Token and Access Token

If the application has custom subject rules, centralize that logic into a shared service. Whenever a customizer changes `sub` on the ID Token, ensure the JWT access token used to call UserInfo receives the exact same subject.

Example customizer structure:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> subjectCustomizer(
        SubjectIdentifierService subjectIdentifierService) {

    return context -> {
        String tokenType = context.getTokenType().getValue();

        boolean userToken =
                OAuth2TokenType.ACCESS_TOKEN.getValue().equals(tokenType)
                || OidcParameterNames.ID_TOKEN.equals(tokenType);

        if (userToken
                && !AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                        context.getAuthorizationGrantType())) {
            String subject = subjectIdentifierService.resolve(
                    context.getPrincipal(),
                    context.getRegisteredClient());

            context.getClaims().subject(subject);
        }
    };
}
~~~

`SubjectIdentifierService` is a service implemented by the application. It must resolve the same End-User and client/sector consistently according to a stable rule. If the application does not need custom subjects, do not add a customizer just to change `sub`; the consistent default subject may already satisfy requirements.

With pairwise subjects, subjects may differ across sectors by OIDC design. Still, the ID Token and UserInfo for the same client and same authentication session must carry the exact same value. Never compute a separate pairwise subject independently inside the UserInfo mapper.

### 6.5. Avoiding Returning Claims Beyond Consent

The mapper must not serialize the entire user entity. Enforce a claim allowlist per scope:

- `profile`: only permitted profile attributes.
- `email`: email and `email_verified`.
- `address`: address in OIDC structure.
- `phone`: phone number and `phone_number_verified`.

Do not treat the client's requested scope as sole proof that the user consented. Apply the Authorization Server's consent and client registration policies.

## 7. Checking Endpoint and Security Configuration

### 7.1. Checking the UserInfo Path

The default path is typically `/userinfo`, though applications may customize endpoint settings or place it behind a context path/proxy. Clients should obtain the path from the discovery document rather than hardcoding it.

When encountering `404`, check in order:

1. Is OIDC enabled on the Authorization Server configurer?
2. Does the discovery document include `userinfo_endpoint`?
3. Does the request pass through the right ingress, reverse proxy, and application context path?
4. Did `AuthorizationServerSettings` customize the UserInfo endpoint?
5. Does the SecurityFilterChain matcher cover that endpoint?

### 7.2. Checking SecurityFilterChain

The Authorization Server typically has a dedicated chain with higher priority than the application chain. If another chain captures the UserInfo request first, bearer tokens may not be processed by the expected Resource Server configuration.

Check:

- The chain uses the exact endpoint matcher of the Authorization Server.
- OIDC UserInfo is enabled in that chain.
- `oauth2ResourceServer(...).jwt(...)` is configured in the chain handling UserInfo.
- `JwtDecoder` is visible to Spring in the application context.
- No rule demands form login or sessions for a UserInfo request that must authenticate via bearer token.

Never open the UserInfo endpoint to anonymous access. UserInfo must require a valid access token.

### 7.3. Checking Issuer and Public URL Behind a Reverse Proxy

If the application runs behind an ingress, the issuer must be the public URL. Forwarded headers and proxy config must align so discovery, tokens, and UserInfo all use the same host/scheme.

Mismatches like tokens having `iss=http://authorization-server:8080` while discovery advertises `https://auth.example.com` can cause decoders or clients to reject tokens. Check all of:

- `AuthorizationServerSettings.issuer`.
- The `issuer` field in discovery.
- The `iss` claim in ID Tokens and access tokens.
- Public URLs in `userinfo_endpoint` and `jwks_uri`.

Never use pod hostnames or internal service addresses as the public issuer.

## 8. Ordered Diagnostic Workflow

Follow this sequence to isolate the fault quickly:

1. **Discovery:** fetch `/.well-known/openid-configuration`; confirm `issuer` and `userinfo_endpoint`.
2. **OIDC config:** confirm `oidc(Customizer.withDefaults())` or equivalent OIDC setup is enabled.
3. **Decoder:** confirm a `JwtDecoder` bean exists and Resource Server JWT is configured on the right SecurityFilterChain.
4. **Token:** obtain a fresh access token from the token endpoint; do not reuse old tokens after changing signing keys or issuer config.
5. **JWT:** verify signature, `kid`, `iss`, `exp`, `nbf`, `aud`, and `sub`.
6. **Scope:** confirm the access token contains `openid` and the scope claims the client needs.
7. **Request:** call UserInfo with the access token in the bearer header.
8. **Response:** verify JSON includes `sub`, then compare it with the ID Token's `sub`.
9. **Mapper:** if claims are missing, inspect authorized scopes, consent, and the UserInfo mapper allowlist.
10. **Replicas:** if errors happen intermittently, compare issuer, JWK set, subject mapping, and config versions across replicas.

Obtaining a fresh token after changing signing keys or the decoder eliminates the risk of testing an old token signed by a previous key.

## 9. Regression Testing for UserInfo

An integration test should obtain tokens through a real OAuth/OIDC flow or use a JWT fixture signed by a test key, then verify the UserInfo response.

Example with MockMvc once a valid access token is available:

~~~java
mvc.perform(get(userInfoEndpoint)
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.sub").value(expectedSubject));
~~~

Test cases should include:

| Test Case | Expected Result |
|---|---|
| Valid access token with `openid profile` scope | UserInfo returns `sub` and permitted profile claims |
| Access token with `openid email` | UserInfo returns `sub`, email, and verification status if policy permits |
| Missing bearer token | Request is rejected |
| Expired token or invalid signature | Request is rejected during authentication |
| Token lacks required scope | Corresponding claims are omitted or request rejected per policy |
| ID Token sent instead of access token | Request is not accepted as a valid bearer access token |
| ID Token and UserInfo have different subjects | Test catches the bug; client must not treat response as valid |
| Pairwise subject | ID Token and UserInfo for the same client/sector have identical subject |
| Key rotation | Valid tokens signed by active key still verify; required public keys remain in JWKS |

A critical test is direct comparison:

~~~java
assertThat(userInfo.getSubject()).isEqualTo(idToken.getSubject());
~~~

This is the core condition for the client to trust that UserInfo describes the exact End-User authenticated in the ID Token.

## 10. Quick Resolution Table

| Error | Resolution |
|---|---|
| Missing `userinfo_endpoint` | Enable OIDC on Authorization Server configurer and check discovery |
| `404` at UserInfo | Use URL from discovery; check proxy, context path, and endpoint settings |
| Missing `JwtDecoder` bean | Declare a decoder from JWKSource or configure a decoder matching token source |
| `401 invalid_token` | Send access token; verify signature, issuer, expiration, audience, and JWKS |
| `403 insufficient_scope` | Check granted scopes, consent, and mapper policy |
| Missing `sub` in response | Require including subject in UserInfo response |
| `sub` differs from ID Token | Share one subject resolver across ID Token and access token/UserInfo |
| Email/profile missing | Request corresponding scopes, check consent and mapper |
| Only some replicas fail | Synchronize JWKSource, issuer, subject resolver, and config across replicas |

## 11. Pre-Release Checklist

- [ ] OIDC is enabled on the Authorization Server SecurityFilterChain.
- [ ] Discovery publishes accurate `issuer`, `userinfo_endpoint`, and `jwks_uri`.
- [ ] Resource Server JWT is configured on the chain handling UserInfo.
- [ ] A `JwtDecoder` matching the access token format is present.
- [ ] Decoder verifies using the public key source matching Authorization Server signing keys.
- [ ] Client sends the access token in the bearer header, not ID Token or refresh token.
- [ ] Scopes and consent govern which claim groups are returned.
- [ ] UserInfo always returns the `sub` claim.
- [ ] `sub` in UserInfo matches `sub` in the ID Token identically.
- [ ] Subject is derived from a stable identifier; does not depend on mutable email or display name.
- [ ] If using pairwise subjects, the same resolver applies to ID Token and access token.
- [ ] Replicas share issuer, signing keys/JWKS, and subject mapping.
- [ ] Tests cover invalid tokens, expired tokens, missing scopes, subject mismatch, and key rotation.
- [ ] Logs do not record bearer tokens, ID Tokens, or full personal data.

When diagnosing OIDC UserInfo, identify which step fails: discovery, bearer token verification, scope checks, or subject matching. Proper `JwtDecoder` configuration enables access token verification; a shared subject resolver guarantees UserInfo describes the exact End-User confirmed by the ID Token.
