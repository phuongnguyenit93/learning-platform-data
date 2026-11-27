# Service Authentication, Authorization, and Protecting Public APIs

## 1. Why do public APIs require multiple layers of protection?

A public API is the interface web apps, mobile apps, partners, or external systems use to interact with cloud services. A request reaching an API Gateway with a valid token still does not prove the caller is allowed to read or modify the data requested. An API can authenticate a user properly yet still expose another user's profile; it can rate-limit at the gateway yet still be abused across multiple accounts; or it can use HTTPS while leaking secrets into logs.

Secure design must distinguish three questions:

- **Authentication:** who or which workload is calling?
- **Authorization:** which actions is the caller permitted to perform on which resources, and under what context?
- **API protection:** how do we reduce abuse, vulnerability exploitation, overload, data leakage, and blast radius?

OAuth 2.0, OpenID Connect (OIDC), workload identity, mutual TLS (mTLS), API Gateways, Web Application Firewalls (WAFs), rate limiting, schema validation, and audit logs solve different parts of this problem. They must work together with application-level permission checks and data boundaries.

In the **CLOUD_ARCHITECTURE** module, these decisions directly affect security, reliability, scalability, cost, and operations. Good API architecture clearly defines identity, permissions, transport security, load limits, and how anomalous behavior is detected and handled.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish user authentication, service authentication, and authorization for third-party applications.
2. Choose appropriate OAuth 2.0/OIDC flows for public clients and machine-to-machine workloads.
3. Design authorization by scope, role, attribute, tenant, and per-object ownership.
4. Validate tokens properly for issuer, audience, signature, expiration, and usage context.
5. Combine API Gateways, WAFs, rate limits, validation, TLS, secrets, and auditing to protect public APIs.
6. Recognize common vulnerabilities such as BOLA/IDOR, BFLA, token leakage, SSRF, mass assignment, and credential abuse.
7. Build checklists and verification procedures before releasing an API.

## 2. Trust boundary model for an API

A request traverses multiple components; each component should only be responsible for its appropriate control layer.

~~~mermaid
flowchart LR
    Client["Web / Mobile / Partner"] --> Edge["DNS / TLS Edge"]
    Edge --> WAF["WAF / DDoS Protection"]
    WAF --> Gateway["API Gateway"]
    Gateway --> Identity["Identity Provider / Token validation"]
    Gateway --> API["Application API"]
    API --> AuthZ["Resource / tenant authorization"]
    AuthZ --> Data[("Private data store")]
    API --> Audit["Security audit + telemetry"]
    Gateway --> Logs["Gateway access logs"]
~~~

*Logical diagram. Token validation may happen at the gateway, at the service, or both depending on deployment model. Even when the gateway validates the token, the application must still enforce business and resource-level authorization.*

| Layer | Question to resolve | Example controls |
|---|---|---|
| Edge / network | Did the request enter through a managed ingress point? | TLS, DDoS protection, ingress policies |
| WAF / gateway | Does the request comply with API policies and quotas? | WAF rules, authentication integration, rate limits, request size limits |
| Authentication | Which user, client, or workload is the caller? | OIDC, OAuth access tokens, mTLS, workload identity |
| Authorization | Is the caller allowed to perform this action on this resource? | Scopes, RBAC, ABAC, tenant/ownership checks |
| Business logic | Do business state and rules permit the action? | Reservation status, payment state, concurrency checks |
| Data | Under what privileges are data and secrets accessed? | DB identities, least privilege, encryption, auditing |
| Observability | Can anomalous behavior be detected, traced, and handled? | Security logs, traces, alerts, incident runbooks |

**No single layer replaces all the others.** A private network does not prove a caller is authorized; a WAF does not know whether a user owns a reservation; a valid token does not make every parameter in the request trustworthy.

## 3. Distinguishing user authentication and service authentication

### 3.1. Interactive users: identity authentication

When a human logs into an application, the system typically verifies identity through an Identity Provider (IdP). **OpenID Connect (OIDC)** adds an identity layer on top of OAuth 2.0 and typically issues an ID Token so the client knows which issuer authenticated the user and under what subject.

Concepts to distinguish:

- **ID Token:** OIDC login session assertion intended for the client to identify the user. Never use an ID Token in place of an access token to call APIs.
- **Access Token:** credential representing granted authority to access a resource/API within assigned scopes. APIs receive access tokens and validate them per the issuer's contract.
- **Refresh Token:** credential used to obtain new access tokens per issuer/client policy; protect like a secret, restrict storage, and support rotation/revocation where possible.
- **Session cookie:** may be used by web apps to maintain sessions; requires appropriate Secure, HttpOnly, SameSite attributes and CSRF protection if sent automatically with requests.

