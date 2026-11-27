# OAuth/OIDC conformance assessment and regression testing after security changes

An Authorization Server works properly only when independent clients can understand and use it according to the OAuth 2.0/OpenID Connect standards, while security constraints remain intact after every change. A successful browser login flow is not enough to prove protocol compliance: redirects could be wrong, tokens could carry incorrect claims, PKCE could be bypassed, or metadata could advertise a different issuer than the ID Token.

Conformance assessment tests server behavior against chosen specifications and profiles. Regression testing verifies that previously correct behaviors stay correct after changes to code, configuration, dependencies, client data, signing keys, proxies, or infrastructure. The two activities complement each other: conformance establishes the target standard; regression keeps that standard stable across releases.

With Spring Authorization Server, you must test `RegisteredClient` configurations, OAuth/OIDC endpoints, user authentication, token issuance and validation, authorization/consent storage, as well as deployment behind reverse proxies. This lesson focuses on the Authorization Code Flow, PKCE, and the OpenID Connect Authorization Code Flow; other grants or profiles are assessed only when explicitly supported by the system.

## 1. Defining conformance scope

OAuth 2.0 is an authorization framework. OpenID Connect adds a user authentication layer and ID Tokens on top of OAuth 2.0. A server can support OAuth 2.0 without enabling OIDC; therefore, do not apply OIDC tests to unconfigured endpoints or features.

Before writing tests, catalog implemented features and applicable specifications:

| Scope | Relevant specification or requirement | Content to verify |
|---|---|---|
| OAuth 2.0 Authorization Framework | RFC 6749 | Authorization requests, token requests, clients, grants, redirects, and error responses |
| OAuth 2.0 Security Best Current Practice | RFC 9700 | PKCE, removal of weak flows, redirect protection, and defense against common OAuth attacks |
| PKCE | RFC 7636 | code_challenge, code_challenge_method=S256, and code_verifier |
| Authorization Server Metadata | RFC 8414 | OAuth metadata, issuer, and published endpoints |
| OAuth Token Revocation | RFC 7009 | Token revocation and post-revocation behavior |
| OAuth Token Introspection | RFC 7662 | Token state and information returned to resource servers |
| OAuth Authorization Server Issuer Identification | RFC 9207 | iss parameter in authorization responses, if supported |
| OpenID Connect Core 1.0 | OIDC Core | ID Tokens, nonce, UserInfo, authentication, and claims |
| OpenID Connect Discovery 1.0 | OIDC Discovery | Provider metadata, issuer, endpoints, and supported algorithms |
| Sender-constrained tokens | RFC 8705 or RFC 9449 | mTLS or DPoP, only when that profile is implemented |

Do not mark a system as "OAuth/OIDC conformant" merely because some endpoints return HTTP 200. Results must specify the exact specification version, profile, grant types, client types, and actually enabled features. If the product supports only Authorization Code Flow with PKCE and OIDC, the report must explicitly state that scope.

### Distinguishing three types of testing

- **Conformance tests:** verify requests and responses comply with standards, including valid, invalid, and boundary cases.
- **Security tests:** actively attempt bypasses, forgery, replay, information leakage, issuer/audience confusion, or protective mechanism downgrades.
- **Regression tests:** preserve verified conditions and re-run them after changes to detect behavioral degradation.

A single test can belong to multiple groups. For example, testing that an authorization code can be used only once serves as a protocol test, an anti-replay security test, and a regression test for the authorization store.

## 2. Preparing the test matrix

A matrix prevents missing features or testing only happy paths. Each row should specify the input request, preconditions, expected outcome, evidence, and severity upon failure.

