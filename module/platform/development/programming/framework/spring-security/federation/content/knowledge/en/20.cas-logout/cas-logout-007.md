# Handling Duplicate Notifications, Expired Sessions, and Network Failures

> **Module:** Spring Security – federation · **Parent topic:** CAS Logout. This lesson explains how to handle **CAS Single Sign Out (SLO)** when the CAS server sends logout notifications **multiple times**, when notifications arrive after the `HttpSession` has already expired or logged out, or when callbacks are lost due to network failures. The goal is to build a session revocation mechanism that is **secure, idempotent, user/service-scoped, and observable**, without claiming CAS provides SLO delivery or completion guarantees that the protocol does not offer.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **CAS SSO session (TGT/TGC)**, **Service Ticket (ST)**, **application HTTP session**, **ST → HttpSession mapping**, and **Single Sign Out notification**.
2. Trace the path from CAS terminating a TGT to the application receiving `logoutRequest` and invalidating the exact local session.
3. State clearly how CAS SLO **back-channel POST** differs from **front-channel browser/AJAX/iframe**, and why SAML2-like XML syntax **does not automatically turn this integration into Spring Security SAML2 SLO**.
4. Explain why CAS SLO per the CAS Protocol is **best-effort / fire-and-forget** on the server side: CAS may ignore errors when sending notifications and does not promise exactly-once delivery.
5. Handle duplicate notifications with **idempotency**: the first invalidates the session, while subsequent ones neither destroy another session nor trigger serious errors.
6. Handle already timed-out/logged-out sessions: the mapping may be gone because `SingleSignOutHttpSessionListener` already cleaned it up, or `invalidate()` may encounter `IllegalStateException` under races.
7. Prevent **late** notifications arriving after a user's fresh login from mistakenly revoking the new session, by scoping correlation keys to service-ticket and generation.
8. Design protection for network ingress, TLS, callback origin, XML/payload limits, replay/DoS defense, and preventing clients from spoofing `SessionIndex`.
9. Understand the roles of `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, `SingleSignOutHandler`/session mapping storage in Java CAS Client, and their relationship to Spring Security `LogoutFilter`.
10. Build a runbook for when CAS cannot reach the SP, callbacks return HTTP errors, proxies time out, restarts wipe in-memory maps, or another node receives the notification.
11. Run a **standalone Java 17** program with deterministic output simulating duplicates, expired sessions, unknown tickets, late callbacks, and transport loss.
12. Create an integration test suite, metrics, and policies to determine whether a session remains active or was revoked across all nodes.

**Scope:** CAS service-ticket login and CAS Single Sign Out in Java Servlet applications. References Spring Boot 3.3.x/Spring Security 6.3.x with Java 17 and Apereo Java CAS Client. `javax`/`jakarta` servlet APIs and dependencies vary by release; when deploying, inspect actually resolved artifacts and verify APIs against your exact version. Snippets marked as "configuration fragments" are not standalone applications.

## 2. Real-world scenario: CAS logs out once, Portal receives multiple or zero notifications

Orders Portal uses CAS login for a user:

~~~text
CAS server:
  TGT-1 / TGC        SSO session at CAS, managed by CAS

Orders Portal:
  ST-A               Service Ticket issued by CAS for Orders
  JSESSIONID=app-71  Orders web session
  ST-A -> app-71     Mapping for CAS Single Sign Out

Reports Portal:
  ST-B -> app-92     A different application, different session
~~~

The user logs out at CAS. CAS destroys the TGT and attempts to notify the applications that participated in SSO.

However, several outcomes can occur:

- **Normal:** Orders receives the ST-A notification, finds `app-71`, calls `invalidate()`, and clears Authentication in the local session.
- **Duplicate:** a proxy retry or CAS resend causes Orders to receive the same notification twice. After the first, `app-71` is already ended; the second must **produce no new side effects**.
- **Expired:** session `app-71` expired before CAS sent the notification. The mapping was cleaned up by the listener; not finding the session is normal, **never a reason to create a new session**.
- **Local logout first:** the user already logged out in Orders, and CAS notifies afterwards. There is no need to re-delete an already-gone session.
- **Network loss:** CAS calls Orders yet DNS/TLS/proxy fails; Orders never receives the notification. **Session `app-71` may remain active** until local logout/session timeout/other revocation controls.
- **Late event after re-login:** the user receives a new ST-C and creates `app-103` after `app-71` ended. A stale notification for **ST-A** must not mistakenly destroy `app-103`.

**Key rule:** Each notification may affect only **the application session bound to the original ticket/CAS issuer**, never "all sessions currently sharing the same username".

## 3. Five objects and independent lifecycles

| Object | Where managed | Role in SLO | Must not be confused with |
| --- | --- | --- | --- |
| CAS TGT/TGC | CAS server + CAS domain cookie | SSO session letting CAS track participating services and trigger logout when TGT ends. | Application `JSESSIONID`. |
| Service Ticket ST | CAS ticket registry | Issued for a specific `service` and **consumed** when Portal validates it. | Java Servlet session ID. |
| `HttpSession` | Portal/container/session store | Local session holding SecurityContext, invalidated upon valid SLO notification. | TGT or ST. |
| Mapping `ST → session` | CAS client at Portal | Locates the local session to destroy based on CAS's `SessionIndex`/ticket. | User database lookup by `NameID` or email. |
| CAS SLO notification | CAS → Portal (back/front channel) | Instructs Portal to terminate the referenced session. | Proof CAS automatically destroyed every session across all apps. |

An ST already consumed at login **can still serve as a correlation key** for logout later. That **does not mean the ST may be verified a second time**; the CAS client merely retains its identifier to match the session created from that ST.

### 3.1. Three different clocks

~~~text
CAS SSO session:
  TGT issued ----------------------------- TGT expires / /logout

Service Ticket:
  ST issued -- ST validated once; consumed (login)

Application session:
  JSESSIONID created -------------------- local idle timeout / logout

SLO notification:
  CAS logout ---> POST queued/sent ---> SP received / timed out / missing
~~~

These timelines do not necessarily align. For instance, a local HttpSession may expire after 20 minutes of inactivity while the CAS TGT stays alive; or CAS may end the TGT early while the SP waits for a notification over a broken network.

## 4. How does CAS SLO happen?

### 4.1. Back-channel: CAS server sends a direct HTTP POST

~~~text
Browser                 CAS Server              Orders Portal          Reports Portal
  |                         |                        |                      |
  |  GET CAS /logout        |                        |                      |
  |------------------------>| invalidate TGT         |                      |
  |                         |                        |                      |
  |                         |--- POST logoutRequest ->|                      |
  |                         |                        | lookup ST-A->app-71  |
  |                         |                        | invalidate session   |
  |                         |<-- HTTP response ------|                      |
  |                         |-------------------------- POST logoutRequest ->|
  |                         |                        |                      | lookup ST-B->app-92
  |                         |                        |                      | invalidate
  |<-- CAS logout page -----|                        |                      |
~~~

Per the CAS Protocol, the server **may support SLO**, and when dispatching SLO POSTs it is permitted to **ignore errors** so CAS's own availability is not harmed. Consequently:

- HTTP 200 from Orders **does not prove** Reports also destroyed its session.
- A successful CAS logout page **does not prove** Orders received the callback.
- Not seeing a callback at Orders **does not prove** CAS failed to destroy the TGT.
- A proxy retry does not turn the operation into exactly-once.
- A CAS server may have version-specific delivery/retry/config behavior; **never assume** every CAS release automatically retries until all SPs acknowledge.

### 4.2. Example logoutRequest XML

In back-channel CAS SLO, the payload is typically a `logoutRequest` form field containing XML shaped like a SAML2 LogoutRequest:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas-logout-event-42"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z">
    <saml:NameID>alice</saml:NameID>
    <samlp:SessionIndex>ST-ORIGINAL-ORDERS-77</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**This is illustrative XML only, carrying no real digital signature.** The value in `SessionIndex` of a standard CAS notice is the **service ticket ID used to correlate the session**; it is **not** Servlet `session.getId()`, and must not be treated as a global user ID.

The `samlp`/`saml` namespace shape in CAS SLO **does not mean** you should use Spring Security's `http.saml2Logout()` to receive the notice. The CAS client has its own handler and different semantics from SAML2 SP LogoutRequest/LogoutResponse.

### 4.3. Front-channel: browser/AJAX/iframe

CAS can also be configured for front-channel SLO: the browser is used as the vehicle to send notifications to apps, such as AJAX/JSONP or iframes depending on profile/version.

Limitations:
- The browser may close the tab, block third-party cookies, block scripts, be affected by ad blockers/CSP, or lose connectivity.
- The browser may be unable to reach an SP's internal network endpoint even though the CAS server back-channel can.
- Not every CAS client fully supports all front-channel variants; check versions and test actual interoperability.
- Never treat an arbitrary HTTP GET JSONP carrying `logoutRequest` as authorization to kill sessions; protect origin/transport/payload and pick the right CAS client filter/profile.

**Choose back-channel when architecture permits**, though it too lacks an exactly-once guarantee; server-to-server calls still face DNS/TLS/proxy/firewall/queue and network failures.

## 5. How does the Java CAS client connect an ST to an HttpSession?

### 5.1. Key components

| Component | Role |
| --- | --- |
| `CasAuthenticationEntryPoint` | Spring redirects the user to CAS login to obtain an ST. |
| `CasAuthenticationFilter` | Receives the ST at the callback and hands it to the CAS authentication provider. |
| `CasAuthenticationProvider` + `Cas20ServiceTicketValidator` | Calls CAS `/serviceValidate` over HTTPS and authenticates the user. |
| Apereo CAS Client `SingleSignOutFilter` | Tracks ticket/session at login and handles incoming CAS SLO notifications. |
| `SingleSignOutHandler` | Component executing mapping/SLO handling logic inside the Java CAS client. |
| `SessionMappingStorage` | Abstraction storing ticket → session and reverse relationships for mapping cleanup. |
| `SingleSignOutHttpSessionListener` | Cleans up mappings when `HttpSession` is destroyed/expires. |
| `Spring Security LogoutFilter` | User-triggered local logout inside the app; not the CAS SLO receiver handler. |
| `SecurityContextRepository` | Persists/restores Authentication in the local HttpSession when the app is stateful. |

The standard package for Apereo's classes is `org.apereo.cas.client.session.*`. You must use a **Java CAS Client** compatible with `jakarta.servlet` on Spring Boot 3.x; never mix old filters compiled for `javax.servlet` into a Jakarta container.

### 5.2. Mapping created when the app receives the ST

~~~text
GET /login/cas?ticket=ST-A
     |
     v
SingleSignOutFilter records ST-A <-> HttpSession app-71
     |
     v
CasAuthenticationFilter / Provider
     |
     v
CAS /serviceValidate (server-to-server)
     |
     v
CAS success -> Spring SecurityContext in app-71
~~~

This is a **conceptual diagram**: exact timing of mapping/session creation and interactions with other filters depend on version, registration, and ordering. Verify via integration tests that the mapping is established properly **for valid logins**, without treating a mapping from a failed ticket validation as a source of authority.

### 5.3. Mapping used when CAS sends logout

~~~text
POST logoutRequest{SessionIndex=ST-A}
     |
     v
SingleSignOutFilter / handler
     |
     +-- ST-A mapped to app-71?
           |
           +-- yes -> invalidate(app-71)
           |         remove ST-A mapping
           |
           +-- no -> no local session to invalidate
                     log/metric with bounded detail
~~~

A CAS SLO notification **does not log a user in**, creates no `SecurityContext`, and must not be processed as a business request. It must be caught early in the filter chain/Servlet path before being accidentally blocked by a login redirect or CSRF rule.

### 5.4. Listener matters when sessions end on their own

`SingleSignOutHttpSessionListener` cleans up mappings when a local HttpSession is destroyed by timeout, local logout, or normal shutdown per container semantics. Without a compatible listener registered or if listener callbacks fail to fire, the ticket→session map can retain references to dead sessions, causing memory leaks, duplicate handling issues, and misdiagnosis.

**Never conclude from "mapping not found" that the user definitely never logged in.** The session may have expired, the listener may have cleaned up properly, a node restart may have cleared memory, or the event may have arrived very late. Use audits/metrics to distinguish these cases.

## 6. Duplicate notifications: handle idempotently instead of trying to prevent every duplicate

### 6.1. Why can duplicates occur?

- The CAS server/worker/proxy resends after a prior request timed out before knowing whether the SP finished processing.
- A network gateway retries a POST after HTTP 502/503 or a dropped connection.
- An event is replayed through an internal queuing system.
- The user refreshes the browser during front-channel or resends a request.
- An operator reruns a workflow per a runbook.
- Two paths/instances route to the same endpoint due to misconfiguration.

Never assume CAS **always** retries; these are possibilities from the deployment infrastructure. Because delivery is uncertain, **the receiver must be idempotent**.

### 6.2. Proper definition

An idempotent operation satisfies: **processing the same valid logout request multiple times for the same session produces the same final state as processing it once**.

~~~text
Before:
  session app-71 = ACTIVE
  ST-A -> app-71

SLO #1:
  session app-71 = INVALIDATED
  ST-A -> ended / mapping removed

SLO #2 (duplicate):
  app-71 stays INVALIDATED
  app-103 (new session) stays ACTIVE
~~~

The second execution **must never**:
- create a new session,
- destroy all sessions with username `alice`,
- destroy a newer session where the user re-logged in with ST-C,
- grant/restore Authentication,
- perform another non-idempotent business side effect,
- treat an `IllegalStateException` from an already-invalidated session as a reason to re-enable auth.

### 6.3. Two levels of outcome

Distinguish **session state** from **event processing outcome**:

| Outcome | Meaning | What should be done? |
| --- | --- | --- |
| `INVALIDATED_NOW` | Found the active session and just destroyed it. | Record success, clean up mapping, emit metric. |
| `ALREADY_INVALIDATED` | Same ticket already destroyed previously. | Do not destroy again; record low-severity duplicate metric. |
| `ALREADY_EXPIRED` | Session expired before the notification arrived. | Do not create a session; do not raise a system error. |
| `ALREADY_LOGGED_OUT` | User already performed local logout earlier. | Do not "undo"; treat as locally ended. |
| `NOT_FOUND` | Could not find a ticket→session mapping. | Do not guess; investigate if rate is abnormal. |
| `INVALID_NOTIFICATION` | Untrusted source/structure/binding. | Reject; raise security alert when appropriate. |
| `PROCESSING_FAILURE` | Session exists yet backend/session store failed during invalidation. | Alert/reconcile; **never claim destruction succeeded**. |

`NOT_FOUND` must not be interpreted with certainty as `ALREADY_INVALIDATED` unless a **tombstone/audit** provides evidence for that ticket. Instead record "mapping not found; no local effect verified".

### 6.4. HttpSession.invalidate may throw IllegalStateException

In Java Servlets, `HttpSession.invalidate()` can throw `IllegalStateException` if the session is already invalidated. Under races among timeout, local logout, and CAS SLO, an implementation may encounter this.

How to handle:
1. Verify the SLO event is valid and the mapping belongs to the right session.
2. Use atomic claim/state transition mechanisms if building a custom store.
3. When invalidation reports the session is already invalid, **never try to restore it**; verify via the session store if needed.
4. Never mask other exceptions (DB/Redis unavailable, network partition) under an "already invalidated" label.
5. Never reissue a session cookie to the callback.
6. Never leak `SessionIndex` or raw tickets in logs.

The Apereo filter includes built-in SLO handling; **do not replace it with a custom handler** without understanding your deployed version's source. If stronger idempotency and specialized auditing are needed, wrap at a tested control plane/store rather than altering CAS XML formats arbitrarily.

## 7. Sessions already expired before receiving SLO

### 7.1. Common sequence of events

~~~text
T0  Portal validates ST-A -> creates HttpSession app-71.
T1  User goes idle; app-71 hits idle timeout.
T2  Servlet container fires sessionDestroyed; CAS listener cleans up ST-A mapping.
T3  CAS TGT ends and sends logoutRequest(SessionIndex=ST-A).
T4  Filter finds no ST-A mapping.
~~~

For T0–T4, **there is no need to re-destroy `app-71`**: it already expired. If the listener works properly, `NOT_FOUND` after timeout is an expected outcome.

However, T4 **does not by itself justify concluding** all sessions of that user ended: the user may have **another local session**, another tenant, or a fresh login. A CAS notification for an old ticket must never be used as a command to wipe all sessions sharing `NameID`.

### 7.2. Local logout before SLO

~~~text
T0  User POST /logout at Portal.
T1  Spring LogoutFilter invalidates app-71.
T2  SingleSignOutHttpSessionListener cleans up ST-A -> app-71.
T3  User chooses CAS logout at https://cas.example/cas/logout.
T4  CAS sends ST-A notice; Portal has no remaining mapping.
~~~

At T4, the event finding no session is **expected**. What matters is verifying the session at T1 was genuinely destroyed, rather than forcing the listener to retain mappings forever just so a later callback can destroy it again.

### 7.3. Session already GC'd/purged while mapping lingers

If the listener is unregistered or a session is deleted in a distributed session store without firing the matching callback, mappings can go stale:
- The ticket still points to a destroyed or unfindable session.
- An in-memory map holds strong references to `HttpSession`, worsening memory leaks.
- The SLO handler may hit `IllegalStateException`.
- Over months, metrics report inflated "active ticket mappings".

Implement **session-lifecycle/TTL cleanup**, metrics on mapping age, and real session timeout tests—not merely manual logout tests.

### 7.4. Bounded tombstones

If business logic needs to distinguish duplicates from unknowns, you can maintain a **TTL-bound tombstone** keyed by a hashed/protected ticket:

~~~text
(approvedCasRealm, serviceRegistration, ticketHash)
 -> state = ENDED_BY_SLO
 -> endedAt, generation
 -> expiresAt = endedAt + shortRetention
~~~

Tombstones let you recognize duplicates without keeping `HttpSession` alive forever. The TTL must align with the latency/retry window and privacy retention policy, with bounded size and minimal stored fields. **Never rely on unbounded tombstones like a login ledger**.

## 8. Stale notifications must not delete new login sessions

### 8.1. Scenario

~~~text
T0  Alice logs in -> ST-A -> session app-71.
T1  app-71 local logout; ST-A mapping ends.
T2  Alice logs in again -> ST-C -> session app-103.
T3  CAS sends late SLO for ST-A.
~~~

**Right:** evaluate only ST-A; `app-103` stays active unless its own revocation policy applies. **Wrong:** use `NameID=alice` and destroy alice's current session regardless of ST.

Keep correlation keys scoped by **source and generation**:

~~~text
CAS realm: cas-partner-A
Service: https://portal.example/login/cas
Ticket: ST-A
Session generation: app-71-created-at-T0

Event ST-A -> targets app-71, never touches app-103
~~~

If CAS wants to log out every session under a TGT, each service ticket/session must be managed per contract with CAS. A notification for ST-A **does not authorize** the SP to destroy other sessions merely because they share a username.

### 8.2. Race when old logout arrives concurrently with new login

In multi-threaded/multi-node environments:

- An old SLO callback starts looking up mapping ST-A.
- A new login is creating session B and mapping ST-B.
- If the implementation stores `Map<username, HttpSession>`, the old callback may mistakenly target session B.
- If storing `Map<realm+ticket, sessionGeneration>` with atomic state, the callback acts only on the matching session.

Choose a **non-username-based key**. Masked usernames belong in audits, never as the sole SLO key.

## 9. Network failures: distinguishing delivery from logout effectiveness

### 9.1. CAS cannot reach the SP

Common causes:

- Wrong callback DNS, expired TLS certificate, or untrusted CA.
- Firewall/NAT/ingress blocks the CAS server from reaching the SP.
- Load balancer has no healthy backends or returns 502/503.
- The SLO endpoint URL was configured with an internal host instead of a URL reachable by the CAS server.
- The SP's session store is failing and cannot invalidate the session.
- A proxy strips the POST body or alters content type/encoding.
- CAS times out before the SP finishes, even though the SP **may already have destroyed the session**.

Per the CAS Protocol, the CAS server may **ignore SLO POST errors** to protect availability. Therefore **a successful CAS logout is not a distributed transaction committing that all SPs logged out**.

### 9.2. Matrix of four network outcomes

| Scenario | What CAS sees | What SP sees | What can be concluded? |
| --- | --- | --- | --- |
| Callback received/destroyed, CAS gets 2xx | Sent successfully. | Destroyed the right session. | SP local ended **if backend confirmed**. |
| Callback finished destroying yet HTTP response lost | CAS times out; may retry per config. | Session already ended. | Duplicate after retry is normal. |
| CAS cannot connect to SP | Network failure. | Never received notification. | Local session **may remain alive**. |
| SP receives callback yet session store fails | May see 5xx/timeout. | Cannot confirm destruction succeeded. | Must alert/reconcile; **do not claim success**. |
| SP receives duplicate after mapping cleaned up | May return 2xx if handled idempotently. | No new session destroyed. | Event handled at endpoint level; does not prove full federation logout. |

**Warning:** HTTP 2xx may simply mean the CAS client filter received and processed a valid notification within local capability. It is **not** proof that other SPs logged out.

### 9.3. Which HTTP status should be returned?

- **2xx:** valid notification, processing completed or session confirmed ended/handled idempotently.
- **4xx:** malformed notification, untrusted origin, or missing required fields; avoid leaking detailed diagnostics to attackers.
- **5xx:** genuine server error preventing confirmation of invalidation, such as an unavailable session store.
- **Unknown mapping:** consider 2xx after origin verification and idempotent handling if aligned with CAS client behavior; **do not label as invalidated** without proof. If policy requires investigation, separate metrics/audits.

The CAS client filter may determine status codes itself; **do not override status manually with a custom Controller** if that breaks filter behavior. Never use HTTP status codes as a substitute for auditing "which sessions actually ended".

### 9.4. Should SLO be retried?

The CAS protocol does not mandate guaranteed retries. If your organization adds queues/retries to the control plane:

1. Preserve the **original event ID/ticket scope**; never fabricate a new session ID.
2. Retry only on recoverable delivery/processing failures, using exponential backoff/jitter and retry caps.
3. The receiver must remain idempotent even if the producer assumes it deduplicated.
4. Events past their age limit must obey TTL/retention policies and never touch new sessions.
5. Never forward raw tickets/XML to unprotected logging or third-party queues.
6. Provide a DLQ/dead-letter queue and alerts; **never promise exactly-once** without an end-to-end transaction.
7. If an event arrives after app session timeout, treat it as locally ended when session expiry evidence exists.
8. Never use network retries to re-call **CAS `/serviceValidate`** with an old ST: that is a different operation, and STs validate only once.

## 10. Protecting the CAS SLO receiver endpoint

### 10.1. Why is a trust boundary required?

Standard CAS SLO messages use SAML-style XML, yet **you must not assume every notification carries an XML signature verified by a framework**. CAS client/filter releases implement their own mapping mechanics. If a public endpoint accepts arbitrary requests just because `logoutRequest` and a valid `SessionIndex` are present, an attacker who guesses/captures an ST can trigger unwanted logouts.

**Deployment-level defenses:**

- Place the CAS SLO receiver on the proper service route and accept back-channel traffic only from authorized CAS networks/identities.
- Use **HTTPS**, verifying hostnames and certificates; consider **mTLS** or an authenticated gateway when CAS and SP support it.
- Never trust `X-Forwarded-For`/`X-Real-IP` unless ingress sets them itself and strips client-supplied headers.
- Separate back-channel and front-channel access policies; front-channel cannot require the CAS server's source IP.
- If the contract specifies **signed CAS SLO messages**, verify signatures against the real profile/trust anchors; never assume a signature exists simply by seeing `<samlp:LogoutRequest>`.
- Enforce body/timeout limits, XXE-safe XML parsing, and proper URL-encoded form decoding; prefer an up-to-date Apereo filter.
- Never write a manual XML parser and call `session.invalidate()` by `NameID`.
- Apply rate limiting and telemetry while ensuring the rate limiter does not drop legitimate CAS bursts during an organization-wide logout.
- Never turn the callback into a login endpoint or create local Authentication upon receiving `logoutRequest`.
- Log hashed tickets/approved realms/services rather than raw STs, `NameID`, or `SessionIndex`.

### 10.2. Watch out for CSRF

Back-channel CAS SLO carries no app browser CSRF token. If the filter sits in the Spring Security chain after `CsrfFilter`, legitimate POST notifications may get 403. The fix is to place **CAS `SingleSignOutFilter` in the proper order across Servlet/security filters** or configure an exemption matcher **solely** for the protocol callback already authenticated via a separate channel.

**Never disable CSRF app-wide** just to make CAS SLO work: Portal browser forms still need CSRF defense. Likewise, a CSRF exemption **does not** make an SLO notification trustworthy; origin/binding validation remains mandatory.

### 10.3. Do not trust Content-Type and HTTP 200 blindly

- CAS can send `application/x-www-form-urlencoded` with a `logoutRequest` field; reverse proxies must pass the body intact.
- Another filter might consume the request body before the CAS filter; filter ordering matters.
- HTTP 200 from a proxy cache or custom health endpoint **does not prove** the CAS handler ran.
- If the endpoint returns a 302 redirect to CAS login due to an authorization rule, SLO was not processed even though proxy logs show a request.
- Never create an MVC `@PostMapping("/login/cas")` controller that accepts `logoutRequest` and returns 200 without destroying sessions.

## 11. Multi-node: where does the session mapping live?

### 11.1. In-memory maps do not share automatically across nodes

~~~text
CAS -> Load Balancer -> Node A:
       ST-A -> HttpSession app-71  (local map A)

CAS -> Load Balancer -> Node B:
       SLO SessionIndex=ST-A
       local map B: ST-A not found
       => cannot locate app-71
~~~

Spring Security reference shows Java CAS client `SingleSignOutFilter` using a local map to find sessions. **Do not assume** that running multiple JVMs or using Spring Session/Redis automatically makes the CAS SLO map distributed; they are two separate storage layers.

If a callback hits Node B while the mapping lives only on Node A, it may report `NOT_FOUND` even though `app-71` stays active. This is an **incomplete SLO** risk, not just noisy logs.

### 11.2. Operational options

| Design | Pros | Limitations / must test |
| --- | --- | --- |
| Sticky routing for callbacks and login | Reduces node mismatches in some setups. | Back-channel from CAS server **carries no browser cookie**, so cookie-based stickiness can fail. |
| All SLO routed to the owning service instance | Relatively simple when mapping knows origin. | Requires a trusted routing contract; never infer node from client-controlled headers. |
| Shared session + shared ticket/session mapping | Callback landing on any node finds the target session. | Requires a compatible `SessionMappingStorage` implementation; TTL/atomic claims/security. |
| Event bus fan-out across nodes | Finds the mapping on the node that created the session. | Requires internal auth, idempotency, retries, backpressure, and reconciliation. |
| Short local session timeout + best-effort SLO | Shrinks the window of surviving sessions. | Does not guarantee instant termination; UX trade-off. |

**Important:** storing a Java `HttpSession` object in Redis is not a valid strategy for all Servlet containers. Usually you store **ticket → session ID/store key** compatible with the session manager and invoke supported APIs to invalidate sessions across nodes, testing serialization and lifecycle.

### 11.3. Mapping counts and memory

A JVM can serve hundreds of thousands of sessions; if mappings are not cleaned up:
- Memory leaks and GC pauses.
- Stale session lookups make duplicates look like errors.
- User performs local logout while the mapping still references the object.
- Node rolling restarts lose in-memory mappings, causing later callbacks to miss.

Register `SingleSignOutHttpSessionListener` appropriately for your environment, verify `sessionDestroyed` lifecycles, and add orphan mapping cleanup, map-size gauges, and alerts. If using a distributed store, also enforce TTL/cleanup and consistency tests.

### 11.4. Session rotation and correlation

Spring Security may rotate the Servlet session ID after CAS login to prevent session fixation. The CAS client mapping must keep pointing to the **live session object/lifecycle** or the new session store key after rotation.

Do not maintain a custom `Map<ST, oldJSESSIONID>` and try to use the old ID to invalidate the session post-rotation without testing. If the app uses Spring Session or custom session strategies, test CAS SLO **after session ID rotation**.

## 12. Sessions and CAS tickets are two systems with separate revocation authority

### 12.1. Local logout

~~~text
Browser -- POST /logout --> Portal
                              |
                              +-- Spring Security LogoutFilter
                              +-- clear Authentication
                              +-- invalidate HttpSession
                              +-- listener removes ST mapping
                              |
                         CAS TGT/TGC may remain
~~~

Local logout ends only the Portal session. If the CAS TGT stays alive, opening a protected page can obtain a **new ST** and immediately re-SSO. That does not prove local logout is broken.

### 12.2. CAS logout

~~~text
Browser -- CAS /logout --> CAS invalidates TGT
                                 |
                                 +-- best-effort notify Orders
                                 +-- best-effort notify Reports
                                 +-- other services per CAS profile
~~~

If Orders receives and handles the notification properly, its local session ends. Otherwise, CAS cannot directly wipe Orders' cookies or session store simply by destroying the TGT.

### 12.3. Local account disable/revocation

Security teams may disable a user inside Portal even while CAS SSO remains active. The application must enforce local policy via account status, authorization checks, session revocation, or deny lists. **Never rely solely on CAS SLO for emergency access revocation**, because callbacks can be lost.

### 12.4. Stateless clients

Applications **without HttpSession** may use proxy tickets + `StatelessTicketCache`. Standard CAS SLO uses an ST→HttpSession mapping to invalidate local sessions, so it **does not automatically evict PT caches** and does not revoke other apps' OAuth/JWT/opaque tokens.

If an API uses a stateless authentication cache, define separate expiry/eviction/revocation policies rather than treating an `HttpSession` listener as sufficient.

## 13. State machine for operating SLO events

~~~text
LOGIN_VALIDATED
      |
      v
MAPPED_ACTIVE <------------------------------ CAS ticket correlated to session
      |
      +----> LOCAL_LOGOUT ---------> ENDED_LOCAL
      |
      +----> SESSION_TIMEOUT ------> ENDED_EXPIRED
      |
      +----> CAS_NOTIFICATION
                 |
                 +--> valid source and mapping -> ATOMIC_INVALIDATE -> ENDED_SLO
                 |
                 +--> duplicate of ended      -> NOOP_ALREADY_ENDED
                 |
                 +--> no mapping              -> NOT_FOUND / INVESTIGATE
                 |
                 +--> malformed/untrusted     -> REJECT_INVALID
                 |
                 +--> backend store failed    -> PROCESSING_FAILURE
      |
      +----> CAS notification never delivered -> MAY_REMAIN_ACTIVE
~~~

**Never design an edge** `ENDED_SLO → ACTIVE` on retry success; a fresh login must create a **new ticket/session generation**. An old notification must never attach to a new session solely via username.

### 13.1. HTTP outcomes differ from business outcomes

An audit model may record:
- `DELIVERED`: HTTP endpoint received the request.
- `VERIFIED`: endpoint verified origin/binding/payload per policy.
- `CORRELATED`: ticket→session mapping found.
- `INVALIDATED`: session store confirmed target session destroyed.
- `NOOP_ALREADY_ENDED`: mapping/tombstone proves it already ended.
- `NO_MAPPING`: insufficient proof the target session exists.
- `PROCESSING_FAILED`: genuine failure.

A CAS server reporting it sent a notification proves only `DELIVERY_ATTEMPTED`, not `INVALIDATED`.

## 14. Standalone Java 17: simulating idempotency and late notifications

This example **makes no real CAS calls, parses no XML, and uses no real HttpSession**. It simulates correlation by `CAS realm + service ticket`, session states, and outcomes when a notification arrives repeatedly. Never use a simulation in place of the Java CAS Client or production origin verification.

### 14.1. File `CasSloIdempotencyDemo.java`

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public class CasSloIdempotencyDemo {

    enum State {
        ACTIVE,
        ENDED_BY_SLO,
        ENDED_BY_TIMEOUT,
        ENDED_LOCALLY
    }

    enum Outcome {
        INVALIDATED_NOW,
        ALREADY_INVALIDATED,
        ALREADY_EXPIRED,
        ALREADY_LOGGED_OUT,
        NO_MAPPING
    }

    record TicketKey(String casRealm, String serviceTicket) {
    }

    static final class SessionRef {
        final String sessionGeneration;
        final AtomicReference<State> state =
            new AtomicReference<>(State.ACTIVE);

        SessionRef(String sessionGeneration) {
            this.sessionGeneration = sessionGeneration;
        }

        State current() {
            return state.get();
        }

        void expire() {
            state.compareAndSet(State.ACTIVE, State.ENDED_BY_TIMEOUT);
        }

        void logoutLocal() {
            state.compareAndSet(State.ACTIVE, State.ENDED_LOCALLY);
        }
    }

    static final class App {
        final Map<TicketKey, SessionRef> mapping =
            new ConcurrentHashMap<>();

        void register(
                String realm,
                String ticket,
                SessionRef session) {
            mapping.put(new TicketKey(realm, ticket), session);
        }

        Outcome onCasLogout(String realm, String ticket) {
            SessionRef target =
                mapping.get(new TicketKey(realm, ticket));

            if (target == null) {
                return Outcome.NO_MAPPING;
            }

            State previous = target.state.getAndUpdate(
                current -> current == State.ACTIVE
                    ? State.ENDED_BY_SLO
                    : current
            );

            return switch (previous) {
                case ACTIVE -> Outcome.INVALIDATED_NOW;
                case ENDED_BY_SLO -> Outcome.ALREADY_INVALIDATED;
                case ENDED_BY_TIMEOUT -> Outcome.ALREADY_EXPIRED;
                case ENDED_LOCALLY -> Outcome.ALREADY_LOGGED_OUT;
            };
        }
    }

    public static void main(String[] args) {
        App app = new App();

        SessionRef old =
            new SessionRef("app-71-generation-1");
        SessionRef renewed =
            new SessionRef("app-103-generation-2");
        SessionRef expired =
            new SessionRef("app-55-generation-1");
        SessionRef local =
            new SessionRef("app-66-generation-1");
        SessionRef networkLost =
            new SessionRef("app-88-generation-1");

        app.register("cas-A", "ST-A", old);
        app.register("cas-A", "ST-C", renewed);
        app.register("cas-A", "ST-EXPIRED", expired);
        app.register("cas-A", "ST-LOCAL", local);
        app.register("cas-A", "ST-NETWORK", networkLost);

        expired.expire();
        local.logoutLocal();

        System.out.println("first=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("duplicate=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("expired=" +
            app.onCasLogout("cas-A", "ST-EXPIRED"));
        System.out.println("local=" +
            app.onCasLogout("cas-A", "ST-LOCAL"));
        System.out.println("unknown=" +
            app.onCasLogout("cas-A", "ST-OTHER"));

        // CAS sends ST-A event late; must not target the new ST-C session.
        System.out.println("lateOld=" +
            app.onCasLogout("cas-A", "ST-A"));
        System.out.println("newSession=" + renewed.current());

        // A notification never arrives due to network failure: no
        // onCasLogout call runs for ticket ST-NETWORK.
        System.out.println("networkLossSession=" +
            networkLost.current());

        // Same ticket string but different realm: must not cross-lookup.
        System.out.println("wrongRealm=" +
            app.onCasLogout("cas-B", "ST-A"));

        System.out.println("otherTicket=" +
            app.onCasLogout("cas-A", "ST-C"));
        System.out.println("newAfterItsOwnLogout=" +
            renewed.current());
    }
}
~~~

### 14.2. Compiling and running

With JDK 17+:

~~~bash
javac --release 17 CasSloIdempotencyDemo.java
java CasSloIdempotencyDemo
~~~

**Deterministic stdout:**

~~~text
first=INVALIDATED_NOW
duplicate=ALREADY_INVALIDATED
expired=ALREADY_EXPIRED
local=ALREADY_LOGGED_OUT
unknown=NO_MAPPING
lateOld=ALREADY_INVALIDATED
newSession=ACTIVE
networkLossSession=ACTIVE
wrongRealm=NO_MAPPING
otherTicket=INVALIDATED_NOW
newAfterItsOwnLogout=ENDED_BY_SLO
~~~

### 14.3. Result explanation

- `first`: the old active session just transitioned to ended.
- `duplicate`: the same event does not destroy the session again.
- `expired`: the target session already expired; SLO is a safe no-op.
- `local`: the user already logged out locally; not restored.
- `unknown`: no mapping found; **never conclude with certainty the session was destroyed**.
- `lateOld` and `newSession`: the ST-A notification leaves the new ST-C session untouched.
- `networkLossSession`: missing callback means the app session may remain `ACTIVE`.
- `wrongRealm`: identical ticket strings across different CAS realms never cross-lookup.
- `otherTicket`: the new session is destroyed only when **its own ST-C** notification arrives.
- `AtomicReference.getAndUpdate` models an atomic state transition in **one JVM**, without CAS XML signatures, TLS, a session store, or networking.
- The demo retains all mappings to demonstrate duplicates. **Production must clean up maps/tombstones via TTL and listeners**, never holding unbounded references.

### 14.4. What this code does not replace

- Does not replace Apereo's `SingleSignOutFilter` for parsing/receiving notifications.
- Does not prove CAS origin trust or signed XML.
- Does not call real `HttpSession.invalidate()`; ended states are simulated.
- Does not handle distributed transactions across multiple API nodes.
- Does not provide CAS retries or delivery guarantees.
- Does not clear sessions on other devices or applications.

Separating **control simulation** from **real CAS integration** is essential; a Java map test cannot prove production SLO works across a load balancer.

## 15. Spring Boot 3.3 / Spring Security 6.3: putting SLO integration in the right place

### 15.1. Dependency and filter-order overview

Spring Security's CAS integration uses `spring-security-cas`; Apereo Java CAS Client supplies `SingleSignOutFilter` and `SingleSignOutHttpSessionListener`. Before deploying, verify the CAS client artifact truly matches the application's Servlet API.

Flow model:

~~~text
Servlet Container
    |
    +-- CharacterEncodingFilter (UTF-8)
    |
    +-- Apereo SingleSignOutFilter (receives/stores tickets and SLO)
    |
    +-- Spring Security FilterChainProxy
          |
          +-- CsrfFilter/browser policy
          +-- CasAuthenticationFilter
          +-- LogoutFilter
          +-- AuthorizationFilter
    |
    +-- Controller/business endpoints
~~~

This is the **desired ordering diagram**, not a claim that every project gets these filters merely by adding one dependency. If you place the Apereo filter in the Servlet container, **do not add the same instance again inside the Spring Security chain**. If integrating inside the Spring chain, set the exact order and avoid Spring Boot auto-registering the filter twice.

### 15.2. Suggested Gradle dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'cas-slo-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'
}
~~~

`spring-security-cas` handles CAS login; Apereo CAS client is the underlying dependency in matching releases. **Inspect the dependency tree and Servlet namespace** (Jakarta vs. Javax) before selecting an additional CAS client release or enabling SLO. This config is only a skeleton: without a CAS server, user mapping, and service registry, the app cannot demonstrate real SLO.

### 15.3. Java config for CAS SLO Filter/Listener

The following is an **illustrative Spring Boot servlet-registration fragment**, not a complete `SecurityFilterChain`:

~~~java
package com.example.casslo;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSingleLogoutServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        SingleSignOutFilter filter = new SingleSignOutFilter();
        FilterRegistrationBean<SingleSignOutFilter> registration =
            new FilterRegistrationBean<>(filter);

        registration.setName("casSingleSignOutFilter");
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
~~~

**Mandatory notes:**

- Apereo classes must belong to a **release compatible** with Spring Boot 3.x/Jakarta Servlet. If a version lacks a constructor/API or still uses `javax.servlet`, never "force compile" by mixing jars; pick a compatible release via dependency insight.
- This filter sits in the **Servlet chain**, ahead of `springSecurityFilterChain` at a verified order. Do not register the same filter a second time via `http.addFilterBefore(...)`.
- The CAS SLO filter must observe callbacks from CAS, including `logoutRequest` and login-flow tickets. If app routing/proxies expose only `/login/cas` while CAS POSTs elsewhere, align the service registry/callback contract.
- `SingleSignOutHttpSessionListener` must receive `sessionDestroyed`/expiration events from the active session manager.
- This code does not yet configure the CAS authentication provider, login filter, or local user/tenant mapping; implement those per CAS login documentation.
- **Numeric filter orders are illustrative only**; verify actual servlet filter registrations in the running environment, especially `CharacterEncodingFilter` and Spring Security.
- Do not declare `@Bean SingleSignOutFilter` alongside another `FilterRegistrationBean` causing double servlet auto-registration.

### 15.4. Spring Security local logout must stay separate

DSL fragment for local logout:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/signed-out", "/error").permitAll()
        .anyRequest().authenticated()
    )
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/signed-out")
        .invalidateHttpSession(true)
        .clearAuthentication(true)
    );
~~~

`POST /logout` handles the **local** session. To let the user log out of federation-wide CAS, deliberately redirect to the CAS server `/logout` via a trusted configured URL after local logout; **never** accept an arbitrary browser-supplied `casLogoutUrl`.

An SLO notification from CAS **is not** a browser local logout form: it has no Portal CSRF token, and the proper handler must accept the protocol cleanly while preserving CSRF protection on cookie-based application endpoints.

### 15.5. Verify the truth with tests, not just bean registration

An app having `SingleSignOutFilter` and `SingleSignOutHttpSessionListener` **still might not do SLO properly** if:
- The filter does not run on the path CAS POSTs to.
- The CAS client creates a mapping before the session is actually authenticated.
- The local session ID rotates after login without the mapping updating.
- The filter sits after security authorization and hits 302/403.
- The container creates two filter instances due to duplicate registration.
- Multi-node callbacks land on the wrong node with a local map.
- The session store/listener disagree, dropping cleanup events.
- The CAS server has SLO disabled or does not send SLO for the registered service.
- Network ingress from CAS to the callback is blocked.

Labs must use a real test CAS or controlled integration harness; never send unverified payloads into production.

## 16. Designing distributed mapping for multi-node deployments

If you cannot rely on local CAS client mapping, you can design a tested **SLO state management layer** while still using CAS client parsing/trust policies. Reference schema:

~~~sql
CREATE TABLE cas_slo_session_binding (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cas_realm_id VARCHAR(80) NOT NULL,
    service_id VARCHAR(120) NOT NULL,
    service_ticket_hash VARCHAR(128) NOT NULL,
    session_store_key VARCHAR(200) NOT NULL,
    session_generation VARCHAR(120) NOT NULL,
    state VARCHAR(24) NOT NULL CHECK (
        state IN ('ACTIVE', 'ENDED_SLO', 'ENDED_LOCAL', 'EXPIRED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE (cas_realm_id, service_id, service_ticket_hash)
);
CREATE INDEX cas_slo_active_expires
    ON cas_slo_session_binding (expires_at)
    WHERE state = 'ACTIVE';
~~~

**This is auxiliary management data**, not a drop-in `SessionMappingStorage` implementation for the Apereo client. Check client/session-manager APIs; a SQL row cannot by itself invalidate an `HttpSession` living in another JVM.

### 16.1. Atomic state transition

~~~sql
-- Call only after CAS notification has passed trust/parser checks.
UPDATE cas_slo_session_binding
SET state = 'ENDED_SLO',
    ended_at = CURRENT_TIMESTAMP
WHERE cas_realm_id = :approved_realm
  AND service_id = :approved_service
  AND service_ticket_hash = :ticket_hash
  AND state = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

An update with `affected-rows = 1` helps handle duplicates, **yet does not mean the `HttpSession` is already invalidated**. Design a sequence/transaction/outbox between mapping state and actual session-store revocation so you never mark `ENDED` and then fail to delete the session.

### 16.2. Safer two-phase state model

~~~text
ACTIVE
  |
  | atomic claim
  v
REVOCATION_PENDING
  |
  +-- session store confirms invalidated --> ENDED_SLO
  |
  +-- transient store failure -----------> RETRYABLE_FAILURE
  |
  +-- session already gone -------------> ENDED_EXPIRED/ENDED_LOCAL
~~~

An internal worker can retry `REVOCATION_PENDING` with backoff, relying on idempotent session invalidation and denying permissions to any session marked pending. This design adds complexity and is not required for every small Portal.

### 16.3. Ticket hashes and privacy

A service ticket is a sensitive credential; if storing mappings in a DB:
- Use a hash/keyed digest suited to the threat model; keep raw tickets out of logs.
- Store only admin-approved CAS realms/registered services; never accept them from requests.
- Enforce unique constraints/TTLs and purge ended records.
- Never put `NameID`, email, full XML, or raw `SessionIndex` in metric labels.
- Restrict query permissions, protect backups, and audit reads of correlation data.

## 17. Monitoring, metrics, and alerting

### 17.1. Suggested metrics

~~~text
cas_slo_notification_received_total{realm,service,channel}
cas_slo_notification_rejected_total{realm,reason_class}
cas_slo_session_invalidated_total{realm,service}
cas_slo_already_ended_total{realm,reason}
cas_slo_mapping_not_found_total{realm,service}
cas_slo_session_store_failure_total{service}
cas_slo_delivery_http_failure_total{service,status_class}
cas_slo_pending_revocation_age_seconds{service}
cas_slo_binding_active_count{service}
cas_slo_binding_expired_cleanup_total{service}
cas_slo_late_event_total{realm,service}
~~~

These **are not built-in metrics** in Spring Security or Apereo CAS. Instrument at the right layer and keep label cardinality low; never use service tickets, session IDs, `NameID`, emails, or raw XML as labels.

### 17.2. Appropriate logging

Structured event example without exposing raw tickets:

~~~text
event=cas_slo_received
cas_realm=partner-a
service=orders-portal
channel=BACK_CHANNEL
ticket_hash_prefix=7c28...
received_at=2030-05-01T10:00:01Z

event=cas_slo_result
cas_realm=partner-a
service=orders-portal
result=ALREADY_EXPIRED
session_generation_ref=opaque-ref
duration_ms=7
~~~

Never log raw `logoutRequest` XML or TGC/TGT/STs; those values can be credentials or PII and create replay/exploitation risks.

### 17.3. Useful alerts

| Symptom | Hypothesis | Action |
| --- | --- | --- |
| Spike in `NOT_FOUND` | Callback hitting wrong node, listener cleaning too early, short session timeout, mapping lost on restart. | Correlate node routing/session mappings and event age. |
| Spike in `ALREADY_INVALIDATED` | CAS/proxy retries or duplicate queue deliveries. | Check delivery/backoff; confirm zero side effects. |
| No callback seen in a CAS logout test | Ingress, DNS, TLS, service URL, or SLO disabled in CAS. | Inspect CAS SLO logs and SP ingress; never assume logout completed. |
| SLO 403 | CSRF/authorization filter blocked before CAS filter. | Fix filter order/matcher; never disable CSRF app-wide. |
| SLO 302 to CAS login | Callback treated like a protected browser resource. | Place protocol filter in the right position. |
| SLO 502/503 | Gateway or session store unavailable. | Repair/retry policy/alerts; inspect surviving active sessions. |
| Mapping count rises while session count drops | Listener/cleanup broken. | Fix `sessionDestroyed`, TTLs, and orphan cleanup. |
| User remains active after CAS logout | Callback lost or mapping missed; session stayed alive. | Reconcile/kill local session via admin workflow. |
| Abnormal re-SSO after CAS logout | TGT not actually destroyed, new login flow, cookie/cache issues. | Distinguish CAS vs. Portal sessions; check for new tickets. |
| SLO targets wrong session | Mapping keyed by username, realm/tenant confusion. | Run incident response; fix correlation key and tests. |

## 18. QA test matrix

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| L01 | Valid ST login; CAS SLO arrives for that ticket. | Invalidates exactly one local session. |
| L02 | Same `logoutRequest` sent twice. | First invalidates; second is a no-op/idempotent. |
| L03 | Two notifications arrive concurrently on the same node. | Single effective invalidation; no double effect. |
| L04 | HTTP response of first lost; proxy retries. | Session stays ended; repeat callback is safe. |
| L05 | Local session times out before SLO. | Listener already cleaned mapping; no new session created. |
| L06 | User performs local logout before SLO. | CAS notification does not restore local Authentication. |
| L07 | `Session.invalidate()` hits `IllegalStateException` due to timeout race. | Classified as already-ended; does not swallow unrelated store errors. |
| L08 | Real session store fails during invalidation. | Alert/processing failure; never report confirmed invalidated. |
| L09 | Old ST arrives after new ST-C login. | Does not destroy the ST-C session. |
| L10 | Two users share `NameID` across different CAS realms. | Never destroys cross-realm. |
| L11 | One user has two sessions issued via two STs. | SLO for ST-A does not auto-kill ST-B outside policy. |
| L12 | Ticket has no mapping. | Does not guess user or session; monitor `NO_MAPPING`. |
| L13 | Ticket mapping wiped on node restart. | No false success; check persistence/routing. |
| L14 | Callback hits Node B while mapping is only on Node A. | Fail closed/route properly or use shared mapping; never delete wrong session. |
| L15 | Callback hits Node B with distributed mapping. | Targets exact session in shared store. |
| L16 | Session ID rotated by fixation protection after CAS login. | Mapping still locates the final session. |
| L17 | Missing `SingleSignOutHttpSessionListener`. | Test catches orphan mapping/leak and blocks go-live. |
| L18 | SLO filter not placed before authorization. | Test catches 302/403 and does not mark success. |
| L19 | Filter auto-registered twice. | Test detects duplicate processing and fixes registration. |
| L20 | Proxy strips `logoutRequest` form field. | Callback fails/alerts; never claims destroyed. |
| L21 | Oversized payload/DOCTYPE/XXE. | Parser rejects; sessions unaffected. |
| L22 | Callback from untrusted origin/wrong binding. | Rejected per authenticated channel. |
| L23 | CAS mTLS contract with wrong client cert. | Ingress rejects; no logout. |
| L24 | CAS cannot reach SP due to firewall/DNS. | App session may stay active; alert/reconcile. |
| L25 | SP finishes invalidation yet CAS sees timeout. | Duplicate/retry may occur; never destroys user again. |
| L26 | CAS `/logout` succeeds yet one SP never gets SLO. | Never claim entire federation ended. |
| L27 | CAS front-channel browser closes tab. | Never assume notification arrived. |
| L28 | CAS front-channel JSONP unsupported by client. | Never silently claim completed; choose compatible profile. |
| L29 | Callback receives GET/`SAMLResponse` in another SAML2 format. | Never routed mistakenly to SAML2 LogoutResponse validator. |
| L30 | CAS session expired while local session has not. | Good SLO kills local; if delivery fails, timeout/revocation handles it. |
| L31 | CAS SLO retried past event TTL. | Never touches new session generation; audit late/expired. |
| L32 | User disabled locally before CAS SLO. | Local authorization still denies even if notification is lost. |
| L33 | App uses stateless PT cache. | HttpSession listener does not automatically evict PT cache. |
| L34 | CAS sends callback to public service URL yet proxy misroutes. | Fix canonical URL/ingress; never disable controls. |
| L35 | Separate OAuth/JWT session exists for same user. | CAS SLO does not automatically revoke other credentials. |
| L36 | Revocation requires cross-node atomicity. | Single logical revocation; no reactivation after races. |

### 18.1. Integration test lab

1. Stand up a **test CAS server** and two authorized service apps; enable back-channel SLO with HTTPS/test trust.
2. Have a user log in to Portal to obtain ST-A; verify the CAS client created a mapping from ST-A to the actual `HttpSession`.
3. Invoke CAS `/logout`; verify Portal receives the notification and the old `HttpSession` is unusable.
4. In test, resend **the exact same valid notification** if the harness permits; verify idempotency and no impact on new sessions.
5. Let a session time out before CAS logout; verify listener cleanup.
6. Block the callback network once via test firewall; confirm the local session can survive and telemetry reflects `UNKNOWN`.
7. Test the CAS server receiving 5xx when the SP session store is unavailable; trigger alerts and check reconciliation policy.
8. Run two nodes with and without shared mapping in the session store to measure behavior.
9. Rotate session ID after authentication; confirm mapping still tracks the current session.
10. Test stale ST-A arriving after a new ST-C login is created; confirm ST-C is untouched.
11. Test front-channel separately if supported by your organization; never assume every client handles JSONP/iframes.
12. Collect masked logs and metrics by realm/service/result without storing raw tickets.

### 18.2. QA pass criteria

- Test CAS logout proves local sessions are actually invalidated on target nodes.
- Duplicate SLOs cause neither cascading 500 errors nor wrong-session logouts.
- Expired sessions yield safe cleanup/no-ops without creating sessions.
- Late messages never touch new login generations.
- Delivery failures are never reported as authenticated logout completion.
- Security filters never widen privileges for untrusted SLO senders.
- User/tenant/revocation enforcement stays independent of SLO delivery reliability.
- `SessionIndex` ST is never used as a substitute for a user ID, login token, or permission.
- CAS sessions and application sessions have clear timeout/logout policies.
- Best-effort limits are stated in operational messages and UX.

## 19. Runbook for common incidents

### 19.1. Case A — repeated notifications

**Symptoms:** the same CAS realm/service/ticket correlation appears repeatedly in audits; the session is already invalidated.

**Actions:** confirm duplicate, measure retry count, inspect proxy/gateway/idempotency store, and never wipe username-wide sessions. If returning HTTP 200 for duplicates, record only that it was handled **idempotently**, never falsely logging "new session invalidated".

### 19.2. Case B — session expired, mapping not found

**Symptoms:** a valid SLO callback arrives after idle timeout; `SingleSignOutHttpSessionListener` already removed the ticket.

**Actions:** compare timestamps against session expiration audits and create no session; if `NO_MAPPING` spikes unexpectedly, check the session store, listener, node routing, and TTL. Do not halt CAS logins over normal late duplicates.

### 19.3. Case C — no callback despite CAS logout

**Symptoms:** CAS TGT is destroyed, yet Portal shows no event and the `JSESSIONID` session remains usable.

**Actions:** confirm CAS has SLO enabled and check the delivery type for the service; inspect firewall/DNS/TLS/routing, CAS outbound logs, and SP ingress logs. If security is suspected, **revoke local sessions directly in the application store** via admin controls and tighten max session lifetime per policy. Never simply tell the user to log out of CAS again and call it done.

### 19.4. Case D — SP processed it yet CAS still reports timeout

**Symptoms:** Portal audited `INVALIDATED_NOW`, while CAS sent the POST and upstream reported a timeout.

**Actions:** confirm the session really ended; if retried, the receiver no-ops and responds per handler policy. Investigate proxy timeouts/response paths; never treat CAS missing the ACK as a reason to restore the session.

### 19.5. Case E — callback landed on wrong node

**Symptoms:** mapping exists only on Node A while callback hits Node B; high `NO_MAPPING` while sessions stay active.

**Actions:** adopt shared mapping or authenticated routing/fan-out per architecture and run multi-node integration tests. Never rely solely on sticky cookies if CAS back-channel carries no browser cookies. Mark SLO coverage degraded until fixed.

### 19.6. Case F — forged POSTs hitting the SLO endpoint

**Symptoms:** anomalous traffic, `SessionIndex` not matching known tickets, wrong source IP/mTLS, malformed bodies, or bursts of failed lookups.

**Actions:** rate-limit/block per policy, lock down ingress and origin, run incident audits without disclosing ticket mappings. If accidental logouts occurred, assess affected user scope and fix the trust boundary before reopening the endpoint.

## 20. Self-assessment questions

**1. Does a successful CAS `/logout` guarantee every SP session was destroyed?**  
No. CAS SLO per protocol is best-effort/fire-and-forget on delivery; each application owns and destroys its own sessions.

**2. What is `SessionIndex` in CAS SLO?**  
In traditional CAS SLO, it is usually the service-ticket identifier used to match the local `HttpSession`, not the raw Servlet session ID.

**3. Why is `SingleSignOutHttpSessionListener` needed?**  
To clean up mappings on session timeout or local logout, preventing leaks and stale lookups.

**4. What should happen if the exact same notification arrives again after the session was invalidated?**  
Idempotent no-op; never destroy a different session sharing the username.

**5. If no mapping is found, is the user guaranteed to be logged out?**  
No. It could be expired, locally logged out, stranded on another node, or lost to network/routing errors.

**6. What if CAS sends a late notification after the user already logged back in?**  
Act only on the original ticket/generation; leave the new session untouched if it has a different ticket.

**7. Does a CAS server timeout calling SLO mean the SP has not logged out?**  
Not necessarily. The SP may have already destroyed the session while the ACK was lost; check the session store/audits.

**8. If the SP receives the notification yet the session store is broken, should it return success?**  
Never record "local session invalidated" without proof; handle as failure/retry/reconciliation.

**9. Why not use `NameID` to immediately destroy all sessions?**  
Because `NameID` is not a unique ticket/session key, can collide across realms/tenants, and causes erroneous logouts.

**10. The CAS notification looks like SAML XML—should you use `saml2Logout()`?**  
Not automatically. CAS SLO uses the Java CAS Client filter and mapping, not the SAML2 SP LogoutResponse workflow.

**11. If an app runs two nodes with shared `HttpSession`, is SLO automatically distributed?**  
Not necessarily; the CAS client's ticket→session mapping may still remain local.

**12. Can a browser's CSRF token authenticate a CAS back-channel POST?**  
Normally no. Use a dedicated protocol filter/ingress origin trust rather than disabling CSRF app-wide.

**13. To avoid duplicates, must you guarantee CAS sends at most once?**  
You cannot rely solely on the producer. The receiver must be idempotent and correlate by ticket.

**14. CAS logged out, yet a cached stateless proxy ticket still works on an API?**  
Possible if a separate cache has not been evicted; `HttpSession` SLO does not automatically revoke other caches/tokens.

## 21. Production checklist

- [ ] Clearly defined CAS TGT/TGC, ST, `HttpSession`, and ST→session mapping.
- [ ] CAS client `SingleSignOutFilter` configured properly and running before filters that could block callbacks.
- [ ] `SingleSignOutHttpSessionListener` aligned with Servlet container/session manager.
- [ ] Callback path, service URL, TLS, ingress networking, and SLO propagation type agreed between CAS and Portal.
- [ ] Never creates a new Authentication/session when receiving `logoutRequest`.
- [ ] Ticket correlation scoped by trusted realm/service/ticket, never by username/`NameID` alone.
- [ ] Duplicate notifications yield no-op or idempotent outcome with zero double side effects.
- [ ] Expired/locally logged-out sessions are handled safely without restoration.
- [ ] Late callbacks never destroy newer session generations.
- [ ] Never uses raw `SessionIndex` as an HTTP session ID to wipe user-wide sessions.
- [ ] Clear SLO origin trust boundary (HTTPS/mTLS/network allowlist/profile validation), ignoring spoofable headers.
- [ ] Parser bounds payload size, blocks XXE, and excludes raw XML/PII/tickets from logs.
- [ ] Never disables CSRF for the entire browser app; handles CAS SLO via proper filter/protocol config.
- [ ] Multi-node deployments test shared mappings or authenticated routing/fan-out.
- [ ] Session ID rotation preserves ticket mapping; `sessionDestroyed` cleanup verified.
- [ ] Distributed stores include TTL, atomic claims, retryable failures, and never mark ended before verified revocation.
- [ ] Best-effort CAS SLO delivery documented in threat model; CAS logout page never treated as global proof.
- [ ] Runbooks exist for network timeouts/5xx/502/DNS/TLS failures.
- [ ] Emergency out-of-band local session revocation exists if SLO callbacks are lost.
- [ ] Local authorization/account disable remains effective during network outages.
- [ ] Stateless PT caches or OAuth/API sessions have dedicated revocation policies.
- [ ] Metrics separate received, verified, mapped, invalidated, expired, duplicate, not_found, and failure.
- [ ] L01–L36 tests or equivalent integration suite executed against test CAS server and multiple nodes.
- [ ] When upgrading Spring Security/Apereo CAS client, verify APIs and Servlet namespaces and rerun SLO regression tests.

## Key takeaways

> **CAS Single Sign Out is a notification mechanism prompting each application to end its own session, not a distributed transaction guaranteeing logout everywhere.** On duplicate notifications, destroy the right session **once** and no-op thereafter; on already-expired sessions, never recreate or kill new sessions; on network loss, **never assume** the local session was revoked. Use **CAS realm + service ticket → session generation** keys, listener cleanup, ingress controls, idempotency, metrics, and runbooks to protect trust boundaries.

### References

- [Apereo CAS — CAS Protocol Specification, 2.3 /logout and Single Logout](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): SLO POST, session identifier, client behavior, and fire-and-forget error handling.
- [Apereo CAS — Logout & Single Signout](https://apereo.github.io/cas/development/installation/Logout-Single-Signout.html): CAS SSO session vs. app session; back-channel and front-channel propagation; notification-only semantics.
- [Apereo Java CAS Client — README: Configuring Single Sign Out](https://github.com/apereo/java-cas-client#configuring-single-sign-out): `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, and filter-order requirements.
- [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS login/filter/provider, local logout vs. CAS logout, mapping, and listener cleanup.
- [Spring Security — Architecture / Filter Registration](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering and risks of registering a Filter bean twice.
- [Spring Security — Logout Handling](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `LogoutFilter`, session invalidation, CSRF, and logout success.
- [Jakarta Servlet API — HttpSession](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession): `invalidate()` and `IllegalStateException`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SessionCreationPolicy`, `SecurityContextRepository`, and session fixation protection.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session lifecycle, and protecting revocation.
