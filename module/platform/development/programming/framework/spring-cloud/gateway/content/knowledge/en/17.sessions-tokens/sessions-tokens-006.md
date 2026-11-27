# SaveSession and When Sessions Are Saved Before Forwarding in Spring Cloud Gateway

When an API Gateway uses **sessions**, a request may update session data and immediately forward to another microservice. If session state is persisted to a data store lazily, the downstream service could process the request **before the latest session state finishes saving**. In **SPRING_CLOUD_GATEWAY**, `SaveSession` is a **GatewayFilter Factory** built to solve this exact ordering problem: **forcing `WebSession` to be saved before continuing to forward the request to the backend**.

This lesson belongs to the **Sessions and Tokens** chapter and explains the semantics of `WebSession.save()`, the position of `SaveSession` in the reactive filter chain, conditions for a backend to read the session, its relationship with Spring Security/Spring Session, configuration, read-after-write ordering tests, and security limits. Route predicates, path/header transforms, service discovery, rate limiting, circuit breakers, retries, TLS, and observability still require separate policies; `SaveSession` does not replace them.

> **Version scope:** Primary configuration follows **Spring Cloud Gateway Server WebFlux** using the `spring.cloud.gateway.routes` namespace common in Gateway 4.x. `SaveSession` operates on **Spring WebFlux** reactive sessions, not Servlet `HttpSession`. Gateway Server MVC and newer Spring Cloud Gateway releases may use different APIs/namespaces. Always consult documentation for your exact release train, starter, and web stack before deploying.

## 1. Understanding Three Concepts: Session, Session ID, and Token

Before using `SaveSession`, separate three concepts often loosely lumped together as "session":

| Component | Meaning | Example |
|---|---|---|
| **`WebSession`** | Server-side reactive session object holding an ID, attributes, started state, and idle timeout | `session.getAttributes().put("workflow", "ready")` |
| **Session ID** | Reference identifier used by client/server to locate the same session; typically passed in a cookie per resolver config | `Cookie: SESSION=opaque-id` |
| **Access token** | Credential for an API to authenticate/authorize requests, such as a Bearer JWT or opaque OAuth2 token | `Authorization: Bearer eyJ...` |

With session-based authentication, the Gateway restores user state from the **session ID** sent by the browser. With a stateless JWT resource server, the Gateway validates requests from a Bearer token **without needing `WebSession`**. These are two distinct models; they can coexist in one system, but must never be treated as identical.

**`SaveSession` does not create JWTs, grant permissions, refresh access tokens, or turn a session into a backend-trusted credential.** It works strictly with the reactive session storage mechanism used by the Gateway application.

### What can a WebSession contain?

A WebFlux session may hold application attributes such as workflow state, OAuth2 login handshake state, certain security metadata, or framework-managed identifiers. However:

- Never treat any arbitrary attribute as a verified identity.
- Never dump passwords, raw access tokens, or sensitive secrets arbitrarily into the session.
- With a distributed session store, evaluate serialization, size, TTL, and access permissions.
- Never let backends trust an attribute like `role=admin` that a client could supply.

## 2. What Exact Problem Does SaveSession Solve?

The Spring Cloud Gateway documentation describes the **SaveSession GatewayFilter Factory** as forcing a `WebSession.save()` operation **before the forwarding call is made**. This is especially useful when using **Spring Session with a data store that persists lazily**, and you want to ensure session state is saved before invoking downstream.

Suppose within a single request:

1. A WebFlux/Spring Security component updates a session attribute to `stage=approved`.
2. The Gateway matches a route targeting `lb://orders-service`.
3. Downstream reads the same session from a shared store to decide how to proceed.

If the Gateway relies only on automatic session saving at the **end of the response**, the execution order can become:

~~~text
Gateway modifies session
    ↓
Gateway forwards request
    ↓
Downstream reads session store: still sees stale data
    ↓
Gateway finishes response and saves session
~~~

When the route includes `SaveSession`, the desired order is:

~~~text
Gateway modifies session
    ↓
SaveSession invokes WebSession.save()
    ↓
