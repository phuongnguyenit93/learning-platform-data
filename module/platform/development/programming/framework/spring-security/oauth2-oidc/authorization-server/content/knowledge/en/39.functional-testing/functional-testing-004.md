# Testing Client Credentials, Refresh Token, and token rotation

In Spring Authorization Server, Client Credentials and Refresh Token are two flows with different purposes. Client Credentials issues an access token to the authenticating machine application itself; Refresh Token allows a client to continue an authorization grant already approved by a user without requiring the user to log in and consent again every time an access token is issued. The functional test suite needs to distinguish clearly between these two flows, verifying client binding, token lifetimes, and behavior after refresh token rotation.

This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The module covers designing and operating an Authorization Server with client management, consent, token issuance, PKCE, refresh tokens, endpoint protection, key signing, and authorization data persistence. In the **Functional Testing** chapter, we focus on testing these two grant types at the token endpoint, including invalid, expired, and replayed token cases.

## 1. Distinguishing the two token lifecycles

With **Client Credentials**, a confidential client authenticates with its own credentials, typically via HTTP Basic with a client secret. The Authorization Server checks the client, grant type, and scopes, then issues an access token. No end user participates in this grant. Per OAuth 2.0, the authorization server should not issue a refresh token for Client Credentials. When the access token expires, the machine application sends another Client Credentials request with its client credentials to obtain a new access token.

With **Refresh Token**, the client has already completed a user-facing authorization flow, typically Authorization Code. The Authorization Server has stored the authorization along with a refresh token bound to the client and the approved scopes. When the access token expires, the client sends the refresh token to the token endpoint to obtain a new access token. If the client is configured for rotation, the server simultaneously issues a new refresh token and invalidates the old one.

| Aspect | Client Credentials | Refresh Token |
|---|---|---|
| Purpose | Authenticate a machine application | Continue an already-granted authorization |
| Represented identity | Client | User together with client |
| Grant type at token endpoint | **client_credentials** | **refresh_token** |
| Refresh token | OAuth 2.0 recommends not issuing one for this grant | Serves as the input credential of the grant |
| How to get a new access token | Re-send Client Credentials | Exchange a valid refresh token |
| Key conditions | Client authentication, grant, and scope | Client binding, unexpired token, active authorization, and valid scope |

Do not add the **refresh_token** grant type to a Client Credentials-only client expecting it to receive a refresh token from that grant. A single client may be registered with multiple grant types, but tests must clearly identify which flow a request is testing.

## 2. Configuring token lifetimes and rotation for tests

Token lifetimes should be kept short in the test profile so expiration milestones can be tested quickly and reproducibly. The example below creates an access token with a two-minute lifetime and a refresh token with a thirty-minute lifetime. The **reuseRefreshTokens(false)** setting instructs Spring Authorization Server to issue a new refresh token when processing the refresh grant:

~~~java
TokenSettings testTokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(2))
        .refreshTokenTimeToLive(Duration.ofMinutes(30))
        .reuseRefreshTokens(false)
        .build();
~~~

**reuseRefreshTokens(false)** configures rotation behavior. When a refresh succeeds, the response must contain a new refresh token. The client must safely replace the old token with the new one. If **reuseRefreshTokens(true)** is configured, the server may continue using the existing refresh token; in that case, tests must not expect the refresh token value to change.

