# 23.2. Choosing Between In-Memory, Session, or Database Token Storage

In **Spring Security OAuth 2.0/OIDC Client**, a successful login is only part of the problem. The application also needs to decide **where to store authentication state, access tokens, and refresh tokens**, how long to keep them, who can read them, and what happens when the user logs out, the application restarts, or another instance continues the work.

A prototype application running on a single JVM may work fine with `InMemoryOAuth2AuthorizedClientService`. But when deployed across three pods behind a load balancer, using refresh token rotation, or needing to sync data days after the user closes their browser, that choice may no longer fit. Conversely, storing every token in a database is not always optimal: it increases the responsibility of protecting sensitive data, managing schemas, encryption, synchronization, and data cleanup.

This lesson explains and compares three approaches: **in-memory storage**, **HTTP session/WebSession storage**, and **database storage**. The focus is **server-side token storage for an OAuth2/OIDC Client**, not how a Resource Server validates JWTs. Topics include the Spring Security model, Java configuration examples, multi-instance management, refresh token rotation, logout, security, migration strategies, and scenario-based selection.

> **Key principle:** Before asking "where is the token stored?", you must identify **which type of data is being stored**: the pre-callback `OAuth2AuthorizationRequest`, the post-login `Authentication/SecurityContext`, or the `OAuth2AuthorizedClient` holding access/refresh tokens for calling APIs. They have different lifecycles and storage mechanisms.

## 1. The Big Picture: There Is No Single "Token Store"

In an OAuth2/OIDC Login system, multiple states appear at different points in time:

| Data | Purpose | Example | When It Must Exist |
|---|---|---|---|
| `ClientRegistration` | Client ID, grant, endpoints, scopes config | `company-login` | Per application configuration |
| `OAuth2AuthorizationRequest` | Tracks the authorization flow before callback | `state`, PKCE verifier, redirect URI | From redirect until callback completes |
| `SecurityContext` / `Authentication` | Represents the authenticated user in the app | `OAuth2AuthenticationToken`, `OidcUser` | Per login/session policy |
| **`OAuth2AuthorizedClient`** | Holds access token and optionally refresh token with registration/principal | Token for calling Calendar API | Until the token/authorization is no longer needed or valid |
| Business connection | Links internal account to external provider | `account_id`, `connection_status` | Per business lifecycle |
| Audit record | Logs login/link/refresh/revoke operations | Timestamp, result code | Per retention policy |

A complete example:

```text
ClientRegistration
  registrationId = calendar
  grant = authorization_code
  provider = company-op

Authorization Request (temporary)
  state = random...
  redirectUri = https://portal.example.test/login/oauth2/code/calendar
  PKCE verifier / OIDC nonce if applicable

SecurityContext
  Authentication = verified user
  Principal = OidcUser

OAuth2AuthorizedClient
  registrationId = calendar
  principalName = user-782
  accessToken = AT-1
  refreshToken = RT-1 (if issued)

Business Connection
  internalAccountId = a9e...
  externalIdentity = (verified iss, sub)
  status = CONNECTED
```

**These states do not have to live in the same place.** For example:

- Authorization request stored temporarily in `HttpSession`.
- SecurityContext stored in the session.
- Authorized client stored in a JDBC database.
- Business connection stored in a dedicated business table.
- ClientRegistration loaded from `application.yml` or a trusted configuration source.

Therefore, "moving all sessions to Redis" does not automatically mean "all authorized client tokens have been moved to Redis".

## 2. Access Tokens, Refresh Tokens, and ID Tokens Have Different Roles

### 2.1. Access Token

The access token is used to call the **Resource Server**:

```http
GET /v1/calendars HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Access tokens are usually short-lived. With a Bearer token, whoever possesses the token can use it within the permissions accepted by the API, so it must be protected in memory, databases, session stores, and logs.

### 2.2. Refresh Token

The refresh token is used at the **Token Endpoint** to request a new access token, if issued by the Authorization Server. It may have a longer lifetime and high security value.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

A refresh token can **expire, be revoked, be rotated, or trigger reuse detection**. Persisting it durably does not guarantee it will remain valid forever.

### 2.3. ID Token

The ID Token is an OIDC artifact used by the Client to verify the user's identity, containing claims such as `iss`, `sub`, `aud`, and timestamps. **Do not use an ID Token as a Bearer token for downstream APIs**, unless a dedicated protocol/API contract explicitly specifies otherwise—do not treat that as an OAuth2/OIDC default.

### 2.4. Tokens Are Not Identical to a Login Session

```text
HTTP Session / SecurityContext:
  "The user is currently authenticated to the application"

OAuth2AuthorizedClient:
  "The application holds tokens to call a Resource Server under a grant"
```

A user may still have a portal login session while the refresh token for the Calendar API has been revoked. Conversely, a previously user-authorized sync job may hold a valid refresh token even after the current browser session has expired—**if the offline access/consent policy allows it**.

The two lifecycles must be defined independently; do not use the session timeout as the default lifetime for all refresh tokens.

## 3. OAuth2/OIDC Login Lifecycle and Storage Points

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant App as Spring OAuth2/OIDC Client
    participant Sess as Session Store
    participant Authz as Authorized Client Store
    participant AS as Authorization Server
    participant API as Resource Server

    U->>B: Start login
    B->>App: GET /oauth2/authorization/company
    App->>Sess: Save OAuth2AuthorizationRequest (state/PKCE/nonce)
    App-->>B: Redirect to Authorization Endpoint
    B->>AS: User login / consent
    AS-->>B: Callback code + state
    B->>App: GET /login/oauth2/code/company
    App->>Sess: Load and consume authorization request
    App->>AS: POST Token Endpoint (authorization_code)
    AS-->>App: Access token, ID token, refresh token?
    App->>App: Verify OIDC / build Authentication
    App->>Sess: Save SecurityContext per configuration
    App->>Authz: Save OAuth2AuthorizedClient
    App-->>B: Login succeeded
    B->>App: GET /calendar
    App->>Authz: Look up token for user/registration
    App->>API: Bearer access token
    API-->>App: Result
```

There are three clear places:

1. **Before the callback:** the authorization request must be short-lived and bound to the browser.
2. **After the callback:** `SecurityContext` preserves the logged-in user state per policy.
3. **When calling APIs:** the authorized client holds the access token and, if present, the refresh token for the manager to use.

Each type has its own repository; avoid mixing data just because all of them relate to OAuth2.

## 4. Token Storage Abstractions in Spring Security Servlet

In a Spring MVC/Servlet application, common interfaces include:

| API | Primary Responsibility | Characteristics |
|---|---|---|
| `ClientRegistrationRepository` | Look up Client configurations | Not a token store |
| `OAuth2AuthorizedClient` | Authorized client record holding tokens | Contains sensitive credentials |
| **`OAuth2AuthorizedClientService`** | Save/load/remove authorized clients by registration and principal | Does not require `HttpServletRequest` |
| **`OAuth2AuthorizedClientRepository`** | Save/load authorized clients bound to an HTTP request and principal | Takes `HttpServletRequest` and `HttpServletResponse` |
| `InMemoryOAuth2AuthorizedClientService` | Store authorized clients in JVM memory | Easy to use, not durable |
| `JdbcOAuth2AuthorizedClientService` | Store authorized clients via JDBC | Durable when the database is properly managed |
| `HttpSessionOAuth2AuthorizedClientRepository` | Store authorized clients in Servlet `HttpSession` | Ties tokens to the browser session |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Repository that can delegate to a service for authenticated principals and use a fallback repository for unauthenticated principals | Bridge between web requests and service |
| `DefaultOAuth2AuthorizedClientManager` | Manage tokens within Servlet requests | Typically uses a repository |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manage tokens outside Servlet requests | Typically uses a service |

Common point of confusion:

**`InMemoryOAuth2AuthorizedClientService` is not `HttpSessionOAuth2AuthorizedClientRepository`.** Even though both can use RAM, they have **different data scopes and lifecycles**.

### 4.1. Service and Repository Have Different Signatures

`OAuth2AuthorizedClientService` has these core methods:

```java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
```

This presents the core signatures; nullability annotations and exact API details depend on the version.

`OAuth2AuthorizedClientRepository` adds the request/response context:

