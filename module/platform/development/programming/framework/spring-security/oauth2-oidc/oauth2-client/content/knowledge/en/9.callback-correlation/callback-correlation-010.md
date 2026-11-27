# 9.10. Custom Repository: Data Preservation and Lifetime Requirements

## 1. What Is the Repository Used For in OAuth2/OIDC Callbacks?

In Spring Security OAuth 2.0/OIDC Client, a single **Authorization Code Login** typically consists of two separate HTTP trips to the application:

1. The user opens the login initiation path, such as `/oauth2/authorization/corporate`. Spring Security builds an `OAuth2AuthorizationRequest`, saves the required details, and redirects the browser to the Authorization Server.
2. After the user authenticates, the provider returns the browser to the callback, such as `/login/oauth2/code/corporate?code=...&state=...`. Spring Security must **locate that exact prior authorization request** to verify correlation and proceed with exchanging the code for tokens.

The **authorization request repository** stores the temporary transaction context between these two legs. The repository may rely on the default session, a shared store like Redis, or another mechanism satisfying Spring Security's contract.

A custom repository is only correct when it satisfies both requirement groups simultaneously:

- **Data preservation:** the retrieved request must retain enough original information for Spring Security to verify `state`, send the right **PKCE code verifier**, process **OIDC nonce**, identify the right `ClientRegistration` and `redirect_uri`, and restore internally used attributes.
- **Lifetime preservation:** a request has an explicit expiration time, serves only the initiating transaction, cannot be reused after consumption, does not linger indefinitely as orphaned data, and cannot be accidentally overwritten by another login flow.

Simply "saving `state` and returning an object" is not enough. If a custom repository drops the verifier or nonce, the flow can fail after the callback or silently skip a security constraint even when the `state` check appears to succeed.

### 1.1. This Repository Differs from Token Storage

