# 6.9. Metadata Limitations and Differences Across Providers

## 1. Why Do Providers Differ in Configuration Even When Using OAuth 2.0/OIDC?

A **Spring Security OAuth 2.0/OIDC Client** application may let users log in through several providers: an internal SSO system, a public OpenID Provider, or a platform that only supports OAuth 2.0. They may all use the Authorization Code Grant yet still differ in endpoint addresses, client authentication methods, scopes, returned claims, token policies, logout mechanisms, and vendor extensions.

Suppose a Spring Boot application at `https://app.example.com` needs to integrate two identity sources:

- **Provider A:** supports OIDC Discovery, publishing issuer, endpoints, JWK Set, and related metadata.
- **Provider B:** supports the OAuth 2.0 Authorization Code Grant, yet does not offer OIDC Discovery; the client must declare endpoints and user-info parsing rules.

Merely copying Provider A's configuration to Provider B can easily cause failures at startup, during login redirect, during authorization code exchange, or when mapping users.

This lesson explains how to **read, evaluate limitations of, and handle metadata differences across providers**, and then configure Spring Security accordingly. The focus is on **OAuth2/OIDC provider metadata**, not user account metadata.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish metadata published by **OpenID Connect Discovery** from metadata under **OAuth 2.0 Authorization Server Metadata**.
2. Identify which fields describe **server capabilities**, which reflect **issued client configuration**, and which only appear during actual logins.
3. Read common metadata fields such as `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`, `scopes_supported`, and `token_endpoint_auth_methods_supported`.
4. Understand limitations: metadata may omit optional fields, not reflect per-tenant/client policies, or describe only partial extensions.
5. Configure `spring.security.oauth2.client.provider.*` manually when full discovery cannot be used.
6. Test real login flows and design an appropriate compatibility layer across multiple providers.

URLs using `example.com`, issuers, client IDs, and claims in this lesson are **illustrative examples**, not the live configuration of any specific vendor.

## 2. What Does Metadata Mean in OAuth2/OIDC?

**Provider metadata** is the set of information about an Authorization Server/OpenID Provider that a client needs to execute the protocol or determine which features the server supports.

For example, an OIDC Provider might publish:

~~~json
{
  "issuer": "https://id.example.com",
  "authorization_endpoint": "https://id.example.com/oauth2/authorize",
  "token_endpoint": "https://id.example.com/oauth2/token",
  "jwks_uri": "https://id.example.com/keys",
  "userinfo_endpoint": "https://id.example.com/oidc/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Information can be grouped into categories:

| Group | Typical fields | Question the metadata answers |
|---|---|---|
| Server identity | `issuer` | Which provider publishes and issues tokens? |
| Protocol endpoints | `authorization_endpoint`, `token_endpoint` | Where does the client send authorize and token requests? |
| Keys and verification | `jwks_uri`, `id_token_signing_alg_values_supported` | Where are public keys fetched, and which algorithms are supported? |
| UserInfo | `userinfo_endpoint` | Is there an OIDC user information endpoint? |
| Grants/responses | `grant_types_supported`, `response_types_supported` | Which grant types and response types does the server support? |
| Client authentication | `token_endpoint_auth_methods_supported` | Which client authentication methods does the token endpoint advertise? |
| Scopes/claims | `scopes_supported`, `claims_supported` | Which scopes/claims are advertised? |
| Extension support | `code_challenge_methods_supported`, `pushed_authorization_request_endpoint` | Is PKCE/PAR or another extension feature advertised? |
| Logout/token management | `end_session_endpoint`, `revocation_endpoint`, `introspection_endpoint` | Are related optional endpoints or capabilities available? |

**Metadata is not a token** and does not contain access permissions granted to any specific user. `scopes_supported` describes general server capabilities; actually granted scopes must be read from the authorization/token response or access token details per the API contract.

## 3. Three Sources of Information That Must Not Be Conflated

For stable integration, distinguish three layers of data.

| Source | Examples | Scope of meaning |
|---|---|---|
| **Server-published metadata** | `authorization_endpoint`, `jwks_uri`, `grant_types_supported` | General protocol addresses/capabilities of the issuer or authorization server. |
| **Client registration and applicable policy** | `client_id`, secret, callback allowlist, approved scopes, client authentication method | What a specific client is permitted to use; usually obtained from an admin console/registration API. |
| **Response from a single transaction** | `code`, `state`, token response, granted `scope`, claims in ID Token | The actual outcome for a given request, user, timestamp, and active policy. |

Suppose metadata says:

~~~json
{
  "scopes_supported": ["openid", "profile", "email", "offline_access"]
}
~~~

That **does not guarantee** the `portal-web` client is allowed to request all four scopes. The provider might require separate approval for `offline_access`, withhold refresh tokens from certain app types, or restrict them by tenant.

Similarly, if metadata contains:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "client_secret_post",
    "private_key_jwt"
  ]
}
~~~

then the client **uses only the method registered and configured for it**. Do not automatically switch from `client_secret_basic` to `private_key_jwt` merely because metadata lists both.

Use metadata to **discover and check capabilities**, client registration to **choose valid configuration**, and actual responses to **confirm outcomes**.

## 4. OIDC Discovery: Common Metadata Source for OpenID Providers

### 4.1. What Does OIDC Discovery Provide?

**OpenID Connect Discovery** lets a client retrieve an OpenID Provider's configuration from a known issuer. For a simple issuer:

~~~text
https://id.example.com
~~~

a common discovery address is:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: id.example.com
Accept: application/json
~~~

A successful response is a JSON metadata document. OIDC Discovery defines standard required fields, including `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `response_types_supported`, `subject_types_supported`, and `id_token_signing_alg_values_supported`. Many other fields are optional or apply only when the provider supports a feature.

**The issuer is the exact identity of the provider.** Received metadata must publish an `issuer` matching the issuer the client intends to trust. If the application configures `https://id.example.com/tenant-a` while the document returns `issuer = https://id.example.com/tenant-b`, the client must never treat them as the same provider just because they share a host.

Issuers with paths follow standard rules for constructing discovery URLs; **never guess paths by naive string concatenation** when implementing a discovery client. Spring Security provides mechanisms to discover metadata from an issuer and should be preferred.

### 4.2. Notable Fields

