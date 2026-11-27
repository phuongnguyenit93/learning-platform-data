# OpenID Provider Configuration and OpenID Connect Discovery

## 1. Why Does an Authorization Server Need OpenID Connect Discovery?

When a Spring Boot application acts as an **OpenID Connect Relying Party (RP)**, it needs to know the Authorization Endpoint, Token Endpoint, UserInfo Endpoint, where to fetch public keys to verify ID Tokens, and which algorithms/response types the OpenID Provider (OP) supports. Configuring every URL and key by hand makes every domain, port, path change, or key rotation prone to configuration drift between the client and the Authorization Server.

**OpenID Connect Discovery 1.0** solves this by providing a standard JSON document, called the **OpenID Provider Configuration** (OP Configuration), containing information about the issuer, endpoints, and OP capabilities. The RP reads this document to configure OIDC login and learn where to fetch public keys.

For example, given issuer:

~~~text
https://auth.example.com
~~~

the standard OpenID Provider Configuration path is:

~~~text
https://auth.example.com/.well-known/openid-configuration
~~~

This lesson belongs to the **Metadata and Discovery** chapter in the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, focusing on designing, configuring, securing, testing, and operating an OAuth 2.0/OIDC Authorization Server with Spring Security and Spring Authorization Server (SAS).

After this lesson, you should be able to:
1. Distinguish **Issuer Discovery**, **OpenID Provider Configuration**, and **JWKS**.
2. Construct the exact `/.well-known/openid-configuration` URL, including for issuers with paths.
3. Read and explain required, recommended, and optional metadata fields.
4. Verify the trust chain `issuer → metadata → JWKS → ID Token`.
5. Distinguish OIDC Discovery from OAuth 2.0 Authorization Server Metadata (RFC 8414).
6. Enable and customize the Provider Configuration Endpoint in SAS, and configure a Spring RP/Resource Server.
7. Write contract tests for consistency, security, and availability of the discovery endpoint.

## 2. Three Distinct Concepts: Issuer, Metadata, JWKS

| Term | Role | Example | Contains private key? |
| --- | --- | --- | --- |
| **Issuer Identifier** | Unique identifier of the OP and expected value in the ID Token's `iss` | `https://auth.example.com` | No |
| **OpenID Provider Configuration** | JSON describing the OP, endpoints, and capabilities | `/.well-known/openid-configuration` | No |
| **JWKS (JSON Web Key Set)** | Set of public keys to verify signatures issued by the OP | `https://auth.example.com/oauth2/jwks` | **Must not** contain private/symmetric key values |
| **ID Token** | JWT carrying end-user authentication information | Received from a valid token response | Not metadata |
| **OAuth Access Token** | Credential for calling protected resources | Issued under an OAuth grant | Not an ID Token |

The Discovery document is **not** a place to store tokens, client secrets, or private signing keys. The `jwks_uri` field in metadata is the address pointing to the JSON Web Key Set, not the public key itself and certainly not the secret signing key.

### 2.1. Flow from Issuer to OIDC Login

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Spring Boot RP
    participant OP as Authorization Server / OP
    participant BR as Browser
    RP->>OP: GET /.well-known/openid-configuration
    OP-->>RP: 200 JSON: issuer, endpoints, jwks_uri, algorithms
    RP->>OP: GET /oauth2/jwks
    OP-->>RP: Public JWK Set
    RP->>BR: Redirect to authorization_endpoint
    BR->>OP: OIDC Authorization Code + PKCE request
    OP-->>BR: Redirect back to RP with code and state
    BR-->>RP: Callback with authorization code
    RP->>OP: POST token_endpoint with code and PKCE verifier
    OP-->>RP: ID Token / Access Token
    RP->>RP: Verify signature, iss, aud, exp, nonce
~~~

In practice, `jwks_uri` may be queried when the decoder needs to verify a token, cached, or refreshed according to key lifecycle; the order in the diagram illustrates data relationships rather than claiming every library downloads the JWKS before starting login.

**Boundary of responsibility:** Discovery tells the RP *where to send requests* and *what the OP advertises it supports*. It does not authenticate users and does not make an invalid ID Token valid.

## 3. OpenID Connect Discovery Consists of Two Processes

### 3.1. Issuer Discovery via WebFinger Is Optional

Sometimes a user provides only an identifier such as an email or personal URL rather than the OP's URL. OpenID Connect Discovery provides a WebFinger mechanism to resolve the issuer from that identifier.

Example:

~~~http
GET /.well-known/webfinger?resource=acct%3Aalice%40example.com&rel=http%3A%2F%2Fopenid.net%2Fspecs%2Fconnect%2F1.0%2Fissuer HTTP/1.1
Host: example.com
~~~

Illustrative response:

~~~json
{
  "subject": "acct:alice@example.com",
  "links": [
    {
      "rel": "http://openid.net/specs/connect/1.0/issuer",
      "href": "https://auth.example.com"
    }
  ]
}
~~~

The `rel` used to find the OpenID Connect issuer is:

~~~text
http://openid.net/specs/connect/1.0/issuer
~~~

The issuer location returned via `href` may have a different host/domain from the initial user identifier. This is security-sensitive data, not an arbitrary URL to trust blindly.

**Important:** WebFinger is an **optional** step. If the RP is already configured with the issuer via a trusted channel, such as `spring.security.oauth2.client.provider.corporate.issuer-uri`, the RP skips WebFinger and goes straight to fetching the OP Configuration. In many enterprise deployments with a fixed IdP, WebFinger is unnecessary.

### 3.2. Fetching the OpenID Provider Configuration Is the Metadata Step

Once the issuer is known, the RP sends an HTTP **GET** to the well-known path according to OIDC rules. A successful response must be HTTP `200 OK` and a JSON object with `Content-Type: application/json`.

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

