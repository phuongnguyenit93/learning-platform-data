# Session Affinity and the Impact of Session State

A load balancer distributes requests across multiple servers or instances to increase throughput and availability. However, an application may store session state in each instance's memory. When a subsequent request is routed to a different instance, the new server may not find the session data, causing users to be logged out, lose their shopping cart, or have to repeat actions.

**Session affinity** (also called sticky sessions or session persistence) is a mechanism that attempts to route subsequent requests from the same client or session to the same backend for a period of time. This mechanism is useful when an application still holds local session state, but it also reduces load-distribution flexibility and can affect scalability, failover, and load balance.

This lesson places session affinity in the context of cloud compute workload design: understanding where session state resides, how the load balancer identifies clients, what happens when a backend fails or scales, and when to move session state out to a shared store.

After this lesson, you will be able to:

- Explain session affinity and distinguish it from user authentication or storing session state.
- Compare cookie-based affinity, source-IP affinity, and consistent hashing.
- Describe the impact of sticky sessions on load distribution, autoscaling, health checks, and failover.
- Design stateless applications or use a shared session store to reduce reliance on a single backend.
- Configure and protect session cookies, lifetimes, access permissions, and session data.
- Test behavior when backends fail, instances are added/removed, or connections are long-lived.

## 1. What Is Session State?

A session is the interaction context maintained across multiple requests from a user or client. HTTP is inherently a stateless protocol: each request is independent at the protocol layer. Applications typically create a session mechanism to remember state across requests.

For example, an e-commerce website might store in a session:

- Whether the user is logged in and the user's identifier.
- A temporary shopping cart or a reference ID to the cart.
- Language, currency, or UI preferences.
- Multi-step state of a checkout workflow.
- CSRF tokens or temporary navigation data.
- Short-lived business data tied to the current interaction.

A session is usually identified by a session ID sent in a cookie or a token mechanism. The server uses that ID to look up session state in the appropriate storage location.

### Where Can Session State Reside?

| Storage Location | How It Works | Advantages | Limitations |
|---|---|---|---|
| Process local memory | Each instance keeps sessions in its own RAM | Fast, simple, no external service required | Lost on process restart; requests must return to the exact instance; hard to scale and fail over |
| Instance local disk | Sessions are written to the VM/container filesystem | Can survive process restarts depending on disk lifecycle | Not naturally shared across instances; local/ephemeral disks can be lost on host replacement |
| Shared session store | Redis, database, or shared key-value store holds sessions | Any backend can serve requests if it can access the store | Adds dependency, network latency, cost, and HA/backup requirements |
| Client-side protected state | Partial state is signed or encrypted and sent in cookies/tokens | Reduces session store lookups | Size limits; difficult to revoke or update state; must protect data and keys |
| Hybrid | Cookie holds ID, shared store holds data; local cache can accelerate | Combines performance and shareability | Must handle cache invalidation, consistency, and expiration |

Do not store passwords, long-lived access tokens, sensitive payment data, or unnecessary secrets in sessions. Sessions should hold minimal information or references to data protected in the appropriate system.

## 2. How Does Session Affinity Work?

When a client sends an initial request, the load balancer selects a backend using its distribution algorithm. If affinity is enabled, the load balancer creates or reads a client/session identifier key and uses it to try selecting that same backend on subsequent requests.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant LB as Load balancer
    participant A as Backend A
    participant B as Backend B
    C->>LB: First request
    LB->>A: Select backend A
    A-->>LB: Response and affinity data
    LB-->>C: Response + affinity cookie
    C->>LB: Subsequent request + cookie
    LB->>A: Route back to backend A
    A-->>LB: Response using local session
    LB-->>C: Response
~~~

This mechanism is commonly called a sticky session. The term "sticky" describes routing stickiness between client and backend; it does not mean session data has been replicated or protected against loss.

### Two Types of Cookies May Appear

Distinguish between:

1. **Application session cookie:** Created by the application to identify the session and look up user state.
2. **Load balancer affinity cookie:** Created by the load balancer or ingress to remember the selected backend.

