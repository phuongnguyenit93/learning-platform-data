# OAuth2 Authorization Server Metadata per RFC 8414

> **Chapter:** Metadata and Discovery  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Objective:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Technical Scope:** RFC 8414 and Spring Authorization Server (SAS) 1.5.x on Spring Boot 3.x/Spring Security 6.x, Servlet stack. Examples place the issuer at `https://auth.example.test`. If the project uses Spring Security 7.x with integrated Authorization Server support, verify the corresponding starter/package/DSL for that exact version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what problem **OAuth 2.0 Authorization Server Metadata** solves and why it is commonly called **OAuth Discovery**.
2. Compute the exact `/.well-known/oauth-authorization-server` URL from an issuer according to RFC 8414, including when the issuer contains a path.
3. Identify `issuer` and fields for endpoints, grant types, response types, PKCE, client authentication, key locations, and metadata extensions.
4. Distinguish between **Authorization Server Metadata**, **JWK Set**, **OpenID Provider Configuration**, and **Protected Resource Metadata**.
5. Understand `REQUIRED`, `RECOMMENDED`, and `OPTIONAL` conditions, RFC 8414 defaults when a field is omitted, and why you should not blindly rely on legacy defaults.
6. Configure `AuthorizationServerSettings` and `OAuth2AuthorizationServerMetadataEndpointConfigurer` in Spring Authorization Server.
7. Design issuer, HTTPS, reverse proxy, path routing, metadata caching, and JWKS without introducing mix-up or issuer mismatch vulnerabilities.
8. Write automated tests for the discovery endpoint, issuer consistency, metadata security, client consumption, and multi-environment deployment.

**Key takeaway:** RFC 8414 lets an OAuth2 Client learn **where the Authorization Server is and what capabilities it supports** from a standard JSON document bound to a **trusted issuer**. Metadata eliminates unnecessary hardcoded URLs, but it **does not authenticate clients, does not grant permissions to clients, and does not prove that every capability is granted to every RegisteredClient**.

## 2. The Problem Before Discovery

An OAuth2 Client application needs at least:

- The Authorization Server (AS) issuer/identifier.
- The Authorization Endpoint to initiate Authorization Code + PKCE.
- The Token Endpoint to exchange an authorization code or refresh token.
- The JWK Set URI if it needs to verify JWTs/ID tokens.
- Supported capabilities: grant types, response types, PKCE challenge methods, and client authentication methods.
- In complex systems: Token Revocation, Token Introspection, Dynamic Client Registration, PAR, Device Authorization, and other extensions.

If all addresses are hardcoded into every client, changing a hostname, reverse proxy, path, or authentication method can force updates across dozens of applications.

Example manually configured client:

~~~yaml
oauth:
  issuer: https://auth.example.test
  authorization-uri: https://auth.example.test/oauth2/authorize
  token-uri: https://auth.example.test/oauth2/token
  jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

If the issuer undergoes a controlled change or endpoints are moved, every client must be updated accurately. A single wrong URL can cause 404s, fetch keys from the wrong issuer, or risk sending authorization codes/credentials to the wrong destination.

RFC 8414 defines **a standard JSON document** that a client can retrieve from the issuer to discover the actual endpoints and capabilities.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant R as Resource Server

    Note over C,AS: Client knows the issuer from trusted configuration
    C->>AS: GET /.well-known/oauth-authorization-server
    AS-->>C: 200 JSON: issuer, endpoints, capabilities, jwks_uri
    C->>C: Verify issuer matches the trusted value
    C->>AS: Authorization request / token request depending on grant
    AS-->>C: Authorization code / access token
    C->>R: Authorization: Bearer access token
    R->>R: Validate issuer, audience, signature, expiry, and permissions
~~~

**Discovery does not replace client registration.** Metadata may advertise `client_secret_basic` and `private_key_jwt`, but each RegisteredClient still has its own allowed authentication method, grants/scopes, and credentials.

## 3. What Is RFC 8414?

RFC 8414, *OAuth 2.0 Authorization Server Metadata* (June 2018), defines a JSON metadata document with:

- The issuer identifier.
- Standard endpoint URLs.
- Authorization Server capabilities.
- How metadata is published at a `.well-known` URI.
- How a client must validate metadata before using it.
- An optional capability to carry signed metadata under `signed_metadata`.

It generalizes the idea from OpenID Connect Discovery to **OAuth 2.0 in general**, including systems **without OIDC enabled**.

### 3.1. Three Things Often Confused

| Component | Question Answered | Where Is It Typically Retrieved? |
| --- | --- | --- |
| **Authorization Server Metadata** (RFC 8414) | “What issuer, endpoints, and capabilities does the AS have?” | `/.well-known/oauth-authorization-server` from the issuer |
| **JWK Set (JWKS)** (RFC 7517) | “Which public keys verify JWTs?” | URI published in `jwks_uri`, e.g., `/oauth2/jwks` |
| **OpenID Provider Configuration** (OIDC Discovery) | “What login, ID token, UserInfo, and scopes/claims does the OpenID Provider support?” | `/.well-known/openid-configuration` per OIDC |

In addition, **Protected Resource Metadata** (RFC 9728, April 2025) describes the **Resource Server**, not the Authorization Server. It can help clients find Authorization Servers associated with a resource, but it does not replace RFC 8414 metadata.

### 3.2. Public Metadata Does Not Mean Other Endpoints Are Public

The metadata document should be accessible via a plain HTTPS GET without requiring a client secret or user login just to inspect configuration. However:

- `/oauth2/token` still requires client authentication appropriate to the grant/registration.
- `/oauth2/introspect` and `/oauth2/revoke` still have their own authentication/authorization.
- `/connect/register` is not automatically opened just because metadata mentions dynamic registration.
- `/oauth2/authorize` still requires user authentication/consent when the flow requires it.
- `/oauth2/jwks` only publishes **public keys**, never private keys.

Metadata advertises **paths and capabilities**; it does not grant permissions by itself.

## 4. Constructing the Correct Well-Known URL from the Issuer

### 4.1. Issuer Without a Path

If the issuer is:

~~~text
https://auth.example.test
~~~

The metadata URL is:

~~~text
https://auth.example.test/.well-known/oauth-authorization-server
~~~

HTTP request:

~~~http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

The AS returns HTTP 200 with JSON metadata.

### 4.2. Issuer With a Path: Well-Known Is Inserted Before the Path

This is a critical detail in RFC 8414. For example, given issuer:

~~~text
https://auth.example.test/tenant/acme
~~~

The metadata URL per RFC 8414 is:

~~~text
https://auth.example.test/.well-known/oauth-authorization-server/tenant/acme
~~~

**Not**:

~~~text
https://auth.example.test/tenant/acme/.well-known/oauth-authorization-server
~~~

Under RFC 8414, `/.well-known/oauth-authorization-server` is **inserted between the host and the issuer's path**.

| Issuer | RFC 8414 metadata URL |
| --- | --- |
| `https://auth.example.test` | `https://auth.example.test/.well-known/oauth-authorization-server` |
| `https://auth.example.test/issuer1` | `https://auth.example.test/.well-known/oauth-authorization-server/issuer1` |
| `https://auth.example.test/tenants/a` | `https://auth.example.test/.well-known/oauth-authorization-server/tenants/a` |

