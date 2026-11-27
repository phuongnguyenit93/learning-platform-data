# Per-Client ID Token Signing Algorithm Policy

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, an ID Token is a JWT carrying user authentication assertions issued by the OpenID Provider (OP) to an OIDC client. The ID Token must be signed using JSON Web Signature (JWS) so the client can verify integrity and origin.

An OP may serve multiple clients with varying compatibility requirements. Legacy clients might only support RSA `RS256`; newer clients might support ECDSA `ES256`. A signing policy must specify which algorithm is permitted for each client, ensure that algorithm appears in the OP's published list, and guarantee a matching private key exists for signing.

Running example: `customer-portal` is registered to use `RS256`; `mobile-app` is registered to use `ES256`. Both run the Authorization Code Flow and receive ID Tokens from the same Authorization Server. When minting tokens, the server reads the `RegisteredClient` configuration, picks the approved algorithm for that client, and signs with the matching key. The client verifies the signature using `alg` in the protected header and the public key from JWKS.

After this lesson, you will be able to:

1. Distinguish the ID Token signing algorithm, the client assertion signing algorithm, and the algorithms advertised by the OP in discovery metadata.
2. Understand the OIDC Dynamic Client Registration field `id_token_signed_response_alg`.
3. Configure algorithms per `RegisteredClient` via `TokenSettings.idTokenSignatureAlgorithm(...)`.
4. Explain how `JwtGenerator`, `JwtEncoder`, and `JWKSource` collaborate to mint ID Tokens.
5. Ensure JWKs have matching key type, curve, `alg`, `use`, and `kid`.
6. Enforce an allow-list during dynamic client registration and persist algorithm settings in the `RegisteredClient` repository.
7. Test algorithms in JWT headers, signatures, discovery metadata, and OIDC client verification.
8. Manage algorithm changes, key rotation, and incidents when no compatible key remains.

**Version scope:** Java examples use Spring Authorization Server 1.5.x, Spring Security 6.x, and the Servlet stack. The primary API is `TokenSettings.Builder.idTokenSignatureAlgorithm(SignatureAlgorithm)`. Newer Spring Security releases integrating Authorization Server may alter packages or configuration style; verify against the Javadoc for your exact version.

## 2. ID Token Signing Algorithms in OIDC

### 2.1. An ID Token Is a Signed JWT

An OIDC ID Token is a security token carrying claims about an End-User authentication event. In JWS compact form, the token has three parts:

~~~text
BASE64URL(protected-header).
BASE64URL(payload).
BASE64URL(signature)
~~~

The protected header declares the signing algorithm, for example:

~~~json
{
  "alg": "RS256",
  "kid": "op-rsa-2026-01",
  "typ": "JWT"
}
~~~

The payload carries claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `auth_time`, `nonce`, and others depending on the flow. The JWS signature lets the client verify the token was not tampered with and was signed by the private key matching a trusted OP public key.

**Signing is not encryption.** With ordinary JWS, both header and payload are readable after Base64URL decoding. If confidentiality via JWE is needed, that is a separate encryption policy with parameters such as `id_token_encrypted_response_alg` and `id_token_encrypted_response_enc`; never confuse them with JWS signing algorithms.

### 2.2. `id_token_signed_response_alg`

OIDC Dynamic Client Registration defines client metadata:

~~~json
{
  "client_name": "customer-portal",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/oidc"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "id_token_signed_response_alg": "RS256"
}
~~~

`id_token_signed_response_alg` specifies the JWS algorithm the client asks the OP to use when signing ID Tokens issued to that client. This is a **per-client setting**, not the algorithm the client uses to sign its own client authentication JWT.

Per OIDC Dynamic Client Registration, if a client omits this field, the default is `RS256`. The OP must still verify that the requested algorithm is supported by the OP and backed by a compatible key configuration.

### 2.3. Three Algorithm Fields Frequently Confused

| Field / API | Who Signs? | Which JWT? | Scope |
| --- | --- | --- | --- |
| `id_token_signed_response_alg` | Authorization Server / OP | ID Token sent to the client | Per-client setting in OIDC registration. |
| `token_endpoint_auth_signing_alg` | OAuth client | `client_assertion` sent to the Token Endpoint when using `private_key_jwt` or `client_secret_jwt` | Client authentication algorithm; does not control the ID Token. |
| `id_token_signing_alg_values_supported` | Published by Authorization Server / OP | Any ID Token the OP can sign | Global list in OpenID Provider Configuration. |

