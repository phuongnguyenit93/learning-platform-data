# Regression Testing OAuth/OIDC Flows and Client Interoperability

When upgrading Spring Authorization Server or Spring Security, an application may start up normally and endpoints may return HTTP 200, yet real clients fail to log in, fail to exchange authorization codes, fail to refresh tokens, or fail to verify ID tokens. The cause usually lies in changes to configuration, protocol behavior, metadata, client authentication, cookies/sessions, token claims, or how authorizations are stored across the new version.

Regression testing must prove that the OAuth 2.0 and OpenID Connect contracts the system provides continue working with supported clients. This article explains how to build an end-to-end test suite, test compatibility across client and Authorization Server versions, and catch unexpected behavioral changes after an upgrade.

After this lesson, you will be able to:

- Establish a baseline for the OAuth/OIDC flows currently in use.
- Test authorization code, PKCE, client credentials, refresh token, and enabled grant types.
- Verify discovery metadata, JWKS, ID tokens, UserInfo, and token validation at the Resource Server.
- Assess interoperability with legacy client libraries and client configurations.
- Detect changes in redirect URIs, client authentication, scopes, consent, error responses, and sessions.
- Organize regression testing before and after upgrades, including existing database records.

## 1. Defining the Contracts to Preserve

OAuth 2.0 and OpenID Connect define the protocols and messages exchanged by clients, the Authorization Server, and Resource Servers. Regression testing should begin from the contracts the system actually publishes, based on the grant types, authentication methods, scopes, endpoints, and extensions currently enabled.

Not every system implements the same feature set. Build a list from the application's current configuration and behavior, then classify each item as required, optional, or unsupported.

| Contract | What to Fix in the Baseline |
|---|---|
| Issuer and discovery | Exact issuer, endpoints, algorithms, and advertised capabilities |
| Client registration | Client ID, client type, redirect URIs, grant types, scopes, and authentication methods |
| Authorization code | Redirects, state, consent, code lifetime, and single-use enforcement |
| PKCE | `S256` method, `code_verifier` check, and mandatory PKCE policy |
| Token endpoint | Client authentication, grant types, token types, scopes, and protocol errors |
| Refresh token | Lifetimes, reuse/rotation policy, and handling of expired or revoked tokens |
| OIDC | `openid` scope, nonce, ID token, JWKS, UserInfo, and promised claims |
| Resource Server | Signature, issuer, audience, validity timestamps, and access permissions |
| Persistence | Clients, authorizations, consents, and active tokens after restarts or migrations |

For each contract, document input requests, expected responses, error codes, storage state, and which clients depend on that behavior. The baseline must reflect the verified behavior of the running version, not merely intended configuration.

## 2. Pre- and Post-Upgrade Testing Strategy

A regression workflow can be split into four layers:

1. **Contract tests:** verify endpoints, HTTP statuses, headers, JSON fields, redirects, and error responses.
2. **Protocol integration tests:** run full flows through the Authorization Server, database, sessions, and JWT decoder.
3. **Client interoperability tests:** use client libraries or representative applications to execute the protocol like a real client.
4. **Migration regression tests:** use existing data, upgrade the schema, and verify continued processing of legacy authorizations/tokens.

Run the same scenario suite against both the current version and the upgraded version with equivalent inputs. Compare outcomes by protocol semantics. Random values such as authorization codes, access tokens, refresh tokens, `state`, `nonce`, issuance timestamps, and `kid` can differ; do not compare raw token strings verbatim or snapshot entire responses containing secrets.

Instead, normalize responses before comparing: check required fields, token type, scopes, lifetimes, issuer, audience, redirect URI, and error codes. For JWTs, decode headers/payloads to inspect claims, then still verify the signature using the public key from JWKS. Decoding payloads alone does not prove a token is valid.

### 2.1. Version Matrix

Select representative clients according to how they are deployed and operated:

| Authorization Server | Legacy Clients | Upgraded Clients | Goal |
|---|---|---|---|
| Current version | Run | Run | Baseline and fixture verification |
| Upgraded version | Run | Run | Verify backward and forward compatibility |
| Upgraded version + legacy data | Run | Run | Verify migration and existing data |

