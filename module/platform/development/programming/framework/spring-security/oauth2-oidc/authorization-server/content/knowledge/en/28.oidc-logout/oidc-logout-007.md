# SessionRegistry and Session Tracking for Logout

An OpenID Provider (OP) needs to know which login sessions exist in order to log out the right user and the right session. When an End-User opens multiple tabs, logs in from multiple browsers, or uses multiple devices, a single account can hold multiple concurrent HTTP sessions. If the OP only knows about access tokens without tracking login sessions, logging out in the current browser may fail to terminate the right session; logging out one session could also inadvertently affect all of the user's sessions.

In Spring Authorization Server, **Spring Security SessionRegistry** is the component that tracks authenticated sessions. When OIDC is enabled, `SessionRegistry` is used by the OAuth2 Authorization Endpoint's default `SessionAuthenticationStrategy` to register new sessions. When an End-User requests RP-Initiated Logout, `OidcLogoutAuthenticationProvider` uses the registry to locate the `SessionInformation` attached to the user logging out; the logout success handler performs the logout operation.

This lesson belongs to the **OIDC Logout** chapter, module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. The module scope is learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot applications. The focus of this lesson is `SessionRegistry`, the `HttpSession` lifecycle, how Spring Authorization Server registers sessions, and how session data is used during logout.

> **Point to Remember:** `SessionRegistry` is an index tracking principals and session IDs. It is not a store holding full `HttpSession` contents, not a token store, and does not automatically revoke all access tokens/refresh tokens on browser logout.

## 1. Why Must the Authorization Server Track Sessions?

In the Authorization Code Flow, the End-User interacts with a browser to log in at the OP. After authentication, the OP creates or reuses an `HttpSession` to maintain login state. Subsequent authorization requests can reuse that session without prompting the user to re-enter their password.

For example, a user logs in on:

- A laptop browser;
- A mobile browser;
- A separate browser profile for an admin environment.

These are distinct `HttpSession`s, even with the same principal. When the user chooses to log out in one browser, the OP needs to identify the current session and handle the exact logout scope. When a session expires or is invalidated, its tracking information must also be cleaned up from the registry.

### 1.1. Distinguishing Session and Token Types

| Component | Where Is It Stored? | Meaning |
|---|---|---|
| OP `HttpSession` | Servlet container or Spring Session | End-User's login session at the Authorization Server |
| `SessionInformation` | `SessionRegistry` | Metadata about principal, session ID, last request, and expired status |
| OAuth2 Authorization | `OAuth2AuthorizationService` | Authorizations and issued tokens |
| ID Token | Received by RP from the token endpoint | OIDC proof of authentication and subject |
| Access Token | Sent by Client/RP to Resource Server | Credential for accessing protected resources |
| RP local session | Client application | User's login session at each Relying Party |

Do not conflate an OP session with an RP session. A user can log into the OP once and create multiple RP sessions across different applications. `SessionRegistry` in Spring Authorization Server tracks authenticated sessions at the OP.

### 1.2. Logout Must Define Scope

A logout action can carry different meanings:

- Ending the current browser session at the OP;
- Ending all OP sessions for an End-User;
- Asking one RP to end the user's session;
- Notifying multiple RPs of logout via front-channel or back-channel;
- Revoking access/refresh tokens according to policy.

These actions can be coordinated, yet they are not automatically equivalent. Define the scope clearly before designing session tracking.

## 2. What Is SessionRegistry?

`org.springframework.security.core.session.SessionRegistry` is the interface managing known `SessionInformation` entries. `SessionRegistryImpl` is Spring Security's default implementation.

Conceptually, the registry maintains two lookup directions:

~~~text
principal  -> list of session IDs
session ID -> SessionInformation(principal, lastRequest, expired)
~~~

This allows the application to look up sessions by user or inspect details of a specific session.

### 2.1. The Registry Is Not a Session Store

`SessionRegistryImpl` does not store the full `SecurityContext`, request attributes, session attributes, or `HttpSession` business data. It only retains information needed for session management. Invalidation still requires the Servlet API, Spring Session, or appropriate logout handlers.

For example:

- `SessionRegistry` knows session ID `S1` belongs to principal `user-42`;
- The Servlet container or Spring Session holds the actual contents of `S1`;
- The logout handler uses the session ID to terminate the session;
- When the session is destroyed, a lifecycle event helps the registry delete the corresponding record.

If the registry still holds a record after the actual session expired, the registry data is stale. Conversely, if a session still exists yet the registry lacks a record, logout/concurrent-session logic may fail to locate the session.

### 2.2. Default SessionRegistryImpl

`SessionRegistryImpl` maintains in-memory data structures inside the JVM and listens to session lifecycle events. It is a good fit for single-node applications or development/test environments.

When OIDC is enabled in Spring Authorization Server:

- If no `SessionRegistry` bean exists, the framework uses `SessionRegistryImpl`;
- If the application declares its own `SessionRegistryImpl` bean, it must register `HttpSessionEventPublisher` to deliver session lifecycle events;
- If Spring Security Concurrent Session Control is also used, share a single `SessionRegistry` bean.