| OIDC field | Meaning | Key point to remember |
|---|---|---|
| `issuer` | OP identifier | Must match the expected issuer exactly, not approximately. |
| `authorization_endpoint` | Endpoint receiving authorization requests | Used for browser redirects; URL published by provider. |
| `token_endpoint` | Endpoint receiving token requests | Code exchange happens on the backend over HTTPS. |
| `jwks_uri` | JWK Set address | Signing keys may rotate; client needs a mechanism to fetch updated valid keys. |
| `userinfo_endpoint` | Endpoint for querying UserInfo | Optional; not every OP returns every claim in UserInfo. |
| `response_types_supported` | Supported response types | `code` is needed for the Authorization Code Flow. |
| `subject_types_supported` | Subject identifier types | `public`/`pairwise` affects how `sub` is generated across clients. |
| `id_token_signing_alg_values_supported` | ID Token signing algorithms | Accept only algorithms allowed by the client and compatible. |
| `grant_types_supported` | Grants advertised by the server | May be omitted; does not replace permissions granted to the client. |
| `scopes_supported` | Published scope list | May omit custom per-tenant/API scopes. |
| `claims_supported` | Claims that may be provided | Does not guarantee every ID Token or UserInfo response includes all claims. |
| `token_endpoint_auth_methods_supported` | Client authentication methods at token endpoint | Choose matching what the client registered. |
| `code_challenge_methods_supported` | Advertised PKCE methods | Field may be absent even if provider supports PKCE; check contract and runtime behavior. |
| `end_session_endpoint` | OIDC logout endpoint if available | Not a mandatory component of every provider. |

If a field required by OIDC Discovery is missing, metadata may be non-compliant or the endpoint may be misconfigured. If **an optional field** is missing, you cannot conclude the feature definitely does not exist: the spec may define a default, the provider may use another mechanism, or the feature may only be documented separately.

### 4.3. Having Metadata Does Not Mean Every Client Gets the Same Features

An OP may serve several client types: confidential web, public SPA, mobile native, or machine-to-machine. Server metadata publishes general capabilities, whereas an individual client's registration may restrict:

- which `redirect_uri` values are permitted;
- which `grant_type` values are enabled;
- whether there is a client secret or `private_key_jwt`;
- whether `offline_access` and refresh tokens are allowed;
- whether the client may use `prompt=none` or step-up authentication;
- which API scopes are approved.

Therefore, the client should rely on **provisioned registration settings** first, use metadata to locate matching endpoints/capabilities, and handle denial conditions via actual responses.

## 5. How Does OAuth 2.0 Authorization Server Metadata Differ from OIDC Discovery?

OAuth 2.0 defines authorization and token flows, yet **does not require every Authorization Server to support OIDC**. Some servers support metadata per **RFC 8414 — OAuth 2.0 Authorization Server Metadata** without issuing ID Tokens or providing OIDC UserInfo.

### 5.1. The Two Document Types Can Look Similar

Example OAuth 2.0-style metadata:

~~~json
{
  "issuer": "https://auth.example.net",
  "authorization_endpoint": "https://auth.example.net/authorize",
  "token_endpoint": "https://auth.example.net/token",
  "revocation_endpoint": "https://auth.example.net/revoke",
  "grant_types_supported": [
    "authorization_code",
    "client_credentials"
  ],
  "response_types_supported": ["code"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic"
  ],
  "code_challenge_methods_supported": ["S256"]
}
~~~

This document may suffice for a client to locate authorization/token endpoints for OAuth2, yet **does not prove the server supports OIDC**. For example, there is no `userinfo_endpoint`, no claim of ID Token support, and no OIDC metadata for `subject_types_supported` or `id_token_signing_alg_values_supported`.

An **OAuth2 Authorization Server** may be completely valid for API access authorization scenarios while being unsuitable as an OIDC Provider for standardized identity login.

### 5.2. Comparison

| Characteristic | OIDC Discovery | OAuth2 AS Metadata (RFC 8414) |
|---|---|---|
| Focus | OpenID Provider and user authentication | Authorization Server and OAuth2 capabilities |
| Common well-known suffix | `openid-configuration` | `oauth-authorization-server` |
| ID Token | Central part of OIDC | Not present by default |
| `userinfo_endpoint` | Optional OIDC metadata field | Not a mandatory general OAuth2 endpoint |
| `jwks_uri` | Important for verifying JWT ID Tokens | May be published depending on server/token config |
| `subject_types_supported` | Part of OIDC metadata | Not a general OAuth2 guarantee |
| `id_token_signing_alg_values_supported` | Part of OIDC metadata | Not a general OAuth2 guarantee |
| Applying `scope=openid` | Carries OIDC semantics | Cannot assume support automatically |
| `sub` claim in ID Token | Defined by OIDC | No ID Token exists in pure OAuth2 |

For issuers with paths, well-known path construction rules differ between OIDC and RFC 8414. Standards-compliant discovery libraries help avoid URL-concatenation mistakes.

A provider may publish both metadata formats simultaneously. **Read the document matching the login type the client needs**: if you want OIDC Login, OIDC support must actually exist; do not read an OAuth2 metadata file and assume an ID Token will appear.

### 5.3. Providers That Publish No Standard Metadata

An OAuth2 provider may describe its endpoints and integration rules only in manual documentation, offering no standard discovery endpoint or only partial support.

In that case, configure the needed URIs directly in Spring Security, for example:

- `authorization-uri`;
- `token-uri`;
- `user-info-uri` if OAuth2 login needs to call a user info API;
- `user-name-attribute` so Spring Security identifies the principal from the user info response;
- `jwk-set-uri` and `issuer-uri` when genuinely integrating OIDC as supported by the provider.

Never put a fake `issuer-uri` into configuration just to make Spring Boot "look complete" if the endpoint does not support OIDC Discovery under that issuer.

## 6. Endpoint Addresses Can Differ Completely

The examples below are **hypothetical patterns**, not fixed URLs of any vendor:

| Function | Provider A | Provider B |
|---|---|---|
| Authorization | `https://id-a.example.com/oauth2/authorize` | `https://login-b.example.net/connect/authorize` |
| Token | `https://id-a.example.com/oauth2/token` | `https://login-b.example.net/connect/token` |
| UserInfo | `https://id-a.example.com/oidc/userinfo` | No standard endpoint |
| JWK Set | `https://id-a.example.com/keys` | `https://login-b.example.net/.well-known/jwks.json` |
| Logout | `https://id-a.example.com/connect/endsession` | Publishes no OIDC endpoint |
| Revocation | May exist | May not exist |

There is no universal rule that the token endpoint is always `/oauth/token` or UserInfo is always `/userinfo`. Nor should you take the authorization URL and replace `authorize` with `token` to guess endpoints.

**What to do:** let valid metadata supply URLs, or read endpoints from provider documentation when declaring manually. For per-tenant issuers, endpoints may include a realm/tenant path, and switching tenants changes both the paths and the trusted issuer.

### 6.1. An Endpoint URL Existing Does Not Mean Every Action Is Allowed

The token endpoint can reject requests because:

- the client has not been granted the grant type;
- `client_id` or secret is wrong;
- the client authentication method mismatches;
- the authorization code is expired or reused;
- the PKCE verifier is invalid;
- `redirect_uri` mismatches;
- tenant policy or user scopes forbid it.

