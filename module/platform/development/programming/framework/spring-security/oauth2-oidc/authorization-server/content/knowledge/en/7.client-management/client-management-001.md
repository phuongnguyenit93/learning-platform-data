# Declaring Clients with Builders and Repositories

> **Chapter: Client Management.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, covering the design, configuration, security, testing, and operations of an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus is on the `RegisteredClient` model, how to build clients with builders, and how to manage them via `RegisteredClientRepository`.

## 1. Why Must an Authorization Server Register Clients?

In OAuth 2.0, a **client** is an application that requests access to resources on behalf of a user or in its own name. The Authorization Server needs to know which clients are allowed to participate, how each client authenticates itself, which grant types it can use, which URIs it can redirect to, and which scopes it can request.

Suppose a system consists of:

- **Authorization Server (AS/OP):** `https://login.example.vn`, issuing authorization codes, access tokens, and ID Tokens when OIDC is enabled.
- **Web client:** `portal-web` at `https://portal.example.vn`, where users sign in via Authorization Code + PKCE; callback `https://portal.example.vn/login/oauth2/code/portal`.
- **Backend worker:** `billing-job`, running on a schedule and calling APIs via Client Credentials, without a user login screen.
- **Public client:** `mobile-app` or SPA, which cannot protect a long-lived client secret like a server can; requires Authorization Code + PKCE and platform-appropriate redirect URIs.
- **Resource Server:** `https://api.example.vn`, validating access tokens and API access permissions.

These are three client types with distinct risks and requirements; **you should not use a single shared configuration for all clients**.

| Question the Authorization Server needs to answer | Configuration component |
|---|---|
| By what value is the client identified? | `clientId` (OAuth `client_id`); `id` is the internal record identifier |
| How does the client prove its identity? | `clientAuthenticationMethods`, `clientSecret`, or another suitable method |
| Which authorization flows can the client execute? | `authorizationGrantTypes` |
| Where can the browser return to? | `redirectUris`; for OIDC logout, `postLogoutRedirectUris` |
| Which permissions is the client allowed to request? | `scopes` |
| Are PKCE and consent required? | `ClientSettings` |
| How long do tokens live, and in what format? | `TokenSettings` |
| Where are these records looked up and stored? | `RegisteredClientRepository` |

**Client registration** is the prerequisite for the Authorization Server to enforce admission policies. It does not automatically grant users permission to call individual APIs; the Resource Server still must validate scopes, audience, and authorization. Nor should client registration be confused with registering **user accounts**.

## 2. The `RegisteredClient` Model: Three Configuration Layers

Spring Authorization Server provides `RegisteredClient` as an immutable object representing a registered client. You construct the object using a **builder**, then store it in a repository.

~~~mermaid
flowchart TB
    Inputs["Information from admin / tenant provisioning<br/>client_id, client type, URIs, scopes, grants"] --> Builder["RegisteredClient.withId(id)<br/>builder"]
    Secrets["Policy-verified credentials<br/>hashed client secret or public key metadata"] --> Builder
    Builder --> Client["RegisteredClient<br/>identity + auth methods + grants + redirects + scopes"]
    Builder --> Settings["ClientSettings<br/>PKCE, consent, client policy"]
    Builder --> Tokens["TokenSettings<br/>TTL, format, rotation policy"]
    Client --> Repo["RegisteredClientRepository"]
    Settings --> Repo
    Tokens --> Repo
    Repo --> AS["Authorization Server<br/>/oauth2/authorize and /oauth2/token"]
~~~

The three groups should be understood separately:

1. **Registration properties** of `RegisteredClient`: `clientId`, `clientName`, `clientSecret`, authentication methods, grants, redirect URIs, and scopes.
2. **`ClientSettings`**: policies applied to the client such as mandatory PKCE (`requireProofKey`) and requiring consent (`requireAuthorizationConsent`). Certain advanced authentication mechanisms have their own settings.
3. **`TokenSettings`**: token issuance policies such as authorization code/access token/refresh token lifetimes, refresh token reuse, and access token format.

