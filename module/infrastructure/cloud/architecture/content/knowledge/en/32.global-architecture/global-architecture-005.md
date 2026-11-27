# Managing Sessions, Identity, and User Experience Across Regional Transitions

> **Chapter:** Global Architecture  
> **Scope:** Cloud application architecture design from business requirements to networking, compute, data, and deployment models. This lesson focuses on session management, identity verification, and maintaining continuous user experience when traffic shifts across regions; it also evaluates routing, data residency, consistency, security, availability, latency, cost, and operations through a Well-Architected lens.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish global traffic steering, regional failover, session affinity, and session continuity.
2. Choose between stateless sessions, centralized stores, regional stores, or replicated sessions based on UX and consistency requirements.
3. Design authentication, token validation, refresh, revocation, and workload identity when requests are served by another region.
4. Analyze how DNS/Anycast/Global Load Balancers, health checks, geo-routing, latency routing, and failover affect sessions.
5. Determine which data may cross borders, which must stay regional, and how to handle residency.
6. Design failover/failback, conflict resolution, caching, idempotency, and degraded-mode UX without introducing security or transaction bugs.
7. Test user journeys under region switches, region loss, identity provider outages, or replication lag.

## 1. Why Can Regional Transitions Break Sessions?

A global application may serve users from multiple regions to lower latency, increase resilience, or satisfy data residency rules. A global traffic manager can shift requests from Region A to Region B when A suffers an outage, or route users to the closest region.

However, a user's session is more than a browser cookie. State can live in:
- An application instance's memory.
- A shared session store.
- Regional databases.
- Distributed caches.
- An identity provider or token service.
- Client-side tokens and refresh tokens.
- Shopping carts, workflow state, or transaction state.
- Device/session registries, risk context, and revocation lists.

If the first request is served in Region A and the next moves to B, Region B must have enough information to verify identity and continue the journey legitimately. If state exists only in memory or a local database in A, the user may be logged out, lose their cart, create duplicate sessions, or see stale data.

**Session continuity** is the ability to preserve valid state and access permissions across instance, zone, or region transitions within policy bounds. The goal is not to preserve sessions at all costs. When a token is revoked, a device poses risk, or a transaction state is uncertain, the system must require re-authentication or place state safely into `pending`.

### 1.1. Distinguishing Key Concepts

| Concept | Meaning | Core Question |
| --- | --- | --- |
| Global traffic steering | Choosing the region/endpoint to serve a request | Which region does the user reach? |
| Session affinity/stickiness | Keeping a user or connection pinned to a backend/region | Does it need to stay in the same place temporarily? |
| Session continuity | Preserving state and access across backend/region changes | Can the new request validly continue the session? |
| Identity federation | Trusting identities issued by an IdP or issuer | How does another region verify the token? |
| Regional failover | Shifting traffic away from a failing region | Which state is ready at the target region? |
| Failback | Returning operations to the preferred region | Are data and sessions safely synchronized? |

Traffic routing can succeed in seconds while session continuity still fails if session stores, keys, token-signing configs, or user data are not ready.

## 2. Defining User Journeys and Global Requirements

Start from the user journey, not from DNS. Each user type and transaction has distinct requirements.

Example booking platform flow:
1. User opens the site and loads the catalog.
2. Logs in via an identity provider.
3. Searches services and builds a cart.
4. Reserves a slot and initiates payment.
5. Receives the booking outcome.
6. Reopens the app from another region or after the serving region fails.

Questions to answer:
- Can a user move between countries/regions within the same session?
- Which region is the account or tenant's home region?
- Does session data contain PII, payment context, or residency-restricted data?
- How long may a session live? When is step-up authentication required?
- Can an in-flight transaction continue in another region, or must it be queried/reconciled?
- If the identity provider becomes unavailable, how are active sessions handled?
- Must users see exact state immediately, or can notifications arrive asynchronously?

### 2.1. Classifying State by Cross-Region Portability

