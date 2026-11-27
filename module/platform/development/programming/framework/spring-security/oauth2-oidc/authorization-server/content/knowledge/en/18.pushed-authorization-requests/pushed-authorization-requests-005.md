# Using request_uri at the Authorization Endpoint

## 1. From a long authorization request to a short reference

In the OAuth 2.0 Authorization Code Flow, the client normally places parameters such as `client_id`, `redirect_uri`, `scope`, `state`, and the PKCE challenge into the URL the browser sends to the Authorization Endpoint. This approach is simple, but has three limitations:

- The URL can become long, exceeding browser, reverse proxy, or web server limits.
- Parameters can appear in browser history, access logs, analytics systems, or referrer headers.
- The user and browser carry a request that can be modified along the application path, even though HTTPS protects each connection.

**Pushed Authorization Requests (PAR)** per RFC 9126 solves this by having the client send the authorization request directly to the Authorization Server via an authenticated HTTP POST. The server stores the payload and returns a `request_uri` reference. Afterward, the client passes only that reference to the Authorization Endpoint through the user agent.

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth/OIDC Client
    participant AS as Authorization Server
    participant B as Browser
    participant U as User
    C->>AS: POST PAR: authorization parameters
    AS->>AS: Authenticate client + validate request
    AS-->>C: 201 + request_uri + expires_in
    C->>B: Open authorization_endpoint?client_id=...&request_uri=...
    B->>AS: GET Authorization Endpoint with request_uri
    AS->>AS: Look up stored request and check binding/expiry
    AS->>AS: Continue login, consent, and authorization
    AS-->>B: Redirect to redirect_uri with code + state
    B-->>C: Callback
    C->>AS: Exchange code at token endpoint + PKCE verifier
    AS-->>C: Access token / ID token if OIDC
```

**Lesson focus:** the `request_uri` returned by PAR is a reference to an authorization request stored on the server. When the browser calls the Authorization Endpoint, the server must properly recognize that reference, restore the exact request, and continue processing per OAuth/OIDC.

This lesson belongs to the **Pushed Authorization Requests** chapter of the module on designing, configuring, securing, testing, and operating an OAuth 2.0/OIDC Authorization Server with Spring Security and Spring Authorization Server. Learners should be able to:

1. Distinguish PAR's `request_uri` from `redirect_uri` and the `request_uri` of JWT-Secured Authorization Request (JAR).
2. Describe the lifecycle from PAR POST and `201 Created` response to the Authorization Endpoint.
3. Understand client binding, expiration, one-time usage, and browser reload behavior.
4. Configure the PAR endpoint and verify support across Spring versions.
5. Design a policy allowing authorization requests only via PAR when required by the product.
6. Test valid requests, invalid/expired URIs, swapped request URIs, replay, and multi-instance setups.

## 2. Distinguishing easily confused URIs

| Value | Role | Example | Who uses it? |
| --- | --- | --- | --- |
| `authorization_endpoint` | Endpoint receiving authorization requests via user agent | `https://auth.example.com/oauth2/authorize` | Browser/client |
| `pushed_authorization_request_endpoint` | Endpoint receiving PAR payloads directly over back channel | `https://auth.example.com/oauth2/par` | Client calling server-to-server |
| `request_uri` returned by PAR | Short, opaque reference to the server-stored request | `urn:ietf:params:oauth:request_uri:abc...` | Client passes to the Authorization Endpoint |
| `redirect_uri` | Registered client callback where the server returns the authorization result | `https://portal.example.com/login/oauth2/code/portal` | Authorization Server redirects browser |
| `request_uri` of JAR/OIDC Request Object | Reference to a Request Object hosted by the client at a URI per JAR/OIDC | Can be a registered HTTPS URI | Authorization Server may need to fetch the Request Object per profile |

**`request_uri` is not `redirect_uri`.** One points to the authorization request data pushed to the AS; the other specifies the callback address to which the AS is permitted to redirect the browser.

### 2.1. PAR `request_uri` and JAR `request_uri` share a name but have different semantics

JAR (RFC 9101) allows sending a signed, optionally encrypted Request Object directly via the `request` parameter or by reference via `request_uri`. PAR (RFC 9126) creates an Authorization Server's own `request_uri` after the client pushes the request to the PAR endpoint.

In PAR:
- The server generates the reference and stores the payload internally.
- The client receives the reference from the PAR endpoint response.
- The client uses that reference at the same Authorization Server.
- The server does not need to expose the payload at a URL another party can download.

In JAR:
- The client builds a Request Object according to a JAR profile.
- The Request Object can be passed directly or by reference per JAR mechanisms.
- Verifying signature, issuer, audience, expiry, and Request Object rules is a separate responsibility.