For public web/mobile apps, a common approach is **Authorization Code Flow with PKCE**. The user is redirected to the IdP to sign in and consent; the client receives an authorization code and exchanges it using PKCE. PKCE reduces the risk of code interception and token exchange in public client flows.

Do not use Implicit Flow or Resource Owner Password Credentials Grant in new designs. Clients that cannot keep secrets like a trusted server must never embed static client secrets in mobile apps, desktop apps, or browser JavaScript.

### 3.2. Service-to-service: workload authentication

For example, Booking API calling Payment API, or a function pushing messages to a queue. There is no interactive user on every request; the caller is a **workload identity**.

Common approaches:

- **Workload identity / managed identity:** the runtime receives a platform-issued identity and uses short-lived tokens to access cloud services without embedding static access keys.
- **OAuth 2.0 Client Credentials Grant:** a confidential service client obtains an access token from an authorization server to call an API with granted scopes/audiences.
- **mTLS:** client and server mutually verify certificates during TLS handshakes, using workload certificates or service mesh identities.
- **Signed requests / provider-specific identity:** some services use request signing or provider-native identity mechanisms.

Choose mechanisms with clear credential lifecycles, rotation, revocation, and auditing. If a function only needs to write to one queue, grant publish permission strictly to that queue—never broad cloud account admin rights.

### 3.3. Comparing credential types

| Credential | Purpose | Key limitations |
|---|---|---|
| ID Token | Login identity assertion for OIDC clients | Never use instead of an access token to call APIs |
| OAuth Access Token | Carries authorization to access APIs/resources | APIs must verify issuer, audience, expiry, and permissions per contract |
| Refresh Token | Obtain fresh tokens | High value; requires protection, rotation/revocation |
| API Key | Identifies a project/client or enforces basic quotas depending on system | Does not prove user identity; usually insufficient for authorization |
| Client Secret | Authenticates a confidential client to an IdP | Store as secret, rotate, never embed in public clients |
| mTLS Certificate | Authenticates endpoints/workloads at TLS layer | Requires CA management, issuance, expiration, rotation, and identity mapping |
| Cloud Access Key | Credential for cloud APIs | Avoid long-lived keys when workload identity/short-lived credentials exist |

**An API key is not universal access control.** If an API uses keys to identify clients, proper authentication and user/resource authorization are still required. Compromised keys should be revocable/rotatable with usage tracking.

## 4. OAuth 2.0 and OIDC: choosing the right flow

OAuth 2.0 is an authorization framework; OIDC adds user authentication. In API design, identify who the client is, which API is the resource server, which authorization server issues tokens, and which permissions are granted.

| Scenario | Typically suitable flow/model | Notes |
|---|---|---|
| Web or mobile app with human users | Authorization Code + PKCE | Public clients cannot keep client secrets; redirect URIs must match exactly |
| Backend server calling API on its own behalf | Client Credentials | Scope/audience grants only permissions the workload needs |
| App calling API on a user's behalf | Authorization Code + PKCE with delegated scopes | API must distinguish user context from service identity |
| Same-cloud service calling managed service | Workload/managed identity | Prefer short-lived tokens and resource-scoped roles |
| Service-to-service requiring mutual transport auth | mTLS combined with identity/authorization | Certificates alone do not fully express business permissions |

### 4.1. Authorization Code + PKCE

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Web/Mobile Client
    participant I as Identity Provider
    participant A as API
    U->>C: Initiate login
    C->>I: Authorization request + PKCE challenge
    I->>U: Authenticate and consent if needed
    I-->>C: Authorization code via redirect URI
    C->>I: Exchange code + PKCE verifier
    I-->>C: ID token + access token as requested
    C->>A: API request + access token
    A->>A: Validate token and authorize resource
~~~

PKCE uses a random code verifier and a code challenge sent during authorization. When exchanging the code, the client sends the verifier for the IdP to validate. Real implementations also use state to bind requests/responses against login CSRF, plus nonce when OIDC clients bind ID Tokens to auth requests.

### 4.2. Client Credentials for machine-to-machine

A confidential service client authenticates with the authorization server and fetches an access token for permitted scopes/APIs:

~~~text
Payment reconciliation worker
    -> Authorization Server: client authentication + requested scope
    <- Access token (audience = payment-api)
    -> Payment API: Authorization: Bearer <access-token>
    <- Response per granted permissions
~~~

Client secrets, private keys, or certificates must reside in a secret manager/KMS or equivalent secure store—never committed to repositories. Prefer workload identity/federation where supported by the platform to minimize static credentials.

### 4.3. Audience and scopes

- **Audience (aud):** which resource/API the token was issued for. An API should reject tokens issued for another API.
- **Scope:** granted permission as interpreted by the authorization server/resource server, such as reservation:read.
- **Role:** permission grouping inside the system, such as support-agent or booking-admin; roles do not replace per-resource checks.
- **Client identity:** identifies the calling application/workload, distinct from user identity in delegated scenarios.

A token carrying reservation:read still does not mean the user can read every reservation. The API must verify access against the specific record and tenant.

## 5. Validating access tokens properly

### 5.1. When using JWT access tokens

JWTs typically consist of header, payload, and signature. Payloads are Base64URL-encoded, **not encrypted confidentially by default**. Never place passwords, secrets, or sensitive data into claims merely because the token is signed.

At minimum, resource servers must validate according to the issuer contract:

1. **Signature:** valid signature using a trusted key from issuer/JWKS, with algorithms restricted to a configured allowlist.
2. **Issuer (iss):** matches the trusted authorization server.
3. **Audience (aud):** contains the receiving API/resource identifier.
4. **Expiration (exp):** token is not expired; check nbf when used and allow only bounded clock skew.
5. **Token type/profile:** confirm this is an access token of the right profile, not mistakenly accepting an ID Token.
6. **Authorization claims:** scopes/roles/tenant/subject used according to API definitions and policies.
7. **Revocation/rotation model:** understand token lifetimes and handling when users/sessions/credentials are revoked.

Never trust the self-declared alg header without enforcing an allowlist. During signing key rotation, resource servers must refresh JWKS/key caches cleanly and handle unknown kid values properly. Simply decoding a JWT to read claims **is not token validation**.

### 5.2. When using opaque access tokens

Opaque tokens do not carry JWT claims for local API validation. Resource servers can use **token introspection** or an issuer lookup mechanism to verify whether the token is active, its client/subject, audience, and scopes. The trade-off is added network dependency, latency, and securing/caching introspection results appropriately.

### 5.3. Tokens can leak: minimizing blast radius

- Keep access tokens short-lived per issuer capabilities with minimal scopes/audiences.
- Never put tokens in URL query strings, analytics, error pages, or logs.
- For browser apps, prefer BFF/server-side sessions where fitting; avoid storing long-lived tokens where untrusted JavaScript can read them.
- On mobile, use platform secure storage; protect redirect URIs and deep links.
- Rotate/revoke compromised credentials; maintain incident procedures and audits.
- Avoid forwarding user tokens to downstream services that do not need those privileges. Use appropriate token exchange/delegation or dedicated service identities.

## 6. Authorization: scopes, roles, attributes, and resource permissions

**Authentication answers who is calling. Authorization answers whether this specific request is allowed.** Authorization checks must run on every meaningful data access or state change.

### 6.1. RBAC: role-based access control

Role-Based Access Control assigns permissions by role. Example:

| Role | Typical capabilities | Restrictions |
|---|---|---|
| guest | View public listings, manage own bookings | Cannot view others' personal data |
| host | Manage own listings and related bookings | Cannot access other hosts' listings |
| support-agent | View selected info needed for support | Sensitive data requires justification, auditing, and masking |
| finance-operator | Reconcile transactions within assigned scope | Cannot alter user identity info or admin roles |
| platform-admin | Administer platform per responsibilities | Privileged access is controlled, time-bound, and audited |

Roles help organize permissions; never let a role bypass all resource-level checks.

### 6.2. Scopes: client/API permissions

OAuth scopes express permissions granted to a client against an API, such as reservation:read, reservation:create, reservation:cancel, payment:status:read. Scopes should have clear meaning and stay bounded per resource server. Broad scopes like admin:* demand strict scrutiny and control. Scopes alone rarely suffice to determine ownership of a specific booking.

### 6.3. ABAC: attribute- and context-based access control

Attribute-Based Access Control evaluates attributes of the subject, resource, action, and environment/context. Example:

~~~text
subject.tenantId == reservation.tenantId
subject.userId == reservation.guestId
action == "cancel" && reservation.status == "PENDING"
request.time < reservation.cancellationDeadline
~~~