## 3. Session Registration and Termination Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant B as Browser
    participant OP as Authorization Server
    participant STR as SessionAuthenticationStrategy
    participant SR as SessionRegistry
    participant E as HttpSessionEventPublisher

    U->>B: Open authorization request
    B->>OP: GET authorization endpoint
    OP->>OP: Check SecurityContext / login
    OP->>STR: Handle session after authentication
    STR->>SR: registerNewSession(sessionId, principal)
    SR-->>STR: Session is tracked
    OP-->>B: Proceed with consent / authorization response
    Note over U,SR: User continues using OP session
    U->>B: Logout / session times out
    B->>OP: Logout or HttpSession invalidated
    OP->>OP: Logout handlers / session invalidation
    OP->>E: Servlet session lifecycle event
    E->>SR: SessionDestroyedEvent
    SR->>SR: remove session information
~~~

Spring Authorization Server ties session registration to the OAuth2 Authorization Endpoint's default `SessionAuthenticationStrategy`. Therefore, preserve the proper filter chain and session strategy when customizing the Authorization Server. If you replace the default strategy, ensure session registration logic is still executed.

## 4. Key SessionRegistry APIs

| Method | Purpose |
|---|---|
| `registerNewSession(sessionId, principal)` | Registers a new session for a principal |
| `getSessionInformation(sessionId)` | Retrieves `SessionInformation` by session ID |
| `getAllSessions(principal, includeExpiredSessions)` | Lists sessions for a principal |
| `getAllPrincipals()` | Retrieves known principals |
| `refreshLastRequest(sessionId)` | Updates the last request timestamp |
| `removeSessionInformation(sessionId)` | Removes the session record from the registry |

Example looking up sessions:

~~~java
List<SessionInformation> sessions =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation session : sessions) {
    String sessionId = session.getSessionId();
    Date lastRequest = session.getLastRequest();
    boolean expired = session.isExpired();
}
~~~

This is an example of using the API to inspect sessions. Never expose raw session IDs to end users or write them to public logs; session IDs are sensitive data that can enable session hijacking.

### 4.1. Finding a Session by ID

~~~java
SessionInformation information =
    sessionRegistry.getSessionInformation(sessionId);

if (information != null && !information.isExpired()) {
    Object principal = information.getPrincipal();
    // Apply policy or inspect the identified session.
}
~~~

`getSessionInformation` can return a session already marked expired. A destroyed session is no longer returned once the lifecycle event has been processed.

### 4.2. Removing a Registry Record

~~~java
sessionRegistry.removeSessionInformation(sessionId);
~~~

This method only deletes the entry from the registry. It **does not replace** `HttpSession.invalidate()` or deleting the session from a Spring Session repository. Removing only the registry record can leave the actual session active.

## 5. SessionInformation Lifecycle

Spring Security distinguishes three states:

| State | Meaning |
|---|---|
| **Active** | Session is tracked and has not been marked for termination |
| **Expired** | Spring Security intends to terminate the session, e.g., due to concurrent session limits |
| **Destroyed** | The actual session was invalidated or destroyed by the servlet container |

### 5.1. expireNow() Does Not Directly Invalidate the Session

~~~java
SessionInformation information =
    sessionRegistry.getSessionInformation(sessionId);

if (information != null) {
    information.expireNow();
}
~~~

`expireNow()` marks the session as expired. With Concurrent Session Control, `ConcurrentSessionFilter` detects this status on the next request, invokes logout handlers, and typically invalidates the session. It does not mean the Servlet container destroyed the session at the exact moment of the call.

This distinction matters when implementing logout:

- Marking expired is a state change in the registry;
- Invalidating is an operation on the session store/container;
- The destroyed event is the lifecycle signal to clean up the record;
- Logout handlers can clear `SecurityContext`, cookies, and related state.

Do not use `expireNow()` as a blanket substitute for the full logout workflow.

### 5.2. Session Timeout and Explicit Logout

A session can end due to user-initiated logout, inactivity session timeout, administrator/security policy termination, concurrent session policy marking it expired, or the servlet container/session store destroying the session.

All of these paths should update the registry consistently. If any path bypasses lifecycle events, stale records can accumulate.

## 6. When Does Spring Authorization Server Use SessionRegistry?

When OIDC 1.0 is enabled, Spring Authorization Server uses `SessionRegistry` to track authenticated sessions. The default `SessionAuthenticationStrategy` associated with the OAuth2 Authorization Endpoint registers new sessions. When an End-User requests OIDC Logout, `OidcLogoutAuthenticationProvider` uses the registry to look up `SessionInformation` associated with the End-User logging out.

Related components:

| Component | Role |
|---|---|
| `OAuth2AuthorizationServerConfigurer` | Enables and configures protocol endpoints |
| OIDC configurer | Enables OIDC endpoints, including the Logout Endpoint |
| `SessionAuthenticationStrategy` | Registers authenticated sessions during authorization |
| `SessionRegistry` | Looks up principal/session metadata |
| `OidcLogoutAuthenticationProvider` | Authenticates RP-Initiated Logout requests and looks up sessions |
| `OidcLogoutAuthenticationSuccessHandler` | Handles logout after the provider succeeds |
| `HttpSessionEventPublisher` | Publishes session lifecycle events for the registry |