An HTTP check to an endpoint only tells you the URL responds; **it does not prove the OAuth2 client flow is authorized and configured properly**.

## 7. Differences in Client Authentication Method

Metadata may list client authentication methods at the token endpoint:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "client_secret_post",
    "private_key_jwt"
  ]
}
~~~

Common methods:

| Value | Interpretation | Notes |
|---|---|---|
| `client_secret_basic` | Sends client ID/secret via HTTP Basic Authorization | Use over HTTPS only; keep secret on backend. |
| `client_secret_post` | Sends client ID/secret in the token request body | Use only when permitted by provider and registration. |
| `private_key_jwt` | Client creates and signs an assertion with its private key | Must register key, algorithm, and matching audience/token endpoint. |
| `client_secret_jwt` | Client uses shared secret to sign an assertion | Not equivalent to `client_secret_basic`. |
| `none` | Public clients without a client secret may register this way | Needs protections like PKCE; do not treat as confidential client. |

For an OAuth2 web application with a backend, a common Spring Boot configuration is:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          demo-provider:
            issuer-uri: https://id.example.com
~~~

If the provider registers the client as `client_secret_post`, update the method configuration accordingly. Server metadata listing supported methods **does not change the registration already issued to your application**.

With `private_key_jwt`, you need additional components to generate assertions, manage private keys, and configure per framework/provider capabilities. Merely changing the `client-authentication-method` line without providing a signing key or valid JWT assertion generator will not make token requests succeed.

### 7.1. Which Error Usually Signals the Wrong Method?

The token endpoint usually returns `invalid_client` or an equivalent client authentication error. Do not assume the secret is wrong by default: the secret might be right while the provider expects a different client authentication method.

When troubleshooting, check:

1. Which method the provider-side registration specifies.
2. Whether `client-authentication-method` in Spring Boot matches.
3. Whether the token endpoint receives headers/body/auth assertions in the expected format.
4. Whether any proxy strips the Authorization header or alters the request.

Never put secrets, Basic headers, or signed client assertions into public diagnostic logs.

## 8. PKCE: Advertised Metadata vs. Mandatory Policy

**Proof Key for Code Exchange (PKCE)** binds the authorization code to a verifier generated by the client when initiating the authorization request. A provider may publish:

~~~json
{
  "code_challenge_methods_supported": ["S256"]
}
~~~

However, variations exist:

- A provider requires PKCE for public clients and recommends it for confidential clients.
- A provider requires PKCE for **every** Authorization Code Grant.
- A provider supports PKCE, yet metadata omits the extension field.
- A legacy provider offers only partial support or requires dedicated client configuration.
- A provider enables PKCE only for certain application types or tenants.

**The absence of `code_challenge_methods_supported` is not enough to infer PKCE is unsupported.** This metadata field can be omitted; check registration parameters and official docs.

Prefer PKCE `S256`. In the Authorization Code Flow, the client sends:

~~~text
Authorization request:
  code_challenge=BASE64URL(SHA256(code_verifier))
  code_challenge_method=S256

Token request:
  code_verifier=saved_original_value
~~~

If the provider bound the code with a challenge, a token request without the matching verifier will fail. The client must never generate a new verifier at the callback, nor reuse one static verifier across all users.

When customizing PKCE in Spring Security, store `code_verifier` tied to the exact authorization request so the token exchange retrieves the original value. Such customizations belong to the OAuth2 authorization request resolver configuration; **provider metadata does not generate verifiers for the client**.

## 9. Advertised Scopes Do Not Guarantee Granted Scopes

Multiple providers may support `openid`, `profile`, and `email` while returning claims differently. Moreover, API scopes are **provider-specific**; names like `read:orders` or `contacts.read` only carry meaning as defined by that provider/API.

Example:

~~~json
{
  "scopes_supported": [
    "openid",
    "profile",
    "email",
    "offline_access"
  ]
}
~~~

At least four levels must be distinguished:

1. **Server supports** the scope in metadata.
2. **Client is approved** for the scope in registration/admin settings.
3. **User or policy allows** the scope in the current authorization request.
4. **Issued token actually receives** which scopes after consent/policy.

Do not conflate these four levels. Some providers return only a subset of scopes or require a separate parameter to allow refresh tokens. Some providers never issue refresh tokens to certain client types even when the client requests `offline_access`.

### 9.1. OIDC Scopes and API Scopes Example

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            scope:
              - openid
              - profile
              - email
          order-api:
            scope:
              - orders.read
              - orders.write
~~~

These two registrations only illustrate grouping scopes; they are not complete runnable configurations. `corporate-login` targets OIDC login, while `order-api` may serve an API under a separately registered grant and provider.

If a provider does not support OIDC yet the client requests `openid`, adding this scope in YAML **does not cause the provider to issue an ID Token**. Conversely, in an OIDC flow, the access token may carry extra API scopes, yet the API still requires the proper audience and authorization policies.

## 10. Differences in Claims, Subject, and UserInfo

### 10.1. Metadata `claims_supported` Does Not Guarantee Every Claim Is Present

An OIDC provider might publish:

~~~json
{
  "claims_supported": [
    "sub", "name", "given_name", "family_name",
    "preferred_username", "email", "email_verified"
  ]
}
~~~

Yet an ID Token or UserInfo response only contains claims matching scopes, configuration, security policies, and user data.

Example:

~~~json
{
  "sub": "user-872",
  "email": "user@example.net",
  "email_verified": false
}
~~~

You cannot assume an email is verified simply because the provider returned `email`. The application must check `email_verified` when policy requires it, while respecting the exact semantics guaranteed by the provider.

**The appropriate OIDC identity key is the `(iss, sub)` pair**, not email or display name. `sub` may be public or pairwise depending on the provider; the same user logging into two clients does not necessarily receive the same `sub`.

### 10.2. ID Token and UserInfo Are Two Different Sources

| Source | What is it used for? | Key point to note |
|---|---|---|
| **ID Token** | Verifies the OIDC Authentication result for the client | Must verify signature/issuer/audience/timestamps/nonce per protocol. |
| **UserInfo Endpoint** | Supplies End-User claims when the client holds a valid token/permission | Does not replace the ID Token; returned `sub` must match `sub` in the ID Token. |
| **Provider-specific Profile API** | A custom API on an OAuth2 provider | Does not automatically conform to standard UserInfo; custom fields and auth method. |

Some providers return `name`, `email`, or avatar in UserInfo; others put them in the ID Token, provide only a subset, or require separate scopes/endpoints.

Do not build logic assuming "every provider puts `email` in the ID Token" or "UserInfo always returns `preferred_username`." When optional data is missing, handle it per business rules: leave blank, ask the user to supply it, or block features that strictly require that data.

