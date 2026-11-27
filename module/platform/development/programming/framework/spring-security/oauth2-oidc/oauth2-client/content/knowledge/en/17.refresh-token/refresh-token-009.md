# 17.9. Multiple Requests Concurrently Refreshing the Same Authorized Client

## 1. Context: One Expired Token, Many Requests Arriving Together

In **Spring Security OAuth 2.0/OIDC Client**, an `OAuth2AuthorizedClient` is created after the client receives an access token from the Authorization Server (AS). If the AS also issues a **refresh token**, the OAuth2 Client can use that refresh token to request a new access token when the old access token expires or is about to expire.

In a low-traffic system, the workflow looks simple:

```text
Request A
    -> Look up stored OAuth2AuthorizedClient
    -> Access token is about to expire
    -> POST /token with grant_type=refresh_token
    -> Receive new access token and new refresh token if issued
    -> Save updated OAuth2AuthorizedClient
    -> Call API
```

However, in a real application, **multiple HTTP requests can need the same authorized client at the same time**:

- A browser opens a dashboard page and fires 6 API calls concurrently.
- Multiple AJAX requests from the same account hit multiple threads in Spring MVC.
- A background job and a web request access the same linked account simultaneously.
- An application runs across 4 pods, all reading the authorized client from JDBC.
- WebFlux launches multiple asynchronous tasks requiring the same access token.
- A mobile/web frontend retries a request after a timeout right as the access token nears expiration.

If every request sees the old token before any request manages to persist the new one, they can **simultaneously send multiple refresh requests using the same refresh token**.

### Example scenario

Suppose:

```text
Client registration ID: partner-api
Principal name:         alice-stable-id
Access token:           AT1, expiresAt = 10:00
Refresh token:          RT1
```

At **09:59:10**, multiple requests for Alice simultaneously need to call Partner API. Suppose the refresh provider uses `clockSkew = 60 seconds`, so AT1 is already treated as needing a refresh even though nearly a minute remains.

```text
Request A -> sees AT1 nearing expiry -> refreshes with RT1
Request B -> sees AT1 nearing expiry -> refreshes with RT1
Request C -> sees AT1 nearing expiry -> refreshes with RT1
```

The problem becomes severe when the AS uses **refresh token rotation**: on each successful refresh, the AS can issue a new refresh token and invalidate the old refresh token.

**Lesson objective:** understand this race condition, know where Spring Security manages refreshing, and design a way so **only one refresh operation runs for a given authorized client at a time** in environments that require it.

### After this lesson, you will understand

1. The refresh mechanism of `OAuth2AuthorizedClientManager`, `RefreshTokenOAuth2AuthorizedClientProvider`, and where `OAuth2AuthorizedClient` is stored.
2. Why `clockSkew` causes multiple requests to start refreshing nearly simultaneously.
3. Refresh token rotation and the risks of `invalid_grant`, reuse detection, and revocation.
4. Race conditions when saving new tokens or deleting the authorized client after errors.
5. **Single-flight / per-key lock** solutions within a single JVM.
6. Shared storage, distributed coordination, optimistic concurrency, and fencing solutions across multiple instances.
7. Why **re-reading the authorized client after acquiring the lock** is a critical step.
8. How to use the right manager for Servlet, service/background, and WebFlux contexts.
9. Retry limitations, error handling, and avoiding refresh token exposure.
10. How to verify concurrency with tests and production observability.

All domain names, clients, users, tokens, and timestamps in this lesson are illustrative and do not represent a real provider.

---

## 2. Distinguishing Access Tokens and Refresh Tokens

The two tokens serve different purposes:

| Property | Access token | Refresh token |
|---|---|---|
| Purpose | Access APIs / Resource Servers. | Request a new access token at the Token Endpoint. |
| Recipient | Resource Server matching audience/scope. | Authorization Server / Token Endpoint. |
| Lifetime | Usually shorter. | May be longer or governed by separate policy. |
| Sent to browser? | Depends on client type and architecture; avoid as much as possible in backends. | Highly sensitive; backend must strictly protect it. |
| If leaked | Can be used to access APIs within granted permissions. | Can mint new tokens until revoked or expired. |
| Rotation | Not an inherent requirement. | May be replaced by the AS with a new refresh token after each use. |

Example request to refresh a token:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=refresh_token&refresh_token=RT1
```

Illustrative response when the AS uses rotation:

```json
{
  "access_token": "AT2",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "RT2",
  "scope": "api.read"
}
```

After this response, the backend must save **AT2 together with RT2** per AS policy. Never update only the access token while keeping RT1.

**Not every refresh response includes a new refresh token.** Some AS implementations keep the old token or do not rotate, while other providers enforce strict rotation. Spring Security's token response client and provider construct results based on valid responses, while the rotation policy itself belongs to the Authorization Server.

## 3. Refresh Token Rotation Turns a Race into a Security Risk

An AS supporting rotation typically behaves as follows:

```text
Before refresh:
    Valid refresh token: RT1

Successful refresh:
    Client sends RT1
    AS invalidates RT1
    AS issues RT2
    Client saves RT2

Reusing RT1:
    AS sees the refresh token was already used
    AS returns an error or triggers reuse detection per policy
```

Rotation is not designed to make life harder for clients. It helps **detect refresh token reuse**, which can indicate a stolen token.

RFC 9700 (*OAuth 2.0 Security Best Current Practice*) recommends/requires replay protections—especially for public clients—including refresh token rotation or sender-constrained refresh tokens.

### 3.1. Race between two requests

```mermaid
sequenceDiagram
    autonumber
    participant A as Request A
    participant B as Request B
    participant Store as Authorized Client Store
    participant AS as Authorization Server

    A->>Store: load(partner-api, alice)
    Store-->>A: AT1, RT1
    B->>Store: load(partner-api, alice)
    Store-->>B: AT1, RT1

    A->>AS: POST /token refresh_token=RT1
    AS-->>A: AT2, RT2
    Note over AS: RT1 has been invalidated

    B->>AS: POST /token refresh_token=RT1
    AS-->>B: invalid_grant or reuse detection

    A->>Store: save(AT2, RT2)
    B->>Store: handles failure, may remove()
    Note over Store: Risk of deleting or losing AT2/RT2
```

Both requests can be **legitimate** when they start: both see AT1 needs refreshing and both read RT1. Yet one can be rejected after the other has already consumed RT1.

### 3.2. Possible consequences

- Request B receives `invalid_grant` even though Request A got new tokens.
- A subsequent request fails to find the authorized client because a failure handler deleted the entry.
- Subsequent requests prompt for **fresh authorization**, disrupting the login experience.
- If the AS enforces strict reuse detection, **even the new refresh token RT2 may be revoked** because the AS suspects the token family was compromised.
- New tokens get overwritten by stale data due to unversioned store updates.
- Retries keep resending RT1, making the situation worse.
- The user gets logged out or loses external account connectivity solely due to the application's own concurrency.

Never assume that **because Request A succeeded, RT2 is guaranteed to stay valid** if the AS subsequently detected RT1 reuse. Revocation behavior depends on the AS's replay-detection policy.

## 4. Which Layers of Spring Security Participate in Refreshing?

Key components in a Servlet application:

| Component | Responsibility |
|---|---|
| `ClientRegistrationRepository` | Looks up OAuth2 client configuration. |
| `OAuth2AuthorizedClient` | Holds registration, principal, access token, and optional refresh token. |
| `OAuth2AuthorizedClientRepository` | Reads/saves authorized clients in a Servlet HTTP request context. |
| `OAuth2AuthorizedClientService` | Reads/saves by registration ID and principal name without a Servlet request. |
| `OAuth2AuthorizedClientManager` | Coordinates authorization/re-authorization and persists/deletes results. |
| `RefreshTokenOAuth2AuthorizedClientProvider` | Determines whether refresh is possible/needed and executes the grant. |
| `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | Sends the refresh request to the Token Endpoint. |
| `OAuth2AuthorizationSuccessHandler` | Handles successful authorization, typically saving new tokens. |
| `OAuth2AuthorizationFailureHandler` | Handles failures; may remove the authorized client for specific error codes. |

