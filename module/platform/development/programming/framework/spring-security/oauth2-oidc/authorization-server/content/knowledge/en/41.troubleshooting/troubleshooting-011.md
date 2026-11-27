# Device Flow, PAR, Token Exchange, and Token Binding Errors

Spring Authorization Server can handle multiple OAuth 2.0 flows and token-protection mechanisms, each with its own endpoints, parameters, state, and validation conditions. When Device Flow hangs in a pending state, PAR returns invalid_request_uri, Token Exchange rejects subject_token, or a resource server reports invalid token binding, you must locate the failure at the exact protocol boundary before changing configuration.

This lesson covers diagnosing by symptom, OAuth error code, authorization data, and Spring Authorization Server configuration. Direct out-of-the-box support for each extension depends on library version and how your application integrates it. Confirm the running version, actual endpoints, and configured converters/providers before applying a fix.

## 1. Gathering Evidence Before Fixing

Start by identifying where the request fails. The flows below can span multiple endpoints; a failure at an early step is not necessarily a token endpoint error.

| Flow | Typical Starting Point | Completion or Next Check Point |
|---|---|---|
| Device Authorization Grant | Device authorization endpoint | Verification URI, then token endpoint |
| Pushed Authorization Requests (PAR) | PAR endpoint | Authorization endpoint receiving request_uri |
| Token Exchange | Token endpoint with exchange grant type | New token, introspection, or resource server |
| DPoP token binding | Token endpoint with DPoP proof | Resource request with DPoP proof and access token |
| mTLS certificate-bound token | Token endpoint over TLS client certificate | Resource request over connection with matching certificate |

Gather the following details for a failing request:

- UTC timestamp, correlation ID, instance ID, and called endpoint.
- HTTP status, OAuth error, and error_description if present.
- Client ID, grant type, token type, and requested audience/resource.
- Deployed Spring Authorization Server version, Spring Security version, and endpoint configuration.
- Related authorization state: pending, approved, denied, expired, consumed, or invalidated.
- Verification results for signature, issuer, audience, lifetime, and key ID when the token is a JWT.
- Connectivity state of database, shared cache, KMS/HSM, and TLS proxy at the time of failure.

Never log raw device_code, user_code, authorization code, request_uri, subject_token, access token, refresh token, DPoP proof, private keys, or client secrets. If you need to correlate two requests, use internal reference IDs or a separately managed HMAC fingerprint. Do not put tokens in tickets, screenshots, or shell commands saved in history.

A brief diagnostic workflow:

1. Identify the actual endpoint and grant type.
2. Read the OAuth error code before guessing from the HTTP status.
3. Check client registration and the client authentication method.
4. Check authorization data, expiration, and one-time-use state.
5. Check issuer, keys, clocks, proxies, and caches when requests cross multiple instances.
6. Reproduce with a test client and fresh data, then re-verify on another instance.

## 2. Confirming Features and Configuration of the Running Version

Not all versions of Spring Authorization Server share the same set of grant types, endpoints, or extensions. A project may also implement Device Flow, PAR, Token Exchange, or token binding via separate modules. Before debugging, determine:

- Actual packaged dependencies and Spring Authorization Server version.
- Grant types declared in RegisteredClient.
- Enabled endpoints and paths after custom configuration is applied.
- Which AuthenticationConverter and AuthenticationProvider handle the request.
- Which OAuth2AuthorizationService and OAuth2AuthorizationConsentService persist state.
- Which token generator, JWK source, or KMS/HSM integration signs tokens.
- Whether the resource server validates the corresponding binding mechanism or only standard bearer JWTs.

If a request sends valid parameters without a matching converter/provider, the server may return unsupported_grant_type, invalid_request, or a validation error depending on where execution stops. Inspect startup logs and actual configuration to confirm extensions are registered. Do not assume support merely because a dependency appears in the build file.

## 3. Diagnosing Device Authorization Grant

Device Flow suits devices with limited keyboard or browser capabilities. The device initiates an authorization request, receives a device_code and user_code, instructs the user to open verification_uri on another device, and polls the token endpoint until the user completes authorization or the request expires.