### 10.3. How Does an OAuth2 Provider Without an ID Token Identify Users?

In OAuth2 Login without `openid`, Spring Security usually uses a UserInfo endpoint or custom user service to fetch a profile and build the principal. Identifier field names can vary:

~~~json
{
  "id": "8521007",
  "login": "sample-user",
  "display_name": "Sample User"
}
~~~

Another provider might return:

~~~json
{
  "user_id": "person-91",
  "nickname": "sample-user"
}
~~~

Both are illustrative payloads. For a non-OIDC provider, Spring Security needs to know which attribute represents the username/ID in the OAuth2 UserInfo response; configure `user-name-attribute` or build a custom `OAuth2UserService` if the API returns non-standard structures.

**Never arbitrarily treat an OAuth2 provider's `id` field as an OIDC `sub`.** When designing internal account linking, store the provider type and identifier separately under an explicit contract.

## 11. JWKS, Signing Algorithms, and Key Rotation

### 11.1. What Is JWKS Used For?

In OIDC, metadata usually publishes `jwks_uri`:

~~~json
{
  "jwks_uri": "https://id.example.com/.well-known/jwks.json"
}
~~~

This address holds a **JSON Web Key Set** with public keys used to verify token signatures as configured. Each JWK may include `kid`, `kty`, `alg`, `use`, or matching key parameters.

When a provider rotates signing keys, new tokens may carry a new `kid`. The client needs a mechanism to fetch updated JWK Sets and manage caching properly. Hard-coding a single public key fetched once and kept forever can break all logins after the provider rotates keys.

### 11.2. Metadata Can Advertise Multiple Algorithms

Example:

~~~json
{
  "id_token_signing_alg_values_supported": [
    "RS256", "ES256"
  ]
}
~~~

Metadata advertising both algorithms **does not mean the client must trust every algorithm**. The client must configure or use a verification mechanism that accepts only algorithms appropriate for the protocol, provider, client registration, and security policy.

Never trust a JWT's `alg` header unconditionally. Never skip signature verification because the JWT payload "looks readable" or because the issuer URL looks familiar.

### 11.3. Issuer, Key, and Audience Must Be Checked Together

A valid ID Token for the current client must satisfy multiple conditions:

~~~text
iss      matches configured issuer?
aud      contains the application's client_id?
exp      not expired?
signature verified by the issuer's trusted key?
nonce    matches if the client used nonce?
azp      satisfies OIDC conditions when multiple audiences/related apply?
~~~

Verifying only the signature while skipping `iss` or `aud` can make the application accept tokens issued for another client/issuer. Conversely, checking only the `iss` string without verifying the signature provides no security guarantee.

Metadata does not replace Spring Security's **ID Token validation logic**.

## 12. Refresh Tokens, Token Revocation, and Introspection Are Not Uniform

OAuth2 providers frequently differ in token lifecycle behavior:

- Some providers issue refresh tokens only under specific conditions.
- Some providers issue refresh tokens only to certain client types or scopes.
- Some providers use refresh token rotation, requiring saving the new token after every refresh.
- Some providers do not offer `revocation_endpoint` or `introspection_endpoint`.
- Some providers issue opaque access tokens; others use JWTs, and may even vary format per resource/audience.

**Never treat a refresh token in the token response as guaranteed.** Spring Security OAuth2 Client must handle absent refresh tokens and valid re-authorization flows.

### 12.1. Revocation Endpoints Are Optional Across Ecosystems

Metadata may publish:

~~~json
{
  "revocation_endpoint": "https://id.example.com/oauth2/revoke",
  "introspection_endpoint": "https://id.example.com/oauth2/introspect"
}
~~~

Having an endpoint does not mean the client may call it with any authentication method or has permission to revoke/introspect every token. Furthermore, **logging out of the web application does not automatically revoke access tokens or end the SSO session at the provider**.

If the application needs to revoke tokens when a user disconnects an account, check the provider's policy documentation, token types, and client authentication method. If the application is a resource server needing introspection, that is a separate inbound token-verification flow, not the default responsibility of an OAuth2 Login client.

### 12.2. Token Endpoint Metadata Does Not Define Access Token Format

An access token can be a JWT or opaque. The client **must not assume** every token is Base64URL-decodable or contains `sub`, `email`, or `roles`. Tokens are issued to access resource servers per permitted scopes/audience.

If an API requires a specific `audience` or `resource`, custom authorization/token request parameters or application settings per provider documentation may be needed. Those vendor-specific parameters are not automatically handled across all providers by standard metadata.

## 13. Logout Metadata and Logout Behavior Differ

OIDC authentication and logout are related yet distinct concerns.

An OpenID Provider might publish:

~~~json
{
  "end_session_endpoint":
    "https://id.example.com/oidc/logout"
}
~~~

However:

- `end_session_endpoint` may not be published at all.
- The provider may require `id_token_hint`, `post_logout_redirect_uri`, or other parameters.
- `post_logout_redirect_uri` usually must be pre-registered or allowed by the provider.
- The provider may only clear the SSO session, while issued tokens follow their own lifecycles.
- Front-channel, back-channel, or RP-initiated logout may only be partially supported.
- Clearing application cookies/sessions does not guarantee the user is logged out of all services sharing the IdP.

Spring Security can integrate OIDC RP-initiated logout when the provider and configuration support it. Yet a client **must not assume** that because a provider supports OIDC login, it shares the same logout endpoint and behavior as another provider.

In particular, never attach one provider's `/logout` URL arbitrarily across all client registrations. Verify metadata, redirect parameters, and security requirements for each provider.

## 14. Extensions Not Supported by Every Provider

Beyond core OAuth2/OIDC, providers may support optional capabilities such as:

| Feature | Related metadata/parameters | Integration limits |
|---|---|---|
| **PKCE** | `code_challenge_methods_supported` | May only support `S256`; may be mandatory per client type. |
| **PAR — Pushed Authorization Requests** | `pushed_authorization_request_endpoint` | Not every provider has it; some providers may require PAR. |
| **JAR — JWT-Secured Authorization Request** | `request_object_signing_alg_values_supported` | Requires request object signing configuration and client keys. |
| **Dynamic Client Registration** | `registration_endpoint` | Does not mean any client may self-register; requires permissions/trust policy. |
| **Resource Indicators** | `resource` parameter | Resource syntax/values must be recognized by provider/API. |
| **Step-up / ACR** | `acr_values_supported`, `acr_values`, `claims` | Assurance values defined by the OP; only certain levels may be supported. |
| **Reauthentication** | `prompt`, `max_age` | Interaction depends on SSO policy and OP capabilities. |
| **Front-/Back-channel logout** | Related logout metadata | Requires separate registration and implementation. |