| Group | Success case | Negative or boundary case |
|---|---|---|
| Metadata | Accurate public issuer and endpoints | Wrong issuer/host/scheme, metadata missing required endpoints |
| Authorization | Valid Authorization Code Flow | Missing or invalid client_id, response_type, scope, redirect_uri |
| PKCE | Matching S256 challenge and verifier | Missing verifier, wrong verifier, malformed challenge, or disallowed method |
| Redirect | URI matches registered URI verbatim | Mismatched host, port, path, query, or scheme |
| State and nonce | Client verifies state; OIDC client verifies nonce | Missing, altered, or session-mismatched values |
| Client authentication | Registered method accepted | Wrong secret, unsupported method, client disallowed from grant |
| Authorization code | Code exchanged once within validity window | Expired, already used, another client's, or different redirect's code |
| Access token | Valid signature, issuer, audience, expiry, and scope | Forged, expired, wrong issuer/audience, or disallowed algorithm |
| ID Token | Claims and signature valid per OIDC | Invalid iss, aud, nonce, exp, iat, sub, or signature |
| Refresh token | Rotates and issues new tokens per policy | Expired, revoked, replayed, or another client's token |
| Consent | Consent recorded and scoped accurately | User denies or scopes exceed consent |
| Revocation/introspection | Token state reflects policy accurately | Revoked token still accepted or introspection leaks excess data |
| JWKS and keys | kid points to right public key | Nonexistent kid, old key deleted too early, disallowed algorithm |
| Session and logout | Login/logout follow policy | Session fixation, CSRF, unregistered logout redirect |
| Deployment | HTTPS, proxy, and public URLs consistent | Spoofed headers, HTTP redirects, or unintended backend access |

The matrix must separate public clients from confidential clients. Public clients cannot securely hold a client secret; PKCE is the critical control protecting authorization codes. Confidential clients must be tested for both client authentication and PKCE per chosen policy. Never assume one client authentication method fits every client.

### Profiling each test client

Create clients representative of production configurations, for example:

| Client fixture | Type | Grants and features | Purpose |
|---|---|---|---|
| web-confidential-test | Confidential | Authorization Code, OIDC, PKCE | Test web applications with a backend |
| spa-public-test | Public | Authorization Code, PKCE S256 | Test browser-based clients |
| service-test | Confidential | Client Credentials | Test machine-to-machine if supported |
| legacy-negative-test | Public or confidential | Disallowed grant configuration | Verify server rejects retired flows |

Use client IDs, secrets, users, and keys dedicated to the test environment. Never copy production credentials into the test suite. Record each fixture's grant types, authentication methods, redirect URIs, scopes, consent policy, and token lifetimes so tests remain reproducible.

## 3. Testing Authorization Code Flow and PKCE

The Authorization Code Flow is the core flow to test for web applications and native/browser-based apps. Test flows should exercise the complete lifecycle: creating the authorization request, logging in, granting consent, receiving the code, exchanging the code for tokens, and using the tokens.

### Testing valid requests

A typical OIDC authorization request looks like:

~~~http
GET /oauth2/authorize?
  response_type=code&
  client_id=spa-public-test&
  redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
  scope=openid%20profile&
  state=state-value&
  nonce=nonce-value&
  code_challenge=BASE64URL_SHA256_CHALLENGE&
  code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Values above are illustrative; the challenge must be computed from the verifier per RFC 7636. Tests should verify:

1. The client is recognized and the grant type is allowed.
2. redirect_uri matches a registered URI verbatim.
3. response_type=code is supported.
4. Scopes are allowed for the client and user.
5. PKCE is required per policy and S256 is processed correctly.
6. For OIDC, the openid scope activates OIDC behavior; if the authorization request includes nonce, the matching value must appear in the ID Token.
7. The server enforces login and consent per policy, then redirects to the exact registered URI with the authorization code and matching state.

Do not verify state only on the Authorization Server side. state primarily helps the client correlate callbacks with initial requests and prevents CSRF in the redirect flow. Client tests must verify the returned state matches the generated value and reject callbacks missing or mismatching state.

### Testing PKCE with positive and negative tests

Given a generated verifier, the S256 challenge is computed as:

~~~text
code_challenge =
  BASE64URL-ENCODE-NO-PADDING(
    SHA256(ASCII(code_verifier))
  )