The RFC requires stripping any trailing `/` from the issuer path before inserting the suffix according to the rule. In multi-tenant deployments, verify the external URL through the actual proxy and routing; do not assume a servlet context path automatically guarantees RFC compliance for every issuer/path.

### 4.3. Do Not Guess the URL from the Token Endpoint

If you only know:

~~~text
https://auth.example.test/oauth2/token
~~~

you cannot reliably infer that the issuer is `https://auth.example.test` if the system deploys multiple issuers/paths or host aliases. Obtain the issuer from trusted configuration or an appropriate AS identification mechanism, then apply the well-known derivation algorithm.

### 4.4. Requirements on Issuer

According to RFC 8414, `issuer`:

- Is a URL using `https`.
- Contains no query string.
- Contains no fragment.
- Must unambiguously identify the AS providing the metadata.
- Must match **exactly** with the issuer identifier the client used to construct the well-known URL.

Examples:

~~~text
Trusted issuer:  https://auth.example.test
Metadata issuer: https://auth.example.test
=> Match

Trusted issuer:  https://auth.example.test
Metadata issuer: https://auth-alias.example.test
=> NO match

Trusted issuer:  https://auth.example.test/tenant/a
Metadata issuer: https://auth.example.test/tenant/b
=> NO match
~~~

Do not "fix" an issuer by stripping paths, changing hosts, lowercasing the entire URL, or turning an alias into a different issuer. RFC 8414 specifies **exact-match** comparison after JSON escaping is processed, without arbitrary Unicode normalization.

## 5. JSON Structure of Authorization Server Metadata

Illustrative example for an AS using Authorization Code + PKCE, Client Credentials, Refresh Token, and common endpoints:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300

{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "scopes_supported": ["booking.read", "booking.write"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "none"
  ],
  "token_endpoint_auth_signing_alg_values_supported": ["RS256"],
  "code_challenge_methods_supported": ["S256"],
  "revocation_endpoint": "https://auth.example.test/oauth2/revoke",
  "introspection_endpoint": "https://auth.example.test/oauth2/introspect"
}
~~~

**Note:** This is an **illustrative JSON document for a possible configuration**, not a claim that Spring Authorization Server emits these exact fields and values by default. The supported list must be verified against the actual version, endpoint configuration, authentication providers, and policies. Do not add `registration_endpoint` if Dynamic Client Registration is not enabled/implemented.

### 5.1. Meaning of Issuer

`issuer` is a **security identifier**, not just a homepage URL. It relates to:

- Discovery metadata validation.
- JWT access token `iss` if the token-issuing profile includes an issuer.
- OIDC ID token `iss` when OIDC is enabled.
- Resource Server issuer validation.
- Preventing confusion among multiple Authorization Servers (authorization server mix-up).
- Separating tenants/realms with distinct issuers.

If metadata states issuer A but a signed JWT carries `iss` as issuer B, the Resource Server/OIDC Client must reject it per policy. Never accept a token merely because its JWT signature verifies against a familiar public key.

### 5.2. Endpoint URLs

A field such as `authorization_endpoint` or `token_endpoint` specifies the **full URL** where clients send requests. Clients should not manually concatenate strings like `issuer + "/oauth2/token"` when metadata already provides the endpoint.

In multi-tenant or reverse-proxy deployments, an endpoint might not share the same logical path prefix as the issuer; what is mandatory is that metadata publishes the real URL and that security/HTTPS constraints apply.

### 5.3. Metadata Describes Server Capabilities, Not Client Permissions

For example, metadata has:

~~~json
{
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ]
}
~~~

A client must not assume "I am allowed to use `client_credentials`." The AS still checks:

- Whether `RegisteredClient.authorizationGrantTypes` includes that grant.
- Whether the client authentication method matches the registration.
- Whether the requested scopes are registered and authorized.
- Whether proof/PKCE/client assertion/certificate is valid.
- Whether endpoint policy/tenant policy permits it.

Similarly, `scopes_supported` only describes the scope namespace supported by the AS; it does not allow a client to request every listed scope.

## 6. Core Fields of RFC 8414

### 6.1. Required or Conditionally Required Fields

| Metadata field | RFC 8414 Requirement Level | Meaning |
| --- | --- | --- |
| `issuer` | **REQUIRED** | AS identifier as an HTTPS URL |
| `authorization_endpoint` | REQUIRED unless no grant needing an authorization endpoint is supported | URL to start the authorization flow |
| `token_endpoint` | REQUIRED except when only the implicit grant is supported | URL to exchange a grant for tokens |
| `response_types_supported` | **REQUIRED** | List of `response_type` values at the authorization endpoint |
| `jwks_uri` | OPTIONAL in RFC 8414 itself | HTTPS URL to the AS's JWK Set |
| `scopes_supported` | RECOMMENDED | List of supported scopes (may omit some scopes) |

"OPTIONAL" in RFC 8414 does not mean optional in every other profile. For example, OIDC Discovery has its own requirement for `jwks_uri`, and if clients require JWT verification, lacking a key source can break the flow.

### 6.2. Capability Extension Fields

| Metadata field | Purpose |
| --- | --- |
| `response_modes_supported` | Response modes such as `query`, `form_post` if supported |
| `grant_types_supported` | Authorization grant types supported by the AS |
| `token_endpoint_auth_methods_supported` | Client authentication methods at the Token Endpoint |
| `token_endpoint_auth_signing_alg_values_supported` | JWS algorithms for `private_key_jwt`/`client_secret_jwt` client assertions |
| `code_challenge_methods_supported` | PKCE methods such as `S256` |
| `registration_endpoint` | Dynamic Client Registration URL if the endpoint is enabled |
| `revocation_endpoint` | Token Revocation Endpoint URL per RFC 7009 |
| `introspection_endpoint` | Token Introspection Endpoint URL per RFC 7662 |
| `revocation_endpoint_auth_methods_supported` | Client authentication at revocation |
| `introspection_endpoint_auth_methods_supported` | Client authentication at introspection |
| `service_documentation` | Integration documentation page for the AS |
| `ui_locales_supported` | UI locales if advertised |
| `op_policy_uri`, `op_tos_uri` | Policy / terms of service URLs |
| `signed_metadata` | Signed metadata, optional in RFC 8414 |

### 6.3. Do Not Confuse the Two Algorithm Categories

- `token_endpoint_auth_signing_alg_values_supported`: algorithms the AS accepts when **a client uses a JWT assertion to authenticate at the Token Endpoint**.
- Signing algorithms for **the AS's own access tokens/ID tokens**: governed by token generator/JWS signing key policy, and may be described by other fields/profiles.

Do not use the client assertion algorithm list as an allowlist for verifying JWT access tokens unless an appropriate contract exists. The names look similar, but their purposes differ.

### 6.4. Rules When a Metadata Field Is Omitted

RFC 8414 defines several historical defaults:

| Omitted Field | Default/Semantics per RFC 8414 | Implementation Note |
| --- | --- | --- |
| `response_modes_supported` | `["query","fragment"]` | Do not assume `form_post` is supported |
| `grant_types_supported` | `["authorization_code","implicit"]` | The `implicit` default is historical; do not enable implicit just because the field is absent |
| `token_endpoint_auth_methods_supported` | `client_secret_basic` | Do not assume `private_key_jwt` or mTLS is supported |
| `revocation_endpoint_auth_methods_supported` | `client_secret_basic` | Different policies can be explicitly advertised |
| `introspection_endpoint_auth_methods_supported` | Must be determined by other means | Do not automatically apply the token endpoint default |
| `code_challenge_methods_supported` | Per RFC, absence indicates PKCE is not supported | When deploying PKCE, explicitly advertise `S256` |
| `scopes_supported` | No implied scope set | Clients must not infer all scopes |
| `jwks_uri` | No default | Clients needing a key source must obtain it via a valid mechanism |

**Standard and best-practice note:** Default values define **RFC 8414 parsing semantics**, not a recommendation to enable `implicit` or allow weak algorithms in new systems. Under OAuth 2.0 Security Best Current Practice (RFC 9700), modern systems should prefer Authorization Code + PKCE and restrict insecure legacy flows.

### 6.5. Are Empty Arrays Valid?

RFC 8414 specifies that multi-valued fields are represented as JSON arrays, and **empty arrays must be omitted from the response**.

Do not advertise:

~~~json
{
  "code_challenge_methods_supported": []
}
~~~

as if it were a normal value; when there are no values, omit the field per the RFC. However, for the required `response_types_supported`, the AS architecture must define an appropriate profile/value rather than fabricating a response type the server does not handle.

## 7. Spring Authorization Server Metadata

### 7.1. Built-in Endpoint

In Spring Authorization Server 1.5.x, `OAuth2AuthorizationServerConfigurer` supports:

- `OAuth2AuthorizationServerMetadataEndpointConfigurer` to customize metadata.
- `OAuth2AuthorizationServerMetadataEndpointFilter` to serve metadata requests.
- `OAuth2AuthorizationServerMetadata` model/builder to construct the JSON response.
- `AuthorizationServerSettings` to define the issuer and URIs of the main OAuth2 endpoints.

The metadata endpoint is part of Spring Authorization Server's default protocol endpoints. You do not need to write a custom `@GetMapping("/.well-known/oauth-authorization-server")` REST controller if you are using the framework's filter/configurer.

### 7.2. Configuring the AS SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.authorizationServerMetadataEndpoint(
                    Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

This example uses SAS 1.x and assumes required beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, and signing keys/issuer configuration are present when issuing JWTs. For OIDC, `OidcConfigurer` and its corresponding components are also needed.

The metadata filter typically returns JSON directly at the endpoint before user authentication logic in the chain runs; thus metadata is publicly accessible even though the chain protects the remaining OAuth2 protocol endpoints. **Always test GET without cookies/credentials**; if a custom filter, proxy, or security rule alters processing order, metadata must not unintentionally return an HTML login page, 302, or 401.

### 7.3. Why Not Let the Application Chain Match First?

If a general `SecurityFilterChain` matches `/**` before the AS chain, requests to `/.well-known/oauth-authorization-server` can fall into the web application instead of the metadata filter.

Consequences:

- 404.
- 302 redirect to `/login`.
- 401/403.
- HTML instead of JSON.
- The metadata endpoint being served by a hand-written controller with out-of-sync configuration.

Use `@Order(1)` and `getEndpointsMatcher()` for the AS, and test real requests directly through the Spring Security FilterChain.

## 8. Configuring Issuer and Endpoints with AuthorizationServerSettings

### 8.1. Stable Issuer Configuration Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.test")
            .authorizationEndpoint("/oauth2/authorize")
            .tokenEndpoint("/oauth2/token")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .jwkSetEndpoint("/oauth2/jwks")
            .build();
    }
}
~~~

`issuer` is the public URL trusted by clients and Resource Servers. Do not casually use `http://localhost:9000` or an internal hostname like `http://auth-service:9000` in production metadata if external clients use `https://auth.example.test`.

### 8.2. Other Endpoint URIs

`AuthorizationServerSettings` supports configuring many OAuth2 and OIDC endpoint paths, depending on version:

| Setting | Typical Path |
| --- | --- |
| `authorizationEndpoint(...)` | `/oauth2/authorize` |
| `tokenEndpoint(...)` | `/oauth2/token` |
| `tokenIntrospectionEndpoint(...)` | `/oauth2/introspect` |
| `tokenRevocationEndpoint(...)` | `/oauth2/revoke` |
| `jwkSetEndpoint(...)` | `/oauth2/jwks` |
| `pushedAuthorizationRequestEndpoint(...)` | `/oauth2/par` |
| `deviceAuthorizationEndpoint(...)` | `/oauth2/device_authorization` |
| `deviceVerificationEndpoint(...)` | `/oauth2/device_verification` |
| `oidcUserInfoEndpoint(...)` | `/userinfo` |
| `oidcLogoutEndpoint(...)` | `/connect/logout` |
| `oidcClientRegistrationEndpoint(...)` | `/connect/register` |

**Not all endpoints are enabled/published in every configuration.** For instance, OIDC is disabled by default; Dynamic Client Registration in OIDC is disabled by default; the JWK Set endpoint is only configured when a `JWKSource<SecurityContext>` bean is present. Metadata must reflect the endpoints that actually serve requests.

### 8.3. Changing Issuer Does Not Automatically Make Clients Accept It

Changing the issuer is a change of **security identity**. It affects JWT `iss`, OIDC login, issuer validation on Resource Servers, and redirect/client registrations in some environments.

Migrating an issuer requires:

1. Defining the new issuer with valid HTTPS/DNS/TLS.
2. Publishing new metadata at the corresponding well-known URL.
3. Updating clients/RS configured with explicit trust.
4. Planning for existing tokens signed under the old issuer.
5. Verifying signed JWT issuer, JWKS URI, and audience.
6. Avoiding arbitrary dual issuer aliases sharing the same authorization state unless explicitly designed by policy.

### 8.4. Metadata Path Is Fixed by the RFC

`AuthorizationServerSettings` lets you customize **protocol endpoint paths** such as token/authorization/JWKS, but the **RFC 8414 well-known** path should not be treated as a business endpoint to rename arbitrarily. `authorizationServerMetadataEndpoint(...)` mainly customizes the **metadata response**, not an arbitrary endpoint renaming API.

When the issuer has a path or complex reverse-proxy rewrites, route external `/.well-known/oauth-authorization-server/...` according to the RFC and test against the real public URL. Do not rely on an internal metadata endpoint matching if the external path differs.

## 9. Customizing the Metadata Response via DSL

Spring Authorization Server 1.5.x provides an extension point:

~~~java
authorizationServer
    .authorizationServerMetadataEndpoint(metadataEndpoint ->
        metadataEndpoint.authorizationServerMetadataCustomizer(
            metadata -> {
                metadata.claim(
                    "service_documentation",
                    "https://docs.example.test/oauth2/integration");

                metadata.claim(
                    "ui_locales_supported",
                    java.util.List.of("vi-VN", "en-US"));
            }
        )
    );
