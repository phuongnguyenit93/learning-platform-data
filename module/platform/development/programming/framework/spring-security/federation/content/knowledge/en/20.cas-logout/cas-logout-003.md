# Mapping Service Tickets to Application Sessions to Handle CAS Logout Notifications

## 1. Problem: CAS logged out, yet the Spring application still has an active session

An employee logs in to a Spring Boot application via the **CAS Protocol**. The CAS Server issues a **Service Ticket (ST)**, the browser carries the ticket back to the application, and the application validates the ticket against the CAS Server and creates an `Authentication` and `HttpSession`.

Later, the user clicks **Log out of CAS**. The CAS Server can destroy the user's centralized login session and send a **Single Logout (SLO) notification** to participating services. However, the Spring application holds one or more `HttpSession` instances of its own. How does the CAS client know **exactly which session** to destroy when it receives a logout notification?

The answer in CAS Protocol Single Logout is: **maintain a mapping from the Service Ticket used during authentication to the application session created or bound during that authentication**. CAS SLO sends back the ticket identifier; the application uses that identifier to look up and invalidate the corresponding session. Without the mapping, CAS may have logged out successfully while the application still holds the old authenticated session.

This lesson belongs to **Spring Security - federation → CAS Logout** and focuses specifically on **"Mapping Service Tickets to application sessions to handle logout notifications"**.

### After this lesson, you will be able to

1. Describe **CAS TGT/TGC**, **Service Ticket**, **HttpSession/SecurityContext**, and **SLO request** separately.
2. Diagram the flow of **login, storing ST → HttpSession, CAS back-channel logout, and session invalidation**.
3. Explain why `SessionIndex` in a CAS SLO message is the **CAS Service Ticket ID**, not `JSESSIONID`, and must not be confused with SAML Web Browser SSO session semantics.
4. Know the roles of **`org.apereo.cas.client.session.SingleSignOutFilter`**, **`SingleSignOutHttpSessionListener`**, **`SessionMappingStorage`**, and Spring Security CAS integration.
5. Distinguish CAS **back-channel POST** and **front-channel browser notification**, browser/cookie requirements, and client support.
6. Understand the limits of **in-memory** mapping when running across multiple pods/nodes and how to design session ID mapping on a distributed store.
7. Handle mapping cleanup on session expiration, local logout, user re-login, multiple tabs, and duplicate SLO notifications.
8. Analyze SLO callback security: spoofing/logout CSRF/DoS, caller origin protection, XML parser hardening, replay, and log redaction.
9. Run a **standalone Java 17** example simulating ST→Session and invalidating the exact session by ST without a servlet container.
10. Build a test plan verifying SLO from a real CAS Server to a running Spring application.

**Technical context:** Apereo CAS Protocol, Java 17+, Spring Boot 3.x with Spring Security Servlet/MVC, and a Jakarta Servlet–compatible CAS Java Client. API names and Filter/Listener registration methods must be verified against your actual dependency version. URLs `cas.example.org` and `app.example.org` in this lesson are illustrative only.

---

## 2. Why doesn't "CAS logout" automatically delete the application's HttpSession?

The system has multiple independent lifecycles:

| Component | Owner | Typical value | Automatically deleted on CAS logout? |
| --- | --- | --- | --- |
| **Ticket-Granting Ticket (TGT)** | CAS Server/ticket registry | Central SSO session | CAS Server can destroy it per policy |
| **Ticket-Granting Cookie (TGC)** | Browser on CAS domain | Cookie referencing the TGT | CAS Server manages logout/cookie policy |
| **Service Ticket (ST)** | Issued by CAS Server for a service | `ST-opaque-...` | ST is consumed during verification, yet its ID can correlate SLO |
| **SP/CAS client HttpSession** | Spring application/Servlet container | Internal session ID such as `JSESSIONID` | **Not automatically deleted by CAS Server** if the client does not handle SLO |
| **SecurityContext/Authentication** | Spring Security inside the app session | CAS principal + authorities | Requires proper session invalidation/security cleanup |
| **Application tokens/WebSocket** | Application-specific layers | JWT, refresh token, socket connection | **Not by default** revoked by CAS SLO |

The CAS Server **does not directly hold a Java `HttpSession` object** living inside the application process. It cannot remotely invoke `session.invalidate()` on the servlet container. CAS can only **notify** the client; the application itself is responsible for locating and destroying its session.

Apereo CAS describes SLO as a **best-effort** operation: CAS sends notifications to services that participated in the centralized session; delivery can fail, the browser can close, or the client may lack support. Therefore **never promise that every device, every application, and every token is revoked** merely because a CAS logout event was emitted.

### Local logout differs from CAS SLO

- **Local logout at the application:** the app destroys the current session, while **TGT/TGC at CAS may remain**. On the next visit, the user may receive a **new ST** and log in without re-entering a password.
- **CAS logout:** CAS destroys the central session; if SLO notifications are sent, clients must process them and destroy local sessions linked to that session.
- **App-wide/global logout:** requires revoking other sessions/tokens; must be designed separately rather than arising automatically from ST mapping alone.

The goal of this lesson is to handle **the application session tied to a single CAS ST** properly, not to build a system that wipes every session across all accounts based on a browser-supplied username.

## 3. Why does the mapping use the ST even though the ticket is already consumed?

A CAS ST serves two functions at two different times:

1. **At login:** the ST is a **single-use** credential for the CAS Server to verify the user and service. If valid, the application creates a session.
2. **At CAS SLO:** the ID of the ST previously issued to the service acts as a **correlation identifier**, letting the CAS client identify which application session to terminate.

This **does not mean** the old ST becomes a reusable credential. The CAS ST remains strictly **one-time validation**. The mapping retains the ticket ID solely to **locate the session for revocation**; it must **never** be used to restore or grant a new Authentication.

Example:

~~~text
CAS Server issues ST:     ST-opaque-A1
App verifies ST:          SUCCESS, user-42
App HTTP session:         SESSION-SP-7F9
SLO mapping at app:       ST-opaque-A1 -> SESSION-SP-7F9

Later, CAS logout:
  logoutRequest.SessionIndex = ST-opaque-A1

App lookup:
  ST-opaque-A1 -> SESSION-SP-7F9

App executes:
  invalidate(HttpSession SESSION-SP-7F9)
  remove mapping ST-opaque-A1
~~~

Neither the **TGT ID** nor the **HttpSession ID** should appear in place of `SessionIndex` in a CAS Protocol SLO message. In Apereo CAS, the session identifier used to correlate SLO is normally the **original Service Ticket ID** of that service.

### Do not confuse CAS SLO with SAML 2.0 SLO

CAS Protocol back-channel SLO can use XML named `<samlp:LogoutRequest>` and `<samlp:SessionIndex>`. **SAML-like XML shape** does not mean the application should route this message into `Saml2LogoutRequestFilter` or apply all rules of the **SAML 2.0 Single Logout Profile** verbatim. CAS SLO and SAML 2.0 SLO are two distinct **protocol integrations**, even when Apereo CAS Server supports both.

In **CAS SLO**, the `SessionIndex` sent by the CAS Server is used to **look up ST→session**. In **SAML 2.0 Web Browser SSO/SLO**, `SessionIndex` typically relates to `AuthnStatement` under different SAML profiles; do not assume it is a CAS ST.