**A builder is not a repository.** `RegisteredClient.withId(...).build()` creates an object; you must call `save(...)` or pass it to a repository so the Authorization Server can look up the corresponding record. Nor is `RegisteredClient` a Spring Security `UserDetails`: a client represents an application, whereas `UserDetails` describes a user.

### 2.1. Common Builder Fields

| Builder API | Purpose and notes |
|---|---|
| `.withId(String)` | Sets the internal record `id`; keep it stable when updating the same client |
| `.clientId(String)` | The `client_id` value sent by the OAuth Client; must be unique within the Authorization Server |
| `.clientIdIssuedAt(Instant)` | Timestamp when `client_id` was issued, useful for lifecycle/metadata management |
| `.clientName(String)` | Descriptive name for operations; not used as a credential |
| `.clientSecret(String)` | Typically stores a **hashed string with an algorithm prefix** such as `{bcrypt}...` for confidential clients |
| `.clientSecretExpiresAt(Instant)` | Expiration time of the secret if policy enforces expiration; requires a rotation flow before expiry |
| `.clientAuthenticationMethod(...)` | For example `CLIENT_SECRET_BASIC`, `CLIENT_SECRET_POST`, `NONE`; choose according to client type |
| `.authorizationGrantType(...)` | For example `AUTHORIZATION_CODE`, `REFRESH_TOKEN`, `CLIENT_CREDENTIALS` |
| `.redirectUri(String)` | Callback URI used at the authorization endpoint; only register trusted URIs |
| `.postLogoutRedirectUri(String)` | URI after OIDC RP-Initiated Logout; controlled separately from login callbacks |
| `.scope(String)` | Scope the client is allowed to request, such as `openid`, `profile`, `orders.read` |
| `.clientSettings(ClientSettings)` | PKCE, consent, and client-level policies |
| `.tokenSettings(TokenSettings)` | Lifetimes, formats, and token policies |

A single client can have multiple grant types, redirect URIs, scopes, and so on by calling builder methods multiple times. **Being registered does not mean every combination is valid:** for instance, Client Credentials has no user interaction and does not issue an OIDC ID Token; authorization code requires a callback, state/PKCE, and appropriate authentication.

## 3. Example: Declaring a Confidential Web Client with a Builder

### 3.1. Registration Design

The `portal-web` client is a server-side Spring Boot application capable of protecting a client secret. Users are redirected to the OP to sign in. Proposed configuration:

| Setting | Illustrative value |
|---|---|
| `client_id` | `portal-web` |
| Client authentication | `client_secret_basic` |
| Grant types | `authorization_code`, `refresh_token` |
| Redirect URI | `https://portal.example.vn/login/oauth2/code/portal` |
| OIDC post-logout redirect | `https://portal.example.vn/signed-out` |
| Scopes | `openid`, `profile`, `orders.read` |
| Client settings | Require PKCE, require consent |
| Token settings | Authorization code 5 minutes, access token 10 minutes, refresh token 8 hours (policy example) |

The Java snippet below illustrates the Spring Authorization Server 1.x and Spring Security 6.x APIs. Use dependency versions compatible with your project's Spring Boot version; check the actual API if your project is on a different major version.

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient webClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientName("Portal Web")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .postLogoutRedirectUri("https://portal.example.vn/signed-out")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .authorizationCodeTimeToLive(Duration.ofMinutes(5))
                    .accessTokenTimeToLive(Duration.ofMinutes(10))
                    .refreshTokenTimeToLive(Duration.ofHours(8))
                    .reuseRefreshTokens(false)
                    .build())
            .build();
}
~~~

This is a **factory method** meant to be placed inside a Java class, not a standalone runnable file. The TTLs are illustrative policy decisions and must be adjusted based on API sensitivity, session lifetime, and revocation capability. `reuseRefreshTokens(false)` requires issuing a new token according to policy when a refresh token is used; the client must store and replace the refresh token properly rather than assuming an old refresh token can be reused indefinitely.

