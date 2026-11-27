# Verifying Metadata Consistency with Enabled Endpoints and Actual Features

An Authorization Server can appear to work when manually testing a single endpoint and still break OAuth2 Clients or Resource Servers in production. A common culprit is **metadata advertising a contract that differs from what the server actually supports**: `jwks_uri` returns 404, `issuer` mismatches JWTs, `grant_types_supported` lists an unimplemented grant, or OpenID Provider Configuration advertises `userinfo_endpoint` that gets blocked by a login page.

**OAuth 2.0 Authorization Server Metadata (RFC 8414)** and **OpenID Connect Discovery 1.0** let clients discover configuration without guessing paths. In return, metadata becomes a **public interface and security contract**. Clients rely on it to pick grants, algorithms, authentication methods, and where to fetch the JWK Set. Syntactically valid JSON is not enough: its contents must match *actual endpoints, features, and policies*.

This lesson belongs to the **Metadata and Discovery** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The module scope covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. The focus here is designing **checks ensuring metadata aligns with enabled endpoints and actual features**, applicable to CI/CD and multi-node environments.

> **Principle:** A capability is considered supported only when **(1)** metadata advertises it accurately, **(2)** the endpoint/flow actually works, **(3)** security constraints are enforced, and **(4)** tests prove it. Adding a claim to the discovery document does not make Spring Authorization Server implement the feature.

## 1. Metadata Is a Protocol Contract, Not a URL Directory Page

Metadata is consumed by OAuth2 Clients, Resource Servers, or Relying Parties to configure the issuer and endpoints/capabilities. Key fields typically include:

| Group | Metadata Examples | Meaning |
|---|---|---|
| Identifier | `issuer` | Trust boundary of the Authorization Server |
| Endpoints | `authorization_endpoint`, `token_endpoint` | Authorization and token issuance |
| Public keys | `jwks_uri` | Fetch public keys to verify JWT/JWS |
| Protocol capabilities | `response_types_supported`, `grant_types_supported` | Response types and grants |
| Client authentication | `token_endpoint_auth_methods_supported` | How clients authenticate |
| PKCE | `code_challenge_methods_supported` | Advertised PKCE methods |
| Token status | `revocation_endpoint`, `introspection_endpoint` | Revocation and status verification |
| Extensions | Device Authorization, PAR, DPoP, mTLS, Token Exchange | Optional capabilities |
| OIDC | `userinfo_endpoint`, `id_token_signing_alg_values_supported` | User authentication and ID Token |

A URL appearing in JSON proves only that it is **advertised**, not that the route exists. Likewise, HTTP 200 may be an HTML page or misproxied error. Verification must flow from **configuration → metadata → HTTP behavior → security enforcement**.

### 1.1. Four Layers That Must Align

| Layer | Question | Evidence |
|---|---|---|
| **Configuration** | Which filter/configurer/provider enables the feature? | `SecurityFilterChain`, beans, settings |
| **Metadata** | How is the feature advertised externally? | Actual discovery JSON |
| **Runtime** | Does the flow follow the protocol properly? | HTTP integration tests |
| **Policy** | Are restrictions genuinely enforced? | Negative tests and authorization checks |

### 1.2. Types of Metadata Drift

| Drift Type | Example | Consequence |
|---|---|---|
| Advertised but missing route | `pushed_authorization_request_endpoint` returns 404 | Clients cannot use PAR |
| Advertised but blocked | `jwks_uri` redirects to `/login` | Resource Servers cannot fetch keys |
| Advertised but unsupported | `private_key_jwt` in metadata while server accepts only Basic | `invalid_client` |
| Supported but unadvertised | UserInfo works yet `userinfo_endpoint` is missing | Discovery clients fail to auto-configure |
| Wrong URL | Public domain replaced by `http://localhost:9000` | Issuer/TLS mismatch |
| Missing enforcement | Advertises PKCE yet exchanges codes with wrong verifier | Security vulnerability |
| Node drift | Node A has the new grant; node B lacks the provider | Intermittent errors behind load balancer |

## 2. Distinguishing RFC 8414 from OIDC Discovery

The two discovery documents are related yet **not identical**.

| Criterion | OAuth 2.0 Authorization Server Metadata | OpenID Provider Configuration |
|---|---|---|
| Specification | RFC 8414 | OpenID Connect Discovery 1.0 |
| Purpose | AS OAuth2 capabilities | OpenID Provider capabilities |
| Common well-known suffix | `/.well-known/oauth-authorization-server` | `/.well-known/openid-configuration` |
| Core contents | Issuer, token/authorization endpoints, grants, client auth | Issuer, UserInfo, ID Token signing, subject types, OIDC endpoints |
| Proves OIDC is enabled? | **No** | Only when the OP actually functions |
| Can coexist? | Yes | Yes |

For example, an AS issuing only OAuth2 access tokens does not necessarily support OIDC ID Tokens, UserInfo, or RP-Initiated Logout. Never fabricate an OpenID Provider Configuration just to "complete metadata" when those capabilities are inactive.

### 2.1. Discovery URLs for a Root Issuer

Given issuer:

~~~text
https://identity.example.com
~~~

The two common URLs are:

~~~http
GET https://identity.example.com/.well-known/oauth-authorization-server
GET https://identity.example.com/.well-known/openid-configuration
~~~

Do not assume both exist. OpenID Provider Configuration depends on OIDC functionality being enabled and configured in Spring.

### 2.2. Path-Based Issuers: URL Rules Must Be Tested

Given issuer:

~~~text
https://identity.example.com/tenant/blue
~~~

RFC 8414 places the well-known suffix between the authority and the issuer's path:

~~~text
https://identity.example.com/.well-known/oauth-authorization-server/tenant/blue
~~~

OIDC Discovery 1.0 defines the traditional path by appending the suffix to the issuer:

~~~text
https://identity.example.com/tenant/blue/.well-known/openid-configuration
~~~

Client/server frameworks may try fallback discovery paths depending on profile and version. Test the **exact URI used by real clients**, especially in multi-tenant and context-path deployments; never guess by concatenating URL strings manually.