`OidcLogoutAuthenticationProvider` accepts `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `SessionRegistry` in its constructor. This shows that logout requires combining client registration, authorization state, and session tracking.

### 6.1. Enabling OIDC on the Authorization Server

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is the filter chain skeleton for Spring Authorization Server 1.5.x. The application still needs beans for `RegisteredClient`, authorization/token services, issuer, signing keys, and application login.

### 6.2. The AS Logout Endpoint Is Not Every Application's Logout Endpoint

The Authorization Server's OIDC Logout Endpoint serves RP-Initiated Logout at the OP. It processes requests per OIDC using the OP login session. The logout URL inside a Spring Security OAuth2 Client application is a separate mechanism serving the RP's local session.

## 7. Declaring SessionRegistryImpl and HttpSessionEventPublisher

If the application wants to explicitly share the same registry between OIDC logout and concurrent-session control, declare:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

`HttpSessionEventPublisher` translates Servlet `HttpSession` lifecycle events—such as session created, destroyed, and session ID changed—into Spring application events. `SessionRegistryImpl` listens to session events to update tracking data.

### 7.1. Why Is the Publisher Needed?

When a session times out or is invalidated, `SessionRegistryImpl` needs to receive the event to remove `SessionInformation`. Without the publisher, records for dead sessions can linger in the registry. Consequences can include:

- `getAllSessions` returning stale data;
- Concurrent session limits miscounting old sessions;
- Logout lookups failing to find the real session or seeing invalid records;
- Memory growth from uncollected records.

### 7.2. Spring Boot and Servlet Listeners

In Spring Boot configuration, declaring `HttpSessionEventPublisher` via `@Bean` as shown is the approach guided by Spring Authorization Server. In manually configured servlet applications, the listener can be registered in the deployment descriptor or via the servlet context per your deployment model.

Do not register multiple publishers for the same servlet context without clear reason; duplicate event processing can complicate lifecycle diagnostics.

## 8. Principals Must Be Stable for Accurate Registry Lookups

`SessionRegistryImpl` groups sessions by principal. A principal used as a key must have stable `equals()` and `hashCode()` throughout the time it is registered.

Recommendations:

- Use a principal object representing a stable user identity;
- Base `equals()`/`hashCode()` on a stable identifier, not a mutable display name;
- Do not use raw access tokens as principals;
- Do not instantiate a fresh object per request without equality semantics;
- In custom distributed registries, normalize principals into a consistent string key.

For example, a custom principal can use an immutable internal subject:

~~~java
public final class ApplicationPrincipal implements UserDetails {

    private final String userId;
    private final String username;

    public ApplicationPrincipal(String userId, String username) {
        this.userId = userId;
        this.username = username;
    }

    public String getUserId() {
        return this.userId;
    }

    @Override
    public String getUsername() {
        return this.username;
    }

    // equals() and hashCode() must use the stable userId.
    // Other UserDetails methods are implemented per application policy.
}
~~~

This is an illustrative skeleton; a production `UserDetails` must implement the full contract. The key point is that the identifier used to group sessions does not change when a display name or email is updated.

## 9. Combining with Concurrent Session Control

Spring Security can limit the number of concurrent sessions for a principal. Both Concurrent Session Control and OIDC logout need to look up sessions, so Spring Authorization Server recommends sharing a single `SessionRegistry` bean when enabling both features.

Example application login chain:

~~~java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        SessionRegistry sessionRegistry) throws Exception {

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
            .maximumSessions(2)
            .sessionRegistry(sessionRegistry)
        );

    return http.build();
}
~~~

This example limits each principal to two sessions. Depending on the application, choose `maxSessionsPreventsLogin(true)` to reject new logins or allow new logins and mark old sessions expired. Choose a policy fitting both UX and security.

### 9.1. Truly Sharing the Registry

Do not create one `SessionRegistryImpl` for the Authorization Server and another registry for Concurrent Session Control. If the two filter chains use different instances, one side can register sessions while the other cannot see them.

Inject the same bean via method parameters to guarantee the exact same instance is used.

### 9.2. Session Fixation Protection

Spring Security includes session fixation protection and can rotate the session ID after authentication. The registry must keep up with session ID changes. Never store a session ID in a database once and assume it never changes. Use lifecycle events and supported session management mechanisms to maintain the mapping.

## 10. RP-Initiated Logout Using Session Tracking

According to OIDC RP-Initiated Logout, the RP navigates the User Agent to the OP's Logout Endpoint. The URL is usually obtained from `end_session_endpoint` in the OpenID Provider Configuration.

The request may contain:

| Parameter | Meaning |
|---|---|
| `id_token_hint` | ID Token previously issued by the OP to the RP; recommended to hint at the End-User/session |
| `post_logout_redirect_uri` | URI the RP wants the browser returned to after logout |
| `state` | Value sent by the RP to correlate the response with the logout request |
| `client_id` | May be used in appropriate cases per the OIDC Logout specification |
| `logout_hint` | Hint identifying the End-User per supported extensions/policies |

Redirect example:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=RANDOM_STATE HTTP/1.1
Host: identity.example.com
~~~

The URL and endpoint path in the example depend on the OP's actual `end_session_endpoint`. Do not hardcode the path if the RP can retrieve it from discovery.

### 10.1. From Logout Request to SessionInformation

In Spring Authorization Server:

1. `OidcLogoutEndpointFilter` receives the RP-Initiated Logout request.
2. `OidcLogoutAuthenticationConverter` converts the HTTP request into `OidcLogoutAuthenticationToken`.
3. `OidcLogoutAuthenticationProvider` validates the request, coordinating `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `SessionRegistry`.
4. The provider looks up `SessionInformation` associated with the End-User requesting logout.
5. `OidcLogoutAuthenticationSuccessHandler` processes logout after authentication succeeds.
6. Logout handlers terminate the OP session and redirect per response/redirect policy.

