# Authenticating and Authorizing Clients Allowed to Introspect

## Lesson Objectives

In the **Introspection** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you on how to authenticate applications calling the **OAuth 2.0 Token Introspection Endpoint** and authorize which tokens those applications are allowed to look up. The content focuses on **Spring Security**, **Spring Authorization Server**, and **Spring Boot** in an OAuth 2.0/OpenID Connect Authorization Server system.

Token introspection is a sensitive operation: the endpoint receives a bearer credential and returns information about the token's status, scopes, subject, audience, expiration, and authorization context. If you only check whether the client authenticated successfully without controlling which tokens the client is allowed to inspect, a compromised Resource Server can become a tool for token scanning or harvesting information belonging to another system.

After this lesson, you will be able to:

- Distinguish **authenticating the introspection caller client** from **authorizing which token information the client may view**.
- Explain endpoint protection requirements according to RFC 7662, especially against token scanning and status leakage.
- Configure client authentication for introspection using **client_secret_basic**, **private_key_jwt**, or mTLS when appropriate.
- Register a dedicated Resource Server/Protected Resource in **RegisteredClientRepository** and manage its credentials.
- Design allowlists/policies based on client identity, audience/resource, token type, tenant, and scope.
- Extend **OAuth2TokenIntrospectionAuthenticationProvider** via **OAuth2TokenIntrospectionEndpointConfigurer** while preserving standard token processing.
- Return **active=false** for tokens that do not exist, are inactive, or that the caller is not authorized to know about.
- Restrict returned claims, protect logs, apply rate limits, cache safely, and test both valid and rejected cases.

> **End-to-end scenario:** **inventory-api** is a Resource Server calling **POST /oauth2/introspect** to verify access tokens. A token may be issued for **inventory-worker**, **employee-portal**, or a partner. **inventory-api** may only look up tokens intended for the **inventory-api** audience; it must not read information from tokens intended only for **billing-api**.

## 1. Introspection Is a Privileged Endpoint

According to RFC 7662, the Token Introspection Endpoint receives a token and returns JSON describing the token's metadata, in which the **active** field indicates whether the token is currently active. The endpoint is typically called by a Resource Server/Protected Resource to decide whether to accept the token for the current request.

Introspection is useful for opaque/reference tokens because the Resource Server cannot verify status from the token string itself. It can also be used with JWTs when the system wants to check revocation status or the latest policy at the Authorization Server.

### 1.1. Who Calls the Endpoint and Which Token Is Looked Up?

There are two independent identities:

| Identity | Role | Example |
|---|---|---|
| **Introspection caller** | Application/Resource Server calling the endpoint. | **inventory-api-introspector** |
| **Token subject / issuing client** | Subject or client for which the token was issued. | **inventory-worker** |
| **Target Resource Server** | API that will use the metadata to make a decision. | **inventory-api** |
| **Authorization Server** | Component that authenticates the caller, looks up token state, and returns the response. | **auth.example.com** |

The Client ID used to authenticate the introspection caller may **differ** from the Client ID returned in the response for the token being looked up. A Resource Server may need to introspect tokens issued to multiple OAuth2 clients; that does not mean every Resource Server is allowed to look up every token.

**Do not confuse the two credentials:**

- The credential of **inventory-api-introspector** proves that the application is allowed to call the introspection endpoint.
- The access token in the **token** body is the object being looked up.
- These two values are not the same and must not be substituted for each other.

### 1.2. Two Layers of Control: Authentication and Authorization

~~~mermaid
flowchart TD
    A[POST /oauth2/introspect] --> B[Client Authentication Filter]
    B --> C{Is caller credential valid?}
    C -->|No| D[401 Unauthorized]
    C -->|Yes| E[OAuth2TokenIntrospectionAuthenticationToken]
    E --> F[Introspection AuthenticationProvider]
    F --> G[Look up token and check status]
    G --> H{Is caller allowed to know this token?}
    H -->|No| I[200 active=false]
    H -->|Yes| J{Is token still valid?}
    J -->|No| I
    J -->|Yes| K[200 active=true + permitted claims]
    K --> L[Resource Server checks scope, audience, and API policy]
~~~

- **Authentication:** Who is calling? Does the credential match a registered client?
- **Authorization:** Is that authenticated client allowed to introspect this specific token?
- **Token validation:** Does the token exist, is it unexpired, unrevoked, and meeting active conditions?
- **Resource authorization:** Does the API allow the token to access the current endpoint/business object?

Passing Authentication alone does not mean passing Authorization. A validly authenticated client may still not be permitted to inspect another resource's tokens.

## 2. RFC 7662 Requirements

### 2.1. Introspection Request

