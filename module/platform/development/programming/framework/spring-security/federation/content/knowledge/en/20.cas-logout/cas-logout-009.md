# Verifying Logout Behavior When Multiple Services Hold Active Sessions

A user may log in to **CAS Single Sign-On (SSO)** once and simultaneously use multiple applications, such as **Portal A**, **Reports B**, and **Admin C**. Each application typically creates its **own HTTP session / SecurityContext** after validating a CAS Server service ticket (ST). Consequently, a CAS page displaying "Logged out" **does not by itself prove** sessions in A, B, and C actually terminated.

With **CAS Single Logout (SLO)**, when the SSO session at the CAS Server ends and SLO is properly configured, CAS attempts to send **logout notifications to the CAS services that participated in the session**. Each receiving service must locate the **exact application session linked to that service ticket** and destroy it. This is a **best effort** mechanism: notifications can fail on the network, be sent asynchronously, be blocked on front-channel, or fail due to misconfigured app handling. This lesson focuses on how to **design and execute end-to-end verification** when multiple services hold active sessions, including late callbacks, an offline service, multiple sessions for the same user, and API tokens surviving logout.

**Expected outcomes:** know how to distinguish **local logout**, **CAS logout**, and **CAS SLO**; build a multi-service test; match `logoutRequest` messages by **SessionIndex (service ticket ID)** to local sessions; verify final state at **each application** instead of merely watching redirects; detect propagation failures; and apply safe compensating policies.

> **Verification principle:** "CAS Server destroyed the SSO session" is one event; "each service destroyed its corresponding application session" is **multiple independent events** that must each be proven. An HTTP 200 or a CAS logout success page never replaces verifying access to protected resources at A/B/C.

## 1. Session types coexisting during a single SSO session

Suppose user `lan` opens one browser profile and visits:

- `https://portal.example.org` — **Service A**, a Spring Boot application.
- `https://reports.example.org` — **Service B**, a reporting application.
- `https://admin.example.org` — **Service C**, an administration application.
- `https://sso.example.org/cas` — **CAS Server**, handling SSO.

When A/B/C receive service tickets and validate them successfully with CAS, each service can issue an **independent local session cookie** (e.g., `JSESSIONID` scoped by host/context path) alongside its own `SecurityContext`. The CAS Server holds the **Ticket-Granting Ticket (TGT)** in its server store, and the browser holds the associated CAS cookie (commonly called **TGC**).

| Object | Where managed | Consequence when ended | Should not be confused with |
| --- | --- | --- | --- |
| CAS TGT / SSO session | CAS Server | New service visits may require re-authentication; CAS may emit SLO notifications. | `JSESSIONID` of A/B/C. |
| CAS Cookie / TGC | Browser and CAS Server | Browser can no longer SSO via that TGT session. | Local cookies of individual services. |
| Service A's ST | Issued by CAS Server, validated by A | Binds a single login transaction to A; also useful for SLO correlation. | TGT or local session ID. |
| Service B/C's ST | Issued separately by CAS Server for B/C | Corresponds to each login at B/C. | A's ST, even for the same username. |
| HTTP session at A | A's Servlet container / Spring Session | Access to A in that session ends upon invalidation. | CAS Server session or B's session. |
| HTTP session at B | Service B | Only B's session changes when B processes logout. | Sessions at A and C. |
| HTTP session at C | Service C | Only C's session changes when C processes logout. | Sessions at A and B. |
| Separate access token / API session | Authorization Server / Resource Server | May remain valid per its own TTL/revocation. | CAS SLO automatically terminating every bearer token. |

**There is no shared `HttpSession` across applications** merely because the user logged in via CAS. Nor should anyone assume `logoutRequest` wipes every session sharing the same username across all devices.

### 1.1. Example pre-logout state

~~~text
CAS:
  TGT-SESSION-1 (user=lan, active=true)
    visited services:
      A -> ST-A1
      B -> ST-B1
      C -> ST-C1

Service A:
  ST-A1 -> HttpSession A-S1 -> Authentication(lan) [ACTIVE]

Service B:
  ST-B1 -> HttpSession B-S1 -> Authentication(lan) [ACTIVE]

Service C:
  ST-C1 -> HttpSession C-S1 -> Authentication(lan) [ACTIVE]
~~~

These IDs are **illustrative only**, not real tickets or cookies. After successful CAS SLO, **each of sessions A-S1, B-S1, and C-S1** must no longer be permitted to access protected resources. One service may hold **multiple local sessions** for the same subject—for example, two browsers or two separate CAS TGTs; SLO must target only the session indicated by CAS rather than blindly wiping all user sessions unless policy authorizes it.

## 2. Three logout types that must be verified separately

| Action | Where the event occurs | Minimum outcome | Automatically affects other services? |
| --- | --- | --- | --- |
| **Local logout at A** | Spring Security A's `POST /logout` | Clears `SecurityContext`, invalidates session A per config. | **No** by default: CAS TGT and B/C sessions may remain alive. |
| **CAS logout** | Browser visits CAS `/logout` via valid flow | CAS destroys the corresponding SSO session/TGT. | **No guarantee** B/C are destroyed unless SLO is enabled and notifications are handled. |
| **CAS Single Logout (SLO)** | CAS emits logout requests to services logged in under the TGT | Each service receives and invalidates its mapped local session. | Can reach A/B/C, yet **best effort** and dependent on each service. |
| **Logout by expiration/timeout** | CAS or local session reaches expiry | CAS/clients may have version/policy-specific SLO behavior. | **Not identical** to user-initiated CAS logout; must be tested separately. |
| **Upstream IdP/broker logout** | Another upstream OIDC/SAML system | Ends upstream session per its protocol. | Cannot automatically infer upstream/downstream logout from CAS SLO. |

When a user clicks logout in A, the app can present options **"Log out of this application"** and **"Log out of CAS"**. Both choices need distinct URLs, expectations, and clear UI messaging. If A only logs out locally while the CAS TGT stays alive, when the browser returns to A and gets redirected to CAS login, CAS can immediately issue a **new ST** without prompting for a password. That is valid SSO behavior and **does not prove local logout failed**.

### 2.1. Why is the logout button at CAS insufficient?

SLO is a **notification** mechanism: the CAS Server proactively contacts recorded services, and each service must **process the message** to destroy its session. Distinguish:

~~~text
TGT destroyed               -- CAS Server confirms
SLO message for A created    -- CAS Server orchestrates
SLO POST A accepted          -- network delivery reached A
A mapped SessionIndex=ST-A1 -- A finds exact local session
A invalidated A-S1           -- session A is destroyed
A GET /private returns 401/redirect CAS -- user no longer has access under A-S1
~~~

Only the final step plus local evidence proves the user **can no longer access A with the old session**. B and C require the same verification chain. If the browser automatically re-SSOs during a test, you could mistake a **post-logout new session** for the old session surviving; compare ticket/session generations and timestamps.

## 3. CAS SLO: how does the server send requests to multiple services?

Per the CAS Protocol and Apereo CAS documentation, when a TGT is **explicitly destroyed** (and optionally on timeout depending on configuration), CAS locates the service tickets issued during that session and sends Single Logout notifications to the corresponding services. In **back-channel SLO**, the CAS Server typically sends an HTTP POST directly to each service; in **front-channel**, CAS may use the browser/AJAX/iframes depending on CAS Server and client.

### 3.1. Back-channel: example of three independent notifications