RFC 9126 specifies that a `request_uri` returned from PAR can be used at the Authorization Endpoint **regardless of** the OIDC metadata `request_uri_parameter_supported` or `require_request_uri_registration`. Never use those two OIDC metadata flags to infer that PAR request URIs are prohibited or require pre-registration.

## 3. `request_uri` lifecycle per RFC 9126

### 3.1. Client pushes the authorization request

The client sends an HTTP **POST** to the PAR endpoint. The body uses `application/x-www-form-urlencoded` with UTF-8. The PAR endpoint must use HTTPS. Common parameters include:

- `response_type=code`;
- `client_id`;
- `redirect_uri`;
- `scope`;
- `state`;
- `code_challenge` and `code_challenge_method=S256` when using PKCE;
- `nonce` if OIDC and the client needs to verify nonce;
- Extension parameters such as `claims`, `resource`, or Request Object per supported profile.

The PAR endpoint applies the same client authentication rules as the token endpoint. For confidential clients, use the exact registered method, such as `client_secret_basic`, `private_key_jwt`, or mTLS if supported. For public clients, follow the registered client authentication/identification mechanism; never embed a fake client secret into mobile apps or SPAs.

**A PAR request must not contain `request_uri`**: the client is creating a new request, not submitting an existing PAR reference for nesting.

### 3.2. Server validates and returns the reference

If processing succeeds, the PAR endpoint returns HTTP `201 Created` with a JSON body:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-cache, no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:Qx7d9mR8...",
  "expires_in": 90
}
```

Mandatory points to remember:

- `request_uri` is a unique reference to the submitted authorization request.
- Its value must include a component generated by a cryptographically strong pseudorandom algorithm, practically unguessable.
- `request_uri` **MUST be bound to the client** that sent the PAR request.
- `expires_in` is the lifetime in seconds, a positive integer; the RFC suggests a short window, typically 5–600 seconds, though the server decides per policy.
- The response includes `Cache-Control: no-cache, no-store` to prevent unintended caching of responses containing sensitive references.

The server may use the URN namespace `urn:ietf:params:oauth:request_uri:`, but the client must treat the value as **opaque** and use it verbatim. Do not strip the prefix, decode the suffix, reconstruct the URI, or infer internal endpoints from it.

### 3.3. Client uses `request_uri` at the Authorization Endpoint

The client directs the browser to the Authorization Endpoint. RFC example:

```http
GET /oauth2/authorize?client_id=portal-web
  &request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AQx7d9mR8...
Host: auth.example.com
```

The browser request only needs to carry `client_id` and `request_uri` in this example. Parameters such as `redirect_uri`, `scope`, `state`, and the PKCE challenge are already in the payload the client sent in the PAR request. The Authorization Server must retrieve the original payload, verify client binding, and continue processing it.

**Do not send a new set of parameters contradicting the pushed payload.** For example, the client must not change `redirect_uri` or `scope` by appending different values to the URL to alter the validated request content. The client should follow the minimal pattern and parameter assembly rules specified by the RFC/server profile.

### 3.4. Expired or reused `request_uri`

RFC 9126 distinguishes client and server responsibilities:

| Behavior | Requirement |
| --- | --- |
| Client uses a `request_uri` multiple times | Client **MUST** use each value only once |
| Authorization Server receives the same `request_uri` again | Server **SHOULD** treat it as single-use; server **MAY** allow duplicates caused by user agent reload/refresh |
| `request_uri` is expired | Server **MUST** reject it as an invalid reference |
| `request_uri` belonging to client A is used by client B | Server must reject due to client binding mismatch |
| `request_uri` not issued by the server's PAR endpoint | Server must not treat it as a valid pushed request |

The exception for browser reloads does not mean a client is allowed to intentionally resubmit the same URI to start a new authorization transaction. The client must still obey the single-use requirement. If the server permits duplicates to recover from a reload, that behavior must be controlled and never become unbounded replay.

## 4. Complete example from client to callback

Assume:

```text
Authorization Server:
  issuer = https://auth.example.com
  PAR endpoint = https://auth.example.com/oauth2/par
  Authorization endpoint = https://auth.example.com/oauth2/authorize

Client:
  client_id = portal-web
  redirect_uri = https://portal.example.com/login/oauth2/code/portal

Request:
  response_type = code
  scope = openid profile orders.read
  state = STATE_FOR_THIS_TRANSACTION
  code_challenge = S256_CHALLENGE
```

### 4.1. Step 1 — discover endpoint via metadata

The client fetches Authorization Server metadata via OAuth Authorization Server Metadata (RFC 8414) or OIDC Discovery depending on issuer/deployment. PAR metadata includes the field:

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "pushed_authorization_request_endpoint": "https://auth.example.com/oauth2/par"
}
```