| State | Examples | Behavior on Region Transition |
| --- | --- | --- |
| Public/read-only | Catalogs, public content | Can be widely cached/replicated per policy |
| Identity proof | Access tokens, session IDs | Verify signature, issuer, audience, expiry, and policy |
| User preferences | Language, theme | Can be replicated/cached if permitted |
| Ephemeral session | CSRF nonces, short-lived workflow state | Needs TTL, secure replication, or re-creation |
| Shopping cart | Items, quantities, promotions | Needs versioning, consistency, and conflict handling |
| Transaction state | Bookings/payments/reservations | Follow source of truth; never infer from cache |
| Sensitive/regional data | PII, financial, regulated data | Moves only under residency and transfer policies |
| Risk/revocation state | Device risk, revoked sessions/tokens | Requires fast propagation and fail-safe policies |

Not all state should be replicated. Some state can be reconstructed from durable records; some should remain strictly in the home region; and some can be dropped without harming correctness.

## 3. Global Traffic Steering and Regional Routing

### 3.1. Common Routing Mechanisms

| Mechanism | How It Works | Best Fit | Known Limitations |
| --- | --- | --- | --- |
| DNS geolocation routing | Returns endpoints based on estimated resolver/client location | Country/region-level routing | DNS caches and resolver locations do not always reflect true user location |
| DNS latency-based routing | Picks the endpoint with lower measured latency | Optimizing access speed | Health checks, DNS TTLs, and measurements can lag |
| Anycast | Multiple locations advertise the same IP; network steers traffic to an optimal point | Edge, DDoS protection, global ingress | Does not automatically synchronize session state |
| Global HTTP load balancer | Routes by host/path, health, region, and policy | HTTP(S), health-aware failover | Requires bounded timeouts, health checks, and policies |
| Geo/tenant home-region routing | Selects region by account, tenant, or data residency | Data anchored to a home region | Distant users may incur higher latency |
| Client-side region selection | Client receives endpoint list and picks per policy | Certain native/mobile apps | DNS caches, app versions, and client logic are hard to keep uniform |

You can combine a global edge load balancer with internal regional ingress. DNS failover is simple to deploy, yet not always fast enough due to TTLs and caches; global load balancers steer requests better, but still require accurate health signals and state readiness.

### 3.2. Routing Policies Beyond Geography

A routing decision can evaluate:
- Region health and capacity.
- User latency and network quality.
- Tenant home region/data residency.
- Feature availability in the region.
- Version compatibility.
- Maintenance windows.
- Regions recovering from an incident.
- Security/risk policies.

If an account belongs to a tenant whose data may only be processed in one geography, never automatically route that data to another region merely because latency is lower.

### 3.3. Global Ingress Architecture Example

~~~mermaid
flowchart TB
    U["Global users"] --> G["Global DNS / Anycast / HTTP load balancer"]
    G --> R1["Regional ingress A"]
    G --> R2["Regional ingress B"]
    G --> R3["Regional ingress C"]
    subgraph A["Region A"]
      R1 --> AAPI["Application/API"]
      AAPI --> ADB[("Regional data A")]
    end
    subgraph B["Region B"]
      R2 --> BAPI["Application/API"]
      BAPI --> BDB[("Regional data B")]
    end
    subgraph C["Region C"]
      R3 --> CAPI["Application/API"]
      CAPI --> CDB[("Regional data C")]
    end
    IDP["Federated identity provider"] --> AAPI
    IDP --> BAPI
    IDP --> CAPI
~~~

This diagram is conceptual. Depending on the data ownership model, regions may run active-active for stateless APIs while using home-region data access; do not assume every region holds an independent writable database.

## 4. Designing the Session Model

### 4.1. Stateless Sessions with Tokens

With self-contained tokens (such as signed access tokens), services can verify tokens using public keys/JWKS without querying a session store on every request.

Typical claims include:
- Subject/user ID.
- Issuer (`iss`).
- Audience (`aud`).
- Expiry (`exp`) and issued-at (`iat`).
- Necessary scopes/roles/claims.
- Token ID (`jti`) if used for revocation/deduplication.
- Tenant or context verified by the issuer.

Advantages:
- Easy to serve requests across multiple regions.
- Reduces reliance on a central session database.
- Can verify locally if keys and issuer metadata are safely cached.
- Fits stateless APIs and service-to-service calls.

Trade-offs:
- Stolen tokens remain usable until expiry unless a revocation mechanism exists.
- Claims can go stale when roles or tenant memberships change.
- Large tokens inflate header and network overhead.
- Signing key rotation and JWKS caching must stay synchronized.
- Avoid stuffing entire user profiles, permissions, and business state into tokens.

### 4.2. Stateful Session Store