~~~text
                    CAS Server /logout
                      | destroy TGT-SESSION-1
             +--------+---------+
             |        |         |
         POST A    POST B     POST C
         ST-A1     ST-B1      ST-C1
             |        |         |
        A session  B session   C session
        A-S1 gone  B-S1 gone   C-S1 gone
~~~

Notifications can be dispatched **asynchronously**. A may receive before C, while B receives late or is offline. Never expect that the exact millisecond the browser is redirected away from CAS, all three services have already finished processing.

### 3.2. What does LogoutRequest look like?

Example **CAS SLO message** using XML structured like a SAML LogoutRequest:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-unique-1"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>lan</saml:NameID>
  <samlp:SessionIndex>ST-A1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

In the **CAS SLO protocol**, `SessionIndex` is normally the **service ticket ID** used by the application at login—**not the CAS TGT ID, not the servlet `JSESSIONID`, and not an `AuthnStatement SessionIndex` from a separate SAML SSO federation**.

Example POST (abbreviated representation illustrating transport only):

~~~http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=<url-encoded-xml-logout-request>
~~~

The `logoutRequest` line above is **symbolic**. When a real client processes it, the CAS library extracts and parses the message per its version. Never take an XML string sent by a browser to `/logout` and treat it as authority to invalidate another user's session.

**Specifically:** despite using XML element names from SAML namespaces, **CAS back-channel SLO is not equivalent to a full SAML 2.0 SLO profile with signatures and trust metadata**. You must enforce notification origin verification appropriate to your CAS deployment: HTTPS, trusted network paths, endpoint ACLs/mTLS/gateway where needed, replay protection, and standard library handling.

### 3.3. How does each service identify the right local session?

Right:

~~~text
CAS logoutRequest SessionIndex = ST-A1
             |
             v
Service A CAS Client mapping:
  key   = ST-A1
  value = HttpSession A-S1
             |
             v
A invalidates A-S1 (not B-S1/C-S1)
~~~

Wrong:

~~~text
logoutRequest NameID = lan
  -> service A deletes ALL sessions for username "lan"
~~~

One account can be active across **two browser profiles** with **two independent TGTs**. Deleting all sessions by username when only one TGT was terminated logs out other devices mistakenly; worse, if a notice is forged, an attacker can disrupt every session of the victim. **The correlation identifier in SLO is service ticket ID → local HttpSession**, never the username.

## 4. Spring Security and Apereo Java CAS Client mechanics

Key components in a Servlet application:

| Component | Role during logout |
| --- | --- |
| **`CasAuthenticationFilter`** | Processes CAS service ticket callbacks for successful Spring Authentication. |
| **`CasAuthenticationProvider`** | Validates ST via `TicketValidator`; loads user authorities. |
| **`SingleSignOutFilter`** (`org.apereo.cas.client.session.SingleSignOutFilter`) | Receives CAS `logoutRequest`, finds the session to destroy, and also participates in recording mappings at login. |
| **`SingleSignOutHttpSessionListener`** | Cleans up mappings when a servlet `HttpSession` is destroyed/expires, avoiding stale references. |
| **`SessionMappingStorage` / `SessionMappingStorageImpl`** | Maps between **service ticket ID** and the service's `HttpSession`. |
| **Spring Security `LogoutFilter`** | Handles application-initiated logout, invoking logout handlers and clearing `SecurityContext`. |
| **`SecurityContextRepository`** | Persists/restores the app's Authentication across requests/sessions. |
| **Spring Session** (when used) | Manages sessions via a distributed store and handles expiration/invalidation appropriately. |

### 4.1. The SLO filter must run in the right order

Apereo Java CAS Client documentation commonly configures `SingleSignOutFilter` in the **container filter chain** and `SingleSignOutHttpSessionListener` as a servlet listener:

~~~xml
<!-- Condensed web.xml example; applies to containers supporting Servlet listeners. -->
<filter>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <filter-class>org.apereo.cas.client.session.SingleSignOutFilter</filter-class>
</filter>
<filter-mapping>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <url-pattern>/*</url-pattern>
</filter-mapping>
<listener>
  <listener-class>
    org.apereo.cas.client.session.SingleSignOutHttpSessionListener
  </listener-class>
</listener>
~~~

**This is an illustrative configuration**, not a complete `web.xml`. In a Spring Boot embedded servlet container, registering `FilterRegistrationBean` and `ServletListenerRegistrationBean` (or equivalent supported mechanisms) must ensure **CAS logout callbacks pass through the filter**, the filter initializes early in the pipeline, and the container invokes the listener. Never register two `SingleSignOutFilter` instances processing the same request; avoid double registration and duplicate invalidation.

Key test point: **`SingleSignOutFilter` must see CAS ST login requests to record the mapping and CAS SLO requests to remove the mapping**. If the filter maps only to `/cas/logout` while the actual ticket callback is `/login/cas`, it may never record the mapping. If Spring Security blocks the callback POST before the filter runs, CAS Server gets 403 and the session is never destroyed.

### 4.2. SLO and Spring Security logout are not the same handler

Spring Security local logout is typically configured as:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

This is a **configuration fragment inside `SecurityFilterChain`**, not a standalone program; depending on CSRF config, the browser must send **POST** to local `/logout`. It guarantees only **local** logout per Spring Security policy; it **does not automatically intercept CAS back-channel SLO** and does not automatically send the browser to CAS `/logout`.

Conversely, `SingleSignOutFilter` must **receive `logoutRequest` from CAS** and invalidate the right session without requiring the browser to have page A open. **Server-side CAS SLO can destroy A-S1 even while the browser is sitting on tab B.**

### 4.3. Session fixation protection and post-login mapping

Spring Security can rotate the **session ID** after authentication (session fixation protection). If the CAS Client mapping holds an `HttpSession` reference while the store/container rotates the ID, or if a callback arrives right as the session changes, tests must prove the mapping **still locates the live active session**. Never disable session fixation protection just to "make SLO work"; test your actual Spring Security, Servlet container, and CAS Client versions.

If the session is **invalidated and replaced by a brand-new session** rather than merely rotating the ID, the old mapping may point to the destroyed session. Ensure lifecycle management registers the mapping against the surviving session. Never infer from a single 200 callback that the session was destroyed when a stale reference was stored.

### 4.4. No Spring Security session exists if the app uses JWT/another BFF

If service B is an SPA or API server using stateless bearer tokens, there is no `HttpSession` corresponding to the service ticket. `SingleSignOutFilter` cannot automatically revoke all issued JWTs. B needs its own **session registry/token revocation/introspection/version check/short token TTL** design. Never label OIDC Back-Channel Logout or SAML SLO as "CAS SLO": **different protocols have different logout messages, correlations, and trust rules**.

## 5. Configuring SLO on the CAS Server: per-service scope

Apereo CAS allows configuring Single Logout per **registered service**. Relevant settings vary by version:

| Aspect | What must be verified |
| --- | --- |
| Does CAS Server enable SLO? | Some releases enable it by default; do not guess from UI—check runtime and service registry. |
| **`logoutType`** | `BACK_CHANNEL`, `FRONT_CHANNEL`, or disabled (`NONE`/equivalent depending on version). |
| **`logoutUrl`** | Can target an endpoint distinct from the `service` used when issuing STs; must be configured explicitly and tested. |
| **Logout propagation** | Async/sync, thread pools/queues/retries, and ordering; never rely on an assumed SLA. |
| Front-channel mode | JSONP/AJAX/iframe and client/browser support. |
| Service registry | ST must belong to a registered service, with public HTTPS URLs matching proxies/ingress. |
| CAS SSO session lifecycle | Explicit logout, TGT expiration, idle timeout, global logout policy. |
| Upstream federation | If CAS acts as an OIDC/SAML broker, each protocol has its own logout logic. |

Condensed **service registration example on CAS Server**:

~~~json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://portal[.]example[.]org/login/cas$",
  "name": "portal",
  "id": 1001,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://portal.example.org/login/cas"
}
~~~

**This is illustrative JSON**; schema, regex escaping, `@class`, and field values must be verified against your **running CAS Server version and service registry implementation**. Never copy directly to production CAS or assume all releases accept the exact same structure. If using a dedicated `logoutUrl`, that endpoint must route to the SLO filter/handler, **not** merely an HTML "logout successful" page.

### 5.1. Back-channel: suited to server-side services yet no absolute delivery guarantee

**Back-channel SLO** sends a direct POST from the CAS Server to the service, independent of whether the user still has the service tab open or allows third-party browser cookies. However, it depends on **network, DNS, TLS certificates, service availability, firewalls, endpoint authentication, message parsing, mapping storage, and the internal session store**.

The CAS Server can dispatch notifications **asynchronously** and ignore delivery errors to avoid slowing CAS logout. Thus **CAS `/logout` HTTP 200 does not prove B received the callback**. Collect per-service metrics/delivery outcomes and verify with an actual request carrying the old session cookie.

### 5.2. Front-channel: watch browsers and CSP/iframes

**Front-channel SLO** relies on the browser to relay/receive notifications, via AJAX JSONP or iframes depending on CAS Server. It can be disrupted by **browser privacy settings, CSP, third-party cookie policies, mixed content, network drops, closed tabs**, or unsupported clients. Never assume front-channel is "stronger" just because the browser sees more pages; test across modern browsers and client versions.

For pure server-side Spring Security services, **back-channel** is usually easier to observe; front-channel fits only when requirements and deployment genuinely support it. Never confuse CAS front-channel with **OpenID Connect Front-Channel Logout** despite the similar name.

### 5.3. Condition of "having participated in the SSO session"

CAS normally knows only about services that **were issued an ST/recorded under the TGT**. An app may accept logins from local accounts bypassing CAS, another browser, or another IdP; CAS SLO **cannot automatically know about** or delete unrelated sessions.

Therefore baseline tests must verify A/B/C all logged in **under the same CAS TGT** against the right CAS Server, not merely the same username. Use a clean browser profile, clear prior test cookies, record identity correlation on the test server, and verify CAS audits issued distinct STs per service.

## 6. Designing the test: three services, one TGT, three local sessions

### 6.1. Preconditions

Prepare a **staging/test** environment with a CAS Server and three services A/B/C. Ensure:

1. Each service has a **public HTTPS URL** permitted by the CAS service registry.
2. CAS Server configures **SLO `BACK_CHANNEL`** (or the specific mode under test) for all three.
3. All three have CAS Client/Spring Security integration handling `logoutRequest`.
4. On each service, a protected endpoint such as `GET /private/whoami` returns **200 with user/session generation** when logged in, and **401/403** or **302 to CAS login** when not logged in. Never hard-assume 302 = logged out; inspect the redirect target.
5. Audits/metrics mask STs/cookies while revealing whether CAS called the service, the mapping was found, the session was invalidated, and subsequent requests still had access.
6. Use **the same browser profile** or automation with a single cookie jar for CAS and each service; do not wipe all cookies right before verifying sessions on each app.
7. Clocks are reasonably synchronized (NTP), with correlation IDs and timestamps for the test run.
8. Connectivity controls exist to simulate service B offline or high latency in this environment.

**Never run logout tests against real production users or organizations.** Test sessions must use authorized test accounts.

### 6.2. Initial state setup

~~~text
User: lan (same browser profile)
CAS TGT: TGT-1

Visit A -> CAS issues ST-A1 -> A validates -> HttpSession A-S1
Visit B -> CAS issues ST-B1 -> B validates -> HttpSession B-S1
Visit C -> CAS issues ST-C1 -> C validates -> HttpSession C-S1

Verify before logout:
  GET A/private/whoami with A cookie -> authenticated lan
  GET B/private/whoami with B cookie -> authenticated lan
  GET C/private/whoami with C cookie -> authenticated lan

Record privately:
  correlation test-run = slo-20261107-001
  A session generation (non-secret ref)
  B session generation
  C session generation
  CAS audit references for ST-A1/ST-B1/ST-C1 (hashed)
~~~

Do not put raw service tickets or `JSESSIONID` values in test reports; HMAC/hash references using a dedicated audit key suffice for correlation.

### 6.3. Triggering CAS logout properly

The test browser triggers CAS `/logout` via the registered mechanism, or an officially configured "Global Logout" button on A that redirects to CAS logout. If a post-logout redirect is used, it must target a CAS-allowed URL; never accept arbitrary `service=https://attacker.example` from clients.

The CAS Server destroys TGT-1 and dispatches notifications to A/B/C. Then:

- Verify **CAS TGT is truly invalidated**.
- Track **callback A**, **callback B**, and **callback C** individually; never conclude "all done" after seeing only A.
- Wait according to a **pre-defined test timeout/SLA**, rather than guessing 100 ms suffices for all async callbacks.
- Use **each service's old session cookie** to call protected endpoints with **auto-following login redirects disabled** so you measure authorization on the existing session.
- If an API auto-redirects through CAS and logs back in, distinguish **old session denied** from **new session issued**; in this test, since the TGT was destroyed, a new login normally requires primary authentication.

### 6.4. Acceptance criteria

| Check | PASS when |
| --- | --- |
| CAS TGT | TGT-1 is destroyed; no longer silently issues new STs via SSO from TGT-1. |
| SLO dispatch | CAS emits notifications for TGT-1's services A/B/C without omitting expected services. |
| Delivery | HTTP requests reach A/B/C's configured endpoints without 404/403/timeouts. |
| Session correlation | A receives ST-A1, B receives ST-B1, C receives ST-C1 in `SessionIndex`; never deletes by username. |
| Local invalidation | A-S1, B-S1, and C-S1 are invalidated or hold no valid authentication. |
| Authorization recheck | Using **old cookies** against protected resources at A/B/C **never returns 200 with old privileges**. |
| Zero out-of-scope impact | Sessions under **another TGT** or another user are not erroneously wiped by this SLO. |
| Evidence | Per-service audit documents dispatch, mapping, invalidation, access check, and verdict. |

**Specifically:** sometimes `/private/whoami` returns 200 from an **HTTP cache/service worker** after logout. Tests must set `Cache-Control: no-store` on protected endpoints, disable caching in the test client, and confirm the server processed the request rather than mistaking cached content for a live session. Conversely, a UI still showing a username does not by itself prove backend access remains alive.

## 7. Scenario matrix: local logout, CAS logout, single-service failure

| Scenario | CAS TGT | Session A | Session B | Session C | Verdict |
| --- | --- | --- | --- | --- | --- |
| Not logged out yet | ACTIVE | ACTIVE | ACTIVE | ACTIVE | Baseline. |
| Local logout at A only | ACTIVE | CLOSED | ACTIVE | ACTIVE | **Not SLO**. |
| Revisit A right after local logout | ACTIVE | May NEW LOGIN via CAS SSO | ACTIVE | ACTIVE | Verifies new session, not restoring old session. |
| CAS logout + SLO succeeds across all services | CLOSED | CLOSED | CLOSED | CLOSED | **SLO E2E PASS**. |
| CAS logout, B offline | CLOSED | CLOSED | May stay ACTIVE | CLOSED | **PARTIAL SLO**, needs alert/mitigation. |
| CAS logout, C lacks SLO filter | CLOSED | CLOSED | CLOSED | May stay ACTIVE | **PARTIAL SLO**, client/config defect. |
| CAS logout yet service registry `logoutType=NONE` on B | CLOSED | CLOSED | ACTIVE | CLOSED | B excluded from propagation per policy; fails system-wide logout goal. |
| CAS front-channel blocked by browser on C | CLOSED | CLOSED | CLOSED | May stay ACTIVE | Browser/client dependent; test separately. |
| CAS logout after session A already timed out | CLOSED | Already CLOSED | CLOSED | CLOSED | Callback A may miss mapping; idempotent/no-op, never deletes another user. |
| A and B share username yet different browsers/TGTs | TGT-1 CLOSED | TGT-1 sessions CLOSED | TGT-2 sessions remain ACTIVE | Scoped | Never log out by username. |
| CAS SLO receives duplicate callback | CLOSED | CLOSED | CLOSED | CLOSED | Duplicates must be safe without creating sessions. |
| CAS logout while API service uses independent JWT | CLOSED | Web session CLOSED | API JWT may stay valid | Policy dependent | SLO alone is insufficient for all bearer tokens. |

**This table represents expected test outcomes in the described architecture, not a guarantee that every CAS Server/Client release behaves identically by default.** Verify actual mode, protocol, service registry, session store, and logout policy.

### 7.1. Never confuse the two meanings of "service B returned 200"

A callback POST returning **HTTP 200** at B proves only that an endpoint handled or ACKed the request; it could be a 200 from a controller that never invalidated any session. Require proof that B located the exact ST, invalidated the session, and denied subsequent requests carrying B's old cookie. If the callback endpoint returns 200 on a mapping miss, log `NO_MATCH`/metric and evaluate it rather than equating it with `INVALIDATED`.

## 8. Runnable Java 17: simulating four sessions and one lost callback

The program below uses **pure Java 17**, simulating three services A/B/C plus a second session at A. It shows that local logout at A leaves B/C untouched, CAS SLO for the same TGT must target the **exact ST**, and B being offline produces a **partial logout** until B processes the notification.

**Example boundary:** `receiveSlo` is invoked **only after** a real CAS Client/Filter has authenticated the message origin at the transport/trust layer and extracted `SessionIndex`. The program generates no real tickets, parses no XML, authenticates no CAS Server, and uses no `HttpSession` or CAS filters. `ST-...` strings are dummy identifiers illustrating mappings.

File **`CasMultiServiceLogoutDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CasMultiServiceLogoutDemo {

    record LocalSession(String id, String username) {}

    static final class Service {
        private final Map<String, LocalSession> byTicket =
                new HashMap<>();
        private final Map<String, String> ticketBySession =
                new HashMap<>();

        synchronized void login(String serviceTicket,
                                String localSessionId, String username) {
            if (byTicket.containsKey(serviceTicket)
                    || ticketBySession.containsKey(localSessionId)) {
                throw new IllegalStateException("Duplicate mapping");
            }
            byTicket.put(serviceTicket,
                    new LocalSession(localSessionId, username));
            ticketBySession.put(localSessionId, serviceTicket);
        }

        synchronized void localLogout(String localSessionId) {
            String ticket = ticketBySession.remove(localSessionId);
            if (ticket != null) {
                byTicket.remove(ticket);
            }
        }

        // Trusted CAS client calls after extracting SessionIndex.
        synchronized String receiveSlo(String serviceTicket) {
            LocalSession session = byTicket.remove(serviceTicket);
            if (session == null) {
                return "NO_MATCH";
            }
            ticketBySession.remove(session.id());
            return "INVALIDATED";
        }

        synchronized boolean active(String localSessionId) {
            return ticketBySession.containsKey(localSessionId);
        }
    }

    public static void main(String[] args) {
        Service a = new Service();
        Service b = new Service();
        Service c = new Service();

        // TGT-1: one browser logged in across A, B, and C.
        a.login("ST-A1", "A-S1", "lan");
        b.login("ST-B1", "B-S1", "lan");
        c.login("ST-C1", "C-S1", "lan");

        // TGT-2: another browser, same username yet separate session at A.
        a.login("ST-A2", "A-S2", "lan");

        System.out.println("BEFORE="
                + (a.active("A-S1")
                   && b.active("B-S1")
                   && c.active("C-S1")));

        // Logout at A only: CAS TGT-1 and B/C remain active.
        a.localLogout("A-S1");
        System.out.println("LOCAL=" + a.active("A-S1")
                + "," + b.active("B-S1")
                + "," + c.active("C-S1"));

        // A can re-login via surviving CAS SSO TGT-1.
        a.login("ST-A3", "A-S3", "lan");
        System.out.println("SSO_RELOGIN=" + a.active("A-S3"));

        // CAS destroys TGT-1, dispatches callbacks to A and C first.
        // B is offline; CAS callback to B is not yet processed.
        System.out.println("SLO_A=" + a.receiveSlo("ST-A3"));
        System.out.println("SLO_C=" + c.receiveSlo("ST-C1"));
        System.out.println("PARTIAL=" + a.active("A-S3")
                + "," + b.active("B-S1")
                + "," + c.active("C-S1"));

        // Assume retry/reconciliation eventually delivers notification to B.
        System.out.println("B_RECOVERY=" + b.receiveSlo("ST-B1"));
        System.out.println("B_DUPLICATE=" + b.receiveSlo("ST-B1"));

        // Independent TGT-2: same user is not destroyed by username.
        System.out.println("OTHER_BROWSER=" + a.active("A-S2"));

        // One service must never consume another service's ST.
        System.out.println("WRONG_SERVICE=" + a.receiveSlo("ST-B1"));
    }
}
~~~

Run:

~~~bash
javac CasMultiServiceLogoutDemo.java
java CasMultiServiceLogoutDemo
~~~

**Exact stdout:**

~~~text
BEFORE=true
LOCAL=false,true,true
SSO_RELOGIN=true
SLO_A=INVALIDATED
SLO_C=INVALIDATED
PARTIAL=false,true,false
B_RECOVERY=INVALIDATED
B_DUPLICATE=NO_MATCH
OTHER_BROWSER=true
WRONG_SERVICE=NO_MATCH
~~~

Explanation:

1. One CAS TGT supports sessions across **three services**.
2. Local logout at A destroys only `A-S1`, while B/C stay `ACTIVE`.
3. The surviving CAS TGT allows A to acquire a new login `ST-A3` (simulated).
4. When CAS SLO reaches only A/C, B remains active: **partial logout**.
5. When B actually receives its notification, `B-S1` is destroyed; a duplicate `ST-B1` callback returns **NO_MATCH** and does nothing further.
6. Session `A-S2` under another TGT yet the same username stays active, proving **no username-based logout**.
7. A does not accept `ST-B1` as its own session.

**Warning:** `B_RECOVERY` simulates a **notification eventually reaching B**. Never assume the CAS Server definitely retries or maintains a durable queue by default; retry/async behavior depends on CAS Server and deployment. **Production systems must plan** monitoring, controlled retries/reconciliation, or SLA-aligned timeouts/revocation. The demo's `HashMap` does not represent real `HttpSession`, networking, auth, token revocation, or TTL, and must not be used in production.

### 8.1. Why not destroy by username?

Two browser profiles may both belong to `lan` yet hold **TGT-1** and **TGT-2**. SLO for TGT-1 sends only ST IDs belonging to that TGT; wiping every `lan` session across A/B/C would log out TGT-2 as well, violating boundaries. Some organizations enforce **global account revocation** (locking a user out across all devices); that is a **separate policy** requiring authenticated signals and dedicated enforcement, never impersonating default CAS SLO.

### 8.2. Limits of what a unit test proves

The program proves only the mapping algorithm; it does not prove:
- CAS Server sent `logoutRequest` to the right service.
- XML/transport was validly verified by the CAS Client.
- `SingleSignOutFilter` actually sits before the Spring Security chain.
- Session fixation rotation and session stores still support accurate lookups.
- Callback HTTP 200 corresponds to real session invalidation.
- Old browser cookies lost access.
- Partial SLO is detected accurately across a multi-node network.

You need **integration tests + browser/E2E tests** as detailed in the next sections.

## 9. End-to-end testing: reliable observation methods

### 9.1. With browser automation

Use Playwright/Selenium or a real browser with a single browser context holding the CAS cookie and service cookies. Suggested test flow:

~~~text
1. Login to A via CAS -> GET A/private -> 200 authenticated
2. Visit B            -> GET B/private -> 200 authenticated
3. Visit C            -> GET C/private -> 200 authenticated

4. Snapshot:
   A local session ref, B session ref, C session ref
   CAS ST correlation references; TGT test reference

5. Browser performs CAS /logout.
6. Collect:
   CAS dispatch events to A/B/C,
   A/B/C callback status,
   A/B/C session-invalidation events.

7. Reuse ORIGINAL service cookies:
   A/private -> no old authentication
   B/private -> no old authentication
   C/private -> no old authentication

8. Verify protected WRITE endpoints also reject old state.
9. Verify browser with independent TGT/session is unchanged.
~~~

Be careful with "reuse original cookies": the browser still holds cookies while the server should have invalidated the sessions—that is what we are testing. Never clear all local cookies before step 7, because then "no longer authorized" only proves **the client deleted cookies**, not that CAS SLO invalidated server sessions.

### 9.2. Interpreting 401/403/302 responses

| Response when calling a protected resource | Interpretation |
| --- | --- |
| **401** | Caller is unauthenticated to the API; usually consistent with the old session being gone. |
| **302 to CAS login** | Spring web app treats caller as anonymous and requests re-login; usually consistent with logout, **yet verify it does not auto-SSO back in**. |
| **403** | May mean authenticated yet lacking role, or CSRF/authorization failure; do not automatically treat as logout. |
| **200 from protected endpoint** | Check whether it is a real server response and whether the identity belongs to the **old session** or a new session. |
| **200 from `/logout-success` page** | Confirms UI only; proves nothing about A/B/C session destruction. |
| **304/200 from cache** | May be stale cached data; disable caching and check server-side. |

A `GET /private` returning 302 is a **signal**, not complete proof. For audit-verification endpoints, prefer returning 200 with a non-sensitive **test-only session generation** or returning 401 from an API so old vs. new sessions are distinguishable.

### 9.3. Testing concurrent requests when callbacks arrive late

Issue a request to B at the exact moment CAS is dispatching SLO:

- A request to B starting **before** B's session invalidation commits may finish under the old privileges unless an in-flight cancellation mechanism exists.
- A request to B starting **after** session invalidation commits must hold no privileges from the old B session.
- If the business case demands **immediate revocation across in-flight requests**, CAS SLO alone is insufficient. Use a **revocation epoch**, checks at critical operations, or an API-enforced session registry.

Never impose unrealistic requirements like "every request already running before logout must roll back" unless the system has explicit transactional/revocation semantics.

## 10. Testing partial failures and limits of "best effort"

### 10.1. Service B offline

Scenario:

1. A/B/C all share TGT-1.
2. Before CAS logout, make B unreachable or block CAS → B traffic in staging.
3. CAS receives logout, sends callbacks to A/C successfully, and fails on B.
4. CAS TGT is destroyed.
5. Test B with the old cookie once B comes back online; without compensating controls, B-S1 may stay active until session timeout.

**This is a crucial test**, proving CAS logout is **not atomic across services**. Never mark the overall system PASS merely because A and C succeeded. Define business RTO/RPO for session revocation and apply **mitigations** such as short session TTLs, forced reauthentication on sensitive apps, versioned session invalidation/revocation, online introspection, or delivery reconciliation.

### 10.2. Front-channel blocked

Test with browsers enforcing strict CSP/third-party-cookie/tracker protection, closing tabs early, or disabling JavaScript. If CAS sends front-channel yet the client cannot process it, C can retain its session. Do not blame `HttpSessionMappingStorage` when the root cause is the callback never arriving. Inspect DevTools network traces + CAS dispatch logs alongside backend session state.

### 10.3. Lost listener/session mapping

Configure CAS client filter and listener matching your dependency/version:

- Confirm that at ST login **it maps to the live `HttpSession`**.
- Verify the mapping disappears on session timeout or local logout.
- Verify `SingleSignOutFilter` finds the right mapping when `SessionIndex=ST-A1`.
- If the mapping misses, record a reason code—never pick the "nearest" session or log out the entire username.
- After deploys/failovers, if mappings lived only in the old JVM's RAM, the service cannot destroy sessions on new nodes.

CAS clients ship default in-memory implementations; when deploying multi-node or with Spring Session, evaluate **distributed session mapping storage compatible with your client/container version**. Never assume sticky sessions suffice when callbacks are separate requests from the CAS Server carrying no browser cookies.

### 10.4. Service `logoutType=NONE`

If the service registry disables SLO for B, B legally stays active per **current configuration**. When the test requirement is "every app must log out", mark it **fails system requirements**, while recording the root cause as **service registry policy** rather than a broken filter. Distinguish **business expectations** from **configured runtime state**.

## 11. Testing multiple devices and multiple sessions on the same service

### 11.1. Same user, two independent CAS sessions

Suppose:

~~~text
Browser-1 / TGT-1 (user=lan):
  A ST-A1 -> A-S1
  B ST-B1 -> B-S1

Browser-2 / TGT-2 (user=lan):
  A ST-A2 -> A-S2
  B ST-B2 -> B-S2

Logout at Browser-1:
  CAS destroys TGT-1
  SLO A for ST-A1 -> A-S1 invalidated
  SLO B for ST-B1 -> B-S1 invalidated

Must NOT automatically invalidate:
  A-S2, B-S2 (belong to TGT-2)
~~~

This test confirms SLO **targets ST-bound sessions**, not usernames/emails. If an organization wants "log out of all devices", a separate **global logout** mechanism with explicit authentication and revocation rules is required; CAS SLO for a single TGT does not provide that by itself.

### 11.2. Multiple tabs in one browser

Tabs of the same origin typically share **the same local session cookie**. When CAS SLO invalidates A-S1, any tab of A sending the old cookie loses valid Authentication. However, an old tab's UI may still display previously rendered data—which differs from backend access. For SPAs, update UX via `BroadcastChannel`/events/state polling to avoid stale UI state, yet **never trust JS alone to prove a session is active or dead**.

### 11.3. One service holding multiple sessions from re-login

If the user performs local logout on A and re-SSOs before CAS logout, A may have had ST-A1 (old session already deleted) and ST-A2 (new session). CAS may have recorded multiple service tickets under the TGT; a notice for the old ST is a no-op once cleaned up, whereas the notice for the new ST must destroy the **live session**. Never destroy A's new session merely because it matches the old ST's username.

## 12. Preventing spoofing and replay of logoutRequest

Back-channel requests can affect other users' sessions, making the SLO endpoint sensitive. Make sure to:

1. **Never blindly accept any XML POST** with a `SessionIndex` field and directly call `session.invalidate()`.
2. Use **Apereo Java CAS Client `SingleSignOutFilter`** or a handler tested against the exact CAS protocol/version.
3. Protect the back-channel origin via **HTTPS, network/gateway ACLs, mTLS if appropriate and supported, and rate limiting**, never merely an arbitrary HTTP header.
4. Pin `service` and endpoints configured on the CAS Server; never let users supply callback URLs/issuers.
5. Harden XML parsers against **XXE/entity expansion**; prefer standard library parsers on patched releases.
6. Duplicate callbacks carrying the same `SessionIndex` must be **idempotent**: once the session is gone, never delete another session.
7. Never treat `NameID` as a key to find all user sessions when handling CAS SLO for a specific ST.
8. Never disable CSRF across all endpoints just because CAS SLO POSTs lack browser CSRF tokens; if an exemption is needed, exempt **only the exact CAS `logoutRequest` endpoint/path**, paired with origin-trust controls.
9. Never log raw `logoutRequest`/tickets/session cookies/PII; use correlation hashes and audit outcomes.
10. Enforce XML request size limits, timeouts, concurrency bounds, and DoS protections.

**CAS back-channel messages resemble SAML LogoutRequests yet do not inherently carry a SAML XML signature.** When policy requires authenticated logout delivery, enforce appropriate channel and CAS Server origin constraints. Never weaken trust merely to get "more apps logged out" in tests.

### 12.1. SLO listener and session lifecycle

`SingleSignOutHttpSessionListener` cleans up mappings when sessions expire or are destroyed, yet **does not send SLO to other apps itself**; dispatch belongs to the CAS Server. A missing listener lets old mappings linger, causing memory leaks and false mappings. A missing filter can yield callback 200/404 responses while local sessions remain intact. Test both components separately.

## 13. Spring Boot Servlet integration: structuring tests

Conceptual component layout:

~~~text
Servlet filter order:
  CharacterEncodingFilter (UTF-8 when needed)
  Apereo SingleSignOutFilter
  Spring Security FilterChainProxy (CAS auth and authorization)
  ...
Servlet session listener:
  SingleSignOutHttpSessionListener

Spring Security:
  CasAuthenticationEntryPoint
  CasAuthenticationFilter (/login/cas)
  CasAuthenticationProvider + TicketValidator
  SecurityContextRepository
  local LogoutFilter (/logout)

CAS Server:
  /logout
  service registry A/B/C with correct logoutType, logoutUrl
  SLO transport/dispatch and service ticket correlation
~~~

This is an **architecture diagram**, not a runnable config file. Exact filter ordering depends on your Spring Boot/Servlet deployment and CAS Client version and must be verified with integration tests. Never place two `SingleSignOutFilter` instances in both the container and Spring chain processing the same request.

### 13.1. Registration example in Spring Boot

Sample showing how to register the CAS SLO filter + listener in a version-compatible Servlet stack:

~~~java
package example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSingleLogoutConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> singleSignOutFilter() {
        FilterRegistrationBean<SingleSignOutFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new SingleSignOutFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            singleSignOutListener() {
        ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
                registration = new ServletListenerRegistrationBean<>();
        registration.setListener(new SingleSignOutHttpSessionListener());
        return registration;
    }
}
~~~

**Note:** the fragment above requires **compatible Spring Boot Servlet, `spring-security-cas`, and Apereo Java CAS Client**, full filter/protocol config, and a real CAS Server. `Ordered.HIGHEST_PRECEDENCE` illustrates **the need to run early**, not that it is always right in every filter stack. Measure actual filter ordering, verify UTF-8 encoding, exception handling, `LogoutFilter`, access logs, and CAS callbacks. Test configurations before choosing a production order. If already registered via `web.xml` or auto-configuration, do not create duplicates.

### 13.2. Configuration errors to avoid

| Error | Outcome |
| --- | --- |
| SLO filter mapped only to local `/logout`. | Misses login ticket callbacks and CAS `logoutRequest`. |
| CAS Server POSTs to `/login/cas` yet reverse proxy permits only GET. | CAS callback gets 405/403; local session stays alive. |
| Spring CSRF blocks SLO POST before the filter. | Fails to invalidate session. |
| Spring Boot auto-config adds a second filter. | Duplicate handler/inconsistent mappings. |
| Missing `SingleSignOutHttpSessionListener`. | Mappings never cleaned up when `HttpSession` expires. |
| Local session ID rotates yet mapping keeps stale reference. | SLO arrives for right ST yet destroys wrong/no live session. |
| `SingleSignOutFilter` on node A while session is on node B. | Needs shared session/mapping rather than sticky cookies. |
| Service `logoutUrl` points to a notification page bypassing SLO filter. | HTTP 200 yet session is not invalidated. |
| CAS Server/ticket validator mismatched across environments (staging/prod). | Wrong ST correlation or trust; breaks SLO. |

## 14. Observing per-service state and QA reporting

With multiple services, SLO test reports **must include a separate row for each session**. Example:

| Service | ST ref | Local session ref | Callback received | Mapping found | Invalidation | Old-cookie test | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | HMAC(ST-A1) | A-S1-ref | YES | YES | YES | DENIED | PASS |
| B | HMAC(ST-B1) | B-S1-ref | YES | YES | YES | DENIED | PASS |
| C | HMAC(ST-C1) | C-S1-ref | NO | N/A | NO | STILL ACTIVE | **FAIL** |

In this example, **the overall test must be FAIL/PARTIAL**; you cannot declare success just because A and B passed. If service C does not require SLO per business contract, "out of scope" must be **defined upfront**, never dropped after a test fails.

### 14.1. What should logs/audits capture?

Suggested event fields (custom-defined, **not default logs** of Spring/CAS):

~~~text
event=CAS_SINGLE_LOGOUT
test_run=slo-20261107-001
timestamp=2026-11-07T04:00:00Z
cas_server_ref=cas-primary
service_ref=reports-b
service_ticket_ref=HMAC(ticket-id)
local_session_ref=HMAC(session-id)
callback_transport=BACK_CHANNEL
callback_received=true
session_mapping_found=true
session_invalidated=true
old_cookie_protected_request=DENIED
result=PASS
~~~

Never put plain STs, TGTs, `JSESSIONID`, usernames, raw `logoutRequest`, or private tokens into broadly readable logs. To correlate events, use **HMAC with a dedicated audit secret** instead of a short guessable hash. Define retention/ACLs and alert on error rates.

### 14.2. Operational metrics

Suggested metrics:

~~~text
cas_slo_dispatch_total{service,channel,outcome}
cas_slo_callback_received_total{service}
cas_slo_mapping_found_total{service}
cas_slo_mapping_missing_total{service}
cas_slo_session_invalidated_total{service}
cas_slo_callback_error_total{service,reason}
cas_slo_latency_seconds{service}
cas_slo_delivery_queue_depth
cas_local_session_active_after_slo_total{service}
cas_slo_replay_noop_total{service}
~~~

Never put `username`, raw STs, or session cookies into metric labels due to **cardinality** and sensitivity. Monitor both the CAS Server (dispatch/delivery) and services (mapping/invalidation). One side may report "delivery 200" while invalidation failed on the other; therefore measure E2E metrics, **not just HTTP status codes**.

## 15. Comprehensive test matrix

| Test case | Expected outcome |
| --- | --- |
| Single service A, CAS logout, back-channel succeeds. | A's old session loses access. |
| A/B/C under one TGT, all active. | All three lose access after SLO completes. |
| Local logout at A while B/C stay active. | B/C and CAS TGT are not destroyed by default. |
| A local logout then revisit while CAS TGT remains. | Can SSO-login into **a new session**; never reuses old session. |
| CAS logout while B is offline. | A/C destroyed; B may stay active; test records **PARTIAL** and alerts. |
| CAS callback to B arrives late. | B destroys exact session on valid callback; never kills a newer session. |
| Repeated CAS callback for the same ST. | Idempotent no-op; never kills another session. |
| CAS `SessionIndex` has wrong ST. | Mapping not found; never deletes by username. |
| CAS `NameID` matches real user yet wrong ST. | Never destroys user's session by `NameID`. |
| CAS back-channel POST misses filter. | Test FAILS with routing/ordering diagnosis. |
| Receiver returns HTTP 200 without invalidating. | E2E FAIL despite transport 200. |
| Session mapping lost after node restart. | Caught by no-match/old-cookie test; no false PASS. |
| A/B/C run multi-node/shared session store. | Every callback can locate/destroy the exact local session. |
| CAS Server picks `FRONT_CHANNEL` while C lacks support. | Must detect C stayed active; never assume compatibility. |
| Browser closes tab before front-channel. | Evaluate lost delivery and compensating policy. |
| One user, two TGTs across two browser profiles. | TGT-1 SLO does not auto-destroy TGT-2 sessions. |
| One user, multiple tabs sharing one local session. | All tabs lose backend privileges on the old session. |
| A already timed out before CAS logout. | SLO at A can no-op; creates no new session. |
| SSO TGT expires by idle timeout. | Verify CAS policy on emitting SLO rather than inferring from explicit logout. |
| C uses JWT access tokens. | CAS SLO does not auto-revoke JWTs; test revocation/TTL separately. |
| Browser cache holds old page. | Protected backend request is blocked; stale UI identified separately. |
| Spoofed `logoutRequest` callback. | Untrusted origin cannot destroy sessions; parser/ACL prevents injection. |
| Oversized/XXE XML callback. | Safely rejected without exhausting resources. |
| Service registry missing B. | SLO not sent to B; test FAILS against A/B/C requirement. |
| `logoutType=NONE` on B. | B outside propagation; do not mark B logged out. |
| Wrong service `logoutUrl`. | Detect 404/302/fake 200; fix registry. |
| Spring Security session ID rotation at login. | `ST → session` mapping still serves SLO properly. |
| Local account DISABLED mid-session. | Authorization must deny per policy independently of SLO. |
| Service gets logout during in-flight request. | Verify revocation semantics on critical ops; never assume auto-rollback. |
| CAS logout yet browser auto-logins because upstream IdP stays active. | Distinguish new session via identity/session generation; check upstream logout contract. |

A system must test both **happy paths** and **lost notifications/delays/races**. Testing only "click logout and see the login page" easily misses B and C still holding valid sessions.

## 16. Layered troubleshooting

| Symptom | Common root cause | Inspection step |
| --- | --- | --- |
| CAS logged out yet A/B/C all stay active. | SLO disabled, wrong service registry, callbacks never arrive. | Inspect CAS dispatch events and `logoutType`. |
| Only A logs out, not B/C. | Local logout at A without redirecting to CAS `/logout`. | Compare "local" vs. "global" logout buttons. |
| CAS dispatches to A yet nothing reaches A. | Wrong DNS/firewall/TLS/gateway/ingress. | Inspect network logs and URLs. |
| CAS POST to A returns 403. | Blocked by Spring Security/CSRF or WAF. | Permit exact SLO path with transport trust; never disable CSRF site-wide. |
| CAS POST to A returns 404/405. | Wrong `logoutUrl`, GET-only route, wrong filter mapping. | Compare service registry and Servlet filters. |
| CAS POST to A returns 200 yet A-S1 stays active. | Handler ACKed without invalidation; mapping missed. | Inspect `ST → HttpSession` and protected old-cookie calls. |
| SLO fails only when session ID rotates. | Session fixation rotation/stale mapping. | Check session strategy and listener/CAS client version. |
| SLO fails after rolling deploy. | In-memory session mapping stuck on old node. | Shared store, lifecycle/failover, CAS client compatibility. |
| SLO logs out all devices of the same user. | Deleted by username instead of ST/TGT scope. | Fix correlation and test with 2 browsers. |
| Duplicate callback throws 500. | Non-idempotent handler when session already gone. | Safe no-op on missing mapping, audit. |
| Front-channel fails in one browser. | CSP/cookie restrictions/iframe blocking/unsupported client. | Browser network traces + test other mode; never assume universal support. |
| Browser tab still displays data. | Stale cached UI/SPA state. | Call uncached protected server endpoint. |
| API JWT still works after SLO. | Independent stateless token not revoked. | Design token expiry, revocation/introspection/`securityVersion`. |
| CAS TGT destroyed yet browser auto-SSOs right back. | Upstream IdP still logged in and CAS broker re-authenticates. | Distinguish CAS vs. upstream sessions. |
| One service receives no SLO per registry. | `logoutType=NONE` or service unrecorded under TGT. | Check policy/business requirements. |

**Debugging sequence:** (1) verify same TGT and A/B/C logged in → (2) did CAS logout destroy TGT → (3) did CAS record/deliver per-service SLO → (4) did endpoint receive it → (5) did filter parse `SessionIndex` → (6) did `ST → HttpSession` mapping hit → (7) did invalidation succeed → (8) does old-cookie protected access still work?

## 17. Designing compensating controls when best-effort SLO is not enough

SLO improves UX consistency and shrinks session lifetimes, yet should never be the **sole control** when sensitive operations demand instant revocation. Controls:

1. **Reasonable session timeouts** and absolute timeouts for sensitive apps, rather than relying indefinitely on surviving cookies.
2. **Forced reauthentication** for high-risk actions: CAS `renew` or agreed step-up/assurance mechanisms; never equate `renew` alone with MFA.
3. **Local account status/entitlement rechecks**: revoked/disabled accounts must be blocked immediately or within defined SLAs.
4. **Distributed session registry/revocation version** if global logout or revoking all sessions for an account is required by separate policy.
5. **Short token TTLs, introspection/revocation** for independent API access tokens; JWTs are not automatically invalidated when a CAS `HttpSession` is deleted.
6. **Reliable audits + alerts** when CAS SLO dispatch/delivery/invalidation diverge, especially for financial/admin services.
7. **Idempotent callbacks** and safe state persistence; never retry spent STs to patch SLO.
8. **Fail-safe policy** when a service cannot reach CAS: sensitive apps require reauth or deny rather than silent indefinite fail-open.
9. **Device/session visibility**: provide UI showing users which sessions may remain active if required by enterprise policy; never claim "logged out everywhere" simply on CAS 200.
10. **OIDC/SAML broker boundary**: use matching logout profiles/tokens rather than assuming CAS `logoutRequest` reaches all upstream/downstream relying parties.

**A realistic design** may accept best-effort SLO for low-sensitivity apps while enforcing explicit **revocation SLAs** for admin/finance. Never expect the CAS Server to treat every service like a distributed ACID transaction, because CAS SLO is a notification protocol.

## 18. Common mistakes

1. **"CAS `/logout` returned 200, so A/B/C are all logged out."** False: prove session termination at each service.
2. **"Clicking logout in A logs out all of CAS."** False if A only clears its local session.
3. **"A user has only one HttpSession across all of CAS."** False: each service, browser, and device has its own session.
4. **"CAS LogoutRequest `SessionIndex` is `JSESSIONID`."** False: in CAS SLO it is normally the **ST ID**.
5. **"Using `NameID`/username to delete all sessions is proper CAS SLO."** False: can wipe another TGT mistakenly.
6. **"Callback HTTP 200 proves the mapping was destroyed."** False: verify local invalidation and old-cookie access.
7. **"Back-channel definitely reaches every service and never fails."** False: SLO is best-effort with timeouts/async/queues.
8. **"Front-channel works in every browser."** False: CSP, iframes, privacy/cookie restrictions, and client support vary.
9. **"Mapping the SLO filter only to local `/logout` is enough."** False: it must observe ST logins and CAS SLO callbacks.
10. **"No session listener is needed."** False: mapping cleanup is vital to the lifecycle.
11. **"Sticky sessions always route back-channel to the right pod."** False: callbacks carry no browser cookie and can hit another node.
12. **"Missing `logoutRequest` means delete sessions by user."** False: fail closed on unverified data.
13. **"SLO is identical to SAML 2.0 signed Single Logout."** False: CAS uses similar XML yet a different protocol/trust model.
14. **"CAS SLO immediately deletes API JWT access tokens."** False when the API manages its own tokens/authorization.
15. **"The tab still showing a profile proves SLO failed."** Not necessarily: UI may be cached; call the server.
16. **"Old-cookie request returning 302 always proves SLO passed."** Insufficient if redirect/auto-login creates a new session; audit generations.
17. **"Retrying the same ST verifies logout."** False: STs are single-use; test with protected resources/correlation.
18. **"TGT-1 SLO should wipe all devices for that username."** False unless a separate global logout policy exists.
19. **"CAS logout means the upstream IdP also logged out."** False if CAS acts as a broker and the upstream session survives.
20. **"A service being offline during SLO doesn't matter because CAS logged out."** False: local sessions on that service may stay valid.

## 19. Pre-production acceptance checklist

1. Were A/B/C logged in under **the same CAS TGT** in tests, each holding its own local session?
2. Does the CAS service registry explicitly specify **`BACK_CHANNEL`/`FRONT_CHANNEL`/`NONE`** per service?
3. Do `logoutUrl`/service URLs use public HTTPS endpoints reaching where `SingleSignOutFilter` runs?
4. Are `SingleSignOutFilter` and `SingleSignOutHttpSessionListener` present with proper filter ordering?
5. Is the **ST ID → HttpSession** mapping recorded at login and found on SLO?
6. Did you test session fixation ID changes, local logout before CAS logout, and session timeouts?
7. Did you test CAS SLO destroying A/B/C after one browser actively used all three?
8. Did you verify using **original service cookies** and protected endpoints rather than UI/HTTP 200 alone?
9. Did you test service B offline/timed out and classify partial logout properly?
10. Did you test two CAS sessions sharing a username across two browser profiles without deleting the other TGT?
11. Did you test duplicate `logoutRequest`, wrong `SessionIndex`, and malformed/forged XML?
12. Does the callback enforce HTTPS, inbound source restrictions, XXE-safe parsing, and properly scoped CSRF exemptions?
13. Do multi-node deployments have consistent session stores/mappings without relying on local RAM?
14. Are per-service audits captured for dispatch, delivery, mapping, invalidation, and old-cookie verification?
15. Are SLAs for partial SLO handling and session timeout/revocation controls defined for sensitive services?
16. For SPAs/API JWTs, is there a dedicated logout/revocation design?
17. Is CAS protocol SLO clearly distinguished from OIDC/SAML downstream/upstream logout?
18. Is documentation clear on local vs. CAS vs. system-wide policies and user guidance to avoid misconceptions?

## 20. Knowledge self-check

1. **Why can service B remain active after the CAS TGT is destroyed?** — Because B holds an independent local session; SLO delivery or invalidation can fail.
2. **What is the difference between local logout and CAS logout?** — Local destroys only the service's session; CAS logout destroys the CAS SSO session.
3. **Who sends SLO callbacks to A/B/C?** — The CAS Server under the CAS protocol, per registered service policy.
4. **What does `SessionIndex` in CAS `logoutRequest` usually point to?** — The **service ticket ID** issued to that service.
5. **Why not look up sessions by username?** — One user may have multiple TGTs/sessions; doing so risks destroying the wrong session.
6. **What does `SingleSignOutFilter` do?** — Handles logout notifications and `ST → session` mapping per CAS Client.
7. **What is `SingleSignOutHttpSessionListener` for?** — Cleans up session mappings when sessions are destroyed or expire.
8. **What is the most important E2E evidence?** — Protected requests carrying **old cookies** at every service no longer retain access after SLO completes.
9. **If SLO succeeds on A/C while B is offline, is that a PASS?** — No if the requirement covers all of A/B/C; that is a partial logout.
10. **Does back-channel CAS need the browser to have tab B open?** — No; the CAS Server sends a server-to-server request.
11. **What can disrupt front-channel CAS?** — Browser/CSP/iframe/cookie restrictions and client support.
12. **Does back-channel SLO using SAML-like XML carry a standard SAML2 signature by default?** — No; CAS transport/origin trust is required.
13. **If local logout on A followed by revisiting A logs right back in, is local logout broken?** — Not necessarily: the CAS TGT remains and issues a new ST for a new session.
14. **Same user holds TGT-1 and TGT-2; CAS logs out TGT-1—what happens to TGT-2?** — It is not automatically destroyed by TGT-1's CAS SLO.
15. **Do API access tokens expire immediately when CAS SLO destroys the HttpSession?** — Not automatically, unless revocation integration exists.
16. **How do you catch a fake HTTP 200 callback?** — Cross-check mapping found/session invalidated and run protected old-cookie tests.
17. **Why does session fixation protection relate to SLO?** — Session IDs can rotate after login; the `ST → live session` mapping must stay accurate.
18. **What compensating policies help when a service misses SLO?** — Session TTLs, forced reauth, revocation/active status checks, monitoring, and SLAs.

## References

- [Apereo CAS — Logout and Single Logout (CAS protocol, BACK_CHANNEL/FRONT_CHANNEL, service registry)](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html)
- [Apereo CAS — CAS Protocol Specification, /logout and Single Logout](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — Security Guide: SLO is best-effort, compensating controls](https://apereo.github.io/cas/development/planning/Security-Guide.html)
- [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — SingleSignOutFilter and SingleSignOutHttpSessionListener](https://github.com/apereo/java-cas-client)
- [Apereo CAS — SSO Session Services & Applications](https://apereo.github.io/cas/development/authentication/Configuring-SSO-Services.html)
- [Spring Security — Session Management and session fixation protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Logout, Servlet applications](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