The RP must verify the TLS server certificate and perform an **exact issuer comparison** between the expected issuer and the `issuer` field in the metadata. If they do not match, it must abort using that metadata.

## 4. Constructing the Exact `/.well-known/openid-configuration` URL

### 4.1. Issuer Without a Path

| Issuer | OIDC Provider Configuration URL |
| --- | --- |
| `https://auth.example.com` | `https://auth.example.com/.well-known/openid-configuration` |
| `https://auth.example.com:9443` | `https://auth.example.com:9443/.well-known/openid-configuration` |

The issuer must use HTTPS in compliant deployments; the URL must not contain a query or fragment. A system might use HTTP loopback for local testing depending on tooling, but internal/production HTTP should never be treated as valid OIDC Discovery per the specification.

### 4.2. Issuer With a Path: Well-Known Is Appended at the End of the Issuer

OIDC Discovery 1.0 specifies: if the issuer contains a path, strip any trailing `/` (if present), then append `/.well-known/openid-configuration`:

| Issuer | OIDC Provider Configuration URL |
| --- | --- |
| `https://auth.example.com/tenant-a` | `https://auth.example.com/tenant-a/.well-known/openid-configuration` |
| `https://auth.example.com/idp/company` | `https://auth.example.com/idp/company/.well-known/openid-configuration` |
| `https://auth.example.com/tenant-a/` | `https://auth.example.com/tenant-a/.well-known/openid-configuration` |

In particular, `https://auth.example.com/tenant-a` is a different issuer from `https://auth.example.com/tenant-b`. In multi-tenant architectures, the RP must map tenant → issuer → metadata → public keys accurately and never mix keys across tenants.

### 4.3. Difference from the OAuth Metadata Path per RFC 8414

A common source of confusion is that RFC 8414 **inserts** the well-known path before the issuer path:

~~~text
Issuer: https://auth.example.com/tenant-a

OIDC Discovery 1.0:
  https://auth.example.com/tenant-a/.well-known/openid-configuration

OAuth 2.0 Authorization Server Metadata (RFC 8414):
  https://auth.example.com/.well-known/oauth-authorization-server/tenant-a
~~~

Both documents may describe the same Authorization Server, but their URL construction rules, required metadata fields, and usage scope are not identical.

Some Spring Security libraries try multiple discovery locations for compatibility. That behavior does not alter the official OIDC definition; do not assume a server is required to expose all of those paths.

### 4.4. Issuer and Endpoints May Not Share the Same Path

Metadata can contain:
- `issuer=https://auth.example.com/tenant-a`;
- `authorization_endpoint=https://auth.example.com/oauth2/authorize`;
- `token_endpoint=https://auth.example.com/oauth2/token`.

What matters is that the endpoints are accurately published by the OP and serve the corresponding issuer. Do not guess endpoints by appending `/authorize` or `/token` to the issuer, nor infer `jwks_uri` from the domain name. The RP must use endpoints from verified metadata.

## 5. Required Fields of OpenID Provider Configuration

According to OpenID Connect Discovery 1.0, the following metadata fields require careful handling:

| Field Name | Spec Requirement Level | Meaning |
| --- | --- | --- |
| `issuer` | **REQUIRED** | OP's issuer URL; must equal `iss` in the ID Token |
| `authorization_endpoint` | **REQUIRED** | Endpoint receiving authorization requests |
| `token_endpoint` | **REQUIRED unless only Implicit Flow is used** | Endpoint exchanging authorization codes for tokens; always needed in modern flows |
| `jwks_uri` | **REQUIRED** | HTTPS URL containing public JWKs to verify signatures |
| `response_types_supported` | **REQUIRED** | `response_type` values supported by the OP |
| `subject_types_supported` | **REQUIRED** | Supported Subject Identifier types, e.g., `public`, `pairwise` |
| `id_token_signing_alg_values_supported` | **REQUIRED** | JWS algorithms for signing ID Tokens; spec requires `RS256` |

Distinguish between **metadata requirement level** and **feature requirement level**. For example:
- The `subject_types_supported` metadata field is required, but an OP does not have to support both `public` and `pairwise`; advertise only what is actually supported.
- The `response_types_supported` metadata field is required, but do not advertise `id_token token` if the runtime does not handle the Implicit Flow. OIDC Discovery 1.0 includes historical requirements for Dynamic OpenID Providers regarding response types; in modern designs, prioritize Authorization Code + PKCE and verify actual conformance profile rules.
- `id_token_signing_alg_values_supported` is not an arbitrary algorithm list clients can pick from for every token type. It describes the **ID Token**, not access token or request object algorithms.
- `jwks_uri` does not imply a spec-mandated fixed URL: the exact endpoint is published by the OP.

### 5.1. Metadata Issuer Is a Security Contract, Not Just a Display Name

If the RP configures its expected issuer as:

~~~text
https://auth.example.com
~~~

but metadata returns:

~~~json
{"issuer": "https://auth.example.com/other-tenant"}
~~~

then the RP must **reject** that metadata; never strip paths, alter hostnames, trim suffixes, or fall back to another issuer. Likewise, trailing slashes, casing, ports, and paths must follow defined URI/string matching rules; do not write an arbitrary "fuzzy" comparison function.

The OIDC spec requires the metadata `issuer` to be **identical** to the issuer queried and to the `iss` claim in the ID Token. This is one of the primary defenses against OP impersonation.

### 5.2. ID Token Claims Cannot Be Inferred from Metadata

Metadata tells the client the issuer and key set, but the ID Token must still be validated independently:
- JWS signature with an appropriate key and allowed algorithm.
- `iss` equals the trusted issuer.
- `aud` contains the matching client ID; `azp` if applicable per profile/rules.
- `exp`/`iat` and time constraints.
- `nonce` if the client sent a nonce in the authorization request.
- `at_hash`, `c_hash`, or other bindings depending on response type/profile.

