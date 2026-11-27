# 23.6. Distributed Sessions and Synchronizing Authorized Clients Across Instances

## 1. The Problem: Logging In on Instance A, Next Request Hits Instance B

A Spring Security OAuth 2.0/OIDC Client application runs smoothly on a developer's machine as a single process. The user logs in through the OpenID Provider, Spring Security stores the login state and access token, and then the backend calls APIs on the user's behalf.

When deploying to production, operations scales up the number of replicas:

~~~text
                  Load Balancer
                 /             \
           Instance A       Instance B
           Spring Boot      Spring Boot
~~~

A typical failure scenario:

1. The browser starts OIDC Login on **instance A**.
2. A creates an authorization request, stores <code>state</code> in A's session, and redirects to the OpenID Provider.
3. The provider authenticates the user and redirects the callback back to the application.
4. The load balancer routes the callback to **instance B**.
5. B cannot find the authorization request/session that A saved, so it rejects the callback.

If sticky sessions keep the callback on A, login may succeed. Yet another issue emerges:

1. A saves the authorized client containing the access token and refresh token after login.
2. The browser calls <code>GET /reports</code> and the load balancer routes it to B.
3. B restores the login session, yet **cannot find the authorized client** because the token lives only in A's memory.
4. The app throws an error, restarts the authorization flow, or fails to call the Reports API.

A third issue is even more dangerous:

1. A and B both read the same refresh token <code>R0</code> from a shared store.
2. The access token nears expiration, so both send refresh requests to the Token Endpoint concurrently.
3. A receives access token <code>A1</code> and a new refresh token <code>R1</code>.
4. B reuses <code>R0</code> and may receive <code>invalid_grant</code> or trigger refresh-token reuse detection.
5. If B's failure handler unconditionally deletes the record, B may wipe out <code>R1</code> that A just saved.

These three problems are related, yet **cannot be fixed by a single configuration setting**:

- **Distributed sessions**: multiple instances can read HTTP session and `SecurityContext` state.
- **Authorized-client persistence**: multiple instances can access the right access/refresh tokens per `ClientRegistration` and principal.
- **Concurrent refresh coordination**: prevent multiple instances from consuming an old refresh token simultaneously or overwriting newer token state.

> **Core thesis:** Sharing HTTP sessions does not automatically mean tokens are stored in a shared authorized-client service; sharing a token database does not automatically prevent refresh races. You must identify each state store, its sharing scope, and its update coordination mechanism.

## 2. Learning Objectives

After this lesson, you can:

1. Distinguish Web/HTTP sessions, `SecurityContext`, OAuth2 authorization requests, `OAuth2AuthorizedClient`, and refresh tokens.
2. Explain why OIDC callbacks can fail when requests traverse multiple replicas.
3. Implement Spring Session with Redis to share Servlet sessions while understanding the corresponding Reactive WebFlux setup.
4. Use <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, and centralized storage appropriately.
5. Recognize the limits of <code>InMemoryOAuth2AuthorizedClientService</code>, <code>HttpSessionOAuth2AuthorizedClientRepository</code>, and JDBC/Redis storage.
6. Choose the right <code>OAuth2AuthorizedClientManager</code> for Servlet/WebFlux requests and background jobs.
7. Design per-key refresh coordination using locks, state reloads, and conditional updates/deletes.
8. Handle logout, token revocation, session expiry, scale-out, failover, and tenant boundaries safely.
9. Test multi-node behavior without logging real access/refresh tokens.

## 3. Four Types of Data Often Conflated

In a web application using OIDC Login, distinguish **at least four states**.

| State | Typical Data | When Created? | Spring Security Component |
|---|---|---|---|
| **Temporary authorization request** | <code>state</code>, redirect URI, PKCE attributes, nonce/correlation data | When initiating redirect to OP | <code>OAuth2AuthorizationRequestRepository</code> / reactive counterpart |
| **HTTP session and SecurityContext** | Session ID, <code>Authentication</code>, <code>OidcUser</code>/principal, authorities | During or after login | <code>HttpSession</code> / <code>WebSession</code>, `SecurityContext` repository |
| **Authorized client** | `ClientRegistration`, `principalName`, access token, optional refresh token | After token exchange/refresh | <code>OAuth2AuthorizedClientRepository</code> / <code>OAuth2AuthorizedClientService</code> |
| **Permission state at OP/API** | Consent, token revocation, user account, roles, entitlements | Managed by Authorization Server/Resource Server | **Not part of the Client's local HTTP session** |

### 3.1. Authorization Request vs. Authorized Client

Before callback:

~~~text
GET /oauth2/authorization/company
    → state, nonce, PKCE verifier ...
    → save authorization request
    → redirect browser to OP
~~~

After a successful callback:

~~~text
GET /login/oauth2/code/company?code=...&state=...
    → verify state and correlation
    → exchange code at Token Endpoint
    → receive access token / ID Token / refresh token (if any)
    → create Authentication and OAuth2AuthorizedClient
~~~

Do not use the authorization-request repository to store long-term refresh tokens. Conversely, you cannot use a stored access token to **bypass checking <code>state</code>** on a new callback.

### 3.2. SecurityContext vs. Access Token

<code>SecurityContext</code> answers: "Which user is logged into the current application?"

<code>OAuth2AuthorizedClient</code> answers: "Which `ClientRegistration` has been granted tokens for which principal?"

These two objects cannot replace each other:

~~~text
SecurityContext:
    Authentication = user-123, authenticated at portal

OAuth2AuthorizedClient:
    registrationId = company
    principalName  = user-123
    accessToken    = A0
    refreshToken   = R0 (if issued by OP)
~~~

A user can remain logged into the portal even after the access token expires. Conversely, an unexpired access token does not prove the current browser session is still valid.

### 3.3. The Browser Does Not Need to Hold a Confidential Backend Client's Refresh Token

In a Backend For Frontend (BFF) architecture with a confidential OAuth2/OIDC Client, the browser normally holds only a **session cookie**. The backend keeps access/refresh tokens in server-side storage. Never put refresh tokens into custom cookies, `localStorage`, or HTML responses merely so replicas can read the same token.

If your app is a browser-based SPA public Client executing OAuth2 directly, the design differs and requires its own token-protection model; do not mechanically apply this lesson's BFF examples.

## 4. OIDC Login Flow Across Two Instances

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant LB as Load Balancer
    participant A as Instance A
    participant B as Instance B
    participant Sessions as Shared Session Store
    participant OP as OpenID Provider
    participant Tokens as Shared Authorized Client Store

    Browser->>LB: GET /oauth2/authorization/company
    LB->>A: Route to A
    A->>Sessions: Save authorization request + state
    A-->>Browser: 302 Authorization Endpoint
    Browser->>OP: Authorization request
    OP-->>Browser: 302 callback code + state
    Browser->>LB: GET /login/oauth2/code/company
    LB->>B: Route to B
    B->>Sessions: Load authorization request and Web/HTTP session
    Sessions-->>B: Original state/PKCE/nonce
    B->>OP: Token exchange
    OP-->>B: Access token, ID Token (+ refresh token)
    B->>Sessions: Save authenticated SecurityContext
    B->>Tokens: Save OAuth2AuthorizedClient
    B-->>Browser: Post-login redirect + session cookie
    Browser->>LB: GET /reports
    LB->>A: Route to A
    A->>Sessions: Restore Authentication
    A->>Tokens: Load authorized client by registration/principal
    Tokens-->>A: Current token
    A-->>Browser: Authorized content
