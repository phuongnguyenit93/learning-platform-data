# Validating redirect_uris, grant_types, response_types, and Authentication Methods

## 1. Context and Objectives

In the **Dynamic Client Registration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson focuses on the most critical step when onboarding a new client: **validating the metadata submitted by the client before turning that metadata into a RegisteredClient authorized to participate in OAuth 2.0/OpenID Connect**.

The module aims to teach how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. Dynamic Client Registration (DCR) is a sensitive entry point because a registration request can create a new `client_id`, credentials, redirect URIs, and permission set in the system.

Suppose a partner sends a registration request:

~~~json
{
  "client_name": "Orders Partner Portal",
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile orders.read"
}
~~~

Before saving the client, the Authorization Server must answer:

1. Do the redirect URIs belong to a domain and application controlled by the partner?
2. Are the grant types on the list permitted by the server?
3. Are the response types compatible with the grant types and the endpoints the server actually supports?
4. Which authentication method does the client choose at the Token Endpoint? Does that method fit the client type and issued keys/secrets?
5. Are the scopes in the allowlist and within the permissions the registrar is authorized to grant?
6. Was the request sent by an authenticated registrar with permission to create clients?

A successful client registration does not merely mean valid JSON. It means the Authorization Server is accepting a **security contract** for future authorization and token requests.

After this lesson, you will be able to:

- Distinguish OAuth 2.0 Dynamic Client Registration under RFC 7591 from OpenID Connect Dynamic Client Registration.
- Validate `redirect_uris` using exact matching, distinguishing web clients from native clients.
- Validate `grant_types` and `response_types` using a compatibility matrix.
- Choose a `token_endpoint_auth_method` suitable for public/confidential clients.
- Build validators with allowlists for metadata and scopes.
- Enable the OIDC Client Registration Endpoint in Spring Authorization Server 1.5.x.
- Protect Initial Access Tokens, Registration Access Tokens, and the Client Configuration Endpoint.
- Test valid registrations, conflicting metadata, and redirect attacks.

## 2. What Is Dynamic Client Registration?

Dynamic Client Registration allows an OAuth Client or OpenID Connect Relying Party to send metadata to a Registration Endpoint to be issued a client identifier and required registration details. After registration, the client uses the approved metadata to interact with the Authorization Server.

Two specifications to distinguish:

| Standard | Scope |
| --- | --- |
| **RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol** | Defines the OAuth client registration protocol, metadata, requests/responses, and errors |
| **OpenID Connect Dynamic Client Registration 1.0** | Extends/describes how an OIDC RP registers with an OpenID Provider, with a Client Configuration Endpoint and OIDC metadata |
| **RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol** | Defines managing created registrations, including read/update/delete via a registration access token |

Spring Authorization Server 1.5.8 provides the **OpenID Connect 1.0 Client Registration Endpoint** per the OIDC DCR specification. Do not assume this endpoint implies every profile or DCR management feature of RFC 7591/7592 is supported identically.

### 2.1. General Workflow

~~~mermaid
sequenceDiagram
    autonumber
    participant Admin as Registrar / Client Developer
    participant AS as Authorization Server
    participant Repo as RegisteredClientRepository
    Admin->>AS: Request Initial Access Token
    AS-->>Admin: IAT with client.create permission
    Admin->>AS: POST Client Registration Request + Bearer IAT
    AS->>AS: Authenticate registrar and validate metadata
    AS->>AS: Generate client_id and credentials if applicable
    AS->>Repo: Save RegisteredClient
    Repo-->>AS: Saved
    AS-->>Admin: Client Registration Response + registration_access_token
    Admin->>AS: GET registration_client_uri + Bearer RAT
    AS-->>Admin: Client Configuration Response
~~~

Registrar authentication and metadata validation occur **before** writing `RegisteredClient`. Never accept client metadata and persist it first, leaving validation to happen later at the Authorization Endpoint.

### 2.2. Open Registration vs. Protected Registration

| Model | Characteristics | Risks |
| --- | --- | --- |
| Open Dynamic Registration | Any caller can register per policy | Client spam, malicious redirect URIs, scope abuse, resource exhaustion |
| Protected Dynamic Registration | Requires Initial Access Token, software statement, or authenticated onboarding flow | Must manage issuance, expiration, and revocation of registrar permissions |
| Admin-mediated registration | Developer submits metadata, then admin/automation approves | Adds an operational step, but controls domains, owners, and grants |

In production systems, do not open unauthenticated registration simply because the endpoint exists. Use protected registration and scope registrar permissions by organization/tenant.

## 3. Four Core Metadata Groups

### 3.1. redirect_uris

`redirect_uris` is the list of URIs to which the Authorization Server is permitted to redirect the browser after authorization. This metadata directly governs where an Authorization Code or Authorization Response is sent.

Example:

~~~json
{
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ]
}
~~~

Points that must be validated:

- At least one redirect URI is present if the client uses a redirect-based flow.
- URIs have valid schemes and contain no fragment.
- Web clients use HTTPS.
- Native clients use claimed HTTPS URIs, suitable custom schemes, or loopback redirects per RFC 8252.
- Arbitrary wildcards/patterns are rejected.
- Domains/paths must be verified per onboarding policy.
- The Authorization Endpoint must compare the request's `redirect_uri` against registered URIs using exact string matching, except for the port on native app loopback URIs per the specification.

### 3.2. grant_types

`grant_types` is the list of OAuth grants the client declares it will use at the Token Endpoint.

Example:

~~~json
{
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ]
}
~~~

Do not accept a grant just because the string exists in an RFC. The Authorization Server should only grant grant types that it has implemented, configured, and permitted under the registrar's policy. RFC 9700 recommends against using the Implicit Grant and Resource Owner Password Credentials Grant.

### 3.3. response_types

`response_types` are the `response_type` values the client declares it will use at the Authorization Endpoint.

Example:

~~~json
{
  "response_types": [
    "code"
  ]
}
~~~

For the Authorization Code Flow, `response_type` is `code` and the corresponding grant is `authorization_code`. Clients must not register response types that the Authorization Endpoint does not support.

### 3.4. token_endpoint_auth_method

`token_endpoint_auth_method` specifies how the client authenticates at the Token Endpoint.

Common OIDC Registration 1.0 values:

- `client_secret_basic`
- `client_secret_post`
- `client_secret_jwt`
- `private_key_jwt`
- `none`

Extended methods such as `tls_client_auth` or `self_signed_tls_client_auth` should only be accepted when the Authorization Server has explicitly implemented and configured support for them.

**Do not treat authentication method as a display attribute.** It determines whether the client proves its identity with a secret, a private key, a certificate, or no client credential at all.

## 4. Validating redirect_uris Safely

### 4.1. Exact Matching Is the Default

When an Authorization Request arrives:

~~~text
redirect_uri=https://portal.example.com/oauth/callback
~~~

that value must match a registered URI using simple string comparison rules. Never replace exact matching with loose checks like:

~~~text
startsWith("https://portal.example.com")
contains("portal.example.com")
endsWith("example.com")
~~~

Such approaches can accept malicious URIs:

| Malicious URI | Why loose checks fail |
| --- | --- |
| https://portal.example.com.attacker.invalid/callback | The actual host is `attacker.invalid` |
| https://portal.example.com@attacker.invalid/callback | Userinfo tricks readers about the host |
| https://attacker.invalid/?next=https://portal.example.com | An open redirect may exist on another endpoint |
| https://portal.example.com.evil/callback | Domain only shares a prefix with the valid domain |

RFC 9700 requires the Authorization Server to use exact matching, except for the port of localhost/loopback redirect URIs for native apps per RFC 8252.

### 4.2. URIs Without Fragments

Registered redirect URIs must not contain a fragment. The following example must be rejected:

~~~text
https://portal.example.com/callback#token
~~~

Fragments are not normally sent to servers and can introduce discrepancies in how browsers, proxies, and servers interpret responses. Spring Authorization Server provides `DEFAULT_REDIRECT_URI_VALIDATOR` to reject URIs containing fragments, missing schemes, or dangerous schemes.

### 4.3. Web Clients

For web clients, common policy:

- Use HTTPS only.
- Domains must be on an allowlist or have verified ownership.
- Reject arbitrary public IPs unless explicitly approved.
- Never use host/path wildcards.
- Never allow the redirect endpoint to act as an open redirector.
- Register specific callback paths rather than an entire domain.

Example:

~~~text
https://portal.example.com/oauth/callback
https://portal.example.com/login/oauth2/code/partner
~~~

Do not register:

~~~text
https://portal.example.com/*
https://*.example.com/oauth/callback
~~~

### 4.4. Native Applications

RFC 8252 defines redirect URI options for native apps:

| Type | Example | Notes |
| --- | --- | --- |
| Claimed HTTPS URI | https://app.example.com/oauth2redirect/provider | The OS can route the URI to the app that claimed the domain |
| Private-use custom scheme | com.example.app:/oauth2redirect/provider | Scheme should use reverse-domain notation to reduce collisions |
| Loopback IPv4 | http://127.0.0.1:51004/oauth2redirect/provider | Authorization Server must allow dynamic ports per RFC 8252 |
| Loopback IPv6 | http://[::1]:61023/oauth2redirect/provider | Listens on the loopback interface only |

Native clients are public clients in most cases; never embed a client secret into mobile/desktop apps since users can extract it. Authorization Code + PKCE is the appropriate flow.

**The dynamic port exception applies only to native app loopback URIs.** Do not apply this exception to web callbacks or custom scheme URIs.

Note when using **OIDC Dynamic Client Registration 1.0**: the `application_type=native` metadata requires redirect URIs to use a private-use custom scheme or an HTTP loopback URL per OIDC Registration rules. RFC 8252 also describes claimed HTTPS URIs for native apps; if you want to use this form, verify that the OP supports the corresponding profile/extension rather than assuming every OIDC DCR endpoint accepts it.

### 4.5. Do Not Accept Arbitrary localhost by Default

RFC 8252 notes that loopback IP literals such as `127.0.0.1` or `[::1]` are the clearest choice; using the `localhost` hostname is discouraged because resolution and binding behavior can be inconsistent. If policy permits `localhost`, restrict it to `application_type=native` and validate the rest of the URI.

### 4.6. Redirect URIs Must Be Validated at Both Registration Time and Authorization Time

Validation at registration time does not replace validation when an Authorization Request arrives. When a live request sends `redirect_uri`, the server must still compare it against the registered URI set for that exact `client_id`. Never take a new URI from a query parameter and automatically add it to the registration.

## 5. Validating grant_types

### 5.1. The Grant List Is Not a List of Grants the Server Must Support

RFC 7591 defines common OAuth grants; OIDC Dynamic Client Registration lists only the OIDC-specific grant set. Distinguish the metadata of the two profiles:

| grant_type | Profile/Source | Purpose and Policy |
| --- | --- | --- |
| authorization_code | RFC 7591 and OIDC DCR | Exchanges an Authorization Code for tokens; PKCE recommended |
| refresh_token | RFC 7591 and OIDC DCR | Exchanges a Refresh Token; requires rotation/reuse protection per policy |
| implicit | RFC 7591 and OIDC DCR | Returns tokens/ID Token via the Authorization Endpoint; not recommended for new systems |
| client_credentials | RFC 7591 | Machine-to-machine; only for confidential clients able to authenticate |
| password | RFC 7591 | Resource Owner Password Credentials; RFC 9700 requires not using this grant |
| JWT/SAML bearer | RFC 7591 extension grant | Allow only if the server has a dedicated implementation and policy |
| device_code | RFC 8628 extension grant | Allow only when the server has enabled the Device Authorization Grant |

OIDC DCR 1.0 lists `authorization_code`, `implicit`, and `refresh_token` in the `grant_types` metadata. `client_credentials`, `password`, JWT/SAML bearer, and Device Authorization belong to general OAuth DCR or extensions; do not assume Spring Authorization Server's OIDC Client Registration Endpoint supports them just because `RegisteredClient` can represent those grants.

### 5.2. Checking Grants Against Client Type

| Client Type | Common Suitable Grants | Constraints |
| --- | --- | --- |
| Web confidential | `authorization_code`, `refresh_token` | Client authentication at the Token Endpoint; PKCE should still be enabled |
| SPA public | `authorization_code` | PKCE mandatory; no client secret |
| Native mobile/desktop | `authorization_code`, `refresh_token` | PKCE; redirects per RFC 8252 |
| Backend service | `client_credentials` in general OAuth DCR or a separate admin workflow | Confidential client authentication; no user redirect flow |
| Device client | `urn:ietf:params:oauth:grant-type:device_code` or implementation value | Requires a Device Authorization Endpoint |

Do not let public clients use `client_credentials` as a substitute for client authentication. This grant is intended for confidential clients.

Spring Authorization Server 1.5.8 provides the OIDC Client Registration Endpoint. If you need to register machine-to-machine clients with `client_credentials`, verify the metadata profile supported by your endpoint or use a dedicated admin workflow/API; do not assume general OAuth DCR examples are compatible OIDC DCR requests.

### 5.3. Scopes and Grants Must Follow the Same Policy

Clients may only register scopes in an allowlist appropriate to the application/tenant. Registering a scope does not mean that scope is granted for every authorization; the Authorization Server still evaluates consent, client policy, and user authorization when issuing tokens.

For example, a web portal might be allowed:

~~~text
openid
profile
orders.read
~~~

But must not self-register:

~~~text
admin
system.write
tenant.impersonate
~~~

if the registrar does not have authority to grant those scopes.

## 6. Validating response_types

### 6.1. Response Types and Grant Types Live at Two Different Endpoints

- `response_types` restricts the `response_type` parameter at the Authorization Endpoint.
- `grant_types` restricts the `grant_type` parameter at the Token Endpoint.

The two fields are related but not interchangeable.

### 6.2. Compatibility Matrix per OIDC Dynamic Client Registration

| response_type | Required grant_types |
| --- | --- |
| code | authorization_code |
| id_token | implicit |
| id_token token | implicit |
| code id_token | authorization_code, implicit |
| code token | authorization_code, implicit |
| code id_token token | authorization_code, implicit |

