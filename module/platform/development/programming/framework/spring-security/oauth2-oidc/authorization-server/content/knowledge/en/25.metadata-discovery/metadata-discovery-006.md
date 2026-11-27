# Customizing Authorization Server and OpenID Provider Metadata

## 1. Objectives and Real-World Scenario

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we design, configure, secure, test, and operate an **OAuth 2.0/OpenID Connect Authorization Server** using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**. When an OAuth client or OpenID Connect Relying Party connects to the server, it should not have to guess the Token Endpoint path, JWK Set Endpoint, client authentication method, or ID Token signing algorithm.

**Metadata and Discovery** solves this problem: the Authorization Server publishes a machine-readable JSON document containing the endpoints and protocol capabilities it actually supports. The client only needs to know the trusted issuer and follow the corresponding discovery rules to retrieve configuration.

Running example: an enterprise operates an Authorization Server at <code>https://auth.example.com</code>, providing OAuth 2.0 for APIs and OpenID Connect for web applications. Legal requires publishing privacy policy and terms of service URLs; developer relations wants to publish documentation URLs; the system runs behind a reverse proxy so the public issuer/endpoints must use HTTPS and the external hostname rather than pointing to <code>localhost:9000</code>. We will configure:

- **OAuth 2.0 Authorization Server Metadata** per **RFC 8414**.
- **OpenID Provider Configuration** per **OpenID Connect Discovery 1.0**.
- Java DSL extension points in **Spring Authorization Server 1.5.x** to enrich metadata without rewriting either endpoint.
- Tests proving the advertised information matches running features.

After this lesson, you will be able to:

1. Distinguish the two metadata documents, where they are fetched, and their required fields.
2. Explain the roles of <code>issuer</code>, <code>authorization_endpoint</code>, <code>token_endpoint</code>, <code>jwks_uri</code>, advertised auth methods, and algorithms.
3. Use <code>AuthorizationServerSettings</code> to declare issuer/endpoints instead of manually patching JSON strings.
4. Use <code>authorizationServerMetadataCustomizer(...)</code> to customize OAuth metadata.
5. Use <code>providerConfigurationCustomizer(...)</code> to customize OpenID Provider metadata.
6. Add useful optional attributes without advertising unimplemented features.
7. Handle public URLs behind reverse proxies, multi-tenant/multi-issuer setups, JWKS, TLS, caching, and key rotation.
8. Write discovery contract tests verifying consistency between metadata and runtime behavior.

**Version scope:** Examples use Spring Authorization Server **1.5.x**, Spring Security **6.x**, and the Spring Boot Servlet stack. Spring Security versions that integrate Authorization Server in a different package may use a different DSL. When upgrading versions, verify Javadoc and contract tests before going to production.

## 2. Two Metadata Standards That Should Not Be Conflated

### 2.1. OAuth 2.0 Authorization Server Metadata — RFC 8414

RFC 8414 defines metadata for an OAuth 2.0 Authorization Server, typically fetched at:

~~~http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Illustrative JSON for a specific deployment:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"],
  "service_documentation": "https://auth.example.com/docs/oauth"
}
~~~

This is **not a guaranteed default response** across every Spring Authorization Server version. Values in this example are valid only if the server has configured and genuinely supports those grants, authentication methods, PKCE, and endpoints.

The RFC 8414 document tells OAuth clients connection details: authorization endpoint, token endpoint, grant/response types, client authentication, JWK Set, and extension capabilities.

### 2.2. OpenID Provider Configuration — OpenID Connect Discovery

OpenID Connect adds an **authentication layer** on top of OAuth 2.0. When OIDC is enabled, the OpenID Provider (OP) publishes a separate discovery document, typically at:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Example:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile"],
  "claims_supported": ["sub", "name"],
  "op_policy_uri": "https://auth.example.com/legal/privacy",
  "op_tos_uri": "https://auth.example.com/legal/terms"
}
~~~

<code>subject_types_supported</code> and <code>id_token_signing_alg_values_supported</code> relate directly to the **ID Token** and End-User identity. <code>userinfo_endpoint</code>, <code>scopes_supported</code>, and <code>claims_supported</code> must reflect real OIDC behavior—never publish them solely because an SDK expects to see them.

### 2.3. Quick Comparison

| Aspect | OAuth Authorization Server Metadata | OpenID Provider Configuration |
| --- | --- | --- |
| Primary specification | RFC 8414 | OpenID Connect Discovery 1.0 |
| Typical well-known for root issuer | <code>/.well-known/oauth-authorization-server</code> | <code>/.well-known/openid-configuration</code> |
| Primary consumers | OAuth clients, OAuth configuration tools | OIDC Relying Parties, login-enabled apps |
| OAuth-related fields | Issuer, authorization/token/JWKS endpoints, grants, client auth | Many shared OAuth fields |
| OIDC-specific fields | Does not require ID Token/subject types | Subject types, ID Token signing algorithms, UserInfo, OIDC claims |
| Spring configuration | <code>authorizationServerMetadataEndpoint(...)</code> | <code>oidc(...).providerConfigurationEndpoint(...)</code> |
| Default state in Spring Authorization Server 1.5.x | OAuth metadata endpoint is included in default config | **OIDC must be explicitly enabled** |

Do not use OAuth metadata to infer that the system supports OIDC. A server issuing only service-to-service access tokens can be a valid OAuth Authorization Server without being an OpenID Provider.

## 3. How Does Discovery Work?