~~~

When exchanging the code at the token endpoint, submit the same code_verifier:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64(client-id:client-secret)

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
code_verifier=ORIGINAL_CODE_VERIFIER
~~~

For public clients, omit the client secret and authenticate using the registered client method. Never send a placeholder secret for a public client.

Minimum negative tests:

- Omitting code_verifier when the authorization code is bound to PKCE.
- Sending a verifier different from the one that generated the challenge.
- Using a verifier violating RFC 7636 syntax/length constraints.
- Sending a disallowed challenge method, such as plain, when policy allows only S256.
- Altering redirect_uri when exchanging the code.
- Reusing a code that was already exchanged successfully.
- Using an expired code or a code issued to another client.

Failure cases must return the appropriate protocol error, typically invalid_grant at the token endpoint when a code is invalid. Responses must not disclose which user or client owns the code or internal implementation details. Do not assert only the status code; verify the response contains no access token, refresh token, or ID Token on failure.

### Testing single-use authorization codes

Once a code is exchanged successfully:

1. Resubmit the exact same authorization code with the original verifier.
2. Verify the second exchange is rejected.
3. Verify no new tokens are issued.
4. Inspect authorization state in the store and security logs if the system emits audit events.

This test must run against the actual persistence backend in use. If the application runs multiple instances, issue the code on node A and exchange it on node B; then attempt replay across another node. Behavior must remain consistent across nodes.

## 4. Testing client authentication and grant policies

`RegisteredClient` governs which grants, scopes, and authentication methods a client may use. Client configuration edits can expand permissions without code changes, so regression tests are needed for client registration data and configuration loading.

For confidential clients, test each declared method, such as client_secret_basic, client_secret_post, private_key_jwt, or tls_client_auth if supported by the system. Never test an unenabled method as though it were mandatory.

Cases to test:

- Nonexistent client ID.
- Wrong or expired client secret.
- Client using a different authentication method than registered.
- Client sending credentials in multiple disallowed locations.
- Client requesting a grant type outside its granted list.
- Client requesting a disallowed scope.
- Client credentials used at an inappropriate endpoint or grant.
- Disabled or revoked client registration.

For secret rotation, confirm the new secret works after rollout and the old secret is rejected at the policy cutoff time. If the system supports a transition overlap window, test the exact overlap bounds and how the window closes.

Never log raw client secrets, private keys, authorization codes, access tokens, refresh tokens, or ID Tokens. When correlation is needed in test reports, use fixture IDs or non-replayable fingerprints.

## 5. Testing access tokens, ID Tokens, and JWKS

An access token is an authorization credential for resource servers. An ID Token is an authentication assertion for OIDC clients. Never use an ID Token as an access token or use an access token in place of OIDC client identity verification steps.

### Access tokens

For JWT access tokens, verify at minimum:

- Signature verified with a trusted public key.
- iss matches the configured issuer verbatim.
- aud contains the expected resource server when policy requires audience.
- exp has not elapsed and nbf (if present) is active.
- iat is reasonable per policy.
- Scopes or authorities accurately reflect granted permissions.
- Signing algorithm is within the allowlist.
- kid selects the right key in JWKS.
- Token contains no unnecessary sensitive data.

If the system uses opaque tokens, test the introspection flow, active status, client/resource audience, scopes, and caching policy. Do not apply JWT claim tests to opaque tokens.

A token with a valid signature can still be invalid for an API if its issuer or audience is wrong. Write dedicated resource server tests validating tokens under the exact configuration the API uses, rather than merely decoding the JWT and inspecting JSON strings.

### ID Tokens per OIDC

ID Tokens must be validated per OIDC Core. Depending on flow and requirements, verify:

- iss equals the Provider's issuer.
- sub is a valid subject identifier and is not arbitrarily mutated.
- aud contains the RP's client ID; enforce azp when applicable.
- exp and iat are valid.
- nonce matches the nonce from the authentication request if one was sent.
- Signature and algorithm belong to the set trusted by the client.
- auth_time, acr, amr, or other claims match when requested by the client and supported by the Provider.

For the UserInfo endpoint, verify the access token carries appropriate permissions and that sub in UserInfo matches sub in the ID Token from the same authentication session. Never return claims exceeding granted scopes or consent policy. If the endpoint is not enabled, state this explicitly in the conformance scope.

### JWKS and key lifecycle

The JWKS is a client dependency during token verification. Test:

1. jwks_uri in discovery points to the public endpoint.
2. The public key matching the active signing key appears in the JWKS.
3. kid in the JWT header selects the right key.
4. Key rotation publishes the new key before tokens signed with it need verification.
5. Old keys stay published long enough to verify valid unexpired tokens signed with them.
6. Revoked or trust-expired keys cease being accepted per policy.
7. Clients handle an unknown kid by refreshing JWKS reasonably and rejecting the token if verification still fails.

Rotation tests should use two test key sets. Issue tokens with key A while publishing A; then switch to key B while publishing both A and B during the overlap window. Confirm both A and B tokens verify as expected. After A tokens expire and the retention window ends, test the A removal policy.

Never use a production private key in the test suite. Generate dedicated test keys or use securely managed key fixtures.

## 6. Testing refresh tokens, consent, revocation, and introspection

### Refresh tokens

Refresh tokens generally outlive access tokens and can mint new access tokens. Test:

- Only permitted clients receive refresh tokens.
- Refresh tokens remain bound to the right client and authorization.
- New scopes do not exceed originally granted permissions.
- Expired or revoked tokens are rejected.
- Rotation policy executes properly if enabled.
- Old tokens are invalidated upon successful rotation.
- Replay of old refresh tokens is detected and handled per policy.
- Logout, consent revocation, or authorization revocation takes effect as designed.

Do not assume every configuration rotates refresh tokens automatically. Document the active policy—such as token reuse vs. rotation, lifetimes, and replay behavior. Tests must match the implemented policy.

### Consent

Create scenarios for:

- User approves a subset of scopes if UI and policy permit.
- User denies consent.
- User previously consented and requests the same scopes again.
- Request adds new scopes requiring supplemental consent.
- Client is revoked or consent is deleted.
- Two concurrent sessions modify consent.

Verify access tokens and ID Tokens reflect the actual granted permissions. A client must never receive elevated scopes simply because it sent them in the authorization request.

### Revocation and introspection

If the revocation endpoint is enabled, test valid tokens, nonexistent tokens, already-revoked tokens, unauthorized revoking clients, and failed client authentication. RFC 7009 states revocation responses should not reveal whether a token exists; tests must verify no sensitive data leaks through response differences beyond what the specification allows.

If the introspection endpoint is enabled, test clients permitted to introspect, active/inactive tokens, and returned metadata. After revocation, introspection and resource servers must reflect the updated status within defined cache bounds. If resource servers cache introspection responses, test revocation lag and set TTLs according to risk tolerances.

## 7. Testing OIDC Discovery and authentication behavior

When OIDC is enabled, the discovery endpoint serves as the contract Relying Parties use to locate Provider configuration. It typically lives at:

~~~text
https://auth.example.test/.well-known/openid-configuration
~~~

Verify:

- issuer matches the configured issuer and ID Token iss claim verbatim.
- authorization_endpoint, token_endpoint, jwks_uri, and userinfo_endpoint (if supported) are valid public URLs.
- response_types_supported, grant_types_supported, subject_types_supported, and id_token_signing_alg_values_supported accurately reflect actual capabilities.
- Published token endpoint authentication methods are implemented and functional.
- Unsupported scopes, claims, endpoints, or features are not advertised as enabled.
- OAuth metadata under RFC 8414 and OIDC Discovery agree on issuer and corresponding endpoints.

