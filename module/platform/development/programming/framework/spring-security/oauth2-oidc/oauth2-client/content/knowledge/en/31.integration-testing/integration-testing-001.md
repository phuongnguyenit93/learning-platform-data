# 31.1. Setting Up a Test Provider and Dedicated Test Accounts

## 1. Why Do We Need a Real Test OpenID Provider?

In unit tests, Spring Security Test lets you mock a user using <code>oidcLogin()</code> or <code>oauth2Login()</code>. That is very useful when you want to test a controller, method security, or how a principal's authorities are mapped.

However, a real OIDC Client has to go through many other components:

1. Fetching OpenID Provider metadata from the Discovery Endpoint.
2. Selecting the <code>ClientRegistration</code> with the right provider, Client ID, scopes, and callback URI.
3. Creating an authorization request with <code>state</code>, <code>nonce</code>, and PKCE when configured.
4. Redirecting the browser to the Authorization Endpoint.
5. Authenticating the test user at the OP and completing provider consent/policies.
6. Receiving the authorization code via the callback.
7. Sending the code to the Token Endpoint with client authentication and <code>code_verifier</code> if PKCE is used.
8. Verifying the ID Token, signature/JWK, <code>iss</code>, <code>aud</code>, <code>exp</code>, and <code>nonce</code> when applicable.
9. Creating <code>OidcUser</code>, <code>OAuth2AuthenticationToken</code>, HTTP session, and <code>OAuth2AuthorizedClient</code>.
10. Only then checking redirects, UserInfo, refresh, logout, or API calls.

A test that only places an <code>OidcUser</code> into the <code>SecurityContext</code> **cannot verify** this entire chain. That is why Chapter **31. Integration Testing** requires a **reproducibly configured test OpenID Provider** and **accounts not used in production**.

> **Goal:** Set up an isolated test OP, declare the OIDC ClientRegistration accurately, create stable test users, and run login success/failure scenarios without touching production accounts, secrets, or data.

In this lesson, we use **Keycloak as the test provider**. This is a practical choice, not a mandatory requirement: the same principles apply to Dex, an organization-managed sandbox OP, or a fake OP that implements the protocol sufficiently. The examples focus on **Spring Boot 3.x, Spring Security 6.x, Java 17, and the Servlet stack**; when applying them to Spring Security 7.x or another Keycloak version, compare against the APIs and configuration of the exact version in use.

## 2. Lesson Objectives

After this lesson, you will be able to:

- Distinguish between unit tests using a mock principal, protocol tests with stubs, and end-to-end tests with a real OP.
- Design an isolated test environment by **realm/tenant, ClientRegistration, users, scopes, and redirect URIs**.
- Launch a Keycloak test realm using Docker Compose or Testcontainers.
- Import a realm and create test users/test clients **from deterministic fixtures**, without manually clicking in the Admin Console every time.
- Configure Spring Security OAuth2 Client to point to the test provider's **issuer**.
- Verify the Discovery document, JWKS, ID Token issuer/audience, and corresponding callback URI.
- Log in via Authorization Code Flow through a browser, without using Resource Owner Password Credentials (ROPC) to "simulate" OIDC browser login.
- Organize test accounts with different permissions, disabled accounts, and negative scenarios.
- Manage the lifecycle of secrets, synthetic personal data, ports, containers, parallel tests, and CI isolation.
- Identify common errors such as issuer mismatch, redirect URI mismatch, missing state, cookie/SameSite issues, and JWKS lookup failures.

## 3. Choosing the Provider Type by Testing Level

| Option | Strengths | Limitations | When to Use |
|---|---|---|---|
| <code>SecurityMockMvcRequestPostProcessors.oidcLogin()</code> | Very fast; tests controller/authorization | No code exchange, Discovery, signature, or OP UI | Unit/MVC security tests |
| Mock <code>OidcUserService</code> or token response client | Isolates an integration boundary | Does not prove OP metadata, JWT issuance, or redirects | Focused component tests |
| HTTP stub like WireMock/MockWebServer | Controls 400/401/503, invalid_grant, malformed responses | Faking a full OP requires building spec-compliant metadata/JWKS/JWT/authorization flow yourself | Negative protocol tests, fault injection |
| Keycloak or real OP in a container | Tests Discovery, authorization code, login UI, consent, token/JWKS | Slower, requires Docker/browser and version management | Integration/E2E OIDC Login |
| External provider sandbox | Close to production provider behavior | Account limits, network, throttling, determinism | Compatibility/contract tests |

**You do not have to pick only one of the options above.** A good test suite has layers:

~~~mermaid
flowchart TD
    U["Unit/MVC tests: mock OidcUser"] --> C["Component tests: stubs/token HTTP"]
    C --> I["Integration tests: local OP container"]
    I --> E["Browser E2E: OP + Portal + browser"]
    E --> S["Sandbox compatibility: provider production-like"]
~~~

A test provider in a container verifies the protocol behavior of a specific OP. It **does not prove** that the production OP supports every feature identically, especially logout, <code>prompt</code>, tenant routing, MFA, or refresh-token rotation.

## 4. Test Environment Architecture

Example:

~~~text
Developer / CI
    |
    +--- Browser/Playwright
    |        |
    |        v
    |    http://localhost:18080
    |        |
    |        v
    |    Spring Boot Portal (OIDC Client)
    |        |
    |        +---- OIDC Discovery/JWKS/Token Endpoint
    |        |             |
    |        |             v
    |        |    http://localhost:18081/realms/it-realm
    |        |             |
    |        |             v
    |        |    Keycloak test container
    |        |
    |        +---- Fake Reports API / test database
    |
    +--- JUnit + Testcontainers
             |
             +---- Ephemeral Keycloak on random host port
             +---- Test clients/users/realm fixture
~~~

Two execution modes in this lesson:

**A. Local browser flow:** Portal uses port <code>18080</code>, Keycloak uses <code>18081</code>. The callback is registered exactly as:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

**B. Testcontainers in JUnit:** Keycloak uses a **random mapped host port** so test processes do not collide. We inject <code>issuer-uri</code> dynamically via <code>@DynamicPropertySource</code>; we must ensure the actual Discovery issuer matches the container's external URL. The initial Testcontainers demo is a **provider smoke test**, not a full automated browser login.

**Do not arbitrarily mix the two port models.** An authorization code is always bound to the redirect URI registered at the OP; the HTTP callback from the browser must reach the exact address where the Portal is serving.

## 5. Test Environment Isolation Principles

A reliable test OP needs:

1. **Dedicated issuer/realm:** do not use the production issuer or production realm.
2. **Dedicated Client ID:** for example <code>portal-it</code>, do not use the production Client ID.
3. **Dedicated test accounts:** synthetic users that do not collide with real users.
4. **Dedicated secrets:** test client secrets and passwords must never be reused in production.
5. **Dedicated redirect URIs:** only controlled local/CI callbacks.
6. **Minimal scopes/permissions:** start with <code>openid</code>, <code>profile</code>, and <code>email</code> only when actually needed.
7. **Never touch production APIs/databases:** downstream integrations point to a fake API/test DB.
8. **Deterministic data:** fixtures can be re-imported identically so tests do not depend on stale state.
9. **Restricted ports/network:** local containers must not be exposed to the public Internet.
10. **Clear lifecycle:** every test run has cleanup; parallel tests must not concurrently mutate shared user/session state arbitrarily.

Example test data:

~~~text
realm           = it-realm
issuer          = http://localhost:18081/realms/it-realm
client_id       = portal-it
registrationId  = it-op
redirect_uri    = http://localhost:18080/login/oauth2/code/it-op
username        = alice.test
email           = alice@example.test
~~~

The <code>example.test</code> domain is a placeholder/test data. Do not send real emails, do not use employee or customer emails, and do not create test accounts from production data.

## 6. Planning Test Accounts Before Setting Up the Provider

You should not just have a single <code>admin/admin</code> account and use it for every scenario. Build a matrix:

| Test User | Status | Role/Policy | Test Scenario |
|---|---|---|---|
| <code>alice.test</code> | enabled, email verified | Reader role | Standard OIDC login |
| <code>bob.test</code> | enabled, email verified | Different permissions from Alice | Switch account, session isolation |
| <code>admin.test</code> | enabled | Test app admin role | Verify role mapping |
| <code>disabled.test</code> | disabled | No permissions granted | OP rejects login |
| <code>unverified.test</code> | enabled, email unverified | Depends on OP policy | Claims/verified email policy |
| <code>consent.test</code> | enabled | Consent required | Accept/deny consent |
| <code>mfa.test</code> | enabled | MFA/step-up per test flow | <code>acr</code>/<code>amr</code> and policy |
| <code>partner.test</code> | different realm/issuer | Partner | Multi-provider/mix-up |

**You do not need to import all accounts immediately.** The base fixture can create Alice/Bob/disabled; scenarios requiring consent/MFA/partner can have separate fixtures or realms so tests stay independent.

### 6.1. OIDC Identity Must Be Based on Issuer and Subject

In OIDC, identity should be distinguished by:

~~~text
(iss, sub)
~~~

Do not use email as a global key. Two realms can issue ID Tokens for:

~~~text
alice@example.test
~~~

yet these are still two distinct identities if <code>iss</code>/<code>sub</code> differ.

### 6.2. Stable Test Subject

If you need to assert a stable <code>sub</code>, you can import a realm user with a fixed ID in the fixture. However, production logic tests should not depend on a Keycloak-specific username format or UUID layout.

For the "user switched accounts" use case, verify:

- The ID Token's <code>iss/sub</code> has been verified.
- <code>OidcUser.getSubject()</code> matches the expected test identity.
- The authorized-client token belongs to the matching registration/principal.
- Sessions/caches/tenants do not carry over data from the previous account.

### 6.3. Do Not Share Mutable-State Accounts Across Tests

If test A disables user Alice and test B logs in as Alice concurrently, test B can fail intermittently.

Solutions:

- Each test suite uses its own realm or container.
- Each test has dedicated users when it needs to mutate an account.
- Reset account/consent/revocation state after the test.
- Run cases that modify the same user sequentially if they cannot be isolated.

## 7. Docker Compose: Keycloak for Local Integration Tests

An example compose file launching a test Keycloak over local HTTP:

~~~yaml
services:
  keycloak-it:
    image: quay.io/keycloak/keycloak:26.0.0
    command: ["start-dev", "--import-realm"]
    environment:
      KC_HTTP_ENABLED: "true"
      KC_HOSTNAME_STRICT: "false"
      KC_BOOTSTRAP_ADMIN_USERNAME: "test-admin"
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${TEST_KEYCLOAK_ADMIN_PASSWORD:-local-only-test-password}
    ports:
      - "127.0.0.1:18081:8080"
    volumes:
      - ./src/test/resources/oidc/realm-integration.json:/opt/keycloak/data/import/realm-integration.json:ro
~~~

Notes:

- The tag <code>26.0.0</code> is only **a pinned illustrative version**, not a claim that it is the latest release. Projects should choose and pin a tested version, ideally an image digest.
- <code>start-dev</code> and HTTP are strictly for **local tests or isolated CI**; they are not production configurations.
- <code>127.0.0.1:18081:8080</code> reduces the risk of exposing the container outside the local machine.
- <code>KC_HOSTNAME_STRICT=false</code> in dev mode allows deriving URLs from the request according to Keycloak's hostname configuration; you must check the Discovery <code>issuer</code> after startup. With a proxy/CI public URL, more explicit hostname settings may be required.
- The admin password here is **only for the local fixture**; do not reuse it, and do not expose the admin port publicly.
- Only mount the test realm JSON, never mount production configuration or databases.

Example commands at the project root once the corresponding compose file exists:

~~~powershell
docker compose -f compose.oidc-it.yml up -d
docker compose -f compose.oidc-it.yml logs -f keycloak-it
~~~

When stopping:

~~~powershell
docker compose -f compose.oidc-it.yml down --volumes
~~~

<code>--volumes</code> should only be used with a clearly identified test compose stack. Do not run commands that destroy production data or target the wrong compose project.

### 7.1. Why Import a Realm Instead of Clicking in the Admin Console?

A manual clicking guide:

~~~text
Open Admin Console
Create realm
Create client
Create users
Set roles
Set password
...
~~~

is hard to reproduce when CI runs headless, environments change, or a reviewer tries to verify a failure.

Realm fixtures allow you to:

- Review configuration like code.
- Re-run with the same test state.
- Inspect diffs via version control.
- Avoid depending on manual step ordering.
- Recreate test users/clients in a few deterministic steps.

However, importing an **already existing** realm behaves differently depending on startup mode/provider. To reset state completely, use a fresh test container/database or a controlled import/reset mechanism rather than assuming <code>--import-realm</code> always overwrites all previous edits.

## 8. Realm Fixture: Test OIDC Client and Users

Example file path:

~~~text
src/test/resources/oidc/realm-integration.json
~~~

Sample content:

~~~json
{
  "realm": "it-realm",
  "enabled": true,
  "sslRequired": "external",
  "clients": [
    {
      "clientId": "portal-it",
      "name": "Portal Integration Test Client",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "clientAuthenticatorType": "client-secret",
      "secret": "local-it-client-secret-not-for-production",
      "standardFlowEnabled": true,
      "implicitFlowEnabled": false,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": false,
      "redirectUris": [
        "http://localhost:18080/login/oauth2/code/it-op"
      ],
      "webOrigins": [
        "http://localhost:18080"
      ]
    }
  ],
  "users": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "username": "alice.test",
      "enabled": true,
      "emailVerified": true,
      "email": "alice@example.test",
      "firstName": "Alice",
      "lastName": "Test",
      "credentials": [
        {
          "type": "password",
          "value": "local-only-alice-password",
          "temporary": false
        }
      ]
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "username": "bob.test",
      "enabled": true,
      "emailVerified": true,
      "email": "bob@example.test",
      "firstName": "Bob",
      "lastName": "Test",
      "credentials": [
        {
          "type": "password",
          "value": "local-only-bob-password",
          "temporary": false
        }
      ]
    },
    {
      "username": "disabled.test",
      "enabled": false,
      "emailVerified": false,
      "email": "disabled@example.test"
    }
  ]
}
~~~

### 8.1. Explaining the OP-Side ClientRegistration

- <code>clientId=portal-it</code>: the test Client ID used by the Portal.
- <code>publicClient=false</code>: example of a confidential Client with a secret.
- <code>standardFlowEnabled=true</code>: enables Authorization Code Flow.
- <code>implicitFlowEnabled=false</code>: do not use implicit flow for this test.
- <code>directAccessGrantsEnabled=false</code>: do not use ROPC/password grant to fake browser login.
- <code>redirectUris</code>: exact callback URL accepted by the OP.
- <code>webOrigins</code>: test origin if browser features require it; not a list of redirect URIs.

**A client secret inside a test fixture must still be treated as test-only.** Because it appears in source code, never carry this client into a public/staging/production deployment that holds real data. For test environments with shared network access, generate secrets dynamically or pull them from a CI secret store instead of using a committed placeholder.

### 8.2. Explaining Users

- Alice and Bob are **two distinct OIDC subjects**.
- Emails belong to the <code>.test</code> domain, sending no real mail.
- Test passwords here are synthetic data solely for an isolated container.
- <code>enabled=false</code> helps create a negative login scenario.

If you need to test MFA, account lockout, consent, or role mappers, add specialized fixtures. Do not assume the Keycloak realm import JSON above includes all production mappers/role policies.

### 8.3. Verifying the Import

After starting Keycloak, try opening:

~~~text
http://localhost:18081/realms/it-realm/.well-known/openid-configuration
~~~

A valid Discovery document contains fields such as:

~~~json
{
  "issuer": "http://localhost:18081/realms/it-realm",
  "authorization_endpoint": "http://localhost:18081/realms/it-realm/protocol/openid-connect/auth",
  "token_endpoint": "http://localhost:18081/realms/it-realm/protocol/openid-connect/token",
  "jwks_uri": "http://localhost:18081/realms/it-realm/protocol/openid-connect/certs"
}
~~~

This is **a partial illustration** of the returned JSON, not the full actual metadata. Do not hardcode token/JWKS endpoints with guessed strings when the OP supports discovery; use <code>issuer-uri</code> so the framework loads metadata and validates values.

