# `OAuth2AuthorizedClient`, Storage, and Access Token / Refresh Token Lifecycle

## 1. Why manage authorized clients?

In **Spring Security Servlet**, an application can act as an **OAuth2 Client**: it requests an access token to call a Resource Server on behalf of a user (authorization code), or for service-to-service communication (client credentials). After receiving the token, the application must associate the token with the right OAuth2 client registration and principal, store the token in an appropriate place, detect expiration, refresh it when permitted, and remove it when access ends.

`OAuth2AuthorizedClient` is the model of **an authorized client**. It holds `ClientRegistration`, the principal name, `OAuth2AccessToken`, and `OAuth2RefreshToken` if present. It is **not** a Spring Security `Authentication`, not merely a registration configuration, and not an OpenID Connect ID token.

Cooperating components:

| Component | Role | Question |
| --- | --- | --- |
| `ClientRegistration` | OAuth2 metadata: registration ID, client ID, grant type, authorization/token URI, scopes | Which provider is the application registered with? |
| `OAuth2AuthorizedClient` | Authorization outcome binding registration, principal, and tokens | Who was granted permission for which client? |
| `OAuth2AuthorizedClientService` | Saves/loads/removes by `(clientRegistrationId, principalName)` | Where does the token live across requests? |
| `OAuth2AuthorizedClientRepository` | Accesses authorized clients in the context of `HttpServletRequest`, `HttpServletResponse`, `Authentication` | Where does a Servlet request get its token? |
| `OAuth2AuthorizedClientManager` | Coordinates loading, authorizing/reauthorizing, saving, and failure handling | When calling an API, does the token need to be issued or refreshed? |
| `OAuth2AuthorizedClientProvider` | Mechanism for each grant (`authorization_code`, `refresh_token`, `client_credentials`...) | Which method is allowed to obtain a new token? |

**Principle:** service/repository **persists state**; manager/provider **orchestrates tokens**. Calling `loadAuthorizedClient()` alone does not automatically refresh an access token.

## 2. Data inside `OAuth2AuthorizedClient`

Logical structure:

```text
OAuth2AuthorizedClient
├── ClientRegistration
│   ├── registrationId = "partner"
│   ├── clientId       = "portal-client"
│   └── authorizationGrantType = authorization_code
├── principalName      = "alice"
├── OAuth2AccessToken
│   ├── tokenValue     = <secret>
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── OAuth2RefreshToken? (nullable)
    ├── tokenValue     = <secret>
    └── issuedAt / expiresAt (if present)
```

Key accessor APIs in Spring Security 6.x:

```java
// Assume client is a preloaded OAuth2AuthorizedClient.
ClientRegistration registration = client.getClientRegistration();
String principal = client.getPrincipalName();
OAuth2AccessToken access = client.getAccessToken();
OAuth2RefreshToken refresh = client.getRefreshToken(); // nullable
Instant expiresAt = access.getExpiresAt();
Set<String> scopes = access.getScopes();
```

This is only a code snippet placed in a scope with a `client` variable and suitable imports (`org.springframework.security.oauth2.client`, `org.springframework.security.oauth2.core`, `java.time`, `java.util`), **not** a standalone Java file. `getTokenValue()` returns a sensitive credential: never put it in logs, JSON returned to the frontend, stack traces, or metrics labels.

The logical key of an authorized client is **registration ID + principal name**. The same `ClientRegistration("partner")` can have separate authorized clients for `alice`, `bob`, and a service principal. Never cache a token in an application-wide static variable and share it across all users.

## 3. Access token, refresh token, ID token, and session

- **Access token:** credential sent to an authorized API, usually via the `Authorization: Bearer ...` header. It has scopes and an expiration time, and can be revoked before `expiresAt`. It is not a user's login password.
- **Refresh token:** credential used to call the authorization server for a new access token without repeating interactive login. A refresh token may not be issued, or may expire, be revoked, or undergo *rotation*.
- **ID token:** identity authentication artifact in OpenID Connect; not automatically a token accepted by a Resource Server.
- **Session/`SecurityContext`:** which user the application recognizes on the current request. Successful login does not mean the user granted all scopes for all external APIs.