```java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);

void removeAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
```

**Service** suits scheduled jobs and operations without a browser request. **Repository** suits cases where authorized client access depends on the HTTP session/request.

### 4.2. The Storage Key Is Usually `(registrationId, principalName)`

Example:

```text
("google", "user-782")   -> AT-1, RT-1
("calendar", "user-782") -> AT-2, RT-2
("google", "user-996")   -> AT-3, RT-3
```

Two authorized clients for the same user can belong to two different providers. The same registration with different principals must keep tokens separate.

**Never use only `registrationId` as the key** for per-user access tokens: doing so can cause user B to receive user A's token.

### 4.3. Principal Name Is Not a System-Wide Default Email

`Authentication#getName()` can be derived from `OidcUser`, `OAuth2User`, or a custom principal name. In systems with multiple providers/tenants, you must establish a stable identity and proper tenant partitioning.

Internal account mapping should rely on a verified external identity such as `(iss, sub)` in OIDC, rather than automatically matching by email. However, the **key of the authorized client service** must stay consistent with the principal name used by the framework when saving the token, avoiding uncontrolled renames.

## 5. Comparing the Three Options: Memory, Session, Database

| Criterion | JVM Memory | HTTP Session / WebSession | Database |
|---|---|---|---|
| Servlet example | `InMemoryOAuth2AuthorizedClientService` | `HttpSessionOAuth2AuthorizedClientRepository` | `JdbcOAuth2AuthorizedClientService` |
| Scope | Per process/instance | Per browser session/session context | Shared store, usually registration + principal |
| Across multiple requests | Yes, if same instance and consistent key | Yes, while the same session exists | Yes |
| Across restarts | No | Possibly not; depends on durable session store | Usually yes |
| Multi-instance | Separate per JVM | Requires shared session store or affinity | Can share a database |
| Without HTTP request | Yes, via service manager | Not suitable for a pure session repository | Yes, via service manager |
| Does logout/session removal delete tokens? | Not by default | Session tokens usually disappear with session | Not by default |
| Good for user-delegated offline jobs | Not ideal if restart durability is needed | Usually not | Usually better suited, if provider issues refresh tokens |
| Ease of configuration | Very easy | Medium | Higher: schema, DB, security |
| Risks to watch | State loss, per-node tokens, memory | Cookie theft/session fixation, expiry, session replication | Centralizing many credentials, DB breach, rotation/race |
| Cleanup | Process lifecycle or explicit remove | Session expiry/logout + explicit remove | Needs explicit retention/cleanup |
| Access cost | Low | Low to medium, depending on store | DB I/O, connection pool, schema ops |
| When scaling out | Prone to duplicate token requests | Requires session architecture | Requires concurrency and capacity planning |

This table is a **guideline**, not a rigid law. A memory store can be backed by a distributed cache, and a session can live in Redis. Always distinguish the **API abstraction** from the **physical infrastructure**.

## 6. Option 1: Storing Authorized Clients in Memory

### 6.1. How Does `InMemoryOAuth2AuthorizedClientService` Work?

`InMemoryOAuth2AuthorizedClientService` is an `OAuth2AuthorizedClientService` implementation that stores authorized clients in the RAM of the Spring Boot process.

Characteristics:

- Tokens survive across multiple HTTP requests on the same JVM with consistent principal/registration mapping.
- Requires no database, migrations, or Redis.
- Tokens are lost when the JVM/process restarts or an instance is replaced.
- Two pods have two separate memory stores.
- Does not inherently bind tokens to a specific browser session.
- The service can be used outside HTTP requests via a service-based manager.

That last point is especially important: **an in-memory service can still retain tokens after the user closes the browser tab**, as long as the process is running and holds the record; do not assume it auto-deletes when the cookie/session expires.

### 6.2. Servlet Configuration Example

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class InMemoryTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }
}
```

This configuration creates a **service** storing tokens in-process. When Spring Boot already auto-configures a corresponding service, avoid declaring a duplicate bean that causes injection ambiguity. Depending on the Boot version and how you register beans, auto-configuration may back off when it detects an application-provided bean.

### 6.3. Using Through an Authorized Client Manager Outside HTTP Requests

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientManager serviceClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, authorizedClients
    );

    manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build()
    );

    return manager;
}
```

For the `client_credentials` grant, this is a simple setup for system jobs. Losing the token after a restart is usually harmless as long as the job safely holds Client credentials to request a new token and the Authorization Server does not impose overly tight rate limits.

### 6.4. When Is In-Memory a Reasonable Choice?

- Learning apps, demos, integration tests.
- Single-instance development.
- Client Credentials Grant where tokens can be easily re-issued and durability is unnecessary.
- Systems that do not need to resume user-delegated syncs after restarts.
- Features that do not retain long-lived refresh tokens, with separate session/consent lifecycle design.

### 6.5. When Is In-Memory Unsuitable?

- Need to retain user refresh tokens across deploys/restarts.
- Running multiple pods with distributed load.
- Background jobs must continue syncing daily.
- The Token Endpoint has low rate limits and each instance re-requests tokens too frequently.
- Need clear token audit/lifecycle management or cross-node revocation control.
- Expect session logout to immediately delete all tokens without an explicit cleanup mechanism.

### 6.6. Do Not Create a "String Token Cache" Instead of Spring's Service

```java
// DO NOT DO THIS:
private static String accessToken;
```

A global variable lacks `registrationId`, principal, scope, `expiresAt`, refresh token, and metadata. It creates risks of user mix-ups, expired tokens, and race conditions. If you need in-memory storage, use the `OAuth2AuthorizedClientService` abstraction or a compatible implementation with full lifecycle support.

## 7. Option 2: Storing Authorized Clients in Servlet HTTP Session

### 7.1. `HttpSessionOAuth2AuthorizedClientRepository`

In Servlet MVC, `HttpSessionOAuth2AuthorizedClientRepository` stores authorized clients bound to the HTTP request's `HttpSession`.

```text
Browser A:
  SESSION=A
  -> AuthorizedClient(company) for session A context

Browser B:
  SESSION=B
  -> AuthorizedClient(company) for session B context
```

If Browser A loses its cookie or the session expires, the repository can generally no longer find the token stored in that session. This behavior differs from `InMemoryOAuth2AuthorizedClientService`, which exists independently of the session.

### 7.2. Bean and OAuth2 Login Configuration Example

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSessionTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizedClientRepository authorizedClientRepository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .authorizedClientRepository(authorizedClientRepository)
            )
            .oauth2Client(client -> client
                .authorizedClientRepository(authorizedClientRepository)
            );

        return http.build();
    }
}
```

This is an **explicit session repository selection pattern**. In real configurations with multiple `SecurityFilterChain` beans or multiple repository beans, make sure the same repository is used during login and API calls. Do not paste this snippet alongside another security chain sharing the same matchers without checking ordering.

### 7.3. Does the Session Cookie Contain the Access Token?

With a standard **server-side `HttpSession`** model:

- The browser holds a cookie containing the **session identifier**.
- Tokens and authorized clients live in the **server-side session store**, not embedded directly in the cookie.
- The cookie is not an OAuth2 access token.

However, the session ID is still a sensitive credential: if stolen, an attacker can hijack the session. Therefore, apply `Secure`, `HttpOnly`, appropriate `SameSite`, HTTPS, session fixation protection, and timeout policies.

**Do not treat the session cookie as completely harmless** just because it does not directly contain the token.

### 7.4. When Is a Session Repository Appropriate?

- Portals that mainly call APIs **while the user is online**.
- No background processing required after the session ends.
- Want tokens tied to the session lifecycle.
- Each user/browser session has its own tokens and UX requires re-login after session timeout.
- A consistent, protected session store exists in multi-instance environments.

### 7.5. Limitations to Know

- Session expiration can lose the authorized client even when the refresh token is still valid at the OP.
- `@Scheduled` tasks have no `HttpServletRequest`; a session repository is not a natural abstraction for background jobs.
- Multiple browser sessions for the same user can hold different authorized clients.
- Using local in-memory sessions with non-sticky load balancing can route callbacks or subsequent requests to a node without that session.
- With distributed sessions, you must still account for serialization, network overhead, TTL, and securing the Redis/database session store.

### 7.6. Does Logging Out Automatically Revoke Tokens at the Authorization Server?

**Not by default.** Upon logout:

- The application may invalidate the local `HttpSession`.
- Tokens in the session store may be deleted along with the session.
- The Authorization Server **may still consider already-issued access/refresh tokens valid**.
- Resource Servers may continue accepting an already-issued access token until it expires or is revoked via a provider mechanism.

If revoking access at the IdP is required, perform **token revocation** where supported by the provider, according to policy and RFC 7009. Session logout, OIDC RP-Initiated Logout, and OAuth2 token revocation are **three distinct mechanisms**.

## 8. `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`: A Commonly Misunderstood Bridge

In many Spring Security Servlet configurations, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` acts as a dispatcher:

- For **authenticated principals**, it can delegate saving/loading authorized clients to an `OAuth2AuthorizedClientService`.
- For **unauthenticated principals**, it can use a fallback `OAuth2AuthorizedClientRepository`, typically session-based.

Illustration:

```text
HTTP request
  -> AuthenticatedPrincipalOAuth2AuthorizedClientRepository
      |
      +-- authenticated principal
      |     -> OAuth2AuthorizedClientService
      |         -> InMemory or JDBC
      |
      +-- unauthenticated principal
            -> HttpSessionOAuth2AuthorizedClientRepository
```

### 8.1. Why Does This Matter?

Suppose:

```java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
```

And the framework uses a repository that delegates to the service for authenticated principals. In that case, the user's token **may be stored in the in-memory service**, not solely in `HttpSession`, even though the app logs users in using an HTTP session.

Similarly, if the service is JDBC-backed and the web login repository delegates to that service, tokens after login may reside in the database.

**Do not deduce token storage merely by seeing `HttpSession` or session cookie settings.** Inspect the actual `OAuth2AuthorizedClientRepository` bean and which `OAuth2AuthorizedClientService` it is wired to.

### 8.2. Example Bridge Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Bean
OAuth2AuthorizedClientRepository authorizedClientRepository(
        OAuth2AuthorizedClientService service) {

    return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
        service
    );
}
```

To ensure this bean is used by OAuth2 Login and OAuth2 Client components, wire the repository into the relevant configurations. Avoid declaring an additional `HttpSessionOAuth2AuthorizedClientRepository` of the same type without qualifiers or explicit wiring.

### 8.3. When Should You Use This Bridge?

- You have browser OAuth2 Login, yet want authenticated users' tokens persisted via a service.
- You need one shared storage service for both web requests and background jobs.
- You want to switch from in-memory to JDBC without rewriting controllers that use authorized clients.
- You want a fallback repository for unauthenticated flows.

Do not assume every framework version's default constructor chooses the exact same storage: always check the actual beans and dependency versions.

## 9. Option 3: Storing Authorized Clients in a Database

### 9.1. `JdbcOAuth2AuthorizedClientService`

Spring Security provides `JdbcOAuth2AuthorizedClientService` to implement `OAuth2AuthorizedClientService` over JDBC.

Unlike memory:

- Tokens can survive application restarts.
- Multiple instances can share the same database.
- Background workers can look up authorized clients by registration/principal.
- Storing long-lived refresh tokens **increases security requirements** on the database.
- You must implement schema, migrations, housekeeping, monitoring, and proper access controls.

### 9.2. JDBC Configuration Example

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class JdbcTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate,
            registrations
        );
    }
}
```

This requires Spring JDBC, a `DataSource`, and compatible schema tables. For demos, the bean can talk to the JDBC store directly; in production, manage schemas with Flyway/Liquibase or your organization's migration pipeline.

**Do not declare both `InMemoryOAuth2AuthorizedClientService` and `JdbcOAuth2AuthorizedClientService` as default injection candidates**, unless you intentionally use multiple stores with `@Qualifier` or partitioned configuration.

### 9.3. What Must the Schema Contain?

Spring Security's official JDBC schema has these conceptual components:

```text
oauth2_authorized_client
  client_registration_id
  principal_name
  access_token_type
  access_token_value
  access_token_issued_at
  access_token_expires_at
  access_token_scopes
  refresh_token_value (nullable)
  refresh_token_issued_at (nullable)
  created_at
```

Typically the primary key is `(client_registration_id, principal_name)`.

The token value columns hold **sensitive data**, not just metadata. Note:

- Select the official schema **matching your Spring Security version and database dialect**.
- JDBC types for token bytes, timestamps, and timezones must match the driver.
- You may need to adjust `BLOB`/`BYTEA`/`VARBINARY` per database.
- Do not invent a minimal schema and assume `JdbcOAuth2AuthorizedClientService` can read/write it.
- Use versioned migrations; never enable auto-drop on token tables in production.
- Do not grant `SELECT *` on the token table to personnel or applications that do not need it.

### 9.4. Conceptual SQL Illustration

A **conceptual model example**, not official DDL applicable directly to every dialect:

```sql
-- PSEUDOCODE / CONCEPTUAL SCHEMA
CREATE TABLE oauth2_authorized_client (
    client_registration_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    access_token_value BLOB NOT NULL,
    access_token_expires_at TIMESTAMP NOT NULL,
    refresh_token_value BLOB NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
```

If you create only the columns above, the standard JDBC repository **may fail** because columns and types expected by the implementation are missing. Use the documented/source schema for your library version and test migrations against the target database.

### 9.5. Does JDBC Automatically Encrypt Tokens When Saving?

Do not assume so. `JdbcOAuth2AuthorizedClientService` is a persistence abstraction; **token encryption** requirements must be evaluated independently across:

- Encryption at rest for the database/disk/backups.
- Infrastructure KMS/key management mechanisms.
- Application-layer encryption before writing tokens.
- Proper decryption when the manager needs to use the refresh token.
- Encryption key rotation policies and operational access controls.

A database with encryption at rest enabled can still return plaintext tokens to any database account granted read privileges. Therefore, enforce **least privilege**, auditing, secret management, and strict limits on direct queries.

### 9.6. When Is JDBC Appropriate?

- User-delegated API connections whose refresh tokens must survive restarts.
- Background workers running outside browser sessions.
- Multi-instance deployments needing a shared authorized client store.
- Need control over retention, revocation, and connection state.
- A well-managed database with backups, migrations, and monitoring is available.
- Using Authorization Code Grant with offline access when the provider actually issues suitable tokens.

**Durable persistence does not automatically extend token validity.** After expiration or user revocation, the JDBC row may still exist while the refresh grant returns `invalid_grant`.

## 10. Connecting the JDBC Service to a Web Application

Merely declaring a JDBC service is not enough if web requests are still using a separate session repository.

An intentional configuration pattern:

```mermaid
flowchart TD
    Web["Servlet OAuth2 Login / WebClient"] --> Repo["OAuth2AuthorizedClientRepository"]
    Repo --> Bridge["AuthenticatedPrincipalOAuth2AuthorizedClientRepository"]
    Bridge --> Service["JdbcOAuth2AuthorizedClientService"]
    Job["@Scheduled / background"] --> Manager["AuthorizedClientServiceOAuth2AuthorizedClientManager"]
    Manager --> Service
    Service --> DB["Shared database"]
```

For authenticated principals, the repository can delegate authorized-client storage to the JDBC service. The background manager also uses that service, enabling it to look up **the same record**, provided registration/principal match and the user has granted authorization.

### 10.1. Watch `principalName` Across Web Login and Workers

A common hazard:

```text
Web login saves:
  registrationId = calendar
  principalName  = "user-oidc-782"

Worker queries:
  registrationId = calendar
  principalName  = "account-42"

=> Authorized client not found.
```

Do not patch this by passing an arbitrary principal to the manager. Design a consistent mapping from the internal account/connection to the **actual `principalName` that was saved**.

If a user's `principalName` changes due to a custom `OidcUserService`, plan a migration. Do not automatically treat email as a unique identity when linking multiple OpenID Providers.

### 10.2. Which Tokens Belong in the Database?

Not every token needs to be persisted:

- Short-lived access tokens can live in the authorized client record alongside the refresh token for manager convenience.
- Refresh tokens may need durability if workers must continue after restarts.
- The ID Token may exist in OIDC authentication state, but is not a required part of the `OAuth2AuthorizedClient` API.
- Authorization codes must never be stored long-term; they are short-lived, one-time credentials.
- Client secrets/private keys are **Client authentication credentials** and belong in a secret manager, not mixed into the authorized client table.
- Cookie session identifiers are session management artifacts, not API tokens.

Classify data by purpose instead of creating an `"all_tokens"` table storing every token type in plaintext.

## 11. Reactive WebFlux: Memory, WebSession, and Reactive Persistence

If your application uses **Spring WebFlux**, the storage and manager APIs belong to the reactive stack:

| Servlet | Reactive WebFlux |
|---|---|
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `HttpSessionOAuth2AuthorizedClientRepository` | `WebSessionServerOAuth2AuthorizedClientRepository` |
| `InMemoryOAuth2AuthorizedClientService` | `InMemoryReactiveOAuth2AuthorizedClientService` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSession` | `WebSession` |

Do not inject `HttpSessionOAuth2AuthorizedClientRepository` into a WebFlux `SecurityWebFilterChain`; Servlet and Reactive contracts differ.

### 11.1. WebSession Token Repository

Example creating a `WebSession`-based repository:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.WebSessionServerOAuth2AuthorizedClientRepository;

@Bean
ServerOAuth2AuthorizedClientRepository webSessionAuthorizedClients() {
    return new WebSessionServerOAuth2AuthorizedClientRepository();
}
```

This repository binds authorized clients to `WebSession`. When `WebSession` expires or cannot be retrieved, tokens inside it are no longer available to subsequent requests via the repository.

### 11.2. Reactive In-Memory Service

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Bean
ReactiveOAuth2AuthorizedClientService reactiveAuthorizedClientService(
        ReactiveClientRegistrationRepository registrations) {

    return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
}
```

The concept matches Servlet: the in-memory service does not require an HTTP `WebSession`, but state is lost on process restart. For durable reactive persistence, choose an implementation supporting a database/backend compatible with your **Spring Security version** and non-blocking I/O model. An application can implement `ReactiveOAuth2AuthorizedClientService` itself with token protection, but must never call blocking JDBC directly on the Reactor event loop.

### 11.3. Reactive Authorized Client Manager Outside HTTP Requests

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` uses a reactive service without requiring a browser `ServerWebExchange`.

It is a good fit when:

- Queue consumers process messages.
- Scheduled jobs run periodically.
- Service-to-service tasks use the Client Credentials Grant.
- User-delegated jobs use an authorized client granted by the user and stored per policy.

It **cannot automatically display an OIDC consent screen** in the background. If the refresh token expires or is revoked, user-interactive reauthorization is needed when required by the provider.

## 12. Spring Session and Distributed Session Storage

For multi-instance deployments, one approach is **Spring Session** with Redis or another supported backend. Example:

```text
Browser
  └── SESSION cookie
       |
       v
Load Balancer
  ├── Pod A
  ├── Pod B
  └── Pod C
       |
       v
Shared Redis / session store
```

If all three pods share a compatible session store, the OAuth2 Login callback and subsequent requests can read the same session even when the load balancer routes requests to different pods.

### 12.1. What Does Spring Session Redis Help With?

- Shares Servlet `HttpSession` or Reactive `WebSession` through the corresponding integration.
- Reduces reliance on session affinity as pods scale or restart.
- Centralizes TTL and session lifecycle management.
- Stores the security context and session attributes placed into the session by the framework.
- If the authorized client repository **actually stores in the session**, the authorized client can also persist in that session when serialization and configuration work properly.

### 12.2. What Does Spring Session Redis **Not** Do Automatically?

- It does not turn each JVM's `InMemoryOAuth2AuthorizedClientService` into a Redis store.
- It does not persist tokens the application placed into a separate static map.
- It does not revoke tokens at the Authorization Server when a session is deleted.
- It does not resolve refresh token rotation race conditions.
- It does not replace a database-backed `OAuth2AuthorizedClientService` if web/workers still need tokens after session expiry.
- It does not make cookies/sessions secure if Redis lacks ACLs, TLS, and secret management.

### 12.3. Dependencies and Session Config Example

For a Spring Boot application using Spring Session Redis:

```kotlin
dependencies {
    implementation("org.springframework.session:spring-session-data-redis")
}
```

**Illustrative** connection configuration:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example.test
      port: 6379
```

You must add Redis authentication, TLS, namespace, connection settings, session timeout, serialization, and retention per your environment. Across Spring Boot versions, Redis/Session configuration properties can vary; follow the documentation for your running version.

### 12.4. Sticky Sessions or Distributed Sessions?

| Option | Pros | Limitations |
|---|---|---|
| Sticky sessions | Simple to start, less shared-store I/O | Restarts/failover lose sessions; affinity is not an absolute guarantee |
| Shared session store | Multiple pods read sessions consistently per configuration | Requires Redis/network/serializer/TTL and security |
| JDBC token service | Durable tokens independent of session | Does not replace session store for authorization request/`SecurityContext` |
| Session store + token DB combined | Separates login state from API credentials | More components, requires lifecycle coordination |

An architecture **may need both a session store and a token database**. They solve two different state layers rather than being mutually exclusive in all cases.

## 13. Choosing Token Storage by Business Requirements

### 13.1. Scenario A: Single-Instance Demo

```text
Single Spring Boot instance
  + OAuth2 Login demo
  + calls API while user is online
  + no need for tokens after restart
```

An in-memory authorized client service or session repository can suffice. Prioritize simplicity to focus on the OIDC flow.

Accepted risk: restarts lose tokens/sessions and require logging in and authorizing again.

### 13.2. Scenario B: Web Portal with Short-Lived Sessions

```text
Spring MVC portal
  + user logs in
  + calls API while browser session is active
  + logout/session expiry ends token usage
```

A session repository may fit well, especially when the product has no offline jobs. When scaling out, add a shared session store or an equivalent session architecture.

**Check carefully:** local user logout does not automatically revoke provider refresh tokens. If the goal is ending authorization at the OP, handle revocation separately.

### 13.3. Scenario C: Nightly Calendar Sync Under User Authorization

```text
User connects Calendar via authorization_code + offline consent
  -> app saves authorized client with refresh token
  -> @Scheduled syncs every night
  -> user may have closed the browser
```

Typically requires a **service-backed persistent store** for authorized clients, and a service-based manager for the worker. JDBC or a secure distributed store can fit.

At the same time:

- Only use tokens the user actually authorized.
- Track a `RECONNECT_REQUIRED` state when the refresh token is rejected.
- Provide consent/permission management, unlink, retention, and auditing.
- Do not make session logout delete all offline connections by default if the product explicitly requested offline permissions; communicate ongoing background access clearly.

### 13.4. Scenario D: Service-to-Service via `client_credentials`

```text
System job
  -> OAuth2 Token Endpoint client_credentials
  -> Reporting API
```

If tokens can be re-requested using Client credentials upon expiration, an in-memory service can be reasonable—even for some production services on one pod or independent pods—provided rate limits and policies allow it.

Persistent JDBC is not automatically required in every case because there are no user refresh tokens that must survive restarts.

### 13.5. Scenario E: Multiple Pods and User Sessions

If browser login must work when a load balancer distributes traffic across pods, design session sharing or routing. A JDBC token store **is not enough** to recover an `OAuth2AuthorizationRequest` saved in session if the callback lands without the initial session.

Use a shared session store for login state; use an appropriate token service store for authorized clients.

## 14. Storage Selection Decision Flow

```mermaid
flowchart TD
    A["What do you need to store?"] --> B{"State type?"}
    B -->|AuthorizationRequest / SecurityContext| S["Design HTTP/WebSession + session lifecycle"]
    B -->|OAuth2AuthorizedClient| C{"Need to use tokens outside browser session?"}
    C -->|No| D{"Must tokens survive session expiry?"}
    D -->|No| E["Session repository is an option"]
    D -->|Yes| F["Appropriate service-backed store"]
    C -->|Yes| G{"Must survive restarts / multi-node?"}
    G -->|No| H["InMemory service may fit"]
    G -->|Yes| I["Persistent/shared service: JDBC or suitable backend"]
    S --> J{"Multiple instances?"}
    J -->|Yes| K["Shared session store / routing policy"]
    J -->|No| L["Local session may suffice"]
    F --> M["Define TTL, refresh, revocation, and cleanup"]
    E --> M
    H --> M
    I --> M
    K --> M
    L --> M