Do not hardcode a single metadata list from test expectations if configurations intentionally vary across profiles. Instead, define contracts per deployment profile and compare responses against the reviewed contract.

### Advanced authentication request parameters

If the Provider supports OIDC parameters, test policy behavior:

- prompt=none when the user is unauthenticated or interactive consent is needed must return an appropriate OIDC error such as login_required or consent_required.
- max_age requires recent authentication and auth_time reflects authentication time.
- prompt=login forces re-authentication per configured behavior.
- nonce is embedded in the ID Token and verified by the RP.
- acr_values are satisfied only when the corresponding authentication level actually occurred.
- login_hint or domain_hint is never treated as proof of authentication.
- Unsupported parameters are handled per specification rather than silently lowering protections.

If RP-Initiated Logout is enabled, validate post_logout_redirect_uri against the registered URI list, preserve state, terminate the Provider session per policy, and confirm callbacks do not create open redirects. Logging out of an SSO session does not automatically mean every access token has been revoked; test token and session behavior independently.

## 8. Testing security boundaries around endpoints

Conformance goes beyond token JSON payloads. Web and infrastructure layers can alter protocol outcomes.

### Sessions, CSRF, and CORS

- Verify session cookies set Secure, HttpOnly, and SameSite appropriately for browser flows.
- Verify session IDs rotate after login if session fixation protection is in use.
- Verify state-changing requests and consent have proper CSRF protection.
- CORS permits only required origins, methods, and headers; never reflect arbitrary origins with credentials.
- Never use CORS as client authentication or a substitute for redirect URI validation.
- Test logout and consent when cookies expire or sessions are revoked.

### Reverse proxies and public URLs

Run tests through the external domain, not solely by calling the servlet container directly. Verify issuer, redirects, discovery, JWKS, callbacks, and cookies all use the proper public scheme/host/path.

Send forged client headers such as Forwarded, X-Forwarded-Host, and X-Forwarded-Proto. Edge proxies must strip or overwrite them. Backends must be restricted so only authorized proxies can reach them. A MockMvc test does not prove firewalls, ingresses, or TLS termination are configured right; separate deployment tests are required.

### Error handling and rate limiting

OAuth/OIDC error responses must be properly structured without exposing stack traces, SQL, secrets, tokens, or user data. Test error categories such as invalid_request, invalid_client, invalid_grant, unauthorized_client, unsupported_grant_type, and invalid_scope at the appropriate endpoints.

Test rate limits for login, token, introspection, and sensitive endpoints per your threat model. Confirm the system does not lock accounts or clients in ways that let attackers easily cause denial of service. Logs need sufficient correlation IDs and audit events for investigation without recording replayable credentials.

## 9. Organizing tests in Spring and CI

Structure test suites in layers to get fast feedback while still verifying real behavior.

| Layer | Tools/execution | Objective |
|---|---|---|
| Unit | JUnit, AssertJ, Mockito | Token customizers, validators, scope mappings, consent policies, and internal rules |
| Spring integration | SpringBootTest, AutoConfigureMockMvc, MockMvc | Security filter chains, endpoints, persistence adapters, and error responses |
| HTTP end-to-end | Test client via deployed URL | Cookies, redirects, TLS, proxies, sessions, and multiple instances |
| Protocol conformance | OpenID Foundation conformance suite and appropriate protocol test suites | Interoperability with independent clients/RPs per profile |
| Regression deployment | Staging pipeline | Compare metadata, JWKS, tokens, revocation, and behavior across releases |

### Example token endpoint error test