Merely getting a 200 from `jwks_uri` with a key matching `kid` does not make an ID Token valid. `kid` only locates the key; the signature and claims must be verified by a trusted library.

## 6. Recommended and Optional Metadata Groups

| Field | Meaning | Implementation Notes |
| --- | --- | --- |
| `userinfo_endpoint` | Endpoint returning user claims with an appropriate access token | RECOMMENDED; not every OP exposes one |
| `registration_endpoint` | Dynamic Client Registration Endpoint | RECOMMENDED in Discovery, but SAS disables it by default |
| `scopes_supported` | Scopes advertised by the OP | RECOMMENDED; OP must support `openid` |
| `token_endpoint_auth_methods_supported` | Client authentication methods at the Token Endpoint | If omitted, OIDC defaults to `client_secret_basic` |
| `token_endpoint_auth_signing_alg_values_supported` | Supported JWS algs when clients use JWT assertions | Does not enable `private_key_jwt` just by listing an alg |
| `response_modes_supported` | `query`, `fragment`, `form_post`, etc. per feature | When omitted, OIDC 1.0 defaults to `query` and `fragment` for Dynamic OPs |
| `grant_types_supported` | OAuth grants advertised by the OP | When omitted, historical default is `authorization_code` and `implicit` |
| `acr_values_supported` | Authentication context class levels | Does not mean clients can request any ACR arbitrarily |
| `claims_supported` | Claims the OP may return | Does not guarantee every user has every claim |
| `claim_types_supported` | Claim types `normal`, `aggregated`, `distributed` | Advertise only actually supported types |
| `claims_parameter_supported` | Whether the OP supports the OIDC `claims` request parameter | Defaults to `false` when omitted |
| `request_parameter_supported` | Whether the OP supports JWT Request Objects in `request` | Defaults to `false` when omitted |
| `request_uri_parameter_supported` | Request Object URI per OIDC Discovery | Defaults to `true` when omitted; not proof of PAR support |
| `require_request_uri_registration` | Requires pre-registration of Request Object URIs | Defaults to `false` |
| `end_session_endpoint` | RP-Initiated Logout endpoint when supported by profile | Added by logout spec/extension |
| `pushed_authorization_request_endpoint` | PAR endpoint per RFC 9126 | Distinct from OpenID `request_uri_parameter_supported` |
| `require_pushed_authorization_requests` | Policy requiring PAR per RFC 9126 | Must match actual runtime enforcement |

When reading metadata, clearly distinguish:
1. An **absent** field may have a spec-defined default, or the feature simply is not advertised.
2. A **present** field must reflect actual runtime capability; do not infer it merely from a dependency existing.
3. **Advertised** metadata does not replace per-`RegisteredClient` policy: client A may be allowed a method/grant that client B is not.

**Do not pad the JSON just to "look complete."** Inaccurate JSON causes interoperability failures and may trick RPs into using weak or non-functional grants/methods.

## 7. Example OpenID Provider Configuration Response

For an OP deployed at `https://auth.example.com`, an **illustrative** JSON example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "claims_supported": ["sub", "name", "email", "email_verified"]
}
~~~

This example assumes the runtime actually supports all advertised fields. Do not treat the example's grants/algorithms list as a guarantee that **every SAS version** enables `private_key_jwt`, `refresh_token`, or returns all those claims out of the box. The RP must register a suitable client and the server must enforce authorization.

For modern systems adopting Authorization Code + PKCE only, `response_types_supported=["code"]` reflects actual behavior; some historical conformance requirements for "Dynamic OpenID Providers" in OIDC Discovery 1.0 also include Implicit response types. Choose a secure practical profile and check certification/conformance requirements rather than advertising non-working flows.

### 7.1. What an RP Can Safely Infer

From the sample JSON, the RP knows:
- Which issuer to expect in the ID Token.
- Which URLs accept authorization and token requests.
- Which URL hosts the public keys.
- The RP may request `response_type=code`.
- The OP advertises `RS256` for signing ID Tokens.
- The OP advertises `openid`, `profile`, `email`; though each client/user remains subject to policy.

The RP **cannot** infer:
- That the email claim is always returned.
- That all users are eligible to log in.
- That all clients are allowed `private_key_jwt`.
- That access tokens share the same structure or signing alg as ID Tokens.
- That the OP has dynamic client registration when `registration_endpoint` is absent.
- That adding `scope=admin` to a request will be approved.

### 7.2. Example Invalid Response

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "http://auth.internal/oauth2/authorize",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": [],
  "subject_types_supported": ["public"]
}
~~~

Obvious problems:
- `authorization_endpoint` uses HTTP, violating OIDC Discovery's HTTPS requirement.
- `id_token_signing_alg_values_supported` is missing.
- `response_types_supported` is an empty array; no response types are advertised.
- `token_endpoint` is missing even though the deployment is not Implicit-Flow-only.

When metadata fails validation, the RP must **halt** any workflow depending on it; never silently synthesize URLs or assume unknown algorithms.

## 8. Discovery Is Neither JWKS Nor OAuth Metadata

### 8.1. OpenID Provider Configuration

~~~text
GET https://auth.example.com/.well-known/openid-configuration
→ JSON containing issuer, authorization_endpoint, token_endpoint,
  userinfo_endpoint, jwks_uri, subject_types_supported,
  id_token_signing_alg_values_supported, ...
~~~

Its goal is to help the RP configure OpenID Connect and verify ID Tokens.

### 8.2. JWK Set

~~~text
GET https://auth.example.com/oauth2/jwks
→ JSON with a "keys" array of public JWKs
~~~

Abbreviated JWK Set example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

In a real deployment, `n` and `e` are Base64URL-encoded key material; the placeholders above are not usable keys. Private RSA parameters `d`, `p`, `q`, etc. **must never appear** in a public JWK Set.