For example, `customer-portal` may require `RS256` ID Tokens while using `client_secret_basic` at the Token Endpoint (no client assertion JWT at all). Another client may request `ES256` ID Tokens while using `private_key_jwt` with a `PS256` client assertion. The two choices are independent.

## 3. Per-RegisteredClient Algorithm Policy

### 3.1. TokenSettings Is the Configuration Location in Spring Authorization Server

Spring Authorization Server models ID Token policies in `TokenSettings`:

~~~java
TokenSettings.builder()
    .idTokenSignatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

`TokenSettings` belongs to `RegisteredClient`, allowing each client to store its own algorithm. The default in Spring Authorization Server 1.5.8 is `RS256`.

Example RS256 client configuration:

~~~java
RegisteredClient customerPortal = RegisteredClient
    .withId("customer-portal-record-001")
    .clientId("customer-portal")
    .clientName("Customer Portal")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri(
        "https://portal.example.com/login/oauth2/code/oidc")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .idTokenSignatureAlgorithm(SignatureAlgorithm.RS256)
        .build())
    .build();
~~~

Example ES256 client:

~~~java
RegisteredClient mobileApp = RegisteredClient
    .withId("mobile-app-record-001")
    .clientId("mobile-app")
    .clientName("Mobile App")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.NONE)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("com.example.mobile:/oauth2redirect")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .idTokenSignatureAlgorithm(SignatureAlgorithm.ES256)
        .build())
    .build();
~~~

These two configurations illustrate different clients; redirect URIs, client authentication methods, and other policies must match the actual application type. Public clients like mobile apps must use PKCE and never rely on an embedded client secret.

### 3.2. Reading Policy From RegisteredClient

When processing an authorization request, the token generation context holds the corresponding `RegisteredClient`. The ID Token algorithm can be read via:

~~~java
SignatureAlgorithm algorithm = context
    .getRegisteredClient()
    .getTokenSettings()
    .getIdTokenSignatureAlgorithm();
~~~

This setting belongs to the client registration record and must never be derived from a browser-sent query parameter at authorization time. If a client changes algorithms, that update must go through a controlled registration update flow persisted in `RegisteredClientRepository`.

### 3.3. Do Not Confuse TokenSettings With ClientSettings

`ClientSettings` holds policies such as requiring PKCE, consent, the client's JWK Set URL, or the JWT signing algorithm used to authenticate the client at the Token Endpoint. `TokenSettings` holds token policies, including the ID Token signing algorithm.

~~~java
ClientSettings clientSettings = ClientSettings.builder()
    .tokenEndpointAuthenticationSigningAlgorithm(
        SignatureAlgorithm.RS256)
    .build();

TokenSettings tokenSettings = TokenSettings.builder()
    .idTokenSignatureAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

This snippet shows two independent configuration groups. `tokenEndpointAuthenticationSigningAlgorithm(...)` takes a `JwsAlgorithm` and applies only to client assertions; `idTokenSignatureAlgorithm(...)` takes a `SignatureAlgorithm` for ID Tokens. Never swap values from one group for the other.

## 4. How Does JwtGenerator Apply the Algorithm?

### 4.1. ID Token Generation Pipeline

In the default setup, `JwtGenerator` can produce JWTs used as OAuth access tokens or OIDC ID Tokens. When the Authorization Code Flow completes and an ID Token is needed:

1. The Authorization Server resolves the `RegisteredClient` for the authorization.
2. The token generation context identifies the token type as ID Token.
3. `JwtGenerator` reads the client's `TokenSettings`.
4. The header is built with the policy-configured JWS algorithm.
5. `JwtEncoder` selects a compatible key from `JWKSource` and signs the JWT.
6. The Authorization Server stores the ID Token on the authorization and returns the token response per the OIDC flow.

~~~mermaid
flowchart TD
    A["Authorization Code Flow completes"] --> B["RegisteredClient"]
    B --> C["TokenSettings.idTokenSignatureAlgorithm"]
    C --> D["JwtGenerator"]
    D --> E["JwsHeader: alg + kid"]
    E --> F["JwtEncoder"]
    F --> G["JWKSource selects matching private key"]
    G --> H["Sign ID Token"]
    H --> I["ID Token returned to OIDC Client"]