Create two separate client fixtures. The first client is granted Client Credentials only. The second client uses Authorization Code and Refresh Token to test the user authorization lifecycle:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class TokenGrantTestFixtures {

    @Bean
    @Primary
    PasswordEncoder testPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Primary
    RegisteredClientRepository testRegisteredClientRepository(
            PasswordEncoder passwordEncoder) {

        TokenSettings tokenSettings = TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(2))
                .refreshTokenTimeToLive(Duration.ofMinutes(30))
                .reuseRefreshTokens(false)
                .build();

        RegisteredClient serviceClient = RegisteredClient.withId("service-client-id")
                .clientId("test-service-client")
                .clientSecret(passwordEncoder.encode("service-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("inventory.read")
                .tokenSettings(tokenSettings)
                .build();

        RegisteredClient userClient = RegisteredClient.withId("user-client-id")
                .clientId("test-user-client")
                .clientSecret(passwordEncoder.encode("user-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("http://127.0.0.1:8080/callback")
                .scope("profile")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(tokenSettings)
                .build();

        return new InMemoryRegisteredClientRepository(serviceClient, userClient);
    }

    @Bean
    @Primary
    OAuth2AuthorizationService testAuthorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }
}
~~~

The types used in the fixture belong to the packages **org.springframework.security.oauth2.server.authorization**, **org.springframework.security.oauth2.server.authorization.client**, **org.springframework.security.oauth2.server.authorization.settings**, **org.springframework.security.oauth2.core**, and **org.springframework.security.crypto**. The application configuration needs a **JWKSource** containing a test key if access tokens are issued as JWTs.

Client secrets are encoded with the **PasswordEncoder** used by client authentication. Do not write production secrets into test fixtures. In a real project, ensure production repositories are not initialized alongside in-memory repositories in the test context; use appropriate profiles or conditional configuration. For persistence tests, replace **InMemoryRegisteredClientRepository** and **InMemoryOAuth2AuthorizationService** with JDBC implementations and a dedicated test datasource.

Activate the fixtures on the test class:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TokenGrantTestFixtures.class)
class TokenGrantFunctionalTest {
    // Tests send HTTP requests to the token endpoint.
}
~~~

Keep the Authorization Server's filter chain intact in the test context. Disabling security or calling the token generator directly skips client authentication and grant processing at the token endpoint.

## 3. Testing Client Credentials

A Client Credentials request uses client authentication and specifies the grant type and scopes. The following example checks a successful response, verifies that an access token is issued, and asserts that the response contains no refresh token:

~~~java
@Autowired
MockMvc mockMvc;

@Test
void issuesAccessTokenForClientCredentials() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-service-client", "service-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "inventory.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token_type").value("Bearer"))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.expires_in").value(greaterThan(0)))
            .andExpect(jsonPath("$.refresh_token").doesNotExist())
            .andExpect(jsonPath("$.scope").value("inventory.read"));
}
~~~

**/oauth2/token** is the default endpoint. If the application's **AuthorizationServerSettings** changes the token endpoint URI, use the configured URI. Tests must also verify that client authentication fails when the secret is wrong:

~~~java
@Test
void rejectsClientCredentialsWithWrongSecret() throws Exception {
    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-service-client", "wrong-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "client_credentials")
                    .param("scope", "inventory.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"));
}
~~~

Add a test case for an unregistered scope or one not granted to the client. The token endpoint must return an appropriate OAuth error, typically **invalid_scope**, and must not create an authorization or access token with permissions exceeding the client's scopes. Do not check only the HTTP status; also check the **error** field in the response to confirm the server returns the exact protocol error.

To test lifetimes, set a short **accessTokenTimeToLive** in the test profile and verify that **expires_in** is positive and does not exceed the configured lifetime (accounting for request execution time). For JWT access tokens, decode with the test public key and verify **iat**, **exp**, **iss**, and scopes. For opaque tokens, verify the token via introspection or a resource server according to the actual configuration.

After the access token expires, the machine client calls Client Credentials again using the same authentication method. The test should verify that a new access token is issued and the old token is no longer accepted after expiration. Do not send a refresh token in this request.

## 4. Preparing an authorization with a refresh token

A refresh token is issued during an authorization flow that supports refresh tokens, typically Authorization Code. The client must be registered with both **authorization_code** and **refresh_token**; the user must complete login and consent according to configuration. If the client requires PKCE, the authorization request must use **code_challenge_method=S256**, and the token request exchanging the authorization code must send the matching **code_verifier**.

There are two testing levels to maintain:

1. **End-to-end authorization flow:** send an authorization request, authenticate the user, handle consent, exchange the authorization code, and verify the response includes a refresh token when allowed by client policy.
2. **Refresh endpoint test:** seed an authorization fixture already containing a refresh token into **OAuth2AuthorizationService**, then send refresh requests directly to the token endpoint. This isolates testing of rotation, expiration, client binding, and replay without repeating login and consent screens in every test.

The helper example below creates an authorization fixture for testing the refresh endpoint. It is solely setup data for token endpoint tests; at least one dedicated end-to-end test is still needed to prove the Authorization Code flow actually issues a refresh token:

~~~java
private String saveRefreshAuthorization(
        RegisteredClient client,
        OAuth2AuthorizationService authorizationService,
        Instant refreshTokenExpiresAt) {

    Instant now = Instant.now();
    OAuth2RefreshToken refreshToken = new OAuth2RefreshToken(
            "refresh-fixture-" + UUID.randomUUID(),
            now.minusSeconds(30),
            refreshTokenExpiresAt);

    OAuth2AccessToken previousAccessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "expired-access-" + UUID.randomUUID(),
            now.minusSeconds(120),
            now.minusSeconds(1),
            Set.of("profile"));

    Authentication userPrincipal = new UsernamePasswordAuthenticationToken(
            "alice",
            "N/A",
            AuthorityUtils.createAuthorityList("ROLE_USER"));

    OAuth2Authorization authorization = OAuth2Authorization
            .withRegisteredClient(client)
            .principalName("alice")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizedScopes(Set.of("profile"))
            .attribute(Principal.class.getName(), userPrincipal)
            .token(previousAccessToken)
            .token(refreshToken)
            .build();

    authorizationService.save(authorization);
    return refreshToken.getTokenValue();
}
~~~

The helper requires imports from **java.security.Principal**, **java.time.Instant**, **java.util.Set**, **java.util.UUID**, **org.springframework.security.core.Authentication**, **org.springframework.security.core.authority.AuthorityUtils**, **org.springframework.security.authentication.UsernamePasswordAuthenticationToken**, **org.springframework.security.oauth2.core.OAuth2AccessToken**, **org.springframework.security.oauth2.core.OAuth2RefreshToken**, **org.springframework.security.oauth2.core.AuthorizationGrantType**, **org.springframework.security.oauth2.server.authorization.OAuth2Authorization**, and **org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService**.

In the test class, look up the client via **RegisteredClientRepository.findByClientId("test-user-client")** and pass it to the helper. The refresh token must be saved inside an authorization bound to the exact registered client. **principalName**, the principal attribute, and authorized scopes provide the context the refresh grant needs to mint new tokens. The fixture uses an already-expired prior access token to simulate a client needing to refresh.

## 5. Testing refresh token rotation and replay

With **reuseRefreshTokens(false)**, a successful refresh token exchange must return a new access token and a new refresh token. The test saves the old refresh token, verifies that the new value differs from the old value, and then attempts to reuse the old token:

~~~java
@Autowired
RegisteredClientRepository registeredClientRepository;

@Autowired
OAuth2AuthorizationService authorizationService;

@Test
void rotatesRefreshTokenAndRejectsThePreviousValue() throws Exception {
    RegisteredClient client = registeredClientRepository
            .findByClientId("test-user-client");
    String oldRefreshToken = saveRefreshAuthorization(
            client,
            authorizationService,
            Instant.now().plus(Duration.ofMinutes(20)));

    MvcResult result = mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", oldRefreshToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.refresh_token").isNotEmpty())
            .andReturn();

    JsonNode body = objectMapper.readTree(
            result.getResponse().getContentAsString());
    String newRefreshToken = body.path("refresh_token").asText();

    assertThat(newRefreshToken)
            .isNotBlank()
            .isNotEqualTo(oldRefreshToken);

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", oldRefreshToken))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"));
}
~~~

The test requires **ObjectMapper** to parse JSON and AssertJ to verify token values. A successful refresh response should also be checked for **token_type**, **expires_in**, and scope. If the client sends a **scope** parameter, the requested value must be a subset of the scopes approved by the original authorization; the server must not expand permissions during a refresh.

You can verify that the new token actually works by sending a subsequent refresh request with the new token. If rotation is enabled, the second exchange must issue yet another token, and the token from the first exchange becomes the old token. The replay test must use the exact token that was already replaced, not the new token.

## 6. Testing expired, wrong-client, and revoked refresh tokens

A refresh token has its own lifetime, independent of the access token. An expired access token does not automatically expire the refresh token. Conversely, an expired refresh token must be rejected even when client authentication is valid.

Create a fixture with **refreshTokenExpiresAt** in the past and verify that the server returns **invalid_grant**:

~~~java
@Test
void rejectsExpiredRefreshToken() throws Exception {
    RegisteredClient client = registeredClientRepository
            .findByClientId("test-user-client");
    String expiredRefreshToken = saveRefreshAuthorization(
            client,
            authorizationService,
            Instant.now().minusSeconds(1));

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("test-user-client", "user-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type", "refresh_token")
                    .param("refresh_token", expiredRefreshToken))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_grant"));
}
~~~