**Why set `requireProofKey(true)` even though the client has a secret?** PKCE binds the authorization code to the party that initiated the transaction, adding protection if the code is intercepted. The secret authenticates the client at the token endpoint, but it does not replace PKCE, `state`, or redirect URI matching.

### 3.2. Corresponding Spring Security Client

This configuration belongs to the **`portal-web` application** running at `https://portal.example.vn`, not to the Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-oidc
            client-id: portal-web
            client-secret: ${PORTAL_WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://login.example.vn
~~~

When `{baseUrl} = https://portal.example.vn` and `{registrationId} = portal`, the client builds the callback `https://portal.example.vn/login/oauth2/code/portal`. The redirect URI sent in the authorization request must exactly match the registered value; a reverse proxy must supply the accurate public scheme and host. `issuer-uri` allows Spring Security to discover OIDC metadata and endpoints via discovery if the OP has OIDC enabled.

The `PORTAL_WEB_CLIENT_SECRET` secret is the **plaintext value held on the client side**; the Authorization Server stores the **hashed** version of that exact value (Section 5). Do not mix up the secret issued to this client with another client's secret.

## 4. Declaring a Client for Service-to-Service Communication

The `billing-job` worker is a **confidential client** calling APIs using Client Credentials. It authenticates with its own credential, has no browser redirects, and does not use the `openid` scope.

~~~java
static RegisteredClient machineClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-billing-job")
            .clientId("billing-job")
            .clientName("Billing background job")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("invoices.read")
            .scope("invoices.write")
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .build())
            .build();
}
~~~

Corresponding token request (the Base64/credential value is generated by the HTTP tool from `client_id:client_secret`; do not put real secrets in commands or logs):

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic BASE64_CLIENT_CREDENTIALS_REDACTED
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=invoices.read
~~~

The Authorization Server authenticates the client, validates the grant type and scope, and issues an access token according to policy. **There is no authorization code, redirect URI, user consent, or ID Token** in Client Credentials. The Resource Server must still restrict actions by scope, audience, and API business rules; allowing a client to request `invoices.write` does not automatically authorize every write request.

For workloads that can use public keys or certificates instead of a shared secret, consider stronger client authentication methods (such as `private_key_jwt` or mTLS with proper protocol and infrastructure support). The declaration will differ from the `CLIENT_SECRET_BASIC` example.

## 5. Encoding Client Secrets and Creating an In-Memory Repository

### 5.1. Protecting Secrets Appropriately

`RegisteredClient.clientSecret` in Spring Authorization Server should be a **hashed** string using a `PasswordEncoder` that supports matching, such as `{bcrypt}...`. The Authorization Server does not need to decrypt the client secret to issue tokens: it only checks whether the secret sent by the client matches the hash. The plaintext value must reside where the client has access (a secret manager or controlled environment variables), never stored in Git or build artifacts.

Avoid `{noop}my-secret`, guessable secrets, a single secret shared across all clients, or logging `RegisteredClient` or HTTP Authorization headers. Client secrets and JWT/ID Token private signing keys are **two different types of credentials**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.util.StringUtils;

@Configuration(proxyBeanMethods = false)
class ClientRegistryConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder,
            @Value("${PORTAL_WEB_CLIENT_SECRET}") String webSecret,
            @Value("${BILLING_JOB_CLIENT_SECRET}") String workerSecret) {

        // Only check the condition; do not include secret values in the error message.
        if (!StringUtils.hasText(webSecret)
                || !StringUtils.hasText(workerSecret)) {
            throw new IllegalStateException("Missing mandatory client credentials");
        }

        RegisteredClient portal = webClient(passwordEncoder.encode(webSecret));
        RegisteredClient billing = machineClient(passwordEncoder.encode(workerSecret));

        return new InMemoryRegisteredClientRepository(portal, billing);
    }

    // Place the two factory methods webClient(...) and machineClient(...) from sections 3 and 4
    // inside this class.
}
~~~

**Note on code scope:** The `webClient(...)` and `machineClient(...)` methods from the previous sections must be placed in the same class (or a utility class) for the example configuration to compile. A complete Authorization Server also requires a `SecurityFilterChain`, issuer configuration, a user authentication mechanism (for Authorization Code), a `JWKSource`, and authorization/consent services. This snippet only demonstrates **client registration**.