### 2.3. OAuth2 Does Not Automatically Imply OIDC Semantics

An OAuth2 metadata document advertising `authorization_code` does not prove the AS issues ID Tokens. For OIDC, test an authorization request with `scope=openid` and verify the actual ID Token, signature, `iss`, `aud`, `nonce` when applicable, and corresponding OIDC requirements.

## 3. Verification Flow from Configuration to Behavior

A solid test suite treats metadata as **an input to contract verification**:

~~~mermaid
flowchart TD
    A[Read settings, configurers, registered clients] --> B[GET OAuth2/OIDC discovery]
    B --> C[Verify issuer and public URLs]
    C --> D[Match endpoint fields against active routes]
    D --> E[Match grants, client auth methods, algorithms]
    E --> F[Run positive protocol tests]
    F --> G[Run negative policy/security tests]
    G --> H{Do metadata, runtime, and policy match?}
    H -->|Yes| I[Release gate PASS + contract snapshot]
    H -->|No| J[Fail release, fix config/deployment]
    J --> A
~~~

**Positive tests** prove an advertised capability works for valid clients. **Negative tests** prove the AS rejects invalid requests and truly enforces policies. Testing only a successful authorization code flow, for example, cannot prove PKCE is enforced.

## 4. Verify `issuer` Before Everything Else

`issuer` is the Authorization Server identifier and trust anchor for Clients/Resource Servers. In many profiles, it must **exact-match** the configured issuer and JWT/ID Token `iss`; a single trailing slash difference can cause validators to reject it.

Metadata:

~~~json
{
  "issuer": "https://identity.example.com"
}
~~~

Issued token has the matching claim:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1794850600
}
~~~

### 4.1. Common Issuer Mistakes

- Discovery returns `http://localhost:9000` while APIs expect `https://identity.example.com`.
- Metadata issuer lacks a trailing slash while JWT `iss` includes a trailing slash.
- Tenants A and B unintentionally share an issuer despite separate token stores and keys.
- A proxy adds/strips a context path, causing an issuer mismatch.
- A rolling deployment serves different issuers across nodes.

### 4.2. Configuring a Stable Public Issuer

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .build();
}
~~~

Keep the issuer a controlled **public HTTPS identifier**, never derived blindly from a caller-supplied `Host`. If resolving dynamically per tenant, enforce a tenant resolver, allowed hosts, stable mapping, and isolation tests.

### 4.3. Reverse Proxies and Forwarded Headers

What clients see:

~~~text
https://identity.example.com/oauth2/token
~~~

What the internal application may see:

~~~text
http://authorization-server:9000/oauth2/token
~~~

This is normal when TLS terminates at ingress. However, the server must trust `Forwarded`/`X-Forwarded-*` only from controlled proxies, and the proxy must strip forged headers sent by internet clients. Never let attackers alter host/scheme in metadata via spoofed forwarded headers.

## 5. Are Advertised Endpoints Actually Enabled?

Endpoints in Spring Authorization Server depend on configurers, `AuthorizationServerSettings`, supporting beans, and providers. Never infer capabilities merely from classes on the classpath.

| Metadata field | Endpoint/flow | Must verify |
|---|---|---|
| `authorization_endpoint` | Browser authorization | Login, consent, redirect URI validation |
| `token_endpoint` | Token issuance | POST, client authentication, grant provider |
| `jwks_uri` | JWK Set | GET public keys, verify JWT, no private keys leaked |
| `revocation_endpoint` | Token revocation | POST + auth, token invalidation per RFC 7009 |
| `introspection_endpoint` | Token introspection | POST + auth, `active` per RFC 7662 |
| `device_authorization_endpoint` | Device flow | Issues device/user codes, verification, and polling |
| `pushed_authorization_request_endpoint` | PAR | POST, `request_uri`, `expires_in`, and client binding |
| `userinfo_endpoint` | OIDC UserInfo | OIDC enabled, valid token, permitted claims |
| `end_session_endpoint` | OIDC logout | Session and post-logout redirect validation |
| `registration_endpoint` | Dynamic Client Registration | Real endpoint and registration access policy |

### 5.1. Right HTTP Method and Request Shape

Do not send GET to every URL and conclude HTTP 405 means the endpoint is unsupported. Token, introspection, revocation, and PAR normally expect POST; a rejected GET may show the route exists and is properly guarded. Test with the **right HTTP method, content type, client authentication, and valid request fixtures**.

### 5.2. A Public Discovery Endpoint Does Not Make Every Endpoint Public

Discovery and JWKS usually allow anonymous GET. Introspection/revocation/token endpoints require client authentication, and registration has its own policy. An endpoint returning 401 without credentials is **not** metadata drift; 401 may be exact enforcement.

## 6. `AuthorizationServerSettings`, Filter Chain, and Beans

Spring Authorization Server uses `AuthorizationServerSettings` to define the issuer and protocol endpoint paths. Example:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .tokenEndpoint("/oauth2/token")
        .jwkSetEndpoint("/oauth2/jwks")
        .tokenIntrospectionEndpoint("/oauth2/introspect")
        .tokenRevocationEndpoint("/oauth2/revoke")
        .build();
}
~~~

Example for a Spring Authorization Server branch supporting those methods. If you change `/oauth2/token` to `/oauth2/v2/token`, metadata must advertise the new URL and clients must update accordingly.

### 6.1. Distinct Layers

| Component | Impact | Does Not Guarantee by Itself |
|---|---|---|
| `AuthorizationServerSettings` | Issuer and relative endpoint paths | That optional grants/providers are implemented |
| `OAuth2AuthorizationServerConfigurer` | Wiring protocol filters and extension points | That custom grants function properly |
| `SecurityFilterChain` | Matchers, authentication, ordering | That metadata URLs match the reverse proxy |
| `JWKSource<SecurityContext>` | Key material/JWKS when paired with signing config | Public JWKS rotation/key consistency |
| `RegisteredClientRepository` | Per-client registration, grants, and auth methods | Global metadata matches all clients |
| `OAuth2AuthorizationService` | Stores authorizations and token state | That revocation/introspection filters are enabled |