Legacy clients are applications still supported that cannot upgrade at the same time as the Authorization Server. New clients represent SDKs or applications releasing in the same cycle. You do not need to test unsupported combinations, but you must test combinations that real users or systems depend on.

### 2.2. Keeping Test Data Stable

Create fixtures for each client type, such as:

- Public client using authorization code and PKCE.
- Confidential client using `client_secret_basic` or the configured authentication method.
- Service client using client credentials.
- OIDC client requesting `openid`, nonce, and UserInfo.
- Clients with multiple redirect URIs or custom scopes if the application supports those cases.

Do not use production clients or production secrets in tests. Use test-only secrets and store fixtures so secrets are never written to logs or snapshots. Generate fresh test data per run when codes or refresh tokens have single-use state.

## 3. Testing Authorization Code and PKCE

Authorization code is the most important flow for web and native applications. An end-to-end scenario must verify the authorization request, login, consent, redirect callback, exchanging the code for tokens, and using the token at a Resource Server.

### 3.1. Preparing the PKCE Request

The client generates a random `code_verifier` for each authorization request. For the `S256` method, `code_challenge` is computed as SHA-256 over the verifier and encoded with URL-safe Base64 without padding.

```java
static String createCodeChallenge(String verifier)
        throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
```

In tests, generate the verifier using a cryptographic random generator and keep the verifier on the test client side. Send the challenge to the authorization endpoint, then send the verifier when calling the token endpoint. Never log the verifier or authorization code.

An authorization request typically includes these parameters:

```text
response_type=code
client_id=web-client
redirect_uri=https://client.example.test/callback
scope=openid profile orders.read
state=<random-state>
nonce=<random-nonce>
code_challenge=<base64url-sha256>
code_challenge_method=S256
```

`nonce` is required when the client requests OIDC and wants to bind the ID token to the authentication request. `state` is a client-generated value to correlate the callback with the initial request and prevent CSRF in the redirect flow. The Authorization Server returns `state`; the client itself must verify the returned value matches the stored value. Validating `state` on the client side is part of interoperability testing and cannot be replaced by asserting that the server merely returned HTTP success.

### 3.2. End-to-End Test Steps

1. Send an authorization request with `response_type=code`, a registered redirect URI, and PKCE S256.
2. Authenticate the user using a test identity or configured login mechanism.
3. If the client requires consent, complete consent and verify granted scopes.
4. Verify the redirect callback targets the exact registered URI, carries an authorization code, and returns `state` intact.
5. Exchange the code for tokens using the proper client authentication method.
6. Verify the access token, token type, scopes, and lifetime.
7. Send the access token to the Resource Server and verify access permissions.
8. Attempt to reuse the authorization code and verify the server rejects it.

At the token exchange step, example with a confidential client using HTTP Basic:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("web-client", testClientSecret))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "authorization_code")
        .param("code", authorizationCode)
        .param("redirect_uri", redirectUri)
        .param("code_verifier", codeVerifier))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.access_token").isNotEmpty())
    .andExpect(jsonPath("$.token_type").value("Bearer"));
