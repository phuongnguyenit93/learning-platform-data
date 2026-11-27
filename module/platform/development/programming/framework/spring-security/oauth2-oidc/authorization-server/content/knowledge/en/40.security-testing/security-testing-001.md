# Negative testing with invalid redirect URI, scope, issuer, and audience

A secure Authorization Server must reject authorization requests and tokens that do not meet policy, while avoiding redirecting or issuing tokens to untrusted destinations. Bugs such as incorrect redirect URIs, excessive scopes, invalid issuers, or audiences not intended for the target API often surface only when testing negative inputs.

With Spring Authorization Server, it is necessary to verify both where errors originate and where tokens are consumed. Redirect URI and scope are validated during authorization/client processing; issuer and audience must also be verified on the client or Resource Server side. A token with a valid signature can still be untrusted if its issuer or audience is wrong.

## 1. Principles for designing negative tests

A good negative test must prove three things:

1. The input violates a specific security rule.
2. The responsible component rejects that exact input.
3. There are no dangerous side effects, such as redirecting to an unknown host, granting excessive scopes, or accepting tokens from another issuer/resource.

Dedicated test data should be created, including at least one valid client, one client with restricted scopes, one registered redirect URI, and one expected issuer/resource server. Each test should change only one factor so you know precisely which rule is being tested.

| Test category | Primary responsible component | Outcome to prove |
|---|---|---|
| Redirect URI | Authorization Server and RegisteredClient | Only registered URIs can be used as destinations for authorization responses |
| Scope | Authorization Server, consent, and token policy | The client cannot request or receive permissions beyond its allowed scope |
| Issuer | OIDC/OAuth2 client and Resource Server | Tokens/metadata must come from a trusted Authorization Server |
| Audience | Resource Server or OIDC client | Tokens are accepted only for the intended target API/client |

Do not treat HTTP status as the sole piece of evidence. A rejected request may return HTTP 400, 401, or 403 depending on the endpoint and security configuration. Also verify the OAuth error code, Location header, token claims, authorization state, and that no token/credential was issued.

## 2. Preparing fixtures for testing

Use a test RegisteredClient with clear, fixed values. For example:

~~~java
RegisteredClient webClient = RegisteredClient.withId("web-client-id")
        .clientId("web-client")
        .clientSecret("{noop}test-secret")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.test/callback")
        .scope(OidcScopes.OPENID)
        .scope("profile")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

This is an illustrative fixture for tests. In a real project, use a configured PasswordEncoder and secret for testing; do not use {noop} in deployment environments. You can create additional clients with distinct redirect URIs or fewer scopes to test boundaries between clients.

Prepare test values:

| Value | Example | Role |
|---|---|---|
| Trusted issuer | https://auth.example.test | Issuer expected by the client/resource server |
| Registered redirect URI | https://app.example.test/callback | Valid destination for authorization responses |
| Invalid redirect URI | https://attacker.example/callback | Input that must be rejected |
| Allowed scopes | openid profile orders.read | Permissions registered for the client |
| Excessive scope | admin.write | Permission not granted to the client |
| API audience | https://api.example.test | Resource server allowed to receive the access token |
| Wrong audience | https://other-api.example.test | Different resource server |

Keep private keys, client secrets, and test tokens in secure fixtures. Never hardcode production credentials in test source code. If you need to generate a JWT with an invalid claim, sign the token with a test key trusted by the Resource Server to test issuer/audience in isolation; if the signature is also invalid, the test will fail for a different reason and will not prove that the validator under test works.

## 3. Negative testing with redirect URI

The redirect URI specifies where the Authorization Server sends the authorization response containing the authorization code or error. If the server accepts a URI controlled by an attacker, the code can be sent to an unintended system. Therefore, the server must validate the URI against the list registered for that specific client before redirecting.

With RegisteredClient, Spring Authorization Server validates the redirect URI against registered values. In tests, try modifying individual components separately: scheme, host, port, path, query, and fragment. Do not use string checks like startsWith in a custom validator as a substitute for exact URI matching.

### 3.1 Cases to test