`SessionRegistry` is what lets the provider find the right registered session. If the registry lacks data or holds stale data, logout may fail to locate the expected session.

### 10.2. Redirect URI Must Be Validated

Spring Authorization Server includes a default `OidcLogoutAuthenticationValidator` to check `post_logout_redirect_uri`. This value must match the post-logout redirect URIs registered for the client. Never accept an arbitrary URL from a query parameter; otherwise, the endpoint can become an open redirect.

If changing validation, custom validators must throw `OAuth2AuthenticationException` when a request is invalid. Never skip validation just to avoid redirect errors.

## 11. OP Session Logout Does Not Mean Token Revocation

`SessionRegistry` tracks the End-User's login sessions at the OP. When RP-Initiated Logout terminates `HttpSession`, the user no longer has that browser session to continue authorization without logging in again. However, this action does not automatically guarantee that all access tokens or refresh tokens have been revoked.

| Resource | Impact When OP `HttpSession` Logs Out |
|---|---|
| Browser session at OP | Logged out/invalidated by logout handler |
| `SessionInformation` | Cleaned up when lifecycle event is published and processed |
| Authorization record | Still managed by `OAuth2AuthorizationService` |
| Issued JWT access token | May remain valid until `exp` unless additional revocation/denylist mechanisms exist |
| Opaque access token | Can be evaluated as inactive by introspection if authorization/token state is revoked |
| Refresh token | Requires a separate revocation policy per authorization/session lifecycle |
| RP local session | Requires front-channel/back-channel notifications or RP self-logout |

Therefore, design logout as coordinated actions: terminate the OP session, handle authorization/token state per policy, and notify RPs if the deployment supports logout propagation. Never treat `SessionRegistry` as a token revocation store.

### 11.1. When Must Authorizations or Refresh Tokens Be Revoked?

Some systems require that when a user logs out, refresh tokens associated with that session can no longer be used to mint new access tokens. In that case, the application must link authorizations/tokens to the session or have an explicit policy to revoke related tokens. This must be designed with `OAuth2AuthorizationService` and the token lifecycle.

Do not revoke all authorizations of the same subject if policy only intends to end a single browser session. A user might be logged in on another device or have another client that should keep working.

### 11.2. JWT Access Tokens Can Live On

Resource Servers verifying JWTs offline typically check signature, issuer, audience, and expiry. Invalidating the OP `HttpSession` does not alter already-issued JWT signatures. If logout must take effect immediately for JWTs, use an additional mechanism such as a token denylist, introspection, token version/session state checks, or short access-token lifetimes aligned with your threat model.

## 12. Distinguishing RP-Initiated, Front-Channel, and Back-Channel Logout

OIDC defines logout mechanisms with distinct purposes:

| Mechanism | Who Initiates? | Transport | Purpose |
|---|---|---|---|
| RP-Initiated Logout | RP | Browser redirect to OP | RP asks OP to log out the End-User |
| Front-Channel Logout | OP | Browser/User Agent | OP notifies RPs of logout through the browser |
| Back-Channel Logout | OP | Server-to-server HTTP | OP sends a Logout Token directly to the RP |
| Local application logout | Application | Local session/logout handler | Ends the session at that specific application |

RP-Initiated Logout is a request from the RP to the OP. Front-channel and back-channel are mechanisms for the OP to notify RPs. They can be used independently or combined based on OP and RP capabilities.

### 12.1. Back-Channel Logout Uses a Logout Token

When the OP supports Back-Channel Logout, the OP sends an HTTP POST to the RP's registered back-channel logout URI. The body contains a `logout_token` parameter holding a signed JWT identifying the user/session to terminate.

The Logout Token must be validated by the RP, including key items:

- Signature and algorithm;
- Issuer and audience;
- Issued-at;
- `jti` (unique identifier of the Logout Token);
- Presence of the `events` claim with the back-channel logout event URI;
- Presence of at least one of `sub` or `sid`;
- Absence of `nonce`;
- Optional checking of previously seen `jti` values to prevent replay.

If the Logout Token contains `sid`, the RP ends sessions linked to that OP session. If only `sub` is present, the RP ends the End-User's sessions at the RP per the specification's semantics.

### 12.1.1. Discovery and Client Registration for Back-Channel Logout

The OP can publish boolean metadata fields:

- `backchannel_logout_supported`: OP supports Back-Channel Logout;
- `backchannel_logout_session_supported`: OP can include `sid` in Logout Tokens; when supported, `sid` is also included in corresponding ID Tokens.