The in-memory repository is suitable for demos, local development, and simple integration tests. Data does not persist across restarts, does not synchronize across multiple instances, and in this example the hash values are regenerated on every startup. The original client secret stays the same, though the `{bcrypt}` hash may differ due to random salting—this is normal behavior. Do not rely on this repository as the production source of client data.

### 5.2. `ClientAuthenticationMethod.NONE` for Public Clients

SPAs and native apps cannot keep a long-lived client secret confidential, because application code and configuration can be read. You can register a public client as follows:

~~~java
RegisteredClient spa = RegisteredClient.withId("registration-frontend-spa")
        .clientId("frontend-spa")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://spa.example.vn/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

For a public client, `clientSecret` is **omitted**—do not use a hardcoded secret and treat it as confidential. The client must use PKCE; token management in browsers/native apps requires additional protections for XSS, sessions, redirects, token storage, and refresh tokens according to the threat model. If a web application can use a **Backend for Frontend (BFF)**, consider keeping tokens on the backend and using protected session cookies.

## 6. How Does `RegisteredClientRepository` Work?

The repository is the lookup and persistence point for client registrations integrated into the Authorization Server. Core interface:

~~~java
public interface RegisteredClientRepository {
    void save(RegisteredClient registeredClient);
    RegisteredClient findById(String id);
    RegisteredClient findByClientId(String clientId);
}
~~~

This is a **simplified API view for explanation**, not a claim that the library class has only those exact three members in every version. During protocol execution:

- A request to `/oauth2/authorize` or `/oauth2/token` sends `client_id`; the Authorization Server looks it up via `findByClientId(clientId)`.
- Administrative tools can use `findById(id)` to access the record by its internal key.
- Controlled provisioning/rotation workflows call `save(RegisteredClient)` to store a new record or update an existing one according to the implementation's mechanics.

~~~mermaid
sequenceDiagram
    participant Admin as Provisioning / Admin
    participant Repo as RegisteredClientRepository
    participant Client as OAuth Client
    participant AS as Authorization Server

    Admin->>Repo: save(RegisteredClient)
    Note over Repo: internal id, client_id, hashed secret, grants, scopes, settings
    Client->>AS: /oauth2/authorize or /oauth2/token, client_id
    AS->>Repo: findByClientId(client_id)
    Repo-->>AS: RegisteredClient or null
    AS->>AS: Validate client authentication, grant, URI, scopes, and policy
    AS-->>Client: Issue token / authorization code or protocol error
~~~

**Do not confuse the client registration repository with other stores:**

| Component | What does it store? | Function |
|---|---|---|
| `RegisteredClientRepository` | Identity, authentication methods, secret hash, redirects, scopes, client/token settings | **Client** identity and policies |
| `OAuth2AuthorizationService` | Authorizations, authorization codes, tokens, and related state | **Authorization/token** lifecycle |
| `OAuth2AuthorizationConsentService` | User consent for a client and approved permissions | **Consent** management |
| `UserDetailsService` / identity provider | Users and credentials/claims from the authentication infrastructure | **End-user** authentication |

Having a `JdbcRegisteredClientRepository` in a project **does not automatically mean** authorization codes, tokens, and consents are persisted durably: you must configure the corresponding services as well. This is critical when running multiple pods.

## 7. Choosing In-Memory, JDBC, or Custom Repositories

| Repository | When it fits | Notes |
|---|---|---|
| `InMemoryRegisteredClientRepository` | Tutorials, unit/integration tests, single-instance demos | Does not survive restarts; changes are not shared across instances |
| `JdbcRegisteredClientRepository` | Production with an RDBMS and durable client management needs | Requires schema/migrations, backups, secure DB access, and a provisioning mechanism |
| Custom `RegisteredClientRepository` | Existing custom client registry, multi-tenant, complex policies, or another data source | Must uphold lookup contracts, tenant isolation, cache/concurrency control, and data security |