~~~

This snippet is a fragment inside `.with(authorizationServer, ...)`, illustrating the `OAuth2AuthorizationServerMetadataEndpointConfigurer` callback.

### 9.1. When Is a Customizer Needed?

- Publishing an integration documentation URL.
- Advertising UI locales if the AS actually supports them.
- Publishing extension metadata from newer standards, e.g., an implemented feature.
- Adding metadata for an internal deployment profile with a well-defined contract and namespace.
- Adjusting capability advertisement so metadata reflects reality, while verifying client compatibility.

### 9.2. Do Not Let Metadata Diverge from Implementation

A customizer can modify the JSON builder, but **it does not add an AuthenticationProvider, filter, or endpoint**.

Incorrect example:

~~~java
metadata.claim(
    "grant_types_supported",
    java.util.List.of("authorization_code", "password"));
~~~

If the AS does not support the `password` grant, clients reading metadata will be misled. Conversely, advertising `registration_endpoint` does not make the Dynamic Client Registration endpoint appear.

For security-critical fields like `issuer`, `jwks_uri`, `token_endpoint`, and authentication methods, prefer configuring the underlying components rather than overriding metadata just to "look right."

### 9.3. A More Complete Configuration Example

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MetadataEndpointConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as -> as
                .authorizationServerMetadataEndpoint(endpoint -> endpoint
                    .authorizationServerMetadataCustomizer(metadata -> {
                        metadata.claim(
                            "service_documentation",
                            "https://docs.example.test/oauth2/integration");
                        metadata.claim(
                            "ui_locales_supported",
                            List.of("vi-VN", "en-US"));
                    })
                )
            )
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());

        return http.build();
    }
}
~~~

**Caution:** This is an alternative to the AS `SecurityFilterChain` configuration in Section 7.2; **do not copy both `@Order(1)` beans into the same project**. Core component/issuer/JWK beans and other application chains must be configured in their appropriate places.

## 10. Metadata, JWT, and JWK Set

### 10.1. Metadata Provides the Path to Public Keys

The field:

~~~json
{
  "jwks_uri": "https://auth.example.test/oauth2/jwks"
}
~~~

points to a JWK Set, for example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "as-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

These values are placeholders. The JWKS is served separately from metadata and must contain only **public key material** intended for publication.

### 10.2. Metadata Discovery and JWKS Fetch Are Two Separate Operations

~~~mermaid
flowchart TD
    ISS["Trusted issuer"]
    META["GET /.well-known/oauth-authorization-server"]
    CHECK{"Response issuer<br/>matches trusted issuer?"}
    JSON["Receive URLs/capabilities"]
    JWK["GET verified jwks_uri"]
    VERIFY["Verify JWT<br/>signature, iss, aud, exp"]
    REJECT["Reject metadata/token"]

    ISS --> META --> CHECK
    CHECK -->|"No"| REJECT
    CHECK -->|"Yes"| JSON --> JWK --> VERIFY
~~~

A Resource Server can be configured directly with `issuer-uri` and use discovery to locate the keys. Some environments pass `jwk-set-uri` directly to control URL/key fetching explicitly; in that case, the issuer must still be verified with an appropriate validator.

### 10.3. Metadata Cache and JWKS Cache Differ

Metadata changes infrequently: the issuer and endpoint URLs are relatively stable. JWKS changes during key rotation.

- Clients may cache metadata according to HTTP policy/SDK behavior.
- Resource Servers may cache JWKS inside the JWT decoder.
- CDNs may cache both with separate TTLs.
- New public keys must be pre-published before the AS switches the active signer as planned.
- Changing `jwks_uri` impacts both metadata caches and key caches.
- Rotating a key `kid` does not necessarily change metadata if `jwks_uri` stays the same.

Do not assume that "client refreshes metadata" refreshes JWKS inside every Resource Server's cache.

## 11. How OAuth Metadata Differs from OIDC Discovery

### 11.1. Two Common Well-Known Endpoints

| Metadata Type | Common Path | When Is It Needed? |
| --- | --- | --- |
| OAuth 2.0 RFC 8414 | `/.well-known/oauth-authorization-server` | OAuth2 AS, even without OIDC |
| OpenID Provider Configuration | `/.well-known/openid-configuration` | OIDC login, ID token, UserInfo, and OP capabilities |

Spring Authorization Server provides both:

- `OAuth2AuthorizationServerMetadataEndpointConfigurer` for OAuth2 metadata.
- `OidcProviderConfigurationEndpointConfigurer` for OIDC Provider Configuration, once `OidcConfigurer` is enabled.

OIDC is **disabled by default** in SAS 1.5.x. Do not assume `/.well-known/openid-configuration` exists just because the OAuth2 metadata endpoint works.

### 11.2. OIDC Metadata Adds Extra Fields

OIDC typically advertises:

- `userinfo_endpoint`.
- `id_token_signing_alg_values_supported`.
- `subject_types_supported`.
- `claims_supported` and OIDC claim capabilities.
- `end_session_endpoint` if RP-Initiated Logout is supported.
- Other fields per OpenID Connect Discovery and extension profiles.

Do not assume RFC 8414 requires every AS to have `userinfo_endpoint`, ID tokens, or OIDC logout.

### 11.3. Historical Difference for Issuer Paths

For an issuer with a path, RFC 8414 inserts the suffix before the issuer path. OIDC Discovery 1.0 historically constructed the well-known URL differently with an issuer path in some scenarios.

For example, given issuer `https://auth.example.test/tenant/a`:

~~~text
RFC 8414:
https://auth.example.test/.well-known/oauth-authorization-server/tenant/a

OIDC Discovery legacy transformation:
https://auth.example.test/tenant/a/.well-known/openid-configuration
~~~

RFC 8414 includes forward-compatibility notes between well-known transformations when using the `openid-configuration` suffix. When operating both OAuth2 and OIDC, inspect the **actual URL used by the client SDK** per profile/library rather than simply swapping the suffix name and assuming paths always match.

## 12. Extension Metadata: PAR, Device, DPoP, mTLS

RFC 8414 allows additional metadata fields defined by other specifications.

### 12.1. Pushed Authorization Requests (PAR)

When supporting PAR (RFC 9126), the AS can publish `pushed_authorization_request_endpoint` so clients know where to send pushed authorization requests.

However:

- Having the metadata field does not enable the PAR filter by itself.
- Clients must be permitted to use PAR per policy.
- The Authorization Endpoint must handle `request_uri` with the proper constraints.
- If a `require_pushed_authorization_requests` policy exists, client registration and AS behavior must stay aligned.

### 12.2. Device Authorization

When supporting OAuth 2.0 Device Authorization Grant (RFC 8628), the AS can publish `device_authorization_endpoint`. Device clients must still be registered for that grant type and obey `interval`/`slow_down`.

Do not confuse `device_authorization_endpoint` (where the device obtains a device code) with `device_verification_endpoint`/verification URI that the user opens in a browser.

### 12.3. DPoP