The RP registers `backchannel_logout_uri`. If the RP requires `sid` in Logout Tokens, client registration can declare `backchannel_logout_session_required`. Advertise support only when the OP actually tracks logged-in RPs and can deliver valid Logout Tokens to registered URIs.

`SessionRegistry` at the OP does not implement all of Back-Channel Logout by itself. It tracks OP `HttpSession`s; storing the list of logged-in RPs, issuing Logout Tokens, and sending requests to `backchannel_logout_uri` belong to a separate workflow.

### 12.2. sid Is Not the Servlet Session ID

OIDC `sid` is a session identifier issued by the OP and meaningful within the issuer's scope. A Servlet session ID is an `HttpSession` identifier at a single application/container. The two values can be linked in a mapping, yet must not be treated as the exact same value.

`SessionRegistry` at the OP tracks the principal and the OP's servlet session ID. To handle Back-Channel Logout at the RP, the RP application needs its own registry mapping OIDC provider sessions (`sid`) and client registrations to RP local sessions.

### 12.3. Do Not Confuse the OP's SessionRegistry with the RP's OidcSessionRegistry

| Registry | Where Does It Live? | What Does It Track? |
|---|---|---|
| Spring Security `SessionRegistry` | Authorization Server / OP | Authenticated `HttpSession`s at the OP |
| Spring Security `OidcSessionRegistry` | OAuth2 Client / RP | Mapping between OP session IDs and local RP sessions |
| Spring Session repository | Application using Spring Session | Actual session contents and lifecycle |

Spring Security OAuth2 Client has `OidcSessionRegistry` to support Back-Channel Logout. That is a different abstraction from the `SessionRegistry` used by Spring Authorization Server in RP-Initiated Logout. Do not mistakenly inject the RP's registry into the Authorization Server.

## 13. SessionRegistry in Multi-Node Environments

`SessionRegistryImpl` stores data inside a single JVM's memory. If the Authorization Server runs across multiple pods, each node can end up with its own registry:

~~~text
Browser -> Load Balancer -> Node A (SessionRegistry A)
                         -> Node B (SessionRegistry B)
                         -> Node C (SessionRegistry C)
~~~

Suppose the login/authorization request hits Node A and the session is registered in registry A. Later, the logout request hits Node B. If Node B does not see the record, the OIDC Logout Provider may fail to find the expected `SessionInformation`.

Sticky sessions can reduce the probability of requests switching nodes, yet they do not replace a shared registry/session store. Nodes can restart, fail over, or receive requests routed elsewhere.

### 13.1. Options

| Solution | Characteristics | Suitable For |
|---|---|---|
| Per-node `SessionRegistryImpl` | Simple, in-memory | Single node, dev/test |
| Shared/custom `SessionRegistry` | Registry state shared via database/cache | Clusters needing consistent lookup |
| Spring Session + `SpringSessionBackedSessionRegistry` | Session data and lookup backed by Spring Session repository | Clusters using Redis/JDBC or compatible repositories |
| Custom session index | Stores custom principal/session mappings and metadata | Multi-tenant or complex logout policies |

### 13.2. Spring Session and SpringSessionBackedSessionRegistry

Spring Session provides `FindByIndexNameSessionRepository` and `SpringSessionBackedSessionRegistry`. This implementation retrieves `SessionInformation` from Spring Session instead of maintaining a separate in-memory map, enabling concurrent-session management in clustered environments.

Conceptual configuration example:

~~~java
@Bean
SessionRegistry sessionRegistry(
        FindByIndexNameSessionRepository<? extends Session> sessionRepository) {

    return new SpringSessionBackedSessionRegistry<>(sessionRepository);
}
~~~

The exact generic type may need adjustment for your repository (such as `RedisIndexedSessionRepository` or `JdbcIndexedSessionRepository`). Crucially, the repository must support looking up sessions by principal index.

### 13.3. Principal Index Must Be Populated

`FindByIndexNameSessionRepository` defines `PRINCIPAL_NAME_INDEX_NAME` to look up sessions by principal name. Spring Session does not automatically understand every authentication mechanism; the application must ensure the principal index is populated.

`SpringSessionBackedSessionRegistry` must also produce the exact same string representation of the principal that the repository indexed. If the Authentication principal is normalized to a user ID while the session repository indexes by username, lookups can return empty even though the session exists.

Tests must cover logging in on node A, logging out/looking up on node B, querying sessions by principal index, invalidating a session and verifying the repository no longer returns it, and rotating session IDs while verifying the mapping updates.

### 13.4. Synchronizing the Session Store and Registry

If a custom registry resides in Redis while `HttpSession` remains stored in each node's local memory, the registry can point to a session the current node cannot invalidate. Session tracking and session storage must use a consistent architecture: either a shared distributed store or a mechanism routing to the right node/session owner.

## 14. Designing a Custom SessionRegistry

Implement a custom registry only when there is a clear requirement such as multi-node, multi-tenant, session auditing, or custom lookup policies. The implementation must satisfy `SessionRegistry`'s contract and must not return inconsistent results across methods.

### 14.1. Data to Store