Waits for save operation to complete
    ↓
Gateway continues filter chain to forward
    ↓
Downstream reads session store: can observe the updated state
~~~

**Critical condition:** Downstream must **be able to look up the exact same session** via session ID and a shared store for early saving to make that state visible. By itself, `SaveSession` **does not transmit the `WebSession` object over HTTP**, does not attach a brand-new session ID to the downstream request, and does not establish cross-app session sharing.

## 3. Position in the Reactive Gateway Filter Chain

In Spring Cloud Gateway Server WebFlux, Spring Security `WebFilter`s and application `WebFilter`s can process requests **before the Gateway selects a route**. Once a route matches, `FilteringWebHandler` orders `GlobalFilter`s and `GatewayFilter`s for execution.

`SaveSession` is a **`GatewayFilter`**, not an application-wide `WebFilter`. Therefore, it participates only on requests matching a route configured with this filter (or via matching default filters).

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux / Security WebFilters
    participant G as Gateway route filter chain
    participant R as WebSession repository
    participant D as Downstream
    C->>W: HTTP request + session cookie (if present)
    W->>W: Restore / update WebSession
    W->>G: Route matched
    G->>G: SaveSession retrieves WebSession
    G->>R: WebSession.save()
    R-->>G: Save complete (Mono<Void>)
    G->>D: Forward request via routing filter
    D-->>G: HTTP response
    G-->>C: Return response to client
~~~

This diagram illustrates **the ordering guarantee `SaveSession` aims for**. In practice, Spring Session might use Redis or another reactive repository; the Gateway does not automatically share application state with downstream merely by sharing a `serviceId`.

### Pseudocode to remember the semantics

Conceptually, the filter corresponds to reactive composition like:

~~~java
return exchange.getSession()
    .flatMap(WebSession::save)
    .then(chain.filter(exchange));
~~~

This is **ordering-explanation pseudocode**, not code to copy manually when using the built-in factory. Its meaning:

- `exchange.getSession()` retrieves the reactive session attached to the exchange.
- `WebSession.save()` returns a `Mono<Void>` representing the save operation.
- `then(chain.filter(exchange))` allows the rest of the filter chain to run only after the session-save publisher **completes successfully**.

If the save operation errors, `SaveSession` does not proceed to forward the request; the error enters the Gateway's error-handling pipeline. **Never call `block()`** to wait for a session on a Netty event loop; use reactive composition as shown.

### "Save before forward" is not "save before response commit"

These are two distinct lifecycle points:

| Milestone | What Is Happening | Role |
|---|---|---|
| **Pre-forward** | Gateway prepares to send the request to the backend | `SaveSession` saves the session **before this step** |
| **Routing/downstream** | Gateway connects, sends the request, and awaits response | Backend reads the session only if a sharing mechanism exists |
| **Response commit** | WebFlux flushes status/headers/cookies to the client | Part of the response lifecycle, **not identical to `SaveSession`** |

`SaveSession` is **not** `ServerHttpResponse.beforeCommit`; it does not force early response commit, does not set HTTP status codes itself, and does not send `Set-Cookie` downstream. Persisting to the session store and returning a session cookie to the browser are separate steps handled by different WebFlux/Spring Session components.

## 4. Configuring SaveSession on a Route

Suppose the Gateway exposes `/api/orders/**` and the backend has service ID `orders-service`. On this route, you need session state saved before calling downstream.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-with-session
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - SaveSession
            - StripPrefix=1
~~~

Explanation:

1. `Path=/api/orders/**` decides whether the route matches.
2. `SaveSession` triggers saving `WebSession` before downstream filters execute forwarding.
3. `StripPrefix=1` rewrites `/api/orders/42` to `/orders/42`, independent of session contents.
4. `lb://orders-service` uses load balancing/discovery to select a backend instance.

**`SaveSession` takes no required configuration parameters.** The shortcut syntax is simply the filter name:

~~~yaml
filters:
  - SaveSession
~~~

The expanded factory declaration can also be written as:

~~~yaml
filters:
  - name: SaveSession