~~~

### 4.2. You Do Not Need a Customizer Just to Choose the Algorithm

With the default `JwtGenerator`, configure `TokenSettings` on the client. You do not need to manually overwrite `alg` in `OAuth2TokenCustomizer<JwtEncodingContext>` just to get per-client algorithm selection.

`JwtGenerator.setJwtCustomizer(...)` is an extension point for customizing JWS headers and claims. If a customizer overrides the `alg` header directly, it can break `TokenSettings` policy, desynchronizing the header from key selection or the approved algorithm.

Customize headers only for a concrete JOSE requirement, while checking token type and testing that `alg`, `kid`, JWK, and signature remain consistent.

### 4.3. Changing the ID Token Algorithm Does Not Change Access Tokens

`TokenSettings.idTokenSignatureAlgorithm` configures the ID Token only. Never treat it as a global setting for all JWTs. JWT access tokens have their own signing and key-selection policies through the token generator, encoder, and `JWKSource`.

When switching ID Tokens from `RS256` to `ES256`, inspect the ID Token header. Do not assume JWT access tokens also switch to `ES256` or that opaque access tokens are affected.

## 5. JWK and Key Selection Must Match the Algorithm

### 5.1. Algorithm Determines Key Type

| JWS Algorithm | Typical Key Type | Key Requirements |
| --- | --- | --- |
| `RS256`, `RS384`, `RS512` | RSA | Matching RSA public/private key pair with sufficient modulus size. |
| `PS256`, `PS384`, `PS512` | RSA | RSA key plus RSA-PSS support in the crypto provider/encoder. |
| `ES256` | EC P-256 | Curve P-256 and matching EC key pair. |
| `ES384` | EC P-384 | Curve P-384. |
| `ES512` | EC P-521 | Curve P-521. |

You cannot sign `ES256` with an RSA private key or sign `RS256` with an EC private key. If a client requests an algorithm for which `JWKSource` holds no compatible private key, token generation must fail safely.

### 5.2. JWK Metadata Must Stay Consistent

A signing JWK typically includes:

- `kty`: key type, such as `RSA` or `EC`.
- `use`: `sig` for signatures.
- `alg`: intended algorithm, when attached to metadata.
- `kid`: stable ID allowing clients to locate the right public key.
- Public parameters: e.g., RSA `n`/`e`, EC `crv`/`x`/`y`.
- Private parameters: kept strictly inside internal signing storage, never exposed in public JWKS.

Example public RSA JWK:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "op-rsa-2026-01",
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

Example public EC JWK:

~~~json
{
  "kty": "EC",
  "use": "sig",
  "alg": "ES256",
  "kid": "op-ec-2026-01",
  "crv": "P-256",
  "x": "base64url-x-coordinate",
  "y": "base64url-y-coordinate"
}
~~~

Parameter values above are placeholders, not real keys.

### 5.3. JWKSource Can Hold Multiple Key Types

When an OP serves both `RS256` and `ES256` clients, `JWKSource` can manage multiple JWKs:

~~~java
JWKSet jwkSet = new JWKSet(List.of(
    rsaSigningJwk,
    ecSigningJwk
));

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(jwkSet);
~~~

`rsaSigningJwk` and `ecSigningJwk` are Nimbus JWKs built from their respective key pairs. In production, key material should live in a keystore/KMS/HSM and be loaded via an appropriate key manager—never regenerate random keys on every startup.

`NimbusJwtEncoder` uses a selector based on the JWS header to locate a matching key. Ensure:

1. An active private key exists for the requested algorithm.
2. Multiple private keys do not ambiguously match the selector and prevent selecting a single key.
3. `kid` in the header identifies the exact public JWK in JWKS.
4. The public JWK and signing private key belong to the same pair.
5. Public JWKS contains zero private key parameters.

### 5.4. Do Not Rely Solely on kid

`kid` locates a key inside a JWK Set, yet `kid` alone does not prove an algorithm or key is safe. Resource Servers and OIDC clients must verify signatures against an algorithm allow-list and the right key; never blindly trust whatever algorithm a JWT header declares.

When a single key is permitted for multiple algorithms, ensure key policy explicitly authorizes those algorithms. Separating keys per algorithm/role is preferable when security or audit requirements demand clear boundaries.