This is abbreviated JSON. Real responses may also include token endpoint, JWK Set URI, client authentication methods, and other metadata.

The presence of `pushed_authorization_request_endpoint` indicates the server can accept PAR. The `require_pushed_authorization_requests` field is an additional signal for mandatory PAR policy; if absent, RFC 9126 defines the default as `false`.

### 4.2. Step 2 — POST payload to the PAR endpoint

Example request with Basic client authentication:

```http
POST /oauth2/par HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_PORTAL_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

response_type=code
&client_id=portal-web
&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal
&scope=openid%20profile%20orders.read
&state=STATE_FOR_THIS_TRANSACTION
&code_challenge=S256_CHALLENGE
&code_challenge_method=S256
&nonce=NONCE_FOR_THIS_OIDC_TRANSACTION
```

`BASE64_PORTAL_CLIENT_CREDENTIALS`, `STATE_FOR_THIS_TRANSACTION`, `S256_CHALLENGE`, and `NONCE_FOR_THIS_OIDC_TRANSACTION` are placeholders. The real body must be properly URL-encoded; never put secrets in query strings. With `private_key_jwt`, the client sends `client_assertion_type` and `client_assertion` per client authentication profile.

### 4.3. Step 3 — receive `request_uri` and `expires_in`

```json
{
  "request_uri": "urn:ietf:params:oauth:request_uri:Qx7d9mR8f4...",
  "expires_in": 90
}
```

The client stores the reference within the current transaction long enough to redirect the browser. Never store it in a global variable shared across all tabs/users. If multiple login transactions run concurrently, each transaction must retain its own request URI, state, and context.

### 4.4. Step 4 — redirect the browser

The client builds the URL from endpoint metadata:

```text
https://auth.example.com/oauth2/authorize
    ?client_id=portal-web
    &request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AQx7d9mR8f4...
```

There is no need to resend the full scope, redirect URI, PKCE challenge, or nonce in the URL. This is a key benefit of PAR: the authorization payload travels directly from client to server over HTTPS, while the browser carries only a short reference.

### 4.5. Step 5 — Authorization Server processes the pushed request

The Authorization Server must:

1. Receive `client_id` and `request_uri`.
2. Look up the reference in the PAR request store.
3. Confirm the reference is unexpired and belongs to the exact client.
4. Restore the stored authorization request.
5. Validate the request against Authorization Endpoint rules like a normal authorization request.
6. Perform user authentication, consent, scope policy checks, and subsequent OIDC/OAuth steps.
7. Return the result via the verified `redirect_uri`, typically an authorization code with `state`.

The server **MUST** validate an authorization request originating from PAR like any other request. The RFC allows skipping certain duplicate checks when the server proves data/policy has not changed; that is a conditional optimization, not a default "once pushed, trust everything".

### 4.6. Step 6 — callback and token exchange proceed as usual

After receiving `code` and `state` at the callback, the client must still verify `state`/transaction and then exchange the code at the token endpoint using the matching transaction's `code_verifier`. **PAR does not replace PKCE, state, nonce, client authentication, redirect URI validation, or consent.**

## 5. Protecting client assertions when authenticating PAR

The PAR endpoint uses the same client authentication rules that apply to the token endpoint. Many confidential clients use `private_key_jwt` or `client_secret_jwt` to authenticate directly with the PAR endpoint.

**New specification update to note:** RFC 10070, published in November 2026, updated RFC 9126 regarding the audience of JWT client authentication assertions. For JWT client assertions used at the PAR endpoint:

- `aud` **MUST** be solely the Authorization Server's issuer identifier URL per RFC 8414.
- The Authorization Server **MUST** reject assertions that do not contain its exact issuer identifier as the sole audience.
- The client assertion JWT **SHOULD** have an explicit type of `client-authentication+jwt` or a more specific type defined by a profile.
- The server is **NOT RECOMMENDED** to reject merely for lacking an explicit `typ`, to avoid breaking compatibility with clients that comply with the new audience rule but have not yet added the type.

This changes the older RFC 9126 audience examples, which previously allowed multiple endpoint representations. When configuring `private_key_jwt` for PAR, use the exact AS issuer identifier as the single audience; do not default to using only the `/oauth2/par` or `/oauth2/token` URL as the audience.

```json
{
  "iss": "portal-web",
  "sub": "portal-web",
  "aud": "https://auth.example.com",
  "exp": 1794859200,
  "jti": "UNIQUE_ASSERTION_ID"
}
```

The payload above only illustrates the key claims; a real JWT must be signed with a registered key, have a short lifetime, use a `jti` matching replay protection policy, and conform to header/claim profile rules. The `aud` value is the AS's issuer identifier, not the request URI returned by PAR.