DPoP (RFC 9449) defines its own metadata capabilities such as `dpop_signing_alg_values_supported` depending on the supported profile. Do not advertise DPoP simply because the AS issues JWTs; DPoP requires proof verification, sender-constrained token semantics, and Resource Server checks.

### 12.4. mTLS

RFC 8705 defines additional metadata, including `mtls_endpoint_aliases` if the AS provides dedicated endpoint aliases for mTLS. Do not set `mtls_endpoint_aliases` if the deployment does not design those aliases.

### 12.5. Token Exchange and Grant Extensions

A grant extension such as Token Exchange uses the URI `urn:ietf:params:oauth:grant-type:token-exchange`. It can be advertised in `grant_types_supported` if the version and policy actually provide a handler for it.

Do not advertise a grant in metadata before its converter/provider, registration, validation, and tests are complete.

### 12.6. Authorization Server Metadata Is Not Protected Resource Metadata

RFC 9728 describes Resource Server metadata so clients can learn about protected resources and their associated Authorization Servers. For example, a resource may advertise an `authorization_servers` list.

However:

- OAuth2 AS Metadata (RFC 8414) returns capabilities of the **AS**.
- Protected Resource Metadata (RFC 9728) returns capabilities of the **RS**.
- Both have separate trust models and endpoint URLs.

Do not put the RS's `authorization_servers` field into AS metadata as a replacement for `issuer`, nor infer that any Authorization Server advertised by an RS is automatically trusted by the client without a trust policy.

## 13. Discovery Security: Issuer Mix-Up, Endpoint Injection, and SSRF

### 13.1. Issuer Validation Is Mandatory

RFC 8414 rule: after fetching metadata, the client **must compare `issuer` in the JSON with the issuer used to construct the well-known URL**. If they do not match exactly, **the metadata must not be used**.

Why? In multi-AS environments, an attacker may try to trick a client into sending an authorization code or token request to the wrong AS. The issuer check is a critical defense against mix-up attacks.

### 13.2. Never Accept Issuers from Untrusted Sources

Mistake:

~~~java
// UNSAFE IDEA:
// Read an arbitrary issuer from an untrusted HTTP request,
// fetch metadata at that URL, and immediately use token_endpoint
// / jwks_uri from the response to send credentials or verify tokens.
~~~

If an application lets a user/client supply an arbitrary issuer and the server fetches that URL, it can cause SSRF to internal hosts, metadata poisoning, or credential exfiltration.

Mitigations:

- Maintain a trusted issuer allowlist or an approved issuer onboarding workflow.
- Allow only `https`, with full TLS certificate/hostname verification.
- Restrict redirects when fetching metadata.
- Block private/loopback/link-local IPs and defend against DNS rebinding per threat model when handling external issuers.
- Enforce exact-match on `issuer`.
- Constrain `authorization_endpoint`, `token_endpoint`, and `jwks_uri` by policy; never send client secrets to unfamiliar URLs.
- Ensure tenants/clients cannot mix issuers and metadata across environments.

### 13.3. Metadata Is Not a Permission-Granting Signature

Metadata is JSON over HTTPS. It is not an access token, does not replace JWT signatures, and does not prove an endpoint is authorized to receive arbitrary credentials.

Even when `jwks_uri` is valid, a Resource Server must still:

- Verify the JWT signature with the right key/algorithm.
- Verify `iss` and `aud`.
- Check `exp`/`nbf`.
- Check scopes/authorities and application policy.
- If tokens are sender-constrained, verify the DPoP/mTLS proof.

### 13.4. Signed Metadata Is Optional

RFC 8414 defines `signed_metadata`: a JWT carrying signed or MACed metadata values.

Key points to remember:

- `signed_metadata` is **OPTIONAL**; not every SAS deployment emits this field.
- The metadata JWT contains the `iss` of the party asserting the metadata.
- Clients must have a trust anchor and proper signature verification process; never accept signed metadata from an arbitrary source.
- If a client supports signed metadata, RFC 8414 requires values inside the signed metadata to take precedence over same-named JSON elements.
- Do not confuse `signed_metadata` with an `id_token` or access token.
- Do not enable metadata signing simply by attaching a custom JWT string to the field without designing the trust and signing workflow.

### 13.5. Avoid Publishing Incorrect or Internal Metadata

Do not publish:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://10.0.1.42:9000/oauth2/token"
}
~~~

to external clients in production. These are internal/HTTP URLs that do not match the public issuer and can break TLS security and trust.

Also never publish private JWK keys, client secrets, database addresses, session keys, or admin-only endpoints in metadata.

## 14. Reverse Proxies, Forwarded Headers, and Stable Issuers

### 14.1. Typical Architecture

~~~mermaid
flowchart LR
    C["OAuth2 Client / Resource Server"]
    LB["HTTPS Reverse Proxy<br/>auth.example.test"]
    AS["Spring Authorization Server<br/>internal auth-service:9000"]

    C -->|"GET metadata HTTPS"| LB
    LB -->|"Forwarded request over trusted network"| AS
    AS -->|"JSON issuer & public endpoints"| LB
    LB --> C
~~~

If the AS constructs URLs from an internal request using scheme `http` and host `auth-service:9000`, metadata will disagree with the public URL. Worse, the JWTs it issues will carry an `iss` different from what clients and Resource Servers trust.

### 14.2. Configure Issuer Explicitly

Prefer declaring:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .build();
}
~~~

Do not rely solely on `Host`/`X-Forwarded-Host`/`X-Forwarded-Proto` from untrusted requests to determine the issuer.

If the application needs forwarded headers:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Configure the trusted proxy to **strip client-supplied forwarded headers** and inject the authoritative values; the backend must not be exposed directly if the application trusts these headers.

### 14.3. What to Verify After Deployment

1. Call the metadata URL externally over real DNS/TLS.
2. Verify `issuer` is the expected public URL.
3. Verify all endpoint URLs use the correct HTTPS scheme, host, and path.
4. Verify `jwks_uri` actually returns public keys.
5. Use a client configured with the public issuer to obtain a token.
6. Inspect JWT `iss` (and ID token `iss` if OIDC).
7. Have the Resource Server decode the token and validate issuer/audience.
8. Test against forwarded-header spoofing and ensure the backend cannot be accessed bypassing the proxy.

A metadata endpoint returning HTTP 200 while advertising internal URLs is still a serious operational defect.

### 14.4. Multi-Tenant and Multiple Issuers

If each tenant has its own issuer:

~~~text
https://auth.example.test/tenant/a
https://auth.example.test/tenant/b
~~~

Each tenant must have its own RFC 8414 metadata URL, its own `issuer`, and consistent endpoint/token policies.

Do not let tenant A fetch tenant B's metadata or accept JWTs with tenant B's `iss` simply because they share a signing key. Isolate trust/registration/authorization and test request routing per issuer path.

Default SAS framework setups are typically configured for a single issuer per application context; multiple issuers/paths may require additional routing/configuration. Do not claim that merely mutating `AuthorizationServerSettings` per request is sufficient for safe multi-issuer support.

## 15. Caching, Versioning, and Backward Compatibility

### 15.1. Metadata Is Public Configuration and Can Be Cached Under Control