## 6. OIDC Dynamic Client Registration

### 6.1. Client Sends the Algorithm in the Registration Request

A registration request may declare:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer <initial-access-token>
Content-Type: application/json

{
  "redirect_uris": [
    "https://partner.example.com/oidc/callback"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "id_token_signed_response_alg": "ES256"
}
~~~

The Dynamic Client Registration endpoint in Spring Authorization Server is **disabled by default**. Enable it only when your organization requires it and has policies protecting initial access tokens, client registration, redirect URIs, and client metadata.

### 6.2. Validate the Algorithm Before Saving

Never accept arbitrary algorithm strings sent by clients. Build an allow-list matching the OP's real capabilities:

~~~java
private static final Map<String, SignatureAlgorithm>
        ALLOWED_ID_TOKEN_ALGORITHMS = Map.of(
            "RS256", SignatureAlgorithm.RS256,
            "ES256", SignatureAlgorithm.ES256
        );
~~~

When receiving `id_token_signed_response_alg`:

1. If omitted, apply the published default (typically `RS256` in OIDC registration).
2. If present, verify it belongs to the allow-list.
3. Verify the OP holds a compatible private key/JWK.
4. Verify the algorithm is advertised in `id_token_signing_alg_values_supported`.
5. Store the algorithm in `RegisteredClient.tokenSettings`.
6. Return registration metadata consistent with the saved value.

If the algorithm is unsupported, reject registration with `invalid_client_metadata` per OIDC Dynamic Client Registration; never silently substitute a different algorithm for what the client requested.

### 6.3. Mapping Registration Metadata to TokenSettings

`OidcClientRegistration` exposes `getIdTokenSignedResponseAlgorithm()`. `OidcClientRegistrationAuthenticationProvider` allows replacing the `RegisteredClient` converter via `setRegisteredClientConverter(...)`. If customizing the converter or enforcing a strict allow-list, map metadata explicitly:

~~~java
private static final Converter<OidcClientRegistration, RegisteredClient>
        DEFAULT_CONVERTER =
            new OidcClientRegistrationRegisteredClientConverter();

private static Converter<OidcClientRegistration, RegisteredClient>
        idTokenAlgorithmConverter() {

    return registration -> {
        RegisteredClient registeredClient =
            DEFAULT_CONVERTER.convert(registration);

        String requestedAlgorithm =
            registration.getIdTokenSignedResponseAlgorithm();

        SignatureAlgorithm algorithm =
            requestedAlgorithm == null
                ? SignatureAlgorithm.RS256
                : ALLOWED_ID_TOKEN_ALGORITHMS.get(requestedAlgorithm);

        if (algorithm == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_client_metadata",
                    "Unsupported id_token_signed_response_alg",
                    null));
        }

        TokenSettings tokenSettings = TokenSettings.withSettings(
            registeredClient.getTokenSettings().getSettings())
            .idTokenSignatureAlgorithm(algorithm)
            .build();

        return RegisteredClient.from(registeredClient)
            .tokenSettings(tokenSettings)
            .build();
    };
}
~~~

This illustrates a custom converter. In real applications, verify whether your version's default converter already maps metadata as needed; if it does, avoid adding a redundant layer. When replacing a converter, preserve all other registration fields such as redirect URIs, grant types, authentication methods, scopes, and client secrets.

### 6.4. Attaching the Converter to the OIDC Registration Provider

Endpoint configuration example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(registration ->
                    registration.authenticationProviders(providers ->
                        providers.forEach(provider -> {
                            if (provider instanceof
                                    OidcClientRegistrationAuthenticationProvider
                                        registrationProvider) {
                                registrationProvider
                                    .setRegisteredClientConverter(
                                        idTokenAlgorithmConverter());
                            }
                        })))))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This snippet shows how to attach the converter to the default provider. The app still needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, a token generator, `JWKSource`, `JwtDecoder`, and other OIDC settings. Protect the registration endpoint with an appropriately scoped access token; never expose it to anonymous callers.

### 6.5. Returning the Saved Algorithm in the Client Registration Response

Client configuration/read responses should echo the active `id_token_signed_response_alg`. Spring Authorization Server provides `setClientRegistrationConverter(...)` to customize converting `RegisteredClient` back into `OidcClientRegistration`.

When using custom converters for both requests and responses:

- Read the algorithm from `registeredClient.getTokenSettings().getIdTokenSignatureAlgorithm()`.
- Return it via `OidcClientRegistration.Builder.idTokenSignedResponseAlgorithm(...)`.
- Never return the originally requested algorithm if the server rejected it or applied another policy.
- Test round-trip behavior: register → store → read back → algorithm remains identical.

## 7. Discovery Metadata and OP Supported Algorithms

### 7.1. `id_token_signing_alg_values_supported`

OpenID Provider Configuration includes:

~~~json
{
  "issuer": "https://auth.example.com",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": [
    "RS256",
    "ES256"
  ]
}
~~~

This is the **global** list of JWS algorithms the OP supports for ID Tokens, not a per-client setting. Every algorithm configured on a `RegisteredClient` must belong to the OP's published list and have real key/encoder support.

### 7.2. Configuring Provider Metadata

Spring Authorization Server provides `OidcProviderConfiguration.Builder.idTokenSigningAlgorithms(...)`:

~~~java
private Consumer<OidcProviderConfiguration.Builder>
        oidcProviderMetadataCustomizer() {

    return builder -> builder.idTokenSigningAlgorithms(algorithms -> {
        algorithms.clear();
        algorithms.add("RS256");
        algorithms.add("ES256");
    });
}
~~~

This customizer must advertise only algorithms the server can currently sign. If the `ES256` key is disabled or the encoder lacks a matching key, remove `ES256` from the list and migrate affected `ES256` clients under a compatibility plan.

### 7.3. Relationship Across the Three Policy Layers

~~~mermaid
flowchart TD
    A["OIDC Discovery: OP supported algs"] --> B["Registration allow-list"]
    B --> C["Client's id_token_signed_response_alg"]
    C --> D["RegisteredClient TokenSettings"]
    D --> E["JwtGenerator"]
    E --> F["JWKSource / JwtEncoder"]
    F --> G["ID Token with matching alg and kid"]
~~~

Discovery states what the OP supports; registration selects one of those algorithms for a client; `TokenSettings` persists that choice; `JwtGenerator` and `JWKSource` execute the signing. If any layer drifts out of sync, failures may surface only when a client executes the Authorization Code Flow.

## 8. Choosing Algorithms and Building an Allow-List

### 8.1. RSA RS256

`RS256` uses RSA with SHA-256. It is the most widely compatible choice across the OIDC ecosystem. For RSA keys, use at least 2048-bit keys per current baselines and manage private keys securely.

Pros:

- Strong compatibility across OIDC clients and JWT libraries.
- Public keys distribute cleanly via JWKS.
- Fits environments with existing RSA signing keys and HSM/KMS support.

Cons:

- Signatures and public keys are larger than EC equivalents.
- Requires sizing keys and throughput appropriately for load.

### 8.2. ECDSA ES256

`ES256` uses ECDSA with curve P-256 and SHA-256. Signatures are shorter than equivalent RSA signatures, yet clients and crypto providers must support the exact curve.

Pros:

- Compact signatures, saving bandwidth.
- Fits environments with solid EC support.

Cons:

- Must verify P-256 compatibility across all clients, HSMs, and encoders.
- Never confuse curve P-256 with P-384 or P-521.

### 8.3. RSA-PSS

`PS256`, `PS384`, and `PS512` use RSA-PSS. They are good options when the entire ecosystem supports them. Test the JWS provider, Nimbus encoder, JWK metadata, and OIDC clients before enabling.

### 8.4. Algorithms Never to Enable Recklessly

- Never advertise an algorithm simply because an enum/library defines its name.
- Never allow `none` for production ID Tokens.
- Never silently downgrade an algorithm if the encoder cannot find a key.
- Never let clients pick algorithms outside the allow-list.
- Never use a symmetric/shared-secret algorithm when key distribution would let multiple parties forge ID Tokens.
- Never confuse JWE encryption algorithms with JWS signing algorithms.

In Spring Authorization Server 1.5.x, `TokenSettings.idTokenSignatureAlgorithm(...)` accepts `SignatureAlgorithm`. If you need algorithms outside the API enum or JWE encryption, build dedicated encoders/generators and test full OIDC interoperability—never cast arbitrary strings to bypass API constraints.

## 9. Safety Controls in JwtEncoder and JWKSource

### 9.1. Never Let Requests Control the Header