## 6. `request_uri` is an opaque reference and must be protected

### 6.1. Do not fetch `request_uri` as an external URL

A common implementation mistake is treating `request_uri` as a URL the server should fetch via HTTP GET. With PAR, the server **already owns the request data** and only needs to look it up in its internal store. Never fetch arbitrary URIs sent by a client/browser.

This avoids risks such as:
- SSRF to internal addresses or unintended metadata endpoints.
- Sending credentials/headers to untrusted hosts.
- Redirect chains causing the server to access resources outside an allowlist.
- Confusing a PAR URN with a JAR Request Object URI.

If the server supports both PAR and JAR, clearly classify the reference type, apply the corresponding trust mechanism, and never fall back to "not found in PAR, so try fetching this URL".

### 6.2. Client binding

Every `request_uri` must be bound to the client that pushed the request. When the Authorization Endpoint receives `client_id` with `request_uri`, the server must verify:

```text
request.client_id == par_record.registered_client_id / stored client_id
```

Do not let client B use client A's request URI, even if both clients share the same redirect URI or scopes. Do not check only the `client_id` query string: compare against the client binding in the server-created and stored PAR record.

### 6.3. Entropy, expiration, and storage

The server needs to:
- Generate practically unguessable references via CSPRNG.
- Enforce a short TTL and return the matching `expires_in`.
- Store request parameters in a mechanism accessible to all instances.
- Mark consumed state or handle duplicates per policy.
- Delete expired data after a reasonable retention period.
- Prevent request URIs from becoming sequential keys, predictable UUIDs, or enumerable internal IDs.

Records can be stored in a shape such as:

```text
request_uri_fingerprint
registered_client_id
authorization_request_payload
created_at
expires_at
status: ACTIVE | CONSUMED
consumed_at
```

This is an illustrative data model, not a default schema published by SAS. If using a fingerprint instead of the raw request URI, design consistent lookup; the payload must be protected as sensitive authorization data.

### 6.4. Preventing `request_uri` swapping

A request URI captured from transaction A could be injected into transaction B. For example, request A requires a high authentication level while request B requires a lower one; an attacker tries to make B's browser use A's request URI or vice versa.

RFC 9126 recommends clients use transaction-binding mechanisms such as:
- per-transaction random `state`;
- PKCE with a dedicated verifier/challenge;
- OIDC `nonce` when required.

Per-client request URI binding does not automatically bind every context of the browser transaction. Clients must still verify state/PKCE/nonce for the exact transaction.

## 7. Mandatory PAR policy and metadata

RFC 9126 defines two metadata fields with the same name but different scopes:

| Metadata | Where published | Meaning |
| --- | --- | --- |
| `pushed_authorization_request_endpoint` | Authorization Server Metadata | URL of the PAR endpoint |
| `require_pushed_authorization_requests` | Authorization Server Metadata | AS accepts authorization requests only via PAR when `true` |
| `require_pushed_authorization_requests` | Client Metadata | A specific client may initiate authorization only via PAR when `true` |

If the `require_pushed_authorization_requests` metadata field is absent, the RFC default is `false`. The AS may apply policy globally or per client. When PAR is mandatory, the Authorization Endpoint must reject authorization requests lacking a PAR-issued `request_uri`, typically with `invalid_request`.

**Do not confuse the three flags:**
- `pushed_authorization_request_endpoint` says the server **has a PAR endpoint**.
- `require_pushed_authorization_requests` says whether PAR **is mandatory**.
- `request_uri_parameter_supported` and `require_request_uri_registration` belong to OIDC/JAR metadata and do not replace PAR metadata.

### 7.1. Capabilities and limits to check in Spring Authorization Server

At the time of writing:
- Spring Authorization Server **1.5** is the branch adding PAR support; the 1.5 GA release announced RFC 9126 support.
- SAS **1.5.8** includes `OAuth2PushedAuthorizationRequestEndpointConfigurer`, `OAuth2PushedAuthorizationRequestEndpointFilter`, `OAuth2PushedAuthorizationRequestAuthenticationProvider`, and `OAuth2PushedAuthorizationRequestAuthenticationToken`.
- `AuthorizationServerSettings.getPushedAuthorizationRequestEndpoint()` has existed since SAS **1.5**, defaulting to `/oauth2/par`.
- Spring Security **7.0+** includes the corresponding Authorization Server PAR classes; Javadoc marks the provider as `@since 7.0`.
- SAS **1.4.x and earlier** have no built-in PAR endpoint per the 1.5 release notes; you must upgrade or implement the grant/endpoint per RFC if unable to upgrade yet.