| Input | Why it is invalid | Expected outcome |
|---|---|---|
| https://attacker.example/callback | Unregistered host | Reject; do not redirect to attacker |
| http://app.example.test/callback | Different scheme from registered URI | Reject for HTTPS web client |
| https://app.example.test:8443/callback | Different port | Reject if this port is not registered |
| https://app.example.test/other | Different path | Reject |
| https://app.example.test/callback/ | Path with a different trailing slash | Reject if not registered verbatim |
| https://app.example.test.evil.test/callback | Lookalike host | Reject |
| https://app.example.test@attacker.example/callback | User-info makes the actual host attacker | Reject |
| URI containing fragment | Fragment is incompatible with OAuth2 redirect URIs | Reject |
| URI missing or altered compared to initial request at token endpoint | Mismatched authorization request | Token exchange fails |

For native apps, loopback redirect URIs may follow dynamic port rules per OAuth guidelines for native applications. Do not mechanically apply HTTPS web fixtures to loopback cases; test according to the exact rules and support behavior of the client version/component being implemented.

### 3.2 Verifying the Authorization Server does not redirect to an unknown URI

Example negative request to the authorization endpoint:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fattacker.example%2Fcallback
    &scope=openid
~~~

A MockMvc test can verify that the unknown URI does not appear in the Location header:

~~~java
mockMvc.perform(get("/oauth2/authorize")
        .param("response_type", "code")
        .param("client_id", "web-client")
        .param("redirect_uri", "https://attacker.example/callback")
        .param("scope", "openid"))
    .andExpect(status().isBadRequest())
    .andExpect(header().doesNotExist("Location"));
~~~

Endpoint paths and error rendering can be customized in the application. The critical security condition is that the response must not redirect to an unverified URI. If the application configuration returns a custom error page, adjust the status/body assertions accordingly, while still verifying there is no redirect to an unknown host.

Do not expect the server to redirect back to a registered URI when the redirect URI itself in the request is invalid. By OAuth rules, if the URI is unverified, the Authorization Server cannot safely send an error response to that URI.

### 3.3 Valid redirect URI but invalid scope

This is a different scenario: the redirect URI has been verified, but another authorization parameter is invalid. In that case, the Authorization Server may send an OAuth error response to the valid redirect URI according to protocol rules.

For example:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback
    &scope=openid%20admin.write
~~~

The test must verify that the error is invalid_scope (or the error code per the implemented extension/policy), and if the response is redirected, Location must point to the exact registered URI. There must be no authorization code in the response.

### 3.4 Validating redirect_uri at the token endpoint

After obtaining an authorization code, the client sends a token request including redirect_uri. This value must match the URI from the initial authorization request when the parameter is used in the authorization code flow.

Negative tests should:

1. Generate an authorization code using a valid redirect URI.
2. Send a token request with a different redirect URI, even if the alternative URI is also in the client's registered URI list.
3. Verify that the token endpoint rejects the exchange per authorization code rules.
4. Verify that no access token or refresh token is issued from the invalid request.

The fact that another URI is also registered for the same client does not make it the URI used in that specific authorization request.

## 4. Negative testing with scope

Scope represents the permissions requested by the client. The Authorization Server needs to restrict scopes according to RegisteredClient, require user consent when policy demands it, and never issue tokens with permissions exceeding the granted authorization.

Three layers should be distinguished:

- **Requested scope**: scopes sent by the client in the authorization request or token request.
- **Authorized scope**: scopes actually approved by the Authorization Server and stored in the authorization.
- **Effective authority**: permissions the Resource Server derives from the access token and API policy.

These three sets are related but not necessarily identical. For instance, if the client requests openid profile orders.read and the user approves a smaller subset per policy, the access token must not implicitly include scopes outside the granted set.

### 4.1 Scope not registered for the client

Register the client for openid, profile, and orders.read only, then attempt to request admin.write. Verify that the Authorization Server rejects the request with invalid_scope or the corresponding endpoint error. No authorization code containing the excessive scope may be created.

For example:

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback
    &scope=openid%20admin.write
~~~