A client can submit `id_token_signed_response_alg` during registration or update. Once validated and approved, that value is persisted in `RegisteredClient`. Never read `alg` from an authorization request query parameter or client-sent header on token issuance.

### 9.2. Never Silently Fall Back When Keys Are Incompatible

Suppose a client requires `ES256`, yet `JWKSource` holds only an RSA private key. The server must raise a configuration/issuance error and trigger an alert—never sign with `RS256` and return a token as though registration were satisfied. Silent fallback breaks the client contract and can introduce downgrade vulnerabilities.

### 9.3. Private Key Management

- Keep private keys in a protected keystore, KMS, or HSM.
- Grant the runtime only the signing permissions it needs.
- Public JWKS must expose only public keys.
- Never log private JWKs, PEMs, raw ID Tokens, or client secrets.
- Give each key a unique `kid` with lifecycle management.
- Maintain procedures for rotation, pre-publishing, and retirement.

### 9.4. Never Confuse ID Token Signatures With Client Assertion Signatures

A client using `private_key_jwt` signs its assertion with the **client's** private key. The OP signs the ID Token with the **server's** private key. Those two keys may reside in completely separate trust domains. Never point the OP's private key source at a client's JWKS URI or vice versa.

## 10. Algorithm Changes and Key Lifecycle

### 10.1. Changing a Client's Algorithm

Example migrating `customer-portal` from `RS256` to `ES256`:

1. Confirm the client supports `ES256`.
2. Verify OP discovery metadata advertises `ES256`.
3. Provision/add an EC P-256 signing key to the key manager and JWKS.
4. Update `RegisteredClient.tokenSettings` via your change-management process.
5. Issue a test ID Token and verify `alg=ES256` and the expected `kid`.
6. Verify the client validates the ID Token successfully.
7. Monitor validation errors and maintain a rollback plan.

Previously issued `RS256` ID Tokens still need the old RSA public key for verification until they expire or per revocation policy. Never delete an old public key just because a client switched algorithms.

### 10.2. Rotating Keys Within the Same Algorithm

Routine rotation does not require changing algorithms. For example, rotating RSA key `K1` to RSA key `K2`:

- Pre-publish public `K2` before signing with `K2`.
- Switch the signer to private `K2`.
- New JWTs carry `kid=K2`, `alg=RS256`.
- Keep public `K1` in JWKS until ID Tokens signed with `K1` no longer need verification.
- Only then retire `K1` per policy.

### 10.3. Emergency Revocation

If a private key is compromised, immediately stop signing with it, rotate to a replacement key, remove the compromised public key from trust stores, and assess impacted tokens. Because OIDC clients cache JWKS, removing a public key from the endpoint does not guarantee every client stops trusting it immediately. Coordinate cache refreshes, client policies, and incident response.

### 10.4. Deprecating an Algorithm

When the OP removes an algorithm from discovery:

- Stop accepting new registrations requesting that algorithm.
- Identify existing clients still configured for the legacy algorithm.
- Notify and migrate those clients on a schedule.
- Keep keys in JWKS until outstanding tokens expire, unless compromised.
- Retain compatibility tests for clients yet to migrate.

## 11. Testing Algorithm Policies

### 11.1. Unit Testing RegisteredClient Settings

~~~java
@Test
void customerPortalUsesRs256ForIdToken() {
    assertThat(customerPortal.getTokenSettings()
        .getIdTokenSignatureAlgorithm())
        .isEqualTo(SignatureAlgorithm.RS256);
}

@Test
void mobileAppUsesEs256ForIdToken() {
    assertThat(mobileApp.getTokenSettings()
        .getIdTokenSignatureAlgorithm())
        .isEqualTo(SignatureAlgorithm.ES256);
}
~~~

`customerPortal` and `mobileApp` are `RegisteredClient` instances created in test fixtures. These tests verify stored configuration only; you still need tests against actual minted ID Tokens.

### 11.2. Integration Testing the ID Token Header

After executing the Authorization Code Flow in a test, decode the ID Token's protected header to confirm:

~~~json
{
  "alg": "ES256",
  "kid": "op-ec-2026-01",
  "typ": "JWT"
}
~~~

Never merely Base64URL-decode and call the token valid. Verify the signature with the matching public JWK, then check issuer, audience, expiry, nonce, and required OIDC claims.