SAS 1.5.8 Protocol Endpoints documentation describes the endpoint, converter, provider, response handler, and custom validator. It also presents default validation for `redirect_uri` and `scope`.

**Point requiring separate verification:** the presence of the endpoint and metadata URL does not by itself prove the server has enabled **PAR-only** mode. The 1.5.8 reference describes PAR endpoint configuration but does not document a separate configuration flag equivalent to `require_pushed_authorization_requests` in the documented endpoint section. If your product mandates PAR, inspect the actual discovery metadata, implement client/server enforcement, and write tests proving regular authorization requests are rejected.

## 8. Configuring PAR in Spring Authorization Server 1.5.x

### 8.1. AuthorizationServerSettings

SAS 1.5.x has default endpoints:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .authorizationEndpoint("/oauth2/authorize")
            .pushedAuthorizationRequestEndpoint("/oauth2/par")
            .tokenEndpoint("/oauth2/token")
            .build();
}
```

`AuthorizationServerSettings` is a required Authorization Server configuration component. If using imported default configuration, SAS may register a settings bean automatically; declare it explicitly when fixing the issuer and endpoint paths. If changing the PAR path, metadata must reflect the new URL so clients call the right endpoint.

### 8.2. Enabling the PAR endpoint and extension points

Example using SAS 1.5.x APIs:

```java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .pushedAuthorizationRequestEndpoint(par -> par
                .authenticationProviders(configureParValidation())
            )
        );

    return http.build();
}
```

This configuration snippet focuses on PAR, not the entire Authorization Server. The application still requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, JWK signing key, issuer, client authentication, and the user login security chain.

### 8.3. Preserving the default validator when adding policy

SAS 1.5.8 lets you customize `OAuth2PushedAuthorizationRequestAuthenticationProvider` via `setAuthenticationValidator`. The default validator checks redirect URI and scope. When adding custom policy, chain onto it rather than accidentally dropping those checks.

Example:

```java
private Consumer<List<AuthenticationProvider>> configureParValidation() {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2PushedAuthorizationRequestAuthenticationProvider parProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    OAuth2AuthorizationCodeRequestAuthenticationValidator
                            .DEFAULT_REDIRECT_URI_VALIDATOR
                    .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator
                            .DEFAULT_SCOPE_VALIDATOR)
                    .andThen(context -> {
                        RegisteredClient client = context.getRegisteredClient();

                        // Additional business policy, for example:
                        // - is client allowed to use PAR for this flow?
                        // - do sensitive scopes need extra conditions?
                        // - does redirect URI meet tenant policy?
                        validateParBusinessPolicy(client, context.getAuthentication());
                    });

            parProvider.setAuthenticationValidator(validator);
        }
    });
}
```

`validateParBusinessPolicy` is an application-implemented business function. This sample code does not replace endpoint client authentication, request URI binding, expiry checks, or Authorization Endpoint validation. Never relax `redirect_uri` just because the request went through PAR; the RFC permits an AS to have a specific policy for dynamic redirect URIs of authenticated confidential clients, but that must be explicitly designed, bounded, and tested.

### 8.4. PAR-only policy must be enforced at the Authorization Endpoint

If a client's authorization requests are all required to go through PAR, verifying that the PAR endpoint works is not enough. The Authorization Endpoint must verify that the request carries a valid `request_uri` issued by the server itself, bound to the client, and unexpired.

Enforcement design must ensure:
1. Regular requests without `request_uri` are rejected with `invalid_request` when the client/server mandates PAR.
2. `request_uri` cannot be guessed, self-generated, or taken from an external JAR URI in place of PAR.
3. Client binding is checked in the request store.
4. TTL and consumption status are verified.
5. No alternative processing path (such as a custom converter or secondary endpoint) bypasses the policy.
6. `require_pushed_authorization_requests` metadata is advertised consistently with the enforced policy.

Because APIs/configuration for PAR-only policies can differ across versions, do not copy an invented property and assume the framework enforces it automatically. When needed, build the policy via the appropriate Authorization Endpoint extension point or a tested integrated filter/policy layer; keep the default provider and create no backdoor for issuing authorization codes.

## 9. Checks at the Authorization Endpoint remain essential

PAR lets the AS validate early, yet the authorization request must still be processed per OAuth/OIDC. Upon receiving `request_uri`, the server must guarantee:

- The reference exists in this issuer's PAR store.
- The client in the authorization request matches the pushing client.
- The request is not expired.
- The request has not been consumed, or any duplicate falls under a policy-permitted reload case.
- The redirect URI is valid per client registration/policy.
- The response type and grant are supported.
- Scopes are registered to the client and permitted by policy.
- PKCE challenge/method match policy.
- `state`, `nonce`, and extension parameters remain those of the stored request.
- Consent and user authentication are performed per policy.
- Client policy has not changed in a way that invalidates the request.

Do not skip authorization checks simply because the PAR endpoint accepted the payload. The RFC allows skipping certain duplicate checks when the server proves data/policy has not changed; that is a conditional optimization, not a default "once pushed, trust everything".

## 10. Errors and response behavior

| Scenario | Appropriate behavior/error |
| --- | --- |
| PAR body missing required parameter or malformed | `invalid_request` |
| Client authentication wrong or missing required credential | `invalid_client` |
| Client not permitted to use the response type/grant | `unauthorized_client` or `unsupported_response_type` depending on cause |
| Disallowed scope | `invalid_scope` |
| Invalid redirect URI | `invalid_request`; do not redirect to an unverified URI |
| Non-POST HTTP method at PAR endpoint | HTTP `405 Method Not Allowed` |
| Payload exceeds server limit | HTTP `413 Payload Too Large` |
| Client sends too many PAR requests | May return HTTP `429 Too Many Requests` |
| `request_uri` expired or non-existent | Reject at Authorization Endpoint, typically `invalid_request` |
| `request_uri` belongs to another client | Reject without exposing the other client's request |
| Authorization request without PAR in PAR-only mode | `invalid_request` |
| Request URI reused | Reject per one-time policy; reload exceptions must be controlled |

Error messages returned to clients must not reveal payload contents, users, sensitive scopes, or detailed request URI state. Internal logs may include correlation IDs and failure categories, but must not record raw `request_uri`, `state`, client assertions, or sensitive data.

## 11. Security and operations

### 11.1. Request URI guessing and request URI replay

An attacker may try to guess a request URI or replay a captured value. The server needs high entropy, short TTLs, client binding, and a one-time policy. Never use sequence numbers, timestamps, low-entropy UUIDs, or sequential database IDs as the entire public value.

### 11.2. Request URI swapping

A request URI captured from transaction A could be injected into transaction B. Use per-transaction random `state`, a distinct PKCE challenge, and OIDC `nonce` when required. The client must verify `state` at the callback; the AS must verify client binding and prevent request URIs from being swapped across clients.

### 11.3. Open redirects and dynamic redirect URIs

PAR lets the AS authenticate the client before user interaction. RFC 9126 permits the AS to relax exact-match redirect URI rules for clients with established credentials, such as allowing per-transaction URIs. This is an **AS option**, not a requirement to open dynamic redirects.

If permitted:
- Apply only to strongly authenticated confidential clients.
- Restrict scheme/host/path or query transformation rules by policy.
- Disallow URIs on arbitrary domains.
- Check for open redirects on the client side.
- Audit whenever a dynamic redirect URI is accepted.

In typical configurations, keeping registered redirect URIs and exact matching is the easiest choice to control.

### 11.4. Do not log PAR payloads verbatim

Payloads can contain scopes, state, nonce, claims, login hints, or sensitive transaction data. PAR reduces exposure in browser URLs, yet does not stop an AS, reverse proxy, or APM from recording the request body. You should:
- Mask or omit PAR bodies from access logs.
- Never log raw `request_uri`, `state`, `nonce`, client assertions, or tokens.
- Restrict read access to the PAR store.
- Encrypt stored data when required by data policy.
- Set TTLs and cleanup so payloads are not retained longer than necessary.
- Control payload size and rate-limit the endpoint.

### 11.5. Multiple instances and cleanup

When running multiple AS instances, PAR records must be stored in a shared store or a consistent sharing mechanism. If node A creates a request URI and the browser hits node B which cannot find it, flows will fail intermittently.

Storage design must provide:
- A shared issuer/client namespace.
- Lookup by request URI/fingerprint.
- Client binding and expiry checks on every instance.
- Concurrency-controlled updates to consumed state.
- TTL/cleanup and metrics for expired records.
- Recovery across restarts and failovers.

### 11.6. Client assertion audience after RFC 10070

For `private_key_jwt` or `client_secret_jwt` used at the PAR endpoint, update both clients and AS per RFC 10070: `aud` must be solely the AS's issuer identifier. Older configurations using the token endpoint or PAR endpoint URL as the audience must be reviewed and migrated. In multi-issuer/multi-tenant deployments, each assertion must target the exact issuer corresponding to the client transaction.

## 12. Testing PAR and `request_uri`

### 12.1. Functional test matrix

| Test | Action | Expectation |
| --- | --- | --- |
| Valid PAR | POST valid body and client authentication | `201 Created` with `request_uri` and `expires_in` |
| Discovery | Read Authorization Server metadata | Contains `pushed_authorization_request_endpoint` with exact URL |
| Authorization via PAR | Call Authorization Endpoint with `client_id` + `request_uri` | Restores exact request and continues flow |
| Client A's URI used with client B | Change `client_id` at Authorization Endpoint | Rejected due to binding |
| Expired URI | Wait past `expires_in` | Rejected |
| Non-existent URI | Send random string | Rejected |
| Guessable URI | Try sequential IDs/fake values | No valid request found |
| Repeated PAR requests | Resend new PAR body | Each request receives its own reference or clear policy handling |
| Request URI replay | Reuse the same `request_uri` after consumption | Rejected per policy |
| Browser reload | Reload authorization URL within policy limits | Controlled duplicate handling; no unexpected code/token |
| Unauthenticated client | Omit client credentials when required by method | `invalid_client` |
| Wrong client auth | Invalid secret/assertion | Rejected |
| Invalid redirect URI | Push redirect URI outside policy | Rejected at PAR or at Authorization Endpoint if validation is deferred |
| Unauthorized scope | Push unregistered scope | Rejected |
| `request_uri` in PAR body | Send `request_uri` when creating new PAR | Rejected per RFC |
| Missing `request_uri` in PAR-only mode | Call Authorization Endpoint with traditional parameters | `invalid_request` |
| JAR Request URI | Send HTTPS JAR URI instead of PAR handle when client requires PAR | Rejected if policy allows PAR only |
| State/PKCE/nonce | Alter value at callback or different transaction | Client rejects; wrong transaction cannot complete login |

### 12.2. Security and operational tests

| Test | Goal |
| --- | --- |
| Two clients share a `request_uri` | Cannot access another client's request |
| Two browser sessions on same client | No state/nonce/PKCE swap between transactions |
| Concurrent `request_uri` replay | Only policy-permitted behavior occurs; never emits two unintended authorization codes |
| Two instances handle the same URI | Binding, expiry, and consumed state stay consistent |
| Restart between PAR POST and browser redirect | Record remains valid within TTL if storage is persistent |
| Database/cache outage | Never accept a request URI when binding/expiry cannot be verified |
| Large payload | Bounded and returns appropriate error without exhausting memory |
| PAR request burst | Rate limiting triggers with telemetry |
| Log inspection | No leakage of state, nonce, client assertions, sensitive payloads, or `request_uri` |
| RFC 10070 client assertion | Audience is solely the issuer identifier; assertions targeting another issuer are rejected |
| PAR-only metadata | Metadata accurately reflects policy and Authorization Endpoint enforces it |
| Client policy changes after PAR | Request re-evaluated when needed; stale permissions violating new policy are rejected |

### 12.3. Callback tests remain mandatory

PAR does not replace Authorization Code Flow tests:
- State matches transaction.
- PKCE verifier matches the challenge stored in the request.
- Redirect URI is valid.
- Authorization code is single-use.
- OIDC nonce and ID token are verified.
- Token endpoint client authentication matches registration.

## 13. Common integration mistakes

**Mistake 1 — resending all request parameters at the Authorization Endpoint.** The client already pushed the payload yet still appends `scope`, `redirect_uri`, or a new `state` to the URL. This creates ambiguity and can make client/server process two conflicting parameter sources. Use `request_uri` as the reference and follow the RFC request structure.

**Mistake 2 — treating `request_uri` as `redirect_uri`.** One points to the stored payload; the other is the client callback. The two values are not interchangeable.

**Mistake 3 — client fabricating `request_uri`.** The Request URI must be issued by the server after authenticating and storing the PAR request. Clients must never guess or construct values themselves.

**Mistake 4 — fetching `request_uri` via HTTP GET.** A PAR URI is an internal lookup handle. Never fetch it arbitrarily, to avoid SSRF and confusion with JAR.

**Mistake 5 — omitting client binding checks.** Another client could use the original client's reference. Always verify against the server-stored record.

**Mistake 6 — assuming PAR is automatically mandatory for all clients.** Having a PAR endpoint does not mean metadata/policy has set `require_pushed_authorization_requests=true`. Verify both discovery and enforcement.

**Mistake 7 — dropping PKCE because PAR authenticated the client.** PAR protects the authorization request on the back channel; PKCE still binds the authorization code to the client transaction.

**Mistake 8 — validating only at the PAR endpoint.** Client policy or redirect URIs may change before the browser reaches the Authorization Endpoint. The server must ensure required checks remain in effect.

**Mistake 9 — allowing unlimited `request_uri` reuse to support browser refreshes.** The RFC only permits the AS to support duplicates due to reloads; clients must still use it once. Cap count, duration, and state.

**Mistake 10 — using JWT client assertions with legacy audiences.** Configuring `aud` as the PAR endpoint URL or token endpoint URL is no longer compliant after the RFC 10070 update; use the AS's sole issuer identifier.

## 14. Scenario exercises

An Authorization Server has issuer `https://auth.example.com`, PAR endpoint `/oauth2/par`, and Authorization Endpoint `/oauth2/authorize`. Client `portal-web` sends an authorization request containing `scope=openid orders.read`, `state`, PKCE challenge, and OIDC nonce. The server returns `request_uri` with `expires_in=60`.