Diagram:

```mermaid
flowchart TD
    A["N requests need token concurrently"] --> M["OAuth2AuthorizedClientManager"]
    M --> S["AuthorizedClientRepository or Service"]
    S --> E["Existing OAuth2AuthorizedClient: AT1 + RT1"]
    M --> P["RefreshTokenOAuth2AuthorizedClientProvider"]
    P --> Q{"Does access token need refresh?"}
    Q -->|No| R["Keep current authorized client"]
    Q -->|Yes and RT present| T["Token Endpoint: grant_type=refresh_token"]
    T --> U["AT2 + RT2 (per AS)"]
    U --> V["SuccessHandler saves new authorized client"]
    T --> X["OAuth2 error"]
    X --> Y["FailureHandler / policy"]
```

**Important:** the manager and service/repository organize storage, yet **you must not assume the entire load–check–HTTP POST–save sequence is atomically locked across all threads or all instances**.

### 4.1. `RefreshTokenOAuth2AuthorizedClientProvider` decides when to refresh

Class:

```java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
```

This provider normally returns `null` when:

- No authorized client exists yet.
- The authorized client has no refresh token.
- The access token has not reached the refresh threshold.

It executes the refresh grant when an authorized client with a refresh token exists and the access token is considered expired or about to expire per `clockSkew`.

Therefore, **the same stale authorized client can cause multiple provider invocations to decide to refresh concurrently** if called around the same time.

### 4.2. Clock skew opens the refresh window early

Per Spring Security's API, the refresh provider exposes `setClockSkew(Duration)`; the default in many modern versions is **60 seconds**. Tokens are treated as needing refresh as they approach `expiresAt`.

Example:

```text
Access token expiresAt: 14:00:00
Clock skew:             60 seconds

Starting around 13:59:00:
    Incoming requests can trigger refresh.
```

This helps avoid sending near-expired access tokens to APIs, yet it also allows **multiple requests to detect the refresh condition simultaneously**. `clockSkew` is neither a lock nor a single-flight mechanism.

Excessive skew relative to a short token lifetime increases refresh frequency and Token Endpoint traffic. Choose a sensible skew, though **reducing skew does not solve the root race condition**.

### 4.3. Provider returning `null` is not an error

When the token is still valid, the provider typically returns `null`; the manager retains and returns the existing authorized client. When refresh succeeds, the provider returns the new authorized client; the manager saves the result. When the token request fails, exceptions/authorization failures flow through the manager.

Applications should invoke **`OAuth2AuthorizedClientManager.authorize(...)`**, rather than calling `RefreshTokenOAuth2AuthorizedClientProvider.authorize(...)` manually and saving tokens in scattered places unless implementing a very deliberate flow.

## 5. Default Failure Handlers and the Risk of Deleting Fresh Results

An easily overlooked detail in Spring Security:

- `DefaultOAuth2AuthorizedClientManager` (Servlet request context) by default removes the stored authorized client from `OAuth2AuthorizedClientRepository` when authorization fails with **`invalid_grant`**.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` (service/background context) likewise defaults to **removing the stored authorized client** upon receiving `invalid_grant`.

This behavior makes sense with a single request: if the refresh token is invalid, the old entry is no longer usable.

Yet under concurrency:

```text
A reads RT1
B reads RT1

A refreshes successfully -> save(AT2, RT2)
B refreshes with RT1 -> invalid_grant
B failure handler -> remove(registrationId, principalName)
```

If `remove` is unaware of the version/token A just saved, it can **delete A's brand-new entry**.

### 5.1. Why is unconditional removal dangerous?

The typical service contract is:

```java
removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
```

This API primarily accepts **the key**, not the version of the entry read by the failing request. If a request using a stale token calls remove by key, it can wipe out a newer entry saved by another request.

The ordering can even invert:

```text
A refreshes successfully but has not saved yet.
B fails refresh -> remove(AT1/RT1).
A saves (AT2/RT2).
```

The final outcome differs completely from A-save followed by B-remove. This is a **race between success handling and failure handling**.

### 5.2. Should you disable the default failure handler?

Do not disable it unconditionally. When a refresh token is **truly invalid**, leaving a broken entry around causes every subsequent request to keep failing refreshes.

Solutions can include:

1. **Prevent concurrent refreshes up front**, keyed by authorized client.
2. After a request fails, **re-read the current entry** to see if the token/version changed.
3. Use **conditional remove** so failures only delete matching old versions.
4. If `invalid_grant` occurs and the stored entry is still the failing version, delete/mark it invalid per policy so the user re-authorizes.
5. Record anomalous events to investigate replay detection—never assume every error is a harmless race.

Depending on architecture, you will need a custom `OAuth2AuthorizationFailureHandler` or a storage service supporting compare-and-delete. Only replace the handler once you understand the manager's contract and save/delete ordering.

## 6. Three Distinct Concurrency Environments

Do not lump every "concurrent requests" case into one identical problem.

| Environment | Example | Synchronization mechanism to consider |
|---|---|---|
| Single process, multiple threads | Spring MVC Tomcat handling 10 requests for Alice. | Local per-key lock or single-flight inside the JVM. |
| Multiple processes/pods | 3 pods sharing a JDBC authorized client service. | Distributed coordination + shared store + versioning. |
| Reactive async in one process | WebFlux with multiple subscribers requesting a token. | Reactive single-flight / cached in-flight publisher without blocking the event loop. |
| Different browser sessions, same principal | Alice logged in on laptop and phone. | Check whether service/repository shares the `registrationId + principalName` key. |
| Web request and background scheduler | Web request and job both use Alice's token. | Coordinate across managers reading/writing the same store. |

A `synchronized` block or `ReentrantLock` inside a JVM **does not synchronize across pods**. A properly designed Redis lock or DB row lock can coordinate across nodes, though it introduces its own failure modes.

## 7. Identifying the Right Synchronization Key

`OAuth2AuthorizedClientService` typically looks up entries by:

```text
(clientRegistrationId, principalName)
```

For multi-tenant or multi-issuer setups, include a trusted namespace:

```text
(tenantId, issuer/provider, clientRegistrationId, principalName)
```

Depending on design, the tenant may already be embedded in the registration ID or stable principal name. Crucially, **two distinct security principals must never share a token just because their display names match**.

Example:

| Registration | Principal | Lock / storage key |
|---|---|---|
| `partner-api` | `alice-uid` | `partner-api + alice-uid` |
| `partner-api` | `bob-uid` | `partner-api + bob-uid` |
| `other-api` | `alice-uid` | `other-api + alice-uid` |
| `tenantA-partner` | `alice-uid` | `tenantA-partner + alice-uid` |

Never use a **single global lock** across all users when there are many authorized clients. It forces 1,000 users to wait behind one unrelated token refresh.

Conversely, if the same authorized client is represented by two different keys, per-key locking will fail to serialize them. Ensure every token access path uses **the exact same registration ID and principal identity**.

### 7.1. Is the OIDC principal name stable enough?

In OIDC, `(issuer, subject)` is usually the reliable external identity foundation. Email addresses and display names can change or collide.

If the app maps OIDC users to local account IDs, ensure that mapping is stable and tenant-isolated. Never use `request.getSession().getId()` as a refresh lock key if the same authorization is shared across sessions; conversely, do not merge independent authorizations arbitrarily.

### 7.2. Lock granularity and token scope

One registration can hold multiple tokens with different scopes/audiences/resources if using custom extensions. In that case, `(registrationId, principalName)` may **not suffice** if custom storage adds authorization variants.

Match the lock key to **the exact storage key and token scope**. If authorizations come from different issuers or tenants, namespace explicitly.

---

## 8. Solution 1: Single-Flight / Per-Key Lock in a Single JVM

For a single-instance app, a straightforward approach is **locking by authorized client key** so at most one thread calls the manager to decide on refreshing that key at any time.

Principle:

```text
Thread A, key K:
    acquire lock(K)
    manager.authorize(K) -> may refresh using RT1
    manager save(AT2, RT2)
    release lock(K)