A random session ID is stored server-side; the cookie holds only the opaque secret ID. Servers look up the session to check user, expiry, state, and revocation.

Advantages:
- Centralized revocation and session updates.
- Can hold workflow state and device context.
- Smaller client-side tokens/cookies.
- Easy to force global logout across all sessions when required.

Trade-offs:
- The session store becomes a runtime dependency.
- Cross-region reads/writes incur latency and replication complexity.
- Store outages can impact login or every request.
- Requires designing partitioning, replication, expiry, failover, and backups.

### 4.3. Hybrid Sessions

A common pattern combines short-lived access tokens with server-side refresh/session records:
- Short-lived access tokens are verified locally at regional APIs.
- Refresh tokens are protected and bound to a server-side session record.
- Refresh/rotation checks session status, device posture, and revocation.
- On region transitions, APIs can keep verifying access tokens; refreshes route to the home region or a highly available session service.

Hybrid models avoid state lookups on every request while preserving control points for refresh and revocation.

### 4.4. Model Comparison

| Criterion | Stateless Token | Centralized Stateful | Hybrid / Regional State |
| --- | --- | --- | --- |
| Cross-region requests | Usually simple if keys/claims are valid | Depends on session store reachability | Depends on access token and refresh policy |
| Rapid revocation | Requires denylist/introspection/short TTL | Can update store directly | Controls refresh and short token TTL |
| Latency | Local verification | May add a network hop | Low for access, stateful for refresh |
| Consistency | Claims may stay stale until expiry | Requires replication consistency | Defined per state category |
| Availability dependency | Issuer/key metadata and clocks | Session store | Both local verification and regional state |
| Operational complexity | Key lifecycle/JWKS/revocation | Store replication/failover | Combines both sets of controls |

No single model fits all applications. Choose based on revocation requirements, session lifetime, stored data, region count, RTO/RPO, and latency targets.

## 5. Cookies, Session IDs, and Browser Protections

For web sessions:
- Mark cookies `Secure` so they are sent only over HTTPS.
- Mark cookies `HttpOnly` to restrict JavaScript access.
- Set `SameSite` appropriately for cross-site flows and CSRF protection.
- Scope `Domain` and `Path` as narrowly as possible.
- Ensure session IDs have high entropy and contain no PII or business data.
- Rotate session IDs after login, privilege elevation, or identity changes.
- Enforce idle timeouts and absolute lifetimes.
- Revoke sessions on logout, password reset, or security incidents per policy.
- Never store long-lived refresh tokens where scripts can easily read them.
- Protect against CSRF whenever browsers attach cookies automatically.

Wide cookie domains shared across subdomains expand the blast radius. Using the same cookie across every region and app without analyzing trust boundaries can let a weak subdomain compromise the primary session.

### 5.1. Session Fixation and Token Theft

- **Session fixation:** an attacker forces a victim to use a known session ID; rotate IDs upon authentication.
- **Token theft:** tokens are stolen from browsers, logs, malware, or networks; use TLS, `HttpOnly` cookies where suitable, short TTLs, narrow audiences/scopes, and revocation.
- **Replay:** stolen tokens/cookies are reused; apply token binding/sender-constrained tokens where supported, device/risk controls, and rotation.
- **CSRF:** browsers send credentials automatically on cross-site requests; apply `SameSite`, CSRF tokens, and origin validation.

Switching regions must never weaken cookie, CSRF, or token-validation controls.

## 6. Identity Federation and Multi-Region Token Verification

### 6.1. Issuer and Audience

Regions may share an identity provider or federation trust. Regional APIs must verify:
- Permitted issuer.
- Valid signature against the matching key.
- Audience matching the target service/resource.
- Valid `exp` and `nbf` timestamps.
- Policy-approved signing algorithm.
- Appropriate scope, role, and tenant claims.
- Clock skew within configured bounds.
- Non-revoked status where the flow requires revocation checks.

Do not check merely whether a token "decodes." JWT payloads can be decoded without verifying the signature; never trust claims before full verification completes.

### 6.2. JWKS and Signing Key Rotation

When using public-key token signing:
1. The issuer publishes public keys via JWKS.
2. Regional APIs cache JWKS per TTL and resolve by key ID (`kid`).
3. During rotation, the issuer publishes the new key before signing with it.
4. APIs fetch the new key according to refresh policy.
5. Old keys remain published long enough to verify still-valid tokens.
6. Compromised keys require an emergency procedure to revoke keys, purge caches, and force re-authentication when necessary.