### 3.1. Basic Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth/OIDC Client
    participant M as Metadata Endpoint
    participant J as JWKS Endpoint
    participant A as Authorization/Token Endpoint
    C->>C: Know trusted issuer from configuration
    C->>M: GET /.well-known/openid-configuration or OAuth metadata
    M-->>C: JSON issuer + endpoint URLs + capabilities
    C->>C: Verify exact issuer match and validate metadata
    C->>J: GET jwks_uri (if JWT verification needed)
    J-->>C: Public JWK Set
    C->>A: Execute appropriate grant or OIDC flow
    A-->>C: Authorization response / token response
    C->>C: Validate token issuer, audience, signature, expiry
~~~

The client must know the **trusted issuer in advance**, e.g., from administrative configuration. Never accept an issuer provided by an unverified token, untrusted redirect, or arbitrary user input.

### 3.2. Metadata Is a Descriptive Contract, Not an Enforcement Mechanism

For example, adding the string <code>private_key_jwt</code> to <code>token_endpoint_auth_methods_supported</code> **does not implement** JWT client authentication. Writing <code>authorization_code</code> into <code>grant_types_supported</code> does not generate an Authorization Endpoint or consent flow.

Conversely, if the server already supports a feature but metadata fails to advertise it accurately, client libraries may fail to configure themselves or choose the wrong flow.

**Rule:** <code>capabilities_advertised ⊆ capabilities_implemented_and_enabled</code>. Everything else is enforced by security configuration, client registration, grant providers, and token generators.

### 3.3. Per-Client Configuration and Server-Wide Metadata Are Two Different Layers

Metadata advertises a **shared set of capabilities** of the Authorization Server. An individual <code>RegisteredClient</code> must still be explicitly permitted to use the corresponding grant, redirect URI, scope, and authentication method.

Example:

- Server advertises support for <code>authorization_code</code> and <code>client_credentials</code>.
- <code>orders-web</code> is registered only for <code>authorization_code</code> + PKCE.
- <code>orders-worker</code> is registered only for <code>client_credentials</code>.

That does not mean <code>orders-web</code> can use Client Credentials merely because metadata lists that grant. The runtime must still enforce `RegisteredClient`.

## 4. Key Fields and Publication Conditions

### 4.1. OAuth Metadata Field Table

| Field | Meaning | What to Check |
| --- | --- | --- |
| <code>issuer</code> | HTTPS identifier of the Authorization Server. | Matches the issuer used to sign/issue tokens and the value trusted by clients. |
| <code>authorization_endpoint</code> | URL for sending authorization requests. | Endpoint exists, works, and uses a public HTTPS URL. |
| <code>token_endpoint</code> | URL for exchanging grants for tokens. | Exact path and client auth policy. |
| <code>jwks_uri</code> | URL publishing public signing keys. | Endpoint exists, public keys valid, no private JWKs leaked. |
| <code>response_types_supported</code> | Response types supported by the Authorization Server. | Do not advertise implicit/hybrid if unimplemented. |
| <code>grant_types_supported</code> | Supported OAuth grant types. | Matches enabled converters/providers. |
| <code>token_endpoint_auth_methods_supported</code> | How clients authenticate at the Token Endpoint. | Matches actual providers/client auth methods. |
| <code>code_challenge_methods_supported</code> | PKCE code challenge methods. | Prefer <code>S256</code>; do not advertise disallowed methods. |
| <code>scopes_supported</code> | Scopes advertised as supported by the server. | Not the set of scopes granted to a given client. |
| <code>revocation_endpoint</code> | URL for revoking tokens. | Endpoint and authentication policy are sound. |
| <code>introspection_endpoint</code> | URL for querying token active state. | Protects caller authentication for introspection. |
| <code>service_documentation</code> | Service documentation URL (optional per RFC 8414). | Valid HTTPS URL and safe for public access. |

Optional fields need not appear in every deployment. Metadata can also describe PAR, Device Authorization, token exchange, mTLS, DPoP, or other mechanisms depending on libraries and versions. Each feature should be advertised only after matching integration tests are in place.

### 4.2. Required Fields per Spring Authorization Server 1.5.8 Builder

In the Spring Authorization Server 1.5.8 API, <code>OAuth2AuthorizationServerMetadata.Builder</code> validates the presence of:

- <code>issuer</code>
- <code>authorization_endpoint</code>
- <code>token_endpoint</code>
- <code>response_types_supported</code>

These are **framework builder validation requirements**; when reading the RFC, also account for protocol semantics and profile-specific exceptions/conditions. Never delete required fields in a customizer and emit arbitrary JSON.

### 4.3. Required Fields in OpenID Provider Configuration

<code>OidcProviderConfiguration.Builder</code> in Spring Authorization Server 1.5.8 requires:

- <code>issuer</code>
- <code>authorization_endpoint</code>
- <code>token_endpoint</code>
- <code>jwks_uri</code>
- <code>response_types_supported</code>
- <code>subject_types_supported</code>
- <code>id_token_signing_alg_values_supported</code>

This is why you cannot simply enable OIDC without an appropriate signing key/JWK Set and assume every OIDC client will work.

### 4.4. Security-Sensitive Semantic Fields

Some metadata changes have consequences beyond "displaying documentation":

1. Changing <code>issuer</code> can cause Resource Servers/OIDC Clients to reject tokens due to <code>iss</code> mismatch.
2. Changing <code>jwks_uri</code> can cause clients to fetch keys from a different source; if unauthenticated/unmanaged, it introduces key-substitution risk.
3. Advertising an unused algorithm in <code>id_token_signing_alg_values_supported</code> can cause verification errors or policy weakening.
4. Advertising weak or unenabled grants in <code>grant_types_supported</code> can cause clients to pick broken flows.
5. Advertising <code>userinfo_endpoint</code> without an active UserInfo endpoint breaks OIDC login/profile flows.