Thread B, key K:
    wait for lock(K)
    acquire lock(K)
    manager.authorize(K) -> manager reloads AT2/RT2
    AT2 still valid -> no refresh
    release lock(K)
```

**Key point:** Thread B must let the manager **reload the authorized client inside the lock**. If B holds an `OAuth2AuthorizedClient` loaded before acquiring the lock and hands it straight to the manager, it may still refresh using stale RT1.

### 8.1. Java example: wrapping the manager with striped locks

The code below is a **wrapper for authorize calls going through the same service manager**. It is effective only among callers using **the same wrapper instance** inside **the same JVM**.

```java
package example.oauth2;

import java.util.Objects;
import java.util.concurrent.locks.ReentrantLock;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class StripedLockingAuthorizedClientManager
        implements OAuth2AuthorizedClientManager {

    private final OAuth2AuthorizedClientManager delegate;
    private final ReentrantLock[] locks;

    public StripedLockingAuthorizedClientManager(
            OAuth2AuthorizedClientManager delegate,
            int stripeCount) {

        this.delegate = Objects.requireNonNull(delegate);

        if (stripeCount <= 0) {
            throw new IllegalArgumentException(
                "stripeCount must be positive"
            );
        }

        this.locks = new ReentrantLock[stripeCount];
        for (int i = 0; i < locks.length; i++) {
            locks[i] = new ReentrantLock();
        }
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizeRequest request) {

        Objects.requireNonNull(request, "request");

        String registrationId = request.getClientRegistrationId();

        if (registrationId == null
                && request.getAuthorizedClient() != null) {
            registrationId = request
                .getAuthorizedClient()
                .getClientRegistration()
                .getRegistrationId();
        }

        if (registrationId == null) {
            throw new IllegalArgumentException(
                "Cannot determine client registration ID"
            );
        }

        String principalName = request.getPrincipal().getName();
        String key = registrationId + "\u0000" + principalName;

        int index = Math.floorMod(key.hashCode(), locks.length);
        ReentrantLock lock = locks[index];

        lock.lock();
        try {
            // Let the manager/service reload state inside the lock.
            return delegate.authorize(request);
        } finally {
            lock.unlock();
        }
    }
}
```

Because different keys can hash to the same stripe, unrelated callers may occasionally wait on each other. That **never leaks tokens**, though it can reduce parallelism. Pick a stripe count matching your load—for example, 64 or 128.

An advantage over a `ConcurrentHashMap<Key, ReentrantLock>` that never evicts keys is bounded lock memory. With many users/tenants, an unbounded lock map without eviction can leak memory indefinitely.

### 8.2. Configuring the manager for service/background usage

```java
package example.oauth2;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class OAuth2AuthorizedClientConfiguration {

    @Bean("serializedAuthorizedClientManager")
    OAuth2AuthorizedClientManager serializedAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager base =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service
            );

        base.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build()
        );

        return new StripedLockingAuthorizedClientManager(base, 128);
    }
}
```

This snippet assumes the authorized client **was already authorized via a prior flow and can be loaded from the service**. Without an existing authorized client, a provider containing only `.refreshToken()` cannot initiate a browser login.

In a real application using both Authorization Code and Refresh Token flows, web authentication must still be configured with Spring Security's OAuth2 Login/Client infrastructure.

### 8.3. Calling from a service that needs a token

```java
package example.oauth2;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class PartnerAccessTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public PartnerAccessTokenService(
            @Qualifier("serializedAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String accessTokenFor(String stablePrincipalName) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("partner-api")
                .principal(stablePrincipalName)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client; interactive authorization may be required"
            );
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
```

This code assumes `stablePrincipalName` comes from an **authenticated and authorized context**, never from an arbitrary user-supplied query parameter. This service **must never mint or hand out an access token for any account merely given a username**.

### 8.4. Limitations of the wrapper

This wrapper solves only a defined scope:

- Works when **every refresh call for the same key goes through the same wrapper**.
- Synchronizes only within **a single JVM**.
- If another manager or HTTP filter bypasses the wrapper, concurrent refreshes can still occur.
- If an `OAuth2AuthorizeRequest` **already embeds a stale authorized client** via `withAuthorizedClient(...)`, the lock does not force the manager to reload the latest entry. For service-backed strategies, prefer `withClientRegistrationId(...)` so the manager loads state inside the lock.
- Locking here also covers cache hits. Under very high load, consider optimizing single-flight only on the refresh branch while preserving re-read and token-update semantics.
- If the process crashes, local locks and caches vanish. It has no effect across other nodes.

**This is not a "universal concurrency safety" patch for all Spring Security flows.** It is a single-instance synchronization pattern when callers are controlled and managers share the same authorized client service.

## 9. Synchronizing Servlet Web Flows: Where to Wrap?

In a Servlet application, web requests may use:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

This manager accepts:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientRepository`.

Meanwhile, services/background tasks use:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

with `OAuth2AuthorizedClientService`.

### 9.1. Two managers can touch the same token

If the web authorized client repository for authenticated principals delegates to `OAuth2AuthorizedClientService`, and a background manager also uses **that same service**, the following can happen:

```text
Web request:
    DefaultOAuth2AuthorizedClientManager
        -> AuthorizedClientRepository
            -> AuthorizedClientService

Background job:
    AuthorizedClientServiceOAuth2AuthorizedClientManager
        -> AuthorizedClientService
```

Both can read the same `(registrationId, principalName)` and refresh simultaneously.

Therefore, inspect **every path capable of refreshing**: web filters, API clients, scheduled jobs, listeners, and custom code. Wrapping only one gateway does not block concurrent refreshes from another path.

### 9.2. HTTP session vs. service storage

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` typically uses an authorized client service for authenticated principals and an HTTP session repository for anonymous users. If the app configures `HttpSessionOAuth2AuthorizedClientRepository` for all principals, each session holds its own token.

Differences:

| Store | Logical key | Concurrency impact |
|---|---|---|
| InMemory service | Registration + principal within one process | Multiple threads reading the key can race. |
| JDBC service | Registration + principal in DB | Multiple nodes reading the key can race. |
| HttpSession repository | Per session and registration | Parallel requests within the same session can race. |
| Shared session store | Distributed session | Multiple nodes can touch the same session state concurrently. |
| Custom store with tenant namespace | Per custom key | Lock/CAS must match the exact key. |

Do not assume **the HTTP session is thread-safe across a long HTTP refresh call**. Multiple parallel requests can easily share the same session.

## 10. Solution 2: Distributed Lock Across Multiple Instances

When an application runs across multiple pods/VMs, a local lock is insufficient:

```text
Pod A: local lock A
Pod B: local lock B

Both can acquire their local locks
and refresh RT1 simultaneously.
```

A **distributed synchronization** mechanism is required if multiple nodes share the same authorized client.

Concept:

```text
Distributed Key:
    oauth2:refresh:{tenant}:{registrationId}:{principalName}

Lock:
    only one node holds refresh ownership for a key

Shared Store:
    persists newly issued OAuth2AuthorizedClient
```

Infrastructure choices include database locking, Redis-based coordination, a distributed lock service, or another organization-approved mechanism. No single lock fits every environment best.

### 10.1. Proposed algorithm

```text
authorize(registrationId, principalName):
    1. Determine stable key in the proper security namespace.
    2. Load current authorized client.
    3. If token still has enough lifetime -> reuse.
    4. If refresh is needed -> acquire distributed lock(key).
    5. Once lock is held, RELOAD authorized client from shared store.
    6. If another node already refreshed the entry:
           -> use the new entry without calling the Token Endpoint.
    7. If refresh is still needed:
           -> invoke manager/provider to refresh using current RT.
           -> save new AT/RT atomically/consistently.
    8. Release lock in finally.
    9. Return appropriate authorized client.
```

In step 7, ensure the manager **reads the latest authorized client acquired inside the lock**. If code passes an old object fetched in step 2 into the manager, the system can still send stale RT1 despite holding the lock.

### 10.2. Sequence diagram with double-check

```mermaid
sequenceDiagram
    autonumber
    participant A as Pod A
    participant B as Pod B
    participant L as Distributed Lock
    participant Store as Shared AuthorizedClient Store
    participant AS as Authorization Server

    A->>Store: load(K)
    Store-->>A: AT1/RT1 nearing expiry
    B->>Store: load(K)
    Store-->>B: AT1/RT1 nearing expiry

    A->>L: acquire(K)
    L-->>A: granted
    B->>L: acquire(K)
    Note over B,L: B waits with bounded timeout

    A->>Store: reload(K) inside lock
    Store-->>A: AT1/RT1
    A->>AS: refresh(RT1)
    AS-->>A: AT2/RT2
    A->>Store: save(AT2/RT2)
    A->>L: release(K)

    L-->>B: granted
    B->>Store: reload(K) inside lock
    Store-->>B: AT2/RT2 still valid
    Note over B: Skip refreshing RT1
    B->>L: release(K)
```

**Re-reading inside the lock** is the step that prevents duplicate refresh requests. Never rely on a snapshot loaded before waiting on the lock.

### 10.3. Avoid mechanically holding long DB transactions across HTTP calls

Some choose:

```text
BEGIN TRANSACTION
SELECT ... FOR UPDATE
POST /token
UPDATE tokens
COMMIT
```

While this serializes callers if all callers use the same transaction/row lock, it has drawbacks:

- Holds DB connections and row locks open for the duration of a multi-second HTTP request.
- Causes lock contention when the AS is slow.
- Can exhaust DB connection pools and block unrelated transactions.
- Complicates AS/DB timeout handling on errors.
- Rolling back the database cannot "undo" the AS having consumed the refresh token.

For high-load systems, consider a **lease-based lock outside long transactions**, optimistic versioning, and recovery policies. Pick based on consistency needs and operational viability—not merely because `FOR UPDATE` is easy to write.

## 11. Distributed Locks Can Expire Mid-Flight

A distributed lock usually carries a **lease/TTL** to prevent permanent deadlocks if a process crashes. Yet a refresh request can take longer than the TTL:

```text
Pod A acquires lock K for 5 seconds.
Pod A calls AS; network stalls for 8 seconds.

After 5 seconds: lock K expires.
Pod B acquires lock K and reads old token.
Pod B also calls AS with RT1.

Pod A receives RT2 and writes to store.
Pod B receives invalid_grant or another new token.
```

Thus, **even having a distributed lock does not absolutely eliminate concurrent refreshes**.

### 11.1. Leases and timeouts must align sensibly

Consider:

- Connect timeout to the Token Endpoint.
- TLS handshake timeout.
- Response/read timeout.
- Worst-case AS latency.
- Retry policy (if any) and total duration.
- Lease TTL / renewal heartbeat.
- Lock acquisition wait time.
- Store read/write latency.
- Shutdown/crash mid-step.

Do not pick an arbitrary TTL like 1 second. If a token request can take 10 seconds, a much shorter lease raises overlap risk. Conversely, never set an infinite lease without handling dead processes.

### 11.2. Fencing tokens protect against stale writes

Some distributed coordination systems provide monotonically increasing **fencing tokens**:

```text
Pod A acquires lock -> fencing = 41
Pod A stalls, lease expires

Pod B acquires lock -> fencing = 42
Pod B writes valid result with fencing = 42

Pod A wakes up, tries to write with fencing = 41
Store rejects the stale write.
```

Fencing prevents **overwriting a newer token with an older result** after lease expiration. However, fencing **cannot undo RT1 already having been sent twice to the Authorization Server**. It is therefore a storage-protection layer, not a complete substitute for curbing duplicate refresh requests.

## 12. Optimistic Concurrency and Compare-and-Set (CAS)

To prevent an older request from deleting or overwriting a newer entry, design a custom authorized client store with a **version**.

Example record:

```text
registration_id = partner-api
principal_name  = alice-uid
version         = 7
access_token    = AT1 (encrypted)
refresh_token   = RT1 (encrypted)
```

After a successful refresh, update only if `version` is still 7:

```sql
UPDATE oauth2_authorized_client_custom
SET
    access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    version = version + 1,
    updated_at = :updated_at
WHERE
    client_registration_id = :registration_id
    AND principal_name = :principal_name
    AND version = :expected_version;
```

If `rowCount = 1`, the update succeeded. If `rowCount = 0`, another operation already changed the entry; the caller must not overwrite unconditionally, and should re-read state and resolve per policy.

**The SQL above is an illustrative custom schema.** It is not the default schema/SQL provided by `JdbcOAuth2AuthorizedClientService`. Implementing CAS requires dedicated implementations, mappers, and storage.

### 12.1. Conditional delete on `invalid_grant`

Idea:

```sql
DELETE FROM oauth2_authorized_client_custom
WHERE
    client_registration_id = :registration_id
    AND principal_name = :principal_name
    AND version = :version_of_failed_refresh;
```

If Request B failed with version 7 while Request A already saved version 8, B **must not delete** version 8.

Remember, however: if the AS performed reuse detection and revoked the entire token family, version 8 may already be invalid. Conditional delete protects against a storage race, **not a guarantee that the newer token is still valid**.

### 12.2. Why is CAS alone not enough?

Suppose A and B both read RT1/version 7, and **both send** `POST /token` before touching the DB:

```text
A: AS consumes RT1, returns RT2.
B: AS receives RT1 again, reports reuse/invalid_grant.
```

CAS stops B from deleting or overwriting the newer version, yet cannot stop two HTTP requests from reaching the AS. With strict rotation, the token family can be invalidated.

Therefore, a resilient design usually combines:

```text
Serialize refresh attempts per key
    +
Re-read state after acquiring lock
    +
Conditional update/delete or fencing
    +
Recovery policy for uncertain refresh outcomes
```

No single primitive guarantees all of these properties under every failure scenario.

## 13. Lost Responses: Uncertain Refresh Outcomes

A trickier scenario than a clear `invalid_grant` is **losing the response after the AS already processed the request**:

```text
T0  Client sends refresh(RT1)
T1  AS accepts RT1
T2  AS invalidates RT1 and generates AT2/RT2
T3  Response is lost between AS and client
T4  Client sees read timeout
```

At T4, the client **does not know** whether the AS consumed RT1 or not.

If it retries with RT1:

- The AS may reject it with `invalid_grant`.
- The AS may treat it as a reuse attempt.
- Under some policies, the token family may be revoked.

### 13.1. Never retry refresh tokens blindly

A generic retry interceptor across all HTTP POSTs can have severe consequences. You should:

- Distinguish pre-send connect failures from response timeouts after the request may have been processed.
- Never assume a client-side exception means the AS never received the request.
- Never retry indefinitely with the old refresh token.
- Apply retry policies only when backed by the AS contract and corresponding idempotency semantics.
- When safe recovery is impossible, prompt the user to re-authorize or follow a provider-supplied recovery workflow.

A token endpoint occasionally offers vendor-specific idempotency, though **never assume support** unless explicitly documented by the provider.

### 13.2. Does a local lock help after a timeout?

A lock guarantees **threads in the same process do not fire concurrent refresh requests at the same instant**, yet after a timeout the next thread still faces:

- Store still holding old RT1.
- No proof whether the AS consumed RT1.
- Retrying RT1 possibly triggering reuse detection.

Concurrency control must therefore pair with a **failure policy**, not just locking.

## 14. Using the Manager to Ensure Fresh State Is Read

`OAuth2AuthorizedClientManager` can accept `OAuth2AuthorizeRequest` in several ways. With a service manager, the common pattern is:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("partner-api")
        .principal("alice-stable-id")
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
```

When backed by `OAuth2AuthorizedClientService`, the manager looks up the authorized client by registration/principal and decides whether to refresh.

### 14.1. Avoid passing a stale `OAuth2AuthorizedClient`

If a caller loads an old object before locking:

```java
OAuth2AuthorizedClient old = service.loadAuthorizedClient(
    "partner-api",
    "alice-stable-id"
);
```

then waits for the lock, and calls:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withAuthorizedClient(old)
        .principal("alice-stable-id")
        .build();
```

the manager may use **the stale object supplied by the caller** instead of reloading from the store. The lock no longer protects the input data.

When building single-flight, prefer **specifying registration + principal and letting the manager load the latest state inside the critical section**, or perform an explicit reload and pass the fresh object.

### 14.2. Manager instances and storage must stay consistent

If an application has multiple managers:

```text
WebManager  -> AuthorizedClientRepository -> JDBC service
JobManager  -> InMemory service
```

the two managers will not see the same state, even with identical `registrationId=partner-api` and `principalName=alice-uid`.

To share an authorization, unify storage and security boundaries. Never manually copy refresh tokens across multiple stores as an ad-hoc workaround.

## 15. `DefaultOAuth2AuthorizedClientManager` vs. Service Manager

### 15.1. Servlet web requests

In an HTTP Servlet context:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

This manager accepts:

```java
DefaultOAuth2AuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository
)
```

It fits when the app processes web requests/sessions with an active `Authentication`.

### 15.2. Background/service contexts

In jobs or services outside HTTP requests:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

This manager accepts:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service
)
```

