# Integration testing with MockMvc, real clients, and Testcontainers

An Authorization Server can pass unit tests and still fail when components work together. The security filter chain might block the wrong endpoint, authorization codes might not be persisted properly, PKCE might be skipped at the token endpoint, session cookies might be lost between requests, or authorization data might not be shared across instances. Integration testing needs to verify these boundaries using real Spring configuration and dependencies close to the deployment environment.

With Spring Authorization Server, combine three complementary approaches:

- **MockMvc** sends requests through Spring MVC and the Security filter chain inside the test ApplicationContext. It is well-suited for testing endpoints, status codes, headers, redirects, cookies, OAuth errors, and directly controllable flows.
- **Real clients over HTTP** call the running application on a real network port. You can use an HTTP client to test endpoints or a real OAuth2 Client application to complete login, callbacks, and token handling just like an external integrating system.
- **Testcontainers** launches real dependencies such as PostgreSQL or Redis inside dedicated containers for tests. This catches schema, SQL, transaction, persistence, and session bugs that simulated databases can miss.

Each approach tests a different boundary. MockMvc does not establish real TCP/TLS connections; an HTTP client alone does not prove durable persistence; Testcontainers alone does not verify the OAuth protocol. Combining them produces stronger evidence of the Authorization Server's behavior.

## 1. Choosing the right testing layer

Before writing a test, clarify the question it needs to answer. If the goal is to test a validator or token customizer, unit tests are usually enough. If you need to test the filter chain, endpoints, and repositories working together, use MockMvc with a Spring context. If you need to verify TLS, reverse proxies, browser redirects, or multiple instances, use real clients over HTTP. If you need to test a JDBC authorization service, consent, or session store, bring in real databases/caches with Testcontainers.

| Testing layer | Real components | Simulated components | Best suited to verify |
|---|---|---|---|
| Unit | Class under test | External dependencies | Scope rules, claims, validators, and customizers |
| MockMvc integration | ApplicationContext, MVC, Security filter chain, configured beans and repositories | TCP, TLS, proxy, browser | OAuth/OIDC endpoints, authentication, authorization, tokens, errors, cookies, and redirects |
| HTTP integration | Server running on a real port and its beans | May still use test dependencies | Network request/response, redirects, cookies, and metadata |
| Testcontainers integration | Containerized database/cache/services | Non-test dependencies | SQL, migrations, transactions, persistence, and sessions |
| End-to-end with real client | Authorization Server and separate OAuth2 Client | May use user/identity fixtures | Client-side login, consent, callback, token exchange, principal, and session |

Do not rely on a single test to prove every layer. MockMvc returning the right redirect proves only the response inside a servlet environment. It does not prove a reverse proxy advertises the right scheme, that a certificate is valid, or that a browser sends cookies back under SameSite policies.

A baseline integration test suite for an Authorization Server should cover:

1. Discovery and metadata publish the accurate issuer, endpoints, and JWKS.
2. Authorization requests validate client, grant, scopes, and redirect URI.
3. Authenticated users can complete the Authorization Code Flow.
4. PKCE S256 is verified at the token endpoint.
5. Authorization codes are single-use and expire per policy.
6. Client authentication and grant types are enforced properly.
7. Authorizations, consents, and tokens are saved and read back via real repositories.
8. Refresh, revocation, and introspection operate as configured.
9. Cookies, sessions, CSRF, and redirects work properly over HTTP.
10. Multiple instances can read shared authorization state if required by architecture.

## 2. Preparing test dependencies

The Maven example below uses Spring Boot test support, Spring Security test support, and Testcontainers. Use Testcontainers versions compatible with your JDK, Spring Boot, and project dependency management. If the project already manages Testcontainers via a BOM, do not declare individual versions on each module.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

If using the Testcontainers BOM, manage versions centrally in `dependencyManagement` via the `testcontainers-bom` artifact with type `pom` and scope `import`. Do not add Testcontainers dependencies for database engines you do not use.