If Region B lacks the new key due to caching or an egress outage, valid tokens from the issuer may be rejected. Conversely, if a region keeps trusting a compromised key for too long, security degrades. Test both routine rotation and emergency revocation.

### 6.3. Identity Provider Outages

Distinguish between:
- Requests carrying an active, valid access token verifiable locally.
- Requests needing a token refresh.
- Requests requiring login or step-up authentication.
- Authorization decisions requiring recently changed role/membership data.
- Sessions or credentials that have been revoked.
- Workloads needing a fresh token to call downstream dependencies.

Valid existing tokens may continue until expiry for low-risk read flows if policy permits; sensitive operations should fail closed or require re-authentication. Never extend expiries or ignore revocations merely to preserve availability.

## 7. Session Continuity During Region Transitions

### 7.1. Transition Flow

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Global router
    participant A as Region A
    participant B as Region B
    participant I as Identity/JWKS
    participant S as Session service
    C->>G: Request + session cookie/token
    G->>A: Route to Region A
    A->>I: Verify issuer/key (cache or fetch)
    A->>S: Read session/risk state if needed
    A-->>C: Response + session context
    Note over A: Region A unhealthy
    C->>G: Next request
    G->>B: Route to Region B
    B->>I: Verify token and policy
    B->>S: Resolve session in home/regional store
    S-->>B: Session state/version or safe failure
    B-->>C: Continue, re-auth, or appropriate pending state
~~~

In practice, the global router may shift requests even while the client holds existing connections or cookies. Region B must verify the session ID/token, session version, user status, and regional data-access policies.

### 7.2. Session Migration vs. Session Reconstruction

There are two approaches:

- **Migration/replication:** copies state to another region. Useful when sessions must stay intact, though it increases complexity around consistency, encryption, residency, and revocation.
- **Reconstruction:** preserves only the session identifier/identity proof, then reloads durable state from the home-region source of truth or recreates ephemeral state. This reduces replicated data at the cost of higher latency or asking users to repeat minor steps.

You do not necessarily have to replicate the entire session object. You can replicate only essential metadata such as session version, revocation status, and a routing/home-region pointer.

## 8. Regional Session Stores and Data Consistency

### 8.1. Where Should Sessions Live?

| Model | How It Works | Advantages | Risks |
| --- | --- | --- | --- |
| Home-region store | Sessions belong to a tenant/origin home region | Simple authority and residency enforcement | Other regions need cross-region calls |
| Global centralized store | All regions read/write one logical store | Consistent state under one control point | Latency, regional dependency, and blast radius |
| Active-passive replicated store | One region writes, another receives replication | Failover can be simpler than active-active | Replication lag and write fencing |
| Active-active store | Multiple regions accept writes | Serves close to users | Conflicts, consistency, and split-brain |
| Local ephemeral + durable source | Short-lived regional cache/session; authoritative state in durable store | Low latency and less replicated data | Cache invalidation and stale state |

### 8.2. Splitting State by Consistency Requirements

Not every field requires the same consistency level:

| State | Appropriate Consistency | Rationale |
| --- | --- | --- |
| Theme/language preference | Eventual consistency is usually fine | Conflicts rarely harm transactions |
| Catalog cache | Eventual + bounded staleness | Slightly stale data is tolerable within bounds |
| Active session/revocation | Strong or rapid propagation per risk | Prevents revoked sessions from continuing |
| Cart quantity | Versioned updates/optimistic concurrency | Prevents devices from overwriting each other |
| Inventory reservation | Strong transactional control per business rules | Prevents overselling |
| Payment status | Source of truth and reconciliation | Never infer outcomes from cache |
| Device risk/step-up requirement | Policy-defined freshness | Protects sensitive actions |

### 8.3. Conflict Resolution

If a user modifies a cart from two devices or two regions concurrently:
- Use versions/ETags/optimistic concurrency.
- Record actor, device, timestamp, and operation ID.
- Merge independent fields when semantics allow.
- Use last-write-wins only for data where silent overwrites cause no harm.
- For transactions, rely on transactions/sources of truth rather than arbitrary merges.
- Surface conflicts or ask the user to confirm when safe merging is impossible.