With the **authorization code** grant, the provider may issue a refresh token depending on policy/scopes/consent. With **client credentials**, the client typically uses client authentication to request another access token and **does not need a refresh token**. Always code for `getRefreshToken() == null`.

An application can be both an OAuth2 Client (calling external APIs) and a Resource Server (validating incoming bearer tokens). The two roles process two separate sets of tokens and Security mechanisms; never mix tokens from incoming requests with tokens used to call external providers.

## 4. OAuth2 authorization code lifecycle in Servlet

```text
Browser -> /oauth2/authorization/partner
              |
              v
  OAuth2AuthorizationRequestRedirectFilter
              |
              v
    Authorization Server / login / consent
              |
              | callback: authorization code
              v
      OAuth2LoginAuthenticationFilter
              |
              | exchange code for access token, possibly with refresh token
              v
      OAuth2AuthorizedClient created
              |
              v
    AuthorizedClientRepository / Service saves
              |
              v
User calls endpoint requiring partner API access
              |
              v
    OAuth2AuthorizedClientManager
              | reads authorized client of principal + registration
              | uses current token or delegates refresh to provider
              | saves updated entry on success
              v
  Outbound HTTP client sends Bearer token to partner API
```

The framework handles state/redirect/callback/token exchange per configuration. The diagram omits session, CSRF, PKCE, security context, and failure cases to highlight the authorized client lifecycle. The callback must point to the exact public scheme/host behind a reverse proxy; with a wrong `redirect-uri`, the flow can fail before any token is saved.

OAuth2 client registration data is configured **beforehand**; only after the provider grants permission does an authorized client exist for that principal. If the user logs in under one registration while the controller looks up the authorized client under another registration, `load` can return `null`.

## 5. How does `OAuth2AuthorizedClientRepository` differ from `OAuth2AuthorizedClientService`?

### Repository: per Servlet request

The repository takes `Authentication`, `HttpServletRequest`, and `HttpServletResponse`. The logical operations are:

```java
// API illustration, omitting full generics/imports and implementation body:
loadAuthorizedClient(registrationId, authentication, request);
saveAuthorizedClient(client, authentication, request, response);
removeAuthorizedClient(registrationId, authentication, request, response);
```

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` can delegate to `OAuth2AuthorizedClientService` when the user is authenticated and use an HTTP session repository for unauthenticated principals. Exactly which backend is used depends on beans and configuration; never assume every token always lives in the HTTP session.

### Service: by registration ID and principal name

Three core operations:

```java
service.loadAuthorizedClient("partner", "alice");
service.saveAuthorizedClient(authorizedClient);
service.removeAuthorizedClient("partner", "alice");
```

`load` returns `null` if not found. It does not automatically request tokens from the provider. Use the service to persist authorized client state, especially in background jobs or when shared persistence is needed.

| Store | Characteristics | Risks/operations |
| --- | --- | --- |
| `InMemoryOAuth2AuthorizedClientService` | Stored per process, lost on restart | Other nodes cannot see tokens; not suitable for HA if durable state is required |
| `HttpSessionOAuth2AuthorizedClientRepository` | Tied to the Servlet HTTP session | Durability/distribution depends on session store config; depends on cookies/session |
| `JdbcOAuth2AuthorizedClientService` | Uses SQL via `JdbcOperations` and a compatible schema | Must manage tables, backups, encryption at rest, and DB permissions |
| Custom service/repository | Can use an encrypted store or per-tenant DB | Must handle keys, concurrency, revocation, and auditing |

Do not equate an in-memory service with a session. A session can live in a distributed store via Spring Session; an in-memory service lives only in the current JVM.

## 6. Standalone Java 17+ program: saving, loading, and removing dummy tokens

This example does not call any provider, **uses no real secrets**, and always produces the same output. It demonstrates that `OAuth2AuthorizedClientService` only performs storage. It uses the Spring Security OAuth2 Client version managed by Spring Boot 3.3.5.

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.security:spring-security-oauth2-client'
}

application {
    mainClass = 'demo.tokens.AuthorizedClientStoreDemo'
}
```