### 6.2. `SecurityFilterChain` Skeleton

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is a configuration skeleton, not a complete Spring Boot application. It needs beans such as client repository, authorization services, signer/JWK source, and a login chain. Tests must verify discovery/JWKS return JSON rather than redirecting to a form login page.

## 7. When Is OpenID Provider Configuration Published?

**OIDC is not synonymous with OAuth2.** In Spring Authorization Server, OIDC functionality must be enabled via the version-appropriate OIDC configurer:

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
            .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This snippet illustrates only how to enable OIDC protocol support; other beans and login/consent config remain necessary. Never advertise OpenID Provider Configuration merely because the server issues OAuth2 access tokens.

### 7.1. OIDC Fields to Verify

| OP metadata field | Meaning | Corresponding Test |
|---|---|---|
| `issuer` | OP identifier | Compare with ID Token `iss` |
| `authorization_endpoint` | Authorization endpoint | Login and consent with `scope=openid` |
| `token_endpoint` | Token issuance | Code exchange + ID Token |
| `jwks_uri` | Public signing keys | Verify ID Token signature by `kid` |
| `userinfo_endpoint` | UserInfo | Access with valid token; claims per consent |
| `response_types_supported` | Supported OIDC response types | Corresponding flows actually work |
| `subject_types_supported` | `public`/`pairwise` | Behavior of `sub` |
| `id_token_signing_alg_values_supported` | ID Token algorithms | Actual signature matches |
| `scopes_supported` | Advertised scopes | Requests follow policy |
| `claims_supported` | Claims OP can provide | No over-disclosure |
| `end_session_endpoint` | OIDC logout if enabled | Logout/redirect validation |
| `registration_endpoint` | Dynamic registration if enabled | Registration access policy |

Do not add `ES256` if the signer only produces `RS256` ID Tokens, or advertise `pairwise` subjects when the OP only returns a global `sub`.

### 7.2. The `openid` Scope Has Protocol Semantics

`scope=openid` activates OIDC authentication semantics, including ID Tokens and associated requirements. If the server accepts that scope yet fails to issue an ID Token in the requested flow, or metadata advertises OIDC while runtime mishandles it, that is a contract failure.

## 8. `jwks_uri` Must Verify Real Tokens

Metadata:

~~~json
{
  "issuer": "https://identity.example.com",
  "jwks_uri": "https://identity.example.com/oauth2/jwks"
}
~~~

JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sign-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

This is illustrative JSON and does not contain a real RSA public modulus.

### 8.1. Checking Beyond HTTP 200

1. GET `jwks_uri` from outside the cluster with no login cookies.
2. Check HTTPS, status 200, JSON content type, and a `keys` array.
3. Every JWK must be public-only; RSA exposes no `d`/CRT parameters, EC/OKP exposes no private `d`, and no symmetric `oct.k` secrets are published.
4. Real JWTs carry a `kid` matching a key in the set.
5. Header `alg` matches the key type and verification allowlist.
6. Resource Servers verify signature, issuer, expiry, and audience of real tokens.

### 8.2. Key Rotation Is Also a Contract

Never remove public key K1 from JWKS immediately upon switching the signer to K2 if K1-signed tokens are still unexpired. Pre-publish K2 first, wait for consumer caches to refresh, switch the signer, retain K1 through the overlap window, and only then retire K1. Tests must verify both K1 and K2 tokens during the transition window.

### 8.3. JWK Set Endpoint Depends on the Key Source

In Spring Authorization Server, an appropriate `JWKSource<SecurityContext>` is essential for the JWK Set Endpoint to function in a JWT-signing architecture. Never inject a custom `jwks_uri` when the server has no matching public keys to publish.

## 9. Grants and Response Types: Advertise Only Working Flows

Example:

~~~json
{
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ]
}
~~~

Use this example only for a server that genuinely supports all three grants. Do not assume a dependency enables every grant automatically.

### 9.1. Globally Supported Differs from Per-Client Allowed

Metadata describes **global AS capabilities**, not `RegisteredClient` overrides. The server may support `client_credentials` and `authorization_code`, yet:

- `backend-service` may be permitted only client credentials;
- `web-app` may be permitted only authorization code;
- `mobile-app` may be permitted only authorization code with PKCE.

Do not judge metadata wrong merely because one client is denied a grant the server supports for another client. Write positive tests with **clients registered for that grant**, and negative tests with unauthorized clients.

### 9.2. Custom Grants and Token Exchange

If adding `urn:ietf:params:oauth:grant-type:token-exchange` per RFC 8693, ensure you have a converter parsing `grant_type`, a policy-enforcing provider, eligible `RegisteredClient`s, an appropriate token generator/state, and positive/negative tests. Only then advertise the grant. Adding a string to metadata **does not create a provider**.

### 9.3. Response Type Differs from Grant Type

`response_types_supported=["code"]` means the authorization endpoint returns an authorization code. `grant_types_supported=["authorization_code"]` means the token endpoint exchanges codes for tokens. Never add `token` or `id_token` response types when the server supports only the Authorization Code Flow.

## 10. PKCE: Metadata and Enforcement Must Go Together

PKCE metadata may contain:

~~~json
{
  "code_challenge_methods_supported": ["S256"]
}
~~~

This field advertises the PKCE methods the AS supports; it **does not prove** every client is forced to use PKCE. Requiring PKCE depends on `ClientSettings.requireProofKey`, client type, and system policy.

### 10.1. Positive Test

1. Valid client sends `response_type=code` with `code_challenge_method=S256`.
2. Authorization endpoint validates `redirect_uri` and stores `code_challenge`.
3. Token endpoint receives matching `code_verifier`.
4. AS issues token response per protocol.

### 10.2. Negative Tests

| Case | Outcome |
|---|---|
| Authorization code bound to challenge, missing verifier | Rejected |
| Verifier does not match challenge | Rejected |
| Method outside deployment allowlist | Rejected |
| Client requires PKCE, request omits challenge | Rejected |
| Authorization code replayed | Rejected |