Do not rely on timestamps alone if clocks across regions cannot be trusted or two updates land at the same instant. Use monotonically increasing versions, sequences, or causal metadata.

## 9. Data Residency and Privacy During Region Transitions

Global architecture must govern where data is stored, processed, and transmitted. A user logging in from another country does not automatically authorize moving their entire account data to the nearest region.

Classification:
- **Identity data:** subject ID, email, phone, credential metadata.
- **Session metadata:** hashed session ID, expiry, device context, IP/risk signals.
- **Business data:** bookings, payments, profiles, carts.
- **Security telemetry:** login events, audits, fraud/risk signals.
- **Secrets/cryptographic material:** refresh tokens, signing keys, encryption keys.

Architecture questions:
- Are there data residency requirements or cross-border transfer mechanisms?
- Can systems handle opaque tokens or identifiers instead of copying PII?
- Where are logs containing IPs, user IDs, or device fingerprints stored?
- Do backups and DR copies share the same residency constraints?
- Which providers/processors are authorized to access the data?
- Do key management and access logs cross regional boundaries?
- Are retention and deletion synchronized across replicas, caches, and backups?

Home-region routing can be used: tenant identity/data stay in the designated region; traveling users still connect to the global edge, which proxies requests to the home region. This preserves data locality at the cost of cross-region latency and dependency. Legal/Privacy teams must confirm exact regulatory obligations—never infer compliance from technical topology alone.

## 10. User Experience During Region Outages or Transitions

Good session continuity delivers clear, consistent feedback without losing critical data.

### 10.1. Scenarios Users May Encounter

| Scenario | Expected UX |
| --- | --- |
| Background region switch while access token is valid | Request succeeds without forcing re-login |
| Session state missing in the new region | Load from home region or explain re-verification |
| Access token expired while IdP is healthy | Refresh silently or prompt re-login per policy |
| IdP temporarily down while token is still valid | Permit operations within approved bounds |
| Refresh token revoked | Force re-login; never reuse the session |
| Booking/payment outcome unknown | Show `pending`/processing and provide status lookup |
| Cart has conflicting edits | Notify user of changes and allow selection/merge |
| Home region unavailable | Follow DR policy or explain temporary unavailability |
| Residency disallows processing in current region | Route to home region or reject clearly |

### 10.2. Avoiding Mass Logouts During Failover

Common causes of mass logouts:
- Session store exists only in Region A.
- Encryption/signing keys differ across regions.
- Cookie domain/path or secrets differ by region.
- Session versions are not replicated.
- Clock skew causes tokens to look expired or not-yet-valid.
- Regional APIs use mismatched issuer/audience configurations.
- Revocation caches are out of sync.
- Geo-routing sends users to the wrong home region.

Standardizing key management, issuer/audience policies, cookie settings, clock synchronization, and session version semantics minimizes errors. Never distribute private signing keys to every region just to keep sessions alive; prefer public-key verification and purpose-scoped keys.

### 10.3. Error Screens and Messaging

Messages should:
- Never expose internal regions, hostnames, session IDs, or security internals.
- Distinguish re-authentication prompts, in-flight transactions, and transient errors.
- Discourage users from clicking pay repeatedly when the outcome is uncertain.
- Provide retry guidance with backoff where appropriate.
- Surface a correlation/reference ID for support lookup.
- Clarify which data was saved and which action must be retried.

## 11. Controlled Failover and Failback

### 11.1. Failover Is More Than Flipping DNS

A failover procedure includes:
1. Confirming the region is unhealthy via health signals and business SLIs.
2. Classifying the fault: ingress, compute, identity, session store, database, or external dependency.
3. Verifying the target region has required capacity and dependencies.
4. Checking data consistency, replication lag, and write authority.
5. Shifting traffic per policy, potentially in waves.
6. Validating authentication, session lookups, authorization, and business transactions.
7. Monitoring error rates, latency, login success, session continuity, and data correctness.
8. Keeping the old region fenced if needed to avoid split-brain.
9. Notifying operators and recording incident/change evidence.

### 11.2. Active-Active vs. Active-Passive