It fits authorized clients persisted by principal without needing `HttpServletRequest`/`HttpServletResponse`.

### 15.3. The same refresh token can be used by both manager types

For example, a portal lets users link an API account, and a background job syncs on their behalf:

```text
Portal web login:
    Servlet Manager + Repository
        -> saves Alice's authorized client

Background job:
    Service manager + AuthorizedClientService
        -> loads Alice's authorized client
        -> refreshes if needed
```

If both share the same underlying service, they can touch **the same RT1**. That is why concurrency coordination belongs at the storage/token-lifecycle layer rather than wrapping only one HTTP controller.

---

## 16. How Spring Security Configures the Refresh Provider

Configuration example in a Servlet application using a composite provider:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class OAuth2ProviderConfiguration {

    @Bean
    OAuth2AuthorizedClientProvider authorizedClientProvider() {
        return OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken(refresh -> refresh
                .clockSkew(Duration.ofSeconds(60))
            )
            .build();
    }
}
```

In an authorization code flow, `authorizationCode()` participates when interactive authorization is required; `refreshToken()` runs when the authorized client already holds a suitable refresh token and the access token needs renewal.

**The provider builder does not add distributed locking.** It defines **grant strategies**, not storage transaction isolation.

### 16.1. Dedicated token response clients for the refresh grant

In modern Spring Security versions, the Servlet refresh token response client can be:

```java
org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient
```

And the reactive counterpart:

```java
org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient
```

Depending on version, older `RestTemplate`-based classes may exist.

Configure appropriate timeouts, TLS, and proxies for refresh token HTTP calls, yet remember **timeouts alone do not stop multiple requests from using RT1 concurrently**.

### 16.2. Clock skew and premature refreshing

If a token lives 2 minutes and skew is 60 seconds, half of the token's lifetime falls inside the refresh window. Under high load, many requests can quickly race to refresh.

Tuning skew for token lifetime and network latency can reduce refresh frequency, though concurrency control remains an independent problem.

## 17. WebFlux/Reactive: Never Use `ReentrantLock` on the Event Loop

In **Spring Security WebFlux**, the corresponding APIs are:

```text
ReactiveOAuth2AuthorizedClientManager
ReactiveOAuth2AuthorizedClientProvider
RefreshTokenReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
```

In WebFlux, token refreshes return:

```java
Mono<OAuth2AuthorizedClient>
```

Calling `ReentrantLock.lock()` or `.block()` directly on a Reactor event loop blocks other I/O tasks and degrades throughput.

### 17.1. What is reactive single-flight?

Instead of blocking threads, structure it as:

```text
key K -> Mono currently executing refresh for K
```

When Request A starts refreshing:

```text
K -> inFlight Mono<OAuth2AuthorizedClient>
```

Request B arrives for the same key while A is still running:

```text
B subscribes to the same inFlight Mono
    -> does not send a second refresh HTTP request
    -> receives the same result or error as the in-flight refresh