Also test cases where a valid scope is misspelled, has improper whitespace/encoding, or is sent repeatedly in a way the application does not support. Do not automatically correct similar-looking scope names; orders.read and order.read are two different values.

### 4.2 Scope escalation at the token endpoint

In the authorization code flow, the token endpoint must not grant permissions beyond the authorization already granted for the code. Generate a code with scope openid profile, then attempt to request an additional admin.write when exchanging the code if the endpoint/flow accepts the scope parameter.

With a refresh token, if the client requests new scopes, the scope set must not exceed the permissions granted in the original authorization. Verify behavior according to the exact grant and version in use; if the scope parameter is rejected, the test should verify invalid_scope or invalid_grant per implementation semantics, and verify that no new token with elevated permissions is issued.

### 4.3 Verifying consent cannot be bypassed

A client can be configured to require consent. Tests should verify:

- On the first request for a new scope, the consent UI appears according to policy.
- After the user denies consent, the Authorization Server does not issue a successful authorization code.
- Consent for client A does not automatically become consent for client B.
- Unapproved scopes do not appear in authorized scopes.
- Revoking consent or changing permissions is reflected in the subsequent authorization request.
- The client cannot add scopes by tampering with the request after the user has given consent.

Consent is state bound to the principal and client. Do not inspect only the UI; verify consent stored via OAuth2AuthorizationConsentService and the actual authorization created via OAuth2AuthorizationService.

### 4.4 Verifying authority at the Resource Server

The Resource Server typically maps scopes to authorities such as SCOPE_orders.read. An API test should verify that a token with orders.read can call an endpoint requiring that permission, whereas a token with only profile is denied.

For example, with MockMvc and Spring Security Test, endpoint policies can be tested using a mock JWT in unit/web-layer tests; however, integration tests using tokens issued by the Authorization Server are also needed to prove that the scope claim and converter map accurately across the entire flow.

Do not rely solely on the scope string on the Authorization Server side. If the Resource Server uses a custom JwtAuthenticationConverter, test that the converter does not inadvertently grant default authorities or map another claim to administrative privileges.

## 5. Negative testing with issuer

The issuer identifies the Authorization Server that issued the token. Both the client and Resource Server must know which issuer is trusted. A token with a valid signature but an incorrect iss must still be rejected.

Example expected issuer:

~~~text
https://auth.example.test
~~~

A token may be signed with a trusted test key yet contain a different issuer:

~~~json
{
  "iss": "https://untrusted-issuer.example.test",
  "sub": "user-123",
  "aud": ["https://api.example.test"],
  "exp": 1893456000
}
~~~

To test the issuer in isolation, sign the JWT using the same test key trusted by the decoder, changing only the iss claim. If an untrusted key is used, the decoder may reject the signature before running the issuer validator; that result does not prove the issuer check works.

### 5.1 Checking issuer on the Resource Server

When configuring a Resource Server with an issuer URI, Spring Security can fetch metadata/JWKs and configure issuer validation according to the declared URI. If creating a JwtDecoder manually, ensure the issuer validator is explicitly configured.

For example:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.test";
    String jwkSetUri = "https://auth.example.test/oauth2/jwks";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

    return decoder;
}
~~~

If the decoder is configured with a standalone JWK Set URI, do not assume fetching public keys automatically validates the issuer. The JWK Set is used to verify signatures; the issuer is a claim that must be checked by a validator.

Test tokens with the following values:

- Exact matching issuer.
- Issuer with a different hostname.
- Issuer with a different scheme, such as HTTP instead of HTTPS.
- Issuer with a different path.
- Issuer with a different trailing slash if it does not match the configured identifier.
- Missing iss claim.

The expected outcome is that the decoder rejects tokens not matching the expected issuer.

### 5.2 Checking discovery metadata and issuer mismatch

OIDC discovery metadata publishes the issuer and endpoints. The client should verify that the issuer in the metadata matches the issuer the client has configured/registered as trusted. If metadata returns a different issuer, the client must not proceed to use the published endpoints/JWKS as if it were the same Authorization Server.

In multi-instance deployments, verify that all nodes return the same issuer. Reverse proxies, forwarded headers, or misconfigured base URLs can cause a node to advertise an internal hostname, HTTP scheme, or incorrect port.