General flow:

~~~mermaid
sequenceDiagram
    participant D as Device / Client
    participant AS as Authorization Server
    participant U as User Browser
    D->>AS: POST device authorization
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D->>U: Display code and URL
    U->>AS: Open verification URI, enter user_code
    AS-->>U: Prompt for login and confirmation
    U->>AS: Approve or deny
    loop At interval
        D->>AS: POST token with device_code
        AS-->>D: authorization_pending or final token/error
    end
~~~

### 3.1 Not Receiving a Device Code

Check in order:

- Is the client registered with the Device Authorization Grant in the manner required by your application's version and extensions?
- Is the device authorization endpoint enabled and does the URL called by the client match discovery/configuration?
- Does client authentication match the client type? If confidential, verify the registered client ID, secret, or authentication method.
- Does the request send required parameters, content type, and valid scopes?
- Is the database/cache storing device authorizations available?
- Can the server generate device_code, user_code, verification_uri, and expiration?

If you receive unauthorized_client, check the grant types allowed for the client. If you receive invalid_client, check client authentication. If you receive invalid_scope, compare requested scopes with registered scopes and authorization policy. If the server returns 404, verify the endpoint is actually configured rather than the request hitting the wrong service/proxy.

### 3.2 User Enters User Code, Yet Device Remains Pending

authorization_pending is a valid waiting state: the device is not yet allowed to receive a token because the user has not completed approval or the state change is not yet visible. Check:

- Has the user logged into the right account and completed the approve action?
- Does the entered user_code match a pending, unexpired, unused request?
- Did the verification UI update the right authorization record?
- Did the instance handling the approval write to the shared store read by the token endpoint?
- Is replica lag or a local cache causing the polling node to see stale state?
- Is the client accidentally polling with a device_code from another request session?

If the user approved yet status remains pending, trace the same internal authorization ID from code creation through approval and polling. Check transaction commits and confirm nodes read from the same data source. Do not fix this by lowering the polling interval; that only increases load.

### 3.3 Polling Too Fast or Returning slow_down

The client must honor the interval returned by the server. If the response omits interval, the client defaults to 5 seconds per the Device Authorization Grant specification. Upon receiving slow_down, the client must add 5 seconds to its interval for subsequent polls instead of continuing at the previous rate.

Common mistakes:

- Multiple threads or processes polling the same device code concurrently.
- Automatic HTTP retries inadvertently increasing request frequency.
- Client ignoring the interval returned by the device authorization endpoint.
- Client failing to back off after slow_down.
- Device clock or scheduler causing erratic polling cadence.

Distinguishing authorization_pending, slow_down, access_denied, and expired_token:

| OAuth error | Meaning | Client Behavior |
|---|---|---|
| authorization_pending | User has not finished yet | Wait for interval and retry |
| slow_down | Polling faster than permitted | Increase interval per protocol |
| access_denied | User denied request | Stop polling and report outcome |
| expired_token | Device code has expired | Stop old request and start a fresh flow |

The client must not poll indefinitely after a terminal error. When the user denies or the code expires, clear temporary state and prompt the user to begin a new authorization session.

### 3.4 Invalid or Cross-Session User Code

Check how codes are displayed and entered: case sensitivity, visually ambiguous characters, separators, leading/trailing whitespace, and normalization rules. Codes need sufficient entropy and must not leak user-identifying information. Do not alter user_code after displaying it without updating the corresponding record.

If a user code is submitted repeatedly, the server must enforce expiration, attempt limits, and brute-force protection. The verification UI should display generic results to avoid revealing whether a code belongs to a specific account. After approval or denial, verify the code cannot be reused to flip the decision.

## 4. Diagnosing Pushed Authorization Requests (PAR)

PAR lets the client post authorization parameters directly to the PAR endpoint first. The Authorization Server stores the request and returns a short-lived request_uri. The client directs the browser to the authorization endpoint using client_id and request_uri instead of putting all authorization parameters in the browser URL.