Create `src/main/java/demo/tokens/AuthorizedClientStoreDemo.java`:

```java
package demo.tokens;

import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

public final class AuthorizedClientStoreDemo {
    public static void main(String[] args) {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("partner")
                        .clientId("demo-client")
                        .clientSecret("only-for-local-demo")
                        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .authorizationUri("https://identity.example.invalid/authorize")
                        .tokenUri("https://identity.example.invalid/token")
                        .scope("profile.read")
                        .build();

        OAuth2AuthorizedClientService service =
                new InMemoryOAuth2AuthorizedClientService(
                        new InMemoryClientRegistrationRepository(registration));

        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-access-value",
                issuedAt,
                issuedAt.plusSeconds(3600),
                Set.of("profile.read"));
        OAuth2RefreshToken refresh = new OAuth2RefreshToken(
                "test-refresh-value", issuedAt);

        OAuth2AuthorizedClient authorizedClient =
                new OAuth2AuthorizedClient(registration, "alice", access, refresh);
        service.saveAuthorizedClient(authorizedClient);

        OAuth2AuthorizedClient loaded =
                service.loadAuthorizedClient("partner", "alice");
        System.out.println("loaded=" + (loaded != null));
        System.out.println("principal=" + loaded.getPrincipalName());
        System.out.println("has_refresh=" + (loaded.getRefreshToken() != null));
        System.out.println("expired_at_fixed_time=" +
                !loaded.getAccessToken().getExpiresAt()
                        .isAfter(issuedAt.plusSeconds(3700)));

        service.removeAuthorizedClient("partner", "alice");
        System.out.println("removed=" +
                (service.loadAuthorizedClient("partner", "alice") == null));
    }
}
```

Run using the project's Gradle wrapper:

```bash
./gradlew run
```

On Windows:

```powershell
.\gradlew.bat run
```

Stdout of the **Java program** (excluding Gradle messages):

```text
loaded=true
principal=alice
has_refresh=true
expired_at_fixed_time=true
removed=true
```

All timestamps are fixed so the output does not depend on the wall clock. Even though the access token is expired relative to the assumed check time, the service still loads the object: **loading data does not refresh it**. `removeAuthorizedClient` deletes the local record and does **not** send a token revocation request to the authorization server. The `.invalid` host intentionally does not exist and is never contacted in this example; Gradle only needs to download dependencies if not yet cached.

## 7. Configuring OAuth2 Client in a real Spring Boot Servlet app

For a web app using OAuth2 Login + OAuth2 Client, declare dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Use a real registration/provider (the example below uses illustrative hostnames; replace them with a real OAuth2 service and store secrets outside source control):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-provider
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          partner-provider:
            authorization-uri: https://identity.partner.example/authorize
            token-uri: https://identity.partner.example/token
            user-info-uri: https://identity.partner.example/userinfo
            user-name-attribute: sub