## 4. Full flow: login followed by back-channel SLO

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Spring Security CAS client
    participant INDEX as ST-to-HttpSession mapping
    participant CAS as CAS Server
    B->>APP: GET /private
    APP-->>B: Redirect CAS /login?service=...
    B->>CAS: GET CAS login, TGC/TGT or new authentication
    CAS-->>B: Redirect /login/cas?ticket=ST-ABC
    B->>APP: GET /login/cas?ticket=ST-ABC
    APP->>INDEX: Bind ST-ABC to the active session
    APP->>CAS: HTTPS /serviceValidate?ticket=ST-ABC&service=...
    CAS-->>APP: authenticationSuccess
    APP->>APP: Store Authentication in HttpSession
    APP-->>B: Redirect to resource without ticket
    Note over CAS,APP: When the user logs out of CAS
    B->>CAS: CAS /logout
    CAS->>CAS: Destroy TGT, select participating services
    CAS->>APP: POST logoutRequest with SessionIndex=ST-ABC
    APP->>INDEX: lookup ST-ABC
    INDEX-->>APP: HttpSession to destroy
    APP->>APP: session.invalidate()
    APP->>INDEX: Clean up mapping
    APP-->>CAS: Appropriate HTTP response
    B->>APP: Request with old SP cookie
    APP->>APP: No matching authenticated session remains
~~~

**Library ordering note:** CAS Java Client `SingleSignOutFilter` typically records the mapping when it sees a request containing the ticket parameter, **before downstream authentication filters**. Therefore, in real code, **never treat the presence of a mapping as proof that ST validation succeeded**. Only a successful CAS TicketValidator result grants Authentication; stale mappings from failed logins or expiry must be cleaned up per policy. Some applications build the mapping **after validation success**; ensure you do not lose SLO capability or introduce races.

## 5. CAS SLO message shape: SessionIndex is the ST

According to Apereo CAS SLO documentation, a **back-channel logout** can send an HTTP POST from the CAS Server to each participating service. The payload contains a SAML-shaped LogoutRequest, for example:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas-logout-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>opaque-principal-42</saml:NameID>
  <samlp:SessionIndex>ST-ABC</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

This is **illustrative XML**, not a real credential and carrying no signature. In typical CAS client deployments, the message is delivered in a form parameter named `logoutRequest`; with front-channel, depending on configuration, a different encoding may be used (such as Base64 in query parameters). **Do not assume** every CAS version sends an unwrapped raw XML body or that every front-channel variant uses the same format.

### Commonly misunderstood fields

| Element | Meaning in CAS SLO | Do not infer |
| --- | --- | --- |
| `LogoutRequest@ID` | Logout message identifier | Not an HttpSession ID |
| `LogoutRequest@IssueInstant` | Message timestamp | Not the ST issuance time |
| `NameID` | Principal info carried by the notice | Never use alone to delete all sessions by email |
| `SessionIndex` | **ST ID used by CAS to correlate with the service's session** | Not JSESSIONID, CAS TGT, or SAML login SessionIndex of arbitrary products |
| `logoutRequest` | Default form/query parameter name in CAS Java Client | Not the login `ticket` param |
| `RelayState` if present | Optional auxiliary parameter depending on flow/client | Not the core session mapping key in CAS SLO |

### Back-channel carries no user browser cookie

With a direct POST from **CAS Server → application**, the user's browser **is not involved in this request**. Hence the notification normally **carries no user `JSESSIONID`**. A controller/filter written as:

~~~java
HttpSession current = request.getSession(false);
if (current != null) {
    current.invalidate();
}
~~~

will **fail to find the user's session to log out** because the back-channel request lacks the right cookie. Worse, calling `getSession(true)` can create a new session for the CAS Server's request while leaving the target session untouched.

The solution is to **locate the user's session via `SessionIndex=ST` mapped at login**, and then invalidate the found session. Never rely on a browser cookie in a back-channel callback.

## 6. What mechanisms does the CAS Java Client provide?

Key components in **Apereo Java CAS Client**:

| Component | Role |
| --- | --- |
| `org.apereo.cas.client.session.SingleSignOutFilter` | Intercepts requests with ST to record mappings; receives SLO callbacks and destroys associated sessions |
| `SingleSignOutHandler` | Handles token registration and logout message processing inside the library |
| `SessionMappingStorage` | Contract for storing ticket ↔ session mappings; supports lookup and removal |
| `HashMapBackedSessionMappingStorage` | Default/example in-memory mapping in client releases |
| `SingleSignOutHttpSessionListener` | Cleans up mappings when an `HttpSession` is destroyed/expires |
| `artifactParameterName` | Login ticket parameter name, default `ticket` |
| `logoutParameterName` | CAS SLO parameter name, default `logoutRequest` |
| `logoutCallbackPath` | Restricts the SLO callback path per version capability; not the general service URL |
| `eagerlyCreateSessions` | Controls session creation behavior when seeing a ticket per CAS Java Client config |
| `org.springframework.security.cas.web.CasAuthenticationFilter` | Spring Security filter that authenticates the CAS ticket |
| `CasAuthenticationProvider` | Spring Security provider that invokes TicketValidator to verify the ticket |

**The two filters have distinct responsibilities:**
- `SingleSignOutFilter`: **records/looks up/destroys session mappings** for logout.
- `CasAuthenticationFilter`: **validates the Service Ticket** via CAS TicketValidator and creates Authentication.

Never substitute one for the other. An application with **only** `CasAuthenticationFilter` can log in normally yet **will not** receive or destroy sessions when CAS sends Single Logout.

### Why must the SLO filter run before the CAS authentication filter?

When the browser returns:

~~~text
GET /login/cas?ticket=ST-A
    |
    v
SingleSignOutFilter: record ST-A → HttpSession
    |
    v
Spring Security filter chain / CasAuthenticationFilter
    |
    v
TicketValidator /serviceValidate
    |
    + success → SecurityContext in the same HttpSession
~~~

To record the mapping at the right time and process logout POSTs before other filters block the request, **SingleSignOutFilter generally needs to run earlier** than CAS authentication and Spring Security authorization/CSRF handlers. If an SLO POST hits a 403 CSRF rejection in another filter before reaching the CAS SLO filter, the application session **is not invalidated**.

Do not "fix" this with `csrf().disable()` for the whole application. Route/register the SLO filter in the right position, restrict the callback, and protect the caller origin per your threat model. CAS client setups using a Servlet Filter outside the Spring Security chain have different ordering; verify the effective filter order with an integration test.

## 7. Configuring CAS client SLO with Spring Boot Servlet

### 7.1 Related dependencies

In a Gradle project using a compatible Boot plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'

    // Choose the Java CAS Client artifact/version compatible with Spring Security
    // and jakarta.servlet in Spring Boot 3, or the dependency already managed
    // by spring-security-cas/the application.
}
~~~

This is a **snippet** inside a project with complete build configuration, not a standalone build file. Inspect Spring Security CAS transitive dependencies and the matching Java CAS Client; do not pull in an old **`javax.servlet`** artifact into a **`jakarta.servlet`** application expecting the Filter to work.

### 7.2 Registering SingleSignOutFilter and Session Listener

Sample **Spring Boot Servlet configuration**, assuming the current dependencies actually provide compatible `org.apereo.cas.client.session.*` classes:

File `src/main/java/com/example/cas/CasSingleLogoutConfig.java`:

~~~java
package com.example.cas;

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
    FilterRegistrationBean<SingleSignOutFilter> casSloFilterRegistration() {
        var bean = new FilterRegistrationBean<SingleSignOutFilter>();
        bean.setFilter(new SingleSignOutFilter());

        // Must observe login requests carrying ticket and SLO callbacks.
        bean.addUrlPatterns("/*");

        // Runs before Spring Security's CAS authentication filter.
        // Verify the actual order of encoding and security filters on deployment.
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
        bean.setName("casSingleSignOutFilter");
        return bean;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
~~~

**Conditions and limitations:**
- This is **Spring Configuration code**, not standalone Java; it requires Boot, the CAS client, Jakarta Servlet, and a real web application.
- Mapping the filter to `/*` allows it to see both `GET /login/cas?ticket=...` and SLO callbacks sent to either the service URL or a dedicated logout URL.
- The order `Ordered.HIGHEST_PRECEDENCE + 50` is illustrative only; check `CharacterEncodingFilter` (UTF-8), Spring Security's `DelegatingFilterProxy`, and other servlet filters in the real system.
- When restricting the logout path, the CAS client offers `logoutCallbackPath` depending on version. You must **preserve the ability to record login tickets** even if logout callbacks are handled only on a dedicated path.
- If the application already registers `SingleSignOutFilter` via `web.xml`, `@EnableCasClient`, or auto-config, **do not register it twice**.
- Spring Boot 3 uses `jakarta.servlet.*`; older CAS client versions may only support `javax.servlet.*`. Use a compatible release.
- The filter may create a session upon seeing a ticket depending on the `eagerlyCreateSessions` policy; test login and inspect `HttpSession` after successful CAS validation.
- The listener cleans up mappings when a session expires or is invalidated. Do not omit the listener just because "logout worked" in a short test.
- Do not let `CasAuthenticationFilter` be auto-registered as a Servlet Filter **twice** if it is also added to the Spring `SecurityFilterChain`.

### 7.3 Spring Security CAS must be configured separately

`SingleSignOutFilter` **does not replace** CAS authentication. The application still requires:

1. `ServiceProperties.service` set to the **public callback URL**, e.g., `https://app.example.org/login/cas`.
2. `CasAuthenticationEntryPoint` directing the browser to CAS login.
3. `CasAuthenticationFilter` receiving the ST at the callback.
4. `CasAuthenticationProvider` calling the CAS Server with a `TicketValidator`.
5. `AuthenticationUserDetailsService` or principal/authorities mapping per policy.
6. A Spring `SecurityFilterChain` protecting business endpoints.
7. Appropriate session persistence upon successful authentication.

A small bean illustrating `ServiceProperties` (not a complete app):

~~~java
@Bean
ServiceProperties serviceProperties() {
    var properties = new ServiceProperties();
    properties.setService("https://app.example.org/login/cas");
    properties.setSendRenew(false);
    return properties;
}
~~~

**Do not copy snippets missing imports/enclosing classes**: `ServiceProperties` belongs to `org.springframework.security.cas.ServiceProperties`, and `@Bean` belongs to Spring Context. You must accurately configure the CAS Server `/login`, service registry, and ticket validation endpoint. In CAS, `service` is also the URL CAS can use as the SLO callback if no separate `logoutUrl` is configured.

## 8. CAS Server config: which services receive notifications?

Per Apereo CAS, SLO can be configured **per registered service**:
- `logoutType = BACK_CHANNEL` is commonly the default choice in CAS documentation.
- `logoutType = FRONT_CHANNEL` delivers notifications via the browser; depends on client and browser capabilities.
- `logoutType = NONE` / equivalent disablement for a service if supported by policy/version.
- `logoutUrl` can specify a **dedicated SLO receiver endpoint**, distinct from the `service` URL used at login.

Illustrative **CAS registered service JSON** fragment showing the format—not a complete file, since service registry schemas and class names depend on CAS version:

~~~json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://app\\.example\\.org/.*",
  "name": "Portal CAS Service",
  "id": 102,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://app.example.org/login/cas"
}
~~~

Notes:
- `serviceId` is typically a CAS-managed regex registration. The example is illustrative; production must **narrow the pattern** to authorized callback paths/hosts rather than broad wildcards.
- CAS SLO can post to the **original service URL** or a separate `logoutUrl` when configured; the app SLO filter must observe the matching path.
- `logoutUrl` is only the notification receiver endpoint, **not a URL for the browser to initiate logout**.
- The CAS service registry must be updated through operational workflows, never from arbitrary browser JSON.
- The CAS Server may dispatch SLO asynchronously; delivery failure to an app does not necessarily fail CAS logout.
- The SLO message uses the Service Ticket ID associated with the login service; if URL configuration changes, mappings still rely on the same ticket/account session.

### Verifying the endpoint via traces

In CAS Server logs (redacted), verify:
1. The TGT is destroyed per the logout flow.
2. Participating services are selected by CAS for notification.
3. For this application: `logoutType`, SLO endpoint, and HTTP response.
4. The `SessionIndex` used by CAS matches the original ST.
5. An actual HTTP POST reaches the app (or front-channel per config).
6. The app looked up the mapping, invalidated the session, and cleaned up the mapping.
7. A new browser request with the old cookie is no longer authenticated.

Never infer "SLO completed" merely from the CAS logout page returning HTTP 200.

## 9. Back-channel and front-channel: different foundations for session mapping

| Aspect | Back-channel SLO | Front-channel SLO |
| --- | --- | --- |
| Request sender | CAS Server calls SP directly | Browser redirects/calls SP at CAS's instruction |
| Typical HTTP method | HTTP POST | HTTP GET/JSONP/AJAX or iframe, depending on CAS version |
| Browser user cookie | **Not present by default** | May be present or blocked by SameSite/third-party policies |
| Payload | LogoutRequest/SessionIndex typically via `logoutRequest` | Payload/encoding may differ, e.g., base64 query param |
| Data to locate session | **ST → HttpSession mapping** | May still need ST mapping; do not depend on cookies |
| Failure points | Firewall/network, wrong callback URL, mapping on another node | Browser closed, cookies blocked, JS/iframe restrictions |
| App-side requirements | Back-channel receiver endpoint/filter, session store | CAS client version supporting front-channel and compatible browser policy |
| "All sessions" guarantee | Best-effort, depends on service/session reachability | Best-effort, depends on browser workflow |

**Important:** Never build a custom front-channel logout via `GET /logout?username=alice` that deletes sessions from user input. CAS already defines the notification protocol and ticket mapping; browser requests are not inherently trusted commands. If a client **does not support front-channel**, configuring CAS to send front-channel leaves local sessions alive even after CAS logout occurs.

## 10. What does SessionMappingStorage manage?

In Apereo Java CAS Client, **SessionMappingStorage** represents the mapping store between a CAS authentication token identifier (usually an ST) and the application's `HttpSession`. Common operations across Java CAS Client versions include:

- Adding a mapping: logic similar to `addSessionById(ticket, session)`.
- Looking up and removing by mapping ID on logout: logic similar to `removeSessionByMappingId(ticket)`.
- Removing the mapping when a session is destroyed/expires: logic similar to `removeBySessionById(sessionId)`.
- Cleaning stale mappings to avoid retaining references to expired sessions.

**Mental model:**

~~~text
At login:
  CAS Service Ticket ST-ABC
          |
          v
  SessionMappingStorage
          |
          v
  HttpSession session-A
          |
          v
  SecurityContext + CAS principal

At CAS SLO:
  logoutRequest.SessionIndex = ST-ABC
          |
          v
  SessionMappingStorage.removeSessionByMappingId("ST-ABC")
          |
          v
  session-A.invalidate()
~~~

This is a conceptual model of the client library's behavior, **not a guarantee of public Spring Security API names callable everywhere**. Across versions, class/method names and capabilities vary; do not reimplement mapping yourself if the official library already provides it.

### The mapping must be created at the right moment

An anti-pattern:

~~~text
CAS ticket validation SUCCESS
    -> Spring creates HttpSession B
    -> Earlier mapping filter recorded ST against HttpSession A
    -> SLO finds A and invalidates A
    -> B remains authenticated
~~~

If the app uses **session fixation protection** or creates a new session during login, verify that the mapping points to **the final session holding the SecurityContext**. The Servlet session ID can change due to `changeSessionId()` or session migration. Never assume `request.getSession().getId()` before login always equals the session ID after authentication.

In deployments using the official CAS client, verify in practice:
1. When the SLO filter observes the ticket and session.
2. Whether CAS AuthenticationFilter/SessionAuthenticationStrategy swaps the session.
3. Whether the session listener cleans up the mapping when the old session is destroyed.
4. Whether an SLO notification invalidates the post-login authenticated session.
5. If not, select a compatible session fixation strategy/extension point or update the mapping **safely after login success**.

**Do not disable session fixation protection** just to keep the session ID unchanged for mapping. Make the mapping and session lifecycle work together cleanly.

## 11. Distinguishing a recorded mapping from successful authentication