## 5. `AuthorizationServerSettings` Is the Canonical Configuration Source

### 5.1. Declaring an Explicit Public Issuer

Spring Authorization Server provides the <code>AuthorizationServerSettings</code> bean to configure the issuer and endpoint paths.

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .tokenEndpoint("/oauth2/token")
        .jwkSetEndpoint("/oauth2/jwks")
        .build();
}
~~~

Paths are declared explicitly here for illustration; in many configurations these are already the defaults. The <code>issuer</code> value must be the stable public URL trusted by clients and Resource Servers. Never use an internal URL like <code>http://auth-service:9000</code> if external parties only know <code>https://auth.example.com</code>.

### 5.2. Difference Between Endpoint Configuration and Metadata Customizers

| Goal | Primary Configuration Place |
| --- | --- |
| Change public issuer | <code>AuthorizationServerSettings.issuer(...)</code>. |
| Change actual Token Endpoint path | <code>AuthorizationServerSettings.tokenEndpoint(...)</code>. |
| Change actual JWK Set Endpoint path | <code>AuthorizationServerSettings.jwkSetEndpoint(...)</code>. |
| Enable OIDC | <code>OAuth2AuthorizationServerConfigurer.oidc(...)</code>. |
| Add OP policy URLs to JSON | <code>providerConfigurationCustomizer(...)</code>. |
| Add documentation URL to OAuth metadata | <code>authorizationServerMetadataCustomizer(...)</code>. |
| Add a real grant | Converter/provider, `RegisteredClient` policy, and grant components; metadata merely reflects the result. |

**Do not override <code>token_endpoint</code> via a metadata customizer to "change the route."** That only advertises a new URL in JSON; if the real filter still listens at the old path, clients hit 404 or the wrong endpoint.

### 5.3. Why Not Infer the Issuer from Arbitrary Requests?

Behind a load balancer/reverse proxy, requests arriving at the backend carry `Host` or `Forwarded` headers. If the application blindly trusts caller-supplied headers to build <code>issuer</code>, attackers can cause **issuer confusion** or inject unwanted hostnames into metadata.

Prefer static issuer configuration for an Authorization Server with a fixed public hostname. If you genuinely support multi-tenant/multi-issuer setups, resolve the issuer per tenant from a trusted registry—never turn an arbitrary `Host` header into a valid issuer.

## 6. Customizing OAuth Authorization Server Metadata

### 6.1. Official API in Spring Authorization Server 1.5.x

<code>OAuth2AuthorizationServerMetadataEndpointConfigurer</code> provides:

~~~java
authorizationServerMetadataEndpoint(metadata -> metadata
    .authorizationServerMetadataCustomizer(
        authorizationServerMetadataBuilder -> {
            // Customize claims in OAuth2AuthorizationServerMetadata.
        }));
~~~

The callback receives an <code>OAuth2AuthorizationServerMetadata.Builder</code>. The builder offers APIs for standard metadata plus <code>claim(...)</code>/<code>claims(...)</code> for custom entries. The framework still constructs default metadata, letting you enrich fields without writing a separate HTTP JSON controller.

### 6.2. Example: Adding `service_documentation`

~~~java
Consumer<OAuth2AuthorizationServerMetadata.Builder> oauthMetadataCustomizer =
    builder -> builder.claim(
        "service_documentation",
        "https://auth.example.com/docs/oauth");
~~~

This is a low-risk customization: <code>service_documentation</code> is optional metadata per RFC 8414. The URL must exist and point to appropriate public documentation. If adding organization-specific custom metadata, choose non-colliding names and document semantics for consumers.

### 6.3. Adding or Modifying a Capability Only When Implemented

The builder has APIs for scopes, grants, client authentication methods, and other attributes. Illustrative example:

~~~java
builder.scope("orders.read");
builder.claim(
    "service_documentation",
    "https://auth.example.com/docs/oauth");
~~~

Only advertise <code>orders.read</code> if the system actually issues and accepts that scope per policy. Calling <code>scope(...)</code> does not register the scope on any `RegisteredClient`, create a Resource Server, or grant any permissions.

If you adjust a supported list, inspect **existing defaults**, the exact builder method, and the final JSON output. Never blindly overwrite all of <code>grant_types_supported</code> with a hardcoded list, as doing so easily drops default grants or advertises inaccurate values.

## 7. Customizing OpenID Provider Configuration

### 7.1. Official API

When OIDC is enabled, <code>OidcProviderConfigurationEndpointConfigurer</code> provides:

~~~java
oidc(oidc -> oidc
    .providerConfigurationEndpoint(provider -> provider
        .providerConfigurationCustomizer(
            providerConfigurationBuilder -> {
                // Customize OpenID Provider Configuration claims.
            })));
~~~

The callback receives an <code>OidcProviderConfiguration.Builder</code>. Similar to the OAuth metadata builder, it offers methods for endpoints, signing algorithms, subject types, and <code>claim(...)</code> for optional fields.

### 7.2. Example: Policy and Terms of Service

~~~java
Consumer<OidcProviderConfiguration.Builder> oidcMetadataCustomizer =
    builder -> {
        builder.claim(
            "op_policy_uri",
            "https://auth.example.com/legal/privacy");
        builder.claim(
            "op_tos_uri",
            "https://auth.example.com/legal/terms");
    };