| Dimension | Active-Passive | Active-Active |
| --- | --- | --- |
| Data writes | Primary region; secondary standby/replica | Multiple regions may accept writes by design |
| Sessions | Replicated or resolved against home region | Needs shared/replicated state or stateless model |
| Failover | Requires promoting/enabling secondary | Traffic shifts, yet data conflicts must still be handled |
| Complexity | Typically lower | Higher across consistency, routing, and operations |
| Cost | Standby capacity and replication | Multiple regions running continuously |
| Use cases | Clear DR and single write ownership | Local serving, high availability, and large scale |

Active-active does not require every state layer to be multi-master. You can run active-active at the edge/stateless API layer while keeping transactional databases active-passive.

### 11.3. Failback

When the original region recovers:
- Do not swing traffic back before checking replication and data divergence.
- Establish write authority and reconcile new data written in the DR region.
- Reconcile session/revocation states and pending workflows.
- Synchronize cache/version and key metadata.
- Send canary/low-percentage traffic first.
- Monitor logins, refreshes, sessions, business transactions, and error rates.
- Ramp traffic only when criteria hold.
- Record failback duration and outcomes.

Botched failback can overwrite recent data or leave sessions stale. Fencing is required to prevent two regions from accepting uncoordinated writes simultaneously.

## 12. Security: Sessions and Identity Must Not Weaken During Failover

Controls to maintain across regions:
- TLS across clients, edge, regional ingress, and internal services.
- Consistent token issuer/audience/signature validation.
- Key rotation, JWKS caching, and emergency revocation.
- Appropriate `Secure`/`HttpOnly`/`SameSite` session cookies.
- Protections against CSRF, replay, fixation, and token theft.
- Session idle timeouts and absolute lifetimes.
- Propagation of user disables, password resets, and session revocations.
- MFA/step-up for sensitive actions.
- Tenant isolation and object-level authorization.
- Workload identities between regional services.
- Audit logs with correlation and region metadata, without logging raw secrets/tokens.
- Global and regional rate limiting and abuse protection.

If a region stops receiving revocation updates, policy must specify which actions may continue and for how long. Payments, admin actions, or data exports may require introspection or fresher state checks, whereas public catalogs may allow unexpired access tokens. Classify risk and UX per action.

## 13. Privacy-Aware Observability

To diagnose session continuity, log enough to trace requests without over-collecting personal data.

Appropriate fields:
- Pseudonymous subject/session references or keyed hashes.
- Session version and token issuer/key ID—never the token itself.
- Source/target region and routing decision.
- Auth decision, outcome class, and policy version.
- Session lookup source, replication version/lag.
- Request/correlation ID, latency, retries, and failover events.
- Device/risk signals only as necessary and within retention policies.

Never log raw cookies, access tokens, refresh tokens, private keys, or full session objects. IPs and device fingerprints can constitute personal data; enforce documented purpose, access control, residency, and retention.

## 14. Testing Session Continuity and Global Experience

### 14.1. Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| User logs in at Region A, next request hits B | Token/session verifies cleanly with no unexpected logout |
| Region A loses ingress | Router shifts traffic; B holds needed state/policies |
| Region A loses session store | B uses home/replicated store per policy or fails safely |
| Token expires during failover | Valid refresh succeeds or user is prompted to re-login |
| Signing key rotation | Both A and B verify new keys; old keys expire cleanly |
| Revocation while a region is partitioned | Sensitive actions follow freshness/fail-closed policy |
| Two devices update cart concurrently | Conflicts are detected/merged per rules |
| Payment times out then switches region | No duplicate charge/booking; status is queryable |
| High replication lag | Writes are withheld if consistency is insufficient |
| Post-DR failback | No lost updates, no split-brain |
| User travels to residency-restricted region | Routes to home region or rejects per policy |
| Clock skew | Token/session expiry stays accurate within tolerance |

### 14.2. Measuring SLIs/SLOs

Measure separately:
- Global routing success and failover convergence.
- Authentication success by region.
- Session continuity rate across regional transitions.
- Failure-driven re-authentication rate (separated from security-driven re-auth).
- Session lookup latency and error rate.
- Token validation/JWKS refresh failures.
- Revocation propagation time.
- Booking/payment correctness after failover.
- Regional latency and UX by geography.
- Residency policy denials/violations.
- Time to recover and data reconciliation duration.

Example session continuity SLI:

\[
SLI_{\text{continuity}} =
\frac{\text{Valid transitions that cleanly continue the session}}
{\text{Total valid transitions attempted}}
\]