In many CAS Java Client versions, `SingleSignOutFilter` records the mapping when it **sees the `ticket` parameter** in a request. At that moment, the CAS ST **has not necessarily been validated yet**. If the ticket is invalid:
- A temporary mapping may exist for an unauthenticated session;
- Existence of a mapping grants zero access rights;
- The mapping must be cleaned up on session expiry, destruction, or failed login per policy;
- Never treat the mapping as an authentication cache.

In custom-built stores, you might choose to record the mapping **only after** the CAS validator returns success; however, you must handle the **race** between authentication success, session persistence, and an almost-simultaneous SLO notification. CAS can emit SLO immediately if the user logs out elsewhere. Thus ensure:
- Only verified STs are mapped;
- The mapping points to the exact authenticated session;
- An SLO arriving before the mapping is committed does not turn into a "lost logout" leaving a new session created after CAS logout;
- State/version/recording lifecycle checks and, if needed, a safely designed TTL-bound pending revocation/tombstone mechanism are in place;
- Never relax permissions to work around races.

An SLO handler that simply receives XML and calls `request.getSession(true).invalidate()` is **wrong** for back-channel calls.

## 12. Cleaning up mappings when sessions end

There are at least four cleanup scenarios:

| Event | Required action |
| --- | --- |
| CAS SLO arrives with mapped ST | Remove ST mapping, invalidate HttpSession, clean up reverse index |
| Local logout at the application | Invalidate HttpSession and remove all associated mappings |
| Idle/absolute session expiry | Listener cleans up mapping to avoid stale memory retention |
| Session fixation rotation or session migration | Update mapping to the new session; clean up old association |
| New CAS login for existing user/session | Decide replace/merge per policy; avoid inconsistent multi-ST mappings to one session |
| Application redeploy | In-memory mappings are lost; do not claim SLO will work for sessions surviving in another store if the map is not recovered |
| Session already invalidated, duplicate SLO | Idempotent no-op; never delete another session |
| Session store/Redis outage | Mark uncertain/retry/alert; never claim logout definitely succeeded |

**SingleSignOutHttpSessionListener** cleans up mappings when a session is destroyed or expires, preventing accumulation of ticket IDs and references to `HttpSession` objects inside the JVM. However, the listener must also be properly registered in the Servlet container (Spring Boot `ServletListenerRegistrationBean`/`web.xml`) with a compatible version.

### Can one session have multiple STs?

This can happen when a user logs in again in the same browser, across multiple tabs, forced reauthentication, or custom flows. Some CAS Java Client implementations **remove the old mapping by session ID when registering a new ST**, effectively keeping only the current mapping for that session. If an app builds custom multi-ticket mapping:
- Clean up **all ticket keys** when the session is invalidated;
- Define semantics if an old ticket still relates to an invalidated TGT;
- Never allow the same ticket key to point to two sessions simultaneously;
- Never use a shared username as the mapping key;
- Evaluate old/new principal login and session fixation.

Never assume one ST always equals one session ID or that one user has exactly one session.

## 13. Session fixation and HttpSession ID changes after login

Spring Security includes **session fixation protection**, which in the Servlet stack commonly changes the session ID when a user logs in. If the CAS SLO filter stores a mapping to the session object before login, verify:
- If `changeSessionId()` keeps **the same logical HttpSession object** with a new ID, a mapping referencing the session object may still destroy the right session; any ID-based reverse index must stay consistent.
- If a migration/new-session strategy swaps the session object, the old mapping may point to an already-invalidated session.
- A `sessionDestroyed` listener may clean up the old mapping, yet **will not automatically create a new mapping** without a hook.
- With distributed session ID mappings, old and new IDs must be updated atomically per policy.

A mandatory test sequence:

~~~text
1. GET /private -> redirect to CAS
2. CAS callback with ticket ST-A
3. SingleSignOutFilter records mapping
4. CAS AuthenticationProvider validation SUCCESS
5. Spring session fixation strategy runs
6. Capture the session ID holding the SecurityContext
7. CAS logout sends SessionIndex=ST-A
8. SLO filter must invalidate the session from step 6
~~~

**Do not fix this by disabling CSRF/session fixation app-wide.** Session handling must remain securely configured while mappings are handled properly across the lifecycle.

## 14. Multi-browser/multi-device logins

For example, a user logs in to the same account from three browsers:

| Browser | CAS ST used | App HttpSession |
| --- | --- | --- |
| Laptop Chrome | `ST-A` | `session-A` |
| Laptop Firefox | `ST-B` | `session-B` |
| Phone | `ST-C` | `session-C` |

These sessions may belong to **different TGTs** or the same/different CAS SSO sessions depending on browser/cookies. The CAS Server only sends SLO for authentication records it links to the destroyed TGT.

If a notification carries:
- `SessionIndex=ST-A`: the app finds **session-A** and destroys only that session.
- `SessionIndex=ST-B`: the app destroys **session-B** if that record belongs to the matching CAS event.
- No `ST-C` mapping: do not infer "user X" and wipe all devices.

**Never let SLO from ST-A automatically delete all of a user's sessions by email** unless there is a separate business requirement and dedicated revocation mechanism designed and authorized for it. CAS SLO ticket mapping targets **the session authenticated by the corresponding ticket**, not an admin global-logout API.

## 15. Multi-pod applications: why can in-memory mapping fail?

Example two-pod deployment:

~~~text
Browser CAS callback ST-A ---> app-pod-1
                               Mapping(ST-A) = HttpSession object on pod-1

CAS back-channel SLO -------> app-pod-2
                               In-memory mapping on pod-2: UNKNOWN
                               app-pod-1 session remains active
~~~

Spring Security documentation illustrates Java CAS Client `SingleSignOutFilter` using a static map to locate HttpSessions. A **static map lives only inside that JVM** and does not automatically synchronize across pods. Spring Session sharing the session store is **not enough** if the ticket→session SLO mapping remains local.

### Strategies

| Approach | Pros | Limitations |
| --- | --- | --- |
| Single-node or sticky routing for all login/SLO | Simple for lab/small deployments | CAS SLO carries no user cookie, so browser-cookie sticky LB **does not guarantee** hitting the right node |
| Distributed ticket→sessionId index | Finds the right session from any pod | Requires custom storage/integration and TTL/revocation consistency |
| Distributed session store (Spring Session Redis/JDBC) | Any pod can read/invalidate a session by ID | Still requires **ST→sessionId mapping** and callback origin protection |
| Verified broker/event bridge | Can coordinate across SPs and session revocation | Not a CAS Java Client default; contract must be verified |
| Short session TTL + live authorization | Limits the window if notifications fail | Does not replace immediate SLO if policy requires it |

**Conclusion:** If SLO can land on a different pod, you need a mechanism where that pod uses the ST to **find the actual session**, rather than relying solely on sticky routing.

### Illustrative Redis architecture

~~~text
Login callback on pod A:
  ticket: ST-X
  finalSessionId: SESSION-9
  -> CAS_SLO:<hash(ST-X)> = SESSION-9   (TTL tied to app session)
  -> optional reverse index SESSION-9 -> {ticket-hashes}
  -> session in Spring Session Redis

SLO callback on pod B:
  receives SessionIndex=ST-X
  -> compute suitably protected key hash
  -> look up and atomically consume mapping
  -> sessionRepository.deleteById("SESSION-9")
  -> remove reverse mappings
  -> audit result
~~~

This is a **custom-designed model**, not a CAS Java Client default or an official Redis schema. If the app manages Spring Session Redis:
- The ST is a short-lived secret; avoid using raw STs as broadly visible Redis keys/logs. You can use **HMAC-SHA256(ticket, server secret)** as the index key to reduce token exposure in stores/logs (requires key management).
- Session IDs are sensitive credentials; ensure the store has proper ACLs, TLS, encryption/retention.
- Use atomic consumption (Lua/transaction/compare-and-delete) to prevent duplicate callbacks and mapping races.
- Mapping TTL must **follow the session lifecycle**, not the ST validation TTL (because the ST is already consumed while the app session may live much longer).
- When the session ID changes due to fixation protection, **update the mapping**.
- When the session expires/logs out locally, clean up mappings/reverse indexes.
- If a CAS SLO event arrives before the mapping is committed, handle pending revocation/ordering safely.
- During a Redis outage, **never** claim SLO succeeded when the session has not been deleted.