```

Once the publisher completes or errors, **remove the in-flight entry** so future calls can load fresh state and refresh again when needed.

### 17.2. Do not cache a token-bearing `Mono` forever

If you leave `Mono.cache()` in a map forever for key K, all subsequent calls will keep returning **the old expired authorized client** long after the refresh finished.

Distinguish:

- Caching the **in-flight operation** only while it is executing.
- Storing the **authorized client** with its token and expiry for future checks.

When using Reactor operators like `cache`, `doFinally`, `defer`, and a concurrent map, carefully manage **subscription, cancellation, cleanup after terminal signals, and map-entry replacement races**. Overly short reactive snippets lacking lifecycle cleanup easily introduce subtle bugs.

### 17.3. Multi-instance reactive still needs distributed coordination

In-process reactive single-flight only deduplicates subscribers within that single process. Two WebFlux pods can still refresh the same RT1 simultaneously. You still need a shared store, distributed locking/coordination, and CAS just like the multi-instance Servlet case.

## 18. When Can an Access Token Be Reused While a Refresh Is Running?

An access token can **still be valid per `expiresAt`** inside the `clockSkew` window even though the provider wants to renew early.

Some systems design a policy:

```text
AT1 has enough lifetime left for this request:
    -> temporarily allow using AT1
    -> a refresh task runs asynchronously
```

However, this is an **application-specific stale-while-refresh strategy**, not default Spring Security behavior to assume.

Risks to weigh:

- The token may expire before the Resource Server processes the request.
- The Resource Server may have already revoked the token.
- The backend request may run longer than the remaining lifetime.
- If refresh token rotation / reuse detection triggers, the AS may revoke related tokens.
- A custom cache layer might bypass fresh manager checks.

Therefore, if using this strategy, define a **safe remaining-lifetime floor** and explicit policy. For critical APIs, awaiting a single-flight refresh is often safer than sending a nearly expired token.

## 19. Recovering from `invalid_grant` in Concurrent Environments

`invalid_grant` can have several causes:

- The refresh token expired.
- The refresh token was revoked.
- The client reused a rotated refresh token.
- The refresh token did not match client authentication.
- The provider enforced another contract policy.

**You cannot look at `invalid_grant` alone and be sure it was a race.**

### 19.1. Triage workflow

When Request B receives `invalid_grant`:

1. Identify the authorization's registration/principal (never log token values).
2. Check whether another refresh request for the same key is running or recently succeeded.
3. Reload the authorized client from the store with proper access controls.
4. Compare protected version or refresh-token fingerprint if supported by the store.
5. If the stored entry is newer than the one B used, do not delete the newer entry just because B failed.
6. If the AS uses reuse detection, determine whether the token family was revoked before continuing to use it.
7. If no valid state exists, prompt for re-authorization per application flow.
8. Record metrics and investigate the source of concurrency—never retry the old RT endlessly.

### 19.2. Never disable AS security to dodge races

A wrong fix is asking the AS **not to invalidate old refresh tokens** just because your client sends concurrent requests. Rotation protects against token replay and is often an essential security control.

The right fix is **fixing client concurrency**, not weakening security to mask concurrency bugs.

### 19.3. When a fresh authorization flow is needed

If the refresh token is no longer valid and the system has no provider-supported recovery path, you may have to:

```text
User Alice
    -> start a fresh Authorization Code + PKCE flow
    -> obtain new access token / refresh token
    -> save updated authorized client