| Field | Purpose |
|---|---|
| `session_id` | Actual session identifier, protected like a secret |
| `principal_key` | Stable subject/user identifier |
| `created_at` | Registration timestamp |
| `last_request_at` | Last observed request |
| `expired` | Flag indicating expired status |
| `tenant_id` | Tenant partition if application is multi-tenant |
| `node/owner` | Only if routing to the session owner is required |

Do not store access tokens or refresh tokens in the session registry merely for logout convenience. Token lifecycle belongs to the authorization/token service.

### 14.2. Contract and Concurrency

A custom registry must guarantee:

- `registerNewSession` handles existing session IDs according to a clear rule;
- `getAllSessions` never returns destroyed sessions;
- `getSessionInformation` returns the right session or `null`;
- `refreshLastRequest` never revives an expired/destroyed session;
- `removeSessionInformation` is idempotent;
- Principal normalization is identical across all nodes;
- Session ID rotation updates mappings atomically;
- Timeout/invalidation cleanup can safely run repeatedly;
- Concurrent operations never create two conflicting records.

### 14.3. TTL Must Not Outlive or Undercut the Session Lifecycle

If using a Redis/database index, the registry record's TTL must match session timeout and session renewal. Prematurely expired registry records cause logout lookups to fail; records living too long cause stale sessions and increase memory/data-retention risk.

A cleanup job is useful as a safety net, yet the source of truth must remain the session repository/container. A cleanup job should not delete a record based purely on age if the actual session is still active.

## 15. Testing SessionRegistry

Tests should cover the registry contract, servlet lifecycle, and the OIDC Logout Endpoint. Unit testing `SessionRegistry` alone does not prove the filter chain and logout handlers are actually wired together.

### 15.1. Unit Testing Registration and Lookup

~~~java
class SessionRegistryTests {

    private final SessionRegistry registry = new SessionRegistryImpl();

    @Test
    void registersAndFindsSessionForPrincipal() {
        Object principal = "user-42";
        registry.registerNewSession("session-1", principal);

        SessionInformation information =
            registry.getSessionInformation("session-1");

        assertThat(information).isNotNull();
        assertThat(information.getPrincipal()).isEqualTo(principal);
        assertThat(registry.getAllSessions(principal, false)).hasSize(1);
    }

    @Test
    void removesSessionInformation() {
        registry.registerNewSession("session-1", "user-42");
        registry.removeSessionInformation("session-1");

        assertThat(registry.getSessionInformation("session-1")).isNull();
    }
}
~~~

This is a unit test example for the registry API. It does not create a real `HttpSession` and does not verify `HttpSessionEventPublisher`.

### 15.2. Testing Session Lifecycle Events

Integration tests should:

1. Create an authenticated `HttpSession`;
2. Verify `SessionRegistry` holds `SessionInformation`;
3. Call `HttpSession.invalidate()`;
4. Verify `HttpSessionEventPublisher` publishes the event;
5. Verify `SessionRegistryImpl` deletes the record after the event.

In addition to explicit invalidation, test session timeout in a servlet container or test environment supporting session expiry. Session timeout is a common source of stale records if the lifecycle publisher is not configured.

### 15.3. Testing OIDC RP-Initiated Logout

A complete integration test should:

- Enable OIDC in the Authorization Server filter chain;
- Create a `RegisteredClient` with a valid post-logout redirect URI;
- Run the authorization flow to establish an OP session and registry record;
- Send a logout request with `id_token_hint` and a valid `post_logout_redirect_uri`;
- Verify the success handler ends the OP session;
- Verify the session lifecycle event cleans up the registry record;
- Send an unregistered redirect URI and verify the request is rejected.

Do not merely mock `OidcLogoutAuthenticationProvider`, because the goal is to verify session registration, provider lookup, validation, and the logout handler together.

A MockMvc test can verify invalid redirect URIs:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OidcLogoutSessionIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsUnregisteredPostLogoutRedirectUri() throws Exception {
        MockHttpSession session = authenticatedOpSession();
        String idTokenHint = registeredClientIdToken();

        mvc.perform(get("/connect/logout")
                .session(session)
                .param("id_token_hint", idTokenHint)
                .param("post_logout_redirect_uri",
                    "https://attacker.example/"))
            .andExpect(status().isBadRequest());
    }
}
~~~

This is a test skeleton for the default endpoint. `authenticatedOpSession` and `registeredClientIdToken` are fixtures created by the test application; matching `RegisteredClient`, ID Token/authorization records, and session registry records are required. If your deployment changes the logout endpoint path or error entry point, adjust the URI/status assertions to match your real configuration.

Happy-path MockMvc tests must also confirm that the session is invalidated and the record is cleaned up after the lifecycle event fires. To verify real servlet listeners and timeouts, supplement with tests running an embedded servlet container rather than relying solely on `MockHttpSession`.

### 15.4. Testing Token Lifecycle Separately

After logout, check access/refresh tokens according to your chosen policy. If the system claims logout revokes refresh tokens, verify token state in `OAuth2AuthorizationService` or via introspection. Never infer that tokens were revoked merely because the browser was redirected to a logged-out page.