If metadata advertises `plain`, verify policy actually permits that method. If your organization permits only S256, do not advertise unapproved methods just because a library can parse them.

## 11. Client Authentication Methods and Algorithms

Example OAuth2 metadata:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "token_endpoint_auth_signing_alg_values_supported": [
    "RS256",
    "PS256"
  ]
}
~~~

This illustrates a single deployment. Separate **how an OAuth2 Client authenticates** from **client assertion signing algorithms**.

### 11.1. Method Matrix

| Metadata value | Characteristics | Tests |
|---|---|---|
| `client_secret_basic` | Client credentials in HTTP Basic | Valid/invalid secret, valid client ID |
| `client_secret_post` | Client secret in form body | Allowed by registration; body logs redacted |
| `client_secret_jwt` | JWT client assertion signed with shared secret | `aud`, `iss`, `sub`, `exp`, signature, and replay |
| `private_key_jwt` | Client assertion signed with private key | Public JWK, signature, alg allowlist |
| `tls_client_auth` | mTLS with certificate per registration | Certificate identity and chain validation |
| `self_signed_tls_client_auth` | Registered self-signed certificate | Certificate match and policy |
| `none` | Public client with no secret | Only in allowed grants/endpoints |

Never advertise a method that lacks an `AuthenticationProvider`/configuration or is rejected by policy for every `RegisteredClient`.

### 11.2. Token Endpoint vs. Introspection Endpoint

`introspection_endpoint_auth_methods_supported` and `revocation_endpoint_auth_methods_supported` (if present) need not match `token_endpoint_auth_methods_supported`. For example, an AS may have public clients for Authorization Code + PKCE while restricting introspection to confidential Resource Servers.

Never copy the token endpoint auth methods list onto introspection when policies differ. An endpoint returning 401 when credentials are missing may be behaving completely correctly.

### 11.3. ID Token Signing Is Not Client Assertion Signing

`id_token_signing_alg_values_supported` (OIDC) describes algorithms the AS uses to sign ID Tokens. `token_endpoint_auth_signing_alg_values_supported` describes client assertion algorithms accepted at the token endpoint. DPoP proof signing is yet another layer. Each list must accurately reflect the implementation and allowlist for its **corresponding purpose**.

## 12. Revocation and Introspection: Routes Must Match Semantics

### 12.1. Token Revocation per RFC 7009

If metadata includes `revocation_endpoint`, test:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic REGISTERED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_TO_REVOKE&token_type_hint=access_token
~~~

Receiving HTTP 200 alone does not prove the token was invalidated. Run introspection or call an API afterward to confirm state changed per policy. Under RFC 7009, nonexistent tokens normally still return a success response to limit token enumeration.

### 12.2. Token Introspection per RFC 7662

If metadata advertises `introspection_endpoint`, test:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.com
Authorization: Basic RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN&token_type_hint=access_token
~~~

Introspection response for an active token:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "portal-web",
  "sub": "user-42",
  "exp": 1794850600
}
~~~

After revocation/expiry, a properly authenticated introspection request normally receives `active=false` without sensitive claims. Distinguish `invalid_client` errors from an **inactive token**: one is a client authentication failure, the other is token state.

### 12.3. A Protected Route Is Not a Missing Route

Do not send anonymous GETs to introspection or revocation and conclude they do not exist because they return 401/405. Test proper POSTs with valid client credentials and invalid credentials, verifying both success semantics and security enforcement.

## 13. PAR: Advertising the Endpoint and Mandatory Enforcement

**Pushed Authorization Requests (RFC 9126)** allow clients to send authorization parameters over a back-channel, receive a short-lived `request_uri`, and redirect the browser with that `request_uri`.

When PAR is supported, metadata may include:

~~~json
{
  "pushed_authorization_request_endpoint":
    "https://identity.example.com/oauth2/par",
  "require_pushed_authorization_requests": false
}
~~~

Two distinct pieces of information:

- `pushed_authorization_request_endpoint`: the advertised PAR endpoint.
- `require_pushed_authorization_requests`: whether authorization requests must use PAR per metadata/policy.

**Having a PAR endpoint does not mean every client is required to use PAR.** If `require_pushed_authorization_requests=true` is advertised, negative tests must prove direct authorization requests bypassing PAR are rejected under the mandatory policy.

### 13.1. Testing Real PAR

1. Properly registered client (method/grant) POSTs to PAR.
2. AS validates client, redirect URI, PKCE, and authorization parameters.
3. AS returns `201 Created` with `request_uri` and `expires_in`.
4. Browser navigates to the authorization endpoint with `client_id` and `request_uri`.
5. AS rejects expired, wrong-client, or invalid `request_uri` values.

Do not merely assert that JSON metadata has a PAR URL; execute the flow and test reference security constraints.

## 14. Device Flow, Token Exchange, DPoP, mTLS, and Extensions

| Capability | Metadata Field | Runtime Verification |
|---|---|---|
| **Device Authorization (RFC 8628)** | `device_authorization_endpoint`, device grant | Device/user code issuance, verification, polling/expiry |
| **Token Exchange (RFC 8693)** | Token exchange in `grant_types_supported` | Converter/provider, subject/actor token policy |
| **DPoP (RFC 9449)** | `dpop_signing_alg_values_supported` when published | Proof signature, `htm`/`htu`/`iat`/`jti`/`ath`, `cnf.jkt`, RS checks |
| **mTLS (RFC 8705)** | mTLS auth methods and `tls_client_certificate_bound_access_tokens` when present | Certificate binding and verification |
| **Authorization response issuer (RFC 9207)** | `authorization_response_iss_parameter_supported` | `iss` in authorization response matches issuer |
| **JWT-Secured Authorization Request (RFC 9101)** | Request Object capabilities | Signed Request Object, validation/precedence |
| **RP-Initiated Logout (OIDC)** | `end_session_endpoint` | Session/redirect allowlist |

### 14.1. DPoP Advertised vs. Enforced