~~~

Do not invent `args.name`, `args.value`, or a session cookie name on this factory by analogy with other filters. Cookie policies and `SessionRepository` settings belong to the Spring WebFlux/Spring Session layer, not `SaveSession` parameters.

### Choosing routes that genuinely need early saving

Not every route needs `SaveSession`. For example:

- Stateful APIs where downstream must immediately read session state updated by the Gateway: **may need it**.
- Stateless Bearer JWT APIs where downstream validates tokens itself: usually **no reason to use `SaveSession`**.
- Read-only public data APIs without sessions: usually **not needed**.
- Login flows handled directly by Spring Security returning redirects before Gateway route selection: **`SaveSession` on a route may never run**.

Applying the filter selectively avoids unnecessary store writes and reduces latency/load on Redis or other session repositories.

## 5. Using `default-filters` for Multiple Session-Backed Routes

If many routes require guaranteed pre-forward saves, in Gateway Server WebFlux versions supporting `default-filters` you can configure:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - SaveSession
      routes:
        - id: orders
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
        - id: profile
          uri: lb://profile-service
          predicates:
            - Path=/api/profile/**
~~~

Routes inheriting the default filter will save sessions before continuing the chain, according to effective filter ordering.

**Considerations before applying globally:**

- Each `WebSession.save()` may perform I/O against the session store; attaching it to every route requires evaluating overhead and store failure modes.
- Requests matching no route may **bypass this `GatewayFilter`**.
- HTTP `401`/`403` responses blocked by Spring Security before Gateway routing may **not execute `SaveSession`**.
- If both `default-filters` and a route's `filters` declare `SaveSession`, avoid redundant save operations.
- Changing `default-filters` does not necessarily alter `discovery.locator.filters` on auto-generated routes; inspect runtime routes to confirm the filter is attached where expected.

Many applications are better off enabling `SaveSession` **only on stateful routes** rather than all traffic, especially when many APIs are cookie/session-free.

## 6. Filter Ordering and When Session Attributes Change

The benefit of `SaveSession` depends on **the data to be saved already being written to `WebSession` before `SaveSession` executes**.

Example of a valid flow:

~~~text
WebFilter / security component updates session.stage = "ready"
    ↓
Gateway matches Route
    ↓
SaveSession invokes WebSession.save()
    ↓
Gateway routes to backend
    ↓
Backend reads stage = "ready" from the same shared session repository
~~~

However, if a filter **after `SaveSession`** updates the session:

~~~text
SaveSession saves old state
    ↓
Later filter writes session.stage = "ready"
    ↓
Routing to backend
    ↓
Backend may still read the old state from the repository
~~~

At the end of the HTTP exchange, session management may save the later change, but **you cannot rely on that to guarantee updated state before the downstream call**.

### Pre-filter vs. post-filter

In Gateway WebFlux, code executing before `chain.filter(exchange)` is a **pre** operation; logic chained after the downstream `Mono` completes is **post** in reactive order. If you update the session in a **post-filter**, that update is too late for the goal "the backend sees the new state on the same request".

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    return chain.filter(exchange)
        .then(exchange.getSession().doOnNext(session ->
            session.getAttributes().put("stage", "ready")).then());
}
~~~

The snippet above is an **ordering anti-example**, not a production recommendation. It writes the attribute **after the downstream chain has completed**, so no `SaveSession` placed before it could ever make `ready` visible during that forward call.

To ensure session state affects downstream, apply updates **before the `SaveSession` step**, or structure filters cleanly so saving happens after all updates complete and before forwarding. Do not rely purely on YAML line position when `GlobalFilter`s, `Ordered`, nested filters, or error/retry conditions exist; verify effective runtime order.

## 7. How Are Sessions Created and Saved?

In WebFlux, `WebSession` exposes key operations:

~~~java
WebSession session = ...;

session.start();                              // Explicitly start session if needed
session.getAttributes().put("stage", "ready"); // Write attribute
Mono<Void> result = session.save();           // Publisher saving the session
~~~

This snippet merely illustrates the API on an existing `WebSession`, **not complete synchronous code inside a reactive handler**. In a WebFlux application, obtain the session via `exchange.getSession()` or framework injection, then compose reactively.

States to distinguish:

| State | Meaning | Does `SaveSession` Do Anything Extra? |
|---|---|---|
| Existing session with state to save | Session object can be written to repository | Triggers save before forwarding |
| Newly created and validly started session | Can generate a session ID and store attributes | Calls save, per session manager/repository |
| Session not yet `start()`ed and no state to save | May not yet require a persisted session | **Never assume `SaveSession` creates a login session on its own** |
| Invalidated session | No longer a valid session per lifecycle | Cannot use `SaveSession` to "revive" login |
| Expired session in repository | Client still sends an old cookie, but session is gone | Requires re-authentication/re-initialization per policy |

`WebSession` is restored/saved by `WebSessionManager` and the configured repository mechanism. When integrating **Spring Session**, a distributed session store like Redis can be used. Writing an attribute into `WebSession` **does not mean the data is durable in the store** at the exact moment another microservice reads it.

### Spring Session and lazy session stores

Spring Session replaces the default session manager with a repository shareable across instances when properly configured. Details to keep in mind:

- Gateway instances must share the **same session backend and compatible namespace/serialization** to access common sessions.
- Sessions have TTLs; timeout and eviction settings affect login behavior.
- Redis/repository failures are not ordinary HTTP routing errors; saving early can fail the request **before calling downstream**.
- A "lazy" session store may defer certain writes until the end of the exchange; `SaveSession` is the pipeline hook forcing persistence earlier.
- Never treat every `WebSession.save()` implementation as having database transaction or distributed lock semantics. It ensures the `save` publisher completes per the repository's contract, not that another backend using caches/replicas immediately sees consistent reads.

For strict read-after-write guarantees, verify **session repository consistency** and downstream read paths, not merely that `SaveSession` appears in YAML.

## 8. When Can a Backend Actually Read the Gateway's Session?

This is where many guides leave gaps. HTTP requests carry **headers, path, query, and body**; a Java `WebSession` object inside the Gateway **is not automatically serialized as an object sent to the backend**.

For downstream to read the same session itself, an explicit sharing design must be satisfied:

1. **Same session ID resolution**, typically from the `SESSION` cookie or a specifically configured cookie name.
2. **That session ID is actually present on the request reaching the backend**, or the backend receives another trusted identifier.
3. **Same session store**, namespace, key prefix, and compatible serializer if the backend reads `WebSession`/Spring Session directly.
4. **Access permissions and security boundaries** between Gateway, backend, and session store are properly enforced.
5. **Save/read timing aligns** with the store's consistency model.

If the backend only validates Bearer JWTs or receives verified identity via token exchange, it **does not need to share `WebSession`**. In that architecture, `SaveSession` may be unrelated to how the backend obtains identity.

### First-request new-session case

A very important nuance:

- A client sends its first request **with no session cookie yet**.
- The Gateway creates/starts the session and `SaveSession` persists it before forwarding.
- Yet the forwarded request may **still lack the new session ID**, because the browser's `Set-Cookie` header goes out on the **response**, rather than automatically turning into a `Cookie` header on the downstream request.

Consequently, the backend **is not guaranteed to read a brand-new session on the very first request**, even when `save()` succeeded.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway
    participant ST as Shared session store
    participant D as Downstream
    B->>G: Request 1, no Cookie yet
    G->>ST: Create/update then SaveSession.save()
    ST-->>G: Save succeeded
    G->>D: Forward Request 1 (may lack new session cookie)
    D-->>G: Response 1
    G-->>B: Response 1 + Set-Cookie for session
    B->>G: Request 2 + Cookie: SESSION=<id>
    G->>ST: Update then SaveSession.save()
    ST-->>G: Save complete
    G->>D: Forward Request 2, existing cookie may be forwarded
    D->>ST: Look up session by ID if sharing repository
    ST-->>D: Updated state
    D-->>B: Response 2 via Gateway
~~~

**Never arbitrarily inject the session ID into a downstream header as a quick fix.** If your design requires authentication on the very first call, use proper token propagation/internal authorization or an identity contract secured by TLS/mTLS, spoofed-header stripping, and backend validation.

## 9. Java Example: Writing Attributes Before Gateway Filters Run

The following **lab-only** example illustrates a `WebFilter` updating a session attribute before route `/lab/session/**` is matched. Never write session state for every public request as a substitute for login.

~~~java
package example.gateway.lab;

import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class LabSessionMarkerFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String path = exchange.getRequest().getPath()
            .pathWithinApplication().value();

        if (!path.startsWith("/lab/session/")) {
            return chain.filter(exchange);
        }

        return exchange.getSession().flatMap(session -> {
            // Lab: start session, then mutate state before route filters.
            session.start();
            Integer oldCount = session.getAttribute("labCounter");
            session.getAttributes().put("labCounter",
                oldCount == null ? 1 : oldCount + 1);

            return chain.filter(exchange);
        });
    }
}
~~~

Then declare the lab route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: lab-shared-session
          uri: http://localhost:9090
          predicates:
            - Path=/lab/session/**
          filters:
            - SaveSession
            - StripPrefix=2
~~~

When calling `/lab/session/check`, the path filter forwards `/check` to the backend. `LabSessionMarkerFilter` runs at the `WebFilter` layer and updates the session **before** the `SaveSession` Gateway route filter executes.

**Example limitations:**

- `@Component` and `Ordered.HIGHEST_PRECEDENCE` are used deliberately to demonstrate early execution; in apps with Spring Security, verify filter order and endpoint protection policies.
- `session.start()` initiates a session for the lab request without authenticating anything; lock down the endpoint to avoid unbounded session creation by strangers.
- Incrementing `labCounter` is a naive read-modify-write and is **not safe as a distributed counter under concurrent requests sharing the same session**.
- The backend can read `labCounter` from `WebSession` only with **the same repository + session ID** as analyzed in section 8.
- Never store access tokens, real user identities, or secrets in lab tests.

### What can the lab backend verify?

If the backend also uses Spring WebFlux + Spring Session with a shared repository and compatible cookie ID, an endpoint can read `labCounter` from **its own request's `WebSession`**. If the backend is just a simple echo server without Spring Session, it can log the `Cookie`/path, but **cannot prove on its own that the data is in Redis**.

You can use a test backend with access to the session repository or a closed-environment store inspector to compare state at the exact moment downstream receives the request. Never print session IDs, tokens, or sensitive session contents in production logs.

## 10. Hands-On Testing: Verifying Save Before Forwarding

### Prerequisites

- Gateway Server WebFlux on `localhost:8080` with route `lab-shared-session` as in section 9.
- Lab backend on `localhost:9090` exposing `GET /check`; to read state, it must share the session repository.
- Real or test session repository where saves can be observed; with Spring Session Redis, ensure both apps use compatible settings.
- Appropriate security policy and access restrictions on `/lab/session/**` in the test environment.

### Step 1 — Request creating the session and receiving the cookie

~~~bash
curl -i -c session-cookies.txt \
  "http://localhost:8080/lab/session/check"
~~~

`-c` instructs cURL to save cookies returned by the server into a file **in the operator's lab environment**. Inspect the response to identify the actual cookie name, often `SESSION` under standard Spring Session configuration; **never assume it is always `JSESSIONID` or `SESSION`**.

On the first request, the Gateway creates the session and sends `Set-Cookie` to the browser/client. The backend **may not receive the new session ID on that same request**, so if the endpoint reports `missing` here, do not immediately conclude `SaveSession` is broken.

### Step 2 — Send back the received cookie

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt \
  "http://localhost:8080/lab/session/check"
~~~

`-b` sends the saved cookie. `LabSessionMarkerFilter` increments `labCounter` at the Gateway; `SaveSession` saves it before forwarding. If the backend reads the same session from the repository, it can observe **the updated value from turn 2**, not the stale value from the previous turn.

In the test environment, check all of these together:

| Observation | What to Verify |
|---|---|
| Cookie sent by client | Exact session ID issued by Gateway in the previous response |
| Session at Gateway | `labCounter` incremented before the `SaveSession` step |
| Session store | Updated data present when the save operation completes |
| Downstream request | Backend receives `/check` with the expected cookie |
| Backend session | Reads the exact same session and updated value, if sharing is configured |
| Client response | Handled normally without leaking sensitive IDs/attributes |

### Step 3 — Temporarily removing `SaveSession` in the lab

Strictly in a controlled environment, remove `SaveSession` from the route while keeping everything else unchanged, then repeat the test. If the session repository/manager writes lazily later, the backend **may observe the prior value** during forwarding. However, it might **still observe the new value** if the implementation persists eagerly; that is not necessarily a test bug.

**Do not claim "without `SaveSession` it is always wrong".** The goal is proving ordering guarantees when needed and measuring the behavior of your **actual repository and version**.

### Step 4 — Testing session repository failures

In the lab, simulate the repository returning errors or becoming unavailable. When `save()` fails, the route may fail **before calling downstream**, with an HTTP status decided by error handling. Check timeouts, connection pools, operational fallbacks, and error rates; never assume `SaveSession` silently ignores errors and keeps serving requests.

### Step 5 — Testing concurrency

Send two concurrent requests with the same session ID updating an attribute. `SaveSession` saves before each forward, yet **does not turn session updates into distributed-locked transactions**. With `labCounter`, lost updates can occur if the repository lacks synchronization. If business logic demands strict accuracy, use storage with atomic operations/transactions/optimistic locking instead of using `WebSession` as a transactional counter.

## 11. SaveSession and Spring Security/OAuth2

### With session cookie login

Spring Security WebFlux can use `WebSession` for login flows and related state (such as OAuth2 login). Once a user is logged in, other Gateway routes may need current session state saved before calling backends.

However:

- An `oauth2Login` step may return a **redirect** directly inside the security filter chain without selecting a Gateway route; thus `SaveSession` on a downstream route **will not necessarily run on login responses**.
- Having a session does not automatically tell the backend who the principal is; design proper **identity propagation**.
- Backends must authorize requests using trusted tokens/identities; session attributes from another app are not trusted by default.
- Logout requires proper invalidation/revocation/cookie handling via security and repository mechanisms. `SaveSession` is not a logout filter.

### With OAuth2 `TokenRelay`

Spring Cloud Gateway's `TokenRelay` deals with attaching an OAuth2 client/authorized client's valid access token on backend calls when Spring Security/OAuth2 Client is properly wired. It is **not synonymous** with `SaveSession`:

| `SaveSession` | `TokenRelay` |
|---|---|
| Operates on `WebSession.save()` | Operates on access token relay |
| Ensures session state is saved before forwarding | Attaches the right credential to downstream requests |
| Does not create `Authorization` headers | May attach `Authorization: Bearer ...` per supported mechanisms |
| Useful in stateful/shared-session flows | Useful when downstream consumes OAuth2 tokens |
| Does not authenticate users itself | Requires proper authentication/authorized client |

A Gateway running as a **stateless JWT Resource Server** may not need `SaveSession` at all for authentication. Conversely, a Gateway using OAuth2 login with `WebSession` may care about state-save ordering while still deciding `TokenRelay` and token audience policies separately.

### Watch session fixation and cookie policies

Session-based applications must handle post-login session fixation via Spring Security mechanisms, session timeouts, `HttpOnly`, `Secure`, `SameSite`, and domain/path cookie attributes, plus CSRF for cookie-driven flows. Never use `SaveSession` as an excuse to disable CSRF or allow `*` in CORS.

## 12. Multi-Instance Gateways and Multiple Backends

If the Gateway runs two instances A/B behind a load balancer:

~~~mermaid
flowchart LR
    C["Browser + session cookie"] --> LB["Ingress / load balancer"]
    LB --> GA["Gateway A"]
    LB --> GB["Gateway B"]
    GA --> STORE["Shared session repository"]
    GB --> STORE
    GA --> BACK["Downstream microservice"]
    GB --> BACK
    BACK -.->|"If a session-reading contract exists"| STORE
~~~

Critical operational requirements:

- **Do not depend on sticky sessions** if the architecture expects any Gateway instance to read sessions from a shared repository.
- Gateway instances must share identical cookie resolver settings, session namespaces, clocks, TTLs, and compatible serialization.
- If downstream services read the same repository, restrict session-store access with least privilege; never let every service read every user's entire session.
- `SaveSession` does not synchronize clocks, solve repository eventual consistency/caching, or prevent concurrent update conflicts on the same session.
- An unhealthy backend instance, wrong discovery entry, or unresolvable `lb://` target can still fail even when `SaveSession` succeeds.

For systems with high security requirements, **passing tokens with proper audience and scope** or a verified internal identity is usually cleaner than letting every backend read the session store directly. The architectural choice depends on your threat model and compatibility needs.

## 13. Performance, Errors, and Observability

`SaveSession` sits on the **request critical path** before forwarding. If the session repository requires network I/O, save latency adds directly to request latency.

| Risk | Impact | Mitigation |
|---|---|---|
| High-latency Redis/repository | Increases delay before downstream is called | Monitor save operation latency and timeouts |
| Repository outage | Requests may fail prior to routing | Monitor availability, connection pools, and storage-layer timeouts/circuits |
| Enabling `SaveSession` on stateless routes | Unnecessary load and cost | Apply only where save ordering is genuinely required |
| Large session payloads | Heavy I/O/serialization and memory growth | Keep sessions lean; avoid dumping large data/PII arbitrarily |
| Concurrent requests on one session | Races/lost updates | Use storage with appropriate synchronization primitives |
| TTL expires mid-request | Backend cannot find session despite client cookie | Review timeouts and expiration semantics |
| Mismatched cookies or namespaces across services | Backend fails to retrieve state | Audit resolvers, stores, serializers, and domain/path settings |
| Retries/fallbacks | May trigger multiple forwards after a single save, depending on order | Design idempotency, timeouts, and verify filter order |

**Separate metric groups:** time-to-route, session save duration, `lb://` instance selection time, downstream latency, repository error rate, and `401/403/429/5xx` ratios. Never blame every `503` on the load balancer when a session-save operation timed out before routing.

### Safe logging

You can log **route ID**, service name, whether a session existed, save duration, and error outcomes at appropriate log levels. Never log:

- Raw session IDs or cookie values.
- Bearer access/refresh tokens.
- Session attributes containing personal identity, addresses, emails, or security secrets.
- Full cache/session repository dumps.

If a correlation ID is needed, generate/validate a non-sensitive ID per observability policy; never turn session IDs into public trace IDs.

## 14. Troubleshooting: When SaveSession Appears Not to Work

| Symptom | Causes to Check | How to Verify |
|---|---|---|
| Session missing in repository | Session not started, no state to save, wrong repository, or route didn't match | Inspect `WebSession` lifecycle, Spring Session config, and route/filters |
| Backend still reads stale state | Attribute updated after `SaveSession`, repository caching/consistency, or different session | Check pre-filter order and confirm identical ID/store |
| Backend sees no session on first request | Client had no cookie yet; `Set-Cookie` only arrives on the response | Test the second request carrying the issued cookie |
| Gateway has session, backend does not | Backend lacks shared repository integration or uses a different cookie resolver | Check cookies, namespaces, serializers, and trust boundaries |
| Gateway returns 5xx before calling backend | `save()` failed/timed out or an earlier filter blocked the request | Inspect `save()` publisher logs and downstream call counts |
| Response missing `Set-Cookie` | No persisted session yet, cookie policy, session resolver, or response error | Inspect `start()`/lifecycle and response headers |
| `SaveSession` doesn't run on login pages | Security handler returns redirect/401 before Gateway routes run | Inspect `WebFilter`/security handlers and route matching |
| `TokenRelay` doesn't forward Bearer | Missing OAuth2 client/authorized client or relay misconfiguration | Debug `TokenRelay` separately; `SaveSession` does not create tokens |
| Fails only on certain Gateway nodes | Divergent session/Redis config or inconsistent route configs | Compare per-instance settings, store namespaces, versions, and clocks |
| `404` after `SaveSession` | Wrong route path/rewrite or downstream endpoint mapping | Check route predicates, `StripPrefix`, and backend paths |
| `401`/`403` despite saved session | Unauthenticated principal, missing scope/role, or cookie not forwarded | Check Spring Security policy; saving is not login |
| Redis load spiked after deploy | `default-filters: SaveSession` applied too broadly | Measure save call rates/latency and narrow scope |

### Five-question isolation workflow

1. **Did the request match the right Gateway route** carrying `SaveSession`, or did security/rate limiting intercept it earlier?
2. **Was the session started/updated** before this filter ran?
3. **Did `WebSession.save()` complete successfully** before the downstream call began?
4. **Which session ID did the backend receive**, and does it read the matching store/namespace/serializer?
5. **Who generated the final response**: backend, fallback, error handler, Spring Security, or web server?

An echo backend can help observe path, `Cookie` header, and arrival timing, **but echoing a cookie alone never proves the session was persisted**. Proving read-after-write requires inspecting the repository and backend directly.

## 15. Pre-Production Checklist

- [ ] I know `SaveSession` is a **GatewayFilter Factory**, not an application-wide `WebFilter` covering every HTTP request.
- [ ] I understand the filter invokes `WebSession.save()` **before the chain proceeds with forwarding**.
- [ ] I distinguish `WebSession`, session ID/cookie, and Bearer tokens/JWTs.
- [ ] I do not use `SaveSession` to authorize, log users in, or attach tokens downstream.
- [ ] I know attributes to be persisted must be updated **before `SaveSession`**.
- [ ] I enabled it only on session-dependent routes, avoiding blanket application across stateless APIs.
- [ ] I know `- SaveSession` takes no arguments.
- [ ] I verified Spring Session/repository config, TTLs, consistency, namespaces, and serialization for shared sessions.
- [ ] I understand the first request creating a session may **not yet carry the new session cookie to the backend**.
- [ ] I tested save-before-forward using **requests carrying an existing session ID**.
- [ ] I tested repository errors/timeouts and concurrent requests.
- [ ] I clarified the security model: session cookies, OAuth2 login, JWT Resource Server, `TokenRelay`, or token exchange.
- [ ] I still enforce session fixation protection, logout, CSRF, `SameSite`, `Secure`, `HttpOnly`, and TLS per threat model.
- [ ] I reviewed `lb://`, path rewrites, rate limiters, retries/circuit breakers, and fallbacks independently of sessions.
- [ ] I measure session-save latency/errors without logging session IDs, cookies, tokens, or private data.
- [ ] I verified multi-instance Gateway cluster behavior and backend transport security.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up **SaveSession GatewayFilter Factory** under **Server WebFlux** for your exact Gateway version.
- [Spring Framework — WebSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html) — `start()`, `getAttributes()`, `save()`, and reactive session lifecycle.
- [Spring Framework — WebSessionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionManager.html) — managing and persisting sessions per request/response.
- [Spring Session Reference](https://docs.spring.io/spring-session/reference/) — repositories, distributed sessions, Spring Session Redis, and session-sharing considerations.
- [Spring Security Reactive Reference](https://docs.spring.io/spring-security/reference/reactive/index.html) — `SecurityWebFilterChain`, OAuth2 login, JWT resource server, and security in WebFlux.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — semantics of `Mono<Void>`, `flatMap`, `then`, and composing asynchronous operations.

**Takeaway:** `SaveSession` ensures **`WebSession` persistence executes and completes before the Gateway forwards the request** down the reactive pipeline. It helps when session state is saved lazily yet the backend needs to read it immediately. Still, for the backend to see the latest session, you must **update the session before the filter, persist to a shared repository, and pass the session ID under a trusted contract**; it is neither a token-issuance mechanism nor a substitute for downstream security.