### 11.3. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| `RegisteredClient` configured with `RS256` | ID Token header has `alg=RS256`. |
| `RegisteredClient` configured with `ES256` | ID Token header has `alg=ES256`. |
| `TokenSettings` leaves algorithm unset | Defaults to `RS256` per `TokenSettings`. |
| Client requests algorithm outside allow-list | Registration rejected with `invalid_client_metadata`. |
| Client requests `ES256` with no matching EC key | No fallback; issuance fails safely with logs/alerts. |
| JWK has duplicate `kid` across keys | Deployment/configuration validation fails. |
| JWKS lacks public key for `kid` | Client verification fails; test catches mismatch. |
| ID Token signature tampered with | Client verification fails. |
| Client A `RS256`, Client B `ES256` | Each client receives its own configured algorithm. |
| JWT access token in same authorization | Access token algorithm stays governed by its own policy, unaffected by ID Token setting. |
| `token_endpoint_auth_signing_alg` differs from ID Token `alg` | Client assertion and ID Token use their independent algorithms. |
| Discovery omits an active algorithm | Contract test fails. |
| Discovery advertises algorithm lacking key/encoder | Contract test fails. |
| Dynamic registration requests `none` | Rejected by allow-list. |
| Client registration read-back | `id_token_signed_response_alg` matches stored `TokenSettings`. |
| Same-algorithm key rotation | Header `kid` switches to new key; old public key remains in JWKS during overlap. |
| Old token after rotation | Still verifies while old key remains trusted. |

### 11.4. Testing With a Real OIDC Client

Pick the OIDC client library used in production:

1. Register a client with `RS256`.
2. Complete Authorization Code + PKCE.
3. Verify the ID Token via discovery/JWKS.
4. Register another client with `ES256` and repeat.
5. Attempt requesting an algorithm unsupported by the OP.
6. Verify the client rejects ID Tokens signed with untrusted keys or algorithms outside its allow-list.

Interoperability tests catch bugs that builder unit tests miss, such as curve mismatches, JWK `kid` issues, key caching, and client library algorithm limitations.

## 12. Common Errors and Resolutions

### Error 1: Placing the ID Token Algorithm in ClientSettings

**Symptom:** Changing `tokenEndpointAuthenticationSigningAlgorithm` still yields `RS256` ID Tokens.

**Cause:** Confusing the client assertion algorithm with the OP's ID Token signing algorithm.

**Resolution:** Use `TokenSettings.idTokenSignatureAlgorithm(...)`.

### Error 2: Editing Only Discovery Metadata

**Symptom:** OP advertises `ES256`, yet ID Tokens are still signed with `RS256` or fail to sign.

**Cause:** Updated only `id_token_signing_alg_values_supported` without configuring `RegisteredClient`, encoder, or keys.

**Resolution:** Align metadata, `TokenSettings`, `JWKSource`, and integration tests.

### Error 3: EC Key Present Yet JWK Metadata Is Wrong

**Symptom:** `JwtEncoder` cannot find a key for `ES256`.

**Cause:** Wrong curve, wrong `kty`/`alg`/`use`, or key lacks private signing material.

**Resolution:** Check EC P-256, public/private key pair, JWK selector, and `kid`.

### Error 4: Client Requests an Unsupported Algorithm

**Symptom:** Token issuance fails after registration succeeded.

**Cause:** `id_token_signed_response_alg` was not validated at registration time.

**Resolution:** Validate against the allow-list and key support before saving `RegisteredClient`.

### Error 5: Overriding the `alg` Header in a Customizer

**Symptom:** Header says `ES256`, yet the signature was computed with an RSA key or the encoder throws an error.

**Cause:** Customizer overwrote `alg` outside `TokenSettings`/key selection.

**Resolution:** Use `JwtGenerator`'s default per-client policy; if using a custom encoder, test selector, header, and key consistency.

### Error 6: Sharing One Algorithm Across All Clients for Convenience

**Symptom:** Clients with different capabilities cannot register or receive incompatible tokens.

**Cause:** Algorithm configured globally instead of per `RegisteredClient`.

**Resolution:** Store `idTokenSignatureAlgorithm` in each client's `TokenSettings` and enforce a global allow-list.

### Error 7: Removing Old Public Keys Immediately After Rotation

**Symptom:** OIDC clients reject still-unexpired ID Tokens signed by the previous key.

**Cause:** Key removed from JWKS too early.