## 9. Issuer, Discovery, and JWKS: Three Things That Must Be Exact

### 9.1. Issuer

In OIDC, the issuer is a security-critical identifier. For example:

~~~text
http://localhost:18081/realms/it-realm
~~~

Spring Security OIDC Client must verify that <code>iss</code> in the ID Token matches the configured issuer.

Do not treat the following strings as equivalent:

~~~text
http://localhost:18081/realms/it-realm
http://127.0.0.1:18081/realms/it-realm
http://keycloak-it:8080/realms/it-realm
~~~

Even though they might reach the same container in some networks, they are **different issuer URLs** under string comparison.

### 9.2. Discovery

OIDC Discovery goes through:

~~~text
{issuer}/.well-known/openid-configuration
~~~

The Client can obtain:

- <code>issuer</code>.
- <code>authorization_endpoint</code>.
- <code>token_endpoint</code>.
- <code>jwks_uri</code>.
- <code>userinfo_endpoint</code>, if present.
- Supported response types, grant types, signing algorithms, and scopes.

**Do not write tests that only assert HTTP 200.** If the Discovery <code>issuer</code> does not match <code>issuer-uri</code>, that is a configuration error that needs to be caught.

### 9.3. JWKS

JWKS contains **public keys** for the Client to verify JWT signatures issued by the OP. Never copy the OP's private signing key into the Portal.

In an integration test:

1. The OP signs the ID Token with the private key belonging to the test realm.
2. Spring Security fetches the public key from the trusted JWKS URI.
3. The Client verifies the JWT signature and claims.

If JWKS is unreachable, do not work around it by disabling JWT signature validation. Check hostname, DNS, network routing, TLS/truststore, key rotation, and cache behavior.

### 9.4. Key Rotation

An advanced scenario:

~~~text
T0: OP signs with kid=K1
T1: OP rotates to kid=K2
T2: Client encounters ID Token kid=K2
T3: Client refreshes/reloads JWK Set per policy
T4: Validation still succeeds if key trust is configured properly
~~~

Testing key rotation requires provider support and control over the key lifecycle. Do not turn a key rotation test into "accept any signature" or permanently hardcode a single PEM public key.

## 10. Pointing the Spring Boot Client to the Test Provider

In the Portal application:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          it-op:
            provider: it-op
            client-id: portal-it
            client-secret: ${TEST_OIDC_CLIENT_SECRET:local-it-client-secret-not-for-production}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          it-op:
            issuer-uri: ${TEST_OIDC_ISSUER_URI:http://localhost:18081/realms/it-realm}
server:
  port: 18080
~~~

For a local browser test:

~~~text
Portal baseUrl:
    http://localhost:18080

OAuth2 initiation:
    http://localhost:18080/oauth2/authorization/it-op

Callback:
    http://localhost:18080/login/oauth2/code/it-op

OIDC issuer:
    http://localhost:18081/realms/it-realm
~~~

**Port note:** <code>server.port=18080</code> fits a single local browser test. When using <code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> or running multiple CI jobs, the callback port will differ; you must provision appropriate redirect URIs or use a dedicated test ingress/hostname. Do not change the callback to a broad wildcard in production to avoid this issue.

### 10.1. Using a Test Profile

This configuration should be placed in:

~~~text
src/test/resources/application-oidc-it.yml
~~~

and enabled only in integration tests or a local test profile:

~~~java
@ActiveProfiles("oidc-it")
~~~

Do not put <code>TEST_OIDC_CLIENT_SECRET</code> or the test issuer on the production configuration path. Verify that CI/CD does not accidentally import the test profile into production.

### 10.2. Distinguishing Provider ID and Registration ID

In Spring Boot:

~~~yaml
registration:
  it-op:
    provider: it-op
~~~

<code>it-op</code> under <code>registration</code> determines the URL:

~~~text
/oauth2/authorization/it-op
~~~

<code>it-op</code> under <code>provider</code> groups metadata/issuer configuration. The two names can differ if the mapping is declared properly, though the example uses the same name for clarity.

## 11. Minimal Servlet SecurityFilterChain Configuration

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TestPortalSecurityConfig {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The example above uses the default OAuth2 Login flow. If you create a custom login page at <code>/login</code>, reconfigure <code>oauth2Login().loginPage("/login")</code> and serve that page. A direct GET:

~~~text
http://localhost:18080/oauth2/authorization/it-op
~~~

does not necessarily require a custom login page.

**Do not disable CSRF for the entire application** just to make login work. A normal Authorization Code GET callback uses OAuth2 <code>state</code> correlation; business POST requests relying on a browser session still need CSRF protection.

### 11.1. A Test-Only Principal Endpoint

To observe the user after login without returning tokens:

~~~java
package example.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TestIdentityController {

    @GetMapping("/test/whoami")
    Map<String, String> whoami(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject());
    }
}
~~~

Only enable this endpoint in an **isolated test environment**. Never expose all claims, ID Token, access token, or refresh token to the browser. In production, apply appropriate authorization/privacy policies if a profile endpoint is needed.

### 11.2. Reading Issuer and Subject

After Alice logs in, conceptual response:

~~~json
{
  "issuer": "http://localhost:18081/realms/it-realm",
  "subject": "11111111-1111-4111-8111-111111111111"
}
~~~

If <code>sub</code> was imported statically from the realm fixture and the Keycloak version honors this ID, the test can assert it directly; even better is to verify claims against the actual OP test state. Do not treat email as the primary identity key.

## 12. Authorization Code Flow: Test with a Browser, Not Password Grant

For OIDC browser login, the user agent executes:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Portal as Spring Security Portal
    participant OP as Keycloak Test OP
    User->>Browser: GET /test/whoami
    Browser->>Portal: Unauthenticated request
    Portal-->>Browser: Redirect OIDC initiation
    Browser->>Portal: GET /oauth2/authorization/it-op
    Portal->>Portal: Generate state, nonce, PKCE when configured
    Portal-->>Browser: 302 Authorization Endpoint
    Browser->>OP: Authorization request
    User->>OP: Login alice.test
    OP-->>Browser: Redirect code + state
    Browser->>Portal: GET /login/oauth2/code/it-op
    Portal->>OP: POST token request with authorization code
    OP-->>Portal: Access Token + ID Token
    Portal->>Portal: Validate ID Token, create OidcUser/session
    Portal-->>Browser: Redirect to protected URL or target
    Browser->>Portal: GET /test/whoami
    Portal-->>Browser: issuer + subject
~~~

### 12.1. Why Not Use ROPC to "Test Login"?

The request:

~~~http
POST /token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=alice.test&password=...
~~~

is **Resource Owner Password Credentials** (password grant), not Authorization Code + OIDC browser authentication. It bypasses redirects, state, nonce, consent UI, browser sessions, and many MFA mechanisms. This lesson intentionally **disables direct access grants** in the realm fixture.

If you only need to test token handling from an issuer, use appropriate token fixtures/stubs and clearly state the scope. Never treat ROPC as proof of a correct OIDC Client login flow.

### 12.2. PKCE in Integration Tests

PKCE includes:

~~~text
code_verifier
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
~~~

If the application uses PKCE, the test must retain the <code>code_verifier</code> of the original authorization request for the token exchange. Do not copy an authorization code from the browser and send a different verifier; the OP must reject it.

With a confidential Client, how the framework generates PKCE depends on configuration and the Spring Security version; inspect the actual authorization request rather than assuming every registration enables PKCE identically.

### 12.3. Nonce and ID Token

The OIDC Client typically includes <code>nonce</code> in the request depending on flow/configuration, then verifies the <code>nonce</code> claim in the ID Token when used. In an E2E test, never replace the ID Token with a hand-crafted JWT missing the nonce just to make login pass.

## 13. Test Accounts and Fixture Data Should Be Managed as Code

An example structure:

~~~text
src/
  main/
    java/example/...
  test/
    java/example/oidc/
      ProviderSmokeIT.java
      OidcLoginBrowserIT.java
      OidcFailureIT.java
    resources/
      application-oidc-it.yml
      oidc/
        realm-integration.json
compose.oidc-it.yml
~~~

This is an illustrative layout, not a requirement to create these exact files in the current task.

### 13.1. Fixtures Should Be Versioned

Any change to:

- Realm name.
- Test Client ID/secret.
- Redirect URIs.
- User roles/credentials.
- Protocol mappers.
- Token/session expiration.
- Signing algorithms/key settings.

can alter test behavior. Review fixtures in the same pull request instead of editing manually on a running Keycloak instance and forgetting to update source.

### 13.2. Create Scenario-Independent Data

For example:

~~~text
Test login success          → alice.test
Test switch account         → alice.test, bob.test
Test disabled account       → disabled.test
Test role mapping           → reader.test, admin.test
Test consent denied         → consent.test + explicit consent
Test refresh revoked        → a dedicated account/grant
Test MFA                    → mfa.test + configured authenticator
~~~

Do not share a single mutable user across dozens of parallel tests if they revoke each other's sessions, reset passwords, or modify consent.

### 13.3. Safe Cleanup

Each test run should:

1. Start a fresh container/realm or reset the test database.
2. Import the fixture.
3. Run tests.
4. Collect necessary redacted logs on failure.
5. Stop the container and remove test data per CI retention policy.

Avoid broad pattern-based cleanup like "delete all realms starting with prod" on a shared provider. Dedicate an endpoint or namespace to test automation.

## 14. Testcontainers: Launching an Ephemeral OP in JUnit

Docker Compose is convenient for developers running a browser. **Testcontainers** fits JUnit/CI because each test run gets its own container, random port mapping, and a lifecycle managed by the test framework.

### 14.1. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
~~~

Dependency versions/BOMs must match the Spring Boot and Testcontainers versions pinned by the project. If not using a BOM, declare versions according to your build's dependency management; do not leave dependencies floating in CI.

### 14.2. Provider Smoke Test Example

~~~java
package example.oidc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class ProviderSmokeIT {

    @Container
    static final GenericContainer<?> keycloak =
        new GenericContainer<>(
            DockerImageName.parse(
                "quay.io/keycloak/keycloak:26.0.0"))
            .withExposedPorts(8080)
            .withEnv("KC_HTTP_ENABLED", "true")
            .withEnv("KC_HOSTNAME_STRICT", "false")
            .withCopyFileToContainer(
                MountableFile.forClasspathResource(
                    "oidc/realm-integration.json"),
                "/opt/keycloak/data/import/realm-integration.json")
            .withCommand("start-dev", "--import-realm")
            .waitingFor(
                Wait.forHttp(
                    "/realms/it-realm/.well-known/openid-configuration")
                    .forPort(8080)
                    .forStatusCode(200)
                    .withStartupTimeout(Duration.ofMinutes(3)));

    @Test
    void oidcDiscoveryIsReachable() throws Exception {
        String base = "http://" + keycloak.getHost() + ":"
            + keycloak.getMappedPort(8080);

        String url = base
            + "/realms/it-realm/.well-known/openid-configuration";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(url))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"authorization_endpoint\""));
        assertTrue(response.body().contains(
            "\"token_endpoint\""));
        assertTrue(response.body().contains("\"jwks_uri\""));
    }
}
~~~