~~~

These two fields belong to OpenID Provider Configuration and serve legal/documentation purposes. They do not create a consent screen, make clients automatically accept terms, or provide UserInfo on their own.

### 7.3. Conditionally Advertising `claims_supported`

<code>claims_supported</code> describes the claims the OP **can provide** in appropriate OIDC contexts. For instance, if the system genuinely supports <code>sub</code>, <code>name</code>, and <code>email</code> per scope, consent, and policy:

~~~java
builder.claim(
    "claims_supported",
    List.of("sub", "name", "email"));
~~~

Do not add <code>email_verified</code>, <code>phone_number</code>, <code>address</code>, <code>acr</code>, or <code>amr</code> just to appease a client if the server cannot produce them with trustworthy semantics. Listing a claim in metadata does not guarantee it appears in every ID Token or UserInfo response.

### 7.4. Subject Type and ID Token Signing Algorithms

OIDC requires metadata for:

- <code>subject_types_supported</code>, typically including <code>public</code>; advertise <code>pairwise</code> only if the OP actually implements pairwise subject identifiers.
- <code>id_token_signing_alg_values_supported</code>, e.g., <code>RS256</code> when ID Tokens are actually signed with RS256.

Spring Authorization Server's builder provides methods such as <code>subjectType(...)</code>, <code>subjectTypes(...)</code>, <code>idTokenSigningAlgorithm(...)</code>, and <code>idTokenSigningAlgorithms(...)</code>. The plural methods mutate the existing list, so avoid clearing required values or advertising algorithms unsupported by your <code>JwtEncoder</code>/`JWKSource`.

## 8. Complete Configuration Example in Spring Boot

The following snippet illustrates configuring both OAuth metadata and OIDC discovery within the same Authorization Server security chain:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerDiscoveryConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .authorizationServerMetadataEndpoint(metadata ->
                    metadata.authorizationServerMetadataCustomizer(
                        builder -> builder.claim(
                            "service_documentation",
                            "https://auth.example.com/docs/oauth")))
                .oidc(oidc -> oidc
                    .providerConfigurationEndpoint(provider ->
                        provider.providerConfigurationCustomizer(
                            builder -> {
                                builder.claim(
                                    "op_policy_uri",
                                    "https://auth.example.com/legal/privacy");
                                builder.claim(
                                    "op_tos_uri",
                                    "https://auth.example.com/legal/terms");
                            }))))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
    }
}
~~~

Imports are omitted. The example uses Spring Authorization Server 1.5.x's <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> API and both customizers with matching generic builders.

**Additional pieces needed in a real application:**

1. <code>RegisteredClientRepository</code> to manage clients.
2. <code>OAuth2AuthorizationService</code> and authorization persistence components.
3. <code>JWKSource&lt;SecurityContext&gt;</code> and appropriate <code>JwtEncoder</code>/token generator to sign ID Tokens/JWT access tokens and publish JWKS.
4. <code>JwtDecoder</code> required for certain OIDC features such as UserInfo per the configuration model.
5. End-User security chain/login provider if using Authorization Code/OIDC.
6. HTTPS, reverse proxy, trust configuration, and deployment database.

Do not treat a sample security chain like this as a complete production-ready Authorization Server. Apply HTTPS, key management, CSRF, and client/user authentication tailored to your system architecture.

### 8.1. No Need to Write Custom Discovery Controllers

When using the two endpoint configurers, the framework registers these filters:

- <code>OAuth2AuthorizationServerMetadataEndpointFilter</code>.
- <code>OidcProviderConfigurationEndpointFilter</code> if OIDC is enabled.

Avoid creating an extra <code>@RestController</code> at the same well-known URLs just to output JSON. Duplicate route controllers can shadow framework filters or break consistency with <code>AuthorizationServerSettings</code>.

### 8.2. OIDC Is Not Enabled by Default

In Spring Authorization Server 1.5.x, the minimal configuration includes the OAuth metadata endpoint, while **OIDC is disabled by default**. You must invoke <code>.oidc(...)</code> or enable the corresponding configurer for OpenID Provider Configuration and OIDC endpoints to be set up.

If an application uses only OAuth client credentials, there is no need to enable OIDC just so an OAuth client can read Token Endpoint details.

## 9. Mandatory Rules on Issuer

### 9.1. Issuer Must Match Exactly

Suppose the Authorization Server publishes:

~~~json
{
  "issuer": "https://auth.example.com"
}
~~~

JWTs issued by the server carry the corresponding <code>iss</code> and clients/Resource Servers configure this issuer. The following values **must not be treated as arbitrarily equivalent**:

~~~text
https://auth.example.com
https://auth.example.com/
https://auth.internal.example.com
http://auth.example.com
https://AUTH.EXAMPLE.COM
~~~

Under RFC 8414, the issuer in the metadata response must be **identical** to the issuer the client used to derive the metadata URL; if they do not match, the client must reject the metadata. Never normalize URLs arbitrarily to ignore differences in path, trailing slash, scheme, or host.

### 9.2. Same Issuer Across the Entire Cluster

In a multi-instance Authorization Server deployment:

- Every node must advertise the exact same issuer for the same logical Authorization Server.
- Issued tokens must carry a consistent <code>iss</code>.
- Discovery and JWKS must reflect keys/endpoints of the same issuer.
- Never let each node infer a different issuer from its internal address.
- When rotating keys, discovery must point to a JWKS containing all public keys still needed for verification.