```

A dedicated `SecurityFilterChain` for OAuth2 login:

```java
package demo.partner;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
```

The `identity.partner.example` URIs are illustrative only and **cannot perform real logins** without a matching provider. This configuration is a standalone class in a **Spring Boot application** with a `@SpringBootApplication` main class, DataSource, and appropriate endpoints if needed; it is not part of the CLI program in Section 6.

After the user authorizes the `"partner"` registration, a controller can receive the authorized client:

```java
package demo.partner;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientStatusController {
    @GetMapping("/partner/status")
    public Map<String, Object> status(
            @RegisteredOAuth2AuthorizedClient("partner")
            OAuth2AuthorizedClient authorizedClient) {
        return Map.of(
                "connected", true,
                "registration",
                authorizedClient.getClientRegistration().getRegistrationId());
    }
}
```

`@RegisteredOAuth2AuthorizedClient` works with OAuth2 Client's resolve/authorize mechanism. If no token exists yet or user consent is needed, the application may need to continue the authorization flow or handle an error, depending on config. The example intentionally does **not** echo the token value back to the browser. Never use `.permitAll()` on endpoints containing user data; enforce proper authorization.

## 8. How does `OAuth2AuthorizedClientManager` coordinate tokens?

An `OAuth2AuthorizedClientManager` can look up an existing authorized client, pass it to matching providers, and persist updated results. For Servlet requests with HTTP request/response, `DefaultOAuth2AuthorizedClientManager` uses a repository.

Illustrative configuration **replacing or supplementing the default manager bean** in an application already configured for OAuth2 Client:

```java
package demo.partner;

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
                        .build();
        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

When `authorize(...)` is invoked at the right time, the `refreshToken()` provider can exchange a refresh token for a new access token if a refresh token is present and the access token needs renewal (including any configured clock skew). The success handler can save the updated authorized client. The failure handler can clear invalid state, e.g., on `invalid_grant` in certain flows, per the active configuration.

**There is no background timer automatically refreshing all tokens merely because `.refreshToken()` is declared.** The manager must be invoked, e.g. through an OAuth2-aware HTTP client or argument resolver. Do not assume tokens stay fresh if the application merely calls `service.loadAuthorizedClient()` and puts the raw token into requests.

When calling APIs with an HTTP client, integrate with Spring Security OAuth2 Client facilities (e.g., `ServletOAuth2AuthorizedClientExchangeFilterFunction` and `WebClient`) to pick the right registration/principal token and persist refreshed tokens. Separate permissions by audience/scope; never pass user A's token into user B's request, and never forward a Bearer token to an untrusted hostname.

## 9. Manager for background tasks and client credentials

`DefaultOAuth2AuthorizedClientManager` fits inside a **Servlet request**. For scheduled jobs or service-to-service calls without a request/session, use `AuthorizedClientServiceOAuth2AuthorizedClientManager` backed by a service:

```java
// Method snippet inside @Configuration, requires importing the used types.
@Bean
OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService service) {
    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());
    return manager;
}
```

`client_credentials` typically obtains a fresh access token using a client secret/private key when needed; do not expect a refresh token. You can invoke:

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("batch-partner")
                .principal("billing-worker")
                .build();

OAuth2AuthorizedClient client = manager.authorize(request);
if (client == null) {
    throw new IllegalStateException("No authorized client for batch-partner");
}
```

This snippet belongs in a class with a `manager` variable and imports for `OAuth2AuthorizeRequest` and `OAuth2AuthorizedClient`; the `batch-partner` registration must be genuinely configured. The `"billing-worker"` principal is the **token storage key of the workload**, not a logged-in user. Choose stable principal names and separate workloads/tenants when privilege levels differ.

## 10. Access token lifecycle

```text
No authorized client yet
    |
    v
Provider executes suitable grant -> access token A1
    |
    v
Manager saves authorized client
    |
    v
Outbound call to Resource Server using A1
    |
    +--> A1 still valid -> continue using
    |
    +--> A1 near/past expiration -> suitable provider
             |--> refresh grant when refresh token exists
             |--> client credentials requests a new token
             |--> authorization code requires user re-authorization
    |
    v
Save updated authorized client or handle failure
```

`OAuth2AccessToken#getExpiresAt()` is metadata about token lifetime. A token can be revoked **before** this timestamp, so `expiresAt` does not guarantee the API will accept the token. Conversely, an HTTP `401` from a Resource Server is not necessarily due to expiration: it may be wrong audience, wrong scope, revoked, invalid signature, or provider policy. Proper response handling and an authorization failure handler are required.