If DPoP proof algorithms are advertised, the AS must verify proofs at the token endpoint and issue sender-constrained tokens—such as `token_type=DPoP` with confirmation binding `cnf.jkt`. Resource Servers must also enforce proof verification when accepting access tokens. AS metadata **does not automatically enable DPoP on every Resource Server**.

Test bad proof signatures, wrong `htm`/`htu`, stale proofs, replays, and access token binding mismatches. Checking the algorithm string in metadata alone does not prove DPoP works.

### 14.2. Token Exchange Advertised vs. Provider

If `grant_types_supported` lists `urn:ietf:params:oauth:grant-type:token-exchange`, the token endpoint must have a converter, provider, `RegisteredClient` grant permission, and policy for subject/actor tokens. Also test off-allowlist audiences and invalid subject tokens.

### 14.3. Version-Dependent Capabilities

Extensions are added across Spring Authorization Server/Spring Security releases; APIs can shift as Spring Authorization Server integrates more deeply into Spring Security. Never copy "latest" docs into an older BOM. Check dependency versions, configuration, runtime metadata, and positive/negative tests.

## 15. Custom Metadata: Use the Right Extension Points

Spring Authorization Server exposes customization points for OAuth2 AS Metadata and OIDC Provider Configuration in supported versions. You can add custom claims, yet **you cannot use a customizer alone to enable a missing endpoint or provider**.

### 15.1. OAuth2 Authorization Server Metadata Customizer

Spring Authorization Server 1.5.x DSL example:

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
            .authorizationServerMetadataEndpoint(metadata -> metadata
                .authorizationServerMetadataCustomizer(builder -> builder
                    .claim("service_documentation",
                        "https://docs.example.com/authz"))
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

`service_documentation` is an illustrative custom metadata field, not a required RFC 8414 claim. Verify builder/method signatures against your actual BOM. Never use a customizer to rewrite a nonexistent URL into another URL just to make a test pass.

### 15.2. OIDC Provider Configuration Customizer

When OIDC is enabled, you can customize the OP document:

~~~java
http.with(authorizationServer, server -> server
    .oidc(oidc -> oidc
        .providerConfigurationEndpoint(provider -> provider
            .providerConfigurationCustomizer(builder -> builder
                .claim("service_documentation",
                    "https://docs.example.com/oidc"))
        )
    )
);
~~~

This is a fragment for a full `SecurityFilterChain`, not a standalone app. Do not call the OIDC customizer and assume UserInfo or Dynamic Client Registration was enabled automatically.

### 15.3. Metadata Changes You Must Not Make Arbitrarily

Never hardcode:

- `userinfo_endpoint` when UserInfo is disabled;
- `registration_endpoint` while Dynamic Client Registration remains off;
- `id_token_signing_alg_values_supported` differing from the real signing algorithm;
- `token_endpoint_auth_methods_supported` differing from real Client Authentication Providers;
- `grant_types_supported` containing undeployed grants;
- `issuer` differing from `AuthorizationServerSettings` and JWT `iss`;
- `jwks_uri` pointing to a set lacking the active signing public key.

**The right fix:** enable or repair the feature implementation, prove behavior, and then update metadata if needed.

## 16. Smoke Testing Through the Public Reverse Proxy

`MockMvc` tests inside the application but does not prove ingress, TLS, and public DNS work. Run a smoke test from a client-like external environment:

~~~bash
curl --fail-with-body -sS \
  https://identity.example.com/.well-known/oauth-authorization-server

curl --fail-with-body -sS \
  https://identity.example.com/.well-known/openid-configuration

curl --fail-with-body -sS \
  https://identity.example.com/oauth2/jwks
~~~

Call the OIDC document only if the OP is actually enabled; use the deployment's public metadata URLs for everything else.

### 16.1. Checking Redirects, TLS, and JSON

- Status 200 for valid discovery/JWKS.
- JSON content type, never HTML or `302 /login`.
- Public issuer is a stable HTTPS URL.
- No internal hostnames, ports, or private IPs exposed.
- Valid TLS hostname/certificate.
- No browser session or cookies required to fetch metadata/JWKS.
- Advertised endpoint URLs are reachable by Resource Servers outside the cluster.

### 16.2. Context Path Must Match

With public issuer `https://identity.example.com/auth`, published URLs may look like:

~~~json
{
  "issuer": "https://identity.example.com/auth",
  "authorization_endpoint":
    "https://identity.example.com/auth/oauth2/authorize",
  "token_endpoint":
    "https://identity.example.com/auth/oauth2/token",
  "jwks_uri":
    "https://identity.example.com/auth/oauth2/jwks"
}
~~~

This is a deployment example; test the actual routes on the proxy and servlet context rather than assuming relative settings paths automatically prepend the right prefix.

### 16.3. Never Trust Caller-Supplied Forwarded Headers

Public endpoint URLs must come from configuration or a proxy-trust-aware resolver, never from arbitrary client-supplied `X-Forwarded-Host`. The gateway must strip/rewrite headers from the internet, and the AS must trust only allowlisted proxies. Test Host-header injection to prevent metadata poisoning.

## 17. Testing Metadata with MockMvc

Integration tests should exercise the real `SecurityFilterChain` and real configuration beans rather than mocking all JSON metadata.

### 17.1. Basic OAuth2 Metadata Check

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerMetadataTests {

    @Autowired
    MockMvc mvc;

    @Test
    void oauth2MetadataMatchesConfiguredIssuerAndEndpoints()
            throws Exception {
        mvc.perform(get("/.well-known/oauth-authorization-server"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                .value("https://identity.example.com"))
            .andExpect(jsonPath("$.authorization_endpoint")
                .value("https://identity.example.com/oauth2/authorize"))
            .andExpect(jsonPath("$.token_endpoint")
                .value("https://identity.example.com/oauth2/token"));
    }
}
~~~

This test skeleton requires complete AS/issuer beans. If the deployment uses custom endpoints, source expected values from the official contract rather than hardcoding default routes.

### 17.2. OIDC Metadata When OIDC Is Enabled

~~~java
@Test
void oidcProviderMetadataContainsJwksAndIdTokenAlgorithms()
        throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://identity.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
            .value("https://identity.example.com/oauth2/jwks"))
        .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
            .isArray());
}
~~~