General flow:

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant B as User Browser
    C->>AS: POST PAR with authorization parameters
    AS-->>C: request_uri, expires_in
    C->>B: Authorization endpoint with client_id and request_uri
    B->>AS: GET authorization request
    AS->>AS: Look up and verify pushed request
    AS-->>B: Continue login / consent
~~~

### 4.1 PAR Endpoint Returns 404 or Unsupported Request

- Check the library version and whether the PAR endpoint is supported/enabled in configuration.
- Compare the actual URL against the configured endpoint; do not assume every version or application uses the same path.
- Verify the reverse proxy routes the POST method and path properly.
- Check issuer, base URL, context path, and forwarded headers configuration.
- Verify the request hits the Authorization Server, not a resource server or another gateway.

If a PAR extension is implemented separately, verify the filter/endpoint is registered in the right filter chain and is not intercepted earlier by another security chain.

### 4.2 PAR Returns invalid_client or unauthorized_client

Check client authentication at the PAR endpoint. Compare client_id, the registered authentication method, and the credentials used. A client might authenticate at the token endpoint yet fail at PAR if endpoint configuration or filter chains apply different rules.

Do not assume every client type can use PAR under the same policy. Check protocol requirements, deployment policy, and specific client settings. With private key JWT or mTLS, verify client assertion audience, assertion lifetime, certificate chain, and accurate client mapping.

### 4.3 Authorization Endpoint Returns invalid_request_uri

Common causes:

- request_uri was truncated, poorly encoded, or the client sent the wrong value.
- Request URI expired before the user opened the authorization page.
- URI was generated by a different issuer or environment.
- PAR record was not persisted durably or another instance cannot read it.
- Request URI is no longer valid under the server's one-time-use/replay policy.
- client_id in the authorization request does not match the client bound to the pushed request.
- Client sent extra authorization parameters conflicting with the pushed payload.

Check PAR creation timestamp, expires_in, authorization request arrival timestamp, and the client ID bound to the record. Use correlation IDs or internal request references to correlate; never log full request URIs, as the URI can grant access to pending authorization data.

### 4.4 PAR Succeeds, Yet Authorization Parameters Are Wrong

Compare the parameters the client sent to the PAR endpoint with the data the Authorization Server stored and applied when processing the authorization request. Fields to check include response_type, redirect_uri, scope, state, nonce, code_challenge, code_challenge_method, resource, prompt, and max_age if supported.

Typical mistakes:

- redirect_uri does not match the registered value exactly.
- PKCE challenge is missing or its method is disallowed.
- scope exceeds permissions granted to the client.
- response_type is unsupported for the client.
- Authorization request sends both request_uri and disallowed duplicate parameters.
- request_uri was created for client A, yet the authorization request declares client B.

If PAR is stored in a database, verify TTL and cleanup of expired records. If using a cache, every instance must be able to resolve the same request URI during its validity window. Test both expired URIs and URIs already consumed per server policy.

## 5. Diagnosing OAuth 2.0 Token Exchange

Token Exchange allows a client to ask the Authorization Server to exchange an input token for another token with a different scope, audience, or delegation context. The standard grant type is:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

A request typically includes subject_token, subject_token_type, and optionally actor_token, actor_token_type, requested_token_type, audience, resource, or scope, depending on server policy.

Illustrative request shape:

~~~http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<input-token>
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=https%3A%2F%2Fapi.example.test
&scope=orders.read
~~~

Never put real tokens in documentation, logs, or shell history. The request above illustrates only parameter structure.

### 5.1 unsupported_grant_type or unauthorized_client

unsupported_grant_type indicates the token endpoint does not recognize the submitted grant type or the extension is not registered properly. unauthorized_client usually indicates the client authenticated but is not allowed to use that grant type.

Check:

- Does RegisteredClient declare the token exchange grant type as required by the application?
- Does the running Spring Authorization Server version support it out of the box, or does the application require a custom extension?
- Does the authentication converter recognize the grant type properly?
- Is the corresponding authentication provider registered on the token endpoint?
- Is the provider invoked after client authentication succeeds?
- Is the client permitted to exchange tokens for the requested audience/resource and scope?