A provider may support a standard extension yet enable it only via admin settings or per tenant. Never use missing metadata fields as justification to substitute non-standard parameters.

### 14.1. Provider-Specific Parameters

Some systems accept extra authorization request parameters such as tenant selector, login hint, audience/resource, or consent flags. Names and semantics of those fields **are not standardized uniformly across vendors**.

In Spring Security, adding parameters to the authorization request usually requires customizing an authorization request resolver or using extension APIs appropriate for the version and Servlet/WebFlux stack.

Conceptual example:

~~~text
Client A:
  response_type=code
  scope=openid profile
  prompt=login

Client B:
  response_type=code
  scope=read:data
  audience=https://api-b.example.net
~~~

These are two illustrative requests, not a guarantee that `audience` or `prompt` works on every provider. **Only add parameters when the provider documents their meaning and accepts them.** Never inject user-controlled endpoints arbitrarily into requests.

## 15. Spring Boot Configuration: Letting OIDC Discovery Supply Metadata

For a provider that genuinely supports OIDC Discovery, the cleanest configuration is usually `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corporate-idp
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://identity.example.com/tenant-a
~~~

Here:

- `corp` is the Spring application's **registrationId**, used in the default URL `/oauth2/authorization/corp`.
- `corporate-idp` is the provider configuration key linking the registration to the issuer.
- `client-id` and `client-secret` belong to **client registration**, not OIDC Discovery.
- `issuer-uri` identifies the trusted OP and lets the framework discover endpoints/metadata where applicable.
- Scope `openid` marks this as OIDC Login.
- `redirect-uri` must match the callback registered at the provider.

If the application runs at `https://app.example.com`, the matching callback is:

~~~text
https://app.example.com/login/oauth2/code/corp
~~~

This address must be permitted at the provider. When running behind a reverse proxy, handle forwarded host/scheme reliably so `{baseUrl}` does not resolve to an incorrect HTTP/internal host.

### 15.1. When Is Metadata Fetched?

Spring Boot can create `ClientRegistrationRepository` from properties; while building a registration with `issuer-uri`, the framework typically needs to call the discovery endpoint to fetch provider metadata. Consequently, a wrong issuer config, lack of HTTPS connectivity to the provider, or invalid metadata can cause startup errors.

Common errors:

- issuer URL has the wrong realm/tenant;
- TLS certificate is untrusted;
- DNS/firewall cannot reach the discovery endpoint;
- metadata returns an `issuer` different from the configured issuer;
- fields needed by the library to build the registration are missing;
- proxy/IdP advertises internal endpoints unreachable from the application.

Never solve these by **disabling issuer or signature checks**. Fix the metadata source or deliberately configure manual endpoints according to provider documentation.

## 16. Manual Configuration When the Provider Lacks Standard Discovery

If a provider supports OAuth2 Authorization Code without OIDC Discovery, Spring Boot allows declaring endpoints directly.

Example of **non-OIDC OAuth2 Login**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy:
            provider: legacy-provider
            client-id: ${LEGACY_CLIENT_ID}
            client-secret: ${LEGACY_CLIENT_SECRET}
            client-authentication-method: client_secret_post
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          legacy-provider:
            authorization-uri: https://login-legacy.example.net/authorize
            token-uri: https://login-legacy.example.net/oauth/token
            user-info-uri: https://api-legacy.example.net/v1/me
            user-name-attribute: id
~~~

Suppose the UserInfo-like API returns:

~~~json
{
  "id": "u-179",
  "display_name": "Sample User"
}
~~~

Spring Security uses the `id` field to identify the principal in this kind of OAuth2 Login flow. **How user info is retrieved** (HTTP method, header/token, JSON structure) must match the provider; if the API differs from the default model, customizing `OAuth2UserService` may be required.

Notes:

- No `openid` is present; this is OAuth2 Login integrating a profile API, **not OIDC authentication**.
- Do not set a fake `issuer-uri` if the provider does not support OIDC discovery.
- `client_secret_post` is only an example method for a hypothetical provider, not the default for every provider.
- `user-name-attribute: id` must match **an actual field** in the response, not be guessed from OIDC `sub`.
- If the provider has no suitable user info API, design an appropriate principal-retrieval mechanism per contract; an OAuth2 access token alone is not enough to fabricate an OIDC ID Token.

### 16.1. Declaring Endpoints Manually for an OIDC Provider with Non-Standard Discovery

If a provider genuinely supports OIDC yet does not publish discovery in a way the library consumes, you may need to supply authorization/token/JWK/UserInfo/issuer metadata explicitly, subject to framework support.

Even with manual declaration, the client must still validate the **ID Token** per OIDC standards: issuer, audience, signature, timestamps, and nonce when used. Putting a `jwk-set-uri` in YAML does not prove the provider is OIDC-compatible or that issued tokens are valid ID Tokens.

If unsure whether a provider supports OIDC, confirm ID Token issuance and required standards-compliant checks; never enable OIDC merely by adding `scope: openid`.

## 17. Two Providers in One Application: Organizing Registrations

A Spring Boot application can create multiple `ClientRegistration` entries, each mapping to its own provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope: [openid, profile, email]
          partner:
            provider: partner-oauth
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [profile.read]
        provider:
          corporate-oidc:
            issuer-uri: https://id-corp.example.com
          partner-oauth:
            authorization-uri: https://login-partner.example.net/authorize
            token-uri: https://login-partner.example.net/token
            user-info-uri: https://api-partner.example.net/profile
            user-name-attribute: user_id
~~~

Two default login initiation paths:

~~~text
/oauth2/authorization/corporate
/oauth2/authorization/partner
~~~

Key points:

- `registrationId` is a name chosen by the Spring application, not synonymous with issuer or client ID.
- Each registration can use its own **issuer, endpoints, scopes, and client auth method**.
- The corporate registration includes the `openid` scope and uses OIDC Discovery.
- The partner registration uses a custom OAuth2 Profile API and must not be treated as an OIDC Provider.
- Responses from the two providers can produce different principal types (`OidcUser` or `OAuth2User`), which the application layer must handle.

In real deployments, each registration should declare important properties explicitly such as redirect URI, client auth method, and grant type if defaults do not fit. Also load secrets from the environment rather than storing them in Git.

### 17.1. Do Not Write Code Assuming Every Principal Is `OidcUser`

For example, a controller can accept a common `OAuth2User`:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OAuth2User user) {

        return Map.of(
            "name", user.getName(),
            "attributes", user.getAttributes()
        );
    }
}
~~~

This snippet only illustrates using the common interface: **never expose all raw attributes in a public API in a real application**, as they may contain personal data or provider-internal fields. For OIDC-specific logic (checking `sub`, `iss`, `auth_time`, `acr`), the application must work with `OidcUser` after OIDC Login and read the verified ID Token.