Analyze these scenarios:

1. The client sends the browser to the Authorization Endpoint with the right `client_id` and `request_uri`. What must the server check before restoring the payload?
2. An attacker changes `client_id` to another client while keeping the same `request_uri`. How does the server respond?
3. The browser is reopened after 30 seconds and sends the same request URI again. What is the difference between the client's obligation and the AS's option?
4. The browser reopens after 70 seconds. Why must the request be rejected?
5. The client sends a different `redirect_uri` in the Authorization Endpoint query string. Why must the new value not replace the pushed payload?
6. Metadata contains `pushed_authorization_request_endpoint` without `require_pushed_authorization_requests`. Can the client infer the server mandates PAR?
7. If the client uses `private_key_jwt` at the PAR endpoint, what value must `aud` carry per RFC 10070?
8. If SAS has a PAR endpoint but no proven PAR-only enforcement configuration, what tests/policies must be added?

**Hints:** request URI must exist, be unexpired, and be bound to the right client; clients use it once; AS may allow controlled reload duplicates; expired ones must be rejected. The metadata endpoint only advertises PAR capability. PAR-only mode requires enforced metadata/policy. JWT client assertions must use the AS's sole issuer identifier as audience.

## 15. Production deployment checklist

1. **Discovery:** client obtains the exact `pushed_authorization_request_endpoint` from metadata and verifies the issuer.
2. **Back channel:** PAR uses HTTPS POST, UTF-8 form-urlencoded, and client authentication matching the registered method.
3. **Validation:** server checks client, response type, redirect URI, scope, PKCE, OIDC nonce, and related extensions.
4. **Response:** returns `201`, high-entropy `request_uri`, client binding, `expires_in`, and appropriate cache-control headers.
5. **Authorization Endpoint:** accepts only valid request URIs from the PAR store, matches client, and restores the original payload.
6. **Lifecycle:** short TTL, client single-use, AS controlled duplicate reload handling, expired URIs always rejected.
7. **PAR-only:** metadata and enforcement consistent server-wide/per-client; do not confuse endpoint support with mandatory policy.
8. **Version:** confirm PAR is available in SAS 1.5+ or Spring Security 7.0+; if older, upgrade or implement tested custom support.
9. **JWT client assertion:** apply the sole issuer identifier as audience per RFC 10070.
10. **Storage:** shared across instances, protects payloads, prevents replay, includes cleanup and rate limiting.
11. **Observability:** mask payloads/`request_uri`/`state`/`nonce`/credentials; track metrics for errors, expirations, replays, rate limits, and storage.
12. **End-to-end:** test PAR endpoint, Authorization Endpoint, browser reload, callback, PKCE, consent, and token endpoint.