If using a custom grant, verify converter/provider ordering and ensure the extension does not accidentally intercept other grant types. A provider should accept only the Authentication types it supports; out-of-scope requests must pass to the appropriate provider or return a clear OAuth2 error.

### 5.2 invalid_grant When subject_token Is Rejected

Validate the input token according to its subject_token_type:

- Does the token have the expected issuer and a valid signature?
- Is the token unexpired and unrevoked?
- Is the audience appropriate for exchange?
- Is the token the right type and intended purpose?
- Was an authorization code, refresh token, or ID Token accidentally passed instead?
- If opaque, can the server introspect or query status from a trusted source?
- If issued by another issuer, does the trust relationship permit that issuer?

Never accept a JWT merely because its header and payload parse. Verify signature, issuer, audience, expiration, and required claims. For opaque tokens, claims cannot be inspected by decoding; use introspection or a trusted lookup mechanism.

invalid_grant can also occur when the subject token has expired, is inactive, belongs to an unauthorized principal, or violates delegation policy. Log an internal reason code to distinguish these cases without leaking sensitive details to the client.

### 5.3 Token Issued, Yet Wrong Audience or Scope

Token exchange must enforce downscoping and delegation policies. Verify the audience/resource requested by the client, permissions on the subject token, permissions of the actor (if any), scopes permitted for the client, and policy of the target resource server.

Never let clients pick arbitrary audiences or escalate scopes beyond the subject's permissions. If orders.read is requested while the source token only holds profile, the server must reject or issue a policy-constrained token; never automatically grant higher privileges merely because the client authenticated.

When the token response succeeds yet the resource server returns 401/403, check:

- Does aud of the new token match the resource server?
- Are scopes or authorities mapped properly to endpoint permissions?
- Are iss, kid, signature, and lifetime valid?
- Is the token of a type accepted by the resource server?
- Is the resource server receiving the original source token instead of the exchanged token?

### 5.4 Actor Token and Delegation Chain

If the request includes actor_token, validate the actor token, actor type, issuer, audience, and delegation authority. Determine under what relationship the actor acts on behalf of the subject, whether delegation is permitted, and whether delegation chain depth is bounded.

Do not merely verify the actor token's signature and assume the actor can represent the subject. You need a policy binding subject, actor, client, and resource. The newly issued token should carry appropriate delegation info, such as the act claim per the implemented profile, and the resource server must interpret that claim accurately.

## 6. Diagnosing DPoP Token Binding

DPoP (Demonstrating Proof of Possession) binds an access token to a client key pair. The client sends a DPoP proof JWT in the DPoP header; the access token can carry a cnf confirmation claim containing the public key thumbprint. When calling the resource server, the client must prove possession of the corresponding private key.

Components commonly verified in a DPoP proof:

- Header typ equals dpop+jwt.
- alg is an asymmetric algorithm permitted by the server; reject none or unsuitable symmetric algorithms.
- Header jwk contains the public key, with no private key material.
- Claim htm matches the HTTP method.
- Claim htu matches the target URI per DPoP normalization rules; query and fragment are excluded from htu.
- Claim iat falls within the allowed time window.
- Claim jti is unique and has not been replayed.
- Claim nonce matches if the server requires a nonce.
- When accessing a resource with an access token, claim ath binds the proof to that exact access token.

If the server returns use_dpop_nonce, the client must obtain a nonce via the server's mechanism and mint a fresh proof. Never reuse an old proof because its jti, timestamp, or nonce may no longer be valid.

### 6.1 invalid_dpop_proof

Inspect each component of the proof:

| Component | Common Error | How to Check |
|---|---|---|
| typ | Not dpop+jwt | Inspect protected header |
| alg | Rejected algorithm | Compare against allowlist |
| jwk | Missing public key or contains private material | Publish public components only |
| htm | Wrong method, e.g. proof created for GET on a POST request | Compare actual method |
| htu | Different scheme/host/path or wrong normalization | Inspect target URI as seen by the server |
| iat | Proof too old or clock skew | Sync NTP and check time window |
| jti | Duplicate or already used | Check replay cache |
| nonce | Missing or mismatches server nonce | Obtain fresh nonce and sign a new proof |
| ath | Does not bind to the exact access token | Compute hash per spec against the submitted token |