RFC 7662 Section 2.1 requires the Protected Resource to send an HTTP **POST** with an **application/x-www-form-urlencoded** body. The **token** field is required; **token_type_hint** may be sent to suggest the token type.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <BASE64_CLIENT_CREDENTIAL>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN_TO_INSPECT>&token_type_hint=access_token
~~~

The values in angle brackets are placeholders. Real requests must use HTTPS/TLS, verify the server certificate, and keep both the client credential and token body confidential.

**Do not send tokens via query strings or GET URLs.** URLs are often recorded in reverse proxy logs, browser history, monitoring, and tracing. A POST form-urlencoded body keeps the token out of the URL, though you still need redaction configured at the gateway/APM.

### 2.2. Why Must the Endpoint Require Authorization?

RFC 7662 Section 2.1 requires the endpoint to have an authorization mechanism to prevent token scanning. An attacker could send batches of guessed values and use the responses to discover valid tokens. The RFC allows protection via client authentication or a separate access token authorized to call the endpoint.

RFC 7662 Section 4 also recommends that the Authorization Server **explicitly authorize which Protected Resources are permitted to introspect**. This is why per-caller policies and scoping of inspectable tokens are necessary.

Principles:

1. Do not expose the introspection endpoint publicly for anyone to submit tokens.
2. Do not treat a bare client ID of a public client as a strong credential.
3. Only issue credentials to Resource Servers/Protected Resources with a clear owner and need.
4. Restrict each caller by resource/audience, tenant, token type, and required claims.
5. If a separate access token is used to call introspection, that token must be scoped exclusively for this purpose and authorized at the endpoint.

### 2.3. Anti-Token-Scanning Rule: Return active=false

RFC 7662 Section 2.2 specifies that if the request is validly authorized but the token:

- Is inactive or expired.
- Does not exist at the Authorization Server.
- Has been revoked.
- Is a token that the calling Protected Resource **is not permitted to know about**.

then the server must return an introspection response with **active=false**. The server **should not** include additional information explaining why the token is inactive.

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": false
}
~~~

This avoids creating an oracle that reveals whether a token exists, which client it belongs to, or why it was revoked.

Distinguish this from caller credential errors:

| Case | Appropriate Response |
|---|---|
| Caller fails authentication with client credential | HTTP 401 per the client authentication mechanism. |
| Request is missing token or malformed | Appropriate OAuth2 error response, typically HTTP 400. |
| Caller is authenticated, token does not exist | HTTP 200 with **active=false**. |
| Caller is authenticated, token is expired/revoked | HTTP 200 with **active=false**. |
| Caller is authenticated but not allowed to know this token | HTTP 200 with **active=false**, no further explanation. |
| Caller is authorized, token is active | HTTP 200 with **active=true** and permitted metadata. |

Do not return **403 token belongs to billing-api** or **404 token exists but forbidden** for a specific token; those responses leak internal state.

## 3. Introspection Response and Permitted Data

### 3.1. Response for an Active Token

RFC 7662 example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "client_id": "inventory-worker",
  "scope": "inventory.read",
  "sub": "service-inventory",
  "aud": ["inventory-api"],
  "iss": "https://auth.example.com",
  "exp": 1794861000,
  "iat": 1794859200,
  "token_type": "Bearer"
}
~~~

The response contains metadata about the **looked-up token**, not the full profile of the introspection caller.

| Claim | Meaning | Authorization Note |
|---|---|---|
| **active** | Whether the token is currently active. | Required boolean. |
| **client_id** | Client that requested/generated the token. | Not the client calling introspection. |
| **scope** | Permissions granted to the token. | Only return scopes needed by the calling Resource Server. |
| **sub** | Subject of the token. | May be a user or machine principal; protect PII. |
| **aud** | Resource/audience the token is targeted at. | Used to verify the caller belongs to an allowed audience. |
| **iss** | Issuer of the token. | Helps the Resource Server bind the trust domain. |
| **exp**, **iat**, **nbf** | Token timestamps. | Used for decisions and safe caching. |
| **jti** | Token identifier, if present. | Can be sensitive in correlation systems. |
| Extension fields | Server-defined metadata. | Return only per policy; do not leak unnecessary internal data. |

### 3.2. Same Token, Different Responses by Caller

RFC 7662 allows the Authorization Server to return different responses to different Protected Resources when introspecting the same token. For example:

- **inventory-api** only needs **scope**, **aud**, **exp**, and the machine **sub**.
- **billing-api** may be allowed to see a different set of claims if the token actually targets billing.
- An API may only be allowed to know **active** and **scope**, without seeing username/email or metadata from other systems.

This reduces the amount of data exposed if one Resource Server is compromised. Do not build a single introspection response containing all claims for every client and rely on each API to ignore what it does not need.

### 3.3. Audience and Scope Are Not Introspection Permission

- A token's **aud** describes the resource receiving the token.
- **scope** describes the token's permissions when accessing an API.
- Introspection permission is **the caller's permission over token data**, determined by the Authorization Server's policy.