With multiple providers, a better architecture maps diverse principals into an **internal user model** and stores the external identity source. Never use email alone to automatically merge users from untrusted issuers.

## 18. When Should Metadata Be Overridden or Customized?

There are cases where part of the framework-discovered information needs adjustment:

- Metadata returns an authorization endpoint on an internal host while the application only reaches the public host.
- The provider does not publish `userinfo_endpoint`, yet offers a non-standard profile API.
- The token endpoint requires a different client authentication method.
- The provider requires extra authorization parameters.
- The provider serves multiple tenants/realms, each with a different issuer.
- The provider implements only part of an RFC or has incompatible metadata.

Depending on the case, options include:

1. **Fix the provider configuration** so metadata outputs the right URLs and issuer; this is the cleanest solution if your organization owns the IdP.
2. **Declare URI overrides in Spring Boot properties**, if the provider's behavior is verified and the framework supports that combination.
3. **Build `ClientRegistration` via builder** or use `ClientRegistrations.fromIssuerLocation(...)` and adjust the needed fields.
4. **Customize OAuth2 User Service, token client, or authorization request resolver** for extensions with clear contracts.
5. **Introduce a dedicated adapter for non-standard providers**, keeping the upper business logic independent of each identity source's format.

Never use overrides to bypass security invariants like issuer, audience, redirect URI, or ID Token signature checks. If endpoints in metadata are wrong because of a reverse proxy, fix the base URL/public issuer at the IdP or use explicit configuration after verifying trust boundaries.

### 18.1. Example: Building `ClientRegistration` from a Trusted Issuer