ABAC fits rules considering owners, tenants, data classification, state, and time. Policies must be transparent, tested, and not scattered inconsistently across endpoints.

### 6.4. Combining multiple authorization layers

A valid authorization decision may require:

1. Valid token with the right API audience.
2. Client holds scope reservation:read.
3. User holds an appropriate role.
4. Reservation belongs to the authorized user/tenant.
5. Business state allows the operation.
6. Request violates no special policy such as legal hold or locked account.

Do not simply check for an admin role at request entry and skip all other boundaries. Privileged roles also need scoping, auditing, and approval workflows.

## 7. Per-object protection: BOLA/IDOR and BFLA

An API can validate tokens and scopes properly and still suffer from **Broken Object Level Authorization (BOLA)**, commonly grouped with IDOR. This occurs when a caller swaps an ID in the URL/body and reads or mutates an object they do not own or have access to.

### Vulnerable example

~~~http
GET /v1/reservations/rs-1002
Authorization: Bearer <valid-access-token>
~~~

The server looks up the reservation by ID and returns its contents without checking whether the guest/host/tenant may view that record. An attacker changes it to rs-1003 and accesses someone else's data.

### Safer design

~~~java
public ReservationView getReservation(
        String reservationId,
        CurrentPrincipal principal) {

    Reservation reservation = repository.findById(reservationId)
        .orElseThrow(NotFoundException::new);

    boolean isGuest = reservation.guestId().equals(principal.userId());
    boolean isAuthorizedHost =
        hostAccessPolicy.canRead(principal, reservation.propertyId());
    boolean isSupportAccess =
        supportPolicy.canReadWithCase(principal, reservation.id());

    if (!(isGuest || isAuthorizedHost || isSupportAccess)) {
        throw new NotFoundException();
    }
    return ReservationView.from(reservation);
}
~~~

This is illustrative Java pseudocode; real policies must consider tenants, roles, states, and auditing. Returning 404 instead of 403 can reduce resource-existence enumeration in some APIs, provided it stays consistent with contracts and internal logging. Never accept a client-submitted ownerId as proof of ownership.

**Broken Function Level Authorization (BFLA)** happens when lower-privileged users can invoke endpoints/functions meant only for higher roles, such as POST /admin/refunds. Hiding UI buttons is not authorization; the API must enforce server-side checks per function/action.

| Principal | Resource | Action | Expected outcome |
|---|---|---|---|
| Guest A | A's Reservation | Read | Allow |
| Guest A | B's Reservation | Read | Deny |
| Host A | A's Listing | Update | Allow within policy |
| Host A | B's Listing | Update | Deny |
| Support without case | Sensitive profile | Read | Deny |
| Support with case and proper role | Records within case scope | Read | Allow + audit |
| Guest | Admin refund endpoint | Execute | Deny |

## 8. API Gateways, WAFs, and network-layer protection

### 8.1. API Gateways as shared policy enforcement points

Gateways commonly handle routing, TLS integration, auth integration, quotas, rate limiting, request size caps, basic schema validation, access logs, metrics, correlation IDs, and custom domains. They do not replace resource authorization or business validation. A gateway knows which scopes a token holds, but usually only the application knows which tenant owns a reservation and whether cancellation rules allow cancelling it.

### 8.2. WAF and DDoS protection

A WAF inspects web/API traffic at the application layer using rules that detect/block patterns like injections, anomalous payloads, bots, or rate-based patterns depending on the product. DDoS protection mitigates volumetric/protocol attacks at the edge/network.

WAFs can produce false positives or miss novel payloads; they do not fix SQL injection bugs in code, broken authorization, or abusable business logic. Managed rules require monitoring, controlled tuning, and false-positive review. Rate-based WAF rules do not replace per-user/tenant quotas. Backends should only accept traffic via the intended ingress path so WAFs cannot be bypassed.

### 8.3. Network access and private services

Public APIs can sit behind public edges while backends, databases, queues, and internal APIs reside on private networks. Restrict service-to-service access by source/destination, identity, and actual ports; private IPs do not automatically make connections trustworthy.

When using mTLS/service meshes, manage CAs, certificate issuance/rotation, peer identities, and policies. mTLS proves transport-layer identity under trust configuration; applications must still authorize actions.

## 9. Rate limiting, quotas, and anti-abuse

Rate limiting protects system capacity and enables fair resource allocation. It can be applied across multiple layers:

| Layer | Limit key | Purpose |
|---|---|---|
| Edge/WAF | IP/prefix, request patterns | Curb floods and simple bot traffic |
| API Gateway | API key, route, stage, client | Shield backends from traffic spikes |
| Identity/application | User, tenant, partner, operation | Prevent one account or tenant from unfair consumption |
| Business | High-cost/high-risk actions | Limit OTP sends, booking creation, refunds, exports |
| Dependency | DB connections, payment providers, downstream services | Protect dependencies and cap concurrency |

Rate limits can use token buckets, leaky buckets, or window algorithms depending on implementation. Define rates, bursts, concurrency, quotas, responses, and distributed counter consistency. Multiple gateways/regions may not sync counters instantaneously; evaluate acceptable drift.

Never use raw IP alone as client identity: many users share NAT/proxies, while attackers distribute across IPs. Combine account/client/tenant and risk signals with appropriate privacy controls.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 5

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Request limit reached. Try again later."
}
~~~

Clients should retry with backoff/jitter and never repeat mutating operations without idempotency.

## 10. Input validation and preventing common exploit classes

### 10.1. Schema validation and mass assignment

APIs must validate data types, lengths, enums, ranges, formats, nested objects, and size limits before processing. Bind only fields the client is allowed to modify; never map entire JSON payloads directly into sensitive entities.

~~~json
{
  "guestCount": 2,
  "status": "CONFIRMED",
  "ownerId": "attacker-user",
  "isAdmin": true
}
~~~

If a backend binds directly to an entity, an attacker can attempt to alter status, owner, or privileges. Use request DTOs with field allowlists and validate all state transitions in the business layer.

### 10.2. Injection and data queries

- Use parameterized queries/prepared statements; avoid building SQL via string concatenation on inputs.
- Escape/encode appropriately for output contexts; input validation does not replace output encoding.
- Bound query complexity, pagination sizes, filter depth, and allowed sort fields.
- For GraphQL, cap depth/complexity, restrict introspection per policy, and guard against batching/alias abuse.
- Never let clients dictate arbitrary URLs for the server to fetch; validate against SSRF.

### 10.3. SSRF and outbound access

**Server-Side Request Forgery (SSRF)** occurs when an API accepts a caller-controlled URL/address and the server fetches an unintended target, such as a metadata endpoint or internal service.

Controls: prefer hostname/destination allowlists; block link-local, loopback, private/internal IPs, and metadata endpoints when unnecessary; validate DNS resolution and redirects; restrict egress at the network layer; enforce timeouts, response size limits, and content-type validation. Naive URL filters can be bypassed via DNS rebinding, redirects, or alternate IP encodings; enforce controls at both application and egress layers.

### 10.4. CORS and CSRF

**CORS** is a browser mechanism controlling which origins' JavaScript may read cross-origin responses. CORS is neither authentication nor authorization; non-browser clients can call APIs directly.

If using cookies automatically attached to user sessions, defend against **CSRF** using appropriate SameSite settings, anti-CSRF tokens/origin checks, and framework protections. With bearer tokens explicitly sent in Authorization headers, CSRF risk profiles differ, though token storage and XSS protection become critical.

Allow only necessary origins and review preflight/headers/methods. Strict CORS never replaces server-side API authorization.

## 11. Secrets, key rotation, and identity lifecycles

Credential leaks are typically lifecycle and operational failures, not merely secret-generation mistakes. Define:

1. **Issuance:** which user or workload receives credentials; purpose, scope, and owner.
2. **Storage:** secret manager/KMS or secure storage; keep out of source control, image layers, shell history, and plaintext logs.
3. **Use:** short-lived tokens, workload identities, least privilege, and proper network paths.
4. **Rotation:** scheduled or event-driven rotation; support old/new key overlap to avoid outages where needed.
5. **Revocation:** lost devices, suspected leaks, staff offboarding, service decommissioning.
6. **Audit:** who created, read, rotated, or used credentials; logs need owners and proper retention.

~~~mermaid
flowchart TD
    Start["Prepare new credential"] --> Store["Store in secret manager"]
    Store --> Deploy["Update clients/pipelines by version"]
    Deploy --> Verify["Verify requests with new credential"]
    Verify --> Revoke["Revoke old credential"]
    Revoke --> Audit["Record and monitor for anomalous usage"]
~~~

Never rotate keys arbitrarily without a process to update all consumers. A controlled overlap window may be needed; revoke old keys once consumer migration is verified.