The RP must verify `kid`, `kty`, `alg`, `use`, and signature validity per policy. During key rotation, the OP may publish multiple public keys temporarily so clients can still verify tokens issued under the previous key.

### 8.3. OAuth Authorization Server Metadata per RFC 8414

~~~text
GET https://auth.example.com/.well-known/oauth-authorization-server
→ JSON describing the OAuth Authorization Server
~~~

RFC 8414 serves OAuth clients/Resource Servers, including applications that do not use OIDC. The two metadata documents share common fields, but:
- OIDC requires `subject_types_supported` and `id_token_signing_alg_values_supported`.
- OAuth metadata does not require those two fields.
- `userinfo_endpoint` and ID Token claims belong to OIDC/extensions.
- RFC 8414 has its own well-known URL; with an issuer path, URL construction differs as shown earlier.
- Do not patch JSON by renaming an endpoint file; the server must genuinely fulfill the respective contract.

Spring Authorization Server uses **OAuth2AuthorizationServerMetadataEndpointFilter** to serve OAuth metadata per RFC 8414, and **OidcProviderConfigurationEndpointFilter** to serve OP Configuration when OIDC is enabled. These are two distinct filters/endpoints even though they may share `issuer`, authorization endpoint, token endpoint, and JWKS.

### 8.4. Metadata Only Advertises Implemented Capabilities

Pay special attention to extensions:
- `end_session_endpoint`: do not assume logout works just because OIDC is enabled.
- `pushed_authorization_request_endpoint`: a real PAR endpoint must exist.
- `require_pushed_authorization_requests`: do not set to true if the Authorization Endpoint still accepts non-PAR requests.
- `request_uri_parameter_supported`: relates to OIDC/JAR Request Objects, not a toggle for enabling PAR.
- `registration_endpoint`: do not advertise if dynamic registration is not enabled and secured.

Test each advertised endpoint and option in practice.

## 9. Enabling OIDC Provider Configuration in Spring Authorization Server

### 9.1. Default OAuth Metadata Does Not Mean OIDC Is Enabled

In Spring Authorization Server **1.5.x**, default Authorization Server configuration enables the OAuth 2.0 Authorization Server Metadata Endpoint per RFC 8414. However, **OpenID Connect 1.0 is disabled in the default configuration**. To expose OP Configuration, UserInfo, and other OIDC components, you must initialize `OidcConfigurer`.

Key SAS components:

| Component | Role |
| --- | --- |
| `OAuth2AuthorizationServerConfigurer` | Collects the Authorization Server's protocol endpoints and filters |
| `OidcConfigurer` | Enables OIDC protocol configuration |
| `OidcProviderConfigurationEndpointConfigurer` | Extension point to customize OP Configuration |
| `OidcProviderConfigurationEndpointFilter` | Serves OP Configuration JSON for valid GET requests |
| `OidcProviderConfiguration.Builder` | Builds/updates OP metadata claims |
| `OAuth2AuthorizationServerMetadataEndpointFilter` | Serves RFC 8414 OAuth metadata; **not** OP Configuration |
| `AuthorizationServerSettings` | Configures issuer and server-side endpoint paths |
| `JWKSource<SecurityContext>` | Provides public keys for the JWKS endpoint and token signing infrastructure |

In SAS 1.5.x, if no `JWKSource<SecurityContext>` bean is registered, the JWKS endpoint is **not configured** by default. That infrastructure is mandatory when you want RPs to verify asymmetrically signed ID Tokens via JWKS.

### 9.2. Illustrative SecurityFilterChain Configuration

The following example is based on the SAS **1.5.x** API. It focuses on enabling OIDC and opening the metadata extension point; it is not a standalone runnable project:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, as -> as
            .oidc(oidc -> oidc
                .providerConfigurationEndpoint(endpoint -> endpoint
                    .providerConfigurationCustomizer(metadata ->
                        metadata.claim(
                            "service_documentation",
                            "https://docs.example.com/oidc"
                        )
                    )
                )
            )
        )
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .exceptionHandling(exceptions -> exceptions
            .authenticationEntryPoint(
                new LoginUrlAuthenticationEntryPoint("/login")
            )
        );

    return http.build();
}
~~~

`providerConfigurationCustomizer` accepts a `Consumer<OidcProviderConfiguration.Builder>`; the example uses the inherited `claim(String, Object)` method to add `service_documentation`. This does not alter `issuer`, `jwks_uri`, or default security fields. In practice, you also need to configure the user login security chain, `RegisteredClientRepository`, `AuthorizationService`, signing keys, token generator, and corresponding beans.

**Filter order note:** The provider-configuration endpoint is handled by a SAS filter, not a regular application controller. Metadata is a public discovery document; it should not require user login or a client secret to download. Always test an anonymous GET in practice, especially when customizing the security chain, reverse proxy, or authorization rules.

### 9.3. Declaring a Fixed Issuer and Endpoint Settings

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .authorizationEndpoint("/oauth2/authorize")
            .tokenEndpoint("/oauth2/token")
            .jwkSetEndpoint("/oauth2/jwks")
            .oidcUserInfoEndpoint("/userinfo")
            .oidcLogoutEndpoint("/connect/logout")
            .build();
}
~~~

In a single-issuer model, explicitly declaring the issuer keeps `issuer` in metadata and `iss` in tokens consistent across requests. In SAS 1.5.x, the OP Configuration Endpoint is exposed at `/.well-known/openid-configuration` when OIDC is enabled; it is not an endpoint whose path you can arbitrarily change via `AuthorizationServerSettings.oidcProviderConfigurationEndpoint(...)`, as that settings setter is not part of the documented endpoint setters.

`OAuth2AuthorizationServerConfiguration` can auto-create an `AuthorizationServerSettings` bean when using the default import, though applications can declare their own bean to pin the issuer and paths per environment.