Client SDKs can cache discovery JSON to avoid calling the AS on every OAuth2 flow. Proxies/CDNs may also cache responses if policy permits.

Caching requires balance:

| Policy | Advantage | Risk |
| --- | --- | --- |
| Short TTL | Propagates endpoint/capability updates quickly | More GET requests, higher load |
| Moderate TTL | Reduces latency/load | Stale window during configuration changes |
| Very long TTL | Minimal requests | Clients miss new endpoints/auth methods; slow migrations |
| ETag/conditional GET | Reduces payload if supported | Requires proper cache revalidation handling |

There is no single mandatory TTL for every deployment. Choose a TTL based on how often issuers/endpoints change and rollback requirements.

### 15.2. Advertising Breaking Capability Changes Can Break Clients

Examples:

- Disabling `client_secret_basic` before older clients support `private_key_jwt`.
- Changing `token_endpoint` while clients still have the old URL cached.
- Moving `jwks_uri` before Resource Servers refresh metadata.
- Retiring a grant while metadata still lists it.
- Changing the issuer while clients/RS only trust the old issuer.
- Changing `code_challenge_methods_supported` when clients hardcode `plain`.

When making changes:

1. Inventory consumers and SDK versions.
2. Publish metadata matching actual behavior.
3. Provide a compatibility window for old endpoints if policy permits.
4. Account for the maximum metadata cache TTL.
5. Monitor requests to old endpoints and 4xx errors.
6. Update client onboarding docs and integration tests.
7. Never retain weak capabilities solely due to metadata caching if doing so violates security policy.

### 15.3. Metadata Alone Does Not Solve Key Rotation

If `jwks_uri` stays unchanged, new keys can be published in the JWKS without changing metadata. However, Resource Servers still need to refresh JWKS when encountering a new `kid` or upon cache expiration.

Keep the previous public key in the JWKS long enough for unexpired tokens to be verified under the key rollover policy. Do not remove the old key simply because metadata JSON was updated.

## 16. How Clients Consume RFC 8414

### 16.1. Safe Discovery Workflow

An OAuth2 Client that knows a trusted issuer:

1. Construct the well-known metadata URL per RFC 8414.
2. Send an HTTPS GET.
3. Verify HTTP status 200 and `Content-Type: application/json`.
4. Parse the JSON object and validate that required fields have the expected types.
5. Verify exact-match between `issuer` and the input issuer.
6. Verify endpoint URLs satisfy HTTPS/trust policy.
7. Select a grant/response type/client auth method allowed by **both the server and the client registration**.
8. Fetch `jwks_uri` if JWT verification is needed.
9. Cache metadata per policy and refresh upon changes.
10. Execute Authorization Code + PKCE, Client Credentials, Device Code, etc. according to the actually supported grant.

### 16.2. Client Pseudocode Example

~~~java
// PSEUDOCODE — not directly compilable Spring API.
String trustedIssuer = "https://auth.example.test";

URI metadataUri = deriveRfc8414WellKnownUri(trustedIssuer);
JsonObject metadata = httpGetJsonOverVerifiedTls(metadataUri);

if (!trustedIssuer.equals(metadata.getString("issuer"))) {
    throw new SecurityException("Authorization Server issuer mismatch");
}

URI tokenEndpoint = validateTrustedHttpsEndpoint(
    metadata.getString("token_endpoint"));

List<String> supportedGrants =
    metadata.getStringList("grant_types_supported");

if (!supportedGrants.contains("authorization_code")) {
    throw new IllegalStateException(
        "Authorization Code flow not advertised");
}

// Continue checking client registration, PKCE support, and
// send protocol requests; never skip client authentication.
~~~

`deriveRfc8414WellKnownUri` and `validateTrustedHttpsEndpoint` are implemented by the application/SDK. For servers that omit `grant_types_supported`, RFC 8414 defines historical defaults, so real clients must parse according to profile/version rather than using this pseudocode verbatim.

### 16.3. Spring Security OAuth2 Client

In Spring Boot, OIDC client configuration commonly uses the issuer:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          booking:
            provider: booking-provider
            client-id: booking-client
            client-secret: __CLIENT_SECRET_FROM_SECRET_MANAGER__
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          booking-provider:
            issuer-uri: https://auth.example.test
~~~

**Distinction:** When configuring `issuer-uri` with OIDC scopes, Spring Security OAuth2 Client may use **OIDC Discovery** (`openid-configuration`) per its implementation, which does not by default prove the SDK fetched `/.well-known/oauth-authorization-server` per RFC 8414. If you only need OAuth2 RFC 8414 without enabling OIDC, check your client SDK's capability/version and configure appropriate endpoint URLs.

This example only illustrates client registration; `__CLIENT_SECRET_FROM_SECRET_MANAGER__` is a placeholder—never put production secrets in public source/config. Do not use the `openid` scope if the AS has not enabled OIDC.

### 16.4. Resource Server Using Issuer Discovery

Spring Boot Resource Server is typically configured as:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Configuring the issuer allows the framework to locate the JWK Set URI via appropriate discovery and create a validator for `iss`. If you choose to configure `jwk-set-uri` directly to avoid a startup discovery dependency, ensure an issuer validator is still applied.

**Do not assume `issuer-uri` automatically validates audience for every API.** Configure an audience validator per Spring Security version/policy; the Resource Server must still enforce scopes and business authorization.

## 17. Testing the Metadata Endpoint

### 17.1. Public HTTP Check

~~~bash
curl --fail --silent --show-error \
  --header "Accept: application/json" \
  https://auth.example.test/.well-known/oauth-authorization-server
~~~

Expected:

- HTTP 200.
- Content-Type JSON.
- Correct `issuer`.
- `response_types_supported` and applicable endpoint URLs present.
- No redirect to `/login`.
- No internal hosts, private keys, or client secrets.

### 17.2. Quick Inspection with jq

~~~bash
curl --silent --show-error \
  https://auth.example.test/.well-known/oauth-authorization-server \
  | jq '{
      issuer,
      authorization_endpoint,
      token_endpoint,
      jwks_uri,
      response_types_supported,
      grant_types_supported,
      code_challenge_methods_supported
    }'
~~~

Do not rely solely on `jq` output looking neat; test the schema, exact issuer match, endpoint reachability, and actual protocol flow.

### 17.3. MockMvc Integration Test

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class AuthorizationServerMetadataTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void oauthMetadataIsPublicAndConsistent() throws Exception {
        mockMvc.perform(get("/.well-known/oauth-authorization-server"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                .value("https://auth.example.test"))
            .andExpect(jsonPath("$.token_endpoint")
                .value("https://auth.example.test/oauth2/token"))
            .andExpect(jsonPath("$.response_types_supported").isArray());
    }
}
~~~

This is the **core test body**; the test class needs `@SpringBootTest` and `@AutoConfigureMockMvc` or an equivalent test setup to load the real AS `SecurityFilterChain`. If the issuer is resolved from request/proxy headers in test configuration, set the host/scheme or provide an explicit issuer bean for the fixture.

### 17.4. Testing `jwks_uri`

If metadata includes `jwks_uri`:

1. Fetch via HTTPS GET.
2. Parse the JWK Set containing a `keys` array.
3. Confirm signing JWKs have public key material and an appropriate `kid`.
4. Confirm no private key parameters such as RSA `d`, `p`, `q` are present.
5. Issue a JWT from an AS test fixture and verify its signature against the published key.
6. Verify issuer/audience/expiry after decoding the JWT.
7. Test key rotation with overlap and consumer JWKS refresh.

Without a `JWKSource<SecurityContext>` bean, SAS does not configure a JWK Set Endpoint by default; never hardcode a fake `jwks_uri` in metadata.

### 17.5. Test Matrix

| Case | Input/Setup | Expected |
| --- | --- | --- |
| Basic discovery | GET valid well-known | 200 JSON |
| Anonymous discovery | No cookie/token | No login redirect |
| Issuer exact match | Trusted issuer = response issuer | Client accepts metadata |
| Issuer mismatch | Response issuer differs | Client rejects |
| Issuer with path | `/tenant/a` | Well-known placed before issuer path |
| Internal host leak | HTTP backend proxy | Metadata does not expose internal host |
| Endpoint reachable | token/authorization/introspection URLs | Correct routing/policy |
| PKCE metadata | AS supports S256 | `code_challenge_methods_supported` includes S256 |
| Capability mismatch | Metadata advertises unsupported grant | Test fails |
| Client permission | AS supports grant but client lacks registration | Client is still denied the grant |
| JWK Set | `jwks_uri` present | Public keys only; JWT verifies |
| JWK Set disabled | No JWKSource | No fake key endpoint advertised |
| OIDC disabled | OAuth2 metadata active | Do not assume OIDC provider config |
| OIDC enabled | `OidcConfigurer` active | OIDC config works separately |
| Metadata caching | CDN holds stale version | Refresh/TTL compatible with rollout |
| Wrong content type | HTML/redirect | Client refuses to parse as JSON |
| SSRF input | User-supplied issuer outside allowlist | Does not fetch untrusted address |
| Multi-instance | Multiple AS pods | Consistent metadata |
| Multi-tenant | Distinct issuers A/B | No issuer/metadata mixing |
| Unknown extension | New field unknown to client | Client handles per profile; does not auto-grant permissions |
| Signing metadata | Optional `signed_metadata` | Trust only when verified against signer/contract |

### 17.6. End-to-End Test with a Real Client

An integration test is more valuable than just comparing JSON:

1. Fetch metadata over public HTTPS.
2. Select the Authorization Endpoint from metadata.
3. Start Authorization Code + PKCE with a registered client.
4. Exchange the code at the Token Endpoint from metadata.
5. If needed, fetch JWKS from `jwks_uri` and verify the access token/ID token.
6. Send the token to the RS and verify issuer/audience/scopes.
7. Change the endpoint address in a test profile and verify the client adapts per policy.

Do not use `@WithMockUser` to claim client metadata authentication works: metadata does not require Resource Owner login anyway. Run HTTP tests through the real filter chain/proxy.

## 18. Operations and Troubleshooting

### 18.1. Common Errors

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| GET well-known returns 404 | Wrong path, AS chain does not match, wrong proxy rewrite | Routing/filter chain/issuer path |
| GET well-known returns 302 /login | Application chain matched first, wrong security rule | `@Order`, matcher, and filters |
| JSON `issuer` is localhost | Issuer not configured or wrong forwarded headers | `AuthorizationServerSettings.issuer` |
| JSON endpoint uses internal HTTP | Proxy terminates TLS while AS builds internal URL | Issuer, proxy trust, public URL |
| Client reports issuer mismatch | Metadata issuer differs from pinned issuer | Exact string comparison, scheme/host/path |
| Client reports invalid metadata | Missing required field, wrong JSON type | RFC schema and customizer |
| Client picks unusable grant | Metadata advertises server-wide capability missing on client registration | RegisteredClient/grant policy |
| Client POSTs to wrong Token Endpoint | Endpoint from metadata unreachable/misrouted | External URL, DNS, TLS |
| Resource Server fails to load keys | Missing `jwks_uri`, missing JWKSource bean, network error | JWK endpoint/JWT decoder |
| RS 401 despite right key | JWT issuer/audience/expiry invalid | JwtDecoder validators |
| OIDC client fails while OAuth2 metadata OK | OIDC config disabled or different path | `OidcConfigurer`/openid-configuration |
| Only tenant B fails discovery | Tenant B path insertion/routing incorrect | RFC 8414 URL per issuer |
| Metadata has registration URL but 404 | Advertised endpoint not enabled | Dynamic registration config |
| Stale metadata after deploy | CDN/client cache TTL too long | Cache-Control/ETag/purge/SDK refresh |
| OAuth2 client vulnerable to SSRF | Unrestricted issuer URL | Issuer allowlist/trust/onboarding |
| Metadata differs across instances | Inconsistent config, rolling deployment | Issuer/settings consistency |

### 18.2. Ordered Diagnostic Runbook

1. Identify the trusted issuer used by the client/RS.
2. Construct the exact well-known URL per RFC 8414.
3. Call the URL over real DNS/TLS/public proxy.
4. Verify HTTP 200, Content-Type, JSON, and exact `issuer` match.
5. Inspect endpoint URLs, grant types, PKCE, auth methods, and JWKS.
6. Inspect the AS `SecurityFilterChain` and `AuthorizationServerSettings`.
7. Check OIDC Discovery separately if the client requests `openid`.
8. Check local/CDN cache and rollout status.
9. Run a real OAuth2 request through the advertised endpoints.
10. If the RS rejects tokens, diagnose JWT signature/issuer/audience/expiry and client authorization independently.

### 18.3. Metrics and Alerts

| Metric | Detects |
| --- | --- |
| Metadata GET volume/latency | Discovery load, proxy failure |
| Metadata 4xx/5xx | Misrouting, availability issues |
| Metadata issuer mismatch in client integrations | Misconfigured security identity |
| Client startup discovery failures | Startup dependency/DNS/TLS issues |
| JWKS GET/refresh failures | Key distribution errors |
| Endpoint 404 after metadata success | Capability/URL mismatch |
| OIDC discovery errors | OIDC activation/path mismatch |
| Multi-instance metadata drift | Inconsistent deployment/settings |
| CDN Age and metadata cache refresh | Stale configuration |

Do not log client secrets, access tokens, or raw authorization headers in logs/metrics. Metadata is public information, yet `issuer` and endpoint URLs must still be governed by change management.

## 19. Design Mistakes to Avoid