## 12. Logging, auditing, and anomaly detection

API security needs visibility into both **request outcomes** and **business-meaningful actions**.

| Source | Useful data fields | Goal |
|---|---|---|
| Gateway access logs | Request ID, route, status, latency, protected client ID, policy-compliant source IP | Identify failing endpoints and traffic patterns |
| Auth/IdP audit | Login success/failure, MFA, grants, token issuance/revocation | Detect account/credential abuse |
| Authorization audit | Subject, action, resource reference, tenant, decision/reason | Investigate unauthorized access |
| Application security events | Validation failures, suspicious object access, rate-limit events | Catch business-layer abuse |
| WAF/DDoS telemetry | Rule, action, source pattern, rate events | Spot malicious traffic and false positives |
| Secret/IAM audit | Credential reads/rotations, role changes, policy updates | Monitor privileged access and credential exposure |

Never log bearer tokens, refresh tokens, passwords, client secrets, private keys, or full payment payloads. Pseudonymize/mask user identifiers and IPs as required by data policy. Protect logs from unauthorized modification/deletion, set retention, and restrict readers.

### Useful alerts

- Sudden spikes in login failures, token issuances, or unusual refreshes.
- Repeated 403/404 requests hitting sequential resource IDs or showing enumeration patterns.
- One client calling expensive endpoints past quota thresholds.
- Scope/resource access deviating from a service's baseline.
- Out-of-band changes to CORS, WAF, gateway routes, IAM roles, or key rotations.
- Tokens or API keys detected in logs/scanners/secret detection.

Alerts need owners and actions. Isolated 401/403 responses are normal traffic; use thresholds, baselines, and correlation to prevent alert fatigue.

## 13. Reference architecture for a booking platform

Suppose the system includes Web/Mobile clients, Booking API, Payment API, a Notification worker, and a database. Users read their own bookings; hosts manage listings; support staff have case-scoped limited access.

~~~mermaid
flowchart TD
    Web["Web / Mobile"] --> Edge["CDN / DDoS / WAF"]
    Edge --> GW["API Gateway"]
    GW --> IdP["OIDC Provider"]
    GW --> Booking["Booking API"]
    GW --> Payment["Payment API"]
    Booking --> Policy["Resource + tenant authorization"]
    Policy --> DB[("Booking DB")]
    Booking --> Outbox[("Outbox")]
    Outbox --> Bus[["Event Bus / Queue"]]
    Bus --> Notify["Notification worker"]
    Payment --> Provider["Payment provider"]
    Booking --> Audit["Audit / traces"]
    Payment --> Audit
~~~

### 13.1. Authentication rules

- Web/Mobile use OIDC Authorization Code + PKCE to sign in.
- Access tokens are issued for the proper API audience; ID Tokens are never used as bearer credentials to call APIs.
- APIs verify issuer, signature, expiry, audience, and required claims.
- Notification worker uses workload identity or short-lived role/service credentials to read its assigned queue and call the provider.
- Booking calls Payment using its own service identity; when acting on a user's behalf, pass controlled context/delegation rather than blindly forwarding raw user access tokens.

### 13.2. Authorization rules

| Action | Minimum conditions |
|---|---|
| Guest reads booking | Valid token + read scope + guest/tenant owns booking |
| Guest cancels booking | Owner or permitted policy actor + cancellable status + valid deadline |
| Host views related booking | Host holds permission on corresponding property + permitted data fields |
| Support reads sensitive info | Proper role + linked ticket/case + auditing and masking |
| Notification sends email | Workload identity authorized to read queue and use required secret/provider credential |
| Payment capture/refund | Appropriate service/user role + valid transaction state + idempotency |

### 13.3. Public API protection

- WAF and DDoS protection at the edge; gateway enforces payload size limits, route policies, auth integration, and quotas.
- Rate limits by client, user, tenant, and expensive actions.
- Backends accept traffic only from the designated gateway/private ingress; DB is never public.
- Request schema allowlists, validation, and output filtering.
- Controlled egress to payment providers; TLS and credential rotation.
- Audit events record sensitive decisions without logging tokens or full payment data.

## 14. Attack scenarios and verification