**The scope of this test is strictly a Discovery smoke test.** There is no browser login, authorization code, token exchange, or ID Token validation. The snippet uses standard Java 17 <code>HttpClient</code>; when using newer Java versions, the HTTP client lifecycle may have different resource management APIs. For a real smoke test, parse the JSON metadata with a JSON parser and assert **the exact <code>issuer</code> value**, instead of using <code>String.contains</code> as in the abbreviated example. The code demonstrates two important parts: container lifecycle and discovery verification.

### 14.3. Issuer Risk When Running a Container on a Random Mapped Port

Inside, Keycloak listens at:

~~~text
http://container:8080
~~~

while the JVM accesses it via:

~~~text
http://localhost:49152
~~~

If Discovery returns:

~~~text
issuer=http://container:8080/realms/it-realm
~~~

while the Portal is configured with:

~~~text
issuer-uri=http://localhost:49152/realms/it-realm
~~~

strict issuer validation may fail. **Do not disable the issuer check to make the test pass.**

Solutions:

1. Configure Keycloak's hostname/public URL so Discovery and token <code>iss</code> match the URL used by the JVM/Portal.
2. Use a consistent test proxy/hostname if the Client runs inside a Docker network.
3. Read the actual Discovery <code>issuer</code> and assert against the exact expected issuer.
4. Keep the browser redirect URI separate from the provider's issuer.

Keycloak's hostname/proxy variables can change across versions. Do not copy old guides for a newer Keycloak release and assume metadata will always be correct.

### 14.4. Separating Smoke Tests and Full Login

In CI, you can run:

~~~text
ProviderSmokeIT
    → container starts
    → realm exists
    → Discovery metadata valid
    → JWKS accessible
    → issuer matches expected
~~~

and separately:

~~~text
OidcBrowserLoginIT
    → Portal + OP started
    → redirect URI registered
    → browser logs in test user
    → callback verified
    → authenticated session
~~~

Avoid naming a smoke test <code>OidcFullLoginIT</code> when it has not gone through an authorization code callback.

## 15. @DynamicPropertySource to Provide issuer-uri

When a container uses a random host port, <code>@DynamicPropertySource</code> lets the Spring test context obtain the issuer dynamically.

~~~java
package example.oidc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("oidc-it")
@Testcontainers
class OidcSpringContextIT {

    // Container declaration similar to ProviderSmokeIT,
    // or use a base fixture properly organized for the suite.
    static GenericContainer<?> keycloak = createTestKeycloak();

    static {
        keycloak.start();
    }

    @DynamicPropertySource
    static void registerProvider(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.client.provider.it-op.issuer-uri",
            () -> "http://" + keycloak.getHost() + ":"
                + keycloak.getMappedPort(8080)
                + "/realms/it-realm");
    }

    @Test
    void springContextLoadsWithTestProvider() {
        // Only verifies wiring + metadata resolution.
    }
}
~~~

This is **illustrative test class pseudocode**, not a complete copy-pasteable class: the <code>createTestKeycloak()</code> method must be defined using the container config from the previous section, and <code>GenericContainer</code> must be imported. You can choose one of two lifecycle styles:

- <code>@Testcontainers</code> + <code>@Container</code> managed by the JUnit extension.
- Start a static container in a shared fixture, then stop/clean it up with a controlled lifecycle.

Do not both start a static container manually and let the JUnit extension start/stop the same container unintentionally. <code>@DynamicPropertySource</code> must return the issuer of the **already started container**, and the Spring test context needs the proper test profile.

### 15.1. Test Context Cache Warning

Spring TestContext can cache the ApplicationContext across multiple test classes. If a cached context points to the random-port issuer of a stopped container, subsequent tests can fail with confusing errors.

Options:

- Use a shared container whose lifecycle spans all reusing contexts.
- Partition contexts cleanly by dynamic properties/test class.
- Use <code>@DirtiesContext</code> when needed to prevent stale caching, balancing performance.
- Do not use a static mutable issuer variable that parallel suites can overwrite.

### 15.2. Dynamic Issuer Is Different from Dynamic Redirect URI

<code>issuer-uri</code> is the OP's URL. <code>redirect-uri</code> is the Portal's callback URL. Even though both can use random ports, how they are supplied differs.

If the Portal runs with <code>@SpringBootTest(RANDOM_PORT)</code>, you must register the callback with the OP for the **actual port**. Do not choose a broad wildcard redirect URI to avoid provisioning the client properly in tests.

## 16. Browser E2E: Setting the Right Callback URI

With the local flow from earlier sections:

~~~text
Portal: http://localhost:18080
OP:     http://localhost:18081
~~~

Client redirect URI at the OP:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

The application must use a registration with:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

and actually be accessed by the browser at <code>http://localhost:18080</code>, not <code>http://127.0.0.1:18080</code> if the OP only registers localhost. In OIDC, URLs must match exactly per registration/OP validation.

### 16.1. Why Not Use localhost on One Side and a Docker Service Name on the Other?

If the Portal is on the host JVM:

~~~text
http://localhost:18081
~~~

may reach Keycloak via the published port.

If the Portal is also inside the Docker network:

~~~text
http://keycloak-it:8080
~~~