## 16. Issues and Diagnostics

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Logout cannot find the session | Session not registered or principal mismatch | `SessionAuthenticationStrategy`, principal `equals`/`hashCode` |
| `SessionRegistry` retains record after timeout | Missing `HttpSessionEventPublisher` or event not reaching registry | Check listener and `SessionDestroyedEvent` |
| Concurrent session limit miscounts | Two registry instances or stale records | Share bean and lifecycle cleanup |
| Logout succeeds on node A but fails on node B | Per-node in-memory `SessionRegistryImpl` | Distributed registry/session repository |
| Session ID changes yet old lookup lingers | Session fixation event not handled | `HttpSessionIdChangedEvent` and session tracking |
| Multiple logins by different users collide | Non-unique/unstable principal key | Use a stable user identifier |
| Logout redirects to unknown host | `post_logout_redirect_uri` not properly allowlisted | `RegisteredClient.postLogoutRedirectUris` |
| OP logs out yet RP remains logged in | Missing front/back-channel propagation or RP local logout | OIDC logout notification |
| Browser logs out yet access token still works | Session logout does not automatically revoke JWTs | Token revocation/introspection policy |
| Spring Session repository cannot find session | Principal index not populated | `PRINCIPAL_NAME_INDEX_NAME` and principal resolver |

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking `SessionRegistry` is an `HttpSession` store | No way to invalidate actual sessions | Pair registry with Servlet/Spring Session |
| Omitting `HttpSessionEventPublisher` for `SessionRegistryImpl` | Stale session records | Publish session lifecycle events |
| Creating a separate registry per filter chain | Session registration and logout lookup diverge | Inject a single shared bean |
| Using `SessionRegistryImpl` in a cluster without sharing | Other nodes cannot find sessions | Shared/custom registry or Spring Session |
| Using a mutable principal as map key | Cannot find sessions after principal mutates | Stable `equals`/`hashCode` |
| Calling `removeSessionInformation` and assuming logout completed | `HttpSession` can stay active | Invalidate session via logout handler |
| Using `expireNow` as invalidation | Session is only marked expired | Use proper logout/session invalidation flow |
| Assuming logout revokes all JWTs | Access tokens may stay valid until `exp` | Design separate token revocation/denylist |
| Confusing OP `SessionRegistry` with RP `OidcSessionRegistry` | Logs out the wrong session layer | Distinguish OP and RP roles |
| Allowing arbitrary post-logout redirects | Open redirect | Check against `RegisteredClient` allowlist |
| Logging raw session IDs | Session hijacking if logs leak | Redact session identifiers |

## 18. Security and Privacy

Session tracking directly affects session hijacking risk and user-identifying data. You must:

- Never log raw session IDs, cookies, or access tokens;
- Never place session IDs in URLs, analytics, or tracing tags;
- Protect `SessionRegistry`/session repositories with internal access controls;
- Use HTTPS and appropriate cookie flags such as `Secure`, `HttpOnly`, and `SameSite` per flow;
- Ensure session ID rotation after authentication per session fixation policy;
- Control post-logout redirect URIs via client registration;
- Never allow clients to self-declare principal/session IDs to log out other users;
- Restrict access to admin APIs that list or terminate sessions;
- Emit logout audit events without credentials;
- Purge session tracking data per retention policy.

### 18.1. Do Not Expose Session Existence

Admin APIs that query sessions require dedicated authentication and authorization. Never expose a public endpoint allowing callers to probe session IDs and learn whether a session exists.

### 18.2. Logout Must Be Idempotent

Users may log out multiple times, a session may have expired before the request arrives, or events may be processed repeatedly. Logout handlers and registry cleanup must tolerate sessions that no longer exist. Do not turn an already-destroyed session into a fatal error or resurrect old records.

## 19. Operations and Monitoring

Monitor the session lifecycle using metrics that contain no session IDs or PII:

| Metric/Event | Meaning |
|---|---|
| `oidc_sessions_registered_total` | Number of sessions registered |
| `oidc_sessions_destroyed_total` | Number of sessions cleaned up |
| `oidc_logout_requests_total` | Number of RP-Initiated Logout requests |
| `oidc_logout_failures_total` | Logout validation/provider failures |
| `session_registry_lookup_misses_total` | `SessionInformation` not found |
| `session_registry_stale_records` | Suspected stale records if cleanup checks run |
| `concurrent_sessions_rejected_total` | Logins rejected due to session limits |
| `session_store_lookup_latency` | Session store lookup latency |

### 19.1. Audit Events

A useful audit record can include:

- Event type: login, logout requested, logout completed, session expired;
- Authenticated client ID if available;
- Pseudonymized principal identifier;
- Timestamp and correlation ID;
- Outcome and error code;
- Logout scope: current session or all sessions if supported by the application.

Never record raw session IDs, cookie values, ID Tokens, refresh tokens, or access tokens.

### 19.2. Suggested Alerts

- Unusual spike in `SessionRegistry` lookup misses;
- `SessionDestroyedEvent` counts mismatched with session expirations/invalidations;
- Logout failures increasing after deployment;
- Unusual divergence in session registry counts across nodes;
- Rising Spring Session repository lookup latency or errors;
- Tokens remaining active after logout beyond the defined revocation SLA.

## 20. Production Checklist