In a Servlet application, you can configure a bean manually using discovery:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class RegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.login.issuer}") String issuer,
            @Value("${app.login.client-id}") String clientId,
            @Value("${app.login.client-secret}") String clientSecret) {

        ClientRegistration registration = ClientRegistrations
            .fromIssuerLocation(issuer)
            .registrationId("corporate")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

This approach fetches metadata from the issuer and then explicitly sets data **belonging to the client registration**.

- `issuer` must come from trusted configuration; never take it directly from a user-supplied URL query parameter.
- `clientId` and `clientSecret` do not come from discovery, but from the provider-side registration.
- The client authentication method must match the registered client; if the provider does not use a compatible default, set it explicitly.
- The callback path must be registered at the provider.
- If the application defines its own `ClientRegistrationRepository` bean, Spring Boot auto-configuration may back off from creating a second repository from properties; pick one primary configuration source.

This is **an alternative** to a repository created from `spring.security.oauth2.client.registration.*`. Never define multiple conflicting repository beans without a specific need.

### 18.2. Servlet and WebFlux Configurations Differ at the API Layer

In Servlet:

~~~text
ClientRegistrationRepository
InMemoryClientRegistrationRepository
HttpSecurity / SecurityFilterChain
~~~

In WebFlux:

~~~text
ReactiveClientRegistrationRepository
InMemoryReactiveClientRegistrationRepository
ServerHttpSecurity / SecurityWebFilterChain
~~~

Standard metadata and OIDC requirements do not change between stacks; **Spring Security's Java classes and reactive mechanisms differ**. Never place a Servlet `ClientRegistrationRepository` bean into a WebFlux-only application and expect the reactive flow to use it automatically.

## 19. Operational Limitations of Discovery in Practice

Even a valid metadata document does not eliminate all operational issues.

### 19.1. Discovery Can Depend on Network Connectivity at Startup

When `issuer-uri` is used to build a registration, the application usually must reach the metadata endpoint while creating the bean. If the IdP or DNS is down, the application may fail to start even when no code has changed.

Operational solutions involve choosing appropriately between live discovery, pre-known endpoint configuration, resilience when the IdP is temporarily unavailable, and metadata refresh policies. Never disable TLS validation to "fix" connection errors.

### 19.2. Caching and Key Rotation

The metadata endpoint, JWKS, and other endpoints do not necessarily share the same update lifecycle. A provider may rotate signing keys without changing the issuer or endpoints, or change supported algorithms after an upgrade.

The client must support valid JWK refreshing and monitor verification errors during key rotation. Never treat a metadata snapshot fetched once as immutable forever.

### 19.3. Multi-Tenant Issuers

A provider might use issuers like:

~~~text
https://id.example.com/tenant-a
https://id.example.com/tenant-b
~~~

Each tenant can have a different token issuer, JWKS, endpoints, and policies. Therefore:

- Never swap tenant paths via unchecked string substitution.
- Never use tenant A's keys/JWKS to verify tenant B's tokens merely because they share a host.
- Never dynamically trust a new issuer from an unverified `iss` claim.
- If supporting multiple tenants, maintain a managed repository/routing layer to select the right issuer and registration before authentication.

### 19.4. Metadata Does Not Reflect All User Policies

Even when metadata includes `acr_values_supported` or `scopes_supported`, the provider may enforce conditions per user, organization, IP, MFA, device, consent, or admin policy. A syntactically valid authorization request can still be denied by policy.

For consent or policy errors, the client must not blindly retry other grant types/endpoints; handle OAuth2 error responses cleanly and keep transaction data safe.

### 19.5. Valid Metadata Does Not Guarantee Every Login Session Succeeds

The client also depends on:

- Registered Redirect URI.
- State/PKCE and stored authorization request data.
- Valid client secret/private key.
- Clock skew and code/token lifetimes.
- UserInfo endpoint or UserService.
- Application session/cookies.
- User permissions, consent, and IdP policies.

Thus, **successful discovery is a configuration prerequisite**, not full verification of the entire login journey.

## 20. Workflow for Integrating a New Provider in Spring Security

A technical workflow can follow these steps.

### Step 1: Determine Whether the Provider Supports OIDC or Only OAuth2

First clarify the application's goal:

- Want **OIDC identity login**: the provider must support OIDC, issue valid ID Tokens, and allow the `openid` scope.
- Want **OAuth2 API authorization**: OIDC may be unnecessary; identify the grant type, scopes, and audience/resources required by the API.
- Want **login from a non-OIDC OAuth2 provider**: understand how to fetch profile/principal via the appropriate API and understand the limits of that model.

Do not call every OAuth2 provider an OIDC provider.

### Step 2: Identify Trusted Issuer and Metadata Source

For OIDC, obtain the issuer URI supplied by the provider, fetch the discovery document, and verify `issuer`. For RFC 8414 OAuth2 metadata, read the document via the server's supported mechanism.

Without discovery, obtain endpoints from official docs or a trusted configuration store. Never take an arbitrary URL from a request and treat it as a permitted issuer.

### Step 3: Register the Client

At the provider, register:

- Client ID and client authentication method (secret, assertion, or public client).
- Redirect URIs.
- Allowed grant types.
- Required scopes and authorized APIs.
- PKCE and mandatory options.
- Logout callback/redirect if used.

Then save the corresponding settings into Spring Boot/Spring Security configuration.

### Step 4: Cross-Check Metadata Against Registration

Verify at minimum:

| Item | What to verify |
|---|---|
| Issuer | `issuer` from metadata and trusted issuer |
| Authorization endpoint | Right URL accepting `response_type=code` |
| Token endpoint | Right URL accepting `grant_type=authorization_code` |
| Client authentication | Matches registered method |
| Redirect URI | Exact match per provider rules |
| Scope | Supported by server and granted to client |
| PKCE | Compatible method/verifier/requirement |
| ID Token signing | Verifiable keys/algorithms per OIDC contract |
| UserInfo | Compatible endpoint/format if needed by app |
| Logout | Genuinely supported and redirect registered if needed |

### Step 5: Configure Spring Security OAuth2 Login

In a Servlet application, minimal example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

`ClientRegistration` configured via `application.yml` or a repository bean supplies the corresponding provider metadata.

### Step 6: Observe the Actual Flow and Handle Differences

Walk through:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Security OAuth2 Client
    participant P as OAuth2 / OIDC Provider
    U->>C: GET /oauth2/authorization/demo
    Note over C: Look up ClientRegistration & configured metadata
    C-->>U: 302 authorization_endpoint
    U->>P: Authorization request (scope, state, PKCE...)
    P-->>U: 302 callback?code=...&state=...
    U->>C: GET /login/oauth2/code/demo
    Note over C: Verify state & authorization request
    C->>P: POST token_endpoint (code, client auth, verifier)
    P-->>C: Tokens or OAuth2 error
    Note over C: If OIDC: verify ID Token
    C-->>U: Create session or show safe error
~~~

Verify actual data at each step without **logging codes/tokens/secrets**. For providers with custom profile APIs, also trace the user-info retrieval step and inspect the created principal type.

### Step 7: Normalize Data for the Business Layer

Do not let business controllers/services depend directly on provider-specific claim names.

Example internal mapping:

~~~text
OIDC Provider A:
  iss + sub -> external identity
  preferred_username -> display name (if present)

OAuth2 Provider B:
  provider ID + profile.id -> external identity
  display_name -> display name (if present)

                 |
                 v

InternalUser {
  localUserId
  externalProviderKey
  externalSubject
  displayName
  authorities
}
~~~

The normalization layer must preserve **the trusted identity source**. For OIDC, the `(iss, sub)` pair is primary; for pure OAuth2 providers, use an explicit provider-specific identifier and contract. Never automatically link accounts based solely on unverified email.

## 21. Common Differences and How to Handle Them

| Difference | Integration symptom | How to handle |
|---|---|---|
| No standard discovery | `issuer-uri` fails to fetch metadata | Declare endpoints manually; confirm whether provider supports OIDC or only OAuth2. |
| Wrong metadata issuer | Discovery or ID Token validation fails | Configure the right issuer/public base URL at the provider; do not skip issuer checks. |
| Authorization endpoint differs from guessed path | Wrong redirect or 404 | Use URL from official metadata/docs. |
| Different token client auth method | `invalid_client` | Match the registered client method. |
| PKCE required | `invalid_request` or `invalid_grant` | Enable PKCE `S256` and preserve verifier throughout the transaction. |
| Scope not granted | `invalid_scope` or missing expected permissions/tokens | Check client registration, consent, and policy. |
| No UserInfo | Fails to load profile via default mechanism | Use ID Token data if appropriate or a provider-specific `OAuth2UserService`/adapter. |
| Different principal field name | Fails to build `OAuth2User` or wrong username | Configure `user-name-attribute` or user service. |
| Different refresh token policy | No refresh token or refresh fails | Adjust scope requests/policies and authorized client lifecycle. |
| JWKS key rotation | ID Token suddenly fails signature check | Verify JWK retrieval/caching and exact issuer. |
| Missing optional claims | Null fields, broken profile mapping | Handle optionals or request scopes/claims under a clear contract. |
| Different logout behavior | Local logout succeeds yet SSO stays active | Design logout matching the provider and supported endpoints. |
| Different multi-tenant metadata | Token issuer/audience mismatch | Bind registrations to the exact tenant/issuer. |
| Provider-specific parameters | Authorization request rejected | Controlled custom resolver/request. |
| Access token is not a JWT | JWT parsing fails | Handle tokens per API contract; do not assume format. |

This table focuses on **differences that may arise**. Not every provider exhibits all of these constraints.

## 22. Design Mistakes to Avoid

### 22.1. "Having `issuer-uri` Means Spring Supports Every Provider"

False: `issuer-uri` is only useful when the provider has metadata compatible with the discovery mechanism used by the framework. A pure OAuth2 API may need explicit authorization/token URIs and a custom user service.

### 22.2. "If Metadata Lists a Scope, the Client Gets That Scope"

False: metadata describes server capabilities, while client registration, consent, and policy decide granted scopes. Refresh tokens also have their own policies.

### 22.3. "Provider Returns a JWT, So It Must Be OIDC"

False: a JWT access token is not an ID Token. OIDC requires the `openid` scope, a compliant ID Token, and corresponding validation steps.

### 22.4. "Every Provider Has the Same User Attributes"

False: some providers return `sub` per OIDC, pure OAuth2 providers return `id` or `user_id`, and email may be absent or unverified. Normalize according to contract.

### 22.5. "Missing Optional Metadata Proves the Provider Lacks That Feature"

False in many cases: some fields have spec defaults, or features are documented outside discovery or governed by private policy. Check provider docs and actual behavior rather than guessing.

### 22.6. "A Valid ID Token Signature Is Enough"

False: you must verify issuer, audience, expiration, and related OIDC constraints; a token valid for another client must never be accepted.

### 22.7. "Changing `tokenUri` Is Enough to Switch Tenants"

False: multi-tenant providers may change issuer, JWK Set, scopes, policies, client registration, and UserInfo endpoint. Map the entire trusted registration.

### 22.8. "App Logout Always Revokes Tokens and Logs Out of the IdP"

False: local session, IdP SSO session, and token lifecycle are three separate concerns handled per protocol and provider.

### 22.9. "Every Client Has a `client_secret`"

False: public clients cannot safely hold a secret. Choose client authentication and PKCE suited to the application model.

### 22.10. "Reading Metadata over HTTP Without TLS Verification Is Fine"

False: metadata is the source of endpoints/keys and directly affects trust boundaries. Production deployments must access it over secure connections, configure trusted issuers, and never fetch metadata from user-supplied hosts.

## 23. Practice Scenarios

### Scenario A: OIDC Metadata Advertises Multiple Client Authentication Methods

Metadata:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

The application's administrative registration requires `private_key_jwt`.

**How to handle:** select `private_key_jwt` and configure the matching keys/assertion. Do not use `client_secret_basic` merely because the library has a convenient default.

### Scenario B: Discovery Succeeds, Yet Callback Is Rejected

Metadata provides valid authorization/token endpoints. On login, the provider reports the redirect URI is unacceptable.

**How to handle:** inspect the actual `redirect-uri` sent by Spring and the client's allowlist at the provider. Successful discovery does not prove the callback is authorized.

### Scenario C: Provider Has `email` Scope, Yet ID Token Lacks `email`

Metadata advertises `email` and the client requests `openid email`. The ID Token contains only `iss`, `sub`, `aud`, `exp`, `iat`.

**How to handle:** still validate the ID Token via mandatory claims; treat email as optional data, potentially fetched from UserInfo if supported/permitted. Never replace `sub` with email or assume email is verified.

### Scenario D: Provider Only Has OAuth 2.0 Authorization Server Metadata

The provider publishes `authorization_endpoint`, `token_endpoint`, and `jwks_uri`, yet has no ID Token or OIDC Discovery.

**How to handle:** use OAuth2 Client for the required grants/APIs. If the problem requires standard OIDC login, choose or configure a provider that genuinely supports OIDC; never call a JWT access token an ID Token.

### Scenario E: Provider Rotates Signing Keys

A day after deployment, new ID Tokens carry a `kid` absent from the old cached JWK Set.

**How to handle:** check how Spring Security/the JWK client refreshes its cache, verify endpoint/certificates and issuer; never disable signature verification. If the provider rotates keys on a schedule, monitor rotation events and new key distribution.

### Scenario F: Two Tenants on the Same Host

Tenant A's token has issuer `https://id.example.com/tenant-a`; the application expects tenant B `https://id.example.com/tenant-b`.

**How to handle:** reject tokens with the wrong issuer, even on the same host. If the application supports both tenants, map trusted registrations and user identities per respective issuer.

### Scenario G: Provider Supports Refresh Tokens, Yet Does Not Issue One to the Client

Metadata does not rule out refresh tokens, yet the token response omits `refresh_token`.

**How to handle:** check grant, scope, consent, client type, and admin policies. Do not assume the token response is broken; some providers only issue refresh tokens when specific conditions are met.

### Scenario H: OAuth2 Provider Returns `user_id` Instead of `sub`

The application has a UserInfo adapter receiving:

~~~json
{
  "user_id": "partner-417",
  "display_name": "Example Person"
}
~~~

**How to handle:** for OAuth2 Login, configure `user-name-attribute: user_id` if the response works with the default mechanism; otherwise customize the user service. Do not mechanically apply OIDC `iss + sub` rules to a profile API without the OIDC protocol.

## 24. Self-Check Questions

**Question 1.** Are OIDC Discovery and OAuth2 Authorization Server Metadata completely identical?

**Answer:** No. They share many concepts such as issuer and authorization/token endpoints, but OIDC Discovery also describes capabilities related to ID Tokens, subjects, and user authentication. An OAuth2 server is not automatically an OIDC Provider.

**Question 2.** If `scopes_supported` includes `offline_access`, is the client guaranteed to receive a refresh token?

**Answer:** No. It still depends on client registration, grant type, consent, provider policy, and the actual token response.

**Question 3.** When a provider only supports `client_secret_post` for the registered client, what should you do?

**Answer:** Configure the matching client authentication method in Spring Security, send the secret via the required method over HTTPS, and verify the contract with the provider.

**Question 4.** Why should email not be used as an account identifier across providers?

**Answer:** Email can change, be missing, be recycled, or be unverified. For OIDC, use the `(issuer, subject)` pair to identify users per OP.

**Question 5.** Does an OIDC Provider missing `end_session_endpoint` cause authorization code login to fail?

**Answer:** Not necessarily. The logout endpoint is a separate capability from login; design logout handling to match what the provider supports.

**Question 6.** Does the absence of `code_challenge_methods_supported` prove the provider does not support PKCE?

**Answer:** No. Check documentation, client settings, and actual behavior; do not infer from a single optional metadata field.

**Question 7.** Why must `issuer` be verified accurately even when JWKS is present?

**Answer:** JWKS/keys verify the signature, whereas the issuer binds the token to the exact trusted OP. Combine all token verification conditions, including audience and expiration.

**Question 8.** When should `authorization-uri`, `token-uri`, and `user-info-uri` be declared manually?

**Answer:** When a provider lacks compatible discovery or when integrating a non-standard OAuth2 profile API per vendor docs. Know clearly whether it is pure OAuth2 or true OIDC.

**Question 9.** Does a provider advertising `private_key_jwt` mean Spring automatically has a private key to sign assertions?

**Answer:** No. The application must have the client registration, keys, and assertion-signing component properly configured.

**Question 10.** Why should you not dynamically select a provider from an `issuer` entered by a user?

**Answer:** Because it can lead to fetching metadata from untrusted sources, breaking issuer boundaries, and risks such as SSRF or login mix-up. Maintain a managed, trusted list/mapping of providers.

## 25. Key Takeaways

| Point to remember | How to apply in Spring Security OAuth2/OIDC Client |
|---|---|
| **Metadata describes the server, not client permissions** | Always cross-check client registration, scopes, and actual policies. |
| **OIDC Discovery differs from general OAuth2 metadata** | Only use OIDC Login when the provider genuinely issues ID Tokens and supports OIDC requests. |
| **Issuer is a trust boundary** | Configure exact issuers, verify `iss`, and never accept arbitrary issuers. |
| **Endpoints have no universal URL across vendors** | Use valid discovery or configure URIs per provider documentation. |
| **Client auth method must match registration** | Choose `client_secret_basic`, `client_secret_post`, `private_key_jwt`, etc. per contract. |
| **PKCE must be checked per client/provider** | Prefer `S256`, preserve the verifier across the transaction, and do not guess from missing metadata fields. |
| **Claims and UserInfo can differ** | Handle optional claims and normalize principals in the application layer. |
| **JWKS can rotate keys** | Use trusted key verification and refresh mechanisms; never hard-code immutable keys. |
| **Refresh/logout/revocation are separate capabilities** | Read provider metadata and policies; do not assume they are always available. |
| **One application can have multiple registrations** | Use separate `spring.security.oauth2.client.registration.*` and `provider.*` blocks. |

When integrating a new provider, start from **the protocol the provider genuinely supports**, obtain metadata from a trusted source, compare it against **the issued client registration**, configure `ClientRegistration` accurately, and observe the **actual authorization code flow**. This approach keeps a Spring Security application compatible with diverse providers while upholding issuer, audience, token, and OIDC security requirements.
