# Preparing the test profile, client fixtures, and signing keys for testing

In Spring Authorization Server, a functional test needs to run through the actual security configuration and OAuth 2.0 endpoints. The test suite must have registered clients, authorization grant data, and controllable signing keys. If it shares the production configuration, the tests risk depending on a real database, real clients, or private keys currently in operation.

This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, where we design and operate an Authorization Server from client management, consent, token issuance, PKCE, and refresh tokens to endpoint protection, key signing, and security flow testing. In the **Functional Testing** chapter, the goal is to set up an isolated test environment, create client fixtures with clear behavior, and provision signing keys that exist only within the test context.

## 1. Defining the boundary of the test profile

The test profile swaps out environment dependencies, such as the test issuer, HTTP port, logging, and data storage location. It must still preserve the security behaviors that the tests need to verify:

- The security filter chain and endpoint matchers of the Authorization Server are still initialized.
- Client authentication still validates the authentication method and client secret properly.
- Authorization Code still validates the redirect URI, state, and PKCE when required by the client.
- Consent is still stored and read through the service configured for testing.
- Tokens are still signed with a private key and can be verified with the corresponding public key.

Do not disable Spring Security entirely to make tests easier to run. Doing so bypasses the very filters, authentication providers, and endpoints that functional testing is meant to verify. Use **@SpringBootTest** together with **MockMvc** or a random HTTP server port so that requests go through the real filter chain.

Create **application-test.yml** in the application's configuration directory:

~~~yaml
spring:
  application:
    name: authorization-server-test

server:
  port: 0

app:
  authorization-server:
    issuer: https://authorization-server.test

logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.oauth2.server.authorization: DEBUG
~~~

**server.port: 0** asks the operating system to allocate a free port when running tests with a web environment. When using **MockMvc**, requests are handled inside the test context without needing to open a real port. The **app.authorization-server.issuer** property is an example application property; the **AuthorizationServerSettings** configuration needs to read this property so the issuer in metadata and tokens remains consistent. The **.test** domain is reserved for testing and does not point to a production Authorization Server.

Activate the profile directly on the test class:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(AuthorizationServerTestFixtures.class)
class TokenEndpointFunctionalTest {
    // Tests send requests through MockMvc
}
~~~

Do not set **spring.profiles.active: test** in **application-test.yml**; the profile must be explicitly selected from the run command or test class. That way, when running the application normally, the test configuration does not activate automatically.

If the application uses JDBC to store **RegisteredClient**, authorizations, or consents, configure a separate datasource for the test profile, typically H2 in the test suite. Initialize the schema using a script compatible with the exact Spring Authorization Server version in use. Do not rely on **spring.jpa.hibernate.ddl-auto** to auto-generate the Authorization Server JDBC tables. When testing persistence across restarts, use the real JDBC services in the test profile instead of in-memory services.

## 2. Creating client fixtures for each flow

A good fixture represents a client with a specific purpose. Avoid using a single client with all grant types and scopes, because that makes it hard to tell which condition is actually being tested.

| Fixture | Authentication method | Grant type | Conditions to test |
|---|---|---|---|
| **test-machine-client** | **client_secret_basic** | **client_credentials** | Client secret, scope, and token endpoint |
| **test-browser-client** | **none** | **authorization_code**, **refresh_token** | Public client, exact redirect URI, PKCE, and consent |

The machine client is a confidential client: it holds a secret on the server side and authenticates using HTTP Basic. The browser client is a public client: it cannot keep a secret safely over the long term, so the fixture assigns no client secret and enforces Proof Key for Code Exchange (PKCE). Each fixture only receives the scopes needed for its test cases.