Even a tiny issuer discrepancy can cause OIDC clients to reject ID Tokens or Resource Servers to reject access tokens despite valid signatures.

### 9.3. Never Change the Issuer Only Inside the Builder

If a customizer overrides <code>issuer</code> while <code>AuthorizationServerSettings</code> and the token generator use a different issuer, metadata and JWTs will contradict each other. Actually changing an issuer requires a controlled migration plan updating client registrations, callbacks, JWKS/discovery, Resource Servers, sessions, and active tokens.

## 10. Reverse Proxies, HTTPS, and Public Endpoint URLs

### 10.1. Common Mistakes Behind Ingress

A deployment may look like:

~~~text
Client --> https://auth.example.com
             |
             v
        Reverse Proxy / Ingress
             |
             v
        http://auth-service:9000
~~~

If misconfigured or if forwarded headers are trusted without control, discovery might return:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://auth-service:9000/oauth2/token",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

Broken result: external clients cannot reach those URLs, issuer mismatches occur, or metadata advertises insecure URLs.

### 10.2. Recommendations

1. Configure <code>AuthorizationServerSettings.issuer("https://auth.example.com")</code> as the source of truth.
2. Configure TLS/ingress/routes so public URLs actually resolve.
3. Trust <code>Forwarded</code>/<code>X-Forwarded-*</code> only from verified proxies; strip headers sent by internet clients.
4. When using <code>ForwardedHeaderFilter</code> or <code>server.forward-headers-strategy</code>, enforce a strict trust boundary against host-header injection.
5. Test with real external HTTP GETs, not just backend `MockMvc`.
6. Configure client redirect URIs and OIDC callbacks with exact public URLs.
7. Never publish private hosts, ports, admin paths, or debug endpoints in metadata.

### 10.3. Never Trust Caller-Supplied URLs

Metadata is critical configuration data. If an attacker tricks a server into returning a <code>jwks_uri</code> or <code>token_endpoint</code> pointing to an attacker-controlled host, clients can send tokens/secrets to the wrong destination or load untrusted keys.

For client discovery, fetch metadata only from configured/allowed issuers. If an app lets users enter arbitrary issuers, enforce strict URL validation, SSRF protection, redirect limits, DNS checks, and network egress rules—never fetch metadata/JWKS from internal addresses or cloud metadata services.

## 11. Path-Based Issuers and Multi-Tenant Models

### 11.1. RFC 8414 Inserts Well-Known Before the Issuer Path

When the issuer is:

~~~text
https://auth.example.com/tenant-a
~~~

RFC 8414 defines the OAuth Authorization Server Metadata URL as:

~~~text
https://auth.example.com/.well-known/oauth-authorization-server/tenant-a
~~~

Never default to appending <code>/.well-known/oauth-authorization-server</code> at the end of the issuer path.

### 11.2. OpenID Connect Discovery Uses a Different Historical Placement Rule

For an issuer with a path, traditional OpenID Connect Discovery 1.0 uses:

~~~text
https://auth.example.com/tenant-a/.well-known/openid-configuration
~~~

Whereas applying the RFC 8414 URL transformation with the <code>openid-configuration</code> suffix yields:

~~~text
https://auth.example.com/.well-known/openid-configuration/tenant-a
~~~

This is an important practical compatibility detail: client libraries and server versions may pick variants based on spec/profile. For a root issuer without a path, both rules produce <code>https://auth.example.com/.well-known/openid-configuration</code>.

### 11.3. Requirements for Multi-Issuer Setups

Do not build multi-tenancy merely by swapping the <code>issuer</code> field based on the `Host` header. A multi-issuer system must ensure:

- Discovery routing matches the tenant and URI standard.
- Metadata `issuer` matches the requested tenant.
- Authorization/token endpoints execute requests within the right tenant context.
- `RegisteredClient`s and authorization storage are partitioned per tenant.
- Signing keys/JWKS and token issuers match the tenant; tokens from one tenant must never be accepted in another.
- Cookie/session/login policies and redirect URIs never mix across tenants.
- Resource Servers validate issuer/audience and keys for the right tenant.

Multi-tenant discovery routes must be tested against your exact Spring Authorization Server version and reverse proxy. Never assume a static <code>AuthorizationServerSettings.issuer()</code> configuration creates a tenant resolver automatically.

## 12. JWKS and Algorithms Must Be Consistent

### 12.1. Conditions for Publishing `jwks_uri`

In Spring Authorization Server 1.5.x, the JWK Set endpoint is configured when a <code>JWKSource&lt;SecurityContext&gt;</code> bean is present. OIDC Provider Configuration has a required <code>jwks_uri</code> field.

When enabling OIDC:

1. Provide an appropriate public/private key source for signing ID Tokens.
2. Ensure the JWKS endpoint actually returns the public JWKs needed for verification.
3. Advertise <code>jwks_uri</code> using HTTPS and the public hostname matching the issuer.
4. Never return private key material in JWKS.
5. Confirm real ID Tokens carry a <code>kid</code> header matching a published public JWK.
6. Test key rotation with client JWKS caches.

### 12.2. ID Token Signing Metadata Is Not Decorative

<code>id_token_signing_alg_values_supported</code> must reflect the algorithms the OP actually uses to sign ID Tokens. If the server signs only with RSA RS256, never advertise <code>ES256</code> just to make the list look modern.

Never let clients choose signing algorithms by passing query parameters to the Discovery Endpoint; algorithm and key selection belong to server policy.