| Mistake | Consequence | Right Principle |
| --- | --- | --- |
| Guessing issuer from Token Endpoint | Breaks with multi-tenant/proxy setups | Issuer must come from trusted config |
| Skipping `issuer` check after discovery | AS mix-up/metadata injection | Exact-match per RFC 8414 |
| Appending `issuer + "/.well-known/..."` when issuer has a path | Wrong well-known URL | Insert suffix between host and issuer path |
| Confusing OAuth2 metadata with OIDC config | Client login/ID token fails | Use the right profile; enable OIDC when needed |
| Embedding JWKS inside metadata | Key exposure or contract violation | Metadata holds `jwks_uri`; JWKS holds public keys |
| Publishing private JWK | Signing key compromise | Publish public keys only |
| Publishing unenabled `registration_endpoint` | Clients get 404 or security bugs | Metadata reflects real endpoints |
| Advertising a grant without a provider | Clients call unsupported grant | Verify implementation/capabilities |
| Treating `grant_types_supported` as permission for every client | Bypasses RegisteredClient policy | Client registration still controls permissions |
| Omitting PKCE S256 when supported | Client SDKs misconfigure | Align metadata with protocol |
| Using HTTP/internal host in production | Broken trust/issuer and client failures | Fixed public HTTPS issuer |
| Trusting forwarded headers from the internet | Host/issuer poisoning | Trusted proxy strips/sets headers |
| Fetching arbitrary user-supplied issuers | SSRF/credential leak | Issuer allowlist or controlled onboarding |
| Treating metadata as authorization | Skips client authentication/consent | Metadata only describes capabilities |
| Changing issuer without migrating clients/RS | JWT `iss` mismatch, login failure | Plan issuer migration |
| Caching metadata indefinitely | Old endpoints/capabilities persist | TTL, revalidation, and rollout plan |
| Assuming `signed_metadata` is always present | Client incompatibility | Optional, with explicit trust model |
| Testing only HTTP 200 | Metadata may have wrong issuer/URLs | Validate schema, HTTPS, issuer, and real flow |

## 20. Self-Check Questions

**Question 1.** What is RFC 8414 used for?

**Answer:** Publishing standard JSON metadata so an OAuth2 Client can discover endpoint URLs and capabilities of an Authorization Server bound to a trusted issuer.

**Question 2.** What metadata URL does issuer `https://auth.example.test/tenant/a` have under RFC 8414?

**Answer:** `https://auth.example.test/.well-known/oauth-authorization-server/tenant/a`, not with the suffix placed after the tenant path.

**Question 3.** Why must `issuer` be exact-matched after fetching metadata?

**Answer:** To avoid using metadata from another AS, reducing the risk of authorization server mix-up and sending credentials or authorization codes to the wrong target.

**Question 4.** Does `grant_types_supported` allow every RegisteredClient to use all listed grants?

**Answer:** No. Those are server capabilities. Each client is still governed by `RegisteredClient.authorizationGrantTypes` and its specific policy.

**Question 5.** Do `jwks_uri` and `issuer` serve the same role?

**Answer:** No. `issuer` is the AS identifier; `jwks_uri` is the URL for fetching public keys to verify JWTs. Public keys do not replace issuer validation.

**Question 6.** Does RFC 8414 require `jwks_uri`?

**Answer:** No, `jwks_uri` is OPTIONAL in RFC 8414 itself; profiles like OIDC and JWT validation requirements impose their own rules.

**Question 7.** If `grant_types_supported` is omitted, what is the RFC 8414 default?

**Answer:** `authorization_code` and `implicit` are the historical defaults per the RFC. Do not enable `implicit` in new systems because of that.

**Question 8.** Should you customize metadata by writing a new controller?

**Answer:** Spring Authorization Server already provides `OAuth2AuthorizationServerMetadataEndpointConfigurer` and customizers. Use the DSL/builder to keep metadata synchronized instead of creating a parallel controller.

**Question 9.** Are the OAuth2 Metadata Endpoint and OIDC Provider Configuration Endpoint enabled together automatically?

**Answer:** No. SAS enables OAuth2 metadata with Authorization Server configuration, whereas OIDC is disabled by default and must be enabled separately.

**Question 10.** Why can a reverse proxy cause wrong metadata even if the endpoint returns 200?

**Answer:** If issuer/endpoint URLs are built from an internal HTTP host/scheme or untrusted forwarded headers, the JSON can advertise incorrect URLs.

**Question 11.** Are the metadata cache and JWKS cache the same thing?

**Answer:** No. Metadata contains endpoint/key-set URIs; JWKS contains public keys. Both have independent TTLs and refresh cycles.

**Question 12.** Should clients fetch metadata from an arbitrary user-supplied issuer?

**Answer:** Not without a trust/onboarding policy, due to SSRF, endpoint injection, and credential leak risks; enforce an allowlist/validation/TLS/exact issuer match.

## 21. Production Deployment Checklist

- [ ] Stable HTTPS issuer with no query/fragment, matching the AS identity.
- [ ] Well-known URL constructed per RFC 8414, including issuers with paths.
- [ ] Metadata GET returns HTTP 200, `application/json`, with no login redirect.
- [ ] `issuer` in JSON matches the trusted issuer exactly.
- [ ] Published endpoint URLs are real, working public HTTPS URLs.
- [ ] `response_types_supported` and profile-required fields are complete.
- [ ] `grant_types_supported`, client auth methods, and PKCE reflect actual implementation.
- [ ] `scopes_supported` is not mistaken as permission for every client.
- [ ] `jwks_uri` serves a public JWK Set without leaking private keys.
- [ ] JWK Set endpoint is only advertised when corresponding keys are configured.
- [ ] OIDC Provider Configuration is enabled separately if using OIDC; do not confuse the two URLs.
- [ ] Dynamic Client Registration is advertised only when actually enabled.
- [ ] PAR/Device/DPoP/mTLS metadata are advertised only if those features are active.
- [ ] `AuthorizationServerSettings` is configured with accurate issuer/endpoint paths.
- [ ] AS `SecurityFilterChain` captures metadata requests properly before the application chain.
- [ ] Proxy strips untrusted forwarded headers and preserves external HTTPS URLs.
- [ ] Cache TTL, refresh, rollout, and rollback plans exist for endpoint/capability changes.
- [ ] Tests cover exact issuer match, well-known path, JSON fields, JWKS, OIDC, and end-to-end flows.
- [ ] External issuer inputs are constrained to prevent SSRF and mix-up attacks.
- [ ] Monitoring exists for discovery failures, issuer mismatch, endpoint 404s, and cache drift.
- [ ] Metadata discovery is never confused with client authentication or authorization.

## 22. References and Conclusion

Official and normative references:

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8414, Section 2 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-2)
- [RFC 8414, Section 3 — Obtaining Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-3)
- [RFC 8414, Section 3.3 — Metadata Validation](https://www.rfc-editor.org/rfc/rfc8414#section-3.3)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9126 — Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126)
- [RFC 9449 — Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)

**Conclusion:** RFC 8414 standardizes how an OAuth2 Client discovers an Authorization Server's issuer, endpoint URLs, and capabilities via JSON at a well-known URL. Its most important security value is **a consistent and strictly verified issuer**, not just reducing hardcoded URLs. In Spring Authorization Server, `AuthorizationServerSettings` defines the issuer/endpoints and `OAuth2AuthorizationServerMetadataEndpointConfigurer` customizes the response. In real-world deployments, discovery must be coordinated with HTTPS, reverse proxies, client registration, JWKS, OIDC profiles, metadata caching, and integration tests. Accurate metadata makes client integration smoother without weakening OAuth 2.0/OpenID Connect authentication and authorization requirements.