A client may retry on network errors, but must never create an infinite `401 -> refresh -> retry -> 401` loop. Requests with side effects (POST/PATCH) require an idempotency contract before automatic retries. Never keep using an old access token after a new one has been issued simply because a cache held onto a stale object.

## 11. Refresh token lifecycle and rotation

A refresh token is a sensitive credential that allows minting new access tokens. Upon a successful refresh, the authorization server may issue a new pair:

```text
Before: access=A1 (expired), refresh=R1
After:  access=A2,           refresh=R2 (if rotation enabled)
```

The manager/service must store the **updated authorized client**. If the provider does not return a new refresh token, retaining/updating the token follows the contract of the client implementation and provider; avoid assembling tokens manually without control.

When refresh fails, categorize the failure:

| Situation | Appropriate behavior |
| --- | --- |
| `invalid_grant` due to expired/revoked/reused refresh token | Stop retrying with R1, consider removing invalid state, prompt user to reauthorize |
| `invalid_client` or expired client secret | Fix client registration/credentials, alert operations, do not repeatedly ask user to re-login |
| Timeout/5xx from authorization server | Bounded retry with backoff and telemetry; do not delete token immediately on a single network error |
| Access token still valid while refresh token expired | Can continue using access token per policy; next renewal requires reauthorization |
| Refresh token rotated, but another instance overwrites the new token | Handle synchronization/locking or CAS keyed by `(registrationId, principalName)` |

A dangerous race condition: two requests read R1 and both refresh concurrently. Request one receives R2; request two reuses R1 and gets `invalid_grant`. If request two deletes the row just updated by request one, the user loses access unnecessarily. With multiple nodes and refresh token rotation, consider distributed locks, optimistic locking, or centralizing refresh coordination. The default service should not be assumed to solve all cross-replica races automatically.

## 12. JDBC storage when persistence is needed

With multiple instances or survival across restarts, you can configure `JdbcOAuth2AuthorizedClientService`.

Example dependencies for Spring Boot Servlet with PostgreSQL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

In a `@Configuration` class that already has a DataSource:

```java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbcOperations,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
            jdbcOperations, registrations);
}
```

Imports for the method snippet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
```

The bean **does not automatically create tables**. Spring Security provides reference SQL schemas for JDBC authorized clients, but you must include a compatible schema in your migrations (Flyway/Liquibase or equivalent), adjust column types for your database, and test actual read/write/delete operations.

The data holds **access tokens and refresh tokens**, so DB read permissions, backups, SQL logs, encryption at rest, auditing, and retention must be protected like credentials. Never copy raw tokens from production to staging. When multi-tenancy is required, define a clear scoping model: `registrationId + principalName` must prevent collisions between tenants with differing privileges.

## 13. Logout, disconnecting, and revocation differ

| Action | What actually happens |
| --- | --- |
| Spring Security session logout | Ends login/session state per config; does not guarantee tokens at the authorization server are revoked |
| `removeAuthorizedClient(...)` | Deletes the token record from the local repository/service; does not automatically send a revocation request |
| Provider's token revocation endpoint | Requests the authorization server to invalidate the token per provider support and policy |
| Deleting tenant/user from business DB | Changes product permissions; does not automatically purge all authorized clients in caches/backups |

"Disconnect integration" should be designed as a dedicated business operation: locate the right principal/registration, revoke at the provider when supported and needed, clear the local store, check token caches, halt background work, and write an audit log **without token values**. A user logging out of the browser is not necessarily a request to revoke every integration, whereas when they explicitly disconnect, previously issued tokens must no longer be used.

## 14. Common errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| OAuth2 login succeeds, but no authorized client exists | Mismatched registration/principal, different session/repository | Check callback, key, service/repository beans, and current auth |
| Restart loses tokens | In-memory service | Evaluate JDBC/shared store |
| Node A works, Node B fails | Data only in local memory/unshared session | Check session persistence and service backend |
| Expired access token still being sent | Calling `loadAuthorizedClient` and using directly without manager | Configure providers and use the manager |
| Refresh token is `null` | Provider did not issue one, incompatible scope/policy/grant | Read provider contract; handle reauthorization |
| Refresh fails repeatedly with `invalid_grant` | Revoked/expired/rotated refresh token | Remove infinite retries, clear invalid tokens, and prompt re-login |
| Still using old token after refresh | Stale cache or concurrent overwrite | Check repository, success handler, locking/transactions |
| Background job fails with missing Servlet request | Using the Servlet-oriented manager | Switch to `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| User A calls API with User B's token | Wrong principal/cache key | Scope tokens by principal, tenant, and registration |
| Local store cleared, yet token still works | Revocation endpoint not called | Design dedicated disconnect/revocation flow |
| API call returns 401 before `expiresAt` | Audience, revocation, policy, or other token error | Inspect Resource Server response; do not look solely at timestamps |
| Tokens appear in logs/responses | Printing raw objects, SQL bindings, or HTTP debug logs | Redact tokens, restrict logging and access permissions |