### 7.1. Using JDBC in a Spring Boot Application

A bean suitable for projects that already have a `DataSource`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Bean
RegisteredClientRepository registeredClientRepository(DataSource dataSource) {
    return new JdbcRegisteredClientRepository(new JdbcTemplate(dataSource));
}
~~~

**This is a replacement variant for the in-memory bean in Section 5.** Do not register both `RegisteredClientRepository` beans as default candidates without an explicit bean selection rule. With JDBC you must:

1. Add Spring JDBC and the appropriate database driver.
2. Create the schema for the client registration table using **controlled migrations** (Flyway, Liquibase, or an equivalent tool). Use the documentation/SQL schema matching **the exact Spring Authorization Server version** you are running; verify column types, lengths, JSON/LOB types, and SQL dialect.
3. Configure the DataSource via a secret store, least-privilege DB permissions, TLS, and backups per policy.
4. Create client records via a governed provisioning/migration tool with a unique `clientId`, stable internal `id`, and appropriate secret hash.
5. Separately configure the authorization and consent storage services if multi-instance operation or restart recovery is needed.

You should not run code that "re-seeds all clients" on **every startup** and overwrites existing secrets, redirects, and token settings. In a multi-pod environment, that behavior can break client logins or unintentionally alter permissions.

### 7.2. Provisioning a Client Once via Repository

Suppose `repository` is JDBC-backed and `client` is an object constructed from a governed client issuance process:

~~~java
RegisteredClient existing = repository.findByClientId("portal-web");

if (existing == null) {
    repository.save(client); // Only use in controlled provisioning commands.
} else {
    // Do not blindly overwrite a record that is in active use.
    // Verify owner, policy, and version before deciding to update.
}
~~~

The code above expresses only basic **idempotent intent** and does not by itself resolve race conditions if two provisioning processes run concurrently. Use a unique constraint on `client_id`, transactions, and an appropriate versioning/synchronization workflow; do not treat check-then-insert as a complete solution for concurrent writes.

For an existing record, `RegisteredClient` is immutable: use `RegisteredClient.from(existing)` to obtain a builder for intentional field updates, then call `repository.save(updated)`. You must consider in-flight data, rules for changing URIs, scopes, secrets, and concurrent operations.

### 7.3. Key Properties of a Custom Repository

If storing clients in a custom table or fetching from a secret/config service, the implementation must:

- Return the exact `RegisteredClient` by `id` and `clientId`, handle not-found cases per contract, and never infer IDs from untrusted request data.
- Guarantee uniqueness of `clientId` and isolation between tenants and environments; avoid returning another tenant's client when local IDs collide.
- Maintain persistence/consistency and visibility of changes across instances; if caching is used, enforce appropriate TTL/invalidation when revoking clients.
- Preserve all grant types, authentication methods, redirect URIs, scopes, `ClientSettings`, and `TokenSettings`, without dropping fields during serialization/deserialization.
- Never store plaintext client secrets when only hash matching is needed. Protect repository contents, audit changes, and limit logging of sensitive data.

## 8. Building a Client Provisioning and Governance Workflow

A practical client provisioning workflow should start from a **business request** to a **reviewed policy**, and only then enter the builder. For example:

~~~mermaid
flowchart LR
    Request["Application team requests<br/>client type + use case"] --> Review["Policy review<br/>grants, authentication,<br/>redirects, scopes"]
    Review --> Credentials["Issue client ID and credentials<br/>over a secure channel"]
    Credentials --> Build["RegisteredClient builder<br/>ClientSettings + TokenSettings"]
    Build --> Repo["RegisteredClientRepository.save"]
    Repo --> Test["Test OAuth2/OIDC flows<br/>positive + negative"]
    Test --> Audit["Audit log: owner, version,<br/>issue date, rotation schedule"]
~~~

### 8.1. Organizational-Level Fields to Manage

Beyond `RegisteredClient`, the governance system should track owner/application, environment, intended purpose, approval ticket, registration date, active status, and rotation schedule. Those fields can live in a separate management table if the standard API does not hold enough metadata. **Do not arbitrarily add custom fields to `RegisteredClient` in examples and expect the standard JDBC repository to persist them automatically.**