A token with the **inventory.read** scope does not automatically grant a client any right to call introspection. Similarly, a client registering the **inventory.read** scope does not mean it is allowed to inspect tokens of every application with that scope.

## 4. Registering and Authenticating Introspection Callers in Spring Authorization Server

Spring Authorization Server 1.5.x configures client authentication via **OAuth2ClientAuthenticationFilter**. By default, client authentication is required at the Token Endpoint, Token Introspection Endpoint, and Token Revocation Endpoint.

Commonly supported methods include:

| Method | Description | Recommendation for Introspection Services |
|---|---|---|
| **client_secret_basic** | Client ID/secret in HTTP Basic. | Suitable with strong secrets, TLS, and proper rotation. |
| **client_secret_post** | Client ID/secret in form body. | Use only when compatibility requires it; requires body redaction. |
| **private_key_jwt** | Client signs a JWT assertion with a private key. | Good when PKI/key management and assertion validation are in place. |
| **client_secret_jwt** | JWT assertion verified with a shared secret. | Use according to policy/version support. |
| **tls_client_auth** | Authentication using an mTLS client certificate. | Suitable for service-to-service with PKI. |
| **self_signed_tls_client_auth** | mTLS with a registered self-signed certificate. | Requires strict certificate pinning/rotation management. |
| **none** | Public client without a client secret. | Should not be used as the sole protection for the introspection endpoint. |

### 4.1. An Introspection Client Is a Dedicated RegisteredClient

Architecture example:

| Registered client | Purpose | Credential |
|---|---|---|
| **inventory-worker** | Request access tokens to call Inventory API. | Worker's credential. |
| **employee-portal** | Perform employee login/authorization. | Portal's credential. |
| **inventory-api-introspector** | Call introspection to verify tokens reaching Inventory API. | Dedicated secret or private key/certificate. |
| **billing-api-introspector** | Call introspection for Billing API. | Separate credential from inventory. |

Separating callers per Resource Server allows revoking or rotating one API's credentials without affecting other APIs. Do not share **inventory-worker**'s secret with **inventory-api-introspector** just because both belong to the same product.

In **RegisteredClientRepository**, the introspection caller must have a valid registration and corresponding client authentication method. Registering the **client_credentials** grant is only needed if that client also needs to request access tokens via that grant; it **does not automatically grant introspection permission**.

### 4.2. Resource Server Configuring Introspection Credentials

With Spring Security Resource Server using opaque tokens, Spring Boot can configure the endpoint and credentials:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: secret-from-secret-manager
~~~

This is configuration on the **Resource Server**, not the Authorization Server. The secret must be injected from a secret manager/credential store and never committed to YAML. The Resource Server uses this credential to authenticate when sending introspection requests.

If a Resource Server requires introspection permissions restricted by audience, the Authorization Server must check whether the caller **inventory-api-introspector** is allowed to inspect tokens with the corresponding **aud**. Merely setting client ID and client secret on the Resource Server does not create that policy.

## 5. Authorizing Clients Allowed to Introspect

### 5.1. Building a Policy by Caller and Token

A practical policy should check at least:

1. **Caller identity:** Which authenticated RegisteredClient is calling?
2. **Resource/audience:** Which API was the token issued for?
3. **Token type:** Is the caller allowed to introspect access tokens, refresh tokens, or extension token types?
4. **Tenant/domain:** Which tenant or trust domain does the token belong to?
5. **Data disclosure:** Which claims is the caller allowed to view?
6. **Operational status:** Is the caller disabled, is its credential expired, or is it rate-limited?

Example permission matrix:

| Introspection caller | Token audience | Result |
|---|---|---|
| **inventory-api-introspector** | **inventory-api** | Allowed; return claims needed for inventory. |
| **inventory-api-introspector** | **billing-api** | Denied; return **active=false**. |
| **billing-api-introspector** | **billing-api** | Allowed; return claims needed for billing. |
| **support-tool-introspector** | Any audience | Allowed only with approved support authorization, audit, and time limits. |
| Unregistered client or wrong credential | Any | Client authentication fails. |

Do not use client names or scopes sent by the caller in the token request body as the basis for granting permissions. Caller identity must come from the Authentication verified by the filter.

### 5.2. Allowlist by Audience/Resource

An easily controllable policy maps introspection clients to allowed audiences:

~~~text
inventory-api-introspector -> inventory-api
billing-api-introspector   -> billing-api
reporting-introspector     -> reporting-api
~~~

When the provider processes a request:
- Obtain the client ID from the authenticated RegisteredClient.
- Look up the authorization/token record from **OAuth2AuthorizationService**.
- Read the audience/resource metadata from the access token or authorization attributes according to the system schema.
- Compare the audience against the caller's allowlist.
- If the caller is not permitted, return the minimal inactive response.
- If permitted, delegate token activity checking and claims generation to the standard provider.