After TLS termination at a reverse proxy, the server may see an internal scheme/host instead of the public URI. When that happens, htu comparison can fail. Forwarded headers and trusted proxy configuration must be accurate; trust only headers written by trusted proxies. Never accept X-Forwarded-Host or X-Forwarded-Proto sent directly by external clients without proxy control.

### 6.2 DPoP Token Rejected by Resource Server

Verify whether the token response has token type DPoP per configuration and whether the access token includes cnf.jkt matching the public key in the proof. Resource requests must send the exact authorization scheme and DPoP proof header required by the DPoP profile. Sending a DPoP token as Bearer or omitting the proof will cause the resource server to reject it.

For each request to a resource server, the proof must match the target method and URI. When an access token is present, the proof must bind to that token via ath. If the client rotates keys while still using an access token bound to the old key, thumbprints will mismatch and the token must be rejected; the client must obtain a new token using the matching key.

### 6.3 Replay Cache Not Shared Across Instances

DPoP proofs use jti to identify each proof. If each node keeps a private replay cache, the same proof could be sent to node A and then node B before either sees the other's jti. Multi-instance deployments need consistent replay detection, typically via a shared cache store with TTL aligned to the proof acceptance window.

Test by sending the exact same proof to two instances within the valid window. The expected result is that the proof is accepted only once per replay policy. Also test cache outages: if replay cannot be verified safely, the system must fail closed or follow a risk-assessed policy rather than silently skipping checks.

## 7. Diagnosing mTLS Certificate-Bound Access Tokens

An mTLS-bound access token ties the token to a client certificate. The resource server checks whether the certificate used on the TLS connection has a thumbprint matching the cnf.x5t#S256 claim in the token.

Check the following:

- Did the client send the right certificate during the TLS handshake?
- Is the certificate valid, unexpired, and chained to a trusted CA?
- Did the Authorization Server identify the certificate properly and map it to the client?
- Does the token contain the expected certificate thumbprint?
- Does the resource server receive the same client's certificate on the request?
- Does a reverse proxy/load balancer terminate TLS and forward certificate info over a protected channel?
- Was the certificate renewed or replaced after the token was issued?

A common failure occurs when TLS terminates at a load balancer, preventing the Authorization Server or resource server from seeing the original client certificate. If the proxy forwards certificate details via headers, strip client-supplied headers at the trust boundary and accept only values verified, signed, or transmitted by the proxy over a protected internal channel. Never trust headers like X-Client-Cert directly from the Internet.

When a certificate is renewed and its thumbprint changes, old tokens remain bound to the old thumbprint. The client must obtain a new token bound to the new certificate per policy. Do not alter claims on old tokens or bypass certificate checks as a quick fix.

DPoP and mTLS are distinct proof-of-possession mechanisms. DPoP proves key ownership via an HTTP-layer proof JWT; mTLS relies on a TLS-layer client certificate. Do not use configuration or test results from one mechanism to conclude the other is working.

## 8. Cross-Cutting Configuration Errors Across Flows

Several errors appear across multiple grant types and extensions:

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| invalid_client | Wrong client secret, assertion, certificate, or auth method | Compare RegisteredClient and authentication method |
| unauthorized_client | Client not permitted to use grant/endpoint | Check grant types and policy |
| unsupported_grant_type | Grant unsupported or provider unregistered | Check version, converter/provider, and token endpoint |
| invalid_scope | Scope not permitted for client/resource | Compare requested scope with policy |
| invalid_request | Missing parameter, duplicate parameter, or wrong format | Check form/body and endpoint rules |
| invalid_grant | Credential expired, used, revoked, or invalid | Check authorization state and token validation |
| invalid_token | Invalid signature, issuer, audience, lifetime, or binding | Check token and resource server |
| 401/403 at resource server | Missing authority, audience, or proof-of-possession | Check claims and verification mechanism |