To run Testcontainers, the developer workstation or CI runner needs a working Docker Engine or compatible runtime. If the CI environment lacks container execution permissions, configure an appropriate runner before running the suite.

## 3. Starting PostgreSQL with Testcontainers

When Spring Authorization Server stores `RegisteredClient`, `OAuth2Authorization`, and `OAuth2AuthorizationConsent` in JDBC, a PostgreSQL container lets you test repositories against a real database. The example below supplies dynamic URL, username, and password properties to Spring Boot via `DynamicPropertySource`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class AuthorizationServerDatabaseIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("authorization_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void applicationContextStartsWithRealDatabase() {
        // ApplicationContext started and connected to the PostgreSQL container.
    }
}
~~~

This skeleton illustrates container lifecycle and datasource configuration. In a real project, the test class must run the application's own migrations/schemas. If production uses Flyway or Liquibase, let migrations execute in the test profile with the exact same order and schema structure. If using Spring Authorization Server's schema scripts, manage them via project migrations rather than relying on a manually prepared database on a personal machine.

Typical JDBC tables store:

- Registered clients: client config, grant types, redirect URIs, scopes, and client settings.
- Authorizations: authorization codes, access tokens, refresh tokens, ID Tokens, and related metadata.
- Authorization consents: scopes approved by the resource owner for a client.

Never load sensitive production data into test containers. Use dedicated fixtures and keep tests independent of execution order.

### Verifying data persists after repository calls

A persistence test should save data through a repository and read it back via the repository or another application context. The goal is to confirm data is genuinely written to the database rather than staying only in objects or mocks.

~~~java
@Autowired
RegisteredClientRepository registeredClientRepository;

@Test
void registeredClientCanBeReadBackFromJdbcStore() {
    String clientId = "jdbc-client-test";

    RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId(clientId)
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("https://client.example.test/callback")
            .scope(OidcScopes.OPENID)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .build())
            .build();

    registeredClientRepository.save(client);

    RegisteredClient loaded =
            registeredClientRepository.findByClientId(clientId);

    assertThat(loaded).isNotNull();
    assertThat(loaded.getClientId()).isEqualTo(clientId);
    assertThat(loaded.getClientSettings().isRequireProofKey()).isTrue();
}
~~~

This example assumes the repository is configured with JDBC and tables have been migrated. If test suites run in parallel, use unique client IDs or dedicated databases/schemas per suite. Avoid using a single fixed client ID in a database shared across multiple pipelines.

Choose container images and settings close to production: PostgreSQL version, collation, timezone, extensions, and relevant data types. If production uses MySQL, MariaDB, or SQL Server, use the matching container to test migrations and SQL statements on the exact engine. Passing tests on PostgreSQL does not prove compatibility with MySQL.

If the application uses Redis to store Spring Session, add a Redis container as well. Add containers only when Redis is genuinely an application dependency.

## 4. Testing endpoints with MockMvc

MockMvc sends requests through DispatcherServlet and the filter chain inside the Spring ApplicationContext without opening a TCP port. It is ideal for verifying the Authorization Server's HTTP behavior quickly and deterministically.

For real security configuration, use `@SpringBootTest` combined with `@AutoConfigureMockMvc`. Do not disable filters just to make tests pass. If using a `@WebMvcTest` slice, provide all required beans and understand clearly which Authorization Server or Security filter chain configurations the slice may omit.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationServerEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void discoveryEndpointReturnsProviderMetadata() throws Exception {
        mockMvc.perform(get("/.well-known/openid-configuration"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.issuer").value(
                        "https://auth.example.test"))
                .andExpect(jsonPath("$.authorization_endpoint").exists())
                .andExpect(jsonPath("$.token_endpoint").exists())
                .andExpect(jsonPath("$.jwks_uri").exists());
    }
}
~~~