Test beans can be declared with **@TestConfiguration**. The following example uses an in-memory repository and authorization services to test HTTP flows without needing a database:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class AuthorizationServerTestFixtures {

    @Bean
    @Primary
    PasswordEncoder testPasswordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Primary
    RegisteredClientRepository testRegisteredClientRepository(
            PasswordEncoder passwordEncoder) {

        TokenSettings shortLivedTokens = TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofMinutes(30))
                .reuseRefreshTokens(false)
                .build();

        RegisteredClient machineClient = RegisteredClient
                .withId("test-machine-client-id")
                .clientId("test-machine-client")
                .clientSecret(passwordEncoder.encode("test-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("message.read")
                .tokenSettings(shortLivedTokens)
                .build();

        RegisteredClient browserClient = RegisteredClient
                .withId("test-browser-client-id")
                .clientId("test-browser-client")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("http://127.0.0.1:8080/authorized")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(shortLivedTokens)
                .build();

        return new InMemoryRegisteredClientRepository(machineClient, browserClient);
    }

    @Bean
    @Primary
    OAuth2AuthorizationService testAuthorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }

    @Bean
    @Primary
    OAuth2AuthorizationConsentService testAuthorizationConsentService() {
        return new InMemoryOAuth2AuthorizationConsentService();
    }

    @Bean
    RSAKey testSigningRsaKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(UUID.randomUUID().toString())
                .generate();
    }

    @Bean
    @Primary
    JWKSource<SecurityContext> testJwkSource(RSAKey testSigningRsaKey) {
        return new ImmutableJWKSet<>(new JWKSet(testSigningRsaKey));
    }

    @Bean
    @Primary
    AuthorizationServerSettings testAuthorizationServerSettings(
            @Value("${app.authorization-server.issuer}") String issuer) {
        return AuthorizationServerSettings.builder()
                .issuer(issuer)
                .build();
    }
}
~~~

The main imports for the fixture class belong to the packages **org.springframework.security.oauth2.server.authorization**, **org.springframework.security.oauth2.server.authorization.client**, **org.springframework.security.oauth2.server.authorization.settings**, **org.springframework.security.crypto**, and **com.nimbusds.jose**. The Nimbus types include **RSAKey**, **RSAKeyGenerator**, **JWKSet**, **JWKSource**, **ImmutableJWKSet**, and **SecurityContext**.

The fixture secret is encoded with the same **PasswordEncoder** used by client authentication. During authentication, the Authorization Server compares the submitted secret against the encoded value in **RegisteredClient**. Do not store production secrets in test source code, configuration files, or shared environment variables.

**test-browser-client** uses **ClientAuthenticationMethod.NONE**, has no client secret, and enables **requireProofKey(true)**. When sending an authorization request, the test must generate a **code_challenge** from a random **code_verifier** and use **code_challenge_method=S256**. When exchanging the authorization code for a token, the client sends back the exact **code_verifier**. Tests should verify missing challenges, invalid verifiers, and valid verifiers alike. The redirect URI in the request must match the URI registered on the fixture exactly.

When testing OIDC discovery or UserInfo, the Authorization Server configuration must enable OIDC endpoints via **authorizationServerConfigurer.oidc(Customizer.withDefaults())** according to the application's configuration. Merely registering the **openid** scope in the fixture does not enable OIDC endpoints automatically.

The **@Primary** beans in the example help the test context prioritize fixtures when the application also declares beans of the same type. In a real project, place production repository configurations under an appropriate profile, such as **@Profile("!test")**, so production datasources or adapters are not initialized unintentionally. For persistence tests, replace the in-memory services with JDBC implementations and a test datasource rather than keeping this fixture as-is.

## 3. Provisioning test-only signing keys

JWT access tokens must be signed with a private key. The test suite needs the corresponding public key to verify the signature and needs to check that the JWKS endpoint publishes the right public key. The fixture above generates a 2048-bit RSA key when the Spring test context starts, then puts the key into an **ImmutableJWKSet** for Spring Authorization Server to use.

The private key exists only in the test context's memory. When the JWKS endpoint returns keys, Spring Authorization Server publishes only the public part of the JWK; private parameters are not sent to clients. Do not copy production private keys into **src/test/resources**, do not share keys between test and production, and do not commit real private keys to the repository.

The **kid** is generated uniquely for the key in each context. Tests should read the **kid** from the JWT header or JWKS response instead of assuming a fixed value. This keeps tests passing when the key is regenerated across runs.

A random key works well for tests that issue tokens and verify signatures within the same context. It is not suitable for tests that restart the application and then verify previously issued tokens, because the new startup generates a different key pair. For persistence or rotation tests across restarts, provide a separate fixed test key set managed as a test fixture and never used in a real environment. When testing rotation, keep the old public key in the JWKS while old tokens remain valid and verify that new tokens are signed with the active key.

## 4. Testing the token endpoint over HTTP