This test applies only to profiles with OIDC enabled. Also obtain a real ID Token, compare `alg`/`kid` against JWKS, and verify the signature; a non-empty algorithms array alone does not prove the signer matches.

### 17.3. Absence of Disabled Features

For example, OIDC enabled while Dynamic Client Registration is disabled:

~~~java
@Test
void metadataDoesNotAdvertiseDisabledRegistration()
        throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registration_endpoint").doesNotExist());
}
~~~

For profiles without OIDC enabled, do not use this test as though OP discovery must always exist.

### 17.4. Checking PKCE Advertised Method

~~~java
@Test
void metadataAdvertisesS256() throws Exception {
    mvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.code_challenge_methods_supported")
            .isArray());
}
~~~

Then parse the methods array and assert `S256` is present when confirmed as a supported capability. Another test must run a real Authorization Code + PKCE flow and test wrong verifiers. Do not rely solely on JSON snapshots.

## 18. Test Suite Driven by Advertised Capabilities

| Metadata field | Required Test When Field Is Present |
|---|---|
| `authorization_endpoint` | Authorization + invalid redirect negative |
| `token_endpoint` | Successful grant POST and bad auth |
| `jwks_uri` | GET public JWKS, JWT signature, private-key leak scan |
| `revocation_endpoint` | POST revoke, inspect token state post-revoke |
| `introspection_endpoint` | POST active/inactive, client auth |
| `pushed_authorization_request_endpoint` | PAR success, `request_uri` binding/expiry |
| `device_authorization_endpoint` | Device code, user verification, polling/expiry |
| `userinfo_endpoint` | UserInfo token/scope/consent |
| `registration_endpoint` | Registration authorization and validation |
| `dpop_signing_alg_values_supported` | DPoP proof/binding/nonce/RS |
| `code_challenge_methods_supported` | PKCE success + verifier negative |
| `token_endpoint_auth_methods_supported` | One client fixture per advertised auth method |

### 18.1. Representative Client Suite

~~~text
web-client          -> authorization_code, confidential auth
mobile-public       -> authorization_code + PKCE, no secret
machine-client      -> client_credentials
private-key-client  -> private_key_jwt
resource-server     -> introspection credentials
device-client       -> device grant, if enabled
par-client          -> PAR, if enabled
~~~

Tests must prove success for permitted clients and rejection for unpermitted clients. This reconciles global metadata against per-client policy.

### 18.2. Do Not Test Every Endpoint with GET

Token, introspection, revocation, and PAR have POST semantics. A GET returning 401/405 does not prove the capability is absent. Use proper protocol request fixtures rather than guessing from a single status code.

### 18.3. Test Algorithms with Real Tokens or Proofs

If OP metadata lists RS256, fetch a real ID Token and verify its signature. If `private_key_jwt` is advertised, construct a real signed client assertion and test bad-audience/expired assertions. If DPoP is advertised, test proofs with wrong method/URI/token binding. Checking the algorithm string in JSON alone is insufficient.

## 19. Metadata Consistency in Clusters and Rolling Deployments

Production Authorization Servers normally run across multiple nodes, availability zones, and load balancers. A new node exposing a new endpoint/grant while an older node lacks it causes metadata to be **right on node A yet wrong on node B**. Clients discover from node A, hit node B on the next request, and fail.

### 19.1. Properties That Must Stay Synchronized

- Public `issuer` and endpoint URLs;
- Advertised metadata fields and capability lists;
- Signing key set, current `kid`, and key rotation policy;
- `RegisteredClient` registrations and client authentication methods;
- Grant converters/providers and OIDC/PKCE/PAR/DPoP policies;
- Token/authorization persistence and revocation state;
- Proxy settings, context path, TLS routing, and ingress rules.

### 19.2. Comparing Nodes via Canonical Metadata

A health check can GET discovery on each node over a protected internal test channel, parse JSON, and canonicalize field/array ordering semantically. Compare fields expected to match; do not compare raw JSON strings if serializer ordering varies without semantic change.

~~~text
node-a:
  issuer = https://identity.example.com
  grants = authorization_code, refresh_token, client_credentials
  jwks_uri = https://identity.example.com/oauth2/jwks

node-b:
  issuer = https://identity.example.com
  grants = authorization_code, refresh_token
  jwks_uri = https://identity.example.com/oauth2/jwks

=> DRIFT: node-b does not yet support or advertise client_credentials
~~~

Detecting a mismatch is the starting point; runtime tests are still needed to confirm which node lacks the feature.

### 19.3. Release Order When Adding a Capability

A safe sequence:

1. Deploy converter/provider/endpoint and security policy for the new capability across all nodes or a controlled canary.
2. Run protocol positive tests and security negative tests.
3. Run smoke tests through the proxy/load balancer, confirming rollout consistency.
4. Only after the capability is ready, **advertise it in metadata**.
5. Monitor client errors and keep metadata rollback ready if needed.

When removing a capability, reverse carefully under a deprecation/migration plan: stop advertising in a controlled manner, notify clients, wait through the transition window, and only then remove endpoints/providers. Never delete a route immediately while clients still rely on cached metadata.

### 19.4. Metadata and JWKS Caching

Clients/Resource Servers may cache discovery and JWKS. Changing endpoint URLs or algorithms in a single deploy means new metadata may not reach every client immediately. Maintain a compatibility window, appropriate cache headers, and a rollout plan. For key rotation specifically, pre-publish the new public key before signing with it and keep the old public key throughout the overlap window.

## 20. Security Review for Discovery and Metadata

Metadata is usually public data, yet its contents directly steer client trust decisions and where tokens/credentials are sent.

### 20.1. Metadata Poisoning and Host-Header Injection

If an AS constructs `issuer` or `token_endpoint` from an uncontrolled `Host`/`X-Forwarded-Host`, attackers can make discovery advertise their own domain. Clients lacking trust-anchor checks may send client secrets, authorization codes, or tokens to untrusted URLs.