```

This snippet assumes `authorizationCode` was captured from the callback after a successful authorization flow, `testClientSecret` is a test secret, and the token endpoint uses the default path. For a public client, do not send a client secret; the request must be identified via `client_id` and parameters matching the client configuration.

### 3.3. Negative Cases for PKCE and Authorization Code

| Case | Outcome to Verify |
|---|---|
| Missing `code_verifier` when PKCE is required for client | Token endpoint rejects the grant |
| Verifier does not match challenge | Rejected with appropriate error; no token issued |
| Using verifier from another authorization request | Rejected |
| Changing `code_challenge_method` to a disallowed method | Rejected per PKCE policy |
| Redirect URI differs from registered URI | Authorization or token request rejected at the corresponding check step |
| Expired authorization code | Rejected with `invalid_grant` |
| Reusing authorization code | Rejected; no second token issued |
| Code belongs to another client | Rejected |
| Invalid client authentication | Client authentication rejected |
| User denies consent | Returns appropriate authorization error without issuing a code |

Do not check only the status code. For OAuth errors, also check the JSON `error`, ensure the body leaks no sensitive info, and verify no token is issued. At the authorization endpoint, errors are typically returned via a valid redirect URI per OAuth rules; if the redirect URI is invalid, the server must never redirect arbitrarily to the request-supplied URI.

## 4. Testing Client Authentication and Grant Types

Upgrades can affect how clients authenticate at the token endpoint. Test every method the system permits and confirm published metadata matches actual configuration.

Methods you may encounter include:

- `client_secret_basic`: client sends credentials via HTTP Basic per OAuth rules.
- `client_secret_post`: client sends credentials in the form body; test only if enabled for compatibility reasons.
- `private_key_jwt`: client signs a JWT assertion using a registered private key.
- Mutual TLS or other methods if integrated and published by the system.

Do not assume every client uses the same method. Check each `RegisteredClient` individually and cross-check discovery metadata if the Authorization Server advertises the corresponding field.

| Check | Outcome to Verify |
|---|---|
| Secret matches registered method | Authentication succeeds |
| Wrong secret or unknown client | Rejected with `invalid_client` per protocol |
| Client uses unregistered method | Rejected |
| Client sends two authentication methods simultaneously | Rejected per client authentication rules |
| Expired client assertion or invalid signature | Rejected |
| Client assertion `aud` does not match token endpoint | Rejected |
| Assertion ID (`jti`) replayed when replay detection is deployed | Rejected per policy |

For each supported grant type, test both success and failure flows. For instance, client credentials requires valid client authentication, a registered grant type, and permitted scopes. Do not issue refresh tokens or ID tokens for this flow unless a specific extension defines that behavior and the system intentionally supports it.

Do not add policy-retired grant types to the supported list merely because an old client still sends requests. For example, implicit grant and resource owner password credentials should not be defaults for new integrations. If the system must reject them, write tests proving the server issues no tokens for those requests.

## 5. Testing Refresh Tokens and Authorization Lifecycle

Refresh tokens usually outlive access tokens and rely on state stored in the Authorization Server. Persistence or token configuration upgrades can break previously issued refresh tokens.

Test with a client permitted to use `refresh_token`:

1. Obtain an access token and refresh token via the configured authorization code flow.
2. Send the refresh token to the token endpoint with proper client authentication.
3. Verify a new access token is issued, scopes do not exceed original grants, and the old token is handled per reuse/rotation policy.
4. Attempt refresh with expired, revoked, or policy-reused tokens.
5. Verify behavior after an Authorization Server restart and after database migration finishes.

Spring Authorization Server lets you configure refresh token reuse behavior. Therefore, tests must use your application's policy as the baseline. If the system rotates refresh tokens, verify a new token is returned and the old token cannot be reused per policy. If the system allows reuse, verify that behavior matches configuration and lifetime. Do not write tests assuming all deployments share the same defaults.

Also verify:

- A refresh token cannot be used by another client.
- A refresh token cannot expand scopes beyond granted permissions.
- Revocation takes effect per the implemented policy.
- Withdrawn consent is reflected in subsequent authorization requests.
- Stored authorizations remain readable after restarts or upgrading to the new version.
- Two concurrent refresh requests are handled consistently with the rotation/reuse policy without creating inconsistent token state.

## 6. Testing OpenID Connect

OpenID Connect adds an identity layer on top of OAuth 2.0. An OAuth flow issuing an access token is not enough to prove OIDC works. Clients must verify ID tokens and related endpoints.

### 6.1. Discovery Metadata

Call the OpenID Provider Configuration at the published discovery path. Typically this endpoint takes the form `/.well-known/openid-configuration` attached to the issuer; use the system's exact issuer URL instead of hardcoding paths if the issuer includes a path component.

Check critical fields:

- `issuer` matches the configured issuer and token `iss` claim exactly.
- `authorization_endpoint`, `token_endpoint`, and `jwks_uri` point to endpoints reachable by clients or Resource Servers.
- `userinfo_endpoint` is present when the system supports UserInfo.
- `response_types_supported` and `grant_types_supported` reflect actual capabilities.
- `subject_types_supported` and `id_token_signing_alg_values_supported` match configuration.
- `token_endpoint_auth_methods_supported` reflects enabled client authentication methods.
- Additional OIDC capabilities are advertised only when implemented and tested.

Do not snapshot the entire discovery JSON without normalizing environment hosts, timestamps, or endpoints. Instead, assert contract values and confirm no internal endpoints, pod hostnames, or unexpected HTTP URLs are advertised.

### 6.2. ID Token and Nonce

When a client requests the `openid` scope, verify the token response includes an ID token per the configured OIDC flow. The ID token must have its signature verified via JWKS and these claims checked:

| Claim | Check |
|---|---|
| `iss` | Matches trusted issuer |
| `sub` | Has subject identifier value and remains stable per provider subject policy |
| `aud` | Contains the client ID that sent the authorization request |
| `exp` | Unexpired, accounting for policy clock skew |
| `iat` | Valid issuance timestamp |
| `nonce` | Matches the nonce generated and sent by the client in the authorization request |
| `azp` | Verified per OIDC rules when multiple audiences exist or when required |

If the client uses `max_age`, verify `auth_time` as required. If the system supports `prompt`, `acr_values`, or other OIDC parameters, add tests matching published behavior. Do not treat an optional claim as mandatory across every configuration if the application does not use it.

An ID token with a valid signature but wrong `aud` must still be rejected. Likewise, a nonce mismatch is a client-side failure when validating the ID token; the client test must check this and refuse to establish a login session.

### 6.3. UserInfo and Subject Consistency

If `userinfo_endpoint` exists, call the endpoint using an access token with appropriate permissions. Verify:

- The token is valid and holds required scopes.
- The response contains only claims permitted by scopes or policy.
- `sub` in UserInfo matches `sub` in the ID token.
- Expired, wrong-audience, or under-scoped tokens are rejected.

Do not assume all profile claims are returned simply because the client requested `profile` or `email`; actual data also depends on policy and user attributes. Define the exact claims promised by the application and test that set.

If the system integrates OIDC logout or an end-session extension, separately test post-logout redirects, session state, and client behavior. Do not assume a standard logout endpoint exists merely because the application supports discovery and ID tokens.

## 7. Testing Resource Servers and Token Semantics

After receiving an access token, the client or service calls a protected API. Regression tests must verify new tokens remain compatible with deployed Resource Servers, especially when changing claim customizers, signing algorithms, issuer, or JWKS.

Core checks:

- JWT has a valid signature and `kid` is found in JWKS.
- `iss` matches the trusted issuer.
- `aud` contains the API identifier if the Resource Server requires an audience.
- `exp` and `nbf` are checked with configured clock skew.
- Scopes/authorities map accurately to access permissions.
- Tokens lacking a scope are rejected at endpoints requiring that permission.
- Tokens with bad signatures, tampered payloads, or non-allowlisted algorithms are rejected.
- Legacy tokens during key transitions are verified per key policy.

If access tokens are opaque, test the introspection endpoint and active/inactive status per configuration. If tokens are self-contained JWTs, also test JWKS refresh and key rotation behavior. Do not assume introspection `active` checks and JWT signature checks are equivalent tests.

For scopes, verify both token contents and authorization outcomes. A token with scope `orders.read` must not access an operation requiring `orders.write`. If the system uses a custom claim to map authorities, keep a fixture for that claim across upgrades and confirm the Resource Server does not silently change mapping rules.

## 8. Testing Consent, Sessions, Redirects, and Browsers

Some bugs appear only in browser flows and never show up in direct token endpoint calls. After upgrading Spring Security, re-test:

- Login, saved requests, and redirecting back to the authorization endpoint.
- Session persistence across redirects and consent.
- CSRF protection on POST forms such as login and consent.
- Session cookies having `Secure`, `HttpOnly`, and `SameSite` suited to the deployment model.
- Redirect URIs matching exact registered URIs without accepting unintended wildcards.
- `state` returned and accurately validated by the client.
- Saved consent displayed and applied properly on subsequent authorizations.
- Logout and session invalidation working per supported behavior.

For applications behind a reverse proxy, verify scheme/host generated from trusted forwarded headers. Redirect URLs and discovery endpoints must use the public issuer, never exposing internal hostnames or wrong protocols. Test in real HTTPS environments or staging with TLS termination matching production.

## 9. Interoperability with Client Libraries

A protocol-compliant server can still be incompatible with a client if metadata, encoding, authentication methods, or redirect behaviors differ from library expectations. Select representative clients from your live ecosystem and test using the actual libraries, versions, and deployed configurations.

Examples of client groups you may need to test:

| Client Group | Representative Scenario |
|---|---|
| Spring Security OAuth2 Client | Authorization code login, callback, token refresh, and principal mapping |
| Native/mobile application | Authorization code + PKCE S256, external browser, and callback URI |
| Confidential web client | Client authentication, redirect URI, session, and refresh token |
| Service-to-service | Client credentials and API scopes |
| OIDC relying party | Discovery, ID token validation, nonce, and UserInfo |
| Spring Security Resource Server | JWKS, JWT validation, authority mapping, and key rotation |

Do not test only a custom-written client built on the same assumptions as the Authorization Server. Use at least one independent client library or supported representative application to uncover protocol implementation differences.

When client libraries upgrade alongside the Authorization Server, run a two-way matrix: new server with old clients and new server with new clients. If a new client requires a capability the server does not advertise, determine whether it is a needed configuration change or an out-of-scope feature.

### 9.1. Common Sources of Failure

- Client library reads discovery metadata to find endpoints, but the server advertises an inaccurate issuer or URL.
- Client sends `client_secret_post` while client registration only allows `client_secret_basic`.
- Client sends a redirect URI differing in trailing slash, port, scheme, or encoding.
- Client requests an unregistered or unpermitted scope.
- Client expects a refresh token, but `offline_access` or refresh issuance policy is not configured as expected.
- Client fails to validate `state`, `nonce`, issuer, or audience properly.
- Resource Server caches stale JWKS during key rotation.
- Client parses error responses or redirects in a format the server no longer returns.

When a failure is found, save requests/responses scrubbed of secrets, tokens, and sensitive user info. Record client library/version, relevant config, endpoint, HTTP status, and error code for reproduction.

## 10. Testing Persistence and Data Migration

Application upgrades often accompany schema, JDBC driver, or authorization/token serialization changes. A test suite that only creates fresh data on an empty schema will fail to catch bugs reading data saved by the previous version.

Create a database fixture using the current version, including:

- Registered clients with multiple grant types, redirect URIs, scopes, and authentication methods.
- Active authorizations containing authorization codes or refresh tokens per supported flows.
- Saved consents for users and clients.
- Expired or revoked tokens if the schema stores those states.

Then execute the migration following the upgrade procedure, start the new version, and verify:

1. Registered clients are read accurately and still authenticate with legacy methods.
2. Still-valid authorizations can be read and processed onward.
3. Legacy refresh tokens work or are rejected strictly per committed policy.
4. Consents are neither lost nor automatically granted broader permissions.
5. Revoked tokens do not revert to active status.
6. A subsequent restart causes no unexpected data mutation.

For rolling deployments, verify schema compatibility with both old and new application versions while both run concurrently. Use the expand/contract strategy: add compatible structures first, deploy the application, migrate data if needed, and remove old structures only when no running version uses them.

Never put real production data into fixtures. Use synthetic data or sanitized copies, and never log access tokens, refresh tokens, authorization codes, or client secrets in test logs.

## 11. Checking Error Responses and HTTP Contracts

Regression tests must check protocol errors because clients often rely on `error` to decide whether to retry, prompt re-login, or display messages.

| Scenario | Error Typically Checked |
|---|---|
| Missing or invalid request parameter | `invalid_request` |
| Invalid client authentication | `invalid_client` |
| Invalid authorization code/refresh token | `invalid_grant` |
| Client not permitted to use grant type | `unauthorized_client` |
| Unsupported grant type | `unsupported_grant_type` |
| Invalid scope | `invalid_scope` |
| Resource Server rejects Bearer token | `invalid_token` or appropriate Bearer challenge response |
| Valid token lacking permission | `insufficient_scope` when using appropriate Bearer token challenge |

Also check HTTP properties:

- `Content-Type` matches the JSON or form-encoded response.
- `Cache-Control` and token-response protection headers meet security requirements.
- `WWW-Authenticate` is returned when Bearer authentication fails per applicable rules.
- No stack traces, SQL details, secrets, or tokens appear in error responses.
- No redirects outside the registered URI list.
- CORS allows only configured origins and methods; preflight reflects current policy.

Do not require every error to share the same HTTP status code if protocol specifications define different handling for the authorization endpoint versus the token endpoint. Compare both HTTP status and error payload per endpoint and scenario.

## 12. Automating the Test Suite

A test suite can be layered to run fast on pull requests and thoroughly before release:

```text
src/test/
  java/
    .../contract/
      DiscoveryMetadataContractTest.java
      JwksContractTest.java
      TokenEndpointErrorContractTest.java
    .../protocol/
      AuthorizationCodePkceFlowTest.java
      ClientCredentialsFlowTest.java
      RefreshTokenLifecycleTest.java
      OidcIdTokenUserInfoTest.java
      RevocationIntrospectionTest.java
    .../interop/
      SpringOAuth2ClientCompatibilityTest.java
      NativePkceClientCompatibilityTest.java
      ResourceServerCompatibilityTest.java
    .../migration/
      ExistingAuthorizationMigrationTest.java