In OIDC DCR 1.0, the table above is the mandatory relationship between the response type declared by the RP and the required grant types. The standalone `token` value belongs to the general RFC 7591 OAuth Implicit response type table, not a row in this OIDC DCR response type table.

General RFC 7591 specifies the OAuth relationship as follows:

| grant_types contains | response_types must include |
| --- | --- |
| authorization_code | code |
| implicit | token |
| password | No response type required |
| client_credentials | No response type required |
| refresh_token | No response type required |
| JWT bearer / SAML bearer | No response type required |

Extension grants/responses must define their own corresponding relationships. Therefore, validators must enforce the exact profile being deployed rather than mixing the two tables.

The Authorization Server should reject inconsistent registrations rather than silently rewriting metadata. For example:

~~~json
{
  "grant_types": ["client_credentials"],
  "response_types": ["code"]
}
~~~

This is an invalid registration because the client declares `response_type` `code` without having the `authorization_code` grant.

### 6.3. Authorization Code Flow

For the Authorization Code Flow:

~~~json
{
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ]
}
~~~

`refresh_token` does not introduce a separate `response_type`. It allows the client to exchange a Refresh Token at the Token Endpoint after having been issued a Refresh Token per policy.

### 6.4. The Server Must Restrict to Actually Supported Response Types

A registration with `response_types=code` does not mean the server automatically supports hybrid/implicit flows. If the Authorization Server only supports `code`, allowlist only `code`. Do not advertise or accept response types that have no corresponding handler.

RFC 9700 recommends using Authorization Code instead of response types that return Access Tokens directly from the Authorization Endpoint. Implicit Flow and Password Grant should not be enabled for new systems.

## 7. Validating token_endpoint_auth_method

### 7.1. Meaning of Each Method

| Method | Client proves identity with | Client Type |
| --- | --- | --- |
| client_secret_basic | Client ID and secret via HTTP Basic | Confidential |
| client_secret_post | Client ID and secret in form body | Confidential |
| client_secret_jwt | JWT signed with shared secret | Confidential |
| private_key_jwt | JWT signed with client's private key; server verifies via public key | Confidential |
| none | No client secret/authentication at the Token Endpoint | Public |
| tls_client_auth | X.509 client certificate via PKI | Confidential |
| self_signed_tls_client_auth | Pre-registered self-signed client certificate | Confidential |

TLS client authentication methods are extensions in the OAuth/OIDC client authentication method registry and require explicit server support.

`client_secret_post` can be used for compatibility, but consider the risk of secrets appearing in form bodies and request logs/tracing. Allow it only when clearly needed; prefer stronger or cleaner authentication methods like `client_secret_basic` or `private_key_jwt` when the architecture supports them.

### 7.2. Default Value

In OIDC Dynamic Client Registration, if `token_endpoint_auth_method` is omitted, the default is `client_secret_basic`. Registrars should not leave client type/auth method ambiguous; send an explicit value or apply the published default.

### 7.3. Public Clients Using none

`none` means the client has no client secret. SPA example:

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://spa.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "none"
}
~~~

Public clients cannot reliably keep a secret. The Authorization Server must require PKCE for the Authorization Code Flow and must not treat `client_id` as proof of authentication.

### 7.4. Confidential Clients

Web backend example:

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

The Authorization Server generates `client_id` and `client_secret` upon successful registration if the method requires a secret. The client secret may appear in both the Registration Response and Client Read Response metadata per OIDC DCR; do not assume only the first response contains this field. The registrar must protect the Registration Access Token and registration responses, store issued credentials in a secret manager, and never log them.

### 7.5. private_key_jwt and JWKS

If a client uses `private_key_jwt`, the server needs public keys to verify the JWT client assertion. The client can provide `jwks_uri` or a JWK Set per supported specification metadata.

Rules:

- `jwks_uri` must use HTTPS.
- If the client can provide `jwks_uri`, do not simultaneously send `jwks` by value; OIDC DCR specifies that these two metadata fields must not be used together and prefers `jwks_uri` to support key rotation.
- The JWK Set must contain only public key material.
- Reject private keys or symmetric secrets in public JWKS.
- Validate key type, `use`, `alg`, `kid`, and key suitability.
- Have key rotation and compromised-key handling procedures.
- For `client_secret_jwt` or `private_key_jwt`, if `token_endpoint_auth_signing_alg` is sent, accept only allowlisted algorithms; if omitted, apply the published default algorithm. Reject `alg=none`.

Do not fetch `jwks_uri` without controls. If the Authorization Server actively fetches this URL, defend against SSRF by validating scheme/host/IP, blocking private/link-local ranges, and limiting redirects, timeouts, response size, and DNS rebinding per your architecture.

### 7.6. Disallow Authentication Method Downgrades

A client registered with `private_key_jwt` or mTLS must not be switched to `none` or `client_secret_post` via an unapproved metadata request. Changing authentication methods requires authenticating the registration owner, validating new keys/secrets, and auditing.

## 8. Checking Consistency Across All Four Fields

A validator must check both individual fields and the relationships between them.

| redirect_uris | grant_types | response_types | token_endpoint_auth_method | Assessment |
| --- | --- | --- | --- | --- |
| Valid HTTPS callback | authorization_code | code | client_secret_basic | Valid for web confidential if policy allows |
| Valid HTTPS callback | authorization_code | code | none | Valid for public client if PKCE is enforced |
| Wildcard callback | authorization_code | code | client_secret_basic | Reject |
| HTTPS callback | client_credentials | code | client_secret_basic | Reject due to grant/response mismatch |
| No redirect URI | client_credentials | No response type | client_secret_basic | Potentially valid for machine client per policy |
| HTTPS callback | authorization_code | token | none | Reject if server does not support implicit |
| HTTPS callback | password | code | client_secret_post | Reject per modern security policy |
| HTTPS callback | authorization_code | code | none without PKCE required | Reject |

The `client_credentials` and `response_type` `token` rows illustrate general OAuth DCR rules under RFC 7591. For OIDC DCR, enforce the response/grant sets defined in OIDC Registration 1.0 and the OP's actual capabilities.

### 8.1. Validation by Client Profile

Do not write a single rule set for every client type. Define registration profiles:

**Web confidential profile**

- `application_type=web`.
- HTTPS Redirect URIs on the allowlist / verified domains.
- `grant_types` includes `authorization_code`, optionally `refresh_token`.
- `response_types` is `code` only.
- `token_endpoint_auth_method` is a server-supported confidential method.
- PKCE required per policy.

**SPA/native public profile**

- `application_type` matches application type.
- `token_endpoint_auth_method=none`.
- Authorization Code + PKCE.
- Redirect URIs per web/native rules.
- No client secret issued.
- Do not grant `client_credentials`.

**Machine-to-machine profile**

- `grant_types` only `client_credentials` or approved M2M grants.
- Confidential client authentication.
- Do not register redirect URIs if there is no authorization redirect flow.
- Do not require `response_type` `code`.
- Scopes include only required API permissions.

## 9. Spring Authorization Server 1.5.8 Support for Dynamic Client Registration

