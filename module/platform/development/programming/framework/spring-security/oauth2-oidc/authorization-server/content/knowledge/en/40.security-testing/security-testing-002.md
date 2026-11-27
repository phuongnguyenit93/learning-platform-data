# Testing missing PKCE, invalid verifier, downgrade, and code replay

PKCE (Proof Key for Code Exchange) adds a client-generated random secret to the authorization code flow. The client sends a hash of the secret in the authorization request, then sends the original secret when exchanging the authorization code for a token. The Authorization Server issues tokens only if the two values match. This mechanism reduces the risk of an attacker intercepting an authorization code and exchanging it for tokens themselves.

Even a configuration with PKCE enabled still needs to be tested with failure cases. It must be proven that the server rejects authorization requests missing a challenge, rejects invalid verifiers, enforces algorithm anti-downgrade policies, and allows an authorization code to be used only once. Tests must run against real Spring Authorization Server endpoints so they cover filters, client authentication, authorization persistence, and error handling.

## 1. Security invariants to test

For the authorization code flow, every code issuance must satisfy the following conditions:

1. A client in the PKCE-required group must send code_challenge in the authorization request.
2. The server only accepts code_challenge_method values within the published policy. For new systems, S256 should be required and plain rejected.
3. The token request must include a valid code_verifier, and this value must produce the exact challenge bound to the authorization code.
4. The authorization code must still be valid, unused, belong to the right client, and match the original redirect_uri.
5. Only one code exchange is allowed to succeed, even when two requests redeeming the same code arrive nearly simultaneously.

These conditions are related but verify different flaws. For example, testing requireProofKey only proves that the client must use PKCE; it does not automatically prove that the server allows only the S256 algorithm. Likewise, testing a valid verifier does not prove that the code is consumed safely against concurrent replay requests.

## 2. Understanding challenge and verifier properly

The client generates a random code_verifier string between 43 and 128 characters long using unreserved characters per RFC 3986: letters, digits, hyphen, period, underscore, and tilde. The client generates the challenge using one of two methods:

| Method | Formula | Recommended policy |
|---|---|---|
| S256 | BASE64URL-NOPAD(SHA256(ASCII(code_verifier))) | Accept |
| plain | code_challenge = code_verifier | Reject under an S256-only policy |

With S256, the server stores the challenge and method alongside the authorization code. When the token request arrives, the server recomputes the challenge from the received verifier and compares it with the stored challenge. The comparison must be performed using credential-safe logic; do not log verifiers or challenges if they could be used to replay test flows or expose client details.

RFC 7636 provides a useful test vector to verify the challenge computation function:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Corresponding Java function:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

static String s256Challenge(String verifier) {
    try {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
    } catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException("SHA-256 is unavailable", ex);
    }
}
~~~

Include a dedicated unit test confirming that the function above produces the exact challenge from the test vector. This unit test catches wrong charsets, using standard Base64 instead of URL-safe Base64, keeping padding, or hashing the wrong data. It does not yet replace integration tests with the Authorization Server.