```

This is an illustrative layout; use packages and test names suited to your project structure. Some tests require a real database via Testcontainers to verify transactions, constraints, migrations, and persistence. HTTP tests can use MockMvc or WebTestClient for the server, while client interoperability should run over real HTTP in integration/staging to test redirects, cookies, TLS, and library behavior.

### 12.1. Pipeline Tiering

| Stage | Tests to Run | Goal |
|---|---|---|
| Pull request | Contract tests, basic PKCE, client authentication, JWT validation | Catch regressions fast |
| Integration build | Full OAuth/OIDC flows, database, consent, refresh, introspection | Verify integrated components |
| Pre-release | Legacy/new clients, migration from legacy data, reverse proxy/TLS | Verify compatibility |
| Staging drill | Rolling deployment, key rotation, dependency failures, emergency revoke | Verify operational behavior |

Each test should have deterministic inputs, timeouts, cleanup, and traceable logs. Never let parallel tests share a single-use authorization code or refresh token. Create distinct client IDs per test case or reset fixtures before each test group.

### 12.2. Upgrade Exit Criteria

Mark an upgrade as passing only when:

- All mandatory baseline flows succeed.
- Negative cases continue to be rejected per policy.
- Supported legacy clients continue working.
- Discovery and JWKS publish accurate issuer, endpoints, and key sets.
- New tokens are compatible with existing Resource Servers.
- Legacy client, authorization, and consent data are read accurately after migration.
- No unintended changes occur in scopes, claims, token lifetimes, consents, or error responses.
- Intentional protocol changes are documented and dependent clients tested.

## 13. Pre-Release Checklist for New Versions

- [ ] OAuth/OIDC baseline captured from the running version's behavior.
- [ ] List of clients, grant types, scopes, and authentication methods confirmed.
- [ ] Authorization code + PKCE S256 succeeds end-to-end from redirect to token endpoint.
- [ ] `state` validated by client and `nonce` verified in ID token.
- [ ] Redirect URIs and consent preserve policy.
- [ ] Client credentials and supported grant types have success/failure tests.
- [ ] Refresh tokens, rotation/reuse, revocation, and persistence tested.
- [ ] Discovery metadata and JWKS compatible with clients/resource servers.
- [ ] ID token, UserInfo, issuer, audience, and subject verified.
- [ ] Resource Server accepts valid tokens and rejects invalid signatures/claims/scopes.
- [ ] Supported legacy and new client libraries tested.
- [ ] Migration tested against synthetic data from the previous version.
- [ ] Error responses, HTTP headers, CORS, cookies, and redirects verified.
- [ ] Test logs contain no secrets, authorization codes, access tokens, or refresh tokens.
- [ ] Intentional protocol changes documented with a client upgrade plan.

## Conclusion

OAuth/OIDC regression testing must trace contracts from the authorization request through tokens, ID tokens, UserInfo, and protected APIs. Run identical scenarios on old and new versions, use representative client libraries, verify both success and failure paths, and run persisted data through migration. This testing approach catches protocol changes or incompatible behaviors before a new Spring Authorization Server release enters production.