Approval rules typically include:

- Allow `authorization_code` only for applications with browser interaction and controlled callbacks; enforce PKCE.
- Issue `client_credentials` only to machine clients with clear identity and ownership; minimal scopes and appropriate TTLs.
- Reserve `ClientAuthenticationMethod.NONE` for legitimate public clients; do not accept hardcoded secrets in SPAs/native apps as a secure authentication mechanism.
- Allow requesting only necessary scopes; clearly define scopes checked by the Resource Server.
- Restrict `redirect_uri` and `post_logout_redirect_uri` per environment with exact scheme/host/path; avoid wildcards and open redirects.
- Review consent policies, refresh tokens, token lifetimes, and client revocation against the threat model.

### 8.2. Updating a Client Secret

When a secret must be rotated, the confidential client must receive the new plaintext secret via a secure channel; the Authorization Server updates the corresponding **hash** in the repository.

~~~java
RegisteredClient existing = repository.findByClientId("portal-web");
if (existing == null) {
    throw new IllegalArgumentException("Unknown client");
}

// newSecret is obtained from a governed workflow/secret store; never hardcode or log it.
RegisteredClient updated = RegisteredClient.from(existing)
        .clientSecret(passwordEncoder.encode(newSecret))
        .build();

repository.save(updated);
~~~

This illustrates an update within a **privilege-protected administrative workflow**, not a public REST endpoint. By default, a `RegisteredClient` has **one** `clientSecret` field; do not assume the server will simultaneously accept both the old secret and the new secret. You need a coordinated client-and-server rollout plan, or a specifically designed overlap mechanism if simultaneous cutover is impossible. Rotating a client secret does **not** automatically revoke all previously issued access tokens and is not the same operation as rotating a private signing key.

### 8.3. Disabling, Deleting, and Revoking

The standard `RegisteredClientRepository` interface focuses on `save`/find and does not define a common `delete`/disable API across all implementations. A governance system that needs to disable clients must design its own policy (for example, an active status in a management layer, changing authentication settings, or blocking at the token flow), while also evaluating previously issued authorizations and tokens.

Cases to consider:

- Disabling a **client** prevents new tokens from being issued per policy, but self-contained access tokens (JWTs) that have not expired may continue to be accepted by the Resource Server until expiration unless a separate revocation check exists.
- Revoking refresh tokens/authorizations must go through supported data mechanisms or revocation endpoints, not merely by editing a field on `RegisteredClient`.
- Raw deletion of DB rows while authorizations/consents still reference the client can leave orphaned data and hinder auditing. A controlled lifecycle termination process is required.

## 9. Secure and Operable Configuration

### 9.1. Common Mistakes When Using Builders

| Mistake | Consequence | Appropriate practice |
|---|---|---|
| `.clientSecret("{noop}secret")` in production | Plaintext or weak secret exposed if DB/logs are accessed | Generate a sufficiently strong random secret, hash with `PasswordEncoder`, protect plaintext on the client |
| Using one `client_id` for web, mobile, and batch jobs | Cannot isolate permissions or revoke individual workloads | Register separate clients per application and trust level |
| Registering `authorization_code` without a redirect URI or with a wrong callback | Authorization/redirect errors, or heightened risk if validation is loosened | Register exact callbacks using HTTPS public URIs |
| Omitting PKCE for clients using the code flow | Increased risk of intercepted authorization codes being used | Set `requireProofKey(true)` and implement code challenge/verifier |
| Registering a public client with a hardcoded secret | Attackers can extract the secret from the distributed app | Use `ClientAuthenticationMethod.NONE` and PKCE |
| Registering every scope for every client | Overly broad access if APIs lack strict policies | Grant scopes on a least-privilege basis and enforce them on the Resource Server |
| Using `openid` for client credentials | Confuses user identity with application identity | Use business scopes and access tokens for M2M |
| Confusing `id` and `clientId` | Failing to look up or identify the client properly | `id` is the record identifier; `clientId` is the OAuth protocol identifier |
| Building a `RegisteredClient` without saving it | The Authorization Server cannot find the client | Pass it to the InMemory repository or `save()` it to a durable repository |
| Seeding clients with a new secret on every startup | Running clients suffer intermittent authentication failures | Provision once, rotate with approval and explicit migrations |
| Implementing JDBC repository only for clients | Tokens/consents do not survive restarts if other services remain in-memory | Configure system-wide persistence as required |