Controls:

- Configure stable public issuer/endpoint URLs;
- Define explicit allowed hosts and trusted proxies;
- Have the gateway strip client-supplied forwarded headers;
- Never treat a URL from a token header, query parameter, or untrusted metadata as an issuer;
- Resource Servers/Clients must fetch metadata only from pre-configured trusted issuers.

### 20.2. Never Advertise Insecure Algorithms

Never advertise `none` as an ID Token signing algorithm in deployments requiring signed tokens. Never let a JWT header dictate the verification algorithm; verifiers need an allowlist. If metadata lists RS256 while tokens are signed with a non-policy algorithm, fix the signer/configuration rather than relaxing the verifier.

### 20.3. Public Discovery Differs from Public Administrative APIs

Discovery/JWKS can allow public GETs, whereas introspection/revocation require client authentication, Dynamic Client Registration requires its own policy, and key/client administration requires strict authorization. Never infer from "public metadata" that all endpoints listed inside metadata allow anonymous access.

### 20.4. False Assurance from Metadata

Metadata may claim support for PKCE, DPoP, PAR, or mTLS without guaranteeing that:

- PKCE is enforced for policy-covered clients;
- DPoP proofs are verified and access tokens carry a matching `cnf.jkt`;
- PAR is enforced when `require_pushed_authorization_requests` is advertised as true;
- Resource Servers verify certificate bindings on mTLS-bound access tokens;
- Token exchange checks actor/subject/audience per policy.

Only negative tests and end-to-end protocol validation prove real enforcement.

## 21. Operations and Alerting on Metadata Drift

| Signal | Meaning | Alert/Check to Track |
|---|---|---|
| Discovery status/latency | Is the discovery endpoint available? | 5xx, TLS errors, latency spikes |
| Unexpected `issuer` | Wrong domain/tenant/proxy | Exact mismatch vs. expected contract |
| Metadata URL 404/302 | Wrong route or filter chain | Smoke check failed |
| Missing active `kid` in JWKS | Key publish/rotation failure | JWT signature failures |
| Rising `unsupported_grant_type` | Grant advertised yet provider/registration missing | Compare metadata and logs |
| Rising `invalid_client` | Advertised auth method unusable | Group by auth method |
| PKCE verification failures | Client config/policy drift | Spike in `invalid_grant` |
| PAR `request_uri` errors | PAR store/TTL/cluster issue | Rising `invalid_request_uri` |
| DPoP binding failures | AS/RS support mismatch | Rising 401s and proof errors |
| Introspection active after revoke | Cache/store inconsistency | Exceeds revocation freshness SLA |
| Per-node metadata mismatch | Rolling deployment/config drift | Differing contract fingerprints |

### 21.1. Never Log Sensitive Data

You may log metadata version, issuer, endpoint names, and contract hashes. Never log raw access tokens, authorization codes, client secrets, private keys, DPoP proofs, JWT assertions, or request bodies carrying credentials. For introspection, log only correlation IDs and privacy-compliant aggregate metrics.

### 21.2. Contract Fingerprint

A system can canonicalize key metadata fields and hash them to detect changes:

~~~text
contractFields = {
  issuer,
  authorization_endpoint,
  token_endpoint,
  jwks_uri,
  response_types_supported,
  grant_types_supported,
  token_endpoint_auth_methods_supported,
  code_challenge_methods_supported,
  optional_feature_endpoints
}

fingerprint = sha256(canonical_json(contractFields))
~~~

This is pseudocode; define canonicalization explicitly, including how order-insensitive arrays are sorted. Hashing detects drift, yet **does not replace behavioral tests**, because two nodes can emit identical metadata while one node's provider is broken.

## 22. Symptom-Based Troubleshooting

| Symptom | Likely Cause | Investigation Path |
|---|---|---|
| Client reports issuer mismatch | Discovery issuer differs from expected or JWT `iss` | Exact string, public issuer settings, proxy |
| Resource Server fails to create `JwtDecoder` | Missing `jwks_uri` or unreachable URL | `JWKSource`, GET JWKS, issuer trust |
| JWKS redirects to login | Wrong `SecurityFilterChain`/matcher/order | Public JWKS route, entry point |
| Grant advertised yet token endpoint reports unsupported | Missing provider, wrong converter, or skewed rollout | Converter/provider/registration + per-node tests |
| `private_key_jwt` advertised yet `invalid_client` | Broken client assertion validation or auth method | JWK, `aud`/`exp`/alg/registration |
| OIDC Client cannot locate UserInfo | OIDC disabled or route missing | `oidc(...)`, UserInfo integration test |
| ID Token signature fails verification | Active signing key absent from JWKS | `kid`, key source, rotation/cache |
| PAR URL present yet returns 404 | Filter or proxy route unimplemented | POST PAR with client credentials |
| PAR required yet direct requests still succeed | Metadata flag not enforced | Direct authorization negative test |
| PKCE method advertised yet exchange skips verifier check | Wrong policy/provider customization | Wrong/missing verifier negative test |
| Works on localhost, fails in production | Public host/path/TLS mismatch | External smoke test through ingress |
| Stale metadata after deploy | Stale client/CDN/cache | `Cache-Control`, rollout, compatibility |
| Node A OK, node B fails intermittently | Metadata/providers/key set differ by node | Per-node contract + flow tests |
| Revoked token still `active:true` | Long introspection cache or skewed auth store | Cache TTL, shared persistence, revocation SLA |

### 22.1. Root-Cause Workflow

1. Fetch the discovery document from the **public URL** used by clients.
2. Compare issuer, endpoint URLs, and capabilities against the expected deployment contract.
3. Reproduce a protocol-compliant HTTP request with a properly registered test client.
4. Inspect response bodies and headers, not just status codes.
5. Run matching negative tests to verify enforcement.
6. Compare across nodes and inspect caches/rolling deployment state.
7. Fix implementation/settings/metadata at the right layer, then re-run the release gate.

Do not rush to edit metadata JSON when a route, filter, or provider is actually missing; doing so hides security defects.