The following example verifies that a confidential client can use client credentials to obtain an access token. Requests pass through **MockMvc**, which tests the filter chain, client authentication provider, grant handler, and token generator working together:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(AuthorizationServerTestFixtures.class)
class TokenEndpointFunctionalTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    RSAKey testSigningRsaKey;

    @Test
    void issuesSignedAccessTokenForClientCredentialsClient() throws Exception {
        MvcResult result = mockMvc.perform(post("/oauth2/token")
                        .with(httpBasic("test-machine-client", "test-secret"))
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type", "client_credentials")
                        .param("scope", "message.read"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token_type").value("Bearer"))
                .andReturn();

        JsonNode response = objectMapper.readTree(
                result.getResponse().getContentAsString());
        String accessToken = response.path("access_token").asText();

        assertThat(accessToken).isNotBlank();

        JwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(testSigningRsaKey.toRSAPublicKey())
                .build();
        Jwt jwt = decoder.decode(accessToken);

        assertThat(jwt.getClaimAsString("iss"))
                .isEqualTo("https://authorization-server.test");
        assertThat(jwt.getClaimAsStringList("scope"))
                .contains("message.read");
    }
}
~~~

The imports for the test class include **MockMvc**, **MockMvcRequestBuilders.post**, **SecurityMockMvcRequestPostProcessors.httpBasic**, **MockMvcResultMatchers**, **MediaType**, **MvcResult**, **ObjectMapper**, **JsonNode**, **JwtDecoder**, **NimbusJwtDecoder**, **Jwt**, and AssertJ assertions. The default endpoint in the example is **/oauth2/token**; if the application customizes the endpoint in **AuthorizationServerSettings**, update the test path to match that configuration.

The test does not merely check HTTP 200 and the presence of an access token. It also verifies the JWT using the fixture's public key, then checks the issuer and scopes. That way, a misconfigured signing key or issuer will also fail the test. If the application issues opaque access tokens instead of JWTs, verify the response and introspection according to the configured token format; do not use **JwtDecoder** for opaque tokens.

## 5. Building a test matrix for the fixtures

Once the profile and fixtures are in place, implement test cases for each flow:

| Flow | Success cases | Cases that must be rejected |
|---|---|---|
| Client credentials | Valid secret, registered grant and scope | Wrong secret, nonexistent client, ungranted grant or scope |
| Authorization Code | Matching redirect URI, valid state, correct PKCE S256 | Wrong redirect URI, missing code challenge, wrong verifier, or already-used authorization code |
| Consent | User approves requested scopes | User denies or client requests scopes outside granted range |
| Refresh token | Valid refresh token exchanged per client policy | Expired, revoked, or already-rotated token under rotation policy |
| Signing and JWKS | JWT verifies with published public key | Invalid signature, untrusted key, or mismatched issuer |

For public clients, specifically test **code_challenge_method=S256**; do not use **plain** as the default for fixtures. For refresh token rotation, note that when **reuseRefreshTokens(false)** is enabled, the old refresh token must be replaced after a successful exchange. Tests must verify the behavior of the old token according to the application's policy.

In-memory services retain data for the lifetime of the Spring context. Therefore, authorizations or consents created in a previous test may still exist when a subsequent test reuses the context. Use fixtures with distinct identifiers, clean up data explicitly with adapters that support it, or create a separate context when clean state is genuinely required. Do not assume that **@Transactional** will roll back data written by every service or HTTP request.

## 6. Checking the configuration before running the test suite

Before running the entire test suite, verify the following items:

- The **test** profile is explicitly activated and does not load production secrets or datasources.
- The Authorization Server's security filter chain is still loaded in the test context.
- Each client fixture has the right client authentication method, grant types, redirect URIs, and scopes.
- Public clients enable PKCE; tests use S256 and verify both valid and invalid verifiers.
- Fixture client secrets are encoded using the same password encoder used by the client authentication provider.
- The test JWKSource contains only test keys; JWKS does not expose private parameters.
- The issuer across **AuthorizationServerSettings**, discovery metadata, and JWTs is consistent.
- Persistence tests use a test database with a schema matching the Spring Authorization Server version.

When these conditions hold steady, the test profile can run repeatedly without affecting clients, authorization data, or signing keys in a live environment. The fixture suite also forms the foundation for subsequent lessons testing the authorization flow, PKCE, consent, refresh tokens, token revocation, and key rotation.