Audience must be issued from a trusted policy source. Do not infer audience solely from the token's client ID if the system has multiple APIs or tokens can target multiple resources.

### 5.3. An Allowlist Does Not Replace Scope and Tenant Checks

A caller allowed to introspect **inventory-api** must still receive only the appropriate scope of data:

- Return only the scopes Inventory API needs to decide the request.
- Return only the necessary subject/tenant claims.
- Do not disclose email, employee name, internal roles, or billing metadata if unrelated.
- If a token carries multiple audiences, the response can be scoped to the current caller.
- The Resource Server continues checking scopes, audience, tenant, and permissions at the actual endpoint.

### 5.4. Do Not Implicitly Use RegisteredClient.scope as Introspection Permission

**RegisteredClient.getScopes()** describes the scopes a client can request when obtaining a token. It is not a list of audiences or a list of tokens allowed to be looked up.

You can build a dedicated policy registry or use application metadata managed alongside the registration, but give it clear naming and semantics, for example:

- **allowedIntrospectionAudiences**.
- **allowedIntrospectionTokenTypes**.
- **introspectionClaimProfile**.
- **introspectionEnabled**.

These attributes are **application-defined schema**, not built-in default fields in every **RegisteredClient**.

## 6. Configuring the Token Introspection Endpoint in Spring Authorization Server

**OAuth2AuthorizationServerConfigurer** provides **tokenIntrospectionEndpoint(...)** to configure the endpoint. **OAuth2TokenIntrospectionEndpointConfigurer** exposes the following extension points:

| API | Role |
|---|---|
| **introspectionRequestConverter(...)** | Add a converter to parse requests into **OAuth2TokenIntrospectionAuthenticationToken**. |
| **introspectionRequestConverters(...)** | Access the default converter list to add/adjust converters. |
| **authenticationProvider(...)** | Add a provider to handle introspection authentication. |
| **authenticationProviders(...)** | Access the default provider list to add/replace providers. |
| **introspectionResponseHandler(...)** | Handle successful responses and serialize **OAuth2TokenIntrospection**. |
| **errorResponseHandler(...)** | Handle OAuth2 errors when authentication/request fails. |

Skeleton configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    var authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenIntrospectionEndpoint(introspection -> {
                // Register custom policy/provider here.
            }))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is an illustrative skeleton for Spring Authorization Server 1.x. A complete application also needs **RegisteredClientRepository**, **OAuth2AuthorizationService**, **AuthorizationServerSettings**, token generator/JWK, and other filter chains for supported grants.

### 6.1. Default Components

According to the Spring Authorization Server 1.5.8 documentation, **OAuth2TokenIntrospectionEndpointFilter** is configured with:

- **OAuth2TokenIntrospectionAuthenticationConverter** to parse requests.
- An **AuthenticationManager** containing **OAuth2TokenIntrospectionAuthenticationProvider**.
- An internal success handler creating the **OAuth2TokenIntrospection** response.
- **OAuth2ErrorAuthenticationFailureHandler** to return OAuth2 errors.

**OAuth2TokenIntrospectionAuthenticationProvider** takes **RegisteredClientRepository** and **OAuth2AuthorizationService**. The standard provider is responsible for processing token introspection and building the result from authorization/token state.

**Keep the default converter and success/error handlers unless there is a specific requirement.** If you only need a caller-to-token policy, focus on the provider. Do not re-parse or re-serialize the entire protocol yourself.

## 7. Adding Policy to the Provider While Preserving Standard Token Processing

### 7.1. Available Authentication Data

**OAuth2TokenIntrospectionAuthenticationToken** contains:

- The token sent in the request via **getToken()**.
- The authenticated client principal via **getPrincipal()**.
- **token_type_hint** via **getTokenTypeHint()**.
- Additional parameters, if any.

The client principal is typically **OAuth2ClientAuthenticationToken** after **OAuth2ClientAuthenticationFilter** authenticates it. Retrieve the RegisteredClient from the authenticated principal; do not take a caller ID from arbitrary parameters.

### 7.2. Application-Defined Policy Interface

Example interface:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

interface IntrospectionAccessPolicy {

    boolean mayIntrospect(
            RegisteredClient caller,
            OAuth2Authorization targetAuthorization,
            String tokenTypeHint);
}
~~~

**IntrospectionAccessPolicy** is an **application-implemented** interface, not a built-in Spring API. Implementations can check audience allowlists, tenant, token type, and claim profiles. If the authorization does not contain an explicit audience, design metadata/resource association with a trusted source rather than guessing.

### 7.3. Wrapping the Standard Provider