Both cookies can coexist. An application session cookie does not automatically guarantee requests return to the same backend unless the load balancer has a matching affinity rule. Conversely, an affinity cookie only controls routing; it does not prove the user is logged in and does not replace authentication/authorization.

## 3. Methods for Establishing Affinity

### Cookie-Based Affinity

The load balancer generates a cookie or reads a configured cookie to bind a client to a backend. Subsequent requests carry that cookie and the load balancer re-selects the corresponding backend.

Advantages:

- Distinguishes sessions sharing the same public IP address.
- Less sensitive to NAT or IP-sharing proxies.
- Suits web applications using HTTP/HTTPS.
- Allows configuring affinity duration and controlling cookie lifecycle.

Limitations:

- Clients must retain and send cookies; clients without cookie support may not remain sticky.
- Expired, deleted, or modified cookies can cause requests to switch backends.
- When a backend becomes unhealthy, the load balancer may have to pick another backend and local sessions may be gone.
- Requires understanding cookie domain, path, Secure, HttpOnly, and SameSite attributes.
- Affinity cookies must not be treated as authentication credentials.

Some services issue their own cookie, while others read an application-provided cookie or configure service-level TTLs. Behavior when a backend disappears varies across providers.

### Source-IP Affinity

The load balancer uses the source IP address to identify the client and attempts to send requests from that IP to the same backend.

Advantages:

- Requires no cookies or application changes.
- Works for protocols that do not carry cookies.
- Easy to enable in certain TCP environments or legacy apps.

Limitations:

- Many users can share one public IP via NAT, proxies, or corporate networks, causing them to pile onto the same backend.
- A single user's IP can change when switching mobile/Wi-Fi networks or traversing different proxies.
- IPv4/IPv6, proxy chains, and observed source addresses can alter the key.
- Can create skewed load distribution if one IP represents many clients.
- Unsuitable when source addresses are unstable or do not reflect application sessions.

Source-IP affinity is usually less accurate than cookie affinity for web applications with many users behind NAT.

### Consistent Hashing

The load balancer or proxy uses a key such as session ID, cookie, URL path, or header to compute a backend via hashing. Consistent hashing is designed to minimize the number of keys that must move between backends when nodes are added or removed, particularly when using a hash ring or equivalent algorithm.

Advantages:

- Provides stable routing based on application keys.
- Applicable to HTTP, TCP, or cache/proxy tiers.
- When membership changes, a portion of keys continues mapping to previous nodes.

Limitations:

- If keys are unevenly distributed, backend load can skew.
- Hashing alone does not store session state or guarantee data survives node loss.
- When a node leaves the ring, its keys shift to other nodes; local sessions can still be lost.
- Must handle empty, spoofed, or client-controlled hash keys.

### Header or Application-Defined Affinity

Some systems allow using an application-defined header or field as the key. This is flexible, but ensure the key contains no sensitive information, has balanced distribution, and cannot be manipulated by clients to force load onto a single backend.

### Method Comparison

| Method | Routing Key | Best Fit | Main Risks |
|---|---|---|---|
| Cookie-based | Affinity/session cookie | HTTP/HTTPS, browsers, web apps | Lost/expired cookies; backend failures; cookie security |
| Source-IP | Source IP | TCP or cookie-less clients | NAT/proxies group many clients under one key; IP changes |
| Consistent hashing | Session ID, cookie, header, or key | Proxies, caches, services needing stable mapping | Key skew; node membership changes; stores no state |
| Application-defined | App-supplied header/key | Systems with custom routing conventions | Untrusted keys, skewed distribution, or data exposure |

## 4. Load Balancing Algorithms and Affinity

Load balancers may support round robin, weighted round robin, least connections, least response time, or other variants. When affinity is enabled, the backend selection algorithm typically applies only on the first request or when an existing mapping becomes invalid.

For example:

- The first request is selected using least connections.
- The load balancer records the mapping client/session → backend A.
- Subsequent requests continue going to A even if backend B has fewer active connections.
- When the cookie expires or A is marked unhealthy, the load balancer can choose another backend.