### 12.3. Rotation and Caching

Clients typically cache metadata and JWKS. During rotation:

- Pre-publish the new public key before signing tokens with the new key.
- Retain the old public key until tokens signed with it expire, except during emergency key-compromise revocation.
- Account for JWKS cache TTLs on OIDC clients and Resource Servers.
- Avoid changing <code>jwks_uri</code> on every rotation when a stable endpoint can serve multiple keys.
- Verify metadata/JWKS externally through the real ingress/CDN.

Stable metadata and updating JWKS are two separate operational layers; rotating keys does not require changing the issuer or endpoint URL.

## 13. Metadata for Advanced Features

Common metadata fields for advanced features:

| Feature | Common Metadata Fields | Condition to Advertise |
| --- | --- | --- |
| PKCE | <code>code_challenge_methods_supported</code> | Server supports listed methods; prefer S256. |
| Device Authorization | <code>device_authorization_endpoint</code> | Endpoint is active and grant has a matching provider. |
| Token Revocation | <code>revocation_endpoint</code> | Endpoint exists; client auth and revocation service work. |
| Token Introspection | <code>introspection_endpoint</code> | Endpoint active with client authorization policy. |
| Pushed Authorization Requests (PAR) | <code>pushed_authorization_request_endpoint</code> | PAR is enabled and the request flow is tested. |
| mTLS | <code>mtls_endpoint_aliases</code>, <code>tls_client_certificate_bound_access_tokens</code> | Real TLS endpoint aliases and end-to-end verification/binding exist. |
| DPoP | <code>dpop_signing_alg_values_supported</code> | Server and clients genuinely process DPoP proofs/bindings. |
| OIDC UserInfo | <code>userinfo_endpoint</code> | Endpoint enabled; tokens validated and claims follow consent/policy. |
| RP-Initiated Logout | <code>end_session_endpoint</code> | Logout endpoint and session/logout policy exist. |
| Dynamic Client Registration | <code>registration_endpoint</code> | Registration enabled and protected by initial access token/registration policy. |

Spring Authorization Server 1.5.x **does not enable Dynamic Client Registration by default**. Never add <code>registration_endpoint</code> to metadata just because you wish you had that feature.

### 13.1. Note on mTLS Endpoint Aliases

RFC 8705 allows publishing dedicated endpoint aliases for mTLS clients so end-user browsers are not prompted for client certificates at the Authorization Endpoint. However, adding <code>mtls_endpoint_aliases</code> to JSON does not create a new TLS listener. Configure ingress, hostnames, certificate trust, and routing first.

### 13.2. Note on PAR and Mandatory PAR

If metadata advertises a PAR endpoint or mandates PAR, clients must follow the corresponding flow. Do not advertise the mandatory-PAR flag if the Authorization Endpoint still accepts standard requests under another policy or clients are not yet compatible.

### 13.3. Note on OIDC Claims and Scopes

<code>scopes_supported</code> describes scopes the OP supports; <code>claims_supported</code> describes claims it can provide. Consent and per-client permissions still govern actual outputs. Never treat advertising <code>profile</code> as a promise to return every profile claim to every client.

## 14. Testing Metadata with HTTP and MockMvc

### 14.1. Smoke Testing with `curl`

From outside the cluster:

~~~bash
curl --fail --show-error --silent \
  https://auth.example.com/.well-known/oauth-authorization-server

curl --fail --show-error --silent \
  https://auth.example.com/.well-known/openid-configuration

curl --fail --show-error --silent \
  https://auth.example.com/oauth2/jwks
~~~

Query the OpenID Provider endpoint only when OIDC is enabled. If the JWKS endpoint is missing or errors, check the JWK source and server config. Never use <code>--insecure</code> to bypass TLS errors.

### 14.2. MockMvc Check for OAuth Metadata

Assuming the Spring Boot test initializes the Authorization Server security chain:

~~~java
@Test
void oauthMetadataPublishesExpectedPublicUrls() throws Exception {
    mockMvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://auth.example.com"))
        .andExpect(jsonPath("$.authorization_endpoint")
            .value("https://auth.example.com/oauth2/authorize"))
        .andExpect(jsonPath("$.token_endpoint")
            .value("https://auth.example.com/oauth2/token"))
        .andExpect(jsonPath("$.service_documentation")
            .value("https://auth.example.com/docs/oauth"));
}
~~~

This snippet assumes <code>mockMvc</code> is injected via <code>@AutoConfigureMockMvc</code> or equivalent setup. It tests metadata only, not that the Token Endpoint issues real tokens; add integration tests for every advertised grant.

### 14.3. MockMvc Check for OpenID Provider Configuration

~~~java
@Test
void oidcDiscoveryPublishesRequiredAndLegalMetadata() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
            .value("https://auth.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
            .value("https://auth.example.com/oauth2/jwks"))
        .andExpect(jsonPath("$.subject_types_supported")
            .isArray())
        .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
            .isArray())
        .andExpect(jsonPath("$.op_policy_uri")
            .value("https://auth.example.com/legal/privacy"))
        .andExpect(jsonPath("$.op_tos_uri")
            .value("https://auth.example.com/legal/terms"));
}
~~~

This test requires OIDC to be enabled and a `JWKSource` configured. If your deployment uses an issuer with a context path or multi-tenant URLs, adjust request paths and expected URLs to match your profile.

### 14.4. Testing Consistency Between Metadata and Runtime

Do not rely solely on JSON snapshot tests. For every key capability:

1. Fetch live metadata.
2. Confirm endpoint URLs sit within the expected public origin.
3. Send valid protocol requests to verify endpoints work.
4. Confirm invalid requests are rejected with proper OAuth/OIDC errors.
5. If PKCE S256 is advertised, complete a real Authorization Code + PKCE flow.
6. If a new grant is advertised, verify authorized clients succeed and unauthorized clients are denied.
7. If a JWK Set is advertised, use the public JWK to verify a real token.
8. If UserInfo is advertised, call it with a valid access token and check subject and scopes/claims.
9. If mTLS/DPoP is advertised, test authentication/proof enforcement at the Token Endpoint and Resource Server.

## 15. Regression Test Matrix

| Case | Expected Result |
| --- | --- |
| OAuth metadata endpoint over HTTPS | Returns JSON, exact issuer, and public HTTPS URLs. |
| OIDC disabled | Does not advertise OpenID Provider Configuration as if OIDC were active. |
| OIDC enabled | OpenID discovery returns valid OIDC metadata. |
| Custom OAuth documentation | <code>service_documentation</code> has valid URL without dropping required fields. |
| Custom OIDC policy/ToS | <code>op_policy_uri</code> and <code>op_tos_uri</code> are present. |
| Metadata <code>issuer</code> differs from token <code>iss</code> | Test fails; fix configuration. |
| Wrong trailing slash on issuer | Client detects mismatch rather than ignoring it. |
| Backend behind ingress | No <code>localhost</code>, internal hostnames, or HTTP URLs in metadata. |
| Client sends spoofed Host | Cannot make metadata advertise an arbitrary issuer. |
| JWKS endpoint | Publishes public keys only, no private material. |
| JWT signed with new key | JWKS includes public key matching <code>kid</code>. |
| OAuth metadata advertises new grant | Provider/converter handles grant and checks `RegisteredClient`. |
| OIDC advertises <code>claims_supported</code> | Claims are genuinely supported per scope/consent/policy. |
| Advertises <code>private_key_jwt</code> | Registered clients can authenticate with JWT assertions. |
| Advertises dynamic client registration | Only when endpoint is enabled and protected. |
| Path/tenant A issuer metadata | Discovery, token issuer, keys, and clients all belong to tenant A. |
| Tenant A metadata requested via tenant B | No leakage of endpoints/keys/issuer or authorizations across tenants. |
| Proxy/CDN caches stale metadata | Refresh/invalidation works when changing capabilities/URLs. |
| No JWKSource yet OIDC enabled | Startup/discovery tests flag missing or broken JWKS. |
| Endpoint returns 200 yet callback/redirect fails | Client-flow contract test catches mismatch. |

### 15.1. Security Testing with a Real Client Library

Run a test using Spring Security OAuth2 Client or your chosen production OIDC SDK:

- Configure only the Authorization Server's issuer.
- Let the library discover URLs and fetch the JWK Set automatically.
- Complete a real flow.
- Verify token signature, issuer, audience, timestamps, and scopes.
- Tamper with the issuer in mock metadata to confirm the client rejects it.

Testing with a real SDK surfaces URL normalization quirks, JWKS caching, path-based issuers, and required-field checks that `MockMvc` snapshot tests might miss.

## 16. Common Mistakes and Fixes

### Mistake 1: Adding a Capability to JSON Without a Real Endpoint

**Symptom:** Discovery returns a syntactically valid endpoint, yet real requests fail with 404 or unsupported grant.

**Cause:** Treating the metadata builder as a feature-enabling toggle.

**Fix:** Configure endpoints/filters/providers first, then advertise metadata and add integration tests.

### Mistake 2: Metadata Uses Internal Addresses Behind a Reverse Proxy

**Symptom:** External OIDC clients cannot reach the Token Endpoint or report invalid issuer.

**Cause:** Issuer was inferred from internal host/scheme.

**Fix:** Configure the public issuer, verify trusted forwarded headers, and test through the real ingress.

### Mistake 3: OIDC Discovery Does Not Exist

**Symptom:** GET <code>/.well-known/openid-configuration</code> returns 404.

**Cause:** OIDC is not enabled in the Authorization Server configurer, or requests do not hit the right security chain.

**Fix:** Enable <code>.oidc(...)</code>, verify matchers/filter chains, and supply JWT/endpoint dependencies.

### Mistake 4: `jwks_uri` Points to Wrong Path or Lacks Public Key

**Symptom:** Client receives an ID Token but cannot verify its signature.

**Cause:** Missing `JWKSource`, wrong JWKS endpoint, `kid` mismatch, or unsynchronized key rotation.

**Fix:** Register a proper key source, publish public JWKs, and test JWT verification with the published public key.

### Mistake 5: JWT `iss` Does Not Equal Discovery `issuer`

**Symptom:** SDK rejects the token despite a valid signature.

**Cause:** Overriding <code>issuer</code> only in the builder, or nodes running with inconsistent settings.

**Fix:** Use one trusted issuer source for both metadata and token generation; test across all instances.

### Mistake 6: Advertising an Unsupported ID Token Algorithm

**Symptom:** Client expects an algorithm incompatible with the token encoder or JWK Set.

**Cause:** Arbitrarily adding elements to <code>id_token_signing_alg_values_supported</code>.

**Fix:** Inspect the token generator's signing algorithms and test real tokens; never advertise weak or unsupported algorithms.

### Mistake 7: Confusing OAuth Metadata with OIDC Discovery

**Symptom:** OIDC client reads RFC 8414 metadata and expects OIDC-specific fields that are absent.