Check these additional factors:

- **Issuer and discovery**: issuer must be consistent across tokens, metadata, PAR requests, resource servers, and nodes.
- **Clock skew**: synchronize clocks across clients, Authorization Server, KMS, and resource servers; check iat, exp, nbf, and nonce TTLs.
- **JWKS cache**: new public keys must be published and resource servers must refresh caches per policy.
- **Client configuration**: grant types, authentication methods, redirect URIs, scopes, and token settings must match across environments.
- **Reverse proxy**: scheme, host, port, path, and client certificate forwarding must accurately reflect the public connection.
- **Shared state**: device authorizations, PAR request URIs, replay caches, authorizations, and consents need shared storage if requests can hit multiple instances.
- **Transaction boundaries**: state must be committed before returning success; storage failures must never turn into false-positive token responses.

## 9. Error Reproduction and Fix Verification Matrix

After identifying the cause, create a reproducible test before changing configuration. Each test should use dedicated clients and tokens, controlled timestamps, and a correlation ID.

| Group | Error Reproduction | Pass Criteria After Fix |
|---|---|---|
| Device Flow | Poll before interval, enter wrong user code, approve after code expires | Client honors interval; pending/denied/expired states are accurate |
| Device Flow multi-node | Create code on A, approve on B, poll on A | Nodes observe the same authorization state |
| PAR | Use expired request URI, wrong client ID, or tampered URI | Invalid requests are rejected with the right OAuth error |
| PAR multi-node | Create PAR on A, open authorization endpoint on B | B reads the valid pushed request |
| Token Exchange | Use subject token with wrong issuer/audience/expiry or excessive scope | Server rejects or downscopes per policy |
| Token Exchange delegation | Actor lacks authority to represent subject | Exchange is rejected without issuing over-privileged tokens |
| DPoP | Wrong htm, htu, ath, nonce, or replayed jti | Invalid proofs are rejected |
| DPoP multi-node | Send same proof to A and B | Replay is detected across nodes |
| mTLS | Missing certificate, wrong certificate, or rotated certificate | Token binding is verified by thumbprint |
| JWKS rotation | Token uses new key while resource server holds stale cache | Key refreshes via configured mechanism and valid tokens verify |

A fix is complete only after testing both happy paths and failure paths. Do not merely verify a failing request changed from 400 to 200; inspect that the issued token carries the right subject, audience, scopes, lifetime, and binding. For replay or one-time-use bugs, re-run tests concurrently and across instances.

## 10. Production Incident Workflow

When an actual incident occurs:

1. Identify the failing flow, endpoint, client, and instance; record timestamp and correlation ID.
2. Capture the OAuth error code and HTTP status; compare against logs of the relevant endpoint.
3. Check client authentication, RegisteredClient, grant type, and policy.
4. Check authorization state, TTL, consent, request URI, or token metadata using internal IDs.
5. Check database, shared cache, clocks, JWKS, KMS/HSM, and reverse proxy.
6. Reproduce in a test environment with fresh data; never use real users' credentials.
7. Deploy a tightly scoped fix and verify other grant types remain unaffected.
8. Monitor error rates, successful token exchanges, device polling, PAR expiry, DPoP rejections, and mTLS binding failures after the fix.

If there are signs of exposed tokens or keys, escalate to the appropriate incident response procedure. Never enable full request body logging or disable signature, audience, nonce, replay, certificate, or token-binding checks just to let requests pass. Such shortcuts mask symptoms while destroying the security boundaries the flow relies on.

A useful incident report states the symptoms, OAuth error, affected client/instance scope, root cause, applied changes, before/after reproduction tests, and remaining limitations. Use only fingerprints or internal IDs to correlate tokens and authorizations; never attach credential values.

By diagnosing per endpoint, error code, storage state, and corresponding verification mechanism, engineering teams can distinguish protocol errors from Spring integration bugs, multi-instance sync issues, and proxy/key misconfigurations. This targets the exact fault while keeping OAuth 2.0/OpenID Connect security checks intact.