Consequently, sticky sessions can reduce the effectiveness of load-balancing algorithms. If one session generates heavy request volume or holds long connections, one backend can receive far more work than others.

Do not assume affinity always overrides health checks. Normally an unhealthy backend should not keep receiving traffic solely because of a sticky cookie, though exact behavior must be checked against your load balancer.

## 5. Impact on Session State and User Experience

### When Requests Return to the Right Backend

If session state resides only in backend A's RAM, affinity helps subsequent requests return to A so the app can find the session. This is the primary benefit of sticky sessions for stateful apps.

For instance, a user adds an item to their cart on A. The next request to view the cart also reaches A, so local data remains intact.

### When Requests Hit a Different Backend

If the next request lands on B and B lacks the session state, outcomes can include:

- The user is forced to log in again.
- Cart contents or wizard state disappear.
- Requests return 401/403/404 errors or unexpected redirects.
- The application creates a new session, causing split state.
- Multi-step transactions cannot proceed.

These are typical symptoms when affinity is lost, cookies are missing, or the load balancer switches backends.

### Affinity Is Not Durable Storage

Even when requests consistently return to A, local sessions can still be lost upon:

- Process restarts or new version deployments.
- VM reboots or host replacements.
- Containers being rescheduled to another node.
- Instance termination due to autoscaling or failures.
- Backends being marked unhealthy.
- Load balancer remapping after cookie expiration.
- Users switching devices or browsers.

Sticky sessions reduce the chance of requests moving to another machine under normal conditions; they do not guarantee sessions survive failures.

## 6. Impact on Load Balancing and Scalability

Affinity alters request distribution. Some backends can hold many active sessions while new backends receive fewer sessions.

### Load Skew

Suppose there are 4 backends with equal capacity. Round robin distributes requests fairly evenly if requests have similar durations. With sticky sessions, a cluster of highly active clients or long-lived sessions can pile onto the same backend.

Causes of skew:

- One client generates far more requests than others.
- Long session durations or uneven workloads.
- Source-IP affinity grouping many users behind the same NAT.
- Skewed hash key distribution.
- Newly added backends not yet holding existing sessions.
- Long-lived WebSocket or TCP connections pinning backends for extended periods.

### Autoscaling and Scale-In

During scale-out, new instances can take new sessions while old backends still hold most existing sessions. Thus, increasing instance count does not immediately rebalance load.

During scale-in, terminating an instance holding many active sessions can destroy local state. A draining process is needed to stop accepting new sessions, let active sessions or connections finish within a reasonable deadline, and persist critical state durably.

### Drain Duration and Connection Lifetime

With HTTP keep-alive, WebSockets, or long-lived TCP connections, a load balancer can hold connections to a backend for a long time. Coordinate:

- Connection idle timeout.
- Maximum connection lifetime if supported by the service.
- Deregistration delay or connection draining.
- Application graceful shutdown.
- Session idle timeout and absolute timeout.
- Affinity cookie lifetime.

If the affinity cookie lifetime exceeds instance lifetime or drain duration, clients can keep presenting cookies pointing to a removed backend. The load balancer must have safe fallback behavior.

## 7. Comparing Sticky Sessions with a Shared Session Store

A common architectural alternative is moving session state out of each backend's memory into a shared store. Any healthy backend can then handle any request given a valid session ID and store access.

~~~mermaid
flowchart LR
    C[Client] --> LB[Load balancer]
    LB --> A[Backend A]
    LB --> B[Backend B]
    LB --> D[Backend C]
    A --> S[(Shared session store)]
    B --> S
    D --> S
~~~

### Benefits of a Shared Session Store

- Backends become interchangeable; requests do not need to return to a specific instance.
- Scale-out instances can immediately absorb traffic and balance load more evenly.
- Backend restarts or failovers rarely lose sessions as long as the store remains available.
- Rolling deployments and autoscaling become simpler.
- Session lifecycle is decoupled from VM/container lifecycle.

### Costs and Risks