Exclude forced re-logins triggered for legitimate security reasons when defining a "continuity failure"; otherwise, the SLI could incentivize accepting revoked sessions.

## 15. Practical Scenario: Three-Region Booking Platform

### 15.1. Context

A booking SaaS serves users across three regions. The system has:
- Global DNS/HTTP load balancing.
- Regional APIs and workers in each region.
- A central OIDC-capable identity provider.
- Short-lived access tokens and refresh session records.
- A booking database with per-tenant home regions.
- Replicated catalog caches.
- External payment and notification providers.

Assumed requirements:
- Users can travel and continue sessions in another region.
- Tenants keep booking data in their home region per policy.
- Catalogs are read close to users.
- Payments must never create duplicate charges during regional failover.
- Revocations and disabled accounts must enforce risk policies.

### 15.2. Proposed Architecture

~~~mermaid
flowchart TB
    USER["User / browser / mobile"] --> GLB["Global traffic manager"]
    GLB --> A["Region A API"]
    GLB --> B["Region B API"]
    GLB --> C["Region C API"]
    IDP["OIDC Identity Provider"] --> A
    IDP --> B
    IDP --> C
    A --> AUTH["Token validation + policy"]
    B --> AUTH
    C --> AUTH
    AUTH --> SESS["Session / revocation service"]
    A --> ROUTE["Tenant home-region resolver"]
    B --> ROUTE
    C --> ROUTE
    ROUTE --> DB[("Home-region booking data")]
    A --> CACHE["Regional catalog cache"]
    B --> CACHE
    C --> CACHE
    A --> PAY["Payment provider"]
    B --> PAY
    C --> PAY
~~~

This flow is illustrative. The session/revocation service can be replicated or home-region routed depending on latency, residency, and failover goals. The diagram does not imply every region writes directly to the same database.

### 15.3. Design Decisions

- Access tokens are short-lived and verified locally using trusted public keys.
- Refresh session records have clear authority, routing to the home region or an approved HA store.
- The tenant's home region governs where booking and payment state are processed.
- Catalog caches are replicated because they tolerate bounded staleness.
- Carts use versions/optimistic concurrency; conflicts are surfaced or merged per rules.
- Payment requests use global idempotency keys and status lookups before retrying.
- Revocations have a propagation SLO; sensitive actions require fresh state checks.
- Failover regions must pass capacity and data-readiness checks before accepting writes.

### 15.4. User Journey When Region A Fails

1. Global router detects A is unhealthy and routes the next request to B.
2. The browser still sends its cookie/access token; B verifies issuer, audience, expiry, and signature.
3. Region B retrieves session/revocation state per policy.
4. Region B resolves the tenant's home region and checks residency.
5. Catalog data is served from Region B's cache if within freshness bounds.
6. If the home-region booking database remains healthy, requests route there over protected private links.
7. If transaction state is uncertain, the UI shows `pending` and queries status by reference—never creating a new transaction.
8. Telemetry logs source/serving region, correlation ID, and outcome without logging tokens or cookies.

## 16. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Flipping DNS and claiming session continuity | Target region lacks sessions/keys/data | Test full journeys and state dependencies |
| Storing sessions in API instance memory | Users log out on backend/region switches | Externalize state or use suitable stateless tokens |
| Replicating all session state indiscriminately | Higher cost and potential residency violations | Classify state by sensitivity and consistency |
| Using overly long-lived JWTs to avoid refreshes | Compromised/revoked tokens remain hard to block | Short TTLs, refresh policies, and revocation |
| Regions drifting on signing keys/issuer configs | Valid tokens rejected or wrong issuers trusted | Standardize issuer/audience and key lifecycles |
| Ignoring revocation during IdP outages | Revoked sessions keep access | Action-based policies, fail-safe defaults, propagation SLOs |
| Shared session store without DR | Every region loses sessions together | HA store, recovery procedures, failure isolation |
| Active-active database without conflict models | Lost updates or split-brain | Home-region ownership, versioning, conflict controls |
| Using last-write-wins for payments/inventory | Corrupted transactions | Sources of truth and transaction semantics |
| Latency-based routing ignoring residency | Data crosses disallowed boundaries | Enforce tenant/data policies before latency optimization |
| Immediate failback when old region recovers | Overwrites new data or creates stale sessions | Reconciliation, fencing, and canary failback |
| Logging raw cookies/tokens for debugging | Credential leakage | Pseudonymous references and redaction |
| Skipping clock-skew and key-rotation tests | Regional token expiry/validation bugs | Automated rotation and clock tests |
| Counting failure-driven re-auth as security success | Poor UX hidden in metrics | Separate security-driven from failure-driven re-auth |
| Non-idempotent payment retries in a new region | Duplicate charges or bookings | Global idempotency keys and reconciliation |