### Do not use username alone as the key

`ST-X → session-X` is a mapping per **authentication transaction**, whereas `username → sessions` is a broader lookup. One user can have multiple sessions/tenants/IdPs. If a user index is required, use identifiers scoped by issuer/tenant/immutable ID with strict authorization to avoid wrong logouts. **CAS SessionIndex never requires the app to extract username from XML and wipe all sessions**.

## 16. Security considerations: is a CAS SLO callback inherently trustworthy?

**No.** Even though a logout notification is a signal emitted by the CAS Server, the application must still defend against an endpoint receiving a forged POST. CAS Protocol SLO **can use SAML-shaped XML, yet you must not assume that message is signed with a SAML XML Signature per the full SAML 2.0 SLO Profile**. In particular, some CAS Java Client implementations process the ST in `SessionIndex` without message signature verification like a Spring Security SAML provider.

### Typical threat model

An attacker can:
- Send `POST logoutRequest=...` to a public endpoint, attempting to target someone else's `SessionIndex`.
- Exploit a ticket leaked in URLs/logs to force-logout the corresponding session (**logout DoS**).
- Replay notifications repeatedly to cause load/noise if the app is not idempotent.
- Attack the XML parser with DTD/XXE or huge payloads if the parser is unhardened.
- Manipulate the request path or `Host` header to bypass routing policies.
- Abuse a filter placed before CSRF to forge callbacks against arbitrary sessions.
- Exploit multi-node mapping races so a session escapes invalidation.

### Appropriate protections

1. **Restrict SLO back-channel origin:** only allow the CAS Server/trusted proxy gateway to reach the callback via network/firewall/mTLS or supported message authentication. IP allowlisting alone is not a complete guarantee across all networks/proxies.
2. **Restrict endpoint/path:** the CAS logout callback must sit on a registered URL accepting only the expected method/format/size; never let the browser pick an arbitrary user/session.
3. **Do not trust Host/Forwarded headers** outside configured reverse proxies.
4. **Parse XML safely**: disable XXE/entity expansion, enforce body size and nesting depth limits.
5. **Look up by ST mapping**, never by NameID/email from XML.
6. **Atomic consume and idempotency:** duplicate notifications must not destroy other sessions or re-grant Authentication.
7. **TLS between CAS Server ↔ app** and hostname/client cert verification per architecture.
8. **Audit/metrics without raw STs** or HttpSession IDs, keeping event correlation/traces protected.
9. **Callback authorization and CSRF:** back-channel calls carry no browser CSRF token; if exempted from CSRF, exempt only that exact endpoint/flow protected by another control, never disable CSRF app-wide.
10. **Fail safely:** if caller origin cannot be verified, do not destroy sessions from arbitrary input; if mapping is not found, do not delete by user text.
11. **Rate limit** without breaking legitimate CAS delivery while curbing SLO spam.
12. **Do not treat front-channel JavaScript/JSONP as server authentication**, and evaluate CORS/Origin/CSRF and framework support independently.

**Important:** Because an SLO handler only destroys sessions, the main risk is **denial of service/logout CSRF**, yet the impact still matters for transactions and multi-session apps. Never weaken validation just to make "logout always work".

## 17. Relationship between ST expiry and mapping retention

A common misconception is: "The ST expires after a few minutes, so deleting the ST→session mapping after a few minutes is right."

Incorrect. The **ST credential** only needs to live long enough for **one-time** CAS validation. However, the **ST ID as a correlation key for SLO** may need to be retained **until the associated application session is destroyed**.

Example:
- 09:00: ST-A is issued and validated successfully; afterwards ST-A is no longer valid for login.
- 09:01: `HttpSession-A` remains authenticated.
- 12:00: User logs out at CAS; CAS sends `SessionIndex=ST-A`.
- 12:00: If the app deleted the mapping because "ST validation TTL is only a few minutes", it cannot find `HttpSession-A`.

Therefore:
- Mapping retention normally tracks the **HttpSession lifespan** and is cleaned up via a session listener.
- Do not retain the raw ST as a credential, only as a safe index/correlation key.
- Enforce TTL/quotas/cleanup to prevent memory leaks if session events are missed.
- On session invalidation/local logout, clear the mapping immediately.
- For distributed sessions, store the mapping with a lifetime aligned to session TTL, not set to the ST TTL.

In multi-node designs, carefully balance late SLO delivery, session lifetime, cache retention, and sensitive-data policies.

## 18. Duplicate SLO, local logout, and idempotency

An already-destroyed session may continue receiving SLO notifications due to CAS Server retries or proxies. Correct handling:

~~~text
Receive SLO with SessionIndex=ST-A
  -> lookup ST-A
  -> if known: atomically remove mapping, invalidate mapped session
  -> if not found: no-op, record unknown/duplicate without leaking ST
  -> respond according to client protocol and monitoring policy
~~~

**Idempotent** behavior:
- An ST→session mapping is consumed at most once.
- Duplicate notifications never create a new session.
- `HttpSession.invalidate()` may throw `IllegalStateException` if already invalidated; handlers/libraries should treat it cleanly as "already invalid".
- Never delete all sessions sharing a username when the ST is not found.
- If the service performed local logout before CAS SLO arrived, the listener may have already removed the mapping; an empty lookup is normal.
- Never allow an old SLO to invalidate **the user's new session** simply because the user logged back in with a different ST.

### Re-login scenario

~~~text
09:00 ST-OLD -> session-1
09:30 Local logout session-1; mapping ST-OLD removed
09:31 CAS TGC still active, issues ST-NEW
09:31 ST-NEW -> session-2

Late CAS SLO message for ST-OLD:
  Must not destroy session-2 just because of the same username.
~~~

If an app only kept a `username→currentSession` table and used NameID, a late notice for the old login could mistakenly log out the new session. Thus **keying by ST** is essential.

## 19. Standalone Java 17: simulating ST → session and invalidating the exact session

The program below uses **no Spring or CAS Server**, only the Java 17 Standard Library. It simulates:
- Recording the **ST → application session** mapping.
- One session optionally linked to multiple tickets in a demo case, with a reverse index.
- When SLO carries a known ST, **destroying the exact session** and cleaning up all ticket keys for that session.
- Duplicate/stale SLO simply no-ops without affecting other sessions.
- Local logout cleans up the mapping.
- Never print tickets or session secrets in a real app; the demo prints fake IDs for traceability.