```

This diagram is directional. Before making a final choice, verify security, operational, compliance, performance, and resilience requirements.

## 15. Refresh Token Rotation Is an Architecture-Defining Factor

One of the biggest challenges when storing tokens in a database/shared service is **refresh token rotation**.

Suppose an authorized client holds:

```text
registration = calendar
principal    = user-782
accessToken  = AT-1 (expiring soon)
refreshToken = RT-1
```

When refreshing:

```text
Client sends RT-1
Authorization Server returns AT-2 + RT-2
Client must update authorized client:
  accessToken  = AT-2
  refreshToken = RT-2
```

If the database still holds `RT-1`, the next refresh may fail with `invalid_grant`.

### 15.1. Multiple Instances Refreshing the Same Token Concurrently

```mermaid
sequenceDiagram
    autonumber
    participant A as Pod A
    participant B as Pod B
    participant DB as Token Database
    participant AS as Authorization Server

    A->>DB: Load calendar/user-782: RT-1
    B->>DB: Load calendar/user-782: RT-1
    A->>AS: POST refresh_token=RT-1
    AS-->>A: AT-2, RT-2
    A->>DB: Save AT-2, RT-2
    B->>AS: POST refresh_token=RT-1
    AS-->>B: invalid_grant
    Note over A,B: May trigger reuse detection
```

**Shared JDBC storage does not mean "refresh runs only once across the cluster".** Consider:

- Single-flight refresh per `(registrationId, principalName)`.
- Distributed locking when using the same refresh token.
- Versioning/optimistic locking to prevent stale writes.
- Reloading the latest token before concluding a connection is broken.
- A policy for handling token-family revocation when the provider detects reuse.
- Bounded retries; **never retry `invalid_grant` indefinitely with the same refresh token**.

### 15.2. Does In-Memory Avoid Race Conditions?

Not completely. Within the same JVM, two HTTP requests or concurrent jobs can still refresh simultaneously. In-memory storage removes some distributed concerns, but does not guarantee single-flight refresh on its own.

### 15.3. Does a Session Store Avoid Race Conditions?

Also not by default. Two requests from the same browser session or two tabs can trigger concurrent refreshes. If sessions are shared in Redis, multiple nodes can also process the token at the same time.

### 15.4. Are Retries After a Network Timeout Dangerous?

Yes. The Authorization Server may have already processed `RT-1` and issued `RT-2`, while the Client timed out before receiving the response. Resending `RT-1` may be treated as token reuse.

Do not treat the refresh token grant as an idempotent operation. Align your strategy with the provider; in some cases, the new token cannot be safely recovered and the user must reauthorize.

## 16. Handling Revoked Tokens and `invalid_grant`

A durably stored token can still be rejected by the Authorization Server because:

- The user revoked consent.
- An administrator disabled the account or revoked sessions.
- The refresh token hit an absolute or idle expiration.
- Refresh token rotation already replaced the old token.
- Client ID, credentials, or registration changed incompatibly.
- The provider detected token replay.

Per OAuth2, the Token Endpoint may return:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
```

**Do not equate `invalid_grant` with "the database lost the token".** The database may hold the exact token, yet the IdP itself no longer accepts it.

### 16.1. Spring Security Failure Handlers

`OAuth2AuthorizedClientManager` implementations have failure-handling hooks. In many default Servlet manager configurations:

- When authorization succeeds, the updated authorized client is saved via the repository/service.
- When a refresh fails with `invalid_grant`, the stored authorized client may be removed to avoid reusing a broken refresh token.

If an application replaces `setAuthorizationFailureHandler(...)` just to log a line, it may accidentally **lose the default cleanup behavior**. When customizing, understand the manager's contract and design safe cleanup—especially under concurrency.

### 16.2. Resource Server 401/403 vs. Refresh Errors

| Error | Source | Typical Meaning |
|---|---|---|
| `invalid_grant` | Token Endpoint | Refresh grant/code is no longer valid |
| `invalid_client` | Token Endpoint | Invalid Client ID/secret/auth method |
| `invalid_scope` | Token Endpoint | Requested scope is not permitted |
| HTTP 401 `invalid_token` | Resource Server | Access token rejected |
| HTTP 403 `insufficient_scope` | Resource Server | Token lacks required API permissions |

Do not delete every refresh token just because an API returned 403 for insufficient scope; refreshing with the same scope will not magically grant new permissions either.

### 16.3. Separating Business Connection State

Example:

```text
oauth_connection:
  id = connection-42
  internal_account_id = account-7
  registration_id = calendar
  principal_name = user-782
  status = RECONNECT_REQUIRED
```

When a refresh token fails, the application can:

1. Stop retrying the same refresh token.
2. Clean up the broken authorized client safely.
3. Keep **business connection metadata** so the UI knows the user had linked it.
4. Mark the status as `RECONNECT_REQUIRED`.
5. Prompt the user to start a new Authorization Code/OIDC flow when needed.
6. After a valid callback, save the new token and transition back to `CONNECTED`.

Do not delete the entire internal account just because one external API connection was revoked.

## 17. Session Timeout, Logout, and Token Expiry Do Not Coincide

| Event | SecurityContext / Session | OAuth2AuthorizedClient | Authorization Server |
|---|---|---|---|
| Access token expires | Session may remain | Can refresh if credentials exist | Decides whether to issue a new token |
| Refresh token revoked | Session may remain | Credentials are no longer usable | Rejects refresh |
| Browser closes tab | Session may remain | Service-backed client may remain | Does not auto-revoke |
| Local logout / session invalidation | Local `Authentication` removed | Depends on store and cleanup | Does not revoke by default |
| App restart | Local in-memory session may be lost | In-memory service lost; JDBC remains | Tokens at AS remain per policy |
| User selects Disconnect | Per app policy | Should delete matching authorized client | May require calling revocation endpoint |
| OP session expires | Local app session may remain | Refresh may or may not work per policy | Controlled by OP |
| Internal account disabled | App must block via authorization | Token store may retain for audit until cleanup | OP does not necessarily know immediately |

**Separate the three timelines:** local authentication/session, access/refresh token validity, and authorization status at the OP.

### 17.1. Logout Does Not Mean Revocation

- Deleting cookies/sessions does not revoke access tokens already accepted by APIs.
- Deleting an authorized client in the database does not automatically call the Authorization Server.
- Calling OIDC RP-Initiated Logout primarily handles the session at the OP; token revocation behavior depends on the provider.
- Token Revocation (RFC 7009) is a separate mechanism, typically invoked when the Client actively terminates authorization per policy.

If a product requires "log out from all devices", design session invalidation, token revocation, and Resource Server enforcement appropriately—do not just delete one row in the token table.

## 18. Securing Token Data in Each Location

### 18.1. Memory: Prioritize Process Protection

Tokens in memory can be exposed via:

- Heap dumps in debug environments.
- Core dumps/crash reports.
- APM or log serialization.
- Unsecured debug endpoints.
- Remote code execution vulnerabilities in the JVM.
- Overly broad process/container access permissions.

Mitigations:

- Never print tokens during debugging.
- Restrict access to heap dumps.
- Disable or secure remote diagnostics tools.
- Never expose sensitive actuator endpoints to the Internet.
- Enforce process/container isolation policies.
- Never stash tokens in arbitrary static maps with infinite TTL.

### 18.2. Session: Protect Cookies and the Session Store

- `Secure` and HTTPS for session cookies.
- `HttpOnly` to prevent JavaScript from reading cookies.
- `SameSite` compatible with OIDC redirects/callbacks, including `form_post` if used.
- Session fixation protection and session ID rotation management.
- Reasonable session timeout limits.
- Secure the session store (such as Redis) against public access.
- Never write real `JSESSIONID`/`SESSION` values to logs.
- Never share session namespaces across environments/tenants unless explicitly designed.

With server-side sessions, the browser usually holds only an ID cookie, not raw access/refresh tokens. Still, if the cookie is stolen, an attacker can abuse the session's privileges.