Spring Authorization Server 1.5.8 implements the **OpenID Connect 1.0 Client Registration Endpoint**. This endpoint is **disabled by default** because many deployments do not need dynamic registration.

Default endpoints:

~~~text
POST /connect/register
GET  {registration_client_uri}
~~~

The Client Registration Endpoint path can be changed with:

~~~java
AuthorizationServerSettings.builder()
        .oidcClientRegistrationEndpoint("/connect/register")
        .build();
~~~

This is the OIDC Client Registration Endpoint. Enable OIDC support and the Client Registration Endpoint explicitly; simply calling `oidc(Customizer.withDefaults())` is not enough to enable the client registration endpoint because it is disabled by default.

### 9.1. Enabling the Client Registration Endpoint

Configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(oidc ->
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
~~~

This is an illustrative filter chain snippet. A complete application still needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2TokenGenerator`, `JWKSource`, additional `SecurityFilterChain` beans, and appropriate authentication/authorization policies.

### 9.2. JwtDecoder Is a Required Bean for This Endpoint

Spring Authorization Server requires a `JwtDecoder` to verify the Initial Access Token sent as a Bearer token:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`JWKSource` must be configured with trusted signing keys. Do not use a decoder that skips signature/issuer verification just to get the registration endpoint working.

### 9.3. AuthorizationServerSettings

Endpoint configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .oidcClientRegistrationEndpoint("/connect/register")
                .build();
    }
}
~~~

If you change the path, update discovery metadata, ingress routing, the registrar `WebClient`, and integration tests.

## 10. Registrar Client and Initial Access Token

Spring Authorization Server uses a pre-registered client as a **registrar**. The registrar needs `client.create` to create new clients and may have `client.read` to query registrations depending on configuration.

Registrar example:

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("registration-service")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

This is an example; `passwordEncoder` and `registrarSecret` must come from a secret manager. Never use `{noop}` for production secrets.

### 10.1. Requesting an Initial Access Token

The registrar authenticates at the Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Per the Spring Authorization Server 1.5.8 guide, the Initial Access Token for a registration request must have only the `client.create` scope; if the token contains additional scopes, the registration request is rejected.

### 10.2. Initial Access Token vs. Registration Access Token

| Token | Used For | Scope |
| --- | --- | --- |
| Initial Access Token (IAT) | Authorizes the registrar to create clients | Pre-granted registration permission |
| Registration Access Token (RAT) | Accesses the Client Configuration Endpoint of a created client | Bound to a specific registration |
| Regular Access Token | Calls a Resource Server | Per granted scopes/resources |

In the Spring Authorization Server guide, the Initial Access Token is single-use; after the client is registered, that token is invalidated. The Registration Access Token is returned in the Client Registration Response and used to read the corresponding registration details.

### 10.3. Protecting the Registrar

- Grant `client.create` only to approved services/administrators.
- Never grant `client.create` to regular applications.
- Limit registration counts per tenant/registrar.
- Set short expiries on Initial Access Tokens.
- Support revoking/rotating registrar credentials.
- Audit which user or service created the client.
- Never write Bearer tokens to logs.

## 11. Sending a Client Registration Request

Registration request example for a web confidential client:

~~~http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer <initial-access-token>
Content-Type: application/json
Accept: application/json

{
  "client_name": "Orders Partner Portal",
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile orders.read"
}
~~~

If the metadata passes the authentication validator and provider checks, the server converts it into a `RegisteredClient` and stores it in `RegisteredClientRepository`.

### 11.1. Client Registration Response

The response may contain:

~~~json
{
  "client_id": "generated-client-id",
  "client_id_issued_at": 1794850000,
  "client_secret": "generated-secret",
  "client_secret_expires_at": 0,
  "client_name": "Orders Partner Portal",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "registration_access_token": "registration-management-token",
  "registration_client_uri": "https://login.example.com/connect/register/client-id"
}
~~~

This is an illustrative response; `client_id`, secrets, timestamps, and the registration URL are generated by the server. Do not hard-code or predict server-generated values. Because the response may include client credentials and a Registration Access Token, return it with a non-caching policy (e.g., `Cache-Control: no-store`) and never log the body.

### 11.2. Protecting the Client Secret in Both Registration and Client Read

For confidential clients using `client_secret_basic`, the Authorization Server generates a secret. The client must immediately store the issued credentials in a secret manager. Never write secrets into application logs, tickets, browser local storage, or source control.

Do not assume Client Read Responses always omit `client_secret`. OIDC Dynamic Client Registration 1.0 states the read response SHOULD contain the registered metadata; Spring Authorization Server 1.5.8 documentation also illustrates Client Read Responses containing `client_secret`. Therefore, the Registration Access Token and Client Configuration Endpoint must be protected as credentials capable of reading sensitive information. The secret value returned in a given implementation may reflect how the server stores/encodes secrets; check your converter and `PasswordEncoder` before assuming that string is usable directly as a credential.

If a secret is lost or suspected compromised, use your implemented rotation/re-registration or registration update workflow, then revoke old credentials and evaluate issued tokens.

### 11.3. Reading the Registration

When the server provides a Client Configuration Endpoint, the Registration Response returns both `registration_access_token` and `registration_client_uri`. OIDC DCR requires the server to provide both or neither. The registrar must use the exact URI provided by the server to read the registration rather than assembling a path or `client_id`:

~~~http
GET <registration-client-uri> HTTP/1.1
Authorization: Bearer <registration-access-token>
Accept: application/json
~~~

Spring Authorization Server requires the `client.read` scope for Client Read Requests per registrar configuration. Never use an Initial Access Token in place of a Registration Access Token to access a created registration.

## 12. Custom Metadata and Converters

RFC 7591 allows extending client metadata per registry/profile. Spring Authorization Server converts `OidcClientRegistration` into `RegisteredClient` and back via converters.

Built-in fields mapped into `RegisteredClient` include, for example:

- `client_id`
- `client_secret`
- `redirect_uris`
- `grant_types`
- `token_endpoint_auth_method`
- `scope`
- `jwks_uri`
- corresponding `ClientSettings`

If you want to store custom metadata such as `logo_uri`, `contacts`, `tenant_code`, or `onboarding_reference`, you must:

1. Specify the accepted metadata extensions.
2. Validate values and data provenance.
3. Use a `RegisteredClient` converter to persist them in `ClientSettings` or a dedicated metadata store.
4. Use a Client Registration converter to return the metadata when the client reads its registration.
5. Never automatically persist arbitrary claims of unknown origin into client settings.

Under RFC 7591, the Authorization Server MUST ignore unrecognized metadata. Only process extensions when the corresponding profile/registry is implemented; never blindly persist unknown fields from requests.

The Spring Authorization Server guide demonstrates custom converters on `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider`. Custom metadata is not preserved automatically unless converters map it.

## 13. Configuring Validators in Spring Authorization Server

### 13.1. Default Validators in Version 1.5.8

`OidcClientRegistrationAuthenticationValidator` provides the following validators:

| Validator | Purpose |
| --- | --- |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Rejects redirect URIs with fragments, missing schemes, or dangerous schemes |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Applies similar rules to post-logout redirect URIs |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Requires `jwks_uri` to use HTTPS |
| `DEFAULT_SCOPE_VALIDATOR` | Strict: rejects requests with non-empty scopes |
| `SIMPLE_REDIRECT_URI_VALIDATOR` | Preserves legacy fragment-only check; may accept dangerous values |
| `SIMPLE_JWK_SET_URI_VALIDATOR` | No URI validation; may open SSRF vectors |
| `SIMPLE_SCOPE_VALIDATOR` | Accepts any scope; may allow arbitrary scope injection |

Default validators do not replace an enterprise's full policy. In particular, you still need to check `grant_types`, `response_types`, `token_endpoint_auth_method`, `application_type`, redirect domain ownership, scope allowlists, and quotas.

**Never use `SIMPLE_SCOPE_VALIDATOR` alone in production.** If you need to accept scopes, write a custom allowlist validator. Likewise, never downgrade strict redirect/JWKS validators just for legacy data compatibility without assessing the risk.

### 13.2. Additional Validator for Web Authorization Code Clients

The example below illustrates a registration profile that permits only:

- Web redirect URIs in an exact allowlist.
- `authorization_code` and `refresh_token`.
- `response_type` `code`.
- `client_secret_basic` or `none`.
- Scopes in an allowlist.

This illustrative profile requires `scope` to be sent explicitly, even though OIDC DCR allows omitting `scope` and letting the OP apply defaults. Requiring explicit scopes helps avoid accidentally granting a broader default scope set than intended.

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;

final class WebClientRegistrationPolicy {

    private static final Set<String> APPROVED_REDIRECT_URIS = Set.of(
            "https://partner.example.com/oauth/callback",
            "https://portal.example.com/login/oauth2/code/partner"
    );

    private static final Set<String> ALLOWED_GRANTS = Set.of(
            "authorization_code",
            "refresh_token"
    );

    private static final Set<String> ALLOWED_RESPONSE_TYPES = Set.of("code");

    private static final Set<String> ALLOWED_AUTH_METHODS = Set.of(
            "client_secret_basic",
            "none"
    );

    private static final Set<String> ALLOWED_SCOPES = Set.of(
            "openid",
            "profile",
            "email",
            "orders.read"
    );

    static Consumer<OidcClientRegistrationAuthenticationContext> validator() {
        return context -> {
            OidcClientRegistrationAuthenticationToken authentication =
                    context.getAuthentication();
            OidcClientRegistration registration =
                    authentication.getClientRegistration();

            if (registration == null) {
                reject("Client registration metadata is missing");
            }

            String applicationType = registration.getClaimAsString("application_type");
            if (applicationType != null && !"web".equals(applicationType)) {
                reject("This registration profile only accepts web clients");
            }

            if (registration.getClientId() != null
                    || registration.getClientSecret() != null) {
                reject("client_id and client_secret are issued by the server");
            }

            if (registration.getJwkSetUrl() != null || registration.hasClaim("jwks")) {
                reject("This profile does not accept client JWKS metadata");
            }

            List<String> redirectUris = registration.getRedirectUris();
            if (redirectUris == null || redirectUris.isEmpty()
                    || new java.util.HashSet<>(redirectUris).size() != redirectUris.size()
                    || !APPROVED_REDIRECT_URIS.containsAll(redirectUris)) {
                reject("redirect_uris is not approved");
            }

            List<String> grantTypes = registration.getGrantTypes();
            if (grantTypes == null || grantTypes.isEmpty()) {
                // OIDC DCR defaults grant_types to authorization_code.
                grantTypes = List.of("authorization_code");
            }
            if (!grantTypes.contains("authorization_code")
                    || new java.util.HashSet<>(grantTypes).size() != grantTypes.size()
                    || !ALLOWED_GRANTS.containsAll(grantTypes)) {
                reject("grant_types is not allowed");
            }

            List<String> responseTypes = registration.getResponseTypes();
            if (responseTypes == null || responseTypes.isEmpty()) {
                // OIDC DCR defaults response_types to code.
                responseTypes = List.of("code");
            }
            if (!responseTypes.equals(List.of("code"))
                    || !ALLOWED_RESPONSE_TYPES.containsAll(responseTypes)) {
                reject("response_types is not supported");
            }

            String authMethod =
                    registration.getTokenEndpointAuthenticationMethod();
            if (authMethod == null) {
                // OIDC Dynamic Client Registration defaults to client_secret_basic.
                authMethod = "client_secret_basic";
            }
            if (!ALLOWED_AUTH_METHODS.contains(authMethod)) {
                reject("token_endpoint_auth_method is not allowed");
            }

            List<String> scopes = registration.getScopes();
            if (scopes == null || scopes.isEmpty()
                    || new java.util.HashSet<>(scopes).size() != scopes.size()
                    || !ALLOWED_SCOPES.containsAll(scopes)) {
                reject("scope is missing, duplicated, or outside the allowlist");
            }
        };
    }

    private static void reject(String description) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error("invalid_client_metadata", description, null));
    }

    private WebClientRegistrationPolicy() {
    }
}
~~~

This is a sample validator for a web profile with fixed redirect URIs, rejecting client JWKS, and allowing only `client_secret_basic` or `none`. Multi-customer systems must replace the static URI set with a domain ownership registry or appropriate approval workflow. Do not use this profile for native apps or machine-to-machine clients. If separating SPAs and web backends into two profiles, create dedicated validators so SPAs can register only `none`; `application_type=web` alone does not distinguish an SPA from a server-side web app.

### 13.3. Chaining Validators with Default Strict Validators

Provider configuration example:

~~~java
import java.util.List;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;

@Bean
Consumer<List<AuthenticationProvider>> registrationProviderCustomizer(
        PkceRegisteredClientConverter pkceRegisteredClientConverter) {
    return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
                Consumer<OidcClientRegistrationAuthenticationContext> validator =
                        OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
                                .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                                .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_JWK_SET_URI_VALIDATOR)
                                .andThen(WebClientRegistrationPolicy.validator());

                registrationProvider.setAuthenticationValidator(validator);
                // pkceRegisteredClientConverter is an application bean that
                // wraps the default converter and enforces PKCE for code clients.
                registrationProvider.setRegisteredClientConverter(
                        pkceRegisteredClientConverter::convert);
            }
        });
}
~~~

Place this method in a Spring configuration class and declare `PkceRegisteredClientConverter` as a bean. A custom validator replaces the provider's default validator, so you must chain back the required strict checks. The example above validates scopes via its own allowlist and does not call `SIMPLE_SCOPE_VALIDATOR`. If the application supports `post_logout_redirect_uris` or `jwks_uri`, keep the corresponding validators and add dedicated policies for those metadata fields.

### 13.4. Wiring the Provider into the Endpoint

Attach the customizer to the OIDC Client Registration Endpoint:

~~~java
authorizationServerConfigurer.oidc(oidc ->
    oidc.clientRegistrationEndpoint(endpoint ->
        endpoint.authenticationProviders(registrationProviderCustomizer)
    )
);
~~~

This snippet wires into the Authorization Server `SecurityFilterChain` created in section 9. Do not register a provider customizer without tests proving the validator executes before `RegisteredClient` is persisted.

## 14. Enforcing PKCE and Converting Metadata to RegisteredClient

### 14.1. Public Clients Must Use PKCE

For clients using `token_endpoint_auth_method=none`, the Authorization Server has no client secret to authenticate them at the Token Endpoint. With the Authorization Code Flow, PKCE is an essential defense against code interception.

In Spring Authorization Server, `RegisteredClient` has `ClientSettings.requireProofKey(true)`. When DCR creates a public client, ensure the converter sets this property:

Example converter injected into the registration provider customizer in section 13.3. The converter keeps the default mapped metadata and then sets `requireProofKey` for Authorization Code clients:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.converter.OidcClientRegistrationRegisteredClientConverter;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

final class PkceRegisteredClientConverter
        implements Converter<OidcClientRegistration, RegisteredClient> {

    private final OidcClientRegistrationRegisteredClientConverter delegate =
            new OidcClientRegistrationRegisteredClientConverter();

    @Override
    public RegisteredClient convert(OidcClientRegistration registration) {
        RegisteredClient registeredClient = delegate.convert(registration);

        boolean authorizationCodeClient = registeredClient.getAuthorizationGrantTypes()
                .contains(AuthorizationGrantType.AUTHORIZATION_CODE);

        ClientSettings settings = ClientSettings.withSettings(
                registeredClient.getClientSettings().getSettings())
                .requireProofKey(authorizationCodeClient)
                .build();

        return RegisteredClient.from(registeredClient)
                .clientSettings(settings)
                .build();
    }
}
~~~

Register this converter class as a bean or instantiate it in configuration and inject it into the customizer. The example above enforces PKCE for all clients with the Authorization Code grant, including both public and confidential clients; public clients still use `ClientAuthenticationMethod.NONE` and have no client secret.

Bean declaration example:

~~~java
import org.springframework.context.annotation.Bean;

@Bean
PkceRegisteredClientConverter pkceRegisteredClientConverter() {
    return new PkceRegisteredClientConverter();
}
~~~

### 14.2. RegisteredClientRepository Is Where Registrations Are Stored

`RegisteredClientRepository` is the central component for storing and querying `RegisteredClient` instances. Spring Authorization Server provides:

- `InMemoryRegisteredClientRepository`: for development/testing.
- `JdbcRegisteredClientRepository`: durable storage via JDBC.

Production should use durable storage, proper transactions, and backups. Ensure `client_id` uniqueness, stable internal IDs, and that client settings are not lost across restarts.

### 14.3. Metadata and RegisteredClient Are Not Identical Structures

OIDC Client Registration contains protocol metadata fields such as `response_types`, `application_type`, `logo_uri`, and `contacts`. `RegisteredClient` stores the properties needed for OAuth processing in Spring Authorization Server. Metadata without dedicated fields needs to be stored via `ClientSettings` or a separate metadata store.

Do not assume default converters will preserve arbitrary metadata extensions. If you need to return custom metadata on Client Read, you must also configure the `RegisteredClient`-to-`OidcClientRegistration` converter.

## 15. DCR Defense Layers

### 15.1. Protecting the Registration Endpoint

- Require HTTPS.
- Require an Initial Access Token or an approved registrar authentication method.
- Only registrars with `client.create` may create clients.
- Limit registration counts, request rates, and JSON body sizes.
- Audit tenant, registrar, timestamp, client metadata, and validation outcome.
- Never return internal details or stack traces in errors.

### 15.2. Preventing Redirect Hijacking

- Exact redirect URI matching at the Authorization Endpoint.
- Disallow wildcards or complex regexes unless justified by a specific threat model.
- Web callbacks must use HTTPS.
- Native loopback exceptions strictly follow RFC 8252.
- Check for open redirectors in client applications.
- Prevent registrars from registering callbacks on unverified domains.

### 15.3. Preventing Scope Escalation

Scopes are an Authorization Server policy, not a property clients may freely choose. Enforce allowlists by registrar/tenant/client profile. Privileged scopes require explicit approval or a trusted software statement.

### 15.4. Preventing SSRF via jwks_uri

If the server fetches `jwks_uri`:

1. Accept HTTPS only.
2. Check host against policy and block localhost/private/link-local/metadata services.
3. Guard against DNS rebinding and unsafe redirects.
4. Cap connect/read timeouts, response size, and key count.
5. Accept only schema-valid JSON JWK Sets.
6. Reject private/symmetric keys.
7. Maintain cache/rotation policies and a mechanism to invalidate compromised keys.

SAS's default validator checks the HTTPS scheme for `jwks_uri`; that alone is not a complete SSRF defense. Network egress policies and URL validation must be added per environment.

### 15.5. Preventing Forged Registrations and Software Statements

RFC 7591 allows a `software_statement` signed by a trusted issuer to attest metadata about the client software. If used:

- Trust only pre-configured issuers.
- The software statement must be signed or MACed per standard, include `iss`, and have its signature, issuer, expiration, audience, and relevant claims verified.
- Metadata from a trusted software statement must take precedence per specification rules.
- Never accept a software statement merely because its payload decodes.

A software statement does not replace redirect URI, grant, and authentication method validation. Do not assume Spring Authorization Server's default OIDC Client Registration Endpoint automatically verifies `software_statement`; if implementing this feature, add dedicated converters/validators and a trust registry.

### 15.6. Post-Registration Credential Management

- Client secrets must be randomly generated with sufficient entropy and encoded via `PasswordEncoder`.
- Client Read Responses may include `client_secret` metadata; only registrars with a valid Registration Access Token may read the registration.
- The Registration Access Token is a bearer credential managing the registration; protect it like a secret.
- Support revoking/rotating secrets and registration tokens per procedure.
- When a client is compromised, disable the client and revoke related authorizations/tokens.

## 16. Registration Request and Validation Examples

### 16.1. Valid Web Confidential Client

~~~json
{
  "client_name": "Billing Partner",
  "application_type": "web",
  "redirect_uris": [
    "https://billing.partner.example/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile billing.read"
}
~~~

Accept only if the callback is approved, scopes are in the allowlist, and the server supports these grants/methods.

### 16.2. Valid Public SPA

~~~json
{
  "client_name": "Customer SPA",
  "application_type": "web",
  "redirect_uris": [
    "https://app.customer.example/oauth/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "none",
  "scope": "openid profile"
}
~~~

The SPA must be configured with mandatory PKCE and must not be issued a client secret.

### 16.3. Registration to Reject: Wildcard Redirect

~~~json
{
  "redirect_uris": [
    "https://*.partner.example/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Wildcards blur the callback boundary and can allow subdomain takeover. Require registering exact URIs.

### 16.4. Registration to Reject: Response/Grant Mismatch

The following example illustrates a validator for general OAuth DCR under RFC 7591. Spring Authorization Server's OIDC DCR must follow OIDC Registration's grant/response sets; do not use this example to conclude that the default OIDC endpoint accepts `client_credentials`.

~~~json
{
  "redirect_uris": [
    "https://partner.example.com/callback"
  ],
  "grant_types": [
    "client_credentials"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

`client_credentials` does not produce `response_type` `code`. The registrar must choose a coherent profile instead of mixing M2M and browser flows.

### 16.5. Registration to Reject: Public Client Using an Inappropriate Grant

This example also belongs to general OAuth DCR under RFC 7591; it illustrates client type/grant policy rather than an OIDC DCR request compatible with the default SAS endpoint.

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://spa.example.com/callback"
  ],
  "grant_types": [
    "client_credentials"
  ],
  "token_endpoint_auth_method": "none"
}
~~~

A public client has no suitable client authentication for `client_credentials`.

## 17. Testing Dynamic Client Registration

Tests should go through the real endpoint inside the test context, use an authenticated registrar Access Token, and verify `RegisteredClient` state after the request completes.

### 17.1. Testing Endpoint Configuration

Verify:

- OIDC support is enabled.
- Client Registration Endpoint is explicitly enabled.
- Discovery metadata includes the right `registration_endpoint` when published.
- `JwtDecoder` bean can verify the Initial Access Token.
- `RegisteredClientRepository` can store and query the new client.

### 17.2. Testing Redirect URI Validators

Write tests for:

- HTTPS callbacks in the allowlist.
- Callbacks outside the allowlist.
- URIs with fragments.
- URIs missing a scheme.
- `javascript`/`data`/`vbscript` schemes.
- Wildcard hosts/paths.
- Spoofed hosts via userinfo.
- Native custom schemes violating policy.
- Loopback URIs with IP literals and dynamic ports matching the native profile.
- Loopback URIs used by a web client.

### 17.3. Testing Grant/Response Compatibility

Verify:

- `authorization_code` + `code`.
- `authorization_code` + `refresh_token` + `code`.
- `client_credentials` without declaring a `code` response.
- Server-unsupported `grant_types`.
- Implicit/hybrid `response_types` rejected when unsupported by the server.
- `password` grant rejected per policy.
- `response_type` `code` without `authorization_code`.
- `response_type` `token` without `implicit` or when the server does not support implicit (general OAuth DCR case under RFC 7591).

### 17.4. Testing Authentication Methods

Verify:

- `client_secret_basic` is allowed and a secret is generated.
- `none` generates no secret and enforces PKCE.
- `client_secret_post` is rejected if disallowed by policy.
- `private_key_jwt` without `jwks_uri` is rejected.
- HTTP `jwks_uri` is rejected.
- TLS methods are rejected if the server has not enabled the corresponding provider.
- Client Read Responses need not return `registration_access_token` again unless rotated/updated; `client_secret` may appear per registered metadata.

## 18. Comprehensive Test Matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Registrar has valid `client.create` | Allowed to submit registration |
| 2 | No Bearer token | 401 |
| 3 | Token lacks `client.create` | 403 or corresponding OAuth error |
| 4 | Token has `client.create` plus extra scopes per SAS policy | Rejected |
| 5 | Already-used Initial Access Token | Subsequent registration request rejected |
| 6 | `redirect_uris` HTTPS exact allowlist | Accepted |
| 7 | Redirect URI outside allowlist | `invalid_client_metadata` |
| 8 | Redirect URI with fragment | Rejected |
| 9 | Redirect URI using `javascript`/`data` | Rejected |
| 10 | Wildcard redirect URI | Rejected |
| 11 | Spoofed host using userinfo | Rejected |
| 12 | Native loopback IP with dynamic port | Accepted per native policy |
| 13 | Native loopback port exception applied to web client | Rejected |
| 14 | `authorization_code` + `code` | Accepted |
| 15 | `client_credentials` + `code` | Rejected |
| 16 | `response_type` unsupported by server | Rejected |
| 17 | `implicit` or `password` grant | Rejected per policy |
| 18 | `token_endpoint_auth_method=none` for SPA + PKCE | Accepted |
| 19 | `token_endpoint_auth_method=none` requesting `client_credentials` | Rejected |
| 20 | `client_secret_basic` | Accepted if policy allows; secret generated |
| 21 | `private_key_jwt` missing JWKS | Rejected |
| 22 | `jwks_uri` not using HTTPS | Rejected |
| 23 | `jwks_uri` pointing to private IP/metadata endpoint | Blocked by SSRF/network policy |
| 24 | `scope` contains ungranted admin scopes | Rejected |
| 25 | Unsupported metadata extension | Ignored or handled per RFC/profile, never blindly persisted |
| 26 | Client Registration succeeds | Returns `client_id` and approved metadata |
| 27 | Client Read using `registration_access_token` | Returns corresponding registration |
| 28 | Client Read lacking valid `client.read`/registration token | Rejected |
| 29 | Client Read Response | Does not return `registration_access_token` if not updated; protect `client_secret` if present |
| 30 | Two concurrent registrations with same callback but different `client_id` | Each client stored separately, callback policy still enforced |
| 31 | Registrar exceeds quota | Rate-limited or rejected |
| 32 | DB failure while saving `RegisteredClient` | Does not return false success response |
| 33 | Scope omitted in web profile requiring explicit scope | Rejected |
| 34 | `application_type=native` sent to web-only validator | Rejected |
| 35 | Request self-supplies `client_id` or `client_secret` | Rejected; server issues values |
| 36 | Request sends both `jwks` and `jwks_uri`, or profile forbids client JWKS | Rejected |

## 19. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/connect/register` returns 404 | Endpoint not enabled or wrong path | Check `oidc.clientRegistrationEndpoint` and `AuthorizationServerSettings` |
| 401 at registration endpoint | Initial Access Token missing/bad signature/wrong issuer | Check `JwtDecoder` and Bearer token |
| `insufficient_scope`/`client.create` | Registrar token lacks required scope | Issue token with exact `client.create` scope |
| `invalid_client_metadata` | Redirect/scope/grant/auth method failed validator | Check metadata and validator chain |
| Valid redirect rejected | Strict validator or allowlist not updated | Check exact URI and profile |
| Client registered successfully but authorization request rejected | Grant/response type or redirect mismatch | Inspect `RegisteredClient` and Authorization Request |
| Public client requires a secret | `token_endpoint_auth_method` is not `none` or wrong converter | Check metadata/converters |
| Public client not required to use PKCE | `ClientSettings.requireProofKey` not enabled | Fix `RegisteredClient` converter/policy |
| Client Read omits custom metadata | Converter does not map metadata extension | Configure converters in both directions |
| Registration token rejected on read | Used Initial Access Token instead of Registration Access Token | Use `registration_access_token` from the response |
| JWKS fetch timeout | DNS/network/SSRF policy or broken client JWKS server | Check URL, timeout, outbound policy |
| Arbitrary scopes saved | Used `SIMPLE_SCOPE_VALIDATOR` without an allowlist | Use a custom scope validator |
| One client registered repeatedly without control | Missing quota/idempotency/onboarding policy | Add rate limits and registrar ownership checks |

## 20. Operations, Auditing, and Registration Lifecycle

### 20.1. Audit Events

Record:

- Registrar identity/client ID.
- Tenant/organization.
- Registration operation and timestamp.
- New Client ID.
- Approved grant types, response types, and auth method.
- Number of granted redirect URIs and scopes.
- Validation policy version.
- Success/failure outcome and error code.

Never write `client_secret`, Initial Access Token, Registration Access Token, or private keys to audit logs.

### 20.2. Managing Metadata Changes

When a client needs to change redirect URIs, grants, or authentication methods:

1. Authenticate the Registration Access Token or admin identity.
2. Verify authorization to manage that exact client.
3. Re-run the entire validator suite, not just checks on the changed field.
4. Check grant/response/auth method consistency.
5. Audit old and new values per data protection policy.
6. Persist the registration within a transaction.
7. Test that the old client can no longer use removed redirects or methods.

Never let clients modify security metadata through an unauthenticated endpoint.

### 20.3. Revoking a Registration

When a client is compromised or no longer used:

- Disable or delete the `RegisteredClient` per procedure.
- Revoke the Registration Access Token.
- Rotate/revoke client secrets or certificates.
- Revoke issued authorizations/tokens if required by policy.
- Confirm Resource Servers reject affected tokens per the revocation strategy.
- Retain audit records and investigative data.

Deleting a registration does not automatically make issued JWTs vanish from every Resource Server. Coordinate with token revocation/introspection/denylists or short TTLs.

### 20.4. Monitoring Metrics

Track:

- Registration requests per registrar/tenant.
- Success vs. `invalid_client_metadata` rates.
- Redirect URI rejection count.
- Grant/auth method rejection count.
- Registration quota usage.
- Initial Access Token consumption.
- Client secret rotation/expiry.
- JWKS fetch errors and unknown `kid` occurrences.
- Inactive or incomplete onboarding client registrations.

## 21. Production Deployment Checklist

1. **Protected registration:** endpoint is not open arbitrarily; requires an Initial Access Token or approval workflow.
2. **Registrar scopes:** `client.create` granted only to trusted registrars; `client.read` strictly scoped to need.
3. **redirect_uris:** exact allowlist, no wildcards, HTTPS for web, native exceptions per RFC 8252.
4. **grant_types:** allow only implemented and policy-approved grants.
5. **response_types:** validate matrix against `grant_types` and server capabilities.
6. **Authentication method:** public/confidential clients choose appropriate methods; disallow downgrades.
7. **PKCE:** mandatory for Authorization Code Flow per security policy.
8. **Scopes:** allowlist by tenant/client profile; never use an accept-all scope validator.
9. **JWKS:** HTTPS, public keys only, SSRF protections, and key rotation.
10. **Secrets:** server-generated secrets stored in a secret manager, never logged.
11. **Registration tokens:** Initial Access Tokens and Registration Access Tokens have separate lifecycles and permissions.
12. **Persistence:** durable `RegisteredClientRepository`; `InMemory` is for dev/test only.
13. **Custom metadata:** bidirectional converters and explicit allowlists.
14. **Validation:** default strict validators preserved; custom policies add grant/response/auth method checks.
15. **Abuse protection:** rate limits, quotas, registrar auditing, and domain verification.
16. **Testing:** negative tests for redirects, scopes, grants, response types, auth methods, and SSRF.
17. **Incident response:** disable client, revoke credentials, and handle already-issued tokens.

## 22. Exercises and Self-Assessment Questions

**Exercise A — Redirect URI.** A web client registers `https://portal.example.com/callback`. Write a validator that rejects wildcards, URI fragments, userinfo, and unapproved domains. Explain why the Authorization Endpoint still needs exact matching.

**Exercise B — Native app.** A native app uses a loopback callback with a dynamic port. Design a policy for `127.0.0.1` and `[::1]`, and explain why the port exception does not apply to web clients.

**Exercise C — Grant/response.** A client sends `grant_types=client_credentials` and `response_types=code`. Write validation logic rejecting the registration and explain the relationship between the two fields.

**Exercise D — Public client.** An SPA sends `token_endpoint_auth_method=none`. Identify the additional settings needed so the client uses Authorization Code + PKCE safely.

**Exercise E — Confidential client.** A backend service requests `private_key_jwt`. Design validation for `jwks_uri`, key `use`, key rotation, and `token_endpoint_auth_signing_alg`.

**Exercise F — Spring Authorization Server.** Enable the OIDC Client Registration Endpoint, create a registrar with `client.create`, issue an Initial Access Token, and register a client using `WebClient`.

**Exercise G — Scope injection.** A DCR validator uses `SIMPLE_SCOPE_VALIDATOR`. A registrar sends `scope=admin system.write`. Analyze the risk and write a replacement allowlist validator.

**Exercise H — Registration takeover.** A Registration Access Token is leaked. Describe how an attacker could read or modify metadata and the revoke/rotate procedure to remediate it.

**Review questions:**

1. How do RFC 7591 and OIDC Dynamic Client Registration differ in scope?
2. How does an Initial Access Token differ from a Registration Access Token?
3. Why does a DCR endpoint need a protected registrar?
4. At which two points must `redirect_uris` be validated?
5. How does exact matching differ from wildcard/prefix matching?
6. When does the native loopback port exception apply?
7. How are `grant_types` and `response_types` related?
8. Why does `client_credentials` not pair with `response_type=code`?
9. What does `token_endpoint_auth_method=none` mean?
10. Why do public clients need PKCE?
11. What key metadata does `private_key_jwt` require?
12. How do `DEFAULT_SCOPE_VALIDATOR` and `SIMPLE_SCOPE_VALIDATOR` differ?
13. Why is using `DEFAULT_REDIRECT_URI_VALIDATOR` alone insufficient for production policy?
14. Does Spring Authorization Server 1.5.8 enable the Client Registration Endpoint by default?
15. Why does the endpoint need a `JwtDecoder`?
16. In which directions does custom metadata need converters?
17. What impact can a leaked Registration Access Token cause?
18. Does deleting a `RegisteredClient` automatically revoke all issued JWTs?

## 23. References

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7591, Section 2 — Client Metadata](https://www.rfc-editor.org/rfc/rfc7591#section-2)
- [RFC 7591, Section 2.1 — Relationship between Grant Types and Response Types](https://www.rfc-editor.org/rfc/rfc7591#section-2.1)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592)
- [OpenID Connect Dynamic Client Registration 1.0, Errata Set 2](https://openid.net/specs/openid-connect-registration-1_0.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [Spring Authorization Server 1.5.8 — How-to: Register a Client Dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html)
- [Spring Authorization Server 1.5.8 — RegisteredClientRepository](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)

**Takeaway:** Dynamic Client Registration creates a client authorized to operate in the Authorization Server. Before saving `RegisteredClient`, validate `redirect_uris`, `grant_types`, `response_types`, `token_endpoint_auth_method`, and `scope` as an interrelated metadata set. Redirect URIs require exact matching; grants/responses must be compatible and restricted to server-supported flows; authentication methods must match public/confidential client types and real keys/secrets. In Spring Authorization Server 1.5.8, the OIDC Client Registration Endpoint is disabled by default, requiring a registrar with `client.create` and a `JwtDecoder` to verify the Initial Access Token. Preserve strict validators, add dedicated allowlists, and protect the Registration Access Token as a bearer credential with client management privileges.