A systemic design bug is keying a cache solely by `"partner"` without distinguishing `"alice"` and `"bob"`. If tokens carry user privileges, such a cache can cause cross-identity access. Keys must accurately reflect the principal and environment/tenant across multiple security boundaries.

## 15. Appropriate testing by layer

**Local storage tests** like the Java program in Section 6 prove save/load/remove, keys, and that tokens can persist even when expired. They do not prove refresh grants or OAuth2 callbacks work.

**Refresh tests:** use an authorization server stub or test OAuth2 provider to return new `access_token`, `expires_in`, and `refresh_token`, then simulate `invalid_grant`, timeouts, and rotation. Call via `OAuth2AuthorizedClientManager`; assert the new token is saved, invalid tokens are handled by the chosen handler, and no infinite retries occur.

**Servlet end-to-end tests:** run the authorization-code flow through a test provider, checking HTTP sessions, redirect URIs, repositories, `@RegisteredOAuth2AuthorizedClient`, outbound API calls, and credential scoping. With multiple replicas, simulate concurrent refreshes to verify atomicity.

**Security tests:** no raw tokens in responses/logs; one user/tenant's token cannot be used for another user/tenant; disconnecting leaves no lingering record; backups/logs/databases do not leak credentials.

## 16. Production checklist

Before deploying an OAuth2 Client, verify:

1. Is the grant authorization code/OIDC or client credentials? Are refresh tokens actually issued?
2. Are registration IDs and principal names defined, properly separating tenants and service accounts?
3. Do tokens live in session, process memory, or a shared store? How do restarts and scaling affect them?
4. Do all flows obtaining tokens for outgoing requests go through the right manager/provider?
5. How are expired access tokens, rotated/revoked refresh tokens, and `invalid_grant` handled?
6. Are backoff, retry limits, and multi-node race controls in place?
7. Are client secrets and refresh tokens protected by encryption, storage controls, backups, and safe logging?
8. Is logout distinct from disconnect, and is provider revocation properly designed?
9. Does the HTTP client send tokens only to APIs with matching audiences/hosts over HTTPS?
10. Are success/failure paths tested alongside metrics that never include raw tokens?

## Remember

`OAuth2AuthorizedClient` binds **registration + principal + access/refresh tokens**. `OAuth2AuthorizedClientService`/`Repository` only **stores and retrieves**, while `OAuth2AuthorizedClientManager` and providers **coordinate obtaining and refreshing tokens**. Storage does not auto-refresh, and deleting locally does not auto-revoke at the provider. Understanding those boundaries, picking the right manager for Servlet requests or batch jobs, and controlling refresh-token rotation will prevent most lifecycle bugs and access leaks.