If implementing issuer identification in authorization responses per RFC 9207, add tests for the iss parameter returned in the authorization response and verify the client compares it against the expected issuer. Enable this test only when the application/client actually supports that mechanism; do not assume every version of Spring Authorization Server enables the extension automatically.

## 6. Negative testing with audience

Audience indicates who or which resource the token was issued for. For access tokens, the Resource Server must verify whether the token is intended for the API it is protecting. For OpenID Connect ID Tokens, aud identifies the client receiving the ID Token; do not confuse the ID Token audience with the access token audience.

For example:

| Token | Expected audience |
|---|---|
| Access token for Orders API | https://api.example.test |
| Access token for Billing API | https://billing.example.test |
| ID Token for web client | web-client (client_id) |

A JWT whose aud contains the Billing API must not be accepted at the Orders API merely because it was signed by the same Authorization Server.

### 6.1 Audience validator for the Resource Server

By default, Spring Resource Server verifies basic JWT conditions such as signature and expiration; the application needs to add a resource-server-specific audience validator if policy requires it.

Example validator requiring the Orders API audience to be present in the claim:

~~~java
@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.example.test";
    String jwkSetUri = "https://auth.example.test/oauth2/jwks";
    String expectedAudience = "https://api.example.test";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "Required audience is missing",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator
            )
    );

    return decoder;
}
~~~

Required imports belong to the Spring Security OAuth2 Resource Server/JWT packages. This is an illustrative configuration for a single API; each resource server must use its own audience policy. If policy requires a single audience, check both the size and contents of the list rather than using only contains.

### 6.2 Negative audience cases

| aud claim | Resource Server | Result |
|---|---|---|
| Contains the exact API audience | Orders API | Accepted if other validators pass |
| Contains only another API's audience | Orders API | Rejected |
| Missing aud | Orders API | Rejected if audience is required |
| Audience is client ID instead of API | Orders API | Rejected if token must target the API |
| Multiple audiences | Orders API | Accepted or rejected per multi-audience policy |
| Audience modified after signing | Any API | Invalid signature, rejected |

To test the audience validator, sign the token with a test key trusted by the decoder and keep issuer, expiration, and subject valid; change only the audience. Verify that the decoder throws a validation error and the protected endpoint returns 401. If the token has an invalid signature, the test fails to isolate audience validation.

### 6.3 ID Token audience in OIDC

An OIDC client must verify that the ID Token's aud contains the exact client_id. When multiple audiences are present, azp (authorized party) rules per OpenID Connect Core must be applied; if azp is present, it must identify the corresponding client. An ID Token intended for client A must not be accepted by client B.

Negative tests for ID Tokens should include:

- aud does not contain client_id.
- aud contains a different client_id.
- Multiple audiences but azp is missing when policy requires it.
- azp does not match client_id.
- Invalid iss or nonce mismatch with the authorization request.
- Invalid exp, iat, or signature.

If using an OIDC client library, prefer testing with the library's validator and end-to-end tests. Do not simply decode the ID Token and read JSON claims to decide whether login succeeded.

## 7. Combined negative test matrix

Some defects are only uncovered when combining multiple parameters. Test both single invalid parameter cases and requests with multiple faults to ensure the server does not leak data or redirect unsafely.

| Test ID | Invalid input | Checkpoint | Expected outcome |
|---|---|---|---|
| REDIR-01 | Unregistered redirect URI host | Authorization endpoint | Reject, do not redirect to unknown host |
| REDIR-02 | Invalid scheme/port/path | Authorization endpoint | URI is not treated as a valid URI |
| REDIR-03 | Different redirect URI during code exchange | Token endpoint | No token issued |
| REDIR-04 | URI with user-info/lookalike host | Authorization endpoint | Reject, no open redirect |
| SCOPE-01 | Unregistered scope | Authorization endpoint | invalid_scope or corresponding policy error |
| SCOPE-02 | Escalated scope on code exchange/refresh | Token endpoint | Do not grant permissions beyond original authorization |
| SCOPE-03 | Token missing API authority | Resource Server | 403 per authorization policy |
| ISS-01 | JWT with different issuer | JWT decoder | Token rejected |
| ISS-02 | JWT missing issuer | JWT decoder | Token rejected |
| ISS-03 | Discovery issuer mismatch with configuration | OIDC client | Do not trust metadata/endpoints from mismatched issuer |
| AUD-01 | Access token intended for another API | Resource Server | 401 or invalid token error |
| AUD-02 | Access token missing required audience | Resource Server | Rejected |
| AUD-03 | ID Token missing client_id | OIDC client | Login fails |
| AUD-04 | azp does not match client_id | OIDC client | ID Token rejected |