1. **OIDC enabled:** Is the OIDC configurer enabled on the Authorization Server?
2. **Registry bean:** Is a single `SessionRegistry` instance shared between logout and concurrent-session control?
3. **Registration:** Does the default `SessionAuthenticationStrategy` still register authenticated sessions?
4. **Lifecycle:** Does `SessionRegistryImpl` have `HttpSessionEventPublisher`?
5. **Principal:** Is the principal key stable with proper `equals`/`hashCode`?
6. **Session store:** Do the registry and `HttpSession` store share a consistent data source?
7. **Cluster:** Does a multi-node deployment use a shared registry/session repository?
8. **Session ID:** Are session fixation protection and ID rotation tracked properly?
9. **Logout endpoint:** Is RP-Initiated Logout enabled and validated?
10. **Redirect:** Does `post_logout_redirect_uri` match the registered allowlist?
11. **Logout scope:** Is the current-session vs. all-sessions policy clearly defined?
12. **Token lifecycle:** Is there a separate policy for access/refresh tokens after logout?
13. **RP propagation:** Is front/back-channel logout implemented if ecosystem-wide SSO logout is required?
14. **Security:** Are session IDs/cookies/tokens excluded from logs and admin session APIs protected?
15. **Testing:** Are registration, invalidation, timeout, logout, and cluster failover covered by tests?
16. **Monitoring:** Are metrics/alerts configured for lookup misses, stale records, and logout failures?

## 21. Practice Scenarios

**Scenario A — Stale Session:** A user logs out, yet `SessionRegistry` still holds `SessionInformation`. Check `HttpSessionEventPublisher`, session invalidation, and `SessionDestroyedEvent`. Write a test proving the record is cleaned up.

**Scenario B — Two Nodes:** A user logs in through node A, and the load balancer routes the logout request to node B. Why might `SessionRegistryImpl` fail to find the session? Design a shared registry.

**Scenario C — Concurrent Sessions:** A user is allowed at most two sessions. On a third login, should the policy reject the new login or mark an older session expired? Analyze UX, security, and logout handlers.

**Scenario D — Token Still Active:** The browser has logged out of the OP, yet the Resource Server still accepts the JWT access token. Why can this happen? Choose a suitable mechanism to meet fast logout enforcement requirements.

**Scenario E — OP and RP:** The OP receives RP-Initiated Logout successfully, yet the RP retains its local session. Distinguish `SessionRegistry` at the OP from `OidcSessionRegistry` at the RP and choose front-channel/back-channel propagation.

**Scenario F — Principal Changes Username:** A user changes their username after a session is registered. If `equals`/`hashCode` or the principal index relies on username, how can lookups fail? Propose a stable principal key.

**Hints:** A requires the event publisher and cleanup; B requires a shared registry/session store; C requires choosing a `maximumSessions` policy; D requires token revocation/introspection or an appropriate JWT lifetime; E requires logout notifications to RPs; F should use an immutable user ID as the key.

## 22. Summary

`SessionRegistry` is the component that tracks authenticated sessions in Spring Security. When OIDC is enabled, Spring Authorization Server uses the registry to register sessions at the OAuth2 Authorization Endpoint and lets `OidcLogoutAuthenticationProvider` look up `SessionInformation` when an End-User requests RP-Initiated Logout.

`SessionRegistryImpl` suits single-node applications and requires `HttpSessionEventPublisher` to receive lifecycle events, especially `SessionDestroyedEvent`. When using Concurrent Session Control, share a single registry bean. Principals need stable identities so lookups do not break after objects or user profiles change.

In clustered environments, an in-memory `SessionRegistryImpl` cannot share session state across nodes. You can use Spring Session with `SpringSessionBackedSessionRegistry` or a shared implementation, ensuring principal indexing, the session store, and logout lookups stay consistent.

Finally, OP session logout, RP local logout, and token revocation are distinct actions. Production OIDC logout designs must coordinate session lifecycles, redirect validation, front/back-channel notifications when needed, token lifecycle policies, multi-node testing, and monitoring without leaking session identifiers.

## 23. References

- [Spring Authorization Server — Core Model / Components: SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): how OIDC uses `SessionRegistry`, `SessionAuthenticationStrategy`, and `HttpSessionEventPublisher`.
- [Spring Authorization Server — Protocol Endpoints: OIDC Logout Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcLogoutEndpointConfigurer`, `OidcLogoutAuthenticationProvider`, and logout handlers.
- [Spring Authorization Server API — OidcLogoutAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html): provider, dependencies, and authentication validator.
- [Spring Security API — SessionRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistry.html): operations for looking up and registering sessions.
- [Spring Security API — SessionRegistryImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistryImpl.html): default implementation and session lifecycle events.
- [Spring Security API — SessionInformation](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionInformation.html): active/expired/destroyed states and `expireNow`.
- [Spring Security API — ConcurrentSessionFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/session/ConcurrentSessionFilter.html): refreshing last request and handling expired sessions.
- [Spring Session API — SpringSessionBackedSessionRegistry](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/security/SpringSessionBackedSessionRegistry.html): `SessionRegistry` backed by Spring Session for clustered environments.
- [Spring Session API — FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html): finding sessions by principal name index.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, and `state`.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): Logout Token, `sub`/`sid`, validation, and session termination at the RP.