### 18.3. Database: Protect Tokens at Rest

- Principle of least privilege for database credentials.
- Encryption at rest for disks, DBs, and backups.
- Consider application-level encryption/KMS for refresh tokens.
- Separate the app's DB account from read-only analytics/admin accounts.
- Restrict who can query `access_token_value` and `refresh_token_value` columns.
- Audit access permissions and schema changes.
- Encrypt backups and enforce proper data deletion policies.
- Rotate secrets for Client credentials and database credentials.
- Keep tokens out of tracing, SQL logs, and unprotected CDC topics.

If you need to look up a token by a key, query by **registration/principal/connection ID metadata**, never by raw token value.

### 18.4. Should You Hash Refresh Tokens Before Storing?

Because the Client must send the **exact plaintext refresh token value** back to the Token Endpoint, storing only a one-way hash is insufficient: you cannot recover the token to use it. Therefore:

- One-way hashing suits mechanisms for **verifying credentials issued by the system itself**.
- For an **OAuth2 Client that must use OP-issued refresh tokens**, protect token readability with encryption and access controls.
- Do not confuse hashed-password storage policies with storing refresh tokens needed to continue an OAuth2 grant.

### 18.5. Is Application-Level Token Encryption Needed?

It depends on your threat model. If database administrators or exposed DB dumps are significant threats, application-level encryption reduces risk, at the cost of extra responsibilities:

- KMS/key rotation.
- Envelope encryption.
- Storing the key version/`kid`.
- Ensuring decryption occurs before the manager uses the token.
- Never placing keys and ciphertext in the same easily accessible location.
- Handling migration/re-encryption workflows.
- Testing performance and failure modes.

Do not assume Spring Security's default JDBC class already provides all required encryption out of the box.

## 19. Is Client/Browser Token Storage a Fourth Option?

This lesson focuses on **backend OAuth2 Clients**, which must be distinguished from SPA/public-client architectures:

- Tokens might be held in browser memory or another mechanism depending on the threat model.
- Storing Bearer tokens/refresh tokens in `localStorage` carries heightened XSS risks.
- `HttpOnly` cookies in a BFF/session architecture normally hold a session identifier, not necessarily an OAuth access token.
- Public clients cannot protect a Client secret the way a confidential backend can.
- Refresh tokens in a browser require strict security constraints under OAuth2 Best Current Practice and provider policies.

Never use "the session store is heavy" as an excuse to move backend refresh tokens into browser JavaScript `localStorage` without an architecture and security review. In a BFF, the backend keeps tokens server-side and the browser holds only a session cookie.

## 20. BFF Design: Session in Browser, Tokens on Server

A typical **Backend for Frontend (BFF)** architecture:

```mermaid
flowchart LR
    Browser["SPA / Browser"] -->|"HttpOnly Secure session cookie"| BFF["Spring BFF"]
    BFF -->|"Auth state"| Session["Session store"]
    BFF -->|"OAuth2AuthorizedClient"| Tokens["Token service / DB"]
    BFF -->|"Bearer access token"| API["Resource Server"]
    BFF -->|"Token Endpoint"| AS["Authorization Server"]
```

The browser never needs to hold the OP's refresh token directly. The BFF:

1. Performs OAuth2/OIDC Login.
2. Maintains the user session.
3. Looks up the authorized client for the right principal.
4. Calls APIs with the Bearer access token.
5. Refreshes tokens when allowed.
6. Returns only necessary business data to the browser.

The session store and token store can both live in RAM for demos, or be split across Redis + database in production. What matters is defining clear ownership and lifecycles.

### 20.1. BFF Does Not Automatically Eliminate All CSRF

Because the browser attaches cookies automatically to requests, the BFF must still enforce CSRF protection on state-changing operations per policy, along with `SameSite`/Origin checks where appropriate. `HttpOnly` cookies do not eliminate CSRF.

### 20.2. Do Not Turn the BFF into an Open Proxy

If the BFF lets the browser specify arbitrary API URLs and then blindly attaches an access token and forwards the request, it creates SSRF and token exfiltration vulnerabilities. Use origin allowlists, fixed routes, and strict redirect controls.

## 21. Multi-Tenant, Multi-Provider, and Principal Keys

A system may serve multiple tenants and multiple OPs:

```text
Tenant A:
  issuer = https://id.example.test/realms/a
  user sub = 100

Tenant B:
  issuer = https://id.example.test/realms/b
  user sub = 100
```

Two identities with the same `sub` from different issuers **are not the same OIDC identity**. If stored token lookup uses a principal key lacking tenant/issuer context, it risks fetching the wrong token.

A sound design can:

- Bind `(verified iss, sub)` to an internal account.
- Use trusted internal account/connection IDs to manage ownership.
- Ensure `principalName` in `OAuth2AuthorizedClientService` matches the identity mapping consistently.
- Never allow tenant A to query tenant B's principals.
- Enforce issuer, audience, and scopes per provider/`ClientRegistration`.

### 21.1. Never Take the Principal from a Query Parameter

Dangerous pattern:

```java
// NEVER select another user's token directly from input:
String principal = request.getParameter("user");
OAuth2AuthorizedClient token =
    service.loadAuthorizedClient("calendar", principal);
```

When retrieving a connection's token, verify that the current user **owns that connection**; the service then queries using the stored, authorized registration/principal.

### 21.2. Use a Connection ID for Business Operations

A model can store:

```text
business_connection:
  id                   = connection-42
  account_id           = internal-account-7
  registration_id      = calendar
  authorized_principal = oidc-user-782
  external_issuer      = https://id.example.test/realms/a
  external_subject     = subject-A
  status               = CONNECTED
```

Raw token values never need to appear in this business table. When the user disconnects, the backend resolves the matching authorized client, removes tokens per policy, and updates the connection status.

## 22. Migrating from Memory/Session to Database

A project often starts with an in-memory store, then adds background jobs or multiple instances. This is a **migration of access rights and sensitive data**, not merely swapping a bean.

### 22.1. Safe Rollout Plan

1. Inventory all `ClientRegistration` entries in use.
2. Identify whether authorized clients currently live in memory, session, or a service.
3. Choose a durable service store and compatible schema migration.
4. Configure repositories/managers to use the new store.
5. Decide how to handle existing sessions/tokens stored under the old mechanism.
6. Reconcile principal names and internal account mappings.
7. Test refresh token rotation as users move across instances.
8. Verify OAuth2 Login callbacks still recover authorization requests properly.
9. Test refresh failures, revoke/logout, reconnects, and multi-node behavior.
10. Add telemetry without logging tokens, and prepare a rollback plan that does not expose credentials.

### 22.2. Can You Migrate Tokens Already Sitting in RAM?

Technically possible if you implement an in-process secure migration, but **rarely necessary or straightforward**. Many teams choose to:

- Roll out JDBC for all new logins/authorizations.
- Let old authorized clients expire per policy.
- Prompt users to reconnect when old tokens are gone, with clear UX.
- Never dump all refresh tokens to CSV files or logs for manual transfer.

For customers requiring uninterrupted background integrations, build a dedicated, tested migration plan with careful handling of rotation and ownership.

### 22.3. Do Not Change the Principal Key Silently

If tokens were previously saved under `principalName=user-782` and after migration the manager queries `account-id-7`, lookups will report "token not found" even though the JDBC row exists. Unify the schema/identity mapping and audit any transition.

### 22.4. A New Token Store Does Not Fix Authorization Request Session Errors

If OAuth2 Login callbacks fail with `authorization_request_not_found` due to lost cookies/sessions, moving authorized clients to JDBC will not fix it. The authorization request must exist **before tokens are issued**. Fix where `state`/PKCE/nonce and session routing are handled.

## 23. Designing Cleanup, TTL, and Retention

A system needs state cleanup policies across multiple layers:

| Data | When to Clean Up? | Risk If Not Cleaned Up |
|---|---|---|
| Pending authorization request | After callback or timeout | Retaining state/PKCE verifier too long, flow confusion |
| Local SecurityContext/session | Logout, timeout, internal revocation per policy | Session remains usable unintentionally |
| Access token record | When authorized client is no longer needed, invalid, or per cleanup policy | Leftover tokens, sensitive data accumulation |
| Refresh token record | Upon unlink/revoke/`invalid_grant`, per consent/retention | Long-lived credentials linger unnecessarily |
| Business connection | Disconnect, account deletion, retention policy | Stale UI status, dangling links |
| Audit logs | Per compliance policy | Indefinite retention of personal data |
| Cached principal/roles | When permissions change or TTL expires | Revoked permissions remain cached |

### 23.1. Do Not Over-Simplify Cleanup by Deleting "All Expired Tokens"

An authorized client with an expired access token but a **valid refresh token** may need to stay so the manager can refresh it. If a housekeeping query deletes every row where `access_token_expires_at < now()`, it can accidentally wipe out refresh tokens users need for offline jobs.

Distinguish between:

- Access token expired.
- Refresh token absent/expired/invalid.
- Business connection revoked/disconnected.
- Whether the authorized client is still needed.
- Provider policies and timelines that may not be fully captured in the DB.

### 23.2. Do Not Assume Refresh Tokens Share the Access Token TTL

OAuth2 token response `expires_in` usually describes the access token. Refresh token lifetimes are governed by provider policy and are not always returned as an explicit expiry. Storing `refresh_token_issued_at` alone is insufficient to compute exact lifetime if the provider does not publish its policy.

### 23.3. Database Backup Retention

Even after deleting tokens from production tables, older backups may still contain credentials until backup retention expires. Protect backups, design expiration/rotation, and maintain appropriate incident response procedures.

## 24. Performance and Operational Costs

### 24.1. Memory Is Fast, Not Free

- Every authorized client consumes RAM.
- Growing users/connections can bloat the memory store.
- There is no built-in TTL for all records unless handled by application/storage logic.
- Restarts can trigger bursts of simultaneous token grants.
- Each pod holds separate tokens and requests tokens frequently.

### 24.2. Session Stores Have Network/Serialization Overhead

When using Redis or a session DB:

- Every session read/write can incur network I/O.
- Session objects may include `OAuth2Authentication`/authorized clients requiring serialization.
- Large session payloads increase latency and storage usage.
- Session expiry can drop pending callback state.
- Serialization incompatibility can occur during rolling deployments across versions.

### 24.3. JDBC Services Have Database Overhead

- Queries by registration/principal.
- Updates when refreshing access/refresh tokens.
- Connection pool usage and throughput.
- Migrations, indexes, and backups.
- Encryption/decryption overhead if enabled.
- Locking/contention during concurrent refreshes.
- Row cleanup and sensitive data protection.

Do not assume the token DB is a bottleneck by default: measure actual workloads. Many OAuth2 Clients making infrequent API calls run very efficiently on JDBC. High-throughput systems (many calls/s) should consider caching with invalidation, without introducing unsafe token reuse.

### 24.4. Do Not Measure Performance by Logging Tokens

Track:

```text
registrationId
principalCategory = user/service
tokenAcquisitionCount
tokenRefreshSuccessCount
tokenRefreshFailureCount
tokenEndpointLatency
authorizedClientStoreLatency
api401Count
api403Count
retryCount
```

Never log `access_token_value`, `refresh_token_value`, cookies, authorization codes, or raw OAuth error responses containing credentials.

## 25. Testing Each Approach

### 25.1. Testing the In-Memory Service

- After successful authorization, the same registration/principal retrieves the client.
- Two principals cannot see each other's tokens.
- Two registrations do not overwrite each other.
- Removing `(registrationId, principalName)` does not drop other users.
- Restarting/recreating the service clears data (expected behavior).
- Do not expect in-memory state to sync across separate pods.

### 25.2. Testing the Session Repository

- A browser keeping the same session retrieves the token.
- A different browser session does not receive session A's token.
- Session expiration makes session tokens inaccessible.
- Logout/invalidated sessions behave as configured.
- `Secure`/`HttpOnly`/`SameSite` cookies work with OIDC callbacks.
- Multi-node callbacks work when using a shared session store.
- Pre-callback authorization requests are not lost due to proxy/cookie issues.

### 25.3. Testing the JDBC Service

- Authorized clients persist and reload across restarts.
- Tokens load accurately by principal/registration.
- Refresh token rotation updates to the new token.
- Concurrent refreshes by two workers follow policy.
- Refresh `invalid_grant` triggers proper cleanup.
- No plaintext tokens appear in logs or unprotected backups.
- Database unavailability has clean error handling (never fabricating user tokens).
- Version/schema migrations are tested against a real database.

### 25.4. Testing Security and Ownership

- User A cannot read User B's token by changing `principalName`.
- Tenant A cannot read Tenant B's authorized clients.
- Tokens for API A are never sent to API B's host.
- Logout/revocation removes only the intended tokens/sessions per policy.
- Users can reconnect if a refresh token is revoked.
- Background workers never use a user's token without consent.
- Backups and logs never expose live tokens.

## 26. Troubleshooting: Misidentifying the Storage Mechanism

| Symptom | Common Cause | Check and Fix |
|---|---|---|
| User must reconnect after restart | Tokens live in an in-memory service | If durability is needed, use a shared/persistent service |
| Flaky logins across multiple pods | Local sessions, callback hits a different node | Shared session store or proper routing |
| JDBC table exists, yet user tokens never appear | Web repository still saves to session or another in-memory service | Inspect repository and service wiring |
| Job cannot find web login token | Different `principalName` or different store | Align key/storage, verify ownership |
| Background job still calls API after logout | Tokens in JDBC service were not deleted/revoked | Clarify logout vs. disconnect policy |
| Session expired, yet JDBC token remains | Two independent lifecycles | Clean up connections/tokens per policy |
| API returns 401 despite access token in DB | Token revoked/wrong audience/expired | Check Resource Server and token lifecycle |
| Refresh returns `invalid_grant` | Token revoked/expired/rotated | Do not retry forever; clean up/reconnect |
| Two pods refreshing invalidate the token | Refresh rotation race condition | Locking/versioning/single-flight, provider policy |
| JDBC errors right after DB migration | Missing columns/types/wrong schema version | Use official Spring Security schema |
| DB tokens readable in another environment | Inadequate tenant/environment isolation | Separate databases/credentials/configs |
| Redis holds session, yet tokens vanish on restart | Authorized client actually lives in an in-memory service | Distinguish session store from token service |
| Token leaked in logs | Printing raw objects/HTTP headers/JDBC bind parameters | Redaction and restricted logging |
| No refresh token after OAuth2 Login | AS did not grant offline access or Client is ineligible | Check consent/grant/provider |
| API returns 403 insufficient scope | Token lacks required permissions | Request proper scopes; do not refresh endlessly |
| Background worker asks for `HttpServletRequest` | Used a request-based manager/repository | Use a service-based manager for jobs |
| Cookie lost on callback from IdP | `SameSite`/domain/path/proxy/timeout | Check cookies, Redirect URI, and `WebSession` |
| Authenticated user principal changed after upgrade | Custom principal mapping changed | Audited mapping migration |
| Cleanup deleted refresh tokens when only AT expired | Wrong retention query | Separate access expiry from connection lifecycle |

### 26.1. Ordered Debugging Workflow

1. **Identify the token type:** access token, refresh token, ID Token, or session cookie?
2. **Identify the actual storage class:** service or repository; in-memory, JDBC, or session?
3. **Identify the key:** `registrationId`, `principalName`, tenant, and session.
4. **Identify when it disappears:** restart, session timeout, logout, refresh, deploy, or scale-out?
5. **Identify the error source:** Token Endpoint, Resource Server, or OIDC callback?
6. **Check internal connection state:** active, disabled, reconnect required?
7. **Check concurrency:** are multiple pods or requests updating the same token?
8. **Check security:** storage encryption, ACLs, cookies, logs, backups.
9. **Check schema/provider versions:** do beans/repositories match contracts?
10. **Only then pick the fix:** switch storage, adjust TTL, handle refresh/reauthorization, or fix wiring.

Never "fix" issues by disabling `state`, PKCE, nonce, signature verification, or passing raw tokens in URLs.

## 27. Scenario Exercises

### Exercise 1: Token Lost After Restart