~~~java
assertThat(s256Challenge(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"))
        .isEqualTo("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
~~~

## 3. Configuring a test client in Spring Authorization Server

Create a dedicated client for authorization code tests and enable the PKCE requirement in ClientSettings:

~~~java
RegisteredClient pkceClient = RegisteredClient.withId("pkce-client-row")
        .clientId("pkce-client")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://client.example/callback")
        .scope("profile.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();

registeredClientRepository.save(pkceClient);
~~~

This client uses client_secret_basic so the tests stay focused on PKCE. When testing a public client, register a separate client with authentication method none and configure no secret. Do not mix client authentication errors with PKCE errors: before evaluating PKCE outcomes, ensure the request authenticates the client successfully for the appropriate client type.

requireProofKey(true) indicates that the client is required to use PKCE. A policy must be added at the authorization request validation step to accept only S256 if that is a system requirement. Do not assume that enabling requireProofKey means every version of Spring Authorization Server automatically rejects plain. Check the behavior of the version in use and test it over HTTP.

The algorithm check in a custom validator can be expressed as follows:

~~~java
// Pseudocode: place in the validator handling the authorization request
// after determining this client belongs to the PKCE-required group.
if (!"S256".equals(codeChallengeMethod)) {
    rejectAuthorizationRequest("invalid_request");
}
~~~

This is policy logic, not the name of a specific Spring API. Attach the logic to the validator extension point supported by your project's Spring Authorization Server version. If code_challenge_method is omitted, RFC 7636 defaults the method to plain; therefore, an S256-only policy must also reject requests that omit the method.

## 4. Setting up integration tests against real endpoints

Use MockMvc with the application's filter chain, client repository, and authorization service matching the integration configuration. Each test should generate a fresh authorization code so results do not depend on previous tests. The authorizeAndExtractCode helper in the examples represents sending an authorization request with an authenticated user, completing consent if the application requires it, and extracting the code from the redirect URI. This keeps the tests below focused on PKCE behavior.

Example code-redemption helper:

~~~java
private ResultActions redeemCode(String code, String verifier) throws Exception {
    MockHttpServletRequestBuilder request = post("/oauth2/token")
            .with(httpBasic("pkce-client", "test-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "authorization_code")
            .param("code", code)
            .param("redirect_uri", "https://client.example/callback");

    if (verifier != null) {
        request.param("code_verifier", verifier);
    }

    return mockMvc.perform(request);
}
~~~

Common imports include MockMvc, MockHttpServletRequestBuilder, MediaType, get, post, httpBasic, user, status, and jsonPath from Spring Test/Spring Security Test. The test configuration must load the Authorization Server filter chain and authenticate the user. If the application requires consent, prepare consent in a fixture or complete the consent screen inside the helper.

## 5. Testing missing challenge and unsupported method

For a client with requireProofKey(true), send an authorization request without code_challenge. The server must reject the request and not issue an authorization code:

~~~java
@Test
void rejectsAuthorizationRequestWithoutChallenge() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .with(user("alice"))
                    .param("response_type", "code")
                    .param("client_id", "pkce-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "profile.read")
                    .param("state", "state-missing-challenge"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern(
                    "https://client.example/callback?error=invalid_request*"));
}
~~~

The authorization endpoint typically returns OAuth errors by redirecting to the registered URI, so do not assume every error at this endpoint returns HTTP 400. Verify error=invalid_request, ensure no code is in the redirect, and confirm the authorization service does not save a valid authorization code for the rejected request.

Next, send an unsupported code_challenge_method, such as S512, along with a syntactically valid challenge. The server must reject the authorization request with invalid_request. This test ensures the server does not silently interpret an unknown algorithm as plain or another method.

## 6. Testing missing, wrong, and malformed verifier

First, generate a valid code with an S256 challenge from a known verifier:

~~~java
String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String challenge = s256Challenge(verifier);
String code = authorizeAndExtractCode(
        "pkce-client", challenge, "S256");
~~~

With valid client authentication and an active authorization code, omit code_verifier from the token request. The server must reject the code exchange and return invalid_grant according to the token endpoint's error handling:

~~~java
redeemCode(code, null)
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"));
~~~

Generate a new authorization code for the wrong-verifier test. Do not reuse the code used in the missing-verifier test:

~~~java
String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String code = authorizeAndExtractCode(
        "pkce-client", s256Challenge(verifier), "S256");

redeemCode(code, "wrong-verifier-value-0123456789-ABCDEFGHIJKLM")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error").value("invalid_grant"))
        .andExpect(jsonPath("$.access_token").doesNotExist());
~~~

In addition to a mismatched verifier, test strings shorter than 43 characters, longer than 128 characters, and containing characters outside the allowed set. The server must not issue tokens from a malformed verifier. Standardize the outcome into an OAuth error appropriate for the server version; for an authorization code that cannot be verified, the expected result is invalid_grant. Do not allow internal exceptions or stack traces to appear in the response.

A failed verifier attempt must not produce an access token, refresh token, or ID token. Inspect both the response and the persisted authorization state. If the system adopts a policy of revoking the code immediately upon a failed PKCE verification, test that policy explicitly; do not assume this behavior if the application has not specified it.

## 7. Testing downgrade from S256 to plain

A downgrade occurs when a request can be altered to use a weaker method. With plain, the challenge is the verifier itself, so the protected secret is no longer hashed before traversing the authorization request. For clients requiring PKCE, a system enforcing an S256-only policy should reject both forms:

- code_challenge_method=plain.
- Omitting code_challenge_method, because RFC 7636 defaults that case to plain.

Example test:

~~~java
@Test
void rejectsPlainChallengeMethod() throws Exception {
    mockMvc.perform(get("/oauth2/authorize")
                    .with(user("alice"))
                    .param("response_type", "code")
                    .param("client_id", "pkce-client")
                    .param("redirect_uri", "https://client.example/callback")
                    .param("scope", "profile.read")
                    .param("state", "state-plain")
                    .param("code_challenge", "plain-verifier-value-0123456789-ABCDEFGHIJKLM")
                    .param("code_challenge_method", "plain"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern(
                    "https://client.example/callback?error=invalid_request*"));
}
~~~

Add another test that omits code_challenge_method entirely while still sending code_challenge; the result must also be invalid_request under an S256-only policy. Do not check only whether the client sends S256 on the happy path. You must prove the server rejects downgrades server-side, even when a client sends a non-compliant request.

If the product has legacy clients that require plain, define per-client exceptions with an owner and deprecation deadline. Do not automatically allow plain for all clients merely for compatibility. Document this policy in client configuration and write separate tests for each group.

## 8. Testing authorization code replay

An authorization code is a single-use credential. After a code has been exchanged successfully, resending the same code with the valid verifier must fail. Do not issue new tokens, create a new refresh token, or return the previous token response:

~~~java
@Test
void rejectsAuthorizationCodeReplay() throws Exception {
    String verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
    String code = authorizeAndExtractCode(
            "pkce-client", s256Challenge(verifier), "S256");

    redeemCode(code, verifier)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").exists());

    redeemCode(code, verifier)
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

The test above checks sequential replay. It does not detect race conditions where two requests both read the code state as valid before one request persists the consumed state. Therefore, if the authorization service uses JDBC or a custom store, write a concurrent integration test with two token requests arriving from two independent threads or HTTP clients:

1. Generate a valid authorization code and use only one valid verifier.
2. Synchronize two requests so they submit the same code nearly simultaneously.
3. Wait for both responses to complete.
4. Confirm that exactly one response succeeds and the other receives invalid_grant.
5. Confirm that only one token issuance is recorded in persisted state.

To achieve this condition, consuming the authorization code must be atomic in the store. It may require a transaction with row locking, optimistic versioning, or a conditional update that succeeds only while the code remains unconsumed. Relying solely on an in-memory status check followed by a later save can let concurrent requests slip through. Test the actual behavior of the implementation in use, especially when running multiple Authorization Server instances.

## 9. Test matrix and expected outcomes

| Case | Checkpoint | Expected outcome |
|---|---|---|
| Missing code_challenge for PKCE-required client | Authorization endpoint | invalid_request, no code issued |
| Unsupported method | Authorization endpoint | invalid_request, no fallback |
| plain under S256-only policy | Authorization endpoint | invalid_request |
| Omitted code_challenge_method under S256-only policy | Authorization endpoint | invalid_request |
| Missing code_verifier | Token endpoint | invalid_grant, no token issued |
| Verifier does not match challenge | Token endpoint | invalid_grant, no token issued |
| Verifier with invalid length or characters | Token endpoint | Request rejected, no token issued |
| Reusing code a second time | Token endpoint | invalid_grant, no new token issued |
| Two requests exchanging same code concurrently | Token endpoint and authorization store | Exactly one request succeeds |

In all token endpoint tests, authenticate the client successfully first so invalid_client does not mask PKCE errors. For authorization endpoint errors, verify the registered redirect URI and OAuth error parameters; for token endpoint errors, check HTTP status, JSON error code, and token state.

## 10. Keeping tests independent and avoiding false positives

Each scenario must use its own authorization code, state, and verifier. Do not reuse a code that was already exchanged successfully for a wrong-verifier or missing-verifier test. Do not assert only the status code: check the error code, absence of tokens in the response, and authorization state after the request.

Tests should run against the same type of authorization service that production uses. If production stores authorizations in JDBC, H2 or in-memory tests can miss transaction and concurrency issues. For concurrent replay tests, use a production-compatible database and execute transactions on independent threads. Running tests on a single instance verifies basic logic; running across multiple instances or workers uncovers bugs when code state is shared.

Use mock client secrets, verifiers, and authorization codes. Never write these values into test reports, CI logs, or assertion messages. When a test fails, print only the request ID, test case name, endpoint, status, and normalized error code.

## 11. Pre-release checklist

- [ ] Every client under the PKCE-required policy rejects authorization requests missing a challenge.
- [ ] The S256 test vector accurately confirms SHA-256 and unpadded URL-safe Base64.
- [ ] The server accepts only S256 for clients under the S256-only policy.
- [ ] Both plain and omitted method cases are rejected according to policy.
- [ ] Missing, wrong, too-short, too-long, or invalid-character verifiers cannot exchange the code for tokens.
- [ ] A used authorization code cannot be exchanged again.
- [ ] Concurrency tests prove only one request can consume the same authorization code.
- [ ] Tests run with the authorization service and storage matching production.
- [ ] Error responses do not contain access tokens, refresh tokens, ID tokens, or internal details.

When these tests run reliably in CI, the development team can detect relaxed PKCE settings, algorithm downgrades, or authorization code reuse early before changes reach production.