**Resolution:** Retain old public keys across the overlap window; handle key compromise separately.

### Error 8: Changing Algorithms Without Testing Real Clients

**Symptom:** Unit tests pass, yet mobile/web clients fail to verify ID Tokens.

**Cause:** Client library or platform does not support the chosen algorithm/curve.

**Resolution:** Run interoperability tests on real clients before rollout.

## 13. Production Checklist

| Item | Condition to Confirm |
| --- | --- |
| Client policy | Does every `RegisteredClient` have an approved ID Token algorithm? |
| Default | Do clients omitting the algorithm get a clear default (`RS256`)? |
| Allow-list | Does registration accept only algorithms the OP truly supports? |
| Discovery | Does `id_token_signing_alg_values_supported` match the encoder and key inventory? |
| Key type | Do RSA/EC curves match the algorithm? |
| JWK metadata | Are `alg`, `use`, `kid`, and public parameters accurate? |
| Private key | Protected in keystore/KMS/HSM and never exposed in JWKS? |
| JwtGenerator | Does no customizer override `alg` outside policy? |
| Dynamic registration | Is `id_token_signed_response_alg` validated, persisted, and returned accurately? |
| Client assertion | Is `token_endpoint_auth_signing_alg` managed independently? |
| Key rotation | Are pre-publish, overlap, retirement, and emergency revocation defined? |
| Client compatibility | Have real OIDC clients verified tokens under each algorithm? |
| Observability | Are metrics/logs emitted for `alg`, `kid`, signing failures, and client ID without raw tokens? |
| Persistence | Are `TokenSettings` persisted durably and synchronized across all Authorization Server nodes? |
| Testing | Do unit, integration, DCR, JWKS, rotation, and interoperability tests exist? |

## 14. Hands-On Exercise

An OP serves three clients:

- `web-portal`: supports only `RS256`.
- `mobile-app`: supports `ES256`.
- `partner-rp`: requests `PS256` and registers via OIDC Dynamic Client Registration.

The OP holds RSA key `K1` and EC P-256 key `K2` in `JWKSource`; no verified RSA-PSS key policy exists yet.

1. Configure `TokenSettings` for `web-portal` (`RS256`) and `mobile-app` (`ES256`).
2. Decide whether to accept `PS256` for `partner-rp`; justify based on keys, encoder, and client compatibility.
3. Implement an algorithm allow-list and reject registrations outside it.
4. Map `id_token_signed_response_alg` into `RegisteredClient` `TokenSettings`.
5. Verify the registration response returns the exact persisted algorithm.
6. Configure discovery metadata to advertise only algorithms the OP genuinely supports.
7. Mint ID Tokens for both clients and verify `alg`, `kid`, and signatures using public JWKs.
8. Demonstrate that `token_endpoint_auth_signing_alg` does not affect ID Tokens.
9. Execute an RSA rotation `K1` → `K3` under `RS256` and verify older tokens still validate.
10. Write a test proving the OP never falls back from `ES256` to `RS256` when an EC key is missing.

**Acceptance criteria:** Every OIDC client receives ID Tokens signed with its registered algorithm, that algorithm belongs to the OP's allow-list, the matching public JWK verifies the signature, and the server never silently downgrades when a key is missing.

## 15. References

- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html): ID Tokens, JWS signing, and token verification.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): client metadata `id_token_signed_response_alg` and registration semantics.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `id_token_signing_alg_values_supported`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected headers, algorithms, and JWS signatures.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWK Set and key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): RSA, ECDSA, RSA-PSS, and JOSE algorithms.
- [Spring Authorization Server — TokenSettings.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): `idTokenSignatureAlgorithm(SignatureAlgorithm)`.
- [Spring Authorization Server — TokenSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): default algorithm and getters.
- [Spring Authorization Server — JwtGenerator Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtGenerator.html): generating JWTs for OAuth access tokens and OIDC ID Tokens.
- [Spring Authorization Server — OidcClientRegistration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.Builder.html): `idTokenSignedResponseAlgorithm(...)`.
- [Spring Authorization Server — OidcClientRegistrationAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): converter for dynamic registration.
- [Spring Authorization Server — OidcProviderConfiguration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): list of algorithms published by the OP.
- [Spring Authorization Server — Dynamic Client Registration Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling the endpoint and customizing converters/providers.