An app uses `InMemoryOAuth2AuthorizedClientService`; the user logs in and calls APIs successfully. After a restart, the authorized client is gone.

**Hint:** That is expected behavior for an in-memory service. If tokens must survive restarts, choose a persistent service and plan migration/onboarding accordingly.

### Exercise 2: A Different Session Still Sees the Token

A developer uses an in-memory service keyed by principal name. The user logs out of their local session, logs back in with a new session under the same principal, and the service still holds the authorized client.

**Hint:** The in-memory service is not tied to a specific session. To clear tokens on logout, add explicit cleanup or choose a session-scoped repository per policy.

### Exercise 3: Redis Has the Session, Yet Tokens Disappear

An app uses Spring Session Redis and `InMemoryOAuth2AuthorizedClientService`. After a deploy, the session remains in Redis, yet the API connection vanishes.

**Hint:** Redis stores the session; it does not automatically persist the in-memory service's data. Inspect the actual repository/service wiring and adopt a persistent service if tokens need durability.

### Exercise 4: Job Runs After Browser Closes

A user consented to offline Calendar sync. A nightly job must refresh tokens even though the browser no longer has a session.

**Hint:** A service-backed persistent store suits this better than a session repository; the background manager uses the authorized client granted by the user.

### Exercise 5: Two Users Share a Registration

```text
registrationId = google
principalName  = user-A / user-B
```

Should a single record per registration be used?

**Hint:** No. User tokens must be partitioned by registration + principal/ownership to prevent cross-user access.

### Exercise 6: Access Token Expired, Refresh Still Valid

A housekeeping job deletes all `oauth2_authorized_client` rows whose access token `expiresAt` is in the past.

**Hint:** This can accidentally delete still-valid refresh tokens. Base retention on connection lifecycle/policy, not access token expiry alone.

### Exercise 7: Does JDBC Encrypt Tokens Automatically?

The security team assumes database tokens are application-encrypted because `JdbcOAuth2AuthorizedClientService` is used.

**Hint:** Never assume that. Evaluate encryption at rest, DB read privileges, backups, and custom encryption/KMS as needed.

### Exercise 8: Does Logout Auto-Revoke?

A user clicks Logout and the app deletes the session. The refresh token remains in the database.

**Hint:** Local logout does not imply token revocation at the OP by default. Define clear policies: logout, disconnect, and revoke are distinct actions.

### Exercise 9: Rotation Across Two Pods

Pod A and Pod B read the same `RT-1`. Pod A refreshes successfully and receives `RT-2`; Pod B uses `RT-1` and gets `invalid_grant`.

**Hint:** A shared database does not solve concurrency automatically. Design single-flight/locking/versioning and handle token-family reuse per provider behavior.

### Exercise 10: Reactive vs. Servlet

A `SecurityWebFilterChain` project tries to inject `HttpSessionOAuth2AuthorizedClientRepository`.

**Hint:** Wrong stack. Use `ServerOAuth2AuthorizedClientRepository`/`WebSessionServerOAuth2AuthorizedClientRepository` or an appropriate reactive service.

### Exercise 11: ID Token and API Token

A developer stores `OidcUser#getIdToken()` in the authorized client table and sends it as a Bearer token to call an API.

**Hint:** Wrong purpose. `OAuth2AuthorizedClient` manages access/refresh tokens; the ID Token is for OIDC identity verification.

### Exercise 12: Minimal Choice for a Service Account

A job uses `client_credentials`, runs independently on each instance, can request a fresh access token after restarts, and has no user refresh tokens.

**Hint:** An in-memory service can fit well if AS rate limits/policies and operations allow it. JDBC is not mandatory just because it is production.

### Exercise 13: Session and Callback

A user starts OAuth2 Login on Pod A, and the callback hits Pod B without session state.

**Hint:** This is a pre-token-exchange authorization request error, not a missing JDBC authorized client. Use a shared session store or appropriate session routing.

### Exercise 14: User Principal Changed After Upgrade

A new release switches from `OidcUser.getName()` to an internal ID as `principalName`, while existing JDBC tokens were stored under the old name.

**Hint:** Perform a verified mapping migration. Never bypass ownership checks or guess matches by email.

### Exercise 15: Revocation and Backups

A user disconnects; the app deletes the token from the live DB. Last month's backup still holds the refresh token.

**Hint:** Protect backups, enforce retention policies, and consider revoking tokens at the Authorization Server to reduce exposure from old credentials.

## 28. Pre-Deployment Storage Selection Checklist

- [ ] Distinguished `OAuth2AuthorizationRequest`, `SecurityContext`, and `OAuth2AuthorizedClient`.
- [ ] Verified the service/repository **actually used by the framework**, rather than guessing from bean names.
- [ ] If in-memory: accepted data loss on restart and per-pod isolation?
- [ ] If session: matched user session lifecycle and secured cookies properly?
- [ ] If JDBC: verified schema, migrations, encryption, DB credentials, and retention?
- [ ] If using Redis sessions: understood that an in-memory authorized client service is a separate store?
- [ ] Confirmed whether background jobs are permitted to use user-delegated credentials after session expiry?
- [ ] Verified access/refresh tokens match audience, scope, grant, and consent?
- [ ] Verified principal/registration/tenant ownership?
- [ ] Implemented handling for refresh, rotation, `invalid_grant`, and reauthorization?
- [ ] Controlled concurrent refreshes across multiple nodes?
- [ ] Separated logout, disconnect, and revocation policies?
- [ ] Ensured cleanup jobs do not mistakenly delete still-needed refresh tokens?
- [ ] Avoided storing raw tokens in frontend/`localStorage` outside an evaluated design?
- [ ] Kept access/refresh tokens out of logs, traces, and unprotected backups?
- [ ] Tested multi-instance, restarts, session expiry, database outages, and recovery?
- [ ] Restricted outbound HTTP origins allowed to receive Bearer tokens?
- [ ] Provided `RECONNECT_REQUIRED` signaling when user authorization expires?

## 29. References

1. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): ClientRegistration model, authorized clients, managers.
2. [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): saving/loading/removing authorized clients outside requests.
3. [Spring Security API — OAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html): managing authorized clients within Servlet requests.
4. [Spring Security API — InMemoryOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/InMemoryOAuth2AuthorizedClientService.html): in-memory token store.
5. [Spring Security API — JdbcOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html): JDBC persistence.
6. [Spring Security API — HttpSessionOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizedClientRepository.html): session-based storage.
7. [Spring Security API — AuthenticatedPrincipalOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthenticatedPrincipalOAuth2AuthorizedClientRepository.html): repository delegating storage for authenticated principals.
8. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager for Servlet requests.
9. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager for service tier/background.
10. [Spring Security Reference — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive token stores and managers.
11. [Spring Session Reference](https://docs.spring.io/spring-session/reference/): distributed session management, Redis, and session lifecycle.
12. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): access tokens, refresh tokens, Authorization Code Flow.
13. [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): proactively revoking OAuth2 tokens.
14. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token security, rotation/reuse, and recommendations.
15. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, OIDC session-related semantics, and authorization flow.

## 30. Summary

Choosing between **in-memory, session, or database** token storage depends first on the **type of state being stored** and its **desired lifecycle**:

- **Memory service:** simple, minimal dependencies, great for learning or easily re-acquired tokens; not durable across restarts and not shared across pods.
- **Session repository:** binds authorized clients to the browser session lifecycle, fitting portals that only use tokens while the user is online; requires proper cookies and a shared session store for multi-instance setups.
- **Database-backed service:** fits user-delegated connections and background jobs needing tokens across restarts, but demands schema management, credential protection, cleanup, and refresh concurrency control.

In Spring Security Servlet, distinguish **`OAuth2AuthorizedClientService`** from **`OAuth2AuthorizedClientRepository`** and understand the role of `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`. In WebFlux, use the corresponding Reactive/Server interfaces. **Spring Session Redis only solves session data stored in `WebSession`/`HttpSession`; it does not automatically turn an in-memory OAuth2 client service into a Redis store.**

Finally, picking the right storage **does not automatically solve refresh token rotation, revocation, account ownership, and authorization**. You need a cohesive architecture aligning session lifecycle, token lifecycle, business connection state, security, and operations so the application grants access to the right user, right resource, and right time.