### 9.4. Providing JWKSource and JwtDecoder

When using asymmetrically signed ID Tokens, the OP needs signing keys and must publish public keys at `jwks_uri`. SAS provides a helper to build `JwtDecoder` from `JWKSource`:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`JWKSource<SecurityContext>` must be registered separately with the system's key material; **never** load private keys from metadata or include private keys in the JWKS response. SAS documentation notes that a `JwtDecoder` bean is required for the OIDC UserInfo and Client Registration Endpoints. An ID Token signing key must also have proper lifecycle management, rotation, and stable key IDs.

### 9.5. Do Not Advertise Unenabled Endpoints

Under SAS 1.5.x configuration:
- OAuth Authorization Server Metadata and JWK Set are separate endpoints.
- OIDC Provider Configuration appears when `oidc(...)` is enabled.
- UserInfo/Logout are configured via OIDC; exact behavior depends on beans/policy.
- **OIDC Dynamic Client Registration is disabled by default**; do not manually add `registration_endpoint` to metadata just because Spring provides the class/configurer.
- Extensions such as PAR, DPoP, token exchange, and mTLS should only be advertised if the implementation genuinely supports them for that version and policy.

If you use the builder to inject `id_token_signing_alg_values_supported` or `response_types_supported` into metadata, ensure they reflect the ID Token types and flows the server actually produces. Do not add `HS256`, `none`, implicit/hybrid grants, or phantom endpoints just to "satisfy a checklist."

### 9.6. Spring Security 7.x Integrated Configuration

In the Spring Security **7.x** line, Authorization Server infrastructure exposes an API directly on `HttpSecurity`, for example:

~~~java
http.oauth2AuthorizationServer(as -> as
        .oidc(Customizer.withDefaults())
);
~~~

This snippet illustrates only **how to enable OIDC** in the integrated generation. It does not replace security chains, issuer, client registration, JWK source, or login setup. Do not mix Spring Security 7.x DSL directly with classes/packages or `http.with(...)` from SAS 1.x examples; rely on your actual dependencies.

## 10. Spring Boot Application as an OIDC Relying Party

### 10.1. Configuring an RP with `issuer-uri`

A Spring Boot application using OAuth2 Login can configure an OIDC provider by issuer:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://auth.example.com
~~~

`issuer-uri` tells the RP which issuer to query for OpenID Provider Configuration. The RP does not need to separately declare `authorization-uri`, `token-uri`, `jwk-set-uri`, and `user-info-uri` if the provider metadata is valid and supplies all needed endpoints.

`OIDC_CLIENT_SECRET` must come from a proper secret manager/environment variable; this pattern is for confidential web applications. Public clients must never embed static client secrets in SPAs or native apps.

A programmatic equivalent is `ClientRegistrations.fromOidcIssuerLocation(issuer)` in supported Spring Security versions; the `fromIssuerLocation` API may probe multiple discovery endpoints for compatibility. Choose the right option for your purpose and do not rely on endpoint probing order as your sole security contract.

### 10.2. The RP Must Not Skip Validation After Discovery

After a successful login:
- Verify `iss` equals the trusted issuer.
- Verify the ID Token signature with the matching public key from JWKS.
- Verify `aud` contains the registered client ID, and `azp` when required.
- Verify `exp`, `iat`, `nonce`, and relevant claims.
- Verify `state` on the OAuth authorization response to prevent CSRF/login injection.
- Scope `sub` usage to its issuer; `sub` is not a globally unique identifier independent of the issuer.

If metadata were spoofed to point `jwks_uri` to an attacker's key and the RP accepted the wrong issuer, the attacker could forge ID Tokens. That is why the issuer–metadata–JWKS relationship must never be relaxed.

### 10.3. Spring Boot Application as a Resource Server

A Resource Server cares about the **access token**, not using ID Tokens for API authorization. For JWT access tokens, Spring Boot can be configured with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          audiences: [orders-api]
~~~

Depending on the running Spring Boot/Security version's capabilities, `issuer-uri` enables the Resource Server to discover the JWKS URL via provider-configuration/OAuth metadata and enable `iss` validation. `audiences` identifies the API as the intended token recipient. If you configure `jwk-set-uri` directly instead, you must still validate issuer and audience; knowing the signing key does not make a token valid for every API.

Some versions perform discovery when creating the decoder, while others defer it until the first request. Do not assume every Spring Security version always calls metadata eagerly at application startup. Configure readiness/timeouts/caching and test against your actual version and deployment.

## 11. Multi-Tenant Issuers and Reverse Proxies

### 11.1. Never Infer Issuer from an Unverified Host

When Spring Authorization Server sits behind a reverse proxy, incoming requests may carry headers such as `Forwarded` or `X-Forwarded-Host`. If the issuer is derived from a Host header that has not crossed a verified trust boundary, an attacker can make metadata return an attacker-controlled issuer, causing broken URLs or token mix-ups.

For single-tenant systems, prefer:

~~~java
AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
~~~

Additionally:
- Configure the proxy to set/overwrite forwarded headers rather than passing through values sent by internet clients.
- Trust only known proxy IPs/service identities.
- Ensure the external scheme is HTTPS with the exact public domain/port/path.
- Test metadata through the public proxy, not just against localhost on the backend.
- Review HSTS, TLS certificates, load balancer, and redirect behavior.

### 11.2. Multi-Issuer Hosting in SAS 1.5.x

SAS supports hosting multiple issuers on the same host starting in 1.3 via `multipleIssuersAllowed(true)`:

~~~java
@Bean
AuthorizationServerSettings multiTenantSettings() {
    return AuthorizationServerSettings.builder()
            .multipleIssuersAllowed(true)
            .build();
}
~~~