### 9.2. Protecting Environments and Secrets

- Keep plaintext client secrets in a secret store or secure runtime injection mechanism with per-client and per-environment access control; never commit them to `application.yml`, Git, CI artifacts, or Docker images.
- Configure DB/JDBC credentials separately from client secrets; use TLS, least-privilege DB accounts, backups, and auditing on client registration changes.
- Do not log Authorization headers, token request bodies, client secrets, or full `RegisteredClient` objects. Restrict Actuator `/env`, `/configprops`, debug logs, and access to the client store.
- Isolate local/staging/production with independent issuers, redirect URIs, secrets, and policies. `https://portal.example.vn/callback` must not be casually replaced by `http://localhost:8080/callback` in another environment.
- With multiple pods, the repository and authorization/consent stores must remain consistent; check caching behavior when updating or revoking clients.

## 10. Testing Client Registration

Merely constructing a valid builder in a unit test is **not enough**. You must test Authorized and Unauthorized flows on a real Authorization Server or in integration tests. The cases below can use **dummy** clients and secrets in a test environment.

| Test case | Input / scenario | Expectation |
|---|---|---|
| Save / lookup client | Save `portal-web`; `findByClientId("portal-web")` | Returns the exact `RegisteredClient` with grants/scopes/settings |
| Non-existent lookup | `findByClientId("unknown")` | Not found; protocol rejects unregistered requests |
| Confidential authentication | `portal-web` sends valid / invalid client secret at the token endpoint | Valid: proceeds to check grant; invalid: `invalid_client` |
| Authorization Code + PKCE | Request for `portal-web` with valid `code_challenge=S256` | Issues code and exchanges for tokens when state, redirect, PKCE, and client auth are all valid |
| Missing / invalid PKCE | Request for a PKCE-required client without a challenge or with a wrong verifier | Rejected at the appropriate step |
| Wrong redirect URI | Change scheme/host/trailing slash from the registered URI | Does not redirect the authorization code to an untrusted URI |
| Over-privileged scope | Request a scope not included in the client registration | Request is rejected or narrowed per protocol handling and policy |
| Client Credentials | `billing-job` requests `invoices.read` | Obtains an appropriate access token; no login interaction or ID Token |
| Wrong grant | `billing-job` sends `grant_type=authorization_code` | Rejected with `unauthorized_client` / appropriate error |
| Public client | `frontend-spa` uses `ClientAuthenticationMethod.NONE` and PKCE | Code flow is accepted per policy; no secret required |
| Persistence | Save `portal-web` in JDBC, restart the instance | Re-querying returns the same ID, URIs, grants, and settings |
| Rotation | Rotate `portal-web` client secret via administrative workflow | New secret works; old secret is rejected according to the cutover timing |
| Multi-instance | Write client from one node, read from another node | Same client version observed, no unexpected authentication failures |
| OIDC | `portal-web` requests `openid` scope and exchanges a valid code | Receives ID Token; RP verifies `iss`, `aud`, signature, `exp`, and `nonce` when applicable |

### 10.1. Testing the Repository in a Spring Test

The snippet below is a brief unit test idea for the registry, not a full protocol test:

~~~java
@Test
void storesClientWithPkceAndExpectedGrant() {
    PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

    RegisteredClientRepository repository =
            new InMemoryRegisteredClientRepository(
                    webClient(encoder.encode("test-only-secret")));

    RegisteredClient found = repository.findByClientId("portal-web");

    assertNotNull(found);
    assertEquals("registration-portal-web", found.getId());
    assertTrue(found.getAuthorizationGrantTypes()
            .contains(AuthorizationGrantType.AUTHORIZATION_CODE));
    assertTrue(found.getClientSettings().isRequireProofKey());
    assertTrue(encoder.matches("test-only-secret", found.getClientSecret()));
}
~~~