In addition to expiration and replay, include the following cases:

- **Wrong client:** use **test-user-client**'s refresh token with another client. The server must reject it because a refresh token is bound to the client it was issued to.
- **Wrong client authentication:** send a valid refresh token with a wrong client secret. The server must reject client authentication before issuing tokens.
- **Revoked token:** delete or invalidate the authorization containing the refresh token through the application's revocation mechanism; the next refresh attempt must fail.
- **Excess scope:** request a scope not approved by the user. The server must return an error and not issue an access token with additional scopes.
- **Unregistered grant:** a client without the **refresh_token** grant must not be allowed to exchange a refresh token.

For revocation tests, use the exact mechanism operated by the application, such as updating or removing the authorization via **OAuth2AuthorizationService**. Do not merely remove the refresh token from an auxiliary map if the production flow uses JDBC or another store.

## 7. Checking consistency across multiple instances

Rotation only matters when the old token can no longer be accepted once the new token is saved. In a single-instance environment, a basic replay test verifies this. In a multi-instance environment, you must also test the scenario where two requests submit the same refresh token nearly concurrently.

If two instances read the authorization before either finishes saving the new state, both could process against the same stale state unless the store has proper synchronization. **reuseRefreshTokens(false)** dictates creating a new token; it does not substitute for transactions, locking, or concurrency update controls in the persistence store.

With JDBC or a shared datastore, verify:

- Whether reading and updating the authorization use proper transaction boundaries.
- Whether two concurrent refresh requests can both accept the old token.
- Whether the updated authorization record is immediately visible to other instances.
- Whether the old token is rejected once rotation is committed.
- When saving the new token fails, whether the previous state remains consistent and recoverable.

If the system requires a refresh token to be used strictly once even under concurrent requests, explicitly identify and test the atomic consume or optimistic locking mechanism at the persistence layer. Sequential tests alone cannot prove this property.

## 8. Test matrix and diagnostics

| Scenario | Expected result |
|---|---|
| Client Credentials with valid secret and scope | **200 OK**, access token present, no refresh token |
| Client Credentials with wrong secret | **401**, **invalid_client** error |
| Client Credentials requesting an ungranted scope | **invalid_scope** error, no over-privileged token issued |
| Valid refresh token, rotation enabled | **200 OK**, new access token and new refresh token |
| Reusing old refresh token after rotation | **400**, **invalid_grant** error |
| Expired or revoked refresh token | **400**, **invalid_grant** error |
| Refresh token belonging to a different client | Rejected, no token issued |
| Refresh request asking for scopes beyond initial grant | Rejected, no scope expansion |
| Two concurrent requests using the same refresh token | Result conforms to the designed atomicity policy; two unintended uses must not both succeed |

When a test fails, check in order: whether the client is found; whether the client authentication method matches the fixture; whether the grant type is registered; whether the refresh token is stored under the right client ID; whether the token is expired or invalidated; whether **reuseRefreshTokens** has the expected value; and whether the authorization service successfully persists the new state.

Do not log access tokens, refresh tokens, or client secrets for diagnostics. You may log the client ID, grant type, OAuth error code, correlation ID, and persistence operation result. When you need to correlate a token in test logs, use a synthetic placeholder or one-way fingerprint instead of the raw token.

## 9. Completion checklist

Before considering the test suite complete, verify the following items:

- Client Credentials and Authorization Code/Refresh Token use separate fixtures with minimal grant types and scopes.
- Client Credentials issues only access tokens; clients obtain new tokens by re-authenticating when the access token expires.
- Refresh tokens are tested only with clients and authorizations granted appropriately.
- Refresh tokens are bound to the exact client, principal, and approved scopes.
- Rotation is explicitly enabled via **reuseRefreshTokens(false)** and tests verify the new token differs from the old one.
- Old tokens are rejected after rotation; expired, revoked, or cross-client tokens are also rejected.
- Scopes on the new access token never exceed originally granted permissions.
- Persistence tests use the same authorization service type and transaction semantics as the target environment.
- Concurrency tests are executed if the system requires strictly single-use refresh tokens across multiple instances.

When these cases are tested through the real token endpoint in the test context, the development team can catch client registration, client authentication, token lifetime, rotation, and authorization storage defects before changes reach a live environment.