In multi-issuer mode, **do not simultaneously pin a single issuer** with `issuer(...)`; builder documentation states that setting a fixed issuer restricts the deployment to single-tenant mode. The application still has to design tenant routing, registries, and policy mapping; enabling the flag does not create tenant isolation on its own.

Example:

| Tenant | Issuer | OIDC Discovery URL |
| --- | --- | --- |
| Alpha | `https://auth.example.com/t/alpha` | `https://auth.example.com/t/alpha/.well-known/openid-configuration` |
| Beta | `https://auth.example.com/t/beta` | `https://auth.example.com/t/beta/.well-known/openid-configuration` |

Per-tenant safety contract:
- `issuer` in metadata matches the tenant's issuer exactly.
- ID Token `iss` identifies only that tenant.
- Client registrations, subject identifiers, and authorizations never cross tenants.
- `jwks_uri` serves keys within the proper trust boundary; if keys are shared, issuer and tenant mapping must still be strictly enforced.
- An RP must never accept a Beta tenant ID Token under Alpha's configuration simply because they share a signing key or host.

### 11.3. CORS and the Discovery Endpoint

OIDC Discovery recommends CORS or equivalent support on the Provider Configuration endpoint for browser-based clients when appropriate. This does not mean the Authorization Endpoint needs CORS; the Authorization Endpoint is normally accessed via browser redirects and the specification **does not recommend CORS** on it.

Do not open `Access-Control-Allow-Origin: *` across all token/UserInfo/client registration endpoints just to "fix discovery." Configure CORS per endpoint, client origin, and allowed method; public metadata does not mean every API behind it is public.

## 12. Security When Consuming OpenID Provider Configuration

### 12.1. The Discovery Document Is Network Data, Not Unconditional Trust

An RP must not take `issuer`, `authorization_endpoint`, or `jwks_uri` URLs from an untrusted page and immediately use them. Determine the issuer through configuration or a controlled provider registration workflow. If dynamic issuer discovery from user input is supported, restrict host/scheme/port, block local-network destinations, and control redirects.

Typical risks:

| Risk | Scenario | Mitigation |
| --- | --- | --- |
| **Issuer impersonation** | Attacker's metadata JSON claims another OP's issuer | TLS validation; metadata issuer must match expected issuer exactly |
| **SSRF** | RP fetches a discovery/JWKS URL pointing to localhost or cloud metadata IP | Allowlist/egress policy; block private/link-local IPs, DNS rebinding, and unsafe redirects |
| **Key substitution** | Metadata points `jwks_uri` to an attacker's key | Accept metadata only after issuer/TLS validation and trust policy checks |
| **Algorithm confusion** | Token carries an `alg` outside the allowlist yet RP verifies it | Pin allowed algorithms; never trust token `alg` as policy |
| **Cross-tenant mix-up** | RP uses issuer B's metadata/key to verify issuer A's token | Key caches and validation by full issuer, not just hostname |
| **Stale metadata** | OP rotates endpoints or signing keys while RP holds stale cache | Cache with appropriate TTL/refresh; support key rotation |
| **Oversharing** | Metadata exposes internal hosts, admin endpoints, or unprotected registration | Publish only public endpoints and genuinely supported features |
| **Downgrade/fallback** | Discovery fails and RP skips `iss` or falls back to HTTP | Fail closed; never weaken checks "just to make login work" |

Never disable TLS hostname verification in production. A "trust all certificates" option renders every downstream issuer check meaningless.

### 12.2. Recommended Metadata Verification Flow

~~~mermaid
flowchart TD
    A[Issuer from trusted configuration] --> B[Construct OIDC well-known URL]
    B --> C[HTTPS GET and verify TLS]
    C --> D{HTTP 200, valid JSON?}
    D -->|No| X[Reject metadata]
    D -->|Yes| E{metadata.issuer == expected issuer?}
    E -->|No| X
    E -->|Yes| F[Check required metadata and URL policy]
    F --> G[Initialize client endpoints]
    G --> H[Fetch JWKS over trusted connection]
    H --> I[Receive and verify ID Token]
    I --> J{iss, aud, exp, nonce, and signature valid?}
    J -->|No| Y[Reject login]
    J -->|Yes| K[Create session per RP policy]
~~~

This diagram represents a **security contract**. Spring APIs calling Discovery/JWKS may use caching or lazy initialization, but none of these checks may be omitted.

### 12.3. Caching and Key Rotation

An OP may rotate signing keys routinely or due to a security incident. An RP should not fetch JWKS on every single HTTP request unnecessarily, yet it must not cache indefinitely either.

An operational approach:
- Configure metadata TTL/HTTP caching according to library capabilities.
- Use a JWKS cache with refresh and safe handling for new key IDs.
- Keep old public keys in JWKS long enough for unexpired ID Tokens during routine key rotation.
- Never continue trusting a compromised key just for compatibility.
- Never fetch keys from `jku`/`x5u` headers declared by an arbitrary JWT unless explicitly permitted by profile and trust policy.
- Monitor discovery/JWKS 404/5xx errors, issuer mismatches, unknown `kid`s, and ID Token signature failures.

Public JWKS contains no private keys, yet losing its availability still disrupts logins and token verification.

## 13. Discovery Contract Test Matrix

### 13.1. Endpoint and Metadata Tests