The following example illustrates an integration test sending an invalid authorization code. The fixture requires registering client_secret_basic, standard token endpoints, and Spring Security test support:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointRegressionTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsUnknownAuthorizationCode() throws Exception {
        mockMvc.perform(post("/oauth2/token")
                .with(httpBasic("web-confidential-test", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "authorization_code")
                .param("code", "unknown-code")
                .param("redirect_uri",
                        "https://client.example.test/callback"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist())
            .andExpect(jsonPath("$.refresh_token").doesNotExist());
    }
}
~~~

Common imports include SecurityMockMvcRequestPostProcessors.httpBasic, MockMvc, MediaType, and MockMvc static matchers. Tests must run with a client fixture using the proper authentication method; if the fixture uses private_key_jwt or mTLS, swap the request authentication accordingly.

The test above verifies only one error case at the token endpoint. It does not replace a full Authorization Code Flow, nor does it verify PKCE when the code does not exist. Add tests that create a real authorization code, redeem it with the right verifier, then replay the code and test wrong verifiers.

### Full integration test flow

An end-to-end scenario can be structured as follows:

~~~text
Create client fixture and test user
             |
             v
Send authorization request with PKCE S256
             |
             v
Log in and handle consent
             |
             v
Receive callback: code + state
             |
             v
Client verifies state
             |
             v
Exchange code + code_verifier
             |
             v
Verify access token and ID Token
             |
             v
Call UserInfo / Resource Server
             |
             v
Refresh token, revocation, and logout
             |
             v
Verify audit events and persistence state
~~~

Tests should preserve cookies/sessions across requests like a real browser. If using MockMvc, configure session and cookie handling in the test client; when testing across multiple instances, use a real HTTP client to route requests across nodes. Never simulate login outcomes by bypassing the security filter chain entirely when the goal is protocol testing.

### Using external conformance suites

The OpenID Foundation provides conformance test suites for OpenID Connect and related profiles. You can run test plans matching Spring Authorization Server's OP (OpenID Provider) role. Select the exact profile, response type, client authentication method, and enabled features.

Recommended workflow:

1. Deploy an isolated test environment with an HTTPS URL reachable by the test suite.
2. Configure test clients and users, dedicated redirect URIs, test keys, and mock data.
3. Select the test plan matching the published profile.
4. Run all mandatory tests, archiving test IDs, outcomes, credential-scrubbed requests/responses, and deployment versions.
5. Analyze failures against the specification to distinguish configuration issues, application bugs, or test harness limitations.
6. Fix issues, re-run failing tests, and re-run the entire mandatory suite before declaring compliance.

Never run a conformance suite against production if the test plan creates users, authorizations, tokens, consents, or stateful records. Never supply production accounts, private keys, or real secrets to the test harness. If compatibility with a specific RP must be proven, run additional interoperability tests with that RP; a conformance suite alone does not guarantee every real-world integration works.

## 10. Building regression gates after security changes

Not every change requires re-running the identical test set, but changes affecting protocol handling or trust boundaries must trigger corresponding tests.

| Change | Minimum regression |
|---|---|
| Spring Authorization Server/Spring Security upgrade | Authorization, token, PKCE, client auth, OIDC discovery, error responses |
| Editing RegisteredClient or client data | Grants, scopes, redirect URIs, authentication methods, and consent |
| Editing token customizers/claims | Access tokens, ID Tokens, issuer, audience, scopes, and resource server validation |
| Changing issuer/domain/context path | Discovery, metadata, redirects, JWKS, ID Token iss, proxy |
| Rotating signing keys or algorithms | JWT signatures, kid, JWKS rotation, old tokens and new tokens |
| Changing persistence/schema | Single-use codes, refresh, revocation, consent, and multi-instance behavior |
| Changing session/CSRF/CORS | Login, consent, callbacks, cookies, logout, and browser flows |
| Changing reverse proxy/ingress/TLS | Forwarded header spoofing, HTTPS, redirects, cookies, discovery |
| Changing rate limits/logging | Error responses, abuse prevention, audits, and zero credential leaks |

A pipeline can enforce four gates:

- **Pull request:** unit tests and fast integration tests for modified modules; run negative tests for redirects, PKCE, and client auth when related code changes.
- **Build candidate:** run the full OAuth/OIDC regression suite, migration tests, and token/JWKS verification.
- **Staging:** run end-to-end tests through proxies, multi-instance tests, mandatory conformance suites, and interoperability scenarios.
- **Release gate:** block release if critical unresolved defects, metadata inconsistencies, broken token validation, or missing mandatory test results exist.

If a test is waived, document the justification, internal approver, impact scope, and review expiration date. Never mark failing tests as skipped merely to turn a pipeline green.

### Defining clear pass/fail criteria

A release candidate passes only when:

1. All mandatory tests for the supported profile pass.
2. No authorization code or refresh token replay is accepted outside policy.
3. Redirect URIs, issuer, audience, PKCE, and token signatures validate properly.
4. Metadata, JWKS, and public endpoints are consistent.
5. Revocation and consent take effect within defined SLAs/policies.
6. Proxy and multi-instance tests pass.
7. Zero credentials or sensitive data appear in logs, error responses, or artifacts.
8. Known failures have documented risk assessments and disposition decisions.

Never use an aggregate pass percentage to mask failures in critical security tests. For instance, a 99% pass rate is still a failed release if a test verifying redirect URIs or PKCE is bypassed.

## 11. Managing evidence and diagnosing failures

Each run should archive enough evidence to reproduce results:

- Commit SHA, application version, Spring Authorization Server, and Spring Security versions.
- OAuth/OIDC profile, endpoint configuration, and test plan version.
- List of test IDs, outcomes, timestamps, and environment details.
- Scrubbed metadata, public JWKS, and key fingerprints.
- Requests/responses scrubbed of tokens, codes, cookies, secrets, and personal data.
- Related correlation IDs or audit events.
- Failure summary, root cause, waiver decisions, and issue links.

When a test fails, investigate in order:

1. Confirm the test plan and profile match actually enabled features.
2. Verify the request uses the right client, redirect URI, scopes, and authentication method.
3. Check the issuer, endpoints, and JWKS actually called by the test harness.
4. Inspect RegisteredClient, AuthorizationServerSettings, token customizers, and security filter chain configurations.
5. Inspect persistence, sessions, and cross-instance consistency.
6. Inspect proxies, TLS, forwarded headers, clocks, and caches.
7. Reproduce the defect with a minimal test in an isolated environment, then add a regression test for the root cause.

Never print raw authorization codes, access tokens, refresh tokens, ID Tokens, cookies, or client secrets into CI logs. When analyzing a JWT, use test tokens and scrub sensitive payloads before attaching artifacts.

## 12. Pre-release checklist

- [ ] OAuth/OIDC scope and specification versions are explicitly documented.
- [ ] Every supported grant type and client authentication method has positive and negative tests.
- [ ] Redirect URIs are validated verbatim; no open redirects exist.
- [ ] Authorization Code Flow requires PKCE per policy; S256 is tested.
- [ ] Expired, reused, or wrong-verifier authorization codes are rejected.
- [ ] Client authentication, scopes, consent, and grant types match configuration.
- [ ] Access tokens validate issuer, audience, expiry, signature, and scopes.
- [ ] ID Tokens validate issuer, audience, nonce, lifetime, and signature.
- [ ] JWKS and key rotation preserve verification for unexpired tokens.
- [ ] Refresh, revocation, and introspection follow policy.
- [ ] Discovery metadata accurately reflects enabled endpoints and features.
- [ ] UserInfo, logout, and advanced OIDC parameters are tested if supported.
- [ ] Cookies, sessions, CSRF, CORS, TLS, and reverse proxies are tested along real access paths.
- [ ] Mandatory conformance tests and regression gates pass.
- [ ] Evidence is stored securely without containing replayable credentials or tokens.

Conformance assessment for Spring Authorization Server is a continuous practice. Any change to clients, tokens, issuers, signing keys, persistence, sessions, or proxies can alter protocol behavior. When test matrices align with published profiles, negative tests cover security boundaries, and regression gates run before release, operations teams catch OAuth/OIDC drift early and preserve Authorization Server compatibility across releases.