- Adds a network hop and latency when reading/writing sessions.
- The session store becomes a critical dependency requiring HA, capacity, and monitoring.
- If the store overloads or loses connectivity, multiple backends are impacted together.
- Requires handling consistency, expiration, serialization, and schema versioning.
- Session data needs encryption, access controls, and proper retention.
- Cache eviction or overly short TTLs can drop sessions prematurely.

### When to Choose Which Option?

| Criterion | Sticky session + local state | Shared session store |
|---|---|---|
| Application changes | Usually minimal changes for legacy apps | Requires integrating a session repository/client |
| Session read latency | Can be very low via local RAM | Adds a network hop |
| Scale-out | New sessions hit new nodes; old sessions stay pinned to old nodes | New backends can serve existing sessions too |
| Backend failover | Local state may be lost | Can continue if the store is available |
| Scale-in/deploy | Requires draining and accepting session migration/loss | Easier to drain backends |
| New dependencies | Fewer on the session path | Session store requires HA and operations |
| Best fit | Legacy apps, hard-to-change local state, short-lived workloads | Apps needing HA, autoscaling, rolling deploys, and interchangeable backends |

Another design is stateless sessions: backends store no local session state; clients send signed or encrypted tokens. This avoids store lookups but requires token revocation plans, key rotation, short lifetimes, and payload size discipline.

## 8. Designing Secure Sessions

A session ID is typically a bearer credential: anyone holding a valid ID can be treated as owning the session. Protecting sessions is therefore just as important as protecting passwords.

### Cookie Attributes

For web application session cookies, consider:

- **Secure:** Send the cookie only over HTTPS.
- **HttpOnly:** Client-side JavaScript cannot read the cookie via standard APIs.
- **SameSite:** Mitigates certain CSRF risks depending on navigation flows and integrations.
- **Path** and **Domain:** Restrict cookie scope to what is necessary.
- **Max-Age** or **Expires:** Enforce cookie lifetime.
- Cookie names with appropriate prefixes such as `__Host-` when meeting prefix requirements.

Illustrative response header example:

~~~http
Set-Cookie: __Host-app_session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

This is an application session cookie, not necessarily a load balancer affinity cookie. Load-balancer-generated affinity cookies may have their own names and attributes; check service documentation and avoid altering platform-managed cookies if doing so breaks mapping.

### Session Lifecycle

- Generate sufficiently random, unpredictable session IDs.
- Regenerate session IDs upon login or privilege changes to mitigate session fixation.
- Enforce business-appropriate idle and absolute timeouts.
- Revoke sessions on logout, password changes, or detected risk.
- Never place session IDs in URLs, logs, analytics, or referrers.
- Rotate signing/encryption keys with a transition plan.
- Limit stored data and access permissions on the session store.
- Do not store sensitive data beyond actual requirements.

### Distinguishing Affinity Cookies from Session Authentication

Affinity cookies should be treated strictly as routing hints. If a client modifies or replays an affinity cookie, that must never grant access to user data. Backends must still validate session/application tokens and check authorization on every request.

## 9. Affinity Across Load Balancer Types and Protocols

### Layer 7 HTTP/HTTPS Load Balancers

Layer 7 can read cookies, headers, hosts, and paths, enabling cookie-based affinity or HTTP-content hashing. This is where sticky sessions are most commonly used for web applications.

Verify TLS termination, cookie rewrites, domain/path, proxy chains, and behavior when clients omit cookies.

### Layer 4 TCP/UDP Load Balancers

Layer 4 typically does not inspect HTTP payloads. Affinity may rely on source IP, source/destination tuples, or flow hashes. For TCP, an open connection usually stays pinned to one backend for its lifetime; that differs from guaranteeing every new connection from the same user reaches the same backend.

### WebSocket and Long-Lived Connections

WebSocket begins with an HTTP upgrade and then maintains a bidirectional connection. Once established, the load balancer typically keeps that connection pinned to the selected backend until close or timeout. Affinity for subsequent HTTP requests does not necessarily re-route an already open WebSocket connection.

When a backend drains or restarts, WebSockets may disconnect and clients must reconnect. If state recovery is required, store subscriptions, cursors, or business state in a shared store and design reconnect/resume logic.