| Test | Action | Expected |
| --- | --- | --- |
| OP config public | Anonymous GET `/.well-known/openid-configuration` | HTTP 200, `application/json` |
| Required metadata | Parse response JSON | All required fields per deployment profile present |
| Issuer exact match | Compare config `issuer` with expected issuer | Exact match |
| ID Token issuer | Log in to obtain ID Token | `iss` claim equals metadata `issuer` |
| Authorization URL | Compare metadata URL with active endpoint | Matches, HTTPS, and reachable |
| Token URL | Send valid token request | Endpoint works for allowed grant |
| JWKS URL | GET `jwks_uri` | 200 JSON with `keys` array, no private keys |
| Key validation | Use ID Token signed by published key | Signature and claims verify |
| Unsupported response type | Request type absent from metadata | Server rejects |
| UserInfo metadata | If `userinfo_endpoint` advertised | Endpoint exists and enforces appropriate token |
| Dynamic Registration metadata | If `registration_endpoint` absent | Do not assume arbitrary client registration is open |
| Extension metadata | PAR/logout/other advertised endpoints | Enforces exact feature/policy |
| Separate OAuth metadata | GET `/.well-known/oauth-authorization-server` | Matches RFC 8414 contract |
| Anonymous access | Send no cookie/session/client secret | Discovery remains accessible |
| HTTP query handling | GET with unrelated query parameters | Does not alter issuer or route to another tenant |
| Empty arrays | Empty array-typed fields | Omitted from metadata per OIDC Discovery response rules |

### 13.2. Security Tests

| Test | Input or Environment | Expected |
| --- | --- | --- |
| Issuer mismatch | Metadata `issuer` belongs to attacker/another tenant | RP rejects |
| ID Token iss mismatch | ID Token from issuer B, metadata from issuer A | RP rejects |
| Wrong audience | ID Token `aud` lacks client ID | RP rejects |
| Unknown signing kid | `kid` matches no valid key | Token rejected |
| Alg downgrade | Header `alg=none` or alg outside allowlist | Rejected |
| Bad TLS certificate | HTTPS endpoint has wrong-domain/expired certificate | Metadata rejected |
| Insecure scheme | Metadata endpoint returns HTTP URL | Rejected per HTTPS policy |
| SSRF via WebFinger | `href` points to 127.0.0.1 or private IP | Dangerous address not fetched |
| SSRF via JWKS | `jwks_uri` points to link-local/cloud metadata | Not fetched |
| Host header injection | Request to OP with spoofed Host | Public issuer unchanged |
| Forwarded host injection | Reverse proxy receives forged `X-Forwarded-Host` | Proxy sanitizes; issuer not poisoned |
| Cross-tenant configuration | RP targets tenant A but receives B | Does not log into wrong tenant |
| JWKS rotation | Server adds new key while retaining old key per policy | RP verifies both old and new tokens appropriately |
| Compromised key | Emergency key revocation | RP stops trusting key per security policy |
| Discovery downtime | OP returns 503 | RP fails closed with bounded retry/backoff |
| Metadata oversize | Server returns oversized JSON/excessive unknown URLs | RP enforces size limit, timeout, and schema |
| Claim mismatch | `claims_supported` lists email, but user lacks it | Client does not treat email as mandatory claim |
| Key material leak | Inspect JWKS response | No private/symmetric keys present |

### 13.3. Testing with MockMvc

In a project with SAS configured and `MockMvc`, illustrative test:

~~~java
@Test
void oidcDiscoveryPublishesExpectedIssuer() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                    .value("https://auth.example.com"))
            .andExpect(jsonPath("$.authorization_endpoint").exists())
            .andExpect(jsonPath("$.token_endpoint").exists())
            .andExpect(jsonPath("$.jwks_uri").exists())
            .andExpect(jsonPath("$.subject_types_supported").isArray())
            .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
                    .isArray());
}
~~~

This snippet focuses on assertions; in a real project it requires `@SpringBootTest`/`@AutoConfigureMockMvc`, JUnit/MockMvc imports, and full SAS beans. Also test `jwks_uri` through a real HTTPS/proxy deployment, because MockMvc will not catch external host or edge TLS misconfigurations.

### 13.4. Testing Issuers with Paths

For issuer `https://auth.example.com/tenant-a`:

~~~text
Expected OIDC:
https://auth.example.com/tenant-a/.well-known/openid-configuration

Expected metadata.issuer:
https://auth.example.com/tenant-a

Expected ID Token iss:
https://auth.example.com/tenant-a
~~~

Also verify:
- `https://auth.example.com/tenant-b` is rejected.
- JWKS or authorization context from another tenant is never mixed in.
- Tenant A's metadata is never cached and served to tenant B.
- When a reverse proxy rewrites paths, browser requests still use the exact public HTTPS issuer.

## 14. Common Mistakes and Fixes

**Mistake 1 — Confusing OP Configuration with OAuth Metadata.** Calling only `/.well-known/oauth-authorization-server` and expecting `subject_types_supported` or `id_token_signing_alg_values_supported`. These are different specs; enable OIDC to get OP Configuration.

**Mistake 2 — OIDC endpoint returns 404 even though the OAuth2 token endpoint works.** In SAS 1.5.x, OIDC is disabled by default. Initialize `OidcConfigurer` and verify `SecurityFilterChain` matchers/issuer.

**Mistake 3 — Internal host issuer behind a reverse proxy.** Metadata advertises `http://localhost:9000` or `http://service:8080`, while the RP expects `https://auth.example.com`. Pin the public issuer and configure trusted proxy headers properly.

**Mistake 4 — Metadata issuer differs from ID Token `iss`.** The RP must reject it; fix issuer resolution on the AS rather than disabling validation on the RP.

**Mistake 5 — Building URLs by manual concatenation.** Guessing `/oauth2/token` or `/oauth2/jwks` from the issuer instead of reading metadata. This breaks when the OP changes endpoints or uses multi-tenancy.

**Mistake 6 — Requiring client login just to GET metadata.** The discovery endpoint must be publicly accessible over TLS; check filters and gateway rules.

**Mistake 7 — Unintentionally exposing dynamic client registration.** `registration_endpoint` is a specialized capability; never advertise or open it if the system does not use this feature.

**Mistake 8 — Advertising unsupported response types/algorithms.** The RP sends a `response_type` the server rejects, or an ID Token is signed with an algorithm the RP does not recognize. Metadata must reflect runtime reality.