| Scenario | Verification | Expected control |
|---|---|---|
| Valid token, wrong audience | Call endpoint using token issued for another API | API rejects request |
| Expired token or invalid signature | Send expired/tampered token in tests | 401, zero business execution |
| BOLA/IDOR | User A swaps resource ID to B's record | Deny, zero data disclosure |
| BFLA | Regular user calls admin/refund endpoint | Denied at server |
| Tenant breakout | Client tampers with tenant ID in body/headers | Tenant taken from trusted context and checked |
| Mass assignment | Inject role, ownerId, status into request | Disallowed fields safely rejected/ignored |
| Credential stuffing/brute force | Run controlled failed-login pattern in tests | Rate/risk controls, alert, avoid mass false lockouts |
| API abuse | Call expensive export/search endpoints at high concurrency | Quotas, page caps, concurrency limits, alerts |
| SSRF | Test URLs pointing to metadata/private addresses in isolated env | Request blocked by allowlist/egress controls |
| CORS misconfiguration | Disallowed origin sends request/reads response | Browser policy enforces; server still authorizes |
| Secret leakage | Scan repositories, images, logs, and pipeline artifacts | Secret detection, revoke/rotate, and incident response |

Testing must occur within authorized environments and scopes using synthetic data; avoid running disruptive payloads against production.

## 15. Integrating protection into the development lifecycle

A secure API process is more than a pre-release security review. Integrate across phases:

1. **Design:** data flows, trust boundaries, threat modeling, scope/role/resource policies, and abuse cases.
2. **Build:** dependency scanning, secret scanning, SAST, and schema/contract validation.
3. **Test:** policy unit tests, negative authorization tests, API security tests, fuzz/input validation, and rate-limit tests.
4. **Deploy:** IaC policy checks, least-privilege pipeline identities, secrets injection, WAF/gateway config reviews.
5. **Operate:** access/audit logs, SLOs, abuse detection, key rotation, incident response, and periodic access reviews.
6. **Retire:** revoke clients, OAuth grants, API keys, certificates, service accounts, webhook subscriptions, and secrets.

### Review principles

- Every endpoint documents authentication requirements and authorization rules.
- APIs distinguish public/anonymous, user-authenticated, partner, and workload-to-workload traffic.
- Every client-supplied resource ID is checked for ownership/tenant relationship server-side.
- Token audiences and scopes bind tightly to the target API; refresh tokens do not enter logs or insecure browser storage.
- Gateways and WAFs enforce quotas and payload/rule policies without replacing business authorization.
- Service identities, secrets, certificates, and permissions have clear owners and lifecycles.
- Logs enable investigation without exposing authentication material.

## 16. Trade-offs under Well-Architected thinking

| Perspective | Decision | Benefits and trade-offs |
|---|---|---|
| **Security** | OAuth/OIDC, workload identity, least privilege, BOLA checks, WAF | Cuts unauthorized access; adds policy, key, and false-positive management |
| **Reliability** | Bounded token-validation caches, IdP fallback strategy, rate/concurrency controls | Reduces dependencies and overload; caching can delay revocation awareness |
| **Performance efficiency** | Appropriate gateway policies, JWKS caching, optimized authorization queries | Lowers introspection latency/cost; requires key rotation and cache invalidation handling |
| **Cost optimization** | Tiered WAF/log retention, quotas, anti-abuse | Curbs malicious request spend; comprehensive observability still requires budget |
| **Operational excellence** | Policy-as-code, auditing, dashboards, runbooks, automated key lifecycles | Easier control and investigation; needs owners and exception workflows |
| **Sustainability** | Drop junk traffic early, avoid wasted request processing | Cuts compute and transfer; overly strict rules risk blocking valid users |

For example, validating tokens at the gateway rejects bad tokens early and relieves backends. Yet if the gateway caches JWKS too long, new tokens may fail during key rotation; if token introspection is cached too long, revoked tokens remain accepted longer than desired. Choose TTLs based on threat models, issuer behavior, and operational requirements.

## 17. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Using ID Tokens to call APIs | Confuses client login assertions with access tokens | Use access tokens scoped to the target audience/resource |
| Decoding JWTs without verifying signatures | Attackers can forge claims | Verify signature, issuer, audience, expiry, and profile |
| Treating API keys as user identity | No ownership/tenant control | Separate authentication and per-resource authorization |
| Checking roles only in the UI | Direct endpoint calls bypass permissions | Enforce server-side per endpoint/action |
| Checking permissions on list but not get/update by ID | BOLA/IDOR | Object-level authorization on every operation |
| Trusting client-sent tenantId | Tenant breakout | Derive tenant context from verified identity and validate resources |
| Skipping backend authorization because gateway authenticates | Users access objects they do not own | Enforce resource-level policies in owning services |
| Embedding client secrets in mobile/browser apps | Secrets get extracted | Public clients use PKCE; backends use secret managers |
| Treating CORS as a firewall | Non-browser clients still call APIs | Server-side AuthN/AuthZ and rate limits |
| Treating WAF as a cure-all | Business logic/API authorization remains broken | SAST, testing, and per-endpoint security reviews |
| Logging tokens/API keys | Credentials leak through observability | Redaction, log allowlists, and secret scanning |
| Retrying mutating APIs without idempotency | Duplicate operations created | Idempotency keys and operation state tracking |