You can wrap **OAuth2TokenIntrospectionAuthenticationProvider** to add an authorization check, then delegate token state verification to the standard provider:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenIntrospection;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2TokenIntrospectionAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2TokenIntrospectionAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

final class ClientAwareIntrospectionAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenIntrospectionAuthenticationProvider delegate;
    private final IntrospectionAccessPolicy accessPolicy;

    ClientAwareIntrospectionAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenIntrospectionAuthenticationProvider delegate,
            IntrospectionAccessPolicy accessPolicy) {
        this.authorizationService = authorizationService;
        this.delegate = delegate;
        this.accessPolicy = accessPolicy;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        OAuth2TokenIntrospectionAuthenticationToken request =
                (OAuth2TokenIntrospectionAuthenticationToken) authentication;

        if (!(request.getPrincipal() instanceof
                OAuth2ClientAuthenticationToken clientAuthentication)
                || !clientAuthentication.isAuthenticated()
                || clientAuthentication.getRegisteredClient() == null) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
        }

        RegisteredClient caller = clientAuthentication.getRegisteredClient();

        OAuth2Authorization targetAuthorization =
                this.authorizationService.findByToken(request.getToken(), null);

        if (targetAuthorization != null
                && !this.accessPolicy.mayIntrospect(
                        caller,
                        targetAuthorization,
                        request.getTokenTypeHint())) {

            // Do not disclose whether the token exists, which client owns it, or why it was denied.
            OAuth2TokenIntrospection inactive =
                    OAuth2TokenIntrospection.builder(false).build();

            return new OAuth2TokenIntrospectionAuthenticationToken(
                    request.getToken(), clientAuthentication, inactive);
        }

        // Standard provider checks token status and builds the claims response.
        return this.delegate.authenticate(authentication);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OAuth2TokenIntrospectionAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
~~~

This is an implementation pattern for Spring Authorization Server 1.x APIs; test against your exact dependency version and your application's actual token types. Key points:

- **OAuth2AuthorizationService.findByToken(...)** is used to look up the corresponding authorization; pass the appropriate token type hint if the policy needs to distinguish token types.
- **token_type_hint** is only a lookup optimization hint; never treat it as proof of token type or caller permission. Policy must be based on the actual found token/authorization.
- The caller is obtained from the authenticated **OAuth2ClientAuthenticationToken**.
- If the token exists but the caller is not allowed to know about it, the provider returns the minimal inactive result.
- If the token is not found, the standard provider continues processing and returns inactive according to its behavior.
- If the caller is permitted, the standard provider still performs active/expiry/revocation checks and builds claims.
- Do not log **request.getToken()** or the entire authentication object.

In a real application, safely handle cases where the principal has the wrong type or lacks a RegisteredClient. The client authentication filter must ensure requests reaching the provider carry a valid client principal; still keep guards and regression tests.

### 7.4. Replacing the Default Provider in the List

**authenticationProviders(...)** gives access to the default provider list. You can replace the introspection provider with the wrapper at the same position to preserve processing order:

~~~java
.tokenIntrospectionEndpoint(introspection ->
    introspection.authenticationProviders(providers -> {
        for (int i = 0; i < providers.size(); i++) {
            AuthenticationProvider provider = providers.get(i);

            if (provider instanceof
                    OAuth2TokenIntrospectionAuthenticationProvider standard) {

                providers.set(i,
                    new ClientAwareIntrospectionAuthenticationProvider(
                        authorizationService,
                        standard,
                        introspectionAccessPolicy));
                break;
            }
        }
    }))
~~~

**authorizationService** and **introspectionAccessPolicy** are application beans. This snippet resides inside the **OAuth2AuthorizationServerConfigurer** configuration lambda; import **AuthenticationProvider** and the corresponding classes.

If the default provider is not found in the version in use, do not silently skip the policy. Check the API/version, fail startup, or have tests ensuring the policy is properly installed. Do not add an uncontrolled, unordered provider and assume it always runs before the standard provider.

### 7.5. Why Return Inactive Instead of Throwing Forbidden?

For a caller that is authenticated and generally permitted to call the endpoint, RFC 7662 requires an **active=false** response when the token is inactive or the caller is not allowed to know about that token. Throwing AccessDeniedException or returning HTTP 403 with a message like "token exists but forbidden" can reveal the token's existence.

Conversely, if the caller **cannot be authenticated** or is not generally permitted to call the introspection endpoint, the request must be rejected at the endpoint/client authentication layer. Do not use **active=false** to mask the caller's own credential error.

## 8. Restricting Response Claims per Resource Server

### 8.1. The Response Handler Is a Post-Processing Layer

**introspectionResponseHandler(...)** receives a successful authentication and returns the JSON response. It can be used to adjust claim projection per caller, but the authorization policy needs to be checked **before** generating the result. The response handler should not be the only place deciding whether a caller may introspect a token.