| Object/component | When it matters | Main contents |
| --- | --- | --- |
| `ClientRegistrationRepository` | Before and throughout the flow | Client config: `clientId`, provider, scopes, grant, endpoints |
| `OAuth2AuthorizationRequest` | When preparing the redirect | Authorization request for **one transaction**, including `state`, redirect URI, additional parameters, and attributes |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Between authorization redirect and callback (Servlet) | Saves, loads, deletes **pending requests** |
| `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Same role in WebFlux | Reactive API for saving, loading, deleting authorization requests |
| `OAuth2AuthorizedClient` | After tokens are issued | `ClientRegistration` along with access token/refresh token when present |
| `OAuth2AuthorizedClientService` / corresponding repository | After tokens are issued | Saves/loads **authorized clients**; does not replace the authorization request repository |

Specifically, the custom repository in this lesson **is not where long-lived access tokens are stored** and does not replace `OAuth2AuthorizedClient` management.

## 2. Which Steps of the Authorization Flow Involve the Repository?

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Browser
    participant App as Spring Security OAuth2 Client
    participant Repo as Custom Authorization Request Repository
    participant IdP as OIDC Provider

    User->>App: GET /oauth2/authorization/corporate
    App->>App: Build OAuth2AuthorizationRequest
    App->>Repo: save(request + attributes, expiry)
    Repo-->>App: Saved
    App-->>User: 302 /authorize?state=...&code_challenge=...&nonce=...
    User->>IdP: Authorization Request
    IdP-->>User: 302 callback?code=...&state=...
    User->>App: Callback with session/correlation
    App->>Repo: load(request by state + session)
    Repo-->>App: Valid original request
    App->>Repo: remove/consume(request)
    Repo-->>App: Consumed request
    App->>App: Verify state, restore verifier/nonce
    App->>IdP: POST /token with code + code_verifier
    IdP-->>App: Token response / ID Token
    App->>App: Verify OIDC nonce and other claims
    App-->>User: Complete login / error
~~~

The diagram depicts responsibilities at a logical level; exact order and method calls depend on the filter, authentication provider, and Spring Security version. The key point is that **the callback can only proceed if the repository retrieves the valid original request**.

One scenario to handle explicitly: the user finishes logging in, yet the callback arrives **after the repository's TTL has expired**. The repository must treat the request as invalid even if the authorization code from the provider looks fine. The application should initiate a fresh flow rather than relaxing correlation checks to "rescue" a stale callback.

## 3. Spring Security Interfaces: Servlet and WebFlux

### 3.1. Servlet/MVC — `AuthorizationRequestRepository`

On the Servlet stack:

~~~java
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface AuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {
    T loadAuthorizationRequest(HttpServletRequest request);

    void saveAuthorizationRequest(
        T authorizationRequest,
        HttpServletRequest request,
        HttpServletResponse response);

    T removeAuthorizationRequest(
        HttpServletRequest request,
        HttpServletResponse response);
}
~~~

Annotations and minor details are omitted to highlight the contract; these are the core signatures of the modern Servlet API.

- **`saveAuthorizationRequest`:** saves the request created **before redirecting**. When the authorization request parameter is `null`, repository behavior must conform to Spring Security's removal contract.
- **`loadAuthorizationRequest`:** looks up the **unconsumed** request associated with the current HTTP request. If absent or invalid, returns `null`.
- **`removeAuthorizationRequest`:** retrieves and removes the matching request so the same correlation cannot be reprocessed. Returns the consumed request, or `null` if absent/expired.

The common default implementation is `HttpSessionOAuth2AuthorizationRequestRepository`. It is a solid starting point for standard single-session login apps; only reach for a custom repository when you need parallel authorization requests or custom storage/TTL behavior.

### 3.2. WebFlux — `ServerAuthorizationRequestRepository`

On the reactive stack:

~~~java
import org.springframework.security.oauth2.client.web.server.ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public interface ServerAuthorizationRequestRepository<T extends OAuth2AuthorizationRequest> {
    Mono<T> loadAuthorizationRequest(ServerWebExchange exchange);

    Mono<Void> saveAuthorizationRequest(
        T authorizationRequest, ServerWebExchange exchange);

    Mono<T> removeAuthorizationRequest(ServerWebExchange exchange);
}
~~~

WebFlux uses `ServerWebExchange` and Reactor `Mono` instead of Servlet `HttpServletRequest`/`HttpServletResponse`. The common session implementation is `WebSessionOAuth2ServerAuthorizationRequestRepository`.

**Never reuse Servlet code directly in WebFlux.** Nor should you call `.block()` inside a reactive implementation to invoke synchronous JDBC/Redis on the event loop. Use reactive I/O clients and return publishers honoring the contract.

### 3.3. Where to Wire the Repository in OAuth2 Login Configuration

Servlet example:

~~~java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest>
                    authorizationRequests) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(authorizationRequests)));

        return http.build();
    }
}
~~~

In WebFlux, the corresponding configuration sits inside `ServerHttpSecurity.oauth2Login(...)` and `authorizationRequestRepository(...)` under the authorization request resolver/repository DSL for that version.

Java snippets in this lesson omit routine `import` statements. When integrating, use the API matching your exact Spring Security version and web stack.

## 4. Exactly What Data Must Be Preserved?

### 4.1. Do Not Store Only `state`

`OAuth2AuthorizationRequest` holds rich data for **a single authorization attempt**. Fields and groups that typically must be preserved:

| Data | Reason to keep | Failure if lost or altered |
| --- | --- | --- |
| `authorizationUri` | Identifies the provider endpoint used to create the request | May pick the wrong provider/flow |
| `authorizationGrantType` / `responseType` | Indicates authorization code flow | Inconsistent with token exchange |
| `clientId` | Binds to the initial client | Uses wrong client or fails code exchange |
| `redirectUri` | Exact callback URI sent | `invalid_grant` or mismatch during token exchange |
| `scopes` | Requested scopes | Loss of authorization request context |
| `state` | Binds callback to initial request | Callback lacks correlation mechanism |
| `additionalParameters` | Extra parameters sent to provider | Loses `nonce`, PKCE challenge/method, or vital extensions |
| `attributes` | **Internal data** used by Spring Security/app after redirect | Loses `code_verifier`, registration info, or correlation metadata |
| Creation time, `expiresAt` | Manages request lifetime | Accepts stale requests or retains records forever |
| Session/tenant/browser binding | Prevents cross-transaction use | Another browser/user could recover the request |

**Crucially:** never assume all data worth preserving appears in the authorization URL query string.

- `additionalParameters` may contain `code_challenge` or OIDC parameters sent **out to the provider**.
- `attributes` is **internal** data that may hold the PKCE `code_verifier` or metadata identifying registration/flow.
- `state` appears in both the initial request and callback, yet **must be matched against the saved copy**, not merely checked for presence.

Exact keys and value types inside `attributes` can depend on how Spring Security or custom resolvers build the request. When serializing, preserve **both values and data types** rather than coercing everything to strings.

### 4.2. Dangers of an Overly Minimal DTO

Example of a flawed DTO design:

~~~java
record SavedLogin(String state, String clientId, String redirectUri) {}
~~~

This DTO cannot restore requests with a PKCE verifier, OIDC nonce, scopes, additional parameters, or internal metadata. Non-PKCE logins might happen to work, masking the bug until a provider enables PKCE or the app switches to OIDC.

If you build a custom-schema DTO for JSON/Redis storage, define and restore **all required fields**, including maps with the exact value types expected by the framework. You can serialize the full `OAuth2AuthorizationRequest` with an appropriate serializer, or maintain an explicit two-way mapping schema and test compatibility across Spring Security upgrades.

**Never store only `getAuthorizationRequestUri()` and parse its query string to rebuild the request on callback.** The URL does not carry internal data; parsing also risks breaking encoding or producing an object that differs from the original.

### 4.3. Differences Between `state`, OIDC `nonce`, and PKCE `code_verifier`

| Value | When created? | Who receives it? | Where verified? |
| --- | --- | --- | --- |
| `state` | When starting authorization | Provider receives in authorization request and echoes on callback | **Client** compares callback against saved request |
| `nonce` | When creating an OIDC request with nonce | Provider receives; ID Token carries matching nonce claim | **OIDC Client** when verifying ID Token |
| `code_verifier` | When initiating PKCE | Only Token Endpoint receives verifier after callback | **Authorization Server** when comparing with challenge |
| `code_challenge` | Derived from verifier | Authorization Endpoint receives | Authorization Server binds to authorization code |

PKCE example with `S256`:

~~~text
code_verifier  = strong random string, 43–128 valid characters
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

**Never store only the code challenge in place of the verifier**: they are different values, and the verifier cannot be recovered from the challenge hash. Nor can you generate a new verifier on callback; the provider already bound the code to the challenge from the earlier authorization request.

With OIDC, the repository or companion store must help the client retrieve the **expected nonce** for that exact authentication request; how Spring Security represents `nonce` internally can vary by version. When customizing `nonce`, ensure the ID Token verification step uses the matching value and continues verifying other claims such as issuer, audience, expiration, and signature.

## 5. Preserving Lifetimes: TTL, Expiry, and Replay

### 5.1. Why Does an Authorization Request Need a TTL?

An authorization request is a **short-lived transaction**, spanning from redirect until callback processing. If stored indefinitely:

- An old `state` could outlive the window in which the transaction should remain valid.
- PKCE verifiers, OIDC nonces, and sensitive metadata linger too long.
- Abandoned requests accumulate in the session/Redis.
- It becomes hard to distinguish a stale callback from an active flow.

A practical policy might set a TTL of, say, **10 minutes**, tuned to login UX, MFA duration, provider timeouts, and infrastructure. **10 minutes is purely illustrative**, not a fixed constant in OAuth2/OIDC or a mandatory Spring Security default.

On save:

~~~text
createdAt = time authorization request was created
expiresAt = createdAt + authorizationRequestTtl
~~~

On callback:

~~~text
if request does not exist:
    reject

if currentTime >= expiresAt:
    reject and delete expired record

if state/session/registration does not match:
    reject

otherwise:
    consume request exactly once
    continue callback processing
~~~

Time comparisons should rely on a trusted system clock in your environment. In distributed apps, all instances and Redis nodes need proper clock synchronization; never compute TTLs from an unverified timestamp supplied by the client browser.

### 5.2. Repository TTL Is Not Token Lifetime

| Lifetime | Subject | Who controls it? |
| --- | --- | --- |
| Authorization request TTL | Request awaiting callback | OAuth2 Client app/repository |
| Authorization code lifetime | Authorization code issued by IdP | Authorization Server |
| Browser session timeout | Application session/browser | Application and session store |
| Access token expiration | Issued access token | Authorization Server and verified by Resource Server |
| Refresh token expiration | Refresh token if issued | Authorization Server/client policy |

Even if the authorization request repository still holds an entry, an expired authorization code still cannot be exchanged for tokens. Conversely, if the provider just issued a valid code yet the original request exceeded the client's TTL, **the client must still reject the callback**.

Choose a TTL aligned with the flow: too short causes users doing slow MFA to fail; too long bloats storage and keeps stale requests alive. Never substitute the access token's TTL for the authorization request TTL.

### 5.3. "Consume Exactly Once" Is Distinct from TTL

TTL prevents using a request too late. **One-time consumption** prevents reusing a request before it expires.

A repository can honor TTL yet still be buggy if two concurrent callbacks both read the same request and both proceed. Verify whether the "retrieve request for final processing and delete" operation is atomic in your storage engine.

~~~text
Start: state=S1 is valid

Callback A: consume(S1) -> returns request, deletes S1
Callback B: consume(S1) -> not found, rejected

Desired outcome: only one callback receives the request to process.
~~~

If storage only offers separate `GET` and `DELETE` calls, multi-worker environments suffer race conditions. Use atomic consume primitives such as `GETDEL` (where appropriate), transactions, compare-and-delete, Lua scripts, or storage-native equivalents. With Spring Security, note that the API separates `loadAuthorizationRequest` and `removeAuthorizationRequest`; your implementation must ensure **the consumption step** serves as the final gate before accepting the callback.

### 5.4. Why Must Abandoned Records Be Cleaned Up?

Many users click "Sign in" and then close the tab, so the callback never returns. If records are only deleted when callbacks arrive, orphaned requests accumulate forever. Depending on storage:

- With Redis, use **key TTLs** alongside an `expiresAt` check inside the payload if needed.
- With a session map, prune expired entries during reads/writes or run suitable cleanup; the session TTL acts as an outer bound.
- With a database, filter by `expires_at` on reads and run a dedicated cleanup job for expired rows.

Never use slow background cleanup as an excuse to accept expired requests. **Expiry validation must happen inline on the callback path**, while cleanup can run asynchronously.

## 6. Servlet Example: Custom Repository with TTL and One Pending Request per Session

The following example intentionally preserves the **one pending authorization request per HTTP session** model to highlight the contract. It demonstrates saving the **entire `OAuth2AuthorizationRequest`**, rejecting expired requests, and deleting the record once consumed by a callback.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.util.StringUtils;

public final class ExpiringSessionAuthorizationRequestRepository
        implements AuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    private static final String SESSION_KEY =
            ExpiringSessionAuthorizationRequestRepository.class.getName() + ".PENDING";

    private final Duration ttl;
    private final Clock clock;

    public ExpiringSessionAuthorizationRequestRepository(
            Duration ttl, Clock clock) {

        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        this.ttl = ttl;
        this.clock = clock;
    }

    @Override
    public void saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (authorizationRequest == null) {
            removeAuthorizationRequest(request, response);
            return;
        }

        if (!StringUtils.hasText(authorizationRequest.getState())) {
            throw new IllegalArgumentException("Authorization request must have state");
        }

        HttpSession session = request.getSession(true);
        StoredRequest stored = new StoredRequest(
                authorizationRequest,
                clock.instant().plus(ttl));

        synchronized (session) {
            session.setAttribute(SESSION_KEY, stored);
        }
    }

    @Override
    public OAuth2AuthorizationRequest loadAuthorizationRequest(
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return null;
        }

        synchronized (session) {
            return readIfValid(session, request);
        }
    }

    @Override
    public OAuth2AuthorizationRequest removeAuthorizationRequest(
            HttpServletRequest request,
            HttpServletResponse response) {

        HttpSession session = request.getSession(false);
        if (session == null) {
            return null;
        }

        synchronized (session) {
            OAuth2AuthorizationRequest original = readIfValid(session, request);

            // Consume only when state matches and the request is still valid.
            if (original != null) {
                session.removeAttribute(SESSION_KEY);
            }
            return original;
        }
    }

    private OAuth2AuthorizationRequest readIfValid(
            HttpSession session, HttpServletRequest request) {

        Object attribute = session.getAttribute(SESSION_KEY);
        if (!(attribute instanceof StoredRequest stored)) {
            return null;
        }

        if (!clock.instant().isBefore(stored.expiresAt)) {
            session.removeAttribute(SESSION_KEY);
            return null;
        }

        String incomingState =
                request.getParameter(OAuth2ParameterNames.STATE);

        if (!StringUtils.hasText(incomingState)
                || !stored.request.getState().equals(incomingState)) {
            return null;
        }

        return stored.request;
    }

    private static final class StoredRequest {
        final OAuth2AuthorizationRequest request;
        final Instant expiresAt;

        StoredRequest(
                OAuth2AuthorizationRequest request, Instant expiresAt) {
            this.request = request;
            this.expiresAt = expiresAt;
        }
    }
}
~~~

**Meaning and limitations of this example:**

- Stores the complete `OAuth2AuthorizationRequest`, keeping `additionalParameters` and `attributes` intact in the session.
- `clock` is injected for explicit time control; use `Clock.systemUTC()` in production and a controllable/fixed clock in tests.
- `request.getSession(false)` on callback avoids creating an **empty new session** merely to "handle" a context-less callback.
- When `state` is missing or wrong, `load`/`remove` return `null`. Never turn the callback's state into a new valid state.
- `remove` deletes the request when a valid match is found; subsequent callbacks will not retrieve the old request.
- `StoredRequest` here is internal data for a **standard single-JVM/session**. If sessions are passivated or distributed, ensure stored data is **serializable** with the right serializer and class version; you can replace it with a serializable DTO and full-request preservation.
- The single session key holds **one pending request**. Logging in on Tab B overwrites Tab A's flow. To support multiple tabs, use a state-to-record map with TTLs and concurrency management.
- `synchronized(session)` only coordinates access to the same session object within one process. **It does not guarantee atomicity across nodes or differing session wrappers**. Do not deploy this snippet verbatim as a distributed repository.
- `saveAuthorizationRequest(null, ...)` logic must fit the framework contract. Implementations requiring deletion of entries even when `state` is absent must define safe deletion scoping; this example removes only when the callback state matches.
- The goal is demonstrating **request preservation and TTL**. Production concerns like overwrite prevention, session hardening, serialization/rotation, multi-tab support, and multi-instance atomic consumption are covered next.

> In real systems, choosing a custom repository must reflect deployment topology and security requirements. Adding a TTL by copying a session snippet is not enough to solve multi-instance deployments.

### 6.1. Wiring the Repository into Spring Security Servlet

~~~java
@Configuration
class LoginSecurity {

    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new ExpiringSessionAuthorizationRequestRepository(
                Duration.ofMinutes(10),
                Clock.systemUTC());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestRepository(repository)));

        return http.build();
    }
}
~~~

This configuration does not replace ID Token verification or perform manual token requests; standard OAuth2 Login components continue operating on the request restored by the repository.

Example `application.yml` for an OIDC client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://idp.example.com/realms/staff
~~~

When deploying, register the exact redirect URI at the provider, use HTTPS, and ensure the browser's session cookie returns on the callback.

## 7. Multiple Tabs, Multiple Flows: Key by State While Preserving Session Binding

One session may spawn multiple parallel authorization requests:

~~~text
Tab A:
    state = A1, verifier = VA, nonce = NA
Tab B:
    state = B2, verifier = VB, nonce = NB

Callback tab B -> must retrieve B2, VB, NB
Callback tab A -> must retrieve A1, VA, NA
~~~

Using a single session attribute lets request B overwrite request A. A custom repository can use:

~~~text
session.pendingRequests = {
    state_A1: {
        request: <OAuth2AuthorizationRequest A>,
        createdAt: ...,
        expiresAt: ...
    },
    state_B2: {
        request: <OAuth2AuthorizationRequest B>,
        createdAt: ...,
        expiresAt: ...
    }
}
~~~

Accompanying responsibilities:

1. **Key by state:** only use unpredictable, properly formatted `state` values; never accept arbitrary keys from the browser to overwrite client config.
2. **Session binding:** the same `state` in a different browser/session must not recover the original request. `state` is a correlation value; knowing `state` must not expose metadata via any public API.
3. **Per-entry TTL:** A can expire while B remains valid.
4. **Consume the exact entry:** callback B deletes only B, leaving A intact.
5. **Capacity limit:** enforce a maximum number of pending requests per session to prevent session or Redis bloat from abuse.
6. **Concurrency:** map structure, read/remove operations, and serialization must be safe under concurrent requests.
7. **Prune expired entries:** delete expired and consumed entries, with a strategy for abandoned flows.
8. **Prevent tenant/provider mix-up:** request A for tenant X must never be consumed by a callback/registration for tenant Y.

Example multi-tab data diagram:

~~~mermaid
flowchart TD
    A[Browser session] --> M["Pending map (state -> record)"]
    M --> SA["State A1 / Client corporate / TTL A"]
    M --> SB["State B2 / Client partner / TTL B"]
    SA --> RA["OAuth2AuthorizationRequest A<br/>attributes: verifier VA, OIDC context"]
    SB --> RB["OAuth2AuthorizationRequest B<br/>attributes: verifier VB, OIDC context"]
    CA["Callback state=A1"] --> SA
    CB["Callback state=B2"] --> SB
~~~

**Subtle pitfall:** if sessions are stored in Redis via Spring Session, mutating a `Map` fetched via `session.getAttribute(...)` does not automatically guarantee the mutation is flushed or atomically synchronized across multiple processes. Understand your session store's dirty-tracking/serialization semantics, and if needed design storage as **one record per state** with dedicated atomic operations rather than relying on single-instance Java locks.

## 8. Designing a Distributed Repository with Redis or a Database

When running multiple instances behind a load balancer, an authorization callback can land on a different node from the one that created the request. A local in-memory repository will fail unless paired with appropriate session routing/distribution.

### 8.1. Data Model in Redis

One logical representation:

~~~text
key:
  oauth2:authrequest:<hash-of-random-state>

value:
  version: 1
  originalAuthorizationRequest: <serialized full request>
  sessionBinding: <server-side session context or protected digest>
  registrationId: "corporate"
  createdAt: 2026-11-16T02:00:00Z
  expiresAt: 2026-11-16T02:10:00Z

redisTTL:
  600 seconds
~~~

This is a **data model**, not built-in field names or serializers from Spring Security. Choose serialization/deserialization that preserves all required `OAuth2AuthorizationRequest` types. `<hash-of-random-state>` avoids storing raw state in keys if policy requires it; since `state` is already random, protecting the context and data inside the record matters even more.

**On save:**

~~~text
save(request, browserContext):
    require strong, nonempty state
    require supported registration/client/provider
    serialized = serializeFullRequest(request)
    record = { serialized, boundContext, createdAt, expiresAt, schemaVersion }
    insertIfAbsent(key(state), record, ttl)
    reject / handle collision safely
~~~

**On load:**

~~~text
load(callback, browserContext):
    state = parseState(callback)
    record = read(key(state))
    if record missing or expired: return absent
    if not validSessionBinding(record, browserContext): return absent
    if not match(record.request.state, state): return absent
    return deserializeFullRequest(record)
~~~

**On consume:**

~~~text
consume(callback, browserContext):
    atomically:
        find record by state
        verify not expired
        verify browser/session binding
        verify state + intended client/provider context
        delete that record only
        return original request
~~~

The **atomically** part is vital. With Redis, use transactions/Lua/appropriate primitives for atomic compare-and-delete. Blindly running `GETDEL` by `state` **without checking session binding** allows anyone who knows `state` to consume another browser's entry without a valid session—enabling DoS or correlation disruption. When binding and expiration must be checked, fold both checks and the deletion into **the same atomic operation**.

With a database, use row locking/transactions or conditional `DELETE ... RETURNING ...` depending on engine. Verify transaction isolation, indexes, unique constraints on the state key, and cleanup of expired rows.

### 8.2. Avoid Confusing "Load" and "Consume"

Spring Security invokes the repository via standard methods, while your underlying store can expose a richer internal API, e.g.:

~~~java
interface AuthorizationRequestStore {
    Mono<Void> save(PendingAuthorizationRequest pending);
    Mono<PendingAuthorizationRequest> read(String state, BrowserBinding browser);
    Mono<PendingAuthorizationRequest> consume(
            String state, BrowserBinding browser);
}
~~~

This is an **illustrative application-defined abstraction**, not a Spring Security interface. An adapter implementing `ServerAuthorizationRequestRepository` or `AuthorizationRequestRepository` maps framework calls onto this store.

The goal is separating responsibilities cleanly:

- `read` only inspects still-valid data without accidentally consuming it.
- `consume` is the **atomic check-and-delete point**.
- Concurrent callbacks must never both get "consume succeeded."
- Never reconstruct a request from the callback's `state` once the original record has been deleted.

In some framework flows, `load` is called before `remove`. Never change `load` semantics to "delete immediately" if doing so causes `remove` to miss the request and break login. Match the actual lifecycle of the filter/provider version you run.

## 9. Serialization Pitfalls: Never Drop Attributes or Alter Types

This is the biggest risk when moving from in-memory session objects to JSON/Redis/databases.

Suppose a request has:

~~~text
OAuth2AuthorizationRequest:
    state: "s_M3..."
    clientId: "portal"
    redirectUri: "https://portal.example.com/login/oauth2/code/corporate"
    scopes: ["openid", "profile"]
    additionalParameters:
        code_challenge: "..."
        code_challenge_method: "S256"
        nonce: "..."
    attributes:
        registration_id: "corporate"
        code_verifier: "<random secret>"
        ... other Spring Security / application metadata
~~~

Exact map keys depend on version/customization; this simply illustrates structure. If a serializer:

- Drops `attributes` or `additionalParameters` because "they aren't shown in the UI";
- Converts `Set<String>` into a single `String` and restores it wrong;
- Turns enums, grant types, response types, or nested objects into untyped `Map`s;
- Breaks on new classes/fields introduced after a Spring Security upgrade;
- Stores the entire request unencrypted in a datastore accessible beyond scope;
- Reconstructs a new object with a substituted `state`;

then callbacks lose the ability to verify or exchange codes against the right request.

### 9.1. Fields to Include in a Storage Schema

| Data group | Design recommendation |
| --- | --- |
| Schema version | Add `version` to handle reading pre-/post-upgrade records |
| Full request | Retain all core fields, additional parameters, and attributes |
| Data types | Explicit type mapping, never arbitrary map stringification |
| Lifetime | Include `createdAt` and `expiresAt`; also set store TTL if supported |
| Session/tenant binding | Tie the request to the exact browser/tenant/provider |
| Integrity | Protect records from external tampering while trusted by client |
| Confidentiality | Protect sensitive verifiers/metadata at rest |
| Size bounds | Prevent oversized unexpected payloads in records |
| Upgrade path | Safely accept or reject legacy records; never guess missing types |

If using Java serialization directly, weigh deserialization risks, class version compatibility, and allowed-class policies. Only deserialize from trusted sources with an allowlisted/controlled serializer. For JSON, allowlist valid fields/types and avoid unrestricted polymorphic deserialization.

### 9.2. Can You Save Just a Few Fields If a Provider Doesn't Use PKCE/Nonce?

An overly minimal implementation might **happen to work** with one provider or version, yet become a technical trap when:

- A provider starts requiring PKCE.
- OIDC is enabled and nonce/claims verification is required.
- Moving from one client registration to multiple providers.
- Adding custom authorization request parameters.
- Upgrading Spring Security changes internal metadata.

Therefore, a custom repository should aim to **preserve the full `OAuth2AuthorizationRequest` contract**, rather than "saving just whatever current code happens to read."

## 10. WebFlux: Reactive Structure and TTL Considerations

In WebFlux, session lookup and store reads are asynchronous. A reactive shared-Redis implementation should return publishers and avoid blocking:

~~~java
public final class RedisServerAuthorizationRequestRepository
        implements ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> {

    private final ReactivePendingRequestStore store;

    public RedisServerAuthorizationRequestRepository(ReactivePendingRequestStore store) {
        this.store = store;
    }

    @Override
    public Mono<Void> saveAuthorizationRequest(
            OAuth2AuthorizationRequest authorizationRequest,
            ServerWebExchange exchange) {
        // Persist complete record with TTL, bound to session/browser.
        // authorizationRequest == null: handle deletion per contract.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> loadAuthorizationRequest(
            ServerWebExchange exchange) {
        // Read by state + browser/session context,
        // reject expired records, and restore full attributes.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> removeAuthorizationRequest(
            ServerWebExchange exchange) {
        // Atomically consume matching request, preventing reuse by a second callback.
        return Mono.error(new UnsupportedOperationException(
                "Implement with a reactive store"));
    }
}
~~~

This is an **architectural interface skeleton**, not a ready-to-use implementation. `ReactivePendingRequestStore` is an application-defined abstraction, and the three methods must be implemented against your concrete store. Never return `Mono.just(null)` since Reactor forbids null values; use `Mono.empty()` to represent an absent request.

When writing a reactive repository, keep in mind:

- Use `exchange.getSession()` and context-appropriate browser binding.
- Return `Mono` from a reactive Redis/database driver; never call `block()` on the event loop.
- Ensure `save` performs its side effect upon subscription; do not merely construct a publisher and drop it.
- `remove` must consume the matching record and never return an expired request.
- Set record TTL independently of access token lifetime.
- If storage fails, **fail closed**: never let a callback proceed because "state couldn't be read"; log a sanitized error and guide the user to restart login when appropriate.
- Never use unbounded `Mono.cache()` for an authorization request entry, as it could keep serving the request after consumption.

### 10.1. When Does WebFlux Use the Session Repository?

If an app only needs one or a few providers without many concurrent pending flows, WebFlux's session repository can suffice. `WebSessionOAuth2ServerAuthorizationRequestRepository` leverages Spring's `WebSession` during the authorization flow.

Build a custom repository only when driven by real requirements like custom TTLs, multi-tab support, specialized session stores, or multi-instance distribution. Every customization increases responsibility across concurrency, serialization, cookies, state protection, and filter integration.

## 11. Security Boundaries: Session, Browser, Tenant, and Provider

Even with a TTL, a repository is unsafe if it cannot enforce **who is allowed to consume which request**.

### 11.1. Session Binding

An authorization request originating from browser session A must be bound to session A or an equivalently protected context. If the Redis key is only `state`, add verification that the callback belongs to the **originating browser/context**.

Never store state in a global field such as:

~~~java
static OAuth2AuthorizationRequest lastLoginRequest;
~~~

When two users sign in, the later request overwrites the earlier one and leaks/mixes contexts. Nor should you use a single fixed key across all flows.

### 11.2. Tenant/Provider Binding

Multi-tenant systems may configure multiple OIDC Providers or client registrations. When the callback returns, you must know it belongs to the **exact client registration/provider** used at authorization request time.

Example:

~~~text
Tenant A:
  registrationId = "tenant-a"
  issuer = https://idp-a.example.com
  state = SA

Tenant B:
  registrationId = "tenant-b"
  issuer = https://idp-b.example.com
  state = SB
~~~

Tenant A's callback result must never complete Tenant B's transaction. Beyond `state` and session binding, applications may need defenses against **authorization-server mix-up** suited to multiple issuers and the active standards/implementations.

A custom repository must never look up `ClientRegistration` from an untrusted callback parameter while ignoring provider metadata in the original authorization request. Preserve issuer, registration bindings, and all Spring Security/OIDC token validations.

### 11.3. Open Redirects and Return URL Data

An app may store `returnTo=/orders/123` in internal metadata. Restrict return URLs to an allowed domain/path list and never read an arbitrary redirect URL straight from callback query parameters.

Using `state` as a carrier for an unvalidated return URL risks open redirects or information disclosure. If business data must be retained, bind it to the corresponding server-side record and validate it before redirecting post-login.

### 11.4. Protecting the Backing Store

Authorization requests can contain data sensitive enough to warrant protection policies, notably the PKCE verifier and tenant metadata. For Redis/databases:

- Grant read/write access only to the relevant service.
- Use TLS over the network where required.
- Avoid writing record contents to logs/monitoring.
- Consider encrypting stored data at rest and managing keys per system policy.
- Never expose a public API listing pending authorization requests.
- Prune expired records; enforce storage quotas and sensible rate limiting.

For cookie-based repositories, protect integrity; if holding verifiers or sensitive metadata, consider **authenticated encryption (AEAD)**, proper `Secure`/`HttpOnly`/`SameSite` flags, and replay protection. A browser-held session cookie **does not inherently protect record contents** simply by carrying `HttpOnly`.

## 12. Timing, Failures, and Retry Handling

### 12.1. Milestones to Distinguish

~~~text
T0  Browser initiates login
T1  Repository saves request, expiresAt = T1 + TTL
T2  Provider performs auth/MFA/consent
T3  Provider returns callback with code/state
T4  Client reads request, checks expiry, consumes
T5  Backend exchanges code at Token Endpoint
T6  OIDC client verifies ID Token, builds Authentication
~~~

If the callback arrives at `T3 > expiresAt`, reject it regardless of whether the authorization code is still valid. If the request was consumed at T4 and token exchange at T5 fails, the old callback **must not be reused**; the user starts a fresh flow.

### 12.2. Storage Failure at Callback Time

If Redis or the session store is temporarily unreachable, the repository cannot prove the callback matches a saved request. A store outage **does not permit skipping state/expiry checks**. The app can return a temporary login error and ask the user to retry from the start once infrastructure recovers.

Set appropriate timeouts and circuit breakers so slow storage doesn't hang all login threads. However, a circuit breaker must never cause the repository to synthesize a new request from the callback when the original record cannot be retrieved.

### 12.3. When the User Presses Back or Refreshes the Callback

Authorization codes are short-lived and typically **single-use**. If the user refreshes the callback URL:

- The request may already have been consumed, so the repository finds nothing.
- The authorization code may already be marked spent by the provider.
- The outcome must be a safely handled failure or returning the user to their active login state per app policy.

Never try to "fix" this by keeping the request around after successful authentication so callback refreshes succeed again.

### 12.4. When the User Loses Their Session Mid-Flow

For example, session timeout is 5 minutes while MFA takes 8 minutes. A repository entry surviving 10 minutes in Redis is **still not enough** if the callback cannot prove the original browser session.

Browser session timeouts, authorization request TTLs, and login flows must be designed in harmony. To support lengthy MFA, raise timeouts within bounded limits or use a protected alternative correlation scheme; never let session-less callbacks "rely on state alone."

## 13. When to Use the Default Implementation vs. Custom?

| Need | Starting choice | When custom adds value |
| --- | --- | --- |
| Web app logging into a few providers, session-based | `HttpSessionOAuth2AuthorizationRequestRepository` or WebFlux equivalent | Need explicit TTL/cleanup or storing multiple pending flows |
| Multi-instance app | Shared session store supported by framework | Need atomic per-state consumption or session-independent storage |
| Multi-tab login in the same browser | Review how default repository handles concurrent flows | Need a state-to-record map with per-flow TTLs |
| Multi-tenant with many IdPs | Repository capable of preserving full request/provider context | Need tenant/issuer binding and record-level access enforcement |
| Avoid server-side state | Weigh cost and risk before using cookies | Need authenticated encryption, replay protection, TTLs, and key rotation |
| Bearer-token-only API | Resource Server | No authorization redirect/callback, so this repository is unnecessary |
| Backend using only `client_credentials` | OAuth2 Client / authorized client manager | No authorization code callback, so this repository is unnecessary |

Adding a custom repository should be driven by **real requirements**: the default session mechanism already fits many OAuth2 Login apps, and every custom layer increases your responsibility over correlation.

## 14. Common Design Mistakes

### 14.1. Serializing Only `state`/`clientId`

**Symptom:** Browser hits callback with valid state, yet Token Endpoint returns `invalid_grant` under PKCE, or OIDC nonce validation fails.

**Cause:** Serializer omitted the full request, dropping verifier, nonce, or internal attributes.

**Remediation:** Preserve the complete request or a controlled schema with exact two-way type mapping and version migration.

### 14.2. Using TTL Only for Cleanup Without Checking on Read

**Symptom:** Cleanup job runs every 30 minutes while logical TTL is 10 minutes; a callback at minute 20 still gets processed.

**Cause:** Code relied entirely on the background cleanup job instead of checking `expiresAt` on the callback path.

**Remediation:** Check expiry during load/consume; background cleanup is strictly for resource reclamation.

### 14.3. `remove` Reads Without Deleting

**Symptom:** Old callbacks can be reprocessed or two concurrent threads both acquire the request.

**Cause:** Custom repository failed to implement one-time consumption.

**Remediation:** Retrieve and delete the exact record, using atomic primitives when multiple processes can access the same state.

### 14.4. Using Redis `GETDEL` Without Checking Browser Binding

**Symptom:** Someone knowing `state` can consume another browser's entry despite lacking the matching session.

**Cause:** Deleted the record by key before verifying binding conditions.

**Remediation:** Verify state, browser/session binding, tenant/registration, and TTL **in the same atomic operation** before returning the consumed request.

### 14.5. Using One Fixed Key in Session

**Symptom:** Logging in on two tabs causes the first tab to fail unpredictably.

**Cause:** Flow B overwrites flow A.

**Remediation:** Support multiple pending entries keyed by state, or intentionally adopt a single-pending-flow policy with clear error handling.

### 14.6. Storing Only in One Instance's Memory

**Symptom:** Single-node deployment works, multi-pod deployment fails callbacks intermittently.

**Cause:** Callback lands on a node that did not save the request, and the repository lacks shared storage.

**Remediation:** Shared session store, distributed store, or proper routing architecture; guarantee atomicity and lifecycle rules.

### 14.7. Extending TTLs to "Fix" Everything

**Symptom:** Setting TTLs to several hours yet still seeing state mismatches or callback failures.

**Cause:** Real bugs are lost cookies/sessions, overwritten requests, wrong redirect URIs, or unsaved PKCE verifiers.

**Remediation:** Diagnose the exact failing stage, tune lifetimes to real UX needs, and keep correlation checks intact.

### 14.8. Using Callback Data to Synthesize a Request

**Symptom:** When load returns nothing, code constructs a fresh `OAuth2AuthorizationRequest` from URL `state` and `code` to keep going.

**Cause:** Callback is "trusted" without proving an initiated transaction existed.

**Remediation:** **Reject callbacks lacking an original request**, requiring a fresh authorization flow.

## 15. System Observability and Testing Repository Behavior

In production, you need to see accurately **why a callback could not locate its request** without exposing secrets.

Operational events to emit:

~~~text
auth_request_saved
auth_request_loaded
auth_request_expired
auth_request_not_found
auth_request_state_mismatch
auth_request_consumed
auth_request_storage_failure
callback_token_exchange_failed
callback_oidc_validation_failed
~~~

Attach an internal correlation ID to stitch step logs together, while **never logging raw state, nonce, code verifier, authorization code, tokens, session cookies, or client secrets**. When logging `registrationId`, tenant, or host, apply data-minimization policies.

### 15.1. Behaviors to Verify in Application Tests

| Scenario | Expectation |
| --- | --- |
| Save then load with same state and session within TTL | Returns complete request, including `attributes`/`additionalParameters` |
| Callback with different state | Returns no matching request |
| Callback in different session even knowing state | Cannot read/consume the original session's request |
| After TTL | Load/consume returns absent; expired data is pruned |
| First valid callback | Consumes successfully; request is deleted |
| Second replayed callback | Cannot consume the request again |
| Two concurrent callbacks with same state | At most one consume succeeds |
| Two tabs with different states | Each tab gets its own verifier/nonce; no cross-talk if supported |
| PKCE flow | Verifier is preserved and sent in Token Request |
| OIDC flow with nonce | Sent nonce is correlated against ID Token for validation |
| Serialization round-trip | Request restores completely with exact attribute types |
| Restart/rolling deployment | With shared store, non-expired requests restore across compatible serializer versions |
| Legacy request with unsupported schema | Rejected safely instead of guessing missing values |
| Session logout/expire | Pending requests handled per policy; no callback bypasses binding |
| Storage unreachable | Callback fails closed; never bypasses state validation |

These are **design-verification scenarios** to clarify the repository contract; actual test implementation depends on your project's storage and framework.

### 15.2. Example Using a Controllable Clock

To test TTLs without real-time waiting, inject a `Clock` rather than calling system time directly everywhere:

~~~java
Clock initialClock = Clock.fixed(
    Instant.parse("2026-11-16T02:00:00Z"), ZoneOffset.UTC);

var repository = new ExpiringSessionAuthorizationRequestRepository(
    Duration.ofMinutes(10),
    initialClock);
~~~

When testing expiry, provide a controllable clock or clock abstraction to simulate timestamps past the TTL. Note that an immutable `Clock.fixed(...)` never advances on its own; to test time progression within the same instance, use a mutable test clock or appropriate injection.

Never use `Thread.sleep(600000)` to test authorization request lifetimes: it is slow and flaky, whereas TTL is pure logic testable with a mock clock.

## 16. Questions and Scenario Exercises

### Question 1. A callback has syntactically valid `state` and `code`, yet the repository finds no record. May token exchange proceed?

**No.** The client must prove the callback belongs to a previously created, still-valid authorization request. Without the original record, reject the callback and let the user start a new login.

### Question 2. Why is storing only `code_challenge` in Redis insufficient for PKCE?

Because the Token Endpoint requires the **original `code_verifier`** for verification. The challenge is normally a one-way hash derived from the verifier and cannot replace it.

### Question 3. Redis TTL deletes the key after 10 minutes. Is `expiresAt` still needed in the payload?

Depends on design, though recording `expiresAt` helps application-level validation, observability, and compatibility across multiple stores. **At minimum, guarantee no expired entry is ever returned**, even if background cleanup/expiration hasn't run yet.

### Question 4. Why can separate `GET` then `DEL` calls be insufficient across multiple pods?

Two callbacks can both read the record before either pod deletes it. Guaranteeing one-time consumption requires an **atomic** operation or equivalent concurrency control.

### Question 5. What if the callback `state` matches, yet arrives from a different browser session?

Under a session-bound design, that callback lacks the right context and must be rejected. `state` must not act as a standalone bearer credential capable of retrieving and consuming any request in storage.

### Question 6. Why must a custom serializer preserve `attributes` even though they are not in the Authorization URL?

Because Spring Security or the application may store **the PKCE verifier and internal metadata** inside `attributes` for callback/token exchange processing. Dropping `attributes` causes unrecoverable data loss.

### Question 7. Can pending requests be stored indefinitely since the provider's authorization code already expires on its own?

No. Authorization requests and codes have separate lifecycles. You still need request TTLs, one-time consumption, and cleanup for abandoned flows.

### Question 8. Can a WebFlux application reuse a Servlet implementation based on `HttpServletRequest` verbatim?

No. WebFlux requires `ServerAuthorizationRequestRepository` operating on `ServerWebExchange` and `Mono`; external stores must use reactive I/O and avoid blocking the event loop.

### Question 9. Two login tabs sharing a session with different states fail intermittently. What should be checked?

Check whether the repository stores **multiple pending requests** or only a single session attribute; if multi-tab support is needed, use a map keyed by state with per-entry TTLs and targeted entry consumption.

### Question 10. Why can an OIDC nonce error originate from the repository even when `state` matched?

Because `nonce` is a separate binding from `state`. If the request or required nonce metadata was dropped or mixed up during serialization or loading, the ID Token cannot be matched properly against the initial authentication request.

## 17. Official References

- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/AuthorizationRequestRepository.html)
- [Spring Security API — HttpSessionOAuth2AuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizationRequestRepository.html)
- [Spring Security API — ServerAuthorizationRequestRepository](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/server/ServerAuthorizationRequestRepository.html)
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)

**Key takeaway:** A custom authorization request repository must return **the complete original request** (especially `state`, PKCE verifier, OIDC correlation, and attributes), for the right **browser/session/tenant/provider**, within its valid **lifetime**, and allow **consumption only once**. These invariants must hold across multiple tabs, multiple instances, serializer changes, and network errors. If you cannot guarantee them, stick with Spring Security's standard repository or design equivalent storage safeguards before going to production.