## 17. Practice Exercise

A booking SaaS platform operates Region A for domestic tenants and Region B for international tenants. A global load balancer routes users to the nearest region. Sessions currently live in standalone Redis per region; access tokens expire in 30 minutes; refresh tokens are stored in the browser; some booking/payment calls execute asynchronously. When Region A fails, users shift to B but frequently get logged out, some carts lose updates, and support cannot tell whether payments succeeded.

Complete the following:

1. Map the journeys and dependency graphs for login, refresh, cart, booking, and payment.
2. Classify state into ephemeral, reconstructable, durable, sensitive, and regional.
3. Compare stateless tokens, centralized session stores, home-region sessions, and hybrid models.
4. Design the cookie/session/refresh lifecycle, token issuer/audience, key rotation, and revocation.
5. Define a global routing policy factoring in health, latency, tenant home regions, and data residency.
6. Design session continuity when failing over from A to B; specify what replicates, resolves from home region, or reconstructs.
7. Establish consistency/conflict rules for carts, session revocation, bookings, and payments.
8. Design failover/failback covering fencing, replication lag, idempotency, and reconciliation.
9. Propose UX flows for expired tokens, IdP outages, unknown payment states, and residency restrictions.
10. Build an SLI/SLO set and test matrix for regional transitions, key rotation, revocation, split-brain, and clock skew.
11. Write an ADR detailing trade-offs across latency, availability, security, cost, and operational complexity.

**Self-Evaluation Criteria:** a strong solution does more than keep users logged in. It preserves accurate identity/authorization, prevents lost or duplicated business state, honors residency, handles tokens/revocations safely, and tells users the exact status of their transactions.

## 18. Pre-Release Checklist for Cross-Region Architectures

- [ ] Login, refresh, cart, checkout, and payment journeys are documented.
- [ ] Session state is classified by sensitivity, consistency, TTL, and residency.
- [ ] Global routing policies consider health, capacity, latency, tenant/home region, and compliance.
- [ ] Session model (stateless/stateful/hybrid) includes rationale and failure behavior.
- [ ] Cookies enforce `Secure`/`HttpOnly`/`SameSite`; session IDs rotate and expire.
- [ ] Token issuer, audience, signature, expiry, and scopes are verified in every region.
- [ ] JWKS/key rotation, emergency revocation, and clock skew have been tested.
- [ ] Session refresh, logout, account disable, and revocation propagation have clear SLOs.
- [ ] Home-region routing and cross-region data access comply with residency.
- [ ] Replicated state has versioning/conflict policies; sensitive state is never copied blindly.
- [ ] Bookings and payments implement idempotency, status queries, and reconciliation.
- [ ] Failover covers capacity, data readiness, write fencing, and monitoring.
- [ ] Failback covers reconciliation, canarying, and traffic-ramp gates.
- [ ] Degraded modes are defined for IdP, session store, and home-region outages.
- [ ] UX never encourages retrying side effects when transaction state is unknown.
- [ ] Logs/metrics exclude raw tokens, cookies, and secrets; privacy and retention are approved.
- [ ] SLIs/SLOs track session continuity and business correctness per region.
- [ ] Test matrix covers transitions, region loss, revocation, key rotation, lag, and split-brain.
- [ ] Runbooks, owners, escalation paths, and DR drills are up to date.
- [ ] An ADR documents trade-offs and re-evaluation triggers.

## Key Takeaways

A global architecture must coordinate **routing, sessions, identity, and data ownership**. A global load balancer can steer requests to a healthy region, yet that region can only continue the session cleanly if it verifies tokens, session/revocation state, permissions, and required data.

Classify state before replicating; prefer short-lived tokens and locally verifiable identities; anchor transaction state to a source of truth or home region; apply consistency/versioning and idempotency to business data; and design residency, failover, and failback from the start. A great cross-region experience is seamless yet accurate and secure—clearly explaining when re-authentication is required or when a transaction is still pending.