may point to the same container, but a browser outside Docker **cannot necessarily resolve** <code>keycloak-it</code>. OP redirects and JWT <code>iss</code> must also use a consistent URL.

Therefore, a full browser test needs a hostname/public URL **accessible correctly by both the browser and the Client backend**, while the OP advertises the corresponding issuer.

### 16.2. Hostnames and TLS

Local HTTP is a testing exception in an isolated environment. For HTTPS integration tests:

- Create a test CA/certificate and configure the truststore for the JVM/browser.
- Ensure issuer, discovery endpoints, and callbacks properly use <code>https</code>.
- Never disable certificate verification JVM-wide just to make tests run.
- Never enable trust-all client TLS in code that could leak into production.

## 17. Browser Automation Logging In Test Accounts

Playwright or Selenium can drive a real browser:

~~~text
1. Open http://localhost:18080/test/whoami.
2. Portal redirects to OIDC initiation/provider login.
3. Fill in alice.test and test password at the OP.
4. Submit login.
5. Browser receives callback code + state.
6. Portal creates session.
7. Browser goes to /test/whoami.
8. Verify Alice's issuer/sub.
~~~

### 17.1. Skeleton Playwright Java Example

~~~java
import com.microsoft.playwright.*;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcBrowserLoginIT {

    @Test
    void aliceCanLogInThroughTestProvider() {
        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                new BrowserType.LaunchOptions().setHeadless(true));

            BrowserContext context = browser.newContext();
            Page page = context.newPage();

            page.navigate(
                "http://localhost:18080/oauth2/authorization/it-op");

            // In practice, use Page Objects/locators matching the DOM of
            // the pinned Keycloak version or test-ids provided by a test theme.
            page.locator("#username").fill("alice.test");
            page.locator("#password").fill(
                "local-only-alice-password");
            page.locator("#kc-login").click();

            page.waitForURL(url ->
                url.contains("localhost:18080"));

            page.navigate("http://localhost:18080/test/whoami");

            String body = page.locator("body").innerText();
            assertTrue(body.contains(
                "11111111-1111-4111-8111-111111111111"));

            context.close();
            browser.close();
        }
    }
}
~~~

This is a **skeleton test flow**, not a standalone runnable E2E suite: Portal + Keycloak must be started, Playwright test dependency and browser binaries must be installed, test fixtures and the right callback URI must be in place, and locators must match the login page of the chosen OP version.

Playwright Java is an optional dependency for E2E tests; do not add it for MockMvc-only tests if a browser is not needed. Keycloak's UI can change across versions, so group locators into Page Objects or use stable themes/test IDs.

### 17.2. Browser Context Isolation

Each test should have a fresh <code>BrowserContext</code>:

~~~text
Test Alice → context A → SSO/session cookies A
Test Bob   → context B → SSO/session cookies B
~~~

Do not share a browser profile carrying an OP SSO cookie from an earlier test. If you want to test switch-account/SSO reuse, that must be **an intentional scenario** using the same context within that scenario.

### 17.3. Do Not Log Passwords or Full Callback URLs

Browser automation can record screenshots, HAR files, and traces. Callback URLs containing <code>code</code>/<code>state</code> are sensitive data. Sanitize artifacts, limit retention/access, and do not push credentials into CI logs.

## 18. Test Accounts: Basic Positive Scenarios

### 18.1. Alice Logs In Successfully

Given:

~~~text
alice.test: enabled, emailVerified=true
client: portal-it
scope: openid profile email
~~~

When:

~~~text
Browser starts /oauth2/authorization/it-op
User authenticates Alice at OP
Callback completes
~~~

Then:

~~~text
Authentication is OAuth2AuthenticationToken
Principal is OidcUser
getSubject() matches Alice test subject
issuer matches registered OP issuer
Authorized Client registrationId = it-op
Portal session authenticated
~~~

Do not assert the access token by matching the entire JWT string or store it in test reports. Tokens have dynamic <code>iat</code>/<code>exp</code> and signatures; test semantic claims and intended audience/scope.

### 18.2. Bob Logs In in Another Context

Given:

~~~text
Bob: different subject
New isolated browser context
~~~

Then:

~~~text
Bob session != Alice session
Bob subject != Alice subject
No cross-user authorized client
No cached profile from Alice
~~~

### 18.3. Checking Post-Login Redirect

An unauthenticated user opens:

~~~text
/reports/quarterly?year=2026
~~~

After a successful login, <code>SavedRequestAwareAuthenticationSuccessHandler</code> can return the user to the original URL. Verify the URL/query and authorization of the new principal.

Do not merely assert <code>302</code> and assume the redirect policy is correct; inspect the <code>Location</code> header or actual browser URL.

## 19. Negative Scenarios for the Test Provider

| Scenario | How to Set Up | Expectation |
|---|---|---|
| Wrong password | User enters an incorrect password | OP rejects; Portal has no authenticated session |
| User disabled | Use <code>disabled.test</code> | OP does not grant a successful login |
| User denies consent | Realm/client requires consent; user declines | Callback contains OAuth2 error when profile supports it; failure handler |
| Wrong redirect_uri | Client registration lacks callback URI | OP rejects authorization request |
| Wrong client secret | Portal sends secret not matching test client | Token Endpoint <code>invalid_client</code> |
| Code reused | Submit an already-consumed authorization code | Token Endpoint rejects, typically <code>invalid_grant</code> |
| Callback state mismatch | Alter callback state or lose repository | Spring Security rejects login |
| Wrong ID Token issuer | Mismatched token fixture/JWKS trust setup | OIDC validation fails |
| Wrong ID Token audience | Token issued for another Client ID | OIDC validation fails |
| ID Token expired | Fault injection with token fixture having old <code>exp</code> | OIDC validation fails |
| JWK key unavailable | Shut down JWKS endpoint or change key cache | Test failure handling, do not disable verification |
| OP unavailable | Stop container/network fault | Portal fails safely, no login loop |
| UserInfo error | Stub/UserInfo policy rejects | OIDC integration error handling |

**You should not use a single real OP to try to manufacture every malformed JWT by editing its live database.** Some negative cases like invalid signatures, nonce mismatches, or malformed token bodies are much easier to control with an **HTTP token-response stub + test signing keys**; use Keycloak for normal behavioral flows and OP errors that can be reliably configured.

### 19.1. Client Secret Mismatch

If the Portal uses:

~~~text
client-secret=WRONG-TEST-SECRET
~~~

while the Keycloak client has:

~~~text
secret=local-it-client-secret-not-for-production
~~~

the token request with <code>client_secret_basic</code> must be rejected per client authentication policy.

In the browser, the user may authenticate successfully at the OP, but the Portal fails during code exchange. This is **not** a "user entered the wrong password" error.

### 19.2. State Mismatch

A callback with a valid code but wrong <code>state</code> must be rejected. Do not fix it by doing:

~~~java
// DO NOT do this:
skipStateValidation = true;
~~~

Tests should maintain the distinction between:

- An authorization request was created, but the state is wrong.
- No authorization request exists due to a different session or expiration.

Neither case may issue an authenticated session, though the root causes differ.

### 19.3. Consent Denied

The base realm fixture does not enable a consent-required flow yet. To test user consent denial, **configure consent on the test client/OP appropriately** and verify the real OP displays the consent screen. Do not assume "every login with OIDC scopes shows a consent screen."

## 20. UserInfo, Roles, and Claims

An OIDC Client may use the ID Token and call the UserInfo Endpoint depending on scopes/provider configuration.

### 20.1. Email Claim

Expect:

~~~text
email = alice@example.test
email_verified = true
~~~

only when the provider actually emits those claims in the token/UserInfo per scopes and protocol mappers.

Do not conclude that configuring <code>scope=email</code> on a client guarantees the ID Token always contains the email claim; the provider may place email in UserInfo or apply another policy.

### 20.2. Role Mapping

Keycloak can use realm/client roles; however, Spring Security OAuth2/OIDC Client does not automatically convert every JSON role into <code>ROLE_ADMIN</code> in all configurations.

If you need to test:

~~~text
admin.test → ROLE_ADMIN
alice.test → ROLE_READER
~~~

configure:

1. Role assignments in the realm fixture.
2. Protocol mappers to deliver roles to the right token/UserInfo if policy requires.
3. The application's <code>OidcUserService</code> / granted-authorities mapper.
4. Assertions on <code>Authentication.getAuthorities()</code>.

**Never grant roles based on an email ending in <code>@example.test</code>**; that is not OIDC authorization proof.

### 20.3. Multi-Provider

If testing both Company and Partner:

~~~text
issuer A: /realms/it-company
issuer B: /realms/it-partner
~~~

Create **two ClientRegistrations**, each with its corresponding issuer/client ID/secret/redirect URI. Never share one issuer for both just because user emails match.

## 21. Refresh Token and Rotation Tests

Not every OIDC login issues a refresh token under the same policy; understand the provider config/scopes, offline access, and session policy.

### 21.1. Access Token Expiry

In the test realm, you can shorten access-token lifetime to test:

~~~text
Login Alice
Wait until access token near expiry
AuthorizedClientManager refreshes
Token Endpoint returns new access token
Token stored for Alice/registrationId
~~~

Do not use <code>Thread.sleep(5 minutes)</code> in every test if you can control the clock or token fixture; the test suite will become slow and flaky.

### 21.2. Refresh Rotation

If the test provider supports refresh-token rotation, enable it in a separate fixture:

~~~text
Initial: access A0, refresh R0
Refresh: access A1, refresh R1
Old R0 reused: rejected according to OP policy
~~~

In a cluster:

~~~text
Node A and B load R0
Node A refreshes R0 → R1
Node B refreshes R0 → invalid_grant
~~~

**A shared JDBC/Redis token store does not prevent races by itself.** You must test single-flight/locking/versioned conditional deletes so Node B does not delete R1 that Node A just saved.

### 21.3. Revoke/Grant Invalidation

Create a dedicated test account/session and revoke the grant at the OP via Admin API/test fixture or provider capability. Never revoke the shared test user Alice while other tests are using it.

## 22. Logout Tests: Local, RP-Initiated, and Back-Channel

OIDC has several types of logout, depending on provider capability.

| Type | Starting Point | Test Focus |
|---|---|---|
| Local logout | Portal session | SecurityContext/session invalidated; POST + CSRF |
| RP-Initiated Logout | Portal → OP <code>end_session_endpoint</code> | OP redirect, <code>id_token_hint</code>, valid post-logout URI |
| Front-Channel Logout | OP → browser → RP | Browser cookies, iframe/session mapping per profile |
| Back-Channel Logout | OP server → RP server | Signed Logout Token, issuer/audience/sid/sub/session registry |

### 22.1. Local Logout Does Not Clear the OP SSO Session

After:

~~~text
POST /logout
~~~

the Portal session may be cleared, but the browser still holds the OP cookie. When visiting:

~~~text
/oauth2/authorization/it-op
~~~

the OP may immediately SSO Alice back in. **This is not necessarily a local logout bug.**

### 22.2. RP-Initiated Logout

If Keycloak/the test OP provides <code>end_session_endpoint</code>, you can test <code>OidcClientInitiatedLogoutSuccessHandler</code> or its reactive counterpart depending on the stack.

You must register/allowlist <code>post_logout_redirect_uri</code> per policy. Never redirect users to an arbitrary URL supplied by the browser.

### 22.3. Back-Channel Logout

If using the supporting Spring Security feature:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

this is a reference configuration for **versions with the Back-Channel Logout DSL**; verify the version and SecurityFilterChain integration.

Tests must prove:

- The OP sends a **signed Logout Token**.
- Spring Security verifies <code>iss</code>, <code>aud</code>, <code>events</code>, signature, and claims per profile.
- <code>sid/sub</code> matches the session registry.
- The exact target session is terminated.

Do not test back-channel logout by manually POSTing an unsigned <code>sub=alice</code> and expecting the Portal to log out.

## 23. CI Environment and Parallel Execution

### 23.1. Docker Requirements

Testcontainers typically requires a Docker-compatible runtime. On developer/CI machines:

~~~text
Docker engine reachable
Container image accessible or mirrored
Sufficient RAM/CPU
Network/DNS predictable
Ports available (for local Compose)
Browser runtime installed (for E2E)
~~~

Do not assume every CI runner has Docker or permission to pull images from the Internet. If your organization uses a registry mirror/private artifact repository, pin the image digest and configure the mirror appropriately.

### 23.2. Do Not Depend on a Shared Public Sandbox

A shared provider sandbox can suffer from:

- Multiple CI runs using the same test account.
- Passwords changed by another test.
- Leftover session/consent state.
- Rate limiting.
- Provider deployments mid-test.
- Network drops or disallowed callbacks from CI runners.

Prefer ephemeral containers for routine integration tests; only use a shared provider sandbox for compatibility tests with clear isolation and ownership.

### 23.3. Parallel Tests

Strategies:

1. Separate container per test class/suite when resources allow.
2. Separate realm/client/user namespace per parallel job.
3. Random mapped host ports for Testcontainers; the test provider issuer must reflect the exact port.
4. One isolated browser context per test user.
5. Never mutate a shared test account.
6. Clean up by run ID/namespace, avoiding actions that break other runs.

### 23.4. Test Results Must Not Depend on Execution Order

Do not design:

~~~text
test1 creates Alice
test2 logs in Alice
test3 disables Alice
test4 expects Alice still enabled
~~~

Each test needs an independent fixture or explicit setup/reset.

## 24. Security of the Test Provider

Although not production, a test OP still holds credentials and can issue tokens valid for test APIs.

### 24.1. Never Use Production Secrets

Never import:

~~~text
PRODUCTION_CLIENT_SECRET
PRODUCTION_REFRESH_TOKEN
PRODUCTION_SIGNING_PRIVATE_KEY
CUSTOMER_PASSWORD
~~~

into the test environment or logs.

### 24.2. Never Broadly Expose the Test OP

Local Compose binds <code>127.0.0.1</code>. In CI, restrict container networks/ingress and avoid public endpoints unless necessary.

If you must run cloud E2E with the browser and Portal/OP on different hosts, require:

- Proper TLS.
- Firewall/access control.
- Test-only issuer/client/users.
- Secret store.
- Logging/redaction.
- Lifecycle cleanup.

### 24.3. Never Send Real Emails or SMS

User <code>alice@example.test</code> is only for claim testing. Disable SMTP or use a fake mail sink such as MailHog/Mailpit in an isolated environment if testing email verification/password reset.

### 24.4. Test Admin Accounts

Admin API users have permission to configure realms. Never use admin credentials in normal browser login tests, never print them to CI output, and never reuse them in production.

### 24.5. Test Artifacts and GDPR/Privacy

Browser screenshots/HAR files can contain email claims, session IDs, authorization codes, or cookies. With synthetic accounts the risk is smaller, but not zero.

Save only necessary artifacts, redact sensitive headers/URL parameters, and limit retention.

## 25. Controlled Fault Testing: Real OP and Complementary Stubs

A real OP like Keycloak is great for positive flows, but not every error is easy to trigger via the UI.

### 25.1. Using HTTP Stubs for Malformed Responses

When you need to test:

- Token Endpoint returning JSON missing <code>access_token</code>.
- An ID Token with an invalid signature.
- JWKS with a mismatched key ID.
- HTTP 429/503.
- UserInfo returning an unexpected content type.
- Token response containing an unknown provider error code.

you can stand up a **test OP stub** with consistent Discovery/JWKS/Token Endpoints, or a dedicated fault injection proxy. You do not need to alter global Keycloak config to fabricate every single fault.

### 25.2. Never Return an Arbitrary JWT and Expect Spring Security to Accept It

A valid ID Token requires:

~~~text
Signature verifiable with trusted JWKS
iss = configured issuer
aud contains expected client_id
exp > now within configured clock policy
iat appropriate
sub present and valid
nonce matches authorization request, when required
~~~

If you want to test an invalid signature, start from a flow with a valid token and intentionally corrupt the signature in the fixture. The expected assertion is **login rejected**, not framework acceptance.

### 25.3. Layered Error Simulation