~~~

This diagram assumes Spring Session and authorized-client storage are configured so all instances see compatible state. Repository details depend on your Servlet/Reactive stack and exact integration.

If you have only shared sessions while tokens remain in a local <code>InMemoryOAuth2AuthorizedClientService</code>, post-login requests may fail to find tokens. If you have only a shared token store while session/correlation stays local, OP callbacks can still fail.

## 5. Are Sticky Sessions Enough?

**Session affinity**, often called sticky sessions, directs the load balancer to route a browser's requests preferentially to the same instance.

Example:

~~~text
Browser 1 → always goes to A
Browser 2 → always goes to B
~~~

This can serve as a temporary workaround for systems without shared sessions, but has clear limits:

| Scenario | Do Sticky Sessions Help? |
|---|---|
| Browser sends consecutive requests while A stays alive | Can maintain local session |
| A crashes or redeploys | No; local state is lost |
| Load balancer changes affinity | Correlation may be lost |
| Another scheduler/service needs the authorized client | Does not solve it |
| A and B share a refresh token | Does not protect concurrency |
| Need high availability during scaling/restarts | Does not replace persistent session/token stores |

**Sticky sessions are a routing strategy, not a data-synchronization mechanism.** When high availability and rolling deployments are required, using a shared session store and proper token storage makes behavior far easier to guarantee, though failure/recovery design is still essential.

## 6. Spring Session: Sharing HTTP Sessions Across Nodes

Spring Session replaces/provides an HTTP session management abstraction so sessions can live outside a single JVM, such as in Redis.

In **Servlet** applications, Spring Session integrates with <code>HttpSession</code>. In **Reactive WebFlux**, Spring Session integrates with <code>WebSession</code>. Both can use Redis, though they do not use the same repository APIs in code.

### 6.1. What Problem Does Spring Session Solve?

~~~text
Unshared:

Instance A memory session = S123
Instance B memory session = (S123 does not exist)

Shared via Redis:

Instance A ──┐
             ├── Redis session namespace ── session S123
Instance B ──┘
~~~

When the browser sends its session cookie, whichever instance receives the request can query the session store to restore needed data.

**Note:** Redis sessions do not verify OAuth2 `state` or ID Tokens by themselves. Spring Security still handles those checks, and cookie/session configuration must be accurate.

### 6.2. Which Components Are Needed?

For a Servlet Spring Boot app, you typically need:

- <code>spring-boot-starter-web</code>.
- <code>spring-boot-starter-security</code>.
- <code>spring-boot-starter-oauth2-client</code>.
- <code>spring-session-data-redis</code> and matching Redis client/configuration.
- A Redis endpoint protected by authentication, TLS, and network policies.

Spring Boot auto-configures Spring Session based on dependencies and properties. If you manually add <code>@EnableRedisHttpSession</code> or custom session configs, understand that they can alter or override auto-configuration; do not add annotations "just to be sure" when auto-configuration already works.

### 6.3. Illustrative Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ensure Spring Boot, Spring Session, and Spring Security versions align. Prefer Spring Boot's dependency management rather than manually pinning multiple versions.

### 6.4. `application.yml` for Redis Sessions

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD:}

  session:
    timeout: 30m
    redis:
      namespace: portal:sessions

server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

This is an **example Servlet** configuration. Property names can change across major versions; follow the Spring Boot/Spring Session docs for your deployed version.

Explanation:

- <code>spring.data.redis.*</code> configures the Redis connection.
- <code>spring.session.timeout</code> sets the configured session idle timeout.
- <code>spring.session.redis.namespace</code> partitions session keys by application/environment.
- <code>HttpOnly</code> cookies restrict JavaScript access to the session cookie.
- <code>Secure</code> requires HTTPS from the browser's perspective, appropriate for production.
- <code>SameSite=Lax</code> typically works with top-level cross-site **GET** OIDC callbacks; if using <code>response_mode=form_post</code> or another SSO flow, verify browser `SameSite`/cookie behavior and CSRF policy.

Never put example Redis passwords in source code. Production must use TLS and proper Redis credentials/ACL/network isolation; if the app sits behind a TLS-terminating proxy, configure secure cookies and trusted forwarded headers.

### 6.5. Session Timeout vs. Access Token Expiry

Example:

~~~text
HTTP session timeout = 30 minutes idle
Access token lifetime = 10 minutes
Refresh token lifetime = per OP policy
~~~

At minute 15, the user may still have an active session while the access token has expired. The manager can refresh it if a valid refresh token exists. Conversely, losing a user's session does not mean tokens in storage were revoked at the OP.

Never assume increasing the session timeout fixes token refresh failures.

## 7. Storing Authorized Clients: Service vs. Repository

In **Spring Security Servlet**, two abstractions are common:

- <code>OAuth2AuthorizedClientService</code>: loads/saves/removes by ClientRegistration ID and principal name.
- <code>OAuth2AuthorizedClientRepository</code>: loads/saves/removes in the context of <code>Authentication</code>, <code>HttpServletRequest</code>, and <code>HttpServletResponse</code>.

A web repository may back onto a service or the HTTP session depending on implementation:

| Implementation | Typical Storage / Lookup | Scale-Out Considerations |
|---|---|---|
| <code>HttpSessionOAuth2AuthorizedClientRepository</code> | HTTP session | Needs a shared session store if requests roam across nodes |
| <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> | Delegates to <code>OAuth2AuthorizedClientService</code> for authenticated principals, with configured fallback for unauthenticated cases | A shared HTTP session **does not guarantee** the underlying service is also shared |
| <code>InMemoryOAuth2AuthorizedClientService</code> | Single-instance memory | Restarts/scale-out lose or fragment tokens |
| <code>JdbcOAuth2AuthorizedClientService</code> | Database table per Spring Security schema | Shares tokens, yet does not lock cross-node refreshes automatically |
| Custom service/repository | Redis/database/token vault per design | Must store full token state and implement clear concurrency/security |

### 7.1. Defaults Are Not Always Identical

Spring Boot/Spring Security may register default beans based on dependencies, configuration, and versions. Never infer:

~~~text
Spring Session Redis is enabled
⇒ all OAuth2AuthorizedClients are automatically in Redis
~~~

If your app uses <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> delegating to an <code>InMemoryOAuth2AuthorizedClientService</code>, authenticated users' tokens may still reside in the current node's RAM.

Conversely, if your app explicitly uses <code>HttpSessionOAuth2AuthorizedClientRepository</code> and Spring Session genuinely shares HTTP sessions, tokens stored in that session follow the session across nodes. Changing repository or security config changes this behavior.

**Inspect the actual bean wiring**, not just dependency names.

### 7.2. Why Use the `(registrationId, principalName)` Pair?

An authorized client is typically keyed by:

~~~text
(clientRegistrationId, principalName)
~~~

Example:

~~~text
(company, user-123)
(company, user-456)
(partner-api, user-123)
~~~