## 18. Public API acceptance checklist

### Identity and tokens

- [ ] User identity, client identity, and workload identity are clearly separated.
- [ ] Web/mobile use appropriate flows such as Authorization Code + PKCE.
- [ ] ID Tokens are never used in place of access tokens; APIs verify issuer/audience/signature/expiry.
- [ ] Scopes, roles, and client permissions are least-privilege.
- [ ] Refresh tokens, client secrets, API keys, and certificates have secure storage, rotation, revocation, and owners.

### Authorization

- [ ] Every endpoint/action has a clear server-enforced policy.
- [ ] Every object ID/tenant ID is checked for ownership and relationships.
- [ ] Negative tests exist for BOLA/IDOR, BFLA, tenant breakout, and mass assignment.
- [ ] Privileged actions have auditing and appropriate approval workflows.
- [ ] Service-to-service callers can invoke only required APIs/resources.

### API protection

- [ ] TLS and certificate lifecycles are managed; backend origins cannot bypass ingress controls.
- [ ] WAF/DDoS, gateway, payload limits, and schema validation are properly configured.
- [ ] Rate limits/quotas apply at appropriate tiers; DB/downstream concurrency is protected.
- [ ] CORS/CSRF match actual credential/client models.
- [ ] SSRF, injection, pagination/query complexity, and abuse cases are tested.

### Operations

- [ ] Gateway, IdP, authorization, WAF, and secret audits are traceable.
- [ ] Logs contain no tokens/passwords/secrets and follow retention/access policies.
- [ ] Alerts have owners and runbooks for credential abuse, authorization anomalies, and traffic spikes.
- [ ] Procedures exist to rotate/revoke credentials, disable clients, and respond to token leakage.
- [ ] Dashboards track latency, 4xx/5xx, 401/403, throttling, and business outcomes.

## 19. Practice lab

**Scenario:** An accommodation-rental platform exposes public APIs for Web, Mobile, and partner agencies. The APIs support viewing listings, creating reservations, cancelling reservations, checking payment status, and customer-support endpoints. Recently, an incident occurred where a user altered an ID in the URL to read another user's booking; a partner agency occasionally exceeds quotas; and an API key was accidentally committed to a repository.

Design the protection model:

1. Classify callers: end users, partner clients, internal workloads, and support agents.
2. Select OAuth/OIDC or workload identity flows for each caller.
3. Define appropriate audiences, scopes, and roles; explain which permissions require additional resource-level checks.
4. Write an authorization matrix for get/cancel reservation, payment status, and support access.
5. Propose token validation, key rotation, and a revocation process for the leaked API key.
6. Design Gateway/WAF, quotas, rate limits by IP/client/user/tenant, and concurrency caps.
7. Specify defenses for BOLA, BFLA, mass assignment, SSRF, and log leakage.
8. Identify audit fields, alerts, and runbooks for signs of cross-tenant access.
9. Propose negative tests and release acceptance criteria.

**Self-check hint:** Do not merely add a role to a token and assume BOLA is solved. Reservation API must verify the relationship between principal and reservation on the server. Partner API keys can aid client identification/quotas, but do not replace contractual credentials and authorization. When a key leaks, determine its usage scope, revoke/rotate it, inspect logs, and purge it from accessible artifacts.

## 20. Takeaways

**Authentication identifies the caller; authorization determines what the caller may do on which resources; API protection curbs abuse and limits request impact.** OAuth 2.0/OIDC, workload identity, mTLS, API Gateways, WAFs, rate limiting, and auditing address distinct layers and must be configured around explicit trust boundaries.

A secure API does not stop at a valid token. It validates audience and scopes, verifies per-object/tenant ownership, authenticates workloads separately, controls traffic and inputs, safeguards credentials, logs bounded audit trails, and tests negative cases. Controls must be continuously operated and measured to balance security with user experience, reliability, performance, scalability, and cost.