| Layer | Tool/Fixture | What to Assert |
|---|---|---|
| Authorization Endpoint | Keycloak UI/policy | User login/consent, redirect + state |
| Token Endpoint | Keycloak or stub | Code exchange/invalid_client/invalid_grant |
| JWKS/ID Token | Test keys, controlled issuer | Signature/issuer/audience/nonce validation |
| UserInfo | Provider/stub | Valid/invalid claims and mapping |
| Resource Server | Fake API | Bearer audience/scope, HTTP 401/403 |
| Local session | MockMvc/browser | SecurityContext/session/cookie |
| Logout | OP feature/fault injection | Correct session termination |

## 26. Troubleshooting: Common Errors

| Symptom | Possible Cause | Diagnostic Direction |
|---|---|---|
| OP returns 404 at Discovery | Realm not imported, wrong path | Check realm name and import logs |
| Discovery returns 200 but wrong issuer | Keycloak hostname/proxy config | Compare exact <code>issuer</code> |
| Browser redirects to <code>keycloak-it:8080</code> and cannot reach it | Docker service hostname only exists inside network | Design a browser-reachable public hostname |
| <code>redirect_uri_mismatch</code> | Portal port/host/path does not match registration | Compare exact callback |
| <code>invalid_client</code> | Wrong client secret/auth method | Check test client and registration |
| <code>unauthorized_client</code> | Standard Flow disabled or policy disallows | Check OP client settings |
| <code>invalid_scope</code> | Scope not yet allowed for client | Check scopes, client scopes/mappers |
| User logs in then immediately returns to login | SecurityContext/session cookie not persisted | Check cookies, session, filter chain |
| Callback <code>authorization_request_not_found</code> | State repo/session/cookie lost | Check HTTP session/SameSite/proxy |
| Callback state mismatch | Wrong session, concurrent flow, or altered state | Never skip state validation |
| <code>invalid_grant</code> at Token Endpoint | Code expired/reused, redirect URI/PKCE mismatch | Check correlation, token request |
| ID Token issuer mismatch | Different hostname, realm, or issuer-uri | Exact issuer, discovery, token claims |
| ID Token signature invalid | Wrong JWKS/key/cache | Check public key and <code>kid</code> |
| Browser reports insecure cookie | Incorrect HTTP/HTTPS/SameSite/Secure config | Adjust test origin/HTTPS |
| Browser test auto-logs into Alice instead of Bob | OP SSO cookie still present | New browser context or account chooser |
| <code>oidcLogin()</code> tests green but E2E fails | Mock does not execute protocol | Add OP + browser integration |
| Test fails only in CI | Docker/network/port/clock/resources | Check runtime constraints & retries |
| Parallel tests flaky | Shared mutable realm/users/session | Isolate realm/container/user |
| Token refresh tests flaky | TTL/sleep/rotation race | Clock/test token lifetime/coordination |
| OP login succeeds but API returns 403 | Scope/audience/role mapping | Inspect access token and Resource Server |

### 26.1. Concrete Investigation Steps

~~~text
Test failure
   |
   +-- Is the provider container ready?
   |       |
   |       +-- No → image, startup logs, realm import, healthcheck
   |       |
   |       +-- Yes → Is Discovery issuer right?
   |                    |
   |                    +-- No → hostname, proxy, mapped port
   |                    |
   |                    +-- Yes → Are ClientRegistration/callback right?
   |                                 |
   |                                 +-- No → client ID, secret, URI
   |                                 |
   |                                 +-- Yes → Authorization request state?
   |                                              |
   |                                              +-- Lost → session/cookie
   |                                              |
   |                                              +-- Present → code/token exchange?
   |                                                           |
   |                                                           +-- Error → PKCE/client credentials
   |                                                           |
   |                                                           +-- OK → ID Token validation,
   |                                                                      SecurityContext/redirect
~~~

### 26.2. What to Log for Safe Debugging?

Example:

~~~text
testRunId=it-2026-11-run42
providerAlias=it-op
realm=it-realm
discoveryStatus=200
issuerMatch=true
loginStage=token_exchange
oauth2ErrorCategory=invalid_grant
correlationId=sample
~~~

Do not log:

~~~text
client_secret
admin_password
user_password
authorization_code
code_verifier
actual state / nonce
id_token / access_token / refresh_token
session cookie
~~~

Do not use raw authorization callback URLs as log labels or public CI artifacts.

## 27. Checklist of Essential Integration Scenarios

| ID | Scenario | Test Type | Key Outcome |
|---|---|---|---|
| IT-01 | Realm/Discovery ready | Testcontainers smoke | Metadata, exact issuer |
| IT-02 | JWKS endpoint reachable | Testcontainers smoke | Valid JWK set |
| IT-03 | Alice authorization-code login | Browser E2E | OIDC principal with right iss/sub |
| IT-04 | Bob login isolated context | Browser E2E | Different subject/session from Alice |
| IT-05 | Protected URL saved request | Browser/MockMvc | Safe redirect after login |
| IT-06 | Invalid password | Browser E2E | No session created |
| IT-07 | Disabled user | Browser E2E | OP rejects |
| IT-08 | Deny consent | Provider-specific E2E | Failure handler |
| IT-09 | Wrong client secret | Token integration | invalid_client |
| IT-10 | Wrong redirect URI | Provider integration | OP rejects |
| IT-11 | Callback state mismatch | OIDC callback integration | Fail closed |
| IT-12 | Wrong ID Token issuer/audience | JWT fixture | Fail closed |
| IT-13 | Bad JWT signature/key | JWT fixture | Fail closed |
| IT-14 | UserInfo unavailable | Stub/provider | Error handling |
| IT-15 | Refresh success | Token integration | Token state updated for right principal |
| IT-16 | Refresh invalid_grant | OP/stub | Cleanup/reauthorize per policy |
| IT-17 | Refresh rotation race | Multi-node fixture | Does not delete new token |
| IT-18 | Local POST logout | Browser/MockMvc | Session invalidated + CSRF |
| IT-19 | RP-Initiated Logout | Provider-specific E2E | OP SSO behavior |
| IT-20 | Back-Channel Logout | OIDC feature integration | Logout Token verified, session mapped |
| IT-21 | Two providers, same email | Multi-realm E2E | Does not mis-link identity |
| IT-22 | Cluster callback across nodes | Multi-instance integration | Shared session/state |
| IT-23 | Token audience/scope mismatch | Resource Server integration | Proper 401/403 |
| IT-24 | OP temporarily unavailable | Fault injection | Safe failure/bounded retry |

You do not need to run all scenarios on every pull request if cost is high: you can split into a fast integration suite and a nightly compatibility suite. However, **never strip security-critical assertions** from the selected tests.

## 28. Common Mistakes When Setting Up a Test OP

### 28.1. Using Production Accounts to Be "Realistic"

Wrong because it leaks credentials, personal data, and can cause side effects. Use synthetic accounts and an isolated sandbox.

### 28.2. Hardcoding Secrets in the Application Production Profile

A fixture secret may only exist in restricted test configuration. Never use the same secret in the real product.

### 28.3. Only Mocking OidcUser and Calling It an OIDC Integration Test

A mock principal does not exercise Discovery, the Token Endpoint, or ID Token signature verification. Label tests accurately.

### 28.4. Disabling Issuer Validation to Avoid Docker Hostname Errors

Unacceptable. Fix the test provider's public hostname/issuer instead.

### 28.5. Overly Broad Wildcard Redirect URIs

A broad callback wildcard risks sending codes to unintended hosts/paths. Use exact URIs and dynamic client provisioning if test ports are dynamic.

### 28.6. Using Password Grant to Test Browser Login

ROPC does not reflect Authorization Code/OIDC flow and does not properly test state, consent, SSO cookies, callbacks, or PKCE.

### 28.7. Reusing Browser Contexts Across Accounts

An OP SSO cookie may silently re-authenticate Alice, causing Bob's test to fail or falsely pass. Isolate contexts; only reuse them in explicit SSO/account-switch scenarios.

### 28.8. Using a Shared Mutable User in Parallel Tests

Tests that revoke/disable/update consent can affect other tests. Isolate accounts or realms.

### 28.9. Printing Tokens to Logs for Debugging

Never print JWTs/authorization codes/refresh tokens to CI logs. Only log redacted metadata and correlation IDs.

### 28.10. Testing One OP and Claiming Compatibility with All Providers