Add JUnit 5, Spring Security, and the corresponding factory/helper imports to the test class. `test-only-secret` here is solely **unit test dummy data**, never used in deployments. This unit test checks mapping and registry storage; it does **not** prove that the token endpoint, user login, PKCE validation, consent, or JWT signing actually work.

### 10.2. Troubleshooting Common Errors

| Symptom | Common cause | How to check |
|---|---|---|
| `invalid_client` at `/oauth2/token` | Wrong secret, wrong auth method, hash missing encoder prefix, unregistered client | Compare `client_id`, authentication method, secret provisioning, and password encoder |
| `unauthorized_client` | Grant type not in client registration | Check `authorizationGrantTypes` and the actual `grant_type` |
| `invalid_redirect_uri` or authorization request error | Redirect URI differs from the registered value | Compare scheme, host, port, path, trailing `/`, query, and proxy configuration |
| Missing ID Token | Client/request does not use `openid` scope or OIDC flow is not enabled | Check granted scopes, OIDC configurer, and signing key |
| Scope rejected | Scope not in `scopes` or consent policy disallows it | Check `RegisteredClient`, request, and Resource Server policy |
| Client disappears after restart | Using in-memory repository | Switch to JDBC/custom persistence and durable provisioning |
| Intermittent failures after rotation | Instances have different cached/seeded secrets or client rollout is skewed | Check shared data source, cache invalidation, and secret cutover timing |
| Client receives token but gets 403 calling API | Access token lacks required scope/audience/API authorization | Inspect the access token against the Resource Server, not just the registry |

## 11. Pre-Production Client Registration Design Checklist

- [ ] Classify clients as web confidential, machine client, or public client with clear ownership.
- [ ] Give each client a unique `client_id` and stable `RegisteredClient.id`; avoid sharing IDs/credentials across environments.
- [ ] Choose appropriate authentication methods and grant types without granting unnecessary flows.
- [ ] Enable PKCE for authorization code, keep redirect URIs exact, and register separate logout URIs if using OIDC.
- [ ] Grant minimal scopes; align with audience and authorization policies on the Resource Server.
- [ ] Store hashes of confidential client secrets, keep plaintext in the client-side secret store, and maintain a rotation schedule.
- [ ] Configure `ClientSettings` and `TokenSettings` according to security, UX, and revocation requirements.
- [ ] Use a durable repository, controlled migrations, and provisioning/rollback/audit processes in production.
- [ ] Persist authorizations and consents durably when a multi-instance architecture requires it.
- [ ] Test lookup, wrong secret, wrong grant, wrong scope, wrong redirect, PKCE, OIDC, restarts, and rotation.

**Self-Check Questions**

1. In `RegisteredClient`, how does `id` differ from `clientId`? Which value does the Authorization Server typically look up when receiving a token request?
2. How does creating a client with a builder differ from `RegisteredClientRepository.save(...)`?
3. Why does `client_credentials` not need a `redirectUri`, whereas `authorization_code` requires a callback URI?
4. If an SPA has a `client_secret` hardcoded in its JavaScript bundle, why is it still a public client?
5. Which steps are affected by `ClientSettings.requireProofKey(true)` and `TokenSettings.accessTokenTimeToLive(...)`?
6. Why is a `JdbcRegisteredClientRepository` alone not enough to ensure all authorization codes, tokens, and consents survive a restart?
7. When rotating a client secret, why must you pay attention to both the rollout timing and previously issued tokens?

## References

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html), especially `RegisteredClient`, `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2AuthorizationConsentService`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html), configuring endpoints and related services.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html), basic client creation and bean examples.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html), client configuration and authentication.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), client registration, client authentication, and grant types.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), PKCE, redirect URIs, and secure management of authorization flows.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252), public native clients and callbacks.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core_1_0.html), `openid` scope, ID Tokens, and identity verification.