### gRPC and Streaming

gRPC can use HTTP/2 multiplexing and long-lived streams. A single channel can reuse multiple RPCs over one connection, so connection-level load balancing differs from per-request distribution. Inspect load balancing capabilities across clients, proxies, and service meshes; never assume each RPC is automatically distributed independently.

## 10. Conceptual Affinity Configuration Example

Exact configuration depends on the cloud provider and load balancer product. The example below illustrates properties to decide, not a schema usable directly on every platform.

~~~yaml
load_balancer:
  listener:
    protocol: HTTPS
    port: 443
  backend_pool:
    name: web-backends
    protocol: HTTP
    port: 8080
  session_affinity:
    enabled: true
    mode: cookie
    cookie_ttl: 1800s
  health_check:
    path: /health/ready
    interval: 10s
    unhealthy_threshold: 3
  connection_draining:
    enabled: true
    timeout: 60s
~~~

When designing, answer:

- Is the affinity cookie managed by the load balancer or the application?
- What is the cookie TTL, and is it aligned with the session idle timeout?
- When a backend becomes unhealthy, does the load balancer drop old mappings?
- During scale-in, what is the maximum drain duration?
- Does the health check reflect application readiness?
- How are clients without cookies handled?
- Could cookies be leaked or forged to induce load skew?

Do not set TTLs overly long merely to prevent re-logins. Long TTLs keep clients pinned to older backends and slow load rebalancing. Overly short TTLs cause local sessions to drop if mappings rotate before the session expires.

## 11. NGINX Example with Sticky Routing

NGINX offers several ways to implement affinity depending on version and compiled modules. The example below uses `ip_hash` to illustrate basic source-IP affinity:

~~~nginx
upstream app_backends {
    ip_hash;

    server 10.20.1.11:8080;
    server 10.20.1.12:8080;
    server 10.20.1.13:8080;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        proxy_pass http://app_backends;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

`ip_hash` illustrates mapping by client IP. If multiple clients traverse the same NAT, they may all map to one backend. When NGINX sits behind another proxy, configure trusted proxies and real client IPs properly; never blindly trust `X-Forwarded-For` headers that clients can forge.

This is a learning example; adjust TLS, health checking, trusted proxies, and versions/modules before production use. This configuration does not demonstrate cookie-based affinity.

## 12. Example: Migrating an App from Local Sessions to a Shared Store

A legacy web application runs on three VMs. Sessions are kept in each VM's RAM; the load balancer uses 30-minute cookie affinity. When VM A redeploys, users pinned to A lose their temporary shopping carts.

This can be addressed in two phases:

**Phase 1 — reduce risk while still using local sessions**

- Enable affinity and verify cookies are sent across requests.
- Configure proper health checks and connection draining during deployments.
- Never terminate instances before draining finishes.
- Alert on active session counts per backend.
- Explicitly accept that host failures can still lose local sessions.
- Do not store critical business data solely in in-RAM sessions.

**Phase 2 — migrate to a shared session store**

- Provision a session repository using Redis or an HA-capable equivalent store.
- Have the application write sessions to the store and keep only bounded local caches.
- Define TTLs and versioned serialization schemas.
- Enforce TLS, authentication, and network policies for the session store.
- Pilot on a canary group of instances.
- Compare latency, error rate, store hits, connection pools, and cost.
- Once all backends read shared sessions, reduce or disable affinity on a planned schedule.

~~~mermaid
flowchart TD
    A[Current app: local sessions] --> B[Add shared session repository]
    B --> C[Canary: subset of backends]
    C --> D{Session read/write stable?}
    D -- No --> E[Roll back and investigate]
    D -- Yes --> F[Gradually shift traffic]
    F --> G[Test scaling, deploys, and failover]
    G --> H[Reduce or disable sticky affinity]
~~~

Do not disable affinity before every backend can read the same shared session state. During migration, handle legacy sessions still living in RAM; wait out TTLs, perform controlled migration, or require users to re-authenticate per business plan.

## 13. Measuring and Monitoring Session Affinity

Dashboards should reveal whether affinity stabilizes the application or induces load skew.

Metrics to track:

- Request count and percentage routed via affinity.
- Number of sessions or clients pinned to each backend.
- Request rate, CPU, memory, and connection counts per backend.
- Request/connection distribution across backends.
- Count of invalid, expired, or missing affinity cookies (if telemetry is available).
- Frequency of backends marked unhealthy forcing mapping changes.
- Application session lookup misses or session-not-found errors.
- Session store latency, error rate, connection usage, and evictions.
- Drain duration and remaining active connections during scale-in/deployments.
- WebSocket reconnect and session resume success rates.

Never include raw session IDs, user IDs, or cookies in metric labels or logs. Record aggregate states or protected identifiers only when strictly needed for investigation.

### Warning Signs to Watch

- One backend shows much higher request rate or CPU than others: possible load skew.
- New backends receive almost no requests while old ones stay busy: sticky sessions pinning old clients.
- Session misses spike after deployments or scale-in: mappings shifted or local state was lost.
- Latency rises when the session store slows down: the new dependency is affecting requests.
- Connection draining drags out: clients holding connections or sessions too long.
- Many clients sharing one IP pile onto one backend: source-IP affinity affected by NAT/proxies.

## 14. Testing Affinity and Failure Scenarios

Test in staging or a canary group before broad rollout.

| Scenario | How to Test | Expected Outcome to Verify |
|---|---|---|
| Consecutive requests | Send multiple requests with the same cookie | Requests route to the same backend within affinity TTL |
| Missing cookie | Send requests from a fresh client or delete cookie | Load balancer picks a backend via default algorithm |
| Expired cookie | Wait past TTL or send an expired test cookie | Mapping is regenerated and the app handles it cleanly |
| Unhealthy backend | Stop health endpoint or remove backend from pool | Traffic shifts to healthy backends; local sessions behave as designed |
| Scale-out | Add new backends | New sessions can land on new backends; existing load may remain pinned to old ones |
| Scale-in | Drain and remove a backend | Stops taking new sessions; active connections honor drain timeout |
| Rolling deployment | Upgrade backends one by one | Users retain critical data; cookies/sessions remain compatible |
| NAT/proxy | Multiple test clients sharing one source IP | Source-IP affinity may group clients; confirm impact |
| Shared store outage | Simulate slow or disconnected session store | Timeouts, fallbacks, and errors are bounded; no retry storms |
| WebSocket reconnect | Terminate a backend holding long-lived connections | Clients reconnect and restore state per design |

Testing must validate both routing and application state. Seeing the same backend ID alone does not prove sessions are safe; verify session data, authorization, and recovery.

## 15. Diagnosing Session Affinity Incidents

| Symptom | Possible Cause | Investigation Direction |
|---|---|---|
| Users logged out randomly | Cookie not sent, TTL expired, backend changed, or local session lost | Cookie attributes, load balancer mappings, deploy/restart events, session lookups |
| Single backend overloaded | Sticky sessions holding heavy client group or source IP grouping many users | Request rate, session count, source IP distribution, CPU, and connections |
| Scale-out leaves load uneven | Existing sessions stay pinned to old backends | Affinity TTL, session duration, backend selection, and shared state |
| Deployments lose shopping carts | Sessions stored only in RAM of replaced instances | Local session store, draining, session migration, and persistent/shared storage |
| Clients lose sessions on network switch | Source-IP affinity changed or cookies missing | Client IP, cookies, proxy/NAT, and application session IDs |
| Unhealthy backend still called | Health checks or deregistration misconfigured | Probe paths, thresholds, backend status, and connection draining |
| Session store causes latency | Pool exhausted, slow network, evictions, or overloaded store | Store p95/p99, connection pools, memory, CPU, and network |
| Cookie affinity seems ineffective | Domain/path/SameSite, TLS termination, or proxy rewrites | Browser devtools, response headers, request headers, and LB logs |

Start investigations with a sample request carrying trace/correlation ID, backend ID, and session lookup status. Never paste raw cookies or session IDs into tickets; use hashes or protected identifiers per policy if correlation is needed.

## 16. Common Mistakes

**Assuming sticky sessions guarantee zero session loss.** Affinity only controls routing; restarts, failovers, or backend terminations can still lose local sessions.

**Using source-IP affinity for websites with many users behind NAT.** Many users can pile onto a single backend. Cookie affinity or a shared session store is usually better.

**Using affinity cookies as proof of login.** Routing cookies do not authenticate users. Applications must still validate sessions/tokens and authorization.

**Setting affinity TTLs too long.** Old backends hold clients too long, making scale-out and load balancing less effective.

**Disabling affinity while sessions are still local.** Requests hitting another backend will fail to find the session. Reduce affinity only after state is shared or the app is stateless.

**Not draining backends during scale-in.** Long-lived connections and active sessions get cut off abruptly. Use appropriate deregistration delays and graceful shutdown.

**Adding a shared store without bounding connections.** Many backends can trigger a connection storm and overwhelm the store. Design pools, timeouts, caching, and capacity.

**Storing sensitive data in unprotected cookies or sessions.** Sessions are high-value targets. Use HTTPS, secure cookie attributes, encryption where needed, TTLs, and least privilege.

## 17. Checklist for Selecting and Operating Session Affinity

### State Design

- [ ] Identified whether session state lives in RAM, disk, shared store, or client-side tokens.
- [ ] Critical business data does not exist solely in local sessions.
- [ ] Assessed session loss impact across restarts, host failures, or rescheduling.
- [ ] Configured idle timeouts, absolute timeouts, and logout/revocation flows.

### Affinity Design

- [ ] Selected cookie, source-IP, or consistent hashing based on protocol and client traits.
- [ ] Evaluated effects of NAT, proxies, and client network switches.
- [ ] Affinity TTL aligns with session lifetime and backend lifecycle.
- [ ] Health checks can eject unhealthy backends despite existing affinity mappings.
- [ ] Defined behavior when cookies are missing, expired, or backends are removed.

### Scaling and HA

- [ ] Per-backend load distribution metrics are available.
- [ ] Scale-out tested with both existing and new sessions.
- [ ] Scale-in uses connection draining and graceful shutdown.
- [ ] Backend failures do not lose critical business data.
- [ ] Shared session store (if used) has HA, timeouts, capacity, encryption, and monitoring.
- [ ] WebSocket/gRPC/long-lived connections have reconnect and resume plans.

### Security and Observability

- [ ] Session cookies use Secure and HttpOnly; SameSite matches app flows.
- [ ] Session IDs never appear in URLs, logs, or metric labels.
- [ ] Affinity cookies are never used instead of authentication/authorization.
- [ ] Metrics cover session misses, affinity distribution, backend health, and store latency.
- [ ] Tested unhealthy backends, deployments, scaling, and store outages.
- [ ] Runbooks and owners exist for session/affinity issues.

## 18. Self-Check

1. How does session state differ from a session ID? Why does a load balancer need an affinity key?
2. How do cookie-based affinity and source-IP affinity differ when many users connect through the same NAT?
3. Why do sticky sessions fail to guarantee users keep their state after a backend restarts?
4. When autoscaling is enabled, how can affinity cause new backends to receive little load?
5. Distinguish an application session cookie from a load balancer affinity cookie.
6. When should session state be migrated to Redis or a shared store?
7. Why can't an affinity cookie replace authentication and authorization?
8. Which timeouts must be coordinated when draining a backend with WebSockets or long-lived TCP connections?
9. Which metrics help detect load skew and session loss?
10. Propose a migration plan to move an application from local sessions to a shared session store without unintended state loss.

Session affinity is a useful compatibility tool when applications still keep local state, but it creates coupling between clients and backends. By understanding where sessions live, the limits of each affinity method, cookie lifecycles, health checks, and connection draining, teams can choose the right design. For workloads requiring autoscaling, rolling deployments, and flexible failover, a shared session store or stateless design generally reduces dependence on specific instances; whichever approach is chosen, session data must still be protected, monitored, and tested as a critical application component.