Keycloak only represents the behavior of the chosen Keycloak version/fixture. Other production OPs may differ in consent, account chooser, UserInfo, logout, refresh rotation, and token claims.

## 29. Practice Exercises

### Exercise 1 — Unit Test or Integration Test?

A test calls:

~~~java
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

**Question:** Does this verify issuer discovery and ID Token signatures?

**Answer:** No. This is a test with a mock principal, suitable for controller/security authorization, and does not run the authorization-code flow.

### Exercise 2 — Realm Fixture

**Requirement:** Create realm <code>it-realm</code>, Client ID <code>portal-it</code>, test users Alice/Bob, and an exact callback URI.

**Suggested Answer:** Write a realm import JSON at <code>src/test/resources/oidc/realm-integration.json</code>; avoid manual clicking on every CI run.

### Exercise 3 — Issuer Mismatch

Discovery returns:

~~~text
http://localhost:49152/realms/it-realm
~~~

The app configures:

~~~text
http://keycloak-it:8080/realms/it-realm
~~~

**Answer:** The two issuer strings differ. Fix the hostname/public URL so Client config, Discovery, and ID Token <code>iss</code> are consistent. Do not disable validation.

### Exercise 4 — Redirect URI

The OP only allows:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

The browser accesses the Portal via:

~~~text
http://127.0.0.1:18080
~~~

**Answer:** The redirect URI may fail to match due to the different hostname. Use the exact registered URI or provision the test client for the actual origin.

### Exercise 5 — Wrong Client Secret

The OP returns <code>invalid_client</code> during code exchange.

**Answer:** Check the Client ID, secret, and client authentication method. Do not treat it as a wrong user password error.

### Exercise 6 — Disabled User

**Requirement:** Log in with <code>disabled.test</code>.

**Answer:** The OP must not issue a normal authenticated login; the Portal must not create an <code>OidcUser</code> from unverified claims.

### Exercise 7 — Testing Account Switch

Alice is logged in, and then you want to select Bob in the same browser.

**Answer:** Local logout does not automatically clear the OP SSO cookie; use provider-supported account-selection/reauth profiles or a fresh browser context depending on the test objective.

### Exercise 8 — Password Grant

**Question:** Why is <code>grant_type=password</code> not a full test of Spring Security OIDC Login?

**Answer:** It bypasses browser authorization redirects, state, nonce, PKCE, consent UI, and the SSO flow.

### Exercise 9 — Callback State Mismatch

**Answer:** Login must fail without creating an authenticated session; do not disable state validation to make the test pass.

### Exercise 10 — JWKS Unavailable

**Answer:** Check network/cert/key URI/JWK cache; never bypass ID Token signature validation when JWKS fails.

### Exercise 11 — Refresh Rotation

Node A uses R0 successfully and saves R1; Node B uses R0 and gets invalid_grant.

**Answer:** Concurrency handling/versioned cleanup is needed so Node B does not delete R1.

### Exercise 12 — Shared CI Account

Two test suites both disable Alice.

**Answer:** The tests are not independent. Use separate realms/accounts or sequential resets with clear ownership.

### Exercise 13 — Local Logout vs OP Logout

**Question:** After POST /logout, the OP still SSOs into Alice—is this definitely a bug?

**Answer:** No. Local session logout differs from RP-Initiated Logout/OP SSO logout.

### Exercise 14 — Role Mapping

The OP returns a Keycloak realm role, but the Portal does not have <code>ROLE_ADMIN</code>.

**Answer:** You must configure protocol mappers/claims and authorities mapping on the Spring Security side. Never assume every realm role automatically becomes a Spring GrantedAuthority.

### Exercise 15 — E2E Artifacts

Browser traces contain callback URLs and cookies.

**Answer:** Redact secrets and restrict access/retention; never upload raw artifacts to public CI reports.

### Exercise 16 — Full Integration Workflow

Follow in order:

1. Create a test-only realm fixture with Client ID, exact callback, and users Alice/Bob.
2. Start local Keycloak via Docker Compose.
3. Verify Discovery <code>issuer</code> and JWKS.
4. Configure Spring Boot <code>issuer-uri</code>, Client ID, secret, and scopes.
5. Run the Portal locally on port 18080.
6. Log in via browser as Alice and verify <code>OidcUser.iss/sub</code>.
7. Use a new browser context to log in as Bob and verify session isolation.
8. Test disabled user and wrong password.
9. Test wrong redirect URI/client secret in a separate fixture.
10. Test state mismatch and ID Token validation using an integration/fault fixture.
11. Test saved request redirect after login.
12. Test local logout and RP-Initiated Logout if the OP supports it.
13. Run smoke tests using Testcontainers with a random port.
14. Run tests in parallel with independent realms/accounts.
15. Collect logs/metrics free of tokens, passwords, state, or session cookies.
16. Clean up containers and test data upon completion.

**Synthesis Question:** Why must we distinguish between a **successful provider discovery** test, an **<code>oidcLogin()</code> with mock principal** test, and a **successful browser authorization-code login** test?

**Answer:** They test different layers: metadata/network, Spring Security authorization/controllers, and the full OIDC protocol/session flow. No layer completely substitutes for the other two.

## 30. Summary

- **OIDC Client integration tests require a reliable test provider**, not just a mocked <code>OidcUser</code>.
- You can use a Keycloak container, a sandbox OP, or HTTP stubs; each tool has a distinct testing scope.
- **Realm, client, test users, scopes, and redirect URIs** should be declared via versioned fixtures, not manual Admin Console clicks.
- The test provider must have a dedicated issuer, dedicated Client ID, dedicated secrets, synthetic users, and never touch production APIs/databases.
- Use Authorization Code Flow via a browser to test real login; **never use password grant/ROPC** as a substitute.
- OIDC Discovery, exact issuer, Token Endpoint, JWKS, ID Token signature/issuer/audience, and state/nonce/PKCE must all be verified properly.
- With Testcontainers random host ports, **the public issuer URL, Discovery issuer, and token <code>iss</code> must match**; do not disable issuer validation to fix hostname errors.
- Callback redirect URIs must be registered exactly at the OP, especially when the Portal runs on a random port or inside a different Docker network than the browser.
- Test accounts should cover multiple subjects/permissions/statuses; any test that mutates a user/session must have explicit isolation/cleanup.
- Browser E2E requires clean browser contexts to avoid SSO cookies from earlier tests, unless intentionally testing switch-account/SSO reuse.
- A real Keycloak instance fits standard flows; stubs/fault injection are useful for malformed JWTs, HTTP 503, JWKS outages, and errors hard to produce in the OP UI.
- A Testcontainers Discovery smoke test **is not automatically an OIDC login integration test**.
- Session, SavedRequest, AuthorizedClient, and OP SSO session are distinct states; test the lifecycle of each.
- Local logout does not automatically imply OP logout; back-channel logout requires a signed Logout Token and session mapping where applicable.
- CI must pin images/dependencies, control Docker/runtime, isolate tests, and govern secrets, logging, and artifacts for reproducible results.

### References

- **Spring Security Reference — OAuth2 Login (Servlet):** ClientRegistration, authorization request, callback, OIDC Login.
- **Spring Security Reference — OAuth2 Client:** authorized clients, token management, and refresh token flow.
- **Spring Security Reference — Spring Security Test:** <code>oauth2Login()</code>, <code>oidcLogin()</code>, MockMvc integration.
- **Spring Boot Reference — Testcontainers and DynamicPropertySource:** container lifecycle and injected configuration.
- **Keycloak Server Guide — Importing and Exporting Realms:** realm import JSON, client/user fixtures, and server startup.
- **Keycloak Server Guide — Hostname Configuration:** public issuer URL, reverse proxy, and hostname behavior.
- **Testcontainers for Java Documentation — GenericContainer, Wait Strategies, JUnit Jupiter:** ephemeral containers and mapped ports.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token, nonce, issuer, audience, and UserInfo.
- **OpenID Connect Discovery 1.0:** <code>.well-known/openid-configuration</code> and issuer metadata.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, redirect URI, state, and Token Endpoint.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code_verifier/code_challenge.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** OAuth flow hardening, mix-up, and refresh-token security.
- **OWASP Authentication Testing Guide / Session Management Cheat Sheet:** test account isolation, session/cookie security, and login/logout testing.