```

For browserless background jobs, never impersonate the user or switch to `client_credentials` to bypass restrictions. The job should recognize that user authorization is unavailable and signal that the user needs to reconnect their account.

## 20. Logout, Disconnect, and Deletion Can Also Race with Refresh

Concurrency does not happen only between two refresh requests. Example:

```text
Request A: currently refreshing RT1.
Request B: user clicks "Disconnect provider".
B: removes authorized client and revokes token.
A: refresh finishes, saves AT2/RT2.
```

If A saves after B disconnects, the token can **reappear in the store** even though the user unlinked the account.

Lifecycle design must cover:

- Token refresh.
- Logout / disconnect.
- User deletion / account deactivation.
- Token revocation at the AS.
- Client credential updates.
- Tenant offboarding.

Use **versions, tombstones, revocation markers, or account-link statuses** to prevent an in-flight refresh from re-writing an authorization the user already deleted. A simple per-key lock serializes operations if **every refresh and delete path shares the same lock**, while multiple instances require distributed coordination.

### 20.1. What is a tombstone?

An entry can carry status metadata:

```text
state = ACTIVE / DISCONNECTED
version = 12
```

A refresh may persist only if the entry is still `ACTIVE` and its version matches. When the user disconnects, the state flips to `DISCONNECTED`; late refresh responses cannot overwrite that state.

This is a **custom storage pattern**, not a built-in field on `JdbcOAuth2AuthorizedClientService`.

## 21. Securing Storage and Logging While Handling Races

Refresh tokens are highly sensitive credentials. **Never log**:

```text
refresh_token
access_token
Authorization: Basic clientId:clientSecret
client_assertion
code_verifier
id_token
```

Safe to log:

```text
registrationId=partner-api
principalReference=<internal opaque id>
operation=refresh
result=success | invalid_grant | timeout
lockWaitMs=...
refreshDurationMs=...
storageVersion=...
retryCount=...
```

If `principalName` is personal data, consider **pseudonymization** in logs. Never place raw principals or emails into high-cardinality metric labels.

### 21.1. Fingerprints to identify token versions

If you need to compare old vs. new tokens, avoid logging full refresh tokens or unmanaged hashes. Prefer a **secret-managed HMAC/fingerprint** as an internal comparison identifier, or better yet, an independent **version counter** in the store.

Avoid logging fingerprints at a scale that enables tracking users unnecessarily. Debugging races usually only needs the version, namespaced key, and timestamp.

### 21.2. Databases and Redis are not automatically safe just by sitting in a private subnet

Enforce:

- TLS to storage where appropriate.
- Least-privilege access controls.
- Encryption at rest and protected backups.
- Never logging query parameters containing tokens.
- Data deletion mechanisms on account disconnect.
- Secret/key rotation and policy auditing.
- Isolation across tenants and principals.
- Keeping unnecessary sensitive data out of lock keys.

## 22. Production Observability: Essential Metrics

Without observability, distinguishing an AS outage from a refresh race is guesswork.

| Metric | Purpose |
|---|---|
| Refresh attempt count | Spot spikes when tokens expire. |
| Refresh success count | Track successful token renewals. |
| `invalid_grant` count | Detect invalid or reused tokens. |
| Requests coalesced by single-flight | Verify concurrency control is working. |
| Lock wait duration | Detect excessive lock contention. |
| Token Endpoint latency | Tune connect/read timeouts and lease TTLs. |
| Storage CAS conflicts | Count versioned write collisions. |
| Conditional delete no-ops | Confirm stale failure paths spared newer records. |
| Re-authorization required count | Measure user impact. |
| Token family/replay events from AS | Detect replay events per provider contract. |
| API calls per authorized client | Correlate traffic with refresh frequency. |
| DB/store errors | Separate persistence failures from AS errors. |

Never attach access tokens, refresh tokens, or raw user emails as metric labels.

### 22.1. A telltale pattern

```text
10:00:00  refresh_attempt=10
10:00:01  refresh_success=1
10:00:01  refresh_invalid_grant=9
```

For the same authorized client with token rotation, this strongly suggests **duplicate refreshes** to investigate, while still verifying root cause via AS/telemetry.

A system with single-flight instead logs:

```text
10:00:00  refresh_attempt=1
10:00:00  in_flight_joiners=9
10:00:01  refresh_success=1
```

Requests wait on a single refresh rather than firing 10 duplicate refresh tokens.

## 23. Unit-Testing Concurrency

Tests should exercise **concurrent behavior**, not just `authorize()` returning a token on a single thread.

Scenarios to cover:

1. 10 threads simultaneously use an authorized client nearing expiration.
2. Only one refresh call reaches the mock Token Endpoint when single-flight is active.
3. All 10 callers eventually receive an authorized client with the new token.
4. No caller uses RT1 after RT2 has been persisted.
5. When refresh fails, the lock is released and subsequent callers can recover per policy.
6. When two different keys need refreshing, they do not block each other globally.
7. After logout/disconnect, an in-flight refresh does not resurrect the authorized client.
8. When the token response includes a new refresh token, the store saves RT2 and drops RT1.
9. CAS stale updates/deletes never overwrite a newer version.
10. Distributed lock lease timeouts do not cause silent overwrites.

### 23.1. Using `CountDownLatch` to make requests start together

In Java/JUnit, you can use `CountDownLatch` to align threads so they start together. Pseudocode example:

```java
int threadCount = 10;
CountDownLatch ready = new CountDownLatch(threadCount);
CountDownLatch start = new CountDownLatch(1);

for (int i = 0; i < threadCount; i++) {
    executor.submit(() -> {
        ready.countDown();
        start.await();

        // All threads call the same wrapper/manager with the same key.
        manager.authorize(
            OAuth2AuthorizeRequest
                .withClientRegistrationId("partner-api")
                .principal("alice-uid")
                .build()
        );

        return null;
    });
}