## 16. Standards and Spring references to consult

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): PAR endpoint, `request_uri` response, Authorization Request, client binding, expiry, replay, and metadata.
- [RFC 10070 — Updates to OAuth 2.0 JWT Client Authentication and Assertion-Based Authorization Grants](https://www.rfc-editor.org/rfc/rfc10070.html): updates RFC 9126 regarding the sole audience of JWT client authentication assertions.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): metadata endpoint and issuer identifier.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authorization requests, client authentication, and responses.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html): binding authorization codes via `code_verifier`/`code_challenge`.
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101.html): Request Objects and differences from PAR request URIs.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): PAR endpoint configurer, converter/provider, and custom validator.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): default `/oauth2/par` endpoint and support since 1.5.
- [Spring Security 7.x — OAuth 2.0 Authorization Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/index.html): Authorization Server endpoints in the newer Spring Security generation.
- [Spring Authorization Server 1.5 goes GA](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): announcement of PAR support in the 1.5 branch.

**Key takeaway:** A client does not send the entire authorization request through the browser after pushing; the client sends **`client_id` and `request_uri`** so the Authorization Server restores the stored payload. The Request URI must be unpredictable, bound to the exact client, time-limited, and governed by a one-time-use policy. PAR reduces parameter exposure and tampering in the browser, yet still requires PKCE, `state`, `nonce`, redirect URI validation, consent, and standard authorization checks. In Spring Authorization Server, built-in support starts at **1.5**; to mandate PAR, verify both metadata and actual enforcement, and update JWT client assertion audiences per RFC 10070.