These are **three distinct authorized clients**. Never store tokens in a singleton variable keyed only by registration ID, or user A will overwrite user B's token.

In multi-tenant or multi-issuer setups, `principalName` must carry a trusted namespace. A <code>sub=123</code> from issuer A and a <code>sub=123</code> from issuer B are not automatically the same account.

### 7.3. Never Equate OIDC Subject and Email

OIDC uses <code>(iss, sub)</code> as the stable identifier within an issuer's context. Email addresses can change, be absent, or remain unverified.

If an app customizes principal name to email without a safe account-linking policy, two users/issuers could collide on the same authorized client. Validate and use proper internal keys when designing shared storage.

## 8. Spring Boot Servlet Example: Spring Session Redis + JDBC Authorized Clients

A straightforward setup separating responsibilities clearly:

~~~text
Redis:
    HttpSession, SecurityContext, authorization request state/PKCE

PostgreSQL:
    OAuth2AuthorizedClient for authenticated principals
    access token + refresh token (per service config)

Authorization Server:
    token issuance rights, OP session, token revocation/rotation
~~~

**Note:** You do not have to use Redis + PostgreSQL in every system. This is a reference architecture; another token vault or store can work if it satisfies persistence, concurrency, and security requirements.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

### 8.2. Configuring Redis, JDBC, and OIDC Registration

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD:}

  session:
    timeout: 30m
    redis:
      namespace: portal:sessions

  datasource:
    url: ${JDBC_URL}
    username: ${JDBC_USERNAME}
    password: ${JDBC_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

All endpoints, Client IDs, and scopes are examples. JDBC/Redis credentials and client secrets must come from proper secret management. Production DB and Redis connections must be secured with TLS, ACLs, and network policies.

### 8.3. Configuring SecurityFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

<code>oauth2Login()</code> handles Authorization Code/OIDC Login and saves the resulting `Authentication`. <code>oauth2Client()</code> enables Servlet OAuth2 Client support when the app uses authorized clients to call APIs.

This is a session-based browser configuration; **never disable CSRF application-wide** simply because some downstream APIs accept Bearer tokens.

### 8.4. Configuring JDBC-Backed OAuth2AuthorizedClientService

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbcOperations,
        ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcOperations, registrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
        OAuth2AuthorizedClientService authorizedClientService) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            authorizedClientService);
    }
}
~~~

Meaning:

1. The service reads/writes authorized clients by registration/principal in JDBC.
2. The web repository loads/saves/removes via the service for authenticated principals.
3. Spring Security OAuth2 Login/Client must actually be **wired to this repository bean**; check your version and bean auto-configuration if multiple repositories or managers exist.
4. Spring Session stores HTTP sessions in Redis through its own configuration, not via <code>JdbcOAuth2AuthorizedClientService</code>.

**You must provision the JDBC schema** matching <code>JdbcOAuth2AuthorizedClientService</code> for your chosen Spring Security version. Do not simply define the bean and assume the library auto-creates tables in every environment. In production, enforce controlled migrations, backups, least-privilege DB access, and token data protection.

### 8.5. A Controller Returning Safe Metadata Only

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/my/oauth2-client")
    public Map<String, Object> info(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient client) {

        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "principalName",
            client.getPrincipalName(),
            "hasRefreshToken",
            client.getRefreshToken() != null,
            "hasAccessToken",
            client.getAccessToken() != null
        );
    }
}
~~~

This example observes which node resolves the authorized client **without returning token values**. In production, `principalName` may be sensitive; consider returning only an application-approved display identifier or keeping this debug endpoint internal.

For APIs that do not need to expose token-storage status, omit this endpoint altogether. When no authorized client exists, handle it per your flow/exception policy—never fall back to another user's token.

### 8.6. What Happens When Instance A Restarts?

If Redis and PostgreSQL stay healthy:

- The browser can keep sending its session cookie pointing to the Redis session.
- Instance B can restore `SecurityContext` provided serialization and `SecurityFilterChain` are compatible.
- The authorized client can be loaded from JDBC by principal/registration.
- Valid tokens can be used; expiring tokens go through the configured manager/provider.

Even so, **being able to read state does not prove refresh concurrency is safe**. If A and B refresh a token simultaneously, a shared database alone will not prevent races.

## 9. Comparing Three Authorized Client Storage Models

### 9.1. Tokens in Web/HTTP Session

~~~text
Browser session cookie
    ↓
Shared Spring Session
    └── Authorized client state (if repository stores in session)
~~~

Pros:

- Tokens follow the browser session lifecycle.
- Simple when the app has only browser logins and needs no tokens after logout.
- A shared session store lets tokens follow the browser across nodes.

Limitations:

- Session expiry drops the authorized client with the session.
- If a user opens multiple browser sessions, token state may split per session depending on repository.
- Session serialization holds sensitive tokens; Redis, backups, and observability must be secured accordingly.
- Services/background jobs cannot look up tokens outside a session by default.
- Refresh races can still occur if two requests in the same session hit two nodes concurrently.

### 9.2. Tokens in a Shared OAuth2AuthorizedClientService

~~~text
Browser A / Browser B
       ↓
Authenticated principal + registrationId
       ↓
Shared OAuth2AuthorizedClientService
       ↓
Token record
~~~

Pros:

- Tokens can be reused across requests/sessions per principal.
- Token persistence is decoupled from session timeout.
- Cleanup, encryption, rotation, and auditing can be managed at a dedicated layer.

Limitations:

- Tokens can remain in the DB after browser logout unless a cleanup policy removes them.
- If two sessions for the same principal update/refresh the same record, concurrent updates must be handled.
- Risk of issuer/tenant collisions if principal keys are poorly designed.
- DB access to tokens becomes a high-value security asset.

### 9.3. Tokens in Per-Instance Memory

~~~text
A: (company,user-123) -> A0/R0
B: (company,user-123) -> absent
~~~

Pros: very simple for local/demo/single-instance setups.

Limitations: lost on restart, unsynchronized across replicas, triggers unnecessary re-authorizations. For a confidential service using `client_credentials`, requesting a fresh token after restart can be acceptable; never apply that reasoning to **End-User delegated refresh tokens** where provider rotation and consent policies are involved.

## 10. Choosing the Right OAuth2AuthorizedClientManager for the Context

The manager coordinates `ClientRegistration`, the authorized-client repository/service, and grant providers. It is neither a database nor a load balancer.

### 10.1. Servlet Browser Requests

<code>DefaultOAuth2AuthorizedClientManager</code> typically uses:

~~~java
new DefaultOAuth2AuthorizedClientManager(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

The repository operates in the context of <code>HttpServletRequest</code> and <code>HttpServletResponse</code>. It fits Servlet HTTP requests that already have `Authentication` and a session.

Example manager with a refresh provider:

~~~java
@Bean
OAuth2AuthorizedClientManager webAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager =
        new DefaultOAuth2AuthorizedClientManager(registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

This is an **optional bean example**; if your project already has an auto-configured manager, do not add a redundant one. When multiple managers exist, distinguish them clearly with bean names and <code>@Qualifier</code>.

### 10.2. Background Jobs or Scheduled Workers

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> uses a service instead of a Servlet request:

~~~java
@Bean("jobAuthorizedClientManager")
OAuth2AuthorizedClientManager jobAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Configuration snippets in section 10 are abbreviated examples. In real classes, import the corresponding types from <code>org.springframework.security.oauth2.client.*</code>, <code>org.springframework.security.oauth2.client.registration.*</code>, <code>org.springframework.security.oauth2.client.web.*</code>, and <code>org.springframework.context.annotation.*</code>.

A `client_credentials` job **is not** an OIDC End-User Login. Use a stable synthetic principal to partition storage by workload:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-worker")
    .principal("reports-worker-runtime")
    .build();
~~~

If a job needs a **user-delegated refresh token**, authorization and lifecycle rules are more complex. Never fetch a user's refresh token from the DB using a caller-supplied user ID; enforce policies for delegated execution and token storage isolation.

### 10.3. The Manager Does Not Coordinate Refreshes Cluster-Wide

<code>refreshToken()</code> teaches the manager **how to refresh**. It does not guarantee only one replica hits the Token Endpoint at a time.

When multiple instances share a token store and manager, add coordination or storage concurrency control matched to the OP's behavior.

## 11. Refresh Token Rotation and Two-Node Races

As the access token nears expiry:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared Token Store
    participant OP as Token Endpoint

    A->>DB: load(company,user-123)
    DB-->>A: A0, R0, version=7
    B->>DB: load(company,user-123)
    DB-->>B: A0, R0, version=7
    A->>OP: refresh_token=R0
    OP-->>A: A1 + R1
    B->>OP: refresh_token=R0
    OP-->>B: invalid_grant / reuse detection
    A->>DB: save A1, R1, version=8
    B->>DB: failure handler deletes record?
    Note over DB: B can mistakenly delete version=8 if delete is unconditional
~~~

If the OP enables **refresh token rotation**, reusing `R0` can invalidate the entire token family per policy. Not every OP handles reuse identically: some grant a grace window, some enforce strictly, and some do not rotate.

Never conclude from "we haven't seen <code>invalid_grant</code> in staging yet" that sharing refresh tokens without locking is safe.

### 11.1. Sharing Data Is Not Serializing Operations

JDBC/Redis lets A and B **read the same token**, but does not prevent them from **reading `R0` together and both refreshing**.

~~~text
Shared store             = shared visibility of data
Distributed coordination = serializing mutations / consumption of state
~~~

These are separate capabilities; both are required with refresh-token rotation.

### 11.2. Why Is `synchronized` Not Enough?

~~~java
public synchronized OAuth2AuthorizedClient refresh(...) { ... }
~~~

<code>synchronized</code> protects threads only within **one JVM**. It cannot coordinate A and B across separate machines or containers.

Likewise, a local <code>ConcurrentHashMap</code> of locks cannot coordinate requests hitting other replicas.

### 11.3. Lock by Authorized-Client Key

Locks should key on:

~~~text
registrationId + trustedPrincipalKey
~~~

Example:

~~~text
oauth2:refresh:company:hash-principal-123
~~~

Never use one global lock across all users; user A should not wait on refreshes for user B.

In multi-tenant environments, lock keys must carry proper issuer/tenant namespaces. Never use raw emails or user-supplied strings as lock keys when PII exposure or collisions are possible.

## 12. Safer Refresh Coordination Algorithm

A practical flow normally performs a **double-check after acquiring the lock**.

~~~text
authorizeOrRefresh(registrationId, trustedPrincipal):
    key = stableAuthorizedClientKey(registrationId, trustedPrincipal)

    current = tokenStore.load(key)
    if current has a usable access token:
        return current

    acquire distributed lock(key) with timeout/lease
    try:
        latest = tokenStore.load(key)  // MUST reload

        if latest was updated by another node and token is valid:
            return latest

        if latest lacks an appropriate refresh token:
            require reauthorization / alternative grant per policy

        response = Token Endpoint.refresh(latest.refreshToken)

        commit the new access/refresh token pair atomically
        with version/fencing checks if needed

        return committed authorized client
    finally:
        release lock only if still holding ownership
~~~

This is **architectural pseudocode**, not a built-in API on <code>OAuth2AuthorizedClientManager</code>.

### 12.1. Why Must You Reload After Acquiring the Lock?

Suppose:

~~~text
T0: A reads R0, B reads R0
T1: A acquires lock; B waits
T2: A refreshes R0, saves R1, releases lock
T3: B acquires lock
~~~

If B keeps using its **T0 snapshot of `R0`**, the lock accomplished nothing. B must read the latest state at T3; if `A1` is now valid, **do not call the Token Endpoint** again.

### 12.2. What If the Lock Cannot Be Acquired?

Never "skip the lock to be faster" and refresh `R0` anyway. Options:

- Wait briefly with a bounded timeout and re-read the store.
- If the old access token still has enough remaining lifetime within a safety margin, use it per policy.
- Return a temporary error for internal APIs or defer the background job.
- Monitor lock contention to find root causes.

Avoid infinite loops or blocking request threads indefinitely.

### 12.3. Ownership and Leases

A distributed lock should have:

1. An **owner token** uniquely identifying one lock acquisition.
2. A **lease/TTL** preventing permanent locks if a node crashes.
3. **Atomic release checking the owner**, never deleting a newer owner's lock.
4. Explicit wait times and timeouts.
5. Where strict guarantees are needed, **fencing tokens** at storage to reject stale writers after lease expiry.

Dangerous example: A holds a 10-second lock, pauses for 15 seconds (GC/network); B acquires a new lock. When A wakes up and deletes the lock unconditionally, it deletes B's lock.

### 12.4. Fencing Prevents Late Writes, Not Already-Sent OP Requests

If A holds fencing sequence 41 and B receives sequence 42, storage can reject A's write with sequence 41.

This protects the **token store** from stale writes. However, if A already sent `R0` to the OP, database fencing **cannot undo `R0` being consumed**.

Hence you need pre-request coordination plus post-request conditional save/delete.

## 13. Optimistic Concurrency: CAS/Versioning on Token Records

To prevent lost updates, a custom token store can track a <code>version</code> column:

~~~text
registration_id | principal_name | access | refresh | version
company         | user-123       | A0     | R0      | 7
~~~

After a refresh returns `A1/R1`:

~~~sql
UPDATE oauth2_authorized_client_state
SET access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    access_expires_at = :new_access_expires_at,
    version = version + 1
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

If affected rows equals **1**, the write from the expected version succeeded. If **0**, another node updated or deleted the record; the writer must never drop the version condition to force an overwrite.

### 13.1. Save Access and Refresh Tokens Atomically

When the OP issues <code>A1/R1</code>, never update access token and refresh token in two separate transactions:

~~~text
UPDATE access_token = A1
COMMIT
-- another node might read A1 + R0 right here
UPDATE refresh_token = R1
COMMIT
~~~

Save the entire related authorized-client state in **one atomic update**. If the response omits a new refresh token, preserve the prior refresh token per response/client contract; if it returns `R1`, replace `R0` atomically.

### 13.2. CAS Protects Only the Database

CAS **does not** stop A and B from concurrently sending `R0` if both read the state before calling the OP. Thus:

~~~text
Lock/single-flight before Token Endpoint → prevents duplicate refreshes
CAS/versioning at storage                → prevents stale updates/deletes
~~~

### 13.3. Default JDBC Service Does Not Mean Versioned Storage

Never assume <code>JdbcOAuth2AuthorizedClientService</code> provides a <code>version</code> column, conditional update/delete, or distributed locking out of the box.

If you need those guarantees, you may have to:

- Extend the storage schema/DAO with compatible versioning.
- Write a wrapper or custom <code>OAuth2AuthorizedClientService</code>.
- Configure success/failure handlers to save/delete conditionally.
- Use a single-writer token service or unified coordinator across all code paths.

**Never alter the default schema expecting the framework to use new columns automatically** without matching code.

## 14. Risk of Failure Handlers Deleting Newer Tokens

Some managers/providers remove the authorized client after an <code>invalid_grant</code> error. Across multiple replicas, watch the ordering:

~~~text
A: refreshes R0 successfully and saves A1/R1, version=8
B: refresh of R0 fails with invalid_grant
B: removeAuthorizedClient(company, user-123)
~~~

If B deletes unconditionally by registration/principal, A's newly saved version 8 is lost.

A safer policy:

~~~text
if refresh fails with invalid_grant:
    latest = tokenStore.load(key)

    if latest.version != version used by the failed refresh:
        do not delete the newer record
        re-evaluate the situation
    else:
        compareAndRemove(key, expectedVersion)
        mark reauthorization needed if appropriate
~~~

Conceptual SQL:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Exact <code>invalid_grant</code> semantics also depend on the OP. If the OP detected `R0` reuse and revoked the entire token family, the newer `A1/R1` may also be affected. **Do not conclude `R1` is definitely still valid merely because version 8 was saved.**

### 14.1. Do Not Delete Tokens on Every Network Error

Distinguish:

| Error | What You Can Infer | Handling |
|---|---|---|
| <code>invalid_grant</code> | Grant/refresh token rejected | Check rotation, revocation, reauthorization |
| <code>invalid_client</code> | Invalid client credentials/auth | Check registration/secrets/key rotation |
| HTTP 429 Token Endpoint | Rate limited | Bounded backoff/jitter; reduce token requests |
| HTTP 502/503 | Temporary AS/gateway outage | Controlled retry; do not blindly delete |
| Timeout after sending refresh | Unknown if OP consumed `R0` | Never retry `R0` infinitely |
| CAS conflict | Concurrent state modification occurred | Reload and evaluate new version |
| Lock timeout | Another node may be refreshing | Wait/reload or return temporary error |

Timing out after the OP issued `R1` whose response was lost is an **unknown outcome**. There is no standard distributed transaction between a Token Endpoint and a local database to guarantee "exactly-once refresh" in every failure mode.

## 15. Logout, Session Expiry, and Token Revocation

A distributed system must clearly define lifecycles for both **sessions** and **authorized clients**.

### 15.1. Operations That Are Not Equivalent

~~~text
Log out browser session
    != Remove OAuth2AuthorizedClient in local store
    != Revoke access/refresh token at Authorization Server
    != Log out SSO session at OpenID Provider
~~~

Depending on the product, logout may require one or several steps.

| Operation | Effect |
|---|---|
| Invalidate HTTP session | Browser can no longer continue the old portal session |
| Remove authorized client | Local service/repository drops the keyed token record |
| Token revocation (RFC 7009) | Requests AS to revoke tokens if endpoint/profile supported |
| OIDC RP-Initiated Logout | Redirects/notifies OP logout per configuration and policy |
| Domain account disable | Blocks business privileges; must be enforced by APIs/Clients |

Never treat deleting a Redis session as proof that **the refresh token was revoked at the OP**.

### 15.2. Deleting Records by Principal Must Account for Multiple Sessions

If <code>OAuth2AuthorizedClientService</code> stores one record per <code>(registrationId, principalName)</code>, multiple sessions for the same user may share that record.

When the user logs out of one browser:

- **Deleting immediately** can strip the authorized client from the user's other active session.
- **Not deleting** can leave tokens on the backend after all sessions have ended.

No single option fits every product. Decide whether token scope is **per session**, **per principal**, **per device**, or **per authorization grant**, then choose storage keys and cleanup policies accordingly.

If you need per-device or per-session separation, do not mutate `principalName` arbitrarily without evaluating expected repository APIs and identity linking.

### 15.3. Concurrent Logout and Refresh

If one node logs out and revokes tokens while another node refreshes:

~~~text
Node A: logout → deletes record
Node B: refreshes R0 → saves A1/R1 back
~~~

Without coordination, the record can **reappear after logout**. Architectures handling this scenario can use:

- Tombstones/revocation generations or an authorization disabled flag.
- CAS/fencing with a rule "never save after a newer logout generation".
- A single writer for authorized-client state.
- Idempotent cleanup/revocation and auditing.

Relying on a bare <code>DELETE</code> without controlling concurrent writers is insufficient when prompt revocation is a security requirement.

## 16. Reactive WebFlux Model

In **WebFlux**, use reactive abstractions:

| Servlet | Reactive WebFlux |
|---|---|
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> |
| <code>OAuth2AuthorizedClientRepository</code> | <code>ServerOAuth2AuthorizedClientRepository</code> |
| <code>OAuth2AuthorizedClientService</code> | <code>ReactiveOAuth2AuthorizedClientService</code> |
| <code>DefaultOAuth2AuthorizedClientManager</code> | <code>DefaultReactiveOAuth2AuthorizedClientManager</code> |
| <code>RestClient</code> or Servlet HTTP integration | <code>WebClient</code> with reactive integration |

### 16.1. Spring Session for WebSession

Spring Session provides Redis integration for reactive <code>WebSession</code>. A WebFlux project needs the corresponding dependencies and auto-configuration, for example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
~~~

Exact dependencies vary by Spring Boot version and Redis client; avoid adding both synchronous and reactive Redis starters if your app only uses one stack.

With Spring Session Reactive, <code>WebSession</code> is centralized so OIDC callbacks across nodes recover state/correlation. However, the authorized-client repository/service must still be configured and verified separately.

### 16.2. Reactive Authorized-Client Storage

Abstractions:

~~~text
ServerOAuth2AuthorizedClientRepository
    ↕
ReactiveOAuth2AuthorizedClientService
    ↕
Reactive-compatible persistent store
~~~

Some repositories store authorized clients in `WebSession`; others delegate to a service by principal. **Never run blocking JDBC directly on the Netty event loop** wrapped in <code>Mono.just(...)</code> and call it reactive.

If you must integrate a blocking driver, isolate it on an appropriate scheduler, manage pools, and measure latency—or use a non-blocking implementation where architecture allows.

### 16.3. Reactivity Does Not Solve Distributed Refresh Races

Two <code>Mono</code> pipelines running on A and B can still read the same `R0` and send concurrent token requests. Not blocking the event loop and not calling `.subscribe()` manually are necessary, yet **you still need distributed coordination** if the provider enforces strict rotation.

Do not confuse reactive concurrency within one pipeline with cluster-wide locking/transactions.

## 17. Session Cookies and Callbacks Through Proxies / Load Balancers

When moving to distributed sessions, many bugs actually stem from **cookies and proxies**, not Redis.

### 17.1. Callback Cannot Find State

Symptom:

~~~text
GET /oauth2/authorization/company → OP redirect succeeds
GET /login/oauth2/code/company → state missing/mismatch
~~~

Possible causes:

- The browser did not send the cookie back on the callback.
- Mismatched cookie `Domain`/`Path` or `SameSite`/`Secure`.
- Proxy corrupted scheme/host when building the redirect URI.
- Session was not persisted/replicated properly.
- Callback hit another node while the session store was not shared.
- Browser ran multiple competing authorization flows in the same session.
- Session timed out while the user was at the OP.

Never fix this by disabling <code>state</code>, <code>nonce</code>, or PKCE validation. Those mechanisms protect OAuth2/OIDC Login against callback injection/replay and code interception.

### 17.2. SameSite and `response_mode`

For top-level GET callbacks, <code>SameSite=Lax</code> cookies generally work. If the OP returns callbacks via cross-site form POST (<code>response_mode=form_post</code>), browser cookie-sending rules differ. When <code>SameSite=None</code> is needed, modern browsers require <code>Secure</code>; review CSRF and session policies thoroughly.

Never switch cookies to <code>SameSite=None</code> system-wide without assessing cross-site cookie risks and protections on state-changing routes.

### 17.3. Trusted Forwarded Headers

When the app runs HTTPS at a public load balancer yet reaches Spring Boot over internal HTTP:

~~~text
Browser: https://portal.example.org
Proxy → app: http://app:8080
~~~

Without proper forwarded-header configuration, Spring may construct:

~~~text
redirect_uri=http://app:8080/login/oauth2/code/company
~~~

instead of the valid public callback URI.

Accept <code>Forwarded</code>/<code>X-Forwarded-*</code> headers only from **trusted proxies**, never arbitrary callers. Configure <code>server.forward-headers-strategy</code> and proxy rules per environment/version.

## 18. Serialization and Rolling Upgrades

When sessions live in Redis, session data is serialized. With Spring Security, `SecurityContext`/`Authentication`/OIDC principals can reference complex classes and dependencies.

Evaluate:

- Which serializer is active (JDK serialization, JSON serializer, or custom config).
- Whether required Spring Security type metadata/modules are registered.
- Whether unsafe polymorphic deserialization is avoided; deserialize only from controlled stores.
- Whether code versions A and B during a rolling deploy can read each other's session objects.
- Whether changing class names or schemas breaks existing sessions.
- Avoiding custom non-serializable objects or unshareable dependencies inside sessions.

A failure scenario:

~~~text
Node A (version v1) saves SecurityContext to Redis
Node B (version v2) reads session
    → deserialization error due to incompatible class/serializer
~~~

This is a **session serialization compatibility** problem, not the OIDC Token Endpoint rejecting a code.

### 18.1. Do Not Treat Redis as Unconditionally Safe

Redis may contain session IDs, `SecurityContext`, and even tokens if a repository stores them in session. Protections:

- Redis ACLs/users/passwords or cloud IAM authentication.
- TLS between application and Redis.
- Network segmentation; never expose Redis to the Internet.
- Secured backups/snapshots and encryption at rest where needed.
- Dedicated namespaces per environment/application.
- Restricted access to inspect Redis keys and values.
- Controls for eviction, TTL, replication, and failover.

Never log raw session IDs in general logs; a session ID is a browser credential in cookie-based session architectures.

### 18.2. Eviction and TTL

Under memory pressure or eviction policies, Redis can drop sessions earlier than expected timeouts. Browsers then lose login state even though cookies remain.

Monitor evictions, key expirations, and Redis availability. Never use a best-effort cache configured to evict arbitrarily as a critical session store without assessing persistence and failure policies.

## 19. Production Architecture Decisions

### 19.1. Must Sessions and Tokens Share the Same Datastore?

No. For example:

~~~text
Session: Redis
Authorized client: PostgreSQL
Secrets/keys: KMS or secret manager
Authorization Server: Dedicated OP
~~~

Pros: tune TTLs, storage encryption, backups, and concurrency independently for each data type.

Cons: more components and consistency handling between session and authorized-client state.

Sharing Redis for both sessions and tokens can also work if implementation and security controls fit, yet **it still shares no transaction with the Authorization Server**.

### 19.2. Per-Session or Per-Principal?

| Model | Fits When | Watch Out For |
|---|---|---|
| Per-session | Tokens are used only during a browser session and need not outlive logout | Multiple browser sessions, token duplication, session expiry |
| Per-principal | Users reuse the same authorized client across sessions/instances | Logging out one session, token sharing, token isolation |
| Per-device | Independent per-device or per-session revocation is required | Extra key dimension, consent and lifecycle management |
| Per-service | Backend workload `client_credentials` | Stable synthetic principal, scopes/audience, secret rotation |

A default <code>OAuth2AuthorizedClientService</code> does not automatically fit when a product needs per-device revocation. If adding key dimensions, build a proper custom service/repository rather than warping `principalName` randomly to bypass constraints.

### 19.3. Decisions to Finalize Before Rollout

- **Ownership:** Who may read/write authorized clients?
- **Keys:** Do identity keys isolate issuer, tenant, and device where needed?
- **Persistence:** Must tokens survive restarts or session expiry?
- **Concurrency:** Do you have single-flight refresh and conditional update/delete for rotation?
- **Revocation:** After logout/disconnect, how long do tokens remain valid at the OP?
- **Retention:** When are orphaned records cleaned up?
- **Availability:** During Redis/DB outages, what errors does the system return?
- **Security:** Are tokens/sessions protected at rest, in transit, and in backups/logs?
- **Compatibility:** Can rolling deploys read prior session/token schemas?

## 20. Multiple Instances Do Not Mean `@Scheduled` Runs Once

If your app uses <code>@Scheduled</code>:

~~~text
Instance A: job 02:00
Instance B: job 02:00
Instance C: job 02:00
~~~

Spring Session, JDBC authorized-client stores, and <code>OAuth2AuthorizedClientManager</code> **do not prevent all three instances from running the job concurrently**.

Separate three concerns:

1. **Distributed job coordination**: only one worker runs a business job when required.
2. **Token refresh coordination**: prevent two workers from consuming the same refresh token.
3. **Idempotent business logic**: if a request was sent and timed out, retries do not duplicate side effects.

A `client_credentials` job can request a new token when needed. A user-delegated job using refresh tokens must enforce principal/consent isolation, revocation checks, and refresh token rotation per policy.

## 21. Security When Multiple Nodes Access Authorized Clients

### 21.1. The Authorized-Client Service Is a Credential Store

Access tokens and especially refresh tokens are sensitive credentials. A compromised node capable of reading the entire token store affects far more users than a single session's access token.

Mitigations:

- Minimal DB/Redis permissions per service.
- TLS and network segmentation.
- Encryption at rest, key rotation, and backup protection.
- Never log raw access/refresh tokens in logs, metrics, or exception messages.
- Scope data access by tenant or service boundary.
- Consider envelope/column encryption if your threat model requires it.
- Enforce authorization checks before loading or deleting tokens.

### 21.2. Never Let the Browser Specify the Principal Key

Wrong:

~~~java
String principal = request.getParameter("userId");
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(principal)
        .build();
~~~

A browser can pass another user's ID. If the token store uses that key, it risks fetching or stealing someone else's authorized client.

For browser logins, derive the principal from Spring Security's verified <code>Authentication</code>. For service jobs, use a **backend-controlled** synthetic principal.

### 21.3. Separate Security Domains per ClientRegistration

Two registrations may point to different issuers or different client IDs at the same issuer. Never use a token from registration A for API B if audience/scopes do not match.

In multi-tenant systems, a subject string from issuer A is not automatically the same user as a subject string from issuer B. Namespace principal keys via trusted issuer/tenant mappings, never unverified emails.

### 21.4. Never Refresh to Escalate Privileges

HTTP 401 Bearer <code>invalid_token</code> relates to token lifecycle; HTTP 403 Bearer <code>insufficient_scope</code> usually means missing permissions. Refreshing with the same grant/scope will not invent new scopes. On 403, fix authorization policies rather than looping refreshes/logins.

## 22. Observability and Troubleshooting

### 22.1. Useful Metrics

| Metric or Log Field | Purpose |
|---|---|
| <code>session_restore_success</code> | Rate of session restoration after routing to another node |
| <code>oauth2_callback_state_mismatch</code> | Detects session/correlation issues |
| <code>authorized_client_lookup_miss</code> | Token lookup failures despite active user session |
| <code>authorized_client_refresh_attempt</code> | Count of refresh token requests sent |
| <code>authorized_client_refresh_invalid_grant</code> | Tracks rotation/reuse/revocation |
| <code>refresh_lock_wait_ms</code> | Contention when refreshing the same key |
| <code>refresh_cas_conflict_total</code> | Stale writes rejected |
| <code>token_storage_latency_ms</code> | DB/Redis latency |
| <code>redis_session_evictions</code> | Sessions dropped due to memory pressure |
| <code>api_401_403_by_service</code> | Separates invalid tokens from missing permissions |

Never use raw tokens, session cookies, client secrets, unsanitized `principalName`, or HTTP `Authorization` headers as metric labels.

### 22.2. Safe Request Diagnostics Log

Example:

~~~text
instance=portal-b
route=/reports
registrationId=company
principalKeyHash=...
sessionRestored=true
authorizedClientFound=true
tokenRefreshOutcome=skipped_valid_token
upstreamStatus=200
correlationId=...
~~~

Never print:

~~~text
JSESSIONID=...
Authorization: Bearer ...
refresh_token=...
code_verifier=...
OIDC ID Token=...
~~~

### 22.3. Common Failure Table

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| Callback succeeds only on A | Local sessions/authorization requests | Spring Session, cookies, LB routing |
| <code>invalid_state</code> after scale-out | Missing original request, lost cookie, or concurrent logins in same session | State repository/TTL/proxy |
| User logged in, yet B cannot find token | Token sits in A's <code>InMemoryOAuth2AuthorizedClientService</code> | Repository/service wiring |
| Users logged out after rolling deploy | Incompatible session serialization or Redis evictions | Serializer, version, TTL |
| All users lose login when Node A restarts | No shared session store or Redis unavailable | Session config/HA |
| HTTP 401 from API after switching nodes | Token missing, expired, or wrong audience | Registration/principal, token lifecycle |
| HTTP 403 from API | Missing scope/role/tenant policy | Do not auto-delete tokens |
| <code>invalid_grant</code> when scaling 2→5 replicas | Likely concurrent `R0` refreshes | Locking, reload, CAS, OP rotation policy |
| DB token overwritten by older version | Stale writer / lost update | Conditional updates/versioning |
| Token record reappears after logout | Concurrent refresh saved after cleanup | Revocation generation/tombstone/coordination |
| Token Endpoint hammered continuously | Refresh result not saved, changing principal, short TTL | Success handler, storage, clock skew |
| Scheduler runs duplicate jobs | <code>@Scheduled</code> running on every node | Distributed scheduler/idempotency |
| Sessions in Redis, yet authorized clients stay local | Repository delegates to InMemory service | Switch to shared service/repository |
| Redis deserialization errors | Class/session schema changed | Check rollout serializer/version |
| Login loop | Blocked cookie, chain matcher/callback, or unsaved auth state | Cookies, `SecurityFilterChain`, callback state |

### 22.4. Isolation Workflow

~~~text
OIDC callback fails when crossing instances?
    |
    +-- Yes → check cookies + session store + state repository
    |
    v
Can SecurityContext/Authentication be restored?
    |
    +-- No → session serializer/TTL/Redis/proxy
    |
    v
Is the authorized client found for the right registration/principal?
    |
    +-- No → repository/service/token storage/tenant key
    |
    v
Is the access token usable or needing refresh?
    |
    +-- Needs refresh → single-flight + reload + CAS/atomic save?
    |
    v
Does the Token Endpoint accept the refresh?
    |
    +-- invalid_grant → check rotation/race/revocation
    |
    v
Does the Resource Server accept audience/scope/permissions?
    |
    +-- 401 → token validation/lifecycle
    |
    +-- 403 → authorization policy
    |
    v
Application returns valid business result
~~~

## 23. Testing Across Two Instances

To verify distributed behavior, **single-instance unit tests are insufficient**. Build an integration environment with two Spring Boot instances, a Redis session store, and a JDBC authorized-client store, using a controlled test OP/API.

### 23.1. Cross-Node Callback Scenario

1. Send <code>/oauth2/authorization/company</code> to instance A.
2. Preserve browser cookies.
3. Complete authentication at the test OP.
4. Route callback <code>/login/oauth2/code/company</code> to instance B.
5. Verify B loads the authorization request from the session store and validates `state`.
6. Ensure ID Token validation still runs; invalid `state` must fail.

### 23.2. Authorized Client Roaming Scenario

1. Log in on A; authorized client is saved in the shared store.
2. Send an API request through B with the same session cookie.
3. B restores `Authentication`.
4. B resolves the right authorized client by registration/principal.
5. No other user's token is used in the request.
6. The browser receives no raw access/refresh tokens.

### 23.3. Restart / Failover Scenario

1. Log in successfully on A.
2. Stop A.
3. Send requests to B.
4. Verify session and token state reload from stores.
5. Test policy under Redis/DB outage: fail safely without bypassing authentication.

### 23.4. Refresh Token Rotation Scenario

1. Seed an authorized client with an expiring access token and refresh token `R0`.
2. Have A and B request an access token for that same authorized client concurrently.
3. Verify the coordinator lets only one effective refresh send `R0` if that is your design invariant.
4. Ensure the waiting node reloads the newly saved token.
5. Verify access/refresh tokens are saved atomically.
6. Simulate lock lease expiry, stale writes/CAS conflicts, and failure handlers deleting tokens.
7. Ensure a failure on an older version never deletes a newer saved version.

### 23.5. Permissions and Logout Scenario

1. User logs out from one browser; confirm that session is no longer usable.
2. Verify the authorized client is kept or deleted per **published policy**.
3. If token revocation is configured, verify the AS responds and the backend stops using revoked tokens.
4. Test logout racing with refresh so token state does not reappear after revocation.
5. If multi-device is supported, verify logging out one device does not unintentionally wipe another device's session/authorization against policy.

These scenarios describe test requirements; they do not replace integration testing against your real Authorization Server and exact Spring Security version.

## 24. Exercises and Applied Questions

### Exercise 1 — Is Spring Session Enough?

A system uses Redis shared sessions, yet Spring Security still uses <code>InMemoryOAuth2AuthorizedClientService</code> for authenticated principals.

**Question:** Can Instance B reliably read the authorized client for a user who logged in on A?

**Answer:** No. Inspect actual repository/service wiring. Sharing sessions in Redis does not automatically move A's in-memory authorized-client service into Redis.

### Exercise 2 — Callback State Mismatch

A browser starts login on A, the OP redirects the callback to B, and B cannot find the original `state`.

**Question:** Should you disable state verification so login succeeds?

**Answer:** No. Fix session/cookie/proxy/authorization-request storage. <code>state</code> provides correlation and protects OAuth2 callbacks.

### Exercise 3 — Sticky Sessions and Failover

Operations enables sticky sessions and logins work. When A restarts, users are logged out.

**Question:** Why?

**Answer:** Sticky sessions only route requests; they do not replicate local state across restarts. Use a shared session store, failover planning, and compatible serializers if sessions must survive restarts.

### Exercise 4 — Shared Tokens, Yet Refresh Races

A and B both load `R0` from JDBC and call the OP concurrently. A receives `R1`; B receives <code>invalid_grant</code>.

**Question:** Did the shared JDBC store solve concurrency?

**Answer:** No. You need per-key single-flight before refreshing, reloading after lock acquisition, atomic token updates, and conditional saves/deletes where appropriate.

### Exercise 5 — Dropping Version Check After CAS Conflict

B tries to update a token with <code>WHERE version=7</code>, affecting 0 rows because A already saved version 8.

**Question:** Should B run an unconditional update just to be sure?

**Answer:** No. That causes a lost update. B must reload state and use the newer token or run policy-based recovery.

### Exercise 6 — Logging Out One of Two Browser Sessions

A user logs in on both a laptop and a phone. Both sessions share one authorized-client record keyed by principal.

**Question:** When logging out on the laptop, should you delete that record?

**Answer:** Depends on policy. Deleting breaks the phone; keeping it leaves tokens alive after one session logs out. Explicitly choose per-session, per-principal, or per-device design and matching cleanup.

### Exercise 7 — Session Expired, Refresh Token Remains

The browser session expires while the JDBC token store still holds a refresh token.

**Question:** Can the client skip login and treat the user as authenticated?

**Answer:** Not by default. Refresh tokens serve OAuth2 authorization/delegation and do not automatically replace `Authentication` for the current browser session; follow your login/authorization policy.

### Exercise 8 — Session Store Outage

Redis disconnects and instances cannot read `SecurityContext`.

**Question:** Should you temporarily accept every request carrying a cookie to preserve availability?

**Answer:** No. A cookie does not prove authentication if the backend cannot verify/restore the session under its security model. Fail safely and resolve the outage.

### Exercise 9 — Reactive Storage

A WebFlux app calls <code>Mono.just(jdbcService.loadAuthorizedClient(...))</code> on the Netty event loop.

**Question:** Is storage non-blocking?

**Answer:** No. The JDBC call executes blocking I/O before/while constructing the `Mono`. Use a reactive driver/store or isolate blocking I/O on a bounded scheduler.

### Exercise 10 — Designing a Two-Replica System

Outline:

1. Two Spring Boot OAuth2/OIDC Client instances behind a load balancer.
2. Shared Spring Session Redis for `SecurityContext` and authorization-request state.
3. Shared authorized-client service aligned with per-session/per-principal policy.
4. Registration/principal keys namespaced by issuer/tenant.
5. Per-key coordinator for refresh token rotation.
6. Atomic saves of access/refresh tokens and conditional deletes by version.
7. Logout/revocation policy for multi-device users.
8. Secured Redis/database with zero credential logging.
9. Plan for rolling deployments, serializer compatibility, session TTLs, and failover.
10. Integration tests for cross-node A/B callbacks and concurrent refreshes.

Explain what happens when **A crashes before the Token Endpoint**, **A crashes after OP refresh but before DB save**, and **A crashes after DB save but before releasing the lock**.

## 25. Summary

- **HTTP sessions**, **OAuth2 authorization requests**, **`SecurityContext`**, and **`OAuth2AuthorizedClient`** are distinct states; define their repositories and lifecycles explicitly.
- **Spring Session + Redis** shares Servlet <code>HttpSession</code> or WebFlux <code>WebSession</code> across replicas, enabling OIDC callbacks behind a load balancer.
- **Authorized clients** may live in sessions or in <code>OAuth2AuthorizedClientService</code>. Never assume enabling Spring Session makes every in-memory token store shared automatically.
- For authenticated principals, <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> can delegate to a service; <code>JdbcOAuth2AuthorizedClientService</code> provides shared persistence, yet lacks built-in distributed refresh locks or CAS.
- Use a **web manager** for HTTP requests and a **service manager** for background jobs; picking the right manager does not replace storage or concurrency policies.
- When an OP enables **refresh token rotation**, multiple instances using `R0` concurrently can trigger <code>invalid_grant</code> and reuse detection. Use per-key single-flight, post-lock reloads, atomic token-pair saves, and conditional updates/deletes where appropriate.
- Sticky sessions **do not replace** shared session or persistent token stores; distributed sessions do not replace distributed job scheduling.
- Session logout, local authorized client deletion, OP token revocation, and OIDC SSO logout **are not equivalent**.
- In multi-tenant/multi-issuer systems, construct principal keys from trusted identities with proper namespaces; never let browsers pick token keys.
- Protect Redis/DB/token stores, cookies, private secrets, backups, and TLS; never log session IDs, access/refresh tokens, authorization codes, PKCE verifiers, or raw ID Tokens.
- To verify scale-out, test **cross-node callbacks, roaming authorized clients, restarts/failovers, and concurrent refreshes**—not just single-machine happy-path login.

### References

- **Spring Session Reference — Spring Session with Redis:** sharing HTTP sessions, `WebSession`, and session store configuration.
- **Spring Security Reference — OAuth2 Login (Servlet):** authorization request repository, callbacks, and saving `Authentication`.
- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, and <code>OAuth2AuthorizedClientManager</code>.
- **Spring Security Java API:** <code>HttpSessionOAuth2AuthorizedClientRepository</code>, <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code>, <code>JdbcOAuth2AuthorizedClientService</code>.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ServerOAuth2AuthorizedClientRepository</code>, <code>ReactiveOAuth2AuthorizedClientService</code>, and <code>DefaultReactiveOAuth2AuthorizedClientManager</code>.
- **Spring Security Reference — Session Management, CSRF Protection, and Logout:** distinguishing browser sessions, authorization, and cleanup.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Access Token, and Refresh Token Grants.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** protecting the Authorization Code Flow.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoking tokens at the Authorization Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token rotation, replay protection, and OAuth security.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token, state/nonce, and UserInfo.
- **Specific Authorization Server documentation:** token lifetimes, refresh rotation, reuse-detection policies, consent/reauthorization, and revocation semantics; verify against your integrated provider.