**Mistake 9 — Equating ID Token and access token.** An ID Token proves authentication to the RP; APIs must use access tokens with appropriate audience/scopes. `id_token_signing_alg_values_supported` does not define access token policy.

**Mistake 10 — Treating `request_uri_parameter_supported` as PAR.** Check `pushed_authorization_request_endpoint` separately per RFC 9126.

**Mistake 11 — SSRF via WebFinger or JWKS.** Never fetch arbitrary endpoints supplied by a user/attacker; enforce URL/egress allowlists and issuer validation.

**Mistake 12 — Disabling TLS checks in test environments.** Fix certificates/CA/trust stores properly; never carry an "ignore SSL verification" flag into production.

## 15. Case Study Exercise

An organization deploys a Spring Boot Authorization Server behind NGINX:

~~~text
Public issuer:
https://login.example.com/identity

Internal service:
http://authorization-server:9000

OIDC RP:
https://portal.example.com

Multi-tenant:
alpha and beta use separate issuer paths
~~~

The backend team encounters the following issues:
- `GET /identity/.well-known/openid-configuration` returns JSON with `issuer=http://authorization-server:9000`.
- The RP sets `issuer-uri=https://login.example.com/identity`, but rejects the metadata.
- `jwks_uri` advertises `http://authorization-server:9000/oauth2/jwks`.
- A developer suggests disabling issuer and SSL checks "just to get login working first."
- `registration_endpoint` is advertised even though dynamic registration is not enabled.
- Tenant alpha receives an ID Token with tenant beta's `iss`.

Analyze:

1. Why must the RP reject the current metadata? Which `issuer` rules are being violated?
2. What is the correct OIDC well-known URL for an issuer with a path? How does it differ from the RFC 8414 path?
3. How should the external issuer and trusted proxy headers be fixed?
4. Which URL should `jwks_uri` advertise, and why should the internal host not be used?
5. Why must TLS and issuer validation never be bypassed?
6. How should the unenabled `registration_endpoint` be handled?
7. What must be done to isolate client registrations and ID Tokens by tenant?
8. Write at least six tests covering anonymous discovery, issuer matching, JWKS availability, key rotation, tenant isolation, and endpoint capabilities.

**Hint:** Publish a consistent public HTTPS issuer from metadata through ID Tokens, route well-known according to the OIDC path rule, use public endpoints for JWKS, and never skip TLS/issuer checks. For multi-tenancy, enable controlled issuer-path support in SAS and enforce tenant isolation at every layer; never rely on a shared host or shared signing key to mix identities.

## 16. Production Deployment Checklist

1. **Issuer:** lock in a stable HTTPS issuer without query/fragment; never derive it from an untrusted `Host`.
2. **Discovery path:** serve `/.well-known/openid-configuration` accurately per issuer, including path/multi-tenant issuers.
3. **OIDC enablement:** enable `OidcConfigurer`; do not confuse it with SAS's default OAuth metadata.
4. **Required claims:** include issuer, authorization endpoint, token endpoint when needed, JWKS, response types, subject types, and ID Token signing algorithms.
5. **Capabilities:** advertise only active scopes, grants, authentication methods, extensions, and endpoints.
6. **JWKS:** public-only JWK Set, with `kid`/rotation and a sound cache/reload strategy.
7. **Security:** RP/Resource Server verifies TLS, issuer, key, signature, audience, expiry, nonce, and state per profile.
8. **Network:** mitigate SSRF when using WebFinger or dynamic issuers; constrain outbound redirects/DNS.
9. **Proxy:** ensure metadata always uses external HTTPS host/scheme/path; trust proxy headers only from identified proxies.
10. **Multi-tenant:** isolate issuers, client registrations, caches, tokens, and keys per tenant.
11. **Availability:** monitor metadata/JWKS endpoints with proper timeouts, cache policies, and incident plans.
12. **Spring version:** check whether you are on SAS 1.x or Spring Security 7.x before using DSLs/configurers.
13. **Contract tests:** run MockMvc and end-to-end tests through ingress, including negative tests for mismatches and 404 endpoints.
14. **Change control:** changing an issuer/domain is a breaking change requiring a migration plan for RPs, token validators, and sessions.

## 17. Official Specifications and Spring References

- [OpenID Connect Discovery 1.0 — Final, incorporating errata set 2](https://openid.net/specs/openid-connect-discovery-1_0.html): WebFinger Issuer Discovery, required metadata, well-known path, and issuer validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC authentication flows, ID Token, nonce, and UserInfo.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): OAuth metadata and well-known path differences from OIDC.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): public key structure.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): JWT signing/verification algorithms.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): claims and checking `iss`, `aud`, `exp`.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): PAR metadata and `request_uri`.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): enabling OIDC, default endpoints, `JWKSource`, `AuthorizationServerSettings`.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcProviderConfigurationEndpointConfigurer` and `providerConfigurationCustomizer`.
- [Spring Authorization Server — OidcProviderConfiguration.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): required fields and builder API.
- [Spring Security 7.x — Authorization Server Configuration Model](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html): integrated generation DSL.
- [Spring Boot — OAuth2/OIDC Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): RP with `issuer-uri`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT issuer/JWKS discovery and validation.

**Remember:** OpenID Provider Configuration is **public JSON metadata** that helps an RP discover an OP's endpoints, OIDC capabilities, and public key location. OpenID Connect Discovery may start with WebFinger to find the issuer, though that step is optional when the RP already knows the issuer. Metadata is fetched over HTTPS at `<issuer>/.well-known/openid-configuration`, and its `issuer` must match **exactly** both the expected issuer and the ID Token's `iss` claim. In Spring Authorization Server, OAuth metadata is enabled by default, whereas **OIDC Provider Configuration** requires explicitly enabling OIDC and advertising only the endpoints, signing keys, and features actually supported.