Example response for Inventory API:

~~~json
{
  "active": true,
  "client_id": "inventory-worker",
  "scope": "inventory.read",
  "aud": ["inventory-api"],
  "sub": "service-inventory",
  "exp": 1794861000
}
~~~

Do not return **email**, **phone_number**, Billing's permission lists, or internal information if Inventory API does not need them.

### 8.2. Policy-Based Claim Projection

An **IntrospectionAccessPolicy** or related component can determine the response profile:

| Caller | Minimum Claims |
|---|---|
| **inventory-api-introspector** | **active**, **scope**, **aud**, **exp**, machine **sub**. |
| **billing-api-introspector** | **active**, **scope**, **aud**, **exp**, subject needed for billing. |
| **analytics-introspector** | **active**, scope/audience needed for reporting, no PII unless required. |

If customizing **OAuth2TokenIntrospection** or the response handler, preserve standard fields and **active** semantics. Never return claims removed by policy simply because they happen to exist in the JWT payload or authorization record.

### 8.3. Claims of JWT Tokens vs. Opaque Tokens

- For JWT access tokens, the Authorization Server can read claims stored in the authorization/token wrapper or verify the JWT using an appropriate mechanism.
- For opaque/reference tokens, metadata resides in the authorization store and is retrieved by the provider/introspection service.
- Do not assume all tokens have the same set of claims.
- Do not parse JWT payloads manually while skipping signature, issuer, expiry, or revocation status checks.
- Do not return all custom claims just because the token generator added them.

## 9. Endpoint Protection and Operations

### 9.1. TLS and Client Credentials

RFC 7662 requires TLS for the introspection endpoint. The caller must verify the server certificate. For client authentication:

- Use sufficiently strong secrets; never use default/demo secrets in production.
- Prefer private_key_jwt or mTLS when infrastructure supports it and proper key management is in place.
- Separate credentials per Resource Server.
- Rotate credentials with overlap/rollout, auditing, and rollback.
- Never place credentials in source code, container images, command history, or logs.
- Never allow unencrypted HTTP on internal ingress just because traffic is on a private network.

### 9.2. Rate Limiting and Anti-Token-Scanning

Apply:

- Rate limiting by authenticated client ID and optionally by IP/network identity.
- Request body size and token length limits.
- Concurrency limits and timeouts to authorization storage.
- Auditing of introspection counts, inactive rates, client authentication errors, and latency.
- Alerts when a caller tests an abnormal number of tokens.
- No distinction between unknown/expired/revoked/unauthorized-to-see responses in public output.

Rate limits must account for legitimate Resource Server load: each API request can trigger an introspection call if uncached. Size quotas high enough for normal traffic with a burst policy.

### 9.3. Caching Introspection Responses

RFC 7662 allows Protected Resources to cache responses to reduce load, but caching delays visibility into revoked tokens or policy changes.

- If the response has **exp**, do not cache past that expiration time.
- Cache TTL should be shorter than or equal to the acceptable revocation risk window.
- Cache keys must distinguish issuer, token fingerprint, and resource/caller context.
- Do not reuse full response claims meant for one Resource Server on another Resource Server.
- When revoking tokens or disabling callers, consider cache invalidation or shorter TTLs.
- If near real-time status is required, use a very short cache or introspect per request based on sized capacity.

Do not cache raw tokens as a metric/log label. Internal caches must protect sensitive data and have bounded memory.

### 9.4. Observability Without Leaking Tokens

You may log:
- Client ID of the authenticated introspection caller.
- Selected Resource Server/audience policy.
- Active/inactive outcome and normalized internal category.
- Latency, request ID, status code, and token type hint.
- Rate limit or policy denial counts.

Do not log:
- Raw access tokens or refresh tokens.
- Client secrets, Basic Authorization headers, private keys, or client assertions.
- Full introspection request/response bodies.
- Subject/PII if unnecessary and lacking a retention policy.

When support needs to look up a token, use a one-way fingerprint with properly managed salt/key and restricted audit access; never copy real tokens into tickets.

## 10. Testing Client Authentication and Introspection Authorization

### 10.1. Endpoint Test Matrix

| Request | Expected Result |
|---|---|
| Valid introspection caller, active token and permitted audience | 200, **active=true**, minimal claims. |
| Wrong client secret or non-existent client | 401 per client authentication. |
| Client authenticates but is not allowed to call the introspection endpoint | Rejected at endpoint authorization layer. |
| Authenticated caller but token does not exist | 200, **active=false**. |
| Expired or revoked token | 200, **active=false**. |
| Token exists but audience does not belong to caller | 200, **active=false**, no explanation. |
| Caller has valid audience but token lacks required scope | Token may be active; response shows actual scopes, Resource Server rejects API request for insufficient permissions. |
| Request body missing **token** | OAuth2 **invalid_request**. |
| Request uses GET/query string | Rejected, or endpoint only accepts POST per configuration. |
| Caller sends wrong token_type_hint | Must not skip determining actual token state. |
| Caller A introspects token of audience B | Inactive per policy, does not reveal token existence. |
| Caller B introspects token of audience B | Active and permitted claims. |
| Same token, two Resource Servers | Response is scoped per caller/resource context. |