## 23. Pre-Release Production Checklist

1. **Issuer:** Do OAuth2/OIDC metadata `issuer` match the public HTTPS identifier and JWT/ID Token `iss`?
2. **Discovery:** Do well-known URLs return valid JSON without redirecting to login?
3. **OIDC:** Is OP Configuration advertised only when OIDC is truly enabled and ID Tokens work?
4. **URLs:** Does every endpoint in metadata route properly through the reverse proxy?
5. **Methods:** Were GET/POST, form bodies, client auth, and responses verified per protocol?
6. **JWKS:** Public GET, no private fields leaked, and public key present for the active signing `kid`?
7. **Grants:** Does each advertised grant have a real converter/provider and an authorized test client?
8. **Response types:** Does the AS return the right types without advertising unimplemented implicit/hybrid?
9. **PKCE:** Does S256 work, and are wrong/missing verifiers rejected when required?
10. **Client auth:** Was each advertised method tested with a matching client fixture?
11. **Introspection:** Are Resource Server client auth, active/inactive semantics, and claim disclosure accurate?
12. **Revocation:** Protected by client auth, invalidating tokens, and reflected accurately in introspection?
13. **PAR:** Do the endpoint, `request_uri` TTL/client binding, and required-PAR policy match metadata?
14. **Device/Exchange:** Do optional flows have providers/policies and E2E tests before being advertised?
15. **DPoP/mTLS:** Are AS issuance and RS token-binding validation compatible?
16. **Algorithms:** Do ID Token signing/client assertion/DPoP methods match actual allowlists?
17. **Client policy:** Do tests distinguish global server support from per-`RegisteredClient` grants?
18. **Proxy:** Trusted forwarded headers, no internal hostnames leaked, immune to host-header injection?
19. **Cluster:** Are issuers/capabilities/keys consistent across all nodes?
20. **Rollout:** Are contract snapshots, smoke tests, and compatibility/deprecation windows in place?
21. **Monitoring:** Are metadata drift and key/flow error alerts active without logging credentials?
22. **Security:** Are negative tests present for redirect URIs, PKCE, client auth, PAR, DPoP, and unsupported grants?

## 24. Case Study Exercises

**Scenario A — OIDC disabled yet discovery still published.** A team creates a custom route returning `/.well-known/openid-configuration` with hand-crafted JSON including `userinfo_endpoint`, while the application never enables the OIDC configurer. List the tests to run, explain why the metadata is wrong, and propose a remediation order.

**Scenario B — Wrong issuer behind reverse proxy.** The AS runs internally at `http://as:9000`, while clients use `https://login.example.com`. Metadata advertises the internal URL. Design the `AuthorizationServerSettings` configuration, proxy trust boundary, and JWT `iss` verification.

**Scenario C — PKCE advertised yet unenforced.** Metadata has `code_challenge_methods_supported=["S256"]`. A public client can still exchange a code for a token even with a wrong `code_verifier`. Why is testing only HTTP 302 from the authorization endpoint insufficient?

**Scenario D — Skewed PAR rollout.** Node A advertises PAR while node B lacks the filter. When clients follow metadata and requests are load-balanced, what errors can occur? Design the release gate and rollout.

**Scenario E — JWKS missing the new key.** OP metadata advertises RS256, ID Tokens carry `kid=K2`, and JWKS currently contains only K1. Design the sequence for publishing K2, switching the signer, overlap, and cache validation.

**Scenario F — Token Exchange advertised prematurely.** The server adds the token-exchange grant to `grant_types_supported` without an `AuthenticationProvider` handling it. Why do clients receive `unsupported_grant_type`, and in what order should this be fixed?

**Scenario G — Device flow enabled for one client yet missing from metadata.** The AS lets a kiosk client use the device grant, while metadata omits the device authorization endpoint. Distinguish per-client limits from global capabilities and propose discovery tests.

**Hints:** A needs the OP enabled and tested before advertising; B needs a stable public issuer and trusted proxy; C needs negative verifier tests; D needs uniform capability deployment before advertising; E needs public K2 pre-published before signing with K2 and keeping K1 across overlap; F needs converter/provider/registration/policy first; G needs discovery aligned with actual global capabilities while preserving per-client restrictions.

## 25. Summary

**Consistent metadata** means the discovery document accurately describes the endpoints, grants, client authentication methods, algorithms, and extensions **actually working in the current deployment**. Metadata is a trusted interface for OAuth2 Clients, Resource Servers, and OIDC Relying Parties; it does not implement the protocol itself.

In Spring Authorization Server, reconcile **`AuthorizationServerSettings`, `OAuth2AuthorizationServerConfigurer`, the OIDC configurer, `SecurityFilterChain`, `JWKSource`, `RegisteredClientRepository`, and token/grant providers**. Testing must span from public issuers and metadata URLs to protocol flows, security negatives, JWT/JWKS verification, per-client permissions, and multi-node consistency.

OAuth 2.0 Authorization Server Metadata (RFC 8414) and OpenID Connect Discovery 1.0 are related documents with distinct purposes; never advertise OIDC when only OAuth2 is enabled. For PKCE, PAR, DPoP, mTLS, or Token Exchange, prove **real enforcement**, not merely the presence of a JSON field.

To preserve consistency, treat metadata as a **versioned release contract**: test in CI, smoke-test through the reverse proxy, compare across cluster nodes, enforce issuer/host trust, and maintain rollout/rollback/deprecation plans for every change.

## 26. References

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): well-known discovery, issuer, endpoints, grants, and authentication methods.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration, issuer, UserInfo, and ID Token algorithms.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code Flow, ID Token, and UserInfo.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization/token endpoints, grant types, and client authentication.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): PKCE methods and code verifier.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set/public keys.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection `active` semantics.
- [RFC 9126 — Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126): PAR metadata, `request_uri`, and mandatory PAR.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device authorization.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange grant.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof and sender-constraining.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS token binding.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): authorization response issuer.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and protocol configuration.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): AS metadata, OAuth2/OIDC endpoint configurers.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS URI, and JWT validation.