File `CasSloSessionMappingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;

public final class CasSloSessionMappingDemo {

    static final class Session {
        final String label;
        boolean active = true;

        Session(String label) {
            this.label = label;
        }

        void invalidate() {
            active = false;
        }
    }

    static final class TicketSessionIndex {
        private final Map<String, Session> byTicket = new HashMap<>();
        private final Map<Session, Set<String>> bySession =
                new IdentityHashMap<>();

        synchronized void record(String ticket, Session session) {
            if (ticket == null || ticket.isBlank() || session == null
                    || !session.active) {
                throw new IllegalArgumentException(
                        "Ticket and active session required");
            }
            Session previous = byTicket.put(ticket, session);
            if (previous != null && previous != session) {
                Set<String> previousTickets = bySession.get(previous);
                if (previousTickets != null) {
                    previousTickets.remove(ticket);
                    if (previousTickets.isEmpty()) {
                        bySession.remove(previous);
                    }
                }
            }
            bySession.computeIfAbsent(session, ignored -> new HashSet<>())
                    .add(ticket);
        }

        synchronized String onCasLogout(String ticket) {
            Session session = byTicket.get(ticket);
            if (session == null) {
                return "NO_MAPPING";
            }
            removeAllMappings(session);
            if (!session.active) {
                return "ALREADY_INACTIVE";
            }
            session.invalidate();
            return "INVALIDATED:" + session.label;
        }

        synchronized void onLocalSessionDestroyed(Session session) {
            removeAllMappings(session);
            session.invalidate();
        }

        private void removeAllMappings(Session session) {
            Set<String> ticketKeys = bySession.remove(session);
            if (ticketKeys != null) {
                for (String key : ticketKeys) {
                    byTicket.remove(key);
                }
            }
        }

        synchronized int mappingCount() {
            return byTicket.size();
        }
    }

    public static void main(String[] args) {
        TicketSessionIndex index = new TicketSessionIndex();
        Session a = new Session("session-A");
        Session b = new Session("session-B");
        Session c = new Session("session-C");

        index.record("ST-A1", a);
        index.record("ST-A2", a);
        index.record("ST-B1", b);
        index.record("ST-C1", c);

        System.out.println("Before: " + index.mappingCount());
        System.out.println("CAS ST-A1: "
                + index.onCasLogout("ST-A1"));
        System.out.println("CAS ST-A2 later: "
                + index.onCasLogout("ST-A2"));
        System.out.println("A active: " + a.active);
        System.out.println("B active: " + b.active);
        System.out.println("Mappings now: " + index.mappingCount());

        index.onLocalSessionDestroyed(c);
        System.out.println("Local logout C active: " + c.active);
        System.out.println("CAS ST-C1 later: "
                + index.onCasLogout("ST-C1"));

        System.out.println("CAS ST-B1: "
                + index.onCasLogout("ST-B1"));
        System.out.println("Mappings final: " + index.mappingCount());
    }
}
~~~

Compile/run on Java 17+:

~~~bash
javac CasSloSessionMappingDemo.java
java CasSloSessionMappingDemo
~~~

**Exact** stdout:

~~~text
Before: 4
CAS ST-A1: INVALIDATED:session-A
CAS ST-A2 later: NO_MAPPING
A active: false
B active: true
Mappings now: 2
Local logout C active: false
CAS ST-C1 later: NO_MAPPING
CAS ST-B1: INVALIDATED:session-B
Mappings final: 0
~~~

### Result explanation

1. Four ticket keys were mapped to three sessions.
2. CAS SLO for `ST-A1` located session A, invalidated A, and cleaned up both ST-A1/ST-A2.
3. Late SLO for ST-A2 found no mapping; session B was unaffected.
4. Local logout C invalidated session C and cleaned up ST-C1; the subsequent SLO was a no-op.
5. CAS SLO ST-B1 destroyed only session B.
6. At the end, zero mappings remain.

**This is not a production CAS Client:**
- ST IDs in the demo are predictable; real CAS requires high-entropy tickets.
- `HashMap/IdentityHashMap` are valid only inside one JVM and do not handle clusters.
- `Session` is a mock object, not `jakarta.servlet.http.HttpSession`.
- No HTTPS, SLO callback authentication, XML parser, or ticket validation.
- Allowing one session to hold multiple STs is a **demo policy**. Default Java CAS Client in many versions replaces the mapping when the same session receives a new ticket; verify actual semantics before applying such logic.
- Never accept self-declared browser input to call `onCasLogout(ticket)` on a real server.
- Production requires notification origin validation, index protection, atomicity across SLO/mapping/session store, cleanup, and auditing.

## 20. Testing at the right time: after CAS login, not just before login

A test that only verifies `ticket→session ID` was recorded at callback time **is insufficient**. You must prove that **the session holding Spring Security Authentication** is the session that gets destroyed.

### Test A — login then CAS SLO

1. Log in to CAS with a test account, capturing the initial ST in a redacted trace.
2. CAS validation returns success; Spring creates an authenticated session.
3. Verify a protected route allows requests with the browser cookie.
4. On the test CAS Server, trigger logout and dispatch notifications to the service.
5. Verify the app processes CAS SLO and invalidates the exact session created.
6. Send a subsequent request with the old cookie: Authentication is gone, normally redirecting back to CAS login per the entry point.
7. Do not claim all three devices/apps logged out unless CAS confirmed delivery.

### Test B — cookie-less CAS back-channel

1. Test CAS Server sends POST `logoutRequest` **without browser JSESSIONID**.
2. App must locate the session from the ST mapping.
3. Do not use `request.getSession(true)` from the callback as the session to destroy.
4. Afterwards, the old browser session is no longer authenticated.

### Test C — SessionIndex is not HttpSession ID

1. Receive SLO with `SessionIndex=ST-A`.
2. App looks up ST-A in the mapping and finds session S.
3. Verify it **does not** look up the servlet session directly using the string `ST-A`.
4. Do not fall back to `NameID` as a shortcut when the ST is missing.

### Test D — local logout before CAS SLO

1. Log in and record the mapping.
2. App local logout invalidates HttpSession.
3. Listener/mapping removal performs cleanup.
4. CAS Server later sends logout for the old ST.
5. App handles it as a safe no-op without creating a new session or destroying another session.

### Test E — duplicate SLO

1. CAS Server/test harness sends the same notification twice in a controlled test.
2. The first call invalidates the right session.
3. The second call no-ops without throwing a 500 error or destroying an unrelated new session.
4. Metrics distinguish already-processed from genuine failures when evidence exists.

### Test F — multi-node app

1. CAS login callback hits **pod A**.
2. SLO callback hits **pod B**.
3. If mappings are in-memory, the test exposes the miss; do not infer SLO succeeded from CAS 200.
4. With distributed mapping + Spring Session, pod B looks up ST→sessionId and deletes the right session.
5. The old cookie no longer grants access on either A or B.
6. Test restarting pod A between login and SLO.

### Test G — session fixation

1. Record the session ID before CAS authentication.
2. Log in successfully through Spring Security.
3. Record the session ID **after** session fixation protection (never log raw values outside tests).
4. Send CAS SLO containing the original ST.
5. Must destroy the **post-login session** holding Authentication.
6. Do not fix by disabling session fixation protection.

### Test H — one session with multiple tickets/reauthentication

1. Have the user reauthenticate or log in again in the same browser session if the flow supports it.
2. Check whether the client replaces the old mapping or keeps multiple ticket keys.
3. SLO for the appropriate ticket must destroy the session per contract.
4. An old mapping must not mistakenly destroy a new session belonging to another principal.
5. Test policy when an old CAS TGT is logged out after the app obtained a new ST.

## 21. Callback security testing

| Test | Expected result |
| --- | --- |
| POST logoutRequest from untrusted source | Restricted/rejected per architecture; never deletes arbitrary sessions |
| SessionIndex is an unknown ticket | No-op + metrics; never creates a new session |
| SessionIndex is a forged raw JSESSIONID | Never looks up a session directly by that value |
| NameID matches a username in another tenant | Never deletes all sessions by NameID |
| XML message contains DTD/XXE | Does not parse external entities; rejects payload |
| Oversized/deeply nested XML | Bounded by size/processing time limits |
| SLO notification sent twice | Idempotent no-op on the second call |
| SLO message arrives after local logout | Does not alter the new authenticated session |
| Ticket leaked in proxy logs | Redact + investigate; never treat ST as non-sensitive |
| CAS SLO over unprotected HTTP | Disallowed in production trust design |
| SLO POST without CSRF token | Only the dedicated callback protected by appropriate caller/transport controls |
| User POSTs logoutRequest from browser | Never allowed to arbitrarily invalidate someone else's session |
| Redis session mapping tampered with | Protect ACL/integrity; never trust client-supplied mappings |
| Session fixation changes ID | Mapping must point to the current authenticated session |
| App session remains while CAS TGT expired | CAS SLO works if required; live authorization remains independent |
| Unauthorized/403 from business endpoint | Do not assume it is a CAS SLO validation failure |

Run negative tests only in authorized **lab/CAS test services**; never send forged logout messages to real users.

## 22. Distinguishing protocol errors from session lookup errors

| Symptom | Where to check |
| --- | --- |
| CAS SSO logged out yet app stays authenticated | SLO notification delivery, filter mapping, lookup/session invalidation |
| No POST logoutRequest arrives at app | CAS registered service `logoutType/logoutUrl`, network/firewall |
| CAS gets HTTP 200 yet session is not destroyed | Did the filter actually parse the request and find the right ST mapping? |
| Filter sees message yet mapping is missing | Mapping expired, on another pod, session ID changed, login callback missed |
| Ticket present in login query yet no mapping | SLO filter order, `artifactParameterName`, filter path, session creation |
| Mapping points to old session | Session fixation strategy, migration, duplicate sessions |
| Local logout followed by SLO throws 500 | Duplicate handling, listener cleanup, already-invalidated session |
| Different pods behave differently | In-memory map, Redis/session store, replica configuration |
| SLO POST gets 403 CSRF | SLO filter order/callback endpoint; never disable CSRF site-wide |
| Front-channel works in browser A but not B | Client support, SameSite/cookie/iframe/JS restrictions |
| User logs out of app then auto-SSOs right back in | CAS TGT/TGC remains; local logout ≠ CAS logout |
| Another application remains logged in | Best-effort SLO delivery, unsupported service, different session scope |
| Unsure if ST can still be used | ST is consumed at login; ID maps logout only; never retry validation |
| JWT/API token remains valid after CAS SLO | Separate token lifecycle; requires explicit revocation if needed |
| CAS XML looks like SAML LogoutRequest yet Spring SAML filter rejects it | Confusing CAS Protocol SLO with SAML 2.0 SLO |

### Distinguishing SessionIndex

In CAS SLO:
- `SessionIndex` is a **service-ticket-based correlation key**.
- `HttpSession` is the local application object.
- `CAS TGT` is the server-side global SSO session.
- `Cookie TGC` lives on the CAS domain.
- `JSESSIONID` is the application cookie and does not travel with a CAS back-channel POST.

A properly managed mapping table connects **ST** to **application session**, rather than conflating those five things.

## 23. Spring Security CAS client and proactive logout at the application

An application typically offers two actions:

**A. Local logout**:
- Spring Security `LogoutFilter/SecurityContextLogoutHandler` clears the local SecurityContext/session.
- The listener cleans up the ST mapping.
- CAS TGT/TGC may still remain.
- When the user visits again, CAS can issue a new ST and continue SSO.

**B. Global CAS logout flow**:
- The application can perform local logout first, then redirect the browser to CAS `/logout`.
- CAS destroys the central session and sends SLO notifications to participating CAS services if enabled.
- Each application receiving SLO must use its ST mapping to invalidate matching local sessions.
- Other apps may fail to receive or process SLO; there is no guarantee every node/device/token is revoked.

Spring Security CAS reference recommends logging out locally before issuing a CAS global logout request, because the client's local session must be explicitly cleaned up rather than relying entirely on external propagation.

**Do not confuse CAS `/logout` with SAML2 `/logout/saml2/slo`** in Spring Security. The SAML2 provider uses `LogoutRequest/Response` with its own protocol, keys, and trust metadata; CAS SLO in this lesson uses the CAS Java Client/session mapping.

## 24. Operations documentation: verifying an end-to-end CAS SLO

A runbook report can look like:

~~~text
CAS SLO test — portal
Protocol: CAS (not direct SAML2)
Service alias: portal-public-callback
Login ticket: [REDACTED]
CAS notification SessionIndex: [REDACTED]
CAS logoutType: BACK_CHANNEL
CAS logout target: configured registered-service SLO URL
Client SLO filter: registered and ordered before auth/CSRF flow
Mapping storage: in-memory / distributed (explicit)
Original authenticated session: found
Session invalidation result: completed
Mapping cleanup result: completed
Subsequent browser request: unauthenticated
Other apps: unknown unless separately verified
~~~

Never store raw CAS STs, session cookies, principal emails, or full LogoutRequests in support tickets. Record only **protected ticket hashes/correlation IDs**, service alias, node, and outcome. If no mapping is found, record **MAPPING_MISS** instead of blindly claiming "CAS failed".

Reference metrics:
- `cas_slo_notification_received_total`
- `cas_slo_session_mapping_hit_total`
- `cas_slo_session_mapping_miss_total`
- `cas_slo_session_invalidated_total`
- `cas_slo_session_already_expired_total`
- `cas_slo_delivery_failure_total` on the CAS Server side if available
- Latency from CAS logout → app invalidation

Metric labels should use only `serviceAlias, result, node, channel` with bounded cardinality, **never** raw ST/sessionId/username.

## 25. Common mistakes

1. **"CAS destroying the TGT means the app session disappears automatically."** False; the app must receive the notification and invalidate its local session.
2. **"Back-channel POST carries the user's cookie."** Not by default, since the request is sent by the CAS Server.
3. **"SessionIndex in CAS SLO is JSESSIONID."** False; in CAS Protocol it is used as the service ticket ID.
4. **"Mapping the ST after validation is useless because the ST is already spent."** False; the ST ID still correlates logout.
5. **"An ST mapping proves the user is authenticated."** False; the mapping may be recorded prior to validation.
6. **"SAML-shaped LogoutRequest means full SAML2 SLO."** False; CAS Protocol SLO has its own contract.
7. **"Having only CasAuthenticationFilter gives you SLO."** False; an SLO filter/client integration is required.
8. **"SingleSignOutFilter on pod A automatically knows sessions on pod B."** False with in-memory mapping.
9. **"Browser-cookie sticky routing always solves CAS back-channel."** False; back-channel calls may carry no browser cookie.
10. **"HttpSessionListener is unnecessary."** Can cause stale mappings and leaks when sessions expire/log out.
11. **"Seeing HTTP 200 from CAS/app proves logout finished."** False; you must verify real session invalidation.
12. **"On mapping miss, delete all sessions with the same username."** Risks wrong logouts and DoS.
13. **"The SLO callback is a public POST, so trust any XML sent to it."** False; protect origin/transport and parse safely.
14. **"SLO callback lacks a CSRF token, so disable CSRF site-wide."** Wrong; narrow exceptions and protect via other controls.
15. **"Mapping TTL equals ST validation TTL."** False; the mapping must live as long as the session needing logout.
16. **"An ST can be kept as a bearer credential for the app to re-login."** False; ST is a one-time credential.
17. **"After local logout, leaving the old ST mapping is harmless."** False; stale mappings can leak memory or destroy a new session.
18. **"There is only one JSESSIONID across all devices."** False; each browser/device can hold its own session.
19. **"Spring Session Redis automatically synchronizes in-memory CAS mappings."** No; a separate distributed ST→session ID map is required if SLO lands on another pod.
20. **"Every SLO success means JWTs/refresh tokens/WebSockets are revoked."** Not by default.
21. **"Changing the session ID after login always keeps the mapping valid."** Depends on fixation strategy/client map; must be tested.
22. **"A late notification for an old ST may destroy the same user's new login session."** Wrong if the new session no longer belongs to the old ST.

## 26. Exercises and answers

**Exercise 1.** CAS sends `SessionIndex=ST-ABC` to the app with no JSESSIONID cookie. How do you find the session?

**Answer:** Look up **ST-ABC** in `SessionMappingStorage`, retrieve the HttpSession/sessionId recorded at login, and invalidate that session.

**Exercise 2.** `SingleSignOutFilter` is placed after the Spring Security CSRF filter and the SLO POST gets 403. What happens?

**Answer:** The SLO handler may not run and the session stays active. Fix the filter order and SLO callback security scope properly without disabling CSRF across all routes.

**Exercise 3.** The ST was already consumed by CAS `serviceValidate`. Why keep the mapping until the session expires?

**Answer:** The ST ID becomes the correlation key for CAS SLO; it is **not a credential for logging in again**.

**Exercise 4.** When CAS logs out ST-A and lookup finds no mapping, should the app delete all sessions for `NameID=alice`?

**Answer:** No. A mapping miss can happen due to an expired session, another pod, cleanup, or an error. Deleting by username without an explicit trust boundary causes erroneous logouts.

**Exercise 5.** The CAS SLO POST reaches app-pod-2, yet the ticket mapping lives only in app-pod-1's RAM. Is SLO guaranteed?

**Answer:** No. You need a distributed ST→sessionId mapping and a session store revocable from the callback-receiving node, or a verified propagation architecture.

**Exercise 6.** Spring Session Redis already shares HttpSession; does that automatically make the CAS ST mapping distributed?

**Answer:** No. If the mapping is managed in-JVM by Java CAS Client `HashMapBackedSessionMappingStorage`, it remains local.

**Exercise 7.** Why is `SingleSignOutHttpSessionListener` important?

**Answer:** It cleans up mappings when sessions are destroyed/expired, preventing stale ST mappings and memory leaks.

**Exercise 8.** An SLO notification arrives twice; the first already invalidated the session. What should the second do?

**Answer:** Idempotent no-op once the mapping is gone; never create a new session and never delete another user's session.

**Exercise 9.** The SLO message uses the `samlp:LogoutRequest` tag. Can it be passed directly to Spring's `Saml2LogoutRequestFilter`?

**Answer:** No. CAS Protocol SLO has its own ST mapping and is not equivalent to the full SAML 2.0 SLO profile.

**Exercise 10.** The browser logs out at the app, yet CAS TGC remains. The user revisits the app and gets a new ST. Is this a bug?

**Answer:** It can be normal for **local logout**; the CAS SSO session was not destroyed. Global logout requires CAS `/logout` and appropriate SLO policies.

**Exercise 11.** `SingleSignOutFilter` records the mapping as soon as it sees a `ticket` query parameter. Does the mapping existing prove CAS validation succeeded?

**Answer:** No. The filter may record before `CasAuthenticationProvider`/`TicketValidator`. Only successful CAS validation may establish Authentication.

**Exercise 12.** When the session fixation strategy changes the HttpSession ID after login, what must be tested?

**Answer:** Ensure ST-based SLO destroys the **post-login** session holding the SecurityContext; never disable fixation protection to work around failures.

**Exercise 13.** Why must the back-channel SLO endpoint be protected from forged requests?

**Answer:** An attacker knowing/guessing an ST could send a forged `logoutRequest` to force-terminate sessions, creating logout CSRF/DoS risk. Use transport/origin validation and callback controls.

**Exercise 14.** If ST-A was issued for session A, then after local logout the user gets session B from ST-B, and CAS sends a stale notification for ST-A, should B be destroyed?

**Answer:** No. The ST-A mapping should have been cleaned up when A ended; a stale notification must not destroy session B belonging to a different ST.

**Exercise 15.** CAS logout returns HTTP 200 and CAS sends a notification, yet a browser with the old SP cookie still has access. What should you check?

**Answer:** SLO delivery to the app, endpoint/filter order, mapping hit, session fixation, session store/multi-node behavior, and actual session invalidation.

**Exercise 16.** For back-channel SLO, why is `request.getSession(true).invalidate()` insufficient?

**Answer:** Requests from the CAS Server carry no user browser cookie, so it would create/invalidate a session for the callback request itself, **not the user session** to log out.

**Exercise 17.** How long should a ticket→session mapping TTL be?

**Answer:** Normally aligned with the **application HttpSession** lifecycle and cleanup, not merely the few-minute ST validation TTL. Keep retention and session expiry policies synchronized.

**Exercise 18.** What factors besides mapping does front-channel CAS SLO depend on?

**Answer:** Whether the Java CAS client supports front-channel, browser GET/JSONP/iframe execution, SameSite/cookie/third-party restrictions, and delivery; browser completion is never guaranteed.

## 27. Implementation and QA checklist

- [ ] Confirmed this is **CAS Protocol SLO**, not confused with SAML2 Single Logout.
- [ ] CAS Server service registry enables SLO appropriately; `logoutType` and `logoutUrl` are verified.
- [ ] CAS login callback receives an ST validated by the CAS Server against the exact service URL.
- [ ] `SingleSignOutFilter` observes login requests carrying STs and receives CAS logout notifications.
- [ ] The SLO filter processes requests **before** filters that could block the callback.
- [ ] No duplicate filter registrations across Servlet and Spring Security chains.
- [ ] `SingleSignOutHttpSessionListener` is registered to clean up session mappings.
- [ ] ST→session mapping binds to the **final authenticated session**, including after session fixation.
- [ ] `SessionIndex` in CAS SLO is looked up by **ST**, not JSESSIONID/NameID.
- [ ] Back-channel CAS SLO works **without browser cookies**.
- [ ] Across multiple nodes, ticket mapping and session deletion are accessible across all nodes.
- [ ] Local logout/session expiry cleans up mappings; duplicate SLO is idempotent.
- [ ] Mapping retention aligns with session lifetime rather than expiring after ST validation TTL.
- [ ] SLO endpoint is origin/transport-protected, restricts method/size/format, and hardens the XML parser.
- [ ] No public API exposes ticket/SessionIndex lookups confirming session existence.
- [ ] No raw STs, CAS TGT/TGC, JSESSIONID, cookies, full LogoutRequest, or sensitive principals in logs.
- [ ] App authorization and API tokens/WebSockets have separate revocation when required by business policy.
- [ ] Tested login→SLO, local logout before SLO, duplicates, session fixation, multiple tabs, and multiple nodes.
- [ ] Tested back-channel POST, front-channel if used, CAS Server outages, and mapping misses.
- [ ] Metrics/traces exist for notifications received, mapping hits/misses, session invalidations, retries/outages.
- [ ] Never claim "logged out of all devices/applications" when only one SP session was destroyed.

## 28. Key takeaways

**The CAS Server manages the central login session; the Spring application manages its own HttpSession.** When CAS wants to Single Logout an application session, it sends the corresponding **Service Ticket ID** in the notification's `SessionIndex`. The CAS client needs an **ST → HttpSession mapping**, looks up that mapping on logout, invalidates **the exact session**, and cleans up the mapping.

Short formula:

~~~text
LOGIN:
  CAS issues ST
  -> application receives ST and CAS TicketValidator verifies it
  -> ST is associated with the authenticated HttpSession

CAS SINGLE LOGOUT:
  CAS destroys SSO session
  -> sends logoutRequest (SessionIndex=ST)
  -> CAS client looks up ST→HttpSession
  -> HttpSession.invalidate()
  -> delete mapping and reject use of the old session

CONDITIONS:
  CAS SLO notification must be received securely;
  mapping must exist on the handling node;
  the destroyed session must be the one holding Authentication.
~~~

**Do not equate ST with JSESSIONID, do not rely on NameID to wipe all sessions, do not treat ST mapping as authentication, and never omit caller protection on the SLO notification endpoint.**

### Official documentation

1. Apereo CAS 8.x — *Logout & Single Logout*, back-channel, front-channel, SessionIndex as Service Ticket, `logoutType/logoutUrl`: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
2. Apereo CAS — *CAS Protocol 2.0 Specification*, Single Logout section and logout XML Appendix C: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
3. Apereo Java CAS Client — *README: Configuring Single Sign Out*, filter, listener, artifactParameterName, logoutRequest: https://github.com/apereo/java-cas-client/blob/master/README.md
4. Spring Security — *CAS Authentication: Single Logout*, SingleSignOutFilter, local logout vs CAS logout, session mapping: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
5. Spring Session — *API/SessionRepository*, distributed session management: https://docs.spring.io/spring-session/reference/api.html
6. Spring Security — *Session Management*, session fixation and HttpSession security: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
7. Apereo CAS 7.3.x — *Logout & Single Logout*, per-service SLO config: https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html
8. Spring Boot — *FilterRegistrationBean / ServletListenerRegistrationBean* API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