### 10.2. Policy Test Matrix

- **inventory-api-introspector** only introspects tokens with audience **inventory-api**.
- **billing-api-introspector** cannot inspect tokens intended only for **inventory-api**.
- A disabled client / revoked credential cannot continue calling introspection.
- A client not in the allowlist is rejected or receives inactive per target-token policy, without leaking status.
- Tenant A cannot view token metadata of tenant B.
- Refresh token introspection is explicitly enabled or disabled by policy; never inferred from access-token permission.
- Returned scopes only include permissions the Resource Server is allowed to know.
- Sensitive custom claims do not appear in the response.

### 10.3. MockMvc Example Testing Unauthorized Token Introspection

This test illustrates the case where an authenticated caller is denied visibility into a token belonging to another audience by policy:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class IntrospectionAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedCallerCannotDiscoverForeignAudienceToken()
            throws Exception {

        mvc.perform(post("/oauth2/introspect")
                .with(httpBasic(
                        "inventory-api-introspector",
                        "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "TOKEN_FOR_BILLING_API")
                .param("token_type_hint", "access_token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.active").value(false))
            .andExpect(jsonPath("$.client_id").doesNotExist())
            .andExpect(jsonPath("$.scope").doesNotExist());
    }
}
~~~

The test assumes the fixture already has:
- A valid introspection client and test credential.
- An existing token whose audience is strictly for Billing API.
- The policy wrapper installed in the provider list.
- The default endpoint path **/oauth2/introspect**.

Do not use real tokens in tests or logs. Add a non-existent token test to confirm the public response cannot distinguish the two cases.

### 10.4. Testing Happy Paths and Failure Paths

Beyond inactive tests:

1. Send an active token with an allowed audience; confirm **active=true** and correct scopes.
2. Send an expired/revoked token; confirm **active=false**.
3. Send a wrong secret; confirm 401.
4. Send a request without a token; confirm request error.
5. Send a token of another audience; confirm the response only has active=false.
6. Send a token with PII/custom claims; confirm projection removes unnecessary claims.
7. Test through the reverse proxy; confirm TLS and that POST bodies are not logged.
8. Send multiple concurrent requests; confirm rate limits and storage are not overloaded.
9. Update the allowlist/disable a caller; confirm the policy takes effect within SLA.
10. Run across multiple Authorization Server instances; confirm policy and authorization state are consistent.

## 11. Common Mistakes and Diagnosis

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Introspection returns 401 | Wrong caller credential or auth method mismatches registration. | Check RegisteredClient, secret/certificate/JWT assertion, and TLS. |
| Valid client can still introspect another API's tokens | Only authentication checked; missing caller-to-token authorization. | Add audience/resource policy and return inactive when not allowed to know. |
| All tokens are inactive | Token not stored/looked up wrongly, different authorization service instance, or mishandled token type hint. | Check OAuth2AuthorizationService and token state. |
| Resource Server cannot reach endpoint | Wrong URI, TLS, client ID/secret, or firewall. | Check opaque token config and network. |
| Non-existent token returns different error than revoked token | Error handler or custom provider leaks state. | Standardize active=false responses. |
| Resource Server sees too many claims | Default response handler/provider returns all claims or customizer lacks projection. | Restrict claim profile per caller. |
| Client uses GET causing tokens to appear in logs | SDK or custom client uses wrong HTTP method. | Enforce POST form-urlencoded and redaction. |
| Token revoked yet API still accepts it | Introspection cache TTL too long. | Shorten TTL, invalidate cache, or introspect more frequently. |
| API A mistakenly uses API B's cached response | Cache key lacks caller/resource context. | Partition cache by issuer, token fingerprint, and resource identity. |
| Custom provider does not run | Default provider not replaced properly or wrong provider order. | Inspect provider list at startup and run endpoint integration tests. |
| Introspection client mistakenly uses token subject's client ID | Confusing introspection caller with issuing client. | Use a dedicated Resource Server credential. |
| Introspect scope mistaken for token lookup permission | Confusing token scope with endpoint authorization. | Build a dedicated policy for introspection callers and audiences. |

## 12. Hands-On Exercise

**Context:** An Authorization Server issues tokens for three APIs: **inventory-api**, **billing-api**, and **reporting-api**. The APIs use opaque token introspection. The security team discovers that one Resource Server's credentials can introspect tokens belonging to other APIs.

Requirements:

1. Register three separate introspection callers: **inventory-api-introspector**, **billing-api-introspector**, and **reporting-introspector**.
2. Configure client authentication with **client_secret_basic** in the test environment, then propose private_key_jwt or mTLS for production.
3. Determine each token's trusted audience/resource; do not infer it from client ID.
4. Create an **IntrospectionAccessPolicy** mapping callers to allowed audiences.
5. Wrap **OAuth2TokenIntrospectionAuthenticationProvider** with a custom provider, delegating token activity checks to the standard provider.
6. When a token exists but the caller is not allowed to know about it, return **active=false** without any other claims.
7. Keep active responses restricted to only the scope, subject, expiry, and audience the API actually needs.
8. Write MockMvc tests for valid callers, invalid caller credentials, non-existent tokens, expired/revoked tokens, and foreign-audience tokens.
9. Configure Spring Resource Server opaque token support with its dedicated credentials.
10. Test introspection caching, token revocation, rate limiting, and auditing; measure state update latency.
11. Verify logs/APM contain no raw tokens, secrets, or response bodies.
12. Run across multiple Authorization Server instances and confirm consistent allowlist/policy enforcement.

**Completion criteria:** each Resource Server can only introspect tokens within its granted scope; callers with wrong credentials get 401; non-existent, inactive, or out-of-scope tokens return active=false; claims are filtered; policies are tested and audited.

## 13. Pre-Production Checklist

- [ ] Introspection Endpoint is accessible only over HTTPS/TLS with certificate verification.
- [ ] Endpoint requires client authentication or an equivalent authorization mechanism.
- [ ] Introspection callers are registered Resource Servers/Protected Resources with clear owners.
- [ ] Introspection credentials are separated per Resource Server, with rotation and least privilege.
- [ ] Public client **none** is not used as the sole protection for this sensitive endpoint.
- [ ] Caller authentication is separated from caller-to-token authorization.
- [ ] Policy checks audience/resource, tenant, token type, and claim profile.
- [ ] Token scopes are not used to implicitly grant introspection permission.
- [ ] Callers not allowed to know a token receive **active=false** without reasons.
- [ ] Non-existent/expired/revoked tokens also return a minimal inactive response.
- [ ] Invalid client authentication returns an appropriate error, never masked as active=false.
- [ ] Active responses contain only the minimum claims needed by the Resource Server.
- [ ] Response claims do not leak PII or metadata of other resources.
- [ ] Token requests use POST form-urlencoded; tokens are never passed in URLs.
- [ ] Rate limits, request-size limits, timeouts, audits, and alerts are in place.
- [ ] Cache respects exp, revocation SLA, and partitions by caller/resource.
- [ ] Custom provider retains the standard delegate to check token activity.
- [ ] MockMvc/E2E tests cover credentials, audience, inactive tokens, and token enumeration.
- [ ] Logs/APM/tracing contain no raw tokens, secrets, assertions, or introspection bodies.
- [ ] Policies, allowlists, rollback, and incident response have owners/runbooks.

## Summary

The Token Introspection Endpoint must be protected in **two layers**. Spring Authorization Server authenticates the client calling the endpoint via the client authentication filter; the system must then decide whether that client is allowed to know the status and claims of the specific token. RFC 7662 requires protecting the endpoint against token scanning and recommends allowing only authorized Protected Resources to call introspection.

With Spring Authorization Server, **OAuth2TokenIntrospectionEndpointConfigurer** lets you customize converters, providers, and response handlers. You can wrap **OAuth2TokenIntrospectionAuthenticationProvider** to add policy checks based on the authenticated client and the token's audience/resource, then delegate token activity determination to the standard provider. When a caller is not permitted to know a token, the response must be a minimal **active=false**, avoiding disclosure of whether the token exists.

Introspection authorization does not replace scope/audience/tenant checks at the Resource Server. Production systems require dedicated credentials, TLS, least privilege, claim projection, rate limiting, bounded caching, token-free audits, and anti-token-enumeration tests.

## References

1. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): endpoint authorization, introspection request/response, active=false, privacy, caching, and TLS.
2. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth2TokenIntrospectionEndpointConfigurer and extension points.
3. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationProvider.html): standard provider, RegisteredClientRepository, and OAuth2AuthorizationService.
4. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospectionAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenIntrospectionAuthenticationToken.html): token, client principal, token type hint, and additional parameters.
5. [Spring Authorization Server 1.5.8 — OAuth2TokenIntrospection API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2TokenIntrospection.html): representation of the introspection response.
6. [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication filter and Authorization Server configuration.
7. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClientRepository, OAuth2AuthorizationService, and authorization data.
8. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): configuring introspection-uri and credentials on the Resource Server.
9. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication and HTTP authorization errors.
10. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer access token usage.