**Cause:** Wrong well-known URL or profile.

**Fix:** Choose the right document and enable the OP config endpoint when deploying OIDC.

### Mistake 8: Path-Based Issuer Using the Wrong Well-Known URL Transformation

**Symptom:** Multi-tenant clients encounter 404 or issuer mismatch.

**Cause:** Concatenating <code>/.well-known/...</code> without following the consumer's RFC/profile.

**Fix:** Apply RFC 8414 and OpenID Connect Discovery placement rules appropriately; test against real path issuers.

### Mistake 9: Using Metadata to Advertise Unprotected Dynamic Client Registration

**Symptom:** Rogue clients can create registrations bypassing policy.

**Cause:** Enabling the endpoint by mistake or publishing the registration URL without access control.

**Fix:** Enable only when required, with clear authorization/initial access token policies.

### Mistake 10: Writing a Custom JSON Controller, Bypassing Default Settings

**Symptom:** Metadata and real endpoints drift apart across upgrades.

**Cause:** Hardcoding JSON instead of using framework builders.

**Fix:** Use the endpoint configurers + builders, backed by contract tests as regression guards.

## 17. Production Operations

### 17.1. Metadata Change Workflow

A metadata change can alter how SDKs/clients select flows or endpoints. Safe workflow:

1. Identify the exact fields and runtime behaviors changing.
2. Check backward compatibility with existing clients.
3. Update real endpoint/grant/key configurations first or in lockstep.
4. Update the builder customizer rather than editing JSON outside the system.
5. Run metadata tests and end-to-end flow tests with real SDKs.
6. Release through staging/rolling deployment while monitoring 4xx/5xx errors and login failures.
7. Handle metadata/CDN caches and keep all nodes consistent.
8. Maintain a rollback plan for capabilities, endpoint URLs, and client configs if failures occur.

### 17.2. Sensible Metadata Caching

Discovery metadata is primarily public configuration and can be cached under well-configured HTTP policies. However:

- Too long a cache delays clients seeing new endpoints or capabilities.
- Too short a cache adds unnecessary load.
- Key rotation usually requires updating only JWKS, not changing the metadata URI.
- Changing the issuer or public host requires a migration plan; lowering cache TTL alone does not handle all existing tokens and sessions.

Do not assume every client honors identical TTLs. Test caching behavior of actual SDKs and reverse proxies/CDNs.

### 17.3. Metrics and Auditing

Monitor:

- Request counts and status codes for both well-known endpoints.
- Metadata schema/issuer mismatch errors from integration tests.
- Client token validation errors tied to issuer/JWKS/algorithms.
- Changes to public endpoint URLs and capability lists after deployment.
- JWKS update timestamps and key rotation events.
- Clients still hitting legacy discovery URLs after migration.

Never log bearer tokens, ID Tokens, client secrets, or sensitive request bodies just to diagnose metadata. For public discovery documents, logging request ID, endpoint, status, version/config hash, and origin is sufficient.

## 18. Practice Exercise

You are building an Authorization Server for three client groups: <code>orders-web</code> using Authorization Code + PKCE/OIDC, <code>orders-worker</code> using Client Credentials, and <code>partner-service</code> using `private_key_jwt`. The public server URL is <code>https://auth.example.com</code>, while the backend behind ingress runs at <code>http://auth:9000</code>.

1. Configure <code>AuthorizationServerSettings</code> with the public issuer and verify metadata contains no internal URLs.
2. Enable OIDC and expose both metadata endpoints per their respective standards.
3. Customize OAuth metadata with <code>service_documentation</code>.
4. Customize OpenID Provider Configuration with <code>op_policy_uri</code> and <code>op_tos_uri</code>.
5. Verify <code>response_types_supported</code>, <code>grant_types_supported</code>, and <code>token_endpoint_auth_methods_supported</code> match the real server.
6. Register a `JWKSource`; read <code>jwks_uri</code> and verify an ID Token using the public JWK.
7. Ensure a client-credentials token is not treated as an OIDC ID Token and OIDC <code>claims_supported</code> does not promise unimplemented claims.
8. Simulate malicious `Forwarded`/`Host` headers to verify the issuer cannot be arbitrarily altered.
9. Create a tenant issuer <code>https://auth.example.com/tenant-a</code>, compute its well-known URLs under RFC 8414 and OpenID Connect Discovery, and explain the difference.
10. Write MockMvc + HTTP integration tests using a real OIDC client SDK to verify discovery, token issuer, JWKS, audience, and cache refresh behavior.

**Acceptance criteria:** Both metadata JSONs conform to spec, public URLs/issuers are consistent, every advertised capability is **actually implemented by the server**, and the SDK can discover, obtain, and verify tokens without hardcoding endpoint URLs.

## 19. Reference Materials

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata fields, well-known URL rules, issuer validation, and security.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration, required metadata, discovery URLs, and OIDC client validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, subject types, and claims.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): <code>OAuth2AuthorizationServerMetadataEndpointConfigurer</code> and <code>OidcProviderConfigurationEndpointConfigurer</code>.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): enabling OIDC, `AuthorizationServerSettings`, JWK Set endpoint, and core beans.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerMetadata.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationServerMetadata.Builder.html): claim builder and required fields.
- [Spring Authorization Server 1.5.8 — OidcProviderConfiguration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): policy/claims/subject/signing metadata and required fields.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): public key format published via JWKS.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS endpoint aliases and certificate-bound token metadata.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR endpoint and behavior.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth/OIDC client configuration and discovery.