The discovery path and metadata fields depend on the issuer, OIDC configuration, and framework version. If the issuer includes a path or metadata endpoints are customized, use the exact URLs published by the application. Do not force tests to expect endpoints that the application has not enabled.

### Checking the token endpoint with a client fixture

The token endpoint requires client authentication depending on client type and registered method. Spring Security Test provides the `httpBasic` request post-processor for confidential clients using `client_secret_basic`.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointTests {

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

The `web-confidential-test` fixture must be registered in the repository with `client_secret_basic`, the Authorization Code grant, and a matching redirect URI. If the fixture uses `client_secret_post`, `private_key_jwt`, or mTLS, adjust authentication in the request accordingly. Never use a placeholder secret to test a public client.

Negative tests must check the status code, error code, and the absence of issued tokens. Do not assert specific internal error message strings if those messages can vary across versions or expose sensitive details.

## 5. Testing Authorization Code Flow and PKCE with MockMvc

You can test an Authorization Code Flow with MockMvc without a browser as long as the goal is verifying Authorization Server behavior. The test sets an authenticated principal, sends the authorization request, extracts the code from the redirect, and exchanges the code at the token endpoint.

The example below uses a public client to focus on PKCE. The client has no client secret, requires PKCE, and does not require interactive consent in this test. Testing the consent screen requires its own dedicated test.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationCodePkceIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RegisteredClientRepository registeredClientRepository;

    private String clientId;

    private static final String REDIRECT_URI =
            "https://client.example.test/callback";

    private static final String VERIFIER =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";

    private static final String CHALLENGE =
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

    @BeforeEach
    void registerPublicClient() {
        clientId = "mvc-public-" + UUID.randomUUID();

        RegisteredClient client = RegisteredClient.withId(
                        UUID.randomUUID().toString())
                .clientId(clientId)
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(REDIRECT_URI)
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(false)
                        .build())
                .build();

        registeredClientRepository.save(client);
    }

    @Test
    @WithMockUser(username = "alice")
    void authorizationCodeCanBeExchangedWithMatchingVerifier()
            throws Exception {

        MvcResult authorizationResult = mockMvc.perform(
                get("/oauth2/authorize")
                        .param("response_type", "code")
                        .param("client_id", clientId)
                        .param("redirect_uri", REDIRECT_URI)
                        .param("scope", "openid profile")
                        .param("state", "state-test-123")
                        .param("nonce", "nonce-test-123")
                        .param("code_challenge", CHALLENGE)
                        .param("code_challenge_method", "S256"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String redirect = authorizationResult.getResponse()
                .getRedirectedUrl();

        assertThat(redirect).isNotBlank();

        String code = UriComponentsBuilder
                .fromUriString(redirect)
                .build()
                .getQueryParams()
                .getFirst("code");

        assertThat(code).isNotBlank();

        mockMvc.perform(post("/oauth2/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type", "authorization_code")
                        .param("client_id", clientId)
                        .param("code", code)
                        .param("redirect_uri", REDIRECT_URI)
                        .param("code_verifier", VERIFIER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").isNotEmpty())
                .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
~~~

This is a structural example; you will need the matching JUnit, Spring Security Test, MockMvc, UriComponentsBuilder, RegisteredClient, and Spring Authorization Server imports. The application must enable OIDC endpoints if you want to verify ID Tokens. You can add an `id_token` assertion once the application's OIDC configuration is enabled.

The verifier/challenge values in the example are known PKCE S256 test vectors. In a larger suite, write a helper that generates a random verifier and computes the SHA-256/Base64 URL-safe challenge so every test stays independent. Never reuse an authorization code across tests.

### Testing wrong verifiers and code replay

Each negative test must mint a fresh authorization code. After retrieving the code, submit a wrong verifier and verify the token endpoint returns `invalid_grant`. A separate test exchanges a code successfully and then submits the same code again to prove a code cannot be used twice.

Key checks:

- Authorization requests missing PKCE are rejected if the client requires PKCE.
- Disallowed `code_challenge_method` values are rejected per policy.
- `code_verifier` mismatching the challenge is rejected.
- `redirect_uri` at the token endpoint must match the URI used when the code was issued.
- Expired or already-consumed codes cannot be exchanged again.
- No token response appears when the request fails.

Do not lump every negative case into one test. Each test should vary only one condition so failures immediately point to the root cause.

MockMvc does not simulate browser behavior on its own. It does not execute JavaScript or enforce browser cookie policies, SameSite cross-site navigation, TLS certificates, reverse proxies, or cross-domain callbacks. You can inspect `Set-Cookie` and `Location` headers at the servlet level, but you must use a real browser or HTTP client to verify actual browser behavior.

## 6. Using a real HTTP client against a running server

To test network connectivity, start the Authorization Server on a random port via `SpringBootTest` `webEnvironment = RANDOM_PORT`. The test uses a real HTTP client to call endpoints over TCP.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthorizationServerHttpTests {

    @LocalServerPort
    int port;

    private HttpClient httpClient;

    @BeforeEach
    void createHttpClient() {
        httpClient = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Test
    void metadataCanBeReadOverHttp() throws Exception {
        URI metadataUri = URI.create(
                "http://localhost:" + port
                        + "/.well-known/openid-configuration");

        HttpRequest request = HttpRequest.newBuilder(metadataUri)
                .GET()
                .header("Accept", "application/json")
                .build();

        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("issuer");
        assertThat(response.body()).contains("jwks_uri");
    }
}
~~~

In the example, redirects are not followed automatically so the test can inspect `Location` and intermediate OAuth steps. If auto-follow is enabled, the HTTP client can obscure intermediate responses or follow unwanted callbacks. For the authorization endpoint, keep redirects manual to inspect `code` and `state`.

### Calling the token endpoint with an HTTP client

For confidential clients, you can test token exchange with a real HTTP client after obtaining a valid authorization code from a test flow. Example illustrating sending a token request with `client_secret_basic`:

~~~java
String credentials = clientId + ":" + clientSecret;
String basic = Base64.getEncoder().encodeToString(
        credentials.getBytes(StandardCharsets.UTF_8));

String form = "grant_type=authorization_code"
        + "&code=" + URLEncoder.encode(code, StandardCharsets.UTF_8)
        + "&redirect_uri=" + URLEncoder.encode(
                redirectUri, StandardCharsets.UTF_8);

HttpRequest tokenRequest = HttpRequest.newBuilder(
                URI.create(baseUrl + "/oauth2/token"))
        .header("Authorization", "Basic " + basic)
        .header("Content-Type", "application/x-www-form-urlencoded")
        .POST(HttpRequest.BodyPublishers.ofString(form))
        .build();

HttpResponse<String> tokenResponse = httpClient.send(
        tokenRequest, HttpResponse.BodyHandlers.ofString());

assertThat(tokenResponse.statusCode()).isEqualTo(200);
assertThat(tokenResponse.body()).contains("access_token");
~~~

If the client uses PKCE, append `code_verifier` to the form. If using a public client, do not send Authorization Basic; send `client_id` per the client type's requirements. In real test code, use a form encoder or HTTP library to encode every parameter rather than concatenating unencoded strings.

This HTTP client verifies network connectivity and the real token endpoint. It is not yet a full OAuth2 Client: it does not manage `state`, `nonce`, browser sessions, discovery, token validation, or authorized client lifecycles. Those behaviors must be tested using a real client application or an OAuth/OIDC client library.

## 7. Testing with a real OAuth2 Client application

A high-value integration test runs two separate applications:

~~~text
Browser / test automation
          |
          v
Client application using Spring Security OAuth2 Client
          |
          | Authorization request / token exchange
          v
Spring Authorization Server
          |
          v
PostgreSQL / Redis test containers
~~~

The client application uses Spring Security OAuth2 Client as an independent integrating party. The client is configured with the issuer URI, client ID, client secret (if confidential), redirect URI, and scopes. It initiates login at `/oauth2/authorization/{registrationId}`; Spring Security redirects to the Authorization Server and handles the callback at `/login/oauth2/code/{registrationId}`.

Example client configuration in `application-test.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          authorization-server:
            provider: authorization-server
            client-id: browser-test-client
            client-secret: test-client-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          authorization-server:
            issuer-uri: https://auth.example.test
~~~

This configuration illustrates a confidential web client. For an SPA or native public client, omit the client secret and use PKCE per policy. The issuer URI in tests must point to the actually running Authorization Server. If ports or domains are allocated dynamically, supply the running server's address to the test client's issuer/registration properties rather than keeping a nonexistent URL.

An end-to-end browser test can:

1. Start the Authorization Server and client application with test configuration.
2. Open the client page using Playwright or Selenium.
3. Visit the endpoint that starts OAuth login.
4. Log in with the user fixture on the Authorization Server.
5. Approve consent if requested by the client.
6. Verify the browser returns to the client's exact callback.
7. Verify the client creates the Authentication principal and stores the authorized client.
8. Call a client-side endpoint to verify user details were loaded from the ID Token or UserInfo per configuration.
9. Test logout and session state.

This is the right place to verify `state`, `nonce`, cookies, SameSite, cross-site redirects, and real browser behavior. You do not need to run browser automation for every unit test; keep it in a dedicated end-to-end tier with a longer runtime budget.

If the module includes an API/resource server consuming access tokens, start that resource server or matching test endpoint. Send an access token issued by the Authorization Server and verify access according to scopes/authorities. Then try expired tokens, wrong audiences, wrong issuers, or invalid signatures. This tests both sides of the contract: the Authorization Server issuing valid tokens and the resource server validating tokens properly.

## 8. Using Testcontainers to test authorization and consent persistence

A mock repository only shows that code calls the right methods. It does not prove JDBC serialization, schema compatibility, transactions, or that authorizations can be retrieved on a subsequent request. When using a JDBC store, run the following tests against a containerized database:

| Behavior | Verification |
|---|---|
| RegisteredClient | Save and read back client, authentication methods, grants, redirect URIs, scopes, and settings |
| Authorization code | Save code, exchange code, mark consumed, and reject replay |
| Access token | Read back token metadata, expiry, scopes, and principal association |
| Refresh token | Rotate or revoke token per policy |
| Consent | Save consent, read back scopes, and apply on subsequent authorization requests |
| Restart | Restart the application context or instance and verify data remains intact |
| Concurrent access | Two concurrent requests cannot both consume the same authorization code successfully |
| Migration | Empty database upgrades to the right schema; older schemas upgrade via migrations |

One valuable test creates an authorization code on instance A, then uses instance B's token endpoint to exchange the code. If both instances share PostgreSQL and the same issuer/key configuration, instance B must locate the authorization and process the code properly. Once exchanged, instance A must reject any replay. This is a multi-instance integration test that may require two server processes or two application contexts on separate ports.

Do not verify the database merely by reading raw rows. Verify behavior through the application's public repositories/services or protocol endpoints to prove full mapping and serialization work end-to-end.

### Transactions and test isolation

With MockMvc on the same thread, a test can sometimes use the test framework's transaction. However, never rely on `@Transactional` to roll back side effects when running on `RANDOM_PORT`. Requests execute on a separate server thread with its own transaction; the test transaction does not wrap the server's transaction.

Appropriate isolation strategies:

- Use a dedicated database container per test suite and clean up fixture data after each test.
- Use separate schemas/databases per worker or pipeline.
- Generate unique client IDs, subjects, and states for every test.
- Use migrations to initialize a clean schema.
- Avoid depending on test execution order or data left by earlier tests.

When data needs to be rolled back, handle cleanup at the application layer or delete fixtures by identifier keys once the test completes. Never truncate shared authorization tables while tests are running in parallel.

## 9. Testing sessions and Redis if the application uses Spring Session

If the application stores HTTP sessions in Redis, use a Redis container to verify sessions can be read by another instance and survive application context restarts. Use in-memory sessions only when that is the exact architecture under test.

Required cases:

- Login creates a new session and returns the session cookie.
- Follow-up requests carrying that cookie continue the login session.
- Instance B can read a session created by instance A.
- Logout deletes or invalidates the session per policy.
- Expired sessions are rejected.
- Session ID changes after authentication when session fixation protection is enabled.
- Redis connection loss or unreadable sessions are handled per defined behavior.

Testcontainers can start Redis via the dedicated module or a `GenericContainer` with a pinned Redis image version. Inject dynamic host/port via `DynamicPropertySource` just like PostgreSQL. If production uses TLS, ACLs, or Redis Sentinel/Cluster, tests should reflect that configuration in the appropriate suite; a plain single Redis container does not prove a production topology.

## 10. Testing reverse proxies and TLS with an HTTP client

MockMvc cannot test TLS termination, certificates, DNS, or how a proxy writes forwarded headers. To test deployment behavior, run the server behind a reverse proxy in a test or staging environment and hit the public domain with an HTTP client or browser.

Cases to verify:

- Discovery and issuer use the right public scheme, host, and path.
- Authorization redirects return to the client's registered URI.
- Client-supplied `Forwarded` or `X-Forwarded-*` headers are not trusted.
- Session cookies carry appropriate `Secure`, `HttpOnly`, and `SameSite` flags.
- Backend endpoints accept traffic only from authorized proxies.
- TLS certificates and hostnames are verified by clients.
- Plain HTTP requests are redirected or rejected per HTTPS policy.
- Proxy-rewritten prefixes are neither duplicated nor stripped in URLs.

Never disable certificate validation in tests just to make requests pass. If the test environment uses an internal CA, configure a test trust store on the HTTP client. A test that skips certificate validation cannot catch chain or hostname verification errors.

## 11. Organizing the test suite in CI

Tests vary in runtime and dependencies. Split the suite by purpose so the pipeline stays fast while retaining necessary evidence.

| Group | Examples | When to run |
|---|---|---|
| Unit | Validators, token customizers, scope mappers | Every relevant change |
| MockMvc integration | Authorization endpoint, token endpoint, discovery, error responses | Pull request |
| JDBC/Testcontainers | RegisteredClient, authorizations, consents, migrations | Pull request or build candidate |
| HTTP integration | RANDOM_PORT, real HTTP client, cookies, and redirects | Build candidate |
| Client end-to-end | Spring Security OAuth2 Client + browser automation | Staging or scheduled runs |
| Multi-instance | Cross-node code exchange, sessions, and shared persistence | Staging prior to release |

Key CI configuration notes:

1. The Docker daemon must be ready before Testcontainers starts.
2. Pin image versions instead of using `latest` so tests stay reproducible.
3. Let JUnit/Testcontainers manage container lifecycles; never leave test containers running indefinitely after pipelines finish.
4. Never share test databases or Redis instances across unrelated pipelines.
5. If parallel tests are enabled, isolate fixtures and schemas to avoid contention.
6. Save container logs when tests fail, scrubbing any sensitive data.
7. Distinguish application test failures from failures caused by Docker/CI runner startup issues.
8. Never suppress security test failures just to make a pipeline green.

Organize tests under Maven Surefire/Failsafe or Gradle test tasks depending on project structure. Tests ending in `IT` are commonly grouped into `integration-test`/`verify` via Maven Failsafe; class names and tasks must stay aligned with your active build configuration. Do not assume a test file automatically runs in the desired phase unless the build configures the corresponding plugin or task.

### Controlling test data

- Use dedicated test client IDs, secrets, users, redirect URIs, and signing keys.
- Never commit production secrets into YAML or test source code.
- Never print access tokens, refresh tokens, authorization codes, ID Tokens, or cookies to logs.
- Keep test data minimal, reproducible, and easy to clean up.
- Record the OAuth/OIDC profile, database image, migration version, and commit SHA in test reports.
- Never target public production endpoints for destructive or high-volume token tests.

## 12. Diagnosing common failures

| Symptom | Possible cause | What to check |
|---|---|---|
| MockMvc returns unexpected 401/302 | Security filter chain, principal, or matcher differs from test setup | Inspect real filter chain, request user, and endpoint matcher |
| Authorization request fails with invalid_request | Client, redirect URI, response type, scope, or PKCE mismatch | Compare RegisteredClient fixture against the request |
| Authorization endpoint redirects to consent | Consent is enabled for the client or new scope | Set up separate fixtures for consent and no-consent tests |
| Token endpoint returns invalid_client | Wrong authentication method or fixture secret | Check RegisteredClient and how credentials are sent |
| Token endpoint returns invalid_grant | Expired/used code, wrong redirect, or wrong PKCE verifier | Generate a fresh code per test and check the verifier |
| Authorization missing after restart | JDBC store not configured or migration failed | Check datasource, schema, and JdbcOAuth2AuthorizationService |
| Testcontainers fails to start | Docker daemon, image pull, or runner permissions | Check Docker availability and container logs |
| Tests pass on H2 but fail on PostgreSQL | SQL/schema/type/transaction differences | Run against the exact database engine used in production |
| Browser callback fails while MockMvc passes | Cookies, SameSite, state, nonce, TLS, or redirects | Run tests with a real browser/client |
| Node B cannot exchange code issued by node A | Non-shared persistence or mismatched issuer/keys | Check database, issuer configuration, key sets, and clocks |
| Logout does not terminate session on another node | Local session store or unshared invalidation | Check Spring Session/Redis and cookies |

When a test fails, locate the very first request whose behavior differs from expectations. Save the status code, `Location`, headers, scrubbed response body, correlation ID, and fixture state. Do not just increase timeouts or retry tests when the root cause is a race condition, database isolation issue, or inconsistent shared state.

## 13. Integration testing completion checklist

- [ ] MockMvc runs with a real Spring ApplicationContext and Security filter chain.
- [ ] Authorization requests validate client, grant, scopes, redirect URI, and PKCE.
- [ ] The token endpoint validates client authentication and OAuth error responses.
- [ ] Authorization codes are strictly single-use.
- [ ] `RegisteredClient`, authorization, and consent data are verified via the JDBC store if the application uses JDBC.
- [ ] Testcontainers uses a database engine and migrations matching production.
- [ ] HTTP tests on a real port verify redirects, cookies, and metadata.
- [ ] A real OAuth2 Client completes login/callback in the end-to-end suite.
- [ ] Access tokens and ID Tokens are verified according to their respective roles.
- [ ] Refresh, revocation, and introspection are tested if enabled.
- [ ] Redis/sessions are tested if they are application dependencies.
- [ ] Proxy/TLS is tested via public domains in an appropriate environment.
- [ ] Tests are order-independent, do not share mutable fixtures, and perform explicit cleanup.
- [ ] CI has the required Docker/runtime, pins images, and stores evidence safely.

MockMvc, real clients, and Testcontainers form three complementary layers of proof. MockMvc quickly tests HTTP and Security logic inside the application; real clients verify the protocol over real connections and integrating-party behavior; Testcontainers verifies persistence and dependencies with near-production technology. When each layer has a clear purpose and scope, the Spring Authorization Server test suite catches endpoint configuration bugs, client integration errors, and durable state defects before changes reach production.