ready.await();
start.countDown();
```

This snippet **illustrates start synchronization**, not a complete JUnit test; you must still declare `executor`, `manager`, imports, timeouts, future collection, and shutdown. In a full test, use a fake/mocked Token Endpoint and store to count refresh requests rather than hitting a real AS.

### 23.2. Why test failure cases too?

Testing only "10 threads all succeed" is not enough. Also simulate:

```text
Thread A refreshes successfully, saves RT2.
Thread B receives invalid_grant from stale RT1.
```

Verify that the failure policy **does not accidentally delete RT2 when the store uses version-aware logic**, and do not assume RT2 stays valid if the AS revoked the token family.

Also test:

```text
Refresh response lost after the AS consumed RT1.
```

For uncertain outcomes, ensure the system avoids blindly retrying RT1 and transitions to recovery/re-authorization as needed.

### 23.3. Single-JVM tests do not prove distributed safety

A local test with `ReentrantLock` can pass flawlessly while production fails across 3 pods. Write integration or fault-injection tests for your distributed coordination and storage layer if the system runs multi-instance.

You do not need a real production Authorization Server to reproduce races; a test provider or mock token endpoint that rotates `RT1->RT2` and rejects reuse works well.

---

## 24. Architectural Options to Choose From

| Architecture | Suitable mechanism | Limitations |
|---|---|---|
| Single Spring MVC instance, one manager used by all callers | Per-key local lock or single-flight | Unsafe if another manager bypasses the wrapper. |
| Multiple instances, shared JDBC service | Distributed serialization + reload + CAS | Requires managing locks/leases and DB versions. |
| Spring Session shared across nodes | Coordination by session/authorized client key | Session storage does not serialize network refreshes by itself. |
| Single-instance WebFlux | Reactive in-flight deduplication | Must not block event loop; must clean up publishers. |
| Multi-pod WebFlux | Reactive single-flight + distributed coordination | Adds lease/lock failure modes. |
| Background job and web app sharing a user token | Shared store + unified token-lifecycle coordination | Must align principal keys and manager usage. |
| Strict token rotation / reuse detection | Prevent duplicate refreshes before Token Endpoint | CAS alone is insufficient. |
| AS does not rotate refresh tokens | Still curb duplicate requests and lost updates | Races are less severe, though not eliminated. |

**Risk-based design recommendations:**

- For small single-instance apps where all callers share one manager, in-JVM single-flight is usually a clean starting point.
- For multi-instance apps with strict refresh token rotation, use cross-node serialization plus version-aware storage/recovery.
- If multiple code paths or managers refresh independently, consolidate refresh ownership behind **one shared management abstraction** instead of adding ad-hoc locks in individual controllers.
- If the AS supports sender-constrained refresh tokens or special rotation policies, check provider docs and your threat model.
- Never recommend disabling rotation or loosening replay detection just to avoid handling client concurrency.

## 25. Common Implementation Mistakes

### Mistake 1 — Every request calls the Token Endpoint directly

Code reads the refresh token and POSTs `/token` inside every controller.

**Consequence:** multiple requests can send RT1 simultaneously and trigger reuse detection.

**Better approach:** call the authorized client manager and centralize token lifecycle in a concurrency-controlled service/gateway.

### Mistake 2 — Relying only on `ConcurrentHashMap` to cache tokens

`ConcurrentHashMap` makes individual map operations thread-safe, yet **does not make load–check–POST–save atomic**. A map can still serve AT1 while multiple callers hit the Token Endpoint concurrently.

### Mistake 3 — Using `synchronized` on per-request objects

If every request creates a new object and runs `synchronized(this)`, requests do not share a monitor. No real serialization occurs.

### Mistake 4 — Using a global lock for all users

One refresh for Alice stalls Bob and thousands of unrelated users.

**Fix:** lock by authorized client key, or use bounded striped locks and monitor contention.

### Mistake 5 — Locking only the save, not the token request

Two requests can already send RT1 concurrently before reaching the save step. By then it is too late to prevent the AS from detecting reuse.

### Mistake 6 — Reading the authorized client before locking without re-reading

Thread B waits for A to finish refreshing, yet still sends the pre-loaded RT1.

**Fix:** re-read state inside the critical section and let the manager use the fresh object.

### Mistake 7 — Distributed lock TTL shorter than the refresh request

A's lock expires before the HTTP request finishes; B acquires the lock and sends RT1.

**Fix:** account for total timeouts, lease renewal, fencing, and failure policies. Never treat a leased lock as an absolute guarantee.

### Mistake 8 — CAS update while still sending duplicate refreshes

CAS prevents overwriting the DB, yet the AS already saw RT1 reused.

**Fix:** serialize before the refresh POST, not only with CAS after the response.

### Mistake 9 — Failure handler deletes an entry just refreshed by another request

Request B gets `invalid_grant` and deletes by key, wiping out A's AT2/RT2.

**Fix:** version-conditional removal plus coordination, and check whether the AS revoked the token family.

### Mistake 10 — Retrying `invalid_grant` endlessly

If RT1 rotated, retrying RT1 can trigger further replay detection or rate limiting.

**Fix:** classify the error, reload state, and trigger re-authorization when needed.

### Mistake 11 — Locking one manager while another path bypasses it

An API gateway uses a locking wrapper, while a scheduled job calls the unwrapped manager directly.

**Fix:** audit all code paths and enforce one unified token lifecycle source.

### Mistake 12 — Key collisions across tenants

Two users in different tenants with matching display names and registration IDs collide on the storage key.

**Fix:** namespace by stable principal, tenant, and trusted issuer/provider.

### Mistake 13 — Holding the lock while calling business APIs

After getting the access token, code holds the lock throughout `GET /orders` or a 30-second business workflow.

**Fix:** keep the critical section strictly around the read/check/refresh/save steps requiring serialization. **Release the lock before calling the Resource Server API** unless a special protocol reason dictates otherwise.

### Mistake 14 — Disabling TLS verification to work around Token Endpoint timeouts

Race conditions and TLS handshake failures are completely separate issues.

**Fix:** tune HTTP transport, truststores, and proxies per policy; never strip transport security on connections carrying refresh tokens.

### Mistake 15 — Substituting Client Credentials for Alice's token after refresh failure

A token issued for a service does not carry Alice's authorization.

**Fix:** ask the user to reauthorize, or use a standard delegated grant if supported by the AS and policy.

### Mistake 16 — Testing only on a single thread

Single-threaded tests will never catch multiple requests concurrently loading RT1.

**Fix:** test with barriers/latches, mock token rotation, save/delete fault injection, and multi-node tests when needed.

## 26. Practice Scenarios

### Scenario A — Dashboard fires 8 API calls at once

Alice just signed in, her access token is nearing expiration, and the frontend opens a dashboard firing 8 parallel requests.

**Analysis:** if all 8 calls hit the manager/store without serialization, they can all send RT1 concurrently.

**Solution:** single-flight keyed by `(registrationId, principal)`; one request refreshes while the others wait and use AT2 once saved.

### Scenario B — 3 pods using InMemory store

Each pod holds its own tokens and refresh tokens because each authorization is stored locally.

**Analysis:** entries are not actually the **same** authorized client; however, users routed to a different node will miss their authorization.

**Solution:** fix the storage architecture before adding distributed locks. If one shared authorization is needed, use consistent shared storage.

### Scenario C — 3 pods using a JDBC service

All pods share one `(registrationId, principalName)`.

**Analysis:** a shared DB makes tokens visible across pods, yet does not ensure only one node refreshes.

**Solution:** distributed locking + re-read + version-aware save/delete, backed by token-rotation tests.

### Scenario D — Request A wins, B fails and deletes the entry

A saves RT2; B receives `invalid_grant` and deletes by key.

**Analysis:** the default failure handler can have unintended side effects during a race.

**Solution:** prevent duplicate refreshes, use conditional removal when needed, and verify the AS's replay policy.

### Scenario E — Request A times out after the AS rotated

The client never receives RT2, and the store still holds RT1.

**Analysis:** the AS outcome is uncertain, so retrying RT1 can look like reuse.

**Solution:** handle uncertain outcomes explicitly; never retry blindly. When needed, prompt for fresh user authorization.

### Scenario F — User disconnects while a refresh is running

B deletes the linked account; A finishes refreshing and saves the token back.

**Analysis:** the token was "resurrected" after disconnect.

**Solution:** use account-link states/tombstones and conditional writes, or serialize refresh and disconnect operations.

### Scenario G — Token is unexpired yet API returns 401

The API rejects Alice's access token even though `expiresAt` still has several minutes left.

**Analysis:** the token may be revoked or have the wrong audience/scope, not necessarily a refresh concurrency issue.

**Solution:** separate Resource Server errors from Token Endpoint errors; do not repeatedly request new tokens when configuration is wrong.

### Scenario H — Clock skew is 5 minutes, token lives only 3 minutes

Every manager call sees the access token as "about to expire".

**Analysis:** causes constant refreshes and increases race frequency.

**Solution:** align skew with token lifetime and latency. If concurrent requests still occur, single-flight is still needed.

### Scenario I — WebFlux calls `.block()` to fetch a token

A developer wraps a blocking manager call inside a reactive handler.

**Analysis:** blocks the event loop, cuts throughput, and risks deadlocks or timeouts.

**Solution:** use the reactive manager and reactive single-flight. Never put a blocking `ReentrantLock` directly on the event loop.

### Scenario J — Custom per-key lock map never evicts entries

Every user login adds a new lock key retained forever in a map.

**Analysis:** the lock map grows unbounded with user count.

**Solution:** use striped locks or a properly designed reference-counted/evicting keyed-lock registry.

### Scenario K — Late refresh result arrives after lease expiration

Pod A's lock TTL expires, Pod B updates to version 8, and then A writes version 7.

**Analysis:** a distributed lock alone does not prevent stale writes.

**Solution:** CAS/fencing blocks A from overwriting, while duplicate token requests to the AS must still be mitigated.

### Scenario L — Backend job and web request share Alice's token

A job refreshes RT1 while a web request also refreshes RT1 through a separate manager.

**Analysis:** two code paths refresh the same authorized client using different locks.

**Solution:** coordinate concurrency at the token lifecycle / shared store layer rather than locking only one controller.

## 27. Self-Check Questions

**Q1.** Why can multiple requests refresh the same authorized client concurrently?

**Answer:** They can all read the old token and see the access token inside the refresh window before any request persists the new token.

**Q2.** How does refresh token rotation make races more dangerous?

**Answer:** The AS can invalidate RT1 after the first refresh; any subsequent use of RT1 fails with `invalid_grant` and may trigger reuse detection or revoke the token family.

**Q3.** What does `RefreshTokenOAuth2AuthorizedClientProvider` normally do if the access token still has plenty of validity?

**Answer:** It needs no reauthorization and returns `null`; the manager retains and returns the existing authorized client.

**Q4.** Is `clockSkew` a mutex or lock?

**Answer:** No. It only shifts the threshold for deciding when a token needs refreshing; it does not serialize requests.

**Q5.** Why must you re-read the token after acquiring the lock?

**Answer:** Another request may have already refreshed and saved RT2 while the caller waited for the lock; the pre-lock RT1 snapshot is stale.

**Q6.** Does a local `ReentrantLock` synchronize across 3 pods?

**Answer:** No. It only coordinates threads sharing that lock within a single JVM.

**Q7.** Does CAS stop the AS from receiving two refresh requests with RT1?

**Answer:** No. CAS only guards store writes/deletes; you must serialize before the token request.

**Q8.** What can the default failure handler do on `invalid_grant`?

**Answer:** Depending on the Spring Security manager, it can remove the stored authorized client. During a race, avoid accidentally deleting a newer version.

**Q9.** Can you retry RT1 endlessly when a refresh times out?

**Answer:** No. The AS may have consumed RT1 even though the response was lost, so retrying can trigger reuse detection.

**Q10.** Why are fencing tokens needed when a distributed lock has a TTL?

**Answer:** Once an older caller's lease expires, a newer caller may have written newer state; fencing rejects stale writes from the expired caller.

**Q11.** When should you prompt the user to reauthorize?

**Answer:** When the refresh token is no longer valid with no AS/policy-supported recovery, or when the token family has been revoked.

**Q12.** Does reactive programming automatically prevent refresh races?

**Answer:** No. Multiple reactive subscriptions or multiple pods can still fire duplicate token requests; proper reactive single-flight/coordination is still required.

**Q13.** Why shouldn't you substitute Client Credentials tokens for a user's token?

**Answer:** They represent the service itself, not the authorization granted by the user.

**Q14.** What happens if disconnect and refresh run concurrently?

**Answer:** A late refresh response can save a token back after the account disconnected; use tombstones, versioning, or serialization.

**Q15.** What should you measure when testing concurrency?

**Answer:** Actual token refresh request counts, refresh successes/`invalid_grant` counts, how many callers receive the new token, and any CAS conflicts or erroneous deletions.

## 28. Key Takeaways

| Concept | Takeaway |
|---|---|
| **Authorized client** | Stores access token + refresh token alongside registration/principal. |
| **Refresh token rotation** | Each successful refresh may replace RT1 with RT2 and invalidate RT1. |
| **Duplicate refresh** | Multiple requests sending RT1 while state is stale. |
| **`invalid_grant`** | May indicate invalid/expired/reused RT; never jump to conclusions without investigation. |
| **`RefreshTokenOAuth2AuthorizedClientProvider`** | Decides when to refresh based on authorized client, RT, and expiry/skew. |
| **`OAuth2AuthorizedClientManager`** | Coordinates loading, providers, success/failure handling, and persistence. |
| **Local single-flight** | At most one active refresh operation per key inside a JVM. |
| **Per-key lock** | Partitioned by the authorized client's security namespace to avoid global contention. |
| **Re-read after lock** | Never use a stale RT loaded prior to waiting. |
| **Distributed lock** | Coordinates across nodes, though leases and failures must be handled. |
| **CAS / optimistic version** | Prevents stale writes/deletes; does not by itself block duplicate token HTTP calls. |
| **Fencing token** | Rejects writes from callers holding expired leases. |
| **Conditional remove** | Prevents a failure on version 7 from deleting version 8. |
| **Retries** | Never blindly retry old RTs when refresh outcomes are uncertain. |
| **User disconnect** | Guard against late refresh responses resurrecting deleted tokens. |
| **WebFlux** | Use reactive in-flight deduplication; never block the event loop. |
| **Multi-instance** | Shared storage alone is insufficient; coordinate per key. |
| **Observability** | Track refresh rate, `invalid_grant`, lock waits, and CAS conflicts without logging secrets. |

### Conclusion

When **multiple requests concurrently refresh the same `OAuth2AuthorizedClient`**, the issue goes beyond wasted Token Endpoint calls. With **refresh token rotation**, requests reusing RT1 can be rejected by the AS, trigger replay detection, or even revoke the entire token family. Spring Security supplies managers, providers, services, and error/persistence hooks, yet you must never assume the entire refresh lifecycle is automatically atomic across threads and nodes.

The reliable solution is to **serialize refreshes by authorized client key, re-read state once refresh ownership is acquired, persist/delete conditionally, and define recovery policies when AS outcomes are uncertain**. In one JVM, use single-flight or per-key locks; across multiple nodes, combine distributed coordination, CAS, and fencing. Always account for `invalid_grant` failure handling, token rotation, user disconnects, Servlet vs. WebFlux differences, and keeping refresh tokens out of logs and insecure storage.

## Official Reference Documentation

- [Spring Security — Core Interfaces and Classes for OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): roles of `OAuth2AuthorizedClientManager`, providers, success/failure handlers, and persistence.
- [Spring Security API — `RefreshTokenOAuth2AuthorizedClientProvider`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RefreshTokenOAuth2AuthorizedClientProvider.html): refresh conditions, clock skew, and token response client.
- [Spring Security API — `DefaultOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): Servlet request manager and failure-handler behavior.
- [Spring Security API — `AuthorizedClientServiceOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): out-of-request manager, saving authorized clients, and handling `invalid_grant`.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive authorized client managers and storage.
- [RFC 6749 — OAuth 2.0 Refresh Token Grant](https://datatracker.ietf.org/doc/html/rfc6749#section-6): requesting new access tokens with a refresh token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token replay detection, rotation, and related security requirements.