For each test, record the request fixture, expected OAuth error or HTTP result, and assertions on post-request state. For example, after REDIR-01, verify not only the status but also that no authorization record/token was created and no Location points to the attacker.

## 8. Writing tests with MockMvc and Spring Security

MockMvc is well-suited for testing endpoints and the security filter chain within the same application context. An example test for an invalid redirect URI can be written as follows:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationNegativeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsUnregisteredRedirectUriWithoutRedirecting() throws Exception {
        mockMvc.perform(get("/oauth2/authorize")
                .param("response_type", "code")
                .param("client_id", "web-client")
                .param("redirect_uri",
                        "https://attacker.example/callback")
                .param("scope", "openid"))
            .andExpect(status().isBadRequest())
            .andExpect(header().doesNotExist("Location"));
    }
}
~~~

Endpoint paths, HTTP status codes, and error rendering can vary depending on application configuration. What must not change is never redirecting to an unverified URI. If the test requires authentication, configure the test principal using Spring Security Test or execute the login flow the way the application uses it.

For an invalid scope with a valid redirect URI, verify the OAuth error response according to the protocol. Depending on how the endpoint handles errors, the error may be redirected back to the valid URI with query error=invalid_scope or rendered as configured. Do not force every endpoint to return the exact same status code.

For issuer and audience, test the JwtDecoder directly in integration tests and add a protected endpoint test to prove requests are blocked at the Resource Server. Use tokens signed with a trusted test key where claims can be adjusted so each test checks a single validator.

## 9. Pitfalls within the negative test suite itself

Negative tests can also produce false confidence if fixtures do not isolate conditions properly:

- Token expires before testing issuer or audience; the test only proves expiration validation.
- Token signature is invalid when testing iss or aud; the test only proves signature validation.
- Client is not registered for the grant type; the scope test fails at the client authorization step.
- Both redirect URI and scope are invalid simultaneously; the server stops at redirect validation so scope is never tested.
- Test uses a mock JwtDecoder that always returns a valid token; real validators are never exercised.
- Database/cache still contains data from a previous test, causing leftover consent or authorization to affect results.
- Test only asserts HTTP 400 without checking Location, tokens, or authorization state.

Use a separate test for each rule before adding combined tests. When a test fails, read the specific error code and assertion before fixing. Never relax a validator just to make a test pass.

## 10. Security criteria and result reporting

The negative test suite passes when it proves:

1. Invalid redirect URIs do not receive authorization responses, authorization codes, or tokens.
2. Disallowed scopes cannot be requested, consented to, or issued beyond policy.
3. Tokens from untrusted issuers are rejected even if their signature is valid under the test key.
4. Access tokens with mismatched audiences are rejected by the Resource Server.
5. ID Tokens not intended for the current client are rejected by the OIDC client.
6. Errors do not leak raw tokens, authorization codes, client secrets, or authentication data.
7. Results remain consistent across repeated test runs and on near-production configurations.

Reports should state the test ID, component under test, negative input, actual result, expected result, and evidence of no side effects. Use correlation IDs, client IDs, and internal authorization IDs for traceability; never include credential values in logs or artifacts.

Negative testing for redirect URI, scope, issuer, and audience verifies the most critical trust boundaries in OAuth 2.0/OpenID Connect. When each validator is tested independently and results are confirmed on both the Authorization Server and Resource Server, development teams can catch misconfigurations leading to open redirects, privilege escalation, or accepting misdirected tokens early.
